"""Typed FE9 rect properties, validation, and an illustrative RID preview."""
from __future__ import annotations

import copy
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageFont, ImageOps

from . import rect_catalog
from .formats import message, rect
from .games import Game


@dataclass(frozen=True)
class Field:
    name: str
    label: str
    kind: str = "int"  # int, float, text, rect, colors, seats
    minimum: int | None = None
    maximum: int | None = None


RESOURCE_FIELDS = (
    Field("mode", "Composition mode (0 stack, 1 frames, 2 fade)", minimum=0, maximum=2),
    Field("depth", "Draw depth", minimum=0, maximum=65535),
    Field("duration", "Animation period (seconds)", "float"),
    Field("brightness", "Brightness (0 = default)", minimum=0, maximum=255),
    Field("effect", "Ambient effect (0 none, 1 snow, 2 altar, 3 sand, 4 mist)", minimum=0, maximum=4),
)
LAYER_FIELDS = {
    rect.TextLayer: (
        Field("text", "Text or message ID", "text"), Field("x", "X", minimum=-32768, maximum=32767),
        Field("y", "Y", minimum=-32768, maximum=32767), Field("depth", "Text depth", minimum=-128, maximum=127),
        Field("style_a", "Shadow", minimum=0, maximum=255), Field("style_b", "Outline", minimum=0, maximum=255),
        Field("color", "Text palette", minimum=0, maximum=255), Field("align", "Align (-1 left, 0 center, 1 right)", minimum=-1, maximum=1),
    ),
    rect.TextboxLayer: (
        *(Field(name, label, "text") for name, label in (("window", "Window RID"), ("panel", "Panel RID"), ("marker", "Page cursor RID"))),
        *(Field(name, label, minimum=-32768, maximum=32767) for name, label in
          (("text_x", "Text X"), ("text_y", "Text Y"), ("marker_x", "Cursor X"), ("marker_y", "Cursor Y"))),
        Field("width", "Text width", minimum=-32768, maximum=32767),
        *(Field(name, label, minimum=0, maximum=255) for name, label in
          (("style_a", "Shadow"), ("style_b", "Outline"), ("speed", "Typing speed"),
           ("block", "Block flag"), ("dynamic", "Dynamic flag"))),
        Field("line_height", "Line height", minimum=0, maximum=255),
        Field("lines", "Lines", minimum=0, maximum=255),
        Field("seat", "Portrait seat (-1 = none)", minimum=-1, maximum=127),
    ),
    rect.GradientLayer: (Field("rect", "Bounds x0,y0,x1,y1", "rect"), Field("colors", "Corner colors: TL, TR, BL, BR", "colors")),
    rect.SeatsLayer: (Field("seats", "Seats: x,y,skip,facing,index (one per line)", "seats"),),
    rect.RectLayer: (
        Field("file", "Texture file", "text"), Field("texture", "Texture index", minimum=0, maximum=255),
        Field("src", "Source x0,y0,x1,y1", "unsigned_rect"), Field("dst", "Destination x0,y0,x1,y1", "rect"),
        Field("alpha", "Opacity", minimum=0, maximum=255), Field("flags", "Load flags", minimum=0, maximum=255),
    ),
    rect.ColorQuadLayer: (
        Field("file", "Texture file", "text"), Field("texture", "Texture index", minimum=0, maximum=255),
        Field("src", "Source x0,y0,x1,y1", "unsigned_rect"), Field("dst", "Destination x0,y0,x1,y1", "rect"),
        Field("alpha", "Opacity", minimum=0, maximum=255), Field("flags", "Load flags", minimum=0, maximum=255),
        Field("colors", "Corner colors: TL, TR, BL, BR", "colors"),
    ),
}


def fields_for(value) -> tuple[Field, ...]:
    if isinstance(value, rect.RectResource):
        return RESOURCE_FIELDS
    return LAYER_FIELDS.get(type(value), ())


def display(value, field: Field) -> str:
    item = getattr(value, field.name)
    if field.kind == "colors":
        return ", ".join("#" + "".join(f"{part:02X}" for part in color) for color in item)
    if field.kind == "seats":
        return "\n".join(", ".join(map(str, seat)) for seat in item)
    if field.kind in ("rect", "unsigned_rect"):
        return ", ".join(map(str, item))
    return str(item)


