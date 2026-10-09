"""Battle scenes of one chapter map: its row of ``BattleTerrData`` in
``FE8Data.bin`` (see :func:`fe8data.read_battle_terrain`), edited on the
chapter page's **Battle scenes** tab.

A row names, for each of the 77 terrain types, the battle scenery drawn
behind a fight on a tile of that type (``zbg/<name>/``). The game finds the
row by the current map's name (the ``zmap`` folder, so each phase of a
chapter has its own) and takes row 0's entry for an empty cell; a map
without a row uses row 0 entirely. :class:`BattleScenePanel` shows the
phase's row (or the default one it falls back to), can give the map its own
row or drop it, and edits the default row on request. By default it lists
only the terrain types found on the map, with their tile counts.

Each cell has **Browse…**, which opens :class:`BattleSceneBrowser`: every
battle scene (the ``zbg/`` folders, plus names the table uses that have no
folder), filterable, and rendered in a 3D preview (``model_viewer``'s
``_ModelPreview``) as it is selected, so the right one can be picked by
looking at it.

Edits go to the shared :class:`~.fe8_session.Fe8DataSession` like every
other ``FE8Data.bin`` edit; **Save FE8Data.bin** writes them.
"""

from __future__ import annotations

import struct
import tkinter as tk
from collections import Counter
from pathlib import Path
from tkinter import messagebox, ttk
from typing import Callable, Optional

from ..formats import fe8data
from ..project import ModProject
from .changelog import ChangeLog
from .widgets import ScrollFrame, section_header

#: How many decoded scenes the browser keeps, so stepping back and forth is instant.
PREVIEW_CACHE_SIZE = 6
#: Delay before the browser renders a selection (arrow keys scroll past scenes without decoding each).
PREVIEW_DELAY_MS = 200


def scene_models(project: ModProject) -> dict[str, Path]:
    """Battle-scene name (the ``zbg/`` folder) -> its pack, the first ``.cmp`` in the folder."""
    zbg = project.extracted_dir / "files" / "zbg"
    found: dict[str, Path] = {}
    if zbg.is_dir():
        for folder in sorted(p for p in zbg.iterdir() if p.is_dir()):
            pack = next(iter(sorted(folder.glob("*.cmp"))), None)
            if pack is not None:
                found[folder.name] = pack
    return found


def find_scene(models: dict[str, Path], name: Optional[str]) -> Optional[Path]:
    """The pack of scene ``name``, matched as written, else ignoring case."""
    if not name:
        return None
    if name in models:
        return models[name]
    folded = name.casefold()
    return next((path for key, path in models.items() if key.casefold() == folded), None)


def scene_names(models: dict[str, Path], rows: list[fe8data.BattleTerrainRow]) -> list[str]:
    """Every scene there is to pick: the ``zbg/`` folders and the names the table already uses."""
    names = {name.casefold(): name for name in models}
    for row in rows:
        for scene in row.scenes:
            if scene and scene.casefold() not in names:
                names[scene.casefold()] = scene
    return sorted(names.values(), key=str.casefold)


def scene_users(rows: list[fe8data.BattleTerrainRow]) -> dict[str, list[str]]:
    """Scene name (case-folded) -> the rows naming it (their map names, row 0 marked as the default)."""
    users: dict[str, list[str]] = {}
    for i, row in enumerate(rows):
        label = f"{row.map_name or '?'} (default)" if i == 0 else row.map_name or "?"
        for scene in {s.casefold() for s in row.scenes if s}:
            users.setdefault(scene, []).append(label)
    return users


def find_row(rows: list[fe8data.BattleTerrainRow], map_name: str) -> Optional[int]:
    """The row of map ``map_name`` (row 0 counts when it names that map), or None."""
    for i, row in enumerate(rows):
        if row.map_name == map_name:
            return i
    return None


