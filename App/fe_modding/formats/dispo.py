"""Parse and edit a chapter's unit deployment ("dispo") data - who spawns
where, as what class, at what level, with what items and AI. This is the
file to edit for chapter design.

Getting one: each chapter's ``zmap/bmapNN/dispos.cmp`` is LZ10-compressed and
decompresses to a ``pack`` archive (same as map.cmp - see map_file.py's
docstring) holding four files, all loaded with the map: ``dispos_c.bin``,
``dispos_n.bin``, ``dispos_h.bin``, ``dispos_m.bin``. Section names carry
the file's letter (``bmap02_mikata_c``, ``bmap02_first_n``...). Scripts
deploy a section by name: ``_c`` sections are used on every difficulty, the
``_n``/``_h``/``_m`` trio goes to a helper that picks one by difficulty.

**File layout** (every offset below the header is stored ``HEADER_SIZE``-
relative), checked against all 158 vanilla variants:

- header, 0x20 bytes: file length, size of everything between the header
  and the end of the label pool, relocation count, section count, then four
  zero words;
- the sections back to back from 0x20, each a 4-byte header word followed by
  ``count`` 0x6C-byte unit records. The header word's bytes are the signed
  unit count, a mode byte (4 in vanilla), a tile-check byte (nonzero skips
  the "tile occupied" check) and the **group id**: an index into
  ``FE8Data.bin``'s ``GroupData`` army names (1 Crimean Army, 2 Daein Army,
  10 Greil Mercenaries...) stored on every unit the section deploys unless
  it is 0. A count-0 section whose word points at a label is a link (the
  first section of every file, ``<map>_date_<d>``, points at the first label);
- the label pool: NUL-terminated strings (PID_, JID_, IID_, SID_, SEQ_,
  MTYPE_...), padded to 4 bytes;
- the relocation table: the ascending list of every word position that holds
  a label pointer (``build_replacement_table()`` reproduces every vanilla
  table byte for byte);
- the section table, (address, name offset) pairs in an order of its own,
  followed by the section names.

**Unit record** - read by ``main.dol``'s ``read_dispos_unit_record``
(0x80107b54, see CHAPTER_DATA_NOTES 5.1) into the runtime
``UnitDeploymentRecord``, so every field below is confirmed from the reader;
the meanings of level, faction and the bonuses also match every vanilla file:

- 0 ``pid`` / 1 ``jid``: character and class (a null class uses the
  character's own). 2 is skipped by the reader.
- 3-10 ``item0``-``item7``: inventory. 40-47 ``item0_flag``-``item7_flag``:
  a flag per item, 1 on the items bosses drop.
- 11-15 ``skill0``-``skill4``: skills granted on top of the character's.
- 16-18: skipped by the reader.
- 19-26 ``bonus_hp`` ... ``bonus_res`` (signed): added to the stats.
- 27 ``laguz_gauge``: a nonzero value below 20 sets the starting gauge.
- 28-30 ``seq_attack``/``seq_move``/``seq_heal``, 31 ``mtype``: AI.
- 32/33 ``pos_x``/``pos_y``: the spawn tile in the map's full grid (the
  ``mapcapacity`` grid, border included). 34/35 ``pos2_x``/``pos2_y``: the
  tile the unit walks to after appearing, equal to the spawn on stationary
  units.
- 36 ``level``: when the class is the character's own and the character's
  base level is higher, the base level wins.
- 37 ``faction``: 0 player, 1 enemy, 2 ally/other, 3 partner (green AI
  allies).
- 38 ``flags``: 0x01 autolevel (class growths applied up to the level);
  0x02 hold position (the AI never moves the unit, it acts from its tile);
  0x04 group commander (the unit its group's army list and Charisma bonus
  refer to: Ike, bosses); 0x08 a reinforcement spawns even when the
  character is absent; 0x40 bridge-cover barrier (the unit cannot enter
  terrain 55 tiles; cleared on fliers); 0x10 the AI may use a Door Key,
  0x20 a Chest Key (thieves with ``SID_KEY0`` get both bits anyway). 0x80
  is not read.
- 39 ``ai_order``: enemy-phase turn order, lower acts first (0 on player
  units, 0-81 on enemies).

**Editing.** ``patch_unit_field()`` overwrites one field in place. Anything
structural (adding or removing units, new label strings, copying units
between variants) goes through the document model: ``parse_dispo()`` turns
the file into a ``DispoDocument`` whose pointer fields hold label *strings*,
and ``build_dispo()`` lays the whole file out again - label pool, relocation
table, header counts - so any label (any character, class, item...) can be
used. ``build_dispo(parse_dispo(data)) == data`` for every vanilla file.
Labels are looked up by name at runtime, so a new string is as valid as an
old one.
"""

