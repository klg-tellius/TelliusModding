"""Shape FE9 map water: outline, shoreline fade, shore waves and flow.

The game draws a ``map_water`` surface from above (GRAPHICS_NOTES, "Map
water" -> Shader): its model's texture coordinates are never read, so only
the mesh's outline and height matter.

- Two layers of the first texture drift over each other, each repeating
  every 32 units and moved by its pair of scroll values, ``(u1, v1)`` and
  ``(u2, v2)`` times the map clock. Both drift *against* their values: the
  pattern moves by ``(-u, -v)`` tiles per clock unit along ``(x, z)``.
- The second texture is a 512 x 512 greyscale **shoreline fade** projected
  like the terrain mask (``u = x / 640``, ``v = z / 640``): it lightens the
  water and takes away its opacity. Vanilla images are 0.8 outside the
  water mesh; inside, most follow the water's depth over the terrain
  (about 0.6 at the waterline, 0.4 one unit deep, clear by five), so the
  mesh can run under the bank and melt into it. Maps whose riverbed is
  modelled flat (bmap07, bmap16) carry a hand-painted fade instead.
- The foam lapping at the shore is the ``wave_99`` prop, one instance per
  chosen tile, centred over water with its local +z pointing at the shore.

:func:`shoreline` cuts a water outline from a ground mesh at a water level,
:func:`shore_fade` builds the fade image for a set of water meshes,
:func:`wave_slots` lines shore waves up along it, and :func:`covered` /
:func:`covered_tiles` say which points and tiles a surface covers.

Pure numpy, without package imports: the Blender add-on ships a copy of
this file next to ``terrain_paint.py``. Images are numpy arrays with row 0
at ``z = 0``; mesh coordinates are the terrain's own (Y up, 5 units per
tile, tile ``(c, r)`` from ``x = 5 c``, ``z = 5 r``).
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

TILE = 5.0
#: World units the fade image covers from the terrain's corner, and its size.
FADE_SPAN = 640.0
FADE_SIZE = 512
#: Fade value over land (and everywhere outside the water meshes).
FADE_LAND = 0.8
#: Vanilla fade by water depth (surface minus ground, in units): the
#: median of bmap01/02/05/10/13/21/24 binned by the terrain under the water.
#: Above the waterline (negative depth) the bank stays faded out.
FADE_DEPTH = (-3.0, -2.0, -1.0, -0.5, 0.0, 0.5, 1.0, 1.5, 2.0, 3.0, 4.0, 5.0, 6.0)
FADE_BY_DEPTH = (0.73, 0.71, 0.68, 0.65, 0.59, 0.50, 0.40, 0.30, 0.22, 0.12, 0.05, 0.02, 0.0)
#: Taper by distance inside the mesh edge (image pixels), so an outline
#: that ends over deep water never shows a hard line.
FADE_EDGE_PX = (0.0, 1.0, 2.0, 3.0, 4.0, 5.0, 6.0)
FADE_BY_EDGE = (0.8, 0.6, 0.45, 0.3, 0.18, 0.08, 0.0)
#: Units the outline runs past the waterline, under the bank: the visible
#: shore (fade ~0.4) sits about 4 pixels, one tile, inside the mesh edge.
BANK_MARGIN = 5.0
#: Image pixels per world unit of the fade image.
FADE_SCALE = FADE_SIZE / FADE_SPAN
#: How far the strip of a ``wave_99`` sits above its instance origin.
WAVE_MODEL_Y = 1.0
#: Fade value of the visible shore line that waves face.
SHORE_FADE = 0.4
EPS = 1e-9


# ---------------------------------------------------------------- coverage


def _flat(tris) -> np.ndarray:
    tris = np.asarray(tris, float).reshape(-1, 3, 3)
    return tris


def covered(tris, x, z) -> np.ndarray:
    """Whether a triangle of ``tris`` (``(N, 3, 3)``) lies over each point
    ``(x, z)`` seen from above (edges count as covered)."""
    tris = _flat(tris)
    x = np.asarray(x, float)
    z = np.asarray(z, float)
    out = np.zeros(x.shape, bool)
    if not len(tris) or not x.size:
        return out
    fx, fz = x.ravel(), z.ravel()
    flat = out.ravel()
    for p in tris:
        ax, az = p[0, 0], p[0, 2]
        bx, bz = p[1, 0] - ax, p[1, 2] - az
        cx, cz = p[2, 0] - ax, p[2, 2] - az
        det = bx * cz - cx * bz
        if abs(det) < EPS:
            continue
        lo_x, hi_x = p[:, 0].min() - 1e-6, p[:, 0].max() + 1e-6
        lo_z, hi_z = p[:, 2].min() - 1e-6, p[:, 2].max() + 1e-6
        near = np.flatnonzero((fx >= lo_x) & (fx <= hi_x) & (fz >= lo_z) & (fz <= hi_z) & ~flat)
        if not len(near):
            continue
        px, pz = fx[near] - ax, fz[near] - az
        u = (px * cz - cx * pz) / det
        v = (bx * pz - px * bz) / det
        flat[near[(u >= -1e-6) & (v >= -1e-6) & (u + v <= 1 + 1e-6)]] = True
    return flat.reshape(x.shape)


def covered_tiles(tris, columns: int, rows: int, origin: tuple[int, int] = (0, 0)) -> np.ndarray:
    """``[column][row]`` grid of the tiles whose centre ``tris`` cover. Tile
    ``(c, r)`` is placement ``(c, r)`` and sits at mesh ``5 * (c - origin)``."""
    c, r = np.meshgrid(np.arange(columns), np.arange(rows), indexing="ij")
    return covered(tris, TILE * (c - origin[0]) + TILE / 2, TILE * (r - origin[1]) + TILE / 2)


def cover_grid(tris, size: int, span: float) -> np.ndarray:
    """``(size, size)`` top-down coverage of ``tris`` at the pixel centres
    of an image over ``span`` units (row 0 at ``z = 0``)."""
    out = np.zeros((size, size), bool)
    scale = size / span
    for p in _flat(tris):
        xs = p[:, 0] * scale - 0.5
        zs = p[:, 2] * scale - 0.5
        c0, c1 = max(math.ceil(xs.min() - 1e-6), 0), min(math.floor(xs.max() + 1e-6), size - 1)
        r0, r1 = max(math.ceil(zs.min() - 1e-6), 0), min(math.floor(zs.max() + 1e-6), size - 1)
        if c0 > c1 or r0 > r1:
            continue
        area = (xs[1] - xs[0]) * (zs[2] - zs[0]) - (xs[2] - xs[0]) * (zs[1] - zs[0])
        if abs(area) < 1e-12:
            continue
        gx, gz = np.meshgrid(np.arange(c0, c1 + 1, dtype=float), np.arange(r0, r1 + 1, dtype=float))
        w1 = ((gx - xs[0]) * (zs[2] - zs[0]) - (xs[2] - xs[0]) * (gz - zs[0])) / area
        w2 = ((xs[1] - xs[0]) * (gz - zs[0]) - (gx - xs[0]) * (zs[1] - zs[0])) / area
        out[r0:r1 + 1, c0:c1 + 1] |= (w1 >= -1e-6) & (w2 >= -1e-6) & (1.0 - w1 - w2 >= -1e-6)
    return out


# ---------------------------------------------------------------- outline


def outline_edges(tris, piece: float = 0.5) -> np.ndarray:
    """``(E, 2, 2)`` top-down ``(x, z)`` segments, at most ``piece`` units
    long, of the outline of the area ``tris`` cover: pieces of triangle
    edges with water on one side only. Shared edges, T-junctions and edges
    lying inside another triangle drop out."""
    tris = _flat(tris)
    if not len(tris):
        return np.zeros((0, 2, 2))
    keys: dict = {}
    for p in tris:
        q = p[:, [0, 2]]
        if abs((q[1, 0] - q[0, 0]) * (q[2, 1] - q[0, 1]) - (q[2, 0] - q[0, 0]) * (q[1, 1] - q[0, 1])) < EPS:
            continue
        for i in range(3):
            key = tuple(sorted((tuple(np.round(q[i], 4)), tuple(np.round(q[(i + 1) % 3], 4)))))
            keys[key] = keys.get(key, 0) + 1
    pieces = []
    for (a, b), n in keys.items():
        if n != 1:
            continue
        a, b = np.array(a), np.array(b)
        count = max(1, int(math.ceil(np.linalg.norm(b - a) / piece)))
        t = np.linspace(0.0, 1.0, count + 1)[:, None]
        points = a + (b - a) * t
        pieces.extend(np.stack([points[:-1], points[1:]], axis=1))
    edges = np.asarray(pieces, float).reshape(-1, 2, 2)
    if not len(edges):
        return edges
    # a piece is on the outline when one side of its midpoint is dry
    mid = edges.mean(axis=1)
    d = edges[:, 1] - edges[:, 0]
    normal = np.stack([-d[:, 1], d[:, 0]], axis=1) / np.maximum(np.linalg.norm(d, axis=1, keepdims=True), EPS)
    step = 1e-3
    left = covered(tris, mid[:, 0] + normal[:, 0] * step, mid[:, 1] + normal[:, 1] * step)
    right = covered(tris, mid[:, 0] - normal[:, 0] * step, mid[:, 1] - normal[:, 1] * step)
    return edges[left != right]


def edge_distance_grid(edges, size: int, span: float, reach: float) -> np.ndarray:
    """``(size, size)`` distance in units from each pixel centre to the
    nearest segment of ``edges``, capped at ``reach``."""
    best = np.full((size, size), float(reach))
    scale = size / span
    for (ax, az), (bx, bz) in np.asarray(edges, float):
        c0 = max(int(math.floor((min(ax, bx) - reach) * scale)), 0)
        c1 = min(int(math.ceil((max(ax, bx) + reach) * scale)), size - 1)
        r0 = max(int(math.floor((min(az, bz) - reach) * scale)), 0)
        r1 = min(int(math.ceil((max(az, bz) + reach) * scale)), size - 1)
        if c0 > c1 or r0 > r1:
            continue
        gx, gz = np.meshgrid((np.arange(c0, c1 + 1) + 0.5) / scale, (np.arange(r0, r1 + 1) + 0.5) / scale)
        dx, dz = bx - ax, bz - az
        length2 = dx * dx + dz * dz
        px, pz = gx - ax, gz - az
        t = np.clip((px * dx + pz * dz) / length2, 0.0, 1.0) if length2 > EPS else 0.0
        region = best[r0:r1 + 1, c0:c1 + 1]
        np.minimum(region, np.hypot(px - t * dx, pz - t * dz), out=region)
    return best


# ---------------------------------------------------------------- shoreline fade


def shore_fade(tris, ground_tris=None, *, depth_scale: float = 1.0, edge_width: float = 1.0,
               size: int = FADE_SIZE, span: float = FADE_SPAN) -> np.ndarray:
    """The ``size`` x ``size`` fade image (0..0.8, row 0 at ``z = 0``) for
    the water meshes ``tris`` (every water body of the map together: they
    share one image).

    ``FADE_LAND`` outside the water. Inside, the vanilla curve of water
    depth over ``ground_tris`` (shallows light and see-through, clear by
    about 5 units deep; ``depth_scale`` 2.0 fades over twice the depth),
    and at least the edge taper (``edge_width`` stretches it) so the
    outline never shows. Without ground, only the edge taper."""
    tris = _flat(tris)
    inside = cover_grid(tris, size, span)
    fade = np.full((size, size), FADE_LAND)
    if not inside.any():
        return fade
    px_per_unit = size / span
    reach = FADE_EDGE_PX[-1] * edge_width / px_per_unit
    dist = edge_distance_grid(outline_edges(tris), size, span, reach) * px_per_unit / edge_width
    value = np.interp(dist, FADE_EDGE_PX, FADE_BY_EDGE)
    if ground_tris is not None and len(_flat(ground_tris)):
        bounds = (0.0, 0.0, span, span)
        surface = ground_heights(tris, span / size, bounds)
        ground = ground_heights(ground_tris, span / size, bounds)
        depth = np.nan_to_num((surface - ground) / depth_scale, nan=np.inf)
        # past the terrain (a sea running to the map's edge) the water is open:
        # vanilla images are black there, with no fade along the mesh's border
        open_sea = np.isnan(ground)
        value = np.where(open_sea, 0.0, np.maximum(value, np.interp(depth, FADE_DEPTH, FADE_BY_DEPTH)))
        fade[open_sea & ~inside] = 0.0
    fade[inside] = value[inside]
    return fade


# ---------------------------------------------------------------- outline from ground


def ground_heights(tris, cell: float, bounds: tuple[float, float, float, float]) -> np.ndarray:
    """Highest ground height at the centre of each ``cell``-sized cell over
    ``bounds = (x0, z0, x1, z1)``: ``(rows, columns)``, ``nan`` without
    ground."""
    x0, z0, x1, z1 = bounds
    cols = max(1, int(math.ceil((x1 - x0) / cell - 1e-9)))
    rows = max(1, int(math.ceil((z1 - z0) / cell - 1e-9)))
    out = np.full((rows, cols), -np.inf)
    for p in _flat(tris):
        xs = (p[:, 0] - x0) / cell - 0.5
        zs = (p[:, 2] - z0) / cell - 0.5
        c0, c1 = max(math.ceil(xs.min() - 1e-9), 0), min(math.floor(xs.max() + 1e-9), cols - 1)
        r0, r1 = max(math.ceil(zs.min() - 1e-9), 0), min(math.floor(zs.max() + 1e-9), rows - 1)
        if c0 > c1 or r0 > r1:
            continue
        area = (xs[1] - xs[0]) * (zs[2] - zs[0]) - (xs[2] - xs[0]) * (zs[1] - zs[0])
        if abs(area) < 1e-12:
            continue
        gx, gz = np.meshgrid(np.arange(c0, c1 + 1, dtype=float), np.arange(r0, r1 + 1, dtype=float))
        w1 = ((gx - xs[0]) * (zs[2] - zs[0]) - (xs[2] - xs[0]) * (gz - zs[0])) / area
        w2 = ((xs[1] - xs[0]) * (gz - zs[0]) - (gx - xs[0]) * (zs[1] - zs[0])) / area
        w0 = 1.0 - w1 - w2
        inside = (w0 >= -1e-6) & (w1 >= -1e-6) & (w2 >= -1e-6)
        height = w0 * p[0, 1] + w1 * p[1, 1] + w2 * p[2, 1]
        region = out[r0:r1 + 1, c0:c1 + 1]
        np.maximum(region, np.where(inside, height, -np.inf), out=region)
    out[np.isneginf(out)] = np.nan
    return out


def _grow(mask: np.ndarray, steps: int, within: np.ndarray | None = None) -> np.ndarray:
    """Grow ``mask`` by ``steps`` cells (8-neighbourhood), optionally only
    into ``within``."""
    for _ in range(steps):
        g = mask.copy()
        g[1:] |= mask[:-1]
        g[:-1] |= mask[1:]
        g[:, 1:] |= mask[:, :-1]
        g[:, :-1] |= mask[:, 1:]
        g[1:, 1:] |= mask[:-1, :-1]
        g[:-1, :-1] |= mask[1:, 1:]
        g[1:, :-1] |= mask[:-1, 1:]
        g[:-1, 1:] |= mask[1:, :-1]
        if within is not None:
            g &= within
        if (g == mask).all():
            return g
        mask = g
    return mask


def _rectangles(mask: np.ndarray) -> list[tuple[int, int, int, int]]:
    """Cover ``mask`` with rectangles ``(row0, col0, row1, col1)`` (end
    exclusive): runs per row, merged down while identical."""
    open_runs: dict[tuple[int, int], int] = {}
    out = []
    rows = mask.shape[0]
    for r in range(rows + 1):
        runs = set()
        if r < rows:
            line = np.concatenate([[False], mask[r], [False]]).astype(np.int8)
            d = np.diff(line)
            runs = set(zip(np.flatnonzero(d == 1).tolist(), np.flatnonzero(d == -1).tolist()))
        for run in list(open_runs):
            if run not in runs:
                out.append((open_runs.pop(run), run[0], r, run[1]))
        for run in runs:
            open_runs.setdefault(run, r)
    return out


def shoreline(
    ground_tris,
    level: float,
    *,
    margin: float = BANK_MARGIN,
    cell: float = 1.25,
    bounds: tuple[float, float, float, float] | None = None,
    seeds=None,
    fill_empty: bool = False,
    fill_area: tuple[float, float, float, float] | None = None,
) -> np.ndarray:
    """A flat water surface at height ``level`` over the ground of
    ``ground_tris`` that lies below it, as up-facing triangles
    (``(N, 3, 3)``, normal +Y).

    The wet area is found on a grid of ``cell`` units, grown by ``margin``
    units so the edge hides under the bank (the shoreline fade makes it
    transparent there), and covered with merged rectangles: the outline is a
    staircase of ``cell`` steps, invisible under the fade. ``seeds`` (``(x,
    z)`` points) keep only the wet regions containing one, so a hollow in
    the hills does not fill; ``fill_empty`` counts cells with no ground as
    wet (open sea past the terrain's edge), only inside ``fill_area`` ``(x0,
    z0, x1, z1)`` when given."""
    tris = _flat(ground_tris)
    if bounds is None:
        if not len(tris):
            raise ValueError("No ground to cut a shoreline from.")
        bounds = (tris[..., 0].min(), tris[..., 2].min(), tris[..., 0].max(), tris[..., 2].max())
    x0, z0 = bounds[0], bounds[1]
    heights = ground_heights(tris, cell, bounds)
    empty = np.isnan(heights)
    fillable = np.full(empty.shape, fill_empty)
    if fill_empty and fill_area is not None:
        rows, cols = empty.shape
        cx = x0 + (np.arange(cols) + 0.5) * cell
        cz = z0 + (np.arange(rows) + 0.5) * cell
        fillable = ((cz[:, None] >= fill_area[1]) & (cz[:, None] <= fill_area[3])
                    & (cx[None, :] >= fill_area[0]) & (cx[None, :] <= fill_area[2]))
    wet = np.where(empty, fillable, heights < level)
    if seeds is not None:
        start = np.zeros_like(wet)
        for sx, sz in seeds:
            c, r = int((sx - x0) // cell), int((sz - z0) // cell)
            if 0 <= r < wet.shape[0] and 0 <= c < wet.shape[1] and wet[r, c]:
                start[r, c] = True
        wet = _grow(start, wet.size, wet)
    wet = _grow(wet, int(round(margin / cell)), ~empty | wet)
    out = []
    for r0, c0, r1, c1 in _rectangles(wet):
        ax, az = x0 + c0 * cell, z0 + r0 * cell
        bx, bz = x0 + c1 * cell, z0 + r1 * cell
        a, b, c, d = (ax, level, az), (bx, level, az), (bx, level, bz), (ax, level, bz)
        # (x, z) counter-clockwise seen from +Y: a -> d -> c, a -> c -> b
        out.append((a, d, c))
        out.append((a, c, b))
    return np.asarray(out, float).reshape(-1, 3, 3)


# ---------------------------------------------------------------- shore waves


@dataclass
class WaveSlot:
    """One shore wave: placement tile ``(column, row)`` in mesh tiles (add
    the terrain origin for ``mapbuildinst``), the instance angle byte, and
    the direction the wave runs toward the shore (unit ``(x, z)``)."""

    column: int
    row: int
    angle: int
    direction: tuple[float, float]


def wave_angle(dx: float, dz: float) -> int:
    """Instance angle byte that turns a ``wave_99`` so its local +z (the way
    the foam runs) points along ``(dx, dz)``: the engine's turn is
    ``360 - angle * 360 / 256`` degrees and local +z ends up at
    ``(sin, cos)`` of it."""
    degrees = math.degrees(math.atan2(dx, dz))
    return int(round(-degrees * 256.0 / 360.0)) % 256


def wave_direction(angle: int) -> tuple[float, float]:
    """The ``(x, z)`` direction a ``wave_99`` with this angle byte runs."""
    radians = math.radians(360.0 - (angle % 256) * 360.0 / 256.0)
    return math.sin(radians), math.cos(radians)


def wave_height(level: float, lift: float = 0.5) -> float:
    """``mapbuildinst`` height that floats a ``wave_99`` strip ``lift``
    units above water at ``level`` (the engine places it at ``-5 * height``
    and the strip is ``WAVE_MODEL_Y`` above that)."""
    return -(level + lift - WAVE_MODEL_Y) / TILE


def fade_at(fade: np.ndarray, x, z, span: float = FADE_SPAN) -> np.ndarray:
    """Nearest pixel of a fade image at mesh ``(x, z)``."""
    size = fade.shape[0]
    px = np.clip((np.asarray(x, float) / span * size).astype(int), 0, size - 1)
    pz = np.clip((np.asarray(z, float) / span * size).astype(int), 0, size - 1)
    return fade[pz, px]


def shore_direction(fade: np.ndarray, x, z, span: float = FADE_SPAN):
    """``(dx, dz, slope)``: the unit way up the fade at mesh ``(x, z)``, toward
    the bank, where a shore wave should run; ``slope`` near 0 means open
    water or dry land, with no shore to face."""
    x = np.asarray(x, float)
    z = np.asarray(z, float)
    gx = fade_at(fade, x + 1.25, z, span) - fade_at(fade, x - 1.25, z, span)
    gz = fade_at(fade, x, z + 1.25, span) - fade_at(fade, x, z - 1.25, span)
    norm = np.hypot(gx, gz)
    return gx / np.maximum(norm, 1e-9), gz / np.maximum(norm, 1e-9), norm


#: Where vanilla shore waves sit: the visible shore (fade ``SHORE_FADE``)
#: lies this many units ahead of the tile centre, along the wave.
WAVE_SHORE_AHEAD = (-1.5, 3.5)


def wave_slots(fade: np.ndarray, *, ahead: tuple[float, float] = WAVE_SHORE_AHEAD, keep: float = 1.0,
               span: float = FADE_SPAN, seed: int = 0) -> list[WaveSlot]:
    """Shore waves along a fade image, one file of tiles following the
    shore: every tile whose centre is over water and sees the visible shore
    (the fade crossing ``SHORE_FADE``) between ``ahead[0]`` and ``ahead[1]``
    units in front of it, up the fade's slope, turned to face it. Vanilla
    waves sit this way (bmap02/10/12/13/24); ``keep`` thins the line, the
    same tiles every time for one ``seed``."""
    tiles = int(span // TILE)
    c, r = np.meshgrid(np.arange(tiles), np.arange(tiles), indexing="ij")
    cx, cz = (c + 0.5) * TILE, (r + 0.5) * TILE

    def at(x, z):
        return fade_at(fade, x, z, span)

    ux, uz, norm = shore_direction(fade, cx, cz, span)
    candidates = (at(cx, cz) < FADE_LAND - 0.05) & (norm > 1e-3)
    # first step along the slope where the shore shows
    reach = np.full(candidates.shape, np.inf)
    for s in np.arange(ahead[0] - 0.5, ahead[1] + 0.5, 0.5)[::-1]:
        reach = np.where(at(cx + ux * s, cz + uz * s) >= SHORE_FADE, s, reach)
    candidates &= (reach >= ahead[0]) & (reach < ahead[1])
    rng = np.random.default_rng(seed)
    candidates &= rng.random(candidates.shape) < keep
    return [WaveSlot(int(i), int(j), wave_angle(ux[i, j], uz[i, j]), (float(ux[i, j]), float(uz[i, j])))
            for i, j in zip(*np.nonzero(candidates))]


# ---------------------------------------------------------------- flow


def flow_from_scroll(scroll) -> tuple[tuple[float, float], tuple[float, float]]:
    """The way each water layer's pattern moves, ``((dx1, dz1), (dx2,
    dz2))`` in tiles per map clock unit along mesh ``(x, z)``: the shader
    adds ``u * t`` to the texture coordinate, so the pattern drifts by
    ``-u``."""
    u1, v1, u2, v2 = scroll
    return (-u1, -v1), (-u2, -v2)


def scroll_from_flow(layer1, layer2) -> tuple[float, float, float, float]:
    """The ``.ga`` scroll table for two layer drift vectors (inverse of
    :func:`flow_from_scroll`), rounded to the table's 0.001 steps."""
    values = (-layer1[0], -layer1[1], -layer2[0], -layer2[1])
    return tuple(round(v, 3) + 0.0 for v in values)


def polar(vector) -> tuple[float, float]:
    """``(direction degrees, speed)`` of a drift vector; 0 degrees runs
    along +x (east), 90 along +z (south, down the map)."""
    dx, dz = vector
    return math.degrees(math.atan2(dz, dx)) % 360.0, math.hypot(dx, dz)


def from_polar(degrees: float, speed: float) -> tuple[float, float]:
    radians = math.radians(degrees)
    return speed * math.cos(radians), speed * math.sin(radians)
