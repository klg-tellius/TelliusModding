"""Radiant Dawn's game database, ``FE10Data.cms`` (LZ10 around the same relocatable container as
Path of Radiance's ``FE8Data.bin``): the character, class, item and skill tables.

The container layer (header, pointer list, symbols, string pool) is :mod:`fe8data`'s; this module
holds the Radiant Dawn record layouts on top of it. Unlike Path of Radiance, three of the four tables
have **variable-size records**: a count byte in the record says how many label pointers follow
(a character's skills, a class's skills and sound classes, an item's attributes and
effectivenesses, an item's optional stat-bonus block). Each table is a count word (the word its
symbol points at) followed by the records back to back; walking them with the layouts below ends
exactly at the next table's symbol for every table of the retail US file, which is the check the
layouts are held to (``test_fe10data``).

Field names follow what the retail data shows. Fields whose meaning is not established yet keep a
neutral name (``unknown_*``) and are still editable as numbers; ``FIELD_NOTES`` says what is known.

Editing:

* :func:`patch_field` writes one scalar or label field in place (a label missing from the file is
  added to the string pool; a null pointer leaves the container's pointer list).
* :func:`set_list` replaces one of a record's label lists. A character, class or item list lives
  inside the record, so a longer or shorter list moves everything after it: every listed pointer
  field, every pointer target and every symbol behind the edit shift with it (:func:`insert_bytes` /
  :func:`delete_bytes`). A skill's two condition lists live outside the record; a new list is
  appended to the data section and the skill repointed.
* :func:`set_item_bonuses` adds, changes or removes an item's stat-bonus block.

All offsets in this module are absolute file offsets of the decompressed container; pointer values
are data-relative (``HEADER_SIZE`` less), as everywhere in :mod:`fe8data`.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass, field
from typing import Optional, Sequence

from . import fe8data
from .fe8data import HEADER_SIZE

STAT_NAMES = ("HP", "Str", "Mag", "Skl", "Spd", "Lck", "Def", "Res")
#: An item's stat-bonus block: the eight stats, then movement and weight, then two unused bytes.
BONUS_NAMES = STAT_NAMES + ("Mov", "Wt")
BONUS_BLOCK_SIZE = 12

KINDS = ("character", "class", "item", "skill")
SYMBOLS = {"character": "PersonData", "class": "JobData", "item": "ItemData", "skill": "SkillData"}
#: The table that follows each one in the retail file (where a walk must end).
NEXT_SYMBOL = {"character": "JobData", "class": "ItemData", "item": "SkillData"}
ID_PREFIX = {"character": "PID_", "class": "JID_", "item": "IID_", "skill": "SID_"}
SKILL_RECORD_SIZE = 0x2C


@dataclass(frozen=True)
class FieldDef:
    key: str
    label: str
    kind: str        # "label", "u8", "s8", "u16", "u32"
    group: str = ""  # form section
    offset: int = -1  # record-relative offset (fixed-size tables; -1: fields follow each other)


def _labels(*pairs: tuple[str, str], group: str = "") -> list[FieldDef]:
    return [FieldDef(key, label, "label", group) for key, label in pairs]


def _bytes(kind: str, names: Sequence[tuple[str, str]], group: str = "") -> list[FieldDef]:
    return [FieldDef(key, label, kind, group) for key, label in names]


def _stats(prefix: str, kind: str, group: str, names: Sequence[str] = STAT_NAMES) -> list[FieldDef]:
    return [FieldDef(f"{prefix}_{name.lower()}", name, kind, group) for name in names]


# -- character (PersonData) ------------------------------------------------------------------------
# +0x00 skill count, +0x01 unknown, +0x02 level, +0x03 sex; 7 labels; skills; 5 labels; 28 bytes.
CHARACTER_HEAD = _bytes("u8", (("unknown_01", "Unknown +0x01"), ("level", "Level"), ("sex", "Sex (1 = female)")), "Unit")
CHARACTER_LABELS = _labels(("pid", "ID"), ("mpid", "Name key"), ("mnpid", "Help key"), ("fid", "Portrait"),
                           ("jid", "Class"), ("affinity", "Affinity"), ("weapon_ranks", "Weapon ranks"),
                           group="Identity")
CHARACTER_AFTER_SKILLS = _labels(("unknown_label", "Unknown label"), ("aid_1", "Animation 1"),
                                 ("aid_2", "Animation 2"), ("aid_3", "Animation 3"), ("aid_4", "Animation 4"),
                                 group="Animations")
CHARACTER_TAIL = (
    _bytes("u8", (("biorhythm", "Biorhythm type"), ("unknown_t1", "Unknown tail +1"),
                  ("unknown_t2", "Unknown tail +2"), ("unknown_t3", "Unknown tail +3 (bit mask)"),
                  ("authority", "Authority stars")), "Unit")
    + _bytes("s8", (("gauge_turn", "Gauge per turn"), ("gauge_battle", "Gauge per battle"),
                    ("gauge_turn_transformed", "Gauge per turn (transformed)"),
                    ("gauge_battle_transformed", "Gauge per battle (transformed)")), "Laguz gauge")
    + _stats("bonus", "s8", "Stats over class bases")
    + _bytes("s8", (("bonus_weight", "Wt"),), "Stats over class bases")
    + _bytes("u8", (("unknown_t18", "Unknown tail +18"),), "Unit")
    + _stats("growth", "u8", "Growth rates (%)")
    + _bytes("u8", (("unknown_t27", "Unknown tail +27"),), "Unit")
)
CHARACTER_TAIL_SIZE = 28

# -- class (JobData) -------------------------------------------------------------------------------
# 11 labels; 12 bytes (+5 skill count, +6 sound-class count); a label; skills; a label; sound
# classes; 32 bytes (caps, bases, growths, promotion gains).
CLASS_LABELS = _labels(("jid", "ID"), ("mjid", "Name key"), ("japanese_name", "Japanese name"),
                       ("help", "Help key"), ("demotes_to", "Previous tier"), ("promotes_to", "Promotes to"),
                       ("other_form", "Other form"), ("innate_weapon", "Innate weapon"),
                       ("aid", "Default animation"), ("weapon_ranks", "Starting weapon ranks"),
                       ("max_weapon_ranks", "Maximum weapon ranks"), group="Identity")
CLASS_FIXED = _bytes("u8", (
    ("unknown_00", "Unknown +0"), ("unknown_01", "Unknown +1"), ("unknown_02", "Unknown +2"),
    ("unknown_03", "Unknown +3"), ("unknown_04", "Unknown +4"), ("skill_count", "Skill count"),
    ("sound_count", "Sound class count"), ("unknown_07", "Unknown +7"), ("unknown_08", "Unknown +8"),
    ("movement", "Movement"), ("skill_capacity", "Skill capacity"), ("weight", "Weight")), "Class")
CLASS_BEFORE_SKILLS = _labels(("unknown_label", "Unknown label"), group="Class")
CLASS_AFTER_SKILLS = _labels(("extra_skill", "Extra skill"), group="Class")
CLASS_TAIL = (_stats("cap", "u8", "Stat caps") + _stats("base", "u8", "Base stats")
              + _stats("growth", "u8", "Growth rates (%)") + _stats("promotion", "u8", "Promotion gains"))
CLASS_TAIL_SIZE = 32
CLASS_FIXED_SIZE = 12

# -- item (ItemData) -------------------------------------------------------------------------------
# 9 labels; 20 bytes (+17 attribute count, +18 effectiveness count, +19 bonus-block count);
# attributes; effectivenesses; 0 or 1 stat-bonus block of 12 bytes.
ITEM_LABELS = _labels(("iid", "ID"), ("miid", "Name key"), ("help", "Help key"), ("weapon_type", "Weapon type"),
                      ("display_type", "Displayed type"), ("rank", "Weapon rank"), ("effect", "Effect"),
                      ("effect_2", "Effect 2"), ("effect_3", "Effect 3"), group="Identity")
ITEM_FIXED = (
    _bytes("u16", (("icon", "Icon"), ("price", "Price per use")), "Item")
    + _bytes("u8", (("might", "Might"), ("hit", "Hit"), ("crit", "Critical"), ("weight", "Weight"),
                    ("uses", "Uses"), ("wexp", "Weapon experience"), ("range_min", "Minimum range"),
                    ("range_max", "Maximum range"), ("unknown_12", "Unknown +12"),
                    ("unknown_13", "Unknown +13"), ("unknown_14", "Unknown +14"), ("unknown_15", "Unknown +15"),
                    ("unknown_16", "Unknown +16"), ("attribute_count", "Attribute count"),
                    ("effective_count", "Effectiveness count"), ("bonus_count", "Bonus blocks")), "Item")
)
ITEM_FIXED_SIZE = 20

# -- skill (SkillData) -----------------------------------------------------------------------------
SKILL_LABELS = _labels(("sid", "ID"), ("msid", "Name key"), ("help", "Help key"), ("help_2", "Help key 2"),
                       ("effect", "Effect"), ("effect_2", "Effect 2"), ("item", "Scroll item"), group="Identity")
SKILL_FIXED = _bytes("u8", (("number", "Number"), ("unknown_1d", "Unknown +0x1D"), ("capacity", "Capacity"),
                            ("icon", "Icon"), ("condition_count", "Condition count"),
                            ("requirement_count", "Requirement count"), ("unknown_22", "Unknown +0x22"),
                            ("unknown_23", "Unknown +0x23")), "Skill")

#: Lists per kind: key -> label shown in the editor.
LISTS = {
    "character": {"skills": "Skills"},
    "class": {"skills": "Skills", "sounds": "Sound classes"},
    "item": {"attributes": "Attributes", "effective": "Effective against"},
    "skill": {"conditions": "Conditions", "requirements": "Requirements"},
}
#: Fields a list or block owns (kept in step by set_list / set_item_bonuses, not edited directly).
COUNT_FIELDS = {"skill_count", "sound_count", "attribute_count", "effective_count", "bonus_count",
                "condition_count", "requirement_count"}

FIELD_NOTES = {
    "biorhythm": "0-9 picks a biorhythm curve; 255 has none.",
    "unknown_t3": "A bit mask (0, 3, 7, 15 or 31), set on royals and a few others.",
    "authority": "0-5 authority stars.",
    "gauge_turn": "Laguz gauge change per turn and per battle, untransformed and transformed.",
    "skill_capacity": "Retail values are 15 (first tier), 30 (second) and 60 (third), more for laguz.",
    "capacity": "Capacity cost of the skill (probable: occult skills read 30, most others 10-20).",
    "conditions": "Mode 1 entries: who cannot have the skill (skills, classes, characters).",
    "requirements": "Mode 0 entries: which class types (SFXC_*) can have the skill.",
}


@dataclass
class Record:
    """One decoded record. ``offsets`` maps each field to its absolute file offset; ``lists`` maps
    each list to its labels (skill conditions: ``(mode, label)`` pairs)."""
    kind: str
    index: int
    start: int
    end: int
    values: dict = field(default_factory=dict)
    offsets: dict = field(default_factory=dict)
    lists: dict = field(default_factory=dict)
    bonuses: Optional[list] = None

    @property
    def id(self) -> Optional[str]:
        key = ID_FIELD.get(self.kind)
        return self.values.get(key) if key else None


@dataclass
class Fe10Data:
    tables: dict

    def table(self, kind: str) -> list:
        return self.tables[kind]

    @property
    def characters(self) -> list:
        return self.tables["character"]

    @property
    def classes(self) -> list:
        return self.tables["class"]

    @property
    def items(self) -> list:
        return self.tables["item"]

    @property
    def skills(self) -> list:
        return self.tables["skill"]


# -- reading ---------------------------------------------------------------------------------------

def _u32(data: bytes, offset: int) -> int:
    return struct.unpack_from(">I", data, offset)[0]


def resolve(data: bytes, ptr: int) -> Optional[str]:
    """The NUL-terminated string a pointer names (ASCII or Shift-JIS), None for a null pointer."""
    if not ptr:
        return None
    addr = ptr + HEADER_SIZE
    if not 0 <= addr < len(data):
        return None
    end = data.find(b"\x00", addr)
    if end == -1:
        return None
    raw = data[addr:end]
    try:
        return raw.decode("ascii")
    except UnicodeDecodeError:
        return raw.decode("shift_jis", errors="replace")


def table_start(data: bytes, kind: str) -> int:
    """Absolute offset of the table's count word (where its symbol points)."""
    return fe8data.section_start(data, SYMBOLS[kind])


