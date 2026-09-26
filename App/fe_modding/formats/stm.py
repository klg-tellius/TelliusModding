"""Nintendo "STM" streamed audio container (``Sound/*.stm``) - background
music, mono or stereo, DSP-ADPCM encoded (see dsp_adpcm.py for the codec
itself). This is a real, documented Nintendo GameCube format (vgmstream
calls its meta type ``ngc_dsp_stm``), not something invented for this game.

Layout, confirmed against two real tracks (matching field-for-field,
including the two fields whose meaning wasn't documented anywhere found -
see below):

- 0x00 (2B): magic, always 0x0200
- 0x02 (2B): sample rate
- 0x04 (4B): channel count (1 or 2)
- 0x08 (4B): per-channel ADPCM byte size (dsp_adpcm.bytes_for_adpcm_samples(num_samples))
- 0x0c (4B): per-channel ADPCM byte *offset of the loop point*
  (bytes_for_adpcm_samples(loop_start_in_samples)) - confirmed by computing
  this independently from each real file's loop_start (itself stored as a
  nibble address in the DSP header below) and getting an exact match both
  times.
- 0x10, 0x14: repeats of the 0x08 value; 0x18, 0x1c: repeats of the 0x0c
  value. Both real samples were stereo with identical channel lengths, so
  it's not possible to tell from them alone whether these are meant to be
  literal per-channel duplicates or something narrower that just happens to
  coincide - writing the same shared value into all of them is what's done
  here, safe for the always-in-sync stereo/mono case this covers.
- 0x20-0x3f: zero padding
- 0x40 + channel_index*0x60: one standard 0x60-byte DSP-ADPCM header per
  channel (num_samples, num_nibbles, sample_rate, loop flag, loop
  start/end as *nibble* addresses, the 16 predictor coefficients, initial
  and loop history state - see dsp_adpcm.AdpcmInfo)
- 0x100: audio data, one block per channel back-to-back (not small-chunk
  interleaved - each channel's entire stream is one block), each block
  padded to "interleave" bytes: ``(channel_byte_size + 0x20) // 0x20 * 0x20``
  (always rounds up by at least one 32-byte block, even if already aligned)
"""

from __future__ import annotations

import struct
import wave
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO, Optional

from . import dsp_adpcm

MAGIC = 0x0200
HEADER_SIZE = 0x100
DSP_HEADER_SIZE = 0x60
DSP_HEADERS_START = 0x40
ALIGN = 0x20


class StmError(Exception):
    pass


@dataclass
class StmAudio:
    sample_rate: int
    channels: list[list[int]]  # one list of PCM16 samples per channel
    loop_start: Optional[int] = None  # sample index, or None if the track doesn't loop


def _interleave(size: int) -> int:
    return (size + ALIGN) // ALIGN * ALIGN


def read_stm(stream: BinaryIO) -> StmAudio:
    header = stream.read(HEADER_SIZE)
    if len(header) < HEADER_SIZE:
        raise StmError("File too short to be an STM.")

    magic, sample_rate = struct.unpack(">HH", header[0:4])
    if magic != MAGIC:
        raise StmError(f"Not an STM file (expected magic {MAGIC:#x}, got {magic:#x}).")
    (num_channels,) = struct.unpack(">I", header[4:8])
    if num_channels not in (1, 2):
        raise StmError(f"Unexpected channel count {num_channels} (only 1 or 2 seen in real files).")

    channels: list[list[int]] = []
    loop_start = None

    for ch in range(num_channels):
        base = DSP_HEADERS_START + ch * DSP_HEADER_SIZE
        dsp_header = header[base : base + DSP_HEADER_SIZE]
        num_samples, num_nibbles, dsp_rate = struct.unpack(">III", dsp_header[0:12])
        loop_flag, _fmt = struct.unpack(">HH", dsp_header[12:16])
        loop_start_nibble, _loop_end_nibble, _initial_offset = struct.unpack(">III", dsp_header[16:28])
        coef = list(struct.unpack(">16h", dsp_header[28:60]))
        _gain, pred_scale = struct.unpack(">HH", dsp_header[60:64])
        yn1, yn2 = struct.unpack(">hh", dsp_header[64:68])

        info = dsp_adpcm.AdpcmInfo(coef=coef, pred_scale=pred_scale, yn1=yn1, yn2=yn2)

        data_size = dsp_adpcm.bytes_for_adpcm_samples(num_samples)
        block = _interleave(data_size)
        stream.seek(HEADER_SIZE + ch * block)
        adpcm_data = stream.read(data_size)
        if len(adpcm_data) < data_size:
            raise StmError(f"Channel {ch}: expected {data_size} bytes of audio data, file has less.")

        channels.append(dsp_adpcm.decode(adpcm_data, info, num_samples))

        if loop_flag:
            loop_start = dsp_adpcm.get_sample_for_adpcm_nibble(loop_start_nibble)

    return StmAudio(sample_rate=sample_rate, channels=channels, loop_start=loop_start)


