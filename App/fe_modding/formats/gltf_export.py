"""Export ``.gs`` meshes, a ``.g`` skeleton, and ``.ga`` animations to a
binary glTF 2.0 (``.glb``) file.

This is not a game-format module: it is the app's bridge to external 3D
tools (Blender imports ``.glb`` natively) and the round-trip partner of
:mod:`gltf_import`. The rig and the animations follow the engine exactly
(:mod:`engine_pose`):

- Joint ``b`` sits at the bone's rest rotate pivot: its world matrix is
  ``world[b] x T(pivot[b])``, its node transform the parent-relative
  version of that (:func:`engine_pose.joint_local`), and its inverse bind
  matrix ``T(-pivot[b]) x skin_matrix[b]``. glTF skinning then reproduces
  the engine's ``world x skin_matrix`` palette for every frame.
- Vertex positions are the stored ones for multi-matrix and composite
  shapes. A single-matrix shape is drawn with ``world[b]`` alone, so its
  vertices are exported as ``skin_matrix[b]^-1 x stored``; either way the
  mesh deforms exactly as in the game. In the rest pose (the bones'
  ``+0xBC`` seed) a prop's shapes appear where the game places them
  unanimated.
- Animations are sampled once per game frame with :mod:`engine_pose`, from
  frame 0 to the header's end frame, and written as linear translation,
  rotation and (when used) scale channels at ``fps`` frames per second.
  Each animation's ``extras`` carry the event track and loop settings
  (``events``: ``[frame, [codes]]`` pairs, ``loops``, ``loop_start``,
  ``end_frame``) so :func:`gltf_import.import_animation` can keep them.
- GX triangle strips are unrolled and reversed to glTF's counter-clockwise
  front face (GX's front face is clockwise). A material is double-sided
  when any shape using it has cull bits ``0x1800`` (cull nothing); shapes
  with ``0x1000`` cull back faces (see :mod:`gltf_import`).
"""

from __future__ import annotations

import io
import json
import math
import struct
from dataclasses import dataclass, field, replace
from typing import Optional

from PIL import Image

from . import animation, engine_pose, model, skeleton

_FLOAT, _UNSIGNED_SHORT, _UNSIGNED_BYTE, _UNSIGNED_INT = 5126, 5123, 5121, 5125
_ARRAY_BUFFER, _ELEMENT_ARRAY_BUFFER = 34962, 34963
_REPEAT = 10497


@dataclass
class _Builder:
    buffer: bytearray = field(default_factory=bytearray)
    buffer_views: list = field(default_factory=list)
    accessors: list = field(default_factory=list)

    def view(self, data: bytes, target: Optional[int] = None) -> int:
        while len(self.buffer) % 4:
            self.buffer.append(0)
        view = {"buffer": 0, "byteOffset": len(self.buffer), "byteLength": len(data)}
        if target is not None:
            view["target"] = target
        self.buffer += data
        self.buffer_views.append(view)
        return len(self.buffer_views) - 1

    def accessor(self, values: list, kind: str, component: int, *, target=None, normalized=False, bounds=False) -> int:
        width = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4, "MAT4": 16}[kind]
        code = {_FLOAT: "f", _UNSIGNED_SHORT: "H", _UNSIGNED_BYTE: "B", _UNSIGNED_INT: "I"}[component]
        flat = [x for v in values for x in (v if width > 1 else (v,))]
        data = struct.pack(f"<{len(flat)}{code}", *flat)
        if component in (_UNSIGNED_BYTE, _UNSIGNED_SHORT) and width > 1:
            # glTF requires each vertex-attribute element to start on a 4-byte boundary.
            elem = struct.calcsize(code) * width
            stride = (elem + 3) & ~3
            if stride != elem:
                padded = bytearray()
                for i in range(len(values)):
                    padded += data[i * elem : (i + 1) * elem] + bytes(stride - elem)
                data = bytes(padded)
        acc = {
            "bufferView": self.view(data, target),
            "componentType": component,
            "count": len(values),
            "type": kind,
        }
        if normalized:
            acc["normalized"] = True
        if bounds and values:
            cols = list(zip(*values)) if width > 1 else [values]
            acc["min"] = [min(c) for c in cols]
            acc["max"] = [max(c) for c in cols]
        self.accessors.append(acc)
        return len(self.accessors) - 1


