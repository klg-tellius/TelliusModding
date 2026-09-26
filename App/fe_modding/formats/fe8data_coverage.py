"""Byte-coverage map of ``FE8Data.bin``: which bytes have a known meaning.

Every byte of the file gets one status:

- ``decoded``: a field with a confirmed (or strongly evidenced) meaning, a
  string the data points at, or container structure;
- ``plausible``: a named field whose meaning is still only a guess;
- ``undecoded``: no known meaning;
- ``reserved``: a field the format has room for but that no code in
  ``main.dol`` reads (checked over every load of that record offset); its
  vanilla values are documented but have no effect in game;
- ``padding``: alignment or a confirmed unread gap.

The layouts below mirror ``FE8DATA_NOTES.md`` and ``SUPPORT_NOTES.md``; a
field changes status here when it changes confidence there. Sections are
found through the container's symbol table, so a rebuilt file works too.

Run ``python -m fe_modding.formats.fe8data_coverage FE8Data.bin`` for the
per-section summary and ``--ranges`` for every undecoded range.
"""

from __future__ import annotations

import argparse
import re
import struct
from dataclasses import dataclass
from pathlib import Path

from . import fe8data

DECODED, PLAUSIBLE, UNDECODED, RESERVED, PADDING = "decoded", "plausible", "undecoded", "reserved", "padding"
STATUSES = (DECODED, PLAUSIBLE, UNDECODED, RESERVED, PADDING)

# (offset, size, name, status) per record; anything not listed is undecoded.
CHARACTER_FIELDS = (
    (0x00, 4, "pid", DECODED), (0x04, 4, "mpid", DECODED), (0x08, 4, "unused_08", RESERVED),
    (0x0C, 4, "fid", DECODED),
    (0x10, 4, "jid", DECODED), (0x14, 4, "affinity", DECODED), (0x18, 4, "weapon_ranks", DECODED),
    (0x1C, 12, "skills", DECODED), (0x28, 4, "aid_unpromoted", DECODED), (0x2C, 4, "aid_promoted", DECODED),
    (0x30, 2, "roster_order", DECODED), (0x32, 2, "biorhythm_pattern", DECODED),
    (0x34, 1, "start_transform_gauge", DECODED), (0x35, 1, "biorhythm_phase", DECODED),
    (0x36, 1, "level", DECODED), (0x37, 1, "build", DECODED),
    (0x38, 1, "weight", DECODED), (0x39, 8, "stat_bonus", DECODED), (0x41, 8, "growth", DECODED),
    (0x49, 8, "fixed_growth_start", DECODED), (0x51, 3, "align", PADDING),
)
CLASS_FIELDS = (
    (0x00, 4, "jid", DECODED), (0x04, 4, "mjid", PLAUSIBLE), (0x08, 4, "description_key", DECODED),
    (0x0C, 4, "promotes_to", DECODED), (0x10, 4, "innate_weapon", DECODED),
    (0x14, 4, "weapon_ranks", DECODED), (0x18, 20, "skills", DECODED), (0x2C, 12, "category_tokens", DECODED),
    (0x38, 4, "aid", DECODED), (0x3C, 2, "build_weight", DECODED), (0x3E, 1, "movement", DECODED),
    (0x3F, 1, "unread_3f", RESERVED), (0x40, 1, "skill_capacity", DECODED), (0x41, 1, "vision", DECODED),
    (0x42, 1, "movement_type", DECODED), (0x43, 1, "unread_43", RESERVED),
    (0x44, 8, "base_stats", DECODED), (0x4C, 8, "stat_caps", DECODED),
    (0x54, 8, "growths", DECODED), (0x5C, 8, "growth_modifiers", DECODED),
)  # 0x3F and 0x43 are copied by the loader but never read
ITEM_FIELDS = ((0x00, 0x5E, "item", DECODED), (0x5E, 2, "padding", PADDING))
SKILL_FIELDS = (
    (0x00, 4, "sid", DECODED), (0x04, 4, "japanese_name", DECODED), (0x08, 4, "msid", DECODED),
    (0x0C, 8, "help_keys", DECODED), (0x14, 4, "effect", DECODED), (0x18, 1, "self_index", DECODED),
    (0x19, 1, "icon", DECODED), (0x1A, 1, "capacity_cost", DECODED), (0x1B, 1, "has_scroll", RESERVED),
    (0x1C, 1, "restriction_count", DECODED), (0x1D, 3, "unread_1d", RESERVED),
    (0x20, 4, "scroll_list", DECODED), (0x24, 4, "restriction_list", DECODED),
)
# The support readers use +0x04-0x09 of a DivineData row, +0x00-0x09 of a
# KiznaData record and bytes 0-6 of a RelianceData slot; the rest pads the
# stride to a word (zero everywhere).
DIVINE_FIELDS = ((0x00, 10, "affinity_row", DECODED), (0x0A, 2, "pad", PADDING))
RELIANCE_SLOT_FIELDS = ((0x00, 7, "slot", DECODED), (0x07, 1, "pad", PADDING))
KIZNA_FIELDS = ((0x00, 10, "bond", DECODED), (0x0A, 2, "pad", PADDING))
# Byte 23 is 0 in every block, past the last movement-cost column (8 + 14).
TERRAIN_BLOCK_FIELDS = ((0x00, 23, "terrain_stats", DECODED), (0x17, 1, "pad", PADDING))
TERRAIN_BLOCK_SIZE = 24
CHAPTER_FIELDS = (
    (0x00, 4, "title_key", DECODED), (0x04, 0x38, "names_objectives", DECODED), (0x3C, 1, "chapter_id", DECODED),
    (0x3D, 4, "enemy_bonus_levels", DECODED), (0x41, 3, "align", PADDING),
    (0x44, 0x1C, "backgrounds_trial_grades", DECODED),
)


