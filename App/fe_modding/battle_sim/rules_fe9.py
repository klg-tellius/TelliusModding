"""Path of Radiance's combat rules: the forecast, strike counts and skill effects.

**Confirmed** (archive ``combat-mechanics`` / ``skill-*`` articles and the
tunables of :mod:`fe_modding.game_code.entries`):

- Hit uses two rolls averaged, Crit one roll; a critical hit does x3 damage.
- A unit attacks again when its attack speed is at least the opponent's + 4.
- A Brave weapon (property ``twice``) strikes twice per exchange.
- Effectiveness doubles the weapon's Might; the weapon's categories are
  tested against the defender's class categories (``boss`` / ``final`` by
  unit flag). Full Guard (``sfxseal``) removes it; ``skysfxseal`` and
  ``lycsfxseal`` remove the anti-flier and anti-laguz bonuses.
- Attack types 4-7 (``flame``, ``thunder``, ``wind``, ``rod``) and magic
  swords use Mag against Res.
- ``crit0`` forces the wielder's Crit to 0; a ``sealcrit`` wielder cannot be
  critted. Blessed armour takes no damage from weapons without ``weakA``.
- Wrath adds 50 Crit at half HP or less; the class trait ``SID_CRITRISE``
  adds the ``GameData`` class critical bonus (15). Insight +20 Hit; Deadeye
  doubles the final Hit; Gamble halves Hit and doubles Crit; a target under a
  status condition is hit 100%. Parity drops terrain bonuses.
- Skill activation chances (``entries.PROCS``) and the effects of Sol, Luna,
  Aether, Counter, Cancel, Pray, Wing Guard and Vantage.

**Not confirmed** - the community formulas in :data:`FORMULAS`, kept in one
place so they can be corrected: Hit = weapon Hit + Skl x 2 + Lck / 2,
Avoid = attack speed x 2 + Lck + terrain, attack speed = Spd - max(0,
weight - Con), Crit = weapon Crit + Skl / 2, crit avoid = Lck, and the
weapon triangle (+-10 Hit, +-1 Atk). Astra's damage (half, rounded up, like
the ``NetuzoSet`` "halve damage" effect bit), Deathblow (lethal, like the
"lethal damage" bit) and Aether's two-strike form are also unverified. The
procs whose effect is untraced (Rumbling, Corrosion, Impact, Snipe,
Sunlight) are rolled and logged but change nothing.

Skills are matched by their table position (the engine tests a bit by raw
position), by ``SID_`` label, or by the English name in the help key
(``Mess_Help_skill_Wrath``), whichever the data provides.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from .units import DEF, HP, LCK, MAG, RES, SKL, SPD, STR, Combatant

#: Constants of the confirmed rules (vanilla values; the game-code tunables can change them).
CRIT_MULTIPLIER = 3
DOUBLE_THRESHOLD = 4
WRATH_CRIT_BONUS = 50
CLASS_CRIT_BONUS = 15
EFFECTIVE_MIGHT_MULTIPLIER = 2
INSIGHT_HIT = 20
ASTRA_STRIKES = 5

#: The unconfirmed formula constants, shown as "unverified" by the simulator.
FORMULAS = {
    "hit_skill": 2, "hit_luck_div": 2, "avoid_speed": 2, "crit_skill_div": 2,
    "triangle_hit": 10, "triangle_atk": 1,
}

#: Skill keys by skill table position (``entries.PROCS`` ids and the archive's skill articles).
SKILL_BY_INDEX = {
    0x29: "vantage", 0x2C: "cancel", 0x2D: "wing_guard", 0x2E: "pray", 0x2F: "sol", 0x30: "luna",
    0x31: "astra", 0x32: "continue", 0x33: "deathblow", 0x34: "corrosion", 0x35: "snipe", 0x37: "counter",
    0x38: "rumbling", 0x39: "impact", 0x4C: "aether", 0x5A: "sunlight",
}
#: Skill keys by SID_ label, where the archive names it.
SKILL_BY_SID = {
    "SID_AMBUSH": "vantage", "SID_DEFENCE": "cancel", "SID_WINGSHIELD": "wing_guard", "SID_PRAY": "pray",
    "SID_SUNTRICK": "sol", "SID_MOONTRICK": "luna", "SID_STARTRICK": "astra", "SID_WEAPONDESTROY": "corrosion",
    "SID_COUNTER": "counter", "SID_RUMBLE": "rumbling", "SID_SUNMOON": "aether", "SID_CRITRISE": "critrise",
    "SID_TELEGNOSIS": "insight", "SID_FAIRNESS": "parity", "SID_GAMBLE": "gamble",
}
#: Skill keys by the English name in the help key (``Mess_Help_skill_<Name>``).
SKILL_BY_HELP_NAME = {
    "wrath": "wrath", "deadeye": "deadeye", "gamble": "gamble", "vantage": "vantage", "adept": "continue",
    "insight": "insight", "parity": "parity",
}

#: Display names of the skill keys.
SKILL_NAMES = {
    "vantage": "Vantage", "cancel": "Cancel", "wing_guard": "Wing Guard", "pray": "Miracle", "sol": "Sol",
    "luna": "Luna", "astra": "Astra", "continue": "Adept", "deathblow": "Deathblow", "corrosion": "Corrosion",
    "snipe": "Snipe", "counter": "Counter", "rumbling": "Colossus", "impact": "Impact", "aether": "Aether",
    "sunlight": "Sunlight", "critrise": "Class crit bonus", "insight": "Insight", "parity": "Parity",
    "gamble": "Gamble", "wrath": "Wrath", "deadeye": "Deadeye",
}
#: Procs that are rolled but whose effect is not modelled.
UNMODELLED_PROCS = ("rumbling", "corrosion", "impact", "snipe", "sunlight")

#: Weapon triangle: each type beats the next.
_TRIANGLE_BEATS = {"sword": "axe", "axe": "lance", "lance": "sword"}
_LAGUZ_CATEGORIES = frozenset({"alize", "beast", "dragon", "bird"})


@dataclass
class SideForecast:
    """One side's numbers against the other, as the battle forecast shows them."""

    can_attack: bool = False
    magic: bool = False
    effective: bool = False
    triangle: int = 0  # +1 advantage, -1 disadvantage
    attack_speed: int = 0
    atk: int = 0
    defense: int = 0  # the opponent's Def or Res, terrain included
    damage: int = 0
    hit: int = 0  # final, 0-100
    crit: int = 0  # final, 0-100
    doubles: bool = False
    strikes: int = 1  # per exchange (Brave: 2)
    raw_hit: int = 0
    avoid: int = 0  # the opponent's
    raw_crit: int = 0
    crit_avoid: int = 0  # the opponent's
    notes: list = field(default_factory=list)


