"""World Map Routes (Radiant Dawn): the route lines of ``gmap/curve/``
(see :mod:`fe_modding.formats.fe10_gmap_curve`)."""

from __future__ import annotations

import io
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, simpledialog, ttk
from typing import Optional

from PIL import Image, ImageTk

from ..formats import fe10_gmap_curve as gc
from ..formats import lz10, tpl
from ..game_profile import files_root_of
from ..project import ModProject
from . import theme
from .changelog import ChangeLog
from .editor_panel import EditorPanel
from .widgets import info

SCALE = 1.0
COLOURS = {0: "#4f8cff", 1: "#ff5050", 2: "#5adc6e"}


class GmapRoutesEditor(EditorPanel):
    display_name = "World Map Routes"

    def __init__(self, parent: tk.Misc, project: ModProject, changelog: ChangeLog):
        super().__init__(parent)
        self._project = project
        self._changelog = changelog
        self._folder = Path(files_root_of(project)) / "gmap" / "curve"
        self._curves: dict[str, gc.Curve] = {}
        self._lines: dict[int, gc.LineDefine] = {}
        self._changed: set[str] = set()
        self._current: Optional[str] = None
        self._point: Optional[int] = None
        self._backdrops: dict[str, Optional[Image.Image]] = {}
        self._photo = None
        self._dirty = False
        self._build()
        self._load()

    # -- layout ---------------------------------------------------------------------------
    def _build(self) -> None:
        bar = ttk.Frame(self, padding=(8, 8, 8, 4))
        bar.pack(fill="x")
        self._save_button = ttk.Button(bar, text="Save routes", style="Accent.TButton", command=self.save,
                                       state="disabled")
        self._save_button.pack(side="left")
        ttk.Button(bar, text="Revert", command=self._revert).pack(side="left", padx=(6, 0))
        self._status = ttk.Label(bar, text="", style="Muted.TLabel")
        self._status.pack(side="left", padx=(10, 0))
        info(bar, "The lines a world-map event draws along an army's route (gmap/curve/<name>.bin). A route is a "
                  "list of points with tangents in 608 x 448 screen pixels; the line style picks the line picture "
                  "and its width and texture length (Line styles); the colour picks one of the game's colour "
                  "pairs. The preview follows a cubic curve through the points and is approximate.").pack(side="right")

        body = ttk.Frame(self, padding=8)
        body.pack(fill="both", expand=True)
        left = ttk.Frame(body)
        left.pack(side="left", fill="y")
        ttk.Label(left, text="Routes", style="Heading.TLabel").pack(anchor="w")
        self._list = tk.Listbox(left, width=22, height=24, exportselection=False)
        self._list.pack(fill="y", expand=True, pady=(4, 0))
        self._list.bind("<<ListboxSelect>>", lambda e: self._on_curve())
        buttons = ttk.Frame(left)
        buttons.pack(fill="x", pady=(6, 0))
        ttk.Button(buttons, text="Duplicate", command=self._duplicate).pack(side="left")
        ttk.Button(buttons, text="Line styles", command=self._edit_lines).pack(side="left", padx=(4, 0))

        middle = ttk.Frame(body, padding=(12, 0))
        middle.pack(side="left", fill="y")
        form = ttk.Frame(middle)
        form.pack(fill="x")
        self._vars = {k: tk.StringVar() for k in ("frames", "style", "colour")}
        for row, (key, label) in enumerate((("frames", "Frames to draw"), ("style", "Line style (0-7)"),
                                            ("colour", "Colour (0-3)"))):
            ttk.Label(form, text=label).grid(row=row, column=0, sticky="w", pady=2)
            entry = ttk.Entry(form, textvariable=self._vars[key], width=8)
            entry.grid(row=row, column=1, sticky="w", padx=(6, 0))
            entry.bind("<Return>", lambda e: self._apply_curve())
            entry.bind("<FocusOut>", lambda e: self._apply_curve())
        columns = ("n", "x", "y", "tx", "ty")
        self._points = ttk.Treeview(middle, columns=columns, show="headings", height=14, selectmode="browse")
        for c, text, width in zip(columns, ("#", "X", "Y", "Tangent X", "Tangent Y"), (30, 70, 70, 80, 80)):
            self._points.heading(c, text=text)
            self._points.column(c, width=width, anchor="e", stretch=False)
        self._points.pack(fill="y", pady=(8, 0))
        self._points.bind("<<TreeviewSelect>>", lambda e: self._on_point())
        pform = ttk.Frame(middle)
        pform.pack(fill="x", pady=(6, 0))
        self._pvars = {k: tk.StringVar() for k in ("x", "y", "tx", "ty")}
        for col, key in enumerate(("x", "y", "tx", "ty")):
            ttk.Label(pform, text=key.upper()).grid(row=0, column=2 * col, sticky="w", padx=(0 if col == 0 else 6, 2))
            entry = ttk.Entry(pform, textvariable=self._pvars[key], width=8)
            entry.grid(row=0, column=2 * col + 1)
            entry.bind("<Return>", lambda e: self._apply_point())
            entry.bind("<FocusOut>", lambda e: self._apply_point())
        pbuttons = ttk.Frame(middle)
        pbuttons.pack(fill="x", pady=(6, 0))
        ttk.Button(pbuttons, text="Add point", command=self._add_point).pack(side="left")
        ttk.Button(pbuttons, text="Remove point", command=self._remove_point).pack(side="left", padx=(4, 0))

        right = ttk.Frame(body)
        right.pack(side="left", fill="both", expand=True)
        top = ttk.Frame(right)
        top.pack(fill="x")
        ttk.Label(top, text="Backdrop").pack(side="left")
        self._backdrop_var = tk.StringVar()
        self._backdrop_box = ttk.Combobox(top, textvariable=self._backdrop_var, state="readonly", width=28)
        self._backdrop_box.pack(side="left", padx=(6, 0))
        self._backdrop_box.bind("<<ComboboxSelected>>", lambda e: self._draw())
        self._canvas = tk.Canvas(right, width=gc.SCREEN[0], height=gc.SCREEN[1], highlightthickness=0,
                                 background=theme.color("surface_alt"))
        self._canvas.pack(anchor="nw", pady=(6, 0))

    # -- data -----------------------------------------------------------------------------
    def _load(self) -> None:
        self._curves.clear()
        self._lines.clear()
        self._changed.clear()
        self._list.delete(0, "end")
        if not self._folder.is_dir():
            self._status.config(text="gmap/curve not found; extract the project first.")
            return
        errors = []
        for path in sorted(self._folder.glob("*.bin")):
            try:
                if path.stem.startswith("linedefine"):
                    self._lines[int(path.stem[len("linedefine"):])] = gc.read_line_define(path.read_bytes())
                else:
                    self._curves[path.stem] = gc.read_curve(path.read_bytes())
            except (OSError, ValueError) as exc:
                errors.append(f"{path.name}: {exc}")
        for name in self._curves:
            self._list.insert("end", name)
        backdrops = sorted(p.name for p in (self._folder.parent / "tpl").glob("gmap_*.cms"))
        self._backdrop_box.config(values=["(none)"] + backdrops)
        self._backdrop_var.set(next((b for b in backdrops if b.startswith("gmap_zentai")), "(none)"))
        self._set_dirty(False)
        self._status.config(text=f"{len(self._curves)} routes, {len(self._lines)} line styles"
                            + (f"; {len(errors)} unreadable" if errors else ""))
        if self._curves:
            self._list.selection_set(0)
            self._on_curve()

    def _curve(self) -> Optional[gc.Curve]:
        return self._curves.get(self._current) if self._current else None

    def _on_curve(self) -> None:
        selection = self._list.curselection()
        self._current = self._list.get(selection[0]) if selection else None
        curve = self._curve()
        for key in self._vars:
            self._vars[key].set("" if curve is None else getattr(curve, key))
        self._fill_points(0)

    def _fill_points(self, select: Optional[int]) -> None:
        self._points.delete(*self._points.get_children())
        curve = self._curve()
        self._point = None
        if curve is not None:
            for i, p in enumerate(curve.points):
                self._points.insert("", "end", iid=str(i), values=(i, f"{p.x:.1f}", f"{p.y:.1f}", f"{p.tx:.1f}",
                                                                   f"{p.ty:.1f}"))
            if select is not None and curve.points:
                select = min(select, len(curve.points) - 1)
                self._points.selection_set(str(select))
        self._on_point()

    def _on_point(self) -> None:
        selection = self._points.selection()
        self._point = int(selection[0]) if selection else None
        curve = self._curve()
        point = curve.points[self._point] if curve and self._point is not None else None
        for key in self._pvars:
            self._pvars[key].set("" if point is None else f"{getattr(point, key):g}")
        self._draw()

    def _mark(self) -> None:
        if self._current:
            self._changed.add(self._current)
        self._set_dirty(True)

    def _apply_curve(self) -> None:
        curve = self._curve()
        if curve is None:
            return
        try:
            values = {k: int(self._vars[k].get(), 0) for k in self._vars}
        except ValueError:
            messagebox.showerror("Invalid value", "Frames, style and colour are whole numbers.", parent=self)
            return
        if not 0 <= values["style"] < gc.STYLES:
            messagebox.showerror("Invalid value", f"The line style is 0-{gc.STYLES - 1}.", parent=self)
            return
        if any(getattr(curve, k) != v for k, v in values.items()):
            for k, v in values.items():
                setattr(curve, k, v)
            self._mark()
            self._draw()

    def _apply_point(self) -> None:
        curve = self._curve()
        if curve is None or self._point is None:
            return
        try:
            values = {k: float(self._pvars[k].get()) for k in self._pvars}
        except ValueError:
            messagebox.showerror("Invalid value", "Point values are numbers.", parent=self)
            return
        point = curve.points[self._point]
        if any(abs(getattr(point, k) - v) > 1e-6 for k, v in values.items()):
            for k, v in values.items():
                setattr(point, k, v)
            self._mark()
            self._fill_points(self._point)

    def _add_point(self) -> None:
        curve = self._curve()
        if curve is None:
            return
        at = len(curve.points) if self._point is None else self._point + 1
        base = curve.points[at - 1] if at else gc.CurvePoint(gc.SCREEN[0] / 2, gc.SCREEN[1] / 2)
        curve.points.insert(at, gc.CurvePoint(base.x + 20, base.y, base.tx, base.ty))
        self._mark()
        self._fill_points(at)

    def _remove_point(self) -> None:
        curve = self._curve()
        if curve is None or self._point is None or len(curve.points) <= 2:
            return
        del curve.points[self._point]
        self._mark()
        self._fill_points(self._point)

    def _duplicate(self) -> None:
        curve = self._curve()
        if curve is None:
            return
        name = simpledialog.askstring("Duplicate route", "Name of the new route (its file name):",
                                      initialvalue=f"{curve.name}_copy", parent=self)
        if not name:
            return
        if name in self._curves or not name.isascii() or len(name) >= gc.NAME_SIZE or "/" in name:
            messagebox.showerror("Invalid name", f"Use a new ASCII name under {gc.NAME_SIZE} characters.",
                                 parent=self)
            return
        import copy
        clone = copy.deepcopy(curve)
        clone.name = name
        self._curves[name] = clone
        self._list.insert("end", name)
        self._list.selection_clear(0, "end")
        self._list.selection_set("end")
        self._on_curve()
        self._mark()

    def _edit_lines(self) -> None:
        if not self._lines:
            return
        window = tk.Toplevel(self)
        window.title("Line styles")
        ttk.Label(window, text="linedefine<n>.bin: style n-1 of the routes. Half width multiplies the base line "
                               "width; the texture repeats every 'texture length'.", wraplength=420,
                  style="Muted.TLabel", padding=8).grid(row=0, column=0, columnspan=3, sticky="w")
        variables = {}
        for row, number in enumerate(sorted(self._lines), start=1):
            line = self._lines[number]
            ttk.Label(window, text=f"Style {number - 1} (linedefine{number})").grid(row=row, column=0, sticky="w",
                                                                                   padx=8)
            w, t = tk.StringVar(value=f"{line.width:g}"), tk.StringVar(value=f"{line.texture_length:g}")
            ttk.Entry(window, textvariable=w, width=8).grid(row=row, column=1, padx=4, pady=2)
            ttk.Entry(window, textvariable=t, width=8).grid(row=row, column=2, padx=(4, 8), pady=2)
            variables[number] = (w, t)

        def apply() -> None:
            try:
                values = {n: (float(w.get()), float(t.get())) for n, (w, t) in variables.items()}
            except ValueError:
                messagebox.showerror("Invalid value", "Widths and lengths are numbers.", parent=window)
                return
            for n, (w, t) in values.items():
                line = self._lines[n]
                if (line.width, line.texture_length) != (w, t):
                    line.width, line.texture_length = w, t
                    self._changed.add(f"linedefine{n}")
                    self._set_dirty(True)
            window.destroy()
        ttk.Button(window, text="Apply", style="Accent.TButton", command=apply).grid(
            row=len(variables) + 1, column=0, columnspan=3, pady=8)

    # -- preview --------------------------------------------------------------------------
    def _backdrop(self, name: str) -> Optional[Image.Image]:
        if name not in self._backdrops:
            image = None
            try:
                raw = (self._folder.parent / "tpl" / name).read_bytes()
                images = tpl.read_tpl_images(io.BytesIO(lz10.decompress(raw) if raw[:1] == b"\x10" else raw))
                image = images[0].convert("RGBA") if images else None
            except (OSError, ValueError, IndexError):
                image = None
            self._backdrops[name] = image
        return self._backdrops[name]

    def _draw(self) -> None:
        canvas = self._canvas
        canvas.delete("all")
        backdrop = self._backdrop(self._backdrop_var.get()) if self._backdrop_var.get() not in ("", "(none)") else None
        if backdrop is not None:
            fitted = backdrop.resize(gc.SCREEN) if backdrop.size != gc.SCREEN else backdrop
            self._photo = ImageTk.PhotoImage(fitted)
            canvas.create_image(0, 0, image=self._photo, anchor="nw")
        canvas.create_rectangle(0, 0, gc.SCREEN[0] - 1, gc.SCREEN[1] - 1, outline=theme.color("border"))
        curve = self._curve()
        if curve is None:
            return
        line = self._lines.get(curve.style + 1)
        width = max(2, round((line.width if line else 10) / 2))
        coords = [c for xy in gc.sample(curve) for c in xy]
        if len(coords) >= 4:
            canvas.create_line(*coords, fill=COLOURS.get(curve.colour, "#e0e0e0"), width=width, capstyle="round",
                               smooth=False)
        for i, p in enumerate(curve.points):
            r = 5 if i == self._point else 3
            canvas.create_oval(p.x - r, p.y - r, p.x + r, p.y + r, fill="#ffffff", outline="#202020")
            canvas.create_line(p.x, p.y, p.x + p.tx / 3, p.y + p.ty / 3, fill="#ffd040", arrow="last")

    # -- save -----------------------------------------------------------------------------
    def _set_dirty(self, dirty: bool) -> None:
        self._dirty = dirty
        self._save_button.config(state="normal" if dirty else "disabled")
        if dirty:
            self._status.config(text="Unsaved changes")

    def save(self) -> bool:
        written = []
        try:
            for name in sorted(self._changed):
                if name.startswith("linedefine"):
                    data = gc.build_line_define(self._lines[int(name[len("linedefine"):])])
                else:
                    data = gc.build_curve(self._curves[name])
                path = self._folder / f"{name}.bin"
                self._project.write_keeping_original(path, data)
                written.append(path.name)
        except (OSError, ValueError) as exc:
            messagebox.showerror("Could not save the routes", str(exc), parent=self)
            return False
        for name in written:
            self._changelog.append(name, "Saved the world-map route")
        self._changed.clear()
        self._set_dirty(False)
        self._status.config(text=f"Saved {len(written)} files")
        return True

    def _revert(self) -> None:
        if self._dirty and not self._confirm_discard():
            return
        self._load()

    def _confirm_discard(self) -> bool:
        return messagebox.askyesno("Discard changes?", "The routes have unsaved changes. Discard them?", parent=self)