@dataclass
class Span:
    start: int
    end: int  # exclusive
    section: str
    status: str
    name: str = ""


class CoverageMap:
    def __init__(self, data: bytes):
        self.data = data
        self.status = [UNDECODED] * len(data)
        self.name = [""] * len(data)
        self.section = [""] * len(data)
        #: section -> (first record, record size, count) for fixed-stride tables
        self.tables: dict[str, tuple[int, int, int]] = {}

    def mark(self, start: int, size: int, status: str, name: str = "") -> None:
        for i in range(max(start, 0), min(start + size, len(self.data))):
            self.status[i] = status
            self.name[i] = name

    def mark_fields(self, base: int, fields, prefix: str = "") -> None:
        for offset, size, name, status in fields:
            self.mark(base + offset, size, status, prefix + name)

    def spans(self) -> list[Span]:
        """Runs of bytes with the same section, status and field name."""
        result = []
        for i, key in enumerate(zip(self.section, self.status, self.name)):
            if result and (result[-1].section, result[-1].status, result[-1].name) == key and result[-1].end == i:
                result[-1].end = i + 1
            else:
                result.append(Span(i, i + 1, *key))
        return result

    def undecoded_ranges(self) -> list[Span]:
        """Merged undecoded runs of one section and field name."""
        result = []
        for i, (section, status, name) in enumerate(zip(self.section, self.status, self.name)):
            if status != UNDECODED:
                continue
            if result and result[-1].end == i and (result[-1].section, result[-1].name) == (section, name):
                result[-1].end = i + 1
            else:
                result.append(Span(i, i + 1, section, UNDECODED, name))
        return result

    def grouped_undecoded(self) -> list[tuple[str, int, int, int, bool]]:
        """Undecoded ranges, ``(section, start, end, occurrences, relative)``.
        Inside a fixed-stride table the ranges are folded to record-relative
        offsets (``relative`` true) and counted over the records."""
        grouped: dict[tuple[str, int, int], int] = {}
        loose: list = []
        named: dict[tuple[str, str, int], list] = {}
        for span in self.undecoded_ranges():
            first, size, count = self.tables.get(span.section, (0, 0, 0))
            if not (size and first <= span.start and span.end <= first + size * count):
                if span.name:  # a named field repeated in variable-length records
                    key = (span.section, re.sub(r"\[\d+\]", "", span.name), span.end - span.start)
                    if key in named:
                        named[key][3] += 1
                        continue
                    named[key] = [span.section, span.start, span.end, 1, False]
                    loose.append(named[key])
                else:
                    loose.append([span.section, span.start, span.end, 1, False])
                continue
            pos = span.start
            while pos < span.end:  # split at record boundaries
                rel = (pos - first) % size
                stop = min(span.end, pos + size - rel)
                key = (span.section, rel, rel + stop - pos)
                grouped[key] = grouped.get(key, 0) + 1
                pos = stop
        rows = [(section, start, end, n, True) for (section, start, end), n in grouped.items()]
        return sorted(rows + [tuple(r) for r in loose], key=lambda r: (r[0], r[1]))

    def summary(self) -> dict[str, dict[str, int]]:
        """Byte counts per section and status, sections in file order."""
        result: dict[str, dict[str, int]] = {}
        for section, status in zip(self.section, self.status):
            counts = result.setdefault(section, dict.fromkeys(STATUSES, 0))
            counts[status] += 1
        return result


