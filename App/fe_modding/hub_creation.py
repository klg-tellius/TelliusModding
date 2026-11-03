"""Create a plain, single-phase FE9 hub from the project's own map assets."""

from __future__ import annotations

import io
import math
import struct
from dataclasses import dataclass
from pathlib import Path
from PIL import Image

from . import chapters, map_heights, map_props, script_sources
from .formats import dispo, fe8data, gltf_import, gs_file, lz10, map_file, message, pak, skeleton, tpl
from .formats.cmb import compile_source, read_cmb, write_cmb


MIN_SIZE = 4
MAX_SIZE = 63  # hub script positions and the map instance format are byte-sized
GRASS = "平地"
DEFAULT_GROUND_COLOR = (89, 140, 66)
AVATAR_AI = {"seq_attack": "SEQ_NOATTACK", "seq_move": "SEQ_NOMOVE",
             "seq_heal": "SEQ_NOHEAL", "mtype": "MTYPE_NORMAL"}


@dataclass(frozen=True)
class GroundAppearance:
    color: tuple[int, int, int]
    image: Image.Image | None
    tiled: bool


def avatar_class(data: bytes, avatar_pid: str) -> str:
    character = next((c for c in fe8data.read_fe8data(data).characters if c.pid == avatar_pid), None)
    if character is None or not character.jid:
        raise ValueError("The hub avatar needs a valid default class.")
    return character.jid


def repair_avatar_deployment(compressed: bytes, avatar_pid: str, avatar_jid: str) -> bytes:
    """Fill required class/AI names without replacing custom assignments."""
    if not avatar_jid:
        raise ValueError("The hub avatar needs a class in its deployment record.")
    packed = lz10.decompress(compressed)
    changes = {}
    found = False
    for entry in pak.read_pak_entries(packed):
        if not entry.name.startswith("dispos_"):
            continue
        document = dispo.parse_dispo(pak.read_pak_file_content(packed, entry))
        changed = False
        for section in document.sections:
            for unit in section.units:
                if unit[dispo.FIELD["pid"]] != avatar_pid:
                    continue
                found = True
                for field, value in {"jid": avatar_jid, **AVATAR_AI}.items():
                    if not unit[dispo.FIELD[field]]:
                        unit[dispo.FIELD[field]] = value
                        changed = True
        if changed:
            changes[entry.name] = dispo.build_dispo(document)
    if not found:
        raise ValueError("The hub deployment has no dedicated avatar to repair.")
    return _pack_entries(packed, changes) if changes else compressed


def _pack_entries(packed: bytes, changes: dict[str, bytes]) -> bytes:
    entries = pak.read_pak_entries(packed)
    return lz10.compress(pak.pack_pak(
        [(entry.name, changes.get(entry.name, pak.read_pak_file_content(packed, entry))) for entry in entries],
        [entry.reserved for entry in entries]))


def _flat_model(width: int, height: int, texture_id: int, white_id: int,
                color: tuple[int, int, int] = DEFAULT_GROUND_COLOR, tiled: bool = False,
                origin: tuple[float, float] = (0.0, 0.0), bone: int = 0,
                bone_world: skeleton.Mat3x4 = skeleton.IDENTITY_3X4) -> bytes:
    """Make a ground plane with valid base and projected-overlay textures."""
    x0, z0 = origin
    x1, z1 = x0 + width * map_file.TILE_UNITS, z0 + height * map_file.TILE_UNITS
    points = ((x0, 0.0, z0), (x1, 0.0, z0), (x1, 0.0, z1), (x0, 0.0, z1))
    normal = ((0.0, 1.0, 0.0),) * 3
    u, v = (float(width), float(height)) if tiled else (1.0, 1.0)
    # The map renderer's ground basis faces the opposite way from image-space.
    # Rotate the UV rectangle so an imported picture is not shown upside-down
    # and backwards in game.  Keep the texture itself untouched so reopening
    # and applying the current image does not rotate it a second time.
    uv = ((u, v), (0.0, v), (0.0, 0.0), (u, 0.0))
    triangle = gltf_import.ImportedTriangle
    rgba = tuple(channel / 255.0 for channel in color) + (1.0,)
    scene = gltf_import.ImportedScene(
        materials=[gltf_import.ImportedMaterial("hub_ground", rgba,
                   image=Image.new("RGBA", (8, 8), "white"), double_sided=True)],
        triangles={0: [triangle((points[0], points[1], points[2]), normal, (uv[0], uv[1], uv[2])),
                       triangle((points[0], points[2], points[3]), normal, (uv[0], uv[2], uv[3]))]})
    # map_base installs a dual-texture callback even on an untextured material
    # (US PC 0x800F010C dereferences its null texture table). A neutral name
    # avoids that route, but ALL terrain materials still need the last-record
    # projected overlay. White preserves the ground's solid colour.
    overlay = gs_file.GsTexture((1, 0), white_id, (257, 0, 0, 0, 0), 1.0, 1.0, 0)
    return gs_file.write_gs(gltf_import.build_static_gs(
        scene, name="tellius_hub_ground", tex_id_base=texture_id, extra_textures=(overlay,),
        bone=bone, bone_world=bone_world).gs)


