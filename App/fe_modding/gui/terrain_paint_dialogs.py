"""Dialogs of the Blender terrain sculpt & paint workflow (:mod:`terrain_kit`).

- :class:`PaintKitDialog`: options of a new terrain kit;
- :class:`PaintImportOptions`: options of importing a painted kit;
- :class:`AtlasSwatchesDialog`: the atlas swatch table of a map, saved per
  project, and the atlas builder for custom swatches;
- :class:`WaterImportOptions`: a kit's water: donor map and tile repaint;
- :func:`add_texturing_tab`, :func:`add_water_tab`: the import review's
  top-down views.
"""

from __future__ import annotations

import queue
import hashlib
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

import numpy as np
from PIL import Image, ImageTk

from .. import terrain_kit
from .. import terrain_paint as tp

SPACINGS = (("1 unit (fine, slow)", 1.0), ("2 units", 2.0), ("4 units (coarse)", 4.0))
LIGHT_CHOICES = (
    ("kit", "The kit's light overlay (as painted or baked in Blender)"),
    ("current", "The map's current light overlay (made for the old ground)"),
    ("white", "None (white)"),
)

# Decoded atlas comparisons are stable until a map container or project
# custom atlas changes. Keeping the result makes reopening Create new map
# instantaneous as well as non-blocking on its first open.
_TILESET_SCAN_CACHE: dict[tuple, tuple] = {}


