"""Coverage of Radiant Dawn's NW4R sound archives (``Sound/sound*.brsar``).

A BRSAR holds three sections. SYMB is the name table and the four name trees
(:mod:`brsar` looks names up in them). INFO is the table of sounds, banks, players, files and
groups the sound player reads (``nw4r::snd::SoundArchive``). FILE is the data of every group: the
headers of the embedded files one after the other (``RSEQ`` sequences, ``RBNK`` instrument banks,
``RWSD`` wave sounds), then their samples.

The layouts are the NW4R ones the app's readers (:mod:`brsar`, :mod:`rseq`, :mod:`rbnk`,
:mod:`rwsd`) follow; a field the readers do not use is placed by the same layout, and a reserved
word is checked to be zero. The samples are DSP-ADPCM or PCM, public codecs, and count as decoded
when a wave of an embedded file points at them.
"""

from __future__ import annotations

import struct

from .coverage import DECODED, PADDING, UNCLASSIFIED, UNDECODED, FileCoverage, Walker, handles


def _u32(data: bytes, at: int) -> int:
    return struct.unpack_from(">I", data, at)[0]


class _Refs:
    """NW4R data references: ``u8 is-offset, u8 data type, u16 reserved, u32 offset`` from a base."""

    def __init__(self, cov: FileCoverage, base: int, end: int):
        self.cov, self.base, self.end = cov, base, end

    def ref(self, at: int, name: str) -> tuple[int, int | None]:
        cov = self.cov
        kind, data_type, reserved, offset = struct.unpack_from(">BBHI", cov.data, at)
        cov.mark(at, 2, DECODED)
        cov.zero(at + 2, 2, f"{name} reference reserved")
        cov.mark(at + 4, 4, DECODED)
        if kind == 0:
            if offset:
                cov.mark(at + 4, 4, UNDECODED, f"{name} null reference offset")
            return data_type, None
        target = self.base + offset
        if not self.base <= target < self.end:
            raise ValueError(f"{name} reference lies outside its block")
        return data_type, target

    def table(self, at: int | None, name: str) -> list[tuple[int, int | None]]:
        """``u32 count`` + that many references."""
        if at is None:
            return []
        count = _u32(self.cov.data, at)
        self.cov.mark(at, 4, DECODED)
        return [self.ref(at + 4 + 8 * i, name) for i in range(count)]


def _close(cov: FileCoverage, start: int, end: int, name: str) -> None:
    """Bytes of a block no structure placed: alignment when zero, else open."""
    for i in range(start, end):
        if cov.status[i] == UNCLASSIFIED:
            cov.mark(i, 1, PADDING if cov.data[i] == 0 else UNDECODED, name)


def _header(cov: FileCoverage, magic: bytes, sections: int) -> list[tuple[int, int]]:
    """The NW4R binary header (magic, BOM, version, size, header size, section count, then
    ``offset, size`` per section); returns the sections."""
    data = cov.data
    if data[:4] != magic:
        raise ValueError(f"not a {magic.decode()} file")
    header_size, count = struct.unpack_from(">HH", data, 0x0C)
    if count != sections:
        raise ValueError(f"{magic.decode()} has {count} sections")
    cov.mark(0, 0x10 + 8 * count, DECODED)
    cov.zero(0x10 + 8 * count, header_size - 0x10 - 8 * count, "header padding")
    return [struct.unpack_from(">2I", data, 0x10 + 8 * i) for i in range(count)]


# ------------------------------------------------------------------ BRSAR

@handles("brsar", lambda name, data: data[:4] == b"RSAR")
def brsar_file(cov: FileCoverage, walker: Walker) -> None:
    from . import brsar

    archive = brsar.read_brsar(cov.data)
    assert brsar.build_brsar(archive) == cov.data
    symb, info, file = archive.sections
    _header(cov, b"RSAR", 3)
    cov.mark(symb.offset, symb.size, DECODED)  # names and the four name trees (brsar.tree_lookup)
    _info(cov, info.offset, info.offset + info.size)
    _file(cov, walker, archive, file.offset, file.offset + file.size)


_SOUND_DETAIL = {1: (0x14, "SeqSoundInfo"), 2: (0x0C, "StrmSoundInfo"), 3: (0x10, "WaveSoundInfo")}


