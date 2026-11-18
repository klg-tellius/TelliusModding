"""Draw a Radiant Dawn conversation frame (fe10_conversation.Frame) with the disc's assets.

Engine data used as is: the layout's seats and text box (``window/RectDesc_en.bin``, and
``RectBase_en.bin`` for the base shop layout), the speech
balloon geometry of position-bound boxes (``fe10_rect.balloon``), the portraits (``Face/``), the
background rects (``s/rect.bin``) and the dialogue font (``Fonts/talk.cms``). The full-width text
window is the textbox's own window resource (``RID_TW``: ``window/talk.tpl`` image 0 at y 296, its
middle 608 pixels in 4:3, all 796 from x -94 in 16:9). Frames are drawn at :data:`FRAME_SIZE` and
shown stretched to :data:`SCENE_SIZE` or :data:`WIDE_SIZE`; the nameplate is the scroll (image 1), placed by
eye. Speech balloons are still drawn as plain panels of the right size.
"""
from __future__ import annotations

import io
import re
from pathlib import Path
from typing import Optional

from PIL import Image, ImageDraw

from . import fe10_message as fm
from . import fe10_rect, lz10, message, tpl
from .fe10_conversation import Frame
from .fe10_faces import FaceLibrary
from .fe9_font import GameFont
from ..game_files import as_path

#: The frame the game draws conversations in: 608x456 (balloons run from x 16 to 592,
#: ``FUN_8022a174``; the text window, y 296-448, is centred on x 304), stretched by the console to the
#: screen. Checked against an in-game capture of II:2 (2026-11-18): the window then ends 8 pixels above
#: the bottom of a 480-line picture.
FRAME_SIZE = (608, 456)
SCENE_SIZE = (640, 480)   # how a 4:3 console shows the frame
WIDE_SIZE = (854, 480)    # how a 16:9 console shows the frame
BOX_HEIGHT = 112          # balloon height used for drawing (3 lines of 28 px plus margins)
PANEL = (16, 20, 44, 215)
NAME_PANEL = (60, 40, 20, 235)
WINDOW_ART = "window/talk.tpl"
NAMEPLATE_IMAGE = 1       # the parchment scroll behind the speaker's name
CURSOR_IMAGE = 2          # the page cursor's 15 frames, 40x56 each (RID_PAGECUR)
FENCE_ART = "window/fence.tpl"   # the carved panel beside a 4:3 conversation on a 16:9 screen
#: The nameplate's place in the full-width window, from the text origin (in-game capture of II:2).
NAMEPLATE_OFFSET = (30, -32)
#: The nameplate's lettering: the alpha font in a grey brown (sampled from the same capture).
NAME_FONT = "alpha"
NAME_COLOR = (64, 58, 46, 255)
_TEXT_PALETTE = {b"RFEE01": 0x80383158, b"RFEP01": 0x80384CD8, b"RFEJ01": 0x8036D0D0}
_COLOR_CODE = re.compile(r"#C([0-9A-Fa-f]{2})|#c")


