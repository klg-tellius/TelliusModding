"""Lossless read/write of the ``.gs`` mesh container.

:mod:`model` decodes a ``.gs`` into render-ready data (floats, resolved
triangle strips). This module sits one level lower: it keeps every stored
field in its raw integer/fixed-point form and knows the exact on-disk block
layout, so ``write_gs(read_gs(data)) == data`` for every real file. It is
the foundation for importing new meshes - an importer builds a
:class:`GsFile` and lets :func:`write_gs` do the layout, pointers, and
relocation table.

File layout (all offsets from ``0x20`` - the "body" - unless noted):

- File header, absolute ``0x00``-``0x1F`` - the engine's generic relocatable
  resource header (``validate_resource_magic_signature``, ``0x8003F87C``):
  ``file_size``, relocation-table offset (body-relative), relocation count,
  export count, import count, one unknown word, then 7 signature bytes and a
  "symbols registered" flag byte. The loader writes the signature and flag
  into RAM after relocating, so on disc they are always zero.
- Body header ``0x00``-``0x63``: root-name pointer, a ``YYYYMMDD`` export
  date (``0x20040723``), a 32-bit model id/hash, a bind-pose bounding box
  (min xyz, max xyz), the 10-entry ``addrs`` table, the 8-entry ``nums``
  table, the three fixed-point fraction bytes (position, normal, UV), one
  zero pad byte and one zero word.
- Then, in this order: positions (``3 x s16``), normals (``3 x s8``), UVs
  (``2 x s16``), vertex colors (``RGBA8``) - each padded to 4 bytes -,
  materials (32 bytes), every material's texture records (28 bytes),
  meshes (``0x24``), chunk records (32 bytes; list ``addrs[6]``, then
  ``[7]``, then ``[8]``), display lists (each padded to 32), the composite
  skinning buffer, bone subsets (each starting on a 32-byte boundary), the
  deduplicated string pool (sorted by byte value), 4-byte padding, the relocation table (ascending body offsets
  of every non-zero pointer field), then the export/import symbol tables
  and their names.

``addrs[6]``/``[7]``/``[8]`` are three singly linked chunk lists - one per
render pass (``draw_gs_shape_list``, ``0x8006C2A4``) - not alternative
locations of the same list. Chunk records are stored contiguously in list
order and each ``next`` pointer links to the following record of its list.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass, field
from typing import Optional

from .common import HEADER_SIZE, decode_str

BODY_HEADER_SIZE = 0x64
MATERIAL_SIZE = 0x20
TEXTURE_SIZE = 0x1C
MESH_SIZE = 0x24
CHUNK_SIZE = 0x20
COMPOSITE_HEADER_SIZE = 0x10
COMPOSITE_WEIGHT_SIZE = 0x18
COMPOSITE_VERTEX_SIZE = 0x0C
BONE_SUBSET_MARKER = 0x10
IMPORTED_POINTER = 0xFFFFFFFF

_ADDR_TABLE = 0x24
_CHUNK_LIST_SLOTS = (6, 7, 8)


class GsFileError(Exception):
    pass


@dataclass
class GsTexture:
    """One 28-byte material texture record (see ``MaterialTexture`` in
    :mod:`model` for what is known about each field)."""

    flags: tuple[int, int]
    tex_id: int
    params: tuple[int, int, int, int, int]
    scale_u: float
    scale_v: float
    extra: int


@dataclass
class GsMaterial:
    name: str
    unk0: tuple[int, int]
    unk1: int
    color0: tuple[int, int, int, int]
    color1: tuple[int, int, int, int]
    color2: tuple[int, int, int, int]
    textures: list[GsTexture] = field(default_factory=list)
    trailer: tuple[int, int] = (0, 0)


@dataclass
class GsMesh:
    name: str
    bounds_min: tuple[float, float, float]
    bounds_max: tuple[float, float, float]
    bone: int
    extra: tuple[int, int, int] = (0, 0, 0)


@dataclass
class GsChunk:
    """One draw call. ``flags`` is the u16 at record ``+0x08`` (bit 0
    composite-skinned, bit 1 multi-matrix via ``bone_subset``, bit 2 reuse
    previous material, ``0x40`` additive blend, ``0x80`` subtractive blend,
    ``0x100`` no Z, ``0x400`` hidden); ``attr_mask`` is the u32 at ``+0x10``
    (GX vertex attributes, see ``declare_gs_vertex_format``; top 3 bits are
    the billboard mode)."""

    mesh_index: Optional[int]
    flags: int
    material_index: int
    bone: int
    cache_slot: int
    attr_mask: int
    display_list: bytes
    bone_subset: Optional[list[int]] = None


@dataclass
class GsComposite:
    """The CPU-skinning buffer used by chunks with ``flags & 1``.

    ``weights`` are the raw 24-byte records: 4 bone indices (``-1`` unused),
    4 ``u8`` weights (``/256``; 0 for one-bone records), the byte offset of
    the record's first 32-byte block, the block byte size, the first
    vertex's offset inside the block, the bone count, the vertex count and
    the NBT-vertex count. ``vertices`` are 12-byte slots (``s16`` position
    and normal scaled by ``2 ** shift``); slots between records are
    padding. ``unk0`` is ``shift << 8``; ``unk1`` counts the records with
    more than one vertex."""

    weights: list[tuple] = field(default_factory=list)  # raw 24-byte records: 4h 4B I H B B H H
    vertices: list[tuple[int, int, int, int, int, int]] = field(default_factory=list)
    unk0: int = 0
    unk1: int = 0
    skin_position_count: int = 0
    skin_normal_count: int = 0


@dataclass
class GsSymbol:
    body_offset: int
    name: str


@dataclass
class GsFile:
    root_name: str
    date: int
    model_id: int
    bbox_min: tuple[float, float, float]
    bbox_max: tuple[float, float, float]
    pos_frac: int
    norm_frac: int
    uv_frac: int
    positions: list[tuple[int, int, int]] = field(default_factory=list)
    normals: list[tuple[int, int, int]] = field(default_factory=list)
    uvs: list[tuple[int, int]] = field(default_factory=list)
    colors: list[tuple[int, int, int, int]] = field(default_factory=list)
    materials: list[GsMaterial] = field(default_factory=list)
    meshes: list[GsMesh] = field(default_factory=list)
    chunk_lists: tuple[list[GsChunk], list[GsChunk], list[GsChunk]] = field(
        default_factory=lambda: ([], [], [])
    )
    composite: Optional[GsComposite] = None
    meshes_imported: bool = False
    exports: list[GsSymbol] = field(default_factory=list)
    imports: list[GsSymbol] = field(default_factory=list)
    header_unknown: int = 0

    @property
    def chunks(self) -> list[GsChunk]:
        return [c for lst in self.chunk_lists for c in lst]


def _encode_name(name: str) -> bytes:
    for codec in ("ascii", "shift_jis", "latin-1"):
        try:
            return name.encode(codec)
        except UnicodeEncodeError:
            continue
    raise GsFileError(f"Cannot encode name {name!r}.")


def _align(value: int, alignment: int) -> int:
    return (value + alignment - 1) & ~(alignment - 1)


# ---------------------------------------------------------------- reading


def texture_id_offsets(data: bytes) -> list[int]:
    """File offsets of every material texture record's ``tex_id`` (u16)."""
    body = data[HEADER_SIZE:]
    addrs = struct.unpack(">10I", body[_ADDR_TABLE : _ADDR_TABLE + 40])
    nums = struct.unpack(">8H", body[0x4C:0x5C])
    offsets = []
    for i in range(nums[4] if addrs[4] else 0):
        m = struct.unpack_from(">I2BBB4B4B4BI2I", body, addrs[4] + MATERIAL_SIZE * i)
        if m[17]:
            offsets += [HEADER_SIZE + m[17] + TEXTURE_SIZE * t + 4 for t in range(m[3])]
    return offsets


