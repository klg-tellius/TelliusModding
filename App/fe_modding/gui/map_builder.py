"""Build tab: construct a chapter map on one top-down canvas - paint terrain
types, place/move/rotate/delete props, set tile corner heights, and
place/move/delete units - with a render of the map (terrain and props, seen
from straight above) behind the tile grid. Its windows (``map_windows.py``)
list and edit every placed object, the map-wide settings and water, and show
the chapter in 3D.

The tab owns no data. Map edits go through the chapter page's
:class:`~.map_editor.MapEditor` (``edit_map()``, ``edit_pack()``,
``paint_terrain()``) and unit edits through its
:class:`~.deployment_editor.DeploymentEditor` (``apply()`` on the parsed
``dispo.DispoDocument``s); Save Chapter writes both. There is no separate
Deployment tab: this one places and edits the units too.

Tile heights: each tile has four corner elevations on three panel layers
(combined, ground, roof - ``map_heights.LAYERS``). The Tile heights tool
edits them; **Deduce** estimates them from the terrain and the props
(``map_heights.deduce_corners``), and with "Heights follow props" every prop
placed, moved, turned or deleted re-deduces the tiles it covered and covers.

Props, terrain and units share one grid: the full ``mapcapacity`` grid, the
coordinates of ``mapbuildinst`` (x, y), the panel layer and the dispos
``pos_x``/``pos_y`` fields (CHAPTER_DATA_NOTES 5.1/5.2). The backdrop is
``map_scene.render_topdown()`` of ``map_scene.build_map_scene()``, built on
a worker thread and redone (debounced) after prop edits.

Units: the canvas shows one deployment file (the "Deployment file" picker:
``dispos_n/h/m/c.bin`` of the phase's ``dispos.cmp``); the "Section" picker
beside it limits it to one section (the one new units go to), and "Add
section..." / "Remove section" add an empty section or remove the picked one
(``dispo.add_section()`` / ``remove_section()``). "All fields..." edits any raw field of a unit. The
"Disposition..." window (``dispo_window.py``) lists the file's sections, each with its header, the script
functions that deploy it and its units in an editable table. The unit
panel edits the selected unit and its section's header; with "Same edit on every difficulty" the
shared fields (character, class, items, AI, position...) follow in each
variant that has the unit (``dispo.find_counterpart_unit()``), while level
and stat bonuses are set per variant in the difficulty table, whose
checkboxes add the unit to a variant or remove it. Any PID/JID/IID/SID label
can be used: the document model adds new strings to the label pool.

Script zones: the chapter script's functions triggered by a unit entering a
zone (``@on_area``) or acting on a tile (``@on_location``) are drawn on the
map (the "Script zones" layer). The Script zones tool draws new zones - each
a new function, or an untriggered one given the trigger - and moves, edits
and deletes them. They edit the source open in the chapter's
:class:`~.script_editor.ScriptEditor` (``edit_chapter_source()``, through
``formats.cmb.script_zones``), so the Script tab shows the same edits and
Save compiles them once. Deleting a zone deletes its function when the
function is empty; one with code is kept, without its trigger, and marked
UNUSED in its description.

Undo/Redo keep snapshots of the map's files (map.bin, and the models and
texture pack a prop copied from another map adds), every dispos variant and
the chapter script's source, taken before each action.
"""

from __future__ import annotations

import colorsys
import queue
import re
import threading
import tkinter as tk
from tkinter import messagebox, simpledialog, ttk
from typing import Callable, Optional

import numpy as np
from PIL import Image, ImageTk

from .. import map_heights
from ..formats import dispo, dispo_rules, map_file
from ..formats.cmb import script_zones
from ..formats.cmb.catalog import ACTIONS, SIDES
from ..formats.cmb.parser import ParseError
from . import dispo_widgets, gpu_renderer, map_scene
from ..project_index import difficulty_name
from .editor_panel import EditorPanel
from .widgets import ScrollFrame

F = dispo.FIELD
BACKDROP_PX_PER_TILE = 32
MARGIN = 12
RENDER_DELAY_MS = 800
FACTION_COLORS = {0: "#3d7bd9", 1: "#d9473b", 2: "#34a853", 3: "#1e8f7a"}
ANGLES = {"0°": 0, "90°": 192, "180°": 128, "270°": 64}
AI_FIELDS = (("seq_attack", "Attack AI", "SEQ"), ("seq_move", "Move AI", "SEQ"), ("seq_heal", "Heal AI", "SEQ"),
             ("mtype", "Movement AI", "MTYPE"))
PER_VARIANT_FIELDS = {F["level"], *(F[f"bonus_{s}"] for s in dispo.STAT_NAMES)}
TOOL_HELP = {
    "select": "Click a unit or a prop to edit it; drag it to move it. Click any other tile to edit its heights.\n"
              "R turns the selected prop, Delete removes the selection.",
    "terrain": "Click or drag over tiles to paint the chosen type.\nRight-click a tile to pick its type.",
    "prop": "Click a tile to place the chosen prop there.\nAdd from another map... copies any chapter's prop here.",
    "heights": "Click a tile to edit its corner heights, or drag to select a rectangle of tiles.",
    "unit": "Click a tile to add a unit there, in the chosen section (or use Add unit... above, "
            "then drag the unit).",
    "zone": "Drag a rectangle (or click a tile) to add a zone that runs a script function.\n"
            "Click a zone to edit it, drag it to move it; Shift+drag draws over an existing zone. "
            "Delete removes the selected zone.",
}
HIGHLIGHT_COLOR = "#4dd0ff"  # the units of the section highlighted from the Disposition window
ZONE_COLORS = {"player": "#4fc3f7", "enemy": "#ff8a65"}
LOCATION_COLOR = "#ce93d8"
ZONE_KINDS = {"Area - a unit enters": script_zones.AREA, "Location - a unit acts on a tile": script_zones.LOCATION}
NEW_FUNCTION = "New function"


def _terrain_color(name: str) -> tuple[int, int, int]:
    if not name:
        return (37, 37, 37)
    hue = (sum(name.encode("utf-8")) * 0.61803398875) % 1.0
    r, g, b = colorsys.hls_to_rgb(hue, 0.45, 0.55)
    return int(r * 255), int(g * 255), int(b * 255)


def _ordered(a, b) -> tuple[int, int, int, int]:
    """The (x1, y1, x2, y2) rectangle with corners ``a`` and ``b``."""
    return min(a[0], b[0]), min(a[1], b[1]), max(a[0], b[0]), max(a[1], b[1])


def _dim(color: str) -> str:
    """``color`` (#rrggbb) faded towards the canvas background."""
    r, g, b = (int(color[i:i + 2], 16) for i in (1, 3, 5))
    return "#%02x%02x%02x" % tuple(int(c * 0.35 + 0x1e * 0.65) for c in (r, g, b))


def _prop_color(desc_index: int) -> str:
    r, g, b = colorsys.hsv_to_rgb((desc_index * 0.61803398875) % 1.0, 0.55, 1.0)
    return f"#{int(r * 255):02x}{int(g * 255):02x}{int(b * 255):02x}"


class _LabelPicker(ttk.Combobox):
    """A combobox of labels shown as "Name (LABEL)", filtered as you type;
    any label can also be typed as is. ``label()`` is the chosen label, or 0
    for none."""

    def __init__(self, parent: tk.Misc, width: int = 30) -> None:
        super().__init__(parent, width=width)
        self._pairs: list[tuple[str, str]] = []
        self.bind("<KeyRelease>", self._filter)

    def set_choices(self, pairs: list[tuple[str, str]]) -> None:
        self._pairs = pairs
        self["values"] = [display for display, _ in pairs]

    def _filter(self, event) -> None:
        if event.keysym in ("Up", "Down", "Return", "Escape", "Tab"):
            return
        text = self.get().lower()
        self["values"] = [d for d, _ in self._pairs if text in d.lower()] if text else [d for d, _ in self._pairs]

    def set_label(self, value) -> None:
        if not isinstance(value, str):
            self.set("" if not value else str(value))
            return
        self.set(next((d for d, label in self._pairs if label == value), value))

    def label(self):
        text = self.get().strip()
        if not text or text == "0":
            return 0
        for display, label in self._pairs:
            if display == text:
                return label
        match = re.search(r"\(([A-Za-z0-9_]+)\)\s*$", text)
        if match:
            return match.group(1)
        if re.fullmatch(r"[A-Za-z0-9_]+", text):
            return int(text) if text.isdigit() else text
        raise ValueError(f"{text!r} is not a label (letters, digits and _ only).")


