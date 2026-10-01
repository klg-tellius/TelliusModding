"""Display-only conversation playback state built from message control codes."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Literal, Optional

from . import message

TEXT_REVEAL_MS = 33
WAIT_UNIT_MS = 250
PAGE_WAIT_MS = 900


@dataclass(frozen=True)
class PreviewPortrait:
    name: Optional[str] = None
    visible: bool = False
    expression: Optional[str] = None


@dataclass(frozen=True)
class PreviewSceneState:
    layout_mode: Optional[str] = None
    background: Optional[str] = None
    selected_box: int = 0
    selected_portrait_slot: int = 0
    speaker_names: tuple[str, str, str, str] = ("", "", "", "")
    portraits: tuple[PreviewPortrait, ...] = field(default_factory=lambda: tuple(PreviewPortrait() for _ in range(9)))


@dataclass(frozen=True)
class PreviewPage:
    state: PreviewSceneState
    speaker: str
    text: str


@dataclass(frozen=True)
class TimelineFrame:
    time_ms: int
    state: PreviewSceneState
    speaker: str
    text: str
    wait_for_input: bool = False
    kind: Literal["command", "text", "pause", "page_break", "end"] = "command"


@dataclass(frozen=True)
class ConversationTimeline:
    frames: tuple[TimelineFrame, ...]

    @property
    def duration_ms(self) -> int:
        return self.frames[-1].time_ms if self.frames else 0

    def frame_at(self, time_ms: int) -> TimelineFrame:
        if not self.frames:
            empty = PreviewSceneState()
            return TimelineFrame(0, empty, "", "", kind="end")
        current = self.frames[0]
        for frame in self.frames:
            if frame.time_ms > time_ms:
                break
            current = frame
        return current

    def next_wait_after(self, time_ms: int) -> Optional[TimelineFrame]:
        for frame in self.frames:
            if frame.time_ms > time_ms and frame.wait_for_input:
                return frame
        return None

    def next_interesting_after(self, time_ms: int) -> TimelineFrame:
        for frame in self.frames:
            if frame.time_ms > time_ms and (frame.kind != "text" or frame.wait_for_input):
                return frame
        return self.frames[-1]

    def next_frame_after(self, time_ms: int) -> TimelineFrame:
        for frame in self.frames:
            if frame.time_ms > time_ms:
                return frame
        return self.frames[-1]

    @property
    def page_count(self) -> int:
        return max(1, 1 + sum(1 for frame in self.frames if frame.wait_for_input))

    def page_number_at(self, time_ms: int) -> int:
        completed_breaks = sum(1 for frame in self.frames if frame.wait_for_input and frame.time_ms < time_ms)
        return min(self.page_count, completed_breaks + 1)


def build_timeline(text: str, fallback_speaker: str = "") -> ConversationTimeline:
    state = PreviewSceneState()
    frames: list[TimelineFrame] = []
    shown_text: list[str] = []
    now = 0

    def current_speaker() -> str:
        return state.speaker_names[state.selected_box] or fallback_speaker

    def append_frame(
        kind: Literal["command", "text", "pause", "page_break", "end"] = "command",
        wait: bool = False,
    ) -> None:
        frames.append(
            TimelineFrame(
                time_ms=now,
                state=state,
                speaker=current_speaker(),
                text="".join(shown_text),
                wait_for_input=wait,
                kind=kind,
            )
        )

    append_frame()
    for token in message.tokenize_control_codes(text):
        if isinstance(token, str):
            for char in token:
                shown_text.append(char)
                now += TEXT_REVEAL_MS
                append_frame("text")
            continue

        name = token.name
        if name == "layout_mode":
            state = replace(state, layout_mode=token.arg)
        elif name == "background":
            state = replace(state, background=token.arg)
        elif name == "select_box" and token.arg is not None:
            state = replace(state, selected_box=_clamp_index(token.arg, 0, 3))
        elif name == "set_speaker_name" and token.arg is not None:
            box = _raw_digit(token.raw, 2, state.selected_box)
            speakers = list(state.speaker_names)
            speakers[_clamp_index(box, 0, 3)] = token.arg
            state = replace(state, speaker_names=tuple(speakers))
        elif name == "dismiss_box":
            box = _raw_digit(token.raw, 2, state.selected_box)
            speakers = list(state.speaker_names)
            speakers[_clamp_index(box, 0, 3)] = ""
            state = replace(state, speaker_names=tuple(speakers))
        elif name == "select_portrait_slot" and token.arg is not None:
            state = replace(state, selected_portrait_slot=_clamp_index(token.arg, 0, 8))
        elif name == "portrait_by_name" and token.arg is not None:
            portraits = list(state.portraits)
            portraits[state.selected_portrait_slot] = replace(
                portraits[state.selected_portrait_slot],
                name=token.arg,
                visible=True,
            )
            state = replace(state, portraits=tuple(portraits))
        elif name == "hide_portrait":
            portraits = list(state.portraits)
            portraits[state.selected_portrait_slot] = replace(portraits[state.selected_portrait_slot], visible=False)
            state = replace(state, portraits=tuple(portraits))
        elif name == "portrait_expression":
            portraits = list(state.portraits)
            expression = token.arg or token.raw[1:]
            portraits[state.selected_portrait_slot] = replace(
                portraits[state.selected_portrait_slot], expression=expression
            )
            state = replace(state, portraits=tuple(portraits))
        elif name == "pause" and token.arg is not None:
            now += _clamp_index(token.arg, 1, 6) * WAIT_UNIT_MS
            append_frame("pause")
            continue
        elif name == "wait_for_input":
            append_frame("page_break", wait=True)
            shown_text.clear()
            now += PAGE_WAIT_MS
            continue

        append_frame("command")

    append_frame("end")
    return ConversationTimeline(tuple(_dedupe_frames(frames)))


def build_preview_pages(text: str, fallback_speaker: str = "") -> list[PreviewPage]:
    timeline = build_timeline(text, fallback_speaker)
    pages = [
        PreviewPage(frame.state, frame.speaker, frame.text.strip())
        for frame in timeline.frames
        if frame.wait_for_input
    ]
    final = timeline.frames[-1] if timeline.frames else None
    if final is not None and final.text.strip():
        if not pages or pages[-1].text != final.text.strip():
            pages.append(PreviewPage(final.state, final.speaker, final.text.strip()))
    if not pages:
        state = final.state if final is not None else PreviewSceneState()
        pages.append(PreviewPage(state=state, speaker=fallback_speaker, text=""))
    return pages


def _dedupe_frames(frames: list[TimelineFrame]) -> list[TimelineFrame]:
    out: list[TimelineFrame] = []
    for frame in frames:
        if out and out[-1] == frame:
            continue
        out.append(frame)
    return out


def _clamp_index(value: str | int, minimum: int, maximum: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = minimum
    return max(minimum, min(maximum, parsed))


def _raw_digit(raw: str, index: int, fallback: int) -> int:
    if len(raw) > index and raw[index].isdigit():
        return int(raw[index])
    return fallback
