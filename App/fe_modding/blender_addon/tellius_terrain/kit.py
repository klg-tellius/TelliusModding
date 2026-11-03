"""Terrain kit: build, paint, preview and export FE9 map terrain in Blender.

The app runs :func:`build_kit` and :func:`export_kit` headlessly; the
add-on's panel calls the rest. Blender is Z-up and glTF/FE9 Y-up: a game
point ``(x, y, z)`` is Blender ``(x, -z, y)``. Paint layers, the mask and
the light overlay are images over the map seen from above (row 0 at game
``z = 0``); Blender stores image rows bottom first, so they flip here.
"""

from __future__ import annotations

import json
import math
from pathlib import Path

import bpy
import numpy as np
from mathutils import Matrix
from mathutils.bvhtree import BVHTree

from . import terrain_paint as tp

KIT_KEY = "fe9_terrain_kit"
LAYOUT_KEY = "fe9_atlas_layout"
KIT_COLLECTION = "FE9 Terrain Kit"
REFERENCE_COLLECTION = "FE9 Reference"
PREVIEW_COLLECTION = "FE9 Game Preview"
SCULPT_NAME = "FE9 Sculpt"
GAME_MESH_NAME = "FE9 Game Mesh"
PREVIEW_NAME = "FE9 Game Preview"
TILES_NAME = "FE9 Tile Grid"
PANELS_NAME = "FE9 Tile Panels"
PAINT_UV = "FE9 Paint UV"
MATERIAL_NAME = "FE9 Terrain Paint"
PREVIEW_MATERIAL = "FE9 Game Preview"
ATLAS_IMAGE = "FE9 Atlas"
LIGHT_IMAGE = "FE9 Light Overlay"
MASK_IMAGE = "FE9 Compiled Mask"
CONFLICT_IMAGE = "FE9 Conflicts"
LAYER_PREFIX = "FE9 Layer - "
WATER_COLLECTION = "FE9 Water"
WAVES_COLLECTION = "FE9 Shore Waves"
WATER_PREFIX = "FE9 Water - "
WATER_FADE_IMAGE = "FE9 Water Fade"
WATER_TEXTURE_PREFIX = "FE9 Water Texture "
WAVE_PREFIX = "FE9 Wave - "
WAVE_MODEL_PREFIX = "FE9 Wave Model - "
#: Map clock units per second for the animated preview: an estimate, the
#: game's rate (map state +0x2c -> +0x34) is not measured yet.
WATER_CLOCK_PER_SECOND = 1.0


# ---------------------------------------------------------------- kit data


def kit_data(scene) -> dict | None:
    text = scene.get(KIT_KEY)
    return json.loads(text) if text else None


def set_kit_data(scene, data: dict) -> None:
    scene[KIT_KEY] = json.dumps(data)


def layout_of(scene) -> tp.AtlasLayout | None:
    data = kit_data(scene)
    if data is not None:
        return tp.AtlasLayout.from_json(json.dumps(data["layout"]))
    text = scene.get(LAYOUT_KEY)
    return tp.AtlasLayout.from_json(text) if text else None


def to_game(points: np.ndarray) -> np.ndarray:
    return np.stack([points[..., 0], points[..., 2], -points[..., 1]], axis=-1)


def to_blender(points: np.ndarray) -> np.ndarray:
    return np.stack([points[..., 0], -points[..., 2], points[..., 1]], axis=-1)


def collection(scene, name: str, parent=None):
    found = bpy.data.collections.get(name)
    if found is None:
        found = bpy.data.collections.new(name)
        (parent or scene.collection).children.link(found)
    return found


def tagged(scene, key: str):
    return next((o for o in scene.objects if o.get(key) and o.type == "MESH"), None)


def sculpt_object(scene):
    return tagged(scene, "fe9_terrain_sculpt")


def game_mesh(scene):
    return tagged(scene, "fe9_map_terrain")


# ---------------------------------------------------------------- images


def image_from_array(name: str, array: np.ndarray, *, data: bool = True):
    """A packed image from a top-down array: ``(h, w)`` floats 0..1 or
    ``(h, w, 4)`` uint8. ``data`` images (weights, masks) skip colour management."""
    h, w = array.shape[:2]
    image = bpy.data.images.get(name)
    if image is not None and tuple(image.size) != (w, h):
        bpy.data.images.remove(image)
        image = None
    if image is None:
        image = bpy.data.images.new(name, w, h, alpha=True)
    if array.ndim == 2:
        value = np.clip(np.asarray(array, np.float32), 0.0, 1.0)
        rgba = np.stack([value, value, value, np.ones_like(value)], axis=-1)
    else:
        rgba = np.asarray(array, np.float32) / 255.0
    if data:
        image.colorspace_settings.name = "Non-Color"
    image.pixels.foreach_set(np.ascontiguousarray(rgba[::-1]).ravel())
    image.update()
    image.pack()
    return image


def array_from_image(image) -> np.ndarray:
    """``(h, w, 4)`` float32, row 0 at game ``z = 0``."""
    w, h = image.size
    flat = np.empty(w * h * 4, np.float32)
    image.pixels.foreach_get(flat)
    return flat.reshape(h, w, 4)[::-1]


def weights_of(image) -> np.ndarray:
    return np.ascontiguousarray(array_from_image(image)[..., 0])


# ---------------------------------------------------------------- meshes


def triangles_of(obj, depsgraph=None) -> np.ndarray:
    """The evaluated object's triangles in game coordinates, ``(n, 3, 3)``."""
    depsgraph = depsgraph or bpy.context.evaluated_depsgraph_get()
    evaluated = obj.evaluated_get(depsgraph)
    mesh = evaluated.to_mesh()
    try:
        mesh.calc_loop_triangles()
        co = np.empty(len(mesh.vertices) * 3, np.float64)
        mesh.vertices.foreach_get("co", co)
        co = co.reshape(-1, 3)
        matrix = np.array(obj.matrix_world)
        co = co @ matrix[:3, :3].T + matrix[:3, 3]
        index = np.empty(len(mesh.loop_triangles) * 3, np.int64)
        mesh.loop_triangles.foreach_get("vertices", index)
        return to_game(co[index.reshape(-1, 3)])
    finally:
        evaluated.to_mesh_clear()


def mesh_from_triangles(name: str, game_positions: np.ndarray, uv_sets: dict | None = None):
    """A mesh with one face per triangle (corners not welded)."""
    verts = to_blender(np.asarray(game_positions, float)).reshape(-1, 3)
    n = len(game_positions)
    mesh = bpy.data.meshes.new(name)
    mesh.vertices.add(len(verts))
    mesh.vertices.foreach_set("co", verts.astype(np.float32).ravel())
    mesh.loops.add(n * 3)
    mesh.loops.foreach_set("vertex_index", np.arange(n * 3, dtype=np.int32))
    mesh.polygons.add(n)
    mesh.polygons.foreach_set("loop_start", np.arange(0, n * 3, 3, dtype=np.int32))
    for uv_name, uvs in (uv_sets or {}).items():
        layer = mesh.uv_layers.new(name=uv_name)
        flipped = np.asarray(uvs, np.float32).reshape(-1, 2).copy()
        flipped[:, 1] = 1.0 - flipped[:, 1]
        layer.data.foreach_set("uv", flipped.ravel())
    mesh.update()
    mesh.validate()
    return mesh


def set_paint_uv(obj) -> None:
    """``FE9 Paint UV`` from the vertices' map position (the layers' and
    mask's top-down 640-unit square); recomputed whenever painting starts,
    so sculpting never leaves it stale."""
    mesh = obj.data
    layer = mesh.uv_layers.get(PAINT_UV) or mesh.uv_layers.new(name=PAINT_UV)
    co = np.empty(len(mesh.vertices) * 3, np.float64)
    mesh.vertices.foreach_get("co", co)
    co = co.reshape(-1, 3)
    matrix = np.array(obj.matrix_world)
    co = co @ matrix[:3, :3].T + matrix[:3, 3]
    loops = np.empty(len(mesh.loops), np.int64)
    mesh.loops.foreach_get("vertex_index", loops)
    p = co[loops]
    uv = np.stack([p[:, 0] / tp.MASK_SPAN, 1.0 + p[:, 1] / tp.MASK_SPAN], axis=-1).astype(np.float32)
    layer.data.foreach_set("uv", uv.ravel())
    mesh.uv_layers.active = layer


