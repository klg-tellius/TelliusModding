"""Import a glTF 2.0 model (``.glb`` or ``.gltf``) as a static ``.gs`` mesh.

Phase 1 of ``research/MODEL_IMPORT_PLAN.md``: geometry with no skinning.
:func:`read_gltf` flattens a glTF scene into world-space triangles grouped
by material; :func:`build_static_gs` turns that into a :class:`gs_file.GsFile`
plus the texture images its materials reference, and :func:`gs_file.write_gs`
does the byte layout. The skeleton (``.g``) and animations (``.ga``) of the
model being replaced stay as they are.

What the builder relies on, and where it comes from:

- **Bone space.** A single-matrix shape is drawn through
  ``actor x world[shape.bone]`` (``build_and_cache_gs_shape_bone_matrices``,
  ``0x8006A930``), so its stored vertices are local to that bone. Every
  shape the builder emits follows one bone, and vertices are moved into its
  space with the inverse of :func:`skeleton.bind_world_matrices`. The glTF
  scene is taken to be the model's bind pose in model space.
- **Vertex format** (``declare_gs_vertex_format``): positions ``3 x s16`` and
  UVs ``2 x s16`` with a per-file fraction-bit count, normals ``3 x s8``
  with 6 fraction bits (every real file), colors ``RGBA8``; every attribute
  is a 16-bit index, so each array is capped at 65,536 entries. Shapes
  always carry POS, NRM and TEX0 (``0x4600``) like the vanilla static
  shapes, plus CLR0 (``0x1000``) when the glTF has vertex colors.
- **Display lists** go to ``GXCallDisplayList`` as stored: ``0x98``
  triangle strips, zero (``GX_NOP``) padding to a multiple of 32 bytes.
- **Winding and culling.** Shape flag bits ``0x1800`` pick the GX cull
  mode (``apply_shape_cull_mode_from_flags``, ``0x80069010``): ``0x1000``
  culls back faces, ``0x0800`` front faces, ``0x1800`` nothing. Vanilla
  shapes use ``0x1000`` or ``0x1800`` only. GX treats clockwise as front,
  and vanilla strip triangles - ``(s[i], s[i+1], s[i+2])`` for even ``i``,
  ``(s[i+1], s[i], s[i+2])`` for odd ``i`` - face away from their normals
  when read counter-clockwise (99.8% of non-degenerate scenery/prop
  triangles). The builder reverses each glTF triangle before stripifying,
  and maps glTF ``doubleSided`` to ``0x1800``, single-sided to ``0x1000``.
- **Material color.** The loader multiplies ``color0`` RGB by 1.25 and
  clamps (``DAT_803692AC``), so a glTF base color is stored divided by
  1.25 - the vanilla ``204`` is ``1.0`` after loading.
- **Render pass.** The camera draws the three chunk lists (``addrs[6..8]``)
  with fixed GX presets (``gcamera_render_transform_points``,
  ``0x800661A8``): list 0 opaque; list 1 alpha-tested (alpha >= 128, Z
  test after texturing, Z written) for cut-outs such as leaves; list 2
  alpha-blended without Z writes. A glTF material's ``alphaMode`` picks
  the list: ``OPAQUE`` 0, ``MASK`` 1, ``BLEND`` 2. Flag bits ``0x6000``
  equal ``(list index + 1) << 13`` on every vanilla shape, and imported
  shapes carry them the same way.
"""

from __future__ import annotations

import base64
import io
import json
import math
import re
import struct
import zlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from PIL import Image

from . import animation, engine_pose, gs_file, skeleton, tpl

_COMPONENT_FORMATS = {5120: "b", 5121: "B", 5122: "h", 5123: "H", 5125: "I", 5126: "f"}
_NORMALIZE_DIVISORS = {5120: 127.0, 5121: 255.0, 5122: 32767.0, 5123: 65535.0}
_TYPE_SIZES = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4, "MAT4": 16}
_MODE_TRIANGLES, _MODE_STRIP, _MODE_FAN = 4, 5, 6

EXPORT_DATE = 0x20040723
FLAG_CULL_BACK, FLAG_CULL_NONE = 0x1000, 0x1800
FLAG_FIRST_PASS = 0x2000
#: glTF alphaMode -> chunk list (draw pass).
ALPHA_MODE_PASS = {"OPAQUE": 0, "MASK": 1, "BLEND": 2}
ATTR_POS, ATTR_NRM, ATTR_CLR0, ATTR_TEX0 = 0x200, 0x400, 0x1000, 0x4000
ATTR_TEX1 = 0x8000  # a second UV index after the first (vanilla terrain: 0xC600)
#: Materials whose second UV set the game uses (the map_base dual-sample callback).
UV2_MATERIALS = frozenset({"map_base", "map_wall"})
NORMAL_FRAC = 6
MAX_FRAC = 14
MAX_INDEX = 0xFFFF
COLOR_LOAD_SCALE = 1.25
MAX_TEXTURE_SIZE = 512


class GltfImportError(Exception):
    pass


Vec3 = tuple[float, float, float]


@dataclass
class ImportedMaterial:
    name: str
    base_color: tuple[float, float, float, float] = (1.0, 1.0, 1.0, 1.0)
    image: Optional[Image.Image] = None
    double_sided: bool = False
    alpha_mode: str = "OPAQUE"
    # from the material's extras, as gltf_export writes them for a game model
    shape_flags: int = 0  # blend bits (0x40 additive...) glTF cannot express
    color1: Optional[tuple[int, int, int, int]] = None
    color2: Optional[tuple[int, int, int, int]] = None

    @property
    def pass_flag(self) -> int:
        """Shape flag bits ``0x6000`` for this material's chunk list, plus
        the blend bits kept in the material's extras."""
        return FLAG_FIRST_PASS * (ALPHA_MODE_PASS.get(self.alpha_mode, 0) + 1) | (self.shape_flags & 0x3E0)


Influences = tuple[tuple[str, float], ...]  # (joint node name, weight), heaviest first


@dataclass
class ImportedTriangle:
    """One glTF triangle in model space, counter-clockwise front face.
    ``influences`` holds each corner's joints when the triangle is skinned,
    or is attached to a joint node; ``None`` otherwise."""

    positions: tuple[Vec3, Vec3, Vec3]
    normals: tuple[Vec3, Vec3, Vec3]
    uvs: tuple[tuple[float, float], tuple[float, float], tuple[float, float]]
    colors: Optional[tuple[tuple[int, int, int, int], ...]] = None
    influences: Optional[tuple[Influences, Influences, Influences]] = None
    # each corner's (position, normal) in the skin's bind space - the mesh
    # space its inverse bind matrices refer to - when it follows a joint
    bind: Optional[tuple] = None
    # the second UV set (glTF TEXCOORD_1), kept for map terrain materials
    uvs2: Optional[tuple[tuple[float, float], tuple[float, float], tuple[float, float]]] = None


@dataclass
class ImportedScene:
    materials: list[ImportedMaterial] = field(default_factory=list)
    triangles: dict[int, list[ImportedTriangle]] = field(default_factory=dict)  # material index -> triangles
    warnings: list[str] = field(default_factory=list)
    joint_parents: dict[str, Optional[str]] = field(default_factory=dict)  # joint name -> parent joint name

    @property
    def skinned(self) -> bool:
        return any(t.influences for tris in self.triangles.values() for t in tris)


# ---------------------------------------------------------------- glTF reading


def _split_glb(data: bytes) -> tuple[dict, bytes]:
    magic, version, _length = struct.unpack_from("<4sII", data, 0)
    if magic != b"glTF" or version != 2:
        raise GltfImportError("Not a glTF 2.0 binary file.")
    offset, doc, binary = 12, None, b""
    while offset + 8 <= len(data):
        size, kind = struct.unpack_from("<I4s", data, offset)
        chunk = data[offset + 8 : offset + 8 + size]
        if kind == b"JSON":
            doc = json.loads(chunk.decode("utf-8"))
        elif kind == b"BIN\0":
            binary = chunk
        offset += 8 + size
    if doc is None:
        raise GltfImportError("glTF binary has no JSON chunk.")
    return doc, binary


def _load_uri(uri: str, base_dir: Optional[Path]) -> bytes:
    if uri.startswith("data:"):
        return base64.b64decode(uri.split(",", 1)[1])
    if base_dir is None:
        raise GltfImportError(f"External file {uri!r} needs the glTF's folder.")
    return (base_dir / uri).read_bytes()


class _Document:
    def __init__(self, data: bytes, base_dir: Optional[Path]) -> None:
        if data[:4] == b"glTF":
            self.doc, glb_binary = _split_glb(data)
        else:
            self.doc, glb_binary = json.loads(data.decode("utf-8")), b""
        self.buffers = []
        for buf in self.doc.get("buffers", []):
            self.buffers.append(_load_uri(buf["uri"], base_dir) if "uri" in buf else glb_binary)
        self.base_dir = base_dir

    def view_bytes(self, index: int) -> tuple[bytes, int]:
        view = self.doc["bufferViews"][index]
        start = view.get("byteOffset", 0)
        return self.buffers[view["buffer"]][start : start + view["byteLength"]], view.get("byteStride", 0)

    def accessor(self, index: int) -> list[tuple]:
        acc = self.doc["accessors"][index]
        if "sparse" in acc:
            raise GltfImportError("Sparse accessors are not supported.")
        ctype, count, width = acc["componentType"], acc["count"], _TYPE_SIZES[acc["type"]]
        fmt = "<" + _COMPONENT_FORMATS[ctype] * width
        element = struct.calcsize(fmt)
        if "bufferView" not in acc:
            return [(0,) * width] * count
        data, stride = self.view_bytes(acc["bufferView"])
        stride = stride or element
        base = acc.get("byteOffset", 0)
        values = [struct.unpack_from(fmt, data, base + i * stride) for i in range(count)]
        if acc.get("normalized") and ctype in _NORMALIZE_DIVISORS:
            div = _NORMALIZE_DIVISORS[ctype]
            values = [tuple(max(c / div, -1.0) for c in v) for v in values]
        return values

    def image(self, texture_index: int) -> Optional[Image.Image]:
        textures = self.doc.get("textures", [])
        if not 0 <= texture_index < len(textures) or "source" not in textures[texture_index]:
            return None
        img = self.doc["images"][textures[texture_index]["source"]]
        raw = self.view_bytes(img["bufferView"])[0] if "bufferView" in img else _load_uri(img["uri"], self.base_dir)
        return Image.open(io.BytesIO(raw)).convert("RGBA")


def _mat4_mul(a: list[float], b: list[float]) -> list[float]:
    """Column-major 4x4 product ``a x b``."""
    return [sum(a[k * 4 + r] * b[c * 4 + k] for k in range(4)) for c in range(4) for r in range(4)]


def _node_matrix(node: dict) -> list[float]:
    if "matrix" in node:
        return list(node["matrix"])
    x, y, z, w = node.get("rotation", (0.0, 0.0, 0.0, 1.0))
    sx, sy, sz = node.get("scale", (1.0, 1.0, 1.0))
    tx, ty, tz = node.get("translation", (0.0, 0.0, 0.0))
    r = [
        1 - 2 * (y * y + z * z), 2 * (x * y + z * w), 2 * (x * z - y * w),
        2 * (x * y - z * w), 1 - 2 * (x * x + z * z), 2 * (y * z + x * w),
        2 * (x * z + y * w), 2 * (y * z - x * w), 1 - 2 * (x * x + y * y),
    ]
    return [
        r[0] * sx, r[1] * sx, r[2] * sx, 0.0,
        r[3] * sy, r[4] * sy, r[5] * sy, 0.0,
        r[6] * sz, r[7] * sz, r[8] * sz, 0.0,
        tx, ty, tz, 1.0,
    ]


