"""Find Blender and turn exported FE9 GLBs into self-contained ``.blend`` files.

Blender is run headlessly.  The temporary GLB carries the editable geometry
and UV channels; a generated Blender Python script replaces its portable
baked-preview material with the live FE9 atlas/mask/light node graph, packs
the source images, and saves the final file.  Ordinary models use a tagged
collection so their meshes, armatures, and animations can make the reverse
trip without exporting unrelated Blender scene objects.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

from PIL import Image

from .config import load_setting
from .exceptions import ModdingError

SETTING_KEY = "blender_path"
EXECUTABLE_NAMES = ("blender.exe", "blender")


class BlenderError(ModdingError):
    """Blender is missing or could not create the requested file."""


@dataclass(frozen=True)
class TerrainMaterial:
    name: str
    atlas: Image.Image
    mask: Image.Image
    light: Image.Image
    selector_matrix: tuple[tuple[float, float, float, float], ...]
    light_matrix: tuple[tuple[float, float, float, float], ...]


def _blender_projection(matrix):
    """Projection rows after glTF Y-up coordinates become Blender Z-up.

    Blender imports ``(x, y, z)`` from glTF as ``(x, -z, y)``. Therefore a
    row that consumed the glTF vector consumes Blender ``(X, Y, Z)`` with
    coefficients ``(x, -z, y)``.
    """
    return tuple((row[0], -row[2], row[1], row[3]) for row in matrix)


def candidate_paths(environ=None) -> list[Path]:
    """Common Windows install locations, newest version first within each root."""
    env = os.environ if environ is None else environ
    roots = [env.get("ProgramFiles"), env.get("LOCALAPPDATA")]
    found: list[Path] = []
    for root in filter(None, roots):
        base = Path(root)
        blender_root = base / "Blender Foundation"
        if blender_root.is_dir():
            found.extend(
                sorted(blender_root.glob("Blender */blender.exe"), reverse=True)
            )
        found += [base / "Blender Foundation" / "Blender" / "blender.exe", base / "Programs" / "Blender" / "blender.exe"]
    return found


def find_blender(
    configured: Optional[str] = None,
    *,
    environ=None,
    is_file: Callable[[Path], bool] = Path.is_file,
    which: Callable[[str], Optional[str]] = shutil.which,
) -> Optional[Path]:
    if configured:
        path = Path(configured)
        return path if is_file(path) else None
    for path in candidate_paths(environ):
        if is_file(path):
            return path
    for name in EXECUTABLE_NAMES:
        hit = which(name)
        if hit:
            return Path(hit)
    return None


def configured_blender() -> Optional[Path]:
    return find_blender(load_setting(SETTING_KEY) or None)


def command(blender: Path | str, script: Path | str, glb: Path | str,
            manifest: Path | str, target: Path | str) -> list[str]:
    return [
        str(blender), "--background", "--factory-startup", "--disable-autoexec",
        "--python", str(script), "--", str(glb), str(manifest), str(target),
    ]


def export_blend(
    glb: bytes,
    materials: list[TerrainMaterial],
    target: Path | str,
    blender: Optional[Path | str] = None,
    terrain_name: str = "",
    *,
    atlas_layout: str = "",
    run=subprocess.run,
) -> Path:
    """Run Blender to build ``target``. All temporary source images are packed.
    ``atlas_layout`` (``terrain_paint.AtlasLayout`` JSON) is kept on the scene
    for the add-on's atlas-piece tool."""
    executable = Path(blender) if blender else configured_blender()
    if executable is None:
        raise BlenderError("Blender was not found. Set its location in Settings > Preferences.")
    if not executable.is_file():
        raise BlenderError(f"Blender was not found at {executable}. Set its location in Settings > Preferences.")
    target = Path(target).resolve()
    target.parent.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="tellius_blender_") as folder:
        work = Path(folder)
        glb_path = work / "map.glb"
        script_path = work / "build_blend.py"
        manifest_path = work / "materials.json"
        glb_path.write_bytes(glb)
        script_path.write_text(_BLENDER_SCRIPT, encoding="utf-8")
        records = []
        for index, material in enumerate(materials):
            paths = {}
            for role, image in (("atlas", material.atlas), ("mask", material.mask), ("light", material.light)):
                path = work / f"material_{index}_{role}.png"
                image.convert("RGBA").save(path)
                paths[role] = str(path)
            records.append({
                "name": material.name,
                **paths,
                "selector_matrix": _blender_projection(material.selector_matrix),
                "light_matrix": _blender_projection(material.light_matrix),
            })
        manifest_path.write_text(json.dumps({"terrain_name": terrain_name, "materials": records, "atlas_layout": atlas_layout}), encoding="utf-8")
        try:
            result = run(
                command(executable, script_path, glb_path, manifest_path, target),
                capture_output=True, text=True, encoding="utf-8", errors="replace",
            )
        except OSError as exc:
            raise BlenderError(f"Blender could not be started: {exc}") from exc
        if result.returncode != 0 or not target.is_file():
            details = (result.stderr or result.stdout or "No diagnostic output.").strip()
            if len(details) > 3000:
                details = details[-3000:]
            raise BlenderError(f"Blender could not create the .blend file (exit {result.returncode}):\n{details}")
    return target


