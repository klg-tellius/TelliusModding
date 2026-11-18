"""The Wii disc banner ``opening.bnr``: the channel title and pictures the Wii Menu shows.

Radiant Dawn's ``opening.bnr`` is the standard Wii layout (one per Wii disc, read by the Wii Menu,
not by the game):

* 0x40 zero bytes, then the ``IMET`` header: hash size (0x600), 3, the unpacked sizes of
  ``icon.bin``, ``banner.bin`` and ``sound.bin``, a zero flag word, then ten channel titles
  (Japanese, English, German, French, Spanish, Italian, Dutch, simplified Chinese, traditional
  Chinese, Korean), each two lines of 21 UTF-16BE characters; zero padding, and at 0x5F0 the MD5
  of bytes 0-0x5FF taken with the MD5 itself zeroed.
* at 0x600 a U8 archive ``meta/icon.bin``, ``meta/banner.bin``, ``meta/sound.bin``. Each is an
  ``IMD5`` header (magic, payload size, 8 zero bytes, the payload's MD5) and a payload: for the
  icon and banner, ``LZ77`` and an LZ10 stream of another U8 archive (``arc/blyt`` layout,
  ``arc/anim`` animation, ``arc/timg/*.tpl`` pictures); for the sound a ``BNS`` stream.

:func:`build_banner` keeps every untouched part byte for byte; a changed picture recompresses its
archive with the app's LZ10 encoder and refreshes the sizes and hashes.
"""

from __future__ import annotations

import hashlib
import struct
from dataclasses import dataclass, field

from . import lz10

U8_MAGIC = b"U\xaa8-"
IMET_OFFSET = 0x40
TITLES_OFFSET = 0x5C
TITLE_SIZE = 0x54
TITLE_CHARS = 21
HASH_OFFSET = 0x5F0
HEADER_END = 0x600
LANGUAGES = ("Japanese", "English", "German", "French", "Spanish", "Italian", "Dutch",
             "Chinese (simplified)", "Chinese (traditional)", "Korean")


class BannerError(ValueError):
    pass


# ------------------------------------------------------------------ U8 archives

@dataclass
class U8Entry:
    path: str                 # "meta/icon.bin"; directories end without data
    data: bytes | None        # None for a directory


def read_u8(data: bytes) -> list[U8Entry]:
    if data[:4] != U8_MAGIC:
        raise BannerError("Not a U8 archive.")
    root, _header_size, _data_start = struct.unpack_from(">III", data, 4)
    (count,) = struct.unpack_from(">I", data, root + 8)
    strings = root + 12 * count
    nodes = [struct.unpack_from(">BBHII", data, root + 12 * i) for i in range(count)]
    entries, stack = [], []   # stack of (end index, path)
    for index, (kind, high, low, offset, size) in enumerate(nodes):
        while stack and index >= stack[-1][0]:
            stack.pop()
        name_at = strings + ((high << 16) | low)
        name = data[name_at:data.index(b"\0", name_at)].decode("ascii")
        parent = stack[-1][1] if stack else ""
        path = f"{parent}/{name}" if parent else name
        if kind == 1:
            if index:
                entries.append(U8Entry(path, None))
            stack.append((size, path))
        else:
            entries.append(U8Entry(path, data[offset:offset + size]))
    return entries


