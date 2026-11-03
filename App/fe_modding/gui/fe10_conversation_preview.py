"""Radiant Dawn conversation preview for the Dialogue tab: one picture per <wait> of the message.

Built on ``formats/fe10_conversation.py`` (the frames) and ``fe10_conversation_render.py`` (the
picture). The Dialogue tab calls the same methods it calls on the Path of Radiance preview."""
from __future__ import annotations

import dataclasses
import tkinter as tk
from pathlib import Path
from tkinter import ttk

from PIL import Image, ImageTk

from ..formats import fe10_conversation, fe10_message
from ..formats.fe10_conversation_render import SCENE_SIZE, WIDE_SIZE, Fe10ConversationAssets, render
from ..game_profile import files_root_of

#: The game's Message Speed option, in frames (1/60 s) per glyph; Max shows the whole page at once.
SPEEDS = {"Slow": 10, "Normal": 4, "Fast": 1, "Max": 0}


def typed(frame: fe10_conversation.Frame, count: int) -> fe10_conversation.Frame:
    """``frame`` with its current box showing only its first ``count`` characters (the text being
    typed out); the other boxes stay as they are."""
    boxes = [box for box in frame.boxes if box.text]
    target = next((box for box in boxes if box.position == frame.position), boxes[0] if boxes else None)
    if target is None or count >= len(target.text):
        return frame
    return dataclasses.replace(frame, boxes=tuple(
        dataclasses.replace(box, text=box.text[:count]) if box is target else box for box in frame.boxes))


def page_length(frame: fe10_conversation.Frame) -> int:
    boxes = [box for box in frame.boxes if box.text]
    target = next((box for box in boxes if box.position == frame.position), boxes[0] if boxes else None)
    return len(target.text) if target is not None else 0


