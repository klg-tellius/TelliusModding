"""Fit a rigged humanoid glTF onto a character set as a **new rig**: the
model keeps its own skeleton (names, proportions) and gets every animation
of the set, retargeted from the game rig.

Steps (:func:`fit_rig`):

1. **Body chains.** On both skeletons the feet, hands and head are found
   (anchor bones first: ``_lfoot_``/``_rfoot_``, ``_l_hand_``/``_r_hand_``,
   ``_s1_``/``_s2_``, the map weapon's hand; else the lowest, outermost and
   highest deforming joints); the pelvis is where the legs meet, the chest
   where the arms meet. Spine, neck and limb chains are matched joint to
   joint by their position along the chain (:func:`auto_mapping`); the
   mapping can be edited.
2. **Rest pose.** The model is scaled to the game mesh's height and each
   mapped joint is turned so its bone points where the game bone it follows
   points (rotation only: the model keeps its proportions). The mesh
   follows through its own skinning. Joints get identity rest rotations.
3. **Sockets.** The game rig's anchor bones (weapon hands, root, camera,
   feet, trail ends) and, on a map model, its weapon bones with their
   meshes (``Ax``/``Ax1``) are added under the model joint that follows
   their game parent, at the game offset. On a battle rig an anchor
   follows its parent's joint exactly, so it hangs from a carrier bone at
   the offset.
4. **Animations.** Per frame, each mapped joint takes the world rotation
   change of its game bone, the pelvis the game pelvis's motion, weapon
   bones the game scale (shown or hidden). Unmapped joints (fingers, hair)
   follow their parent. Events and loop settings are the game's.

The result is a glTF for :func:`model_viewer.replace_battle_rig_with_glb`
(new-rig mode) or :func:`model_viewer.replace_rig_with_glb`.
"""

from __future__ import annotations

import io
import json
import struct
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import numpy as np
from PIL import Image

from .formats import gltf_import

FOLLOW_PARENT = ""


class RigFitError(Exception):
    pass


# ---------------------------------------------------------------- glTF reading


