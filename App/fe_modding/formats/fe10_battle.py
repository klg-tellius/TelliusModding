"""Structural reader for Radiant Dawn's decompressed ``FE10Battle.cms``.

The file is a standard relocatable Tellius data container. Twenty-one named
tables have a four-byte ``u16 count, u16 zero`` header and fixed-size rows;
three camera symbols are raw byte arrays. Pointer fields are determined from
the container relocation list rather than guessed from values. Unknown row
bytes remain available verbatim while individual relocated strings can be
inspected safely.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass, field, replace

from .common import HEADER_SIZE
from .fe8data import symbol_offsets

# symbol: record size. Counts are read from the file.
TABLE_SIZES = {
    "FE10BAnimData": 20,
    "FE10BFootEffect": 24,
    "FE10BSFXList": 20,
    "FE10BSFXData": 20,
    "FE10BSetup": 8,
    "FE10BWeapon": 36,
    "FE10BWeaponType": 8,
    "FE10BMapModel": 24,
    "FE10BMapData": 16,
    "FE10BSky": 8,
    "FE10BSkill": 20,
    "FE10BMotion": 12,
    "FE10BFlags": 4,
    "FE10BParam": 4,
    "FE10BCamFile": 12,
    "FE10BCamGroup": 20,
    "FE10BCamEffect": 16,
    "FE10BCamList": 72,
    "FE10BCamType": 8,
    "FE10BUnit": 340,
    "FE10BTex": 8,
}

RAW_ARRAYS = ("FE10BCamFileIndex", "FE10BCamFileRate", "FE10BCamGroupIndex")

BATTLE_SYMBOL_ORDER = (
    "FE10BAnimData", "FE10BFootEffect", "FE10BSFXList", "FE10BSFXData", "FE10BSetup",
    "FE10BWeapon", "FE10BWeaponType", "FE10BMapModel", "FE10BMapData", "FE10BSky",
    "FE10BSkill", "FE10BMotion", "FE10BFlags", "FE10BParam", "FE10BCamFile",
    "FE10BCamGroup", "FE10BCamFileIndex", "FE10BCamFileRate", "FE10BCamEffect",
    "FE10BCamList", "FE10BCamGroupIndex", "FE10BCamType", "FE10BUnit", "FE10BTex",
)


@dataclass(frozen=True)
class BattleRecord:
    address: int  # absolute file address
    raw: bytes
    strings: tuple[tuple[int, str], ...]  # (row-relative byte offset, value)

    @property
    def words(self) -> tuple[int, ...]:
        return struct.unpack(f">{len(self.raw) // 4}I", self.raw)


@dataclass(frozen=True)
class BattleTable:
    name: str
    record_size: int
    records: tuple[BattleRecord, ...]


@dataclass(frozen=True)
class CameraChoice:
    """One weighted camera-file choice owned by an ``FE10BCamGroup`` row."""

    file_index: int
    selection_weight: int


@dataclass(frozen=True)
class CameraGroup:
    record_index: int
    choices: tuple[CameraChoice, ...]


@dataclass(frozen=True)
class CameraList:
    record_index: int
    # Sixteen dispatch contexts, each indexed by the 30-row FE10BMotion table.
    group_indices: tuple[tuple[int | None, ...], ...]


@dataclass(frozen=True)
class MapModel:
    record_index: int
    archive_name: str
    sound_group: str
    flags: int
    parameters: tuple[int, ...]
    translation: tuple[int, int, int]
    rotation_value: int
    scale_value: int


@dataclass(frozen=True)
class MapData:
    record_index: int
    map_name: str
    model_indices: tuple[int | None, ...]


@dataclass(frozen=True)
class TextureMapping:
    condition: str
    texture_name: str


@dataclass(frozen=True)
class UnitTextureSet:
    record_index: int
    unit_name: str
    model_name: str
    mappings: tuple[TextureMapping, ...]


@dataclass(frozen=True)
class Fe10Battle:
    tables: tuple[BattleTable, ...]
    arrays: tuple[tuple[str, bytes], ...]
    string_pool: bytes
    camera_groups: tuple[CameraGroup, ...]
    camera_lists: tuple[CameraList, ...]
    camera_context_names: tuple[str, ...]
    map_models: tuple[MapModel, ...]
    map_data: tuple[MapData, ...]
    texture_mappings: tuple[TextureMapping, ...]
    unit_texture_sets: tuple[UnitTextureSet, ...]
    _source: bytes = field(default=b"", repr=False, compare=False)

    def table(self, name: str) -> BattleTable:
        return next(table for table in self.tables if table.name == name)

    def map_model(self, map_record: MapData, variant: int) -> MapModel | None:
        """Resolve one of the five scenery variants using the engine's fallback order."""
        if not 0 <= variant < 5:
            raise IndexError("Battle scenery variant must be 0 through 4.")
        index = map_record.model_indices[variant]
        if index is None and variant == 3:
            index = map_record.model_indices[2]
        if index is None:
            index = map_record.model_indices[0]
        return None if index is None else self.map_models[index]