def is_fe10data(data: bytes) -> bool:
    """Whether ``data`` is a decompressed Radiant Dawn database: its character records, walked with
    the Radiant Dawn layout, end exactly where JobData starts (Path of Radiance's fixed 0x54-byte
    characters never do)."""
    try:
        characters = _walk(data, "character")
        return bool(characters) and characters[-1].end == table_start(data, "class")
    except (struct.error, ValueError, IndexError, KeyError):
        return False


def _read_fields(data: bytes, record: Record, defs: Sequence[FieldDef], at: int) -> int:
    for d in defs:
        record.offsets[d.key] = at
        if d.offset >= 0:
            at = record.start + d.offset
            record.offsets[d.key] = at
        if d.kind == "label":
            record.values[d.key] = resolve(data, _u32(data, at))
            at += 4
        elif d.kind == "u32":
            record.values[d.key] = _u32(data, at)
            at += 4
        elif d.kind == "u16":
            record.values[d.key] = struct.unpack_from(">H", data, at)[0]
            at += 2
        elif d.kind == "s8":
            record.values[d.key] = struct.unpack_from(">b", data, at)[0]
            at += 1
        else:
            record.values[d.key] = data[at]
            at += 1
    return at


def _read_label_list(data: bytes, record: Record, key: str, at: int, count: int) -> int:
    record.offsets[key] = at
    record.lists[key] = [resolve(data, _u32(data, at + 4 * i)) for i in range(count)]
    return at + 4 * count


