"""Fit an imported terrain's playable area to the tile grid.

The game draws the move/attack grid and places units from ``map.bin``'s tile
corner heights, one flat panel per tile half; each tile is split along its
top-right/bottom-left diagonal (``(x+1, z)``-``(x, z+1)``). Vanilla terrains
follow the same panels: inside the playable area every triangle has its
corners on tile corners, and split tiles use that diagonal (1,083 of 1,098
diagonal edges on ``bmap07``). A mesh that bulges inside a tile shows
through the grid overlay, so :func:`conform_to_tiles` cuts the imported
triangles along the tile lines and diagonals of an area and moves every
vertex there onto its tile panel, whose corners are the surface heights at
the tile corners. UVs, normals and colours are interpolated along the cuts.
"""

from __future__ import annotations

import math

import numpy as np

from . import map_heights
from .formats.gltf_import import ImportedScene, ImportedTriangle

EPS = 1e-4


#: Height difference below which a triangle counts as flat and level with a panel.
FLAT = 0.01


def _lerp(a, b, t):
    return tuple(x + (y - x) * t for x, y in zip(a, b))


def _split(poly: list[dict], f) -> tuple[list[dict], list[dict]]:
    """Split a convex polygon by the line ``f(v) = 0`` into its ``<= 0`` and
    ``>= 0`` parts (vertices on the line go to both)."""
    below, above = [], []
    n = len(poly)
    for i in range(n):
        a, b = poly[i], poly[(i + 1) % n]
        fa, fb = f(a), f(b)
        if fa <= EPS:
            below.append(a)
        if fa >= -EPS:
            above.append(a)
        if (fa < -EPS and fb > EPS) or (fa > EPS and fb < -EPS):
            t = fa / (fa - fb)
            v = {key: (_lerp(a[key], b[key], t) if a[key] is not None else None) for key in a}
            below.append(v)
            above.append(v)
    return below, above


def _cut(poly: list[dict], lines) -> list[list[dict]]:
    pieces = [poly]
    for f in lines:
        nxt = []
        for p in pieces:
            lo, hi = _split(p, f)
            nxt += [q for q in (lo, hi) if len(q) >= 3]
        pieces = nxt
    return pieces


def _area_xz(p) -> float:
    return abs(sum(p[i]["pos"][0] * p[(i + 1) % len(p)]["pos"][2] - p[(i + 1) % len(p)]["pos"][0] * p[i]["pos"][2] for i in range(len(p)))) / 2


def _flat_on_panels(t: ImportedTriangle, corner, x0: float, z0: float, tile: float, nx: int, nz: int) -> bool:
    """A flat triangle whose every covered tile corner is at its height lies
    on the panels already: cutting it would change nothing."""
    ys = [p[1] for p in t.positions]
    if max(ys) - min(ys) > FLAT:
        return False
    xs = [p[0] for p in t.positions]
    zs = [p[2] for p in t.positions]
    i0 = max(math.floor((min(xs) - x0) / tile + EPS), 0)
    i1 = min(math.ceil((max(xs) - x0) / tile - EPS), nx)
    j0 = max(math.floor((min(zs) - z0) / tile + EPS), 0)
    j1 = min(math.ceil((max(zs) - z0) / tile - EPS), nz)
    block = corner[i0 : i1 + 1, j0 : j1 + 1]
    return bool(block.size) and not np.isnan(block).any() and float(np.max(np.abs(block - ys[0]))) <= FLAT