def signature(obj) -> str:
    co = np.empty(len(obj.data.vertices) * 3, np.float64)
    obj.data.vertices.foreach_get("co", co)
    modifiers = ",".join(f"{m.type}:{m.show_viewport}" for m in obj.modifiers)
    return f"{len(obj.data.vertices)}:{np.round(co.sum(), 3)}:{np.round(np.abs(co).sum(), 3)}:{modifiers}"


# ---------------------------------------------------------------- materials


def _socket(sockets, identifier: str):
    return next(s for s in sockets if s.identifier == identifier)


def _mix(tree, factor, a, b, blend: str = "MIX"):
    node = tree.nodes.new("ShaderNodeMix")
    node.data_type = "RGBA"
    node.blend_type = blend
    links = tree.links
    if isinstance(factor, float):
        _socket(node.inputs, "Factor_Float").default_value = factor
    else:
        links.new(factor, _socket(node.inputs, "Factor_Float"))
    links.new(a, _socket(node.inputs, "A_Color"))
    links.new(b, _socket(node.inputs, "B_Color"))
    return _socket(node.outputs, "Result_Color")


def _math(tree, operation: str, a, b=None, c=None):
    node = tree.nodes.new("ShaderNodeMath")
    node.operation = operation
    for index, value in enumerate((a, b, c)):
        if value is None:
            continue
        if isinstance(value, (int, float)):
            node.inputs[index].default_value = float(value)
        else:
            tree.links.new(value, node.inputs[index])
    return node.outputs[0]


def _position(tree):
    coords = tree.nodes.new("ShaderNodeTexCoord")
    separate = tree.nodes.new("ShaderNodeSeparateXYZ")
    tree.links.new(coords.outputs["Object"], separate.inputs[0])
    return separate.outputs["X"], separate.outputs["Y"]


def _image_node(tree, image, vector, *, interpolation: str = "Linear", extension: str = "EXTEND", label=""):
    node = tree.nodes.new("ShaderNodeTexImage")
    node.image = image
    node.interpolation = interpolation
    node.extension = extension
    node.label = label
    tree.links.new(vector, node.inputs["Vector"])
    return node


def _combine(tree, u, v):
    node = tree.nodes.new("ShaderNodeCombineXYZ")
    tree.links.new(u, node.inputs["X"])
    tree.links.new(v, node.inputs["Y"])
    return node.outputs[0]


def _swatch_vector(tree, x, y, swatch: tp.Swatch, layout: tp.AtlasLayout):
    """Atlas UV of a swatch laid from above at the atlas density
    (Blender ``X = x``, ``Y = -z``), as :func:`terrain_paint.planar_uvs`."""
    d, inset = layout.density, tp.INSET
    fu = _math(tree, "FRACT", _math(tree, "MULTIPLY", x, d / swatch.w))
    fv = _math(tree, "FRACT", _math(tree, "MULTIPLY", y, -d / swatch.h))
    u = _math(tree, "MULTIPLY_ADD", fu, (swatch.w - 2 * inset) / layout.width, (swatch.x + inset) / layout.width)
    v = _math(tree, "MULTIPLY_ADD", fv, -(swatch.h - 2 * inset) / layout.height,
              1.0 - (swatch.y + inset) / layout.height)
    return _combine(tree, u, v)


def _projected(tree, x, y, matrix):
    """Blender UV of a game top-down projection row pair ``u = m0 . (x, y, z, 1)``."""
    m = matrix
    u = _math(tree, "MULTIPLY_ADD", x, m[0][0], _math(tree, "MULTIPLY_ADD", y, -m[0][2], m[0][3]))
    v_tex = _math(tree, "MULTIPLY_ADD", x, m[1][0], _math(tree, "MULTIPLY_ADD", y, -m[1][2], m[1][3]))
    return _combine(tree, u, _math(tree, "SUBTRACT", 1.0, v_tex))


def _finish(tree, colour, light_matrix, light_image, x, y):
    if light_image is not None and light_matrix is not None:
        light = _image_node(tree, light_image, _projected(tree, x, y, light_matrix), extension="REPEAT",
                            label="Light overlay")
        colour = _mix(tree, 1.0, colour, light.outputs["Color"], "MULTIPLY")
    bsdf = tree.nodes.new("ShaderNodeBsdfPrincipled")
    bsdf.inputs["Roughness"].default_value = 1.0
    output = tree.nodes.new("ShaderNodeOutputMaterial")
    tree.links.new(colour, bsdf.inputs["Base Color"])
    tree.links.new(bsdf.outputs["BSDF"], output.inputs["Surface"])


def _fresh_material(name: str):
    material = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    material.use_nodes = True
    material.node_tree.nodes.clear()
    return material


def build_paint_material(scene):
    """The splat preview: every layer's swatch laid from above, composited
    in order by its painted weight, times the light overlay."""
    data = kit_data(scene)
    layout = layout_of(scene)
    atlas = bpy.data.images.get(ATLAS_IMAGE)
    material = _fresh_material(MATERIAL_NAME)
    tree = material.node_tree
    x, y = _position(tree)
    paint_uv = tree.nodes.new("ShaderNodeUVMap")
    paint_uv.uv_map = PAINT_UV
    colour = None
    for k, layer in enumerate(scene.fe9_layers):
        if not 0 <= layer.swatch < len(layout.swatches):
            continue
        swatch = layout.swatches[layer.swatch]
        sampled = _image_node(tree, atlas, _swatch_vector(tree, x, y, swatch, layout), label=layer.name)
        if colour is None or k == 0:
            colour = sampled.outputs["Color"]
            continue
        if layer.image is None or not layer.visible:
            continue
        weight = _image_node(tree, layer.image, paint_uv.outputs["UV"], extension="REPEAT",
                             label=f"Weight {layer.name}")
        colour = _mix(tree, weight.outputs["Color"], colour, sampled.outputs["Color"])
    if colour is None:
        colour = tree.nodes.new("ShaderNodeRGB").outputs[0]
    _finish(tree, colour, data.get("light_matrix") if data else None,
            bpy.data.images.get(LIGHT_IMAGE) if scene.fe9_show_light else None, x, y)
    for obj in (sculpt_object(scene), game_mesh(scene)):
        if obj is not None:
            obj.data.materials.clear()
            obj.data.materials.append(material)
    return material


def build_preview_material(scene):
    """What the game draws: the atlas through UV0 and UV1, mixed by the
    compiled mask, times the light overlay; conflicts in red when shown."""
    data = kit_data(scene)
    material = _fresh_material(PREVIEW_MATERIAL)
    tree = material.node_tree
    x, y = _position(tree)
    atlas = bpy.data.images.get(ATLAS_IMAGE)
    samples = []
    for uv_name in ("UV0", "UV1"):
        uv = tree.nodes.new("ShaderNodeUVMap")
        uv.uv_map = uv_name
        samples.append(_image_node(tree, atlas, uv.outputs["UV"], label=f"Atlas {uv_name}").outputs["Color"])
    selector = _projected(tree, x, y, ((1 / tp.MASK_SPAN, 0, 0, 0), (0, 0, 1 / tp.MASK_SPAN, 0)))
    mask = _image_node(tree, bpy.data.images.get(MASK_IMAGE), selector, extension="REPEAT", label="Mask")
    colour = _mix(tree, mask.outputs["Color"], samples[0], samples[1])
    if scene.fe9_show_conflicts and bpy.data.images.get(CONFLICT_IMAGE) is not None:
        conflict = _image_node(tree, bpy.data.images.get(CONFLICT_IMAGE), selector, interpolation="Closest",
                               extension="REPEAT", label="Conflicts")
        red = tree.nodes.new("ShaderNodeRGB")
        red.outputs[0].default_value = (1.0, 0.0, 0.0, 1.0)
        factor = _math(tree, "MULTIPLY", conflict.outputs["Color"], 0.6)
        colour = _mix(tree, factor, colour, red.outputs[0])
    _finish(tree, colour, data.get("light_matrix") if data else None,
            bpy.data.images.get(LIGHT_IMAGE) if scene.fe9_show_light else None, x, y)
    return material


# ---------------------------------------------------------------- layers


def kit_layers(scene) -> list[tp.Layer]:
    layers = []
    for k, item in enumerate(scene.fe9_layers):
        weights = None
        if k > 0 and item.image is not None and item.visible:
            weights = weights_of(item.image)
        elif k > 0:
            weights = np.zeros((8, 8), np.float32)
        layers.append(tp.Layer(item.name, item.swatch, weights, item.slopes))
    return layers


