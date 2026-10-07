"""The battle scene: the scenery, both units and their weapons, posed tick by
tick from a :mod:`fe_modding.battle_sim.timeline` and filmed by the game's
battle camera (:mod:`fe_modding.battle_sim.camera`).

Loading reuses the 3D model viewer's readers (``_set_contents``,
``_build_loaded_set``, ``_load_model_set``), so models, textures and
animations come out exactly as the viewer shows them, and the scene is drawn
by its ``_ModelCanvas`` (GPU when available, else the numpy rasterizer).

- :class:`SkinnedMesh` skins a whole mesh with numpy, the same maths as
  ``model_viewer._skin_triangles``.
- Units stand where the engine puts them (:mod:`fe_modding.battle_sim.staging`):
  the attacker at ``InitPosL`` turned +90 degrees about Y, the defender at
  ``InitPosR`` turned -90, both moving along X as the timeline runs them in.
- Weapons are carried by the unit's ``_r_hand_`` bone (``_l_hand_`` for
  bows). Missiles fly from the striker's hand to the target's ``_cam_``
  bone: the thrown weapon, or a plain stand-in arrow (no arrow model is
  decoded).
- The backdrop (``zbg/<name>/bf.cmp``) is placed as the engine places a
  battle map's models (:mod:`fe_modding.formats.battle_terrain`).
- Effects (``yme/EID_*.cmp``: hit sparks, miss and no-damage marks, spells,
  skills, death, dust) play where the timeline spawns them: on the ground
  at the unit's spot, turned as the unit is, and stay there while they play.
- The scene's triangles are laid out once (:meth:`BattleStage.triangles`);
  each frame only their posed positions change (:meth:`BattleStage.arrays`),
  which the canvas takes without building triangle objects. Hidden parts
  (an effect not playing, a missile not flying) collapse to a point.

:class:`StageView` plays it in real time: the frame shown is the one the
wall clock has reached, so a slow frame is skipped over, not slowed down.
"""

from __future__ import annotations

import math
import struct
import time
import tkinter as tk
from dataclasses import dataclass, field
from pathlib import Path
from tkinter import ttk
from typing import Optional

import numpy as np

from ..battle_sim import camera as cam
from ..battle_sim import scene_assets as sa
from ..battle_sim import timeline as tlm
from ..battle_sim.staging import FACING, BattleParams, UnitParams
from ..formats import animation, battle_terrain, engine_pose
from .model_viewer import (
    _build_loaded_set,
    _LoadedSet,
    _load_model_set,
    _ModelCanvas,
    _set_contents,
    _Triangle,
    posed_triangles,
)

SIDE_NAMES = ("Attacker", "Defender")
HAND_BONES = ("_r_hand_", "_l_hand_")
BOW_KIND = 3  # battle_weapons.KINDS


