"""One page for the battle data each game stores its own way (Battle Data, Battle Cameras).

The page is a search box, a list of items in groups, the selected item's editor, the actions,
Save and Discard (when the data keeps unsaved changes) and a status line. A per-game
:class:`BrowserAdapter` supplies the groups, the editor, the actions and the saving, so both
games get the same screen."""

from __future__ import annotations

import tkinter as tk
from dataclasses import dataclass, field
from tkinter import messagebox, ttk
from typing import Callable

from ..project import ModProject
from .changelog import ChangeLog
from .editor_panel import EditorPanel


@dataclass
class Item:
    key: str
    values: tuple[str, ...]  # one per column after the first: the first column is the label
    label: str = ""


@dataclass
class Group:
    key: str
    label: str
    items: list[Item] = field(default_factory=list)
    info: str = ""  # shown in the group row's second column


class BrowserAdapter:
    """One game's data behind a :class:`BattleBrowser`."""

    display_name = ""
    #: the file the page edits, shown bold in the top bar
    source = ""
    #: a muted line next to it
    note = ""
    #: (key, title, width) after the label column
    columns: tuple[tuple[str, str, int], ...] = (("info", "Details", 200), ("state", "State", 80))
    label_title = "Name"
    #: the data keeps unsaved changes: the page shows Save and Discard
    keeps_changes = False

    def __init__(self, project: ModProject, changelog: ChangeLog):
        self.project = project
        self.changelog = changelog
        self.page: BattleBrowser | None = None

    # -- the page calls these ---------------------------------------------------------
    def load(self) -> list[Group]:
        """Read the data; raise to show the error in the status line."""
        raise NotImplementedError

    def summary(self) -> str:
        """The status line after a load."""
        return ""

    def build_detail(self, parent: ttk.Frame) -> None:
        raise NotImplementedError

    def show(self, key: str | None) -> None:
        """Show item ``key`` (None: nothing selected) in the editor."""

    def actions(self) -> tuple[tuple[str, Callable[[], None]], ...]:
        return ()

    def leave(self) -> bool:
        """Before another item is shown: False keeps the current one (the user cancelled)."""
        return True

    @property
    def dirty(self) -> bool:
        return False

    def save(self) -> bool:
        return True

    def discard(self) -> None:
        """Drop the unsaved changes (the page reloads afterwards)."""

    def cleanup(self) -> None:
        pass

    # -- helpers for adapters -----------------------------------------------------------
    def status(self, text: str) -> None:
        if self.page is not None:
            self.page.set_status(text)

    def changed(self) -> None:
        """The dirty state may have changed."""
        if self.page is not None:
            self.page.refresh_buttons()

    def reload(self, select: str | None = None) -> None:
        if self.page is not None:
            self.page.reload(select)

    def selected(self) -> str | None:
        return self.page.selected() if self.page is not None else None

    def error(self, title: str, exc: object) -> None:
        messagebox.showerror(title, str(exc), parent=self.page)


