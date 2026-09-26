"""The Build tab's windows onto the open chapter map.

- :class:`MapObjectsWindow` - every placed object (``mapbuildinst``) in a
  table, each editable: object, tile, angle, height and the tiles it covers.
- :class:`MapSettingsWindow` - capacity scale, light, fog, grid colour and
  the ``mapextra`` record, and the water surface (import, flow).
- :class:`Map3DWindow` - the whole chapter in 3D (``map_scene.build_map_scene``),
  rebuilt on a worker thread after each edit.

They edit through the :class:`~.map_builder.MapBuilder` (``edit_map()``,
``edit_instance()``...), so every edit is on the Build tab's Undo/Redo, and
follow the :class:`~.map_editor.MapEditor`'s change listener."""

from __future__ import annotations

import queue
import struct
import threading
import tkinter as tk
from tkinter import messagebox, ttk

from .. import map_props
from ..formats import map_file
from . import map_scene
from .model_viewer import _ModelPreview
from .widgets import ScrollFrame

ANGLES = {"0°": 0, "90°": 192, "180°": 128, "270°": 64}
LIGHT_FIELDS = ["enabled", "unknown1", "unknown2", "model_red", "model_green", "model_blue", "light_red", "light_green", "light_blue"]
FOG_FIELDS = ["enabled", "unused1", "effect_type", "transparency", "red", "green", "blue", "unused2"]
GRID_FIELDS = ["unknown", "red", "green", "blue"]
EXTRA_FIELDS = [
    "panel_offset_x",
    "panel_offset_y",
    "half_x_size",
    "half_y_size",
    "texture_projection_extent_x2",
    "grid_buffer",
    "unknown_tail",  # map flags: 0x20 water, 0x10000000 roof/house tile rectangles
]


def angle_label(angle: int) -> str:
    angle %= 256
    return next((k for k, v in ANGLES.items() if v == angle), str(angle))


def parse_angle(text: str) -> int:
    text = text.strip()
    if text in ANGLES:
        return ANGLES[text]
    value = int(text.rstrip("°"))
    if not 0 <= value <= 255:
        raise ValueError("An angle is 0°, 90°, 180°, 270° or a raw byte 0-255.")
    return value


class _Window(tk.Toplevel):
    """A window following the builder's map: ``_map_changed()`` runs after
    each change, and closing it stops that."""

    def __init__(self, builder, title: str, geometry: str) -> None:
        super().__init__(builder)
        self.builder = builder
        self.map = builder.map_editor
        self._base_title = title
        self.geometry(geometry)
        self.transient(builder.winfo_toplevel())
        self.map.add_listener(self._on_map_changed)
        self.protocol("WM_DELETE_WINDOW", self.close)
        self.bind("<Control-z>", lambda e: builder.undo())
        self.bind("<Control-y>", lambda e: builder.redo())
        self._set_title()

    def _set_title(self) -> None:
        self.title(f"{self._base_title} - {self.map.map_name}" if self.map.map_name else self._base_title)

    def _on_map_changed(self) -> None:
        if self.winfo_exists():
            self._set_title()
            self._map_changed()

    def _map_changed(self) -> None:
        pass

    def close(self) -> None:
        self.map.remove_listener(self._on_map_changed)
        self.destroy()


# -- objects -------------------------------------------------------------------------------