def _ground(files: dict[str, bytes]) -> tuple[map_file.MapData, map_file.MapObject]:
    data = map_file.read_map_bytes(files["map.bin"])
    ground = next((obj for obj in data.build_desc if map_file.is_base_terrain_object(obj)
                   and f"{obj.filename}.gs" in files and "water" not in obj.filename.lower()), None)
    if ground is None:
        raise ValueError("The hub map has no usable ground model.")
    return data, ground


def flat_ground_appearance(files: dict[str, bytes]) -> GroundAppearance:
    """Read the editable appearance of a generated blank-hub ground."""
    _data, ground = _ground(files)
    model = gs_file.read_gs(files[f"{ground.filename}.gs"])
    material = next((item for item in model.materials if item.name == "hub_ground"), None)
    if material is None or not material.textures:
        raise ValueError("Only a hub created with Blank map has an editable generated ground.")
    color = tuple(min(255, round(channel * gltf_import.COLOR_LOAD_SCALE)) for channel in material.color0[:3])
    base_id = material.textures[0].tex_id
    overlay_id = material.textures[-1].tex_id
    image = None
    if base_id != overlay_id:
        images = tpl.read_tpl_images(io.BytesIO(files[map_props.texpack_name(files)]))
        if not 0 <= base_id < len(images):
            raise ValueError("The generated hub ground refers to a missing texture.")
        image = images[base_id].convert("RGBA")
    scale = float(1 << model.uv_frac)
    tiled = any(abs(u / scale) > 1.0001 or abs(v / scale) > 1.0001 for u, v in model.uvs)
    return GroundAppearance(color, image, tiled)


def replace_flat_ground(_entries: list[pak.PakEntry], files: dict[str, bytes], *,
                        ground_color: tuple[int, int, int] = DEFAULT_GROUND_COLOR,
                        ground_image: Image.Image | None = None, tile_ground_image: bool = False,
                        replace_custom_terrain: bool = False) -> None:
    """Replace a hub's ground appearance, optionally flattening custom terrain."""
    if len(ground_color) != 3 or any(not 0 <= channel <= 255 for channel in ground_color):
        raise ValueError("The hub ground color needs three values from 0 to 255.")
    data, ground = _ground(files)
    if not replace_custom_terrain:
        flat_ground_appearance(files)  # reject template or subsequently replaced terrain
    if data.capacity is None:
        raise ValueError("The hub map has no editable dimensions.")
    ox, oy = map_heights.terrain_origin(data, ground.filename)
    origin = (-ox * map_file.TILE_UNITS, -oy * map_file.TILE_UNITS)
    original = gs_file.read_gs(files[f"{ground.filename}.gs"])
    first = next(iter(original.chunks), None)
    bone = first.bone if first is not None else 0
    bone_world = skeleton.IDENTITY_3X4
    if f"{ground.filename}.g" in files:
        bones = skeleton.read_skeleton_file(files[f"{ground.filename}.g"]).bones
        if 0 <= bone < len(bones):
            bone_world = skeleton.bind_world_matrices(bones)[bone]
    texpack = map_props.texpack_name(files)
    white = tpl.build_tpl([(Image.new("RGBA", (8, 8), "white"), tpl.FORMAT_I4)], wrap=tpl.WRAP_CLAMP)
    files[texpack], white_id = tpl.copy_images(files[texpack], white, [0])
    texture_id = white_id
    material_color = ground_color
    if ground_image is not None:
        converted, texture_format = gltf_import.texture_for_tpl(ground_image, 1024)
        source = tpl.build_tpl([(converted, texture_format)],
                               wrap=tpl.WRAP_REPEAT if tile_ground_image else tpl.WRAP_CLAMP)
        files[texpack], texture_id = tpl.copy_images(files[texpack], source, [0])
        material_color = (255, 255, 255)
    files[f"{ground.filename}.gs"] = _flat_model(
        data.capacity.x_size, data.capacity.y_size, texture_id, white_id, material_color,
        ground_image is not None and tile_ground_image, origin, bone, bone_world)
    x0, z0 = origin
    x1 = x0 + data.capacity.x_size * map_file.TILE_UNITS
    z1 = z0 + data.capacity.y_size * map_file.TILE_UNITS
    map_bin = files["map.bin"]
    for field_name, value in (("offset_x", x0), ("offset_y", 0.0), ("offset_z", z0),
                              ("size_x", x1), ("size_y", 0.1), ("size_z", z1)):
        map_bin = map_file.patch_object_field(map_bin, ground, field_name, value)
    files["map.bin"] = map_bin
    map_props.compact_texpack(files)