class SkinnedMesh:
    """A triangle list skinned with numpy (see the module docstring).

    Triangle corners that share a position and skin are skinned once: each
    distinct vertex gets its blended bone matrix (``sum(weight * matrix)``),
    which moves the vertex and turns the normals of the triangles it starts."""

    def __init__(self, triangles: list[_Triangle], *, exact_faces: bool = False):
        self.triangles = triangles
        self.exact_faces = exact_faces  # posed normals = the posed faces' own (bending characters)
        n = len(triangles)
        self.positions = np.array([(t.a, t.b, t.c) for t in triangles], dtype=np.float64).reshape(n, 3, 3)
        self.normals = np.array([t.normal for t in triangles], dtype=np.float64).reshape(n, 3)
        k = max((len(s.bone_indices) for t in triangles if t.skin for s in t.skin), default=0)
        self.k = max(k, 1)
        keys: dict = {}
        corners = np.zeros((n, 3), dtype=np.int64)
        vertices, indices, weights, palette = [], [], [], []
        for i, t in enumerate(triangles):
            for v, point in enumerate((t.a, t.b, t.c)):
                s = t.skin[v] if t.skin is not None else None
                key = (tuple(point), (s.bone_indices, s.bone_weights, s.uses_palette) if s is not None else None)
                index = keys.get(key)
                if index is None:
                    index = keys[key] = len(vertices)
                    vertices.append(point)
                    row_i, row_w = [-1] * self.k, [0.0] * self.k
                    if s is not None:
                        total = sum(s.bone_weights) or 1.0
                        row_i[:len(s.bone_indices)] = s.bone_indices
                        row_w[:len(s.bone_indices)] = [w / total for w in s.bone_weights]
                    indices.append(row_i)
                    weights.append(row_w)
                    palette.append(1 if s is not None and s.uses_palette else 0)
                corners[i, v] = index
        self.corners = corners
        self.vertices = np.array(vertices, dtype=np.float64).reshape(-1, 3)
        # which way each triangle's corners wind relative to its stored normal, measured at rest:
        # posed normals are then the posed face's own (exact, so culling agrees on all corners)
        rest = _face_normals(self.positions)
        self.winding = np.where((rest * self.normals).sum(axis=1) < 0.0, -1.0, 1.0)[:, None]
        self.indices = np.array(indices, dtype=np.int64).reshape(-1, self.k)
        self.weights = np.array(weights, dtype=np.float64).reshape(-1, self.k)
        self.palette = np.array(palette, dtype=np.int64)

    def pose(self, world, palette, place: Optional[np.ndarray] = None) -> tuple[np.ndarray, np.ndarray]:
        """Posed ``(positions (n, 3, 3), normals (n, 3))``, moved by the 3x4 ``place`` when given
        (folded into the bone matrices, so the mesh is only walked once)."""
        bones = len(world)
        if bones == 0 or not len(self.triangles):
            return (self.positions, self.normals) if place is None else _transform(place, self.positions,
                                                                                  self.normals)
        mats = np.stack([np.asarray(world, dtype=np.float64), np.asarray(palette, dtype=np.float64)])
        if place is not None:
            mats = _compose_all(place, mats)
        valid = (self.indices >= 0) & (self.indices < bones)
        safe = np.where(valid, self.indices, 0)
        m = mats[self.palette[:, None], safe]  # (v, k, 3, 4)
        blended = np.einsum("vk,vkij->vij", self.weights * valid, m)
        moved = np.einsum("vij,vj->vi", blended[..., :3], self.vertices) + blended[..., 3]
        used = valid.any(axis=-1)
        rest, rest_normals = self.vertices, self.normals
        if place is not None and not used.all():
            rest = self.vertices @ place[:, :3].T + place[:, 3]
            rest_normals = self.normals @ place[:, :3].T
        moved = np.where(used[:, None], moved, rest)
        out = moved[self.corners]
        first = self.corners[:, 0]
        dn = np.einsum("nij,nj->ni", blended[first, :, :3], self.normals)
        length = np.linalg.norm(dn, axis=-1, keepdims=True)
        dn = np.where(length > 1e-9, dn / np.maximum(length, 1e-12), dn)
        normals = np.where(used[first][:, None], dn, rest_normals)
        # the face normal of the posed corners, turned the way the stored normal faced at rest
        # (a skinned normal follows only its first corner's bones, so bent cloth would face away)
        if self.exact_faces:
            face = _face_normals(out) * self.winding
            normals = np.where((np.abs(face).sum(axis=1) > 0.0)[:, None], face, normals)
        return out, normals


def _face_normals(positions: np.ndarray) -> np.ndarray:
    """Unit normals of triangles (n, 3, 3) from their corners (0 for degenerate ones)."""
    cross = np.cross(positions[:, 1] - positions[:, 0], positions[:, 2] - positions[:, 0])
    length = np.linalg.norm(cross, axis=1, keepdims=True)
    return np.where(length > 1e-12, cross / np.maximum(length, 1e-12), 0.0)


