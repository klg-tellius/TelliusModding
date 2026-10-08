"""The battle camera, tick by tick, as ``main.dol`` drives it.

**Rigs** (``zdbx/camera.dbx``, ``kaneko_camera_construct``): each ``Camera``
block is its own camera object with ``dest`` (the look-at point when it
follows no unit), ``offs``, ``rot`` (pitch, yaw, roll in degrees), ``dist``
and up to three unit slots (``entityName``, ``entityName1``,
``entityName2``: ``charaAtk`` / ``charaDef`` / ``charaSup``). One rig is
active at a time; the fight opens on ``cam1``.

**View** (``KanekoCamera::compute_eye_and_target_basis``): with ``attract``
set, the camera looks at ``target + offs``, where ``target`` is the followed
unit's ``cam`` bone (``gactor_default_actor_get_bone_position_b``) or
``dest``, from ``Ry(yaw) * Rx(pitch) * (0, 0, -dist)`` away; up is +Y. The
projection is the scene camera's: 30 degrees vertical field of view, 4:3.

**Scripts** (``xcam/*.dbx``, ``CameraAnime``): starting one
(``FUN_801caf94``) makes its rig active, sets which unit slot it follows and
the two mirror flags, and restarts at keyframe 0. Each tick
(``slot_00_FUN_801cb2a4``) the next keyframe is handed to the rig as soon as
the previous one has finished moving (keyframe 0 at once). A keyframe
(``FUN_800e8bf8``) tweens ``offs`` (skipped when ``pos`` is 0, 0, 0), the
pitch and yaw, and ``dist`` to its values over ``time`` ticks (0 = cut).
Mirrored scripts use ``yaw' = 360 - yaw`` and ``x' = -x``.

**Tweens** (``update_point_track_with_distance`` /
``update_tween_animation_progress``): a Catmull-Rom Hermite from the current
value to the target, its tangents taken from the previous tween's start, one
step per tick.

**Clip and spell cameras** (``xcam/<model>/cam.cmp``, ``xcam/magic/cam.cmp``,
:meth:`GameCamera.with_packs`): an actor switching to a clip plays the script
named by the clip's first 11 characters when there is one, on the actor's own
slot (attacker 0, defender 1, mirrored); the strike's generic script
(``atk_l``, ``mag_at_l``...) is then skipped. Spells play ``<NAME>_at0`` when
they leave the caster and ``<NAME>_at1`` when they hit.

**Opening** (``FUN_800d06bc``): on the fight's second tick ``cam1`` is
pointed between the two units' ``cam`` bones, 9 units up, and plays
``standby`` (``standby2`` at range).

**Shake** (``set_camera_shake_parameters`` / ``update_shake_oscillation``):
a hit shakes every camera sideways, ``amplitude * sin(phase)`` with
amplitude ``1.8 * quake`` falling by ``0.06 * quake`` a tick, phase + 1 a
tick, for 60 ticks.

Which script a strike plays, and which unit slot it follows, is the
timeline's job (:mod:`.timeline`); this module turns those cues into one
:class:`Shot` per tick.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Optional

from ..formats import battle_camera, zdbx
from .staging import number, numbers

FOVY = 30.0  # degrees, gcamera_allocate_and_construct
ASPECT = 4.0 / 3.0
OPENING_RIG = "cam1"
ENTITY_SIDES = {"charaAtk": 0, "charaDef": 1}
SHAKE_SCALE, SHAKE_DECAY, SHAKE_TICKS, SHAKE_SPEED = 1.8, 0.06, 60, 1.0


@dataclass(frozen=True)
class Rig:
    name: str
    dest: tuple = (0.0, 0.0, 0.0)
    offs: tuple = (0.0, 0.0, 0.0)
    rot: tuple = (0.0, 0.0, 0.0)
    dist: float = 0.0
    entities: tuple = ("", "", "")

    @classmethod
    def from_rig(cls, rig: battle_camera.CameraRig) -> "Rig":
        def vec(key):
            text = rig.get(key)
            return (numbers(text) + (0.0, 0.0, 0.0))[:3] if text else (0.0, 0.0, 0.0)

        return cls(rig.name, vec("dest"), vec("offs"), vec("rot"), number(rig.get("dist")),
                   (rig.get("entityName"), rig.get("entityName1"), rig.get("entityName2")))

    def follows(self, slot: int) -> Optional[int]:
        """The side the rig's unit slot ``slot`` names (None: no unit)."""
        return ENTITY_SIDES.get(self.entities[slot] if 0 <= slot < 3 else "")


