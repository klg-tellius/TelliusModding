"""Structured, lossless step view of one FE9 message for the scene editor.

A message's text is split into *steps* (set layout, load a portrait, speak a
line, ...) on top of ``fe9_conversation.tokenize``. Each decompiled step keeps
its exact source slice in ``raw``; ``compile_steps`` emits that slice unchanged
until the step is edited, after which its canonical form is regenerated. Hence
``compile_steps(decompile(text)) == text`` for any input, and every vanilla
step's canonical form equals its source (see test_fe9_message_scene.py).

Texts are the cp437 strings ``message.read_messages`` produces (one character
per byte). Fields shown to the user hold the Shift-JIS decoding of those
bytes, which is what the game's font and ``$R``/``$B`` tags use.

Command semantics: research/CONVERSATION_RENDERING.md and
research/CHAPTER_DATA_NOTES.md §5.4.
"""
from __future__ import annotations

import re
from bisect import bisect_right
from dataclasses import dataclass, field

from .fe9_conversation import Token, tokenize


def to_display(raw: str) -> str:
    """cp437 source string -> readable Shift-JIS text."""
    return raw.encode("cp437").decode("shift_jis", errors="replace")


def to_raw(display: str) -> str:
    """Readable text -> cp437 source string (raises UnicodeEncodeError)."""
    return display.encode("shift_jis").decode("cp437")


@dataclass(frozen=True)
class FieldSpec:
    name: str
    label: str
    # seat, seat_opt, box, fid, layout, background, int, choice, text, bool, line_target
    type: str
    choices: tuple[tuple[str, str], ...] = ()


@dataclass(frozen=True)
class StepKind:
    kind: str
    label: str
    group: str
    description: str
    fields: tuple[FieldSpec, ...] = ()
    confidence: str = "Confirmed"


_SEAT_OPT = FieldSpec("seat", "Seat", "seat_opt")
_EYES = (("c", "Close eyes ($Fc)"), ("h", "Half-open eyes ($Fh)"),
         ("o", "Hold eyes open ($Fo)"), ("d", "Normal eyes and blinking ($Fd)"))
_CONTROLS = (("C", "$C…|"),)
_SKIP = (("SD", "Disable skipping ($SD)"), ("SE", "Enable skipping ($SE)"),
         ("DC", "Disable skipping ($DC, unused alias)"))
_RELEASE = (("UB", "$UB"), ("Ub", "$Ub (identical)"))
_TYPING_SOUNDS = (("0", "Silent ($O0)"), ("1", "Dialogue ($O1)"), ("2", "Ancient language ($O2)"),
                  ("3", "Narration ($O3)"), ("4", "Tutorial ($O4)"))

# English names for the $R layouts (window/rectdesc.bin descriptors with
# textbox parts), most used first: layout pickers list them in this order.
# Vanilla US use counts in the comments; the unused ones differ from a used
# sibling only by the "draw background" flag.
LAYOUT_NAMES: dict[str, str] = {
    "上下会話": "Two-box talk",                         # 896: top/bottom boxes, $c/$s
    "背景会話": "Background scene",                     # 695: lined-up $F seats over a $B backdrop
    "TUT会話": "Tutorial talk",                         # 344: four boxes in tutorial frames
    "GMAP会話": "World map narration",                  # 43
    "背景なし会話": "Scene without background",         # 36: same seats over the map/3D view
    "TUT小会話": "Tutorial info windows",               # 31: small $W windows, no portraits
    "のみ会話": "Text box only",                        # 25: one box, portraits kept off-screen
    "ダイアログ会話": "Dialog popup",                   # 1: the centred tutorial-intro dialog
    "背景上下会話": "Two-box talk over background",     # unused
    "背景のみ会話": "Text box over background",         # unused
    "チュ会話": "Plain text, no window",                # unused
}


def layout_label(name: str) -> str:
    """'English name (ID)' for a known layout, otherwise the ID itself."""
    english = LAYOUT_NAMES.get(name)
    return f"{english} ({name})" if english else name


def layout_from_label(label: str) -> str:
    """Inverse of ``layout_label``; anything else is taken as a raw ID."""
    label = label.strip()
    if label.endswith(")") and " (" in label:
        name = label[label.rindex(" (") + 2:-1]
        if name in LAYOUT_NAMES:
            return name
    return label


