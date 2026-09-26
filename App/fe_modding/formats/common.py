"""Shared conventions used across Path of Radiance's file formats.

Most of these formats are a small fixed header followed by a body whose
internal pointers are 0-based from the end of that header - not from the
start of the file. HEADER_SIZE is that header size; every format module
seeks to ``pointer + HEADER_SIZE`` when it wants the pointer's absolute file
position.
"""

from __future__ import annotations

import struct
from typing import BinaryIO

HEADER_SIZE = 0x20

# Real section addresses never get anywhere near this; a table entry whose
# "address" is >= this value is actually the start of the section-name
# strings, reinterpreted as if it were one more (address, name_offset) pair.
SECTION_TABLE_SENTINEL = 0x01000000


def decode_str(data: bytes) -> str:
    """Decode a NUL-terminated string's raw bytes, tolerating stray non-ASCII bytes.

    Every name in these formats is plain ASCII in the overwhelming majority
    of cases, but at least one real file has a name with a byte sequence
    that isn't: a mapbuilddesc object name in three real chapter maps
    (zmap/bmap04, bmap12, bmap12_2) stores "flowerpot_01.g" with its leading
    "f" typed in full-width Shift-JIS (bytes 0x82 0x86) instead of
    half-width ASCII - decoding those two bytes as Shift-JIS recovers the
    intended fullwidth "f" character exactly (confirmed by decoding a real
    sample), so this is a stray IME artifact from the original Japanese dev
    environment, not corrupt data. Shift-JIS is tried before latin-1 so a
    case like that decodes to something meaningful rather than mojibake;
    latin-1 is the final fallback since it can decode any byte sequence and
    so can't itself raise.
    """
    try:
        return data.decode("ascii")
    except UnicodeDecodeError:
        pass
    try:
        return data.decode("shift_jis")
    except UnicodeDecodeError:
        return data.decode("latin-1")


def read_cstring(stream: BinaryIO) -> bytes:
    """Read a single NUL-terminated string starting at the stream's current position."""
    chunks = []
    while True:
        byte = stream.read(1)
        if not byte or byte == b"\x00":
            break
        chunks.append(byte)
    return b"".join(chunks)


def read_cstring_table(data: bytes, base_offset: int = 0) -> dict[int, bytes]:
    """Split a blob of back-to-back NUL-terminated strings into {offset: string}.

    Offsets are relative to the start of ``data`` by default; pass
    ``base_offset`` to key them by absolute file position instead (needed
    when some other structure's stored pointers point at that position
    directly, e.g. dispo files - see dispo.py).
    """
    table: dict[int, bytes] = {}
    offset = base_offset
    for entry in data.split(b"\x00"):
        table[offset] = entry
        offset += len(entry) + 1
    return table


def read_section_table(stream: BinaryIO, table_start: int, filesize: int) -> list[tuple[int, str]]:
    """Read a sentinel-terminated (address, name) table.

    Shared by map.bin and dispo files: consecutive 8-byte (address,
    name_offset) pairs starting at table_start, until the sentinel is hit
    (see SECTION_TABLE_SENTINEL) - at which point the *rest of the file* is
    the section names, as NUL-terminated strings addressed by name_offset
    (0-based from where the names start). Returns
    [(absolute_section_address, name), ...] in file order, with addresses
    already shifted by HEADER_SIZE.
    """
    stream.seek(table_start)
    addresses = []
    name_offsets = []
    while True:
        address, name_offset = struct.unpack(">II", stream.read(8))
        if address >= SECTION_TABLE_SENTINEL:
            break
        addresses.append(address + HEADER_SIZE)
        name_offsets.append(name_offset)

    names_start = stream.tell() - 8
    stream.seek(names_start)
    names_by_offset = read_cstring_table(stream.read(filesize - names_start))

    return [(addr, decode_str(names_by_offset[off])) for addr, off in zip(addresses, name_offsets)]
