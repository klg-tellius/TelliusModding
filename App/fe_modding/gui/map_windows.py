"""The Build tab's windows onto the open chapter map.

- :class:`MapObjectsWindow` - every placed object (``mapbuildinst``) in a
  table, each editable: object, tile, angle, height and the tiles it covers.
- :class:`MapSettingsWindow` - :class:`MapSettingsForm` (capacity scale,
  lighting, fog, grid colour, the grid border and the rest of ``mapextra``,
  the water surface: import, flow; each chapter's Settings tab shows it too),
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
from tkinter import colorchooser, messagebox, ttk

from .. import map_props
from ..formats import fe8data, map_file
from . import map_scene
from .model_viewer import _ModelPreview
from .widgets import ScrollFrame, info, tip

ANGLES = {"0°": 0, "90°": 192, "180°": 128, "270°": 64}


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
            ttk.Button(more, text="Object flags...", command=lambda: self._object_flags(inst.desc_index)).pack(side="left", padx=(6, 0))

    def _object_flags(self, desc_index: int) -> None:
        data = self.map.map_data
        if data is None or not 0 <= desc_index < len(data.build_desc):
            return
        obj = data.build_desc[desc_index]
        dialog = tk.Toplevel(self)
        dialog.title(f"Object flags — {obj.filename}")
        dialog.transient(self)
        frame = ttk.Frame(dialog, padding=12)
        frame.pack(fill="both", expand=True)
        fields = ("flag_bits_a", "flag_bits_b", "flag_bits_c", "effect_type")
        raw = {}
        for row, field in enumerate(fields):
            ttk.Label(frame, text=field.replace("_", " ")).grid(row=row, column=0, sticky="w", pady=2)
            raw[field] = tk.StringVar(value=f"0x{getattr(obj, field):02X}")
            ttk.Entry(frame, textvariable=raw[field], width=8).grid(row=row, column=1, sticky="w", padx=(8, 0))
        ttk.Label(frame, text=("Base terrain: yes" if map_file.is_base_terrain_object(obj) else "Base terrain: no")
                  + ("   ·   .ga animation: yes" if map_file.has_ga_animation(obj) else "   ·   .ga animation: no"),
                  style="Muted.TLabel").grid(row=4, column=0, columnspan=2, sticky="w", pady=(8, 3))
        toggles = (
            ("flag_bits_b", 0x01, "Skip placed-object draw (B bit 0)"),
            ("flag_bits_b", 0x02, "Initially hidden (B bit 1)"),
            ("flag_bits_b", 0x10, "Exclude from footprint test (B bit 4)"),
            ("flag_bits_c", 0x04, "Advance animation timer (C bit 2)"),
            ("flag_bits_c", 0x08, "Footprint test candidate (C bit 3)"),
            ("flag_bits_c", 0x10, "Footprint test candidate (C bit 4)"),
            ("flag_bits_c", 0x20, "Projected texture target (C bit 5)"),
            ("effect_type", 0x01, "Second actor update pass (effect bit 0)"),
            ("effect_type", 0x02, "Copy roof height to base layer too (effect bit 1)"),
            ("effect_type", 0x08, "Extended frustum test (effect bit 3)"),
            ("effect_type", 0x10, "Exclude from footprint test (effect bit 4)"),
            ("effect_type", 0x40, "Skip placed-object draw (effect bit 6)"),
            ("effect_type", 0x80, "Exclude from tile-object lookup (effect bit 7)"),
        )
        checks = []
        for row, (field, mask, label) in enumerate(toggles if self.map.verified_us_map_layout else (), start=5):
            initial = bool(getattr(obj, field) & mask)
            var = tk.BooleanVar(value=initial)
            ttk.Checkbutton(frame, text=label, variable=var).grid(row=row, column=0, columnspan=2, sticky="w")
            checks.append((field, mask, initial, var))
        ttk.Label(frame, text="These flags belong to the object definition and affect every placement. "
                  "C bit 0 is probably unused in the US build; raw bytes preserve it. "
                  "The footprint test also depends on map flags and runtime state.",
                  style="Muted.TLabel", wraplength=390, justify="left").grid(row=18, column=0, columnspan=2, sticky="w", pady=(8, 0))

        def apply() -> None:
            try:
                values = {field: int(var.get(), 0) for field, var in raw.items()}
                if any(not 0 <= value <= 255 for value in values.values()):
                    raise ValueError("Each raw flag must be a byte (0–255).")
                for field, mask, initial, var in checks:
                    if var.get() != initial:
                        values[field] = (values[field] | mask) if var.get() else (values[field] & ~mask)
                changed = {field: value for field, value in values.items() if value != getattr(obj, field)}
                if changed:
                    def edit(files):
                        out = files["map.bin"]
                        for field, value in changed.items():
                            out = map_file.patch_object_field(out, obj, field, value)
                        files["map.bin"] = out
                    self.builder.edit_map(edit, f"Changed flags of {obj.filename}", raise_errors=True)
            except (ValueError, struct.error, map_file.MapFileError) as exc:
                messagebox.showerror("Object flags", str(exc), parent=dialog)
                return
            dialog.destroy()

        ttk.Button(frame, text="Apply", command=apply).grid(row=19, column=0, sticky="w", pady=(10, 0))
        dialog.grab_set()

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

#: The map-wide records the settings form edits: ``(attribute, title, patch, rows)``, a row being
#: ``(field, label)`` or ``("rgb", label, (red, green, blue))`` (three byte fields and a colour picker).
SETTINGS_SECTIONS = [
    ("light", "Lighting", map_file.patch_light_field, [
        ("enabled", "Enabled"), ("angle_y", "Light Y angle (°)"), ("angle_z", "Light Z angle (°)"),
        ("rgb", "Model colour", ("model_red", "model_green", "model_blue")),
        ("rgb", "Light colour", ("light_red", "light_green", "light_blue")),
    ]),
    ("fog", "Fog", map_file.patch_fog_field, [
        ("enabled", "Enabled"), ("mode_code", "Mode code"),
        ("start_distance", "Start distance"), ("end_distance", "End distance"),
        ("rgb", "Fog colour", ("red", "green", "blue")),
        ("unused2", "Unused 2"),
    ]),
    ("grid", "Grid colour", map_file.patch_grid_field, [
        ("unknown", "Stored alpha (draw uses SetGrid)"), ("rgb", "Grid colour", ("red", "green", "blue")),
    ]),
    ("extra", "Grid size & map extra (mapextra)", map_file.patch_extra_field, [
        ("grid_buffer", "Grid border (tiles)"), ("half_x_size", "Half width"), ("half_y_size", "Half height"),
        ("panel_offset_x", "Panel offset X"), ("panel_offset_y", "Panel offset Y"),
        ("texture_projection_extent_x2", "Texture extent ×2"),
        ("sight_code", "Sight code (difficulty 1)"), ("weather_id", "Weather ID (0–17)"),
        ("preserve_object_order", "Keep object file order (0/1)"),
        ("unknown_tail", "Raw map flags"),
    ]),
]


def _section_fields(rows) -> list[str]:
    return [f for row in rows for f in (row[2] if row[0] == "rgb" else (row[0],))]


LIGHT_FIELDS, FOG_FIELDS, GRID_FIELDS, EXTRA_FIELDS = (_section_fields(rows) for _a, _t, _p, rows in SETTINGS_SECTIONS)


def _hex_colour(rgb) -> str | None:
    """``#rrggbb`` of three byte values (ints or text), None when one isn't a byte."""
    try:
        values = [int(v, 0) if isinstance(v, str) else int(v) for v in rgb]
    except ValueError:
        return None
    return "#%02x%02x%02x" % tuple(values) if len(values) == 3 and all(0 <= v <= 255 for v in values) else None


