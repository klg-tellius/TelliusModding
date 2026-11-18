"""Read and write a ``.ga`` animation file - skeletal animation curves for a
``.g`` skeleton (:mod:`skeleton`) / ``.gs`` mesh (:mod:`model`).

The Noesis plugin used as a research reference for ``.g`` and ``.gs``
(https://github.com/Zheneq/Noesis-Plugins) does not implement ``.ga``.
This module implements the animation layout investigated by this project.
The recorded validation corpus covered 4,422 animation files, including
loose files and animations inside archives.

Layout::

    0x00  header, 12 big-endian uint32 words (see GaHeader)
    0x30  bone-group table, header word 7 records of 16 bytes (word 8 = 0x30)
          curve_table_addr   12-byte curve records
          keyframe_data_addr (frame, value) keyframe pairs, 4 bytes each,
                             one run per curve, in curve order, no sharing
          [footer_addr]      optional 9-slot footer, right after the keyframes

The loader relocation (``fixup_animation_pointer_offsets``, ``0x80063A14``)
confirms which words are file offsets: 0 (footer), 1 (always 0), 8 (group
table), 9 (curve table), 10 (always 0) and 11 (keyframes).

**The curve table's real length is derived, not stored.** The table runs
from ``curve_table_addr`` all the way to ``keyframe_data_addr``, always an
exact multiple of 12 bytes.

**Bone assignment comes from the group table.** Each 16-byte group record is
``(bone_index, channel_mask, first_curve, curve_count)``: curves
``[first_curve, first_curve + curve_count)`` all drive ``bone_index``. The
table starts at ``0x30`` - earlier versions of this module read a 16-word
header and started the table at ``0x40``, which made the first record look
like header words 12-15 and led to a wrong "implicit bone 0" reading. The
first group names a real bone (bone 1 - the hip - on 1,294 files, bone 0 on
only 319). Confirmed: header word 7 equals the record count; the first
record's ``first_curve`` is 0; each group's ``first_curve`` equals the
previous group's end; the last group's end equals the curve count; bone
indices strictly ascend.

**Channels.** A curve record's first field is a channel index, not a bone:
the index of the slot it overwrites in the bone's 43-float value block (see
:mod:`engine_pose`, which ports the engine's evaluation). 0-2 scale X/Y/Z,
3-5 rotate X/Y/Z (degrees), 6-8 translate X/Y/Z, 12-14 the rotate pivot.
The group's ``channel_mask`` says which families are present - bit 3
scale, bit 4 rotate, bit 5 translate (``build_bone_local_matrix``,
``0x80062920``) - and matches its curves' own channel indices (the pivot
family appears under mask 0: it only matters through the bone's own
pivot flag). Earlier versions of this module had scale and translate
swapped.

**Keyframes** are ``(frame: uint16, value: int16)`` pairs, 4 bytes each.
Frames ascend within a curve, and a curve record's third field is exactly
its own last frame. A value is ``raw * 2 ** -scale_shift``
(:meth:`AnimCurve.scaled_value`; ``scale_shift`` is the high byte of the
record's second field) and is **absolute**: it replaces the skeleton's value
for that slot (``interpolate_animation_frame_value``, ``0x80063614``).
Between keys values are linear in the frame; before the first and after
the last key the end values hold.

**Header words 3-6** (``gactor_update_animation_timer``, ``0x80060060``,
and the evaluator): word 3 is the format (``0x11`` on every file: bit 0
Euler rotation, bit 1 quaternion rotation, bit 4 int16 keys - without it
the engine reads a float/Hermite layout no file uses), word 4 the loop flag,
word 5 the frame a loop restarts at, word 6 the frame the animation ends
at (it may run past the last key, holding the final pose).

**Footer.** Nine big-endian words of file offsets (the loader relocates all
nine; for the first eight it also stores ``block + 8`` into the block's
second word at runtime), one zero pad word, then the pointed-to blocks back
to back. Slot 0 is the **event track** (``find_animation_frames_in_time_range``,
``0x800651FC``): a ``u16`` key count, a pad halfword, a runtime pointer
word, ``count`` ``u16`` offsets, then ``count`` keys of ``(frame: u16,
code_count: u16, codes: u16...)``. Each frame the engine collects (up to
four) codes whose frame was crossed and acts on them - ``3``/``4`` mark a
loop start/end, ``0x1C``/``0x1D`` set/clear a battle flag, ``0x28``/``0x29``
spawn camera/light effects; the rest are read elsewhere (``0`` lands a
hit, ``1`` advances a miss, ``6``/``7`` are ignored Ward-effect markers,
and codes at least 1000 are looked up in
``gcfesnd.bin``'s ``SFXTable`` and played as sound cues).
Slot 1 holds **material alpha tracks** (:func:`read_material_tracks`,
``interpolate_animation_keyframe_value``, ``0x80064938``): the same head
(count, pad, runtime pointer word, ``count`` ``u16`` offsets, ``0xFFFF`` for
none) with one track per ``.gs`` material, each a ``u16`` key count, a
``u16`` mode (0 linear, 1 step) and ``(frame: u16, value: s16)`` keys; the
value (0-255) replaces the material's alpha, which is how effects fade in
and out. Slot 2 is laid out the same with RGB565 colours
(``interpolate_keyframe_color``; no vanilla effect uses it), slots 3/4 are
the U/V scroll tracks (``interpolate_animation_channel_uv_scale_u``/``_v``), read only by
the map water shader ``setup_map_texture_material_multi_pass`` as scroll speeds (never by effects)
and slot 8 the particle emitters (``update_actor_material_runtime``).
:func:`read_particle_table_layout` exposes its confirmed header, emitter,
stage and curve/key ranges; the unresolved controls and original block remain
raw. Other slots on effect (``yme/``) and scenery (``zbg/``, ``zmap/``)
animations remain raw. A footer whose nine slots are all zero is valid.
"""

