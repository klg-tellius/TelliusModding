"""``s/rect.bin``: the table of full-screen "rect" images (event/conversation
backgrounds, map illustrations, title screen, ending art, ...).

It is an HSDArc container (``CONTAINER_FORMATS.md`` section 2). Each export is
a **resource** named ``RID_...`` (Shift-JIS, e.g. ``RID_街-夜``), which an event
script instantiates with ``RectBuild("RID_...")``. A resource is a small
descriptor followed by a list of **layers**, and each layer draws a rectangle
of one texture of one TPL file under ``s/``.

Descriptor (20 bytes, then one u32 pointer per layer)::

    +0x00  u32  pointer to the resource's own name in the label pool
    +0x04  u8   layer count
    +0x05  u8   composition mode: 0 stack every layer (layer 0 underneath),
                1 flip-book, 2 cross-fade
    +0x06  u16  depth (added to the rect's Z; 900 in every vanilla resource)
    +0x08  f32  animation period in seconds (one pass over all layers)
    +0x0C  u8   brightness, 255 = unchanged (see ``RectResource.brightness``)
    +0x0D  u8   not read by the rect process (0xAA-0xFF in vanilla)
    +0x0E  u8   ambient effect: 0 none, 1 snow, 2 altar particles, 3 sand, 4 mist
    +0x0F  5 bytes, zero

Layer (0x24 bytes, always kind 1 in this file)::

    +0x00  u8   kind (1 = textured quad)
    +0x08  u32  pointer to the TPL path (``s/95x``)
    +0x10  u8   flags (1 in every layer; bit 0 ORs flag 4 into the file's
                resource-manager record when the layer loads)
    +0x11  u8   dead byte, overwritten with 0 when the layer is loaded
    +0x12  u8   texture index inside the TPL
    +0x13  u8   alpha (used when the layer is drawn at full strength)
    +0x14  4xs16 destination x0,y0,x1,y1 (all zero in vanilla)
    +0x1C  4xu16 source x0,y0,x1,y1 in texels

Everything above was read from the engine's rect process
(``rect_process_init``, ``rect_process_tick``, the layer draw method) and
checked against all 195 resources / 316 layers of the vanilla file;
``RectFile.build()`` reproduces the vanilla file byte for byte. See
``research/RECT_NOTES.md``.

Layout of the file (reproduced exactly by ``build``): the header, then one
block per resource (descriptor, layer pointers, layers; each block starts on a
4-byte boundary) in ``address_order``,
then the label pool (every resource name, then every TPL path), the
relocation table (ascending positions of all pointer words), the export table
(``(block address, name offset)`` per resource, ``table order``) and the name
blob the export table indexes.
"""

from __future__ import annotations

import io
import struct
from dataclasses import dataclass, field
from pathlib import Path
from typing import BinaryIO, Callable

from .common import HEADER_SIZE

CODEC = "shift_jis"

DESCRIPTOR_SIZE = 20
LAYER_SIZE = 0x24  # kind 1
COLOR_QUAD_SIZE = 0x34  # kind 6
TEXT_SIZE = 0x18  # kind 3 (and the unused kind 0)
TEXTBOX_SIZE = 0x28  # kind 2
GRADIENT_SIZE = 0x20  # kind 5
SEATS_HEADER_SIZE = 10  # kind 4: header, then SEAT_SIZE bytes per seat
SEAT_SIZE = 8
KIND_QUAD, KIND_TEXTBOX, KIND_TEXT, KIND_SEATS, KIND_GRADIENT, KIND_COLOR_QUAD = 1, 2, 3, 4, 5, 6

MODE_STACK, MODE_FLIPBOOK, MODE_CROSSFADE = 0, 1, 2
MODE_NAMES = {MODE_STACK: "stack", MODE_FLIPBOOK: "flip-book", MODE_CROSSFADE: "cross-fade"}

EFFECT_NONE, EFFECT_SNOW, EFFECT_ALTAR, EFFECT_SAND, EFFECT_MIST = range(5)
EFFECT_NAMES = {
    EFFECT_NONE: "none",
    EFFECT_SNOW: "snow",
    EFFECT_ALTAR: "altar particles",
    EFFECT_SAND: "sand",
    EFFECT_MIST: "mist",
}

