"""The app side of terrain painting (:mod:`terrain_paint`).

- :func:`read_terrain` gives a map's ``map_base`` triangles, UVs, atlas,
  mask and light overlay;
- the atlas swatch table of a map is detected from its UVs or saved per
  project (``terrain_paint/<map>.json``, with an optional custom atlas
  ``<map>_atlas.png`` from the atlas builder);
- :class:`PaintData` is what a terrain kit carries between the app and
  Blender (layers as ``.npy`` weight images, so Blender needs no PIL);
- :func:`apply_paint` compiles painted layers onto an imported scene's
  ``map_base`` triangles for :func:`model_viewer.replace_map_terrain_with_glb`;
- :func:`read_water` / :func:`write_water_dir` carry the map's water
  surfaces, shoreline fade and shore props (:mod:`water_kit`) into the kit.
"""

from __future__ import annotations

import io
import colorsys
import json
import math
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import numpy as np
from PIL import Image

from . import terrain_paint as tp
from .formats import gltf_import, gs_file, map_file, tpl
from .formats import model as model_fmt

PAINT_FOLDER = "terrain_paint"
TILESETS_FOLDER = "tilesets"
#: Paint layers cover the mask's 640 units at 1.6 pixels per unit, twice the mask's detail.
PAINT_RESOLUTION = 1024
#: Units between the sculpt grid's vertices.
SCULPT_SPACING = 2.0
MANIFEST = "kit.json"


@dataclass
class TerrainSource:
    terrain: str
    positions: np.ndarray  # (n, 3, 3) map_base triangles
    uv0: np.ndarray
    uv1: np.ndarray
    atlas: Image.Image
    mask: np.ndarray  # uint8, square
    light: Optional[Image.Image]
    light_matrix: Optional[tuple]
    playable: Optional[tuple[float, float, float, float]]
    triangles: int  # every terrain triangle, all materials


def read_terrain(container: Path) -> TerrainSource:
    """The land terrain of a ``zmap/<map>/map.cmp``: its ``map_base``
    triangles (strip order, hidden chunks skipped) and projected textures."""
    from .formats.gltf_export import _strip_triangles
    from .gui import map_scene
    from .gui import model_viewer as mv
    from . import map_props

    _entries, files = mv._read_container(container)
    map_data = map_file.read_map_bytes(files["map.bin"])
    name = mv.map_terrain_name(files, map_data, container.parent.name)
    gs = model_fmt.read_model_bytes(files[f"{name}.gs"])
    base = next((i for i, m in enumerate(gs.materials) if m.name == "map_base" and len(m.textures) >= 2), None)
    if base is None:
        raise gltf_import.GltfImportError(f"{name} has no map_base material with an atlas and a mask to paint.")
    material = gs.materials[base]
    tris = [t for c in gs.chunks if c.material_index == base and not c.hidden
            for s in c.strips for t in _strip_triangles(s)]
    every = sum(1 for c in gs.chunks if not c.hidden for s in c.strips for _t in _strip_triangles(s))
    positions = np.array([[v.position for v in t] for t in tris], float).reshape(-1, 3, 3)
    uv0 = np.array([[v.uv for v in t] for t in tris], float).reshape(-1, 3, 2)
    uv1 = np.array([[v.uv2 if v.uv2 is not None else v.uv for v in t] for t in tris], float).reshape(-1, 3, 2)
    images = tpl.read_tpl_images(io.BytesIO(files[map_props.texpack_name(files)]))
    atlas_id = material.textures[0].tex_id
    light_id = material.textures[-1].tex_id
    projection = map_scene.compute_map_texture_projection(name, map_data)
    return TerrainSource(
        name, positions, uv0, uv1,
        images[atlas_id].convert("RGBA"),
        np.asarray(images[atlas_id + 1].convert("L")),
        images[light_id].convert("L") if light_id < len(images) and len(material.textures) >= 3 else None,
        projection.last_matrix if projection is not None else None,
        mv.map_playable_area(map_data, name),
        every,
    )


def read_terrain_atlas(container: Path) -> Image.Image:
    """Read only a map's ground atlas, without decoding its terrain geometry.

    This is the inexpensive path used to preview and deduplicate the map
    tileset picker.  ``read_terrain`` remains the full authoring-data read.
    """
    from .gui import model_viewer as mv
    from . import map_props

    _entries, files = mv._read_container(container)
    map_data = map_file.read_map_bytes(files["map.bin"])
    name = mv.map_terrain_name(files, map_data, container.parent.name)
    gs = model_fmt.read_model_bytes(files[f"{name}.gs"])
    material = next((m for m in gs.materials if m.name == "map_base" and len(m.textures) >= 2), None)
    if material is None:
        raise gltf_import.GltfImportError(f"{name} has no map_base material with a terrain atlas.")
    texpack = files[map_props.texpack_name(files)]
    return tpl.read_mip_levels(texpack, material.textures[0].tex_id)[0].convert("RGBA")


# ---------------------------------------------------------------- swatch tables


def layout_path(project_dir: Path, map_folder: str) -> Path:
    return Path(project_dir) / PAINT_FOLDER / f"{map_folder}.json"


def custom_atlas_path(project_dir: Path, map_folder: str) -> Path:
    return Path(project_dir) / PAINT_FOLDER / f"{map_folder}_atlas.png"


@dataclass
class ProjectTileset:
    """A reusable terrain atlas owned by the project rather than one map."""

    key: str
    name: str
    source_map: str
    layout: tp.AtlasLayout
    atlas: Image.Image


def _tileset_key(name: str) -> str:
    key = re.sub(r"[^A-Za-z0-9_-]+", "_", name.strip()).strip("_").lower()
    if not key:
        raise ValueError("Give the tileset a name containing a letter or number.")
    return key[:64]


def tilesets_path(project_dir: Path) -> Path:
    return Path(project_dir) / PAINT_FOLDER / TILESETS_FOLDER


def save_project_tileset(project_dir: Path, name: str, source_map: str, layout: tp.AtlasLayout,
                         atlas: Image.Image, *, key: str | None = None) -> ProjectTileset:
    """Save a named, reusable atlas and its swatches in ``terrain_paint/tilesets``."""
    layout.validate()
    if atlas.size != (layout.width, layout.height):
        raise ValueError(f"The atlas is {atlas.width}x{atlas.height}, but its swatches describe "
                         f"{layout.width}x{layout.height}.")
    key = key or _tileset_key(name)
    folder = tilesets_path(project_dir)
    folder.mkdir(parents=True, exist_ok=True)
    record = {
        "name": name.strip(), "source_map": source_map,
        "layout": json.loads(layout.to_json()),
    }
    (folder / f"{key}.json").write_text(json.dumps(record, indent=1) + "\n", encoding="utf-8")
    atlas.convert("RGBA").save(folder / f"{key}.png")
    return ProjectTileset(key, record["name"], source_map, layout, atlas.convert("RGBA"))


def load_project_tileset(project_dir: Path, key: str) -> ProjectTileset:
    folder = tilesets_path(project_dir)
    record = json.loads((folder / f"{key}.json").read_text(encoding="utf-8"))
    layout = tp.AtlasLayout.from_json(json.dumps(record["layout"]))
    atlas = Image.open(folder / f"{key}.png").convert("RGBA")
    if atlas.size != (layout.width, layout.height):
        raise ValueError(f"Tileset {record.get('name', key)} has an atlas and swatch table of different sizes.")
    return ProjectTileset(key, str(record.get("name") or key), str(record.get("source_map") or ""), layout, atlas)