from __future__ import annotations

import io
import struct
from dataclasses import dataclass, field as dataclass_field
from pathlib import Path
from typing import BinaryIO, Optional, Union

from .common import HEADER_SIZE, decode_str, read_cstring_table, read_section_table

RECORD_SIZE = 0x6C
RECORD_FORMAT = ">16I12b4I16b"

FIELD_NAMES: dict[int, str] = {
    0: "pid",
    1: "jid",
    **{3 + i: f"item{i}" for i in range(8)},
    **{11 + i: f"skill{i}" for i in range(5)},
    **{19 + i: f"bonus_{stat}" for i, stat in enumerate(("hp", "str", "mag", "skl", "spd", "lck", "def", "res"))},
    27: "laguz_gauge",
    28: "seq_attack",
    29: "seq_move",
    30: "seq_heal",
    31: "mtype",
    32: "pos_x",
    33: "pos_y",
    34: "pos2_x",
    35: "pos2_y",
    36: "level",
    37: "faction",
    38: "flags",
    39: "ai_order",
    **{40 + i: f"item{i}_flag" for i in range(8)},
}
#: Field index by name (``FIELD["level"] == 36``).
FIELD = {name: index for index, name in FIELD_NAMES.items()}
STAT_NAMES = ("hp", "str", "mag", "skl", "spd", "lck", "def", "res")
#: Field 37. 3 is the partner army (the green AI allies of the partner phase,
#: Tanith's pegasus knights in bmap24).
FACTION_NAMES = {0: "Player", 1: "Enemy", 2: "Ally", 3: "Partner"}
FLAG_AUTOLEVEL = 0x01
FLAG_HOLD_POSITION = 0x02
FLAG_COMMANDER = 0x04
FLAG_SPAWN_WHEN_ABSENT = 0x08
FLAG_AI_DOOR_KEY = 0x10
FLAG_AI_CHEST_KEY = 0x20
FLAG_BRIDGE_BARRIER = 0x40
#: Every bit of field 38: (mask, short label, what the game does with it).
FLAG_BITS = (
    (FLAG_AUTOLEVEL, "Autolevel", "Grows the unit from its base stats to its level with the class growths."),
    (FLAG_HOLD_POSITION, "Hold position", "The AI never moves the unit; it still attacks, heals and acts from its tile."),
    (FLAG_COMMANDER, "Group commander", "Leader of its army: the army list shows it and its Charisma helps its army."),
    (FLAG_SPAWN_WHEN_ABSENT, "Spawn if absent", "A reinforcement appears even when the character is not already in play."),
    (FLAG_AI_DOOR_KEY, "AI uses Door Key", "The AI may use a Door Key: the unit walks to the nearest door and opens it."),
    (FLAG_AI_CHEST_KEY, "AI uses Chest Key", "The AI may use a Chest Key on chests. Thieves with Lockpick (SID_KEY0) can do both without these bits."),
    (FLAG_BRIDGE_BARRIER, "Blocked by bridge cover", "Terrain 55 (bridge cover) costs 48 to enter. Cleared on fliers."),
    (0x80, "Bit 0x80", "Not read by the game."),
)
ITEM_FLAG_DROP = 0x01
ITEM_FLAG_RING = 0x02
#: Every used bit of fields 40-47.
ITEM_FLAG_BITS = (
    (ITEM_FLAG_DROP, "drop", "Dropped when the unit is defeated (one item per unit; cleared if it changes side)."),
    (ITEM_FLAG_RING, "ring", "Class ring: withheld in one game mode; with drop set it becomes the unit's only drop."),
)
#: One-line help for every field, shown by the editors.
FIELD_HELP = {
    0: "Character (PID_).", 1: "Class (JID_); 0 uses the character's own class.",
    2: "Not read by the game.",
    **{3 + i: "Inventory item (IID_)." for i in range(8)},
    **{11 + i: "Skill added on top of the character's and class's own (SID_)." for i in range(5)},
    16: "Not read by the game.", 17: "Not read by the game.", 18: "Not read by the game.",
    **{19 + i: f"Signed bonus added to {s.upper() if s != 'hp' else 'HP'}." for i, s in enumerate(STAT_NAMES)},
    27: "Starting laguz gauge; values 1-19 override the default.",
    28: "AI attack behaviour (SEQ_).", 29: "AI move behaviour (SEQ_).", 30: "AI heal behaviour (SEQ_).",
    31: "Movement AI (MTYPE_).",
    32: "Spawn tile X (full grid, border included).", 33: "Spawn tile Y.",
    34: "Tile the unit walks to after appearing, X.", 35: "Tile the unit walks to after appearing, Y.",
    36: "Level (the character's base level wins when the class is its own and higher).",
    37: "Army the unit joins.",
    38: "Deployment flags.",
    39: "Enemy-phase turn order: lower acts first.",
    **{40 + i: "Flags of the item in the same slot." for i in range(8)},
}
MAX_SECTION_UNITS = 127


