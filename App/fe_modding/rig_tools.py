"""Helpers that make skeletons easier to handle in the 3D Models page.

- **Mirroring a joint mapping** (:func:`mirror_mapping`): the Replace with my character
  mapping set on one side of the body is copied to the other. Mirrored
  joints are found by name (``Left``/``Right``, ``L``/``R``, ``hidari``/
  ``migi``...) or, failing that, by position (the joint nearest the
  mirrored position).
- **Skeleton outlines** (:func:`skeleton_outline`): joints projected on the
  front view, for the mapping dialog's two skeletons.
- **Anchor bones** (:func:`add_joints_to_glb`, :func:`anchor_offsets`):
  engine anchors (``_ex1_``, ``_s1_``, ``_sw1_``...) added to a rig kit
  ``.glb`` under a chosen bone, or copied from another set at the same
  place relative to their parent.
- **Rig check** (:func:`rig_check`): what the engine and the set's
  animations need from the skeleton, against what it has: anchors that a
  trail or a hand needs, anchors the vanilla set had, bone counts against
  the disc's largest models, map vertices blended between bones.
"""

from __future__ import annotations

import json
import re
import struct
from dataclasses import dataclass
from typing import Iterable, Optional

import numpy as np

from . import rig_contract
from .formats import animation, gs_stats, skeleton

# ---------------------------------------------------------------- mirroring

_WORD_PAIRS = (("Left", "Right"), ("left", "right"), ("LEFT", "RIGHT"), ("hidari", "migi"), ("Hidari", "Migi"),
               ("HIDARI", "MIGI"))
_LETTER_PAIRS = (("L", "R"), ("l", "r"))


def _swap_table() -> tuple[re.Pattern, dict[str, str]]:
    table: dict[str, str] = {}
    parts = []
    for a, b in _WORD_PAIRS:
        table[a], table[b] = b, a
        parts += [rf"(?<![a-z]){a}", rf"(?<![a-z]){b}"]
    for a, b in _LETTER_PAIRS:
        table[a], table[b] = b, a
        # a lone letter: not inside a word ("LeftFoot", "Lower"), but "L_arm", "hand.L", "Bip001 L Thigh"
        parts += [rf"(?<![A-Za-z]){a}(?![a-z])", rf"(?<![A-Za-z]){b}(?![a-z])"]
    return re.compile("|".join(parts)), table


_SWAP_RE, _SWAP = _swap_table()


def mirrored_names(name: str) -> list[str]:
    """Candidate names of the joint on the other side: every side token
    swapped, then each one alone (``L_arm`` -> ``R_arm``)."""
    out = []
    whole = _SWAP_RE.sub(lambda m: _SWAP[m.group(0)], name)
    if whole != name:
        out.append(whole)
    for m in _SWAP_RE.finditer(name):
        one = name[: m.start()] + _SWAP[m.group(0)] + name[m.end():]
        if one not in out and one != name:
            out.append(one)
    return out


def _name_twin(names: list[str], k: int) -> Optional[int]:
    index = {n: i for i, n in enumerate(names)}
    for candidate in mirrored_names(names[k]):
        if candidate in index:
            return index[candidate]
    return None


def _nearest_mirror(positions: np.ndarray, k: int, exclude: set[int]) -> tuple[Optional[int], float]:
    p = positions[k]
    target = np.array([-p[0], p[1], p[2]])
    d = np.linalg.norm(positions - target, axis=1)
    d[k] = np.inf
    for e in exclude:
        d[e] = np.inf
    best = int(d.argmin())
    return (best, float(d[best])) if np.isfinite(d[best]) else (None, np.inf)


def mirror_joint(names: list[str], positions: np.ndarray, k: int, tolerance: float) -> Optional[int]:
    """The joint mirroring joint ``k`` across the body's middle (x = 0):
    by name first; else, among joints with no name twin, the one nearest
    ``k``'s mirrored position within ``tolerance`` whose own nearest mirror
    is ``k`` (a pouch on one hip is not the other leg). A joint on the
    middle line is its own mirror."""
    twin = _name_twin(names, k)
    if twin is not None:
        return twin
    if abs(positions[k][0]) <= tolerance * 0.25:
        return k
    paired = {i for i in range(len(names)) if _name_twin(names, i) is not None}
    best, dist = _nearest_mirror(positions, k, paired)
    if best is None or dist > tolerance:
        return None
    back, _d = _nearest_mirror(positions, best, paired)
    return best if back == k else None