def _cstring(data: bytes, pointer: int) -> str:
    start = HEADER_SIZE + pointer
    if not HEADER_SIZE <= start < len(data):
        raise ValueError(f"String pointer {pointer:#x} is outside FE10Battle.cms.")
    end = data.find(b"\0", start)
    if end < 0:
        raise ValueError(f"String at {pointer:#x} is not terminated.")
    return data[start:end].decode("shift_jis", errors="replace")


def read_fe10_battle(data: bytes) -> Fe10Battle:
    _size, data_size, pointer_count, _symbol_count = struct.unpack_from(">4I", data)
    data_end = HEADER_SIZE + data_size
    if data_end > len(data):
        raise ValueError("FE10Battle.cms data section is truncated.")
    symbols = symbol_offsets(data)
    missing = (set(TABLE_SIZES) | set(RAW_ARRAYS)) - set(symbols)
    if missing:
        raise ValueError("FE10Battle.cms is missing symbols: " + ", ".join(sorted(missing)))
    pointers = set(struct.unpack_from(f">{pointer_count}I", data, data_end))

    tables = []
    table_ends = {}
    for name, record_size in TABLE_SIZES.items():
        start = symbols[name]
        count, reserved = struct.unpack_from(">HH", data, HEADER_SIZE + start)
        if reserved:
            raise ValueError(f"{name} has non-zero reserved count padding {reserved:#x}.")
        end = start + 4 + count * record_size
        if end > data_size:
            raise ValueError(f"{name} rows extend beyond the data section.")
        records = []
        for index in range(count):
            row_offset = start + 4 + index * record_size
            raw = data[HEADER_SIZE + row_offset : HEADER_SIZE + row_offset + record_size]
            strings = []
            for field in range(0, record_size, 4):
                if row_offset + field in pointers:
                    (pointer,) = struct.unpack_from(">I", raw, field)
                    strings.append((field, _cstring(data, pointer) if pointer else ""))
            records.append(BattleRecord(HEADER_SIZE + row_offset, raw, tuple(strings)))
        tables.append(BattleTable(name, record_size, tuple(records)))
        table_ends[name] = end

    ordered_symbols = sorted(symbols.items(), key=lambda item: item[1])
    next_offset = {name: (ordered_symbols[i + 1][1] if i + 1 < len(ordered_symbols) else data_size)
                   for i, (name, _offset) in enumerate(ordered_symbols)}
    arrays = tuple(
        (name, data[HEADER_SIZE + symbols[name] : HEADER_SIZE + next_offset[name]])
        for name in RAW_ARRAYS
    )
    by_name = {table.name: table for table in tables}
    array_data = dict(arrays)
    file_indices = array_data["FE10BCamFileIndex"]
    selection_weights = array_data["FE10BCamFileRate"]
    group_rows = by_name["FE10BCamGroup"].records
    file_rows = by_name["FE10BCamFile"].records
    choice_count = sum(record.raw[11] for record in group_rows)
    if len(file_indices) != choice_count or len(selection_weights) != choice_count:
        raise ValueError(
            "FE10 camera file-index/rate arrays do not match the group choice counts."
        )
    camera_groups = []
    choice_at = 0
    for index, record in enumerate(group_rows):
        count = record.raw[11]
        choices = []
        for file_index, weight in zip(
                file_indices[choice_at:choice_at + count],
                selection_weights[choice_at:choice_at + count]):
            if file_index >= len(file_rows):
                raise ValueError(f"FE10BCamGroup row {index} uses invalid camera file {file_index}.")
            choices.append(CameraChoice(file_index, weight))
        camera_groups.append(CameraGroup(index, tuple(choices)))
        choice_at += count

    weapon_type_rows = by_name["FE10BWeaponType"].records
    if len(weapon_type_rows) != 16:
        raise ValueError(
            f"FE10BWeaponType has {len(weapon_type_rows)} rows; camera dispatch requires 16."
        )
    camera_context_names = tuple(
        dict(record.strings).get(4, f"type_{index}")
        for index, record in enumerate(weapon_type_rows)
    )
    motion_count = len(by_name["FE10BMotion"].records)
    list_rows = by_name["FE10BCamList"].records
    group_matrix = array_data["FE10BCamGroupIndex"]
    expected_matrix_size = len(list_rows) * 16 * motion_count
    if len(group_matrix) != expected_matrix_size:
        raise ValueError(
            f"FE10BCamGroupIndex is {len(group_matrix)} bytes; expected {expected_matrix_size} "
            "for 16 contexts per camera list and one entry per battle motion."
        )
    camera_lists = []
    matrix_at = 0
    for list_index, _record in enumerate(list_rows):
        contexts = []
        for _context in range(16):
            values = []
            for value in group_matrix[matrix_at:matrix_at + motion_count]:
                if value == 0xff:
                    values.append(None)
                elif value < len(group_rows):
                    values.append(value)
                else:
                    raise ValueError(
                        f"FE10BCamList row {list_index} uses invalid camera group {value}."
                    )
            contexts.append(tuple(values))
            matrix_at += motion_count
        camera_lists.append(CameraList(list_index, tuple(contexts)))

    map_model_rows = by_name["FE10BMapModel"].records
    map_models = tuple(
        MapModel(
            record_index=index,
            archive_name=dict(record.strings).get(0, ""),
            sound_group=dict(record.strings).get(4, ""),
            flags=record.raw[8],
            parameters=tuple(record.raw[9:14]),
            translation=struct.unpack_from(">3h", record.raw, 14),
            rotation_value=struct.unpack_from(">h", record.raw, 20)[0],
            scale_value=struct.unpack_from(">h", record.raw, 22)[0],
        )
        for index, record in enumerate(map_model_rows)
    )
    map_data = []
    for index, record in enumerate(by_name["FE10BMapData"].records):
        indices = tuple(None if value < 0 else value for value in struct.unpack_from(">5h", record.raw, 4))
        for model_index in indices:
            if model_index is not None and model_index >= len(map_models):
                raise ValueError(f"FE10BMapData row {index} uses invalid map model {model_index}.")
        map_data.append(MapData(index, dict(record.strings).get(0, ""), indices))

    texture_mappings = tuple(
        TextureMapping(dict(record.strings).get(0, ""), dict(record.strings).get(4, ""))
        for record in by_name["FE10BTex"].records
    )
    unit_texture_sets = []
    texture_at = 0
    for index, record in enumerate(by_name["FE10BUnit"].records):
        count = record.raw[0x14D]
        end = texture_at + count
        if end > len(texture_mappings):
            raise ValueError(f"FE10BUnit row {index} texture mappings exceed FE10BTex.")
        strings = dict(record.strings)
        unit_texture_sets.append(UnitTextureSet(
            index, strings.get(0, ""), strings.get(4, ""), texture_mappings[texture_at:end]))
        texture_at = end
    if texture_at != len(texture_mappings):
        raise ValueError(
            f"FE10BUnit texture counts consume {texture_at} of {len(texture_mappings)} FE10BTex rows."
        )

    pool_start = table_ends["FE10BTex"]
    return Fe10Battle(
        tuple(tables), arrays, data[HEADER_SIZE + pool_start:data_end],
        tuple(camera_groups), tuple(camera_lists), camera_context_names,
        map_models, tuple(map_data), texture_mappings, tuple(unit_texture_sets), data,
    )


