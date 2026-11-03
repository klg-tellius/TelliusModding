"""FE7Dragon's battle info window: a parchment box at the bottom middle of the battle screen with
both fighters' hit, damage and critical rate, in animated and in map battles.

Port of the "FE9 Battle Info Display Patch" v2.0 by FE7Dragon (credits: Jade, Vicious Sal,
Donlot, TurtleMan64): https://feuniverse.us/t/fe9-battle-info-display-patch-v-2-0/37457.
The code is the patch's own (``battle_window_data``); the textures are rebuilt from the
player's disc instead of shipped.

How it works:

- **Animated battles.** The battle HUD (``zdbx/battle.dbx`` in ``zdbx.cmp``) already holds a
  hidden ``ParamWin`` picture and six hidden ``Number`` widgets (``NumAtkL/R``, ``NumHitL/R``,
  ``NumCritL/R``) that ``battle_preview_setup_forecast_number_widgets`` fills each exchange. The
  dbx edit shows them inside the box; the forecast hook recomputes damage (Atk minus the other
  side's Def, never below 0), hit and crit from the battle context's actors (+0x299/+0x29B/
  +0x2A3/+0x2A9, the other actor 0x2E0 further) and the 8 register edits feed those values to the
  widgets in Hit / Dmg / Crit order. A side whose Atk is 0 (no weapon) shows 0 hit and crit.
- **Map battles.** The HP-window draw (``map_battle_hp_window_draw``, US 0x8017E8C0) is hooked once per frame for the left
  window: the hook loads ``zdbx/ztex/3sukumi.tpl`` and ``zdbx/ztex/number.tpl`` by path, draws
  the box centred under the HP windows (moved to the top when they sit low) and the six numbers
  with the small digit row, swapping sides when the context's flag (+0xCAC bit 0x20) says so.
- **Where the code lives.** The patch shipped as a GeckoLoader DOL whose loader copied a code
  handler to 0x80001800, the Game Code cave. Here the two hook bodies go into MetroTRK's
  single-step / interrupt handlers instead (US 0x80229040), which only run when a hardware
  debugger is attached: nothing outside TRK branches to or points at them (checked on all three
  builds), and ``__start`` only starts TRK when the boot info reports a debugger.

Textures, rebuilt from the retail files:

- ``ztex/3sukumi.tpl`` (new): ``window/3sukumi.tpl`` (the weapon-triangle window) with its
  parchment scaled into the 164x100 box cell at (0, 0) and "Hit", "Dmg", "Crt" drawn in the
  game's ``Fonts/alpha.gcf``.
- ``ztex/number.tpl``: the retail digits (20x28 cells) plus a second row of the same digits at
  15x21 from y=28, the ``num1`` cell the widgets and the map hook use.

Both go into ``zdbx.cmp`` (the dbx loads ``ztex/...``) and as loose ``files/zdbx/ztex/`` files
(the map hook loads them by path), as the original patch does.
"""

from __future__ import annotations

import io
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from PIL import Image, ImageChops, ImageFilter

from ..formats import dbx, fe9_font, tpl, zdbx
from . import ppc
from .battle_window_data import HOOKS
from .catalog import Edit

US, EU, JP = "GFEE01", "GFEP01", "GFEJ01"
_KEYS = {US: "US", EU: "EU", JP: "JP"}

AUTHOR = "FE7Dragon"
CREDIT = ("Port of the FE9 Battle Info Display Patch v2.0 by FE7Dragon (with thanks to Jade, Vicious Sal, "
          "Donlot and TurtleMan64).")
SOURCE_URL = "https://feuniverse.us/t/fe9-battle-info-display-patch-v-2-0/37457"

_TRK_SIZE = 0x5E0               # the bytes trk_sha1 covers
_FORECAST_OFFSET = 0x570        # the map body (0x568 bytes + branch) comes first


def _word(value: int) -> bytes:
    return value.to_bytes(4, "big")