#: Weather ids (mapextra bits 20-24, 0-17; ``spawn_map_weather_children_for_current_chapter``).
#: The names come from the effect each id starts, or from its battle sky (BattleSkyData: 12
#: night_01, 13 sunset_01, 15 mountain_01); the others name the vanilla map that uses them.
WEATHER_NAMES = {
    0: "None", 1: "Light overlay (as Ch.6, Ch.17, Ch.23)", 2: "Rain (as Ch.24)", 3: "Light rain (unused)", 4: "Heavy rain (as Ch.8)",
    5: "Snow (as Ch.18, Ch.20)", 6: "Snow 6 (unused)", 7: "Snow 7 (as Ch.19)", 8: "Sandstorm (as Ch.15)", 9: "Effect 9 (unused)",
    10: "Waves (as Ch.13)", 11: "Effect 11 (as Ch.14)", 12: "Night (as Ch.5)", 13: "Sunset (as Ch.4)",
    14: "Effect 14 (as Ch.7, Ch.10)", 15: "Mountain (as Ch.9, Ch.12)", 16: "Effect 16 (unused)",
    17: "Light overlay 2 (as the Prologue)",
}
#: Fog-of-war code (mapextra bits 18-19): the game maps 0/1/2/3 to runtime modes 0/3/1/2
#: and keeps it only on Hard (US/PAL; any difficulty but Normal in JP).
SIGHT_NAMES = {0: "None", 1: "Fog of war, mode 3 (unused in vanilla)", 2: "Fog of war, mode 1 (as Ch.5)",
               3: "Fog of war, mode 2 (as Ch.14)"}