def export_model_blend(
    glb: bytes,
    target: Path | str,
    blender: Optional[Path | str] = None,
    model_name: str = "",
    *,
    run=subprocess.run,
) -> Path:
    """Import an ordinary model GLB, pack its images, and save a tagged blend."""
    executable = Path(blender) if blender else configured_blender()
    if executable is None:
        raise BlenderError("Blender was not found. Set its location in Settings > Preferences.")
    if not executable.is_file():
        raise BlenderError(f"Blender was not found at {executable}. Set its location in Settings > Preferences.")
    target = Path(target).resolve()
    target.parent.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="tellius_blender_model_") as folder:
        work = Path(folder)
        glb_path = work / "model.glb"
        script_path = work / "build_model_blend.py"
        glb_path.write_bytes(glb)
        script_path.write_text(_MODEL_BLENDER_SCRIPT, encoding="utf-8")
        try:
            result = run(
                [
                    str(executable), "--background", "--factory-startup", "--disable-autoexec",
                    "--python", str(script_path), "--", str(glb_path), str(target), model_name,
                ],
                capture_output=True, text=True, encoding="utf-8", errors="replace",
            )
        except OSError as exc:
            raise BlenderError(f"Blender could not be started: {exc}") from exc
        if result.returncode != 0 or not target.is_file():
            details = (result.stderr or result.stdout or "No diagnostic output.").strip()
            if len(details) > 3000:
                details = details[-3000:]
            raise BlenderError(f"Blender could not create the .blend file (exit {result.returncode}):\n{details}")
    return target


# ---------------------------------------------------------------- terrain kits and the add-on

ADDON_MODULE = "tellius_terrain"
ADDON_SOURCE = Path(__file__).resolve().parent / "blender_addon" / ADDON_MODULE
#: The compiler shared with the app; the add-on gets a copy (Blender has numpy but not this package).
ADDON_SHARED = Path(__file__).resolve().parent / "terrain_paint.py"


def addon_files() -> dict[str, bytes]:
    """The add-on package's files, relative to its folder."""
    files = {p.name: p.read_bytes() for p in sorted(ADDON_SOURCE.glob("*.py"))}
    files["terrain_paint.py"] = ADDON_SHARED.read_bytes()
    return files


def stage_addon(folder: Path) -> Path:
    """Write the add-on package into ``folder/tellius_terrain``; returns ``folder``
    (what a headless script puts on ``sys.path``)."""
    package = Path(folder) / ADDON_MODULE
    package.mkdir(parents=True, exist_ok=True)
    for name, data in addon_files().items():
        (package / name).write_bytes(data)
    return Path(folder)


def addon_zip(target: Path | str) -> Path:
    import zipfile

    target = Path(target)
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, data in addon_files().items():
            archive.writestr(f"{ADDON_MODULE}/{name}", data)
    return target


def _executable(blender: Optional[Path | str]) -> Path:
    executable = Path(blender) if blender else configured_blender()
    if executable is None:
        raise BlenderError("Blender was not found. Set its location in Settings > Preferences.")
    if not executable.is_file():
        raise BlenderError(f"Blender was not found at {executable}. Set its location in Settings > Preferences.")
    return executable


