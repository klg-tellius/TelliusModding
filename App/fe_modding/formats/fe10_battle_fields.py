"""Typed fields of every ``FE10Battle.cms`` table, for the Battle Data page's row form.

The names and readers come from the byte-coverage rules (``coverage_handlers.FE10_BATTLE_LAYOUTS``,
each field cited to its RFEE01 reader there) and the table modules (:mod:`formats.fe10_battle_units`,
:mod:`formats.fe10_battle_weapons`, :mod:`formats.fe10_battle_scenery`). Text fields are the rows'
relocated labels; number fields are written in place. Bytes no field names (pads, the pointers the
loader writes in RAM, FE10BCamType +0x04 that nothing reads) are kept as they are.

``FE10BUnit`` +0x40 holds, for each of the sixteen ``FE10BWeaponType`` rows, a 128-bit set of
``FE10BMotion`` rows: RFEE01 ``0x800A7324`` (unit, weapon type, motion) tests bit ``motion % 32`` of
word ``motion // 32`` in the weapon type's 16 bytes. :func:`unit_motions` / :func:`set_unit_motions`
read and write it as sets of motion rows.
"""

from __future__ import annotations

import struct

from . import fe10_battle
from .record_fields import BIT, LABEL, Field, read_numbers, write_numbers


def _labels(*names: tuple[int, str], note: str = "") -> tuple[Field, ...]:
    return tuple(Field(f"s{offset:02x}", offset, LABEL, name, note) for offset, name in names)


_NAME = (0, "Name")
_GROUND_NOTE = "An FE10BSFXData row; the scenery's footstep ground picks the column (RFEE01 0x800BA2C8)."
_CONTEXT_NOTE = "An FE10BCamGroup row for this camera context (RFEE01 0x800A6D08); -1: none."
WEAPON_TYPES = 16
MOTION_BITS = 128
MOTIONS_OFFSET = 0x40
CAMERA_LISTS_OFFSET = 0x140

FIELDS: dict[str, tuple[Field, ...]] = {
    "FE10BAnimData": _labels((0, "Animation ID"), (4, "Text +0x04"), (8, "Text +0x08"), (12, "Description"),
                             (16, "Text +0x10")),
    "FE10BFootEffect": _labels(_NAME, *((4 * i, f"Effect {i}") for i in range(1, 6))),
    "FE10BSFXList": _labels(_NAME) + tuple(
        Field(f"ground{i}", 4 + 2 * i, "s16", f"Ground column {i}", _GROUND_NOTE) for i in range(8)),
    "FE10BSFXData": _labels(_NAME, *((4 * i, f"Sound {i}") for i in range(1, 5)),
                            note="A cue name. On the disc +0x08 is the move sound, +0x0C the fall and +0x10 the "
                                 "away sound (SFX_BTL_MOVE_/FALL_/AWAY_)."),
    "FE10BSetup": _labels(_NAME) + (
        Field("value", 4, "s32", "Value (1/65536)", "Looked up by its name (RFEE01 0x800A84A4); 65536 = 1.0."),),
    "FE10BWeapon": _labels(_NAME, (4, "Weapon key"), (8, "Model"), (12, "Hit effect"), (16, "Critical hit effect"),
                           (20, "Weapon effect"), (24, "Target effect"), (28, "Magic class")) + (
        Field("type", 0x20, "u8", "Weapon type", "An FE10BWeaponType row."),
        *(Field(f"flag{bit}", 0x21, BIT, f"Actor flag 0x{1 << bit:02X}",
                "Tested by the weapon actor (RFEE01 0x800BC590, 0x800BF394, 0x800C0900, 0x800C0F94).", bit=bit)
          for bit in range(4)),
        Field("scale", 0x22, "u16", "Scale", "Read at RFEE01 0x800BFD60."),
    ),
    "FE10BWeaponType": _labels(_NAME, (4, "Code")),
    "FE10BMapModel": _labels((0, "Scenery folder"), (4, "Sound group")) + (
        Field("flags", 8, "hex8", "Flags", "0x02 indoors, 0x08 mirrored, 0x10/0x20/0x40 the run-in "
                                           "(Battle Sceneries names each one)."),
        *(Field(f"p{i}", 9 + i, "u8", f"Parameter +0x{9 + i:02X}") for i in range(5)),
        Field("x", 0x0E, "s16", "Position X"), Field("y", 0x10, "s16", "Position Y"),
        Field("z", 0x12, "s16", "Position Z"), Field("rotation", 0x14, "s16", "Rotation"),
        Field("scale", 0x16, "u16", "Scale (1/256)", "0 means 768 (3.0)."),
    ),
    "FE10BMapData": _labels((0, "Map key")) + tuple(
        Field(f"variant{i}", 4 + 2 * i, "s16", f"Scenery variant {i}", "An FE10BMapModel row; -1: none.")
        for i in range(5)),
    "FE10BSky": _labels(_NAME, (4, "Sky folder")),
    "FE10BSkill": _labels(_NAME, (4, "Skill (SID)"), (8, "Effect 1"), (12, "Effect 2"), (16, "Effect 3")),
    "FE10BMotion": _labels(_NAME, (4, "Code")) + (
        Field("flags", 8, "hex16", "Flags", "0x0001 and 0x0008 are tested on the motion row (RFEE01 "
                                            "0x800B2178); the other bits are read through a field shared with the "
                                            "camera rows, their meaning not proven."),
        Field("value", 0x0A, "u8", "Value +0x0A", "Read at RFEE01 0x800B21DC."),
        Field("extra", 0x0B, "u8", "Value +0x0B", "Read through the shared field; meaning not proven."),
    ),
    "FE10BFlags": _labels(_NAME),
    "FE10BParam": _labels(_NAME),
    "FE10BCamFile": _labels(_NAME, (4, "Camera file")) + (
        Field("flags", 8, "hex16", "Flags", "Every set bit is tested (RFEE01 0x800A4420, 0x800A6150); "
                                            "0xE000 is the target mode copied to the camera."),
        Field("chain", 0x0B, "u8", "Chain ID"),
    ),
    "FE10BCamGroup": _labels(_NAME, (4, "Code")),
    "FE10BCamEffect": _labels((0, "Effect")) + tuple(
        Field(f"context{i}", 4 + 2 * i, "s16", f"Camera group, context {i}", _CONTEXT_NOTE) for i in range(5)),
    "FE10BCamList": _labels(_NAME, (4, "Code")),
    "FE10BCamType": _labels(_NAME),
    "FE10BUnit": _labels((0, "Description"), (4, "Model"), (8, "Trail effect"), (12, "Aura effect")) + (
        Field("flags", 0x10, "hex32", "FE10BFlags bits", "Bit i is FE10BFlags row i (Battle Unit Parameters "
                                                         "names each one)."),
        Field("variants", 0x14, "hex32", "Random attack variants",
              "Bit i: FE10BWeaponType row i picks a random attack variant (RFEE01 0x800BEED8)."),
        *(Field(f"p{i}", 0x18 + 2 * i, "s16", f"FE10BParam {i} (1/256)") for i in range(20)),
        *(Field(f"camera{i}", CAMERA_LISTS_OFFSET + 2 * i, "s16", f"Camera list {i}",
                "An FE10BCamList row (RFEE01 0x800A6F34).") for i in range(6)),
        Field("sound", 0x14C, "u8", "Footstep sound set", "An FE10BSFXList row."),
        Field("textures", 0x14D, "u8", "FE10BTex rows", "Set by the colour-variant tools."),
    ),
    "FE10BTex": _labels((0, "Condition"), (4, "Texture")),
}


