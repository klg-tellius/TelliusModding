"""Parse a ``.gs`` file - a 3D mesh (vertices, normals, UVs, vertex colors,
materials/texture references, and triangle-strip geometry), typically paired
with a ``.g`` skeleton (:mod:`skeleton`) of the same base name or a sibling
``skeleton.g``.

Zheneq's Fire Emblem Noesis plugin (``fmt_fireemblem_gs.py`` at
https://github.com/Zheneq/Noesis-Plugins) was a research reference for the
``.g`` and ``.gs`` layouts. The project maintainer identifies it as a
reference used during reverse engineering, rather than a source-code port.
See the public distribution's CREDITS.md for research resources and notices.

The composite buffer (``addrs[9]``, chunks with ``format & 1``) holds
CPU-skinned vertices with up to four blended bones each. Positions and
normals use signed 16-bit values scaled by the header's shift value.

File layout (also described by the reference plugin):

- Absolute offsets 0x00-0x0B: ``file_size``, ``table_addr``, ``table_num`` -
  present in every real file but not otherwise referenced by the plugin's
  own model-loading path (the same "read but unused downstream" situation
  as several fields in this package's other formats), so kept only as raw
  fields on :class:`GsHeader` rather than acted on.
- Absolute offset 0x20 onward: the real body, with every pointer inside it
  ``0x20``-relative (same ``HEADER_SIZE`` convention as the rest of this
  package) - ``root_name_addr``, 8 ``unk0`` floats, a 10-entry ``addrs``
  pointer table, an 8-entry ``nums`` count table, then 3 bytes giving
  ``1 << byte`` scale divisors for the vertex/normal/UV buffers.
- ``addrs``/``nums`` index meaning (0-9 / 0-7), by buffer:
  0=vertex positions (int16 xyz / vert_scale), 1=normals (int8 xyz /
  norm_scale), 2=UVs (int16 uv / uv_scale), 3=vertex colors (4x uint8
  RGBA), 4=materials, 5=meshes, 6=triangle-strip chunks (or built from
  addrs[7]/addrs[8] as a fallback - the plugin's own comment flags one real
  file, ``PoR/zmap/bmap28/map.cmp/fire_01.gs``, where addrs[5]'s top bit
  being set means "standard shape, maybe a glitch" and meshes are skipped
  entirely), 9=the "composite buffer" (skinned-vertex weights + packed
  positions/normals used by chunks with ``format & 1`` set). ``nums[7]`` is
  asserted to always be 0 by the plugin (a real warning path, not exercised
  by the samples checked for this implementation).

This module returns structured data (materials, meshes, chunks, decoded triangle
strips as flat vertex lists). Byte-exact reading and writing of the raw
fields is :mod:`gs_file`.
"""

from __future__ import annotations

import io
import struct
from dataclasses import dataclass, field
from pathlib import Path
from typing import BinaryIO, Optional

from .common import HEADER_SIZE, decode_str

# addrs[]/nums[] indices, named for readability - see module docstring.
_ADDR_POS, _ADDR_NORM, _ADDR_UV, _ADDR_COLOR, _ADDR_MATERIALS, _ADDR_MESHES = range(6)
_ADDR_CHUNKS_A, _ADDR_CHUNKS_B, _ADDR_CHUNKS_C, _ADDR_COMPOSITE = range(6, 10)

_MATERIAL_RECORD_SIZE = 32
_MATERIAL_TEX_RECORD_SIZE = 28
_MESH_RECORD_SIZE = 0x24
_COMPOSITE_WEIGHT_RECORD_SIZE = 24
_COMPOSITE_VERT_RECORD_SIZE = 12
_CHUNK_RECORD_SIZE = 32
_STRIP_MAGIC = 0x98


class ModelError(Exception):
    pass


@dataclass(frozen=True)
class GsHeader:
    file_size: int
    table_addr: int
    table_num: int
    root_name: str
    vert_scale: int
    norm_scale: int
    uv_scale: int