class Fe10ConversationPreview(ttk.Frame):
    def __init__(self, parent, project):
        super().__init__(parent)
        self._files = files_root_of(project)
        self._assets: dict[tuple[str, bool], Fe10ConversationAssets] = {}
        self._wide = tk.BooleanVar(value=False)
        self._prefix = "e_"
        self._frames: list[fe10_conversation.Frame] = []
        self._source_positions = []
        self._index = 0
        self._photo = None
        self._render_id = None
        self._play_id = None
        self._playing = False
        self._reveal: int | None = None  # characters typed on the current page while playing; None = all
        self.on_position = None
        self.on_inheritance = None
        self.on_context_changed = None
        self.context_description = ""

        controls = ttk.Frame(self)
        controls.pack(fill="x")
        self._play = ttk.Button(controls, text="Play", width=9, command=self._toggle_play)
        self._play.pack(side="left", padx=(0, 4))
        for label, command in (("Restart", lambda: self._show(0)), ("Previous", lambda: self._show(self._index - 1)),
                               ("Next", lambda: self._show(self._index + 1))):
            ttk.Button(controls, text=label, command=command).pack(side="left", padx=(0, 4))
        self._auto = tk.BooleanVar(value=True)
        ttk.Checkbutton(controls, text="Auto-advance", variable=self._auto).pack(side="left", padx=4)
        self._speed = tk.StringVar(value="Normal")
        ttk.Label(controls, text="Message speed").pack(side="left", padx=(8, 2))
        ttk.Combobox(controls, textvariable=self._speed, values=tuple(SPEEDS), state="readonly",
                     width=7).pack(side="left")
        ttk.Checkbutton(controls, text="16:9", variable=self._wide, command=self._schedule).pack(side="left", padx=4)
        ttk.Button(controls, text="Reload assets", command=self._reload).pack(side="right")
        self._status = ttk.Label(self, style="Muted.TLabel")
        self._status.pack(anchor="w", pady=(3, 0))
        self._canvas = tk.Label(self, background="black", anchor="center")
        self._canvas.pack(fill="both", expand=True, pady=(4, 0))
        self._canvas.bind("<Configure>", lambda e: self._schedule())
        ttk.Label(self, text="One picture per <wait>. Portraits, layout seats, balloon sizes, backgrounds and the font "
                             "come from the disc; the window art is drawn as plain panels.",
                  style="Muted.TLabel", wraplength=520, justify="left").pack(anchor="w", pady=(4, 0))

    @property
    def assets(self) -> Fe10ConversationAssets:
        key = (self._prefix, self._wide.get())
        if key not in self._assets:
            self._assets[key] = Fe10ConversationAssets(self._files, self._prefix, wide=key[1])
        return self._assets[key]

    # -- what the Dialogue tab calls -------------------------------------------------------
    def update_message(self, speaker: str, text: str, *, context=None, message_id=None) -> None:
        if message_id is not None:
            name = Path(message_id[0]).name.lower()
            self._prefix = name[:2] if name[1:2] == "_" else ""
        self._source_positions = []
        display_end = 0
        for token in fe10_message.tokenize(text.encode("cp437")):
            display_end += len(fe10_message.token_display(token))
            self._source_positions.append((display_end, token.offset))
        try:
            self._frames = fe10_conversation.build_frames(text)
        except ValueError:
            self._frames = []
        self._index = min(self._index, max(0, len(self._frames) - 1))
        self._schedule()

    def seek_before(self, offset: int) -> None:
        if self._frames and not self._playing:  # while playing, the editor follows the preview
            self._show(fe10_conversation.frame_before(self._frames, offset), notify=False)

    def set_inheritance_source(self, sources, ids) -> None:
        pass

    def cleanup(self) -> None:
        self._stop()
        if self._render_id is not None:
            self.after_cancel(self._render_id)
            self._render_id = None

    # -- playing -------------------------------------------------------------------------------
    def _toggle_play(self) -> None:
        if self._playing:
            self._stop()
            self._schedule()
            return
        if not self._frames:
            return
        if self._reveal is None:  # a page shown whole: play the next one, or start over at the end
            if self._index >= len(self._frames) - 1:
                self._index = 0
            elif self._play.cget("text") == "Continue":
                self._index += 1
            self._reveal = 0
        self._playing = True
        self._play.configure(text="Pause")
        self._tick()

    def _stop(self) -> None:
        self._playing = False
        if self._play_id is not None:
            self.after_cancel(self._play_id)
            self._play_id = None
        if self.winfo_exists():
            self._play.configure(text="Play")

    def _tick(self) -> None:
        self._play_id = None
        if not self._playing or not self._frames:
            return
        frame = self._frames[self._index]
        per_glyph = SPEEDS.get(self._speed.get(), 4)
        length = page_length(frame)
        self._reveal = length if per_glyph == 0 else min(length, (self._reveal or 0) + 1)
        self._draw()
        if self._reveal < length:
            self._play_id = self.after(max(16, per_glyph * 1000 // 60), self._tick)
            return
        self._reveal = None
        if frame.kind == "end" or self._index >= len(self._frames) - 1:
            self._stop()
        elif self._auto.get():
            self._play_id = self.after(900, self._next_page)
        else:
            self._playing = False
            self._play.configure(text="Continue")

    def _next_page(self) -> None:
        self._play_id = None
        if self._playing and self._index < len(self._frames) - 1:
            self._index += 1
            self._reveal = 0
            self._notify()
            self._tick()

    # -- drawing -------------------------------------------------------------------------------
    def _reload(self) -> None:
        self._assets.clear()
        self._schedule()

    def _show(self, index: int, notify: bool = True) -> None:
        if not self._frames:
            return
        self._stop()
        self._reveal = None
        self._index = max(0, min(index, len(self._frames) - 1))
        self._schedule()
        if notify:
            self._notify()

    def _notify(self) -> None:
        if self.on_position is not None:
            # Frames use legacy notation offsets; the shared editor callback uses bytes.
            frame_end = self._frames[self._index].offset
            offset = next((byte for end, byte in self._source_positions if end >= frame_end), 0)
            self.on_position(offset, "frame")

    def _schedule(self) -> None:
        if self._render_id is None:
            self._render_id = self.after(60, self._draw)

    def _draw(self) -> None:
        self._render_id = None
        if not self._frames:
            self._canvas.configure(image="", text="Nothing to show", foreground="white")
            self._status.configure(text="")
            return
        frame = self._frames[self._index]
        try:
            image = render(typed(frame, self._reveal) if self._reveal is not None else frame, self.assets)
            error = ""
        except (OSError, ValueError, KeyError, IndexError) as exc:
            image = Image.new("RGBA", SCENE_SIZE, (0, 0, 0, 255))
            error = f"  ·  preview error: {exc}"
        width = max(160, self._canvas.winfo_width() - 4)
        height = max(120, self._canvas.winfo_height() - 4)
        shown = WIDE_SIZE if self._wide.get() else SCENE_SIZE
        scale = min(width / shown[0], height / shown[1])
        size = (max(1, int(shown[0] * scale)), max(1, int(shown[1] * scale)))
        self._photo = ImageTk.PhotoImage(image.resize(size, Image.LANCZOS))
        self._canvas.configure(image=self._photo, text="")
        kind = {"wait": "waits for A", "suspend": "suspended (script resumes it)", "end": "end of the message"}
        self._status.configure(text=f"Page {self._index + 1} / {len(self._frames)}  ·  {kind.get(frame.kind, frame.kind)}"
                                    f"{('  ·  ' + frame.layout) if frame.layout else ''}{error}")