def _quat_from_matrix(m) -> tuple[float, float, float, float]:
    """(x, y, z, w) unit quaternion for a row-major 3x3 rotation matrix."""
    (m00, m01, m02), (m10, m11, m12), (m20, m21, m22) = m
    trace = m00 + m11 + m22
    if trace > 0:
        s = math.sqrt(trace + 1.0) * 2
        q = ((m21 - m12) / s, (m02 - m20) / s, (m10 - m01) / s, 0.25 * s)
    elif m00 > m11 and m00 > m22:
        s = math.sqrt(1.0 + m00 - m11 - m22) * 2
        q = (0.25 * s, (m01 + m10) / s, (m02 + m20) / s, (m21 - m12) / s)
    elif m11 > m22:
        s = math.sqrt(1.0 + m11 - m00 - m22) * 2
        q = ((m01 + m10) / s, 0.25 * s, (m12 + m21) / s, (m02 - m20) / s)
    else:
        s = math.sqrt(1.0 + m22 - m00 - m11) * 2
        q = ((m02 + m20) / s, (m12 + m21) / s, 0.25 * s, (m10 - m01) / s)
    n = math.sqrt(sum(c * c for c in q)) or 1.0
    return tuple(c / n for c in q)  # type: ignore[return-value]


def _mat4(m: skeleton.Mat3x4) -> list[float]:
    """Column-major glTF 4x4 of a row-major 3x4 affine matrix."""
    rows = [list(m[0]), list(m[1]), list(m[2]), [0.0, 0.0, 0.0, 1.0]]
    return [rows[r][c] for c in range(4) for r in range(4)]


def _normalize(v) -> tuple[float, float, float]:
    n = math.sqrt(sum(c * c for c in v))
    return (v[0] / n, v[1] / n, v[2] / n) if n > 1e-9 else (0.0, 1.0, 0.0)


def _strip_triangles(strip):
    """Strip triangles in glTF winding (counter-clockwise front): the game's
    front face is clockwise (see :mod:`gltf_import`), so each game triangle
    is reversed."""
    for i in range(len(strip) - 2):
        a, b, c = strip[i], strip[i + 1], strip[i + 2]
        yield (a, c, b) if i % 2 == 0 else (b, c, a)


def _single_matrix_placement(chunk: model.TriChunk, bones: list[skeleton.Bone]):
    """Vertex mapper for one chunk. The engine draws a single-matrix shape
    (no multi-matrix or composite flag) with ``world[bone]`` while the glTF
    joint applies ``world[bone] x skin_matrix[bone]``, so its vertices are
    exported as ``skin_matrix^-1 x stored``; other shapes are kept as stored."""
    if chunk.format & 3 or not 0 <= chunk.bone < len(bones):
        return lambda v: v
    skin = engine_pose.skin_matrix(bones[chunk.bone])
    if skin == skeleton.IDENTITY_3X4:
        return lambda v: v
    inverse = engine_pose.invert_3x4(skin)

    def place(v: model.StripVertex) -> model.StripVertex:
        # normals take the inverse-transpose of skin^-1, i.e. skin's transpose
        n = v.normal
        normal = tuple(skin[0][r] * n[0] + skin[1][r] * n[1] + skin[2][r] * n[2] for r in range(3))
        return replace(v, position=engine_pose.apply(inverse, v.position), normal=normal)

    return place


