"""Radiant Dawn's loose ``xcam`` clip and FE10Battle dispatch camera.

Unlike Path of Radiance's DBX keyframe cameras, RD animates a two-bone
camera rig.  FE10BCamList selects a weighted FE10BCamFile for the current
weapon context and battle motion; the chosen loose ``.ga`` poses
``locator1`` (look-at point) and its child ``camera1`` (eye) each tick.
"""

from __future__ import annotations

import math
from pathlib import Path

from ..formats import animation, engine_pose, skeleton
from .camera import SHAKE_DECAY, SHAKE_SCALE, SHAKE_SPEED, Shot


_CUE_MOTIONS = {
    "standby": 0, "standby2": 0,
    "atk_l": 2, "atk_r": 2, "atk2_l": 3, "atk2_r": 3,
    "mag_at_l": 2, "mag_at_r": 2, "bow_at_l": 2, "bow_at_r": 2,
    "crit_l": 6, "crit_r": 6, "crit2_l": 7, "crit2_r": 7,
    "mag_cr_l": 6, "mag_cr_r": 6, "bow_cr_l": 6, "bow_cr_r": 6,
    "skill_l": 10, "skill_r": 10, "ded_l": 29, "ded_r": 29,
}


class Fe10GameCamera:
    """The same ``scripts``/``track`` boundary consumed by BattleStage."""

    def __init__(self, folder: Path, battle, *, distance: int = 1, units=()):
        self.folder = Path(folder)
        self.battle = battle
        self.distance = int(distance)
        self.units = tuple(units)
        self._files = tuple(dict(row.strings).get(4, "")
                            for row in battle.table("FE10BCamFile").records)
        loose = {path.stem: path for path in self.folder.glob("*.ga")}
        self._paths = loose
        # Timeline only tests membership.  Values intentionally are paths,
        # not FE9 CameraScript objects.
        self.scripts = {name: loose.get(name) for name in {*loose, *_CUE_MOTIONS}}
        self.rigs = {}
        self._bones = skeleton.read_skeleton_path(self.folder / "cam.g")
        names = {bone.name: index for index, bone in enumerate(self._bones)}
        self._center_bone = names.get("locator1", 0)
        self._eye_bone = names.get("camera1", min(1, len(self._bones) - 1))
        self._clips = {}

    def _context(self, side: int) -> int:
        prefix = getattr(self.units[side], "prefix", "no") if side < len(self.units) else "no"
        try:
            return self.battle.camera_context_names.index(prefix)
        except ValueError:
            return 0

    def _registered_name(self, cue) -> str | None:
        # An explicitly named loose clip (including a clip animation's own
        # camera) bypasses table dispatch.
        if cue.script in self._paths:
            return cue.script
        motion = _CUE_MOTIONS.get(cue.script)
        if motion is None:
            if cue.script.startswith("arc"):
                motion = 10
            elif "crit" in cue.script or "_cr" in cue.script:
                motion = 6
            elif "atk" in cue.script:
                motion = 2
            else:
                motion = 0
        list_index = 1 if self.distance > 1 and len(self.battle.camera_lists) > 1 else 0
        camera_list = self.battle.camera_lists[list_index]
        context = self._context(int(cue.slot))
        group_index = camera_list.group_indices[context][min(motion, len(camera_list.group_indices[context]) - 1)]
        if group_index is None:
            return "focus_f" if self.distance > 1 else "focus_n"
        choices = self.battle.camera_groups[group_index].choices
        if not choices:
            return None
        total = sum(max(choice.selection_weight, 0) for choice in choices)
        if total:
            pick = (int(cue.frame) * 17 + int(cue.slot) * 31 + motion * 13) % total
            selected = choices[-1]
            for choice in choices:
                pick -= max(choice.selection_weight, 0)
                if pick < 0:
                    selected = choice
                    break
        else:
            selected = choices[0]
        return self._files[selected.file_index]

    def _clip(self, name: str | None):
        if not name:
            return None
        if name not in self._clips:
            path = self._paths.get(name)
            try:
                self._clips[name] = animation.read_animation_path(path) if path else None
            except (OSError, ValueError):
                self._clips[name] = None
        return self._clips[name]

    @staticmethod
    def _shot(eye, center, *, mirror: bool, shake: float = 0.0) -> Shot:
        eye, center = [list(map(float, point)) for point in (eye, center)]
        if mirror:
            eye[0], center[0] = -eye[0], -center[0]
        dx, dy, dz = eye[0] - center[0], eye[1] - center[1], eye[2] - center[2]
        distance = math.sqrt(dx * dx + dy * dy + dz * dz) or 1.0
        pitch = math.degrees(math.asin(max(-1.0, min(1.0, dy / distance))))
        yaw = math.degrees(math.atan2(-dx, -dz))
        return Shot(None, tuple(center), (0.0, 0.0, 0.0), pitch, yaw, distance, (shake, 0.0))

    def _pose(self, clip, frame: float, mirror: bool, shake: float) -> Shot:
        world, _palette = engine_pose.pose(self._bones, clip, frame)
        center = tuple(world[self._center_bone][row][3] for row in range(3))
        eye = tuple(world[self._eye_bone][row][3] for row in range(3))
        return self._shot(eye, center, mirror=mirror, shake=shake)

    def track(self, cues: list, quakes: list, length: int) -> list[Shot]:
        """Select and pose one registered RD camera clip per battle tick."""
        by_frame = {}
        for cue in cues:
            by_frame.setdefault(int(cue.frame), []).append(cue)
        shakes = {}
        for quake in quakes:
            shakes.setdefault(int(quake.frame), []).append(quake)
        active = None
        started = 0
        mirror = False
        amp = decay = phase = shake_x = 0.0
        left = 0
        shots = []
        fallback_eye = (24.0, 9.0, 29.0 if self.distance <= 1 else 38.0)
        fallback_center = (0.0, 5.0, 0.0)
        for tick in range(int(length) + 1):
            for cue in by_frame.get(tick, ()):
                selected = self._clip(self._registered_name(cue))
                if selected is not None:
                    active, started = selected, tick
                    mirror = bool(cue.mirror or int(cue.slot) == 1)
            for quake in shakes.get(tick, ()):
                if quake.duration == 0 or quake.strength <= 0:
                    amp = decay = phase = shake_x = 0.0
                    left = 0
                else:
                    amp = SHAKE_SCALE * quake.strength
                    decay = 0.0 if quake.duration < 0 else -SHAKE_DECAY * quake.strength
                    left = int(length) - tick + 1 if quake.duration < 0 else quake.duration
                    phase = 0.0
            if left > 0:
                shake_x = amp * math.sin(phase)
                phase += SHAKE_SPEED
                amp = max(amp + decay, 0.0)
                left -= 1
            else:
                shake_x = 0.0
            if active is None:
                shots.append(self._shot(fallback_eye, fallback_center, mirror=False, shake=shake_x))
            else:
                frame = min(max(tick - started, 0), max(active.length_in_frames, 0))
                shots.append(self._pose(active, frame, mirror, shake_x))
        return shots


__all__ = ["Fe10GameCamera"]
