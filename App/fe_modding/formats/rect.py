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
block per resource (descriptor, layer pointers, layers) in ``address_order``,
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
LAYER_SIZE = 0x24
KIND_QUAD = 1

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
_LAYER = struct.Struct(">BBHIIIBBBBhhhhHHHH")
assert _DESCRIPTOR.size == DESCRIPTOR_SIZE and _LAYER.size == LAYER_SIZE


class RectError(ValueError):
    pass


@dataclass
class RectLayer:
    file: str  # TPL path relative to the disc's files/ folder, e.g. "s/95x"
    texture: int = 0  # image index inside the TPL
    src: tuple[int, int, int, int] = (0, 0, 0, 0)  # x0, y0, x1, y1 in texels
    dst: tuple[int, int, int, int] = (0, 0, 0, 0)  # x0, y0, x1, y1; equal ends mean "source size"
    flags: int = 1
    state: int = 0
    alpha: int = 255

    @property
    def width(self) -> int:
        return abs(self.src[2] - self.src[0])

    @property
    def height(self) -> int:
        return abs(self.src[3] - self.src[1])


@dataclass
class RectResource:
    name: str
    layers: list[RectLayer] = field(default_factory=list)
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
        rect's size (and as its scale/rotation pivot, halved)."""
        return (self.layers[0].width, self.layers[0].height) if self.layers else (0, 0)

    @property
    def frame_seconds(self) -> float:
        """How long each layer stays up in a flip-book or cross-fade."""
        return self.duration / len(self.layers) if self.layers else 0.0


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
        """Every TPL path the resources use, sorted."""
        return sorted({layer.file for r in self.resources for layer in r.layers}, key=lambda s: s.encode(CODEC))

    def build(self) -> bytes:
        return build_rect(self)


def _cstring(data: bytes, offset: int) -> bytes:
    end = data.find(b"\0", offset)
    if offset < 0 or end < 0:
        raise RectError("Unterminated string")
    return data[offset:end]