def export_glb(
    gs_models: list[tuple[str, model.GsModel]],
    bones: Optional[list[skeleton.Bone]] = None,
    textures: Optional[dict[int, Image.Image]] = None,
    animations: Optional[list[tuple[str, animation.GaAnimation]]] = None,
    fps: float = 60.0,
) -> bytes:
    """Build a ``.glb``. ``gs_models`` are ``(name, model)`` pairs sharing
    the one skeleton; ``textures`` maps a material ``tex_id`` to its decoded
    image (the caller decides that mapping - see ``model_viewer``)."""
    bones = bones or []
    textures = textures or {}
    animations = animations or []
    b = _Builder()
    gltf: dict = {
        "asset": {"version": "2.0", "generator": "Tellius Modding"},
        "scene": 0,
        "scenes": [{"nodes": []}],
        "nodes": [],
        "meshes": [],
        "materials": [],
    }
    nodes, scene_nodes = gltf["nodes"], gltf["scenes"][0]["nodes"]

    # Skeleton nodes (node index == bone index), in the rest (+0xBC seed) pose.
    seed = engine_pose.local_matrices(bones)
    for i, bone in enumerate(bones):
        nodes.append({"name": bone.name or f"bone_{i}", **_node_trs(engine_pose.joint_local(bones, i, seed[i]))})
    for i, bone in enumerate(bones):
        if 0 <= bone.parent_index < len(bones):
            nodes[bone.parent_index].setdefault("children", []).append(i)
        else:
            scene_nodes.append(i)

    # Textures.
    image_index: dict[int, int] = {}
    if textures:
        gltf["images"], gltf["textures"] = [], []
        gltf["samplers"] = [{"wrapS": _REPEAT, "wrapT": _REPEAT}]
        for tex_id, image in sorted(textures.items()):
            png = io.BytesIO()
            image.convert("RGBA").save(png, format="PNG")
            gltf["images"].append({"bufferView": b.view(png.getvalue()), "mimeType": "image/png", "name": f"tex_{tex_id}"})
            gltf["textures"].append({"source": len(gltf["images"]) - 1, "sampler": 0})
            image_index[tex_id] = len(gltf["textures"]) - 1

    for model_name, gs in gs_models:
        material_ids: dict[int, int] = {}
        primitives = []
        by_material: dict[int, list] = {}
        for chunk in gs.chunks:
            if chunk.hidden:  # never drawn by the game
                continue
            place = _single_matrix_placement(chunk, bones)
            for strip in chunk.strips:
                by_material.setdefault(chunk.material_index, []).extend(
                    tuple(place(v) for v in tri) for tri in _strip_triangles(strip)
                )
        model_has_skin = bool(bones) and any(v.bone_indices for t in by_material.values() for tri in t for v in tri)
        double_sided = {c.material_index for c in gs.chunks if (c.format & 0x1800) != 0x1000}
        passes: dict[int, int] = {}
        blend_flags: dict[int, int] = {}
        for c in gs.chunks:
            passes[c.material_index] = max(passes.get(c.material_index, 0), (c.format >> 13 & 3) - 1)
            blend_flags[c.material_index] = blend_flags.get(c.material_index, 0) | (c.format & SHAPE_BLEND_FLAGS)
        for mat_index, tris in by_material.items():
            if mat_index not in material_ids:
                material_ids[mat_index] = _add_material(
                    gltf, gs, mat_index, image_index, model_name, mat_index in double_sided,
                    passes.get(mat_index, 0),
                    blend_flags.get(mat_index, 0),
                )
            keys: dict[tuple, int] = {}
            positions, normals, uvs, colors, joints, weights, indices = [], [], [], [], [], [], []
            uvs2 = []
            has_color = any(v.color is not None for t in tris for v in t)
            has_uv2 = any(v.uv2 is not None for t in tris for v in t)
            has_skin = model_has_skin
            for tri in tris:
                for v in tri:
                    j, w = _vertex_skin(v, len(bones)) if has_skin else ((0, 0, 0, 0), (1.0, 0.0, 0.0, 0.0))
                    key = (v.position, v.normal, v.uv, v.uv2, v.color, j, w)
                    if key not in keys:
                        keys[key] = len(positions)
                        positions.append(tuple(float(c) for c in v.position))
                        normals.append(_normalize(v.normal))
                        uvs.append(tuple(float(c) for c in v.uv))
                        uvs2.append(tuple(float(c) for c in (v.uv2 if v.uv2 is not None else v.uv)))
                        colors.append(tuple(v.color) if v.color is not None else (255, 255, 255, 255))
                        joints.append(j)
                        weights.append(w)
                    indices.append(keys[key])
            attributes = {
                "POSITION": b.accessor(positions, "VEC3", _FLOAT, target=_ARRAY_BUFFER, bounds=True),
                "NORMAL": b.accessor(normals, "VEC3", _FLOAT, target=_ARRAY_BUFFER),
                "TEXCOORD_0": b.accessor(uvs, "VEC2", _FLOAT, target=_ARRAY_BUFFER),
            }
            if has_uv2:  # the second UV set of map terrain (map_base's second texture0 sample)
                attributes["TEXCOORD_1"] = b.accessor(uvs2, "VEC2", _FLOAT, target=_ARRAY_BUFFER)
            if has_color:
                attributes["COLOR_0"] = b.accessor(colors, "VEC4", _UNSIGNED_BYTE, target=_ARRAY_BUFFER, normalized=True)
            if has_skin:
                attributes["JOINTS_0"] = b.accessor(joints, "VEC4", _UNSIGNED_SHORT, target=_ARRAY_BUFFER)
                attributes["WEIGHTS_0"] = b.accessor(weights, "VEC4", _FLOAT, target=_ARRAY_BUFFER)
            index_type = _UNSIGNED_SHORT if len(positions) < 65536 else _UNSIGNED_INT
            primitives.append(
                {
                    "attributes": attributes,
                    "indices": b.accessor(indices, "SCALAR", index_type, target=_ELEMENT_ARRAY_BUFFER),
                    "material": material_ids[mat_index],
                }
            )
        if not primitives:
            continue
        gltf["meshes"].append({"name": model_name, "primitives": primitives})
        mesh_node = {"name": model_name, "mesh": len(gltf["meshes"]) - 1}
        if bones and any("JOINTS_0" in p["attributes"] for p in primitives):
            mesh_node["skin"] = 0
        nodes.append(mesh_node)
        scene_nodes.append(len(nodes) - 1)

    if bones:  # written even without a skinned mesh: the inverse binds define the rig for animation import
        ibm = b.accessor([_mat4(engine_pose.inverse_bind(bone)) for bone in bones], "MAT4", _FLOAT)
        roots = [i for i, bone in enumerate(bones) if not 0 <= bone.parent_index < len(bones)]
        gltf["skins"] = [{"joints": list(range(len(bones))), "inverseBindMatrices": ibm, "skeleton": roots[0]}]

    if bones and animations:
        gltf["animations"] = [_export_animation(b, bones, name, anim, fps) for name, anim in animations]

    for key in ("meshes", "materials"):
        if not gltf[key]:
            del gltf[key]
    gltf["bufferViews"] = b.buffer_views
    gltf["accessors"] = b.accessors
    gltf["buffers"] = [{"byteLength": len(b.buffer)}]
    return _pack_glb(gltf, bytes(b.buffer))


