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


# -- adding stream sounds --------------------------------------------------------------------
#
# SYMB (after its 8-byte header) starts with five offsets: the string table, then the sound,
# player, group and bank name trees. A tree is ``u32 root, u32 count`` and ``count`` 0x14-byte
# nodes ``u16 flags (1: leaf), u16 bit, u32 left, u32 right, u32 string, u32 id``. A name is
# found from the root: at an inner node, bit ``b`` of the name (byte ``b >> 3``, most
# significant bit first; past the end of the name it is 0) picks right when set, else left; the
# leaf holds the string and id. Checked against every retail RFEE01 sound and bank.
#
# A STRM sound is a 0x2C INFO entry (string, file, player, a 3D-parameter reference, volume,
# priority, type 2, a reference to its 12-byte stream info, user words), and its file a 0x1C
# entry (file size, wave size 0, entry -1, a reference to the external path, an empty position
# table). Adding one appends the new INFO records and moved copies of the sound and file
# tables after INFO's old content, so every existing INFO offset stays valid.

NODE = struct.Struct(">HHIIII")
_REF = 0x01000000


@dataclass(frozen=True)
class StreamSoundSpec:
    """One STRM sound to add: its name, its ``strm/...brstm`` path and the records copied
    from a template sound (``stream_spec``)."""

    name: str
    external_path: str
    file_size: int
    entry: bytes        # the 0x2C sound entry (string and file fields are rewritten)
    strm_info: bytes    # 12 bytes: start position, channel count, track flags, reserved
    param3d: bytes      # 12 bytes
    strm_info_ref: int  # the reference word of the stream info (type 0x0102...)


def _tree_bit(name: bytes, bit: int) -> int:
    index = bit >> 3
    return (name[index] >> (7 - (bit & 7))) & 1 if index < len(name) else 0


def _symb_layout(data: bytes, archive: BrsarArchive):
    symb = archive.sections[0]
    base = symb.offset + 8
    offsets = struct.unpack_from(">5I", data, base)
    table = base + offsets[0]
    count = struct.unpack_from(">I", data, table)[0]
    strings = []
    for index in range(count):
        at = base + struct.unpack_from(">I", data, table + 4 + 4 * index)[0]
        strings.append(data[at:data.index(b"\0", at)])
    trees = []
    for which in range(1, 5):
        at = base + offsets[which]
        root, nodes = struct.unpack_from(">2I", data, at)
        trees.append((root, [list(NODE.unpack_from(data, at + 8 + NODE.size * i)) for i in range(nodes)]))
    return strings, trees


def tree_lookup(root: int, nodes: list, strings: list[bytes], name: str) -> int | None:
    """The id a name tree gives ``name`` (None when it has no such name)."""
    if not nodes:
        return None
    key = name.encode("shift_jis")
    node = nodes[root]
    while not node[0] & 1:
        node = nodes[node[3] if _tree_bit(key, node[1]) else node[2]]
    return node[5] if strings[node[4]] == key else None


def sound_id_of(data: bytes, name: str) -> int | None:
    """The sound id the archive's sound name tree gives ``name``."""
    strings, trees = _symb_layout(data, read_brsar(data))
    return tree_lookup(*trees[0], strings, name)


def _tree_insert(root: int, nodes: list, strings: list[bytes], key: bytes, string_index: int,
                 item_id: int) -> int:
    """Insert a leaf (crit-bit insertion, appending a leaf and an inner node); returns the root."""
    leaf = [1, 0xFFFF, 0xFFFFFFFF, 0xFFFFFFFF, string_index, item_id]
    if not nodes:
        nodes.append(leaf)
        return 0
    node = nodes[root]
    while not node[0] & 1:
        node = nodes[node[3] if _tree_bit(key, node[1]) else node[2]]
    other = strings[node[4]]
    if other == key:
        raise BrsarError(f"{key.decode('shift_jis', 'replace')} is already in the name tree")
    crit = next(bit for bit in range(8 * (max(len(key), len(other)) + 1))
                if _tree_bit(key, bit) != _tree_bit(other, bit))
    parent, side, current = None, 0, root
    while not nodes[current][0] & 1 and nodes[current][1] < crit:
        parent, side = current, _tree_bit(key, nodes[current][1])
        current = nodes[current][3] if side else nodes[current][2]
    leaf_index, inner_index = len(nodes), len(nodes) + 1
    nodes.append(leaf)
    inner = [0, crit, current, leaf_index, 0xFFFFFFFF, 0xFFFFFFFF]
    if not _tree_bit(key, crit):
        inner[2], inner[3] = leaf_index, current
    nodes.append(inner)
    if parent is None:
        return inner_index
    nodes[parent][3 if side else 2] = inner_index
    return root


