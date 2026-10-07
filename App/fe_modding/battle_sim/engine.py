"""Runs a fight between two :class:`~.units.Combatant` s, strike by strike.

The order follows the archive's ``combat-mechanics`` article: the attacker's
exchange, then the defender's (Vantage swaps the two), then a follow-up
exchange for each side whose attack speed is 4 or more above the other's.
An exchange holds one strike, two with a Brave weapon; Astra, Aether and
Adept change that count when they trigger at its start. Each strike rolls
Hit, then Crit if it hit, then the strike's procs. The fight stops when a
unit dies.

Every random question goes through an outcome source as a
:class:`Decision`, numbered by the strike it belongs to (an exchange-level
proc belongs to the exchange's first strike, Counter to the strike that
triggers it):

- :class:`RngOutcomes` answers with :class:`~.rng.Fe9Rng`;
- :class:`FixedOutcomes` answers from the user's per-strike choices,
  defaulting to "hits, no crit, no proc".

So both modes share the same sequencing; a fixed fight is replayed by
editing the choices and simulating again.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional, Protocol

from .rng import Fe9Rng
from .rules_fe9 import ASTRA_STRIKES, CRIT_MULTIPLIER, SKILL_NAMES, UNMODELLED_PROCS, Fe9Rules, Forecast
from .units import HP, Combatant

ATTACKER, DEFENDER = 0, 1


@dataclass
class Decision:
    strike: int  # 1-based strike number
    side: int  # whose roll it is (the skill owner, for procs)
    kind: str  # "hit", "crit", or "proc:<skill key>"
    chance: int
    result: bool
    roll: Optional[int] = None  # the random number, in RNG mode


class OutcomeSource(Protocol):
    def decide(self, strike: int, side: int, kind: str, chance: int) -> tuple[bool, Optional[int]]: ...


class RngOutcomes:
    def __init__(self, rng: Fe9Rng | int = 0):
        self.rng = rng if isinstance(rng, Fe9Rng) else Fe9Rng(rng)

    def decide(self, strike, side, kind, chance):
        if kind == "hit":
            return self.rng.roll_true_hit(chance)
        return self.rng.roll_percent(chance)


class FixedOutcomes:
    """The user's choices, keyed by ``(strike, kind)``; anything unchosen
    takes the default: a strike with any Hit chance hits, nothing crits and
    no skill triggers."""

    def __init__(self, choices: Optional[dict] = None):
        self.choices = dict(choices or {})

    def decide(self, strike, side, kind, chance):
        if (strike, kind) in self.choices:
            return bool(self.choices[(strike, kind)]), None
        return (kind == "hit" and chance > 0), None


@dataclass
class Strike:
    number: int
    side: int  # who strikes
    hit: bool = False
    crit: bool = False
    procs: list = field(default_factory=list)  # skill keys that triggered on this strike
    damage: int = 0
    heal: int = 0
    hp_after: tuple = (0, 0)
    kill: bool = False
    label: str = ""  # "", "follow-up", "brave", "Counter", "Astra"...
    hit_chance: int = 0
    crit_chance: int = 0


@dataclass
class BattleLog:
    attacker: Combatant
    defender: Combatant
    forecast: Forecast
    strikes: list = field(default_factory=list)
    decisions: list = field(default_factory=list)
    hp_start: tuple = (0, 0)
    hp_end: tuple = (0, 0)
    notes: list = field(default_factory=list)

    @property
    def dead(self) -> Optional[int]:
        """The side that died, if any."""
        for side in (ATTACKER, DEFENDER):
            if self.hp_end[side] <= 0:
                return side
        return None

    def text(self) -> str:
        names = (self.attacker.name, self.defender.name)
        lines = []
        for s in self.strikes:
            what = "misses" if not s.hit else ("crits" if s.crit else "hits")
            extra = f" [{', '.join(SKILL_NAMES.get(p, p) for p in s.procs)}]" if s.procs else ""
            tag = f" ({s.label})" if s.label else ""
            dmg = f" for {s.damage}" if s.hit else ""
            heal = f", heals {s.heal}" if s.heal else ""
            kill = " - defeated" if s.kill else ""
            lines.append(f"{s.number}. {names[s.side]}{tag} {what}{dmg}{extra}{heal}"
                         f" -> HP {s.hp_after[0]} / {s.hp_after[1]}{kill}")
        return "\n".join(lines + self.notes)


class _Fight:
    def __init__(self, rules: Fe9Rules, units: list, distance: int, source: OutcomeSource, log: BattleLog):
        self.rules, self.units, self.distance, self.source, self.log = rules, units, distance, source, log
        self.keys = [rules.skill_keys(u) for u in units]
        self.number = 0  # strikes done

    def decide(self, side: int, kind: str, chance: int) -> bool:
        result, roll = self.source.decide(self.number + 1, side, kind, chance)
        self.log.decisions.append(Decision(self.number + 1, side, kind, chance, result, roll))
        return result

    def proc(self, side: int, key: str) -> bool:
        if key not in self.keys[side]:
            return False
        return self.decide(side, f"proc:{key}", self.rules.proc_chance(key, self.units[side]))

    def over(self) -> bool:
        return any(u.hp <= 0 for u in self.units)

    def exchange(self, side: int, label: str = "") -> None:
        if self.over() or not self.rules.can_attack(self.units[side], self.distance):
            return
        other = 1 - side
        if side == DEFENDER and self.proc(ATTACKER, "cancel"):
            self.log.notes.append(f"Cancel stops {self.units[side].name}'s counter")
            return
        brave = self.rules.side(self.units[side], self.units[other], self.distance).strikes
        plan = [("brave" if i else label, set()) for i in range(brave)]
        if self.proc(side, "astra"):
            plan = [("Astra", {"astra"}) for _ in range(ASTRA_STRIKES)]
        elif self.proc(side, "aether"):
            plan = [("Aether", {"sol"}), ("Aether", {"luna"})]
        if self.proc(side, "continue"):
            plan.append(("Adept", set()))
        for strike_label, forced in plan:
            if self.over():
                return
            self.strike(side, strike_label, forced)

    def strike(self, side: int, label: str, forced: set, *, from_counter: bool = False) -> None:
        other = 1 - side
        unit, target = self.units[side], self.units[other]
        f = self.rules.side(unit, target, self.distance)
        s = Strike(self.number + 1, side, label=label, hit_chance=f.hit, crit_chance=f.crit)
        s.procs.extend(sorted(forced - {"astra"}))
        if "astra" in forced:
            s.procs.append("astra")
        s.hit = self.decide(side, "hit", f.hit)
        if s.hit:
            s.crit = self.decide(side, "crit", f.crit)
            luna = "luna" in forced or self.proc(side, "luna")
            if luna and "luna" not in s.procs:
                s.procs.append("luna")
            defense = f.defense // 2 if luna else f.defense
            damage = max(0, f.atk - defense)
            if "astra" in forced:
                damage = (damage + 1) // 2
            if s.crit:
                damage *= CRIT_MULTIPLIER
            if s.crit and self.proc(side, "deathblow"):
                s.procs.append("deathblow")
                damage = max(damage, target.hp)
            for key in UNMODELLED_PROCS:
                if self.proc(side, key):
                    s.procs.append(key)
            if damage and self.proc(other, "wing_guard"):
                s.procs.append("wing_guard")
                damage = 0
            if damage >= target.hp > 1 and self.proc(other, "pray"):
                s.procs.append("pray")
                damage = target.hp - 1
            damage = min(damage, target.hp)
            s.damage = damage
            target.hp -= damage
            sol = "sol" in forced or self.proc(side, "sol")
            if sol and "sol" not in s.procs:
                s.procs.append("sol")
            if sol or (unit.weapon and "resire" in unit.weapon.properties):
                s.heal = min(damage, unit.stats[HP] - unit.hp)
                unit.hp += s.heal
            s.kill = target.hp <= 0
        counter = (s.hit and s.damage and not s.kill and not from_counter and not unit.blessed_armor
                   and self.rules.can_attack(target, self.distance) and self.proc(other, "counter"))
        self.number += 1
        s.hp_after = (self.units[0].hp, self.units[1].hp)
        self.log.strikes.append(s)
        if counter:
            self.strike(other, "Counter", set(), from_counter=True)


def simulate(attacker: Combatant, defender: Combatant, *, rules: Optional[Fe9Rules] = None,
             outcomes: Optional[OutcomeSource] = None, distance: int = 1) -> BattleLog:
    """Fight ``attacker`` against ``defender`` (copies; the inputs are not changed)."""
    rules = rules or Fe9Rules()
    outcomes = outcomes or FixedOutcomes()
    a, d = attacker.copy(), defender.copy()
    log = BattleLog(a, d, rules.forecast(a, d, distance), hp_start=(a.hp, d.hp))
    fight = _Fight(rules, [a, d], distance, outcomes, log)
    order = [DEFENDER, ATTACKER] if "vantage" in fight.keys[DEFENDER] else [ATTACKER, DEFENDER]
    if order[0] == DEFENDER:
        log.notes.append(f"Vantage: {d.name} strikes first")
    for side in order:
        fight.exchange(side)
    for side in (ATTACKER, DEFENDER):
        if not fight.over() and rules.side(fight.units[side], fight.units[1 - side], distance).doubles:
            fight.exchange(side, "follow-up")
    log.hp_end = (a.hp, d.hp)
    return log