def _vertex_skin(v, bone_count: int):
    pairs = [(i, w) for i, w in zip(v.bone_indices, v.bone_weights) if 0 <= i < bone_count and w > 0]
    pairs = sorted(pairs, key=lambda p: -p[1])[:4] or [(0, 1.0)]
    total = sum(w for _, w in pairs)
    pairs += [(0, 0.0)] * (4 - len(pairs))
    return tuple(i for i, _ in pairs), tuple(w / total for _, w in pairs)


#: Shape flag bits that change how a material's shapes are blended or
#: depth-tested: 0x20 camera effect, 0x40 additive, 0x80 subtractive,
#: 0x100 depth test off, 0x200 (undecoded, set on the candle flames with 0x40).
SHAPE_BLEND_FLAGS = 0x3E0


def _add_material(
    gltf: dict,
    gs: model.GsModel,
    mat_index: int,
    image_index: dict[int, int],
    model_name: str,
    double_sided: bool,
    draw_pass: int = 0,
    shape_flags: int = 0,
) -> int:
    """``draw_pass`` is the chunk list the material's shapes are drawn in:
    list 1 (alpha-tested) becomes ``alphaMode`` MASK, list 2 (blended)
    BLEND, list 0 stays opaque (the game ignores texture alpha there)."""
    material = gs.materials[mat_index] if 0 <= mat_index < len(gs.materials) else None
    # The loader multiplies color0 RGB by 1.25 and clamps (see gltf_import).
    color = (
        [min(255.0, c * 1.25) / 255.0 for c in material.color0[:3]] + [material.color0[3] / 255.0]
        if material
        else [1.0, 1.0, 1.0, 1.0]
    )
    pbr: dict = {"baseColorFactor": color, "metallicFactor": 0.0, "roughnessFactor": 1.0}
    entry: dict = {"name": material.name if material and material.name else f"{model_name}_mat{mat_index}", "doubleSided": double_sided}
    if material and material.textures and material.textures[0].tex_id in image_index:
        pbr["baseColorTexture"] = {"index": image_index[material.textures[0].tex_id]}
    if draw_pass == 1:
        entry["alphaMode"] = "MASK"
    elif draw_pass == 2:
        entry["alphaMode"] = "BLEND"
    entry["pbrMetallicRoughness"] = pbr
    if material is not None:
        # What glTF cannot say, kept for re-import (gltf_import reads it back):
        # the shapes' blend bits (0x40 additive...) and the second and third colours.
        entry["extras"] = {
            "fe9_shape_flags": shape_flags,
            "fe9_color1": list(material.color1),
            "fe9_color2": list(material.color2),
        }
    gltf["materials"].append(entry)
    return len(gltf["materials"]) - 1


