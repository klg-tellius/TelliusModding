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


# -- Radiant Dawn ------------------------------------------------------------------------------
#: Radiant Dawn's title cards: ``window/title/<prefix>ch<id>.cms`` (``ch0102.cms`` Japanese,
#: ``e_ch0102.cms`` English), one 480x160 RGB5A3 image each: two centred lines of green-grey serif
#: text with a dark drop shadow (retail ink: lines 29-58 and 101-130, colour about 112,168,132).
#: The retail lettering is a serif no game font carries (bigkana has no Latin letters), so new cards
#: use the dialogue font, or a TrueType/OpenType file the user picks.
FE10_CARD_FOLDER = "window/title"
FE10_FONT_FILE = "Fonts/talk.cms"
FE10_CARD_INK = (112, 168, 132, 255)
FE10_CARD_LINES = ((29, 30), (101, 30))  # (top, ink height) of each line


def fe10_card_name(chapter_id: str, prefix: str = "e_") -> str:
    return f"{prefix}ch{chapter_id}.cms"


def split_fe10_title(title: str) -> tuple[str, str]:
    """``"I:1-Maiden of Miracles"`` -> (``"Ch 1"``, ``"Maiden of Miracles"``); ``"II:Prologue-On
    Drifting Clouds"`` -> (``"Prologue"``, ...); a trailing ``(5)`` part number is dropped, like the
    retail cards. A title without the ``part:chapter-name`` shape is the second line alone."""
    match = re.fullmatch(r"\s*[IVX]+\s*:\s*([^-]+?)\s*-\s*(.+?)\s*(?:\(\d+\))?\s*", title)
    if not match:
        return "", title.strip()
    head, name = match.groups()
    return (f"Ch {head}" if head.isdigit() else head), name


def _truetype_mask(path, text: str) -> Image.Image:
    from PIL import ImageDraw, ImageFont
    face = ImageFont.truetype(str(path), 64)
    left, top, right, bottom = face.getbbox(text)
    canvas = Image.new("L", (right - left + 8, bottom - top + 8))
    ImageDraw.Draw(canvas).text((4 - left, 4 - top), text, font=face, fill=255)
    box = canvas.getbbox()
    return canvas.crop(box) if box else Image.new("L", (1, 1))


def render_fe10_card(font, title: str, size=(480, 160)) -> Image.Image:
    """The card for ``title``; ``font`` is a game font or the path of a TrueType/OpenType file."""
    head, name = split_fe10_title(title)
    image = Image.new("RGBA", size)
    lines = [(head, FE10_CARD_LINES[0]), (name, FE10_CARD_LINES[1])] if head else [(name, (65, 30))]
    for text, (top, height) in lines:
        mask = _text_mask(font, text) if isinstance(font, fe9_font.GameFont) else _truetype_mask(font, text)
        width = min(round(mask.width * height / max(1, mask.height)), size[0] - 16)
        mask = mask.resize((max(1, width), height), Image.LANCZOS)
        left = (size[0] - width) // 2
        shadow = Image.new("RGBA", mask.size, (0, 0, 0, 255))
        shadow.putalpha(mask.point(lambda a: a * 3 // 4))
        image.alpha_composite(shadow, (left + 2, top + 2))
        ink = Image.new("RGBA", mask.size, FE10_CARD_INK)
        ink.putalpha(mask)
        image.alpha_composite(ink, (left, top))
    return image


def fe10_title_card(files: Path, chapter_id: str, title: str, prefix: str = "e_",
                    template_id: str = "0101", truetype=None) -> Optional[tuple[Path, bytes]]:
    """(path, file bytes) of chapter ``chapter_id``'s title card drawn from ``title`` on a copy of
    its own card (else ``template_id``'s), or None without a template or the font. ``truetype``
    (a font file path) replaces the game's dialogue font."""
    folder = files / FE10_CARD_FOLDER
    font_path = files / FE10_FONT_FILE
    template = _template(folder, [fe10_card_name(chapter_id, prefix), fe10_card_name(template_id, prefix)])
    if template is None or (truetype is None and not font_path.is_file()):
        return None
    font = truetype if truetype is not None else fe9_font.GameFont(lz10.decompress(font_path.read_bytes()))
    return folder / fe10_card_name(chapter_id, prefix), _replace(template, render_fe10_card(font, title))