def _walk(data: bytes, kind: str) -> list[Record]:
    if kind == "skill":
        return _read_skills(data)
    if kind in FIXED_TABLES:
        return _read_fixed(data, kind)
    if kind == "support":
        return _read_supports(data)
    start = table_start(data, kind)
    count = _u32(data, start)
    at = start + 4
    records = []
    reader = {"character": _read_character, "class": _read_class, "item": _read_item}[kind]
    for i in range(count):
        record = reader(data, i, at)
        records.append(record)
        at = record.end
    return records


def _read_character(data: bytes, index: int, at: int) -> Record:
    r = Record("character", index, at, at)
    count = data[at]
    r.offsets["skill_count"], r.values["skill_count"] = at, count
    pos = _read_fields(data, r, CHARACTER_HEAD, at + 1)
    pos = _read_fields(data, r, CHARACTER_LABELS, pos)
    pos = _read_label_list(data, r, "skills", pos, count)
    pos = _read_fields(data, r, CHARACTER_AFTER_SKILLS, pos)
    pos = _read_fields(data, r, CHARACTER_TAIL, pos)
    r.end = pos
    return r


def _read_class(data: bytes, index: int, at: int) -> Record:
    r = Record("class", index, at, at)
    pos = _read_fields(data, r, CLASS_LABELS, at)
    pos = _read_fields(data, r, CLASS_FIXED, pos)
    pos = _read_fields(data, r, CLASS_BEFORE_SKILLS, pos)
    pos = _read_label_list(data, r, "skills", pos, r.values["skill_count"])
    pos = _read_fields(data, r, CLASS_AFTER_SKILLS, pos)
    pos = _read_label_list(data, r, "sounds", pos, r.values["sound_count"])
    pos = _read_fields(data, r, CLASS_TAIL, pos)
    r.end = pos
    return r