def _apply_point(m: list[float], v) -> Vec3:
    return tuple(m[r] * v[0] + m[4 + r] * v[1] + m[8 + r] * v[2] + m[12 + r] for r in range(3))  # type: ignore[return-value]


def _normal_matrix(m: list[float]) -> list[list[float]]:
    """Inverse-transpose of the upper 3x3, row-major (identity for a
    singular matrix, e.g. a joint scaled to 0 to hide a part)."""
    a = [[m[c * 4 + r] for c in range(3)] for r in range(3)]
    try:
        inv = _inverse3(a)
    except GltfImportError:
        return [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]]
    return [[inv[c][r] for c in range(3)] for r in range(3)]


def _inverse3(a: list[list[float]]) -> list[list[float]]:
    det = (
        a[0][0] * (a[1][1] * a[2][2] - a[1][2] * a[2][1])
        - a[0][1] * (a[1][0] * a[2][2] - a[1][2] * a[2][0])
        + a[0][2] * (a[1][0] * a[2][1] - a[1][1] * a[2][0])
    )
    if abs(det) < 1e-12:
        raise GltfImportError("A transform in the scene is singular (zero scale).")
    cof = [
        [a[1][1] * a[2][2] - a[1][2] * a[2][1], a[0][2] * a[2][1] - a[0][1] * a[2][2], a[0][1] * a[1][2] - a[0][2] * a[1][1]],
        [a[1][2] * a[2][0] - a[1][0] * a[2][2], a[0][0] * a[2][2] - a[0][2] * a[2][0], a[0][2] * a[1][0] - a[0][0] * a[1][2]],
        [a[1][0] * a[2][1] - a[1][1] * a[2][0], a[0][1] * a[2][0] - a[0][0] * a[2][1], a[0][0] * a[1][1] - a[0][1] * a[1][0]],
    ]
    return [[c / det for c in row] for row in cof]


def _invert_4x4(m: list[float]) -> list[float]:
    """Inverse of a column-major affine 4x4."""
    a = [[m[c * 4 + r] for c in range(3)] for r in range(3)]
    inv = _inverse3(a)
    t = (m[12], m[13], m[14])
    it = [-sum(inv[r][k] * t[k] for k in range(3)) for r in range(3)]
    return [inv[0][0], inv[1][0], inv[2][0], 0.0, inv[0][1], inv[1][1], inv[2][1], 0.0,
            inv[0][2], inv[1][2], inv[2][2], 0.0, it[0], it[1], it[2], 1.0]


def _mat3_vec(m, v) -> Vec3:
    return (
        m[0][0] * v[0] + m[0][1] * v[1] + m[0][2] * v[2],
        m[1][0] * v[0] + m[1][1] * v[1] + m[1][2] * v[2],
        m[2][0] * v[0] + m[2][1] * v[1] + m[2][2] * v[2],
    )


def _normalize(v) -> Vec3:
    n = math.sqrt(v[0] * v[0] + v[1] * v[1] + v[2] * v[2])
    return (v[0] / n, v[1] / n, v[2] / n) if n > 1e-12 else (0.0, 1.0, 0.0)


def _face_normal(a, b, c) -> Vec3:
    u = (b[0] - a[0], b[1] - a[1], b[2] - a[2])
    v = (c[0] - a[0], c[1] - a[1], c[2] - a[2])
    return _normalize((u[1] * v[2] - u[2] * v[1], u[2] * v[0] - u[0] * v[2], u[0] * v[1] - u[1] * v[0]))


def _triangle_indices(mode: int, indices: list[int]) -> list[tuple[int, int, int]]:
    if mode == _MODE_TRIANGLES:
        return [tuple(indices[i : i + 3]) for i in range(0, len(indices) - 2, 3)]  # type: ignore[misc]
    if mode == _MODE_STRIP:
        return [
            (indices[i], indices[i + 1], indices[i + 2]) if i % 2 == 0 else (indices[i + 1], indices[i], indices[i + 2])
            for i in range(len(indices) - 2)
        ]
    if mode == _MODE_FAN:
        return [(indices[0], indices[i], indices[i + 1]) for i in range(1, len(indices) - 1)]
    raise GltfImportError(f"Primitive mode {mode} is not triangles.")


def _skinned_vertices(d: _Document, skin: dict, attrs: dict, positions, normals, joint_world, node_name):
    """Pose a skinned primitive's vertices at the joints' rest transforms
    (``joint world x inverse bind``, blended by weight) and list each
    vertex's influences, heaviest first."""
    joints = skin["joints"]
    ibms = d.accessor(skin["inverseBindMatrices"]) if "inverseBindMatrices" in skin else [_node_matrix({})] * len(joints)
    mats = [_mat4_mul(joint_world(j), list(ibm)) for j, ibm in zip(joints, ibms)]
    normal_mats: dict[int, list[list[float]]] = {}
    vertex_joints = d.accessor(attrs["JOINTS_0"]) if "JOINTS_0" in attrs else [(0, 0, 0, 0)] * len(positions)
    vertex_weights = d.accessor(attrs["WEIGHTS_0"]) if "WEIGHTS_0" in attrs else [(1.0, 0.0, 0.0, 0.0)] * len(positions)
    out_p, out_n, out_inf, out_local = [], [], [], []
    for i, p in enumerate(positions):
        pairs = [(int(k), float(w)) for k, w in zip(vertex_joints[i], vertex_weights[i]) if w > 0 and int(k) < len(mats)]
        total = sum(w for _, w in pairs)
        if total <= 0:
            out_p.append(tuple(p))
            out_n.append(normals[i] if normals else None)
            out_inf.append(())
            out_local.append(None)
            continue
        pairs = sorted(((k, w / total) for k, w in pairs), key=lambda kw: -kw[1])
        out_local.append((tuple(p), tuple(normals[i]) if normals else None))
        acc_p, acc_n = [0.0, 0.0, 0.0], [0.0, 0.0, 0.0]
        for k, w in pairs:
            q = _apply_point(mats[k], p)
            if normals:
                if k not in normal_mats:
                    normal_mats[k] = _normal_matrix(mats[k])
                n = _mat3_vec(normal_mats[k], normals[i])
            for axis in range(3):
                acc_p[axis] += w * q[axis]
                if normals:
                    acc_n[axis] += w * n[axis]
        out_p.append(tuple(acc_p))
        out_n.append(_normalize(acc_n) if normals else None)
        out_inf.append(tuple((node_name(joints[k]), w) for k, w in pairs))
    return out_p, (out_n if normals else None), out_inf, out_local


def read_gltf(data: bytes, base_dir: Optional[Path | str] = None) -> ImportedScene:
    """Flatten the default scene into model-space triangles per material.
    Node transforms are baked in. A skinned mesh is posed at its joints'
    rest transforms (its own node transform is ignored, as the glTF spec
    says) and keeps each vertex's joint weights; a plain mesh parented to
    a joint node is attached rigidly to that joint."""
    d = _Document(data, Path(base_dir) if base_dir is not None else None)
    doc = d.doc
    scene = ImportedScene()
    nodes = doc.get("nodes", [])
    parents = {c: i for i, n in enumerate(nodes) for c in n.get("children", [])}
    world_cache: dict[int, list[float]] = {}

    def node_world(i: int) -> list[float]:
        chain = []
        while i is not None and i not in world_cache:
            chain.append(i)
            i = parents.get(i)
        m = world_cache[i] if i is not None else _node_matrix({})
        for j in reversed(chain):
            m = _mat4_mul(m, _node_matrix(nodes[j]))
            world_cache[j] = m
        return m

    def node_name(i: int) -> str:
        return nodes[i].get("name") or f"node{i}"

    joint_nodes = {j for s in doc.get("skins", []) for j in s.get("joints", [])}

    def joint_ancestor(i: int) -> Optional[int]:
        p = parents.get(i)
        while p is not None and p not in joint_nodes:
            p = parents.get(p)
        return p

    for j in sorted(joint_nodes):
        parent = joint_ancestor(j)
        scene.joint_parents[node_name(j)] = node_name(parent) if parent is not None else None
    # a joint's bind world: the inverse of its inverse bind matrix
    bind_world: dict[int, list[float]] = {}
    for skin in doc.get("skins", []):
        joints = skin.get("joints", [])
        ibms = d.accessor(skin["inverseBindMatrices"]) if "inverseBindMatrices" in skin else None
        for k, j in enumerate(joints):
            bind_world.setdefault(j, _invert_4x4(list(ibms[k])) if ibms else node_world(j))

    for i, mat in enumerate(doc.get("materials", [])):
        pbr = mat.get("pbrMetallicRoughness", {})
        image = d.image(pbr["baseColorTexture"]["index"]) if "baseColorTexture" in pbr else None
        extras = mat.get("extras") if isinstance(mat.get("extras"), dict) else {}

        def colour(key: str):
            value = extras.get(key)
            return tuple(int(c) for c in value[:4]) if isinstance(value, list) and len(value) >= 4 else None

        scene.materials.append(
            ImportedMaterial(
                mat.get("name") or f"material{i}",
                tuple(pbr.get("baseColorFactor", (1.0, 1.0, 1.0, 1.0))),
                image,
                bool(mat.get("doubleSided", False)),
                str(mat.get("alphaMode", "OPAQUE")),
                int(extras.get("fe9_shape_flags", 0) or 0),
                colour("fe9_color1"),
                colour("fe9_color2"),
            )
        )
    default_material: Optional[int] = None

    scenes = doc.get("scenes", [])
    roots = scenes[doc.get("scene", 0)]["nodes"] if scenes else [i for i in range(len(nodes)) if i not in parents]
    stack = list(roots)
    seen = set()
    while stack:
        index = stack.pop()
        if index in seen:
            continue
        seen.add(index)
        node = nodes[index]
        stack.extend(node.get("children", []))
        if "mesh" not in node:
            continue
        skin = doc["skins"][node["skin"]] if "skin" in node else None
        transform = node_world(index)
        normal_m = _normal_matrix(transform)
        attached = joint_ancestor(index) if skin is None else None
        rigid: Influences = ((node_name(attached), 1.0),) if attached is not None else ()
        # an attached mesh in bind space: its offset from the joint, placed at the joint's bind
        to_bind = None
        if attached is not None:
            offset, walk = _node_matrix({}), index
            while walk != attached:  # node transforms between the joint and the mesh
                offset = _mat4_mul(_node_matrix(nodes[walk]), offset)
                walk = parents[walk]
            to_bind = _mat4_mul(bind_world.get(attached, node_world(attached)), offset)
        for prim in doc["meshes"][node["mesh"]]["primitives"]:
            attrs = prim["attributes"]
            if "POSITION" not in attrs:
                continue
            vertex_influences = None
            vertex_local = None
            if skin is not None:
                raw_normals = [tuple(n) for n in d.accessor(attrs["NORMAL"])] if "NORMAL" in attrs else None
                positions, normals, vertex_influences, vertex_local = _skinned_vertices(
                    d, skin, attrs, d.accessor(attrs["POSITION"]), raw_normals, node_world, node_name
                )
            else:
                raw = d.accessor(attrs["POSITION"])
                positions = [_apply_point(transform, p) for p in raw]
                normals = (
                    [_normalize(_mat3_vec(normal_m, n)) for n in d.accessor(attrs["NORMAL"])] if "NORMAL" in attrs else None
                )
                if to_bind is not None:
                    bind_normal_m = _normal_matrix(to_bind)
                    raw_normals = d.accessor(attrs["NORMAL"]) if "NORMAL" in attrs else None
                    vertex_local = [
                        (_apply_point(to_bind, p), _normalize(_mat3_vec(bind_normal_m, raw_normals[k])) if raw_normals else None)
                        for k, p in enumerate(raw)
                    ]
            uvs = [tuple(uv) for uv in d.accessor(attrs["TEXCOORD_0"])] if "TEXCOORD_0" in attrs else None
            uvs2 = [tuple(uv) for uv in d.accessor(attrs["TEXCOORD_1"])] if "TEXCOORD_1" in attrs else None
            colors = None
            if "COLOR_0" in attrs:
                colors = []
                for c in d.accessor(attrs["COLOR_0"]):
                    if doc["accessors"][attrs["COLOR_0"]]["componentType"] == 5126 or doc["accessors"][attrs["COLOR_0"]].get("normalized"):
                        c = tuple(round(max(0.0, min(1.0, x)) * 255) for x in c)
                    colors.append(tuple(c) + (255,) * (4 - len(c)))
            indices = [v[0] for v in d.accessor(prim["indices"])] if "indices" in prim else list(range(len(positions)))
            material = prim.get("material")
            if material is None:
                if default_material is None:
                    scene.materials.append(ImportedMaterial("default"))
                    default_material = len(scene.materials) - 1
                material = default_material
            out = scene.triangles.setdefault(material, [])
            for a, b, c in _triangle_indices(prim.get("mode", _MODE_TRIANGLES), indices):
                pa, pb, pc = positions[a], positions[b], positions[c]
                if normals is None:
                    fn = _face_normal(pa, pb, pc)
                    tri_normals = (fn, fn, fn)
                else:
                    tri_normals = (normals[a], normals[b], normals[c])
                if vertex_influences is not None:
                    influences = (vertex_influences[a], vertex_influences[b], vertex_influences[c])
                else:
                    influences = (rigid, rigid, rigid) if rigid else None
                bind = (vertex_local[a], vertex_local[b], vertex_local[c]) if vertex_local is not None else None
                out.append(
                    ImportedTriangle(
                        (pa, pb, pc),
                        tri_normals,
                        (uvs[a], uvs[b], uvs[c]) if uvs else ((0.0, 0.0),) * 3,  # type: ignore[arg-type]
                        (colors[a], colors[b], colors[c]) if colors else None,
                        influences,  # type: ignore[arg-type]
                        bind,
                        (uvs2[a], uvs2[b], uvs2[c]) if uvs2 else None,
                    )
                )
    if not any(scene.triangles.values()):
        raise GltfImportError("The glTF scene has no triangles.")
    return scene