def _transform(matrix: np.ndarray, positions: np.ndarray, normals: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    rot, move = matrix[:, :3], matrix[:, 3]
    return positions @ rot.T + move, normals @ rot.T


def _compose_all(outer: np.ndarray, inner) -> np.ndarray:
    """``outer`` (3x4) applied after every 3x4 matrix of ``inner`` (..., 3, 4) at once."""
    inner = np.asarray(inner, dtype=np.float64)
    out = np.empty(inner.shape)
    out[..., :3] = np.einsum("ij,...jk->...ik", outer[:, :3], inner[..., :3])
    out[..., 3] = np.einsum("ij,...j->...i", outer[:, :3], inner[..., 3]) + outer[:, 3]
    return out


def _compose(outer: np.ndarray, inner) -> np.ndarray:
    inner = np.asarray(inner, dtype=np.float64)
    out = np.zeros((3, 4))
    out[:, :3] = outer[:, :3] @ inner[:, :3]
    out[:, 3] = outer[:, :3] @ inner[:, 3] + outer[:, 3]
    return out


def placement(x: float, yaw_degrees: float) -> np.ndarray:
    """A unit at ``x`` on the X axis, turned ``yaw_degrees`` about Y (+Z turns toward +X)."""
    a = math.radians(yaw_degrees)
    c, s = math.cos(a), math.sin(a)
    return np.array([[c, 0, s, x], [0, 1, 0, 0], [-s, 0, c, 0]], dtype=np.float64)


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
    eye: Optional[int] = None  # _cam_: what the game camera looks at

    @property
    def params(self) -> UnitParams:
        return self.assets.staging()

    def bone(self, *names: str) -> Optional[int]:
        bones = [b.name for b in self.loaded.bones] if self.loaded is not None else []
        return next((bones.index(n) for n in names if n in bones), None)

    def clip(self, role: str) -> Optional[tlm.Clip]:
        stem = self.assets.roles.get(role)
        anim = self.clips.get(stem) if stem else None
        if anim is None:
            return None
        impact = next((e.frame for e in anim.events if 0 in e.codes), None)
        swing = next((e.frame for e in anim.events if 1 in e.codes), None)
        release = next((e.frame for e in anim.events if 2 in e.codes), None)
        return tlm.Clip(stem, float(max(anim.length_in_frames, 1)), impact, swing, release, _codes(anim))


def _codes(anim) -> tuple:
    """``(frame, code)`` of an animation's event codes, sounds (1000 and up) left out."""
    return tuple((float(e.frame), c) for e in anim.events for c in e.codes if c < 1000)


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
            return loaded, SkinnedMesh(loaded.triangles, exact_faces=True), clips

        unit.loaded, unit.mesh, unit.clips = cache.get(("unit", assets.pack, assets.texture), load)
        ys = unit.mesh.positions[..., 1] if len(unit.loaded.triangles) else np.zeros(1)
        unit.height = max(float(ys.max() - ys.min()), 1e-3)
        bow = assets.weapon_kind == BOW_KIND
        unit.hand = unit.bone(*(HAND_BONES[::-1] if bow else HAND_BONES[:1]))
        unit.eye = unit.bone("_cam_", "_root_")
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
    """A ``zbg/<name>/`` pack placed in the battle's world: each of its
    ``map.bin`` instances (:mod:`fe_modding.formats.battle_terrain`) is its
    model at its pose. A pack without a readable ``map.bin`` comes as the
    3D model viewer loads it."""
    files, animations = _set_contents(path)
    try:
        terrain = battle_terrain.read_battle_terrain(files["map.bin"])
    except (KeyError, ValueError, struct.error):
        return _load_model_set(path.parent.name, path)
    textures = {n: d for n, d in files.items() if n.lower().endswith(".tpl")}
    models: dict = {}
    triangles: list[_Triangle] = []
    for inst in terrain.instances:
        if not 0 <= inst.model < len(terrain.models):
            continue
        name = terrain.models[inst.model].name
        if name not in models:
            parts = {n: d for n, d in files.items() if Path(n).stem == name and n.lower().endswith((".g", ".gs"))}
            loaded = _build_loaded_set(name, {**parts, **textures}, [])
            mesh = SkinnedMesh(loaded.triangles)
            world, palette = engine_pose.pose(loaded.bones) if loaded.bones else ([], [])
            models[name] = (loaded.triangles, *mesh.pose(world, palette))
        tris, positions, normals = models[name]
        matrix = np.asarray(inst.matrix(terrain.width, terrain.height), dtype=np.float64)
        rotation = matrix[:, :3] / battle_terrain.BATTLE_SCALE
        p = positions @ matrix[:, :3].T + matrix[:, 3]
        n = normals @ rotation.T
        triangles += posed_triangles(tris, p, n)
    return _LoadedSet(path.parent.name, [], triangles, {}, animations)


@dataclass
class EffectAsset:
    """A ``yme/EID_*.cmp`` effect pack, ready to pose."""

    loaded: _LoadedSet
    mesh: SkinnedMesh
    anim: Optional[animation.GaAnimation]
    length: float

    def alphas(self, local: float) -> Optional[np.ndarray]:
        """Each triangle's alpha at ``local`` from the animation's material alpha tracks (footer
        slot 1; the value replaces the material's alpha), or None when it has none."""
        if self.anim is None:
            return None
        cache = self.__dict__.setdefault("_alpha_cache", {})
        if "tracks" not in cache:
            tracks = self.anim.material_alphas()
            cache["tracks"] = tracks
            cache["materials"] = np.array([t.material for t in self.loaded.triangles], dtype=np.int64)
            cache["rest"] = np.array([t.alpha for t in self.loaded.triangles], dtype=np.float32)
        tracks = cache["tracks"]
        if not tracks:
            return None
        out = cache["rest"].copy()
        materials = cache["materials"]
        for material, track in tracks.items():
            out[materials == material] = max(0, min(track.value(local), 255)) / 255.0
        return out

    def code(self, code: int) -> Optional[float]:
        """The first frame of an event code in the effect's animation."""
        events = self.anim.events if self.anim is not None else ()
        return next((float(e.frame) for e in events if code in e.codes), None)

    def travel(self, local: float) -> float:
        """How far along from its spawn spot to its aim point the effect is at ``local``:
        code 17 jumps there, code 18 moves there by the frame of the next code 19."""
        jump = self.code(0x11)
        if jump is not None and local >= jump:
            return 1.0
        start, end = self.code(0x12), self.code(0x13)
        if start is None or local < start:
            return 0.0
        if end is None or end <= start:
            return 1.0
        return min((local - start) / (end - start), 1.0)


def load_effect(path: Path) -> Optional[EffectAsset]:
    if not path.is_file():
        return None
    loaded = _load_model_set(path.stem, path)
    anim = None
    for _name, data in loaded.animations:
        try:
            anim = animation.read_animation_bytes(data)
            break
        except Exception:  # noqa: BLE001 - an unreadable clip leaves the effect static
            continue
    length = float(anim.length_in_frames) if anim is not None and anim.length_in_frames else EFFECT_FRAMES
    return EffectAsset(loaded, SkinnedMesh(loaded.triangles), anim, length)


def effect_alpha(alpha):
    """The vertex alpha the GPU renderer draws as an effect triangle: unlit and seen from both
    sides (game effects are particle planes and shells), with ``alpha`` as its real alpha."""
    return -1.0 - np.asarray(alpha, dtype=np.float32)


POSE_CACHE = 4000  # unit poses kept (two units, a long fight)
EFFECT_FRAMES = 60.0  # an effect without an animation shows this long
ARROW_COLOR = (150, 110, 70)
ARROW_LENGTH = 6.0


def _arrow(length: float) -> tuple[list[_Triangle], np.ndarray, np.ndarray]:
    """A plain two-plane arrow along +Z (no arrow model is decoded), with both windings."""
    w = length * 0.03
    quads = [((-w, 0, 0), (w, 0, 0), (w, 0, length), (-w, 0, length)),
             ((0, -w, 0), (0, w, 0), (0, w, length), (0, -w, length))]
    tris = []
    for a, b, c, d in quads:
        for tri in ((a, b, c), (a, c, d), (c, b, a), (d, c, a)):
            tris.append(_Triangle(tri[0], tri[1], tri[2], (0.0, 0.0, -1.0), ARROW_COLOR))
    positions = np.array([(t.a, t.b, t.c) for t in tris], dtype=np.float64)
    normals = np.array([t.normal for t in tris], dtype=np.float64)
    return tris, positions, normals


def _look_rotation(direction: np.ndarray) -> np.ndarray:
    """A 3x3 rotation turning +Z to ``direction``."""
    z = direction / max(np.linalg.norm(direction), 1e-9)
    up = np.array([0.0, 1.0, 0.0]) if abs(z[1]) < 0.99 else np.array([1.0, 0.0, 0.0])
    x = np.cross(up, z)
    x /= max(np.linalg.norm(x), 1e-9)
    y = np.cross(z, x)
    return np.stack([x, y, z], axis=1)


@dataclass
class _Part:
    """One run of the scene's triangle list."""

    start: int
    count: int
    kind: str  # scenery, unit, weapon, flight, effect
    side: int = 0
    item: object = None  # the Flight or Cue it shows


class BattleStage:
    """Scenery plus two :class:`StageUnit` s on the game's spots.

    ``effects(kind, key)`` returns the :class:`EffectAsset` of a timeline
    cue (a skill key or a spell's EID), or None to skip it. After
    :meth:`set_log`, :meth:`triangles` is the scene's fixed triangle list and
    :meth:`arrays` / :meth:`frame` pose it at a frame."""

    def __init__(self, units: list[StageUnit], scenery: Optional[_LoadedSet] = None, effects=None,
                 params: Optional[BattleParams] = None, foot_effect: int = 1):
        self.units = units
        self.foot_effect = foot_effect  # the backdrop's ground: picks dust, splashes or snow
        self.scenery = scenery.triangles if scenery is not None else []
        self.params = params or BattleParams()
        self.timeline: Optional[tlm.Timeline] = None
        self.shots: Optional[list] = None  # camera.Shot per tick
        self.effects = effects or (lambda kind, key: None)
        self._world: list = [[], []]  # each unit's bone world matrices at the last frame (placed)
        self._arrow = _arrow(ARROW_LENGTH)
        self._parts: list[_Part] = []
        self._triangles: list[_Triangle] = []
        self._rest_parts: list = []
        self._poses: dict = {}
        self.changed: Optional[np.ndarray] = None
        self.alphas: Optional[np.ndarray] = None
        self._rest: Optional[np.ndarray] = None
        self._rest_normals: Optional[np.ndarray] = None

    def lookup(self, side: int, role: str) -> Optional[tlm.Clip]:
        return self.units[side].clip(role)

    def effect_clip(self, eid: str) -> Optional[tlm.Clip]:
        """An effect pack's animation as a clip: its length and events (a spell's blow lands on
        its event 0, a miss on event 1)."""
        effect = self.effects("effect", eid)
        anim = effect.anim if effect is not None else None
        if anim is None:
            return None
        impact = next((e.frame for e in anim.events if 0 in e.codes), None)
        swing = next((e.frame for e in anim.events if 1 in e.codes), None)
        return tlm.Clip(eid, float(effect.length), impact, swing, None, _codes(anim))

    def set_log(self, log, distance: int = 1, game_camera: Optional[cam.GameCamera] = None) -> None:
        self.timeline = tlm.build(log, self.lookup, distance=distance, params=self.params,
                                  units=[u.params for u in self.units],
                                  weapon_kinds=[u.assets.weapon_kind for u in self.units],
                                  weapons=[tlm.WeaponEffects(u.assets.weapon_missile, u.assets.weapon_effect,
                                                             u.assets.weapon_damage_effect) for u in self.units],
                                  effect_clip=self.effect_clip, foot_effect=self.foot_effect,
                                  cameras=game_camera.scripts if game_camera is not None else ())
        self.shots = game_camera.track(self.timeline.camera, self.timeline.quakes, int(self.timeline.length)) \
            if game_camera is not None else None
        self._layout()

    # -- layout -----------------------------------------------------------------------------------
    def _add(self, kind: str, tris: list, positions=None, normals=None, side: int = 0, item=None) -> None:
        if not tris:
            return
        self._parts.append(_Part(len(self._triangles), len(tris), kind, side, item))
        self._triangles.extend(tris)
        if positions is None:
            positions = np.array([(t.a, t.b, t.c) for t in tris], dtype=np.float64)
            normals = np.array([t.normal for t in tris], dtype=np.float64)
        self._rest_parts.append((positions, normals))

    def _layout(self) -> None:
        self._parts, self._triangles, self._rest_parts = [], [], []
        self._add("scenery", self.scenery)
        for side, unit in enumerate(self.units):
            if unit.loaded is not None:
                self._add("unit", unit.loaded.triangles, unit.mesh.positions, unit.mesh.normals, side)
            if unit.weapon is not None:
                self._add("weapon", unit.weapon.triangles, unit.weapon_positions, unit.weapon_normals, side)
        tl = self.timeline
        for flight in (tl.flights if tl is not None else ()):
            unit = self.units[flight.side]
            if unit.weapon is not None and unit.assets.weapon_kind != BOW_KIND:
                self._add("flight", unit.weapon.triangles, unit.weapon_positions, unit.weapon_normals,
                          flight.side, flight)
            else:
                tris, positions, normals = self._arrow
                self._add("flight", tris, positions, normals, flight.side, flight)
        for cue in (tl.cues if tl is not None else ()):
            effect = self.effects(cue.kind, cue.key)
            if effect is not None:
                self._add("effect", effect.loaded.triangles, effect.mesh.positions, effect.mesh.normals,
                          cue.side, (cue, effect))
        if self._rest_parts:
            self._rest = np.concatenate([p for p, _n in self._rest_parts])
            self._rest_normals = np.concatenate([n for _p, n in self._rest_parts])
        else:
            self._rest = np.zeros((0, 3, 3))
            self._rest_normals = np.zeros((0, 3))
        # posed in place every frame: every moving part is written or hidden each time
        self._posed = self._rest.copy(), self._rest_normals.copy()
        self._rest_alphas = np.array([t.alpha for t in self._triangles], dtype=np.float32)
        self.alphas = self._rest_alphas.copy()  # each triangle's alpha this frame (effects fade)
        self.changed = np.ones(len(self._triangles), dtype=bool)
        for part in self._parts:
            if part.kind == "scenery":
                self.changed[part.start:part.start + part.count] = False

    def triangles(self) -> list[_Triangle]:
        return self._triangles

    # -- posing -----------------------------------------------------------------------------------
    def placement(self, side: int, t: float) -> np.ndarray:
        x = self.timeline.x(side, t) if self.timeline is not None else self.params.start_x(side)
        return placement(x, FACING[side])

    def point(self, side: int, bone: Optional[int], t: float = 0.0) -> np.ndarray:
        """Where ``bone`` of ``side`` is at the last posed frame (the unit's spot if unknown)."""
        world = self._world[side]
        if bone is not None and bone < len(world):
            return world[bone][:, 3].copy()
        return self.placement(side, t)[:, 3].copy()

    def arrays(self, t: float) -> tuple[np.ndarray, np.ndarray]:
        """The scene's triangles posed at frame ``t``: positions (n, 3, 3), normals (n, 3).
        The same two arrays come back every call, rewritten."""
        if self._rest is None:
            self._layout()
        positions, normals = self._posed
        tl = self.timeline
        flying = {id(f) for f in (tl.flights if tl is not None else ()) if f.progress(t) is not None}
        thrown = {f.side for f in (tl.flights if tl is not None else ())
                  if id(f) in flying and self.units[f.side].assets.weapon_kind not in (None, BOW_KIND)}
        for side, unit in enumerate(self.units):
            self._world[side] = []
            if unit.loaded is None:
                continue
            place = self.placement(side, t)
            stem, frame = tl.pose(side, t) if tl is not None else (None, 0.0)
            world, palette = self._pose(side, unit, stem, frame)
            self._world[side] = _compose_all(place, world) if len(world) else []
            part = self._part("unit", side)
            if part is not None:
                self._put(positions, normals, part, *unit.mesh.pose(world, palette, place))
        for side, unit in enumerate(self.units):
            part = self._part("weapon", side)
            if part is None:
                continue
            world = self._world[side]
            if unit.hand is None or unit.hand >= len(world) or side in thrown:
                self._hide(positions, part)
            else:
                self._put(positions, normals, part, *_transform(world[unit.hand], unit.weapon_positions,
                                                                unit.weapon_normals))
        for part in self._parts:
            if part.kind == "flight":
                u = part.item.progress(t)
                if u is None:
                    self._hide(positions, part)
                else:
                    self._put(positions, normals, part, *self._projectile(part, u, t))
            elif part.kind == "effect":
                cue, effect = part.item
                if cue.frame <= t < cue.frame + effect.length:
                    self._put(positions, normals, part, *self._effect(effect, cue, t - cue.frame, t))
                    faded = effect.alphas(t - cue.frame)
                    rest = self._rest_alphas[part.start:part.start + part.count]
                    self.alphas[part.start:part.start + part.count] = effect_alpha(
                        faded if faded is not None else rest)
                else:
                    self._hide(positions, part)
        return positions, normals

    def _pose(self, side: int, unit: StageUnit, stem: Optional[str], frame: float):
        """``engine_pose.pose`` of a unit's clip frame, kept for replays and scrubbing."""
        key = (side, stem, round(frame, 3))
        cached = self._poses.get(key)
        if cached is None:
            anim = unit.clips.get(stem) if stem else None
            cached = engine_pose.pose(unit.loaded.bones, anim, frame) if unit.loaded.bones else ([], [])
            if len(self._poses) > POSE_CACHE:
                self._poses.clear()
            self._poses[key] = cached
        return cached

    def frame(self, t: float) -> list[_Triangle]:
        """The visible triangles at frame ``t`` (hidden parts left out)."""
        positions, normals = self.arrays(t)
        posed = posed_triangles(self._triangles, positions, normals)
        hidden = set()
        for part in self._parts:
            if not positions[part.start:part.start + part.count].any():
                hidden.update(range(part.start, part.start + part.count))
        return [tri for i, tri in enumerate(posed) if i not in hidden]

    def _part(self, kind: str, side: int) -> Optional[_Part]:
        return next((p for p in self._parts if p.kind == kind and p.side == side), None)

    @staticmethod
    def _put(positions, normals, part: _Part, p: np.ndarray, n: np.ndarray) -> None:
        positions[part.start:part.start + part.count] = p
        normals[part.start:part.start + part.count] = n

    @staticmethod
    def _hide(positions, part: _Part) -> None:
        positions[part.start:part.start + part.count] = 0.0

    def _projectile(self, part: _Part, u: float, t: float) -> tuple[np.ndarray, np.ndarray]:
        side = part.side
        unit, target = self.units[side], self.units[1 - side]
        start = self.point(side, unit.hand, t)
        end = self.point(1 - side, target.eye, t)
        matrix = np.zeros((3, 4))
        matrix[:, :3] = _look_rotation(end - start)
        matrix[:, 3] = start + (end - start) * u
        rest_p, rest_n = self._rest[part.start:part.start + part.count], \
            self._rest_normals[part.start:part.start + part.count]
        return _transform(matrix, rest_p, rest_n)

    def _effect(self, effect: EffectAsset, cue: tlm.Cue, local: float, t: float) -> tuple[np.ndarray, np.ndarray]:
        bones = effect.loaded.bones
        world, palette = engine_pose.pose(bones, effect.anim, local) if bones else ([], [])
        # spawn_effect_at_position: where the unit stands when the effect starts, on the ground
        # (cue.height up), turned as the unit is; it stays there while it plays
        matrix = self.placement(cue.side, cue.frame)
        if cue.aim is not None and self.timeline is not None:
            x0, x1 = matrix[0, 3], self.timeline.x(cue.aim, cue.frame)
            matrix[0, 3] = x0 + (x1 - x0) * effect.travel(local)
        matrix[1, 3] = cue.height
        return effect.mesh.pose(world, palette, matrix)

    # -- camera -----------------------------------------------------------------------------------
    def view(self, t: float) -> Optional[tuple[tuple, tuple]]:
        """``(eye, center)`` of the game camera at ``t`` (after :meth:`arrays` posed that frame)."""
        if not self.shots:
            return None
        # tick 0 only sets the scene up; the opening camera script starts on tick 1, so the first
        # picture is tick 1's (the rig's resting pose at tick 0 sits under the ground)
        shot = self.shots[max(min(1, len(self.shots) - 1), min(int(t), len(self.shots) - 1))]
        if shot.side is None:
            target = shot.dest
        else:
            target = self.point(shot.side, self.units[shot.side].eye, t)
        return shot.eye_center(target)


#: Ticks playback may skip to keep up with the clock; a longer stall pauses the clock instead.
MAX_CATCH_UP = 6


class StageView(ttk.Frame):
    """Canvas, HP bars and playback controls for a :class:`BattleStage`.

    The canvas keeps the game's 4:3 picture; playback follows the wall clock
    (:data:`~fe_modding.battle_sim.timeline.FPS` frames a second)."""

    def __init__(self, parent: tk.Misc):
        super().__init__(parent)
        self.stage: Optional[BattleStage] = None
        self._t = 0.0
        self._playing = False
        self._after = None
        self._clock: Optional[tuple[float, float]] = None  # (wall time, frame) playback started from
        self._max_hp = (1, 1)
        self._names = SIDE_NAMES
        self.on_finished = None  # called when playback reaches the end of the fight

        bars = ttk.Frame(self)
        bars.pack(fill="x")
        self._hp_labels, self._hp_bars = [], []
        for side in (0, 1):
            box = ttk.Frame(bars)
            box.pack(side="left", fill="x", expand=True, padx=4)
            label = ttk.Label(box, text=SIDE_NAMES[side])
            label.pack(anchor="w" if side == 0 else "e")
            bar = ttk.Progressbar(box, maximum=1, value=1)
            bar.pack(fill="x")
            self._hp_labels.append(label)
            self._hp_bars.append(bar)
        self._popup = ttk.Label(self, text="", style="Subtitle.TLabel", anchor="center")
        self._popup.pack(fill="x")

        self._screen = tk.Frame(self, background="#000000")
        self._screen.pack(fill="both", expand=True)
        self.canvas = _ModelCanvas(self._screen)
        self.canvas.set_show_skeleton(False)
        self._screen.bind("<Configure>", self._fit_screen)

        controls = ttk.Frame(self)
        controls.pack(fill="x", pady=(4, 0))
        self._play_button = ttk.Button(controls, text="Play", command=self.toggle, width=7)
        self._play_button.pack(side="left")
        ttk.Button(controls, text="Replay", command=self.replay).pack(side="left", padx=(4, 0))
        self._scale = ttk.Scale(controls, from_=0, to=1, command=self._scrub)
        self._scale.pack(side="left", fill="x", expand=True, padx=(8, 0))
        self._time = ttk.Label(controls, text="", width=12)
        self._time.pack(side="left", padx=(6, 0))

    def _fit_screen(self, event) -> None:
        """Center the largest 4:3 box in the screen area."""
        width, height = max(event.width, 1), max(event.height, 1)
        w = min(width, int(height * cam.ASPECT))
        h = int(w / cam.ASPECT)
        self.canvas.place(x=(width - w) // 2, y=(height - h) // 2, width=w, height=h)

    def set_stage(self, stage: Optional[BattleStage], names: tuple = SIDE_NAMES, max_hp: tuple = (1, 1)) -> None:
        self.stop()
        self.stage = stage
        self._max_hp = max_hp
        self._names = tuple(names)
        for side in (0, 1):
            self._hp_labels[side].configure(text=names[side])
        if stage is None or stage.timeline is None:
            self.canvas.set_model([], {}, {}, {})
            return
        self._scale.configure(to=stage.timeline.length)
        self._t = 0.0
        self.canvas.set_model(stage.triangles(), {}, {}, {})
        self._show(0.0)

    def refresh(self) -> None:
        if self.stage is not None and self.stage.timeline is not None:
            self._scale.configure(to=self.stage.timeline.length)
            self._t = min(self._t, self.stage.timeline.length)
            self._show(self._t)

    def _show(self, t: float, now: bool = False) -> None:
        stage = self.stage
        if stage is None or stage.timeline is None:
            return
        positions, normals = stage.arrays(t)
        self.canvas.set_pose_arrays(positions, normals, stage.changed, stage.alphas)
        view = stage.view(t)
        if view is not None:
            self.canvas.set_camera(view[0], view[1], cam.FOVY)
        if now:
            self.canvas.render_now()
        hp = stage.timeline.hp(t)
        for side in (0, 1):
            maximum = max(self._max_hp[side], stage.timeline.hp_start[side], 1)
            self._hp_bars[side].configure(maximum=maximum, value=max(hp[side], 0))
            self._hp_labels[side].configure(text=f"{self._names[side]}   HP {max(hp[side], 0)}")
        popup = stage.timeline.popup(t)
        name = self._names[popup.side] if popup else ""
        self._popup.configure(text=f"{name}: {popup.text}" if popup else "")
        self._time.configure(text=f"{t / tlm.FPS:5.1f} s")

    def _scrub(self, value) -> None:
        if self._playing:
            return
        self._t = float(value)
        self._show(self._t)

    def play_when_shown(self) -> None:
        """Start playing once the canvas is on screen at its size and has drawn a frame, so the
        window opening (and the GPU set-up of the first draw) does not eat the opening."""
        if self.stage is None or not self.winfo_exists():
            return
        self.update_idletasks()
        if not self.canvas.winfo_viewable() or self.canvas.winfo_width() < 50:
            self._after = self.after(30, self.play_when_shown)
            return
        self._after = None
        self._show(self._t, now=True)
        self._after = self.after(50, self.toggle)

    def toggle(self) -> None:
        if self._playing:
            self.stop()
        elif self.stage is not None and self.stage.timeline is not None:
            if self._after is not None:  # a pending play_when_shown
                self.after_cancel(self._after)
                self._after = None
            if self._t >= self.stage.timeline.length:
                self._t = 0.0
            # draw the first frame before the clock starts (the first draw also sets up the GPU)
            self._show(self._t, now=True)
            self._playing = True
            self._clock = (time.perf_counter(), self._t)
            self._play_button.configure(text="Pause")
            self._tick()

    def replay(self) -> None:
        self.stop()
        self._t = 0.0
        self._scale.set(0)
        self.toggle()

    def stop(self) -> None:
        self._playing = False
        if self._after is not None:
            self.after_cancel(self._after)
            self._after = None
        self._play_button.configure(text="Play")

    def _tick(self) -> None:
        self._after = None
        if not self._playing or self.stage is None or self.stage.timeline is None:
            return
        started, frame0 = self._clock
        # the game shows whole ticks: show the last one the clock has reached
        shown = self._t
        self._t = float(math.floor(frame0 + (time.perf_counter() - started) * tlm.FPS))
        if self._t - shown > MAX_CATCH_UP:
            # a stall (a first draw, a clip loading, the window being moved): carry on from the
            # next tick instead of jumping ahead, and follow the clock again from there
            self._t = shown + 1
            self._clock = started, frame0 = time.perf_counter(), self._t
        length = self.stage.timeline.length
        if self._t >= length:
            self._t = length
            self._scale.set(self._t)
            self._show(self._t, now=True)
            self.update_idletasks()
            self.stop()
            if self.on_finished is not None:
                self.on_finished()
            return
        self._scale.set(self._t)
        self._show(self._t, now=True)
        # Tk puts the new image and labels on screen only when idle, and the next tick's timer is
        # usually already due: flush the display now or the picture freezes until a stall
        self.update_idletasks()
        # the next frame is due one tick after this one; never queue behind a slow frame
        due = self._t + 1
        wait = (due - frame0) / tlm.FPS - (time.perf_counter() - started)
        self._after = self.after(max(1, int(wait * 1000)), self._tick)

    def cleanup(self) -> None:
        self.stop()
