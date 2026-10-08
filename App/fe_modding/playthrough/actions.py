"""The commands a unit can be given, and what they do.

A command is a small frozen record. The player's commands come from the
window; the AI builds the same records, so a fight, a shove or a visit runs
the same code whoever ordered it. :func:`apply` moves the unit and queues
the rest as tasks at the front of the state's queue, in the game's order:

- a ``battle`` trigger check (type 9: boss quotes), the fight, then the
  ``death`` checks (types 11 and 10) for a unit that died;
- for Visit, Talk and the other tile actions, the matching trigger check
  (type 5 with the action id, type 8 for Talk);
- then :class:`AfterAction`: the zone check (type 4), the after-action check
  (type 7), the goal checks (types 1 and 2), and Canto.

Rules taken from the archive's ``map-actions`` and ``skill-canto`` articles:
Shove pushes an adjacent unit one tile straight away (not fliers; the
destination must be free and enterable); Canto (``SID_TWICE``, or an item
with the ``movtw`` property) lets the unit move again with what is left of
its movement after acting. The Build (Con) test of Shove - the pusher's Build
at least the target's minus 2 - is the series rule, not traced in this game.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from . import combat, movement
from .state import PLAYER, GameState, SimUnit, Task, TriggerCheck, hostile
from .world import IMPASSABLE, World

LOCATION_ACTIONS = {9: "visit", 11: "door", 12: "chest", 13: "seize", 14: "escape", 37: "destroy", 41: "arrive",
                    44: "event"}
ACTION_IDS = {name: ident for ident, name in LOCATION_ACTIONS.items()}
#: Visit and destroy: a village they were done at is spent (``GameState.visited``)
VILLAGE_ACTIONS = (9, 37)
NOT_HEALING = frozenset({"IID_WARP", "IID_RESCUE", "IID_MSHIELD", "IID_TORCH", "IID_HAMMERNE", "IID_UNLOCK"})


@dataclass(frozen=True)
class Act:
    """Move ``uid`` to ``dest`` and do ``action`` there: wait, attack, staff,
    shove, talk, or a tile action (visit, door, chest, seize, escape, arrive...)."""

    uid: int
    dest: tuple
    action: str = "wait"
    target: Optional[int] = None  # the other unit (attack, staff, shove, talk)
    item: Optional[int] = None  # inventory index of the weapon, staff or item
    to: Optional[tuple] = None  # Warp: where the target is sent


@dataclass(frozen=True)
class CantoMove:
    """Use what is left of the unit's movement after acting (``dest`` = its tile to stay)."""

    uid: int
    dest: tuple


@dataclass(frozen=True)
class EndPhase:
    """End the player phase now; units that haven't acted wait."""


@dataclass
class Combat(Task):
    attacker: int
    defender: int
    item: int
    distance: int

    @property
    def title(self) -> str:
        return "Battle"


@dataclass
class AfterAction(Task):
    uid: int
    canto: int = 0  # movement left for Canto, 0 = none
    entered: list = field(default_factory=list)  # tiles walked through (zone checks)
    target: Optional[int] = None  # the other unit of the action (its heal flag is refreshed too)

    @property
    def title(self) -> str:
        return "After action"


@dataclass
class Choice:
    """One entry of a unit's action menu."""

    action: str
    target: Optional[int] = None
    item: Optional[int] = None
    label: str = ""


# -- availability ---------------------------------------------------------------------------------


def has_canto(world: World, unit: SimUnit) -> bool:
    if "SID_TWICE" in unit.skills:
        return True
    return any("movtw" in (world.items[iid].properties if iid in world.items else ()) for iid, _u, _d in unit.items)


def shove_destination(world: World, state: GameState, pusher_tile: tuple, target: SimUnit) -> Optional[tuple]:
    dx, dy = target.x - pusher_tile[0], target.y - pusher_tile[1]
    if abs(dx) + abs(dy) != 1:
        return None
    to = (target.x + dx, target.y + dy)
    if world.move_cost(*to, target.movement_type) >= IMPASSABLE or not world.linked(target.x, target.y, *to):
        return None
    other = state.unit_at(*to)
    if other is not None:
        return None
    return to


def can_shove(world: World, state: GameState, unit: SimUnit, tile: tuple, target: SimUnit) -> bool:
    if target.uid == unit.uid or "fly" in target.categories:
        return False
    if unit.build < target.build - 2:
        return False
    return shove_destination(world, state, tile, target) is not None