def _u32(data: bytes, offset: int) -> int:
    return struct.unpack_from(">I", data, offset)[0]


def _sections(data: bytes) -> list[tuple[str, int, int]]:
    """(name, start, end) of each data-area section, absolute offsets. The
    per-skill ``SID_`` symbols name records inside ``SkillData``, not
    sections."""
    data_end = fe8data.HEADER_SIZE + _u32(data, 4)
    symbols = sorted(
        (offset + fe8data.HEADER_SIZE, name)
        for name, offset in fe8data.symbol_offsets(data).items()
        if not name.startswith("SID_")
    )
    return [(name, start, symbols[i + 1][0] if i + 1 < len(symbols) else data_end)
            for i, (start, name) in enumerate(symbols)]


def _mark_table(cov: CoverageMap, start: int, record_size: int, fields, label: str) -> int:
    """A count word then ``count`` fixed-size records; returns the end offset."""
    count = _u32(cov.data, start)
    cov.mark(start, 4, DECODED, "count")
    cov.tables[cov.section[start]] = (start + 4, record_size, count)
    for i in range(count):
        cov.mark_fields(start + 4 + i * record_size, fields, f"{label}[{i}].")
    return start + 4 + count * record_size


def _mark_skill_lists(cov: CoverageMap, skills_start: int) -> None:
    """Each skill's one-entry scroll list (+0x20) and its restriction list
    (+0x24, +0x1C labels)."""
    count = _u32(cov.data, skills_start)
    for i in range(count):
        rec = skills_start + 4 + i * fe8data.SKILL_RECORD_SIZE
        scroll, restriction, length = _u32(cov.data, rec + 0x20), _u32(cov.data, rec + 0x24), cov.data[rec + 0x1C]
        if scroll:
            cov.mark(scroll + fe8data.HEADER_SIZE, 4, DECODED, f"skill[{i}].scroll")
        if restriction and length:
            cov.mark(restriction + fe8data.HEADER_SIZE, 4 * length, DECODED, f"skill[{i}].restriction_list")


def _mark_reliance(cov: CoverageMap, start: int, end: int) -> int:
    data = cov.data
    count = _u32(data, start)
    cov.mark(start, 4, DECODED, "count")
    pos = start + 4
    for i in range(count):
        if pos + 8 > end:
            break
        slots = data[pos + 7]  # the engine reads the low byte of the slot count
        cov.mark(pos, 8, DECODED, f"reliance[{i}].header")
        for s in range(slots):
            cov.mark_fields(pos + 8 + s * 8, RELIANCE_SLOT_FIELDS, f"reliance[{i}].slot[{s}].")
        pos += 8 + slots * 8
    return pos


def _mark_kizna(cov: CoverageMap, start: int) -> int:
    end = _mark_table(cov, start, 12, KIZNA_FIELDS, "bond")
    if _u32(cov.data, end) == 0:
        cov.mark(end, 4, DECODED, "terminator")
        end += 4
    return end


def _mark_terrain(cov: CoverageMap, start: int, end: int) -> None:
    """A zero word (the engine walks a fixed 77 records past it), the 77
    records, a zero terminator, then 24-byte stats blocks up to the next
    section. Blocks no record points at are well-formed dead data."""
    data = cov.data
    cov.mark(start, 4, PADDING, "unused_count")
    records = start + 4
    blocks = set()
    for i in range(fe8data.TERRAIN_TYPE_COUNT):
        rec = records + 12 * i
        cov.mark(rec, 12, DECODED, f"terrain[{i}]")
        block = _u32(data, rec + 8)
        if block:
            blocks.add(block + fe8data.HEADER_SIZE)
    first_block = records + 12 * fe8data.TERRAIN_TYPE_COUNT
    if _u32(data, first_block) == 0:
        cov.mark(first_block, 4, PADDING, "terminator")
        first_block += 4
    for block in range(first_block, end - TERRAIN_BLOCK_SIZE + 1, TERRAIN_BLOCK_SIZE):
        name = "stats_block." if block in blocks else "unreferenced_stats_block."
        cov.mark_fields(block, TERRAIN_BLOCK_FIELDS, name)
    for block in blocks:
        cov.mark_fields(block, TERRAIN_BLOCK_FIELDS, "stats_block.")


