"""``xwp/<NAME>.dbx`` - the weapon a battle actor holds (``zdbx.cmp``).

``gactor_create_weapon_instance`` opens ``xwp/<NAME>.dbx`` for the equipped
item (its IID without ``IID_``); no file means no weapon actor and bare hands.
A file has two blocks:

- ``class Model``: ``name``, ``folder`` (``xwp/<NAME>``) and ``model`` - the
  ``.cmp`` under ``files/xwp/``. Tomes have no Model block (no 3D weapon).
- ``class Weapon``: ``name``, ``model``, ``show`` (always 1 in vanilla),
  ``kind``, ``missile`` and optionally ``effectId`` (``EID_`` effect played
  with the weapon) and ``damageEffId`` (``EID_..._WP`` effect on the target).

``kind`` is also the index of the executable's category-name table
(``sw, sp, ax, ar, mg, kn, ja, ha, ms, aw, cr, br``). Its primary runtime
uses are projectile setup and motion, visual marker names, and magic-camera
loading; see ``research/docs/toInclude/battle_staging_and_camera.md``.
``missile`` controls effect placement and the special wave-impact camera.
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
    adds the Model block, leave it None for a tome. The Weapon block names the
    Model block (``name``), not the file: a mismatch such as ``model saber_r``
    under ``name SABER_R`` leaves the unit empty-handed and crashes the battle
    when the engine looks for the blade's bones (retail tables use one name)."""
    if not NAME_RE.match(name):
        raise WeaponError("Weapon name must be letters, digits and underscores.")
    lines = ["#", f"# {name}", "#", ""]
    if model:
        lines += ["{", "\tclass\tModel", f"\tname\t{name}", f"\tfolder\txwp/{name}", f"\tmodel\t{model}", "}", ""]
    lines += ["{", "\tclass\tWeapon", f"\tname\t{name}"]
    if model:
        lines.append(f"\tmodel\t{name}")
    lines += ["\tshow\t1", f"\tkind\t{int(kind)}", f"\tmissile\t{int(missile)}", "}",
              "\\"]  # every retail table ends with a lone backslash line
    text = eol.join(lines) + eol
    doc = dbx.parse(text)
    block = doc.find("Weapon")
    for key, value in (("effectId", effect_id), ("damageEffId", damage_effect_id)):
        if value:
            doc.add_field(block, key, _check(key, value))
            block = doc.find("Weapon")
    return doc.text


#: Wave blades (``kind`` 8, the Rune and Sonic Swords; ``missile`` 2) need a model with the blade's two marker
#: quads: hidden 1x1 meshes on the ``_sw1_`` / ``_sw2_`` bones at the base and the tip (draw flag 0x400). Every
#: vanilla weapon model has them except ``ironsword``, ``ironlance`` and three ``forge`` models. In game (checks
#: E1/E1m/E1t, 2026-11-25): a fire wave blade on the Iron Sword's model ends its fight with about 2.5 s of flat
#: magenta; on the Steel or Sonic Sword's model it doesn't.
HIDDEN_CHUNK = 0x400


def is_wave(table: WeaponTable) -> bool:
    return table.kind == 8 or table.missile == 2


def model_pack(text: str, files_root) -> "object | None":
    """The ``.cmp`` the Model block names (``files/<folder>/<model>.cmp``, case-insensitive), or None."""
    from pathlib import Path
    doc = dbx.parse(text)
    block = next((b for b in doc.blocks() if b.cls == "Model"), None)
    if block is None or not block.get("folder") or not block.get("model"):
        return None
    root = Path(files_root)
    folder = root / block.get("folder")
    if not folder.is_dir():
        folder = next((p for p in (root / "xwp").glob("*") if p.name.lower() == Path(block.get("folder")).name.lower()),
                      folder)
    name = f"{block.get('model')}.cmp".lower()
    return next((p for p in folder.glob("*.cmp") if p.name.lower() == name), None) if folder.is_dir() else None


def has_blade_markers(cmp_bytes: bytes) -> bool:
    """True if the weapon model has a hidden mesh (the blade's base/tip marker quads)."""
    from . import gs_file, lz10, pak
    data = lz10.decompress(cmp_bytes) if cmp_bytes[:1] == b"\x10" else cmp_bytes
    for entry in pak.read_pak_entries(data):
        if entry.name.lower().endswith(".gs"):
            gs = gs_file.read_gs(pak.read_pak_file_content(data, entry))
            return any(chunk.flags & HIDDEN_CHUNK for chunk in gs.chunks)
    return False


def wave_model_problem(text: str, files_root) -> str | None:
    """Why this table's wave blade would flash magenta at the end of its fights, or None."""
    try:
        table = read_weapon(text)
    except WeaponError:
        return None
    if not is_wave(table):
        return None
    pack = model_pack(text, files_root)
    if pack is None:
        return None
    try:
        if has_blade_markers(pack.read_bytes()):
            return None
    except Exception:  # noqa: BLE001 - an unreadable model is reported elsewhere
        return None
    return (f"{pack.parent.name}/{pack.name} has no blade markers (hidden quads at the base and tip of the "
            f"blade): a wave blade on it ends its fights with a magenta screen. Use a model that has them, such as the Steel or "
            f"Sonic Sword's.")
