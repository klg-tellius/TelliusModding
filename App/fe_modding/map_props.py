"""Props on a chapter map: export, import, replace and place.

A prop is a static model in ``zmap/<map>/map.cmp`` (``<name>.gs`` with a
one-bone ``<name>.g``, textures in the shared ``texpack.tpl``) described by
one ``mapbuilddesc`` record and placed by ``mapbuildinst`` records.

- Model coordinates: one tile is 5 units; the placed tile's corner is the
  origin and the model turns around the tile centre ``(2.5, 2.5)``.
- ``mapbuilddesc`` holds the model's bounding box: ``offset`` its minimum
  corner, ``size`` its maximum corner.
- ``mapbuildinst`` holds the tile, an angle byte (``degrees = 360 - angle *
  360 / 256``), the tiles the object covers after rotation, and a height
  float (``pos_y = -5 * height``); :func:`place_prop` sets the height to the
  terrain surface at the tile centre, as vanilla props sit.

A prop does not change what its tiles are for movement: the tiles' terrain
types (``map_file.set_tile_terrains``) do.
"""

from __future__ import annotations

import io
import json
import struct
from dataclasses import dataclass, replace
from pathlib import Path

import numpy as np

from . import map_heights
from .formats import animation, gltf_export, gltf_import, gs_file, lz10, map_file, model, pak, skeleton, tpl

#: Material names the map loader gives projected-texture callbacks.
CALLBACK_MATERIALS = frozenset(
    {"map_base", "map_wall", "map_water", "kbground", "kbground0", "kbground1", "kbground2", "kbground3", "kbwater"}
)
TEXTURE_SIZE = 512


def read_map_container(path: Path) -> tuple[list[pak.PakEntry], dict[str, bytes]]:
    """A chapter's ``map.cmp`` (LZ10 around a pack) as entries and files."""
    raw = lz10.decompress(Path(path).read_bytes())
    entries = pak.read_pak_entries(raw)
    return entries, {e.name: pak.read_pak_file_content(raw, e) for e in entries}


def texpack_name(files: dict[str, bytes]) -> str:
    name = next((n for n in files if n.lower() == "texpack.tpl"), None)
    if name is None:
        raise gltf_import.GltfImportError("This map has no texpack.tpl.")
    return name


def used_texture_ids(files: dict[str, bytes], skip: set[str] = frozenset()) -> set[int]:
    """Texture ids used by every model in the pack except ``skip`` names."""
    return {
        t.tex_id
        for n, d in files.items()
        if n.lower().endswith(".gs") and n not in skip
        for m in gs_file.read_gs(d).materials
        for t in m.textures
    }


def compact_texpack(files: dict[str, bytes]) -> tuple[int, int]:
    """Drop every ``texpack.tpl`` image no model of the pack uses and
    renumber the texture ids of every model to match; the kept images keep
    their order and bytes. Returns ``(images removed, bytes saved)``."""
    name = texpack_name(files)
    count = len(tpl.read_tpl_image_info(io.BytesIO(files[name])))
    used = used_texture_ids(files)
    keep = [i for i in range(count) if i in used]
    if len(keep) == count:
        return 0, 0
    before = len(files[name])
    files[name] = tpl.select_images(files[name], keep)
    mapping = {old: new for new, old in enumerate(keep) if old != new}
    for file_name in [n for n in files if n.lower().endswith(".gs")]:
        files[file_name] = gs_file.remap_texture_ids(files[file_name], mapping)
    return count - len(keep), before - len(files[name])


def _place_images(files: dict[str, bytes], gs: gs_file.GsFile, images: list, base: int) -> None:
    """Put a build's images into ``texpack.tpl`` and point ``gs`` at them:
    an image identical to one already there (a re-imported export) reuses
    it, the others are appended. The build numbered them from ``base``."""
    name = texpack_name(files)
    existing = tpl.read_tpl_images(io.BytesIO(files[name]))
    pixels = [(e.size, e.convert("RGBA").tobytes()) for e in existing]
    ids: dict[int, int] = {}
    new = []
    for k, image in enumerate(images):
        key = (image.size, image.convert("RGBA").tobytes())
        if key in pixels:
            ids[base + k] = pixels.index(key)
        else:
            new.append(k)
    if new:
        added = [(*gltf_import.texture_for_tpl(images[k], TEXTURE_SIZE), tpl.WRAP_REPEAT) for k in new]
        files[name], first = tpl.append_images(files[name], added, tpl.typical_mip_count(files[name]))
        ids.update({base + k: first + j for j, k in enumerate(new)})
    for material in gs.materials:
        material.textures = [replace(t, tex_id=ids.get(t.tex_id, t.tex_id)) for t in material.textures]


