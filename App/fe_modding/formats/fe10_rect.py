"""Read Radiant Dawn rect files: ``window/RectDesc*.bin`` (conversation layouts, windows) and
``s/rect.bin`` (backgrounds).

Same container and resource descriptor as Path of Radiance (``rect.py``), with layer changes:

* kind 2, the text box, is 0x30 bytes (0x28 on Path of Radiance)::

    +0x08  u32  window RID (drawn behind the box, e.g. RID_TW)     +0x0C  u32  page-cursor RID
    +0x10  RGBA text colour (FFFFFFFF white; CEBD89FF on the world map)
    +0x14  s16  text x, y         +0x18  s16  cursor x, y         +0x1C  u16  width
    +0x1E  4 x s16  nameplate rectangle of the tutorial boxes (zero elsewhere)
    +0x26  u8   line height       +0x27  u8   lines               +0x28  u8   speed
    +0x29  s8   position the box belongs to (-1 for a layout's single shared box)

* kind 7 (0x24 bytes) is new; the other kinds keep their Path of Radiance sizes.

Boxes tied to a position (上下会話, 背景上下会話, TUT会話...) are speech balloons: the game sizes
and places them from the text width when a portrait comes in (``mess_balloon_geometry``,
``FUN_8022a174``, see :func:`balloon`). This reader is read-only: the layout files are not edited.
"""
from __future__ import annotations

import struct
from dataclasses import dataclass, field
from pathlib import Path

ENCODING = "cp932"
_SIZES = {0: 0x18, 1: 0x24, 2: 0x30, 3: 0x18, 5: 0x20, 6: 0x34, 7: 0x24}


@dataclass(frozen=True)
class Textbox:
    window: str
    cursor: str
    color: tuple[int, int, int, int]
    text_x: int
    text_y: int
    cursor_x: int
    cursor_y: int
    width: int
    line_height: int
    lines: int
    speed: int
    position: int


@dataclass(frozen=True)
class Seat:
    x: int          # centre-bottom of the portrait
    y: int
    skip: int
    facing: int     # 1 mirrors the portrait
    index: int


@dataclass(frozen=True)
class Quad:
    kind: int
    file: str
    texture: int
    dst: tuple[int, int, int, int]
    src: tuple[int, int, int, int]
    alpha: int


@dataclass
class Layer:
    kind: int
    raw: bytes
    strings: dict[int, str] = field(default_factory=dict)   # field offset -> resolved string

    def textbox(self) -> Textbox:
        r = self.raw
        tx, ty, cx, cy, width = struct.unpack_from(">hhhhH", r, 0x14)
        line_height, lines, speed, position = struct.unpack_from(">BBBb", r, 0x26)
        return Textbox(self.strings.get(8, ""), self.strings.get(12, ""), tuple(r[0x10:0x14]), tx, ty, cx, cy,
                       width, line_height, lines, speed, position)

    def seats(self) -> list[Seat]:
        count = struct.unpack_from(">H", self.raw, 8)[0]
        return [Seat(*struct.unpack_from(">hhHBB", self.raw, 10 + 8 * i)) for i in range(count)]

    def quad(self) -> Quad:
        r = self.raw
        texture, alpha = r[0x12], r[0x13]
        dst = struct.unpack_from(">4h", r, 0x14)
        src = struct.unpack_from(">4H", r, 0x1C)
        return Quad(self.kind, self.strings.get(8, ""), texture, dst, src, alpha)


@dataclass
class Resource:
    name: str
    mode: int
    depth: int
    duration: float
    layers: list[Layer]

    def textboxes(self) -> list[Textbox]:
        return [layer.textbox() for layer in self.layers if layer.kind == 2]

    def seats(self) -> list[Seat]:
        for layer in self.layers:
            if layer.kind == 4:
                return layer.seats()
        return []

    def quads(self) -> list[Quad]:
        return [layer.quad() for layer in self.layers if layer.kind in (1, 6)]


