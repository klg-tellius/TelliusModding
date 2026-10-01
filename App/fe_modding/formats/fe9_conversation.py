"""Deterministic, seekable FE9 message interpreter.

The event index is authoritative: an input wait and the next command can share
a timestamp without either being skipped. Milliseconds describe game time;
waiting for the user does not consume game time.
"""
from __future__ import annotations

import re
from bisect import bisect_right
from dataclasses import dataclass, field, replace
from typing import Callable


@dataclass(frozen=True)
class Diagnostic:
    offset: int
    description: str


@dataclass(frozen=True)
class Token:
    offset: int
    code: str
    arg: str = ""


_COMMAND = re.compile(rb"\$(?:([RBcC])([^|]*)\||FC([^|]*)\||([F][ASDcdhfos0-9])|([sdwWO][0-9])|(=[0-9]{4})|(M[CD]|U[Bb]|[SN]D|DC|SE|W[+\-D])|([KPNHGY<>]))")

# Message Speed option (MCFG_MESSSPEED) -> frames per text tick, from process_dialogue_textbox_frame
# (80120354): option 0 Slow 10, 1 Normal 4, 2 Fast 1, 3 Max = the whole page in one tick.
TEXT_SPEEDS = {"slow": 10, "normal": 4, "fast": 1, "max": 0}
# Commands for which dialogue_textbox_exec_command (8011e4b8) returns 2: they end the current
# text tick, so the next glyph waits for the following tick.
# Markup kept in a textbox's text for the renderer (draw_markup_text_core 8000e7fc).
_DRAWN_MARKUP = ("#F", "#C", "#P", "#S", "#X", "#Y", "#R", "#G", "#B", "#A", "#I",
                 "#c", "#D", "#s", "#x", "#y", "#E", "#e", "#O", "#o", "#i")
_TICK_ENDING = {"c", "d", "P", "K", "H", "Y", "w", "W+", "W-", "WD"}


def tokenize(text: str) -> tuple[Token, ...]:
    data = text.encode("cp437")
    result = []
    i = 0
    while i < len(data):
        match = _COMMAND.match(data, i)
        if match:
            groups = match.groups()
            if groups[0]:
                code = groups[0].decode()
                arg = groups[1].decode("shift_jis" if code in ("R", "B") else "ascii")
            elif groups[2] is not None:
                code, arg = "FC", groups[2].decode("ascii")
            else:
                command = next(g.decode() for g in groups[3:] if g is not None)
                if command[0] in "sdwWO=" and command[-1].isdigit():
                    code, arg = command[0], command[1:]
                elif command[0] == "F" and command[1].isdigit():
                    code, arg = "F", command[1]
                else:
                    code, arg = command, ""
            result.append(Token(i, code, arg)); i = match.end()
        elif data[i] == 36:
            end = min(i + 2, len(data))
            result.append(Token(i, "unsupported", data[i:end].decode("ascii", errors="replace"))); i = end
        elif data[i] == 35 and i + 1 < len(data):
            code = chr(data[i+1])
            length = 4 if code in "ABCGIRYFSX" else 5 if code == "P" else 2
            result.append(Token(i, "markup", data[i:i+length].decode("ascii", errors="replace"))); i += length
        else:
            size = 2 if (0x81 <= data[i] <= 0x9f or 0xe0 <= data[i] <= 0xfc) and i + 1 < len(data) else 1
            result.append(Token(i, "text", data[i:i+size].decode("shift_jis", errors="replace"))); i += size
    return tuple(result)


@dataclass(frozen=True)
class Portrait:
    fid: str = ""
    mouth: int | None = 1
    eye_mode: int = 1
    blink_mode: int = 1
    loaded_ms: int = 0
    expression_ms: int = 0


@dataclass(frozen=True)
class Textbox:
    text: str = ""
    visible: bool = False
    width: int = 368
    opened_ms: int = 0


@dataclass(frozen=True)
class InitialContext:
    layout: str = "上下会話"
    background: str = ""
    portraits: tuple[str, ...] = ("",) * 9
    aliases: tuple[tuple[str, str], ...] = ()


@dataclass(frozen=True)
class Scene:
    layout: str = "上下会話"
    background: str = ""
    portraits: tuple[Portrait, ...] = field(default_factory=lambda: (Portrait(),) * 9)
    boxes: tuple[Textbox, ...] = field(default_factory=lambda: (Textbox(),) * 4)
    box: int = 0
    seat: int = 0
    speaker_seat: int = -1
    mouth_enabled: bool = True
    nametag: bool = True
    transition_ms: int = 267
    screen_black: bool = False
    # ("in" | "out", start_ms, duration_ms) of the latest $< / $> screen transition. It runs
    # alongside the text: the message does not wait for it.
    screen_fade: tuple[str, int, int] | None = None
    # $SD/$SE: while False, B no longer skips the conversation and advances text like A instead.
    skippable: bool = True
    # $UB/$Ub: the event script that started the message has been released and runs again.
    script_released: bool = False