def flag_names(value: int, bits=FLAG_BITS) -> list[str]:
    """The labels of the bits set in ``value``."""
    return [label for mask, label, _help in bits if value & mask]


def describe_field(index: int, value) -> str:
    """``value`` of field ``index`` as the editors show it."""
    if isinstance(value, str):
        return value
    if index == FIELD["faction"]:
        return f"{value} ({FACTION_NAMES[value]})" if value in FACTION_NAMES else str(value)
    if index == FIELD["flags"]:
        names = flag_names(value)
        return f"0x{value:02X} ({', '.join(names)})" if names else "0x00"
    if index >= FIELD["item0_flag"]:
        names = flag_names(value, ITEM_FLAG_BITS)
        return f"{value} ({', '.join(names)})" if names else str(value)
    return str(value)


def field_name(index: int) -> Optional[str]:
    """The name of one of the 48 unit-record fields, or None for the fields
    the game's reader skips (2, 16-18)."""
    return FIELD_NAMES.get(index)


Resolved = Union[int, bytes]


def _expand_format(fmt: str) -> list[tuple[int, int, bool]]:
    """('>16I12b4I16b') -> [(byte_offset, size, signed), ...] one entry per field."""
    sizes = {"b": 1, "B": 1, "h": 2, "H": 2, "i": 4, "I": 4}
    layout = []
    offset = 0
    i = 1 if fmt[:1] in ("<", ">", "=", "!", "@") else 0
    while i < len(fmt):
        count_str = ""
        while i < len(fmt) and fmt[i].isdigit():
            count_str += fmt[i]
            i += 1
        count = int(count_str) if count_str else 1
        type_char = fmt[i]
        i += 1
        size = sizes[type_char]
        signed = type_char.islower()
        for _ in range(count):
            layout.append((offset, size, signed))
            offset += size
    return layout


FIELD_LAYOUT = _expand_format(RECORD_FORMAT)
assert sum(size for _, size, _ in FIELD_LAYOUT) == RECORD_SIZE


@dataclass
class DispoField:
    index: int
    offset: int  # byte offset within the unit's record
    size: int  # 1 or 4
    signed: bool
    value: int  # raw numeric value as stored in the file
    label: Optional[bytes]  # resolved label, if value matched something in the label pool

    @property
    def display(self) -> str:
        return self.label.decode("ascii", errors="replace") if self.label is not None else str(self.value)


@dataclass
class DispoUnit:
    address: int  # absolute file offset of this record's start
    fields: list[DispoField] = dataclass_field(default_factory=list)


@dataclass
class DispoSection:
    name: str
    address: int
    count: int
    linked_label: Optional[bytes]  # set when count == 0: this section is an alias/redirect, not a unit list
    units: list[DispoUnit] = dataclass_field(default_factory=list)


@dataclass
class _DispoLayout:
    """The file-level boundaries read_dispo_file() needs before it can read
    any section - factored out so insert_unit() can re-derive the same
    boundaries from a file's raw bytes without duplicating this scan."""

    filesize: int
    label_map_start: int
    label_map_end: int
    label_map: dict[int, bytes]
    section_table_start: int