class _BuildCanvas(tk.Canvas):
    """The tile canvas: backdrop, terrain colours, grid, props and units.
    Pointer events come back to the builder as tile coordinates."""

    def __init__(self, parent: tk.Misc, builder: "MapBuilder") -> None:
        super().__init__(parent, background="#1e1e1e", highlightthickness=0, takefocus=1)
        self._builder = builder
        self.cell = 28
        self.size: tuple[int, int] | None = None
        self.backdrop: Image.Image | None = None
        self.terrain: list | None = None
        self.playable = None
        self.props: list[dict] = []
        self.units: list[dict] = []
        self.highlighting = False  # a section's units are highlighted (the others are drawn dimmed)
        self.zones: list[dict] = []
        self.heights = None  # [x][y] mean combined elevation, for the heights layer
        self.selected_tiles: set = set()
        self.show = {"image": True, "terrain": False, "heights": False, "grid": True, "props": True, "zones": True,
                     "units": True}
        self._photo = None
        self._composite_key = None
        for sequence, handler in (
            ("<ButtonPress-1>", self._press), ("<B1-Motion>", self._drag), ("<ButtonRelease-1>", self._release),
            ("<ButtonPress-3>", self._right), ("<Motion>", self._motion),
            ("<ButtonPress-2>", lambda e: self.scan_mark(e.x, e.y)),
            ("<B2-Motion>", lambda e: self.scan_dragto(e.x, e.y, gain=1)),
            ("<MouseWheel>", self._wheel), ("<Control-MouseWheel>", self._zoom_wheel),
            ("<Shift-MouseWheel>", lambda e: self.xview_scroll(-1 if e.delta > 0 else 1, "units")),
        ):
            self.bind(sequence, handler)

    # -- coordinates -------------------------------------------------------------------
    def tile_at(self, event) -> tuple[int, int] | None:
        if self.size is None:
            return None
        x = int((self.canvasx(event.x) - MARGIN) // self.cell)
        y = int((self.canvasy(event.y) - MARGIN) // self.cell)
        return (x, y) if 0 <= x < self.size[0] and 0 <= y < self.size[1] else None

    def box(self, x0, y0, x1=None, y1=None):
        """Canvas rectangle covering tiles x0..x1, y0..y1 (inclusive)."""
        x1 = x0 if x1 is None else x1
        y1 = y0 if y1 is None else y1
        c = self.cell
        return MARGIN + x0 * c, MARGIN + y0 * c, MARGIN + (x1 + 1) * c, MARGIN + (y1 + 1) * c

    def see_tile(self, x: int, y: int) -> None:
        """Scroll so tile (x, y) is in the middle of the view."""
        if self.size is None:
            return
        x = min(max(x, 0), self.size[0] - 1)
        y = min(max(y, 0), self.size[1] - 1)
        x0, y0, x1, y1 = self.box(x, y)
        width, height = self.size[0] * self.cell + 2 * MARGIN, self.size[1] * self.cell + 2 * MARGIN
        self.xview_moveto(max(0.0, ((x0 + x1) / 2 - self.winfo_width() / 2) / width))
        self.yview_moveto(max(0.0, ((y0 + y1) / 2 - self.winfo_height() / 2) / height))

    def zoom(self, factor: float) -> None:
        self.cell = int(max(8, min(96, round(self.cell * factor))))
        self.redraw()

    # -- drawing -----------------------------------------------------------------------
    def _composite(self) -> Image.Image | None:
        w, h = self.size
        key = (id(self.backdrop), id(self.terrain), id(self.heights), self.cell, self.show["image"], self.show["terrain"],
               self.show["heights"])
        if key == self._composite_key and self._photo is not None:
            return None
        self._composite_key = key
        size = (w * self.cell, h * self.cell)
        base = None
        if self.show["image"] and self.backdrop is not None:
            base = self.backdrop.convert("RGB").resize(size, Image.BILINEAR)
        if self.show["terrain"] and self.terrain is not None:
            colors = np.array([[_terrain_color(self.terrain[x][y]) for x in range(w)] for y in range(h)], dtype=np.uint8)
            overlay = Image.fromarray(colors, "RGB").resize(size, Image.NEAREST)
            base = overlay if base is None else Image.blend(base, overlay, 0.45)
        if self.show["heights"] and self.heights is not None:
            values = np.array(self.heights, dtype=float).T  # rows are y
            low, high = float(values.min()), float(values.max())
            t = (values - low) / (high - low) if high > low else np.zeros_like(values)
            t = 1.0 - t  # elevations grow downwards: the smallest is the highest ground
            colors = np.stack([60 + 195 * t, 90 + 60 * (1 - abs(t - 0.5) * 2), 220 - 180 * t], axis=-1).astype(np.uint8)
            overlay = Image.fromarray(colors, "RGB").resize(size, Image.NEAREST)
            base = overlay if base is None else Image.blend(base, overlay, 0.55)
        return base if base is not None else Image.new("RGB", size, (42, 42, 42))

    def redraw(self) -> None:
        self.delete("all")
        if self.size is None:
            self.create_text(16, 16, anchor="nw", text=self._builder.empty_text, fill="#999999")
            return
        w, h = self.size
        image = self._composite()
        if image is not None:
            self._photo = ImageTk.PhotoImage(image)
        self.create_image(MARGIN, MARGIN, anchor="nw", image=self._photo)
        x1, y1 = MARGIN + w * self.cell, MARGIN + h * self.cell
        if self.show["grid"]:
            for x in range(w + 1):
                self.create_line(MARGIN + x * self.cell, MARGIN, MARGIN + x * self.cell, y1, fill="#000000", stipple="gray50")
            for y in range(h + 1):
                self.create_line(MARGIN, MARGIN + y * self.cell, x1, MARGIN + y * self.cell, fill="#000000", stipple="gray50")
            if self.cell >= 20:
                for x in range(0, w, 5):
                    self.create_text(MARGIN + x * self.cell + 2, MARGIN + 1, anchor="nw", text=str(x), fill="#f0f0f0",
                                     font=("Segoe UI", 7))
                for y in range(5, h, 5):
                    self.create_text(MARGIN + 2, MARGIN + y * self.cell + 1, anchor="nw", text=str(y), fill="#f0f0f0",
                                     font=("Segoe UI", 7))
        if self.playable:
            px0, px1, py0, py1 = self.playable
            self.create_rectangle(MARGIN + px0 * self.cell, MARGIN + py0 * self.cell, MARGIN + px1 * self.cell,
                                  MARGIN + py1 * self.cell, outline="#f0d37a", width=2)
        if self.show["props"]:
            for prop in self.props:
                width = 3 if prop["selected"] else 1
                color = "#ffe14d" if prop["selected"] else prop["color"]
                self.create_rectangle(*self.box(*prop["rect"]), outline=color, width=width,
                                      dash=() if prop["model"] else (3, 3))
        if self.show["zones"]:
            for zone in self.zones:
                self._draw_zone(zone)
        if self.show["units"]:
            self.highlighting = any(unit["highlight"] for unit in self.units)
            # the highlighted section's units on top, the selected unit above them
            for unit in sorted(self.units, key=lambda u: (u["selected"], u["highlight"])):
                self._draw_unit(unit)
        for x, y in self.selected_tiles:
            self.create_rectangle(*self.box(x, y), outline="#ffe14d", width=2)
        self.configure(scrollregion=(0, 0, x1 + MARGIN, y1 + MARGIN))

    def _draw_unit(self, unit: dict) -> None:
        x0, y0, x1, y1 = self.box(unit["x"], unit["y"])
        pad = max(2, self.cell * 0.12)
        if unit["pos2"] != (unit["x"], unit["y"]):
            bx0, by0, bx1, by1 = self.box(*unit["pos2"])
            self.create_line((x0 + x1) / 2, (y0 + y1) / 2, (bx0 + bx1) / 2, (by0 + by1) / 2, fill=unit["color"],
                             width=2, arrow="last", dash=(4, 2))
        dimmed = self.highlighting and not unit["highlight"] and not unit["selected"]
        if unit["highlight"]:
            self.create_rectangle(x0 + 1, y0 + 1, x1 - 1, y1 - 1, outline=HIGHLIGHT_COLOR, width=2)
        if unit["selected"]:
            self.create_rectangle(x0, y0, x1, y1, outline="#ffe14d", width=3)
        self.create_oval(x0 + pad, y0 + pad, x1 - pad, y1 - pad, fill=_dim(unit["color"]) if dimmed else unit["color"],
                         outline="#ffffff" if unit["selected"] else "#101010", width=3 if unit["selected"] else 1)
        if self.cell >= 18:
            self.create_text((x0 + x1) / 2, (y0 + y1) / 2, text=unit["text"], fill="#8a8a8a" if dimmed else "#ffffff",
                             font=("Segoe UI", max(6, int(self.cell / 4)), "bold"))

    def _draw_zone(self, zone: dict) -> None:
        x0, y0, x1, y1 = self.box(*zone["rect"])
        color = "#ffe14d" if zone["selected"] else zone["color"]
        pad = 2 if zone["area"] else max(3, self.cell * 0.18)
        self.create_rectangle(x0 + pad, y0 + pad, x1 - pad, y1 - pad, outline=color, fill=zone["color"], stipple="gray25",
                              width=3 if zone["selected"] else 2, dash=() if zone["area"] else (4, 2))
        if self.cell >= 16:
            self.create_text(x0 + pad + 2, y0 + pad + 1, anchor="nw", text=zone["text"], fill=color,
                             font=("Segoe UI", max(7, min(10, int(self.cell / 3))), "bold"))

    def preview_tiles(self, tiles, color: str) -> None:
        self.delete("preview")
        for x, y in tiles:
            self.create_rectangle(*self.box(x, y), fill=color, outline="#ffffff", tags="preview")

    def preview_rect(self, rect, color: str) -> None:
        self.delete("preview")
        self.create_rectangle(*self.box(*rect), outline=color, width=3, dash=(6, 3), tags="preview")

    def preview_marker(self, tile, color: str) -> None:
        self.delete("preview")
        if tile is not None:
            self.create_rectangle(*self.box(*tile), outline=color, width=3, tags="preview")

    # -- events --------------------------------------------------------------------------
    def _press(self, event) -> None:
        self.focus_set()
        self._builder.on_press(self.tile_at(event), event)

    def _drag(self, event) -> None:
        self._builder.on_drag(self.tile_at(event), event)

    def _release(self, event) -> None:
        self._builder.on_release(self.tile_at(event), event)

    def _right(self, event) -> None:
        self._builder.on_right(self.tile_at(event), event)

    def _motion(self, event) -> None:
        self._builder.on_hover(self.tile_at(event))

    def _wheel(self, event) -> None:
        self.yview_scroll(-1 if event.delta > 0 else 1, "units")

    def _zoom_wheel(self, event) -> None:
        self.zoom(1.15 if event.delta > 0 else 1 / 1.15)


class _NewUnitDialog(tk.Toplevel):
    def __init__(self, parent, characters, classes, tile, section: str, sections: Optional[list] = None) -> None:
        """``sections`` (the Build tab's section choices): show a section picker, starting on ``section``;
        ``result`` then ends with the chosen one."""
        super().__init__(parent)
        self.title("New unit")
        self.transient(parent)
        self.result = None
        self._sections = sections
        body = ttk.Frame(self, padding=12)
        body.pack(fill="both", expand=True)
        if sections:
            ttk.Label(body, text=f"On tile {tile} (drag it afterwards)", style="Muted.TLabel").grid(
                row=0, column=0, columnspan=2, sticky="w")
            self._section = tk.StringVar(value=next((c for c in sections if c.split("  (", 1)[0] == section),
                                                    sections[0]))
            ttk.Label(body, text="Section").grid(row=5, column=0, sticky="w", pady=3)
            ttk.Combobox(body, textvariable=self._section, values=sections, state="readonly", width=60).grid(
                row=5, column=1, sticky="w", pady=3, padx=(8, 0))
            if not any(c.endswith(", battle start)") for c in sections):
                ttk.Label(body, style="Muted.TLabel", wraplength=460, justify="left", text=(
                    "This deployment file has no battle-start section. The enemies of the battle are usually "
                    "in the Normal, Hard and Maniac files: choose one in Deployment file at the top first. "
                    "Units of an 'event scene only' section appear only during that scene.")).grid(
                    row=7, column=0, columnspan=2, sticky="w", pady=(6, 0))
        else:
            ttk.Label(body, text=f"On tile {tile}, section {section}", style="Muted.TLabel").grid(
                row=0, column=0, columnspan=2, sticky="w")
        self._character = _LabelPicker(body, width=34)
        self._character.set_choices(characters)
        self._class = _LabelPicker(body, width=34)
        self._class.set_choices(classes)
        self._level = tk.StringVar(value="1")
        for row, (label, widget) in enumerate((("Character", self._character), ("Class (empty: the character's)", self._class),
                                               ("Level", ttk.Spinbox(body, from_=1, to=40, textvariable=self._level, width=6))), 1):
            ttk.Label(body, text=label).grid(row=row, column=0, sticky="w", pady=3)
            widget.grid(row=row, column=1, sticky="w", pady=3, padx=(8, 0))
        buttons = ttk.Frame(body)
        buttons.grid(row=8, column=0, columnspan=2, sticky="e", pady=(10, 0))
        ttk.Button(buttons, text="Add", command=self._ok).pack(side="left")
        ttk.Button(buttons, text="Cancel", command=self.destroy).pack(side="left", padx=(6, 0))
        self._character.focus_set()
        self.bind("<Return>", lambda e: self._ok())
        self.grab_set()

    def _ok(self) -> None:
        try:
            pid, jid, level = self._character.label(), self._class.label(), int(self._level.get())
        except ValueError as exc:
            messagebox.showerror("New unit", str(exc), parent=self)
            return
        if not isinstance(pid, str):
            messagebox.showerror("New unit", "Choose a character.", parent=self)
            return
        self.result = (pid, jid, level) + ((self._section.get(),) if self._sections else ())
        self.destroy()


class MapBuilder(EditorPanel):
    display_name = "Build"

    def __init__(self, parent, project, changelog, map_editor, deployment,
                 index_provider: Callable[[], object] = lambda: None,
                 session_provider: Callable[[], object] = lambda: None,
                 on_navigate_to_character: Optional[Callable[[str], None]] = None,
                 navigate: Optional[Callable[[tuple], None]] = None,
                 script_editor=None, on_open_function: Optional[Callable[[str], None]] = None) -> None:
        super().__init__(parent)
        self._project = project
        self._changelog = changelog
        self._map = map_editor
        self._deploy = deployment
        self._index_provider = index_provider
        self._session_provider = session_provider
        self._on_navigate_to_character = on_navigate_to_character
        self.navigate = navigate  # workspace routes, e.g. ("data", "chapters", "3")
        self._script = script_editor
        self._on_open_function = on_open_function
        self._zones_key = None  # (source, zones, parse problem or None), cached per source text
        self._zones_stale = False
        self._zone_function_choices = {NEW_FUNCTION: None}
        self.empty_text = "Open a chapter with a map."
        # ("unit", section, index) | ("prop", index) | ("zone", function) | ("tile", x, y) | ("tiles", tiles)
        self._selection: tuple | None = None
        self._press_state: dict | None = None
        self._undo: list = []
        self._redo: list = []
        self._backdrop: Image.Image | None = None
        self._script_strings_key = None  # (script path, mtime) the cache below was read from
        self._script_strings_cache: Optional[set] = None
        self._render_generation = 0
        self._render_after = None
        self._render_wanted = False
        self._rendered_props = None
        self._map_path = None
        self._gpu = None
        self._gpu_checked = False
        self._choices_cache = None
        self._ai_labels: dict[str, list[str]] | None = None
        self._form_vars: dict = {}
        self._windows: dict[str, tk.Toplevel] = {}
        self._highlight: tuple[str, str] | None = None  # (variant, section) highlighted on the canvas

        self._build_widgets()
        map_editor.add_listener(self._on_map_changed)
        deployment.add_listener(self._on_units_changed)
        if script_editor is not None:
            script_editor.add_listener(self._on_script_changed)
        self.bind("<Map>", lambda e: self._on_shown())

    # -- layout ------------------------------------------------------------------------
    def _build_widgets(self) -> None:
        top = ttk.Frame(self, padding=(8, 6))
        top.pack(fill="x")
        ttk.Button(top, text="Save Chapter", command=self._save).pack(side="left")
        ttk.Button(top, text="Play...", style="Accent.TButton", command=self.open_play).pack(side="left", padx=(6, 0))
        self._undo_button = ttk.Button(top, text="Undo", command=self._do_undo, state="disabled")
        self._undo_button.pack(side="left", padx=(6, 0))
        self._redo_button = ttk.Button(top, text="Redo", command=self._do_redo, state="disabled")
        self._redo_button.pack(side="left", padx=(4, 0))
        ttk.Label(top, text="Deployment file").pack(side="left", padx=(14, 4))
        self._variant_var = tk.StringVar()
        self._variant_combo = ttk.Combobox(top, textvariable=self._variant_var, state="readonly", width=26)
        self._variant_combo.pack(side="left")
        self._variant_combo.bind("<<ComboboxSelected>>", lambda e: self._variant_changed())
        ttk.Label(top, text="Section").pack(side="left", padx=(10, 4))
        self._filter_var = tk.StringVar(value="All sections")
        self._filter_combo = ttk.Combobox(top, textvariable=self._filter_var, state="readonly", width=24)
        self._filter_combo.pack(side="left")
        self._filter_combo.bind("<<ComboboxSelected>>", lambda e: self._filter_changed())
        ttk.Button(top, text="Add section...", command=self._add_section).pack(side="left", padx=(6, 0))
        self._remove_section_button = ttk.Button(top, text="Remove section", command=self._remove_section,
                                                 state="disabled")
        self._remove_section_button.pack(side="left", padx=(4, 0))
        self._filter_var.trace_add("write", lambda *_: self._remove_section_button.configure(
            state="disabled" if self._filter_var.get() == "All sections" else "normal"))

        paned = ttk.PanedWindow(self, orient="horizontal")
        paned.pack(fill="both", expand=True)

        tools = ttk.Frame(paned, padding=8, width=230)
        paned.add(tools, weight=0)
        self._build_tools(tools)

        middle = ttk.Frame(paned)
        paned.add(middle, weight=4)
        self._canvas = _BuildCanvas(middle, self)
        ybar = ttk.Scrollbar(middle, orient="vertical", command=self._canvas.yview)
        xbar = ttk.Scrollbar(middle, orient="horizontal", command=self._canvas.xview)
        self._canvas.configure(yscrollcommand=ybar.set, xscrollcommand=xbar.set)
        bottom = ttk.Frame(middle)
        bottom.pack(side="bottom", fill="x", padx=6, pady=(2, 4))
        self._status = ttk.Label(bottom, text="", style="Muted.TLabel")
        self._status.pack(side="right")
        self._hover = ttk.Label(bottom, text="", style="Muted.TLabel", anchor="w")
        self._hover.pack(side="left", fill="x", expand=True)
        view = ttk.Frame(middle)
        view.pack(side="bottom", fill="x", padx=6, pady=(4, 0))
        self._layer_vars = {}
        for key, text in (("image", "Map image"), ("terrain", "Terrain"), ("heights", "Heights"), ("grid", "Grid"),
                          ("props", "Props"), ("zones", "Script zones"), ("units", "Units")):
            var = tk.BooleanVar(value=key not in ("terrain", "heights"))
            self._layer_vars[key] = var
            ttk.Checkbutton(view, text=text, variable=var, command=self._layers_changed).pack(side="left", padx=(0, 6))
        ttk.Button(view, text="−", width=3, command=lambda: self._canvas.zoom(1 / 1.25)).pack(side="left", padx=(8, 0))
        ttk.Button(view, text="+", width=3, command=lambda: self._canvas.zoom(1.25)).pack(side="left", padx=(2, 0))
        ttk.Button(view, text="Re-render", command=lambda: self._request_render(0)).pack(side="left", padx=(8, 0))
        ttk.Button(view, text="3D view...", command=self.open_3d).pack(side="left", padx=(4, 0))
        xbar.pack(side="bottom", fill="x")
        ybar.pack(side="right", fill="y")
        self._canvas.pack(side="left", fill="both", expand=True)
        for sequence, handler in (("<Delete>", lambda e: self._delete_selection()), ("<r>", lambda e: self._rotate_selected()),
                                  ("<Control-z>", lambda e: self._do_undo()), ("<Control-y>", lambda e: self._do_redo()),
                                  ("<Escape>", lambda e: self._select(None))):
            self._canvas.bind(sequence, handler)

        inspector = ScrollFrame(paned, padding=(10, 8))
        paned.add(inspector, weight=0)
        self._inspector = inspector.body
        self._canvas.redraw()

    def _build_tools(self, parent: ttk.Frame) -> None:
        ttk.Button(parent, text="Add unit...", style="Accent.TButton", command=self.add_unit).pack(
            anchor="w", fill="x", pady=(0, 10))
        ttk.Label(parent, text="Tool", font=("Segoe UI", 10, "bold")).pack(anchor="w")
        self._tool = tk.StringVar(value="select")
        for key, text in (("select", "Select / move"), ("terrain", "Paint terrain"), ("prop", "Place prop"),
                          ("heights", "Tile heights"), ("unit", "Place unit"), ("zone", "Script zones")):
            ttk.Radiobutton(parent, text=text, value=key, variable=self._tool, command=self._tool_changed).pack(anchor="w", pady=1)
        self._tool_help = ttk.Label(parent, text=TOOL_HELP["select"], style="Muted.TLabel", wraplength=210, justify="left")
        self._tool_help.pack(anchor="w", pady=(6, 8))
        self._tool_frames = {}

        frame = ttk.Frame(parent)
        ttk.Label(frame, text="Terrain type").pack(anchor="w")
        self._terrain_var = tk.StringVar()
        self._terrain_combo = ttk.Combobox(frame, textvariable=self._terrain_var, state="readonly", width=30)
        self._terrain_combo.pack(anchor="w", fill="x")
        self._rect_fill = tk.BooleanVar(value=False)
        ttk.Checkbutton(frame, text="Fill a rectangle", variable=self._rect_fill).pack(anchor="w", pady=(4, 0))
        self._tool_frames["terrain"] = frame

        frame = ttk.Frame(parent)
        ttk.Label(frame, text="Prop").pack(anchor="w")
        self._prop_list = tk.Listbox(frame, exportselection=False, height=14)
        self._prop_list.pack(fill="both", expand=True)
        row = ttk.Frame(frame)
        row.pack(fill="x", pady=(4, 0))
        ttk.Label(row, text="Angle").pack(side="left")
        self._prop_angle = tk.StringVar(value="0°")
        ttk.Combobox(row, textvariable=self._prop_angle, values=list(ANGLES), state="readonly", width=6).pack(side="left", padx=(6, 0))
        ttk.Button(frame, text="Add from another map...", command=self._add_prop_from_map).pack(anchor="w", pady=(6, 0))
        ttk.Button(frame, text="Import prop .glb...", command=self._import_prop).pack(anchor="w", pady=(4, 0))
        self._tool_frames["prop"] = frame

        frame = ttk.Frame(parent)
        ttk.Label(frame, text="Units stand on the combined layer. Show the Heights layer to see it shaded (red is high).",
                  style="Muted.TLabel", wraplength=210, justify="left").pack(anchor="w")
        self._tool_frames["heights"] = frame

        frame = ttk.Frame(parent)
        ttk.Label(frame, text="Section").pack(anchor="w")
        self._section_var = tk.StringVar()
        self._section_combo = ttk.Combobox(frame, textvariable=self._section_var, state="readonly", width=30)
        self._section_combo.pack(anchor="w", fill="x")
        ttk.Label(frame, text="New units copy the AI, faction and flags of the section's first unit.",
                  style="Muted.TLabel", wraplength=210, justify="left").pack(anchor="w", pady=(4, 0))
        ttk.Label(frame, text="Add to").pack(anchor="w", pady=(8, 0))
        self._add_to_frame = ttk.Frame(frame)
        self._add_to_frame.pack(anchor="w")
        self._add_to_vars: dict[str, tk.BooleanVar] = {}
        self._tool_frames["unit"] = frame

        frame = ttk.Frame(parent)
        ttk.Label(frame, text="New zone").pack(anchor="w")
        self._zone_kind = tk.StringVar(value=next(iter(ZONE_KINDS)))
        kind_box = ttk.Combobox(frame, textvariable=self._zone_kind, values=list(ZONE_KINDS), state="readonly", width=30)
        kind_box.pack(anchor="w", fill="x")
        kind_box.bind("<<ComboboxSelected>>", lambda e: self._zone_kind_changed())
        self._zone_mode_label = ttk.Label(frame, text="Triggered by")
        self._zone_mode_label.pack(anchor="w", pady=(6, 0))
        self._zone_mode = tk.StringVar(value="player")
        self._zone_mode_box = ttk.Combobox(frame, textvariable=self._zone_mode, state="readonly", width=30)
        self._zone_mode_box.pack(anchor="w", fill="x")
        ttk.Label(frame, text="Runs").pack(anchor="w", pady=(6, 0))
        self._zone_function = tk.StringVar(value=NEW_FUNCTION)
        self._zone_function_box = ttk.Combobox(frame, textvariable=self._zone_function, state="readonly", width=30)
        self._zone_function_box.pack(anchor="w", fill="x")
        ttk.Label(frame, text="A new zone runs a new, empty function, or an existing function without a trigger "
                              "(the ones marked UNUSED come first): it gets the zone's trigger.",
                  style="Muted.TLabel", wraplength=210, justify="left").pack(anchor="w", pady=(4, 0))
        self._zone_note = ttk.Label(frame, text="", style="Muted.TLabel", wraplength=210, justify="left")
        self._zone_note.pack(anchor="w", pady=(8, 0))
        self._zone_open_script = ttk.Button(frame, text="Open this chapter's script", command=self._open_chapter_script)
        self._tool_frames["zone"] = frame
        self._zone_kind_changed()

        windows = ttk.Frame(parent)
        windows.pack(side="bottom", fill="x", pady=(8, 0))
        ttk.Separator(windows).pack(fill="x", pady=(0, 6))
        ttk.Label(windows, text="Map", font=("Segoe UI", 10, "bold")).pack(anchor="w")
        row = ttk.Frame(windows)
        row.pack(fill="x", pady=(2, 0))
        ttk.Button(row, text="Objects...", command=self.open_objects).pack(side="left")
        ttk.Button(row, text="Disposition...", command=self.open_disposition).pack(side="left", padx=(4, 0))
        ttk.Button(windows, text="Map settings & chapter...", command=self.open_settings).pack(anchor="w", pady=(4, 0))
        self._all_variants = tk.BooleanVar(value=True)
        ttk.Checkbutton(parent, text="Same edit on every difficulty", variable=self._all_variants).pack(side="bottom", anchor="w")
        self._auto_heights = tk.BooleanVar(value=True)
        ttk.Checkbutton(parent, text="Heights follow props", variable=self._auto_heights).pack(side="bottom", anchor="w")
        self._tool_changed()

    # -- data refresh ------------------------------------------------------------------
    def _on_map_changed(self) -> None:
        path = self._map.current_path
        if path != self._map_path:
            self._map_path = path
            self._undo.clear()
            self._redo.clear()
            self._backdrop = None
            self._rendered_props = None
            self._selection = None
            self._canvas.cell = 28
            self._refresh_catalogs()
        else:
            self._refresh_prop_list()
        props = self._prop_signature()
        if props != self._rendered_props:
            self._request_render(0 if self._backdrop is None else RENDER_DELAY_MS)
        self._refresh_canvas()
        self._update_buttons()

    def _on_units_changed(self) -> None:
        order = "cnhm"
        variants = sorted(self._deploy.variants(), key=lambda v: order.find(v.removeprefix("dispos_")[:1]))
        names = [self._variant_name(v) for v in variants]
        self._variant_combo.configure(values=names)
        if self._variant_var.get() not in names:
            self._variant_var.set(names[0] if names else "")
            self._selection = None if self._selection and self._selection[0] == "unit" else self._selection
        for child in self._add_to_frame.winfo_children():
            child.destroy()
        old = {v: var.get() for v, var in self._add_to_vars.items()}
        self._add_to_vars = {}
        for v in variants:
            var = tk.BooleanVar(value=old.get(v, True))
            self._add_to_vars[v] = var
            ttk.Checkbutton(self._add_to_frame, text=self._variant_name(v), variable=var).pack(anchor="w")
        self._refresh_sections()
        self._refresh_canvas()
        self._update_buttons()
        self._notify_disposition()

    @staticmethod
    def _variant_name(variant: str) -> str:
        letter = variant.removeprefix("dispos_").removesuffix(".bin")
        # _c sections are deployed by name on every difficulty; the n/h/m trio goes to the
        # scripts' DisposSetMode-style helpers, which pick one by difficulty (script tutorial, lesson 15).
        return f"{variant} ({'every difficulty' if letter == 'c' else difficulty_name(letter)})"

    def _variant(self) -> str | None:
        name = self._variant_var.get()
        return next((v for v in self._deploy.variants() if self._variant_name(v) == name), None)

    def _doc(self) -> dispo.DispoDocument | None:
        variant = self._variant()
        return self._deploy.document(variant) if variant else None

    def _variant_changed(self) -> None:
        if self._selection and self._selection[0] == "unit":
            self._selection = None
        self._refresh_sections()
        self._refresh_canvas()
        self._notify_disposition()

    def _see_unit(self, section_name: str, index: int) -> None:
        unit = self.raw_unit(self._variant(), section_name, index)
        if unit is not None:
            self.after_idle(lambda: self._canvas.see_tile(unit[F["pos_x"]], unit[F["pos_y"]]))

    def _refresh_sections(self) -> None:
        doc = self._doc()
        names = [s.name for s in doc.sections if not s.is_link] if doc else []
        self._filter_combo.configure(values=["All sections"] + names)
        if self._filter_var.get() not in names:
            self._filter_var.set("All sections")
        deployed = self._script_strings()
        labelled = [f"{name}  ({self._section_army(doc.section(name))}{self._section_role(name, deployed)})"
                    for name in names]
        self._section_combo.configure(values=labelled)
        if self._section_var.get() not in labelled:
            self._section_var.set(labelled[0] if labelled else "")

    def _script_strings(self) -> Optional[set]:
        """The strings of the chapter's saved script (the section names it deploys), or None."""
        path = self._script.chapter_path if self._script is not None else None
        if path is None or not path.is_file():
            return None
        if self._script_strings_key != (path, path.stat().st_mtime_ns):
            self._script_strings_key = (path, path.stat().st_mtime_ns)
            self._script_strings_cache = {m.decode("latin-1") for m in re.findall(rb"[\w.]{3,}", path.read_bytes())}
        return self._script_strings_cache

    @staticmethod
    def _section_role(name: str, deployed: Optional[set]) -> str:
        """What a section is for, from its name (the retail naming) and whether the script names it."""
        base = re.sub(r"_[cnhm]$", "", name)
        if deployed is not None and name not in deployed and base not in deployed:
            return ", not deployed by the script"
        lowered = base.lower()
        if "mikata" in lowered:
            return ", player army"
        if "boss" in lowered:
            return ", boss"
        if "event" in lowered or re.search(r"_ev\d", lowered):
            return ", event scene only, not in the battle"
        if "zoen" in lowered or re.search(r"_z\d", lowered):
            return ", reinforcements"
        if "first" in lowered:
            return ", battle start"
        return ""

    def _battle_section(self) -> Optional[str]:
        """The section new enemies of the battle usually go to: the first 'battle start' one."""
        for label in self._section_combo.cget("values"):
            if label.endswith(", battle start)"):
                return label
        return None

    def _filter_changed(self) -> None:
        """Show the picked section's units (or every section's); placed units go to it."""
        name = self._filter_var.get()
        match = next((v for v in self._section_combo.cget("values") if v.split("  (", 1)[0] == name), None)
        if match is not None:
            self._section_var.set(match)
        self._refresh_canvas()

    def _section_variants(self, docs, name: str) -> list[tuple[str, str]]:
        """(variant, section name) pairs a section edit on ``name`` in the
        current file reaches: that file, plus with "Same edit on every
        difficulty" the other Normal/Hard/Maniac files, whose sections carry
        their own difficulty letter (``bmap02_first_n`` -> ``bmap02_first_h``)."""
        current = self._variant()
        targets = [(current, name)]
        base = dispo.section_base(name)
        letter = current.removeprefix("dispos_")[:1]
        if not self._all_variants.get() or base == name or letter not in "nhm":
            return targets
        for variant in docs:
            other = variant.removeprefix("dispos_")[:1]
            if variant != current and other in "nhm":
                targets.append((variant, f"{base}_{other}"))
        return targets

    def _add_section(self) -> None:
        doc = self._doc()
        if doc is None:
            return
        dialog = _AddSectionDialog(self, self._deploy.group_keys())
        self.wait_window(dialog)
        if dialog.result is None:
            return
        name, header = dialog.result

        def edit(docs):
            for variant, section_name in self._section_variants(docs, name):
                if docs[variant].section(section_name) is None or variant == self._variant():
                    dispo.add_section(docs[variant], section_name, header)

        if self._edit_units(edit, f"Added section {name}"):
            self._refresh_sections()
            self._filter_var.set(name)
            self._filter_changed()

    def _remove_section(self) -> None:
        name = self._filter_var.get()
        doc = self._doc()
        section = doc.section(name) if doc and name != "All sections" else None
        if section is None:
            return
        targets = self._section_variants({v: None for v in self._deploy.variants()}, name)
        targets = [(v, n) for v, n in targets if (d := self._deploy.document(v)) is not None and d.section(n)]
        count = sum(len(self._deploy.document(v).section(n).units) for v, n in targets)
        where = ", ".join(f"{n} in {v}" for v, n in targets)
        if not messagebox.askyesno(
                "Remove section",
                f"Remove {where}, with {'its' if len(targets) == 1 else 'their'} {count} unit{'s' if count != 1 else ''}?\n\n"
                "Scripts that deploy the section by name will find nothing.", parent=self):
            return
        if self._selection and self._selection[0] == "unit":
            self._selection = None

        def edit(docs):
            for variant, section_name in targets:
                dispo.remove_section(docs[variant], section_name)

        self._edit_units(edit, f"Removed section {name}")

    @staticmethod
    def _section_army(section) -> str:
        if not section.units:
            return "empty"
        return dispo.FACTION_NAMES.get(section.units[0][F["faction"]], f"faction {section.units[0][F['faction']]}")

    def _target_section(self) -> str | None:
        text = self._section_var.get()
        return text.split("  (", 1)[0] if text else None

    def _refresh_catalogs(self) -> None:
        self._choices_cache = None
        terrains = self._map.terrain_types
        self._terrain_choices = {self._map.terrain_choice_text(t): t.name for t in terrains}
        self._terrain_combo.configure(values=list(self._terrain_choices))
        if self._terrain_var.get() not in self._terrain_choices and terrains:
            self._terrain_var.set(next(iter(self._terrain_choices)))
        self._refresh_prop_list()

    def _refresh_prop_list(self, select: str | None = None) -> None:
        """The Place prop list: the map's props, keeping the chosen one."""
        from .. import map_props

        data = self._map.map_data
        names = map_props.prop_names(self._map.pak_contents, data) if data else []
        current = self._prop_list.curselection()
        select = select or (self._prop_list.get(current[0]) if current else None)
        if list(self._prop_list.get(0, "end")) != names:
            self._prop_list.delete(0, "end")
            for name in names:
                self._prop_list.insert("end", name)
        self._prop_list.selection_clear(0, "end")
        if select in names:
            self._prop_list.selection_set(names.index(select))
            self._prop_list.see(names.index(select))

    def _prop_signature(self):
        data = self._map.map_data
        if data is None:
            return None
        return tuple((i.x, i.y, i.angle, i.desc_index, i.unused) for i in data.build_inst), len(data.build_desc)

    def _refresh_canvas(self) -> None:
        canvas = self._canvas
        data = self._map.map_data
        if data is None or data.capacity is None:
            canvas.size = None
            canvas.units = []
            canvas.redraw()
            # the inspector still works without a map
            self._refresh_inspector()
            return
        cap = data.capacity
        canvas.size = (cap.x_size, cap.y_size)
        canvas.backdrop = self._backdrop
        canvas.terrain = self._map.terrain_grid
        canvas.heights = self._heights_grid(data)
        selection = self._selection
        canvas.selected_tiles = ({(selection[1], selection[2])} if selection and selection[0] == "tile" else
                                 set(selection[1]) if selection and selection[0] == "tiles" else set())
        extra = data.extra
        canvas.playable = None
        if extra is not None and 0 < extra.grid_buffer * 2 < min(cap.x_size, cap.y_size):
            b = extra.grid_buffer
            canvas.playable = (b, cap.x_size - b, b, cap.y_size - b)
        canvas.show = {key: var.get() for key, var in self._layer_vars.items()}

        props = []
        selected_prop = self._selection[1] if self._selection and self._selection[0] == "prop" else None
        for i, inst in enumerate(data.build_inst):
            if not 0 <= inst.desc_index < len(data.build_desc):
                continue
            obj = data.build_desc[inst.desc_index]
            if map_file.is_base_terrain_object(obj) or not (0 <= inst.x < cap.x_size and 0 <= inst.y < cap.y_size):
                continue  # the terrain itself, and scenery beyond the grid (not editable here)
            rect = (inst.x2, inst.y2, inst.end_x2, inst.end_y2)
            if not (rect[0] <= inst.x <= rect[2] and rect[1] <= inst.y <= rect[3]):
                rect = (inst.x, inst.y, inst.x, inst.y)
            rect = (max(rect[0], 0), max(rect[1], 0), min(rect[2], cap.x_size - 1), min(rect[3], cap.y_size - 1))
            props.append({"index": i, "rect": rect, "color": _prop_color(inst.desc_index), "selected": i == selected_prop,
                          "model": f"{obj.filename}.gs" in self._map.pak_contents, "name": obj.filename})
        canvas.props = props

        units = []
        doc = self._doc()
        only = self._filter_var.get()
        if doc is not None:
            for section in doc.sections:
                if only != "All sections" and section.name != only:
                    continue
                for ui, unit in enumerate(section.units):
                    selected = self._selection == ("unit", section.name, ui)
                    highlight = self._highlight == (self._variant(), section.name)
                    units.append({
                        "key": (section.name, ui), "x": unit[F["pos_x"]], "y": unit[F["pos_y"]],
                        "pos2": (unit[F["pos2_x"]], unit[F["pos2_y"]]),
                        "color": FACTION_COLORS.get(unit[F["faction"]], "#8a8a8a"),
                        "text": self._short_name(unit[F["pid"]]), "selected": selected, "highlight": highlight,
                    })
        canvas.units = units

        zones, _problem = self._zone_state()
        selected_zone = self._selection[1] if self._selection and self._selection[0] == "zone" else None
        canvas.zones = []
        for zone in zones:
            x1, y1, x2, y2 = zone.rect
            if x2 < 0 or y2 < 0 or x1 >= cap.x_size or y1 >= cap.y_size:
                continue
            rect = (max(x1, 0), max(y1, 0), min(x2, cap.x_size - 1), min(y2, cap.y_size - 1))
            color = ZONE_COLORS.get(zone.mode, "#bdbdbd") if zone.is_area else LOCATION_COLOR
            text = zone.function if zone.is_area else f"{zone.function} [{zone.mode}]"
            canvas.zones.append({"function": zone.function, "rect": rect, "area": zone.is_area, "color": color,
                                 "text": text, "selected": zone.function == selected_zone})
        canvas.redraw()
        self._refresh_inspector()

    def _layers_changed(self) -> None:
        self._refresh_canvas()

    def _heights_grid(self, data):
        """Mean combined elevation of each tile, ``[x][y]``, cached per map.bin."""
        map_bin = self._map.pak_contents.get("map.bin")
        if getattr(self, "_heights_key", None) is map_bin:
            return self._heights_cache
        grid, panels = data.panel_index, data.unique_panel
        heights = None
        if grid is not None and panels:
            heights = [[sum(map_heights._record(panels[i])[:4]) / 4 if 0 <= i < len(panels) else 0 for i in column]
                       for column in grid]
        self._heights_key, self._heights_cache = map_bin, heights
        return heights

    def _short_name(self, pid) -> str:
        if not isinstance(pid, str):
            return "?"
        info = self._character(pid)
        name = info.name if info is not None and info.name else pid.removeprefix("PID_")
        return name[:3]

    def _character(self, pid):
        index = self._index_provider()
        return getattr(index, "by_pid", {}).get(pid) if index is not None else None

    def _update_buttons(self) -> None:
        self._undo_button.configure(state="normal" if self._undo else "disabled")
        self._redo_button.configure(state="normal" if self._redo else "disabled")
        dirty = [p.display_name for p in self._panels() if p.dirty]
        self._status.configure(text=("Unsaved: " + ", ".join(dirty)) if dirty else "")

    # -- backdrop render -----------------------------------------------------------------
    def _on_shown(self) -> None:
        if self._render_wanted:
            self._request_render(0)
        if self._zones_stale:
            self._on_script_changed()

    def _request_render(self, delay: int) -> None:
        if self._render_after is not None:
            self.after_cancel(self._render_after)
            self._render_after = None
        if not self.winfo_ismapped():
            self._render_wanted = True
            return
        self._render_wanted = False
        self._render_after = self.after(delay, self._start_render)

    def _start_render(self) -> None:
        self._render_after = None
        data = self._map.map_data
        camera = map_scene.topdown_camera(data, BACKDROP_PX_PER_TILE) if data is not None else None
        if camera is None:
            return
        if not self._gpu_checked:
            self._gpu_checked = True
            self._gpu = gpu_renderer.create_renderer()
        self._render_generation += 1
        generation = self._render_generation
        signature = self._prop_signature()
        files, gpu = dict(self._map.pak_contents), self._gpu
        results: "queue.Queue" = queue.Queue()

        def worker() -> None:
            try:
                scene = map_scene.build_map_scene(files, data)
                results.put(("scene", scene) if gpu is not None else ("image", map_scene.render_topdown(scene, camera)))
            except Exception as exc:  # noqa: BLE001
                results.put(("error", str(exc)))

        self._hover.configure(text="Rendering the map image…")
        threading.Thread(target=worker, daemon=True).start()
        self._poll_render(results, generation, camera, signature)

    def _poll_render(self, results, generation, camera, signature) -> None:
        try:
            kind, payload = results.get_nowait()
        except queue.Empty:
            self.after(100, lambda: self._poll_render(results, generation, camera, signature))
            return
        if generation != self._render_generation:
            return
        if kind == "scene":
            try:
                payload = map_scene.render_topdown(payload, camera, self._gpu)
            except Exception:  # noqa: BLE001 - fall back to the CPU rasterizer
                gpu_renderer.log.warning("GPU render failed - switching to the CPU rasterizer", exc_info=True)
                self._gpu = None
                payload = map_scene.render_topdown(payload, camera, None)
            kind = "image"
        if kind == "error":
            self._hover.configure(text=f"Could not render the map image: {payload}")
            return
        self._backdrop = payload
        self._rendered_props = signature
        self._hover.configure(text="")
        self._refresh_canvas()
        play = self._windows.get("play")
        if play is not None and play.winfo_exists():
            play.backdrop_ready(payload)  # the Play window may have drawn before the picture was ready

    # -- undo ------------------------------------------------------------------------------
    def _state(self) -> tuple:
        script = self._script.source_snapshot() if self._script is not None else None
        return self._map.snapshot(), self._deploy.snapshot(), script

    def _record(self) -> None:
        self._undo.append(self._state())
        del self._undo[:-50]
        self._redo.clear()
        self._update_buttons()

    def _swap(self, source: list, target: list) -> None:
        if not source:
            return
        map_state, units, script = source.pop()
        target.append(self._state())
        if map_state is not None and map_state != self._map.snapshot():
            self._map.restore(map_state)
        if units != self._deploy.snapshot():
            self._deploy.restore(units)
        if self._script is not None:
            self._script.restore_source(script)
        self._selection = None
        self._refresh_canvas()
        self._update_buttons()

    def _do_undo(self) -> None:
        self._swap(self._undo, self._redo)

    def _do_redo(self) -> None:
        self._swap(self._redo, self._undo)

    def _panels(self) -> list:
        """The editors whose data this tab edits (the script only while the
        Script tab shows this chapter's own script)."""
        panels = [self._map, self._deploy]
        if self._script is not None and self._script.chapter_source() is not None:
            panels.append(self._script)
        return panels

    def _save(self) -> None:
        for panel in self._panels():
            if panel.dirty and not panel.save():
                break
        self._update_buttons()

    # -- windows ------------------------------------------------------------------------------
    @property
    def map_editor(self):
        return self._map

    def _open_window(self, key: str, factory, needs_map: bool = True) -> None:
        window = self._windows.get(key)
        if window is not None and window.winfo_exists():
            window.deiconify()
            window.lift()
            window.focus_set()
            return
        if needs_map and self._map.map_data is None:
            messagebox.showinfo("Build", "Open a chapter with a map first.", parent=self)
            return
        self._windows[key] = factory(self)

    def open_objects(self) -> None:
        from .map_windows import MapObjectsWindow

        self._open_window("objects", MapObjectsWindow)

    def open_settings(self) -> None:
        from .map_windows import MapSettingsWindow

        self._open_window("settings", MapSettingsWindow)

    def open_3d(self) -> None:
        from .map_windows import Map3DWindow

        self._open_window("3d", Map3DWindow)

    def open_play(self) -> None:
        """Play the chapter on this map (moves, fights, events, the enemy AI), step by step."""
        from .playthrough_window import PlaythroughWindow

        self._open_window("play", PlaythroughWindow)

    def open_disposition(self) -> None:
        from .dispo_window import DispositionWindow

        if not self._deploy.variants():
            messagebox.showinfo("Build", "This chapter has no deployment file.", parent=self)
            return
        self._open_window("disposition", DispositionWindow, needs_map=False)

    def _notify_disposition(self) -> None:
        window = self._windows.get("disposition")
        if window is not None and window.winfo_exists():
            window.units_changed()

    @property
    def project(self):
        return self._project

    @property
    def changelog(self):
        return self._changelog

    @property
    def fe8_session(self):
        """The shared FE8Data.bin session (None outside the workspace)."""
        return self._session_provider()

    def cleanup(self) -> None:
        for window in list(self._windows.values()):
            if window.winfo_exists():
                window.close()

    def undo(self) -> None:
        self._do_undo()

    def redo(self) -> None:
        self._do_redo()

    def selected_instance(self) -> int | None:
        return self._selection[1] if self._selection and self._selection[0] == "prop" else None

    def select_instance(self, index: int) -> None:
        """Select a placed object (from the Objects window). The terrain and
        objects beyond the grid aren't drawn, so they only show in the window."""
        if any(p["index"] == index for p in self._canvas.props):
            if self._selection != ("prop", index):
                self._select(("prop", index))
        elif self._selection is not None and self._selection[0] == "prop":
            self._select(None)

    def run_undoable(self, action) -> None:
        """Run a map action that edits through the MapEditor itself (water
        import, water flow) as one Undo step; nothing is recorded when it
        changes nothing (the user cancelled)."""
        self._record()
        before = self._map.snapshot()
        action()
        if self._map.snapshot() == before:
            self._undo.pop()
        self._update_buttons()

    # -- edits -------------------------------------------------------------------------------
    def edit_map(self, edit, log_text: str, raise_errors: bool = False) -> bool:
        """``edit(files)`` through ``MapEditor.edit_map`` as one Undo step."""
        self._record()
        try:
            self._map.edit_map(edit, log_text)
        except Exception as exc:  # noqa: BLE001
            self._undo.pop()
            self._update_buttons()
            if raise_errors:
                raise
            messagebox.showerror("Build", str(exc), parent=self)
            return False
        self._update_buttons()
        return True

    _edit_map = edit_map

    @staticmethod
    def _covered(data, index: int | None) -> set:
        """The grid tiles instance ``index`` covers (none for the terrain)."""
        cap = data.capacity
        if index is None or cap is None or not 0 <= index < len(data.build_inst):
            return set()
        inst = data.build_inst[index]
        obj = data.build_desc[inst.desc_index] if 0 <= inst.desc_index < len(data.build_desc) else None
        if obj is None or map_file.is_base_terrain_object(obj):
            return set()
        return {(x, y) for x in range(inst.x2, inst.end_x2 + 1) for y in range(inst.y2, inst.end_y2 + 1)
                if 0 <= x < cap.x_size and 0 <= y < cap.y_size}

    def _prop_edit(self, op, log_text: str, index: int | None = None):
        """Run ``op(files)`` - a prop edit returning the instance's index
        afterwards (None once deleted) - as one Undo step. With "Heights
        follow props", the tiles the instance covered and now covers get
        deduced corner heights. Returns the index, or False on failure."""
        out = {}

        def edit(files):
            before = self._covered(map_file.read_map_bytes(files["map.bin"]), index)
            out["index"] = op(files)
            if self._auto_heights.get():
                data = map_file.read_map_bytes(files["map.bin"])
                tiles = sorted(before | self._covered(data, out["index"]))
                if tiles:
                    files["map.bin"] = map_heights.set_tile_corners(
                        files["map.bin"], map_heights.deduce_corners(files, data, tiles))

        return out.get("index") if self._edit_map(edit, log_text) else False

    def edit_instance(self, index: int, desc: int | None = None, tile=None, angle: int | None = None,
                      height: float | None = None, rect=None) -> bool:
        """Change placed object ``index`` (from the Objects window): its object,
        tile (moving keeps its height above the ground), angle (recomputing
        the covered tiles), height, covered-tiles rectangle - in that order."""
        from .. import map_props

        def op(files):
            def current():
                return map_file.read_map_bytes(files["map.bin"]).build_inst[index]

            if desc is not None:
                files["map.bin"] = map_file.patch_build_inst_field(files["map.bin"], current(), "desc_index", desc)
            if tile is not None:
                map_props.move_instance(files, index, *tile)
            if angle is not None:
                map_props.rotate_instance(files, index, angle)
            if height is not None:
                files["map.bin"] = map_file.patch_build_inst_height(files["map.bin"], current(), height)
            if rect is not None:
                for field, value in zip(("x2", "y2", "end_x2", "end_y2"), rect):
                    files["map.bin"] = map_file.patch_build_inst_field(files["map.bin"], current(), field, value)
            return index

        what = ", ".join(k for k, v in (("object", desc), ("tile", tile), ("angle", angle), ("height", height),
                                         ("covered tiles", rect)) if v is not None)
        return self._prop_edit(op, f"Edited instance {index} ({what})", index) is not False

    def add_instance(self, name: str, x: int, y: int, angle: int) -> None:
        from .. import map_props

        placed = self._prop_edit(lambda files: map_props.place_prop(files, name, x, y, angle), f"Placed {name} on ({x}, {y})")
        if placed is not False:
            self.select_instance(placed)
            window = self._windows.get("objects")
            if window is not None and window.winfo_exists():
                window.show_instance(placed)

    def delete_instance(self, index: int) -> None:
        from .. import map_props

        if self._selection and self._selection[0] == "prop":
            self._selection = None

        def op(files):
            map_props.remove_instance(files, index)
            return None

        self._prop_edit(op, f"Deleted instance {index}", index)

    def _edit_units(self, edit, log_text: str) -> bool:
        self._record()
        try:
            self._deploy.apply(edit, log_text)
        except Exception as exc:  # noqa: BLE001
            self._undo.pop()
            self._update_buttons()
            messagebox.showerror("Build", str(exc), parent=self)
            return False
        self._update_buttons()
        return True

    def _unit_targets(self, docs, section: str, index: int, all_variants: bool,
                      current: str | None = None) -> list[tuple[str, str, int]]:
        """(variant, section, index) of the selected unit (in ``current``,
        the shown deployment file by default), plus its counterparts in the
        other variants when ``all_variants``."""
        current = current or self._variant()
        unit = docs[current].section(section).units[index]
        targets = [(current, section, index)]
        if all_variants:
            for variant, doc in docs.items():
                if variant == current:
                    continue
                found = dispo.find_counterpart_unit(doc, section, unit, index)
                if found is not None:
                    targets.append((variant, dispo.counterpart_section(doc, section).name, found))
        return targets

    def _move_unit(self, key, tile) -> None:
        section, index = key
        all_variants = self._all_variants.get()

        def edit(docs):
            for variant, sec, i in self._unit_targets(docs, section, index, all_variants):
                dispo.move_unit(docs[variant].section(sec).units[i], *tile)

        self._edit_units(edit, f"Moved {section}[{index}] to {tile}")

    def _delete_selection(self) -> None:
        if not self._selection:
            return
        if self._selection[0] == "prop":
            self.delete_instance(self._selection[1])
            return
        if self._selection[0] == "zone":
            self._delete_zone(self._selection[1])
            return
        if self._selection[0] != "unit":
            return
        _kind, section, index = self._selection
        all_variants = self._all_variants.get()

        def edit(docs):
            for variant, sec, i in self._unit_targets(docs, section, index, all_variants):
                dispo.remove_unit(docs[variant], sec, i)

        self._selection = None
        self._edit_units(edit, f"Deleted unit {section}[{index}]")

    def _rotate_selected(self, angle: int | None = None) -> None:
        if not self._selection or self._selection[0] != "prop":
            return
        index = self._selection[1]
        inst = self._map.map_data.build_inst[index]
        new = (inst.angle + 192) % 256 if angle is None else angle
        from .. import map_props

        def op(files):
            map_props.rotate_instance(files, index, new)
            return index

        self._prop_edit(op, f"Turned instance {index}", index)

    def _place_prop(self, tile) -> None:
        selection = self._prop_list.curselection()
        if not selection:
            messagebox.showinfo("Place prop", "Choose a prop in the list first.", parent=self)
            return
        name = self._prop_list.get(selection[0])
        angle = ANGLES[self._prop_angle.get()]
        from .. import map_props

        placed = self._prop_edit(lambda files: map_props.place_prop(files, name, *tile, angle), f"Placed {name} on {tile}")
        if placed is not False:
            self._select(("prop", placed))

    def _add_prop_from_map(self) -> None:
        """Copy a prop of another chapter map into this one and choose it for
        Place prop. A prop of the same name that is the same model is just
        chosen; a different one is copied under another name."""
        data = self._map.map_data
        if data is None:
            return
        from .. import map_props
        from .prop_browser import PropPickerDialog

        dialog = PropPickerDialog(self, self._project, exclude=self._map.current_path)
        self.wait_window(dialog)
        if dialog.result is None:
            return
        info, source = dialog.result
        files = self._map.pak_contents
        name = info.name
        if any(o.filename == name for o in data.build_desc) or f"{name}.gs" in files:
            if map_props.same_prop(source, info.name, files, name):
                messagebox.showinfo("Add prop", f"This map already has {name}, the same model. It is chosen for Place prop.",
                                    parent=self)
                self._choose_prop(name)
                return
            name = simpledialog.askstring(
                "Prop name", f"This map already has a different object named {info.name}.\nName of the copy:",
                initialvalue=map_props.free_prop_name(files, data, info.name), parent=self)
            if not name:
                return
        self._record()
        try:
            self._map.copy_prop(source, info.name, name, info.map_name)
        except Exception as exc:  # noqa: BLE001
            self._undo.pop()
            self._update_buttons()
            messagebox.showerror("Could not add prop", str(exc), parent=self)
            return
        self._update_buttons()
        self._choose_prop(name)

    def _import_prop(self) -> None:
        result = {}
        self.run_undoable(lambda: result.setdefault("name", self._map.import_prop(self)))
        if result.get("name"):
            self._choose_prop(result["name"])

    def _choose_prop(self, name: str) -> None:
        self._tool.set("prop")
        self._tool_changed()
        self._refresh_prop_list(select=name)

    def add_unit(self) -> None:
        """Add a unit without picking a tile first: the Place unit dialog, then the unit stands on a free
        tile near the middle of the playable area, selected, ready to be dragged where it belongs."""
        data = self._map.map_data
        if data is None or data.capacity is None:
            messagebox.showinfo("Add unit", "Open a chapter with a map first.", parent=self)
            return
        self._tool.set("unit")
        self._tool_changed()
        cap = data.capacity
        x0, x1, y0, y1 = self._canvas.playable or (0, cap.x_size, 0, cap.y_size)
        doc = self._doc()
        taken = {(u[F["pos_x"]], u[F["pos_y"]]) for section in (doc.sections if doc else ()) for u in section.units}
        centre = ((x0 + x1 - 1) / 2, (y0 + y1 - 1) / 2)
        free = sorted(((x, y) for x in range(x0, x1) for y in range(y0, y1) if (x, y) not in taken),
                      key=lambda t: (abs(t[0] - centre[0]) + abs(t[1] - centre[1]), t[1], t[0]))
        if not free:
            messagebox.showinfo("Add unit", "Every tile of the map already has a unit.", parent=self)
            return
        battle = self._battle_section()
        if battle is not None and "battle start" not in self._section_var.get():
            self._section_var.set(battle)  # the usual place for a new enemy; the dialog can change it
        before = self._selection
        self._place_unit(free[0], choose_section=True)
        if self._selection != before and self._selection and self._selection[0] == "unit":
            self._hover.configure(text=f"Unit added on tile {free[0]}: drag it to where it should stand.")

    def _place_unit(self, tile, choose_section: bool = False) -> None:
        section = self._target_section()
        current = self._variant()
        if not section or current is None:
            messagebox.showinfo("Place unit", "This chapter has no deployment section.", parent=self)
            return
        characters, classes, _items, _skills = self._choices()
        sections = list(self._section_combo.cget("values")) if choose_section else None
        dialog = _NewUnitDialog(self, characters, classes, tile, section, sections)
        self.wait_window(dialog)
        if dialog.result is None:
            return
        pid, jid, level = dialog.result[:3]
        if choose_section:
            self._section_var.set(dialog.result[3])
            section = self._target_section()
        docs_now = {v: self._deploy.document(v) for v in self._deploy.variants()}
        template_section = docs_now[current].section(section)
        template = list(template_section.units[0]) if template_section.units else dispo.new_unit_values()
        for f in range(3, 16):  # items and skills belong to the template's character
            template[f] = 0
        for f in range(40, 48):
            template[f] = 0
        for f in PER_VARIANT_FIELDS:
            template[f] = 0
        template[F["pid"]], template[F["jid"]], template[F["level"]] = pid, jid, level
        template[F["pos_x"]], template[F["pos_y"]] = tile
        template[F["pos2_x"]], template[F["pos2_y"]] = tile
        chosen = [v for v, var in self._add_to_vars.items() if var.get()] or [current]
        added = {}

        def edit(docs):
            for variant in chosen:
                target = docs[variant].section(section) if variant == current else dispo.counterpart_section(docs[variant], section)
                if target is None:
                    continue
                added[variant] = (target.name, dispo.add_unit(docs[variant], target.name, template))

        if self._edit_units(edit, f"Added {pid} on {tile} to {section}") and current in added:
            self._select(("unit", *added[current]))

    # -- script zones ------------------------------------------------------------------------
    def _zone_state(self) -> tuple[list, Optional[str]]:
        """(zones, problem): the chapter script's zones, or none and why."""
        if self._script is None or not self._script.has_chapter_script:
            return [], "This chapter has no script."
        source = self._script.chapter_source()
        if source is None:
            return [], "The Script tab shows another file: open this chapter's script to see and edit its zones."
        if self._zones_key is None or self._zones_key[0] != source:
            try:
                self._zones_key = (source, script_zones.zones(source), None)
            except ParseError as exc:
                self._zones_key = (source, [], f"The chapter script doesn't parse (line {exc.line}: {exc.message}). "
                                               "Fix it in the Script tab to see its zones.")
        return self._zones_key[1], self._zones_key[2]

    def _zone(self, function: str):
        return next((z for z in self._zone_state()[0] if z.function == function), None)

    def _zones_at(self, tile) -> list[str]:
        """The functions of the drawn zones covering ``tile``, smallest zone first."""
        found = [z for z in self._canvas.zones if z["rect"][0] <= tile[0] <= z["rect"][2] and z["rect"][1] <= tile[1] <= z["rect"][3]]
        found.sort(key=lambda z: (z["rect"][2] - z["rect"][0] + 1) * (z["rect"][3] - z["rect"][1] + 1))
        return [z["function"] for z in found]

    def _zone_at(self, tile) -> Optional[str]:
        if not self._canvas.show["zones"]:
            return None
        found = self._zones_at(tile)
        return found[0] if found else None

    def _on_script_changed(self) -> None:
        if not self.winfo_ismapped():
            self._zones_stale = True
            return
        self._zones_stale = False
        self._refresh_zone_tool()
        self._refresh_canvas()
        self._update_buttons()

    def _refresh_zone_tool(self) -> None:
        zones, problem = self._zone_state()
        choices = {NEW_FUNCTION: None}
        if problem is None:
            for name, unused in script_zones.attachable_functions(self._script.chapter_source()):
                choices[f"{name}  (unused)" if unused else name] = name
        self._zone_function_choices = choices
        self._zone_function_box.configure(values=list(choices))
        if self._zone_function.get() not in choices:
            self._zone_function.set(NEW_FUNCTION)
        if problem is None:
            self._zone_note.configure(text=f"{len(zones)} zone(s) in {self._script.current_path.name}.")
        else:
            self._zone_note.configure(text=problem)
        if problem is not None and self._script is not None and self._script.has_chapter_script:
            self._zone_open_script.pack(anchor="w", pady=(4, 0))
        else:
            self._zone_open_script.pack_forget()

    def _open_chapter_script(self) -> None:
        if self._script is not None and self._script.show_chapter_script():
            self._on_script_changed()

    @staticmethod
    def _mode_names(trigger_type: int) -> list[str]:
        return list((SIDES if trigger_type == script_zones.AREA else ACTIONS).values())

    def _zone_kind_changed(self) -> None:
        kind = ZONE_KINDS[self._zone_kind.get()]
        names = self._mode_names(kind)
        self._zone_mode_label.configure(text="Triggered by" if kind == script_zones.AREA else "Action")
        self._zone_mode_box.configure(values=names)
        if self._zone_mode.get() not in names:
            self._zone_mode.set(names[0] if kind == script_zones.AREA else "visit")

    @staticmethod
    def _mode_value(text: str):
        """A side/action from its combobox text (a number if it has no name)."""
        text = text.strip()
        return int(text) if text.lstrip("-").isdigit() else text

    def _edit_script(self, edit, select: Optional[str] = None) -> bool:
        """Run ``edit(source) -> source`` on the chapter script as one Undo step."""
        _zones, problem = self._zone_state()
        if problem is not None:
            messagebox.showinfo("Script zones", problem, parent=self)
            return False
        source = self._script.chapter_source()
        try:
            new = edit(source)
        except (ParseError, ValueError, KeyError) as exc:
            messagebox.showerror("Script zones", str(exc).strip("'\""), parent=self)
            return False
        if new == source:
            return True
        self._record()
        self._script.edit_chapter_source(new, select=select)
        self._update_buttons()
        return True

    def _add_zone(self, rect) -> None:
        kind = ZONE_KINDS[self._zone_kind.get()]
        mode = self._mode_value(self._zone_mode.get())
        function = self._zone_function_choices.get(self._zone_function.get())
        out = {}

        def edit(source):
            new, out["name"] = script_zones.add_zone(source, kind, rect, mode, None, function=function)
            return new

        if self._edit_script(edit, select=function):
            self._zone_function.set(NEW_FUNCTION)
            what = "gets the zone's trigger" if function else "is a new function: write what it does in the Script tab"
            self._zone_note.configure(text=f"Added a zone on {rect[:2]}–{rect[2:]}. {out['name']} {what}.")
            self._select(("zone", out["name"]))

    def _moved_zone_rect(self, function: str, dx: int, dy: int):
        """The zone's tiles moved by (dx, dy), kept on the map grid."""
        zone = self._zone(function)
        if zone is None or self._canvas.size is None:
            return None
        w, h = self._canvas.size
        x1, y1, x2, y2 = zone.rect
        dx = max(-x1, min(dx, w - 1 - x2))
        dy = max(-y1, min(dy, h - 1 - y2))
        return x1 + dx, y1 + dy, x2 + dx, y2 + dy

    def _move_zone(self, function: str, dx: int, dy: int) -> None:
        rect = self._moved_zone_rect(function, dx, dy)
        if rect is not None:
            self._edit_script(lambda source: script_zones.update_zone(source, function, rect=rect))

    def _delete_zone(self, function: str) -> None:
        out = {}

        def edit(source):
            new, out["result"] = script_zones.delete_zone(source, function)
            return new

        if self._selection == ("zone", function):
            self._selection = None
        if self._edit_script(edit):
            if out["result"] == "deleted":
                note = f"Deleted the zone and its empty function {function}."
            else:
                note = (f"Deleted the zone. {function} has code (or is exported or called), so it is kept without a "
                        "trigger and marked UNUSED in its description.")
            self._zone_note.configure(text=note)
            self._hover.configure(text=note)
            self._refresh_canvas()

    def _zone_inspector(self, body, function: str) -> None:
        zone = self._zone(function)
        if zone is None:
            self._selection = None
            self._refresh_inspector()
            return
        source = self._script.chapter_source()
        ttk.Label(body, text=f"Zone: {function}", font=("Segoe UI", 11, "bold")).pack(anchor="w")
        info = zone.trigger_text() + (f"\nExported as {zone.export_id}" if zone.export_id else "")
        ttk.Label(body, text=info, style="Muted.TLabel", wraplength=300, justify="left").pack(anchor="w", pady=(2, 8))
        form = ttk.Frame(body)
        form.pack(anchor="w", fill="x")
        v = {"name": tk.StringVar(value=function), "description": tk.StringVar(value=zone.description.replace("\n", " / ")),
             "kind": tk.StringVar(value=next(k for k, t in ZONE_KINDS.items() if t == zone.type)),
             "mode": tk.StringVar(value=str(zone.mode)),
             "label": tk.StringVar(value="" if zone.label is None else str(zone.label))}
        for key, value in zip(("x1", "y1", "x2", "y2"), zone.rect):
            v[key] = tk.StringVar(value=str(value))
        self._form_vars = v
        row = 0

        def add(label, widget):
            nonlocal row
            ttk.Label(form, text=label).grid(row=row, column=0, sticky="w", pady=2)
            widget.grid(row=row, column=1, sticky="w", pady=2, padx=(8, 0))
            row += 1

        add("Function", ttk.Entry(form, textvariable=v["name"], width=26))
        add("Description", ttk.Entry(form, textvariable=v["description"], width=26))
        kind_box = ttk.Combobox(form, textvariable=v["kind"], values=list(ZONE_KINDS), state="readonly", width=26)
        add("Kind", kind_box)
        mode_label = ttk.Label(form)
        mode_box = ttk.Combobox(form, textvariable=v["mode"], state="readonly", width=16)
        mode_label.grid(row=row, column=0, sticky="w", pady=2)
        mode_box.grid(row=row, column=1, sticky="w", pady=2, padx=(8, 0))
        row += 1
        spins = {}
        for label, keys in (("From tile", ("x1", "y1")), ("To tile", ("x2", "y2"))):
            tiles = ttk.Frame(form)
            add(label, tiles)
            for i, key in enumerate(keys):
                ttk.Label(tiles, text="XY"[i]).pack(side="left", padx=(0 if i == 0 else 8, 2))
                spins[key] = ttk.Spinbox(tiles, from_=0, to=255, textvariable=v[key], width=4)
                spins[key].pack(side="left")
        add("Event name", ttk.Entry(form, textvariable=v["label"], width=26))

        def kind_changed(_event=None) -> None:
            kind = ZONE_KINDS[v["kind"].get()]
            names = self._mode_names(kind)
            if kind == zone.type and str(zone.mode) not in names:
                names.append(str(zone.mode))
            mode_box.configure(values=names)
            if v["mode"].get() not in names:
                v["mode"].set(str(zone.mode) if kind == zone.type else names[0] if kind == script_zones.AREA else "visit")
            mode_label.configure(text="Triggered by" if kind == script_zones.AREA else "Action")
            for key in ("x2", "y2"):
                spins[key].configure(state="normal" if kind == script_zones.AREA else "disabled")

        kind_box.bind("<<ComboboxSelected>>", kind_changed)
        kind_changed()
        buttons = ttk.Frame(body)
        buttons.pack(anchor="w", pady=(10, 0))
        ttk.Button(buttons, text="Apply", command=lambda: self._apply_zone(function)).pack(side="left")
        ttk.Button(buttons, text="Delete zone", command=lambda: self._delete_zone(function)).pack(side="left", padx=(6, 0))
        if self._on_open_function is not None:
            ttk.Button(buttons, text="Open in Script tab", command=lambda: self._on_open_function(function)).pack(side="left", padx=(6, 0))
        try:
            empty = script_zones.is_empty(source, function)
        except (ParseError, StopIteration):
            empty = False
        if empty and zone.export_id is None and not script_zones.is_referenced(source, function):
            fate = "The function is empty: deleting the zone deletes it."
        else:
            fate = "Deleting the zone keeps the function (it has code, or is exported or called), without its trigger and marked UNUSED."
        ttk.Label(body, text=fate, style="Muted.TLabel", wraplength=300, justify="left").pack(anchor="w", pady=(10, 0))
        ttk.Label(body, text="Event name: the trigger's name label (a debug label for a zone; empty for none). "
                             "Area sides and location actions: see the script tutorial, lessons 7 and 11. Changing "
                             "the code the zone runs is done in the Script tab.",
                  style="Muted.TLabel", wraplength=300, justify="left").pack(anchor="w", pady=(6, 0))

    def _apply_zone(self, function: str) -> None:
        v = self._form_vars
        zone = self._zone(function)
        if zone is None:
            return
        kind = ZONE_KINDS[v["kind"].get()]
        try:
            coords = [int(v[k].get()) for k in ("x1", "y1", "x2", "y2")]
        except ValueError:
            messagebox.showerror("Zone", "Tile coordinates are whole numbers.", parent=self)
            return
        if kind == script_zones.LOCATION:
            coords[2:] = coords[:2]
        rect = _ordered(coords[:2], coords[2:])
        size = self._canvas.size
        if size is not None and (rect[0] < 0 or rect[1] < 0 or rect[2] >= size[0] or rect[3] >= size[1]):
            messagebox.showerror("Zone", f"The zone must be on the map grid (0-{size[0] - 1}, 0-{size[1] - 1}).", parent=self)
            return
        label = v["label"].get().strip() or None
        name = v["name"].get().strip()
        description = "\n".join(part.strip() for part in v["description"].get().split(" / ") if part.strip())
        if name != function:
            self._selection = ("zone", name)

        def edit(source):
            return script_zones.update_zone(source, function, rect=rect, mode=self._mode_value(v["mode"].get()),
                                            label=label, trigger_type=kind, new_name=name,
                                            description=description if description != zone.description else None)

        if not self._edit_script(edit, select=name):
            self._selection = ("zone", function)

    # -- pointer ------------------------------------------------------------------------------
    def _unit_at(self, tile):
        for unit in reversed(self._canvas.units):
            if (unit["x"], unit["y"]) == tile:
                return unit["key"]
        return None

    def _prop_at(self, tile):
        for prop in reversed(self._canvas.props):
            x0, y0, x1, y1 = prop["rect"]
            if x0 <= tile[0] <= x1 and y0 <= tile[1] <= y1:
                return prop["index"]
        return None

    def on_press(self, tile, event) -> None:
        tool = self._tool.get()
        self._press_state = None
        if tile is None:
            return
        if tool == "select":
            key = self._unit_at(tile) if self._canvas.show["units"] else None
            if key is not None:
                self._select(("unit", *key))
                self._press_state = {"kind": "unit", "key": key, "start": tile}
                return
            prop = self._prop_at(tile) if self._canvas.show["props"] else None
            if prop is not None:
                self._select(("prop", prop))
                self._press_state = {"kind": "prop", "index": prop, "start": tile}
                return
            self._select(("tile", *tile))
        elif tool == "heights":
            self._press_state = {"kind": "tiles", "start": tile}
            self._select(("tile", *tile))
        elif tool == "terrain":
            self._press_state = {"kind": "paint", "start": tile, "tiles": {tile}}
            self._canvas.preview_tiles([tile], self._paint_color())
        elif tool == "prop":
            self._place_prop(tile)
        elif tool == "unit":
            self._place_unit(tile)
        elif tool == "zone":
            zone = None if event is not None and event.state & 0x0001 else self._zone_at(tile)  # Shift: draw anyway
            if zone is not None:
                self._select(("zone", zone))
                self._press_state = {"kind": "zone", "function": zone, "start": tile}
            else:
                self._press_state = {"kind": "zone_new", "start": tile}
                self._canvas.preview_rect((*tile, *tile), "#ffe14d")

    def on_drag(self, tile, _event) -> None:
        state = self._press_state
        if state is None or tile is None:
            return
        if state["kind"] == "tiles":
            (ax, ay), (bx, by) = state["start"], tile
            state["to"] = tile
            self._canvas.preview_tiles([(x, y) for x in range(min(ax, bx), max(ax, bx) + 1)
                                        for y in range(min(ay, by), max(ay, by) + 1)], "")
        elif state["kind"] == "paint":
            if self._rect_fill.get():
                (ax, ay), (bx, by) = state["start"], tile
                state["tiles"] = {(x, y) for x in range(min(ax, bx), max(ax, bx) + 1) for y in range(min(ay, by), max(ay, by) + 1)}
            else:
                state["tiles"].add(tile)
            self._canvas.preview_tiles(state["tiles"], self._paint_color())
        elif state["kind"] == "zone_new":
            if ZONE_KINDS[self._zone_kind.get()] == script_zones.LOCATION:
                state["start"] = tile
            state["to"] = tile
            self._canvas.preview_rect(_ordered(state["start"], tile), "#ffe14d")
        elif state["kind"] == "zone":
            state["to"] = tile
            rect = self._moved_zone_rect(state["function"], tile[0] - state["start"][0], tile[1] - state["start"][1])
            if rect is not None:
                self._canvas.preview_rect(rect, "#ffe14d")
        else:
            state["to"] = tile
            self._canvas.preview_marker(tile, "#ffe14d")
        self.on_hover(tile)

    def on_release(self, tile, _event) -> None:
        state, self._press_state = self._press_state, None
        self._canvas.delete("preview")
        if state is None:
            return
        if state["kind"] == "tiles":
            target = state.get("to")
            if target is not None and target != state["start"]:
                (ax, ay), (bx, by) = state["start"], target
                self._select(("tiles", frozenset((x, y) for x in range(min(ax, bx), max(ax, bx) + 1)
                                                 for y in range(min(ay, by), max(ay, by) + 1))))
            return
        if state["kind"] == "zone_new":
            self._add_zone(_ordered(state["start"], state.get("to", state["start"])))
            return
        if state["kind"] == "paint":
            name = self._terrain_choices.get(self._terrain_var.get())
            if name:
                self._record()
                try:
                    changed = self._map.paint_terrain(state["tiles"], name)
                except Exception as exc:  # noqa: BLE001
                    changed = 0
                    messagebox.showerror("Paint terrain", str(exc), parent=self)
                if not changed:
                    self._undo.pop()
                self._update_buttons()
            return
        target = state.get("to")
        if target is None or target == state["start"]:
            return
        if state["kind"] == "zone":
            self._move_zone(state["function"], target[0] - state["start"][0], target[1] - state["start"][1])
        elif state["kind"] == "unit":
            self._move_unit(state["key"], target)
        elif state["kind"] == "prop":
            from .. import map_props

            index = state["index"]

            def op(files):
                map_props.move_instance(files, index, *target)
                return index

            self._prop_edit(op, f"Moved instance {index} to {target}", index)

    def on_right(self, tile, event) -> None:
        if tile is None:
            return
        if self._tool.get() == "terrain" and self._canvas.terrain is not None:
            name = self._canvas.terrain[tile[0]][tile[1]]
            text = next((t for t, n in self._terrain_choices.items() if n == name), None)
            if text:
                self._terrain_var.set(text)
            return
        key = self._unit_at(tile)
        prop = self._prop_at(tile)
        menu = tk.Menu(self, tearoff=0)
        menu.add_command(label="Tile heights...", command=lambda: self._select(("tile", *tile)))
        if key is not None:
            menu.add_command(label="Select unit", command=lambda: self._select(("unit", *key)))
            menu.add_command(label="Delete unit", command=lambda: (self._select(("unit", *key)), self._delete_selection()))
        if prop is not None:
            menu.add_command(label="Select prop", command=lambda: self._select(("prop", prop)))
            menu.add_command(label="Turn prop 90°", command=lambda: (self._select(("prop", prop)), self._rotate_selected()))
            menu.add_command(label="Delete prop", command=lambda: (self._select(("prop", prop)), self._delete_selection()))
        if self._canvas.show["zones"]:
            for zone in self._zones_at(tile):
                menu.add_separator()
                menu.add_command(label=f"Select zone {zone}", command=lambda z=zone: self._select(("zone", z)))
                menu.add_command(label=f"Delete zone {zone}", command=lambda z=zone: self._delete_zone(z))
                if self._on_open_function is not None:
                    menu.add_command(label=f"Open {zone} in the Script tab", command=lambda z=zone: self._on_open_function(z))
        if menu.index("end") is not None:
            menu.tk_popup(event.x_root, event.y_root)

    def on_hover(self, tile) -> None:
        size = self._canvas.size
        if tile is None or size is None or not (0 <= tile[0] < size[0] and 0 <= tile[1] < size[1]):
            self._hover.configure(text="")
            return
        parts = [f"Tile {tile}"]
        grid = self._canvas.terrain
        if grid is not None:
            name = grid[tile[0]][tile[1]]
            parts.append(f"{self._map.terrain_label(name)} [{name}]")
        data = self._map.map_data
        corners = map_heights.tile_corners(data, tile).get("combined") if data is not None else None
        if corners is not None:
            parts.append("height " + " ".join(f"{-c / 400:g}" for c in corners))
        prop = self._prop_at(tile)
        if prop is not None:
            parts.append(next(p["name"] for p in self._canvas.props if p["index"] == prop))
        doc = self._doc()
        for unit in self._canvas.units:
            if (unit["x"], unit["y"]) == tile and doc is not None:
                section, index = unit["key"]
                pid = doc.section(section).units[index][F["pid"]]
                info = self._character(pid) if isinstance(pid, str) else None
                parts.append(info.label if info is not None else str(pid))
        if self._canvas.show["zones"]:
            parts += [f"zone {z}" for z in self._zones_at(tile)]
        self._hover.configure(text="   ·   ".join(parts))

    def _paint_color(self) -> str:
        name = self._terrain_choices.get(self._terrain_var.get(), "")
        return "#%02x%02x%02x" % _terrain_color(name)

    def _tool_changed(self) -> None:
        tool = self._tool.get()
        if tool == "zone":
            self._refresh_zone_tool()
            if not self._layer_vars["zones"].get():
                self._layer_vars["zones"].set(True)
                self._refresh_canvas()
        self._tool_help.configure(text=TOOL_HELP[tool])
        for key, frame in self._tool_frames.items():
            if key == tool:
                frame.pack(anchor="w", fill="both", expand=True)
            else:
                frame.pack_forget()

    def _select(self, selection) -> None:
        self._selection = selection
        self._refresh_canvas()
        window = self._windows.get("objects")
        if window is not None and window.winfo_exists():
            window.show_instance(self.selected_instance())
        window = self._windows.get("disposition")
        if window is not None and window.winfo_exists():
            window.show_unit(self.selected_unit())

    # -- inspector -----------------------------------------------------------------------------
    def _choices(self):
        if self._choices_cache is not None:
            return self._choices_cache
        session = self._session_provider()
        fe8 = getattr(session, "fe8", None) if session is not None else None
        index = self._index_provider()
        class_names = getattr(index, "class_names", {}) if index is not None else {}
        item_names = getattr(index, "item_names", {}) if index is not None else {}
        characters, classes, items, skills = [], [], [], []
        if fe8 is not None:
            for c in fe8.characters:
                if c.pid:
                    info = self._character(c.pid)
                    characters.append((info.label if info is not None else c.pid, c.pid))
            classes = [(f"{class_names.get(c.jid) or c.jid} ({c.jid})", c.jid) for c in fe8.classes if c.jid]
            items = [(f"{item_names.get(i.iid) or i.iid} ({i.iid})", i.iid) for i in fe8.items if i.iid]
            skills = [(s.sid, s.sid) for s in fe8.skills if s.sid]
            for choices in (characters, classes, items):  # pickers list them by name
                choices.sort(key=lambda choice: choice[0].casefold())
        self._choices_cache = (characters, classes, items, skills)
        return self._choices_cache

    def _ai_choices(self) -> dict[str, list[str]]:
        """Every SEQ_/MTYPE_ label the project's deployment files use."""
        if self._ai_labels is None:
            from ..formats import lz10, pak

            docs = []
            for path in sorted(self._project.extracted_dir.glob("**/zmap/*/dispos.cmp")):
                try:
                    archive = lz10.decompress(path.read_bytes())
                    for entry in pak.read_pak_entries(archive):
                        if entry.name.startswith("dispos_"):
                            docs.append(dispo.parse_dispo(pak.read_pak_file_content(archive, entry)))
                except Exception:  # noqa: BLE001 - an unreadable file just adds nothing
                    continue
            self._ai_labels = dispo.labels_by_prefix(docs)
        return self._ai_labels

    def _clear_inspector(self) -> None:
        for child in self._inspector.winfo_children():
            child.destroy()
        self._form_vars = {}

    def _refresh_inspector(self) -> None:
        self._clear_inspector()
        body = self._inspector
        selection = self._selection
        if selection is None:
            ttk.Label(body, text="Nothing selected", font=("Segoe UI", 11, "bold")).pack(anchor="w")
            ttk.Label(body, text="Pick a tool on the left. With Select / move, click a unit or a prop to edit it here; "
                                 "with Script zones, a zone.\n\n"
                                 "Middle-drag pans, Ctrl+wheel zooms. Ctrl+Z / Ctrl+Y undo and redo.",
                      style="Muted.TLabel", wraplength=300, justify="left").pack(anchor="w", pady=(6, 0))
            return
        if selection[0] == "prop":
            self._prop_inspector(body, selection[1])
        elif selection[0] == "tile":
            self._tile_inspector(body, (selection[1], selection[2]))
        elif selection[0] == "tiles":
            self._tiles_inspector(body, sorted(selection[1]))
        elif selection[0] == "zone":
            self._zone_inspector(body, selection[1])
        else:
            self._unit_inspector(body, selection[1], selection[2])

    def _prop_inspector(self, body, index: int) -> None:
        data = self._map.map_data
        if data is None or index >= len(data.build_inst):
            self._selection = None
            self._refresh_inspector()
            return
        inst = data.build_inst[index]
        obj = data.build_desc[inst.desc_index]
        ttk.Label(body, text=obj.filename, font=("Segoe UI", 11, "bold")).pack(anchor="w")
        ttk.Label(body, text=f"Instance {index} on tile ({inst.x}, {inst.y}), covering ({inst.x2}, {inst.y2})–"
                             f"({inst.end_x2}, {inst.end_y2}), height {inst.height():g}",
                  style="Muted.TLabel", wraplength=300, justify="left").pack(anchor="w", pady=(2, 8))
        row = ttk.Frame(body)
        row.pack(anchor="w")
        ttk.Label(row, text="Angle").pack(side="left")
        current = next((k for k, v in ANGLES.items() if v == inst.angle % 256), f"{inst.angle % 256} (raw)")
        angle = tk.StringVar(value=current)
        box = ttk.Combobox(row, textvariable=angle, values=list(ANGLES), state="readonly", width=8)
        box.pack(side="left", padx=(6, 0))
        box.bind("<<ComboboxSelected>>", lambda e: self._rotate_selected(ANGLES[angle.get()]))
        buttons = ttk.Frame(body)
        buttons.pack(anchor="w", pady=(10, 0))
        ttk.Button(buttons, text="Turn 90°", command=self._rotate_selected).pack(side="left")
        ttk.Button(buttons, text="Delete", command=self._delete_selection).pack(side="left", padx=(6, 0))
        ttk.Button(buttons, text="View model...", command=lambda: self._map.view_model(self, obj.filename)).pack(side="left", padx=(6, 0))
        ttk.Label(body, text="A prop doesn't block movement by itself: paint its tiles' terrain type (for example "
                             "Obstacle) with Paint terrain.", style="Muted.TLabel", wraplength=300,
                  justify="left").pack(anchor="w", pady=(10, 0))

    LAYER_TEXT = {"combined": "Combined", "ground": "Ground", "roof": "Roof"}
    HEIGHTS_HELP = ("Elevations are the game's values: -400 is one unit higher (a tile is 5 units wide). "
                    "Units and the cursor stand on the combined layer; ground is the land under objects; roof is "
                    "used on buildings. Two neighbouring corners 400 or more apart close the way between the tiles.")

    def _tile_inspector(self, body, tile) -> None:
        data = self._map.map_data
        corners = map_heights.tile_corners(data, tile) if data is not None else {}
        ttk.Label(body, text=f"Tile {tile}", font=("Segoe UI", 11, "bold")).pack(anchor="w")
        grid = self._map.terrain_grid
        if grid is not None:
            name = grid[tile[0]][tile[1]]
            ttk.Label(body, text=f"{self._map.terrain_label(name)} [{name}]", style="Muted.TLabel").pack(anchor="w")
        if not corners:
            ttk.Label(body, text="This map has no panel layers.", style="Muted.TLabel").pack(anchor="w", pady=(6, 0))
            return
        table = ttk.Frame(body)
        table.pack(anchor="w", pady=(10, 0))
        for col, text in enumerate(("", "Top left", "Top right", "Bottom left", "Bottom right")):
            ttk.Label(table, text=text, style="Muted.TLabel").grid(row=0, column=col, sticky="w", padx=(0, 4))
        self._form_vars = {}
        for row, (layer, values) in enumerate(corners.items(), start=1):
            ttk.Label(table, text=self.LAYER_TEXT[layer]).grid(row=row, column=0, sticky="w", padx=(0, 6), pady=2)
            for k, value in enumerate(values):
                var = tk.StringVar(value=str(value))
                entry = ttk.Entry(table, textvariable=var, width=7)
                entry.grid(row=row, column=k + 1, sticky="w", padx=(0, 4))
                entry.bind("<Return>", lambda e: self._apply_tile(tile))
                self._form_vars[layer, k] = var
        buttons = ttk.Frame(body)
        buttons.pack(anchor="w", pady=(8, 0))
        ttk.Button(buttons, text="Apply", command=lambda: self._apply_tile(tile)).pack(side="left")
        ttk.Button(buttons, text="Deduce from terrain and props", command=lambda: self._deduce([tile])).pack(side="left", padx=(6, 0))
        ttk.Label(body, text=self.HEIGHTS_HELP, style="Muted.TLabel", wraplength=300, justify="left").pack(anchor="w", pady=(10, 0))
        ttk.Label(body, text="Deduce: the ground is the terrain (or a bridge deck over it); the combined and roof layers "
                             "rise to the height vanilla gives the props covering the tile (trees, walls, houses). "
                             "An estimate: check the result in game.",
                  style="Muted.TLabel", wraplength=300, justify="left").pack(anchor="w", pady=(6, 0))

    def _apply_tile(self, tile) -> None:
        data = self._map.map_data
        current = map_heights.tile_corners(data, tile)
        try:
            values = {layer: tuple(int(self._form_vars[layer, k].get()) for k in range(4)) for layer in current}
        except ValueError:
            messagebox.showerror("Tile heights", "An elevation is a whole number.", parent=self)
            return
        changed = {layer: v for layer, v in values.items() if v != current[layer]}
        if changed:
            self._edit_map(lambda files: files.__setitem__("map.bin", map_heights.set_tile_corners(files["map.bin"], {tile: changed})),
                           f"Set the corner heights of tile {tile}")

    def _deduce(self, tiles) -> None:
        def edit(files):
            data = map_file.read_map_bytes(files["map.bin"])
            files["map.bin"] = map_heights.set_tile_corners(files["map.bin"], map_heights.deduce_corners(files, data, tiles))

        self._edit_map(edit, f"Deduced the corner heights of {len(tiles)} tile(s)" if len(tiles) > 1 else
                       f"Deduced the corner heights of tile {tiles[0]}")

    def _tiles_inspector(self, body, tiles) -> None:
        xs, ys = [t[0] for t in tiles], [t[1] for t in tiles]
        ttk.Label(body, text=f"{len(tiles)} tiles", font=("Segoe UI", 11, "bold")).pack(anchor="w")
        ttk.Label(body, text=f"({min(xs)}, {min(ys)}) to ({max(xs)}, {max(ys)})", style="Muted.TLabel").pack(anchor="w")
        ttk.Button(body, text="Deduce from terrain and props", command=lambda: self._deduce(tiles)).pack(anchor="w", pady=(10, 0))
        ttk.Label(body, text="Set every corner of these tiles", style="Muted.TLabel").pack(anchor="w", pady=(12, 2))
        row = ttk.Frame(body)
        row.pack(anchor="w")
        layer = tk.StringVar(value="All layers")
        ttk.Combobox(row, textvariable=layer, values=["All layers", *self.LAYER_TEXT.values()], state="readonly",
                     width=12).pack(side="left")
        data = self._map.map_data
        first = map_heights.tile_corners(data, tiles[0]).get("combined", (0, 0, 0, 0)) if data is not None else (0, 0, 0, 0)
        value = tk.StringVar(value=str(first[0]))
        ttk.Entry(row, textvariable=value, width=8).pack(side="left", padx=(6, 0))
        ttk.Button(row, text="Apply", command=lambda: self._flatten(tiles, layer.get(), value.get())).pack(side="left", padx=(6, 0))
        ttk.Label(body, text=self.HEIGHTS_HELP, style="Muted.TLabel", wraplength=300, justify="left").pack(anchor="w", pady=(10, 0))

    def _flatten(self, tiles, layer_text: str, text: str) -> None:
        try:
            value = int(text)
        except ValueError:
            messagebox.showerror("Tile heights", "An elevation is a whole number.", parent=self)
            return
        data = self._map.map_data
        layers = [k for k, v in self.LAYER_TEXT.items() if layer_text in ("All layers", v)]
        changes = {}
        for tile in tiles:
            present = map_heights.tile_corners(data, tile)
            changes[tile] = {layer: (value,) * 4 for layer in layers if layer in present}
        self._edit_map(lambda files: files.__setitem__("map.bin", map_heights.set_tile_corners(files["map.bin"], changes)),
                       f"Set {len(tiles)} tiles to elevation {value} ({layer_text.lower()})")

    def _unit_inspector(self, body, section_name: str, index: int) -> None:
        doc = self._doc()
        section = doc.section(section_name) if doc else None
        if section is None or index >= len(section.units):
            self._selection = None
            self._refresh_inspector()
            return
        unit = section.units[index]
        variant = self._variant()
        characters, classes, items, skills = self._choices()
        ai = self._ai_choices()
        pid = unit[F["pid"]]
        info = self._character(pid) if isinstance(pid, str) else None
        ttk.Label(body, text=info.label if info else str(pid), font=("Segoe UI", 11, "bold")).pack(anchor="w")
        ttk.Label(body, text=f"{section_name} [{index}] in {self._variant_name(variant)}", style="Muted.TLabel").pack(anchor="w")

        form = ttk.Frame(body)
        form.pack(anchor="w", fill="x", pady=(8, 0))
        row = 0

        groups: dict[str, list] = {"gauge": [], "ai": [], "ai_toggle": []}

        def add(label, widget, group=None):
            nonlocal row
            caption = ttk.Label(form, text=label)
            caption.grid(row=row, column=0, sticky="w", pady=2, padx=(0, 6))
            widget.grid(row=row, column=1, sticky="w", pady=2)
            if group:
                groups[group].append((caption, widget))
            row += 1

        def picker(field, pairs, width=30):
            p = _LabelPicker(form, width=width)
            p.set_choices(pairs)
            p.set_label(unit[F[field]])
            self._form_vars[field] = p
            return p

        def number(field, low, high, width=6):
            var = tk.StringVar(value=str(unit[F[field]]))
            self._form_vars[field] = var
            return ttk.Spinbox(form, from_=low, to=high, textvariable=var, width=width)

        add("Character", picker("pid", characters))
        add("Class", picker("jid", classes))
        faction = tk.StringVar(value=dispo.FACTION_NAMES.get(unit[F["faction"]], str(unit[F["faction"]])))
        self._form_vars["faction"] = faction
        add("Faction", ttk.Combobox(form, textvariable=faction, values=list(dispo.FACTION_NAMES.values()), width=10))
        flags = dispo_widgets.FlagChecks(form, unit[F["flags"]], dispo_rules.unit_flag_bits(unit[F["flags"]]))
        self._form_vars["flags"] = flags
        add("Flags", flags)
        position = ttk.Frame(form)
        for field in ("pos_x", "pos_y", "pos2_x", "pos2_y"):
            var = tk.StringVar(value=str(unit[F[field]]))
            self._form_vars[field] = var
        ttk.Spinbox(position, from_=-128, to=127, textvariable=self._form_vars["pos_x"], width=4).pack(side="left")
        ttk.Spinbox(position, from_=-128, to=127, textvariable=self._form_vars["pos_y"], width=4).pack(side="left", padx=(2, 0))
        ttk.Label(position, text="  moves to").pack(side="left")
        ttk.Spinbox(position, from_=-128, to=127, textvariable=self._form_vars["pos2_x"], width=4).pack(side="left", padx=(4, 0))
        ttk.Spinbox(position, from_=-128, to=127, textvariable=self._form_vars["pos2_y"], width=4).pack(side="left", padx=(2, 0))
        add("Tile", position)
        for slot in range(8):
            cell = ttk.Frame(form)
            p = _LabelPicker(cell, width=26)
            p.set_choices(items)
            p.set_label(unit[F[f"item{slot}"]])
            p.pack(anchor="w")
            self._form_vars[f"item{slot}"] = p
            item_flags = dispo_widgets.FlagChecks(cell, unit[F[f"item{slot}_flag"]], dispo.ITEM_FLAG_BITS, columns=2)
            self._form_vars[f"item{slot}_flag"] = item_flags
            item_flags.pack(anchor="w")
            add(f"Item {slot + 1}", cell)
        for slot in range(5):
            add(f"Skill {slot + 1}", picker(f"skill{slot}", skills, 26))
        ai_on = tk.BooleanVar(value=False)
        self._form_vars["ai_on"] = ai_on
        add("AI", ttk.Checkbutton(form, text="AI-controlled unit", variable=ai_on), "ai_toggle")
        for field, label, prefix in AI_FIELDS:
            add(label, picker(field, [(l, l) for l in ai.get(prefix, [])], 26), "ai")
        add("AI turn order (lower first)", number("ai_order", -128, 127, 6), "ai")
        add("Laguz gauge", number("laguz_gauge", 0, 19), "gauge")

        is_laguz = self._is_laguz()
        original_ai = (unit[F["seq_attack"]], unit[F["seq_move"]], unit[F["seq_heal"]], unit[F["ai_order"]])
        original_gauge = unit[F["laguz_gauge"]]

        def show(group, visible):
            for caption, widget in groups[group]:
                for part in (caption, widget):
                    part.grid() if visible else part.grid_remove()

        def refresh_rules(*_):
            """Show only the controls that apply to the faction and class now in the form."""
            try:
                faction_now = self._read_faction()
                laguz_now = is_laguz(self._form_vars["jid"].label(), self._form_vars["pid"].label())
            except ValueError:
                return
            default_ai = dispo_rules.show_ai(faction_now, *original_ai)
            show("ai_toggle", not default_ai)
            show("ai", default_ai or ai_on.get())
            show("gauge", dispo_rules.show_laguz_gauge(laguz_now, original_gauge))
            for slot in range(8):
                iid = self._form_vars[f"item{slot}"]
                try:
                    label = iid.label()
                except ValueError:
                    continue
                item_flags = self._form_vars[f"item{slot}_flag"]
                item_flags.set_visible(dispo.ITEM_FLAG_RING,
                                       dispo_rules.show_ring_flag(label, unit[F[f"item{slot}_flag"]]))

        for widget in (faction, ai_on):
            widget.trace_add("write", refresh_rules)
        for field in ("pid", "jid", *[f"item{i}" for i in range(8)]):
            picker_widget = self._form_vars[field]
            for sequence in ("<<ComboboxSelected>>", "<FocusOut>", "<KeyRelease>"):
                picker_widget.bind(sequence, refresh_rules, add="+")
        refresh_rules()

        ttk.Label(body, text="Section", font=("Segoe UI", 10, "bold")).pack(anchor="w", pady=(12, 2))
        header_form = dispo_widgets.SectionHeaderFrame(body, dispo.section_header(section), self._deploy.group_keys())
        header_form.pack(anchor="w")
        ttk.Button(body, text="Apply to section", command=lambda: self._apply_section(section_name, header_form)).pack(
            anchor="w", pady=(4, 0))

        ttk.Label(body, text="Difficulties", font=("Segoe UI", 10, "bold")).pack(anchor="w", pady=(12, 2))
        ttk.Label(body, text="Tick where the unit exists; level and stat bonuses are per difficulty.",
                  style="Muted.TLabel", wraplength=320, justify="left").pack(anchor="w")
        table = ttk.Frame(body)
        table.pack(anchor="w", pady=(4, 0))
        headers = ["", "Lv"] + [s.upper() if s != "hp" else "HP" for s in dispo.STAT_NAMES]
        for c, text in enumerate(headers):
            ttk.Label(table, text=text, style="Muted.TLabel").grid(row=0, column=c, padx=1)
        docs = {v: self._deploy.document(v) for v in self._deploy.variants()}
        self._variant_rows = {}
        for r, (v, other) in enumerate(docs.items(), 1):
            if v == variant:
                found = (section_name, index)
            else:
                i = dispo.find_counterpart_unit(other, section_name, unit, index)
                found = (dispo.counterpart_section(other, section_name).name, i) if i is not None else None
            source = other.section(found[0]).units[found[1]] if found else unit
            present = tk.BooleanVar(value=found is not None)
            has_section = v == variant or dispo.counterpart_section(other, section_name) is not None
            check = ttk.Checkbutton(table, text=v.removeprefix("dispos_").removesuffix(".bin"), variable=present)
            if not has_section:
                check.state(["disabled"])
            check.grid(row=r, column=0, sticky="w")
            values = {}
            for c, field in enumerate(["level"] + [f"bonus_{s}" for s in dispo.STAT_NAMES], 1):
                var = tk.StringVar(value=str(source[F[field]]))
                values[field] = var
                ttk.Spinbox(table, from_=-128 if field != "level" else 1, to=127 if field != "level" else 40,
                            textvariable=var, width=4 if field == "level" else 3).grid(row=r, column=c, padx=1)
            self._variant_rows[v] = {"present": present, "found": found, "values": values}

        buttons = ttk.Frame(body)
        buttons.pack(anchor="w", pady=(12, 0))
        ttk.Button(buttons, text="Apply", command=lambda: self._apply_unit(section_name, index)).pack(side="left")
        ttk.Button(buttons, text="Delete", command=self._delete_selection).pack(side="left", padx=(6, 0))
        ttk.Button(buttons, text="All fields...", command=lambda: self._open_raw_fields(section_name, index)).pack(
            side="left", padx=(6, 0))
        if isinstance(pid, str) and self._on_navigate_to_character is not None:
            ttk.Button(buttons, text="View Stats...", command=lambda: self._on_navigate_to_character(pid)).pack(side="left", padx=(6, 0))
        ttk.Label(body, text="Apply writes the form to this unit, and with \"Same edit on every difficulty\" to the "
                             "same unit in the other difficulties.", style="Muted.TLabel", wraplength=320,
                  justify="left").pack(anchor="w", pady=(8, 0))

    def _is_laguz(self):
        """``is_laguz(jid, pid)`` for the loaded FE8Data (cached with the choices)."""
        session = self._session_provider()
        fe8 = getattr(session, "fe8", None) if session is not None else None
        if getattr(self, "_laguz_source", None) is not fe8:
            self._laguz_source = fe8
            self._laguz_check = dispo_rules.laguz_lookup(fe8)
        return self._laguz_check

    def _read_faction(self) -> int:
        faction_text = self._form_vars["faction"].get().strip()
        faction = next((k for k, name in dispo.FACTION_NAMES.items() if name == faction_text), None)
        return faction if faction is not None else int(faction_text)

    def _read_form(self) -> dict[int, object]:
        """Field index -> value from the unit form (shared fields only)."""
        v = self._form_vars
        values: dict[int, object] = {}
        for field in ("pid", "jid", *[f"item{i}" for i in range(8)], *[f"skill{i}" for i in range(5)],
                      *[f for f, _l, _p in AI_FIELDS]):
            values[F[field]] = v[field].label()
        values[F["faction"]] = self._read_faction()
        for field in ("pos_x", "pos_y", "pos2_x", "pos2_y", "laguz_gauge"):
            values[F[field]] = int(v[field].get())
        values[F["ai_order"]] = int(v["ai_order"].get())
        for i in range(8):
            values[F[f"item{i}_flag"]] = v[f"item{i}_flag"].value()
        values[F["flags"]] = v["flags"].value()
        if not isinstance(values[F["pid"]], str):
            raise ValueError("Choose a character.")
        return values

    def _apply_unit(self, section_name: str, index: int) -> None:
        try:
            shared = self._read_form()
            rows = {v: {field: int(var.get()) for field, var in row["values"].items()} for v, row in self._variant_rows.items()}
        except ValueError as exc:
            messagebox.showerror("Unit", str(exc), parent=self)
            return
        current = self._variant()
        all_variants = self._all_variants.get()
        presence = {v: (row["present"].get(), row["found"]) for v, row in self._variant_rows.items()}
        base_unit = list(self._deploy.document(current).section(section_name).units[index])
        if (shared[F["faction"]] == dispo_rules.PLAYER_FACTION and base_unit[F["faction"]] != dispo_rules.PLAYER_FACTION
                and not self._form_vars["ai_on"].get()):
            # Moved onto the player army without asking for AI: give it the inert AI vanilla player units carry.
            for field, label in dispo_rules.INERT_AI.items():
                shared[F[field]] = label
            shared[F["ai_order"]] = 0
        problems = dispo_rules.warnings(
            shared[F["faction"]], self._is_laguz()(shared[F["jid"]], shared[F["pid"]]), shared[F["laguz_gauge"]],
            [(shared[F[f"item{i}"]], shared[F[f"item{i}_flag"]]) for i in range(8)])
        if problems and not messagebox.askokcancel(
                "Unit", "\n".join(problems) + "\n\nApply anyway?", parent=self):
            return
        new_selection = {}

        def write(unit, per_variant):
            for f, value in shared.items():
                unit[f] = value
            for field, value in per_variant.items():
                unit[F[field]] = value

        def edit(docs):
            removals = []
            for v, (present, found) in presence.items():
                doc = docs[v]
                if present and found is not None:
                    unit = doc.section(found[0]).units[found[1]]
                    if v == current or all_variants:
                        write(unit, rows[v])
                    else:
                        for field, value in rows[v].items():
                            unit[F[field]] = value
                elif present:
                    target = dispo.counterpart_section(doc, section_name)
                    if target is not None:
                        unit = list(base_unit)
                        write(unit, rows[v])
                        dispo.add_unit(doc, target.name, unit)
                elif found is not None:
                    removals.append((v, found))
            for v, (sec, i) in removals:
                dispo.remove_unit(docs[v], sec, i)
            new_selection["keep"] = presence[current][0]

        pid = shared[F["pid"]]
        if self._edit_units(edit, f"Edited {pid} ({section_name}[{index}])") and not new_selection.get("keep", True):
            self._select(None)

    def _open_raw_fields(self, section_name: str, index: int) -> None:
        variant = self._variant()
        if variant is not None:
            _RawFieldsDialog(self, variant, section_name, index)

    def edit_raw_field(self, variant: str, section_name: str, index: int, field: int, value) -> bool:
        """Set one field of one unit, in this deployment file only (All fields...)."""
        def edit(docs):
            docs[variant].section(section_name).units[index][field] = value

        name = dispo.field_name(field) or f"field {field}"
        return self._edit_units(edit, f"{variant} {section_name}[{index}]: {name} = {value}")

    def label_choices(self) -> dict[str, list[str]]:
        """Every label the chapter's deployment files use, by prefix."""
        return dispo.labels_by_prefix([self._deploy.document(v) for v in self._deploy.variants()])

    def navigate_to_character(self, pid: str) -> None:
        if self._on_navigate_to_character is not None:
            self._on_navigate_to_character(pid)

    def raw_unit(self, variant: str | None, section_name: str, index: int) -> list | None:
        doc = self._deploy.document(variant) if variant else None
        section = doc.section(section_name) if doc else None
        return section.units[index] if section is not None and 0 <= index < len(section.units) else None

    def select_unit(self, difficulty: str, section_name: str, index: int) -> None:
        """Show one unit (deep links): difficulty letter (n/h/m/c) of its
        deployment file, its section and its index there."""
        variant = f"dispos_{difficulty}.bin"
        if variant not in self._deploy.variants():
            return
        if self._variant() != variant:
            self._variant_var.set(self._variant_name(variant))
            self._variant_changed()
        if self.raw_unit(variant, section_name, index) is None:
            return
        if self._filter_var.get() not in ("All sections", section_name):
            self._filter_var.set("All sections")
        self._select(("unit", section_name, index))
        self._see_unit(section_name, index)

    def _apply_section(self, section_name: str, form) -> None:
        """Write the section header form to this section and, with "Same
        edit on every difficulty", to the same section in the other files."""
        try:
            header = form.header()
        except ValueError as exc:
            messagebox.showerror("Section", str(exc), parent=self)
            return
        self.apply_section_header(self._variant(), section_name, header)

    def apply_section_header(self, variant: str, section_name: str, header: dispo.SectionHeader) -> bool:
        """Write ``header`` to a section of ``variant`` and, with "Same edit
        on every difficulty", to the same section in the other files."""
        all_variants = self._all_variants.get()

        def edit(docs):
            for v, doc in docs.items():
                if v != variant and not all_variants:
                    continue
                target = doc.section(section_name) if v == variant else dispo.counterpart_section(doc, section_name)
                if target is not None and not target.is_link:
                    dispo.set_section_header(target, header)

        return self._edit_units(edit, f"Section {section_name}: army {header.group}, occupied tiles {header.occupied_ok}")

    # -- the Disposition window ------------------------------------------------------------
    def variants(self) -> list[str]:
        """The chapter's deployment files, in the Deployment file picker's order."""
        order = "cnhm"
        return sorted(self._deploy.variants(), key=lambda v: order.find(v.removeprefix("dispos_")[:1]))

    def variant_name(self, variant: str) -> str:
        return self._variant_name(variant)

    def current_variant(self) -> str | None:
        return self._variant()

    def set_variant(self, variant: str) -> None:
        """Show ``variant`` on the canvas (the Deployment file picker)."""
        if variant in self._deploy.variants() and variant != self._variant():
            self._variant_var.set(self._variant_name(variant))
            self._variant_changed()

    def document(self, variant: str | None) -> dispo.DispoDocument | None:
        return self._deploy.document(variant) if variant else None

    def group_keys(self) -> list:
        return self._deploy.group_keys()

    @property
    def all_variants_var(self) -> tk.BooleanVar:
        """The "Same edit on every difficulty" checkbox's variable."""
        return self._all_variants

    def selected_unit(self) -> tuple[str, str, int] | None:
        """(variant, section, index) of the unit selected on the canvas."""
        if self._selection and self._selection[0] == "unit" and self._variant():
            return self._variant(), self._selection[1], self._selection[2]
        return None

    def show_unit(self, variant: str, section_name: str, index: int | None) -> None:
        """Select (and scroll to) a unit on the canvas, switching the shown
        file to ``variant``; ``index`` None clears a unit selection."""
        self.set_variant(variant)
        if index is None:
            if self._selection and self._selection[0] == "unit":
                self._select(None)
            return
        if self.raw_unit(variant, section_name, index) is None or self._selection == ("unit", section_name, index):
            return
        if self._filter_var.get() not in ("All sections", section_name):
            self._filter_var.set("All sections")
        self._select(("unit", section_name, index))
        self._see_unit(section_name, index)

    def highlight_section(self, variant: str | None, section_name: str | None) -> None:
        """Outline every unit of a section on the canvas and dim the others
        (None clears it). A section filter hiding the section is lifted."""
        target = (variant, section_name) if variant and section_name else None
        if target == self._highlight:
            return
        self._highlight = target
        if target is not None and self._filter_var.get() not in ("All sections", section_name):
            self._filter_var.set("All sections")
        self._refresh_canvas()

    def see_section(self, variant: str, section_name: str) -> None:
        """Scroll the canvas to the middle of a section's units."""
        doc = self._deploy.document(variant)
        section = doc.section(section_name) if doc else None
        if not section or not section.units:
            return
        self.set_variant(variant)
        xs = [int(u[F["pos_x"]]) for u in section.units]
        ys = [int(u[F["pos_y"]]) for u in section.units]
        self.after_idle(lambda: self._canvas.see_tile((min(xs) + max(xs)) // 2, (min(ys) + max(ys)) // 2))

    def unit_choices(self):
        """(characters, classes, items, skills) as (display, label) pairs, and
        the SEQ_/MTYPE_ labels by prefix."""
        return self._choices(), self._ai_choices()

    def character_name(self, pid) -> str:
        if not isinstance(pid, str):
            return "" if not pid else str(pid)
        info = self._character(pid)
        return info.name if info is not None and info.name else pid

    def edit_unit_fields(self, variant: str, section_name: str, index: int, values: dict) -> bool:
        """Set fields (index -> value) of one unit of ``variant``. With "Same
        edit on every difficulty" the shared ones follow in the same unit of
        the other files; level and stat bonuses stay per file."""
        all_variants = self._all_variants.get()

        def edit(docs):
            for v, sec, i in self._unit_targets(docs, section_name, index, all_variants, variant):
                unit = docs[v].section(sec).units[i]
                for field, value in values.items():
                    if v == variant or field not in PER_VARIANT_FIELDS:
                        unit[field] = value

        text = ", ".join(f"{dispo.field_name(f) or f'field {f}'} = {value}" for f, value in values.items())
        return self._edit_units(edit, f"{section_name}[{index}]: {text}")

    def delete_unit(self, variant: str, section_name: str, index: int) -> bool:
        all_variants = self._all_variants.get()

        def edit(docs):
            for v, sec, i in self._unit_targets(docs, section_name, index, all_variants, variant):
                dispo.remove_unit(docs[v], sec, i)

        if self._selection and self._selection[0] == "unit":
            self._selection = None
        return self._edit_units(edit, f"Deleted unit {section_name}[{index}]")

    def open_raw_fields(self, variant: str, section_name: str, index: int) -> None:
        _RawFieldsDialog(self, variant, section_name, index)

    def section_loaders(self, section_name: str) -> tuple[list, Optional[str]]:
        """(references, problem): the calls of the chapter script that name
        ``section_name`` - or its name without the difficulty letter, the
        prefix the ...Rank deployment calls take - as
        ``source_tools.StringReference``s; problem says why there are none
        to show."""
        from ..formats.cmb import source_tools
        from .. import script_sources

        if self._script is None or not self._script.has_chapter_script:
            return [], "This chapter has no script."
        source = self._script.chapter_source()
        if source is None:  # the Script tab shows another file: read the chapter's from disk
            path = self._script.chapter_path
            try:
                key = (path, path.stat().st_mtime_ns)
                if getattr(self, "_disk_script", (None,))[0] != key:
                    self._disk_script = (key, script_sources.load(self._project, path).source)
                source = self._disk_script[1]
            except Exception as exc:  # noqa: BLE001
                return [], f"Could not read the chapter script: {exc}"
        if getattr(self, "_refs_key", (None,))[0] != source:
            try:
                self._refs_key = (source, source_tools.string_references(source), None)
            except ParseError as exc:
                self._refs_key = (source, [], f"The chapter script doesn't parse (line {exc.line}: {exc.message}).")
        _source, refs, problem = self._refs_key
        base = dispo.section_base(section_name)
        return [r for r in refs if r.value == section_name or (base != section_name and r.value == base)], problem

    def open_function(self, name: str) -> None:
        """Show a function of the chapter script in the Script tab."""
        if self._on_open_function is not None:
            self._on_open_function(name)

    # -- workspace --------------------------------------------------------------------------
    def refresh_chapter_list(self) -> None:
        pass


class _AddSectionDialog(tk.Toplevel):
    """Name and header of a new, empty section; ``result`` is (name, header)
    once OK is pressed."""

    def __init__(self, builder: MapBuilder, group_keys) -> None:
        super().__init__(builder)
        self.title("Add section")
        self.result = None
        frame = ttk.Frame(self, padding=10)
        frame.pack(fill="both", expand=True)
        ttk.Label(frame, text="Name").pack(anchor="w")
        self._name_var = tk.StringVar()
        entry = ttk.Entry(frame, textvariable=self._name_var, width=36)
        entry.pack(anchor="w", fill="x")
        ttk.Label(frame, text="Scripts deploy a section by this name. With \"Same edit on every difficulty\", "
                              "a name ending in the file's difficulty letter (_n, _h, _m) adds the section "
                              "to the other difficulties too, with their letter.",
                  style="Muted.TLabel", wraplength=340, justify="left").pack(anchor="w", pady=(2, 8))
        self._header = dispo_widgets.SectionHeaderFrame(frame, dispo.SectionHeader(4, 0, 0), group_keys)
        self._header.pack(anchor="w")
        buttons = ttk.Frame(frame)
        buttons.pack(anchor="e", pady=(10, 0))
        ttk.Button(buttons, text="OK", command=self._ok).pack(side="left")
        ttk.Button(buttons, text="Cancel", command=self.destroy).pack(side="left", padx=(6, 0))
        self.bind("<Return>", lambda e: self._ok())
        self.bind("<Escape>", lambda e: self.destroy())
        self.transient(builder.winfo_toplevel())
        self.grab_set()
        entry.focus_set()

    def _ok(self) -> None:
        name = self._name_var.get().strip()
        try:
            header = self._header.header()
            if not name:
                raise ValueError("Give the section a name.")
        except ValueError as exc:
            messagebox.showerror("Add section", str(exc), parent=self)
            return
        self.result = (name, header)
        self.destroy()


class _RawFieldsDialog(tk.Toplevel):
    """Every field of one unit, as the file stores it (unread ones included);
    double-click one to edit it. Edits touch this deployment file only."""

    def __init__(self, builder: MapBuilder, variant: str, section_name: str, index: int) -> None:
        super().__init__(builder)
        self.title(f"{section_name} [{index}] - {variant}")
        self._builder, self._key = builder, (variant, section_name, index)
        frame = ttk.Frame(self, padding=10)
        frame.pack(fill="both", expand=True)
        ttk.Label(frame, text="Double-click a field to edit it. Changes apply to this deployment file only.",
                  style="Muted.TLabel").pack(anchor="w", pady=(0, 6))
        self._tree = ttk.Treeview(frame, columns=("index", "value"), show="headings", height=22)
        self._tree.heading("index", text="#")
        self._tree.heading("value", text="Value")
        self._tree.column("index", width=160, stretch=False)
        self._tree.column("value", width=320)
        self._tree.pack(fill="both", expand=True)
        self._tree.bind("<Double-Button-1>", lambda e: self._edit())
        ttk.Button(frame, text="Close", command=self.destroy).pack(anchor="e", pady=(8, 0))
        self._fill()
        self.transient(builder.winfo_toplevel())
        self.grab_set()

    def _fill(self) -> None:
        self._tree.delete(*self._tree.get_children())
        unit = self._builder.raw_unit(*self._key)
        for i, value in enumerate(unit or ()):
            name = dispo.field_name(i)
            self._tree.insert("", "end", iid=str(i), values=(f"{i} ({name})" if name else f"{i} (unread)",
                                                              dispo.describe_field(i, value)))

    def _navigate(self, pid: str) -> None:
        self.destroy()
        self._builder.navigate_to_character(pid)

    def _edit(self) -> None:
        from .deployment_editor import _FieldEditDialog

        unit = self._builder.raw_unit(*self._key)
        selection = self._tree.selection()
        if unit is None or not selection:
            return
        field = int(selection[0])
        dialog = _FieldEditDialog(self, field, unit[field], self._builder.label_choices(),
                                  on_navigate_to_character=self._navigate)
        self.wait_window(dialog)
        if dialog.result is None or dialog.result == unit[field]:
            return
        if self._builder.edit_raw_field(*self._key, field, dialog.result):
            self._fill()
            self._tree.selection_set(str(field))
            self._tree.see(str(field))
