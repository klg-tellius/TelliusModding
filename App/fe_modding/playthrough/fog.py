"""Fog of war as a view of the player's side.

The chapter's fog is not run by the simulator: nothing in play depends on it (the enemy AI is
not limited by it), and the ``Fog`` natives stay presentation calls. When ``GameState.fog`` is
on, this module says which tiles the player can see so the window can hide the rest.

An approximation, not the game's rule: a tile is visible when it is within ``vision`` tiles
(Manhattan distance) of a player-side unit on the map, ``vision`` being the class's vision
field. Torches, roofs and line of sight are not modelled.
"""

from __future__ import annotations

from .state import PLAYER, GameState
from .world import World

#: Used when a unit's class is unknown to the world.
DEFAULT_VISION = 3


def vision_of(world: World, unit) -> int:
    cls = world.classes.get(unit.jid)
    return max(1, int(cls.vision)) if cls is not None else DEFAULT_VISION


def visible_tiles(world: World, state: GameState) -> set:
    """Every tile the player's units see. Everything, when fog is off."""
    if not state.fog:
        return {(x, y) for x in range(world.width) for y in range(world.height)}
    seen = set()
    for unit in state.living(PLAYER):
        reach = vision_of(world, unit)
        for dx in range(-reach, reach + 1):
            span = reach - abs(dx)
            for dy in range(-span, span + 1):
                x, y = unit.x + dx, unit.y + dy
                if 0 <= x < world.width and 0 <= y < world.height:
                    seen.add((x, y))
    return seen


def can_see(world: World, state: GameState, unit, visible=None) -> bool:
    """Whether the player sees ``unit`` (own side always; others only on visible tiles)."""
    if not state.fog or unit.faction == PLAYER:
        return True
    return unit.tile in (visible if visible is not None else visible_tiles(world, state))