@dataclass(frozen=True)
class MaterialTexture:
    tex_id: int
    unk0: tuple[int, int]
    unk1: tuple[int, int, int, int, int]
    unk2: float
    unk3: float
    unk4: int


@dataclass(frozen=True)
class Material:
    index: int
    name: str
    color0: tuple[int, int, int, int]
    color1: tuple[int, int, int, int]
    color2: tuple[int, int, int, int]
    textures: list[MaterialTexture]


@dataclass(frozen=True)
class Mesh:
    index: int
    name: str
    bounds_a: tuple[float, float, float]
    bounds_b: tuple[float, float, float]
    bone: int


@dataclass(frozen=True)
class StripVertex:
    """One decoded triangle-strip vertex - already resolved to real
    position/normal/UV values (and, for a skinned chunk, real bone
    indices/weights), not raw buffer indices."""

    position: tuple[float, float, float]
    normal: tuple[float, float, float]
    uv: tuple[float, float]
    uv2: Optional[tuple[float, float]]
    color: Optional[tuple[int, int, int, int]]
    bone_indices: list[int]
    bone_weights: list[float]


#: Shape flag ``0x400``: ``draw_gs_shape_list`` skips the shape. No code
#: in ``main.dol`` was found changing it, so these shapes are never drawn
#: (weapon meshes inside ``zu/`` battle bodies, half the ``xwp/`` shapes).
SHAPE_FLAG_HIDDEN = 0x400


@dataclass(frozen=True)
class TriChunk:
    mesh_index: int
    material_index: int
    bone: int
    format: int  # the shape flags word
    format2: int
    bone_subset: list[int]
    strips: list[list[StripVertex]]  # each inner list is one triangle strip

    @property
    def hidden(self) -> bool:
        """The engine never draws this shape (:data:`SHAPE_FLAG_HIDDEN`)."""
        return bool(self.format & SHAPE_FLAG_HIDDEN)


@dataclass
class GsModel:
    header: GsHeader
    positions: list[tuple[float, float, float]]
    normals: list[tuple[float, float, float]]
    uvs: list[tuple[float, float]]
    colors: list[tuple[int, int, int, int]]
    materials: list[Material]
    meshes: list[Mesh]
    chunks: list[TriChunk]


def _rebase(addr: int) -> int:
    """Every pointer read from anywhere in the body (materials' name/texture
    addresses, meshes' name address, chunks' mesh/tri/bone-subset addresses,
    ...) is ``HEADER_SIZE``-relative, same as the top-level ``addrs`` table -
    the reference plugin reads all of them through one stream
    already rebased to start at absolute 0x20, so every pointer it reads
    anywhere is implicitly in that coordinate system. This module reads with
    a plain, unrebased stream instead, so every such pointer needs this
    applied at the point it's used as a seek position."""
    return addr + HEADER_SIZE if addr else 0


def _get_string(stream: BinaryIO, addr: int) -> str:
    if addr == 0:
        return ""
    stream.seek(addr)
    from .common import read_cstring

    return decode_str(read_cstring(stream))