def _replace_table(document: Fe10Battle, name: str,
                   records: tuple[BattleRecord, ...]) -> Fe10Battle:
    return replace(document, tables=tuple(
        replace(table, records=records) if table.name == name else table
        for table in document.tables
    ))


def _replace_array(document: Fe10Battle, name: str, value: bytes) -> Fe10Battle:
    return replace(document, arrays=tuple(
        (array_name, value if array_name == name else data)
        for array_name, data in document.arrays
    ))


def build_fe10_battle(document: Fe10Battle) -> bytes:
    """Rebuild all FE10 battle tables, raw arrays, strings and relocations.

    Unknown row bytes and the original string pool are retained. An unchanged
    parsed RFEE01 document returns its exact source bytes.
    """
    tables = {table.name: table for table in document.tables}
    arrays = dict(document.arrays)
    missing = (set(TABLE_SIZES) - set(tables)) | (set(RAW_ARRAYS) - set(arrays))
    if missing:
        raise ValueError("FE10Battle.cms is missing: " + ", ".join(sorted(missing)))
    for name, size in TABLE_SIZES.items():
        table = tables[name]
        if table.record_size != size or any(len(record.raw) != size for record in table.records):
            raise ValueError(f"{name} contains a row of the wrong size.")
    if document._source:
        original = read_fe10_battle(document._source)
        if original.tables == document.tables and original.arrays == document.arrays:
            return document._source

    order = list(BATTLE_SYMBOL_ORDER)
    export_order = list(BATTLE_SYMBOL_ORDER)
    if document._source:
        from . import fe8data
        entries = fe8data._symbol_entries(document._source)
        candidate = [name for _position, _offset, name in entries]
        physical = [name for _position, _offset, name in sorted(entries, key=lambda item: item[1])]
        if set(candidate) == set(order):
            export_order = candidate
            order = physical

    blocks: dict[str, bytearray] = {}
    symbol_offsets_new: dict[str, int] = {}
    data_section = bytearray()
    pointer_patches: list[tuple[int, str, int | None]] = []

    old_pool_at = None
    if document._source:
        tex_at = symbol_offsets(document._source)["FE10BTex"]
        tex_count = struct.unpack_from(">H", document._source, HEADER_SIZE + tex_at)[0]
        old_pool_at = tex_at + 4 + tex_count * TABLE_SIZES["FE10BTex"]

    for name in order:
        symbol_offsets_new[name] = len(data_section)
        if name in tables:
            table = tables[name]
            block = bytearray(struct.pack(">HH", len(table.records), 0))
            for index, record in enumerate(table.records):
                raw = bytearray(record.raw)
                for field_offset, value in record.strings:
                    old_pointer = struct.unpack_from(">I", raw, field_offset)[0]
                    patch_at = len(data_section) + len(block) + field_offset
                    pointer_patches.append((patch_at, value, old_pointer))
                    struct.pack_into(">I", raw, field_offset, 0)
                block += raw
        else:
            block = bytearray(arrays[name])
        blocks[name] = block
        data_section += block

    pool_at = len(data_section)
    strings = bytearray(document.string_pool)
    appended: dict[str, int] = {}

    def string_pointer(value: str, old_pointer: int | None) -> int:
        if not value:
            return 0
        encoded = value.encode("shift_jis") + b"\0"
        if old_pool_at is not None and old_pointer is not None and old_pointer >= old_pool_at:
            relative = old_pointer - old_pool_at
            if strings[relative:relative + len(encoded)] == encoded:
                return pool_at + relative
        found = strings.find(encoded)
        if found >= 0:
            return pool_at + found
        if value not in appended:
            appended[value] = pool_at + len(strings)
            strings.extend(encoded)
        return appended[value]

    pointers: list[int] = []
    for patch_at, value, old_pointer in pointer_patches:
        target = string_pointer(value, old_pointer)
        struct.pack_into(">I", data_section, patch_at, target)
        if target:
            pointers.append(patch_at)
    data_section += strings
    data_section += bytes(-len(data_section) % 4)

    names = bytearray()
    exports = bytearray()
    for name in export_order:
        exports += struct.pack(">2I", symbol_offsets_new[name], len(names))
        names += name.encode("ascii") + b"\0"
    relocations = struct.pack(f">{len(pointers)}I", *sorted(pointers)) if pointers else b""
    header_tail = document._source[16:32] if document._source else bytes(16)
    size = 0x20 + len(data_section) + len(relocations) + len(exports) + len(names)
    built = (struct.pack(">4I", size, len(data_section), len(pointers), len(export_order))
             + header_tail + data_section + relocations + exports + names)
    read_fe10_battle(built)
    return built