def add_layer(scene, name: str, swatch: int, weights: np.ndarray | None = None, slopes: bool = False):
    data = kit_data(scene) or {}
    size = int(data.get("paint_resolution", 1024))
    item = scene.fe9_layers.add()
    item.name = name
    item.swatch = swatch
    item.slopes = slopes
    if len(scene.fe9_layers) > 1:
        array = weights if weights is not None else np.zeros((size, size), np.float32)
        item.image = image_from_array(f"{LAYER_PREFIX}{name}", array)
    return item


def remove_layer(scene, index: int) -> None:
    item = scene.fe9_layers[index]
    image = item.image
    scene.fe9_layers.remove(index)
    if image is not None and image.users == 0:
        bpy.data.images.remove(image)


def pack_dirty_images() -> int:
    count = 0
    for image in bpy.data.images:
        if image.is_dirty and (image.name.startswith(LAYER_PREFIX) or image.name in (LIGHT_IMAGE, WATER_FADE_IMAGE)):
            image.pack()
            count += 1
    return count


# ---------------------------------------------------------------- building


def _raycaster(obj, depsgraph):
    return BVHTree.FromObject(obj, depsgraph)


def _heights(tree: BVHTree, xs: np.ndarray, ys: np.ndarray, top: float, default: float) -> np.ndarray:
    out = np.full(len(xs), default)
    for i, (x, y) in enumerate(zip(xs, ys)):
        hit = tree.ray_cast((float(x), float(y), top), (0.0, 0.0, -1.0))
        if hit[0] is not None:
            out[i] = hit[0].z
    return out


def build_sculpt_grid(scene, reference, spacing: float, kit):
    depsgraph = bpy.context.evaluated_depsgraph_get()
    positions = triangles_of(reference, depsgraph)
    lo = positions.reshape(-1, 3).min(axis=0)
    hi = positions.reshape(-1, 3).max(axis=0)
    nx = int(math.ceil((hi[0] - lo[0]) / spacing)) + 1
    nz = int(math.ceil((hi[2] - lo[2]) / spacing)) + 1
    gx = lo[0] + np.minimum(np.arange(nx) * spacing, hi[0] - lo[0])
    gz = lo[2] + np.minimum(np.arange(nz) * spacing, hi[2] - lo[2])
    xx, zz = np.meshgrid(gx, gz)  # row = z
    tree = _raycaster(reference, depsgraph)
    heights = _heights(tree, xx.ravel(), -zz.ravel(), float(hi[1]) + 100.0, float(lo[1]))
    verts = np.stack([xx.ravel(), -zz.ravel(), heights], axis=-1)
    index = np.arange(nx * nz).reshape(nz, nx)
    # quads wound so normals point up (+Z) with Blender Y = -z
    quads = np.stack([index[:-1, :-1], index[:-1, 1:], index[1:, 1:], index[1:, :-1]], axis=-1).reshape(-1, 4)
    quads = quads[:, ::-1]
    mesh = bpy.data.meshes.new(SCULPT_NAME)
    mesh.from_pydata(verts.tolist(), [], quads.tolist())
    mesh.update()
    obj = bpy.data.objects.new(SCULPT_NAME, mesh)
    obj["fe9_terrain_sculpt"] = True
    kit.objects.link(obj)
    for poly in mesh.polygons:
        poly.use_smooth = True
    return obj


def build_flat_sculpt_grid(bounds, spacing: float, kit, height: float = 0.0):
    """A new, level sculpt grid over game-coordinate ``(x0, x1, z0, z1)``.

    Starter kits use this instead of sampling the donor map's terrain.  The
    final row and column land exactly on the requested boundary even when the
    spacing does not divide the size.
    """
    x0, x1, z0, z1 = (float(v) for v in bounds)
    if x1 <= x0 or z1 <= z0 or spacing <= 0:
        raise RuntimeError("The starter terrain bounds and sculpt spacing must be positive.")
    nx = int(math.ceil((x1 - x0) / spacing)) + 1
    nz = int(math.ceil((z1 - z0) / spacing)) + 1
    gx = x0 + np.minimum(np.arange(nx) * spacing, x1 - x0)
    gz = z0 + np.minimum(np.arange(nz) * spacing, z1 - z0)
    xx, zz = np.meshgrid(gx, gz)
    verts = np.stack([xx.ravel(), -zz.ravel(), np.full(xx.size, height)], axis=-1)
    index = np.arange(nx * nz).reshape(nz, nx)
    quads = np.stack(
        [index[:-1, :-1], index[:-1, 1:], index[1:, 1:], index[1:, :-1]], axis=-1
    ).reshape(-1, 4)[:, ::-1]
    mesh = bpy.data.meshes.new(SCULPT_NAME)
    mesh.from_pydata(verts.tolist(), [], quads.tolist())
    mesh.update()
    obj = bpy.data.objects.new(SCULPT_NAME, mesh)
    obj["fe9_terrain_sculpt"] = True
    kit.objects.link(obj)
    for poly in mesh.polygons:
        poly.use_smooth = True
    return obj


def build_tile_grid(scene, reference, playable, tile: float, parent):
    """Wire lines on the playable tiles, draped on the reference terrain."""
    if not playable:
        return None
    x0, x1, z0, z1 = playable
    depsgraph = bpy.context.evaluated_depsgraph_get()
    tree = _raycaster(reference, depsgraph)
    xs = np.arange(x0, x1 + 1e-6, tile)
    zs = np.arange(z0, z1 + 1e-6, tile)
    xx, zz = np.meshgrid(xs, zs)
    top = 1000.0
    heights = _heights(tree, xx.ravel(), -zz.ravel(), top, 0.0) + 0.05
    verts = np.stack([xx.ravel(), -zz.ravel(), heights], axis=-1)
    index = np.arange(len(xs) * len(zs)).reshape(len(zs), len(xs))
    edges = [(int(index[r, c]), int(index[r, c + 1])) for r in range(len(zs)) for c in range(len(xs) - 1)]
    edges += [(int(index[r, c]), int(index[r + 1, c])) for r in range(len(zs) - 1) for c in range(len(xs))]
    mesh = bpy.data.meshes.new(TILES_NAME)
    mesh.from_pydata(verts.tolist(), edges, [])
    obj = bpy.data.objects.new(TILES_NAME, mesh)
    obj.hide_select = True
    obj.hide_render = True
    parent.objects.link(obj)
    return obj


# ---------------------------------------------------------------- water


def water_objects(scene) -> list:
    return [o for o in scene.objects if o.get("fe9_water") and o.type == "MESH"]


def wave_objects(scene) -> list:
    return [o for o in scene.objects if o.get("fe9_wave")]


def _blended(material) -> None:
    if hasattr(material, "surface_render_method"):
        material.surface_render_method = "BLENDED"
    else:
        material.blend_method = "BLEND"


def _clock(tree):
    """A value node driven by the frame: the map clock of the preview."""
    node = tree.nodes.new("ShaderNodeValue")
    node.label = "Map clock"
    driver = node.outputs[0].driver_add("default_value").driver
    driver.type = "SCRIPTED"
    driver.expression = f"frame / fps * {WATER_CLOCK_PER_SECOND}"
    variable = driver.variables.new()
    variable.name = "fps"
    variable.type = "SINGLE_PROP"
    variable.targets[0].id_type = "SCENE"
    variable.targets[0].id = bpy.context.scene
    variable.targets[0].data_path = "render.fps"
    return node.outputs[0]


def _value(tree, label: str, value: float):
    node = tree.nodes.new("ShaderNodeValue")
    node.label = label
    node.name = label
    node.outputs[0].default_value = float(value)
    return node.outputs[0]


