"""RFEE01 tactical sight state, separate from distance-render fog.

``GameState.sight`` is changed by the event VM and is part of replay/rewind.
The window's Show all switch is only a view override and never mutates it.
"""

from __future__ import annotations

from .state import PLAYER, GameState
from .world import World

#: Used when a unit's class is unknown to the world.
DEFAULT_VISION = 3


def vision_of(world: World, unit) -> int:
    if getattr(unit, "vision", 0):
        return max(1, int(unit.vision))
    cls = world.classes.get(unit.jid)
    return max(1, int(getattr(cls, "vision", DEFAULT_VISION))) if cls is not None else DEFAULT_VISION


def visible_tiles(world: World, state: GameState, *, show_all: bool = False) -> set:
    """Every tile visible to the player under the current game sight state."""
    if show_all or not (state.sight or state.fog):
        return {(x, y) for x in range(world.width) for y in range(world.height)}
    seen = set()
    for unit in state.living(PLAYER):
        reach = max(int(state.sight), vision_of(world, unit))
        for dx in range(-reach, reach + 1):
            span = reach - abs(dx)
            for dy in range(-span, span + 1):
                x, y = unit.x + dx, unit.y + dy
                if 0 <= x < world.width and 0 <= y < world.height:
                    seen.add((x, y))
    for (sx, sy), duration in state.sight_sources.items():
        if duration <= 0:
            continue
        reach = max(1, int(state.sight)) + 2
        for x in range(max(0, sx - reach), min(world.width, sx + reach + 1)):
            for y in range(max(0, sy - reach), min(world.height, sy + reach + 1)):
                if abs(x - sx) + abs(y - sy) <= reach:
                    seen.add((x, y))
    return seen


def can_see(world: World, state: GameState, unit, visible=None) -> bool:
    """Whether the player sees ``unit`` (own side always; others only on visible tiles)."""
    if not (state.sight or state.fog) or unit.faction == PLAYER:
        return True
    return unit.tile in (visible if visible is not None else visible_tiles(world, state))