@dataclass
class Forecast:
    attacker: SideForecast
    defender: SideForecast
    distance: int = 1

    def side(self, index: int) -> SideForecast:
        return self.defender if index else self.attacker


def _clamp(value: int) -> int:
    return max(0, min(100, value))


class Fe9Rules:
    """Path of Radiance's rules. ``skill_table`` (``Fe8Data.skills``) lets
    skills be matched by table position and help key as well as by label."""

    name = "Path of Radiance"

    def __init__(self, skill_table: Optional[list] = None, *, class_crit_bonus: int = CLASS_CRIT_BONUS):
        self.class_crit_bonus = class_crit_bonus
        self._keys: dict[str, str] = dict(SKILL_BY_SID)
        for skill in skill_table or ():
            if not skill.sid:
                continue
            key = SKILL_BY_INDEX.get(skill.index)
            if key is None and skill.help_key and skill.help_key.startswith("Mess_Help_skill_"):
                key = SKILL_BY_HELP_NAME.get(skill.help_key[len("Mess_Help_skill_"):].lower())
            if key is not None:
                self._keys[skill.sid] = key

    # -- skills -------------------------------------------------------------------------------
    def skill_key(self, sid: str) -> Optional[str]:
        return self._keys.get(sid)

    def skill_keys(self, unit: Combatant) -> set:
        return {k for k in (self._keys.get(s) for s in unit.skills) if k}

    def proc_chance(self, key: str, owner: Combatant) -> int:
        """Activation chance of a proc skill (``entries.PROCS``), for its owner."""
        skl = owner.stats[SKL] + self._bonus(owner)[SKL]
        if key in ("astra", "impact", "snipe", "counter"):
            return _clamp(skl // 2)
        if key == "deathblow":
            return 50
        if key == "pray":
            return _clamp(owner.stats[LCK] + self._bonus(owner)[LCK])
        return _clamp(skl)

    # -- forecast -----------------------------------------------------------------------------
    @staticmethod
    def _bonus(unit: Combatant) -> tuple:
        return tuple(unit.weapon.stat_bonus) if unit.weapon else (0,) * 10

    def stat(self, unit: Combatant, index: int) -> int:
        return unit.stats[index] + self._bonus(unit)[index]

    def attack_speed(self, unit: Combatant) -> int:
        weight = unit.weapon.weight if unit.weapon else 0
        con = unit.build + self._bonus(unit)[9]
        return self.stat(unit, SPD) - max(0, weight - con)

    def can_attack(self, unit: Combatant, distance: int) -> bool:
        w = unit.weapon
        return w is not None and not w.is_staff and w.in_range(distance, self.stat(unit, MAG))

    def effective(self, unit: Combatant, target: Combatant) -> bool:
        w = unit.weapon
        if w is None:
            return False
        guard = target.weapon.properties if target.weapon else frozenset()
        if "sfxseal" in guard:
            return False
        cats = set(target.categories)
        if "skysfxseal" in guard:
            cats.discard("fly")
        if "lycsfxseal" in guard:
            cats -= _LAGUZ_CATEGORIES
        if target.boss:
            cats.add("boss")
        if target.final_boss:
            cats.add("final")
        return bool(w.effective & cats)

    @staticmethod
    def triangle(unit: Combatant, target: Combatant) -> int:
        a = unit.weapon.weapon_type if unit.weapon else None
        b = target.weapon.weapon_type if target.weapon else None
        if a and _TRIANGLE_BEATS.get(a) == b:
            return 1
        if b and _TRIANGLE_BEATS.get(b) == a:
            return -1
        return 0

    def side(self, unit: Combatant, target: Combatant, distance: int = 1) -> SideForecast:
        f = SideForecast()
        keys, target_keys = self.skill_keys(unit), self.skill_keys(target)
        parity = "parity" in keys or "parity" in target_keys
        w = unit.weapon
        f.attack_speed = self.attack_speed(unit)
        f.can_attack = self.can_attack(unit, distance)
        if w is None:
            f.notes.append("unarmed")
            return f
        f.magic = w.magic
        f.effective = self.effective(unit, target)
        f.triangle = self.triangle(unit, target)
        might = w.might * (EFFECTIVE_MIGHT_MULTIPLIER if f.effective else 1)
        f.atk = self.stat(unit, MAG if f.magic else STR) + might + f.triangle * FORMULAS["triangle_atk"]
        if target.blessed_armor and "weakA" not in w.properties:
            f.atk = 0
            f.notes.append("blessed armour: Attack 0")
        terrain = (0, 0, 0) if parity else target.terrain
        f.defense = self.stat(target, RES) + terrain[2] if f.magic else self.stat(target, DEF) + terrain[1]
        f.damage = max(0, f.atk - f.defense)

        f.raw_hit = (w.hit + self.stat(unit, SKL) * FORMULAS["hit_skill"]
                     + self.stat(unit, LCK) // FORMULAS["hit_luck_div"] + f.triangle * FORMULAS["triangle_hit"])
        if "insight" in keys:
            f.raw_hit += INSIGHT_HIT
        f.avoid = self.attack_speed(target) * FORMULAS["avoid_speed"] + self.stat(target, LCK) + terrain[0]
        hit = _clamp(f.raw_hit - f.avoid)

        f.raw_crit = w.crit + self.stat(unit, SKL) // FORMULAS["crit_skill_div"]
        if "critrise" in keys:
            f.raw_crit += self.class_crit_bonus
        if "wrath" in keys and unit.hp * 2 <= unit.stats[HP]:
            f.raw_crit += WRATH_CRIT_BONUS
        f.crit_avoid = self.stat(target, LCK)
        crit = _clamp(f.raw_crit - f.crit_avoid)

        if "deadeye" in keys:
            hit = _clamp(hit * 2)
        if "gamble" in keys:
            hit, crit = hit // 2, _clamp(crit * 2)
        if target.status_condition:
            hit = 100
        if "crit0" in w.properties:
            crit = 0
            f.notes.append("cannot crit")
        if target.weapon and "sealcrit" in target.weapon.properties:
            crit = 0
            f.notes.append("target cannot be critted")
        f.hit, f.crit = hit, crit
        f.strikes = 2 if "twice" in w.properties else 1
        f.doubles = f.attack_speed >= self.attack_speed(target) + DOUBLE_THRESHOLD
        if f.effective:
            f.notes.append("effective")
        return f

    def forecast(self, attacker: Combatant, defender: Combatant, distance: int = 1) -> Forecast:
        return Forecast(self.side(attacker, defender, distance), self.side(defender, attacker, distance), distance)
