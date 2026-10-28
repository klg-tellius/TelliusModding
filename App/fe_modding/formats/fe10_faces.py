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
import re
import struct
from dataclasses import dataclass
from pathlib import Path

from PIL import Image

from . import fe8data, fe10data, lz10, tpl

RECORD_SIZE = 48
CUT_IN, BODY, MOUTHS, EYES_A, EYES_B, MENU = 0, 1, range(2, 8), range(8, 11), range(11, 14), 14
NAME_RE = re.compile(r"^[A-Z0-9_]{1,24}$")


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


def _record_layout(data: bytes) -> tuple[int, int]:
    if len(data) < 0x28:
        raise ValueError("Face/facedata.bin is truncated.")
    size, data_size = struct.unpack_from(">II", data)
    if size != len(data) or 0x20 + data_size > len(data):
        raise ValueError("Face/facedata.bin has an invalid container header.")
    count, records = struct.unpack_from(">II", data, 0x20)
    start = 0x20 + records
    if records < 8 or start + count * RECORD_SIZE > 0x20 + data_size:
        raise ValueError("Face/facedata.bin has an invalid record array.")
    return count, start


def _validate_record(record: FaceRecord) -> None:
    if not record.fid.startswith("FID_"):
        raise ValueError("The face ID must start with FID_.")
    if not record.large_fid.startswith("FID_L_"):
        raise ValueError("The large face ID must start with FID_L_.")
    if not record.name_id.startswith("MPID_"):
        raise ValueError("The name key must start with MPID_.")
    if not record.filename.lower().endswith(".cms") or "/" in record.filename or "\\" in record.filename:
        raise ValueError("The portrait filename must be a .cms file name.")
    values = (*record.eye_a, *record.eye_b, *record.mouth, *record.cut_in_origin, *record.extra)
    if len(values) != 16 or any(not -0x8000 <= int(value) <= 0x7FFF for value in values):
        raise ValueError("Face coordinates and unknown values must fit signed 16-bit fields.")


def patch_face_record(data: bytes, index: int, record: FaceRecord) -> bytes:
    """Replace one FE10 face record, retaining the rest of the container verbatim.

    New strings are appended to the data pool and the four record pointers remain on the
    relocation list. Old, now-unused pool strings are intentionally retained.
    """
    _validate_record(record)
    records = read_face_data(data)
    if not 0 <= index < len(records):
        raise IndexError(f"No face record {index}.")
    for other_index, other in enumerate(records):
        if other_index != index and other.fid == record.fid:
            raise ValueError(f"{record.fid} already exists.")
    _count, start = _record_layout(data)
    offset = start + index * RECORD_SIZE
    for field, value in enumerate((record.fid, record.large_fid, record.name_id, record.filename)):
        data, pointer = fe8data._label_pointer(data, value, append=True)
        out = bytearray(data)
        fe8data._pack_pointer(out, offset + field * 4, pointer)
        data = bytes(out)
    out = bytearray(data)
    struct.pack_into(">16h", out, offset + 16, *record.eye_a, *record.eye_b, *record.mouth,
                     *record.cut_in_origin, *record.extra)
    return bytes(out)


def add_face_record(data: bytes, copy_of: int, name: str, name_id: str) -> tuple[bytes, int]:
    """Append a record cloned from ``copy_of`` and give it a new safe texture slot."""
    records = read_face_data(data)
    if not 0 <= copy_of < len(records):
        raise IndexError(f"No face record {copy_of}.")
    name = name.strip().upper().removeprefix("FID_")
    if not NAME_RE.fullmatch(name) or name.startswith("L_"):
        raise ValueError("Use capital letters, digits and _ (up to 24), not starting with L_.")
    if not name_id.startswith("MPID_"):
        raise ValueError("The name key must start with MPID_.")
    fid, filename = f"FID_{name}", f"{name}.cms"
    if any(record.fid == fid for record in records):
        raise ValueError(f"{fid} already exists.")
    if any(record.filename.casefold() == filename.casefold() for record in records):
        raise ValueError(f"{filename} already exists.")

    count, start = _record_layout(data)
    source = start + copy_of * RECORD_SIZE
    block = data[source:source + RECORD_SIZE]
    insert_at = start + count * RECORD_SIZE
    data = fe10data.insert_bytes(data, insert_at, block, (0, 4, 8, 12))
    out = bytearray(data)
    struct.pack_into(">I", out, 0x20, count + 1)
    clone = records[copy_of]
    new = FaceRecord(fid, f"FID_L_{name}", name_id, filename, clone.eye_a, clone.eye_b, clone.mouth,
                     clone.cut_in_origin, clone.extra)
    data = patch_face_record(bytes(out), count, new)
    return data, count


def remove_face_record(data: bytes, index: int) -> bytes:
    """Remove a face record. Its possibly shared pool strings remain available to other rows."""
    count, start = _record_layout(data)
    if not 0 <= index < count:
        raise IndexError(f"No face record {index}.")
    if count == 1:
        raise ValueError("The last face record cannot be removed.")
    if index == 0:
        # The array pointer targets the first row. Point it at the following row so the generic
        # delete operation moves it back to the unchanged array start.
        out = bytearray(data)
        struct.pack_into(">I", out, 0x24, struct.unpack_from(">I", out, 0x24)[0] + RECORD_SIZE)
        data = bytes(out)
    data = fe10data.delete_bytes(data, start + index * RECORD_SIZE, RECORD_SIZE)
    out = bytearray(data)
    struct.pack_into(">I", out, 0x20, count - 1)
    return bytes(out)


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
        return compose_face(record, images, large=large, eyes=eyes, mouth=mouth)


def compose_face(record: FaceRecord, images: list[Image.Image], *, large: bool = False,
                 eyes: int = 0, mouth: int = 0) -> Image.Image:
    """Compose one already-decoded FE10 portrait.

    Kept separate from :class:`FaceLibrary` so the portrait editor can
    preview unsaved texture replacements without rereading the on-disc file.
    """
    if len(images) <= BODY:
        raise ValueError("The portrait has no body image.")
    body = images[BODY].copy().convert("RGBA")
    parts = ((EYES_A, record.eye_a, eyes), (EYES_B, record.eye_b, eyes), (MOUTHS, record.mouth, mouth))
    for frames, point, frame in parts:
        if point[0] < 0 or len(images) <= frames[-1]:
            continue
        part = images[frames[min(frame, len(frames) - 1)]].convert("RGBA")
        layer = Image.new("RGBA", body.size)
        layer.paste(part, point)
        body = Image.alpha_composite(layer, body)  # the parts sit behind the body's holes
    if large:
        return body
    if len(images) <= CUT_IN:
        raise ValueError("The portrait has no cut-in image.")
    x, y = record.cut_in_origin
    width, height = images[CUT_IN].size
    if x < 0:
        return images[CUT_IN].convert("RGBA")
    return body.crop((x, y, x + width, y + height))