def project_tilesets(project_dir: Path) -> list[ProjectTileset]:
    """Load every valid reusable tileset, sorted by its display name."""
    folder = tilesets_path(project_dir)
    if not folder.is_dir():
        return []
    result = []
    for path in folder.glob("*.json"):
        try:
            result.append(load_project_tileset(project_dir, path.stem))
        except (OSError, ValueError, KeyError, json.JSONDecodeError):
            continue
    return sorted(result, key=lambda item: item.name.casefold())


def detect_layout(source: TerrainSource) -> tp.AtlasLayout:
    width, height = source.atlas.size
    layout = tp.layout_from_uvs(source.positions, source.uv0, source.uv1, width, height)
    _split_mixed_swatches(layout, source.atlas)
    add_unused_cells(layout, atlas=source.atlas)
    _name_generic_swatches(layout, source.atlas)
    return layout


def load_layout(source: TerrainSource, project_dir: Optional[Path], map_folder: str
                ) -> tuple[tp.AtlasLayout, Image.Image, bool]:
    """The saved swatch table and atlas of a map, else detected ones.
    Returns ``(layout, atlas, custom)``; ``custom`` when the atlas builder
    replaced the game's atlas."""
    if project_dir is not None:
        saved = layout_path(project_dir, map_folder)
        if saved.is_file():
            layout = tp.AtlasLayout.from_json(saved.read_text(encoding="utf-8"))
            custom = custom_atlas_path(project_dir, map_folder)
            if custom.is_file():
                atlas = Image.open(custom).convert("RGBA")
                add_unused_cells(layout, atlas=atlas)
                _name_generic_swatches(layout, atlas)
                return layout, atlas, True
            if (layout.width, layout.height) == source.atlas.size:
                add_unused_cells(layout, atlas=source.atlas)
                _name_generic_swatches(layout, source.atlas)
                return layout, source.atlas, False
    return detect_layout(source), source.atlas, False


def save_layout(project_dir: Path, map_folder: str, layout: tp.AtlasLayout,
                custom_atlas: Optional[Image.Image] = None, clear_custom: bool = False) -> Path:
    layout.validate()
    path = layout_path(project_dir, map_folder)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as stream:
        stream.write(layout.to_json() + "\n")
    custom = custom_atlas_path(project_dir, map_folder)
    if custom_atlas is not None:
        custom_atlas.convert("RGBA").save(custom)
    elif clear_custom and custom.is_file():
        custom.unlink()
    return path


def _swatch_content_name(atlas: Image.Image, x: int, y: int, width: int, height: int) -> str:
    """A short, deliberately visual name based on the rectangle's pixels.

    Colour alone cannot distinguish grass from green carpet, or dirt from
    brown floorboards.  Use neutral colour/texture descriptions except for
    strong structural cues, which makes indoor atlases substantially less
    misleading than the old hue-only names.
    """
    crop = np.asarray(atlas.convert("RGBA").crop((x, y, x + width, y + height)).resize((24, 24)), np.float32)
    visible = crop[..., 3] > 16
    if not visible.any():
        kind = "Transparent"
    else:
        rgb = crop[..., :3][visible] / 255.0
        red, green, blue = rgb.mean(axis=0)
        hue, saturation, value = colorsys.rgb_to_hsv(float(red), float(green), float(blue))
        pixels = crop[..., :3] / 255.0
        luminance = pixels[..., 0] * 0.299 + pixels[..., 1] * 0.587 + pixels[..., 2] * 0.114
        variation = float(luminance[visible].std())
        horizontal = float(np.abs(np.diff(luminance, axis=1)).mean())
        vertical = float(np.abs(np.diff(luminance, axis=0)).mean())
        degrees = hue * 360.0
        if saturation < 0.10:
            colour = "White" if value > 0.86 else "Light grey" if value > 0.66 else \
                "Grey" if value > 0.38 else "Charcoal" if value > 0.16 else "Black"
        elif degrees < 15 or degrees >= 345:
            colour = "Red"
        elif degrees < 42:
            colour = "Brown" if value < 0.62 else "Orange"
        elif degrees < 68:
            colour = "Tan" if saturation < 0.48 else "Gold"
        elif degrees < 105:
            colour = "Olive"
        elif degrees < 165:
            colour = "Green"
        elif degrees < 195:
            colour = "Teal"
        elif degrees < 255:
            colour = "Blue"
        elif degrees < 300:
            colour = "Purple"
        else:
            colour = "Magenta"

        directional = max(horizontal, vertical) > 1.65 * max(min(horizontal, vertical), 0.008)
        if variation < 0.035:
            kind = f"Smooth {colour.lower()}"
        elif directional and colour in {"Brown", "Tan", "Orange"}:
            kind = f"{colour} wood grain"
        elif directional:
            kind = f"Striped {colour.lower()}"
        elif max(horizontal, vertical) > 0.115 and colour in {"Grey", "Light grey", "Charcoal", "White"}:
            kind = f"{colour} stone pattern"
        elif max(horizontal, vertical) > 0.115:
            kind = f"Patterned {colour.lower()}"
        elif variation > 0.15:
            kind = f"Mottled {colour.lower()}"
        else:
            kind = f"Textured {colour.lower()}"
    return f"{kind} {x // max(width, 1) + 1},{y // max(height, 1) + 1}"


_OLD_AUTO_NAME = re.compile(
    r"^(?:Transparent|Snow|Dark stone|Stone|Grey|Red earth|Earth|Sand|Dry grass|Yellow|Grass|Teal|Water|Purple) "
    r"\d+,\d+$"
)


def _name_generic_swatches(layout: tp.AtlasLayout, atlas: Image.Image) -> None:
    """Replace detector/cell placeholder names with pixel-informed names."""
    for swatch in layout.swatches:
        if swatch.name.startswith(("Swatch ", "Cell ")) or _OLD_AUTO_NAME.fullmatch(swatch.name):
            swatch.name = _swatch_content_name(atlas, swatch.x, swatch.y, swatch.w, swatch.h)


