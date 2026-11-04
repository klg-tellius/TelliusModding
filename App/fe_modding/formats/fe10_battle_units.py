"""Radiant Dawn's battle unit parameters: the 340-byte ``FE10BUnit`` rows of ``FE10Battle.cms``.

Path of Radiance keeps them in ``zu/<code>_prm.dbx`` (:mod:`formats.battle_params`: speed, range,
jump attacks, flying, size). Radiant Dawn keeps one row per battle model description here:

- +0x00 the description (``剣士一般``), +0x04 the model code (``swoL``, the ``zu/`` model).
- +0x10 a flag mask: bit ``i`` is ``FE10BFlags`` row ``i`` (大型 large, 飛行系 flying...). RFEE01
  ``0x800A7460`` (row, flag name) finds the name's row and tests that bit.
- +0x18 twenty signed 16-bit values in 1/256, value ``i`` named by ``FE10BParam`` row ``i`` (補間比率,
  間合い, 命中高度...). ``0x800A7370`` (row, parameter name) finds the name's row and returns
  ``value / 256``; an unknown name gives 0.
- +0x14C the footstep sound set, an ``FE10BSFXList`` row (一般 normal, 鎧系 armour, 下級馬系 horse...);
  the scenery's ground byte picks the column (``0x800BA2C8``, see :mod:`formats.fe10_battle_scenery`).
- +0x14D the number of ``FE10BTex`` rows the unit owns (edited by the colour-variant tools).

The game looks flags and parameters up by name, so each row's meaning is its name in those two
tables; what each one does in a fight is not traced further.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass

from . import fe10_battle

TABLE = "FE10BUnit"
FLAGS_OFFSET, PARAMS_OFFSET, SOUND_OFFSET = 0x10, 0x18, 0x14C
PARAM_COUNT = 20
PARAM_UNIT = 256.0
#: English labels of the vanilla FE10BParam names
PARAM_LABELS = {
    "補間比率": "Blend ratio", "間合い": "Attack range", "命中高度": "Hit height", "命中位置": "Hit position",
    "注目限界": "Look-at limit", "移動速度": "Move speed", "移動比率": "Move ratio", "初期位置": "Start position",
    "高さ": "Height", "回転": "Rotation", "目パチ比率": "Blink rate", "カメラ比率": "Camera ratio",
    "カメラ高度": "Camera height", "スキップ時間": "Skip time", "スケールＸ": "Scale X", "スケールＹ": "Scale Y",
    "スケールＺ": "Scale Z", "２Ｄ回転": "2D rotation", "２Ｄ高度": "2D height", "２Ｄスケール": "2D scale",
}
#: English labels of the vanilla FE10BFlags names
FLAG_LABELS = {
    "大型": "Large", "飛行系": "Flying", "左利き": "Left-handed", "二刀流": "Two weapons",
    "カメラ反転": "Camera flipped", "重量級": "Heavy", "回避弾き": "Parries when dodging",
    "首回転の連動": "Head follows body", "逆手持ち": "Reverse grip", "獣系": "Beast",
    "強制構え": "Always on guard", "強制素手": "Always bare-handed", "止め停止": "Stops on the finishing blow",
    "回避攻撃": "Attacks when dodging", "アピール切替": "Switches pose", "中心配置": "Stands at the centre",
    "位置固定": "Fixed position", "サウンド判定": "Sound check",
}
#: English labels of the vanilla FE10BSFXList names
SOUND_LABELS = {
    "なし": "None", "一般": "Normal", "鎧系": "Armour", "軽量系": "Light", "重量系": "Heavy",
    "超重量系": "Very heavy", "ミカヤ": "Micaiah", "下級馬系": "Horse", "上級馬系": "Promoted horse",
    "獅子、虎系": "Lion or tiger", "猫、狼系": "Cat or wolf", "獅子系": "Lion", "虎系": "Tiger", "猫系": "Cat",
    "狼系": "Wolf", "竜系": "Dragon (laguz)", "ラフィエル": "Rafiel", "ペガサス系": "Pegasus",
    "ドラゴン系": "Wyvern",
}


@dataclass(frozen=True)
class BattleUnit:
    index: int
    description: str
    model: str
    flags: int
    params: tuple[int, ...]  # raw, in 1/256
    sound: int

    def label(self) -> str:
        return f"{self.model or '?'} #{self.index}"

    def value(self, param: int) -> float:
        return self.params[param] / PARAM_UNIT


def _labelled(name: str, labels: dict[str, str]) -> str:
    return f"{labels[name]} ({name})" if name in labels else name or "?"


def param_names(data: bytes) -> list[str]:
    """FE10BParam names as labels (``Attack range (間合い)``), by value index."""
    rows = fe10_battle.read_fe10_battle(data).table("FE10BParam").records
    return [_labelled(dict(r.strings).get(0) or "", PARAM_LABELS) for r in rows][:PARAM_COUNT]


def flag_names(data: bytes) -> list[str]:
    """FE10BFlags names as labels, by bit."""
    rows = fe10_battle.read_fe10_battle(data).table("FE10BFlags").records
    return [_labelled(dict(r.strings).get(0) or "", FLAG_LABELS) for r in rows][:32]


def sound_sets(data: bytes) -> dict[int, str]:
    """FE10BSFXList: row -> label."""
    rows = fe10_battle.read_fe10_battle(data).table("FE10BSFXList").records
    return {i: _labelled(dict(r.strings).get(0) or "", SOUND_LABELS) for i, r in enumerate(rows)}


def read_units(data: bytes) -> list[BattleUnit]:
    out = []
    for i, r in enumerate(fe10_battle.read_fe10_battle(data).table(TABLE).records):
        strings = dict(r.strings)
        out.append(BattleUnit(
            i, strings.get(0, ""), strings.get(4, ""),
            struct.unpack_from(">I", r.raw, FLAGS_OFFSET)[0],
            struct.unpack_from(f">{PARAM_COUNT}h", r.raw, PARAMS_OFFSET), r.raw[SOUND_OFFSET]))
    return out


def to_raw(value: float | str) -> int:
    """A parameter as the game stores it (1/256 steps, rounded)."""
    try:
        number = float(str(value).strip())
    except ValueError as exc:
        raise ValueError(f"{value!r} is not a number.") from exc
    raw = round(number * PARAM_UNIT)
    if not -32768 <= raw <= 32767:
        raise ValueError(f"{number} is outside -128 to 127.99.")
    return raw


def set_unit(data: bytes, index: int, *, flags: int | None = None,
             params: dict[int, int] | None = None, sound: int | None = None) -> bytes:
    """``data`` with row ``index``'s flag mask, raw parameters (value index -> 1/256 steps) or
    sound set changed; every other byte is kept."""
    out = bytearray(data)
    at = fe10_battle._row_offset(data, TABLE, index)
    if flags is not None:
        if not 0 <= flags <= 0xFFFFFFFF:
            raise ValueError("The flags are a 32-bit mask.")
        struct.pack_into(">I", out, at + FLAGS_OFFSET, flags)
    for param, raw in (params or {}).items():
        if not 0 <= param < PARAM_COUNT:
            raise IndexError(f"There are {PARAM_COUNT} parameters.")
        if not -32768 <= raw <= 32767:
            raise ValueError("A parameter is a signed 16-bit value.")
        struct.pack_into(">h", out, at + PARAMS_OFFSET + 2 * param, raw)
    if sound is not None:
        sounds = len(fe10_battle.read_fe10_battle(data).table("FE10BSFXList").records)
        if not 0 <= sound < sounds:
            raise ValueError(f"The sound set is an FE10BSFXList row (0-{sounds - 1}).")
        out[at + SOUND_OFFSET] = sound
    return bytes(out)