def build_water_material(obj, origin, texture_image, fade_image):
    """What the game draws for a ``map_water`` surface (GRAPHICS_NOTES "Map
    water"): its image laid from above twice, each copy every 6.4 tiles and
    drifting by its own scroll pair (the second mirrored along V), averaged;
    lightened by half the shoreline fade, whose value also takes opacity
    away from about 223/255. The scroll values are the ``u1`` .. ``v2``
    nodes, the clock follows the frame."""
    scroll = list(obj.get("fe9_scroll") or (1.0, 0.5, 0.5, 1.0))
    material = _fresh_material(f"{WATER_PREFIX}{obj['fe9_water']}")
    tree = material.node_tree
    x, y = _position(tree)
    z = _math(tree, "MULTIPLY", y, -1.0)  # game z
    t = _clock(tree)
    u1, v1, u2, v2 = (_value(tree, label, value) for label, value in zip(("u1", "v1", "u2", "v2"), scroll))
    ox, oy = float(origin[0]), float(origin[1])

    def tiles(coord, offset, speed):
        # (coord / 5 + offset + speed * t) / 6.4
        moved = _math(tree, "MULTIPLY_ADD", speed, t, _math(tree, "MULTIPLY_ADD", coord, 0.2, offset))
        return _math(tree, "MULTIPLY", moved, 1.0 / 6.4)

    ua = _math(tree, "ADD", tiles(x, ox, u1), 0.5)
    va = _math(tree, "ADD", tiles(z, oy, v1), 0.5)
    ub = _math(tree, "ADD", tiles(x, ox, u2), 0.5)
    vb = _math(tree, "SUBTRACT", 0.5, tiles(z, oy, v2))
    if texture_image is not None:
        layers = []
        for u, v, label in ((ua, va, "Layer 1"), (ub, vb, "Layer 2")):
            node = _image_node(tree, texture_image, _combine(tree, u, _math(tree, "SUBTRACT", 1.0, v)),
                               extension="REPEAT", label=label)
            layers.append(node.outputs["Color"])
        colour = _mix(tree, 0.5, layers[0], layers[1])
    else:  # a new body on a dry map: the import copies a donor's images
        plain = tree.nodes.new("ShaderNodeRGB")
        plain.label = "Donor water (set at import)"
        plain.outputs[0].default_value = (0.08, 0.3, 0.38, 1.0)
        colour = plain.outputs[0]
    alpha = _value(tree, "Opacity", 223.0 / 255.0)
    if fade_image is not None and obj.get("fe9_fade"):
        fade_uv = _combine(tree, _math(tree, "MULTIPLY", x, 1.0 / 640.0),
                           _math(tree, "SUBTRACT", 1.0, _math(tree, "MULTIPLY", z, 1.0 / 640.0)))
        fade = _image_node(tree, fade_image, fade_uv, label="Shoreline fade").outputs["Color"]
        colour = _mix(tree, 1.0, colour, _math(tree, "MULTIPLY", fade, 0.5), "ADD")
        alpha = _math(tree, "SUBTRACT", alpha, fade)
        alpha.node.use_clamp = True
    # the game lights water like any prop (texture x lit colour): matte, no highlight
    bsdf = tree.nodes.new("ShaderNodeBsdfPrincipled")
    bsdf.inputs["Roughness"].default_value = 1.0
    if "Specular IOR Level" in bsdf.inputs:
        bsdf.inputs["Specular IOR Level"].default_value = 0.0
    output = tree.nodes.new("ShaderNodeOutputMaterial")
    tree.links.new(colour, bsdf.inputs["Base Color"])
    tree.links.new(alpha, bsdf.inputs["Alpha"])
    tree.links.new(bsdf.outputs["BSDF"], output.inputs["Surface"])
    _blended(material)
    obj.data.materials.clear()
    obj.data.materials.append(material)
    return material


def set_water_scroll(obj, scroll) -> None:
    """New scroll values on a water surface and its preview material."""
    obj["fe9_scroll"] = [float(v) for v in scroll]
    material = obj.data.materials[0] if obj.data.materials else None
    if material is None or material.node_tree is None:
        return
    for label, value in zip(("u1", "v1", "u2", "v2"), scroll):
        node = material.node_tree.nodes.get(label)
        if node is not None:
            node.outputs[0].default_value = float(value)


#: Shore props drawn additively in the game (chunk flag 0x40): black vanishes.
ADDITIVE_WAVES = ("ship_wave_01", "ship_wave_02")


def _wave_material(name: str, image=None):
    """The prop's texture, at the opacity of mid-animation (``wave_99``
    fades 0 -> 255 -> 0); additive props show their brightness as opacity."""
    material = _fresh_material(f"{WAVE_MODEL_PREFIX}{name}")
    tree = material.node_tree
    bsdf = tree.nodes.new("ShaderNodeBsdfPrincipled")
    bsdf.inputs["Roughness"].default_value = 1.0
    if "Specular IOR Level" in bsdf.inputs:
        bsdf.inputs["Specular IOR Level"].default_value = 0.0
    if image is None:
        bsdf.inputs["Base Color"].default_value = (1.0, 1.0, 1.0, 1.0)
        bsdf.inputs["Alpha"].default_value = 0.6
    else:
        uv = tree.nodes.new("ShaderNodeUVMap")
        uv.uv_map = "UV"
        texture = _image_node(tree, image, uv.outputs["UV"], extension="REPEAT", label=name)
        tree.links.new(texture.outputs["Color"], bsdf.inputs["Base Color"])
        strength = texture.outputs["Color"] if name in ADDITIVE_WAVES else texture.outputs["Alpha"]
        tree.links.new(_math(tree, "MULTIPLY", strength, 0.7), bsdf.inputs["Alpha"])
    output = tree.nodes.new("ShaderNodeOutputMaterial")
    tree.links.new(bsdf.outputs["BSDF"], output.inputs["Surface"])
    _blended(material)
    return material


def wave_model(name: str, positions=None, uvs=None, image=None):
    """The shared mesh of one shore prop, its tile centre at the origin (the
    engine turns props about the centre of their tile)."""
    mesh = bpy.data.meshes.get(f"{WAVE_MODEL_PREFIX}{name}")
    if mesh is None and positions is not None:
        mesh = mesh_from_triangles(f"{WAVE_MODEL_PREFIX}{name}", np.asarray(positions) - (2.5, 0.0, 2.5),
                                   {"UV": uvs} if uvs is not None else None)
        mesh.materials.append(_wave_material(name, image))
    return mesh


def place_wave(scene, name: str, column: float, row: float, angle: int, height: float, index: int = -1):
    """A shore prop object at a placement tile (mesh tiles), as
    ``mapbuildinst`` stores it; ``index`` is its vanilla instance, -1 new."""
    mesh = wave_model(name)
    obj = bpy.data.objects.new(f"{WAVE_PREFIX}{name}", mesh)
    obj["fe9_wave"] = name
    obj["fe9_instance"] = int(index)
    centre = np.array([5.0 * column + 2.5, -5.0 * height, 5.0 * row + 2.5])
    obj.location = tuple(to_blender(centre))
    obj.rotation_euler = (0.0, 0.0, math.radians(360.0 - (angle % 256) * 360.0 / 256.0))
    obj.lock_rotation = (True, True, False)
    collection(scene, WAVES_COLLECTION, collection(scene, WATER_COLLECTION)).objects.link(obj)
    return obj


def wave_placement(obj) -> tuple[int, int, int, float]:
    """``(column, row, angle, height)`` of a shore prop object: the tile
    under its origin, its turn as an angle byte, its height field."""
    x, z, y = obj.location.x, -obj.location.y, obj.location.z
    degrees = math.degrees(obj.rotation_euler.z)
    angle = int(round((360.0 - degrees) * 256.0 / 360.0)) % 256
    return int(math.floor(x / 5.0)), int(math.floor(z / 5.0)), angle, -y / 5.0


def fade_signature(fade: np.ndarray) -> str:
    """Hash of a fade image at the game's 8-bit steps: the import replaces
    the map's image only when this changed."""
    import hashlib

    return hashlib.sha1(np.round(np.clip(fade, 0.0, 1.0) * 255).astype(np.uint8).tobytes()).hexdigest()


def build_water(scene, folder: Path, water: dict | None) -> None:
    """Water surfaces, the fade image and the shore props of a kit."""
    if not water:
        return
    root = collection(scene, WATER_COLLECTION)
    fade_image = None
    if water.get("fade"):
        fade = np.load(folder / water["fade"])
        fade_image = image_from_array(WATER_FADE_IMAGE, fade)
        data = kit_data(scene)
        if data is not None and data.get("water") is not None:
            data["water"]["fade_signature"] = fade_signature(fade)
            set_kit_data(scene, data)
    textures = {}
    for key, file in (water.get("textures") or {}).items():
        textures[int(key)] = image_from_array(f"{WATER_TEXTURE_PREFIX}{key}", np.load(folder / file), data=False)
    for body in water.get("bodies", []):
        mesh = mesh_from_triangles(f"{WATER_PREFIX}{body['name']}", np.load(folder / body["file"]))
        obj = bpy.data.objects.new(f"{WATER_PREFIX}{body['name']}", mesh)
        obj["fe9_water"] = body["name"]
        obj["fe9_level"] = float(body["level"])
        obj["fe9_texture"] = int(body["texture"])
        obj["fe9_fade"] = bool(body["fade"])
        if body.get("new"):
            obj["fe9_new"] = True
        if body.get("scroll") is not None:
            obj["fe9_scroll"] = [float(v) for v in body["scroll"]]
        root.objects.link(obj)
        build_water_material(obj, water.get("origin", (0, 0)), textures.get(int(body["texture"])), fade_image)
    for name, files in (water.get("wave_models") or {}).items():
        uvs = np.load(folder / files["uv"]) if files.get("uv") else None
        image = None
        if files.get("texture"):
            image = image_from_array(f"{WAVE_MODEL_PREFIX}{name}", np.load(folder / files["texture"]), data=False)
        wave_model(name, np.load(folder / files["file"]), uvs, image)
    for wave in water.get("waves", []):
        place_wave(scene, wave["name"], wave["column"], wave["row"], wave["angle"], wave["height"], wave["index"])


