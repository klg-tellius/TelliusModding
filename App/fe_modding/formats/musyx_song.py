"""MusyX song data (``Sound/gcfesnd.slib``) and a small offline renderer.

``gcfesnd.slib`` is a chain of song blobs, one per ``gcfesnd.stbl`` entry
(104 of them): each starts with a ``u32`` blob size (the next blob follows
right after it) and seven ``0xFFFFFFFF``, then the song itself at +0x20. The
layout below comes from the public MusyX decompilation
(https://github.com/AxioDL/musyx, ``seq.h``/``seq.c``) and was confirmed on
this file. All values are big-endian and offsets are relative to the song
(blob + 0x20).

Song header (6 words): ``track_table, pattern_table, channel_table,
master_track, info, loop_point``. ``info`` is the tempo in BPM (the
``0x40000000`` flag says it is already scaled by 1024, ``0x80000000`` a
per-track section table, neither seen here). ``track_table`` is 64 offsets
(0 = unused track); ``channel_table`` 64 bytes, the MIDI channel of each track
(``0xFF`` = none); ``pattern_table`` the offsets of the patterns.

A track is a list of 12-byte entries ``u32 tick, u8 program_change (0xFF =
none), u8 volume (0xFF = none), 2 pad, u16 pattern, s8 transpose, s8
velocity_add``. Pattern ``0xFFFF`` ends the track, ``0xFFFE`` loops back to the
entry whose index is the u16 at +0xA.

A pattern is ``u32 header_len, u32 pitch_bend_offset, u32 modulation_offset``,
then (after ``header_len`` bytes counted from +4) its events: ``u16 delta_ticks,
u8 key, u8 velocity``. ``key & 0x80`` marks a 4-byte controller event (the
controller is ``velocity & 0x7F``, its value ``key & 0x7F``; controller 0
means program change); otherwise a 6-byte note follows with ``u16 length``.
``key == 0xFF and velocity == 0xFF`` ends the pattern, key and velocity both 0
are 4 bytes of padding.

``pitch_bend_offset`` and ``modulation_offset`` (0 = none; offsets from the
song start) point at delta streams (MusyX ``GetStreamValue``): each event is
a tick delta (1 byte, or 2 bytes with bit 15 set: 15 bits) then a value delta
(1 byte holding a signed 7-bit value, or 2 bytes with bit 15 set: signed 15
bits); ``80 00`` ends the stream. The value starts at ``0x2000`` (pitch bend,
centre) or 0 (modulation) when the pattern starts and the delta is added at
the event's tick. 151 patterns carry a pitch-bend stream, none a modulation
stream. The engine scales a bend by the voice's range (2 semitones unless its
macro sets one with command ``0x33``): ``semitones = range * (value - 0x2000) / 0x2000``.

Time: 384 ticks per beat. This is taken from Amuse/MusyX convention and
matches the data (controller sweeps step about every 12 ticks, ~12 ms at 150
BPM); the sequencer code itself only gives it indirectly.

The renderer is a mono approximation: a note plays its program's first
sample (from the song group's page table, see ``musyx.py``), repitched by
the note relative to the sample's base key, looped while held if the sample
loops, scaled by velocity and the channel's volume and expression
controllers and bent by the pattern's pitch-bend stream. Envelopes,
panning, reverb and multi-layer programs are ignored."""

from __future__ import annotations

import bisect
import struct
from dataclasses import dataclass, field

import numpy as np

from .musyx import Bank, MusyxError, SoundBanks

BLOB_HEADER_SIZE = 0x20
TRACK_COUNT = 64
TICKS_PER_BEAT = 384
OUTPUT_RATE = 32000
MAX_SECONDS = 60.0
RELEASE_SECONDS = 0.08
END_PATTERN = 0xFFFF
LOOP_PATTERN = 0xFFFE
CTL_PROGRAM = 0
CTL_VOLUME = 7
CTL_EXPRESSION = 11
PITCH_BEND_CENTRE = 0x2000
STREAM_END = b"\x80\x00"