def read_stm_path(path: Path | str) -> StmAudio:
    with open(path, "rb") as stream:
        return read_stm(stream)


def write_stm(audio: StmAudio) -> bytes:
    num_channels = len(audio.channels)
    if num_channels not in (1, 2):
        raise StmError(f"Only mono or stereo is supported (got {num_channels} channels).")
    num_samples = len(audio.channels[0])
    if any(len(ch) != num_samples for ch in audio.channels):
        raise StmError("All channels must have the same number of samples.")

    channel_data_size = dsp_adpcm.bytes_for_adpcm_samples(num_samples)
    block = _interleave(channel_data_size)

    loop_flag = 1 if audio.loop_start is not None else 0
    loop_start_sample = audio.loop_start if audio.loop_start is not None else 0
    loop_start_nibble = dsp_adpcm.get_nibble_address(loop_start_sample)
    loop_end_nibble = dsp_adpcm.get_nibbles_for_n_samples(num_samples)
    loop_byte_offset = dsp_adpcm.bytes_for_adpcm_samples(loop_start_sample)

    header = bytearray(HEADER_SIZE)
    struct.pack_into(">HH", header, 0, MAGIC, audio.sample_rate)
    struct.pack_into(">I", header, 4, num_channels)
    struct.pack_into(">IIIIII", header, 8, channel_data_size, loop_byte_offset, channel_data_size, channel_data_size, loop_byte_offset, loop_byte_offset)

    encoded_channels = []
    for ch_index, pcm in enumerate(audio.channels):
        info = dsp_adpcm.AdpcmInfo()
        adpcm = dsp_adpcm.encode(pcm, info)
        if loop_flag:
            dsp_adpcm.get_loop_context(adpcm, info, loop_start_sample)

        base = DSP_HEADERS_START + ch_index * DSP_HEADER_SIZE
        num_nibbles = dsp_adpcm.get_nibbles_for_n_samples(num_samples)
        struct.pack_into(">III", header, base, num_samples, num_nibbles, audio.sample_rate)
        struct.pack_into(">HH", header, base + 12, loop_flag, 0)
        struct.pack_into(">III", header, base + 16, loop_start_nibble, loop_end_nibble, 2)
        struct.pack_into(">16h", header, base + 28, *info.coef)
        struct.pack_into(">HH", header, base + 60, info.gain, info.pred_scale)
        struct.pack_into(">hh", header, base + 64, info.yn1, info.yn2)
        struct.pack_into(">H", header, base + 68, info.loop_pred_scale)
        struct.pack_into(">hh", header, base + 70, info.loop_yn1, info.loop_yn2)

        encoded_channels.append(adpcm)

    out = bytearray(header)
    for adpcm in encoded_channels:
        out += adpcm
        out += bytes(block - len(adpcm))

    return bytes(out)


def write_stm_path(path: Path | str, audio: StmAudio) -> None:
    Path(path).write_bytes(write_stm(audio))


# -- WAV helpers (stdlib `wave` module - no extra dependency) ---------------


def stm_to_wav_path(audio: StmAudio, path: Path | str) -> None:
    num_channels = len(audio.channels)
    num_samples = len(audio.channels[0])

    interleaved = [0] * (num_samples * num_channels)
    for ch_index, pcm in enumerate(audio.channels):
        interleaved[ch_index::num_channels] = pcm

    with wave.open(str(path), "wb") as w:
        w.setnchannels(num_channels)
        w.setsampwidth(2)
        w.setframerate(audio.sample_rate)
        w.writeframes(struct.pack(f"<{len(interleaved)}h", *interleaved))


def wav_path_to_stm_audio(path: Path | str, loop_start: Optional[int] = None) -> StmAudio:
    with wave.open(str(path), "rb") as w:
        num_channels = w.getnchannels()
        sample_width = w.getsampwidth()
        sample_rate = w.getframerate()
        num_frames = w.getnframes()
        raw = w.readframes(num_frames)

    if sample_width != 2:
        raise StmError(f"Only 16-bit WAV is supported (this file is {sample_width * 8}-bit).")
    if num_channels not in (1, 2):
        raise StmError(f"Only mono or stereo WAV is supported (this file has {num_channels} channels).")

    total_samples = len(raw) // 2
    all_samples = list(struct.unpack(f"<{total_samples}h", raw))

    if num_channels == 1:
        channels = [all_samples]
    else:
        channels = [all_samples[0::2], all_samples[1::2]]

    return StmAudio(sample_rate=sample_rate, channels=channels, loop_start=loop_start)