# ---------------------------------------------------------------- water editing


def water_data(scene) -> dict:
    return (kit_data(scene) or {}).get("water") or {}


def active_water(scene):
    """The water body the Water panel edits: the chosen one, else the active
    object when it is water, else the first."""
    chosen = getattr(scene, "fe9_water", None)
    if chosen is not None and chosen.get("fe9_water") and chosen.name in scene.objects:
        return chosen
    active = bpy.context.view_layer.objects.active if bpy.context.view_layer else None
    if active is not None and active.get("fe9_water"):
        return active
    bodies = water_objects(scene)
    return bodies[0] if bodies else None


def water_textures() -> dict:
    return {int(i.name[len(WATER_TEXTURE_PREFIX):]): i for i in bpy.data.images
            if i.name.startswith(WATER_TEXTURE_PREFIX) and i.name[len(WATER_TEXTURE_PREFIX):].isdigit()}


def refresh_water_material(scene, obj) -> None:
    build_water_material(obj, water_data(scene).get("origin", (0, 0)),
                         water_textures().get(int(obj.get("fe9_texture", -1))), bpy.data.images.get(WATER_FADE_IMAGE))


def set_water_level(obj, level: float) -> None:
    """Move a flat water surface to height ``level`` (game units)."""
    mesh = obj.data
    co = np.empty(len(mesh.vertices) * 3, np.float32)
    mesh.vertices.foreach_get("co", co)
    co = co.reshape(-1, 3)
    co[:, 2] = level - obj.matrix_world.translation.z
    mesh.vertices.foreach_set("co", co.ravel())
    mesh.update()
    obj["fe9_level"] = float(level)


def set_water_triangles(obj, positions: np.ndarray) -> None:
    """Give a water surface new triangles (game coordinates), keeping its material."""
    materials = list(obj.data.materials)
    old = obj.data
    obj.data = mesh_from_triangles(old.name, positions)
    for material in materials:
        obj.data.materials.append(material)
    obj.matrix_world = Matrix.Identity(4)
    if old.users == 0:
        bpy.data.meshes.remove(old)


def add_water_body(scene, level: float, centre: tuple[float, float]):
    """A new water surface: a two-tile square at ``centre`` (game x, z),
    named after the map's next free ``<map>_water<N>``."""
    data = kit_data(scene) or {}
    taken = {o["fe9_water"] for o in water_objects(scene)}
    base = data.get("terrain") or data.get("map") or "map"
    name = next(f"{base}_water{n}" for n in range(100) if f"{base}_water{n}" not in taken)
    x, z = (math.floor(c / 5.0) * 5.0 for c in centre)
    a, b, c, d = (x - 5, level, z - 5), (x + 5, level, z - 5), (x + 5, level, z + 5), (x - 5, level, z + 5)
    obj = bpy.data.objects.new(f"{WATER_PREFIX}{name}",
                               mesh_from_triangles(f"{WATER_PREFIX}{name}", np.array([(a, d, c), (a, c, b)], float)))
    obj["fe9_water"] = name
    obj["fe9_level"] = float(level)
    textures = water_textures()
    obj["fe9_texture"] = min(textures) if textures else -1
    obj["fe9_fade"] = True
    obj["fe9_new"] = True
    collection(scene, WATER_COLLECTION).objects.link(obj)
    refresh_water_material(scene, obj)
    return obj


def _ground(scene) -> np.ndarray:
    triangles, _source = current_triangles(scene)
    return triangles


def cut_shoreline(scene, obj, margin: float, seed=None, open_sea: bool = False) -> int:
    """Reshape ``obj`` to the ground below its level (see
    :func:`water_kit.shoreline`); ``seed`` (game x, z) keeps only that lake.
    Returns the triangle count."""
    from . import water_kit as wk

    ground = _ground(scene)
    level = float(obj.get("fe9_level", 0.0))
    lo = ground.reshape(-1, 3).min(axis=0)
    hi = ground.reshape(-1, 3).max(axis=0)
    # the area searched: the terrain, the surface as it is, and the cursor (a sea may run past the terrain)
    points = [ground.reshape(-1, 3)[:, [0, 2]], triangles_of(obj).reshape(-1, 3)[:, [0, 2]]]
    if seed is not None:
        points.append(np.array([seed], float))
    every = np.concatenate(points)
    bounds = (min(every[:, 0].min(), 0.0), min(every[:, 1].min(), 0.0), every[:, 0].max() + 5.0, every[:, 1].max() + 5.0)
    current = triangles_of(obj).reshape(-1, 3)
    sea = (current[:, 0].min(), current[:, 2].min(), current[:, 0].max(), current[:, 2].max())
    tris = wk.shoreline(ground, level, margin=margin, bounds=bounds,
                        seeds=[seed] if seed is not None else None, fill_empty=open_sea, fill_area=sea)
    if not len(tris):
        if seed is not None and not open_sea and not (lo[0] <= seed[0] <= hi[0] and lo[2] <= seed[1] <= hi[2]):
            raise RuntimeError("The 3D cursor is past the terrain's edge: tick Open sea past the terrain "
                               "(it fills as far as the surface reaches now), or put the cursor over the ground.")
        raise RuntimeError(f"No ground lies below {level:g} there: raise the water level or pick another spot.")
    set_water_triangles(obj, tris)
    return len(tris)


def all_water_triangles(scene) -> np.ndarray:
    parts = [triangles_of(o) for o in water_objects(scene)]
    return np.concatenate(parts) if parts else np.zeros((0, 3, 3))


def make_fade(scene, from_depth: bool = True, depth_scale: float = 1.0, edge_width: float = 1.0):
    """Rebuild the shoreline fade from every water surface (and the ground,
    for the depth-based vanilla look)."""
    from . import water_kit as wk

    water = all_water_triangles(scene)
    if not len(water):
        raise RuntimeError("The kit has no water surface.")
    fade = wk.shore_fade(water, _ground(scene) if from_depth else None,
                         depth_scale=depth_scale, edge_width=edge_width)
    image = image_from_array(WATER_FADE_IMAGE, fade)
    for obj in water_objects(scene):
        refresh_water_material(scene, obj)
    return image


def fade_array() -> np.ndarray | None:
    image = bpy.data.images.get(WATER_FADE_IMAGE)
    return weights_of(image) if image is not None else None


def default_wave_model():
    """``wave_99``'s strip for a map that has none (the import copies the
    real prop from another map): 10 x 5 units, 1 unit above its origin."""
    a, b, c, d = (0, 1, -5), (10, 1, -5), (10, 1, 0), (0, 1, 0)
    uv = [(0, 0), (1, 0), (1, 1), (0, 1)]
    positions = np.array([(a, d, c), (a, c, b)], float)
    uvs = np.array([(uv[0], uv[3], uv[2]), (uv[0], uv[2], uv[1])], float)
    return wave_model("wave_99", positions, uvs)


def _near(objects, centre, radius):
    if radius <= 0 or centre is None:
        return list(objects)
    return [o for o in objects if math.hypot(o.location.x - centre[0], -o.location.y - centre[1]) <= radius]


def clear_waves(scene, centre=None, radius: float = 0.0, name: str = "wave_99") -> int:
    gone = _near([o for o in wave_objects(scene) if o["fe9_wave"] == name], centre, radius)
    for obj in gone:
        bpy.data.objects.remove(obj)
    return len(gone)


def place_waves(scene, *, keep: float = 1.0, seed: int = 0, centre=None, radius: float = 0.0,
                lift: float = 0.5, replace: bool = True) -> int:
    """Line the shore with ``wave_99`` props from the fade image (see
    :func:`water_kit.wave_slots`), within ``radius`` units of ``centre``
    (game x, z) when ``radius`` > 0. Each floats ``lift`` above the water
    body under it. Returns how many were placed."""
    from . import water_kit as wk

    fade = fade_array()
    if fade is None:
        raise RuntimeError("Make the shoreline fade first: waves follow it.")
    if wave_model("wave_99") is None:
        default_wave_model()
    if replace:
        clear_waves(scene, centre, radius)
    taken = {wave_placement(o)[:2] for o in wave_objects(scene)}
    bodies = [(o, triangles_of(o), float(o.get("fe9_level", 0.0))) for o in water_objects(scene)]
    placed = 0
    for slot in wk.wave_slots(fade, keep=keep, seed=seed):
        x, z = 5.0 * slot.column + 2.5, 5.0 * slot.row + 2.5
        if radius > 0 and centre is not None and math.hypot(x - centre[0], z - centre[1]) > radius:
            continue
        if (slot.column, slot.row) in taken:
            continue
        level = next((lv for _o, tris, lv in bodies if wk.covered(tris, [x], [z])[0]), None)
        if level is None:
            continue
        place_wave(scene, "wave_99", slot.column, slot.row, slot.angle, wk.wave_height(level, lift))
        placed += 1
    return placed