def _split_mixed_swatches(layout: tp.AtlasLayout, atlas: Image.Image, quantum: int = 64) -> None:
    """Split a UV bounding box when the atlas has clear material seams inside it.

    A connected terrain UV chart may span several separately useful atlas
    textures.  Its bounding box is therefore evidence of coverage, not proof
    that the whole rectangle is one paint swatch.  Strong full-edge changes
    in colour distribution or texture energy split non-base rectangles;
    continuous textures (including the large base) remain intact.
    """
    pixels = np.asarray(atlas.convert("RGBA"), np.float32) / 255.0
    pixels[..., :3] *= pixels[..., 3:4]

    def histogram(region: np.ndarray) -> np.ndarray:
        parts = []
        for channel in range(4):
            values, _edges = np.histogram(region[..., channel], bins=8, range=(0.0, 1.0))
            parts.append(values.astype(np.float32) / max(values.sum(), 1))
        return np.concatenate(parts)

    def gradient_histogram(region: np.ndarray) -> np.ndarray:
        luminance = region[..., 0] * 0.299 + region[..., 1] * 0.587 + region[..., 2] * 0.114
        gradients = np.concatenate((np.abs(np.diff(luminance, axis=1)).ravel(),
                                    np.abs(np.diff(luminance, axis=0)).ravel()))
        values, _edges = np.histogram(
            gradients, bins=(0.0, 0.015, 0.035, 0.07, 0.14, 0.28, 0.5, 0.75, 1.01)
        )
        return values.astype(np.float32) / max(values.sum(), 1)

    def cut_score(x: int, y: int, width: int, height: int, cut: int, vertical: bool) -> float | None:
        band = min(32, cut, (width if vertical else height) - cut)
        if vertical:
            first = pixels[y:y + height, x + cut - band:x + cut]
            second = pixels[y:y + height, x + cut:x + cut + band]
            seam = float(np.abs(first[:, -1] - second[:, 0]).mean())
            internal = float(np.concatenate((np.abs(np.diff(first, axis=1)).ravel(),
                                             np.abs(np.diff(second, axis=1)).ravel())).mean())
        else:
            first = pixels[y + cut - band:y + cut, x:x + width]
            second = pixels[y + cut:y + cut + band, x:x + width]
            seam = float(np.abs(first[-1] - second[0]).mean())
            internal = float(np.concatenate((np.abs(np.diff(first, axis=0)).ravel(),
                                             np.abs(np.diff(second, axis=0)).ravel())).mean())
        overlap = float(np.minimum(histogram(first), histogram(second)).sum() / 4.0)
        gradient_overlap = float(np.minimum(gradient_histogram(first), gradient_histogram(second)).sum())
        mean_delta = float(np.abs(first.mean(axis=(0, 1)) - second.mean(axis=(0, 1))).mean())
        deviation_delta = float(np.abs(first.std(axis=(0, 1)) - second.std(axis=(0, 1))).mean())
        # Demand more than an ordinary feature inside a noisy texture.  A
        # distribution change catches boundaries whose edge pixels happen to
        # match; the seam ratio catches sharp borders with similar averages.
        distribution_break = (
            overlap < 0.46
            or (overlap < 0.68 and mean_delta > 0.065)
            or gradient_overlap < 0.76
            or (deviation_delta > 0.045 and (overlap < 0.85 or mean_delta > 0.05))
        )
        edge_break = seam > max(0.095, internal * 2.15 + 0.012)
        if not distribution_break and not edge_break:
            return None
        return ((1.0 - overlap) + (1.0 - gradient_overlap) * 0.8 + mean_delta * 2.0
                + deviation_delta + max(0.0, seam - internal * 1.4))

    def split(swatch: tp.Swatch) -> list[tp.Swatch]:
        candidates: list[tuple[float, bool, int]] = []
        for cut in range(quantum, swatch.w - quantum + 1, quantum):
            score = cut_score(swatch.x, swatch.y, swatch.w, swatch.h, cut, True)
            if score is not None:
                candidates.append((score, True, cut))
        for cut in range(quantum, swatch.h - quantum + 1, quantum):
            score = cut_score(swatch.x, swatch.y, swatch.w, swatch.h, cut, False)
            if score is not None:
                candidates.append((score, False, cut))
        if not candidates:
            return [swatch]
        _score, vertical, cut = max(candidates)
        if vertical:
            parts = (tp.Swatch("Swatch 0", swatch.x, swatch.y, cut, swatch.h),
                     tp.Swatch("Swatch 0", swatch.x + cut, swatch.y, swatch.w - cut, swatch.h))
        else:
            parts = (tp.Swatch("Swatch 0", swatch.x, swatch.y, swatch.w, cut),
                     tp.Swatch("Swatch 0", swatch.x, swatch.y + cut, swatch.w, swatch.h - cut))
        return split(parts[0]) + split(parts[1])

    rebuilt: list[tp.Swatch] = []
    new_base = 0
    for index, swatch in enumerate(layout.swatches):
        if index == layout.base:
            new_base = len(rebuilt)
            rebuilt.append(swatch)
        else:
            rebuilt.extend(split(swatch))
    layout.swatches = rebuilt
    layout.base = new_base


def _unused_cell_size(layout: tp.AtlasLayout) -> tuple[int, int]:
    """Infer the atlas grid from real, non-base UV swatches.

    Indoor maps frequently use rectangular 32/64/128-texel regions.  The
    greatest common divisor preserves those boundaries, while the 128 cap
    retains the conventional outdoor fallback when only the large base is
    available.
    """
    details = [s for i, s in enumerate(layout.swatches) if i != layout.base]
    if not details:
        return min(128, layout.width), min(128, layout.height)

    def step(values: list[int], extent: int) -> int:
        result = 0
        for value in values:
            if value > 0:
                result = math.gcd(result, value)
        return min(128, max(16, result or min(128, extent)))

    return (
        step([layout.width] + [value for s in details for value in (s.x, s.w)], layout.width),
        step([layout.height] + [value for s in details for value in (s.y, s.h)], layout.height),
    )


