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
from pathlib import Path
from typing import Optional, Sequence

from . import fe8data
from .fe8data import HEADER_SIZE
from ..game_files import as_path

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
    kind: str        # "label", "u8", "s8", "u16", "u32", "f32"
    group: str = ""  # form section
    offset: int = -1  # record-relative offset (fixed-size tables; -1: fields follow each other)


def _labels(*pairs: tuple[str, str], group: str = "") -> list[FieldDef]:
    return [FieldDef(key, label, "label", group) for key, label in pairs]


def _bytes(kind: str, names: Sequence[tuple[str, str]], group: str = "") -> list[FieldDef]:
    return [FieldDef(key, label, kind, group) for key, label in names]


def _stats(prefix: str, kind: str, group: str, names: Sequence[str] = STAT_NAMES) -> list[FieldDef]:
    return [FieldDef(f"{prefix}_{name.lower()}", name, kind, group) for name in names]


# -- character (PersonData) ------------------------------------------------------------------------
# +0x00 skill count, +0x01 unused, +0x02 level, +0x03 sex; 7 labels; skills; 5 labels; 28 bytes. The loader
# is 0x80109df8 (0xFC-byte runtime records).
CHARACTER_HEAD = _bytes("u8", (("unused_01", "Unused +0x01"), ("level", "Level"), ("sex", "Sex (1 = female)")), "Unit")
CHARACTER_LABELS = _labels(("pid", "ID"), ("mpid", "Name key"), ("mnpid", "Help key"), ("fid", "Portrait"),
                           ("jid", "Class"), ("affinity", "Affinity"), ("weapon_ranks", "Weapon ranks"),
                           group="Identity")
CHARACTER_AFTER_SKILLS = _labels(("extra_skill", "Extra skill"), ("aid_1", "Animation 1"),
                                 ("aid_2", "Animation 2"), ("aid_3", "Animation 3"), ("aid_4", "Animation 4"),
                                 group="Animations")
CHARACTER_TAIL = (
    _bytes("u8", (("biorhythm", "Biorhythm type"), ("biorhythm_phase", "Biorhythm starting phase"),
                  ("biorhythm_step", "Biorhythm step per phase"), ("protected_parts", "Withdraws instead of dying in Parts"),
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
# 11 labels; 16 bytes (+5 skill count, +6 sound-class count, +13..+15 padding); skills; a label;
# sound classes; 32 bytes (caps, bases, growths, promotion gains). The loader is 0x8010a2fc (0x11C-byte
# runtime records).
CLASS_LABELS = _labels(("jid", "ID"), ("mjid", "Name key"), ("japanese_name", "Japanese name"),
                       ("help", "Help key"), ("demotes_to", "Previous tier"), ("promotes_to", "Promotes to"),
                       ("other_form", "Other form"), ("innate_weapon", "Innate weapon"),
                       ("aid", "Default animation"), ("weapon_ranks", "Starting weapon ranks"),
                       ("max_weapon_ranks", "Maximum weapon ranks"), group="Identity")
CLASS_FIXED = (
    _bytes("u8", (("weight", "Weight"), ("weight_kind_1", "Weight part 1: kind")), "Class")
    + _bytes("s8", (("weight_part_1", "Weight part 1"),), "Class")
    + _bytes("u8", (("weight_kind_2", "Weight part 2: kind"),), "Class")
    + _bytes("s8", (("weight_part_2", "Weight part 2"),), "Class")
    + _bytes("u8", (("skill_count", "Skill count"), ("sound_count", "Sound class count"),
                    ("promotion_level", "Promotion level"), ("movement_type", "Movement type"),
                    ("movement", "Movement"), ("skill_capacity", "Skill capacity"), ("vision", "Vision"),
                    ("unknown_0c", "Unknown +12")), "Class"))
CLASS_FIXED_PADDING = 3  # +13..+15: the loader skips them
CLASS_AFTER_SKILLS = _labels(("extra_skill", "Extra skill"), group="Class")
CLASS_TAIL = (_stats("cap", "u8", "Stat caps") + _stats("base", "u8", "Base stats")
              + _stats("growth", "u8", "Growth rates (%)") + _stats("promotion", "u8", "Promotion gains"))
CLASS_TAIL_SIZE = 32
CLASS_FIXED_SIZE = 16

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
                    ("range_max", "Maximum range"), ("article", "English article"),
                    ("pad_13", "Padding +13"), ("pad_14", "Padding +14"), ("pad_15", "Padding +15"),
                    ("colour", "Colour"), ("attribute_count", "Attribute count"),
                    ("effective_count", "Effectiveness count"), ("bonus_count", "Bonus blocks")), "Item")
)
ITEM_FIXED_SIZE = 20

