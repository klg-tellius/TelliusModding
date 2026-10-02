"""Where a unit can move: a cheapest-path search over the map.

Entering a tile costs its terrain type's ``move_costs[movement_type]``
(``fe8data.TerrainType``; 255 can't be entered). A step between two tiles
must also be open in the map's composed link grid
(``map_file.link_tiles_are_adjacent_passable``, the engine's own check).
Units can pass through tiles of units that aren't hostile to them but not
stop there, and never pass through hostile units. A unit deployed with the
bridge-barrier flag (``dispo.FLAG_BRIDGE_BARRIER``) can't enter terrain
type 55.
"""

from __future__ import annotations

import heapq
from typing import Optional

from ..formats import dispo
from .state import GameState, SimUnit, hostile
from .world import IMPASSABLE, World

BRIDGE_COVER_TERRAIN = 55
NEIGHBOURS = ((0, -1), (1, 0), (0, 1), (-1, 0))


def _blocked_terrain(world: World, unit: SimUnit, x: int, y: int) -> bool:
    if unit.flags & dispo.FLAG_BRIDGE_BARRIER and "fly" not in unit.categories:
        t = world.terrain_at(x, y)
        return t is not None and t.index == BRIDGE_COVER_TERRAIN
    return False


def search(world: World, state: GameState, unit: SimUnit, budget: Optional[int] = None,
           start: Optional[tuple] = None) -> dict:
    """Every tile ``unit`` can reach within ``budget`` movement (its Mov by
    default) from ``start`` (its tile): ``{tile: (cost, previous tile)}``.
    Occupied tiles are included when they can be passed through."""
    budget = unit.move if budget is None else budget
    start = start or unit.tile
    best = {start: (0, None)}
    heap = [(0, start)]
    blockers = {u.tile: u for u in state.units.values() if u.on_map and u.uid != unit.uid}
    while heap:
        cost, (x, y) = heapq.heappop(heap)
        if cost > best[(x, y)][0]:
            continue
        for dx, dy in NEIGHBOURS:
            nx, ny = x + dx, y + dy
            step = world.move_cost(nx, ny, unit.movement_type)
            if (nx, ny) in state.opened and world.inside(nx, ny):
                step = 1  # an opened door
            if step >= IMPASSABLE or _blocked_terrain(world, unit, nx, ny):
                continue
            if not world.linked(x, y, nx, ny):
                continue
            other = blockers.get((nx, ny))
            if other is not None and hostile(unit.faction, other.faction):
                continue
            total = cost + step
            if total > budget:
                continue
            if (nx, ny) not in best or total < best[(nx, ny)][0]:
                best[(nx, ny)] = (total, (x, y))
                heapq.heappush(heap, (total, (nx, ny)))
    return best


def destinations(world: World, state: GameState, unit: SimUnit, budget: Optional[int] = None,
                 start: Optional[tuple] = None) -> dict:
    """The tiles ``unit`` can stop on: :func:`search` without other units' tiles."""
    found = search(world, state, unit, budget, start)
    occupied = {u.tile for u in state.units.values() if u.on_map and u.uid != unit.uid}
    return {tile: v for tile, v in found.items() if tile not in occupied}


def path(found: dict, tile: tuple) -> list:
    """The tiles from the search's start to ``tile``, both included."""
    if tile not in found:
        return []
    out = []
    while tile is not None:
        out.append(tile)
        tile = found[tile][1]
    return out[::-1]


def distance(a: tuple, b: tuple) -> int:
    return abs(a[0] - b[0]) + abs(a[1] - b[1])


def tiles_in_range(world: World, origin: tuple, low: int, high: int) -> set:
    x, y = origin
    out = set()
    for dx in range(-high, high + 1):
        rest = high - abs(dx)
        for dy in range(-rest, rest + 1):
            d = abs(dx) + abs(dy)
            if low <= d <= high and world.inside(x + dx, y + dy):
                out.add((x + dx, y + dy))
    return out


def threat_tiles(world: World, state: GameState, unit: SimUnit, ranges: list) -> set:
    """Every tile ``unit`` could strike after moving: its destinations widened by ``ranges`` [(min, max)]."""
    out = set()
    for tile in destinations(world, state, unit):
        for low, high in ranges:
            out |= tiles_in_range(world, tile, low, high)
    return out
