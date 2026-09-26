"""GameCube disc composer: turn an extracted ``sys/`` + ``files/`` tree back
into a GameCube disc image (CISO).

This exists because the bundled WIT cannot do it: WIT 3.05 composes *every*
extracted directory as a Wii disc (encrypted DATA partition at 0xF800000,
fake-signed ticket/TMD, IOS 35) - ``wit dump`` of a Path of Radiance
extraction reports ``FST/WII`` even with ``disc-type = GameCube`` in its
``setup.txt``. Dolphin then boots that image in Wii mode and the GameCube
``main.dol`` faults immediately ("Unable to resolve read address ... PC
400"). The 4.7 GB plain-ISO padding once noted in tools.py was the same bug
seen from a different angle (that's the Wii single-layer size).

GameCube disc layout (all offsets absolute, big-endian):

- 0x0000: ``boot.bin`` (0x440 bytes). Fields patched here: 0x420 main.dol
  offset, 0x424 FST offset, 0x428 FST size, 0x42C max FST size.
- 0x0440: ``bi2.bin`` (0x2000 bytes)
- 0x2440: ``apploader.img``
- then ``main.dol``, then ``fst.bin``, then file data.

The FST is a flat array of 12-byte entries followed by a string table.
Entry 0 is the root directory. A file entry is (flags=0 | name offset
(24-bit), data offset, length); a directory entry is (flags=1 | name offset,
parent index, index one past its last descendant).

Entry order follows the source disc's own ``sys/fst.bin`` (retail order is
neither ASCII- nor case-insensitively sorted); files not in it - e.g. a new
music track - are appended to their directory in case-insensitive order.
The game's path lookup is a linear per-directory scan, so order is kept
only to stay as close to retail as possible, not for correctness.

File data is packed contiguously right after the FST at 32-byte alignment
(retail uses as little as 4; 32 keeps every file DMA-friendly). Retail
discs instead park data at the far end of the disc for faster outer-edge
reads - irrelevant under emulation, and packing from the front leaves the
most headroom below ``GAMECUBE_DISC_SIZE``.

CISO container: a 0x8000-byte header (``b"CISO"``, little-endian u32 block
size, then one byte per block - 1 if the block is stored), followed by the
stored blocks in order. All-zero blocks are left out.
"""

from __future__ import annotations

import os
import struct
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Iterator, Optional

from ..exceptions import ModdingError

GAMECUBE_DISC_SIZE = 1_459_978_240  # single-layer GameCube disc (0x57058000)

BOOT_SIZE = 0x440
BI2_OFFSET = 0x440
BI2_SIZE = 0x2000
APPLOADER_OFFSET = 0x2440
FST_ENTRY_SIZE = 12
FILE_ALIGN = 0x20
HEADER_ALIGN = 0x100
DATA_START_ALIGN = 0x8000

CISO_MAGIC = b"CISO"
CISO_HEADER_SIZE = 0x8000
CISO_MAP_SIZE = CISO_HEADER_SIZE - 8
CISO_BLOCK_SIZE = 0x200000

REQUIRED_SYS_FILES = ("boot.bin", "bi2.bin", "apploader.img", "main.dol")


class GcDiscError(ModdingError):
    pass


@dataclass
class _Node:
    name: str
    path: Optional[Path] = None  # set for files
    children: list["_Node"] = field(default_factory=list)

    @property
    def is_dir(self) -> bool:
        return self.path is None


@dataclass
class BuildResult:
    disc_size: int  # end of the last file's data - the image's logical size

    @property
    def oversized(self) -> bool:
        return self.disc_size > GAMECUBE_DISC_SIZE


def _align(value: int, align: int) -> int:
    return (value + align - 1) // align * align


