"""The battle simulator's 3D stage: the scenery, both units and their weapons
in one scene, posed frame by frame from a :mod:`fe_modding.battle_sim.timeline`.

Loading reuses the 3D model viewer's readers (``_set_contents``,
``_build_loaded_set``, ``_load_model_set``), so models, textures and
animations come out exactly as the viewer shows them, and the scene is drawn
by its ``_ModelCanvas`` (GPU when available, else the numpy rasterizer).

What is new here:

- :class:`SkinnedMesh` skins a whole mesh with numpy, the same maths as
  ``model_viewer._skin_triangles`` (each vertex through its bones'
  ``engine_pose`` matrices: the skin palette for multi-matrix shapes, the
  world matrix for single-matrix ones), fast enough for two units at once.
- Weapons are posed at rest and carried by the unit's ``_r_hand_`` bone
  (``_l_hand_`` for bows), the anchors :mod:`fe_modding.rig_contract` lists.
- Placement is the simulator's own: the attacker at ``-spacing / 2`` and the
  defender at ``+spacing / 2`` on the Z axis, turned to face each other. The
  engine's spacing (``間合い``) and the models' facing axis are not measured,
  so both are adjustable.
"""

from __future__ import annotations

import math
import tkinter as tk
from dataclasses import dataclass, field
from pathlib import Path
from tkinter import ttk
from typing import Optional

import numpy as np

from ..battle_sim import scene_assets as sa
from ..battle_sim import timeline as tlm
from ..formats import animation, engine_pose
from .model_viewer import (
    _build_loaded_set,
    _LoadedSet,
    _load_model_set,
    _ModelCanvas,
    _set_contents,
    _Triangle,
)

SIDE_NAMES = ("Attacker", "Defender")
HAND_BONES = ("_r_hand_", "_l_hand_")
BOW_KIND = 3  # battle_weapons.KINDS


class SkinnedMesh:
    """A triangle list skinned with numpy (see the module docstring)."""

    def __init__(self, triangles: list[_Triangle]):
        self.triangles = triangles
        n = len(triangles)
        self.positions = np.array([(t.a, t.b, t.c) for t in triangles], dtype=np.float64).reshape(n, 3, 3)
        self.normals = np.array([t.normal for t in triangles], dtype=np.float64).reshape(n, 3)
        k = max((len(s.bone_indices) for t in triangles if t.skin for s in t.skin), default=0)
        self.k = max(k, 1)
        self.indices = np.full((n, 3, self.k), -1, dtype=np.int64)
        self.weights = np.zeros((n, 3, self.k), dtype=np.float64)
        self.palette = np.zeros((n, 3), dtype=np.int64)
        for i, t in enumerate(triangles):
            if t.skin is None:
                continue
            for v, s in enumerate(t.skin):
                total = sum(s.bone_weights) or 1.0
                count = len(s.bone_indices)
                self.indices[i, v, :count] = s.bone_indices
                self.weights[i, v, :count] = [w / total for w in s.bone_weights]
                self.palette[i, v] = 1 if s.uses_palette else 0

    def pose(self, world, palette) -> tuple[np.ndarray, np.ndarray]:
        """Posed ``(positions (n, 3, 3), normals (n, 3))``."""
        bones = len(world)
        if bones == 0 or not len(self.triangles):
            return self.positions, self.normals
        mats = np.stack([np.asarray(world, dtype=np.float64), np.asarray(palette, dtype=np.float64)])
        valid = (self.indices >= 0) & (self.indices < bones)
        safe = np.where(valid, self.indices, 0)
        m = mats[self.palette[..., None], safe]  # (n, 3, k, 3, 4)
        q = np.einsum("nvkij,nvj->nvki", m[..., :3], self.positions) + m[..., 3]
        w = self.weights * valid
        out = np.einsum("nvki,nvk->nvi", q, w)
        used = valid.any(axis=-1)
        out = np.where(used[..., None], out, self.positions)
        d = np.einsum("nkij,nj->nki", m[:, 0, :, :, :3], self.normals)
        dn = np.einsum("nki,nk->ni", d, w[:, 0])
        length = np.linalg.norm(dn, axis=-1, keepdims=True)
        dn = np.where(length > 1e-9, dn / np.maximum(length, 1e-12), dn)
        normals = np.where(used[:, :1], dn, self.normals)
        return out, normals