def read_rect(data: bytes) -> dict[str, Resource]:
    """Every resource of a rect file by name (``RID_上下会話``)."""
    base = 0x20
    _size, data_size, pointer_count, export_count = struct.unpack_from(">IIII", data)
    reloc = base + data_size
    exports = reloc + 4 * pointer_count
    names = exports + 8 * export_count
    pointers = {struct.unpack_from(">I", data, reloc + 4 * i)[0] for i in range(pointer_count)}

    def string(offset: int) -> str:
        end = data.index(b"\0", base + offset)
        return data[base + offset:end].decode(ENCODING, errors="replace")

    def text_at(name_offset: int) -> str:
        end = data.index(b"\0", names + name_offset)
        return data[names + name_offset:end].decode(ENCODING, errors="replace")

    entries = sorted(struct.unpack_from(">II", data, exports + 8 * i) for i in range(export_count))
    resources = {}
    for address, name_offset in entries:
        name = text_at(name_offset)
        count, mode, depth, duration = struct.unpack_from(">BBHf", data, base + address + 4)
        layers = []
        for i in range(count):
            at = struct.unpack_from(">I", data, base + address + 20 + 4 * i)[0]
            kind = data[base + at]
            size = 10 + 8 * struct.unpack_from(">H", data, base + at + 8)[0] if kind == 4 else _SIZES.get(kind, 0x18)
            raw = data[base + at:base + at + size]
            strings = {off: string(struct.unpack_from(">I", raw, off)[0])
                       for off in range(0, size - 3, 4) if at + off in pointers}
            layers.append(Layer(kind, raw, strings))
        resources[name] = Resource(name, mode, depth, duration, layers)
    return resources


def read_rect_path(path: Path | str) -> dict[str, Resource]:
    return read_rect(Path(path).read_bytes())


def balloon(position: int, text_width: int, no_portrait: bool = False) -> dict[str, tuple[int, int] | int]:
    """Speech-balloon geometry of a position-bound box (``FUN_8022a174``, US RFEE01).

    ``text_width`` is the widest line of the page; the game adds 0xE0 for the portrait inset (and
    takes 0x80 back when the actor has no portrait in the box). The width is rounded up to whole
    48-pixel tiles and kept between 336 and 576. Returns the box origin and width, the text origin,
    the page-cursor point and the portrait anchor (the seat point)."""
    width = text_width + 0xE0 - (0x80 if no_portrait else 0)
    width = min(max(-(-width // 48) * 48, 0x150), 0x240)
    tiles = width // 48
    shift = 0x50 if width + 0x50 <= 0x240 else 0x240 - width
    right = 0x250 - width
    if position == 0:
        box, text, cursor, anchor = (0x10, 0x14), (0x40 if no_portrait else 0xC0, 0x20), (width - 0x40, 0x6C), (0x70, 0x82)
    elif position == 1:
        box, text, cursor, anchor = (right, 0x13C), (0x280 - width, 0x148), (right + width - 0xD0, 0x194), (right + width - 0x60, 0x1AA)
    elif position == 2:
        box, text = (shift + 0x10, 0x98), (shift + (0x40 if no_portrait else 0xC0), 0xA4)
        cursor, anchor = (width + shift + 0x10 - 0x50, 0xF0), (shift + 0x70, 0x106)
    elif position == 3:
        x = right - shift
        box, text, cursor, anchor = (x, 0xBC), (x + 0x30, 200), (x + width - 0xD0, 0x114), (x + width - 0x60, 0x12A)
    elif position == 4:
        box, text, cursor, anchor = (right, 0x14), (0x280 - width, 0x20), (right + width - 0xD0, 0x6C), (right + width - 0x60, 0x82)
    elif position == 5:
        box, text, cursor, anchor = (0x10, 0x13C), (0x40 if no_portrait else 0xC0, 0x148), (width - 0x40, 0x194), (0x70, 0x1AA)
    elif position == 6:
        x = right - shift
        box, text, cursor, anchor = (x, 0x98), (x + 0x30, 0xA4), (x + width - 0xD0, 0xF0), (x + width - 0x60, 0x106)
    elif position == 7:
        box, text = (shift + 0x10, 0xBC), (shift + (0x40 if no_portrait else 0xC0), 200)
        cursor, anchor = (width + shift + 0x10 - 0x50, 0x114), (shift + 0x70, 0x12A)
    else:
        raise ValueError(f"position {position} has no balloon")
    return {"box": box, "width": width, "tiles": tiles, "text": text, "cursor": cursor, "anchor": anchor}