# -- skill (SkillData) -----------------------------------------------------------------------------
SKILL_LABELS = _labels(("sid", "ID"), ("msid", "Name key"), ("help", "Help key"), ("help_2", "Help key 2"),
                       ("effect", "Effect"), ("effect_2", "Effect 2"), ("item", "Scroll item"), group="Identity")
SKILL_FIXED = _bytes("u8", (("number", "Number"), ("article", "English article"), ("capacity", "Capacity"),
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
    "protected_parts": "Bit n set: in Part n+1 (bit 4: Endgame) the unit withdraws instead of dying, unless the "
                       "gf_gameover flag is set (0x8011f428 tests it against the chapter's Part bits).",
    "biorhythm_phase": "Starting phase of the biorhythm curve: 0-6 pick a fixed phase, other values a random one.",
    "biorhythm_step": "How far the biorhythm counter moves at the end of each of the unit's phases; negative "
                      "(255) picks a random step.",
    "extra_skill": "One more skill given to the unit after the skill list (none in the retail data).",
    "unused_01": "Not copied by the loader.",
    "weight": "Base weight of the class; a unit's weight is this plus its personal weight (0x8012401c).",
    "weight_kind_1": "Two (kind, weight) parts added to the unit's weight for its mounted total (0x80124144). "
                     "Retail kinds: 1 armour and gear, 2 horse, 3 pegasus, 4 wyvern, 6 beast, 7 dragon, 8 bird, "
                     "9 goddess.",
    "promotion_level": "A level-up that would reach this level promotes the unit instead (21 on first and "
                       "second tier classes); 0: no limit (0x8006d19c).",
    "enemy_levels_0": "Levels added to the chapter's enemy units on each difficulty, up to the class's maximum level.",
    "move_change": "Added to the movement of units whose class type matches (mounted and beast tests in "
                   "0x80060828); -2 on six desert and snow maps.",
    "skip_mask": "Non-zero: the next-chapter step skips this chapter unless the bit for the current difficulty "
                 "is set (bit 1 Easy, 2 Normal, 3 Hard, 0 Maniac). The base sub-chapters use 0x80.",
    "part": "Bit 0 Part 1 ... bit 4 Endgame; bit 7 on 4-1, 4-2 and their bases.",
    "player_group": "GroupData index the player's units take as their army in this chapter.",
    "authority": "0-5 authority stars.",
    "bonus_hp": "Starting stat = class base + this, capped at the class cap (checked in game: Micaiah "
                "with +19 HP over the Light Mage's 16 starts at its cap, 30).",
    "gauge_turn": "Laguz gauge change per turn and per battle, untransformed and transformed.",
    "movement_type": "The TerrainData movement-cost column the class moves with (0-22; 10 on every flier).",
    "skill_capacity": "Retail values are 15 (first tier), 30 (second) and 60 (third), more for laguz.",
    "base_lck": "Not used: the loader sets every class's base Luck to 0.",
    "article": "Article before the name in English text: 0 none, 1 'a', 2 'an', 3 (system skills, flagged "
               "items); 255 picks 'a' or 'an' from the first letter (0x801110c4, 0x8011a174).",
    "colour": "Index 0-8 into the item colour palette (grey, translucent black, red, green, blue, yellow, purple, "
              "orange, teal; 0x801125b4); every retail item uses 4. Forged weapons use their own colour.",
    "vision": "Fog-of-war sight range; SID_INSIGHT adds 5 and an equipped torch 2 (0x801241f4).",
    "kind": "Bond kind: the game matches bonds by kind and counts kind 1 (every retail bond); scripts can add "
            "bonds of other kinds at run time.",
    "preparations": "Probably the battle preparations mode: 0 on chapters that start without preparations, "
                    "1 on most, 2 and 5 in the Endgame (0x800581f4).",
    "grade_turns_a": "Trial maps only (chapter number 90 and up): the most turns, units lost and the least score "
                     "for each grade; the final grade averages the three.",
    "blessing_hp": "Added to the stats of player and allied units while flag G_0407_ユンヌの加護 is set (the Endgame "
                 "blessing), by difficulty (0x801243f4 and the other stat accessors).",
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
        elif d.kind == "f32":
            record.values[d.key] = round(struct.unpack_from(">f", data, at)[0], 6)
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
    if kind == "battle_scenery":
        return _read_battle_scenery(data)
    if kind == "no_battle":
        return _read_no_battle(data)
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
    pos += CLASS_FIXED_PADDING
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
    flags = r.values["bonus_count"]  # a bit mask (0x8010a958): bit 0 the stat block, bit 1 an 8-byte block
    if flags & 1:
        r.bonuses = [struct.unpack_from(">b", data, pos + i)[0] for i in range(len(BONUS_NAMES))]
    pos += _bonus_blocks_size(flags)
    r.end = pos
    return r


def _bonus_blocks_size(flags: int) -> int:
    """Bytes the optional blocks after an item's lists take: the 10-byte stat block (bit 0), an 8-byte block
    no retail item has (bit 1), then padding to a word."""
    size = (len(BONUS_NAMES) if flags & 1 else 0) + (8 if flags & 2 else 0)
    return size + -size % 4


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
        "class": CLASS_LABELS + CLASS_FIXED + CLASS_AFTER_SKILLS + CLASS_TAIL,
        "item": ITEM_LABELS + ITEM_FIXED,
        "skill": SKILL_LABELS + SKILL_FIXED,
    }.get(kind)
    if defs is None:
        defs = FIXED_TABLES[kind].fields if kind in FIXED_TABLES else NO_BATTLE_FIELDS if kind == "no_battle" else []
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
    if definition.kind == "f32":
        out = bytearray(data)
        struct.pack_into(">f", out, offset, float(value))
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
    if kind == "no_battle" and key == "characters":
        return _set_no_battle_list(data, index, list(values))
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
    if rec.values["bonus_count"] & ~1:
        raise ValueError("This item has a second bonus block (bit 1 of its block byte); edit it as raw bytes.")
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
        data = delete_bytes(data, at, _bonus_blocks_size(rec.values["bonus_count"]))
    elif bonuses is not None:
        data = insert_bytes(data, at, block)
    out = bytearray(data)
    out[count_offset] = 0 if bonuses is None else 1
    return bytes(out)


def message_key(speaker: str) -> str:
    """A message key as FE10Data names it: :mod:`message` decodes key bytes one to one (cp437), and
    the Japanese keys (``MT_平地``, ``MG_...``) are Shift-JIS."""
    from . import message

    try:
        return speaker.encode(message.ENCODING).decode("shift_jis")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return speaker


def message_names(mess_dir: Path) -> dict[str, str]:
    """Message key -> first line of its text from ``common.m``, English (``e_common.m``) when the
    disc has it: the names of the ``MPID_``/``MIID_``/... keys records point at."""
    from . import message

    for name in ("e_common.m", "common.m"):
        path = as_path(mess_dir) / name
        if path.is_file():
            try:
                return {message_key(m.speaker): m.text.split("\n", 1)[0] for m in message.read_messages_path(path)}
            except Exception:  # noqa: BLE001 - names are a convenience
                return {}
    return {}


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
    fixed_count: int = 0  # a table with neither count word nor names: this many records
    start: int = 0  # where the first record is, from the symbol (fixed_count tables)


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
    # +0x85..+0x88: enemy level bonus picked by the save's difficulty byte 3, 0, 1, 2 (0x80092c84, applied
    # to enemy units in 0x8011f70c). The byte is 0 Normal, 1 Hard, 2 Maniac (the US disc's Hard), 3 Easy. +0x89 selects the party-state gold account (FUN_800615dc/FUN_80061808/
    # FUN_800626e0); +0x8A selects the warehouse pointer (FUN_801059b0).
    fields += [_f(f"enemy_levels_{d}", f"Enemy levels, {name}", "u8", o, "Enemy level bonus")
               for o, d, name in ((0x85, 3, "Easy"), (0x86, 0, "Normal"), (0x87, 1, "Hard"),
                                  (0x88, 2, "Maniac (US Hard)"))]
    fields += [_f("gold_account", "Gold account", "u8", 0x89, "Settings"),
               _f("convoy", "Convoy", "u8", 0x8A, "Settings"),
               _f("move_change", "Movement change", "s8", 0x8B, "Settings"),
               _f("preparations", "Preparations mode", "u8", 0x8C, "Settings"),
               _f("skip_mask", "Skipped unless difficulty bit", "u8", 0x8D, "Settings"),
               _f("part", "Part bits", "u8", 0x8E, "Settings"),
               _f("player_group", "Player army", "u8", 0x8F, "Settings")]
    fields += [_f("affinity", "Affinity", "label", 0x90, "Settings"),
               _f("base_scene", "Base scene", "label", 0x94, "Settings"),
               _f("battle_background", "Battle background", "label", 0x98, "Settings"),
               _f("weather", "Weather", "label", 0x9C, "Settings"),
               _f("scene_2", "Second scene", "label", 0xA0, "Settings"),
               _f("lord", "Lord", "label", 0xA4, "Settings")]
    # +0xA8..+0xB3: trial-map grade thresholds A-D (0x800634d8, 0x80063568, 0x80063620); chapters below
    # number 90 grade '-'.
    for base, key, what in ((0xA8, "grade_turns", "turns"), (0xAC, "grade_losses", "units lost"),
                            (0xB0, "grade_score", "score")):
        fields += [_f(f"{key}_{g.lower()}", f"{g} grade, {what}", "u8", base + i, "Trial map grades")
                   for i, g in enumerate("ABCD")]
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

DIFFICULTY_ROW_NAMES = (
    "Kill EXP base",
    "Action EXP base",
    "Kill EXP multiplier (%)",
    "Action EXP multiplier (%)",
    "Second-tier effective-level adjustment",
    "Third-tier effective-level adjustment",
    "Animalize effective-level adjustment",
    "Boss target kill EXP bonus",
    "Steal-skill target kill EXP bonus",
    "Weapon EXP multiplier (%)",
    "Row 11 (no reader found)",
    "Row 12 (no reader found)",
    "Critical bonus with SID_CRITRISE",
)
DIFFICULTY_NAMES = ("Easy", "Normal", "Hard", "Maniac")  # GameData columns: save difficulty 3, 0, 1, 2


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
        _f("kind", "Kind", "u8", 8, "Bond"), _f("bonus", "Bonus", "u8", 9, "Bond"))),
    "affinity": FixedTable("DivineData", 0x0C, (
        _f("affinity", "Affinity", "label", 0, "Affinity"), _f("attack", "Attack", "s8", 4, "Affinity"),
        _f("defense", "Defense", "s8", 5, "Affinity"), _f("hit", "Hit", "s8", 6, "Affinity"),
        _f("avoid", "Avoid", "s8", 7, "Affinity"), _f("crit", "Critical", "s8", 8, "Affinity"),
        _f("crit_avoid", "Critical avoid", "s8", 9, "Affinity"))),  # per support rank (0x8012ec2c)
    "affinity_pair": FixedTable("DivineParam", 0x0C, (
        _f("affinity", "Affinity", "label", 0, "Pair"), _f("partner", "Partner affinity", "label", 4, "Pair"),
        _f("value_0", "Value 1", "s8", 8, "Pair"), _f("value_1", "Value 2", "s8", 9, "Pair"),
        _f("value_2", "Value 3", "s8", 10, "Pair"), _f("value_3", "Value 4", "s8", 11, "Pair"))),
    "triangle": FixedTable("3SukumiData", 0x0C, (
        _f("weapon", "Weapon type", "label", 0, "Weapon triangle"),
        _f("against", "Against", "label", 4, "Weapon triangle"),
        _f("damage", "Damage", "s8", 8, "Weapon triangle"), _f("hit", "Hit", "s8", 9, "Weapon triangle"))),
    "difficulty": FixedTable("GameData", 0x08, tuple(
        _f(f"value_{i}", name, "u16", 2 * i, "Difficulty values")
        for i, name in enumerate(("Easy", "Normal", "Hard", "Maniac"))), counted=False,
        fixed_count=13),  # 13 rows of four u16 (one per difficulty), then the blessing block
    "blessing": FixedTable("GameData", 0x08, tuple(
        _f(f"blessing_{stat.lower()}", stat, "s8", i, "Yune's blessing") for i, stat in enumerate(STAT_NAMES)),
        counted=False, fixed_count=4, start=0x68),  # one row per difficulty column, as GameData's
    "biorhythm": FixedTable("BioData", 0x10, tuple(
        _f(f"value_{i}", f"Value {i + 1}", "f32", 4 * i, "Biorhythm row") for i in range(4)), counted=False,
        fixed_count=10),  # ten rows of four floats
    # BioParam: five bands, f32 threshold then the bonus bytes build_biorhythm_bonus_vector (0x80107864)
    # copies into its output slots 2-6; +9..+11 are not read.
    "biorhythm_band": FixedTable("BioParam", 0x0C, (
        _f("threshold", "Threshold", "f32", 0, "Biorhythm band"),) + tuple(
        _f(f"bonus_{i + 1}", f"Bonus {i + 1}", "s8", 4 + i, "Bonus vector (slots 2-6)") for i in range(5)),
        counted=False, fixed_count=5),
    # RelianceParam: one 16-byte block (readers at 0x80091cd0, 0x80119990, 0x8012eb70).
    "support_param": FixedTable("RelianceParam", 0x10, (
        _f("points_c", "Points for C", "u8", 0, "Support levels"),
        _f("points_b", "Points for B", "u8", 1, "Support levels"),
        _f("points_a", "Points for A", "u8", 2, "Support levels"),
        _f("points_cap", "Point limit at A", "u8", 3, "Support levels"),
        _f("gain_0", "Event 0", "u8", 4, "Points per event"),
        _f("gain_0_flag", "Event 0 (flag set)", "u8", 5, "Points per event"))
        + tuple(_f(f"gain_{i}", f"Event {i}", "s8", 5 + i, "Points per event") for i in range(1, 6))
        + tuple(_f(f"speed_{i}", f"Speed {i}", "s8", 11 + i, "Points added per support speed") for i in range(5)),
        counted=False, fixed_count=1),
}