STEP_KINDS: dict[str, StepKind] = {k.kind: k for k in (
    StepKind("layout", "Set layout", "Scene",
             "$R: conversation layout (window/seat descriptor), e.g. Two-box talk, "
             "Background scene, World map narration. Clears every textbox.",
             (FieldSpec("layout", "Layout", "layout"),)),
    StepKind("background", "Set background", "Scene",
             "$B: background image descriptor drawn behind the portraits.",
             (FieldSpec("background", "Background", "background"),)),
    StepKind("transition", "Transition duration", "Scene",
             "$=dddd: duration in milliseconds of the next fade; 9999 means the default 267 ms.",
             (FieldSpec("ms", "Milliseconds", "int"),)),
    StepKind("fade_in", "Fade in", "Scene", "$<: start the configured screen transition (fade in)."),
    StepKind("fade_out", "Fade out", "Scene", "$>: fade the screen out to black.", confidence="Plausible"),
    StepKind("load_portrait", "Load portrait", "Portraits",
             "$F<n>$FC<name>|: load a portrait into a seat. L_ names are the large portraits.",
             (_SEAT_OPT, FieldSpec("fid", "Portrait", "fid"))),
    StepKind("remove_portrait", "Remove portrait", "Portraits",
             "$F<n>$FD: remove the seat's portrait (fades out).", (_SEAT_OPT,)),
    StepKind("eyes", "Eyes", "Portraits", "$Fc/$Fh/$Fo/$Fd: eye expression of the seat's portrait.",
             (_SEAT_OPT, FieldSpec("mode", "Eyes", "choice", _EYES))),
    StepKind("blink", "Blink speed", "Portraits", "$Ff/$Fs: quick or normal random blinking.",
             (_SEAT_OPT, FieldSpec("speed", "Blinking", "choice", (("f", "Quick ($Ff)"), ("s", "Normal ($Fs)"))))),
    StepKind("mouth_set", "Mouth set", "Portraits",
             "$FS/$FA: first or second mouth texture set. Not a show/hide command.",
             (_SEAT_OPT, FieldSpec("set", "Mouth", "choice", (("S", "First set ($FS)"), ("A", "Second set ($FA)"))))),
    StepKind("select_seat", "Select seat", "Portraits",
             "$F<n>: make seat n current for following portrait commands and text.",
             (FieldSpec("seat", "Seat", "seat"),)),
    StepKind("show_speaker", "Show speaker in box", "Boxes",
             "$c<n><name>|: open textbox n and load the portrait into seat n.",
             (FieldSpec("box", "Box", "box"), FieldSpec("fid", "Portrait", "fid"))),
    StepKind("select_box", "Select box", "Boxes",
             "$s<n>/$W<n>: select (and clear) textbox n.",
             (FieldSpec("box", "Box", "box"),
              FieldSpec("command", "Command", "choice", (("s", "$s"), ("W", "$W (small windows)"))))),
    StepKind("dismiss_box", "Dismiss box", "Boxes",
             "$d<n>: hide textbox n and remove its portrait.", (FieldSpec("box", "Box", "box"),)),
    StepKind("windows", "Windows", "Boxes", "$W-/$W+/$WD: hide all, re-show all, or hide the current window.",
             (FieldSpec("mode", "Action", "choice", (("-", "Hide all ($W-)"), ("+", "Show all ($W+)"),
                                                      ("D", "Hide current ($WD)"))),)),
    StepKind("nametag", "Toggle nameplate", "Boxes", "$ND: toggle the speaker nameplate."),
    StepKind("line", "Line", "Text",
             "Text shown in the current box. Inline $w<n> pauses 2^n frames, $MC/$MD stop/restart "
             "mouth motion, $N starts a line, #Cxx/#c colours, #Fxx fonts.",
             (FieldSpec("target", "Speaker", "line_target"), FieldSpec("flush", "Clear box first ($P)", "bool"),
              FieldSpec("text", "Text", "text"), FieldSpec("wait", "Wait for input ($K)", "bool"))),
    StepKind("wait", "Wait for input", "Text", "$K: wait for the player to press a button."),
    StepKind("no_wait", "Continue without waiting", "Text",
             "$Y: end the current text tick without waiting for input, e.g. to cut a speaker off. "
             "The next command runs on the following tick."),
    StepKind("narration", "Narration log entry", "Text",
             "$G: the following text goes into the text log (Z at a wait) as narration, "
             "without a speaker name. Vanilla uses it after $O3 in world-map narration."),
    StepKind("typing_sound", "Typing sound", "Text",
             "$O<n>: sound played as text appears (SFX_SYS_MSG<n>). Nothing is drawn.",
             (FieldSpec("value", "Sound", "choice", _TYPING_SOUNDS),)),
    StepKind("yield", "Yield to script", "Flow",
             "$H: pause the message and resume the event script; the message continues later."),
    StepKind("release_script", "Release event script", "Flow",
             "$UB/$Ub: let the event script that started this message run again while the "
             "message stays on screen. Vanilla puts it right before $H, at the end of a message "
             "so the scene carries over, or mid-message so the script can move the camera or units. "
             "$Ub also sets a flag nothing reads.",
             (FieldSpec("code", "Code", "choice", _RELEASE),)),
    StepKind("skip", "Conversation skipping", "Flow",
             "$SD/$SE: normally B skips the whole conversation. After $SD, B advances the text "
             "like A instead; $SE restores skipping. Vanilla disables skipping around choices.",
             (FieldSpec("mode", "Skipping", "choice", _SKIP),)),
    StepKind("control", "Control code", "Advanced",
             "$C…| is not a command in the US executable: the game prints the text after it.",
             (FieldSpec("code", "Code", "choice", _CONTROLS),), confidence="Undecoded"),
    StepKind("raw", "Raw text", "Advanced", "Unrecognised source kept byte for byte.",
             (FieldSpec("text", "Source", "text"),), confidence="Raw"),
)}