def prop_names(files: dict[str, bytes], data: map_file.MapData) -> list[str]:
    """Placeable objects that have a model: every non-terrain object's name."""
    return [o.filename for o in data.build_desc if not map_file.is_base_terrain_object(o) and f"{o.filename}.gs" in files]


#: ``mapbuilddesc`` flag byte c bit 1: ``load_map_data`` loads ``<name>.ga``
#: onto the object's actor (``gactor_update_map_sprite_resource``) when set.
FLAG_C_ANIMATED = 0x02


def export_prop_glb(files: dict[str, bytes], name: str) -> bytes:
    """A prop's model as ``.glb`` in its own coordinates, with the first
    texture of each material; an animated prop (a ``.ga`` with bone tracks)
    comes with its skeleton and animation."""
    gs_model = model.read_model_bytes(files[f"{name}.gs"])
    used = {m.textures[0].tex_id for m in gs_model.materials if m.textures}
    images = tpl.read_tpl_images(io.BytesIO(files[texpack_name(files)]))
    textures = {i: image for i, image in enumerate(images) if i in used}
    bones, animations = [], []
    ga = files.get(f"{name}.ga")
    if ga is not None and f"{name}.g" in files:
        anim = animation.read_animation_bytes(ga)
        if anim.curves:
            bones = skeleton.read_skeleton(io.BytesIO(files[f"{name}.g"]))
            animations = [(name, anim)]
    return gltf_export.export_glb([(name, gs_model)], bones, textures, animations)


def _animated_build(gltf_data: bytes, name: str, base_dir: Path | None, loop: bool):
    """``(build, .g bytes, .ga bytes, warnings)`` for a skinned, animated
    glTF: a new skeleton in the map-model convention vanilla animated props
    use (``none`` root, pivot bones, multi-matrix shapes), the mesh weighted
    to it and the glTF's first animation, looping when ``loop``."""
    new_skeleton, warnings = gltf_import.build_skeleton(gltf_data, base_dir)
    g_bytes = skeleton.write_skeleton_file(new_skeleton)
    names = gltf_import.list_animations(gltf_data, base_dir)
    ga, anim_warnings = gltf_import.import_animation(gltf_data, g_bytes, animation_name=names[0], base_dir=base_dir)
    warnings += anim_warnings
    if len(names) > 1:
        warnings.append(f"The glTF has {len(names)} animations; the prop plays the first, {names[0]}.")
    anim = animation.read_animation_bytes(ga)
    words = list(anim.header.words)
    if loop:
        words[4], words[5] = 1, 0  # loop flag, loop start frame
    anim = animation.GaAnimation(animation.GaHeader(tuple(words)), anim.groups, anim.curves, anim.events, anim.footer)
    ga = animation.write_animation(anim)
    build = gltf_import.import_skinned_build(gltf_data, g_bytes, base_dir=base_dir, name=name, animations=(anim,))
    warnings.append(
        f"Animated prop: {len(new_skeleton.bones)} bones, {names[0]} over {words[6]} frames"
        + (", looping." if loop else ", played once.")
    )
    return build, g_bytes, ga, warnings + list(build.warnings)


def _one_bone_skeleton(files: dict[str, bytes], data: map_file.MapData) -> bytes:
    """A prop skeleton to copy: vanilla props use one identity bone."""
    for o in data.build_desc:
        g = files.get(f"{o.filename}.g")
        if g is not None and not map_file.is_base_terrain_object(o):
            return g
    for o in data.build_desc:
        g = files.get(f"{o.filename}.g")
        if g is not None:
            return g
    raise gltf_import.GltfImportError("No model skeleton in this map to copy.")


