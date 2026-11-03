"""A table of every icon on one image of ``window/icon.tpl`` to pick an
item's or a skill's icon from, instead of typing its number."""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Callable, Optional

from PIL import Image, ImageTk

from ..formats import icons
from .widgets import ScrollFrame, tip

COLUMNS = 16


class IconPickerDialog(tk.Toplevel):
    """``values`` are the icon numbers to offer, ``cell_of(value)`` the sheet
    cell each draws and ``users(value)`` the records already using it (shown
    on hover). ``result`` is the chosen value, or None when cancelled."""

    def __init__(self, parent: tk.Misc, title: str, images: list, image_index: int, size: int, values: list[int],
                 cell_of: Callable[[int], Optional[int]], current: Optional[int],
                 users: Callable[[int], list[str]]):
        super().__init__(parent)
        self.title(title)
        self.transient(parent)
        self.result: Optional[int] = None
        self._photos = []
        self._query = tk.StringVar()
        top = ttk.Frame(self, padding=(10, 10, 10, 4))
        top.pack(fill="x")
        ttk.Label(top, text="Filter").pack(side="left")
        entry = ttk.Entry(top, textvariable=self._query, width=28)
        entry.pack(side="left", padx=(6, 0))
        tip(entry, "Type an icon number or the name of an item or skill that uses it.")
        ttk.Label(top, text="Click an icon to use it. Hover one to see what already uses it.",
                  style="Muted.TLabel").pack(side="left", padx=(12, 0))
        scroll = ScrollFrame(self, padding=(10, 4, 10, 10))
        scroll.pack(fill="both", expand=True)
        self._grid = scroll.body
        self._cells = []
        scale = 2 if size <= 24 else 1.5
        for value in values:
            image = icons.cell_image(images, image_index, cell_of(value), size)
            if image is None and cell_of(value) is not None:
                continue
            names = users(value)
            frame = tk.Frame(self._grid, borderwidth=2, relief="solid" if value == current else "flat",
                             highlightthickness=0, cursor="hand2")
            if image is not None:
                backing = Image.new("RGBA", image.size, (96, 96, 96, 255))
                backing.alpha_composite(image)
                photo = ImageTk.PhotoImage(backing.resize((int(size * scale), int(size * scale)), Image.NEAREST))
                self._photos.append(photo)
                picture = tk.Label(frame, image=photo, borderwidth=0)
            else:
                picture = tk.Label(frame, text="none", width=6, height=3)
            picture.pack()
            caption = tk.Label(frame, text=str(value), font=("Segoe UI", 8))
            caption.pack()
            text = f"Icon {value}" + (": " + ", ".join(names) if names else ": unused")
            for widget in (frame, picture, caption):
                widget.bind("<Button-1>", lambda e, v=value: self._choose(v))
                tip(widget, text)
            self._cells.append((value, " ".join(names).casefold(), frame))
        self._query.trace_add("write", lambda *_: self._layout())
        self._layout()
        ttk.Button(self, text="Cancel", command=self.destroy).pack(anchor="e", padx=10, pady=(0, 10))
        self.geometry("1000x660")
        self.bind("<Escape>", lambda e: self.destroy())
        entry.focus_set()
        self.grab_set()

    def _layout(self) -> None:
        words = self._query.get().casefold().split()
        shown = 0
        for value, haystack, frame in self._cells:
            frame.grid_forget()
            if all(w == str(value) or w in haystack for w in words):
                frame.grid(row=shown // COLUMNS, column=shown % COLUMNS, padx=2, pady=2)
                shown += 1

    def _choose(self, value: int) -> None:
        self.result = value
        self.destroy()