class SongError(Exception):
    pass


@dataclass
class TrackEntry:
    tick: int
    program: int
    volume: int
    pattern: int
    transpose: int
    velocity_add: int
    loop_index: int  # u16 at +0xA, used by loop entries


@dataclass
class PatternEvent:
    tick: int  # relative to the pattern start
    kind: str  # "note" or "ctl"
    a: int  # note: key; ctl: controller number
    b: int  # note: velocity; ctl: value
    length: int = 0


class TempoMap:
    """Tick to seconds, for a constant tempo or a master track of (tick, BPM)
    changes."""

    def __init__(self, changes: list[tuple[int, int]]):
        self._ticks = [t for t, _ in changes]
        self._bpm = [b for _, b in changes]
        self._seconds = [0.0]
        for i in range(1, len(changes)):
            span = self._ticks[i] - self._ticks[i - 1]
            self._seconds.append(self._seconds[-1] + span * 60.0 / (self._bpm[i - 1] * TICKS_PER_BEAT))

    def seconds(self, tick: int) -> float:
        i = max(0, bisect.bisect_right(self._ticks, tick) - 1)
        return self._seconds[i] + (tick - self._ticks[i]) * 60.0 / (self._bpm[i] * TICKS_PER_BEAT)

    def sample(self, tick: int) -> int:
        return int(self.seconds(tick) * OUTPUT_RATE)


@dataclass
class Song:
    bpm: int
    loop_tick: int
    tempo: TempoMap = None  # type: ignore[assignment]
    tracks: dict[int, list[TrackEntry]] = field(default_factory=dict)
    patterns: list[list[PatternEvent]] = field(default_factory=list)
    channels: list[int] = field(default_factory=list)  # MIDI channel per track
    bends: list[list[tuple[int, int]]] = field(default_factory=list)  # per pattern: (tick, value)
    modulation: list[list[tuple[int, int]]] = field(default_factory=list)


def _stream_events(data: bytes, offset: int, limit: int) -> tuple[list[tuple[int, int]], int]:
    events = []
    while offset + 2 <= limit and data[offset:offset + 2] != STREAM_END:
        b1, b2 = data[offset], data[offset + 1]
        if b1 & 0x80:
            delta_tick, offset = ((b1 & 0x7F) << 8) | b2, offset + 2
        else:
            delta_tick, offset = b1, offset + 1
        b1 = data[offset]
        if b1 & 0x80:
            value = ((b1 & 0x7F) << 8) | data[offset + 1]
            value = value - 0x8000 if value & 0x4000 else value
            offset += 2
        else:
            value = b1 - 0x80 if b1 & 0x40 else b1
            offset += 1
        events.append((delta_tick, value))
    return events, offset + 2


def decode_stream(data: bytes, offset: int, limit: int) -> list[tuple[int, int]]:
    """(tick delta, value delta) events of a pitch-bend or modulation stream."""
    return _stream_events(data, offset, limit)[0]


def stream_size(data: bytes, offset: int, limit: int) -> int:
    """Bytes a stream takes, its ``80 00`` end included."""
    return _stream_events(data, offset, limit)[1] - offset


def stream_values(events: list[tuple[int, int]], start: int) -> list[tuple[int, int]]:
    """Absolute (tick, value) points from :func:`decode_stream` deltas."""
    tick, value, points = 0, start, []
    for delta_tick, delta_value in events:
        tick += delta_tick
        value += delta_value
        points.append((tick, value))
    return points


def split_slib(data: bytes) -> list[tuple[int, int]]:
    """(offset, size) of every song blob."""
    blobs = []
    offset = 0
    while offset + BLOB_HEADER_SIZE <= len(data):
        size = struct.unpack_from(">I", data, offset)[0]
        if size < BLOB_HEADER_SIZE or offset + size > len(data):
            break
        blobs.append((offset, size))
        offset += size
    return blobs