class NewMapKitDialog(tk.Toplevel):
    """Options for a flat, from-scratch terrain kit.

    ``result`` is ``(size, grid_width, grid_height, offset_x, offset_y,
    include_water, tileset_path, project_tileset_key)``. Dimensions and offsets are in tiles;
    the kit converts them to the game's five model units per tile.
    """

    def __init__(self, parent, maps: list[tuple[str, Path]], current: Path | None = None,
                 project_dir: Path | None = None) -> None:
        super().__init__(parent)
        self.title("Create new map")
        self.transient(parent)
        self.result: tuple | None = None
        self._maps: list[tuple[str, Path, str | None]] = []
        self._raw_maps = maps
        self._current = current
        self._project_dir = Path(project_dir) if project_dir is not None else None
        self._atlas_by_path: dict[Path, Image.Image] = {}
        body = ttk.Frame(self, padding=12)
        body.pack(fill="both", expand=True)
        ttk.Label(
            body,
            text=("Create a flat Blender terrain kit. Size is the square ground; Grid is the playable "
                  "rectangle; Offset places its top-left corner within the ground. One tile is 5 model units."),
            wraplength=580, justify="left",
        ).grid(row=0, column=0, columnspan=4, sticky="w", pady=(0, 10))

        self._size = tk.StringVar(value="32")
        self._grid_w = tk.StringVar(value="24")
        self._grid_h = tk.StringVar(value="20")
        self._offset_x = tk.StringVar(value="4")
        self._offset_y = tk.StringVar(value="6")
        fields = (
            ("Ground size", self._size, "tiles square"),
            ("Grid width", self._grid_w, "tiles"),
            ("Grid height", self._grid_h, "tiles"),
            ("Grid offset X", self._offset_x, "tiles from left"),
            ("Grid offset Y", self._offset_y, "tiles from top"),
        )
        for row, (label, var, unit) in enumerate(fields, 1):
            ttk.Label(body, text=label).grid(row=row, column=0, sticky="w", pady=2)
            ttk.Entry(body, textvariable=var, width=8).grid(row=row, column=1, sticky="w", padx=(8, 4), pady=2)
            ttk.Label(body, text=unit, style="Muted.TLabel").grid(row=row, column=2, sticky="w", pady=2)

        ttk.Label(body, text="Tileset from").grid(row=6, column=0, sticky="w", pady=(10, 2))
        self._tileset = tk.StringVar(value="Finding distinct tilesets…")
        self._tileset_box = ttk.Combobox(body, textvariable=self._tileset,
                                         values=("Finding distinct tilesets…",), state="disabled", width=36)
        self._tileset_box.grid(
            row=6, column=1, columnspan=3, sticky="ew", padx=(8, 0), pady=(10, 2)
        )
        self._tileset_box.bind("<<ComboboxSelected>>", lambda _e: self._request_preview())
        self._water = tk.BooleanVar(value=False)
        ttk.Checkbutton(body, text="Include an editable water surface", variable=self._water).grid(
            row=7, column=0, columnspan=4, sticky="w", pady=(8, 0)
        )
        ttk.Label(
            body,
            text=("Water starts 2 units below the flat ground and covers the square. Sculpt below it, then use "
                  "Cut Shoreline from Terrain in Blender."),
            style="Muted.TLabel", wraplength=560, justify="left",
        ).grid(row=8, column=0, columnspan=4, sticky="w", pady=(2, 0))

        preview = ttk.LabelFrame(body, text="Tileset preview", padding=6)
        preview.grid(row=1, column=4, rowspan=8, sticky="nsew", padx=(18, 0))
        self._preview = ttk.Label(preview, text="Choose a tileset", anchor="center", width=36)
        self._preview.pack(fill="both", expand=True)
        self._preview_photo = None
        self._tileset_results: queue.Queue = queue.Queue()

        buttons = ttk.Frame(body)
        buttons.grid(row=9, column=0, columnspan=5, sticky="e", pady=(14, 0))
        self._create_button = ttk.Button(buttons, text="Create…", style="Accent.TButton",
                                         command=self._ok, state="disabled")
        self._create_button.pack(side="left")
        ttk.Button(buttons, text="Cancel", command=self.destroy).pack(side="left", padx=(6, 0))
        body.grid_columnconfigure(3, weight=1)
        self.protocol("WM_DELETE_WINDOW", self.destroy)
        self.bind("<Escape>", lambda _e: self.destroy())
        self.bind("<Return>", lambda _e: self._ok())
        self.grab_set()
        self._start_tileset_scan()

    def _start_tileset_scan(self) -> None:
        """Find unique decoded atlases without blocking the form opening."""
        self._preview.configure(image="", text=f"Comparing terrain atlases…\n0/{len(self._raw_maps)}")
        stamps = []
        for _label, path in self._raw_maps:
            try:
                stat = path.stat()
                custom = (terrain_kit.custom_atlas_path(self._project_dir, path.parent.name)
                          if self._project_dir is not None else None)
                custom_stat = custom.stat() if custom is not None and custom.is_file() else None
                stamps.append((str(path), stat.st_mtime_ns, stat.st_size,
                               custom_stat.st_mtime_ns if custom_stat else 0,
                               custom_stat.st_size if custom_stat else 0))
            except OSError:
                stamps.append((str(path), 0, 0, 0, 0))
        folder = terrain_kit.tilesets_path(self._project_dir) if self._project_dir is not None else None
        for asset in folder.glob("*.*") if folder is not None and folder.is_dir() else ():
            if asset.suffix.lower() not in {".json", ".png"}:
                continue
            try:
                stat = asset.stat()
                stamps.append((str(asset), stat.st_mtime_ns, stat.st_size, 0, 0))
            except OSError:
                pass
        cache_key = (str(self._current or ""), tuple(stamps))
        cached = _TILESET_SCAN_CACHE.get(cache_key)
        if cached is not None:
            self._tileset_results.put(("done", *cached))
            self.after(10, self._poll_tilesets)
            return

        def worker() -> None:
            groups = {}
            for index, (label, path) in enumerate(self._raw_maps, 1):
                try:
                    custom = (terrain_kit.custom_atlas_path(self._project_dir, path.parent.name)
                              if self._project_dir is not None else None)
                    atlas = (Image.open(custom).convert("RGBA") if custom is not None and custom.is_file()
                             else terrain_kit.read_terrain_atlas(path))
                    signature = hashlib.sha256(
                        f"{atlas.width}x{atlas.height}:".encode("ascii") + atlas.tobytes()
                    ).digest()
                except Exception:  # noqa: BLE001 - non-paintable/open-sea maps are not tileset choices
                    self._tileset_results.put(("progress", index, len(self._raw_maps)))
                    continue
                group = groups.get(signature)
                if group is None:
                    group = groups[signature] = {"label": label, "path": path, "atlas": atlas, "members": [label]}
                else:
                    group["members"].append(label)
                if self._current is not None and path == self._current:
                    group.update(label=label, path=path, atlas=atlas)
                self._tileset_results.put(("progress", index, len(self._raw_maps)))
            choices, atlases, initial = [], {}, None
            for group in sorted(groups.values(), key=lambda item: item["label"].lower()):
                count = len(group["members"])
                display = group["label"] + (f"  ·  {count} maps share this atlas" if count > 1 else "")
                choices.append((display, group["path"], None))
                atlases[group["path"]] = group["atlas"]
                if self._current is not None and group["path"] == self._current:
                    initial = display
            if self._project_dir is not None:
                for saved in terrain_kit.project_tilesets(self._project_dir):
                    source = next((path for _label, path in self._raw_maps
                                   if path.parent.name == saved.source_map), None)
                    if source is None:
                        continue
                    display = f"{saved.name}  ·  Project tileset"
                    choices.insert(0, (display, source, saved.key))
                    atlases[(source, saved.key)] = saved.atlas
            _TILESET_SCAN_CACHE[cache_key] = (choices, atlases, initial)
            self._tileset_results.put(("done", choices, atlases, initial))

        threading.Thread(target=worker, daemon=True).start()
        self.after(50, self._poll_tilesets)

    def _poll_tilesets(self) -> None:
        if not self.winfo_exists():
            return
        try:
            result = self._tileset_results.get_nowait()
        except queue.Empty:
            self.after(100, self._poll_tilesets)
            return
        if result[0] == "progress":
            _kind, done, total = result
            self._preview.configure(image="", text=f"Comparing terrain atlases…\n{done}/{total}")
            self.after(10, self._poll_tilesets)
            return
        _kind, choices, atlases, initial = result
        self._maps = choices
        self._atlas_by_path = atlases
        if not choices:
            self._tileset.set("No paintable terrain atlas found")
            self._preview.configure(image="", text="No map can supply a paintable terrain atlas.")
            return
        labels = [label for label, _path, _key in choices]
        self._tileset_box.configure(values=labels, state="readonly")
        self._tileset.set(initial or labels[0])
        self._create_button.configure(state="normal")
        self._request_preview()

    def _request_preview(self) -> None:
        chosen = next(((path, key) for label, path, key in self._maps if label == self._tileset.get()), None)
        image = (self._atlas_by_path.get(chosen) or self._atlas_by_path.get(chosen[0])) if chosen is not None else None
        if image is None:
            return
        image = image.convert("RGB")
        image.thumbnail((300, 420), Image.LANCZOS)
        self._preview_photo = ImageTk.PhotoImage(image)
        self._preview.configure(image=self._preview_photo, text="")

    def _ok(self) -> None:
        try:
            size, width, height, ox, oy = (
                int(v.get().strip()) for v in
                (self._size, self._grid_w, self._grid_h, self._offset_x, self._offset_y)
            )
        except ValueError:
            messagebox.showerror("Create new map", "Size, grid dimensions and offsets must be whole numbers.", parent=self)
            return
        if not 1 <= size <= 63:
            messagebox.showerror("Create new map", "Ground size must be from 1 to 63 tiles.", parent=self)
            return
        if not 1 <= width <= 63 or not 1 <= height <= 63:
            messagebox.showerror("Create new map", "Grid width and height must each be from 1 to 63 tiles.", parent=self)
            return
        if ox < 0 or oy < 0 or ox + width > size or oy + height > size:
            messagebox.showerror("Create new map", "The complete playable grid must fit inside the square ground.", parent=self)
            return
        chosen = next(((path, key) for label, path, key in self._maps if label == self._tileset.get()), None)
        if chosen is None:
            messagebox.showerror("Create new map", "Choose a map whose terrain tileset should be used.", parent=self)
            return
        self.result = (size, width, height, ox, oy, self._water.get(), chosen[0], chosen[1])
        self.destroy()