def _run_checked(run, args: list[str], what: str, expected: Optional[Path] = None):
    try:
        result = run(args, capture_output=True, text=True, encoding="utf-8", errors="replace")
    except OSError as exc:
        raise BlenderError(f"Blender could not be started: {exc}") from exc
    if result.returncode != 0 or (expected is not None and not expected.exists()):
        details = (result.stderr or result.stdout or "No diagnostic output.").strip()
        if len(details) > 3000:
            details = details[-3000:]
        raise BlenderError(f"Blender could not {what} (exit {result.returncode}):\n{details}")
    return result


_INSTALL_SCRIPT = r'''
import bpy
import sys

zip_path, module = sys.argv[sys.argv.index("--") + 1:]
bpy.ops.preferences.addon_install(filepath=zip_path, overwrite=True)
bpy.ops.preferences.addon_enable(module=module)
bpy.ops.wm.save_userpref()
print("TELLIUS_ADDON_INSTALLED")
'''


def install_addon(blender: Optional[Path | str] = None, *, run=subprocess.run) -> Path:
    """Install and enable the Tellius Terrain add-on in the user's Blender
    preferences (not a factory startup: the preferences are saved)."""
    executable = _executable(blender)
    with tempfile.TemporaryDirectory(prefix="tellius_addon_") as folder:
        work = Path(folder)
        archive = addon_zip(work / f"{ADDON_MODULE}.zip")
        script = work / "install.py"
        script.write_text(_INSTALL_SCRIPT, encoding="utf-8")
        result = _run_checked(
            run,
            [str(executable), "--background", "--python", str(script), "--", str(archive), ADDON_MODULE],
            "install the add-on",
        )
        if "TELLIUS_ADDON_INSTALLED" not in (result.stdout or ""):
            details = (result.stderr or result.stdout or "").strip()[-3000:]
            raise BlenderError(f"Blender did not confirm the add-on install:\n{details}")
    return executable


_KIT_BUILD_SCRIPT = r'''
import sys

addon_parent, glb_path, folder, target = sys.argv[sys.argv.index("--") + 1:]
sys.path.insert(0, addon_parent)
from tellius_terrain import kit

kit.build_kit(glb_path, folder, target)
'''


def export_terrain_kit(
    glb: bytes,
    write_inputs: Callable[[Path], None],
    target: Path | str,
    blender: Optional[Path | str] = None,
    *,
    run=subprocess.run,
) -> Path:
    """Run Blender to build a terrain kit ``.blend``: ``glb`` is the map's
    terrain and context props; ``write_inputs(folder)`` writes the
    :func:`terrain_kit.write_paint_dir` folder Blender reads."""
    executable = _executable(blender)
    target = Path(target).resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="tellius_kit_") as folder:
        work = Path(folder)
        stage_addon(work / "addon")
        inputs = work / "inputs"
        write_inputs(inputs)
        glb_path = work / "terrain.glb"
        glb_path.write_bytes(glb)
        script = work / "build_kit.py"
        script.write_text(_KIT_BUILD_SCRIPT, encoding="utf-8")
        _run_checked(
            run,
            [str(executable), "--background", "--factory-startup", "--disable-autoexec", "--python", str(script),
             "--", str(work / "addon"), str(glb_path), str(inputs), str(target)],
            "create the terrain kit",
            target,
        )
    return target


_TERRAIN_IMPORT_SCRIPT = r'''
import bpy
import sys

addon_parent, source_path, folder, terrain_name = sys.argv[sys.argv.index("--") + 1:]
sys.path.insert(0, addon_parent)
from pathlib import Path
from tellius_terrain import kit

bpy.ops.wm.open_mainfile(filepath=source_path, load_ui=False, use_scripts=False)
if bpy.context.scene.get(kit.KIT_KEY):
    kit.export_kit(source_path, folder)
else:
    bpy.ops.object.select_all(action="DESELECT")
    terrain = [obj for obj in bpy.context.scene.objects
               if obj.type == "MESH" and (obj.get("fe9_map_terrain") or obj.name == terrain_name)]
    if not terrain:
        raise RuntimeError(
            "No tagged terrain object was found. Keep the exported terrain object or its fe9_map_terrain property."
        )
    for obj in terrain:
        obj.hide_set(False)
        obj.hide_viewport = False
        obj.hide_render = False
        obj.select_set(True)
    bpy.context.view_layer.objects.active = terrain[0]
    Path(folder).mkdir(parents=True, exist_ok=True)
    bpy.ops.export_scene.gltf(
        filepath=str(Path(folder) / "terrain.glb"), export_format="GLB", use_selection=True,
        export_yup=True, export_extras=True,
    )
'''


