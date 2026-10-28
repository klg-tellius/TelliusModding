"""Reader for Radiant Dawn's decompressed ``FE10Anim.cms``.

The model table ends in a weapon-by-motion matrix.  A non-zero matrix byte is
the numbered ``.ga`` variant for that model, weapon archive and motion stem.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass, field, replace

from .common import HEADER_SIZE
from .fe8data import pointer_list, symbol_offsets

HEADER_SIZE_BYTES = 20
MODEL_SIZE = 456
MOTION_SIZE = 12
WEAPON_SIZE = 8
WEAPON_SLOTS = 9
MOTION_SLOTS = 48
MODEL_METADATA_SIZE = 0x18


@dataclass(frozen=True)
class AnimRecord:
    address: int
    raw: bytes
    strings: tuple[tuple[int, str], ...]
    linked_model: int | None = None

    @property
    def words(self) -> tuple[int, ...]:
        return struct.unpack(f">{len(self.raw) // 4}I", self.raw)


@dataclass(frozen=True)
class AnimTable:
    name: str
    record_size: int
    records: tuple[AnimRecord, ...]


@dataclass(frozen=True)
class AnimHeader:
    aid_name: str
    description: str
    ordinal: int
    flags: int
    texture_name: str
    model_index: int


@dataclass(frozen=True)
class AnimModel:
    folder: str
    movement_sound: str
    floor_movement_sound: str
    extra_movement_sound: str
    parameters: tuple[int, ...]
    variants: tuple[tuple[int, ...], ...]


@dataclass(frozen=True)
class AnimMotion:
    description: str
    file_stem: str
    flags: int


@dataclass(frozen=True)
class AnimWeapon:
    description: str
    archive_suffix: str


@dataclass(frozen=True)
class Fe10Anim:
    tables: tuple[AnimTable, ...]
    string_pool: bytes
    headers: tuple[AnimHeader, ...]
    models: tuple[AnimModel, ...]
    motions: tuple[AnimMotion, ...]
    weapons: tuple[AnimWeapon, ...]
    _source: bytes = field(default=b"", repr=False, compare=False)

    def table(self, name: str) -> AnimTable:
        return next(table for table in self.tables if table.name == name)

    def animation_filename(self, header_index: int, weapon_index: int,
                           motion_index: int) -> str | None:
        """Return the selected packed ``.ga`` member name, or ``None`` if absent."""
        header = self.headers[header_index]
        model = self.models[header.model_index]
        variant = model.variants[weapon_index][motion_index]
        if not variant:
            return None
        return f"{self.motions[motion_index].file_stem}_{variant}.ga"


def _cstring(data: bytes, pointer: int) -> str:
    start = HEADER_SIZE + pointer
    if not HEADER_SIZE <= start < len(data):
        raise ValueError(f"String pointer {pointer:#x} is outside FE10Anim.cms.")
    end = data.find(b"\0", start)
    if end < 0:
        raise ValueError(f"String at {pointer:#x} is not terminated.")
    return data[start:end].decode("shift_jis", errors="replace")


def _counted_layout(data: bytes, offset: int, record_size: int, limit: int, name: str) -> tuple[int, int, int]:
    count, reserved = struct.unpack_from(">HH", data, HEADER_SIZE + offset)
    if reserved:
        raise ValueError(f"{name} has non-zero count padding {reserved:#x}.")
    start, end = offset + 4, offset + 4 + count * record_size
    if end > limit:
        raise ValueError(f"{name} rows extend into the next section.")
    return count, start, end


def read_fe10_anim(data: bytes) -> Fe10Anim:
    size, data_size, _pointer_count, _symbol_count = struct.unpack_from(">4I", data)
    data_end = HEADER_SIZE + data_size
    if size != len(data) or data_end > len(data):
        raise ValueError("FE10Anim.cms has an invalid container header.")
    symbols = symbol_offsets(data)
    required = {"FE10AnimHeader", "FE10AnimData", "FE10AnimMotion", "FE10AnimWeapon"}
    missing = required - set(symbols)
    if missing:
        raise ValueError("FE10Anim.cms is missing symbols: " + ", ".join(sorted(missing)))
    header_at, model_at = symbols["FE10AnimHeader"], symbols["FE10AnimData"]
    motion_at, weapon_at = symbols["FE10AnimMotion"], symbols["FE10AnimWeapon"]
    if not header_at < model_at < motion_at < weapon_at < data_size:
        raise ValueError("FE10Anim.cms sections are not in their expected order.")
    header_count, header_start, header_end = _counted_layout(
        data, header_at, HEADER_SIZE_BYTES, model_at, "FE10AnimHeader")
    if header_end != model_at:
        raise ValueError("FE10AnimHeader has unexplained bytes before FE10AnimData.")
    model_bytes = motion_at - model_at
    if model_bytes % MODEL_SIZE:
        raise ValueError("FE10AnimData is not a whole number of 456-byte records.")
    model_count = model_bytes // MODEL_SIZE
    motion_count, motion_start, motion_end = _counted_layout(
        data, motion_at, MOTION_SIZE, weapon_at, "FE10AnimMotion")
    if motion_end != weapon_at:
        raise ValueError("FE10AnimMotion has unexplained bytes before FE10AnimWeapon.")
    weapon_count, weapon_start, weapon_end = _counted_layout(
        data, weapon_at, WEAPON_SIZE, data_size, "FE10AnimWeapon")
    listed = set(pointer_list(data)[1])

    def records(name: str, start: int, count: int, record_size: int,
                string_fields: tuple[int, ...], link_field: int | None = None) -> AnimTable:
        result = []
        for index in range(count):
            row = start + index * record_size
            raw = data[HEADER_SIZE + row:HEADER_SIZE + row + record_size]
            strings = []
            for field in string_fields:
                if row + field in listed:
                    pointer = struct.unpack_from(">I", raw, field)[0]
                    strings.append((field, _cstring(data, pointer) if pointer else ""))
            linked = None
            if link_field is not None:
                pointer = struct.unpack_from(">I", raw, link_field)[0]
                delta = pointer - model_at
                if row + link_field not in listed or delta < 0 or delta % MODEL_SIZE or delta // MODEL_SIZE >= model_count:
                    raise ValueError(f"{name} row {index} has an invalid FE10AnimData pointer {pointer:#x}.")
                linked = delta // MODEL_SIZE
            result.append(AnimRecord(HEADER_SIZE + row, raw, tuple(strings), linked))
        return AnimTable(name, record_size, tuple(result))

    tables = (
        records("FE10AnimHeader", header_start, header_count, HEADER_SIZE_BYTES, (0, 4, 12), 16),
        records("FE10AnimData", model_at, model_count, MODEL_SIZE, (0, 4, 8, 12)),
        records("FE10AnimMotion", motion_start, motion_count, MOTION_SIZE, (0, 4)),
        records("FE10AnimWeapon", weapon_start, weapon_count, WEAPON_SIZE, (0, 4)),
    )
    header_records, model_records, motion_records, weapon_records = (table.records for table in tables)
    headers = tuple(
        AnimHeader(
            aid_name=dict(record.strings).get(0, ""),
            description=dict(record.strings).get(4, ""),
            ordinal=struct.unpack_from(">H", record.raw, 8)[0],
            flags=struct.unpack_from(">H", record.raw, 10)[0],
            texture_name=dict(record.strings).get(12, ""),
            model_index=record.linked_model if record.linked_model is not None else -1,
        )
        for record in header_records
    )
    models = tuple(
        AnimModel(
            folder=dict(record.strings).get(0, ""),
            movement_sound=dict(record.strings).get(4, ""),
            floor_movement_sound=dict(record.strings).get(8, ""),
            extra_movement_sound=dict(record.strings).get(12, ""),
            parameters=tuple(record.raw[16:MODEL_METADATA_SIZE]),
            variants=tuple(
                tuple(record.raw[MODEL_METADATA_SIZE + weapon * MOTION_SLOTS:
                                 MODEL_METADATA_SIZE + (weapon + 1) * MOTION_SLOTS])
                for weapon in range(WEAPON_SLOTS)
            ),
        )
        for record in model_records
    )
    motions = tuple(
        AnimMotion(dict(record.strings).get(0, ""), dict(record.strings).get(4, ""), record.words[2])
        for record in motion_records
    )
    weapons = tuple(
        AnimWeapon(dict(record.strings).get(0, ""), dict(record.strings).get(4, ""))
        for record in weapon_records
    )
    return Fe10Anim(tables, data[HEADER_SIZE + weapon_end:data_end], headers, models, motions, weapons, data)


def _replace_table(document: Fe10Anim, name: str, records: tuple[AnimRecord, ...]) -> Fe10Anim:
    tables = tuple(replace(table, records=records) if table.name == name else table
                   for table in document.tables)
    return replace(document, tables=tables)


def build_fe10_anim(document: Fe10Anim) -> bytes:
    """Rebuild ``FE10Anim.cms`` with valid pointers, exports and strings.

    Raw record bytes carry every still-opaque metadata byte. An unchanged
    parsed document returns byte-for-byte source data; a changed document
    rebuilds only the four known tables and their shared string pool.
    """
    expected = (
        ("FE10AnimHeader", HEADER_SIZE_BYTES), ("FE10AnimData", MODEL_SIZE),
        ("FE10AnimMotion", MOTION_SIZE), ("FE10AnimWeapon", WEAPON_SIZE),
    )
    if tuple((table.name, table.record_size) for table in document.tables) != expected:
        raise ValueError("FE10Anim.cms needs its four tables in engine order.")
    for table in document.tables:
        if any(len(record.raw) != table.record_size for record in table.records):
            raise ValueError(f"{table.name} contains a row of the wrong size.")
    if document._source:
        original = read_fe10_anim(document._source)
        if original.tables == document.tables:
            return document._source

    header_table, model_table, motion_table, weapon_table = document.tables
    if len(motion_table.records) > MOTION_SLOTS or len(weapon_table.records) > WEAPON_SLOTS:
        raise ValueError("Animation motion/weapon tables exceed the 48 by 9 model matrix.")
    if any(record.linked_model is None or not 0 <= record.linked_model < len(model_table.records)
           for record in header_table.records):
        raise ValueError("Every animation header must link to a model row.")

    header_at = 0
    model_at = 4 + len(header_table.records) * HEADER_SIZE_BYTES
    motion_at = model_at + len(model_table.records) * MODEL_SIZE
    weapon_at = motion_at + 4 + len(motion_table.records) * MOTION_SIZE
    pool_at = weapon_at + 4 + len(weapon_table.records) * WEAPON_SIZE
    strings = bytearray()
    string_offsets: dict[str, int] = {}

    def pointer(value: str) -> int:
        if not value:
            return 0
        if value not in string_offsets:
            string_offsets[value] = pool_at + len(strings)
            strings.extend(value.encode("shift_jis") + b"\0")
        return string_offsets[value]

    pointers: list[int] = []

    def rows(table: AnimTable, start: int, string_fields: tuple[int, ...],
             *, counted: bool, links: bool = False) -> bytearray:
        out = bytearray(struct.pack(">HH", len(table.records), 0) if counted else b"")
        prefix = 4 if counted else 0
        for index, record in enumerate(table.records):
            raw = bytearray(record.raw)
            string_values = dict(record.strings)
            for field in string_fields:
                value = string_values.get(field, "")
                target = pointer(value)
                struct.pack_into(">I", raw, field, target)
                if target:
                    pointers.append(start + prefix + index * table.record_size + field)
            if links:
                target = model_at + int(record.linked_model) * MODEL_SIZE
                struct.pack_into(">I", raw, 16, target)
                pointers.append(start + prefix + index * table.record_size + 16)
            out += raw
        return out

    data_section = bytearray()
    data_section += rows(header_table, header_at, (0, 4, 12), counted=True, links=True)
    data_section += rows(model_table, model_at, (0, 4, 8, 12), counted=False)
    data_section += rows(motion_table, motion_at, (0, 4), counted=True)
    data_section += rows(weapon_table, weapon_at, (0, 4), counted=True)
    data_section += strings
    data_section += bytes(-len(data_section) % 4)

    symbol_values = {
        "FE10AnimHeader": header_at, "FE10AnimData": model_at,
        "FE10AnimMotion": motion_at, "FE10AnimWeapon": weapon_at,
    }
    symbol_order = list(symbol_values)
    if document._source:
        from . import fe8data
        candidate = [name for _position, _offset, name in fe8data._symbol_entries(document._source)]
        if set(candidate) == set(symbol_values):
            symbol_order = candidate
    names = bytearray()
    exports = bytearray()
    for name in symbol_order:
        exports += struct.pack(">2I", symbol_values[name], len(names))
        names += name.encode("ascii") + b"\0"
    relocations = struct.pack(f">{len(pointers)}I", *sorted(pointers)) if pointers else b""
    header_tail = document._source[16:32] if document._source else bytes(16)
    size = 0x20 + len(data_section) + len(relocations) + len(exports) + len(names)
    built = (struct.pack(">4I", size, len(data_section), len(pointers), len(symbol_order))
             + header_tail + data_section + relocations + exports + names)
    read_fe10_anim(built)
    return built


def update_anim_header(data: bytes, index: int, **changes) -> bytes:
    """Edit known header fields, addressing model links by row index."""
    document = read_fe10_anim(data)
    table = document.table("FE10AnimHeader")
    if not 0 <= index < len(table.records):
        raise IndexError("Animation header index is out of range.")
    allowed = {"aid_name", "description", "ordinal", "flags", "texture_name", "model_index"}
    unknown = set(changes) - allowed
    if unknown:
        raise ValueError("Unknown animation header fields: " + ", ".join(sorted(unknown)))
    record = table.records[index]
    strings = dict(record.strings)
    for key, field_offset in (("aid_name", 0), ("description", 4), ("texture_name", 12)):
        if key in changes:
            strings[field_offset] = str(changes[key])
    raw = bytearray(record.raw)
    if "ordinal" in changes:
        struct.pack_into(">H", raw, 8, int(changes["ordinal"]))
    if "flags" in changes:
        struct.pack_into(">H", raw, 10, int(changes["flags"]))
    linked = int(changes.get("model_index", record.linked_model))
    records = list(table.records)
    records[index] = replace(record, raw=bytes(raw), strings=tuple(sorted(strings.items())), linked_model=linked)
    return build_fe10_anim(_replace_table(document, table.name, tuple(records)))


def clone_anim_model(data: bytes, index: int, folder: str) -> tuple[bytes, int]:
    """Append a model row cloned from ``index`` and give it a new folder."""
    document = read_fe10_anim(data)
    table = document.table("FE10AnimData")
    if not 0 <= index < len(table.records):
        raise IndexError("Animation model index is out of range.")
    strings = dict(table.records[index].strings)
    strings[0] = folder
    clone = replace(table.records[index], address=0, strings=tuple(sorted(strings.items())))
    records = table.records + (clone,)
    return build_fe10_anim(_replace_table(document, table.name, records)), len(table.records)


def clone_anim_header(data: bytes, index: int, aid_name: str,
                      model_index: int | None = None) -> tuple[bytes, int]:
    """Append a header clone, optionally pointing it at a different model row."""
    document = read_fe10_anim(data)
    table = document.table("FE10AnimHeader")
    if not 0 <= index < len(table.records):
        raise IndexError("Animation header index is out of range.")
    if aid_name in {header.aid_name for header in document.headers}:
        raise ValueError(f"{aid_name} already exists.")
    source = table.records[index]
    strings = dict(source.strings)
    strings[0] = aid_name
    linked = source.linked_model if model_index is None else model_index
    clone = replace(source, address=0, strings=tuple(sorted(strings.items())), linked_model=linked)
    records = table.records + (clone,)
    return build_fe10_anim(_replace_table(document, table.name, records)), len(table.records)


def remove_anim_header(data: bytes, index: int) -> bytes:
    document = read_fe10_anim(data)
    table = document.table("FE10AnimHeader")
    if not 0 <= index < len(table.records):
        raise IndexError("Animation header index is out of range.")
    records = table.records[:index] + table.records[index + 1:]
    return build_fe10_anim(_replace_table(document, table.name, records))


def remove_anim_model(data: bytes, index: int) -> bytes:
    """Remove an unreferenced model row and remap all later header links."""
    document = read_fe10_anim(data)
    models = document.table("FE10AnimData")
    if not 0 <= index < len(models.records):
        raise IndexError("Animation model index is out of range.")
    users = [header.aid_name for header in document.headers if header.model_index == index]
    if users:
        raise ValueError("Animation model is still used by: " + ", ".join(users))
    document = _replace_table(document, models.name, models.records[:index] + models.records[index + 1:])
    headers = document.table("FE10AnimHeader")
    remapped = tuple(replace(record, linked_model=record.linked_model - 1)
                     if record.linked_model is not None and record.linked_model > index else record
                     for record in headers.records)
    return build_fe10_anim(_replace_table(document, headers.name, remapped))


def set_animation_variant(data: bytes, model_index: int, weapon_index: int,
                          motion_index: int, variant: int) -> bytes:
    """Patch one fixed-width model dispatch byte without moving container data.

    ``0`` disables the combination. The byte field safely represents 0 through
    255; retail numbered variants currently use 1 through 6.
    """
    document = read_fe10_anim(data)
    if not 0 <= model_index < len(document.models):
        raise IndexError("Animation model index is out of range.")
    if not 0 <= weapon_index < WEAPON_SLOTS:
        raise IndexError("Animation weapon index is out of range.")
    if not 0 <= motion_index < MOTION_SLOTS:
        raise IndexError("Animation motion index is out of range.")
    if not 0 <= variant <= 0xFF:
        raise ValueError("Animation variant must fit in one byte.")
    model_at = symbol_offsets(data)["FE10AnimData"]
    offset = (HEADER_SIZE + model_at + model_index * MODEL_SIZE + MODEL_METADATA_SIZE
              + weapon_index * MOTION_SLOTS + motion_index)
    out = bytearray(data)
    out[offset] = variant
    return bytes(out)