def parse(field: Field, raw: str):
    try:
        if field.kind == "text":
            raw.encode("shift_jis")
            if "\0" in raw:
                raise ValueError("NUL is not allowed")
            return raw
        if field.kind == "float":
            number = float(raw)
            if not 0 <= number <= 3600 or not number < float("inf"):
                raise ValueError("must be between 0 and 3600")
            return number
        if field.kind == "colors":
            colors = []
            for item in raw.split(","):
                item = item.strip().removeprefix("#")
                if len(item) != 8:
                    raise ValueError("use four #RRGGBBAA colors")
                colors.append(tuple(bytes.fromhex(item)))
            if len(colors) != 4:
                raise ValueError("use four #RRGGBBAA colors")
            return tuple(colors)
        if field.kind == "seats":
            seats = []
            for line in raw.splitlines():
                if not line.strip():
                    continue
                values = tuple(int(part.strip(), 0) for part in line.split(","))
                if len(values) != 5 or not all(-32768 <= n <= 32767 for n in values[:2]) or not 0 <= values[2] <= 65535 or not all(0 <= n <= 255 for n in values[3:]):
                    raise ValueError("each seat needs x,y,skip,facing,index in field range")
                seats.append(values)
            if len(seats) > 255:
                raise ValueError("too many seats")
            return seats
        if field.kind in ("rect", "unsigned_rect"):
            values = tuple(int(part.strip(), 0) for part in raw.split(","))
            lo, hi = (0, 65535) if field.kind == "unsigned_rect" else (-32768, 32767)
            if len(values) != 4 or any(not lo <= n <= hi for n in values):
                raise ValueError(f"four coordinates between {lo} and {hi} required")
            return values
        value = int(raw.strip(), 0)
        if field.minimum is not None and value < field.minimum or field.maximum is not None and value > field.maximum:
            raise ValueError(f"must be between {field.minimum} and {field.maximum}")
        return value
    except (UnicodeError, ValueError) as exc:
        raise ValueError(f"{field.label}: {exc}") from exc


def update(value, inputs: dict[str, str]):
    changed = copy.deepcopy(value)
    for field in fields_for(value):
        if field.name in inputs:
            setattr(changed, field.name, parse(field, inputs[field.name]))
    return changed


def validate_links(project, resource, *, paths: list[Path] | None = None) -> list[str]:
    names = {item.name for path in (paths or rect_catalog.rect_paths(project))
             for item in rect_catalog.read_doc(project, path).resources}
    names.add(resource.name)
    missing = []
    for layer in resource.layers:
        if isinstance(layer, rect.TextboxLayer):
            for slot in ("window", "panel", "marker"):
                name = getattr(layer, slot)
                if name and name not in names:
                    missing.append(f"{slot}: {name}")
    return missing


def prepare_edit(project, path: Path, old_name: str, edited: rect.RectResource, original: bytes) -> dict[Path, bytes]:
    if project.game != Game.PATH_OF_RADIANCE:
        raise ValueError("Non-image RID editing currently supports Path of Radiance")
    if path.read_bytes() != original:
        raise ValueError("Rect file changed since this editor opened; refresh before saving")
    doc = rect.parse_rect(original)
    if doc.build() != original:
        raise ValueError("Rect file cannot be rebuilt byte-for-byte")
    current = doc.find(old_name)
    if current is None or edited.name != old_name or len(edited.layers) != len(current.layers) or any(type(a) is not type(b) for a, b in zip(edited.layers, current.layers)):
        raise ValueError("RID identity or layer structure changed")
    old_links = set(validate_links(project, current))
    new_links = set(validate_links(project, edited))
    if new_links - old_links:
        raise ValueError("Unknown RID link: " + ", ".join(sorted(new_links - old_links)))
    for index, (before, after) in enumerate(zip(current.layers, edited.layers)):
        if not isinstance(after, rect.RectLayer) or after == before:
            continue
        try:
            texture = rect_catalog.preview_image(project, after)
        except (OSError, ValueError, IndexError) as exc:
            raise ValueError(f"Layer {index} texture cannot be loaded: {exc}") from exc
        if max(after.src[0], after.src[2]) > texture.width or max(after.src[1], after.src[3]) > texture.height:
            raise ValueError(f"Layer {index} source region exceeds its {texture.width} × {texture.height} texture")
    for index, item in enumerate(doc.resources):
        if item.name == old_name:
            doc.resources[index] = copy.deepcopy(edited)
            break
    data = doc.build()
    rect.parse_rect(data)
    return {path: data} if data != original else {}


def describe(layer) -> str:
    if isinstance(layer, rect.TextboxLayer):
        return "Textbox: positions dialogue and starts its window, panel, and page cursor RIDs."
    if isinstance(layer, rect.TextLayer):
        return "Text: draws a literal string or resolves a message ID."
    if isinstance(layer, rect.SeatsLayer):
        return "Portrait seats: places and mirrors character portraits; it draws nothing by itself."
    if isinstance(layer, rect.GradientLayer):
        return "Gradient: draws a rectangle from four corner RGBA colors."
    if isinstance(layer, rect.ColorQuadLayer):
        return "Tinted image: draws a texture with corner colors."
    if isinstance(layer, rect.RectLayer):
        return "Image: draws one region of a texture."
    return "Unused layer: the game draws nothing; its raw bytes are preserved."


