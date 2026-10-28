"""Preservation-first reader for Nintendo's Wii ``RSAR`` sound archive.

Phase 7 initially needs a trustworthy archive catalogue: the named resources
in ``SYMB`` are joined with FE10's cue registry and with the embedded files
stored through INFO groups.  Unknown entry fields remain in the source and
the writer is still deliberately preservation-first.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass


class BrsarError(ValueError):
    pass


@dataclass(frozen=True)
class BrsarSection:
    magic: str
    offset: int
    size: int


@dataclass(frozen=True)
class BrsarFile:
    index: int
    external_path: str | None
    header: bytes = b""
    wave_data: bytes = b""
    group_refs: tuple[tuple[int, int], ...] = ()
    info_offset: int = 0

    @property
    def magic(self) -> str | None:
        return self.header[:4].decode("ascii", "replace") if len(self.header) >= 4 else None


@dataclass(frozen=True)
class BrsarGroupEntry:
    file_index: int
    header_offset: int
    header_size: int
    data_offset: int
    data_size: int
    info_offset: int = 0


@dataclass(frozen=True)
class BrsarGroup:
    index: int
    name: str
    header_offset: int
    header_size: int
    data_offset: int
    data_size: int
    entries: tuple[BrsarGroupEntry, ...]
    info_offset: int = 0


@dataclass(frozen=True)
class BrsarBank:
    index: int
    name: str
    file_index: int


@dataclass(frozen=True)
class BrsarSound:
    index: int
    name: str
    file_index: int
    external_path: str | None
    sound_type: int = 0
    volume: int = 0
    player_priority: int = 0
    info_index: int = 0
    bank_index: int | None = None
    raw: bytes = b""


@dataclass(frozen=True)
class BrsarArchive:
    version: int
    sections: tuple[BrsarSection, ...]
    symbols: tuple[str, ...]
    files: tuple[BrsarFile, ...]
    sounds: tuple[BrsarSound, ...]
    source: bytes
    groups: tuple[BrsarGroup, ...] = ()
    banks: tuple[BrsarBank, ...] = ()

    def has_symbol(self, name: str) -> bool:
        return name in self.symbols


def read_brsar(data: bytes) -> BrsarArchive:
    if len(data) < 0x40 or data[:4] != b"RSAR":
        raise BrsarError("Not a BRSAR file (missing RSAR header)")
    bom, version, file_size, header_size, section_count = struct.unpack_from(">HHIHH", data, 4)
    if bom != 0xFEFF or file_size != len(data) or header_size < 0x28:
        raise BrsarError("Invalid BRSAR header")
    if section_count != 3:
        raise BrsarError(f"Expected three BRSAR sections, found {section_count}")
    sections = []
    for index in range(section_count):
        offset, size = struct.unpack_from(">2I", data, 0x10 + index * 8)
        if offset < header_size or size < 8 or offset + size > len(data):
            raise BrsarError("BRSAR section lies outside the file")
        magic = data[offset:offset + 4].decode("ascii", "replace")
        if struct.unpack_from(">I", data, offset + 4)[0] != size:
            raise BrsarError(f"{magic} section size does not match its header")
        sections.append(BrsarSection(magic, offset, size))
    if tuple(section.magic for section in sections) != ("SYMB", "INFO", "FILE"):
        raise BrsarError("Unexpected BRSAR section order")

    symb = sections[0]
    base = symb.offset + 8
    table = base + struct.unpack_from(">I", data, base)[0]
    if table + 4 > symb.offset + symb.size:
        raise BrsarError("BRSAR symbol table lies outside SYMB")
    count = struct.unpack_from(">I", data, table)[0]
    if table + 4 + count * 4 > symb.offset + symb.size:
        raise BrsarError("BRSAR symbol offsets are truncated")
    symbols = []
    for index in range(count):
        offset = base + struct.unpack_from(">I", data, table + 4 + index * 4)[0]
        end = data.find(b"\0", offset, symb.offset + symb.size)
        if not base <= offset < symb.offset + symb.size or end < 0:
            raise BrsarError(f"Invalid BRSAR symbol {index}")
        symbols.append(data[offset:end].decode("shift_jis", "replace"))
    info = sections[1]
    info_base = info.offset + 8

    def reference(at: int) -> int | None:
        if at < 0 or at + 8 > info.offset + info.size:
            raise BrsarError("BRSAR INFO reference is truncated")
        kind, offset = struct.unpack_from(">2I", data, at)
        return None if kind == 0 else info_base + offset

    def vector(top_reference: int, *, allow_null: bool = False) -> list[int | None]:
        start = reference(top_reference)
        if start is None or start + 4 > info.offset + info.size:
            raise BrsarError("BRSAR INFO vector is missing")
        count = struct.unpack_from(">I", data, start)[0]
        if start + 4 + count * 8 > info.offset + info.size:
            raise BrsarError("BRSAR INFO vector is truncated")
        result = []
        for item in range(count):
            target = reference(start + 4 + item * 8)
            if target is None and not allow_null:
                raise BrsarError("BRSAR INFO vector contains a null entry")
            result.append(target)
        return result

    def cstring(at: int) -> str:
        if not info_base <= at < info.offset + info.size:
            raise BrsarError("BRSAR INFO string is outside INFO")
        end = data.find(b"\0", at, info.offset + info.size)
        if end < 0:
            raise BrsarError("BRSAR INFO string is not terminated")
        return data[at:end].decode("shift_jis", "replace")

    def direct_vector(at: int) -> list[int]:
        if at + 4 > info.offset + info.size:
            raise BrsarError("BRSAR INFO direct vector is truncated")
        count = struct.unpack_from(">I", data, at)[0]
        if at + 4 + count * 8 > info.offset + info.size:
            raise BrsarError("BRSAR INFO direct vector entries are truncated")
        result = []
        for item in range(count):
            target = reference(at + 4 + item * 8)
            if target is None:
                raise BrsarError("BRSAR INFO direct vector contains a null entry")
            result.append(target)
        return result

    # INFO's vectors: sounds, banks, players, files, groups and footer.
    group_entries = vector(info_base + 4 * 8)
    groups = []
    for index, entry in enumerate(group_entries):
        assert entry is not None
        if entry + 0x28 > info.offset + info.size:
            raise BrsarError("BRSAR group entry is truncated")
        symbol_index, _entry_number = struct.unpack_from(">2I", data, entry)
        header_offset, header_size, wave_offset, wave_size = struct.unpack_from(">4I", data, entry + 0x10)
        members_at = reference(entry + 0x20)
        if symbol_index != 0xFFFFFFFF and symbol_index >= len(symbols) or members_at is None:
            raise BrsarError("BRSAR group has an invalid name or member list")
        members = []
        for member_at in direct_vector(members_at):
            file_index, member_header, member_header_size, member_data, member_data_size, _reserved = \
                struct.unpack_from(">6I", data, member_at)
            members.append(BrsarGroupEntry(file_index, member_header, member_header_size,
                                           member_data, member_data_size, member_at))
        if header_offset + header_size > len(data) or wave_offset + wave_size > len(data):
            raise BrsarError("BRSAR group data lies outside the archive")
        name = symbols[symbol_index] if symbol_index != 0xFFFFFFFF else f"group_{index}"
        groups.append(BrsarGroup(index, name, header_offset, header_size,
                                 wave_offset, wave_size, tuple(members), entry))

    file_entries = vector(info_base + 3 * 8)
    preliminary_files = []
    for index, entry in enumerate(file_entries):
        assert entry is not None
        path_at = reference(entry + 0x0C)
        path = cstring(path_at) if path_at is not None else None
        refs_at = reference(entry + 0x14)
        refs = []
        if refs_at is not None:
            for ref_at in direct_vector(refs_at):
                refs.append(struct.unpack_from(">2I", data, ref_at))
        preliminary_files.append((index, path, tuple(refs), entry))

    files = []
    for index, path, refs, info_offset in preliminary_files:
        header = wave = b""
        if refs:
            group_index, member_index = refs[0]
            if group_index >= len(groups) or member_index >= len(groups[group_index].entries):
                raise BrsarError("BRSAR file group reference is out of range")
            group = groups[group_index]
            member = group.entries[member_index]
            if member.file_index != index:
                raise BrsarError("BRSAR file group reference points to another file")
            header_at = group.header_offset + member.header_offset
            wave_at = group.data_offset + member.data_offset
            if header_at + member.header_size > len(data) or wave_at + member.data_size > len(data):
                raise BrsarError("BRSAR embedded file lies outside the archive")
            header = data[header_at:header_at + member.header_size]
            wave = data[wave_at:wave_at + member.data_size]
        files.append(BrsarFile(index, path, header, wave, refs, info_offset))

    bank_entries = vector(info_base + 8)
    banks = []
    for index, entry in enumerate(bank_entries):
        assert entry is not None
        symbol_index, file_index = struct.unpack_from(">2I", data, entry)
        if symbol_index >= len(symbols) or file_index >= len(files):
            raise BrsarError("BRSAR bank entry has an out-of-range index")
        banks.append(BrsarBank(index, symbols[symbol_index], file_index))

    sound_entries = vector(info_base)
    sounds = []
    for index, entry in enumerate(sound_entries):
        assert entry is not None
        if entry + 0x2C > info.offset + info.size:
            raise BrsarError("BRSAR sound entry is truncated")
        symbol_index, file_index, _player_index = struct.unpack_from(">3I", data, entry)
        if symbol_index >= len(symbols) or file_index >= len(files):
            raise BrsarError("BRSAR sound entry has an out-of-range index")
        volume, priority, sound_type, _remote = struct.unpack_from(">4B", data, entry + 0x14)
        sound_info = reference(entry + 0x18)
        info_index = 0
        bank_index = None
        if sound_info is not None:
            info_index = struct.unpack_from(">I", data, sound_info)[0]
            if sound_type == 1:
                bank_index = struct.unpack_from(">I", data, sound_info + 4)[0]
        sounds.append(BrsarSound(index, symbols[symbol_index], file_index, files[file_index].external_path,
                                 sound_type, volume, priority, info_index, bank_index,
                                 bytes(data[entry:entry + 0x2C])))
    return BrsarArchive(version, tuple(sections), tuple(symbols), tuple(files), tuple(sounds), data,
                        tuple(groups), tuple(banks))


def build_brsar(archive: BrsarArchive) -> bytes:
    """Return an unchanged parsed archive byte-identically.

    Mutating embedded resources requires a dedicated builder; callers cannot
    accidentally serialize a partial interpretation.
    """
    read_brsar(archive.source)
    return archive.source


def replace_embedded_file(archive: BrsarArchive, file_index: int, header: bytes,
                          wave_data: bytes) -> bytes:
    """Replace one internal file and rebuild every RSAR group copy.

    SYMB and INFO retain their original layouts; only documented file/group
    sizes and offsets are updated.  This is sufficient for replacement while
    deliberately avoiding the unrelated complexity of adding archive names.
    """
    if not 0 <= file_index < len(archive.files):
        raise BrsarError("BRSAR file index is out of range")
    original = archive.files[file_index]
    if not original.group_refs or original.external_path is not None:
        raise BrsarError("Only embedded BRSAR files can be replaced")
    if len(header) < 4 or header[:4] not in (b"RWSD", b"RBNK", b"RSEQ"):
        raise BrsarError("Unsupported embedded BRSAR file type")
    if bytes(header) == original.header and bytes(wave_data) == original.wave_data:
        return archive.source

    info_section = next(section for section in archive.sections if section.magic == "INFO")
    file_section = next(section for section in archive.sections if section.magic == "FILE")
    info = bytearray(archive.source[info_section.offset:info_section.offset + info_section.size])
    file_out = bytearray(archive.source[file_section.offset:file_section.offset + 0x20])

    def align() -> None:
        file_out.extend(bytes(-len(file_out) % 0x20))

    replacements = {file_index: (bytes(header), bytes(wave_data))}
    file_sizes: dict[int, tuple[int, int]] = {}
    for group in archive.groups:
        align()
        group_header_absolute = file_section.offset + len(file_out)
        member_layouts = []
        for member in group.entries:
            item = archive.files[member.file_index]
            item_header, item_wave = replacements.get(member.file_index, (item.header, item.wave_data))
            relative_header = len(file_out) - (group_header_absolute - file_section.offset)
            file_out += item_header
            align()
            member_layouts.append([relative_header, len(item_header), 0, len(item_wave)])
            file_sizes[member.file_index] = (len(item_header), len(item_wave))
        group_header_size = len(file_out) - (group_header_absolute - file_section.offset)
        align()
        group_data_absolute = file_section.offset + len(file_out)
        for member, layout in zip(group.entries, member_layouts):
            item = archive.files[member.file_index]
            _item_header, item_wave = replacements.get(member.file_index, (item.header, item.wave_data))
            layout[2] = len(file_out) - (group_data_absolute - file_section.offset)
            file_out += item_wave
            align()
        group_data_size = len(file_out) - (group_data_absolute - file_section.offset)

        group_at = group.info_offset - info_section.offset
        struct.pack_into(">4I", info, group_at + 0x10, group_header_absolute, group_header_size,
                         group_data_absolute, group_data_size)
        for member, layout in zip(group.entries, member_layouts):
            member_at = member.info_offset - info_section.offset
            struct.pack_into(">4I", info, member_at + 4, *layout)

    for index, (header_size, data_size) in file_sizes.items():
        file_at = archive.files[index].info_offset - info_section.offset
        struct.pack_into(">2I", info, file_at, header_size, data_size)

    struct.pack_into(">I", file_out, 4, len(file_out))
    prefix = bytearray(archive.source[:info_section.offset])
    result = prefix + info + file_out
    struct.pack_into(">I", result, 8, len(result))
    struct.pack_into(">2I", result, 0x20, file_section.offset, len(file_out))
    rebuilt = bytes(result)
    checked = read_brsar(rebuilt)
    changed = checked.files[file_index]
    if changed.header != header or changed.wave_data != wave_data:
        raise BrsarError("Rebuilt BRSAR replacement did not validate")
    return rebuilt

