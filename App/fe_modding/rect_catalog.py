"""Rect resource catalogue and cross-file RID references for both Tellius games."""
from __future__ import annotations

import io
import re
from dataclasses import dataclass
from pathlib import Path

from PIL import Image

from .formats import fe10_rect, lz10, message, rect, soundroom, tpl
from .formats.cmb import read_cmb, write_cmb
from .formats.cmb.model import PUSHSTR_OPS
from .games import Game

_IMAGE_TYPES = (rect.RectLayer, rect.ColorQuadLayer)


@dataclass(frozen=True)
class Reference:
    kind: str
    path: Path
    location: str


def rect_paths(project) -> list[Path]:
    root = project.files_dir
    if not root.is_dir():
        return []
    return sorted(
        (path for path in root.rglob("*.bin")
         if path.is_file() and (path.name.casefold() == "rect.bin" or path.name.casefold().startswith("rect"))),
        key=lambda path: str(path.relative_to(root)).casefold(),
    )


def is_fe10(project) -> bool:
    return project.game == Game.RADIANT_DAWN


def read_doc(project, path: Path):
    raw = path.read_bytes()
    return fe10_rect.read_editable_rect(raw) if is_fe10(project) else rect.parse_rect(raw)


def resources(doc):
    return doc.resources


def image_layers(resource):
    for index, layer in enumerate(resource.layers):
        if isinstance(layer, _IMAGE_TYPES) or isinstance(layer, fe10_rect.EditableLayer) and layer.kind in (1, 6):
            yield index, layer


def layer_file(layer):
    return layer.file


def layer_texture(layer):
    return layer.texture


def _strings(layer):
    if isinstance(layer, rect.TextboxLayer):
        return [(slot, getattr(layer, slot)) for slot in ("window", "panel", "marker")]
    if isinstance(layer, fe10_rect.EditableLayer) and layer.kind not in (1, 6):
        return [(f"pointer {offset:#x}", value) for offset, value in layer.strings.items()]
    return []


def _message_matches(raw: bytes, rid: str, fe10: bool):
    short = rid.removeprefix("RID_").encode("cp932")
    if fe10:
        # FE10's 04 commands store the RID without its prefix.
        pattern = rb"\x04(?:R:|B:|b:)" + re.escape(short) + rb"\|"
    else:
        pattern = rb"\$(?:R|B)" + re.escape(short) + rb"\|"
    return list(re.finditer(pattern, raw))


def collect_references(project, rid: str, paths: list[Path] | None = None) -> list[Reference]:
    paths = paths if paths is not None else rect_paths(project)
    found = []
    for path in paths:
        try:
            doc = read_doc(project, path)
            for resource in resources(doc):
                for index, layer in enumerate(resource.layers):
                    for slot, value in _strings(layer):
                        if value == rid:
                            found.append(Reference("Rect", path, f"{resource.name}, layer {index}, {slot}"))
        except Exception as exc:
            found.append(Reference("Unreadable rect", path, str(exc)))
    script_dir = project.files_dir / "Scripts"
    if script_dir.is_dir():
        needle = rid.encode("cp932")
        for path in sorted(script_dir.rglob("*.cmb")):
            try:
                raw = path.read_bytes()
                if needle not in raw:
                    continue
                script = read_cmb(raw)
                for number, function in enumerate(script.functions):
                    for instruction in function.instructions():
                        if instruction.op in PUSHSTR_OPS and instruction.operands and instruction.operands[0] == rid:
                            found.append(Reference("Script", path, function.id_string or f"function {number}"))
            except Exception as exc:
                found.append(Reference("Unreadable script", path, str(exc)))
    mess_dir = project.files_dir / "Mess"
    if mess_dir.is_dir():
        needle = rid.removeprefix("RID_").encode("cp932")
        for path in sorted(mess_dir.rglob("*.m")):
            try:
                if needle not in path.read_bytes():
                    continue
                for item in message.read_messages_path(path):
                    raw = item.text.encode("cp437")
                    for _match in _message_matches(raw, rid, is_fe10(project)):
                        found.append(Reference("Dialogue", path, item.speaker))
            except Exception as exc:
                found.append(Reference("Unreadable dialogue", path, str(exc)))
    if not is_fe10(project):
        sound = project.files_dir / "soundroom.bin"
        if sound.is_file():
            try:
                for index, item in enumerate(soundroom.read_soundroom_path(sound)):
                    if item.name == rid:
                        found.append(Reference("Sound Room", sound, f"entry {index + 1}"))
            except Exception as exc:
                found.append(Reference("Unreadable Sound Room", sound, str(exc)))
    return found


