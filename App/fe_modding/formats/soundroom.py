"""Read and write ``soundroom.bin`` - the Sound Room's picture list (Path of Radiance).

The Sound Room (the extras jukebox) shows a full-screen picture behind its
track menu. ``soundroom.bin`` lists those pictures; the track list itself is
the fixed 64-entry ``BGM_`` table in ``main.dol`` and does not come from this
file.

**Container**: the standard GameCube data container (see ``anim_registry``):
a 0x20-byte header (file size, data size, pointer count, symbol count = 0),
the data section, then the data-relative offset of every pointer field. No
symbol table. The data section is a record count, the records, then the
pool of the record names, sorted and unique. :func:`build_soundroom` rebuilds
the vanilla file byte for byte.

**Record** (8 bytes):

- ``+0x00`` pointer to a Shift-JIS ``RID_`` name: a resource of
  ``s/rect.bin`` (:mod:`rect`), built exactly like an event script's
  ``RectBuild``.
- ``+0x04`` s16 X, ``+0x06`` s16 Y: written into the built rect's screen
  position. Vanilla pictures are at least 608x448; the bigger ones use a
  negative offset to choose which part is on screen (``RID_塔``, 608x800, is
  at Y -250).

**Engine** (US ``main.dol``): ``soundroom_init`` (``0x801C332C``) loads the
file, keeps the count and the record array, and builds record 0.
``soundroom_update`` (``0x801C2AD0``) advances the picture as a slideshow,
wrapping at the record count read from the file, so records can be added
or removed: A on a track plays it and shows the next picture; with the menu
hidden (X), A/Right shows the next and Left the previous. The old picture
fades out and the new one fades in over 64 frames.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass
from pathlib import Path

from .common import HEADER_SIZE

RECORD_SIZE = 8
ENCODING = "shift_jis"
#: Size of a standard full-screen rect picture (the vanilla pictures at 0, 0).
SCREEN_SIZE = (608, 448)


class SoundRoomError(ValueError):
    pass


@dataclass
class SoundRoomEntry:
    name: str
    x: int = 0
    y: int = 0


def _cstring(data: bytes, offset: int) -> str:
    end = data.index(b"\x00", offset)
    return data[offset:end].decode(ENCODING)


def read_soundroom(data: bytes) -> list[SoundRoomEntry]:
    if len(data) < HEADER_SIZE + 4:
        raise SoundRoomError("File too small for a soundroom.bin")
    size, data_size, _pointer_count, _symbols = struct.unpack(">4I", data[:16])
    if size != len(data) or HEADER_SIZE + data_size > len(data):
        raise SoundRoomError("Header sizes don't match the file")
    body = data[HEADER_SIZE : HEADER_SIZE + data_size]
    (count,) = struct.unpack(">I", body[:4])
    if 4 + count * RECORD_SIZE > len(body):
        raise SoundRoomError(f"Record count {count} runs past the data section")
    entries = []
    for i in range(count):
        pointer, x, y = struct.unpack(">Ihh", body[4 + i * RECORD_SIZE : 4 + (i + 1) * RECORD_SIZE])
        entries.append(SoundRoomEntry(_cstring(body, pointer), x, y))
    return entries


def read_soundroom_path(path: Path | str) -> list[SoundRoomEntry]:
    return read_soundroom(Path(path).read_bytes())


def build_soundroom(entries: list[SoundRoomEntry]) -> bytes:
    """Build a ``soundroom.bin`` (vanilla entries give the vanilla file)."""
    if not entries:
        raise SoundRoomError("The Sound Room needs at least one picture")
    for entry in entries:
        if not entry.name:
            raise SoundRoomError("Every picture needs a resource name")
        if not (-0x8000 <= entry.x < 0x8000 and -0x8000 <= entry.y < 0x8000):
            raise SoundRoomError(f"{entry.name}: X and Y must fit a signed 16-bit value")
    encoded = [entry.name.encode(ENCODING) for entry in entries]
    pool_start = 4 + len(entries) * RECORD_SIZE
    offsets = {}
    pool = bytearray()
    for name in sorted(set(encoded)):
        offsets[name] = pool_start + len(pool)
        pool += name + b"\x00"
    body = bytearray(struct.pack(">I", len(entries)))
    for name, entry in zip(encoded, entries):
        body += struct.pack(">Ihh", offsets[name], entry.x, entry.y)
    body += pool
    body += bytes(-len(body) % 4)
    pointers = [4 + i * RECORD_SIZE for i in range(len(entries))]
    tail = struct.pack(f">{len(pointers)}I", *pointers)
    size = HEADER_SIZE + len(body) + len(tail)
    header = struct.pack(">4I", size, len(body), len(pointers), 0) + bytes(16)
    return header + bytes(body) + tail


def write_soundroom(entries: list[SoundRoomEntry], path: Path | str) -> None:
    Path(path).write_bytes(build_soundroom(entries))