DEFAULT_DEPTH = 900
FRAMES_PER_SECOND = 60  # the engine steps the animation once per 60 Hz frame

_DESCRIPTOR = struct.Struct(">IBBHfBBB5s")
_QUAD = struct.Struct(">BBHIIIBBBBhhhhHHHH")  # kind 1, first 0x24 bytes (also kind 6)
_COLORS = struct.Struct(">16B")
assert _DESCRIPTOR.size == DESCRIPTOR_SIZE and _QUAD.size == LAYER_SIZE


class RectError(ValueError):
    pass


def _rgba(values) -> tuple[tuple[int, int, int, int], ...]:
    return tuple(tuple(values[4 * i:4 * i + 4]) for i in range(4))


@dataclass
class RectLayer:
    """Kind 1, a textured quad (the only kind in ``s/rect.bin``)."""

    file: str  # TPL path relative to the disc's files/ folder, e.g. "s/95x"
    texture: int = 0  # image index inside the TPL
    src: tuple[int, int, int, int] = (0, 0, 0, 0)  # x0, y0, x1, y1 in texels; a reversed pair mirrors
    dst: tuple[int, int, int, int] = (0, 0, 0, 0)  # x0, y0, x1, y1; equal ends mean "source size"
    flags: int = 1
    state: int = 0
    alpha: int = 255

    kind = KIND_QUAD

    @property
    def width(self) -> int:
        return abs(self.src[2] - self.src[0])

    @property
    def height(self) -> int:
        return abs(self.src[3] - self.src[1])

    def strings(self) -> list[str]:
        return [self.file]

    def size(self) -> int:
        return LAYER_SIZE

    def pack(self, offsets: dict[str, int]) -> tuple[bytes, list[int]]:
        for value in (self.texture, self.flags, self.state, self.alpha):
            if not 0 <= value <= 255:
                raise RectError("a quad layer byte field is out of range")
        if len(self.src) != 4 or len(self.dst) != 4:
            raise RectError("layer rectangles need four values")
        raw = _QUAD.pack(self.kind, 0, 0, 0, offsets[self.file], 0, self.flags, self.state, self.texture,
                         self.alpha, *self.dst, *self.src)
        return raw, [8]


@dataclass
class ColorQuadLayer(RectLayer):
    """Kind 6 (0x34 bytes): a quad like kind 1 plus one RGBA colour per corner
    (``+0x24`` upper-left ... ``+0x30``, multiplied by the draw alpha)."""

    colors: tuple[tuple[int, int, int, int], ...] = ((255, 255, 255, 255),) * 4

    kind = KIND_COLOR_QUAD

    def size(self) -> int:
        return COLOR_QUAD_SIZE

    def pack(self, offsets):
        raw, pointers = super().pack(offsets)
        raw = bytes([self.kind]) + raw[1:]
        flat = [c for color in self.colors for c in color]
        if len(flat) != 16 or any(not 0 <= c <= 255 for c in flat):
            raise RectError("a colour quad needs four RGBA colours")
        return raw + _COLORS.pack(*flat), pointers


@dataclass
class TextLayer:
    """Kind 3 (0x18 bytes): one line of text at ``(x, y)``. ``text`` is looked up
    by name in the engine's name table (a ``Mess/common.m`` ID such as
    ``MIK_AX``); a name that is not found is drawn as the literal string, so
    inline ``#`` markup (``#P011`` icon, ``#R41#G48#B34`` colour) works too."""

    text: str
    x: int = 0
    y: int = 0
    depth: int = 0  # header byte +2, drawn as the vertex depth
    style_a: int = 0  # +0x10: selects a text-record variant (0 in every vanilla layer)
    style_b: int = 0  # +0x11: 1 selects the multi-vertex glyph variant (13 vanilla layers)
    color: int = 1  # +0x12: text palette index
    unknown_13: int = 1  # +0x13: 1 in every vanilla layer, not read by the draw method
    align: int = -1  # +0x14: -1 left, 0 centred on x, 1 right-aligned to x
    padding: bytes = bytes(3)

    kind = KIND_TEXT

    def strings(self) -> list[str]:
        return [self.text]

    def size(self) -> int:
        return TEXT_SIZE

    def pack(self, offsets):
        for value in (self.style_a, self.style_b, self.color, self.unknown_13):
            if not 0 <= value <= 255:
                raise RectError("a text layer byte field is out of range")
        if not -128 <= self.depth <= 127 or not -128 <= self.align <= 127:
            raise RectError("a text layer signed byte is out of range")
        raw = struct.pack(">BBbBIIhhBBBBb3s", self.kind, 0, self.depth, 0, 0, offsets[self.text], self.x, self.y,
                          self.style_a, self.style_b, self.color, self.unknown_13, self.align, self.padding)
        return raw, [8]


