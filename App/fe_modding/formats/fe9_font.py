"""Read and write FE9 GCF fonts: a glyph table plus GX I4 atlas sheets.

Layout, lookup and which font is used where: research/FONT_NOTES.md. ``build_gcf`` writes a
font from glyph bitmaps, and ``import_truetype`` renders a TrueType/OpenType file into the
metrics of an existing game font.
"""
from __future__ import annotations

import io
import struct
from dataclasses import dataclass, field
from pathlib import Path
import numpy as np
from PIL import Image, ImageDraw, ImageFont
from . import tpl


@dataclass(frozen=True)
class Glyph:
    code: int
    sheet: int
    x: int
    y: int
    width: int
    height: int
    bearing_x: int
    bearing_y: int
    advance: int


MISSING_GLYPH_CODE = 0x8199  # font_missing_glyph_key in main.dol

#: Font index -> (name, file under files/). Index order is game_font_handles; ``#Fxx`` uses it.
#: The system font is read from the LZ10 ``.cms`` (``system.gcf`` is never loaded); fonts 1-4 are
#: also bundled in ``system.cmp``, which the build refreshes from the loose files.
FONT_FILES = (("system", "Fonts/system.cms"), ("fe_font", "Fonts/fe_font.gcf"),
              ("talk", "Fonts/talk.gcf"), ("bigkana", "Fonts/bigkana.gcf"), ("alpha", "Fonts/alpha.gcf"))
#: Radiant Dawn: the same GCF fonts, every one LZ10-wrapped, each with a ``_w`` twin drawn in 16:9
#: mode. The game's table (US 0x80382a20) holds a (4:3, 16:9) path pair per index: 0 system,
#: 1 fe_font, 2 talk, 3 bigkana, 4 alpha, 5 ruby (ruby has one file for both). ``debug.cms`` is on the
#: disc but no table points at it.
FONT_FILES_FE10 = (("system", "Fonts/system.cms"), ("system_w", "Fonts/system_w.cms"),
                   ("fe_font", "Fonts/fe_font.cms"), ("fe_font_w", "Fonts/fe_font_w.cms"),
                   ("talk", "Fonts/talk.cms"), ("talk_w", "Fonts/talk_w.cms"),
                   ("bigkana", "Fonts/bigkana.cms"), ("bigkana_w", "Fonts/bigkana_w.cms"),
                   ("alpha", "Fonts/alpha.cms"), ("alpha_w", "Fonts/alpha_w.cms"), ("ruby", "Fonts/ruby.cms"))


@dataclass(frozen=True)
class GlyphBitmap:
    """One glyph as drawn: an L-mode coverage mask plus its placement metrics."""
    mask: Image.Image
    bearing_x: int
    bearing_y: int
    advance: int


def code_of(char: str) -> int:
    """The game text code of a character (one byte, or a two-byte CP932 code)."""
    try:
        return int.from_bytes(char.encode("cp932"), "big")
    except UnicodeEncodeError:
        raise ValueError(f"U+{ord(char):04X} has no game text encoding") from None


def char_of(code: int) -> str | None:
    """The character a glyph code stands for, or None when CP932 has none."""
    try:
        return (bytes((code,)) if code < 0x100 else code.to_bytes(2, "big")).decode("cp932")
    except UnicodeDecodeError:
        return None