class BattleBrowser(EditorPanel):
    def __init__(self, parent: tk.Misc, adapter: BrowserAdapter):
        super().__init__(parent)
        self.adapter = adapter
        self.display_name = adapter.display_name
        adapter.page = self
        self._groups: list[Group] = []
        self._items: dict[str, Item] = {}
        self._current: str | None = None
        self._selecting = False

        top = ttk.Frame(self, padding=8)
        top.pack(fill="x")
        if adapter.source:
            ttk.Label(top, text=adapter.source, font=("Segoe UI", 12, "bold")).pack(side="left", padx=(0, 10))
        ttk.Label(top, text="Search").pack(side="left")
        self._query = tk.StringVar()
        ttk.Entry(top, textvariable=self._query, width=28).pack(side="left", padx=(6, 12))
        self._query.trace_add("write", lambda *_: self._fill())
        ttk.Button(top, text="Refresh", command=self._refresh).pack(side="left")
        self._save_button = self._discard_button = None
        if adapter.keeps_changes:
            self._save_button = ttk.Button(top, text="Save", command=self.save, state="disabled")
            self._save_button.pack(side="right")
            self._discard_button = ttk.Button(top, text="Discard changes", command=self._discard, state="disabled")
            self._discard_button.pack(side="right", padx=(0, 6))
        for label, command in reversed(adapter.actions()):
            ttk.Button(top, text=label, command=command).pack(side="right", padx=(0, 6))
        if adapter.note:
            ttk.Label(self, text=adapter.note, style="Muted.TLabel", padding=(8, 0, 8, 4)).pack(anchor="w")

        body = ttk.PanedWindow(self, orient="horizontal")
        body.pack(fill="both", expand=True, padx=8, pady=(0, 4))
        left, right = ttk.Frame(body), ttk.Frame(body, padding=(12, 0, 0, 0))
        body.add(left, weight=2)
        body.add(right, weight=5)
        keys = [key for key, _title, _width in adapter.columns]
        self._tree = ttk.Treeview(left, columns=keys, show="tree headings", selectmode="browse")
        self._tree.heading("#0", text=adapter.label_title)
        self._tree.column("#0", width=230, stretch=True)
        for key, title, width in adapter.columns:
            self._tree.heading(key, text=title)
            self._tree.column(key, width=width, stretch=False)
        scroll = ttk.Scrollbar(left, command=self._tree.yview)
        self._tree.configure(yscrollcommand=scroll.set)
        scroll.pack(side="right", fill="y")
        self._tree.pack(side="left", fill="both", expand=True)
        self._tree.bind("<<TreeviewSelect>>", lambda _e: self._on_select())
        adapter.build_detail(right)
        self._status = ttk.Label(self, style="Muted.TLabel", padding=(8, 0, 8, 6))
        self._status.pack(anchor="w")
        self._list_width = 230 + sum(width for _key, _title, width in adapter.columns) + 24
        body.bind("<Configure>", lambda _e: self._place_sash(body), add="+")
        self.reload()

    def _place_sash(self, body: ttk.PanedWindow) -> None:
        """Open the list wide enough for its columns (at most half the page), once."""
        if self._list_width and body.winfo_width() > 1:
            body.sashpos(0, min(self._list_width, body.winfo_width() // 2))
            self._list_width = 0

    # -- list -------------------------------------------------------------------------
    def reload(self, select: str | None = None) -> bool:
        keep = select if select is not None else self._current
        try:
            self._groups = self.adapter.load()
        except Exception as exc:  # noqa: BLE001 - unreadable or missing project data: say so on the page
            self._groups = []
            self._items = {}
            self._fill()
            self.set_status(f"Could not read {self.adapter.source or 'the data'}: {exc}")
            return False
        self._items = {item.key: item for group in self._groups for item in group.items}
        self._fill()
        self.set_status(self.adapter.summary())
        self._current = keep if keep in self._items else None
        if self._current is not None and self._tree.exists(self._current):
            self._select_row(self._current)
        self.adapter.show(self._current)
        self.refresh_buttons()
        return True

    def refresh_from_archive(self) -> bool:
        return self.reload()

    def _refresh(self) -> None:
        """Reread the files (another page may have changed them); asks first about unsaved changes."""
        if self._confirm_discard() and self.adapter.leave():
            self.reload()

    def _fill(self) -> None:
        query = self._query.get().strip().casefold()
        self._selecting = True
        self._tree.delete(*self._tree.get_children())
        flat = len(self._groups) == 1
        for group in self._groups:
            items = [item for item in group.items if not query or query in item.key.casefold()
                     or query in item.label.casefold() or any(query in str(v).casefold() for v in item.values)]
            if query and not items:
                continue
            parent = ""
            if not flat:
                parent = "group:" + group.key
                self._tree.insert("", "end", iid=parent, text=group.label,
                                  values=(group.info,) + ("",) * (len(self.adapter.columns) - 1),
                                  open=bool(query) or len(self._groups) <= 2)
            for item in items:
                self._tree.insert(parent, "end", iid=item.key, text=item.label or item.key, values=item.values)
        if self._current and self._tree.exists(self._current):
            self._select_row(self._current)
        self._selecting = False

    def _select_row(self, key: str) -> None:
        parent = self._tree.parent(key)
        if parent:
            self._tree.item(parent, open=True)
        self._selecting = True
        self._tree.selection_set(key)
        self._tree.see(key)
        self._selecting = False

    def selected(self) -> str | None:
        return self._current

    def select(self, key: str | None) -> None:
        """Show ``key`` as if the user picked it."""
        if key is not None and self._tree.exists(key):
            self._select_row(key)
        self._current = key if key in self._items else None
        self.adapter.show(self._current)
        self.refresh_buttons()

    def _on_select(self) -> None:
        if self._selecting:
            return
        selection = self._tree.selection()
        key = selection[0] if selection and selection[0] in self._items else None
        if key == self._current or (key is None and selection):
            return  # a group row: keep the item on show
        if not self.adapter.leave():
            if self._current and self._tree.exists(self._current):
                self._select_row(self._current)
            else:
                self._selecting = True
                self._tree.selection_remove(*selection)
                self._selecting = False
            return
        self._current = key
        self.adapter.show(key)
        self.refresh_buttons()

    # -- saving -------------------------------------------------------------------------
    @property
    def dirty(self) -> bool:
        return self.adapter.dirty

    def refresh_buttons(self) -> None:
        state = "normal" if self.adapter.dirty else "disabled"
        for button in (self._save_button, self._discard_button):
            if button is not None:
                button.configure(state=state)

    def save(self) -> bool:
        ok = self.adapter.save()
        self.refresh_buttons()
        return ok

    def _discard(self) -> None:
        if self.adapter.dirty and not messagebox.askyesno(
                "Unsaved changes", f"Discard the unsaved {self.display_name.lower()} changes?", parent=self):
            return
        self.adapter.discard()
        self.reload()

    def _confirm_discard(self) -> bool:
        if not self.adapter.dirty:
            return True
        answer = messagebox.askyesnocancel(
            "Unsaved changes", f"Save the {self.display_name.lower()} changes before leaving?", parent=self)
        if answer is None:
            return False
        if answer:
            return self.save()
        self.adapter.discard()
        return True

    def set_status(self, text: str) -> None:
        self._status.configure(text=text)

    def cleanup(self) -> None:
        self.adapter.cleanup()
        parent_cleanup = getattr(super(), "cleanup", None)
        if parent_cleanup is not None:
            parent_cleanup()
