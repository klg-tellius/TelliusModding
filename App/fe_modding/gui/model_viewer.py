"""Read-only viewer for the 3D formats decoded in ``fe_modding/formats/``:
``skeleton.py`` (``.g``), ``model.py`` (``.gs``), and ``animation.py``
(``.ga``). Lists every character/battle-scenery model set found under
``ymu/*/pack.cmp`` and ``zbg/*/*.cmp`` (confirmed real layouts - a decompressed
``ymu/<class>/pack.cmp`` holds ``skeleton.g`` + ``body.gs`` + a couple of
``.ga`` files, plus more ``.ga`` files sitting loose, uncompressed, alongside
it in the same folder; a decompressed ``zbg/<name>/*.cmp`` holds
``map.bin`` + ``<name>.g`` + ``<name>.gs`` + ``<name>.ga`` + a texture pack).

**Scope is deliberately limited to what's actually confirmed decoded data**,
matching this project's usual discipline about not overclaiming:

- ``.gs`` mesh geometry (positions/normals/triangle strips) is real,
  validated data - rendered here as a shaded, rotatable static mesh in its
  own bind pose.
- ``.g`` bone *hierarchy* (name/parent), *position*, and *rotation* are
  all real, confirmed (position) or strong-evidence (rotation) data - see
  ``skeleton.py``'s docstring for how each was established.
- ``.ga`` animation curves are real, fully decoded data (see
  ``animation.py``).

**Mesh coloring**: triangles are sampled from the first texture record on
the material and modulated by ``material.color0`` wherever that texture can
be resolved. Runtime map callbacks can reuse that first texture through the
secondary UV source, lerp UV0/UV2 by projected texture-record 1 where a
RAM-backed map projection is known, then multiply by the projected final
material texture. The RAM-backed bmap01/bmap02/bmap03 still projections use
the same seed-point layout as the native callback's stack setup. For maps
without a known projection, the preview keeps the older conservative
light/detail blend rather than presenting guessed matrices as game parity.
For character models (``ymu``), textures sit in several standalone
``tex_N.tpl`` files instead of one indexed pack, so this uses pak-encounter
order as the index (unconfirmed, but a real sample -
``ymu/archer`` - showed the first pak-order texture is a genuine
UV-unwrapped body-skin atlas, matching the model's one real material).
Falls back to the flat material-color tint (or gray) wherever a texture
can't be resolved or decoded.

**Skeleton + mesh playback**: selecting an animation and scrubbing/playing
the frame slider poses the skeleton and mesh with
``fe_modding.formats.engine_pose`` - a port of the engine's own curve
evaluation, bone-matrix builder and hierarchy/skinning chain - so each
vertex is drawn where the game draws it (``world x skin_matrix`` for
multi-matrix shapes, ``world`` for single-matrix ones). Both revert to the
static bind pose/mesh whenever no animation is selected or playing.

**Cross-reference from other editors**: ``load_named_model_set()`` decodes
just one named model group (e.g. ``"bmap01_water0"``) out of an
already-unpacked archive's ``{filename: content}`` map, rather than an
entire ``ymu``/``zbg`` pack - for chapter maps, whose own ``map.cmp``
bundles *several* independently-named model groups (the chapter's terrain,
a water plane, decorative props) in one archive, unlike ``ymu``/``zbg``'s
one-model-per-pack convention the rest of this module assumes.
``ModelPreviewDialog`` hosts the same canvas/skeleton/animation widgets
as this panel's own central+right columns (factored out as
``_ModelPreview``, shared rather than duplicated) in a lightweight popup,
for a single resolved model - see ``map_editor.py``'s "View Model..."
buttons for where this gets used.

Write support: "Export .glb..." writes the selected set through
``gltf_export``. "Import .glb..." rebuilds the set's ``.gs`` from a glTF
through ``gltf_import`` and repacks the ``.cmp``: as a static mesh for
``zbg/`` scenery (``replace_set_with_static_glb()``), as a skinned body on
the class skeleton for ``ymu/`` characters (blended vertices use the engine's
CPU-skinned composite shapes)
(``replace_body_with_glb()``, which also handles the ``tex_N.tpl``
variants). "Import animation..." (``ymu/`` sets) rebuilds one of the set's
``.ga`` from a glTF animation (``replace_animation_with_glb()``). "Replace
rig..." (``ymu/`` sets) builds a new skeleton from a glTF armature and
rebuilds the body and every class animation on it
(``replace_rig_with_glb()``).

Battle models (``zu/<code>/<code>_<weapon>.pak``, uncompressed, one pack
per weapon type with the same mesh and skeleton) are listed once per
folder; ``replace_battle_body_with_glb()`` rebuilds their mesh from
composite shapes only and writes it into every weapon pack. ``ymu/`` sets
are the map models.

Weapon models (``xwp/<name>/<name>.cmp``, and ``xwp/forge/<name>_b.cmp``
for forged weapons; see ``formats/icons.py`` for how an item picks one) are
listed as ``xwp/<name>`` and ``xwp/forge/<name>_b``; Game Data's items link
here. "Import .glb..." replaces a weapon as a rigid static mesh, like
scenery; bows are refused (``is_skinned_weapon()``): their string bends
through composite shapes, which that import doesn't write.

Each import first returns a :class:`ModelImport` (the files it would
write, warnings, the joint -> bone mapping). ``_ImportReviewDialog`` shows
it before anything is written: a preview of the converted set, the figures
of every changed file next to the current ones (``import_review_rows()``,
flagging sizes above every vanilla model of the same kind), the joints and the
warnings. Writing goes through ``ModProject.write_keeping_original``, which
keeps the file as extracted in the project's ``originals/`` folder;
"Restore original..." puts a set's kept files back.

"New slot..." (``ymu/`` and ``zu/`` sets, ``_NewSlotDialog``) copies the
set under a new name and points a character or class at the copy through
``model_slots``, so the copy can be changed without touching the vanilla
model's other users. "Model tables..." (``_ModelTablesDialog``) edits the
tables that pick the models: the battle job list (with a "which models does
a character get" check), each battle model's texture lines, and the per-army
texture numbers of a map model's ``FE8Anim.bin`` records; it also removes
slots made with "New slot..." (``model_slots.remove_battle_model`` /
``remove_map_model``).
"""

from __future__ import annotations

import io
import json
import math
import re
import tkinter as tk
from dataclasses import dataclass, field, replace
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

import numpy as np
from PIL import Image, ImageTk

from ..formats import animation, engine_pose, gltf_export, gltf_import, gs_file, gs_stats, lz10, map_file, pak, skeleton, tpl
from ..formats import model as model_fmt
from .. import map_heights, map_props, mesh_reduce, model_slots, rig_contract, rig_fit, terrain_conform
from ..formats import anim_registry, fe8data, zdbx
from ..project import ModProject
from . import gpu_renderer
from .changelog import ChangeLog
from .editor_panel import EditorPanel


@dataclass(frozen=True)
class _VertexSkin:
    bone_indices: tuple[int, ...]
    bone_weights: tuple[float, ...]
    # multi-matrix/composite shapes are drawn with world x skin_matrix,
    # single-matrix shapes with the bone's world matrix alone
    uses_palette: bool = True


@dataclass
class _TextureLayer:
    uv: tuple[tuple[float, float], tuple[float, float], tuple[float, float]]
    texture: "np.ndarray"
    role: str
    flip_v: bool = False
    color_scale: tuple[float, float, float] = (1.0, 1.0, 1.0)
    wrap_s: int = 1
    wrap_t: int = 1


@dataclass(frozen=True)
class _LoadedTexture:
    image: Image.Image
    wrap_s: int = 1
    wrap_t: int = 1

    @property
    def array(self) -> "np.ndarray":
        """The image as an (H, W, 4) uint8 array, converted once and shared
        by every model and triangle using this texture (so the GPU renderer
        also uploads it once)."""
        cached = self.__dict__.get("_array")
        if cached is None:
            cached = np.asarray(self.image.convert("RGBA"), dtype=np.uint8)
            object.__setattr__(self, "_array", cached)
        return cached


@dataclass(frozen=True)
class MapTextureProjection:
    """Texture matrices used by the native map material callbacks.

    The game does not simply draw every material texture through stored mesh
    UVs. For map-base/map-wall materials it samples texture0 on UV0 and UV2,
    lerps those two samples by projected texture1, then multiplies by the
    projected final material texture.
    """

    selector_matrix: tuple[tuple[float, float, float, float], ...]
    last_matrix: tuple[tuple[float, float, float, float], ...]

    def selector_uv(self, point: tuple[float, float, float]) -> tuple[float, float]:
        return _project_texture_uv(self.selector_matrix, point)

    def last_uv(self, point: tuple[float, float, float]) -> tuple[float, float]:
        return _project_texture_uv(self.last_matrix, point)


@dataclass
class _Triangle:
    a: tuple[float, float, float]
    b: tuple[float, float, float]
    c: tuple[float, float, float]
    normal: tuple[float, float, float]
    color: tuple[int, int, int]
    skin: tuple[_VertexSkin, _VertexSkin, _VertexSkin] | None = None
    # per-vertex UV + a shared (H, W, 3) uint8 numpy texture array, for the
    # rasterizer's real per-pixel texture sampling (_ModelCanvas._redraw()) -
    # `color` stays populated as a flat fallback (the old area-averaged
    # sample) for triangles with no texture, or if per-pixel sampling can't
    # be done for some reason. `texture` deliberately holds the SAME array
    # object across every triangle sharing one texture (converted once, not
    # per-triangle) - see _texture_array()'s cache.
    uv: tuple[tuple[float, float], tuple[float, float], tuple[float, float]] | None = None
    texture: "np.ndarray | None" = None
    texture_layers: tuple[_TextureLayer, ...] = ()
    alpha: float = 1.0
    blend_mode: str = "normal"


@dataclass
class _LoadedSet:
    label: str
    bones: list[skeleton.Bone]
    triangles: list[_Triangle] = field(default_factory=list)
    bone_markers: dict[int, tuple[float, float, float]] = field(default_factory=dict)
    animations: list[tuple[str, bytes]] = field(default_factory=list)


@dataclass(frozen=True)
class GridOverlay:
    """World-space placement-grid lines + edge coordinate labels, sized and
    anchored to line up with a chapter's terrain footprint - not a decoded
    file-format fact, a rendering aid built by `map_scene.compute_grid_overlay()`
    to help place new `mapbuildinst` entries by reading off which raw (x, y)
    an on-screen tile corresponds to. A tile column `c`'s world X is
    `(c - origin_col) * tile_scale` - the exact same formula
    `map_file.MapBuildInstance.world_transform()` uses for its own `pos_x`
    (`tile_scale * inst.x`), composed with the same negated-terrain-instance
    `parent_matrix` `map_scene._find_prop_anchor()` already uses - exact, not
    an approximation, for angle=0 grid lines (real ones can be rotated; grid
    lines have no angle to rotate by)."""

    col_min: int
    col_max: int
    row_min: int
    row_max: int
    tile_scale: float
    origin_col: float
    origin_row: float


def _iter_model_sets(project: ModProject) -> list[tuple[str, Path]]:
    files_dir = project.extracted_dir / "files"
    sets: list[tuple[str, Path]] = []

    ymu_dir = files_dir / "ymu"
    if ymu_dir.exists():
        for pack_path in sorted(ymu_dir.glob("*/pack.cmp")):
            sets.append((f"ymu/{pack_path.parent.name}", pack_path))

    # Battle models: zu/<code>/<code>_<weapon>.pak, one per weapon type, all
    # holding the same body and skeleton; listed once per folder.
    zu_dir = files_dir / "zu"
    if zu_dir.exists():
        for folder in sorted(p for p in zu_dir.iterdir() if p.is_dir()):
            paks = sorted(folder.glob(f"{folder.name}_*.pak"))
            if paks:
                sets.append((f"zu/{folder.name}", paks[0]))

    # Chapter maps: zmap/<map>/map.cmp (terrain, water, props and map.bin).
    zmap_dir = files_dir / "zmap"
    if zmap_dir.exists():
        for cmp_path in sorted(zmap_dir.glob("*/map.cmp")):
            sets.append((f"zmap/{cmp_path.parent.name}", cmp_path))

    zbg_dir = files_dir / "zbg"
    if zbg_dir.exists():
        for folder in sorted(p for p in zbg_dir.iterdir() if p.is_dir()):
            for cmp_path in sorted(folder.glob("*.cmp")):
                sets.append((f"zbg/{folder.name}", cmp_path))

    # Weapons: xwp/<name>/<name>.cmp, the equipped item's model in battle
    # (formats/icons.py), and xwp/forge/<name>_b.cmp for forged weapons.
    xwp_dir = files_dir / "xwp"
    if xwp_dir.exists():
        for folder in sorted(p for p in xwp_dir.iterdir() if p.is_dir()):
            for cmp_path in sorted(folder.glob("*.cmp")):
                label = f"xwp/forge/{cmp_path.stem}" if folder.name.lower() == "forge" else f"xwp/{folder.name}"
                sets.append((label, cmp_path))

    return sets


def is_skinned_weapon(container_path: Path) -> bool:
    """A weapon model drawn through the composite (CPU-skinned) path, the
    bows: their string bends, so they can't be replaced by a rigid mesh."""
    _entries, files = _read_container(container_path)
    return any(Path(name).suffix.lower() == ".gs" and gs_file.read_gs(data).composite is not None
               for name, data in files.items())


def _material_color(gs_model: model_fmt.GsModel, material_index: int) -> tuple[int, int, int]:
    if 0 <= material_index < len(gs_model.materials):
        r, g, b, _a = gs_model.materials[material_index].color0
        if r or g or b:
            return (r, g, b)
    return (190, 190, 190)


def _material_alpha(gs_model: model_fmt.GsModel, material_index: int) -> float:
    if 0 <= material_index < len(gs_model.materials):
        return gs_model.materials[material_index].color0[3] / 255.0
    return 1.0


def _chunk_blend_mode(chunk: model_fmt.TriChunk) -> str:
    """Native `.gs` bit 0x40 selects GX_BM_BLEND/SRCALPHA/ONE."""
    if chunk.format & 0x40:
        return "additive"
    return "normal"


def _average(vectors) -> tuple[float, float, float]:
    vectors = list(vectors)
    n = len(vectors) or 1
    sx = sum(v[0] for v in vectors)
    sy = sum(v[1] for v in vectors)
    sz = sum(v[2] for v in vectors)
    return (sx / n, sy / n, sz / n)


def _sample_texture(image: Image.Image, uv: tuple[float, float], flip_v: bool = False) -> tuple[int, int, int] | None:
    """Bilinear-filtered sample at (u, v), wrapped to [0, 1). Ordinary
    sampling treats ``v=0`` as the image top. Terrain preview code can request
    a flipped sample when using the lower half of a tall atlas as masked
    detail; see ``_sample_texture_layers()``."""
    u, v = uv
    u -= math.floor(u)
    v -= math.floor(v)
    width, height = image.size
    if width <= 0 or height <= 0:
        return None
    fx = u * width - 0.5
    if flip_v:
        v = 1.0 - v
    fy = v * height - 0.5
    x0 = math.floor(fx)
    y0 = math.floor(fy)
    tx = fx - x0
    ty = fy - y0
    x0c, x1c = min(max(x0, 0), width - 1), min(max(x0 + 1, 0), width - 1)
    y0c, y1c = min(max(y0, 0), height - 1), min(max(y0 + 1, 0), height - 1)
    px = image.load()
    p00, p10, p01, p11 = px[x0c, y0c], px[x1c, y0c], px[x0c, y1c], px[x1c, y1c]
    result = []
    for c in range(3):
        top = p00[c] * (1 - tx) + p10[c] * tx
        bottom = p01[c] * (1 - tx) + p11[c] * tx
        result.append(int(top * (1 - ty) + bottom * ty))
    return (result[0], result[1], result[2])


def _sample_texture_area(
    image: Image.Image, uv0: tuple[float, float], uv1: tuple[float, float], uv2: tuple[float, float]
) -> tuple[int, int, int] | None:
    """Average several samples across a triangle's own UV footprint (its 3
    corners, the 3 edge midpoints, and the centroid) instead of one point at
    the corners' naive average. A single point sample is fine when a
    triangle's own UVs barely move, but real terrain data doesn't behave
    that way: a chapter's shared ``texpack.tpl`` packs many small, visually
    unrelated ground materials (grass, stone, gravel, dirt, ...) into one
    image (confirmed - see this module's "Mesh coloring" docstring section),
    and checking `bmap01.gs` found 98.2% of its 6028 real triangles have a
    per-vertex UV spread over 0.05 (median ~0.06, up to 0.25 - a quarter of
    the whole atlas). A single sample at the averaged UV routinely lands on
    an unrelated material's texel for triangles like that; because terrain
    meshes are built from a regular grid of quads, the resulting per-triangle
    color error alternates in a regular pattern between neighboring
    triangles rather than looking like random noise - it reads as a visible
    interlaced/checkerboard artifact, not just "blocky." Averaging multiple
    samples' *pixel colors* (not averaging UVs and sampling once) is a cheap
    way to get a real regional average without a full rasterizer."""
    corners = (uv0, uv1, uv2)
    midpoints = (
        ((uv0[0] + uv1[0]) / 2, (uv0[1] + uv1[1]) / 2),
        ((uv1[0] + uv2[0]) / 2, (uv1[1] + uv2[1]) / 2),
        ((uv2[0] + uv0[0]) / 2, (uv2[1] + uv0[1]) / 2),
    )
    centroid = ((uv0[0] + uv1[0] + uv2[0]) / 3, (uv0[1] + uv1[1] + uv2[1]) / 3)
    samples = [_sample_texture(image, p) for p in (*corners, *midpoints, centroid)]
    samples = [s for s in samples if s is not None]
    if not samples:
        return None
    n = len(samples)
    return (
        sum(s[0] for s in samples) // n,
        sum(s[1] for s in samples) // n,
        sum(s[2] for s in samples) // n,
    )


def _sample_texture_area_batch(texture: "np.ndarray", uvs: "np.ndarray") -> "np.ndarray":
    """``_sample_texture_area()`` for many triangles at once: ``uvs`` is
    (N, 3, 2), ``texture`` an (H, W, C) uint8 array; returns (N, 3) ints
    equal to what the per-triangle version gives (same bilinear arithmetic,
    same truncation and integer average)."""
    uv0, uv1, uv2 = uvs[:, 0], uvs[:, 1], uvs[:, 2]
    points = np.stack(
        (uv0, uv1, uv2, (uv0 + uv1) / 2, (uv1 + uv2) / 2, (uv2 + uv0) / 2, (uv0 + uv1 + uv2) / 3), axis=1
    )
    height, width = texture.shape[:2]
    u = points[..., 0] - np.floor(points[..., 0])
    v = points[..., 1] - np.floor(points[..., 1])
    fx = u * width - 0.5
    fy = v * height - 0.5
    x0 = np.floor(fx)
    y0 = np.floor(fy)
    tx = (fx - x0)[..., None]
    ty = (fy - y0)[..., None]
    x0 = x0.astype(np.int64)
    y0 = y0.astype(np.int64)
    x0c, x1c = np.clip(x0, 0, width - 1), np.clip(x0 + 1, 0, width - 1)
    y0c, y1c = np.clip(y0, 0, height - 1), np.clip(y0 + 1, 0, height - 1)
    rgb = texture[..., :3].astype(np.float64)
    top = rgb[y0c, x0c] * (1 - tx) + rgb[y0c, x1c] * tx
    bottom = rgb[y1c, x0c] * (1 - tx) + rgb[y1c, x1c] * tx
    samples = (top * (1 - ty) + bottom * ty).astype(np.int64)
    return samples.sum(axis=1) // points.shape[1]


def _wrap_texture_coord(coord: "np.ndarray", mode: int) -> "np.ndarray":
    if mode == 0:
        return np.minimum(np.maximum(coord, 0.0), np.nextafter(1.0, 0.0))
    if mode == 2:
        folded = coord - np.floor(coord / 2.0) * 2.0
        return np.where(folded >= 1.0, 2.0 - folded, folded)
    return coord - np.floor(coord)


def _sample_texture_batch(
    texture: "np.ndarray",
    u: "np.ndarray",
    v: "np.ndarray",
    flip_v: bool = False,
    wrap_s: int = 1,
    wrap_t: int = 1,
) -> "np.ndarray":
    """Vectorized nearest-neighbor sample of a (TH, TW, C) uint8 texture
    array at every (u, v) position in the given arrays, honoring the source
    TPL's GX wrap modes for the rasterizer's per-pixel texture mapping -
    batched over a whole triangle's rasterized pixel block in one call
    instead of one Python call per pixel. `u`/`v` share one shape; the
    result is that same shape with an extra trailing channel axis.

    Nearest, not bilinear: profiling a real merged-scene redraw found this
    function was ~27% of total rasterize time (four gathers + interpolation
    per call, called once per textured triangle - tens of thousands of
    times for a busy chapter). The real quality jump was already won by
    fixing *what* gets sampled - a real per-screen-pixel UV via barycentric
    interpolation, replacing the old one-flat-color-per-triangle
    approximation entirely - not by how each individual sample is filtered;
    nearest keeps that win at a quarter of the per-triangle cost. Also uses
    np.minimum/np.maximum instead of np.clip to clamp texture coordinates -
    np.clip carries real fixed per-call overhead (dtype-range lookups) that
    showed up directly in the same profile, disproportionate to how little
    work each individual call does here."""
    th, tw = texture.shape[:2]
    u_wrapped = _wrap_texture_coord(u, wrap_s)
    v_wrapped = _wrap_texture_coord(v, wrap_t)
    if flip_v:
        v_wrapped = 1.0 - v_wrapped
    tx = np.minimum(np.maximum((u_wrapped * tw).astype(np.int64), 0), tw - 1)
    ty = np.minimum(np.maximum((v_wrapped * th).astype(np.int64), 0), th - 1)
    return texture[ty, tx].astype(np.float64)


def _project_texture_uv(
    matrix: tuple[tuple[float, float, float, float], ...], point: tuple[float, float, float]
) -> tuple[float, float]:
    x, y, z = point
    s = matrix[0][0] * x + matrix[0][1] * y + matrix[0][2] * z + matrix[0][3]
    t = matrix[1][0] * x + matrix[1][1] * y + matrix[1][2] * z + matrix[1][3]
    q = matrix[2][0] * x + matrix[2][1] * y + matrix[2][2] * z + matrix[2][3]
    if abs(q) > 1e-8:
        return (s / q, t / q)
    return (s, t)


def _texture_layer_role(texture: "np.ndarray") -> str:
    """Classify an extra material texture for the viewer's best-effort
    preview blend. This is intentionally renderer-side and conservative:
    the exact GX/TEV program still belongs in reverse-engineering notes once
    it is found in main.dol."""
    sample = texture[..., :3].reshape((-1, 3)).astype(np.float64)
    if sample.size == 0:
        return "detail"
    luma = sample.mean(axis=1)
    dark_fraction = float((luma < 8.0).mean())
    bright_fraction = float((luma > 240.0).mean())
    saturation = sample.max(axis=1) - sample.min(axis=1)
    if dark_fraction > 0.75 and bright_fraction > 0.02:
        return "blend_mask"
    if float(saturation.mean()) < 10.0:
        return "light"
    return "detail"


def _sample_texture_layers(
    layers: tuple[_TextureLayer, ...], w0: "np.ndarray", w1: "np.ndarray", w2: "np.ndarray"
) -> "np.ndarray":
    layer = layers[0]
    uv0, uv1, uv2 = layer.uv
    u = w0 * uv0[0] + w1 * uv1[0] + w2 * uv2[0]
    v = w0 * uv0[1] + w1 * uv1[1] + w2 * uv2[1]
    sampled_rgba = _sample_texture_batch(layer.texture, u, v, flip_v=layer.flip_v, wrap_s=layer.wrap_s, wrap_t=layer.wrap_t)
    sampled = sampled_rgba[..., :3] * np.array(layer.color_scale, dtype=np.float64)
    alpha = sampled_rgba[..., 3:4] if sampled_rgba.shape[2] >= 4 else np.full(sampled.shape[:2] + (1,), 255.0)
    pending_callback_detail: np.ndarray | None = None
    saw_map_selector = False
    for overlay_layer in layers[1:]:
        uv0, uv1, uv2 = overlay_layer.uv
        u = w0 * uv0[0] + w1 * uv1[0] + w2 * uv2[0]
        v = w0 * uv0[1] + w1 * uv1[1] + w2 * uv2[1]
        overlay_rgba = _sample_texture_batch(
            overlay_layer.texture,
            u,
            v,
            flip_v=overlay_layer.flip_v,
            wrap_s=overlay_layer.wrap_s,
            wrap_t=overlay_layer.wrap_t,
        )
        if overlay_layer.role == "callback_uv2_detail":
            pending_callback_detail = overlay_rgba[..., :3] * np.array(overlay_layer.color_scale, dtype=np.float64)
        elif overlay_layer.role == "map_selector":
            saw_map_selector = True
            if pending_callback_detail is not None:
                selector = overlay_rgba[..., :3].mean(axis=2, keepdims=True) / 255.0
                sampled = sampled * (1.0 - selector) + pending_callback_detail * selector
                pending_callback_detail = None
        elif overlay_layer.role == "map_projected_light":
            sampled *= overlay_rgba[..., :3] / 255.0
        elif overlay_layer.role == "light":
            luma = overlay_rgba[..., :3].mean(axis=2, keepdims=True) / 255.0
            if pending_callback_detail is not None and not saw_map_selector:
                detail_mask = np.minimum(np.maximum((1.0 - luma - 0.20) * 3.0, 0.0), 0.60)
                sampled = sampled * (1.0 - detail_mask) + pending_callback_detail * detail_mask
            sampled *= 0.7 + luma * 0.6
    return np.concatenate((sampled, alpha), axis=2)


def _material_uses_map_base_callback(material: model_fmt.Material) -> bool:
    return material.name in {"map_base", "map_wall"} and len(material.textures) >= 2


