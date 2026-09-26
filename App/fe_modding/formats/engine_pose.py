"""Skeletal pose exactly as the engine computes it from a ``.g`` skeleton and
a ``.ga`` animation.

Python implementation of pose behavior documented through engine analysis:

- ``interpolate_animation_frame_value`` (``0x80063614``) evaluates the
  curves. A curve writes an **absolute** value into one slot of the bone's
  43-float *value block* - a copy of the bone record's floats at ``+0x40``
  (:func:`bone_values`) - so un-animated slots keep the skeleton's values.
  Keys are ``(frame, int16)`` pairs scaled by ``2 ** -shift``; before the
  first key the first value holds, after the last key the last value holds,
  and in between values are linear in the (fractional) frame.
- ``build_bone_local_matrix`` (``0x80062920``) turns the value block into
  the bone's parent-relative matrix, Maya transform style::

      local = T(translate) . [T(rp_translate)] . T(rotate_pivot)
              . [JointOrient] . R(rotate) . [RotateAxis] . T(-rotate_pivot)
              . [T(sp_translate)] . T(scale_pivot) . S(scale) . T(-scale_pivot)

  Which terms apply is decided by ``flags`` = the animation group's channel
  mask ORed with the bone record's flags (``+0x0C``), bit by bit (see the
  ``FLAG_*`` constants). Without :data:`FLAG_ROTATE` the whole rotation and
  pivot part is skipped. Euler angles are degrees, composed in the bone's
  rotation order (``+0xEE``; every file on the disc uses order 1,
  ``Rz . Ry . Rx``).
- ``gactor_blend_skeleton_pose_from_animations`` (``0x80061A08``) rebuilds
  only the bones the animation has a group for; every other bone keeps the
  local matrix seeded from its ``+0xBC`` record matrix. That seed equals
  :func:`local_matrix` of the bone's own values with every channel bit set
  on 56,463 of the disc's 56,836 bones (all character and weapon rigs; the
  rest are effect/scenery nodes with shear-like extra bits).
- ``gactor_build_bone_hierarchy_matrices_recursive`` chains
  ``world = world[parent] x local`` and, for skinning, multiplies by the
  bone's ``skin_matrix`` (record ``+0x10``, floats 0-11).

A multi-matrix ``.gs`` vertex is drawn at ``world[b] x skin[b] x stored``
(:func:`skin_palette`).
"""

from __future__ import annotations

import math
from typing import Optional

from . import animation, skeleton
from .skeleton import IDENTITY_3X4, Mat3x4, mul_3x4

VALUE_COUNT = 43
VALUE_OFFSET = 12  # bone.unknown_floats index of value slot 0 (record +0x40)

# Value-block slots (a curve's channel index is a slot index).
SLOT_SCALE = 0
SLOT_ROTATE = 3
SLOT_TRANSLATE = 6
SLOT_JOINT_ORIENT = 9
SLOT_ROTATE_PIVOT = 12
SLOT_SCALE_PIVOT = 15
SLOT_ROTATE_PIVOT_TRANSLATE = 18
SLOT_SCALE_PIVOT_TRANSLATE = 21
SLOT_ROTATE_AXIS = 24
SLOT_QUATERNION = 27

# Flag bits (group channel mask | bone record flags).
FLAG_SCALE = 0x8
FLAG_ROTATE = 0x10
FLAG_TRANSLATE = 0x20
FLAG_JOINT_ORIENT = 0x40
FLAG_ROTATE_PIVOT = 0x80
FLAG_SCALE_PIVOT = 0x100
FLAG_ROTATE_PIVOT_TRANSLATE = 0x200
FLAG_SCALE_PIVOT_TRANSLATE = 0x400
FLAG_ROTATE_AXIS = 0x800
ALL_CHANNELS = FLAG_SCALE | FLAG_ROTATE | FLAG_TRANSLATE

#: Rotation order code -> axes in application order (first applied first).
ROTATION_ORDERS = {1: "XYZ", 2: "YZX", 3: "ZXY", 4: "XZY", 5: "YXZ", 6: "ZYX"}


def bone_values(bone: skeleton.Bone) -> list[float]:
    return list(bone.unknown_floats[VALUE_OFFSET : VALUE_OFFSET + VALUE_COUNT])


def bone_flags(bone: skeleton.Bone) -> int:
    return bone.unknown_ints[2]


def rotation_order(bone: skeleton.Bone) -> int:
    return bone.unknown_shorts[1]


def skin_matrix(bone: skeleton.Bone) -> Mat3x4:
    f = bone.unknown_floats
    return (tuple(f[0:4]), tuple(f[4:8]), tuple(f[8:12]))  # type: ignore[return-value]


def translation(x: float, y: float, z: float) -> Mat3x4:
    return ((1.0, 0.0, 0.0, x), (0.0, 1.0, 0.0, y), (0.0, 0.0, 1.0, z))