_FACE_CODES = {"FC": ("load_portrait", "fid"), "FD": ("remove_portrait", None),
               "Fc": ("eyes", "c"), "Fh": ("eyes", "h"), "Fo": ("eyes", "o"), "Fd": ("eyes", "d"),
               "Ff": ("blink", "f"), "Fs": ("blink", "s"), "FS": ("mouth_set", "S"), "FA": ("mouth_set", "A")}
_CONTROL_CODES = {"C"}


@dataclass
class Step:
    kind: str
    fields: dict = field(default_factory=dict)
    raw: str | None = None   # exact cp437 source; None once edited
    offset: int = -1         # source byte offset, -1 for new steps

    def edited(self, **changes) -> "Step":
        return Step(self.kind, {**self.fields, **changes}, None, self.offset)


def new_step(kind: str, **fields) -> Step:
    defaults = {"layout": {"layout": "上下会話"}, "background": {"background": ""},
                "transition": {"ms": 1000}, "load_portrait": {"seat": 0, "fid": ""},
                "remove_portrait": {"seat": 0}, "eyes": {"seat": 0, "mode": "c"},
                "blink": {"seat": 0, "speed": "s"}, "mouth_set": {"seat": 0, "set": "A"},
                "select_seat": {"seat": 0}, "show_speaker": {"box": 0, "fid": ""},
                "select_box": {"box": 0, "command": "s"}, "dismiss_box": {"box": 0},
                "windows": {"mode": "-"}, "control": {"code": "C"}, "typing_sound": {"value": "1"},
                "release_script": {"code": "UB"}, "skip": {"mode": "SD"},
                "raw": {"text": ""},
                "line": {"select": "", "index": 0, "flush": True, "text": "", "wait": True}}
    return Step(kind, {"trail": 0, **defaults.get(kind, {}), **fields})


def _is_inline(token: Token) -> bool:
    return token.code in ("text", "w", "MC", "MD", "N", "markup")