_TEXTURE_CACHE_SIZE = 8
_texture_cache: "dict[tuple[bytes, ...], dict[int, _LoadedTexture]]" = {}


def _load_textures(tpl_contents: dict[str, bytes]) -> dict[int, _LoadedTexture]:
    """Best-effort ``tex_id`` -> decoded texture image, so mesh triangles can
    be colored with their real texture instead of a flat material tint.
    Takes a plain ``{filename: raw .tpl bytes}`` map - both this module's
    own folder-based loading and ``load_named_model_set()``'s in-memory
    archive loading already have exactly that, just built differently. See
    this module's docstring ("Mesh coloring") for the differing confidence
    between the two cases handled here.

    Results are cached by the ``.tpl`` bytes themselves: a chapter scene
    loads each of its props with the chapter's whole shared ``texpack.tpl``,
    which would otherwise be decoded again for every prop. Keying on
    content means an edited file can never hit a stale entry. Callers must
    treat the returned images as read-only."""
    if not tpl_contents:
        return {}
    key = tuple(tpl_contents.values())
    cached = _texture_cache.pop(key, None)
    if cached is None:
        cached = _decode_textures(tpl_contents)
    _texture_cache[key] = cached  # most recently used last
    while len(_texture_cache) > _TEXTURE_CACHE_SIZE:
        del _texture_cache[next(iter(_texture_cache))]
    return cached


def _decode_textures(tpl_contents: dict[str, bytes]) -> dict[int, _LoadedTexture]:
    """``_load_textures()`` without the cache."""

    if len(tpl_contents) == 1:
        # a single multi-image texture pack (zbg's texpack.tpl) - confirmed:
        # a material's own texture ID indexes this file's own image list
        # directly.
        (content,) = tpl_contents.values()
        try:
            images = tpl.read_tpl_images(io.BytesIO(content))
            infos = {info.index: info for info in tpl.read_tpl_image_info(io.BytesIO(content))}
        except Exception:  # noqa: BLE001
            return {}
        textures: dict[int, _LoadedTexture] = {}
        for i, img in enumerate(images):
            info = infos.get(i)
            textures[i] = _LoadedTexture(
                img.convert("RGBA"),
                info.wrap_s if info is not None else 1,
                info.wrap_t if info is not None else 1,
            )
        return textures

    # several standalone single-texture files (ymu/<class>/tex_N.tpl) - not
    # independently confirmed; uses encounter order as the index.
    textures: dict[int, _LoadedTexture] = {}
    for i, content in enumerate(tpl_contents.values()):
        try:
            images = tpl.read_tpl_images(io.BytesIO(content))
            infos = tpl.read_tpl_image_info(io.BytesIO(content))
        except Exception:  # noqa: BLE001
            continue
        if images:
            info = infos[0] if infos else None
            textures[i] = _LoadedTexture(images[0].convert("RGBA"), info.wrap_s if info else 1, info.wrap_t if info else 1)
    return textures


def _texture_array(image: Image.Image, cache: dict[int, "np.ndarray"]) -> "np.ndarray":
    """Convert (once, memoized by the PIL Image's own id) a decoded texture
    to a plain (H, W, 4) uint8 numpy array for the rasterizer's vectorized
    per-pixel sampling - every triangle sharing one texture image shares the
    same array object, not a copy."""
    key = id(image)
    if key not in cache:
        cache[key] = np.asarray(image.convert("RGBA"), dtype=np.uint8)
    return cache[key]


def _accumulate_mesh(
    gs_model: model_fmt.GsModel,
    triangles: list[_Triangle],
    textures_by_index: dict[int, _LoadedTexture],
    map_projection: MapTextureProjection | None = None,
) -> None:
    for chunk in gs_model.chunks:
        if chunk.hidden:
            continue
        material_index = chunk.material_index
        blend_mode = _chunk_blend_mode(chunk)
        texture_image = None
        material_textures: list[tuple[int, _LoadedTexture, np.ndarray, str]] = []
        if 0 <= material_index < len(gs_model.materials):
            material = gs_model.materials[material_index]
            if material.textures:
                first_image = textures_by_index.get(material.textures[0].tex_id)
                if first_image is not None:
                    first_array = first_image.array
                    material_textures.append((0, first_image, first_array, "diffuse"))
                    if _material_uses_map_base_callback(material):
                        material_textures.append((-1, first_image, first_array, "callback_uv2_detail"))
                        if map_projection is not None and len(material.textures) >= 2:
                            selector_image = textures_by_index.get(material.textures[1].tex_id)
                            if selector_image is not None:
                                selector_array = selector_image.array
                                material_textures.append((1, selector_image, selector_array, "map_selector"))
                if len(material.textures) > 2:
                    stage_index = 2
                    stage_texture = material.textures[stage_index]
                    if map_projection is not None and _material_uses_map_base_callback(material):
                        stage_index = len(material.textures) - 1
                        stage_texture = material.textures[stage_index]
                    stage_image = textures_by_index.get(stage_texture.tex_id)
                    if stage_image is not None:
                        stage_array = stage_image.array
                        role = _texture_layer_role(stage_array)
                        if map_projection is not None and _material_uses_map_base_callback(material):
                            role = "map_projected_light"
                        material_textures.append((stage_index, stage_image, stage_array, role))
                if material_textures:
                    texture_image = material_textures[0][1]
        fallback_color = _material_color(gs_model, material_index)
        material_alpha = _material_alpha(gs_model, material_index)
        texture_array = material_textures[0][2] if material_textures else None
        material_color_scale = (1.0, 1.0, 1.0)
        if 0 <= material_index < len(gs_model.materials):
            mat_color = gs_model.materials[material_index].color0
            material_color_scale = (mat_color[0] / 255.0, mat_color[1] / 255.0, mat_color[2] / 255.0)
        area_colors: list[tuple[int, int, int]] = []
        if texture_image is not None:
            # every triangle's flat fallback color in one vectorized pass
            strip_uvs = [
                (strip[i].uv, strip[i + 1].uv, strip[i + 2].uv) for strip in chunk.strips for i in range(len(strip) - 2)
            ]
            if strip_uvs:
                sampled = _sample_texture_area_batch(texture_array, np.array(strip_uvs, dtype=np.float64))
                area_colors = [tuple(c) for c in (sampled * np.array(material_color_scale)).astype(np.int64).tolist()]
        triangle_index = -1

        for strip in chunk.strips:
            for i in range(len(strip) - 2):
                v0, v1, v2 = strip[i], strip[i + 1], strip[i + 2]
                triangle_index += 1
                normal = _average((v0.normal, v1.normal, v2.normal))
                color = fallback_color
                uv = None
                texture_layers: list[_TextureLayer] = []
                if texture_image is not None:
                    color = area_colors[triangle_index]
                    uv = (tuple(v0.uv), tuple(v1.uv), tuple(v2.uv))
                    for stage_index, _stage_image, stage_array, role in material_textures:
                        if map_projection is not None and role == "map_selector":
                            layer_uv = (
                                map_projection.selector_uv(v0.position),
                                map_projection.selector_uv(v1.position),
                                map_projection.selector_uv(v2.position),
                            )
                        elif map_projection is not None and role == "map_projected_light":
                            layer_uv = (
                                map_projection.last_uv(v0.position),
                                map_projection.last_uv(v1.position),
                                map_projection.last_uv(v2.position),
                            )
                        else:
                            use_uv2 = (
                            (stage_index == 2 or role == "callback_uv2_detail")
                            and v0.uv2 is not None
                            and v1.uv2 is not None
                            and v2.uv2 is not None
                            )
                            layer_uv = (
                                tuple(v0.uv2 if use_uv2 else v0.uv),
                                tuple(v1.uv2 if use_uv2 else v1.uv),
                                tuple(v2.uv2 if use_uv2 else v2.uv),
                            )
                        layer_color_scale = material_color_scale
                        if role in {"map_selector", "map_projected_light", "light"}:
                            layer_color_scale = (1.0, 1.0, 1.0)
                        texture_layers.append(
                            _TextureLayer(
                                layer_uv,
                                stage_array,
                                role,
                                color_scale=layer_color_scale,
                                wrap_s=_stage_image.wrap_s,
                                wrap_t=_stage_image.wrap_t,
                            )
                        )
                uses_palette = bool(chunk.format & 3)
                skin = (
                    _VertexSkin(tuple(v0.bone_indices), tuple(v0.bone_weights), uses_palette),
                    _VertexSkin(tuple(v1.bone_indices), tuple(v1.bone_weights), uses_palette),
                    _VertexSkin(tuple(v2.bone_indices), tuple(v2.bone_weights), uses_palette),
                )
                triangles.append(
                    _Triangle(
                        v0.position,
                        v1.position,
                        v2.position,
                        normal,
                        color,
                        skin,
                        uv,
                        texture_array,
                        tuple(texture_layers),
                        material_alpha,
                        blend_mode,
                    )
                )


def _skin_vertex(p, skin: _VertexSkin, world, palette, *, direction: bool = False):
    """Blend ``p`` through each influencing bone's engine matrix (see
    ``engine_pose``): ``palette`` for multi-matrix/composite shapes,
    ``world`` for single-matrix ones."""
    matrices = palette if skin.uses_palette else world
    total = sum(skin.bone_weights) or 1.0
    out = [0.0, 0.0, 0.0]
    used = False
    for index, weight in zip(skin.bone_indices, skin.bone_weights):
        if not 0 <= index < len(matrices):
            continue
        q = engine_pose.apply_direction(matrices[index], p) if direction else engine_pose.apply(matrices[index], p)
        for axis in range(3):
            out[axis] += q[axis] * weight / total
        used = True
    if not used:
        return p
    if direction:
        length = math.sqrt(sum(c * c for c in out))
        if length > 1e-9:
            out = [c / length for c in out]
    return tuple(out)


def _skin_triangles(triangles: list[_Triangle], world, palette) -> list[_Triangle]:
    """Deform ``triangles`` to an engine pose (``engine_pose.pose()``):
    each vertex goes through its bones' matrices exactly as the game draws
    it. Triangles with no skinning data pass through unchanged."""
    skinned: list[_Triangle] = []
    for tri in triangles:
        if tri.skin is None:
            skinned.append(tri)
            continue
        skin_a, skin_b, skin_c = tri.skin
        a = _skin_vertex(tri.a, skin_a, world, palette)
        b = _skin_vertex(tri.b, skin_b, world, palette)
        c = _skin_vertex(tri.c, skin_c, world, palette)
        # the face normal follows the first vertex's bones - a reasonable
        # approximation for this per-face painter's-algorithm renderer.
        normal = _skin_vertex(tri.normal, skin_a, world, palette, direction=True)
        skinned.append(
            _Triangle(
                a,
                b,
                c,
                normal,
                tri.color,
                tri.skin,
                tri.uv,
                tri.texture,
                tri.texture_layers,
                tri.alpha,
                tri.blend_mode,
            )
        )
    return skinned


def _build_loaded_set(
    label: str,
    files: dict[str, bytes],
    loose_animations: list[tuple[str, bytes]],
    map_projection: MapTextureProjection | None = None,
) -> _LoadedSet:
    """Shared plumbing for both loading routes below: given a
    ``{filename: content}`` map already limited to the relevant entries
    (a whole pack for ``_load_model_set()``, or one named group's files
    for ``load_named_model_set()``), decode skeleton/mesh/animations."""
    bones: list[skeleton.Bone] = []
    triangles: list[_Triangle] = []
    animations: list[tuple[str, bytes]] = list(loose_animations)

    tpl_contents = {name: data for name, data in files.items() if Path(name).suffix.lower() == ".tpl"}
    textures_by_index = _load_textures(tpl_contents)

    for name, content in files.items():
        suffix = Path(name).suffix.lower()
        if suffix == ".g":
            bones = skeleton.read_skeleton(io.BytesIO(content))
        elif suffix == ".gs":
            gs_model = model_fmt.read_model_bytes(content)
            _accumulate_mesh(gs_model, triangles, textures_by_index, map_projection=map_projection)
        elif suffix == ".ga":
            animations.append((name, content))

    # confirmed bind-pose world position (skeleton.Bone.position) - see that
    # module's docstring for how this was cross-checked against the mesh.
    bone_markers = {i: bone.position for i, bone in enumerate(bones)}

    return _LoadedSet(label=label, bones=bones, triangles=triangles, bone_markers=bone_markers, animations=animations)


def _load_model_set(label: str, container_path: Path, pending: dict[Path, bytes] | None = None) -> _LoadedSet:
    """The set as stored, or as it will be once ``pending`` (``{file: new
    bytes}``, an import's outputs) is written."""
    if is_map_container(container_path):
        from .map_scene import build_map_scene  # map_scene imports this module

        data = (pending or {}).get(container_path) or container_path.read_bytes()
        files = _unpack(container_path, data)[1]
        scene = build_map_scene(files, map_file.read_map_bytes(files["map.bin"]))
        return replace(scene, label=label)
    files, animations = _set_contents(container_path, pending)
    return _build_loaded_set(label, files, animations)


def _is_battle_container(path: Path) -> bool:
    """``zu/<code>/<code>_<weapon>.pak``: a battle model's uncompressed
    pack (map models and scenery use LZ10-compressed ``.cmp`` packs)."""
    return path.suffix.lower() == ".pak"


def _unpack(path: Path, data: bytes) -> tuple[list[pak.PakEntry], dict[str, bytes]]:
    raw = data if _is_battle_container(path) else lz10.decompress(data)
    entries = pak.read_pak_entries(raw)
    return entries, {e.name: pak.read_pak_file_content(raw, e) for e in entries}


def _pack(path: Path, entries: list[pak.PakEntry], files: dict[str, bytes]) -> bytes:
    packed = pak.pack_pak([(e.name, files[e.name]) for e in entries], [e.reserved for e in entries])
    return packed if _is_battle_container(path) else lz10.compress(packed)


def _read_container(container_path: Path) -> tuple[list[pak.PakEntry], dict[str, bytes]]:
    return _unpack(container_path, container_path.read_bytes())


def _set_containers(container_path: Path) -> list[Path]:
    """Every pack of the set: a battle model's weapon packs, else the one pack."""
    if _is_battle_container(container_path):
        return sorted(container_path.parent.glob(f"{container_path.parent.name}_*.pak"))
    return [container_path]


def _set_contents(
    container_path: Path, pending: dict[Path, bytes] | None = None
) -> tuple[dict[str, bytes], list[tuple[str, bytes]]]:
    """The set's pack files (mesh, skeleton, textures, the pack's own
    animations) and its other animations ``(name, bytes)``, as stored or
    as ``pending`` would write them.

    A map model's other animations are the loose ``.ga`` next to its pack.
    A battle model's are those of every weapon pack; its texture is the
    folder's ``<code>.tpl`` (each unit picks one of the folder's ``.tpl``,
    e.g. ``bole_map1.tpl`` for Boyd in the Prologue)."""
    pending = pending or {}

    def data(path: Path) -> bytes:
        return pending.get(path) or path.read_bytes()

    _entries, files = _unpack(container_path, data(container_path))
    if not _is_battle_container(container_path):
        return files, [(p.name, data(p)) for p in sorted(container_path.parent.glob("*.ga"))]
    files = {n: d for n, d in files.items() if Path(n).suffix.lower() != ".ga"}
    folder = container_path.parent
    texture = folder / f"{folder.name}.tpl"
    if not texture.is_file():
        texture = next(iter(sorted(folder.glob("*.tpl"))), None)
    if texture is not None:
        files[texture.name] = data(texture)
    animations = []
    for pack_path in _set_containers(container_path):
        _e, pack_files = _unpack(pack_path, data(pack_path))
        animations += [(n, d) for n, d in pack_files.items() if Path(n).suffix.lower() == ".ga"]
    return files, animations


def export_set_glb(container_path: Path) -> bytes:
    """A model set (pack plus the loose ``.ga`` next to it) as ``.glb``,
    through :func:`gltf_export.export_glb` - every ``.gs`` in the pack, the
    ``.g`` skeleton, textures resolved the same way the viewer resolves
    them, and every animation the parser accepts."""
    files, other_animations = _set_contents(container_path)
    bones: list[skeleton.Bone] = []
    models, animations = [], []
    for name, content in files.items():
        suffix = Path(name).suffix.lower()
        if suffix == ".g":
            bones = skeleton.read_skeleton(io.BytesIO(content))
        elif suffix == ".gs":
            models.append((Path(name).stem, model_fmt.read_model_bytes(content)))
        elif suffix == ".ga":
            animations.append((Path(name).stem, content))
    animations += [(Path(name).stem, data) for name, data in other_animations]
    tpl_contents = {name: data for name, data in files.items() if Path(name).suffix.lower() == ".tpl"}
    textures = {i: t.image for i, t in _load_textures(tpl_contents).items()}
    decoded = []
    for anim_name, data in animations:
        try:
            decoded.append((anim_name, animation.read_animation_bytes(data)))
        except Exception:  # noqa: BLE001 - skip an animation the parser rejects
            continue
    return gltf_export.export_glb(models, bones, textures, decoded)


@dataclass
class ModelImport:
    """What an import would write, before anything is written: ``outputs``
    (``{file: new bytes}`` - the recompressed pack and any loose files),
    warnings, and for skinned bodies how each glTF joint was matched
    (``gltf_import.StaticBuild.joint_map``)."""

    outputs: dict[Path, bytes]
    warnings: list[str] = field(default_factory=list)
    joint_map: dict[str, tuple[str, str]] = field(default_factory=dict)


def replace_set_with_static_glb(container_path: Path, gltf_path: Path) -> ModelImport:
    """The pack with its single ``.gs`` rebuilt from a glTF as a static
    mesh (``gltf_import``). Shapes follow the bone the original's first
    shape used, in that bone's bind space; the skeleton and animations are
    kept. When the glTF has textures, the pack's ``.tpl`` is replaced by a
    new one holding only them (the new ``.gs`` references nothing else)."""
    entries, files = _read_container(container_path)
    gs_names = [n for n in files if Path(n).suffix.lower() == ".gs"]
    g_names = [n for n in files if Path(n).suffix.lower() == ".g"]
    tpl_names = [n for n in files if Path(n).suffix.lower() == ".tpl"]
    if len(gs_names) != 1:
        raise gltf_import.GltfImportError(f"Expected one .gs in {container_path.name}, found {len(gs_names)}.")
    original = gs_file.read_gs(files[gs_names[0]])
    first = next(iter(original.chunks), None)
    bone = first.bone if first is not None else 0
    gs_bytes, tpl_bytes, warnings = gltf_import.import_static_model(
        gltf_path.read_bytes(),
        skeleton_data=files[g_names[0]] if g_names else None,
        bone=bone,
        base_dir=gltf_path.parent,
        name=Path(gs_names[0]).stem,
    )
    files[gs_names[0]] = gs_bytes
    if tpl_bytes is not None:
        if len(tpl_names) > 1:
            raise gltf_import.GltfImportError(f"{container_path.name} has several .tpl files; not sure which to replace.")
        tpl_name = tpl_names[0] if tpl_names else Path(gs_names[0]).stem + ".tpl"
        if tpl_name not in files:
            entries.append(pak.PakEntry(tpl_name, 0, 0))
        files[tpl_name] = tpl_bytes
    return ModelImport({container_path: _pack(container_path, entries, files)}, warnings)


#: Material names the map loader gives texture-projection callbacks
#: (``setup_map_texture_material_callbacks``); an imported terrain material
#: with one of these names is renamed so it draws as a plain textured mesh.
MAP_CALLBACK_MATERIALS = frozenset(
    {"map_base", "map_wall", "map_water", "kbground", "kbground0", "kbground1", "kbground2", "kbground3", "kbwater"}
)
#: Mesh height per elevation unit of ``map.bin``'s panels: every
#: ``uniquepanelBase`` corner of bmap01/bmap02 sits at ``-elevation / 400``.
MAP_ELEVATION_SCALE = -1.0 / 400.0
MAP_TILE_SIZE = 5.0
#: Largest side of an imported terrain texture (vanilla terrain atlases are
#: 512x1024 CMPR).
MAP_TEXTURE_SIZE = 1024


def is_map_container(path: Path) -> bool:
    """``zmap/<map>/map.cmp``: a chapter's terrain, props and ``map.bin``."""
    return path.name.lower() == "map.cmp" and path.parent.parent.name.lower() == "zmap"


def map_terrain_name(files: dict[str, bytes], map_data: map_file.MapData, folder: str) -> str:
    """The chapter's land terrain model: the base terrain object named after
    its folder (``bmap01``), else the only non-water base terrain object."""
    names = [o.filename for o in map_data.build_desc if map_file.is_base_terrain_object(o) and f"{o.filename}.gs" in files]
    if folder in names:
        return folder
    land = [n for n in names if "water" not in n.lower()]
    if len(land) == 1:
        return land[0]
    raise gltf_import.GltfImportError(f"Could not tell which model is the terrain of {folder} ({', '.join(names) or 'none'}).")


def map_tactical_corners(map_data: map_file.MapData) -> list[tuple[float, float]]:
    """Mesh ``(x, z)`` of every corner of the playable tiles (inside
    ``mapextra.grid_buffer``); tile 0 starts at ``panel_offset * 5``."""
    cap, extra = map_data.capacity, map_data.extra
    if cap is None or extra is None:
        return []
    buffer = extra.grid_buffer if 0 < extra.grid_buffer * 2 < min(cap.x_size, cap.y_size) else 0
    return [
        (MAP_TILE_SIZE * (extra.panel_offset_x + col), MAP_TILE_SIZE * (extra.panel_offset_y + row))
        for col in range(buffer, cap.x_size - buffer + 1)
        for row in range(buffer, cap.y_size - buffer + 1)
    ]


def map_playable_area(map_data: map_file.MapData, terrain_name: str) -> tuple[float, float, float, float] | None:
    """``(x0, x1, z0, z1)`` of the playable tiles (inside ``grid_buffer``)
    in the terrain mesh's coordinates."""
    cap, extra = map_data.capacity, map_data.extra
    if cap is None:
        return None
    buffer = extra.grid_buffer if extra is not None and 0 < extra.grid_buffer * 2 < min(cap.x_size, cap.y_size) else 0
    ox, oy = map_heights.terrain_origin(map_data, terrain_name)
    return (
        MAP_TILE_SIZE * (buffer - ox), MAP_TILE_SIZE * (cap.x_size - buffer - ox),
        MAP_TILE_SIZE * (buffer - oy), MAP_TILE_SIZE * (cap.y_size - buffer - oy),
    )


def surface_heights(triangles: list[_Triangle], points: list[tuple[float, float]]) -> "np.ndarray":
    """Highest surface height of the triangles above each ``(x, z)`` point
    (``nan`` where none covers it)."""
    return map_heights.surface_heights(_triangle_array(triangles), points)


def export_map_terrain_glb(container_path: Path) -> bytes:
    """A chapter's land terrain as ``.glb``, in the mesh's own coordinates
    (5 units per tile, tile 0 at ``panel_offset * 5``), with each material's
    first texture. Props and water are left out."""
    _entries, files = _read_container(container_path)
    map_data = map_file.read_map_bytes(files["map.bin"])
    name = map_terrain_name(files, map_data, container_path.parent.name)
    gs_model = model_fmt.read_model_bytes(files[f"{name}.gs"])
    used = {m.textures[0].tex_id for m in gs_model.materials if m.textures}
    all_textures = _load_textures({n: d for n, d in files.items() if Path(n).suffix.lower() == ".tpl"})
    textures = {i: t.image for i, t in all_textures.items() if i in used}
    # The terrain's one bone is the identity: exported without a skeleton,
    # the mesh re-imports as the static mesh it is.
    return gltf_export.export_glb([(name, gs_model)], [], textures, [])


#: The map_base mask (texture ``index + 1``) spans 128 tiles from the
#: terrain mesh's corner: u = x / 640, v = z / 640 (``map_scene``'s selector
#: projection with ``mapextra``'s offsets cancelled out).
MAP_MASK_SPAN = 640.0


def terrain_mask_image(files: dict[str, bytes], terrain: str) -> Image.Image | None:
    """The road/shore mask of a terrain's ``map_base`` material: the image
    right after its first texture, spanning :data:`MAP_MASK_SPAN` units."""
    gs = gs_file.read_gs(files[f"{terrain}.gs"])
    material = next((m for m in gs.materials if m.name in gltf_import.UV2_MATERIALS and m.textures), None)
    if material is None:
        return None
    images = tpl.read_tpl_images(io.BytesIO(files[map_props.texpack_name(files)]))
    index = material.textures[0].tex_id + 1
    return images[index] if index < len(images) else None


