"""Read/write ``pack``-magic archives (``.pak`` files).

Layout: 4-byte magic ``pack`` + big-endian int16 file count + 2 reserved
bytes, then one 16-byte entry per file (big-endian: reserved uint32 - always
observed as 0, name offset, content offset, content length, all absolute
file offsets). Names are tightly packed NUL-terminated strings right after
the entry table; content blocks follow, each one padded up to the next
32-byte boundary (including after the last one, so the file size itself is
always a multiple of 32). Verified byte-for-byte: extracting and repacking
a real 9-file archive unchanged reproduced the original file exactly.

The "reserved" field is 0 on every entry except 176 on the US disc, which
hold 1: 154 of the 292 ``yme/`` effect meshes, 8 map-prop meshes and
``bmap28_2``'s ``map.bin`` (``coverage.py`` survey). Its meaning is open.
PakEntry keeps it (``reserved``) and ``pack_pak(files, reserved)`` writes it
back; without that list ``pack_pak()`` writes 0.
"""

from __future__ import annotations

import io
import struct
from dataclasses import dataclass
from pathlib import Path

from .common import decode_str, read_cstring

MAGIC = b"pack"
ALIGNMENT = 32


class PakError(Exception):
    pass


@dataclass(frozen=True)
class PakEntry:
    name: str
    offset: int
    length: int
    reserved: int = 0


def read_pak_entries(data: bytes) -> list[PakEntry]:
    if data[:4] != MAGIC:
        raise PakError("Not a pak archive (missing 'pack' magic).")

    (num_files,) = struct.unpack(">h", data[4:6])

    entries = []
    for i in range(num_files):
        entry_offset = 8 + i * 16
        reserved, name_offset, content_offset, content_length = struct.unpack(
            ">IIII", data[entry_offset : entry_offset + 16]
        )
        name = decode_str(read_cstring(_stream_at(data, name_offset)))
        entries.append(PakEntry(name=name, offset=content_offset, length=content_length, reserved=reserved))

    return entries


def read_pak_file_content(data: bytes, entry: PakEntry) -> bytes:
    return data[entry.offset : entry.offset + entry.length]


def extract_pak(archive_path: Path | str, dest_dir: Path | str) -> list[PakEntry]:
    """Write every file in the archive into dest_dir. Returns the entries in
    on-disk order, for passing to repack_pak() later."""
    data = Path(archive_path).read_bytes()
    entries = read_pak_entries(data)

    dest_dir = Path(dest_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)
    for entry in entries:
        (dest_dir / entry.name).write_bytes(read_pak_file_content(data, entry))

    return entries


def pack_pak(files: list[tuple[str, bytes]], reserved: list[int] | None = None) -> bytes:
    """Build a pak archive from (name, content) pairs, in the given order."""
    if reserved is None:
        reserved = [0] * len(files)
    if len(reserved) != len(files):
        raise PakError("reserved must have one entry per file.")

    num_files = len(files)
    out = bytearray()
    out += MAGIC
    out += struct.pack(">h", num_files)
    out += b"\x00\x00"

    entry_table_offset = len(out)
    out += bytes(16 * num_files)  # placeholder, patched below

    name_offsets = []
    for name, _ in files:
        name_offsets.append(len(out))
        out += name.encode("ascii") + b"\x00"

    content_offsets = []
    for _, content in files:
        while len(out) % ALIGNMENT != 0:
            out.append(0)
        content_offsets.append(len(out))
        out += content

    while len(out) % ALIGNMENT != 0:
        out.append(0)

    for i, (_, content) in enumerate(files):
        entry_bytes = struct.pack(">IIII", reserved[i], name_offsets[i], content_offsets[i], len(content))
        out[entry_table_offset + i * 16 : entry_table_offset + (i + 1) * 16] = entry_bytes

    return bytes(out)


def repack_pak(dest_dir: Path | str, entries: list[PakEntry]) -> bytes:
    """Rebuild an archive from files previously written by extract_pak(),
    reading current (possibly edited) content back off disk."""
    dest_dir = Path(dest_dir)
    files = [(entry.name, (dest_dir / entry.name).read_bytes()) for entry in entries]
    reserved = [entry.reserved for entry in entries]
    return pack_pak(files, reserved)


def _stream_at(data: bytes, offset: int) -> io.BytesIO:
    stream = io.BytesIO(data)
    stream.seek(offset)
    return stream