class Fe10ConversationAssets:
    """Everything the renderer reads from an extracted Radiant Dawn disc (loaded lazily)."""

    def __init__(self, files_root: Path | str, language_prefix: Optional[str] = None, wide: bool = False):
        """``wide``: the 16:9 assets (``Face/wide``, ``_w`` fonts and layouts). They use the same
        640x480 coordinates, with art squeezed horizontally that the console stretches back; show
        the rendered frame stretched to 854x480 (:data:`WIDE_SIZE`). The Japanese disc has no
        widescreen assets, so ``wide`` is dropped there. ``language_prefix`` defaults to ``e_``
        where the disc has English text, else none."""
        self.files = as_path(files_root)
        if language_prefix is None:
            language_prefix = "e_" if (self.files / "Mess" / "e_common.m").is_file() else ""
        self.prefix = language_prefix
        self.wide = wide and (self.files / "Fonts" / "talk_w.cms").is_file()
        self._layouts = self._backgrounds = self._font = self._names = None
        self._faces = None
        self._colors: dict[int, tuple[int, int, int, int]] = {}
        self._textures: dict[tuple[str, int], Image.Image] = {}
        self._narrow: Optional["Fe10ConversationAssets"] = None

    @property
    def name_font(self) -> GameFont | None:
        """The nameplate's font (``Fonts/alpha.cms``), or None."""
        if not hasattr(self, "_name_font"):
            path = self.files / "Fonts" / (f"{NAME_FONT}_w.cms" if self.wide else f"{NAME_FONT}.cms")
            self._name_font = GameFont(lz10.decompress(path.read_bytes())) if path.is_file() else None
        return self._name_font

    @property
    def narrow(self) -> "Fe10ConversationAssets":
        """The 4:3 assets of the same disc (a full-screen conversation is drawn 4:3 on a 16:9 screen)."""
        if not self.wide:
            return self
        if self._narrow is None:
            self._narrow = Fe10ConversationAssets(self.files, self.prefix, wide=False)
        return self._narrow

    @property
    def faces(self) -> FaceLibrary:
        if self._faces is None:
            self._faces = FaceLibrary(self.files, wide=self.wide)
        return self._faces

    @property
    def layouts(self) -> dict[str, fe10_rect.Resource]:
        if self._layouts is None:
            self._layouts = {}
            suffix = ("_en" if self.prefix else "") + ("_w" if self.wide else "")
            # RectDesc holds the conversation layouts; RectBase the base screens (BASE_SHOP_MESS).
            for name in (f"window/RectBase{suffix}.bin", f"window/RectDesc{suffix}.bin"):
                path = self.files / name
                if path.is_file():
                    self._layouts.update(fe10_rect.read_rect_path(path))
        return self._layouts

    @property
    def backgrounds(self) -> dict[str, fe10_rect.Resource]:
        if self._backgrounds is None:
            path = self.files / "s" / "rect.bin"
            self._backgrounds = fe10_rect.read_rect_path(path) if path.is_file() else {}
        return self._backgrounds

    @property
    def font(self) -> GameFont | None:
        if self._font is None:
            path = self.files / "Fonts" / ("talk_w.cms" if self.wide else "talk.cms")
            if path.is_file():
                self._font = GameFont(lz10.decompress(path.read_bytes()))
        return self._font

    def character_name(self, cast_name: str) -> str:
        """The shown name of a cast entry (MPID text from ``<prefix>common.m``), or the entry."""
        if self._names is None:
            self._names = {}
            path = self.files / "Mess" / f"{self.prefix}common.m"
            if path.is_file():
                for msg in message.read_messages_path(path):
                    if msg.speaker.startswith("MPID_"):
                        self._names[msg.speaker] = fm.plain_text(msg.text)
        found = self.faces.lookup(cast_name)
        if found is not None and found[0].name_id in self._names:
            return self._names[found[0].name_id]
        return cast_name.removeprefix("L_")

    def texture(self, rel: str, index: int) -> Image.Image | None:
        key = (rel, index)
        if key not in self._textures:
            path = self.files / rel
            image = None
            if path.is_file():
                data = path.read_bytes()
                if data[:1] == b"\x10":
                    data = lz10.decompress(data)
                images = tpl.read_tpl_images(io.BytesIO(data))
                image = images[index].convert("RGBA") if index < len(images) else None
            self._textures[key] = image
        return self._textures[key]

    def background(self, name: str) -> Image.Image | None:
        resource = self.backgrounds.get("RID_" + name)
        if resource is None:
            return None
        canvas = None
        for quad in resource.quads():
            texture = self.texture(quad.file, quad.texture)
            if texture is None:
                continue
            x0, y0, x1, y1 = quad.src
            part = texture.crop((min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1))) if x1 or y1 else texture
            if canvas is None:
                canvas = Image.new("RGBA", part.size, (0, 0, 0, 255))
            canvas.alpha_composite(part.resize(canvas.size) if part.size != canvas.size else part)
            if resource.mode != 0:   # flip-book / cross-fade: the first layer is enough for a still
                break
        return canvas

    def text_color(self, index: int) -> tuple[int, int, int, int]:
        """The 40-entry RGBA palette the glyph renderer uses for ``#Cxx`` markup (main.dol data;
        the three retail builds hold the same colours)."""
        if not 0 <= index < 40:
            raise ValueError(f"Text color {index:02X} is outside the palette")
        if index not in self._colors:
            from ..game_code.dol import Dol

            root = self.files.parent
            boot = root / "sys" / "boot.bin"
            from ..games import retail_disc_id
            game_id = boot.read_bytes()[:6] if boot.is_file() else b"RFEE01"
            game_id = retail_disc_id(game_id.decode("ascii", "replace")).encode("ascii", "replace")
            try:
                address = _TEXT_PALETTE[game_id]
            except KeyError:
                raise ValueError(f"No RD text palette for {game_id.decode('ascii', 'replace')}") from None
            dol = Dol.open(root / "sys" / "main.dol")
            self._colors[index] = tuple(dol.read(address + 4 * index, 4))
        return self._colors[index]