def scaling(x: float, y: float, z: float) -> Mat3x4:
    return ((x, 0.0, 0.0, 0.0), (0.0, y, 0.0, 0.0), (0.0, 0.0, z, 0.0))


def axis_rotation(axis: str, degrees: float) -> Mat3x4:
    a = math.radians(degrees)
    c, s = math.cos(a), math.sin(a)
    if axis == "X":
        return ((1.0, 0.0, 0.0, 0.0), (0.0, c, -s, 0.0), (0.0, s, c, 0.0))
    if axis == "Y":
        return ((c, 0.0, s, 0.0), (0.0, 1.0, 0.0, 0.0), (-s, 0.0, c, 0.0))
    return ((c, -s, 0.0, 0.0), (s, c, 0.0, 0.0), (0.0, 0.0, 1.0, 0.0))


def euler_matrix(order: int, x: float, y: float, z: float) -> Mat3x4:
    angles = {"X": x, "Y": y, "Z": z}
    m = IDENTITY_3X4
    for axis in ROTATION_ORDERS.get(order, "XYZ"):
        if angles[axis] != 0.0:
            m = mul_3x4(axis_rotation(axis, angles[axis]), m)
    return m


def _pivoted(m: Mat3x4, pivot) -> Mat3x4:
    return mul_3x4(mul_3x4(translation(*pivot), m), translation(-pivot[0], -pivot[1], -pivot[2]))


def local_matrix(values: list[float], flags: int, order: int = 1) -> Mat3x4:
    """The engine's parent-relative bone matrix for a value block."""
    v = values
    m = IDENTITY_3X4
    if flags & FLAG_ROTATE:
        m = euler_matrix(order, *v[SLOT_ROTATE : SLOT_ROTATE + 3])
        if flags & FLAG_JOINT_ORIENT:
            m = mul_3x4(euler_matrix(order, *v[SLOT_JOINT_ORIENT : SLOT_JOINT_ORIENT + 3]), m)
        if flags & FLAG_ROTATE_AXIS:
            m = mul_3x4(m, euler_matrix(order, *v[SLOT_ROTATE_AXIS : SLOT_ROTATE_AXIS + 3]))
        if flags & FLAG_ROTATE_PIVOT:
            m = _pivoted(m, v[SLOT_ROTATE_PIVOT : SLOT_ROTATE_PIVOT + 3])
            if flags & FLAG_ROTATE_PIVOT_TRANSLATE:
                m = mul_3x4(translation(*v[SLOT_ROTATE_PIVOT_TRANSLATE : SLOT_ROTATE_PIVOT_TRANSLATE + 3]), m)
    if flags & FLAG_SCALE:
        s = scaling(*v[SLOT_SCALE : SLOT_SCALE + 3])
        if flags & FLAG_SCALE_PIVOT:
            s = _pivoted(s, v[SLOT_SCALE_PIVOT : SLOT_SCALE_PIVOT + 3])
            if flags & FLAG_SCALE_PIVOT_TRANSLATE:
                s = mul_3x4(translation(*v[SLOT_SCALE_PIVOT_TRANSLATE : SLOT_SCALE_PIVOT_TRANSLATE + 3]), s)
        m = mul_3x4(m, s)
    if flags & FLAG_TRANSLATE:
        m = mul_3x4(translation(*v[SLOT_TRANSLATE : SLOT_TRANSLATE + 3]), m)
    return m


def curve_value(curve: animation.AnimCurve, frame: float) -> float:
    """``interpolate_animation_frame_value``'s int16 path for one curve."""
    keys = curve.keyframes
    scale = 2.0 ** -(curve.scale_shift & 0x3F)
    if not keys:
        return 0.0
    whole = int(frame)
    if whole >= keys[-1].frame:
        return keys[-1].value * scale
    if whole < keys[0].frame:
        return keys[0].value * scale
    lo, hi = 0, len(keys) - 1
    while lo < hi:  # last key with key.frame <= whole
        mid = (lo + hi + 1) // 2
        if keys[mid].frame <= whole:
            lo = mid
        else:
            hi = mid - 1
    a, b = keys[lo], keys[lo + 1]
    t = (frame - a.frame) / (b.frame - a.frame)
    return (a.value + (b.value - a.value) * t) * scale


