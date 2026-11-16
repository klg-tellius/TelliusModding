"""A shared editor for files that are a few tables of fixed records (the glossary, the
Conversation Room, the epilogues, the class introductions).

A subclass reads its files into :class:`TableSpec` lists in :meth:`load_tables`, and turns them
back into bytes in :meth:`build_files`. Each table gets a tab: the records in a list, a form
for the selected one, and Add / Duplicate / Remove / move buttons. ``linked`` is a second list
kept in step with the records (the glossary's unlock flags), shown and edited as extra columns.
Message-key columns show the key's text from the message file the subclass names.
"""

from __future__ import annotations

import copy
import tkinter as tk
from dataclasses import dataclass, field
from pathlib import Path
from tkinter import messagebox, ttk
from typing import Callable, Optional

from ..project import ModProject
from .changelog import ChangeLog
from .editor_panel import EditorPanel
from .message_reference import preview
from .widgets import info


@dataclass
class Column:
    attr: str
    heading: str
    kind: str = "text"      # text, int, key (a message key: shows its text), optional (text or empty)
    width: int = 120
    linked: bool = False    # read from the linked list instead of the record
    editable: bool = True
    note: str = ""


@dataclass
class TableSpec:
    key: str
    label: str
    rows: list
    columns: list[Column]
    new_row: Optional[Callable[[], object]] = None
    linked: Optional[list] = None
    new_linked: Optional[Callable[[object], object]] = None  # makes the linked entry for a new row
    note: str = ""
    fixed: bool = False      # no add/remove/move (the game reads a fixed number)


def _get(obj, attr):
    return getattr(obj, attr)


def _show(value, kind: str) -> str:
    if value is None:
        return ""
    return str(value)