# ---------------------------------------------------------------- stripifying


def stripify(triangles: list[tuple[int, int, int]]) -> list[list[int]]:
    """Greedy triangle-strip builder. Input and output use the game's
    convention: strip triangle ``i`` is ``(s[i], s[i+1], s[i+2])`` for even
    ``i`` and ``(s[i+1], s[i], s[i+2])`` for odd ``i``; every input
    triangle comes out exactly once with its winding (cyclic order) kept.
    Degenerate triangles are dropped."""
    tris = [t for t in triangles if len({*t}) == 3]
    by_edge: dict[tuple[int, int], list[int]] = {}
    for i, (a, b, c) in enumerate(tris):
        for e in ((a, b), (b, c), (c, a)):
            by_edge.setdefault(e, []).append(i)
    used = [False] * len(tris)

    def same_winding(t, x, y, z) -> bool:
        return (x, y, z) in ((t[0], t[1], t[2]), (t[1], t[2], t[0]), (t[2], t[0], t[1]))

    def extend(strip: list[int], mark: set[int]) -> list[int]:
        while True:
            p, q = strip[-2], strip[-1]
            parity = (len(strip) - 2) % 2
            # The next triangle is (p, q, r) for an even slot, (q, p, r) for an odd one;
            # in either case it contains the directed edge p->q or q->p respectively.
            edge = (p, q) if parity == 0 else (q, p)
            found = None
            for ti in by_edge.get(edge, ()):
                if used[ti] or ti in mark:
                    continue
                t = tris[ti]
                r = next(v for v in t if v != p and v != q)
                if same_winding(t, *((p, q, r) if parity == 0 else (q, p, r))):
                    found = (ti, r)
                    break
            if found is None:
                return strip
            mark.add(found[0])
            strip.append(found[1])

    strips = []
    for start in range(len(tris)):
        if used[start]:
            continue
        a, b, c = tris[start]
        best, best_mark = None, None
        for rot in ((a, b, c), (b, c, a), (c, a, b)):
            mark = {start}
            candidate = extend(list(rot), mark)
            if best is None or len(candidate) > len(best):
                best, best_mark = candidate, mark
        for ti in best_mark:
            used[ti] = True
        strips.append(best)
    return strips


def strip_triangles(strip: list[int]):
    """The triangles a game strip draws, in the game's winding."""
    for i in range(len(strip) - 2):
        a, b, c = strip[i], strip[i + 1], strip[i + 2]
        yield (a, b, c) if i % 2 == 0 else (b, a, c)


# ---------------------------------------------------------------- building


def _fraction_bits(max_abs: float, limit: int = 32767, cap: int = MAX_FRAC) -> int:
    if max_abs > limit:
        raise GltfImportError(f"Coordinate {max_abs:g} does not fit a 16-bit fixed-point value.")
    bits = cap
    while bits > 0 and max_abs * (1 << bits) > limit:
        bits -= 1
    return bits


def _quantize(value: float, bits: int, low: int, high: int) -> int:
    return max(low, min(high, round(value * (1 << bits))))


def _pow2_at_most(n: int, cap: int) -> int:
    p = 1
    while p * 2 <= min(n, cap):
        p *= 2
    return max(p, 8)


def texture_for_tpl(image: Image.Image, max_size: int = MAX_TEXTURE_SIZE) -> tuple[Image.Image, int]:
    """Resize to power-of-two sides (needed for repeat wrapping) no larger
    than ``max_size``, and pick CMPR for images whose alpha is only 0 or
    255 (CMPR's 1-bit alpha, as in the vanilla battle-model textures),
    RGB5A3 otherwise."""
    rgba = image.convert("RGBA")
    size = (_pow2_at_most(rgba.width, max_size), _pow2_at_most(rgba.height, max_size))
    if size != rgba.size:
        rgba = rgba.resize(size, Image.LANCZOS)
    alphas = {value for _count, value in rgba.getchannel("A").getcolors(256)}
    return rgba, (tpl.FORMAT_CMPR if alphas <= {0, 255} else tpl.FORMAT_RGB5A3)


def _invert_3x4(m: skeleton.Mat3x4) -> tuple[list[list[float]], Vec3]:
    inv = _inverse3([list(row[:3]) for row in m])
    t = (m[0][3], m[1][3], m[2][3])
    return inv, tuple(-c for c in _mat3_vec(inv, t))  # type: ignore[return-value]


def _chunk_lists(chunks: list[gs_file.GsChunk]) -> tuple[list, list, list]:
    """Chunks split into the three draw lists by their flag bits ``0x6000``."""
    lists: tuple[list, list, list] = ([], [], [])
    for chunk in chunks:
        lists[(chunk.flags >> 13 & 3) - 1].append(chunk)
    return lists


@dataclass
class StaticBuild:
    gs: gs_file.GsFile
    images: list[Image.Image]  # tex_id order
    warnings: list[str] = field(default_factory=list)
    #: Skinned builds: glTF joint -> (game bone name, how it was matched:
    #: ``"name"``, ``"parent <joint>"`` or ``"fallback"``).
    joint_map: dict[str, tuple[str, str]] = field(default_factory=dict)


def _source_material(scene: ImportedScene, index: int) -> ImportedMaterial:
    return scene.materials[index] if index < len(scene.materials) else ImportedMaterial(f"material{index}")


def _image_index(images: list[Image.Image], image: Optional[Image.Image]) -> Optional[int]:
    """``tex_id`` for ``image``, appending it unless an identical image is
    already listed (materials sharing a glTF texture share one ``tex_id``)."""
    if image is None:
        return None
    for i, known in enumerate(images):
        if known.size == image.size and known.tobytes() == image.tobytes():
            return i
    images.append(image)
    return len(images) - 1


def _material_record(
    src: ImportedMaterial, tex_id: Optional[int], extra_textures: tuple[gs_file.GsTexture, ...] = ()
) -> gs_file.GsMaterial:
    """A material with the vanilla static defaults (see module docstring),
    followed by ``extra_textures`` records."""
    textures = [gs_file.GsTexture((1, 0), tex_id, (257, 0, 0, 0, 0), 1.0, 1.0, 0)] if tex_id is not None else []
    textures += list(extra_textures)
    r, g, b, a = src.base_color
    color0 = tuple(max(0, min(255, round(c * 255 / COLOR_LOAD_SCALE))) for c in (r, g, b)) + (max(0, min(255, round(a * 255))),)
    return gs_file.GsMaterial(
        name=src.name,
        unk0=(0, 0),
        unk1=0,
        color0=color0,
        color1=src.color1 or (0, 0, 0, 255),
        color2=src.color2 or (0, 0, 0, 0),
        textures=textures,  # type: ignore[arg-type]
    )