def _quat_matrix(q) -> np.ndarray:
    x, y, z, w = q
    return np.array([
        [1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
        [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
        [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)],
    ])


def _trs(node: dict) -> np.ndarray:
    if "matrix" in node:
        return np.array(node["matrix"], float).reshape(4, 4).T
    m = np.eye(4)
    m[:3, :3] = _quat_matrix(node.get("rotation", (0, 0, 0, 1))) * np.array(node.get("scale", (1, 1, 1)))
    m[:3, 3] = node.get("translation", (0, 0, 0))
    return m


def _quat_from_matrix(m: np.ndarray) -> np.ndarray:
    t = np.trace(m)
    if t > 0:
        s = np.sqrt(t + 1.0) * 2
        q = [(m[2, 1] - m[1, 2]) / s, (m[0, 2] - m[2, 0]) / s, (m[1, 0] - m[0, 1]) / s, 0.25 * s]
    elif m[0, 0] > m[1, 1] and m[0, 0] > m[2, 2]:
        s = np.sqrt(1.0 + m[0, 0] - m[1, 1] - m[2, 2]) * 2
        q = [0.25 * s, (m[0, 1] + m[1, 0]) / s, (m[0, 2] + m[2, 0]) / s, (m[2, 1] - m[1, 2]) / s]
    elif m[1, 1] > m[2, 2]:
        s = np.sqrt(1.0 + m[1, 1] - m[0, 0] - m[2, 2]) * 2
        q = [(m[0, 1] + m[1, 0]) / s, 0.25 * s, (m[1, 2] + m[2, 1]) / s, (m[0, 2] - m[2, 0]) / s]
    else:
        s = np.sqrt(1.0 + m[2, 2] - m[0, 0] - m[1, 1]) * 2
        q = [(m[0, 2] + m[2, 0]) / s, (m[1, 2] + m[2, 1]) / s, 0.25 * s, (m[1, 0] - m[0, 1]) / s]
    q = np.array(q)
    return q / np.linalg.norm(q)


def _orthonormal(m: np.ndarray) -> np.ndarray:
    u, _s, vt = np.linalg.svd(m)
    if np.linalg.det(u @ vt) < 0:
        u[:, -1] *= -1
    return u @ vt


def _rotation_between(a, b) -> np.ndarray:
    a = np.asarray(a, float) / np.linalg.norm(a)
    b = np.asarray(b, float) / np.linalg.norm(b)
    v = np.cross(a, b)
    c = float(np.dot(a, b))
    if c < -0.999999:
        axis = np.cross(a, [1.0, 0, 0])
        if np.linalg.norm(axis) < 1e-6:
            axis = np.cross(a, [0, 1.0, 0])
        axis /= np.linalg.norm(axis)
        return 2 * np.outer(axis, axis) - np.eye(3)
    vx = np.array([[0, -v[2], v[1]], [v[2], 0, -v[0]], [-v[1], v[0], 0]])
    return np.eye(3) + vx + vx @ vx / (1 + c)


def is_anchor(name: str) -> bool:
    return gltf_import.is_anchor_name(name)


@dataclass
class Rig:
    """A skinned glTF at rest: joints, their rest world matrices, the mesh
    as displayed, its texture, and (for a rig kit) its animations."""

    doc: gltf_import._Document
    nodes: list[dict]
    node_parent: dict[int, int]
    joints: list[int]  # node indices
    names: list[str]
    parent: list[int]  # joint index of the parent joint, -1 for none
    rest: np.ndarray  # (n, 4, 4) rest world matrices
    V: np.ndarray
    N: np.ndarray
    UV: np.ndarray
    J: np.ndarray  # (v, 4) joint indices
    W: np.ndarray  # (v, 4) weights
    idx: np.ndarray
    image: Optional[Image.Image]
    joint_index: dict[str, int] = field(default_factory=dict)

    @property
    def pos(self) -> np.ndarray:
        return self.rest[:, :3, 3]

    def children(self, j: int) -> list[int]:
        return [k for k, p in enumerate(self.parent) if p == j]

    def ancestors(self, j: int) -> list[int]:
        out = []
        while self.parent[j] >= 0:
            j = self.parent[j]
            out.append(j)
        return out

    def path(self, top: int, bottom: int) -> list[int]:
        """Joints from ``top`` (excluded) down to ``bottom`` (included)."""
        chain = [bottom]
        while chain[-1] != top:
            p = self.parent[chain[-1]]
            if p < 0:
                raise RigFitError(f"{self.names[top]} is not above {self.names[bottom]}.")
            chain.append(p)
        return list(reversed(chain[:-1]))

    def lca(self, a: int, b: int) -> int:
        up = set([a] + self.ancestors(a))
        for j in [b] + self.ancestors(b):
            if j in up:
                return j
        raise RigFitError("The skeleton has more than one root.")


def _node_worlds(nodes: list[dict], parent: dict[int, int], local=None) -> dict[int, np.ndarray]:
    world: dict[int, np.ndarray] = {}

    def w(i):
        if i not in world:
            m = local[i] if local is not None and i in local else _trs(nodes[i])
            world[i] = (w(parent[i]) @ m) if i in parent else m
        return world[i]

    for i in range(len(nodes)):
        w(i)
    return world


def read_rig(data: bytes, base_dir: Optional[Path] = None, *, single_texture: bool = True) -> Rig:
    d = gltf_import._Document(data, base_dir)
    doc = d.doc
    skins = doc.get("skins", [])
    if not skins:
        raise RigFitError("The model has no armature (glTF skin).")
    skin_index = max(range(len(skins)), key=lambda i: len(skins[i].get("joints", [])))
    skin = skins[skin_index]
    nodes = doc["nodes"]
    node_parent = {c: i for i, n in enumerate(nodes) for c in n.get("children", [])}
    world = _node_worlds(nodes, node_parent)
    joints = list(skin["joints"])
    names = [nodes[j].get("name") or f"joint{k}" for k, j in enumerate(joints)]
    jset = {j: k for k, j in enumerate(joints)}

    def joint_parent(j):
        p = node_parent.get(j)
        while p is not None and p not in jset:
            p = node_parent.get(p)
        return jset[p] if p is not None else -1

    parent = [joint_parent(j) for j in joints]
    rest = np.array([world[j] for j in joints])
    if "inverseBindMatrices" in skin:
        ibm = np.array(d.accessor(skin["inverseBindMatrices"]), float).reshape(-1, 4, 4).transpose(0, 2, 1)
    else:
        ibm = np.array([np.linalg.inv(m) for m in rest])
    skin_m = np.array([rest[k] @ ibm[k] for k in range(len(joints))])
    Vs, Ns, UVs, Js, Ws, idxs, images = [], [], [], [], [], [], set()
    image = None
    base = 0
    for i, node in enumerate(nodes):
        if node.get("skin") != skin_index or "mesh" not in node:
            continue
        for prim in doc["meshes"][node["mesh"]]["primitives"]:
            at = prim["attributes"]
            if "JOINTS_0" not in at or prim.get("mode", 4) != 4:
                continue
            P = np.array(d.accessor(at["POSITION"]), float)
            n = len(P)
            N = np.array(d.accessor(at["NORMAL"]), float) if "NORMAL" in at else np.tile([0.0, 1.0, 0.0], (n, 1))
            UV = np.array(d.accessor(at["TEXCOORD_0"]), float) if "TEXCOORD_0" in at else np.zeros((n, 2))
            J = np.array(d.accessor(at["JOINTS_0"]), int)
            W = np.array(d.accessor(at["WEIGHTS_0"]), float)
            if doc["accessors"][at["WEIGHTS_0"]]["componentType"] == 5121 and not doc["accessors"][at["WEIGHTS_0"]].get("normalized"):
                W = W / 255.0
            W = W / np.maximum(W.sum(1, keepdims=True), 1e-9)
            M = skin_m[J]
            V = np.einsum("vk,vkij,vj->vi", W, M, np.c_[P, np.ones(n)])[:, :3]
            Nn = np.einsum("vk,vkij,vj->vi", W, M[:, :, :3, :3], N)
            Nn /= np.maximum(np.linalg.norm(Nn, axis=1, keepdims=True), 1e-9)
            idx = np.array(d.accessor(prim["indices"]), int).reshape(-1) if "indices" in prim else np.arange(n)
            material = doc.get("materials", [{}])[prim["material"]] if "material" in prim else {}
            tex = material.get("pbrMetallicRoughness", {}).get("baseColorTexture", {}).get("index")
            if tex is not None:
                images.add(tex)
                if image is None:
                    image = d.image(tex)
            Vs.append(V)
            Ns.append(Nn)
            UVs.append(UV)
            Js.append(J)
            Ws.append(W)
            idxs.append(idx + base)
            base += n
    if not Vs:
        raise RigFitError("The armature has no skinned mesh.")
    if single_texture and len(images) > 1:
        raise RigFitError(
            f"The model uses {len(images)} textures; bake them into one image (one material) first."
        )
    rig = Rig(
        d, nodes, node_parent, joints, names, parent, rest,
        np.vstack(Vs), np.vstack(Ns), np.vstack(UVs), np.vstack(Js), np.vstack(Ws), np.concatenate(idxs), image,
    )
    rig.joint_index = {n: k for k, n in enumerate(names)}
    return rig


# ---------------------------------------------------------------- body chains


@dataclass
class Chains:
    pelvis: int
    chest: int
    spine: list[int]  # pelvis .. chest, both included
    neck: list[int]  # below chest .. head
    limbs: dict[str, list[int]]  # arm_l, arm_r, leg_l, leg_r: from below the branch to the end


def _deforming(rig: Rig, skip: set[int]) -> set[int]:
    dominant = rig.J[np.arange(len(rig.J)), rig.W.argmax(1)]
    return {int(j) for j in np.unique(dominant)} - skip


def body_chains(rig: Rig, skip: set[int] = frozenset(), ends: Optional[dict[str, int]] = None) -> Chains:
    """Pelvis, chest and the spine, neck and limb chains. ``ends`` may name
    known feet/hands (``foot_l``, ``foot_r``, ``hand_l``, ``hand_r``);
    missing ones are the lowest and outermost deforming joints on each side
    (+x is the character's left, glTF convention)."""
    ends = dict(ends or {})
    deform = _deforming(rig, set(skip))
    if len(deform) < 5:
        raise RigFitError("The armature has too few weighted joints for a humanoid.")
    pos = rig.pos
    cand = sorted(deform)
    mid_y = (pos[cand, 1].min() + pos[cand, 1].max()) / 2
    if "foot_l" not in ends:
        side = [j for j in cand if pos[j, 0] > 0] or cand
        ends["foot_l"] = min(side, key=lambda j: (pos[j, 1], -pos[j, 0]))
    if "foot_r" not in ends:
        side = [j for j in cand if pos[j, 0] < 0] or cand
        ends["foot_r"] = min(side, key=lambda j: (pos[j, 1], pos[j, 0]))
    upper = [j for j in cand if pos[j, 1] > mid_y] or cand
    if "hand_l" not in ends:
        ends["hand_l"] = max(upper, key=lambda j: pos[j, 0])
    if "hand_r" not in ends:
        ends["hand_r"] = min(upper, key=lambda j: pos[j, 0])
    pelvis = rig.lca(ends["foot_l"], ends["foot_r"])
    chest = rig.lca(ends["hand_l"], ends["hand_r"])
    if pelvis not in [chest] + rig.ancestors(chest):
        raise RigFitError(
            f"Could not find the spine: the legs meet at {rig.names[pelvis]} and the arms at {rig.names[chest]}, "
            "which is not below it."
        )
    limb_joints = set(rig.path(pelvis, ends["foot_l"]) + rig.path(pelvis, ends["foot_r"]))
    limb_joints |= set(rig.path(chest, ends["hand_l"]) + rig.path(chest, ends["hand_r"]))
    head_cands = [j for j in cand if chest in rig.ancestors(j) and j not in limb_joints]
    if not head_cands:
        raise RigFitError("Could not find the head: no weighted joint above the chest besides the arms.")
    head = max(head_cands, key=lambda j: pos[j, 1])
    # the head chain stops at the joint that carries the head, not a hair tip
    neck = rig.path(chest, head)
    spine = [pelvis] + (rig.path(pelvis, chest) if chest != pelvis else [])
    limbs = {
        "arm_l": rig.path(chest, ends["hand_l"]),
        "arm_r": rig.path(chest, ends["hand_r"]),
        "leg_l": rig.path(pelvis, ends["foot_l"]),
        "leg_r": rig.path(pelvis, ends["foot_r"]),
    }
    return Chains(pelvis, chest, spine, neck, limbs)


def _chain_fractions(rig: Rig, start: int, chain: list[int]) -> list[float]:
    pts = [rig.pos[start]] + [rig.pos[j] for j in chain]
    lengths = np.cumsum([0.0] + [np.linalg.norm(b - a) for a, b in zip(pts, pts[1:])])
    total = lengths[-1] or 1.0
    return list(lengths[1:] / total)


def _match_chain(model: Rig, m_start: int, m_chain: list[int], game: Rig, g_start: int, g_chain: list[int]) -> dict[int, int]:
    if not m_chain or not g_chain:
        return {}
    mf = _chain_fractions(model, m_start, m_chain)
    gf = _chain_fractions(game, g_start, g_chain)
    out = {}
    for j, f in zip(m_chain, mf):
        k = min(range(len(g_chain)), key=lambda i: abs(gf[i] - f))
        out[j] = g_chain[k]
    out[m_chain[-1]] = g_chain[-1]
    return out


def _match_from_end(m_chain: list[int], g_chain: list[int]) -> dict[int, int]:
    """Arms: hand to hand, elbow to elbow, shoulder to shoulder, then any
    collarbone; extra model joints nearer the chest follow the first game
    one."""
    out = {}
    for i, j in enumerate(reversed(m_chain)):
        out[j] = g_chain[max(len(g_chain) - 1 - i, 0)]
    return out


def auto_mapping(model: Rig, model_chains: Chains, game: Rig, game_chains: Chains) -> dict[str, str]:
    """Model joint name -> game bone name (or :data:`FOLLOW_PARENT`)."""
    mapping: dict[int, int] = {}
    mapping[model_chains.pelvis] = game_chains.pelvis
    ms, gs = model_chains.spine, game_chains.spine
    if len(ms) > 1 and len(gs) > 1:
        mapping.update(_match_chain(model, ms[0], ms[1:], game, gs[0], gs[1:]))
    mapping[model_chains.chest] = game_chains.chest
    mapping.update(_match_chain(model, model_chains.chest, model_chains.neck, game, game_chains.chest, game_chains.neck))
    for limb in ("arm_l", "arm_r"):
        mapping.update(_match_from_end(model_chains.limbs[limb], game_chains.limbs[limb]))
    for limb in ("leg_l", "leg_r"):
        m, g = model_chains.limbs[limb], game_chains.limbs[limb]
        if m and g:
            mapping[m[0]] = g[0]
            mapping.update(_match_chain(model, m[0], m[1:], game, g[0], g[1:]))
    return {model.names[j]: (game.names[mapping[j]] if j in mapping else FOLLOW_PARENT) for j in range(len(model.names))}


# ---------------------------------------------------------------- game side


def game_ends(game: Rig, weapon_bones: set[str]) -> dict[str, int]:
    """Feet and hands of a game rig from its anchors (battle hands and feet,
    map shadow points, the map weapon's hand)."""
    ix = game.joint_index
    ends = {}

    def parent_of(name):
        return game.parent[ix[name]] if name in ix and game.parent[ix[name]] >= 0 else None

    for key, names in (("hand_l", ("_l_hand_",)), ("hand_r", ("_r_hand_",)), ("foot_l", ("_lfoot_",)), ("foot_r", ("_rfoot_",))):
        for n in names:
            p = parent_of(n)
            if p is not None:
                ends[key] = p
    for n in ("_s1_", "_s2_"):
        p = parent_of(n)
        if p is not None:
            ends["foot_l" if game.pos[ix[n], 0] > 0 else "foot_r"] = p
    for wb in sorted(weapon_bones):
        p = parent_of(wb)
        if p is not None and game.names[p] not in weapon_bones:
            key = "hand_l" if game.pos[p, 0] > 0 else "hand_r"
            ends.setdefault(key, p)
    return ends


# ---------------------------------------------------------------- fitting


@dataclass
class FitResult:
    glb: bytes
    warnings: list[str]
    mapping: dict[str, str]


def _game_weapon_bones(game_anims_hidden: dict[str, set[str]]) -> set[str]:
    return set().union(*game_anims_hidden.values()) if game_anims_hidden else set()


def fit_rig(
    model: Rig,
    game: Rig,
    mapping: dict[str, str],
    *,
    battle: bool,
    weapon_bones: set[str] = frozenset(),
) -> FitResult:
    """Build the glTF of ``model`` on its own skeleton with every animation
    of the ``game`` rig kit (see the module docstring)."""
    warnings: list[str] = []
    ix = game.joint_index
    follow = {}
    for k, name in enumerate(model.names):
        target = mapping.get(name, FOLLOW_PARENT)
        if target and target not in ix:
            raise RigFitError(f"{name} follows {target}, which is not a bone of this set.")
        follow[k] = ix[target] if target else None
    mapped = [k for k in follow if follow[k] is not None]
    if not mapped:
        raise RigFitError("No joint of the model follows a game bone.")
    # the pelvis: the mapped joint above all other mapped joints
    roots = [k for k in mapped if not any(a in mapped for a in model.ancestors(k))]
    if len(roots) != 1:
        raise RigFitError("The mapped joints must hang from one joint (the pelvis): " + ", ".join(model.names[k] for k in roots))
    pelvis = roots[0]
    g_pelvis = follow[pelvis]

    # scale and rest targets
    g_top = game.V[:, 1].max()
    m_low, m_top = model.V[:, 1].min(), model.V[:, 1].max()
    s = g_top / (m_top - m_low)
    order = sorted(range(len(model.names)), key=lambda k: len(model.ancestors(k)))
    rot: dict[int, np.ndarray] = {}
    tgt: dict[int, np.ndarray] = {}
    gp = game.pos[g_pelvis]
    tgt[pelvis] = np.array([gp[0], (model.pos[pelvis][1] - m_low) * s, gp[2]])
    for a in model.ancestors(pelvis):
        tgt[a] = tgt[pelvis] + s * (model.pos[a] - model.pos[pelvis])
        rot[a] = np.eye(3)

    def toward(k):
        """The game direction this joint's bone should point to at rest."""
        g = follow[k]
        if g is None:
            return None
        best = None
        for c in model.children(k):
            stack = [c]
            while stack:
                x = stack.pop()
                if follow[x] is not None and follow[x] != g and g in game.ancestors(follow[x]):
                    best = (x, follow[x])
                    break
                if follow[x] is None or follow[x] == g:
                    stack.extend(model.children(x))
            if best:
                break
        return best

    for k in order:
        if k in tgt and k != pelvis:
            continue
        p = model.parent[k]
        if k != pelvis:
            tgt[k] = tgt[p] + rot[p] @ (s * (model.pos[k] - model.pos[p]))
        t = toward(k)
        if t is not None:
            c, gc = t
            rot[k] = _rotation_between(model.pos[c] - model.pos[k], game.pos[gc] - game.pos[follow[k]])
        else:
            rot[k] = rot[p] if p >= 0 else np.eye(3)
    for k in order:
        if k not in tgt:
            p = model.parent[k]
            tgt[k] = tgt[p] + rot[p] @ (s * (model.pos[k] - model.pos[p]))
            rot.setdefault(k, rot[p])

    # mesh: each vertex moved by its joints' rest transforms
    V = np.zeros_like(model.V)
    N = np.zeros_like(model.N)
    for k in range(len(model.names)):
        w = (model.W * (model.J == k)).sum(1)
        m = w > 0
        if not m.any():
            continue
        V[m] += w[m, None] * (tgt[k] + (s * (model.V[m] - model.pos[k])) @ rot[k].T)
        N[m] += w[m, None] * (model.N[m] @ rot[k].T)
    N /= np.maximum(np.linalg.norm(N, axis=1, keepdims=True), 1e-9)

    # skeleton: a static root, the model's joints, then sockets and weapons
    root_name = "rig_root"
    while root_name in model.names:
        root_name += "_"
    # model joints named like the game weapon bones added below are renamed
    mname = {k: (f"{n}_model" if n in weapon_bones else n) for k, n in enumerate(model.names)}
    if any(mname[k] != model.names[k] for k in mname):
        warnings.append("Model joints renamed (a game weapon bone has the name): "
                        + ", ".join(f"{model.names[k]} -> {mname[k]}" for k in mname if mname[k] != model.names[k]))
    joints: list[tuple[str, Optional[str], np.ndarray]] = [(root_name, None, np.zeros(3))]
    jfollow: dict[str, Optional[int]] = {root_name: None}
    for k in order:
        p = model.parent[k]
        name = mname[k]
        if is_anchor(name):
            raise RigFitError(f"The model's joint {name} is named like an engine anchor; rename it.")
        joints.append((name, mname[p] if p >= 0 else root_name, tgt[k]))
        jfollow[name] = follow[k]
    holder: dict[int, str] = {}  # game bone -> the deepest model joint following it
    for k in order:
        if follow[k] is not None:
            holder[follow[k]] = mname[k]
    wpos = {n: p for n, _, p in joints}

    def attach_point(g: int) -> tuple[str, np.ndarray]:
        """The model joint that carries game bone ``g``'s children, and the
        offset that maps game rest positions onto the model."""
        for a in [g] + game.ancestors(g):
            if a in holder:
                return holder[a], wpos[holder[a]] - game.pos[a]
        return root_name, np.zeros(3)

    extra_mesh = None
    added = set()
    for gk, gname in enumerate(game.names):
        in_weapon = gname in weapon_bones or any(game.names[a] in weapon_bones for a in game.ancestors(gk))
        if not (is_anchor(gname) or in_weapon) or gname in added:
            continue
        gpar = game.parent[gk]
        parent_is_extra = gpar >= 0 and game.names[gpar] in added
        if parent_is_extra:
            parent_name = game.names[gpar]
            offset = wpos[parent_name] - game.pos[gpar]
            base_follow = jfollow[parent_name]
        else:
            parent_name, offset = attach_point(gpar) if gpar >= 0 else (root_name, np.zeros(3))
            base_follow = gpar if gpar >= 0 else None
        position = game.pos[gk] + offset
        if battle and is_anchor(gname) and not parent_is_extra and np.linalg.norm(position - wpos[parent_name]) > 1e-4:
            carrier = f"carrier{gname}"
            joints.append((carrier, parent_name, position))
            wpos[carrier] = position
            jfollow[carrier] = base_follow
            parent_name = carrier
        joints.append((gname, parent_name, position))
        wpos[gname] = position
        jfollow[gname] = gk if gname in weapon_bones else None
        added.add(gname)
    missing = [n for n in game.names if is_anchor(n) and n not in added]
    if missing:
        warnings.append("Anchors not carried over: " + ", ".join(missing))
    if weapon_bones:
        extra_mesh = _weapon_mesh(game, weapon_bones, wpos)

    # texture and weapon geometry
    idx, UV, image = model.idx, model.UV.copy(), model.image
    weights = []
    for v in range(len(V)):
        d: dict[str, float] = {}
        for slot in range(4):
            w = float(model.W[v, slot])
            if w > 0:
                key = mname[int(model.J[v, slot])]
                d[key] = d.get(key, 0) + w
        weights.append(d)
    if image is None:
        image = Image.new("RGB", (64, 64), (200, 200, 200))
        warnings.append("The model has no texture: a plain grey one is used.")
    image = image.convert("RGB")
    if extra_mesh is not None:
        EP, EN, EUV, EW, Eidx, eimg, box = extra_mesh
        size, split = 256, 192
        atlas = Image.new("RGB", (size, size))
        atlas.paste(image.resize((split, size), Image.LANCZOS), (0, 0))
        crop = eimg.convert("RGB").crop(box)
        sc = min((size - split) / max(crop.size[0], 1), size / max(crop.size[1], 1))
        atlas.paste(crop.resize((max(1, int(crop.size[0] * sc)), max(1, int(crop.size[1] * sc))), Image.LANCZOS), (split, 0))
        UV = UV.copy()
        UV[:, 0] = np.mod(UV[:, 0], 1.0) * split / size
        UV[:, 1] = np.mod(UV[:, 1], 1.0)
        iw, ih = eimg.size
        EUV = EUV.copy()
        EUV[:, 0] = (split + (EUV[:, 0] * iw - box[0]) * sc) / size
        EUV[:, 1] = ((EUV[:, 1] * ih - box[1]) * sc) / size
        idx = np.concatenate([idx, Eidx + len(V)])
        V = np.vstack([V, EP])
        N = np.vstack([N, EN])
        UV = np.vstack([UV, EUV])
        weights = weights + EW
        image = atlas

    # animations
    names = [j[0] for j in joints]
    parent_of = {n: p for n, p, _ in joints}
    anims = []
    for anim, tracks, times in _game_animations(game):
        frames = {n: [] for n in names}
        scales = {n: [] for n in names}
        hips = []
        for t in times:
            world = _pose(game, tracks, t)
            wr: dict[str, np.ndarray] = {}
            for n in names:
                g = jfollow.get(n)
                if g is None:
                    p = parent_of[n]
                    wr[n] = wr[p] if p else np.eye(3)
                    continue
                node = game.joints[g]
                R = _orthonormal(world[node][:3, :3])
                R0 = _orthonormal(game.rest[g][:3, :3])
                wr[n] = R @ R0.T
                if n in weapon_bones:
                    scales[n].append(np.linalg.norm(world[node][:3, :3], axis=0).mean()
                                     / max(np.linalg.norm(game.rest[g][:3, :3], axis=0).mean(), 1e-9))
            for n in names:
                p = parent_of[n]
                frames[n].append(_quat_from_matrix(wr[p].T @ wr[n] if p else wr[n]))
            node = game.joints[g_pelvis]
            hips.append(world[node][:3, 3] - game.rest[g_pelvis][:3, 3])
        anims.append((anim, times, frames, scales, np.array(hips)))
    glb = _write_glb(joints, V, N, UV, weights, idx, image, anims, mname[pelvis], weapon_bones)
    return FitResult(glb, warnings, dict(mapping))


def _weapon_mesh(game: Rig, weapon_bones: set[str], wpos: dict[str, np.ndarray]):
    """The game body's triangles whose vertices all belong to the weapon
    bones (or their anchors), moved with them, weighted to their bone."""
    owner = {}
    for k, n in enumerate(game.names):
        if n in weapon_bones:
            owner[k] = n
        else:
            for a in game.ancestors(k):
                if game.names[a] in weapon_bones:
                    owner[k] = game.names[a]
                    break
    dom = game.J[np.arange(len(game.J)), game.W.argmax(1)]
    tris = game.idx.reshape(-1, 3)
    keep = [t for t in tris if all(int(dom[v]) in owner for v in t)]
    if not keep or game.image is None:
        return None
    used = sorted({int(v) for t in keep for v in t})
    remap = {v: i for i, v in enumerate(used)}
    P = np.array([game.V[v] - game.pos[game.joint_index[owner[int(dom[v])]]] + wpos[owner[int(dom[v])]] for v in used])
    N = game.N[used]
    UV = game.UV[used]
    W = [{owner[int(dom[v])]: 1.0} for v in used]
    idx = np.array([remap[int(v)] for t in keep for v in t])
    img = game.image
    iw, ih = img.size
    u0, v0 = UV.min(0)
    u1, v1 = UV.max(0)
    box = (int(np.floor(u0 * iw)), int(np.floor(v0 * ih)), int(np.ceil(u1 * iw)), int(np.ceil(v1 * ih)))
    return P, N, UV, W, idx, img, box


def _game_animations(game: Rig):
    doc = game.doc.doc
    for a in doc.get("animations", []):
        tracks = {}
        times = set()
        for ch in a["channels"]:
            smp = a["samplers"][ch["sampler"]]
            t = np.array(game.doc.accessor(smp["input"]), float).reshape(-1)
            v = np.array(game.doc.accessor(smp["output"]), float)
            tracks[(ch["target"]["node"], ch["target"]["path"])] = (t, v, smp.get("interpolation", "LINEAR"))
            times.update(np.round(t, 6).tolist())
        yield a, tracks, np.array(sorted(times))


def _pose(game: Rig, tracks, t) -> dict[int, np.ndarray]:
    local = {}
    animated = {k[0] for k in tracks}
    for i in animated:
        n = dict(game.nodes[i])
        for path in ("translation", "rotation", "scale"):
            tr = tracks.get((i, path))
            if tr is None:
                continue
            times, vals, interp = tr
            k = np.searchsorted(times, t, side="right") - 1
            if k < 0:
                v = vals[0]
            elif k >= len(times) - 1 or interp == "STEP":
                v = vals[min(k, len(vals) - 1)]
            else:
                u = (t - times[k]) / (times[k + 1] - times[k])
                a, b = vals[k], vals[k + 1]
                if path == "rotation" and np.dot(a, b) < 0:
                    b = -b
                v = a * (1 - u) + b * u
                if path == "rotation":
                    v = v / np.linalg.norm(v)
            n[path] = list(map(float, v))
            n.pop("matrix", None)
        local[i] = _trs(n)
    return _node_worlds(game.nodes, game.node_parent, local)


def _write_glb(joints, V, N, UV, weights, idx, image, anims, pelvis_name, weapon_bones) -> bytes:
    names = [j[0] for j in joints]
    index = {n: i for i, n in enumerate(names)}
    wpos = {n: p for n, _, p in joints}
    blobs, views, accs = [], [], []

    def add(raw):
        off = sum(len(x) for x in blobs)
        blobs.append(raw + b"\0" * (-len(raw) % 4))
        views.append({"buffer": 0, "byteOffset": off, "byteLength": len(raw)})
        return len(views) - 1

    def accessor(arr, ctype, typ, minmax=False):
        arr = np.ascontiguousarray(arr)
        a = {"bufferView": add(arr.tobytes()), "componentType": ctype, "count": len(arr), "type": typ}
        if minmax:
            flat = arr.reshape(len(arr), -1)
            a["min"] = flat.min(0).tolist()
            a["max"] = flat.max(0).tolist()
        accs.append(a)
        return len(accs) - 1

    nodes = []
    for n, p, pos in joints:
        node = {"name": n, "translation": [float(x) for x in (pos - (wpos[p] if p else 0))]}
        kids = [index[c] for c, pp, _ in joints if pp == n]
        if kids:
            node["children"] = kids
        nodes.append(node)
    J = np.zeros((len(V), 4), np.uint16)
    Wt = np.zeros((len(V), 4), np.float32)
    for v, d in enumerate(weights):
        items = sorted(d.items(), key=lambda kv: -kv[1])[:4]
        total = sum(w for _, w in items) or 1.0
        for slot, (bone, w) in enumerate(items):
            J[v, slot] = index[bone]
            Wt[v, slot] = w / total
    ibm = np.array([np.eye(4) for _ in names], np.float32)
    for i, n in enumerate(names):
        ibm[i][:3, 3] = -wpos[n]
    mesh_node = len(nodes)
    nodes.append({"name": "body", "mesh": 0, "skin": 0})
    gl_anims = []
    for a, times, frames, scales, hips in anims:
        channels, samplers = [], []
        tin = accessor(times.astype(np.float32), 5126, "SCALAR", True)
        for n in names:
            q = np.array(frames[n], np.float32)
            if np.allclose(np.abs(q[:, 3]), 1.0, atol=1e-6):
                continue
            samplers.append({"input": tin, "output": accessor(q, 5126, "VEC4"), "interpolation": "LINEAR"})
            channels.append({"sampler": len(samplers) - 1, "target": {"node": index[n], "path": "rotation"}})
        parent = next(p for n, p, _ in joints if n == pelvis_name)
        tr = (wpos[pelvis_name] - (wpos[parent] if parent else 0) + hips).astype(np.float32)
        samplers.append({"input": tin, "output": accessor(tr, 5126, "VEC3"), "interpolation": "LINEAR"})
        channels.append({"sampler": len(samplers) - 1, "target": {"node": index[pelvis_name], "path": "translation"}})
        for wb in sorted(weapon_bones):
            if wb in index and scales.get(wb):
                sv = np.repeat(np.array(scales[wb], np.float32)[:, None], 3, axis=1)
                samplers.append({"input": tin, "output": accessor(sv, 5126, "VEC3"), "interpolation": "LINEAR"})
                channels.append({"sampler": len(samplers) - 1, "target": {"node": index[wb], "path": "scale"}})
        entry = {"name": a.get("name", "animation"), "channels": channels, "samplers": samplers}
        if "extras" in a:
            entry["extras"] = a["extras"]
        gl_anims.append(entry)
    png = io.BytesIO()
    image.save(png, "PNG")
    pos = accessor(V.astype(np.float32), 5126, "VEC3", True)
    nor = accessor(N.astype(np.float32), 5126, "VEC3")
    uv = accessor(UV.astype(np.float32), 5126, "VEC2")
    jo = accessor(J, 5123, "VEC4")
    we = accessor(Wt, 5126, "VEC4")
    ind = accessor(np.asarray(idx, np.uint32), 5125, "SCALAR")
    ib = accessor(ibm.transpose(0, 2, 1).reshape(-1, 16), 5126, "MAT4")
    imgv = add(png.getvalue())
    doc = {
        "asset": {"version": "2.0", "generator": "fe_modding rig_fit"},
        "scene": 0,
        "scenes": [{"nodes": [0, mesh_node]}],
        "nodes": nodes,
        "skins": [{"joints": list(range(len(names))), "inverseBindMatrices": ib, "skeleton": 0}],
        "meshes": [{"name": "body", "primitives": [{"attributes": {"POSITION": pos, "NORMAL": nor, "TEXCOORD_0": uv,
                                                                   "JOINTS_0": jo, "WEIGHTS_0": we},
                                                    "indices": ind, "material": 0}]}],
        "materials": [{"name": "body", "pbrMetallicRoughness": {"baseColorTexture": {"index": 0}, "metallicFactor": 0,
                                                                  "roughnessFactor": 1}}],
        "textures": [{"source": 0, "sampler": 0}],
        "samplers": [{"magFilter": 9729, "minFilter": 9729, "wrapS": 10497, "wrapT": 10497}],
        "images": [{"bufferView": imgv, "mimeType": "image/png"}],
        "animations": gl_anims,
        "accessors": accs,
        "bufferViews": views,
        "buffers": [{"byteLength": sum(len(x) for x in blobs)}],
    }
    js = json.dumps(doc, separators=(",", ":")).encode()
    js += b" " * (-len(js) % 4)
    body = b"".join(blobs)
    out = struct.pack("<III", 0x46546C67, 2, 28 + len(js) + len(body))
    return out + struct.pack("<II", len(js), 0x4E4F534A) + js + struct.pack("<II", len(body), 0x004E4942) + body