def _read_item(data: bytes, index: int, at: int) -> Record:
    r = Record("item", index, at, at)
    pos = _read_fields(data, r, ITEM_LABELS, at)
    pos = _read_fields(data, r, ITEM_FIXED, pos)
    pos = _read_label_list(data, r, "attributes", pos, r.values["attribute_count"])
    pos = _read_label_list(data, r, "effective", pos, r.values["effective_count"])
    r.offsets["bonuses"] = pos
    if r.values["bonus_count"]:
        r.bonuses = [struct.unpack_from(">b", data, pos + i)[0] for i in range(len(BONUS_NAMES))]
        pos += BONUS_BLOCK_SIZE * r.values["bonus_count"]
    r.end = pos
    return r


def _read_condition_list(data: bytes, ptr: int, count: int) -> list[tuple[int, Optional[str]]]:
    if not ptr or not count:
        return []
    at = ptr + HEADER_SIZE
    return [(data[at + 8 * i], resolve(data, _u32(data, at + 8 * i + 4))) for i in range(count)]


def _read_skills(data: bytes) -> list[Record]:
    start = table_start(data, "skill")
    count = _u32(data, start)
    records = []
    for i in range(count):
        at = start + 4 + i * SKILL_RECORD_SIZE
        r = Record("skill", i, at, at + SKILL_RECORD_SIZE)
        pos = _read_fields(data, r, SKILL_LABELS, at)
        _read_fields(data, r, SKILL_FIXED, pos)
        for key, slot, count_key in (("conditions", 0x24, "condition_count"),
                                     ("requirements", 0x28, "requirement_count")):
            r.offsets[key] = at + slot
            r.lists[key] = _read_condition_list(data, _u32(data, at + slot), r.values[count_key])
        records.append(r)
    return records


def read_fe10data(data: bytes) -> Fe10Data:
    return Fe10Data({kind: _walk(data, kind) for kind in ALL_KINDS})


def read_table(data: bytes, kind: str) -> list[Record]:
    return _walk(data, kind)


def record(data: bytes, kind: str, index: int) -> Record:
    records = _walk(data, kind)
    if not 0 <= index < len(records):
        raise IndexError(f"No {kind} record {index}.")
    return records[index]


def field_defs(kind: str) -> list[FieldDef]:
    """Every editable field of a kind, in record order (counts excluded)."""
    defs = {
        "character": CHARACTER_HEAD + CHARACTER_LABELS + CHARACTER_AFTER_SKILLS + CHARACTER_TAIL,
        "class": CLASS_LABELS + CLASS_FIXED + CLASS_BEFORE_SKILLS + CLASS_AFTER_SKILLS + CLASS_TAIL,
        "item": ITEM_LABELS + ITEM_FIXED,
        "skill": SKILL_LABELS + SKILL_FIXED,
    }.get(kind)
    if defs is None:
        defs = FIXED_TABLES[kind].fields if kind in FIXED_TABLES else []
    return [d for d in defs if d.key not in COUNT_FIELDS]


def _field_def(kind: str, key: str) -> FieldDef:
    for d in field_defs(kind):
        if d.key == key:
            return d
    raise KeyError(f"A {kind} has no field {key!r}.")


# -- byte moves ------------------------------------------------------------------------------------

def _data_end(data) -> int:
    return HEADER_SIZE + _u32(data, 4)


