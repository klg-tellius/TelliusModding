"""Editable fields of Radiant Dawn's ``sound_data*.cms``: the cue parameters and the ``SND_*`` tables.

:mod:`formats.fe10_sound` names every byte (``CUE_FIELDS``, ``SND_TABLES``, each cited to its RFEE01
reader). This module gives those fields types and writers for the editor pages:

- A cue's parameters (+0x08..+0x23): kind, volume, pitch, pans, filters, sends, priority, voice limit,
  random pitch and volume, start delay, distance settings, Sound Room index. The name and BRSAR sound
  stay with ``fe10_sound.repoint_cue`` / ``add_cue``.
- The ``SND_*`` tables: per-map environment sounds and mixer settings, the ``.ga`` SFX event codes,
  each chapter's music (``SND_MAP_BGM_DATA``), boss and pairing battle themes
  (``SND_BATTLE_BGM_DATA``) and the BRSAR group each chapter loads.

Text fields are pointers to NUL-terminated names (a cue, a chapter ID ``C0101``, a map ``bmap0101``, a
PID, an event-flag name); an empty value writes a null pointer. A name the file does not hold yet is
added to its string pool. Numbers are written in place; every other byte is kept.

``add_row`` copies a row: the table moves to the end of the data section with one row more and its
export points at the copy (the game finds each table by that export, RFEE01 ``0x80077064``). The old
rows stay behind, unread.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass
from typing import Optional

from . import fe8data, fe10_sound
from .common import HEADER_SIZE
from .record_fields import LABEL, Field, FieldError, read_numbers, write_numbers


class SoundTableError(FieldError):
    pass


#: The cue record's parameters (``fe10_sound.CUE_FIELDS`` from +0x08; the readers are cited there).
CUE_PARAMETERS = (
    Field("kind", 0x08, "u8", "Kind", "0 or 1: a stream (music, voices), 2: a sound effect."),
    Field("volume", 0x09, "u8", "Volume", "0-127."),
    Field("pitch", 0x0A, "s16", "Pitch", "0: unchanged. The game divides it by the pitch divisor and turns it into a frequency ratio."),
    Field("pitch_divisor", 0x0C, "u8", "Pitch divisor"),
    Field("pan", 0x0D, "u8", "Pan", "64 is the centre."),
    Field("surround_pan", 0x0E, "u8", "Surround pan"),
    Field("low_pass", 0x0F, "u8", "Low-pass filter"),
    Field("main_send", 0x11, "u8", "Main send", "0-127."),
    Field("effect_send", 0x12, "u8", "Effect send", "0-127 (reverb)."),
    Field("priority", 0x13, "u8", "Priority"),
    Field("no_distance", 0x14, "u8", "No distance attenuation", "1: the volume does not fall with distance."),
    Field("max_plays", 0x15, "u8", "Most simultaneous plays", "255: no limit."),
    Field("random_pitch_min", 0x16, "s16", "Random pitch, lowest"),
    Field("random_pitch_max", 0x18, "s16", "Random pitch, highest"),
    Field("random_volume_min", 0x1A, "s8", "Random volume, lowest"),
    Field("random_volume_max", 0x1B, "s8", "Random volume, highest"),
    Field("start_delay", 0x1C, "u16", "Start delay (frames)"),
    Field("distance_low_pass", 0x1E, "s8", "Distance low-pass"),
    Field("distance_main_send", 0x20, "s8", "Distance main send"),
    Field("distance_effect_send", 0x21, "s8", "Distance effect send"),
    Field("sound_room", 0x22, "u16", "Sound Room index", "65535: not in the Sound Room."),
)


@dataclass(frozen=True)
class Table:
    symbol: str
    title: str
    row_size: int
    fields: tuple[Field, ...]
    note: str = ""

    def field(self, key: str) -> Field:
        return next(f for f in self.fields if f.key == key)


_ANY = "-1: any."
TABLES = {table.symbol: table for table in (
    Table("SND_MAP_BGM_DATA", "Chapter music", 0x34, (
        Field("chapter", 0x00, LABEL, "Chapter", "The chapter ID (C0101)."),
        Field("condition", 0x04, "u8", "Condition kind", "0 on every chapter but one (2)."),
        *(Field(f"map{i}", 0x08 + 4 * i, LABEL, f"Map music {i + 1}" if i else "Map music",
                "" if i else "The cue played on the map.") for i in range(4)),
        Field("phase_player", 0x18, LABEL, "Player phase"),
        Field("phase_enemy", 0x1C, LABEL, "Enemy phase"),
        Field("phase_third", 0x20, LABEL, "Third army phase"),
        Field("phase_fourth", 0x24, LABEL, "Fourth army phase"),
        Field("preparations", 0x28, LABEL, "Preparations"),
        Field("base", 0x2C, LABEL, "Base"),
        Field("select", 0x30, LABEL, "Unit select"),
    ), "One row per chapter. A chapter without a row has no music of its own (RFEE01 0x80068398)."),
    Table("SND_BATTLE_BGM_DATA", "Battle themes", 0x1C, (
        Field("cue", 0x00, LABEL, "Theme", "The cue played during the fight."),
        Field("chapter", 0x04, LABEL, "Chapter", "Empty: every chapter."),
        Field("pid1", 0x08, LABEL, "Character", "Empty: anyone."),
        Field("pid2", 0x0C, LABEL, "Opponent", "Empty: anyone."),
        Field("flag", 0x10, LABEL, "Event flag", "A flag name; empty: no flag test."),
        Field("class1", 0x14, "s8", "Character's class value", _ANY),
        Field("class2", 0x15, "s8", "Opponent's class value", _ANY),
        Field("army1", 0x16, "s8", "Character's army", _ANY),
        Field("army2", 0x17, "s8", "Opponent's army", _ANY),
        Field("flag_state", 0x18, "u8", "Flag state", "1: the flag must be set, 0: clear."),
        Field("either_order", 0x19, "u8", "Either order", "1: the two sides may be swapped."),
    ), "The first matching row picks the fight's music (RFEE01 0x800689d4, row test 0x80068638)."),
    Table("SND_ENV_DATA", "Environment sounds", 0x18, (
        Field("map", 0x00, LABEL, "Map or scenery", "bmap0101, a battle backdrop (bg0310sky)..."),
        Field("cue", 0x04, LABEL, "Sound"),
        Field("emitter_kind", 0x08, "u8", "Emitter kind", "1, 3 or 4 on the disc."),
        Field("emitter_state", 0x09, "u8", "Emitter state"),
        Field("x", 0x0C, "f32", "Position X"), Field("y", 0x10, "f32", "Position Y"),
        Field("z", 0x14, "f32", "Position Z"),
    ), "Ambient and positioned sounds of each map (RFEE01 0x8013a8d8)."),
    Table("SND_MAP_DATA", "Map mixer", 0x14, (
        Field("map", 0x00, LABEL, "Map"),
        Field("mixer_a", 0x04, "u8", "Mixer A", "0-127."), Field("mixer_b", 0x05, "u8", "Mixer B", "0-127."),
        Field("float0", 0x08, "f32", "Mixer value 1"), Field("float1", 0x0C, "f32", "Mixer value 2"),
        Field("float2", 0x10, "f32", "Mixer value 3"),
    ), "Per-map mixer settings (RFEE01 0x8013ac48)."),
    Table("SND_SFX_MAYA_DATA", "Animation sounds", 8, (
        Field("code", 0x00, "u32", "Event code", "1000 and up, as written in a .ga event track."),
        Field("cue", 0x04, LABEL, "Sound"),
    ), "Animation event codes from 1000 up and the sound each plays. The game searches the rows by "
       "code (binary search, RFEE01 0x800f14b4): keep them in ascending order."),
    Table("SND_CHAPTER_GROUP_DATA", "Chapter sound groups", 0x10, (
        Field("chapter", 0x00, LABEL, "Chapter"),
        Field("flag", 0x04, LABEL, "Event flag", "A flag name; empty: no flag test."),
        Field("flag_state", 0x08, "u8", "Flag state"),
        Field("group", 0x0C, LABEL, "BRSAR group", "The sound group loaded for the chapter (SND_GROUP_*)."),
    ), "The sound group each chapter loads (RFEE01 0x800680d0)."),
)}


def _label(data: bytes, pointer: int) -> str:
    if not pointer:
        return ""
    at = HEADER_SIZE + pointer
    end = data.find(b"\0", at)
    if not 0 <= at < len(data) or end < 0:
        raise SoundTableError(f"String pointer {pointer:#x} is outside the file.")
    return data[at:end].decode("shift_jis", errors="replace")


def read_fields(data: bytes, at: int, fields) -> dict:
    """The values of ``fields`` in the record at absolute offset ``at``."""
    values = read_numbers(data, at, fields)
    for f in fields:
        if f.kind == LABEL:
            values[f.key] = _label(data, struct.unpack_from(">I", data, at + f.offset)[0])
    return {f.key: values[f.key] for f in fields}


def write_fields(data: bytes, at: int, fields, values: dict) -> bytes:
    """``data`` with the record at absolute ``at`` given ``values`` (field key -> value)."""
    data = write_numbers(data, at, fields, values)
    by_key = {f.key: f for f in fields}
    for key, value in values.items():
        field = by_key[key]
        if field.kind != LABEL:
            continue
        text = (value or "").strip()
        if text == read_fields(data, at, (field,))[key]:
            continue
        data = fe8data._patch_label_field(data, at + field.offset, text or None, append=True)
    return data


# -- cues ----------------------------------------------------------------------------------------

def cue_parameters(data: bytes, cue_name: str) -> dict:
    cue = _cue(data, cue_name)
    return read_fields(data, HEADER_SIZE + cue.record_offset, CUE_PARAMETERS)


def set_cue_parameters(data: bytes, cue_name: str, **values) -> bytes:
    """``data`` with cue ``cue_name``'s parameters changed (see :data:`CUE_PARAMETERS`)."""
    cue = _cue(data, cue_name)
    out = write_fields(data, HEADER_SIZE + cue.record_offset, CUE_PARAMETERS, values)
    if fe10_sound.cue_map(out)[cue_name].resource != cue.resource:
        raise SoundTableError("The cue did not validate.")
    return out