def _tolerance(positions: np.ndarray) -> float:
    if len(positions) == 0:
        return 1.0
    return max(float(np.ptp(positions[:, 1])), 1e-6) * 0.05


@dataclass
class MirrorResult:
    mapping: dict[str, str]
    changed: list[str]  # model joints whose entry changed
    unmatched: list[str]  # source-side joints with no mirror found (model or game)


def side_of(x: float, tolerance: float) -> str:
    return "left" if x > tolerance else "right" if x < -tolerance else "middle"


def mirror_mapping(model, game, mapping: dict[str, str], source: str = "left") -> MirrorResult:
    """Copy the mapping of the ``source`` side's model joints (``left``:
    +x, the character's left in glTF) to the other side: each mirrored
    model joint follows the mirror of the game bone its counterpart
    follows (a middle bone stays itself). ``model`` and ``game`` are
    :class:`rig_fit.Rig` (``names``, ``pos``)."""
    m_tol, g_tol = _tolerance(model.pos), _tolerance(game.pos)
    out = dict(mapping)
    changed, unmatched = [], []
    g_index = {n: i for i, n in enumerate(game.names)}
    for k, name in enumerate(model.names):
        if side_of(float(model.pos[k][0]), m_tol * 0.25) != source:
            continue
        twin = mirror_joint(model.names, model.pos, k, m_tol)
        if twin is None or twin == k:
            unmatched.append(name)
            continue
        target = mapping.get(name, "")
        mirrored = ""
        if target:
            g = g_index.get(target)
            if g is None:
                unmatched.append(name)
                continue
            gm = mirror_joint(game.names, game.pos, g, g_tol)
            if gm is None:
                unmatched.append(name)
                continue
            mirrored = game.names[gm]
        twin_name = model.names[twin]
        if out.get(twin_name, "") != mirrored:
            out[twin_name] = mirrored
            changed.append(twin_name)
    return MirrorResult(out, changed, unmatched)


# ---------------------------------------------------------------- outlines

@dataclass
class Outline:
    """A skeleton seen from the front, in 0..1 coordinates (y down)."""

    names: list[str]
    parent: list[int]
    points: list[tuple[float, float]]


def skeleton_outline(names: list[str], parent: list[int], positions: np.ndarray, *, margin: float = 0.05) -> Outline:
    """Joint positions projected on the front view, as seen facing the
    character (its left, +x, on the viewer's right), fitted into the unit
    square keeping proportions."""
    if len(positions) == 0:
        return Outline(list(names), list(parent), [])
    xs = positions[:, 0]
    ys = positions[:, 1]
    span = max(float(np.ptp(xs)), float(np.ptp(ys)), 1e-6)
    cx, cy = (xs.max() + xs.min()) / 2, (ys.max() + ys.min()) / 2
    scale = (1 - 2 * margin) / span
    pts = [(0.5 + (x - cx) * scale, 0.5 - (y - cy) * scale) for x, y in zip(xs, ys)]
    return Outline(list(names), list(parent), pts)


def deforming_joints(rig) -> dict[str, int]:
    """Vertices each joint carries most (its weight is the vertex's
    largest), for a :class:`rig_fit.Rig`."""
    if len(rig.J) == 0:
        return {}
    dominant = rig.J[np.arange(len(rig.J)), rig.W.argmax(1)]
    ids, counts = np.unique(dominant, return_counts=True)
    return {rig.names[int(i)]: int(c) for i, c in zip(ids, counts) if 0 <= int(i) < len(rig.names)}


def unmapped_deforming(rig, mapping: dict[str, str], min_share: float = 0.02) -> list[str]:
    """Model joints that carry at least ``min_share`` of the vertices
    while neither they nor any joint above them follows a game bone: they
    will not move at all."""
    carried = deforming_joints(rig)
    total = max(sum(carried.values()), 1)
    out = []
    for k, name in enumerate(rig.names):
        if carried.get(name, 0) / total < min_share or mapping.get(name):
            continue
        chain = [rig.names[a] for a in rig.ancestors(k)]
        if not any(mapping.get(a) for a in chain):
            out.append(name)
    return out


# ---------------------------------------------------------------- anchors

#: Map trail events and the anchor pair they draw between.
TRAIL_EVENTS = {0x14: "sw", 0x15: "sp", 0x16: "ax", 0x17: "bw", 0x18: "ex", 0x1A: "ja", 0x1B: "ha"}