def _fitting_unused_rectangles(layout: tp.AtlasLayout, cell_w: int, cell_h: int,
                               atlas: Image.Image) -> list[tuple[int, int, int, int]]:
    """Group uncovered grid cells whose pixels continue across their edge.

    The small inferred grid is only a measurement lattice.  Rectangles grow
    only while *every* newly enclosed internal seam is visually continuous.
    This deliberately avoids transitive connected-component grouping, where
    one small bridge could join several different terrains into one swatch.
    UV-detected swatches are marked occupied before this begins.
    """
    columns = layout.width // cell_w
    rows = layout.height // cell_h
    available = np.ones((rows, columns), bool)
    for row in range(rows):
        y = row * cell_h
        for column in range(columns):
            x = column * cell_w
            if any(x < s.x + s.w and s.x < x + cell_w and y < s.y + s.h and s.y < y + cell_h
                   for s in layout.swatches):
                available[row, column] = False

    # A dense 32-texel grid is the characteristic indoor-atlas case.  Its
    # unused area contains arranged wall/floor kits whose corner, border and
    # centre cells intentionally have different colour distributions.  The
    # ordinary terrain rule below must compare cell contents to avoid joining
    # unrelated outdoor materials; doing that here, however, reduces every
    # indoor kit back to its minimum cells.  For indoor atlases we instead
    # treat the grid as a packing lattice and decide from the shared boundary.
    # Requiring a sizeable uncovered area keeps this special case away from
    # small custom atlases which merely happen to use 32-pixel tiles.
    structural_indoor = cell_w <= 32 and cell_h <= 32 and int(available.sum()) >= 48

    pixels = np.asarray(atlas.convert("RGBA"), np.float32) / 255.0
    # Premultiplication makes fully transparent padding compare by alpha
    # instead of by arbitrary hidden RGB values.
    pixels[..., :3] *= pixels[..., 3:4]

    def descriptor(row: int, column: int) -> tuple:
        x, y = column * cell_w, row * cell_h
        cell = pixels[y:y + cell_h, x:x + cell_w]
        colour_hist = []
        for channel in range(4):
            hist, _edges = np.histogram(cell[..., channel], bins=8, range=(0.0, 1.0))
            colour_hist.append(hist.astype(np.float32) / max(hist.sum(), 1))
        luminance = cell[..., 0] * 0.299 + cell[..., 1] * 0.587 + cell[..., 2] * 0.114
        gx = np.abs(np.diff(luminance, axis=1)).ravel()
        gy = np.abs(np.diff(luminance, axis=0)).ravel()
        gradients = np.concatenate((gx, gy))
        gradient_hist, _edges = np.histogram(
            gradients, bins=(0.0, 0.015, 0.035, 0.07, 0.14, 0.28, 0.5, 0.75, 1.01)
        )
        gradient_hist = gradient_hist.astype(np.float32) / max(gradient_hist.sum(), 1)
        return (np.concatenate(colour_hist), gradient_hist,
                cell.mean(axis=(0, 1)), cell.std(axis=(0, 1)),
                float(gradients.mean()), float((gradients > 0.035).mean()))

    descriptors = [[descriptor(row, column) for column in range(columns)] for row in range(rows)]

    def content_compatible(row: int, column: int, other_row: int, other_column: int) -> bool:
        colours_a, gradients_a, mean_a, deviation_a, energy_a, edges_a = descriptors[row][column]
        colours_b, gradients_b, mean_b, deviation_b, energy_b, edges_b = descriptors[other_row][other_column]
        # Each colour channel's histogram sums to one, hence division by 4.
        colour_overlap = float(np.minimum(colours_a, colours_b).sum() / 4.0)
        gradient_overlap = float(np.minimum(gradients_a, gradients_b).sum())
        mean_delta = float(np.abs(mean_a - mean_b).mean())
        deviation_delta = float(np.abs(deviation_a - deviation_b).mean())
        texture_scale_compatible = not (abs(energy_a - energy_b) > 0.009
                                        and abs(edges_a - edges_b) > 0.09)
        return (colour_overlap >= 0.58 and gradient_overlap >= 0.56
                and mean_delta <= 0.085 and deviation_delta <= 0.075
                and texture_scale_compatible)
    def fits(row: int, column: int, other_row: int, other_column: int) -> bool:
        x, y = column * cell_w, row * cell_h
        ox, oy = other_column * cell_w, other_row * cell_h
        first = pixels[y:y + cell_h, x:x + cell_w]
        second = pixels[oy:oy + cell_h, ox:ox + cell_w]
        if other_column != column:
            seam = float(np.abs(first[:, -1] - second[:, 0]).mean())
            internal = float(np.concatenate((np.abs(np.diff(first, axis=1)).reshape(-1, 4),
                                             np.abs(np.diff(second, axis=1)).reshape(-1, 4))).mean())
        else:
            seam = float(np.abs(first[-1] - second[0]).mean())
            internal = float(np.concatenate((np.abs(np.diff(first, axis=0)).reshape(-1, 4),
                                             np.abs(np.diff(second, axis=0)).reshape(-1, 4))).mean())
        variation = float(first.std(axis=(0, 1)).mean() + second.std(axis=(0, 1)).mean())
        if structural_indoor:
            # Indoor kits commonly place dissimilar corner/edge/centre pieces
            # next to one another.  A real packing boundary remains much
            # stronger than texture variation immediately inside the cells,
            # whereas an arranged kit has a continuous or comparably noisy
            # shared edge.  Rectangle growth still requires *every* enclosed
            # seam to pass, so a single weak bridge cannot absorb a mixed
            # block through transitive connected-component grouping.
            seam_limit = min(0.18, max(0.05, internal * 1.8 + 0.01))
            return seam <= seam_limit

        # Both tests are mandatory for ordinary terrain.  Treating an
        # invisible edge as decisive allowed unrelated textures with
        # coincidentally similar border pixels to bridge whole components.
        seam_limit = min(0.14, max(0.035, internal * 1.35 + 0.006))
        return seam <= seam_limit and content_compatible(row, column, other_row, other_column)

    horizontal = np.zeros((rows, max(columns - 1, 0)), bool)
    vertical = np.zeros((max(rows - 1, 0), columns), bool)
    for row in range(rows):
        for column in range(columns - 1):
            if available[row, column] and available[row, column + 1]:
                horizontal[row, column] = fits(row, column, row, column + 1)
    for row in range(rows - 1):
        for column in range(columns):
            if available[row, column] and available[row + 1, column]:
                vertical[row, column] = fits(row, column, row + 1, column)

    def belongs_to_group(row: int, column: int, other_row: int, other_column: int) -> bool:
        return structural_indoor or content_compatible(row, column, other_row, other_column)

    def plausible_shape(start_row: int, start_column: int,
                        end_row: int, end_column: int) -> bool:
        if not structural_indoor:
            return True
        width = (end_column - start_column + 1) * cell_w
        height = (end_row - start_row + 1) * cell_h
        # In the stock indoor sheets inferred kits are compact blocks or
        # short trim strips.  Without a shape bound, a run of coincidentally
        # quiet 32-pixel edges can create a nonsensical 32 x 500 swatch.
        return max(width, height) <= 256 and max(width, height) <= min(width, height) * 4

    rectangles: list[tuple[int, int, int, int]] = []
    consumed = np.zeros_like(available)
    for row in range(rows):
        for column in range(columns):
            if not available[row, column] or consumed[row, column]:
                continue
            end_column = column
            end_row = row
            while True:
                can_right = end_column + 1 < columns
                if can_right:
                    new_column = end_column + 1
                    can_right = bool(
                        available[row:end_row + 1, new_column].all()
                        and not consumed[row:end_row + 1, new_column].any()
                        and horizontal[row:end_row + 1, end_column].all()
                        and (end_row == row or vertical[row:end_row, new_column].all())
                        and all(belongs_to_group(row, column, scan_row, new_column)
                                for scan_row in range(row, end_row + 1))
                        and plausible_shape(row, column, end_row, new_column)
                    )
                can_down = end_row + 1 < rows
                if can_down:
                    new_row = end_row + 1
                    can_down = bool(
                        available[new_row, column:end_column + 1].all()
                        and not consumed[new_row, column:end_column + 1].any()
                        and vertical[end_row, column:end_column + 1].all()
                        and (end_column == column or horizontal[new_row, column:end_column].all())
                        and all(belongs_to_group(row, column, new_row, scan_column)
                                for scan_column in range(column, end_column + 1))
                        and plausible_shape(row, column, new_row, end_column)
                    )
                if not can_right and not can_down:
                    break
                # Prefer the extension that absorbs more cells; ties favor
                # width because atlas terrain strips are commonly horizontal.
                if can_right and (not can_down or end_row - row + 1 >= end_column - column + 1):
                    end_column += 1
                else:
                    end_row += 1
            consumed[row:end_row + 1, column:end_column + 1] = True
            rectangles.append((column * cell_w, row * cell_h,
                               (end_column - column + 1) * cell_w, (end_row - row + 1) * cell_h))
    return rectangles


def add_unused_cells(layout: tp.AtlasLayout, cell: int | tuple[int, int] | None = None,
                     atlas: Optional[Image.Image] = None) -> int:
    """Add every uncovered cell using the grid inferred from real UV swatches.

    ``cell`` remains an override for callers with known atlas metadata.  A
    ``(width, height)`` pair permits rectangular cells.
    """
    if cell is None:
        cell_w, cell_h = _unused_cell_size(layout)
    elif isinstance(cell, tuple):
        cell_w, cell_h = cell
    else:
        cell_w = cell_h = cell
    if cell_w <= 0 or cell_h <= 0:
        raise ValueError("Atlas cell dimensions must be positive.")
    if atlas is not None and atlas.size == (layout.width, layout.height):
        rectangles = _fitting_unused_rectangles(layout, cell_w, cell_h, atlas)
    else:
        rectangles = []
        for y in range(0, layout.height - cell_h + 1, cell_h):
            for x in range(0, layout.width - cell_w + 1, cell_w):
                if not any(x < s.x + s.w and s.x < x + cell_w and y < s.y + s.h and s.y < y + cell_h
                           for s in layout.swatches):
                    rectangles.append((x, y, cell_w, cell_h))
    for x, y, width, height in rectangles:
        name = (_swatch_content_name(atlas, x, y, width, height)
                if atlas is not None else f"Cell {x},{y}")
        layout.swatches.append(tp.Swatch(name, x, y, width, height))
    return len(rectangles)