def stream_spec(archive: BrsarArchive, template: int, name: str, external_path: str, file_size: int,
                channels: int | None = None) -> StreamSoundSpec:
    """A new STRM sound copying sound ``template``'s player, volume and 3D settings."""
    data = archive.source
    if not 0 <= template < len(archive.sounds) or archive.sounds[template].sound_type != 2:
        raise BrsarError("The template must be a stream (STRM) sound")
    info_base = archive.sections[1].offset + 8
    table = info_base + struct.unpack_from(">2I", data, info_base)[1]
    entry_at = info_base + struct.unpack_from(">2I", data, table + 4 + 8 * template)[1]
    entry = data[entry_at:entry_at + 0x2C]
    ref3d = struct.unpack_from(">2I", data, entry_at + 0x0C)
    ref_info = struct.unpack_from(">2I", data, entry_at + 0x18)
    param3d = data[info_base + ref3d[1]:info_base + ref3d[1] + 12] if ref3d[0] else bytes(12)
    strm = bytearray(data[info_base + ref_info[1]:info_base + ref_info[1] + 12])
    if channels is not None:
        if not 1 <= channels <= 16:
            raise BrsarError("A stream has 1 to 16 channels")
        struct.pack_into(">HH", strm, 4, channels, (1 << ((channels + 1) // 2)) - 1)
    return StreamSoundSpec(name, external_path, file_size, entry, bytes(strm), param3d, ref_info[0])


def _append_sound(data: bytes, name: str, entry: bytes, info_ref: int, sound_info: bytes, param3d: bytes,
                  file_record, groups: tuple[int, ...] = ()) -> tuple[bytes, int, int]:
    """``data`` with a new sound ``name`` (its 0x2C ``entry`` copied, its sound info and 3D block
    appended) and a new file (``file_record(rel, positions_at)`` gives its 0x1C entry), the name
    put into SYMB's sound tree, and the file added to ``groups`` with empty placeholders (the
    caller lays FILE out). Returns the bytes, the sound id and the file id."""
    archive = read_brsar(data)
    if name in {sound.name for sound in archive.sounds} or name in archive.symbols:
        raise BrsarError(f"{name} is already in the sound archive")
    symb, info, file_section = archive.sections
    strings, trees = _symb_layout(data, archive)
    key = name.encode("shift_jis")
    string_index, sound_id, file_id = len(strings), len(archive.sounds), len(archive.files)
    strings.append(key)
    root, nodes = trees[0]
    trees[0] = (_tree_insert(root, nodes, strings, key, string_index, sound_id), nodes)

    # SYMB: offsets, string table, strings, then the trees
    body = bytearray(20)
    table_at = len(body)
    body += struct.pack(">I", len(strings)) + bytes(4 * len(strings))
    for index, raw in enumerate(strings):
        struct.pack_into(">I", body, table_at + 4 + 4 * index, len(body))
        body += raw + b"\0"
    tree_offsets = []
    for tree_root, tree_nodes in trees:
        tree_offsets.append(len(body))
        body += struct.pack(">2I", tree_root, len(tree_nodes))
        for node in tree_nodes:
            body += NODE.pack(*node)
    struct.pack_into(">5I", body, 0, table_at, *tree_offsets)
    new_symb = bytearray(b"SYMB" + bytes(4)) + body
    new_symb += bytes(-len(new_symb) % 0x20)
    struct.pack_into(">I", new_symb, 4, len(new_symb))

    # INFO: its old content, then the new records and moved copies of the tables that grow
    old_info = bytearray(data[info.offset:info.offset + info.size])
    new_info = bytearray(old_info)  # kept whole (its padding too): every old offset stays valid

    def rel() -> int:
        return len(new_info) - 8

    def old_vector(at: int) -> tuple[bytes, int]:
        count = struct.unpack_from(">I", old_info, at)[0]
        return bytes(old_info[at + 4:at + 4 + 8 * count]), count

    param_at = rel()
    new_info += param3d
    info_at = rel()
    new_info += sound_info
    entry = bytearray(entry)
    struct.pack_into(">2I", entry, 0, string_index, file_id)
    struct.pack_into(">2I", entry, 0x0C, _REF, param_at)
    struct.pack_into(">2I", entry, 0x18, info_ref, info_at)
    entry_at = rel()
    new_info += entry
    # the file's position table: one (group, member) pair per group it joins
    members = []
    for group in groups:
        members.append((group, len(archive.groups[group].entries)))
    pairs_at = []
    for group, member in members:
        pairs_at.append(rel())
        new_info += struct.pack(">2I", group, member)
    positions_at = rel()
    new_info += struct.pack(">I", len(members)) + b"".join(struct.pack(">2I", _REF, at) for at in pairs_at)
    record = file_record(rel, positions_at, new_info)  # may first append what it points at
    file_at = rel()
    new_info += record
    for which, added in ((0, entry_at), (3, file_at)):
        refs, count = old_vector(8 + struct.unpack_from(">2I", old_info, 8 + 8 * which)[1])
        moved = rel()
        new_info += struct.pack(">I", count + 1) + refs + struct.pack(">2I", _REF, added)
        struct.pack_into(">2I", new_info, 8 + 8 * which, _REF, moved)
    for group, _member in members:
        # a placeholder member: the caller's FILE rebuild gives it its offsets and sizes
        item_at = rel()
        new_info += struct.pack(">6I", file_id, 0, 0, 0, 0, 0)
        group_at = archive.groups[group].info_offset - info.offset
        refs, count = old_vector(8 + struct.unpack_from(">2I", old_info, group_at + 0x20)[1])
        moved = rel()
        new_info += struct.pack(">I", count + 1) + refs + struct.pack(">2I", _REF, item_at)
        struct.pack_into(">2I", new_info, group_at + 0x20, _REF, moved)
    new_info += bytes(-len(new_info) % 0x20)
    struct.pack_into(">I", new_info, 4, len(new_info))

    # FILE moves: shift every absolute group offset
    shift = (symb.offset + len(new_symb) + len(new_info)) - file_section.offset
    for group in archive.groups:
        at = group.info_offset - info.offset
        header_offset, header_size, wave_offset, wave_size = struct.unpack_from(">4I", new_info, at + 0x10)
        struct.pack_into(">4I", new_info, at + 0x10, header_offset + shift, header_size, wave_offset + shift,
                         wave_size)
    result = bytearray(data[:symb.offset]) + new_symb + new_info + \
        data[file_section.offset:file_section.offset + file_section.size]
    struct.pack_into(">I", result, 8, len(result))
    struct.pack_into(">6I", result, 0x10, symb.offset, len(new_symb), symb.offset + len(new_symb), len(new_info),
                     symb.offset + len(new_symb) + len(new_info), file_section.size)
    return bytes(result), sound_id, file_id


def add_stream_sound(data: bytes, spec: StreamSoundSpec) -> bytes:
    """``data`` with a new STRM sound ``spec.name`` playing the external ``spec.external_path``."""
    def external_file(rel, positions_at, info):
        path_at = rel()
        info += spec.external_path.encode("shift_jis") + b"\0"
        info += bytes(-len(info) % 4)
        return (struct.pack(">IIi", spec.file_size, 0, -1) + struct.pack(">2I", _REF, path_at) +
                struct.pack(">2I", _REF, positions_at))

    rebuilt, sound_id, _file_id = _append_sound(data, spec.name, spec.entry, spec.strm_info_ref, spec.strm_info,
                                                spec.param3d, external_file)
    checked = read_brsar(rebuilt)
    sound = checked.sounds[sound_id]
    if (sound.name, sound.external_path, sound_id_of(rebuilt, spec.name)) != (spec.name, spec.external_path,
                                                                              sound_id):
        raise BrsarError("The rebuilt sound archive did not validate")
    return rebuilt


@dataclass(frozen=True)
class WaveSoundSpec:
    """One wave sound to add, with its own embedded one-entry RWSD (``rwsd.single_entry_rwsd``),
    loaded with the groups ``groups`` (those of the template sound's file)."""

    name: str
    header: bytes       # the RWSD
    wave_data: bytes
    entry: bytes        # the 0x2C sound entry (string and file fields are rewritten)
    wave_info: bytes    # 16 bytes: RWSD entry (0 here), track allocation, priorities
    param3d: bytes
    wave_info_ref: int
    groups: tuple[int, ...]


def _records_of(archive: BrsarArchive, index: int) -> tuple[bytes, bytes, bytes, int]:
    """A sound's 0x2C entry, the first 16 bytes of its sound info, its 3D block, and the
    reference word of its sound info."""
    data = archive.source
    info_base = archive.sections[1].offset + 8
    table = info_base + struct.unpack_from(">2I", data, info_base)[1]
    entry_at = info_base + struct.unpack_from(">2I", data, table + 4 + 8 * index)[1]
    ref3d = struct.unpack_from(">2I", data, entry_at + 0x0C)
    ref_info = struct.unpack_from(">2I", data, entry_at + 0x18)
    param3d = data[info_base + ref3d[1]:info_base + ref3d[1] + 12] if ref3d[0] else bytes(12)
    return (data[entry_at:entry_at + 0x2C], data[info_base + ref_info[1]:info_base + ref_info[1] + 16], param3d,
            ref_info[0])


def wave_spec(archive: BrsarArchive, template: int, name: str, header: bytes, wave_data: bytes) -> WaveSoundSpec:
    """A new wave sound copying sound ``template``'s player, volume, priorities and 3D settings and
    loaded with its file's groups; ``header``/``wave_data`` are its own one-entry RWSD."""
    if not 0 <= template < len(archive.sounds) or archive.sounds[template].sound_type != 3:
        raise BrsarError("The template must be a wave (RWSD) sound")
    entry, info, param3d, info_ref = _records_of(archive, template)
    info = bytearray(info)
    struct.pack_into(">I", info, 0, 0)  # the new RWSD's only entry
    groups = tuple(dict.fromkeys(group for group, _member in
                                 archive.files[archive.sounds[template].file_index].group_refs))
    if not groups:
        raise BrsarError("The template sound's file is in no group, so it is never loaded")
    return WaveSoundSpec(name, bytes(header), bytes(wave_data), entry, bytes(info), param3d, info_ref, groups)


def add_wave_sound(data: bytes, spec: WaveSoundSpec) -> bytes:
    """``data`` with a new wave sound ``spec.name`` playing entry 0 of its own embedded RWSD, a new
    file added to ``spec.groups``; FILE is laid out again (``replace_embedded_file``)."""
    def embedded_file(_rel, positions_at, _info):
        return (struct.pack(">IIi", len(spec.header), len(spec.wave_data), -1) + bytes(8) +
                struct.pack(">2I", _REF, positions_at))

    placeholder, sound_id, file_id = _append_sound(data, spec.name, spec.entry, spec.wave_info_ref,
                                                   spec.wave_info, spec.param3d, embedded_file, spec.groups)
    rebuilt = replace_embedded_file(read_brsar(placeholder), file_id, spec.header, spec.wave_data)
    checked = read_brsar(rebuilt)
    sound, file = checked.sounds[sound_id], checked.files[file_id]
    if (sound.name, sound.sound_type, sound.info_index, sound_id_of(rebuilt, spec.name), file.header,
            file.wave_data) != (spec.name, 3, 0, sound_id, spec.header, spec.wave_data):
        raise BrsarError("The rebuilt sound archive did not validate")
    return rebuilt


def added_sound_specs(current: bytes, vanilla: bytes) -> list[StreamSoundSpec | WaveSoundSpec]:
    """The sounds of ``current`` that ``vanilla`` lacks, as specs to add again (streams and the
    one-entry wave sounds the app adds)."""
    archive, original = read_brsar(current), read_brsar(vanilla)
    known = {sound.name for sound in original.sounds}
    specs = []
    for sound in archive.sounds:
        if sound.name in known:
            continue
        if sound.sound_type == 2 and sound.external_path:
            size = struct.unpack_from(">I", current, archive.files[sound.file_index].info_offset)[0]
            specs.append(stream_spec(archive, sound.index, sound.name, sound.external_path, size))
        elif sound.sound_type == 3:
            file = archive.files[sound.file_index]
            specs.append(wave_spec(archive, sound.index, sound.name, file.header, file.wave_data))
        else:
            raise BrsarError(f"{sound.name} is an added sound the app cannot rebuild")
    return specs


added_stream_specs = added_sound_specs  # the name the music code first used


def add_sound(data: bytes, spec: StreamSoundSpec | WaveSoundSpec) -> bytes:
    return add_wave_sound(data, spec) if isinstance(spec, WaveSoundSpec) else add_stream_sound(data, spec)


def remove_added_sound(current: bytes, vanilla: bytes, name: str) -> bytes:
    """``vanilla`` with every sound ``current`` added except ``name`` (retail sounds refuse)."""
    if name in {sound.name for sound in read_brsar(vanilla).sounds}:
        raise BrsarError(f"{name} is one of the game's own sounds")
    specs = added_sound_specs(current, vanilla)
    if name not in {spec.name for spec in specs}:
        raise BrsarError(f"{name} is not a sound the mod added")
    result = vanilla
    for spec in specs:
        if spec.name != name:
            result = add_sound(result, spec)
    return result

