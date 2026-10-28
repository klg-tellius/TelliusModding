"""Radiant Dawn (RFEE01) battle rules traced from the retail combat pipeline.

This is intentionally independent from :class:`Fe9Rules`: no Path of
Radiance formula or mastery implementation is inherited.  Optional combat
modifiers are passed in already resolved on ``Combatant`` so the tactical
runtime can source them from FE10Data, supports, terrain and current map state.
"""

from __future__ import annotations

from typing import Optional

from .rules_fe9 import Forecast, SideForecast
from .units import DEF, HP, LCK, MAG, RES, SKL, SPD, STR, Combatant

DOUBLE_THRESHOLD = 4
CRIT_MULTIPLIER = 3
TRIANGLE = {("sword", "axe"): (1, 10), ("axe", "lance"): (1, 10), ("lance", "sword"): (1, 10)}

SKILLS = {
    "SID_AMBUSH": "vantage", "SID_VANTAGE": "vantage", "SID_CONTINUE": "adept", "SID_ADEPT": "adept",
    "SID_ASTRA": "astra", "SID_AETHER": "aether", "SID_CANCEL": "cancel", "SID_PAVIS": "pavise",
    "SID_MIRACLE": "miracle", "SID_MERCY": "mercy", "SID_MANTLE": "mantle", "SID_PARITY": "parity",
    "SID_FAIRNESS": "parity", "SID_GAMBLE": "gamble", "SID_WARMUP": "warmup", "SID_WRATH": "wrath",
    "SID_INSIGHT": "insight", "SID_TELEGNOSIS": "insight", "SID_VIGILANCE": "vigilance",
    "SID_LUNA": "luna", "SID_LUNA2": "luna2", "SID_SOL": "sol", "SID_FLARE": "flare",
    "SID_AURORAL": "auroral", "SID_CRUSH": "crush", "SID_COLOSSUS": "colossus",
    "SID_DEADEYE": "deadeye", "SID_STUN": "stun", "SID_LETHALITY": "lethality", "SID_BANE": "bane",
    "SID_ROAR": "roar", "SID_SMASH": "smash", "SID_GRANDEUR": "grandeur", "SID_SOARING": "soaring",
    "SID_DISPLEASURE": "displeasure", "SID_CORROSION": "corrosion", "SID_RELEASE": "release",
    "SID_NIHIL": "nihil", "SID_LUCKY": "lucky", "SID_DAUNT": "daunt",
}


def _clamp(value: int) -> int:
    return max(0, min(100, int(value)))