# ---------------------------------------------------------------- paint data


@dataclass
class PaintData:
    """Painted layers and what they need: compiled by :func:`apply_paint`."""

    layout: tp.AtlasLayout
    layers: list[tp.Layer]
    atlas: Image.Image
    custom_atlas: bool = False
    light: Optional[Image.Image] = None  # a baked or painted overlay; None keeps the choice to the import
    slope_degrees: float = tp.SLOPE_DEGREES
    extra: dict = field(default_factory=dict)


def write_paint_dir(folder: Path, paint: PaintData, extra: Optional[dict] = None) -> Path:
    """``kit.json`` plus ``atlas.npy``, ``layer_<k>.npy`` and ``light.npy``."""
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    np.save(folder / "atlas.npy", np.asarray(paint.atlas.convert("RGBA"), np.uint8))
    layers = []
    for k, layer in enumerate(paint.layers):
        record = {"name": layer.name, "swatch": layer.swatch, "slopes": layer.slopes, "file": None}
        if layer.weights is not None:
            record["file"] = f"layer_{k}.npy"
            np.save(folder / record["file"], np.asarray(layer.weights, np.float32))
        layers.append(record)
    if paint.light is not None:
        np.save(folder / "light.npy", np.asarray(paint.light.convert("L"), np.uint8))
    manifest = {
        **paint.extra,
        **(extra or {}),
        "layout": json.loads(paint.layout.to_json()),
        "layers": layers,
        "custom_atlas": paint.custom_atlas,
        "light": "light.npy" if paint.light is not None else None,
        "slope_degrees": paint.slope_degrees,
    }
    path = folder / MANIFEST
    with path.open("w", encoding="utf-8", newline="\n") as stream:
        json.dump(manifest, stream, indent=1)
    return path


def read_paint_dir(folder: Path) -> PaintData:
    folder = Path(folder)
    manifest = json.loads((folder / MANIFEST).read_text(encoding="utf-8"))
    layout = tp.AtlasLayout.from_json(json.dumps(manifest["layout"]))
    layers = []
    for record in manifest["layers"]:
        weights = np.load(folder / record["file"]) if record.get("file") else None
        swatch = int(record["swatch"])
        if not 0 <= swatch < len(layout.swatches):
            raise ValueError(f"Layer {record['name']} uses swatch {swatch}, which the atlas does not have.")
        layers.append(tp.Layer(str(record["name"]), swatch, weights, bool(record.get("slopes"))))
    if not layers:
        raise ValueError("The terrain kit has no layers.")
    atlas = Image.fromarray(np.load(folder / "atlas.npy"), "RGBA")
    light = Image.fromarray(np.load(folder / manifest["light"]), "L") if manifest.get("light") else None
    known = {"layout", "layers", "custom_atlas", "light", "slope_degrees"}
    return PaintData(
        layout, layers, atlas, bool(manifest.get("custom_atlas")), light,
        float(manifest.get("slope_degrees", tp.SLOPE_DEGREES)),
        {k: v for k, v in manifest.items() if k not in known},
    )


def kit_paint(source: TerrainSource, layout: tp.AtlasLayout, atlas: Image.Image, custom: bool,
              resolution: int = PAINT_RESOLUTION) -> PaintData:
    """The map as it is, as layers: the starting point of a kit."""
    layers = tp.decompile(source.positions, source.uv0, source.uv1, source.mask, layout, resolution)
    # a custom atlas has its own swatches; start from the base alone
    if custom:
        layers = layers[:1]
        layers[0].swatch = layout.base
        layers[0].name = layout.swatches[layout.base].name
    return PaintData(layout, layers, atlas, custom, source.light)


# ---------------------------------------------------------------- water


#: Animated shore props a kit lets the user move: the lapping shore foam and
#: the ship wakes (GRAPHICS_NOTES "Map water").
WAVE_OBJECTS = ("wave_99", "ship_wave_01", "ship_wave_02")


@dataclass
class WaterBody:
    name: str
    level: float
    positions: np.ndarray  # (n, 3, 3) surface triangles, glTF winding
    scroll: Optional[tuple[float, float, float, float]]
    texture: int  # the drifting image (first texture record)
    fade: bool  # has the shoreline fade (a second record)
    new: bool = False  # added in Blender


@dataclass
class WaveInstance:
    index: int  # in mapbuildinst
    name: str
    column: int  # mesh tiles: placement minus the terrain origin
    row: int
    angle: int
    height: float


@dataclass
class WaterData:
    """A map's water as a kit carries it: surfaces, the shared shoreline
    fade, the drifting images and the shore props."""

    origin: tuple[int, int]
    bodies: list[WaterBody]
    fade: Optional[np.ndarray]  # float 0..1, row 0 at z = 0
    textures: dict[int, Image.Image]
    waves: list[WaveInstance]
    wave_models: dict[str, np.ndarray]  # (n, 3, 3) in the prop's own coordinates
    wave_uvs: dict[str, np.ndarray] = field(default_factory=dict)  # (n, 3, 2)
    wave_textures: dict[str, Image.Image] = field(default_factory=dict)
    #: playable tiles whose terrain type is a water one, in mesh tiles
    water_tiles: list[tuple[int, int]] = field(default_factory=list)


def _model_triangles(gs_bytes: bytes, uvs: bool = False):
    """A static model's triangles (glTF winding, hidden chunks skipped), and
    with ``uvs`` their first UV set."""
    from .formats.gltf_export import _strip_triangles

    gs = model_fmt.read_model_bytes(gs_bytes)
    tris = [t for c in gs.chunks if not c.hidden for s in c.strips for t in _strip_triangles(s)]
    positions = np.array([[v.position for v in t] for t in tris], float).reshape(-1, 3, 3)
    if not uvs:
        return positions
    return positions, np.array([[v.uv or (0.0, 0.0) for v in t] for t in tris], float).reshape(-1, 3, 2)


def read_water(container: Path) -> WaterData:
    """The water of a ``zmap/<map>/map.cmp``: every ``map_water`` object,
    the fade image they share, their images, and the shore props."""
    from . import map_heights, map_props
    from .gui import model_viewer as mv

    _entries, files = mv._read_container(container)
    map_data = map_file.read_map_bytes(files["map.bin"])
    try:
        terrain = mv.map_terrain_name(files, map_data, container.parent.name)
    except gltf_import.GltfImportError:
        terrain = ""  # open sea without land (bmap14): the panel offsets place it
    origin = map_heights.terrain_origin(map_data, terrain)
    images = tpl.read_tpl_images(io.BytesIO(files[map_props.texpack_name(files)]))
    bodies, textures, fade = [], {}, None
    for name in map_props.water_names(files, map_data):
        gs = model_fmt.read_model_bytes(files[f"{name}.gs"])
        material = next(m for m in gs.materials if m.name == "map_water")
        texture = material.textures[0].tex_id
        positions = _model_triangles(files[f"{name}.gs"])
        ga = files.get(f"{name}.ga")
        bodies.append(WaterBody(
            name, float(np.median(positions[..., 1])) if len(positions) else 0.0, positions,
            map_props.water_scroll(ga) if ga is not None else None, texture, len(material.textures) >= 2,
        ))
        textures.setdefault(texture, images[texture].convert("RGBA"))
        if fade is None and len(material.textures) >= 2:
            fade = np.asarray(images[texture + 1].convert("L"), np.float32) / 255.0
    waves, models, uvs, wave_textures = [], {}, {}, {}
    for index, inst in enumerate(map_data.build_inst):
        name = map_data.build_desc[inst.desc_index].filename
        if name not in WAVE_OBJECTS or f"{name}.gs" not in files:
            continue
        if name not in models:
            models[name], uvs[name] = _model_triangles(files[f"{name}.gs"], uvs=True)
            material = next((m for m in model_fmt.read_model_bytes(files[f"{name}.gs"]).materials if m.textures), None)
            if material is not None and material.textures[0].tex_id < len(images):
                wave_textures[name] = images[material.textures[0].tex_id].convert("RGBA")
        waves.append(WaveInstance(index, name, inst.x - origin[0], inst.y - origin[1], inst.angle % 256,
                                  float(inst.height())))
    grid = map_file.terrain_grid(files["map.bin"]) or []
    wet = [(x - origin[0], y - origin[1]) for x, column in enumerate(grid) for y, kind in enumerate(column)
           if kind in map_props.WATER_TERRAINS]
    return WaterData(tuple(origin), bodies, fade, textures, waves, models, uvs, wave_textures, wet)