@dataclass
class TextboxLayer:
    """Kind 2 (0x28 bytes): a dialogue text window (``dialogue_initialize_textbox_descriptor``).
    ``window``/``panel``/``marker`` name other rect resources (``""`` = none)."""

    window: str = ""  # +0x08 RID started as the window's child process
    panel: str = ""  # +0x0C RID built when ``block`` is 0
    marker: str = ""  # +0x10 RID of the "more text" cursor
    text_x: int = 0  # +0x14
    text_y: int = 0  # +0x16
    marker_x: int = 0  # +0x18
    marker_y: int = 0  # +0x1A
    width: int = 0  # +0x1C
    style_a: int = 1  # +0x1E, the same two text-variant toggles as TextLayer +0x10/+0x11
    style_b: int = 1  # +0x1F
    line_height: int = 28  # +0x20
    lines: int = 3  # +0x21
    speed: int = 7  # +0x22
    seat: int = -1  # +0x23: portrait seat (0-3) the box is tied to, -1 none
    block: int = 0  # +0x24
    dynamic: int = 0  # +0x25
    padding: bytes = bytes(2)

    kind = KIND_TEXTBOX

    def strings(self) -> list[str]:
        return [s for s in (self.window, self.panel, self.marker) if s]

    def size(self) -> int:
        return TEXTBOX_SIZE

    def pack(self, offsets):
        for value in (self.style_a, self.style_b, self.line_height, self.lines, self.speed, self.block,
                      self.dynamic):
            if not 0 <= value <= 255:
                raise RectError("a textbox byte field is out of range")
        if not -128 <= self.seat <= 127:
            raise RectError("a textbox seat is out of range")
        pointers, refs = [], []
        for slot, text in ((8, self.window), (12, self.panel), (16, self.marker)):
            refs.append(offsets[text] if text else 0)
            if text:
                pointers.append(slot)
        raw = struct.pack(">BBHIIII4hhBBBBBbBB2s", self.kind, 0, 0, 0, *refs, self.text_x, self.text_y,
                          self.marker_x, self.marker_y, self.width, self.style_a, self.style_b, self.line_height,
                          self.lines, self.speed, self.seat, self.block, self.dynamic, self.padding)
        return raw, pointers


@dataclass
class GradientLayer:
    """Kind 5 (0x20 bytes): a filled rectangle with one RGBA colour per corner
    (upper-left, upper-right, lower-left, lower-right order as the engine
    passes them to ``prim2d_set_quad_vertex_colors``)."""

    rect: tuple[int, int, int, int] = (0, 0, 0, 0)  # x0, y0, x1, y1
    colors: tuple[tuple[int, int, int, int], ...] = ((0, 0, 0, 255),) * 4

    kind = KIND_GRADIENT

    def strings(self) -> list[str]:
        return []

    def size(self) -> int:
        return GRADIENT_SIZE

    def pack(self, offsets):
        flat = [c for color in self.colors for c in color]
        if len(flat) != 16 or any(not 0 <= c <= 255 for c in flat) or len(self.rect) != 4:
            raise RectError("a gradient needs a rectangle and four RGBA colours")
        return struct.pack(">BBHI4h", self.kind, 0, 0, 0, *self.rect) + _COLORS.pack(*flat), []


@dataclass
class SeatsLayer:
    """Kind 4 (10 + 8 per seat bytes): the portrait seat table of a conversation
    layout. Each seat is ``(x, y, skip, facing, index)``: the portrait's
    centre-bottom point, ``skip`` (a u16 whose high byte non-zero leaves the seat
    out of the table the dialogue code builds), ``facing`` (1 mirrors the
    portrait) and the seat's own number, which the loader does not read."""

    seats: list[tuple[int, int, int, int, int]] = field(default_factory=list)

    kind = KIND_SEATS

    def strings(self) -> list[str]:
        return []

    def size(self) -> int:
        return SEATS_HEADER_SIZE + SEAT_SIZE * len(self.seats)

    def pack(self, offsets):
        out = bytearray(struct.pack(">BBHIH", self.kind, 0, 0, 0, len(self.seats)))
        for x, y, skip, facing, index in self.seats:
            out += struct.pack(">hhHBB", x, y, skip, facing, index)
        return bytes(out), []