def _info(cov: FileCoverage, start: int, end: int) -> None:
    data = cov.data
    cov.mark(start, 8, DECODED)
    base = start + 8
    refs = _Refs(cov, base, end)
    tops = [refs.ref(base + 8 * i, "INFO table")[1] for i in range(6)]
    sounds, banks, players, files, groups, player_info = tops

    for _, at in refs.table(sounds, "sound"):
        cov.mark(at, 0x0C, DECODED)  # name, file, player
        _, param3d = refs.ref(at + 0x0C, "Sound3DParam")
        cov.mark(at + 0x14, 4, DECODED)  # volume, player priority, type, remote filter
        detail_type, detail = refs.ref(at + 0x18, "sound detail")
        cov.mark(at + 0x20, 8, DECODED)  # user parameters
        cov.mark(at + 0x28, 3, DECODED)  # pan mode, pan curve, actor player
        cov.zero(at + 0x2B, 1, "sound reserved")
        if param3d is not None:
            cov.mark(param3d, 8, DECODED)  # flags, decay curve, decay ratio, doppler factor, pad
            cov.zero(param3d + 7, 1, "Sound3DParam padding")
            cov.zero(param3d + 8, 4, "Sound3DParam reserved")
        if detail is not None:
            size, name = _SOUND_DETAIL.get(detail_type, (0, "sound detail"))
            if not size:
                raise ValueError(f"sound detail type {detail_type}")
            cov.mark(detail, size - 4, DECODED, name)
            if detail_type in (1, 3):  # channel priority, release fix, then two bytes of padding
                cov.zero(detail + size - 6, 2, f"{name} padding")
            cov.zero(detail + size - 4, 4, f"{name} reserved")

    for _, at in refs.table(banks, "bank"):
        cov.mark(at, 8, DECODED)
        cov.zero(at + 8, 4, "bank reserved")

    for _, at in refs.table(players, "player"):
        cov.mark(at, 5, DECODED)  # name, playable sound count
        cov.zero(at + 5, 3, "player padding")
        cov.mark(at + 8, 4, DECODED)  # heap size
        cov.zero(at + 12, 4, "player reserved")

    for _, at in refs.table(files, "file"):
        cov.mark(at, 0x0C, DECODED)  # header size, data size, entry number
        _, path = refs.ref(at + 0x0C, "external file name")
        _, positions = refs.ref(at + 0x14, "file positions")
        if path is not None:
            stop = data.index(b"\0", path)
            cov.mark(path, stop + 1 - path, DECODED)
        for _, pos in refs.table(positions, "file position"):
            cov.mark(pos, 8, DECODED)  # group, index in the group

    for _, at in refs.table(groups, "group"):
        cov.mark(at, 8, DECODED)  # name, entry number
        _, path = refs.ref(at + 8, "group external file name")
        if path is not None:
            stop = data.index(b"\0", path)
            cov.mark(path, stop + 1 - path, DECODED)
        cov.mark(at + 0x10, 0x10, DECODED)  # header and wave-data offsets and sizes
        _, items = refs.ref(at + 0x20, "group items")
        for _, item in refs.table(items, "group item"):
            cov.mark(item, 0x14, DECODED)
            cov.zero(item + 0x14, 4, "group item reserved")

    if player_info is not None:
        cov.mark(player_info, 0x0E, DECODED)  # sound, track and channel counts
        cov.zero(player_info + 0x0E, 2, "player info padding")
        cov.zero(player_info + 0x10, 4, "player info reserved")
    _close(cov, start, end, "INFO (unplaced)")


