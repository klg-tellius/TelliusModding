import os
import sys
import unittest
from pathlib import Path
from PIL import Image, ImageDraw

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fe_modding.formats import fe9_message_scene as ms
from fe_modding.formats import lz10
from fe_modding.formats.fe9_font import (FONT_FILES, GameFont, GlyphBitmap, ImportOptions, build_gcf,
                                         char_of, code_of, import_truetype, rebuild)


def _quantized(image):
    # I4 keeps 16 levels, so compare against the 4-bit value each pixel is stored as.
    return image.point(lambda v: (v * 15 + 127) // 255 * 17).tobytes()


def _bitmap(size, bearing_y, advance, fill=255):
    mask = Image.new("L", size)
    ImageDraw.Draw(mask).rectangle((0, 0, size[0] - 1, size[1] - 1), outline=fill)
    return GlyphBitmap(mask, 0, bearing_y, advance)


class GcfWriterTests(unittest.TestCase):
    def test_build_and_read_back(self):
        bitmaps = {0x20: GlyphBitmap(Image.new("L", (1, 1)), 0, 0, 6),
                   0x41: _bitmap((12, 16), 16, 13, 200),
                   0x8199: _bitmap((20, 20), 18, 22)}
        data = build_gcf(bitmaps, ascent=22, descent=5, sheet_width=64, sheet_height=64)
        font = GameFont(data)
        self.assertEqual((font.ascent, font.descent, font.width, font.height), (22, 5, 64, 64))
        self.assertEqual(sorted(font.glyphs), [0x20, 0x41, 0x8199])
        glyph = font.glyphs[0x41]
        self.assertEqual((glyph.width, glyph.height, glyph.bearing_y, glyph.advance), (12, 16, 16, 13))
        self.assertEqual(font.mask(glyph).tobytes(), _quantized(bitmaps[0x41].mask))
        self.assertEqual(int.from_bytes(data[0x24:0x28], "big") % 32, 0)
        self.assertEqual(int.from_bytes(data[4:6], "big"), 0x8199)       # max_code
        self.assertEqual(int.from_bytes(data[0xC:0xE], "big"), 20)       # max_glyph_width
        self.assertEqual(font.glyph("唸").code, 0x8199)                  # missing -> star

    def test_packing_spills_onto_new_sheets(self):
        bitmaps = {0x8140 + i: _bitmap((30, 30), 28, 30) for i in range(10)}
        font = GameFont(build_gcf(bitmaps, ascent=28, descent=4, sheet_width=64, sheet_height=64))
        self.assertEqual(font.sheet_count, 3)  # four 30x30 boxes (with gutter) fit on a 64x64 sheet
        boxes = {}
        for glyph in font.glyphs.values():
            for other in boxes.get(glyph.sheet, []):
                self.assertFalse(glyph.x < other.x + other.width and other.x < glyph.x + glyph.width
                                 and glyph.y < other.y + other.height and other.y < glyph.y + glyph.height)
            boxes.setdefault(glyph.sheet, []).append(glyph)

    def test_rejects_out_of_range_metrics(self):
        with self.assertRaises(ValueError):
            build_gcf({0x41: GlyphBitmap(Image.new("L", (4, 4), 255), 0, 200, 4)}, ascent=10, descent=2)

    def test_codes(self):
        self.assertEqual(code_of("A"), 0x41)
        self.assertEqual(code_of("①"), 0x8740)
        self.assertEqual(char_of(0x8740), "①")
        with self.assertRaises(ValueError):
            code_of("é")


class FontMarkupTests(unittest.TestCase):
    def test_tellius_wraps_each_line_like_vanilla(self):
        text = "Leanne!\nIs it you?"
        new, start, end = ms.apply_font(text, 0, len(text), 1)
        self.assertEqual(new, "#F01$O2Leanne!#F02$O1\n#F01$O2Is it you?#F02$O1")
        self.assertEqual((start, end), (0, len(new)))
        self.assertEqual(ms.strip_fonts(new, 0, len(new))[0], text)

    def test_partial_selection_and_cursor(self):
        new, *_ = ms.apply_font("Say Leanne now", 4, 10, 3)
        self.assertEqual(new, "Say #F03Leanne#F02 now")
        new, start, end = ms.apply_font("ab", 1, 1, 4)
        self.assertEqual((new, start, end), ("a#F04#F02b", 5, 5))

    def test_describe(self):
        self.assertIn("Tellius", ms.describe_inline("#F01"))
        self.assertIn("ancient", ms.describe_inline("$O2"))
        self.assertIn(";", ms.describe_inline("#F01$O2"))


def _system_ttf():
    for name in ("georgia.ttf", "arial.ttf", "DejaVuSans.ttf"):
        for folder in (Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts", Path("/usr/share/fonts/truetype/dejavu")):
            if (folder / name).is_file():
                return folder / name
    return None


@unittest.skipUnless(_system_ttf(), "no TrueType font found on this machine")
class TrueTypeImportTests(unittest.TestCase):
    def test_import_replaces_latin_and_keeps_the_rest(self):
        base = GameFont(build_gcf({0x41: _bitmap((10, 14), 14, 11), 0x82A0: _bitmap((18, 18), 16, 20),
                                   0x20: GlyphBitmap(Image.new("L", (1, 1)), 0, 0, 5)},
                                  ascent=22, descent=5))
        result = import_truetype(base, _system_ttf(), ImportOptions(add="B"))
        font = GameFont(result.data)
        self.assertIn("A", result.replaced)
        self.assertEqual(result.added, ["B"])
        self.assertEqual(font.ascent, 22)
        self.assertEqual(font.glyphs[0x82A0].advance, 20)  # あ is kept from the game font
        self.assertNotEqual(font.mask(font.glyphs[0x41]).size, (10, 14))


@unittest.skipUnless(os.environ.get("FE9_EXTRACTED"), "set FE9_EXTRACTED for local asset validation")
class VanillaFontTests(unittest.TestCase):
    def test_rebuild_keeps_every_glyph(self):
        files = next(Path(os.environ["FE9_EXTRACTED"]).glob("**/files/Fonts")).parent
        for name, relative in FONT_FILES:
            with self.subTest(font=name):
                data = (files / relative).read_bytes()
                if relative.endswith(".cms"):
                    data = lz10.decompress(data)
                before = GameFont(data)
                rebuilt = rebuild(before)
                after = GameFont(rebuilt)
                self.assertLessEqual(len(rebuilt), len(data))
                self.assertEqual(before.glyphs.keys(), after.glyphs.keys())
                for code, glyph in before.glyphs.items():
                    other = after.glyphs[code]
                    self.assertEqual((glyph.width, glyph.height, glyph.bearing_x, glyph.bearing_y, glyph.advance),
                                     (other.width, other.height, other.bearing_x, other.bearing_y, other.advance))
                    self.assertEqual(before.mask(glyph).tobytes(), after.mask(other).tobytes())


if __name__ == "__main__":
    unittest.main()