def build_u8(entries: list[U8Entry], align: int = 0x20) -> bytes:
    """A U8 archive of ``entries`` in their order (directories before their contents)."""
    names = bytearray(b"\0")
    nodes = [[1, 0, 0, 0]]  # kind, name offset, offset/parent, size/next
    dirs = {"": 0}
    for entry in entries:
        parent, _, name = entry.path.rpartition("/")
        if parent not in dirs:
            raise BannerError(f"{entry.path}: its folder must come first.")
        offset = len(names)
        names += name.encode("ascii") + b"\0"
        if entry.data is None:
            dirs[entry.path] = len(nodes)
            nodes.append([1, offset, dirs[parent], 0])
        else:
            nodes.append([0, offset, 0, len(entry.data)])
    # a directory's "next" is the index after its last descendant
    for path, index in dirs.items():
        last = index
        for i, entry in enumerate(entries, start=1):
            if path == "" or entry.path.startswith(path + "/"):
                last = i
        nodes[index][3] = last + 1
    root = 0x20
    header_size = 12 * len(nodes) + len(names)
    data_start = -(-(root + header_size) // align) * align
    out = bytearray(data_start)
    blobs = []
    at = data_start
    for node, entry in zip(nodes[1:], entries):
        if entry.data is not None:
            at = -(-at // align) * align
            node[2] = at
            blobs.append((at, entry.data))
            at += len(entry.data)
    struct.pack_into(">4sIII", out, 0, U8_MAGIC, root, header_size, data_start)
    for i, (kind, name, a, b) in enumerate(nodes):
        struct.pack_into(">BBHII", out, root + 12 * i, kind, name >> 16, name & 0xFFFF, a, b)
    out[root + 12 * len(nodes):root + header_size] = names
    for offset, blob in blobs:
        out += bytes(offset - len(out))
        out += blob
    return bytes(out)  # the last file is not padded


# ------------------------------------------------------------------ IMD5 / LZ77 wrapping

def unwrap(blob: bytes) -> tuple[bytes, bool]:
    """``(payload, compressed)`` of an IMD5 file; the payload is unpacked when it is LZ77."""
    if blob[:4] != b"IMD5":
        raise BannerError("Not an IMD5 file.")
    payload = blob[0x20:]
    if payload[:4] == b"LZ77":
        return lz10.decompress(payload[4:]), True
    return payload, False


def wrap(payload: bytes, compress: bool) -> bytes:
    body = b"LZ77" + lz10.compress(payload) if compress else payload
    return b"IMD5" + struct.pack(">I", len(body)) + bytes(8) + hashlib.md5(body).digest() + body


# ------------------------------------------------------------------ the banner

@dataclass
class Banner:
    header: bytes                      # bytes 0-0x5FF
    archive: list[U8Entry]             # the outer U8 entries
    titles: list[tuple[str, str]] = field(default_factory=list)
    _raw_archive: bytes = b""
    _unpacked: dict[str, list[U8Entry]] = field(default_factory=dict)
    _changed: set[str] = field(default_factory=set)

    def part(self, name: str) -> list[U8Entry]:
        """The unpacked archive inside ``meta/<name>`` (``icon.bin``, ``banner.bin``)."""
        if name not in self._unpacked:
            entry = next(e for e in self.archive if e.path == f"meta/{name}")
            payload, _compressed = unwrap(entry.data)
            self._unpacked[name] = read_u8(payload)
        return self._unpacked[name]

    def pictures(self, name: str) -> list[U8Entry]:
        return [e for e in self.part(name) if e.data is not None and e.path.endswith(".tpl")]

    def replace_file(self, name: str, path: str, data: bytes) -> None:
        for entry in self.part(name):
            if entry.path == path:
                entry.data = data
                self._changed.add(name)
                return
        raise BannerError(f"No {path} in {name}.")


def _read_titles(header: bytes) -> list[tuple[str, str]]:
    titles = []
    for i in range(len(LANGUAGES)):
        raw = header[TITLES_OFFSET + TITLE_SIZE * i:TITLES_OFFSET + TITLE_SIZE * (i + 1)]
        text = raw.decode("utf-16-be")
        titles.append((text[:TITLE_CHARS].split("\0", 1)[0], text[TITLE_CHARS:].split("\0", 1)[0]))
    return titles


def read_banner(data: bytes) -> Banner:
    if len(data) < HEADER_END or data[IMET_OFFSET:IMET_OFFSET + 4] != b"IMET":
        raise BannerError("Not a Wii banner (no IMET header at 0x40).")
    raw_archive = data[HEADER_END:]
    archive = read_u8(raw_archive)
    return Banner(data[:HEADER_END], archive, _read_titles(data), raw_archive)


def _title_bytes(line1: str, line2: str, old: bytes) -> bytes:
    for line in (line1, line2):
        if len(line) > TITLE_CHARS:
            raise BannerError(f"A title line holds at most {TITLE_CHARS} characters: {line!r}.")
    new = bytearray(old)
    for index, line in enumerate((line1, line2)):
        start = 2 * TITLE_CHARS * index
        current = old[start:start + 2 * TITLE_CHARS].decode("utf-16-be").split("\0", 1)[0]
        if line != current:
            encoded = line.encode("utf-16-be")
            new[start:start + 2 * TITLE_CHARS] = encoded + bytes(2 * TITLE_CHARS - len(encoded))
    return bytes(new)


def build_banner(banner: Banner) -> bytes:
    header = bytearray(banner.header)
    for i, (line1, line2) in enumerate(banner.titles):
        at = TITLES_OFFSET + TITLE_SIZE * i
        header[at:at + TITLE_SIZE] = _title_bytes(line1, line2, bytes(header[at:at + TITLE_SIZE]))
    archive = banner.archive
    if banner._changed:
        archive = []
        sizes = {}
        for entry in banner.archive:
            name = entry.path.rpartition("/")[2]
            if name in banner._changed:
                payload = build_u8(banner.part(name))
                sizes[name] = len(payload)
                archive.append(U8Entry(entry.path, wrap(payload, compress=True)))
            else:
                archive.append(entry)
        for index, name in enumerate(("icon.bin", "banner.bin")):
            if name in sizes:
                struct.pack_into(">I", header, IMET_OFFSET + 12 + 4 * index, sizes[name])
        raw_archive = build_u8(archive)
    else:
        raw_archive = banner._raw_archive
    header[HASH_OFFSET:HEADER_END] = bytes(16)
    header[HASH_OFFSET:HEADER_END] = hashlib.md5(bytes(header)).digest()
    return bytes(header) + raw_archive
