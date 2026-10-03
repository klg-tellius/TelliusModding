"""Every map's props in one list, with a 3D preview of the selected one.

Shared by the Game Data page's **Map Objects** tab (browse, export) and the
Build tab's **Add from another map...** dialog (pick a prop to copy into the
open chapter map). The catalog is ``map_props.prop_catalog()``, read on a
worker thread the first time the browser is shown (each ``map.cmp`` is
decompressed once and cached until it changes on disk). It reflects the
saved maps: unsaved edits of an open chapter don't show until saved."""

from __future__ import annotations

import queue
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import Callable, Optional

from .. import chapters, map_props
from ..formats import map_file
from . import map_scene
from .editor_panel import EditorPanel
from .model_viewer import _ModelPreview, load_named_model_set

ALL_MAPS = "All maps"
COLUMNS = (("map", "Map", 150), ("name", "Object", 190), ("placed", "Placed", 60), ("tiles", "Tiles", 60),
           ("height", "Height", 60), ("kind", "Kind", 110))


def _kind(info: map_props.PropInfo) -> str:
    obj = info.obj
    if (obj.flag_bits_b >> 2) & 7:
        return "Goal marker"
    if obj.effect_type:
        return "Animated, effect" if info.animated else "Effect"
    return "Animated" if info.animated else "Static"