ID_FIELD = {"character": "pid", "class": "jid", "item": "iid", "skill": "sid", "chapter": "cid",
            "terrain": "name", "group": "name", "bond": "pid", "affinity": "affinity",
            "affinity_pair": "affinity", "triangle": "weapon", "support": "pid", "battle_scenery": "map",
            "growth": "pid", "no_battle": "pid"}
ALL_KINDS = KINDS + tuple(FIXED_TABLES) + ("support", "battle_scenery", "no_battle")
FIELD_NOTES.update({
    "flags": "Bit flags of the terrain type (byte 7 of Path of Radiance's block marks object tiles).",
    "bonus": "Bonus between bonded units (5 or 10 in the retail data).",
    "damage": "Weapon-triangle damage and hit change (+1/+10 with the advantage, -1/-10 against).",
    "points_c": "Support points a pair needs for each level. Points stop at the next level's value "
                "until that level is reached; past A they stop at the limit.",
    "gain_0": "Support points a pair gains per event type (the event types are not named yet); "
              "event 0 takes the second value while a game flag is set.",
    "speed_0": "Added to every gain, picked by the pair's support speed (RelianceData).",
    "threshold": "The band applies while the biorhythm curve is at or above this value.",
    "bonus_1": "Copied into the unit's biorhythm bonus vector; Tempest doubles it, Serenity halves it.",
    "characters": "Characters this one cannot attack (0x8011f1a8, used by targeting and the AI). An entry's "
                  "flag byte, 0 in every retail list, lets the pair fight in combat anyway (0x8011f2f0).",
})
LISTS["no_battle"] = {"characters": "Characters"}