@dataclass(frozen=True)
class Event:
    index: int
    time_ms: int
    source_offset: int
    kind: str
    state: Scene
    wait: bool = False
    transition_from: Scene | None = None
    transition_duration_ms: int = 0


@dataclass(frozen=True)
class Timeline:
    events: tuple[Event, ...]
    diagnostics: tuple[Diagnostic, ...]
    times: tuple[int, ...]

    @property
    def duration_ms(self):
        return self.times[-1]

    def index_at(self, time_ms: int) -> int:
        return max(0, bisect_right(self.times, time_ms) - 1)

    def advance(self, index: int, target_ms: int, *, stop_at_wait=True) -> int:
        last = index
        for event in self.events[index+1:]:
            if event.time_ms > target_ms:
                break
            last = event.index
            if stop_at_wait and event.wait:
                break
        return last


def build_timeline(text: str, *, context: InitialContext | None = None,
                   measure: Callable[[str], int] | None = None,
                   text_speed: str = "normal") -> Timeline:
    """``text_speed`` is the Message Speed option: slow, normal, fast or max."""
    if text_speed not in TEXT_SPEEDS:
        raise ValueError(f"Unknown text speed {text_speed!r}")
    tick_frames = TEXT_SPEEDS[text_speed]
    context = context or InitialContext()
    if len(context.portraits) != 9:
        raise ValueError("Initial context must contain nine portrait seats")
    measure = measure or (lambda s: len(s) * 10)
    tokens = tokenize(text)
    aliases = dict(context.aliases)
    aliases = {(k if k.startswith("FID_") else "FID_" + k):
               (v if v.startswith("FID_") else "FID_" + v) for k, v in aliases.items() if v}
    scene = Scene(layout=context.layout, background=context.background,
                  portraits=tuple(Portrait(fid=(f if f.startswith("FID_") else "FID_" + f)) if f else Portrait()
                                  for f in context.portraits))
    events, diagnostics = [], []
    frames = 0  # game time in 60 Hz frames; events report milliseconds

    def now():
        return round(frames * 1000 / 60)

    def emit(kind="command", offset=0, wait=False, transition_from=None, duration=0):
        events.append(Event(len(events), now(), offset, kind, scene, wait, transition_from, duration))

    def end_tick():
        # Even at Max speed the following glyphs wait for the next frame.
        nonlocal frames
        frames += max(1, tick_frames)

    def portrait(**changes):
        nonlocal scene
        portraits = list(scene.portraits)
        portraits[scene.seat] = replace(portraits[scene.seat], **changes)
        scene = replace(scene, portraits=tuple(portraits))

    def textbox(**changes):
        nonlocal scene
        boxes = list(scene.boxes)
        boxes[scene.box] = replace(boxes[scene.box], **changes)
        scene = replace(scene, boxes=tuple(boxes))

    def load_face(name, offset):
        fid = name if name.startswith("FID_") else "FID_" + name
        fid = aliases.get(fid, fid)
        if fid in ("FID_ME", "FID_LME"):
            diagnostics.append(Diagnostic(offset, f"{fid} needs a character alias in Initial context"))
        if scene.portraits[scene.seat].fid:
            portrait(fid=fid, mouth=1, eye_mode=1, blink_mode=1, loaded_ms=now(), expression_ms=now())
        else:
            portrait(fid=fid, loaded_ms=now())

    def width_after(start, box):
        # 801208bc: scan future lines for this window until its dismissal.
        active, line, maximum = box, "", 0
        for token in tokens[start:]:
            code = token.code
            if code == "d" and int(token.arg) == box:
                break
            if code in ("s", "W") and token.arg.isdigit():
                active = int(token.arg)
            if code == "c" and token.arg[:1].isdigit():
                active = int(token.arg[0])
            if code in ("P", "N") or (code == "text" and token.arg == "\n"):
                maximum = max(maximum, measure(line)); line = ""
            elif (code == "text" or code == "markup" and token.arg.startswith(_DRAWN_MARKUP)) and active == box:
                line += token.arg
        return min(560, max(368, max(maximum, measure(line)) + 224))

    emit()
    for i, token in enumerate(tokens):
        before = scene
        code, arg = token.code, token.arg
        if code == "text":
            char = arg
            old = scene.boxes[scene.box]
            # Empty separator lines after waits do not create a visible new page.
            if char == "\n" and (not old.text or old.text.endswith("\n")):
                continue
            text_value = old.text + char
            # The native text queue scrolls when its three visible lines fill.
            if char != "\n" and len(text_value.split("\n")) > 3:
                text_value = "\n".join(text_value.split("\n")[-3:])
            textbox(text=text_value, visible=True)
            if char != "\n":
                scene = replace(scene, speaker_seat=scene.seat)
            emit("text", token.offset)
            if char != "\n":
                frames += tick_frames
            continue
        if code == "R":
            scene = replace(scene, layout=arg, boxes=(Textbox(),)*4, speaker_seat=-1)
        elif code == "B":
            scene = replace(scene, background=arg)
        elif code == "=":
            scene = replace(scene, transition_ms=267 if arg == "9999" else int(arg))
        elif code in ("<", ">"):
            # screen_start_transition (8008a32c): ms / 16.667 whole frames, linear (easing mode 0).
            duration = round(scene.transition_ms * 60 // 1000 * 1000 / 60)
            scene = replace(scene, screen_black=code == ">",
                            screen_fade=("in" if code == "<" else "out", now(), duration))
            emit("screen_fade_in" if code == "<" else "screen_fade_out", token.offset, duration=duration)
            continue
        elif code in ("s", "W", "c", "d"):
            value = int(arg[0]) if arg and arg[0].isdigit() else -1
            if not 0 <= value < 4:
                diagnostics.append(Diagnostic(token.offset, f"Invalid textbox: ${code}{arg}")); continue
            scene = replace(scene, box=value, seat=value, speaker_seat=-1)
            if code == "s" and not scene.boxes[value].visible:
                # $s on a hidden box only selects it: no flush, and the text tick goes on.
                emit(offset=token.offset)
                continue
            if code == "d":
                textbox(visible=False, text=""); portrait(fid="",mouth=1,eye_mode=1,blink_mode=1)
            else:
                old_box = scene.boxes[value]
                width = old_box.width if old_box.visible else width_after(i+1,value)
                textbox(width=width, visible=True, text="", opened_ms=now())
                if code == "c":
                    load_face(arg[1:], token.offset)
        elif code == "F":
            if not 0 <= int(arg) < 9:
                diagnostics.append(Diagnostic(token.offset, f"Invalid portrait seat: {arg}")); continue
            scene = replace(scene, seat=int(arg), speaker_seat=-1)
        elif code == "FC":
            load_face(arg, token.offset)
        elif code == "FD":
            portrait(fid="",mouth=1,eye_mode=1,blink_mode=1); scene = replace(scene, speaker_seat=-1)
        elif code in ("FS", "FA"):
            portrait(mouth=0 if code == "FS" else 1)
        elif code in ("Fc", "Fh", "Fo", "Fd", "Ff", "Fs"):
            changes = {"expression_ms": now()}
            if code in ("Fc", "Fh", "Fo", "Fd"):
                changes["eye_mode"] = {"Fc":3,"Fh":4,"Fo":5,"Fd":1}[code]
            if code in ("Fd", "Ff", "Fs", "Fo"):
                changes["blink_mode"] = {"Fd":1,"Ff":2,"Fs":1,"Fo":5}[code]
            portrait(**changes)
        elif code == "P":
            textbox(text="", visible=True)
        elif code == "N":
            textbox(text=scene.boxes[scene.box].text + "\n")
        elif code == "ND":
            scene = replace(scene, nametag=not scene.nametag)
        elif code in ("MC", "MD"):
            scene = replace(scene, mouth_enabled=(code=="MD"))
        elif code in ("K", "H"):
            emit("wait" if code == "K" else "event_wait", token.offset, True)
            end_tick()
            continue
        elif code == "w":
            # A blocking child process of 2^n frames, then the rest of the text tick.
            emit("pause", token.offset)
            frames += 1 << int(arg)
            emit("pause_end", token.offset)
            end_tick()
            continue
        elif code == "WD":
            textbox(visible=False, text="")
        elif code == "W-":
            scene = replace(scene, boxes=tuple(replace(b,visible=False) for b in scene.boxes))
        elif code == "W+":
            scene = replace(scene, boxes=tuple(replace(b,visible=bool(b.text)) for b in scene.boxes))
        elif code in ("SD", "DC", "SE"):
            # Bit 8 of the dialogue flags (80367a58): B stops skipping the conversation.
            scene = replace(scene, skippable=code == "SE")
        elif code in ("UB", "Ub"):
            # Releases the event script blocked on this message; $Ub's extra flag 0x100 is never read.
            scene = replace(scene, script_released=True)
        elif code in ("G", "Y"):
            # $G names the text-log entry "G" (narration); $Y only ends the text tick.
            pass
        elif code == "O":
            # $On only picks the text-typing sound (SFX_SYS_MSG<n>, 0 = silent); nothing is drawn.
            pass
        elif code == "markup" and arg.startswith(_DRAWN_MARKUP):
            textbox(text=scene.boxes[scene.box].text+arg)
        elif code == "markup" and arg == "##":
            textbox(text=scene.boxes[scene.box].text+"#")
        else:
            diagnostics.append(Diagnostic(token.offset, f"Unsupported command: {arg if code in ('unsupported','markup') else '$'+code+arg}"))
        if code in ("FC", "c", "FD", "d") and before != scene:
            # Both face alpha and textbox visibility tweens use eight frames.
            # 800790d4/800791f0 and 80122238/801222a4; curve mode 0.
            emit("transition", token.offset, transition_from=before, duration=133)
            frames += 8
        emit(offset=token.offset)
        if code in _TICK_ENDING or code == "s":
            end_tick()
    emit("end", len(text))
    return Timeline(tuple(events), tuple(diagnostics), tuple(e.time_ms for e in events))