def replace_map_terrain_with_glb(
    container_path: Path,
    gltf_path: Path,
    follow_heights: bool = True,
    conform: bool = True,
    map_texturing: bool = False,
    mask: Image.Image | None = None,
    keep_light: bool = False,
) -> ModelImport:
    """``map.cmp`` with its land terrain rebuilt from a glTF (a static mesh
    in the terrain's own coordinates, as :func:`export_map_terrain_glb`
    writes it). The glTF's images are added to the end of ``texpack.tpl``
    with one white image, so props and water keep their texture numbers.
    Every material ends with a record of that white image: the map loader
    multiplies each terrain material's last texture over the map, and white
    leaves the imported colours unchanged. ``map.bin``'s terrain record gets
    the new bounds. With ``follow_heights``, the tile heights units stand on
    and the props' heights move with the surface (``map_heights``); the
    warnings say how much moved and how many passages the new heights
    block.

    With ``map_texturing``, materials named ``map_base``/``map_wall`` keep
    their name and the game's road/shore texturing: their texture is the
    atlas sampled through both UV sets (glTF ``TEXCOORD_0``/``_1``), blended
    by the grey mask stored right after it (``mask``, else the current
    terrain's; black keeps the first UV set, white the second; see
    :data:`MAP_MASK_SPAN`), and multiplied by a last image: the current
    light overlay with ``keep_light``, else white."""
    entries, files = _read_container(container_path)
    current = dict(files)
    map_data = map_file.read_map_bytes(files["map.bin"])
    name = map_terrain_name(files, map_data, container_path.parent.name)
    original = gs_file.read_gs(files[f"{name}.gs"])
    first = next((c for chunks in original.chunk_lists for c in chunks), None)
    bone = first.bone if first is not None else 0
    last_record = next((m.textures[-1] for m in original.materials if m.textures), None)

    scene = gltf_import.read_gltf(gltf_path.read_bytes(), gltf_path.parent)
    warnings = []
    old_mask = terrain_mask_image(files, name)
    old_base = next((m for m in original.materials if m.name in gltf_import.UV2_MATERIALS and len(m.textures) >= 2), None)
    for material in scene.materials:
        if map_texturing and material.name in gltf_import.UV2_MATERIALS:
            continue
        if material.name in MAP_CALLBACK_MATERIALS:
            warnings.append(f"Material {material.name} renamed {material.name}_mesh: the map loader would give it projected textures.")
            material.name += "_mesh"
    area = map_playable_area(map_data, name) if conform else None
    if area is not None:
        cut = terrain_conform.conform_to_tiles(scene, *area)
        if cut:
            warnings.append(
                f"The playable area was fitted to the tile grid ({cut} triangles cut): the move grid and units use "
                "one flat panel per tile half, so the ground there is flattened onto those panels."
            )
    texpack = next((n for n in files if n.lower() == "texpack.tpl"), None)
    if texpack is None:
        raise gltf_import.GltfImportError(f"{container_path.name} has no texpack.tpl.")
    base = len(tpl.read_tpl_image_info(io.BytesIO(files[texpack])))
    white = gs_file.GsTexture((1, 0), -1, last_record.params if last_record else (257, 0, 0, 0, 0), 1.0, 1.0, 0)
    world = skeleton.IDENTITY_3X4
    if f"{name}.g" in files:
        bones = skeleton.read_skeleton_file(files[f"{name}.g"]).bones
        world = skeleton.bind_world_matrices(bones)[bone] if 0 <= bone < len(bones) else world
    build = gltf_import.build_static_gs(
        scene, bone=bone, bone_world=world, name=name, tex_id_base=base, extra_textures=(white,)
    )
    warnings += build.warnings
    images = list(build.images)
    textured = [m for m in build.gs.materials if m.name in gltf_import.UV2_MATERIALS] if map_texturing else []
    mask_at = None
    if textured:
        atlas_ids = {m.textures[0].tex_id for m in textured if len(m.textures) > 1}
        if len(atlas_ids) != 1:
            raise gltf_import.GltfImportError(
                "Map texturing needs every map_base/map_wall material to use one and the same texture (the atlas)."
            )
        source_mask = mask if mask is not None else old_mask
        if source_mask is None:
            raise gltf_import.GltfImportError("This terrain has no road/shore mask to keep: choose a mask image.")
        mask_at = atlas_ids.pop() - base + 1  # the mask must be the image right after the atlas
        images.insert(mask_at, source_mask)
        for material in build.gs.materials:
            material.textures = [
                replace(t, tex_id=t.tex_id + 1) if 0 <= t.tex_id - base and t.tex_id - base >= mask_at else t
                for t in material.textures
            ]
        if not any(t.uvs2 for i in scene.triangles for t in scene.triangles[i]):
            warnings.append("The glTF has no second UV set (TEXCOORD_1): both atlas samples use the first, so the mask shows nothing.")
    white_id = base + len(images)
    last_image = Image.new("RGBA", (8, 8), (255, 255, 255, 255))
    last_entry = (last_image, tpl.FORMAT_I4, tpl.WRAP_CLAMP)
    if map_texturing and keep_light and last_record is not None:
        old_images = tpl.read_tpl_images(io.BytesIO(current[texpack]))
        if 0 <= last_record.tex_id < len(old_images):
            last_entry = (old_images[last_record.tex_id], tpl.FORMAT_I4, tpl.WRAP_CLAMP)
    for material in build.gs.materials:
        material.textures[-1] = replace(white, tex_id=white_id)
    for material in textured:
        atlas = material.textures[0].tex_id
        template = old_base.textures if old_base is not None else [material.textures[0], material.textures[0]]
        material.textures = [
            replace(material.textures[0], params=template[0].params),
            replace(material.textures[0], tex_id=atlas + 1, params=template[1].params),
            replace(white, tex_id=white_id),
        ]
    # Images identical to ones already in texpack.tpl (a re-imported export)
    # are reused, the atlas and its mask only as an adjacent pair.
    def pixels(img: Image.Image) -> tuple:
        return img.size, img.convert("RGBA").tobytes()

    known = [pixels(e) for e in tpl.read_tpl_images(io.BytesIO(files[texpack]))]
    reuse: dict[int, int] = {}
    pair = (mask_at - 1, mask_at) if mask_at is not None else ()
    if pair:
        wanted = (pixels(images[pair[0]]), pixels(images[pair[1]]))
        at = next((i for i in range(len(known) - 1) if (known[i], known[i + 1]) == wanted), None)
        if at is not None:
            reuse.update({pair[0]: at, pair[1]: at + 1})
    for k, img in enumerate(images):
        if k not in reuse and k not in pair and pixels(img) in known:
            reuse[k] = known.index(pixels(img))
    last_key = len(images)
    if pixels(last_entry[0]) in known:
        reuse[last_key] = known.index(pixels(last_entry[0]))
    added, appended = [], []
    for k, img in enumerate(images):
        if k in reuse:
            continue
        appended.append(k)
        if k == mask_at:
            added.append((img, tpl.FORMAT_I4, tpl.WRAP_REPEAT))
        else:
            added.append((*gltf_import.texture_for_tpl(img, MAP_TEXTURE_SIZE), tpl.WRAP_REPEAT))
    if last_key not in reuse:
        appended.append(last_key)
        added.append(last_entry)
    if added:
        files[texpack], first_new = tpl.append_images(files[texpack], added)
        reuse.update({k: first_new + j for j, k in enumerate(appended)})
    final = {base + k: new_id for k, new_id in reuse.items()}
    for material in build.gs.materials:
        material.textures = [replace(t, tex_id=final.get(t.tex_id, t.tex_id)) for t in material.textures]
    if textured:
        warnings.append(
            "Map texturing kept: the atlas is sampled through both UV sets and blended by the "
            + ("new" if mask is not None else "current") + " road/shore mask"
            + (", under the current light overlay." if keep_light else ", with a white light overlay.")
        )
    files[f"{name}.gs"] = gs_file.write_gs(build.gs)
    # Images no model uses any more (the replaced terrain's) are dropped.
    map_props.compact_texpack(files)
    if len(files[texpack]) > gs_stats.MAP_TEXPACK_LIMIT:
        warnings.append(
            f"texpack.tpl grows to {len(files[texpack]):,} bytes, above every vanilla map "
            f"({gs_stats.MAP_TEXPACK_LIMIT:,}); the game has not been seen loading that much."
        )

    terrain = next(o for o in map_data.build_desc if o.filename == name)
    lo, hi = build.gs.bbox_min, build.gs.bbox_max
    map_bin = files["map.bin"]
    for field_name, value in (
        ("offset_x", lo[0]), ("offset_y", lo[1]), ("offset_z", lo[2]),
        ("size_x", hi[0]), ("size_y", hi[1]), ("size_z", hi[2]),  # the bounding box's maximum corner
    ):
        map_bin = map_file.patch_object_field(map_bin, terrain, field_name, float(value))
    files["map.bin"] = map_bin

    corners = map_tactical_corners(map_data)
    old = load_named_model_set(current, name)
    new = load_named_model_set(files, name)
    if old is not None and new is not None:
        old_tris, new_tris = _triangle_array(old.triangles), _triangle_array(new.triangles)
        if corners:
            before = map_heights.surface_heights(old_tris, corners)
            after = map_heights.surface_heights(new_tris, corners)
            missing = int(np.sum(~np.isnan(before) & np.isnan(after)))
            if missing:
                warnings.append(
                    f"{missing} of {len(corners)} playable tile corners have no terrain under them any more; "
                    "their heights in map.bin are left as they were."
                )
        if follow_heights:
            open_before = _open_passages(map_file.read_map_bytes(files["map.bin"]))
            update = map_heights.follow_terrain(files["map.bin"], name, old_tris, new_tris)
            files["map.bin"] = update.map_bin
            if update.corners_changed:
                warnings.append(
                    f"The ground moved at {update.corners_changed} tile corners (largest {update.largest_change:.2f}): "
                    f"map.bin's heights of {update.tiles_changed} tiles and {update.props_moved} props follow it."
                )
                if update.props_kept:
                    warnings.append(
                        f"{update.props_kept} props were not standing on the old ground (sunk, floating or on another "
                        "object) and keep their height."
                    )
                if update.corners_on_props:
                    warnings.append(
                        f"{update.corners_on_props} tile corners stand on a prop (a bridge or floor), not the ground, "
                        "and keep their height."
                    )
                blocked = open_before - _open_passages(map_file.read_map_bytes(update.map_bin))
                if blocked > 0:
                    warnings.append(
                        f"{blocked} passages between neighbouring tiles are now blocked: the game closes an edge "
                        "whose corners differ by one unit (400 elevation) or more."
                    )
    return ModelImport({container_path: _pack(container_path, entries, files)}, warnings)


def _triangle_array(triangles: list[_Triangle]) -> "np.ndarray":
    return np.array([[t.a, t.b, t.c] for t in triangles], dtype=float).reshape(-1, 3, 3)


def _open_passages(data: map_file.MapData) -> int:
    """Open directional passages (low bits 0-3) over the whole grid."""
    if data.capacity is None:
        return 0
    status = map_file.compose_link_status_grid(data)
    return sum(bin(value & 0xF).count("1") for column in status for value in column if value > 0)


#: Every vanilla character texture (``ymu/<class>/tex_N.tpl``) is one
#: 128x128 CMPR image; imported body textures are fitted to the same.
BODY_TEXTURE_SIZE = 128


def _texture_variant_files(container_path: Path, files: dict[str, bytes]) -> dict[str, bytes]:
    """Every texture variant of a character class: the pack's ``tex_N.tpl``
    entries (keys as-is) and the loose ``tex_N.tpl`` files next to the pack
    (keys are their full paths). Which one a unit uses is chosen per unit
    (``texnum``); a body's materials all use ``tex_id`` 0 of it."""
    variants = {name: data for name, data in files.items() if Path(name).suffix.lower() == ".tpl"}
    for path in sorted(container_path.parent.glob("*.tpl")):
        variants[str(path)] = path.read_bytes()
    return variants


def _same_image(a: Image.Image, b: Image.Image) -> bool:
    return a.size == b.size and a.convert("RGBA").tobytes() == b.convert("RGBA").tobytes()


def replace_body_with_glb(container_path: Path, gltf_path: Path) -> ModelImport:
    """Rebuild a character pack's ``body.gs`` from a glTF weighted to the
    class skeleton (``gltf_import.import_skinned_model``); the skeleton and
    every animation are kept. Writes the pack, plus the loose ``tex_N.tpl``
    files when they change. See :func:`_rebuild_character` for textures."""
    return _rebuild_character(container_path, gltf_path)


def replace_rig_with_glb(container_path: Path, gltf_path: Path) -> ModelImport:
    """Replace a character class's whole rig from a glTF (Phase 4): a new
    ``skeleton.g`` built from the armature (``gltf_import.build_skeleton``),
    the body weighted to it, and **every** animation of the class - the
    pack's and the loose ones - rebuilt from the glTF animation of the same
    name, keeping each replaced file's events unless the glTF carries its
    own. Refused when an animation is missing (the old ones can't drive a
    different skeleton) or when the armature lacks one of the old rig's
    anchor bones (``_s1_``, ``_sw1_``...)."""
    _entries, files = _read_container(container_path)
    g_names = [n for n in files if Path(n).suffix.lower() == ".g"]
    if not g_names:
        raise gltf_import.GltfImportError(f"{container_path.name} has no skeleton.")
    gltf_data = gltf_path.read_bytes()
    new_skeleton, warnings = gltf_import.build_skeleton(gltf_data, gltf_path.parent)
    old_bones = skeleton.read_skeleton_file(files[g_names[0]]).bones
    errors, rig_warnings = gltf_import.check_rig_against(new_skeleton.bones, old_bones)
    warnings += rig_warnings

    targets: dict[str, bytes] = {n: files[n] for n in files if Path(n).suffix.lower() == ".ga"}
    targets.update({p.name: p.read_bytes() for p in sorted(container_path.parent.glob("*.ga"))})
    available = {name.lower(): name for name in gltf_import.list_animations(gltf_data, gltf_path.parent)}
    missing = [t for t in targets if Path(t).stem.lower() not in available]
    if missing:
        errors.append(
            f"The glTF lacks {len(missing)} of the class's {len(targets)} animations (a new skeleton needs all of "
            "them, named like the files): " + ", ".join(sorted(missing))
        )
    if errors:
        raise gltf_import.GltfImportError("\n".join(errors))
    extra = sorted(set(available) - {Path(t).stem.lower() for t in targets})
    if extra:
        warnings.append("glTF animations with no matching class animation (ignored): " + ", ".join(extra))

    g_bytes = skeleton.write_skeleton_file(new_skeleton)
    animations: dict[str, bytes] = {}
    event_problems: list[str] = []
    for target, template in targets.items():
        ga, anim_warnings = gltf_import.import_animation(
            gltf_data, g_bytes, animation_name=available[Path(target).stem.lower()], template=template, base_dir=gltf_path.parent
        )
        animations[target] = ga
        warnings += [f"{target}: {w}" for w in anim_warnings]
        event_problems += rig_contract.event_errors(target, ga, template)
    if event_problems:
        raise gltf_import.GltfImportError("\n".join(event_problems))
    warnings += rig_contract.visibility_warnings(
        old_bones, targets, skeleton.read_skeleton_file(g_bytes).bones, animations
    )
    result = _rebuild_character(container_path, gltf_path, skeleton_data=g_bytes, animations=animations)
    result.warnings[:0] = warnings
    return result


def _rebuild_character(
    container_path: Path,
    gltf_path: Path,
    *,
    skeleton_data: bytes | None = None,
    animations: dict[str, bytes] | None = None,
) -> ModelImport:
    """Rebuild ``body.gs`` (and, for a new rig, ``skeleton.g`` and the
    given animations - pack entries or loose files by name) and repack.

    Textures: a body uses one texture (``tex_id`` 0) and the unit picks one
    of the class's ``tex_N.tpl`` variants. A glTF texture identical to one
    of those variants (what Export .glb writes) keeps every variant as it
    is; a new texture replaces all of them (army colours are lost); no
    texture keeps the variants and points the materials at them."""
    entries, files = _read_container(container_path)
    gs_names = [n for n in files if Path(n).suffix.lower() == ".gs"]
    g_names = [n for n in files if Path(n).suffix.lower() == ".g"]
    if len(gs_names) != 1 or not g_names:
        raise gltf_import.GltfImportError(f"{container_path.name} is not a character pack (one .gs and a .g).")
    # Every animation the body will play, to size the blended vertices'
    # fixed-point range (gltf_import.build_skinned_gs).
    class_animations = {n: files[n] for n in files if Path(n).suffix.lower() == ".ga"}
    class_animations.update({p.name: p.read_bytes() for p in sorted(container_path.parent.glob("*.ga"))})
    class_animations.update(animations or {})
    parsed_animations = tuple(animation.read_animation_bytes(data) for data in class_animations.values())
    fallback = None
    if skeleton_data is None:
        original = model_fmt.read_model_bytes(files[gs_names[0]])
        usage: dict[int, int] = {}
        for chunk in original.chunks:
            for strip in chunk.strips:
                for v in strip:
                    if v.bone_indices:
                        usage[v.bone_indices[0]] = usage.get(v.bone_indices[0], 0) + 1
        fallback = max(usage, key=usage.get) if usage else None
    build = gltf_import.import_skinned_build(
        gltf_path.read_bytes(),
        skeleton_data if skeleton_data is not None else files[g_names[0]],
        fallback_bone=fallback,
        base_dir=gltf_path.parent,
        name=Path(gs_names[0]).stem,
        animations=parsed_animations,
    )
    gs, images, warnings = build.gs, build.images, list(build.warnings)

    variants = _texture_variant_files(container_path, files)
    new_tpl: bytes | None = None
    if len(images) > 1:
        raise gltf_import.GltfImportError(
            f"The model uses {len(images)} different textures; a map model uses a single texture image."
        )
    if not images:
        for material in gs.materials:
            material.textures = [gs_file.GsTexture((1, 0), 0, (257, 0, 0, 0, 0), 1.0, 1.0, 0)]
        gs_bytes = gs_file.write_gs(gs)
        warnings.append("The model has no texture: it uses the class's existing texture with its own UVs.")
    else:
        for material in gs.materials:
            if not material.textures:
                material.textures = [gs_file.GsTexture((1, 0), 0, (257, 0, 0, 0, 0), 1.0, 1.0, 0)]
        gs_bytes = gs_file.write_gs(gs)
        known = []
        for data in variants.values():
            try:
                known += tpl.read_tpl_images(io.BytesIO(data))
            except Exception:  # noqa: BLE001 - an unreadable variant just can't match
                continue
        if not any(_same_image(images[0], k) for k in known):
            rgba, _fmt = gltf_import.texture_for_tpl(images[0], max_size=BODY_TEXTURE_SIZE)
            new_tpl = tpl.build_tpl([(rgba, tpl.FORMAT_CMPR)])
            warnings.append(
                f"New texture: all {len(variants)} texture variants (tex_N.tpl) are replaced with it, "
                "so every unit of this class shows the same colours."
            )

    files[gs_names[0]] = gs_bytes
    out: dict[Path, bytes] = {}
    if skeleton_data is not None:
        files[g_names[0]] = skeleton_data
    for name, data in (animations or {}).items():
        if name in files:
            files[name] = data
        else:
            out[container_path.parent / name] = data
    if new_tpl is not None:
        for key in variants:
            if key in files:
                files[key] = new_tpl
            else:
                out[Path(key)] = new_tpl
    out = {container_path: _pack(container_path, entries, files), **out}
    return ModelImport(out, warnings, build.joint_map)


#: Battle-model textures (``zu/<code>/*.tpl``) hold 256x256 images.
BATTLE_TEXTURE_SIZE = 256


#: Weapon socket bone names in ``zu/`` skeletons: ``_r_hand_`` (the weapon),
#: ``_ar1_``/``_ar2_`` (arrows), ``BW001``.. (bow). The engine attaches the
#: real weapon actor to the hand (``attach_hand_item_and_update_label``:
#: ``l_hand`` for weapon category 3, else ``r_hand``); the body's own
#: weapon meshes are hidden placeholders (shape flag 0x400) on these bones.
_WEAPON_BONE_RE = re.compile(r"^(_.+_|BW\d+)$")


def battle_weapon_bones(gs_bytes: bytes, g_bytes: bytes) -> set[int]:
    """Bones a battle body keeps free of visible geometry: those only its
    hidden placeholder shapes use, plus socket-named bones (``_r_hand_``,
    ``_cam_``, ``_root_``, ``BW001``...) no visible shape uses."""
    gs_model = model_fmt.read_model_bytes(gs_bytes)
    names = [b.name for b in skeleton.read_skeleton_file(g_bytes).bones]
    hidden, visible = set(), set()
    for chunk in gs_model.chunks:
        used = {i for strip in chunk.strips for v in strip for i in v.bone_indices}
        (hidden if chunk.hidden else visible).update(used)
    named = {i for i, n in enumerate(names) if _WEAPON_BONE_RE.match(n)}
    return (hidden | named) - visible


def vertices_on_bones(gs_bytes: bytes, bones: set[int]) -> int:
    """Visible strip vertices whose largest weight is on one of ``bones``."""
    count = 0
    for chunk in model_fmt.read_model_bytes(gs_bytes).chunks:
        if chunk.hidden:
            continue
        for strip in chunk.strips:
            for v in strip:
                if v.bone_indices:
                    top = max(range(len(v.bone_indices)), key=lambda k: v.bone_weights[k] if k < len(v.bone_weights) else 0)
                    count += v.bone_indices[top] in bones
    return count


def _fallback_animation(stem: str, available: dict[str, str]) -> str | None:
    """For a new rig, the glTF animation that stands in for a missing one:
    a follow-up clip (``fig1_cr1_ax_at1``) reuses its base clip
    (``fig1_cr1_ax``), then a clip reuses the same role of another weapon
    (``fig1_dam_no`` from ``fig1_dam_ax``)."""
    parts = stem.split("_")
    if len(parts) < 3:
        return None
    if len(parts) > 3:
        base = "_".join(parts[:3])
        if base in available:
            return base
    same_role = sorted(
        k for k in available if "@" not in k and k.split("_")[:2] == parts[:2] and len(k.split("_")) == 3
    )
    return same_role[0] if same_role else None


def replace_battle_rig_with_glb(container_path: Path, gltf_path: Path, *, new_rig: bool | None = None) -> ModelImport:
    """Replace a battle model's skeleton, mesh and the animations of every
    weapon pack from a glTF armature. An animation the glTF carries under a
    pack file's name (``fig1_at1_ax``, or ``fig1_dam_ax@ha`` for one pack
    only) is imported, keeping the file's events. The others:

    - same rig (most body bones keep their names): retargeted from the old
      skeleton by bone name (``animation.retarget_animation``: tracks of
      bones the new rig lacks are dropped, translate and pivot keys follow
      the new rest pose);
    - **new rig** (``new_rig``, by default when fewer than half the old body
      bones are in the armature): retargeting would drop every track, so a
      missing follow-up clip reuses its base clip and a missing clip the
      same role of another weapon (:func:`_fallback_animation`), each with
      its own file's events; anything still missing refuses the import.

    Refused when the armature lacks one of the old rig's anchor bones, or
    when an imported animation lacks an event code the battle script waits
    for (``rig_contract.event_errors``)."""
    paks = _set_containers(container_path)
    _entries, files = _read_container(paks[0])
    g_names = [n for n in files if Path(n).suffix.lower() == ".g"]
    if not g_names:
        raise gltf_import.GltfImportError(f"{container_path.name} has no skeleton.")
    gltf_data = gltf_path.read_bytes()
    old_bones = skeleton.read_skeleton_file(files[g_names[0]]).bones
    new_skeleton, warnings = gltf_import.build_skeleton(gltf_data, gltf_path.parent, template=old_bones)
    errors, rig_warnings = gltf_import.check_rig_against(new_skeleton.bones, old_bones)
    if errors:
        raise gltf_import.GltfImportError("\n".join(errors))
    warnings += rig_warnings
    g_bytes = skeleton.write_skeleton_file(new_skeleton)
    new_bones = skeleton.read_skeleton_file(g_bytes).bones

    old_names = [b.name for b in old_bones]
    new_names = [b.name for b in new_bones]
    old_values = [list(engine_pose.bone_values(b)) for b in old_bones]
    new_values = [list(engine_pose.bone_values(b)) for b in new_bones]
    available = {name.lower(): name for name in gltf_import.list_animations(gltf_data, gltf_path.parent)}
    body_names = {n for n in old_names if not gltf_import.is_anchor_name(n)}
    if new_rig is None:
        new_rig = len(body_names & set(new_names)) < len(body_names) / 2
    pack_animations: dict[Path, dict[str, bytes]] = {}
    imported = retargeted = 0
    dropped_bones: set[str] = set()
    missing: list[str] = []
    reused: list[str] = []
    event_problems: list[str] = []
    cache: dict[tuple[str, bytes], tuple[bytes, list[str]]] = {}
    for pack_path in paks:
        _e, pack_files = _read_container(pack_path)
        weapon = pack_path.stem.rsplit("_", 1)[-1].lower()
        rebuilt = {}
        for name, data in pack_files.items():
            if Path(name).suffix.lower() != ".ga":
                continue
            stem = Path(name).stem.lower()
            source = available.get(f"{stem}@{weapon}") or available.get(stem)
            if source is None and new_rig:
                fallback = _fallback_animation(stem, available)
                if fallback is not None:
                    source = available[fallback]
                    reused.append(f"{name} ({weapon}) from {source}")
            if source is not None:
                key = (source, data)
                if key not in cache:
                    cache[key] = gltf_import.import_animation(
                        gltf_data, g_bytes, animation_name=source, template=data, base_dir=gltf_path.parent
                    )
                ga, anim_warnings = cache[key]
                warnings += [f"{name}: {w}" for w in anim_warnings]
                event_problems += rig_contract.event_errors(f"{name} ({weapon})", ga, data)
                imported += 1
            elif new_rig:
                missing.append(f"{name} ({weapon})")
                continue
            else:
                moved, dropped = animation.retarget_animation(
                    animation.read_animation_bytes(data), old_names, old_values, new_names, new_values
                )
                ga = animation.write_animation(moved)
                dropped_bones.update(dropped)
                retargeted += 1
            rebuilt[name] = ga
        pack_animations[pack_path] = rebuilt
    problems = []
    if missing:
        problems.append(
            "A new skeleton needs every animation (named like the files; see Rig kit...). Missing: " + ", ".join(missing)
        )
    problems += event_problems
    if problems:
        raise gltf_import.GltfImportError("\n".join(problems))
    if reused:
        warnings.append("Animations filled from another clip: " + "; ".join(reused))
    warnings.append(
        f"{imported} animations imported from the glTF, {retargeted} retargeted from the old skeleton by bone name."
    )
    if dropped_bones:
        warnings.append(
            "Tracks of bones the new skeleton lacks were dropped from the retargeted animations: "
            + ", ".join(sorted(dropped_bones))
        )
    added = sorted(set(new_names) - set(old_names))
    if added and retargeted:
        warnings.append("New bones keep their bind pose in the retargeted animations: " + ", ".join(added))
    result = replace_battle_body_with_glb(container_path, gltf_path, skeleton_data=g_bytes, pack_animations=pack_animations)
    result.warnings[:0] = warnings
    return result