def blank_map(compressed: bytes, width: int, height: int, *,
              ground_color: tuple[int, int, int] = DEFAULT_GROUND_COLOR,
              ground_image: Image.Image | None = None, tile_ground_image: bool = False) -> bytes:
    """Retain a valid donor archive's engine resources; replace its ground and grid."""
    if not MIN_SIZE <= width <= MAX_SIZE or not MIN_SIZE <= height <= MAX_SIZE:
        raise ValueError(f"Hub dimensions must be {MIN_SIZE}–{MAX_SIZE} tiles.")
    if len(ground_color) != 3 or any(not 0 <= channel <= 255 for channel in ground_color):
        raise ValueError("The hub ground color needs three values from 0 to 255.")
    packed = lz10.decompress(compressed)
    entries = pak.read_pak_entries(packed)
    content = {entry.name: pak.read_pak_file_content(packed, entry) for entry in entries}
    if "map.bin" not in content:
        raise ValueError("The starter map has no map.bin.")
    data = content["map.bin"]
    parsed = map_file.read_map_bytes(data)
    if parsed.capacity is None or parsed.panel_index is None or not parsed.unique_panel:
        raise ValueError("The starter map has no editable terrain grid.")
    ground = next((obj for obj in parsed.build_desc if map_file.is_base_terrain_object(obj)
                   and f"{obj.filename}.gs" in content and "water" not in obj.filename.lower()), None)
    if ground is None:
        raise ValueError("The starter map has no usable ground model.")
    base_index = parsed.build_desc.index(ground)
    # Replace every present panel layer with one flat panel and a zero-index grid.
    for index_name, panel_name in (("panelindex", "uniquepanel"),
                                   ("panelindexRoof", "uniquepanelRoof"),
                                   ("panelindexBase", "uniquepanelBase")):
        try:
            map_file.section_bytes(data, index_name)
            map_file.section_bytes(data, panel_name)
        except map_file.MapFileError:
            continue
        grid = bytes(width * height * 2)
        data = map_file.replace_section(data, index_name, grid + bytes(-len(grid) % 4))
        data, grass_ptr = map_file.add_pool_string(data, GRASS)
        data = map_file.replace_section(data, panel_name,
                                        struct.pack(">hhhhI", 0, 0, 0, 0, grass_ptr), [8])
    for section in ("maplink", "maplinkAt", "maplinkAbs"):
        try:
            map_file.section_bytes(data, section)
        except map_file.MapFileError:
            continue
        data = map_file.replace_section(data, section, b"\x00\x00\x00\x00")
    capacity_at, _ = map_file.section_bytes(data, "mapcapacity")
    out = bytearray(data)
    struct.pack_into(">HH", out, capacity_at, width, height)
    data = bytes(out)
    # Only the base terrain instance is kept; all decorative placements disappear.
    parsed = map_file.read_map_bytes(data)
    for field, value in (("offset_x", 0.0), ("offset_y", 0.0), ("offset_z", 0.0),
                         ("size_x", width * map_file.TILE_UNITS), ("size_y", 0.1),
                         ("size_z", height * map_file.TILE_UNITS)):
        data = map_file.patch_object_field(data, parsed.build_desc[base_index], field, value)
    parsed = map_file.read_map_bytes(data)
    ground_record = map_file.instance_record(parsed.build_desc[base_index], base_index, 0, 0, 0, 0.0)
    data = map_file.set_build_instances(data, [ground_record])
    parsed = map_file.read_map_bytes(data)
    if parsed.extra is not None:
        for field, value in (("panel_offset_x", 0), ("panel_offset_y", 0),
                             ("half_x_size", math.ceil(width / 2)), ("half_y_size", math.ceil(height / 2)),
                             ("texture_projection_extent_x2", min(255, 2 * max(width, height))),
                             ("grid_buffer", 0),
                             ("unknown_tail", parsed.extra.unknown_tail & ~map_props.MAP_FLAG_WATER)):
            data = map_file.patch_extra_field(data, parsed.extra, field, value)
    content["map.bin"] = data
    white = tpl.build_tpl([(Image.new("RGBA", (8, 8), "white"), tpl.FORMAT_I4)], wrap=tpl.WRAP_CLAMP)
    if "texpack.tpl" in content:
        content["texpack.tpl"], white_id = tpl.copy_images(content["texpack.tpl"], white, [0])
    else:
        content["texpack.tpl"], white_id = white, 0
    texture_id = white_id
    material_color = ground_color
    if ground_image is not None:
        converted, texture_format = gltf_import.texture_for_tpl(ground_image, 1024)
        source = tpl.build_tpl([(converted, texture_format)],
                               wrap=tpl.WRAP_REPEAT if tile_ground_image else tpl.WRAP_CLAMP)
        content["texpack.tpl"], texture_id = tpl.copy_images(content["texpack.tpl"], source, [0])
        material_color = (255, 255, 255)  # show the image without a color tint
    content[f"{ground.filename}.gs"] = _flat_model(
        width, height, texture_id, white_id, material_color,
        ground_image is not None and tile_ground_image)
    if not any(entry.name == "texpack.tpl" for entry in entries):
        return lz10.compress(pak.pack_pak(list(content.items())))
    return _pack_entries(packed, content)