def import_prop(
    entries: list[pak.PakEntry],
    files: dict[str, bytes],
    gltf_data: bytes,
    name: str,
    base_dir: Path | None = None,
    loop: bool = True,
) -> list[str]:
    """Add the glTF as prop ``name``, or replace prop ``name``'s model when
    it exists. Updates ``entries``/``files`` (the unpacked ``map.cmp``) in
    place and returns warnings.

    A glTF with a skin and an animation becomes an animated prop: its own
    skeleton, the mesh weighted to it, the first animation as ``<name>.ga``
    (looping unless ``loop`` is False) and flag c bit 1 set so the map
    loader plays it. A static glTF over an animated prop drops the ``.ga``
    and the bit."""
    if not name or not all(c.isalnum() or c == "_" for c in name) or not name.isascii():
        raise gltf_import.GltfImportError(f"A prop name is ASCII letters, digits or _ (got {name!r}).")
    data = map_file.read_map_bytes(files["map.bin"])
    existing = next((o for o in data.build_desc if o.filename == name), None)
    if existing is not None and map_file.is_base_terrain_object(existing):
        raise gltf_import.GltfImportError(f"{name} is the map's terrain; use the terrain import.")

    scene = gltf_import.read_gltf(gltf_data, base_dir)
    warnings = list()
    for material in scene.materials:
        if material.name in CALLBACK_MATERIALS:
            warnings.append(f"Material {material.name} renamed {material.name}_mesh.")
            material.name += "_mesh"
    animated = _has_skin_and_animation(gltf_data, base_dir)
    ga_bytes = None
    if animated:
        build, skeleton_bytes, ga_bytes, more = _animated_build(gltf_data, name, base_dir, loop)
        warnings += more
        for material in build.gs.materials:
            if material.name in CALLBACK_MATERIALS:
                material.name += "_mesh"
        _place_images(files, build.gs, build.images, 0)
    else:
        base = len(tpl.read_tpl_image_info(io.BytesIO(files[texpack_name(files)])))
        build = gltf_import.build_static_gs(scene, bone=0, name=name, tex_id_base=base)
        warnings += build.warnings
        _place_images(files, build.gs, build.images, base)
        was_animated = existing is not None and existing.flag_bits_c & FLAG_C_ANIMATED
        skeleton_bytes = (files.get(f"{name}.g") if not was_animated else None) or _one_bone_skeleton(files, data)
        if f"{name}.ga" in files:
            del files[f"{name}.ga"]
            entries[:] = [e for e in entries if e.name != f"{name}.ga"]
    written = [(f"{name}.gs", gs_file.write_gs(build.gs)), (f"{name}.g", skeleton_bytes)]
    if ga_bytes is not None:
        written.append((f"{name}.ga", ga_bytes))
    for file_name, content in written:
        if file_name not in files:
            entries.append(pak.PakEntry(file_name, 0, 0))
        files[file_name] = content
    # The replaced model's images, if no other model uses them, go.
    compact_texpack(files)

    lo, hi = build.gs.bbox_min, build.gs.bbox_max
    bounds = {"offset_x": lo[0], "offset_y": lo[1], "offset_z": lo[2], "size_x": hi[0], "size_y": hi[1], "size_z": hi[2]}
    map_bin = files["map.bin"]
    flag_c = 1 | (FLAG_C_ANIMATED if animated else 0)
    if existing is None:
        obj = map_file.MapObject(**bounds, flag_bits_a=0, flag_bits_b=0, flag_bits_c=flag_c, effect_type=0, filename=name)
        map_bin, _index = map_file.add_build_object(map_bin, obj)
    else:
        for field_name, value in bounds.items():
            map_bin = map_file.patch_object_field(map_bin, existing, field_name, float(value))
        new_c = (existing.flag_bits_c & ~FLAG_C_ANIMATED) | (FLAG_C_ANIMATED if animated else 0)
        if new_c != existing.flag_bits_c:
            map_bin = map_file.patch_object_field(map_bin, existing, "flag_bits_c", new_c)
    files["map.bin"] = map_bin
    if max(hi[0] - lo[0], hi[2] - lo[2]) > 60:
        warnings.append("The prop is wider than 12 tiles; props are modelled at 5 units per tile.")
    return warnings


def _has_skin_and_animation(gltf_data: bytes, base_dir: Path | None) -> bool:
    try:
        return bool(gltf_import.list_animations(gltf_data, base_dir)) and _gltf_has_skin(gltf_data)
    except gltf_import.GltfImportError:
        return False


def _gltf_has_skin(gltf_data: bytes) -> bool:
    if gltf_data[:4] == b"glTF":
        length = struct.unpack_from("<I", gltf_data, 12)[0]
        doc = json.loads(gltf_data[20 : 20 + length])
    else:
        doc = json.loads(gltf_data)
    return bool(doc.get("skins"))