def _parse_pattern(data: bytes, offset: int, limit: int) -> list[PatternEvent]:
    header_len = struct.unpack_from(">I", data, offset)[0]
    position = offset + 4 + header_len
    tick = 0
    events: list[PatternEvent] = []
    while position + 4 <= limit:
        delta, key, velocity = struct.unpack_from(">HBB", data, position)
        if key == 0xFF and velocity == 0xFF:
            break
        tick += delta
        if key & 0x80:
            events.append(PatternEvent(tick, "ctl", velocity & 0x7F, key & 0x7F))
            position += 4
        elif key == 0 and velocity == 0:
            position += 4
        else:
            length = struct.unpack_from(">H", data, position + 4)[0]
            events.append(PatternEvent(tick, "note", key, velocity, length))
            position += 6
    return events


def parse_song(data: bytes, blob_offset: int, blob_size: int) -> Song:
    base = blob_offset + BLOB_HEADER_SIZE
    limit = blob_offset + blob_size
    track_table, pattern_table, channel_table, master_track, info, loop_point = struct.unpack_from(">6I", data, base)
    scaled = bool(info & 0x40000000)
    bpm = info & 0x0FFFFFFF
    if scaled:
        bpm >>= 10
    changes = [(0, max(1, bpm))]
    if master_track:
        position = base + master_track
        while position + 8 <= limit:
            tick, value = struct.unpack_from(">II", data, position)
            if tick == 0xFFFFFFFF:
                break
            value = value >> 10 if scaled else value
            if value:
                changes.append((tick, value))
            position += 8
        changes = _normalise_tempo(changes)
    song = Song(bpm=bpm, loop_tick=loop_point, tempo=TempoMap(changes))
    song.channels = list(data[base + channel_table:base + channel_table + TRACK_COUNT])

    for track in range(TRACK_COUNT):
        offset = struct.unpack_from(">I", data, base + track_table + 4 * track)[0]
        if not offset:
            continue
        entries = []
        position = base + offset
        while position + 12 <= limit:
            tick, program, volume, _pad, pattern, transpose, velocity_add = struct.unpack_from(">IBBHHbb", data, position)
            loop_index = struct.unpack_from(">H", data, position + 10)[0]
            entries.append(TrackEntry(tick, program, volume, pattern, transpose, velocity_add, loop_index))
            position += 12
            if pattern in (END_PATTERN, LOOP_PATTERN):
                break
        song.tracks[track] = entries

    used = {e.pattern for entries in song.tracks.values() for e in entries if e.pattern < LOOP_PATTERN}
    count = max(used) + 1 if used else 0
    pattern_offsets = [struct.unpack_from(">I", data, base + pattern_table + 4 * i)[0] for i in range(count)]
    song.patterns = [_parse_pattern(data, base + offset, limit) for offset in pattern_offsets]
    for offset in pattern_offsets:
        bend, modulation = struct.unpack_from(">II", data, base + offset + 4)
        song.bends.append(stream_values(decode_stream(data, base + bend, limit), PITCH_BEND_CENTRE) if bend else [])
        song.modulation.append(stream_values(decode_stream(data, base + modulation, limit), 0) if modulation else [])
    return song


def _normalise_tempo(changes: list[tuple[int, int]]) -> list[tuple[int, int]]:
    """Sorted, one change per tick (the last wins), starting at tick 0."""
    by_tick = {}
    for tick, bpm in changes:
        by_tick[tick] = bpm
    if 0 not in by_tick:
        by_tick[0] = changes[0][1]
    return sorted(by_tick.items())


@dataclass
class Note:
    tick: int
    channel: int
    key: int
    velocity: int
    length: int


@dataclass
class Timeline:
    notes: list[Note]
    controllers: list[tuple[int, int, int, int]]  # tick, channel, controller, value
    end_tick: int
    bends: list[tuple[int, int, int]] = field(default_factory=list)  # tick, channel, 14-bit value