from __future__ import annotations

import io
import struct
from dataclasses import dataclass, field
from pathlib import Path
from typing import BinaryIO, Optional

HEADER_WORDS = 12
HEADER_SIZE = HEADER_WORDS * 4  # 0x30
GROUP_RECORD_SIZE = 16
CURVE_RECORD_SIZE = 12
SAMPLE_SIZE = 4
FOOTER_SLOTS = 9
FOOTER_LEAD_IN_SIZE = 40  # nine slot words + one pad word

CHANNEL_SCALE = range(0, 3)
CHANNEL_ROTATE = range(3, 6)
CHANNEL_TRANSLATE = range(6, 9)
CHANNEL_ROTATE_PIVOT = range(12, 15)

MASK_SCALE = 0x08
MASK_ROTATE = 0x10
MASK_TRANSLATE = 0x20

FORMAT_EULER_INT16 = 0x11  # header word 3 on every file

_CHANNEL_NAMES = {
    0: "scale_x", 1: "scale_y", 2: "scale_z",
    3: "rotate_x", 4: "rotate_y", 5: "rotate_z",
    6: "translate_x", 7: "translate_y", 8: "translate_z",
    12: "rotate_pivot_x", 13: "rotate_pivot_y", 14: "rotate_pivot_z",
}

# Header words that hold layout-derived values; write_animation() recomputes them.
_W_FOOTER, _W_GROUP_COUNT, _W_GROUP_TABLE, _W_CURVE_TABLE, _W_KEYFRAMES = 0, 7, 8, 9, 11


class AnimationError(Exception):
    pass


def channel_name(channel: int) -> str:
    """Name for a curve's channel (value-block slot) index, or
    ``"channel_<n>"`` for a slot no file animates."""
    return _CHANNEL_NAMES.get(channel, f"channel_{channel}")


@dataclass(frozen=True)
class GaHeader:
    words: tuple[int, ...]  # the 12 raw header words, see module docstring

    @property
    def footer_addr(self) -> int:
        """Word 0 - the footer's file offset, or 0 when there is none."""
        return self.words[_W_FOOTER]

    @property
    def format_flags(self) -> int:
        """Word 3 - ``0x11`` (Euler rotation, int16 keys) on every file."""
        return self.words[3]

    @property
    def loops(self) -> bool:
        """Word 4 - nonzero when the animation loops."""
        return self.words[4] != 0

    @property
    def loop_start_frame(self) -> int:
        """Word 5 - the frame a loop restarts at."""
        return self.words[5]

    @property
    def end_frame(self) -> int:
        """Word 6 - the frame playback ends (or loops) at."""
        return self.words[6]

    @property
    def animated_bone_count(self) -> int:
        """Word 7 - the number of group records (one per animated bone)."""
        return self.words[_W_GROUP_COUNT]

    @property
    def group_table_addr(self) -> int:
        return self.words[_W_GROUP_TABLE]

    @property
    def curve_table_addr(self) -> int:
        return self.words[_W_CURVE_TABLE]

    @property
    def keyframe_data_addr(self) -> int:
        return self.words[_W_KEYFRAMES]


@dataclass(frozen=True)
class Keyframe:
    frame: int
    value: int  # signed - see the module docstring


@dataclass(frozen=True)
class AnimCurve:
    bone_index: int  # resolved from the owning group
    channel: int  # see channel_name()
    scale_shift: int  # value = raw * 2 ** -scale_shift
    end_frame: int  # equals the last keyframe's frame in every real file
    keyframes: list[Keyframe] = field(repr=False)

    def scaled_value(self, keyframe: Keyframe) -> float:
        """The key's value in the slot's own unit (degrees for rotation)."""
        return keyframe.value / (1 << (self.scale_shift & 0x3F))


@dataclass(frozen=True)
class BoneGroup:
    bone_index: int
    channel_mask: int  # MASK_SCALE / MASK_ROTATE / MASK_TRANSLATE bits
    first_curve: int
    curve_count: int


@dataclass(frozen=True)
class EventKey:
    """One key of the footer's event track: the codes fired at ``frame``."""

    frame: int
    codes: tuple[int, ...]


@dataclass
class GaFooter:
    """The 9-slot footer. ``blocks[i]`` is slot ``i``'s raw block (or None
    when the slot is 0); ``order`` lists the used slots in file order."""

    blocks: list[Optional[bytes]] = field(default_factory=lambda: [None] * FOOTER_SLOTS)
    order: list[int] = field(default_factory=list)
    pad_word: int = 0
    trailing: bytes = b""  # bytes after the lead-in that no slot points at (the empty-footer variant)
    # FE10 uses a compact 12-byte descriptor whose kind-specific block can
    # point backwards into the animation. Its semantics are not decoded yet;
    # preserving it verbatim still permits curve playback and lossless writes.
    compact_raw: Optional[bytes] = None


@dataclass
class GaAnimation:
    header: GaHeader
    groups: list[BoneGroup]
    curves: list[AnimCurve] = field(repr=False)
    events: list[EventKey] = field(default_factory=list)
    footer: Optional[GaFooter] = None
    # Opaque bytes between the final decoded keyframe and the footer (or
    # EOF). FE10 effect/weapon animations can keep kind-specific payloads
    # here even when their ordinary bone group count is zero.
    body_trailing: bytes = b""
    # Radiant Dawn: where the footer region (body_trailing + compact_raw) started in the file read,
    # so write_animation can move its file offsets when the keyframes change size.
    fe10_region_start: Optional[int] = None

    def curves_for_bone(self, bone_index: int) -> list[AnimCurve]:
        return [c for c in self.curves if c.bone_index == bone_index]

    def material_alphas(self) -> dict[int, "MaterialTrack"]:
        """Footer slot 1's alpha track per material index (empty when there is none)."""
        block = self.footer.blocks[MATERIAL_ALPHA_SLOT] if self.footer is not None else None
        return read_material_tracks(block) if block else {}

    @property
    def length_in_frames(self) -> int:
        """The engine's playback end frame, including footer-only effects."""
        return self.header.end_frame