class PropBrowser(ttk.Frame):
    """Search box, map filter, the props table and a 3D preview.
    ``on_activate(info)`` runs on a double-click; ``exclude`` leaves one
    map (the one being edited) out of the list."""

    def __init__(self, parent: tk.Misc, project, exclude: Optional[Path] = None,
                 on_activate: Optional[Callable[[map_props.PropInfo], None]] = None,
                 on_select: Optional[Callable[[Optional[map_props.PropInfo]], None]] = None) -> None:
        super().__init__(parent)
        self._project = project
        self._exclude = Path(exclude) if exclude is not None else None
        self._on_activate = on_activate
        self._on_select = on_select
        self._props: list[map_props.PropInfo] = []
        self._rows: dict[str, map_props.PropInfo] = {}
        self._sort = ("map", False)
        self._scanning = False
        self._loaded_path: Optional[Path] = None
        self._loaded_files: dict[str, bytes] = {}
        self._titles: dict[str, str] | None = None
        self._build_widgets()
        self.bind("<Map>", lambda e: self._first_show(), add="+")

    # -- layout ------------------------------------------------------------------------
    def _build_widgets(self) -> None:
        bar = ttk.Frame(self, padding=(0, 0, 0, 6))
        bar.pack(fill="x")
        ttk.Label(bar, text="Search").pack(side="left")
        self._search = tk.StringVar()
        self._search.trace_add("write", lambda *_: self._fill())
        ttk.Entry(bar, textvariable=self._search, width=24).pack(side="left", padx=(6, 12))
        ttk.Label(bar, text="Map").pack(side="left")
        self._map_var = tk.StringVar(value=ALL_MAPS)
        self._map_combo = ttk.Combobox(bar, textvariable=self._map_var, state="readonly", width=40, values=[ALL_MAPS])
        self._map_combo.pack(side="left", padx=(6, 12))
        self._map_combo.bind("<<ComboboxSelected>>", lambda e: self._fill())
        self._unique = tk.BooleanVar(value=False)
        ttk.Checkbutton(bar, text="One row per name", variable=self._unique, command=self._fill).pack(side="left")
        ttk.Button(bar, text="Rescan", command=self.scan).pack(side="right")
        self._status = ttk.Label(bar, text="", style="Muted.TLabel")
        self._status.pack(side="right", padx=(0, 10))

        self._paned = paned = ttk.PanedWindow(self, orient="horizontal")
        paned.pack(fill="both", expand=True)
        left = ttk.Frame(paned)
        paned.add(left, weight=1)
        self._tree = ttk.Treeview(left, columns=[c[0] for c in COLUMNS], show="headings", selectmode="browse")
        for key, title, width in COLUMNS:
            self._tree.heading(key, text=title, command=lambda k=key: self._sort_by(k))
            self._tree.column(key, width=width, stretch=key == "name",
                              anchor="w" if key in ("map", "name", "kind") else "e")
        ybar = ttk.Scrollbar(left, orient="vertical", command=self._tree.yview)
        self._tree.configure(yscrollcommand=ybar.set)
        ybar.pack(side="right", fill="y")
        self._tree.pack(side="left", fill="both", expand=True)
        self._tree.bind("<<TreeviewSelect>>", lambda e: self._selected_changed())
        self._tree.bind("<Double-1>", lambda e: self._activate())

        right = ttk.Frame(paned)
        paned.add(right, weight=1)
        self._preview = _ModelPreview(right)
        self._preview.pack(fill="both", expand=True)
        self._preview.show(None, "Select a prop to preview it.")

    # -- catalog -----------------------------------------------------------------------
    def _first_show(self) -> None:
        if not self._props and not self._scanning:
            self.after_idle(lambda: self._paned.sashpos(0, sum(c[2] for c in COLUMNS) + 24))
            self.scan()

    def scan(self) -> None:
        if self._scanning:
            return
        self._scanning = True
        self._status.configure(text="Reading maps...")
        results: "queue.Queue" = queue.Queue()
        extracted = self._project.extracted_dir

        def worker() -> None:
            try:
                props = map_props.prop_catalog(extracted, progress=lambda done, total: results.put(("progress", done, total)))
                results.put(("done", props))
            except Exception as exc:  # noqa: BLE001
                results.put(("error", exc))

        threading.Thread(target=worker, daemon=True).start()
        self.after(100, lambda: self._poll(results))

    def _poll(self, results: "queue.Queue") -> None:
        if not self.winfo_exists():
            return
        while True:
            try:
                message = results.get_nowait()
            except queue.Empty:
                self.after(100, lambda: self._poll(results))
                return
            if message[0] == "progress":
                self._status.configure(text=f"Reading maps... {message[1]}/{message[2]}")
                continue
            self._scanning = False
            if message[0] == "error":
                self._status.configure(text=f"Could not read the maps: {message[1]}")
                return
            self._set_props(message[1])
            return

    def _map_label(self, map_name: str) -> str:
        if self._titles is None:
            self._titles = chapters.chapter_titles(self._project)
        chapter = chapters.chapter_of_map_folder(map_name)
        return f"{map_name} · {chapters.chapter_display_title(chapter, self._titles)}" if chapter else map_name

    def _set_props(self, props: list[map_props.PropInfo]) -> None:
        self._props = [p for p in props if self._exclude is None or p.path != self._exclude]
        maps = list(dict.fromkeys(p.map_name for p in self._props))
        self._map_labels = {self._map_label(m): m for m in maps}
        self._map_combo.configure(values=[ALL_MAPS, *self._map_labels])
        if self._map_var.get() not in self._map_labels:
            self._map_var.set(ALL_MAPS)
        self._fill()

    def _visible(self) -> list[map_props.PropInfo]:
        text = self._search.get().strip().lower()
        wanted = self._map_labels.get(self._map_var.get()) if self._map_var.get() != ALL_MAPS else None
        props = [p for p in self._props if (wanted is None or p.map_name == wanted) and (not text or text in p.name.lower())]
        if self._unique.get():
            props = list({p.name: p for p in reversed(props)}.values())[::-1]
        key, reverse = self._sort
        getters = {
            "map": lambda p: (p.map_name, p.name), "name": lambda p: (p.name, p.map_name),
            "placed": lambda p: p.instances, "tiles": lambda p: p.footprint[0] * p.footprint[1],
            "height": lambda p: p.obj.size_y - p.obj.offset_y, "kind": _kind,
        }
        return sorted(props, key=getters[key], reverse=reverse)

    def _fill(self) -> None:
        if not hasattr(self, "_map_labels"):
            return
        previous = self.selected()
        self._tree.delete(*self._tree.get_children())
        self._rows = {}
        visible = self._visible()
        for info in visible:
            w, d = info.footprint
            row = self._tree.insert("", "end", values=(
                info.map_name, info.name, info.instances, f"{w}×{d}", f"{(info.obj.size_y - info.obj.offset_y) / 5:.1f}",
                _kind(info)))
            self._rows[row] = info
            if previous is not None and (info.path, info.name) == (previous.path, previous.name):
                self._tree.selection_set(row)
                self._tree.see(row)
        maps = len({p.map_name for p in self._props})
        self._status.configure(text=f"{len(visible)} of {len(self._props)} props, {maps} maps")

    def _sort_by(self, key: str) -> None:
        self._sort = (key, not self._sort[1] if self._sort[0] == key else key in ("placed", "tiles", "height"))
        self._fill()

    # -- selection ---------------------------------------------------------------------
    def selected(self) -> Optional[map_props.PropInfo]:
        selection = self._tree.selection()
        return self._rows.get(selection[0]) if selection else None

    def files_of(self, info: map_props.PropInfo) -> dict[str, bytes]:
        """The unpacked ``map.cmp`` holding ``info`` (the last one is kept)."""
        if info.path != self._loaded_path:
            _entries, self._loaded_files = map_props.read_map_container(info.path)
            self._loaded_path = info.path
        return self._loaded_files

    def _selected_changed(self) -> None:
        info = self.selected()
        if self._on_select is not None:
            self._on_select(info)
        if info is None:
            self._preview.show(None, "Select a prop to preview it.")
            return
        try:
            files = self.files_of(info)
            data = map_file.read_map_bytes(files["map.bin"])
            loaded = load_named_model_set(files, info.name, label=f"{info.map_name}/{info.name}",
                                          map_projection=map_scene.compute_map_texture_projection(info.name, data))
        except Exception as exc:  # noqa: BLE001
            self._preview.show(None, f"Could not load {info.name}: {exc}")
            return
        self._preview.show(loaded, "No model data.")

    def _activate(self) -> None:
        info = self.selected()
        if info is not None and self._on_activate is not None:
            self._on_activate(info)

    def export_selected(self) -> None:
        info = self.selected()
        if info is None:
            return
        target = filedialog.asksaveasfilename(title="Export prop", defaultextension=".glb", initialfile=f"{info.name}.glb",
                                              filetypes=[("glTF binary", "*.glb")], parent=self)
        if not target:
            return
        try:
            Path(target).write_bytes(map_props.export_prop_glb(self.files_of(info), info.name))
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror("Could not export", str(exc), parent=self)

    def cleanup(self) -> None:
        self._preview.cleanup()