def avatar_deployment(compressed: bytes, avatar_pid: str, x: int, y: int, avatar_jid: str) -> bytes:
    packed = lz10.decompress(compressed)
    entries = pak.read_pak_entries(packed)
    changed = {}
    found = False
    for entry in entries:
        if not entry.name.startswith("dispos_"):
            continue
        document = dispo.parse_dispo(pak.read_pak_file_content(packed, entry))
        for section in document.sections:
            if not section.is_link:
                section.units.clear()
        if entry.name == "dispos_c.bin":
            player = next((section for section in document.sections
                           if "mikata" in section.name and not section.is_link), None)
            if player is None:
                raise ValueError("The starter deployment has no common player section.")
            unit = dispo.new_unit_values()
            unit[dispo.FIELD["pid"]] = avatar_pid
            unit[dispo.FIELD["jid"]] = avatar_jid
            for field, value in AVATAR_AI.items():
                unit[dispo.FIELD[field]] = value
            for field, value in (("pos_x", x), ("pos_y", y), ("pos2_x", x), ("pos2_y", y)):
                unit[dispo.FIELD[field]] = value
            player.units.append(unit)
            # "_mikata_" invokes reserve-army selection, including a special
            # case for Ike. A dedicated avatar must use direct PID deployment.
            dispo.rename_section_prefix(document, player.name, player.name.replace("mikata", "avatar"))
            found = True
        changed[entry.name] = dispo.build_dispo(document)
    if not found:
        raise ValueError("The starter deployment has no common difficulty file.")
    return _pack_entries(packed, changed)


