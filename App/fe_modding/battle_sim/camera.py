"""The game camera of a simulated fight, from the ``xcam/`` scripts.

Each strike picks the script named after its action and side, as the vanilla
names suggest: ``crit_l`` / ``atk_l`` for the left unit (the attacker, as in
``battle.dbx``), ``crit_r`` / ``atk_r`` for the right one, then any
``atk*`` script. A script moves one rig of ``zdbx/camera.dbx`` through
keyframes of ``pos``, ``rot`` and ``dist``; ``time`` is the duration to
reach a keyframe (0 = cut). The rig's ``entityName`` (``charaAtk`` /
``charaDef``) says which unit it follows.

**Not measured**, so labelled approximate in the simulator: the unit of
``time`` (taken as frames, times :attr:`GameCamera.time_scale`), and how
``pos`` / ``rot`` / ``dist`` combine. They are read as an orbit, like the
``cam1`` rig: the camera looks at the followed unit's ``_cam_`` bone plus
the rig's ``offs`` plus ``pos``, from ``dist`` away, turned by ``rot``
(degrees: x tilts the camera down, y turns it about the fighters, 180 being
the side view with the left unit on the left).

The scale of ``dist`` / ``pos`` against the battle models is not measured
either, so the stage scales them: :meth:`GameCamera.reference_dist` (the
first ``atk_l`` keyframe's ``dist``) is mapped to the distance that frames
both units, which keeps each script's push-ins and pull-backs.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from ..formats import battle_camera, zdbx


@dataclass(frozen=True)
class View:
    follow: Optional[int]  # side the camera looks at (None: between the units)
    offset: tuple  # added to the look-at point (keyframe pos + the rig's offs), in game units
    rot: tuple  # degrees: pitch, yaw, roll
    dist: float


def _lerp(a, b, u: float):
    return tuple(x + (y - x) * u for x, y in zip(a, b))


def sample(script: battle_camera.CameraScript, t: float) -> Optional[tuple]:
    """``(pos, rot, dist)`` ``t`` time units into ``script``."""
    frames = script.keyframes
    if not frames:
        return None
    cur, elapsed = frames[0], 0.0
    for kf in frames[1:]:
        if kf.time <= 0:
            cur = kf
            continue
        if t < elapsed + kf.time:
            u = (t - elapsed) / kf.time
            return _lerp(cur.pos, kf.pos, u), _lerp(cur.rot, kf.rot, u), cur.dist + (kf.dist - cur.dist) * u
        elapsed += kf.time
        cur = kf
    return cur.pos, cur.rot, cur.dist


def choose_script(scripts: dict, side: int, crit: bool) -> Optional[battle_camera.CameraScript]:
    suffix = "lr"[side]
    names = ([f"crit_{suffix}"] if crit else []) + [f"atk_{suffix}"]
    for name in names:
        if name in scripts:
            return scripts[name]
    return next((scripts[n] for n in sorted(scripts) if n.startswith("atk")), None)


class GameCamera:
    def __init__(self, scripts: dict, rigs: dict, time_scale: float = 1.0):
        self.scripts = scripts  # name -> CameraScript
        self.rigs = rigs  # name -> CameraRig
        self.time_scale = time_scale

    @classmethod
    def from_zdbx(cls, zdbx_data: bytes) -> "GameCamera":
        scripts, rigs = {}, {}
        for entry in zdbx.read_zdbx_archive(zdbx_data) if zdbx_data else ():
            folder, _sep, file = entry.name.partition("/")
            try:
                if folder == "xcam" and file.endswith(".dbx"):
                    scripts[file[:-4]] = battle_camera.read_script(entry.text)
                elif entry.name == "zdbx/camera.dbx":
                    rigs = {r.name: r for r in battle_camera.read_rigs(entry.text)}
            except Exception:  # noqa: BLE001 - one unreadable script must not lose the rest
                continue
        return cls(scripts, rigs)

    def reference_dist(self) -> Optional[float]:
        """The first ``atk_l`` keyframe's ``dist`` (else any attack script's): the normal framing."""
        script = choose_script(self.scripts, 0, False)
        if script is None or not script.keyframes:
            return None
        dist = script.keyframes[0].dist
        return dist if dist > 0 else None

    def _rig_offset(self, script: battle_camera.CameraScript) -> tuple:
        rig = self.rigs.get(script.camera)
        offs = battle_camera.parse_vec(rig.get("offs")) if rig is not None else None
        return offs or (0.0, 0.0, 0.0)

    def _follow(self, script: battle_camera.CameraScript, striker: int) -> Optional[int]:
        rig = self.rigs.get(script.camera)
        entity = rig.get("entityName") if rig is not None else ""
        if entity == "charaAtk":
            return striker
        if entity == "charaDef":
            return 1 - striker
        return None

    def view(self, shots: list, t: float) -> Optional[View]:
        """The camera at frame ``t``; ``shots`` are ``(start frame, striker side, crit)``."""
        current = None
        for shot in shots:
            if shot[0] <= t:
                current = shot
        if current is None and shots:
            current = shots[0]
        if current is None:
            return None
        start, side, crit = current
        script = choose_script(self.scripts, side, crit)
        if script is None:
            return None
        values = sample(script, max(t - start, 0.0) / max(self.time_scale, 1e-6))
        if values is None:
            return None
        pos, rot, dist = values
        offset = tuple(p + o for p, o in zip(pos, self._rig_offset(script)))
        return View(self._follow(script, side), offset, rot, dist)
