"""Dialogs of the Blender terrain sculpt & paint workflow (:mod:`terrain_kit`).

- :class:`PaintKitDialog`: options of a new terrain kit;
- :class:`PaintImportOptions`: options of importing a painted kit;
- :class:`AtlasSwatchesDialog`: the atlas swatch table of a map, saved per
  project, and the atlas builder for custom swatches;
- :func:`add_texturing_tab`: the import review's top-down views.
"""

from __future__ import annotations

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


class AtlasSwatchesDialog(tk.Toplevel):
    """Edit the swatches a map's terrain can be painted with. The table is
    detected from the terrain's UVs until it is saved in the project."""

    SCALE = 0.625  # a 512x1024 atlas shows at 320x640

    def __init__(self, parent, project_dir: Path, container_path: Path) -> None:
        super().__init__(parent)
        self.title(f"Atlas swatches - {container_path.parent.name}")
        self.transient(parent)
        self._project_dir = Path(project_dir)
        self._folder = container_path.parent.name
        self._source = terrain_kit.read_terrain(container_path)
        self._layout, self._atlas, self._custom = terrain_kit.load_layout(self._source, self._project_dir, self._folder)
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
            ("Detect again", self._detect), ("Add unused 128 cells", self._add_cells),
            ("Build custom atlas...", self._build_atlas), ("Use the game's atlas", self._use_game_atlas),
        )):
            ttk.Button(actions, text=text, command=command).grid(row=k // 3, column=k % 3, sticky="ew", padx=2, pady=2)
        for column in range(3):
            actions.grid_columnconfigure(column, weight=1)
        ttk.Label(
            side,
            text="A swatch is a tileable rectangle laid on the ground at 6.4 texels per unit; the base covers "
                 "the ground everywhere else. Sizes that divide each other (64, 128, 256, 512) keep the cuts "
                 "on the terrain few.",
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
        state = "custom atlas (atlas builder)" if self._custom else "the game's atlas"
        saved = terrain_kit.layout_path(self._project_dir, self._folder).is_file()
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
        self._layout.swatches.append(tp.Swatch(f"Swatch {len(self._layout.swatches) + 1}", 0,
                                               min(width, height - 128), 128, 128))
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
            messagebox.showinfo("Swatches", "Every 128-texel cell is already in a swatch.", parent=self)

    def _build_atlas(self) -> None:
        base = filedialog.askopenfilename(
            title="Base ground image (tileable; resized to 512x512)",
            filetypes=[("Images", "*.png *.jpg *.jpeg *.bmp *.tga"), ("All files", "*.*")], parent=self,
        )
        if not base:
            return
        extras = filedialog.askopenfilenames(
            title="Swatch images (tileable; each made square at 64, 128 or 256 texels)",
            filetypes=[("Images", "*.png *.jpg *.jpeg *.bmp *.tga"), ("All files", "*.*")], parent=self,
        )
        try:
            base_image = np.asarray(_square(Image.open(base), 512))
            swatches = []
            for path in extras:
                image = Image.open(path)
                side = min((64, 128, 256), key=lambda s: abs(s - min(image.size)))
                swatches.append((Path(path).stem, np.asarray(_square(image, side))))
            atlas, layout = tp.build_atlas(base_image, swatches)
        except (OSError, ValueError) as exc:
            messagebox.showerror("Atlas builder", str(exc), parent=self)
            return
        self._atlas = Image.fromarray(atlas, "RGBA")
        self._layout = layout
        self._custom = True
        self._custom_changed = True
        self._selected = None
        self._refresh()

    def _use_game_atlas(self) -> None:
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
