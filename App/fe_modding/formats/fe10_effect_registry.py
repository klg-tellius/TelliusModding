"""Read Radiant Dawn's ``FE10Effect.cms`` registry.

The decompressed file is a standard relocatable Tellius data container with
two symbols. ``EffectData`` is a count followed by 24-byte records. The word
at ``+0x0c`` is four independent parameters and the word at ``+0x10`` is two
signed child-record indices (``-1`` means no child). ``EIDTable`` maps a small
set of numeric effect IDs to registered EID names.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass, field, replace
from typing import Optional

from .common import HEADER_SIZE
from .fe8data import symbol_offsets

RECORD_SIZE = 0x18
EID_RECORD_SIZE = 0x08


@dataclass(frozen=True)
class Fe10EffectRecord:
    address: int
    description: str
    eid_name: str
    flags: int
    parameter_bytes: tuple[int, int, int, int]
    child_effect_indices: tuple[Optional[int], Optional[int]]
    sound_group: Optional[str]

    @property
    def parameters(self) -> int:
        """The four parameters packed as their original big-endian word."""
        return int.from_bytes(bytes(self.parameter_bytes), "big")

    @property
    def link(self) -> int:
        """The two child indices packed as their original unsigned word."""
        first, second = self.child_effect_indices
        return ((0xFFFF if first is None else first) << 16) | (0xFFFF if second is None else second)


@dataclass(frozen=True)
class Fe10EffectRegistry:
    records: tuple[Fe10EffectRecord, ...]
    eid_table: tuple[tuple[int, str], ...]
    _source: bytes = field(default=b"", repr=False, compare=False)

    def child_eids(self, record: Fe10EffectRecord) -> tuple[str, ...]:
        return tuple(self.records[index].eid_name for index in record.child_effect_indices
                     if index is not None)

    def numeric_ids(self, eid_name: str) -> tuple[int, ...]:
        return tuple(effect_id for effect_id, eid in self.eid_table if eid == eid_name)


def _cstring(data: bytes, pointer: int) -> str:
    if pointer == 0:
        return ""
    start = HEADER_SIZE + pointer
    if not HEADER_SIZE <= start < len(data):
        raise ValueError(f"String pointer {pointer:#x} is outside FE10Effect.cms.")
    end = data.find(b"\0", start)
    if end < 0:
        raise ValueError(f"String at {pointer:#x} is not terminated.")
    return data[start:end].decode("shift_jis", errors="replace")


def read_fe10_effect_registry(data: bytes) -> Fe10EffectRegistry:
    symbols = symbol_offsets(data)
    try:
        records_at = HEADER_SIZE + symbols["EffectData"]
        eid_at = HEADER_SIZE + symbols["EIDTable"]
    except KeyError as exc:
        raise ValueError(f"FE10Effect.cms is missing {exc.args[0]}.") from exc

    (count,) = struct.unpack_from(">I", data, records_at)
    if records_at + 4 + count * RECORD_SIZE > len(data):
        raise ValueError("FE10Effect.cms effect table is truncated.")
    records = []
    for index in range(count):
        address = records_at + 4 + index * RECORD_SIZE
        description, eid, flags = struct.unpack_from(">3I", data, address)
        parameter_bytes = struct.unpack_from(">4B", data, address + 0x0C)
        children = struct.unpack_from(">2h", data, address + 0x10)
        (sound,) = struct.unpack_from(">I", data, address + 0x14)
        records.append(Fe10EffectRecord(
            address=address,
            description=_cstring(data, description),
            eid_name=_cstring(data, eid),
            flags=flags,
            parameter_bytes=parameter_bytes,
            child_effect_indices=tuple(None if child < 0 else child for child in children),
            sound_group=_cstring(data, sound) if sound else None,
        ))

    for record in records:
        for child in record.child_effect_indices:
            if child is not None and child >= count:
                raise ValueError(f"Effect {record.eid_name} has out-of-range child index {child}.")

    (eid_count,) = struct.unpack_from(">I", data, eid_at)
    if eid_at + 4 + eid_count * EID_RECORD_SIZE > len(data):
        raise ValueError("FE10Effect.cms EID table is truncated.")
    eid_table = tuple(
        (index, _cstring(data, pointer))
        for index, pointer in (
            struct.unpack_from(">2I", data, eid_at + 4 + row * EID_RECORD_SIZE)
            for row in range(eid_count)
        )
    )
    ids = tuple(effect_id for effect_id, _eid in eid_table)
    if ids != tuple(sorted(ids)) or len(ids) != len(set(ids)):
        raise ValueError("FE10Effect.cms numeric EID table is not sorted and unique.")
    return Fe10EffectRegistry(tuple(records), eid_table, data)


def _validate_registry(registry: Fe10EffectRegistry) -> None:
    names = [record.eid_name for record in registry.records]
    if any(not name.startswith("EID_") for name in names):
        raise ValueError("Every registered effect needs an EID_ name.")
    if len(names) != len(set(names)):
        raise ValueError("FE10Effect.cms effect names must be unique.")
    count = len(names)
    for record in registry.records:
        if not 0 <= record.flags <= 0xFFFFFFFF:
            raise ValueError(f"{record.eid_name} flags do not fit in 32 bits.")
        if len(record.parameter_bytes) != 4 or any(not 0 <= value <= 0xFF
                                                   for value in record.parameter_bytes):
            raise ValueError(f"{record.eid_name} needs four one-byte parameters.")
        for child in record.child_effect_indices:
            if child is not None and not 0 <= child < count:
                raise ValueError(f"{record.eid_name} has out-of-range child index {child}.")
    ids = [effect_id for effect_id, _name in registry.eid_table]
    if ids != sorted(ids) or len(ids) != len(set(ids)):
        raise ValueError("FE10Effect.cms numeric EID table must be sorted and unique.")
    known = set(names)
    missing = sorted({name for _effect_id, name in registry.eid_table} - known)
    if missing:
        raise ValueError("Numeric aliases target unknown effects: " + ", ".join(missing))

    # Both child slots are recursively loaded by the engine. Cycles would
    # recurse forever, so reject them before constructing the file.
    visiting: set[int] = set()
    visited: set[int] = set()

    def visit(index: int) -> None:
        if index in visiting:
            raise ValueError(f"Effect child graph contains a cycle at {names[index]}.")
        if index in visited:
            return
        visiting.add(index)
        for child in registry.records[index].child_effect_indices:
            if child is not None:
                visit(child)
        visiting.remove(index)
        visited.add(index)

    for index in range(count):
        visit(index)


def build_fe10_effect_registry(registry: Fe10EffectRegistry) -> bytes:
    """Build a valid relocatable ``FE10Effect.cms`` document.

    An unchanged parsed document returns its exact source bytes. Modified
    documents preserve the 16-byte loader header tail and original export
    order while rebuilding records, aliases, strings, relocations and sizes.
    """
    _validate_registry(registry)
    if registry._source:
        original = read_fe10_effect_registry(registry._source)
        if original.records == registry.records and original.eid_table == registry.eid_table:
            return registry._source

    strings = bytearray()
    string_offsets: dict[str, int] = {}
    records_size = 4 + len(registry.records) * RECORD_SIZE
    eid_offset = records_size
    pool_offset = eid_offset + 4 + len(registry.eid_table) * EID_RECORD_SIZE

    def pointer(value: Optional[str]) -> int:
        if not value:
            return 0
        if value not in string_offsets:
            string_offsets[value] = pool_offset + len(strings)
            strings.extend(value.encode("shift_jis") + b"\0")
        return string_offsets[value]

    records = bytearray(struct.pack(">I", len(registry.records)))
    pointer_fields: list[int] = []
    for index, record in enumerate(registry.records):
        row = len(records)
        description = pointer(record.description)
        eid = pointer(record.eid_name)
        sound = pointer(record.sound_group)
        first, second = record.child_effect_indices
        records += struct.pack(
            ">3I4B2hI", description, eid, record.flags, *record.parameter_bytes,
            -1 if first is None else first, -1 if second is None else second, sound,
        )
        pointer_fields.extend(row + field for field, value in ((0, description), (4, eid), (0x14, sound)) if value)

    aliases = bytearray(struct.pack(">I", len(registry.eid_table)))
    for effect_id, name in registry.eid_table:
        row = len(aliases)
        eid = pointer(name)
        aliases += struct.pack(">2I", effect_id, eid)
        pointer_fields.append(eid_offset + row + 4)

    data_section = records + aliases + strings
    data_section += bytes(-len(data_section) % 4)
    symbols = (("EffectData", 0), ("EIDTable", eid_offset))
    if registry._source:
        from . import fe8data
        source_order = [name for _position, _offset, name in fe8data._symbol_entries(registry._source)]
        by_name = dict(symbols)
        if set(source_order) == set(by_name):
            symbols = tuple((name, by_name[name]) for name in source_order)
    names = bytearray()
    exports = bytearray()
    for name, offset in symbols:
        exports += struct.pack(">2I", offset, len(names))
        names += name.encode("ascii") + b"\0"
    relocations = struct.pack(f">{len(pointer_fields)}I", *sorted(pointer_fields)) if pointer_fields else b""
    tail = relocations + exports + names
    header_tail = registry._source[16:32] if registry._source else bytes(16)
    size = 0x20 + len(data_section) + len(tail)
    built = (struct.pack(">4I", size, len(data_section), len(pointer_fields), len(symbols))
             + header_tail + data_section + tail)
    # The builder's output is not trusted until the public reader accepts it.
    read_fe10_effect_registry(built)
    return built


def update_effect_record(data: bytes, index: int, **changes) -> bytes:
    """Update one effect row and rebuild all relocations and strings."""
    registry = read_fe10_effect_registry(data)
    if not 0 <= index < len(registry.records):
        raise IndexError("Effect index is out of range.")
    allowed = {"description", "eid_name", "flags", "parameter_bytes",
               "child_effect_indices", "sound_group"}
    unknown = set(changes) - allowed
    if unknown:
        raise ValueError("Unknown effect fields: " + ", ".join(sorted(unknown)))
    records = list(registry.records)
    records[index] = replace(records[index], **changes)
    aliases = tuple((effect_id, changes.get("eid_name", name) if name == registry.records[index].eid_name else name)
                    for effect_id, name in registry.eid_table)
    return build_fe10_effect_registry(replace(registry, records=tuple(records), eid_table=aliases))


def clone_effect_record(data: bytes, index: int, eid_name: str,
                        description: str | None = None) -> bytes:
    """Append a cloned effect row. Numeric aliases are intentionally not copied."""
    registry = read_fe10_effect_registry(data)
    if not 0 <= index < len(registry.records):
        raise IndexError("Effect index is out of range.")
    source = registry.records[index]
    clone = replace(source, address=0, eid_name=eid_name,
                    description=source.description if description is None else description)
    return build_fe10_effect_registry(replace(registry, records=registry.records + (clone,)))


def remove_effect_record(data: bytes, index: int) -> bytes:
    """Remove an effect, remapping later child indices and its numeric aliases."""
    registry = read_fe10_effect_registry(data)
    if not 0 <= index < len(registry.records):
        raise IndexError("Effect index is out of range.")
    users = [record.eid_name for record in registry.records
             if index in record.child_effect_indices]
    if users:
        raise ValueError("Effect is still used as a child by: " + ", ".join(users))
    removed = registry.records[index].eid_name
    records = []
    for current, record in enumerate(registry.records):
        if current == index:
            continue
        children = tuple(child - 1 if child is not None and child > index else child
                         for child in record.child_effect_indices)
        records.append(replace(record, child_effect_indices=children))
    aliases = tuple(pair for pair in registry.eid_table if pair[1] != removed)
    return build_fe10_effect_registry(replace(registry, records=tuple(records), eid_table=aliases))


def set_numeric_aliases(data: bytes, eid_name: str, effect_ids: tuple[int, ...]) -> bytes:
    """Replace the numeric aliases of one registered EID."""
    registry = read_fe10_effect_registry(data)
    if eid_name not in {record.eid_name for record in registry.records}:
        raise ValueError(f"Unknown registered effect {eid_name}.")
    if any(not 0 <= effect_id <= 0xFFFFFFFF for effect_id in effect_ids):
        raise ValueError("Numeric effect IDs must fit in 32 bits.")
    aliases = [pair for pair in registry.eid_table if pair[1] != eid_name]
    aliases.extend((effect_id, eid_name) for effect_id in effect_ids)
    aliases.sort()
    return build_fe10_effect_registry(replace(registry, eid_table=tuple(aliases)))