MATERIAL_ALPHA_SLOT = 1


@dataclass(frozen=True)
class MaterialTrack:
    """One material's keys in a footer track table (slot 1 alpha, slot 2 colour)."""

    mode: int  # 0 linear, 1 step (any other mode reads 0 between keys)
    keys: tuple  # (frame, value) pairs, frames ascending

    def value(self, frame: float) -> int:
        """The track at ``frame`` as ``interpolate_animation_keyframe_value`` reads it: the
        first key's value before it, the last one's after it, linear (mode 0) or held (mode 1)
        between keys."""
        keys = self.keys
        if not keys:
            return 0
        whole = int(frame)
        index = -1
        for i, (key_frame, _value) in enumerate(keys):
            if key_frame <= whole:
                index = i
            else:
                break
        if index < 0:
            return keys[0][1]
        if index >= len(keys) - 1 or self.mode == 1:
            return keys[index][1]
        if self.mode != 0:
            return 0
        (f0, v0), (f1, v1) = keys[index], keys[index + 1]
        return int(v0 + (v1 - v0) * (frame - f0) / (f1 - f0)) if f1 != f0 else v0


def read_material_tracks(block: bytes) -> dict[int, MaterialTrack]:
    """Decode a footer track table (slot 1 or 2): ``{material index: MaterialTrack}``."""
    if len(block) < 8:
        return {}
    (count,) = struct.unpack(">H", block[0:2])
    offsets = struct.unpack(f">{count}H", block[8:8 + 2 * count])
    tracks = {}
    for index, offset in enumerate(offsets):
        if offset == 0xFFFF or offset + 4 > len(block):
            continue
        keys, mode = struct.unpack(">HH", block[offset:offset + 4])
        values = struct.unpack(f">{2 * keys}h", block[offset + 4:offset + 4 + 4 * keys])
        tracks[index] = MaterialTrack(mode, tuple(zip(values[0::2], values[1::2])))
    return tracks


@dataclass(frozen=True)
class ParticleEmitterLayout:
    """Confirmed offsets in one slot-8 particle emitter (GParticle.cpp reader)."""

    record_offset: int
    name_path: str
    local_index: int  # record +4; equals emitter position in tested effect packs
    first_stage_index: int  # record +8; cumulative stages in preceding emitters
    material_index: int
    draw_flags: int
    unresolved_control: int  # emitter +0x0C; no runtime reader identified
    initial_scale_st: tuple[float, float]
    initial_rotation_degrees: float
    stage_count: int
    stages_offset: int
    stage_curves_offset: int
    curves_offset: int
    keys_offset: int
    curve_count: int


@dataclass(frozen=True)
class ParticleTableLayout:
    """Structural view of the particle table; the original bytes remain untouched."""

    block_offset: int
    emitters: tuple[ParticleEmitterLayout, ...]


@dataclass(frozen=True)
class ParticleStageLayout:
    """One emitter stage's frame window, initial position and curve range."""

    local_index: int  # source stage +0; equals stage position on every tested effect
    global_index: int  # curve-range table +0; checked against runtime counter
    start_frame: int
    end_frame: int
    initial_position: tuple[float, float, float]
    first_curve: int
    curve_count: int


PARTICLE_CURVE_CHANNELS = (
    "velocity X", "velocity Y", "velocity Z", "scale S+T", "alpha",
    "red", "green", "blue", "scale S", "scale T", "rotation Z",
)


@dataclass(frozen=True)
class ParticleCurveLayout:
    """Runtime-read curve channel, scale and key range."""

    channel: int
    channel_name: str
    scale_shift: int
    last_key_frame: int  # descriptor +4; equals the final key's frame in tested packs
    key_count: int
    first_key: int


def read_particle_curve_keys(data: bytes, emitter: ParticleEmitterLayout,
                             curve: ParticleCurveLayout) -> tuple[tuple[int, float], ...]:
    """Return the curve's frame/value keys in the units used by the runtime."""
    offset = emitter.keys_offset + curve.first_key * 4
    end = offset + curve.key_count * 4
    if end > len(data):
        raise AnimationError("Particle curve key range exceeds the animation file.")
    divisor = 1 << curve.scale_shift
    return tuple((frame, value / divisor)
                 for frame, value in struct.iter_unpack(">Hh", data[offset:end]))


def sample_particle_curve(keys: tuple[tuple[int, float], ...], frame: float) -> float:
    """Clamp or linearly interpolate a particle channel at its local stage frame."""
    if not keys:
        return 0.0
    if frame <= keys[0][0]:
        return keys[0][1]
    for (left_frame, left_value), (right_frame, right_value) in zip(keys, keys[1:]):
        if frame < right_frame:
            span = right_frame - left_frame
            return left_value + (right_value - left_value) * (frame - left_frame) / span if span else right_value
    return keys[-1][1]


def read_particle_curve(data: bytes, emitter: ParticleEmitterLayout, index: int) -> ParticleCurveLayout:
    """Read one curve descriptor; uninterpreted descriptor bits stay in the source."""
    if not 0 <= index < emitter.curve_count:
        raise IndexError(index)
    channel, flags, _padding, last_key_frame, key_count, first_key = struct.unpack_from(
        ">HBBHHI", data, emitter.curves_offset + index * 12)
    name = PARTICLE_CURVE_CHANNELS[channel] if channel < len(PARTICLE_CURVE_CHANNELS) else f"channel {channel}"
    return ParticleCurveLayout(channel, name, flags & 0x3F, last_key_frame, key_count, first_key)