class BattleSceneBrowser(tk.Toplevel):
    """Every battle scene in a list; selecting one renders it. ``result`` is
    the chosen name after **Use this scene**, ``""`` after the
    ``clear_label`` button (the cell falls back to the default row), None
    when closed without a choice. With ``choose=False`` it only shows them."""

    def __init__(self, parent: tk.Misc, project: ModProject, names: list[str], current: Optional[str] = None,
                 users: Optional[dict[str, list[str]]] = None, title: str = "Battle scenes",
                 clear_label: Optional[str] = None, choose: bool = True):
        super().__init__(parent)
        from .model_viewer import _ModelPreview  # heavy (numpy, the renderer): loaded when first browsed

        self.title(title)
        self.geometry("1200x720")
        self.transient(parent.winfo_toplevel())
        self.result: Optional[str] = None
        self._project = project
        self._models = scene_models(project)
        self._names = names
        self._users = users or {}
        self._shown: list[str] = []
        self._cache: dict[str, object] = {}
        self._pending: Optional[str] = None
        self._rendered: Optional[str] = None
        self._choose = choose

        buttons = ttk.Frame(self, padding=(8, 0, 8, 8))
        buttons.pack(side="bottom", fill="x")
        self._use_button = ttk.Button(buttons, text="Use this scene", style="Accent.TButton", command=self._use,
                                      state="disabled")
        if choose:
            self._use_button.pack(side="right")
        ttk.Button(buttons, text="Cancel" if choose else "Close", command=self._close).pack(
            side="right", padx=(0, 6))
        if clear_label:
            ttk.Button(buttons, text=clear_label, command=self._clear).pack(side="left")

        paned = ttk.PanedWindow(self, orient="horizontal")
        paned.pack(fill="both", expand=True, padx=8, pady=8)
        left = ttk.Frame(paned, padding=(0, 0, 8, 0))
        paned.add(left, weight=1)
        top = ttk.Frame(left)
        top.pack(fill="x")
        ttk.Label(top, text="Filter", style="Muted.TLabel").pack(side="left")
        self._query = tk.StringVar()
        search = ttk.Entry(top, textvariable=self._query, width=24)
        search.pack(side="left", fill="x", expand=True, padx=(6, 0))
        self._query.trace_add("write", lambda *_: self._fill())
        box = ttk.Frame(left)
        box.pack(fill="both", expand=True, pady=(6, 0))
        self._list = tk.Listbox(box, exportselection=False, activestyle="none", width=30)
        scroll = ttk.Scrollbar(box, orient="vertical", command=self._list.yview)
        self._list.configure(yscrollcommand=scroll.set)
        scroll.pack(side="right", fill="y")
        self._list.pack(side="left", fill="both", expand=True)
        self._list.bind("<<ListboxSelect>>", lambda e: self._on_select())
        self._list.bind("<Double-Button-1>", lambda e: self._use())
        self._list.bind("<Return>", lambda e: self._use())
        search.bind("<Down>", lambda e: (self._list.focus_set(), self._step(1)))
        search.bind("<Return>", lambda e: self._use())
        self._info = ttk.Label(left, text="", style="Muted.TLabel", wraplength=260, justify="left")
        self._info.pack(fill="x", pady=(6, 0))
        ttk.Label(left, style="Faint.TLabel", wraplength=260, justify="left",
                  text="Arrow keys step through the scenes" + (
                      "; Enter or a double-click uses the selected one." if choose else ".")).pack(
            fill="x", pady=(6, 0))

        self._preview = _ModelPreview(paned)
        paned.add(self._preview, weight=4)

        self.protocol("WM_DELETE_WINDOW", self._close)
        self.bind("<Escape>", lambda e: self._close())
        self._fill()
        self._select_name(current)
        search.focus_set()

    # -- the list -------------------------------------------------------------------------
    def _label(self, name: str) -> str:
        return name if find_scene(self._models, name) is not None else f"{name}  (no zbg folder)"

    def _fill(self) -> None:
        selected = self._selected()
        words = self._query.get().casefold().split()
        self._shown = [n for n in self._names if all(w in n.casefold() for w in words)]
        self._list.delete(0, "end")
        for name in self._shown:
            self._list.insert("end", self._label(name))
        if selected in self._shown:
            self._select_name(selected)
        elif not self._shown:
            self._use_button.configure(state="disabled")

    def _selected(self) -> Optional[str]:
        picked = self._list.curselection()
        return self._shown[picked[0]] if picked and picked[0] < len(self._shown) else None

    def _select_name(self, name: Optional[str]) -> None:
        if not name:
            return
        folded = name.casefold()
        for i, shown in enumerate(self._shown):
            if shown.casefold() == folded:
                self._list.selection_clear(0, "end")
                self._list.selection_set(i)
                self._list.activate(i)
                self._list.see(i)
                self._on_select()
                return

    def _step(self, step: int) -> str:
        current = self._list.curselection()
        index = min(max((current[0] + step) if current else 0, 0), len(self._shown) - 1)
        if index >= 0:
            self._select_name(self._shown[index])
        return "break"

    def _on_select(self) -> None:
        name = self._selected()
        self._use_button.configure(state="normal" if name else "disabled")
        if name is None:
            return
        users = self._users.get(name.casefold(), [])
        pack = find_scene(self._models, name)
        where = f"zbg/{pack.parent.name}/{pack.name}" if pack is not None else "no zbg folder of that name"
        self._info.configure(text=f"{name}\n{where}\n" + (
            f"Used by: {', '.join(users)}" if users else "Not used by any map yet"))
        if self._pending is None:
            self.after(PREVIEW_DELAY_MS, self._render_pending)
        self._pending = name

    # -- the preview ----------------------------------------------------------------------
    def _render_pending(self) -> None:
        name, self._pending = self._pending, None
        if name is None or name == self._rendered or not self.winfo_exists():
            return
        self._rendered = name
        pack = find_scene(self._models, name)
        if pack is None:
            self._preview.show(None, f"{name}: no zbg/{name}/ folder in this project, so nothing to show.")
            return
        loaded = self._cache.get(name)
        if loaded is None:
            from .model_viewer import _load_model_set

            self.configure(cursor="watch")
            self.update_idletasks()
            try:
                loaded = _load_model_set(f"zbg/{pack.parent.name}", pack)
            except Exception as exc:  # noqa: BLE001 - one unreadable scene must not close the browser
                self._preview.show(None, f"Could not read zbg/{pack.parent.name}/{pack.name}: {exc}")
                return
            finally:
                self.configure(cursor="")
            self._cache[name] = loaded
            while len(self._cache) > PREVIEW_CACHE_SIZE:
                self._cache.pop(next(iter(self._cache)))
        self._preview.show(loaded)

    # -- closing --------------------------------------------------------------------------
    def _use(self) -> None:
        name = self._selected()
        if name is not None and self._choose:
            self.result = name
            self._close()

    def _clear(self) -> None:
        self.result = ""
        self._close()

    def _close(self) -> None:
        self._preview.cleanup()
        self.destroy()