def terrain_triangles(files: dict[str, bytes], data: map_file.MapData) -> np.ndarray:
    """The land terrain's triangles, for placing props on its surface."""
    for o in data.build_desc:
        if map_file.is_base_terrain_object(o) and "water" not in o.filename.lower() and f"{o.filename}.gs" in files:
            m = model.read_model_bytes(files[f"{o.filename}.gs"])
            tris = [
                [v.position for v in (s[k], s[k + 1], s[k + 2])]
                for chunk in m.chunks
                for s in chunk.strips
                for k in range(len(s) - 2)
            ]
            return np.array(tris, dtype=float).reshape(-1, 3, 3)
    return np.zeros((0, 3, 3))


def tile_heights(files: dict[str, bytes], data: map_file.MapData, tiles) -> list[float]:
    """The instance height value (``pos_y = -5 * height``) of the terrain
    surface at the centre of each tile ``(x, y)``; 0 off the terrain."""
    terrain = next((o.filename for o in data.build_desc if map_file.is_base_terrain_object(o) and "water" not in o.filename.lower()), "")
    ox, oy = map_heights.terrain_origin(data, terrain)
    centres = [(map_heights.TILE_SIZE * (x - ox) + 2.5, map_heights.TILE_SIZE * (y - oy) + 2.5) for x, y in tiles]
    surfaces = map_heights.surface_heights(terrain_triangles(files, data), centres)
    return [0.0 if np.isnan(s) else -s / map_heights.TILE_SIZE for s in surfaces]


def place_prop(files: dict[str, bytes], name: str, x: int, y: int, angle: int = 0) -> int:
    """Add an instance of prop ``name`` on tile ``(x, y)`` (placement
    coordinates, the same as the map's tile grid) at the terrain height of
    the tile centre. Returns the new instance's index."""
    data = map_file.read_map_bytes(files["map.bin"])
    index = next((i for i, o in enumerate(data.build_desc) if o.filename == name), None)
    if index is None:
        raise map_file.MapFileError(f"No object {name!r} on this map.")
    (height,) = tile_heights(files, data, [(x, y)])
    records = map_file.instance_records(files["map.bin"])
    records.append(map_file.instance_record(data.build_desc[index], index, x, y, angle, height))
    files["map.bin"] = map_file.set_build_instances(files["map.bin"], records)
    return len(records) - 1


def move_instance(files: dict[str, bytes], index: int, x: int, y: int) -> None:
    """Move instance ``index`` to tile ``(x, y)``. Its covered-tiles
    rectangle moves with it and it keeps its height above the ground (a prop
    raised or sunk on purpose stays so)."""
    data = map_file.read_map_bytes(files["map.bin"])
    inst = data.build_inst[index]
    dx, dy = x - inst.x, y - inst.y
    old_ground, new_ground = tile_heights(files, data, [(inst.x, inst.y), (x, y)])
    height = inst.height() + new_ground - old_ground
    records = map_file.instance_records(files["map.bin"])
    records[index] = struct.pack(
        ">bbBbbbbbf", x, y, inst.angle % 256, inst.desc_index,
        inst.x2 + dx, inst.y2 + dy, inst.end_x2 + dx, inst.end_y2 + dy, height,
    )
    files["map.bin"] = map_file.set_build_instances(files["map.bin"], records)


def rotate_instance(files: dict[str, bytes], index: int, angle: int) -> None:
    """Turn instance ``index`` to ``angle`` (the stored byte: 0, 64, 128,
    192 for quarter turns), recomputing its covered-tiles rectangle."""
    data = map_file.read_map_bytes(files["map.bin"])
    inst = data.build_inst[index]
    records = map_file.instance_records(files["map.bin"])
    records[index] = map_file.instance_record(data.build_desc[inst.desc_index], inst.desc_index, inst.x, inst.y, angle, inst.height())
    files["map.bin"] = map_file.set_build_instances(files["map.bin"], records)


def remove_instance(files: dict[str, bytes], index: int) -> None:
    records = map_file.instance_records(files["map.bin"])
    del records[index]
    files["map.bin"] = map_file.set_build_instances(files["map.bin"], records)


# -- props of every map --------------------------------------------------------------


