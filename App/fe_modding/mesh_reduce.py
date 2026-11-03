"""Reduce a glTF model's triangle count before it becomes a map model.

Vanilla map bodies (``ymu/<class>/body.gs``) have a median of 444
triangles and at most 853 (``gs_stats.MAP_BODY_LIMITS``). Models made for
other games or for PC run to thousands. :func:`reduce_glb` brings each mesh
down to a triangle budget and returns a new ``.glb`` with everything else
(skeleton, skin, animations, materials, textures) unchanged.

Method: edge collapses in order of quadric error (Garland-Heckbert), each
moving one vertex onto a neighbour (half-edge collapse) so that UVs,
normals and skin weights stay those of real vertices:

- vertices are welded by position, so a UV seam or a material border is an
  edge whose sides use different vertices; such edges, and open borders,
  add planes to the quadrics and may only be shortened along themselves
  (a seam vertex collapses onto the next seam vertex; seam corners stay),
  which keeps texture charts intact;
- a collapse between vertices with different skin weights costs extra, so
  joints keep the rings the skin bends at;
- a collapse is refused when it would fold a triangle over, pinch the
  surface (link condition) or move a locked vertex (the map weapon's).
"""

from __future__ import annotations

import heapq
import json
import struct
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import numpy as np

from .formats import gltf_import

_COMPONENT_FORMATS = {5120: "b", 5121: "B", 5122: "h", 5123: "H", 5125: "I", 5126: "f"}
_TYPE_SIZES = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4, "MAT4": 16}
_SEAM_WEIGHT = 8.0  # how strongly seam and border planes hold
_SKIN_WEIGHT = 1.0  # cost of merging differently weighted vertices, per unit of weight moved
_SEAM_BREAK = 4.0  # cost of stretching a texture chart, like the skin cost
_MIN_NORMAL_DOT = 0.2  # a collapse may not turn a triangle further than this


class MeshReduceError(Exception):
    pass


@dataclass
class ReduceResult:
    glb: bytes
    triangles_before: int
    triangles_after: int
    vertices_before: int
    vertices_after: int
    warnings: list[str] = field(default_factory=list)


# ---------------------------------------------------------------- simplification