@dataclass
class UnusedLayer:
    """Kind 0 (0x18 bytes): the engine builds nothing for it. Kept as raw bytes;
    no vanilla file contains one."""

    raw: bytes = bytes(TEXT_SIZE)

    kind = 0

    def strings(self) -> list[str]:
        return []

    def size(self) -> int:
        return len(self.raw)

    def pack(self, offsets):
        return self.raw, []


Layer = RectLayer | ColorQuadLayer | TextLayer | TextboxLayer | GradientLayer | SeatsLayer | UnusedLayer


def _layer_length(data: bytes, address: int) -> int:
    kind = data[address]
    if kind == KIND_SEATS:
        return SEATS_HEADER_SIZE + SEAT_SIZE * struct.unpack_from(">H", data, address + 8)[0]
    try:
        return {0: TEXT_SIZE, KIND_QUAD: LAYER_SIZE, KIND_TEXTBOX: TEXTBOX_SIZE, KIND_TEXT: TEXT_SIZE,
                KIND_GRADIENT: GRADIENT_SIZE, KIND_COLOR_QUAD: COLOR_QUAD_SIZE}[kind]
    except KeyError:
        raise RectError(f"unknown layer kind {kind} at {address:#x}") from None


@dataclass
class RectResource:
    name: str
    layers: list[Layer] = field(default_factory=list)
    mode: int = MODE_CROSSFADE
    depth: int = DEFAULT_DEPTH
    duration: float = 1.0
    #: 255 leaves the image alone; smaller values darken it. The engine stores
    #: ``(value >> 1) + 1`` as the prim2d group brightness, which multiplies
    #: every vertex colour by ``brightness / 128``. 0 also means "unchanged".
    brightness: int = 255
    unused_0d: int = 255
    effect: int = EFFECT_NONE
    padding: bytes = bytes(5)

    @property
    def size(self) -> tuple[int, int]:
        """Width and height of the first layer, which the engine uses as the
        rect's size (and as its scale/rotation pivot, halved). Zero when the
        first layer is not a quad."""
        first = self.layers[0] if self.layers else None
        return (first.width, first.height) if isinstance(first, RectLayer) else (0, 0)

    @property
    def frame_seconds(self) -> float:
        """How long each layer stays up in a flip-book or cross-fade."""
        return self.duration / len(self.layers) if self.layers else 0.0

    def quads(self) -> list[RectLayer]:
        return [layer for layer in self.layers if isinstance(layer, RectLayer)]


@dataclass
class RectFile:
    resources: list[RectResource]  # export-table order
    address_order: list[str]  # resource names in file order
    pool_order: list[str]  # label pool strings in file order
    header_tail: bytes = bytes(12)  # header bytes 0x14..0x1F

    def find(self, name: str) -> RectResource | None:
        for resource in self.resources:
            if resource.name == name:
                return resource
        return None

    def add(self, resource: RectResource) -> RectResource:
        """Append a resource. The export table stays sorted by name bytes
        when the vanilla one is (it is), so a new entry goes to its place."""
        if self.find(resource.name) is not None:
            raise RectError(f"{resource.name!r} already exists")
        if not resource.layers:
            raise RectError(f"{resource.name!r} needs at least one layer")
        key = resource.name.encode(CODEC)
        if [r.name.encode(CODEC) for r in self.resources] == sorted(r.name.encode(CODEC) for r in self.resources):
            index = sum(1 for r in self.resources if r.name.encode(CODEC) < key)
            self.resources.insert(index, resource)
        else:
            self.resources.append(resource)
        self.address_order.append(resource.name)
        return resource

    def remove(self, name: str) -> None:
        resource = self.find(name)
        if resource is None:
            raise RectError(f"No resource {name!r}")
        self.resources.remove(resource)
        self.address_order.remove(name)

    def files(self) -> list[str]:
        """Every TPL path the quad layers use, sorted."""
        return sorted({layer.file for r in self.resources for layer in r.quads()}, key=lambda s: s.encode(CODEC))

    def build(self) -> bytes:
        return build_rect(self)