def _last_lines(text: str, lines: int) -> str:
    return "\n".join(text.split("\n")[-lines:])


def _plain(display: str) -> str:
    """Box text without inline codes (the notation's <...> tags)."""
    out, depth = [], 0
    for char in display:
        if char == "<":
            depth += 1
        elif char == ">" and depth:
            depth -= 1
        elif not depth:
            out.append(char)
    return _COLOR_CODE.sub("", "".join(out))


def _styled_lines(display: str, assets: Fe10ConversationAssets, keep: int) -> list[list[tuple[str, tuple]]]:
    """Visible text split into colour runs, preserving the colour active before the last lines."""
    plain, depth = [], 0
    for char in display:
        if char == "<":
            depth += 1
        elif char == ">" and depth:
            depth -= 1
        elif not depth:
            plain.append(char)
    text = "".join(plain)
    default = (255, 255, 255, 255)
    color = previous = default
    lines: list[list[tuple[str, tuple]]] = [[]]
    at = 0
    for match in _COLOR_CODE.finditer(text):
        chunk = text[at:match.start()]
        for i, piece in enumerate(chunk.split("\n")):
            if i:
                lines.append([])
            if piece:
                lines[-1].append((piece, color))
        if match.group(1) is not None:
            previous, color = color, assets.text_color(int(match.group(1), 16))
        else:
            color, previous = previous, color
        at = match.end()
    for i, piece in enumerate(text[at:].split("\n")):
        if i:
            lines.append([])
        if piece:
            lines[-1].append((piece, color))
    return lines[-keep:]


def _draw_styled(font: GameFont, image: Image.Image, display: str, xy: tuple[int, int],
                 assets: Fe10ConversationAssets, lines: int, line_height: int) -> None:
    for row, runs in enumerate(_styled_lines(display, assets, lines)):
        x = xy[0]
        for text, color in runs:
            font.draw(image, text, (x, xy[1] + row * line_height), color=color, line_height=line_height)
            x += font.measure(text)