class Fe10Rules:
    name = "Radiant Dawn"

    def __init__(self, skill_table: Optional[list] = None, difficulty: Optional[dict] = None):
        self.difficulty = dict(difficulty or {})
        self._keys = dict(SKILLS)
        for skill in skill_table or ():
            sid = getattr(skill, "sid", None)
            if sid and sid not in self._keys:
                token = sid.removeprefix("SID_").lower()
                if token in set(SKILLS.values()):
                    self._keys[sid] = token

    def skill_keys(self, unit: Combatant) -> set[str]:
        return {self._keys[s] for s in unit.skills if s in self._keys}

    def skill_key(self, sid: str):
        return self._keys.get(sid)

    def stat(self, unit: Combatant, index: int) -> int:
        bonus = unit.weapon.stat_bonus[index] if unit.weapon else 0
        value = unit.stats[index] + bonus
        if unit.transformed and any(c in unit.categories for c in ("beast", "bird", "dragon", "laguz", "alize")):
            value = value * (2 if not unit.royal else 2)
        return max(0, value)

    def attack_speed(self, unit: Combatant) -> int:
        weight = unit.weapon.weight if unit.weapon else 0
        return max(0, self.stat(unit, SPD) - max(weight - self.stat(unit, STR), 0))

    def can_attack(self, unit: Combatant, distance: int) -> bool:
        return bool(unit.weapon and not unit.weapon.is_staff and unit.weapon.in_range(distance, self.stat(unit, MAG))
                    and unit.status not in {"sleep", "stone"})

    @staticmethod
    def triangle(unit: Combatant, target: Combatant) -> tuple[int, int]:
        a = unit.weapon.weapon_type if unit.weapon else ""
        b = target.weapon.weapon_type if target.weapon else ""
        if (a, b) in TRIANGLE:
            return TRIANGLE[(a, b)]
        if (b, a) in TRIANGLE:
            damage, hit = TRIANGLE[(b, a)]
            return -damage, -hit
        return 0, 0

    @staticmethod
    def effective(unit: Combatant, target: Combatant) -> bool:
        return bool(unit.weapon and set(unit.weapon.effective) & set(target.categories))

    def side(self, unit: Combatant, target: Combatant, distance: int = 1) -> SideForecast:
        out = SideForecast()
        keys, target_keys = self.skill_keys(unit), self.skill_keys(target)
        out.attack_speed = self.attack_speed(unit)
        out.can_attack = self.can_attack(unit, distance)
        if unit.weapon is None:
            out.notes.append("unarmed")
            return out
        w = unit.weapon
        out.magic = w.magic
        out.effective = self.effective(unit, target)
        triangle_damage, triangle_hit = self.triangle(unit, target)
        out.triangle = (triangle_damage > 0) - (triangle_damage < 0)
        support = unit.support_bonus
        target_support = target.support_bonus
        might = w.might * (3 if out.effective else 1)
        out.atk = self.stat(unit, MAG if out.magic else STR) + might + triangle_damage + support[0]
        if "warmup" in keys:
            out.atk //= 2
        parity = "parity" in keys or "parity" in target_keys
        terrain = (0, 0, 0) if parity else target.terrain
        out.defense = self.stat(target, RES if out.magic else DEF) + terrain[2 if out.magic else 1] + target_support[1]
        out.damage = max(0, out.atk - out.defense)
        out.raw_hit = w.hit + 2 * self.stat(unit, SKL) + self.stat(unit, LCK) + triangle_hit + support[2] + unit.biorhythm
        if "insight" in keys:
            out.raw_hit += 20
        out.avoid = 2 * self.attack_speed(target) + self.stat(target, LCK) + terrain[0] + target_support[3] + target.biorhythm
        if "vigilance" in target_keys:
            out.avoid += 20
        out.raw_crit = w.crit + self.stat(unit, SKL) // 2 + support[4] + unit.biorhythm
        if "wrath" in keys and unit.hp * 10 <= unit.stats[HP] * 3 and "lucky" not in target_keys:
            out.raw_crit += 50
        out.crit_avoid = self.stat(target, LCK) + target_support[5] + (20 if "vigilance" in target_keys else 0)
        daunt = sum(1 for s in target.skills if self._keys.get(s) == "daunt")
        out.raw_hit -= 5 * daunt
        out.raw_crit -= 5 * daunt
        out.hit = _clamp(out.raw_hit - out.avoid)
        out.crit = 0 if "mantle" in target_keys else _clamp(out.raw_crit - out.crit_avoid)
        if "gamble" in keys:
            out.hit //= 2
            out.crit = _clamp(out.crit * 2)
        out.doubles = out.attack_speed >= self.attack_speed(target) + DOUBLE_THRESHOLD
        out.strikes = 2 if "twice" in w.properties else 1
        return out

    def forecast(self, attacker: Combatant, defender: Combatant, distance: int = 1) -> Forecast:
        return Forecast(self.side(attacker, defender, distance), self.side(defender, attacker, distance), distance)

    def proc_chance(self, key: str, owner: Combatant) -> int:
        if key == "adept":
            return _clamp(self.stat(owner, SPD) + owner.biorhythm)
        if key in {"miracle"}:
            return _clamp(self.stat(owner, LCK) + owner.biorhythm)
        if key in {"roar"}:
            return _clamp(self.stat(owner, STR) // 2 + owner.biorhythm)
        if key in {"smash", "soaring"}:
            return _clamp(self.stat(owner, SPD) // 2 + owner.biorhythm)
        if key in {"astra", "aether", "luna", "luna2", "flare", "auroral", "sol", "colossus",
                   "deadeye", "stun", "lethality", "bane", "corrosion", "release"}:
            return _clamp(self.stat(owner, SKL) // 2 + owner.biorhythm)
        return _clamp(self.stat(owner, SKL) + owner.biorhythm)

    def battle_exp(self, winner: Combatant, other: Combatant, *, dealt: bool, killed: bool,
                   constants: Optional[dict] = None) -> int:
        """RFEE01 ``0x8006CA04``/``0x8006CB24`` and ``0x801207B4``.

        The ten mode values come from FE10Data's ``GameData`` rows.  Keeping
        this here prevents the tactical runner from using FE9's promoted-level
        and boss/thief constants for an RD battle.
        """
        if "SID_FINALBOSS" in other.skills:
            return 0
        c = dict(self.difficulty)
        c.update(constants or {})
        actor_level = int(winner.effective_level)
        target_level = int(other.effective_level)
        if "SID_LYCANTHROPE" in winner.skills:
            actor_level *= 2
        if "SID_LYCANTHROPE" in other.skills:
            target_level *= 2
        action_base = int(c.get("action_exp_base", 1))
        action_mul = int(c.get("action_exp_multiplier", 100))
        if "SID_ANIMALIZE" in other.skills:
            action_base += int(c.get("animalize_level_adjustment", 0))
        action = max(1, min(255, (action_base + ((target_level - actor_level + 1) >> 1))
                            * action_mul // 100)) if dealt else 0
        kill = 0
        if killed:
            bonus = (int(c.get("boss_kill_bonus", 0)) if other.boss else
                     int(c.get("steal_kill_bonus", 0)) if "SID_STEAL" in other.skills else 0)
            kill = max(0, min(255, (int(c.get("kill_exp_base", 0)) + target_level - actor_level + bonus)
                                   * int(c.get("kill_exp_multiplier", 100)) // 100))
        award = action + kill
        if award:
            if "SID_PARAGON" in winner.skills:
                award *= 2
            if "SID_BLOSSOM" in winner.skills:
                award //= 2
            award = max(1, min(100, award))
        return min(max(0, 100 - int(winner.exp)), award)

    def simulate(self, attacker: Combatant, defender: Combatant, *, outcomes, distance: int = 1):
        from .engine import ATTACKER, DEFENDER, BattleLog, Decision, Strike

        units = [attacker.copy(), defender.copy()]
        log = BattleLog(units[0], units[1], self.forecast(*units, distance), hp_start=(units[0].hp, units[1].hp))
        keys = [self.skill_keys(u) for u in units]
        number = 0

        def decide(side, kind, chance):
            nonlocal number
            result, roll = outcomes.decide(number + 1, side, kind, chance)
            log.decisions.append(Decision(number + 1, side, kind, chance, result, roll))
            return result

        def proc(side, key):
            return key in keys[side] and decide(side, f"proc:{key}", self.proc_chance(key, units[side]))

        def strike(side, label="", forced=()):
            nonlocal number
            if any(u.hp <= 0 for u in units):
                return
            other, unit, target = 1 - side, units[side], units[1 - side]
            f = self.side(unit, target, distance)
            if not f.can_attack:
                return
            s = Strike(number + 1, side, label=label, hit_chance=f.hit, crit_chance=f.crit)
            if unit.weapon and unit.weapon.durability is not None and unit.weapon.durability > 0:
                unit.weapon.durability -= 1
            s.hit = decide(side, "hit", f.hit)
            if s.hit:
                s.crit = decide(side, "crit", f.crit)
                damage = f.damage * (CRIT_MULTIPLIER if s.crit else 1)
                active = list(forced)
                for key in ("luna2", "luna", "flare", "auroral", "sol", "crush", "colossus", "deadeye", "stun",
                            "lethality", "bane", "roar", "smash", "grandeur", "soaring", "displeasure",
                            "corrosion", "release"):
                    if key in keys[side] and key not in active and proc(side, key):
                        active.append(key)
                if "pavise" in keys[other] and proc(other, "pavise"):
                    active.append("pavise"); damage = 0
                elif "mantle" in keys[other] and "mantle_bypass" not in unit.weapon.properties:
                    active.append("mantle"); damage = 0
                elif "luna2" in active:
                    damage = max(0, f.atk + 4 * self.stat(unit, STR))
                elif "luna" in active:
                    damage = max(0, f.atk + 2 * self.stat(unit, STR))
                elif "flare" in active or "auroral" in active:
                    damage = max(0, f.atk)
                elif "colossus" in active:
                    strength = self.stat(unit, STR); damage = max(f.atk + 2 * strength - f.defense + max(strength - f.defense, 0), 0)
                elif "roar" in active or "grandeur" in active or "soaring" in active:
                    damage = max(f.atk + 2 * self.stat(unit, STR) - f.defense, 0)
                elif "smash" in active:
                    damage = max(f.atk + 4 * self.stat(unit, STR) - f.defense, 0)
                elif any(k in active for k in ("sol", "stun", "deadeye", "displeasure")):
                    damage *= 3
                elif "crush" in active:
                    damage *= 4
                if "lethality" in active and not target.boss and damage < target.hp:
                    damage = max(0, target.hp - 1)
                if "bane" in active and not target.boss:
                    damage = target.hp
                if damage >= target.hp and "mercy" in keys[side] and target.hp > 1:
                    damage = target.hp - 1
                if damage >= target.hp and "miracle" in keys[other] and target.hp > 1 and proc(other, "miracle"):
                    active.append("miracle"); damage = target.hp // 2
                s.procs.extend(active)
                s.damage = min(max(0, damage), target.hp)
                target.hp -= s.damage
                if "sol" in active or "flare" in active:
                    s.heal = min(s.damage, unit.stats[HP] - unit.hp); unit.hp += s.heal
                if "corrosion" in active and target.weapon and target.weapon.durability:
                    target.weapon.durability = max(0, target.weapon.durability - max(1, self.stat(unit, SKL) // 2))
                if "release" in active and target.weapon:
                    target.weapon.durability = 0
                s.kill = target.hp <= 0
            number += 1
            s.hp_after = (units[0].hp, units[1].hp)
            log.strikes.append(s)

        def exchange(side, label=""):
            if any(u.hp <= 0 for u in units) or not self.can_attack(units[side], distance):
                return
            if side == DEFENDER and proc(ATTACKER, "cancel"):
                log.notes.append("Cancel prevents the reply")
                return
            count = self.side(units[side], units[1 - side], distance).strikes
            plan = [(label if i == 0 else "brave", ()) for i in range(count)]
            if proc(side, "astra"):
                plan = [("Astra", ("astra",))] * 5
            elif proc(side, "aether"):
                plan = [("Aether", ("sol",)), ("Aether", ("luna",))]
            elif proc(side, "adept"):
                plan *= 2
            for lbl, forced in plan:
                strike(side, lbl, forced)

        order = [DEFENDER, ATTACKER] if proc(DEFENDER, "vantage") else [ATTACKER, DEFENDER]
        for side in order:
            exchange(side)
        for side in (ATTACKER, DEFENDER):
            if not any(u.hp <= 0 for u in units) and self.side(units[side], units[1 - side], distance).doubles:
                exchange(side, "follow-up")
        log.hp_end = (units[0].hp, units[1].hp)
        return log
