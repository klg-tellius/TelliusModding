"""Nintendo Wii ``RBNK`` sequence instrument banks embedded in BRSAR."""

from __future__ import annotations

import struct
from dataclasses import dataclass

from . import dsp_adpcm, rwsd


class RbnkError(ValueError):
    pass


@dataclass(frozen=True)
class RbnkInstrument:
    wave_index: int
    attack: int
    decay: int
    sustain: int
    release: int
    hold: int
    original_key: int
    volume: int
    pan: int
    pitch: float


@dataclass(frozen=True)
class _Node:
    kind: int
    at: int | None


@dataclass(frozen=True)
class RbnkFile:
    programs: tuple[_Node, ...]
    waves: tuple[rwsd.RwsdWave, ...]
    header: bytes
    wave_data: bytes
    data_base: int


def _u32(data: bytes, at: int, label: str) -> int:
    if at < 0 or at + 4 > len(data):
        raise RbnkError(f"Truncated RBNK {label}")
    return struct.unpack_from(">I", data, at)[0]


def _node(data: bytes, at: int, base: int) -> _Node:
    if at < 0 or at + 8 > len(data):
        raise RbnkError("Truncated RBNK reference")
    control, offset = struct.unpack_from(">2I", data, at)
    kind = (control >> 16) & 0xFF
    if kind in (0, 4):
        return _Node(kind, None)
    target = base + offset
    if not 0 <= target < len(data):
        raise RbnkError("RBNK reference lies outside the header")
    return _Node(kind, target)


def _parse_wave(header: bytes, wave_data: bytes, wave_at: int, section_start: int,
                section_end: int) -> rwsd.RwsdWave:
    if wave_at < section_start or wave_at + 0x1C > section_end:
        raise RbnkError("RBNK wave info lies outside WAVE")
    encoding, looped, channel_count, rate_high = struct.unpack_from(">4B", header, wave_at)
    rate = rate_high << 16 | struct.unpack_from(">H", header, wave_at + 4)[0]
    loop_value, sample_value, table_offset, audio_offset = struct.unpack_from(">4I", header, wave_at + 8)
    if encoding not in (0, 1, 2) or channel_count not in (1, 2) or not rate:
        raise RbnkError("Unsupported RBNK wave format")
    if encoding == 2:
        sample_count = sample_value // 16 * 14 + sample_value % 16 - 2
        loop_start = loop_value // 16 * 14 + loop_value % 16 - 2 if looped else None
        byte_count = (sample_value + 1) // 2
    else:
        sample_count = sample_value
        loop_start = loop_value if looped else None
        byte_count = sample_count * (1 if encoding == 0 else 2)
    if sample_count <= 0 or (loop_start is not None and not 0 <= loop_start < sample_count):
        raise RbnkError("Invalid RBNK wave sample geometry")
    table_at = wave_at + table_offset
    if table_at < wave_at + 0x1C or table_at + channel_count * 4 > section_end:
        raise RbnkError("RBNK channel table lies outside WAVE")
    channels = []
    for index in range(channel_count):
        channel_at = wave_at + _u32(header, table_at + index * 4, "channel offset")
        if channel_at < wave_at or channel_at + 0x1C > section_end:
            raise RbnkError("RBNK channel info lies outside WAVE")
        data_offset, adpcm_offset = struct.unpack_from(">2I", header, channel_at)
        adpcm = None
        if encoding == 2:
            adpcm_at = wave_at + adpcm_offset
            if adpcm_at < wave_at or adpcm_at + 0x30 > section_end:
                raise RbnkError("Truncated RBNK DSP-ADPCM state")
            coef = list(struct.unpack_from(">16h", header, adpcm_at))
            gain, ps = struct.unpack_from(">2H", header, adpcm_at + 0x20)
            yn1, yn2 = struct.unpack_from(">2h", header, adpcm_at + 0x24)
            lps = struct.unpack_from(">H", header, adpcm_at + 0x28)[0]
            lyn1, lyn2 = struct.unpack_from(">2h", header, adpcm_at + 0x2A)
            adpcm = dsp_adpcm.AdpcmInfo(coef, gain, ps, yn1, yn2, lps, lyn1, lyn2)
        if audio_offset + data_offset + byte_count > len(wave_data):
            raise RbnkError("RBNK sample data lies outside its RSAR group")
        channels.append(rwsd.RwsdChannel(data_offset, adpcm))
    return rwsd.RwsdWave(encoding, rate, loop_start, sample_count, audio_offset, tuple(channels))