class MapObjectsPanel(EditorPanel):
    """Assets › Map Objects: every map's props, read only."""

    def __init__(self, parent: tk.Misc, project, changelog=None) -> None:
        super().__init__(parent, style="Page.TFrame", padding=(12, 10))
        top = ttk.Frame(self, style="Page.TFrame")
        top.pack(fill="x", pady=(0, 6))
        self._export = ttk.Button(top, text="Export .glb...", state="disabled", command=lambda: self.browser.export_selected())
        self._export.pack(side="left")
        ttk.Label(top, text="Every prop of every chapter map. To use one on another map, open that chapter's Build tab, "
                            "choose Place prop and Add from another map...", style="Muted.TLabel").pack(side="left", padx=(10, 0))
        self.browser = PropBrowser(self, project, on_select=lambda info: self._export.configure(
            state="normal" if info is not None else "disabled"))
        self.browser.pack(fill="both", expand=True)

    def cleanup(self) -> None:
        self.browser.cleanup()


class PropPickerDialog(tk.Toplevel):
    """Pick a prop of another map. ``result`` is ``(info, files)`` (the
    source map's unpacked ``map.cmp``) or None."""

    def __init__(self, parent: tk.Misc, project, exclude: Optional[Path]) -> None:
        super().__init__(parent)
        self.title("Add a prop from another map")
        self.geometry("1400x800")
        self.transient(parent.winfo_toplevel())
        self.result = None
        buttons = ttk.Frame(self, padding=8)
        buttons.pack(side="bottom", fill="x")
        ttk.Button(buttons, text="Cancel", command=self._close).pack(side="right")
        self._ok = ttk.Button(buttons, text="Add to this map", state="disabled", command=self._accept)
        self._ok.pack(side="right", padx=(0, 6))
        ttk.Label(buttons, text="The prop's model, animation and textures are copied into this map. "
                                "Its flags and effect come with it.", style="Muted.TLabel").pack(side="left")
        self._browser = PropBrowser(self, project, exclude=exclude, on_activate=lambda info: self._accept(),
                                    on_select=lambda info: self._ok.configure(state="normal" if info else "disabled"))
        self._browser.pack(fill="both", expand=True, padx=8, pady=(8, 0))
        self.protocol("WM_DELETE_WINDOW", self._close)
        self.grab_set()

    def _accept(self) -> None:
        info = self._browser.selected()
        if info is None:
            return
        try:
            files = self._browser.files_of(info)
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror("Could not read map", str(exc), parent=self)
            return
        self.result = (info, files)
        self._close()

    def _close(self) -> None:
        self._browser.cleanup()
        self.destroy()