def _scan_layout(stream: BinaryIO) -> _DispoLayout:
    header = stream.read(8)
    filesize, label_map_end = struct.unpack(">II", header)  # the exact file length
    label_map_end += HEADER_SIZE

    stream.seek(HEADER_SIZE)
    (label_map_start,) = struct.unpack(">I", stream.read(4))
    label_map_start += HEADER_SIZE

    stream.seek(label_map_start)
    label_map = read_cstring_table(stream.read(label_map_end - label_map_start), base_offset=label_map_start - HEADER_SIZE)

    # Skip over a table of ascending pointers whose length isn't stored anywhere;
    # walk it until a value fails to be greater than the last one, which lands
    # right at the start of the real section table.
    stream.seek(label_map_end)
    last_value = -1
    next_value = struct.unpack(">I", stream.read(4))[0]
    position = label_map_end + 4
    while next_value > last_value:
        last_value = next_value
        next_value = struct.unpack(">I", stream.read(4))[0]
        position += 4
    section_table_start = position - 4

    return _DispoLayout(
        filesize=filesize,
        label_map_start=label_map_start,
        label_map_end=label_map_end,
        label_map=label_map,
        section_table_start=section_table_start,
    )


def read_dispo_file(stream: BinaryIO) -> list[DispoSection]:
    layout = _scan_layout(stream)
    sections = read_section_table(stream, layout.section_table_start, layout.filesize)
    return [_read_section(stream, address, name, layout.label_map) for address, name in sections]


def build_replacement_table(data: bytes, label_map: dict[int, bytes], label_map_start: int) -> bytes:
    """Regenerate the "replacement table" (see the module docstring) from
    scratch: the ascending, HEADER_SIZE-relative list of every 4-byte-
    aligned position between the header and the label pool whose stored
    value resolves to a real label. `label_map_start` is the absolute file
    offset the label pool begins at (same value read_dispo_file() computes
    from the header) - scanning stops there since positions inside the
    label pool are string bytes, not fields, and reinterpreting them as
    4-byte words isn't meaningful.

    Confirmed to exactly reproduce a real file's own stored table: run
    against bmap02/03/05's real dispos_n.bin (83/104/194 entries), the
    result is byte-for-byte identical to what's actually stored on disc.
    ``build_dispo()`` doesn't scan: it lists the positions it writes a label
    pointer to, so a byte field that happens to equal a label offset is never
    relocated. The tests use this scan to check that list.
    """
    positions = []
    for offset in range(HEADER_SIZE, label_map_start, 4):
        (value,) = struct.unpack(">I", data[offset : offset + 4])
        if value in label_map:
            positions.append(offset - HEADER_SIZE)
    return b"".join(struct.pack(">I", p) for p in positions)


def read_dispo_bytes(data: bytes) -> list[DispoSection]:
    return read_dispo_file(io.BytesIO(data))


def read_dispo_path(path: Path | str) -> list[DispoSection]:
    with open(path, "rb") as stream:
        return read_dispo_file(stream)


def _read_section(stream: BinaryIO, address: int, name: str, label_map: dict[int, bytes]) -> DispoSection:
    stream.seek(address)
    signed_count, b1, b2, b3 = struct.unpack(">bBBB", stream.read(4))

    linked_label = None
    if signed_count == 0:
        linked_label = label_map.get((b2 << 8) + b3)

    units = [_read_unit(stream, address + 4 + i * RECORD_SIZE, label_map) for i in range(max(signed_count, 0))]
    return DispoSection(name=name, address=address, count=signed_count, linked_label=linked_label, units=units)


def _read_unit(stream: BinaryIO, address: int, label_map: dict[int, bytes]) -> DispoUnit:
    stream.seek(address)
    raw = struct.unpack(RECORD_FORMAT, stream.read(RECORD_SIZE))
    fields = [
        DispoField(index=i, offset=offset, size=size, signed=signed, value=value, label=label_map.get(value))
        for i, (value, (offset, size, signed)) in enumerate(zip(raw, FIELD_LAYOUT))
    ]
    return DispoUnit(address=address, fields=fields)


def label_index(sections: list[DispoSection]) -> dict[bytes, int]:
    """Every label seen anywhere in this file, mapped to its raw (writable) value."""
    index: dict[bytes, int] = {}
    for section in sections:
        for unit in section.units:
            for f in unit.fields:
                if f.label is not None:
                    index[f.label] = f.value
    return index


def label_index_by_prefix(sections: list[DispoSection]) -> dict[str, dict[bytes, int]]:
    """label_index(), grouped by the label's prefix up to its first underscore
    (e.g. "PID", "JID", "IID", "SID", "SEQ", "MTYPE") - handy for narrowing a
    dropdown to "things that could plausibly go in this field"."""
    grouped: dict[str, dict[bytes, int]] = {}
    for label, value in label_index(sections).items():
        prefix = label.split(b"_", 1)[0].decode("ascii", errors="replace")
        grouped.setdefault(prefix, {})[label] = value
    return grouped


