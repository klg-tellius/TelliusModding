"""Bounded preview renderer for Nintendo Wii ``RSEQ`` sequences.

The game executes an MML bytecode stream and uses an ``RBNK`` instrument
bank.  This renderer follows the musical/control commands used by Radiant
Dawn, resolves notes through the bank's range tables, and deliberately caps
branches, loops, operations and duration so malformed data cannot hang the
editor.  Effects and controller automation are approximated.
"""

from __future__ import annotations

import heapq
import math
import struct
from dataclasses import dataclass, field

import numpy as np

from . import rbnk


class RseqError(ValueError):
    pass


@dataclass(frozen=True)
class RseqFile:
    commands: bytes
    labels: tuple[tuple[int, str], ...]
    source: bytes


@dataclass(frozen=True)
class SequenceNote:
    tick: int
    duration: int
    key: int
    velocity: int
    program: int
    volume: int
    pan: int


@dataclass(order=True)
class _Track:
    tick: int
    number: int
    pc: int = field(compare=False)
    program: int = field(default=0, compare=False)
    volume: int = field(default=127, compare=False)
    pan: int = field(default=64, compare=False)
    transpose: int = field(default=0, compare=False)
    note_wait: bool = field(default=True, compare=False)
    call_stack: list[int] = field(default_factory=list, compare=False)
    loops: list[tuple[int, int]] = field(default_factory=list, compare=False)
    jumps: dict[int, int] = field(default_factory=dict, compare=False)


U8_COMMANDS = set(range(0xB0, 0xE0))
S16_COMMANDS = {0xE0, 0xE1, 0xE3}


def read_rseq(data: bytes) -> RseqFile:
    if len(data) < 0x20 or data[:4] != b"RSEQ":
        raise RseqError("Not an RSEQ file (missing RSEQ header)")
    bom, version, file_size, header_size, sections = struct.unpack_from(">HHIHH", data, 4)
    if bom != 0xFEFF or version not in (0x0100, 0x0101) or file_size != len(data):
        raise RseqError("Invalid RSEQ common header")
    if header_size < 0x20 or sections != 2:
        raise RseqError("Unsupported RSEQ section layout")
    data_offset, data_size, label_offset, label_size = struct.unpack_from(">4I", data, 0x10)
    for magic, offset, size in ((b"DATA", data_offset, data_size), (b"LABL", label_offset, label_size)):
        if offset < header_size or size < 12 or offset + size > len(data):
            raise RseqError(f"RSEQ {magic.decode()} section lies outside the file")
        if data[offset:offset + 4] != magic or struct.unpack_from(">I", data, offset + 4)[0] != size:
            raise RseqError(f"Invalid RSEQ {magic.decode()} section")
    base_offset = struct.unpack_from(">I", data, data_offset + 8)[0]
    command_at = data_offset + base_offset
    if not data_offset + 12 <= command_at <= data_offset + data_size:
        raise RseqError("RSEQ command stream lies outside DATA")
    commands = data[command_at:data_offset + data_size]

    count = struct.unpack_from(">I", data, label_offset + 8)[0]
    if count > (label_size - 12) // 4:
        raise RseqError("Truncated RSEQ label table")
    label_base = label_offset + 8
    labels = []
    for index in range(count):
        at = label_base + struct.unpack_from(">I", data, label_offset + 12 + index * 4)[0]
        if at < label_offset or at + 8 > label_offset + label_size:
            raise RseqError("RSEQ label lies outside LABL")
        command_id, length = struct.unpack_from(">2I", data, at)
        if at + 8 + length > label_offset + label_size:
            raise RseqError("Truncated RSEQ label")
        labels.append((command_id, data[at + 8:at + 8 + length].decode("shift_jis", "replace")))
    return RseqFile(commands, tuple(labels), bytes(data))