def read_model(stream: BinaryIO) -> GsModel:
    file_size, table_addr, table_num = struct.unpack(">III", stream.read(12))

    stream.seek(HEADER_SIZE)
    root_name_addr = struct.unpack(">I", stream.read(4))[0] + HEADER_SIZE
    stream.read(8 * 4)  # unk0: 8 floats, purpose not decoded

    addrs = [v + HEADER_SIZE if v else 0 for v in struct.unpack(">10I", stream.read(40))]
    nums = list(struct.unpack(">8H", stream.read(16)))
    vert_shift, norm_shift, uv_shift = struct.unpack(">3B", stream.read(3))
    vert_scale, norm_scale, uv_scale = 1 << vert_shift, 1 << norm_shift, 1 << uv_shift

    header = GsHeader(
        file_size=file_size,
        table_addr=table_addr,
        table_num=table_num,
        root_name=_get_string(stream, root_name_addr),
        vert_scale=vert_scale,
        norm_scale=norm_scale,
        uv_scale=uv_scale,
    )

    positions = _read_positions(stream, addrs[_ADDR_POS], nums[_ADDR_POS], vert_scale)
    normals = _read_normals(stream, addrs[_ADDR_NORM], nums[_ADDR_NORM], norm_scale)
    uvs = _read_uvs(stream, addrs[_ADDR_UV], nums[_ADDR_UV], uv_scale)
    colors = _read_colors(stream, addrs[_ADDR_COLOR], nums[_ADDR_COLOR])

    materials = _read_materials(stream, addrs[_ADDR_MATERIALS], nums[_ADDR_MATERIALS])

    meshes: list[Mesh] = []
    mesh_addr = addrs[_ADDR_MESHES]
    if mesh_addr and not (mesh_addr - HEADER_SIZE) & 0x80000000:
        meshes = _read_meshes(stream, mesh_addr, nums[_ADDR_MESHES])

    chunk_addr = addrs[_ADDR_CHUNKS_A]
    if not chunk_addr:
        chunk_addr = addrs[_ADDR_CHUNKS_B] or addrs[_ADDR_CHUNKS_C]

    comp_pos: list[tuple[float, float, float]] = []
    comp_norm: list[tuple[float, float, float]] = []
    bone_idx_by_vert: list[list[int]] = []
    bone_wei_by_vert: list[list[float]] = []
    if addrs[_ADDR_COMPOSITE]:
        comp_pos, comp_norm, bone_idx_by_vert, bone_wei_by_vert = _read_composite_buffer(
            stream, addrs[_ADDR_COMPOSITE]
        )

    chunks: list[TriChunk] = []
    if chunk_addr:
        chunks = _read_chunks(
            stream,
            chunk_addr,
            nums[_ADDR_CHUNKS_A],
            addrs[_ADDR_MESHES],
            positions,
            normals,
            uvs,
            colors,
            comp_pos,
            comp_norm,
            bone_idx_by_vert,
            bone_wei_by_vert,
        )

    return GsModel(
        header=header,
        positions=positions,
        normals=normals,
        uvs=uvs,
        colors=colors,
        materials=materials,
        meshes=meshes,
        chunks=chunks,
    )


def read_model_bytes(data: bytes) -> GsModel:
    return read_model(io.BytesIO(data))


def read_model_path(path: Path | str) -> GsModel:
    with open(path, "rb") as stream:
        return read_model(stream)


def _read_positions(stream, addr, count, scale):
    if not addr:
        return []
    stream.seek(addr)
    return [tuple(v / scale for v in struct.unpack(">3h", stream.read(6))) for _ in range(count)]


def _read_normals(stream, addr, count, scale):
    if not addr:
        return []
    stream.seek(addr)
    return [tuple(v / scale for v in struct.unpack(">3b", stream.read(3))) for _ in range(count)]


def _read_uvs(stream, addr, count, scale):
    if not addr:
        return []
    stream.seek(addr)
    return [tuple(v / scale for v in struct.unpack(">2h", stream.read(4))) for _ in range(count)]


def _read_colors(stream, addr, count):
    if not addr:
        return []
    stream.seek(addr)
    return [struct.unpack(">4B", stream.read(4)) for _ in range(count)]