def _pack_format(size: int, signed: bool) -> str:
    if size == 4:
        return ">i" if signed else ">I"
    return ">b" if signed else ">B"


def patch_unit_field(data: bytes, unit: DispoUnit, field_index: int, new_value: int) -> bytes:
    """Return a copy of data with one field of one unit record overwritten.
    Everything else in the file - including every other unit - is untouched."""
    return patch_unit_fields(data, unit, {field_index: new_value})


def patch_unit_fields(data: bytes, unit: DispoUnit, edits: dict[int, int]) -> bytes:
    out = bytearray(data)
    for field_index, new_value in edits.items():
        f = unit.fields[field_index]
        struct.pack_into(_pack_format(f.size, f.signed), out, unit.address + f.offset, new_value)
    return bytes(out)


def insert_unit(data: bytes, sections: list[DispoSection], section: DispoSection, field_values: list[int]) -> bytes:
    """Return a copy of data with one unit appended to ``section``.
    ``field_values`` is 48 raw ints as stored in *this* file (copy an
    existing unit's ``[f.value for f in unit.fields]``); pointer fields are
    resolved against the file's own label pool. ``sections`` is the parse of
    ``data`` and only needed for the checks. Kept for the raw-value callers;
    new code edits a ``DispoDocument`` directly."""
    if len(field_values) != len(FIELD_LAYOUT):
        raise ValueError(f"field_values must have {len(FIELD_LAYOUT)} entries (one per record field), got {len(field_values)}")
    if section.count + 1 > MAX_SECTION_UNITS:
        raise ValueError(f"Section {section.name!r} already has the maximum {MAX_SECTION_UNITS} units")
    doc = parse_dispo(data)
    by_offset = {offset: label for label, offset in doc.label_offsets().items()}
    values = [by_offset.get(v, v) if i in POINTER_FIELDS and v else v for i, v in enumerate(field_values)]
    add_unit(doc, section.name, values)
    return build_dispo(doc)


# -- document model ------------------------------------------------------------------

#: Record fields that hold a label pointer (or 0): every 4-byte field.
POINTER_FIELDS = frozenset(i for i, (_offset, size, _signed) in enumerate(FIELD_LAYOUT) if size == 4)
#: A field value: a label string for a pointer to a label, else the raw number.
Value = Union[int, str]
_LABEL_CODEC = "latin-1"  # byte-exact for any label; every vanilla label is ASCII
DIFFICULTY_LETTERS = "nhmc"


@dataclass
class DocSection:
    """One section of a ``DispoDocument``. ``header`` is the section's first
    word: a label string on a link section (count 0), else the raw word,
    whose top byte ``build_dispo()`` replaces with the unit count."""

    name: str
    header: Value
    units: list[list[Value]] = dataclass_field(default_factory=list)

    @property
    def is_link(self) -> bool:
        return isinstance(self.header, str)


@dataclass
class DispoDocument:
    """A whole dispos variant with its pointers resolved to label strings;
    edit ``sections[...].units`` freely and write it with ``build_dispo()``."""

    sections: list[DocSection]  # file order
    table_order: list[int]  # section-table order, as indices into ``sections``
    name_offsets: list[int]  # one per section-table entry
    names_blob: bytes
    labels: list[str]  # label pool order
    header_tail: bytes  # header words 4-7, kept as they are

    def section(self, name: str) -> Optional[DocSection]:
        return next((s for s in self.sections if s.name == name), None)

    def label_offsets(self) -> dict[str, int]:
        """The HEADER_SIZE-relative position of every pool label as this
        document's sections and labels lay out now."""
        offsets, position = {}, self._pool_start() - HEADER_SIZE
        for label in self.labels:
            offsets.setdefault(label, position)
            position += len(label.encode(_LABEL_CODEC)) + 1
        return offsets

    def _pool_start(self) -> int:
        return HEADER_SIZE + sum(4 + RECORD_SIZE * len(s.units) for s in self.sections)