def _cue(data: bytes, cue_name: str) -> fe10_sound.Fe10SoundCue:
    try:
        return fe10_sound.cue_map(data)[cue_name]
    except KeyError:
        raise SoundTableError(f"Unknown sound cue {cue_name}.") from None


# -- SND_* tables --------------------------------------------------------------------------------

def _table(name: str) -> Table:
    try:
        return TABLES[name]
    except KeyError:
        raise SoundTableError(f"No editable table {name}.") from None


def table_start(data: bytes, name: str) -> int:
    """Absolute offset of ``name``'s count word."""
    offset = fe8data.symbol_offsets(data).get(name)
    if offset is None:
        raise SoundTableError(f"This sound-data file has no {name}.")
    return HEADER_SIZE + offset


def row_count(data: bytes, name: str) -> int:
    return struct.unpack_from(">I", data, table_start(data, name))[0]


def row_offset(data: bytes, name: str, index: int) -> int:
    count = row_count(data, name)
    if not 0 <= index < count:
        raise SoundTableError(f"{name} has {count} rows.")
    return table_start(data, name) + 4 + index * _table(name).row_size


def read_rows(data: bytes, name: str) -> list[dict]:
    table = _table(name)
    start = table_start(data, name) + 4
    return [read_fields(data, start + i * table.row_size, table.fields) for i in range(row_count(data, name))]