class _AddInstanceDialog(tk.Toplevel):
    """Pick an object, a tile and a quarter-turn angle for a new instance."""

    def __init__(self, parent, names: list[str], selected: str | None, tile: tuple[int, int]) -> None:
        super().__init__(parent)
        self.title("Add object")
        self.transient(parent)
        self.result = None
        body = ttk.Frame(self, padding=10)
        body.pack(fill="both", expand=True)
        self._name = tk.StringVar(value=selected if selected in names else names[0])
        self._x, self._y = tk.StringVar(value=str(tile[0])), tk.StringVar(value=str(tile[1]))
        self._angle = tk.StringVar(value="0°")
        rows = (
            ("Object", ttk.Combobox(body, textvariable=self._name, values=names, state="readonly", width=24)),
            ("Tile x", ttk.Spinbox(body, textvariable=self._x, from_=-128, to=127, width=8)),
            ("Tile y", ttk.Spinbox(body, textvariable=self._y, from_=-128, to=127, width=8)),
            ("Angle", ttk.Combobox(body, textvariable=self._angle, values=list(ANGLES), state="readonly", width=8)),
        )
        for row, (label, widget) in enumerate(rows):
            ttk.Label(body, text=label).grid(row=row, column=0, sticky="w", pady=2)
            widget.grid(row=row, column=1, sticky="w", pady=2, padx=(8, 0))
        ttk.Label(body, text="It is placed on the ground there.", style="Muted.TLabel").grid(
            row=4, column=0, columnspan=2, sticky="w", pady=(4, 0))
        buttons = ttk.Frame(body)
        buttons.grid(row=5, column=0, columnspan=2, sticky="e", pady=(8, 0))
        ttk.Button(buttons, text="Place", command=self._ok).pack(side="left")
        ttk.Button(buttons, text="Cancel", command=self.destroy).pack(side="left", padx=(6, 0))
        self.grab_set()

    def _ok(self) -> None:
        try:
            x, y = int(self._x.get()), int(self._y.get())
        except ValueError:
            messagebox.showerror("Add object", "Tile x and y are whole numbers.", parent=self)
            return
        self.result = (self._name.get(), x, y, ANGLES[self._angle.get()])
        self.destroy()


