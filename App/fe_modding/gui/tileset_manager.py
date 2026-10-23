"""Assets > Tilesets: reusable terrain atlases and their paint swatches."""

from __future__ import annotations

import hashlib
import queue
import threading
import tkinter as tk
from dataclasses import dataclass
from pathlib import Path
from tkinter import filedialog, messagebox, simpledialog, ttk

import numpy as np
from PIL import Image, ImageTk

from .. import terrain_kit
from .. import terrain_paint as tp
from .editor_panel import EditorPanel
from .terrain_paint_dialogs import AtlasSwatchesDialog, _square, _tile_image


@dataclass
class _Choice:
    label: str
    atlas: Image.Image
    map_path: Path
    maps: tuple[str, ...] = ()
    key: str | None = None


class TilesetManager(EditorPanel):
    """Browse each distinct game atlas and author reusable project tilesets."""

    display_name = "Tilesets"

    def __init__(self, parent, project, changelog) -> None:
        super().__init__(parent)
        self._project = project
        self._changelog = changelog
        self._dirty = False
        self._choices: list[_Choice] = []
        self._results: queue.Queue = queue.Queue()
        self._photo = None
        self._build()
        self._scan()

    def _build(self) -> None:
        split = ttk.PanedWindow(self, orient="horizontal")
        split.pack(fill="both", expand=True)
        left = ttk.Frame(split, padding=10)
        right = ttk.Frame(split, padding=10)
        split.add(left, weight=2)
        split.add(right, weight=3)
        ttk.Label(left, text="Tilesets", style="Title.TLabel").pack(anchor="w")
        ttk.Label(left, text="Every distinct map atlas, plus reusable tilesets made for this project.",
                  style="Muted.TLabel", wraplength=360, justify="left").pack(anchor="w", pady=(2, 8))
        self._list = tk.Listbox(left, exportselection=False)
        self._list.pack(fill="both", expand=True)
        self._list.bind("<<ListboxSelect>>", lambda _e: self._show())
        self._status = ttk.Label(left, text="Finding terrain atlases…", style="Muted.TLabel")
        self._status.pack(anchor="w", pady=(6, 0))

        actions = ttk.Frame(left)
        actions.pack(fill="x", pady=(8, 0))
        buttons = (
            ("Import full tileset…", self._import_full),
            ("Build from images…", self._build_images),
            ("New from swatches…", self._copy_selected),
            ("Import into swatches…", self._add_images),
            ("Edit swatches…", self._edit),
        )
        self._buttons = []
        for index, (text, command) in enumerate(buttons):
            button = ttk.Button(actions, text=text, command=command)
            button.grid(row=index // 2, column=index % 2, sticky="ew", padx=2, pady=2)
            self._buttons.append(button)
        actions.grid_columnconfigure(0, weight=1)
        actions.grid_columnconfigure(1, weight=1)

        self._title = ttk.Label(right, text="Choose a tileset", style="Heading.TLabel")
        self._title.pack(anchor="w")
        self._preview = ttk.Label(right, text="", anchor="center")
        self._preview.pack(fill="both", expand=True, pady=(8, 8))
        self._details = ttk.Label(right, text="", style="Muted.TLabel", wraplength=520, justify="left")
        self._details.pack(anchor="w", fill="x")
        self._swatches = ttk.Treeview(right, columns=("x", "y", "size", "base"), height=9)
        self._swatches.heading("#0", text="Swatch")
        for column, heading, width in (("x", "X", 55), ("y", "Y", 55), ("size", "Size", 90), ("base", "", 55)):
            self._swatches.heading(column, text=heading)
            self._swatches.column(column, width=width, anchor="e")
        self._swatches.pack(fill="x", pady=(8, 0))

    def _map_paths(self) -> list[tuple[str, Path]]:
        root = self._project.files_dir / "zmap"
        return [(f"zmap/{path.parent.name}", path) for path in sorted(root.glob("*/map.cmp"))] if root.is_dir() else []

    def _scan(self) -> None:
        maps = self._map_paths()

        def worker() -> None:
            groups: dict[bytes, dict] = {}
            for index, (label, path) in enumerate(maps, 1):
                try:
                    custom = terrain_kit.custom_atlas_path(self._project.directory, path.parent.name)
                    atlas = Image.open(custom).convert("RGBA") if custom.is_file() else terrain_kit.read_terrain_atlas(path)
                    digest = hashlib.sha256(f"{atlas.size}:".encode() + atlas.tobytes()).digest()
                    group = groups.setdefault(digest, {"atlas": atlas, "path": path, "maps": []})
                    group["maps"].append(label)
                except Exception:  # a map without paintable map_base is intentionally omitted
                    pass
                self._results.put(("progress", index, len(maps)))
            choices = [
                _Choice(data["maps"][0], data["atlas"], data["path"], tuple(data["maps"]))
                for data in groups.values()
            ]
            for saved in terrain_kit.project_tilesets(self._project.directory):
                source = self._project.files_dir / "zmap" / saved.source_map / "map.cmp"
                if source.is_file():
                    choices.append(_Choice(saved.name, saved.atlas, source, key=saved.key))
            choices.sort(key=lambda item: (item.key is None, item.label.casefold()))
            self._results.put(("done", choices))

        threading.Thread(target=worker, daemon=True).start()
        self.after(50, self._poll)

    def _poll(self) -> None:
        try:
            message = self._results.get_nowait()
        except queue.Empty:
            if self.winfo_exists():
                self.after(100, self._poll)
            return
        if message[0] == "progress":
            self._status.configure(text=f"Finding terrain atlases… {message[1]}/{message[2]}")
            self.after(10, self._poll)
            return
        self._choices = message[1]
        self._list.delete(0, "end")
        for item in self._choices:
            suffix = "  ·  Project" if item.key else (f"  ·  {len(item.maps)} maps" if len(item.maps) > 1 else "")
            self._list.insert("end", item.label + suffix)
        self._status.configure(text=f"{len(self._choices)} distinct tilesets")
        if self._choices:
            self._list.selection_set(0)
            self._show()

    def _selected(self) -> _Choice | None:
        selection = self._list.curselection()
        return self._choices[selection[0]] if selection else None

    def _layout(self, choice: _Choice) -> tp.AtlasLayout:
        if choice.key:
            return terrain_kit.load_project_tileset(self._project.directory, choice.key).layout
        source = terrain_kit.read_terrain(choice.map_path)
        return terrain_kit.load_layout(source, self._project.directory, choice.map_path.parent.name)[0]

    def _show(self) -> None:
        choice = self._selected()
        if choice is None:
            return
        self._title.configure(text=choice.label)
        image = choice.atlas.convert("RGB")
        image.thumbnail((520, 480), Image.LANCZOS)
        self._photo = ImageTk.PhotoImage(image)
        self._preview.configure(image=self._photo)
        try:
            layout = self._layout(choice)
        except Exception as exc:  # noqa: BLE001
            self._details.configure(text=str(exc))
            return
        self._details.configure(text=("Reusable project tileset" if choice.key else
                                     "Used by " + ", ".join(choice.maps)))
        self._swatches.delete(*self._swatches.get_children())
        for index, swatch in enumerate(layout.swatches):
            self._swatches.insert("", "end", iid=str(index), text=swatch.name,
                                  values=(swatch.x, swatch.y, f"{swatch.w}×{swatch.h}",
                                          "Base" if index == layout.base else ""))

    def _name_and_source(self, title: str) -> tuple[str, Path] | None:
        name = simpledialog.askstring(title, "Tileset name", parent=self)
        if not name:
            return None
        try:
            key = terrain_kit._tileset_key(name)
        except ValueError as exc:
            messagebox.showerror(title, str(exc), parent=self)
            return None
        if (terrain_kit.tilesets_path(self._project.directory) / f"{key}.json").exists():
            messagebox.showerror(title, "A project tileset with that name already exists.", parent=self)
            return None
        maps = self._map_paths()
        if not maps:
            messagebox.showerror(title, "No map is available to supply the game-compatible terrain template.", parent=self)
            return None
        selected = self._selected()
        source = selected.map_path if selected is not None else maps[0][1]
        return name.strip(), source

    def _save_new(self, name: str, source: Path, atlas: Image.Image, layout: tp.AtlasLayout) -> None:
        try:
            saved = terrain_kit.save_project_tileset(
                self._project.directory, name, source.parent.name, layout, atlas
            )
        except (OSError, ValueError) as exc:
            messagebox.showerror("Tilesets", str(exc), parent=self)
            return
        self._changelog.append("Tilesets", f"Created project tileset {saved.name}")
        self._scan()

    def _import_full(self) -> None:
        named = self._name_and_source("Import full tileset")
        if named is None:
            return
        path = filedialog.askopenfilename(title="Full 512×1024 terrain atlas", parent=self,
                                          filetypes=[("Images", "*.png *.jpg *.jpeg *.bmp *.tga"), ("All files", "*.*")])
        if not path:
            return
        try:
            atlas = Image.open(path).convert("RGBA")
            if atlas.size != (512, 1024):
                raise ValueError("A full terrain tileset must be exactly 512×1024 pixels.")
            layout = tp.default_layout(512, 1024)
            terrain_kit._name_generic_swatches(layout, atlas)
        except (OSError, ValueError) as exc:
            messagebox.showerror("Import full tileset", str(exc), parent=self)
            return
        self._save_new(named[0], named[1], atlas, layout)

    def _build_images(self) -> None:
        named = self._name_and_source("Build tileset from images")
        if named is None:
            return
        base = filedialog.askopenfilename(title="Base ground image", parent=self,
                                          filetypes=[("Images", "*.png *.jpg *.jpeg *.bmp *.tga")])
        if not base:
            return
        extras = filedialog.askopenfilenames(title="Additional swatch images", parent=self,
                                             filetypes=[("Images", "*.png *.jpg *.jpeg *.bmp *.tga")])
        try:
            base_data = np.asarray(_square(Image.open(base), 512))
            swatches = [(Path(path).stem, np.asarray(_tile_image(Image.open(path)))) for path in extras]
            atlas_data, layout = tp.build_atlas(base_data, swatches)
            atlas = Image.fromarray(atlas_data, "RGBA")
            terrain_kit.add_unused_cells(layout, atlas=atlas)
        except (OSError, ValueError) as exc:
            messagebox.showerror("Build tileset", str(exc), parent=self)
            return
        self._save_new(named[0], named[1], atlas, layout)

    def _copy_selected(self) -> None:
        choice = self._selected()
        if choice is None:
            return
        named = self._name_and_source("New tileset from swatches")
        if named is None:
            return
        layout = self._layout(choice)
        picked = {int(item) for item in self._swatches.selection()}
        # No explicit selection means "copy them all"; the base is always
        # included because the game requires one full ground swatch.
        if not picked:
            picked = set(range(len(layout.swatches)))
        base_swatch = layout.swatches[layout.base]
        base_crop = choice.atlas.crop((base_swatch.x, base_swatch.y,
                                      base_swatch.x + base_swatch.w, base_swatch.y + base_swatch.h))
        base = np.asarray(_square(base_crop, 512))
        extras = []
        for index in sorted(picked):
            if index == layout.base:
                continue
            swatch = layout.swatches[index]
            crop = choice.atlas.crop((swatch.x, swatch.y, swatch.x + swatch.w, swatch.y + swatch.h))
            extras.append((swatch.name, np.asarray(_tile_image(crop))))
        try:
            data, new_layout = tp.build_atlas(base, extras)
            atlas = Image.fromarray(data, "RGBA")
        except ValueError as exc:
            messagebox.showerror("New tileset from swatches", str(exc), parent=self)
            return
        self._save_new(named[0], named[1], atlas, new_layout)

    def _add_images(self) -> None:
        choice = self._selected()
        if choice is None or choice.key is None:
            messagebox.showinfo("Import swatches", "Create a project tileset first, then import into its swatches.", parent=self)
            return
        picked = [int(item) for item in self._swatches.selection()]
        if not picked:
            messagebox.showinfo("Import swatches", "Select one or more swatches in the table first.", parent=self)
            return
        paths = filedialog.askopenfilenames(title="Images for the selected swatches", parent=self,
                                            filetypes=[("Images", "*.png *.jpg *.jpeg *.bmp *.tga")])
        if not paths:
            return
        if len(paths) != len(picked):
            messagebox.showerror("Import swatches", "Choose exactly one image for each selected swatch.", parent=self)
            return
        saved = terrain_kit.load_project_tileset(self._project.directory, choice.key)
        try:
            atlas = saved.atlas.copy()
            for index, path in zip(picked, paths):
                swatch = saved.layout.swatches[index]
                image = Image.open(path).convert("RGBA").resize((swatch.w, swatch.h), Image.LANCZOS)
                atlas.paste(image, (swatch.x, swatch.y))
                swatch.name = Path(path).stem
            terrain_kit.save_project_tileset(self._project.directory, saved.name, saved.source_map,
                                               saved.layout, atlas, key=saved.key)
        except (OSError, ValueError) as exc:
            messagebox.showerror("Import swatches", str(exc), parent=self)
            return
        self._changelog.append("Tilesets", f"Imported {len(paths)} swatch images into {saved.name}")
        self._scan()

    def _edit(self) -> None:
        choice = self._selected()
        if choice is None:
            return
        try:
            dialog = (AtlasSwatchesDialog(self, self._project.directory, tileset_key=choice.key)
                      if choice.key else AtlasSwatchesDialog(self, self._project.directory, choice.map_path))
            self.wait_window(dialog)
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror("Tilesets", str(exc), parent=self)
        self._scan()
