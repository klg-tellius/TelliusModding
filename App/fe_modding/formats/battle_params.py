"""``zu/<code>_prm.dbx`` tuning keys - how a battle model moves and fights.

A ``_prm.dbx`` is one ``class Param`` block: ``name``, the texture lines
(``texnum N`` and N lines, edited by ``zdbx.set_param_texture``) and these
optional tuning keys (Japanese key names as in the files):

- ``移動速度`` move speed, ``間合い`` attack range, ``ルートスケール`` root
  scale, ``ダメージ後退`` knockback when hit (floats).
- ``走り回数`` run count, ``補間速度`` / ``待機補間速度`` / ``移動補間速度``
  animation blend speed in general / standing / moving (whole numbers).
- Flags, present as ``1`` or absent: ``ジャンプ攻撃``, ``ジャンプ攻撃２``,
  ``ジャンプ必殺``, ``ジャンプ止め``, ``ジャンプ奥義`` (the attack variants
  that jump), ``飛行系`` (flying unit), ``大型`` (large unit),
  ``止め飛び去り`` (flies away on the finishing blow).

Vanilla values: move speed 0.15-1.0, range 10-22, knockback 0.1 or 1.0,
blend speeds 10-30. The engine's exact units were not measured.
"""

from __future__ import annotations

from dataclasses import dataclass

from . import dbx

FLOAT_KEYS = {"移動速度": "Move speed", "間合い": "Attack range", "ルートスケール": "Root scale",
              "ダメージ後退": "Knockback"}
INT_KEYS = {"走り回数": "Run count", "補間速度": "Blend speed", "待機補間速度": "Standing blend speed",
            "移動補間速度": "Moving blend speed"}
FLAG_KEYS = {"ジャンプ攻撃": "Jump attack", "ジャンプ攻撃２": "Jump attack 2", "ジャンプ必殺": "Jump critical",
             "ジャンプ止め": "Jump finisher", "ジャンプ奥義": "Jump skill", "飛行系": "Flying",
             "大型": "Large", "止め飛び去り": "Flies away on finisher"}
REQUIRED = ("移動速度",)
TUNING = {**FLOAT_KEYS, **INT_KEYS, **FLAG_KEYS}


class ParamError(dbx.DbxError):
    pass


@dataclass(frozen=True)
class UnitParams:
    name: str
    values: dict  # tuning key -> raw text, only the keys the file has

    def get(self, key: str) -> str:
        return self.values.get(key, "")


def read_params(text: str) -> UnitParams:
    try:
        block = dbx.parse(text).find("Param")
    except dbx.DbxError as exc:
        raise ParamError("No Param block.") from exc
    return UnitParams(block.name or "", {f.key: f.value for f in block.fields if f.key in TUNING})


def _check(key: str, value: str) -> str:
    value = str(value).strip()
    if key in FLAG_KEYS:
        if value in ("", "0"):
            return ""
        if value != "1":
            raise ParamError(f"{key} must be 1 (on) or 0 (off).")
        return "1"
    if not value:
        if key in REQUIRED:
            raise ParamError(f"{key} cannot be empty.")
        return ""
    try:
        number = float(value) if key in FLOAT_KEYS else int(value)
    except ValueError as exc:
        kind = "a number" if key in FLOAT_KEYS else "a whole number"
        raise ParamError(f"{key} must be {kind}.") from exc
    if number < 0:
        raise ParamError(f"{key} cannot be negative.")
    return value


def set_param(text: str, key: str, value: str) -> str:
    """Set, add or (empty value, or 0 for a flag) remove one tuning key."""
    if key not in TUNING:
        raise ParamError(f"Unknown parameter {key!r}.")
    value = _check(key, value)
    doc = dbx.parse(text)
    try:
        block = doc.find("Param")
    except dbx.DbxError as exc:
        raise ParamError("No Param block.") from exc
    existing = next((f for f in block.fields if f.key == key), None)
    if existing is None:
        if value:
            doc.add_field(block, key, value)
    elif not value:
        doc.remove_field(existing)
    elif existing.value != value:
        doc.set_value(existing, value)
    return doc.text
