"""The app side of terrain painting (:mod:`terrain_paint`).

- :func:`read_terrain` gives a map's ``map_base`` triangles, UVs, atlas,
  mask and light overlay;
- the atlas swatch table of a map is detected from its UVs or saved per
  project (``terrain_paint/<map>.json``, with an optional custom atlas
  ``<map>_atlas.png`` from the atlas builder);
- :class:`PaintData` is what a terrain kit carries between the app and
  Blender (layers as ``.npy`` weight images, so Blender needs no PIL);
- :func:`apply_paint` compiles painted layers onto an imported scene's
  ``map_base`` triangles for :func:`model_viewer.replace_map_terrain_with_glb`.
"""

from __future__ import annotations

import io
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import numpy as np
from PIL import Image

from . import terrain_paint as tp
from .formats import gltf_import, map_file, tpl
from .formats import model as model_fmt

PAINT_FOLDER = "terrain_paint"
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


# ---------------------------------------------------------------- swatch tables


def layout_path(project_dir: Path, map_folder: str) -> Path:
    return Path(project_dir) / PAINT_FOLDER / f"{map_folder}.json"


def custom_atlas_path(project_dir: Path, map_folder: str) -> Path:
    return Path(project_dir) / PAINT_FOLDER / f"{map_folder}_atlas.png"


def detect_layout(source: TerrainSource) -> tp.AtlasLayout:
    width, height = source.atlas.size
    return tp.layout_from_uvs(source.positions, source.uv0, source.uv1, width, height)


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
                return layout, Image.open(custom).convert("RGBA"), True
            if (layout.width, layout.height) == source.atlas.size:
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


def add_unused_cells(layout: tp.AtlasLayout, cell: int = 128) -> int:
    """Add a swatch for every ``cell``-texel square of the atlas no swatch
    touches (unused vanilla swatches such as cobbles); returns how many."""
    added = 0
    for y in range(0, layout.height - cell + 1, cell):
        for x in range(0, layout.width - cell + 1, cell):
            if any(x < s.x + s.w and s.x < x + cell and y < s.y + s.h and s.y < y + cell for s in layout.swatches):
                continue
            layout.swatches.append(tp.Swatch(f"Cell {x},{y}", x, y, cell, cell))
            added += 1
    return added


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
