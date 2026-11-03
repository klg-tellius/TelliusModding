"""Byte-coverage map of Radiant Dawn's ``FE10Data.cms`` (decompressed): which bytes have a known meaning.

The statuses and the map are :mod:`fe8data_coverage`'s (``decoded``, ``plausible``, ``undecoded``,
``reserved``, ``padding``). The records come from :mod:`fe10data` itself, so the map follows the
parser: a field the parser names is decoded, a field it calls ``unknown_*`` is undecoded, and the
fields listed in ``PLAUSIBLE_FIELDS`` are named but not confirmed. Bytes no record reaches stay
undecoded, so a gap the layouts miss shows up here. ``research/rd/FE10DATA_NOTES.md`` holds the
field facts; ``research/rd/FE10DATA_DECODE_PLAN.md`` the work still open.

Run ``python -m fe_modding.formats.fe10data_coverage FE10Data.cms`` (compressed or not) for the
per-section summary and ``--ranges`` for every undecoded range.
"""

from __future__ import annotations

import argparse
import struct
from pathlib import Path

from . import fe8data, fe10data, lz10
from .fe8data import HEADER_SIZE
from .fe8data_coverage import (DECODED, PADDING, PLAUSIBLE, RESERVED, UNDECODED, CoverageMap,
                               format_summary)

_SIZES = {"label": 4, "u32": 4, "f32": 4, "u16": 2, "s8": 1, "u8": 1}

#: Named fields whose meaning is still a guess.
PLAUSIBLE_FIELDS = {
    "skill": {"capacity", "icon"},
    "support_param": {"gain_0", "gain_0_flag", "gain_1", "gain_2", "gain_3", "gain_4", "gain_5"},
    "class": {"weight_kind_1", "weight_kind_2"},  # the kind numbers are named from the retail classes only
    "chapter": {"move_change", "preparations"},  # class types / modes not resolved
}
#: Fields that only pad a record to a word (zero everywhere, a word field follows, the loader skips them).
ALIGNMENT_FIELDS = {"character": {"unknown_t27"}, "skill": {"unknown_22", "unknown_23"},
                    "item": {"pad_13", "pad_14", "pad_15"}}
#: Fields the loader does not copy.
UNREAD_FIELDS = {"character": {"unused_01"}}


def _u32(data: bytes, offset: int) -> int:
    return struct.unpack_from(">I", data, offset)[0]


def _status(kind: str, key: str) -> str:
    if key in ALIGNMENT_FIELDS.get(kind, ()):
        return PADDING
    if key in UNREAD_FIELDS.get(kind, ()):
        return RESERVED
    if key.startswith("unknown"):
        return UNDECODED
    return PLAUSIBLE if key in PLAUSIBLE_FIELDS.get(kind, ()) else DECODED


def _mark_record(cov: CoverageMap, r: fe10data.Record, defs: dict) -> None:
    """The scalar and label fields of one record."""
    for key, offset in r.offsets.items():
        definition = defs.get(key)
        if definition is None or key in r.lists:
            continue
        cov.mark(offset, _SIZES[definition.kind], _status(r.kind, key), f"{r.kind}.{key}")


def _mark_count(cov: CoverageMap, data: bytes, kind: str) -> None:
    cov.mark(fe10data._count_offset(data, kind), 4, DECODED, f"{kind}.count")


def _pad(cov: CoverageMap, offset: int, size: int, name: str) -> None:
    """Zero bytes that fill a record out to a word; anything else stays undecoded."""
    if any(cov.data[offset:offset + size]):
        cov.mark(offset, size, UNDECODED, name)
    else:
        cov.mark(offset, size, PADDING, name)