def _mark_strings(cov: CoverageMap, pool_start: int, pool_end: int) -> None:
    """Pointer targets inside the string pool are strings up to their NUL.
    Zero bytes between strings are padding; other unreached runs are left
    undecoded (candidate orphan strings)."""
    data = cov.data
    targets = sorted({
        _u32(data, field) + fe8data.HEADER_SIZE
        for field in fe8data.listed_pointer_fields(data)
        if field + 4 <= len(data)
    })
    for target in targets:
        if not pool_start <= target < pool_end:
            continue
        end = data.find(b"\x00", target, pool_end)
        end = pool_end if end < 0 else end + 1
        cov.mark(target, end - target, DECODED, "string")
    for i in range(pool_start, pool_end):
        if cov.status[i] == UNDECODED and data[i] == 0:
            cov.mark(i, 1, PADDING, "padding")
    # Unreached NUL-terminated runs are dead strings (AID_FIGHTER_BOX...).
    i = pool_start
    while i < pool_end:
        if cov.status[i] != UNDECODED:
            i += 1
            continue
        end = data.find(b"\x00", i, pool_end)
        end = pool_end if end < 0 else end + 1
        cov.mark(i, end - i, DECODED, "unreferenced_string")
        i = end


def build_coverage(data: bytes) -> CoverageMap:
    cov = CoverageMap(data)
    size, data_size, pointer_count, symbol_count = struct.unpack_from(">IIII", data, 0)
    data_end = fe8data.HEADER_SIZE + data_size
    pointers_end = data_end + 4 * pointer_count
    symbols_end = pointers_end + 8 * symbol_count

    for i in range(len(data)):
        cov.section[i] = "(tail)"
    for i in range(fe8data.HEADER_SIZE):
        cov.section[i] = "(header)"
    # HSDArc header: sizes, relocation count, export count, then the import
    # count (+0x10), an unread word (+0x14), and 8 bytes load_relocatable_resource
    # writes in RAM: the "HSDArc" relocated stamp (+0x18-0x1E) and the
    # symbols-registered flag (+0x1F). Zero on disc.
    cov.mark(0, 0x14, DECODED, "header")
    cov.mark(0x14, 4, RESERVED, "header_unread_14")
    cov.mark(0x18, 8, DECODED, "header_runtime_stamp")
    for i in range(data_end, pointers_end):
        cov.section[i] = "(pointer list)"
    cov.mark(data_end, pointers_end - data_end, DECODED, "pointer_list")
    for i in range(pointers_end, symbols_end):
        cov.section[i] = "(symbol table)"
    cov.mark(pointers_end, symbols_end - pointers_end, DECODED, "symbol_table")
    for i in range(symbols_end, len(data)):
        cov.section[i] = "(symbol names)"
    cov.mark(symbols_end, len(data) - symbols_end, DECODED, "symbol_names")

    sections = _sections(data)
    content_ends: dict[str, int] = {}
    for name, start, end in sections:
        for i in range(start, end):
            cov.section[i] = name
        content_end = start
        if name == "DatabaseHead":
            # word 0 is 0 and off the pointer list (the loader starts at +4);
            # words 1-2 point at the build time ("2005/06/29 10:11:21") and the
            # author ("金子", Kaneko)
            cov.mark(start, 4, RESERVED, "unread_word0")
            cov.mark(start + 4, 8, DECODED, "build_time_author")
        elif name == "PersonData":
            content_end = _mark_table(cov, start, fe8data.CHARACTER_RECORD_SIZE, CHARACTER_FIELDS, "character")
        elif name == "JobData":
            content_end = _mark_table(cov, start, fe8data.CLASS_RECORD_SIZE, CLASS_FIELDS, "class")
        elif name == "ItemData":
            content_end = _mark_table(cov, start, fe8data.ITEM_RECORD_SIZE, ITEM_FIELDS, "item")
        elif name == "SkillData":
            content_end = _mark_table(cov, start, fe8data.SKILL_RECORD_SIZE, SKILL_FIELDS, "skill")
            _mark_skill_lists(cov, start)
        elif name == "DivineData":
            content_end = _mark_table(cov, start, 12, DIVINE_FIELDS, "affinity")
        elif name == "GameData":
            cov.mark(start, 28, DECODED, "difficulty_rows")
            content_end = start + 28
        elif name == "TerrainData":
            _mark_terrain(cov, start, end)
        elif name == "BattleTerrData":
            columns, rows = struct.unpack_from(">HH", data, start)
            cov.mark(start, 4 + rows * (columns + 1) * 4, DECODED, "battle_terrain")
        elif name == "BattleSkyData":
            cov.mark(start, 1, DECODED, "count")
            cov.mark(start + 1, 3, PADDING, "pad")
            cov.mark(start + 4, 4 * data[start], DECODED, "sky_names")
        elif name == "ChapterData":
            content_end = _mark_table(cov, start, fe8data.CHAPTER_RECORD_SIZE, CHAPTER_FIELDS, "chapter")
        elif name == "GroupData":
            cov.mark(start, 4 + 4 * _u32(data, start), DECODED, "group_names")
        elif name == "RelianceData":
            content_end = _mark_reliance(cov, start, end)
        elif name == "KiznaData":
            content_end = _mark_kizna(cov, start)
        content_ends[name] = max(content_end, start)
    # The string pool follows KiznaData in the vanilla layout. A section the
    # app grew moves past the pool (fe8data.replace_section), so the pool is
    # bounded by the first string a pointer names and the next section.
    strings = [_u32(data, f) + fe8data.HEADER_SIZE for f in fe8data.listed_pointer_fields(data)
               if f + 4 <= len(data) and fe8data._resolve(data, _u32(data, f)) is not None]
    first_string = min(strings, default=data_end)
    pool_start = content_ends.get("KiznaData", first_string)
    if pool_start > first_string:
        pool_start = first_string
    pool_end = min([start for _name, start, _end in sections if start > pool_start] + [data_end])
    for i in range(pool_start, pool_end):
        cov.section[i] = "(string pool)"
    _mark_strings(cov, pool_start, data_end)
    # the zeroed place of a moved section, and the room left after a moved table
    for i in range(fe8data.HEADER_SIZE, data_end):
        if cov.status[i] == UNDECODED and data[i] == 0:
            cov.mark(i, 1, PADDING, "free")
    return cov


