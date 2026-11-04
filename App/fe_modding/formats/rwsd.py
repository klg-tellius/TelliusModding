"""Nintendo Wii ``RWSD`` wave-sound data embedded in a BRSAR.

An RSAR stores an RWSD's metadata and sample bytes separately in a group's
header and wave-data regions.  DATA maps the sound index from INFO to a WAVE
entry; WAVE describes one or more PCM or DSP-ADPCM channels.  This module is
deliberately read-only for now, but parses enough of both sections to provide
bounded, loop-aware previews without guessing at archive offsets.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass

from . import dsp_adpcm


class RwsdError(ValueError):
    pass


@dataclass(frozen=True)
class RwsdEntry:
    wave_index: int
    pitch: float
    pan: int
    volume: int
    note_pitch: float


@dataclass(frozen=True)
class RwsdChannel:
    data_offset: int
    adpcm_info: dsp_adpcm.AdpcmInfo | None


@dataclass(frozen=True)
class RwsdWave:
    encoding: int
    sample_rate: int
    loop_start: int | None
    sample_count: int
    data_offset: int
    channels: tuple[RwsdChannel, ...]


@dataclass(frozen=True)
class RwsdFile:
    entries: tuple[RwsdEntry, ...]
    waves: tuple[RwsdWave, ...]
    header: bytes
    wave_data: bytes


@dataclass(frozen=True)
class RwsdAudio:
    sample_rate: int
    channels: tuple[tuple[int, ...], ...]
    loop_start: int | None = None


def _u32(data: bytes, at: int, label: str) -> int:
    if at < 0 or at + 4 > len(data):
        raise RwsdError(f"Truncated RWSD {label}")
    return struct.unpack_from(">I", data, at)[0]


def _reference(data: bytes, at: int, base: int, label: str) -> int:
    if at < 0 or at + 8 > len(data):
        raise RwsdError(f"Truncated RWSD {label} reference")
    kind, offset = struct.unpack_from(">2I", data, at)
    if kind == 0:
        raise RwsdError(f"RWSD {label} reference is null")
    target = base + offset
    if not 0 <= target < len(data):
        raise RwsdError(f"RWSD {label} reference lies outside the header")
    return target


def _reference_list(data: bytes, at: int, base: int, label: str) -> list[int]:
    count = _u32(data, at, f"{label} count")
    if count > (len(data) - at - 4) // 8:
        raise RwsdError(f"Truncated RWSD {label} list")
    return [_reference(data, at + 4 + index * 8, base, label) for index in range(count)]


def _adpcm_info(data: bytes, at: int) -> dsp_adpcm.AdpcmInfo:
    if at < 0 or at + 0x30 > len(data):
        raise RwsdError("Truncated RWSD DSP-ADPCM state")
    coefficients = list(struct.unpack_from(">16h", data, at))
    gain, pred_scale = struct.unpack_from(">2H", data, at + 0x20)
    yn1, yn2 = struct.unpack_from(">2h", data, at + 0x24)
    loop_pred_scale = struct.unpack_from(">H", data, at + 0x28)[0]
    loop_yn1, loop_yn2 = struct.unpack_from(">2h", data, at + 0x2A)
    return dsp_adpcm.AdpcmInfo(coefficients, gain, pred_scale, yn1, yn2,
                               loop_pred_scale, loop_yn1, loop_yn2)


def _nibbles_to_samples(nibbles: int) -> int:
    frames, remainder = divmod(nibbles, 16)
    samples = frames * 14 + remainder - 2
    if samples < 0:
        raise RwsdError("Invalid RWSD ADPCM nibble count")
    return samples


def read_rwsd(header: bytes, wave_data: bytes) -> RwsdFile:
    """Parse an RWSD whose header and audio payload came from an RSAR group."""
    if len(header) < 0x20 or header[:4] != b"RWSD":
        raise RwsdError("Not an RWSD file (missing RWSD header)")
    bom, version, file_size, header_size, section_count = struct.unpack_from(">HHIHH", header, 4)
    if bom != 0xFEFF or version not in (0x0100, 0x0101, 0x0102):
        raise RwsdError("Unsupported RWSD byte order or version")
    if file_size != len(header) or header_size < 0x20 or section_count != 2:
        raise RwsdError("Invalid RWSD common header")
    data_offset, data_size, wave_offset, wave_size = struct.unpack_from(">4I", header, 0x10)
    for magic, offset, size in ((b"DATA", data_offset, data_size), (b"WAVE", wave_offset, wave_size)):
        if offset < header_size or size < 12 or offset + size > len(header):
            raise RwsdError(f"RWSD {magic.decode()} section lies outside the header")
        if header[offset:offset + 4] != magic or _u32(header, offset + 4, magic.decode()) != size:
            raise RwsdError(f"Invalid RWSD {magic.decode()} section")

    # All DATA ruint offsets are relative to the list beginning at DATA + 8.
    data_base = data_offset + 8
    entry_offsets = _reference_list(header, data_base, data_base, "DATA entry")
    entries = []
    for entry_at in entry_offsets:
        if entry_at + 0x18 > data_offset + data_size:
            raise RwsdError("Truncated RWSD DATA entry")
        wsd_at = _reference(header, entry_at, data_base, "WSD info")
        note_table_at = _reference(header, entry_at + 0x10, data_base, "note table")
        if wsd_at + 0x20 > data_offset + data_size:
            raise RwsdError("Truncated RWSD WSD info")
        notes = _reference_list(header, note_table_at, data_base, "note")
        if not notes or notes[0] + 0x30 > data_offset + data_size:
            raise RwsdError("RWSD entry has no complete note info")
        note_at = notes[0]
        wave_index = _u32(header, note_at, "wave index")
        pitch = struct.unpack_from(">f", header, wsd_at)[0]
        note_pitch = struct.unpack_from(">f", header, note_at + 0x10)[0]
        if not 0.01 <= pitch <= 100.0 or not 0.01 <= note_pitch <= 100.0:
            raise RwsdError("RWSD entry has an invalid pitch")
        entries.append(RwsdEntry(wave_index, pitch, header[wsd_at + 4],
                                 header[note_at + 9], note_pitch))

    wave_count = _u32(header, wave_offset + 8, "WAVE count")
    if wave_count > (wave_size - 12) // 4:
        raise RwsdError("Truncated RWSD WAVE offset table")
    waves = []
    for index in range(wave_count):
        wave_at = wave_offset + _u32(header, wave_offset + 12 + index * 4, "wave offset")
        if wave_at < wave_offset + 12 or wave_at + 0x1C > wave_offset + wave_size:
            raise RwsdError("RWSD wave info lies outside WAVE")
        encoding, looped, channel_count, rate_high = struct.unpack_from(">4B", header, wave_at)
        sample_rate = rate_high << 16 | struct.unpack_from(">H", header, wave_at + 4)[0]
        loop_value, sample_value, table_offset, audio_offset = struct.unpack_from(">4I", header, wave_at + 8)
        if encoding not in (0, 1, 2) or channel_count not in (1, 2) or not sample_rate:
            raise RwsdError("Unsupported RWSD wave format")
        sample_count = _nibbles_to_samples(sample_value) if encoding == 2 else sample_value
        loop_start = (_nibbles_to_samples(loop_value) if encoding == 2 else loop_value) if looped else None
        if sample_count <= 0 or (loop_start is not None and not 0 <= loop_start < sample_count):
            raise RwsdError("Invalid RWSD wave sample geometry")
        table_at = wave_at + table_offset
        if table_at < wave_at + 0x1C or table_at + channel_count * 4 > wave_offset + wave_size:
            raise RwsdError("RWSD channel table lies outside WAVE")
        channels = []
        for channel_index in range(channel_count):
            channel_at = wave_at + _u32(header, table_at + channel_index * 4, "channel offset")
            if channel_at < wave_at or channel_at + 0x1C > wave_offset + wave_size:
                raise RwsdError("RWSD channel info lies outside WAVE")
            channel_data, adpcm_offset = struct.unpack_from(">2I", header, channel_at)
            adpcm = _adpcm_info(header, wave_at + adpcm_offset) if encoding == 2 else None
            channels.append(RwsdChannel(channel_data, adpcm))
        byte_count = ((sample_value + 1) // 2 if encoding == 2 else
                      sample_count * (1 if encoding == 0 else 2))
        if any(audio_offset + channel.data_offset + byte_count > len(wave_data) for channel in channels):
            raise RwsdError("RWSD sample data lies outside its RSAR group")
        waves.append(RwsdWave(encoding, sample_rate, loop_start, sample_count,
                              audio_offset, tuple(channels)))

    if any(entry.wave_index >= len(waves) for entry in entries):
        raise RwsdError("RWSD DATA entry refers to a missing wave")
    return RwsdFile(tuple(entries), tuple(waves), bytes(header), bytes(wave_data))


def decode_wave(document: RwsdFile, wave_index: int) -> RwsdAudio:
    """Decode one WAVE entry to signed 16-bit PCM channels."""
    if not 0 <= wave_index < len(document.waves):
        raise RwsdError(f"RWSD wave index {wave_index} is out of range")
    wave = document.waves[wave_index]
    channels = []
    for channel in wave.channels:
        start = wave.data_offset + channel.data_offset
        if wave.encoding == 2:
            assert channel.adpcm_info is not None
            size = dsp_adpcm.bytes_for_adpcm_samples(wave.sample_count)
            decoded = dsp_adpcm.decode(document.wave_data[start:start + size], channel.adpcm_info,
                                       wave.sample_count)
        elif wave.encoding == 1:
            decoded = list(struct.unpack_from(f">{wave.sample_count}h", document.wave_data, start))
        else:
            raw = document.wave_data[start:start + wave.sample_count]
            decoded = [struct.unpack("b", bytes((sample,)))[0] << 8 for sample in raw]
        channels.append(tuple(decoded))
    return RwsdAudio(wave.sample_rate, tuple(channels), wave.loop_start)


def render_entry(document: RwsdFile, entry_index: int, *, max_seconds: float = 120.0,
                 loop_count: int = 2) -> RwsdAudio:
    """Render an RWSD sound entry, limiting previews to ``max_seconds``.

    Looping waves include the initial pass plus ``loop_count`` repetitions of
    their loop region.  Pitch metadata is represented by the output rate, so
    no lossy resampling is needed for preview.
    """
    if not 0 <= entry_index < len(document.entries):
        raise RwsdError(f"RWSD sound index {entry_index} is out of range")
    if max_seconds <= 0 or loop_count < 0:
        raise RwsdError("Invalid RWSD preview limit")
    entry = document.entries[entry_index]
    audio = decode_wave(document, entry.wave_index)
    rate = max(1, round(audio.sample_rate * entry.pitch * entry.note_pitch))
    limit = max(1, round(rate * max_seconds))
    rendered = []
    for channel in audio.channels:
        samples = list(channel)
        if audio.loop_start is not None and loop_count:
            samples += list(channel[audio.loop_start:]) * loop_count
        rendered.append(tuple(samples[:limit]))
    return RwsdAudio(rate, tuple(rendered), audio.loop_start)


def replace_wave(document: RwsdFile, wave_index: int, audio: RwsdAudio) -> tuple[bytes, bytes]:
    """Replace one RWSD wave and rebuild its detached sample payload.

    Channel count must match the template because channel-info records live in
    the fixed-size header.  Every wave's data location is rewritten, allowing
    the replacement duration to grow or shrink without overwriting neighbours.
    """
    if not 0 <= wave_index < len(document.waves):
        raise RwsdError("RWSD wave index is out of range")
    old = document.waves[wave_index]
    if len(audio.channels) != len(old.channels) or len(audio.channels) not in (1, 2):
        raise RwsdError("Replacement audio must match the RWSD wave's channel count")
    sample_count = len(audio.channels[0]) if audio.channels else 0
    if sample_count <= 0 or any(len(channel) != sample_count for channel in audio.channels):
        raise RwsdError("Replacement channels must have the same non-zero length")
    if not 1 <= audio.sample_rate <= 0xFFFFFF:
        raise RwsdError("RWSD sample rate is out of range")
    if audio.loop_start is not None and not 0 <= audio.loop_start < sample_count:
        raise RwsdError("RWSD loop start is outside the replacement")
    if audio == decode_wave(document, wave_index):
        return document.header, document.wave_data

    header = bytearray(document.header)
    wave_section = struct.unpack_from(">I", header, 0x18)[0]
    encoded_replacement = []
    replacement_info = []
    for channel in audio.channels:
        info = dsp_adpcm.AdpcmInfo()
        encoded = dsp_adpcm.encode(list(channel), info)
        if audio.loop_start is not None:
            dsp_adpcm.get_loop_context(encoded, info, audio.loop_start)
        encoded_replacement.append(encoded)
        replacement_info.append(info)

    payload = bytearray()
    for index, wave in enumerate(document.waves):
        payload += bytes(-len(payload) % 0x20)
        wave_at = wave_section + _u32(header, wave_section + 12 + index * 4, "wave offset")
        struct.pack_into(">I", header, wave_at + 0x14, len(payload))
        if index == wave_index:
            header[wave_at:wave_at + 4] = bytes((2, int(audio.loop_start is not None),
                                                 len(audio.channels), (audio.sample_rate >> 16) & 0xFF))
            struct.pack_into(">H", header, wave_at + 4, audio.sample_rate & 0xFFFF)
            loop_nibbles = dsp_adpcm.get_nibble_address(audio.loop_start) if audio.loop_start is not None else 0
            # WaveInfo stores an address in the DSP nibble stream, including
            # the two header nibbles of the current frame (not merely a count
            # of encoded payload nibbles).
            total_nibbles = dsp_adpcm.get_nibble_address(sample_count)
            struct.pack_into(">2I", header, wave_at + 8, loop_nibbles, total_nibbles)
            table_offset = _u32(header, wave_at + 0x10, "channel table offset")
            for channel_index, (encoded, info) in enumerate(zip(encoded_replacement, replacement_info)):
                payload += bytes(-len(payload) % 0x20)
                channel_relative = len(payload) - struct.unpack_from(">I", header, wave_at + 0x14)[0]
                channel_at = wave_at + _u32(header, wave_at + table_offset + channel_index * 4,
                                            "channel offset")
                struct.pack_into(">I", header, channel_at, channel_relative)
                adpcm_at = wave_at + _u32(header, channel_at + 4, "ADPCM offset")
                struct.pack_into(">16h2H2hH2h", header, adpcm_at, *info.coef, info.gain,
                                 info.pred_scale, info.yn1, info.yn2, info.loop_pred_scale,
                                 info.loop_yn1, info.loop_yn2)
                payload += encoded
                payload += bytes(max(0, (total_nibbles + 1) // 2 - len(encoded)))
        else:
            bytes_per_channel = (dsp_adpcm.bytes_for_adpcm_samples(wave.sample_count) if wave.encoding == 2 else
                                 wave.sample_count * (1 if wave.encoding == 0 else 2))
            old_base = wave.data_offset
            table_offset = _u32(header, wave_at + 0x10, "channel table offset")
            new_base = len(payload)
            for channel_index, channel in enumerate(wave.channels):
                payload += bytes(-len(payload) % 0x20)
                channel_at = wave_at + _u32(header, wave_at + table_offset + channel_index * 4,
                                            "channel offset")
                struct.pack_into(">I", header, channel_at, len(payload) - new_base)
                start = old_base + channel.data_offset
                payload += document.wave_data[start:start + bytes_per_channel]
    rebuilt = read_rwsd(bytes(header), bytes(payload))
    check = decode_wave(rebuilt, wave_index)
    if (check.sample_rate != audio.sample_rate or check.loop_start != audio.loop_start or
            len(check.channels) != len(audio.channels) or
            any(len(channel) != sample_count for channel in check.channels)):
        raise RwsdError("Rebuilt RWSD replacement did not validate")
    return bytes(header), bytes(payload)


# -- a new one-entry RWSD ---------------------------------------------------------------------
#
# DATA (after its 8-byte header, every reference relative to that point): a count and references
# to the entries. An entry (0x18) references its wave sound info (0x20: pitch, pan, sends, then
# envelope and randomizer references), its track table (count, references to 8-byte track infos,
# each referencing a table of 0x10-byte note events: position, length, note index) and its note
# table (count, references to 0x30-byte note infos: wave index, ADSR, key, volume, pan, pitch,
# then LFO, envelope and randomizer references). WAVE: a count, offsets from WAVE's start to each
# wave info (0x1C, then its channel table, channel infos and DSP-ADPCM states).

_REF = 0x01000000


def _wave_block(header: bytes, wave_at: int) -> bytes:
    """A wave info with everything it points at (offsets inside it are relative to ``wave_at``)."""
    channel_count = header[wave_at + 2]
    table_at = wave_at + _u32(header, wave_at + 0x10, "channel table offset")
    end = table_at + 4 * channel_count
    for index in range(channel_count):
        channel_at = wave_at + _u32(header, table_at + 4 * index, "channel offset")
        end = max(end, channel_at + 0x1C, wave_at + _u32(header, channel_at + 4, "ADPCM offset") + 0x30)
    return header[wave_at:end]


def single_entry_rwsd(document: RwsdFile, entry_index: int) -> tuple[bytes, bytes]:
    """An RWSD holding only ``document``'s entry ``entry_index``: its wave sound info, its first
    track with its first note event, its first note (pointing at wave 0) and a copy of its wave.
    Envelope, randomizer and LFO references are left out (null). Replace the wave's audio with
    :func:`replace_wave`."""
    header = document.header
    if not 0 <= entry_index < len(document.entries):
        raise RwsdError("RWSD entry index is out of range")
    data_offset, _data_size, wave_offset, _wave_size = struct.unpack_from(">4I", header, 0x10)
    base = data_offset + 8
    entry_at = _reference_list(header, base, base, "DATA entry")[entry_index]
    wsd_at = _reference(header, entry_at, base, "WSD info")
    track_at = _reference_list(header, _reference(header, entry_at + 8, base, "track table"), base, "track")[0]
    event_at = _reference_list(header, _reference(header, track_at, base, "event table"), base, "event")[0]
    note_at = _reference_list(header, _reference(header, entry_at + 0x10, base, "note table"), base, "note")[0]
    wave_index = _u32(header, note_at, "wave index")

    body = bytearray()

    def put(raw: bytes) -> int:
        at = len(body)
        body.extend(raw)
        return at

    def ref(at: int) -> bytes:
        return struct.pack(">2I", _REF, at)

    put(bytes(4 + 8))                           # the entry list, filled below
    entry_rel = put(bytes(0x18))
    wsd = bytearray(header[wsd_at:wsd_at + 0x20])
    wsd[0x0C:0x1C] = bytes(0x10)                 # no envelope, no randomizer
    wsd_rel = put(wsd)
    track_table_rel = put(struct.pack(">I", 1) + bytes(8))
    track_rel = put(bytes(8))
    event_table_rel = put(struct.pack(">I", 1) + bytes(8))
    event = bytearray(header[event_at:event_at + 0x10])
    struct.pack_into(">I", event, 8, 0)          # the first (only) note
    event_rel = put(event)
    note_table_rel = put(struct.pack(">I", 1) + bytes(8))
    note = bytearray(header[note_at:note_at + 0x30])
    struct.pack_into(">I", note, 0, 0)           # wave 0
    note[0x14:0x2C] = bytes(0x18)                # no LFO, envelope or randomizer
    note_rel = put(note)
    struct.pack_into(">I", body, 0, 1)
    body[4:12] = ref(entry_rel)
    body[entry_rel:entry_rel + 0x18] = ref(wsd_rel) + ref(track_table_rel) + ref(note_table_rel)
    body[track_table_rel + 4:track_table_rel + 12] = ref(track_rel)
    body[track_rel:track_rel + 8] = ref(event_table_rel)
    body[event_table_rel + 4:event_table_rel + 12] = ref(event_rel)
    body[note_table_rel + 4:note_table_rel + 12] = ref(note_rel)
    data = bytearray(b"DATA" + bytes(4)) + body
    data += bytes(-len(data) % 0x20)
    struct.pack_into(">I", data, 4, len(data))

    wave_at = wave_offset + _u32(header, wave_offset + 12 + 4 * wave_index, "wave offset")
    block = bytearray(_wave_block(header, wave_at))
    template = document.waves[wave_index]
    stored = _u32(block, 0x0C, "sample count")  # nibbles for DSP-ADPCM, as read_rwsd measures it
    bytes_per_channel = ((stored + 1) // 2 if template.encoding == 2 else
                         template.sample_count * (1 if template.encoding == 0 else 2))
    payload = bytearray()
    struct.pack_into(">I", block, 0x14, 0)
    table_offset = _u32(block, 0x10, "channel table offset")
    for index, channel in enumerate(template.channels):
        payload += bytes(-len(payload) % 0x20)
        channel_at = _u32(block, table_offset + 4 * index, "channel offset")
        struct.pack_into(">I", block, channel_at, len(payload))
        start = template.data_offset + channel.data_offset
        payload += document.wave_data[start:start + bytes_per_channel]
    wave = bytearray(b"WAVE" + bytes(4)) + struct.pack(">II", 1, 0x10) + block  # the block at WAVE + 0x10
    wave += bytes(-len(wave) % 0x20)
    struct.pack_into(">I", wave, 4, len(wave))

    out = bytearray(0x20)
    out[0:4] = b"RWSD"
    struct.pack_into(">HHIHH", out, 4, 0xFEFF, struct.unpack_from(">H", header, 6)[0], 0, 0x20, 2)
    struct.pack_into(">4I", out, 0x10, 0x20, len(data), 0x20 + len(data), len(wave))
    out += data + wave
    struct.pack_into(">I", out, 8, len(out))
    built = read_rwsd(bytes(out), bytes(payload))
    if len(built.entries) != 1 or decode_wave(built, 0) != decode_wave(document, wave_index):
        raise RwsdError("The new RWSD did not validate")
    return bytes(out), bytes(payload)
