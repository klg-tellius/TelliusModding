"""Paint FE9 map terrain with its atlas: painted layers -> the game's blend.

The game draws ``map_base`` terrain as

    colour = lerp(atlas(UV0), atlas(UV1), mask(x / 640, z / 640)) * light

(GRAPHICS_NOTES, "Keeping the road/shore texturing"). On outdoor maps the
atlas holds tileable *swatches*: one 512x512 ground image in its top half
and smaller ones (road, cobbles, flowers, rocks...) in its bottom half.
Vanilla terrains lay both UV sets down from above at 6.4 texels per unit
(``u = x * 6.4``, ``v = z * 6.4`` texels, phase 0), each triangle wrapped
into its own swatch, so the mesh is cut on every swatch repeat line.

A painter wants more than two textures and soft brushes, so this module
works with *layers*: layer 0 is the base ground, every other layer a weight
image (0..1) over the same 640 x 640 units as the mask, composited in order
like image-editor layers. :func:`compile_paint` turns layers into what the
game can draw: per triangle a UV0 swatch (normally the base) and a UV1
swatch (the strongest other layer), planar UVs, and the mask. Where three
layers overlap only two can show; the result reports those spots.
:func:`decompile` goes the other way, so a vanilla map opens as layers.

Pure numpy, without package imports: the Blender add-on ships a copy of
this file (Blender bundles numpy, not PIL). Images are numpy arrays with
row 0 at ``z = 0``, the TPL/PIL top-left convention; mesh coordinates are
the terrain's own (Y up, 5 units per tile).
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from typing import Optional

import numpy as np

#: Atlas texels per world unit of vanilla terrain UVs (both UV sets).
DENSITY = 6.4
#: World units the mask covers from the terrain's corner (u = x / 640).
MASK_SPAN = 640.0
MASK_SIZE = 512
#: Faces steeper than this get a side projection instead of the top-down one.
SLOPE_DEGREES = 50.0
#: Share of a point's painted look that the two drawn layers may lose
#: before the point counts as a conflict.
CONFLICT_LOSS = 0.25
#: UVs stay half a texel inside their swatch so filtering never reads the
#: neighbouring swatch (vanilla keeps about one texel).
INSET = 0.5
EPS = 1e-6


# ---------------------------------------------------------------- data


@dataclass
class Swatch:
    """A tileable rectangle of the atlas, in texels from its top-left."""

    name: str
    x: int
    y: int
    w: int
    h: int

    def to_dict(self) -> dict:
        return {"name": self.name, "x": self.x, "y": self.y, "w": self.w, "h": self.h}

    @classmethod
    def from_dict(cls, data: dict) -> "Swatch":
        return cls(str(data["name"]), int(data["x"]), int(data["y"]), int(data["w"]), int(data["h"]))

    def contains(self, tx: float, ty: float) -> bool:
        return self.x <= tx <= self.x + self.w and self.y <= ty <= self.y + self.h


@dataclass
class AtlasLayout:
    """The swatches of one atlas; ``base`` is the ground swatch's index."""

    width: int
    height: int
    swatches: list[Swatch] = field(default_factory=list)
    base: int = 0
    density: float = DENSITY

    def to_json(self) -> str:
        return json.dumps(
            {
                "width": self.width, "height": self.height, "density": self.density, "base": self.base,
                "swatches": [s.to_dict() for s in self.swatches],
            },
            indent=1,
        )

    @classmethod
    def from_json(cls, text: str) -> "AtlasLayout":
        data = json.loads(text)
        layout = cls(
            int(data["width"]), int(data["height"]), [Swatch.from_dict(s) for s in data["swatches"]],
            int(data.get("base", 0)), float(data.get("density", DENSITY)),
        )
        layout.validate()
        return layout

    def validate(self) -> None:
        if not self.swatches:
            raise ValueError("The atlas has no swatches.")
        if not 0 <= self.base < len(self.swatches):
            raise ValueError("The base swatch is not one of the swatches.")
        for s in self.swatches:
            if s.w < 8 or s.h < 8 or s.x < 0 or s.y < 0 or s.x + s.w > self.width or s.y + s.h > self.height:
                raise ValueError(f"Swatch {s.name} ({s.x}, {s.y}, {s.w}x{s.h}) does not fit the "
                                 f"{self.width}x{self.height} atlas.")

    def swatch_at(self, tx: float, ty: float) -> int:
        """Index of the smallest swatch holding texel ``(tx, ty)``, else the nearest one."""
        inside = [i for i, s in enumerate(self.swatches) if s.contains(tx, ty)]
        if inside:
            return min(inside, key=lambda i: self.swatches[i].w * self.swatches[i].h)

        def distance(s: Swatch) -> float:
            dx = max(s.x - tx, 0.0, tx - s.x - s.w)
            dy = max(s.y - ty, 0.0, ty - s.y - s.h)
            return dx * dx + dy * dy

        return min(range(len(self.swatches)), key=lambda i: distance(self.swatches[i]))


@dataclass
class Layer:
    """A painted layer: which swatch it shows and where (``weights``, a
    square float image over :data:`MASK_SPAN` units). Layer 0 is the base
    ground and shows wherever the layers above leave room; its weights are
    ignored. ``slopes`` layers cover steep faces (cliffs) on their own."""

    name: str
    swatch: int
    weights: Optional[np.ndarray] = None
    slopes: bool = False