@dataclass(frozen=True)
class Cue:
    """Start script ``script`` at tick ``frame``; ``slot`` is the unit slot the
    rig follows (0 for the attacker's strikes, 1 for the defender's).
    ``dest``, when given, first moves the rig's look-at point there (the
    opening ``cam1`` shot looks between the units)."""

    frame: int
    script: str
    slot: int = 0
    mirror: bool = False
    dest: Optional[tuple] = None


@dataclass(frozen=True)
class Quake:
    frame: int
    strength: float


@dataclass(frozen=True)
class Shot:
    """The camera at one tick: it looks at ``side``'s ``cam`` bone (or at
    ``dest`` when ``side`` is None) plus ``offs`` and ``shake``."""

    side: Optional[int]
    dest: tuple
    offs: tuple
    pitch: float  # degrees
    yaw: float
    dist: float
    shake: tuple = (0.0, 0.0)

    def eye_center(self, target) -> tuple[tuple, tuple]:
        tx, ty, tz = (float(v) for v in target)
        cx, cy, cz = tx + self.offs[0], ty + self.offs[1], tz + self.offs[2]
        p, y = math.radians(self.pitch), math.radians(self.yaw)
        # Ry(yaw) * Rx(pitch) * (0, 0, -dist)
        ox = -self.dist * math.cos(p) * math.sin(y)
        oy = self.dist * math.sin(p)
        oz = -self.dist * math.cos(p) * math.cos(y)
        sx, sy = self.shake
        return (cx + ox + sx, cy + oy + sy, cz + oz), (cx + sx, cy + sy, cz)


def hermite(p0: float, p1: float, p2: float, p3: float, u: float) -> float:
    """``interpolate_cubic_spline``: from p1 to p2, tangents (p2 - p0) / 2 and (p3 - p1) / 2."""
    return (0.5 * u * u * (u - 1) * (p3 - p1) + 0.5 * u * (1 - u) ** 2 * (p2 - p0)
            + (1 + 2 * u) * (u - 1) ** 2 * p1 + (3 - 2 * u) * u * u * p2)


class Tween:
    """One tweened vector of a camera (``gcamera_init_default_param_block``)."""

    def __init__(self, value):
        self.value = list(value)
        self.p0 = list(value)
        self.p1 = list(value)
        self.target = list(value)
        self.frames = 0
        self.left = 0

    def start(self, target, frames: int) -> None:
        target = list(target)
        if frames <= 0:
            self.p0, self.p1, self.value = list(target), list(target), list(target)
            self.left = 0
        else:
            self.p0, self.p1 = self.p1, list(self.value)
            self.left = frames if self.value != target else 0
        self.target, self.frames = target, max(frames, 0)

    def step(self) -> None:
        if self.left <= 0:
            return
        if self.value == self.target:
            self.left = 0
            return
        self.left -= 1
        if self.left < 1:
            self.left = 0
            self.value = list(self.target)
            return
        u = (self.frames - self.left) / self.frames
        self.value = [hermite(a, b, c, c, u) for a, b, c in zip(self.p0, self.p1, self.target)]


class _RigState:
    def __init__(self, rig: Rig):
        self.rig = rig
        self.offs = Tween(rig.offs)
        self.rot = Tween(rig.rot)
        self.dist = Tween((rig.dist,))
        self.slot = 0
        self.dest = rig.dest
        self.script: Optional[battle_camera.CameraScript] = None
        self.index = -1
        self.mirror = False

    def moving(self) -> bool:
        return bool(self.offs.left or self.rot.left or self.dist.left)

    def start(self, script: battle_camera.CameraScript, slot: int, mirror: bool) -> None:
        self.script, self.index, self.slot, self.mirror = script, 0, slot, mirror

    def advance(self) -> None:
        """``slot_00_FUN_801cb2a4``: hand the next keyframe over once the last one has landed."""
        if self.script is None or self.index < 0:
            return
        if self.index > 0 and self.moving():
            return
        kf = self.script.keyframes[self.index]
        pos, rot = list(kf.pos), list(kf.rot)
        if self.mirror:
            rot[1] = 360.0 - rot[1]
            pos[0] = -pos[0]
        if any(pos):
            self.offs.start(pos, kf.time)
        self.rot.start(rot, kf.time)
        self.dist.start((kf.dist,), kf.time)
        self.index += 1
        if self.index >= len(self.script.keyframes):
            self.index = -1

    def step(self) -> None:
        self.offs.step()
        self.rot.step()
        self.dist.step()