@dataclass(frozen=True)
class PropInfo:
    """One prop of one map, for the catalog of every map's props."""

    map_name: str
    path: Path
    name: str
    obj: map_file.MapObject
    instances: int
    animated: bool

    @property
    def footprint(self) -> tuple[int, int]:
        return map_file.footprint_tiles(self.obj)


_catalog_cache: dict[Path, tuple[tuple[int, int], list[PropInfo]]] = {}


def map_paths(extracted_dir: Path) -> list[Path]:
    """Every chapter map (``zmap/<map>/map.cmp``) of an extracted disc."""
    return sorted(Path(extracted_dir).glob("**/zmap/*/map.cmp"))


def map_props_info(path: Path) -> list[PropInfo]:
    """The props of one ``map.cmp``, cached until the file changes."""
    path = Path(path)
    stat = path.stat()
    stamp = (stat.st_mtime_ns, stat.st_size)
    cached = _catalog_cache.get(path)
    if cached is not None and cached[0] == stamp:
        return cached[1]
    _entries, files = read_map_container(path)
    data = map_file.read_map_bytes(files["map.bin"])
    counts: dict[int, int] = {}
    for inst in data.build_inst:
        counts[inst.desc_index] = counts.get(inst.desc_index, 0) + 1
    names = set(prop_names(files, data))
    props = [
        PropInfo(path.parent.name, path, o.filename, o, counts.get(i, 0), f"{o.filename}.ga" in files and map_file.has_ga_animation(o))
        for i, o in enumerate(data.build_desc)
        if o.filename in names
    ]
    _catalog_cache[path] = (stamp, props)
    return props


def prop_catalog(extracted_dir: Path, progress=None) -> list[PropInfo]:
    """Every prop of every map; ``progress(done, total)`` after each map. A
    map that can't be read is skipped."""
    paths = map_paths(extracted_dir)
    props: list[PropInfo] = []
    for k, path in enumerate(paths):
        try:
            props += map_props_info(path)
        except Exception:  # noqa: BLE001 - one broken map must not hide the others
            pass
        if progress is not None:
            progress(k + 1, len(paths))
    return props


def _prop_key(files: dict[str, bytes], name: str) -> tuple:
    """What makes a prop what it is, whatever map holds it: its files (the
    model with its texture ids blanked) and the images it uses, in order."""
    gs = files[f"{name}.gs"]
    offsets = gs_file.texture_id_offsets(gs)
    blank = bytearray(gs)
    ids = []
    for offset in offsets:
        ids.append(struct.unpack_from(">H", gs, offset)[0])
        struct.pack_into(">H", blank, offset, 0)
    keys = tpl.image_keys(files[texpack_name(files)])
    images = tuple(keys[i] if i < len(keys) else i for i in ids)
    return bytes(blank), files.get(f"{name}.g"), files.get(f"{name}.ga"), images


def same_prop(source_files: dict[str, bytes], source_name: str, files: dict[str, bytes], name: str) -> bool:
    """Whether prop ``name`` of ``files`` is prop ``source_name`` of
    ``source_files`` (same model, skeleton, animation and images)."""
    if f"{name}.gs" not in files:
        return False
    return _prop_key(source_files, source_name) == _prop_key(files, name)


def free_prop_name(files: dict[str, bytes], data: map_file.MapData, name: str) -> str:
    """``name``, or ``name_2``, ``name_3``... if the map already uses it."""
    used = {o.filename for o in data.build_desc} | {n.rsplit(".", 1)[0] for n in files}
    candidate, k = name, 2
    while candidate in used:
        candidate, k = f"{name}_{k}", k + 1
    return candidate