def read_particle_stage(data: bytes, emitter: ParticleEmitterLayout, index: int) -> ParticleStageLayout:
    """Read one validated emitter stage without allocating the entire stage table."""
    if not 0 <= index < emitter.stage_count:
        raise IndexError(index)
    at = emitter.stages_offset + index * 12
    range_at = emitter.stage_curves_offset + index * 8
    local_index, start, end, x, y, z = struct.unpack_from(">Hhhhhh", data, at)
    global_index, _reserved, first_curve, curve_count = struct.unpack_from(">HHHH", data, range_at)
    return ParticleStageLayout(local_index, global_index, start, end, (x / 64, y / 64, z / 64),
                               first_curve, curve_count)


def read_particle_table_layout(data: bytes, block: int | None = None) -> ParticleTableLayout | None:
    """Read the confirmed portion of footer slot 8 from a whole ``.ga`` file.

    ``block`` is the table's file offset; when omitted it comes from PoR's
    nine-word footer, or Radiant Dawn's slot 13. Radiant Dawn stores the same table as compact-footer
    slot 13 (``fe10_footer_chain``): RFEE01 ``main.dol`` checks the same
    0x12345678 magic (``0x8001528c``), relocates the same five record
    pointers (``0x800151ec``) and reads stages, curve ranges, curves and keys
    with the same strides and channel switch (``0x800159xx``).

    Offsets in this table refer to the start of the ``.ga``, rather than the
    slot-8 block. Each emitter has 0x34 bytes, one 0x0C-byte stage per count,
    one 8-byte curve range per stage, 0x0C-byte curve descriptors, and 4-byte
    ``(frame: u16, value: s16)`` keys. The emitter's less understood settings
    stay in the original bytes; this reader never rewrites them.
    """
    if len(data) < HEADER_SIZE:
        raise AnimationError("Animation header is truncated.")
    if block is None:
        footer = struct.unpack_from(">I", data)[0]
        if not footer:
            return None
        if is_fe10_animation(data):
            found = fe10_footer_blocks(data).get(FE10_PARTICLE_SLOT)
            if found is None:
                return None
            return read_particle_table_layout(data, found[0])
        if footer + FOOTER_LEAD_IN_SIZE > len(data):
            raise AnimationError("Animation footer is truncated.")
        block = struct.unpack_from(">I", data, footer + 8 * 4)[0]
        if not block:
            return None
    if block + 8 > len(data) or data[block:block + 4] != b"\x12\x34\x56\x78":
        raise AnimationError("Particle table has no 0x12345678 header.")
    count = struct.unpack_from(">H", data, block + 6)[0]
    table_end = block + 8 + count * 0x34
    if table_end > len(data):
        raise AnimationError("Particle emitter table is truncated.")
    emitters = []
    for index in range(count):
        rec = block + 8 + index * 0x34
        name_ptr = struct.unpack_from(">I", data, rec)[0]
        local_index = struct.unpack_from(">H", data, rec + 4)[0]
        first_stage_index = struct.unpack_from(">H", data, rec + 8)[0]
        material_index = struct.unpack_from(">h", data, rec + 0x0A)[0]
        draw_flags = struct.unpack_from(">H", data, rec + 6)[0]
        unresolved_control = struct.unpack_from(">H", data, rec + 0x0C)[0]
        mode = draw_flags & 7
        if mode == 4:
            initial_scale_st = tuple(value / 64.0 for value in struct.unpack_from(">2h", data, rec + 0x16))
        elif mode == 2:
            scale = struct.unpack_from(">h", data, rec + 0x12)[0] / 64.0
            initial_scale_st = (scale, scale)
        elif mode == 1:
            scale = struct.unpack_from(">h", data, rec + 0x0E)[0] / 64.0
            initial_scale_st = (scale, scale)
        else:
            initial_scale_st = (1.0, 1.0)
        initial_rotation_degrees = struct.unpack_from(">h", data, rec + 0x1A)[0] / 64.0
        stages = struct.unpack_from(">H", data, rec + 0x1E)[0]
        stages_ptr, stage_curves_ptr, curves_ptr, keys_ptr = struct.unpack_from(">4I", data, rec + 0x20)
        if any(ptr < table_end or ptr > len(data) for ptr in (stages_ptr, stage_curves_ptr, curves_ptr, keys_ptr)):
            raise AnimationError(f"Particle emitter {index} has an out-of-range table pointer.")
        if stages_ptr + stages * 12 > len(data) or stage_curves_ptr + stages * 8 > len(data):
            raise AnimationError(f"Particle emitter {index} has truncated stage tables.")
        if curves_ptr > keys_ptr or (keys_ptr - curves_ptr) % 12:
            raise AnimationError(f"Particle emitter {index} has an invalid curve table.")
        curve_count = (keys_ptr - curves_ptr) // 12
        for stage in range(stages):
            first, length = struct.unpack_from(">HH", data, stage_curves_ptr + stage * 8 + 4)
            if first + length > curve_count:
                raise AnimationError(f"Particle emitter {index} has an invalid stage curve range.")
        for curve in range(curve_count):
            curve_at = curves_ptr + curve * 12
            key_count = struct.unpack_from(">H", data, curve_at + 6)[0]
            first_key = struct.unpack_from(">I", data, curve_at + 8)[0]
            if keys_ptr + (first_key + key_count) * 4 > len(data):
                raise AnimationError(f"Particle emitter {index} has an invalid key range.")
        if not table_end <= name_ptr < len(data):
            raise AnimationError(f"Particle emitter {index} has an invalid name pointer.")
        end_name = data.find(b"\0", name_ptr)
        if end_name < 0:
            raise AnimationError(f"Particle emitter {index} has an unterminated name path.")
        name_path = data[name_ptr:end_name].decode("shift_jis", errors="replace")
        emitters.append(ParticleEmitterLayout(rec, name_path, local_index, first_stage_index,
                                              material_index, draw_flags, unresolved_control, initial_scale_st,
                                              initial_rotation_degrees, stages,
                                              stages_ptr, stage_curves_ptr, curves_ptr, keys_ptr, curve_count))
    return ParticleTableLayout(block, tuple(emitters))


