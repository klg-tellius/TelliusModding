"""Nintendo Wii BRSTM (``RSTM``) streamed DSP-ADPCM audio.

Radiant Dawn keeps music, voices and some long sound effects in
``Sound/strm/*.brstm``.  The container divides each channel into interleaved
blocks and stores the decoder history for every block in ``ADPC``.  The
sample codec itself is the same DSP-ADPCM implementation used by PoR's STM
and THP support.

The writer deliberately accepts a retail file as a template.  This keeps
the archive-authored HEAD track/channel layout and any unknown flags while
replacing only the documented stream geometry, channel ADPCM state, ADPC
history table and DATA payload.  A template is also the safest basis for a
new RD stream: callers choose a stream with the required channel count.
"""

from __future__ import annotations

import struct
import wave
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO, Optional

from . import dsp_adpcm

MAGIC = b"RSTM"
HEAD_MAGIC = b"HEAD"
ADPC_MAGIC = b"ADPC"
DATA_MAGIC = b"DATA"
ALIGN = 0x20


class BrstmError(ValueError):
    pass


@dataclass
class BrstmAudio:
    sample_rate: int
    channels: list[list[int]]
    loop_start: Optional[int] = None


@dataclass(frozen=True)
class BrstmInfo:
    codec: int
    sample_rate: int
    channel_count: int
    loop_start: Optional[int]
    sample_count: int
    block_count: int
    block_size: int
    samples_per_block: int
    last_block_used: int
    last_block_samples: int
    last_block_padded: int
    head_offset: int
    head_size: int
    adpc_offset: int
    adpc_size: int
    data_offset: int
    data_size: int
    stream_info_offset: int
    channel_info_offsets: tuple[int, ...]
    adpcm_info_offsets: tuple[int, ...]


def _align(value: int, alignment: int = ALIGN) -> int:
    return (value + alignment - 1) // alignment * alignment


def _u32(data: bytes | bytearray, at: int) -> int:
    if at < 0 or at + 4 > len(data):
        raise BrstmError(f"Offset {at:#x} is outside the BRSTM")
    return struct.unpack_from(">I", data, at)[0]


def _reference(data: bytes | bytearray, at: int, base: int) -> int:
    """Read an NW4R eight-byte reference (type/pad plus relative offset)."""
    if at < 0 or at + 8 > len(data):
        raise BrstmError("Truncated BRSTM reference")
    return base + _u32(data, at + 4)


def read_info(data: bytes | bytearray) -> BrstmInfo:
    if len(data) < 0x40 or data[:4] != MAGIC:
        raise BrstmError("Not a BRSTM file (missing RSTM header)")
    bom, version, file_size, header_size = struct.unpack_from(">HHIH", data, 4)
    if bom != 0xFEFF:
        raise BrstmError(f"Unsupported BRSTM byte order {bom:#x}")
    if version not in (0x0100, 0x0101):
        raise BrstmError(f"Unsupported BRSTM version {version:#x}")
    if file_size != len(data) or header_size < 0x28 or header_size > len(data):
        raise BrstmError("BRSTM header size does not match the file")

    head_offset, head_size, adpc_offset, adpc_size, data_offset, data_size = struct.unpack_from(">6I", data, 0x10)
    for magic, offset, size in ((HEAD_MAGIC, head_offset, head_size),
                                (ADPC_MAGIC, adpc_offset, adpc_size),
                                (DATA_MAGIC, data_offset, data_size)):
        if offset < header_size or size < 8 or offset + size > len(data) or data[offset:offset + 4] != magic:
            raise BrstmError(f"Invalid {magic.decode()} section")
        if _u32(data, offset + 4) != size:
            raise BrstmError(f"{magic.decode()} section size does not match its header")

    reference_base = head_offset + 8
    stream_info = _reference(data, head_offset + 8, reference_base)
    channel_refs = _reference(data, head_offset + 24, reference_base)
    if stream_info + 0x34 > head_offset + head_size:
        raise BrstmError("Truncated BRSTM stream info")
    codec, loop_flag, channel_count, _pad, sample_rate = struct.unpack_from(">4BH", data, stream_info)
    if codec != 2:
        raise BrstmError(f"Unsupported BRSTM codec {codec}; only DSP-ADPCM is supported")
    if channel_count not in (1, 2):
        raise BrstmError(f"Unsupported BRSTM channel count {channel_count}")
    (loop_start, sample_count, audio_offset, block_count, block_size, samples_per_block,
     last_used, last_samples, last_padded, _adpc_samples, adpc_entry_size) = struct.unpack_from(">11I", data, stream_info + 8)
    if not block_count or not block_size or not samples_per_block or adpc_entry_size != 4:
        raise BrstmError("Invalid BRSTM block geometry")
    if audio_offset < data_offset + 8 or audio_offset > data_offset + data_size:
        raise BrstmError("BRSTM audio payload is outside DATA")
    expected_payload = (block_count - 1) * block_size * channel_count + last_padded * channel_count
    if audio_offset + expected_payload > data_offset + data_size:
        raise BrstmError("BRSTM block data runs past DATA")

    # HEAD3 begins with an eight-bit count and three reserved bytes.
    if channel_refs + 4 > len(data) or data[channel_refs] != channel_count:
        raise BrstmError("BRSTM channel table count disagrees with stream info")
    channel_infos = []
    adpcm_infos = []
    for channel in range(channel_count):
        channel_info = _reference(data, channel_refs + 4 + channel * 8, reference_base)
        adpcm_info = _reference(data, channel_info, reference_base)
        if adpcm_info + 0x2E > head_offset + head_size:
            raise BrstmError("Truncated BRSTM channel ADPCM info")
        channel_infos.append(channel_info)
        adpcm_infos.append(adpcm_info)

    return BrstmInfo(codec, sample_rate, channel_count, loop_start if loop_flag else None, sample_count,
                     block_count, block_size, samples_per_block, last_used, last_samples, last_padded,
                     head_offset, head_size, adpc_offset, adpc_size, data_offset, data_size, stream_info,
                     tuple(channel_infos), tuple(adpcm_infos))