def simplify(
    positions: np.ndarray,
    triangles: np.ndarray,
    target: int,
    *,
    weights: Optional[list[dict[int, float]]] = None,
    locked: Optional[np.ndarray] = None,
) -> tuple[np.ndarray, np.ndarray]:
    """Collapse edges until at most ``target`` triangles remain (or no
    collapse is allowed). ``positions`` is (n, 3), ``triangles`` (m, 3)
    vertex indices; ``weights`` one ``{joint: weight}`` per vertex;
    ``locked`` a boolean mask of vertices that may not move.

    Returns the kept triangles (indices into the original vertices) and the
    vertices' new positions (a vertex keeps its attributes but may have
    moved onto a neighbour's position)."""
    P = np.asarray(positions, np.float64).copy()
    tris = [tuple(int(x) for x in t) for t in np.asarray(triangles).reshape(-1, 3)]
    n = len(P)
    locked = np.zeros(n, bool) if locked is None else np.asarray(locked, bool)
    if len(tris) <= target or not tris:
        return np.array(tris, np.int64).reshape(-1, 3), P

    # weld by position: a group is one point of the surface
    extent = float(np.linalg.norm(P.max(0) - P.min(0))) or 1.0
    keys = np.round(P / (extent * 1e-6)).astype(np.int64)
    _uniq, group = np.unique(keys, axis=0, return_inverse=True)
    group = group.reshape(-1)
    gpos = np.zeros((group.max() + 1, 3))
    gpos[group] = P
    g_locked = np.zeros(len(gpos), bool)
    np.logical_or.at(g_locked, group, locked)
    alive = [True] * len(tris)
    corners: list[list[int]] = [list(t) for t in tris]
    g_tris: list[set[int]] = [set() for _ in range(len(gpos))]
    for t, tri in enumerate(corners):
        if len({group[v] for v in tri}) < 3:
            alive[t] = False
            continue
        for v in tri:
            g_tris[group[v]].add(t)

    def tgroups(t):
        return [group[v] for v in corners[t]]

    def normal(a, b, c):
        return np.cross(b - a, c - a)

    # quadrics
    Q = np.zeros((len(gpos), 4, 4))
    for t, tri in enumerate(corners):
        if not alive[t]:
            continue
        a, b, c = (gpos[group[v]] for v in tri)
        nv = normal(a, b, c)
        length = np.linalg.norm(nv)
        if length < 1e-12:
            continue
        nv /= length
        plane = np.append(nv, -nv @ a)
        K = np.outer(plane, plane) * (length / 2)
        for v in tri:
            Q[group[v]] += K

    def edge_sides(ga, gb):
        """The triangles on edge (ga, gb) and, for each, its (vertex at ga,
        vertex at gb) pair."""
        out = []
        for t in g_tris[ga] & g_tris[gb]:
            va = next(v for v in corners[t] if group[v] == ga)
            vb = next(v for v in corners[t] if group[v] == gb)
            out.append((t, va, vb))
        return out

    def is_border(ga, gb):
        sides = edge_sides(ga, gb)
        if len(sides) != 2:
            return True
        return (sides[0][1], sides[0][2]) != (sides[1][1], sides[1][2])

    def neighbours(g):
        return {h for t in g_tris[g] for h in tgroups(t)} - {g}

    def border_edges(g):
        return [h for h in neighbours(g) if is_border(g, h)]

    # seam and border planes: perpendicular to the face through the edge
    for g in range(len(gpos)):
        for h in border_edges(g):
            if h < g:
                continue
            for t, _va, _vb in edge_sides(g, h):
                a, b, c = (gpos[x] for x in tgroups(t))
                fn = normal(a, b, c)
                e = gpos[h] - gpos[g]
                pn = np.cross(e, fn)
                length = np.linalg.norm(pn)
                if length < 1e-12:
                    continue
                pn /= length
                plane = np.append(pn, -pn @ gpos[g])
                K = np.outer(plane, plane) * _SEAM_WEIGHT * float(e @ e)
                Q[g] += K
                Q[h] += K

    g_members: list[set[int]] = [set() for _ in range(len(gpos))]
    for t, tri in enumerate(corners):
        if alive[t]:
            for v in tri:
                g_members[group[v]].add(v)

    def breaks_seam(ga, gb) -> bool:
        """Whether collapsing ga onto gb leaves a texture chart or border
        stretched: ga is on a seam or border and gb is not the next vertex
        along it, or a chart at ga does not reach gb."""
        borders = border_edges(ga)
        if not borders:
            return len(g_members[ga]) > 1
        if len(borders) != 2 or gb not in borders:
            return True
        at_edge = {va for _t, va, _vb in edge_sides(ga, gb)}
        return bool(g_members[ga] - at_edge)

    def plan(ga, gb):
        """The vertex moves of collapsing ga onto gb, or None if refused."""
        if g_locked[ga]:
            return None
        sides = edge_sides(ga, gb)
        if not sides:
            return None
        # link condition: the groups next to both are the triangles' third corners
        thirds = {next(x for x in tgroups(t) if x not in (ga, gb)) for t, _, _ in sides}
        if neighbours(ga) & neighbours(gb) != thirds:
            return None
        partner: dict[int, int] = {}
        for _t, va, vb in sides:
            if partner.setdefault(va, vb) != vb:
                return None
        # no triangle folds over or collapses
        removed = {t for t, _, _ in sides}
        target = gpos[gb]
        for t in g_tris[ga] - removed:
            pts = [gpos[x] for x in tgroups(t)]
            before = normal(*pts)
            pts = [target if x == ga else gpos[x] for x in tgroups(t)]
            after = normal(*pts)
            lb, la = np.linalg.norm(before), np.linalg.norm(after)
            if la < 1e-12 or lb < 1e-12 or (before @ after) / (la * lb) < _MIN_NORMAL_DOT:
                return None
        return partner, removed

    def skin_cost(ga, gb):
        if weights is None:
            return 0.0
        va = next(iter(g_members[ga]))
        vb = next(iter(g_members[gb]))
        wa, wb = weights[va], weights[vb]
        diff = sum(abs(wa.get(j, 0.0) - wb.get(j, 0.0)) for j in set(wa) | set(wb))
        e = gpos[gb] - gpos[ga]
        return _SKIN_WEIGHT * diff * float(e @ e) * max(np.trace(Q[ga][:3, :3]), 1e-9)

    def cost(ga, gb):
        p = np.append(gpos[gb], 1.0)
        c = float(p @ Q[ga] @ p) + skin_cost(ga, gb)
        if breaks_seam(ga, gb):
            e = gpos[gb] - gpos[ga]
            c += _SEAM_BREAK * float(e @ e) * max(np.trace(Q[ga][:3, :3]), 1e-9)
        return c

    version = [0] * len(gpos)
    heap: list[tuple[float, int, int, int]] = []
    blocked: dict[int, set[int]] = {}  # collapses refused since the group last changed

    def push(g):
        version[g] += 1
        if g_locked[g] or not g_tris[g]:
            return
        skip = blocked.get(g, ())
        best = min(((cost(g, h), h) for h in neighbours(g) if h not in skip), default=None)
        if best is not None:
            heapq.heappush(heap, (best[0], g, best[1], version[g]))

    def collapse(ga, gb, partner, removed) -> int:
        for t in removed:
            alive[t] = False
            for v in corners[t]:
                g_tris[group[v]].discard(t)
        for t in list(g_tris[ga]):
            corners[t] = [partner.get(v, v) for v in corners[t]]
            g_tris[gb].add(t)
        g_tris[ga] = set()
        for v in g_members[ga] - set(partner):
            group[v] = gb
            P[v] = gpos[gb]
            g_members[gb].add(v)
        g_members[ga] = set()
        Q[gb] += Q[ga]
        version[ga] += 1
        for g in {gb} | neighbours(gb):
            blocked.pop(g, None)
            push(g)
        return len(removed)

    count = sum(alive)
    for g in range(len(gpos)):
        push(g)
    while count > target and heap:
        _c, ga, gb, ver = heapq.heappop(heap)
        if ver != version[ga] or not g_tris[ga] or not g_tris[gb]:
            continue
        step = plan(ga, gb)
        if step is None:
            blocked.setdefault(ga, set()).add(gb)
            push(ga)
            continue
        count -= collapse(ga, gb, *step)
    kept = np.array([corners[t] for t in range(len(corners)) if alive[t]], np.int64).reshape(-1, 3)
    return kept, P