def _rename_in_doc(doc, old: str, new: str):
    changed = False
    for resource in resources(doc):
        if resource.name == old:
            resource.name = new
            changed = True
        for layer in resource.layers:
            if isinstance(layer, rect.TextboxLayer):
                for slot in ("window", "panel", "marker"):
                    if getattr(layer, slot) == old:
                        setattr(layer, slot, new)
                        changed = True
            elif isinstance(layer, fe10_rect.EditableLayer) and layer.kind not in (1, 6):
                for offset, value in list(layer.strings.items()):
                    if value == old:
                        layer.strings[offset] = new
                        changed = True
    if old in doc.address_order:
        doc.address_order = [new if value == old else value for value in doc.address_order]
    if changed:
        doc.resources.sort(key=lambda item: item.name.encode("cp932"))
    return changed


def _rename_message_text(text: str, old: str, new: str, fe10: bool) -> str:
    raw = text.encode("cp437")
    old_short = old.removeprefix("RID_").encode("cp932")
    new_short = new.removeprefix("RID_").encode("cp932")
    if fe10:
        pattern = rb"(\x04(?:R:|B:|b:))" + re.escape(old_short) + rb"(?=\|)"
    else:
        pattern = rb"(\$(?:R|B))" + re.escape(old_short) + rb"(?=\|)"
    return re.sub(pattern, lambda match: match.group(1) + new_short, raw).decode("cp437")


def _require_roundtrip(project, path: Path, doc) -> None:
    if is_fe10(project) and doc.build() != path.read_bytes():
        raise ValueError(f"{path.name} cannot be edited safely: the FE10 writer does not reproduce this file")


def prepare_rename(project, old: str, new: str, paths: list[Path] | None = None) -> dict[Path, bytes]:
    """Build every changed file in memory; no writes until all readers and writers succeed."""
    paths = paths if paths is not None else rect_paths(project)
    if not new.startswith("RID_") or new == "RID_" or "\0" in new:
        raise ValueError("A RID must start with RID_ and contain a name")
    new.encode("cp932")
    if new == old:
        return {}
    docs = {path: read_doc(project, path) for path in paths}
    for path, doc in docs.items():
        _require_roundtrip(project, path, doc)
    if not any(any(item.name == old for item in resources(doc)) for doc in docs.values()):
        raise ValueError(f"{old} was not found")
    if any(any(item.name == new for item in resources(doc)) for doc in docs.values()):
        raise ValueError(f"{new} already exists")
    changes = {}
    for path, doc in docs.items():
        if _rename_in_doc(doc, old, new):
            changes[path] = doc.build()
    script_dir = project.files_dir / "Scripts"
    if script_dir.is_dir():
        for path in sorted(script_dir.rglob("*.cmb")):
            raw = path.read_bytes()
            if old.encode("cp932") not in raw:
                continue
            script = read_cmb(raw)
            if old not in script.pool:
                continue
            script.pool = [new if value == old else value for value in script.pool]
            for function in script.functions:
                for instruction in function.instructions():
                    if instruction.op in PUSHSTR_OPS and instruction.operands and instruction.operands[0] == old:
                        instruction.operands[0] = new
            changes[path] = write_cmb(script)
    mess_dir = project.files_dir / "Mess"
    if mess_dir.is_dir():
        for path in sorted(mess_dir.rglob("*.m")):
            if old.removeprefix("RID_").encode("cp932") not in path.read_bytes():
                continue
            items = message.read_messages_path(path)
            updated = [message.Message(item.speaker, _rename_message_text(item.text, old, new, is_fe10(project)))
                       for item in items]
            if updated != items:
                changes[path] = message.write_messages(updated, message.read_text_order_path(path))
    if not is_fe10(project):
        path = project.files_dir / "soundroom.bin"
        if path.is_file():
            entries = soundroom.read_soundroom_path(path)
            if any(entry.name == old for entry in entries):
                for entry in entries:
                    if entry.name == old:
                        entry.name = new
                changes[path] = soundroom.build_soundroom(entries)
    return changes


