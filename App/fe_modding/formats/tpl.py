"""Decode/encode GameCube/Wii ``.tpl`` texture containers as Pillow images.

A TPL holds one or more images, each with its own pixel format, using GX's
standard texture format enum (the same public spec CMPR/C8 below come from -
e.g. Dolphin's TextureDecoder/libogc's GX enum). Nine formats are decodable;
all nine now have working *encoders* too (write support, used by the
import/replace flow - see replace_image() / ENCODABLE_FORMATS):

- CMPR (format 14, GX's S3TC-like 4x4 block compression) - confirmed
  against real backgrounds (files/s/*, see the background viewer).
- an 8-bit palette-indexed format (matches GX C8: one byte per pixel, 8x4
  tiling) - confirmed against real portraits (Face/*.cms, see the portrait
  viewer). This is also where a real bug got caught: the palette's
  RGB5A3 decode was checking the wrong bit for opaque-vs-alpha (see
  _rgb5a3()) - fixed after a real portrait decoded with a corrupted patch
  of wrong colors under the old logic.

Seven more formats were added once real files outside backgrounds/portraits
(files/window, files/gmap, files/etc, files/zu - see graphics_viewers.py)
turned out to use them, raising TplError instead of displaying. All seven
started as decode-only and later gained encoders too (see below):

- I4 (format 0) - 4-bit grayscale, 8x8 tiling. Encoded by luminance-
  converting the source image and quantizing to 4 bits/pixel.
- IA4 (format 2) - 4-bit intensity + 4-bit alpha packed in one byte (high
  nibble intensity, low nibble alpha), 8x4 tiling like C8.
- IA8 (format 3) - 8-bit intensity + 8-bit alpha packed in one big-endian
  u16 (high byte intensity, low byte alpha), 4x4 tiling.
- RGB565 (format 4) - 16-bit color, opaque, 4x4 tiling. Encoded with the
  same _to_rgb565() helper CMPR's endpoint colors already use.
- RGB5A3 (format 5) - 16-bit color - reuses the same _rgb5a3() helper the
  C8 palette already decodes with (and the new _from_rgb5a3() to encode:
  a fully-opaque pixel always takes the higher-precision RGB555 branch,
  everything else the lower-precision ARGB3444 branch, mirroring the
  decoder's own bit-15 branch), 4x4 tiling.
- RGBA8 (format 6) - 32-bit color, 4x4 tiling but stored as two
  interleaved 32-byte AR/GB sub-blocks per tile - GX's one genuinely
  unusual tiling layout among the formats seen so far.
- C4 (format 8) - 4-bit palette index (packed 2/byte, same nibble order as
  I4), 8x8 tiling - otherwise the same palette-resolve path as C8
  (_read_palette()), just twice the pixels per index byte. This is also
  where a second real palette format turned up: every C8 palette seen
  before this was GX TLUT format 2 (RGB5A3) - the one real C4 file found
  (files/window/logo.cms) uses format 1 (RGB565, opaque, no alpha) instead.
  _read_palette() now decodes both; format 0 (IA8) is the one remaining GX
  palette format with no real example yet, so it still raises. Like C8,
  encoding is against the slot's *existing* palette (encode_c4()) - not
  regenerated, same reasoning as encode_palette_indexed().

A header-only scan of every real file under files/s, files/Face, and the
six graphics_viewers.py folders (1517 files, 7371 images) found every
image using one of these nine formats - no other format value has turned
up. Each decoder was spot-checked against a real image before being
trusted (an achievement popup's alpha-blended RGBA8 background, small I4/
RGB5A3 world-map icons) - all decoded clean, no corruption. The five
formats with no natural alpha/palette precision loss beyond quantization
(I4, IA4, IA8, RGB565, RGBA8) round-trip straightforwardly; RGB5A3 and C4
carry the same kind of lossy-but-principled quantization CMPR/C8 already
did before this. None of the seven encoders have been checked against a
real disc rebuild yet (unlike CMPR/C8) - see graphics_viewers.py's own
validation notes for what has and hasn't been confirmed end-to-end.

Any other format value still raises TplError rather than guessing - GX
defines a couple more (I8, C14X2) that no real file examined by this app
has needed yet.

Requires Pillow and numpy (not core dependencies of the rest of this app -
only import this module if you need texture extraction). Decoding is
vectorized with numpy (whole blocks at a time rather than one pixel per
Python loop step); its output is byte-identical to the per-pixel decoders it
replaced, checked on every texture of a Path of Radiance disc.
"""

from __future__ import annotations

import io
import struct
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO

import numpy as np

try:
    from PIL import Image
except ImportError as exc:
    raise ImportError("fe_modding.formats.tpl requires Pillow: pip install Pillow") from exc

MAGIC = 0x0020AF30
FORMAT_I4 = 0
FORMAT_IA4 = 2
FORMAT_IA8 = 3
FORMAT_RGB565 = 4
FORMAT_RGB5A3 = 5
FORMAT_RGBA8 = 6
FORMAT_C4 = 8
FORMAT_C8 = 9
FORMAT_CMPR = 14
CMPR_BLOCK = 8  # CMPR is tiled in 8x8 blocks, 32 bytes each (4 4x4 sub-blocks x 8 bytes)
C8_BLOCK_W, C8_BLOCK_H = 8, 4  # C8 is tiled in 8x4 blocks, 32 bytes each (1 byte/pixel)
I4_BLOCK = 8  # I4 is tiled in 8x8 blocks, 32 bytes each (4 bits/pixel)
IA4_BLOCK_W, IA4_BLOCK_H = 8, 4  # IA4 is tiled in 8x4 blocks, 32 bytes each (1 byte/pixel)
IA8_BLOCK = 4  # IA8 is tiled in 4x4 blocks, 32 bytes each (2 bytes/pixel)
RGB565_BLOCK = 4  # RGB565 is tiled in 4x4 blocks, 32 bytes each (2 bytes/pixel)
RGB5A3_BLOCK = 4  # RGB5A3 is tiled in 4x4 blocks, 32 bytes each (2 bytes/pixel)
RGBA8_BLOCK = 4  # RGBA8 is tiled in 4x4 blocks, 64 bytes each (2 interleaved 32-byte AR/GB sub-blocks)
C4_BLOCK = 8  # C4 is tiled in 8x8 blocks, 32 bytes each (4 bits/pixel, same nibble order as I4)

_OTHER_FORMAT_NAMES = {
    FORMAT_I4: "I4",
    FORMAT_IA4: "IA4",
    FORMAT_IA8: "IA8",
    FORMAT_RGB565: "RGB565",
    FORMAT_RGB5A3: "RGB5A3",
    FORMAT_RGBA8: "RGBA8",
    FORMAT_C4: "C4",
}

# Every format this module can both decode and encode - what GUI import
# flows should gate "can this image be replaced" on (see replace_image()).
ENCODABLE_FORMATS = {
    FORMAT_CMPR,
    FORMAT_C8,
    FORMAT_C4,
    FORMAT_I4,
    FORMAT_IA4,
    FORMAT_IA8,
    FORMAT_RGB565,
    FORMAT_RGB5A3,
    FORMAT_RGBA8,
}

# (block_w, block_h, bytes_per_block) for every tiled format whose encoded
# size is a plain "pixels per block, bytes per block" formula - i.e.
# everything except CMPR/C8, which keep their own named *_data_length()
# functions for backwards compatibility (both predate this table).
_BLOCK_SPECS = {
    FORMAT_I4: (I4_BLOCK, I4_BLOCK, 32),
    FORMAT_IA4: (IA4_BLOCK_W, IA4_BLOCK_H, 32),
    FORMAT_IA8: (IA8_BLOCK, IA8_BLOCK, 32),
    FORMAT_RGB565: (RGB565_BLOCK, RGB565_BLOCK, 32),
    FORMAT_RGB5A3: (RGB5A3_BLOCK, RGB5A3_BLOCK, 32),
    FORMAT_RGBA8: (RGBA8_BLOCK, RGBA8_BLOCK, 64),
    FORMAT_C4: (C4_BLOCK, C4_BLOCK, 32),
}