class GameFont:
    def __init__(self, data: bytes):
        if len(data) < 48:
            raise ValueError("Truncated GCF header")
        self.ascent, self.descent = struct.unpack_from(">HH", data, 8)
        self.sheet_size = struct.unpack_from(">I", data, 20)[0]
        sheet_count = struct.unpack_from(">H", data, 26)[0]
        self.width, self.height, table = struct.unpack_from(">HHH", data, 30)
        pixels = struct.unpack_from(">I", data, 36)[0]
        if (not self.width or not self.height or table < 48 or pixels < table
                or self.sheet_size != self.width * self.height // 2
                or pixels + sheet_count * self.sheet_size > len(data)):
            raise ValueError("Invalid GCF atlas/table bounds")
        self.glyphs = {}
        for offset in range(table, pixels - 15, 16):
            values = struct.unpack_from(">4H2B3b", data, offset)
            if values[0] == 0:
                continue
            glyph = Glyph(*values)
            if (glyph.sheet >= sheet_count or glyph.x + glyph.width > self.width
                    or glyph.y + glyph.height > self.height):
                raise ValueError(f"Invalid GCF glyph {glyph.code:04x}")
            self.glyphs[glyph.code] = glyph
        if not self.glyphs:
            raise ValueError("GCF font has no glyphs")
        self.sheet_count = sheet_count
        self._first = self.glyphs[min(self.glyphs)]
        self._data, self._pixels = data, pixels
        self._sheets: dict[int, Image.Image] = {}
        self._glyph_images: dict[int, Image.Image] = {}

    def glyph(self, char: str) -> Glyph:
        """Look a character up the way font_find_glyph does.

        Text is CP932 (Shift-JIS plus the NEC 0x87xx row the fonts carry). A code the
        font lacks draws the 0x8199 white star, or the first record when that is missing too.
        """
        code = code_of(char)
        return self.glyphs.get(code) or self.glyphs.get(MISSING_GLYPH_CODE) or self._first

    def has(self, char: str) -> bool:
        try:
            return code_of(char) in self.glyphs
        except ValueError:
            return False

    def sheet(self, index: int) -> Image.Image:
        """Sheet ``index`` as an L-mode coverage image."""
        if index not in self._sheets:
            self._sheets[index] = tpl._decode_i4(
                io.BytesIO(self._data), self._pixels + index * self.sheet_size,
                self.width, self.height).getchannel("R")
        return self._sheets[index]

    def mask(self, glyph: Glyph) -> Image.Image:
        if glyph.code not in self._glyph_images:
            self._glyph_images[glyph.code] = self.sheet(glyph.sheet).crop(
                (glyph.x, glyph.y, glyph.x + glyph.width, glyph.y + glyph.height))
        return self._glyph_images[glyph.code]

    def bitmaps(self) -> dict[int, GlyphBitmap]:
        return {code: GlyphBitmap(self.mask(g), g.bearing_x, g.bearing_y, g.advance)
                for code, g in self.glyphs.items()}

    def measure(self, text: str) -> int:
        return max((sum(self.glyph(c).advance for c in line) for line in text.split("\n")), default=0)

    def draw(self, image: Image.Image, text: str, xy: tuple[int, int], *,
             color=(255, 255, 255, 255), line_height=28, shadow=True) -> None:
        x, y = xy
        for char in text:
            if char == "\n":
                x, y = xy[0], y + line_height
                continue
            glyph = self.glyph(char)
            mask = self.mask(glyph)
            point = (x + glyph.bearing_x, y + self.ascent - glyph.bearing_y)
            if shadow:
                shadow_image = Image.new("RGBA", mask.size, (0, 0, 0, 255))
                shadow_image.putalpha(mask)
                image.alpha_composite(shadow_image, (point[0] + 1, point[1] + 1))
            ink = Image.new("RGBA", mask.size, color)
            ink.putalpha(mask.point(lambda a: a * color[3] // 255))
            image.alpha_composite(ink, point)
            x += glyph.advance


def _encode_i4(sheet: np.ndarray) -> bytes:
    """An (h, w) uint8 coverage array as GX I4: 8x8 tiles, high nibble = left pixel."""
    h, w = sheet.shape
    v = (sheet.astype(np.uint16) * 15 + 127) // 255
    tiles = v.reshape(h // 8, 8, w // 8, 8).transpose(0, 2, 1, 3).reshape(-1, 2)
    return ((tiles[:, 0] << 4) | tiles[:, 1]).astype(np.uint8).tobytes()


def build_gcf(bitmaps: dict[int, GlyphBitmap], *, ascent: int, descent: int,
              sheet_width: int = 256, sheet_height: int = 256) -> bytes:
    """Write a GCF font. Glyphs are shelf-packed tallest first with a 1-pixel gutter, on as
    many I4 sheets as they need; empty glyphs get the 1x1 blank box vanilla uses."""
    if not bitmaps:
        raise ValueError("A font needs at least one glyph")
    if sheet_width % 8 or sheet_height % 8:
        raise ValueError("Sheet size must be a multiple of 8")
    masks = {}
    for code, glyph in bitmaps.items():
        if not 0 < code <= 0xFFFF:
            raise ValueError(f"Invalid glyph code {code:#x}")
        for name, value in (("bearing X", glyph.bearing_x), ("bearing Y", glyph.bearing_y),
                            ("advance", glyph.advance)):
            if not -128 <= value <= 127:
                raise ValueError(f"Glyph {code:04X}: {name} {value} is outside -128..127")
        mask = glyph.mask.convert("L")
        if mask.width == 0 or mask.height == 0 or mask.getbbox() is None:
            mask = Image.new("L", (1, 1))
        if mask.width > min(255, sheet_width) or mask.height > min(255, sheet_height):
            raise ValueError(f"Glyph {code:04X} is {mask.width}x{mask.height}, larger than a sheet or 255 px")
        masks[code] = mask

    # First-fit decreasing height: each glyph goes on the first shelf tall enough with room left.
    placed: dict[int, tuple[int, int, int]] = {}
    sheets: list[np.ndarray] = []
    shelves: list[list[int]] = []  # [sheet, y, height, next free x]
    next_y: list[int] = []         # first free row of each sheet
    for code in sorted(masks, key=lambda c: (-masks[c].height, -masks[c].width, c)):
        mask = masks[code]
        w, h = mask.size
        shelf = next((s for s in shelves if s[2] >= h and s[3] + w <= sheet_width), None)
        if shelf is None:
            sheet = next((i for i, y in enumerate(next_y) if y + h <= sheet_height), None)
            if sheet is None:
                sheets.append(np.zeros((sheet_height, sheet_width), np.uint8))
                next_y.append(0)
                sheet = len(sheets) - 1
            shelf = [sheet, next_y[sheet], h, 0]
            shelves.append(shelf)
            next_y[sheet] += h + 1
        sheet, y, _, x = shelf
        sheets[sheet][y:y + h, x:x + w] = np.asarray(mask)
        placed[code] = (sheet, x, y)
        shelf[3] = x + w + 1

    table = 0x30
    pixels = table + 16 * len(masks)
    pixels += -pixels % 32  # keep sheet data 32-byte aligned for GX
    sheet_size = sheet_width * sheet_height // 2
    header = struct.pack(">IHHHHHHHHIHHHHHHIII", 0x20, max(masks), 0, ascent, descent,
                         max(m.width for m in masks.values()), 0, 0, 0, sheet_size, 0,
                         len(sheets), 0, sheet_width, sheet_height, table, pixels,
                         len(sheets) * sheet_size, 0)
    records = bytearray()
    for code in sorted(masks):
        sheet, gx, gy = placed[code]
        g, mask = bitmaps[code], masks[code]
        records += struct.pack(">4H2B3b3x", code, sheet, gx, gy, mask.width, mask.height,
                               g.bearing_x, g.bearing_y, g.advance)
    body = header + records
    # Padding records are all zero, which the loader trims from the glyph count.
    body += bytes(pixels - len(body))
    return bytes(body) + b"".join(_encode_i4(s) for s in sheets)


def rebuild(font: GameFont, replacements: dict[int, GlyphBitmap] | None = None) -> bytes:
    """``font`` rewritten with ``replacements`` (added or replacing glyphs) on the same sheet size."""
    bitmaps = font.bitmaps()
    bitmaps.update(replacements or {})
    return build_gcf(bitmaps, ascent=font.ascent, descent=font.descent,
                     sheet_width=font.width, sheet_height=font.height)


def truetype_coverage(path: Path | str) -> set[int] | None:
    """Code points a TrueType/OpenType file maps, or None when fontTools is not installed."""
    try:
        from fontTools.ttLib import TTFont
    except ImportError:
        return None
    with TTFont(str(path), fontNumber=0, lazy=True) as ttf:
        return set(ttf.getBestCmap() or {})


@dataclass
class ImportOptions:
    """How ``import_truetype`` renders a TrueType/OpenType file into a game font.

    ``size`` is the FreeType pixel size (None: match the capital H of the font being replaced).
    ``characters`` limits the import to these characters; None means every glyph the game font
    already has. ``add`` lists characters to add when the game font lacks them. ``x_offset`` and
    ``y_offset`` move glyphs right and down; ``spacing`` widens every advance."""
    size: int | None = None
    characters: str | None = None
    add: str = ""
    antialias: bool = True
    x_offset: int = 0
    y_offset: int = 0
    spacing: int = 0


@dataclass
class ImportResult:
    data: bytes
    size: int
    replaced: list[str] = field(default_factory=list)
    added: list[str] = field(default_factory=list)
    kept: list[str] = field(default_factory=list)         # not in the TrueType file: game glyph kept
    unencodable: list[str] = field(default_factory=list)  # no CP932 code, so no game text can reach it


def auto_size(path: Path | str, base: GameFont) -> int:
    """The pixel size whose capital H is as tall as the game font's (fallback: its ascent)."""
    target = base.glyphs[0x48].bearing_y if 0x48 in base.glyphs else base.ascent
    best, best_error = 8, None
    for size in range(6, 97):
        error = abs(-ImageFont.truetype(str(path), size).getbbox("H", anchor="ls")[1] - target)
        if best_error is None or error < best_error:
            best, best_error = size, error
    return best


def render_truetype_glyph(font: ImageFont.FreeTypeFont, char: str, *, antialias=True,
                          x_offset=0, y_offset=0, spacing=0) -> GlyphBitmap:
    left, top, right, bottom = font.getbbox(char, anchor="ls")
    advance = round(font.getlength(char)) + spacing
    if right <= left or bottom <= top:
        return GlyphBitmap(Image.new("L", (1, 1)), 0, 0, advance)
    mask = Image.new("L", (right - left, bottom - top))
    draw = ImageDraw.Draw(mask)
    draw.fontmode = "L" if antialias else "1"
    draw.text((-left, -top), char, font=font, fill=255, anchor="ls")
    return GlyphBitmap(mask, left + x_offset, -top - y_offset, advance)


def import_truetype(base: GameFont, path: Path | str, options: ImportOptions | None = None) -> ImportResult:
    """Replace ``base``'s glyphs with ones rendered from a TrueType/OpenType file.

    Ascent, descent and sheet size stay the game font's, so text keeps its line positions.
    Glyphs the file lacks keep their game bitmaps, so a Latin font over the talk font leaves
    the kana and kanji alone."""
    options = options or ImportOptions()
    size = options.size or auto_size(path, base)
    font = ImageFont.truetype(str(path), size)
    coverage = truetype_coverage(path)
    if options.characters is None:
        wanted = [c for c in map(char_of, sorted(base.glyphs)) if c]
    else:
        wanted = [c for c in options.characters if c != "\n"]
    wanted += [c for c in options.add if c != "\n"]
    result = ImportResult(b"", size)
    replacements = {}
    for char in dict.fromkeys(wanted):
        try:
            code = code_of(char)
        except ValueError:
            result.unencodable.append(char)
            continue
        if coverage is not None:
            covered = ord(char) in coverage
        else:
            covered = char == " " or font.getmask(char).getbbox() is not None
        if not covered:
            if code in base.glyphs:
                result.kept.append(char)
            continue
        replacements[code] = render_truetype_glyph(
            font, char, antialias=options.antialias, x_offset=options.x_offset,
            y_offset=options.y_offset, spacing=options.spacing)
        (result.replaced if code in base.glyphs else result.added).append(char)
    result.data = rebuild(base, replacements)
    return result