class GameCamera:
    def __init__(self, scripts: dict, rigs: dict):
        self.scripts = scripts  # name -> CameraScript
        self.rigs = rigs  # name -> Rig

    @classmethod
    def from_zdbx(cls, zdbx_data: bytes) -> "GameCamera":
        scripts, rigs = {}, {}
        for entry in zdbx.read_zdbx_archive(zdbx_data) if zdbx_data else ():
            folder, _sep, file = entry.name.partition("/")
            try:
                if folder == "xcam" and file.endswith(".dbx"):
                    scripts[file[:-4]] = battle_camera.read_script(entry.text)
                elif entry.name == "zdbx/camera.dbx":
                    rigs = {r.name: Rig.from_rig(r) for r in battle_camera.read_rigs(entry.text)}
            except Exception:  # noqa: BLE001 - one unreadable script must not lose the rest
                continue
        return cls(scripts, rigs)

    def with_packs(self, packs) -> "GameCamera":
        """A copy that also knows the scripts of these ``cam.cmp`` packs (unreadable ones skipped)."""
        scripts = dict(self.scripts)
        for data in packs:
            try:
                scripts.update((s.name, s) for s in battle_camera.read_script_pack(data) if s.name)
            except Exception:  # noqa: BLE001 - a damaged pack must not lose the rest
                continue
        return GameCamera(scripts, self.rigs)

    def track(self, cues: list, quakes: list, length: int) -> list:
        """One :class:`Shot` per tick, ``0 .. length`` (cues for missing scripts are skipped)."""
        states = {name: _RigState(rig) for name, rig in self.rigs.items()}
        active = states.get(OPENING_RIG) or (next(iter(states.values())) if states else _RigState(Rig("none")))
        by_frame: dict = {}
        for cue in cues:
            by_frame.setdefault(int(cue.frame), []).append(cue)
        shakes = {int(q.frame): q.strength for q in quakes}
        amp, decay, phase, left = 0.0, 0.0, 0.0, 0
        shake_x = 0.0
        shots = []
        for tick in range(int(length) + 1):
            for cue in by_frame.get(tick, ()):
                script = self.scripts.get(cue.script)
                state = states.get(script.camera) if script is not None else None
                if state is None or not script.keyframes:
                    continue
                for other in states.values():
                    if other.script is not None and other is not state:
                        other.index = -1
                if cue.dest is not None:
                    state.dest = tuple(cue.dest)
                state.start(script, cue.slot, cue.mirror)
                active = state
            if tick in shakes:
                amp, decay, phase, left = SHAKE_SCALE * shakes[tick], -SHAKE_DECAY * shakes[tick], 0.0, SHAKE_TICKS
            active.advance()
            for state in states.values():
                state.step()
            if left > 0:
                shake_x = amp * math.sin(phase)
                phase += SHAKE_SPEED
                amp = max(amp + decay, 0.0)
                left -= 1
            rig = active.rig
            rot = active.rot.value
            shots.append(Shot(rig.follows(active.slot), active.dest, tuple(active.offs.value),
                              rot[0], rot[1], active.dist.value[0], (shake_x, 0.0)))
        return shots


def look_at(eye, center) -> "list[list[float]]":
    """The view rotation of ``gcamera_set_basis_from_points`` (up +Y): rows are
    the screen's right, up and forward (into the screen) directions."""
    f = [c - e for c, e in zip(center, eye)]
    n = math.sqrt(sum(v * v for v in f)) or 1.0
    f = [v / n for v in f]
    right = [-f[2], 0.0, f[0]]  # f x up
    n = math.sqrt(sum(v * v for v in right)) or 1.0
    right = [v / n for v in right]
    up = [right[1] * f[2] - right[2] * f[1], right[2] * f[0] - right[0] * f[2], right[0] * f[1] - right[1] * f[0]]
    return [right, up, f]


__all__ = ["ASPECT", "Cue", "FOVY", "GameCamera", "Quake", "Rig", "Shot", "hermite", "look_at"]