@dataclass
class CompileResult:
    positions: np.ndarray  # (n, 3, 3) after the seam cuts
    attrs: dict  # name -> (n, 3, k) interpolated along the cuts
    uv0: np.ndarray  # (n, 3, 2) atlas UVs, 0..1 from the top-left
    uv1: np.ndarray
    pairs: np.ndarray  # (n, 2) swatch of UV0 and UV1 per triangle
    mask: np.ndarray  # (MASK_SIZE, MASK_SIZE) uint8, white shows UV1
    conflicts: np.ndarray  # (MASK_SIZE, MASK_SIZE) bool, look the two layers cannot show
    steep: np.ndarray  # (n,) bool, side-projected triangles
    triangles_before: int = 0

    @property
    def conflict_share(self) -> float:
        return float(self.conflicts.mean())

    def report(self, layout: AtlasLayout) -> list[str]:
        lines = [
            f"{len(self.positions):,} triangles after cutting on the swatch repeat lines "
            f"(from {self.triangles_before:,}).",
        ]
        used = {}
        for a, b in self.pairs:
            for s in {int(a), int(b)}:
                used[s] = used.get(s, 0) + 1
        names = ", ".join(f"{layout.swatches[s].name} ({n:,})" for s, n in sorted(used.items(), key=lambda kv: -kv[1]))
        lines.append(f"Swatches drawn (triangles): {names}.")
        if self.steep.any():
            lines.append(f"{int(self.steep.sum()):,} steep triangles use a side projection.")
        share = self.conflict_share
        if share > 0:
            lines.append(
                f"{share:.1%} of the mask area shows only two of three or more painted layers "
                "(conflicts); paint the base between two detail layers or simplify the overlap."
            )
        return lines


# ---------------------------------------------------------------- geometry


def triangle_normals(positions: np.ndarray) -> np.ndarray:
    n = np.cross(positions[:, 1] - positions[:, 0], positions[:, 2] - positions[:, 0])
    length = np.linalg.norm(n, axis=1, keepdims=True)
    return n / np.maximum(length, 1e-12)


def _split(points: np.ndarray, attrs: list[np.ndarray], axis: int, value: float):
    """Split one triangle by the plane ``coord[axis] = value``; triangles
    keep their winding."""
    d = points[:, axis] - value
    below: list = []
    above: list = []
    for i in range(3):
        j = (i + 1) % 3
        corner = (points[i], [a[i] for a in attrs])
        if d[i] <= 0:
            below.append(corner)
        if d[i] >= 0:
            above.append(corner)
        if (d[i] < 0 < d[j]) or (d[j] < 0 < d[i]):
            t = d[i] / (d[i] - d[j])
            cut = (points[i] + (points[j] - points[i]) * t, [a[i] + (a[j] - a[i]) * t for a in attrs])
            below.append(cut)
            above.append(cut)
    out = []
    for poly in (below, above):
        for k in range(1, len(poly) - 1):
            out.append((poly[0], poly[k], poly[k + 1]))
    return out


def cut_planes(positions: np.ndarray, attrs: dict, axis: int, values, only: Optional[np.ndarray] = None):
    """Cut every triangle crossing one of the planes ``coord[axis] = v``
    (with ``only``, just those triangles). Returns new positions, attrs,
    and the index of each new triangle's source triangle."""
    names = list(attrs)
    origin = np.arange(len(positions))
    for value in values:
        coords = positions[:, :, axis]
        crossing = (coords.min(axis=1) < value - 1e-7) & (coords.max(axis=1) > value + 1e-7)
        if only is not None:
            crossing &= only[origin]
        hit = np.flatnonzero(crossing)
        if not len(hit):
            continue
        new_pos, new_attr, new_origin = [], {n: [] for n in names}, []
        for t in hit:
            for tri in _split(positions[t], [attrs[n][t] for n in names], axis, value):
                if np.linalg.norm(np.cross(tri[1][0] - tri[0][0], tri[2][0] - tri[0][0])) < 1e-9:
                    continue
                new_pos.append([c[0] for c in tri])
                for k, n in enumerate(names):
                    new_attr[n].append([c[1][k] for c in tri])
                new_origin.append(origin[t])
        keep = np.ones(len(positions), bool)
        keep[hit] = False
        positions = np.concatenate([positions[keep], np.asarray(new_pos, float).reshape(-1, 3, 3)])
        attrs = {
            n: np.concatenate([attrs[n][keep], np.asarray(new_attr[n], float).reshape(-1, 3, attrs[n].shape[2])])
            for n in names
        }
        origin = np.concatenate([origin[keep], np.asarray(new_origin, int)])
    return positions, attrs, origin


def _period_lines(lo: float, hi: float, period: float) -> np.ndarray:
    first = math.ceil(lo / period - 1e-9)
    last = math.floor(hi / period + 1e-9)
    return np.arange(first, last + 1) * period