def conform_to_tiles(scene: ImportedScene, x0: float, x1: float, z0: float, z1: float, tile: float = 5.0) -> int:
    """Cut and flatten the scene's triangles over ``[x0, x1] x [z0, z1]``
    (whole tiles, in mesh coordinates) onto the tile panels. Returns how
    many triangles were cut."""
    nx, nz = round((x1 - x0) / tile), round((z1 - z0) / tile)
    all_tris = [t for tris in scene.triangles.values() for t in tris]
    if nx <= 0 or nz <= 0 or not all_tris:
        return 0
    surface = np.array([t.positions for t in all_tris], dtype=float)
    grid_points = [(x0 + tile * i, z0 + tile * j) for i in range(nx + 1) for j in range(nz + 1)]
    corner = map_heights.surface_heights(surface, grid_points).reshape(nx + 1, nz + 1)

    def panel_height(x: float, z: float):
        if not (x0 - EPS <= x <= x1 + EPS and z0 - EPS <= z <= z1 + EPS):
            return None
        i = min(max(int(math.floor((x - x0) / tile)), 0), nx - 1)
        j = min(max(int(math.floor((z - z0) / tile)), 0), nz - 1)
        u = min(max((x - x0) / tile - i, 0.0), 1.0)
        v = min(max((z - z0) / tile - j, 0.0), 1.0)
        tl, tr, bl, br = corner[i, j], corner[i + 1, j], corner[i, j + 1], corner[i + 1, j + 1]
        if u + v <= 1.0:
            h = tl + (tr - tl) * u + (bl - tl) * v
        else:
            h = br + (bl - br) * (1.0 - u) + (tr - br) * (1.0 - v)
        return None if math.isnan(h) else float(h)

    cut = 0
    for material, tris in scene.triangles.items():
        out: list[ImportedTriangle] = []
        for t in tris:
            xs = [p[0] for p in t.positions]
            zs = [p[2] for p in t.positions]
            if max(xs) <= x0 + EPS or min(xs) >= x1 - EPS or max(zs) <= z0 + EPS or min(zs) >= z1 - EPS:
                out.append(t)
                continue
            if _area_xz([{"pos": p} for p in t.positions]) < 1e-9 or _flat_on_panels(t, corner, x0, z0, tile, nx, nz):
                out.append(t)  # already level with every panel it covers (vanilla flat ground)
                continue
            lines = []
            for k in range(math.ceil((min(xs) - x0) / tile - EPS), math.floor((max(xs) - x0) / tile + EPS) + 1):
                if 0 <= k <= nx:
                    lines.append(lambda v, c=x0 + tile * k: v["pos"][0] - c)
            for k in range(math.ceil((min(zs) - z0) / tile - EPS), math.floor((max(zs) - z0) / tile + EPS) + 1):
                if 0 <= k <= nz:
                    lines.append(lambda v, c=z0 + tile * k: v["pos"][2] - c)
            lo = math.ceil((min(xs) + min(zs) - x0 - z0) / tile - EPS)
            hi = math.floor((max(xs) + max(zs) - x0 - z0) / tile + EPS)
            for k in range(lo, hi + 1):
                lines.append(lambda v, c=x0 + z0 + tile * k: v["pos"][0] + v["pos"][2] - c)
            poly = [
                {"pos": t.positions[k], "nrm": t.normals[k], "uv": t.uvs[k], "col": t.colors[k] if t.colors else None,
                 "uv2": t.uvs2[k] if t.uvs2 else None}
                for k in range(3)
            ]
            pieces = _cut(poly, lines)
            if len(pieces) > 1:
                cut += 1
            for piece in pieces:
                if _area_xz(piece) < 1e-6:
                    continue
                verts = []
                for v in piece:
                    x, y, z = v["pos"]
                    h = panel_height(x, z)
                    verts.append({**v, "pos": (x, y if h is None else h, z)})
                for k in range(1, len(verts) - 1):
                    a, b, c = verts[0], verts[k], verts[k + 1]
                    tri = [a, b, c]
                    if _area_xz(tri) < 1e-6:
                        continue
                    out.append(
                        ImportedTriangle(
                            positions=tuple(w["pos"] for w in tri),
                            normals=tuple(w["nrm"] for w in tri),
                            uvs=tuple(w["uv"] for w in tri),
                            colors=tuple(tuple(int(round(c_)) for c_ in w["col"]) for w in tri) if t.colors else None,
                            uvs2=tuple(w["uv2"] for w in tri) if t.uvs2 else None,
                        )
                    )
        scene.triangles[material] = out
    return cut