def parse_dispo(data: bytes) -> DispoDocument:
    """Read one dispos variant into a ``DispoDocument``."""
    layout = _scan_layout(io.BytesIO(data))
    section_count = struct.unpack_from(">I", data, 12)[0]
    table_start = layout.section_table_start
    entries = [struct.unpack_from(">II", data, table_start + 8 * i) for i in range(section_count)]
    names_start = table_start + 8 * section_count
    names = read_cstring_table(data[names_start:])

    order = sorted(range(section_count), key=lambda i: entries[i][0])
    position_of = {entry_index: position for position, entry_index in enumerate(order)}

    pool_start = HEADER_SIZE
    for i in order:
        address = entries[i][0] + HEADER_SIZE
        if address != pool_start:
            raise ValueError(f"Section at {address:#x} doesn't follow the previous one ({pool_start:#x})")
        count = struct.unpack_from(">b", data, address)[0]
        pool_start = address + 4 + max(count, 0) * RECORD_SIZE
    labels, by_offset, position = [], {}, pool_start - HEADER_SIZE
    for raw in data[pool_start : layout.label_map_end].split(b"\x00"):
        if raw:
            label = raw.decode(_LABEL_CODEC)
            labels.append(label)
            by_offset[position] = label
        position += len(raw) + 1

    sections = []
    for i in order:
        address = entries[i][0] + HEADER_SIZE
        (word,) = struct.unpack_from(">I", data, address)
        count = struct.unpack_from(">b", data, address)[0]
        header: Value = by_offset.get(word, word) if count == 0 else word
        units = []
        for u in range(max(count, 0)):
            raw_values = struct.unpack_from(RECORD_FORMAT, data, address + 4 + u * RECORD_SIZE)
            units.append([by_offset.get(v, v) if f in POINTER_FIELDS and v else v for f, v in enumerate(raw_values)])
        sections.append(DocSection(name=decode_str(names.get(entries[i][1], b"")), header=header, units=units))

    return DispoDocument(
        sections=sections,
        table_order=[position_of[i] for i in range(section_count)],
        name_offsets=[entry[1] for entry in entries],
        names_blob=data[names_start:],
        labels=labels,
        header_tail=data[0x10:HEADER_SIZE],
    )


def build_dispo(doc: DispoDocument) -> bytes:
    """Lay a ``DispoDocument`` out as a dispos variant. The label pool keeps
    the document's labels that are still used, in order, followed by the new
    ones in order of first use; the relocation table and header counts are
    rebuilt."""
    used: list[str] = []
    seen: set[str] = set()

    def use(value: Value) -> None:
        if isinstance(value, str) and value not in seen:
            seen.add(value)
            used.append(value)

    for section in doc.sections:
        use(section.header)
        for unit in section.units:
            if len(unit) != len(FIELD_LAYOUT):
                raise ValueError(f"A unit of {section.name!r} has {len(unit)} fields, not {len(FIELD_LAYOUT)}")
            for value in unit:
                use(value)
    pool_labels = [label for label in doc.labels if label in seen]
    in_pool = set(pool_labels)
    pool_labels += [label for label in used if label not in in_pool]

    pool_start = doc._pool_start()
    offsets, position = {}, pool_start - HEADER_SIZE
    pool = bytearray()
    for label in pool_labels:
        offsets[label] = position
        raw = label.encode(_LABEL_CODEC) + b"\x00"
        pool += raw
        position += len(raw)
    pool += bytes(-len(pool) % 4)

    body = bytearray()
    relocations: list[int] = []
    addresses: list[int] = []
    for section in doc.sections:
        address = HEADER_SIZE + len(body)
        addresses.append(address)
        if section.is_link:
            if section.units:
                raise ValueError(f"Section {section.name!r} is a link; it can't hold units")
            relocations.append(address - HEADER_SIZE)
            body += struct.pack(">I", offsets[section.header])
            continue
        if len(section.units) > MAX_SECTION_UNITS:
            raise ValueError(f"Section {section.name!r} has more than {MAX_SECTION_UNITS} units")
        body += struct.pack(">I", (section.header & 0x00FFFFFF) | (len(section.units) << 24))
        for unit in section.units:
            record = HEADER_SIZE + len(body)
            raw_values = []
            for f, value in enumerate(unit):
                if isinstance(value, str):
                    relocations.append(record + FIELD_LAYOUT[f][0] - HEADER_SIZE)
                    value = offsets[value]
                raw_values.append(value)
            body += struct.pack(RECORD_FORMAT, *raw_values)

    pool_end = pool_start + len(pool)
    table = bytearray()
    for entry_index, section_index in enumerate(doc.table_order):
        table += struct.pack(">II", addresses[section_index] - HEADER_SIZE, doc.name_offsets[entry_index])
    tail = b"".join(struct.pack(">I", r) for r in relocations) + bytes(table) + doc.names_blob
    total = pool_end + len(tail)
    header = struct.pack(">4I", total, pool_end - HEADER_SIZE, len(relocations), len(doc.table_order)) + doc.header_tail
    return header + bytes(body) + bytes(pool) + tail