def rasterize_top(positions: np.ndarray, size: int, span: float = MASK_SPAN,
                  select: Optional[np.ndarray] = None) -> tuple[np.ndarray, np.ndarray]:
    """Top-down raster of ``size`` x ``size`` pixels over ``span`` units:
    the index of the highest triangle over each pixel centre (-1 for none)
    and its height there."""
    ids = np.full((size, size), -1, np.int32)
    depth = np.full((size, size), -np.inf)
    scale = size / span
    indices = np.flatnonzero(select) if select is not None else range(len(positions))
    for t in indices:
        p = positions[t]
        xs = p[:, 0] * scale - 0.5
        zs = p[:, 2] * scale - 0.5
        x0, x1 = max(math.ceil(xs.min()), 0), min(math.floor(xs.max()), size - 1)
        z0, z1 = max(math.ceil(zs.min()), 0), min(math.floor(zs.max()), size - 1)
        if x0 > x1 or z0 > z1:
            continue
        gx, gz = np.meshgrid(np.arange(x0, x1 + 1, dtype=float), np.arange(z0, z1 + 1, dtype=float))
        area = (xs[1] - xs[0]) * (zs[2] - zs[0]) - (xs[2] - xs[0]) * (zs[1] - zs[0])
        if abs(area) < 1e-12:
            continue
        w1 = ((gx - xs[0]) * (zs[2] - zs[0]) - (xs[2] - xs[0]) * (gz - zs[0])) / area
        w2 = ((xs[1] - xs[0]) * (gz - zs[0]) - (gx - xs[0]) * (zs[1] - zs[0])) / area
        w0 = 1.0 - w1 - w2
        inside = (w0 >= -1e-9) & (w1 >= -1e-9) & (w2 >= -1e-9)
        if not inside.any():
            continue
        height = w0 * p[0, 1] + w1 * p[1, 1] + w2 * p[2, 1]
        region_ids = ids[z0:z1 + 1, x0:x1 + 1]
        region_depth = depth[z0:z1 + 1, x0:x1 + 1]
        better = inside & (height > region_depth)
        region_ids[better] = t
        region_depth[better] = height[better]
    return ids, depth


def pixel_centres(size: int, span: float = MASK_SPAN) -> tuple[np.ndarray, np.ndarray]:
    step = span / size
    axis = (np.arange(size) + 0.5) * step
    x, z = np.meshgrid(axis, axis)
    return x, z


# ---------------------------------------------------------------- layers


def sample(image: np.ndarray, x: np.ndarray, z: np.ndarray, span: float = MASK_SPAN) -> np.ndarray:
    """Bilinear, repeating sample of a square float image at mesh ``(x, z)``."""
    size_z, size_x = image.shape[:2]
    fx = np.asarray(x, float) / span * size_x - 0.5
    fz = np.asarray(z, float) / span * size_z - 0.5
    x0 = np.floor(fx).astype(np.int64)
    z0 = np.floor(fz).astype(np.int64)
    tx, tz = fx - x0, fz - z0
    xa, xb = np.mod(x0, size_x), np.mod(x0 + 1, size_x)
    za, zb = np.mod(z0, size_z), np.mod(z0 + 1, size_z)
    return ((image[za, xa] * (1 - tx) + image[za, xb] * tx) * (1 - tz)
            + (image[zb, xa] * (1 - tx) + image[zb, xb] * tx) * tz)


def visibility(layers: list[Layer], x: np.ndarray, z: np.ndarray, span: float = MASK_SPAN) -> np.ndarray:
    """How much of each layer shows at each point: ``(len(layers), *x.shape)``.
    Layers composite in order over the base; the shares sum to 1."""
    alpha = [np.zeros(np.shape(x))]
    for layer in layers[1:]:
        alpha.append(np.clip(sample(layer.weights, x, z, span), 0.0, 1.0) if layer.weights is not None
                     else np.zeros(np.shape(x)))
    alpha[0] = np.ones(np.shape(x))
    out = np.empty((len(layers), *np.shape(x)))
    covered = np.ones(np.shape(x))  # what the layers above leave visible
    for k in range(len(layers) - 1, -1, -1):
        out[k] = alpha[k] * covered
        covered = covered * (1.0 - alpha[k])
    return out


def _swatch_periods(layout: AtlasLayout, used) -> tuple[float, float]:
    widths = [layout.swatches[s].w for s in used]
    heights = [layout.swatches[s].h for s in used]
    return math.gcd(*widths) / layout.density, math.gcd(*heights) / layout.density


def planar_uvs(positions: np.ndarray, swatches: np.ndarray, layout: AtlasLayout,
               steep: np.ndarray) -> np.ndarray:
    """UVs laying each triangle's swatch on it at the atlas density: from
    above, or for ``steep`` triangles from the side they face. Each triangle
    wraps into its swatch by its centre's repeat; the mesh must already be
    cut on the repeat lines."""
    normals = triangle_normals(positions)
    centre = positions.mean(axis=1)
    h = np.empty(positions.shape[:2])
    v = np.empty(positions.shape[:2])
    hc = np.empty(len(positions))
    vc = np.empty(len(positions))
    flat = ~steep
    h[flat], v[flat] = positions[flat, :, 0], positions[flat, :, 2]
    hc[flat], vc[flat] = centre[flat, 0], centre[flat, 2]
    side_x = steep & (np.abs(normals[:, 0]) >= np.abs(normals[:, 2]))
    side_z = steep & ~side_x
    # facing +x the viewer's right is -z; facing +z it is +x (not mirrored)
    sx = np.where(normals[:, 0] > 0, -1.0, 1.0)[:, None]
    sz = np.where(normals[:, 2] > 0, 1.0, -1.0)[:, None]
    h[side_x] = (positions[:, :, 2] * sx)[side_x]
    h[side_z] = (positions[:, :, 0] * sz)[side_z]
    v[steep] = -positions[steep, :, 1]
    hc[side_x] = (centre[:, 2] * sx[:, 0])[side_x]
    hc[side_z] = (centre[:, 0] * sz[:, 0])[side_z]
    vc[steep] = -centre[steep, 1]

    rects = np.array([[s.x, s.y, s.w, s.h] for s in layout.swatches], float)[swatches]
    d = layout.density
    ku = np.floor(hc * d / rects[:, 2])
    kv = np.floor(vc * d / rects[:, 3])
    lu = np.clip(h * d - (ku * rects[:, 2])[:, None], 0.0, rects[:, 2:3])
    lv = np.clip(v * d - (kv * rects[:, 3])[:, None], 0.0, rects[:, 3:4])
    lu = INSET + lu * (rects[:, 2:3] - 2 * INSET) / rects[:, 2:3]
    lv = INSET + lv * (rects[:, 3:4] - 2 * INSET) / rects[:, 3:4]
    u = (rects[:, 0:1] + lu) / layout.width
    vv = (rects[:, 1:2] + lv) / layout.height
    return np.stack([u, vv], axis=-1)


