"""Turns a :class:`~.engine.BattleLog` into what the battle scene shows,
tick by tick, following ``update_battle_preview_frame`` (the battle's state
machine in ``main.dol``). Ticks are game frames, 60 per second
(:data:`FPS`); clips advance one frame per tick.

The fight opens with both units idle at their start spots for ``WaitInit``
ticks while ``cam1`` plays ``standby`` (``standby2`` at range) between them. Then, for each strike (one queued record):

- **wait**: ``WaitAtk2`` ticks before a strike by the other unit (none
  before the first one, or between two strikes of the same unit);
- **melee approach**: a striker farther than its range (``間合い``) + 3
  from its target plays its run clip ``走り回数`` times while moving
  ``移動速度`` units a tick toward the spot its range away from the target
  (and stops there), unless its attack clip leaps in by itself
  (``ジャンプ攻撃``...);
- **attack**: after ``WaitAtk0`` (normal) or one tick (critical, skill),
  the striker plays 攻撃1 / 攻撃2, 必殺1, 必殺2 (a critical that kills) or
  奥義 (a strike with an attack skill), or 投げ / 必殺投げ / 奥義投げ for a
  thrown weapon, and its camera script starts: ``atk_l``, ``crit_l``,
  ``crit2_l``, ``mag_at_l`` (bows, tomes), ``mag_crit_l`` / ``mag_skill_l``
  (tomes), ``atk_hand_sp_l`` / ``atk_hand_ax_l`` (thrown spears / axes). A
  strike by the defender plays the same script mirrored, following the
  defender. Most models have their own camera for the clip
  (``xcam/<model>/cam.cmp``, named by the clip's first 11 characters:
  ``fig1_at1_ax``); any clip a unit switches to starts it, run clips
  included, and the generic script is then skipped;
- **blow**: a hit lands on the clip's combat event 0 (the target plays
  ダメージ, or 死亡 on a kill, and the camera shakes by ``QuakeAttack`` /
  ``QuakeCrit`` / ``QuakeSkill`` / ``QuakeShoot`` / ``QuakeMagic`` when
  damage is dealt); a miss makes the target dodge (回避) on event 1. Bows
  and thrown weapons release their missile on event 2, which flies at
  ``ArrowSpeed`` / ``SpearSpeed`` / ``AxeSpeed`` / ``KnifeSpeed`` and lands
  ``ShootDamageDist`` from the target; ``bow_impact_l`` follows the arrow
  or spear. A spell plays ``<NAME>_at0`` (``WIND_at0``) as it leaves the
  caster and ``<NAME>_at1`` as it hits, filming the target
  (``mag_impact_l`` instead for magic swords, hit or miss);
- **end**: the next record starts ``WaitAtk1`` ticks after the attack clip
  ends (``WaitShoot1`` after a missile, ``WaitMagic1`` after a spell). A
  kill plays ``ded_l`` on the dead unit and waits for its death clip and
  ``WaitDie1``.

A clip named ``<role>_<previous role>`` (``必殺1_攻撃1``...) replaces the
plain one when the unit's table has it (``substitute_battle_preview_animation_state``).

Effects (:class:`Cue`, ``kind`` "effect", the ``EID_`` pack to play) are spawned where the engine
spawns them, at the unit's root on the ground, turned as the unit is:

- a blow that deals damage: ``EID_K_ATTACK`` (``EID_K_SP_ATTACK`` for a critical or skill strike)
  on the struck unit ``DamageEffWait`` ticks after it lands (``gactor_process_battle_attack_tick``),
  or the weapon table's ``damageEffId`` for a missile weapon (Flame Lance, Lightning Bow); none
  for a spell, whose own effect is the hit;
- a blow for no damage: ``EID_NODAMAGE`` and ``EID_K_SPARK_ND``; a miss: ``EID_MISS``; both 6
  units up (``battle_preview_state_no_damage``, ``battle_preview_spawn_miss_visual_effect``);
- a spell: the weapon table's ``effectId`` (``EID_K_WIND``...) starts on the cast clip's event 2,
  at the caster aimed at the target for a missile weapon (tomes, magic swords) and on the target
  otherwise (``battle_preview_orient_effect_toward_target``). Its code 17 moves it to the target at
  once, code 18 over the frames to its code 19 (``0x8015160C``); the blow lands on the effect's own
  event 0 and a miss on its event 1;
- a death: ``EID_K_DEATH`` ``DeathEffTime`` ticks before the death clip's fade (code 0x38);
- dust: clip codes 0x2B, 0x2C, 0x2D, 0x2E and 0x3C raise ``EID_CLOUDOFDUST`` 1-5, or the
  ``CLOUDOFSNOW`` / ``WATERSPLASH`` ones, by the backdrop's ``footEffect`` (1 dust, 2 water,
  3 snow; ``gactor_dispatch_attack_animation_events``).

Not modelled: the knock-back on damage, the dodge step back, returning hand axes, and the units'
root motion inside a clip.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Callable, Optional, Sequence

from . import camera as cam
from . import scene_assets as sa
from .engine import BattleLog
from .staging import APPROACH_SLACK, TICKS_PER_SECOND, BattleParams, UnitParams

FPS = TICKS_PER_SECOND
HIT_EFFECT, SPECIAL_HIT_EFFECT = "EID_K_ATTACK", "EID_K_SP_ATTACK"
MISS_EFFECT, NO_DAMAGE_EFFECTS, DEATH_EFFECT = "EID_MISS", ("EID_NODAMAGE", "EID_K_SPARK_ND"), "EID_K_DEATH"
MARK_HEIGHT = 6.0  # the miss and no-damage marks float this far above the unit
DEATH_FADE = 0x38  # death clip code where the body fades
CLIP_CAMERA_CHARS = 11  # a clip's camera script is named by its first 11 characters
#: Clip codes that raise dust, and the effects per backdrop footEffect (1 dust, 2 water, 3 snow).
DUST_CODES = {0x2B: 0, 0x2C: 1, 0x2D: 2, 0x2E: 3, 0x3C: 4}
FOOT_EFFECTS = {
    1: ("EID_CLOUDOFDUST", "EID_CLOUDOFDUST2", "EID_CLOUDOFDUST3", "EID_CLOUDOFDUST4", "EID_CLOUDOFDUST5"),
    2: ("EID_WATERSPLASH2", "EID_WATERSPLASH3", "EID_WATERSPLASH4", "EID_WATERSPLASH5", "EID_WATERSPLASH6"),
    3: ("EID_CLOUDOFSNOW", "EID_CLOUDOFSNOW2", "EID_CLOUDOFSNOW3", "EID_CLOUDOFSNOW4", "EID_CLOUDOFSNOW5"),
}
OPENING_HEIGHT = 9.0  # the opening shot looks this far above the units' cam bones (scene +0x18C)
#: Skills that make a strike a "skill" strike (奥義 clip, QuakeSkill).
ATTACK_SKILLS = frozenset({"astra", "sol", "luna", "aether", "rumbling", "impact", "corrosion", "snipe", "sunlight"})
#: Skills whose effect plays on the unit that owns them while being struck.
DEFENDER_SKILLS = frozenset({"wing_guard", "pray"})
#: battle_weapons.KINDS of missiles.
BOW, KNIFE, SPEAR, THROWN_AXE = 3, 5, 6, 7
#: Role fallbacks of battle_preview_set_animation_state.
FALLBACKS = {sa.ATTACK2: sa.ATTACK1, sa.CRIT2: sa.CRIT1, sa.SKILL: sa.ATTACK1, sa.SKILL_THROW: sa.THROW}


@dataclass(frozen=True)
class Clip:
    stem: str
    length: float  # frames
    impact: Optional[float] = None  # frame of combat event 0 (blow lands)
    swing: Optional[float] = None  # frame of combat event 1 (a miss is dodged)
    release: Optional[float] = None  # frame of combat event 2 (the thrown or fired item leaves)
    events: tuple = ()  # (frame, code) of the clip's other event codes (sounds left out)

    @property
    def contact(self) -> float:
        for frame in (self.impact, self.swing):
            if frame is not None and 0 <= frame <= self.length:
                return frame
        return self.length / 2

    @property
    def dodge(self) -> float:
        for frame in (self.swing, self.impact):
            if frame is not None and 0 <= frame <= self.length:
                return frame
        return self.length / 2


#: ``lookup(side, role)`` -> the side's clip for that role, or None.
ClipLookup = Callable[[int, str], Optional[Clip]]


@dataclass
class Segment:
    side: int
    start: float
    end: float
    clip: Optional[Clip]
    role: str
    loop: bool = False
    hold: bool = False  # keep the last frame after ``end`` (death)

    def frame(self, t: float) -> float:
        if self.clip is None:
            return 0.0
        local = t - self.start
        length = max(self.clip.length, 1.0)
        if self.loop:
            return local % length
        return min(local, length)


@dataclass
class Change:
    frame: float
    side: int  # who was struck
    hp: tuple  # both sides' HP from this frame on
    text: str  # "12", "Miss", "Crit 36"...
    strike: int


@dataclass
class Cue:
    """A visual effect starting at ``frame`` on ``side``: a skill that
    triggered (``kind`` "skill", ``key`` a :data:`rules_fe9.SKILL_NAMES` key)
    or a spell landing (``kind`` "spell", ``key`` the tome's ``EID_`` effect)."""

    frame: float
    side: int
    kind: str  # "skill" (key: a SKILL_NAMES key) or "effect" (key: the EID_ pack)
    key: str
    height: float = 0.0  # above the ground
    aim: Optional[int] = None  # the side a spell moves to on its codes 17 / 18-19


@dataclass(frozen=True)
class WeaponEffects:
    """The effect fields of a weapon's ``xwp/<NAME>.dbx`` table (:mod:`..formats.battle_weapons`)."""

    missile: int = 0  # 1 bows, thrown weapons, tomes; 2 magic swords
    effect: Optional[str] = None  # effectId: the spell
    damage_effect: Optional[str] = None  # damageEffId: replaces the hit effect



@dataclass
class Flight:
    """A thrown or fired item travelling from ``side`` to the other unit."""

    start: float
    end: float
    side: int

    def progress(self, t: float) -> Optional[float]:
        if self.start <= t < self.end:
            return (t - self.start) / max(self.end - self.start, 1e-6)
        return None


@dataclass
class Move:
    """``side`` moving along X from ``x0`` to ``x1`` between two ticks."""

    side: int
    start: float
    end: float
    x0: float
    x1: float


@dataclass
class Timeline:
    segments: list = field(default_factory=list)
    changes: list = field(default_factory=list)
    cues: list = field(default_factory=list)
    flights: list = field(default_factory=list)
    moves: list = field(default_factory=list)
    camera: list = field(default_factory=list)  # camera.Cue
    quakes: list = field(default_factory=list)  # camera.Quake
    length: float = 0.0
    hp_start: tuple = (0, 0)
    start_x: tuple = (-20.0, 20.0)

    def segment(self, side: int, t: float) -> Optional[Segment]:
        """The segment ``side`` plays at frame ``t``: the last held one past its end, and at or
        past the end of the fight the last one started (so a unit never drops to its bind pose)."""
        current = latest = None
        for seg in self.segments:
            if seg.side != side:
                continue
            if seg.start <= t < seg.end or (seg.hold and t >= seg.start):
                current = seg
            if seg.start <= t and (latest is None or seg.start >= latest.start):
                latest = seg
        return current or latest

    def pose(self, side: int, t: float) -> tuple[Optional[str], float]:
        """``(clip stem, clip frame)`` for ``side`` at frame ``t``."""
        seg = self.segment(side, t)
        if seg is None or seg.clip is None:
            return None, 0.0
        return seg.clip.stem, seg.frame(t)

    def x(self, side: int, t: float) -> float:
        """Where ``side`` stands along X at frame ``t``."""
        x = self.start_x[side]
        for move in self.moves:
            if move.side != side or t < move.start:
                continue
            if t >= move.end:
                x = move.x1
            else:
                x = move.x0 + (move.x1 - move.x0) * (t - move.start) / max(move.end - move.start, 1e-6)
        return x

    def hp(self, t: float) -> tuple:
        hp = self.hp_start
        for change in self.changes:
            if change.frame <= t:
                hp = change.hp
        return hp

    def popup(self, t: float, duration: float = 48) -> Optional[Change]:
        """The damage text shown at ``t``, if a blow landed in the last ``duration`` frames."""
        shown = None
        for change in self.changes:
            if change.frame <= t < change.frame + duration:
                shown = change
        return shown


def _mode(strike) -> str:
    if ATTACK_SKILLS & set(strike.procs):
        return "skill"
    if strike.crit:
        return "finish" if strike.kill else "crit"
    return "attack"


class _Builder:
    def __init__(self, log: BattleLog, lookup: ClipLookup, distance: int, params: BattleParams,
                 units: Sequence[UnitParams], weapon_kinds: Sequence[Optional[int]],
                 weapons: Sequence[WeaponEffects] = (), effect_clip: Callable[[str], Optional[Clip]] = None,
                 foot_effect: int = 1, cameras=()):
        self.log, self.lookup, self.distance, self.params = log, lookup, distance, params
        self.units, self.kinds = units, weapon_kinds
        self.weapons = list(weapons) + [WeaponEffects()] * (2 - len(weapons))
        self.effect_clip = effect_clip or (lambda eid: None)
        self.foot_effect = foot_effect
        self.tl = Timeline(hp_start=log.hp_start, start_x=(params.start_x(0), params.start_x(1)))
        self.x = list(self.tl.start_x)
        self.busy = [0.0, 0.0]  # tick each side's last clip ends
        self.last_role = ["", ""]
        self.dead = [False, False]
        self.cameras = frozenset(cameras)  # camera script names the scene knows
        self.clip_camera = [False, False]  # actor +0x1A7: the last clip switch started a camera

    # -- clips ------------------------------------------------------------------------------------
    def clip(self, side: int, role: str) -> tuple[str, Optional[Clip]]:
        """The clip ``side`` plays for ``role``: its ``<role>_<previous>`` variant, the
        role, then the engine's fallback."""
        while role:
            previous = self.last_role[side]
            if previous:
                variant = self.lookup(side, f"{role}_{previous}")
                if variant is not None:
                    return role, variant
            found = self.lookup(side, role)
            if found is not None:
                return role, found
            if role not in FALLBACKS:
                return role, None
            role = FALLBACKS[role]
        return role, None

    def idle(self, side: int, until: float) -> None:
        if self.dead[side] or until <= self.busy[side]:
            return
        clip = self.lookup(side, sa.IDLE) or self.lookup(side, sa.READY)
        self.tl.segments.append(Segment(side, self.busy[side], until, clip, sa.IDLE, loop=True))
        self.busy[side] = until

    def play(self, side: int, start: float, role: str, *, hold: bool = False, loop_for: float = 0.0) -> Optional[Clip]:
        """Start ``role`` on ``side`` at ``start``, cutting whatever it still played."""
        role, clip = self.clip(side, role)
        self.idle(side, start)
        for seg in self.tl.segments:
            if seg.side == side and seg.end > start:
                seg.end = max(start, seg.start)
        length = loop_for or (clip.length if clip else 20.0)
        self.tl.segments.append(Segment(side, float(start), float(start + length), clip, role,
                                        loop=bool(loop_for), hold=hold))
        self.busy[side] = start + length
        self.last_role[side] = role
        if clip is not None:  # gactor_switch_animation_module: the clip's own camera
            name = clip.stem[:CLIP_CAMERA_CHARS]
            self.clip_camera[side] = name in self.cameras
            if self.clip_camera[side]:
                self.tl.camera.append(cam.Cue(int(start), name, side, side == 1))
        dust = FOOT_EFFECTS.get(self.foot_effect)
        if clip is not None and dust and not loop_for:
            for frame, code in clip.events:
                if code in DUST_CODES and frame <= length:
                    self.effect(start + frame, side, dust[DUST_CODES[code]])
        return clip

    def effect(self, frame: float, side: int, eid: Optional[str], height: float = 0.0,
               aim: Optional[int] = None) -> None:
        if eid:
            self.tl.cues.append(Cue(float(frame), side, "effect", eid, height, aim))

    # -- strikes ----------------------------------------------------------------------------------
    def build(self) -> Timeline:
        p = self.params
        first = self.log.strikes[0].side if self.log.strikes else 0
        middle = ((self.x[0] + self.x[1]) / 2, OPENING_HEIGHT, 0.0)
        self.tl.camera.append(cam.Cue(1, "standby" if self.distance == 1 else "standby2", 0, first == 1, middle))
        t = 1 + p.wait_init + 2  # states 0, 1 (WaitInit), 2, 3
        previous = None
        for index, strike in enumerate(self.log.strikes):
            t += 1  # state 4: next record
            same = previous == strike.side
            t += max(p.wait_atk2 if index and not same else 0, 1)  # state 5
            t = self.strike(strike, t, second=same and strike.label in ("brave", "Astra"))
            previous = strike.side
        t += 2 + p.wait_exp  # the closing record, then WaitExp
        end = max(t, *self.busy)
        for side in (0, 1):
            self.idle(side, end)
        self.tl.length = float(end)
        return self.tl

    def strike(self, s, t: float, second: bool) -> float:
        p, tl = self.params, self.tl
        side, other = s.side, 1 - s.side
        unit = (self.log.attacker, self.log.defender)[side]
        w = unit.weapon
        kind = self.kinds[side] if side < len(self.kinds) else None
        mode = _mode(s)
        slot, mirror = side, side == 1
        if w is not None and w.magic:
            path = "magic"
        elif kind == BOW or (w is not None and w.weapon_type == "bow"):
            path = "bow"
        elif self.distance > 1:
            path = "throw"
        else:
            path = "melee"

        if path == "melee":
            t = self.approach(side, other, t, mode, second)
            t += 1  # waits for the run clip, then sets the pre-attack wait
            t += (p.wait_atk0 + 1) if mode == "attack" else 0

        if path == "throw":
            role = {"skill": sa.SKILL_THROW, "attack": sa.THROW}.get(mode, sa.CRIT_THROW)
        else:
            role = {"attack": sa.ATTACK2 if second else sa.ATTACK1, "crit": sa.CRIT1, "finish": sa.CRIT2,
                    "skill": sa.SKILL}[mode]
        start = t
        clip = self.play(side, start, role)
        length = clip.length if clip else 30.0

        script = {"melee": {"attack": "atk_l", "skill": "atk_l", "crit": "crit_l", "finish": "crit2_l"}[mode],
                  "bow": "mag_at_l",
                  "magic": {"crit": "mag_crit_l", "finish": "mag_crit_l", "skill": "mag_skill_l"}.get(mode, "mag_at_l"),
                  "throw": "atk_hand_sp_l" if kind == SPEAR else "atk_hand_ax_l"}[path]
        if not self.clip_camera[side]:  # battle_play_record_camera_script skips it then
            tl.camera.append(cam.Cue(int(start), script, slot, mirror))

        contact = start + (clip.contact if clip else length / 2)
        dodge = start + (clip.dodge if clip else length / 2)
        fx = self.weapons[side]
        spell = (fx.effect or (w.effect if w is not None else None)) if path == "magic" else None
        name = w.iid[4:] if w is not None and w.iid.startswith("IID_") else ""
        cast = start + (clip.release if clip and clip.release is not None else length)
        if path == "magic" and name:
            tl.camera.append(cam.Cue(int(cast), f"{name}_at0", slot, mirror))
        if spell:
            # the spell starts on the cast clip's event 2 (or its end); its own events time the blow
            self.effect(cast, side if fx.missile in (1, 2) else other, spell, aim=other)
            eff = self.effect_clip(spell)
            if eff is not None:
                contact = cast + (eff.impact if eff.impact is not None else eff.contact)
                dodge = cast + (eff.swing if eff.swing is not None else eff.dodge)
        if path in ("bow", "throw"):
            release = start + (clip.release if clip and clip.release is not None else (clip.contact if clip else length / 2))
            speed = {BOW: p.arrow_speed, SPEAR: p.spear_speed, KNIFE: p.knife_speed}.get(
                kind, p.arrow_speed if path == "bow" else p.axe_speed)
            gap = abs(self.x[other] - self.x[side])
            contact = dodge = release + max(math.ceil(max(gap - p.shoot_damage_dist, 0.0) / max(speed, 1e-6)), 1)
            tl.flights.append(Flight(release, contact, side))
            if path == "bow" or kind == SPEAR:
                tl.camera.append(cam.Cue(int(release), "bow_impact_l", slot, mirror))

        quake = {"melee": {"attack": p.quake_attack, "crit": p.quake_crit, "finish": p.quake_crit,
                           "skill": p.quake_skill}[mode],
                 "bow": p.quake_shoot, "throw": p.quake_shoot, "magic": p.quake_magic}[path]
        if path == "magic" and (s.hit or fx.missile == 2):
            if fx.missile == 2:
                tl.camera.append(cam.Cue(int(contact if s.hit else dodge), "mag_impact_l", slot, mirror))
            elif name:
                tl.camera.append(cam.Cue(int(contact), f"{name}_at1", slot, mirror))
        if s.hit:
            reaction = self.play(other, contact, sa.DEATH if s.kill else sa.DAMAGE, hold=s.kill)
            if s.damage > 0:
                tl.quakes.append(cam.Quake(int(contact), quake))
                if path != "magic":
                    hit = fx.damage_effect if fx.damage_effect and (fx.missile == 1 or self.distance > 1) else \
                        SPECIAL_HIT_EFFECT if mode in ("crit", "finish", "skill") else HIT_EFFECT
                    self.effect(contact + p.damage_eff_wait, other, hit)
            else:
                for eid in NO_DAMAGE_EFFECTS:
                    self.effect(contact, other, eid, MARK_HEIGHT)
            if s.kill:
                fade = next((f for f, code in reaction.events if code == DEATH_FADE), reaction.length) \
                    if reaction is not None else 60.0
                self.effect(contact + max(fade - p.death_eff_time, 1), other, DEATH_EFFECT)
            text = f"Crit {s.damage}" if s.crit else str(s.damage)
        else:
            contact = dodge
            reaction = self.play(other, contact, sa.DODGE)
            self.effect(contact, other, MISS_EFFECT, MARK_HEIGHT)
            text = "Miss"
        if s.kill:
            self.dead[other] = True
        tl.changes.append(Change(contact, other, s.hp_after, text, s.number))
        if s.label == "Counter":
            tl.cues.append(Cue(start, side, "skill", "counter"))
        for key in s.procs:
            tl.cues.append(Cue(contact, other if key in DEFENDER_SKILLS else side, "skill", key))

        end = start + length
        if path in ("bow", "throw"):
            t = max(end, contact + 1) + p.wait_shoot1
        elif path == "magic":
            t = max(end, contact + (reaction.length if reaction else 20.0)) + p.wait_magic1
        else:
            t = end + max(p.wait_atk1, 1)
        if s.kill:
            tl.camera.append(cam.Cue(int(t), "ded_l", slot, mirror))
            death_end = contact + (reaction.length if reaction else 60.0)
            t = max(t + 2, death_end) + 1 + p.wait_die1
        return t

    def approach(self, side: int, other: int, t: float, mode: str, second: bool) -> float:
        """``battle_preview_process_actor_approach_state``: run in when out of range."""
        unit = self.units[side] if side < len(self.units) else UnitParams()
        gap = abs(self.x[other] - self.x[side])
        if unit.jumps(mode, second) or gap <= APPROACH_SLACK + unit.range:
            return t + 1
        run = self.lookup(side, sa.RUN)
        if run is not None:
            steps = int(run.length) * max(unit.run_count, 1)
        else:
            steps = math.ceil((gap - unit.range * self.params.attack_dist_scale) / max(unit.move_speed, 1e-6))
        steps = max(steps, 1)
        direction = 1.0 if self.x[other] > self.x[side] else -1.0
        # the engine aims at the target minus its range; it never runs through the target
        reach = max(gap - unit.range * self.params.attack_dist_scale, 0.0)
        x1 = self.x[side] + direction * min(unit.move_speed * steps, reach)
        self.tl.moves.append(Move(side, float(t), float(t + steps), self.x[side], x1))
        self.x[side] = x1
        self.play(side, t, sa.RUN, loop_for=steps)
        return t + steps + 1


def build(log: BattleLog, lookup: ClipLookup, *, distance: int = 1, params: Optional[BattleParams] = None,
          units: Optional[Sequence[UnitParams]] = None,
          weapon_kinds: Sequence[Optional[int]] = (None, None),
          weapons: Sequence[WeaponEffects] = (), effect_clip: Optional[Callable[[str], Optional[Clip]]] = None,
          foot_effect: int = 1, cameras=()) -> Timeline:
    """The timeline of ``log``; ``units`` are the sides' model parameters, ``weapon_kinds`` their
    weapons' ``xwp`` kinds (``battle_weapons.KINDS``) and ``weapons`` those tables' effect fields.
    ``effect_clip(eid)`` gives an effect's animation (length and events) and ``foot_effect`` is the
    backdrop's ground (``zbg/<name>/param.dbx``). ``cameras`` are the camera script names
    loaded (:attr:`.camera.GameCamera.scripts`): a clip with its own camera plays it."""
    return _Builder(log, lookup, distance, params or BattleParams(), units or (UnitParams(), UnitParams()),
                    weapon_kinds, weapons, effect_clip, foot_effect, cameras).build()