def choices(world: World, state: GameState, unit: SimUnit, dest: tuple) -> list:
    """What ``unit`` may do once it stands on ``dest``."""
    from . import triggers

    out = []
    others = [u for u in state.living() if u.uid != unit.uid]
    for index, item in combat.weapon_items(world, unit):
        low, high = combat.item_range(unit, item)
        for other in others:
            d = movement.distance(dest, other.tile)
            if hostile(unit.faction, other.faction) and low <= d <= high:
                out.append(Choice("attack", other.uid, index,
                                  f"Attack {world.name(other.pid)} with {world.item_name(item.iid)}"))
    from .ai_actions import STATUS_STAVES

    for index, item in combat.staff_items(world, unit):
        low, high = combat.item_range(unit, item)
        for other in others:
            d = movement.distance(dest, other.tile)
            if not low <= d <= high:
                continue
            foe = hostile(unit.faction, other.faction)
            if item.iid in STATUS_STAVES:
                ok = foe
            elif item.iid == "IID_REST":
                ok = not foe and bool(other.status)
            elif item.iid in NOT_HEALING:
                ok = False  # Warp, Rescue, Ward, Torch, Hammerne, Unlock: not in the simulator's menu
            else:
                ok = not foe and other.hp < other.stats[0]
            if ok:
                out.append(Choice("staff", other.uid, index,
                                  f"{world.item_name(item.iid)} on {world.name(other.pid)}"))
    for other in others:
        if movement.distance(dest, other.tile) != 1:
            continue
        if triggers.talk_events(world, state, unit.pid, other.pid):
            out.append(Choice("talk", other.uid, label=f"Talk to {world.name(other.pid)}"))
        if can_shove(world, state, unit, dest, other):
            out.append(Choice("shove", other.uid, label=f"Shove {world.name(other.pid)}"))
    for action_id, name in LOCATION_ACTIONS.items():
        if action_id in VILLAGE_ACTIONS and dest in state.visited:
            continue
        if triggers.location_events(world, state, dest, action_id):
            out.append(Choice(name, label=name.capitalize()))
    out.append(Choice("wait", label="Wait"))
    return out


# -- applying -------------------------------------------------------------------------------------


class CommandError(ValueError):
    pass


def apply(world: World, state: GameState, command, *, by_ai: bool = False) -> None:
    if isinstance(command, EndPhase):
        _end_player_phase(world, state)
        return
    if isinstance(command, CantoMove):
        _canto(world, state, command)
        return
    if not isinstance(command, Act):
        raise CommandError(f"Unknown command {command!r}")
    unit = state.units.get(command.uid)
    if unit is None or not unit.on_map:
        raise CommandError("That unit is not on the map.")
    if unit.done:
        raise CommandError(f"{world.name(unit.pid)} has already acted.")
    reach = movement.destinations(world, state, unit)
    dest = tuple(command.dest)
    if dest not in reach:
        raise CommandError(f"{world.name(unit.pid)} can't reach {dest}.")
    walked = movement.path(reach, dest)
    spent = reach[dest][0]
    action = command.action
    target = state.units.get(command.target) if command.target is not None else None
    if action in ("attack", "shove", "talk", "steal", "take_item") and (target is None or not target.on_map):
        raise CommandError(f"{action}: no target.")
    start, emitted = unit.tile, len(state.out)
    if dest != unit.tile:
        state.emit("action", f"{world.name(unit.pid)} moves to {dest}", uid=unit.uid, path=walked)
    unit.x, unit.y = dest
    try:
        tasks = _act(world, state, unit, dest, action, target, command.item, command.to)
    except CommandError:
        # nothing happened: an AI unit that can't act waits where it stood
        unit.x, unit.y = start
        del state.out[emitted:]
        raise
    acted = action != "wait"
    left = unit.move - spent
    canto = left if acted and not by_ai and left > 0 and has_canto(world, unit) else 0
    tasks.append(AfterAction(unit.uid, canto, walked, target.uid if target is not None else None))
    unit.done = True
    state.push_front(*tasks)