def fe10_footer_chain(data: bytes, footer_start: int) -> list[tuple[int, int, int]]:
    """Walk Radiant Dawn's compact footer: a linked list of 12-byte
    ``(slot, block offset, next descriptor offset)`` triples starting at header
    word 0 and ending at a zero ``next``. Returns ``(descriptor, slot, block)``
    in chain order. Every shipped RD ``.ga`` with a footer places its first
    block right after the keyframe data and the descriptors after the blocks.
    """
    chain, seen, at = [], set(), footer_start
    while at:
        if at in seen or at + 12 > len(data):
            raise AnimationError(f"Footer chain breaks at {at:#x}.")
        seen.add(at)
        slot, block, nxt = struct.unpack_from(">3I", data, at)
        if block >= len(data):
            raise AnimationError(f"Footer block {block:#x} is outside the file.")
        chain.append((at, slot, block))
        at = nxt
    return chain


# Radiant Dawn's compact-footer slot numbers (RFEE01 ``main.dol``). Slots 0,
# 6-12, 14 and 15 hold the same key tables as PoR's slots 1-4
# (``read_material_tracks``: indexed by material, or by bone for slot 0);
# slot 5 is the event track, slot 13 the particle emitter table
# (``read_particle_table_layout``).
FE10_FOOTER_SLOT_NAMES = {
    0: "bone visibility",  # 0x8000db10: track mode word = bone index; value 0 scales the bone to zero
    5: "events",  # 0x80009bc8-0x8000a22c, find/collect keys by frame and code
    6: "material alpha",  # 0x8000ab6c: 8-bit value per material
    7: "material colour",  # 0x8000a838 with slot 7: RGB565 value, multiplies the material colour
    8: "texture translate U",  # 0x8000ae38 -> PSMTXTrans in 0x80012f00
    9: "texture translate V",  # 0x8000b100, negated before PSMTXTrans
    10: "texture rotation",  # 0x8000b3c8 -> rotation about Z
    11: "texture scale U",  # 0x8000b690 -> PSMTXScale
    12: "texture scale V",  # 0x8000b958 -> PSMTXScale
    13: "particle emitters",  # 0x8001528c setup, 0x800159xx update
    14: "material colour (slot 14)",  # 0x8000a838 with slot 14
    15: "material colour (slot 15)",  # 0x8000a838 with slot 15
}
# Slots 1-3 have the same table shape; 0x8000bf68 (slot 1) and 0x8000c3c4
# (slot 2) read them with extra fields (block +2, key +2/+3) whose meaning
# is not traced yet.
FE10_OPEN_TRACK_SLOTS = frozenset((1, 2, 3))
FE10_MATERIAL_TRACK_SLOTS = frozenset((0, 6, 7, 8, 9, 10, 11, 12, 14, 15))
FE10_EVENT_SLOT = 5
FE10_PARTICLE_SLOT = 13


@dataclass(frozen=True)
class Fe10EventKey:
    """One key of Radiant Dawn's event track (compact-footer slot 5)."""

    frame: int
    codes: tuple[tuple[int, int], ...]  # (code, signed parameter)


def read_fe10_event_block(block: bytes) -> list[Fe10EventKey]:
    """Decode Radiant Dawn's slot-5 event track.

    Layout: u16 key count, u16 pad, a runtime pointer word (the loader sets it
    to block+8), then one u16 key offset per key (from the block start,
    0xFFFF for none). Each key is u16 frame, u8 pad, u8 code count, then
    ``count`` 4-byte ``(u16 code, s16 parameter)`` pairs. ``0x80009d60``
    matches codes at key +4 with stride 4 and count at key +3; ``0x800e2a78``
    compares code 0x1F's parameter with a battle index.
    """
    if len(block) < 8:
        raise AnimationError("Event track header is truncated.")
    (count,) = struct.unpack_from(">H", block)
    if 8 + 2 * count > len(block):
        raise AnimationError("Event track offsets are truncated.")
    keys = []
    for offset in struct.unpack_from(f">{count}H", block, 8):
        if offset == 0xFFFF:
            continue
        if offset + 4 > len(block):
            raise AnimationError(f"Event key at {offset:#x} is outside the block.")
        frame, pad, n = struct.unpack_from(">HBB", block, offset)
        if pad or offset + 4 + 4 * n > len(block):
            raise AnimationError(f"Event key at {offset:#x} is malformed.")
        pairs = struct.unpack_from(f">{2 * n}H", block, offset + 4)
        codes = tuple((pairs[i], pairs[i + 1] - 0x10000 if pairs[i + 1] & 0x8000 else pairs[i + 1])
                      for i in range(0, 2 * n, 2))
        keys.append(Fe10EventKey(frame, codes))
    return keys


