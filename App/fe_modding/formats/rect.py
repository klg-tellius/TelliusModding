"""Parse ``s/rect.bin``, the game's single sprite-sheet rect table: for each
of ~194 named resources (portraits, UI elements, ...), which image file(s)
back it and the rect(s) within them.

Unlike every other format in this package, the offsets/counts below are
hardcoded rather than derived from a header - but there's only one
rect.bin in the whole game (checked: not a per-chapter or per-character
file), so that's a property of the file, not a shortcut taken here.

These offsets were found by manually inspecting the real file, and were
re-verified against it while writing this module: all 194 top-level entries
and all 315 sub-image entries resolve cleanly, and the resolved file names
(``s/qf0``, ``s/1f5``, ...) match real files in ``files/s/``. The RID/name
strings are Shift-JIS (Japanese), left as raw bytes rather than decoded -
they read like internal dev labels (``RID_...``) rather than player-facing
text, unremoved from the original Japanese build.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO

from .common import HEADER_SIZE, read_cstring_table

LABEL_MAP_RANGE = (0x40BC, 0x5187)
ENTRY_TABLE_START = 0x5E78
ENTRY_COUNT = 0xC2
ENTRY_SIZE = 8
IMAGE_HEADER_SIZE = 20
SUB_ENTRY_SIZE = 0x24


@dataclass(frozen=True)
class RectImage:
    file_name: bytes
    height: int
    width: int
    raw_fields: tuple[int, ...]  # the other unlabeled bytes/ints from the sub-entry, in file order


@dataclass(frozen=True)
class RectEntry:
    name: bytes
    resource_id: bytes  # "RID_..." label
    flags: tuple[int, ...]  # the 15 unlabeled bytes following resource_id in the entry header
    images: list[RectImage]


def read_rects(stream: BinaryIO) -> list[RectEntry]:
    start, end = LABEL_MAP_RANGE
    stream.seek(start)
    label_map_bytes = stream.read(end - start)

    # RIDPtr/filePtr fields elsewhere in the file are absolute positions (need -HEADER_SIZE);
    # nameOffset in the entry table below is blob-relative (0-based) - same bytes, two key bases.
    label_by_position = read_cstring_table(label_map_bytes, base_offset=start - HEADER_SIZE)
    label_by_blob_offset = read_cstring_table(label_map_bytes)

    entries = []
    address = ENTRY_TABLE_START
    for _ in range(ENTRY_COUNT):
        stream.seek(address)
        address += ENTRY_SIZE
        name_offset, data_offset = struct.unpack(">II", stream.read(ENTRY_SIZE))
        name = label_by_blob_offset[name_offset]

        stream.seek(data_offset + HEADER_SIZE)
        rid_ptr, num_images, *flags = struct.unpack(">IBBBBBBBBBBBBBBBB", stream.read(IMAGE_HEADER_SIZE))
        resource_id = label_by_position[rid_ptr]

        images = []
        image_ptr_address = data_offset + HEADER_SIZE + IMAGE_HEADER_SIZE
        for _ in range(num_images):
            stream.seek(image_ptr_address)
            (data_ptr,) = struct.unpack(">I", stream.read(4))
            image_ptr_address += 4

            stream.seek(data_ptr + HEADER_SIZE)
            fields = struct.unpack(">BBBBBBBBIBBBBBBBBIIIHH", stream.read(SUB_ENTRY_SIZE))
            file_ptr = fields[8]
            height, width = fields[-2], fields[-1]
            file_name = label_by_position[file_ptr]
            other_fields = fields[:8] + fields[9:-2]
            images.append(RectImage(file_name=file_name, height=height, width=width, raw_fields=other_fields))

        entries.append(RectEntry(name=name, resource_id=resource_id, flags=tuple(flags), images=images))

    return entries


def read_rects_path(path: Path | str) -> list[RectEntry]:
    with open(path, "rb") as stream:
        return read_rects(stream)