def update_battle_record(data: bytes, table_name: str, index: int, *,
                         raw: bytes | None = None,
                         strings: dict[int, str] | None = None) -> bytes:
    """Replace one fixed row while retaining every opaque byte by default."""
    document = read_fe10_battle(data)
    table = document.table(table_name)
    if not 0 <= index < len(table.records):
        raise IndexError(f"{table_name} row index is out of range.")
    record = table.records[index]
    new_raw = record.raw if raw is None else bytes(raw)
    if len(new_raw) != table.record_size:
        raise ValueError(f"{table_name} rows are {table.record_size} bytes.")
    new_strings = dict(record.strings)
    if strings:
        if any(offset % 4 or not 0 <= offset <= table.record_size - 4 for offset in strings):
            raise ValueError("String field offsets must identify a whole word in the row.")
        new_strings.update(strings)
    records = list(table.records)
    records[index] = replace(record, raw=new_raw, strings=tuple(sorted(new_strings.items())))
    return build_fe10_battle(_replace_table(document, table_name, tuple(records)))


def clone_map_model(data: bytes, index: int, archive_name: str) -> tuple[bytes, int]:
    """Append an ``FE10BMapModel`` clone with a new scenery archive name."""
    document = read_fe10_battle(data)
    table = document.table("FE10BMapModel")
    if not 0 <= index < len(table.records):
        raise IndexError("Battle map-model index is out of range.")
    source = table.records[index]
    strings = dict(source.strings)
    strings[0] = archive_name
    clone = replace(source, address=0, strings=tuple(sorted(strings.items())))
    return build_fe10_battle(_replace_table(
        document, table.name, table.records + (clone,))), len(table.records)


