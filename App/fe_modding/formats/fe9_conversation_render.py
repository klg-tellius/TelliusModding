"""Native-coordinate FE9 conversation compositor, independent of Tkinter."""
from __future__ import annotations

import random
import re
import struct
from dataclasses import dataclass, replace
from PIL import Image
from .fe9_conversation import Event, Diagnostic, Portrait
from .fe9_conversation_assets import ConversationAssets

SCENE_SIZE = (608, 448)
FONT_NAMES = ("system", "fe_font", "talk", "bigkana", "alpha")
# #Pnnn: cell nnn (hex) of window/icon.tpl image 0, 24x24 cells in rows of 32, advance 24px,
# centred on the line (draw_markup_text_core 8000e7fc, icon object 80367160).
ICON_SHEET = "window/icon.tpl"
ICON_SIZE = 24
_MARKUP = r"(#[FCSXYRGBAI][0-9A-Fa-f]{2}|#P[0-9A-Fa-f]{3}|#[cDsxyEeOoi]|\n)"
# Code names that only change drawing state (no width): see draw_markup_text_core.
_STATE_CODES = ("#s", "#x", "#y", "#D", "#E", "#e", "#O", "#o", "#i")
# Text effects of draw_markup_text_core: the drop shadow is the glyph in black at half its alpha,
# offset 2px (x sx, y sy); the outline is the glyph in black at its alpha, drawn at radius 1px in
# the 8 directions of the table at 802838e8; then the glyph itself.
SHADOW_OFFSET = 2.0
OUTLINE_DIRECTIONS = ((1, 0), (0, 1), (-1, 0), (0, -1),
                      (0.70710678, 0.70710678), (-0.70710678, 0.70710678),
                      (-0.70710678, -0.70710678), (0.70710678, -0.70710678))


def _scale(run: str, sx: float, sy: float) -> tuple[float, float]:
    """#Sxx / #Xxx / #Yxx set both / horizontal / vertical text scale to xx/64; #s, #x, #y
    and #D reset them (draw_markup_text_core 8000e7fc)."""
    if len(run) == 4 and run[1] in "SXY":
        value = int(run[2:], 16) / 64
        return (value if run[1] in "SX" else sx), (value if run[1] in "SY" else sy)
    return (1.0 if run in ("#s", "#x", "#D") else sx), (1.0 if run in ("#s", "#y", "#D") else sy)


def icon_cell(sheet: Image.Image, index: int) -> Image.Image:
    columns = sheet.width // ICON_SIZE
    x, y = index % columns * ICON_SIZE, index // columns * ICON_SIZE
    if y + ICON_SIZE > sheet.height:
        raise ValueError(f"Icon #{index:03X} is outside {ICON_SHEET}")
    return sheet.crop((x, y, x + ICON_SIZE, y + ICON_SIZE)).convert("RGBA")


@dataclass(frozen=True)
class RenderResult:
    image: Image.Image
    diagnostics: tuple[Diagnostic, ...]