def insert_bytes(data: bytes, at: int, block: bytes, pointer_fields: Sequence[int] = ()) -> bytes:
    """Insert ``block`` at absolute offset ``at`` inside the data section. Everything at or after
    ``at`` moves: listed pointer fields, pointer values aimed there and symbols. ``pointer_fields``
    are offsets inside ``block`` that hold (already data-relative) pointers to list."""
    if not HEADER_SIZE <= at <= _data_end(data):
        raise ValueError("Insertion point outside the data section.")
    size = len(block)
    if size % 4:
        raise ValueError("Inserted blocks must be a multiple of 4 bytes.")
    rel = at - HEADER_SIZE
    start, listed = fe8data.pointer_list(data)
    out = bytearray(data[:start])
    for field in listed:  # retarget pointers before moving them (offsets are pre-insert)
        target = _u32(out, HEADER_SIZE + field)
        if target >= rel:
            struct.pack_into(">I", out, HEADER_SIZE + field, target + size)
    block = bytearray(block)
    for f in pointer_fields:
        target = _u32(block, f)
        if target >= rel:
            struct.pack_into(">I", block, f, target + size)
    out[at:at] = block
    moved = [f + size if f >= rel else f for f in listed] + [rel + f for f in pointer_fields]
    out += data[start:]
    struct.pack_into(">II", out, 0, len(out), _u32(out, 4) + size)
    out = fe8data.write_pointer_list(out, moved)
    for position, offset, _name in fe8data._symbol_entries(out):
        if offset >= rel and offset != 0:
            struct.pack_into(">I", out, position, offset + size)
    return bytes(out)


def delete_bytes(data: bytes, at: int, size: int) -> bytes:
    """Remove ``size`` bytes at absolute offset ``at`` (the inverse of :func:`insert_bytes`). Listed
    pointer fields inside the range are dropped; a pointer aimed inside it is an error."""
    if size % 4:
        raise ValueError("Removed spans must be a multiple of 4 bytes.")
    rel, rel_end = at - HEADER_SIZE, at - HEADER_SIZE + size
    start, listed = fe8data.pointer_list(data)
    out = bytearray(data[:start])
    kept = []
    for field in listed:
        if rel <= field < rel_end:
            continue
        target = _u32(out, HEADER_SIZE + field)
        if rel <= target < rel_end:
            raise ValueError(f"A pointer at {HEADER_SIZE + field:#x} still points into the removed bytes.")
        if target >= rel_end:
            struct.pack_into(">I", out, HEADER_SIZE + field, target - size)
        kept.append(field - size if field >= rel_end else field)
    del out[at:at + size]
    out += data[start:]
    struct.pack_into(">II", out, 0, len(out), _u32(out, 4) - size)
    out = fe8data.write_pointer_list(out, kept)
    for position, offset, _name in fe8data._symbol_entries(out):
        if offset >= rel_end:
            struct.pack_into(">I", out, position, offset - size)
    return bytes(out)


# -- writing ---------------------------------------------------------------------------------------

def _label_value(data: bytes, label: Optional[str]) -> tuple[bytes, int]:
    if label is None or label == "":
        return data, 0
    return fe8data._label_pointer(data, label, append=True)


def patch_field(data: bytes, kind: str, index: int, key: str, value) -> bytes:
    """Write one field of a record. Labels take a string (None or "" for null)."""
    definition = _field_def(kind, key)
    rec = record(data, kind, index)
    offset = rec.offsets[key]
    if definition.kind == "label":
        data, ptr = _label_value(data, value)
        out = bytearray(data)
        fe8data._pack_pointer(out, offset, ptr)
        return bytes(out)
    value = int(value)
    fmt, low, high = {"u8": (">B", 0, 255), "s8": (">b", -128, 127), "u16": (">H", 0, 0xFFFF),
                      "u32": (">I", 0, 0xFFFFFFFF)}[definition.kind]
    if not low <= value <= high:
        raise ValueError(f"{definition.label} must be between {low} and {high}.")
    out = bytearray(data)
    struct.pack_into(fmt, out, offset, value)
    return bytes(out)


#: list key -> (count field, whether the list lives inside the record)
_LIST_COUNT = {
    ("character", "skills"): "skill_count",
    ("class", "skills"): "skill_count",
    ("class", "sounds"): "sound_count",
    ("item", "attributes"): "attribute_count",
    ("item", "effective"): "effective_count",
    ("skill", "conditions"): "condition_count",
    ("skill", "requirements"): "requirement_count",
}