# ---------------------------------------------------------------- glTF


def _glb_parts(data: bytes, base_dir: Optional[Path]) -> tuple[dict, list[bytes]]:
    d = gltf_import._Document(data, base_dir)
    return d.doc, d.buffers


def _element_bytes(doc: dict, buffers: list[bytes], index: int) -> tuple[list[bytes], int, str]:
    acc = doc["accessors"][index]
    if "sparse" in acc:
        raise MeshReduceError("Sparse accessors are not supported.")
    width = _TYPE_SIZES[acc["type"]]
    size = struct.calcsize("<" + _COMPONENT_FORMATS[acc["componentType"]] * width)
    if "bufferView" not in acc:
        return [b"\0" * size] * acc["count"], size, acc["type"]
    view = doc["bufferViews"][acc["bufferView"]]
    raw = buffers[view["buffer"]]
    start = view.get("byteOffset", 0) + acc.get("byteOffset", 0)
    stride = view.get("byteStride", 0) or size
    return [raw[start + i * stride : start + i * stride + size] for i in range(acc["count"])], size, acc["type"]


def _values(doc: dict, buffers: list[bytes], index: int) -> np.ndarray:
    acc = doc["accessors"][index]
    fmt = "<" + _COMPONENT_FORMATS[acc["componentType"]] * _TYPE_SIZES[acc["type"]]
    elems, _size, _t = _element_bytes(doc, buffers, index)
    return np.array([struct.unpack(fmt, e) for e in elems], np.float64)


def _primitive_triangles(doc: dict, buffers: list[bytes], prim: dict) -> np.ndarray:
    count = doc["accessors"][prim["attributes"]["POSITION"]]["count"]
    indices = [int(x) for x in _values(doc, buffers, prim["indices"])[:, 0]] if "indices" in prim else list(range(count))
    return np.array(gltf_import._triangle_indices(prim.get("mode", 4), indices), np.int64).reshape(-1, 3)


def glb_triangle_count(data: bytes, base_dir: Optional[Path] = None) -> int:
    """Triangles of every mesh a node uses (what an import would build)."""
    doc, buffers = _glb_parts(data, base_dir)
    used = {node["mesh"] for node in doc.get("nodes", []) if "mesh" in node}
    return sum(
        len(_primitive_triangles(doc, buffers, prim))
        for m in sorted(used)
        for prim in doc["meshes"][m]["primitives"]
        if prim.get("mode", 4) in (4, 5, 6)
    )


