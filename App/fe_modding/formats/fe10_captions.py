"""Radiant Dawn's movie subtitles: ``Movie/caption_data.bin`` and ``Movie/Caption/<lang><movie>.cms``.

The US and European discs subtitle seven THP movies with pictures, not text. The movie
player (``0x800D1D14`` / ``0x800D1EDC``) looks the movie's file name up in ``CAPTION_DATA`` and,
when it is listed, loads ``<folder><lang><picture file>`` (the format ``%s%s%s``, the language
prefix ``e_``, ``d_``...) and steps through the caption list.

``caption_data.bin`` is a :mod:`pool_file` file whose tables also hold the caption blocks:

* data 0 and 4: the build time and author; ``CAPTION_DATA`` (offset 8): a u32 count and
  ``(movie file, caption block)`` pointer pairs;
* a caption block: the folder (``/Movie/Caption/``) and the picture file (``s1.cms``), then
  20-byte captions and a closing ``-1`` word.

A caption is five s32 values: the picture's index in the ``.cms`` (an LZ10 TPL), then the wait
before it, its fade-in, how long it stays and its fade-out, in milliseconds counted from the
previous caption's end (``0x800D176C``, ``0x800D1418``, ``0x800D1124``, ``0x800D0EE0``). Each
picture is drawn centred at the bottom of the 608 x 448 screen.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass, field

from .pool_file import PoolFile, TableWriter, build_pool_file, read_pool_file

SYMBOL = "CAPTION_DATA"
CAPTION_SIZE = 20
END = -1
SCREEN = (608, 448)


class CaptionError(ValueError):
    pass


@dataclass
class Caption:
    picture: int
    wait: int = 0
    fade_in: int = 100
    hold: int = 2800
    fade_out: int = 100

    @property
    def length(self) -> int:
        return self.wait + self.fade_in + self.hold + self.fade_out


@dataclass
class MovieCaptions:
    movie: str
    folder: str = "/Movie/Caption/"
    pictures: str = ""
    captions: list[Caption] = field(default_factory=list)

    def picture_path(self, prefix: str) -> str:
        """The disc path of the picture file for a language prefix (``e_``)."""
        return f"{self.folder}{prefix}{self.pictures}".lstrip("/")

    def timeline(self) -> list[tuple[int, int, Caption]]:
        """``(shown from, shown until, caption)`` in milliseconds from the movie's start."""
        out, clock = [], 0
        for caption in self.captions:
            start = clock + caption.wait
            out.append((start, start + caption.fade_in + caption.hold + caption.fade_out, caption))
            clock = out[-1][1]
        return out


@dataclass
class CaptionData:
    build_time: str | None = None
    author: str | None = None
    movies: list[MovieCaptions] = field(default_factory=list)
    header_tail: bytes = bytes(12)


def _blocks_end(payload: bytes) -> int:
    (count,) = struct.unpack_from(">I", payload, 8)
    end = 12 + 8 * count
    for i in range(count):
        (block,) = struct.unpack_from(">I", payload, 16 + 8 * i)
        at = block + 8
        while True:
            if at + 4 > len(payload):
                raise CaptionError("A caption list has no end.")
            (index,) = struct.unpack_from(">i", payload, at)
            if index == END:
                at += 4
                break
            at += CAPTION_SIZE
        end = max(end, at)
    return end


def read_captions(data: bytes) -> CaptionData:
    payload = data[0x20:0x20 + struct.unpack_from(">I", data, 4)[0]]
    doc = read_pool_file(data, pool_start=_blocks_end(payload))
    if doc.symbols != [(SYMBOL, 8)]:
        raise CaptionError("caption_data.bin should export CAPTION_DATA at offset 8.")
    body, text = doc.body, doc.pointers
    out = CaptionData(text.get(0), text.get(4), header_tail=doc.header_tail)
    (count,) = struct.unpack_from(">I", body, 8)
    for i in range(count):
        movie_at, block_at = 12 + 8 * i, 16 + 8 * i
        block = doc.inner.get(block_at)
        if movie_at not in text or block is None:
            raise CaptionError(f"Caption entry {i} is not a movie name and a caption block.")
        entry = MovieCaptions(text[movie_at], text.get(block), text.get(block + 4, ""))
        at = block + 8
        while struct.unpack_from(">i", body, at)[0] != END:
            entry.captions.append(Caption(*struct.unpack_from(">5i", body, at)))
            at += CAPTION_SIZE
        out.movies.append(entry)
    return out


def build_captions(document: CaptionData) -> bytes:
    w = TableWriter()
    w.text(document.build_time)
    w.text(document.author)
    w.word(len(document.movies))
    links = []
    for movie in document.movies:
        w.text(movie.movie)
        links.append(w.offset)
        w.word(0)
    for movie, link in zip(document.movies, links):
        w.patch_link(link, w.offset)
        w.text(movie.folder)
        w.text(movie.pictures)
        for caption in movie.captions:
            if caption.picture < 0:
                raise CaptionError(f"{movie.movie}: a picture index cannot be negative.")
            w.pack(">5i", caption.picture, caption.wait, caption.fade_in, caption.hold, caption.fade_out)
        w.pack(">i", END)
    doc = PoolFile(bytes(w.body), w.pointers, [(SYMBOL, 8)], document.header_tail, w.inner)
    return build_pool_file(doc)