class PaintKitDialog(tk.Toplevel):
    """``result``: ``(object_names, sculpt_spacing, from_current)`` or ``None``."""

    def __init__(self, parent, objects: list[str]) -> None:
        super().__init__(parent)
        self.title("Sculpt & paint kit")
        self.transient(parent)
        self.result: tuple | None = None
        body = ttk.Frame(self, padding=10)
        body.pack(fill="both", expand=True)
        ttk.Label(
            body,
            text="Blender opens a sculpt grid seeded from the map's ground, its texture layers and the playable "
                 "tiles. Sculpt FE9 Sculpt, paint the layers from the sidebar's Tellius tab (the add-on is "
                 "installed from Settings > Preferences), save, then use Import .blend/.glb... here.",
            wraplength=560, justify="left",
        ).pack(anchor="w")
        self._from_current = tk.BooleanVar(value=True)
        ttk.Radiobutton(body, text="Start from the map's current painting", variable=self._from_current,
                        value=True).pack(anchor="w", pady=(10, 0))
        ttk.Radiobutton(body, text="Start from the base ground only", variable=self._from_current,
                        value=False).pack(anchor="w")
        row = ttk.Frame(body)
        row.pack(anchor="w", pady=(10, 0))
        ttk.Label(row, text="Sculpt grid spacing").pack(side="left")
        self._spacing = tk.StringVar(value=SPACINGS[1][0])
        ttk.Combobox(row, textvariable=self._spacing, values=[s[0] for s in SPACINGS], state="readonly",
                     width=20).pack(side="left", padx=(6, 0))
        self._objects = objects
        self._list = None
        if objects:
            ttk.Label(body, text="Context objects to include (not exported back):").pack(anchor="w", pady=(10, 0))
            frame = ttk.Frame(body)
            frame.pack(fill="both", expand=True)
            self._list = tk.Listbox(frame, selectmode="multiple", height=min(8, len(objects)), exportselection=False)
            for name in objects:
                self._list.insert("end", name)
            self._list.pack(side="left", fill="both", expand=True)
            scroll = ttk.Scrollbar(frame, command=self._list.yview)
            scroll.pack(side="right", fill="y")
            self._list.config(yscrollcommand=scroll.set)
        buttons = ttk.Frame(body)
        buttons.pack(anchor="e", pady=(10, 0))
        ttk.Button(buttons, text="Continue", command=self._ok).pack(side="left")
        ttk.Button(buttons, text="Cancel", command=self.destroy).pack(side="left", padx=(6, 0))
        self.grab_set()

    def _ok(self) -> None:
        names = [self._objects[i] for i in self._list.curselection()] if self._list is not None else []
        spacing = dict(SPACINGS)[self._spacing.get()]
        self.result = (names, spacing, self._from_current.get())
        self.destroy()