@dataclass
class TerrainBlend:
    """A map ``.blend`` converted for import: the terrain GLB and, for a
    terrain kit, its paint (``terrain_kit.PaintData``)."""

    glb: bytes
    paint: object = None


def blend_terrain_for_import(
    source: Path | str,
    terrain_name: str,
    blender: Optional[Path | str] = None,
    *,
    run=subprocess.run,
) -> TerrainBlend:
    """Convert a map ``.blend``: a terrain kit gives its game mesh and
    paint, a plain map export its tagged terrain objects."""
    from . import terrain_kit

    executable = _executable(blender)
    source = Path(source).resolve()
    if not source.is_file():
        raise BlenderError(f"The Blender file does not exist: {source}")
    with tempfile.TemporaryDirectory(prefix="tellius_kit_import_") as folder:
        work = Path(folder)
        stage_addon(work / "addon")
        out = work / "out"
        script = work / "import_terrain.py"
        script.write_text(_TERRAIN_IMPORT_SCRIPT, encoding="utf-8")
        _run_checked(
            run,
            [str(executable), "--background", "--factory-startup", "--disable-autoexec", "--python", str(script),
             "--", str(work / "addon"), str(source), str(out), terrain_name],
            "convert the .blend file",
            out / "terrain.glb",
        )
        paint = terrain_kit.read_paint_dir(out) if (out / terrain_kit.MANIFEST).is_file() else None
        return TerrainBlend((out / "terrain.glb").read_bytes(), paint)


def import_command(blender: Path | str, script: Path | str, source: Path | str,
                   target: Path | str, terrain_name: str) -> list[str]:
    return [
        str(blender), "--background", "--factory-startup", "--disable-autoexec",
        "--python", str(script), "--", str(source), str(target), terrain_name,
    ]


def blend_to_glb(
    source: Path | str,
    terrain_name: str,
    blender: Optional[Path | str] = None,
    *,
    run=subprocess.run,
) -> bytes:
    """Export the tagged terrain objects of ``source`` to an in-memory GLB."""
    executable = Path(blender) if blender else configured_blender()
    if executable is None:
        raise BlenderError("Blender was not found. Set its location in Settings > Preferences.")
    if not executable.is_file():
        raise BlenderError(f"Blender was not found at {executable}. Set its location in Settings > Preferences.")
    source = Path(source).resolve()
    if not source.is_file():
        raise BlenderError(f"The Blender file does not exist: {source}")
    with tempfile.TemporaryDirectory(prefix="tellius_blender_import_") as folder:
        work = Path(folder)
        script_path = work / "export_glb.py"
        target = work / "terrain.glb"
        script_path.write_text(_GLB_EXPORT_SCRIPT, encoding="utf-8")
        try:
            result = run(
                import_command(executable, script_path, source, target, terrain_name),
                capture_output=True, text=True, encoding="utf-8", errors="replace",
            )
        except OSError as exc:
            raise BlenderError(f"Blender could not be started: {exc}") from exc
        if result.returncode != 0 or not target.is_file():
            details = (result.stderr or result.stdout or "No diagnostic output.").strip()
            if len(details) > 3000:
                details = details[-3000:]
            raise BlenderError(f"Blender could not convert the .blend file (exit {result.returncode}):\n{details}")
        return target.read_bytes()


