"""Read and write the Tellius ``soundroom.bin`` picture and track tables.

The Sound Room (the extras jukebox) shows a full-screen picture behind its
track menu. Path of Radiance stores eight-byte picture rows here and its
fixed 64-entry track list in ``main.dol``. Radiant Dawn extends picture rows
to twelve bytes and follows them with 85 cue/unlock rows.

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
    #: FE10 extends each row with one opaque word.  It is preserved until
    #: its runtime meaning is confirmed; FE9 rows use ``None``.
    extra_word: int | None = None

    @property
    def scale(self) -> int | None:
        return None if self.extra_word is None else (self.extra_word >> 16) & 0xFFFF


@dataclass
class SoundRoomTrack:
    cue: str
    unlock_id: int


def _cstring(data: bytes, offset: int) -> str:
    end = data.index(b"\x00", offset)
    return data[offset:end].decode(ENCODING)


def _pooled_pointer(body: bytes, value: str) -> int | None:
    """Find a complete existing string even when no current row points to it."""
    needle = value.encode(ENCODING) + b"\0"
    at = body.find(needle)
    return at if at >= 0 else None


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
    # FE9 has one relocation per eight-byte row.  FE10 has additional
    # structures later in the same container and uses 12-byte image rows.
    fe10 = _pointer_count != count
    record_size = 12 if fe10 else RECORD_SIZE
    if 4 + count * record_size > len(body):
        raise SoundRoomError(f"Record count {count} runs past the data section")
    entries = []
    for i in range(count):
        start = 4 + i * record_size
        if fe10:
            pointer, x, y, extra = struct.unpack_from(">IhhI", body, start)
            entries.append(SoundRoomEntry(_cstring(body, pointer), x, y, extra))
        else:
            pointer, x, y = struct.unpack_from(">Ihh", body, start)
            entries.append(SoundRoomEntry(_cstring(body, pointer), x, y))
    return entries


def read_soundroom_path(path: Path | str) -> list[SoundRoomEntry]:
    return read_soundroom(Path(path).read_bytes())


def _fe10_track_table(data: bytes) -> tuple[bytes, int, int]:
    size, data_size, pointer_count, _symbols = struct.unpack_from(">4I", data)
    if size != len(data):
        raise SoundRoomError("Header sizes don't match the file")
    body = data[HEADER_SIZE:HEADER_SIZE + data_size]
    picture_count = struct.unpack_from(">I", body)[0]
    if pointer_count == picture_count:
        raise SoundRoomError("Path of Radiance stores its Sound Room tracks in main.dol")
    at = 4 + picture_count * 12
    if at + 4 > len(body):
        raise SoundRoomError("Radiant Dawn Sound Room track table is missing")
    count = struct.unpack_from(">I", body, at)[0]
    if at + 4 + count * 8 > len(body):
        raise SoundRoomError("Radiant Dawn Sound Room track table is truncated")
    return body, at + 4, count


def read_soundroom_tracks(data: bytes) -> list[SoundRoomTrack]:
    body, at, count = _fe10_track_table(data)
    result = []
    for index in range(count):
        pointer, unlock_id = struct.unpack_from(">2I", body, at + index * 8)
        result.append(SoundRoomTrack(_cstring(body, pointer), unlock_id))
    return result


def build_soundroom_tracks(data: bytes, tracks: list[SoundRoomTrack]) -> bytes:
    """Rebuild RD's track list and shared string pool."""
    return build_fe10_soundroom(read_soundroom(data), tracks, data)


def build_fe10_soundroom(entries: list[SoundRoomEntry], tracks: list[SoundRoomTrack],
                         source: bytes | None = None) -> bytes:
    """Build RD's variable-size image and track tables.

    Both tables point into one Shift-JIS string pool and every pointer field
    is listed in the container relocation table.  ``source`` is used only to
    preserve the common header's reserved bytes and to make a semantic no-op
    byte-identical.
    """
    if not entries:
        raise SoundRoomError("The Sound Room needs at least one picture")
    if not tracks:
        raise SoundRoomError("The Sound Room needs at least one track")
    for entry in entries:
        if not entry.name:
            raise SoundRoomError("Every picture needs a resource name")
        if entry.extra_word is None or not 0 <= entry.extra_word <= 0xFFFFFFFF:
            raise SoundRoomError("Radiant Dawn picture metadata must fit in 32 bits")
        if not (-0x8000 <= entry.x < 0x8000 and -0x8000 <= entry.y < 0x8000):
            raise SoundRoomError(f"{entry.name}: X and Y must fit a signed 16-bit value")
    for track in tracks:
        if not track.cue:
            raise SoundRoomError("Every Sound Room track needs a cue name")
        if not 0 <= track.unlock_id <= 0xFFFFFFFF:
            raise SoundRoomError("Sound Room unlock IDs must fit in 32 bits")
    if source is not None:
        if read_soundroom(source) == entries and read_soundroom_tracks(source) == tracks:
            return bytes(source)

    encoded_entries = [entry.name.encode(ENCODING) for entry in entries]
    encoded_tracks = [track.cue.encode(ENCODING) for track in tracks]
    pool_start = 4 + len(entries) * 12 + 4 + len(tracks) * 8
    offsets: dict[bytes, int] = {}
    pool = bytearray()
    for name in sorted(set(encoded_entries + encoded_tracks)):
        offsets[name] = pool_start + len(pool)
        pool += name + b"\0"

    body = bytearray(struct.pack(">I", len(entries)))
    pointer_fields = []
    for name, entry in zip(encoded_entries, entries):
        pointer_fields.append(len(body))
        body += struct.pack(">IhhI", offsets[name], entry.x, entry.y, entry.extra_word)
    body += struct.pack(">I", len(tracks))
    for name, track in zip(encoded_tracks, tracks):
        pointer_fields.append(len(body))
        body += struct.pack(">2I", offsets[name], track.unlock_id)
    body += pool
    body += bytes(-len(body) % 4)
    relocations = struct.pack(f">{len(pointer_fields)}I", *pointer_fields)
    size = HEADER_SIZE + len(body) + len(relocations)
    reserved = source[0x10:HEADER_SIZE] if source is not None and len(source) >= HEADER_SIZE else bytes(16)
    header = struct.pack(">4I", size, len(body), len(pointer_fields), 0) + reserved
    result = header + bytes(body) + relocations
    if read_soundroom(result) != entries or read_soundroom_tracks(result) != tracks:
        raise SoundRoomError("Rebuilt Radiant Dawn Sound Room did not validate")
    return result


def build_soundroom(entries: list[SoundRoomEntry], source: bytes | None = None) -> bytes:
    """Build a ``soundroom.bin`` (vanilla entries give the vanilla file)."""
    if not entries:
        raise SoundRoomError("The Sound Room needs at least one picture")
    for entry in entries:
        if not entry.name:
            raise SoundRoomError("Every picture needs a resource name")
        if not (-0x8000 <= entry.x < 0x8000 and -0x8000 <= entry.y < 0x8000):
            raise SoundRoomError(f"{entry.name}: X and Y must fit a signed 16-bit value")
    if any(entry.extra_word is not None for entry in entries):
        if source is None:
            raise SoundRoomError("Radiant Dawn Sound Room edits need the original file")
        return build_fe10_soundroom(entries, read_soundroom_tracks(source), source)

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


def write_soundroom(entries: list[SoundRoomEntry], path: Path | str, source: bytes | None = None) -> None:
    Path(path).write_bytes(build_soundroom(entries, source))