def _steep(positions: np.ndarray, slope_degrees: float) -> np.ndarray:
    return np.abs(triangle_normals(positions)[:, 1]) < math.cos(math.radians(slope_degrees))


# ---------------------------------------------------------------- compile


def repeat_periods(layout: AtlasLayout, swatches) -> tuple[float, float]:
    """Units between the x and the z lines the mesh is cut on for these
    swatches (and the base)."""
    return _swatch_periods(layout, sorted(set(swatches) | {layout.base}))


def drawn_swatches(layers: list[Layer]) -> list[int]:
    """Swatches a compile can draw: the base, every layer with paint, and
    cliff layers. An empty layer adds no repeat lines to cut."""
    used = {layers[0].swatch}
    for layer in layers[1:]:
        if layer.slopes or (layer.weights is not None and float(np.max(layer.weights)) > 1e-3):
            used.add(layer.swatch)
    return sorted(used)


def layer_reach(positions: np.ndarray, layers: list[Layer], steep: np.ndarray,
                span: float = MASK_SPAN) -> np.ndarray:
    """``(n, len(layers))`` bool: the layers that can show anywhere on each
    triangle. The base always can; a painted layer where any weight pixel a
    bilinear sample inside the triangle's footprint reads is painted; a
    slopes layer on steep triangles. A triangle only needs cutting on the
    repeat lines of these layers' swatches."""
    positions = np.asarray(positions, float).reshape(-1, 3, 3)
    reach = np.zeros((len(positions), len(layers)), bool)
    reach[:, 0] = True
    lo = positions.min(axis=1)
    hi = positions.max(axis=1)
    for k, layer in enumerate(layers[1:], 1):
        if layer.slopes:
            reach[steep, k] = True
        if layer.weights is None:
            continue
        painted = np.asarray(layer.weights) > 1e-3
        if not painted.any():
            continue
        size_z, size_x = painted.shape
        # pixels a sample may read (see :func:`sample`), on a 2x2 tiling so
        # wrapped ranges stay contiguous; counted with an integral image
        tiled = np.zeros((2 * size_z + 1, 2 * size_x + 1), np.int64)
        tiled[1:, 1:] = np.tile(painted, (2, 2)).cumsum(axis=0).cumsum(axis=1)
        x0 = np.floor(lo[:, 0] / span * size_x - 0.5).astype(np.int64)
        x1 = np.floor(hi[:, 0] / span * size_x - 0.5).astype(np.int64) + 1
        z0 = np.floor(lo[:, 2] / span * size_z - 0.5).astype(np.int64)
        z1 = np.floor(hi[:, 2] / span * size_z - 0.5).astype(np.int64) + 1
        wide = (x1 - x0 + 1 >= size_x) | (z1 - z0 + 1 >= size_z)
        xa, za = np.mod(x0, size_x), np.mod(z0, size_z)
        xb = np.where(wide, xa, xa + x1 - x0 + 1)
        zb = np.where(wide, za, za + z1 - z0 + 1)
        count = tiled[zb, xb] - tiled[za, xb] - tiled[zb, xa] + tiled[za, xa]
        reach[:, k] |= wide | (count > 0)
    return reach


def seam_cut(positions: np.ndarray, layers: list[Layer], layout: AtlasLayout, attrs: Optional[dict] = None, *,
             slope_degrees: float = SLOPE_DEGREES, span: float = MASK_SPAN
             ) -> tuple[np.ndarray, dict, np.ndarray, np.ndarray]:
    """Cut each triangle on the repeat lines of the swatches that can show
    on it (:func:`layer_reach`): x and z lines everywhere, height lines
    through steep triangles. A small swatch only adds its lines where it is
    painted, not over the whole map. Returns positions, attrs, which
    triangles are steep and the layer reach of each cut triangle."""
    positions = np.asarray(positions, float).reshape(-1, 3, 3)
    attrs = {k: np.asarray(v, float) for k, v in (attrs or {}).items()}
    steep = _steep(positions, slope_degrees)
    reach = layer_reach(positions, layers, steep, span)
    widths = np.array([layout.swatches[layer.swatch].w for layer in layers])
    heights = np.array([layout.swatches[layer.swatch].h for layer in layers])
    period_x = np.gcd.reduce(np.where(reach, widths, 0), axis=1) / layout.density
    period_z = np.gcd.reduce(np.where(reach, heights, 0), axis=1) / layout.density
    # sides were cut on x/z lines already, which also bound their horizontal repeat
    period_y = np.where(steep, np.minimum(period_x, period_z), 0.0)
    origin = np.arange(len(positions))
    for axis, periods in ((0, period_x), (2, period_z), (1, period_y)):
        for period in np.unique(periods[periods > 0]):
            group = periods[origin] == period
            if not group.any():
                continue
            coords = positions[group][:, :, axis]
            lines = _period_lines(coords.min(), coords.max(), period)
            positions, attrs, cut_origin = cut_planes(positions, attrs, axis, lines, only=group)
            origin = origin[cut_origin]
    return positions, attrs, steep[origin], reach[origin]


