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
        font = self.assets.font()
        width = maximum = 0
        for run in re.split(r"(#[FC][0-9A-Fa-f]{2}|#[cD]|\n)", text):
            if run == '\n':
                maximum, width = max(maximum, width), 0
            elif run.startswith('#F') and len(run)==4:
                index=int(run[2:],16)
                if index >= len(FONT_NAMES): raise ValueError(f"Unknown font index {index}")
                font=self.assets.font(FONT_NAMES[index])
            elif run.startswith('#C') and len(run)==4 or run in ('#c','#D'):
                continue
            else:
                width += font.measure(run)
        return max(maximum,width)

    def _text(self, image, text, xy, brightness=255, font_name="talk", missing=None):
        """Draw a textbox's text; ``missing`` collects (font name, character) pairs the font lacks."""
        x, y = xy
        font = self.assets.font(font_name)
        current = font_name
        color = previous_color = (255,255,255,255)
        for run in re.split(r"(#[FC][0-9A-Fa-f]{2}|#[cD]|\n)", text):
            if run == "\n":
                # Each textbox line is queued as its own talk-font primitive, so font and colour
                # changes do not carry over to the next line (dialogue_textbox_draw_lines).
                x, y = xy[0], y+28
                font, current = self.assets.font(font_name), font_name
                color = previous_color = (255,255,255,255)
            elif run.startswith("#F") and len(run)==4:
                index=int(run[2:],16)
                if index >= len(FONT_NAMES): raise ValueError(f"Unknown font index {index}")
                current=FONT_NAMES[index]
                font=self.assets.font(current)
            elif run.startswith('#C') and len(run)==4:
                previous_color, color = color, self.assets.text_color(int(run[2:],16))
            elif run == '#c':
                color = previous_color
            elif run == '#D':
                color = (255,255,255,255)
            else:
                if missing is not None:
                    missing.update((current, c) for c in run if not font.has(c))
                ink = tuple(c*brightness//255 for c in color[:3])+(color[3],)
                font.draw(image,run,(x,y),color=ink)
                x += font.measure(run)

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
            text_positions[i]=(x,y,width,brightness)
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
        for i,(x,y,width,brightness) in text_positions.items():
            text=scene.boxes[i].text.rstrip("\n")
            measured=attempt(lambda:self.measure(text))
            if measured is not None and measured > width:
                diagnostics.append(Diagnostic(event.source_offset,f"Textbox {i}: line exceeds its {width}px text area ({measured}px)"))
            layer=Image.new("RGBA",SCENE_SIZE)
            missing=set()
            attempt(lambda:self._text(layer,text,(x,y),brightness,missing=missing))
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
        if scene.screen_black:
            image = Image.new("RGBA", SCENE_SIZE, (0,0,0,255))
        elif event.kind in ("screen_fade_in", "screen_fade_out"):
            fraction = min(1.0,max(0.0,(time_ms-event.time_ms)/max(1,event.transition_duration_ms)))
            alpha = 1-fraction if event.kind == "screen_fade_in" else fraction
            image = Image.blend(image,Image.new("RGBA",SCENE_SIZE,(0,0,0,255)),alpha)
        return RenderResult(image,tuple(diagnostics))