def decompile(text: str) -> list[Step]:
    tokens = tokenize(text)
    ends = [t.offset for t in tokens[1:]] + [len(text)]
    steps: list[Step] = []
    line: Step | None = None
    i = 0

    def add(kind, offset, **fields):
        steps.append(Step(kind, {"trail": 0, **fields}, None, offset))
        return steps[-1]

    def open_line(offset, select="", index=0, flush=False):
        return add("line", offset, select=select, index=index, flush=flush, text="", wait=False)

    while i < len(tokens):
        token = tokens[i]
        code, arg = token.code, token.arg
        following = tokens[i + 1] if i + 1 < len(tokens) else None
        source = text[token.offset:ends[i]]
        if code == "text" and arg == "\n" and line is None and steps:
            steps[-1].fields["trail"] += 1
        elif _is_inline(token):
            if line is None:
                line = open_line(token.offset)
            line.fields["text"] += to_display(source)
        elif code == "P":
            line = open_line(token.offset, flush=True)
        elif code == "K":
            if line is None:
                add("wait", token.offset)
            else:
                line.fields["wait"] = True
                line = None
        elif code in ("F", "s", "W") and arg.isdigit():
            line = None
            index = int(arg)
            if code == "F" and following and following.code in _FACE_CODES:
                kind, value = _FACE_CODES[following.code]
                fields = {"seat": index}
                if value == "fid":
                    fields["fid"] = following.arg
                elif value:
                    fields[{"eyes": "mode", "blink": "speed", "mouth_set": "set"}[kind]] = value
                add(kind, token.offset, **fields)
                i += 1
            elif following and (following.code == "P" or _is_inline(following) and following.arg != "\n"):
                line = open_line(token.offset, code, index, following.code == "P")
                if following.code == "P":
                    i += 1
            elif code == "F":
                add("select_seat", token.offset, seat=index)
            else:
                add("select_box", token.offset, box=index, command=code)
        else:
            line = None
            if code == "R":
                add("layout", token.offset, layout=arg)
            elif code == "B":
                add("background", token.offset, background=arg)
            elif code == "=":
                add("transition", token.offset, ms=int(arg))
            elif code in ("<", ">"):
                add("fade_in" if code == "<" else "fade_out", token.offset)
            elif code in _FACE_CODES:
                kind, value = _FACE_CODES[code]
                fields = {"seat": None}
                if value == "fid":
                    fields["fid"] = arg
                elif value:
                    fields[{"eyes": "mode", "blink": "speed", "mouth_set": "set"}[kind]] = value
                add(kind, token.offset, **fields)
            elif code == "c" and arg[:1].isdigit():
                add("show_speaker", token.offset, box=int(arg[0]), fid=arg[1:])
            elif code == "d":
                add("dismiss_box", token.offset, box=int(arg))
            elif code in ("W-", "W+", "WD"):
                add("windows", token.offset, mode=code[1])
            elif code == "ND":
                add("nametag", token.offset)
            elif code == "H":
                add("yield", token.offset)
            elif code == "O":
                add("typing_sound", token.offset, value=arg)
            elif code in ("SD", "SE", "DC"):
                add("skip", token.offset, mode=code)
            elif code in ("UB", "Ub"):
                add("release_script", token.offset, code=code)
            elif code == "G":
                add("narration", token.offset)
            elif code == "Y":
                add("no_wait", token.offset)
            elif code in _CONTROL_CODES and (code != "C" or not arg):
                add("control", token.offset, code=code)
            else:
                add("raw", token.offset, text=to_display(source))
        i += 1

    for index, step in enumerate(steps):
        end = steps[index + 1].offset if index + 1 < len(steps) else len(text)
        step.raw = text[step.offset:end]
    return steps