class MapObjectsWindow(_Window):
    """Every object placed on the map, each editable. Selecting a row
    selects the object on the Build canvas and the other way round."""

    COLUMNS = (("index", "#", 44), ("name", "Object", 190), ("x", "X", 44), ("y", "Y", 44), ("angle", "Angle", 56),
               ("height", "Height", 64), ("covers", "Covers tiles", 130), ("note", "", 110))

    def __init__(self, builder) -> None:
        super().__init__(builder, "Objects", "1220x700")
        self._syncing = False
        self._rows: dict[str, int] = {}
        self._vars: dict[str, tk.StringVar] = {}
        self._shown: int | None = None

        bar = ttk.Frame(self, padding=(8, 8, 8, 4))
        bar.pack(fill="x")
        ttk.Label(bar, text="Search").pack(side="left")
        self._search = tk.StringVar()
        self._search.trace_add("write", lambda *_: self._fill())
        ttk.Entry(bar, textvariable=self._search, width=22).pack(side="left", padx=(6, 12))
        self._grid_only = tk.BooleanVar(value=False)
        ttk.Checkbutton(bar, text="Only on the map grid", variable=self._grid_only, command=self._fill).pack(side="left")
        ttk.Button(bar, text="Add...", command=self._add).pack(side="right")
        self._count = ttk.Label(bar, text="", style="Muted.TLabel")
        self._count.pack(side="right", padx=(0, 10))

        body = ttk.Frame(self)
        body.pack(fill="both", expand=True, padx=8, pady=(0, 8))
        self._form = ttk.Frame(body, padding=(12, 0, 0, 0), width=380)
        self._form.pack(side="right", fill="y")
        self._form.pack_propagate(False)
        self._form.grid_propagate(False)
        left = ttk.Frame(body)
        left.pack(side="left", fill="both", expand=True)
        self._tree = ttk.Treeview(left, columns=[c[0] for c in self.COLUMNS], show="headings", selectmode="browse")
        for key, title, width in self.COLUMNS:
            self._tree.heading(key, text=title)
            self._tree.column(key, width=width, stretch=key == "name", anchor="w" if key in ("name", "covers", "note") else "e")
        ybar = ttk.Scrollbar(left, orient="vertical", command=self._tree.yview)
        self._tree.configure(yscrollcommand=ybar.set)
        ybar.pack(side="right", fill="y")
        self._tree.pack(side="left", fill="both", expand=True)
        self._tree.bind("<<TreeviewSelect>>", lambda e: self._row_selected())
        self._tree.bind("<Delete>", lambda e: self._delete())

        self._fill()
        self.show_instance(builder.selected_instance())

    # -- table ---------------------------------------------------------------------------
    def _map_changed(self) -> None:
        self._fill()

    def _fill(self) -> None:
        data = self.map.map_data
        selected = self.selected()
        self._tree.delete(*self._tree.get_children())
        self._rows = {}
        if data is None:
            self._count.configure(text="")
            self._show_form(None)
            return
        cap = data.capacity
        text = self._search.get().strip().lower()
        for i, inst in enumerate(data.build_inst):
            obj = data.build_desc[inst.desc_index] if 0 <= inst.desc_index < len(data.build_desc) else None
            name = obj.filename if obj is not None else f"? (object {inst.desc_index})"
            on_grid = cap is not None and 0 <= inst.x < cap.x_size and 0 <= inst.y < cap.y_size
            terrain = obj is not None and map_file.is_base_terrain_object(obj)
            if text and text not in name.lower() or self._grid_only.get() and (not on_grid or terrain):
                continue
            note = "map terrain" if terrain else "" if on_grid else "off the grid"
            if obj is not None and not terrain and f"{obj.filename}.gs" not in self.map.pak_contents:
                note = "no model (marker)"
            row = self._tree.insert("", "end", values=(
                i, name, inst.x, inst.y, angle_label(inst.angle), f"{round(inst.height(), 3) + 0.0:g}",
                f"({inst.x2}, {inst.y2})–({inst.end_x2}, {inst.end_y2})", note))
            self._rows[row] = i
        self._count.configure(text=f"{len(self._rows)} of {len(data.build_inst)} objects")
        if selected is not None:
            self._select_row(selected)
        self._show_form(selected)

    def selected(self) -> int | None:
        selection = self._tree.selection()
        return self._rows.get(selection[0]) if selection else None

    def _select_row(self, index: int | None) -> None:
        row = next((r for r, i in self._rows.items() if i == index), None)
        self._syncing = True
        try:
            if row is None:
                self._tree.selection_remove(self._tree.selection())
            else:
                self._tree.selection_set(row)
                self._tree.see(row)
        finally:
            self.update_idletasks()
            self._syncing = False

    def show_instance(self, index: int | None) -> None:
        """Select ``index`` (the Build canvas selected it)."""
        if index != self.selected():
            self._select_row(index)
            self._show_form(index)

    def _row_selected(self) -> None:
        if self._syncing:
            return
        index = self.selected()
        self._show_form(index)
        if index is not None:
            self.builder.select_instance(index)

    # -- form ----------------------------------------------------------------------------
    def _show_form(self, index: int | None) -> None:
        for child in self._form.winfo_children():
            child.destroy()
        self._vars = {}
        self._shown = index
        data = self.map.map_data
        if data is None or index is None or index >= len(data.build_inst):
            ttk.Label(self._form, text="Select an object to edit it.", style="Muted.TLabel").pack(anchor="w")
            return
        inst = data.build_inst[index]
        names = [f"{i}  {o.filename}" for i, o in enumerate(data.build_desc)]
        current = names[inst.desc_index] if 0 <= inst.desc_index < len(names) else str(inst.desc_index)
        ttk.Label(self._form, text=f"Object {index}", font=("Segoe UI", 11, "bold")).grid(row=0, column=0, columnspan=4, sticky="w")
        grid = ttk.Frame(self._form)
        grid.grid(row=1, column=0, columnspan=4, sticky="w", pady=(8, 0))

        def field(row, label, key, value, width=8, values=None, col=0):
            ttk.Label(grid, text=label).grid(row=row, column=col, sticky="w", pady=3, padx=(0 if col == 0 else 12, 6))
            var = tk.StringVar(value=value)
            if values is not None:
                widget = ttk.Combobox(grid, textvariable=var, values=values, width=width)
            else:
                widget = ttk.Entry(grid, textvariable=var, width=width)
            widget.grid(row=row, column=col + 1, sticky="w")
            widget.bind("<Return>", lambda e: self._apply())
            self._vars[key] = var

        field(0, "Object", "desc", current, width=24, values=names)
        field(1, "Tile x", "x", str(inst.x))
        field(2, "Tile y", "y", str(inst.y))
        field(3, "Angle", "angle", angle_label(inst.angle), values=list(ANGLES))
        field(4, "Height", "height", f"{inst.height():g}", width=12)
        ttk.Label(grid, text="Covers tiles", style="Muted.TLabel").grid(row=5, column=0, columnspan=2, sticky="w", pady=(10, 0))
        field(6, "From x", "x2", str(inst.x2))
        field(7, "From y", "y2", str(inst.y2))
        field(8, "To x", "end_x2", str(inst.end_x2))
        field(9, "To y", "end_y2", str(inst.end_y2))

        ground = None
        cap = data.capacity
        if cap is not None and 0 <= inst.x < cap.x_size and 0 <= inst.y < cap.y_size:
            try:
                (ground,) = map_props.tile_heights(self.map.pak_contents, data, [(inst.x, inst.y)])
            except Exception:  # noqa: BLE001 - no terrain model: no ground hint
                ground = None
        hint = ("Height is the game's value (the model sits at -5 × height). "
                "Moving keeps the object's height above the ground; turning recomputes the covered tiles.")
        if ground is not None:
            hint += f" The ground at this tile is {round(ground, 4) + 0.0:g}."
        ttk.Label(self._form, text=hint, style="Muted.TLabel", wraplength=320, justify="left").grid(
            row=2, column=0, columnspan=4, sticky="w", pady=(10, 0))
        buttons = ttk.Frame(self._form)
        buttons.grid(row=3, column=0, columnspan=4, sticky="w", pady=(10, 0))
        ttk.Button(buttons, text="Apply", command=self._apply).pack(side="left")
        if ground is not None:
            ttk.Button(buttons, text="Put on the ground",
                       command=lambda: self.builder.edit_instance(index, height=ground)).pack(side="left", padx=(6, 0))
        ttk.Button(buttons, text="Delete", command=self._delete).pack(side="left", padx=(6, 0))
        obj = data.build_desc[inst.desc_index] if 0 <= inst.desc_index < len(data.build_desc) else None
        if obj is not None:
            more = ttk.Frame(self._form)
            more.grid(row=4, column=0, columnspan=4, sticky="w", pady=(6, 0))
            ttk.Button(more, text="View model...", command=lambda: self.map.view_model(self, obj.filename)).pack(side="left")
            ttk.Button(more, text="Export .glb...", command=lambda: self.map.export_prop(self, obj.filename)).pack(side="left", padx=(6, 0))

    def _apply(self) -> None:
        index = self._shown
        data = self.map.map_data
        if index is None or data is None or index >= len(data.build_inst):
            return
        inst = data.build_inst[index]
        try:
            desc = int(self._vars["desc"].get().split()[0])
            x, y = int(self._vars["x"].get()), int(self._vars["y"].get())
            angle = parse_angle(self._vars["angle"].get())
            height = float(self._vars["height"].get())
            rect = tuple(int(self._vars[k].get()) for k in ("x2", "y2", "end_x2", "end_y2"))
            if not 0 <= desc < len(data.build_desc):
                raise ValueError(f"There is no object {desc}.")
            if any(not -128 <= v <= 127 for v in (x, y, *rect)):
                raise ValueError("Tile coordinates are whole numbers from -128 to 127.")
        except (ValueError, IndexError) as exc:
            messagebox.showerror("Objects", str(exc), parent=self)
            return
        changes = {}
        if desc != inst.desc_index:
            changes["desc"] = desc
        if (x, y) != (inst.x, inst.y):
            changes["tile"] = (x, y)
        if angle != inst.angle % 256:
            changes["angle"] = angle
        if f"{height:g}" != f"{inst.height():g}":
            changes["height"] = height
        if rect != (inst.x2, inst.y2, inst.end_x2, inst.end_y2):
            changes["rect"] = rect
        if changes:
            self.builder.edit_instance(index, **changes)

    def _add(self) -> None:
        data = self.map.map_data
        if data is None:
            return
        names = map_props.prop_names(self.map.pak_contents, data)
        if not names:
            messagebox.showinfo("Add object", "This map has no prop models.", parent=self)
            return
        index = self.selected()
        selected = data.build_desc[data.build_inst[index].desc_index].filename if index is not None else None
        tile = (data.build_inst[index].x, data.build_inst[index].y) if index is not None else (0, 0)
        dialog = _AddInstanceDialog(self, names, selected, tile)
        self.wait_window(dialog)
        if dialog.result is not None:
            self.builder.add_instance(*dialog.result)

    def _delete(self) -> None:
        index = self.selected()
        if index is not None:
            self.builder.delete_instance(index)