def set_list(data: bytes, kind: str, index: int, key: str, values: Sequence) -> bytes:
    """Replace a record's list. Character/class/item lists take labels; skill lists take
    ``(mode, label)`` pairs."""
    if (kind, key) not in _LIST_COUNT:
        raise KeyError(f"A {kind} has no list {key!r}.")
    values = list(values)
    if len(values) > 255:
        raise ValueError("A list holds at most 255 entries.")
    if kind == "skill":
        return _set_condition_list(data, index, key, values)
    rec = record(data, kind, index)
    old = rec.lists[key]
    at = rec.offsets[key]
    count_offset = rec.offsets[_LIST_COUNT[(kind, key)]]
    # drop the old entries (null them first so no pointer-list entry survives in the removed span)
    out = bytearray(data)
    for i in range(len(old)):
        fe8data._pack_pointer(out, at + 4 * i, 0)
    data = delete_bytes(bytes(out), at, 4 * len(old)) if old else bytes(out)
    pointers = []
    for label in values:
        data, ptr = _label_value(data, label)
        pointers.append(ptr)
    block = struct.pack(f">{len(pointers)}I", *pointers)
    data = insert_bytes(data, at, block, [4 * i for i, p in enumerate(pointers) if p]) if pointers else data
    out = bytearray(data)
    out[count_offset] = len(values)
    return bytes(out)


def _set_condition_list(data: bytes, index: int, key: str, values: list) -> bytes:
    rec = record(data, "skill", index)
    slot = rec.offsets[key]
    count_offset = rec.offsets["condition_count" if key == "conditions" else "requirement_count"]
    out = bytearray(data)
    old_ptr = _u32(out, slot)
    if old_ptr:  # unlist the old block's label fields; the bytes stay as unused space
        for i in range(len(rec.lists[key])):
            fe8data._pack_pointer(out, HEADER_SIZE + old_ptr + 8 * i + 4, 0)
    fe8data._pack_pointer(out, slot, 0)
    out[count_offset] = len(values)
    data = bytes(out)
    if not values:
        return data
    entries = []
    for mode, label in values:
        data, ptr = _label_value(data, label)
        if not 0 <= int(mode) <= 255:
            raise ValueError("A condition mode is a byte (0-255).")
        entries.append((int(mode), ptr))
    block = b"".join(struct.pack(">B3xI", mode, ptr) for mode, ptr in entries)
    data, base = fe8data.append_block(data, block, [8 * i + 4 for i, (_m, p) in enumerate(entries) if p])
    out = bytearray(data)
    fe8data._pack_pointer(out, record(data, "skill", index).offsets[key], base)
    return bytes(out)


def set_item_bonuses(data: bytes, index: int, bonuses: Optional[Sequence[int]]) -> bytes:
    """Give an item a stat-bonus block (``BONUS_NAMES`` order), change it, or (None) remove it."""
    rec = record(data, "item", index)
    at = rec.offsets["bonuses"]
    count_offset = rec.offsets["bonus_count"]
    if bonuses is not None:
        bonuses = [int(v) for v in bonuses]
        if len(bonuses) != len(BONUS_NAMES) or not all(-128 <= v <= 127 for v in bonuses):
            raise ValueError(f"A bonus block holds {len(BONUS_NAMES)} values between -128 and 127.")
        block = struct.pack(f">{len(bonuses)}b", *bonuses) + bytes(BONUS_BLOCK_SIZE - len(bonuses))
    if rec.bonuses is not None and bonuses is not None:
        out = bytearray(data)
        out[at:at + len(block)] = block
        return bytes(out)
    if rec.bonuses is not None:
        data = delete_bytes(data, at, BONUS_BLOCK_SIZE * rec.values["bonus_count"])
    elif bonuses is not None:
        data = insert_bytes(data, at, block)
    out = bytearray(data)
    out[count_offset] = 0 if bonuses is None else 1
    return bytes(out)


def labels_with_prefix(data: bytes, prefix: str) -> list[str]:
    """Every distinct label in the file starting with ``prefix`` (pickers for label fields)."""
    seen = set()
    for f in fe8data.listed_pointer_fields(data):
        label = resolve(data, _u32(data, f))
        if label and label.startswith(prefix):
            seen.add(label)
    return sorted(seen)


# -- fixed-size tables -----------------------------------------------------------------------------

@dataclass(frozen=True)
class FixedTable:
    """A table of same-size records: ``symbol`` points at a count word (``counted``) or straight at
    the first record (then the records run while their word at +4, the name, is a listed pointer)."""
    symbol: str
    size: int
    fields: tuple
    counted: bool = True


def _f(key: str, label: str, kind: str, offset: int, group: str = "") -> FieldDef:
    return FieldDef(key, label, kind, group, offset)


