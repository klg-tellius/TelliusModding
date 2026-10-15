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

@dataclass
class EditableLayer:
    """Raw FE10 layer with resolved relocated strings."""
    raw: bytes
    strings: dict[int, str] = field(default_factory=dict)

    @property
    def kind(self):
        return self.raw[0]

    @property
    def file(self):
        return self.strings.get(8, "") if self.kind in (1, 6) else ""

    @file.setter
    def file(self, value):
        self.strings[8] = value

    @property
    def texture(self):
        return self.raw[0x12]


@dataclass
class EditableResource:
    name: str
    descriptor: bytes
    layers: list[EditableLayer]


@dataclass
class EditableRect:
    resources: list[EditableResource]
    address_order: list[str]
    pool_order: list[str]
    header_tail: bytes

    def find(self, name):
        return next((resource for resource in self.resources if resource.name == name), None)

    def add(self, resource):
        if self.find(resource.name) is not None:
            raise ValueError(f"{resource.name} already exists")
        if not 0 < len(resource.layers) <= 255:
            raise ValueError("A rect resource needs 1-255 layers")
        self.resources.append(resource)
        self.resources.sort(key=lambda item: item.name.encode(ENCODING))
        self.address_order.append(resource.name)

    def build(self):
        return build_editable_rect(self)


def read_editable_rect(data: bytes) -> EditableRect:
    """Read FE10 rects without discarding unknown layer fields."""
    if len(data) < 0x20:
        raise ValueError("Truncated rect file")
    size, data_size, pointer_count, export_count, imports = struct.unpack_from(">5I", data)
    if size != len(data) or imports:
        raise ValueError("Invalid rect header or unsupported imports")
    base = 0x20
    reloc = base + data_size
    exports = reloc + 4 * pointer_count
    names = exports + 8 * export_count
    if names > size:
        raise ValueError("Rect tables exceed file size")
    pointers = {struct.unpack_from(">I", data, reloc + 4 * i)[0] for i in range(pointer_count)}

    def string(offset):
        start = base + offset
        if not base <= start < reloc:
            raise ValueError("Invalid rect string pointer")
        return data[start:data.index(b"\0", start, reloc)].decode(ENCODING)

    blocks = []
    resources = []
    for index in range(export_count):
        address, name_offset = struct.unpack_from(">II", data, exports + 8 * index)
        name_start = names + name_offset
        name = data[name_start:data.index(b"\0", name_start)].decode(ENCODING)
        at = base + address
        descriptor = data[at:at + 20]
        if len(descriptor) != 20 or string(struct.unpack_from(">I", descriptor)[0]) != name:
            raise ValueError(f"Invalid rect descriptor: {name}")
        count = descriptor[4]
        layers = []
        end = at + 20 + count * 4
        for layer_index in range(count):
            layer_address = struct.unpack_from(">I", data, at + 20 + 4 * layer_index)[0]
            layer_at = base + layer_address
            kind = data[layer_at]
            length = (10 + 8 * struct.unpack_from(">H", data, layer_at + 8)[0]
                      if kind == 4 else _SIZES[kind])
            raw = data[layer_at:layer_at + length]
            if len(raw) != length:
                raise ValueError(f"Truncated layer of {name}")
            refs = {off: string(struct.unpack_from(">I", raw, off)[0])
                    for off in range(0, length - 3, 4) if layer_address + off in pointers}
            layers.append(EditableLayer(raw, refs))
            end = max(end, layer_at + length)
        resources.append(EditableResource(name, descriptor, layers))
        blocks.append((at, end, name))
    blocks.sort()
    pool_start = max((end for _start, end, _name in blocks), default=base)
    raw_pool = data[pool_start:reloc].rstrip(b"\0")
    pool_order = [item.decode(ENCODING) for item in raw_pool.split(b"\0") if item]
    return EditableRect(resources, [name for _start, _end, name in blocks], pool_order, data[0x14:0x20])


def build_editable_rect(doc: EditableRect) -> bytes:
    by_name = {resource.name: resource for resource in doc.resources}
    if len(by_name) != len(doc.resources) or set(doc.address_order) != set(by_name):
        raise ValueError("Rect resource names or address order are inconsistent")
    names_used = []
    for resource in doc.resources:
        names_used.append(resource.name)
        for layer in resource.layers:
            names_used.extend(layer.strings.values())
    pool_order = list(dict.fromkeys([s for s in doc.pool_order if s in names_used] + names_used))
    body = bytearray()
    addresses = {}
    layer_addresses = {}
    for name in doc.address_order:
        resource = by_name[name]
        body += bytes(-len(body) % 4)
        addresses[name] = len(body)
        layer_addresses[name] = []
        body += bytes(20 + 4 * len(resource.layers))
        for layer in resource.layers:
            layer_addresses[name].append(len(body))
            body += layer.raw
    pool_start = len(body)
    pool = bytearray()
    offsets = {}
    for value in pool_order:
        offsets[value] = pool_start + len(pool)
        pool += value.encode(ENCODING) + b"\0"
    pool += bytes(-(0x20 + len(body) + len(pool)) % 4)
    relocations = []
    for name in doc.address_order:
        resource = by_name[name]
        at = addresses[name]
        descriptor = bytearray(resource.descriptor)
        struct.pack_into(">I", descriptor, 0, offsets[name])
        descriptor[4] = len(resource.layers)
        body[at:at + 20] = descriptor
        relocations.append(at)
        for index, layer in enumerate(resource.layers):
            slot = at + 20 + index * 4
            struct.pack_into(">I", body, slot, layer_addresses[name][index])
            relocations.append(slot)
            raw = bytearray(layer.raw)
            for off, value in layer.strings.items():
                struct.pack_into(">I", raw, off, offsets[value])
                relocations.append(layer_addresses[name][index] + off)
            body[layer_addresses[name][index]:layer_addresses[name][index] + len(raw)] = raw
    relocations.sort()
    exports = bytearray()
    export_names = bytearray()
    for resource in doc.resources:
        exports += struct.pack(">II", addresses[resource.name], len(export_names))
        export_names += resource.name.encode(ENCODING) + b"\0"
    data_size = len(body) + len(pool)
    tail = b"".join(struct.pack(">I", value) for value in relocations) + exports + export_names
    size = 0x20 + data_size + len(tail)
    header = struct.pack(">5I", size, data_size, len(relocations), len(doc.resources), 0)
    return header + doc.header_tail + body + pool + tail


def new_image_resource(name: str, file: str, width: int, height: int, images: int = 1) -> EditableResource:
    if not 0 < images <= 255 or not 0 < width <= 1024 or not 0 < height <= 1024:
        raise ValueError("Images must number 1-255 and fit within 1024 by 1024 pixels")
    descriptor = struct.pack(">IBBHfBBB5s", 0, images, 2 if images > 1 else 0, 900, 1.0, 255, 255, 0, bytes(5))
    layers = []
    for index in range(images):
        raw = struct.pack(">BBHIIIBBBBhhhhHHHH", 1, 0, 0, 0, 0, 0, 1, 0, index, 255,
                          0, 0, 0, 0, 0, 0, width, height)
        layers.append(EditableLayer(raw, {8: file}))
    return EditableResource(name, descriptor, layers)