def remove_map_model(data: bytes, index: int) -> bytes:
    """Remove an unused map model and remap all later scenery indices."""
    document = read_fe10_battle(data)
    models = document.table("FE10BMapModel")
    if not 0 <= index < len(models.records):
        raise IndexError("Battle map-model index is out of range.")
    users = [row.map_name for row in document.map_data if index in row.model_indices]
    if users:
        raise ValueError("Battle map model is still used by: " + ", ".join(users))
    document = _replace_table(document, models.name, models.records[:index] + models.records[index + 1:])
    maps = document.table("FE10BMapData")
    remapped = []
    for record in maps.records:
        raw = bytearray(record.raw)
        values = list(struct.unpack_from(">5h", raw, 4))
        values = [value - 1 if value > index else value for value in values]
        struct.pack_into(">5h", raw, 4, *values)
        remapped.append(replace(record, raw=bytes(raw)))
    return build_fe10_battle(_replace_table(document, maps.name, tuple(remapped)))


def clone_camera_file(data: bytes, index: int, file_name: str,
                      description: str | None = None) -> tuple[bytes, int]:
    """Append a camera-file registry row cloned from ``index``."""
    document = read_fe10_battle(data)
    table = document.table("FE10BCamFile")
    if not 0 <= index < len(table.records):
        raise IndexError("Camera file index is out of range.")
    existing = {dict(record.strings).get(4) for record in table.records}
    if file_name in existing:
        raise ValueError(f"Camera clip {file_name} is already registered.")
    source = table.records[index]
    strings = dict(source.strings)
    strings[4] = file_name
    if description is not None:
        strings[0] = description
    clone = replace(source, address=0, strings=tuple(sorted(strings.items())))
    return build_fe10_battle(_replace_table(
        document, table.name, table.records + (clone,))), len(table.records)


