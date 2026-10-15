"""Create a hub chapter: a copy of a template chapter whose units are the avatar alone.

The links to other chapters are placed afterwards on the new chapter's Build
tab (``hub_tool.py``), with every other chapter tool at hand.
"""

from __future__ import annotations

import tkinter as tk
from tkinter import messagebox, ttk

from ..hub_creation import MAX_SIZE, MIN_SIZE
from .widgets import info, tip


class CreateHubDialog(tk.Toplevel):
    """``result``: ``(chapter, title, template id, keep_map, (width, height), avatar pid, activation chapter)``."""

    def __init__(self, parent, *, free: list[int], templates: dict[str, str], avatars: dict[str, str],
                 activations: dict[str, int]):
        super().__init__(parent)
        self.title("Create hub")
        self.resizable(False, False)
        self.result = None
        self._templates = templates
        self._avatars = avatars
        self._activations = activations
        self._chapter = tk.StringVar(value=f"{free[0]:02d}" if free else "")
        self._title = tk.StringVar(value="Hub")
        self._template = tk.StringVar(value=next(iter(templates), ""))
        self._keep_map = tk.BooleanVar(value=True)
        self._width = tk.StringVar(value="16")
        self._height = tk.StringVar(value="12")
        self._avatar = tk.StringVar(value=next(iter(avatars), ""))
        self._activation = tk.StringVar(value=next(iter(activations), ""))

        body = ttk.Frame(self, padding=16)
        body.pack(fill="both", expand=True)
        rows = (
            ("Chapter number", ttk.Combobox(body, textvariable=self._chapter, values=[f"{n:02d}" for n in free],
                                            state="readonly", width=8),
             "A free chapter number; the hub stays out of the story order."),
            ("Title", ttk.Entry(body, textvariable=self._title, width=30), ""),
            ("Template chapter", ttk.Combobox(body, textvariable=self._template, values=list(templates),
                                              state="readonly", width=40),
             "The hub is a copy of this chapter, as Add chapter makes: its chapter data, map and assets. Its "
             "units are replaced by the avatar, its events by an empty opening."),
            ("Avatar", ttk.Combobox(body, textvariable=self._avatar, values=list(avatars), state="readonly",
                                    width=40),
             "The character the player walks around the hub with. It must not be deployed in any other "
             "chapter: create one in Game Data › Characters first if none is listed."),
            ("Opens after", ttk.Combobox(body, textvariable=self._activation, values=list(activations),
                                         state="readonly", width=40),
             "The hub opens once this chapter is won."),
        )
        for r, (label, widget, help_text) in enumerate(rows):
            tip(ttk.Label(body, text=label), help_text).grid(row=r, column=0, sticky="w", pady=3, padx=(0, 10))
            widget.grid(row=r, column=1, sticky="w", pady=3)
        r = len(rows)
        tip(ttk.Label(body, text="Map"), "Keep the template's map to decorate it, or start from a flat grass "
                                         "ground and paint it.").grid(row=r, column=0, sticky="nw", pady=3)
        maps = ttk.Frame(body)
        maps.grid(row=r, column=1, sticky="w", pady=3)
        ttk.Radiobutton(maps, text="Copy the template's map", variable=self._keep_map, value=True,
                        command=self._sync).pack(anchor="w")
        blank = ttk.Frame(maps)
        blank.pack(anchor="w", pady=(2, 0))
        ttk.Radiobutton(blank, text="Blank map", variable=self._keep_map, value=False,
                        command=self._sync).pack(side="left")
        self._size_entries = []
        for var in (self._width, self._height):
            entry = ttk.Entry(blank, textvariable=var, width=4)
            entry.pack(side="left", padx=(6, 0))
            self._size_entries.append(entry)
        tip(ttk.Label(blank, text="tiles", style="Muted.TLabel"),
            f"Width × height: {MIN_SIZE}–{MAX_SIZE} tiles per side.").pack(side="left", padx=(4, 0))
        note = ttk.Frame(body)
        note.grid(row=r + 1, column=0, columnspan=2, sticky="w", pady=(10, 0))
        ttk.Label(note, text="The chapter then opens on its Build tab, with the Hub tool.",
                  style="Muted.TLabel").pack(side="left")
        info(note, "On the Build tab the Hub tool places the links to other chapters: an action tile each "
                   "(Arrive enters the chapter, Visit shows its description) and the tile the avatar comes "
                   "back to. Install hub then writes the events and the chapter routing.").pack(
            side="left", padx=(6, 0))
        bottom = ttk.Frame(self, padding=(16, 0, 16, 16))
        bottom.pack(fill="x")
        ttk.Button(bottom, text="Cancel", command=self.destroy).pack(side="right")
        ttk.Button(bottom, text="Create hub", style="Accent.TButton", command=self._accept).pack(
            side="right", padx=(0, 8))
        self._sync()
        self.transient(parent.winfo_toplevel())
        self.grab_set()

    def _sync(self) -> None:
        for entry in self._size_entries:
            entry.configure(state="disabled" if self._keep_map.get() else "normal")

    def _accept(self) -> None:
        try:
            if not self._chapter.get():
                raise ValueError("No free chapter number from 33 to 89.")
            title = self._title.get().strip()
            if not title or not title.isascii():
                raise ValueError("The chapter title must be plain ASCII text.")
            if self._template.get() not in self._templates:
                raise ValueError("Choose a template chapter.")
            if self._avatar.get() not in self._avatars:
                raise ValueError("Choose the avatar.")
            if self._activation.get() not in self._activations:
                raise ValueError("Choose the chapter after which the hub opens.")
            size = None
            if not self._keep_map.get():
                try:
                    size = int(self._width.get()), int(self._height.get())
                except ValueError:
                    size = None
                if size is None or not all(MIN_SIZE <= n <= MAX_SIZE for n in size):
                    raise ValueError(f"A blank map is {MIN_SIZE} to {MAX_SIZE} tiles per side.")
        except ValueError as exc:
            messagebox.showerror("Create hub", str(exc), parent=self)
            return
        self.result = (int(self._chapter.get()), title, self._templates[self._template.get()],
                       bool(self._keep_map.get()), size, self._avatars[self._avatar.get()],
                       self._activations[self._activation.get()])
        self.destroy()