def _read_materials(stream, addr, count) -> list[Material]:
    if not addr:
        return []
    stream.seek(addr)
    raw = [struct.unpack(">I2BBB4B4B4BI2I", stream.read(_MATERIAL_RECORD_SIZE)) for _ in range(count)]
    materials = []
    for i, rec in enumerate(raw):
        # layout: nameAddr(I) unk0(2B) texNum(B) unk1(B) color0(4B) color1(4B) color2(4B) texAddr(I) junk(2I)
        name_addr = _rebase(rec[0])
        tex_num = rec[3]
        color0 = rec[5:9]
        color1 = rec[9:13]
        color2 = rec[13:17]
        tex_addr = _rebase(rec[17])
        textures = []
        if tex_addr:
            stream.seek(tex_addr)
            for _ in range(tex_num):
                t = struct.unpack(">2HH5HffI", stream.read(_MATERIAL_TEX_RECORD_SIZE))
                textures.append(
                    MaterialTexture(tex_id=t[2], unk0=t[0:2], unk1=t[3:8], unk2=t[8], unk3=t[9], unk4=t[10])
                )
        materials.append(
            Material(
                index=i,
                name=_get_string(stream, name_addr),
                color0=color0,
                color1=color1,
                color2=color2,
                textures=textures,
            )
        )
    return materials


def _read_meshes(stream, addr, count) -> list[Mesh]:
    stream.seek(addr)
    raw = [struct.unpack(">I3f3fH3H", stream.read(_MESH_RECORD_SIZE)) for _ in range(count)]
    meshes = []
    for i, rec in enumerate(raw):
        name_addr = _rebase(rec[0])
        bounds_a = rec[1:4]
        bounds_b = rec[4:7]
        bone = rec[7]
        meshes.append(Mesh(index=i, name=_get_string(stream, name_addr), bounds_a=bounds_a, bounds_b=bounds_b, bone=bone))
    return meshes


def _read_composite_buffer(stream, addr):
    stream.seek(addr)
    addr_weights, addr_verts, num_weights, num_verts, shift, _pad, _groups = struct.unpack(">IIHHBBH", stream.read(16))
    scale = float(1 << shift)

    bone_idx_by_vert: list[list[int]] = [[0]] * num_verts
    bone_wei_by_vert: list[list[float]] = [[1.0]] * num_verts

    stream.seek(addr + addr_weights)
    for _ in range(num_weights):
        indices = struct.unpack(">4h", stream.read(8))
        weights = [v / 0x100 for v in struct.unpack(">4B", stream.read(4))]
        start, size, start_add, num_indices, vert_count, _unk1 = struct.unpack(">IHBBHH", stream.read(12))

        real_indices = [i for i in indices if i != -1]
        real_weights = weights[: len(real_indices)] if len(real_indices) > 1 else [1.0]

        start_vert = (start + start_add) // 0xC
        for i in range(start_vert, start_vert + vert_count):
            if 0 <= i < num_verts:
                bone_idx_by_vert[i] = real_indices
                bone_wei_by_vert[i] = real_weights

    stream.seek(addr + addr_verts)
    comp_pos = []
    comp_norm = []
    for _ in range(num_verts):
        comp_pos.append(tuple(v / scale for v in struct.unpack(">3h", stream.read(6))))
        comp_norm.append(tuple(v / scale for v in struct.unpack(">3h", stream.read(6))))

    return comp_pos, comp_norm, bone_idx_by_vert, bone_wei_by_vert