class RecordTablesEditor(EditorPanel):
    display_name = ""
    #: what the save button and messages call the data
    subject = "records"
    help_text = ""

    def __init__(self, parent: tk.Misc, project: ModProject, changelog: ChangeLog):
        super().__init__(parent)
        self._project = project
        self._changelog = changelog
        self._dirty = False
        self._tables: list[TableSpec] = []
        self._trees: dict[str, ttk.Treeview] = {}
        self._forms: dict[str, dict[str, tk.StringVar]] = {}
        self._previews: dict[str, dict[str, ttk.Label]] = {}
        self._selected: dict[str, Optional[int]] = {}
        self._texts: dict[str, str] = {}
        self._build_bar()
        self._notebook = ttk.Notebook(self)
        self._notebook.pack(fill="both", expand=True, padx=8, pady=(0, 8))
        self._load()

    # -- subclass hooks ------------------------------------------------------------------
    def load_tables(self) -> list[TableSpec]:
        raise NotImplementedError

    def build_files(self) -> dict[Path, bytes]:
        raise NotImplementedError

    def message_texts(self) -> dict[str, str]:
        return {}

    def problems(self) -> list[str]:
        return []

    def build_extra(self, spec: TableSpec, parent) -> None:
        """Add widgets under a table's form (a preview)."""

    def row_selected(self, spec: TableSpec, index: Optional[int]) -> None:
        """Called after a row is shown in the form (``None``: nothing selected)."""

    def describe(self) -> str:
        return ", ".join(f"{len(t.rows)} {t.label.lower()}" for t in self._tables)

    # -- layout ---------------------------------------------------------------------------
    def _build_bar(self) -> None:
        bar = ttk.Frame(self, padding=(8, 8, 8, 4))
        bar.pack(fill="x")
        self._save_button = ttk.Button(bar, text=f"Save {self.subject}", style="Accent.TButton",
                                       command=self.save, state="disabled")
        self._save_button.pack(side="left")
        ttk.Button(bar, text="Revert", command=self._revert).pack(side="left", padx=(6, 0))
        self._status = ttk.Label(bar, text="", style="Muted.TLabel")
        self._status.pack(side="left", padx=(10, 0))
        if self.help_text:
            info(bar, self.help_text).pack(side="right")

    def _build_tab(self, spec: TableSpec) -> None:
        tab = ttk.Frame(self._notebook, padding=8)
        self._notebook.add(tab, text=spec.label)
        if spec.note:
            ttk.Label(tab, text=spec.note, style="Muted.TLabel", wraplength=900, justify="left").pack(
                anchor="w", pady=(0, 6))
        body = ttk.Frame(tab)
        body.pack(fill="both", expand=True)
        left = ttk.Frame(body)
        left.pack(side="left", fill="both", expand=True)
        columns = ["n"] + [c.attr + ("@" if c.linked else "") for c in spec.columns]
        tree = ttk.Treeview(left, columns=columns, show="headings", selectmode="browse", height=18)
        tree.heading("n", text="#")
        tree.column("n", width=40, anchor="e", stretch=False)
        for c, cid in zip(spec.columns, columns[1:]):
            tree.heading(cid, text=c.heading)
            tree.column(cid, width=c.width, anchor="e" if c.kind == "int" else "w", stretch=False)
        scroll = ttk.Scrollbar(left, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=scroll.set)
        tree.pack(side="left", fill="both", expand=True)
        scroll.pack(side="left", fill="y")
        tree.bind("<<TreeviewSelect>>", lambda e, s=spec: self._on_select(s))
        self._trees[spec.key] = tree

        right = ttk.Frame(body, padding=(12, 0, 0, 0))
        right.pack(side="left", fill="y")
        form, previews = {}, {}
        row = 0
        for c in spec.columns:
            ttk.Label(right, text=c.heading).grid(row=row, column=0, sticky="w", pady=(4, 0))
            var = tk.StringVar()
            entry = ttk.Entry(right, textvariable=var, width=34, state="normal" if c.editable else "readonly")
            entry.grid(row=row, column=1, sticky="w", padx=(6, 0), pady=(4, 0))
            entry.bind("<Return>", lambda e, s=spec: self._apply(s))
            entry.bind("<FocusOut>", lambda e, s=spec: self._apply(s))
            form[c.attr + ("@" if c.linked else "")] = var
            row += 1
            if c.kind == "key" or c.note:
                label = ttk.Label(right, text=c.note, style="Muted.TLabel", wraplength=320, justify="left")
                label.grid(row=row, column=1, sticky="w", padx=(6, 0))
                previews[c.attr + ("@" if c.linked else "")] = label
                row += 1
        if not spec.fixed:
            buttons = ttk.Frame(right)
            buttons.grid(row=row, column=0, columnspan=2, sticky="w", pady=(12, 0))
            for text, command in (("▲", lambda s=spec: self._move(s, -1)), ("▼", lambda s=spec: self._move(s, 1)),
                                  ("Add", lambda s=spec: self._add(s, duplicate=False)),
                                  ("Duplicate", lambda s=spec: self._add(s, duplicate=True)),
                                  ("Remove", lambda s=spec: self._remove(s))):
                if text == "Add" and spec.new_row is None:
                    continue
                ttk.Button(buttons, text=text, width=3 if len(text) == 1 else None, command=command).pack(
                    side="left", padx=(0, 4))
        extra = ttk.Frame(right)
        extra.grid(row=row + 1, column=0, columnspan=2, sticky="w", pady=(12, 0))
        self.build_extra(spec, extra)
        self._forms[spec.key] = form
        self._previews[spec.key] = previews

    # -- data -----------------------------------------------------------------------------
    def _load(self) -> None:
        for tab in self._notebook.tabs():
            self._notebook.forget(tab)
        self._trees.clear()
        self._forms.clear()
        self._previews.clear()
        try:
            self._tables = self.load_tables()
        except FileNotFoundError as exc:
            self._tables = []
            self._status.config(text=f"{Path(str(exc.filename or exc)).name} not found; extract the project first.")
            return
        except (OSError, ValueError) as exc:
            self._tables = []
            self._status.config(text=f"Could not read the files: {exc}")
            return
        self._texts = self.message_texts()
        for spec in self._tables:
            self._build_tab(spec)
            self._fill(spec, 0)
        self._set_dirty(False)
        self._status.config(text=self.describe())

    def _value(self, spec: TableSpec, index: int, column: Column):
        source = spec.linked[index] if column.linked else spec.rows[index]
        return _get(source, column.attr)

    def _row_values(self, spec: TableSpec, index: int) -> tuple:
        return (index,) + tuple(_show(self._value(spec, index, c), c.kind) for c in spec.columns)

    def _fill(self, spec: TableSpec, select: Optional[int]) -> None:
        tree = self._trees[spec.key]
        tree.delete(*tree.get_children())
        for i in range(len(spec.rows)):
            tree.insert("", "end", iid=str(i), values=self._row_values(spec, i))
        self._selected[spec.key] = None
        if select is not None and spec.rows:
            select = max(0, min(select, len(spec.rows) - 1))
            tree.selection_set(str(select))
            tree.see(str(select))
            self._on_select(spec)
        else:
            self._show(spec)

    def _on_select(self, spec: TableSpec) -> None:
        selection = self._trees[spec.key].selection()
        self._selected[spec.key] = int(selection[0]) if selection else None
        self._show(spec)

    def _show(self, spec: TableSpec) -> None:
        index = self._selected.get(spec.key)
        for c in spec.columns:
            cid = c.attr + ("@" if c.linked else "")
            value = None if index is None else self._value(spec, index, c)
            self._forms[spec.key][cid].set(_show(value, c.kind))
            label = self._previews[spec.key].get(cid)
            if label is not None:
                text = c.note
                if c.kind == "key" and value:
                    shown = self._texts.get(value)
                    text = preview(shown, fe10=True) if shown else "(no text for this message key)"
                label.config(text=text)
        self.row_selected(spec, index)

    def _apply(self, spec: TableSpec) -> None:
        index = self._selected.get(spec.key)
        if index is None:
            return
        changed = False
        for c in spec.columns:
            if not c.editable:
                continue
            cid = c.attr + ("@" if c.linked else "")
            raw = self._forms[spec.key][cid].get().strip()
            target = spec.linked[index] if c.linked else spec.rows[index]
            old = _get(target, c.attr)
            try:
                new = self._parse(raw, c, old)
            except ValueError as exc:
                messagebox.showerror("Invalid value", f"{c.heading}: {exc}", parent=self)
                self._show(spec)
                return
            if new != old:
                try:
                    setattr(target, c.attr, new)
                except ValueError as exc:
                    messagebox.showerror("Invalid value", f"{c.heading}: {exc}", parent=self)
                    self._show(spec)
                    return
                changed = True
        if changed:
            self._trees[spec.key].item(str(index), values=self._row_values(spec, index))
            self._show(spec)
            self._set_dirty(True)

    @staticmethod
    def _parse(raw: str, column: Column, old):
        if column.kind == "int":
            return int(raw, 0)
        if column.kind in ("optional", "key"):
            return raw or None
        if not raw:
            raise ValueError("cannot be empty")
        return raw

    def _add(self, spec: TableSpec, duplicate: bool) -> None:
        index = self._selected.get(spec.key)
        if duplicate:
            if index is None:
                return
            row = copy.deepcopy(spec.rows[index])
        else:
            row = spec.new_row()
        at = len(spec.rows) if index is None else index + 1
        spec.rows.insert(at, row)
        if spec.linked is not None:
            spec.linked.insert(at, spec.new_linked(row) if spec.new_linked else copy.deepcopy(spec.linked[index]))
        self._set_dirty(True)
        self._fill(spec, at)

    def _remove(self, spec: TableSpec) -> None:
        index = self._selected.get(spec.key)
        if index is None:
            return
        del spec.rows[index]
        if spec.linked is not None:
            del spec.linked[index]
        self._set_dirty(True)
        self._fill(spec, index)

    def _move(self, spec: TableSpec, step: int) -> None:
        index = self._selected.get(spec.key)
        if index is None or not 0 <= index + step < len(spec.rows):
            return
        for items in (spec.rows, spec.linked):
            if items is not None:
                items[index], items[index + step] = items[index + step], items[index]
        self._set_dirty(True)
        self._fill(spec, index + step)

    def _set_dirty(self, dirty: bool) -> None:
        self._dirty = dirty
        self._save_button.config(state="normal" if dirty else "disabled")
        if dirty:
            self._status.config(text="Unsaved changes")

    # -- save -----------------------------------------------------------------------------
    def save(self) -> bool:
        if not self._tables:
            return False
        problems = self.problems()
        if problems and not messagebox.askyesno(
                "Save anyway?", "The game may not read these as intended:\n\n" + "\n".join(problems[:12])
                + "\n\nSave anyway?", parent=self):
            return False
        try:
            files = self.build_files()
            for path, data in files.items():
                self._project.write_keeping_original(path, data)
        except (OSError, ValueError) as exc:
            messagebox.showerror(f"Could not save the {self.subject.lower()}", str(exc), parent=self)
            return False
        for path in files:
            self._changelog.append(path.name, f"Saved {self.describe()}")
        self._set_dirty(False)
        self._status.config(text="Saved " + ", ".join(p.name for p in files))
        return True

    def _revert(self) -> None:
        if self._dirty and not self._confirm_discard():
            return
        self._load()

    def _confirm_discard(self) -> bool:
        return messagebox.askyesno("Discard changes?", f"The {self.subject.lower()} have unsaved changes. "
                                   "Discard them?", parent=self)
