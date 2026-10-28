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
from .terrain_paint_dialogs import _square, _tile_image
from ..game_profile import files_root_of


@dataclass
class _Choice:
    label: str
    atlas: Image.Image
    map_path: Path
    maps: tuple[str, ...] = ()
    key: str | None = None
    layout: tp.AtlasLayout | None = None


class _SwatchImportDialog(tk.Toplevel):
    """Choose one or more swatches from another visible tileset."""

    def __init__(self, parent, choices: list[_Choice], layout_of) -> None:
        super().__init__(parent)
        self.title("Import from tileset")
        self.transient(parent)
        self.result: tuple[_Choice, list[int]] | None = None
        self._choices = choices
        self._layout_of = layout_of
        self._preview_photo = None
        body = ttk.Frame(self, padding=12)
        body.pack(fill="both", expand=True)
        ttk.Label(body, text="Source tileset").pack(anchor="w")
        self._source = ttk.Combobox(body, state="readonly", values=[choice.label for choice in choices], width=42)
        self._source.pack(fill="x", pady=(2, 8))
        self._source.bind("<<ComboboxSelected>>", lambda _event: self._load())
        ttk.Label(body, text="Select the swatches to copy into the current tileset.",
                  style="Muted.TLabel").pack(anchor="w", pady=(0, 4))
        content = ttk.Frame(body)
        content.pack(fill="both", expand=True)
        self._table = ttk.Treeview(content, columns=("size",), selectmode="extended", height=14)
        self._table.heading("#0", text="Swatch")
        self._table.heading("size", text="Size")
        self._table.column("#0", width=260)
        self._table.column("size", width=90, anchor="e")
        self._table.pack(side="left", fill="both", expand=True)
        self._table.bind("<<TreeviewSelect>>", self._show_preview)
        preview = ttk.LabelFrame(content, text="Selected swatch", padding=8)
        preview.pack(side="left", fill="both", padx=(10, 0))
        self._preview = ttk.Label(preview, text="Select a swatch", anchor="center", width=34)
        self._preview.pack(fill="both", expand=True)
        self._preview_details = ttk.Label(preview, text="", style="Muted.TLabel", anchor="center")
        self._preview_details.pack(fill="x", pady=(6, 0))
        buttons = ttk.Frame(body)
        buttons.pack(anchor="e", pady=(10, 0))
        ttk.Button(buttons, text="Import", style="Accent.TButton", command=self._accept).pack(side="left")
        ttk.Button(buttons, text="Cancel", command=self.destroy).pack(side="left", padx=(6, 0))
        if choices:
            self._source.current(0)
            self._load()
        self.protocol("WM_DELETE_WINDOW", self.destroy)
        self.bind("<Escape>", lambda _event: self.destroy())
        self.grab_set()

    def _load(self) -> None:
        self._table.delete(*self._table.get_children())
        index = self._source.current()
        if not 0 <= index < len(self._choices):
            return
        layout = self._layout_of(self._choices[index])
        for swatch_index, swatch in enumerate(layout.swatches):
            suffix = " · Base" if swatch_index == layout.base else ""
            self._table.insert("", "end", iid=str(swatch_index), text=swatch.name + suffix,
                               values=(f"{swatch.w}×{swatch.h}",))
        if layout.swatches:
            selected = str(layout.base)
            self._table.selection_set(selected)
            self._table.focus(selected)
            self._show_preview()

    def _show_preview(self, _event=None) -> None:
        source_index = self._source.current()
        selected = self._table.selection()
        if not 0 <= source_index < len(self._choices) or not selected:
            self._preview.configure(image="", text="Select a swatch")
            self._preview_details.configure(text="")
            self._preview_photo = None
            return
        swatch_index = int(self._table.focus() or selected[0])
        source = self._choices[source_index]
        swatch = self._layout_of(source).swatches[swatch_index]
        crop = source.atlas.crop((swatch.x, swatch.y, swatch.x + swatch.w, swatch.y + swatch.h)).convert("RGB")
        scale = min(300 / max(crop.width, 1), 300 / max(crop.height, 1), 8.0)
        if scale != 1.0:
            crop = crop.resize((max(1, round(crop.width * scale)), max(1, round(crop.height * scale))),
                               Image.Resampling.NEAREST)
        self._preview_photo = ImageTk.PhotoImage(crop)
        self._preview.configure(image=self._preview_photo, text="")
        self._preview_details.configure(
            text=f"{swatch.name} · {swatch.w}×{swatch.h} at ({swatch.x}, {swatch.y})"
        )

    def _accept(self) -> None:
        source_index = self._source.current()
        picked = [int(item) for item in self._table.selection()]
        if not 0 <= source_index < len(self._choices) or not picked:
            messagebox.showinfo("Import swatches", "Select at least one source swatch.", parent=self)
            return
        self.result = self._choices[source_index], picked
        self.destroy()


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
        self._active: _Choice | None = None
        self._selected_swatch: int | None = None
        self._zoom = tk.IntVar(value=50)
        self._cell_editor: ttk.Entry | None = None
        self._build()
        self._scan()

    def _build(self) -> None:
        split = ttk.PanedWindow(self, orient="horizontal")
        split.pack(fill="both", expand=True)
        left = ttk.Frame(split, padding=10)
        atlas_column = ttk.Frame(split, padding=10)
        swatch_column = ttk.Frame(split, padding=10)
        split.add(left, weight=1)
        split.add(atlas_column, weight=2)
        split.add(swatch_column, weight=2)
        ttk.Label(left, text="Tilesets", style="Title.TLabel").pack(anchor="w")
        ttk.Label(left, text="Every distinct map atlas, plus reusable tilesets made for this project.",
                  style="Muted.TLabel", wraplength=230, justify="left").pack(anchor="w", pady=(2, 8))
        self._list = tk.Listbox(left, exportselection=False)
        self._list.pack(fill="both", expand=True)
        self._list.bind("<<ListboxSelect>>", self._choice_selected)
        self._status = ttk.Label(left, text="Finding terrain atlases…", style="Muted.TLabel")
        self._status.pack(anchor="w", pady=(6, 0))

        actions = ttk.Frame(left)
        actions.pack(fill="x", pady=(8, 0))
        buttons = (
            ("Import full tileset…", self._import_full),
            ("Build from images…", self._build_images),
            ("New from swatches…", self._copy_selected),
        )
        self._buttons = []
        for index, (text, command) in enumerate(buttons):
            button = ttk.Button(actions, text=text, command=command)
            button.grid(row=index, column=0, sticky="ew", pady=2)
            self._buttons.append(button)
        actions.grid_columnconfigure(0, weight=1)

        self._title = ttk.Label(atlas_column, text="Choose a tileset", style="Heading.TLabel")
        self._title.pack(anchor="w")
        zoom = ttk.Frame(atlas_column)
        zoom.pack(fill="x", pady=(4, 2))
        ttk.Label(zoom, text="Atlas preview").pack(side="left")
        ttk.Button(zoom, text="−", width=3, command=lambda: self._change_zoom(-25)).pack(side="right")
        ttk.Button(zoom, text="+", width=3, command=lambda: self._change_zoom(25)).pack(side="right", padx=(4, 0))
        self._zoom_label = ttk.Label(zoom, text="50%", width=6, anchor="center")
        self._zoom_label.pack(side="right")
        ttk.Button(zoom, text="Fit", command=self._fit_zoom).pack(side="right", padx=(0, 6))

        preview_frame = ttk.Frame(atlas_column)
        preview_frame.pack(fill="both", expand=True)
        self._preview = tk.Canvas(preview_frame, background="#202020", highlightthickness=0,
                                  width=520, height=390)
        preview_x = ttk.Scrollbar(preview_frame, orient="horizontal", command=self._preview.xview)
        preview_y = ttk.Scrollbar(preview_frame, orient="vertical", command=self._preview.yview)
        self._preview.configure(xscrollcommand=preview_x.set, yscrollcommand=preview_y.set)
        self._preview.grid(row=0, column=0, sticky="nsew")
        preview_y.grid(row=0, column=1, sticky="ns")
        preview_x.grid(row=1, column=0, sticky="ew")
        preview_frame.grid_rowconfigure(0, weight=1)
        preview_frame.grid_columnconfigure(0, weight=1)
        self._preview.bind("<Button-1>", self._preview_clicked)
        self._preview.bind("<Control-MouseWheel>", self._zoom_wheel)
        self._details = ttk.Label(atlas_column, text="", style="Muted.TLabel", wraplength=430, justify="left")
        self._details.pack(anchor="w", fill="x", pady=(6, 0))

        ttk.Label(swatch_column, text="Swatches", style="Heading.TLabel").pack(anchor="w")
        ttk.Label(swatch_column, text="Double-click a name or number to edit it directly.",
                  style="Muted.TLabel", wraplength=390).pack(anchor="w", pady=(2, 6))
        swatch_table = ttk.Frame(swatch_column)
        swatch_table.pack(fill="both", expand=True)
        self._swatches = ttk.Treeview(swatch_table, columns=("x", "y", "w", "h", "base"), height=16,
                                      selectmode="extended")
        self._swatches.heading("#0", text="Swatch")
        self._swatches.column("#0", width=170, minwidth=90)
        for column, heading, width in (("x", "X", 55), ("y", "Y", 55), ("w", "W", 55), ("h", "H", 55),
                                       ("base", "", 55)):
            self._swatches.heading(column, text=heading)
            self._swatches.column(column, width=width, anchor="e")
        swatch_scroll = ttk.Scrollbar(swatch_table, orient="vertical", command=self._swatches.yview)
        self._swatches.configure(yscrollcommand=swatch_scroll.set)
        self._swatches.pack(side="left", fill="both", expand=True)
        swatch_scroll.pack(side="right", fill="y")
        self._swatches.bind("<<TreeviewSelect>>", self._swatch_selected)
        self._swatches.bind("<Double-1>", self._begin_cell_edit)

        swatch_actions = ttk.Frame(swatch_column)
        swatch_actions.pack(fill="x", pady=(6, 0))
        for index, (text, command) in enumerate((("Add swatch", self._add_swatch),
                                                  ("Remove", self._remove_swatch),
                                                  ("Set as base", self._set_base),
                                                  ("Import images…", self._add_images),
                                                  ("Import from tileset…", self._import_from_tileset),
                                                  ("Save swatches", self._save_active))):
            ttk.Button(swatch_actions, text=text, command=command).grid(
                row=index // 2, column=index % 2, sticky="ew", padx=2, pady=2
            )
        swatch_actions.grid_columnconfigure(0, weight=1)
        swatch_actions.grid_columnconfigure(1, weight=1)
        self.after(50, lambda: self._place_sashes(split))

    def _place_sashes(self, split: ttk.PanedWindow, attempts: int = 20) -> None:
        if not split.winfo_exists():
            return
        width = split.winfo_width()
        if width < 600 and attempts:
            self.after(50, lambda: self._place_sashes(split, attempts - 1))
            return
        try:
            split.sashpos(0, int(width * 0.20))
            split.sashpos(1, int(width * 0.60))
        except tk.TclError:
            pass

    def _map_paths(self) -> list[tuple[str, Path]]:
        root = files_root_of(self._project) / "zmap"
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
                source = files_root_of(self._project) / "zmap" / saved.source_map / "map.cmp"
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
        if choice.layout is not None:
            return choice.layout
        if choice.key:
            choice.layout = terrain_kit.load_project_tileset(self._project.directory, choice.key).layout
        else:
            source = terrain_kit.read_terrain(choice.map_path)
            choice.layout = terrain_kit.load_layout(source, self._project.directory, choice.map_path.parent.name)[0]
        return choice.layout

    def _choice_selected(self, _event=None) -> None:
        choice = self._selected()
        if choice is self._active:
            return
        previous = self._active
        if self._dirty:
            answer = messagebox.askyesnocancel(
                "Save swatches?", "Save the swatch changes before opening another tileset?", parent=self
            )
            if answer is None:
                if previous in self._choices:
                    self._list.selection_clear(0, "end")
                    self._list.selection_set(self._choices.index(previous))
                return
            if answer and not self._save_active():
                if previous in self._choices:
                    self._list.selection_clear(0, "end")
                    self._list.selection_set(self._choices.index(previous))
                return
            if not answer:
                self._discard_active()
                self._dirty = False
        self._show()

    def _show(self) -> None:
        choice = self._selected()
        if choice is None:
            return
        self._active = choice
        self._selected_swatch = None
        self._title.configure(text=choice.label)
        try:
            layout = self._layout(choice)
        except Exception as exc:  # noqa: BLE001
            self._details.configure(text=str(exc))
            return
        self._details.configure(text=("Reusable project tileset" if choice.key else
                                     "Used by " + ", ".join(choice.maps)))
        self._refresh_swatch_table()
        self._draw_preview()

    def _refresh_swatch_table(self) -> None:
        choice = self._active
        if self._cell_editor is not None and self._cell_editor.winfo_exists():
            self._cell_editor.destroy()
        self._cell_editor = None
        self._swatches.delete(*self._swatches.get_children())
        if choice is None:
            return
        layout = self._layout(choice)
        for index, swatch in enumerate(layout.swatches):
            self._swatches.insert("", "end", iid=str(index), text=swatch.name,
                                  values=(swatch.x, swatch.y, swatch.w, swatch.h,
                                          "Base" if index == layout.base else ""))
        if self._selected_swatch is not None and self._selected_swatch < len(layout.swatches):
            self._swatches.selection_set(str(self._selected_swatch))
            self._swatches.focus(str(self._selected_swatch))

    def _draw_preview(self) -> None:
        self._preview.delete("all")
        choice = self._active
        if choice is None:
            return
        scale = self._zoom.get() / 100.0
        width, height = choice.atlas.size
        shown = choice.atlas.convert("RGB").resize(
            (max(1, round(width * scale)), max(1, round(height * scale))), Image.Resampling.LANCZOS
        )
        self._photo = ImageTk.PhotoImage(shown)
        self._preview.create_image(0, 0, image=self._photo, anchor="nw")
        layout = self._layout(choice)
        for index, swatch in enumerate(layout.swatches):
            colour = "#ff4040" if index == self._selected_swatch else (
                "#40c0ff" if index == layout.base else "#ffd040"
            )
            self._preview.create_rectangle(
                swatch.x * scale, swatch.y * scale,
                (swatch.x + swatch.w) * scale, (swatch.y + swatch.h) * scale,
                outline=colour, width=3 if index == self._selected_swatch else 1,
            )
            if scale >= 0.5:
                self._preview.create_text(swatch.x * scale + 3, swatch.y * scale + 2,
                                          text=swatch.name, anchor="nw", fill=colour)
        self._preview.configure(scrollregion=(0, 0, width * scale, height * scale))
        self._zoom_label.configure(text=f"{self._zoom.get()}%")

    def _change_zoom(self, amount: int) -> None:
        self._zoom.set(max(25, min(400, self._zoom.get() + amount)))
        self._draw_preview()

    def _fit_zoom(self) -> None:
        choice = self._active
        if choice is None:
            return
        self.update_idletasks()
        width = max(self._preview.winfo_width() - 4, 1)
        height = max(self._preview.winfo_height() - 4, 1)
        scale = min(width / choice.atlas.width, height / choice.atlas.height)
        self._zoom.set(max(25, min(400, int(scale * 100))))
        self._draw_preview()

    def _zoom_wheel(self, event) -> str:
        self._change_zoom(25 if event.delta > 0 else -25)
        return "break"

    def _preview_clicked(self, event) -> None:
        choice = self._active
        if choice is None:
            return
        scale = self._zoom.get() / 100.0
        tx = self._preview.canvasx(event.x) / scale
        ty = self._preview.canvasy(event.y) / scale
        layout = self._layout(choice)
        inside = [index for index, swatch in enumerate(layout.swatches) if swatch.contains(tx, ty)]
        if inside:
            index = min(inside, key=lambda item: layout.swatches[item].w * layout.swatches[item].h)
            self._swatches.selection_set(str(index))
            self._swatches.focus(str(index))
            self._swatches.see(str(index))

    def _swatch_selected(self, _event=None) -> None:
        selected = self._swatches.selection()
        choice = self._active
        if not selected or choice is None:
            self._selected_swatch = None
            self._draw_preview()
            return
        self._selected_swatch = int(self._swatches.focus() or selected[0])
        self._draw_preview()

    def _begin_cell_edit(self, event) -> None:
        row = self._swatches.identify_row(event.y)
        column = self._swatches.identify_column(event.x)
        if not row or column not in {"#0", "#1", "#2", "#3", "#4"}:
            return
        self._swatches.selection_set(row)
        self._swatches.focus(row)
        self._selected_swatch = int(row)
        box = self._swatches.bbox(row, column)
        if not box:
            return
        if self._cell_editor is not None and self._cell_editor.winfo_exists():
            self._cell_editor.destroy()
        index = int(row)
        swatch = self._layout(self._active).swatches[index]
        fields = ("name", "x", "y", "w", "h")
        field = fields[int(column[1:])]
        value = swatch.name if field == "name" else str(getattr(swatch, field))
        editor = ttk.Entry(self._swatches)
        self._cell_editor = editor
        editor.insert(0, value)
        editor.select_range(0, "end")
        editor.place(x=box[0], y=box[1], width=box[2], height=box[3])
        editor.focus_set()
        committed = {"done": False}

        def commit(_event=None) -> None:
            if committed["done"]:
                return
            committed["done"] = True
            self._commit_cell_edit(index, field, editor.get())
            if editor.winfo_exists():
                editor.destroy()
            self._cell_editor = None

        def cancel(_event=None) -> None:
            committed["done"] = True
            if editor.winfo_exists():
                editor.destroy()
            self._cell_editor = None

        editor.bind("<Return>", commit)
        editor.bind("<FocusOut>", commit)
        editor.bind("<Escape>", cancel)

    def _commit_cell_edit(self, index: int, field: str, value: str) -> None:
        choice = self._active
        if choice is None or not 0 <= index < len(self._layout(choice).swatches):
            return
        layout = self._layout(choice)
        current = layout.swatches[index]
        values = {key: getattr(current, key) for key in ("name", "x", "y", "w", "h")}
        try:
            values[field] = (value.strip() or "Swatch") if field == "name" else int(value.strip())
            replacement = tp.Swatch(values["name"], values["x"], values["y"], values["w"], values["h"])
        except ValueError:
            messagebox.showerror("Swatch", f"{field.upper()} must be a whole number of texels.", parent=self)
            return
        layout.swatches[index] = replacement
        try:
            layout.validate()
        except ValueError as exc:
            layout.swatches[index] = current
            messagebox.showerror("Swatch", str(exc), parent=self)
            return
        self._dirty = True
        self._refresh_swatch_table()
        self._draw_preview()

    def _add_swatch(self) -> None:
        choice = self._active
        if choice is None:
            return
        layout = self._layout(choice)
        cell_w, cell_h = terrain_kit._unused_cell_size(layout)
        layout.swatches.append(tp.Swatch(
            f"Swatch {len(layout.swatches) + 1}", 0, max(0, layout.height - cell_h), cell_w, cell_h
        ))
        self._selected_swatch = len(layout.swatches) - 1
        self._dirty = True
        self._refresh_swatch_table()
        self._swatch_selected()

    def _remove_swatch(self) -> None:
        choice = self._active
        index = self._selected_swatch
        if choice is None or index is None:
            return
        layout = self._layout(choice)
        if len(layout.swatches) == 1:
            messagebox.showerror("Swatch", "A tileset must keep at least one swatch.", parent=self)
            return
        if index == layout.base:
            messagebox.showerror("Swatch", "Set another swatch as the base before removing this one.", parent=self)
            return
        del layout.swatches[index]
        if layout.base > index:
            layout.base -= 1
        self._selected_swatch = None
        self._dirty = True
        self._refresh_swatch_table()
        self._draw_preview()

    def _set_base(self) -> None:
        choice = self._active
        index = self._selected_swatch
        if choice is None or index is None:
            return
        self._layout(choice).base = index
        self._dirty = True
        self._refresh_swatch_table()
        self._draw_preview()

    def _save_active(self) -> bool:
        choice = self._active
        if choice is None or not self._dirty:
            return True
        layout = self._layout(choice)
        try:
            if choice.key:
                saved = terrain_kit.load_project_tileset(self._project.directory, choice.key)
                terrain_kit.save_project_tileset(
                    self._project.directory, saved.name, saved.source_map, layout, choice.atlas, key=saved.key
                )
                description = f"Edited swatches for project tileset {saved.name}"
            else:
                folders = [label.split("/", 1)[-1] for label in choice.maps] or [choice.map_path.parent.name]
                for folder in folders:
                    terrain_kit.save_layout(self._project.directory, folder, layout)
                description = f"Edited swatches for {choice.label}"
        except (OSError, ValueError) as exc:
            messagebox.showerror("Save swatches", str(exc), parent=self)
            return False
        self._dirty = False
        self._changelog.append("Tilesets", description)
        self._details.configure(text=("Reusable project tileset · Saved" if choice.key else
                                     "Used by " + ", ".join(choice.maps) + " · Saved"))
        return True

    def _confirm_discard(self) -> bool:
        if not self._dirty:
            return True
        answer = messagebox.askyesnocancel("Save swatches?", "Save the swatch changes before leaving Tilesets?",
                                           parent=self)
        if answer is None:
            return False
        if answer:
            return self._save_active()
        self._discard_active()
        self._dirty = False
        return True

    def _discard_active(self) -> None:
        choice = self._active
        if choice is None:
            return
        if choice.key:
            try:
                saved = terrain_kit.load_project_tileset(self._project.directory, choice.key)
                choice.atlas = saved.atlas
                choice.layout = saved.layout
            except (OSError, ValueError):
                choice.layout = None
        else:
            choice.layout = None

    def save(self) -> None:
        self._save_active()

    def _name_and_source(self, title: str) -> tuple[str, Path] | None:
        if self._dirty:
            answer = messagebox.askyesnocancel(
                "Save swatches?", "Save the current swatch changes before creating another tileset?", parent=self
            )
            if answer is None:
                return None
            if answer:
                if not self._save_active():
                    return None
            else:
                self._discard_active()
                self._dirty = False
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

    def _import_from_tileset(self) -> None:
        destination = self._active
        if destination is None:
            return
        if destination.key is None:
            messagebox.showinfo(
                "Import from tileset",
                "Game atlases are read-only images. Use “New from swatches…” to make a project tileset first.",
                parent=self,
            )
            return
        sources = [choice for choice in self._choices if choice is not destination]
        if not sources:
            messagebox.showinfo("Import from tileset", "There is no other tileset to import from.", parent=self)
            return
        dialog = _SwatchImportDialog(self, sources, self._layout)
        self.wait_window(dialog)
        if dialog.result is None:
            return
        source, picked = dialog.result
        destination_layout = self._layout(destination)
        source_layout = self._layout(source)
        base_swatch = destination_layout.swatches[destination_layout.base]
        base_image = destination.atlas.crop((base_swatch.x, base_swatch.y,
                                             base_swatch.x + base_swatch.w, base_swatch.y + base_swatch.h))
        base = np.asarray(_square(base_image, 512))
        extras: list[tuple[str, np.ndarray]] = []
        for index, swatch in enumerate(destination_layout.swatches):
            if index == destination_layout.base:
                continue
            crop = destination.atlas.crop((swatch.x, swatch.y, swatch.x + swatch.w, swatch.y + swatch.h))
            extras.append((swatch.name, np.asarray(_tile_image(crop))))
        for index in picked:
            swatch = source_layout.swatches[index]
            crop = source.atlas.crop((swatch.x, swatch.y, swatch.x + swatch.w, swatch.y + swatch.h))
            extras.append((swatch.name, np.asarray(_tile_image(crop))))
        try:
            data, layout = tp.build_atlas(base, extras)
        except ValueError as exc:
            messagebox.showerror(
                "Import from tileset",
                f"{exc}\n\nRemove unneeded destination swatches to make room, then try again.",
                parent=self,
            )
            return
        layout.swatches[layout.base].name = base_swatch.name
        destination.atlas = Image.fromarray(data, "RGBA")
        destination.layout = layout
        self._selected_swatch = None
        self._dirty = True
        self._refresh_swatch_table()
        self._draw_preview()

    def _add_images(self) -> None:
        choice = self._active
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
        try:
            layout = self._layout(choice)
            atlas = choice.atlas.copy()
            for index, path in zip(picked, paths):
                swatch = layout.swatches[index]
                image = Image.open(path).convert("RGBA").resize((swatch.w, swatch.h), Image.LANCZOS)
                atlas.paste(image, (swatch.x, swatch.y))
                swatch.name = Path(path).stem
        except (OSError, ValueError) as exc:
            messagebox.showerror("Import swatches", str(exc), parent=self)
            return
        choice.atlas = atlas
        self._dirty = True
        self._refresh_swatch_table()
        self._draw_preview()
