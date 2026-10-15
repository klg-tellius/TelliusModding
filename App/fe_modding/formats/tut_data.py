"""Read and write ``tut_data.bin`` / ``tut_data_en.bin`` - the tutorial list (Path of Radiance).

**Container**: the standard GameCube data container with five symbols, sorted by name:
``TUT_CATEGORY``, ``TUT_CHAPTER``, ``TUT_DATA``, ``TUT_INITIAL``, ``TutDataHead``. The data is
laid out head, chapter labels, category labels, initial labels, ``TUT_DATA``, then the strings
(sorted by bytes, unique, padded to 4).

- ``TutDataHead``: u32 0, pointer to the build time, pointer to the author's name.
- ``TUT_CHAPTER`` / ``TUT_CATEGORY`` / ``TUT_INITIAL``: arrays of pointers to message keys
  (``MT_CN``, ``MT_C00`` ...), one per group of the tutorial browser's three sort modes.
- ``TUT_DATA``: u32 count, then 24-byte rows:

  ======  =====================================================================================
  +0x00   id (the bit of the party's tutorial unlocked/learned masks, ``party_data+0x74/+0x84``)
  +0x01   category key (browser mode 1)
  +0x02   chapter key (browser mode 0)
  +0x03   display order (the list is merge-sorted on this signed byte)
  +0x04   initial key (browser mode 2)
  +0x05   start flags per difficulty, read by ``reinit_party_struct`` at a new game as
  ..+08   ``row[5 + difficulty]`` (Normal, Hard, Maniac, Easy): bit 1 sets the tutorial
          unlocked, bit 0 sets it learned
  +0x09   3 bytes of zero padding
  +0x0C   pointer: title message key (``MT_C01_s移動``)
  +0x10   pointer: event script file (``Scripts/C80.cmb``)
  +0x14   pointer: script function that plays it (``tut_01_Idou``)
  ======  =====================================================================================

The browser's group builders count keys from 1, so a key of 0 never forms a group.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass, field
from pathlib import Path

from .common import HEADER_SIZE

ENCODING = "shift_jis"
ROW_SIZE = 24
DIFFICULTIES = ("Normal", "Hard", "Maniac", "Easy")
UNLOCKED, LEARNED = 2, 1
LABEL_SECTIONS = ("TUT_CHAPTER", "TUT_CATEGORY", "TUT_INITIAL")


class TutDataError(ValueError):
    pass


@dataclass
class TutorialEntry:
    id: int
    category: int
    chapter: int
    order: int
    initial: int
    start_flags: list[int]            # per difficulty (DIFFICULTIES order)
    title_key: str
    script: str
    function: str


@dataclass
class TutData:
    build_time: str
    author: str
    head_word: int = 0
    chapters: list[str] = field(default_factory=list)
    categories: list[str] = field(default_factory=list)
    initials: list[str] = field(default_factory=list)
    entries: list[TutorialEntry] = field(default_factory=list)


def _symbols(data: bytes, data_size: int, pointers: int, count: int) -> dict[str, int]:
    base = HEADER_SIZE + data_size + 4 * pointers
    names = base + 8 * count
    out = {}
    for i in range(count):
        offset, name_at = struct.unpack_from(">II", data, base + 8 * i)
        end = data.index(b"\0", names + name_at)
        out[data[names + name_at:end].decode("ascii")] = offset
    return out


def read_tut_data(data: bytes) -> TutData:
    size, data_size, pointers, count = struct.unpack_from(">4I", data, 0)
    if size != len(data) or count != 5:
        raise TutDataError("Not a tut_data file")
    body = data[HEADER_SIZE:HEADER_SIZE + data_size]
    sym = _symbols(data, data_size, pointers, count)

    def text(pointer: int) -> str:
        return body[pointer:body.index(b"\0", pointer)].decode(ENCODING) if pointer else ""

    head_word, built, author = struct.unpack_from(">3I", body, sym["TutDataHead"])
    starts = sorted(sym.values()) + [None]

    def labels(name: str) -> list[str]:
        start = sym[name]
        end = starts[starts.index(start) + 1]
        return [text(p) for p in struct.unpack_from(f">{(end - start) // 4}I", body, start)]

    rows_at = sym["TUT_DATA"]
    (n,) = struct.unpack_from(">I", body, rows_at)
    entries = []
    for i in range(n):
        r = rows_at + 4 + ROW_SIZE * i
        b = body[r:r + 9]
        if body[r + 9:r + 12] != bytes(3):
            raise TutDataError(f"row {i}: padding bytes +9..+B are not zero")
        title, script, function = struct.unpack_from(">3I", body, r + 12)
        entries.append(TutorialEntry(b[0], b[1], b[2], struct.unpack("b", b[3:4])[0], b[4], list(b[5:9]),
                                     text(title), text(script), text(function)))
    return TutData(text(built), text(author), head_word, labels("TUT_CHAPTER"), labels("TUT_CATEGORY"),
                   labels("TUT_INITIAL"), entries)


def build_tut_data(tut: TutData) -> bytes:
    """Build the file (vanilla data gives the vanilla bytes)."""
    strings = [tut.build_time, tut.author, *tut.chapters, *tut.categories, *tut.initials]
    strings += [s for e in tut.entries for s in (e.title_key, e.script, e.function)]
    sections = {"TutDataHead": 0}
    at = 12
    for name, values in zip(LABEL_SECTIONS, (tut.chapters, tut.categories, tut.initials)):
        sections[name] = at
        at += 4 * len(values)
    sections["TUT_DATA"] = at
    pool_start = at + 4 + ROW_SIZE * len(tut.entries)
    where, pool = {}, bytearray()
    for raw in sorted({s.encode(ENCODING) for s in strings if s}):
        where[raw] = pool_start + len(pool)
        pool += raw + b"\0"
    body, pointers = bytearray(), []

    def put(s: str) -> None:
        if s:
            pointers.append(len(body))
        body.extend(struct.pack(">I", where[s.encode(ENCODING)] if s else 0))

    body += struct.pack(">I", tut.head_word)
    put(tut.build_time)
    put(tut.author)
    for values in (tut.chapters, tut.categories, tut.initials):
        for s in values:
            put(s)
    body += struct.pack(">I", len(tut.entries))
    for e in tut.entries:
        if len(e.start_flags) != 4:
            raise TutDataError(f"tutorial {e.id}: four start flags (one per difficulty) are needed")
        body += bytes((e.id, e.category, e.chapter)) + struct.pack("b", e.order) + bytes((e.initial,))
        body += bytes(e.start_flags) + bytes(3)
        for s in (e.title_key, e.script, e.function):
            put(s)
    body += pool
    body += bytes(-len(body) % 4)
    order = sorted(sections, key=lambda n: n.encode())
    names = b"".join(n.encode() + b"\0" for n in order)
    symbols, name_at = b"", 0
    for name in order:
        symbols += struct.pack(">II", sections[name], name_at)
        name_at += len(name) + 1
    tail = struct.pack(f">{len(pointers)}I", *pointers) + symbols + names
    size = HEADER_SIZE + len(body) + len(tail)
    header = struct.pack(">4I", size, len(body), len(pointers), len(order)) + bytes(16)
    return header + bytes(body) + tail


def read_tut_data_path(path: Path | str) -> TutData:
    return read_tut_data(Path(path).read_bytes())