def write_water_dir(folder: Path, water: WaterData) -> dict:
    """``water_<body>.npy``, ``water_fade.npy``, ``water_texture_<id>.npy``
    and ``wave_model_<name>.npy`` into ``folder``; returns the manifest
    entry for ``kit.json``'s ``water``."""
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    bodies = []
    for body in water.bodies:
        file = f"water_{body.name}.npy"
        np.save(folder / file, np.asarray(body.positions, np.float32))
        bodies.append({"name": body.name, "level": body.level, "file": file,
                       "scroll": list(body.scroll) if body.scroll is not None else None,
                       "texture": body.texture, "fade": body.fade, "new": body.new})
    if water.fade is not None:
        np.save(folder / "water_fade.npy", np.asarray(water.fade, np.float32))
    textures = {}
    for texture, image in water.textures.items():
        textures[str(texture)] = f"water_texture_{texture}.npy"
        np.save(folder / textures[str(texture)], np.asarray(image.convert("RGBA"), np.uint8))
    models = {}
    for name, positions in water.wave_models.items():
        models[name] = {"file": f"wave_model_{name}.npy", "uv": None, "texture": None}
        np.save(folder / models[name]["file"], np.asarray(positions, np.float32))
        if name in water.wave_uvs:
            models[name]["uv"] = f"wave_uv_{name}.npy"
            np.save(folder / models[name]["uv"], np.asarray(water.wave_uvs[name], np.float32))
        if name in water.wave_textures:
            models[name]["texture"] = f"wave_texture_{name}.npy"
            np.save(folder / models[name]["texture"], np.asarray(water.wave_textures[name].convert("RGBA"), np.uint8))
    return {
        "origin": list(water.origin),
        "bodies": bodies,
        "fade": "water_fade.npy" if water.fade is not None else None,
        "textures": textures,
        "waves": [{"index": w.index, "name": w.name, "column": w.column, "row": w.row,
                   "angle": w.angle, "height": w.height} for w in water.waves],
        "wave_models": models,
        "water_tiles": [list(t) for t in water.water_tiles],
    }


@dataclass
class WaterEdit:
    """A kit's water as Blender saved it, for :func:`apply_water`."""

    bodies: list[WaterBody]
    removed: list[str]
    fade: Optional[np.ndarray]
    fade_changed: bool
    waves: list[WaveInstance]  # index -1: added in Blender
    origin: tuple[int, int]

    @property
    def triangles(self) -> np.ndarray:
        parts = [b.positions for b in self.bodies]
        return np.concatenate(parts) if parts else np.zeros((0, 3, 3))


def read_water_edit(folder: Path, water: Optional[dict]) -> Optional[WaterEdit]:
    """The ``water`` entry of an exported kit's ``kit.json`` (``kit.export_kit``)."""
    if not water or "bodies" not in water:
        return None
    folder = Path(folder)
    bodies = [WaterBody(b["name"], float(b["level"]), np.load(folder / b["file"]).astype(float),
                        tuple(b["scroll"]) if b.get("scroll") is not None else None, int(b.get("texture", -1)),
                        bool(b.get("fade")), bool(b.get("new"))) for b in water["bodies"]]
    waves = [WaveInstance(int(w["index"]), w["name"], int(w["column"]), int(w["row"]), int(w["angle"]) % 256,
                          float(w["height"])) for w in water.get("waves", [])]
    fade = np.load(folder / water["fade"]).astype(np.float32) if water.get("fade") else None
    return WaterEdit(bodies, list(water.get("removed", [])), fade, bool(water.get("fade_changed")), waves,
                     tuple(water.get("origin", (0, 0))))


#: Terrain types the import can repaint tiles with (names used on vanilla maps).
WATER_TILE_TYPES = {"River": "川", "Sea": "海", "Waterway": "水路", "Pond": "池", "Moat": "堀"}
LAND_TILE_TYPES = {"Plain": "平地", "Shore": "海岸", "Desert": "砂漠", "Snow": "雪原"}
#: Natural ground the repaint may flood (and their numbered variants): never
#: bridges, ship decks, floors or buildings standing over water.
FLOODABLE_PREFIXES = ("平地", "海岸", "砂漠", "雪原", "茂み", "山道")
#: Fade under which a covered tile counts as water: where vanilla's water
#: and land tiles split best (bmap03/05/10/13: 90-100 %).
REPAINT_FADE = 0.7


@dataclass
class WaterOutcome:
    warnings: list[str]
    notes: list[str]
    previews: dict[str, Image.Image]


class WaterDonorNeeded(gltf_import.GltfImportError):
    """The kit adds water (or shore foam) the map has no model for."""


def _water_scene(positions: np.ndarray) -> gltf_import.ImportedScene:
    up = (0.0, 1.0, 0.0)
    tris = [gltf_import.ImportedTriangle(tuple(tuple(map(float, p)) for p in t), (up, up, up),
                                         ((0.0, 0.0), (0.0, 0.0), (0.0, 0.0))) for t in positions]
    return gltf_import.ImportedScene([gltf_import.ImportedMaterial("map_water")], {0: tris})


def water_needs_donor(files: dict[str, bytes], edit: WaterEdit) -> list[str]:
    """What the kit adds that the map cannot supply itself: ``"water"`` (a
    body on a map without any) and the names of shore props it lacks."""
    from . import map_props

    data = map_file.read_map_bytes(files["map.bin"])
    needs = []
    if any(b.new for b in edit.bodies) and not map_props.water_names(files, data):
        needs.append("water")
    names = {o.filename for o in data.build_desc}
    needs += sorted({w.name for w in edit.waves if w.index < 0 and w.name not in names})
    return needs


def same_surface(a: np.ndarray, b: np.ndarray, tolerance: float = 1e-3) -> bool:
    """Whether two triangle sets draw the same surface: degenerate strip
    joints dropped, each triangle started at its smallest corner (winding
    kept), the triangles sorted."""
    def canonical(tris):
        tris = np.asarray(tris, float).reshape(-1, 3, 3)
        area = np.linalg.norm(np.cross(tris[:, 1] - tris[:, 0], tris[:, 2] - tris[:, 0]), axis=1)
        tris = np.round(tris[area > 1e-6] / tolerance) * tolerance
        out = []
        for t in tris:
            k = min(range(3), key=lambda i: tuple(t[i]))
            out.append(np.roll(t, -k, axis=0).ravel())
        out = np.array(out).reshape(-1, 9)
        return out[np.lexsort(out.T[::-1])] if len(out) else out

    ca, cb = canonical(a), canonical(b)
    return ca.shape == cb.shape and np.allclose(ca, cb, atol=tolerance * 2)