def compile_paint(
    positions: np.ndarray,
    layers: list[Layer],
    layout: AtlasLayout,
    attrs: Optional[dict] = None,
    *,
    slope_degrees: float = SLOPE_DEGREES,
    mask_size: int = MASK_SIZE,
    span: float = MASK_SPAN,
) -> CompileResult:
    """Turn painted layers into the game's two-sample terrain (see the
    module docstring). ``positions`` is ``(n, 3, 3)`` in the terrain's own
    coordinates; ``attrs`` (normals, colours...) are cut with it."""
    if not layers:
        raise ValueError("There are no layers to compile.")
    layout.validate()
    positions = np.asarray(positions, float).reshape(-1, 3, 3)
    before = len(positions)
    positions, attrs, steep, reach = seam_cut(positions, layers, layout, attrs,
                                              slope_degrees=slope_degrees, span=span)

    n = len(positions)
    # each triangle's layer shares: its corners, edge midpoints and centre
    corners = positions
    mids = (positions + np.roll(positions, -1, axis=1)) / 2
    centre = positions.mean(axis=1, keepdims=True)
    points = np.concatenate([corners, mids, centre], axis=1)  # (n, 7, 3)
    share = visibility(layers, points[:, :, 0], points[:, :, 2], span).mean(axis=2)  # (L, n)

    # a triangle only draws layers whose repeat lines it was cut on
    share = np.where(reach.T, share, -1.0)
    base_layer = 0
    detail = share.copy()
    detail[base_layer] = -1.0
    strongest = detail.argmax(axis=0)
    strongest_share = detail.max(axis=0)
    first = np.full(n, base_layer)
    second = np.where(strongest_share > 1e-3, strongest, base_layer)
    # where the base hardly shows, the two strongest detail layers are drawn
    no_base = share[base_layer] < 0.05
    if len(layers) > 2 and no_base.any():
        runner = detail.copy()
        runner[strongest, np.arange(n)] = -1.0
        runner_layer = runner.argmax(axis=0)
        use = no_base & (runner.max(axis=0) > 1e-3)
        # the lower layer of the two is UV0, the upper one UV1
        first = np.where(use, np.minimum(runner_layer, strongest), first)
        second = np.where(use, np.maximum(runner_layer, strongest), second)
    slope_layers = [k for k, layer in enumerate(layers) if layer.slopes]
    if steep.any():
        if slope_layers:
            pick = np.array(slope_layers)[share[slope_layers][:, steep].argmax(axis=0)] if len(slope_layers) > 1 \
                else np.full(int(steep.sum()), slope_layers[0])
        else:
            pick = share[:, steep].argmax(axis=0)
        first[steep] = pick
        second[steep] = pick

    layer_swatch = np.array([layer.swatch for layer in layers])
    pairs = np.stack([layer_swatch[first], layer_swatch[second]], axis=1)
    uv0 = planar_uvs(positions, pairs[:, 0], layout, steep)
    uv1 = planar_uvs(positions, pairs[:, 1], layout, steep)

    # the mask: per pixel, the share of the triangle's UV1 layer
    ids, _ = rasterize_top(positions, mask_size, span, select=~steep)
    px, pz = pixel_centres(mask_size, span)
    vis = visibility(layers, px, pz, span)
    covered = 1.0 - vis[base_layer]
    mask = covered.copy()
    conflicts = np.zeros((mask_size, mask_size), bool)
    hit = ids >= 0
    if hit.any():
        tri = ids[hit]
        a, b = first[tri], second[tri]
        rows = np.flatnonzero(hit.ravel())
        flat_vis = vis.reshape(len(layers), -1)
        va = flat_vis[a, rows]
        vb = flat_vis[b, rows]
        two = a != b
        value = np.where(two, vb / np.maximum(va + vb, EPS), covered.ravel()[rows])
        value = np.where(two | (b != base_layer), value, 0.0)
        mask.ravel()[rows] = value
        lost = 1.0 - va - np.where(two, vb, 0.0)
        conflicts.ravel()[rows] = lost > CONFLICT_LOSS
    mask_u8 = np.clip(np.rint(mask * 255.0), 0, 255).astype(np.uint8)
    for name, values in list(attrs.items()):
        if name == "normals":
            attrs[name] = values / np.maximum(np.linalg.norm(values, axis=2, keepdims=True), 1e-12)
    return CompileResult(positions, attrs, uv0, uv1, pairs, mask_u8, conflicts, steep, before)


# ---------------------------------------------------------------- decompile


def triangle_swatches(uvs: np.ndarray, layout: AtlasLayout) -> np.ndarray:
    """The swatch each triangle's UVs fall in (by their centre)."""
    centre = np.asarray(uvs, float).reshape(-1, 3, 2).mean(axis=1)
    tx = np.mod(centre[:, 0], 1.0) * layout.width
    ty = np.mod(centre[:, 1], 1.0) * layout.height
    cache: dict = {}
    out = np.empty(len(centre), int)
    for i, key in enumerate(zip(np.floor(tx).astype(int), np.floor(ty).astype(int))):
        if key not in cache:
            cache[key] = layout.swatch_at(key[0] + 0.5, key[1] + 0.5)
        out[i] = cache[key]
    return out