class ConversationRenderer:
    def __init__(self, assets: ConversationAssets):
        self.assets = assets
        self._portraits = {}

    def invalidate(self):
        self._portraits.clear()

    def measure(self, text: str) -> int:
        """Width as measure_text_width (80010b78) computes it, which sizes conversation windows."""
        font = self.assets.font()
        width = maximum = 0
        sx = 1.0
        # measure_text_width skips #y as a 4-byte code, so the two characters after it are not
        # counted; the renderer draws them normally.
        text = re.sub(r"#y..", "#y", text)
        for run in re.split(_MARKUP, text):
            if run == '\n':
                maximum, width = max(maximum, width), 0
                sx = 1.0
            elif run[:1] == '#' and (len(run) == 4 and run[1] in "SXY" or run in _STATE_CODES):
                sx = _scale(run, sx, 1.0)[0]
            elif run[:1] == '#' and len(run) == 4 and run[1] in "RGBAI":
                continue
            elif run.startswith('#P') and len(run)==5:
                width += ICON_SIZE  # measure_text_width adds the icon object's 24px width
            elif run.startswith('#F') and len(run)==4:
                index=int(run[2:],16)
                if index >= len(FONT_NAMES): raise ValueError(f"Unknown font index {index}")
                font=self.assets.font(FONT_NAMES[index])
            elif run.startswith('#C') and len(run)==4 or run == '#c':
                continue
            else:
                width += font.measure(run) * sx
        return round(max(maximum,width))

    @staticmethod
    def _effects(image, layer, xy, shadow, outline, sx, sy):
        """Composite ``layer`` (one run of glyphs) at ``xy`` with the game's shadow and outline."""
        alpha = layer.getchannel("A")
        black = Image.new("RGBA", layer.size, (0, 0, 0, 255))

        def stamp(mask, dx, dy):
            pad = Image.new("RGBA", layer.size)
            pad.paste(black, (0, 0), mask)
            shifted = pad.transform(pad.size, Image.AFFINE, (1, 0, -dx, 0, 1, -dy), Image.BILINEAR)
            image.alpha_composite(shifted, xy)

        if shadow:
            stamp(alpha.point(lambda v: v // 2), SHADOW_OFFSET * sx, SHADOW_OFFSET * sy)
        if outline:
            for dx, dy in OUTLINE_DIRECTIONS:
                stamp(alpha, dx, dy)
        image.alpha_composite(layer, xy)

    def _text(self, image, text, xy, brightness=255, font_name="talk", missing=None,
              shadow=False, outline=False):
        """Draw a textbox's text; ``missing`` collects (font name, character) pairs the font lacks.

        ``shadow``/``outline`` are the textbox descriptor's +0x1E/+0x1F bytes; #E/#e and #O/#o
        switch them inside the text, #D turns both off."""
        x, y = xy
        font = self.assets.font(font_name)
        current = font_name
        default_color = (255,255,255,255)
        color = previous_color = default_color
        sx = sy = 1.0
        italic = 0.0
        effects = (shadow, outline)
        for run in re.split(_MARKUP, text):
            if run == "\n":
                # Each textbox line is queued as its own talk-font primitive, so font, colour,
                # scale and effect changes do not carry over to the next line
                # (dialogue_textbox_draw_lines).
                x, y = xy[0], y+28
                font, current = self.assets.font(font_name), font_name
                color = previous_color = default_color
                sx = sy = 1.0
                italic = 0.0
                shadow, outline = effects
            elif run.startswith("#F") and len(run)==4:
                index=int(run[2:],16)
                if index >= len(FONT_NAMES): raise ValueError(f"Unknown font index {index}")
                current=FONT_NAMES[index]
                font=self.assets.font(current)
            elif run.startswith('#C') and len(run)==4:
                previous_color, color = color, self.assets.text_color(int(run[2:],16))
            elif run == '#c':
                color = previous_color
            elif run[:1] == '#' and len(run) == 4 and run[1] in "RGBA":
                # One colour channel, without saving the previous colour for #c.
                channel = "RGBA".index(run[1])
                color = tuple(int(run[2:], 16) if i == channel else v for i, v in enumerate(color))
            elif run[:1] == '#' and len(run) == 4 and run[1] == 'I':
                italic = int(run[2:], 16) / 16
            elif run[:1] == '#' and (len(run) == 4 and run[1] in "SXY" or run in _STATE_CODES):
                sx, sy = _scale(run, sx, sy)
                if run == '#D':
                    color = self.assets.text_color(1)
                    italic, shadow, outline = 0.0, False, False
                elif run in ('#E', '#e'):
                    shadow = run == '#E'
                elif run in ('#O', '#o'):
                    outline = run == '#O'
                elif run == '#i':
                    italic = 0.0
            elif run.startswith('#P') and len(run)==5:
                # Icons ignore #C and the text effects; only the window brightness modulates them.
                icon = icon_cell(self.assets.textures(ICON_SHEET)[0], int(run[2:],16))
                if brightness < 255:
                    icon = Image.merge("RGBA", [*(band.point(lambda v: v*brightness//255)
                                                  for band in icon.split()[:3]), icon.split()[3]])
                # The icon keeps its size; only its centring follows the vertical scale.
                line_height = font.ascent + font.descent
                image.alpha_composite(icon, (round(x), y + round((line_height * sy - ICON_SIZE) / 2)))
                x += ICON_SIZE
            else:
                if missing is not None:
                    missing.update((current, c) for c in run if not font.has(c))
                ink = tuple(c*brightness//255 for c in color[:3])+(color[3],)
                width = font.measure(run)
                height = font.ascent + font.descent
                # Glyph boxes, bearings and advances scale about the line's top-left corner;
                # scaled glyphs are filtered bilinearly. Italic shears each glyph about the
                # baseline: the top of the ascent moves right by italic * sx pixels.
                lean = abs(italic) * sx * max(font.ascent, font.descent) / max(1, font.ascent)
                pad = int(lean) + 4
                layer = Image.new("RGBA", (width + 2 * pad, height + 2 * pad))
                font.draw(layer, run, (pad, pad), color=ink, shadow=False)
                if sx != 1.0 or sy != 1.0:
                    layer = layer.resize((max(1, round(layer.width * sx)), max(1, round(layer.height * sy))),
                                         Image.BILINEAR)
                origin = (round(x - pad * sx), round(y - pad * sy))
                if italic:
                    baseline = (pad + font.ascent) * sy
                    k = italic * sx / (font.ascent * sy)
                    layer = layer.transform(layer.size, Image.AFFINE, (1, k, -k * baseline, 0, 1, 0),
                                            Image.BILINEAR)
                self._effects(image, layer, origin, shadow, outline, sx, sy)
                x += width * sx

    def _face(self, portrait: Portrait, seat, time_ms, talking, mirrored, brightness):
        # The game draws random blink intervals (30..541 frames) and random
        # mouth holds (1..8 frames). Local seeded RNGs make preview seeking stable;
        # they deliberately do not pretend to reproduce the event VM's global RNG.
        elapsed = max(0,(time_ms-portrait.loaded_ms)*60//1000)
        expression_age=max(0,(time_ms-portrait.expression_ms)*60//1000)
        eye = 0
        if portrait.eye_mode == 3:
            eye = 1 if expression_age < 3 else 2
        elif portrait.eye_mode == 4:
            eye = 1
        elif portrait.eye_mode != 5:
            rng=random.Random(0xFE900+seat)
            cursor=rng.randrange(512)+30
            if portrait.blink_mode==2: cursor=rng.randrange(64)+1
            while cursor+10 <= elapsed:
                cursor += 10 + (rng.randrange(64)+1 if portrait.blink_mode==2 else rng.randrange(512)+30)
            if cursor <= elapsed:
                eye=(1,2,1,0)[min(3,(elapsed-cursor)//3)]
        mouth=2
        if talking:
            rng=random.Random(0xFACE+seat)
            cursor=0; phase=0
            while cursor <= elapsed:
                cursor += rng.randrange(8)+1; phase=(phase+1)%4
            mouth=(0,1,2,1)[phase]
        key=(portrait.fid,portrait.mouth,eye,mouth,mirrored,brightness)
        if key not in self._portraits:
            if len(self._portraits)>512: self._portraits.clear()
            self._portraits[key]=self.assets.face(portrait.fid).compose(
                mouth_variant=portrait.mouth,mouth_frame=mouth,left_eye_frame=eye,
                right_eye_frame=eye,mirrored=mirrored,brightness=brightness)
        return self._portraits[key]

    def render(self, event: Event, *, time_ms: int | None = None,
               backdrop: Image.Image | None = None) -> RenderResult:
        scene=event.state
        time_ms=event.time_ms if time_ms is None else time_ms
        if event.transition_from is not None:
            previous = self.render(replace(event,state=event.transition_from,transition_from=None),
                                   time_ms=time_ms,backdrop=backdrop)
            current = self.render(replace(event,transition_from=None),time_ms=time_ms,backdrop=backdrop)
            fraction = min(1.0,max(0.0,(time_ms-event.time_ms)/max(1,event.transition_duration_ms)))
            return RenderResult(Image.blend(previous.image,current.image,fraction),
                                tuple(dict.fromkeys((*previous.diagnostics,*current.diagnostics))))
        image=backdrop.convert("RGBA").resize(SCENE_SIZE) if backdrop else Image.new("RGBA",SCENE_SIZE,(0,0,0,255))
        diagnostics=[]

        def attempt(call):
            try: return call()
            except (ValueError, OSError, IndexError, KeyError, UnicodeError, struct.error) as error:
                diagnostic=Diagnostic(event.source_offset,str(error))
                if diagnostic not in diagnostics: diagnostics.append(diagnostic)
                return None

        if scene.background:
            attempt(lambda:self.assets.draw_resource(image,scene.background))
        elif backdrop is None:
            diagnostics.append(Diagnostic(event.source_offset,"No scene background supplied; map/event scenery is outside this message"))
        layout=attempt(lambda:self.assets.layout(scene.layout))
        if layout is None: return RenderResult(image,tuple(diagnostics))
        definitions=[p for p in layout.parts if p.kind==2]
        seats=list(attempt(lambda:self.assets.seats(scene.layout)) or ())
        panel_names=set()
        text_positions={}; markers={}
        for i,definition in enumerate(definitions):
            if i>=4: break
            box=scene.boxes[i]
            if not box.visible: continue
            raw=definition.raw
            x,y,marker_x,marker_y,width=struct.unpack_from(">5h",raw,20)
            brightness=255 if scene.speaker_seat in (-1,i) or len(definitions)==1 else 178
            if definition.window:
                w=box.width
                shift=min(96,560-w)
                if i==0:
                    bounds=(24,20,w); x,y=192,36; marker_x,marker_y=w-64,124
                elif i==1:
                    bounds=(584-w,316,w); x,y=632-w,332; marker_x,marker_y=648-w,420
                elif i==2:
                    bounds=(24+shift,160,w); x,y=192+shift,176; marker_x,marker_y=w+shift-64,264
                    if len(seats)>2: seats[2]=(112+shift,271,True)
                else:
                    bounds=(584-w-shift,180,w); x,y=632-w-shift,196; marker_x,marker_y=648-w-shift,284
                    if len(seats)>3: seats[3]=(496-shift,291,False)
                attempt(lambda:self.assets.draw_resource(image,definition.window,bounds=bounds,brightness=brightness))
            if definition.panel: panel_names.add(definition.panel)
            text_positions[i]=(x,y,width,brightness,(raw[0x1e],raw[0x1f]))  # shadow, outline
            markers[i]=(definition.marker,marker_x,marker_y)
        # GX depth comes from facedata +0x1d, independently of seat/load order.
        ordered = sorted(enumerate(scene.portraits), key=lambda pair:
                         self.assets.faces[pair[1].fid].depth if pair[1].fid in self.assets.faces else 0,
                         reverse=True)
        for seat,portrait in ordered:
            if not portrait.fid: continue
            if seat>=len(seats):
                diagnostics.append(Diagnostic(event.source_offset,f"Seat {seat} is unavailable in layout {scene.layout}")); continue
            x,y,mirrored=seats[seat]
            brightness=255 if seat==scene.speaker_seat or scene.speaker_seat<0 else 178
            talking=event.kind=="text" and seat==scene.speaker_seat and scene.mouth_enabled
            face=attempt(lambda:self._face(portrait,seat,time_ms,talking,mirrored,brightness))
            if face is not None:
                layer = Image.new("RGBA", SCENE_SIZE)
                layer.alpha_composite(face,(x-face.width//2,y-face.height))
                if not portrait.fid.startswith("FID_L_"):
                    left, right = (max(0,x-82), min(608,x-82+300)) if mirrored else (0,min(608,x+82))
                    if right > left:
                        image.alpha_composite(layer.crop((left,0,right,448)),(left,0))
                else:
                    image.alpha_composite(layer)
        for name in panel_names:
            attempt(lambda:self.assets.draw_resource(image,name))
        for i,(x,y,width,brightness,effects) in text_positions.items():
            text=scene.boxes[i].text.rstrip("\n")
            measured=attempt(lambda:self.measure(text))
            if measured is not None and measured > width:
                diagnostics.append(Diagnostic(event.source_offset,f"Textbox {i}: line exceeds its {width}px text area ({measured}px)"))
            layer=Image.new("RGBA",SCENE_SIZE)
            missing=set()
            attempt(lambda:self._text(layer,text,(x,y),brightness,missing=missing,
                                      shadow=bool(effects[0]),outline=bool(effects[1])))
            for name in sorted({n for n,_ in missing}):
                chars="".join(sorted({c for n,c in missing if n==name}))
                fallback=attempt(lambda:"☆" if self.assets.font(name).has("☆") else "a space")
                diagnostics.append(Diagnostic(event.source_offset,
                    f"Textbox {i}: font {name} has no glyph for {chars!r}; the game draws {fallback}"))
            # Native glyph queues clip to the textbox's configured region.
            region=layer.crop((x,y,min(SCENE_SIZE[0],x+max(1,width)),min(SCENE_SIZE[1],y+84)))
            image.alpha_composite(region,(x,y))
        seat=scene.speaker_seat
        if scene.nametag and 0<=seat<len(seats) and scene.portraits[seat].fid:
            portrait=scene.portraits[seat]; x,y,_=seats[seat]
            if x>999: x-=1000
            x=min(504,max(104,x))
            name=attempt(lambda:self.assets.display_name(portrait.fid))
            plate=attempt(lambda:self.assets.textures("window/xinfo.tpl")[30])
            if plate is not None: image.alpha_composite(plate,(x-plate.width//2,y-12))
            if name:
                font=attempt(lambda:self.assets.font("system"))
                if font is not None: attempt(lambda:font.draw(image,name,(x-font.measure(name)//2,y-12)))
        if event.wait and scene.box in markers:
            name,x,y=markers[scene.box]
            if name:
                cursor=Image.new("RGBA",SCENE_SIZE)
                attempt(lambda:self.assets.draw_resource(cursor,name,frame=time_ms*60//1000))
                image.alpha_composite(cursor,(x,y))
        alpha = 1.0 if scene.screen_black else 0.0
        if scene.screen_fade is not None:
            kind, start, duration = scene.screen_fade
            fraction = min(1.0,max(0.0,(time_ms-start)/max(1,duration)))
            alpha = 1-fraction if kind == "in" else fraction
        if alpha >= 1.0:
            image = Image.new("RGBA", SCENE_SIZE, (0,0,0,255))
        elif alpha > 0.0:
            image = Image.blend(image,Image.new("RGBA",SCENE_SIZE,(0,0,0,255)),alpha)
        return RenderResult(image,tuple(diagnostics))