def build_timeline(song: Song) -> Timeline:
    """Flatten tracks and patterns into absolute-tick notes and controller
    changes (one pass: a looping track stops where it would jump back)."""
    notes: list[Note] = []
    controllers: list[tuple[int, int, int, int]] = []
    bends: list[tuple[int, int, int]] = []
    end_tick = 0
    for track, entries in song.tracks.items():
        channel = song.channels[track] if track < len(song.channels) else 0xFF
        if channel == 0xFF:
            continue
        for entry in entries:
            if entry.pattern >= LOOP_PATTERN:
                end_tick = max(end_tick, entry.tick)
                break
            if entry.program != 0xFF:
                controllers.append((entry.tick, channel, CTL_PROGRAM, entry.program))
            if entry.volume != 0xFF:
                controllers.append((entry.tick, channel, CTL_VOLUME, entry.volume))
            if entry.pattern < len(song.bends) and song.bends[entry.pattern]:
                bends.append((entry.tick, channel, PITCH_BEND_CENTRE))  # each pattern restarts at centre
                bends.extend((entry.tick + tick, channel, value) for tick, value in song.bends[entry.pattern])
            for event in song.patterns[entry.pattern]:
                tick = entry.tick + event.tick
                if event.kind == "ctl":
                    controllers.append((tick, channel, event.a, event.b))
                else:
                    key = max(0, min(127, event.a + entry.transpose))
                    velocity = max(0, min(127, event.b + entry.velocity_add))
                    notes.append(Note(tick, channel, key, velocity, event.length))
                    end_tick = max(end_tick, tick + event.length)
    notes.sort(key=lambda n: n.tick)
    controllers.sort(key=lambda c: c[0])
    bends.sort(key=lambda b: b[0])
    return Timeline(notes, controllers, end_tick, bends)


def _channel_bends(timeline: Timeline, total: int, tempo: TempoMap) -> dict[int, np.ndarray]:
    """Per-channel pitch-bend curves, -1..1 of the range, at the output rate."""
    curves = {}
    for channel in {c for _t, c, _v in timeline.bends}:
        curve = np.zeros(total, dtype=np.float32)
        points = [(tempo.sample(t), v) for t, c, v in timeline.bends if c == channel]
        for i, (start, value) in enumerate(points):
            stop = points[i + 1][0] if i + 1 < len(points) else total
            curve[min(start, total):min(stop, total)] = (value - PITCH_BEND_CENTRE) / PITCH_BEND_CENTRE
        curves[channel] = curve
    return curves


def _channel_gains(timeline: Timeline, setup, total: int, tempo: TempoMap) -> dict[int, np.ndarray]:
    """Per-channel volume*expression curves sampled at the output rate."""
    state = {ch: {CTL_VOLUME: setup[ch].volume, CTL_EXPRESSION: 127} for ch in range(16)}
    changes: dict[int, list[tuple[int, float]]] = {ch: [] for ch in range(16)}
    for tick, channel, controller, value in timeline.controllers:
        if controller not in (CTL_VOLUME, CTL_EXPRESSION) or channel > 15:
            continue
        state[channel][controller] = value
        gain = (state[channel][CTL_VOLUME] / 127.0) * (state[channel][CTL_EXPRESSION] / 127.0)
        changes[channel].append((tempo.sample(tick), gain * gain))
    curves = {}
    for channel in range(16):
        initial = setup[channel].volume / 127.0
        curve = np.full(total, initial * initial, dtype=np.float32)
        points = changes[channel]
        for i, (start, gain) in enumerate(points):
            stop = points[i + 1][0] if i + 1 < len(points) else total
            curve[min(start, total):min(stop, total)] = gain
        curves[channel] = curve
    return curves