def decompile(
    positions: np.ndarray,
    uv0: np.ndarray,
    uv1: np.ndarray,
    mask: np.ndarray,
    layout: AtlasLayout,
    resolution: int = 1024,
    span: float = MASK_SPAN,
) -> list[Layer]:
    """Layers that reproduce an existing terrain: the base, then one layer
    per other swatch the terrain draws, weighted by the mask where the
    swatch is UV1 (or fully where it is UV0)."""
    positions = np.asarray(positions, float).reshape(-1, 3, 3)
    s0 = triangle_swatches(uv0, layout)
    s1 = triangle_swatches(uv1, layout)
    ids, _ = rasterize_top(positions, resolution, span)
    px, pz = pixel_centres(resolution, span)
    m = sample(np.asarray(mask, float) / 255.0, px, pz, span)
    hit = ids >= 0
    tri = np.where(hit, ids, 0)
    a, b = np.where(hit, s0[tri], layout.base), np.where(hit, s1[tri], layout.base)
    m = np.where(a == b, 0.0, m)

    counts: dict[int, float] = {}
    for s in np.concatenate([a[a != layout.base], b[b != layout.base]]):
        counts[int(s)] = counts.get(int(s), 0) + 1
    # rarer swatches (roads, flowers) composite above common ones (rock, sand)
    order = sorted(counts, key=lambda s: -counts[s])
    layers = [Layer(layout.swatches[layout.base].name, layout.base)]
    for s in order:
        weight = np.where(b == s, m, 0.0) + np.where(a == s, 1.0, 0.0)
        layers.append(Layer(layout.swatches[s].name, s, np.clip(weight, 0.0, 1.0).astype(np.float32)))
    return layers


# ---------------------------------------------------------------- swatches


def _uv_charts(positions: np.ndarray, uvs: np.ndarray) -> np.ndarray:
    """Chart id per triangle: triangles sharing a mesh edge with the same
    UVs at both ends are one chart (a swatch repeat seam breaks charts)."""
    n = len(positions)
    parent = np.arange(n)

    def find(i):
        root = i
        while parent[root] != root:
            root = parent[root]
        while parent[i] != root:
            parent[i], i = root, parent[i]
        return root

    keys = np.round(positions * 1000).astype(np.int64)
    edges: dict = {}
    for t in range(n):
        for i in range(3):
            j = (i + 1) % 3
            a, b = tuple(keys[t, i]), tuple(keys[t, j])
            ua, ub = uvs[t, i], uvs[t, j]
            if b < a:
                a, b, ua, ub = b, a, ub, ua
            for other, oa, ob in edges.get((a, b), ()):
                if np.abs(oa - ua).max() < 1e-3 and np.abs(ob - ub).max() < 1e-3:
                    ra, rb = find(t), find(other)
                    if ra != rb:
                        parent[rb] = ra
            edges.setdefault((a, b), []).append((t, ua, ub))
    return np.array([find(i) for i in range(n)])


def detect_swatches(positions: np.ndarray, uv_sets, width: int, height: int,
                    snap: int = 16) -> list[tuple[int, int, int, int]]:
    """Swatch rectangles ``(x, y, w, h)`` the given triangle UVs wrap into.
    Each UV chart's texel rectangle is rounded to ``snap`` texels and
    overlapping rectangles merge; neighbouring swatches only touch."""
    positions = np.asarray(positions, float).reshape(-1, 3, 3)
    rects = set()
    for uvs in uv_sets:
        uvs = np.asarray(uvs, float).reshape(-1, 3, 2)
        if not len(uvs):
            continue
        charts = _uv_charts(positions, uvs)
        texels = uvs * (width, height)
        order = np.argsort(charts, kind="stable")
        bounds = np.flatnonzero(np.diff(charts[order])) + 1
        for group in np.split(order, bounds):
            lo = texels[group].reshape(-1, 2).min(axis=0)
            hi = texels[group].reshape(-1, 2).max(axis=0)
            if lo.min() < -0.5 or hi[0] > width + 0.5 or hi[1] > height + 0.5:
                continue
            x0, y0 = (np.round(lo / snap) * snap).astype(int)
            x1, y1 = (np.round(hi / snap) * snap).astype(int)
            x1, y1 = max(x1, x0 + snap), max(y1, y0 + snap)
            x0, y0 = max(x0, 0), max(y0, 0)
            x1, y1 = min(x1, width), min(y1, height)
            # UVs exactly on the right/bottom edge (commonly repeated-wrap
            # endpoints) used to produce zero-width/height rectangles. Those
            # are not atlas regions and poisoned the inferred unused grid.
            if x1 > x0 and y1 > y0:
                rects.add((x0, y0, x1, y1))
    boxes = sorted(rects)
    merged = True
    while merged:
        merged = False
        out: list = []
        for box in boxes:
            for k, other in enumerate(out):
                if box[0] < other[2] and other[0] < box[2] and box[1] < other[3] and other[1] < box[3]:
                    out[k] = (min(box[0], other[0]), min(box[1], other[1]), max(box[2], other[2]),
                              max(box[3], other[3]))
                    merged = True
                    break
            else:
                out.append(box)
        boxes = out
    return sorted(((b[0], b[1], b[2] - b[0], b[3] - b[1]) for b in boxes), key=lambda r: (r[1], r[0]))


def default_layout(width: int, height: int) -> AtlasLayout:
    """Vanilla outdoor arrangement: the top half is the base, the bottom
    half 128-texel swatches."""
    swatches = [Swatch("Base", 0, 0, width, min(height, width))]
    for y in range(min(height, width), height, 128):
        for x in range(0, width, 128):
            swatches.append(Swatch(f"Swatch {len(swatches)}", x, y, min(128, width - x), min(128, height - y)))
    return AtlasLayout(width, height, swatches, 0)