def _read_fixed(data: bytes, kind: str) -> list[Record]:
    table = FIXED_TABLES[kind]
    start = fe8data.section_start(data, table.symbol)
    if table.fixed_count:
        count, at = table.fixed_count, start + table.start
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


# -- battle scenery per map and terrain (BattleTerrIndex / BattleTerrName) --------------------------

def battle_scenery_names(data: bytes) -> list[Optional[str]]:
    """BattleTerrName: the battle backgrounds (``bg0101街``...), indexed by BattleTerrIndex."""
    start = fe8data.section_start(data, "BattleTerrName")
    end = fe8data.section_start(data, "RelianceData")
    return [resolve(data, _u32(data, at)) for at in range(start, end, 4)]


def _read_battle_scenery(data: bytes) -> list[Record]:
    """BattleTerrIndex: u16 terrain-type count (199) and u16 map count (44), then per map its folder
    label and one u16 per terrain type, the BattleTerrName index fought on (0xFFFF: none), padded
    to a word."""
    start = fe8data.section_start(data, "BattleTerrIndex")
    types, maps = struct.unpack_from(">HH", data, start)
    size = 4 + (2 * types + 3) // 4 * 4
    records = []
    for i in range(maps):
        at = start + 4 + size * i
        r = Record("battle_scenery", i, at, at + size)
        r.offsets["map"] = at
        r.values["map"] = resolve(data, _u32(data, at))
        r.offsets["scenery"] = at + 4
        r.lists["scenery"] = list(struct.unpack_from(f">{types}H", data, at + 4))
        records.append(r)
    return records


