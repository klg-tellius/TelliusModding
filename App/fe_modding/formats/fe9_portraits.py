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
    mini_portrait: int  # +1a: texture index of the 64x64 menu face, 0xffff for none (L_ faces)
    default_mouth: int
    depth: int
    menu_offset: int = 0  # +1e (s16): pixels the face is lowered in menu panels


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
        flags, mini, default, depth, menu_offset = struct.unpack_from(">HHBBh", data, offset + 24)
        if not fid.startswith("FID_") or fid in result:
            raise ValueError(f"Invalid/duplicate face ID: {fid}")
        result[fid] = FaceRecord(fid, name, filename, coords[:2], coords[2:4],
                                 coords[4:], flags, mini, default, depth, menu_offset)
    return result


def build_face_table(records: list[FaceRecord]) -> bytes:
    """Write ``face/facedata.bin`` from its records, in the given order.

    Same layout as the retail file (rebuilt byte for byte): the labeled-section
    header, ``count`` and the record offset (8), the 32-byte records, then the
    label pool (every string once, sorted by byte value, padded to 4) and the
    relocation table (the record-offset word and the three string words of
    each record). No sections."""
    fids = [r.fid for r in records]
    if len(set(fids)) != len(fids):
        raise ValueError("Duplicate face ID")
    base = 8 + 32 * len(records)
    offsets, pool = {}, bytearray()
    for text in sorted({s for r in records for s in (r.fid, r.name_id, r.filename)}, key=str.encode):
        offsets[text] = base + len(pool)
        pool += text.encode("ascii") + b"\0"
    pool += bytes(-len(pool) % 4)
    body = bytearray(struct.pack(">II", len(records), 8))
    relocations = [4]
    for r in records:
        relocations += [len(body), len(body) + 4, len(body) + 8]
        body += struct.pack(">III6hHHBBh", offsets[r.fid], offsets[r.name_id], offsets[r.filename],
                            *r.left_eye, *r.right_eye, *r.mouth, r.flags, r.mini_portrait,
                            r.default_mouth, r.depth, r.menu_offset)
    body += pool
    size = 32 + len(body) + 4 * len(relocations)
    header = struct.pack(">8I", size, len(body), len(relocations), 0, 0, 0, 0, 0)
    return header + bytes(body) + struct.pack(f">{len(relocations)}I", *relocations)


def large_face_id(fid: str) -> str:
    """The large portrait the game pairs with a small one: ``FID_IKE`` ->
    ``FID_L_IKE`` (main.dol builds it from the ``FID_L_`` prefix)."""
    return "FID_L_" + fid.removeprefix("FID_")


# Texture headers of a retail face set (IKE.cms): the body clamps, the eye
# frames and the menu face repeat; every image is C8 with nearest filtering.
FACE_BODY_SIZE = (192, 128)
LARGE_BODY_MAX = (256, 296)
MOUTH_SIZE = (24, 24)
LARGE_MOUTH_SIZE = (24, 32)
EYE_SIZE = (16, 16)
MENU_FACE_SIZE = (64, 64)


def build_face_cms(body: Image.Image, mouths: list[Image.Image] | None = None,
                   eyes: list[Image.Image] | None = None,
                   menu_face: Image.Image | None = None) -> tuple[bytes, int]:
    """Encode a portrait texture set (the decompressed ``Face/<NAME>.cms`` TPL).

    ``mouths``: six frames (two sets of three, the third of each closed);
    ``eyes``: six frames (left eye 0-2, right eye 3-5); ``menu_face``: the
    64x64 menu picture of small portraits. Returns ``(tpl bytes, flags)``
    where flags is the face record's parts byte (1 eyes, 2 mouth). Every image
    except the menu face shares one 256-colour RGB5A3 palette, as in retail;
    the menu face has its own."""
    from . import tpl

    mouths = list(mouths or [])
    eyes = list(eyes or [])
    if mouths and len(mouths) != 6:
        raise ValueError("A mouth needs six frames (two sets of three).")
    if eyes and len(eyes) != 6:
        raise ValueError("Eyes need six frames (three per eye).")
    shared = [body.convert("RGBA")] + [m.convert("RGBA") for m in mouths] + [e.convert("RGBA") for e in eyes]
    groups = [(shared, [0] * (1 + len(mouths)) + [1] * len(eyes))]
    if menu_face is not None:
        groups.append(([menu_face.convert("RGBA").resize(MENU_FACE_SIZE, Image.LANCZOS)], [1]))
    flags = (1 if eyes else 0) | (2 if mouths else 0)
    return tpl.build_c8_tpl(groups), flags


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