def build_static_gs(
    scene: ImportedScene,
    *,
    bone: int = 0,
    bone_world: skeleton.Mat3x4 = skeleton.IDENTITY_3X4,
    name: str = "imported",
    tex_id_base: int = 0,
    extra_textures: tuple[gs_file.GsTexture, ...] = (),
) -> StaticBuild:
    """Build a static ``.gs`` whose shapes all follow ``bone``, whose
    bind-pose world matrix is ``bone_world`` (see
    :func:`skeleton.bind_world_matrices`). Texture ids count from
    ``tex_id_base`` (images added after a shared TPL's existing ones), and
    every material ends with ``extra_textures``."""
    inv_rot, inv_t = _invert_3x4(bone_world)
    normal_rot = [[bone_world[c][r] for c in range(3)] for r in range(3)]  # inverse-transpose of inv_rot

    def to_local(p) -> Vec3:
        q = _mat3_vec(inv_rot, p)
        return (q[0] + inv_t[0], q[1] + inv_t[1], q[2] + inv_t[2])

    used_materials = [m for m in sorted(scene.triangles) if scene.triangles[m]]
    local_tris = {
        m: [
            (
                tuple(to_local(p) for p in t.positions),
                tuple(_normalize(_mat3_vec(normal_rot, n)) for n in t.normals),
                t.uvs,
                t.colors,
                t.positions,
                t.uvs2,
            )
            for t in scene.triangles[m]
        ]
        for m in used_materials
    }

    all_positions = [p for tris in local_tris.values() for t in tris for p in t[0]]
    all_uvs = [uv for tris in local_tris.values() for t in tris for uv in (*t[2], *(t[5] or ()))]
    pos_frac = _fraction_bits(max(abs(c) for p in all_positions for c in p))
    uv_frac = _fraction_bits(max((abs(c) for uv in all_uvs for c in uv), default=0.0))

    positions: dict[tuple, int] = {}
    normals: dict[tuple, int] = {}
    uvs: dict[tuple, int] = {}
    colors: dict[tuple, int] = {}

    def index_of(table: dict, key) -> int:
        if key not in table:
            table[key] = len(table)
        return table[key]

    images: list[Image.Image] = []
    materials: list[gs_file.GsMaterial] = []
    meshes: list[gs_file.GsMesh] = []
    chunks: list[gs_file.GsChunk] = []
    world_min, world_max = [math.inf] * 3, [-math.inf] * 3

    for mat_index in used_materials:
        src = _source_material(scene, mat_index)
        image_index = _image_index(images, src.image)
        tex_id = None if image_index is None else tex_id_base + image_index
        materials.append(_material_record(src, tex_id, extra_textures))

        has_color = any(t[3] is not None for t in local_tris[mat_index])
        # a second UV set is written only for map terrain materials, the one
        # place the game samples it (map_base / map_wall, texture0 twice)
        has_uv2 = src.name in UV2_MATERIALS and any(t[5] is not None for t in local_tris[mat_index])
        keys: dict[tuple, int] = {}
        key_list: list[tuple] = []
        game_tris = []
        local_min, local_max = [math.inf] * 3, [-math.inf] * 3
        for local_p, local_n, tri_uv, tri_c, world_p, tri_uv2 in local_tris[mat_index]:
            corner_keys = []
            for k in range(3):
                qp = tuple(_quantize(c, pos_frac, -32768, 32767) for c in local_p[k])
                qn = tuple(_quantize(c, NORMAL_FRAC, -128, 127) for c in local_n[k])
                qu = tuple(_quantize(c, uv_frac, -32768, 32767) for c in tri_uv[k])
                key = (index_of(positions, qp), index_of(normals, qn), index_of(uvs, qu))
                if has_color:
                    key += (index_of(colors, tuple(tri_c[k]) if tri_c else (255, 255, 255, 255)),)
                if has_uv2:
                    second = tri_uv2[k] if tri_uv2 else tri_uv[k]
                    key += (index_of(uvs, tuple(_quantize(c, uv_frac, -32768, 32767) for c in second)),)
                if key not in keys:
                    keys[key] = len(key_list)
                    key_list.append(key)
                corner_keys.append(keys[key])
                for axis in range(3):
                    local_min[axis] = min(local_min[axis], local_p[k][axis])
                    local_max[axis] = max(local_max[axis], local_p[k][axis])
                    world_min[axis] = min(world_min[axis], world_p[k][axis])
                    world_max[axis] = max(world_max[axis], world_p[k][axis])
            a_, b_, c_ = corner_keys
            game_tris.append((a_, c_, b_))  # glTF counter-clockwise -> game clockwise

        dl = bytearray()
        for strip in stripify(game_tris):
            if len(strip) > 0xFFFF:
                raise GltfImportError("A triangle strip is longer than 65,535 vertices.")
            dl += struct.pack(">BH", 0x98, len(strip))
            for vertex in strip:
                pi, ni, ui, *rest = key_list[vertex]
                dl += struct.pack(">HH", pi, ni)
                if has_color:
                    dl += struct.pack(">H", rest.pop(0))
                dl += struct.pack(">H", ui)
                if has_uv2:
                    dl += struct.pack(">H", rest.pop(0))
        dl += bytes(-len(dl) % 32)

        meshes.append(gs_file.GsMesh("none", tuple(local_min), tuple(local_max), bone))  # type: ignore[arg-type]
        chunks.append(
            gs_file.GsChunk(
                mesh_index=len(meshes) - 1,
                flags=src.pass_flag | (FLAG_CULL_NONE if src.double_sided else FLAG_CULL_BACK),
                material_index=len(materials) - 1,
                bone=bone,
                cache_slot=0,
                attr_mask=ATTR_POS | ATTR_NRM | ATTR_TEX0 | (ATTR_CLR0 if has_color else 0) | (ATTR_TEX1 if has_uv2 else 0),
                display_list=bytes(dl),
            )
        )

    for table, label in ((positions, "positions"), (normals, "normals"), (uvs, "UVs"), (colors, "colors")):
        if len(table) > MAX_INDEX + 1:
            raise GltfImportError(f"Too many distinct {label} ({len(table)}); the game indexes them with 16 bits.")

    gs = gs_file.GsFile(
        root_name="unknown",
        date=EXPORT_DATE,
        model_id=zlib.crc32(name.encode("utf-8")),
        bbox_min=tuple(world_min),  # type: ignore[arg-type]
        bbox_max=tuple(world_max),  # type: ignore[arg-type]
        pos_frac=pos_frac,
        norm_frac=NORMAL_FRAC,
        uv_frac=uv_frac,
        positions=list(positions),
        normals=list(normals),
        uvs=list(uvs),
        colors=list(colors),
        materials=materials,
        meshes=meshes,
        chunk_lists=_chunk_lists(chunks),
    )
    warnings = list(scene.warnings)
    if scene.skinned:
        warnings.append("Joint weights are ignored: the model is imported in its rest pose as one rigid piece.")
    return StaticBuild(gs, images, warnings)


def import_static_model(
    gltf_data: bytes,
    *,
    skeleton_data: Optional[bytes] = None,
    bone: int = 0,
    base_dir: Optional[Path | str] = None,
    name: str = "imported",
) -> tuple[bytes, Optional[bytes], list[str]]:
    """glTF bytes -> ``(.gs bytes, .tpl bytes or None, warnings)``. With
    ``skeleton_data`` (the ``.g`` the model is drawn with), vertices go into
    ``bone``'s bind space; without it the bone is taken as identity."""
    scene = read_gltf(gltf_data, base_dir)
    world = skeleton.IDENTITY_3X4
    if skeleton_data is not None:
        bones = skeleton.read_skeleton_file(skeleton_data).bones
        if not 0 <= bone < len(bones):
            raise GltfImportError(f"Bone {bone} is not in the skeleton ({len(bones)} bones).")
        world = skeleton.bind_world_matrices(bones)[bone]
    build = build_static_gs(scene, bone=bone, bone_world=world, name=name)
    tpl_bytes = tpl.build_tpl([texture_for_tpl(img) for img in build.images]) if build.images else None
    return gs_file.write_gs(build.gs), tpl_bytes, build.warnings


# ---------------------------------------------------------------- skinned build

MAX_SUBSET_BONES = 10
FLAG_COMPOSITE = 0x1
FLAG_MULTI_MATRIX = 0x2
ATTR_PNMTXIDX = 0x1
#: Bones per blended vertex (a composite weight record holds four).
MAX_BLEND_BONES = 4
#: Vertices per composite weight record: up to 8 alignment bytes plus
#: 12 x 340 fit one 4 KiB locked-cache half.
MAX_RECORD_VERTICES = 340


def _name_key(name: str) -> str:
    """Loose bone-name key: case-folded, Blender's ``.001`` duplicate
    suffix dropped, punctuation (``|``, ``_``, spaces) ignored."""
    name = re.sub(r"\.\d{3}$", "", name)
    return "".join(ch for ch in name.casefold() if ch.isalnum())


def match_joints(joint_names, bones: list[skeleton.Bone]) -> dict[str, int]:
    """glTF joint name -> game bone index, exact name first, then the loose
    :func:`_name_key` match. Unmatched names are left out."""
    exact: dict[str, int] = {}
    loose: dict[str, int] = {}
    for i, bone in enumerate(bones):
        exact.setdefault(bone.name, i)
        loose.setdefault(_name_key(bone.name), i)
    result = {}
    for name in joint_names:
        if name in exact:
            result[name] = exact[name]
        elif _name_key(name) in loose:
            result[name] = loose[_name_key(name)]
    return result


def _bone_weights(influences, matched: dict[str, int], joint_parents: dict[str, str], unmatched: set[str]):
    """glTF ``(joint, weight)`` pairs -> ``((bone, u8 weight), ...)``, heaviest
    first. Joints map to their bone or their nearest matched ancestor;
    weights are summed per bone, cut to :data:`MAX_BLEND_BONES`, and
    quantized to 1/256 steps that add up to 256 (the engine reads them as
    ``u8 / 256`` and does not renormalize). Empty when no joint matches."""
    per_bone: dict[int, float] = {}
    for joint, weight in influences:
        while joint is not None and joint not in matched:
            unmatched.add(joint)
            joint = joint_parents.get(joint)
        if joint is not None:
            per_bone[matched[joint]] = per_bone.get(matched[joint], 0.0) + weight
    pairs = sorted(per_bone.items(), key=lambda bw: (-bw[1], bw[0]))[:MAX_BLEND_BONES]
    while pairs:
        total = sum(w for _, w in pairs)
        quantized = [(b, round(w / total * 256)) for b, w in pairs]
        quantized[0] = (quantized[0][0], quantized[0][1] + 256 - sum(q for _, q in quantized))
        if all(q > 0 for _, q in quantized):
            return tuple(quantized)
        pairs = [pair for pair, (_, q) in zip(pairs, quantized) if q > 0]
    return ()


def _composite_layout(vertex_groups: list[tuple[tuple, list]]) -> tuple[list[tuple], dict, int]:
    """Place composite vertices the way every vanilla composite buffer does.

    Each weight record's vertices start in a fresh 32-byte block (the
    skinning routine moves every record in and out of the locked cache as
    whole 32-byte blocks), at its first multiple of 12 bytes. A record holds
    at most :data:`MAX_RECORD_VERTICES` vertices (one 4 KiB cache half).
    Returns the raw weight records, ``vertex -> slot`` and the slot count."""
    records: list[tuple] = []
    slots: dict = {}
    block = 0
    for influence, group in vertex_groups:
        for first in range(0, len(group), MAX_RECORD_VERTICES):
            part = group[first : first + MAX_RECORD_VERTICES]
            start = block + (-block) % 12
            add = start - block
            size = (add + 12 * len(part) + 31) // 32 * 32
            bones = [b for b, _ in influence] + [-1] * (4 - len(influence))
            # A one-bone record skips the weighting, and vanilla files store 0.
            weights = [w for _, w in influence] + [0] * (4 - len(influence)) if len(influence) > 1 else [0] * 4
            records.append((*bones, *weights, block, size, add, len(influence), len(part), 0))
            for i, vertex in enumerate(part):
                slots[vertex] = start // 12 + i
            block += size
    return records, slots, (block + 11) // 12