def resolved_text(project, value: str) -> str | None:
    path = project.files_dir / "Mess" / "common.m"
    if not path.is_file():
        return None
    try:
        return next((item.text for item in message.read_messages_path(path) if item.speaker == value), None)
    except (OSError, ValueError, UnicodeError):
        return None


def render(project, resource: rect.RectResource, resources: dict[str, rect.RectResource], *, size=(608, 448)) -> tuple[Image.Image, list[str]]:
    """Illustrative still of an FE9 RID. Boxes and seat markers stand in for runtime dialogue."""
    image = Image.new("RGBA", size, (30, 34, 42, 255))
    draw = ImageDraw.Draw(image, "RGBA")
    notes = []
    active = set()

    def draw_resource(item):
        if item.name in active:
            notes.append(f"Cyclic RID link: {item.name}")
            return
        active.add(item.name)
        layers = item.layers[:1] if item.mode == rect.MODE_FLIPBOOK else item.layers
        for layer in layers:
            try:
                if isinstance(layer, rect.GradientLayer):
                    x0, y0, x1, y1 = layer.rect
                    if x1 > x0 and y1 > y0 and x1 - x0 <= 2048 and y1 - y0 <= 2048:
                        tiny = Image.new("RGBA", (2, 2))
                        tiny.putdata(layer.colors)
                        image.alpha_composite(tiny.resize((x1-x0, y1-y0), Image.Resampling.BILINEAR), (x0, y0))
                elif isinstance(layer, rect.RectLayer):
                    tile = rect_catalog.preview_image(project, layer).convert("RGBA")
                    u0, v0, u1, v1 = layer.src
                    tile = tile.crop((min(u0, u1), min(v0, v1), max(u0, u1), max(v0, v1)))
                    if u1 < u0: tile = ImageOps.mirror(tile)
                    if v1 < v0: tile = ImageOps.flip(tile)
                    x0, y0, x1, y1 = layer.dst
                    width = abs(u1-u0) if x0 == x1 else x1-x0
                    height = abs(v1-v0) if y0 == y1 else y1-y0
                    if width > 0 and height > 0 and width <= 2048 and height <= 2048:
                        tile = tile.resize((width, height), Image.Resampling.BILINEAR)
                        if isinstance(layer, rect.ColorQuadLayer):
                            tint = Image.new("RGBA", (2, 2))
                            tint.putdata(layer.colors)
                            tint = tint.resize((width, height), Image.Resampling.BILINEAR)
                            tile = ImageChops.multiply(tile, tint)
                        if layer.alpha != 255:
                            tile.putalpha(tile.getchannel("A").point(lambda alpha: alpha * layer.alpha // 255))
                        image.alpha_composite(tile, (x0, y0))
                elif isinstance(layer, rect.TextLayer):
                    label = resolved_text(project, layer.text) or layer.text
                    font = ImageFont.load_default()
                    width = draw.textbbox((0, 0), label, font=font)[2]
                    x = layer.x - (width if layer.align == 1 else width // 2 if layer.align == 0 else 0)
                    draw.text((x, layer.y), label, fill="white", font=font)
                elif isinstance(layer, rect.TextboxLayer):
                    for link in (layer.panel, layer.window):
                        if link in resources:
                            draw_resource(resources[link])
                        elif link:
                            notes.append(f"Missing linked RID: {link}")
                    x, y = layer.text_x, layer.text_y
                    draw.rectangle((x, y, x + max(1, layer.width), y + max(1, layer.lines * layer.line_height)), outline=(255, 214, 120, 220), width=2)
                    draw.text((x+4, y+4), "Sample dialogue", fill="white", font=ImageFont.load_default())
                    draw.ellipse((layer.marker_x-4, layer.marker_y-4, layer.marker_x+4, layer.marker_y+4), fill=(255, 214, 120, 255))
                elif isinstance(layer, rect.SeatsLayer):
                    for index, (x, y, skip, facing, _seat_id) in enumerate(layer.seats):
                        if skip & 0xFF00:
                            continue
                        draw.ellipse((x-19, y-58, x+19, y-20), fill=(90, 148, 192, 170), outline="white", width=2)
                        draw.rectangle((x-26, y-22, x+26, y+2), fill=(90, 148, 192, 170), outline="white", width=2)
                        draw.text((x-13, y-45), f"{index}{'<' if facing else '>'}", fill="white", font=ImageFont.load_default())
            except (OSError, ValueError, IndexError) as exc:
                notes.append(f"Layer {type(layer).__name__}: {exc}")
        active.remove(item.name)

    draw_resource(resource)
    return image, notes