def _raw_rows(data: bytes, name: str) -> list[bytes]:
    size = _table(name).row_size
    start = table_start(data, name) + 4
    return [data[start + i * size:start + (i + 1) * size] for i in range(row_count(data, name))]


def _place_rows(data: bytes, name: str, rows: list[bytes]) -> bytes:
    """``data`` with table ``name`` rewritten at the end of the data section as ``rows`` (raw), its
    export moved there. Every non-null text field goes on the pointer list (the loader relocates it)."""
    table = _table(name)
    block = struct.pack(">I", len(rows)) + b"".join(rows)
    pointer_fields = [4 + i * table.row_size + f.offset for i, row in enumerate(rows) for f in table.fields
                      if f.kind == LABEL and struct.unpack_from(">I", row, f.offset)[0]]
    out, moved = fe8data.append_block(data, block, pointer_fields)
    out = _move_export(out, name, moved)
    if _raw_rows(out, name) != rows:
        raise SoundTableError("The table did not move.")
    return out


def _sorted(data: bytes, name: str) -> bytes:
    """Tables the game binary-searches stay in ascending order of their key."""
    key = SORT_KEYS.get(name)
    if key is None:
        return data
    rows = read_rows(data, name)
    order = sorted(range(len(rows)), key=lambda i: rows[i][key])
    if order == list(range(len(rows))):
        return data
    raw = _raw_rows(data, name)
    return _place_rows(data, name, [raw[i] for i in order])


