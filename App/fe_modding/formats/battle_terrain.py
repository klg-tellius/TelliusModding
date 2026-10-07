"""``zbg/<scenery>/bf.cmp:map.bin`` - where a battle backdrop's models stand.

A battle backdrop is loaded as a map in battle mode (``load_map_data`` with
``map_mode`` 1, from ``load_battle_terrain_preview_map``). Its ``map.bin`` is
a relocatable resource (``load_relocatable_resource``: a 0x20-byte header,
the data, the relocation offsets, then ``(data offset, name offset)``
symbols and their names) holding the ``...B`` sections:

- ``mapcapacityB``: u16 width, height (tiles; 1 x 1 in vanilla), model count,
  instance count, then a float.
- ``mapbuilddescB``: per model, six floats (its bounding box: min xyz, max
  xyz), a flag word and a pointer to its name (``<name>.g`` / ``<name>.gs``
  in the pack, textured from ``texpack.tpl``).
- ``mapbuildinstB``: per placed instance, 12 bytes: signed tile x and y, an
  angle byte, the model index, four more bytes (a second tile pair, unread
  here) and a big-endian float height.
- ``mapextraB``, ``mapfogB``, ``maplightB``: not used here.

``expand_mapbuildinst_records`` places each instance with
``T(5 s x, -5 s h, 5 s y) * Scale(s) * T(2.5, 0, 2.5) * RotY(angle) *
T(-2.5, 0, -2.5)``, where ``s`` is the battle map's tile scale (3.0,
``0x80368F20``), ``angle = 360 - byte * 360 / 256`` degrees, and in battle
mode the tile is first moved by minus half the map size (0 for 1 x 1 maps).
The map's own matrix is the identity in battle mode, so this is the
backdrop's world placement around the fighters (who stand at x = -20 / +20).
"""

from __future__ import annotations

import math
import struct
from dataclasses import dataclass

TILE = 5.0
PIVOT = 2.5
BATTLE_SCALE = 3.0


class BattleTerrainError(ValueError):
    pass


@dataclass(frozen=True)
class TerrainModel:
    name: str
    bounds: tuple  # min x, y, z, max x, y, z
    flags: int


@dataclass(frozen=True)
class TerrainInstance:
    x: int
    y: int
    angle: int  # byte; degrees = 360 - angle * 360 / 256
    model: int
    height: float

    def matrix(self, width: int = 1, height_tiles: int = 1, scale: float = BATTLE_SCALE) -> list:
        """The 3 x 4 world matrix (rows) of this instance."""
        degrees = 360.0 - self.angle * 360.0 / 256.0
        c, s = math.cos(math.radians(degrees)), math.sin(math.radians(degrees))
        tx = (self.x - width // 2) * TILE * scale
        tz = (self.y - height_tiles // 2) * TILE * scale
        ty = -self.height * TILE * scale
        # Scale * T(pivot) * RotY * T(-pivot)
        rot = [[c, 0.0, s], [0.0, 1.0, 0.0], [-s, 0.0, c]]
        pivot = (PIVOT, 0.0, PIVOT)
        offset = [pivot[i] - sum(rot[i][j] * pivot[j] for j in range(3)) for i in range(3)]
        return [[rot[i][0] * scale, rot[i][1] * scale, rot[i][2] * scale, offset[i] * scale + t]
                for i, t in enumerate((tx, ty, tz))]


@dataclass(frozen=True)
class BattleTerrain:
    width: int
    height: int
    models: tuple
    instances: tuple


def _symbols(data: bytes) -> tuple[bytes, dict]:
    if len(data) < 0x20:
        raise BattleTerrainError("map.bin is too short.")
    _size, data_size, relocs, count = struct.unpack(">4I", data[:16])
    body = data[0x20:0x20 + data_size]
    table = 0x20 + data_size + 4 * relocs
    strings = table + 8 * count
    symbols = {}
    for i in range(count):
        offset, name = struct.unpack(">II", data[table + 8 * i:table + 8 * i + 8])
        end = data.index(b"\0", strings + name)
        symbols[data[strings + name:end].decode("ascii", "replace")] = offset
    return body, symbols


def read_battle_terrain(data: bytes) -> BattleTerrain:
    body, symbols = _symbols(data)
    for key in ("mapcapacityB", "mapbuilddescB", "mapbuildinstB"):
        if key not in symbols:
            raise BattleTerrainError(f"map.bin has no {key} section.")
    width, height, model_count, instance_count = struct.unpack_from(">4H", body, symbols["mapcapacityB"])
    models = []
    at = symbols["mapbuilddescB"]
    for _ in range(model_count):
        *bounds, flags, name_at = struct.unpack_from(">6fII", body, at)
        name = body[name_at:body.index(b"\0", name_at)].decode("ascii", "replace")
        models.append(TerrainModel(name, tuple(bounds), flags))
        at += 0x20
    instances = []
    at = symbols["mapbuildinstB"]
    for _ in range(instance_count):
        x, y, angle, model = struct.unpack_from(">bbBB", body, at)
        (lift,) = struct.unpack_from(">f", body, at + 8)
        instances.append(TerrainInstance(x, y, angle, model, lift))
        at += 12
    return BattleTerrain(width, height, tuple(models), tuple(instances))
