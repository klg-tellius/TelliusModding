"""A page of fixed-row tables edited through typed fields (:mod:`formats.record_fields`).

Each :class:`FieldTab` is one tab: its rows in a list (the ``columns`` fields), and a form with one
box per field for the selected row. **Apply** writes the form through the tab's ``write``; **Add
(copy)** and **Remove** appear when the tab has ``add`` / ``remove``. A text field with ``choices``
offers them in its box (any other text is accepted). Edits stay in memory until **Save**, which
writes the page's one logical file through the project.

A subclass (or a caller) gives the logical file and the tabs; every tab works on the same bytes.
"""

from __future__ import annotations

import tkinter as tk
from dataclasses import dataclass, field
from tkinter import messagebox, ttk
from typing import Callable, Optional

from ..formats.record_fields import BIT, LABEL, Field, show
from ..project import ModProject
from .changelog import ChangeLog
from .editor_panel import EditorPanel
from .widgets import info


@dataclass
class FieldTab:
    key: str
    title: str
    fields: tuple[Field, ...]
    read: Callable[[bytes], list[dict]]          # data -> one value dict per row
    write: Callable[[bytes, int, dict], bytes]   # data, row, changed values -> data
    columns: tuple[str, ...] = ()                # field keys shown in the list (default: the first four)
    note: str = ""
    add: Optional[Callable[[bytes, int], tuple[bytes, int]]] = None   # data, copy of -> data, new row
    remove: Optional[Callable[[bytes, int], bytes]] = None
    label: Optional[Callable[[int, dict], str]] = None                # the row's name in the list
    choices: dict[str, Callable[[bytes], list[str]]] = field(default_factory=dict)