def replace_battle_body_with_glb(
    container_path: Path,
    gltf_path: Path,
    *,
    skeleton_data: bytes | None = None,
    pack_animations: dict[Path, dict[str, bytes]] | None = None,
) -> ModelImport:
    """Rebuild a battle model's mesh (``zu/<code>/<code>.gs``, the same in
    every weapon pack) from a glTF weighted to its skeleton.

    Every triangle goes to composite (CPU-blended) shapes, as in every
    vanilla battle model; multi-matrix shapes are drawn misplaced in battle.
    The blended range is sized from the animations of every weapon pack.
    Textures: each unit picks one of the folder's ``.tpl`` files. glTF
    images all found in one of them keep every file and point the
    materials at those images; new images replace every ``.tpl`` of the
    folder (each character's own colours are lost); no image keeps the
    textures, giving each material the texture records of the original
    material of the same name. ``skeleton_data`` and ``pack_animations``
    (per pack, file name -> ``.ga``) replace the rig too
    (:func:`replace_battle_rig_with_glb`)."""
    paks = _set_containers(container_path)
    _entries, files = _read_container(paks[0])
    gs_names = [n for n in files if Path(n).suffix.lower() == ".gs"]
    g_names = [n for n in files if Path(n).suffix.lower() == ".g"]
    if len(gs_names) != 1 or not g_names:
        raise gltf_import.GltfImportError(f"{container_path.name} is not a battle model (one .gs and a .g).")
    original = gs_file.read_gs(files[gs_names[0]])
    parsed = []
    for pack_path in paks:
        _e, pack_files = _read_container(pack_path)
        pack_files.update((pack_animations or {}).get(pack_path, {}))
        parsed += [animation.read_animation_bytes(d) for n, d in pack_files.items() if Path(n).suffix.lower() == ".ga"]
    build = gltf_import.import_skinned_build(
        gltf_path.read_bytes(),
        skeleton_data if skeleton_data is not None else files[g_names[0]],
        base_dir=gltf_path.parent,
        name=Path(gs_names[0]).stem,
        animations=tuple(parsed),
        composite_only=True,
    )
    gs, images, warnings = build.gs, build.images, list(build.warnings)

    template = next((t for m in original.materials for t in m.textures), None)

    def texture_record(tex_id: int) -> gs_file.GsTexture:
        if template is None:
            return gs_file.GsTexture((1, 0), tex_id, (257, 0, 0, 0, 0), 1.0, 1.0, 0)
        return gs_file.GsTexture(template.flags, tex_id, template.params, template.scale_u, template.scale_v, template.extra)

    folder = container_path.parent
    variants = {p: p.read_bytes() for p in sorted(folder.glob("*.tpl"))}
    new_tpl: bytes | None = None
    if not images:
        by_name = {m.name: m for m in original.materials}
        for material in gs.materials:
            source = by_name.get(material.name)
            material.textures = (
                [gs_file.GsTexture(t.flags, t.tex_id, t.params, t.scale_u, t.scale_v, t.extra) for t in source.textures]
                if source is not None
                else [texture_record(0)]
            )
        warnings.append(
            "The model has no texture: materials named like an original material keep its textures, the others "
            "use image 0 of the unit's texture file."
        )
    else:
        mapping = None
        for data in variants.values():
            try:
                known = tpl.read_tpl_images(io.BytesIO(data))
            except Exception:  # noqa: BLE001 - an unreadable file just can't match
                continue
            found = [next((j for j, k in enumerate(known) if _same_image(image, k)), None) for image in images]
            if all(j is not None for j in found):
                mapping = found
                break
        if mapping is None:
            new_tpl = tpl.build_tpl(
                [gltf_import.texture_for_tpl(image, max_size=BATTLE_TEXTURE_SIZE) for image in images]
            )
            mapping = list(range(len(images)))
            warnings.append(
                f"New textures: all {len(variants)} texture files of {folder.name} are replaced, so every unit using "
                "this battle model shows the same colours."
            )
        for material in gs.materials:
            material.textures = [texture_record(mapping[t.tex_id]) for t in material.textures]

    gs_bytes = gs_file.write_gs(gs)
    old_names = [b.name for b in skeleton.read_skeleton_file(files[g_names[0]]).bones]
    names = [b.name for b in skeleton.read_skeleton_file(skeleton_data or files[g_names[0]]).bones]
    socket_names = {old_names[i] for i in battle_weapon_bones(files[gs_names[0]], files[g_names[0]]) if i < len(old_names)}
    weapon_bones = {i for i, n in enumerate(names) if n in socket_names}
    on_weapon = vertices_on_bones(gs_bytes, weapon_bones)
    if on_weapon:
        listed = ", ".join(sorted(socket_names))
        warnings.append(
            f"{on_weapon} visible vertices are bound to socket bones the original body keeps free ({listed}). "
            "The game attaches the real weapon to the hand in battle, so a weapon modelled into the body is drawn "
            "next to it; camera, foot and root sockets carry no geometry either."
        )
    out: dict[Path, bytes] = {}
    for pack_path in paks:
        entries, pack_files = _read_container(pack_path)
        pack_files[gs_names[0]] = gs_bytes
        if skeleton_data is not None:
            pack_files[g_names[0]] = skeleton_data
        pack_files.update((pack_animations or {}).get(pack_path, {}))
        out[pack_path] = _pack(pack_path, entries, pack_files)
    if new_tpl is not None:
        for path in variants:
            out[path] = new_tpl
    return ModelImport(out, warnings, build.joint_map)


def set_animation_names(container_path: Path) -> list[str]:
    """The ``.ga`` a character set can play: the pack's own (``wait``/``move``)
    then the loose battle animations next to it."""
    files, other_animations = _set_contents(container_path)
    names = [n for n in files if Path(n).suffix.lower() == ".ga"]
    return names + [name for name, _data in other_animations]


def set_animations_by_pack(container_path: Path) -> list[tuple[str, str, bytes]]:
    """``(file name, pack, data)`` of every animation of the set: a battle
    model's per weapon pack (``ax``, ``ha``...), a map model's ``pack`` and
    ``loose`` ones."""
    out: list[tuple[str, str, bytes]] = []
    if _is_battle_container(container_path):
        for pack_path in _set_containers(container_path):
            _e, files = _read_container(pack_path)
            weapon = pack_path.stem.rsplit("_", 1)[-1]
            out += [(n, weapon, d) for n, d in files.items() if Path(n).suffix.lower() == ".ga"]
        return out
    files, loose = _set_contents(container_path)
    out += [(n, "pack", d) for n, d in files.items() if Path(n).suffix.lower() == ".ga"]
    return out + [(n, "loose", d) for n, d in loose]


def kit_animation_names(entries: list[tuple[str, str, bytes]]) -> list[tuple[str, str, str, bytes]]:
    """``(glTF animation name, file, pack, data)``: the file's stem, or
    ``stem@pack`` when packs hold different files of the same name (the
    name the rig import looks for first)."""
    by_name: dict[str, list[tuple[str, str, bytes]]] = {}
    for name, pack, data in entries:
        by_name.setdefault(name, []).append((name, pack, data))
    out = []
    for name, group in by_name.items():
        if len({d for _n, _p, d in group}) == 1:
            out.append((Path(name).stem, name, group[0][1], group[0][2]))
        else:
            out += [(f"{Path(name).stem}@{pack}", name, pack, data) for _n, pack, data in group]
    return out


def _files_root(container_path: Path) -> Path:
    """The disc's ``files`` folder above a ``ymu/``/``zu/`` set."""
    return container_path.parent.parent.parent


def rig_kit_glb(container_path: Path) -> tuple[bytes, list[skeleton.Bone], list[tuple[str, str, str, bytes]]]:
    """The rig kit's ``.glb`` (skeleton, body and every animation named as
    the rig imports look for them), the skeleton and the named animations."""
    files, _other = _set_contents(container_path)
    bones: list[skeleton.Bone] = []
    models = []
    for name, content in files.items():
        suffix = Path(name).suffix.lower()
        if suffix == ".g":
            bones = skeleton.read_skeleton(io.BytesIO(content))
        elif suffix == ".gs":
            models.append((Path(name).stem, model_fmt.read_model_bytes(content)))
    named = kit_animation_names(set_animations_by_pack(container_path))
    tpl_contents = {name: data for name, data in files.items() if Path(name).suffix.lower() == ".tpl"}
    textures = {i: t.image for i, t in _load_textures(tpl_contents).items()}
    decoded = []
    for gltf_name, _file, _pack, data in named:
        try:
            decoded.append((gltf_name, animation.read_animation_bytes(data)))
        except Exception:  # noqa: BLE001 - skip an animation the parser rejects
            continue
    return gltf_export.export_glb(models, bones, textures, decoded), bones, named


def _map_weapon_bones(bones: list[skeleton.Bone], named: list[tuple[str, str, str, bytes]]) -> set[str]:
    """A map model's weapon bones (the top ones of what its animations show
    and hide, ``Ax``/``Ax1`` on the Fighter)."""
    switchable = set().union(*rig_contract.weapon_bones(bones, {n: d for n, _f, _p, d in named}).values())
    by_name = {b.name: b for b in bones}
    return {
        n for n in switchable
        if not gltf_import.is_anchor_name(n)
        and not (0 <= by_name[n].parent_index < len(bones) and bones[by_name[n].parent_index].name in switchable)
    }


def map_triangle_budget(container_path: Path) -> int:
    """The triangle count to suggest when a map model is reduced: the
    current body's, or 500 (about a vanilla class's) when it is missing or
    above the largest vanilla map model (``gs_stats.MAP_BODY_LIMITS``)."""
    try:
        files, _other = _set_contents(container_path)
        current = max(gs_stats.model_stats(d).triangles for n, d in files.items() if Path(n).suffix.lower() == ".gs")
    except Exception:  # noqa: BLE001
        return 500
    return current if current <= gs_stats.MAP_BODY_LIMITS["triangles"] else 500


def map_locked_joints(container_path: Path) -> set[str]:
    """The joints a map model reduction leaves alone: the set's weapon
    bones (``Ax``/``Ax1``...), whose small meshes are switched by scale."""
    try:
        _glb, bones, named = rig_kit_glb(container_path)
    except Exception:  # noqa: BLE001
        return set()
    return _map_weapon_bones(bones, named)


def reduce_map_glb(
    container_path: Path, gltf_path: Path, target: int, saved_path: Path | None = None
) -> tuple[Path, mesh_reduce.ReduceResult]:
    """A copy of a glTF for a map set with its meshes reduced to about
    ``target`` triangles (``mesh_reduce.reduce_glb``, the set's weapon
    bones kept). Written to ``saved_path`` (default: next to the source,
    ``<name>_<target>tris.glb``); returns that path and the figures."""
    result = mesh_reduce.reduce_glb(
        gltf_path.read_bytes(), target, gltf_path.parent, locked_joints=map_locked_joints(container_path)
    )
    path = saved_path or gltf_path.with_name(f"{gltf_path.stem}_{target}tris.glb")
    path.write_bytes(result.glb)
    return path, result


def reduction_note(result: mesh_reduce.ReduceResult, path: Path) -> list[str]:
    return [
        f"Mesh reduced from {result.triangles_before:,} to {result.triangles_after:,} triangles "
        f"({result.vertices_before:,} to {result.vertices_after:,} vertices); the reduced model was saved as {path}.",
        *result.warnings,
    ]


@dataclass
class RigFitSetup:
    """What :func:`fit_new_rig` needs, and the automatic joint mapping."""

    model: "rig_fit.Rig"
    game: "rig_fit.Rig"
    weapon_bones: set[str]
    mapping: dict[str, str]
    battle: bool


def prepare_rig_fit(container_path: Path, model_path: Path) -> RigFitSetup:
    """Read the set's rig kit and a rigged model, and guess which game bone
    each model joint follows (``rig_fit.auto_mapping``)."""
    glb, bones, named = rig_kit_glb(container_path)
    battle = _is_battle_container(container_path)
    weapon = set() if battle else _map_weapon_bones(bones, named)
    game = rig_fit.read_rig(glb, single_texture=False)
    model = rig_fit.read_rig(model_path.read_bytes(), model_path.parent)
    skip = {k for k, n in enumerate(game.names) if gltf_import.is_anchor_name(n)}
    skip |= {k for k, n in enumerate(game.names)
             if n in weapon or any(game.names[a] in weapon for a in game.ancestors(k))}
    game_chains = rig_fit.body_chains(game, skip, rig_fit.game_ends(game, weapon))
    model_chains = rig_fit.body_chains(model)
    mapping = rig_fit.auto_mapping(model, model_chains, game, game_chains)
    return RigFitSetup(model, game, weapon, mapping, battle)


def fit_new_rig(
    container_path: Path,
    setup: RigFitSetup,
    mapping: dict[str, str],
    fitted_path: Path | None = None,
    max_triangles: int | None = None,
) -> ModelImport:
    """Put a rigged model on the set as a new rig (``rig_fit.fit_rig``):
    its own skeleton, every animation of the set retargeted onto it, then
    the regular rig import. ``fitted_path`` keeps the generated glTF.
    ``max_triangles`` reduces the fitted mesh first (``mesh_reduce``; the
    weapon meshes are kept)."""
    import tempfile

    fit = rig_fit.fit_rig(setup.model, setup.game, mapping, battle=setup.battle, weapon_bones=setup.weapon_bones)
    if max_triangles is not None:
        reduced = mesh_reduce.reduce_glb(fit.glb, max_triangles, locked_joints=setup.weapon_bones)
        if reduced.triangles_after < reduced.triangles_before:
            fit.glb = reduced.glb
            fit.warnings.append(
                f"Mesh reduced from {reduced.triangles_before:,} to {reduced.triangles_after:,} triangles "
                f"({reduced.vertices_before:,} to {reduced.vertices_after:,} vertices)."
            )
        fit.warnings += reduced.warnings
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "fitted.glb"
        path.write_bytes(fit.glb)
        if setup.battle:
            result = replace_battle_rig_with_glb(container_path, path, new_rig=True)
        else:
            result = replace_rig_with_glb(container_path, path)
    if fitted_path is not None:
        fitted_path.write_bytes(fit.glb)
        fit.warnings.append(f"The fitted model (its skeleton and every animation) was saved as {fitted_path}.")
    result.warnings[:0] = fit.warnings
    return result


def export_rig_kit(container_path: Path, target: Path) -> list[Path]:
    """Write the rig kit of a character set: ``target`` (a ``.glb`` with the
    skeleton, body and every animation named as the rig import looks for
    them), ``<target>.md`` (the checklist: anchors, map weapons, each
    animation's frames, loop, role and events) and ``<target>.json`` (the
    animation list for scripts). See :mod:`rig_contract`."""
    glb, bones, named = rig_kit_glb(container_path)
    target.write_bytes(glb)

    battle = _is_battle_container(container_path)
    roles: dict[str, list[str]] = {}
    hidden: dict[str, set[str]] = {}
    if battle:
        zdbx_path = _files_root(container_path) / "zdbx.cmp"
        if zdbx_path.is_file():
            for key, stem in rig_contract.read_battle_roles(zdbx_path.read_bytes(), container_path.parent.name):
                roles.setdefault(stem.lower(), []).append(rig_contract.describe_role(key))
    else:
        hidden = rig_contract.weapon_bones(bones, {name: data for _g, name, _p, data in named})
    kit = []
    for gltf_name, name, pack, data in named:
        stem = Path(name).stem
        role = rig_contract.describe_battle_file(stem) if battle else rig_contract.describe_map_file(stem)
        entry = rig_contract.kit_animation(
            gltf_name, pack, data, role, hidden=hidden.get(name), roles=roles.get(stem.lower())
        )
        kit.append(entry)
    label = f"{container_path.parent.parent.name}/{container_path.parent.name}"
    sheet = target.with_suffix(".md")
    sheet.write_text(rig_contract.rig_kit_sheet(label, bones, kit, battle), encoding="utf-8")
    listing = target.with_suffix(".json")
    listing.write_text(rig_contract.kit_json(kit), encoding="utf-8")
    return [target, sheet, listing]


def _set_animation_output(container_path: Path, target: str, ga: bytes) -> dict[Path, bytes]:
    """The files to write so the set's animation ``target`` (a pack entry,
    in every weapon pack that holds it, or a loose file) becomes ``ga``."""
    out = {}
    for pack_path in _set_containers(container_path):
        entries, files = _read_container(pack_path)
        if target in files:
            files[target] = ga
            out[pack_path] = _pack(pack_path, entries, files)
    if out:
        return out
    loose = container_path.parent / target
    if loose.is_file():
        return {loose: ga}
    raise gltf_import.GltfImportError(f"{target} is not an animation of this set.")


def set_animation_bytes(container_path: Path, target: str) -> bytes:
    """The current bytes of the set's animation ``target``."""
    for pack_path in _set_containers(container_path):
        _e, files = _read_container(pack_path)
        if target in files:
            return files[target]
    loose = container_path.parent / target
    if loose.is_file():
        return loose.read_bytes()
    raise gltf_import.GltfImportError(f"{target} is not an animation of this set.")


def replace_animation_events(container_path: Path, target: str, events: list[animation.EventKey]) -> ModelImport:
    """Rewrite the event track of the set's animation ``target``. Warns when
    a code the battle script waits for (``rig_contract.COMBAT_CODES``) is
    dropped."""
    old = set_animation_bytes(container_path, target)
    ga = rig_contract.replace_events(old, events)
    warnings = [e.replace("the fight would", "the fight may") for e in rig_contract.event_errors(target, ga, old)]
    return ModelImport(_set_animation_output(container_path, target, ga), warnings)


def replace_animation_with_glb(
    container_path: Path, gltf_path: Path, gltf_animation: str, target: str
) -> ModelImport:
    """Rebuild the set's ``target`` animation (a pack entry or a loose file)
    from one glTF animation (``gltf_import.import_animation``), keeping the
    replaced file's events and loop settings unless the glTF carries its
    own. A battle model's animation is rewritten in the weapon pack that
    holds it."""
    for pack_path in _set_containers(container_path):
        entries, files = _read_container(pack_path)
        if target in files:
            container_path = pack_path
            break
    else:
        entries, files = _read_container(container_path)
    g_names = [n for n in files if Path(n).suffix.lower() == ".g"]
    if not g_names:
        raise gltf_import.GltfImportError(f"{container_path.name} has no skeleton.")
    loose = container_path.parent / target
    if target in files:
        template = files[target]
    elif loose.is_file():
        template = loose.read_bytes()
    else:
        raise gltf_import.GltfImportError(f"{target} is not an animation of this set.")
    ga, warnings = gltf_import.import_animation(
        gltf_path.read_bytes(),
        files[g_names[0]],
        animation_name=gltf_animation,
        template=template,
        base_dir=gltf_path.parent,
    )
    gs_names = [n for n in files if Path(n).suffix.lower() == ".gs"]
    if gs_names:
        excess = gltf_import.composite_range_excess(
            gs_file.read_gs(files[gs_names[0]]),
            skeleton.read_skeleton_file(files[g_names[0]]).bones,
            [animation.read_animation_bytes(ga)],
        )
        if excess is not None and excess > 1.0:
            warnings.append(
                f"This animation moves the body's smoothly skinned vertices {excess:.1f}x beyond the range its "
                "blended-vertex buffer holds; the game clamps them there. Re-import the body after the animation "
                "to resize that range."
            )
    if target not in files:
        return ModelImport({loose: ga}, warnings)
    files[target] = ga
    return ModelImport({container_path: _pack(container_path, entries, files)}, warnings)


class _NewSlotDialog(tk.Toplevel):
    """Copy a battle model (``zu/``) or map model (``ymu/``) under a new name
    and pick who uses the copy."""

    def __init__(self, parent, project: ModProject, label: str) -> None:
        super().__init__(parent)
        self.title(f"New slot from {label}")
        self.transient(parent)
        self.result: str | None = None
        self._project = project
        self._battle = label.startswith("zu/")
        self._source = label.split("/", 1)[1]
        fe8 = fe8data.read_fe8data((project.extracted_dir / "files" / "FE8Data.bin").read_bytes())
        self._characters = {c.pid: c for c in fe8.characters if c.pid}
        jids = sorted({c.jid for c in fe8.classes if c.jid})

        body = ttk.Frame(self, padding=10)
        body.pack(fill="both", expand=True)
        row = 0

        def field(text: str, widget: tk.Widget, hint: str = "") -> None:
            nonlocal row
            ttk.Label(body, text=text).grid(row=row, column=0, sticky="w", pady=2)
            widget.grid(row=row, column=1, sticky="we", pady=2, padx=(8, 0))
            if hint:
                ttk.Label(body, text=hint, style="Muted.TLabel").grid(row=row, column=2, sticky="w", padx=(8, 0))
            row += 1

        self._new_name = tk.StringVar()
        self._pid = tk.StringVar()
        self._jid = tk.StringVar()
        self._folder = tk.StringVar()
        self._source_aid = tk.StringVar()
        self._promoted = tk.BooleanVar(value=False)
        pid_box = ttk.Combobox(body, textvariable=self._pid, values=sorted(self._characters), width=30)
        pid_box.bind("<<ComboboxSelected>>", lambda e: self._character_picked())
        if self._battle:
            field("New model code", ttk.Entry(body, textvariable=self._new_name, width=12), "4 lowercase letters or digits")
            field("Character", pid_box, "empty: the whole class")
            field("Class", ttk.Combobox(body, textvariable=self._jid, values=jids, width=30))
        else:
            bases = sorted({r.base_aid for r in model_slots.map_model_records(project)
                            if r.class_folder == self._source + "/"})
            field("Copy animation ID", ttk.Combobox(body, textvariable=self._source_aid, values=bases,
                                                    state="readonly", width=30))
            if bases:
                self._source_aid.set(bases[0])
            field("New animation ID", ttk.Entry(body, textvariable=self._new_name, width=30), "AID_ and capitals")
            self._folder.set(f"{self._source}_new")
            field("New folder", ttk.Entry(body, textvariable=self._folder, width=30), "ymu/<folder>/; empty: share")
            field("Character", pid_box, "empty: register only")
            field("", ttk.Checkbutton(body, text="Promoted model", variable=self._promoted))
        body.columnconfigure(1, weight=1)
        buttons = ttk.Frame(body)
        buttons.grid(row=row, column=0, columnspan=3, sticky="e", pady=(8, 0))
        ttk.Button(buttons, text="Create", command=self._ok).pack(side="left")
        ttk.Button(buttons, text="Cancel", command=self.destroy).pack(side="left", padx=(6, 0))
        self.grab_set()

    def _character_picked(self) -> None:
        character = self._characters.get(self._pid.get())
        if character and self._battle and character.jid:
            self._jid.set(character.jid)

    def _ok(self) -> None:
        name, pid = self._new_name.get().strip(), self._pid.get().strip() or None
        try:
            if self._battle:
                jid = self._jid.get().strip()
                if not jid:
                    raise ValueError("Pick the class the model is used for.")
                model_slots.clone_battle_model(self._project, self._source, name)
                model_slots.assign_battle_model(self._project, name, jid=jid, pid=pid)
                who = f"{pid} as {jid}" if pid else jid
                self.result = f"New battle model zu/{name} (copy of {self._source}), used by {who}"
            else:
                folder = self._folder.get().strip() or None
                model_slots.clone_map_model(self._project, self._source_aid.get(), name, folder)
                if pid:
                    model_slots.assign_map_model(self._project, pid, name, promoted=self._promoted.get())
                where = f"ymu/{folder}" if folder else f"ymu/{self._source}"
                who = ""
                if pid:
                    who = f", used by {pid}" + (" (promoted)" if self._promoted.get() else "")
                self.result = f"New map model {name} in {where} (copy of {self._source_aid.get()}){who}"
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror("Could not create the slot", str(exc), parent=self)
            return
        self.destroy()


ARMY_KEYS = {"自軍": "player army", "敵軍": "enemy army", "中立": "other army", "味方": "ally army"}