def render_step(step: Step) -> str:
    """Source text of one step: its original slice, or its canonical form."""
    if step.raw is not None:
        return step.raw
    f, kind = step.fields, step.kind
    seat = f"$F{f['seat']}" if f.get("seat") is not None else ""
    if kind == "layout":
        out = f"$R{to_raw(f['layout'])}|"
    elif kind == "background":
        out = f"$B{to_raw(f['background'])}|"
    elif kind == "transition":
        out = f"$={int(f['ms']):04d}"
    elif kind in ("fade_in", "fade_out"):
        out = "$<" if kind == "fade_in" else "$>"
    elif kind == "load_portrait":
        out = f"{seat}$FC{f['fid']}|"
    elif kind == "remove_portrait":
        out = f"{seat}$FD"
    elif kind == "eyes":
        out = f"{seat}$F{f['mode']}"
    elif kind == "blink":
        out = f"{seat}$F{f['speed']}"
    elif kind == "mouth_set":
        out = f"{seat}$F{f['set']}"
    elif kind == "select_seat":
        out = f"$F{f['seat']}"
    elif kind == "show_speaker":
        out = f"$c{f['box']}{f['fid']}|"
    elif kind == "select_box":
        out = f"${f['command']}{f['box']}"
    elif kind == "dismiss_box":
        out = f"$d{f['box']}"
    elif kind == "windows":
        out = f"$W{f['mode']}"
    elif kind == "nametag":
        out = "$ND"
    elif kind == "line":
        target = f"${f['select']}{f['index']}" if f.get("select") else ""
        out = target + ("$P" if f["flush"] else "") + to_raw(f["text"]) + ("$K" if f["wait"] else "")
    elif kind == "wait":
        out = "$K"
    elif kind == "yield":
        out = "$H"
    elif kind == "control":
        out = "$C|" if f["code"] == "C" else "$" + f["code"]
    elif kind == "typing_sound":
        out = f"$O{int(f['value'])}"
    elif kind in ("skip", "release_script"):
        out = "$" + f["mode" if kind == "skip" else "code"]
    elif kind == "narration":
        out = "$G"
    elif kind == "no_wait":
        out = "$Y"
    elif kind == "raw":
        out = to_raw(f["text"])
    else:
        raise ValueError(f"Unknown step kind: {kind}")
    return out + "\n" * f.get("trail", 0)


def compile_steps(steps: list[Step]) -> str:
    return "".join(render_step(step) for step in steps)


def step_offsets(steps: list[Step]) -> list[int]:
    """Source start offset of each step in ``compile_steps(steps)``."""
    offsets, position = [], 0
    for step in steps:
        offsets.append(position)
        position += len(render_step(step))
    return offsets


def step_at_offset(offsets: list[int], offset: int) -> int:
    return max(0, bisect_right(offsets, offset) - 1)


def validate_step(step: Step) -> str | None:
    """Return an error for fields the game cannot encode, else None."""
    f = step.fields
    for name in ("fid", "layout", "background"):
        if name in f and ("|" in f[name] or "$" in f[name]):
            return f"{name} cannot contain '|' or '$'"
    if step.kind in ("load_portrait", "show_speaker") and not f.get("fid"):
        return "Choose a portrait"
    if step.kind == "transition" and not 0 <= int(f["ms"]) <= 9999:
        return "Duration must be 0-9999"
    if step.kind == "typing_sound" and not 0 <= int(f["value"]) <= 9:
        return "Value must be 0-9"
    for key in ("seat", "index"):
        if f.get(key) is not None and not 0 <= int(f[key]) <= (3 if key == "index" and f.get("select") in ("s", "W") else 8):
            return f"{key} out of range"
    if "box" in f and not 0 <= int(f["box"]) <= 3:
        return "Box must be 0-3"
    try:
        render_step(step.edited())
    except UnicodeEncodeError as error:
        return f"Character not in the game's Shift-JIS encoding: {error.object[error.start:error.end]!r}"
    return None


def summary(step: Step) -> str:
    """One-line description of a step for the step list."""
    f, kind = step.fields, step.kind
    seat = f"seat {f['seat']}" if f.get("seat") is not None else "current seat"
    if kind == "layout":
        text = layout_label(f["layout"])
    elif kind == "background":
        text = f["background"]
    elif kind == "transition":
        text = "default (267 ms)" if int(f["ms"]) == 9999 else f"{int(f['ms'])} ms"
    elif kind == "load_portrait":
        text = f"{seat} ← {f['fid']}"
    elif kind in ("remove_portrait", "select_seat"):
        text = seat
    elif kind in ("eyes", "blink", "mouth_set"):
        spec = STEP_KINDS[kind].fields[1]
        text = f"{seat}: " + dict(spec.choices)[f[spec.name]].split(" (")[0]
    elif kind == "show_speaker":
        text = f"box {f['box']} ← {f['fid']}"
    elif kind in ("select_box", "dismiss_box"):
        text = f"box {f['box']}"
    elif kind in ("windows", "control", "skip", "release_script"):
        spec = STEP_KINDS[kind].fields[0]
        text = dict(spec.choices)[f[spec.name]]
    elif kind == "typing_sound":
        text = dict(_TYPING_SOUNDS).get(str(f["value"]), f"SFX_SYS_MSG{f['value']} ($O{f['value']})")
    elif kind == "line":
        who = {"F": "seat ", "s": "box ", "W": "box "}.get(f["select"], "")
        prefix = f"[{who}{f['index']}] " if f["select"] else ""
        body = line_plain_text(f["text"]).replace("\n", " / ")
        text = prefix + (body if body.strip(" /") else "(line break)" if body else "(no text)") + ("" if f["wait"] else "  …")
    elif kind == "raw":
        text = f["text"]
    else:
        text = ""
    return text + (" ↵" * f.get("trail", 0))


