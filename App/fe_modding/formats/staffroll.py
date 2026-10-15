"""Read and write ``ending/staffroll*.bin`` - the staff credits (Path of Radiance).

**Container**: the standard GameCube data container (see ``soundroom``): a 0x20-byte header
(file size, data size, pointer count, symbol count = 2), the data section, the data-relative
offset of every non-null pointer, then two symbols, ``END_STAFFROLL_LINES`` (data +0x08) and
``END_STAFFROLL_STRS`` (data +0x0C), and their names.

**Data**: ``+0x00`` pointer to the build time text, ``+0x04`` pointer to the author's name,
``+0x08`` u32 line count, ``+0x0C`` one 12-byte row per line: three string pointers (null =
empty), then the strings, sorted by bytes and unique, padded to 4.

**Engine** (US): ``load_staffroll_parameters`` (``0x801FA534``) loads ``staffroll_noa.bin``
(``staffroll.bin`` is the shorter Japanese list and is not loaded) and sizes the scroll from the
line count, 0x30 per line. ``draw_staffroll_ui`` (``0x801FA5DC``) draws each row: column 1
right-aligned to x 288 (a role), column 2 centred on x 304 (a heading, with its own ``#F``
font code), column 3 left-aligned with the format ``"#F04%s"`` (a name).
"""

from __future__ import annotations

import struct
from dataclasses import dataclass, field
from pathlib import Path

from .common import HEADER_SIZE

ENCODING = "shift_jis"
ROW_SIZE = 12
ROWS_AT = 0x0C
SYMBOLS = (("END_STAFFROLL_LINES", 0x08), ("END_STAFFROLL_STRS", 0x0C))


class StaffRollError(ValueError):
    pass


@dataclass
class StaffRoll:
    build_time: str
    author: str
    lines: list[tuple[str, str, str]] = field(default_factory=list)   # role, heading, name ("" = none)


def read_staffroll(data: bytes) -> StaffRoll:
    size, data_size, _pointers, symbols = struct.unpack_from(">4I", data, 0)
    if size != len(data) or HEADER_SIZE + data_size > len(data) or symbols != 2:
        raise StaffRollError("Not a staff roll file")
    body = data[HEADER_SIZE:HEADER_SIZE + data_size]

    def text(pointer: int) -> str:
        return body[pointer:body.index(b"\0", pointer)].decode(ENCODING) if pointer else ""

    built, author, count = struct.unpack_from(">3I", body, 0)
    if ROWS_AT + count * ROW_SIZE > len(body):
        raise StaffRollError(f"Line count {count} runs past the data section")
    lines = [tuple(text(p) for p in struct.unpack_from(">3I", body, ROWS_AT + i * ROW_SIZE)) for i in range(count)]
    return StaffRoll(text(built), text(author), lines)


def build_staffroll(roll: StaffRoll) -> bytes:
    """Build the file (a vanilla roll gives the vanilla bytes)."""
    strings = [roll.build_time, roll.author] + [s for line in roll.lines for s in line]
    encoded = sorted({s.encode(ENCODING) for s in strings if s})
    pool_start = ROWS_AT + len(roll.lines) * ROW_SIZE
    where, pool = {}, bytearray()
    for raw in encoded:
        where[raw] = pool_start + len(pool)
        pool += raw + b"\0"
    body, pointers = bytearray(), []

    def put(s: str) -> None:
        if s:
            pointers.append(len(body))
        body.extend(struct.pack(">I", where[s.encode(ENCODING)] if s else 0))

    put(roll.build_time)
    put(roll.author)
    body += struct.pack(">I", len(roll.lines))
    for line in roll.lines:
        if len(line) != 3:
            raise StaffRollError("Every line has three columns")
        for s in line:
            put(s)
    body += pool
    body += bytes(-len(body) % 4)
    names = b"".join(name.encode() + b"\0" for name, _ in SYMBOLS)
    symbols, name_at = b"", 0
    for name, offset in SYMBOLS:
        symbols += struct.pack(">II", offset, name_at)
        name_at += len(name) + 1
    tail = struct.pack(f">{len(pointers)}I", *pointers) + symbols + names
    size = HEADER_SIZE + len(body) + len(tail)
    header = struct.pack(">4I", size, len(body), len(pointers), len(SYMBOLS)) + bytes(16)
    return header + bytes(body) + tail


def read_staffroll_path(path: Path | str) -> StaffRoll:
    return read_staffroll(Path(path).read_bytes())