class BattleScenePanel(ttk.Frame):
    """The chapter page's Battle scenes tab: the ``BattleTerrData`` row of the
    phase's map (:meth:`select_map`)."""

    display_name = "Battle scenes"

    def __init__(self, parent: tk.Misc, project: ModProject, changelog: ChangeLog,
                 session_provider: Callable[[], object], map_editor=None):
        super().__init__(parent, style="Page.TFrame")
        self._project = project
        self._changelog = changelog
        self._session_provider = session_provider
        self._map_editor = map_editor
        self._map: Optional[str] = None
        self._edit_default = False
        self._subscribed = None
        self._cells: dict[int, tuple[tk.StringVar, ttk.Label]] = {}
        self._models: Optional[dict[str, Path]] = None
        self._counts_key = None
        self._only_map = tk.BooleanVar(value=True)

        top = ttk.Frame(self, padding=(8, 8, 8, 0))
        top.pack(fill="x")
        self._save_button = ttk.Button(top, text="Save FE8Data.bin", style="Accent.TButton", command=self._save,
                                       state="disabled")
        self._save_button.pack(side="left")
        self._revert_button = ttk.Button(top, text="Discard unsaved edits", command=self._revert, state="disabled")
        self._revert_button.pack(side="left", padx=(6, 0))
        self._status = ttk.Label(top, text="", style="Muted.TLabel")
        self._status.pack(side="left", padx=(10, 0))
        ttk.Checkbutton(top, text="Only terrain types on this map", variable=self._only_map,
                        command=self._render).pack(side="right")
        self._scroll = ScrollFrame(self, padding=(16, 8, 16, 16))
        self._scroll.pack(fill="both", expand=True)
        if map_editor is not None:
            map_editor.add_listener(self._on_map_changed)

    # -- data -----------------------------------------------------------------------------
    def _session(self):
        session = self._session_provider()
        if session is not None and session is not self._subscribed:
            session.subscribe(self._on_session_changed)
            self._subscribed = session
        return session if session is not None and session.available else None

    def _rows(self) -> list[fe8data.BattleTerrainRow]:
        session = self._session()
        if session is None:
            return []
        try:
            return fe8data.read_battle_terrain(session.data)
        except (KeyError, ValueError, struct.error):
            return []

    def _write(self, rows: list[fe8data.BattleTerrainRow], log_text: str) -> None:
        session = self._session()
        session.data = fe8data.write_battle_terrain(session.data, rows)
        session.changed(self)
        self._changelog.append("FE8Data.bin", log_text)

    def _scene_models(self) -> dict[str, Path]:
        if self._models is None:
            self._models = scene_models(self._project)
        return self._models

    def _terrain_names(self, session) -> tuple[list[str], list[str]]:
        """Each terrain type's display name and ``TerrainData`` name, in column order."""
        if session is None:
            return [], []
        try:
            types = fe8data.read_terrain_types(session.data)
        except (KeyError, ValueError, IndexError, struct.error):
            return [], []
        if self._map_editor is not None:
            return [self._map_editor.terrain_label(t.name) for t in types], [t.name for t in types]
        return [t.name for t in types], [t.name for t in types]

    def _tile_counts(self) -> Optional[Counter]:
        """Tiles per terrain-type name on the map, when the map editor holds this map."""
        editor = self._map_editor
        if editor is None or editor.map_name != self._map or editor.terrain_grid is None:
            return None
        return Counter(name for column in editor.terrain_grid for name in column if name)

    # -- workspace ------------------------------------------------------------------------
    def select_map(self, map_name: Optional[str]) -> None:
        """Show the row of map folder ``map_name`` (``bmap05_2``)."""
        self.flush()
        if map_name != self._map:
            self._edit_default = False
        self._map = map_name
        self._models = None  # the zbg folders may have changed (3D Models imports)
        self._render()

    def _on_session_changed(self, source) -> None:
        if source is self:
            return
        try:
            self._render()
        except tk.TclError:
            pass

    def _on_map_changed(self) -> None:
        counts = self._tile_counts()
        key = (self._map, frozenset(counts) if counts is not None else None)
        if key != self._counts_key:
            try:
                self._render()
            except tk.TclError:
                pass

    # -- rendering ------------------------------------------------------------------------
    def _render(self) -> None:
        body = self._scroll.body
        for child in body.winfo_children():
            child.destroy()
        self._cells = {}
        self._update_status()
        session = self._session()
        if self._map is None:
            ttk.Label(body, text="This chapter has no map folder, so it has no battle scenes.",
                      style="Muted.TLabel").pack(anchor="w")
            return
        if session is None:
            ttk.Label(body, text="FE8Data.bin could not be read.", style="Muted.TLabel").pack(anchor="w")
            return
        rows = self._rows()
        if not rows:
            ttk.Label(body, text="FE8Data.bin has no BattleTerrData table.", style="Muted.TLabel").pack(anchor="w")
            return
        own = find_row(rows, self._map)
        editing = own if own is not None else (0 if self._edit_default else None)
        shown = rows[editing if editing is not None else 0]
        default = rows[0]

        section_header(body, f"Battle scenes of {self._map}",
                       "the scenery drawn behind a fight, per terrain type of the tile").pack(fill="x")
        state = ttk.Frame(body, style="Page.TFrame")
        state.pack(fill="x", pady=(6, 10))
        default_name = default.map_name or "row 0"
        if own == 0:
            text = "Default battle scenery"
        elif own is not None:
            text = f"Custom battle scenery - empty cells use {default_name}"
        elif self._edit_default:
            text = "Editing default battle scenery"
            ttk.Button(state, text="Stop editing the default row",
                       command=lambda: self._set_edit_default(False)).pack(side="right")
            ttk.Button(state, text=f"Give {self._map} its own row", command=self._add_row).pack(
                side="right", padx=(0, 6))
        else:
            text = f"Uses default battle scenery - {default_name}"
            ttk.Button(state, text="Edit the default row", command=lambda: self._set_edit_default(True)).pack(
                side="right")
            ttk.Button(state, text=f"Give {self._map} its own row", command=self._add_row).pack(
                side="right", padx=(0, 6))
        state_style = "Strong.TLabel" if own == 0 or self._edit_default else "Muted.TLabel"
        ttk.Label(state, text=text, style=state_style, wraplength=640, justify="left").pack(side="left")

        labels, keys = self._terrain_names(session)
        counts = self._tile_counts()
        self._counts_key = (self._map, frozenset(counts) if counts is not None else None)
        columns = range(len(shown.scenes))
        if self._only_map.get() and counts is not None:
            columns = [k for k in columns if k < len(keys) and counts.get(keys[k])]
            ttk.Label(body, style="Faint.TLabel", text=(
                f"{len(columns)} of the {len(shown.scenes)} terrain types are on this map; clear "
                "\"Only terrain types on this map\" to see them all.")).pack(anchor="w", pady=(0, 6))
        elif self._only_map.get():
            ttk.Label(body, style="Faint.TLabel", text=(
                "The map could not be read, so every terrain type is listed.")).pack(anchor="w", pady=(0, 6))

        names = scene_names(self._scene_models(), rows)
        grid = ttk.Frame(body, style="Page.TFrame")
        grid.pack(fill="x")
        for header, column in (("Terrain type", 0), ("Tiles", 1), ("Battle scene", 2)):
            ttk.Label(grid, text=header, style="Muted.TLabel").grid(row=0, column=column, sticky="w", padx=(0, 10))
        for line, k in enumerate(columns, start=1):
            label = labels[k] if k < len(labels) else str(k)
            key = keys[k] if k < len(keys) else ""
            ttk.Label(grid, text=f"{k}: {label}" + (f"  [{key}]" if key and key != label else "")).grid(
                row=line, column=0, sticky="w", padx=(0, 10), pady=1)
            ttk.Label(grid, text=str(counts.get(key, 0)) if counts is not None else "",
                      style="Muted.TLabel").grid(row=line, column=1, sticky="e", padx=(0, 10))
            var = tk.StringVar(value=shown.scenes[k] or "")
            box = ttk.Combobox(grid, textvariable=var, values=[""] + names, width=22)
            box.grid(row=line, column=2, sticky="w", pady=1)
            browse = ttk.Button(grid, text="Browse…", command=lambda k=k: self._browse(k))
            browse.grid(row=line, column=3, sticky="w", padx=(6, 0))
            note = ttk.Label(grid, text="", style="Muted.TLabel")
            note.grid(row=line, column=4, sticky="w", padx=(10, 0))
            self._cells[k] = (var, note)
            self._update_note(k, rows, editing)
            if editing is None:
                box.configure(state="disabled")
                browse.configure(text="View…")
            else:
                box.bind("<<ComboboxSelected>>", lambda e, k=k: self._apply(k))
                box.bind("<Return>", lambda e, k=k: self._apply(k))
                box.bind("<FocusOut>", lambda e, k=k: self._apply(k))

    def _update_note(self, k: int, rows: list[fe8data.BattleTerrainRow], editing: Optional[int]) -> None:
        var, note = self._cells[k]
        value = rows[editing].scenes[k] if editing is not None else rows[0].scenes[k]
        missing = value and find_scene(self._scene_models(), value) is None
        if editing not in (None, 0) and not value:
            fallback = rows[0].scenes[k]
            text = f"default: {fallback}" if fallback else "default: none"
        elif missing:
            text = "no zbg folder of that name"
        else:
            text = ""
        note.configure(text=text, style="Danger.TLabel" if missing else "Muted.TLabel")

    def _update_status(self) -> None:
        session = self._session_provider()
        dirty = bool(session is not None and getattr(session, "dirty", False))
        try:
            self._save_button.configure(state="normal" if dirty else "disabled")
            self._revert_button.configure(state="normal" if dirty else "disabled")
            if dirty:
                self._status.configure(text="Unsaved changes (FE8Data.bin)", style="Muted.TLabel")
            elif self._status.cget("style") != "Danger.TLabel":
                self._status.configure(text="")
        except tk.TclError:
            pass

    # -- editing --------------------------------------------------------------------------
    def _editing_row(self, rows: list[fe8data.BattleTerrainRow]) -> Optional[int]:
        own = find_row(rows, self._map) if self._map else None
        return own if own is not None else (0 if self._edit_default else None)

    def _apply(self, k: int, value: Optional[str] = None) -> None:
        if k not in self._cells:
            return
        var, _note = self._cells[k]
        value = (var.get() if value is None else value).strip() or None
        rows = self._rows()
        editing = self._editing_row(rows)
        if editing is None or k >= len(rows[editing].scenes) or rows[editing].scenes[k] == value:
            return
        rows[editing].scenes[k] = value
        who = rows[editing].map_name or f"row {editing}"
        self._write(rows, f"Battle scene of {who}, terrain type {k}: {value or '(default)'}")
        var.set(value or "")
        self._update_note(k, rows, editing)
        self._update_status()

    def _browse(self, k: int) -> None:
        rows = self._rows()
        editing = self._editing_row(rows)
        row = rows[editing if editing is not None else 0]
        current = row.scenes[k] or (rows[0].scenes[k] if editing not in (None, 0) else None)
        labels, _keys = self._terrain_names(self._session())
        terrain = labels[k] if k < len(labels) else str(k)
        dialog = BattleSceneBrowser(
            self, self._project, scene_names(self._scene_models(), rows), current, scene_users(rows),
            title=f"Battle scene of {self._map}: {terrain}" if editing is not None else "Battle scenes",
            clear_label="Use the default row's" if editing not in (None, 0) else None, choose=editing is not None)
        if editing is None:
            return  # browsing only: this map has no row to write to
        self.wait_window(dialog)
        if dialog.result is not None:
            self._apply(k, dialog.result)

    def _set_edit_default(self, value: bool) -> None:
        self._edit_default = value
        self._render()

    def _add_row(self) -> None:
        rows = self._rows()
        if not rows or self._map is None or find_row(rows, self._map) is not None:
            return
        rows.append(fe8data.BattleTerrainRow(self._map, [None] * len(rows[0].scenes)))
        self._edit_default = False
        self._write(rows, f"Added a battle-scene row for {self._map}")
        self._render()


    def flush(self) -> None:
        """Apply a cell still being typed in (a button click doesn't take its focus)."""
        if not self._cells:
            return
        rows = self._rows()
        editing = self._editing_row(rows)
        if editing is None:
            return
        for k, (var, _note) in list(self._cells.items()):
            if k < len(rows[editing].scenes) and (var.get().strip() or None) != rows[editing].scenes[k]:
                self._apply(k)

    def _save(self) -> None:
        self.flush()
        session = self._session()
        if session is None:
            return
        try:
            session.save()
        except OSError as exc:
            messagebox.showerror("Could not save FE8Data.bin", str(exc), parent=self)
            self._status.configure(text=f"Not saved: {exc}", style="Danger.TLabel")
            return
        self._update_status()
        self._status.configure(text="Saved FE8Data.bin", style="Muted.TLabel")

    def _revert(self) -> None:
        session = self._session()
        if session is None or not messagebox.askyesno(
                "Discard unsaved edits?", "Discard every unsaved FE8Data.bin edit (on every page, not only the "
                "battle scenes)?", icon="warning", parent=self):
            return
        session.revert()
        self._render()