def set_battle_scenery(data: bytes, index: int, terrain: int, scenery: int) -> bytes:
    """Map ``index`` fights on terrain type ``terrain`` in front of BattleTerrName entry ``scenery``
    (0xFFFF: none)."""
    rec = _read_battle_scenery(data)[index]
    if not 0 <= terrain < len(rec.lists["scenery"]):
        raise IndexError(f"No terrain type {terrain}.")
    names = battle_scenery_names(data)
    if scenery != 0xFFFF and not 0 <= scenery < len(names):
        raise ValueError(f"The scenery is 0-{len(names) - 1} or 65535 (none).")
    out = bytearray(data)
    struct.pack_into(">H", out, rec.offsets["scenery"] + 2 * terrain, scenery)
    return bytes(out)


# -- adding and removing records -------------------------------------------------------------------

#: Tables whose records can be added and removed: the ones with a count word the engine loops on.
#: Skills are left fixed (each has its own symbol, and Path of Radiance binds them to literal
#: numbers); terrain and the row tables have no count word.
ADDABLE_KINDS = ("character", "class", "item", "chapter", "group", "bond", "affinity_pair", "triangle")
#: A save stores these records by number: removing one renumbers the ones after it.
SAVED_BY_NUMBER = ("character", "class", "item")


# -- no-battle lists (NOBTL_TABLE) ---------------------------------------------------------------