def format_name(fmt: int) -> str:
    """Human-readable name for a TPL format value, for GUI status labels."""
    if fmt == FORMAT_CMPR:
        return "CMPR"
    if fmt == FORMAT_C8:
        return "C8"
    return _OTHER_FORMAT_NAMES.get(fmt, f"format {fmt}")


def _block_data_length(width: int, height: int, block_w: int, block_h: int, bytes_per_block: int) -> int:
    blocks_x = (width + block_w - 1) // block_w
    blocks_y = (height + block_h - 1) // block_h
    return blocks_x * blocks_y * bytes_per_block


class TplError(Exception):
    pass


@dataclass(frozen=True)
class TplImageInfo:
    index: int
    width: int
    height: int
    format: int
    data_addr: int
    palette_offset: int
    wrap_s: int
    wrap_t: int
    min_filter: int
    mag_filter: int
    lod_bias: float

    @property
    def data_length(self) -> int:
        if self.format == FORMAT_CMPR:
            return cmpr_data_length(self.width, self.height)
        if self.format == FORMAT_C8:
            return c8_data_length(self.width, self.height)
        if self.format in _BLOCK_SPECS:
            return _block_data_length(self.width, self.height, *_BLOCK_SPECS[self.format])
        raise TplError(f"data_length is not defined for format {self.format}.")


def cmpr_data_length(width: int, height: int) -> int:
    blocks_x = (width + CMPR_BLOCK - 1) // CMPR_BLOCK
    blocks_y = (height + CMPR_BLOCK - 1) // CMPR_BLOCK
    return blocks_x * blocks_y * 32


def c8_data_length(width: int, height: int) -> int:
    blocks_x = (width + C8_BLOCK_W - 1) // C8_BLOCK_W
    blocks_y = (height + C8_BLOCK_H - 1) // C8_BLOCK_H
    return blocks_x * blocks_y * (C8_BLOCK_W * C8_BLOCK_H)


def _iter_image_headers(stream: BinaryIO):
    header = stream.read(12)
    magic, num_images, offset_image = struct.unpack(">III", header)
    if magic != MAGIC:
        raise TplError(f"Not a TPL file (expected magic {MAGIC:#x}, got {magic:#x}).")

    next_addr = offset_image
    for i in range(num_images):
        stream.seek(next_addr)
        next_addr += 8
        offset, palette_offset = struct.unpack(">II", stream.read(8))

        stream.seek(offset)
        height, width, fmt, data_addr = struct.unpack(">HHII", stream.read(12))
        wrap_s, wrap_t, min_filter, mag_filter, lod_bias = struct.unpack(">IIIIf", stream.read(20))

        yield TplImageInfo(
            index=i,
            width=width,
            height=height,
            format=fmt,
            data_addr=data_addr,
            palette_offset=palette_offset,
            wrap_s=wrap_s,
            wrap_t=wrap_t,
            min_filter=min_filter,
            mag_filter=mag_filter,
            lod_bias=lod_bias,
        )


def read_tpl_image_info(stream: BinaryIO) -> list[TplImageInfo]:
    return list(_iter_image_headers(stream))


def read_tpl_image_info_path(path: Path | str) -> list[TplImageInfo]:
    with open(path, "rb") as stream:
        return read_tpl_image_info(stream)


def read_tpl_images(stream: BinaryIO) -> list["Image.Image"]:
    images = []
    palette_cache: dict[int, list[tuple[int, int, int, int]]] = {}

    for info in _iter_image_headers(stream):
        if info.format == FORMAT_CMPR:
            images.append(_decode_cmpr(stream, info.data_addr, info.width, info.height))
        elif info.format == FORMAT_C8:
            if info.palette_offset not in palette_cache:
                palette_cache[info.palette_offset] = _read_palette(stream, info.palette_offset)
            images.append(
                _decode_palette_indexed(stream, info.data_addr, info.width, info.height, palette_cache[info.palette_offset])
            )
        elif info.format == FORMAT_C4:
            if info.palette_offset not in palette_cache:
                palette_cache[info.palette_offset] = _read_palette(stream, info.palette_offset)
            images.append(
                _decode_c4(stream, info.data_addr, info.width, info.height, palette_cache[info.palette_offset])
            )
        elif info.format == FORMAT_I4:
            images.append(_decode_i4(stream, info.data_addr, info.width, info.height))
        elif info.format == FORMAT_IA4:
            images.append(_decode_ia4(stream, info.data_addr, info.width, info.height))
        elif info.format == FORMAT_IA8:
            images.append(_decode_ia8(stream, info.data_addr, info.width, info.height))
        elif info.format == FORMAT_RGB565:
            images.append(_decode_rgb565(stream, info.data_addr, info.width, info.height))
        elif info.format == FORMAT_RGB5A3:
            images.append(_decode_rgb5a3(stream, info.data_addr, info.width, info.height))
        elif info.format == FORMAT_RGBA8:
            images.append(_decode_rgba8(stream, info.data_addr, info.width, info.height))
        else:
            raise TplError(
                f"Unrecognized image format {info.format} (known formats: CMPR={FORMAT_CMPR}, C8={FORMAT_C8}, "
                f"C4={FORMAT_C4}, I4={FORMAT_I4}, IA4={FORMAT_IA4}, IA8={FORMAT_IA8}, "
                f"RGB565={FORMAT_RGB565}, RGB5A3={FORMAT_RGB5A3}, RGBA8={FORMAT_RGBA8})."
            )

    return images


def read_tpl_images_path(path: Path | str) -> list["Image.Image"]:
    with open(path, "rb") as stream:
        return read_tpl_images(stream)


def replace_image(tpl_bytes: bytes, image_index: int, new_image: "Image.Image") -> bytes:
    """Return a copy of tpl_bytes with one image's pixel data replaced.

    new_image is resized (stretched, not cropped) to the target slot's exact
    width/height, then re-encoded in whatever format that slot already uses:

    - CMPR: encoded fresh (encode_cmpr()), full RGB color range.
    - C8 (palette-indexed): new_image's pixels are nearest-color-matched
      into the slot's *existing* palette, which is NOT regenerated. This
      isn't a shortcut - portrait files store one palette shared by every
      image in the file (confirmed on a real portrait: 13 of its 14 images,
      including several tiny ones that read like eye/mouth animation
      frames, all pointed at the same palette), so changing it would also
      recolor every other image sharing it. The tradeoff: a replacement
      image is limited to colors already in that character's original
      palette (up to 256), so a very differently-colored image will look
      posterized/off. There's no way around that without redesigning how
      multiple images reference one palette.

    Either way, the encoded size is fully determined by width/height (see
    cmpr_data_length()/c8_data_length()), so the replacement always fits
    exactly - this overwrites that one byte range in place, same approach as
    dispo.patch_unit_field(): no container structure to regenerate, so
    nothing else in the file can get corrupted by this.
    """
    infos = read_tpl_image_info(io.BytesIO(tpl_bytes))
    if image_index >= len(infos):
        raise TplError(f"Image index {image_index} out of range (this file has {len(infos)} images).")
    info = infos[image_index]

    resized_rgba = new_image.convert("RGBA").resize((info.width, info.height), Image.LANCZOS)

    if info.format == FORMAT_CMPR:
        encoded = encode_cmpr(resized_rgba.convert("RGB"))
    elif info.format == FORMAT_C8:
        palette = _read_palette(io.BytesIO(tpl_bytes), info.palette_offset)
        encoded = encode_palette_indexed(resized_rgba, palette)
    elif info.format == FORMAT_C4:
        palette = _read_palette(io.BytesIO(tpl_bytes), info.palette_offset)
        encoded = encode_c4(resized_rgba, palette)
    elif info.format == FORMAT_I4:
        encoded = encode_i4(resized_rgba)
    elif info.format == FORMAT_IA4:
        encoded = encode_ia4(resized_rgba)
    elif info.format == FORMAT_IA8:
        encoded = encode_ia8(resized_rgba)
    elif info.format == FORMAT_RGB565:
        encoded = encode_rgb565(resized_rgba)
    elif info.format == FORMAT_RGB5A3:
        encoded = encode_rgb5a3(resized_rgba)
    elif info.format == FORMAT_RGBA8:
        encoded = encode_rgba8(resized_rgba)
    else:
        raise TplError(f"Can't encode format {info.format} - no encoder implemented.")

    if len(encoded) != info.data_length:
        raise TplError(  # pragma: no cover - would indicate a bug in *_data_length()/encode_*() agreeing
            f"Encoded size {len(encoded)} doesn't match the {info.data_length}-byte slot for "
            f"{info.width}x{info.height} - this is an internal bug, not a bad input image."
        )

    out = bytearray(tpl_bytes)
    out[info.data_addr : info.data_addr + len(encoded)] = encoded
    return bytes(out)