def remap_texture_ids(data: bytes, mapping: dict[int, int]) -> bytes:
    """``data`` with every material texture id ``k`` in ``mapping`` changed
    to ``mapping[k]``, in place: nothing else in the file moves."""
    out = bytearray(data)
    for offset in texture_id_offsets(data):
        old = struct.unpack_from(">H", out, offset)[0]
        if old in mapping:
            struct.pack_into(">H", out, offset, mapping[old])
    return bytes(out)



def read_gs(data: bytes) -> GsFile:
    (_file_size, reloc_offset, reloc_count, n_exports, n_imports, header_unknown) = struct.unpack(
        ">6I", data[:24]
    )
    body = data[HEADER_SIZE:]

    def u32(off: int) -> int:
        return struct.unpack(">I", body[off : off + 4])[0]

    def string(off: int) -> str:
        if not off:
            return ""
        return decode_str(body[off : body.index(b"\0", off)])

    root_ptr, date, model_id = struct.unpack(">3I", body[0:12])
    bbox = struct.unpack(">6f", body[12:36])
    addrs = struct.unpack(">10I", body[_ADDR_TABLE : _ADDR_TABLE + 40])
    nums = struct.unpack(">8H", body[0x4C:0x5C])
    pos_frac, norm_frac, uv_frac = body[0x5C], body[0x5D], body[0x5E]

    gs = GsFile(
        root_name=string(root_ptr),
        date=date,
        model_id=model_id,
        bbox_min=bbox[0:3],
        bbox_max=bbox[3:6],
        pos_frac=pos_frac,
        norm_frac=norm_frac,
        uv_frac=uv_frac,
        header_unknown=header_unknown,
    )

    if addrs[0]:
        gs.positions = [struct.unpack_from(">3h", body, addrs[0] + 6 * i) for i in range(nums[0])]
    if addrs[1]:
        gs.normals = [struct.unpack_from(">3b", body, addrs[1] + 3 * i) for i in range(nums[1])]
    if addrs[2]:
        gs.uvs = [struct.unpack_from(">2h", body, addrs[2] + 4 * i) for i in range(nums[2])]
    if addrs[3]:
        gs.colors = [struct.unpack_from(">4B", body, addrs[3] + 4 * i) for i in range(nums[3])]

    for i in range(nums[4] if addrs[4] else 0):
        m = struct.unpack_from(">I2BBB4B4B4BI2I", body, addrs[4] + MATERIAL_SIZE * i)
        textures = []
        if m[17]:
            for t in range(m[3]):
                r = struct.unpack_from(">2HH5HffI", body, m[17] + TEXTURE_SIZE * t)
                textures.append(GsTexture(r[0:2], r[2], r[3:8], r[8], r[9], r[10]))
        gs.materials.append(
            GsMaterial(
                name=string(m[0]),
                unk0=m[1:3],
                unk1=m[4],
                color0=m[5:9],
                color1=m[9:13],
                color2=m[13:17],
                textures=textures,
                trailer=m[18:20],
            )
        )
        if m[3] != len(textures):
            raise GsFileError("Material texture count without a texture table.")

    if addrs[5] == IMPORTED_POINTER:
        gs.meshes_imported = True
    elif addrs[5]:
        for i in range(nums[5]):
            r = struct.unpack_from(">I3f3fH3H", body, addrs[5] + MESH_SIZE * i)
            gs.meshes.append(GsMesh(string(r[0]), r[1:4], r[4:7], r[7], r[8:11]))

    for list_index, slot in enumerate(_CHUNK_LIST_SLOTS):
        ptr = addrs[slot]
        while ptr:
            mesh_ptr, next_ptr, flags, mat, bone, cache, attr, dl_ptr, dl_size, bs_ptr = struct.unpack_from(
                ">IIHHHHIIII", body, ptr
            )
            subset = None
            if bs_ptr:
                if body[bs_ptr] != BONE_SUBSET_MARKER:
                    raise GsFileError(f"Bad bone-subset marker at {bs_ptr + HEADER_SIZE:#x}.")
                subset = list(body[bs_ptr + 2 : bs_ptr + 2 + body[bs_ptr + 1]])
            mesh_index = None
            if mesh_ptr:
                mesh_index, rem = divmod(mesh_ptr - addrs[5], MESH_SIZE)
                if rem or not 0 <= mesh_index < len(gs.meshes):
                    raise GsFileError(f"Chunk mesh pointer {mesh_ptr:#x} is not a mesh record.")
            gs.chunk_lists[list_index].append(
                GsChunk(mesh_index, flags, mat, bone, cache, attr, body[dl_ptr : dl_ptr + dl_size], subset)
            )
            ptr = next_ptr

    if addrs[9]:
        c = addrs[9]
        w_off, v_off, n_w, n_v, unk0, unk1 = struct.unpack_from(">IIHHHH", body, c)
        comp = GsComposite(unk0=unk0, unk1=unk1)
        comp.weights = [struct.unpack_from(">4h4BIHBBHH", body, c + w_off + COMPOSITE_WEIGHT_SIZE * i) for i in range(n_w)]
        comp.vertices = [struct.unpack_from(">6h", body, c + v_off + COMPOSITE_VERTEX_SIZE * i) for i in range(n_v)]
        if not addrs[0]:
            comp.skin_position_count = nums[0]
        if not addrs[1]:
            comp.skin_normal_count = nums[1]
        gs.composite = comp

    tables = HEADER_SIZE + reloc_offset + 4 * reloc_count
    names = tables + 8 * (n_exports + n_imports)

    def symbol(i: int) -> GsSymbol:
        target, name_off = struct.unpack_from(">II", data, tables + 8 * i)
        return GsSymbol(target, decode_str(data[names + name_off : data.index(b"\0", names + name_off)]))

    gs.exports = [symbol(i) for i in range(n_exports)]
    gs.imports = [symbol(n_exports + i) for i in range(n_imports)]
    return gs