def remove_camera_file(data: bytes, index: int) -> bytes:
    """Remove an unreferenced camera file and remap later group choices."""
    document = read_fe10_battle(data)
    table = document.table("FE10BCamFile")
    if not 0 <= index < len(table.records):
        raise IndexError("Camera file index is out of range.")
    users = [group.record_index for group in document.camera_groups
             if any(choice.file_index == index for choice in group.choices)]
    if users:
        raise ValueError("Camera file is still used by groups: " + ", ".join(map(str, users)))
    indices = bytes(value - 1 if value > index else value
                    for value in dict(document.arrays)["FE10BCamFileIndex"])
    document = _replace_table(document, table.name, table.records[:index] + table.records[index + 1:])
    return build_fe10_battle(_replace_array(document, "FE10BCamFileIndex", indices))


def clone_unit_model(data: bytes, index: int, model_name: str,
                     description: str) -> tuple[bytes, int]:
    """Clone one battle unit/model row and its owned texture slice."""
    document = read_fe10_battle(data)
    units = document.table("FE10BUnit")
    textures = document.table("FE10BTex")
    if not 0 <= index < len(units.records):
        raise IndexError("Battle unit-model index is out of range.")
    if model_name in {unit.model_name for unit in document.unit_texture_sets}:
        raise ValueError(f"Battle model {model_name} already exists.")
    source_set = document.unit_texture_sets[index]
    start = sum(len(unit.mappings) for unit in document.unit_texture_sets[:index])
    count = len(source_set.mappings)
    texture_clones = []
    for record in textures.records[start:start + count]:
        values = dict(record.strings)
        if values.get(4) == source_set.model_name:
            values[4] = model_name
        texture_clones.append(replace(record, address=0, strings=tuple(sorted(values.items()))))
    source = units.records[index]
    values = dict(source.strings)
    values[0], values[4] = description, model_name
    unit_clone = replace(source, address=0, strings=tuple(sorted(values.items())))
    document = _replace_table(document, units.name, units.records + (unit_clone,))
    document = _replace_table(document, textures.name, textures.records + tuple(texture_clones))
    return build_fe10_battle(document), len(units.records)