def new_unit_values() -> list[Value]:
    """A blank unit: every field 0 but the bridge-cover barrier flag, which
    every vanilla non-flying unit has."""
    values: list[Value] = [0] * len(FIELD_LAYOUT)
    values[FIELD["flags"]] = FLAG_BRIDGE_BARRIER
    return values


def add_unit(doc: DispoDocument, section_name: str, values: list[Value]) -> int:
    """Append a unit to a section; returns its index there."""
    section = doc.section(section_name)
    if section is None:
        raise ValueError(f"No section {section_name!r}")
    if section.is_link:
        raise ValueError(f"Section {section_name!r} is a link; it can't hold units")
    if len(section.units) >= MAX_SECTION_UNITS:
        raise ValueError(f"Section {section_name!r} already has the maximum {MAX_SECTION_UNITS} units")
    if len(values) != len(FIELD_LAYOUT):
        raise ValueError(f"A unit has {len(FIELD_LAYOUT)} fields, got {len(values)}")
    section.units.append(list(values))
    return len(section.units) - 1


def remove_unit(doc: DispoDocument, section_name: str, index: int) -> list[Value]:
    section = doc.section(section_name)
    if section is None or not 0 <= index < len(section.units):
        raise ValueError(f"No unit {index} in section {section_name!r}")
    return section.units.pop(index)


def move_unit(unit: list[Value], x: int, y: int) -> None:
    """Put a unit's spawn on (x, y); its second tile moves by the same
    amount, so a stationary unit stays stationary."""
    dx, dy = x - int(unit[FIELD["pos_x"]]), y - int(unit[FIELD["pos_y"]])
    unit[FIELD["pos_x"]], unit[FIELD["pos_y"]] = x, y
    unit[FIELD["pos2_x"]] = max(-128, min(127, int(unit[FIELD["pos2_x"]]) + dx))
    unit[FIELD["pos2_y"]] = max(-128, min(127, int(unit[FIELD["pos2_y"]]) + dy))


@dataclass
class SectionHeader:
    """A unit section's header bytes after the unit count: ``mode`` (4 on
    every vanilla section), ``occupied_ok`` (nonzero places units even on
    occupied tiles) and ``group``, the army (``GroupData`` index, 0 keeps
    the unit's current army)."""

    mode: int
    occupied_ok: int
    group: int


def section_header(section: DocSection) -> SectionHeader:
    word = section.header if isinstance(section.header, int) else 0
    return SectionHeader((word >> 16) & 0xFF, (word >> 8) & 0xFF, word & 0xFF)


def set_section_header(section: DocSection, header: SectionHeader) -> None:
    """Store ``header`` in a unit section (the count byte is rebuilt on save)."""
    if section.is_link:
        raise ValueError(f"{section.name} is a link, not a unit section")
    for value in (header.mode, header.occupied_ok, header.group):
        if not 0 <= value <= 0xFF:
            raise ValueError(f"header byte {value} out of range 0..255")
    section.header = (section.header & 0xFF000000) | (header.mode << 16) | (header.occupied_ok << 8) | header.group


def _set_section_table(doc: DispoDocument, table_sections: list[DocSection]) -> None:
    """Rewrite the section table to list ``table_sections`` (every section of
    ``doc``) in that order, with the names laid out afresh in the same order."""
    names, offsets = bytearray(), []
    for section in table_sections:
        offsets.append(len(names))
        names += section.name.encode(_LABEL_CODEC) + b"\x00"
    position = {id(section): i for i, section in enumerate(doc.sections)}
    doc.table_order = [position[id(section)] for section in table_sections]
    doc.name_offsets = offsets
    doc.names_blob = bytes(names)