def _transform(matrix: np.ndarray, positions: np.ndarray, normals: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    rot, move = matrix[:, :3], matrix[:, 3]
    return positions @ rot.T + move, normals @ rot.T


def _compose(outer: np.ndarray, inner) -> np.ndarray:
    inner = np.asarray(inner, dtype=np.float64)
    out = np.zeros((3, 4))
    out[:, :3] = outer[:, :3] @ inner[:, :3]
    out[:, 3] = outer[:, :3] @ inner[:, 3] + outer[:, 3]
    return out


def placement(z: float, yaw_degrees: float) -> np.ndarray:
    a = math.radians(yaw_degrees)
    c, s = math.cos(a), math.sin(a)
    return np.array([[c, 0, s, 0], [0, 1, 0, 0], [-s, 0, c, z]], dtype=np.float64)


def _rebuild(triangles: list[_Triangle], positions: np.ndarray, normals: np.ndarray) -> list[_Triangle]:
    out = []
    for t, p, nrm in zip(triangles, positions.tolist(), normals.tolist()):
        out.append(_Triangle(tuple(p[0]), tuple(p[1]), tuple(p[2]), tuple(nrm), t.color, t.skin, t.uv, t.texture,
                             t.texture_layers, t.alpha, t.blend_mode))
    return out


@dataclass
class StageUnit:
    assets: sa.UnitAssets
    loaded: Optional[_LoadedSet] = None
    mesh: Optional[SkinnedMesh] = None
    clips: dict = field(default_factory=dict)  # stem -> GaAnimation
    weapon: Optional[_LoadedSet] = None
    weapon_positions: Optional[np.ndarray] = None
    weapon_normals: Optional[np.ndarray] = None
    hand: Optional[int] = None
    height: float = 1.0

    def clip(self, role: str) -> Optional[tlm.Clip]:
        stem = self.assets.roles.get(role)
        anim = self.clips.get(stem) if stem else None
        if anim is None:
            return None
        impact = next((e.frame for e in anim.events if 0 in e.codes), None)
        swing = next((e.frame for e in anim.events if 1 in e.codes), None)
        return tlm.Clip(stem, float(max(anim.length_in_frames, 1)), impact, swing)


class SetCache:
    """Loaded model sets, by pack and texture (loading a battle set reads every weapon pack)."""

    def __init__(self, size: int = 8):
        self._items: dict = {}
        self._size = size

    def get(self, key, load):
        if key in self._items:
            value = self._items.pop(key)
        else:
            value = load()
        self._items[key] = value
        while len(self._items) > self._size:
            self._items.pop(next(iter(self._items)))
        return value


def load_unit(cache: SetCache, assets: sa.UnitAssets) -> StageUnit:
    unit = StageUnit(assets)
    if assets.pack is not None:
        def load():
            files, anims = _set_contents(assets.pack)
            if assets.texture is not None:
                files = {n: d for n, d in files.items() if not n.lower().endswith(".tpl")}
                files[assets.texture.name] = assets.texture.read_bytes()
            loaded = _build_loaded_set(assets.code or assets.pack.stem, files, anims)
            clips = {}
            for name, data in loaded.animations:
                try:
                    clips[Path(name).stem] = animation.read_animation_bytes(data)
                except Exception:  # noqa: BLE001 - one bad clip must not stop the stage
                    continue
            return loaded, SkinnedMesh(loaded.triangles), clips

        unit.loaded, unit.mesh, unit.clips = cache.get(("unit", assets.pack, assets.texture), load)
        ys = unit.mesh.positions[..., 1] if len(unit.loaded.triangles) else np.zeros(1)
        unit.height = max(float(ys.max() - ys.min()), 1e-3)
        names = [b.name for b in unit.loaded.bones]
        wanted = HAND_BONES[1] if assets.weapon_kind == BOW_KIND else HAND_BONES[0]
        unit.hand = names.index(wanted) if wanted in names else (
            names.index(HAND_BONES[0]) if HAND_BONES[0] in names else None)
    if assets.weapon_model is not None:
        def load_weapon():
            loaded = _load_model_set(assets.weapon_model.parent.name, assets.weapon_model)
            mesh = SkinnedMesh(loaded.triangles)
            world, palette = engine_pose.pose(loaded.bones) if loaded.bones else ([], [])
            positions, normals = mesh.pose(world, palette)
            return loaded, positions, normals

        unit.weapon, unit.weapon_positions, unit.weapon_normals = cache.get(("weapon", assets.weapon_model), load_weapon)
    return unit


def load_scenery(path: Path) -> _LoadedSet:
    """A ``zbg/<name>/`` pack, as the 3D model viewer loads it."""
    return _load_model_set(path.parent.name, path)


class BattleStage:
    """Scenery plus two :class:`StageUnit` s; :meth:`frame` gives the scene's triangles at a time."""

    def __init__(self, units: list[StageUnit], scenery: Optional[_LoadedSet] = None):
        self.units = units
        self.scenery = scenery.triangles if scenery is not None else []
        self.spacing = 1.2 * max(u.height for u in units) if units else 1.0
        self.facing = 0.0
        self.timeline: Optional[tlm.Timeline] = None

    def lookup(self, side: int, role: str) -> Optional[tlm.Clip]:
        return self.units[side].clip(role)

    def set_log(self, log, distance: int = 1) -> None:
        self.timeline = tlm.build(log, self.lookup, distance=distance)

    def _placements(self) -> list[np.ndarray]:
        half = self.spacing / 2
        return [placement(-half, self.facing), placement(half, self.facing + 180.0)]

    def frame(self, t: float) -> list[_Triangle]:
        tris = list(self.scenery)
        for side, (unit, place) in enumerate(zip(self.units, self._placements())):
            if unit.loaded is None:
                continue
            stem, frame = self.timeline.pose(side, t) if self.timeline is not None else (None, 0.0)
            anim = unit.clips.get(stem) if stem else None
            world, palette = engine_pose.pose(unit.loaded.bones, anim, frame) if unit.loaded.bones else ([], [])
            positions, normals = unit.mesh.pose(world, palette)
            tris += _rebuild(unit.loaded.triangles, *_transform(place, positions, normals))
            if unit.weapon is not None and unit.hand is not None and world:
                hand = _compose(place, world[unit.hand])
                tris += _rebuild(unit.weapon.triangles, *_transform(hand, unit.weapon_positions, unit.weapon_normals))
        return tris


class StageView(ttk.Frame):
    """Canvas, HP bars and playback controls for a :class:`BattleStage`."""

    def __init__(self, parent: tk.Misc):
        super().__init__(parent)
        self.stage: Optional[BattleStage] = None
        self._t = 0.0
        self._playing = False
        self._after = None
        self._max_hp = (1, 1)
        self.speed = tk.StringVar(value="1x")

        bars = ttk.Frame(self)
        bars.pack(fill="x")
        self._hp_labels, self._hp_bars = [], []
        for side in (0, 1):
            box = ttk.Frame(bars)
            box.pack(side="left", fill="x", expand=True, padx=4)
            label = ttk.Label(box, text=SIDE_NAMES[side])
            label.pack(anchor="w")
            bar = ttk.Progressbar(box, maximum=1, value=1)
            bar.pack(fill="x")
            self._hp_labels.append(label)
            self._hp_bars.append(bar)
        self._popup = ttk.Label(self, text="", style="Title.TLabel", anchor="center")
        self._popup.pack(fill="x")

        self.canvas = _ModelCanvas(self)
        self.canvas.set_show_skeleton(False)
        self.canvas.configure(height=360)
        self.canvas.pack(fill="both", expand=True)

        controls = ttk.Frame(self)
        controls.pack(fill="x", pady=(4, 0))
        self._play_button = ttk.Button(controls, text="Play", command=self.toggle, width=7)
        self._play_button.pack(side="left")
        ttk.Button(controls, text="Restart", command=self.restart).pack(side="left", padx=(4, 0))
        speed = ttk.Combobox(controls, textvariable=self.speed, values=("0.25x", "0.5x", "1x", "2x"), width=6,
                             state="readonly")
        speed.pack(side="left", padx=(8, 0))
        self._scale = ttk.Scale(controls, from_=0, to=1, command=self._scrub)
        self._scale.pack(side="left", fill="x", expand=True, padx=(8, 0))
        self._time = ttk.Label(controls, text="", width=12)
        self._time.pack(side="left", padx=(6, 0))

    def set_stage(self, stage: Optional[BattleStage], names: tuple = SIDE_NAMES, max_hp: tuple = (1, 1)) -> None:
        self.stop()
        self.stage = stage
        self._max_hp = max_hp
        for side in (0, 1):
            self._hp_labels[side].configure(text=names[side])
        if stage is None or stage.timeline is None:
            self.canvas.set_model([], {}, {}, {})
            return
        self._scale.configure(to=stage.timeline.length)
        self._t = 0.0
        self.canvas.set_model(stage.frame(0.0), {}, {}, {})
        self._show(0.0)

    def refresh(self) -> None:
        """Redraw the current frame (after the timeline or the placement changed)."""
        if self.stage is not None and self.stage.timeline is not None:
            self._scale.configure(to=self.stage.timeline.length)
            self._t = min(self._t, self.stage.timeline.length)
            self._show(self._t)

    def _show(self, t: float) -> None:
        stage = self.stage
        if stage is None or stage.timeline is None:
            return
        self.canvas.set_pose(None, stage.frame(t))
        hp = stage.timeline.hp(t)
        for side in (0, 1):
            maximum = max(self._max_hp[side], stage.timeline.hp_start[side], 1)
            self._hp_bars[side].configure(maximum=maximum, value=max(hp[side], 0))
        popup = stage.timeline.popup(t)
        self._popup.configure(text=f"{SIDE_NAMES[popup.side]}: {popup.text}" if popup else "")
        self._time.configure(text=f"{t / tlm.FPS:5.1f} s")

    def _scrub(self, value) -> None:
        if self._playing:
            return
        self._t = float(value)
        self._show(self._t)

    def toggle(self) -> None:
        if self._playing:
            self.stop()
        elif self.stage is not None and self.stage.timeline is not None:
            if self._t >= self.stage.timeline.length:
                self._t = 0.0
            self._playing = True
            self._play_button.configure(text="Pause")
            self._tick()

    def restart(self) -> None:
        self._t = 0.0
        self._scale.set(0)
        self._show(0.0)

    def stop(self) -> None:
        self._playing = False
        if self._after is not None:
            self.after_cancel(self._after)
            self._after = None
        self._play_button.configure(text="Play")

    def _tick(self) -> None:
        if not self._playing or self.stage is None or self.stage.timeline is None:
            return
        step = float(self.speed.get().rstrip("x") or 1)
        self._t += step
        if self._t >= self.stage.timeline.length:
            self._t = self.stage.timeline.length
            self._scale.set(self._t)
            self._show(self._t)
            self.stop()
            return
        self._scale.set(self._t)
        self._show(self._t)
        self._after = self.after(1000 // tlm.FPS, self._tick)

    def cleanup(self) -> None:
        self.stop()