def opening_source(chapter: int, player_section: str, avatar_pid: str) -> str:
    """Direct avatar deployment and a complete visible tactical-map opening."""
    return ("@export\n"
            "def Opening0():\n"
            "    Comeback()\n"
            "    Fade(1, 0)\n"
            f'    MapLoad("bmap{chapter:02d}")\n'
            f'    InstantDisposFirst("{player_section}")\n'
            f'    InstantUnitFocusByPID("{avatar_pid}")\n'
            "    InstantSetMapCamera(0, 40, 14)\n"
            "    SetOutLink(1)\n"
            "    Fade(2, 500)\n"
            "    FadeWait()\n")


def clean_script(project, chapter: int, player_section: str, avatar_pid: str) -> None:
    """Remove copied story events while retaining a script file the compiler can build on."""
    path = script_sources.chapter_script(project, f"{chapter:02d}")
    if path is None:
        raise ValueError("The newly created chapter has no script.")
    base = read_cmb(path.read_bytes())
    padded = f"{chapter:02d}"
    source = (f"# Generated hub chapter {padded}; Hub setup owns the destination events.\n\n"
              + opening_source(chapter, player_section, avatar_pid))
    compiled = compile_source(source, base=base)
    project.write_keeping_original(path, write_cmb(compiled.script))
    sidecar = script_sources.sidecar_path(project, path)
    sidecar.parent.mkdir(parents=True, exist_ok=True)
    sidecar.write_text(source, encoding="utf-8")


def create_chapter(project, fe8: bytes, source_id: str, chapter: int, title: str,
                   width: int, height: int, avatar_pid: str, start: tuple[int, int], keep_map: bool = False,
                   ground_color: tuple[int, int, int] = DEFAULT_GROUND_COLOR,
                   ground_image: str | Path | None = None, tile_ground_image: bool = False):
    """Create the chapter's data, map, single avatar and clean script. The map is
    a copy of the source chapter's with ``keep_map``, else a flat one of
    ``width`` × ``height`` tiles."""
    if not 0 <= start[0] < width or not 0 <= start[1] < height:
        raise ValueError("The avatar start must be inside the map.")
    source = chapters.chapter_paths(project, source_id)
    if source.map is None or source.deployment is None or source.script is None:
        raise ValueError("The starter chapter needs a map, deployment and script.")
    if len(chapters.chapter_phases(project, source_id)) != 1:
        raise ValueError("Choose a chapter with one map phase as the starter.")
    image = None
    if not keep_map and ground_image:
        try:
            with Image.open(ground_image) as opened:
                image = opened.convert("RGBA").copy()
        except Exception as exc:  # noqa: BLE001 - Pillow reports format and file errors through several types
            raise ValueError(f"Could not read the hub ground image: {exc}") from exc
    map_bytes = source.map.read_bytes() if keep_map else blank_map(
        source.map.read_bytes(), width, height, ground_color=ground_color,
        ground_image=image, tile_ground_image=tile_ground_image)
    renumbered_deployment = chapters._renumber_dispos(source.deployment.read_bytes(),
                                                      source_id.zfill(2), f"{chapter:02d}")
    deployment_bytes = avatar_deployment(renumbered_deployment, avatar_pid, *start,
                                        avatar_class(fe8, avatar_pid))
    packed_deployment = lz10.decompress(deployment_bytes)
    common = next((entry for entry in pak.read_pak_entries(packed_deployment)
                   if entry.name == "dispos_c.bin"), None)
    player_section = next((section.name for section in dispo.parse_dispo(
        pak.read_pak_file_content(packed_deployment, common)).sections
        if "_avatar_" in section.name and not section.is_link), None) if common else None
    if player_section is None:
        raise ValueError("The prepared deployment has no player section.")
    plan = chapters.add_story_chapter(project, fe8, source_id, chapter, title, after=None)
    paths = chapters.chapter_paths(project, f"{chapter:02d}")
    project.write_keeping_original(paths.map, map_bytes)
    project.write_keeping_original(paths.deployment, deployment_bytes)
    project.write_keeping_original(paths.dialogue, message.write_messages([]))
    clean_script(project, chapter, player_section, avatar_pid)
    return plan