def add_unit_texture(data: bytes, index: int, condition: str, texture_name: str) -> bytes:
    """Give battle unit ``index`` one more ``FE10BTex`` row, ``condition`` (an army key or a PID)
    -> ``texture_name`` (``zu/<model>/<texture>.tpl``), at the end of its slice; the unit's row
    count (+0x14D) goes up by one. A PID row is picked before the army rows (retail
    ``PID_ISAIYA`` -> ``ISAIYA`` follows ``swoL``'s four army rows)."""
    document = read_fe10_battle(data)
    units = document.table("FE10BUnit")
    textures = document.table("FE10BTex")
    if not 0 <= index < len(units.records):
        raise IndexError("Battle unit-model index is out of range.")
    unit = document.unit_texture_sets[index]
    if any(m.condition == condition for m in unit.mappings):
        raise ValueError(f"{unit.unit_name} already has a {condition} texture.")
    if len(unit.mappings) >= 0xFF:
        raise ValueError(f"{unit.unit_name} has no room for another texture row.")
    end = sum(len(item.mappings) for item in document.unit_texture_sets[:index + 1])
    template = textures.records[end - 1] if unit.mappings else textures.records[0]
    row = replace(template, address=0, raw=bytes(len(template.raw)),
                  strings=((0, condition), (4, texture_name)))
    raw = bytearray(units.records[index].raw)
    raw[0x14D] += 1
    unit_records = list(units.records)
    unit_records[index] = replace(units.records[index], raw=bytes(raw))
    document = _replace_table(document, units.name, tuple(unit_records))
    document = _replace_table(document, textures.name, textures.records[:end] + (row,) + textures.records[end:])
    return build_fe10_battle(document)


def clone_battle_selector(
    data: bytes, index: int, description: str, *, aid: str | None = None,
    pid: str | None = None, jid: str | None = None,
) -> tuple[bytes, int]:
    """Append an FE10BAnimData selector targeting a unit description."""
    if not any((aid, pid, jid)):
        raise ValueError("A battle selector needs an AID, PID, or JID.")
    document = read_fe10_battle(data)
    table = document.table("FE10BAnimData")
    if not 0 <= index < len(table.records):
        raise IndexError("Battle animation selector index is out of range.")
    source = table.records[index]
    raw = bytearray(source.raw)
    values = dict(source.strings)
    for field_offset, value in ((0, aid), (4, pid), (8, jid)):
        if value:
            values[field_offset] = value
        else:
            values.pop(field_offset, None)
            struct.pack_into(">I", raw, field_offset, 0)
    values[12] = description
    clone = replace(source, address=0, raw=bytes(raw), strings=tuple(sorted(values.items())))
    return build_fe10_battle(_replace_table(
        document, table.name, table.records + (clone,))), len(table.records)


def update_battle_selector(
    data: bytes, index: int, *, aid: str | None = None,
    pid: str | None = None, jid: str | None = None,
) -> bytes:
    """Change the stable selector keys of one FE10BAnimData row."""
    if not any((aid, pid, jid)):
        raise ValueError("A battle selector needs an AID, PID, or JID.")
    document = read_fe10_battle(data)
    table = document.table("FE10BAnimData")
    if not 0 <= index < len(table.records):
        raise IndexError("Battle animation selector index is out of range.")
    record = table.records[index]
    raw = bytearray(record.raw)
    values = dict(record.strings)
    for field_offset, value in ((0, aid), (4, pid), (8, jid)):
        if value:
            values[field_offset] = value
        else:
            values.pop(field_offset, None)
            struct.pack_into(">I", raw, field_offset, 0)
    records = list(table.records)
    records[index] = replace(record, raw=bytes(raw), strings=tuple(sorted(values.items())))
    return build_fe10_battle(_replace_table(document, table.name, tuple(records)))


def remove_battle_selector(data: bytes, index: int) -> bytes:
    document = read_fe10_battle(data)
    table = document.table("FE10BAnimData")
    if not 0 <= index < len(table.records):
        raise IndexError("Battle animation selector index is out of range.")
    return build_fe10_battle(_replace_table(
        document, table.name, table.records[:index] + table.records[index + 1:]))