def row_values(record: fe10_battle.BattleRecord, table: str) -> dict:
    """The fields of ``table``'s row ``record`` as a value dict."""
    strings = dict(record.strings)
    values = read_numbers(record.raw, 0, FIELDS[table])
    for f in FIELDS[table]:
        if f.kind == LABEL:
            values[f.key] = strings.get(f.offset) or ""
    return {f.key: values[f.key] for f in FIELDS[table]}


def read_rows(data: bytes, table: str) -> list[dict]:
    return [row_values(r, table) for r in fe10_battle.read_fe10_battle(data).table(table).records]


def set_row(data: bytes, table: str, index: int, **values) -> bytes:
    """``data`` with row ``index`` of ``table`` given ``values`` (field key -> value)."""
    fields = FIELDS[table]
    records = fe10_battle.read_fe10_battle(data).table(table).records
    if not 0 <= index < len(records):
        raise IndexError(f"{table} has {len(records)} rows.")
    raw = write_numbers(records[index].raw, 0, fields, values)
    by_key = {f.key: f for f in fields}
    strings = {by_key[k].offset: (str(v).strip() or "") for k, v in values.items() if by_key[k].kind == LABEL}
    return fe10_battle.update_battle_record(data, table, index, raw=raw, strings=strings)


# -- FE10BUnit motion sets -----------------------------------------------------------------------

def unit_motions(record: fe10_battle.BattleRecord) -> list[set[int]]:
    """Per FE10BWeaponType row, the FE10BMotion rows unit ``record`` may play with it."""
    out = []
    for weapon in range(WEAPON_TYPES):
        words = struct.unpack_from(">4I", record.raw, MOTIONS_OFFSET + 16 * weapon)
        out.append({32 * w + b for w, word in enumerate(words) for b in range(32) if word >> b & 1})
    return out


def set_unit_motions(data: bytes, index: int, motions: list[set[int]]) -> bytes:
    """``data`` with FE10BUnit row ``index``'s motion sets replaced (one set per weapon type)."""
    if len(motions) != WEAPON_TYPES:
        raise ValueError(f"A unit has {WEAPON_TYPES} weapon types.")
    record = fe10_battle.read_fe10_battle(data).table("FE10BUnit").records[index]
    raw = bytearray(record.raw)
    for weapon, rows in enumerate(motions):
        words = [0, 0, 0, 0]
        for motion in rows:
            if not 0 <= motion < MOTION_BITS:
                raise ValueError(f"Motion rows run from 0 to {MOTION_BITS - 1}.")
            words[motion // 32] |= 1 << (motion % 32)
        struct.pack_into(">4I", raw, MOTIONS_OFFSET + 16 * weapon, *words)
    return fe10_battle.update_battle_record(data, "FE10BUnit", index, raw=bytes(raw))


def row_names(data: bytes, table: str) -> list[str]:
    """``table``'s rows as ``code (name)`` labels, for the boxes that pick a row."""
    out = []
    for r in fe10_battle.read_fe10_battle(data).table(table).records:
        strings = dict(r.strings)
        name, code = strings.get(0) or "", strings.get(4) or ""
        out.append(f"{code} ({name})" if code and table not in ("FE10BSFXData", "FE10BFootEffect") else name or "?")
    return out