def copy_prop(
    source_files: dict[str, bytes],
    source_name: str,
    entries: list[pak.PakEntry],
    files: dict[str, bytes],
    name: str | None = None,
) -> str:
    """Copy prop ``source_name`` of another map (its unpacked ``map.cmp``)
    into ``entries``/``files`` as prop ``name`` (default: the same name):
    its model, skeleton and animation, its ``mapbuilddesc`` record (bounds,
    flags, effect type) and the ``texpack.tpl`` images it uses, byte for
    byte (an image the map already has is shared). Returns the name."""
    name = name or source_name
    if not name or not all(c.isalnum() or c == "_" for c in name) or not name.isascii():
        raise map_file.MapFileError(f"A prop name is ASCII letters, digits or _ (got {name!r}).")
    source_data = map_file.read_map_bytes(source_files["map.bin"])
    obj = next((o for o in source_data.build_desc if o.filename == source_name), None)
    if obj is None or f"{source_name}.gs" not in source_files or map_file.is_base_terrain_object(obj):
        raise map_file.MapFileError(f"{source_name} is not a prop of that map.")
    data = map_file.read_map_bytes(files["map.bin"])
    if any(o.filename == name for o in data.build_desc) or f"{name}.gs" in files:
        raise map_file.MapFileError(f"This map already has an object named {name}.")

    gs = source_files[f"{source_name}.gs"]
    used = sorted({struct.unpack_from(">H", gs, offset)[0] for offset in gs_file.texture_id_offsets(gs)})
    source_tpl = source_files[texpack_name(source_files)]
    source_keys = tpl.image_keys(source_tpl)
    target_name = texpack_name(files)
    target_keys = tpl.image_keys(files[target_name])
    mapping: dict[int, int] = {}
    new: list[int] = []
    for tex_id in used:
        if tex_id >= len(source_keys):
            continue
        if source_keys[tex_id] in target_keys:
            mapping[tex_id] = target_keys.index(source_keys[tex_id])
        else:
            new.append(tex_id)
    if new:
        files[target_name], first = tpl.copy_images(files[target_name], source_tpl, new)
        mapping.update({tex_id: first + k for k, tex_id in enumerate(new)})

    written = {f"{name}.gs": gs_file.remap_texture_ids(gs, mapping)}
    for ext in ("g", "ga"):
        if f"{source_name}.{ext}" in source_files:
            written[f"{name}.{ext}"] = source_files[f"{source_name}.{ext}"]
    for file_name, content in written.items():
        if file_name not in files:
            entries.append(pak.PakEntry(file_name, 0, 0))
        files[file_name] = content
    files["map.bin"], _index = map_file.add_build_object(files["map.bin"], replace(obj, filename=name))
    return name


# -- water ---------------------------------------------------------------------------

#: Map flag (``mapextra`` tail word, map state ``+0x64``) that installs the
#: ``map_water`` multi-pass callback (``setup_map_texture_material_callbacks``);
#: set on every vanilla map with water and on none without.
MAP_FLAG_WATER = 0x20
#: A water object's ``mapbuilddesc`` flags and type byte on every vanilla map.
WATER_FLAGS = (0xC0, 0x00, 0x02)
WATER_EFFECT_TYPE = 154
#: Terrain types a water surface normally covers (river, sea, waterway, pond, moat).
WATER_TERRAINS = frozenset({"川", "海", "水路", "池", "堀"})


def water_names(files: dict[str, bytes], data: map_file.MapData) -> list[str]:
    """Water objects: base objects whose model has a ``map_water`` material."""
    names = []
    for o in data.build_desc:
        gs = files.get(f"{o.filename}.gs")
        if gs is not None and map_file.is_base_terrain_object(o) and o.filename not in names:
            if any(m.name == "map_water" for m in gs_file.read_gs(gs).materials):
                names.append(o.filename)
    return names


def _water_triangles(gs_bytes: bytes) -> np.ndarray:
    m = model.read_model_bytes(gs_bytes)
    tris = [[v.position for v in (s[k], s[k + 1], s[k + 2])] for c in m.chunks for s in c.strips for k in range(len(s) - 2)]
    return np.array(tris, dtype=float).reshape(-1, 3, 3)


def water_terrain_mismatch(files: dict[str, bytes]) -> tuple[int, int]:
    """``(tiles covered by water whose terrain type is not a water type,
    water-type tiles no water covers)`` over the whole map grid."""
    data = map_file.read_map_bytes(files["map.bin"])
    grid = map_file.terrain_grid(files["map.bin"])
    names = water_names(files, data)
    if grid is None:
        return 0, 0
    terrain = next((o.filename for o in data.build_desc if map_file.is_base_terrain_object(o) and o.filename not in names), "")
    ox, oy = map_heights.terrain_origin(data, terrain)
    tris = [_water_triangles(files[f"{n}.gs"]) for n in names]
    tris = np.concatenate(tris) if tris else np.zeros((0, 3, 3))
    cells = [(x, y) for x in range(len(grid)) for y in range(len(grid[0]))]
    centres = [(map_heights.TILE_SIZE * (x - ox) + 2.5, map_heights.TILE_SIZE * (y - oy) + 2.5) for x, y in cells]
    covered = ~np.isnan(map_heights.surface_heights(tris, centres)) if len(tris) else np.zeros(len(cells), bool)
    dry = sum(1 for (x, y), c in zip(cells, covered) if c and grid[x][y] not in WATER_TERRAINS)
    uncovered = sum(1 for (x, y), c in zip(cells, covered) if not c and grid[x][y] in WATER_TERRAINS)
    return dry, uncovered