def _chapter_fields() -> tuple:
    fields = [_f("cid", "ID", "label", 0x00, "Chapter"), _f("title", "Title key", "label", 0x04, "Chapter"),
              _f("map", "Map folder", "label", 0x08, "Chapter"), _f("script", "Script", "label", 0x0C, "Chapter"),
              _f("messages", "Message file", "label", 0x10, "Chapter")]
    for d in range(3):
        base, group = 0x20 + 0x20 * d, f"Objectives, difficulty {d + 1}"
        fields += [_f(f"win_{d}", "Victory", "label", base + 0x04, group),
                   _f(f"win2_{d}", "Victory 2", "label", base + 0x08, group)]
        fields += [_f(f"lose{i}_{d}", f"Defeat {i + 1}", "label", base + 0x10 + 4 * i, group) for i in range(4)]
    fields += [_f("number", "Number", "u8", 0x84, "Settings")]
    fields += [_f(f"unknown_{o:02x}", f"Unknown +0x{o:02X}", "u8", o, "Settings") for o in range(0x88, 0x90)]
    fields += [_f("affinity", "Affinity", "label", 0x90, "Settings"),
               _f("base_scene", "Base scene", "label", 0x94, "Settings"),
               _f("battle_background", "Battle background", "label", 0x98, "Settings"),
               _f("weather", "Weather", "label", 0x9C, "Settings"),
               _f("scene_2", "Second scene", "label", 0xA0, "Settings"),
               _f("lord", "Lord", "label", 0xA4, "Settings")]
    return tuple(fields)


TERRAIN_BLOCK_SIZE = 0x2C
MOVE_COST_COUNT = 23
_TERRAIN_GROUP = "Terrain stats (shared block)"
TERRAIN_BLOCK_FIELDS = (
    tuple(FieldDef(key, label, "s8", _TERRAIN_GROUP, o) for o, (key, label) in enumerate((
        ("avoid", "Avoid"), ("defense", "Defense"), ("resistance", "Resistance"), ("alt_avoid", "Avoid (alt)"),
        ("alt_defense", "Defense (alt)"), ("alt_resistance", "Resistance (alt)"))))
    + (FieldDef("heal", "Heal % per turn", "u8", _TERRAIN_GROUP, 6),
       FieldDef("flags", "Flags", "u8", _TERRAIN_GROUP, 7),
       FieldDef("step_effect", "Step effect", "label", _TERRAIN_GROUP, 8),
       FieldDef("move_sound", "Move sound", "label", _TERRAIN_GROUP, 0x0C),
       FieldDef("move_sound_2", "Move sound 2", "label", _TERRAIN_GROUP, 0x10))
    + tuple(FieldDef(f"cost_{i}", f"Movement type {i}", "u8", "Movement costs (255: impassable)", 0x14 + i)
            for i in range(MOVE_COST_COUNT))
)

FIXED_TABLES = {
    "chapter": FixedTable("ChapterData", 0xB4, _chapter_fields()),
    "terrain": FixedTable("TerrainData", 0x10, (
        _f("number", "Number", "u8", 0, "Terrain"), _f("name", "Name", "label", 4, "Terrain"),
        _f("name_key", "Name key", "label", 8, "Terrain")) + TERRAIN_BLOCK_FIELDS, counted=False),
    "group": FixedTable("GroupData", 0x0C, (
        _f("number", "Number", "u32", 0, "Army"), _f("name", "Name", "label", 4, "Army"),
        _f("name_key", "Name key", "label", 8, "Army"))),
    "bond": FixedTable("KiznaData", 0x0C, (
        _f("pid", "Character", "label", 0, "Bond"), _f("partner", "Partner", "label", 4, "Bond"),
        _f("unknown_08", "Unknown +8", "u8", 8, "Bond"), _f("bonus", "Bonus", "u8", 9, "Bond"))),
    "affinity": FixedTable("DivineData", 0x0C, (
        _f("affinity", "Affinity", "label", 0, "Affinity"), _f("attack", "Attack", "s8", 4, "Affinity"),
        _f("defense", "Defense", "s8", 5, "Affinity"), _f("hit", "Hit", "s8", 6, "Affinity"),
        _f("avoid", "Avoid", "s8", 7, "Affinity"))),
    "affinity_pair": FixedTable("DivineParam", 0x0C, (
        _f("affinity", "Affinity", "label", 0, "Pair"), _f("partner", "Partner affinity", "label", 4, "Pair"),
        _f("value_0", "Value 1", "s8", 8, "Pair"), _f("value_1", "Value 2", "s8", 9, "Pair"),
        _f("value_2", "Value 3", "s8", 10, "Pair"), _f("value_3", "Value 4", "s8", 11, "Pair"))),
    "triangle": FixedTable("3SukumiData", 0x0C, (
        _f("weapon", "Weapon type", "label", 0, "Weapon triangle"),
        _f("against", "Against", "label", 4, "Weapon triangle"),
        _f("damage", "Damage", "s8", 8, "Weapon triangle"), _f("hit", "Hit", "s8", 9, "Weapon triangle"))),
    "difficulty": FixedTable("GameData", 0x08, tuple(
        _f(f"value_{i}", f"Difficulty {i + 1}", "u16", 2 * i, "Constants") for i in range(4)), counted=False),
}
#: GameData holds ten rows of four u16 values (one per difficulty) before the terrain blocks.
DIFFICULTY_ROWS = 10