def _read_chunks(
    stream,
    addr,
    count,
    meshes_addr,
    positions,
    normals,
    uvs,
    colors,
    comp_pos,
    comp_norm,
    bone_idx_by_vert,
    bone_wei_by_vert,
) -> list[TriChunk]:
    stream.seek(addr)
    raw = [struct.unpack(">II HHH 4B BB III", stream.read(_CHUNK_RECORD_SIZE)) for _ in range(count)]

    chunks = []
    for rec in raw:
        mesh_addr, _next_addr, fmt, mat_id, bone, _u1a, _u1b, _u1c, _u1d, fmt2, _u2, tri_addr, tri_size, bone_subset_addr = rec
        mesh_addr = _rebase(mesh_addr)
        tri_addr = _rebase(tri_addr)
        bone_subset_addr = _rebase(bone_subset_addr)
        mesh_index = (mesh_addr - meshes_addr) // _MESH_RECORD_SIZE if meshes_addr else -1

        bone_subset: list[int] = []
        if bone_subset_addr:
            stream.seek(bone_subset_addr)
            mark, subset_count = struct.unpack(">BB", stream.read(2))
            if mark != 0x10:
                raise ModelError(f"Unexpected bone-subset marker {mark:#x} (expected 0x10).")
            bone_subset = list(struct.unpack(f">{subset_count}B", stream.read(subset_count)))

        use_comp_buffer = bool(fmt & 1)
        single_bone_per_vertex = bool(fmt & 2)
        has_color = bool(fmt2 & 0x10)
        has_uv2 = bool(fmt2 & 0x80)

        strips = _read_strips(
            stream,
            tri_addr,
            tri_size,
            bone,
            bone_subset,
            use_comp_buffer,
            single_bone_per_vertex,
            has_color,
            has_uv2,
            positions,
            normals,
            uvs,
            colors,
            comp_pos,
            comp_norm,
            bone_idx_by_vert,
            bone_wei_by_vert,
        )

        chunks.append(
            TriChunk(
                mesh_index=mesh_index,
                material_index=mat_id,
                bone=bone,
                format=fmt,
                format2=fmt2,
                bone_subset=bone_subset,
                strips=strips,
            )
        )
    return chunks


def _read_strips(
    stream,
    tri_addr,
    tri_size,
    chunk_bone,
    bone_subset,
    use_comp_buffer,
    single_bone_per_vertex,
    has_color,
    has_uv2,
    positions,
    normals,
    uvs,
    colors,
    comp_pos,
    comp_norm,
    bone_idx_by_vert,
    bone_wei_by_vert,
) -> list[list[StripVertex]]:
    stream.seek(tri_addr)
    end = tri_addr + tri_size
    strips: list[list[StripVertex]] = []

    while stream.tell() < end:
        mag = stream.read(1)[0]
        if mag != _STRIP_MAGIC:
            break
        (num,) = struct.unpack(">H", stream.read(2))

        strip: list[StripVertex] = []
        bone_indices = [chunk_bone]
        for _ in range(num):
            if single_bone_per_vertex:
                sub_index = stream.read(1)[0] // 3
                bone_indices = [bone_subset[sub_index]] if sub_index < len(bone_subset) else [chunk_bone]

            (vert,) = struct.unpack(">H", stream.read(2))
            (norm,) = struct.unpack(">H", stream.read(2))

            color = None
            if has_color:
                (col,) = struct.unpack(">H", stream.read(2))
                color = colors[col] if col < len(colors) else None

            (uv,) = struct.unpack(">H", stream.read(2))
            uv2 = None
            if has_uv2:
                (uv2_idx,) = struct.unpack(">H", stream.read(2))
                uv2 = uvs[uv2_idx] if uv2_idx < len(uvs) else None

            if use_comp_buffer:
                position = comp_pos[vert] if vert < len(comp_pos) else (0.0, 0.0, 0.0)
                normal = comp_norm[norm] if norm < len(comp_norm) else (0.0, 0.0, 0.0)
                weights_bone_idx = bone_idx_by_vert[vert] if vert < len(bone_idx_by_vert) else bone_indices
                weights_bone_wei = bone_wei_by_vert[vert] if vert < len(bone_wei_by_vert) else [1.0]
            else:
                position = positions[vert] if vert < len(positions) else (0.0, 0.0, 0.0)
                normal = normals[norm] if norm < len(normals) else (0.0, 0.0, 0.0)
                weights_bone_idx = bone_indices
                weights_bone_wei = [1.0]

            strip.append(
                StripVertex(
                    position=position,
                    normal=normal,
                    uv=uvs[uv] if uv < len(uvs) else (0.0, 0.0),
                    uv2=uv2,
                    color=color,
                    bone_indices=weights_bone_idx,
                    bone_weights=weights_bone_wei,
                )
            )

        strips.append(strip)

    return strips
