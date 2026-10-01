"""``xwp/<NAME>.dbx`` - the weapon a battle actor holds (``zdbx.cmp``).

``gactor_create_weapon_instance`` opens ``xwp/<NAME>.dbx`` for the equipped
item (its IID without ``IID_``); no file means no weapon actor and bare hands.
A file has two blocks:

- ``class Model``: ``name``, ``folder`` (``xwp/<NAME>``) and ``model`` - the
  ``.cmp`` under ``files/xwp/``. Tomes have no Model block (no 3D weapon).
- ``class Weapon``: ``name``, ``model``, ``show`` (always 1 in vanilla),
  ``kind``, ``missile`` and optionally ``effectId`` (``EID_`` effect played
  with the weapon) and ``damageEffId`` (``EID_..._WP`` effect on the target).

``kind`` and ``missile`` meanings below are read off the vanilla files (every
weapon of a type shares the code); the engine's use of the values is not
traced further.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from . import dbx

NAME_RE = re.compile(r"^[A-Za-z0-9_]+$")
EFFECT_RE = re.compile(r"^EID_[A-Za-z0-9_]+$")

KINDS = {
    0: "Sword", 1: "Lance", 2: "Axe", 3: "Bow", 4: "Tome (no model)", 5: "Knife",
    6: "Thrown spear", 7: "Thrown axe / sword", 8: "Wave blade (Rune/Sonic sword)",
    9: "Arrow", 10: "Claw (beast)", 11: "Breath (dragon)",
}
MISSILES = {0: "Melee", 1: "Projectile", 2: "Special (wave)"}


class WeaponError(dbx.DbxError):
    pass


@dataclass(frozen=True)
class WeaponTable:
    name: str
    model_folder: str | None  # Model block ``folder`` (None: no Model block)
    model: str | None
    show: int
    kind: int
    missile: int
    effect_id: str | None
    damage_effect_id: str | None


def read_weapon(text: str) -> WeaponTable:
    doc = dbx.parse(text)
    try:
        weapon = doc.find("Weapon")
    except dbx.DbxError as exc:
        raise WeaponError("No Weapon block.") from exc
    model = next((b for b in doc.blocks() if b.cls == "Model"), None)
    try:
        return WeaponTable(
            name=weapon.name or "",
            model_folder=model.get("folder") if model else None,
            model=weapon.get("model") or (model.get("model") if model else None),
            show=int(weapon.get("show", "1")),
            kind=int(weapon.get("kind", "0")),
            missile=int(weapon.get("missile", "0")),
            effect_id=weapon.get("effectId"),
            damage_effect_id=weapon.get("damageEffId"),
        )
    except ValueError as exc:
        raise WeaponError(f"Bad number in Weapon block: {exc}") from exc


def _check(field: str, value: str) -> str:
    value = str(value).strip()
    if field in ("show", "kind", "missile"):
        if not value.lstrip("-").isdigit():
            raise WeaponError(f"{field} must be a whole number.")
    elif field in ("effectId", "damageEffId"):
        if value and not EFFECT_RE.match(value):
            raise WeaponError(f"{field} must be an EID_ name.")
    else:
        raise WeaponError(f"Unknown weapon field {field!r}.")
    return value


def set_weapon_field(text: str, field: str, value: str) -> str:
    """Set (or add) one field of the ``Weapon`` block. An empty ``effectId`` /
    ``damageEffId`` removes the line."""
    value = _check(field, value)
    doc = dbx.parse(text)
    block = doc.find("Weapon")
    existing = next((f for f in block.fields if f.key == field), None)
    if existing is None:
        if value:
            doc.add_field(block, field, value)
    elif value:
        doc.set_value(existing, value)
    else:
        doc.remove_field(existing)
    return doc.text


def new_weapon_dbx(name: str, *, kind: int, missile: int, model: str | None = None,
                   effect_id: str | None = None, damage_effect_id: str | None = None,
                   eol: str = "\r\n") -> str:
    """A fresh ``xwp/<NAME>.dbx``; ``model`` (a ``.cmp`` under ``files/xwp/<name>/``)
    adds the Model block, leave it None for a tome."""
    if not NAME_RE.match(name):
        raise WeaponError("Weapon name must be letters, digits and underscores.")
    lines = ["#", f"# {name}", "#", ""]
    if model:
        lines += ["{", "\tclass\tModel", f"\tname\t{name}", f"\tfolder\txwp/{name}", f"\tmodel\t{model}", "}", ""]
    lines += ["{", "\tclass\tWeapon", f"\tname\t{name}"]
    if model:
        lines.append(f"\tmodel\t{model}")
    lines += ["\tshow\t1", f"\tkind\t{int(kind)}", f"\tmissile\t{int(missile)}", "}"]
    text = eol.join(lines) + eol
    doc = dbx.parse(text)
    block = doc.find("Weapon")
    for key, value in (("effectId", effect_id), ("damageEffId", damage_effect_id)):
        if value:
            doc.add_field(block, key, _check(key, value))
            block = doc.find("Weapon")
    return doc.text