# -- map settings -----------------------------------------------------------------------------


class MapSettingsWindow(_Window):
    """The map-wide records (capacity scale, light, fog, grid colour, extra)
    and the water surface."""

    SECTIONS = [
        ("light", "Light", LIGHT_FIELDS, map_file.patch_light_field),
        ("fog", "Fog", FOG_FIELDS, map_file.patch_fog_field),
        ("grid", "Grid colour", GRID_FIELDS, map_file.patch_grid_field),
        ("extra", "Extra (mapextra)", EXTRA_FIELDS, map_file.patch_extra_field),
    ]

    def __init__(self, builder) -> None:
        super().__init__(builder, "Map settings", "780x720")
        scroll = ScrollFrame(self, padding=12)
        scroll.pack(fill="both", expand=True)
        self._body = scroll.body
        self._vars: dict[str, tk.StringVar] = {}
        self._render()

    def _map_changed(self) -> None:
        self._render()

    def _render(self) -> None:
        for child in self._body.winfo_children():
            child.destroy()
        self._vars = {}
        data = self.map.map_data
        if data is None or data.capacity is None:
            ttk.Label(self._body, text="No map is open.", style="Muted.TLabel").grid(row=0, column=0, sticky="w")
            return
        form = self._body
        cap = data.capacity
        ttk.Label(form, text="Map capacity", font=("Segoe UI", 10, "bold")).grid(row=0, column=0, columnspan=8, sticky="w")
        ttk.Label(form, text=f"Grid {cap.x_size} × {cap.y_size}   ·   {cap.build_desc_count} object types   ·   "
                             f"{cap.build_inst_count} placed objects", style="Muted.TLabel").grid(
            row=1, column=0, columnspan=8, sticky="w", pady=(0, 4))
        ttk.Label(form, text="scale_unit").grid(row=2, column=0, sticky="w")
        var = tk.StringVar(value=str(cap.scale_unit))
        ttk.Entry(form, textvariable=var, width=10).grid(row=2, column=1, sticky="w")
        self._vars["capacity:scale_unit"] = var
        row = 3
        for prefix, title, fields, _patch in self.SECTIONS:
            record = getattr(data, prefix)
            if record is None:
                continue
            ttk.Label(form, text=title, font=("Segoe UI", 10, "bold")).grid(row=row, column=0, columnspan=8, sticky="w", pady=(12, 2))
            row += 1
            col = 0
            for f in fields:
                ttk.Label(form, text=f).grid(row=row, column=col, sticky="w", padx=(0 if col == 0 else 10, 4))
                var = tk.StringVar(value=str(getattr(record, f)))
                ttk.Entry(form, textvariable=var, width=10).grid(row=row, column=col + 1, sticky="w", pady=1)
                self._vars[f"{prefix}:{f}"] = var
                col += 2
                if col >= 6:
                    col, row = 0, row + 1
            row += 1 if col else 0
        ttk.Label(form, text="unknown_tail holds the map flags: 0x20 water, 0x10000000 roof/house tile rectangles.",
                  style="Muted.TLabel").grid(row=row, column=0, columnspan=8, sticky="w", pady=(4, 0))
        ttk.Button(form, text="Apply", command=self._apply).grid(row=row + 1, column=0, sticky="w", pady=(10, 0))

        waters = self.map.water_names()
        ttk.Label(form, text="Water", font=("Segoe UI", 10, "bold")).grid(row=row + 2, column=0, columnspan=8, sticky="w", pady=(18, 2))
        ttk.Label(form, text=("Water objects: " + ", ".join(waters)) if waters else "This map has no water.",
                  style="Muted.TLabel").grid(row=row + 3, column=0, columnspan=8, sticky="w")
        water = ttk.Frame(form)
        water.grid(row=row + 4, column=0, columnspan=8, sticky="w", pady=(4, 0))
        ttk.Button(water, text="Import water .glb...", command=lambda: self._undoable(lambda: self.map.import_water(self))).pack(side="left")
        ttk.Button(water, text="Water flow...", command=lambda: self._undoable(lambda: self.map.water_flow(self))).pack(side="left", padx=(6, 0))

    def _undoable(self, action) -> None:
        self.builder.run_undoable(action)

    def _apply(self) -> None:
        data = self.map.map_data
        if data is None:
            return
        try:
            pending = [(data.capacity, "scale_unit", float(self._vars["capacity:scale_unit"].get()), map_file.patch_capacity_field)]
            for prefix, _title, fields, patch in self.SECTIONS:
                record = getattr(data, prefix)
                if record is None:
                    continue
                for f in fields:
                    value = int(self._vars[f"{prefix}:{f}"].get(), 0)
                    if value != getattr(record, f):
                        pending.append((record, f, value, patch))
        except ValueError as exc:
            messagebox.showerror("Map settings", str(exc), parent=self)
            return
        if pending[0][2] == data.capacity.scale_unit:
            pending.pop(0)
        if not pending:
            return

        def edit(files):
            out = files["map.bin"]
            for record, f, value, patch in pending:  # patching never moves a record
                out = patch(out, record, f, value)
            files["map.bin"] = out

        try:
            self.builder.edit_map(edit, "Changed " + ", ".join(sorted({f for _r, f, _v, _p in pending})), raise_errors=True)
        except (struct.error, OverflowError, map_file.MapFileError) as exc:
            messagebox.showerror("Could not apply", str(exc), parent=self)


