"""Radiant Dawn portraits: ``Face/facedata.bin`` records and the ``Face/<NAME>.cms`` images.

``facedata.bin`` (data container, 316 records of 48 bytes after a ``count, pointer`` header)::

    +0x00  FID_<NAME>     the small portrait (the 192x128 cut-in used inside speech balloons)
    +0x04  FID_L_<NAME>   the large portrait (the 336x336 body of background scenes)
    +0x08  MPID_<NAME>    the character's name message
    +0x0C  <NAME>.cms     the image file in Face/ (and Face/wide/ for 16:9)
    +0x10  s16 x6         eye A, eye B and mouth positions: top-left points in the body image
                          (-1 for faces without moving parts)
    +0x1C  s16 x2         where the cut-in is cropped from the body (checked: IKE's cut-in is the
                          body at 83,78 pixel for pixel)
    +0x20  s16 x8         not read by this module yet

``<NAME>.cms`` is an LZ10 TPL of 15 images: 0 the cut-in (192x128), 1 the body (336x336), 2-7 the
mouth frames, 8-10 eye A and 11-13 eye B frames, 14 the 64x64 menu face. Body and cut-in have
transparent holes where the eyes and mouth go.
"""
from __future__ import annotations

import io
import struct
from dataclasses import dataclass
from pathlib import Path

from PIL import Image

from . import lz10, tpl

RECORD_SIZE = 48
CUT_IN, BODY, MOUTHS, EYES_A, EYES_B, MENU = 0, 1, range(2, 8), range(8, 11), range(11, 14), 14


@dataclass(frozen=True)
class FaceRecord:
    fid: str
    large_fid: str
    name_id: str
    filename: str
    eye_a: tuple[int, int]
    eye_b: tuple[int, int]
    mouth: tuple[int, int]
    cut_in_origin: tuple[int, int]
    extra: tuple[int, ...]


def read_face_data(data: bytes) -> list[FaceRecord]:
    base = 0x20
    count, records = struct.unpack_from(">II", data, base)

    def string(pointer: int) -> str:
        if pointer == 0:
            return ""
        end = data.index(b"\0", base + pointer)
        return data[base + pointer:end].decode("cp932", errors="replace")

    result = []
    for i in range(count):
        offset = base + records + i * RECORD_SIZE
        fid, large, name, filename = (string(p) for p in struct.unpack_from(">4I", data, offset))
        values = struct.unpack_from(">16h", data, offset + 16)
        result.append(FaceRecord(fid, large, name, filename, values[0:2], values[2:4], values[4:6],
                                 values[6:8], values[8:]))
    return result


class FaceLibrary:
    """Faces of an extracted disc, looked up by cast name (``IKE``, ``L_IKE``) or FID."""

    def __init__(self, files_dir: Path | str, wide: bool = False):
        self._dir = Path(files_dir) / "Face"
        self._wide = wide
        data_path = (self._dir / "wide" / "facedata.bin") if wide else (self._dir / "facedata.bin")
        self.records = read_face_data(data_path.read_bytes()) if data_path.is_file() else []
        self._by_fid = {}
        for record in self.records:
            self._by_fid.setdefault(record.fid, (record, False))
            self._by_fid.setdefault(record.large_fid, (record, True))
        self._images: dict[str, list[Image.Image]] = {}

    def lookup(self, name: str) -> tuple[FaceRecord, bool] | None:
        """(record, large) for a cast name (without FID_) or a full FID."""
        fid = name if name.startswith("FID_") else "FID_" + name
        return self._by_fid.get(fid)

    def images(self, record: FaceRecord) -> list[Image.Image]:
        if record.filename not in self._images:
            folder = self._dir / "wide" if self._wide and (self._dir / "wide" / record.filename).is_file() else self._dir
            raw = (folder / record.filename).read_bytes()
            self._images[record.filename] = [im.convert("RGBA") for im in
                                             tpl.read_tpl_images(io.BytesIO(lz10.decompress(raw)))]
        return self._images[record.filename]

    def compose(self, name: str, *, eyes: int = 0, mouth: int = 0) -> Image.Image | None:
        """The portrait for a cast name with eye frame ``eyes`` (0-2) and mouth frame ``mouth`` (0-5):
        the body for ``L_`` names, the cut-in otherwise. None when the face is unknown."""
        found = self.lookup(name)
        if found is None:
            return None
        record, large = found
        try:
            images = self.images(record)
        except (OSError, ValueError):
            return None
        body = images[BODY].copy()
        parts = ((EYES_A, record.eye_a, eyes), (EYES_B, record.eye_b, eyes), (MOUTHS, record.mouth, mouth))
        for frames, point, frame in parts:
            if point[0] < 0 or len(images) <= frames[-1]:
                continue
            part = images[frames[min(frame, len(frames) - 1)]]
            layer = Image.new("RGBA", body.size)
            layer.paste(part, point)
            body = Image.alpha_composite(layer, body)  # the parts sit behind the body's holes
        if large:
            return body
        x, y = record.cut_in_origin
        width, height = images[CUT_IN].size
        if x < 0:
            return images[CUT_IN]
        return body.crop((x, y, x + width, y + height))
