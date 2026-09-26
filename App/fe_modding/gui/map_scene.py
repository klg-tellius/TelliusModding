"""Build one merged 3D scene for a whole chapter map: the terrain/water
mesh(es) plus every placed prop, each in its real position/rotation - the
feature `map_editor.py`'s "3D Terrain"/"Tile Map" split was deliberately
shipped *without*, back when the `mapbuildinst` -> world-space placement
transform was an unsolved reverse-engineering wall (see that module's own
docstring, and `MAP_PLACEMENT_INVESTIGATION.md`, for the full account of
that investigation). The transform is now confirmed - live Dolphin
emulator debugging found and verified the real formula, implemented as
`map_file.MapBuildInstance.world_transform()` - so this module exists to
actually use it.

This is app-level composition, not a decoded file format: it combines `map_file.py`'s placement math with
`model_viewer.py`'s model loading/decoding, neither of which needed to
change to make this possible.

**Terrain/water objects are placed with zero transform; every prop is
anchored to the terrain's own `mapbuildinst` offset, not the identity.**
This corrects this module's own first version, which used
`parent_matrix=None` (identity) for props - that shipped without checking
where the terrain's *raw mesh* actually sits, and it was wrong. A terrain
object's own raw `.gs` vertex positions are confirmed world-space and
rendered with zero transform (`map_editor.py`'s "3D Terrain" tab, validated
against real disc rebuilds) - but "world-space" for a terrain mesh turns
out to mean a **corner-anchored local box starting at (0, 0)**, not a
box centered on the origin: checked directly against real files, `bmap07`'s
terrain mesh spans exactly `x:[0, 330] z:[0, 320]` (its own declared
`size_x`/`size_z`), never negative. Meanwhile `world_transform()` computes
prop positions in a *different* coordinate space - one where `(0, 0)` is
wherever the terrain's own placed instance says the terrain should sit,
not the terrain mesh's own corner. Rendering terrain unshifted (as
established) while placing props with `parent_matrix=None` therefore
placed most real props *outside* the terrain's actual mesh footprint
entirely (visually: they'd cluster into whatever small overlap region
happened to line up, not spread across the map as the raw instance data
actually shows - a real, user-caught visual symptom this project's own
"cross-check every finding against real data" discipline should have
applied here from the start).

The fix: find the terrain's own `mapbuildinst` entry, compute *its* own
`world_transform()` translation, and use the **negation** of that
translation as every prop's `parent_matrix` (a pure-translation matrix -
terrain's own `angle` is confirmed `0` in every real chapter checked, so
there's no rotation component to invert). This says, in effect: "props are
positioned relative to where the terrain instance claims the terrain
should be; since we're instead rendering the terrain at its own raw-mesh
origin, shift every prop by the same amount the terrain itself would have
moved, in the opposite direction." Checked against real data - not just
plausible, this is now exact: land and water share the identical instance
offset in every real chapter checked (`bmap01`: both `(-22, -20)`), and
after applying this correction, **100% of real non-terrain props land
inside the terrain's own raw mesh bounding box** (`bmap01`: 228/228;
`bmap07`: 381/381) - up from the previous version's much weaker,
wrongly-anchored check.

**`map_scale` defaults to 1.0, not `MapCapacity.scale_unit` (2000.0).**
The investigation's own "what's still open" note flags that the runtime
`mapScale` value (map-state struct +0x6C) was never independently confirmed
to equal `scale_unit` at all - it might be a copy, a per-instance cache, or
a different field entirely. Empirically, `map_scale=1.0` is what produces
physically sensible results against real data (props landing inside the
terrain's footprint, as above); a literal `2000.0` multiplier would blow up
every prop's own mesh geometry by three orders of magnitude relative to the
terrain it needs to sit on. Exposed as a parameter (not hardcoded) so a
future confirmation of the real value doesn't need surgery here.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from .. import map_heights
from ..formats import map_file
from .model_viewer import FIT_FRACTION, GridOverlay, MapTextureProjection, _LoadedSet, _ModelCanvas, _Triangle, load_named_model_set


_NATIVE_TILE_SCALE = 5.0
_MAP_BASE_SELECTOR_PROJECTION_EXTENT = 64.0


_RAM_BACKED_MAP_TEXTURE_PROJECTIONS: dict[str, MapTextureProjection] = {
    "bmap02": MapTextureProjection(
        selector_matrix=(
            (0.000390625006, 0.0, 6.8299047e-11, 0.505859375),
            (-6.8299047e-11, -5.89828994e-19, 0.000390625006, 0.470703125),
            (0.0, 0.0, 0.0, 1.0),
        ),
        last_matrix=(
            (0.000781250012, 0.0, 1.36598094e-10, 0.5078125),
            (-1.36598094e-10, 2.08120813e-19, 0.000781250012, 0.4921875),
            (0.0, 0.0, 0.0, 1.0),
        ),
    ),
    "bmap03": MapTextureProjection(
        selector_matrix=(
            (6.8590106e-12, 4.65815667e-12, 0.000575184831, 0.431298565),
            (-0.000575184831, -4.65815721e-12, 6.85901069e-12, 0.451801525),
            (0.0, 0.0, 0.0, 1.0),
        ),
        last_matrix=(
            (1.37180212e-11, 9.31631335e-12, 0.00115036966, 0.48759713),
            (-0.00115036966, -9.31631441e-12, 1.37180214e-11, 0.528603051),
            (0.0, 0.0, 0.0, 1.0),
        ),
    ),
}


def _find_base_terrain_instance(
    map_name: str, map_data: map_file.MapData
) -> map_file.MapBuildInstance | None:
    terrain_desc_indices = {
        i
        for i, obj in enumerate(map_data.build_desc)
        if i in _base_terrain_desc_indices(map_data) and obj.filename.lower() == map_name.lower()
    }
    for inst in map_data.build_inst:
        if inst.desc_index in terrain_desc_indices:
            return inst
    return None


def _base_terrain_desc_indices(map_data: map_file.MapData) -> set[int]:
    """Return map terrain/water descriptors for scene rendering.

    Most maps mark their terrain/water objects with `flag_bits_a == 0xc0`.
    `bmap31*` is a real exception in the extracted FE9 data: its main terrain
    is the largest descriptor (`bmap30*`) but the flag is clear. Keep the
    file-format predicate strict, and use this renderer-side fallback only
    when no flagged terrain exists at all.
    """
    flagged = {i for i, obj in enumerate(map_data.build_desc) if map_file.is_base_terrain_object(obj)}
    if flagged:
        return flagged
    if not map_data.build_desc:
        return set()
    largest_index, largest_obj = max(
        enumerate(map_data.build_desc),
        key=lambda item: item[1].size_x * item[1].size_z,
    )
    if largest_obj.size_x <= 0.0 or largest_obj.size_z <= 0.0:
        return set()
    return {largest_index}


def _find_terrain_instance(map_data: map_file.MapData) -> map_file.MapBuildInstance | None:
    terrain_indices = _base_terrain_desc_indices(map_data)
    for inst in map_data.build_inst:
        if inst.desc_index in terrain_indices:
            return inst
    return None


def _native_file_projection_matrix(
    inst: map_file.MapBuildInstance, origin_x: float, origin_z: float, extent: float
) -> tuple[tuple[float, float, float, float], ...] | None:
    if extent <= 0.0:
        return None

    # The native terrain actor matrix used by the callback maps raw model X/Z
    # into map-tile units: x' = raw_x / 5 + inst.x, z' = raw_z / 5 + inst.y.
    # The map-state +0x70 matrix then swaps axes into the projection helper's
    # basis. For bmap01's angle-0 terrain instance this reduces to the same
    # 3x4 rows captured live, minus only float32 trig noise around 90 degrees.
    scale = (1.0 / _NATIVE_TILE_SCALE) / (2.0 * extent)
    return (
        (scale, 0.0, 0.0, 0.5 + (float(inst.x) - origin_x) / (2.0 * extent)),
        (0.0, 0.0, scale, 0.5 + (float(inst.y) - origin_z) / (2.0 * extent)),
        (0.0, 0.0, 0.0, 1.0),
    )


def _compute_file_derived_map_texture_projection(
    map_name: str, map_data: map_file.MapData
) -> MapTextureProjection | None:
    if map_data.extra is None:
        return None

    inst = _find_base_terrain_instance(map_name, map_data)
    if inst is None:
        return None

    extra = map_data.extra
    selector_matrix = _native_file_projection_matrix(
        inst,
        float(0x40 - extra.panel_offset_x),
        float(0x40 - extra.panel_offset_y),
        _MAP_BASE_SELECTOR_PROJECTION_EXTENT,
    )
    last_matrix = _native_file_projection_matrix(
        inst,
        float(extra.half_x_size),
        float(extra.half_y_size),
        float(max(extra.texture_projection_extent_x2 >> 1, 1)),
    )
    if selector_matrix is None or last_matrix is None:
        return None
    return MapTextureProjection(selector_matrix=selector_matrix, last_matrix=last_matrix)


def compute_map_texture_projection(
    map_name: str, map_data: map_file.MapData | None = None
) -> MapTextureProjection | None:
    """Return a native map texture projection when one is known.

    For chapter maps with `mapextra` and a matching base terrain instance,
    the projection is derived from `map.bin`/`mapextra` instead of hardcoded
    per-map constants. The live early-map captures are retained as validation
    evidence and fallback data, not as the renderer's primary source of truth.
    """

    if map_data is not None:
        derived = _compute_file_derived_map_texture_projection(map_name, map_data)
        if derived is not None:
            return derived

    return _RAM_BACKED_MAP_TEXTURE_PROJECTIONS.get(map_name.lower())


def _apply_point(matrix, point: tuple[float, float, float]) -> tuple[float, float, float]:
    x, y, z = point
    return (
        matrix[0][0] * x + matrix[0][1] * y + matrix[0][2] * z + matrix[0][3],
        matrix[1][0] * x + matrix[1][1] * y + matrix[1][2] * z + matrix[1][3],
        matrix[2][0] * x + matrix[2][1] * y + matrix[2][2] * z + matrix[2][3],
    )


def _apply_direction(matrix, vector: tuple[float, float, float]) -> tuple[float, float, float]:
    """Rotate (never translate) a direction/normal vector. `world_transform()`'s
    scale component is always uniform (the same `map_scale` on all three
    axes), so a plain rotation - no inverse-transpose needed - keeps a unit
    normal a unit normal (renormalized here only to absorb float error)."""
    x, y, z = vector
    rx = matrix[0][0] * x + matrix[0][1] * y + matrix[0][2] * z
    ry = matrix[1][0] * x + matrix[1][1] * y + matrix[1][2] * z
    rz = matrix[2][0] * x + matrix[2][1] * y + matrix[2][2] * z
    length = math.sqrt(rx * rx + ry * ry + rz * rz) or 1.0
    return (rx / length, ry / length, rz / length)


def _transform_triangle(tri: _Triangle, matrix) -> _Triangle:
    return _Triangle(
        a=_apply_point(matrix, tri.a),
        b=_apply_point(matrix, tri.b),
        c=_apply_point(matrix, tri.c),
        normal=_apply_direction(matrix, tri.normal),
        color=tri.color,
        uv=tri.uv,  # a UV coordinate lives in texture space, unaffected by the 3D world transform
        texture=tri.texture,
        texture_layers=tri.texture_layers,
        alpha=tri.alpha,
        blend_mode=tri.blend_mode,
    )


def _translation_matrix(tx: float, ty: float, tz: float):
    return [
        [1.0, 0.0, 0.0, tx],
        [0.0, 1.0, 0.0, ty],
        [0.0, 0.0, 1.0, tz],
        [0.0, 0.0, 0.0, 1.0],
    ]


def _find_prop_anchor(map_data: map_file.MapData, map_scale: float):
    """The negated translation of the terrain's own `mapbuildinst` entry -
    see this module's own docstring for why every prop needs this as its
    `parent_matrix`. Land/water share the same instance offset in every
    real chapter checked, so the first terrain instance found is enough.
    Returns `None` (identity - the old, wrong-but-harmless default) if a
    chapter genuinely has no terrain instance to anchor to."""
    for inst in map_data.build_inst:
        if inst.desc_index in _base_terrain_desc_indices(map_data):
            m = inst.world_transform(map_scale=map_scale)
            return _translation_matrix(-m[0][3], -m[1][3], -m[2][3])
    return None


def compute_grid_overlay(map_data: map_file.MapData, tile_scale: float = 5.0) -> "GridOverlay | None":
    """Derive the placement-grid lattice (see `GridOverlay`'s own docstring)
    covering the terrain's own raw mesh footprint - used by both the "3D
    Terrain" and "Map View" tabs to show a "hide/show grid + coordinates"
    overlay that helps place new `mapbuildinst` entries, since editing an
    instance's `x`/`y` (see `map_editor.py`'s Instances tab) is exactly what
    this grid's edge labels read off. Reuses the same terrain-instance
    lookup `_find_prop_anchor()` does; if multiple terrain/water objects
    share that instance (the confirmed-common case), the grid is sized to
    the *largest* one by footprint area (typically the land mesh, which the
    smaller water plane normally sits inside) rather than an arbitrary pick.
    Returns `None` if the chapter has no resolvable terrain instance - same
    "nothing to anchor to" case `_find_prop_anchor()` documents."""
    terrain_indices = _base_terrain_desc_indices(map_data)
    if not terrain_indices:
        return None
    origin: tuple[float, float] | None = None
    best_area = 0.0
    best_size: tuple[float, float] | None = None
    for inst in map_data.build_inst:
        if inst.desc_index not in terrain_indices:
            continue
        if origin is None:
            origin = (float(inst.x), float(inst.y))
        obj = map_data.build_desc[inst.desc_index]
        area = obj.size_x * obj.size_z
        if area > best_area:
            best_area = area
            best_size = (obj.size_x, obj.size_z)
    if origin is None or best_size is None or best_area <= 0.0:
        return None
    origin_col, origin_row = origin
    size_x, size_z = best_size
    return GridOverlay(
        col_min=int(origin_col),
        col_max=int(origin_col + size_x / tile_scale),
        row_min=int(origin_row),
        row_max=int(origin_row + size_z / tile_scale),
        tile_scale=tile_scale,
        origin_col=origin_col,
        origin_row=origin_row,
    )


def compute_gameplay_grid_overlay(map_data: map_file.MapData, tile_scale: float = 5.0) -> "GridOverlay | None":
    """The *other* grid - `MapCapacity.x_size`/`y_size`, the tactical
    movement/deployment grid the player actually sees in battle (distinct
    from `compute_grid_overlay()`'s placement/`mapbuildinst` grid, which has
    its own unrelated coordinate space and origin). **Strong evidence, not
    independently confirmed the way the placement grid is** - this project's
    own discipline (see `skeleton.py`'s row-vs-transpose finding for the
    precedent) requires flagging that distinction honestly rather than
    shipping a guess as fact.

    Found by static cross-referencing in `research/main_dol` (GAME_NOTES.md's
    Twenty-eighth finding), not live-debugged the way the placement grid's
    Twentieth finding was: `compute_cursor_tile_world_position()` (renamed
    from `FUN_80045b9c`) builds `world = tile_scale(5.0) * (float)tile *
    mapScale` from two globals (`cursor_tile_x`/`cursor_tile_y`, renamed from
    `DAT_8036728d`/`DAT_8036728e`) - the exact same `tile_scale` SDA constant
    and map-state `+0x6c` `mapScale` field the CONFIRMED
    `MapBuildInstance.world_transform()` uses, but a plain multiply with
    **no pivot/rotation**. The viewer then expresses that grid in the same
    terrain-local placement space as props: real maps checked in this pass
    store `mapextra.panel_offset_x/y` as the positive counterpart of the base
    terrain instance's negative `mapbuildinst.x/y`, so tile 0 is drawn at that
    placement origin instead of the raw mesh's own `(0, 0)` corner.
    Those two globals are written by cursor-move code throughout the
    map-code cluster and are tied, through a shared grid-bounds buffer
    (`DAT_802ca518`), to the same map-state struct `load_uniquepanel_sections()`
    reads `x_size`/`y_size` from - real evidence, but not a live memory
    trace confirming the cursor bytes are literally bounded by
    `x_size`/`y_size` the way the Twentieth finding's recipe would give.

    Cross-checked against already-decoded, already-trusted data before
    shipping: real deployment units' `dispo.py` `pos_x`/`pos_y` fields (their
    literal tactical-grid deployment tile) fall strictly inside
    `[0, x_size) x [0, y_size)` with zero exceptions across every chapter
    checked (`bmap01`/`bmap07`/`bmap12`) - confirming which coordinate space
    `MapCapacity`'s grid is in, even though the *world-space transform*
    itself is only strong evidence. `tile_scale` defaults to the same `5.0`
    confirmed for placement, since the gameplay-grid formula reuses that
    exact SDA constant. `mapextra.grid_buffer` is the confirmed usable
    tactical inset (`min=buffer`, `max=size-buffer`), and Fire Emblem Wiki's
    rendered chapter-map dimensions match that inset for the checked early
    FE9 maps rather than the full padded `MapCapacity` dimensions."""
    cap = map_data.capacity
    if cap.x_size <= 0 or cap.y_size <= 0:
        return None

    origin_col = 0.0
    origin_row = 0.0
    terrain_inst = _find_terrain_instance(map_data)
    if terrain_inst is not None:
        origin_col = float(terrain_inst.x)
        origin_row = float(terrain_inst.y)

    if map_data.extra is not None:
        # Real maps checked so far store panel_offset_x/y as the positive
        # counterpart of the base terrain instance's negative placement
        # coordinate. `bmap31*` is an exception: its terrain instance is
        # positive and the mapextra bytes are not the matching origin, so only
        # prefer mapextra when it agrees with the terrain instance.
        extra_origin_col = -float(map_data.extra.panel_offset_x)
        extra_origin_row = -float(map_data.extra.panel_offset_y)
        if terrain_inst is None or (
            abs(float(terrain_inst.x) - extra_origin_col) <= 0.001
            and abs(float(terrain_inst.y) - extra_origin_row) <= 0.001
        ):
            origin_col = extra_origin_col
            origin_row = extra_origin_row

    col_min = 0
    col_max = cap.x_size
    row_min = 0
    row_max = cap.y_size
    if map_data.extra is not None:
        buffer = map_data.extra.grid_buffer
        if buffer > 0 and buffer * 2 < cap.x_size and buffer * 2 < cap.y_size:
            col_min = buffer
            col_max = cap.x_size - buffer
            row_min = buffer
            row_max = cap.y_size - buffer

    return GridOverlay(
        col_min=col_min,
        col_max=col_max,
        row_min=row_min,
        row_max=row_max,
        tile_scale=tile_scale,
        origin_col=origin_col,
        origin_row=origin_row,
    )


def _loaded_model_cache() -> dict[str, _LoadedSet | None]:
    return {}


def _loaded_for_map_model(
    pak_contents: dict[str, bytes],
    map_data: map_file.MapData,
    cache: dict[str, _LoadedSet | None],
    filename: str,
) -> _LoadedSet | None:
    if filename not in cache:
        cache[filename] = load_named_model_set(
            pak_contents,
            filename,
            map_projection=compute_map_texture_projection(filename, map_data),
        )
    return cache[filename]


def build_map_terrain_scene(
    pak_contents: dict[str, bytes],
    map_data: map_file.MapData,
    cache: dict[str, _LoadedSet | None] | None = None,
    label: str = "map terrain",
) -> _LoadedSet:
    """Build the chapter's terrain/water meshes using the same map texture
    projection path as the full map scene. This is the shared renderer core
    for the terrain-only app view and `build_map_scene()`; the full scene's
    only extra work is adding placed non-terrain objects."""
    if cache is None:
        cache = _loaded_model_cache()

    triangles: list[_Triangle] = []
    terrain_indices = _base_terrain_desc_indices(map_data)
    for index, obj in enumerate(map_data.build_desc):
        if index not in terrain_indices:
            continue
        loaded = _loaded_for_map_model(pak_contents, map_data, cache, obj.filename)
        if loaded is not None:
            triangles.extend(loaded.triangles)

    return _LoadedSet(label=label, bones=[], triangles=triangles, bone_markers={}, animations=[])


def build_map_scene(
    pak_contents: dict[str, bytes], map_data: map_file.MapData, map_scale: float = 1.0
) -> _LoadedSet:
    """Merge a chapter's terrain/water mesh(es) with every placed prop
    (each transformed by its own `mapbuildinst.world_transform()`) into one
    `_LoadedSet` suitable for a mesh-only `_ModelPreview`. Caches decoded
    model sets by `MapObject.filename` (`pak_contents`/`map_data` already
    hold everything in memory - real chapters reuse one mesh across dozens
    of instances, e.g. 377 instances over 41 distinct objects in `bmap12`,
    so decoding is bounded by distinct objects, not instance count).
    Instances whose object has no real `.g`/`.gs` (invisible logic-only
    markers - `load_named_model_set()` returns `None` for those) are
    silently skipped, same as every other caller of that function."""
    cache = _loaded_model_cache()
    terrain_scene = build_map_terrain_scene(pak_contents, map_data, cache=cache, label="map scene")
    triangles: list[_Triangle] = list(terrain_scene.triangles)

    anchor = _find_prop_anchor(map_data, map_scale)
    terrain_indices = _base_terrain_desc_indices(map_data)

    for inst in map_data.build_inst:
        if not (0 <= inst.desc_index < len(map_data.build_desc)):
            continue
        obj = map_data.build_desc[inst.desc_index]
        if inst.desc_index in terrain_indices:
            continue  # already placed above with zero transform
        loaded = _loaded_for_map_model(pak_contents, map_data, cache, obj.filename)
        if loaded is None:
            continue
        matrix = inst.world_transform(map_scale=map_scale, parent_matrix=anchor)
        triangles.extend(_transform_triangle(tri, matrix) for tri in loaded.triangles)

    return _LoadedSet(label="map scene", bones=[], triangles=triangles, bone_markers={}, animations=[])


# -- top-down image (the Build tab's backdrop) -------------------------------------------

#: Camera rotation looking straight down: screen x = world x, screen y = world
#: z (rows grow downwards with ``screen_y_sign = -1``), depth = -height, so
#: higher geometry is nearer. A proper rotation (det +1); both renderers cull
#: by the stored normal, which an upward face passes.
TOPDOWN_ROTATION = ((1.0, 0.0, 0.0), (0.0, 0.0, 1.0), (0.0, -1.0, 0.0))


@dataclass
class TopdownCamera:
    width: int
    height: int
    center: tuple[float, float, float]
    scale: float  # pixels per world unit
    extent: float


def topdown_camera(map_data: map_file.MapData, px_per_tile: int) -> TopdownCamera | None:
    """The orthographic camera that puts tile ``(x, y)`` of the full
    ``mapcapacity`` grid on pixels ``[x * px_per_tile, (x + 1) * px_per_tile)``
    (and the same for y), from the terrain instance's placement origin - the
    same origin ``map_props.place_prop`` uses."""
    cap = map_data.capacity
    if cap is None or cap.x_size <= 0 or cap.y_size <= 0:
        return None
    terrain = next((o.filename for o in map_data.build_desc
                    if map_file.is_base_terrain_object(o) and "water" not in o.filename.lower()), "")
    ox, oy = map_heights.terrain_origin(map_data, terrain)
    tile = map_heights.TILE_SIZE
    return TopdownCamera(
        width=cap.x_size * px_per_tile,
        height=cap.y_size * px_per_tile,
        center=(tile * (cap.x_size / 2.0 - ox), 0.0, tile * (cap.y_size / 2.0 - oy)),
        scale=px_per_tile / tile,
        extent=tile * max(cap.x_size, cap.y_size),
    )


class _TopdownRasterCamera:
    """The attributes ``_ModelCanvas._rasterize()`` reads, for rendering
    without a canvas."""

    def __init__(self, camera: TopdownCamera) -> None:
        import numpy as np

        self._matrix = np.array(TOPDOWN_ROTATION)
        self._center = camera.center
        self._extent = camera.extent
        self._zoom = camera.scale * camera.extent / (min(camera.width, camera.height) * FIT_FRACTION)
        self._screen_x_sign, self._screen_y_sign = 1.0, -1.0

    def _rotation_matrix(self):
        return self._matrix


def render_topdown(scene: _LoadedSet, camera: TopdownCamera, gpu=None):
    """``scene`` (``build_map_scene()``) seen from straight above through
    ``camera``, as a PIL image. ``gpu`` is a ``gpu_renderer`` renderer, or
    None for the CPU rasterizer (slower; safe on a worker thread)."""
    import numpy as np
    from PIL import Image

    if gpu is not None:
        gpu.set_triangles(scene.triangles)
        return gpu.render_image(camera.width, camera.height, np.array(TOPDOWN_ROTATION), camera.center,
                                camera.scale, camera.extent, 1.0, -1.0)
    frame = _ModelCanvas._rasterize(_TopdownRasterCamera(camera), scene.triangles, camera.width, camera.height)
    return Image.fromarray(frame)