def _file(cov: FileCoverage, walker: Walker, archive, start: int, end: int) -> None:
    from . import rbnk, rwsd

    cov.mark(start, 8, DECODED)
    cov.zero(start + 8, 0x18, "FILE header padding")
    files = {f.index: f for f in archive.files}
    for group in archive.groups:
        for member in group.entries:
            header_at = group.header_offset + member.header_offset
            wave_at = group.data_offset + member.data_offset
            header = cov.data[header_at:header_at + member.header_size]
            waves = cov.data[wave_at:wave_at + member.data_size]
            name = files[member.file_index].external_path or f"file{member.file_index}"
            magic = header[:4]
            handler = _EMBEDDED.get(magic)
            if handler is None:
                raise ValueError(f"group {group.name} holds a {magic!r} file")
            # Placed in place, so the archive's bytes are counted once, under brsar.
            sub = FileCoverage(header, magic.decode().lower(), name)
            handler(sub, walker)
            cov.status[header_at:header_at + len(header)] = sub.status
            prefix = f"{magic.decode()} "
            cov.labels += [(header_at + a, header_at + b, st, prefix + label) for a, b, st, label in sub.labels]
            if not member.data_size:
                continue
            if magic == b"RWSD":
                used = [(w.data_offset, w) for w in rwsd.read_rwsd(header, waves).waves]
            elif magic == b"RBNK":
                used = [(w.data_offset, w) for w in rbnk.read_rbnk(header, waves).waves]
            else:
                raise ValueError(f"{magic!r} file with wave data")
            for offset, wave in used:
                for channel in wave.channels:
                    size = _sample_bytes(wave)
                    cov.mark(wave_at + offset + channel.data_offset, size, DECODED)
            _close(cov, wave_at, wave_at + member.data_size, "group wave data (no wave points at it)")
    _close(cov, start, end, "FILE (unplaced)")