def line_plain_text(text: str) -> str:
    """Line text without inline commands, for summaries."""
    tokens = tokenize(to_raw(text)) if text else ()
    out = []
    for token in tokens:
        if token.code == "text":
            out.append(token.arg)
        elif token.code == "N":
            out.append("\n")
        elif token.code == "markup" and token.arg == "##":
            out.append("#")
    return "".join(out)


INLINE_CODES: tuple[tuple[str, str], ...] = (
    ("$w1", "Pause 2 frames"), ("$w2", "Pause 4 frames"), ("$w3", "Pause 8 frames"),
    ("$w4", "Pause 16 frames"), ("$w5", "Pause 32 frames"), ("$w6", "Pause 64 frames"),
    ("$MC...$MD", "Ellipsis with the mouth still"), ("$MC--$MD", "Dash with the mouth still"),
    ("$N", "New line ($N)"), ("#C0A", "Colour 0A (#Cxx)"), ("#c", "Previous colour (#c)"),
)

#: What vanilla text uses each #P icon cell for (window/icon.tpl image 0, 24x24, 32 per row).
ICON_LABELS: dict[int, str] = {
    0x01: "Boss", 0x09: "Beorc", 0x0A: "Laguz", 0x0B: "Knight", 0x0C: "Armor", 0x0D: "Dragon",
    0x0E: "Flying", 0x0F: "Sword / knife", 0x10: "Lance", 0x11: "Axe", 0x12: "Bow", 0x13: "Staff",
    0x14: "Fire", 0x15: "Wind", 0x16: "Thunder", 0x27: "A button (OK)", 0x28: "B button (Back)",
    0x2A: "Status / Help button", 0x2B: "Unit List button", 0x2C: "Move left/right (tutorial)",
    0x2D: "Switch (item captions, with 02E-030)", 0x2E: "Switch (with 02D)", 0x2F: "Switch (with 030)",
    0x30: "Switch (with 02F)", 0x31: "Move (tutorial, alternative to 02C)", 0x32: "Fight button",
    0x33: "Menu / Reinforcement (first half, with 034)", 0x34: "Menu / Reinforcement (second half)",
    0x35: "Select Topic", 0x36: "Select Content", 0x38: "Select", 0x53: "Beast", 0x54: "Bird",
}

#: Fonts a Line can switch to: (index, label, opening codes). A switch lasts until the end of
#: the textbox line, so ``apply_font`` repeats it on every line and closes it with ``#F02``
#: (back to talk). The Tellius alphabet also switches the typing sound, as vanilla does.
FONT_CHOICES: tuple[tuple[int, str, str], ...] = (
    (1, "Tellius alphabet (ancient language)", "#F01$O2"),
    (0, "System (menu font)", "#F00"),
    (3, "Bigkana (title-menu serif)", "#F03"),
    (4, "Alpha (staff-roll sans)", "#F04"),
    (2, "Talk (dialogue default)", "#F02"),
)
FONT_LABELS = {0: "system", 1: "fe_font, the Tellius alphabet", 2: "talk, the dialogue default",
               3: "bigkana, a large serif", 4: "alpha, a condensed sans"}
_FONT_CODES = re.compile(r"#F0[0-9](?:\$O[0-9])?")


def apply_font(text: str, start: int, end: int, index: int) -> tuple[str, int, int]:
    """Draw ``text[start:end]`` in font ``index``; returns the new text and selection.

    Each line of the selection gets its own opening code and, unless the font is talk, a
    closing ``#F02`` (plus ``$O1`` after the Tellius alphabet), matching vanilla's
    ``#F01$O2...#F02$O1``. An empty selection inserts the pair around the cursor."""
    opening = next(code for i, _label, code in FONT_CHOICES if i == index)
    closing = "" if index == 2 else "#F02$O1" if index == 1 else "#F02"
    if start == end:
        return text[:start] + opening + closing + text[end:], start + len(opening), start + len(opening)
    parts = []
    for segment in _FONT_CODES.sub("", text[start:end]).split("\n"):
        parts.append(opening + segment + closing if segment.strip() else segment)
    middle = "\n".join(parts)
    return text[:start] + middle + text[end:], start, start + len(middle)