def _act(world: World, state: GameState, unit: SimUnit, dest: tuple, action: str, target, item,
         to: Optional[tuple] = None) -> list:
    """Do ``action`` with ``unit`` standing on ``dest``; returns the tasks that
    follow it. Raises :class:`CommandError` before changing anything."""
    tasks: list[Task] = []
    if action == "attack":
        if item is None:
            item = combat.equipped(world, unit, movement.distance(dest, target.tile))[0]
        if item is None:
            raise CommandError("No weapon can reach that unit.")
        tasks.append(TriggerCheck(9, {"pid1": unit.pid, "pid2": target.pid, "me": unit.uid, "target": target.uid}))
        tasks.append(Combat(unit.uid, target.uid, item, movement.distance(dest, target.tile)))
    elif action == "staff":
        use_staff(world, state, unit, target, item, to)
    elif action == "steal":
        steal(world, state, unit, target, item)
    elif action == "item":
        use_item(world, state, unit, item)
    elif action == "take_item":
        if item is None or item >= len(target.items):
            raise CommandError("Nothing to take.")
        entry = target.items.pop(item)
        unit.items.append(entry)
        state.emit("action", f"{world.name(unit.pid)} takes {world.item_name(entry[0])} from "
                             f"{world.name(target.pid)}", uid=unit.uid)
        use_item(world, state, unit, len(unit.items) - 1)
    elif action == "shove":
        to = shove_destination(world, state, dest, target)
        if to is None or not can_shove(world, state, unit, dest, target):
            raise CommandError(f"{world.name(unit.pid)} can't shove {world.name(target.pid)}.")
        start = target.tile
        target.x, target.y = to
        state.emit("action", f"{world.name(unit.pid)} shoves {world.name(target.pid)} to {to}", uid=target.uid,
                   path=[start, to])
    elif action == "talk":
        state.emit("action", f"{world.name(unit.pid)} talks to {world.name(target.pid)}")
        tasks.append(TriggerCheck(8, {"pid1": unit.pid, "pid2": target.pid, "me": unit.uid, "target": target.uid}))
    elif action in ACTION_IDS:
        action_id = ACTION_IDS[action]
        state.emit("action", f"{world.name(unit.pid)}: {action} at {dest}")
        if action_id in VILLAGE_ACTIONS:
            state.visited.add(dest)
        tasks.append(TriggerCheck(5, {"x": dest[0], "y": dest[1], "action": action_id, "me": unit.uid}))
    elif action == "wait":
        state.emit("action", f"{world.name(unit.pid)} waits", uid=unit.uid)
    else:
        raise CommandError(f"Unknown action {action!r}")
    return tasks


def staff_heal(world: World, unit: SimUnit, item) -> int:
    """HP a healing staff restores: Mag + 10, Mag + 20 for Mend-type staves
    (``IID_RELIVE``), everything for Recover-type staves (``IID_RECOVER``,
    ``IID_RESERVE``) - the series values; the staves' own effect data isn't decoded."""
    iid = item.iid or ""
    if iid in ("IID_RECOVER", "IID_RESERVE"):
        return 999
    return unit.stats[2] + (20 if iid == "IID_RELIVE" else 10)


def use_staff(world: World, state: GameState, unit: SimUnit, target: Optional[SimUnit], index: Optional[int],
              to: Optional[tuple] = None) -> None:
    """Healing staves heal (Fortify: every unit of the caster's side in its range); Restore clears a
    status; Silence, Sleep and Berserk hit with ``ai_actions.magic_hit`` and last
    ``ai_actions.STATUS_TURNS`` phases; Rescue brings the target next to the caster; Warp sends it to
    ``to``; Ward's Res bonus is not simulated."""
    from . import ai_actions

    staves = dict(combat.staff_items(world, unit))
    if index not in staves:
        if not staves:
            raise CommandError(f"{world.name(unit.pid)} has no staff.")
        index = next(iter(staves))
    item = staves[index]
    iid = item.iid or ""
    name = world.item_name(iid)
    if iid == "IID_RESERVE" or target is None:
        high = ai_actions.max_range(unit, item)
        healed = [u for u in state.living() if not hostile(unit.faction, u.faction)
                  and 1 <= movement.distance(u.tile, unit.tile) <= high and u.hp < u.stats[0]]
        for u in healed:
            amount = min(staff_heal(world, unit, item), u.stats[0] - u.hp)
            u.hp += amount
            state.emit("action", f"{name}: {world.name(u.pid)} recovers {amount} HP", uid=u.uid)
        if not healed:
            state.emit("action", f"{world.name(unit.pid)} uses {name}: nobody to heal", uid=unit.uid)
    else:
        if target is None or not target.on_map:
            raise CommandError("staff: no target.")
        low, high = max(1, item.min_range), ai_actions.max_range(unit, item)
        d = movement.distance(unit.tile, target.tile)
        if not low <= d <= high:
            raise CommandError("The staff can't reach that unit.")
        if iid in ai_actions.STATUS_STAVES:
            hit = ai_actions.magic_hit(unit, target, d)
            ok, roll = state.rng.roll_percent(hit)
            if ok:
                target.status, target.status_turns = ai_actions.STATUS_STAVES[iid], ai_actions.STATUS_TURNS
            state.emit("action", f"{world.name(unit.pid)} uses {name} on {world.name(target.pid)}: hit {hit}, "
                                 f"roll {roll}: " + (target.status if ok else "missed"), uid=target.uid)
        elif iid == "IID_REST":
            state.emit("action", f"{world.name(unit.pid)} restores {world.name(target.pid)}"
                                 + (f" (no longer {target.status})" if target.status else ""), uid=target.uid)
            target.status, target.status_turns = "", 0
        elif iid in ("IID_WARP", "IID_RESCUE"):
            dest = to
            if iid == "IID_RESCUE":
                dest = next((n for n in sorted(movement.tiles_in_range(world, unit.tile, 1, 1))
                             if state.unit_at(*n) is None
                             and world.move_cost(*n, target.movement_type) < IMPASSABLE), None)
            if dest is None or state.unit_at(*dest) is not None:
                raise CommandError(f"{name}: no free tile to send {world.name(target.pid)} to.")
            start = target.tile
            target.x, target.y = dest
            state.emit("action", f"{world.name(unit.pid)} uses {name}: {world.name(target.pid)} to {dest}",
                       uid=target.uid, path=[start, dest])
        elif iid == "IID_MSHIELD":
            state.emit("action", f"{world.name(unit.pid)} uses {name} on {world.name(target.pid)} "
                                 "(the Res bonus is not simulated)", uid=target.uid)
        else:
            heal_with_staff(world, state, unit, target, index)
            return
    combat._use(world, state, unit, index, 1)
    if unit.faction == PLAYER:
        combat.gain_exp(world, state, unit, 11)