def import_water(
    entries: list[pak.PakEntry],
    files: dict[str, bytes],
    gltf_data: bytes,
    name: str | None = None,
    base_dir: Path | None = None,
    donor: dict[str, bytes] | None = None,
) -> list[str]:
    """Replace water object ``name`` with the glTF surface, or, when the map
    has no water, add ``<map>_water0`` built from ``donor`` (another map's
    unpacked ``map.cmp``: its water ``.g``, ``.ga`` scroll animation and two
    water images are copied). Model the surface in the terrain's
    coordinates (5 units per tile from the terrain's corner; vanilla water
    sits at y = -2). Every material becomes ``map_water``, keeping the water
    material's colours (alpha 127) and texture records; a glTF image
    replaces the first record's image. Returns warnings."""
    data = map_file.read_map_bytes(files["map.bin"])
    waters = water_names(files, data)
    warnings: list[str] = []
    texpack = texpack_name(files)
    if name is None:
        name = waters[0] if waters else None
    if name is not None and name in waters:
        source_files, source_name, new = files, name, False
    else:
        if donor is None:
            raise gltf_import.GltfImportError("This map has no water: pick a map with water to copy its animation and textures from.")
        donor_data = map_file.read_map_bytes(donor["map.bin"])
        donor_waters = water_names(donor, donor_data)
        if not donor_waters:
            raise gltf_import.GltfImportError("The chosen map has no water either.")
        terrain = next((o.filename for o in data.build_desc if map_file.is_base_terrain_object(o)), None)
        if terrain is None:
            raise gltf_import.GltfImportError("This map has no base terrain object.")
        name = name or f"{terrain}_water0"
        source_files, source_name, new = donor, donor_waters[0], True
    if not all(c.isalnum() or c == "_" for c in name) or not name.isascii():
        raise gltf_import.GltfImportError(f"A water name is ASCII letters, digits or _ (got {name!r}).")

    source_material = next(m for m in gs_file.read_gs(source_files[f"{source_name}.gs"]).materials if m.name == "map_water")
    records = [replace(t) for t in source_material.textures]
    if new:  # the donor's water images go after this map's images
        donor_tpl = source_files[texpack_name(source_files)]
        donor_images = tpl.read_tpl_images(io.BytesIO(donor_tpl))
        donor_info = tpl.read_tpl_image_info(io.BytesIO(donor_tpl))
        ids = sorted({t.tex_id for t in records})
        added = [
            (donor_images[i], donor_info[i].format if donor_info[i].format in tpl._DIRECT_ENCODERS else tpl.FORMAT_RGBA8,
             tpl.WRAP_REPEAT)
            for i in ids
        ]
        files[texpack], first = tpl.append_images(files[texpack], added, tpl.typical_mip_count(donor_tpl))
        records = [replace(t, tex_id=first + ids.index(t.tex_id)) for t in records]

    scene = gltf_import.read_gltf(gltf_data, base_dir)
    base = len(tpl.read_tpl_image_info(io.BytesIO(files[texpack])))
    build = gltf_import.build_static_gs(scene, bone=0, name=name, tex_id_base=base)
    warnings += build.warnings
    _place_images(files, build.gs, build.images, base)
    for material in build.gs.materials:
        own = [t for t in material.textures]
        material.name = "map_water"
        material.color0, material.color1, material.color2 = source_material.color0, source_material.color1, source_material.color2
        material.unk0, material.unk1 = source_material.unk0, source_material.unk1
        material.textures = [replace(t) for t in records]
        if own and records:
            material.textures[0] = replace(records[0], tex_id=own[0].tex_id)
    if len(build.gs.materials) > 1:
        warnings.append(f"{len(build.gs.materials)} materials: each becomes map_water with the water textures.")

    for file_name, content in (
        (f"{name}.gs", gs_file.write_gs(build.gs)),
        (f"{name}.g", source_files[f"{source_name}.g"]),
        (f"{name}.ga", source_files[f"{source_name}.ga"]),
    ):
        if file_name not in files:
            entries.append(pak.PakEntry(file_name, 0, 0))
        files[file_name] = content
    compact_texpack(files)

    lo, hi = build.gs.bbox_min, build.gs.bbox_max
    bounds = {"offset_x": lo[0], "offset_y": lo[1], "offset_z": lo[2], "size_x": hi[0], "size_y": hi[1], "size_z": hi[2]}
    map_bin = files["map.bin"]
    if new:
        a, b, c = WATER_FLAGS
        obj = map_file.MapObject(**bounds, flag_bits_a=a, flag_bits_b=b, flag_bits_c=c, effect_type=WATER_EFFECT_TYPE, filename=name)
        map_bin, index = map_file.add_build_object(map_bin, obj)
        data = map_file.read_map_bytes(map_bin)
        extra = data.extra
        records_out = map_file.instance_records(map_bin)
        records_out.append(map_file.instance_record(data.build_desc[index], index, -extra.panel_offset_x, -extra.panel_offset_y, 0, 0.0))
        map_bin = map_file.set_build_instances(map_bin, records_out)
        extra = map_file.read_map_bytes(map_bin).extra
        if not extra.unknown_tail & MAP_FLAG_WATER:
            map_bin = map_file.patch_extra_field(map_bin, extra, "unknown_tail", extra.unknown_tail | MAP_FLAG_WATER)
            warnings.append("The map's water flag (0x20) was set so the game animates the new water.")
    else:
        existing = next(o for o in data.build_desc if o.filename == name)
        for field_name, value in bounds.items():
            map_bin = map_file.patch_object_field(map_bin, existing, field_name, float(value))
    files["map.bin"] = map_bin
    dry, uncovered = water_terrain_mismatch(files)
    if dry or uncovered:
        warnings.append(
            f"{dry} tiles under the water are not a water terrain type, and {uncovered} water-type tiles have no water "
            "over them: paint them with the Build tab's Paint terrain tool (River, Sea...) so movement matches."
        )
    return warnings