class _ModelTablesDialog(tk.Toplevel):
    """The tables that pick each unit's models: the battle job list, each
    battle model's texture lines, and the map-model records of an animation
    ID, with the slot removals. ``on_change(label, text)`` is called after
    each write."""

    def __init__(self, parent, project: ModProject, on_change) -> None:
        super().__init__(parent)
        self.title("Model tables")
        self.transient(parent)
        self.geometry("900x560")
        self._project = project
        self._on_change = on_change
        fe8 = fe8data.read_fe8data((project.extracted_dir / "files" / "FE8Data.bin").read_bytes())
        self._characters = {c.pid: c for c in fe8.characters if c.pid}
        self._classes = {c.jid: c for c in fe8.classes if c.jid}
        notebook = ttk.Notebook(self)
        notebook.pack(fill="both", expand=True, padx=8, pady=8)
        self._build_job_tab(notebook)
        self._build_texture_tab(notebook)
        self._build_map_tab(notebook)
        self._refresh_all()

    # -- helpers ------------------------------------------------------------------
    def _run(self, action, label: str, text: str) -> bool:
        try:
            action()
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror("Model tables", str(exc), parent=self)
            return False
        self._on_change(label, text)
        self._refresh_all()
        return True

    @staticmethod
    def _tree(parent, columns: tuple[tuple[str, str, int], ...]) -> ttk.Treeview:
        frame = ttk.Frame(parent)
        frame.pack(fill="both", expand=True)
        tree = ttk.Treeview(frame, columns=[c[0] for c in columns], show="headings", selectmode="browse")
        for name, heading, width in columns:
            tree.heading(name, text=heading)
            tree.column(name, width=width, stretch=True)
        scroll = ttk.Scrollbar(frame, command=tree.yview)
        tree.config(yscrollcommand=scroll.set)
        tree.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")
        return tree

    def _base_aid_of(self, pid: str, promoted: bool) -> str | None:
        """The base animation ID the engine uses: the character's, else its class's."""
        character = self._characters.get(pid)
        if character is None:
            return None
        aid = character.aid_promoted if promoted else character.aid_unpromoted
        job = self._classes.get(character.jid)
        return aid or (job.aid if job else None)

    def _refresh_all(self) -> None:
        self._refresh_jobs()
        self._refresh_codes()
        self._refresh_aids()

    # -- job list ----------------------------------------------------------------
    def _build_job_tab(self, notebook: ttk.Notebook) -> None:
        tab = ttk.Frame(notebook, padding=8)
        notebook.add(tab, text="Battle job list")
        ttk.Label(
            tab, style="Muted.TLabel",
            text="The battle model of a unit: its animation ID's line, else its class plus character, else its class.",
        ).pack(anchor="w")
        self._job_tree = self._tree(tab, (("key", "Class / character / animation ID", 320), ("code", "Model", 80),
                                          ("comment", "Comment", 200)))
        form = ttk.Frame(tab)
        form.pack(fill="x", pady=(6, 0))
        self._job_jid, self._job_pid, self._job_aid, self._job_code = (tk.StringVar() for _ in range(4))
        ttk.Label(form, text="Class").grid(row=0, column=0, sticky="w")
        ttk.Combobox(form, textvariable=self._job_jid, values=sorted(self._classes), width=24).grid(row=0, column=1)
        ttk.Label(form, text="Character").grid(row=0, column=2, sticky="w", padx=(8, 0))
        ttk.Combobox(form, textvariable=self._job_pid, values=sorted(self._characters), width=24).grid(row=0, column=3)
        ttk.Label(form, text="or animation ID").grid(row=1, column=0, sticky="w")
        self._job_aid_box = ttk.Combobox(form, textvariable=self._job_aid, width=24)
        self._job_aid_box.grid(row=1, column=1)
        ttk.Label(form, text="Model").grid(row=1, column=2, sticky="w", padx=(8, 0))
        self._job_code_box = ttk.Combobox(form, textvariable=self._job_code, width=10)
        self._job_code_box.grid(row=1, column=3, sticky="w")
        ttk.Button(form, text="Set line", command=self._set_job_line).grid(row=0, column=4, padx=(8, 0))
        ttk.Button(form, text="Remove line", command=self._remove_job_line).grid(row=1, column=4, padx=(8, 0))

        check = ttk.LabelFrame(tab, text="Which models does a character get?", padding=6)
        check.pack(fill="x", pady=(8, 0))
        self._check_pid = tk.StringVar()
        self._check_promoted = tk.BooleanVar(value=False)
        box = ttk.Combobox(check, textvariable=self._check_pid, values=sorted(self._characters), width=28)
        box.pack(side="left")
        box.bind("<<ComboboxSelected>>", lambda e: self._check_character())
        ttk.Checkbutton(check, text="Promoted", variable=self._check_promoted,
                        command=self._check_character).pack(side="left", padx=(8, 0))
        self._check_result = ttk.Label(check, text="")
        self._check_result.pack(side="left", padx=(12, 0))

    def _refresh_jobs(self) -> None:
        self._job_tree.delete(*self._job_tree.get_children())
        for key, code, comment in model_slots.job_list(self._project):
            self._job_tree.insert("", "end", iid=key, values=(key, code, comment))
        self._job_code_box.config(values=model_slots.battle_model_codes(self._project))
        self._job_aid_box.config(values=sorted({r.base_aid for r in model_slots.map_model_records(self._project)}))
        self._check_character()

    def _set_job_line(self) -> None:
        jid, pid = self._job_jid.get().strip() or None, self._job_pid.get().strip() or None
        aid, code = self._job_aid.get().strip() or None, self._job_code.get().strip()
        who = aid or (f"{jid} + {pid}" if pid else jid)
        self._run(lambda: model_slots.assign_battle_model(self._project, code, jid=jid, pid=pid, aid=aid),
                  "zdbx/jobList.dbx", f"Battle model of {who} set to {code}")

    def _remove_job_line(self) -> None:
        selection = self._job_tree.selection()
        if selection:
            key = selection[0]
            self._run(lambda: model_slots.remove_job_line(self._project, key),
                      "zdbx/jobList.dbx", f"Removed the job-list line {key}")

    def _check_character(self) -> None:
        pid = self._check_pid.get().strip()
        character = self._characters.get(pid)
        if character is None:
            self._check_result.config(text="")
            return
        aid = self._base_aid_of(pid, self._check_promoted.get())
        models = {key: code for key, code, _comment in model_slots.job_list(self._project)}
        battle = zdbx.battle_model_for(models, character.jid or "", pid, aid)
        records = [r for r in model_slots.map_model_records(self._project) if r.base_aid == aid]
        folders = sorted({r.class_folder for r in records})
        self._check_result.config(
            text=f"class {character.jid}, animation ID {aid or '-'}: battle zu/{battle or '?'}, "
                 f"map ymu/{', ymu/'.join(folders) if folders else '?'}"
        )

    # -- battle textures ------------------------------------------------------------
    def _build_texture_tab(self, notebook: ttk.Notebook) -> None:
        tab = ttk.Frame(notebook, padding=8)
        notebook.add(tab, text="Battle textures")
        top = ttk.Frame(tab)
        top.pack(fill="x")
        ttk.Label(top, text="Battle model").pack(side="left")
        self._tex_code = tk.StringVar()
        self._tex_code_box = ttk.Combobox(top, textvariable=self._tex_code, state="readonly", width=10)
        self._tex_code_box.pack(side="left", padx=(6, 0))
        self._tex_code_box.bind("<<ComboboxSelected>>", lambda e: self._refresh_textures())
        self._remove_code_button = ttk.Button(top, text="Remove this slot...", command=self._remove_battle_slot)
        self._remove_code_button.pack(side="right")
        ttk.Label(
            tab, style="Muted.TLabel",
            text="zu/<code>/<texture>.tpl is picked by the unit's animation ID, then its character, then its army.",
        ).pack(anchor="w", pady=(4, 0))
        self._tex_tree = self._tree(tab, (("key", "Key", 260), ("texture", "Texture (.tpl)", 200)))
        form = ttk.Frame(tab)
        form.pack(fill="x", pady=(6, 0))
        self._tex_key, self._tex_name = tk.StringVar(), tk.StringVar()
        ttk.Label(form, text="Key").grid(row=0, column=0, sticky="w")
        keys = list(ARMY_KEYS) + sorted(self._characters)
        ttk.Combobox(form, textvariable=self._tex_key, values=keys, width=28).grid(row=0, column=1)
        ttk.Label(form, text="Texture").grid(row=0, column=2, sticky="w", padx=(8, 0))
        self._tex_name_box = ttk.Combobox(form, textvariable=self._tex_name, width=20)
        self._tex_name_box.grid(row=0, column=3)
        ttk.Button(form, text="Set", command=self._set_texture).grid(row=0, column=4, padx=(8, 0))
        ttk.Button(form, text="Remove", command=self._remove_texture).grid(row=0, column=5, padx=(6, 0))
        ttk.Label(form, style="Muted.TLabel", text="Army keys: 自軍 player, 敵軍 enemy, 中立 other, 味方 ally.").grid(
            row=1, column=0, columnspan=6, sticky="w", pady=(4, 0))

    def _refresh_codes(self) -> None:
        codes = model_slots.battle_model_codes(self._project)
        self._tex_code_box.config(values=codes)
        if self._tex_code.get() not in codes:
            self._tex_code.set(codes[0] if codes else "")
        self._refresh_textures()

    def _refresh_textures(self) -> None:
        code = self._tex_code.get()
        self._tex_tree.delete(*self._tex_tree.get_children())
        if not code:
            return
        for key, texture in model_slots.battle_textures(self._project, code).items():
            label = f"{key} ({ARMY_KEYS[key]})" if key in ARMY_KEYS else key
            self._tex_tree.insert("", "end", iid=key, values=(label, texture))
        folder = self._project.extracted_dir / "files" / "zu" / code
        self._tex_name_box.config(values=sorted(p.stem for p in folder.glob("*.tpl")))
        vanilla = code in model_slots.vanilla_battle_codes(self._project)
        self._remove_code_button.config(state="disabled" if vanilla else "normal")

    def _set_texture(self) -> None:
        code, key, name = self._tex_code.get(), self._tex_key.get().strip(), self._tex_name.get().strip()
        self._run(lambda: model_slots.set_battle_texture(self._project, code, key, name),
                  f"zu/{code}", f"Battle texture for {key} set to {name}.tpl")

    def _remove_texture(self) -> None:
        selection = self._tex_tree.selection()
        code = self._tex_code.get()
        if selection:
            key = selection[0]
            self._run(lambda: model_slots.remove_battle_texture(self._project, code, key),
                      f"zu/{code}", f"Removed the battle texture line {key}")

    def _remove_battle_slot(self) -> None:
        code = self._tex_code.get()
        if not code or not messagebox.askyesno(
            "Remove battle model",
            f"Delete zu/{code}/ and its tables, and stop every job-list line from selecting it? "
            "Lines the game's own job list had get their original model back.",
            parent=self,
        ):
            return
        self._run(lambda: model_slots.remove_battle_model(self._project, code),
                  f"zu/{code}", f"Removed the battle model zu/{code}")

    # -- map models -----------------------------------------------------------------
    def _build_map_tab(self, notebook: ttk.Notebook) -> None:
        tab = ttk.Frame(notebook, padding=8)
        notebook.add(tab, text="Map models")
        top = ttk.Frame(tab)
        top.pack(fill="x")
        ttk.Label(top, text="Animation ID").pack(side="left")
        self._map_aid = tk.StringVar()
        self._map_aid_box = ttk.Combobox(top, textvariable=self._map_aid, state="readonly", width=28)
        self._map_aid_box.pack(side="left", padx=(6, 0))
        self._map_aid_box.bind("<<ComboboxSelected>>", lambda e: self._refresh_records())
        self._remove_aid_button = ttk.Button(top, text="Remove this slot...", command=self._remove_map_slot)
        self._remove_aid_button.pack(side="right")
        self._map_tree = self._tree(tab, (
            ("aid", "Record", 200), ("folder", "ymu/ folder", 110), ("textures", "tex_<n> per army", 140),
            ("blend", "Blend", 50), ("b0b", "+0x0B", 50), ("actions", "Animations", 330)))
        form = ttk.Frame(tab)
        form.pack(fill="x", pady=(6, 0))
        self._map_textures = [tk.StringVar() for _ in anim_registry.ARMIES]
        for i, army in enumerate(anim_registry.ARMIES):
            ttk.Label(form, text=army).grid(row=0, column=2 * i, sticky="w", padx=(0 if i == 0 else 8, 0))
            ttk.Spinbox(form, textvariable=self._map_textures[i], from_=0, to=255, width=5).grid(row=0, column=2 * i + 1)
        ttk.Button(form, text="Set textures", command=self._set_map_textures).grid(row=0, column=8, padx=(8, 0))
        ttk.Label(
            form, style="Muted.TLabel",
            text="Every weapon set of the ID loads ymu/<folder>tex_<n>.tpl, n picked by the unit's army. "
                 "Blend: cross-fade weight (16 frames up to 20, 32 from 40).",
        ).grid(row=1, column=0, columnspan=9, sticky="w", pady=(4, 0))

    def _refresh_aids(self) -> None:
        aids = sorted({r.base_aid for r in model_slots.map_model_records(self._project)})
        self._map_aid_box.config(values=aids)
        if self._map_aid.get() not in aids:
            self._map_aid.set(aids[0] if aids else "")
        self._refresh_records()

    def _refresh_records(self) -> None:
        aid = self._map_aid.get()
        self._map_tree.delete(*self._map_tree.get_children())
        records = [r for r in model_slots.map_model_records(self._project) if r.base_aid == aid]
        for i, r in enumerate(records):
            signed = r.body_type - 256 if r.body_type > 127 else r.body_type
            self._map_tree.insert("", "end", iid=str(i), values=(
                r.aid_name, r.class_folder, " ".join(map(str, r.texture_ids)), r.blend_weight, signed,
                " ".join(r.actions)))
        if records:
            for var, value in zip(self._map_textures, records[0].texture_ids):
                var.set(str(value))
        vanilla = aid in model_slots.vanilla_map_aids(self._project)
        self._remove_aid_button.config(state="disabled" if vanilla or not aid else "normal")

    def _set_map_textures(self) -> None:
        aid = self._map_aid.get()
        try:
            ids = tuple(int(v.get()) for v in self._map_textures)
        except ValueError:
            messagebox.showerror("Model tables", "Texture numbers are whole numbers 0-255.", parent=self)
            return
        self._run(lambda: model_slots.set_map_textures(self._project, aid, ids),
                  "FE8Anim.bin", f"Map textures of {aid} set to {ids}")

    def _remove_map_slot(self) -> None:
        aid = self._map_aid.get()
        if not aid or not messagebox.askyesno(
            "Remove map model",
            f"Delete {aid}'s records, its copied ymu/ folder if nothing else uses it, and point the "
            "characters and classes using it back at their extracted animation IDs?",
            parent=self,
        ):
            return
        changes: list[str] = []

        def remove() -> None:
            changes.extend(model_slots.remove_map_model(self._project, aid))

        if self._run(remove, "FE8Anim.bin", f"Removed the map model {aid}"):
            messagebox.showinfo("Map model removed", "\n".join(changes), parent=self)


class _TerrainImportOptions(tk.Toplevel):
    """The optional steps of a terrain import: heights, tile fitting and the
    game's road/shore texturing (``replace_map_terrain_with_glb``)."""

    def __init__(self, parent, has_map_base: bool = False) -> None:
        super().__init__(parent)
        self.title("Terrain import")
        self.transient(parent)
        self.result: tuple | None = None
        body = ttk.Frame(self, padding=10)
        body.pack(fill="both", expand=True)
        self._follow = tk.BooleanVar(value=True)
        self._conform = tk.BooleanVar(value=True)
        self._texturing = tk.BooleanVar(value=has_map_base)
        self._keep_light = tk.BooleanVar(value=False)
        self._mask = tk.StringVar()
        ttk.Checkbutton(
            body, variable=self._follow,
            text="Move tile heights and props with the new ground (units stand on map.bin's heights)",
        ).pack(anchor="w")
        ttk.Checkbutton(
            body, variable=self._conform,
            text="Fit the playable area to the tile grid (the move grid is drawn flat per tile half)",
        ).pack(anchor="w", pady=(4, 0))
        ttk.Checkbutton(
            body, variable=self._texturing,
            text="Keep map texturing on materials named map_base (atlas through both UV sets, blended by the mask)",
        ).pack(anchor="w", pady=(8, 0))
        mask_row = ttk.Frame(body)
        mask_row.pack(fill="x", padx=(20, 0), pady=(2, 0))
        ttk.Label(mask_row, text="Mask image (empty: keep the current one)").pack(side="left")
        ttk.Entry(mask_row, textvariable=self._mask, width=36).pack(side="left", padx=(6, 0))
        ttk.Button(mask_row, text="Browse...", command=self._browse).pack(side="left", padx=(6, 0))
        ttk.Checkbutton(
            body, variable=self._keep_light,
            text="Keep the map's light overlay (made for the old ground; off: white)",
        ).pack(anchor="w", padx=(20, 0), pady=(2, 0))
        buttons = ttk.Frame(body)
        buttons.pack(anchor="e", pady=(10, 0))
        ttk.Button(buttons, text="Continue", command=self._ok).pack(side="left")
        ttk.Button(buttons, text="Cancel", command=self.destroy).pack(side="left", padx=(6, 0))
        self.grab_set()

    def _browse(self) -> None:
        chosen = filedialog.askopenfilename(title="Road/shore mask", filetypes=[("Images", "*.png *.bmp *.tga"), ("All files", "*.*")], parent=self)
        if chosen:
            self._mask.set(chosen)

    def _ok(self) -> None:
        mask = None
        if self._texturing.get() and self._mask.get().strip():
            try:
                mask = Image.open(self._mask.get().strip()).convert("RGBA")
            except OSError as exc:
                messagebox.showerror("Mask image", str(exc), parent=self)
                return
        self.result = (self._follow.get(), self._conform.get(), self._texturing.get(), mask, self._keep_light.get())
        self.destroy()


class _MapReduceDialog(tk.Toplevel):
    """Offer to reduce a model that is larger than the game's map models
    (``mesh_reduce``). ``result``: a triangle count, ``0`` to keep the mesh
    as it is, ``None`` to cancel the import."""

    def __init__(self, parent, label: str, triangles: int, suggested: int) -> None:
        super().__init__(parent)
        self.title("Map model size")
        self.transient(parent)
        self.result: int | None = None
        body = ttk.Frame(self, padding=10)
        body.pack(fill="both", expand=True)
        limit = gs_stats.MAP_BODY_LIMITS["triangles"]
        ttk.Label(
            body,
            text=f"The model has {triangles:,} triangles; vanilla map models have 444 (median) and at most {limit:,}.\n"
            f"A reduced copy for {label} keeps the texture charts, the skin and the weapon meshes, and is\n"
            "saved next to the model.",
            justify="left",
        ).pack(anchor="w")
        row = ttk.Frame(body)
        row.pack(anchor="w", pady=(8, 0))
        ttk.Label(row, text="Reduce to").pack(side="left")
        self._target = tk.IntVar(value=suggested)
        ttk.Spinbox(row, from_=50, to=max(triangles, 50), increment=50, textvariable=self._target, width=8).pack(side="left", padx=6)
        ttk.Label(row, text="triangles").pack(side="left")
        buttons = ttk.Frame(body)
        buttons.pack(anchor="e", pady=(10, 0))
        ttk.Button(buttons, text="Reduce", command=self._reduce).pack(side="left")
        ttk.Button(buttons, text="Keep all", command=self._keep).pack(side="left", padx=(6, 0))
        ttk.Button(buttons, text="Cancel", command=self.destroy).pack(side="left", padx=(6, 0))
        self.grab_set()

    def _reduce(self) -> None:
        try:
            target = int(self._target.get())
        except (tk.TclError, ValueError):
            messagebox.showerror("Map model size", "Enter a triangle count.", parent=self)
            return
        self.result = max(target, 1)
        self.destroy()

    def _keep(self) -> None:
        self.result = 0
        self.destroy()


class _RigMappingDialog(tk.Toplevel):
    """Which game bone each joint of the model follows (guessed from the
    body's shape; blank: the joint follows its parent)."""

    def __init__(self, parent, label: str, setup: RigFitSetup) -> None:
        super().__init__(parent)
        self.title(f"Fit new rig - {label}")
        self.transient(parent)
        self.result: dict[str, str] | None = None
        self._setup = setup
        top = ttk.Frame(self, padding=8)
        top.pack(fill="both", expand=True)
        ttk.Label(
            top,
            text="Each model joint turns like the game bone it follows. Blank: the joint follows its parent "
            "(fingers, hair...).\nThe pelvis must be the one mapped joint all the others hang from.",
            justify="left",
        ).pack(anchor="w")
        frame = ttk.Frame(top)
        frame.pack(fill="both", expand=True, pady=(6, 0))
        canvas = tk.Canvas(frame, height=420, width=460, highlightthickness=0)
        scroll = ttk.Scrollbar(frame, command=canvas.yview)
        inner = ttk.Frame(canvas)
        inner.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=inner, anchor="nw")
        canvas.configure(yscrollcommand=scroll.set)
        canvas.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")
        game_bones = [""] + [n for n in setup.game.names if not gltf_import.is_anchor_name(n)]
        self._vars: dict[str, tk.StringVar] = {}
        model = setup.model
        order = sorted(range(len(model.names)), key=lambda k: (len(model.ancestors(k)), k))
        for row, k in enumerate(order):
            name = model.names[k]
            ttk.Label(inner, text="  " * len(model.ancestors(k)) + name).grid(row=row, column=0, sticky="w")
            var = tk.StringVar(value=setup.mapping.get(name, ""))
            ttk.Combobox(inner, textvariable=var, values=game_bones, width=24).grid(row=row, column=1, sticky="w")
            self._vars[name] = var
        buttons = ttk.Frame(top)
        buttons.pack(fill="x", pady=(8, 0))
        ttk.Button(buttons, text="Load mapping...", command=self._load).pack(side="left")
        ttk.Button(buttons, text="Save mapping...", command=self._save).pack(side="left", padx=(6, 0))
        ttk.Button(buttons, text="Fit", command=self._ok).pack(side="right")
        ttk.Button(buttons, text="Cancel", command=self.destroy).pack(side="right", padx=(0, 6))
        self.grab_set()

    def _current(self) -> dict[str, str]:
        return {name: var.get().strip() for name, var in self._vars.items()}

    def _load(self) -> None:
        path = filedialog.askopenfilename(title="Load a joint mapping", filetypes=[("JSON", "*.json")], parent=self)
        if not path:
            return
        try:
            data = json.loads(Path(path).read_text(encoding="utf-8"))
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror("Could not read the mapping", str(exc), parent=self)
            return
        for name, var in self._vars.items():
            if name in data:
                var.set(data[name] or "")

    def _save(self) -> None:
        path = filedialog.asksaveasfilename(
            title="Save the joint mapping", defaultextension=".json", filetypes=[("JSON", "*.json")], parent=self
        )
        if path:
            Path(path).write_text(json.dumps(self._current(), indent=1), encoding="utf-8")

    def _ok(self) -> None:
        self.result = self._current()
        self.destroy()


class _EventEditorDialog(tk.Toplevel):
    """Edit an animation's event track: frame and codes per key. Codes the
    battle script waits for (0, 1, 2) are marked; see ``rig_contract``."""

    def __init__(self, parent, label: str, path: Path, names: list[str]) -> None:
        super().__init__(parent)
        self.title(f"Events - {label}")
        self.transient(parent)
        self.result: tuple[str, list[animation.EventKey]] | None = None
        self._path = path
        self._events: list[animation.EventKey] = []
        self._frames = 0

        top = ttk.Frame(self, padding=8)
        top.pack(fill="both", expand=True)
        ttk.Label(top, text="Animation").grid(row=0, column=0, sticky="w")
        self._name = tk.StringVar(value=names[0] if names else "")
        box = ttk.Combobox(top, textvariable=self._name, values=names, state="readonly", width=36)
        box.grid(row=0, column=1, columnspan=3, sticky="we")
        box.bind("<<ComboboxSelected>>", lambda e: self._load())
        self._info = ttk.Label(top, text="", style="Muted.TLabel")
        self._info.grid(row=1, column=0, columnspan=4, sticky="w", pady=(4, 4))
        self._list = tk.Listbox(top, height=12, width=60, exportselection=False)
        self._list.grid(row=2, column=0, columnspan=4, sticky="nsew")
        self._list.bind("<<ListboxSelect>>", lambda e: self._pick())
        ttk.Label(top, text="Frame").grid(row=3, column=0, sticky="w", pady=(6, 0))
        self._frame = tk.StringVar()
        ttk.Entry(top, textvariable=self._frame, width=8).grid(row=3, column=1, sticky="w", pady=(6, 0))
        ttk.Label(top, text="Codes (comma-separated)").grid(row=4, column=0, sticky="w")
        self._codes = tk.StringVar()
        ttk.Entry(top, textvariable=self._codes, width=30).grid(row=4, column=1, columnspan=3, sticky="we")
        row = ttk.Frame(top)
        row.grid(row=5, column=0, columnspan=4, sticky="w", pady=(6, 0))
        ttk.Button(row, text="Add", command=self._add).pack(side="left")
        ttk.Button(row, text="Update", command=self._update).pack(side="left", padx=(6, 0))
        ttk.Button(row, text="Delete", command=self._delete).pack(side="left", padx=(6, 0))
        ttk.Label(
            top,
            text="0 = the blow lands, 1 = the swing (miss), 2 = throw/shot release: combat waits for these.\n"
            "50 footsteps, 0x14-0x1B trails (0x19 ends), 1000+ sounds.",
            style="Muted.TLabel",
            justify="left",
        ).grid(row=6, column=0, columnspan=4, sticky="w", pady=(6, 0))
        buttons = ttk.Frame(top)
        buttons.grid(row=7, column=0, columnspan=4, sticky="e", pady=(8, 0))
        ttk.Button(buttons, text="Save...", command=self._ok).pack(side="left")
        ttk.Button(buttons, text="Cancel", command=self.destroy).pack(side="left", padx=(6, 0))
        top.columnconfigure(3, weight=1)
        top.rowconfigure(2, weight=1)
        self._load()
        self.grab_set()

    def _load(self) -> None:
        name = self._name.get()
        if not name:
            return
        try:
            anim = animation.read_animation_bytes(set_animation_bytes(self._path, name))
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror("Could not read the animation", str(exc), parent=self)
            return
        self._events = list(anim.events)
        self._frames = anim.header.end_frame
        self._info.config(text=f"{self._frames} frames, {'looping' if anim.header.loops else 'plays once'}")
        self._refresh()

    def _refresh(self) -> None:
        self._events.sort(key=lambda k: k.frame)
        self._list.delete(0, "end")
        for key in self._events:
            codes = ", ".join(
                f"{c}*" if c in rig_contract.COMBAT_CODES else (f"{c} ({rig_contract.EVENT_NAMES[c]})" if c in rig_contract.EVENT_NAMES else str(c))
                for c in key.codes
            )
            self._list.insert("end", f"frame {key.frame}: {codes}")

    def _pick(self) -> None:
        sel = self._list.curselection()
        if not sel:
            return
        key = self._events[sel[0]]
        self._frame.set(str(key.frame))
        self._codes.set(", ".join(str(c) for c in key.codes))

    def _parsed(self) -> animation.EventKey | None:
        try:
            frame = int(self._frame.get())
            codes = tuple(int(c.strip(), 0) for c in self._codes.get().split(",") if c.strip())
        except ValueError:
            messagebox.showerror("Invalid event", "Frame and codes must be numbers.", parent=self)
            return None
        if not codes or len(codes) > 4 or not 0 <= frame <= self._frames:
            messagebox.showerror(
                "Invalid event", f"One to four codes, and a frame from 0 to {self._frames}.", parent=self
            )
            return None
        return animation.EventKey(frame, codes)

    def _add(self) -> None:
        key = self._parsed()
        if key is not None:
            self._events.append(key)
            self._refresh()

    def _update(self) -> None:
        sel = self._list.curselection()
        key = self._parsed()
        if sel and key is not None:
            self._events[sel[0]] = key
            self._refresh()

    def _delete(self) -> None:
        sel = self._list.curselection()
        if sel:
            del self._events[sel[0]]
            self._refresh()

    def _ok(self) -> None:
        self.result = (self._name.get(), list(self._events))
        self.destroy()


