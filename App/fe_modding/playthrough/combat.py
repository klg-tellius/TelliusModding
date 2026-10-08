"""A map unit's battle numbers and fights, through :mod:`fe_modding.battle_sim`.

A :class:`~.state.SimUnit` becomes a :class:`battle_sim.Combatant` with its
current HP, the weapon it fights with and the terrain bonus of its tile
(the flier column, ``TerrainType.alt_bonus``, for units of the ``fly``
category). The fight itself is ``battle_sim.simulate``: the state's random
stream answers every roll, unless the user forced the outcomes of this fight.

After the fight the HP are written back and weapons lose uses: a physical
weapon one per strike that hit, a tome or a staff one per strike made (the
usual series rule; Path of Radiance's own accounting is not traced). The
EXP award is an approximation of the archive's ``combat-mechanics`` formula
with the Normal-mode constants guessed (level constant 21, kill bonus 20,
boss bonus 40).
"""

from __future__ import annotations

from typing import Optional

from .. import battle_sim
from ..battle_sim import Combatant, FixedOutcomes, RngOutcomes
from ..battle_sim.units import weapon_from_item
from .state import GameState, SimUnit
from .world import World

MAGIC_TYPES = frozenset({"flame", "thunder", "wind", "rod"})


def weapon_items(world: World, unit: SimUnit) -> list:
    """``[(inventory index, ItemEntry)]`` of the weapons ``unit`` can attack with, inventory order."""
    out = []
    for i, (iid, uses, _drop) in enumerate(unit.items):
        item = world.items.get(iid)
        if item is None or uses <= 0 or not world.can_wield(unit, item):
            continue
        if item.weapon_type == "rod" and not item.might:
            continue  # a staff
        if unit.status == "silence" and item.weapon_type in MAGIC_TYPES:
            continue
        out.append((i, item))
    return out


def staff_items(world: World, unit: SimUnit) -> list:
    out = []
    if unit.status == "silence":
        return out
    for i, (iid, uses, _drop) in enumerate(unit.items):
        item = world.items.get(iid)
        if item is not None and uses > 0 and item.weapon_type == "rod" and not item.might and world.can_wield(unit, item):
            out.append((i, item))
    return out


