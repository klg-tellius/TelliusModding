"""Path of Radiance's movie subtitles: ``MovieCaptionData.bin``, on the European disc only (GFEP01).

The file is a :mod:`pool_file` file with no symbols. ``main.dol`` loads it once
(``0x8020798C``, the name at ``0x8028C123``) and the THP player reads it at ``0x802070EC``:

* data 0: a u32 count of movies, then one 8-byte entry per movie: a pointer to the movie's path
  (``movie/s01.thp``, compared with the playing movie's) and a pointer to its caption list;
* each caption list: 16-byte rows ended by a u32 zero. A row is

  ======  ==========================================================================================
  +0x00   pointer: the message key of the line (``MMC_SCENE01_01``), looked up in the language's
          message file (``0x8000E20C``); a ``\\n`` in the text starts a new line
  +0x04   u32: when the line appears, in milliseconds from the start of the movie (divided by the
          frame length of the video mode, 50 or 60 Hz, to get a frame)
  +0x08   u32: when the line disappears, in milliseconds
  +0x0C   u32: placement. 0 places the text at the bottom, raised by its number of lines; any other
          value puts it at a fixed height (only the last line of ``s08.thp`` uses 1)
  ======  ==========================================================================================

* then the string pool (keys and paths, sorted), as in every pool file.

The text itself is in the European message files (``MMC_*`` keys); this file holds only the timing.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass, field

from . import pool_file as pf
from .common import HEADER_SIZE

FILE_NAME = "MovieCaptionData.bin"
ROW_SIZE = 16
FIELDS = (  # (offset, size, name) of a caption row
    (0x00, 4, "message key"),
    (0x04, 4, "start (ms)"),
    (0x08, 4, "end (ms)"),
    (0x0C, 4, "placement"),
)


class CaptionError(ValueError):
    pass


@dataclass
class Caption:
    key: str
    start_ms: int
    end_ms: int
    placement: int = 0


@dataclass
class MovieCaptions:
    movie: str
    captions: list[Caption] = field(default_factory=list)


def read_captions(data: bytes) -> list[MovieCaptions]:
    if len(data) < HEADER_SIZE:
        raise CaptionError(f"{FILE_NAME} is shorter than its header.")
    data_size, pointer_count = struct.unpack_from(">II", data, 4)
    fields = struct.unpack_from(f">{pointer_count}I", data, HEADER_SIZE + data_size)
    targets = [struct.unpack_from(">I", data, HEADER_SIZE + f)[0] for f in fields]
    last = max(fields, default=0)
    # the caption lists are pointed at too: the pool starts at the first target past every field
    doc = pf.read_pool_file(data, pool_start=min((t for t in targets if t > last), default=data_size))
    if doc.symbols:
        raise CaptionError(f"{FILE_NAME} has no symbols.")
    body = doc.body
    (count,) = struct.unpack_from(">I", body, 0)
    movies = []
    for i in range(count):
        entry = 4 + 8 * i
        movie, table = doc.pointers.get(entry), doc.inner.get(entry + 4)
        if movie is None or table is None:
            raise CaptionError(f"movie {i}: the path or the caption list is missing.")
        captions = []
        at = table
        while True:
            if at + 4 > len(body):
                raise CaptionError(f"{movie}: the caption list has no end.")
            if at not in doc.pointers:
                if struct.unpack_from(">I", body, at)[0]:
                    raise CaptionError(f"{movie}: a row at {at:#x} has no message key.")
                break
            start, end, placement = struct.unpack_from(">3I", body, at + 4)
            captions.append(Caption(doc.pointers[at], start, end, placement))
            at += ROW_SIZE
        movies.append(MovieCaptions(movie, captions))
    return movies


def build_captions(movies: list[MovieCaptions]) -> bytes:
    """The file for ``movies`` (the retail list gives back the retail bytes)."""
    body = bytearray(struct.pack(">I", len(movies)) + bytes(8 * len(movies)))
    pointers: dict[int, str] = {}
    inner: dict[int, int] = {}
    for i, movie in enumerate(movies):
        if not movie.movie:
            raise CaptionError(f"movie {i} has no path.")
        pointers[4 + 8 * i] = movie.movie
        inner[8 + 8 * i] = len(body)
        for caption in movie.captions:
            if not caption.key:
                raise CaptionError(f"{movie.movie}: every line needs a message key.")
            if not 0 <= caption.start_ms <= caption.end_ms <= 0xFFFFFFFF:
                raise CaptionError(f"{movie.movie} {caption.key}: the end must not come before the start.")
            pointers[len(body)] = caption.key
            body += struct.pack(">I3I", 0, caption.start_ms, caption.end_ms, caption.placement)
        body += bytes(4)
    return pf.build_pool_file(pf.PoolFile(bytes(body), pointers, [], bytes(12), inner))