def _cstring(data: bytes, offset: int) -> bytes:
    end = data.find(b"\0", offset)
    if offset < 0 or end < 0:
        raise RectError("Unterminated string")
    return data[offset:end]


def _string_at(data: bytes, pointer: int) -> str:
    return _cstring(data, pointer + HEADER_SIZE).decode(CODEC)


def _parse_layer(data: bytes, address: int, name: str, index: int) -> Layer:
    if not HEADER_SIZE <= address < len(data):
        raise RectError(f"{name!r}: layer {index} pointer {address:#x} is outside the file")
    kind = data[address]
    length = _layer_length(data, address)
    raw = data[address:address + length]
    where = f"{name!r}: layer {index}"
    if len(raw) != length:
        raise RectError(f"{where} is truncated")
    if kind in (KIND_QUAD, KIND_COLOR_QUAD):
        (_k, size, zero0, vtable, file_ptr, loaded, flags, state, texture, alpha, *rects) = _QUAD.unpack_from(raw)
        if size or zero0 or vtable or loaded:
            raise RectError(f"{where} has runtime fields set on disc")
        common = dict(file=_string_at(data, file_ptr), texture=texture, src=tuple(rects[4:8]),
                      dst=tuple(rects[0:4]), flags=flags, state=state, alpha=alpha)
        if kind == KIND_QUAD:
            return RectLayer(**common)
        return ColorQuadLayer(colors=_rgba(_COLORS.unpack_from(raw, LAYER_SIZE)), **common)
    if kind == KIND_TEXT:
        (_k, size, depth, zero3, vtable, ptr, x, y, style_a, style_b, color, unknown, align, padding) = \
            struct.unpack(">BBbBIIhhBBBBb3s", raw)
        if size or zero3 or vtable:
            raise RectError(f"{where} has runtime fields set on disc")
        return TextLayer(_string_at(data, ptr), x, y, depth, style_a, style_b, color, unknown, align, padding)
    if kind == KIND_TEXTBOX:
        (_k, size, zero2, vtable, p_window, p_panel, p_marker, tx, ty, mx, my, width, style_a, style_b,
         line_height, lines, speed, seat, block, dynamic, padding) = struct.unpack(">BBHIIII4hhBBBBBbBB2s", raw)
        if size or zero2 or vtable:
            raise RectError(f"{where} has runtime fields set on disc")
        return TextboxLayer(*(_string_at(data, p) if p else "" for p in (p_window, p_panel, p_marker)),
                            tx, ty, mx, my, width, style_a, style_b, line_height, lines, speed, seat, block,
                            dynamic, padding)
    if kind == KIND_GRADIENT:
        (_k, size, zero2, vtable, *rect) = struct.unpack_from(">BBHI4h", raw)
        if size or zero2 or vtable:
            raise RectError(f"{where} has runtime fields set on disc")
        return GradientLayer(tuple(rect), _rgba(_COLORS.unpack_from(raw, 16)))
    if kind == KIND_SEATS:
        (_k, size, zero2, vtable, count) = struct.unpack_from(">BBHIH", raw)
        if size or zero2 or vtable:
            raise RectError(f"{where} has runtime fields set on disc")
        seats = [struct.unpack_from(">hhHBB", raw, SEATS_HEADER_SIZE + SEAT_SIZE * i) for i in range(count)]
        return SeatsLayer([tuple(s) for s in seats])
    return UnusedLayer(raw)