def apply_water(entries, files: dict[str, bytes], edit: WaterEdit, donor: Optional[dict[str, bytes]] = None,
                repaint: Optional[tuple[str, str]] = None) -> WaterOutcome:
    """Write a kit's water into an unpacked ``map.cmp``: changed or new
    surfaces (:func:`map_props.import_water_scene`), removed ones, the
    scroll tables, the shoreline fade when it was remade or painted, and
    the shore props (moved, turned, removed, added). ``repaint`` ``(water
    type, land type)`` also sets the playable tiles' terrain to match: a
    tile is water when a surface covers its centre and the fade there is
    under :data:`REPAINT_FADE`; only natural ground floods (bridges and
    decks over water stay). Unchanged parts are left byte for byte."""
    from . import map_props

    warnings, notes = [], []
    data = map_file.read_map_bytes(files["map.bin"])
    existing = set(map_props.water_names(files, data))
    placed = {data.build_desc[i.desc_index].filename for i in data.build_inst}
    had_water = bool(existing)
    changed_bodies = 0
    for body in edit.bodies:
        current = _model_triangles(files[f"{body.name}.gs"]) if body.name in existing else None
        same = current is not None and body.name in placed and same_surface(current, body.positions)
        if not same:
            if not existing and donor is None:
                raise WaterDonorNeeded("The kit adds water to a map without any: pick a map to copy its water look from.")
            warnings += [w for w in map_props.import_water_scene(entries, files, _water_scene(body.positions), body.name,
                                                                  donor=None if existing else donor)
                         if "tiles under the water" not in w]
            existing.add(body.name)
            changed_bodies += 1
        ga = files.get(f"{body.name}.ga")
        if body.scroll is not None and ga is not None and map_props.water_scroll(ga) is not None:
            if tuple(round(v, 3) for v in map_props.water_scroll(ga)) != tuple(round(v, 3) for v in body.scroll):
                files[f"{body.name}.ga"] = map_props.set_water_scroll(ga, body.scroll)
                notes.append(f"{body.name}: flow set to " + ", ".join(f"{v:g}" for v in body.scroll) + ".")
    for name in edit.removed:
        if name in existing:
            warnings += map_props.remove_water(files, name)
    notes.insert(0, f"{changed_bodies} of {len(edit.bodies)} water surfaces rebuilt, {len(edit.removed)} removed.")

    # the shoreline fade is the water material's second texture record
    texpack = map_props.texpack_name(files)
    fade_id = None
    for body in edit.bodies:
        material = next((m for m in gs_file.read_gs(files[f"{body.name}.gs"]).materials if m.name == "map_water"), None)
        if material is not None and len(material.textures) >= 2:
            fade_id = material.textures[1].tex_id
            break
    if edit.fade is not None and (edit.fade_changed or not had_water):
        if fade_id is None:
            warnings.append("The water has no shoreline fade image (one texture record): the new fade was not written.")
        else:
            image = Image.fromarray(np.clip(np.rint(edit.fade * 255.0), 0, 255).astype(np.uint8), "L")
            files[texpack] = tpl.replace_image(files[texpack], fade_id, image)
            notes.append("Shoreline fade replaced.")
    elif not had_water and edit.bodies:
        warnings.append("The new water uses the donor map's shoreline fade: make the fade in Blender to match its shore.")

    notes.append(_apply_waves(entries, files, edit, donor))
    if repaint is not None:
        notes.append(_repaint_tiles(files, edit, repaint))
    dry, uncovered = map_props.water_terrain_mismatch(files)
    notes.append(f"Tile check: {uncovered} water tiles without a surface, {dry} land tiles under one "
                 "(normal along banks, where the fade hides it).")
    if uncovered:
        warnings.append(f"{uncovered} water tiles have no water surface over them: repaint them or extend the water.")
    return WaterOutcome(warnings, notes, water_previews(files, edit))


def _apply_waves(entries, files: dict[str, bytes], edit: WaterEdit, donor) -> str:
    from . import map_props

    data = map_file.read_map_bytes(files["map.bin"])
    names = {o.filename: i for i, o in enumerate(data.build_desc)}
    for name in sorted({w.name for w in edit.waves if w.index < 0 and w.name not in names}):
        if donor is None or f"{name}.gs" not in donor:
            raise WaterDonorNeeded(f"The kit adds {name} shore props this map has no model for: pick a map that has them.")
        map_props.copy_prop(donor, name, entries, files)
    data = map_file.read_map_bytes(files["map.bin"])
    names = {o.filename: i for i, o in enumerate(data.build_desc)}
    ox, oy = edit.origin
    records = map_file.instance_records(files["map.bin"])
    by_index = {w.index: w for w in edit.waves if w.index >= 0}
    out, moved, removed = [], 0, 0
    for k, (record, inst) in enumerate(zip(records, data.build_inst)):
        if data.build_desc[inst.desc_index].filename not in WAVE_OBJECTS:
            out.append(record)
            continue
        wave = by_index.get(k)
        if wave is None:
            removed += 1
            continue
        target = (wave.column + ox, wave.row + oy, wave.angle)
        if (inst.x, inst.y, inst.angle % 256) == target and abs(float(inst.height()) - wave.height) < 1e-4:
            out.append(record)
            continue
        out.append(map_file.instance_record(data.build_desc[inst.desc_index], inst.desc_index, *target, wave.height))
        moved += 1
    added = 0
    for wave in edit.waves:
        if wave.index >= 0:
            continue
        index = names[wave.name]
        out.append(map_file.instance_record(data.build_desc[index], index, wave.column + ox, wave.row + oy,
                                            wave.angle, wave.height))
        added += 1
    if moved or removed or added:
        files["map.bin"] = map_file.set_build_instances(files["map.bin"], out)
    return f"Shore props: {moved} moved or turned, {removed} removed, {added} added."


def _repaint_tiles(files: dict[str, bytes], edit: WaterEdit, repaint: tuple[str, str]) -> str:
    from . import map_props, water_kit

    water_type, land_type = repaint
    grid = map_file.terrain_grid(files["map.bin"]) or []
    if not grid:
        return "No tile grid to repaint."
    ox, oy = edit.origin
    columns, rows = len(grid), len(grid[0])
    wet_now = water_kit.covered_tiles(edit.triangles, columns, rows, (ox, oy))
    if edit.fade is not None:
        c, r = np.meshgrid(np.arange(columns), np.arange(rows), indexing="ij")
        wet_now &= water_kit.fade_at(edit.fade, 5.0 * (c - ox) + 2.5, 5.0 * (r - oy) + 2.5) < REPAINT_FADE
    changes, kept = {}, 0
    for x in range(columns):
        for y in range(rows):
            kind = grid[x][y]
            wet = kind in map_props.WATER_TERRAINS
            if wet_now[x, y] and not wet:
                if kind.startswith(FLOODABLE_PREFIXES):
                    changes[(x, y)] = water_type
                else:
                    kept += 1
            elif wet and not wet_now[x, y]:
                changes[(x, y)] = land_type
    if changes:
        files["map.bin"] = map_file.set_tile_terrains(files["map.bin"], changes)
    to_water = sum(1 for t in changes.values() if t == water_type)
    note = f"Tiles repainted: {to_water} to water, {len(changes) - to_water} to land."
    if kept:
        note += f" {kept} tiles over the water that are not natural ground (bridges, decks, floors) kept their type."
    return note