#: Footer slot of a water ``.ga`` holding its scroll table.
WATER_SCROLL_SLOT = 3
#: ``interpolate_animation_channel_uv_scale_u`` multiplies a stored value by this.
WATER_SCROLL_SCALE = 0.001


def water_scroll(ga: bytes) -> tuple[float, float, float, float] | None:
    """The four scroll values of a water ``.ga`` (footer slot 3): the
    ``map_water`` callback reads channel 0 at keys 0-3 and scales each by
    0.001 - the two textures' scroll speeds, ``(u1, v1, u2, v2)``, times the
    map's clock. ``None`` when the slot is missing (the game then uses
    1.0, 0.5, 0.5, 1.0)."""
    anim = animation.read_animation_bytes(ga)
    block = anim.footer.blocks[WATER_SCROLL_SLOT] if anim.footer else None
    if block is None:
        return None
    offset = struct.unpack_from(">H", block, 8)[0]  # channel 0's track
    count, _mode = struct.unpack_from(">HH", block, offset)
    keys = dict(struct.unpack_from(">Hh", block, offset + 4 + 4 * k) for k in range(count))
    return tuple(keys.get(k, 0) * WATER_SCROLL_SCALE for k in range(4))  # type: ignore[return-value]


def set_water_scroll(ga: bytes, values: tuple[float, float, float, float]) -> bytes:
    """``ga`` with its scroll table (keys 0-3 of channel 0) set to ``values``
    (each -32.768 to 32.767); the block keeps the vanilla layout: channel
    count 1, a runtime pointer word, the track offset, then a step track of
    four ``(key, value)`` pairs."""
    anim = animation.read_animation_bytes(ga)
    if anim.footer is None or anim.footer.blocks[WATER_SCROLL_SLOT] is None:
        raise ValueError("This animation has no water scroll table (footer slot 3).")
    raw = [round(v / WATER_SCROLL_SCALE) for v in values]
    if any(not -32768 <= r <= 32767 for r in raw):
        raise ValueError("Scroll values run from -32.768 to 32.767.")
    track = struct.pack(">HH", 4, 1) + b"".join(struct.pack(">Hh", k, r) for k, r in enumerate(raw))
    block = struct.pack(">HHIH", 1, 0, 0, 10) + track
    block += bytes(-len(block) % 4)
    anim.footer.blocks[WATER_SCROLL_SLOT] = block
    return animation.write_animation(anim)