# ---------------------------------------------------------------- writing


class _Body:
    def __init__(self) -> None:
        self.buf = bytearray(BODY_HEADER_SIZE)
        self.pointers: list[int] = []  # body offsets of non-zero pointer fields

    def align(self, alignment: int) -> None:
        self.buf.extend(bytes(_align(len(self.buf), alignment) - len(self.buf)))

    def append(self, data: bytes) -> int:
        offset = len(self.buf)
        self.buf.extend(data)
        return offset

    def put_u32(self, offset: int, value: int) -> None:
        struct.pack_into(">I", self.buf, offset, value)

    def put_ptr(self, offset: int, target: int) -> None:
        self.put_u32(offset, target)
        if target:
            self.pointers.append(offset)


def write_gs(gs: GsFile) -> bytes:
    body = _Body()
    string_refs: list[tuple[int, str]] = []  # (pointer field offset, name)
    addrs = [0] * 10
    nums = [0] * 8

    def block(items, fmt: str, alignment: int = 4) -> int:
        if not items:
            return 0
        offset = body.append(b"".join(struct.pack(fmt, *v) for v in items))
        body.align(alignment)
        return offset

    addrs[0] = block(gs.positions, ">3h")
    addrs[1] = block(gs.normals, ">3b")
    addrs[2] = block(gs.uvs, ">2h")
    addrs[3] = block(gs.colors, ">4B")
    nums[0:4] = [len(gs.positions), len(gs.normals), len(gs.uvs), len(gs.colors)]
    if gs.composite is not None:
        if not gs.positions:
            nums[0] = gs.composite.skin_position_count
        if not gs.normals:
            nums[1] = gs.composite.skin_normal_count

    material_offsets = []
    if gs.materials:
        addrs[4] = body.append(bytes(MATERIAL_SIZE * len(gs.materials)))
        material_offsets = [addrs[4] + MATERIAL_SIZE * i for i in range(len(gs.materials))]
    for m, off in zip(gs.materials, material_offsets):
        tex_ptr = 0
        if m.textures:
            tex_ptr = body.append(
                b"".join(
                    struct.pack(">2HH5HffI", *t.flags, t.tex_id, *t.params, t.scale_u, t.scale_v, t.extra)
                    for t in m.textures
                )
            )
        struct.pack_into(
            ">I2BBB4B4B4BI2I", body.buf, off, 0, *m.unk0, len(m.textures), m.unk1,
            *m.color0, *m.color1, *m.color2, 0, *m.trailer,
        )
        string_refs.append((off, m.name))
        body.put_ptr(off + 0x14, tex_ptr)
    nums[4] = len(gs.materials)

    mesh_base = 0
    if gs.meshes_imported:
        addrs[5] = IMPORTED_POINTER
    elif gs.meshes:
        mesh_base = body.append(
            b"".join(struct.pack(">I3f3fH3H", 0, *m.bounds_min, *m.bounds_max, m.bone, *m.extra) for m in gs.meshes)
        )
        addrs[5] = mesh_base
        string_refs.extend((mesh_base + MESH_SIZE * i, m.name) for i, m in enumerate(gs.meshes))
    nums[5] = len(gs.meshes)

    chunk_offsets: list[int] = []
    for list_index, chunks in enumerate(gs.chunk_lists):
        for i, ch in enumerate(chunks):
            off = body.append(bytes(CHUNK_SIZE))
            chunk_offsets.append(off)
            if i == 0:
                addrs[_CHUNK_LIST_SLOTS[list_index]] = off
    nums[6] = len(chunk_offsets)
    all_chunks = gs.chunks

    dl_offsets = []
    for ch in all_chunks:
        body.align(32)
        dl_offsets.append(body.append(ch.display_list))

    if gs.composite is not None:
        comp = gs.composite
        body.align(32)
        base = body.append(bytes(COMPOSITE_HEADER_SIZE))
        body.append(b"".join(struct.pack(">4h4BIHBBHH", *w) for w in comp.weights))
        body.align(32)
        v_off = body.append(b"".join(struct.pack(">6h", *v) for v in comp.vertices)) - base
        struct.pack_into(
            ">IIHHHH", body.buf, base, COMPOSITE_HEADER_SIZE, v_off,
            len(comp.weights), len(comp.vertices), comp.unk0, comp.unk1,
        )
        addrs[9] = base

    subset_offsets = []
    for ch in all_chunks:
        if ch.bone_subset is None:
            subset_offsets.append(0)
            continue
        body.align(32)
        subset_offsets.append(body.append(bytes([BONE_SUBSET_MARKER, len(ch.bone_subset), *ch.bone_subset])))

    position = 0
    for list_index, chunks in enumerate(gs.chunk_lists):
        for i, ch in enumerate(chunks):
            off = chunk_offsets[position]
            next_off = chunk_offsets[position + 1] if i + 1 < len(chunks) else 0
            struct.pack_into(
                ">IIHHHHIIII", body.buf, off, 0, 0, ch.flags, ch.material_index, ch.bone,
                ch.cache_slot, ch.attr_mask, 0, len(ch.display_list), 0,
            )
            if ch.mesh_index is not None:
                body.put_ptr(off, mesh_base + MESH_SIZE * ch.mesh_index)
            body.put_ptr(off + 4, next_off)
            body.put_ptr(off + 0x14, dl_offsets[position])
            body.put_ptr(off + 0x1C, subset_offsets[position])
            position += 1

    # String pool: deduplicated and sorted by encoded bytes.
    string_refs.append((0, gs.root_name))
    pool: dict[bytes, int] = {}
    for encoded in sorted({_encode_name(name) for _, name in string_refs if name}):
        pool[encoded] = body.append(encoded + b"\0")
    for ref_offset, name in string_refs:
        if name:
            body.put_ptr(ref_offset, pool[_encode_name(name)])
    body.align(4)

    # Header fields.
    hdr = body.buf
    struct.pack_into(">I", hdr, 4, gs.date)
    struct.pack_into(">I", hdr, 8, gs.model_id)
    struct.pack_into(">6f", hdr, 12, *gs.bbox_min, *gs.bbox_max)
    for i, value in enumerate(addrs):
        if value == IMPORTED_POINTER:
            body.put_u32(_ADDR_TABLE + 4 * i, value)
        else:
            body.put_ptr(_ADDR_TABLE + 4 * i, value)
    struct.pack_into(">8H", hdr, 0x4C, *nums)
    hdr[0x5C:0x60] = bytes([gs.pos_frac, gs.norm_frac, gs.uv_frac, 0])

    reloc_offset = len(body.buf)
    pointers = sorted(body.pointers)
    body.append(b"".join(struct.pack(">I", p) for p in pointers))

    symbols = gs.exports + gs.imports
    names = bytearray()
    name_offsets = []
    for sym in symbols:
        name_offsets.append(len(names))
        names += _encode_name(sym.name) + b"\0"
    body.append(b"".join(struct.pack(">II", s.body_offset, n) for s, n in zip(symbols, name_offsets)))
    body.append(bytes(names))

    out = bytearray(HEADER_SIZE)
    out += body.buf
    struct.pack_into(
        ">6I", out, 0, len(out), reloc_offset, len(pointers), len(gs.exports), len(gs.imports), gs.header_unknown
    )
    return bytes(out)
