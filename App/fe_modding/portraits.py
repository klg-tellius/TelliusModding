"""Path of Radiance portraits: the face table (``Face/facedata.bin``) and the
texture sets (``Face/<NAME>.cms``) of a project.

The loose ``Face/facedata.bin`` is the file edited here; the build copies it
into ``system.cmp``, whose copy is the one the game reads
(``ModProject.sync_system_archive``). A character's ``FID_`` (FE8Data) names
its small portrait; the game pairs it with ``FID_L_<same name>`` for the
large one (status screen, level-up, background scenes), so a new portrait
always gets both records. See wiki/formats/face-data.md.
"""

from __future__ import annotations

import io
import re
from dataclasses import replace
from pathlib import Path

from PIL import Image

from .formats import lz10, tpl
from .formats.fe9_portraits import (FACE_BODY_SIZE, FaceRecord, build_face_cms, build_face_table,
                                    large_face_id, read_face_table)
from .game_profile import files_root_of

NAME_RE = re.compile(r"^[A-Z0-9_]{1,24}$")
NO_POSITION = (-1, -1)


def face_dir(project) -> Path:
    return files_root_of(project) / "Face"


def face_table_path(project) -> Path:
    return face_dir(project) / "facedata.bin"


def load_faces(project) -> list[FaceRecord]:
    """Every face record, in file order."""
    return list(read_face_table(face_table_path(project).read_bytes()).values())


def save_faces(project, records: list[FaceRecord]) -> None:
    project.write_keeping_original(face_table_path(project), build_face_table(records))


def update_face(project, record: FaceRecord) -> None:
    """Replace the record with the same ``FID_``."""
    records = load_faces(project)
    for i, old in enumerate(records):
        if old.fid == record.fid:
            records[i] = record
            break
    else:
        raise KeyError(record.fid)
    save_faces(project, records)


def read_texture_set(path: Path) -> bytes:
    return lz10.decompress(Path(path).read_bytes())


def rebuild_with_new_palette(tpl_bytes: bytes, replacements: dict[int, Image.Image]) -> bytes:
    """Re-encode a C8 texture set with ``replacements`` (image index -> new
    picture, resized to the slot) and a fresh palette for every group of
    images that shares one, so a new picture keeps its own colours instead
    of being matched to the old palette. Wrap modes are kept."""
    import struct

    infos = tpl.read_tpl_image_info(io.BytesIO(tpl_bytes))
    if any(info.format != tpl.FORMAT_C8 for info in infos):
        raise ValueError("Only palette (C8) texture sets can get a new palette.")
    images = tpl.read_tpl_images(io.BytesIO(tpl_bytes))
    count, table = struct.unpack_from(">II", tpl_bytes, 4)
    groups: dict[int, tuple[list[Image.Image], list[int]]] = {}
    for i in range(count):
        header, palette = struct.unpack_from(">II", tpl_bytes, table + 8 * i)
        wrap = struct.unpack_from(">I", tpl_bytes, header + 12)[0]
        image = images[i]
        if i in replacements:
            image = replacements[i].convert("RGBA").resize(image.size, Image.LANCZOS)
        group = groups.setdefault(palette, ([], []))
        group[0].append(image)
        group[1].append(wrap)
    order = []  # images must keep their indices: refuse interleaved groups
    for palette, (members, _wraps) in groups.items():
        order += [palette] * len(members)
    expected = [struct.unpack_from(">II", tpl_bytes, table + 8 * i)[1] for i in range(count)]
    if order != expected:
        raise ValueError("This texture set mixes its palettes; it can only take the existing palette.")
    return tpl.build_c8_tpl(list(groups.values()))


