"""Best-effort parser for ``system.cmp``'s ``face/facedata.bin`` table.

The executable research confirms this resource is loaded during core system
initialization and is keyed by the same ``FID_`` family used by dialogue
portraits. The exact production-table layout still needs a full byte-level
writeup, so this parser intentionally supports a conservative structural
format useful to the app: find ``FID_`` keys and expose nearby coordinate
pairs when they are stored plainly. The dialogue preview also has an
alpha-hole fallback, so an incomplete parse never blocks rendering.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from . import lz10, pak


@dataclass(frozen=True)
class FaceDataRecord:
    fid: str
    eye: Optional[tuple[int, int]] = None
    mouth: Optional[tuple[int, int]] = None


def read_face_data(data: bytes) -> dict[str, FaceDataRecord]:
    """Return face records keyed by FID label.

    Two shapes are supported:
    - a compact synthetic/test shape: ``FDAT`` magic, count, then fixed
      ``32shhhh`` records;
    - a best-effort real-data scan for NUL-terminated ``FID_`` labels,
      with plausible signed 16-bit coordinate pairs immediately following.
    """
    if data[:4] == b"FDAT":
        return _read_synthetic_fdat(data)
    return _scan_fid_records(data)


def read_face_data_from_system_cmp(path: Path | str) -> dict[str, FaceDataRecord]:
    decompressed = lz10.decompress(Path(path).read_bytes())
    entries = pak.read_pak_entries(decompressed)
    entry = next((e for e in entries if e.name.replace("\\", "/") == "face/facedata.bin"), None)
    if entry is None:
        return {}
    return read_face_data(pak.read_pak_file_content(decompressed, entry))


def _read_synthetic_fdat(data: bytes) -> dict[str, FaceDataRecord]:
    if len(data) < 8:
        return {}
    count = struct.unpack_from(">I", data, 4)[0]
    offset = 8
    out: dict[str, FaceDataRecord] = {}
    for _ in range(count):
        if offset + 40 > len(data):
            break
        raw_name, eye_x, eye_y, mouth_x, mouth_y = struct.unpack_from(">32shhhh", data, offset)
        offset += 40
        fid = raw_name.split(b"\x00", 1)[0].decode("ascii", errors="ignore")
        if fid.startswith("FID_"):
            out[fid] = FaceDataRecord(fid=fid, eye=(eye_x, eye_y), mouth=(mouth_x, mouth_y))
    return out


def _scan_fid_records(data: bytes) -> dict[str, FaceDataRecord]:
    out: dict[str, FaceDataRecord] = {}
    start = 0
    while True:
        index = data.find(b"FID_", start)
        if index == -1:
            break
        end = data.find(b"\x00", index)
        if end == -1 or end - index > 48:
            start = index + 4
            continue
        raw = data[index:end]
        if not raw.isascii():
            start = index + 4
            continue
        fid = raw.decode("ascii")
        tail = data[end + 1 : end + 1 + 32]
        coords = _first_plausible_coordinate_pairs(tail)
        out.setdefault(fid, FaceDataRecord(fid=fid, eye=coords[0], mouth=coords[1]))
        start = end + 1
    return out


def _first_plausible_coordinate_pairs(data: bytes) -> tuple[Optional[tuple[int, int]], Optional[tuple[int, int]]]:
    pairs: list[tuple[int, int]] = []
    for offset in range(0, max(0, len(data) - 3), 2):
        x, y = struct.unpack_from(">hh", data, offset)
        if -256 <= x <= 256 and -256 <= y <= 256:
            pairs.append((x, y))
            if len(pairs) == 2:
                break
    while len(pairs) < 2:
        pairs.append(None)  # type: ignore[arg-type]
    return pairs[0], pairs[1]
