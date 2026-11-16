"""Read and rebuild Radiant Dawn's small table files with a sorted string pool.

``dictionary.bin``, ``dictionaryF.bin``, ``conversationroom.bin``, ``FE10Epilogue.bin`` and
``FE10Intro.bin`` share one layout inside the labeled-section container
(``wiki/formats/labeled-section.md``):

* the tables, from data offset 0 (each a count followed by fixed-size records);
* the string pool: every distinct string once, sorted by its Shift-JIS bytes, each ending in a NUL,
  padded with zeros to four bytes;
* the relocation table (every pointer field, ascending), then the section table and its names.

No pointer targets the tables themselves, so a file is the table bytes, a map of pointer fields to
their strings, and its symbols. :func:`build_pool_file` lays the pool out again from the strings
the fields hold, which gives back the retail files byte for byte and lets an editor add, remove or
change any string.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass, field

from .common import HEADER_SIZE

ENCODING = "cp932"


class PoolFileError(ValueError):
    pass


@dataclass
class PoolFile:
    """``body``: the table bytes (pointer fields hold zero). ``pointers``: body offset -> string.
    ``symbols``: ``(name, data offset)`` in table order. ``header_tail``: header bytes 0x14-0x1F."""

    body: bytes
    pointers: dict[int, str] = field(default_factory=dict)
    symbols: list[tuple[str, int]] = field(default_factory=list)
    header_tail: bytes = bytes(12)

    def string(self, offset: int) -> str | None:
        return self.pointers.get(offset)


def read_pool_file(data: bytes, encoding: str = ENCODING) -> PoolFile:
    if len(data) < HEADER_SIZE:
        raise PoolFileError("The file is shorter than its header.")
    size, data_size, pointer_count, symbol_count, imports = struct.unpack_from(">5I", data)
    if size != len(data) or imports:
        raise PoolFileError("Not a labeled-section file without imports.")
    payload = data[HEADER_SIZE:HEADER_SIZE + data_size]
    reloc = HEADER_SIZE + data_size
    fields = [struct.unpack_from(">I", data, reloc + 4 * i)[0] for i in range(pointer_count)]
    targets = {f: struct.unpack_from(">I", payload, f)[0] for f in fields}
    pool = min(targets.values(), default=len(payload))
    if any(f + 4 > pool for f in fields):
        raise PoolFileError("A pointer field lies inside the string pool.")
    body = bytearray(payload[:pool])
    pointers = {}
    for offset, target in targets.items():
        end = payload.find(b"\0", target)
        if end < 0:
            raise PoolFileError(f"The string at {target:#x} has no end.")
        pointers[offset] = payload[target:end].decode(encoding)
        body[offset:offset + 4] = bytes(4)
    table = reloc + 4 * pointer_count
    names = table + 8 * symbol_count
    symbols = []
    for i in range(symbol_count):
        address, name_offset = struct.unpack_from(">II", data, table + 8 * i)
        start = names + name_offset
        symbols.append((data[start:data.index(b"\0", start)].decode(encoding), address))
    document = PoolFile(bytes(body), pointers, symbols, data[0x14:HEADER_SIZE])
    return document


def build_pool_file(document: PoolFile, encoding: str = ENCODING) -> bytes:
    body = bytearray(document.body)
    if len(body) % 4:
        raise PoolFileError("The tables must end on a four-byte boundary.")
    encoded = {text: text.encode(encoding) for text in set(document.pointers.values())}
    if any(b"\0" in raw for raw in encoded.values()):
        raise PoolFileError("A string holds a NUL character.")
    pool, at = bytearray(), {}
    for text, raw in sorted(encoded.items(), key=lambda item: item[1]):
        at[text] = len(body) + len(pool)
        pool += raw + b"\0"
    pool += bytes(-len(pool) % 4)
    for offset, text in document.pointers.items():
        if offset % 4 or offset + 4 > len(body):
            raise PoolFileError(f"Pointer field {offset:#x} is outside the tables.")
        struct.pack_into(">I", body, offset, at[text])
    payload = bytes(body + pool)
    fields = sorted(document.pointers)
    names = bytearray()
    table = bytearray()
    for name, address in document.symbols:
        table += struct.pack(">II", address, len(names))
        names += name.encode(encoding) + b"\0"
    tail = b"".join(struct.pack(">I", f) for f in fields) + bytes(table) + bytes(names)
    size = HEADER_SIZE + len(payload) + len(tail)
    header = struct.pack(">5I", size, len(payload), len(fields), len(document.symbols), 0)
    return header + document.header_tail + payload + tail


# ------------------------------------------------------------------ table helpers

def u32(document: PoolFile, offset: int) -> int:
    return struct.unpack_from(">I", document.body, offset)[0]


class TableWriter:
    """Builds the table bytes and pointer map of a new :class:`PoolFile` body."""

    def __init__(self) -> None:
        self.body = bytearray()
        self.pointers: dict[int, str] = {}

    @property
    def offset(self) -> int:
        return len(self.body)

    def word(self, value: int) -> None:
        self.body += struct.pack(">I", value & 0xFFFFFFFF)

    def pack(self, fmt: str, *values) -> None:
        self.body += struct.pack(fmt, *values)

    def text(self, value: str | None) -> None:
        """A pointer field: ``None`` stores a plain zero that is not relocated."""
        if value is not None:
            self.pointers[len(self.body)] = value
        self.word(0)

    def raw(self, data: bytes) -> None:
        self.body += data
