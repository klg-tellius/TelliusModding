"""The two pictures that show a chapter's name, drawn from its title for an added chapter.

- ``window/chapter2/chapN.cms``: the 312x32 strip of the file menu's save slots (one RGB5A3
  image, white text with a dark shadow). The game finds it through a table of chapter numbers
  in ``main.dol`` (``chapter_flow`` extends it to the added chapter numbers).
- ``window/chapter/chapN.cms``: the 480x160 title card shown when the chapter starts
  ("Chapter 1" over "The Battle Begins", RGBA8), loaded by number as ``chap%d.cms``.

Both are LZ10-compressed TPL files. A new chapter's files are the template chapter's with the
image replaced (same size and pixel format), drawn with the game's own large serif font
(``Fonts/bigkana.gcf``); they can be replaced afterwards like any other image.
"""

from __future__ import annotations

import io
import re
from pathlib import Path
from typing import Optional

from PIL import Image, ImageChops, ImageFilter

from .formats import fe9_font, lz10, tpl

STRIP_FOLDER = "window/chapter2"
CARD_FOLDER = "window/chapter"
FONT_FILE = "Fonts/bigkana.gcf"


def strip_name(chapter: int) -> str:
    """The save-menu strip's file name; retail chapter 29 (Ch.27 part 2) reuses chapter 28's."""
    return f"chap{28 if chapter == 29 else chapter}.cms"


def card_name(chapter: int) -> str:
    return f"chap{chapter}.cms"


def split_title(title: str) -> tuple[str, str]:
    """``"Ch.8: Despair and Hope"`` -> (``"Chapter 8"``, ``"Despair and Hope"``)."""
    head, sep, rest = title.partition(":")
    if not sep:
        return "", title.strip()
    head = re.sub(r"^\s*Ch\.\s*", "Chapter ", head.strip())
    return head.strip(), rest.strip()


def _text_mask(font: fe9_font.GameFont, text: str) -> Image.Image:
    """Coverage mask of one line of text, cropped to its ink."""
    canvas = Image.new("RGBA", (max(1, font.measure(text)) + 8, font.ascent + font.descent + 8))
    font.draw(canvas, text, (4, 4), shadow=False)
    mask = canvas.getchannel("A")
    box = mask.getbbox()
    return mask.crop(box) if box else Image.new("L", (1, 1))


def render_strip(font: fe9_font.GameFont, title: str, size=(312, 32)) -> Image.Image:
    """White title with a dark one-pixel shadow, condensed to fit, like the retail strips."""
    mask = _text_mask(font, title.replace(":", ": "))
    height = min(mask.height, size[1] - 4)
    width = min(round(mask.width * height / mask.height * 0.88), size[0] - 6)
    mask = mask.resize((width, height), Image.LANCZOS)
    image = Image.new("RGBA", size)
    top = (size[1] - height) // 2 - 1
    shadow = Image.new("RGBA", mask.size, (40, 40, 48, 255))
    shadow.putalpha(mask)
    image.alpha_composite(shadow, (3, top + 2))
    ink = Image.new("RGBA", mask.size, (255, 255, 255, 255))
    ink.putalpha(mask)
    image.alpha_composite(ink, (2, top))
    return image


def _card_line(mask: Image.Image, height: int, max_width: int) -> Image.Image:
    """One line of the title card: silver-blue gradient letters with a dark outline."""
    width = min(round(mask.width * height / mask.height), max_width)
    mask = mask.resize((width, height), Image.LANCZOS)
    pad = 4
    full = Image.new("L", (width + 2 * pad, height + 2 * pad))
    full.paste(mask, (pad, pad))
    outline = full.filter(ImageFilter.MaxFilter(5))
    gradient = Image.new("RGBA", full.size)
    for y in range(full.height):
        t = y / max(1, full.height - 1)
        shade = (int(225 - 95 * t), int(232 - 80 * t), int(240 - 55 * t), 255)
        gradient.paste(shade, (0, y, full.width, y + 1))
    line = Image.new("RGBA", full.size, (20, 26, 40, 255))
    line.putalpha(outline.point(lambda a: a * 200 // 255))
    gradient.putalpha(full)
    line.alpha_composite(gradient)
    return line


def render_card(font: fe9_font.GameFont, title: str, size=(480, 160)) -> Image.Image:
    """"Chapter N" over the chapter's name, centred, like the retail title cards."""
    head, name = split_title(title)
    image = Image.new("RGBA", size)
    rows = []
    if head:
        rows.append((_card_line(_text_mask(font, head), 34, size[0] - 40), 8))
    rows.append((_card_line(_text_mask(font, name), 44, size[0] - 8), 72 if head else 52))
    for line, top in rows:
        image.alpha_composite(line, ((size[0] - line.width) // 2, top))
    return image


def _replace(template: bytes, image: Image.Image) -> bytes:
    data = lz10.decompress(template) if template[:1] == b"\x10" else template
    return lz10.compress(tpl.replace_image(data, 0, image))


def _template(folder: Path, names: list[str]) -> Optional[bytes]:
    for name in names:
        path = folder / name
        if path.is_file():
            return path.read_bytes()
    return None


def chapter_name_images(files: Path, chapter: int, title: str, template_chapter: int) -> dict[Path, bytes]:
    """The strip and title card files of ``chapter`` (paths under ``files``), drawn from
    ``title`` on copies of ``template_chapter``'s. Missing templates or font give fewer files."""
    font_path = files / FONT_FILE
    if not font_path.is_file():
        return {}
    font = fe9_font.GameFont(font_path.read_bytes())
    result = {}
    strip = _template(files / STRIP_FOLDER, [strip_name(template_chapter), strip_name(1)])
    if strip is not None:
        result[files / STRIP_FOLDER / strip_name(chapter)] = _replace(strip, render_strip(font, title))
    card = _template(files / CARD_FOLDER, [card_name(template_chapter), card_name(1)])
    if card is not None:
        result[files / CARD_FOLDER / card_name(chapter)] = _replace(card, render_card(font, title))
    return result


def preview(data: bytes) -> Image.Image:
    """The first image of a chapter-name file."""
    raw = lz10.decompress(data) if data[:1] == b"\x10" else data
    return tpl.read_tpl_images(io.BytesIO(raw))[0]
