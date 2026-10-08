"""FE9 preview, with the earlier FE10 implementation kept separate."""
from __future__ import annotations

import time
import tkinter as tk
from tkinter import ttk
from PIL import Image, ImageTk
from ..game_profile import DIALOGUE, profile_of
from ..formats.fe9_conversation import InitialContext, build_timeline
from ..formats.fe9_conversation_assets import ConversationAssets
from ..formats.fe9_conversation_render import ConversationRenderer, SCENE_SIZE
from ..formats.fe9_message_scene import layout_from_label, layout_label
from .scene_editor import layout_labels


def ConversationPreview(parent, project):
    if not profile_of(project).supports(DIALOGUE):
        from .legacy_conversation_preview import ConversationPreview as LegacyPreview
        return LegacyPreview(parent, project)
    return FE9ConversationPreview(parent, project)


class FE9ConversationPreview(ttk.Frame):
    def __init__(self, parent, project):
        super().__init__(parent)
        self._project = project
        self._assets = self._renderer = None
        self._timeline = build_timeline("")
        self._index, self._clock = 0, 0.0
        self._playing = False
        self._after_id = self._render_id = None
        self._photo = self._message_id = None
        self._text = self._speaker = ""
        self._syncing = False
        self.on_position = None
        self.context_description = ""
        self.on_inheritance = None
        self.on_context_changed = None
        self._inherit_source = tk.StringVar()
        self._inherit_error = ""
        self._reset_position = True
        self._auto = tk.BooleanVar(value=True)
        self._position = tk.DoubleVar(value=0)
        self._context_open = tk.BooleanVar(value=False)
        self._layout = tk.StringVar(value=layout_label("上下会話"))
        self._background = tk.StringVar()
        self._portraits = [tk.StringVar() for _ in range(9)]
        self._aliases = {key: tk.StringVar() for key in ("ME", "LME", "IKE", "L_IKE", "VOKE", "L_VOKE")}
        controls = ttk.Frame(self)
        controls.pack(fill="x")
        self._play = ttk.Button(controls, text="Play", width=9, command=self._toggle_play)
        self._play.pack(side="left")
        for label, callback in (("Restart", self._restart), ("Previous page", self._previous),
                                ("Next page", self._next), ("Step", self._step)):
            ttk.Button(controls, text=label, command=callback).pack(side="left", padx=(4, 0))
        ttk.Checkbutton(controls, text="Auto-advance", variable=self._auto).pack(side="left", padx=4)
        # The game's Message Speed option: frames per glyph (Slow 10, Normal 4, Fast 1, Max = page).
        self._speed = tk.StringVar(value="Normal")
        ttk.Label(controls, text="Message speed").pack(side="left", padx=(8, 2))
        speed = ttk.Combobox(controls, textvariable=self._speed, values=("Slow", "Normal", "Fast", "Max"),
                             state="readonly", width=7)
        speed.pack(side="left")
        speed.bind("<<ComboboxSelected>>", lambda event: self._rebuild())
        ttk.Button(controls, text="Reload assets", command=self._reload).pack(side="right")
        self._status = ttk.Label(self)
        self._status.pack(anchor="w", pady=(3, 0))
        self._scale = ttk.Scale(self, from_=0, to=1, variable=self._position, command=self._seek)
        self._scale.pack(fill="x")
        inheritance = ttk.Frame(self)
        inheritance.pack(fill="x", pady=(2, 4))
        ttk.Label(inheritance, text="Inherit from message:").pack(side="left")
        self._inherit_entry = ttk.Combobox(inheritance, textvariable=self._inherit_source, width=30)
        self._inherit_entry.pack(side="left", fill="x", expand=True, padx=4)
        self._inherit_entry.bind("<Return>", lambda event: self._apply_inheritance())
        self._inherit_entry.bind("<<ComboboxSelected>>", lambda event: self._apply_inheritance())
        ttk.Button(inheritance, text="Apply", command=self._apply_inheritance).pack(side="left")
        ttk.Button(inheritance, text="Auto", command=lambda: self._apply_inheritance(automatic=True)).pack(side="left", padx=(4,0))
        ttk.Checkbutton(self, text="Initial scene context", variable=self._context_open,
                        command=self._show_context).pack(anchor="w")
        self._context = ttk.Frame(self, padding=4)
        ttk.Label(self._context, text="For context inherited from earlier events; resets when selecting another message.").grid(row=0, column=0, columnspan=6, sticky="w")
        ttk.Label(self._context, text="Layout").grid(row=1, column=0, sticky="w")
        self._layout_combo = ttk.Combobox(self._context, textvariable=self._layout, width=30)
        self._layout_combo.grid(row=1, column=1, columnspan=2, sticky="ew")
        ttk.Label(self._context, text="Background RID").grid(row=1, column=3, sticky="w")
        ttk.Entry(self._context, textvariable=self._background, width=25).grid(row=1, column=4, columnspan=2, sticky="ew")
        for i, var in enumerate(self._portraits):
            row, column = 2+i//3, (i%3)*2
            ttk.Label(self._context, text=f"Seat {i}").grid(row=row, column=column, sticky="w")
            ttk.Entry(self._context, textvariable=var, width=17).grid(row=row, column=column+1, sticky="ew")
        for i, (key, var) in enumerate(self._aliases.items()):
            row, column = 5+i//3, (i%3)*2
            ttk.Label(self._context, text=key+" →").grid(row=row, column=column, sticky="w")
            ttk.Entry(self._context, textvariable=var, width=17).grid(row=row, column=column+1, sticky="ew")
        ttk.Button(self._context, text="Apply context", command=self._rebuild).grid(row=7, column=0, columnspan=2, sticky="w")
        ttk.Button(self._context, text="Reset context", command=self._reset_and_rebuild).grid(row=7, column=2, columnspan=2, sticky="w")
        self._canvas = tk.Canvas(self, width=608, height=448, background="#17191d", highlightthickness=0)
        self._canvas.pack(fill="both", expand=True, pady=(3, 0))
        self._canvas.bind("<Configure>", lambda event: self._schedule_render())
        self._canvas.bind("<Button-1>", lambda event: self._next())
        self._diagnostics = tk.Text(self, height=3, wrap="word", font=("Segoe UI", 9), borderwidth=0,
                                   background="#f4f4f4", foreground="#824718", state="disabled")
        self._diagnostics.pack(fill="x", pady=(3, 0))
        self.bind("<Destroy>", self._destroyed)
        self._reload()

    def _destroyed(self, event):
        if event.widget is self:
            self.cleanup()

    def _show_context(self):
        if self._context_open.get():
            self._context.pack(fill="x", before=self._canvas)
        else:
            self._context.pack_forget()

    @property
    def assets(self):
        return self._assets

    def current_context(self):
        return self._get_context()

    def seek_before(self, offset):
        """Show the scene after every command before source byte `offset`."""
        self._goto(max((e.index for e in self._timeline.events if e.source_offset < offset), default=0))

    def _get_context(self):
        return InitialContext(layout_from_label(self._layout.get()), self._background.get().strip(),
                              tuple(v.get().strip() for v in self._portraits),
                              tuple((k, v.get().strip()) for k, v in self._aliases.items() if v.get().strip()))

    def _reset_context(self):
        self._layout.set(layout_label("上下会話"))
        self._background.set("")
        for var in [*self._portraits, *self._aliases.values()]:
            var.set("")

    def _reset_and_rebuild(self):
        self._reset_context()
        self._inherit_source.set("")
        self.context_description = "No inherited message context"
        self._rebuild()

    def set_inheritance_source(self, sources=(), choices=()):
        self._inherit_source.set(sources[0] if sources else "")
        self._inherit_entry.configure(values=tuple(choices))
        self._inherit_error = ""

    def _apply_inheritance(self, automatic=False):
        if self.on_inheritance is None:
            return
        try:
            resolution = self.on_inheritance(None if automatic else self._inherit_source.get().strip())
            if resolution.context is None:
                raise ValueError(resolution.description)
        except Exception as error:
            self._inherit_error = str(error)
            self._render()
            return
        self._inherit_error = ""
        self._inherit_source.set(resolution.sources[0] if resolution.sources else "")
        self.context_description = resolution.description
        self._reset_context()
        self._reset_position = True
        self.update_message(self._speaker, self._text, resolution.context, message_id=self._message_id)

    def update_message(self, speaker, text, context=None, *, message_id=None):
        key = message_id if message_id is not None else speaker
        if key != self._message_id:
            self._reset_context()
            self._inherit_source.set("")
            self._inherit_error = ""
            self._reset_position = True
        self._message_id = key
        if context is not None:
            self._layout.set(layout_label(context.layout))
            self._background.set(context.background)
            for var, fid in zip(self._portraits, context.portraits):
                var.set(fid)
            for key, value in context.aliases:
                if key.removeprefix("FID_") in self._aliases:
                    self._aliases[key.removeprefix("FID_")].set(value)
        self._speaker, self._text = speaker, text
        self._rebuild()

    def _reload(self):
        self._stop()
        try:
            self._assets = ConversationAssets(self._project.extracted_dir)
            self._renderer = ConversationRenderer(self._assets)
            self._layout_combo.configure(values=layout_labels(self._assets))
        except Exception as error:
            self._assets = self._renderer = None
            self._set_diagnostics([str(error)])
            return
        self._rebuild()

    def _rebuild(self):
        self._stop()
        if self._renderer is None:
            return
        old_offset = self._timeline.events[self._index].source_offset
        context = self._get_context()
        if context != getattr(self, "_last_context", None):
            self._last_context = context
            if self.on_context_changed is not None:
                self.on_context_changed(context)
        try:
            if self._assets.refresh():
                self._renderer.invalidate()
            self._timeline = build_timeline(self._text, context=context, measure=self._renderer.measure,
                                            text_speed=self._speed.get().lower())
        except Exception as error:
            self._timeline = build_timeline("")
            self._index, self._clock = 0, 0.0
            self._set_diagnostics([str(error)])
            self._canvas.delete("all")
            return
        self._index = 0 if self._reset_position else max((e.index for e in self._timeline.events
                                                        if e.source_offset <= old_offset), default=0)
        self._reset_position = False
        self._clock = float(self._timeline.events[self._index].time_ms)
        self._scale.configure(to=max(1, len(self._timeline.events)-1))
        self._render()

    def _stop(self):
        self._playing = False
        if self._after_id is not None:
            self.after_cancel(self._after_id)
            self._after_id = None

    def _toggle_play(self):
        if self._playing:
            self._stop()
            self._render()
            return
        if self._renderer is None:
            return
        if self._assets.refresh():
            self._rebuild()
        if self._index >= len(self._timeline.events)-1:
            self._restart()
        self._playing = True
        self._last_tick = time.monotonic()
        self._tick()

    def _tick(self):
        self._after_id = None
        if not self._playing:
            return
        current = time.monotonic()
        self._clock += min(0.1, current-self._last_tick)*1000
        self._last_tick = current
        previous_index = self._index
        self._index = self._timeline.advance(self._index, int(self._clock), stop_at_wait=True)
        event = self._timeline.events[self._index]
        if event.wait and self._index != previous_index:
            self._clock = float(event.time_ms)
            if self._auto.get():
                self._render()
                self._after_id = self.after(900, self._resume_auto)
                return
            self._playing = False
        if self._index == len(self._timeline.events)-1:
            self._playing = False
        self._render()
        if self._playing:
            self._after_id = self.after(16, self._tick)

    def _resume_auto(self):
        self._after_id = None
        if self._playing:
            self._last_tick = time.monotonic()
            self._tick()

    def _goto(self, index):
        self._stop()
        self._index = max(0, min(index, len(self._timeline.events)-1))
        self._clock = float(self._timeline.events[self._index].time_ms)
        self._render()

    def _restart(self):
        self._goto(0)

    def _step(self):
        self._goto(self._index+1)

    def _next(self):
        self._goto(next((e.index for e in self._timeline.events[self._index+1:] if e.wait), len(self._timeline.events)-1))

    def _previous(self):
        self._goto(next((e.index for e in reversed(self._timeline.events[:self._index]) if e.wait), 0))

    def _seek(self, value):
        if not self._syncing:
            self._goto(round(float(value)))

    def _set_diagnostics(self, lines):
        value = "\n".join(dict.fromkeys(lines))
        if self._diagnostics.get("1.0", "end-1c") == value:
            return
        self._diagnostics.configure(state="normal")
        self._diagnostics.delete("1.0", "end")
        self._diagnostics.insert("1.0", value)
        self._diagnostics.configure(state="disabled")

    def _schedule_render(self):
        if self._render_id is None:
            self._render_id = self.after_idle(self._render)

    def _render(self):
        if self._render_id is not None:
            self.after_cancel(self._render_id)
            self._render_id = None
        if self._renderer is None:
            return
        event = self._timeline.events[self._index]
        if self.on_position is not None:
            self.on_position(event.source_offset, event.kind)
        result = self._renderer.render(event, time_ms=int(self._clock))
        width, height = max(1, self._canvas.winfo_width()), max(1, self._canvas.winfo_height())
        scale = min(width/SCENE_SIZE[0], height/SCENE_SIZE[1])
        size = (max(1, round(SCENE_SIZE[0]*scale)), max(1, round(SCENE_SIZE[1]*scale)))
        self._photo = ImageTk.PhotoImage(result.image.resize(size, Image.Resampling.LANCZOS))
        self._canvas.delete("all")
        self._canvas.create_image(width//2, height//2, image=self._photo)
        self._syncing = True
        self._position.set(self._index)
        self._syncing = False
        page = sum(e.wait for e in self._timeline.events[:self._index+1])
        pages = sum(e.wait for e in self._timeline.events)
        flags = ("" if event.state.skippable else "   B skip off") + ("   script released" if event.state.script_released else "")
        self._status.configure(text=f"{self._speaker}   Page {max(1,page)}/{max(1,pages)}   {event.time_ms/1000:.2f}s   {event.kind}{flags}")
        self._play.configure(text="Pause" if self._playing else "Continue" if event.wait else "Play")
        self._set_diagnostics(([self._inherit_error] if self._inherit_error else []) +
                              ([self.context_description] if self.context_description else []) +
                              [f"Byte {d.offset}: {d.description}" for d in (*self._timeline.diagnostics, *result.diagnostics)])

    def cleanup(self):
        self._stop()
        if self._render_id is not None:
            self.after_cancel(self._render_id)
            self._render_id = None