def local_matrices(
    bones: list[skeleton.Bone],
    anim: Optional[animation.GaAnimation] = None,
    frame: float = 0.0,
    seed: Optional[list[Mat3x4]] = None,
) -> list[Mat3x4]:
    """Every bone's local matrix at ``frame`` (bind seed when ``anim`` is None).
    ``seed`` may pass precomputed seed matrices to skip rebuilding them."""
    result = list(seed) if seed is not None else [skeleton.local_bind_matrix(b) for b in bones]
    if anim is None:
        return result
    for group in anim.groups:
        if not 0 <= group.bone_index < len(bones):
            continue
        bone = bones[group.bone_index]
        values = bone_values(bone)
        for curve in anim.curves[group.first_curve : group.first_curve + group.curve_count]:
            if 0 <= curve.channel < VALUE_COUNT:
                values[curve.channel] = curve_value(curve, frame)
        result[group.bone_index] = local_matrix(values, group.channel_mask | bone_flags(bone), rotation_order(bone))
    return result


def world_matrices(bones: list[skeleton.Bone], locals_: list[Mat3x4]) -> list[Mat3x4]:
    world: dict[int, Mat3x4] = {}

    def resolve(i: int, depth: int = 0) -> Mat3x4:
        if i not in world:
            parent = bones[i].parent_index
            if 0 <= parent < len(bones) and parent != i and depth < len(bones):
                world[i] = mul_3x4(resolve(parent, depth + 1), locals_[i])
            else:
                world[i] = locals_[i]
        return world[i]

    return [resolve(i) for i in range(len(bones))]


def skin_palette(bones: list[skeleton.Bone], world: list[Mat3x4]) -> list[Mat3x4]:
    """``world[b] x skin_matrix[b]`` - what a multi-matrix shape's vertex on
    bone ``b`` is drawn with."""
    return [mul_3x4(w, skin_matrix(b)) for w, b in zip(world, bones)]


def pose(bones: list[skeleton.Bone], anim: Optional[animation.GaAnimation] = None, frame: float = 0.0):
    """``(world, palette)`` at ``frame``."""
    world = world_matrices(bones, local_matrices(bones, anim, frame))
    return world, skin_palette(bones, world)


def apply(m: Mat3x4, p) -> tuple[float, float, float]:
    return tuple(m[r][0] * p[0] + m[r][1] * p[1] + m[r][2] * p[2] + m[r][3] for r in range(3))  # type: ignore[return-value]


def apply_direction(m: Mat3x4, d) -> tuple[float, float, float]:
    return tuple(m[r][0] * d[0] + m[r][1] * d[1] + m[r][2] * d[2] for r in range(3))  # type: ignore[return-value]


def posed_extent(
    bones: list[skeleton.Bone],
    boxes: dict[int, tuple[tuple[float, float, float], tuple[float, float, float]]],
    animations,
    step: int = 2,
) -> float:
    """Largest absolute coordinate that stored vertices inside ``boxes``
    (bone -> stored-space ``(min, max)``) reach through the skin palette,
    at rest and every ``step`` frames of each animation. A blended vertex
    is a weighted average of its bones' results, so its bones' boxes bound
    it too. An affine map's extremes over a box lie at its corners."""
    corners = {
        b: [(x, y, z) for x in (lo[0], hi[0]) for y in (lo[1], hi[1]) for z in (lo[2], hi[2])]
        for b, (lo, hi) in boxes.items()
    }
    extent = 0.0
    frames = [(None, 0.0)] + [
        (anim, float(f)) for anim in animations for f in range(0, anim.header.end_frame + 1, step)
    ]
    for anim, frame in frames:
        _world, palette = pose(bones, anim, frame)
        for b, points in corners.items():
            m = palette[b]
            for p in points:
                extent = max(extent, *(abs(c) for c in apply(m, p)))
    return extent


# ---------------------------------------------------------------- joint frames
#
# glTF-style joints for this rig: joint ``b``'s frame is ``world[b] x
# T(rotate_pivot[b])`` (its rest pivot), so a joint sits where the bone
# rotates about. Its parent-relative matrix is then
# ``T(-pivot[parent]) x local[b] x T(pivot[b])``, which is a plain
# translate/rotate/scale for every character bone, and its inverse bind
# matrix is the constant ``T(-pivot[b]) x skin_matrix[b]``: a stored vertex
# ``v`` of a multi-matrix shape is drawn at ``joint[b] x inverse_bind[b] x
# v = world[b] x skin[b] x v``, exactly the engine's palette.


def rest_pivot(bone: skeleton.Bone) -> tuple[float, float, float]:
    v = bone_values(bone)
    return tuple(v[SLOT_ROTATE_PIVOT : SLOT_ROTATE_PIVOT + 3])  # type: ignore[return-value]


def joint_local(bones: list[skeleton.Bone], index: int, local: Mat3x4) -> Mat3x4:
    parent = bones[index].parent_index
    pp = rest_pivot(bones[parent]) if 0 <= parent < len(bones) and parent != index else (0.0, 0.0, 0.0)
    return mul_3x4(mul_3x4(translation(-pp[0], -pp[1], -pp[2]), local), translation(*rest_pivot(bones[index])))


