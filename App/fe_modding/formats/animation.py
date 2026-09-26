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
spawn camera/light effects; the rest are read elsewhere (``1`` sits on
the hit frame of every attack, codes above 1000 look like sound ids). The
other slots appear on effect (``yme/``) and scenery (``zbg/``, ``zmap/``)
animations and are kept as raw bytes. A footer whose nine slots are all
zero is a valid empty footer.
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


@dataclass
class GaAnimation:
    header: GaHeader
    groups: list[BoneGroup]
    curves: list[AnimCurve] = field(repr=False)
    events: list[EventKey] = field(default_factory=list)
    footer: Optional[GaFooter] = None

    def curves_for_bone(self, bone_index: int) -> list[AnimCurve]:
        return [c for c in self.curves if c.bone_index == bone_index]

    @property
    def length_in_frames(self) -> int:
        return max((c.end_frame for c in self.curves), default=0)


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
    for i in range(curve_bytes // CURVE_RECORD_SIZE):
        channel, scale_raw, end_frame, count, _unused, offset_words = struct.unpack_from(
            ">6H", data, table_addr + i * CURVE_RECORD_SIZE
        )
        start = keyframe_addr + offset_words * SAMPLE_SIZE
        keyframes = [Keyframe(*struct.unpack_from(">Hh", data, start + j * SAMPLE_SIZE)) for j in range(count)]
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
    return GaAnimation(header=header, groups=groups, curves=curves, events=events, footer=footer)


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
        out += struct.pack(
            ">6H", c.channel, c.scale_shift << 8, c.end_frame, len(c.keyframes), 0, len(keyframe_data) // SAMPLE_SIZE
        )
        for kf in c.keyframes:
            keyframe_data += struct.pack(">Hh", kf.frame, kf.value)
    out += keyframe_data

    footer_at = 0
    if anim.footer is not None:
        footer_at = len(out)
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
    return GaAnimation(anim.header, groups, curves, list(anim.events), anim.footer), dropped
