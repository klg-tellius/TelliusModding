"""FE9 face records and texture composition, verified against the US executable.

See research/CONVERSATION_RENDERING.md. Coordinates are top-left offsets, not
centres. Texture 0 is the body; 1..6 are mouths; 7..12 are the two eyes.
"""
from __future__ import annotations

import struct
from dataclasses import dataclass
from PIL import Image, ImageOps


@dataclass(frozen=True)
class FaceRecord:
    fid: str
    name_id: str
    filename: str
    left_eye: tuple[int, int]
    right_eye: tuple[int, int]
    mouth: tuple[int, int]
    flags: int
    unknown_1a: int
    default_mouth: int
    depth: int


def read_face_table(data: bytes) -> dict[str, FaceRecord]:
    if len(data) < 40:
        raise ValueError("Truncated face table")
    size, reloc = struct.unpack_from(">II", data)
    count, records = struct.unpack_from(">II", data, 32)
    records += 32
    if size != len(data) or records < 40 or records + count * 32 > reloc + 32:
        raise ValueError("Invalid face table bounds")

    def string(pointer: int) -> str:
        start = pointer + 32
        end = data.find(b"\0", start)
        if not 40 <= start < end < reloc + 32:
            raise ValueError("Invalid face string pointer")
        return data[start:end].decode("ascii")

    result = {}
    for offset in range(records, records + count * 32, 32):
        fid, name, filename = (string(p) for p in struct.unpack_from(">III", data, offset))
        coords = struct.unpack_from(">6h", data, offset + 12)
        flags, textures, default, depth = struct.unpack_from(">HHBB", data, offset + 24)
        if not fid.startswith("FID_") or fid in result:
            raise ValueError(f"Invalid/duplicate face ID: {fid}")
        result[fid] = FaceRecord(fid, name, filename, coords[:2], coords[2:4],
                                 coords[4:], flags, textures, default, depth)
    return result


@dataclass
class FaceAsset:
    record: FaceRecord
    images: tuple[Image.Image, ...]

    def compose(self, *, mouth_variant: int | None = None, mouth_frame: int = 2,
                left_eye_frame: int = 0, right_eye_frame: int = 0,
                mirrored: bool = False, brightness: int = 255) -> Image.Image:
        if not self.images:
            raise ValueError(f"No textures for {self.record.fid}")
        out = self.images[0].convert("RGBA").copy()
        rec = self.record

        def paste(index: int, xy: tuple[int, int]) -> None:
            if xy[0] < 0 or xy[1] < 0:
                return
            if not 0 <= index < len(self.images):
                raise ValueError(f"{rec.fid}: missing texture {index}")
            out.alpha_composite(self.images[index], xy)

        if rec.flags & 2:
            variant = (0 if rec.default_mouth else 1) if mouth_variant is None else mouth_variant
            paste(1 + 3 * variant + mouth_frame, rec.mouth)
        if rec.flags & 1:
            base = 7 if rec.flags & 2 else 1
            if rec.left_eye[0] != rec.right_eye[0]:
                paste(base + left_eye_frame, rec.left_eye)
            paste(base + 3 + right_eye_frame, rec.right_eye)
        if brightness != 255:
            r, g, b, a = out.split()
            table = [i * brightness // 255 for i in range(256)]
            out = Image.merge("RGBA", (r.point(table), g.point(table), b.point(table), a))
        return ImageOps.mirror(out) if mirrored else out