def strip_fonts(text: str, start: int, end: int) -> tuple[str, int, int]:
    """Remove ``#F0n`` codes (and the ``$On`` right after them) from the selection."""
    if start == end:
        start, end = 0, len(text)
    middle = _FONT_CODES.sub("", text[start:end])
    return text[:start] + middle + text[end:], start, start + len(middle)


def describe_inline(code: str) -> str:
    """Hover text for an inline command in a Line."""
    if code.startswith("$w") and code[2:].isdigit():
        return f"Pause 2^{code[2:]} = {1 << int(code[2:])} frames"
    parts = re.findall(r"#F[0-9]{2}|\$O[0-9]", code)
    if len(parts) > 1 and "".join(parts) == code:
        return "; ".join(describe_inline(part) for part in parts)
    if code.startswith("#F") and code[2:].isdigit():
        index = int(code[2:])
        return f"Font {index}: {FONT_LABELS.get(index, 'no such font')}, until the end of the line"
    if len(code) == 4 and code[:2] in ("#S", "#X", "#Y") and all(c in "0123456789abcdefABCDEF" for c in code[2:]):
        value = int(code[2:], 16)
        axis = {"#S": "Text scale", "#X": "Horizontal text scale", "#Y": "Vertical text scale"}[code[:2]]
        return f"{axis} {value}/64 = {value / 64:.0%}, from the line's top-left corner, until reset or the end of the line"
    if len(code) == 4 and code[:2] in ("#R", "#G", "#B", "#A") and all(c in "0123456789abcdefABCDEF" for c in code[2:]):
        channel = {"#R": "Red", "#G": "Green", "#B": "Blue", "#A": "Alpha"}[code[:2]]
        return f"{channel} channel of the text colour = {int(code[2:], 16)}/255"
    if len(code) == 4 and code[:2] == "#I" and all(c in "0123456789abcdefABCDEF" for c in code[2:]):
        return f"Italic: the top of the line leans {int(code[2:], 16) / 16:g}px right"
    if code.startswith("#P") and len(code) == 5:
        return f"Icon {code[2:]}: cell {int(code[2:], 16)} of window/icon.tpl (24x24)"
    if code.startswith("$O") and code[2:].isdigit():
        sounds = {"0": "silent", "1": "dialogue", "2": "ancient language", "3": "narration", "4": "tutorial"}
        return f"Typing sound {code[2:]} ({sounds.get(code[2:], 'SFX_SYS_MSG' + code[2:])})"
    return {"$MC": "Stop mouth motion", "$MD": "Restart mouth motion", "$N": "New line",
            "#c": "Restore previous colour", "#D": "Default colour, scale and italic; shadow and outline off", "##": "Literal #"}.get(
        code, {"#C": "Text colour", "#F": "Font",
               "#x": "Reset horizontal text scale", "#y": "Reset vertical text scale (the window"
               " width measurement also skips the next 2 characters)",
               "#s": "Reset text scale", "#E": "Drop shadow on (2px, black at half alpha)",
               "#e": "Drop shadow off", "#O": "Outline on (1px black, 8 directions)",
               "#o": "Outline off", "#i": "Italic off"}.get(code[:2], code))


def _template(*parts: str) -> str:
    return to_raw("".join(parts))


TEMPLATES: dict[str, str] = {
    "Empty message": "",
    "Two-box talk (上下会話)": _template(
        "$R上下会話|$c0IKE|$s0First line.$K\n", "$c1MIST|$s1Reply.$K"),
    "Background scene (背景会話)": _template(
        "$R背景会話|$B村-崖|$<$F1$FCL_IKE|$F4$FCL_MIST|",
        "$F1$PFirst line.$K\n", "$F4$PReply.$K"),
    "World map narration (GMAP会話)": _template("$RGMAP会話|$O3$GNarration text.$K"),
}