def layout_from_uvs(positions: np.ndarray, uv0: np.ndarray, uv1: np.ndarray, width: int,
                    height: int) -> AtlasLayout:
    """Detect the swatches a terrain uses; the base is UV0's most used one."""
    rects = detect_swatches(positions, [uv0, uv1], width, height)
    if not rects:
        return default_layout(width, height)
    swatches = [Swatch(f"Swatch {i + 1}", *(int(v) for v in r)) for i, r in enumerate(rects)]
    layout = AtlasLayout(width, height, swatches, 0)
    s0 = triangle_swatches(uv0, layout)
    layout.base = int(np.bincount(s0, minlength=len(swatches)).argmax())
    layout.swatches[layout.base].name = "Base"
    return layout


def build_atlas(base: np.ndarray, extras: list[tuple[str, np.ndarray]], width: int = 512,
                height: int = 1024) -> tuple[np.ndarray, AtlasLayout]:
    """A new atlas: ``base`` (square RGB(A) uint8, resized by the caller to
    ``width``) in the top half, ``extras`` packed in rows below. Extra width
    and height are independent powers of two (32, 64, 128 or 256 texels), so
    indoor walls, floors, carpets and trim do not have to be square."""
    channels = base.shape[2]
    atlas = np.zeros((height, width, channels), np.uint8)
    atlas[:width, :width] = base[:width, :width]
    swatches = [Swatch("Base", 0, 0, width, width)]
    x = 0
    y = width
    row = 0
    allowed = (32, 64, 128, 256)
    for name, image in sorted(extras, key=lambda item: (-item[1].shape[0], -item[1].shape[1])):
        tile_h, tile_w = image.shape[:2]
        if tile_w not in allowed or tile_h not in allowed:
            raise ValueError(f"Swatch {name} must be 32, 64, 128 or 256 texels on each axis.")
        if x + tile_w > width:
            x, y, row = 0, y + row, 0
        if y + tile_h > height:
            raise ValueError("The swatches do not fit the bottom half of the atlas.")
        atlas[y:y + tile_h, x:x + tile_w] = image[:, :, :channels]
        swatches.append(Swatch(name, x, y, tile_w, tile_h))
        x += tile_w
        row = max(row, tile_h)
    return atlas, AtlasLayout(width, height, swatches, 0)


# ---------------------------------------------------------------- auto paint


def _raster_normals(positions: np.ndarray, resolution: int, span: float):
    ids, height = rasterize_top(positions, resolution, span)
    normals = triangle_normals(positions)
    normals = np.where(normals[:, 1:2] < 0, -normals, normals)
    return ids, height, normals


def slope_weights(positions: np.ndarray, resolution: int, low_degrees: float, high_degrees: float,
                  span: float = MASK_SPAN) -> np.ndarray:
    """Weights rising from 0 at ``low_degrees`` of slope to 1 at ``high_degrees``."""
    positions = np.asarray(positions, float).reshape(-1, 3, 3)
    ids, _, normals = _raster_normals(positions, resolution, span)
    slope = np.degrees(np.arccos(np.clip(normals[np.maximum(ids, 0), 1], -1.0, 1.0)))
    t = (slope - low_degrees) / max(high_degrees - low_degrees, EPS)
    return np.where(ids >= 0, np.clip(t, 0.0, 1.0), 0.0).astype(np.float32)


def height_weights(positions: np.ndarray, resolution: int, low: float, high: float,
                   span: float = MASK_SPAN) -> np.ndarray:
    """Weights 1 at or below ``low`` falling to 0 at ``high`` (``low > high``
    reverses: 0 below, 1 above)."""
    positions = np.asarray(positions, float).reshape(-1, 3, 3)
    ids, height, _ = _raster_normals(positions, resolution, span)
    t = (high - height) / (high - low) if high != low else (height <= low).astype(float)
    return np.where(ids >= 0, np.clip(t, 0.0, 1.0), 0.0).astype(np.float32)


# ---------------------------------------------------------------- light


def bake_light(
    positions: np.ndarray,
    light_matrix,
    size: int = 512,
    *,
    sun: tuple[float, float, float] = (-0.45, -0.75, -0.5),
    strength: float = 0.35,
    shadow_distance: float = 120.0,
    step: float = 1.0,
) -> np.ndarray:
    """A light overlay (``size`` x ``size`` uint8, white = unchanged) for
    the projection ``light_matrix`` (3x4 rows, ``u = row0 . (x, y, z, 1)``):
    sun shading and cast shadows of the terrain. Open flat ground stays
    white like vanilla overlays; ``strength`` is how dark full shadow gets
    (vanilla's darkest areas are about 0.3)."""
    positions = np.asarray(positions, float).reshape(-1, 3, 3)
    m = np.asarray(light_matrix, float)
    lo = positions.reshape(-1, 3).min(axis=0)
    hi = positions.reshape(-1, 3).max(axis=0)
    # heights one unit apart over the terrain
    grid_span = float(max(hi[0], hi[2], 1.0)) + 1.0
    grid_size = int(math.ceil(grid_span / step))
    ids, height = rasterize_top(positions, grid_size, grid_size * step)
    floor = lo[1]
    height = np.where(ids >= 0, height, floor)
    normals = triangle_normals(positions)
    normals = np.where(normals[:, 1:2] < 0, -normals, normals)

    # light pixel centres -> mesh (x, z); repeats pick the copy nearest the terrain's centre
    a = np.array([[m[0, 0], m[0, 2]], [m[1, 0], m[1, 2]]])
    inverse = np.linalg.inv(a)
    axis = (np.arange(size) + 0.5) / size
    u, v = np.meshgrid(axis, axis)
    centre = (lo + hi) / 2
    cu = m[0, 0] * centre[0] + m[0, 2] * centre[2] + m[0, 3]
    cv = m[1, 0] * centre[0] + m[1, 2] * centre[2] + m[1, 3]
    u = u + np.round(cu - u)
    v = v + np.round(cv - v)
    x = inverse[0, 0] * (u - m[0, 3]) + inverse[0, 1] * (v - m[1, 3])
    z = inverse[1, 0] * (u - m[0, 3]) + inverse[1, 1] * (v - m[1, 3])

    def lookup(grid, gx, gz):
        ix = np.clip(np.floor(gx / step).astype(int), 0, grid_size - 1)
        iz = np.clip(np.floor(gz / step).astype(int), 0, grid_size - 1)
        return grid[iz, ix], (ix, iz)

    ground, (ix, iz) = lookup(height, x, z)
    tri = ids[iz, ix]
    n = np.where((tri >= 0)[..., None], normals[np.maximum(tri, 0)], (0.0, 1.0, 0.0))
    to_sun = -np.asarray(sun, float)
    to_sun /= np.linalg.norm(to_sun)
    lambert = np.clip(n @ to_sun, 0.0, None) / max(to_sun[1], EPS)
    lit = np.ones_like(ground)
    horizontal = np.hypot(to_sun[0], to_sun[2])
    if horizontal > EPS:
        dx, dz = to_sun[0] / horizontal, to_sun[2] / horizontal
        rise = to_sun[1] / horizontal
        for k in range(1, int(shadow_distance / step) + 1):
            d = k * step
            above, _ = lookup(height, x + dx * d, z + dz * d)
            lit = np.where(above > ground + rise * d + 0.25, 0.0, lit)
    shade = np.clip(lambert, 0.0, 1.0) * lit
    value = 1.0 - strength * (1.0 - shade)
    value = np.where(tri >= 0, value, 1.0)
    return np.clip(np.rint(value * 255.0), 0, 255).astype(np.uint8)