def parse_rect(data: bytes) -> RectFile:
    if len(data) < HEADER_SIZE:
        raise RectError("Truncated rect file")
    size, data_size, reloc_count, export_count, import_count = struct.unpack_from(">5I", data)
    if size != len(data):
        raise RectError(f"Header size {size:#x} does not match the file ({len(data):#x})")
    if import_count:
        raise RectError("Rect files with imports are not supported")
    pool_end = HEADER_SIZE + data_size
    table = pool_end + 4 * reloc_count
    names = table + 8 * export_count
    if names > size:
        raise RectError("Export table runs past the end of the file")

    resources: list[RectResource] = []
    blocks: list[tuple[int, int, int]] = []  # (address, end, table index)
    for index in range(export_count):
        address, name_offset = struct.unpack_from(">II", data, table + 8 * index)
        address += HEADER_SIZE
        name = _cstring(data, names + name_offset).decode(CODEC)
        (rid, count, mode, depth, duration, brightness, unused, effect, padding) = _DESCRIPTOR.unpack_from(
            data, address
        )
        if _string_at(data, rid) != name:
            raise RectError(f"{name!r}: descriptor name pointer does not name the resource")
        layers: list[Layer] = []
        end = address + DESCRIPTOR_SIZE + 4 * count
        for i in range(count):
            (layer_address,) = struct.unpack_from(">I", data, address + DESCRIPTOR_SIZE + 4 * i)
            layer_address += HEADER_SIZE
            layer = _parse_layer(data, layer_address, name, i)
            layers.append(layer)
            end += layer.size()
        resources.append(RectResource(name=name, layers=layers, mode=mode, depth=depth, duration=duration,
                                      brightness=brightness, unused_0d=unused, effect=effect, padding=padding))
        blocks.append((address, end, index))

    blocks.sort()
    pool_start = blocks[-1][1] if blocks else HEADER_SIZE
    # The blocks must tile the data area without gaps or the rebuilt file would differ.
    position = HEADER_SIZE
    for address, end, _index in blocks:
        if address != (position + 3) & ~3 or any(data[position:address]):
            raise RectError(f"Unexpected gap before the block at {address:#x}")
        position = end
    pool = data[pool_start:pool_end].split(b"\0")
    while pool and pool[-1] == b"":
        pool.pop()
    doc = RectFile(
        resources=resources,
        address_order=[resources[i].name for _a, _e, i in blocks],
        pool_order=[s.decode(CODEC) for s in pool],
        header_tail=data[0x14:HEADER_SIZE],
    )
    return doc


def build_rect(doc: RectFile) -> bytes:
    """Lay the document out again. Strings keep their vanilla pool order, new
    ones follow in order of first use; the relocation table and the export
    table are rebuilt."""
    by_name = {r.name: r for r in doc.resources}
    if len(by_name) != len(doc.resources):
        raise RectError("Duplicate resource names")
    if sorted(doc.address_order) != sorted(by_name):
        raise RectError("address_order does not list exactly the resources")

    used: list[str] = []
    seen: set[str] = set()

    def use(text: str) -> None:
        if text not in seen:
            seen.add(text)
            used.append(text)

    for resource in doc.resources:
        use(resource.name)
        for layer in resource.layers:
            for text in layer.strings():
                use(text)
    pool_strings = [s for s in doc.pool_order if s in seen]
    kept = set(pool_strings)
    pool_strings += [s for s in used if s not in kept]

    body = bytearray()
    addresses: dict[str, int] = {}
    layer_addresses: dict[str, list[int]] = {}
    for name in doc.address_order:
        resource = by_name[name]
        body += bytes(-len(body) % 4)  # every block starts on a 4-byte boundary
        address = HEADER_SIZE + len(body)
        addresses[name] = address
        count = len(resource.layers)
        cursor = address + DESCRIPTOR_SIZE + 4 * count
        layer_addresses[name] = []
        for layer in resource.layers:
            layer_addresses[name].append(cursor)
            cursor += layer.size()
        body += bytes(cursor - address)
    pool_start = HEADER_SIZE + len(body)

    pool = bytearray()
    offsets: dict[str, int] = {}
    for text in pool_strings:
        offsets[text] = pool_start - HEADER_SIZE + len(pool)
        pool += text.encode(CODEC) + b"\0"
    pool += bytes(-(pool_start + len(pool)) % 4)  # the pool ends on a 4-byte boundary (of the file)

    relocations: list[int] = []
    for name in doc.address_order:
        resource = by_name[name]
        address = addresses[name]
        if not 0 < len(resource.layers) <= 255:
            raise RectError(f"{name!r}: a resource holds 1-255 layers")
        if not 0 <= resource.mode <= 255 or not 0 <= resource.depth <= 0xFFFF:
            raise RectError(f"{name!r}: mode or depth out of range")
        if not (0 <= resource.brightness <= 255 and 0 <= resource.unused_0d <= 255 and 0 <= resource.effect <= 255):
            raise RectError(f"{name!r}: a descriptor byte is out of range")
        descriptor = _DESCRIPTOR.pack(
            offsets[name], len(resource.layers), resource.mode, resource.depth, resource.duration,
            resource.brightness, resource.unused_0d, resource.effect, resource.padding,
        )
        relocations.append(address - HEADER_SIZE)
        body[address - HEADER_SIZE:address - HEADER_SIZE + DESCRIPTOR_SIZE] = descriptor
        for i, layer in enumerate(resource.layers):
            slot = address + DESCRIPTOR_SIZE + 4 * i
            struct.pack_into(">I", body, slot - HEADER_SIZE, layer_addresses[name][i] - HEADER_SIZE)
            relocations.append(slot - HEADER_SIZE)
            layer_address = layer_addresses[name][i]
            raw, pointer_slots = layer.pack(offsets)
            if len(raw) != layer.size():
                raise RectError(f"{name!r}: layer {i} packed to {len(raw)} bytes, expected {layer.size()}")
            body[layer_address - HEADER_SIZE:layer_address - HEADER_SIZE + len(raw)] = raw
            relocations.extend(layer_address - HEADER_SIZE + s for s in pointer_slots)
    relocations.sort()

    names_blob = bytearray()
    table = bytearray()
    for resource in doc.resources:
        table += struct.pack(">II", addresses[resource.name] - HEADER_SIZE, len(names_blob))
        names_blob += resource.name.encode(CODEC) + b"\0"

    pool_end = pool_start + len(pool)
    tail = b"".join(struct.pack(">I", r) for r in relocations) + bytes(table) + bytes(names_blob)
    total = pool_end + len(tail)
    header = struct.pack(">5I", total, pool_end - HEADER_SIZE, len(relocations), len(doc.resources), 0)
    return header + doc.header_tail + bytes(body) + bytes(pool) + tail