def _mark_variable_tables(cov: CoverageMap, data: bytes) -> None:
    for kind in ("character", "class", "item"):
        defs = {d.key: d for d in fe10data.field_defs(kind)}
        defs.update({k: fe10data.FieldDef(k, k, "u8") for k in fe10data.COUNT_FIELDS})
        _mark_count(cov, data, kind)
        for r in fe10data.read_table(data, kind):
            _mark_record(cov, r, defs)
            for key, labels in r.lists.items():
                cov.mark(r.offsets[key], 4 * len(labels), DECODED, f"{kind}.{key}")
            if kind == "class":  # +13..+15 of the fixed block, skipped by the loader
                _pad(cov, r.offsets["unknown_0c"] + 1, fe10data.CLASS_FIXED_PADDING, "class.pad")
            if kind == "item" and r.bonuses is not None:
                at = r.offsets["bonuses"]
                cov.mark(at, len(fe10data.BONUS_NAMES), DECODED, "item.bonuses")
                _pad(cov, at + len(fe10data.BONUS_NAMES), fe10data.BONUS_BLOCK_SIZE - len(fe10data.BONUS_NAMES),
                     "item.bonuses_pad")


def _mark_skills(cov: CoverageMap, data: bytes) -> None:
    defs = {d.key: d for d in fe10data.field_defs("skill")}
    defs.update({k: fe10data.FieldDef(k, k, "u8") for k in fe10data.COUNT_FIELDS})
    _mark_count(cov, data, "skill")
    for r in fe10data.read_table(data, "skill"):
        _mark_record(cov, r, defs)
        for key in ("conditions", "requirements"):
            cov.mark(r.offsets[key], 4, DECODED, f"skill.{key}_pointer")
            target = _u32(data, r.offsets[key])
            for i in range(len(r.lists[key]) if target else 0):
                at = HEADER_SIZE + target + 8 * i
                cov.mark(at, 1, DECODED, f"skill.{key}.mode")
                _pad(cov, at + 1, 3, f"skill.{key}.pad")
                cov.mark(at + 4, 4, DECODED, f"skill.{key}.label")


def _mark_fixed_tables(cov: CoverageMap, data: bytes) -> None:
    for kind, table in fe10data.FIXED_TABLES.items():
        defs = {d.key: d for d in table.fields}
        if table.counted:
            _mark_count(cov, data, kind)
        for r in fe10data.read_table(data, kind):
            _mark_record(cov, r, defs)
            if kind == "difficulty" and r.index in (10, 11):  # no getter found for these two rows
                cov.mark(r.start, table.size, UNDECODED, "difficulty.row_without_reader")
            if kind == "terrain":
                cov.mark(r.start + 0x0C, 4, DECODED, "terrain.block")
            own = [d for d in table.fields if kind != "terrain" or d.key not in fe10data.TERRAIN_FIELDS]
            covered = {o for d in own for o in range(d.offset, d.offset + _SIZES[d.kind])} | (
                set(range(0x0C, 0x10)) if kind == "terrain" else set())
            for o in range(table.size):
                if o in covered:
                    continue
                word = o - o % 4
                if kind == "biorhythm_band":  # build_biorhythm_bonus_vector copies +4..+8 only
                    cov.mark(r.start + o, 1, RESERVED, f"{kind}.unread")
                elif word in covered and not covered & set(range(o, word + 4)):
                    _pad(cov, r.start + o, 1, f"{kind}.pad")  # the rest of a word that starts with a field
                else:
                    cov.mark(r.start + o, 1, UNDECODED, f"{kind}.+{word:#04x}")
        if kind == "terrain":
            _mark_terrain_blocks(cov, data)
            # the engine uses exactly 199 types (0x8011d17c); the bytes after them up to BattleTerrIndex are unread
            records = fe10data.read_table(data, kind)
            tail = fe8data.section_start(data, "BattleTerrIndex")
            if records and len(records) == 199:
                cov.mark(records[-1].end, tail - records[-1].end, RESERVED, "terrain.after_199")
        if kind == "bond":  # a null word ends the bonds (as on Path of Radiance)
            records = fe10data.read_table(data, kind)
            end = records[-1].end if records else fe8data.section_start(data, table.symbol) + 4
            if end + 4 <= len(data) and _u32(data, end) == 0:
                cov.mark(end, 4, DECODED, "bond.terminator")


def _mark_terrain_block(cov: CoverageMap, block: int, name: str) -> None:
    for d in fe10data.TERRAIN_BLOCK_FIELDS:
        cov.mark(block + d.offset, _SIZES[d.kind], DECODED, f"{name}.{d.key}")
    last = 0x14 + fe10data.MOVE_COST_COUNT
    _pad(cov, block + last, fe10data.TERRAIN_BLOCK_SIZE - last, f"{name}.pad")