def format_summary(cov: CoverageMap) -> str:
    rows = [f"{'section':<16}{'bytes':>8}{'decoded':>9}{'plaus.':>8}{'undec.':>8}{'resv.':>7}{'pad':>6}"]
    totals = dict.fromkeys(STATUSES, 0)
    for section, counts in cov.summary().items():
        for k in STATUSES:
            totals[k] += counts[k]
        rows.append(f"{section:<16}{sum(counts.values()):>8}{counts[DECODED]:>9}"
                    f"{counts[PLAUSIBLE]:>8}{counts[UNDECODED]:>8}{counts[RESERVED]:>7}{counts[PADDING]:>6}")
    total = sum(totals.values())
    rows.append(f"{'TOTAL':<16}{total:>8}{totals[DECODED]:>9}{totals[PLAUSIBLE]:>8}"
                f"{totals[UNDECODED]:>8}{totals[RESERVED]:>7}{totals[PADDING]:>6}")
    rows.append(f"undecoded: {100 * totals[UNDECODED] / total:.2f} %, "
                f"plausible: {100 * totals[PLAUSIBLE] / total:.2f} %, "
                f"reserved: {100 * totals[RESERVED] / total:.2f} %")
    return "\n".join(rows)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("path", type=Path)
    parser.add_argument("--ranges", action="store_true", help="list every undecoded range")
    args = parser.parse_args()
    cov = build_coverage(args.path.read_bytes())
    print(format_summary(cov))
    if args.ranges:
        print("\nundecoded ranges (table rows as record offset +x, times the records it occurs in):")
        for section, start, end, n, relative in cov.grouped_undecoded():
            where = f"+{start:#04x}..+{end - 1:#04x}" if relative else f"{start:#07x}..{end - 1:#07x}"
            print(f"  {section:<16}{where:<18}{end - start:>6} B  x{n}")


if __name__ == "__main__":
    main()
