"""Parse and write a ``.g`` skeleton (e.g. ``skeleton.g`` inside a
character's ``pack.cmp``): the bone hierarchy and each bone's transform
data.

Each 244-byte bone record (layout shared with the third-party Noesis
plugin, github.com/Zheneq/Noesis-Plugins) is read by the engine as follows
(``build_bone_local_matrix``, ``gactor_build_bone_hierarchy_matrices_recursive``
and the shape-matrix builders; see :mod:`engine_pose`, which ports them):

- ``+0x00`` parent, ``+0x04`` next sibling, ``+0x08`` first child (indices on
  disc); ``+0x0C`` flags - which transform terms apply (``unknown_ints[2]``).
- ``+0x10`` ``skin_matrix``, a 3x4 (``unknown_floats[0:12]``): multi-matrix
  shapes draw with ``world x skin_matrix``. Its 3x3 is
  :attr:`Bone.rotation`.
- ``+0x40`` the 43-float **value block** (``unknown_floats[12:55]``), which
  animation curves overwrite slot by slot: scale, Euler rotation (degrees),
  translate, joint orient, rotate pivot (:attr:`Bone.position` - the bind
  world position on character rigs), scale pivot, the two pivot
  translations, rotate axis, a quaternion, and at ``+0xBC`` the 3x4 seed
  local matrix those values produce (:func:`local_bind_matrix`).
- ``+0xEC`` the bone's index, ``+0xEE`` its Euler rotation order
  (``unknown_shorts``); ``+0xF0`` the name.
"""

from __future__ import annotations

import io
import struct
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO

from .common import read_cstring_table

BONE_RECORD_SIZE = 61 * 4  # 0xF4
BONE_RECORD_FORMAT = ">4i55fHHI"
BONES_START = 0x10

#: unknown_floats[24:27]: the value block's rotate pivot (the scale pivot at [27:30] repeats it).
_POSITION_OFFSET = 24

#: unknown_floats[0:3], [4:7], [8:11] - the 3x3 of skin_matrix (3/7/11 are its translation).
_ROTATION_ROW_OFFSETS = (0, 4, 8)


@dataclass(frozen=True)
class Bone:
    name: str
    parent_index: int
    unknown_ints: tuple[int, int, int]
    unknown_floats: tuple[float, ...]  # 55 values: skin_matrix (12), then the 43-float value block
    unknown_shorts: tuple[int, int]

    @property
    def position(self) -> tuple[float, float, float]:
        """The rotate pivot: where the bone turns, which is its bind-pose
        world position on character rigs."""
        return self.unknown_floats[_POSITION_OFFSET : _POSITION_OFFSET + 3]

    @property
    def rotation(self) -> tuple[tuple[float, float, float], tuple[float, float, float], tuple[float, float, float]]:
        """The 3x3 part of ``skin_matrix``, row-major (identity on most
        character bones)."""
        f = self.unknown_floats
        return tuple(f[o : o + 3] for o in _ROTATION_ROW_OFFSETS)  # type: ignore[return-value]


#: unknown_floats[43:55] - the record's ``+0xBC`` 3x4 matrix (row-major,
#: translation in the 4th column), the parent-relative bind matrix the
#: engine seeds each frame's bone hierarchy from.
_LOCAL_MATRIX_OFFSET = 43

Mat3x4 = tuple[tuple[float, float, float, float], tuple[float, float, float, float], tuple[float, float, float, float]]


def local_bind_matrix(bone: Bone) -> Mat3x4:
    """The bone's ``+0xBC`` matrix: the parent-relative bind transform
    (scale included) that ``gactor_build_bone_hierarchy_matrices_recursive``
    (``0x80065AF8``) chains as ``world[b] = world[parent] x local[b]``."""
    f = bone.unknown_floats[_LOCAL_MATRIX_OFFSET : _LOCAL_MATRIX_OFFSET + 12]
    return (tuple(f[0:4]), tuple(f[4:8]), tuple(f[8:12]))  # type: ignore[return-value]


def mul_3x4(a: Mat3x4, b: Mat3x4) -> Mat3x4:
    """``a x b`` for 3x4 affine matrices (implicit ``0 0 0 1`` last row).
    Unrolled: posing a battle scene calls this hundreds of times a frame."""
    b0, b1, b2 = b
    b00, b01, b02, b03 = b0
    b10, b11, b12, b13 = b1
    b20, b21, b22, b23 = b2
    rows = []
    for a0, a1, a2, a3 in a:
        rows.append((a0 * b00 + a1 * b10 + a2 * b20, a0 * b01 + a1 * b11 + a2 * b21,
                     a0 * b02 + a1 * b12 + a2 * b22, a0 * b03 + a1 * b13 + a2 * b23 + a3))
    return tuple(rows)  # type: ignore[return-value]