def _mark_terrain_blocks(cov: CoverageMap, data: bytes) -> None:
    """The shared stats blocks, after GameData's rows. Blocks on the same 0x2C grid that no terrain
    type points at are well-formed dead data (as on Path of Radiance)."""
    used = {HEADER_SIZE + r.values["block"] for r in fe10data.read_table(data, "terrain") if r.values["block"]}
    for block in used:
        _mark_terrain_block(cov, block, "terrain_block")
    if not used:
        return
    first, end = min(used), fe8data.section_start(data, "TerrainData")
    for block in range(first, end - fe10data.TERRAIN_BLOCK_SIZE + 1, fe10data.TERRAIN_BLOCK_SIZE):
        if block not in used and all(cov.status[i] == UNDECODED for i in range(block, block + fe10data.TERRAIN_BLOCK_SIZE)):
            _mark_terrain_block(cov, block, "unreferenced_terrain_block")


def _mark_supports(cov: CoverageMap, data: bytes) -> None:
    cov.mark(fe8data.section_start(data, "RelianceData"), 4, DECODED, "support.count")
    for r in fe10data.read_table(data, "support"):
        cov.mark(r.start, 8, DECODED, "support.header")
        for i in range(len(r.lists["partners"])):
            at = r.start + 8 + fe10data.SUPPORT_ENTRY_SIZE * i
            cov.mark(at, 6, DECODED, "support.entry")
            _pad(cov, at + 6, 2, "support.entry_pad")


def _mark_battle_scenery(cov: CoverageMap, data: bytes) -> None:
    start = fe8data.section_start(data, "BattleTerrIndex")
    types, maps = struct.unpack_from(">HH", data, start)
    cov.mark(start, 4, DECODED, "battle_scenery.counts")
    row = 4 + 2 * types
    row += -row % 4
    for i in range(maps):
        at = start + 4 + row * i
        cov.mark(at, 4 + 2 * types, DECODED, "battle_scenery.row")
        _pad(cov, at + 4 + 2 * types, row - 4 - 2 * types, "battle_scenery.row_pad")
    names = fe8data.section_start(data, "BattleTerrName")
    cov.mark(names, 4 * len(fe10data.battle_scenery_names(data)), DECODED, "battle_scenery.names")


def _mark_no_battle(cov: CoverageMap, data: bytes) -> None:
    cov.mark(fe8data.section_start(data, "NOBTL_TABLE"), 4, DECODED, "no_battle.count")
    for r in fe10data.read_table(data, "no_battle"):
        cov.mark(r.start, 4, DECODED, "no_battle.pid")
        at = r.offsets["characters"]
        for i in range(len(r.lists["characters"])):
            entry = at + fe10data.NO_BATTLE_ENTRY_SIZE * i
            cov.mark(entry, 4, DECODED, "no_battle.character")
            cov.mark(entry + 4, 1, DECODED, "no_battle.flag")
            cov.mark(entry + 5, 3, RESERVED, "no_battle.unread")  # copied with the entry, never used
        cov.mark(r.end - 4, 4, DECODED, "no_battle.terminator")


def _mark_strings(cov: CoverageMap, data: bytes, pool_start: int, pool_end: int) -> None:
    """Pointer targets are strings up to their NUL; unreached zeros are padding and unreached text an
    unreferenced string."""
    for field in fe8data.listed_pointer_fields(data):
        target = HEADER_SIZE + _u32(data, field)
        if pool_start <= target < pool_end:
            end = data.find(b"\0", target, pool_end)
            end = pool_end if end < 0 else end + 1
            cov.mark(target, end - target, DECODED, "string")
    i = pool_start
    while i < pool_end:
        if cov.status[i] != UNDECODED:
            i += 1
            continue
        if data[i] == 0:
            cov.mark(i, 1, PADDING, "padding")
            i += 1
            continue
        end = data.find(b"\0", i, pool_end)
        end = pool_end if end < 0 else end + 1
        cov.mark(i, end - i, DECODED, "unreferenced_string")
        i = end