def _joint_names(doc: dict, mesh_index: int) -> Optional[list[str]]:
    for node in doc.get("nodes", []):
        if node.get("mesh") == mesh_index and "skin" in node:
            return [doc["nodes"][j].get("name", "") for j in doc["skins"][node["skin"]]["joints"]]
    return None


def reduce_glb(
    data: bytes,
    target_triangles: int,
    base_dir: Optional[Path] = None,
    *,
    locked_joints: set[str] = frozenset(),
) -> ReduceResult:
    """A copy of the glTF with its meshes reduced to about
    ``target_triangles`` triangles in total, shared between meshes in
    proportion to their size. Vertices mostly weighted to a joint named in
    ``locked_joints`` (or below one) are kept as they are."""
    doc, buffers = _glb_parts(data, base_dir)
    doc = json.loads(json.dumps(doc))
    warnings: list[str] = []
    used = sorted({node["mesh"] for node in doc.get("nodes", []) if "mesh" in node})

    # the parents of each node, to lock whole weapon sub-trees
    parent: dict[int, int] = {}
    for i, node in enumerate(doc.get("nodes", [])):
        for c in node.get("children", []):
            parent[c] = i
    locked_nodes = set()
    for i, node in enumerate(doc.get("nodes", [])):
        k = i
        while k is not None:
            if doc["nodes"][k].get("name") in locked_joints:
                locked_nodes.add(i)
                break
            k = parent.get(k)

    meshes = []
    for m in used:
        prims = []
        for p, prim in enumerate(doc["meshes"][m]["primitives"]):
            if prim.get("mode", 4) not in (4, 5, 6):
                continue
            if prim.get("targets"):
                warnings.append(f"Mesh {m} primitive {p} has morph targets: left as it is.")
                continue
            prims.append((p, prim, _primitive_triangles(doc, buffers, prim)))
        meshes.append((m, prims))
    before = sum(len(t) for _m, prims in meshes for _p, _prim, t in prims)
    vertices_before = sum(
        doc["accessors"][prim["attributes"]["POSITION"]]["count"] for _m, prims in meshes for _p, prim, _t in prims
    )
    if before <= target_triangles:
        return ReduceResult(data, before, before, vertices_before, vertices_before,
                            ["The model is already within the budget."])

    blobs: list[bytes] = []
    new_views: list[dict] = []
    new_accessors: list[dict] = []

    def add_accessor(template: dict, raw: bytes, count: int, **extra) -> int:
        blobs.append(raw + b"\0" * (-len(raw) % 4))
        new_views.append({"byteLength": len(raw)})
        acc = {k: v for k, v in template.items() if k not in ("bufferView", "byteOffset", "count", "min", "max", "sparse")}
        acc.update(count=count, **extra)
        acc["_view"] = len(new_views) - 1
        new_accessors.append(acc)
        return len(doc.get("accessors", [])) + len(new_accessors) - 1

    vertices_after = 0
    after = 0
    for m, prims in meshes:
        if not prims:
            continue
        names = _joint_names(doc, m)
        skin_nodes = None
        for node in doc["nodes"]:
            if node.get("mesh") == m and "skin" in node:
                skin_nodes = doc["skins"][node["skin"]]["joints"]
                break
        # one vertex list for the whole mesh, so material borders weld
        positions, weights, locked, tris, spans = [], [], [], [], []
        base = 0
        for p, prim, t in prims:
            attrs = prim["attributes"]
            if doc["accessors"][attrs["POSITION"]]["componentType"] != 5126:
                raise MeshReduceError("Only float vertex positions are supported.")
            pos = _values(doc, buffers, attrs["POSITION"])
            positions.append(pos)
            if "JOINTS_0" in attrs and "WEIGHTS_0" in attrs:
                J = _values(doc, buffers, attrs["JOINTS_0"]).astype(int)
                W = _values(doc, buffers, attrs["WEIGHTS_0"])
                wacc = doc["accessors"][attrs["WEIGHTS_0"]]
                if wacc.get("normalized") and wacc["componentType"] in (5121, 5123):
                    W = W / (255.0 if wacc["componentType"] == 5121 else 65535.0)
                for jr, wr in zip(J, W):
                    d: dict[int, float] = {}
                    for j, w in zip(jr, wr):
                        if w > 0:
                            d[int(j)] = d.get(int(j), 0.0) + float(w)
                    weights.append(d)
                    top = max(d, key=d.get) if d else None
                    locked.append(top is not None and skin_nodes is not None and skin_nodes[top] in locked_nodes)
            else:
                weights.extend({} for _ in range(len(pos)))
                locked.extend(False for _ in range(len(pos)))
            tris.append(t + base)
            spans.append((p, prim, base, len(pos), len(t)))
            base += len(pos)
        P = np.vstack(positions)
        T = np.vstack(tris)
        budget = max(1, round(target_triangles * len(T) / before))
        kept, moved = simplify(P, T, budget, weights=weights if names else None, locked=np.array(locked, bool))
        after += len(kept)
        if len(kept) > budget:
            warnings.append(
                f"Mesh {doc['meshes'][m].get('name', m)}: stopped at {len(kept)} triangles (asked {budget}); "
                "the remaining edges are texture seams, borders or would fold the surface."
            )
        # split the kept triangles back into their primitives
        owner = np.zeros(len(P), np.int64)
        for s, (_p, _prim, start, count, _n) in enumerate(spans):
            owner[start:start + count] = s
        for s, (p, prim, start, count, _n) in enumerate(spans):
            mine = kept[owner[kept[:, 0]] == s]
            used_v = np.unique(mine)
            remap = {int(v): i for i, v in enumerate(used_v)}
            local = [int(v) - start for v in used_v]
            vertices_after += len(local)
            new_attrs = {}
            for name, acc_index in prim["attributes"].items():
                template = doc["accessors"][acc_index]
                if name == "POSITION":
                    arr = moved[start:start + count][local].astype(np.float32)
                    new_attrs[name] = add_accessor(template, arr.tobytes(), len(local),
                                                   min=arr.min(0).tolist(), max=arr.max(0).tolist())
                    continue
                elems, _size, _typ = _element_bytes(doc, buffers, acc_index)
                new_attrs[name] = add_accessor(template, b"".join(elems[i] for i in local), len(local))
            flat = np.array([remap[int(v)] for v in mine.reshape(-1)], np.uint32)
            ctype = 5123 if len(local) < 65536 else 5125
            raw = flat.astype(np.uint16 if ctype == 5123 else np.uint32).tobytes()
            index_acc = add_accessor({"componentType": ctype, "type": "SCALAR"}, raw, len(flat))
            new_prim = dict(prim, attributes=new_attrs, indices=index_acc, mode=4)
            doc["meshes"][m]["primitives"][p] = new_prim

    glb = _write_glb(doc, buffers, blobs, new_views, new_accessors, base_dir)
    return ReduceResult(glb, before, after, vertices_before, vertices_after, warnings)


