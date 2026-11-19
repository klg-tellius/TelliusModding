"""Radiant Dawn's battle weapons: the 36-byte ``FE10BWeapon`` rows of ``FE10Battle.cms``.

Path of Radiance keeps one ``xwp/<NAME>.dbx`` table per weapon in ``zdbx.cmp``
(:mod:`formats.battle_weapons`); Radiant Dawn keeps one row per weapon actor here. Each string field
is a relocated label (null when absent):

- +0x00 the row's Japanese name (``鉄の剣``);
- +0x04 the weapon key (``IRONSWORD``, the name Path of Radiance files its table under; an arrow row
  names the bow, ``IRONBOW``);
- +0x08 the model, ``xwp/<model>/<model>.cmp`` in lower case (null: no 3D weapon, as on laguz rows);
- +0x0C / +0x10 the hit and critical-hit effects (``EID_K_ATTK1``, ``EID_K_CRIT1``);
- +0x14 the weapon's own effect (Path of Radiance's ``effectId``: ``EID_K_FIRE``, ``EID_K_RAGNELL``);
- +0x18 the effect on the target (``EID_K_HEAD_FIRE``; Path of Radiance's ``damageEffId``);
- +0x1C the magic class name (``光魔法``) on a few rows.

+0x20 is an index into ``FE10BWeaponType`` (1 ``sw`` sword, 2 ``sp`` lance, 3 ``ax`` axe, 9 ``mg``
magic...). +0x21 holds actor flags 0x01/0x02/0x04/0x08 (set on thrown weapons, arrows and breaths) and
+0x22 a u16 scale; the Battle Data page edits both (:mod:`formats.fe10_battle_fields`).
"""

from __future__ import annotations

from dataclasses import dataclass, replace

from . import fe10_battle

TABLE = "FE10BWeapon"
#: field key -> row offset of its label
STRING_FIELDS = {"name": 0x00, "key": 0x04, "model": 0x08, "hit": 0x0C, "crit": 0x10, "effect": 0x14,
                 "target": 0x18, "magic": 0x1C}
TYPE_OFFSET, SECOND_OFFSET = 0x20, 0x21


@dataclass(frozen=True)
class Fe10Weapon:
    index: int
    labels: dict  # STRING_FIELDS key -> value or None
    type: int
    second: int

    def label(self) -> str:
        """``IRONSWORD #12``: unique, since several rows share a key."""
        return f"{self.labels.get('key') or self.labels.get('name') or '?'} #{self.index}"


def weapon_types(data: bytes) -> dict[int, str]:
    """FE10BWeaponType: index -> ``sw (剣)``."""
    rows = fe10_battle.read_fe10_battle(data).table("FE10BWeaponType").records
    return {i: f"{dict(r.strings).get(4) or '?'} ({dict(r.strings).get(0) or ''})" for i, r in enumerate(rows)}


def read_weapons(data: bytes) -> list[Fe10Weapon]:
    rows = fe10_battle.read_fe10_battle(data).table(TABLE).records
    out = []
    for i, r in enumerate(rows):
        strings = dict(r.strings)
        out.append(Fe10Weapon(i, {key: strings.get(at) for key, at in STRING_FIELDS.items()},
                              r.raw[TYPE_OFFSET], r.raw[SECOND_OFFSET]))
    return out


def set_weapon(data: bytes, index: int, *, labels: dict | None = None, type: int | None = None) -> bytes:
    """``data`` with row ``index``'s labels (``""``/None: null) and type changed; other bytes kept."""
    record = fe10_battle.read_fe10_battle(data).table(TABLE).records[index]
    raw = bytearray(record.raw)
    if type is not None:
        if not 0 <= type <= 255:
            raise ValueError("The weapon type is a byte (0-255).")
        raw[TYPE_OFFSET] = type
    strings = {STRING_FIELDS[key]: (value or None) for key, value in (labels or {}).items()}
    return fe10_battle.update_battle_record(data, TABLE, index, raw=bytes(raw), strings=strings)


def add_weapon(data: bytes, copy_of: int, key: str, *, model: str | None = None,
               labels: dict | None = None) -> tuple[bytes, int]:
    """Append a copy of row ``copy_of`` whose key is ``key`` (the item ID without ``IID_``, as the
    battle looks it up) and whose model is ``model`` (an ``xwp/`` folder; None: the copied row's).
    ``labels`` overrides other string fields (``"hit"``, ``"effect"``...; None or "" clears one).
    Returns the file and the new row's index."""
    document = fe10_battle.read_fe10_battle(data)
    table = document.table(TABLE)
    if not 0 <= copy_of < len(table.records):
        raise IndexError("FE10BWeapon row index is out of range.")
    if not key or any(dict(r.strings).get(STRING_FIELDS["key"], "").upper() == key.upper() for r in table.records):
        raise ValueError(f"FE10BWeapon already has a row for {key!r}.")
    source = table.records[copy_of]
    strings = dict(source.strings)
    strings[STRING_FIELDS["key"]] = key
    if model is not None:
        strings[STRING_FIELDS["model"]] = model
    for name, value in (labels or {}).items():
        strings[STRING_FIELDS[name]] = value or None  # None: a null pointer
    clone = replace(source, address=0, strings=tuple(sorted(strings.items())))
    records = table.records + (clone,)
    return fe10_battle.build_fe10_battle(fe10_battle._replace_table(document, TABLE, records)), len(table.records)


def remove_weapon(data: bytes, index: int, vanilla_rows: int) -> bytes:
    """Drop an added row (``index >= vanilla_rows``); the game's own rows are refused."""
    document = fe10_battle.read_fe10_battle(data)
    table = document.table(TABLE)
    if not vanilla_rows <= index < len(table.records):
        raise ValueError("Only added FE10BWeapon rows can be removed.")
    records = table.records[:index] + table.records[index + 1:]
    return fe10_battle.build_fe10_battle(fe10_battle._replace_table(document, TABLE, records))