def read_rbnk(header: bytes, wave_data: bytes) -> RbnkFile:
    if len(header) < 0x20 or header[:4] != b"RBNK":
        raise RbnkError("Not an RBNK file (missing RBNK header)")
    bom, version, file_size, header_size, sections = struct.unpack_from(">HHIHH", header, 4)
    if bom != 0xFEFF or version not in (0x0100, 0x0101, 0x0102) or file_size != len(header):
        raise RbnkError("Invalid RBNK common header")
    if header_size < 0x20 or sections != 2:
        raise RbnkError("Unsupported RBNK section layout")
    data_offset, data_size, wave_offset, wave_size = struct.unpack_from(">4I", header, 0x10)
    for magic, offset, size in ((b"DATA", data_offset, data_size), (b"WAVE", wave_offset, wave_size)):
        if offset < header_size or size < 12 or offset + size > len(header):
            raise RbnkError(f"RBNK {magic.decode()} section lies outside the header")
        if header[offset:offset + 4] != magic or _u32(header, offset + 4, magic.decode()) != size:
            raise RbnkError(f"Invalid RBNK {magic.decode()} section")

    data_base = data_offset + 8
    program_count = _u32(header, data_base, "program count")
    if program_count > (data_size - 12) // 8:
        raise RbnkError("Truncated RBNK program table")
    programs = tuple(_node(header, data_base + 4 + index * 8, data_base)
                     for index in range(program_count))

    wave_base = wave_offset + 8
    wave_count = _u32(header, wave_base, "wave count")
    if wave_count > (wave_size - 12) // 8:
        raise RbnkError("Truncated RBNK wave table")
    waves = []
    for index in range(wave_count):
        control, relative = struct.unpack_from(">2I", header, wave_base + 4 + index * 8)
        if not control:
            raise RbnkError("RBNK wave table contains a null entry")
        target = wave_base + relative
        waves.append(_parse_wave(header, wave_data, target, wave_offset, wave_offset + wave_size))
    return RbnkFile(programs, tuple(waves), bytes(header), bytes(wave_data), data_base)


def _instrument_at(bank: RbnkFile, node: _Node, selectors: tuple[int, ...]) -> RbnkInstrument | None:
    if node.kind in (0, 4) or node.at is None:
        return None
    data = bank.header
    if node.kind == 1:
        at = node.at
        if at + 0x30 > len(data):
            raise RbnkError("Truncated RBNK instrument")
        wave_index = _u32(data, at, "instrument wave index")
        if wave_index >= len(bank.waves):
            raise RbnkError("RBNK instrument refers to a missing wave")
        attack, decay, sustain, release, hold = struct.unpack_from(">5B", data, at + 4)
        original_key, volume, pan = struct.unpack_from(">3B", data, at + 12)
        pitch = struct.unpack_from(">f", data, at + 16)[0]
        if not 0.01 <= pitch <= 100.0:
            raise RbnkError("RBNK instrument has an invalid pitch")
        return RbnkInstrument(wave_index, attack, decay, sustain, release, hold,
                              original_key, volume, pan, pitch)
    selector = selectors[0] if selectors else 60
    remaining = selectors[1:] if selectors else ()
    if node.kind == 2:
        count = data[node.at]
        table_at = node.at + ((1 + count + 3) // 4 * 4)
        if not count or table_at + count * 8 > len(data):
            raise RbnkError("Truncated RBNK range table")
        keys = data[node.at + 1:node.at + 1 + count]
        chosen = next((index for index, upper in enumerate(keys) if selector <= upper), count - 1)
        return _instrument_at(bank, _node(data, table_at + chosen * 8, bank.data_base), remaining)
    if node.kind == 3:
        if node.at + 4 > len(data):
            raise RbnkError("Truncated RBNK index table")
        minimum, maximum = data[node.at], data[node.at + 1]
        if not minimum <= selector <= maximum:
            return None
        return _instrument_at(bank, _node(data, node.at + 4 + (selector - minimum) * 8,
                                           bank.data_base), remaining)
    raise RbnkError(f"Unsupported RBNK region type {node.kind}")


def instrument(bank: RbnkFile, program: int, key: int, velocity: int = 127) -> RbnkInstrument | None:
    if not 0 <= program < len(bank.programs) or not 0 <= key <= 127 or not 0 <= velocity <= 127:
        return None
    return _instrument_at(bank, bank.programs[program], (key, velocity))


def decode_instrument(bank: RbnkFile, value: RbnkInstrument) -> rwsd.RwsdAudio:
    document = rwsd.RwsdFile((), bank.waves, bank.header, bank.wave_data)
    return rwsd.decode_wave(document, value.wave_index)