def item_range(unit: SimUnit, item) -> tuple:
    """(min, max): a max range of 255 is Mag / 2 clamped to 5..15 (``resolve_stat_or_default_from_magic``)."""
    high = min(15, max(5, unit.stats[2] // 2)) if item.max_range == 255 else item.max_range
    return (max(1, item.min_range), max(1, high))


def attack_ranges(world: World, unit: SimUnit) -> list:
    return sorted({item_range(unit, item) for _i, item in weapon_items(world, unit)})


def equipped(world: World, unit: SimUnit, distance: Optional[int] = None):
    """``(index, ItemEntry)`` of the weapon ``unit`` fights with: the first
    usable one (in range of ``distance`` when given), else ``(None, None)``."""
    for i, item in weapon_items(world, unit):
        low, high = item_range(unit, item)
        if distance is None or low <= distance <= high:
            return i, item
    return None, None


def combatant(world: World, unit: SimUnit, item=None) -> Combatant:
    c = Combatant(
        name=world.name(unit.pid), pid=unit.pid, jid=unit.jid, aid=_aid(world, unit), level=unit.level,
        stats=list(unit.stats), hp=unit.hp, build=unit.build, skills=list(unit.skills),
        categories=frozenset(unit.categories), weapon=weapon_from_item(item) if item is not None else None,
        boss=unit.boss,
    )
    t = world.terrain_at(unit.x, unit.y)
    if t is not None:
        c.terrain = tuple(t.alt_bonus) if "fly" in unit.categories else (t.avoid, t.defense, t.resistance)
    return c


def _aid(world: World, unit: SimUnit) -> Optional[str]:
    char = world.characters.get(unit.pid)
    cls = world.classes.get(unit.jid)
    if char is not None:
        promoted = cls is not None and unit.jid != char.jid  # as battle_sim.units.from_character
        aid = char.aid_promoted if promoted and char.aid_promoted else char.aid_unpromoted
        if aid:
            return aid
    return cls.aid if cls is not None else None


def forecast(world: World, attacker: SimUnit, defender: SimUnit, item, distance: int):
    _di, ditem = equipped(world, defender, distance)
    return world.rules.forecast(combatant(world, attacker, item), combatant(world, defender, ditem), distance)


def fight(world: World, state: GameState, attacker: SimUnit, defender: SimUnit, item_index: int,
          distance: int) -> battle_sim.BattleLog:
    """Run the fight, write its results back to the two units and emit a ``battle`` output."""
    item = world.items.get(attacker.items[item_index][0])
    di, ditem = equipped(world, defender, distance)
    a, d = combatant(world, attacker, item), combatant(world, defender, ditem)
    if state.forced is not None:
        outcomes = FixedOutcomes(state.forced)
        state.forced = None
        how = "forced outcomes"
    else:
        outcomes = RngOutcomes(state.rng)
        how = "random"
    log = battle_sim.simulate(a, d, rules=world.rules, outcomes=outcomes, distance=distance)
    attacker.hp, defender.hp = max(0, log.hp_end[0]), max(0, log.hp_end[1])
    for side, (unit, index, weapon) in enumerate(((attacker, item_index, item), (defender, di, ditem))):
        if index is None or weapon is None:
            continue
        magic = weapon.weapon_type in MAGIC_TYPES
        used = sum(1 for s in log.strikes if s.side == side and (s.hit or magic))
        _use(world, state, unit, index, used)
    exp = 0
    player = attacker if attacker.faction == 0 else defender
    if player.faction == 0 and player.hp > 0:  # a fallen unit gains nothing
        other = defender if player is attacker else attacker
        dealt = any(s.side == (0 if player is attacker else 1) and s.damage for s in log.strikes)
        exp = battle_exp(player, other, dealt, other.hp <= 0, world.exp_constants())
    state.emit("battle", f"{world.name(attacker.pid)} attacks {world.name(defender.pid)} ({how})\n" + log.text(),
               attacker=attacker.uid, defender=defender.uid, distance=distance, log=log, exp=exp)
    if exp:
        gain_exp(world, state, player, exp)
    return log


def _use(world: World, state: GameState, unit: SimUnit, index: int, used: int) -> None:
    if used <= 0 or index >= len(unit.items):
        return
    entry = unit.items[index]
    item = world.items.get(entry[0])
    if item is not None and item.uses >= 100:  # unbreakable (laguz strikes, legendary weapons)
        return
    entry[1] = max(0, entry[1] - used)
    if entry[1] == 0:
        state.emit("log", f"{world.name(unit.pid)}'s {world.item_name(entry[0])} broke")
        del unit.items[index]


#: GameData's retail Normal values, for a world without them.
DEFAULT_EXP_CONSTANTS = {"battle_exp_mode_bonus": 20, "battle_exp_level_constant": 20, "promotion_exp_bonus_base": 0,
                         "boss_exp_bonus": 30, "thief_exp_bonus": 20}


def _has(unit: SimUnit, sid: str) -> bool:
    return sid in unit.skills


def _half(value: int) -> int:
    return int(value / 2)  # C division: towards zero


def battle_exp(winner: SimUnit, other: SimUnit, dealt: bool, killed: bool,
               constants: Optional[dict] = None) -> int:
    """``calculate_battle_exp``: the EXP ``winner`` gets for a fight with ``other``. A promoted unit
    (``SID_HIGHER``) counts 20 levels higher (plus GameData's promotion base for the kill term); the
    kill term adds the boss (``SID_BOSS``) and thief (``SID_STEAL``) bonuses. ``constants`` are the
    difficulty's GameData values (:data:`DEFAULT_EXP_CONSTANTS` when None)."""
    c = constants or DEFAULT_EXP_CONSTANTS
    if _has(other, "SID_FINAL"):
        return 0
    if not dealt:
        return 1

    def level(unit: SimUnit, table: bool) -> int:
        if not _has(unit, "SID_HIGHER"):
            return unit.level
        return unit.level + 20 + (c["promotion_exp_bonus_base"] if table else 0)

    exp = max(1, _half(c["battle_exp_level_constant"] + level(other, False) - level(winner, False) + 1))
    if killed:
        exp += max(0, c["battle_exp_mode_bonus"] + level(other, True) - level(winner, True)
                   + (c["boss_exp_bonus"] if _has(other, "SID_BOSS") else 0)
                   + (c["thief_exp_bonus"] if _has(other, "SID_STEAL") else 0))
    if _has(winner, "SID_ELITE"):
        exp *= 2
    if _has(winner, "SID_FRAC90"):
        exp = max(1, exp * 7 // 10)
    return min(100, exp)


def gain_exp(world: World, state: GameState, unit: SimUnit, exp: int) -> None:
    unit.exp += exp
    state.emit("log", f"{world.name(unit.pid)} gains {exp} EXP ({unit.exp}/100)")
    while unit.exp >= 100 and unit.level < 20:
        unit.exp -= 100
        level_up(world, state, unit)


def level_up(world: World, state: GameState, unit: SimUnit) -> None:
    """Random growth (the archive's ``level-up-growth``): a point per full
    100% of the rate, then one roll for the rest, capped by the class."""
    char, cls = world.characters.get(unit.pid), world.classes.get(unit.jid)
    growth = list(char.growth) if char is not None else (list(cls.growths) if cls is not None else [0] * 8)
    caps = list(cls.stat_caps) if cls is not None else [99] * 8
    unit.level += 1
    gains = []
    for i, rate in enumerate(growth[:8]):
        gain = rate // 100 + (1 if state.rng.roll_percent(rate % 100)[0] else 0)
        gain = max(0, min(gain, caps[i] - unit.stats[i])) if caps[i] else gain
        unit.stats[i] += gain
        if i == 0:
            unit.hp += gain
        gains.append(gain)
    names = ("HP", "Str", "Mag", "Skl", "Spd", "Lck", "Def", "Res")
    text = ", ".join(f"{n} +{g}" for n, g in zip(names, gains) if g) or "no gains"
    state.emit("log", f"{world.name(unit.pid)} reached level {unit.level}: {text}")