def parse_rect(data: bytes) -> RectFile:
    if len(data) < HEADER_SIZE:
        raise RectError("Truncated rect.bin")
    size, data_size, reloc_count, export_count, import_count = struct.unpack_from(">5I", data)
    if size != len(data):
        raise RectError(f"Header size {size:#x} does not match the file ({len(data):#x})")
    if import_count:
        raise RectError("rect.bin with imports is not supported")
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
        if _cstring(data, rid + HEADER_SIZE).decode(CODEC) != name:
            raise RectError(f"{name!r}: descriptor name pointer does not name the resource")
        layers = []
        for i in range(count):
            (layer_address,) = struct.unpack_from(">I", data, address + DESCRIPTOR_SIZE + 4 * i)
            layer_address += HEADER_SIZE
            (kind, _size, zero0, _vtable, file_ptr, loaded, flags, state, texture, alpha, *rects) = _LAYER.unpack_from(
                data, layer_address
            )
            if kind != KIND_QUAD:
                raise RectError(f"{name!r}: layer {i} has kind {kind}, only textured quads (1) are supported")
            if _size or zero0 or _vtable or loaded:
                raise RectError(f"{name!r}: layer {i} has runtime fields set on disc")
            layers.append(
                RectLayer(
                    file=_cstring(data, file_ptr + HEADER_SIZE).decode(CODEC),
                    texture=texture,
                    src=tuple(rects[4:8]),
                    dst=tuple(rects[0:4]),
                    flags=flags,
                    state=state,
                    alpha=alpha,
                )
            )
        resources.append(
            RectResource(
                name=name,
                layers=layers,
                mode=mode,
                depth=depth,
                duration=duration,
                brightness=brightness,
                unused_0d=unused,
                effect=effect,
                padding=padding,
            )
        )
        blocks.append((address, address + DESCRIPTOR_SIZE + count * (4 + LAYER_SIZE), index))

    blocks.sort()
    pool_start = blocks[-1][1] if blocks else HEADER_SIZE
    # The blocks must tile the data area without gaps or the rebuilt file would differ.
    position = HEADER_SIZE
    for address, end, _index in blocks:
        if address != position:
            raise RectError(f"Unexpected gap before the block at {address:#x}")
        position = end
    pool = data[pool_start:pool_end].split(b"\0")
    while pool and pool[-1] == b"":
        pool.pop()
    return RectFile(
        resources=resources,
        address_order=[resources[i].name for _a, _e, i in blocks],
        pool_order=[s.decode(CODEC) for s in pool],
        header_tail=data[0x14:HEADER_SIZE],
    )


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
            use(layer.file)
    pool_strings = [s for s in doc.pool_order if s in seen]
    kept = set(pool_strings)
    pool_strings += [s for s in used if s not in kept]

    body = bytearray()
    addresses: dict[str, int] = {}
    layer_addresses: dict[str, list[int]] = {}
    for name in doc.address_order:
        resource = by_name[name]
        address = HEADER_SIZE + len(body)
        addresses[name] = address
        count = len(resource.layers)
        layer_addresses[name] = [address + DESCRIPTOR_SIZE + 4 * count + LAYER_SIZE * i for i in range(count)]
        body += bytes(DESCRIPTOR_SIZE + count * (4 + LAYER_SIZE))
    pool_start = HEADER_SIZE + len(body)

    pool = bytearray()
    offsets: dict[str, int] = {}
    for text in pool_strings:
        offsets[text] = pool_start - HEADER_SIZE + len(pool)
        pool += text.encode(CODEC) + b"\0"
    pool += bytes(-len(pool) % 4)

    relocations: list[int] = []
    for name in doc.address_order:
        resource = by_name[name]
        address = addresses[name]
        if not 0 <= len(resource.layers) <= 255:
            raise RectError(f"{name!r}: a resource holds 1-255 layers")
        if not 0 <= resource.mode <= 255 or not 0 <= resource.depth <= 0xFFFF:
            raise RectError(f"{name!r}: mode or depth out of range")
        if not (0 <= resource.brightness <= 255 and 0 <= resource.unused_0d <= 255 and 0 <= resource.effect <= 255):
            raise RectError(f"{name!r}: a descriptor byte is out of range")
        descriptor = _DESCRIPTOR.pack(
            offsets[name],
            len(resource.layers),
            resource.mode,
            resource.depth,
            resource.duration,
            resource.brightness,
            resource.unused_0d,
            resource.effect,
            resource.padding,
        )
        relocations.append(address - HEADER_SIZE)
        offset = address - HEADER_SIZE
        body[offset:offset + DESCRIPTOR_SIZE] = descriptor
        for i, layer in enumerate(resource.layers):
            slot = address + DESCRIPTOR_SIZE + 4 * i
            struct.pack_into(">I", body, slot - HEADER_SIZE, layer_addresses[name][i] - HEADER_SIZE)
            relocations.append(slot - HEADER_SIZE)
            layer_address = layer_addresses[name][i]
            for values in (layer.src, layer.dst):
                if len(values) != 4:
                    raise RectError(f"{name!r}: layer {i} rectangles need four values")
            if not (0 <= layer.texture <= 255 and 0 <= layer.flags <= 255 and 0 <= layer.state <= 255
                    and 0 <= layer.alpha <= 255):
                raise RectError(f"{name!r}: layer {i} has a byte field out of range")
            _LAYER.pack_into(
                body,
                layer_address - HEADER_SIZE,
                KIND_QUAD, 0, 0, 0, offsets[layer.file], 0,
                layer.flags, layer.state, layer.texture, layer.alpha,
                *layer.dst, *layer.src,
            )
            relocations.append(layer_address + 8 - HEADER_SIZE)
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


def validate(doc: RectFile, texture_sizes: Callable[[str], list[tuple[int, int]] | None]) -> list[str]:
    """Problems the engine would not report itself. ``texture_sizes(path)``
    returns the (width, height) of every image of a TPL, or None when the file
    is missing."""
    problems = []
    cache: dict[str, list[tuple[int, int]] | None] = {}
    for resource in doc.resources:
        if not resource.name.startswith("RID_"):
            problems.append(f"{resource.name}: names conventionally start with RID_")
        if resource.mode > MODE_CROSSFADE:
            problems.append(f"{resource.name}: mode {resource.mode} draws nothing")
        for i, layer in enumerate(resource.layers):
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
            for l in r.layers
        ]
        entries.append(RectEntry(r.name.encode(CODEC), r.name.encode(CODEC), flags, images))
    return entries


def read_rects_path(path: Path | str) -> list[RectEntry]:
    with open(path, "rb") as stream:
        return read_rects(io.BytesIO(stream.read()))