ID_FIELD = {"character": "pid", "class": "jid", "item": "iid", "skill": "sid", "chapter": "cid",
            "terrain": "name", "group": "name", "bond": "pid", "affinity": "affinity",
            "affinity_pair": "affinity", "triangle": "weapon", "support": "pid"}
ALL_KINDS = KINDS + tuple(FIXED_TABLES) + ("support",)
FIELD_NOTES.update({
    "flags": "Bit flags of the terrain type (byte 7 of Path of Radiance's block marks object tiles).",
    "bonus": "Bonus between bonded units (5 or 10 in the retail data).",
    "damage": "Weapon-triangle damage and hit change (+1/+10 with the advantage, -1/-10 against).",
})


def _read_fixed(data: bytes, kind: str) -> list[Record]:
    table = FIXED_TABLES[kind]
    start = fe8data.section_start(data, table.symbol)
    if kind == "difficulty":
        count, at = DIFFICULTY_ROWS, start
    elif table.counted:
        count, at = _u32(data, start), start + 4
    else:  # no count word: the records run while their name field (+4) is a listed pointer
        count, at = 0, start
        listed = fe8data.listed_pointer_fields(data)
        while count < 0x400 and at + table.size * count + 4 in listed:
            count += 1
    own = [d for d in table.fields if kind != "terrain" or d.key not in TERRAIN_FIELDS]  # block fields read below
    records = []
    for i in range(count):
        r = Record(kind, i, at + i * table.size, at + (i + 1) * table.size)
        _read_fields(data, r, own, r.start)
        if kind == "terrain":
            block = _u32(data, r.start + 0x0C)
            r.values["block"] = block
            if block:
                b = Record(kind, i, HEADER_SIZE + block, HEADER_SIZE + block + TERRAIN_BLOCK_SIZE)
                _read_fields(data, b, TERRAIN_BLOCK_FIELDS, b.start)
                r.values.update(b.values)
                r.offsets.update(b.offsets)
        records.append(r)
    return records


TERRAIN_FIELDS = frozenset(d.key for d in TERRAIN_BLOCK_FIELDS)


def terrain_block_users(data: bytes, index: int) -> list[int]:
    """Terrain types sharing type ``index``'s stats block (editing it changes all of them)."""
    types = _read_fixed(data, "terrain")
    return [t.index for t in types if t.values["block"] == types[index].values["block"]]


def own_terrain_block(data: bytes, index: int) -> bytes:
    """Give terrain type ``index`` a copy of its stats block, so its edits stop reaching the types
    it shared the block with."""
    rec = _read_fixed(data, "terrain")[index]
    block = rec.values["block"]
    raw = bytes(data[HEADER_SIZE + block:HEADER_SIZE + block + TERRAIN_BLOCK_SIZE])
    listed = fe8data.listed_pointer_fields(data)
    pointer_fields = [o for o in (8, 0x0C, 0x10) if HEADER_SIZE + block + o in listed]
    data, base = fe8data.append_block(data, raw, pointer_fields)
    out = bytearray(data)
    fe8data._pack_pointer(out, rec.start + 0x0C, base)
    return bytes(out)


# -- supports (RelianceData) -----------------------------------------------------------------------

SUPPORT_ENTRY_SIZE = 8


def _read_supports(data: bytes) -> list[Record]:
    """RelianceData: a count, then per character its PID, a partner count and one 8-byte entry per
    partner (``partner PID, u8 flag, u8 speed, 2 zero bytes``). The retail table lists all 71
    supporting characters against all 71 (themselves included)."""
    start = fe8data.section_start(data, "RelianceData")
    count = _u32(data, start)
    at = start + 4
    records = []
    for i in range(count):
        r = Record("support", i, at, at)
        r.offsets["pid"] = at
        r.values["pid"] = resolve(data, _u32(data, at))
        partners = _u32(data, at + 4)
        r.offsets["partners"] = at + 8
        r.lists["partners"] = [(resolve(data, _u32(data, at + 8 + 8 * k)), data[at + 12 + 8 * k],
                                data[at + 13 + 8 * k]) for k in range(partners)]
        r.end = at + 8 + SUPPORT_ENTRY_SIZE * partners
        records.append(r)
        at = r.end
    return records


def set_support(data: bytes, index: int, partner: int, flag: int, speed: int) -> bytes:
    """Set the flag and speed of character ``index``'s ``partner``-th support entry."""
    rec = _read_supports(data)[index]
    if not 0 <= partner < len(rec.lists["partners"]):
        raise IndexError(f"{rec.values['pid']} has no support entry {partner}.")
    if not (0 <= flag <= 255 and 0 <= speed <= 255):
        raise ValueError("The flag and speed are bytes (0-255).")
    out = bytearray(data)
    at = rec.offsets["partners"] + SUPPORT_ENTRY_SIZE * partner + 4
    out[at], out[at + 1] = flag, speed
    return bytes(out)
