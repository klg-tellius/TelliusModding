"""The battle engine's staging values: where the units stand, how long it
waits, how far it runs, how hard the camera shakes.

Two sources, both read by ``main.dol``:

- ``zdbx/param.dbx`` (``load_battle_effect_tuning_table``): one block of
  ``Key value`` lines. :class:`BattleParams` keeps the ones the fight uses;
  missing keys keep the vanilla values.
- ``zu/<code>_prm.dbx`` (``load_actor_param_database_entry``): per model.
  :class:`UnitParams` keeps the movement keys, with the loader's defaults
  (move speed 0.6, range 10, run count 1).

Units start at ``InitPosL`` / ``InitPosR`` (x -20 / +20), turned +90 / -90
degrees about Y so they face each other along X. Time is in game ticks, 60
per second: battle clips advance one frame per tick, and the waits and the
camera tweens count ticks too.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, fields
from typing import Optional

TICKS_PER_SECOND = 60
#: Yaw of the left (attacker) and right (defender) unit, degrees.
FACING = (90.0, -90.0)
#: ``battle_preview_process_actor_approach_state``: a striker within range + this needs no run.
APPROACH_SLACK = 3.0

_NUMBER = re.compile(r"[-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?")


def number(text: str, default: float = 0.0) -> float:
    """The leading number of ``text``, as ``atof`` reads it: ``"-2.-2"`` is -2,
    ``"40.0f"`` is 40."""
    match = _NUMBER.match(text.strip())
    return float(match.group()) if match else default


def numbers(text: str) -> tuple:
    return tuple(number(part) for part in text.split(","))


@dataclass
class BattleParams:
    """``zdbx/param.dbx``, with the vanilla values as defaults."""

    init_pos_l: tuple = (-20.0, 0.0, 0.0)
    init_pos_r: tuple = (20.0, 0.0, 0.0)
    wait_init: int = 120  # before the first strike
    wait_exp: int = 30
    wait_atk0: int = 1  # before an attack clip starts
    wait_atk1: int = 1  # after it ends
    wait_atk2: int = 20  # before the other unit's turn
    wait_crit0: int = 1
    wait_skill0: int = 1
    wait_shoot1: int = 20
    wait_magic1: int = 1
    wait_die1: int = 20
    quake_attack: float = 0.5
    quake_crit: float = 1.8
    quake_skill: float = 1.8
    quake_shoot: float = 0.5
    quake_magic: float = 1.2
    attack_dist_scale: float = 1.0
    knife_speed: float = 2.8
    spear_speed: float = 5.0
    axe_speed: float = 4.5
    arrow_speed: float = 6.0
    shoot_damage_dist: float = 2.8
    death_eff_time: int = 30  # EID_K_DEATH starts this long before the death clip's fade (code 0x38)
    damage_eff_wait: int = 1  # ticks from a blow landing to its hit effect (EID_K_ATTACK)
    foot_eff_scale: tuple = (1.0, 1.0, 1.0, 1.0)

    KEYS = {
        "InitPosL": "init_pos_l", "InitPosR": "init_pos_r", "WaitInit": "wait_init", "WaitExp": "wait_exp",
        "WaitAtk0": "wait_atk0", "WaitAtk1": "wait_atk1", "WaitAtk2": "wait_atk2", "WaitCrit0": "wait_crit0",
        "WaitSkill0": "wait_skill0", "WaitShoot1": "wait_shoot1", "WaitMagic1": "wait_magic1",
        "WaitDie1": "wait_die1", "QuakeAttack": "quake_attack", "QuakeCrit": "quake_crit",
        "QuakeSkill": "quake_skill", "QuakeShoot": "quake_shoot", "QuakeMagic": "quake_magic",
        "AttackDistScale": "attack_dist_scale", "KnifeSpeed": "knife_speed", "SpearSpeed": "spear_speed",
        "AxeSpeed": "axe_speed", "ArrowSpeed": "arrow_speed", "ShootDamageDist": "shoot_damage_dist",
        "DeathEffTime": "death_eff_time", "DamageEffWait": "damage_eff_wait", "FootEffScale": "foot_eff_scale",
    }

    @classmethod
    def from_text(cls, text: str) -> "BattleParams":
        params = cls()
        kinds = {f.name: type(f.default) for f in fields(cls)}
        for line in text.splitlines():
            line = line.split("#", 1)[0].strip()
            key, _sep, value = line.partition("\t") if "\t" in line else line.partition(" ")
            attr = cls.KEYS.get(key.strip())
            value = value.strip()
            if attr is None or not value:
                continue
            kind = kinds[attr]
            if kind is tuple:
                setattr(params, attr, (numbers(value) + (0.0, 0.0, 0.0))[:3])
            elif kind is int:
                setattr(params, attr, int(number(value)))
            else:
                setattr(params, attr, number(value))
        return params

    def start_x(self, side: int) -> float:
        return float((self.init_pos_l, self.init_pos_r)[side][0])


@dataclass
class UnitParams:
    """The movement keys of ``zu/<code>_prm.dbx``."""

    move_speed: float = 0.6  # 移動速度, units per tick while running
    range: float = 10.0  # 間合い
    run_count: int = 1  # 走り回数: the run clip plays this many times
    flying: bool = False  # 飛行系
    jump_attack: bool = False  # ジャンプ攻撃: the attack clip covers the approach
    jump_attack2: bool = False  # ジャンプ攻撃２
    jump_crit: bool = False  # ジャンプ必殺
    jump_finish: bool = False  # ジャンプ止め
    jump_skill: bool = False  # ジャンプ奥義

    @classmethod
    def from_values(cls, values: Optional[dict]) -> "UnitParams":
        values = values or {}
        p = cls()

        def get(key: str) -> Optional[float]:
            text = values.get(key)
            return number(text) if text not in (None, "") else None

        speed, rng, runs = get("移動速度"), get("間合い"), get("走り回数")
        p.move_speed = speed if speed else p.move_speed
        p.range = rng if rng else p.range
        p.run_count = int(runs) if runs else p.run_count
        p.flying = bool(get("飛行系"))
        p.jump_attack = bool(get("ジャンプ攻撃"))
        p.jump_attack2 = bool(get("ジャンプ攻撃２"))
        p.jump_crit = bool(get("ジャンプ必殺"))
        p.jump_finish = bool(get("ジャンプ止め"))
        p.jump_skill = bool(get("ジャンプ奥義"))
        return p

    def jumps(self, mode: str, second: bool = False) -> bool:
        """Whether the attack clip of ``mode`` ("attack", "crit", "finish",
        "skill") leaps in by itself, so the unit does not run first."""
        if mode == "attack":
            return self.jump_attack2 if second else self.jump_attack
        return {"crit": self.jump_crit, "finish": self.jump_finish, "skill": self.jump_skill}.get(mode, False)