def build_skinned_gs(
    scene: ImportedScene,
    bones: list[skeleton.Bone],
    *,
    fallback_bone: int = 0,
    name: str = "imported",
    smooth: bool = True,
    pose_extent: Optional[float] = None,
    animations: tuple = (),
    composite_only: bool = False,
) -> StaticBuild:
    """Build a skinned ``.gs`` for an existing skeleton (Phases 2 and 5).

    Joints map to game bones by name (see :func:`match_joints`; an
    unmatched joint follows its nearest matched ancestor joint, then
    ``fallback_bone``). Vertices are stored in the skin's bind space (the
    glTF mesh space): the exporter writes stored vertices there, with
    inverse bind matrices that make the joints reproduce the engine's
    ``world x skin_matrix`` palette, so an exported body comes back
    unchanged and a re-weighted one follows its bones as in the glTF.

    - Triangles whose corners each follow one bone go to **multi-matrix**
      shapes (``flags & 2``): at most 10 subset bones each, one or more per
      material, each vertex carrying its slot as ``PNMTXIDX``
      (``slot x 3``).
    - With ``smooth``, triangles with a corner blending several bones go to
      one **composite** shape per material (``flags & 1``), which the engine
      skins on the CPU with up to four weighted bones per vertex. Its POS
      and NRM index the composite buffer. That buffer's positions and
      normals are ``s16`` with one fraction-bit count, and the posed output
      is written at the same precision (clamped), so it is sized for the
      largest coordinate the blended vertices reach: ``pose_extent`` if
      given, else measured over ``animations`` (the ``.ga`` files that will
      drive the model; 5% margin), else 8 x the bind-pose extent (battle
      animations move vertices up to about 5 x theirs). Without
      ``smooth``, every corner follows its heaviest bone.
    - With ``composite_only``, every triangle goes to composite shapes
      (one-bone vertices as one-bone records), the way every vanilla
      battle model (``zu/``) is built."""
    all_names = {
        joint for tris in scene.triangles.values() for t in tris if t.influences for inf in t.influences for joint, _ in inf
    }
    joint_names = all_names | set(scene.joint_parents) | {p for p in scene.joint_parents.values() if p}
    matched = match_joints(joint_names, bones)
    if all_names and not any(n in matched for n in all_names):
        raise GltfImportError(
            "None of the glTF joints match a bone of this skeleton. Export the model set with "
            "Export .glb and weight the new mesh to that armature."
        )
    warnings = list(scene.warnings)
    unmatched: set[str] = set()
    counts = {"blended": 0, "unbound": 0}

    def corner(tri: ImportedTriangle, k: int):
        """(((bone, u8 weight), ...), stored position, stored normal) for one
        corner. The glTF bind space is the game's stored space: the
        exporter writes stored vertices there, and it survives a tool
        re-orienting the joints."""
        bind = tri.bind[k] if tri.bind is not None else None
        if bind is None:
            bind = (tri.positions[k], tri.normals[k])
        position, normal = bind[0], bind[1] if bind[1] is not None else tri.normals[k]
        weights = _bone_weights(tri.influences[k] if tri.influences else (), matched, scene.joint_parents, unmatched)
        if not weights:
            counts["unbound"] += 1
            return ((fallback_bone, 256),), position, normal
        if len(weights) > 1:
            counts["blended"] += 1
            if not smooth:
                weights = ((weights[0][0], 256),)
        return weights, position, normal

    used_materials = [m for m in sorted(scene.triangles) if scene.triangles[m]]
    rigid: dict[int, list] = {}
    blended: dict[int, list] = {}
    for m in used_materials:
        rigid[m], blended[m] = [], []
        for t in scene.triangles[m]:
            corners = [corner(t, k) for k in range(3)]
            tri_positions, tri_normals = tuple(c[1] for c in corners), tuple(c[2] for c in corners)
            if not composite_only and all(len(c[0]) == 1 for c in corners):
                rigid[m].append((t, tuple(c[0][0][0] for c in corners), tri_positions, tri_normals))
            else:
                blended[m].append((t, tuple(c[0] for c in corners), tri_positions, tri_normals))

    parts = (rigid, blended)
    all_positions = [p for part in parts for tris in part.values() for _t, _b, ps, _n in tris for p in ps]
    all_uvs = [uv for part in parts for tris in part.values() for t, *_ in tris for uv in t.uvs]
    bind_extent = max(abs(c) for p in all_positions for c in p)
    pos_frac = _fraction_bits(bind_extent)
    uv_frac = _fraction_bits(max((abs(c) for uv in all_uvs for c in uv), default=0.0))
    if pose_extent is None and animations and any(blended.values()):
        boxes: dict[int, tuple] = {}
        for tris in blended.values():
            for _t, tri_weights, tri_positions, _n in tris:
                for weights, p in zip(tri_weights, tri_positions):
                    for bone, _w in weights:
                        lo, hi = boxes.get(bone, (p, p))
                        boxes[bone] = (tuple(map(min, lo, p)), tuple(map(max, hi, p)))
        pose_extent = 1.05 * engine_pose.posed_extent(bones, boxes, animations)
    skin_frac = _fraction_bits(max(pose_extent or 8.0 * bind_extent, bind_extent, 1.0))

    positions: dict[tuple, int] = {}
    normals: dict[tuple, int] = {}
    uvs: dict[tuple, int] = {}
    colors: dict[tuple, int] = {}
    skinned: dict[tuple, dict] = {}  # influence -> its composite vertices, in first-use order

    def index_of(table: dict, key) -> int:
        if key not in table:
            table[key] = len(table)
        return table[key]

    images: list[Image.Image] = []
    materials: list[gs_file.GsMaterial] = []
    meshes: list[gs_file.GsMesh] = []
    chunks: list[gs_file.GsChunk] = []
    composite_shapes: list[tuple[gs_file.GsChunk, list[list[int]], list[tuple], bool]] = []
    model_min, model_max = [math.inf] * 3, [-math.inf] * 3

    def extend_bounds(bounds_min, bounds_max, p) -> None:
        for axis in range(3):
            bounds_min[axis] = min(bounds_min[axis], p[axis])
            bounds_max[axis] = max(bounds_max[axis], p[axis])

    def strips_of(game_tris: list[tuple[int, int, int]]) -> list[list[int]]:
        strips = stripify(game_tris)
        if any(len(strip) > 0xFFFF for strip in strips):
            raise GltfImportError("A triangle strip is longer than 65,535 vertices.")
        return strips

    for mat_index in used_materials:
        src = _source_material(scene, mat_index)
        materials.append(_material_record(src, _image_index(images, src.image)))
        has_color = any(t.colors is not None for part in parts for t, *_ in part[mat_index])
        cull = FLAG_CULL_NONE if src.double_sided else FLAG_CULL_BACK

        def tail(tri: ImportedTriangle, k: int) -> tuple:
            """UV index, then color index when the shape has colors."""
            key = (index_of(uvs, tuple(_quantize(c, uv_frac, -32768, 32767) for c in tri.uvs[k])),)
            if has_color:
                key += (index_of(colors, tuple(tri.colors[k]) if tri.colors else (255, 255, 255, 255)),)
            return key

        # Shapes of at most 10 bones; sorting by bone set keeps neighbouring
        # body parts in the same shape.
        groups: list[tuple[set[int], list]] = []
        for entry in sorted(rigid[mat_index], key=lambda e: tuple(sorted(set(e[1])))):
            tri_bones = entry[1]
            if not groups or len(groups[-1][0] | set(tri_bones)) > MAX_SUBSET_BONES:
                groups.append((set(), []))
            groups[-1][0].update(tri_bones)
            groups[-1][1].append(entry)

        for bone_set, tris in groups:
            subset = sorted(bone_set)
            slot = {b: i for i, b in enumerate(subset)}
            keys: dict[tuple, int] = {}
            key_list: list[tuple] = []
            game_tris = []
            shape_min, shape_max = [math.inf] * 3, [-math.inf] * 3
            for tri, tri_bones, tri_positions, tri_normals in tris:
                corner_keys = []
                for k in range(3):
                    p = tri_positions[k]
                    qp = tuple(_quantize(c, pos_frac, -32768, 32767) for c in p)
                    qn = tuple(_quantize(c, NORMAL_FRAC, -128, 127) for c in tri_normals[k])
                    key = (slot[tri_bones[k]], index_of(positions, qp), index_of(normals, qn)) + tail(tri, k)
                    if key not in keys:
                        keys[key] = len(key_list)
                        key_list.append(key)
                    corner_keys.append(keys[key])
                    extend_bounds(shape_min, shape_max, p)
                a_, b_, c_ = corner_keys
                game_tris.append((a_, c_, b_))  # glTF counter-clockwise -> game clockwise

            dl = bytearray()
            for strip in strips_of(game_tris):
                dl += struct.pack(">BH", 0x98, len(strip))
                for vertex in strip:
                    si, pi, ni, ui, *ci = key_list[vertex]
                    dl += struct.pack(">BHH", si * 3, pi, ni)
                    if has_color:
                        dl += struct.pack(">H", ci[0])
                    dl += struct.pack(">H", ui)
            dl += bytes(-len(dl) % 32)
            extend_bounds(model_min, model_max, shape_min)
            extend_bounds(model_min, model_max, shape_max)

            meshes.append(gs_file.GsMesh("none", tuple(shape_min), tuple(shape_max), subset[0]))  # type: ignore[arg-type]
            chunks.append(
                gs_file.GsChunk(
                    mesh_index=len(meshes) - 1,
                    flags=src.pass_flag | FLAG_MULTI_MATRIX | cull,
                    material_index=len(materials) - 1,
                    bone=0,
                    cache_slot=0,
                    attr_mask=ATTR_PNMTXIDX | ATTR_POS | ATTR_NRM | ATTR_TEX0 | (ATTR_CLR0 if has_color else 0),
                    display_list=bytes(dl),
                    bone_subset=subset,
                )
            )

        if blended[mat_index]:
            keys = {}
            key_list = []
            game_tris = []
            shape_min, shape_max = [math.inf] * 3, [-math.inf] * 3
            bone_use: dict[int, int] = {}
            for tri, tri_weights, tri_positions, tri_normals in blended[mat_index]:
                corner_keys = []
                for k in range(3):
                    p = tri_positions[k]
                    vertex = (
                        tri_weights[k],
                        tuple(_quantize(c, skin_frac, -32768, 32767) for c in p),
                        tuple(_quantize(c, skin_frac, -32768, 32767) for c in _normalize(tri_normals[k])),
                    )
                    skinned.setdefault(tri_weights[k], {}).setdefault(vertex, None)
                    key = (vertex,) + tail(tri, k)
                    if key not in keys:
                        keys[key] = len(key_list)
                        key_list.append(key)
                    corner_keys.append(keys[key])
                    extend_bounds(shape_min, shape_max, p)
                    bone_use[tri_weights[k][0][0]] = bone_use.get(tri_weights[k][0][0], 0) + 1
                a_, b_, c_ = corner_keys
                game_tris.append((a_, c_, b_))
            extend_bounds(model_min, model_max, shape_min)
            extend_bounds(model_min, model_max, shape_max)
            # The draw path ignores a composite shape's bone; vanilla shapes
            # name a bone of the part anyway.
            main_bone = max(bone_use, key=lambda b: bone_use[b])
            meshes.append(gs_file.GsMesh("none", tuple(shape_min), tuple(shape_max), main_bone))  # type: ignore[arg-type]
            chunk = gs_file.GsChunk(
                mesh_index=len(meshes) - 1,
                flags=src.pass_flag | FLAG_COMPOSITE | cull,
                material_index=len(materials) - 1,
                bone=main_bone,
                cache_slot=0,
                attr_mask=ATTR_POS | ATTR_NRM | ATTR_TEX0 | (ATTR_CLR0 if has_color else 0),
                display_list=b"",
                bone_subset=None,
            )
            chunks.append(chunk)
            composite_shapes.append((chunk, strips_of(game_tris), key_list, has_color))

    composite = None
    if skinned:
        # One-vertex records first, then the shared ones, as in vanilla
        # files; the header's last field counts the shared ones.
        vertex_groups = sorted(((w, list(vs)) for w, vs in skinned.items()), key=lambda item: len(item[1]) > 1)
        records, slots, slot_count = _composite_layout(vertex_groups)
        if slot_count > MAX_INDEX + 1:
            raise GltfImportError(f"Too many blended vertices ({slot_count} slots); the game indexes them with 16 bits.")
        vertices = [(0, 0, 0, 0, 0, 0)] * slot_count
        for vertex, index in slots.items():
            vertices[index] = vertex[1] + vertex[2]
        composite = gs_file.GsComposite(
            weights=records,
            vertices=vertices,
            unk0=skin_frac << 8,
            unk1=sum(1 for record in records if record[12] > 1),
        )
        for chunk, strips, key_list, has_color in composite_shapes:
            dl = bytearray()
            for strip in strips:
                dl += struct.pack(">BH", 0x98, len(strip))
                for vertex in strip:
                    skin_vertex, ui, *ci = key_list[vertex]
                    index = slots[skin_vertex]
                    dl += struct.pack(">HH", index, index)
                    if has_color:
                        dl += struct.pack(">H", ci[0])
                    dl += struct.pack(">H", ui)
            dl += bytes(-len(dl) % 32)
            chunk.display_list = bytes(dl)

    for table, label in ((positions, "positions"), (normals, "normals"), (uvs, "UVs"), (colors, "colors")):
        if len(table) > MAX_INDEX + 1:
            raise GltfImportError(f"Too many distinct {label} ({len(table)}); the game indexes them with 16 bits.")

    if unmatched:
        warnings.append(
            "Joints with no bone of the same name (their vertices follow the nearest matching parent joint): "
            + ", ".join(sorted(unmatched))
        )
    if counts["unbound"]:
        warnings.append(f"{counts['unbound']} vertices have no joint and follow bone {bones[fallback_bone].name!r}.")
    if counts["blended"] and not smooth:
        warnings.append(
            f"{counts['blended']} vertices blend several joints; each follows only its heaviest joint (rigid skinning)."
        )

    joint_map: dict[str, tuple[str, str]] = {}
    for joint in sorted(all_names | set(matched)):
        ancestor = joint
        while ancestor is not None and ancestor not in matched:
            ancestor = scene.joint_parents.get(ancestor)
        if ancestor == joint:
            joint_map[joint] = (bones[matched[joint]].name, "name")
        elif ancestor is not None:
            joint_map[joint] = (bones[matched[ancestor]].name, f"parent {ancestor}")
        else:
            joint_map[joint] = (bones[fallback_bone].name, "fallback")

    gs = gs_file.GsFile(
        root_name="unknown",
        date=EXPORT_DATE,
        model_id=zlib.crc32(name.encode("utf-8")),
        bbox_min=tuple(model_min),  # type: ignore[arg-type]
        bbox_max=tuple(model_max),  # type: ignore[arg-type]
        pos_frac=pos_frac,
        norm_frac=NORMAL_FRAC,
        uv_frac=uv_frac,
        positions=list(positions),
        normals=list(normals),
        uvs=list(uvs),
        colors=list(colors),
        materials=materials,
        meshes=meshes,
        chunk_lists=_chunk_lists(chunks),
        composite=composite,
    )
    return StaticBuild(gs, images, warnings, joint_map)