def render(frame: Frame, assets: Fe10ConversationAssets) -> Image.Image:
    image = Image.new("RGBA", FRAME_SIZE, (0, 0, 0, 255))
    if frame.background:
        background = assets.background(frame.background)
        if background is not None:
            scale = FRAME_SIZE[0] / background.width
            image.alpha_composite(background.resize((FRAME_SIZE[0], round(background.height * scale))))
    layout = assets.layouts.get("RID_" + frame.layout)
    textboxes = layout.textboxes() if layout else []
    balloons = any(box.position >= 0 for box in textboxes)
    draw = ImageDraw.Draw(image, "RGBA")
    font = assets.font
    by_position = {actor.position: (index, actor) for index, actor in enumerate(frame.actors)
                   if actor.visible and actor.position >= 0}

    seats = layout.seats() if layout else []
    if balloons:
        for box in frame.boxes:
            if box.position < 0 or box.position > 7:
                continue
            actor = by_position.get(box.position)
            text = _last_lines(_plain(box.text), 3)
            width = font.measure(text) if font else 8 * max((len(line) for line in text.split("\n")), default=0)
            portrait = assets.faces.compose(actor[1].name, eyes=actor[1].eyes) if actor else None
            geometry = fe10_rect.balloon(box.position, width, no_portrait=portrait is None)
            bx, by = geometry["box"]
            draw.rounded_rectangle((bx, by, bx + geometry["width"], by + BOX_HEIGHT), 14, fill=PANEL,
                                   outline=(200, 190, 160, 255), width=2)
            if portrait is not None:
                ax, ay = geometry["anchor"]
                if _mirrored(actor[1].facing, seats, box.position):
                    portrait = portrait.transpose(Image.FLIP_LEFT_RIGHT)
                image.alpha_composite(portrait, (ax - portrait.width // 2, max(0, ay - portrait.height)))
            speaker = frame.cast[box.speaker] if 0 <= box.speaker < len(frame.cast) else ""
            tx, ty = geometry["text"]
            if speaker:
                _name(draw, image, assets, font, assets.character_name(speaker), tx, by - 14)
            if font:
                _draw_styled(font, image, box.text, (tx, ty), assets, 3, 28)
    else:
        for actor in frame.actors:
            if not actor.visible or not 0 <= actor.position < len(seats):
                continue
            seat = seats[actor.position]
            portrait = assets.faces.compose(actor.name, eyes=actor.eyes)
            if portrait is None:
                continue
            if _mirrored(actor.facing, seats, actor.position):
                portrait = portrait.transpose(Image.FLIP_LEFT_RIGHT)
            image.alpha_composite(portrait, (seat.x - portrait.width // 2, max(0, seat.y - portrait.height)))
        boxes = {b.position: b for b in frame.boxes if b.text}
        box = boxes.get(frame.position) or next(iter(boxes.values()), None)
        textbox = next((t for t in textboxes), None)
        if box is not None:
            tx, ty = (textbox.text_x, textbox.text_y) if textbox else (96, 322)
            width = textbox.width if textbox else 576
            lines = textbox.lines if textbox else 3
            line_height = textbox.line_height if textbox else 28
            if not _draw_resource(image, assets, textbox.window if textbox else "RID_TW"):
                draw.rounded_rectangle((tx - 48, ty - 18, tx - 48 + width, ty + lines * line_height + 14), 14,
                                       fill=PANEL, outline=(200, 190, 160, 255), width=2)
            speaker_index = box.speaker if box.speaker >= 0 else frame.current
            if 0 <= speaker_index < len(frame.cast):
                name = assets.character_name(frame.cast[speaker_index])
                plate = assets.texture(WINDOW_ART, NAMEPLATE_IMAGE)
                if plate is not None:
                    _plate(image, assets.name_font or font, name, plate,
                           tx + NAMEPLATE_OFFSET[0], ty + NAMEPLATE_OFFSET[1])
                else:
                    _name(draw, image, assets, font, name, tx, ty - 40)
            if font:
                _draw_styled(font, image, box.text, (tx, ty), assets, lines, line_height)
            if textbox and frame.kind == "wait":
                cursor = assets.texture(WINDOW_ART, CURSOR_IMAGE)
                if cursor is not None:
                    image.alpha_composite(cursor.crop((0, 0, 40, 56)), (textbox.cursor_x, textbox.cursor_y))
    return image


def present(frame: Frame, assets: Fe10ConversationAssets) -> Image.Image:
    """``frame`` as the console shows it: the 608x456 frame stretched to 640x480, or to 854x480 on a
    16:9 screen. There a conversation with a background is the 4:3 picture between two carved panels
    (``window/fence.tpl``, mirrored on the right), drawn with the 4:3 assets."""
    if not assets.wide:
        return render(frame, assets).resize(SCENE_SIZE, Image.LANCZOS)
    if not frame.background:
        return render(frame, assets).resize(WIDE_SIZE, Image.LANCZOS)
    scene = render(frame, assets.narrow).resize(SCENE_SIZE, Image.LANCZOS)
    out = Image.new("RGBA", WIDE_SIZE, (0, 0, 0, 255))
    side = (WIDE_SIZE[0] - SCENE_SIZE[0]) // 2
    out.alpha_composite(scene, (side, 0))
    fence = assets.texture(FENCE_ART, 0)
    if fence is not None:
        fence = fence.resize((side, WIDE_SIZE[1]), Image.LANCZOS)
        out.alpha_composite(fence, (0, 0))
        out.alpha_composite(fence.transpose(Image.FLIP_LEFT_RIGHT), (WIDE_SIZE[0] - side, 0))
    return out


def _mirrored(facing: str, seats, position: int) -> bool:
    """Portrait art faces left; ``D`` keeps the seat's own facing (1 = mirrored), ``L``/``R`` force it."""
    if facing == "L":
        return False
    if facing == "R":
        return True
    return bool(seats[position].facing) if 0 <= position < len(seats) else False


def _draw_resource(image: Image.Image, assets: Fe10ConversationAssets, rid: str) -> bool:
    """Draw a layout's still image resource (the text window ``RID_TW``) where its quads say; False when
    the layouts have no such resource or its art is missing. A quad whose second corner repeats the first
    is drawn at the source rectangle's own size."""
    resource = assets.layouts.get(rid)
    if resource is None:
        return False
    drawn = False
    for quad in resource.quads():
        texture = assets.texture(quad.file, quad.texture)
        if texture is None:
            continue
        sx0, sy0, sx1, sy1 = quad.src
        part = texture.crop((sx0, sy0, sx1, sy1)) if sx1 > sx0 and sy1 > sy0 else texture
        x0, y0, x1, y1 = quad.dst
        size = (x1 - x0, y1 - y0) if (x1, y1) != (x0, y0) else part.size
        if size[0] <= 0 or size[1] <= 0:
            continue
        if size != part.size:
            part = part.resize(size)
        if quad.alpha < 255:
            part = part.copy()
            part.putalpha(part.getchannel("A").point(lambda a: a * quad.alpha // 255))
        layer = Image.new("RGBA", image.size, (0, 0, 0, 0))
        layer.paste(part, (x0, y0))  # dst may start left of the frame (the 16:9 window at x -94)
        image.alpha_composite(layer)
        drawn = True
    return drawn


def _name(draw, image, assets, font, name: str, x: int, y: int) -> None:
    width = (font.measure(name) if font else 8 * len(name)) + 24
    draw.rounded_rectangle((x - 12, y - 2, x - 12 + width, y + 28), 8, fill=NAME_PANEL)
    if font:
        font.draw(image, name, (x, y), line_height=28)


def _plate(image, font, name: str, plate: Image.Image, x: int, y: int) -> None:
    """The scroll nameplate (talk.tpl image 1) at ``(x, y)``, widened for a long name, the name centred."""
    width = (font.measure(name) if font else 8 * len(name)) + 32
    if width > plate.width:
        plate = plate.resize((width, plate.height))
    image.alpha_composite(plate, (x, y))
    if font:
        font.draw(image, name, (x + (plate.width - font.measure(name)) // 2, y + (plate.height - 28) // 2 + 1),
                  color=NAME_COLOR, line_height=28, shadow=False)