class PaintImportOptions(tk.Toplevel):
    """``result``: ``(follow_heights, conform, light_mode)`` or ``None``."""

    def __init__(self, parent, has_kit_light: bool) -> None:
        super().__init__(parent)
        self.title("Painted terrain import")
        self.transient(parent)
        self.result: tuple | None = None
        body = ttk.Frame(self, padding=10)
        body.pack(fill="both", expand=True)
        ttk.Label(
            body,
            text="The kit's layers are compiled into the game's texturing: two atlas swatches per triangle "
                 "blended by the mask. The Texturing tab of the review shows the result.",
            wraplength=620, justify="left",
        ).pack(anchor="w")
        self._follow = tk.BooleanVar(value=True)
        self._conform = tk.BooleanVar(value=True)
        ttk.Checkbutton(
            body, variable=self._follow,
            text="Move tile heights and props with the new ground (units stand on map.bin's heights)",
        ).pack(anchor="w", pady=(8, 0))
        ttk.Checkbutton(
            body, variable=self._conform,
            text="Fit the playable area to the tile grid (the move grid is drawn flat per tile half)",
        ).pack(anchor="w", pady=(4, 0))
        ttk.Label(body, text="Light overlay:").pack(anchor="w", pady=(8, 0))
        self._light = tk.StringVar(value="kit" if has_kit_light else "current")
        for value, text in LIGHT_CHOICES:
            button = ttk.Radiobutton(body, text=text, variable=self._light, value=value)
            button.pack(anchor="w", padx=(20, 0))
            if value == "kit" and not has_kit_light:
                button.state(["disabled"])
        buttons = ttk.Frame(body)
        buttons.pack(anchor="e", pady=(10, 0))
        ttk.Button(buttons, text="Continue", command=self._ok).pack(side="left")
        ttk.Button(buttons, text="Cancel", command=self.destroy).pack(side="left", padx=(6, 0))
        self.grab_set()

    def _ok(self) -> None:
        self.result = (self._follow.get(), self._conform.get(), self._light.get())
        self.destroy()