NO_BATTLE_ENTRY_SIZE = 8
NO_BATTLE_FIELDS = (FieldDef("pid", "Character", "label", "No-battle list"),)


def _read_no_battle(data: bytes) -> list[Record]:
    """NOBTL_TABLE: a count, then the lists back to back (each also has its own ``NOBTL_<name>``
    symbol): the owner's PID, one 8-byte entry per listed character (``PID``, a word 0 in every retail
    entry but a flag byte at +4), and a null word that ends the list. Built by ``0x8010af44``."""
    start = fe8data.section_start(data, "NOBTL_TABLE")
    at = start + 4
    records = []
    for i in range(_u32(data, start)):
        r = Record("no_battle", i, at, at)
        r.offsets["pid"] = at
        r.values["pid"] = resolve(data, _u32(data, at))
        pos = r.offsets["characters"] = at + 4
        names, flags = [], []
        while _u32(data, pos):
            names.append(resolve(data, _u32(data, pos)))
            flags.append(data[pos + 4])
            pos += NO_BATTLE_ENTRY_SIZE
        r.lists["characters"] = names
        r.values["flags"] = flags  # per entry; kept through list edits
        r.end = at = pos + 4
        records.append(r)
    return records


def _set_no_battle_list(data: bytes, index: int, values: list) -> bytes:
    rec = _read_no_battle(data)[index]
    at, old = rec.offsets["characters"], rec.lists["characters"]
    old_flags = dict(zip(old, rec.values["flags"]))
    if any(not label for label in values):
        raise ValueError("A no-battle list cannot hold an empty entry (a null word ends the list).")
    out = bytearray(data)
    for i in range(len(old)):
        fe8data._pack_pointer(out, at + NO_BATTLE_ENTRY_SIZE * i, 0)
    data = delete_bytes(bytes(out), at, NO_BATTLE_ENTRY_SIZE * len(old)) if old else bytes(out)
    pointers = []
    for label in values:
        data, ptr = _label_value(data, label)
        pointers.append(ptr)
    if not pointers:
        return data
    block = b"".join(struct.pack(">IB3x", ptr, old_flags.get(label, 0)) for ptr, label in zip(pointers, values))
    return insert_bytes(data, at, block, [NO_BATTLE_ENTRY_SIZE * i for i in range(len(pointers))])