def model_blend_to_glb(
    source: Path | str,
    blender: Optional[Path | str] = None,
    *,
    run=subprocess.run,
) -> bytes:
    """Export the tagged ordinary-model collection of ``source`` to GLB."""
    executable = Path(blender) if blender else configured_blender()
    if executable is None:
        raise BlenderError("Blender was not found. Set its location in Settings > Preferences.")
    if not executable.is_file():
        raise BlenderError(f"Blender was not found at {executable}. Set its location in Settings > Preferences.")
    source = Path(source).resolve()
    if not source.is_file():
        raise BlenderError(f"The Blender file does not exist: {source}")
    with tempfile.TemporaryDirectory(prefix="tellius_blender_model_import_") as folder:
        work = Path(folder)
        script_path = work / "export_model_glb.py"
        target = work / "model.glb"
        script_path.write_text(_MODEL_GLB_EXPORT_SCRIPT, encoding="utf-8")
        try:
            result = run(
                [
                    str(executable), "--background", "--factory-startup", "--disable-autoexec",
                    "--python", str(script_path), "--", str(source), str(target),
                ],
                capture_output=True, text=True, encoding="utf-8", errors="replace",
            )
        except OSError as exc:
            raise BlenderError(f"Blender could not be started: {exc}") from exc
        if result.returncode != 0 or not target.is_file():
            details = (result.stderr or result.stdout or "No diagnostic output.").strip()
            if len(details) > 3000:
                details = details[-3000:]
            raise BlenderError(f"Blender could not convert the .blend file (exit {result.returncode}):\n{details}")
        return target.read_bytes()


_MODEL_BLENDER_SCRIPT = r'''
import bpy
import sys

glb_path, target_path, model_name = sys.argv[sys.argv.index("--") + 1:]
before = set(bpy.data.objects)
bpy.ops.import_scene.gltf(filepath=glb_path)
imported = [obj for obj in bpy.data.objects if obj not in before]
if not imported:
    raise RuntimeError("The GLB did not create any Blender objects.")

collection_name = "FE9 Model" + ((" - " + model_name) if model_name else "")
collection = bpy.data.collections.new(collection_name)
collection["fe9_model_collection"] = True
bpy.context.scene.collection.children.link(collection)
for obj in imported:
    obj["fe9_model_object"] = True
    for old_collection in list(obj.users_collection):
        old_collection.objects.unlink(obj)
    collection.objects.link(obj)

bpy.ops.file.pack_all()
bpy.ops.wm.save_as_mainfile(filepath=target_path, check_existing=False)
'''


_MODEL_GLB_EXPORT_SCRIPT = r'''
import bpy
import sys

source_path, target_path = sys.argv[sys.argv.index("--") + 1:]
bpy.ops.wm.open_mainfile(filepath=source_path, load_ui=False, use_scripts=False)
bpy.ops.object.select_all(action="DESELECT")

tagged_collections = [collection for collection in bpy.data.collections
                      if collection.get("fe9_model_collection")]
objects = set()
for collection in tagged_collections:
    objects.update(collection.all_objects)
objects.update(obj for obj in bpy.context.scene.objects if obj.get("fe9_model_object"))
objects = [obj for obj in objects if obj.name in bpy.context.scene.objects]
if not objects:
    raise RuntimeError(
        "No tagged FE9 model collection was found. Keep the exported FE9 Model collection or its custom property."
    )
for obj in objects:
    obj.hide_set(False)
    obj.hide_viewport = False
    obj.hide_render = False
    obj.select_set(True)
bpy.context.view_layer.objects.active = next(
    (obj for obj in objects if obj.type == "MESH"), objects[0]
)
bpy.ops.export_scene.gltf(
    filepath=target_path,
    export_format="GLB",
    use_selection=True,
    export_yup=True,
    export_extras=True,
    export_animations=True,
)
'''