def write_fe10_event_block(keys: list[Fe10EventKey]) -> bytes:
    """Encode Radiant Dawn's slot-5 event track (the layout :func:`read_fe10_event_block` reads);
    the runtime pointer word is written as zero, as on the disc."""
    if any(b.frame < a.frame for a, b in zip(keys, keys[1:])):
        raise AnimationError("Event frames must be in ascending order.")
    offsets, body = [], bytearray()
    head = 8 + 2 * len(keys)  # keys follow the offsets directly, as on the disc
    for key in keys:
        if not 0 <= key.frame <= 0xFFFF or len(key.codes) > 0xFF:
            raise AnimationError("An event key has a frame past 65535 or more than 255 codes.")
        offsets.append(head + len(body))
        body += struct.pack(">HBB", key.frame, 0, len(key.codes))
        for code, parameter in key.codes:
            if not 0 <= code <= 0xFFFF or not -0x8000 <= parameter <= 0x7FFF:
                raise AnimationError("An event code is 0-65535 and its parameter -32768 to 32767.")
            body += struct.pack(">Hh", code, parameter)
    if head + len(body) > 0xFFFF:
        raise AnimationError("The event track is too large.")
    block = struct.pack(">HHI", len(keys), 0, 0) + struct.pack(f">{len(keys)}H", *offsets) + body
    return block + bytes(-len(block) % 4)


# -- Radiant Dawn footer edits --------------------------------------------------------------------
#
# The compact footer's descriptors and the particle table hold file offsets, so a block is never
# moved: a new block is appended at the end of the file and its descriptor repointed, the old block
# staying behind unread (the particle editor already grows the slot-13 table this way). A slot the
# file does not have gets a new descriptor at the end, linked in as the chain's head.

def is_fe10_animation(data: bytes) -> bool:
    """A Radiant Dawn ``.ga``: header byte 8 is the loader's footer switch (RFEE01 ``0x8000bc20``),
    1 on every Radiant Dawn file and 0 on Path of Radiance's; a footer too short for Path of
    Radiance's nine words is also Radiant Dawn's."""
    if len(data) < HEADER_SIZE:
        raise AnimationError("Animation header is truncated.")
    footer = struct.unpack_from(">I", data)[0]
    return data[8] == 1 or bool(footer) and len(data) - footer < FOOTER_LEAD_IN_SIZE


def fe10_footer_blocks(data: bytes) -> dict[int, tuple[int, int]]:
    """Slot -> (block offset, end) of a Radiant Dawn ``.ga``'s footer. A block ends where the next
    block or descriptor starts (or at the end of the file)."""
    footer = struct.unpack_from(">I", data)[0]
    if not footer:
        return {}
    chain = fe10_footer_chain(data, footer)
    starts = sorted({block for _d, _s, block in chain} | {d for d, _s, _b in chain} | {len(data)})
    out = {}
    for _descriptor, slot, block in chain:
        out.setdefault(slot, (block, next(s for s in starts if s > block)))
    return out


def footer_block(data: bytes, slot: int) -> Optional[bytes]:
    """Footer slot ``slot``'s block, or None (either game)."""
    if is_fe10_animation(data):
        found = fe10_footer_blocks(data).get(slot)
        return data[found[0]:found[1]] if found else None
    anim = read_animation_bytes(data)
    return anim.footer.blocks[slot] if anim.footer and 0 <= slot < FOOTER_SLOTS else None


def fe10_events(data: bytes) -> list[Fe10EventKey]:
    """A Radiant Dawn ``.ga``'s event track (slot 5), or [] when it has none."""
    found = fe10_footer_blocks(data).get(FE10_EVENT_SLOT) if is_fe10_animation(data) else None
    return read_fe10_event_block(data[found[0]:found[1]]) if found else []


def fe10_set_footer_block(data: bytes, slot: int, block: Optional[bytes]) -> bytes:
    """``data`` (a Radiant Dawn ``.ga``) with footer slot ``slot`` holding ``block``; None removes
    the slot from the chain. Nothing already in the file moves (see above)."""
    if not 0 <= slot <= 15:
        raise AnimationError("Radiant Dawn footer slots run from 0 to 15.")
    out = bytearray(data)
    footer = struct.unpack_from(">I", out)[0]
    chain = fe10_footer_chain(bytes(out), footer) if footer else []
    found = next((item for item in chain if item[1] == slot), None)
    if block is None:
        if found is None:
            return data
        descriptor = found[0]
        following = struct.unpack_from(">I", out, descriptor + 8)[0]
        previous = next((d for d, _s, _b in chain
                         if struct.unpack_from(">I", out, d + 8)[0] == descriptor), None)
        if previous is None:
            struct.pack_into(">I", out, 0, following)
        else:
            struct.pack_into(">I", out, previous + 8, following)
        return bytes(out)
    out += bytes(-len(out) % 4)
    at = len(out)
    out += block + bytes(-len(block) % 4)
    if found is not None:
        struct.pack_into(">I", out, found[0] + 4, at)
    else:
        descriptor = len(out)
        out += struct.pack(">3I", slot, at, footer)
        struct.pack_into(">I", out, 0, descriptor)
    out[8] = max(out[8], 1)  # the loader drops a footer while header byte 8 is 0
    return bytes(out)


def _fe10_pointer_fields(data: bytes) -> list[int]:
    """Every word of a Radiant Dawn ``.ga`` that holds a file offset into the footer region: header
    word 0, each descriptor's block and next words, and the particle table's record pointers."""
    footer = struct.unpack_from(">I", data)[0]
    if not footer:
        return []
    fields = [0]
    for descriptor, slot, block in fe10_footer_chain(data, footer):
        fields += [descriptor + 4, descriptor + 8]
        if slot == FE10_PARTICLE_SLOT:
            layout = read_particle_table_layout(data, block)
            for emitter in layout.emitters if layout else ():
                fields += [emitter.record_offset + offset for offset in (0, 0x20, 0x24, 0x28, 0x2C)]
    return fields