def composite_range_excess(gs: gs_file.GsFile, bones: list[skeleton.Bone], animations) -> Optional[float]:
    """How far ``animations`` push the composite (blended) vertices of
    ``gs`` beyond what its ``s16`` buffer holds, as a ratio (``> 1`` means
    the engine clamps them), or ``None`` when the model has no composite
    buffer."""
    comp = gs.composite
    if comp is None or not comp.weights:
        return None
    shift = comp.unk0 >> 8
    boxes: dict[int, tuple] = {}
    for record in comp.weights:
        first = (record[8] + record[10]) // 12
        points = [tuple(c / (1 << shift) for c in v[:3]) for v in comp.vertices[first : first + record[12]]]
        for bone in record[: record[11]]:
            for p in points:
                lo, hi = boxes.get(bone, (p, p))
                boxes[bone] = (tuple(map(min, lo, p)), tuple(map(max, hi, p)))
    return engine_pose.posed_extent(bones, boxes, animations) / (32767 / (1 << shift))


def import_skinned_model(
    gltf_data: bytes,
    skeleton_data: bytes,
    *,
    fallback_bone: Optional[int] = None,
    base_dir: Optional[Path | str] = None,
    name: str = "imported",
    smooth: bool = True,
    pose_extent: Optional[float] = None,
    animations: tuple = (),
) -> tuple[bytes, list[Image.Image], list[str]]:
    """glTF bytes -> ``(.gs bytes, texture images in tex_id order,
    warnings)`` for the skeleton in ``skeleton_data``, which stays as it is.
    ``fallback_bone`` (default: the first root bone) takes geometry with no
    joint. ``smooth``, ``pose_extent`` and ``animations`` (parsed ``.ga``
    files) go to :func:`build_skinned_gs`. Texture files are left to the
    caller: a character's texture file is chosen per unit (``tex_N.tpl``),
    see ``model_viewer``."""
    build = import_skinned_build(
        gltf_data,
        skeleton_data,
        fallback_bone=fallback_bone,
        base_dir=base_dir,
        name=name,
        smooth=smooth,
        pose_extent=pose_extent,
        animations=animations,
    )
    return gs_file.write_gs(build.gs), build.images, build.warnings


def import_skinned_build(
    gltf_data: bytes,
    skeleton_data: bytes,
    *,
    fallback_bone: Optional[int] = None,
    base_dir: Optional[Path | str] = None,
    name: str = "imported",
    smooth: bool = True,
    pose_extent: Optional[float] = None,
    animations: tuple = (),
    composite_only: bool = False,
) -> StaticBuild:
    """:func:`import_skinned_model` returning the whole build (the
    unwritten :class:`gs_file.GsFile`, images, warnings and joint map).
    ``composite_only`` goes to :func:`build_skinned_gs` (battle models)."""
    bones = skeleton.read_skeleton_file(skeleton_data).bones
    if not bones:
        raise GltfImportError("The skeleton has no bones.")
    if fallback_bone is None:
        fallback_bone = next((i for i, b in enumerate(bones) if not 0 <= b.parent_index < len(bones)), 0)
    scene = read_gltf(gltf_data, base_dir)
    return build_skinned_gs(
        scene,
        bones,
        fallback_bone=fallback_bone,
        name=name,
        smooth=smooth,
        pose_extent=pose_extent,
        animations=animations,
        composite_only=composite_only,
    )


# ---------------------------------------------------------------- animation import

#: Largest error a dropped keyframe may introduce, per value slot family.
KEY_TOLERANCE = {"scale": 5e-4, "rotate": 0.02, "translate": 2e-3}
MAX_SHIFT = 15


def _sampler_value(times, values, interpolation: str, t: float, is_rotation: bool):
    """glTF sampler value at time ``t`` (LINEAR / STEP / CUBICSPLINE)."""
    cubic = interpolation == "CUBICSPLINE"

    def key(i):
        return values[i * 3 + 1] if cubic else values[i]

    if t <= times[0]:
        return tuple(key(0))
    if t >= times[-1]:
        return tuple(key(len(times) - 1))
    lo, hi = 0, len(times) - 1
    while hi - lo > 1:
        mid = (lo + hi) // 2
        if times[mid] <= t:
            lo = mid
        else:
            hi = mid
    t0, t1 = times[lo], times[hi]
    u = (t - t0) / (t1 - t0) if t1 > t0 else 0.0
    if interpolation == "STEP":
        return tuple(key(lo))
    a, b = key(lo), key(hi)
    if cubic:
        dt = t1 - t0
        m0, m1 = values[lo * 3 + 2], values[hi * 3]
        u2, u3 = u * u, u * u * u
        out = tuple(
            (2 * u3 - 3 * u2 + 1) * a[i] + (u3 - 2 * u2 + u) * dt * m0[i] + (-2 * u3 + 3 * u2) * b[i] + (u3 - u2) * dt * m1[i]
            for i in range(len(a))
        )
        if is_rotation:
            n = math.sqrt(sum(c * c for c in out)) or 1.0
            out = tuple(c / n for c in out)
        return out
    if is_rotation:  # slerp
        dot = sum(x * y for x, y in zip(a, b))
        if dot < 0:
            b, dot = tuple(-c for c in b), -dot
        if dot > 0.9995:
            out = tuple(x + (y - x) * u for x, y in zip(a, b))
        else:
            theta = math.acos(dot)
            sa, sb = math.sin((1 - u) * theta), math.sin(u * theta)
            out = tuple((x * sa + y * sb) / math.sin(theta) for x, y in zip(a, b))
        n = math.sqrt(sum(c * c for c in out)) or 1.0
        return tuple(c / n for c in out)
    return tuple(x + (y - x) * u for x, y in zip(a, b))


def _trs_matrix(t, r, s) -> list[float]:
    return _node_matrix({"translation": t, "rotation": r, "scale": s})


def _to_3x4(m: list[float]) -> skeleton.Mat3x4:
    return tuple(tuple(m[c * 4 + r] for c in range(4)) for r in range(3))  # type: ignore[return-value]


def _solve_values(bone: skeleton.Bone, local: skeleton.Mat3x4, previous) -> tuple[list[float], float]:
    """Value block that makes the engine rebuild ``local`` for ``bone``
    (all channel bits set): scale, Euler rotation and translation are solved,
    every other slot keeps the skeleton's value. Returns the values and the
    largest matrix error (non-zero only for shear the rig can't express)."""
    flags = engine_pose.bone_flags(bone) | engine_pose.ALL_CHANNELS
    order = engine_pose.rotation_order(bone)
    values = engine_pose.bone_values(bone)
    m3 = [list(row[:3]) for row in local]
    if flags & engine_pose.FLAG_JOINT_ORIENT:
        jo = engine_pose.euler_matrix(order, *values[engine_pose.SLOT_JOINT_ORIENT : engine_pose.SLOT_JOINT_ORIENT + 3])
        m3 = [[sum(jo[k][r] * m3[k][c] for k in range(3)) for c in range(3)] for r in range(3)]  # jo^T x m3
    unit, scale = engine_pose.orthonormal_columns([[m3[r][c] for r in range(3)] for c in range(3)])
    rot = [[unit[c][r] for c in range(3)] for r in range(3)]
    if flags & engine_pose.FLAG_ROTATE_AXIS:
        ra = engine_pose.euler_matrix(order, *values[engine_pose.SLOT_ROTATE_AXIS : engine_pose.SLOT_ROTATE_AXIS + 3])
        rot = [[sum(rot[r][k] * ra[c][k] for k in range(3)) for c in range(3)] for r in range(3)]  # rot x ra^T
    values[engine_pose.SLOT_SCALE : engine_pose.SLOT_SCALE + 3] = scale
    values[engine_pose.SLOT_ROTATE : engine_pose.SLOT_ROTATE + 3] = engine_pose.euler_from_matrix(rot, previous)
    values[engine_pose.SLOT_TRANSLATE : engine_pose.SLOT_TRANSLATE + 3] = [0.0, 0.0, 0.0]
    base = engine_pose.local_matrix(values, flags, order)
    values[engine_pose.SLOT_TRANSLATE : engine_pose.SLOT_TRANSLATE + 3] = [local[r][3] - base[r][3] for r in range(3)]
    check = engine_pose.local_matrix(values, flags, order)
    error = max(abs(check[r][c] - local[r][c]) for r in range(3) for c in range(4))
    return values, error