#: table -> the field its rows are sorted by
SORT_KEYS = {"SND_SFX_MAYA_DATA": "code"}


def set_row(data: bytes, name: str, index: int, **values) -> bytes:
    """``data`` with row ``index`` of ``name`` changed. In a sorted table (:data:`SORT_KEYS`) a row
    whose key moves it out of order is put back in place (the table is rewritten)."""
    out = write_fields(data, row_offset(data, name, index), _table(name).fields, values)
    read_rows(out, name)
    return _sorted(out, name)


def add_row(data: bytes, name: str, copy_of: Optional[int] = None) -> tuple[bytes, int]:
    """``data`` with a copy of row ``copy_of`` (default: the last) added at the end of ``name``; returns
    the new file and the new row's index. The table is rewritten at the end of the data section."""
    raw = _raw_rows(data, name)
    source = len(raw) - 1 if copy_of is None else copy_of
    row_offset(data, name, source)  # range check
    if name in SORT_KEYS:  # the copy goes right after its source
        return _place_rows(data, name, raw[:source + 1] + [raw[source]] + raw[source + 1:]), source + 1
    return _place_rows(data, name, raw + [raw[source]]), len(raw)


def remove_row(data: bytes, name: str, index: int) -> bytes:
    """``data`` without row ``index`` of ``name``: the rows after it move up one place, in place, and the
    count drops by one (the last row's old bytes stay behind, unread)."""
    table = _table(name)
    count = row_count(data, name)
    row_offset(data, name, index)  # range check
    if count <= 1:
        raise SoundTableError("A table keeps at least one row.")
    start = table_start(data, name) + 4
    out = bytearray(data)
    listed = fe8data.listed_pointer_fields(data)
    labels = [f.offset for f in table.fields if f.kind == LABEL]
    for i in range(index, count - 1):  # shift each later row's bytes and its pointer-list entries
        src, dst = start + (i + 1) * table.row_size, start + i * table.row_size
        out[dst:dst + table.row_size] = data[src:src + table.row_size]
    pointers = set(listed)
    for i in range(index, count):
        for offset in labels:
            pointers.discard(start + i * table.row_size + offset)
    for i in range(index, count - 1):
        for offset in labels:
            if start + (i + 1) * table.row_size + offset in listed:
                pointers.add(start + i * table.row_size + offset)
    struct.pack_into(">I", out, start - 4, count - 1)
    out = fe8data.write_pointer_list(out, [p - HEADER_SIZE for p in pointers])
    read_rows(bytes(out), name)
    return bytes(out)


def _move_export(data: bytes, name: str, offset: int) -> bytes:
    symbols = fe10_sound._raw_symbols(data)
    key = name.encode("ascii")
    if key not in {symbol for _o, symbol in symbols}:
        raise SoundTableError(f"No export {name}.")
    return fe10_sound._set_symbols(data, [(offset if symbol == key else o, symbol) for o, symbol in symbols])