class _AnimationImportDialog(tk.Toplevel):
    """Pick which glTF animation replaces which of the set's animations."""

    def __init__(self, parent, gltf_names: list[str], targets: list[str]) -> None:
        super().__init__(parent)
        self.title("Import animation")
        self.transient(parent)
        self.result: tuple[str, str] | None = None
        body = ttk.Frame(self, padding=10)
        body.pack(fill="both", expand=True)
        ttk.Label(body, text="glTF animation").grid(row=0, column=0, sticky="w")
        ttk.Label(body, text="Replaces").grid(row=0, column=1, sticky="w", padx=(10, 0))
        self._source = tk.Listbox(body, exportselection=False, height=14, width=28)
        self._target = tk.Listbox(body, exportselection=False, height=14, width=28)
        self._source.grid(row=1, column=0, sticky="nsew")
        self._target.grid(row=1, column=1, sticky="nsew", padx=(10, 0))
        for name in gltf_names:
            self._source.insert("end", name)
        for name in targets:
            self._target.insert("end", name)
        self._gltf_names, self._targets = gltf_names, targets
        self._source.bind("<<ListboxSelect>>", lambda e: self._match_target())
        buttons = ttk.Frame(body)
        buttons.grid(row=2, column=0, columnspan=2, sticky="e", pady=(8, 0))
        ttk.Button(buttons, text="Import", command=self._ok).pack(side="left")
        ttk.Button(buttons, text="Cancel", command=self.destroy).pack(side="left", padx=(6, 0))
        if gltf_names:
            self._source.selection_set(0)
            self._match_target()
        self.grab_set()

    def _match_target(self) -> None:
        selection = self._source.curselection()
        if not selection:
            return
        name = self._gltf_names[selection[0]].lower()
        for i, target in enumerate(self._targets):
            if Path(target).stem.lower() == name:
                self._target.selection_clear(0, "end")
                self._target.selection_set(i)
                self._target.see(i)
                break

    def _ok(self) -> None:
        source, target = self._source.curselection(), self._target.curselection()
        if not source or not target:
            messagebox.showinfo("Import animation", "Pick a glTF animation and the animation it replaces.", parent=self)
            return
        self.result = (self._gltf_names[source[0]], self._targets[target[0]])
        self.destroy()


def _file_figures(name: str, data: bytes) -> dict[str, str]:
    """Display figures of one model-set file, by kind."""
    suffix = Path(name).suffix.lower()
    figures: dict[str, str] = {}
    try:
        figures.update(_content_figures(suffix, data))
    except Exception:  # noqa: BLE001 - an unreadable file still shows its size
        pass
    figures["File size"] = f"{len(data):,} bytes"
    return figures


def _content_figures(suffix: str, data: bytes) -> dict[str, str]:
    figures: dict[str, str] = {}
    if suffix == ".gs":
        s = gs_stats.model_stats(data)
        figures["Triangles"] = f"{s.triangles:,}"
        figures["Vertex positions"] = f"{s.positions:,}"
        figures["Blended vertices"] = f"{s.blended_vertices:,}"
        figures["Shapes (1 bone / 10 / blended)"] = (
            f"{s.single_bone_shapes} / {s.multi_matrix_shapes} / {s.composite_shapes}"
        )
        figures["Bones used"] = str(s.bones_used)
        figures["Materials"] = str(s.materials)
        figures["Position step (range)"] = f"{s.position_step:.4g} (±{s.position_range:.4g})"
        if s.blended_step is not None:
            figures["Blended step (range)"] = f"{s.blended_step:.4g} (±{s.blended_range:.4g})"
    elif suffix == ".g":
        figures["Bones"] = str(len(skeleton.read_skeleton_file(data).bones))
    elif suffix == ".ga":
        anim = animation.read_animation_bytes(data)
        figures["Frames"] = str(anim.header.words[6])
        figures["Curves"] = str(len(anim.curves))
        figures["Keys"] = f"{sum(len(c.keyframes) for c in anim.curves):,}"
        figures["Events"] = str(len(anim.events))
    elif suffix == ".tpl":
        images = tpl.read_tpl_images(io.BytesIO(data))
        figures["Images"] = ", ".join(f"{im.width}x{im.height}" for im in images)
    return figures


def _set_files(container_path: Path, pending: dict[Path, bytes]) -> dict[str, tuple[bytes | None, bytes | None]]:
    """``{display name: (current bytes, new bytes)}`` for every file an
    import changes: the pack's entries by name, loose files by file name."""
    changed: dict[str, tuple[bytes | None, bytes | None]] = {}
    for path, data in pending.items():
        if path.suffix.lower() in (".cmp", ".pak"):
            old = dict(_read_container(path)[1]) if path.is_file() else {}
            new = _unpack(path, data)[1]
            for entry in new:
                # A battle model's weapon packs share their mesh: list it once.
                if old.get(entry) != new[entry] and entry not in changed:
                    changed[entry] = (old.get(entry), new[entry])
        else:
            changed[path.name] = (path.read_bytes() if path.is_file() else None, data)
    return changed


def import_review_rows(
    label: str, container_path: Path, pending: dict[Path, bytes]
) -> tuple[list[tuple[str, str, str, str, bool]], list[str]]:
    """The review table of an import: rows ``(file, figure, current, new,
    over)``, where ``over`` flags a figure above every vanilla model of the
    set's kind (``gs_stats.MAP_BODY_LIMITS`` for ``ymu/``,
    ``BATTLE_BODY_LIMITS`` for ``zu/``), plus a note for each flagged
    figure."""
    rows: list[tuple[str, str, str, str, bool]] = []
    notes: list[str] = []
    limits, kind = {
        "ymu": (gs_stats.MAP_BODY_LIMITS, "map model"),
        "zu": (gs_stats.BATTLE_BODY_LIMITS, "battle model"),
        "zmap": (gs_stats.MAP_TERRAIN_LIMITS, "map terrain"),
    }.get(label.split("/", 1)[0], (None, ""))
    for name, (old, new) in _set_files(container_path, pending).items():
        old_figures = _file_figures(name, old) if old is not None else {}
        new_figures = _file_figures(name, new) if new is not None else {}
        over: set[str] = set()
        if limits is not None and new is not None and Path(name).suffix.lower() == ".gs":
            s = gs_stats.model_stats(new)
            for figure, value, limit in (
                ("Triangles", s.triangles, limits["triangles"]),
                ("Vertex positions", s.positions, limits["positions"]),
                ("Blended vertices", s.blended_vertices, limits["blended_vertices"]),
                ("Bones used", s.bones_used, limits["bones_used"]),
                ("File size", s.file_size, limits["file_size"]),
            ):
                if value > limit:
                    over.add(figure)
                    notes.append(
                        f"{name}: {figure.lower()} {value:,} is above every vanilla {kind} ({limit:,}); "
                        "the game has not been seen handling that much."
                    )
        for figure in dict.fromkeys([*new_figures, *old_figures]):
            rows.append((name, figure, old_figures.get(figure, "-"), new_figures.get(figure, "-"), figure in over))
    return rows, notes


class _ImportReviewDialog(tk.Toplevel):
    """Everything an import would change, before it is written: a preview
    of the converted set, the figures of every changed file next to the
    current ones, the joint -> bone mapping and the warnings. ``result`` is
    ``True`` when the user chose to write."""

    def __init__(
        self,
        parent: tk.Misc,
        title: str,
        label: str,
        container_path: Path,
        result: ModelImport,
        animation_name: str | None = None,
    ) -> None:
        super().__init__(parent)
        self.title(title)
        self.geometry("1300x740")
        self.transient(parent.winfo_toplevel())
        self.result = False

        rows, notes = import_review_rows(label, container_path, result.outputs)
        body = ttk.Frame(self)
        body.pack(fill="both", expand=True, padx=8, pady=(8, 0))
        # The figures get a fixed-width column; the preview takes the rest.
        side = ttk.Frame(body, width=480)
        side.pack(side="right", fill="y", padx=(8, 0))
        side.pack_propagate(False)
        tabs = ttk.Notebook(side)
        tabs.pack(fill="both", expand=True)
        self._preview = _ModelPreview(body)
        self._preview.pack(side="left", fill="both", expand=True)

        summary = ttk.Frame(tabs, padding=6)
        tabs.add(summary, text="Changes")
        written = ", ".join(p.name for p in result.outputs)
        ttk.Label(summary, text=f"Writes: {written}", wraplength=440, justify="left").pack(anchor="w")
        table = ttk.Treeview(summary, columns=("current", "new"), height=16)
        table.heading("#0", text="Figure")
        table.heading("current", text="Current")
        table.heading("new", text="Imported")
        table.column("#0", width=210)
        table.column("current", width=115, anchor="e")
        table.column("new", width=115, anchor="e")
        table.tag_configure("over", foreground="#b00020")
        parents: dict[str, str] = {}
        for name, figure, old, new, over in rows:
            if name not in parents:
                parents[name] = table.insert("", "end", text=name, open=True)
            table.insert(parents[name], "end", text=figure, values=(old, new), tags=("over",) if over else ())
        table.pack(fill="both", expand=True, pady=(6, 0))
        ttk.Label(
            summary,
            text="Red: above every vanilla model of this kind. Shapes: one bone, up to 10 bones, blended. Steps are the stored precision in model units.",
            style="Muted.TLabel",
            wraplength=440,
            justify="left",
        ).pack(anchor="w", pady=(4, 0))

        if result.joint_map:
            bones_tab = ttk.Frame(tabs, padding=6)
            tabs.add(bones_tab, text=f"Joints ({len(result.joint_map)})")
            mapping = ttk.Treeview(bones_tab, columns=("joint", "bone", "how"), show="headings")
            for column, heading, width in (("joint", "glTF joint", 160), ("bone", "Game bone", 160), ("how", "Matched by", 140)):
                mapping.heading(column, text=heading)
                mapping.column(column, width=width)
            for joint, (bone, how) in result.joint_map.items():
                mapping.insert("", "end", values=(joint, bone, how))
            mapping.pack(fill="both", expand=True)

        warnings = notes + result.warnings
        if warnings:
            warnings_tab = ttk.Frame(tabs, padding=6)
            tabs.add(warnings_tab, text=f"Warnings ({len(warnings)})")
            text = tk.Text(warnings_tab, wrap="word", height=10, font="TkDefaultFont")
            text.insert("end", "\n\n".join(warnings))
            text.config(state="disabled")
            text.pack(fill="both", expand=True)
            tabs.select(warnings_tab)

        buttons = ttk.Frame(self)
        buttons.pack(fill="x", padx=8, pady=8)
        ttk.Label(
            buttons, text="The files as extracted are kept in the project's originals folder.", style="Muted.TLabel"
        ).pack(side="left")
        ttk.Button(buttons, text="Cancel", command=self._close).pack(side="right")
        ttk.Button(buttons, text="Write files", command=self._accept).pack(side="right", padx=(0, 6))
        self.protocol("WM_DELETE_WINDOW", self._close)

        try:
            self._preview.show(_load_model_set(label + " (imported)", container_path, result.outputs))
            if animation_name:
                self._preview.select_animation(animation_name)
        except Exception as exc:  # noqa: BLE001 - the review still works without a preview
            self._preview.show(None, f"Could not preview the imported set: {exc}")
        self.grab_set()

    def _accept(self) -> None:
        self.result = True
        self._close()

    def _close(self) -> None:
        self._preview.cleanup()
        self.destroy()


def load_named_model_set(
    contents: dict[str, bytes],
    base_name: str,
    label: str | None = None,
    map_projection: MapTextureProjection | None = None,
) -> _LoadedSet | None:
    """Decode just one named model group out of an already-unpacked
    archive's ``{filename: content}`` map (e.g. a chapter's ``map.cmp``,
    which - unlike ``ymu``/``zbg``'s one-model-per-pack packs -  bundles
    several independently-named groups: the chapter's own terrain, a
    water plane, decorative props like a tree or flower bed). ``base_name``
    is matched against each entry's filename *without* its extension
    (``map_file.MapObject.filename`` is confirmed to be a bare name with
    no extension - see that module's docstring). Returns ``None`` if
    nothing in ``contents`` matches - a real possibility, since not every
    placed object is a real model (some ``mapbuilddesc`` entries are
    invisible logic-only markers with no backing ``.g``/``.gs`` at all).

    Textures aren't necessarily named after the object they texture (a
    shared ``texpack.tpl`` covers every object in the archive) - this
    falls back to every ``.tpl`` in the whole archive when the named group
    has none of its own.
    """
    relevant = {name: data for name, data in contents.items() if Path(name).stem == base_name}
    if not relevant:
        return None

    if not any(Path(name).suffix.lower() == ".tpl" for name in relevant):
        shared_tpl = {name: data for name, data in contents.items() if Path(name).suffix.lower() == ".tpl"}
        relevant = {**relevant, **shared_tpl}

    return _build_loaded_set(label or base_name, relevant, [], map_projection=map_projection)


def _populate_bone_tree(tree: ttk.Treeview, bones: list[skeleton.Bone]) -> None:
    tree.delete(*tree.get_children())
    item_by_index: dict[int, str] = {}
    remaining = list(enumerate(bones))

    while remaining:
        progressed = False
        still: list[tuple[int, skeleton.Bone]] = []
        for index, bone in remaining:
            parent = bone.parent_index
            if parent == -1:
                item_by_index[index] = tree.insert("", "end", text=f"{index}: {bone.name}")
                progressed = True
            elif parent in item_by_index:
                item_by_index[index] = tree.insert(item_by_index[parent], "end", text=f"{index}: {bone.name}")
                progressed = True
            else:
                still.append((index, bone))
        if not progressed:
            # A parent index this pass couldn't resolve (out of range, or a
            # cycle) - surface the remaining bones flat rather than looping.
            for index, bone in still:
                tree.insert("", "end", text=f"{index}: {bone.name} (parent {bone.parent_index})")
            break
        remaining = still


# 300x the fit-to-view size: a single map tile fills a large part of the view
ZOOM_MAX = 300.0
# the model's largest dimension spans this fraction of the canvas's short side
# at zoom 1 (its 3D diagonal, up to sqrt(3) times that, still fits when orbiting)
FIT_FRACTION = 0.55