def unreferenced_strings(cov: CoverageMap) -> list[tuple[int, str]]:
    """``(offset, text)`` of every pool string no listed pointer reaches."""
    out, i = [], 0
    while i < len(cov.data):
        if cov.name[i] == "unreferenced_string":
            j = i
            while j < len(cov.data) and cov.name[j] == "unreferenced_string" and cov.data[j]:
                j += 1
            out.append((i, cov.data[i:j].decode("shift_jis", "replace")))
            while j < len(cov.data) and cov.name[j] == "unreferenced_string":
                j += 1
            i = j
        else:
            i += 1
    return out


def build_coverage(data: bytes) -> CoverageMap:
    cov = CoverageMap(data)
    size, data_size, pointer_count, symbol_count = struct.unpack_from(">IIII", data, 0)
    data_end = HEADER_SIZE + data_size
    pointers_end = data_end + 4 * pointer_count
    symbols_end = pointers_end + 8 * symbol_count
    regions = ((0, HEADER_SIZE, "(header)"), (data_end, pointers_end, "(pointer list)"),
               (pointers_end, symbols_end, "(symbol table)"), (symbols_end, len(data), "(symbol names)"))
    for start, end, name in regions:
        for i in range(start, end):
            cov.section[i] = name
    # The container header, as FE8Data.bin's (fe8data_coverage): +0x14 unread there, +0x18..+0x1F
    # written in RAM by the loader. Not checked against RFEE01's loader yet.
    cov.mark(0, 0x14, DECODED, "header")
    cov.mark(0x14, 4, RESERVED, "header_unread_14")
    cov.mark(0x18, 8, DECODED, "header_runtime_stamp")
    cov.mark(data_end, len(data) - data_end, DECODED, "container")

    # Sections in file order; the per-skill SID_ and per-list NOBTL_ symbols name records, not sections.
    symbols = sorted((HEADER_SIZE + offset, name) for name, offset in fe8data.symbol_offsets(data).items()
                     if not name.startswith("SID_") and not (name.startswith("NOBTL_") and name != "NOBTL_TABLE"))
    for i, (start, name) in enumerate(symbols):
        end = symbols[i + 1][0] if i + 1 < len(symbols) else data_end
        for j in range(start, end):
            cov.section[j] = name

    head = fe8data.section_start(data, "DatabaseHead")
    cov.mark(head, 4, RESERVED, "database_head.word0")  # 0, off the pointer list; the loader ignores the section
    cov.mark(head + 4, 8, DECODED, "database_head.build_time_author")
    _mark_variable_tables(cov, data)
    _mark_skills(cov, data)
    _mark_fixed_tables(cov, data)
    _mark_supports(cov, data)
    _mark_battle_scenery(cov, data)
    _mark_no_battle(cov, data)

    # The string pool runs from the end of the last NOBTL list to the end of the data area.
    lists = fe10data.read_table(data, "no_battle")
    pool_start = lists[-1].end if lists else data_end
    for i in range(pool_start, data_end):
        cov.section[i] = "(string pool)"
    _mark_strings(cov, data, pool_start, data_end)
    return cov


def load(path: Path) -> bytes:
    raw = Path(path).read_bytes()
    return lz10.decompress(raw) if raw[:1] == b"\x10" else raw


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("path", type=Path)
    parser.add_argument("--ranges", action="store_true", help="list every undecoded range")
    parser.add_argument("--orphans", action="store_true", help="list the strings no pointer reaches")
    args = parser.parse_args()
    cov = build_coverage(load(args.path))
    print(format_summary(cov))
    if args.ranges:
        print("\nundecoded ranges (field, offset of the first, size, times it occurs):")
        grouped: dict[tuple[str, str, int], list] = {}
        for span in cov.undecoded_ranges():
            key = (span.section, span.name, span.end - span.start)
            grouped.setdefault(key, [span.start, 0])[1] += 1
        for (section, name, size), (first, n) in sorted(grouped.items(), key=lambda kv: kv[1][0]):
            print(f"  {section:<16}{name or '(no field)':<34}{first:#08x}{size:>6} B  x{n}")
    if args.orphans:
        for offset, text in unreferenced_strings(cov):
            print(f"  {offset:#08x} {text}")


if __name__ == "__main__":
    main()