IDENTITY_3X4: Mat3x4 = ((1.0, 0.0, 0.0, 0.0), (0.0, 1.0, 0.0, 0.0), (0.0, 0.0, 1.0, 0.0))


def bind_world_matrices(bones: list[Bone]) -> list[Mat3x4]:
    """Every bone's bind-pose world matrix, chained the engine's way from
    the ``+0xBC`` matrices along ``parent_index``. A single-matrix ``.gs``
    shape draws its vertices through ``actor x world[shape.bone]``, so this
    is the matrix that takes a static shape's stored (bone-local) vertices
    to model space when no animation moves the bone."""
    world: dict[int, Mat3x4] = {}

    def resolve(i: int, depth: int = 0) -> Mat3x4:
        if i in world:
            return world[i]
        local = local_bind_matrix(bones[i])
        parent = bones[i].parent_index
        if 0 <= parent < len(bones) and parent != i and depth < len(bones):
            local = mul_3x4(resolve(parent, depth + 1), local)
        world[i] = local
        return local

    return [resolve(i) for i in range(len(bones))]


def read_skeleton(stream: BinaryIO) -> list[Bone]:
    header = stream.read(16)
    _junk, string_pool_offset, num_bones, _data_start = struct.unpack(">IIII", header)

    stream.seek(string_pool_offset)
    names_by_offset = read_cstring_table(stream.read())

    bones = []
    address = BONES_START
    for _ in range(num_bones):
        stream.seek(address)
        address += BONE_RECORD_SIZE
        fields = struct.unpack(BONE_RECORD_FORMAT, stream.read(BONE_RECORD_SIZE))

        parent_index = fields[0]
        unknown_ints = fields[1:4]
        unknown_floats = fields[4:59]
        unknown_shorts = fields[59:61]
        name_offset = fields[61]

        name_bytes = names_by_offset.get(name_offset, b"")
        try:
            name = name_bytes.decode("ascii")
        except UnicodeDecodeError:
            name = name_bytes.decode("latin-1")

        bones.append(Bone(name, parent_index, unknown_ints, unknown_floats, unknown_shorts))

    return bones


def read_skeleton_path(path: Path | str) -> list[Bone]:
    with open(path, "rb") as stream:
        return read_skeleton(stream)


@dataclass
class SkeletonFile:
    """A whole ``.g`` file, for lossless round-tripping.

    Layout: a 16-byte header (a zero word, the name-pool offset, the bone
    count, the bone-array offset - always ``0x10``), the bone records back to
    back, then the name pool: ``root_name`` first (referenced by no bone),
    then each bone's name in bone order. No trailing padding.

    The loader (``0x80065F48``) relocates both offsets and turns each record's
    first three ints - parent, next sibling, first child, as bone indices
    with ``-1`` for none - into pointers; the fourth int is a flags word it
    ORs name-derived bits into. It overwrites ``unknown_shorts[0]`` with the
    bone's own index (always equal to it on disc).
    """

    root_name: str
    bones: list[Bone]


def _encode_bone_name(name: str) -> bytes:
    try:
        return name.encode("ascii")
    except UnicodeEncodeError:
        return name.encode("latin-1")


def read_skeleton_file(data: bytes) -> SkeletonFile:
    _zero, pool_offset, _count, _bones_start = struct.unpack(">IIII", data[:16])
    root_name = data[pool_offset : data.index(b"\0", pool_offset)].decode("ascii", errors="replace")
    return SkeletonFile(root_name=root_name, bones=read_skeleton(io.BytesIO(data)))


def write_skeleton_file(skel: SkeletonFile) -> bytes:
    pool = bytearray(_encode_bone_name(skel.root_name) + b"\0")
    records = bytearray()
    for bone in skel.bones:
        name_offset = len(pool)
        pool += _encode_bone_name(bone.name) + b"\0"
        records += struct.pack(
            BONE_RECORD_FORMAT,
            bone.parent_index,
            *bone.unknown_ints,
            *bone.unknown_floats,
            *bone.unknown_shorts,
            name_offset,
        )
    header = struct.pack(">IIII", 0, BONES_START + len(records), len(skel.bones), BONES_START)
    return header + bytes(records) + bytes(pool)