class _ModelCanvas(tk.Canvas):
    """Orbiting orthographic renderer. Rasterizes the whole mesh into an
    off-screen numpy framebuffer + real per-pixel Z-buffer every frame -
    real per-pixel texture sampling and backface culling, no painter's-
    algorithm sorting artifacts - then displays the result as a *single*
    Tkinter image (`create_image`), not one Canvas item per triangle.

    This replaced an earlier version that drew one `create_polygon` per
    triangle directly on the Tkinter canvas (flat-shaded, one precomputed
    color per triangle, no Z-buffer - painter's-algorithm depth sorting
    only). That approach hit a real, measured wall on large merged scenes
    (`map_scene.build_map_scene()`'s "Map View" tab): profiling a real
    27,531-triangle chapter scene found ~1500ms of every ~1736ms redraw
    (86%) was pure Tcl/Tk per-item `create_polygon`/`delete("all")`
    overhead, not Python math (isolating the pure-Python project+sort loop
    alone: 237ms) - no amount of vectorizing the *math* fixes a bottleneck
    that's actually in Tk's own per-item object management. Rasterizing to
    one array and blitting one image removes that bottleneck entirely -
    see `fe_modding.gui.map_scene`'s own docstring and this project's
    `MAP_PLACEMENT_INVESTIGATION.md`-adjacent planning notes for the full
    profiling. This is why `fe_modding.gui` now depends on numpy (declared
    in `requirements.txt`) - the rest of the core app stays stdlib-only
    except Pillow, same one-purpose-exception precedent as
    `fe_modding.formats.tpl`.

    Skeleton bone markers/connector lines/highlight are still drawn as real
    Canvas primitives, layered on top of the blitted mesh image - cheap
    (tens of items, not thousands), no reason to move them into the
    rasterizer.

    When a GPU is available the mesh is drawn by
    `gpu_renderer.GpuSceneRenderer` instead (wgpu, same shading rules,
    geometry uploaded once per model), which keeps orbiting a full chapter
    scene at interactive frame rates; `_rasterize()` stays as the fallback
    when wgpu or a GPU adapter is missing. Either way the frame goes into
    one persistent PhotoImage, and only the overlay items are recreated per
    frame."""

    def __init__(self, parent: tk.Misc):
        super().__init__(parent, background="#2b2b2b", highlightthickness=0)
        self._triangles: list[_Triangle] = []
        self._bone_markers: dict[int, tuple[float, float, float]] = {}
        self._bone_parents: dict[int, int] = {}
        self._bone_names: dict[int, str] = {}
        self._posed_positions: dict[int, tuple[float, float, float]] | None = None
        self._animated_triangles: list[_Triangle] | None = None
        self._highlighted_bone: int | None = None
        self._show_mesh = True
        self._show_skeleton = True
        self._grid: "GridOverlay | None" = None
        self._show_grid = False
        self._gameplay_grid: "GridOverlay | None" = None
        self._show_gameplay_grid = False
        self._center = (0.0, 0.0, 0.0)
        self._extent = 1.0
        self._yaw = 0.6
        self._pitch = -0.4
        self._zoom = 1.0
        self._screen_x_sign = 1.0
        self._screen_y_sign = 1.0
        self._drag_start: tuple[int, int, float, float] | None = None
        self._pan_last: tuple[int, int] | None = None
        # the fitted center; panning moves _center away from it
        self._home_center = (0.0, 0.0, 0.0)
        self._redraw_pending = False
        # Keeps the live PhotoImage alive - Tkinter doesn't hold its own
        # reference, so without this the image gets garbage-collected and
        # the canvas silently goes blank.
        self._photo_image: "ImageTk.PhotoImage | None" = None
        self._image_item: int | None = None
        # created on the first redraw (requesting a GPU adapter takes ~1s);
        # _gpu_uploaded is the triangle list whose geometry the GPU holds
        self._gpu: "gpu_renderer.GpuSceneRenderer | None" = None
        self._gpu_checked = False
        self._gpu_model: list[_Triangle] | None = None
        self._gpu_uploaded: list[_Triangle] | None = None

        self.bind("<ButtonPress-1>", self._on_drag_start)
        self.bind("<B1-Motion>", self._on_drag_motion)
        # pan: right or middle drag (Button-2 is the right button on macOS),
        # or Shift + left drag for trackpads
        for button in (2, 3):
            self.bind(f"<ButtonPress-{button}>", self._on_pan_start)
            self.bind(f"<B{button}-Motion>", self._on_pan_motion)
        self.bind("<Shift-ButtonPress-1>", self._on_pan_start)
        self.bind("<Shift-B1-Motion>", self._on_pan_motion)
        self.bind("<MouseWheel>", self._on_zoom)
        self.bind("<Button-4>", lambda e: self._zoom_by(1.15, e.x, e.y))
        self.bind("<Button-5>", lambda e: self._zoom_by(1 / 1.15, e.x, e.y))
        self.bind("<Configure>", lambda _e: self._schedule_redraw())

    def set_model(
        self,
        triangles: list[_Triangle],
        bone_markers: dict[int, tuple[float, float, float]],
        bone_parents: dict[int, int],
        bone_names: dict[int, str],
    ) -> None:
        self._triangles = triangles
        self._bone_markers = bone_markers
        self._bone_parents = bone_parents
        self._bone_names = bone_names
        self._posed_positions = None
        self._animated_triangles = None
        self._highlighted_bone = None
        self._gpu_model = None
        self._fit_to_content()
        self._schedule_redraw()

    def set_pose(
        self,
        positions: dict[int, tuple[float, float, float]] | None,
        triangles: list[_Triangle] | None = None,
    ) -> None:
        """Override bone positions with a posed frame (see
        ``fe_modding.formats.engine_pose``), and optionally the mesh triangles
        too (skinned to follow - see ``_skin_triangles()``). Pass ``None``
        for both to revert to the static bind pose/mesh."""
        self._posed_positions = positions
        self._animated_triangles = triangles
        self._schedule_redraw()

    def set_show_mesh(self, show: bool) -> None:
        """Toggle the mesh's visibility - the skeleton overlay (markers and
        connector lines) is controlled separately by `set_show_skeleton()`."""
        self._show_mesh = show
        self._schedule_redraw()

    def set_show_skeleton(self, show: bool) -> None:
        self._show_skeleton = show
        self._schedule_redraw()

    def set_grid(self, overlay: "GridOverlay | None") -> None:
        """Set (or clear, with `None`) the placement-grid overlay to draw -
        see `GridOverlay`'s own docstring. Independent of `set_show_grid()`'s
        visibility toggle, so a caller can hand over a chapter's grid once
        and let the checkbox purely control visibility."""
        self._grid = overlay
        self._schedule_redraw()

    def set_show_grid(self, show: bool) -> None:
        self._show_grid = show
        self._schedule_redraw()

    def set_gameplay_grid(self, overlay: "GridOverlay | None") -> None:
        """Set (or clear) the *other* grid - `MapCapacity.x_size`/`y_size`,
        the in-game tactical grid, strong-evidence-not-confirmed (see
        `map_scene.compute_gameplay_grid_overlay()`'s own docstring).
        Deliberately a separate slot from `set_grid()`'s placement grid, not
        a shared one - the two use unrelated coordinate spaces and can be
        shown independently or together."""
        self._gameplay_grid = overlay
        self._schedule_redraw()

    def set_show_gameplay_grid(self, show: bool) -> None:
        self._show_gameplay_grid = show
        self._schedule_redraw()

    def highlight_bone(self, bone_index: int) -> None:
        self._highlighted_bone = bone_index
        self._schedule_redraw()

    def reset_view(self) -> None:
        self._yaw, self._pitch, self._zoom = 0.6, -0.4, 1.0
        self._center = self.__dict__.get("_home_center", self.__dict__.get("_center"))
        self._screen_x_sign = 1.0
        self._screen_y_sign = 1.0
        self._schedule_redraw()

    def top_down_view(self) -> None:
        # Game-facing battle-map orientation. Chapter 11's goal marker and
        # chapter 12's boat/bridge landmarks show that the app's previous
        # top-down preset still had both screen axes inverted relative to the
        # in-game map. Keep the camera above the Y-up terrain for backface
        # culling, and express the orientation as screen-space signs instead
        # of looking from below.
        self._yaw, self._pitch, self._zoom = 0.0, -math.pi / 2.0, 1.0
        self._center = self.__dict__.get("_home_center", self.__dict__.get("_center"))
        self._screen_x_sign = 1.0
        self._screen_y_sign = -1.0
        self._schedule_redraw()

    def _fit_to_content(self) -> None:
        points = [v for tri in self._triangles for v in (tri.a, tri.b, tri.c)]
        points.extend(self._bone_markers.values())
        if not points:
            self._center = self._home_center = (0.0, 0.0, 0.0)
            self._extent = 1.0
            return
        array = np.asarray(points, dtype=np.float64)
        lo, hi = array.min(axis=0), array.max(axis=0)
        self._center = self._home_center = tuple(((lo + hi) / 2).tolist())
        self._extent = max(float((hi - lo).max()), 1e-6)

    def _on_drag_start(self, event: tk.Event) -> None:
        self._drag_start = (event.x, event.y, self._yaw, self._pitch)

    def _on_drag_motion(self, event: tk.Event) -> None:
        if self._drag_start is None:
            return
        start_x, start_y, start_yaw, start_pitch = self._drag_start
        self._yaw = start_yaw + (event.x - start_x) * 0.01
        self._pitch = start_pitch + (event.y - start_y) * 0.01
        self._schedule_redraw()

    def _on_pan_start(self, event: tk.Event) -> None:
        self._pan_last = (event.x, event.y)
        self._drag_start = None  # releasing Shift mid-drag must not orbit from a stale start

    def _on_pan_motion(self, event: tk.Event) -> None:
        if self._pan_last is None:
            return
        last_x, last_y = self._pan_last
        self._pan_last = (event.x, event.y)
        # drag the content with the cursor: shift the orbit center the
        # opposite way, in the camera's screen plane
        self._shift_center(-(event.x - last_x), -(event.y - last_y))
        self._schedule_redraw()

    def _view_scale(self) -> float:
        width = self.winfo_width() or 480
        height = self.winfo_height() or 360
        return (min(width, height) * FIT_FRACTION / self._extent) * self._zoom

    def _shift_center(self, dx: float, dy: float) -> None:
        """Move the orbit center by (dx, dy) screen pixels - the inverse of
        `to_screen()`'s x/y mapping, rotated back into world space."""
        scale = self._view_scale()
        camera = np.array([dx / (scale * self._screen_x_sign), -dy / (scale * self._screen_y_sign), 0.0])
        world = self._rotation_matrix().T @ camera
        self._center = tuple((np.array(self._center) + world).tolist())

    def _on_zoom(self, event: tk.Event) -> None:
        self._zoom_by(1.15 if event.delta > 0 else 1 / 1.15, event.x, event.y)

    def _zoom_by(self, factor: float, x: float | None = None, y: float | None = None) -> None:
        """Zoom by `factor`, keeping the point under (x, y) - the cursor -
        fixed on screen, so zooming in goes where the mouse points."""
        old_zoom = self._zoom
        self._zoom = max(0.2, min(ZOOM_MAX, self._zoom * factor))
        if x is not None and y is not None and self._zoom != old_zoom:
            width = self.winfo_width() or 480
            height = self.winfo_height() or 360
            # cursor offset from the view center, scaled by how much of it the
            # zoom pulls in
            keep = 1.0 - old_zoom / self._zoom
            self._zoom, zoomed = old_zoom, self._zoom
            self._shift_center((x - width / 2) * keep, (y - height / 2) * keep)
            self._zoom = zoomed
        self._schedule_redraw()

    def _schedule_redraw(self) -> None:
        if self._redraw_pending:
            return
        self._redraw_pending = True
        # the GPU path renders in a few ms, so don't cap it at the timer;
        # input events arriving during a frame still coalesce into one redraw
        self.after(1 if self._gpu is not None else 16, self._redraw)

    def _rotate(self, vector: tuple[float, float, float]) -> tuple[float, float, float]:
        x, y, z = vector
        cosy, siny = math.cos(self._yaw), math.sin(self._yaw)
        cosp, sinp = math.cos(self._pitch), math.sin(self._pitch)
        x1 = x * cosy + z * siny
        z1 = -x * siny + z * cosy
        y2 = y * cosp - z1 * sinp
        z2 = y * sinp + z1 * cosp
        return x1, y2, z2

    def _rotation_matrix(self) -> "np.ndarray":
        """The same yaw-then-pitch composition as _rotate(), as a 3x3 numpy
        matrix R such that R @ column_vector reproduces _rotate()'s result -
        for a batch of row-vectors this is `points @ R.T`."""
        cosy, siny = math.cos(self._yaw), math.sin(self._yaw)
        cosp, sinp = math.cos(self._pitch), math.sin(self._pitch)
        r_yaw = np.array([[cosy, 0.0, siny], [0.0, 1.0, 0.0], [-siny, 0.0, cosy]])
        r_pitch = np.array([[1.0, 0.0, 0.0], [0.0, cosp, -sinp], [0.0, sinp, cosp]])
        return r_pitch @ r_yaw

    def _rasterize(self, triangles: list[_Triangle], width: int, height: int) -> "np.ndarray":
        """Render `triangles` into an (height, width, 3) uint8 framebuffer:
        batch-transform every vertex with one matrix multiply, drop
        back-facing triangles, then for each remaining triangle rasterize
        its own screen-space bounding box with vectorized numpy (a
        barycentric inside-test, a per-pixel Z-buffer test, and per-pixel
        bilinear-filtered texture sampling where the triangle has one) -
        see this class's own docstring for why this replaced one
        `create_polygon` per triangle."""
        bg = np.array([43, 43, 43], dtype=np.uint8)
        framebuffer = np.full((height, width, 3), bg, dtype=np.uint8)
        if not triangles:
            return framebuffer
        zbuffer = np.full((height, width), np.inf, dtype=np.float64)

        rot = self._rotation_matrix()
        ccx, ccy, ccz = self._center
        center = np.array([ccx, ccy, ccz])
        cx0, cy0 = width / 2.0, height / 2.0
        scale = (min(width, height) * FIT_FRACTION / self._extent) * self._zoom

        tri_a = np.array([t.a for t in triangles])
        tri_b = np.array([t.b for t in triangles])
        tri_c = np.array([t.c for t in triangles])
        normals = np.array([t.normal for t in triangles])

        def to_screen(points: "np.ndarray") -> tuple["np.ndarray", "np.ndarray", "np.ndarray"]:
            rotated = (points - center) @ rot.T
            return (
                cx0 + rotated[:, 0] * scale * self._screen_x_sign,
                cy0 - rotated[:, 1] * scale * self._screen_y_sign,
                rotated[:, 2],
            )

        ax, ay, az = to_screen(tri_a)
        bx, by, bz = to_screen(tri_b)
        cx, cy, cz = to_screen(tri_c)
        rotated_normals = normals @ rot.T
        nz = rotated_normals[:, 2]

        # The camera looks toward +Z (larger camera-space z = farther away,
        # matching the Z-buffer's "smaller depth wins" convention below), so
        # a triangle facing the camera has a normal pointing toward -Z, not
        # +Z - confirmed against real data: even the already-validated,
        # zero-transform terrain mesh (unrelated to map_scene.py's own
        # transform math) has negative nz on ~98% of its triangles at a
        # normal viewing angle. The old renderer never needed to get this
        # right (no culling, just `max(0, nz)` for a dim-if-facing-away
        # brightness floor - so a backwards sign there just meant "usually
        # dim," not "usually invisible") - backface culling is what actually
        # exposed it.
        visible = nz < 0.0
        brightness = 0.35 + 0.65 * np.maximum(-nz, 0.0)

        full_gx, full_gy = np.meshgrid(np.arange(width) + 0.5, np.arange(height) + 0.5)

        # Bounding boxes + the barycentric denominator, vectorized once over
        # every triangle instead of computed with plain Python min/max/abs
        # inside the loop below - profiling a real merged-scene redraw found
        # ~200K such builtin calls were real, avoidable time. Converting the
        # per-vertex screen coordinates to plain Python lists once (`.tolist()`)
        # rather than repeatedly indexing the numpy arrays inside the loop is
        # the other half of this - a single numpy-scalar element access
        # (`ax[i]`) is measurably slower than plain list indexing when done
        # tens of thousands of times in a tight Python loop.
        tri_minx = np.maximum(np.floor(np.minimum(np.minimum(ax, bx), cx)), 0).astype(np.int64)
        tri_maxx = np.minimum(np.ceil(np.maximum(np.maximum(ax, bx), cx)), width - 1).astype(np.int64)
        tri_miny = np.maximum(np.floor(np.minimum(np.minimum(ay, by), cy)), 0).astype(np.int64)
        tri_maxy = np.minimum(np.ceil(np.maximum(np.maximum(ay, by), cy)), height - 1).astype(np.int64)
        denom = (by - cy) * (ax - cx) + (cx - bx) * (ay - cy)

        ax_l, ay_l, bx_l, by_l, cx_l, cy_l = ax.tolist(), ay.tolist(), bx.tolist(), by.tolist(), cx.tolist(), cy.tolist()
        az_l, bz_l, cz_l = az.tolist(), bz.tolist(), cz.tolist()
        denom_l = denom.tolist()
        minx_l, maxx_l = tri_minx.tolist(), tri_maxx.tolist()
        miny_l, maxy_l = tri_miny.tolist(), tri_maxy.tolist()

        for i in np.nonzero(visible)[0].tolist():
            minx, maxx, miny, maxy = minx_l[i], maxx_l[i], miny_l[i], maxy_l[i]
            if minx > maxx or miny > maxy:
                continue

            d = denom_l[i]
            if abs(d) < 1e-9:
                continue

            axi, ayi, bxi, byi, cxi, cyi = ax_l[i], ay_l[i], bx_l[i], by_l[i], cx_l[i], cy_l[i]
            px = full_gx[miny : maxy + 1, minx : maxx + 1]
            py = full_gy[miny : maxy + 1, minx : maxx + 1]
            w0 = ((byi - cyi) * (px - cxi) + (cxi - bxi) * (py - cyi)) / d
            w1 = ((cyi - ayi) * (px - cxi) + (axi - cxi) * (py - cyi)) / d
            w2 = 1.0 - w0 - w1
            # fused inside-test: all three barycentric weights >= eps, done
            # as one min()+compare instead of three compares + two ANDs
            inside = np.minimum(np.minimum(w0, w1), w2) >= -1e-6
            if not inside.any():
                continue

            depth = w0 * az_l[i] + w1 * bz_l[i] + w2 * cz_l[i]
            zbuf_region = zbuffer[miny : maxy + 1, minx : maxx + 1]
            closer = inside & (depth < zbuf_region)
            if not closer.any():
                continue

            tri = triangles[i]
            if tri.texture_layers:
                sampled_rgba = _sample_texture_layers(tri.texture_layers, w0, w1, w2)
                sampled = sampled_rgba[..., :3] * brightness[i]
                alpha = (sampled_rgba[..., 3] / 255.0) * tri.alpha
            elif tri.texture is not None and tri.uv is not None:
                uv0, uv1, uv2 = tri.uv
                u = w0 * uv0[0] + w1 * uv1[0] + w2 * uv2[0]
                v = w0 * uv0[1] + w1 * uv1[1] + w2 * uv2[1]
                sampled_rgba = _sample_texture_batch(tri.texture, u, v)
                sampled = sampled_rgba[..., :3] * brightness[i]
                alpha = (sampled_rgba[..., 3] / 255.0) * tri.alpha if sampled_rgba.shape[2] >= 4 else tri.alpha
            else:
                sampled = np.array(tri.color, dtype=np.float64) * brightness[i]
                sampled = np.broadcast_to(sampled, px.shape + (3,))
                alpha = np.full(px.shape, tri.alpha, dtype=np.float64)
            pixel_colors = np.minimum(np.maximum(sampled, 0), 255).astype(np.uint8)

            fb_region = framebuffer[miny : maxy + 1, minx : maxx + 1]
            if tri.blend_mode == "additive":
                add_mask = closer & (alpha > 0.001)
                if add_mask.any():
                    src_alpha = alpha[..., None]
                    blended = fb_region.astype(np.float64) + pixel_colors.astype(np.float64) * src_alpha
                    fb_region[add_mask] = np.minimum(np.maximum(blended, 0), 255).astype(np.uint8)[add_mask]
                    zbuf_region[add_mask] = depth[add_mask]
                continue

            opaque = closer & (alpha >= 0.995)
            translucent = closer & (alpha > 0.001) & ~opaque
            fb_region[opaque] = pixel_colors[opaque]
            zbuf_region[opaque] = depth[opaque]
            if translucent.any():
                src_alpha = alpha[..., None]
                blended = pixel_colors.astype(np.float64) * src_alpha + fb_region.astype(np.float64) * (1.0 - src_alpha)
                fb_region[translucent] = np.minimum(np.maximum(blended, 0), 255).astype(np.uint8)[translucent]
                zbuf_region[translucent] = depth[translucent]

        return framebuffer

    def _gpu_frame(self, triangles: list[_Triangle], width: int, height: int, scale: float) -> "Image.Image | None":
        """Render `triangles` on the GPU, or None to use `_rasterize()`."""
        if not self._gpu_checked:
            self._gpu_checked = True
            self._gpu = gpu_renderer.create_renderer()
        if self._gpu is None:
            return None
        try:
            if self._gpu_model is not self._triangles:
                self._gpu.set_triangles(self._triangles)
                self._gpu_model = self._triangles
                self._gpu_uploaded = self._triangles
            if self._gpu_uploaded is not triangles:
                # a posed frame (or back to the bind pose) of the same model
                if not self._gpu.update_positions(triangles):
                    self._gpu.set_triangles(triangles)
                    self._gpu_model = None
                self._gpu_uploaded = triangles
            return self._gpu.render_image(
                width,
                height,
                self._rotation_matrix(),
                self._center,
                scale,
                self._extent,
                self._screen_x_sign,
                self._screen_y_sign,
            )
        except Exception:  # noqa: BLE001 - a driver/device failure falls back to the CPU rasterizer
            gpu_renderer.log.warning("GPU render failed - switching to the CPU rasterizer", exc_info=True)
            self._gpu = None
            return None

    def _show_frame(self, pil_image: Image.Image) -> None:
        """Blit into the persistent PhotoImage, recreating it only when the
        canvas size changes."""
        photo = self._photo_image
        if photo is None or photo.width() != pil_image.width or photo.height() != pil_image.height:
            self._photo_image = ImageTk.PhotoImage(pil_image)
        else:
            photo.paste(pil_image)
        if self._image_item is None:
            self._image_item = self.create_image(0, 0, image=self._photo_image, anchor="nw")
        else:
            self.itemconfigure(self._image_item, image=self._photo_image, state="normal")
            self.tag_lower(self._image_item)

    def _redraw(self) -> None:
        self._redraw_pending = False
        # everything except the mesh image is an overlay, rebuilt per frame
        self.addtag_all("overlay")
        if self._image_item is not None:
            self.dtag(self._image_item, "overlay")
        self.delete("overlay")
        width = self.winfo_width() or 480
        height = self.winfo_height() or 360
        cx, cy = width / 2, height / 2
        scale = (min(width, height) * FIT_FRACTION / self._extent) * self._zoom
        if not self._show_mesh or (not self._triangles and not self._bone_markers):
            if self._image_item is not None:
                self.itemconfigure(self._image_item, state="hidden")
        if not self._triangles and not self._bone_markers:
            self.create_text(width / 2, height / 2, text="No mesh data for this model set", fill="#999999")
            return

        positions = self._posed_positions if self._posed_positions is not None else self._bone_markers

        if self._show_mesh:
            triangles = self._animated_triangles if self._animated_triangles is not None else self._triangles
            frame = self._gpu_frame(triangles, width, height, scale)
            if frame is None:
                frame = Image.fromarray(self._rasterize(triangles, width, height), mode="RGB")
            self._show_frame(frame)

        ccx, ccy, ccz = self._center

        def to_screen(point: tuple[float, float, float]) -> tuple[float, float, float]:
            rx, ry, rz = self._rotate((point[0] - ccx, point[1] - ccy, point[2] - ccz))
            return cx + rx * scale * self._screen_x_sign, cy - ry * scale * self._screen_y_sign, rz

        if self._show_grid and self._grid is not None:
            self._draw_grid(self._grid, to_screen, "#ffee55")
        if self._show_gameplay_grid and self._gameplay_grid is not None:
            self._draw_grid(self._gameplay_grid, to_screen, "#55ddff")

        if not self._show_skeleton:
            return

        drawables: list[tuple[float, str, object, object]] = []
        for bone_index, parent_index in self._bone_parents.items():
            if bone_index not in positions or parent_index not in positions:
                continue
            p0 = to_screen(positions[bone_index])
            p1 = to_screen(positions[parent_index])
            depth = (p0[2] + p1[2]) / 2
            drawables.append((depth, "line", (p0[:2], p1[:2]), None))

        for bone_index, pos in positions.items():
            sx, sy, sz = to_screen(pos)
            drawables.append((sz, "marker", (sx, sy), bone_index))

        drawables.sort(key=lambda d: d[0])

        for _depth, kind, payload, extra in drawables:
            if kind == "line":
                (x0, y0), (x1, y1) = payload
                self.create_line(x0, y0, x1, y1, fill="#66ccff", width=2)
            else:
                x, y = payload
                is_highlighted = extra == self._highlighted_bone
                radius = 5 if is_highlighted else 3
                fill = "#ffcc33" if is_highlighted else "#ffffff"
                self.create_oval(x - radius, y - radius, x + radius, y + radius, fill=fill, outline="")
                if is_highlighted:
                    name = self._bone_names.get(extra, str(extra))
                    self.create_text(x + 8, y, text=name, fill="#ffffff", anchor="w")

    def _draw_grid(self, grid: "GridOverlay", to_screen, color: str) -> None:
        """Draw one grid lattice (real Canvas primitives, same "cheap,
        layered on top of the blitted mesh image" treatment as the skeleton
        overlay above) in `color` - `_redraw()` calls this once per overlay
        (the confirmed placement grid and/or the strong-evidence gameplay
        grid, see `set_grid()`/`set_gameplay_grid()`), each its own color so
        the two - unrelated coordinate spaces, different confidence levels -
        are never visually ambiguous when shown together. Coordinate labels
        sit only along the two near edges (column indices along the min-row
        edge, row indices along the min-col edge), spreadsheet-header style,
        rather than one label per cell - hundreds of overlapping per-cell
        labels would be unreadable on a real chapter (up to ~76x64 tiles),
        whereas an edge ruler is enough to read off any tile's (x, y) by
        following its grid lines to the edge.

        **Line/label spacing is picked adaptively from the current zoom, not
        fixed at one tile.** A first version drew every single 5-unit tile
        boundary unconditionally - fine in isolation, but at this renderer's
        default fit-to-content zoom a tile projects to only ~4px on screen
        for a real chapter (`bmap01`: extent ~330 world units into a ~700px
        canvas), so ~59 column lines packed into a few hundred pixels
        rendered as a solid yellow mass that obscured the terrain entirely -
        caught by rendering a real chapter and looking at it, not assumed
        fine from the math alone. `_grid_interval()` measures one tile's
        actual on-screen size this frame and picks the smallest candidate
        step (1/2/5/10/20/50 tiles) whose lines land at least ~18px apart,
        so the grid stays a readable reference at any zoom level - zooming
        in reveals finer lines/labels, matching how a map app's own grid
        overlay behaves."""
        y0 = 0.0

        def tile_point(col: float, row: float) -> tuple[float, float, float]:
            return (
                (col - grid.origin_col) * grid.tile_scale,
                y0,
                (row - grid.origin_row) * grid.tile_scale,
            )

        p0 = to_screen(tile_point(grid.col_min, grid.row_min))
        p1 = to_screen(tile_point(grid.col_min + 1, grid.row_min))
        screen_tile_size = math.hypot(p1[0] - p0[0], p1[1] - p0[1]) or 1e-6
        interval = 50
        for candidate in (1, 2, 5, 10, 20, 50):
            if candidate * screen_tile_size >= 18.0:
                interval = candidate
                break

        def aligned_range(lo: int, hi: int) -> range:
            start = -(-lo // interval) * interval  # ceil(lo / interval) * interval
            return range(start, hi + 1, interval)

        for col in aligned_range(grid.col_min, grid.col_max):
            p0 = to_screen(tile_point(col, grid.row_min))
            p1 = to_screen(tile_point(col, grid.row_max))
            self.create_line(p0[0], p0[1], p1[0], p1[1], fill=color, width=1)
        for row in aligned_range(grid.row_min, grid.row_max):
            p0 = to_screen(tile_point(grid.col_min, row))
            p1 = to_screen(tile_point(grid.col_max, row))
            self.create_line(p0[0], p0[1], p1[0], p1[1], fill=color, width=1)

        for col in aligned_range(grid.col_min, grid.col_max):
            sx, sy, _sz = to_screen(tile_point(col, grid.row_min))
            self.create_text(sx, sy + 9, text=str(col), fill=color, font=("Segoe UI", 7))
        for row in aligned_range(grid.row_min, grid.row_max):
            sx, sy, _sz = to_screen(tile_point(grid.col_min, row))
            self.create_text(sx - 10, sy, text=str(row), fill=color, font=("Segoe UI", 7))


class _ModelPreview(ttk.Frame):
    """The canvas + skeleton tree + animation/playback controls shared by
    both ``ModelViewer`` (the global "3D Models" panel, with its own
    set-browsing list to the left of this) and ``ModelPreviewDialog`` (a
    lightweight popup for a single model resolved elsewhere - see
    ``map_editor.py``'s "View Model..." buttons). Factored out once a
    second, independent caller needed the same widgets rather than a
    second near-copy of ~200 lines of canvas/playback code."""

    def __init__(self, parent: tk.Misc, mesh_only: bool = False):
        """``mesh_only=True`` skips building the Skeleton/Animations
        notebook entirely - for a merged multi-object scene (see
        ``map_editor.py``'s "3D Terrain" tab) there's no single meaningful
        skeleton or animation list to show, and the canvas alone gets the
        whole frame instead of sharing it with an empty notebook."""
        super().__init__(parent)
        self._mesh_only = mesh_only
        self._loaded: _LoadedSet | None = None
        self._current_animation: animation.GaAnimation | None = None
        self._playing = False
        self._play_after_id: str | None = None
        self._build_widgets()

    def cleanup(self) -> None:
        self._stop_playback()

    # -- layout ---------------------------------------------------------------
    def _build_widgets(self) -> None:
        center = self if self._mesh_only else None
        if not self._mesh_only:
            paned = ttk.PanedWindow(self, orient="horizontal")
            paned.pack(fill="both", expand=True)
            center = ttk.Frame(paned, padding=8)
            paned.add(center, weight=3)
        canvas_header = ttk.Frame(center)
        canvas_header.pack(fill="x")
        ttk.Label(canvas_header, text="Drag to orbit, scroll to zoom, right-drag or Shift+drag to pan", style="Muted.TLabel").pack(side="left")
        ttk.Button(canvas_header, text="Reset View", command=self._reset_view).pack(side="right")
        ttk.Button(canvas_header, text="Top Down", command=self._top_down_view).pack(side="right", padx=(0, 8))
        self._show_mesh_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(
            canvas_header, text="Show mesh", variable=self._show_mesh_var, command=self._on_show_mesh_toggled
        ).pack(side="right", padx=(0, 8))
        self._show_skeleton_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(
            canvas_header,
            text="Show skeleton",
            variable=self._show_skeleton_var,
            command=lambda: self._canvas.set_show_skeleton(self._show_skeleton_var.get()),
        ).pack(side="right", padx=(0, 8))
        # Only meaningful once a caller hands over a chapter's placement
        # grid via set_grid() (map_editor.py's "3D Terrain"/"Map View" tabs)
        # - stays disabled (not just unchecked) for an ordinary single-model
        # view, where there's no grid concept at all. Labeled "placement",
        # not just "grid", once set_gameplay_grid() added a second,
        # unrelated grid below - see that checkbox's own comment for why the
        # two need to stay visually and textually distinct.
        self._show_grid_var = tk.BooleanVar(value=False)
        self._show_grid_check = ttk.Checkbutton(
            canvas_header,
            text="Show placement grid",
            variable=self._show_grid_var,
            command=self._on_show_grid_toggled,
            state="disabled",
        )
        self._show_grid_check.pack(side="right", padx=(0, 8))
        # The *other* grid - MapCapacity.x_size/y_size, the in-game tactical
        # grid - strong evidence, not confirmed the way the placement grid
        # above is (see map_scene.compute_gameplay_grid_overlay()'s own
        # docstring for the full reasoning and what's still open). The
        # checkbox label says so plainly rather than implying equal
        # confidence with "Show placement grid" - this project's own
        # discipline about not overclaiming a finding.
        self._show_gameplay_grid_var = tk.BooleanVar(value=False)
        self._show_gameplay_grid_check = ttk.Checkbutton(
            canvas_header,
            text="Show gameplay grid (unconfirmed)",
            variable=self._show_gameplay_grid_var,
            command=self._on_show_gameplay_grid_toggled,
            state="disabled",
        )
        self._show_gameplay_grid_check.pack(side="right", padx=(0, 8))
        self._canvas = _ModelCanvas(center)
        if self._mesh_only:
            self._canvas.top_down_view()
        self._canvas.pack(fill="both", expand=True, pady=(4, 4))
        self._mesh_info_label = ttk.Label(center, text="", style="Muted.TLabel")
        self._mesh_info_label.pack(anchor="w")

        if self._mesh_only:
            # no Skeleton/Animations notebook - these widgets are created
            # unpacked (never shown) so show()/_on_animation_selected()/etc.
            # can keep referencing them unconditionally instead of needing
            # an "if mesh_only" branch at every call site.
            self._bone_tree = ttk.Treeview(self)
            self._anim_list = tk.Listbox(self)
            self._anim_summary_label = ttk.Label(self)
            self._curve_tree = ttk.Treeview(self)
            self._play_button = ttk.Button(self)
            self._frame_scale = ttk.Scale(self)
            self._frame_label = ttk.Label(self)
            return

        right = ttk.Frame(paned, padding=8)
        paned.add(right, weight=2)
        notebook = ttk.Notebook(right)
        notebook.pack(fill="both", expand=True)

        skel_tab = ttk.Frame(notebook, padding=6)
        notebook.add(skel_tab, text="Skeleton")
        ttk.Label(
            skel_tab,
            text=(
                "Bone hierarchy (name / parent). Select a bone to\n"
                "highlight it; pick an animation to pose the model\n"
                "the way the game does."
            ),
            style="Muted.TLabel",
            justify="left",
        ).pack(anchor="w", pady=(0, 6))
        self._bone_tree = ttk.Treeview(skel_tab, show="tree")
        self._bone_tree.pack(fill="both", expand=True)
        self._bone_tree.bind("<<TreeviewSelect>>", lambda e: self._on_bone_selected())

        anim_tab = ttk.Frame(notebook, padding=6)
        notebook.add(anim_tab, text="Animations")
        ttk.Label(anim_tab, text="Animation files (.ga)").pack(anchor="w")
        anim_list_frame = ttk.Frame(anim_tab)
        anim_list_frame.pack(fill="x", pady=(2, 6))
        self._anim_list = tk.Listbox(anim_list_frame, height=8, exportselection=False)
        self._anim_list.pack(fill="both", expand=True, side="left")
        anim_scroll = ttk.Scrollbar(anim_list_frame, command=self._anim_list.yview)
        anim_scroll.pack(fill="y", side="right")
        self._anim_list.config(yscrollcommand=anim_scroll.set)
        self._anim_list.bind("<<ListboxSelect>>", lambda e: self._on_animation_selected())

        self._anim_summary_label = ttk.Label(anim_tab, text="", style="Muted.TLabel", justify="left")
        self._anim_summary_label.pack(anchor="w", pady=(0, 4))

        playback_row = ttk.Frame(anim_tab)
        playback_row.pack(fill="x", pady=(0, 4))
        self._play_button = ttk.Button(playback_row, text="Play", command=self._toggle_play, state="disabled")
        self._play_button.pack(side="left")
        self._frame_scale = ttk.Scale(playback_row, from_=0, to=0, orient="horizontal", command=self._on_frame_scrub)
        self._frame_scale.config(state="disabled")
        self._frame_scale.pack(side="left", fill="x", expand=True, padx=(8, 8))
        self._frame_label = ttk.Label(playback_row, text="", style="Muted.TLabel", width=10)
        self._frame_label.pack(side="left")

        ttk.Label(
            anim_tab,
            text=(
                "Skeleton + mesh playback (see model_viewer.py's module\n"
                "note) - forward kinematics/skinning built on skeleton.py's\n"
                "confirmed/strong-evidence bind data, not itself confirmed\n"
                "against the game."
            ),
            style="Muted.TLabel",
            justify="left",
        ).pack(anchor="w", pady=(0, 4))
        columns = ("bone", "channel", "end_frame", "keyframes", "peak")
        self._curve_tree = ttk.Treeview(anim_tab, columns=columns, show="headings", height=10)
        headings = (
            ("bone", "Bone", 90),
            ("channel", "Channel", 90),
            ("end_frame", "End Frame", 70),
            ("keyframes", "Keyframes", 70),
            ("peak", "Peak (scaled, unit unconfirmed)", 170),
        )
        for col, label, width in headings:
            self._curve_tree.heading(col, text=label)
            self._curve_tree.column(col, width=width, anchor="w")
        self._curve_tree.pack(fill="both", expand=True, pady=(4, 0))

    def _reset_view(self) -> None:
        self._canvas.reset_view()

    def _top_down_view(self) -> None:
        self._canvas.top_down_view()

    def _on_show_mesh_toggled(self) -> None:
        self._canvas.set_show_mesh(self._show_mesh_var.get())

    def _on_show_grid_toggled(self) -> None:
        self._canvas.set_show_grid(self._show_grid_var.get())

    def set_grid(self, overlay: "GridOverlay | None") -> None:
        """Hand over (or clear, with `None`) a chapter's placement-grid
        overlay - see `GridOverlay`'s own docstring. Enables/disables the
        "Show grid" checkbox based on whether `overlay` is real (an ordinary
        single-model view never calls this, so the checkbox stays disabled
        there); clearing the overlay also force-unchecks it rather than
        leaving a stale "checked but disabled" state."""
        self._canvas.set_grid(overlay)
        if overlay is None:
            self._show_grid_var.set(False)
            self._canvas.set_show_grid(False)
            self._show_grid_check.config(state="disabled")
        else:
            self._show_grid_check.config(state="normal")

    def _on_show_gameplay_grid_toggled(self) -> None:
        self._canvas.set_show_gameplay_grid(self._show_gameplay_grid_var.get())

    def set_gameplay_grid(self, overlay: "GridOverlay | None") -> None:
        """Hand over (or clear) a chapter's gameplay-grid overlay - see
        `map_scene.compute_gameplay_grid_overlay()`'s own docstring for what
        this is and its confidence level. Same enable/disable-checkbox
        pattern as `set_grid()`, kept as a fully separate method/slot since
        the two grids are unrelated coordinate spaces a caller may want
        independently."""
        self._canvas.set_gameplay_grid(overlay)
        if overlay is None:
            self._show_gameplay_grid_var.set(False)
            self._canvas.set_show_gameplay_grid(False)
            self._show_gameplay_grid_check.config(state="disabled")
        else:
            self._show_gameplay_grid_check.config(state="normal")

    # -- public: what a caller drives -----------------------------------------
    def show(self, loaded: _LoadedSet | None, empty_message: str = "No model data.") -> None:
        """Display ``loaded`` (or clear everything and show
        ``empty_message`` if ``None``)."""
        self._stop_playback()
        self._current_animation = None
        self._loaded = loaded

        if loaded is None:
            self._canvas.set_model([], {}, {}, {})
            self._mesh_info_label.config(text=empty_message)
            self._bone_tree.delete(*self._bone_tree.get_children())
            self._anim_list.delete(0, "end")
            self._anim_summary_label.config(text="")
            self._curve_tree.delete(*self._curve_tree.get_children())
            self._frame_scale.config(to=0, state="disabled")
            self._play_button.config(state="disabled")
            self._frame_label.config(text="")
            return

        bone_names = {i: b.name for i, b in enumerate(loaded.bones)}
        bone_parents = {i: b.parent_index for i, b in enumerate(loaded.bones) if b.parent_index >= 0}
        self._canvas.set_model(loaded.triangles, loaded.bone_markers, bone_parents, bone_names)
        self._frame_scale.config(to=0, state="disabled")
        self._play_button.config(state="disabled")
        self._frame_label.config(text="")
        self._mesh_info_label.config(
            text=(
                f"{len(loaded.triangles)} triangles, {len(loaded.bones)} bones, "
                f"{len(loaded.animations)} animation(s) - bind pose"
            )
        )
        _populate_bone_tree(self._bone_tree, loaded.bones)

        self._anim_list.delete(0, "end")
        for name, _raw in loaded.animations:
            self._anim_list.insert("end", name)
        self._anim_summary_label.config(text="")
        self._curve_tree.delete(*self._curve_tree.get_children())

    def select_animation(self, name: str) -> None:
        """Select (and pose) the loaded animation called ``name``."""
        if self._loaded is None:
            return
        for i, (anim_name, _raw) in enumerate(self._loaded.animations):
            if anim_name == name:
                self._anim_list.selection_clear(0, "end")
                self._anim_list.selection_set(i)
                self._anim_list.see(i)
                self._on_animation_selected()
                return

    def _on_bone_selected(self) -> None:
        selection = self._bone_tree.selection()
        if not selection or self._loaded is None:
            return
        text = self._bone_tree.item(selection[0], "text")
        try:
            bone_index = int(text.split(":", 1)[0])
        except ValueError:
            return
        self._canvas.highlight_bone(bone_index)

    def _on_animation_selected(self) -> None:
        selection = self._anim_list.curselection()
        if not selection or self._loaded is None:
            return
        _name, raw = self._loaded.animations[selection[0]]
        try:
            anim = animation.read_animation_bytes(raw)
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror("Could not decode animation", str(exc), parent=self)
            return

        bone_count = len(anim.groups)
        self._anim_summary_label.config(
            text=(
                f"{len(anim.curves)} curves, {bone_count} animated bones, "
                f"{anim.length_in_frames} frames, events: {len(anim.events)}"
            )
        )

        self._curve_tree.delete(*self._curve_tree.get_children())
        bone_names = {i: b.name for i, b in enumerate(self._loaded.bones)}
        for curve in anim.curves:
            bone_label = bone_names.get(curve.bone_index, str(curve.bone_index))
            peak = max((abs(curve.scaled_value(kf)) for kf in curve.keyframes), default=0.0)
            self._curve_tree.insert(
                "",
                "end",
                values=(
                    bone_label,
                    animation.channel_name(curve.channel),
                    curve.end_frame,
                    len(curve.keyframes),
                    f"{peak:.1f}",
                ),
            )

        self._stop_playback()
        self._current_animation = anim
        self._frame_scale.config(to=max(anim.length_in_frames, 1), state="normal")
        self._frame_scale.set(0)
        self._play_button.config(state="normal", text="Play")
        self._update_pose_display(0)

    # -- playback ---------------------------------------------------------
    def _update_pose_display(self, frame: float) -> None:
        if self._loaded is None or self._current_animation is None:
            return
        bones = self._loaded.bones
        world, palette = engine_pose.pose(bones, self._current_animation, frame)
        triangles = _skin_triangles(self._loaded.triangles, world, palette)
        # a bone's marker is its rotate pivot, carried by its world matrix
        positions = {
            i: engine_pose.apply(world[i], engine_pose.bone_values(b)[engine_pose.SLOT_ROTATE_PIVOT : engine_pose.SLOT_ROTATE_PIVOT + 3])
            for i, b in enumerate(bones)
        }
        self._canvas.set_pose(positions, triangles)
        self._frame_label.config(text=f"frame {frame:.0f}/{self._current_animation.length_in_frames}")

    def _on_frame_scrub(self, value_str: str) -> None:
        self._update_pose_display(float(value_str))

    def _toggle_play(self) -> None:
        if self._playing:
            self._stop_playback()
        else:
            self._playing = True
            self._play_button.config(text="Pause")
            self._advance_frame()

    def _advance_frame(self) -> None:
        if not self._playing or self._current_animation is None:
            return
        length = max(self._current_animation.length_in_frames, 1)
        next_frame = (self._frame_scale.get() + 1) % (length + 1)
        self._frame_scale.set(next_frame)
        self._update_pose_display(next_frame)
        self._play_after_id = self.after(33, self._advance_frame)

    def _stop_playback(self) -> None:
        self._playing = False
        if self._play_after_id is not None:
            self.after_cancel(self._play_after_id)
            self._play_after_id = None
        if hasattr(self, "_play_button"):
            self._play_button.config(text="Play")


class ModelPreviewDialog(tk.Toplevel):
    """Lightweight popup hosting one ``_ModelPreview`` for a single already-
    resolved ``_LoadedSet`` (or ``None``, to show ``empty_message``) - the
    "View Model..." cross-reference target for other editors. A real
    ``Toplevel``, matching this app's own precedent for a one-shot,
    single-purpose popup rather than a piece of the ongoing workspace (see
    ``new_project_dialog.py``)."""

    def __init__(self, parent: tk.Misc, title: str, loaded: _LoadedSet | None, empty_message: str = "No model data."):
        super().__init__(parent)
        self.title(title)
        self.geometry("900x600")
        self.transient(parent.winfo_toplevel())

        self._preview = _ModelPreview(self)
        self._preview.pack(fill="both", expand=True, padx=8, pady=(8, 0))
        ttk.Button(self, text="Close", command=self.destroy).pack(anchor="e", padx=8, pady=8)

        self._preview.show(loaded, empty_message)
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    def _on_close(self) -> None:
        self._preview.cleanup()
        self.destroy()


class ModelViewer(EditorPanel):
    display_name = "3D Models"

    def __init__(self, parent: tk.Misc, project: ModProject, changelog: ChangeLog):
        super().__init__(parent)
        self._project = project
        self._changelog = changelog
        self._dirty = False  # read-only viewer - never has unsaved changes
        self._all_sets: list[tuple[str, Path]] = []
        self._filtered_sets: list[tuple[str, Path]] = []

        self._build_widgets()
        self._load_set_list()

    # -- EditorPanel contract ------------------------------------------------
    def _confirm_discard(self) -> bool:
        return True

    def cleanup(self) -> None:
        self._preview.cleanup()

    def refresh_set_list(self) -> None:
        """Re-glob ymu/, zu/, zmap/, zbg/ and xwp/ (New slot... adds folders)."""
        self._load_set_list()

    def select_set(self, label: str) -> None:
        """Select a model set by its list label (``zu/reng``, ``ymu/lord``...)."""
        for i, (name, _path) in enumerate(self._filtered_sets):
            if name == label:
                self._set_list.selection_clear(0, "end")
                self._set_list.selection_set(i)
                self._set_list.see(i)
                self._on_set_selected()
                return

    # -- layout ---------------------------------------------------------------
    def _build_widgets(self) -> None:
        paned = ttk.PanedWindow(self, orient="horizontal")
        paned.pack(fill="both", expand=True)

        left = ttk.Frame(paned, padding=8)
        paned.add(left, weight=1)
        ttk.Label(left, text="Model sets").pack(anchor="w")

        search_var = tk.StringVar()
        ttk.Entry(left, textvariable=search_var).pack(fill="x", pady=(4, 4))
        search_var.trace_add("write", lambda *_: self._apply_filter(search_var.get()))

        self._empty_label = ttk.Label(left, text="", style="Muted.TLabel")
        self._empty_label.pack(anchor="w")

        list_frame = ttk.Frame(left)
        list_frame.pack(fill="both", expand=True)
        self._set_list = tk.Listbox(list_frame, exportselection=False)
        self._set_list.pack(fill="both", expand=True, side="left")
        scrollbar = ttk.Scrollbar(list_frame, command=self._set_list.yview)
        scrollbar.pack(fill="y", side="right")
        self._set_list.config(yscrollcommand=scrollbar.set)
        self._set_list.bind("<<ListboxSelect>>", lambda e: self._on_set_selected())

        buttons = ttk.Frame(left)
        buttons.pack(fill="x", pady=(6, 0))
        self._export_button = ttk.Button(buttons, text="Export .glb...", command=self._export_glb, state="disabled")
        self._import_button = ttk.Button(buttons, text="Import .glb...", command=self._import_glb, state="disabled")
        self._import_anim_button = ttk.Button(
            buttons, text="Import animation...", command=self._import_animation, state="disabled"
        )
        self._import_rig_button = ttk.Button(
            buttons, text="Replace rig...", command=self._import_rig, state="disabled"
        )
        self._kit_button = ttk.Button(buttons, text="Rig kit...", command=self._export_rig_kit, state="disabled")
        self._events_button = ttk.Button(buttons, text="Events...", command=self._edit_events, state="disabled")
        self._fit_button = ttk.Button(buttons, text="Fit new rig...", command=self._fit_rig, state="disabled")
        self._restore_button = ttk.Button(
            buttons, text="Restore original...", command=self._restore_originals, state="disabled"
        )
        self._new_slot_button = ttk.Button(buttons, text="New slot...", command=self._new_slot, state="disabled")
        self._tables_button = ttk.Button(buttons, text="Model tables...", command=self._model_tables)

        # wrapped in rows so the button bar never widens the list pane
        for i, button in enumerate((self._export_button, self._import_button, self._import_anim_button,
                                    self._import_rig_button, self._kit_button, self._events_button,
                                    self._fit_button, self._restore_button, self._new_slot_button,
                                    self._tables_button)):
            button.grid(row=i // 3, column=i % 3, sticky="ew", padx=(0, 4), pady=(0, 4))
        for column in range(3):
            buttons.grid_columnconfigure(column, weight=1, uniform="buttons")

        self._preview = _ModelPreview(paned)
        paned.add(self._preview, weight=5)

    # -- data loading ---------------------------------------------------------
    def _load_set_list(self) -> None:
        self._all_sets = _iter_model_sets(self._project)
        self._apply_filter("")
        self._empty_label.config(
            text="" if self._all_sets else "No .g/.gs/.ga model data found.\nExtract the project first."
        )

    def _apply_filter(self, query: str) -> None:
        query = query.strip().lower()
        self._filtered_sets = [s for s in self._all_sets if query in s[0].lower()]
        self._set_list.delete(0, "end")
        for label, _path in self._filtered_sets:
            self._set_list.insert("end", label)

    def _on_set_selected(self) -> None:
        selection = self._set_list.curselection()
        if not selection:
            return
        label, path = self._filtered_sets[selection[0]]
        self._export_button.config(state="normal")
        # Scenery takes a static mesh, map and battle models a skinned body.
        self._import_button.config(
            state="normal" if label.startswith(("zbg/", "ymu/", "zu/", "zmap/", "xwp/")) else "disabled")
        self._import_anim_button.config(state="normal" if label.startswith(("ymu/", "zu/")) else "disabled")
        self._import_rig_button.config(state="normal" if label.startswith(("ymu/", "zu/")) else "disabled")
        self._kit_button.config(state="normal" if label.startswith(("ymu/", "zu/")) else "disabled")
        self._events_button.config(state="normal" if label.startswith(("ymu/", "zu/")) else "disabled")
        self._fit_button.config(state="normal" if label.startswith(("ymu/", "zu/")) else "disabled")
        self._restore_button.config(state="normal" if self._project.originals_in(path.parent) else "disabled")
        self._new_slot_button.config(state="normal" if label.startswith(("ymu/", "zu/")) else "disabled")
        try:
            loaded = _load_model_set(label, path)
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror("Could not read model", str(exc), parent=self)
            return
        self._preview.show(loaded)

    def _selected_set(self) -> tuple[str, Path] | None:
        selection = self._set_list.curselection()
        return self._filtered_sets[selection[0]] if selection else None

    def _export_glb(self) -> None:
        selected = self._selected_set()
        if selected is None:
            return
        label, path = selected
        target = filedialog.asksaveasfilename(
            title="Export model as glTF",
            defaultextension=".glb",
            initialfile=label.replace("/", "_") + ".glb",
            filetypes=[("glTF binary", "*.glb")],
            parent=self,
        )
        if not target:
            return
        try:
            data = export_map_terrain_glb(path) if is_map_container(path) else export_set_glb(path)
            Path(target).write_bytes(data)
            written = [target]
            if is_map_container(path):
                _entries, files = _read_container(path)
                terrain = map_terrain_name(files, map_file.read_map_bytes(files["map.bin"]), path.parent.name)
                mask = terrain_mask_image(files, terrain)
                if mask is not None:
                    mask_path = Path(target).with_name(Path(target).stem + "_mask.png")
                    mask.convert("L").save(mask_path)
                    written.append(str(mask_path))
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror("Could not export model", str(exc), parent=self)
            return
        note = ""
        if len(written) > 1:
            note = (
                "\n\nThe mask covers 640 x 640 units (128 tiles) from the terrain's corner, x to the right and z "
                "downwards: black shows the atlas through the first UV set, white through the second (roads, shores)."
            )
        messagebox.showinfo("Exported", "Wrote " + "\n".join(written) + note, parent=self)

    def _import_rig(self) -> None:
        selected = self._selected_set()
        if selected is None:
            return
        label, path = selected
        chosen = filedialog.askopenfilename(
            title=f"Replace the {label} skeleton, body and every animation with a glTF rig",
            filetypes=[("glTF", "*.glb *.gltf"), ("All files", "*.*")],
            parent=self,
        )
        if not chosen:
            return
        try:
            source = self._map_model_source(label, path, Path(chosen))
            if source is None:
                return
            source, notes = source
            replace = replace_battle_rig_with_glb if label.startswith("zu/") else replace_rig_with_glb
            result = self._busy(lambda: replace(path, source))
            result.warnings[:0] = notes
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror("Could not import rig", str(exc), parent=self)
            return
        self._review_and_write(
            label,
            path,
            result,
            f"Replace the rig of {label}",
            f"Replaced skeleton, body and animations with {Path(chosen).name} ({len(result.outputs)} files)",
        )

    def _export_rig_kit(self) -> None:
        selected = self._selected_set()
        if selected is None:
            return
        label, path = selected
        target = filedialog.asksaveasfilename(
            title="Export the rig kit (reference .glb, checklist .md, animation list .json)",
            defaultextension=".glb",
            initialfile=label.replace("/", "_") + "_rig_kit.glb",
            filetypes=[("glTF binary", "*.glb")],
            parent=self,
        )
        if not target:
            return
        try:
            written = self._busy(lambda: export_rig_kit(path, Path(target)))
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror("Could not export the rig kit", str(exc), parent=self)
            return
        messagebox.showinfo(
            "Rig kit exported",
            "Wrote " + "\n".join(str(p) for p in written) + "\n\nThe .md lists the anchor bones, map weapons and "
            "every animation with its frames and events; a replacement rig imported with Replace rig... must "
            "provide them.",
            parent=self,
        )

    def _ask_map_reduction(self, label: str, path: Path, triangles: int) -> int | None:
        """A triangle budget for a map model larger than the vanilla ones
        (``0``: keep the mesh; ``None``: cancel)."""
        if triangles <= gs_stats.MAP_BODY_LIMITS["triangles"]:
            return 0
        dialog = _MapReduceDialog(self, label, triangles, map_triangle_budget(path))
        self.wait_window(dialog)
        return dialog.result

    def _map_model_source(self, label: str, path: Path, chosen: Path) -> tuple[Path, list[str]] | None:
        """The glTF a map-model import reads: ``chosen``, or a reduced copy
        when the model is larger than the vanilla ones and the user asks for
        one (with the note for the review). ``None``: cancelled."""
        if not label.startswith("ymu/"):
            return chosen, []
        triangles = mesh_reduce.glb_triangle_count(chosen.read_bytes(), chosen.parent)
        target = self._ask_map_reduction(label, path, triangles)
        if target is None:
            return None
        if not target:
            return chosen, []
        reduced, result = self._busy(lambda: reduce_map_glb(path, chosen, target))
        return reduced, reduction_note(result, reduced)

    def _fit_rig(self) -> None:
        selected = self._selected_set()
        if selected is None:
            return
        label, path = selected
        chosen = filedialog.askopenfilename(
            title=f"Fit a rigged humanoid model onto {label} (its own skeleton, the set's animations)",
            filetypes=[("glTF", "*.glb *.gltf"), ("All files", "*.*")],
            parent=self,
        )
        if not chosen:
            return
        try:
            setup = self._busy(lambda: prepare_rig_fit(path, Path(chosen)))
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror("Could not read the rigs", str(exc), parent=self)
            return
        dialog = _RigMappingDialog(self, label, setup)
        self.wait_window(dialog)
        if dialog.result is None:
            return
        max_triangles = None
        if not setup.battle:
            max_triangles = self._ask_map_reduction(label, path, len(setup.model.idx) // 3)
            if max_triangles is None:
                return
            max_triangles = max_triangles or None
        fitted = Path(chosen).with_name(f"{Path(chosen).stem}_on_{label.replace('/', '_')}.glb")
        try:
            result = self._busy(lambda: fit_new_rig(path, setup, dialog.result, fitted, max_triangles))
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror("Could not fit the rig", str(exc), parent=self)
            return
        self._review_and_write(
            label,
            path,
            result,
            f"Fit {Path(chosen).name} onto {label}",
            f"New rig from {Path(chosen).name}: its skeleton, every animation retargeted ({len(result.outputs)} files)",
        )

    def _edit_events(self) -> None:
        selected = self._selected_set()
        if selected is None:
            return
        label, path = selected
        try:
            names = sorted(set(set_animation_names(path)))
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror("Could not read the set", str(exc), parent=self)
            return
        dialog = _EventEditorDialog(self, label, path, names)
        self.wait_window(dialog)
        if dialog.result is None:
            return
        target, events = dialog.result
        try:
            result = replace_animation_events(path, target, events)
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror("Could not write the events", str(exc), parent=self)
            return
        self._review_and_write(
            label, path, result, f"Events of {target}", f"Edited the events of {target}", animation_name=target
        )

    def _import_animation(self) -> None:
        selected = self._selected_set()
        if selected is None:
            return
        label, path = selected
        chosen = filedialog.askopenfilename(
            title=f"Import an animation for {label}",
            filetypes=[("glTF", "*.glb *.gltf"), ("All files", "*.*")],
            parent=self,
        )
        if not chosen:
            return
        try:
            gltf_names = gltf_import.list_animations(Path(chosen).read_bytes(), Path(chosen).parent)
            targets = set_animation_names(path)
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror("Could not read glTF", str(exc), parent=self)
            return
        if not gltf_names:
            messagebox.showerror("No animations", "The glTF file has no animations.", parent=self)
            return
        dialog = _AnimationImportDialog(self, gltf_names, targets)
        self.wait_window(dialog)
        if dialog.result is None:
            return
        source, target = dialog.result
        try:
            result = self._busy(lambda: replace_animation_with_glb(path, Path(chosen), source, target))
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror("Could not import animation", str(exc), parent=self)
            return
        self._review_and_write(
            label,
            path,
            result,
            f"Replace {target} with {source}",
            f"Replaced animation {target} with {source} from {Path(chosen).name}",
            animation_name=target,
        )

    def _import_glb(self) -> None:
        selected = self._selected_set()
        if selected is None:
            return
        label, path = selected
        skinned = label.startswith(("ymu/", "zu/"))
        if label.startswith("xwp/"):
            try:
                bow = is_skinned_weapon(path)
            except Exception as exc:  # noqa: BLE001
                messagebox.showerror("Could not read model", str(exc), parent=self)
                return
            if bow:
                messagebox.showerror(
                    "Can't import this weapon",
                    f"{label} is a bow: the game bends it through a skinned (composite) mesh, which the importer "
                    "doesn't write. Swords, lances, axes and knives can be replaced.", parent=self)
                return
        chosen = filedialog.askopenfilename(
            title=f"Replace the {label} terrain with a glTF model" if is_map_container(path) else f"Replace the {label} mesh with a glTF model",
            filetypes=[("glTF", "*.glb *.gltf"), ("All files", "*.*")],
            parent=self,
        )
        if not chosen:
            return
        try:
            if is_map_container(path):
                has_map_base = any(
                    m.name in gltf_import.UV2_MATERIALS
                    for m in gltf_import.read_gltf(Path(chosen).read_bytes(), Path(chosen).parent).materials
                )
                options = _TerrainImportOptions(self, has_map_base)
                self.wait_window(options)
                if options.result is None:
                    return
                follow, conform, texturing, mask, keep_light = options.result
                result = self._busy(
                    lambda: replace_map_terrain_with_glb(path, Path(chosen), follow, conform, texturing, mask, keep_light)
                )
            elif label.startswith("zu/"):
                result = self._busy(lambda: replace_battle_body_with_glb(path, Path(chosen)))
            elif skinned:
                source = self._map_model_source(label, path, Path(chosen))
                if source is None:
                    return
                source, notes = source
                result = self._busy(lambda: replace_body_with_glb(path, source))
                result.warnings[:0] = notes
            else:
                result = self._busy(lambda: replace_set_with_static_glb(path, Path(chosen)))
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror("Could not import model", str(exc), parent=self)
            return
        kind = "terrain import" if is_map_container(path) else "skinned body import" if skinned else "static import"
        names = ", ".join(p.name for p in result.outputs)
        self._review_and_write(
            label,
            path,
            result,
            f"Replace the {label} mesh",
            f"Replaced mesh with {Path(chosen).name} ({kind}; wrote {names})",
        )

    def _busy(self, work):
        """Run ``work()`` with a wait cursor (imports take a few seconds)."""
        top = self.winfo_toplevel()
        top.config(cursor="watch")
        top.update_idletasks()
        try:
            return work()
        finally:
            top.config(cursor="")

    def _review_and_write(
        self,
        label: str,
        path: Path,
        result: ModelImport,
        title: str,
        description: str,
        animation_name: str | None = None,
    ) -> None:
        """Show the import review; on Write, write every output (keeping
        the files as extracted in the project's originals folder), log the
        change and reload the set."""
        dialog = _ImportReviewDialog(self, title, label, path, result, animation_name=animation_name)
        self.wait_window(dialog)
        if not dialog.result:
            return
        try:
            for out_path, data in result.outputs.items():
                self._project.write_keeping_original(out_path, data)
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror("Could not save", str(exc), parent=self)
            return
        self._changelog.append(label, description)
        self._on_set_selected()

    def _new_slot(self) -> None:
        selected = self._selected_set()
        if selected is None:
            return
        label, _path = selected
        try:
            dialog = _NewSlotDialog(self, self._project, label)
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror("Could not read the game data", str(exc), parent=self)
            return
        self.wait_window(dialog)
        if dialog.result is None:
            return
        self._changelog.append(label, dialog.result)
        self._load_set_list()

    def _model_tables(self) -> None:
        def changed(label: str, text: str) -> None:
            self._changelog.append(label, text)
            self._load_set_list()

        try:
            _ModelTablesDialog(self, self._project, changed)
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror("Could not read the game data", str(exc), parent=self)

    def _restore_originals(self) -> None:
        selected = self._selected_set()
        if selected is None:
            return
        label, path = selected
        originals = self._project.originals_in(path.parent)
        if not originals:
            return
        names = ", ".join(p.name for p in originals)
        if not messagebox.askyesno(
            "Restore original files?",
            f"Put back the files of {label} as they were extracted ({names})? Every import into them is undone.",
            parent=self,
        ):
            return
        try:
            for original in originals:
                self._project.restore_original(original)
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror("Could not restore", str(exc), parent=self)
            return
        self._changelog.append(label, f"Restored the extracted files ({names})")
        self._on_set_selected()