def render_song(banks: SoundBanks, data: bytes, index: int) -> tuple[int, np.ndarray]:
    """Render song ``index`` of a ``.slib`` to (sample rate, mono int16)."""
    blobs = split_slib(data)
    if index >= len(blobs):
        raise SongError(f"Song {index} is not in the library ({len(blobs)} songs).")
    group = next((g for bank in banks.banks for g in bank.song_groups if index in g.setups), None)
    if group is None:
        raise MusyxError(f"No song group has a MIDI setup for song {index}.")
    setup = group.setups[index]
    song = parse_song(data, *blobs[index])
    timeline = build_timeline(song)

    tempo = song.tempo
    duration = min(MAX_SECONDS, tempo.seconds(timeline.end_tick) + RELEASE_SECONDS + 0.5)
    total = int(duration * OUTPUT_RATE)
    out = np.zeros(total, dtype=np.float32)
    gains = _channel_gains(timeline, setup, total, tempo)
    bend_curves = _channel_bends(timeline, total, tempo)

    programs = [setup[ch].program for ch in range(16)]
    controller_events = iter(timeline.controllers)
    pending = next(controller_events, None)
    for note in timeline.notes:
        while pending is not None and pending[0] <= note.tick:
            if pending[2] == CTL_PROGRAM and pending[1] < 16:
                programs[pending[1]] = pending[3]
            pending = next(controller_events, None)
        start = tempo.sample(note.tick)
        if start >= total or note.channel > 15:
            continue
        pages = group.drum_pages if note.channel == 9 else group.pages
        page = pages.get(programs[note.channel])
        if page is None:
            continue
        voices = banks.voices_with_macro(page.macro, note.key)
        for bank, sample_id, played, gain, delay, macro_id in voices:
            begin = start + int(delay * OUTPUT_RATE)
            if begin < total:
                bend = bend_curves.get(note.channel)
                if bend is not None:
                    up, down = banks.pitch_wheel_range(macro_id)
                    bend = np.where(bend >= 0, bend * up, bend * down)
                _mix_voice(banks, (bank, sample_id, played), note, begin, tempo,
                           gains[note.channel] * (gain / len(voices)), out, bend)

    peak = float(np.max(np.abs(out))) if total else 0.0
    if peak > 1.0:
        out /= peak
    return OUTPUT_RATE, np.clip(out * 32767.0, -32768, 32767).astype(np.int16)


def _mix_voice(banks: SoundBanks, voice: tuple[Bank, int, int], note: Note, start: int,
               tempo: TempoMap, channel_gain: np.ndarray, out: np.ndarray,
               bend_semitones: np.ndarray | None = None) -> None:
    bank, sample_id, played = voice
    info, pcm = banks.sample_pcm(bank, sample_id)
    if not len(pcm):
        return
    step = info.sample_rate / OUTPUT_RATE * 2.0 ** ((played - info.base_key) / 12.0)
    held = tempo.sample(note.tick + note.length) - start
    release = int(RELEASE_SECONDS * OUTPUT_RATE)
    loops = info.loop_length > 0 and info.loop_offset + info.loop_length <= len(pcm)
    if loops:
        count = held + release
    else:
        count = int((len(pcm) - 1) / step)
    count = min(count, len(out) - start)
    if count <= 0:
        return
    if bend_semitones is None:
        position = np.arange(count, dtype=np.float64) * step
    else:
        steps = step * np.exp2(bend_semitones[start:start + count].astype(np.float64) / 12.0)
        position = np.concatenate(([0.0], np.cumsum(steps[:-1])))
        if not loops:
            count = int(np.searchsorted(position, len(pcm) - 1))
            position = position[:count]
            if count <= 0:
                return
    if loops:
        loop_end = info.loop_offset + info.loop_length
        over = position >= loop_end
        position[over] = info.loop_offset + (position[over] - info.loop_offset) % info.loop_length
    signal = np.interp(position, np.arange(len(pcm)), pcm).astype(np.float32)
    envelope = np.ones(count, dtype=np.float32)
    attack = min(count, 160)
    envelope[:attack] = np.linspace(0.0, 1.0, attack, dtype=np.float32)
    if loops and held < count:
        envelope[held:] = np.linspace(1.0, 0.0, count - held, dtype=np.float32)
    velocity = note.velocity / 127.0
    out[start:start + count] += signal * envelope * channel_gain[start:start + count] * (velocity * velocity)