_BLENDER_SCRIPT = r'''
import bpy
import json
import sys


def linear_component(nodes, separate, row, label):
    terms = []
    for socket, coefficient in zip(("X", "Y", "Z"), row[:3]):
        if coefficient == 0.0:
            continue
        multiply = nodes.new("ShaderNodeMath")
        multiply.operation = "MULTIPLY"
        multiply.label = label
        multiply.inputs[1].default_value = coefficient
        nodes.id_data.links.new(separate.outputs[socket], multiply.inputs[0])
        terms.append(multiply.outputs[0])
    value = nodes.new("ShaderNodeValue")
    value.outputs[0].default_value = row[3]
    value.label = label
    current = value.outputs[0]
    for term in terms:
        add = nodes.new("ShaderNodeMath")
        add.operation = "ADD"
        add.label = label
        nodes.id_data.links.new(current, add.inputs[0])
        nodes.id_data.links.new(term, add.inputs[1])
        current = add.outputs[0]
    return current


def projected_vector(nodes, coordinates, matrix, label):
    separate = nodes.new("ShaderNodeSeparateXYZ")
    separate.label = label
    nodes.id_data.links.new(coordinates, separate.inputs[0])
    s = linear_component(nodes, separate, matrix[0], label)
    t = linear_component(nodes, separate, matrix[1], label)
    q = linear_component(nodes, separate, matrix[2], label)
    divide_s = nodes.new("ShaderNodeMath")
    divide_t = nodes.new("ShaderNodeMath")
    divide_s.operation = divide_t.operation = "DIVIDE"
    nodes.id_data.links.new(s, divide_s.inputs[0])
    nodes.id_data.links.new(q, divide_s.inputs[1])
    nodes.id_data.links.new(t, divide_t.inputs[0])
    nodes.id_data.links.new(q, divide_t.inputs[1])
    # TPL/PIL and glTF use a top-left texture origin; Blender image nodes use
    # bottom-left UVs. Imported glTF UV maps are flipped by Blender, while
    # these generated projected coordinates need the equivalent flip here.
    flip_t = nodes.new("ShaderNodeMath")
    flip_t.operation = "SUBTRACT"
    flip_t.inputs[0].default_value = 1.0
    nodes.id_data.links.new(divide_t.outputs[0], flip_t.inputs[1])
    combine = nodes.new("ShaderNodeCombineXYZ")
    combine.label = label
    nodes.id_data.links.new(divide_s.outputs[0], combine.inputs["X"])
    nodes.id_data.links.new(flip_t.outputs[0], combine.inputs["Y"])
    return combine.outputs[0]


def load_image(path, name):
    image = bpy.data.images.load(path, check_existing=False)
    image.name = name
    image.pack()
    return image


def first_uv_names(material):
    for obj in bpy.data.objects:
        if obj.type == "MESH" and material.name in obj.data.materials and len(obj.data.uv_layers) >= 2:
            return obj.data.uv_layers[0].name, obj.data.uv_layers[1].name
    return "UVMap", "UVMap.001"


def build_material(material, record):
    material.use_nodes = True
    old_principled = next((node for node in material.node_tree.nodes if node.type == "BSDF_PRINCIPLED"), None)
    factor = tuple(old_principled.inputs["Base Color"].default_value) if old_principled else (1.0, 1.0, 1.0, 1.0)
    nodes = material.node_tree.nodes
    nodes.clear()
    output = nodes.new("ShaderNodeOutputMaterial")
    principled = nodes.new("ShaderNodeBsdfPrincipled")
    principled.inputs["Metallic"].default_value = 0.0
    principled.inputs["Roughness"].default_value = 1.0
    material.node_tree.links.new(principled.outputs["BSDF"], output.inputs["Surface"])

    atlas = load_image(record["atlas"], "FE9 Atlas - " + material.name)
    mask = load_image(record["mask"], "FE9 Blend Mask - " + material.name)
    light = load_image(record["light"], "FE9 Light Overlay - " + material.name)
    uv0_name, uv1_name = first_uv_names(material)
    uv0 = nodes.new("ShaderNodeUVMap")
    uv1 = nodes.new("ShaderNodeUVMap")
    uv0.uv_map, uv1.uv_map = uv0_name, uv1_name
    uv0.label, uv1.label = "FE9 UV0", "FE9 UV1"
    atlas0 = nodes.new("ShaderNodeTexImage")
    atlas1 = nodes.new("ShaderNodeTexImage")
    atlas0.image = atlas1.image = atlas
    atlas0.extension = atlas1.extension = "REPEAT"
    atlas0.label, atlas1.label = "Atlas through UV0", "Atlas through UV1"
    material.node_tree.links.new(uv0.outputs["UV"], atlas0.inputs["Vector"])
    material.node_tree.links.new(uv1.outputs["UV"], atlas1.inputs["Vector"])

    coordinates = nodes.new("ShaderNodeTexCoord")
    selector_vector = projected_vector(nodes, coordinates.outputs["Object"], record["selector_matrix"], "Mask projection")
    light_vector = projected_vector(nodes, coordinates.outputs["Object"], record["light_matrix"], "Light projection")
    mask_texture = nodes.new("ShaderNodeTexImage")
    light_texture = nodes.new("ShaderNodeTexImage")
    mask_texture.image, light_texture.image = mask, light
    mask_texture.extension = light_texture.extension = "REPEAT"
    mask_texture.label, light_texture.label = "Projected blend mask", "Projected light overlay"
    material.node_tree.links.new(selector_vector, mask_texture.inputs["Vector"])
    material.node_tree.links.new(light_vector, light_texture.inputs["Vector"])
    grey = nodes.new("ShaderNodeRGBToBW")
    material.node_tree.links.new(mask_texture.outputs["Color"], grey.inputs["Color"])
    blend = nodes.new("ShaderNodeMixRGB")
    blend.blend_type = "MIX"
    blend.label = "FE9 atlas blend"
    material.node_tree.links.new(grey.outputs["Val"], blend.inputs[0])
    material.node_tree.links.new(atlas0.outputs["Color"], blend.inputs[1])
    material.node_tree.links.new(atlas1.outputs["Color"], blend.inputs[2])
    illuminate = nodes.new("ShaderNodeMixRGB")
    illuminate.blend_type = "MULTIPLY"
    illuminate.inputs[0].default_value = 1.0
    illuminate.label = "FE9 projected lighting"
    material.node_tree.links.new(blend.outputs["Color"], illuminate.inputs[1])
    material.node_tree.links.new(light_texture.outputs["Color"], illuminate.inputs[2])
    tint = nodes.new("ShaderNodeMixRGB")
    tint.blend_type = "MULTIPLY"
    tint.inputs[0].default_value = 1.0
    tint.inputs[2].default_value = factor
    tint.label = "FE9 material colour"
    material.node_tree.links.new(illuminate.outputs["Color"], tint.inputs[1])
    material.node_tree.links.new(tint.outputs["Color"], principled.inputs["Base Color"])
    material["fe9_baked_terrain_preview"] = True
    material["fe9_live_map_blend"] = True


args = sys.argv[sys.argv.index("--") + 1:]
glb_path, manifest_path, target_path = args
bpy.ops.import_scene.gltf(filepath=glb_path)
with open(manifest_path, "r", encoding="utf-8") as stream:
    manifest = json.load(stream)
terrain_name = manifest.get("terrain_name", "")
if manifest.get("atlas_layout"):
    bpy.context.scene["fe9_atlas_layout"] = manifest["atlas_layout"]
for obj in bpy.data.objects:
    if obj.type == "MESH" and obj.name == terrain_name:
        obj["fe9_map_terrain"] = True
for record in manifest["materials"]:
    matches = [material for material in bpy.data.materials
               if material.name == record["name"] or material.name.startswith(record["name"] + ".")]
    if not matches:
        raise RuntimeError("Imported GLB has no material named " + record["name"])
    for material in matches:
        build_material(material, record)
bpy.ops.file.pack_all()
bpy.ops.wm.save_as_mainfile(filepath=target_path, check_existing=False)
'''


_GLB_EXPORT_SCRIPT = r'''
import bpy
import sys

source_path, target_path, terrain_name = sys.argv[sys.argv.index("--") + 1:]
bpy.ops.wm.open_mainfile(filepath=source_path, load_ui=False, use_scripts=False)
bpy.ops.object.select_all(action="DESELECT")
terrain = [obj for obj in bpy.context.scene.objects
           if obj.type == "MESH" and (obj.get("fe9_map_terrain") or obj.name == terrain_name)]
if not terrain:
    raise RuntimeError(
        "No tagged terrain object was found. Keep the exported terrain object or its fe9_map_terrain property."
    )
for obj in terrain:
    obj.hide_set(False)
    obj.hide_viewport = False
    obj.hide_render = False
    obj.select_set(True)
bpy.context.view_layer.objects.active = terrain[0]
bpy.ops.export_scene.gltf(
    filepath=target_path,
    export_format="GLB",
    use_selection=True,
    export_yup=True,
    export_extras=True,
)
'''