def _count_offset(data: bytes, kind: str) -> int:
    if kind in KINDS:
        return table_start(data, kind)
    return fe8data.section_start(data, FIXED_TABLES[kind].symbol)


def add_record(data: bytes, kind: str, copy_of: int, new_id: Optional[str] = None) -> tuple[bytes, int]:
    """Append a copy of record ``copy_of`` to the end of its table (its label fields stay listed and
    still name the same strings), give it ``new_id``, and return the file and the new index."""
    if kind not in ADDABLE_KINDS:
        raise ValueError(f"{kind} records cannot be added.")
    records = _walk(data, kind)
    source = records[copy_of]
    listed = fe8data.listed_pointer_fields(data)
    block = bytes(data[source.start:source.end])
    fields = [f - source.start for f in sorted(listed) if source.start <= f < source.end]
    data = insert_bytes(data, records[-1].end, block, [f for f in fields])
    out = bytearray(data)
    at = _count_offset(data, kind)
    struct.pack_into(">I", out, at, _u32(out, at) + 1)
    data, index = bytes(out), len(records)
    if new_id:
        data = patch_field(data, kind, index, ID_FIELD[kind], new_id)
    return data, index


def remove_record(data: bytes, kind: str, index: int) -> bytes:
    """Remove record ``index`` (the records after it move up one number)."""
    if kind not in ADDABLE_KINDS:
        raise ValueError(f"{kind} records cannot be removed.")
    records = _walk(data, kind)
    if len(records) <= 1:
        raise ValueError("The last record of a table cannot be removed.")
    rec = records[index]
    out = bytearray(data)
    for f in sorted(fe8data.listed_pointer_fields(data)):
        if rec.start <= f < rec.end:
            fe8data._pack_pointer(out, f, 0)
    data = delete_bytes(bytes(out), rec.start, rec.end - rec.start)
    out = bytearray(data)
    at = _count_offset(data, kind)
    struct.pack_into(">I", out, at, _u32(out, at) - 1)
    return bytes(out)