def fe10_rebase_footer(data: bytes, old_start: int, body: bytes) -> bytes:
    """``body`` (a new file up to the end of its keyframes) followed by ``data``'s footer region,
    everything from ``old_start`` (the end of ``data``'s keyframes): every footer pointer
    (:func:`_fe10_pointer_fields`) at or past ``old_start`` moves by the difference, header word 0
    included."""
    delta = len(body) - old_start
    out = bytearray(body) + data[old_start:]
    for field_at in _fe10_pointer_fields(data):
        value = struct.unpack_from(">I", data, field_at)[0]
        if value >= old_start and (field_at == 0 or field_at >= old_start):
            struct.pack_into(">I", out, field_at + (delta if field_at else 0), value + delta)
    return bytes(out)


def read_event_block(block: bytes) -> list[EventKey]:
    """Decode footer slot 0's event track (see the module docstring)."""
    (count,) = struct.unpack(">H", block[0:2])
    pos = 8 + count * 2  # skip the count's padded slot, the runtime pointer word, and the offset array
    entries = []
    for _ in range(count):
        frame, num_codes = struct.unpack(">HH", block[pos : pos + 4])
        pos += 4
        codes = struct.unpack(f">{num_codes}H", block[pos : pos + num_codes * 2])
        pos += num_codes * 2
        entries.append(EventKey(frame=frame, codes=codes))
    return entries


def write_event_block(events: list[EventKey]) -> bytes:
    """Encode an event track as footer slot 0 stores it: count, pad, a zero
    runtime pointer word, the per-key offsets (from the block start), the
    keys, then zero padding to 4 bytes."""
    head = 8 + 2 * len(events)
    offsets, body = [], bytearray()
    for key in events:
        offsets.append(head + len(body))
        body += struct.pack(f">HH{len(key.codes)}H", key.frame, len(key.codes), *key.codes)
    block = struct.pack(">HHI", len(events), 0, 0) + struct.pack(f">{len(offsets)}H", *offsets) + bytes(body)
    return block + bytes(-len(block) % 4)


def _read_footer(data: bytes, footer_start: int) -> GaFooter:
    if is_fe10_animation(data):
        raw = data[footer_start:]
        if len(raw) < 12:
            raise AnimationError(f"Compact footer of {len(raw)} bytes (expected at least 12).")
        return GaFooter(compact_raw=raw)
    slots = struct.unpack(f">{FOOTER_SLOTS}I", data[footer_start : footer_start + 36])
    (pad_word,) = struct.unpack(">I", data[footer_start + 36 : footer_start + 40])
    used = sorted((addr, slot) for slot, addr in enumerate(slots) if addr)
    footer = GaFooter(pad_word=pad_word, order=[slot for _, slot in used])
    body_start = footer_start + FOOTER_LEAD_IN_SIZE
    if used and used[0][0] != body_start:
        raise AnimationError(f"First footer block at {used[0][0]:#x}, expected {body_start:#x}.")
    if not used:
        footer.trailing = data[body_start:]
    for i, (addr, slot) in enumerate(used):
        end = used[i + 1][0] if i + 1 < len(used) else len(data)
        footer.blocks[slot] = data[addr:end]
    return footer


