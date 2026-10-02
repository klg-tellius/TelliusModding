"""Turns a :class:`~.engine.BattleLog` into what each unit plays, frame by frame.

For every strike the striker plays its attack (or critical, shot, throw,
spell) clip. The target reacts when the blow lands: the frame of the
clip's ``.ga`` combat event 0 ("the blow lands", see
:data:`fe_modding.rig_contract.COMBAT_CODES`), else event 1 ("the swing"),
else half-way through the clip. It plays its damage clip on a hit, its dodge
clip on a miss and its death clip on a kill, and HP changes on that frame.
Between clips both units loop their idle clip; a dead unit holds the last
frame of its death clip.

The archive's ``.ga`` article says event 1 is the frame the attack connects;
the rig contract names 0. This follows the rig contract and falls back to 1.
Battle frames are played at 30 per second, like the 3D model preview.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Optional

from . import scene_assets as sa
from .engine import BattleLog

FPS = 30
LEAD_FRAMES = 20  # idle before the first strike
GAP_FRAMES = 8  # idle between strikes
TAIL_FRAMES = 40  # after the last strike


@dataclass(frozen=True)
class Clip:
    stem: str
    length: float  # frames
    impact: Optional[float] = None  # frame of combat event 0 (blow lands)
    swing: Optional[float] = None  # frame of combat event 1

    @property
    def contact(self) -> float:
        for frame in (self.impact, self.swing):
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
class Timeline:
    segments: list = field(default_factory=list)
    changes: list = field(default_factory=list)
    length: float = 0.0
    hp_start: tuple = (0, 0)

    def segment(self, side: int, t: float) -> Optional[Segment]:
        """The segment ``side`` plays at frame ``t`` (the last held one past its end)."""
        current = None
        for seg in self.segments:
            if seg.side != side:
                continue
            if seg.start <= t < seg.end or (seg.hold and t >= seg.start):
                current = seg
        return current

    def pose(self, side: int, t: float) -> tuple[Optional[str], float]:
        """``(clip stem, clip frame)`` for ``side`` at frame ``t``."""
        seg = self.segment(side, t)
        if seg is None or seg.clip is None:
            return None, 0.0
        return seg.clip.stem, seg.frame(t)

    def hp(self, t: float) -> tuple:
        hp = self.hp_start
        for change in self.changes:
            if change.frame <= t:
                hp = change.hp
        return hp

    def popup(self, t: float, duration: float = 24) -> Optional[Change]:
        """The damage text shown at ``t``, if a blow landed in the last ``duration`` frames."""
        shown = None
        for change in self.changes:
            if change.frame <= t < change.frame + duration:
                shown = change
        return shown


def build(log: BattleLog, lookup: ClipLookup, *, distance: int = 1) -> Timeline:
    tl = Timeline(hp_start=log.hp_start)
    busy = [0.0, 0.0]  # frame each side is free from
    dead = [False, False]
    units = (log.attacker, log.defender)

    def idle(side: int, until: float) -> None:
        if dead[side] or until <= busy[side]:
            return
        clip = lookup(side, sa.IDLE) or lookup(side, sa.READY)
        tl.segments.append(sa_segment(side, busy[side], until, clip, sa.IDLE, loop=True))
        busy[side] = until

    t = float(LEAD_FRAMES)
    previous_side = None
    for strike in log.strikes:
        side, other = strike.side, 1 - strike.side
        unit = units[side]
        w = unit.weapon
        role = sa.attack_role(
            _roles(lookup, side), crit=strike.crit, second=previous_side == side and strike.label in ("brave", "Astra"),
            weapon_type=w.weapon_type if w else "", magic=bool(w and w.magic), ranged=distance > 1)
        previous_side = side
        attack = lookup(side, role)
        start = max(t, busy[side], busy[other] if not dead[other] else t)
        idle(side, start)
        idle(other, start)
        length = attack.length if attack else 30.0
        contact = start + (attack.contact if attack else length / 2)
        tl.segments.append(sa_segment(side, start, start + length, attack, role))
        busy[side] = start + length

        reaction_role = sa.DEATH if strike.kill else (sa.DAMAGE if strike.hit else sa.DODGE)
        reaction = lookup(other, reaction_role)
        idle(other, contact)
        r_length = reaction.length if reaction else 20.0
        tl.segments.append(sa_segment(other, contact, contact + r_length, reaction, reaction_role,
                                      hold=strike.kill))
        busy[other] = contact + r_length
        if strike.kill:
            dead[other] = True
        text = "Miss" if not strike.hit else (f"Crit {strike.damage}" if strike.crit else str(strike.damage))
        tl.changes.append(Change(contact, other, strike.hp_after, text, strike.number))
        t = max(busy[side], busy[other]) + GAP_FRAMES

    end = max(t, *busy) + TAIL_FRAMES
    for side in (0, 1):
        idle(side, end)
    tl.length = end
    return tl


def _roles(lookup: ClipLookup, side: int) -> dict:
    """The attack roles the side has a clip for (for :func:`scene_assets.attack_role`)."""
    roles = (sa.ATTACK1, sa.ATTACK2, sa.CRIT1, sa.CRIT2, sa.SHOT, sa.CRIT_SHOT, sa.THROW, sa.CRIT_THROW, sa.SPELL)
    return {r: True for r in roles if lookup(side, r) is not None}


def sa_segment(side, start, end, clip, role, *, loop=False, hold=False) -> Segment:
    return Segment(side, float(start), float(end), clip, role, loop=loop, hold=hold)