def _reduce_keys(samples: list[float], shift: int, tolerance: float) -> list[animation.Keyframe]:
    """Integer keys for per-frame ``samples``: a key is dropped when the
    engine's linear interpolation between the kept neighbours reproduces
    every skipped frame within ``tolerance``."""
    scale = float(1 << shift)
    q = [max(-32768, min(32767, round(v * scale))) for v in samples]
    tol = max(tolerance * scale, 0.5)
    keys = [0]
    start = 0
    while start < len(q) - 1:
        end = start + 1
        while end + 1 < len(q):
            candidate = end + 1
            ok = all(
                abs(q[start] + (q[candidate] - q[start]) * (f - start) / (candidate - start) - q[f]) <= tol
                for f in range(start + 1, candidate)
            )
            if not ok:
                break
            end = candidate
        keys.append(end)
        start = end
    return [animation.Keyframe(f, q[f]) for f in keys]


def _shift_for(samples: list[float]) -> int:
    peak = max((abs(v) for v in samples), default=0.0)
    shift = MAX_SHIFT
    while shift > 0 and peak * (1 << shift) > 32767:
        shift -= 1
    if peak * (1 << shift) > 32767:
        raise GltfImportError(f"An animated value ({peak:g}) is too large for the game's 16-bit keys.")
    return shift


def list_animations(gltf_data: bytes, base_dir: Optional[Path | str] = None) -> list[str]:
    doc = _Document(gltf_data, Path(base_dir) if base_dir is not None else None).doc
    return [a.get("name") or f"animation{i}" for i, a in enumerate(doc.get("animations", []))]


def import_animation(
    gltf_data: bytes,
    skeleton_data: bytes,
    *,
    animation_name: Optional[str] = None,
    template: Optional[bytes] = None,
    fps: float = 60.0,
    base_dir: Optional[Path | str] = None,
) -> tuple[bytes, list[str]]:
    """One glTF animation -> ``(.ga bytes, warnings)`` for the skeleton in
    ``skeleton_data`` (Phase 3 of ``research/MODEL_IMPORT_PLAN.md``).

    Each frame (``fps`` frames per second) the glTF joints are posed, and a
    bone matched by name gets the engine world matrix that deforms its
    vertices as the joint does in the glTF (``joint x inverse_bind x
    skin_matrix^-1``; see :mod:`engine_pose`). Its local matrix is solved
    into scale / rotation / translation values, keys the engine's linear
    interpolation reproduces are dropped, and curves equal to the
    skeleton's own value are omitted. Unmatched bones keep their rest pose.

    Events and loop settings come from the glTF animation's ``extras`` (as
    :mod:`gltf_export` writes them) or else from ``template`` - the vanilla
    ``.ga`` being replaced -, retimed to the new length. Battle animations
    need their events (the hit frame, sounds): an attack with none will not
    hit."""
    d = _Document(gltf_data, Path(base_dir) if base_dir is not None else None)
    doc = d.doc
    anims = doc.get("animations", [])
    if not anims:
        raise GltfImportError("The glTF file has no animations.")
    names = [a.get("name") or f"animation{i}" for i, a in enumerate(anims)]
    if animation_name is None:
        chosen = anims[0]
    elif animation_name in names:
        chosen = anims[names.index(animation_name)]
    else:
        raise GltfImportError(f"No animation named {animation_name!r} (found: {', '.join(names)}).")
    bones = skeleton.read_skeleton_file(skeleton_data).bones
    if any(engine_pose.rotation_order(b) != 1 for b in bones):
        raise GltfImportError("The skeleton uses a rotation order other than XYZ; not supported.")
    warnings: list[str] = []

    nodes = doc.get("nodes", [])
    parents = {c: i for i, n in enumerate(nodes) for c in n.get("children", [])}
    node_names = [n.get("name") or f"node{i}" for i, n in enumerate(nodes)]
    skins = doc.get("skins", [])
    joint_nodes = [j for s in skins for j in s.get("joints", [])] or list(range(len(nodes)))
    matched_nodes = {}
    by_name = match_joints([node_names[j] for j in joint_nodes], bones)
    for j in joint_nodes:
        if node_names[j] in by_name and by_name[node_names[j]] not in matched_nodes.values():
            matched_nodes[j] = by_name[node_names[j]]
    if not matched_nodes:
        raise GltfImportError("None of the glTF joints match a bone of this skeleton.")

    # inverse bind per joint node (a joint outside any skin binds at rest)
    rest_cache: dict[int, list[float]] = {}

    def rest_world(i: int) -> list[float]:
        if i not in rest_cache:
            local = _node_matrix(nodes[i])
            rest_cache[i] = _mat4_mul(rest_world(parents[i]), local) if i in parents else local
        return rest_cache[i]

    inverse_binds: dict[int, list[float]] = {}
    for skin in skins:
        ibms = d.accessor(skin["inverseBindMatrices"]) if "inverseBindMatrices" in skin else None
        for k, j in enumerate(skin.get("joints", [])):
            inverse_binds.setdefault(j, list(ibms[k]) if ibms else _invert_4x4(rest_world(j)))

    tracks: dict[tuple[int, str], tuple] = {}
    duration = 0.0
    for channel in chosen.get("channels", []):
        target = channel.get("target", {})
        if "node" not in target or target.get("path") not in ("translation", "rotation", "scale"):
            continue
        sampler = chosen["samplers"][channel["sampler"]]
        times = [v[0] for v in d.accessor(sampler["input"])]
        values = d.accessor(sampler["output"])
        tracks[(target["node"], target["path"])] = (times, values, sampler.get("interpolation", "LINEAR"))
        duration = max(duration, times[-1] if times else 0.0)
    last_frame = max(1, round(duration * fps))

    def rest_trs(node: dict):
        return (
            tuple(node.get("translation", (0.0, 0.0, 0.0))),
            tuple(node.get("rotation", (0.0, 0.0, 0.0, 1.0))),
            tuple(node.get("scale", (1.0, 1.0, 1.0))),
        )

    seed = engine_pose.local_matrices(bones)
    skins_inv = {b: engine_pose.invert_3x4(engine_pose.skin_matrix(bones[b])) for b in matched_nodes.values()}
    node_of_bone = {b: j for j, b in matched_nodes.items()}
    per_bone: dict[int, list[list[float]]] = {b: [] for b in node_of_bone}
    worst = 0.0
    for frame in range(last_frame + 1):
        t = frame / fps
        world_cache: dict[int, list[float]] = {}

        local_cache: dict[int, list[float]] = {}

        def node_local(i: int) -> list[float]:
            if i not in local_cache:
                node = nodes[i]
                if "matrix" in node:
                    local_cache[i] = list(node["matrix"])
                else:
                    tr, ro, sc = rest_trs(node)
                    parts = {"translation": tr, "rotation": ro, "scale": sc}
                    for path in parts:
                        if (i, path) in tracks:
                            times, values, interp = tracks[(i, path)]
                            parts[path] = _sampler_value(times, values, interp, t, path == "rotation")
                    local_cache[i] = _trs_matrix(parts["translation"], parts["rotation"], parts["scale"])
            return local_cache[i]

        def node_world(i: int) -> list[float]:
            if i not in world_cache:
                world_cache[i] = _mat4_mul(node_world(parents[i]), node_local(i)) if i in parents else node_local(i)
            return world_cache[i]

        def chain_between(ancestor: int, i: int) -> Optional[list[float]]:
            """Product of the node transforms from below ``ancestor`` down to
            ``i`` (None when ``ancestor`` is not an ancestor of ``i``)."""
            m = _node_matrix({})
            while i != ancestor:
                if i not in parents:
                    return None
                m = _mat4_mul(node_local(i), m)
                i = parents[i]
            return m

        world: list[Optional[skeleton.Mat3x4]] = [None] * len(bones)

        def bone_world(b: int) -> skeleton.Mat3x4:
            if world[b] is None:
                if b in node_of_bone:
                    j = node_of_bone[b]
                    deform = _to_3x4(_mat4_mul(node_world(j), inverse_binds.get(j) or _invert_4x4(rest_world(j))))
                    world[b] = skeleton.mul_3x4(deform, skins_inv[b])
                else:
                    parent = bones[b].parent_index
                    parent_world = bone_world(parent) if 0 <= parent < len(bones) and parent != b else skeleton.IDENTITY_3X4
                    world[b] = skeleton.mul_3x4(parent_world, seed[b])
            return world[b]  # type: ignore[return-value]

        for b in node_of_bone:
            parent = bones[b].parent_index
            j = node_of_bone[b]
            chain = chain_between(node_of_bone[parent], j) if parent in node_of_bone else None
            if chain is not None:
                # parent^-1 x bone without inverting the parent's world, which is
                # singular when the parent is scaled to 0 (a hidden weapon):
                # skin_p x IBM_p^-1 x (joint chain) x IBM_j x skin_b^-1
                jp = node_of_bone[parent]
                ibm_p = inverse_binds.get(jp) or _invert_4x4(rest_world(jp))
                ibm_j = inverse_binds.get(j) or _invert_4x4(rest_world(j))
                middle = _to_3x4(_mat4_mul(_invert_4x4(ibm_p), _mat4_mul(chain, ibm_j)))
                local = skeleton.mul_3x4(
                    skeleton.mul_3x4(engine_pose.skin_matrix(bones[parent]), middle), skins_inv[b]
                )
            else:
                parent_world = bone_world(parent) if 0 <= parent < len(bones) and parent != b else skeleton.IDENTITY_3X4
                local = skeleton.mul_3x4(engine_pose.invert_3x4(parent_world), bone_world(b))
            previous = per_bone[b][-1][engine_pose.SLOT_ROTATE : engine_pose.SLOT_ROTATE + 3] if per_bone[b] else None
            values, error = _solve_values(bones[b], local, previous)
            worst = max(worst, error)
            per_bone[b].append(values)
    if worst > 1e-3:
        warnings.append(f"Some joint transforms have shear the game can't represent (error up to {worst:.3g}).")

    families = (("scale", engine_pose.SLOT_SCALE, engine_pose.FLAG_SCALE),
                ("rotate", engine_pose.SLOT_ROTATE, engine_pose.FLAG_ROTATE),
                ("translate", engine_pose.SLOT_TRANSLATE, engine_pose.FLAG_TRANSLATE))
    groups: list[animation.BoneGroup] = []
    curves: list[animation.AnimCurve] = []
    for b in sorted(per_bone):
        defaults = engine_pose.bone_values(bones[b])
        bone_curves, mask = [], 0
        for family, slot, flag in families:
            tol = KEY_TOLERANCE[family]
            family_curves = []
            for axis in range(3):
                samples = [v[slot + axis] for v in per_bone[b]]
                if all(abs(x - defaults[slot + axis]) <= tol for x in samples):
                    continue
                shift = _shift_for(samples)
                keys = _reduce_keys(samples, shift, tol)
                family_curves.append(animation.AnimCurve(b, slot + axis, shift, keys[-1].frame, keys))
            if family_curves or (family == "translate" and any(defaults[slot : slot + 3])) or (
                family == "scale" and any(abs(c - 1.0) > 1e-9 for c in defaults[slot : slot + 3])
            ):
                mask |= flag
            bone_curves += family_curves
        if not bone_curves:
            continue
        mask |= engine_pose.FLAG_ROTATE
        groups.append(animation.BoneGroup(b, mask, len(curves), len(bone_curves)))
        curves += bone_curves
    unmatched = sorted(node_names[j] for j in joint_nodes if j not in matched_nodes and any(k[0] == j for k in tracks))
    if unmatched:
        warnings.append("Animated joints with no bone of the same name (ignored): " + ", ".join(unmatched))

    # Loop settings and events: glTF extras, else the replaced animation.
    extras = chosen.get("extras", {}) if isinstance(chosen.get("extras"), dict) else {}
    template_anim = animation.read_animation_bytes(template) if template else None
    words = list(template_anim.header.words) if template_anim else [0] * 12
    words[3] = animation.FORMAT_EULER_INT16
    events: list[animation.EventKey] = []
    if "events" in extras:
        events = [animation.EventKey(int(f), tuple(int(c) for c in codes)) for f, codes in extras["events"]]
        words[4] = 1 if extras.get("loops") else 0
        words[5] = int(extras.get("loop_start", 1))
    elif template_anim is not None:
        old_end = max(template_anim.header.end_frame, 1)
        ratio = last_frame / old_end
        events = [animation.EventKey(min(last_frame, round(e.frame * ratio)), e.codes) for e in template_anim.events]
        if template_anim.events and old_end != last_frame:
            warnings.append(f"Events copied from the replaced animation and retimed from {old_end} to {last_frame} frames.")
    else:
        words[4], words[5] = 0, 1
        warnings.append("No events: the animation has none in its glTF extras and no animation is being replaced.")
    words[5] = min(words[5], last_frame)
    words[6] = last_frame
    for slot in (1, 2, 10):
        words[slot] = 0

    footer = None
    if template_anim is not None and template_anim.footer is not None:
        footer = animation.GaFooter(
            blocks=list(template_anim.footer.blocks),
            order=list(template_anim.footer.order),
            pad_word=template_anim.footer.pad_word,
            trailing=template_anim.footer.trailing,
        )
    if events:
        footer = footer or animation.GaFooter()
        footer.blocks[0] = animation.write_event_block(events)
        if 0 not in footer.order:
            footer.order = [0] + footer.order
            footer.trailing = b""
    elif footer is not None and footer.blocks[0] is not None:
        footer.blocks[0] = None
        footer.order = [s for s in footer.order if s != 0]

    ga = animation.GaAnimation(
        header=animation.GaHeader(tuple(words)), groups=groups, curves=curves, events=events, footer=footer
    )
    return animation.write_animation(ga), warnings