def read_animation(stream: BinaryIO, size: int) -> GaAnimation:
    data = stream.read(size) if size else stream.read()
    header = GaHeader(words=struct.unpack(f">{HEADER_WORDS}I", data[:HEADER_SIZE]))

    group_addr = header.group_table_addr
    table_addr = header.curve_table_addr
    keyframe_addr = header.keyframe_data_addr
    group_count = header.animated_bone_count
    curve_bytes = keyframe_addr - table_addr
    if group_addr + group_count * GROUP_RECORD_SIZE != table_addr or curve_bytes % CURVE_RECORD_SIZE:
        raise AnimationError("Group/curve tables don't match the known .ga layout.")

    groups = [
        BoneGroup(*struct.unpack_from(">4I", data, group_addr + i * GROUP_RECORD_SIZE)) for i in range(group_count)
    ]

    bone_of_curve = [0] * (curve_bytes // CURVE_RECORD_SIZE)
    for group in groups:
        for index in range(group.first_curve, group.first_curve + group.curve_count):
            if index < len(bone_of_curve):
                bone_of_curve[index] = group.bone_index

    curves = []
    keyframes_end = keyframe_addr
    for i in range(curve_bytes // CURVE_RECORD_SIZE):
        channel, scale_raw, end_frame, count, offset_high, offset_low = struct.unpack_from(
            ">6H", data, table_addr + i * CURVE_RECORD_SIZE
        )
        offset_words = (offset_high << 16) | offset_low
        start = keyframe_addr + offset_words * SAMPLE_SIZE
        keyframes = [Keyframe(*struct.unpack_from(">Hh", data, start + j * SAMPLE_SIZE)) for j in range(count)]
        keyframes_end = max(keyframes_end, start + count * SAMPLE_SIZE)
        curves.append(
            AnimCurve(
                bone_index=bone_of_curve[i],
                channel=channel,
                scale_shift=scale_raw >> 8,
                end_frame=end_frame,
                keyframes=keyframes,
            )
        )

    footer = _read_footer(data, header.footer_addr) if header.footer_addr else None
    events = read_event_block(footer.blocks[0]) if footer and footer.blocks[0] else []
    body_end = header.footer_addr or len(data)
    return GaAnimation(header=header, groups=groups, curves=curves, events=events, footer=footer,
                       body_trailing=data[keyframes_end:body_end],
                       fe10_region_start=keyframes_end if footer and footer.compact_raw is not None else None)


def read_animation_bytes(data: bytes) -> GaAnimation:
    return read_animation(io.BytesIO(data), len(data))


def read_animation_path(path: Path | str) -> GaAnimation:
    path = Path(path)
    with open(path, "rb") as stream:
        return read_animation(stream, path.stat().st_size)


def write_animation(anim: GaAnimation) -> bytes:
    """Serialize ``anim`` in the on-disk layout. The layout-derived header
    words (0, 7, 8, 9, 11) are recomputed; every other header word is
    written as stored. Groups are written as stored, so their
    ``first_curve``/``curve_count`` must describe ``anim.curves``' order."""
    words = list(anim.header.words[:HEADER_WORDS]) + [0] * (HEADER_WORDS - len(anim.header.words))
    group_table = HEADER_SIZE
    curve_table = group_table + GROUP_RECORD_SIZE * len(anim.groups)
    keyframes_at = curve_table + CURVE_RECORD_SIZE * len(anim.curves)

    out = bytearray(HEADER_SIZE)
    for g in anim.groups:
        out += struct.pack(">4I", g.bone_index, g.channel_mask, g.first_curve, g.curve_count)
    keyframe_data = bytearray()
    for c in anim.curves:
        offset_words = len(keyframe_data) // SAMPLE_SIZE
        out += struct.pack(
            ">6H", c.channel, c.scale_shift << 8, c.end_frame, len(c.keyframes),
            offset_words >> 16, offset_words & 0xFFFF
        )
        for kf in c.keyframes:
            keyframe_data += struct.pack(">Hh", kf.frame, kf.value)
    out += keyframe_data
    out += anim.body_trailing

    footer_at = 0
    if anim.footer is not None and anim.footer.compact_raw is not None and anim.fe10_region_start is not None \
            and anim.fe10_region_start != len(out) - len(anim.body_trailing):
        # Radiant Dawn footer whose keyframes changed size: move its file offsets with it
        start = anim.fe10_region_start
        old = bytearray(start) + anim.body_trailing + anim.footer.compact_raw
        struct.pack_into(">I", old, 0, start + len(anim.body_trailing))
        old[8] = 1
        new_start = len(out) - len(anim.body_trailing)
        out = bytearray(fe10_rebase_footer(bytes(old), start, bytes(out[:new_start])))
        footer_at = struct.unpack_from(">I", out)[0]
    elif anim.footer is not None:
        footer_at = len(out)
        if anim.footer.compact_raw is not None:
            out += anim.footer.compact_raw
        else:
            slots = [0] * FOOTER_SLOTS
            body = bytearray()
            for slot in anim.footer.order:
                block = anim.footer.blocks[slot]
                if block is None:
                    raise AnimationError(f"Footer slot {slot} is in the order list but has no block.")
                slots[slot] = footer_at + FOOTER_LEAD_IN_SIZE + len(body)
                body += block
            out += struct.pack(f">{FOOTER_SLOTS}I", *slots) + struct.pack(">I", anim.footer.pad_word)
            out += body + anim.footer.trailing

    words[_W_FOOTER] = footer_at
    words[_W_GROUP_COUNT] = len(anim.groups)
    words[_W_GROUP_TABLE] = group_table
    words[_W_CURVE_TABLE] = curve_table
    words[_W_KEYFRAMES] = keyframes_at
    struct.pack_into(f">{HEADER_WORDS}I", out, 0, *words)
    return bytes(out)


#: Value-block slots holding absolute positions: translate X/Y/Z and the rotate pivot.
_POSITION_CHANNELS = frozenset((6, 7, 8, 12, 13, 14))


def _requantize(values: list[float], shift: int) -> tuple[int, list[int]]:
    """``values`` as int16 keys: the finest shift (at most ``shift``) that fits."""
    while shift > 0 and any(not -32768 <= round(v * (1 << shift)) <= 32767 for v in values):
        shift -= 1
    return shift, [max(-32768, min(32767, round(v * (1 << shift)))) for v in values]


def retarget_animation(
    anim: GaAnimation,
    old_names: list[str],
    old_values: list[list[float]],
    new_names: list[str],
    new_values: list[list[float]],
) -> tuple[GaAnimation, list[str]]:
    """Play ``anim`` (made for the skeleton ``old_names``) on another one,
    matching bones by name. Tracks of bones the new skeleton lacks are
    dropped (returned); new bones without tracks keep their bind pose.
    Keys are absolute, so translate and pivot keys are shifted by the
    difference between the two skeletons' rest values: the motion is kept
    and the new proportions too. Rotation and scale keys are copied as
    they are, which assumes matching bone orientations. ``*_values`` are
    each bone's 43-float value block."""
    index = {name: i for i, name in enumerate(new_names)}
    dropped: list[str] = []
    moved: list[tuple[int, BoneGroup, list[AnimCurve]]] = []
    for group in anim.groups:
        name = old_names[group.bone_index] if group.bone_index < len(old_names) else None
        target = index.get(name) if name is not None else None
        curves = anim.curves[group.first_curve : group.first_curve + group.curve_count]
        if target is None:
            dropped.append(name or f"#{group.bone_index}")
            continue
        adjusted = []
        for c in curves:
            if c.channel in _POSITION_CHANNELS:
                delta = new_values[target][c.channel] - old_values[group.bone_index][c.channel]
                values = [c.scaled_value(k) + delta for k in c.keyframes]
                shift, raws = _requantize(values, c.scale_shift & 0x3F)
                c = AnimCurve(target, c.channel, shift, c.end_frame,
                              [Keyframe(k.frame, raw) for k, raw in zip(c.keyframes, raws)])
            else:
                c = AnimCurve(target, c.channel, c.scale_shift, c.end_frame, c.keyframes)
            adjusted.append(c)
        moved.append((target, group, adjusted))
    moved.sort(key=lambda item: item[0])
    groups: list[BoneGroup] = []
    curves: list[AnimCurve] = []
    for target, group, adjusted in moved:
        groups.append(BoneGroup(target, group.channel_mask, len(curves), len(adjusted)))
        curves += adjusted
    return GaAnimation(anim.header, groups, curves, list(anim.events), anim.footer,
                       body_trailing=anim.body_trailing, fe10_region_start=anim.fe10_region_start), dropped