# -- 3D view ----------------------------------------------------------------------------------


class Map3DWindow(_Window):
    """The whole chapter in 3D: terrain and every placed prop. Rebuilt on a
    worker thread shortly after each edit."""

    DELAY_MS = 1200

    def __init__(self, builder) -> None:
        super().__init__(builder, "3D view", "1100x760")
        bar = ttk.Frame(self, padding=(8, 8, 8, 4))
        bar.pack(fill="x")
        ttk.Button(bar, text="Re-render", command=lambda: self._request(0)).pack(side="left")
        self._auto = tk.BooleanVar(value=True)
        ttk.Checkbutton(bar, text="Update after each edit", variable=self._auto).pack(side="left", padx=(10, 0))
        self._status = ttk.Label(bar, text="", style="Muted.TLabel")
        self._status.pack(side="left", padx=(12, 0))
        self._preview = _ModelPreview(self, mesh_only=True)
        self._preview.pack(fill="both", expand=True, padx=8, pady=(0, 8))
        self._after = None
        self._generation = 0
        self._request(0)

    def _map_changed(self) -> None:
        if self._auto.get():
            self._request(self.DELAY_MS)
        else:
            self._status.configure(text="The map changed: Re-render to update.")

    def _request(self, delay: int) -> None:
        if self._after is not None:
            self.after_cancel(self._after)
        self._after = self.after(delay, self._render)

    def _render(self) -> None:
        self._after = None
        data = self.map.map_data
        if data is None:
            self._preview.show(None, "No map is open.")
            return
        self._generation += 1
        generation = self._generation
        files = dict(self.map.pak_contents)
        results: "queue.Queue" = queue.Queue()

        def worker() -> None:
            try:
                results.put(("ok", map_scene.build_map_scene(files, data)))
            except Exception as exc:  # noqa: BLE001
                results.put(("error", str(exc)))

        self._status.configure(text="Rendering…")
        threading.Thread(target=worker, daemon=True).start()
        self._poll(results, generation, data)

    def _poll(self, results: "queue.Queue", generation: int, data) -> None:
        if not self.winfo_exists():
            return
        try:
            status, payload = results.get_nowait()
        except queue.Empty:
            self.after(120, lambda: self._poll(results, generation, data))
            return
        if generation != self._generation:
            return
        if status == "error":
            self._status.configure(text=f"Could not render: {payload}")
            return
        self._preview.show(payload)
        self._preview.set_grid(map_scene.compute_grid_overlay(data))
        self._preview.set_gameplay_grid(map_scene.compute_gameplay_grid_overlay(data))
        cap = data.capacity
        self._status.configure(text=f"{len(payload.triangles):,} triangles" + (f" · grid {cap.x_size}×{cap.y_size}" if cap else ""))

    def close(self) -> None:
        if self._after is not None:
            self.after_cancel(self._after)
        self._preview.cleanup()
        super().close()