def _sample_bytes(wave) -> int:
    if wave.encoding == 2:  # DSP-ADPCM: whole 8-byte frames of a header byte and 14 samples
        return -(-(wave.sample_count + 2) // 14) * 8
    return wave.sample_count * (1 if wave.encoding == 0 else 2)


# ------------------------------------------------------------------ embedded files
# Placed by brsar_file inside the archive (they exist only there).

def rseq_file(cov: FileCoverage, walker: Walker) -> None:
    from . import rseq

    rseq.read_rseq(cov.data)
    data = cov.data
    (data_at, data_size), (label_at, label_size) = _header(cov, b"RSEQ", 2)
    # DATA: magic, size, the offset of the command stream, then the MML byte-code the sequence
    # player runs (rseq.collect_notes follows it).
    cov.mark(data_at, data_size, DECODED)
    cov.mark(label_at, 0x0C, DECODED)
    count = _u32(data, label_at + 8)
    cov.mark(label_at + 0x0C, 4 * count, DECODED)
    for i in range(count):
        at = label_at + 8 + _u32(data, label_at + 0x0C + 4 * i)
        length = _u32(data, at + 4)
        cov.mark(at, 8 + length + 1, DECODED)  # command offset, length, name and its terminator
    _close(cov, label_at, label_at + label_size, "LABL (unplaced)")
    _close(cov, 0, len(data), "RSEQ (unplaced)")


def _wave_infos(cov: FileCoverage, start: int, end: int, targets: list[int]) -> None:
    """``WaveInfo`` records (format, loop flag, channels, rate, loop start and end, channel table,
    data offset) and their channels (data, ADPCM state, four volumes)."""
    data = cov.data
    for at in targets:
        cov.mark(at, 6, DECODED)  # format, loop, channel count, 24-bit sample rate
        cov.zero(at + 6, 2, "WaveInfo padding")
        cov.mark(at + 8, 0x10, DECODED)  # loop start, loop end, channel table offset, data offset
        cov.zero(at + 0x18, 4, "WaveInfo reserved")
        channels = data[at + 2]
        table = at + _u32(data, at + 0x10)
        for i in range(channels):
            cov.mark(table + 4 * i, 4, DECODED)
            channel = at + _u32(data, table + 4 * i)
            cov.mark(channel, 0x18, DECODED)  # data offset, ADPCM offset, four volumes
            cov.zero(channel + 0x18, 4, "ChannelInfo reserved")
            if data[at] == 2:
                adpcm = at + _u32(data, channel + 4)
                cov.mark(adpcm, 0x2E, DECODED)  # coefficients, gain, scale, history, loop context
                cov.zero(adpcm + 0x2E, 2, "AdpcmInfo padding")
    _close(cov, start, end, "WAVE (unplaced)")


def _note_param(cov: FileCoverage, refs: _Refs, at: int, name: str) -> None:
    """``InstParam`` / ``NoteInfo``: wave, envelope, hold, key, volume, pan, pitch, then the LFO,
    envelope-graph and randomizer tables (null on every vanilla note), then a reserved word."""
    cov.mark(at, 0x14, DECODED)
    for i, table in enumerate(("LFO table", "graph envelope table", "randomizer table")):
        _, target = refs.ref(at + 0x14 + 8 * i, f"{name} {table}")
        if target is not None:
            cov.mark(target, 4, UNDECODED, f"{name} {table}")
    cov.zero(at + 0x2C, 4, f"{name} reserved")


def rwsd_file(cov: FileCoverage, walker: Walker) -> None:
    data = cov.data
    (data_at, data_size), (wave_at, wave_size) = _header(cov, b"RWSD", 2)
    cov.mark(data_at, 8, DECODED)
    refs = _Refs(cov, data_at + 8, data_at + data_size)
    for _, sound in refs.table(data_at + 8, "WaveSound"):
        _, info = refs.ref(sound, "WaveSoundInfo")
        _, tracks = refs.ref(sound + 8, "track table")
        _, notes = refs.ref(sound + 0x10, "note table")
        if info is not None:
            cov.mark(info, 10, DECODED)  # pitch, pan, surround pan, three effect sends, main send
            cov.zero(info + 10, 2, "WaveSoundInfo padding")
            for i, table in enumerate(("graph envelope table", "randomizer table")):
                _, target = refs.ref(info + 0x0C + 8 * i, f"WaveSoundInfo {table}")
                if target is not None:
                    cov.mark(target, 4, UNDECODED, f"WaveSoundInfo {table}")
            cov.zero(info + 0x1C, 4, "WaveSoundInfo reserved")
        for _, track in refs.table(tracks, "track"):
            # TrackInfo: a reference to the track's note-event table
            _, events = refs.ref(track, "note events") if track is not None else (0, None)
            for _, event in refs.table(events, "note event"):
                cov.mark(event, 0x0C, DECODED)  # position, length, note index
                cov.zero(event + 0x0C, 4, "note event reserved")
        for _, note in refs.table(notes, "note"):
            _note_param(cov, refs, note, "NoteInfo")
    _close(cov, data_at, data_at + data_size, "DATA (unplaced)")
    cov.mark(wave_at, 0x0C, DECODED)
    count = _u32(data, wave_at + 8)
    cov.mark(wave_at + 0x0C, 4 * count, DECODED)
    _wave_infos(cov, wave_at, wave_at + wave_size,
                [wave_at + _u32(data, wave_at + 0x0C + 4 * i) for i in range(count)])
    _close(cov, 0, len(data), "RWSD (unplaced)")


def rbnk_file(cov: FileCoverage, walker: Walker) -> None:
    data = cov.data
    (data_at, data_size), (wave_at, wave_size) = _header(cov, b"RBNK", 2)
    cov.mark(data_at, 8, DECODED)
    refs = _Refs(cov, data_at + 8, data_at + data_size)
    seen: set[int] = set()

    def node(data_type: int, at: int | None, depth: int = 0) -> None:
        if at is None or at in seen or depth > 4:
            return
        seen.add(at)
        if data_type == 1:
            _note_param(cov, refs, at, "InstParam")
        elif data_type == 2:  # range table: size, upper keys, aligned, then a reference per range
            size = data[at]
            cov.mark(at, 1 + size, DECODED)
            refs_at = at + ((1 + size + 3) & ~3)
            cov.zero(at + 1 + size, refs_at - at - 1 - size, "RangeTable padding")
            for i in range(size):
                node(*refs.ref(refs_at + 8 * i, "range"), depth + 1)
        elif data_type == 3:  # index table: lowest and highest key, then a reference per key
            low, high = data[at], data[at + 1]
            cov.mark(at, 2, DECODED)
            cov.zero(at + 2, 2, "IndexTable reserved")
            for i in range(high - low + 1):
                node(*refs.ref(at + 4 + 8 * i, "index"), depth + 1)
        else:
            raise ValueError(f"RBNK node type {data_type}")

    for data_type, at in refs.table(data_at + 8, "program"):
        node(data_type, at)
    _close(cov, data_at, data_at + data_size, "DATA (unplaced)")
    cov.mark(wave_at, 8, DECODED)
    wave_refs = _Refs(cov, wave_at + 8, wave_at + wave_size)
    targets = [at for _, at in wave_refs.table(wave_at + 8, "wave") if at is not None]
    _wave_infos(cov, wave_at, wave_at + wave_size, targets)
    _close(cov, 0, len(data), "RBNK (unplaced)")


_EMBEDDED = {b"RSEQ": rseq_file, b"RWSD": rwsd_file, b"RBNK": rbnk_file}