def _byte(commands: bytes, track: _Track) -> int:
    if not 0 <= track.pc < len(commands):
        raise RseqError("RSEQ command runs past DATA")
    value = commands[track.pc]
    track.pc += 1
    return value


def _u24(commands: bytes, track: _Track) -> int:
    return (_byte(commands, track) << 16) | (_byte(commands, track) << 8) | _byte(commands, track)


def _varint(commands: bytes, track: _Track) -> int:
    value = 0
    for _ in range(5):
        current = _byte(commands, track)
        value = value << 7 | current & 0x7F
        if current < 0x80:
            return value
    raise RseqError("RSEQ variable-length integer is too long")


def _apply(track: _Track, command: int, value: int) -> None:
    if command == 0x81:
        track.program = max(0, value)
    elif command == 0xC0:
        track.pan = max(0, min(127, value))
    elif command in (0xC1, 0xC2, 0xD5):
        track.volume = max(0, min(127, value))
    elif command == 0xC3:
        track.transpose = max(-127, min(127, value))
    elif command == 0xC7:
        track.note_wait = bool(value)


def collect_notes(sequence: RseqFile, start_offset: int = 0, *, max_ticks: int = 120 * 192,
                  max_operations: int = 200_000, loop_count: int = 2) -> tuple[list[SequenceNote], int, int]:
    """Return notes plus the sequence timebase and tempo."""
    if not 0 <= start_offset < len(sequence.commands):
        raise RseqError("RSEQ start offset is outside DATA")
    queue = [_Track(0, 0, start_offset)]
    notes: list[SequenceNote] = []
    timebase, tempo = 48, 120
    operations = 0
    next_track_number = 1
    while queue:
        track = heapq.heappop(queue)
        while track.tick <= max_ticks:
            operations += 1
            if operations > max_operations:
                raise RseqError("RSEQ preview exceeded its command limit")
            command = _byte(sequence.commands, track)
            if command <= 0x7F:
                velocity = _byte(sequence.commands, track)
                duration = _varint(sequence.commands, track)
                notes.append(SequenceNote(track.tick, duration, max(0, min(127, command + track.transpose)),
                                          velocity, track.program, track.volume, track.pan))
                if track.note_wait:
                    track.tick += duration
                continue
            if command == 0x80:
                track.tick += _varint(sequence.commands, track)
                continue
            if command == 0x81:
                _apply(track, command, _varint(sequence.commands, track))
                continue
            if command == 0x88:
                _track_id = _byte(sequence.commands, track)
                target = _u24(sequence.commands, track)
                if target < len(sequence.commands):
                    heapq.heappush(queue, _Track(track.tick, next_track_number, target))
                    next_track_number += 1
                continue
            if command in (0x89, 0x8A):
                target = _u24(sequence.commands, track)
                if command == 0x8A:
                    track.call_stack.append(track.pc)
                visits = track.jumps.get(target, 0)
                if target >= len(sequence.commands) or visits >= loop_count:
                    break
                track.jumps[target] = visits + 1
                track.pc = target
                continue
            if command in (0xA0, 0xA4):
                wrapped = _byte(sequence.commands, track)
                low = struct.unpack(">h", bytes((_byte(sequence.commands, track), _byte(sequence.commands, track))))[0]
                high = struct.unpack(">h", bytes((_byte(sequence.commands, track), _byte(sequence.commands, track))))[0]
                _apply(track, wrapped, (low + high) // 2)
                continue
            if command in (0xA1, 0xA2, 0xA3, 0xA5):
                _wrapped = _byte(sequence.commands, track)
                _argument = _byte(sequence.commands, track)
                continue
            if command in U8_COMMANDS:
                value = _byte(sequence.commands, track)
                _apply(track, command, value if command != 0xC3 or value < 128 else value - 256)
                if command == 0xB0 and value:
                    timebase = value
                elif command == 0xD4:
                    track.loops.append((track.pc, value or loop_count))
                continue
            if command in S16_COMMANDS:
                value = struct.unpack(">h", bytes((_byte(sequence.commands, track), _byte(sequence.commands, track))))[0]
                if command == 0xE1 and value > 0:
                    tempo = value
                continue
            if command == 0xF0:
                _extended = _byte(sequence.commands, track)
                _variable = _byte(sequence.commands, track)
                _value = (_byte(sequence.commands, track) << 8) | _byte(sequence.commands, track)
                continue
            if command == 0xFB:
                continue
            if command == 0xFC:
                if track.loops:
                    target, remaining = track.loops[-1]
                    if remaining > 1:
                        track.loops[-1] = (target, remaining - 1)
                        track.pc = target
                    else:
                        track.loops.pop()
                continue
            if command == 0xFD:
                if track.call_stack:
                    track.pc = track.call_stack.pop()
                    continue
                break
            if command == 0xFE:
                _mask = (_byte(sequence.commands, track) << 8) | _byte(sequence.commands, track)
                continue
            if command == 0xFF:
                break
            raise RseqError(f"Unsupported RSEQ command {command:#04x}")
    return notes, timebase, tempo


def render_sequence(sequence: RseqFile, bank: rbnk.RbnkFile, start_offset: int = 0, *,
                    sample_rate: int = 32000, max_seconds: float = 120.0,
                    loop_count: int = 2) -> tuple[int, np.ndarray]:
    """Render a bounded mono preview of an RSEQ/RBNK pair."""
    max_ticks = max(1, math.ceil(max_seconds * 120 * 48 / 60))
    notes, timebase, tempo = collect_notes(sequence, start_offset, max_ticks=max_ticks,
                                           loop_count=loop_count)
    seconds_per_tick = 60.0 / max(1, tempo * timebase)
    limit = max(1, round(sample_rate * max_seconds))
    mix = np.zeros(limit, dtype=np.float64)
    last_audio_end = 1
    decoded_waves: dict[int, object] = {}
    for note in notes:
        instrument = rbnk.instrument(bank, note.program, note.key, note.velocity)
        if instrument is None:
            continue
        source = decoded_waves.get(instrument.wave_index)
        if source is None:
            source = rbnk.decode_instrument(bank, instrument)
            decoded_waves[instrument.wave_index] = source
        mono = np.mean(np.asarray(source.channels, dtype=np.float64), axis=0)
        pitch = instrument.pitch * 2.0 ** ((note.key - instrument.original_key) / 12.0)
        step = source.sample_rate * pitch / sample_rate
        if not math.isfinite(step) or step <= 0:
            continue
        wanted = (round(note.duration * seconds_per_tick * sample_rate) if note.duration else
                  max(1, math.ceil(len(mono) / step)))
        wanted = min(wanted, limit)
        positions = np.arange(wanted, dtype=np.float64) * step
        if source.loop_start is not None and len(mono) > source.loop_start:
            loop_length = len(mono) - source.loop_start
            positions = np.where(positions < len(mono), positions,
                                 source.loop_start + (positions - source.loop_start) % loop_length)
        else:
            wanted = min(wanted, max(0, math.ceil(len(mono) / step)))
            positions = positions[:wanted]
        rendered = np.interp(positions, np.arange(len(mono)), mono)
        gain = note.velocity / 127.0 * note.volume / 127.0 * instrument.volume / 127.0
        start = round(note.tick * seconds_per_tick * sample_rate)
        end = min(limit, start + len(rendered))
        if start < limit and end > start:
            mix[start:end] += rendered[:end - start] * gain
            last_audio_end = max(last_audio_end, end)
    if not notes:
        raise RseqError("RSEQ produced no notes")
    last = min(limit, last_audio_end)
    peak = float(np.max(np.abs(mix[:last]))) if last else 0.0
    if peak > 32767:
        mix *= 32767.0 / peak
    return sample_rate, np.asarray(np.rint(mix[:last]), dtype=np.int16)
