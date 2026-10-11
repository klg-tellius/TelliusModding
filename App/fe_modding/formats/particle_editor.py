"""Lossless, bounded edits to the particle table in an effect .ga file.

The table contains file-absolute pointers and several controls whose meanings
are still being investigated.  Editing existing records in place keeps those
values, all other footer slots, and the original archive layout intact.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass

from . import animation


class ParticleEditError(ValueError):
    pass


@dataclass(frozen=True)
class Field:
    """One editable on-disk field, with a raw integer value."""

    offset: int
    format: str
    scale: int = 1


EMITTER_FIELDS = {
    "material": Field(0x0A, "h"),
    "draw_flags": Field(0x06, "H"),
    "raw_control": Field(0x0C, "H"),
    "mode1_scale": Field(0x0E, "h", 64),
    "line_width": Field(0x10, "h", 64),
    "mode2_scale": Field(0x12, "h", 64),
    "mode2_alpha": Field(0x14, "h", 64),
    "scale_s": Field(0x16, "h", 64),
    "scale_t": Field(0x18, "h", 64),
    "rotation": Field(0x1A, "h", 64),
}
STAGE_FIELDS = {
    "start": Field(2, "h"), "end": Field(4, "h"),
    "x": Field(6, "h", 64), "y": Field(8, "h", 64), "z": Field(10, "h", 64),
}
CURVE_FIELDS = {"channel": Field(0, "H"), "scale_shift": Field(2, "B")}
KEY_FIELDS = {"frame": Field(0, "H"), "value": Field(2, "h")}


def _limits(fmt: str) -> tuple[int, int]:
    bits = struct.calcsize(fmt) * 8
    return (-(1 << (bits - 1)), (1 << (bits - 1)) - 1) if fmt.islower() else (0, (1 << bits) - 1)


def _put(data: bytearray, address: int, field: Field, value: int) -> None:
    low, high = _limits(field.format)
    if not isinstance(value, int) or not low <= value <= high:
        raise ParticleEditError(f"Value must be an integer from {low} to {high}.")
    struct.pack_into(">" + field.format, data, address + field.offset, value)


def field_value(data: bytes, address: int, field: Field) -> int:
    return struct.unpack_from(">" + field.format, data, address + field.offset)[0]


def _layout(data: bytes) -> animation.ParticleTableLayout:
    layout = animation.read_particle_table_layout(data)
    if layout is None:
        raise ParticleEditError("This animation has no particle table.")
    return layout


def _emitter(data: bytes, emitter_index: int) -> animation.ParticleEmitterLayout:
    layout = _layout(data)
    try:
        return layout.emitters[emitter_index]
    except IndexError as exc:
        raise ParticleEditError("Emitter index is out of range.") from exc


def edit_emitter(data: bytes, emitter_index: int, **values: int) -> bytes:
    emitter = _emitter(data, emitter_index)
    out = bytearray(data)
    for name, value in values.items():
        if name not in EMITTER_FIELDS:
            raise ParticleEditError(f"Unknown emitter field: {name}")
        _put(out, emitter.record_offset, EMITTER_FIELDS[name], value)
    _layout(out)
    return bytes(out)


def edit_emitter_name(data: bytes, emitter_index: int, name_path: str) -> bytes:
    emitter = _emitter(data, emitter_index)
    if not name_path or "\0" in name_path:
        raise ParticleEditError("The emitter path must be nonempty and contain no NUL byte.")
    try:
        encoded = name_path.encode("shift_jis") + b"\0"
    except UnicodeEncodeError as exc:
        raise ParticleEditError("The emitter path cannot be encoded as Shift-JIS.") from exc
    if name_path == emitter.name_path:
        return data
    out = bytearray(data)
    address = len(out)
    out += encoded
    struct.pack_into(">I", out, emitter.record_offset, address)
    _layout(out)
    return bytes(out)


def edit_stage(data: bytes, emitter_index: int, stage_index: int, **values: int) -> bytes:
    emitter = _emitter(data, emitter_index)
    if not 0 <= stage_index < emitter.stage_count:
        raise ParticleEditError("Stage index is out of range.")
    current = animation.read_particle_stage(data, emitter, stage_index)
    start = values.get("start", current.start_frame)
    end = values.get("end", current.end_frame)
    if start > end:
        raise ParticleEditError("The start frame must not exceed the end frame.")
    out = bytearray(data)
    for name, value in values.items():
        if name not in STAGE_FIELDS:
            raise ParticleEditError(f"Unknown stage field: {name}")
        _put(out, emitter.stages_offset + stage_index * 12, STAGE_FIELDS[name], value)
    if end > struct.unpack_from(">I", out, 6 * 4)[0]:
        struct.pack_into(">I", out, 6 * 4, end)
    _layout(out)
    return bytes(out)


def edit_curve(data: bytes, emitter_index: int, curve_index: int, **values: int) -> bytes:
    emitter = _emitter(data, emitter_index)
    if not 0 <= curve_index < emitter.curve_count:
        raise ParticleEditError("Curve index is out of range.")
    out = bytearray(data)
    address = emitter.curves_offset + curve_index * 12
    for name, value in values.items():
        if name not in CURVE_FIELDS:
            raise ParticleEditError(f"Unknown curve field: {name}")
        if name == "scale_shift":
            if not 0 <= value <= 15:
                raise ParticleEditError("The scale shift must be from 0 to 15.")
            value = (out[address + 2] & 0xC0) | value
        if name == "channel" and not 0 <= value < len(animation.PARTICLE_CURVE_CHANNELS):
            raise ParticleEditError("Unknown particle channel.")
        _put(out, address, CURVE_FIELDS[name], value)
    _layout(out)
    return bytes(out)


def edit_key(data: bytes, emitter_index: int, curve_index: int, key_index: int,
             *, frame: int | None = None, value: int | None = None) -> bytes:
    emitter = _emitter(data, emitter_index)
    curve = animation.read_particle_curve(data, emitter, curve_index)
    if not 0 <= key_index < curve.key_count:
        raise ParticleEditError("Key index is out of range.")
    address = emitter.keys_offset + (curve.first_key + key_index) * 4
    out = bytearray(data)
    if frame is not None:
        _put(out, address, KEY_FIELDS["frame"], frame)
    if value is not None:
        _put(out, address, KEY_FIELDS["value"], value)
    frames = [struct.unpack_from(">H", out, emitter.keys_offset + (curve.first_key + i) * 4)[0]
              for i in range(curve.key_count)]
    if frames != sorted(frames) or len(frames) != len(set(frames)):
        raise ParticleEditError("Key frames must increase without duplicates.")
    struct.pack_into(">H", out, emitter.curves_offset + curve_index * 12 + 4,
                     frames[-1] if frames else 0)
    _layout(out)
    return bytes(out)


@dataclass
class _Curve:
    descriptor: bytearray
    keys: list[tuple[int, int]]


@dataclass
class _Stage:
    record: bytearray
    curve_range: bytearray
    curves: list[_Curve]


def _read_structure(data: bytes, emitter: animation.ParticleEmitterLayout) -> tuple[list[_Stage], list[_Curve]]:
    curves = []
    for index in range(emitter.curve_count):
        at = emitter.curves_offset + index * 12
        descriptor = bytearray(data[at:at + 12])
        curve = animation.read_particle_curve(data, emitter, index)
        keys_at = emitter.keys_offset + curve.first_key * 4
        keys = [struct.unpack_from(">Hh", data, keys_at + n * 4) for n in range(curve.key_count)]
        curves.append(_Curve(descriptor, keys))
    stages = []
    used = set()
    for index in range(emitter.stage_count):
        stage = animation.read_particle_stage(data, emitter, index)
        used.update(range(stage.first_curve, stage.first_curve + stage.curve_count))
        stages.append(_Stage(bytearray(data[emitter.stages_offset + index * 12:
                                           emitter.stages_offset + (index + 1) * 12]),
                             bytearray(data[emitter.stage_curves_offset + index * 8:
                                           emitter.stage_curves_offset + (index + 1) * 8]),
                             curves[stage.first_curve:stage.first_curve + stage.curve_count]))
    if len(used) != sum(len(stage.curves) for stage in stages):
        raise ParticleEditError("Shared particle curves cannot be edited structurally yet.")
    return stages, [curve for index, curve in enumerate(curves) if index not in used]


def _rewrite_structure(data: bytes, emitter_index: int, stages: list[_Stage],
                       unattached: list[_Curve]) -> bytes:
    """Append replacement tables and redirect the emitter's four pointers.

    Old table bytes remain as inert data in slot 8. This preserves unrelated
    slots and unknown bytes while allowing table sizes to change safely.
    """
    emitter = _emitter(data, emitter_index)
    if len(stages) > 65535:
        raise ParticleEditError("Too many stages.")
    out = bytearray(data)
    out += bytes(-len(out) % 4)
    stages_at = len(out)
    for local, stage in enumerate(stages):
        record = bytearray(stage.record)
        struct.pack_into(">H", record, 0, local)
        out += record
    ranges_at = len(out)
    curve_list = []
    for stage in stages:
        entry = bytearray(stage.curve_range)
        struct.pack_into(">HH", entry, 4, len(curve_list), len(stage.curves))
        curve_list.extend(stage.curves)
        out += entry
    curve_list.extend(unattached)
    curves_at = len(out)
    key_words = bytearray()
    for curve in curve_list:
        desc = bytearray(curve.descriptor)
        frames = [frame for frame, _ in curve.keys]
        if frames != sorted(set(frames)):
            raise ParticleEditError("Curve key frames must increase without duplicates.")
        if len(curve.keys) > 65535:
            raise ParticleEditError("Too many keys in a curve.")
        struct.pack_into(">HHI", desc, 4, frames[-1] if frames else 0,
                         len(curve.keys), len(key_words) // 4)
        out += desc
        for frame, value in curve.keys:
            key_words += struct.pack(">Hh", frame, value)
    keys_at = len(out)
    out += key_words
    struct.pack_into(">H4I", out, emitter.record_offset + 0x1E,
                     len(stages), stages_at, ranges_at, curves_at, keys_at)
    # Re-number the cumulative indices in all emitters, including those after
    # the changed emitter. Their stage tables stay at their original offsets.
    count = 0
    for index, other in enumerate(_layout(out).emitters):
        struct.pack_into(">H", out, other.record_offset + 8, count)
        for local in range(other.stage_count):
            struct.pack_into(">H", out, other.stage_curves_offset + local * 8, count + local)
        count += other.stage_count
    _layout(out)
    return bytes(out)


def _shift_tail_pointers(out: bytearray, table_start: int, count: int,
                         boundary: int, delta: int) -> None:
    """Move file-absolute references after an emitter-record insertion/removal."""
    footer = struct.unpack_from(">I", out)[0]
    for slot in range(animation.FOOTER_SLOTS):
        address = footer + slot * 4
        pointer = struct.unpack_from(">I", out, address)[0]
        if pointer >= boundary:
            struct.pack_into(">I", out, address, pointer + delta)
    for index in range(count):
        record = table_start + 8 + index * 0x34
        for offset in (0, 0x20, 0x24, 0x28, 0x2C):
            pointer = struct.unpack_from(">I", out, record + offset)[0]
            if pointer >= boundary:
                struct.pack_into(">I", out, record + offset, pointer + delta)


def _renumber_emitters(out: bytearray) -> None:
    total_stages = 0
    for index, emitter in enumerate(_layout(out).emitters):
        if total_stages + emitter.stage_count > 65535:
            raise ParticleEditError("Too many stages across emitters.")
        struct.pack_into(">H", out, emitter.record_offset + 4, index)
        struct.pack_into(">H", out, emitter.record_offset + 8, total_stages)
        for local in range(emitter.stage_count):
            struct.pack_into(">H", out, emitter.stages_offset + local * 12, local)
            struct.pack_into(">H", out, emitter.stage_curves_offset + local * 8,
                             total_stages + local)
        total_stages += emitter.stage_count


def duplicate_emitter(data: bytes, emitter_index: int) -> bytes:
    """Append a full emitter clone with independent stage and curve tables."""
    layout = _layout(data)
    if len(layout.emitters) >= 65535:
        raise ParticleEditError("Too many emitters.")
    if not 0 <= emitter_index < len(layout.emitters):
        raise ParticleEditError("Emitter index is out of range.")
    source = layout.emitters[emitter_index]
    insertion = layout.block_offset + 8 + len(layout.emitters) * 0x34
    clone_record = data[source.record_offset:source.record_offset + 0x34]
    out = bytearray(data[:insertion] + clone_record + data[insertion:])
    struct.pack_into(">H", out, layout.block_offset + 6, len(layout.emitters) + 1)
    _shift_tail_pointers(out, layout.block_offset, len(layout.emitters) + 1,
                         insertion, 0x34)
    clone = _layout(out).emitters[-1]
    stages, unattached = _read_structure(out, clone)
    return _rewrite_structure(bytes(out), len(layout.emitters), stages, unattached)


def add_emitter(data: bytes, name_path: str = "|root|") -> bytes:
    """Add an empty emitter, ready for a material, stages, and curves."""
    layout = _layout(data)
    if len(layout.emitters) >= 65535:
        raise ParticleEditError("Too many emitters.")
    if not name_path or "\0" in name_path:
        raise ParticleEditError("The emitter path must be nonempty and contain no NUL byte.")
    try:
        encoded_name = name_path.encode("shift_jis") + b"\0"
    except UnicodeEncodeError as exc:
        raise ParticleEditError("The emitter path cannot be encoded as Shift-JIS.") from exc
    insertion = layout.block_offset + 8 + len(layout.emitters) * 0x34
    out = bytearray(data[:insertion] + bytes(0x34) + data[insertion:])
    new_count = len(layout.emitters) + 1
    struct.pack_into(">H", out, layout.block_offset + 6, new_count)
    _shift_tail_pointers(out, layout.block_offset, new_count, insertion, 0x34)
    record = insertion
    struct.pack_into(">H", out, record + 6, 4)  # textured draw path
    struct.pack_into(">h", out, record + 0x0A, -1)  # material is chosen in the UI
    struct.pack_into(">2h", out, record + 0x16, 64, 64)
    out += bytes(-len(out) % 4)
    empty_at = len(out)
    struct.pack_into(">4I", out, record + 0x20, *([empty_at] * 4))
    struct.pack_into(">I", out, record, empty_at)
    out += encoded_name
    _renumber_emitters(out)
    _layout(out)
    return bytes(out)


def remove_emitter(data: bytes, emitter_index: int) -> bytes:
    layout = _layout(data)
    if not 0 <= emitter_index < len(layout.emitters):
        raise ParticleEditError("Emitter index is out of range.")
    removal = layout.emitters[emitter_index].record_offset
    end = removal + 0x34
    out = bytearray(data[:removal] + data[end:])
    new_count = len(layout.emitters) - 1
    struct.pack_into(">H", out, layout.block_offset + 6, new_count)
    _shift_tail_pointers(out, layout.block_offset, new_count, end, -0x34)
    _renumber_emitters(out)
    _layout(out)
    return bytes(out)


def duplicate_stage(data: bytes, emitter_index: int, stage_index: int) -> bytes:
    emitter = _emitter(data, emitter_index)
    stages, unattached = _read_structure(data, emitter)
    if not 0 <= stage_index < len(stages):
        raise ParticleEditError("Stage index is out of range.")
    stage = stages[stage_index]
    clone = _Stage(bytearray(stage.record), bytearray(stage.curve_range),
                   [_Curve(bytearray(curve.descriptor), list(curve.keys)) for curve in stage.curves])
    stages.insert(stage_index + 1, clone)
    return _rewrite_structure(data, emitter_index, stages, unattached)


def add_stage(data: bytes, emitter_index: int) -> bytes:
    emitter = _emitter(data, emitter_index)
    stages, unattached = _read_structure(data, emitter)
    stages.append(_Stage(bytearray(12), bytearray(8), []))
    return _rewrite_structure(data, emitter_index, stages, unattached)


def move_stage(data: bytes, emitter_index: int, stage_index: int, direction: int) -> bytes:
    emitter = _emitter(data, emitter_index)
    stages, unattached = _read_structure(data, emitter)
    target = stage_index + direction
    if not 0 <= stage_index < len(stages) or not 0 <= target < len(stages):
        raise ParticleEditError("Stage cannot move farther in that direction.")
    stages[stage_index], stages[target] = stages[target], stages[stage_index]
    return _rewrite_structure(data, emitter_index, stages, unattached)


def remove_stage(data: bytes, emitter_index: int, stage_index: int) -> bytes:
    emitter = _emitter(data, emitter_index)
    stages, unattached = _read_structure(data, emitter)
    if not 0 <= stage_index < len(stages):
        raise ParticleEditError("Stage index is out of range.")
    del stages[stage_index]
    return _rewrite_structure(data, emitter_index, stages, unattached)


def add_curve(data: bytes, emitter_index: int, stage_index: int, channel: int) -> bytes:
    if not 0 <= channel < len(animation.PARTICLE_CURVE_CHANNELS):
        raise ParticleEditError("Unknown particle channel.")
    emitter = _emitter(data, emitter_index)
    stages, unattached = _read_structure(data, emitter)
    if not 0 <= stage_index < len(stages):
        raise ParticleEditError("Stage index is out of range.")
    descriptor = bytearray(12)
    struct.pack_into(">H", descriptor, 0, channel)
    stages[stage_index].curves.append(_Curve(descriptor, [(0, 0)]))
    return _rewrite_structure(data, emitter_index, stages, unattached)


def remove_curve(data: bytes, emitter_index: int, stage_index: int, curve_index: int) -> bytes:
    emitter = _emitter(data, emitter_index)
    stages, unattached = _read_structure(data, emitter)
    if not 0 <= stage_index < len(stages):
        raise ParticleEditError("Stage index is out of range.")
    stage = animation.read_particle_stage(data, emitter, stage_index)
    local = curve_index - stage.first_curve
    if not 0 <= local < len(stages[stage_index].curves):
        raise ParticleEditError("Curve does not belong to this stage.")
    del stages[stage_index].curves[local]
    return _rewrite_structure(data, emitter_index, stages, unattached)


def add_key(data: bytes, emitter_index: int, curve_index: int, frame: int, value: int) -> bytes:
    emitter = _emitter(data, emitter_index)
    stages, unattached = _read_structure(data, emitter)
    found = None
    for index, stage in enumerate(stages):
        layout = animation.read_particle_stage(data, emitter, index)
        if layout.first_curve <= curve_index < layout.first_curve + layout.curve_count:
            found = stage.curves[curve_index - layout.first_curve]
            break
    if found is None:
        raise ParticleEditError("Curve is not attached to a stage.")
    if not 0 <= frame <= 65535 or not -32768 <= value <= 32767:
        raise ParticleEditError("Key value is out of range.")
    if any(existing_frame == frame for existing_frame, _ in found.keys):
        raise ParticleEditError("A key already exists at that frame.")
    found.keys.append((frame, value))
    found.keys.sort()
    return _rewrite_structure(data, emitter_index, stages, unattached)


def remove_key(data: bytes, emitter_index: int, curve_index: int, key_index: int) -> bytes:
    emitter = _emitter(data, emitter_index)
    stages, unattached = _read_structure(data, emitter)
    found = None
    for index, stage in enumerate(stages):
        layout = animation.read_particle_stage(data, emitter, index)
        if layout.first_curve <= curve_index < layout.first_curve + layout.curve_count:
            found = stage.curves[curve_index - layout.first_curve]
            break
    if found is None or not 0 <= key_index < len(found.keys):
        raise ParticleEditError("Key index is out of range.")
    del found.keys[key_index]
    return _rewrite_structure(data, emitter_index, stages, unattached)


def _write_rebased(data: bytes, anim: animation.GaAnimation) -> bytes:
    """Write a changed footer while fixing file-absolute particle pointers."""
    old_layout = animation.read_particle_table_layout(data)
    out = bytearray(animation.write_animation(anim))
    if old_layout is not None:
        footer = struct.unpack_from(">I", out)[0]
        new_block = struct.unpack_from(">I", out, footer + 8 * 4)[0]
        delta = new_block - old_layout.block_offset
        for old_emitter in old_layout.emitters:
            record = old_emitter.record_offset + delta
            for offset in (0, 0x20, 0x24, 0x28, 0x2C):
                pointer = struct.unpack_from(">I", out, record + offset)[0]
                struct.pack_into(">I", out, record + offset, pointer + delta)
        _layout(out)
    return bytes(out)


def _set_footer_block(anim: animation.GaAnimation, slot: int, block: bytes) -> None:
    if anim.footer is None:
        anim.footer = animation.GaFooter()
    anim.footer.blocks[slot] = block
    if slot not in anim.footer.order:
        position = next((index for index, old_slot in enumerate(anim.footer.order) if old_slot > slot),
                        len(anim.footer.order))
        anim.footer.order.insert(position, slot)


def replace_events(data: bytes, events: list[animation.EventKey]) -> bytes:
    """Rewrite event slot 0 and rebase slot-8 file pointers if it moves."""
    frames = [event.frame for event in events]
    if frames != sorted(frames):
        raise ParticleEditError("Event frames must be in ascending order.")
    for event in events:
        if not 0 <= event.frame <= 65535 or any(not 0 <= code <= 65535 for code in event.codes):
            raise ParticleEditError("Event frames and codes must fit in 16 bits.")
    anim = animation.read_animation_bytes(data)
    if anim.events == events:
        return data
    anim.events = events
    _set_footer_block(anim, 0, animation.write_event_block(events))
    if frames:
        words = list(anim.header.words)
        words[6] = max(words[6], frames[-1])
        anim.header = animation.GaHeader(tuple(words))
    return _write_rebased(data, anim)


def replace_material_tracks(data: bytes, slot: int, tracks: dict[int, animation.MaterialTrack],
                            material_count: int) -> bytes:
    """Set alpha, colour, U, or V tracks (footer slots 1 through 4)."""
    if slot not in (1, 2, 3, 4):
        raise ParticleEditError("Material tracks belong to footer slots 1 through 4.")
    if not 0 <= material_count <= 65535 or any(not 0 <= index < material_count for index in tracks):
        raise ParticleEditError("Material index is out of range.")
    anim = animation.read_animation_bytes(data)
    old_block = anim.footer.blocks[slot] if anim.footer else None
    old_tracks = animation.read_material_tracks(old_block) if old_block else {}
    if old_tracks == tracks and old_block is not None and struct.unpack_from(">H", old_block)[0] == material_count:
        return data
    body = bytearray()
    offsets = []
    head_size = 8 + material_count * 2
    for index in range(material_count):
        track = tracks.get(index)
        if track is None:
            offsets.append(0xFFFF)
            continue
        if track.mode not in (0, 1) or len(track.keys) > 65535:
            raise ParticleEditError("Track mode or key count is invalid.")
        frames = [frame for frame, _ in track.keys]
        if frames != sorted(set(frames)):
            raise ParticleEditError("Material key frames must increase without duplicates.")
        if head_size + len(body) >= 0xFFFF:
            raise ParticleEditError("Material track table is too large.")
        offsets.append(head_size + len(body))
        body += struct.pack(">HH", len(track.keys), track.mode)
        for frame, value in track.keys:
            if not 0 <= frame <= 65535 or not -32768 <= value <= 32767:
                raise ParticleEditError("Material key is out of range.")
            if slot == 1 and not 0 <= value <= 255:
                raise ParticleEditError("Alpha values must be from 0 to 255.")
            body += struct.pack(">Hh", frame, value)
    pad_and_runtime = old_block[2:8] if old_block else bytes(6)
    block = struct.pack(">H", material_count) + pad_and_runtime + struct.pack(f">{material_count}H", *offsets) + body
    block += bytes(-len(block) % 4)
    _set_footer_block(anim, slot, block)
    return _write_rebased(data, anim)