def remove_unit_model(data: bytes, index: int) -> bytes:
    """Remove an unreferenced battle unit/model and its texture slice."""
    document = read_fe10_battle(data)
    units = document.table("FE10BUnit")
    textures = document.table("FE10BTex")
    if not 0 <= index < len(units.records):
        raise IndexError("Battle unit-model index is out of range.")
    unit = document.unit_texture_sets[index]
    description = dict(units.records[index].strings).get(0)
    users = [row for row, record in enumerate(document.table("FE10BAnimData").records)
             if dict(record.strings).get(12) == description]
    if users:
        raise ValueError("Battle unit model is still used by selectors: " + ", ".join(map(str, users)))
    start = sum(len(item.mappings) for item in document.unit_texture_sets[:index])
    count = len(unit.mappings)
    document = _replace_table(document, units.name, units.records[:index] + units.records[index + 1:])
    document = _replace_table(
        document, textures.name, textures.records[:start] + textures.records[start + count:])
    return build_fe10_battle(document)


def _row_offset(data: bytes, table: str, index: int) -> int:
    start = symbol_offsets(data)[table]
    count = struct.unpack_from(">H", data, HEADER_SIZE + start)[0]
    if not 0 <= index < count:
        raise IndexError(f"{table} row index is out of range.")
    return HEADER_SIZE + start + 4 + index * TABLE_SIZES[table]


def set_map_model_variant(data: bytes, map_index: int, variant: int,
                          model_index: int | None) -> bytes:
    """Patch one signed ``FE10BMapData`` model index, preserving all other bytes."""
    document = read_fe10_battle(data)
    if not 0 <= map_index < len(document.map_data):
        raise IndexError("Battle map index is out of range.")
    if not 0 <= variant < 5:
        raise IndexError("Battle scenery variant must be 0 through 4.")
    if model_index is not None and not 0 <= model_index < len(document.map_models):
        raise IndexError("Battle scenery model index is out of range.")
    out = bytearray(data)
    struct.pack_into(">h", out, _row_offset(data, "FE10BMapData", map_index) + 4 + variant * 2,
                     -1 if model_index is None else model_index)
    return bytes(out)


def set_camera_choice_weight(data: bytes, group_index: int, choice_index: int,
                             weight: int) -> bytes:
    """Patch one camera-group selection weight in the parallel rate array."""
    document = read_fe10_battle(data)
    if not 0 <= group_index < len(document.camera_groups):
        raise IndexError("Camera group index is out of range.")
    group = document.camera_groups[group_index]
    if not 0 <= choice_index < len(group.choices):
        raise IndexError("Camera choice index is out of range.")
    if not 0 <= weight <= 100:
        raise ValueError("Camera selection weight must be from 0 to 100.")
    preceding = sum(len(item.choices) for item in document.camera_groups[:group_index])
    offset = HEADER_SIZE + symbol_offsets(data)["FE10BCamFileRate"] + preceding + choice_index
    out = bytearray(data)
    out[offset] = weight
    return bytes(out)


def set_camera_dispatch_group(data: bytes, list_index: int, context_index: int,
                              motion_index: int, group_index: int | None) -> bytes:
    """Patch one camera-list/context/motion dispatch byte; ``None`` writes ``0xff``."""
    document = read_fe10_battle(data)
    if not 0 <= list_index < len(document.camera_lists):
        raise IndexError("Camera list index is out of range.")
    if not 0 <= context_index < len(document.camera_context_names):
        raise IndexError("Camera context index is out of range.")
    motion_count = len(document.table("FE10BMotion").records)
    if not 0 <= motion_index < motion_count:
        raise IndexError("Battle motion index is out of range.")
    if group_index is not None and not 0 <= group_index < len(document.camera_groups):
        raise IndexError("Camera group index is out of range.")
    linear = ((list_index * len(document.camera_context_names) + context_index) * motion_count
              + motion_index)
    offset = HEADER_SIZE + symbol_offsets(data)["FE10BCamGroupIndex"] + linear
    out = bytearray(data)
    out[offset] = 0xFF if group_index is None else group_index
    return bytes(out)