def add_texturing_tab(tabs: ttk.Notebook, previews: dict[str, Image.Image], notes: list[str]) -> ttk.Frame:
    """Thumbnails of the compiled terrain (seen from above) and the report."""
    tab = ttk.Frame(tabs, padding=6)
    tabs.add(tab, text="Texturing")
    grid = ttk.Frame(tab)
    grid.pack(anchor="w")
    tab._photos = []  # keep the PhotoImages alive with the tab
    captions = {
        "Game": "What the game draws",
        "Painted": "The layers as painted",
        "Conflicts": "Conflicts (red)",
        "Mask": "Compiled mask",
    }
    for k, (name, image) in enumerate(previews.items()):
        thumb = image.copy()
        thumb.thumbnail((215, 215))
        photo = ImageTk.PhotoImage(thumb)
        tab._photos.append(photo)
        cell = ttk.Frame(grid)
        cell.grid(row=k // 2, column=k % 2, padx=2, pady=2, sticky="n")
        ttk.Label(cell, image=photo).pack()
        ttk.Label(cell, text=captions.get(name, name), style="Muted.TLabel").pack()
    ttk.Label(tab, text="\n".join(notes), wraplength=440, justify="left").pack(anchor="w", pady=(6, 0))
    return tab


class WaterImportOptions(tk.Toplevel):
    """Options of a kit's water: a donor map when the kit adds water or
    shore props the map has no model for, and the tile repaint.
    ``result``: ``(donor_path or None, repaint (water type, land type) or
    None)``, or ``None`` when cancelled."""

    def __init__(self, parent, needs: list[str], donors: list[Path]) -> None:
        super().__init__(parent)
        self.title("Water import")
        self.transient(parent)
        self.result: tuple | None = None
        self._donors = donors
        body = ttk.Frame(self, padding=10)
        body.pack(fill="both", expand=True)
        ttk.Label(
            body,
            text="The kit's water surfaces, shoreline fade, flow and shore waves are written with the terrain. "
                 "The Water tab of the review shows the result.",
            wraplength=560, justify="left",
        ).pack(anchor="w")
        self._donor = tk.StringVar()
        if needs:
            what = " and ".join("water" if n == "water" else f"{n} shore props" for n in needs)
            ttk.Label(body, text=f"The kit adds {what} this map has no model for. Copy them from:",
                      wraplength=560, justify="left").pack(anchor="w", pady=(10, 0))
            names = [p.parent.name for p in donors]
            ttk.Combobox(body, textvariable=self._donor, values=names, state="readonly",
                         width=24).pack(anchor="w", padx=(20, 0), pady=(4, 0))
            if names:
                self._donor.set(names[0])
        self._repaint = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            body, variable=self._repaint,
            text="Repaint the tiles to match the water (a tile is water where you can see water over its centre)",
        ).pack(anchor="w", pady=(10, 0))
        row = ttk.Frame(body)
        row.pack(anchor="w", padx=(20, 0), pady=(4, 0))
        ttk.Label(row, text="Water tiles become").pack(side="left")
        self._water = tk.StringVar(value="River")
        ttk.Combobox(row, textvariable=self._water, values=list(terrain_kit.WATER_TILE_TYPES), state="readonly",
                     width=10).pack(side="left", padx=(6, 12))
        ttk.Label(row, text="dried tiles become").pack(side="left")
        self._land = tk.StringVar(value="Plain")
        ttk.Combobox(row, textvariable=self._land, values=list(terrain_kit.LAND_TILE_TYPES), state="readonly",
                     width=10).pack(side="left", padx=(6, 0))
        self._needs = needs
        buttons = ttk.Frame(body)
        buttons.pack(anchor="e", pady=(10, 0))
        ttk.Button(buttons, text="Continue", command=self._ok).pack(side="left")
        ttk.Button(buttons, text="Cancel", command=self.destroy).pack(side="left", padx=(6, 0))
        self.grab_set()

    def _ok(self) -> None:
        donor = None
        if self._needs:
            donor = next((p for p in self._donors if p.parent.name == self._donor.get()), None)
            if donor is None:
                messagebox.showerror("Water import", "Pick a map to copy the water from.", parent=self)
                return
        repaint = None
        if self._repaint.get():
            repaint = (terrain_kit.WATER_TILE_TYPES[self._water.get()], terrain_kit.LAND_TILE_TYPES[self._land.get()])
        self.result = (donor, repaint)
        self.destroy()


def add_water_tab(tabs: ttk.Notebook, previews: dict[str, Image.Image], notes: list[str]) -> ttk.Frame:
    """The import review's water: a top-down view and the fade, with the report."""
    tab = ttk.Frame(tabs, padding=6)
    tabs.add(tab, text="Water")
    grid = ttk.Frame(tab)
    grid.pack(anchor="w")
    tab._photos = []
    captions = {
        "Water": "Water over the tiles (blue dots: water tiles; white: shore waves)",
        "Fade": "Shoreline fade",
    }
    for k, (name, image) in enumerate(previews.items()):
        thumb = image.copy()
        thumb.thumbnail((300, 300))
        photo = ImageTk.PhotoImage(thumb)
        tab._photos.append(photo)
        cell = ttk.Frame(grid)
        cell.grid(row=0, column=k, padx=2, pady=2, sticky="n")
        ttk.Label(cell, image=photo).pack()
        ttk.Label(cell, text=captions.get(name, name), style="Muted.TLabel", wraplength=300).pack()
    ttk.Label(tab, text="\n".join(notes), wraplength=440, justify="left").pack(anchor="w", pady=(6, 0))
    return tab


