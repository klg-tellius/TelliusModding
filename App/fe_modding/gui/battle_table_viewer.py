"""Base page for the battle engine's one-file-per-item ``.dbx`` tables.

Weapons (``xwp/``) and sceneries (``zbg/``) share one shape: a list of
entries of ``zdbx.cmp``, a few fields per entry edited with dropdowns, and
the first edit keeping the vanilla archive for "Restore original". A
subclass names the folder, parses an entry and says which fields exist."""

from __future__ import annotations

import tkinter as tk
from tkinter import messagebox, ttk

from .. import battle_tables
from ..exceptions import ProjectError
from ..formats import dbx
from ..project import ModProject
from .changelog import ChangeLog
from .editor_panel import EditorPanel


def choice_label(table: dict[int, str], value: int) -> str:
    return f"{value} - {table[value]}" if value in table else f"{value} - unknown"


class BattleTableViewer(EditorPanel):
    """Subclass contract: set the class attributes and implement the hooks."""

    folder = ""  # zdbx.cmp folder, e.g. "xwp"
    entry_suffix = ".dbx"
    noun = "entry"  # "weapon", "scenery"
    plural = "entries"
    columns: tuple = ()  # (key, title, width, anchor)
    #: (label, key, choices {number: text} or None for free text)
    fields: tuple = ()
    changelog_scope = ""
    can_add = True

    def __init__(self, parent: tk.Misc, project: ModProject, changelog: ChangeLog):
        super().__init__(parent)
        self._project = project
        self._changelog = changelog
        self._tables: dict[str, object] = {}
        self._paths: dict[str, str] = {}
        self._edited: set[str] = set()
        self._build_widgets()
        self._load()

    # -- hooks ----------------------------------------------------------------
    def name_of(self, path: str) -> str:
        raise NotImplementedError

    def parse(self, text: str):
        raise NotImplementedError

    def row(self, name: str, table) -> tuple:
        raise NotImplementedError

    def values(self, table) -> dict[str, str]:
        """Field key -> text to show in the form."""
        raise NotImplementedError

    def describe(self, name: str, table) -> str:
        return ""

    def set_field(self, text: str, key: str, value: str) -> str:
        raise NotImplementedError

    def new_entry(self) -> tuple[str, str] | None:
        """Ask for and build a new entry: (name, text), or None to cancel."""
        return None

    def note(self) -> str:
        return ""

    def entry_path(self, name: str) -> str:
        return self._paths.get(name) or f"{self.folder}/{name}{self.entry_suffix}"

    # -- layout ---------------------------------------------------------------
    def _build_widgets(self) -> None:
        top = ttk.Frame(self, padding=(8, 8, 8, 0))
        top.pack(fill="x")
        ttk.Label(top, text="Search").pack(side="left")
        self._query = tk.StringVar()
        ttk.Entry(top, textvariable=self._query).pack(side="left", fill="x", expand=True, padx=(6, 0))
        self._query.trace_add("write", lambda *_: self._refresh())
        self._count = ttk.Label(self, text="", style="Muted.TLabel", padding=(8, 4))
        self._count.pack(anchor="w")

        body = ttk.PanedWindow(self, orient="horizontal")
        body.pack(fill="both", expand=True, padx=8, pady=(0, 8))
        left = ttk.Frame(body)
        body.add(left, weight=3)
        cols = [c[0] for c in self.columns] + ["state"]
        self._tree = ttk.Treeview(left, columns=cols, show="headings", selectmode="browse")
        for key, title, width, anchor in self.columns:
            self._tree.heading(key, text=title)
            self._tree.column(key, width=width, anchor=anchor, stretch=key == self.columns[0][0])
        self._tree.column("state", width=70, anchor="w")
        scroll = ttk.Scrollbar(left, command=self._tree.yview)
        self._tree.config(yscrollcommand=scroll.set)
        self._tree.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")
        self._tree.bind("<<TreeviewSelect>>", lambda _e: self._show_selected())

        right = ttk.Frame(body, padding=(12, 0, 0, 0))
        body.add(right, weight=2)
        self._title = ttk.Label(right, text=f"(no {self.noun} selected)", font=("Segoe UI", 12, "bold"))
        self._title.pack(anchor="w")
        self._detail = ttk.Label(right, text="", style="Muted.TLabel", justify="left")
        self._detail.pack(anchor="w", pady=(2, 8))

        form = ttk.Frame(right)
        form.pack(anchor="w", fill="x")
        form.columnconfigure(1, weight=1)
        self._vars: dict[str, tk.StringVar] = {}
        for row, (label, key, choices) in enumerate(self.fields):
            self._vars[key] = tk.StringVar()
            ttk.Label(form, text=label).grid(row=row, column=0, sticky="w", pady=3)
            values = [choice_label(choices, k) for k in choices] if choices else []
            ttk.Combobox(form, textvariable=self._vars[key], values=values, width=30,
                         state="readonly" if choices else "normal").grid(row=row, column=1, sticky="ew", padx=(8, 0), pady=3)
        if self.note():
            ttk.Label(right, text=self.note(), style="Muted.TLabel", wraplength=360, justify="left").pack(anchor="w", pady=(4, 8))

        actions = ttk.Frame(right)
        actions.pack(anchor="w")
        self._apply_btn = ttk.Button(actions, text="Apply", command=self._apply, state="disabled")
        self._apply_btn.pack(side="left")
        self._restore_btn = ttk.Button(actions, text="Restore original", command=self._restore, state="disabled")
        self._restore_btn.pack(side="left", padx=(6, 0))
        if self.can_add:
            ttk.Button(actions, text=f"Add {self.noun}...", command=self._add).pack(side="left", padx=(6, 0))
        self._status = ttk.Label(right, text="", style="Muted.TLabel", wraplength=360, justify="left")
        self._status.pack(anchor="w", pady=(8, 0))

    # -- list -----------------------------------------------------------------
    def _load(self) -> None:
        self._tables.clear()
        self._paths.clear()
        try:
            texts = battle_tables.read_entries(self._project, self.folder, self.entry_suffix)
            self._edited = battle_tables.modified_entries(self._project, self.folder)
        except (ProjectError, OSError) as exc:
            self._count.config(text=f"Could not read zdbx.cmp: {exc}. Extract the project first.")
            return
        for path, text in texts.items():
            try:
                name = self.name_of(path)
                self._tables[name] = self.parse(text)
                self._paths[name] = path
            except dbx.DbxError:
                continue
        self._refresh()

    def _refresh(self) -> None:
        query = self._query.get().strip().lower()
        selected = self._selected()
        self._tree.delete(*self._tree.get_children())
        for name, table in sorted(self._tables.items()):
            if query and query not in name.lower():
                continue
            self._tree.insert("", "end", iid=name, values=(*self.row(name, table),
                                                           "edited" if self._paths[name] in self._edited else ""))
        self._count.config(text=f"{len(self._tree.get_children())} of {len(self._tables)} {self.plural}")
        if selected and self._tree.exists(selected):
            self._tree.selection_set(selected)

    def _selected(self) -> str | None:
        selection = self._tree.selection()
        return selection[0] if selection else None

    def _show_selected(self) -> None:
        name = self._selected()
        if name is None:
            return
        table = self._tables[name]
        self._title.config(text=name)
        self._detail.config(text=self.describe(name, table))
        for key, text in self.values(table).items():
            self._vars[key].set(text)
        self._apply_btn.config(state="normal")
        self._restore_btn.config(state="normal")
        self._status.config(text="")

    # -- edits ------------------------------------------------------------------
    def _apply(self) -> None:
        name = self._selected()
        if name is None:
            return
        path = self.entry_path(name)
        try:
            text = battle_tables.read_entry(self._project, path)
            new = text
            for _label, key, choices in self.fields:
                value = self._vars[key].get().strip()
                new = self.set_field(new, key, value.split(" - ", 1)[0].strip() if choices else value)
            if new == text:
                self._status.config(text="No change.")
                return
            battle_tables.write_entry(self._project, path, new)
        except (dbx.DbxError, ProjectError) as exc:
            messagebox.showerror(self.display_name, str(exc), parent=self)
            return
        self._after_edit(name, f"Edited {self.noun} {name}")

    def _restore(self) -> None:
        name = self._selected()
        if name is None:
            return
        path = self.entry_path(name)
        if not battle_tables.is_modified(self._project, path):
            self._status.config(text="Already the original.")
            return
        battle_tables.restore_entry(self._project, path)
        self._after_edit(name, f"Restored {self.noun} {name}")

    def _add(self) -> None:
        try:
            made = self.new_entry()
            if made is None:
                return
            name, text = made
            if name in self._tables:
                raise dbx.DbxError(f"{name} already exists.")
            battle_tables.write_entry(self._project, self.entry_path(name), text, create=True)
        except (dbx.DbxError, ProjectError) as exc:
            messagebox.showerror(self.display_name, str(exc), parent=self)
            return
        self._after_edit(name, f"Added {self.noun} {name}")

    def _after_edit(self, name: str, message: str) -> None:
        self._changelog.append(self.changelog_scope or self.display_name, message)
        self._load()
        if self._tree.exists(name):
            self._tree.selection_set(name)
            self._tree.see(name)
            self.after(50, lambda: self._status.config(text=message + "."))  # after the select event