def snap_waves(objects) -> None:
    """Put shore props on their tile centre and the nearest angle byte."""
    for obj in objects:
        column, row, angle, height = wave_placement(obj)
        obj.location = tuple(to_blender(np.array([5.0 * column + 2.5, -5.0 * height, 5.0 * row + 2.5])))
        obj.rotation_euler = (0.0, 0.0, math.radians(360.0 - angle * 360.0 / 256.0))


def face_shore(objects) -> int:
    """Turn shore props up the fade, toward the bank; returns how many had a shore to face."""
    from . import water_kit as wk

    fade = fade_array()
    if fade is None:
        raise RuntimeError("Make the shoreline fade first: waves face up it.")
    turned = 0
    for obj in objects:
        dx, dz, slope = wk.shore_direction(fade, obj.location.x, -obj.location.y)
        if float(slope) > 1e-3:
            angle = wk.wave_angle(float(dx), float(dz))
            obj.rotation_euler = (0.0, 0.0, math.radians(360.0 - angle * 360.0 / 256.0))
            turned += 1
    return turned


WATER_CHECK_NAME = "FE9 Water Tile Check"


def water_tile_check(scene) -> tuple[int, int]:
    """Mark the playable tiles where the water surfaces and the tiles' water
    terrain disagree: red, water terrain with no surface over its centre;
    yellow, a surface over land (normal along banks, where the fade hides
    it). Returns ``(uncovered water, covered land)``."""
    from . import water_kit as wk

    data = kit_data(scene) or {}
    playable = data.get("playable")
    if not playable:
        raise RuntimeError("The kit has no playable area.")
    x0, x1, z0, z1 = playable
    columns = range(int(round(x0 / 5.0)), int(round(x1 / 5.0)))
    rows = range(int(round(z0 / 5.0)), int(round(z1 / 5.0)))
    wet = {tuple(t) for t in water_data(scene).get("water_tiles", [])}
    water = all_water_triangles(scene)
    cells = [(c, r) for c in columns for r in rows]
    covered = wk.covered(water, [5.0 * c + 2.5 for c, _ in cells], [5.0 * r + 2.5 for _, r in cells])
    uncovered = [cell for cell, cov in zip(cells, covered) if not cov and cell in wet]
    land = [cell for cell, cov in zip(cells, covered) if cov and cell not in wet]
    old = bpy.data.objects.get(WATER_CHECK_NAME)
    if old is not None:
        bpy.data.objects.remove(old)
    tris, kinds = [], []
    level = max([float(o.get("fe9_level", 0.0)) for o in water_objects(scene)] or [0.0]) + 0.3
    for kind, cells_of in ((0, uncovered), (1, land)):
        for c, r in cells_of:
            a, b, cc, d = ((5 * c + 0.5, level, 5 * r + 0.5), (5 * c + 4.5, level, 5 * r + 0.5),
                           (5 * c + 4.5, level, 5 * r + 4.5), (5 * c + 0.5, level, 5 * r + 4.5))
            tris += [(a, d, cc), (a, cc, b)]
            kinds += [kind, kind]
    if tris:
        mesh = mesh_from_triangles(WATER_CHECK_NAME, np.array(tris, float))
        for name, colour in (("FE9 Check Uncovered", (1.0, 0.1, 0.1, 1.0)), ("FE9 Check Land", (1.0, 0.8, 0.1, 1.0))):
            material = bpy.data.materials.get(name) or bpy.data.materials.new(name)
            material.diffuse_color = colour
            material.use_nodes = False
            mesh.materials.append(material)
        mesh.polygons.foreach_set("material_index", np.array(kinds, np.int32))
        mesh.update()
        obj = bpy.data.objects.new(WATER_CHECK_NAME, mesh)
        obj.hide_select = True
        obj.hide_render = True
        collection(scene, WATER_COLLECTION).objects.link(obj)
    return len(uncovered), len(land)


def export_water(scene, folder: Path, original: dict) -> dict:
    """The kit's water as saved, for ``terrain_kit.read_water_edit``:
    surfaces as ``water_<name>.npy`` (game coordinates), the fade and
    whether it changed, the shore props' placements and the bodies taken
    out."""
    bodies = []
    for obj in water_objects(scene):
        name = obj["fe9_water"]
        file = f"water_{name}.npy"
        np.save(folder / file, triangles_of(obj).astype(np.float32))
        scroll = obj.get("fe9_scroll")
        bodies.append({"name": name, "level": float(obj.get("fe9_level", 0.0)), "file": file,
                       "scroll": [float(v) for v in scroll] if scroll is not None else None,
                       "texture": int(obj.get("fe9_texture", -1)), "fade": bool(obj.get("fe9_fade")),
                       "new": bool(obj.get("fe9_new"))})
    kept = {b["name"] for b in bodies}
    fade = fade_array()
    if fade is not None:
        np.save(folder / "water_fade.npy", fade.astype(np.float32))
    waves = []
    for obj in wave_objects(scene):
        column, row, angle, height = wave_placement(obj)
        waves.append({"index": int(obj.get("fe9_instance", -1)), "name": obj["fe9_wave"], "column": column,
                      "row": row, "angle": angle, "height": height})
    original_bodies = original.get("original_bodies", original.get("bodies", []))
    return {
        **{k: v for k, v in original.items() if k in ("origin", "water_tiles")},
        "bodies": bodies,
        "removed": [b["name"] for b in original_bodies if b["name"] not in kept],
        "fade": "water_fade.npy" if fade is not None else None,
        "fade_changed": fade is not None and fade_signature(fade) != original.get("fade_signature"),
        "waves": waves,
    }


def build_kit(glb_path: str, folder: str, target: str) -> None:
    """Headless: the kit ``.blend`` from the app's terrain GLB and
    :func:`terrain_kit.write_paint_dir` folder."""
    from . import register

    register()
    folder = Path(folder)
    manifest = json.loads((folder / "kit.json").read_text(encoding="utf-8"))
    scene = bpy.context.scene
    for obj in list(bpy.data.objects):
        bpy.data.objects.remove(obj)
    before = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=glb_path)
    imported = [o for o in bpy.data.objects if o not in before]
    kit = collection(scene, KIT_COLLECTION)
    kit[KIT_KEY] = True
    reference = collection(scene, REFERENCE_COLLECTION)
    for obj in imported:
        for old in list(obj.users_collection):
            old.objects.unlink(obj)
        reference.objects.link(obj)
        obj.hide_select = True
        obj.hide_render = True
    terrain = next((o for o in imported if o.type == "MESH" and o.name.split(".")[0] == manifest["terrain"]), None)
    terrain = terrain or next(o for o in imported if o.type == "MESH")
    terrain.name = "FE9 Original Terrain"

    set_kit_data(scene, {k: v for k, v in manifest.items() if k not in ("layers",)})
    scene.fe9_budget = int(manifest.get("budget", scene.fe9_budget))
    atlas = np.load(folder / "atlas.npy")
    image_from_array(ATLAS_IMAGE, atlas, data=False)
    light_matrix = manifest.get("light_matrix")
    light = np.load(folder / manifest["light"]) if manifest.get("light") else None
    if light is not None:
        image_from_array(LIGHT_IMAGE, light.astype(np.float32) / 255.0)
    elif light_matrix is not None:
        image_from_array(LIGHT_IMAGE, np.ones((512, 512), np.float32))
    for record in manifest["layers"]:
        weights = np.load(folder / record["file"]) if record.get("file") else None
        add_layer(scene, record["name"], int(record["swatch"]), weights, bool(record.get("slopes")))

    starter = manifest.get("starter_ground")
    sculpt = (build_flat_sculpt_grid(starter, float(manifest.get("sculpt_spacing", 2.0)), kit)
              if starter else
              build_sculpt_grid(scene, terrain, float(manifest.get("sculpt_spacing", 2.0)), kit))
    set_paint_uv(sculpt)
    build_tile_grid(scene, sculpt if starter else terrain, manifest.get("playable"),
                    float(manifest.get("tile_size", 5.0)), reference)
    build_paint_material(scene)
    build_water(scene, folder, manifest.get("water"))
    terrain.hide_set(True)
    terrain.hide_viewport = True
    bpy.context.view_layer.objects.active = sculpt
    sculpt.select_set(True)
    for screen in bpy.data.screens:
        for area in screen.areas:
            if area.type == "VIEW_3D":
                for space in area.spaces:
                    if space.type == "VIEW_3D":
                        space.shading.type = "MATERIAL"
                        space.clip_end = 10000.0
    bpy.ops.wm.save_as_mainfile(filepath=target, check_existing=False)