# ---------------------------------------------------------------- previews


def _sample_nearest(image: np.ndarray, u: np.ndarray, v: np.ndarray) -> np.ndarray:
    h, w = image.shape[:2]
    x = np.minimum((np.mod(u, 1.0) * w).astype(np.int64), w - 1)
    y = np.minimum((np.mod(v, 1.0) * h).astype(np.int64), h - 1)
    return image[y, x]


def render_compiled(result: CompileResult, atlas: np.ndarray, size: int, span: float,
                    light: Optional[np.ndarray] = None, light_matrix=None) -> np.ndarray:
    """Top-down RGB uint8 image of what the game draws (``span`` units square)."""
    ids, _ = rasterize_top(result.positions, size, span)
    out = np.zeros((size, size, 3), np.uint8)
    hit = ids >= 0
    if not hit.any():
        return out
    px, pz = pixel_centres(size, span)
    tri = ids[hit]
    p = result.positions[tri]
    x, z = px[hit], pz[hit]
    # barycentric weights in the top-down plane
    a, b, c = p[:, 0], p[:, 1], p[:, 2]
    den = (b[:, 0] - a[:, 0]) * (c[:, 2] - a[:, 2]) - (c[:, 0] - a[:, 0]) * (b[:, 2] - a[:, 2])
    den = np.where(np.abs(den) < 1e-12, 1e-12, den)
    w1 = ((x - a[:, 0]) * (c[:, 2] - a[:, 2]) - (c[:, 0] - a[:, 0]) * (z - a[:, 2])) / den
    w2 = ((b[:, 0] - a[:, 0]) * (z - a[:, 2]) - (x - a[:, 0]) * (b[:, 2] - a[:, 2])) / den
    w = np.stack([1 - w1 - w2, w1, w2], axis=1)[:, :, None]
    uv0 = (result.uv0[tri] * w).sum(axis=1)
    uv1 = (result.uv1[tri] * w).sum(axis=1)
    first = _sample_nearest(atlas, uv0[:, 0], uv0[:, 1])[:, :3].astype(float)
    second = _sample_nearest(atlas, uv1[:, 0], uv1[:, 1])[:, :3].astype(float)
    m = sample(result.mask.astype(float) / 255.0, x, z)[:, None]
    colour = first * (1 - m) + second * m
    if light is not None and light_matrix is not None:
        lm = np.asarray(light_matrix, float)
        lu = lm[0, 0] * x + lm[0, 2] * z + lm[0, 3]
        lv = lm[1, 0] * x + lm[1, 2] * z + lm[1, 3]
        colour = colour * (_sample_nearest(light, lu, lv).astype(float).reshape(len(x), -1)[:, :1] / 255.0)
    out[hit] = np.clip(np.rint(colour), 0, 255).astype(np.uint8)
    return out


def render_layers(layers: list[Layer], layout: AtlasLayout, atlas: np.ndarray, size: int,
                  span: float) -> np.ndarray:
    """Top-down RGB uint8 image of the painted layers as painted (no
    two-layer limit), ``span`` units square; the layers keep their own
    :data:`MASK_SPAN`."""
    px, pz = pixel_centres(size, span)
    vis = visibility(layers, px, pz)
    out = np.zeros((size, size, 3))
    for k, layer in enumerate(layers):
        s = layout.swatches[layer.swatch]
        tx = s.x + INSET + np.mod(px * layout.density, s.w) * (s.w - 2 * INSET) / s.w
        ty = s.y + INSET + np.mod(pz * layout.density, s.h) * (s.h - 2 * INSET) / s.h
        colour = _sample_nearest(atlas, tx / layout.width, ty / layout.height)[..., :3].astype(float)
        out += colour * vis[k][..., None]
    return np.clip(np.rint(out), 0, 255).astype(np.uint8)