class AtlasSwatchesDialog(tk.Toplevel):
    """Edit the swatches a map's terrain can be painted with. The table is
    detected from the terrain's UVs until it is saved in the project."""

    SCALE = 0.625  # a 512x1024 atlas shows at 320x640

    def __init__(self, parent, project_dir: Path, container_path: Path | None = None, *,
                 tileset_key: str | None = None) -> None:
        super().__init__(parent)
        self.transient(parent)
        self._project_dir = Path(project_dir)
        self._tileset_key = tileset_key
        if tileset_key is not None:
            saved_tileset = terrain_kit.load_project_tileset(self._project_dir, tileset_key)
            self.title(f"Tileset swatches - {saved_tileset.name}")
            self._tileset_name = saved_tileset.name
            self._source_map = saved_tileset.source_map
            self._folder = ""
            self._source = None
            self._layout, self._atlas, self._custom = saved_tileset.layout, saved_tileset.atlas, True
        else:
            if container_path is None:
                raise ValueError("A map is required for map atlas swatches.")
            self._folder = container_path.parent.name
            self.title(f"Atlas swatches - {self._folder}")
            self._source = terrain_kit.read_terrain(container_path)
            self._layout, self._atlas, self._custom = terrain_kit.load_layout(
                self._source, self._project_dir, self._folder
            )
        self._custom_changed = False
        self._selected: int | None = None

        body = ttk.Frame(self, padding=8)
        body.pack(fill="both", expand=True)
        self._canvas = tk.Canvas(body, width=int(512 * self.SCALE), height=int(1024 * self.SCALE),
                                 highlightthickness=0, background="#202020")
        self._canvas.pack(side="left", fill="y")
        self._canvas.bind("<Button-1>", self._click)
        side = ttk.Frame(body, padding=(8, 0, 0, 0))
        side.pack(side="left", fill="both", expand=True)
        self._status = ttk.Label(side, text="", style="Muted.TLabel", wraplength=420, justify="left")
        self._status.pack(anchor="w")
        columns = ("x", "y", "w", "h", "base")
        self._table = ttk.Treeview(side, columns=columns, height=14, selectmode="browse")
        self._table.heading("#0", text="Swatch")
        self._table.column("#0", width=150)
        for column in columns:
            self._table.heading(column, text=column)
            self._table.column(column, width=48, anchor="e")
        self._table.pack(fill="both", expand=True, pady=(6, 0))
        self._table.bind("<<TreeviewSelect>>", lambda e: self._on_select())

        edit = ttk.Frame(side)
        edit.pack(fill="x", pady=(6, 0))
        self._swatch_name = tk.StringVar()
        self._fields = {key: tk.IntVar() for key in ("x", "y", "w", "h")}
        ttk.Label(edit, text="Name").grid(row=0, column=0, sticky="w")
        ttk.Entry(edit, textvariable=self._swatch_name, width=22).grid(row=0, column=1, columnspan=3, sticky="ew")
        for k, key in enumerate(("x", "y", "w", "h")):
            ttk.Label(edit, text=key).grid(row=1 + k // 2, column=(k % 2) * 2, sticky="w")
            ttk.Spinbox(edit, from_=0, to=1024, increment=16, textvariable=self._fields[key], width=7).grid(
                row=1 + k // 2, column=(k % 2) * 2 + 1, sticky="w")
        ttk.Button(edit, text="Apply", command=self._apply).grid(row=3, column=3, sticky="e", pady=(4, 0))

        actions = ttk.Frame(side)
        actions.pack(fill="x", pady=(6, 0))
        for k, (text, command) in enumerate((
            ("Add swatch", self._add), ("Remove", self._remove), ("Set as base", self._set_base),
            ("Detect again", self._detect),
            ("Build custom tileset...", self._build_atlas), ("Use the game's atlas", self._use_game_atlas),
        )):
            ttk.Button(actions, text=text, command=command).grid(row=k // 3, column=k % 3, sticky="ew", padx=2, pady=2)
        for column in range(3):
            actions.grid_columnconfigure(column, weight=1)
        ttk.Label(
            side,
            text="A swatch is a tileable rectangle laid on the ground at 6.4 texels per unit; the base covers "
                 "the ground everywhere else. Width and height may differ. PNG is recommended; the custom "
                 "tileset builder accepts PNG, JPEG, BMP or TGA and fits each axis to 32, 64, 128 or 256 texels.",
            style="Muted.TLabel", wraplength=420, justify="left",
        ).pack(anchor="w", pady=(6, 0))
        buttons = ttk.Frame(side)
        buttons.pack(anchor="e", pady=(8, 0))
        ttk.Button(buttons, text="Save", command=self._save).pack(side="left")
        ttk.Button(buttons, text="Close", command=self.destroy).pack(side="left", padx=(6, 0))
        self._refresh()
        self.grab_set()

    # -- drawing
    def _refresh(self) -> None:
        self._canvas.delete("all")
        width, height = self._atlas.size
        scale = min(512 * self.SCALE / width, 1024 * self.SCALE / height)
        self._scale = scale
        shown = self._atlas.convert("RGB").resize((max(1, int(width * scale)), max(1, int(height * scale))))
        self._photo = ImageTk.PhotoImage(shown)
        self._canvas.create_image(0, 0, image=self._photo, anchor="nw")
        for i, s in enumerate(self._layout.swatches):
            colour = "#ff4040" if i == self._selected else ("#40c0ff" if i == self._layout.base else "#ffd040")
            self._canvas.create_rectangle(s.x * scale, s.y * scale, (s.x + s.w) * scale, (s.y + s.h) * scale,
                                          outline=colour, width=2 if i == self._selected else 1)
            self._canvas.create_text(s.x * scale + 3, s.y * scale + 2, text=s.name, anchor="nw", fill=colour,
                                     font=("TkDefaultFont", 8))
        self._table.delete(*self._table.get_children())
        for i, s in enumerate(self._layout.swatches):
            self._table.insert("", "end", iid=str(i), text=s.name,
                               values=(s.x, s.y, s.w, s.h, "base" if i == self._layout.base else ""))
        if self._selected is not None and self._selected < len(self._layout.swatches):
            self._table.selection_set(str(self._selected))
        state = "reusable project tileset" if self._tileset_key is not None else (
            "custom atlas (atlas builder)" if self._custom else "the game's atlas"
        )
        saved = (self._tileset_key is not None or
                 terrain_kit.layout_path(self._project_dir, self._folder).is_file())
        self._status.config(text=f"{len(self._layout.swatches)} swatches on {state}, {width}x{height}. "
                                 + ("Saved in the project." if saved else "Detected from the terrain; not saved yet."))

    def _click(self, event) -> None:
        tx, ty = event.x / self._scale, event.y / self._scale
        inside = [i for i, s in enumerate(self._layout.swatches) if s.contains(tx, ty)]
        if inside:
            self._select(min(inside, key=lambda i: self._layout.swatches[i].w * self._layout.swatches[i].h))

    def _select(self, index: int) -> None:
        self._selected = index
        s = self._layout.swatches[index]
        self._swatch_name.set(s.name)
        for key in ("x", "y", "w", "h"):
            self._fields[key].set(getattr(s, key))
        self._refresh()

    def _on_select(self) -> None:
        chosen = self._table.selection()
        if chosen and int(chosen[0]) != self._selected:
            self._select(int(chosen[0]))

    # -- editing
    def _apply(self) -> None:
        if self._selected is None:
            return
        try:
            swatch = tp.Swatch(self._swatch_name.get().strip() or "Swatch", *(int(self._fields[k].get()) for k in "xywh"))
        except (tk.TclError, ValueError):
            messagebox.showerror("Swatch", "x, y, w and h must be whole numbers of texels.", parent=self)
            return
        previous = self._layout.swatches[self._selected]
        self._layout.swatches[self._selected] = swatch
        try:
            self._layout.validate()
        except ValueError as exc:
            self._layout.swatches[self._selected] = previous
            messagebox.showerror("Swatch", str(exc), parent=self)
            return
        self._refresh()

    def _add(self) -> None:
        width, height = self._layout.width, self._layout.height
        cell_w, cell_h = terrain_kit._unused_cell_size(self._layout)
        self._layout.swatches.append(tp.Swatch(f"Swatch {len(self._layout.swatches) + 1}", 0,
                                               min(width, height - cell_h), cell_w, cell_h))
        self._select(len(self._layout.swatches) - 1)

    def _remove(self) -> None:
        if self._selected is None or len(self._layout.swatches) == 1:
            return
        if self._selected == self._layout.base:
            messagebox.showerror("Swatch", "Choose another base before removing this one.", parent=self)
            return
        del self._layout.swatches[self._selected]
        if self._layout.base > self._selected:
            self._layout.base -= 1
        self._selected = None
        self._refresh()

    def _set_base(self) -> None:
        if self._selected is not None:
            self._layout.base = self._selected
            self._refresh()

    def _detect(self) -> None:
        if self._source is None:
            messagebox.showinfo("Detect", "Reusable tilesets have no terrain UVs to detect from.", parent=self)
            return
        if self._custom:
            messagebox.showinfo("Detect", "Detection reads the game's terrain, which does not use the custom atlas.",
                                parent=self)
            return
        self._layout = terrain_kit.detect_layout(self._source)
        self._selected = None
        self._refresh()

    def _add_cells(self) -> None:
        added = terrain_kit.add_unused_cells(self._layout)
        self._refresh()
        if not added:
            messagebox.showinfo("Swatches", "Every inferred atlas cell is already in a swatch.", parent=self)

    def _build_atlas(self) -> None:
        base = filedialog.askopenfilename(
            title="Base ground image (tileable; centre-cropped and resized to 512x512)",
            filetypes=[("Images", "*.png *.jpg *.jpeg *.bmp *.tga"), ("All files", "*.*")], parent=self,
        )
        if not base:
            return
        extras = filedialog.askopenfilenames(
            title="Extra tile images (tileable; width and height fitted independently)",
            filetypes=[("Images", "*.png *.jpg *.jpeg *.bmp *.tga"), ("All files", "*.*")], parent=self,
        )
        try:
            base_image = np.asarray(_square(Image.open(base), 512))
            swatches = []
            for path in extras:
                swatches.append((Path(path).stem, np.asarray(_tile_image(Image.open(path)))))
            atlas, layout = tp.build_atlas(base_image, swatches)
        except (OSError, ValueError) as exc:
            messagebox.showerror("Atlas builder", str(exc), parent=self)
            return
        self._atlas = Image.fromarray(atlas, "RGBA")
        self._layout = layout
        terrain_kit.add_unused_cells(self._layout, atlas=self._atlas)
        self._custom = True
        self._custom_changed = True
        self._selected = None
        self._refresh()

    def _use_game_atlas(self) -> None:
        if self._source is None:
            messagebox.showinfo("Game atlas", "This reusable tileset is not attached to a game atlas.", parent=self)
            return
        if not self._custom:
            return
        self._atlas = self._source.atlas
        self._custom = False
        self._custom_changed = True
        self._layout = terrain_kit.detect_layout(self._source)
        self._selected = None
        self._refresh()

    def _save(self) -> None:
        try:
            if self._tileset_key is not None:
                terrain_kit.save_project_tileset(
                    self._project_dir, self._tileset_name, self._source_map, self._layout, self._atlas,
                    key=self._tileset_key,
                )
            else:
                terrain_kit.save_layout(
                    self._project_dir, self._folder, self._layout,
                    custom_atlas=self._atlas if self._custom and self._custom_changed else None,
                    clear_custom=not self._custom,
                )
        except (OSError, ValueError) as exc:
            messagebox.showerror("Atlas swatches", str(exc), parent=self)
            return
        self._custom_changed = False
        self._refresh()


def _square(image: Image.Image, side: int) -> Image.Image:
    """Centre-crop to a square and resize to ``side``, as RGBA."""
    image = image.convert("RGBA")
    w, h = image.size
    edge = min(w, h)
    image = image.crop(((w - edge) // 2, (h - edge) // 2, (w - edge) // 2 + edge, (h - edge) // 2 + edge))
    return image.resize((side, side), Image.LANCZOS)


def _tile_image(image: Image.Image) -> Image.Image:
    """Fit each axis independently to a supported custom-swatch size."""
    image = image.convert("RGBA")
    allowed = (32, 64, 128, 256)
    width = min(allowed, key=lambda size: abs(size - image.width))
    height = min(allowed, key=lambda size: abs(size - image.height))
    return image.resize((width, height), Image.LANCZOS)