def steal(world: World, state: GameState, unit: SimUnit, target: SimUnit, index: Optional[int]) -> None:
    if movement.distance(unit.tile, target.tile) != 1 or index is None or index >= len(target.items):
        raise CommandError("Nothing to steal there.")
    entry = target.items.pop(index)
    unit.items.append(list(entry))
    state.emit("action", f"{world.name(unit.pid)} steals {world.item_name(entry[0])} from "
                         f"{world.name(target.pid)}", uid=target.uid)


def use_item(world: World, state: GameState, unit: SimUnit, index: Optional[int]) -> None:
    """Vulnerary +10 HP, Elixir full HP; other items are logged (their effects aren't simulated)."""
    if index is None or index >= len(unit.items):
        raise CommandError("No such item.")
    iid = unit.items[index][0]
    if iid in ("IID_VULNERARY", "IID_ELIXIR"):
        amount = min(10 if iid == "IID_VULNERARY" else unit.stats[0], unit.stats[0] - unit.hp)
        unit.hp += amount
        state.emit("action", f"{world.name(unit.pid)} uses {world.item_name(iid)}: +{amount} HP", uid=unit.uid)
    else:
        state.emit("action", f"{world.name(unit.pid)} uses {world.item_name(iid)} (effect not simulated)",
                   uid=unit.uid)
    combat._use(world, state, unit, index, 1)


def heal_with_staff(world: World, state: GameState, unit: SimUnit, target: SimUnit, index: Optional[int]) -> None:
    staves = dict(combat.staff_items(world, unit))
    if index not in staves:
        if not staves:
            raise CommandError(f"{world.name(unit.pid)} has no staff.")
        index = next(iter(staves))
    item = staves[index]
    low, high = combat.item_range(unit, item)
    if not low <= movement.distance(unit.tile, target.tile) <= high:
        raise CommandError("The staff can't reach that unit.")
    amount = min(staff_heal(world, unit, item), target.stats[0] - target.hp)
    target.hp += amount
    state.emit("action", f"{world.name(unit.pid)} heals {world.name(target.pid)} for {amount} "
                         f"({world.item_name(item.iid)})", uid=target.uid)
    combat._use(world, state, unit, index, 1)
    if unit.faction == PLAYER:
        combat.gain_exp(world, state, unit, 11)


def _canto(world: World, state: GameState, command: CantoMove) -> None:
    if state.canto is None or state.canto[0] != command.uid:
        raise CommandError("No Canto move is pending for that unit.")
    unit = state.units[command.uid]
    reach = movement.destinations(world, state, unit, budget=state.canto[1])
    dest = tuple(command.dest)
    if dest not in reach:
        raise CommandError(f"{world.name(unit.pid)} can't reach {dest} with Canto.")
    state.canto = None
    if dest != unit.tile:
        walked = movement.path(reach, dest)
        state.emit("action", f"{world.name(unit.pid)} moves on (Canto) to {dest}", uid=unit.uid, path=walked)
        unit.x, unit.y = dest
        state.push_front(AfterAction(unit.uid, 0, walked))


def _end_player_phase(world: World, state: GameState) -> None:
    from .state import PhaseEnd

    state.canto = None
    for u in state.living(PLAYER):
        u.done = True
    state.emit("phase", "Player phase ended")
    state.push_front(PhaseEnd(state.phase))