# ---------------------------------------------------------------- new skeletons

#: Bone flags of an ordinary character bone: rotate pivot + scale pivot.
RIG_BONE_FLAGS = 0x180
MAX_BONES = 0xFF


def is_anchor_name(name: str) -> bool:
    """Names wrapped in underscores (``_s1_``, ``_sw1_``...). The loader flags
    these bones (``0x80000000``) and they are the only ones the engine finds
    by name (``find_matching_record_index_in_list``, ``0x8006135C``): shadow
    and foot points, weapon-trail ends, camera and effect anchors."""
    return len(name) > 2 and name.startswith("_") and name.endswith("_")


#: Battle-rig bone flags (``zu/`` skeletons): translate plus two low bits.
BATTLE_BONE_FLAGS = 0x26


def build_skeleton(
    gltf_data: bytes,
    base_dir: Optional[Path | str] = None,
    *,
    template: Optional[list[skeleton.Bone]] = None,
) -> tuple[skeleton.SkeletonFile, list[str]]:
    """A new ``.g`` from the glTF's skin (Phase 4). Joint names become bone
    names; parents come first.

    Without ``template``, in the convention map-model rigs use: identity
    skinning matrix, rotate and scale pivot at the joint's bind position
    (from its inverse bind matrix), every other value at rest, flags
    ``0x180``, identity seed matrix. The bind pose then draws stored
    vertices where they are and a bone turns about its joint.

    With ``template`` (the old skeleton of a battle model), each bone takes
    the convention of the template bone of the same name, and new bones the
    battle one: the parent-relative bind offset as translation (and seed
    matrix), no pivot, the inverse bind position as skinning matrix, flags
    ``0x26`` (the template's own when it has one). A template bone with
    flags 0 (a socket following its parent) stays so, wherever the glTF
    puts it; template pivot bones keep the pivot convention. The engine attaches weapons to battle socket
    bones (``_r_hand_``) by their world matrix, which the pivot convention
    would leave at the origin. :func:`import_skinned_model` and
    :func:`import_animation` work on either."""
    d = _Document(gltf_data, Path(base_dir) if base_dir is not None else None)
    doc = d.doc
    skins = doc.get("skins", [])
    if not skins:
        raise GltfImportError("The glTF file has no skin (armature) to build a skeleton from.")
    warnings: list[str] = []
    skin = max(skins, key=lambda s: len(s.get("joints", [])))
    if len(skins) > 1:
        warnings.append(f"The file has {len(skins)} skins; the skeleton is built from the largest ({len(skin['joints'])} joints).")
    joints = list(skin["joints"])
    if len(joints) > MAX_BONES:
        raise GltfImportError(f"The armature has {len(joints)} joints; the game allows at most {MAX_BONES}.")
    nodes = doc.get("nodes", [])
    names = [nodes[j].get("name") or f"joint{k}" for k, j in enumerate(joints)]
    if len(set(names)) != len(names):
        dupes = sorted({n for n in names if names.count(n) > 1})
        raise GltfImportError("Joint names must be unique: " + ", ".join(dupes))
    for n in names:
        try:
            n.encode("ascii")
        except UnicodeEncodeError:
            raise GltfImportError(f"Joint name {n!r} is not plain ASCII.") from None
    parents = {c: i for i, n in enumerate(nodes) for c in n.get("children", [])}
    joint_set = set(joints)

    def joint_parent(j: int) -> Optional[int]:
        p = parents.get(j)
        while p is not None and p not in joint_set:
            p = parents.get(p)
        return p

    ibms = d.accessor(skin["inverseBindMatrices"]) if "inverseBindMatrices" in skin else None
    # parents before children, otherwise in joint order
    children: dict[Optional[int], list[int]] = {}
    for j in joints:
        children.setdefault(joint_parent(j), []).append(j)
    order: list[int] = []
    stack = list(reversed(children.get(None, [])))
    while stack:
        j = stack.pop()
        order.append(j)
        stack.extend(reversed(children.get(j, [])))
    index = {j: i for i, j in enumerate(order)}

    def bind_position(j: int) -> tuple[float, float, float]:
        k = joints.index(j)
        if ibms is not None:
            bind = _invert_4x4(list(ibms[k]))
        else:
            bind, walk = _node_matrix(nodes[j]), j
            while walk in parents:
                walk = parents[walk]
                bind = _mat4_mul(_node_matrix(nodes[walk]), bind)
        return (bind[12], bind[13], bind[14])

    old = {b.name: b for b in template} if template is not None else {}
    # where each built bone's rest world matrix puts the origin of its children
    origin: dict[int, tuple[float, float, float]] = {}
    bones = []
    for j in order:
        k = joints.index(j)
        pivot = bind_position(j)
        parent = joint_parent(j)
        values = [0.0] * engine_pose.VALUE_COUNT
        values[engine_pose.SLOT_SCALE : engine_pose.SLOT_SCALE + 3] = [1.0, 1.0, 1.0]
        source = old.get(names[k])
        old_flags = engine_pose.bone_flags(source) if source is not None else None
        battle = template is not None and not (old_flags is not None and old_flags & engine_pose.FLAG_ROTATE_PIVOT)
        if battle:
            base = origin[parent] if parent is not None else (0.0, 0.0, 0.0)
            offset = tuple(a - b for a, b in zip(pivot, base))
            flags = BATTLE_BONE_FLAGS if old_flags is None else old_flags
            if flags & engine_pose.FLAG_TRANSLATE:
                values[engine_pose.SLOT_TRANSLATE : engine_pose.SLOT_TRANSLATE + 3] = offset
                values[31:43] = [c for row in engine_pose.translation(*offset) for c in row]
                origin[j] = tuple(a + b for a, b in zip(base, offset))
                skin = engine_pose.translation(*(-c for c in origin[j]))
            else:  # a socket that follows its parent (vanilla flags 0): identity skin, no offset
                values[31:43] = [c for row in skeleton.IDENTITY_3X4 for c in row]
                origin[j] = base
                skin = skeleton.IDENTITY_3X4
            floats = tuple(c for row in skin for c in row) + tuple(values)
        else:
            flags = RIG_BONE_FLAGS
            values[engine_pose.SLOT_ROTATE_PIVOT : engine_pose.SLOT_ROTATE_PIVOT + 3] = pivot
            values[engine_pose.SLOT_SCALE_PIVOT : engine_pose.SLOT_SCALE_PIVOT + 3] = pivot
            values[31:43] = [c for row in skeleton.IDENTITY_3X4 for c in row]
            floats = tuple(c for row in skeleton.IDENTITY_3X4 for c in row) + tuple(values)
            origin[j] = origin[parent] if parent is not None else (0.0, 0.0, 0.0)
        siblings = children.get(parent, [])
        pos = siblings.index(j)
        next_sibling = index[siblings[pos + 1]] if pos + 1 < len(siblings) else -1
        first_child = index[children[j][0]] if children.get(j) else -1
        bones.append(
            skeleton.Bone(
                names[k],
                index[parent] if parent is not None else -1,
                (next_sibling, first_child, flags),
                floats,
                (index[j], 1),
            )
        )
    return skeleton.SkeletonFile("[unknown]", bones), warnings


def check_rig_against(new_bones: list[skeleton.Bone], old_bones: list[skeleton.Bone]) -> tuple[list[str], list[str]]:
    """``(errors, warnings)`` for replacing a class skeleton: every anchor
    bone of the old rig (see :func:`is_anchor_name`) must exist in the new
    one; an anchor that moved is reported, since weapons, trails and
    shadows are placed from those bones."""
    errors, warnings = [], []
    new_by_name = {b.name: b for b in new_bones}
    missing = [b.name for b in old_bones if is_anchor_name(b.name) and b.name not in new_by_name]
    if missing:
        errors.append("The new armature lacks the engine's anchor bones: " + ", ".join(missing))
    def joint_positions(bones: list[skeleton.Bone]) -> dict[str, tuple[float, float, float]]:
        world = engine_pose.world_matrices(bones, engine_pose.local_matrices(bones, None, 0))
        return {b.name: engine_pose.apply(world[i], engine_pose.rest_pivot(b)) for i, b in enumerate(bones)}

    old_at, new_at = joint_positions(old_bones), joint_positions(new_bones)
    moved = []
    for b in old_bones:
        if is_anchor_name(b.name) and b.name in new_by_name:
            a, c = old_at[b.name], new_at[b.name]
            if math.dist(a, c) > 0.5:
                moved.append(f"{b.name} ({math.dist(a, c):.1f} units)")
    if moved:
        warnings.append(
            "Anchor bones placed away from the original (weapons, trails and shadows may be offset): " + ", ".join(moved)
        )
    return errors, warnings