def _block_geometry(fmt: int) -> tuple[int, int, int]:
    """(block width, block height, bytes per block) of a GX format."""
    if fmt == FORMAT_CMPR:
        return CMPR_BLOCK, CMPR_BLOCK, 32
    if fmt == FORMAT_C8:
        return C8_BLOCK_W, C8_BLOCK_H, C8_BLOCK_W * C8_BLOCK_H
    if fmt in _BLOCK_SPECS:
        return _BLOCK_SPECS[fmt]
    raise TplError(f"Unknown block layout for format {fmt}.")


def replace_region(
    tpl_bytes: bytes, image_index: int, box: tuple[int, int, int, int], new_image: "Image.Image"
) -> bytes:
    """Return a copy of tpl_bytes with one rectangle of one image replaced -
    one icon of an icon sheet. ``box`` is (left, top, right, bottom);
    new_image is stretched to its size.

    Every pixel outside ``box`` decodes exactly as before, so the other
    icons of the sheet never pick up re-encoding loss. A C8/C4 image whose
    palette no other image of the file uses gets the new colors written
    into palette entries no pixel outside ``box`` needs (duplicate entries
    are merged to make room - the icon sheets repeat dozens of colors), so
    the icon keeps its own colors instead of snapping to the old palette;
    only when those run out is it quantized to fit. Any other format is
    re-encoded as replace_image() would, then only the blocks touching
    ``box`` are copied back.
    """
    infos = read_tpl_image_info(io.BytesIO(tpl_bytes))
    if image_index >= len(infos):
        raise TplError(f"Image index {image_index} out of range (this file has {len(infos)} images).")
    info = infos[image_index]
    left, top, right, bottom = box
    if not (0 <= left < right <= info.width and 0 <= top < bottom <= info.height):
        raise TplError(f"Region {box} is outside the {info.width}x{info.height} image.")
    cell = new_image.convert("RGBA").resize((right - left, bottom - top), Image.LANCZOS)

    shared = any(other.palette_offset == info.palette_offset for other in infos if other.index != image_index)
    if info.format in (FORMAT_C8, FORMAT_C4) and not shared:
        (palette_format,) = struct.unpack_from(">xxxxI", tpl_bytes, info.palette_offset)
        if palette_format == 2:
            return _replace_region_own_palette(tpl_bytes, info, box, cell)

    sheet = read_tpl_images(io.BytesIO(tpl_bytes))[image_index].convert("RGBA")
    sheet.paste(cell, (left, top))
    encoded = replace_image(tpl_bytes, image_index, sheet)
    block_w, block_h, block_bytes = _block_geometry(info.format)
    blocks_x = (info.width + block_w - 1) // block_w
    out = bytearray(tpl_bytes)
    for by in range(top // block_h, (bottom - 1) // block_h + 1):
        for bx in range(left // block_w, (right - 1) // block_w + 1):
            start = info.data_addr + (by * blocks_x + bx) * block_bytes
            out[start : start + block_bytes] = encoded[start : start + block_bytes]
    return bytes(out)


def _rgb5a3_nearest(rgba: tuple[int, int, int, int]) -> int:
    """The RGB5A3 value whose _rgb5a3() decode is closest to ``rgba`` -
    the inverse of the decoder's own scaling (5-bit x 8, 4-bit x 0x11,
    3-bit alpha x 0x20), so a color read back from a sheet re-encodes to
    the value it came from."""
    r, g, b, a = rgba
    if a >= 255:
        return 0x8000 | (min(31, round(r / 8)) << 10) | (min(31, round(g / 8)) << 5) | min(31, round(b / 8))
    return (min(7, round(a / 32)) << 12) | (round(r / 17) << 8) | (round(g / 17) << 4) | round(b / 17)


def _replace_region_own_palette(
    tpl_bytes: bytes, info: TplImageInfo, box: tuple[int, int, int, int], cell: "Image.Image"
) -> bytes:
    left, top, right, bottom = box
    block_w, block_h, block_bytes = _block_geometry(info.format)
    length, _fmt, palette_data = struct.unpack_from(">HxxII", tpl_bytes, info.palette_offset)
    palette = _read_palette(io.BytesIO(tpl_bytes), info.palette_offset)

    tiles = _read_tiles(io.BytesIO(tpl_bytes), info.data_addr, info.width, info.height, block_w, block_h, block_bytes)
    if info.format == FORMAT_C4:
        tiles = _nibbles(tiles)
    blocks_y, blocks_x = tiles.shape[:2]
    grid = tiles.reshape(blocks_y, blocks_x, block_h, block_w).transpose(0, 2, 1, 3)
    grid = grid.reshape(blocks_y * block_h, blocks_x * block_w).copy()

    # Entries repeating an earlier entry's value are merged into it first:
    # the sheets carry dozens of such duplicates, and folding them changes
    # no pixel while freeing their slots for the new icon's colors.
    first_of_value: dict[int, int] = {}
    lut = np.arange(max(length, 1 << (4 if info.format == FORMAT_C4 else 8)), dtype=np.uint8)
    for i in range(length):
        lut[i] = first_of_value.setdefault(_palette_value(tpl_bytes, palette_data, i), i)
    grid = lut[grid]

    outside = np.ones(grid.shape, dtype=bool)
    outside[top:bottom, left:right] = False
    used = {int(i) for i in np.unique(grid[outside]) if i < length}
    free = [i for i in range(length) if i not in used]
    existing = {}
    for i in sorted(used):
        existing.setdefault(palette[i], i)

    # Snap every pixel to an RGB5A3 value (fully transparent ones to one key)
    # and see whether the colors not already in the palette fit the free entries.
    def rounded(image: "Image.Image") -> "np.ndarray":
        pixels = np.array(image, dtype=np.uint8).reshape(-1, 4)
        values = np.empty(len(pixels), dtype=np.uint16)
        cache: dict[tuple, int] = {}
        for n, rgba in enumerate(map(tuple, pixels)):
            value = cache.get(rgba)
            if value is None:
                if rgba in existing:
                    value = cache[rgba] = _palette_value(tpl_bytes, palette_data, existing[rgba])
                elif rgba[3] < 16:
                    value = cache[rgba] = 0
                else:
                    value = cache[rgba] = _rgb5a3_nearest(rgba)
            values[n] = value
        return values

    by_value: dict[int, int] = {}
    for i in sorted(used):
        by_value.setdefault(_palette_value(tpl_bytes, palette_data, i), i)
    transparent_index = next((i for i in sorted(used) if palette[i][3] == 0), None)

    def needed(values: "np.ndarray") -> list[int]:
        out = []
        for value in np.unique(values):
            value = int(value)
            if value in by_value or (not value & 0x8000 and value >> 12 == 0 and transparent_index is not None):
                continue
            out.append(value)
        return out

    values = rounded(cell)
    new_values = needed(values)
    if len(new_values) > len(free):
        # Too many colors: reduce the icon to a manageable set, give the free
        # entries to its most-used new colors and snap the rest to the
        # nearest color available (already in the palette or just added).
        clean = np.array(cell, dtype=np.uint8)
        clean[clean[..., 3] < 16] = 0
        quantized = Image.fromarray(clean, "RGBA").quantize(min(256, len(free) + 64), method=Image.Quantize.FASTOCTREE)
        values = rounded(quantized.convert("RGBA"))
        counts = dict(zip(*(v.tolist() for v in np.unique(values, return_counts=True))))
        new_values = sorted(needed(values), key=lambda v: -counts[v])
        allowed = set(new_values[: len(free)])
        choices = [(v, _rgb5a3(v)) for v in list(by_value) + sorted(allowed)]
        remap = {}
        for value in set(new_values) - allowed:
            r, g, b, a = _rgb5a3(value)
            remap[value] = min(
                choices, key=lambda c: (c[1][0] - r) ** 2 + (c[1][1] - g) ** 2 + (c[1][2] - b) ** 2 + (c[1][3] - a) ** 2
            )[0]
        values = np.array([remap.get(int(v), int(v)) for v in values], dtype=np.uint16)
        new_values = sorted(allowed)

    out = bytearray(tpl_bytes)
    for value, index in zip(new_values, free):
        by_value[value] = index
        struct.pack_into(">H", out, palette_data + index * 2, value)

    def index_of(value: int) -> int:
        if value in by_value:
            return by_value[value]
        return transparent_index  # a fully transparent pixel reuses the palette's transparent entry

    grid[top:bottom, left:right] = np.array([index_of(int(v)) for v in values], dtype=np.uint8).reshape(
        bottom - top, right - left
    )
    tiled = grid.reshape(blocks_y, block_h, blocks_x, block_w).transpose(0, 2, 1, 3).reshape(blocks_y, blocks_x, -1)
    if info.format == FORMAT_C4:
        tiled = (tiled[..., 0::2] << 4) | tiled[..., 1::2]
    data = tiled.astype(np.uint8).tobytes()
    out[info.data_addr : info.data_addr + len(data)] = data
    return bytes(out)


def _palette_value(tpl_bytes: bytes, palette_data: int, index: int) -> int:
    (value,) = struct.unpack_from(">H", tpl_bytes, palette_data + index * 2)
    return value


def _read_palette(stream: BinaryIO, palette_offset: int) -> list[tuple[int, int, int, int]]:
    stream.seek(palette_offset)
    length, fmt, data_offset = struct.unpack(">HxxII", stream.read(12))
    # GX TLUT formats: 0=IA8, 1=RGB565, 2=RGB5A3. Only 2 (C8's palette, e.g.
    # portraits) and 1 (a real C4 palette - files/window/logo.cms) have been
    # confirmed against real data; 0 raises rather than guessing.
    if fmt == 2:
        decode_entry = _rgb5a3
    elif fmt == 1:
        decode_entry = _rgb565
    else:
        raise TplError(f"Unrecognized palette format {fmt} (only RGB5A3=2 and RGB565=1 have been confirmed).")

    stream.seek(data_offset)
    palette = []
    for _ in range(length):
        (value,) = struct.unpack(">H", stream.read(2))
        palette.append(decode_entry(value))
    return palette


def _rgb5a3(value: int) -> tuple[int, int, int, int]:
    # Standard GX RGB5A3: bit 15 (0x8000) selects opaque RGB555 vs ARGB3444.
    # The original script checked 0x80 (bit 7) instead - confirmed wrong by
    # testing against a real portrait (IKE.cms, format 9/C8): 0x80 produced
    # a corrupted patch of wrong colors on part of the face; 0x8000 decoded
    # it correctly (and revealed the "corruption" at other pixels was
    # actually intentional alpha=0 transparency - see the portrait viewer's
    # docstring for what that transparent region is for).
    if value & 0x8000:
        r = 0x8 * ((value >> 10) & 0b11111)
        g = 0x8 * ((value >> 5) & 0b11111)
        b = 0x8 * (value & 0b11111)
        return (r, g, b, 255)
    a = 0x20 * ((value >> 12) & 0b111)
    r = 0x11 * ((value >> 8) & 0b1111)
    g = 0x11 * ((value >> 4) & 0b1111)
    b = 0x11 * (value & 0b1111)
    return (r, g, b, a)


def _from_rgb5a3(rgba: tuple[int, int, int, int]) -> int:
    """Inverse of _rgb5a3(): a fully-opaque pixel always takes the
    higher-precision RGB555 branch (bit 15 set) - there's no reason to
    spend a bit of color precision on the alpha branch for a pixel that
    doesn't need alpha at all - everything else takes the ARGB3444 branch,
    mirroring the decoder's own bit-15 split."""
    r, g, b, a = rgba
    if a >= 255:
        r5 = round(r / 255 * 31)
        g5 = round(g / 255 * 31)
        b5 = round(b / 255 * 31)
        return 0x8000 | (r5 << 10) | (g5 << 5) | b5
    a3 = round(a / 255 * 7)
    r4 = round(r / 255 * 15)
    g4 = round(g / 255 * 15)
    b4 = round(b / 255 * 15)
    return (a3 << 12) | (r4 << 8) | (g4 << 4) | b4


def _rgb565(value: int) -> tuple[int, int, int, int]:
    r = 0x8 * ((value >> 11) & 0b11111)
    g = 0x4 * ((value >> 5) & 0b111111)
    b = 0x8 * (value & 0b11111)
    return (r, g, b, 255)


def _read_tiles(
    stream: BinaryIO, addr: int, width: int, height: int, block_w: int, block_h: int, bytes_per_block: int
) -> "np.ndarray":
    """The image's raw blocks as a (blocks_y, blocks_x, bytes_per_block)
    uint8 array - every GX format stores whole blocks, row by row."""
    blocks_x = (width + block_w - 1) // block_w
    blocks_y = (height + block_h - 1) // block_h
    length = blocks_x * blocks_y * bytes_per_block
    stream.seek(addr)
    data = stream.read(length)
    if len(data) < length:
        raise TplError(f"Image data truncated: expected {length} bytes at {addr:#x}, got {len(data)}.")
    return np.frombuffer(data, dtype=np.uint8).reshape(blocks_y, blocks_x, bytes_per_block)


def _untile(pixels: "np.ndarray", width: int, height: int, block_w: int, block_h: int) -> "Image.Image":
    """(blocks_y, blocks_x, block_h * block_w, 4) RGBA pixels, each block in
    row-major order, to an RGBA image cropped to width x height."""
    blocks_y, blocks_x = pixels.shape[:2]
    rows = pixels.reshape(blocks_y, blocks_x, block_h, block_w, 4).transpose(0, 2, 1, 3, 4)
    full = rows.reshape(blocks_y * block_h, blocks_x * block_w, 4)[:height, :width]
    return Image.fromarray(np.ascontiguousarray(full, dtype=np.uint8), mode="RGBA")


def _gray_alpha(value: "np.ndarray", alpha: "np.ndarray") -> "np.ndarray":
    return np.stack((value, value, value, alpha), axis=-1).astype(np.uint8)


def _nibbles(tiles: "np.ndarray") -> "np.ndarray":
    """Split each byte into (high, low) nibbles - the high nibble is the left pixel."""
    return np.stack((tiles >> 4, tiles & 0xF), axis=-1).reshape(tiles.shape[:-1] + (-1,))


def _u16(tiles: "np.ndarray") -> "np.ndarray":
    return (tiles[..., 0::2].astype(np.uint16) << 8) | tiles[..., 1::2]


def _rgb5a3_array(value: "np.ndarray") -> "np.ndarray":
    """Vectorized _rgb5a3()."""
    value = value.astype(np.int32)
    opaque = (value & 0x8000) != 0
    r = np.where(opaque, 0x8 * ((value >> 10) & 0x1F), 0x11 * ((value >> 8) & 0xF))
    g = np.where(opaque, 0x8 * ((value >> 5) & 0x1F), 0x11 * ((value >> 4) & 0xF))
    b = np.where(opaque, 0x8 * (value & 0x1F), 0x11 * (value & 0xF))
    a = np.where(opaque, 255, 0x20 * ((value >> 12) & 0x7))
    return np.stack((r, g, b, a), axis=-1).astype(np.uint8)


def _rgb565_array(value: "np.ndarray") -> "np.ndarray":
    """Vectorized _rgb565()."""
    value = value.astype(np.int32)
    r = 0x8 * ((value >> 11) & 0x1F)
    g = 0x4 * ((value >> 5) & 0x3F)
    b = 0x8 * (value & 0x1F)
    return np.stack((r, g, b, np.full_like(r, 255)), axis=-1).astype(np.uint8)


def _palette_array(palette: list[tuple[int, int, int, int]]) -> "np.ndarray":
    return np.array(palette, dtype=np.uint8).reshape(-1, 4)


def _decode_palette_indexed(
    stream: BinaryIO, addr: int, width: int, height: int, palette: list[tuple[int, int, int, int]]
) -> "Image.Image":
    tiles = _read_tiles(stream, addr, width, height, C8_BLOCK_W, C8_BLOCK_H, C8_BLOCK_W * C8_BLOCK_H)
    return _untile(_palette_array(palette)[tiles], width, height, C8_BLOCK_W, C8_BLOCK_H)


def _decode_cmpr(stream: BinaryIO, addr: int, width: int, height: int) -> "Image.Image":
    tiles = _read_tiles(stream, addr, width, height, CMPR_BLOCK, CMPR_BLOCK, 32)
    blocks_y, blocks_x = tiles.shape[:2]
    # 4 sub-blocks per 8x8 block (top-left, top-right, bottom-left,
    # bottom-right), each: color0 u16, color1 u16, 16 x 2-bit indices u32
    sub = tiles.reshape(blocks_y, blocks_x, 4, 8).astype(np.uint32)
    color0 = (sub[..., 0] << 8) | sub[..., 1]
    color1 = (sub[..., 2] << 8) | sub[..., 3]
    bits = (sub[..., 4] << 24) | (sub[..., 5] << 16) | (sub[..., 6] << 8) | sub[..., 7]

    c0 = _rgb565_array(color0)[..., :3].astype(np.int32)
    c1 = _rgb565_array(color1)[..., :3].astype(np.int32)
    four_color = (color0 > color1)[..., None]
    # np.round rounds half to even, like _cmpr_subblock_palette()'s round()
    c2 = np.where(four_color, c0 + np.round((c1 - c0) / 3), c0 + np.round((c1 - c0) / 2))
    c3 = np.where(four_color, c0 + np.round(2 * (c1 - c0) / 3), 0)
    colors = np.empty(color0.shape + (4, 4), dtype=np.uint8)
    colors[..., 0, :3] = c0
    colors[..., 1, :3] = c1
    colors[..., 2, :3] = c2
    colors[..., 3, :3] = c3
    colors[..., :3, 3] = 255
    colors[..., 3, 3] = np.where(four_color[..., 0], 255, 0)

    shifts = np.arange(30, -1, -2, dtype=np.uint32)
    indices = ((bits[..., None] >> shifts) & 0b11).astype(np.intp)  # (by, bx, sub, 16)
    pixels = np.take_along_axis(colors, indices[..., None], axis=-2)  # (by, bx, sub, 16, rgba)
    # (by, bx, sub_y, sub_x, y, x, rgba) -> row-major 8x8 block
    pixels = pixels.reshape(blocks_y, blocks_x, 2, 2, 4, 4, 4).transpose(0, 1, 2, 4, 3, 5, 6)
    return _untile(pixels.reshape(blocks_y, blocks_x, 64, 4), width, height, CMPR_BLOCK, CMPR_BLOCK)


def _decode_i4(stream: BinaryIO, addr: int, width: int, height: int) -> "Image.Image":
    tiles = _read_tiles(stream, addr, width, height, I4_BLOCK, I4_BLOCK, 32)
    v = _nibbles(tiles) * 17  # scale 4-bit (0-15) to 8-bit (0-255)
    return _untile(_gray_alpha(v, np.full_like(v, 255)), width, height, I4_BLOCK, I4_BLOCK)


def _decode_rgb5a3(stream: BinaryIO, addr: int, width: int, height: int) -> "Image.Image":
    tiles = _read_tiles(stream, addr, width, height, RGB5A3_BLOCK, RGB5A3_BLOCK, 32)
    return _untile(_rgb5a3_array(_u16(tiles)), width, height, RGB5A3_BLOCK, RGB5A3_BLOCK)


def _decode_ia4(stream: BinaryIO, addr: int, width: int, height: int) -> "Image.Image":
    tiles = _read_tiles(stream, addr, width, height, IA4_BLOCK_W, IA4_BLOCK_H, 32)
    # high nibble: intensity, low nibble: alpha
    return _untile(_gray_alpha((tiles >> 4) * 17, (tiles & 0xF) * 17), width, height, IA4_BLOCK_W, IA4_BLOCK_H)


def _decode_ia8(stream: BinaryIO, addr: int, width: int, height: int) -> "Image.Image":
    tiles = _read_tiles(stream, addr, width, height, IA8_BLOCK, IA8_BLOCK, 32)
    # high byte: intensity, low byte: alpha
    return _untile(_gray_alpha(tiles[..., 0::2], tiles[..., 1::2]), width, height, IA8_BLOCK, IA8_BLOCK)


def _decode_rgb565(stream: BinaryIO, addr: int, width: int, height: int) -> "Image.Image":
    tiles = _read_tiles(stream, addr, width, height, RGB565_BLOCK, RGB565_BLOCK, 32)
    return _untile(_rgb565_array(_u16(tiles)), width, height, RGB565_BLOCK, RGB565_BLOCK)


def _decode_c4(
    stream: BinaryIO, addr: int, width: int, height: int, palette: list[tuple[int, int, int, int]]
) -> "Image.Image":
    tiles = _read_tiles(stream, addr, width, height, C4_BLOCK, C4_BLOCK, 32)
    return _untile(_palette_array(palette)[_nibbles(tiles)], width, height, C4_BLOCK, C4_BLOCK)


def _decode_rgba8(stream: BinaryIO, addr: int, width: int, height: int) -> "Image.Image":
    tiles = _read_tiles(stream, addr, width, height, RGBA8_BLOCK, RGBA8_BLOCK, 64)
    ar, gb = tiles[..., :32], tiles[..., 32:]  # 16 pixels x (A, R) bytes, then 16 x (G, B)
    pixels = np.stack((ar[..., 1::2], gb[..., 0::2], gb[..., 1::2], ar[..., 0::2]), axis=-1)
    return _untile(pixels, width, height, RGBA8_BLOCK, RGBA8_BLOCK)


def _cmpr_subblock_palette(color0: int, color1: int) -> list[tuple[int, int, int, int]]:
    def rgb565(value: int) -> tuple[int, int, int]:
        r = 0x8 * ((value >> 11) & 0b11111)
        g = 0x4 * ((value >> 5) & 0b111111)
        b = 0x8 * (value & 0b11111)
        return (r, g, b)

    c0 = rgb565(color0)
    c1 = rgb565(color1)

    if color0 > color1:
        c2 = tuple(c0[i] + round((c1[i] - c0[i]) / 3) for i in range(3))
        c3 = tuple(c0[i] + round(2 * (c1[i] - c0[i]) / 3) for i in range(3))
        return [(*c0, 255), (*c1, 255), (*c2, 255), (*c3, 255)]

    c2 = tuple(c0[i] + round((c1[i] - c0[i]) / 2) for i in range(3))
    return [(*c0, 255), (*c1, 255), (*c2, 255), (0, 0, 0, 0)]


def encode_cmpr(image: "Image.Image") -> bytes:
    """Encode an RGB or RGBA image as CMPR. image.size determines the output
    size - resize to the target slot's exact dimensions before calling this
    (replace_image() does that for you).

    An RGB image is encoded in 4-opaque-color mode (color0 > color1) only.
    In an RGBA image, a 4x4 block holding a pixel with alpha below 128 uses
    the 3-color mode, whose 4th index is transparent (1-bit alpha, as in
    the vanilla battle-model textures); other blocks stay opaque.
    """
    width, height = image.size
    if image.mode not in ("RGB", "RGBA"):
        image = image.convert("RGB")
    pixels = image.load()
    out = bytearray()

    for y_block in range((height + CMPR_BLOCK - 1) // CMPR_BLOCK):
        for x_block in range((width + CMPR_BLOCK - 1) // CMPR_BLOCK):
            for sub_block in range(4):
                block_pixels = []
                for pixel in range(16):
                    x = x_block * CMPR_BLOCK + ((sub_block % 2) * 4) + (pixel % 4)
                    y = y_block * CMPR_BLOCK + ((sub_block // 2) * 4) + (pixel // 4)
                    # Pad past the image edge by repeating the nearest real pixel - decode()
                    # never reads these back (it skips out-of-bounds the same way), so this
                    # only has to be *some* valid color, not a specific one.
                    x = min(x, width - 1)
                    y = min(y, height - 1)
                    block_pixels.append(pixels[x, y])
                out += _encode_cmpr_subblock(block_pixels)

    return bytes(out)


def encode_palette_indexed(image: "Image.Image", palette: list[tuple[int, int, int, int]]) -> bytes:
    """Encode an RGBA image as C8 against a *fixed, existing* palette (not
    regenerated - see replace_image()'s docstring for why). Each pixel picks
    the closest palette entry by RGBA distance, so a transparent source
    pixel is steered toward a transparent palette entry (if the palette has
    one) rather than an opaque color that happens to be nearby in hue.
    """
    width, height = image.size
    pixels = image.load()
    out = bytearray()
    cache: dict[tuple[int, int, int, int], int] = {}

    def nearest_index(rgba: tuple[int, int, int, int]) -> int:
        cached = cache.get(rgba)
        if cached is not None:
            return cached
        r, g, b, a = rgba
        best_index, _ = min(
            enumerate(palette),
            key=lambda kv: (kv[1][0] - r) ** 2 + (kv[1][1] - g) ** 2 + (kv[1][2] - b) ** 2 + (kv[1][3] - a) ** 2,
        )
        cache[rgba] = best_index
        return best_index

    for y_block in range((height + C8_BLOCK_H - 1) // C8_BLOCK_H):
        for x_block in range((width + C8_BLOCK_W - 1) // C8_BLOCK_W):
            for index in range(C8_BLOCK_W * C8_BLOCK_H):
                x = min(x_block * C8_BLOCK_W + (index % C8_BLOCK_W), width - 1)
                y = min(y_block * C8_BLOCK_H + (index // C8_BLOCK_W), height - 1)
                out.append(nearest_index(pixels[x, y]))

    return bytes(out)


def encode_c4(image: "Image.Image", palette: list[tuple[int, int, int, int]]) -> bytes:
    """Encode as C4 (4-bit palette index, 2 pixels/byte, 8x8 tiling) against
    a *fixed, existing* palette - same discipline as
    encode_palette_indexed() and for the same reason (see replace_image()'s
    docstring): a replacement image is limited to whatever colors the
    slot's original palette already has.
    """
    width, height = image.size
    rgba = image.convert("RGBA")
    pixels = rgba.load()
    out = bytearray()
    cache: dict[tuple[int, int, int, int], int] = {}

    def nearest_index(rgba_px: tuple[int, int, int, int]) -> int:
        cached = cache.get(rgba_px)
        if cached is not None:
            return cached
        r, g, b, a = rgba_px
        best_index, _ = min(
            enumerate(palette),
            key=lambda kv: (kv[1][0] - r) ** 2 + (kv[1][1] - g) ** 2 + (kv[1][2] - b) ** 2 + (kv[1][3] - a) ** 2,
        )
        cache[rgba_px] = best_index
        return best_index

    for y_block in range((height + C4_BLOCK - 1) // C4_BLOCK):
        for x_block in range((width + C4_BLOCK - 1) // C4_BLOCK):
            for y in range(C4_BLOCK):
                for x in range(0, C4_BLOCK, 2):
                    nibbles = []
                    for dx in (0, 1):
                        px = min(x_block * C4_BLOCK + x + dx, width - 1)
                        py = min(y_block * C4_BLOCK + y, height - 1)
                        nibbles.append(nearest_index(pixels[px, py]))
                    out.append((nibbles[0] << 4) | nibbles[1])

    return bytes(out)


def encode_i4(image: "Image.Image") -> bytes:
    """Encode as I4 (4-bit grayscale, no alpha, 2 pixels/byte, 8x8 tiling).
    Luminance-converts the source image and quantizes to 4 bits/pixel."""
    width, height = image.size
    gray = image.convert("L")
    pixels = gray.load()
    out = bytearray()

    for y_block in range((height + I4_BLOCK - 1) // I4_BLOCK):
        for x_block in range((width + I4_BLOCK - 1) // I4_BLOCK):
            for y in range(I4_BLOCK):
                for x in range(0, I4_BLOCK, 2):
                    nibbles = []
                    for dx in (0, 1):
                        px = min(x_block * I4_BLOCK + x + dx, width - 1)
                        py = min(y_block * I4_BLOCK + y, height - 1)
                        nibbles.append(round(pixels[px, py] / 17))
                    out.append((nibbles[0] << 4) | nibbles[1])

    return bytes(out)


def encode_ia4(image: "Image.Image") -> bytes:
    """Encode as IA4 (4-bit intensity + 4-bit alpha, one byte/pixel, 8x4
    tiling like C8)."""
    width, height = image.size
    rgba = image.convert("RGBA")
    gray_px = rgba.convert("L").load()
    rgba_px = rgba.load()
    out = bytearray()
    block_w, block_h = IA4_BLOCK_W, IA4_BLOCK_H

    for y_block in range((height + block_h - 1) // block_h):
        for x_block in range((width + block_w - 1) // block_w):
            for y in range(block_h):
                for x in range(block_w):
                    px = min(x_block * block_w + x, width - 1)
                    py = min(y_block * block_h + y, height - 1)
                    v = round(gray_px[px, py] / 17)
                    a = round(rgba_px[px, py][3] / 17)
                    out.append((v << 4) | a)

    return bytes(out)


def encode_ia8(image: "Image.Image") -> bytes:
    """Encode as IA8 (8-bit intensity + 8-bit alpha packed in one
    big-endian u16, 4x4 tiling)."""
    width, height = image.size
    rgba = image.convert("RGBA")
    gray_px = rgba.convert("L").load()
    rgba_px = rgba.load()
    out = bytearray()

    for y_block in range((height + IA8_BLOCK - 1) // IA8_BLOCK):
        for x_block in range((width + IA8_BLOCK - 1) // IA8_BLOCK):
            for y in range(IA8_BLOCK):
                for x in range(IA8_BLOCK):
                    px = min(x_block * IA8_BLOCK + x, width - 1)
                    py = min(y_block * IA8_BLOCK + y, height - 1)
                    v = gray_px[px, py]
                    a = rgba_px[px, py][3]
                    out += struct.pack(">H", (v << 8) | a)

    return bytes(out)


def encode_rgb565(image: "Image.Image") -> bytes:
    """Encode as RGB565 (16-bit color, opaque, 4x4 tiling)."""
    width, height = image.size
    pixels = image.convert("RGB").load()
    out = bytearray()

    for y_block in range((height + RGB565_BLOCK - 1) // RGB565_BLOCK):
        for x_block in range((width + RGB565_BLOCK - 1) // RGB565_BLOCK):
            for y in range(RGB565_BLOCK):
                for x in range(RGB565_BLOCK):
                    px = min(x_block * RGB565_BLOCK + x, width - 1)
                    py = min(y_block * RGB565_BLOCK + y, height - 1)
                    out += struct.pack(">H", _to_rgb565(pixels[px, py]))

    return bytes(out)


def encode_rgb5a3(image: "Image.Image") -> bytes:
    """Encode as RGB5A3 (16-bit color, 4x4 tiling) via _from_rgb5a3()."""
    width, height = image.size
    pixels = image.convert("RGBA").load()
    out = bytearray()

    for y_block in range((height + RGB5A3_BLOCK - 1) // RGB5A3_BLOCK):
        for x_block in range((width + RGB5A3_BLOCK - 1) // RGB5A3_BLOCK):
            for y in range(RGB5A3_BLOCK):
                for x in range(RGB5A3_BLOCK):
                    px = min(x_block * RGB5A3_BLOCK + x, width - 1)
                    py = min(y_block * RGB5A3_BLOCK + y, height - 1)
                    out += struct.pack(">H", _from_rgb5a3(pixels[px, py]))

    return bytes(out)


def encode_rgba8(image: "Image.Image") -> bytes:
    """Encode as RGBA8 (32-bit color, 4x4 tiling stored as two interleaved
    32-byte AR/GB sub-blocks per tile, mirroring _decode_rgba8())."""
    width, height = image.size
    pixels = image.convert("RGBA").load()
    out = bytearray()

    for y_block in range((height + RGBA8_BLOCK - 1) // RGBA8_BLOCK):
        for x_block in range((width + RGBA8_BLOCK - 1) // RGBA8_BLOCK):
            ar = bytearray()
            gb = bytearray()
            for i in range(16):
                px = min(x_block * RGBA8_BLOCK + (i % RGBA8_BLOCK), width - 1)
                py = min(y_block * RGBA8_BLOCK + (i // RGBA8_BLOCK), height - 1)
                r, g, b, a = pixels[px, py]
                ar += bytes((a, r))
                gb += bytes((g, b))
            out += ar
            out += gb

    return bytes(out)


def _to_rgb565(color: tuple[int, int, int]) -> int:
    r, g, b = color
    r5 = round(r / 255 * 31)
    g6 = round(g / 255 * 63)
    b5 = round(b / 255 * 31)
    return (r5 << 11) | (g6 << 5) | b5


def _encode_cmpr_subblock(pixels: list[tuple[int, ...]]) -> bytes:
    if any(len(p) > 3 and p[3] < 128 for p in pixels):
        return _encode_cmpr_subblock_transparent(pixels)
    # Endpoints: the two pixels furthest apart in RGB space (16 pixels -> 120
    # pairs, cheap enough to brute-force and much better than per-channel
    # min/max for blocks with an off-axis color gradient).
    best_pair = (pixels[0], pixels[0])
    best_dist = -1
    for i in range(len(pixels)):
        for j in range(i + 1, len(pixels)):
            dr = pixels[i][0] - pixels[j][0]
            dg = pixels[i][1] - pixels[j][1]
            db = pixels[i][2] - pixels[j][2]
            dist = dr * dr + dg * dg + db * db
            if dist > best_dist:
                best_dist = dist
                best_pair = (pixels[i], pixels[j])

    color0 = _to_rgb565(best_pair[0][:3])
    color1 = _to_rgb565(best_pair[1][:3])
    if color0 <= color1:
        color0, color1 = color1, color0
    if color0 == color1:  # flat block; nudge apart so we stay in 4-opaque-color mode
        color0 = min(color0 + 1, 0xFFFF)

    palette = _cmpr_subblock_palette(color0, color1)

    pixel_bits = 0
    for i, p in enumerate(pixels):
        best_k, _ = min(
            enumerate(palette),
            key=lambda kv: (kv[1][0] - p[0]) ** 2 + (kv[1][1] - p[1]) ** 2 + (kv[1][2] - p[2]) ** 2,
        )
        pixel_bits |= best_k << (30 - 2 * i)

    return struct.pack(">HHI", color0, color1, pixel_bits)


def _encode_cmpr_subblock_transparent(pixels: list[tuple[int, ...]]) -> bytes:
    """3-color mode (color0 <= color1): index 3 for pixels with alpha below
    128, the two endpoints and their midpoint for the others."""
    opaque = [p for p in pixels if p[3] >= 128]
    best_pair, best_dist = ((0, 0, 0), (0, 0, 0)), -1
    for i in range(len(opaque)):
        for j in range(i, len(opaque)):
            dist = sum((opaque[i][k] - opaque[j][k]) ** 2 for k in range(3))
            if dist > best_dist:
                best_dist, best_pair = dist, (opaque[i], opaque[j])
    color0, color1 = sorted((_to_rgb565(best_pair[0][:3]), _to_rgb565(best_pair[1][:3])))
    palette = _cmpr_subblock_palette(color0, color1)[:3]
    pixel_bits = 0
    for i, p in enumerate(pixels):
        if p[3] < 128:
            k = 3
        else:
            k = min(range(3), key=lambda n: sum((palette[n][c] - p[c]) ** 2 for c in range(3)))
        pixel_bits |= k << (30 - 2 * i)
    return struct.pack(">HHI", color0, color1, pixel_bits)


WRAP_CLAMP, WRAP_REPEAT = 0, 1
FILTER_LINEAR = 1

_DIRECT_ENCODERS = {
    FORMAT_CMPR: lambda image: encode_cmpr(image.convert("RGBA")),
    FORMAT_I4: encode_i4,
    FORMAT_IA4: encode_ia4,
    FORMAT_IA8: encode_ia8,
    FORMAT_RGB565: encode_rgb565,
    FORMAT_RGB5A3: encode_rgb5a3,
    FORMAT_RGBA8: encode_rgba8,
}


def build_tpl(images: list[tuple["Image.Image", int]], wrap: int = WRAP_REPEAT) -> bytes:
    """Build a new TPL from ``(image, format)`` pairs - no palette formats,
    no mipmaps (linear min/mag filter, LOD fields zero).

    Same layout as real single- and multi-image files (``etc/curb.tpl``,
    ``zbg/*/texpack.tpl``): the 12-byte header, one 8-byte table entry per
    image (header offset, palette offset 0), the 36-byte image headers back
    to back, then each image's pixel data starting on a 32-byte boundary.
    Images keep their size; GX needs power-of-two sizes for ``wrap`` =
    repeat, which is the caller's job.
    """
    count = len(images)
    headers_at = 12 + 8 * count
    offset = headers_at + 0x24 * count
    out = bytearray(struct.pack(">III", MAGIC, count, 12))
    headers = bytearray()
    blobs = bytearray()
    for i, (image, fmt) in enumerate(images):
        if fmt not in _DIRECT_ENCODERS:
            raise TplError(f"build_tpl cannot encode format {fmt} (palette formats need an existing palette).")
        data = _DIRECT_ENCODERS[fmt](image.convert("RGBA"))
        pad = -(offset + len(blobs)) % 32
        blobs += bytes(pad)
        data_addr = offset + len(blobs)
        blobs += data
        out += struct.pack(">II", headers_at + 0x24 * i, 0)
        width, height = image.size
        headers += struct.pack(
            ">HHIIIIIIf4B", height, width, fmt, data_addr, wrap, wrap, FILTER_LINEAR, FILTER_LINEAR, 0.0, 0, 0, 0, 0
        )
    return bytes(out + headers + blobs)


def append_images(tpl_bytes: bytes, images: list[tuple["Image.Image", int, int]]) -> tuple[bytes, int]:
    """Add ``(image, format, wrap)`` images to the end of an existing TPL
    and return ``(new bytes, index of the first added image)``.

    Existing images keep their index and their bytes (no re-encoding): the
    image table grows in place, everything after it moves down by a
    32-byte multiple (keeping pixel data aligned), and every stored
    offset - table entries, image data, palette headers and palette data -
    is shifted by the same amount. New headers and data go at the end."""
    magic, count, table_at = struct.unpack(">III", tpl_bytes[:12])
    if magic != MAGIC:
        raise TplError(f"Not a TPL file (expected magic {MAGIC:#x}, got {magic:#x}).")
    table_end = table_at + 8 * count
    grow = 8 * len(images)
    shift = grow + (-grow % 32)

    def moved(offset: int) -> int:
        return offset + shift if offset >= table_end else offset

    out = bytearray(tpl_bytes[:table_end]) + bytearray(shift) + bytearray(tpl_bytes[table_end:])
    for i in range(count):
        entry = table_at + 8 * i
        header, palette = struct.unpack(">II", tpl_bytes[entry : entry + 8])
        struct.pack_into(">II", out, entry, moved(header), moved(palette) if palette else 0)
        data_addr = struct.unpack(">I", tpl_bytes[header + 8 : header + 12])[0]
        struct.pack_into(">I", out, moved(header) + 8, moved(data_addr))
        if palette:
            palette_data = struct.unpack(">I", tpl_bytes[palette + 8 : palette + 12])[0]
            struct.pack_into(">I", out, moved(palette) + 8, moved(palette_data))
    struct.pack_into(">I", out, 4, count + len(images))
    for k, (image, fmt, wrap) in enumerate(images):
        if fmt not in _DIRECT_ENCODERS:
            raise TplError(f"append_images cannot encode format {fmt}.")
        out += bytes(-len(out) % 32)
        header_at = len(out)
        data_at = header_at + 0x40
        width, height = image.size
        out += struct.pack(
            ">HHIIIIIIf4B", height, width, fmt, data_at, wrap, wrap, FILTER_LINEAR, FILTER_LINEAR, 0.0, 0, 0, 0, 0
        )
        out += bytes(data_at - len(out))
        out += _DIRECT_ENCODERS[fmt](image.convert("RGBA"))
        struct.pack_into(">II", out, table_end + 8 * k, header_at, 0)
    out += bytes(-len(out) % 32)
    return bytes(out), count


def truncate_images(tpl_bytes: bytes, keep: int) -> bytes:
    """Keep only the first ``keep`` images, rebuilt compactly."""
    count = struct.unpack(">I", tpl_bytes[4:8])[0]
    if keep >= count:
        return tpl_bytes
    return select_images(tpl_bytes, range(keep))


class _Blocks:
    """A TPL's images as blocks (image header, palette header, palette data,
    pixel data); a block runs to the next block or the end of the file."""

    def __init__(self, tpl_bytes: bytes) -> None:
        magic, count, table_at = struct.unpack(">III", tpl_bytes[:12])
        if magic != MAGIC:
            raise TplError(f"Not a TPL file (expected magic {MAGIC:#x}, got {magic:#x}).")
        self.data = tpl_bytes
        self.entries = []
        starts = {table_at, len(tpl_bytes)}
        for i in range(count):
            header, palette = struct.unpack(">II", tpl_bytes[table_at + 8 * i : table_at + 8 * i + 8])
            data = struct.unpack(">I", tpl_bytes[header + 8 : header + 12])[0]
            palette_data = struct.unpack(">I", tpl_bytes[palette + 8 : palette + 12])[0] if palette else 0
            self.entries.append((header, palette, data, palette_data))
            starts |= {header, data} | ({palette, palette_data} if palette else set())
        self._ordered = sorted(starts)

    def block(self, offset: int) -> bytes:
        return self.data[offset : self._ordered[self._ordered.index(offset) + 1]]

    def key(self, index: int) -> bytes:
        header, palette, data, palette_data = self.entries[index]
        head = self.data[header : header + 0x24]
        key = head[:8] + head[12:] + self.block(data).rstrip(b"\0")
        if palette:
            pal = self.data[palette : palette + 12]
            key += b"P" + pal[:8] + self.block(palette_data).rstrip(b"\0")
        return key


def image_keys(tpl_bytes: bytes) -> list[bytes]:
    """One key per image: equal keys are the same image (size, format,
    wrap, filters, pixels and palette), wherever each file stores it."""
    blocks = _Blocks(tpl_bytes)
    return [blocks.key(i) for i in range(len(blocks.entries))]


def combine_images(parts) -> bytes:
    """A new TPL of the images ``indices`` of each ``(tpl_bytes, indices)``
    part, in order. Every kept block is copied unchanged."""
    sources = []
    for tpl_bytes, indices in parts:
        blocks = _Blocks(tpl_bytes)
        indices = list(indices)
        if any(not 0 <= i < len(blocks.entries) for i in indices):
            raise TplError(f"Image index out of range (the TPL has {len(blocks.entries)} images).")
        sources.append((blocks, indices))
    keep = sum(len(indices) for _, indices in sources)
    out = bytearray(struct.pack(">III", MAGIC, keep, 12)) + bytearray(8 * keep)
    placed: dict[tuple[int, int], int] = {}

    def place(part: int, offset: int, align: int) -> int:
        nonlocal out
        if (part, offset) not in placed:
            out += bytes(-len(out) % align)
            placed[part, offset] = len(out)
            out += sources[part][0].block(offset)
        return placed[part, offset]

    kept = [(part, blocks.entries[i]) for part, (blocks, indices) in enumerate(sources) for i in indices]
    for i, (part, (header, palette, data, palette_data)) in enumerate(kept):
        new_header = place(part, header, 4)
        new_palette = place(part, palette, 4) if palette else 0
        struct.pack_into(">II", out, 12 + 8 * i, new_header, new_palette)
    for i, (part, (header, palette, data, palette_data)) in enumerate(kept):
        struct.pack_into(">I", out, placed[part, header] + 8, place(part, data, 32))
        if palette:
            struct.pack_into(">I", out, placed[part, palette] + 8, place(part, palette_data, 32))
    out += bytes(-len(out) % 32)
    return bytes(out)


def select_images(tpl_bytes: bytes, indices) -> bytes:
    """Keep the images at ``indices``, in that order, rebuilt compactly: the
    image at ``indices[k]`` becomes image ``k``. Every kept block (image
    header, palette header, palette data, pixel data) is copied unchanged."""
    return combine_images([(tpl_bytes, indices)])


def copy_images(tpl_bytes: bytes, source: bytes, indices) -> tuple[bytes, int]:
    """Add the images ``indices`` of TPL ``source`` after the images of
    ``tpl_bytes``, bytes unchanged (no re-encoding, palettes kept). Returns
    ``(new bytes, index of the first added image)``."""
    count = struct.unpack(">I", tpl_bytes[4:8])[0]
    return combine_images([(tpl_bytes, range(count)), (source, indices)]), count