def _adpcm_info(data: bytes | bytearray, at: int) -> dsp_adpcm.AdpcmInfo:
    coef = list(struct.unpack_from(">16h", data, at))
    gain, pred_scale = struct.unpack_from(">HH", data, at + 32)
    yn1, yn2 = struct.unpack_from(">hh", data, at + 36)
    loop_pred_scale = struct.unpack_from(">H", data, at + 40)[0]
    loop_yn1, loop_yn2 = struct.unpack_from(">hh", data, at + 42)
    return dsp_adpcm.AdpcmInfo(coef, gain, pred_scale, yn1, yn2, loop_pred_scale, loop_yn1, loop_yn2)


def read_brstm(data: bytes | bytearray) -> BrstmAudio:
    info = read_info(data)
    audio_start = info.data_offset + 0x20
    channels = [bytearray() for _ in range(info.channel_count)]
    cursor = audio_start
    for block in range(info.block_count):
        used = info.last_block_used if block == info.block_count - 1 else info.block_size
        padded = info.last_block_padded if block == info.block_count - 1 else info.block_size
        for channel in range(info.channel_count):
            channels[channel] += data[cursor:cursor + used]
            cursor += padded
    pcm = [dsp_adpcm.decode(bytes(encoded), _adpcm_info(data, at), info.sample_count)
           for encoded, at in zip(channels, info.adpcm_info_offsets)]
    return BrstmAudio(info.sample_rate, pcm, info.loop_start)


def read_brstm_path(path: Path | str) -> BrstmAudio:
    return read_brstm(Path(path).read_bytes())