def _read_fst_order(fst: bytes) -> list[str]:
    """Every path in a retail fst.bin, in entry order ('/'-joined, relative
    to files/). Directories included, so empty ones keep their place too."""
    if len(fst) < FST_ENTRY_SIZE:
        return []
    count = struct.unpack_from(">I", fst, 8)[0]
    strings = count * FST_ENTRY_SIZE
    paths = []
    ends: list[tuple[int, str]] = []  # (index one past the dir's last entry, dir path)
    for i in range(1, count):
        while ends and i >= ends[-1][0]:
            ends.pop()
        word, _, nxt = struct.unpack_from(">III", fst, i * FST_ENTRY_SIZE)
        start = strings + (word & 0xFFFFFF)
        name = fst[start:fst.index(b"\0", start)].decode("shift_jis")
        path = f"{ends[-1][1]}/{name}" if ends else name
        paths.append(path)
        if word >> 24:
            ends.append((nxt, path))
    return paths


def _build_tree(files_dir: Path, retail_order: list[str]) -> _Node:
    rank = {path.lower(): i for i, path in enumerate(retail_order)}

    def walk(directory: Path, rel: str) -> _Node:
        node = _Node(name=directory.name)
        entries = []
        for entry in os.scandir(directory):
            child_rel = f"{rel}/{entry.name}" if rel else entry.name
            if entry.is_dir():
                entries.append((child_rel, walk(Path(entry.path), child_rel)))
            else:
                entries.append((child_rel, _Node(name=entry.name, path=Path(entry.path))))
        entries.sort(key=lambda e: (e[0].lower() not in rank, rank.get(e[0].lower(), 0), e[1].name.lower()))
        node.children = [n for _, n in entries]
        return node

    return walk(files_dir, "")


def _flatten(root: _Node) -> list[list]:
    """Pre-order list of [node, parent index, next index] - FST entry order.
    A directory's next index is one past its last descendant."""
    out: list[list] = [[root, 0, 0]]

    def visit(node: _Node, index: int) -> None:
        for child in node.children:
            out.append([child, index, 0])
            if child.is_dir:
                child_index = len(out) - 1
                visit(child, child_index)
                out[child_index][2] = len(out)

    visit(root, 0)
    out[0][2] = len(out)
    return out


def _build_fst(entries: list[list], data_start: int) -> tuple[bytes, list[tuple[int, _Node]]]:
    """Returns (fst bytes, [(disc offset, file node)] in data order)."""
    names = bytearray()
    name_offsets = []
    for node, _, _ in entries[1:]:
        name_offsets.append(len(names))
        names += node.name.encode("shift_jis") + b"\0"

    table = bytearray()
    placements = []
    cursor = data_start
    for i, (node, parent, nxt) in enumerate(entries):
        if i == 0:
            table += struct.pack(">III", 1 << 24, 0, nxt)
            continue
        name_off = name_offsets[i - 1]
        if node.is_dir:
            table += struct.pack(">III", (1 << 24) | name_off, parent, nxt)
        else:
            size = node.path.stat().st_size
            table += struct.pack(">III", name_off, cursor, size)
            placements.append((cursor, node))
            cursor = _align(cursor + size, FILE_ALIGN)
    return bytes(table + names), placements


def _disc_chunks(sys_parts: list[tuple[int, bytes]], placements: list[tuple[int, _Node]]) -> Iterator[tuple[int, bytes]]:
    """(disc offset, bytes) pieces in ascending, non-overlapping order."""
    yield from sys_parts
    for offset, node in placements:
        with open(node.path, "rb") as f:
            pos = offset
            while chunk := f.read(CISO_BLOCK_SIZE):
                yield pos, chunk
                pos += len(chunk)