def _node_trs(m: skeleton.Mat3x4) -> dict:
    t, rot, scale = engine_pose.decompose(m)
    trs: dict = {"translation": list(t), "rotation": list(_quat_from_matrix(rot))}
    if any(abs(c - 1.0) > 1e-6 for c in scale):
        trs["scale"] = list(scale)
    return trs


def _export_animation(b: _Builder, bones, name: str, anim: animation.GaAnimation, fps: float) -> dict:
    last = max(anim.length_in_frames, anim.header.end_frame)
    frames = list(range(last + 1))
    times = [f / fps for f in frames]
    time_acc = b.accessor(times, "SCALAR", _FLOAT, bounds=True)
    animated = sorted({g.bone_index for g in anim.groups if 0 <= g.bone_index < len(bones)})
    samples = []
    seed = engine_pose.local_matrices(bones)
    for f in frames:
        local = engine_pose.local_matrices(bones, anim, float(f), seed)
        samples.append({i: engine_pose.decompose(engine_pose.joint_local(bones, i, local[i])) for i in animated})
    samplers, channels = [], []
    for bone_index in animated:
        quats, prev = [], None
        for sample in samples:
            q = _quat_from_matrix(sample[bone_index][1])
            if prev is not None and sum(a * c for a, c in zip(prev, q)) < 0:
                q = tuple(-c for c in q)
            quats.append(q)
            prev = q
        tracks = [("translation", [tuple(s[bone_index][0]) for s in samples], "VEC3"), ("rotation", quats, "VEC4")]
        scales = [tuple(s[bone_index][2]) for s in samples]
        rest_scale = engine_pose.decompose(engine_pose.joint_local(bones, bone_index, seed[bone_index]))[2]
        if any(abs(c - r) > 1e-6 for sc in scales for c, r in zip(sc, rest_scale)):
            tracks.append(("scale", scales, "VEC3"))
        for path, values, kind in tracks:
            samplers.append({"input": time_acc, "output": b.accessor(values, kind, _FLOAT), "interpolation": "LINEAR"})
            channels.append({"sampler": len(samplers) - 1, "target": {"node": bone_index, "path": path}})
    extras = {
        "events": [[key.frame, list(key.codes)] for key in anim.events],
        "loops": anim.header.loops,
        "loop_start": anim.header.loop_start_frame,
        "end_frame": anim.header.end_frame,
    }
    return {"name": name, "samplers": samplers, "channels": channels, "extras": extras}


def _pack_glb(gltf: dict, binary: bytes) -> bytes:
    json_chunk = json.dumps(gltf, separators=(",", ":")).encode("utf-8")
    json_chunk += b" " * (-len(json_chunk) % 4)
    binary += bytes(-len(binary) % 4)
    total = 12 + 8 + len(json_chunk) + 8 + len(binary)
    return (
        struct.pack("<4sII", b"glTF", 2, total)
        + struct.pack("<I4s", len(json_chunk), b"JSON")
        + json_chunk
        + struct.pack("<I4s", len(binary), b"BIN\0")
        + binary
    )