def trk_code(version: str) -> bytes:
    """What goes into the MetroTRK space: both hook bodies, each ending in its branch back."""
    h = HOOKS[_KEYS[version]]
    base = h["trk"]
    map_end = base + len(h["map"])
    forecast_end = base + _FORECAST_OFFSET + len(h["forecast"])
    code = h["map"] + _word(ppc.b(map_end, h["map_site"] + 4))
    code += _word(ppc.NOP) * ((_FORECAST_OFFSET - len(code)) // 4)
    code += h["forecast"] + _word(ppc.b(forecast_end, h["forecast_site"] + 4))
    assert len(code) == _TRK_SIZE, hex(len(code))
    return code


def edits(version: str) -> tuple[Edit, ...]:
    h = HOOKS[_KEYS[version]]
    base = h["trk"]
    return (Edit(base, b"", trk_code(version), original_sha1=h["trk_sha1"]),
            Edit(h["map_site"], h["map_original"], _word(ppc.b(h["map_site"], base))),
            Edit(h["forecast_site"], h["forecast_original"],
                 _word(ppc.b(h["forecast_site"], base + _FORECAST_OFFSET))),
            *(Edit(a, old, new) for a, old, new in h["widget_edits"]))


VERSIONS = (US, EU, JP)


# -- disc files ---------------------------------------------------------------------------------------
ARCHIVE = "files/zdbx.cmp"
BATTLE_DBX = "zdbx/battle.dbx"
BOX_MEMBER, NUMBER_MEMBER = "ztex/3sukumi.tpl", "ztex/number.tpl"
LOOSE_BOX, LOOSE_NUMBER = "files/zdbx/ztex/3sukumi.tpl", "files/zdbx/ztex/number.tpl"
BOX_SOURCE = "files/window/3sukumi.tpl"
LABEL_FONT = "files/Fonts/alpha.gcf"


@dataclass
class GameFiles:
    """The project's extracted files as a patch's file step sees them. Paths are relative to
    ``extracted/``; ``original`` gives a file as extracted (before any edit), or None."""
    root: Path
    write: Callable[[Path, bytes], None]
    original: Callable[[Path], bytes | None]

    def path(self, relative: str) -> Path:
        return self.root / relative

    def read(self, relative: str) -> bytes | None:
        path = self.path(relative)
        return path.read_bytes() if path.is_file() else None

    def read_original(self, relative: str) -> bytes | None:
        return self.original(self.path(relative))

    def put(self, relative: str, data: bytes) -> None:
        path = self.path(relative)
        if path.is_file() and path.read_bytes() == data:
            return
        path.parent.mkdir(parents=True, exist_ok=True)
        self.write(path, data)

    def delete(self, relative: str) -> None:
        """Remove a file the patch added, and the folders it leaves empty."""
        path = self.path(relative)
        path.unlink(missing_ok=True)
        files = self.path("files")
        for folder in path.parents:
            if folder == files or files not in folder.parents or not folder.is_dir() or any(folder.iterdir()):
                break
            folder.rmdir()


# (class, name): {key: (retail value, patched value)}; None is "no such line".
DBX_EDITS: dict[tuple[str, str], dict[str, tuple[str | None, str]]] = {
    ("Texture", "ParamPlate"): {"fileName": ("ztex/btlwin", "ztex/3sukumi"), "cellSize": ("74,80", "164,100"),
                                "srcPos": ("236,100", "0,0")},
    ("Texture", "num1"): {"cellSize": ("10,20", "15,21")},
    ("Picture", "ParamWin"): {"show": ("0", "1"), "pos": ("283,40", "221,344")},
}
for _row, _y, _retail_y in (("Hit", 360, 64), ("Atk", 384, 44), ("Crit", 408, 88)):    # Atk shows the damage
    for _side, _x, _retail_x in (("L", 264, 300), ("R", 336, 344)):
        DBX_EDITS[("Number", f"Num{_row}{_side}")] = {
            "show": ("0", "1"), "pos": (f"{_retail_x}, {_retail_y}", f"{_x}, {_y}"),
            "rgba": ("255, 255, 255, 168", "255, 255, 255, 255"), "kerning": (None, "-4")}


def edit_battle_dbx(text: str, install: bool) -> str:
    doc = dbx.parse(text)
    for (cls, name), fields in DBX_EDITS.items():
        for key, (retail, patched) in fields.items():
            block = doc.find(cls, name)
            field = next((f for f in block.fields if f.key == key), None)
            want = patched if install else retail
            if want is None:
                if field is not None:
                    doc.remove_field(field)
            elif field is None:
                doc.add_field(block, key, want)
            elif field.value != want:
                doc.set_value(field, want)
    return doc.text


def _label(font: fe9_font.GameFont, text: str, scale: float) -> Image.Image:
    sheet = Image.new("RGBA", (font.measure(text) + 8, font.ascent + font.descent + 8), (0, 0, 0, 0))
    font.draw(sheet, text, (4, 4), shadow=False)
    cover = sheet.getchannel("A")
    cover = cover.crop(cover.getbbox())
    cover = cover.resize((max(1, round(cover.width * scale)), max(1, round(cover.height * scale))), Image.LANCZOS)
    pad = Image.new("L", (cover.width + 4, cover.height + 4), 0)
    pad.paste(cover, (2, 2))
    out = Image.new("RGBA", pad.size, (0, 0, 0, 0))
    out.paste((52, 44, 28, 255), (0, 0), pad.filter(ImageFilter.MaxFilter(3)))    # dark outline
    out.paste((236, 232, 208, 255), (0, 0), pad)
    return out


BOX_SIZE = (164, 100)
_LABELS = (("Hit", 27), ("Dmg", 51), ("Crt", 74))     # centre lines, matching the number rows
_LABEL_X, _CAP_HEIGHT = 82, 12


def build_box(window_tpl: bytes, font_data: bytes) -> bytes:
    """``window/3sukumi.tpl`` with image 0 replaced by the info window."""
    font = fe9_font.GameFont(font_data)
    parchment = tpl.read_tpl_images(io.BytesIO(window_tpl))[0].convert("RGBA")
    canvas = Image.new("RGBA", parchment.size, (0, 0, 0, 0))
    # premultiplied, so the torn edges' transparent texels do not bleed black into the parchment
    canvas.paste(parchment.convert("RGBa").resize(BOX_SIZE, Image.BICUBIC).convert("RGBA"), (0, 0))
    cap = font.mask(font.glyph("H"))
    scale = _CAP_HEIGHT / cap.crop(cap.getbbox()).height
    for text, centre in _LABELS:
        label = _label(font, text, scale)
        canvas.alpha_composite(label, (_LABEL_X - label.width // 2, centre - label.height // 2))
    return tpl.replace_image(window_tpl, 0, canvas)


SMALL_DIGIT = (15, 21)
_SMALL_ROW_Y = 28
_SMALL_TINT = (255, 247, 214)


def build_numbers(number_tpl: bytes) -> bytes:
    """The battle digits with the small row added below them (200x50)."""
    digits = tpl.read_tpl_images(io.BytesIO(number_tpl))[0].convert("RGBA")
    cell_w, cell_h = digits.width // 10, 28
    sheet = Image.new("RGBA", (digits.width, _SMALL_ROW_Y + SMALL_DIGIT[1] + 1), (0, 0, 0, 0))
    sheet.paste(digits.crop((0, 0, digits.width, _SMALL_ROW_Y)), (0, 0))
    tint = Image.new("RGB", SMALL_DIGIT, _SMALL_TINT)
    for d in range(10):
        small = digits.crop((d * cell_w, 0, (d + 1) * cell_w, cell_h)).resize(SMALL_DIGIT, Image.LANCZOS)
        ink = ImageChops.multiply(small.convert("RGB"), tint)          # the cream of FE7Dragon's digits
        sheet.paste(Image.merge("RGBA", (*ink.split(), small.getchannel("A"))), (d * SMALL_DIGIT[0], _SMALL_ROW_Y))
    info = tpl.read_tpl_image_info(io.BytesIO(number_tpl))[0]
    return tpl.build_tpl([(sheet, tpl.FORMAT_CMPR)], wrap=info.wrap_s)


def _is_rebuilt_numbers(data: bytes) -> bool:
    return tpl.read_tpl_image_info(io.BytesIO(data))[0].height > 32


def _members(files: GameFiles) -> dict[str, bytes] | None:
    data = files.read(ARCHIVE)
    return dict(zdbx.read_zdbx_files(data)) if data is not None else None


def install_files(files: GameFiles) -> list[str]:
    """Add the box texture, the small digits and the dbx edits; returns what changed."""
    members = _members(files)
    if members is None:
        raise FileNotFoundError(f"{ARCHIVE} is missing.")
    window, font = files.read(BOX_SOURCE), files.read(LABEL_FONT)
    if window is None or font is None:
        raise FileNotFoundError(f"{BOX_SOURCE if window is None else LABEL_FONT} is missing.")
    changed = []
    text = members[BATTLE_DBX].decode("shift_jis")
    edited = edit_battle_dbx(text, True)
    if edited != text:
        members[BATTLE_DBX] = zdbx.encode_dbx(edited)
        changed.append(BATTLE_DBX)
    numbers = members[NUMBER_MEMBER]
    if not _is_rebuilt_numbers(numbers):
        members[NUMBER_MEMBER] = numbers = build_numbers(numbers)
        changed.append(NUMBER_MEMBER)
    box = members.get(BOX_MEMBER)
    if box is None:
        members[BOX_MEMBER] = box = build_box(window, font)
        changed.append(BOX_MEMBER)
    if changed:
        files.put(ARCHIVE, zdbx.build_zdbx_archive(list(members.items())))
    files.put(LOOSE_BOX, box)
    files.put(LOOSE_NUMBER, numbers)
    return changed


def remove_files(files: GameFiles) -> list[str]:
    """Undo :func:`install_files`: retail dbx values and digits, no box texture or loose copies."""
    files.delete(LOOSE_BOX)
    files.delete(LOOSE_NUMBER)
    members = _members(files)
    if members is None:
        return []
    changed = []
    text = members[BATTLE_DBX].decode("shift_jis")
    edited = edit_battle_dbx(text, False)
    if edited != text:
        members[BATTLE_DBX] = zdbx.encode_dbx(edited)
        changed.append(BATTLE_DBX)
    if _is_rebuilt_numbers(members[NUMBER_MEMBER]):
        original = files.read_original(ARCHIVE)
        retail = dict(zdbx.read_zdbx_files(original)).get(NUMBER_MEMBER) if original else None
        if retail is None or _is_rebuilt_numbers(retail):
            digits = tpl.read_tpl_images(io.BytesIO(members[NUMBER_MEMBER]))[0].convert("RGBA")
            retail = tpl.build_tpl([(digits.crop((0, 0, digits.width, 32)), tpl.FORMAT_CMPR)], wrap=tpl.WRAP_CLAMP)
        members[NUMBER_MEMBER] = retail
        changed.append(NUMBER_MEMBER)
    if members.pop(BOX_MEMBER, None) is not None:
        changed.append(BOX_MEMBER)
    if changed:
        files.put(ARCHIVE, zdbx.build_zdbx_archive(list(members.items())))
    return changed


def files_installed(files: GameFiles) -> bool:
    members = _members(files)
    return bool(members) and BOX_MEMBER in members and files.path(LOOSE_BOX).is_file() \
        and edit_battle_dbx(members[BATTLE_DBX].decode("shift_jis"), True) == members[BATTLE_DBX].decode("shift_jis")