def _write_ciso(dest: Path, chunks: Iterator[tuple[int, bytes]], disc_size: int,
                progress: Optional[Callable[[int, int], None]] = None) -> None:
    num_blocks = _align(disc_size, CISO_BLOCK_SIZE) // CISO_BLOCK_SIZE
    if num_blocks > CISO_MAP_SIZE:
        raise GcDiscError("Disc too large for a CISO block map.")
    block_map = bytearray(CISO_MAP_SIZE)
    tmp = dest.with_name(dest.name + ".tmp")
    with open(tmp, "wb") as out:
        out.write(bytes(CISO_HEADER_SIZE))
        current = -1
        buf = bytearray(CISO_BLOCK_SIZE)

        def flush() -> None:
            if current >= 0 and any(buf):
                block_map[current] = 1
                out.write(buf)

        for offset, data in chunks:
            view = memoryview(data)
            while view:
                block, within = divmod(offset, CISO_BLOCK_SIZE)
                if block != current:
                    flush()
                    current = block
                    buf[:] = bytes(CISO_BLOCK_SIZE)
                    if progress:
                        progress(block, num_blocks)
                take = min(len(view), CISO_BLOCK_SIZE - within)
                buf[within:within + take] = view[:take]
                view = view[take:]
                offset += take
        flush()
        out.seek(0)
        out.write(CISO_MAGIC + struct.pack("<I", CISO_BLOCK_SIZE) + bytes(block_map))
    os.replace(tmp, dest)


def build_gamecube_ciso(extracted_dir: Path | str, dest: Path | str,
                        progress: Optional[Callable[[int, int], None]] = None) -> BuildResult:
    """Compose extracted_dir (containing sys/ and files/) into a GameCube CISO.

    An image larger than GAMECUBE_DISC_SIZE is still written - Dolphin reads
    past the physical limit - but BuildResult.oversized flags it, since it
    cannot fit a real disc (or run on hardware loaders that enforce it)."""
    extracted_dir = Path(extracted_dir)
    dest = Path(dest)
    sys_dir = extracted_dir / "sys"
    files_dir = extracted_dir / "files"
    for name in REQUIRED_SYS_FILES:
        if not (sys_dir / name).is_file():
            raise GcDiscError(f"Missing sys/{name} in {extracted_dir}")
    if not files_dir.is_dir():
        raise GcDiscError(f"Missing files/ in {extracted_dir}")

    boot = bytearray((sys_dir / "boot.bin").read_bytes()[:BOOT_SIZE])
    bi2 = (sys_dir / "bi2.bin").read_bytes()[:BI2_SIZE]
    apploader = (sys_dir / "apploader.img").read_bytes()
    dol = (sys_dir / "main.dol").read_bytes()
    if len(boot) != BOOT_SIZE:
        raise GcDiscError("sys/boot.bin is too short.")
    old_fst = sys_dir / "fst.bin"
    retail_order = _read_fst_order(old_fst.read_bytes()) if old_fst.is_file() else []

    entries = _flatten(_build_tree(files_dir, retail_order))

    dol_offset = _align(APPLOADER_OFFSET + len(apploader), HEADER_ALIGN)
    fst_offset = _align(dol_offset + len(dol), HEADER_ALIGN)
    # The FST's own size doesn't depend on data offsets, so lay it out once
    # to measure it, then again with the real data start.
    fst_size = len(_build_fst(entries, 0)[0])
    data_start = _align(fst_offset + fst_size, DATA_START_ALIGN)
    fst, placements = _build_fst(entries, data_start)

    struct.pack_into(">IIII", boot, 0x420, dol_offset, fst_offset, len(fst), len(fst))

    disc_size = data_start
    if placements:
        last_offset, last_node = placements[-1]
        disc_size = last_offset + last_node.path.stat().st_size

    sys_parts = [
        (0, bytes(boot)),
        (BI2_OFFSET, bi2),
        (APPLOADER_OFFSET, apploader),
        (dol_offset, dol),
        (fst_offset, fst),
    ]
    dest.parent.mkdir(parents=True, exist_ok=True)
    _write_ciso(dest, _disc_chunks(sys_parts, placements), disc_size, progress)
    return BuildResult(disc_size=disc_size)
