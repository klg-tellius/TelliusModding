"""Guided hub creation using the chapter builder's tile canvas."""

from __future__ import annotations

import tkinter as tk
from tkinter import messagebox, ttk

from .. import chapters, hub
from ..hub_creation import GRASS, MAX_SIZE, MIN_SIZE
from .map_builder import _BuildCanvas
from .widgets import info, tip


class GuidedHubDialog(tk.Toplevel):
    """Collect a complete hub setup before creating or editing project files."""

    def __init__(self, parent, *, ids: list[str], destination_ids: list[str], free: list[int], titles: dict[str, str],
                 avatars: dict[str, str], starters: dict[str, str], saved: dict | None = None,
                 size: tuple[int, int] | None = None, terrain: list | None = None, map_info=None):
        """``map_info(chapter_id)`` gives a template chapter's ``(size, terrain)``, to place the
        links on its map when the hub copies it."""
        super().__init__(parent)
        self._map_info = map_info
        self._keep_map = tk.BooleanVar(value=map_info is not None and not saved)
        self.title("Edit hub" if saved else "Create hub")
        self.geometry("1100x750")
        self.minsize(900, 600)
        self.result = None
        self.empty_text = "Choose map dimensions."
        self._saved = saved
        self._titles = titles
        self._terrain = terrain
        self._starters = starters
        self._avatars = avatars
        self._destinations = [dict(d) for d in saved.get("destinations", [])] if saved else []
        self._current = None
        self._tool = tk.StringVar(value="destination")
        self._chapter = tk.StringVar(value=f"{saved['chapter']:02d}" if saved else f"{free[0]:02d}" if free else "")
        self._title = tk.StringVar(value=titles.get(self._chapter.get(), "Hub"))
        self._activation = tk.StringVar(value=f"{saved['activation_chapter']:02d}" if saved else "01")
        self._avatar = tk.StringVar(value=next((label for label, pid in avatars.items()
                                               if saved and pid == saved.get("avatar_pid")),
                                              next(iter(avatars), "")))
        self._starter = tk.StringVar(value=next(iter(starters), ""))
        self._width = tk.StringVar(value=str(size[0] if size else 16))
        self._height = tk.StringVar(value=str(size[1] if size else 12))
        self._start = (tuple(1 if saved.get(key) is None else saved[key]
                             for key in ("start_x", "start_y")) if saved else (1, 1))
        self._new_destination = tk.StringVar()
        self._description = tk.StringVar()
        self._build(ids, destination_ids, free)
        if not saved:
            self._starter_changed()
        self._redraw()
        self.transient(parent.winfo_toplevel())
        self.grab_set()

    def _build(self, ids, destination_ids, free):
        top = ttk.Frame(self, padding=12)
        top.pack(fill="x")
        ttk.Label(top, text="Hub chapter").grid(row=0, column=0, sticky="w")
        box = ttk.Combobox(top, textvariable=self._chapter, values=[f"{n:02d}" for n in free],
                           state="disabled" if self._saved else "readonly", width=8)
        box.grid(row=0, column=1, sticky="w", padx=6)
        ttk.Label(top, text="Title").grid(row=0, column=2, sticky="w", padx=(14, 0))
        ttk.Entry(top, textvariable=self._title, width=22,
                  state="disabled" if self._saved else "normal").grid(row=0, column=3, sticky="w", padx=6)
        ttk.Label(top, text="Activate after").grid(row=0, column=4, sticky="w", padx=(14, 0))
        ttk.Combobox(top, textvariable=self._activation, values=ids, state="readonly", width=8).grid(
            row=0, column=5, sticky="w", padx=6)
        ttk.Label(top, text="Avatar").grid(row=1, column=0, sticky="w", pady=8)
        ttk.Combobox(top, textvariable=self._avatar, values=list(self._avatars), state="readonly", width=28).grid(
            row=1, column=1, columnspan=2, sticky="w", padx=6)
        if not self._saved:
            tip(ttk.Label(top, text="Template chapter"),
                "The new hub is a copy of this chapter, like Add chapter makes: its chapter data, map and "
                "assets. Its units are replaced by the avatar and its events by the hub's.").grid(
                row=1, column=3, sticky="w")
            starter = ttk.Combobox(top, textvariable=self._starter, values=list(self._starters), state="readonly",
                                   width=28)
            starter.grid(row=1, column=4, columnspan=2, sticky="w", padx=6)
            starter.bind("<<ComboboxSelected>>", lambda e: self._starter_changed())
        sizes = ttk.Frame(top)
        sizes.grid(row=2, column=0, columnspan=6, sticky="w")
        if not self._saved and self._map_info is not None:
            ttk.Radiobutton(sizes, text="Copy the template's map", variable=self._keep_map, value=True,
                            command=self._starter_changed).pack(side="left")
            ttk.Radiobutton(sizes, text="Blank map", variable=self._keep_map, value=False,
                            command=self._starter_changed).pack(side="left", padx=(12, 6))
        self._size_entries = []
        for var in (self._width, self._height):
            entry = ttk.Entry(sizes, textvariable=var, width=5, state="disabled" if self._saved else "normal")
            entry.pack(side="left", padx=(0, 4))
            self._size_entries.append(entry)
            var.trace_add("write", lambda *_: self._redraw())
        tip(ttk.Label(sizes, text="tiles", style="Muted.TLabel"),
            f"Width × height of a blank map: {MIN_SIZE}–{MAX_SIZE} tiles per side, flat grass.").pack(side="left")

        middle = ttk.PanedWindow(self, orient="horizontal")
        middle.pack(fill="both", expand=True, padx=12)
        map_frame = ttk.Frame(middle)
        middle.add(map_frame, weight=4)
        tools = ttk.Frame(map_frame)
        tools.pack(fill="x", pady=(0, 6))
        for value, label in (("avatar", "Place avatar"), ("destination", "Place chapter link"),
                             ("return", "Place return point")):
            ttk.Radiobutton(tools, text=label, variable=self._tool, value=value).pack(side="left", padx=(0, 12))
        self._canvas = _BuildCanvas(map_frame, self)
        ybar = ttk.Scrollbar(map_frame, orient="vertical", command=self._canvas.yview)
        xbar = ttk.Scrollbar(map_frame, orient="horizontal", command=self._canvas.xview)
        self._canvas.configure(yscrollcommand=ybar.set, xscrollcommand=xbar.set)
        xbar.pack(side="bottom", fill="x")
        ybar.pack(side="right", fill="y")
        self._canvas.pack(fill="both", expand=True)
        self._canvas.show.update({"terrain": True, "image": False})
        self._hint = ttk.Label(map_frame, text="Click a tile with a placement tool. Middle-drag pans; Ctrl+wheel zooms.")
        self._hint.pack(anchor="w", pady=4)

        side = ttk.Frame(middle, padding=(12, 0, 0, 0))
        middle.add(side, weight=2)
        ttk.Label(side, text="Linked chapters").pack(anchor="w")
        self._list = tk.Listbox(side, height=10, exportselection=False)
        self._list.pack(fill="both", expand=True, pady=(4, 6))
        self._list.bind("<<ListboxSelect>>", self._selected)
        for item in self._destinations:
            self._list.insert("end", self._label(item))
        choices = ttk.Frame(side)
        choices.pack(fill="x")
        available = {chapters.chapter_display_title(cid, self._titles) + f" ({cid})": int(cid)
                     for cid in destination_ids if cid.isdigit() and int(cid) != int(self._chapter.get())}
        self._choices = available
        self._new_destination.set(next(iter(available), ""))
        ttk.Combobox(choices, textvariable=self._new_destination, values=list(available), state="readonly").pack(
            side="left", fill="x", expand=True)
        ttk.Button(choices, text="Add", command=self._add).pack(side="left", padx=(4, 0))
        ttk.Button(side, text="Remove selected", command=self._remove).pack(anchor="w", pady=(6, 12))
        ttk.Label(side, text="Optional short description (Visit action)").pack(anchor="w")
        ttk.Entry(side, textvariable=self._description).pack(fill="x", pady=(4, 8))
        self._description.trace_add("write", lambda *_: self._set_description())
        self._placement = ttk.Label(side, text="Select a linked chapter to place its tile and return point.",
                                    wraplength=300, justify="left")
        self._placement.pack(anchor="w")
        info(side, "Each linked chapter gets an action tile with two commands: Arrive enters the chapter, Visit "
                   "shows its description and stays in the hub. After the chapter, the avatar comes back on the "
                   "return point.").pack(anchor="w", pady=(16, 0))
        bottom = ttk.Frame(self, padding=12)
        bottom.pack(fill="x")
        ttk.Button(bottom, text="Cancel", command=self.destroy).pack(side="right")
        ttk.Button(bottom, text="Save hub" if self._saved else "Create hub", command=self._accept).pack(
            side="right", padx=(0, 8))

    def _starter_changed(self) -> None:
        """Show the template's map (size and terrain) when the hub copies it."""
        keep = self._keep_map.get() and self._map_info is not None
        for entry in self._size_entries:
            entry.configure(state="disabled" if keep or self._saved else "normal")
        if keep:
            source = self._starters.get(self._starter.get())
            found = self._map_info(source) if source else None
            if found is not None:
                (width, height), self._terrain = found
                self._width.set(str(width))
                self._height.set(str(height))
        elif not self._saved:
            self._terrain = None
        self._redraw()

    def _dimensions(self):
        try:
            width, height = int(self._width.get()), int(self._height.get())
        except ValueError:
            return None
        if self._keep_map.get() and not self._saved:
            return (width, height) if width > 0 and height > 0 else None
        return (width, height) if MIN_SIZE <= width <= MAX_SIZE and MIN_SIZE <= height <= MAX_SIZE else None

    def _label(self, item):
        title = chapters.chapter_display_title(f"{item['chapter']:02d}", self._titles)
        tile = "place tile" if item.get("x") is None else f"({item['x']}, {item['y']})"
        return f"{item['chapter']:02d} · {title} — {tile}"

    def _add(self):
        chapter = self._choices.get(self._new_destination.get())
        if chapter is None or any(item["chapter"] == chapter for item in self._destinations):
            return
        item = {"chapter": chapter, "x": None, "y": None, "return_x": None, "return_y": None,
                "description": ""}
        self._destinations.append(item)
        self._list.insert("end", self._label(item))
        self._list.selection_clear(0, "end")
        self._list.selection_set("end")
        self._selected()

    def _remove(self):
        if self._current is None:
            return
        self._destinations.pop(self._current)
        self._list.delete(self._current)
        self._current = None
        self._description.set("")
        self._redraw()

    def _selected(self, _event=None):
        selected = self._list.curselection()
        self._current = selected[0] if selected else None
        self._description.set(self._destinations[self._current].get("description", "") if selected else "")
        self._redraw()

    def _set_description(self):
        if self._current is not None:
            self._destinations[self._current]["description"] = self._description.get()

    def _redraw(self):
        if not hasattr(self, "_canvas"):
            return
        dimensions = self._dimensions()
        self._canvas.size = dimensions
        if dimensions is not None:
            w, h = dimensions
            self._canvas.terrain = self._terrain if self._terrain is not None else [[GRASS] * h for _ in range(w)]
            x, y = self._start
            self._canvas.units = ([{"x": x, "y": y, "pos2": (x, y), "color": "#4387d1", "text": "A",
                                   "selected": False, "highlight": False}] if x < w and y < h else [])
            self._canvas.zones = [
                {"function": str(i), "rect": (d["x"], d["y"], d["x"], d["y"]), "area": False,
                 "color": "#7bb85c", "text": f"{d['chapter']:02d}", "selected": i == self._current}
                for i, d in enumerate(self._destinations) if d.get("x") is not None and d["x"] < w and d["y"] < h]
            self._canvas.selected_tiles = {
                (d["return_x"], d["return_y"]) for d in self._destinations
                if d.get("return_x") is not None and d["return_x"] < w and d["return_y"] < h}
        self._canvas.redraw()
        if self._current is not None:
            d = self._destinations[self._current]
            action = "unset" if d.get("x") is None else f"({d['x']}, {d['y']})"
            return_ = "unset" if d.get("return_x") is None else f"({d['return_x']}, {d['return_y']})"
            self._placement.configure(text=f"Action tile: {action} · Return point: {return_}")

    def on_press(self, tile, _event):
        if tile is None:
            return
        tool = self._tool.get()
        if tool == "avatar":
            self._start = tile
        elif self._current is not None:
            item = self._destinations[self._current]
            keys = ("x", "y") if tool == "destination" else ("return_x", "return_y")
            item[keys[0]], item[keys[1]] = tile
            self._list.delete(self._current)
            self._list.insert(self._current, self._label(item))
            self._list.selection_set(self._current)
        self._redraw()

    def on_drag(self, tile, event):
        pass

    def on_release(self, tile, event):
        pass

    def on_right(self, tile, event):
        pass

    def on_hover(self, tile):
        if tile is not None:
            self._hint.configure(text=f"Tile {tile} · {self._tool.get()} placement")

    def _accept(self):
        try:
            dimensions = self._dimensions()
            if dimensions is None:
                raise ValueError(f"Choose a width and height from {MIN_SIZE} to {MAX_SIZE}.")
            if not self._destinations:
                raise ValueError("Add at least one linked chapter.")
            if any(d.get("x") is None or d.get("return_x") is None for d in self._destinations):
                raise ValueError("Place the action tile and return point for every linked chapter.")
            if not self._avatar.get() in self._avatars:
                raise ValueError("Choose a dedicated avatar character.")
            if not self._saved and self._starter.get() not in self._starters:
                raise ValueError("Choose starter map assets.")
            if not self._title.get().isascii():
                raise ValueError("The chapter title must use plain ASCII text.")
            setup = hub.HubSetup(int(self._chapter.get()), int(self._activation.get()),
                                 self._avatars[self._avatar.get()],
                                 tuple(hub.Destination(**d) for d in self._destinations), *self._start)
            self.result = (setup, self._starters.get(self._starter.get()), self._title.get().strip(), dimensions,
                           bool(self._keep_map.get()) and not self._saved)
        except (ValueError, TypeError) as exc:
            messagebox.showerror("Invalid hub", str(exc), parent=self)
            return
        self.destroy()