#: Anchors a battle rig of the disc always has.
BATTLE_ANCHORS = ("_r_hand_", "_l_hand_", "_root_", "_cam_")
#: Anchors a map rig of the disc always has.
MAP_ANCHORS = ("_s1_", "_s2_")


def anchor_names() -> list[str]:
    """Every anchor name the engine looks for, for a choice list."""
    names = list(rig_contract.ANCHORS)
    for pair in TRAIL_EVENTS.values():
        names += [f"_{pair}1_", f"_{pair}2_"]
    names += ["_ar1_", "_ar2_"]
    return list(dict.fromkeys(names))


def describe_anchor(name: str) -> str:
    if name in rig_contract.ANCHORS:
        return rig_contract.ANCHORS[name]
    m = rig_contract.TRAIL_RE.match(name)
    if m:
        kind = {"sw": "sword", "sp": "lance", "ax": "axe", "bw": "bow", "ex": "spell", "ja": "javelin",
                "ha": "hand axe", "ar": "arrow"}[m.group(1)]
        return f"{kind} trail end (the trail is drawn between the 1 and 2 anchors)"
    return "anchor (found by name by the engine)"


@dataclass
class JointSpec:
    """A joint to add: ``position`` and ``rotation`` (3x3) in the kit's
    rest world space, under the joint ``parent``."""

    name: str
    parent: str
    position: tuple[float, float, float]
    rotation: Optional[np.ndarray] = None


def _split_glb(glb: bytes) -> tuple[dict, bytes]:
    if glb[:4] != b"glTF":
        raise ValueError("Not a binary glTF.")
    n = struct.unpack_from("<I", glb, 12)[0]
    doc = json.loads(glb[20:20 + n])
    rest = glb[20 + n:]
    body = b""
    if len(rest) >= 8:
        m = struct.unpack_from("<I", rest, 0)[0]
        body = rest[8:8 + m]
    return doc, body


def _join_glb(doc: dict, body: bytes) -> bytes:
    body = body + b"\0" * (-len(body) % 4)
    doc.setdefault("buffers", [{}])[0]["byteLength"] = len(body)
    js = json.dumps(doc, separators=(",", ":")).encode()
    js += b" " * (-len(js) % 4)
    total = 12 + 8 + len(js) + 8 + len(body)
    return (struct.pack("<III", 0x46546C67, 2, total) + struct.pack("<II", len(js), 0x4E4F534A) + js
            + struct.pack("<II", len(body), 0x004E4942) + body)