def write_brstm(audio: BrstmAudio, template: bytes | bytearray) -> bytes:
    """Encode ``audio`` while retaining the template's safe HEAD layout."""
    old = read_info(template)
    channel_count = len(audio.channels)
    if channel_count != old.channel_count:
        raise BrstmError(f"The template has {old.channel_count} channels; imported audio has {channel_count}")
    if channel_count not in (1, 2) or not audio.channels:
        raise BrstmError("BRSTM audio must be mono or stereo")
    sample_count = len(audio.channels[0])
    if sample_count <= 0 or any(len(channel) != sample_count for channel in audio.channels):
        raise BrstmError("All BRSTM channels must have the same non-zero sample count")
    if not 1 <= audio.sample_rate <= 0xFFFF:
        raise BrstmError("BRSTM sample rate must fit an unsigned 16-bit value")
    if audio.loop_start is not None and not 0 <= audio.loop_start < sample_count:
        raise BrstmError("BRSTM loop start is outside the audio")
    # A parsed, untouched document has an exact representation already.  DSP
    # re-encoding is lossy, so returning that source is both faster and the
    # only correct byte-identical round trip.
    if audio == read_brstm(template):
        return bytes(template)

    block_size = old.block_size
    samples_per_block = block_size // dsp_adpcm.BYTES_PER_FRAME * dsp_adpcm.SAMPLES_PER_FRAME
    encoded: list[bytes] = []
    adpcm_infos: list[dsp_adpcm.AdpcmInfo] = []
    for pcm in audio.channels:
        channel_info = dsp_adpcm.AdpcmInfo()
        channel_data = dsp_adpcm.encode(list(pcm), channel_info)
        if audio.loop_start is not None:
            dsp_adpcm.get_loop_context(channel_data, channel_info, audio.loop_start)
        encoded.append(channel_data)
        adpcm_infos.append(channel_info)

    block_count = (sample_count + samples_per_block - 1) // samples_per_block
    last_samples = sample_count - (block_count - 1) * samples_per_block
    last_used = dsp_adpcm.bytes_for_adpcm_samples(last_samples)
    last_padded = _align(last_used)
    checkpoints = [index * samples_per_block for index in range(block_count)]
    states = [dsp_adpcm.get_states_at(data, info.coef, sample_count, checkpoints)
              for data, info in zip(encoded, adpcm_infos)]

    head = bytearray(template[old.head_offset:old.head_offset + old.head_size])
    stream = old.stream_info_offset - old.head_offset
    struct.pack_into(">4BH", head, stream, 2, int(audio.loop_start is not None), channel_count, 0, audio.sample_rate)
    struct.pack_into(">11I", head, stream + 8, audio.loop_start or 0, sample_count, 0, block_count,
                     block_size, samples_per_block, last_used, last_samples, last_padded,
                     samples_per_block, 4)
    for at, channel_info in zip(old.adpcm_info_offsets, adpcm_infos):
        pos = at - old.head_offset
        struct.pack_into(">16hHHhhHhh", head, pos, *channel_info.coef, channel_info.gain,
                         channel_info.pred_scale, channel_info.yn1, channel_info.yn2,
                         channel_info.loop_pred_scale, channel_info.loop_yn1, channel_info.loop_yn2)

    adpc_payload = bytearray()
    for block_start in checkpoints:
        for channel in range(channel_count):
            hist1, hist2 = states[channel][block_start]
            adpc_payload += struct.pack(">hh", hist1, hist2)
    adpc_size = _align(8 + len(adpc_payload))
    adpc = bytearray(adpc_size)
    adpc[:4] = ADPC_MAGIC
    struct.pack_into(">I", adpc, 4, adpc_size)
    adpc[8:8 + len(adpc_payload)] = adpc_payload

    data_payload = bytearray()
    for block in range(block_count):
        start = block * block_size
        used = last_used if block == block_count - 1 else block_size
        padded = last_padded if block == block_count - 1 else block_size
        for channel_data in encoded:
            chunk = channel_data[start:start + used]
            data_payload += chunk + bytes(padded - len(chunk))
    data_size = 0x20 + len(data_payload)
    data_section = bytearray(data_size)
    data_section[:4] = DATA_MAGIC
    struct.pack_into(">I", data_section, 4, data_size)
    data_section[0x20:] = data_payload

    header_size = struct.unpack_from(">H", template, 0x0C)[0]
    head_offset = _align(header_size)
    adpc_offset = _align(head_offset + len(head))
    data_offset = _align(adpc_offset + len(adpc))
    file_size = data_offset + len(data_section)
    out = bytearray(file_size)
    out[:header_size] = template[:header_size]
    out[head_offset:head_offset + len(head)] = head
    out[adpc_offset:adpc_offset + len(adpc)] = adpc
    out[data_offset:data_offset + len(data_section)] = data_section
    struct.pack_into(">I", out, 8, file_size)
    struct.pack_into(">6I", out, 0x10, head_offset, len(head), adpc_offset, len(adpc), data_offset, len(data_section))
    # DATA payload offsets in HEAD are absolute file offsets.
    struct.pack_into(">I", out, head_offset + stream + 0x10, data_offset + 0x20)
    return bytes(out)


def brstm_to_wav_path(audio: BrstmAudio, path: Path | str) -> None:
    channel_count = len(audio.channels)
    sample_count = len(audio.channels[0])
    interleaved = [0] * (sample_count * channel_count)
    for index, channel in enumerate(audio.channels):
        interleaved[index::channel_count] = channel
    with wave.open(str(path), "wb") as output:
        output.setnchannels(channel_count)
        output.setsampwidth(2)
        output.setframerate(audio.sample_rate)
        output.writeframes(struct.pack(f"<{len(interleaved)}h", *interleaved))


def wav_path_to_brstm_audio(path: Path | str, loop_start: Optional[int] = None) -> BrstmAudio:
    with wave.open(str(path), "rb") as source:
        channel_count = source.getnchannels()
        width = source.getsampwidth()
        sample_rate = source.getframerate()
        raw = source.readframes(source.getnframes())
    if width != 2 or channel_count not in (1, 2):
        raise BrstmError("Only mono or stereo 16-bit PCM WAV files are supported")
    values = list(struct.unpack(f"<{len(raw) // 2}h", raw))
    channels = [values[index::channel_count] for index in range(channel_count)]
    return BrstmAudio(sample_rate, channels, loop_start)