def water_previews(files: dict[str, bytes], edit: WaterEdit, size: int = 512) -> dict[str, Image.Image]:
    """Top-down views for the import review: the water (lighter where the
    fade shows the bank through it) over the playable tiles, blue dots on
    water-typed tiles, white strokes for the shore props; and the fade."""
    from . import map_props, water_kit

    span = water_kit.FADE_SPAN
    scale = size / span
    canvas = np.full((size, size, 3), (70, 62, 52), np.uint8)
    cover = water_kit.cover_grid(edit.triangles, size, span)
    fade = edit.fade if edit.fade is not None else np.zeros((water_kit.FADE_SIZE,) * 2, np.float32)
    centres = (np.arange(size) + 0.5) / scale
    xx, zz = np.meshgrid(centres, centres)
    shade = water_kit.fade_at(fade, xx, zz)
    water = np.stack([20 + shade * 150, 90 + shade * 120, 120 + shade * 100], axis=-1)
    canvas[cover] = water[cover].astype(np.uint8)
    grid = map_file.terrain_grid(files["map.bin"]) or []
    ox, oy = edit.origin
    for x, column in enumerate(grid):
        for y, kind in enumerate(column):
            x0, z0 = int(5 * (x - ox) * scale), int(5 * (y - oy) * scale)
            x1, z1 = int(5 * (x - ox + 1) * scale), int(5 * (y - oy + 1) * scale)
            if 0 <= x0 < size and 0 <= z0 < size:
                canvas[z0, x0:x1] = (110, 110, 110)
                canvas[z0:z1, x0] = (110, 110, 110)
                if kind in map_props.WATER_TERRAINS:
                    canvas[(z0 + z1) // 2, (x0 + x1) // 2] = (40, 120, 255)
    for wave in edit.waves:
        dx, dz = water_kit.wave_direction(wave.angle)
        cx, cz = 5 * wave.column + 2.5, 5 * wave.row + 2.5
        for t in np.linspace(-2.0, 2.0, 9):
            x, z = int((cx + dz * t) * scale), int((cz - dx * t) * scale)
            if 0 <= x < size and 0 <= z < size:
                canvas[z, x] = (255, 255, 255)
    # crop both views to the water, the playable tiles and the waves
    rows, cols = np.nonzero(cover)
    points = [(cols.min(), rows.min()), (cols.max(), rows.max())] if len(rows) else []
    if grid:
        points += [(-ox * 5 * scale, -oy * 5 * scale), ((len(grid) - ox) * 5 * scale, (len(grid[0]) - oy) * 5 * scale)]
    points += [((5 * w.column + 2.5) * scale, (5 * w.row + 2.5) * scale) for w in edit.waves]
    box = (0, 0, size, size)
    if points:
        xs, zs = [p[0] for p in points], [p[1] for p in points]
        box = (max(0, int(min(xs)) - 8), max(0, int(min(zs)) - 8), min(size, int(max(xs)) + 9), min(size, int(max(zs)) + 9))
    fade_box = tuple(int(v * fade.shape[0] / size) for v in box)
    return {"Water": Image.fromarray(canvas, "RGB").crop(box),
            "Fade": Image.fromarray(np.clip(fade * 255, 0, 255).astype(np.uint8), "L").crop(fade_box)}


# ---------------------------------------------------------------- compile onto an import


@dataclass
class PaintOutcome:
    mask: Image.Image
    result: tp.CompileResult
    notes: list[str]
    previews: dict[str, Image.Image]


def _scene_arrays(tris: list[gltf_import.ImportedTriangle]) -> tuple[np.ndarray, dict]:
    positions = np.array([t.positions for t in tris], float).reshape(-1, 3, 3)
    attrs = {"normals": np.array([t.normals for t in tris], float).reshape(-1, 3, 3)}
    if all(t.colors is not None for t in tris):
        attrs["colors"] = np.array([t.colors for t in tris], float).reshape(-1, 3, 4)
    return positions, attrs


def apply_paint(scene: gltf_import.ImportedScene, paint: PaintData,
                light_matrix=None, light: Optional[Image.Image] = None) -> PaintOutcome:
    """Compile ``paint`` onto the scene's ``map_base`` triangles (a scene
    with a single material gets that material renamed ``map_base``): the
    triangles are cut on the swatch repeat lines and given both UV sets,
    and the material samples the atlas. Returns the mask for the import."""
    names = [m.name for m in scene.materials]
    if "map_base" not in names:
        if len(scene.materials) != 1:
            raise gltf_import.GltfImportError(
                "The painted terrain needs one material named map_base (the kit's game mesh has it)."
            )
        scene.materials[0].name = "map_base"
        names = ["map_base"]
    index = names.index("map_base")
    tris = scene.triangles.get(index, [])
    if not tris:
        raise gltf_import.GltfImportError("The painted terrain has no map_base triangles.")
    positions, attrs = _scene_arrays(tris)
    result = tp.compile_paint(positions, paint.layers, paint.layout, attrs, slope_degrees=paint.slope_degrees)
    colors = attrs.get("colors") is not None
    rebuilt = []
    for k in range(len(result.positions)):
        rebuilt.append(gltf_import.ImportedTriangle(
            positions=tuple(tuple(map(float, p)) for p in result.positions[k]),
            normals=tuple(tuple(map(float, n)) for n in result.attrs["normals"][k]),
            uvs=tuple(tuple(map(float, uv)) for uv in result.uv0[k]),
            colors=tuple(tuple(int(round(c)) for c in col) for col in result.attrs["colors"][k]) if colors else None,
            uvs2=tuple(tuple(map(float, uv)) for uv in result.uv1[k]),
        ))
    scene.triangles[index] = rebuilt
    material = scene.materials[index]
    material.image = paint.atlas.convert("RGBA")
    material.baked_terrain_preview = False
    mask = Image.fromarray(result.mask, "L")
    notes = result.report(paint.layout)
    return PaintOutcome(mask, result, notes, previews(result, paint, light_matrix, light))


def previews(result: tp.CompileResult, paint: PaintData, light_matrix=None,
             light: Optional[Image.Image] = None, size: int = 512) -> dict[str, Image.Image]:
    """Top-down views for the import review: what the game draws, the
    layers as painted, the conflicts and the mask, over the terrain."""
    span = float(max(result.positions[:, :, 0].max(), result.positions[:, :, 2].max(), 1.0))
    atlas = np.asarray(paint.atlas.convert("RGB"))
    light_array = np.asarray(light.convert("L"))[..., None] if light is not None else None
    game = tp.render_compiled(result, atlas, size, span, light_array, light_matrix)
    painted = tp.render_layers(paint.layers, paint.layout, atlas, size, span)
    px, pz = tp.pixel_centres(size, span)
    conflict = tp.sample(result.conflicts.astype(float), px, pz) > 0.5
    marked = game.copy()
    marked[conflict] = (marked[conflict] * 0.4 + np.array([255, 0, 0]) * 0.6).astype(np.uint8)
    mask_view = tp.sample(result.mask.astype(float), px, pz)
    return {
        "Game": Image.fromarray(game, "RGB"),
        "Painted": Image.fromarray(painted, "RGB"),
        "Conflicts": Image.fromarray(marked, "RGB"),
        "Mask": Image.fromarray(np.clip(mask_view, 0, 255).astype(np.uint8), "L"),
    }