SECTION_HELP = {
    "grid": "The tactical grid: the playable area and how its lines are drawn.",
    "light": "The directional light on the map's models.",
    "fog": "Distance fog: the map fades into this colour away from the camera. Scripts can change it "
           "during the chapter (SetFog).",
    "weather": "Weather and fog of war of the map.",
    "advanced": "Values the engine reads but that rarely need changing.",
}


class MapSettingsForm(ttk.Frame):
    """The open map's map-wide settings, grouped by what they do: the grid
    (size, playable border, line colour), lighting, distance fog, weather and
    fog of war, and an Advanced group (texture projection, panel offsets,
    object order, the other map flag bits); then its water surface. Edits go
    through the builder (``edit_map``), so they are on the Build tab's
    Undo/Redo and Save Chapter writes them. Follows the builder's map.

    Values the game never reads are not offered: maplight ``enabled`` (always
    1), mapfog byte 7, the grid's stored alpha (the draw uses SetGrid) and the
    half sizes, which are kept equal to ceil(size / 2)."""

    def __init__(self, parent, builder) -> None:
        super().__init__(parent)
        self.builder = builder
        self.map = builder.map_editor
        self._vars: dict[str, tk.Variable] = {}
        self.map.add_listener(self._on_map_changed)
        self.bind("<Destroy>", self._on_destroy)
        self.render()

    def _on_destroy(self, event) -> None:
        if event.widget is self:
            self.map.remove_listener(self._on_map_changed)

    def _on_map_changed(self) -> None:
        if self.winfo_exists():
            self.render()

    # -- layout helpers --------------------------------------------------------------------
    def _section(self, row: int, key: str, title: str) -> int:
        head = ttk.Frame(self)
        head.grid(row=row, column=0, columnspan=8, sticky="w", pady=(14, 2))
        ttk.Label(head, text=title, font=("Segoe UI", 10, "bold")).pack(side="left")
        info(head, SECTION_HELP[key]).pack(side="left", padx=(4, 0))
        return row + 1

    def _number(self, row: int, col: int, key: str, label: str, value, help_text: str, unit: str = "") -> None:
        tip(ttk.Label(self, text=label), help_text).grid(row=row, column=col, sticky="w",
                                                         padx=(0 if col == 0 else 14, 6), pady=1)
        cell = ttk.Frame(self)
        cell.grid(row=row, column=col + 1, sticky="w", pady=1)
        var = tk.StringVar(value=str(value))
        tip(ttk.Entry(cell, textvariable=var, width=7), help_text).pack(side="left")
        if unit:
            ttk.Label(cell, text=unit, style="Muted.TLabel").pack(side="left", padx=(4, 0))
        self._vars[key] = var

    def _check(self, row: int, col: int, key: str, label: str, value: bool, help_text: str) -> None:
        var = tk.BooleanVar(value=bool(value))
        tip(ttk.Checkbutton(self, text=label, variable=var), help_text).grid(
            row=row, column=col, columnspan=2, sticky="w", pady=1)
        self._vars[key] = var

    def _choice(self, row: int, key: str, label: str, names: dict, value: int, help_text: str) -> None:
        tip(ttk.Label(self, text=label), help_text).grid(row=row, column=0, sticky="w", padx=(0, 6), pady=1)
        choices = [f"{k} · {name}" for k, name in names.items()]
        if value not in names:
            choices.append(str(value))
        var = tk.StringVar(value=next((c for c in choices if c.split(" ·", 1)[0] == str(value)), str(value)))
        ttk.Combobox(self, textvariable=var, values=choices, state="readonly", width=40).grid(
            row=row, column=1, columnspan=5, sticky="w", pady=1)
        self._vars[key] = var

    def render(self) -> None:
        for child in self.winfo_children():
            child.destroy()
        self._vars = {}
        data = self.map.map_data
        if data is None or data.capacity is None:
            ttk.Label(self, text="This chapter has no map open.", style="Muted.TLabel").grid(row=0, column=0, sticky="w")
            return
        cap, extra, us = data.capacity, data.extra, self.map.verified_us_map_layout
        row = self._section(0, "grid", "Grid")
        size = f"{cap.x_size} × {cap.y_size} tiles"
        tip(ttk.Label(self, text="Map size"), "The whole map, border included. Changing it needs a new map.").grid(
            row=row, column=0, sticky="w")
        ttk.Label(self, text=size, style="Muted.TLabel").grid(row=row, column=1, columnspan=3, sticky="w")
        row += 1
        if extra is not None:
            playable = (f"playable {cap.x_size - 2 * extra.grid_buffer} × {cap.y_size - 2 * extra.grid_buffer}"
                        if 0 < extra.grid_buffer * 2 < min(cap.x_size, cap.y_size) else "")
            self._number(row, 0, "extra:grid_buffer", "Border", extra.grid_buffer,
                         "Tiles along each edge that units and the cursor cannot enter.", "tiles  " + playable)
            row += 1
        if data.grid is not None:
            row = self._colour_row(row, "grid", data.grid, "Line colour", ("red", "green", "blue"),
                                   "Colour of the grid lines (their strength is set by scripts with SetGrid).")
        if data.light is not None:
            row = self._section(row, "light", "Lighting")
            light = data.light
            self._number(row, 0, "light:angle_y", "Direction", light.angle_y,
                         "Horizontal angle of the light, in degrees.", "° around")
            self._number(row, 2, "light:angle_z", "Height", light.angle_z,
                         "Vertical angle of the light, in degrees.", "° up")
            row += 1
            row = self._colour_row(row, "light", light, "Model colour", ("model_red", "model_green", "model_blue"),
                                   "Base colour applied to the map's models.")
            row = self._colour_row(row, "light", light, "Light colour", ("light_red", "light_green", "light_blue"),
                                   "Colour of the directional light.")
        if data.fog is not None:
            row = self._section(row, "fog", "Distance fog")
            fog = data.fog
            self._check(row, 0, "fog:enabled", "Fog on", fog.enabled, "Draw the distance fog on this map.")
            row += 1
            distance_help = "Distance from the camera, in tiles (the game scales it by 5 × map scale)."
            self._number(row, 0, "fog:start_distance", "Starts at", fog.start_distance,
                         "Where the fog begins. " + distance_help, "tiles")
            self._number(row, 2, "fog:end_distance", "Full at", fog.end_distance,
                         "Where the fog hides everything. " + distance_help, "tiles")
            row += 1
            if fog.mode_code:  # 0 on every vanilla map
                self._number(row, 0, "fog:mode_code", "Fog type", fog.mode_code,
                             "Render fog type minus 1. 0 on every vanilla map.")
                row += 1
            row = self._colour_row(row, "fog", fog, "Colour", ("red", "green", "blue"), "Colour of the fog.")
        if extra is not None and us:
            row = self._section(row, "weather", "Weather")
            self._choice(row, "extra:weather_id", "Weather", WEATHER_NAMES, extra.weather_id,
                         "Effect drawn over the map: rain, snow, sandstorm, waves...")
            row += 1
            row = self._sky_row(row, extra.weather_id)
            self._choice(row, "extra:sight_code", "Fog of war", SIGHT_NAMES, extra.sight_code,
                         "Fog of war hides the units outside your units' vision. The game uses it on Hard "
                         "only (any difficulty above Normal in the Japanese release).")
            row += 1
        if extra is not None:
            row = self._section(row, "advanced", "Advanced")
            self._number(row, 0, "extra:texture_projection_extent_x2", "Texture projection",
                         extra.texture_projection_extent_x2,
                         "Twice the size of the map's projected ground texture (the engine uses half of it).")
            row += 1
            self._number(row, 0, "extra:panel_offset_x", "Panel offset X", extra.panel_offset_x,
                         "Read by a 2D panel draw; its effect is not decoded. Keep the vanilla value.")
            self._number(row, 2, "extra:panel_offset_y", "Panel offset Y", extra.panel_offset_y,
                         "Read by a 2D panel draw; its effect is not decoded. Keep the vanilla value.")
            row += 1
            if us:
                self._check(row, 0, "extra:preserve_object_order", "Objects already sorted",
                            extra.preserve_object_order,
                            "Set on every vanilla map. When off, the game sorts the placed objects on load "
                            "and sets it.")
                row += 1
            other = extra.unknown_tail & ~(map_file.MAP_EXTRA_SIGHT_MASK | map_file.MAP_EXTRA_WEATHER_MASK
                                           | map_file.MAP_EXTRA_OBJECT_ORDER_MASK) if us else extra.unknown_tail
            self._number(row, 0, "extra:other_flags", "Other map flags", hex(other),
                         "0x20 draws water, 0x04 and 0x10 pick texture effects, 0x10000000 tests object "
                         "footprints (roofs). 0x02 is set on every vanilla map and not read.")
            row += 1
        ttk.Button(self, text="Apply", style="Accent.TButton", command=self._apply).grid(
            row=row, column=0, sticky="w", pady=(12, 0))
        row += 1

        waters = self.map.water_names()
        head = ttk.Frame(self)
        head.grid(row=row, column=0, columnspan=8, sticky="w", pady=(22, 2))
        ttk.Label(head, text="Water", font=("Segoe UI", 10, "bold")).pack(side="left")
        info(head, "The animated water surface objects of the map.").pack(side="left", padx=(4, 0))
        ttk.Label(self, text=("Water objects: " + ", ".join(waters)) if waters else "This map has no water.",
                  style="Muted.TLabel").grid(row=row + 1, column=0, columnspan=8, sticky="w")
        water = ttk.Frame(self)
        water.grid(row=row + 2, column=0, columnspan=8, sticky="w", pady=(4, 0))
        ttk.Button(water, text="Import water .glb...", command=lambda: self._undoable(lambda: self.map.import_water(self))).pack(side="left")
        ttk.Button(water, text="Water flow...", command=lambda: self._undoable(lambda: self.map.water_flow(self))).pack(side="left", padx=(6, 0))

    def _session(self):
        session = getattr(self.builder, "fe8_session", None)
        session = session() if callable(session) else session
        return session if session is not None and getattr(session, "available", False) else None

    def _sky_row(self, row: int, weather_id: int) -> int:
        """The sky behind this map's battles: BattleSkyData's entry for its weather id."""
        session = self._session()
        if session is None:
            return row
        skies = fe8data.read_battle_skies(session.data)
        current = skies[weather_id] if weather_id < len(skies) else None
        sharing = [i for i, name in enumerate(skies) if name == current and i != weather_id]
        tip(ttk.Label(self, text="Battle sky"),
            f"The sky drawn behind this map's fights: BattleSkyData's entry {weather_id} (the weather id). Every "
            "map with this weather uses it" + (f"; weather ids {', '.join(map(str, sharing))} show the same sky"
                                                if sharing else "") +
            ". It is saved with FE8Data.bin (Chapter data › Save FE8Data.bin).").grid(row=row, column=0, sticky="w")
        cell = ttk.Frame(self)
        cell.grid(row=row, column=1, columnspan=5, sticky="w", pady=1)
        from .battle_scene_editor import scene_models

        names = sorted(scene_models(self.builder.project))
        var = tk.StringVar(value=current or "")
        box = ttk.Combobox(cell, textvariable=var, values=[""] + names, state="readonly", width=24)
        box.pack(side="left")
        box.bind("<<ComboboxSelected>>", lambda e: self._set_sky(weather_id, var.get()))
        ttk.Button(cell, text="Browse in 3D…", command=lambda: self._browse_sky(weather_id, var.get(), names)).pack(
            side="left", padx=(6, 0))
        return row + 1

    def _browse_sky(self, weather_id: int, current: str, names: list[str]) -> None:
        from .battle_scene_editor import BattleSceneBrowser

        dialog = BattleSceneBrowser(self, self.builder.project, names, current or None, title="Battle skies")
        self.wait_window(dialog)
        if dialog.result:
            self._set_sky(weather_id, dialog.result)

    def _set_sky(self, weather_id: int, name: str) -> None:
        session = self._session()
        if session is None:
            return
        skies = list(fe8data.read_battle_skies(session.data))
        while len(skies) <= weather_id:
            skies.append(None)
        if skies[weather_id] == (name or None):
            return
        skies[weather_id] = name or None
        try:
            session.data = fe8data.write_battle_skies(session.data, skies)
        except ValueError as exc:
            messagebox.showerror("Battle sky", str(exc), parent=self)
            return
        session.changed(self)
        self.builder.changelog.append("FE8Data.bin", f"Battle sky of weather {weather_id}: {name or 'none'}")
        self.render()

    def _colour_row(self, row: int, prefix: str, record, label: str, fields, help_text: str) -> int:
        """A colour as a swatch and a picker (which applies at once), with the
        red, green and blue bytes beside it; returns the next free row."""
        tip(ttk.Label(self, text=label), help_text).grid(row=row, column=0, sticky="w", pady=1)
        cell = ttk.Frame(self)
        cell.grid(row=row, column=1, columnspan=5, sticky="w", pady=1)
        names = [f"{prefix}:{f}" for f in fields]
        swatch = tk.Label(cell, width=4, relief="solid", borderwidth=1,
                          bg=_hex_colour([getattr(record, f) for f in fields]) or "#000000")
        swatch.pack(side="left")
        for f, name, letter in zip(fields, names, "RGB"):
            var = tk.StringVar(value=str(getattr(record, f)))
            self._vars[name] = var
            ttk.Label(cell, text=letter, style="Muted.TLabel").pack(side="left", padx=(8, 2))
            ttk.Entry(cell, textvariable=var, width=4).pack(side="left")

        def refresh(*_):
            colour = _hex_colour([self._vars[n].get() for n in names])
            if colour is not None and swatch.winfo_exists():
                swatch.configure(bg=colour)

        for name in names:
            self._vars[name].trace_add("write", refresh)

        def pick():
            initial = _hex_colour([self._vars[n].get() for n in names])
            rgb, _hex = colorchooser.askcolor(initial, parent=self, title=label)
            if rgb is not None:
                for name, value in zip(names, rgb):
                    self._vars[name].set(str(int(value)))
                self._apply()

        ttk.Button(cell, text="Pick...", command=pick).pack(side="left", padx=(10, 0))
        return row + 1

    def _undoable(self, action) -> None:
        self.builder.run_undoable(action)

    def _value(self, key: str) -> int:
        var = self._vars[key]
        if isinstance(var, tk.BooleanVar):
            return int(var.get())
        text = var.get().strip()
        return int(text.split(" ·", 1)[0], 0)

    def _apply(self) -> None:
        data = self.map.map_data
        if data is None:
            return
        patches = {"light": map_file.patch_light_field, "fog": map_file.patch_fog_field,
                   "grid": map_file.patch_grid_field, "extra": map_file.patch_extra_field}
        pending = []
        try:
            for key in self._vars:
                prefix, f = key.split(":", 1)
                if prefix == "extra" and f in ("sight_code", "weather_id", "preserve_object_order", "other_flags"):
                    continue
                record = getattr(data, prefix)
                value = self._value(key)
                if record is not None and value != getattr(record, f):
                    pending.append((record, f, value, patches[prefix]))
            extra = data.extra
            if extra is not None:
                flags = self._value("extra:other_flags")
                if not 0 <= flags <= 0xFFFFFFFF:
                    raise ValueError("Other map flags must be a 32-bit value.")
                if self.map.verified_us_map_layout:
                    known = (map_file.MAP_EXTRA_SIGHT_MASK | map_file.MAP_EXTRA_WEATHER_MASK
                             | map_file.MAP_EXTRA_OBJECT_ORDER_MASK)
                    flags = ((flags & ~known) | (self._value("extra:sight_code") << 18)
                             | (self._value("extra:weather_id") << 20)
                             | (self._value("extra:preserve_object_order") << 29))
                if flags != extra.unknown_tail:
                    pending.append((extra, "unknown_tail", flags, map_file.patch_extra_field))
                if data.capacity is not None:  # keep the half sizes in step with the map size
                    for f, size in (("half_x_size", data.capacity.x_size), ("half_y_size", data.capacity.y_size)):
                        if getattr(extra, f) != (size + 1) // 2:
                            pending.append((extra, f, (size + 1) // 2, map_file.patch_extra_field))
        except ValueError as exc:
            messagebox.showerror("Map settings", str(exc), parent=self)
            return
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


class MapSettingsWindow(_Window):
    """Map-wide settings for the open phase."""

    def __init__(self, builder) -> None:
        super().__init__(builder, "Map settings", "1000x800")
        scroll = ScrollFrame(self, padding=12)
        scroll.pack(fill="both", expand=True)
        MapSettingsForm(scroll.body, builder).pack(fill="x", anchor="w")


# -- 3D view ----------------------------------------------------------------------------------


class Map3DWindow(_Window):
    """The whole chapter in 3D: terrain and every placed prop. Rebuilt on a
    worker thread shortly after each edit."""

    DELAY_MS = 1200

    def __init__(self, builder) -> None:
        super().__init__(builder, "3D view", "1100x760")
        self.resizable(True, True)
        self.minsize(700, 500)
        bar = ttk.Frame(self, padding=(8, 8, 8, 4))
        bar.pack(fill="x")
        ttk.Button(bar, text="Re-render", command=lambda: self._request(0)).pack(side="left")
        ttk.Button(bar, text="Top Down", command=lambda: self._preview._top_down_view()).pack(side="left", padx=(6, 0))
        ttk.Button(bar, text="Reset View", command=lambda: self._preview._reset_view()).pack(side="left", padx=(4, 0))
        self._status = ttk.Label(bar, text="", style="Muted.TLabel")
        self._status.pack(side="left", padx=(12, 0))
        self._preview = _ModelPreview(self, mesh_only=True)
        self._preview.pack(fill="both", expand=True, padx=8, pady=(0, 8))
        self._after = None
        self._generation = 0
        self._request(0)

    def _map_changed(self) -> None:
        self._request(self.DELAY_MS)

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