def save_changes(project, changes: dict[Path, bytes], changelog, note: str) -> None:
    """Write prepared changes, restoring previous bytes if any write fails."""
    originals = {path: path.read_bytes() if path.exists() else None for path in changes}
    written = []
    try:
        for path, data in changes.items():
            written.append(path)
            project.write_keeping_original(path, data)
    except Exception:
        for path in reversed(written):
            old = originals[path]
            if old is None:
                path.unlink(missing_ok=True)
            else:
                path.write_bytes(old)
        raise
    for path in changes:
        changelog.append(str(path.relative_to(project.files_dir)), note)


def image_path(project, file_name: str) -> Path:
    parts = Path(file_name.replace("\\", "/"))
    if parts.is_absolute() or ".." in parts.parts:
        raise ValueError(f"Invalid image path: {file_name}")
    return project.files_dir / parts


def preview_image(project, layer) -> Image.Image:
    path = image_path(project, layer_file(layer))
    raw = path.read_bytes()
    if path.suffix.casefold() == ".cms":
        raw = lz10.decompress(raw)
    images = tpl.read_tpl_images(io.BytesIO(raw))
    return images[layer_texture(layer)]


def new_texture_path(project, rect_path: Path) -> tuple[Path, str]:
    folder = rect_path.parent
    if folder.name.casefold() == "s":
        name = rect.free_tpl_name(folder)
    else:
        for index in range(1, 10000):
            name = f"rid_{index:04d}.tpl"
            if not (folder / name).exists():
                break
        else:
            raise ValueError("No free texture filename")
    path = folder / name
    return path, path.relative_to(project.files_dir).as_posix()


def encode_images(images: list[Image.Image]) -> bytes:
    if not images:
        raise ValueError("Choose at least one image")
    size = images[0].size
    if not 0 < size[0] <= 1024 or not 0 < size[1] <= 1024:
        raise ValueError("Images must fit within 1024 by 1024 pixels")
    if any(image.size != size for image in images):
        raise ValueError("All images for a RID must have the same dimensions")
    return tpl.build_tpl([(image.convert("RGBA"), tpl.FORMAT_CMPR) for image in images], wrap=tpl.WRAP_CLAMP)


def prepare_add(project, rect_path: Path, rid: str, images: list[Image.Image]) -> dict[Path, bytes]:
    if not rid.startswith("RID_") or rid == "RID_":
        raise ValueError("A RID must start with RID_ and contain a name")
    rid.encode("cp932")
    if any(any(item.name == rid for item in resources(read_doc(project, path))) for path in rect_paths(project)):
        raise ValueError(f"{rid} already exists")
    image_bytes = encode_images(images)
    image_file, reference = new_texture_path(project, rect_path)
    doc = read_doc(project, rect_path)
    _require_roundtrip(project, rect_path, doc)
    width, height = images[0].size
    template = next((item for item in doc.resources if any(image_layers(item))), None)
    if is_fe10(project):
        resource = fe10_rect.new_image_resource(rid, reference, width, height, len(images))
        if template is not None:
            descriptor = bytearray(resource.descriptor)
            descriptor[6:8] = template.descriptor[6:8]  # destination file's usual draw depth
            resource.descriptor = bytes(descriptor)
        doc.add(resource)
    else:
        resource = rect.new_background(rid, reference, width, height, textures=len(images))
        if template is not None:
            resource.depth = template.depth
        doc.add(resource)
    return {image_file: image_bytes, rect_path: doc.build()}


def prepare_replace(project, rect_path: Path, rid: str, layer_index: int, image: Image.Image) -> dict[Path, bytes]:
    doc = read_doc(project, rect_path)
    _require_roundtrip(project, rect_path, doc)
    resource = doc.find(rid)
    if resource is None or not 0 <= layer_index < len(resource.layers):
        raise ValueError("The selected RID layer no longer exists")
    layer = resource.layers[layer_index]
    if layer_index not in [index for index, _layer in image_layers(resource)]:
        raise ValueError("The selected layer has no image")
    # A new file ensures other resources and other layers keep their original texture.
    original = preview_image(project, layer)
    image = image.convert("RGBA").resize(original.size, Image.Resampling.LANCZOS)
    image_bytes = encode_images([image])
    image_file, reference = new_texture_path(project, rect_path)
    layer.file = reference
    if isinstance(layer, fe10_rect.EditableLayer):
        raw = bytearray(layer.raw)
        raw[0x12] = 0
        layer.raw = bytes(raw)
    else:
        layer.texture = 0
    return {image_file: image_bytes, rect_path: doc.build()}
