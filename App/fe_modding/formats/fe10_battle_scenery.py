"""Radiant Dawn's battle sceneries: the 24-byte ``FE10BMapModel`` rows of ``FE10Battle.cms``.

Path of Radiance keeps one ``zbg/<scenery>/param.dbx`` per backdrop (:mod:`formats.battle_scenery`:
indoor flag, footstep effect and sound). Radiant Dawn keeps one row per placed backdrop model here;
``FE10BMapData`` picks up to five rows per battle background (see :mod:`formats.fe10_battle`).
RFEE01 reads a row in ``0x800AA548`` (scenery setup), ``0x800AB310`` / ``0x80185D0C`` (the battle
weather), ``0x800A95F4`` (flight height), ``0x800ABA28`` (the run-in) and ``0x800BA2C8`` (footsteps):

- +0x00 the ``zbg/`` folder of the model, +0x04 the map's sound group (``SND_GROUP_C0101``).
- +0x08 flag bits (:data:`FLAGS`): 0x02 indoors (the map's weather effect and sky are not
  applied), 0x08 mirrored (drawn with X scale -1), 0x10 the fighters may run in (the 突撃 motion, on
  variants 0 and 2 only), 0x20 / 0x40 when they run in, mirror the model / turn it 180 degrees.
  0x01 and 0x04 are set on vanilla rows but no reader was found.
- +0x09 flight height for the aerial variants (2 and 3); 0 uses FE10BSetup ``上空高度``.
- +0x0A move limit, +0x0B camera limit; 0 uses FE10BSetup ``移動限界`` (50) / ``カメラ限界`` (40).
- +0x0C the ``FE10BFootEffect`` row (dust, water spray, snow...) played under the fighters' feet.
- +0x0D the ground for footstep sounds: the column of the fighter's ``FE10BSFXList`` row
  (:data:`GROUNDS`); the unit's row is FE10BUnit +0x14C.
- +0x0E / +0x10 / +0x12 signed x, y, z position (world units), +0x14 signed Y rotation (degrees),
  +0x16 signed scale in 1/256 (0 means 3.0, the vanilla value is 0x300).
"""

from __future__ import annotations

import struct
from dataclasses import dataclass

from . import fe10_battle

TABLE = "FE10BMapModel"
FLAGS = {0x01: "Flag 0x01 (no reader found)", 0x02: "Indoors (no weather or sky)",
         0x04: "Flag 0x04 (no reader found)", 0x08: "Mirrored",
         0x10: "Fighters run in", 0x20: "Mirror when they run in", 0x40: "Turn 180° when they run in"}
#: FE10BSFXList columns (the vanilla FE10BSFXData names: 平地, 砂, 水, 雪, 雨, 床, コイン, 床)
GROUNDS = {0: "Plain", 1: "Sand", 2: "Water", 3: "Snow", 4: "Rain", 5: "Floor", 6: "Coins", 7: "Floor (2)"}
#: FE10BFootEffect rows by their vanilla names (なし, 砂煙, 砂煙(夜), 水煙, 雪煙, 雨煙, コイン)
FOOT_EFFECT_NAMES = {"なし": "None", "砂煙": "Dust", "砂煙(夜)": "Dust (night)", "水煙": "Water spray",
                     "雪煙": "Snow spray", "雨煙": "Rain spray", "コイン": "Coins"}
#: field -> row offset of its byte
BYTE_FIELDS = {"flags": 0x08, "flight_height": 0x09, "move_limit": 0x0A, "camera_limit": 0x0B,
               "foot_effect": 0x0C, "ground": 0x0D}
SCALE_UNIT = 256.0
DEFAULT_SCALE = 3.0


@dataclass(frozen=True)
class SceneryModel:
    index: int
    folder: str
    sound_group: str
    flags: int
    flight_height: int
    move_limit: int
    camera_limit: int
    foot_effect: int
    ground: int
    position: tuple[int, int, int]
    rotation: int
    scale: int  # in 1/256; 0 means DEFAULT_SCALE

    def label(self) -> str:
        """``bg0101twn #1``: unique, since a folder has several rows."""
        return f"{self.folder or '?'} #{self.index}"

    @property
    def indoors(self) -> bool:
        return bool(self.flags & 0x02)

    def scale_value(self) -> float:
        return self.scale / SCALE_UNIT if self.scale else DEFAULT_SCALE

    def flag_names(self) -> list[str]:
        return [name for bit, name in FLAGS.items() if self.flags & bit]


def read_sceneries(data: bytes) -> list[SceneryModel]:
    out = []
    for i, r in enumerate(fe10_battle.read_fe10_battle(data).table(TABLE).records):
        strings = dict(r.strings)
        raw = r.raw
        out.append(SceneryModel(
            i, strings.get(0, ""), strings.get(4, ""), raw[8], raw[9], raw[10], raw[11], raw[12], raw[13],
            struct.unpack_from(">3h", raw, 0x0E), struct.unpack_from(">h", raw, 0x14)[0],
            struct.unpack_from(">h", raw, 0x16)[0]))
    return out


def foot_effects(data: bytes) -> dict[int, str]:
    """FE10BFootEffect: row -> ``Dust (砂煙)``."""
    rows = fe10_battle.read_fe10_battle(data).table("FE10BFootEffect").records
    out = {}
    for i, r in enumerate(rows):
        name = dict(r.strings).get(0) or ""
        out[i] = f"{FOOT_EFFECT_NAMES[name]} ({name})" if name in FOOT_EFFECT_NAMES else name or "?"
    return out


def map_uses(data: bytes) -> dict[int, list[tuple[str, int]]]:
    """Model row -> the (FE10BMapData background name, variant) pairs that pick it."""
    out: dict[int, list[tuple[str, int]]] = {}
    for record in fe10_battle.read_fe10_battle(data).map_data:
        for variant, model in enumerate(record.model_indices):
            if model is not None:
                out.setdefault(model, []).append((record.map_name, variant))
    return out


def set_scenery(data: bytes, index: int, **fields: int) -> bytes:
    """``data`` with row ``index``'s byte fields (:data:`BYTE_FIELDS`), ``position`` (x, y, z),
    ``rotation`` or ``scale`` changed; every other byte is kept."""
    out = bytearray(data)
    at = fe10_battle._row_offset(data, TABLE, index)
    for key, value in fields.items():
        if key in BYTE_FIELDS:
            if not 0 <= int(value) <= 255:
                raise ValueError(f"{key.replace('_', ' ')} is a byte (0-255).")
            out[at + BYTE_FIELDS[key]] = int(value)
        elif key == "position":
            values = tuple(int(v) for v in value)
            if len(values) != 3 or any(not -32768 <= v <= 32767 for v in values):
                raise ValueError("The position is three whole numbers from -32768 to 32767.")
            struct.pack_into(">3h", out, at + 0x0E, *values)
        elif key in ("rotation", "scale"):
            if not -32768 <= int(value) <= 32767:
                raise ValueError(f"The {key} is a whole number from -32768 to 32767.")
            struct.pack_into(">h", out, at + (0x14 if key == "rotation" else 0x16), int(value))
        else:
            raise ValueError(f"Unknown scenery field {key!r}.")
    return bytes(out)