def add_section(doc: DispoDocument, name: str, header: Optional[SectionHeader] = None) -> DocSection:
    """Append an empty unit section called ``name`` (mode 4, no army unless
    ``header`` says otherwise). The section table stays sorted by name when
    it was; otherwise the new entry goes last."""
    try:
        raw_name = name.encode("ascii")
    except UnicodeEncodeError:
        raise ValueError("A section name must be ASCII") from None
    if not name or b"\x00" in raw_name or any(c.isspace() for c in name):
        raise ValueError("A section name must be non-empty, with no spaces")
    if doc.section(name) is not None:
        raise ValueError(f"There is already a section {name!r}")
    table = [doc.sections[i] for i in doc.table_order]
    was_sorted = [s.name.encode(_LABEL_CODEC) for s in table] == sorted(s.name.encode(_LABEL_CODEC) for s in table)
    section = DocSection(name=name, header=0)
    set_section_header(section, header or SectionHeader(4, 0, 0))
    doc.sections.append(section)
    if was_sorted:
        at = next((i for i, s in enumerate(table) if s.name.encode(_LABEL_CODEC) > raw_name), len(table))
        table.insert(at, section)
    else:
        table.append(section)
    _set_section_table(doc, table)
    return section


def remove_section(doc: DispoDocument, name: str) -> DocSection:
    """Remove a unit section, its units included; link sections stay."""
    section = doc.section(name)
    if section is None:
        raise ValueError(f"No section {name!r}")
    if section.is_link:
        raise ValueError(f"Section {name!r} is a link the game needs; it can't be removed")
    table = [doc.sections[i] for i in doc.table_order if doc.sections[i] is not section]
    doc.sections.remove(section)
    _set_section_table(doc, table)
    return section


def section_base(name: str) -> str:
    """A section's name without its difficulty letter (``bmap02_first_n`` ->
    ``bmap02_first``), the part the variants share."""
    head, _, letter = name.rpartition("_")
    return head if head and len(letter) == 1 and letter in DIFFICULTY_LETTERS else name


def counterpart_section(doc: DispoDocument, section_name: str) -> Optional[DocSection]:
    """The section of ``doc`` (another variant) that matches ``section_name``."""
    base = section_base(section_name)
    return next((s for s in doc.sections if section_base(s.name) == base), None)


def find_counterpart_unit(doc: DispoDocument, section_name: str, unit: list[Value], index_hint: Optional[int] = None) -> Optional[int]:
    """The index, in ``doc``'s matching section, of the same unit as
    ``unit``: the unit with the same character, preferring the same index
    and then the same spawn tile when the character appears several times
    (generic enemies)."""
    section = counterpart_section(doc, section_name)
    if section is None:
        return None
    pid = unit[FIELD["pid"]]
    same = [i for i, other in enumerate(section.units) if other[FIELD["pid"]] == pid]
    if not same:
        return None
    if len(same) == 1:
        return same[0]
    if index_hint in same:
        return index_hint
    tile = (unit[FIELD["pos_x"]], unit[FIELD["pos_y"]])
    return next((i for i in same if (section.units[i][FIELD["pos_x"]], section.units[i][FIELD["pos_y"]]) == tile), same[0])


def labels_by_prefix(docs) -> dict[str, list[str]]:
    """Every label the documents use, grouped by prefix (``SEQ``, ``MTYPE``...)."""
    grouped: dict[str, set[str]] = {}
    for doc in docs:
        for label in doc.labels:
            grouped.setdefault(label.split("_", 1)[0], set()).add(label)
    return {prefix: sorted(labels) for prefix, labels in grouped.items()}


def rename_chapter_sections(data: bytes, old_number: str, new_number: str) -> bytes:
    """Return a copy of one dispo variant's bytes (e.g. a dispos_n.bin
    pulled out of the pak - same granularity insert_unit() works at) with
    every section name containing "bmap<old_number>" rewritten to
    "bmap<new_number>" - e.g. renumbering bmap01's dispos_n.bin for reuse as
    a new chapter's (see chapters.duplicate_chapter()).

    Real chapter numbers are always 2 digits, so this only supports a
    same-length rename: a same-length substring swap changes no byte count
    anywhere in the file, so it's a trivial whole-buffer replace - nothing
    like insert_unit()'s label-pool-shift machinery is needed. A
    different-length rename would need actually resizing the section-names
    blob (see common.py's read_section_table() for where that lives), which
    isn't attempted here - raise rather than silently leave it renamed
    inconsistently.
    """
    if len(old_number) != len(new_number):
        raise ValueError(
            f"Chapter numbers must be the same length to rename in place ({old_number!r} vs {new_number!r})."
        )
    old_bytes = f"bmap{old_number}".encode("ascii")
    new_bytes = f"bmap{new_number}".encode("ascii")
    return data.replace(old_bytes, new_bytes)