# ---------------------------------------------------------------- game mesh


def current_triangles(scene) -> tuple[np.ndarray, str]:
    """Triangles to compile: the game mesh when it was made from the current
    sculpt, else the sculpt itself."""
    depsgraph = bpy.context.evaluated_depsgraph_get()
    sculpt = sculpt_object(scene)
    made = game_mesh(scene)
    if made is not None and (sculpt is None or made.get("fe9_source") == signature(sculpt)):
        return triangles_of(made, depsgraph), made.name
    if sculpt is None:
        raise RuntimeError("The kit has no FE9 Sculpt object.")
    return triangles_of(sculpt, depsgraph), sculpt.name


def make_game_mesh(scene, budget: int):
    """A triangulated copy of the sculpt reduced so that, once cut on the
    swatch repeat lines, it has about ``budget`` triangles; tagged as the
    terrain the import converts. Returns the object and that cut count."""
    sculpt = sculpt_object(scene)
    if sculpt is None:
        raise RuntimeError("The kit has no FE9 Sculpt object.")
    data = kit_data(scene) or {}
    layout = layout_of(scene)
    layers = kit_layers(scene)
    slope = float(data.get("slope_degrees", tp.SLOPE_DEGREES))
    depsgraph = bpy.context.evaluated_depsgraph_get()
    mesh = bpy.data.meshes.new_from_object(sculpt.evaluated_get(depsgraph))
    old = game_mesh(scene)
    if old is not None:
        old_mesh = old.data
        bpy.data.objects.remove(old)
        if old_mesh.users == 0:
            bpy.data.meshes.remove(old_mesh)
    obj = bpy.data.objects.new(GAME_MESH_NAME, mesh)
    obj.matrix_world = sculpt.matrix_world
    collection(scene, KIT_COLLECTION).objects.link(obj)
    count = sum(len(p.vertices) - 2 for p in mesh.polygons)
    # Keeping the vertices where repeat lines cross stops the reduction from
    # leaving long triangles over many lines; the cuts then add a quarter fewer
    # triangles for the same detail (measured on the Prologue). Only the base
    # swatch's lines run over the whole map: a small swatch's would pin a fine
    # grid of vertices everywhere.
    period_x, period_z = tp.repeat_periods(layout, [])
    co = np.empty(len(mesh.vertices) * 3, np.float64)
    mesh.vertices.foreach_get("co", co)
    game = to_game(co.reshape(-1, 3) @ np.array(obj.matrix_world)[:3, :3].T + np.array(obj.matrix_world)[:3, 3])
    crossings = np.flatnonzero(
        (np.abs(game[:, 0] - np.round(game[:, 0] / period_x) * period_x) < 0.01)
        & (np.abs(game[:, 2] - np.round(game[:, 2] / period_z) * period_z) < 0.01)
    )
    keep = obj.vertex_groups.new(name="FE9 Repeat Crossings")
    keep.add([int(i) for i in crossings], 1.0, "REPLACE")
    # The cut count is a floor (the repeat lines' grid) plus a share of the
    # source triangles, and fewer source triangles can cross more lines:
    # search the decimation target, keeping the most detailed mesh that fits.
    attempts: dict[int, tuple[int, object]] = {}  # target -> (cut count, mesh)
    fits = over = None  # largest target that fits, smallest that does not
    target = budget
    for _attempt in range(6):
        obj.modifiers.clear()
        obj.data = mesh
        triangulate = obj.modifiers.new("Triangulate", "TRIANGULATE")
        triangulate.quad_method = "SHORTEST_DIAGONAL"
        if count > target:
            decimate = obj.modifiers.new("Decimate", "DECIMATE")
            decimate.decimate_type = "COLLAPSE"
            decimate.ratio = max(target / count, 0.001)
            decimate.use_collapse_triangulate = True
            decimate.vertex_group = keep.name
            decimate.invert_vertex_group = True
            decimate.vertex_group_factor = 2.0
        depsgraph = bpy.context.evaluated_depsgraph_get()
        reduced = bpy.data.meshes.new_from_object(obj.evaluated_get(depsgraph))
        obj.modifiers.clear()
        obj.data = reduced
        cut_count = len(tp.seam_cut(triangles_of(obj), layers, layout, slope_degrees=slope)[0])
        obj.data = mesh
        attempts[target] = (cut_count, reduced)
        if cut_count <= budget * 1.03:
            fits = target if fits is None else max(fits, target)
            if target >= count or cut_count >= budget * 0.9:
                break
        else:
            over = target if over is None else min(over, target)
        if fits is not None and over is not None:
            guess = (fits + over) / 2
        elif fits is None:
            guess = target * budget / cut_count * 0.97
            low = sorted(attempts)[:2]
            if len(low) == 2 and attempts[low[1]][0] != attempts[low[0]][0]:
                slope_k = (attempts[low[1]][0] - attempts[low[0]][0]) / (low[1] - low[0])
                if slope_k > 0:
                    guess = low[0] + (budget * 0.98 - attempts[low[0]][0]) / slope_k
        else:
            guess = target * budget / cut_count * 0.97
        target = min(max(int(guess), 200), count)
        if target in attempts or (fits is not None and over is not None and over - fits < max(50, fits // 20)):
            break
    fitting = [a for a in attempts.values() if a[0] <= budget * 1.03]
    best = max(fitting, key=lambda a: a[0]) if fitting else min(attempts.values(), key=lambda a: a[0])
    for attempt in attempts.values():
        if attempt is not best:
            bpy.data.meshes.remove(attempt[1])
    cut_count, reduced = best
    obj.data = reduced
    bpy.data.meshes.remove(mesh)
    obj.vertex_groups.clear()
    reduced.name = GAME_MESH_NAME
    obj["fe9_map_terrain"] = True
    obj["fe9_source"] = signature(sculpt)
    material = bpy.data.materials.get(MATERIAL_NAME)
    reduced.materials.clear()
    if material is not None:
        reduced.materials.append(material)
    obj.hide_set(True)
    return obj, cut_count


# ---------------------------------------------------------------- preview


def game_preview(scene) -> tuple[tp.CompileResult, str]:
    positions, source = current_triangles(scene)
    layout = layout_of(scene)
    data = kit_data(scene)
    result = tp.compile_paint(positions, kit_layers(scene), layout,
                              slope_degrees=float(data.get("slope_degrees", tp.SLOPE_DEGREES)))
    image_from_array(MASK_IMAGE, result.mask.astype(np.float32) / 255.0)
    image_from_array(CONFLICT_IMAGE, result.conflicts.astype(np.float32))
    preview = bpy.data.objects.get(PREVIEW_NAME)
    if preview is not None:
        old = preview.data
        bpy.data.objects.remove(preview)
        bpy.data.meshes.remove(old)
    mesh = mesh_from_triangles(PREVIEW_NAME, result.positions, {"UV0": result.uv0, "UV1": result.uv1})
    preview = bpy.data.objects.new(PREVIEW_NAME, mesh)
    collection(scene, PREVIEW_COLLECTION).objects.link(preview)
    preview.hide_render = True
    mesh.materials.append(build_preview_material(scene))
    return result, source


def remove_preview(scene) -> None:
    preview = bpy.data.objects.get(PREVIEW_NAME)
    if preview is not None:
        old = preview.data
        bpy.data.objects.remove(preview)
        bpy.data.meshes.remove(old)


# ---------------------------------------------------------------- tools


def tile_panels(scene):
    """The flat tile panels the game will stand units on: per playable tile
    two triangles split along (x+1, z)-(x, z+1), corners on the sculpt."""
    data = kit_data(scene)
    sculpt = sculpt_object(scene)
    if not data or not data.get("playable") or sculpt is None:
        raise RuntimeError("The kit has no playable area or sculpt.")
    x0, x1, z0, z1 = data["playable"]
    tile = float(data.get("tile_size", 5.0))
    depsgraph = bpy.context.evaluated_depsgraph_get()
    tree = _raycaster(sculpt, depsgraph)
    xs = np.arange(x0, x1 + 1e-6, tile)
    zs = np.arange(z0, z1 + 1e-6, tile)
    xx, zz = np.meshgrid(xs, zs)
    heights = _heights(tree, xx.ravel(), -zz.ravel(), 1000.0, 0.0).reshape(xx.shape) + 0.02
    tris = []
    for r in range(len(zs) - 1):
        for c in range(len(xs) - 1):
            a = (xs[c], heights[r, c], zs[r])
            b = (xs[c + 1], heights[r, c + 1], zs[r])
            cc = (xs[c + 1], heights[r + 1, c + 1], zs[r + 1])
            d = (xs[c], heights[r + 1, c], zs[r + 1])
            tris += [(a, d, b), (b, d, cc)]
    old = bpy.data.objects.get(PANELS_NAME)
    if old is not None:
        mesh = old.data
        bpy.data.objects.remove(old)
        bpy.data.meshes.remove(mesh)
    mesh = mesh_from_triangles(PANELS_NAME, np.array(tris, float))
    obj = bpy.data.objects.new(PANELS_NAME, mesh)
    obj.display_type = "WIRE"
    obj.show_in_front = True
    obj.hide_select = True
    obj.hide_render = True
    collection(scene, REFERENCE_COLLECTION).objects.link(obj)
    return obj


def bake_light(scene, strength: float, sun_angle: float, sun_height: float) -> None:
    data = kit_data(scene)
    if not data or data.get("light_matrix") is None:
        raise RuntimeError("This map's light projection is unknown; its light overlay cannot be baked.")
    positions, _ = current_triangles(scene)
    azimuth = math.radians(sun_angle)
    elevation = math.radians(sun_height)
    sun = (-math.cos(elevation) * math.cos(azimuth), -math.sin(elevation), -math.cos(elevation) * math.sin(azimuth))
    image = bpy.data.images.get(LIGHT_IMAGE)
    size = image.size[0] if image is not None else 512
    light = tp.bake_light(positions, data["light_matrix"], size, sun=sun, strength=strength)
    image_from_array(LIGHT_IMAGE, light.astype(np.float32) / 255.0)


def auto_paint(scene, index: int, mode: str, low: float, high: float, combine: str) -> None:
    item = scene.fe9_layers[index]
    if index == 0 or item.image is None:
        raise RuntimeError("Choose a layer above the base.")
    positions, _ = current_triangles(scene)
    size = item.image.size[0]
    if mode == "SLOPE":
        weights = tp.slope_weights(positions, size, low, high)
    else:
        weights = tp.height_weights(positions, size, low, high)
    current = weights_of(item.image)
    if combine == "ADD":
        weights = np.maximum(current, weights)
    elif combine == "SUBTRACT":
        weights = np.clip(current - weights, 0.0, 1.0)
    image_from_array(item.image.name, weights)


def apply_swatch_to_faces(obj, swatch_index: int, layout: tp.AtlasLayout, slope_degrees: float) -> tuple[int, int]:
    """Lay one swatch on the selected faces through both UV sets (UV0 and
    UV1 the same, so the mask does not matter there): the atlas-piece tool
    for indoor floors and walls. Returns (faces, faces larger than a repeat)."""
    import bmesh

    if obj.mode != "EDIT":
        raise RuntimeError("Select faces in Edit Mode first.")
    mesh = obj.data
    if len(mesh.uv_layers) < 2:
        raise RuntimeError("The terrain needs two UV maps (the game's UV0 and UV1).")
    bm = bmesh.from_edit_mesh(mesh)
    uv_layers = [bm.loops.layers.uv[mesh.uv_layers[0].name], bm.loops.layers.uv[mesh.uv_layers[1].name]]
    matrix = np.array(obj.matrix_world)
    swatch = layout.swatches[swatch_index]
    d = layout.density
    cos_limit = math.cos(math.radians(slope_degrees))
    faces = too_big = 0
    for face in bm.faces:
        if not face.select:
            continue
        co = np.array([tuple(loop.vert.co) for loop in face.loops], float)
        game = to_game(co @ matrix[:3, :3].T + matrix[:3, 3])
        normal = to_game(np.array(face.normal) @ matrix[:3, :3].T)
        if abs(normal[1]) >= cos_limit:
            h, v = game[:, 0], game[:, 2]
        elif abs(normal[0]) >= abs(normal[2]):
            h, v = game[:, 2] * (-1.0 if normal[0] > 0 else 1.0), -game[:, 1]
        else:
            h, v = game[:, 0] * (1.0 if normal[2] > 0 else -1.0), -game[:, 1]
        ku = math.floor(h.mean() * d / swatch.w)
        kv = math.floor(v.mean() * d / swatch.h)
        lu = h * d - ku * swatch.w
        lv = v * d - kv * swatch.h
        if lu.min() < -0.01 or lv.min() < -0.01 or lu.max() > swatch.w + 0.01 or lv.max() > swatch.h + 0.01:
            too_big += 1
        lu = tp.INSET + np.clip(lu, 0, swatch.w) * (swatch.w - 2 * tp.INSET) / swatch.w
        lv = tp.INSET + np.clip(lv, 0, swatch.h) * (swatch.h - 2 * tp.INSET) / swatch.h
        for loop, a, b in zip(face.loops, lu, lv):
            uv = ((swatch.x + a) / layout.width, 1.0 - (swatch.y + b) / layout.height)
            for layer in uv_layers:
                loop[layer].uv = uv
        faces += 1
    bmesh.update_edit_mesh(mesh)
    return faces, too_big


# ---------------------------------------------------------------- export


def export_kit(source: str, folder: str) -> None:
    """Headless: the kit's terrain as ``terrain.glb`` (the game mesh, made
    again when the sculpt changed since) and its paint as a
    :func:`terrain_kit.read_paint_dir` folder."""
    from . import register

    register()
    bpy.ops.wm.open_mainfile(filepath=source, load_ui=False, use_scripts=False)
    scene = bpy.context.scene
    data = kit_data(scene)
    if data is None:
        raise RuntimeError("This Blender file is not a terrain kit.")
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    sculpt = sculpt_object(scene)
    made = game_mesh(scene)
    if made is None or (sculpt is not None and made.get("fe9_source") != signature(sculpt)):
        made, _count = make_game_mesh(scene, int(data.get("budget", 8000)))
        print("FE9: made the game mesh again from the current sculpt")
    for material in bpy.data.materials:
        if material.name.split(".")[0] == "map_base":
            material.name = "FE9 reference map_base"  # the original terrain's; the name is the import's cue
    plain = bpy.data.materials.new("map_base")
    made.data.materials.clear()
    made.data.materials.append(plain)
    if not made.data.uv_layers:
        made.data.uv_layers.new(name="UVMap")
    # the file may have been saved in a paint mode, where object operators do not run
    for obj in bpy.context.view_layer.objects:
        obj.select_set(False)
    made.hide_set(False)
    made.hide_viewport = False
    made.select_set(True)
    bpy.context.view_layer.objects.active = made
    bpy.ops.export_scene.gltf(
        filepath=str(folder / "terrain.glb"), export_format="GLB", use_selection=True, export_yup=True,
        export_extras=False, export_materials="EXPORT",
    )
    atlas = bpy.data.images.get(ATLAS_IMAGE)
    np.save(folder / "atlas.npy", np.clip(np.rint(array_from_image(atlas) * 255.0), 0, 255).astype(np.uint8))
    layers = []
    for k, item in enumerate(scene.fe9_layers):
        record = {"name": item.name, "swatch": int(item.swatch), "slopes": bool(item.slopes), "file": None}
        if k > 0:
            record["file"] = f"layer_{k}.npy"
            weights = weights_of(item.image) if item.image is not None and item.visible \
                else np.zeros((8, 8), np.float32)
            np.save(folder / record["file"], weights.astype(np.float32))
        layers.append(record)
    light = bpy.data.images.get(LIGHT_IMAGE)
    if light is not None:
        np.save(folder / "light.npy",
                np.clip(np.rint(array_from_image(light)[..., 0] * 255.0), 0, 255).astype(np.uint8))
    manifest = dict(data)
    manifest.update({"layers": layers, "light": "light.npy" if light is not None else None})
    if data.get("water") is not None or water_objects(scene):
        manifest["water"] = export_water(scene, folder, data.get("water") or {})
    (folder / "kit.json").write_text(json.dumps(manifest, indent=1), encoding="utf-8")
