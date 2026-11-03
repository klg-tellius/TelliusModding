"""Replay a Radiant Dawn message into preview frames (one per ``<wait>``), for the Dialogue tab.

This follows ``mess_exec_command`` (FUN_80149434) closely enough for a preview: the cast list,
the layout, the background, who stands at which position, the text of each box and when a page
is cleared. It does not run the game's timing (pauses, fades, voices); see fe10_message.py.
"""
from __future__ import annotations

from dataclasses import dataclass, field, replace

from . import fe10_message as fm


@dataclass(frozen=True)
class Actor:
    name: str                 # cast entry (``L_IKE``)
    position: int = -1
    visible: bool = False
    facing: str = "D"
    eyes: int = 0             # 0 open, 1 half, 2 closed
    mouth_set: int = 0


@dataclass(frozen=True)
class Box:
    position: int
    speaker: int = -1         # cast index
    text: str = ""
    open: bool = True


@dataclass(frozen=True)
class Frame:
    offset: int               # notation offset just after the command that produced the frame
    kind: str                 # "wait", "suspend", "end"
    layout: str
    background: str
    cast: tuple[str, ...]
    actors: tuple[Actor, ...]
    boxes: tuple[Box, ...]
    current: int              # current actor index (-1 none)
    position: int             # current position (-1 none)


@dataclass
class _State:
    layout: str = ""
    background: str = ""
    cast: list[str] = field(default_factory=list)
    actors: dict[int, Actor] = field(default_factory=dict)
    boxes: dict[int, Box] = field(default_factory=dict)
    current: int = -1
    position: int = -1

    def actor(self, index: int) -> Actor:
        if index not in self.actors:
            name = self.cast[index] if 0 <= index < len(self.cast) else f"#{index}"
            self.actors[index] = Actor(name)
        return self.actors[index]

    def box(self, position: int) -> Box:
        if position not in self.boxes:
            self.boxes[position] = Box(position)
        return self.boxes[position]

    def frame(self, offset: int, kind: str) -> Frame:
        return Frame(offset, kind, self.layout, self.background, tuple(self.cast),
                     tuple(self.actors[i] for i in sorted(self.actors)),
                     tuple(self.boxes[p] for p in sorted(self.boxes)), self.current, self.position)


def _hex(char: str) -> int:
    try:
        return int(char, 16)
    except ValueError:
        return 0


def build_frames(text: str, encoding: str = fm.ENCODING) -> list[Frame]:
    """Frames of a message (its cp437 text). Always at least one (the end of the message)."""
    state = _State()
    frames: list[Frame] = []
    offset = 0
    for token in fm.tokenize(text.encode("cp437"), encoding):
        display = fm.token_display(token, encoding)
        offset += len(display)
        if token.kind in ("text", "newline"):
            box_position = state.position if state.position >= 0 else -1
            box = state.box(box_position)
            chunk = "\n" if token.kind == "newline" else display
            state.boxes[box_position] = replace(box, text=box.text + chunk, open=True)
            continue
        if token.kind != "command":
            continue
        key = fm.command_key(token)
        args = token.args
        if key == "FL|":
            state.cast = list(args)
            state.actors = {}
        elif key == "R:":
            state.layout = args[0] if args else ""
            state.boxes = {}
        elif key in ("B:", "b:"):
            state.background = args[0] if args else ""
        elif key in ("seat", "speaker"):
            index, position = _hex(args[0][0]), _hex(args[0][1])
            state.current, state.position = index, position
            actor = state.actor(index)
            state.actors[index] = replace(actor, position=position)
            if key == "speaker":
                box = state.box(position)
                if box.speaker != index:
                    box = replace(box, speaker=index, text="")
                state.boxes[position] = box
        elif key in ("show", "show_now", "attach"):
            position, facing = _hex(args[0][0]), args[0][1]
            state.position = position
            if state.current >= 0:
                actor = state.actor(state.current)
                state.actors[state.current] = replace(actor, position=position, visible=True, facing=facing)
                box = state.box(position)
                state.boxes[position] = replace(box, speaker=state.current if box.speaker < 0 else box.speaker)
        elif key in ("hide", "hide_now"):
            if state.current >= 0:
                actor = state.actor(state.current)
                state.actors[state.current] = replace(actor, visible=False)
                state.boxes.pop(actor.position, None)
        elif key in ("page", "P"):
            position = state.position if state.position >= 0 else -1
            if position in state.boxes:
                state.boxes[position] = replace(state.boxes[position], text="")
        elif key in ("ec", "eh", "eo", "eO"):
            if state.current >= 0:
                state.actors[state.current] = replace(state.actor(state.current),
                                                      eyes={"ec": 2, "eh": 1}.get(key, 0))
        elif key in ("a", "s"):
            if state.current >= 0:
                state.actors[state.current] = replace(state.actor(state.current), mouth_set=1 if key == "a" else 0)
        elif key == "wait":
            frames.append(state.frame(offset, "wait"))
        elif key == "H":
            frames.append(state.frame(offset, "suspend"))
    frames.append(state.frame(offset, "end"))
    return frames


def frame_before(frames: list[Frame], offset: int) -> int:
    """Index of the frame shown for a notation offset (the first frame at or after it)."""
    for index, frame in enumerate(frames):
        if frame.offset >= offset:
            return index
    return len(frames) - 1