def _fit(image: Image.Image, size: tuple[int, int]) -> Image.Image:
    """``image`` scaled to fit ``size`` and centred on its bottom edge, the
    way the game anchors a portrait (middle of the bottom edge)."""
    image = image.convert("RGBA")
    scale = min(size[0] / image.width, size[1] / image.height)
    fitted = image.resize((max(1, round(image.width * scale)), max(1, round(image.height * scale))),
                          Image.LANCZOS)
    canvas = Image.new("RGBA", size, (0, 0, 0, 0))
    canvas.paste(fitted, ((size[0] - fitted.width) // 2, size[1] - fitted.height))
    return canvas


def default_menu_face(body: Image.Image) -> Image.Image:
    """A 64x64 menu face cut from the top middle of a small body picture."""
    body = body.convert("RGBA")
    side = min(body.width, body.height, 96)
    left = (body.width - side) // 2
    return body.crop((left, 0, left + side, side)).resize((64, 64), Image.LANCZOS)


def add_portrait(project, name: str, name_key: str, small_body: Image.Image,
                 large_body: Image.Image | None = None, *,
                 small_mouths: list[Image.Image] | None = None, small_eyes: list[Image.Image] | None = None,
                 small_positions: tuple[tuple[int, int], tuple[int, int], tuple[int, int]] | None = None,
                 large_mouths: list[Image.Image] | None = None, large_eyes: list[Image.Image] | None = None,
                 large_positions: tuple[tuple[int, int], tuple[int, int], tuple[int, int]] | None = None,
                 menu_face: Image.Image | None = None, depth: int = 0, menu_offset: int = 0) -> tuple[str, str]:
    """Add ``FID_<name>`` and ``FID_L_<name>`` with new texture sets
    ``Face/<name>.cms`` and ``Face/L_<name>.cms``; return both IDs.

    ``small_body`` is fitted to 192x128 (the size of every small portrait);
    ``large_body`` keeps its size (retail: up to 256x296, 232x296 for Ike)
    and defaults to the small body scaled up. Positions are
    ``(left eye, right eye, mouth)`` top-left corners on the body; parts are
    optional (no eyes or mouth: a still picture)."""
    name = name.strip().upper().removeprefix("FID_")
    if not NAME_RE.match(name) or name.startswith("L_"):
        raise ValueError("Use capital letters, digits and _ (up to 24), not starting with L_.")
    records = load_faces(project)
    small_id, large_id = "FID_" + name, large_face_id("FID_" + name)
    taken = {r.fid for r in records}
    files = {r.filename.casefold() for r in records}
    for fid, filename in ((small_id, f"{name}.cms"), (large_id, f"L_{name}.cms")):
        if fid in taken:
            raise ValueError(f"{fid} already exists.")
        if filename.casefold() in files or (face_dir(project) / filename).exists():
            raise ValueError(f"Face/{filename} already exists.")
    if not name_key.startswith("MPID_"):
        raise ValueError("The name key is an MPID_ label (the nameplate text).")

    small = _fit(small_body, FACE_BODY_SIZE)
    if large_body is None:
        large = small.resize((FACE_BODY_SIZE[0] * 3 // 2, FACE_BODY_SIZE[1] * 3 // 2), Image.LANCZOS)
    else:
        large = large_body.convert("RGBA")
    menu = menu_face if menu_face is not None else default_menu_face(small)

    def record(fid, filename, mouths, eyes, positions, flags, mini):
        left, right, mouth = positions if positions else (NO_POSITION,) * 3
        return FaceRecord(fid, name_key, filename, tuple(left) if flags & 1 else NO_POSITION,
                          tuple(right) if flags & 1 else NO_POSITION, tuple(mouth) if flags & 2 else NO_POSITION,
                          flags, mini, 1 if flags & 2 else 0, depth, menu_offset)

    small_tpl, small_flags = build_face_cms(small, small_mouths, small_eyes, menu)
    large_tpl, large_flags = build_face_cms(large, large_mouths, large_eyes, None)
    for flags, positions, label in ((small_flags, small_positions, "small"), (large_flags, large_positions, "large")):
        if flags and not positions:
            raise ValueError(f"Give the eye and mouth positions of the {label} portrait's parts.")
    mini = 1 + 6 * bool(small_flags & 2) + 6 * bool(small_flags & 1)
    new = [record(small_id, f"{name}.cms", small_mouths, small_eyes, small_positions, small_flags, mini),
           record(large_id, f"L_{name}.cms", large_mouths, large_eyes, large_positions, large_flags, 0xFFFF)]
    face_dir(project).mkdir(parents=True, exist_ok=True)
    (face_dir(project) / f"{name}.cms").write_bytes(lz10.compress(small_tpl))
    (face_dir(project) / f"L_{name}.cms").write_bytes(lz10.compress(large_tpl))
    save_faces(project, records + new)
    return small_id, large_id


def remove_portrait(project, fid: str) -> list[str]:
    """Remove an added portrait (both sizes) and its texture files; refuse a
    face the extracted table already had. Returns the removed IDs."""
    original = project.extracted_bytes(face_table_path(project))
    retail = set(read_face_table(original)) if original else set()
    small = "FID_" + fid.removeprefix("FID_").removeprefix("L_")
    ids = {small, large_face_id(small)}
    if ids & retail:
        raise ValueError("The game's own portraits cannot be removed.")
    records = load_faces(project)
    kept = [r for r in records if r.fid not in ids]
    for r in records:
        if r.fid in ids and not any(k.filename == r.filename for k in kept):
            path = face_dir(project) / r.filename
            if path.exists():
                path.unlink()
    save_faces(project, kept)
    return sorted(ids & {r.fid for r in records})


def with_fields(record: FaceRecord, **fields) -> FaceRecord:
    return replace(record, **fields)