def build_field_form(parent: tk.Misc, fields, row: dict, choices: dict | None = None,
                     columns: int = 1) -> dict[str, tk.StringVar]:
    """A grid of labelled boxes for ``fields`` showing ``row``'s values, packed into ``parent``;
    returns field key -> the box's variable. ``choices`` maps a field key to a callable giving the
    names its box offers. Long forms can use several ``columns`` of label/box pairs."""
    grid = ttk.Frame(parent)
    grid.pack(fill="x")
    variables = {}
    per_column = -(-len(fields) // columns) if fields else 1
    for at, f in enumerate(fields):
        line, column = at % per_column, 3 * (at // per_column)
        ttk.Label(grid, text=f.name).grid(row=line, column=column, sticky="w", padx=(0 if column == 0 else 14, 8),
                                          pady=1)
        var = tk.StringVar(value=show(f, row[f.key]))
        width = 28 if columns == 1 else 16
        if f.kind == BIT:
            box = ttk.Combobox(grid, textvariable=var, values=("No", "Yes"), state="readonly", width=width)
        elif f.choices:
            box = ttk.Combobox(grid, textvariable=var, width=width, values=[f"{v} - {n}" for v, n in f.choices])
        elif choices and f.key in choices:
            box = ttk.Combobox(grid, textvariable=var, width=width, values=choices[f.key]())
        else:
            box = ttk.Entry(grid, textvariable=var, width=width + 2)
        box.grid(row=line, column=column + 1, sticky="we", pady=1)
        if f.note:
            info(grid, f.note).grid(row=line, column=column + 2, sticky="w", padx=(4, 0))
        grid.columnconfigure(column + 1, weight=1)
        variables[f.key] = var
    return variables


def changed_values(fields, row: dict, variables: dict[str, tk.StringVar]) -> dict:
    """The boxes whose text differs from ``row``'s value (text as typed)."""
    return {f.key: variables[f.key].get() for f in fields
            if variables[f.key].get().strip() != show(f, row[f.key]).strip()}


class FieldsDialog(tk.Toplevel):
    """A modal form over one record: ``apply(changes)`` writes the changed values and may raise
    ``ValueError`` to keep the dialog open."""

    def __init__(self, parent: tk.Misc, title: str, fields, row: dict, apply: Callable[[dict], None], *,
                 choices: dict | None = None, note: str = "", columns: int = 1):
        super().__init__(parent)
        self.title(title)
        self.transient(parent.winfo_toplevel())
        self._fields, self._row, self._apply = fields, row, apply
        body = ttk.Frame(self, padding=12)
        body.pack(fill="both", expand=True)
        if note:
            ttk.Label(body, text=note, style="Muted.TLabel", wraplength=520 * columns,
                      justify="left").pack(anchor="w", pady=(0, 8))
        self._vars = build_field_form(body, fields, row, choices, columns)
        buttons = ttk.Frame(body)
        buttons.pack(fill="x", pady=(10, 0))
        ttk.Button(buttons, text="Apply", command=self._ok, style="Accent.TButton").pack(side="right")
        ttk.Button(buttons, text="Cancel", command=self.destroy).pack(side="right", padx=(0, 6))
        self.grab_set()

    def _ok(self) -> None:
        changes = changed_values(self._fields, self._row, self._vars)
        if changes:
            try:
                self._apply(changes)
            except (ValueError, IndexError, KeyError, UnicodeError) as exc:
                messagebox.showerror("Not applied", str(exc), parent=self)
                return
        self.destroy()


class FieldTablesPanel(EditorPanel):
    """``logical`` is the project file the tabs edit; ``tabs`` builds the tabs from its bytes."""

    display_name = ""
    logical = ""
    intro = ""

    def __init__(self, parent: tk.Misc, project: ModProject, changelog: ChangeLog):
        super().__init__(parent)
        self._project = project
        self._changelog = changelog
        self._data = b""
        self._dirty = False
        self._tabs: list[FieldTab] = []
        self._rows: dict[str, list[dict]] = {}
        self._trees: dict[str, ttk.Treeview] = {}
        self._forms: dict[str, ttk.Frame] = {}
        self._vars: dict[str, tk.StringVar] = {}
        self._shown: Optional[tuple[str, int]] = None
        self._build_top()
        self._load()

    # -- subclass hooks ---------------------------------------------------------------------------
    def tabs(self, data: bytes) -> list[FieldTab]:
        raise NotImplementedError

    def file_label(self) -> str:
        return self._project.profile.file_label(self.logical)

    # -- data -----------------------------------------------------------------------------------
    def _load(self) -> None:
        try:
            self._data = self._project.read_logical(self.logical)
            self._tabs = self.tabs(self._data)
        except Exception as exc:  # noqa: BLE001 - a missing or unreadable file is reported on the page
            self._status.configure(text=f"Could not read {self.file_label()}: {exc}")
            return
        self._build_tabs()
        self._refresh()

    def _read_rows(self) -> None:
        for tab in self._tabs:
            self._rows[tab.key] = tab.read(self._data)

    def _replace(self, data: bytes, what: str, select: Optional[tuple[str, int]] = None) -> None:
        self._data = data
        self._dirty = True
        self._save_button.configure(state="normal")
        self._changelog.append(self.file_label(), what)
        self._refresh(select or self._shown)
        self._status.configure(text=f"{what} (unsaved)")

    def save(self) -> bool:
        if not self._dirty:
            return True
        try:
            self._project.write_logical(self.logical, self._data)
        except OSError as exc:
            messagebox.showerror(f"Could not save {self.file_label()}", str(exc), parent=self)
            return False
        self._dirty = False
        self._save_button.configure(state="disabled")
        self._status.configure(text=f"Saved {self.file_label()}.")
        self._changelog.append(self.file_label(), f"Saved {self.display_name.lower()}")
        return True

    def _revert(self) -> None:
        if self._dirty and not self._confirm_discard():
            return
        self._dirty = False
        self._save_button.configure(state="disabled")
        for child in self._notebook.winfo_children():
            child.destroy()
        self._trees.clear()
        self._forms.clear()
        self._shown = None
        self._load()
        self._status.configure(text="Changes discarded.")

    def _confirm_discard(self) -> bool:
        return messagebox.askyesno("Unsaved changes", f"Discard the unsaved {self.display_name.lower()} changes?",
                                   parent=self)

    # -- layout ---------------------------------------------------------------------------------
    def _build_top(self) -> None:
        top = ttk.Frame(self, padding=(8, 8, 8, 4))
        top.pack(fill="x")
        ttk.Label(top, text=self.display_name, style="Title.TLabel").pack(side="left")
        self._save_button = ttk.Button(top, text="Save", command=self.save, state="disabled", style="Accent.TButton")
        self._save_button.pack(side="right")
        ttk.Button(top, text="Discard changes", command=self._revert).pack(side="right", padx=(0, 6))
        self._status = ttk.Label(top, style="Muted.TLabel")
        self._status.pack(side="right", padx=8)
        if self.intro:
            ttk.Label(self, padding=(8, 0), style="Muted.TLabel", wraplength=1100, justify="left",
                      text=self.intro).pack(anchor="w")
        self._notebook = ttk.Notebook(self)
        self._notebook.pack(fill="both", expand=True, padx=8, pady=8)

    def _columns(self, tab: FieldTab) -> list[Field]:
        keys = tab.columns or tuple(f.key for f in tab.fields[:4])
        by_key = {f.key: f for f in tab.fields}
        return [by_key[k] for k in keys]

    def _build_tabs(self) -> None:
        for tab in self._tabs:
            frame = ttk.Frame(self._notebook, padding=4)
            self._notebook.add(frame, text=tab.title)
            if tab.note:
                ttk.Label(frame, text=tab.note, style="Muted.TLabel", wraplength=1050,
                          justify="left").pack(anchor="w", pady=(0, 4))
            paned = ttk.PanedWindow(frame, orient="horizontal")
            paned.pack(fill="both", expand=True)
            left = ttk.Frame(paned)
            paned.add(left, weight=3)
            bar = ttk.Frame(left)
            bar.pack(fill="x", pady=(0, 4))
            ttk.Label(bar, text="Find").pack(side="left")
            query = tk.StringVar()
            ttk.Entry(bar, textvariable=query, width=24).pack(side="left", padx=(4, 8))
            query.trace_add("write", lambda *_a, t=tab: self._fill(t))
            if tab.add is not None:
                ttk.Button(bar, text="Add (copy of selected)", command=lambda t=tab: self._add(t)).pack(side="left")
            if tab.remove is not None:
                ttk.Button(bar, text="Remove", command=lambda t=tab: self._remove(t)).pack(side="left", padx=4)
            columns = ["row"] + [f.key for f in self._columns(tab)]
            tree = ttk.Treeview(left, columns=columns, show="headings", selectmode="browse")
            tree.heading("row", text="#")
            tree.column("row", width=60, stretch=False, anchor="e")
            for f in self._columns(tab):
                tree.heading(f.key, text=f.name)
                tree.column(f.key, width=150 if f.kind == LABEL else 90, stretch=f.kind == LABEL)
            tree._query = query  # noqa: SLF001 - the tab's filter text
            scroll = ttk.Scrollbar(left, orient="vertical", command=tree.yview)
            tree.configure(yscrollcommand=scroll.set)
            tree.pack(side="left", fill="both", expand=True)
            scroll.pack(side="left", fill="y")
            tree.bind("<<TreeviewSelect>>", lambda _e, t=tab: self._on_select(t))
            self._trees[tab.key] = tree
            form = ttk.Frame(paned, padding=8)
            paned.add(form, weight=2)
            self._forms[tab.key] = form

    def _row_name(self, tab: FieldTab, index: int, row: dict) -> str:
        return tab.label(index, row) if tab.label else str(index)

    def _fill(self, tab: FieldTab) -> None:
        tree = self._trees[tab.key]
        query = tree._query.get().strip().lower()  # noqa: SLF001
        tree.delete(*tree.get_children())
        for index, row in enumerate(self._rows.get(tab.key, ())):
            values = [show(f, row[f.key]) for f in self._columns(tab)]
            name = self._row_name(tab, index, row)
            if query and query not in " ".join([name, *map(str, row.values())]).lower():
                continue
            tree.insert("", "end", iid=str(index), values=(name, *values))

    def _refresh(self, select: Optional[tuple[str, int]] = None) -> None:
        try:
            self._read_rows()
        except Exception as exc:  # noqa: BLE001
            self._status.configure(text=str(exc))
            return
        for tab in self._tabs:
            self._fill(tab)
        if select is not None:
            key, index = select
            tree = self._trees.get(key)
            if tree is not None and tree.exists(str(index)):
                tree.selection_set(str(index))
                tree.see(str(index))
                self._build_form(next(t for t in self._tabs if t.key == key), index)
        else:
            self._status.configure(text=", ".join(f"{len(self._rows[t.key])} {t.title.lower()}" for t in self._tabs))

    # -- form -----------------------------------------------------------------------------------
    def _on_select(self, tab: FieldTab) -> None:
        selection = self._trees[tab.key].selection()
        if selection:
            self._build_form(tab, int(selection[0]))

    def _build_form(self, tab: FieldTab, index: int) -> None:
        self._shown = (tab.key, index)
        form = self._forms[tab.key]
        for child in form.winfo_children():
            child.destroy()
        row = self._rows[tab.key][index]
        ttk.Label(form, text=f"{tab.title}: {self._row_name(tab, index, row)}",
                  style="Heading.TLabel").pack(anchor="w", pady=(0, 6))
        self._vars = build_field_form(form, tab.fields, row,
                                      {k: (lambda f=f: f(self._data)) for k, f in tab.choices.items()})
        buttons = ttk.Frame(form)
        buttons.pack(fill="x", pady=(8, 0))
        ttk.Button(buttons, text="Apply", command=lambda: self._apply(tab, index)).pack(side="right")
        ttk.Button(buttons, text="Reset form", command=lambda: self._build_form(tab, index)).pack(side="right",
                                                                                                padx=(0, 6))

    def form_values(self, tab: FieldTab, index: int) -> dict:
        """The form's values that differ from row ``index`` (text as typed)."""
        return changed_values(tab.fields, self._rows[tab.key][index], self._vars)

    def _apply(self, tab: FieldTab, index: int) -> None:
        changes = self.form_values(tab, index)
        if not changes:
            self._status.configure(text="No change.")
            return
        try:
            data = tab.write(self._data, index, changes)
        except (ValueError, IndexError, KeyError, UnicodeError) as exc:
            messagebox.showerror("Not applied", str(exc), parent=self)
            return
        self._replace(data, f"{tab.title}: edited row {self._row_name(tab, index, self._rows[tab.key][index])}",
                      (tab.key, index))

    def _selected(self, tab: FieldTab) -> Optional[int]:
        selection = self._trees[tab.key].selection()
        return int(selection[0]) if selection else None

    def _add(self, tab: FieldTab) -> None:
        source = self._selected(tab)
        if source is None:
            source = len(self._rows[tab.key]) - 1
        try:
            data, new = tab.add(self._data, source)
        except (ValueError, IndexError, KeyError) as exc:
            messagebox.showerror("Not added", str(exc), parent=self)
            return
        self._replace(data, f"{tab.title}: added row {new} (copy of {source})", (tab.key, new))

    def _remove(self, tab: FieldTab) -> None:
        index = self._selected(tab)
        if index is None:
            return
        name = self._row_name(tab, index, self._rows[tab.key][index])
        if not messagebox.askyesno("Remove row", f"Remove {tab.title.lower()} row {name}?", parent=self):
            return
        try:
            data = tab.remove(self._data, index)
        except (ValueError, IndexError, KeyError) as exc:
            messagebox.showerror("Not removed", str(exc), parent=self)
            return
        self._shown = None
        for child in self._forms[tab.key].winfo_children():
            child.destroy()
        self._replace(data, f"{tab.title}: removed row {name}")
