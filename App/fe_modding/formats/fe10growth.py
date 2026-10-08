"""Radiant Dawn's ``FE10Growth.cms``: precomputed stats per level for each character.

LZ10 around the usual data container (:mod:`fe8data`), with one symbol, ``FE10PersonGrowth``:

* a u16 record count (375 in the US file) and two zero bytes;
* per record, 12 bytes: PID pointer, u8 first level, u8 last level, two zero bytes, a pointer to
  the stat lines;
* the stat lines: one per level from first to last, eight bytes each, the absolute
  HP Str Mag Skl Spd Lck Def Res at that level.

Levels are **internal levels**: tier 1 is 1-20, tier 2 21-40, tier 3 41-60 (Ike's record runs 31-60,
from Hero level 11, his level in ``FE10Data.cms``, to Vanguard level 20; a laguz runs 1-40).
A unit's **starting** stats do not come from here: they are the class bases plus the character's
bonuses in ``FE10Data.cms`` (checked in game: Micaiah's level-1 line set to HP 25 left her at the
FE10Data value). What the game reads these lines for is not established yet.

A few records share one block of lines (the tutorial's ``PID_TUT_*`` duplicates), so editing a
shared line changes each of them; :func:`sharing` names them.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass
from typing import Sequence

from . import fe8data
from .fe8data import HEADER_SIZE
from .fe10data import STAT_NAMES, resolve

SYMBOL = "FE10PersonGrowth"
RECORD_SIZE = 12
LINE_SIZE = 8


@dataclass
class GrowthRecord:
    index: int
    pid: str
    first: int
    last: int
    lines_at: int     # absolute offset of the first stat line
    lines: list       # one list of 8 stats per level, first..last

    def level_of(self, line: int) -> int:
        return self.first + line

    @staticmethod
    def describe_level(level: int) -> str:
        """``31`` -> ``"tier 2, level 11"``."""
        tier, within = divmod(level - 1, 20)
        return f"tier {tier + 1}, level {within + 1}"


def read_growth(data: bytes) -> list[GrowthRecord]:
    start = fe8data.section_start(data, SYMBOL)
    count = struct.unpack_from(">H", data, start)[0]
    records = []
    for i in range(count):
        at = start + 4 + RECORD_SIZE * i
        pid_ptr, first, last, lines_ptr = struct.unpack_from(">IBB2xI", data, at)
        lines_at = HEADER_SIZE + lines_ptr
        n = max(0, last - first + 1)
        lines = [list(data[lines_at + LINE_SIZE * k:lines_at + LINE_SIZE * (k + 1)]) for k in range(n)]
        records.append(GrowthRecord(i, resolve(data, pid_ptr) or "", first, last, lines_at, lines))
    return records


def sharing(data: bytes, index: int) -> list[int]:
    """Records whose stat lines are the same block as record ``index``'s (itself included)."""
    records = read_growth(data)
    return [r.index for r in records if r.lines_at == records[index].lines_at]


def set_line(data: bytes, index: int, level: int, stats: Sequence[int]) -> bytes:
    """Set the eight stats of record ``index`` at internal ``level``."""
    record = read_growth(data)[index]
    if not record.first <= level <= record.last:
        raise ValueError(f"{record.pid} has stats for levels {record.first}-{record.last} only.")
    stats = [int(v) for v in stats]
    if len(stats) != len(STAT_NAMES) or not all(0 <= v <= 255 for v in stats):
        raise ValueError(f"A stat line holds {len(STAT_NAMES)} values between 0 and 255.")
    out = bytearray(data)
    at = record.lines_at + LINE_SIZE * (level - record.first)
    out[at:at + LINE_SIZE] = bytes(stats)
    return bytes(out)