def _quat_matrix(q) -> np.ndarray:
    x, y, z, w = q
    return np.array([
        [1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
        [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
        [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)],
    ])


def _quat_from_matrix(m: np.ndarray) -> list[float]:
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
    return [float(v) for v in q]


def _local(node: dict) -> np.ndarray:
    if "matrix" in node:
        return np.array(node["matrix"], float).reshape(4, 4).T
    m = np.eye(4)
    m[:3, :3] = _quat_matrix(node.get("rotation", (0, 0, 0, 1))) * np.array(node.get("scale", (1, 1, 1)))
    m[:3, 3] = node.get("translation", (0, 0, 0))
    return m


def node_worlds(doc: dict) -> dict[int, np.ndarray]:
    nodes = doc.get("nodes", [])
    parent = {c: i for i, n in enumerate(nodes) for c in n.get("children", [])}
    world: dict[int, np.ndarray] = {}

    def w(i: int) -> np.ndarray:
        if i not in world:
            world[i] = (w(parent[i]) @ _local(nodes[i])) if i in parent else _local(nodes[i])
        return world[i]

    for i in range(len(nodes)):
        w(i)
    return world


def _skin(doc: dict) -> dict:
    skins = doc.get("skins", [])
    if not skins:
        raise ValueError("The model has no armature (glTF skin).")
    return max(skins, key=lambda s: len(s.get("joints", [])))


def glb_joints(glb: bytes) -> tuple[list[str], list[int], np.ndarray, np.ndarray]:
    """``(names, parent joint indices, rest world positions, rest world
    rotations)`` of a ``.glb``'s armature (its largest skin)."""
    doc, _body = _split_glb(glb)
    skin = _skin(doc)
    nodes = doc["nodes"]
    joints = list(skin["joints"])
    world = node_worlds(doc)
    parent_node = {c: i for i, n in enumerate(nodes) for c in n.get("children", [])}
    jset = {j: k for k, j in enumerate(joints)}

    def joint_parent(j: int) -> int:
        p = parent_node.get(j)
        while p is not None and p not in jset:
            p = parent_node.get(p)
        return jset[p] if p is not None else -1

    names = [nodes[j].get("name") or f"joint{k}" for k, j in enumerate(joints)]
    pos = np.array([world[j][:3, 3] for j in joints]) if joints else np.zeros((0, 3))
    rot = np.array([_orthonormal(world[j][:3, :3]) for j in joints]) if joints else np.zeros((0, 3, 3))
    return names, [joint_parent(j) for j in joints], pos, rot


def _orthonormal(m: np.ndarray) -> np.ndarray:
    u, _s, vt = np.linalg.svd(m)
    r = u @ vt
    if np.linalg.det(r) < 0:
        u[:, -1] *= -1
        r = u @ vt
    return r


def add_joints_to_glb(glb: bytes, joints: Iterable[JointSpec]) -> bytes:
    """The ``.glb`` with ``joints`` added to its armature, each under its
    ``parent`` joint (a joint added earlier in the list may be a parent).
    They get no animation track: they follow their parent in every
    animation. Refused when a name is taken or a parent is missing."""
    doc, body = _split_glb(glb)
    skin = _skin(doc)
    nodes = doc["nodes"]
    by_name = {nodes[j].get("name"): j for j in skin["joints"]}
    world = node_worlds(doc)
    ibm_rows: list[np.ndarray] = []
    if "inverseBindMatrices" in skin:
        acc = doc["accessors"][skin["inverseBindMatrices"]]
        view = doc["bufferViews"][acc["bufferView"]]
        start = view.get("byteOffset", 0) + acc.get("byteOffset", 0)
        old = np.frombuffer(body, "<f4", acc["count"] * 16, start).reshape(-1, 16)
        ibm_rows = [row.copy() for row in old]
    else:
        ibm_rows = [np.linalg.inv(world[j]).T.reshape(16).astype("<f4") for j in skin["joints"]]
    for spec in joints:
        if spec.name in by_name:
            raise ValueError(f"The skeleton already has a bone named {spec.name}.")
        if spec.parent not in by_name:
            raise ValueError(f"{spec.parent} is not a bone of this skeleton.")
        p = by_name[spec.parent]
        target = np.eye(4)
        target[:3, :3] = spec.rotation if spec.rotation is not None else _orthonormal(world[p][:3, :3])
        target[:3, 3] = spec.position
        local = np.linalg.inv(world[p]) @ target
        scale = np.linalg.norm(local[:3, :3], axis=0)
        rot = local[:3, :3] / np.where(scale > 1e-9, scale, 1.0)
        node = {"name": spec.name, "translation": [float(v) for v in local[:3, 3]],
                "rotation": _quat_from_matrix(_orthonormal(rot))}
        if not np.allclose(scale, 1.0, atol=1e-4):
            node["scale"] = [float(v) for v in scale]
        nodes.append(node)
        index = len(nodes) - 1
        nodes[p].setdefault("children", []).append(index)
        world[index] = world[p] @ _local(node)
        skin["joints"].append(index)
        by_name[spec.name] = index
        ibm_rows.append(np.linalg.inv(world[index]).T.reshape(16).astype("<f4"))
    raw = np.array(ibm_rows, "<f4").tobytes()
    body = body + b"\0" * (-len(body) % 4)
    doc.setdefault("bufferViews", []).append({"buffer": 0, "byteOffset": len(body), "byteLength": len(raw)})
    doc.setdefault("accessors", []).append({"bufferView": len(doc["bufferViews"]) - 1, "componentType": 5126,
                                            "count": len(ibm_rows), "type": "MAT4"})
    skin["inverseBindMatrices"] = len(doc["accessors"]) - 1
    return _join_glb(doc, body + raw)


@dataclass
class AnchorCopy:
    """An anchor of another set, placed on this one: ``parent`` is this
    set's bone it goes under (``""`` when no bone of that name exists),
    ``offset`` the world offset from that bone, scaled to this set. With
    no bone of the same name, ``parent`` is the bone nearest where the
    source parent stands, to check."""

    name: str
    source_parent: str
    parent: str
    offset: tuple[float, float, float]


def _height(names: list[str], positions: np.ndarray) -> float:
    """The body's height from its joints (anchors and carriers left out)."""
    body = [p for n, p in zip(names, positions) if not _is_anchor(n) and not n.startswith("carrier_")]
    return float(np.ptp(np.array(body)[:, 1])) if len(body) > 1 else 1.0


def anchor_offsets(source_glb: bytes, target_glb: bytes, names: Optional[Iterable[str]] = None,
                   bone_map: Optional[dict[str, str]] = None) -> list[AnchorCopy]:
    """The anchors of ``source_glb`` (all, or ``names``) for the set of
    ``target_glb``: under the bone of the same name when it has one, else
    the one ``bone_map`` pairs with the source parent (or its nearest
    paired ancestor: ``rig_fit.auto_mapping`` of the two bodies), else the
    nearest bone; at the source's offset scaled by the two skeletons'
    heights. Anchors the target already has are left out."""
    from . import animation_catalog
    s_names, s_parent, s_pos, _s_rot = glb_joints(source_glb)
    t_names, _t_parent, t_pos, _t_rot = glb_joints(target_glb)
    scale = _height(t_names, t_pos) / max(_height(s_names, s_pos), 1e-6)
    wanted = set(names) if names is not None else None
    renames = animation_catalog.bone_renames(s_names, set(t_names))
    out = []
    for k, name in enumerate(s_names):
        if not _is_anchor(name) or name in t_names or (wanted is not None and name not in wanted):
            continue
        p = s_parent[k]
        # an anchor hanging from a carrier bone (a fitted battle rig) is placed from the carrier's parent
        while p >= 0 and s_names[p].startswith("carrier_"):
            p = s_parent[p]
        source_parent = s_names[p] if p >= 0 else ""
        parent = renames.get(source_parent, source_parent) if source_parent else ""
        if parent not in t_names and p >= 0 and bone_map:
            for a in [p] + _ancestors(s_parent, p):
                if bone_map.get(s_names[a]) in t_names:
                    parent = bone_map[s_names[a]]
                    break
        if parent not in t_names and p >= 0:
            parent = _nearest_bone(s_pos[p], s_pos, t_names, t_pos, scale)
        offset = (s_pos[k] - s_pos[p]) * scale if p >= 0 else np.zeros(3)
        out.append(AnchorCopy(name, source_parent, parent, tuple(float(v) for v in offset)))
    return out


def _ancestors(parent: list[int], k: int) -> list[int]:
    out = []
    while parent[k] >= 0:
        k = parent[k]
        out.append(k)
    return out


def _nearest_bone(point: np.ndarray, s_pos: np.ndarray, t_names: list[str], t_pos: np.ndarray,
                  scale: float) -> str:
    """The target body bone nearest a source position, both skeletons
    standing on the ground and scaled to the same height."""
    s_base = np.array([0.0, s_pos[:, 1].min(), 0.0])
    t_base = np.array([0.0, t_pos[:, 1].min(), 0.0])
    where = t_base + (point - s_base) * scale
    best, best_d = "", np.inf
    for name, p in zip(t_names, t_pos):
        if _is_anchor(name) or name.startswith("carrier_"):
            continue
        d = float(np.linalg.norm(p - where))
        if d < best_d:
            best, best_d = name, d
    return best


def _is_anchor(name: str) -> bool:
    return len(name) > 2 and name.startswith("_") and name.endswith("_")


def anchor_joint_specs(target_glb: bytes, anchors: Iterable[tuple[str, str, tuple[float, float, float]]],
                       *, battle: bool) -> list[JointSpec]:
    """Joints for :func:`add_joints_to_glb`: each ``(name, parent,
    offset)`` at its parent's rest position plus ``offset``. On a battle
    rig an anchor sits on its parent, so an offset anchor hangs from a
    ``carrier<name>`` bone placed at the offset (as Replace with my character does)."""
    t_names, _t_parent, t_pos, _t_rot = glb_joints(target_glb)
    index = {n: i for i, n in enumerate(t_names)}
    specs: list[JointSpec] = []
    for name, parent, offset in anchors:
        if not _is_anchor(name):
            raise ValueError(f"{name}: an anchor name starts and ends with an underscore (_ex1_).")
        if parent not in index:
            raise ValueError(f"{name}: choose the bone it goes under.")
        position = t_pos[index[parent]] + np.asarray(offset, float)
        if battle and np.linalg.norm(np.asarray(offset, float)) > 1e-4:
            carrier = f"carrier{name}"
            specs.append(JointSpec(carrier, parent, tuple(position)))
            specs.append(JointSpec(name, carrier, tuple(position)))
        else:
            specs.append(JointSpec(name, parent, tuple(position)))
    return specs


def strip_animations(glb: bytes) -> bytes:
    """The ``.glb`` without its animations (their data stays in the buffer)."""
    doc, body = _split_glb(glb)
    doc.pop("animations", None)
    return _join_glb(doc, body)


# ---------------------------------------------------------------- rig check

@dataclass
class Finding:
    level: str  # "error": the game will misbehave; "warning": worth a look; "ok": fine
    text: str


def _event_codes(ga: bytes) -> set[int]:
    try:
        events = animation.read_animation_bytes(ga).events
    except Exception:  # noqa: BLE001 - an unreadable clip is reported elsewhere
        return set()
    return {c for e in events for c in e.codes}


def rig_check(
    bones: list[skeleton.Bone],
    animations: list[tuple[str, bytes]],
    *,
    battle: bool,
    body_gs: Optional[bytes] = None,
    reference_bones: Optional[list[skeleton.Bone]] = None,
) -> list[Finding]:
    """What the set's skeleton lacks or overdoes (see the module
    docstring). ``animations`` are ``(file, .ga bytes)``; ``reference_bones``
    the vanilla set's skeleton when there is one."""
    findings: list[Finding] = []
    names = [b.name for b in bones]
    have = set(names)
    anchors = [n for n in names if _is_anchor(n)]
    required = BATTLE_ANCHORS if battle else MAP_ANCHORS
    missing = [a for a in required if a not in have]
    if missing:
        findings.append(Finding("error", "Missing anchors every " + ("battle" if battle else "map")
                                + " model has: " + ", ".join(f"{a} ({describe_anchor(a)})" for a in missing)))
    if not battle:
        needs: dict[str, list[str]] = {}
        for file, data in animations:
            for code in _event_codes(data):
                pair = TRAIL_EVENTS.get(code)
                if pair:
                    needs.setdefault(pair, []).append(file)
        for pair, files in sorted(needs.items()):
            lacking = [a for a in (f"_{pair}1_", f"_{pair}2_") if a not in have]
            if lacking:
                shown = ", ".join(sorted(set(files))[:4]) + ("..." if len(set(files)) > 4 else "")
                findings.append(Finding(
                    "error",
                    f"{shown} start a {describe_anchor(lacking[0]).split(' (')[0]} but the skeleton lacks "
                    f"{', '.join(lacking)}: no trail or effect is drawn (Add anchor bone... can copy them from "
                    "a class that has them)."))
    if reference_bones is not None:
        ref = [b.name for b in reference_bones]
        lost = [n for n in ref if _is_anchor(n) and n not in have]
        if lost:
            findings.append(Finding("error", "Anchors the vanilla set had and this one lacks: " + ", ".join(lost)))
        if len(bones) != len(reference_bones):
            findings.append(Finding("ok" if len(bones) <= len(reference_bones) else "warning",
                                    f"{len(bones)} bones (the vanilla set has {len(reference_bones)})."))
    limits = gs_stats.BATTLE_BODY_LIMITS if battle else gs_stats.MAP_BODY_LIMITS
    if len(bones) > limits["bones_used"] and reference_bones is None:
        findings.append(Finding("warning", f"{len(bones)} bones: more than any {'battle' if battle else 'map'} model "
                                f"of the disc ({limits['bones_used']}). Untested, not a known limit."))
    if body_gs is not None:
        try:
            stats = gs_stats.model_stats(body_gs)
        except Exception:  # noqa: BLE001
            stats = None
        if stats is not None:
            if stats.bones_used > limits["bones_used"]:
                findings.append(Finding("warning", f"The body uses {stats.bones_used} bones: more than any "
                                        f"{'battle' if battle else 'map'} model of the disc ({limits['bones_used']})."))
            if not battle and (stats.blended_vertices or stats.composite_shapes):
                findings.append(Finding(
                    "error", f"{stats.blended_vertices} map vertices are blended between bones: every retail map "
                    "model has one bone per vertex, and the map renderer bends shared vertices wrongly "
                    "(Replace with my character gives each vertex its heaviest bone)."))
            if stats.triangles > limits["triangles"]:
                findings.append(Finding("warning", f"{stats.triangles:,} triangles: more than any "
                                        f"{'battle' if battle else 'map'} model of the disc ({limits['triangles']:,})."))
    for n in anchors:
        findings.append(Finding("ok", f"{n}: {describe_anchor(n)}"))
    if not any(f.level != "ok" for f in findings):
        findings.insert(0, Finding("ok", "Nothing missing: the anchors the engine and the animations use are there."))
    return findings