def inverse_bind(bone: skeleton.Bone) -> Mat3x4:
    p = rest_pivot(bone)
    return mul_3x4(translation(-p[0], -p[1], -p[2]), skin_matrix(bone))


def invert_3x4(m: Mat3x4) -> Mat3x4:
    a = [list(row[:3]) for row in m]
    det = (
        a[0][0] * (a[1][1] * a[2][2] - a[1][2] * a[2][1])
        - a[0][1] * (a[1][0] * a[2][2] - a[1][2] * a[2][0])
        + a[0][2] * (a[1][0] * a[2][1] - a[1][1] * a[2][0])
    )
    if abs(det) < 1e-12:
        return IDENTITY_3X4
    inv = [
        [(a[1][1] * a[2][2] - a[1][2] * a[2][1]) / det, (a[0][2] * a[2][1] - a[0][1] * a[2][2]) / det, (a[0][1] * a[1][2] - a[0][2] * a[1][1]) / det],
        [(a[1][2] * a[2][0] - a[1][0] * a[2][2]) / det, (a[0][0] * a[2][2] - a[0][2] * a[2][0]) / det, (a[0][2] * a[1][0] - a[0][0] * a[1][2]) / det],
        [(a[1][0] * a[2][1] - a[1][1] * a[2][0]) / det, (a[0][1] * a[2][0] - a[0][0] * a[2][1]) / det, (a[0][0] * a[1][1] - a[0][1] * a[1][0]) / det],
    ]
    t = [-sum(inv[r][k] * m[k][3] for k in range(3)) for r in range(3)]
    return tuple(tuple(inv[r]) + (t[r],) for r in range(3))  # type: ignore[return-value]


def _cross(a, b):
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


def orthonormal_columns(cols):
    """Rotation columns and scales of a 3x3 given as columns (no shear
    assumed). A zero-length column - a zero scale, which the game uses to
    hide parts such as the bow bone ``yumiya`` - gets scale 0 and a column
    completing a right-handed frame; a negative determinant flips X."""
    scale = [math.sqrt(sum(x * x for x in col)) for col in cols]
    unit = [tuple(x / n for x in col) if n > 1e-9 else None for col, n in zip(cols, scale)]
    for i in range(3):
        if scale[i] <= 1e-9:
            scale[i] = 0.0
    known = [i for i in range(3) if unit[i] is not None]
    if not known:
        unit = [(1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0)]
    elif len(known) == 1:
        k = known[0]
        axis = unit[k]
        helper = (1.0, 0.0, 0.0) if abs(axis[0]) < 0.9 else (0.0, 1.0, 0.0)
        a = _cross(axis, helper)
        n = math.sqrt(sum(x * x for x in a))
        a = tuple(x / n for x in a)
        unit[(k + 1) % 3] = a
        unit[(k + 2) % 3] = _cross(axis, a)
    elif len(known) == 2:
        missing = next(i for i in range(3) if unit[i] is None)
        unit[missing] = _cross(unit[(missing + 1) % 3], unit[(missing + 2) % 3])
    det = sum(unit[0][i] * _cross(unit[1], unit[2])[i] for i in range(3))
    if det < 0:
        unit[0] = tuple(-x for x in unit[0])
        scale[0] = -scale[0]
    return unit, scale


def decompose(m: Mat3x4):
    """``(translation, rotation 3x3 rows, scale)`` of an affine matrix with no
    shear (``m = T x R x S``); see :func:`orthonormal_columns`."""
    t = (m[0][3], m[1][3], m[2][3])
    unit, scale = orthonormal_columns([[m[r][c] for r in range(3)] for c in range(3)])
    rot = tuple(tuple(unit[c][r] for c in range(3)) for r in range(3))
    return t, rot, tuple(scale)


def euler_from_matrix(rot, previous: Optional[tuple[float, float, float]] = None) -> tuple[float, float, float]:
    """Degrees ``(x, y, z)`` with ``rot = Rz . Ry . Rx`` (rotation order 1).
    With ``previous``, each angle is moved by whole turns to the value
    closest to it, so linearly interpolated keys don't spin the long way."""
    sy = -rot[2][0]
    sy = max(-1.0, min(1.0, sy))
    y = math.degrees(math.asin(sy))
    if abs(sy) < 1.0 - 1e-12:
        x = math.degrees(math.atan2(rot[2][1], rot[2][2]))
        z = math.degrees(math.atan2(rot[1][0], rot[0][0]))
    else:  # gimbal lock: y is +-90 and only x -+ z matters; put it all in x
        y = math.copysign(90.0, sy)
        x = math.degrees(math.atan2(-rot[1][2], rot[1][1]))
        z = 0.0
    angles = [x, y, z]
    if previous is not None:
        for i in range(3):
            angles[i] += 360.0 * round((previous[i] - angles[i]) / 360.0)
    return tuple(angles)  # type: ignore[return-value]
