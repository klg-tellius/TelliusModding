"""Draw a Radiant Dawn conversation frame (fe10_conversation.Frame) with the disc's assets.

Engine data used as is: the layout's seats and text box (``window/RectDesc_en.bin``, and
``RectBase_en.bin`` for the base shop layout), the speech
balloon geometry of position-bound boxes (``fe10_rect.balloon``), the portraits (``Face/``), the
background rects (``s/rect.bin``) and the dialogue font (``Fonts/talk.cms``). The window art itself
(``window/talk.tpl`` tiles) is not composed yet: boxes are drawn as plain panels of the right size.
"""
from __future__ import annotations

import io
from pathlib import Path

from PIL import Image, ImageDraw

from . import fe10_message as fm
from . import fe10_rect, lz10, message, tpl
from .fe10_conversation import Frame
from .fe10_faces import FaceLibrary
from .fe9_font import GameFont

SCENE_SIZE = (640, 480)
BOX_HEIGHT = 112          # balloon height used for drawing (3 lines of 28 px plus margins)
PANEL = (16, 20, 44, 215)
NAME_PANEL = (60, 40, 20, 235)


class Fe10ConversationAssets:
    """Everything the renderer reads from an extracted Radiant Dawn disc (loaded lazily)."""

    def __init__(self, files_dir: Path | str, language_prefix: str = "e_"):
        self.files = Path(files_dir)
        self.prefix = language_prefix
        self._layouts = self._backgrounds = self._font = self._names = None
        self._faces = None
        self._textures: dict[tuple[str, int], Image.Image] = {}

    @property
    def faces(self) -> FaceLibrary:
        if self._faces is None:
            self._faces = FaceLibrary(self.files)
        return self._faces

    @property
    def layouts(self) -> dict[str, fe10_rect.Resource]:
        if self._layouts is None:
            self._layouts = {}
            suffix = "_en" if self.prefix else ""
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
            path = self.files / "Fonts" / "talk.cms"
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
    return "".join(out)


def render(frame: Frame, assets: Fe10ConversationAssets) -> Image.Image:
    image = Image.new("RGBA", SCENE_SIZE, (0, 0, 0, 255))
    if frame.background:
        background = assets.background(frame.background)
        if background is not None:
            scale = SCENE_SIZE[0] / background.width
            image.alpha_composite(background.resize((SCENE_SIZE[0], round(background.height * scale))))
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
                font.draw(image, text, (tx, ty), line_height=28)
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
            draw.rounded_rectangle((tx - 48, ty - 18, tx - 48 + width, ty + lines * line_height + 14), 14,
                                   fill=PANEL, outline=(200, 190, 160, 255), width=2)
            speaker_index = box.speaker if box.speaker >= 0 else frame.current
            if 0 <= speaker_index < len(frame.cast):
                _name(draw, image, assets, font, assets.character_name(frame.cast[speaker_index]), tx, ty - 40)
            if font:
                font.draw(image, _last_lines(_plain(box.text), lines), (tx, ty), line_height=line_height)
    return image


def _mirrored(facing: str, seats, position: int) -> bool:
    """Portrait art faces left; ``D`` keeps the seat's own facing (1 = mirrored), ``L``/``R`` force it."""
    if facing == "L":
        return False
    if facing == "R":
        return True
    return bool(seats[position].facing) if 0 <= position < len(seats) else False


def _name(draw, image, assets, font, name: str, x: int, y: int) -> None:
    width = (font.measure(name) if font else 8 * len(name)) + 24
    draw.rounded_rectangle((x - 12, y - 2, x - 12 + width, y + 28), 8, fill=NAME_PANEL)
    if font:
        font.draw(image, name, (x, y), line_height=28)