def new_background(
    name: str,
    file: str,
    width: int,
    height: int,
    *,
    textures: int = 1,
    duration: float = 1.0,
    brightness: int = 255,
    effect: int = EFFECT_NONE,
) -> RectResource:
    """A resource showing ``textures`` images of ``file`` (cross-faded over
    ``duration`` seconds when there are several), each ``width`` x ``height``."""
    layers = [RectLayer(file=file, texture=i, src=(0, 0, width, height)) for i in range(textures)]
    return RectResource(name=name, layers=layers, duration=duration, brightness=brightness, effect=effect)


def free_tpl_name(directory: Path | str) -> str:
    """The first unused three-character name (0-9, a-z, like every vanilla
    ``s/`` file) in ``directory``, counting up from ``aaa``."""
    taken = {p.name for p in Path(directory).iterdir()} if Path(directory).is_dir() else set()
    alphabet = "0123456789abcdefghijklmnopqrstuvwxyz"
    for n in range(10, len(alphabet) ** 3):
        text = "".join(alphabet[(n // len(alphabet) ** k) % len(alphabet)] for k in (2, 1, 0))
        if text not in taken:
            return text
    raise RectError("No free three-character file name left in s/")


def add_background(
    doc: RectFile,
    files_dir: Path | str,
    name: str,
    images: list,
    *,
    tpl_name: str | None = None,
    mode: int = MODE_CROSSFADE,
    duration: float = 1.0,
    brightness: int = 255,
    effect: int = EFFECT_NONE,
) -> RectResource:
    """Encode ``images`` (Pillow images of one size) as a new CMPR TPL under
    ``files_dir/s/`` and add a resource that shows them. The caller writes
    ``doc.build()`` back to ``s/rect.bin`` (a project build then copies it into
    ``system.cmp``, where the game reads it)."""
    from . import tpl  # Pillow is only needed for this helper

    if not images:
        raise RectError("Give at least one image")
    if len({image.size for image in images}) != 1:
        raise RectError("Every image of a resource must have the same size")
    width, height = images[0].size
    if not (0 < width <= 1024 and 0 < height <= 1024):
        raise RectError(f"{width}x{height}: a GX texture is at most 1024 pixels on each side")
    folder = Path(files_dir) / "s"
    tpl_name = tpl_name or free_tpl_name(folder)
    if (folder / tpl_name).exists():
        raise RectError(f"s/{tpl_name} already exists")
    resource = new_background(
        name, f"s/{tpl_name}", width, height, textures=len(images),
        duration=duration, brightness=brightness, effect=effect,
    )
    resource.mode = mode
    doc.add(resource)
    folder.mkdir(parents=True, exist_ok=True)
    (folder / tpl_name).write_bytes(tpl.build_tpl([(image, tpl.FORMAT_CMPR) for image in images], wrap=tpl.WRAP_CLAMP))
    return resource


def validate(
    doc: RectFile,
    texture_sizes: Callable[[str], list[tuple[int, int]] | None],
    known_names: set[str] | None = None,
) -> list[str]:
    """Problems the engine would not report itself. ``texture_sizes(path)``
    returns the (width, height) of every image of a TPL, or None when the file
    is missing. Textbox layers name other resources (frame, panel, cursor):
    with ``known_names`` (every RID loaded alongside this file, e.g. those of
    ``rectdesc.bin``) a reference to a name found in neither is reported."""
    problems = []
    if known_names is not None:
        available = known_names | {r.name for r in doc.resources}
        for resource in doc.resources:
            for i, layer in enumerate(resource.layers):
                if isinstance(layer, TextboxLayer):
                    for text in layer.strings():
                        if text not in available:
                            problems.append(f"{resource.name}: textbox layer {i} names unknown resource {text}")
    cache: dict[str, list[tuple[int, int]] | None] = {}
    for resource in doc.resources:
        if not resource.name.startswith("RID_"):
            problems.append(f"{resource.name}: names conventionally start with RID_")
        if resource.mode > MODE_CROSSFADE:
            problems.append(f"{resource.name}: mode {resource.mode} draws nothing")
        for i, layer in enumerate(resource.layers):
            if not isinstance(layer, RectLayer):
                continue
            if layer.file not in cache:
                cache[layer.file] = texture_sizes(layer.file)
            sizes = cache[layer.file]
            if sizes is None:
                problems.append(f"{resource.name}: layer {i} uses missing file {layer.file}")
            elif layer.texture >= len(sizes):
                problems.append(f"{resource.name}: layer {i} uses texture {layer.texture} of {layer.file}, "
                                f"which has {len(sizes)}")
            else:
                width, height = sizes[layer.texture]
                if max(layer.src[0], layer.src[2]) > width or max(layer.src[1], layer.src[3]) > height:
                    problems.append(f"{resource.name}: layer {i} source {layer.src} is outside the "
                                    f"{width}x{height} texture")
    return problems


def read_rect_file(path: Path | str) -> RectFile:
    return parse_rect(Path(path).read_bytes())


def write_rect_file(doc: RectFile, path: Path | str) -> None:
    with open(path, "wb") as stream:
        stream.write(doc.build())


# -- compatibility with the first version of this module -------------------------
# It read the export table four bytes off, pairing each name with the next
# resource's data and dropping the last resource. ``resource_id`` was right
# (it comes from the descriptor); ``name`` was not. Kept for existing callers.


@dataclass(frozen=True)
class RectImage:
    file_name: bytes
    height: int
    width: int
    raw_fields: tuple[int, ...]


@dataclass(frozen=True)
class RectEntry:
    name: bytes
    resource_id: bytes  # "RID_..." label, Shift-JIS
    flags: tuple[int, ...]  # descriptor bytes +0x05..+0x13
    images: list[RectImage]


def read_rects(stream: BinaryIO) -> list[RectEntry]:
    doc = parse_rect(stream.read())
    entries = []
    for r in doc.resources:
        flags = (r.mode, *struct.pack(">H", r.depth), *struct.pack(">f", r.duration),
                 r.brightness, r.unused_0d, r.effect, *r.padding)
        images = [
            RectImage(l.file.encode(CODEC), l.height, l.width, (l.flags, l.state, l.texture, l.alpha, *l.dst, *l.src))
            for l in r.quads()
        ]
        entries.append(RectEntry(r.name.encode(CODEC), r.name.encode(CODEC), flags, images))
    return entries


def read_rects_path(path: Path | str) -> list[RectEntry]:
    with open(path, "rb") as stream:
        return read_rects(io.BytesIO(stream.read()))