def _write_glb(doc, buffers, blobs, new_views, new_accessors, base_dir) -> bytes:
    """Everything in one binary chunk: the old buffers (images included),
    then the new accessors' data."""
    out = bytearray()
    starts = []
    for raw in buffers:
        starts.append(len(out))
        out += raw + b"\0" * (-len(raw) % 4)
    for view in doc.get("bufferViews", []):
        view["byteOffset"] = view.get("byteOffset", 0) + starts[view["buffer"]]
        view["buffer"] = 0
    for image in doc.get("images", []):
        if "uri" in image:
            raw = gltf_import._load_uri(image["uri"], base_dir)
            doc.setdefault("bufferViews", []).append({"buffer": 0, "byteOffset": len(out), "byteLength": len(raw)})
            out += raw + b"\0" * (-len(raw) % 4)
            image["bufferView"] = len(doc["bufferViews"]) - 1
            image.setdefault("mimeType", "image/jpeg" if image["uri"].lower().endswith((".jpg", ".jpeg")) else "image/png")
            del image["uri"]
    view_base = len(doc.get("bufferViews", []))
    for view, raw in zip(new_views, blobs):
        doc.setdefault("bufferViews", []).append({"buffer": 0, "byteOffset": len(out), "byteLength": view["byteLength"]})
        out += raw
    for acc in new_accessors:
        acc["bufferView"] = view_base + acc.pop("_view")
        doc.setdefault("accessors", []).append(acc)
    doc["buffers"] = [{"byteLength": len(out)}]
    js = json.dumps(doc, separators=(",", ":")).encode("utf-8")
    js += b" " * (-len(js) % 4)
    total = 12 + 8 + len(js) + 8 + len(out)
    return (struct.pack("<4sII", b"glTF", 2, total) + struct.pack("<I4s", len(js), b"JSON") + js
            + struct.pack("<I4s", len(out), b"BIN\0") + bytes(out))
