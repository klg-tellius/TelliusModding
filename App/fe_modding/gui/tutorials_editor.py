"""Tutorials editor: ``tut_data_en.bin`` (see :mod:`fe_modding.formats.tut_data`).

Each tutorial is a row of the in-game tutorial list: its title message, the script function that
plays it, the group it falls under in each of the list's three sort modes (chapter, category,
initial), its place in the list, and whether a new game starts with it unlocked or already
learned on each difficulty.
"""

from __future__ import annotations

import tkinter as tk
from tkinter import messagebox, ttk
from typing import Optional

from ..formats import tut_data as td
from ..project import ModProject
from .changelog import ChangeLog
from .editor_panel import EditorPanel
from .message_reference import message_texts, preview

#: The file each build reads (the US game loads the English list).
FILE_NAMES = ("tut_data_en.bin", "tut_data.bin")
#: Tutorial ids are bits of the party's 128-bit unlocked/learned masks.
MAX_ID = 127


class TutorialsEditor(EditorPanel):
    display_name = "Tutorials"

    def __init__(self, parent: tk.Misc, project: ModProject, changelog: ChangeLog):
        super().__init__(parent)
        self._project = project
        self._changelog = changelog
        folder = project.extracted_dir / "files"
        self._path = next((folder / n for n in FILE_NAMES if (folder / n).is_file()), folder / FILE_NAMES[0])
        self._data: Optional[td.TutData] = None
        self._texts: dict[str, str] = {}
        self._index: Optional[int] = None
        self._dirty = False
        self._loading = False
        self._build_widgets()
        self._load()

    # -- layout -----------------------------------------------------------------------------
    def _build_widgets(self) -> None:
        bar = ttk.Frame(self, padding=(8, 8, 8, 4))
        bar.pack(fill="x")
        self._save_button = ttk.Button(bar, text="Save tutorials", style="Accent.TButton", command=self.save,
                                       state="disabled")
        self._save_button.pack(side="left")
        ttk.Button(bar, text="Revert", command=self._revert).pack(side="left", padx=(6, 0))
        self._status = ttk.Label(bar, text="", style="Muted.TLabel")
        self._status.pack(side="left", padx=(10, 0))
        ttk.Label(self, style="Muted.TLabel", wraplength=1000, justify="left", padding=(8, 2), text=(
            "The in-game tutorial list (pause menu). Each tutorial plays a function of an event script; the list "
            "sorts it by chapter, category or initial (group 0 never shows as a group) and by its order number. "
            "The start flags say whether a new game begins with the tutorial unlocked and already learned, per "
            "difficulty. The id is the tutorial's bit in the save (0-127).")).pack(fill="x")
        body = ttk.Frame(self, padding=8)
        body.pack(fill="both", expand=True)
        left = ttk.Frame(body)
        left.pack(side="left", fill="both", expand=True)
        columns = ("id", "order", "title", "function")
        self._tree = ttk.Treeview(left, columns=columns, show="headings", selectmode="browse", height=24)
        for column, text, width in zip(columns, ("Id", "Order", "Title", "Function"), (40, 50, 260, 200)):
            self._tree.heading(column, text=text)
            self._tree.column(column, width=width, anchor="e" if column in ("id", "order") else "w",
                              stretch=column == "title")
        scroll = ttk.Scrollbar(left, orient="vertical", command=self._tree.yview)
        self._tree.configure(yscrollcommand=scroll.set)
        self._tree.pack(side="left", fill="both", expand=True)
        scroll.pack(side="left", fill="y")
        self._tree.bind("<<TreeviewSelect>>", lambda e: self._on_select())

        form = ttk.Frame(body, padding=(12, 0, 0, 0))
        form.pack(side="left", fill="y")
        self._vars: dict[str, tk.StringVar] = {}
        self._boxes: dict[str, ttk.Combobox] = {}
        rows = (("id", "Id"), ("title_key", "Title message"), ("script", "Script file"),
                ("function", "Script function"), ("order", "Order in the list"),
                ("chapter", "Chapter group"), ("category", "Category group"), ("initial", "Initial group"))
        for r, (key, label) in enumerate(rows):
            ttk.Label(form, text=label).grid(row=r, column=0, sticky="w", pady=2)
            var = tk.StringVar()
            if key in ("chapter", "category", "initial"):
                widget = ttk.Combobox(form, textvariable=var, state="readonly", width=34)
                widget.bind("<<ComboboxSelected>>", lambda e: self._apply())
                self._boxes[key] = widget
            else:
                widget = ttk.Entry(form, textvariable=var, width=36)
                for event in ("<Return>", "<FocusOut>"):
                    widget.bind(event, lambda e: self._apply())
            widget.grid(row=r, column=1, sticky="w", padx=(6, 0), pady=2)
            self._vars[key] = var
        self._title_text = ttk.Label(form, text="", style="Muted.TLabel", wraplength=300, justify="left")
        self._title_text.grid(row=len(rows), column=0, columnspan=2, sticky="w", pady=(2, 8))
        flags = ttk.Frame(form)
        flags.grid(row=len(rows) + 1, column=0, columnspan=2, sticky="w")
        ttk.Label(flags, text="New game starts with it").grid(row=0, column=0, sticky="w")
        ttk.Label(flags, text="unlocked").grid(row=0, column=1, padx=6)
        ttk.Label(flags, text="learned").grid(row=0, column=2, padx=6)
        self._flags: list[tuple[tk.BooleanVar, tk.BooleanVar]] = []
        for i, name in enumerate(td.DIFFICULTIES):
            ttk.Label(flags, text=f"  {name}").grid(row=i + 1, column=0, sticky="w")
            pair = (tk.BooleanVar(), tk.BooleanVar())
            for c, var in enumerate(pair):
                ttk.Checkbutton(flags, variable=var, command=self._apply).grid(row=i + 1, column=c + 1)
            self._flags.append(pair)
        buttons = ttk.Frame(form)
        buttons.grid(row=len(rows) + 2, column=0, columnspan=2, sticky="w", pady=(10, 0))
        ttk.Button(buttons, text="Duplicate", command=self._duplicate).pack(side="left", padx=(0, 4))
        ttk.Button(buttons, text="Remove", command=self._remove).pack(side="left")

    # -- data -------------------------------------------------------------------------------
    def _load(self) -> None:
        self._texts = message_texts(self._project)
        try:
            self._data = td.read_tut_data_path(self._path)
            self._status.config(text=f"{self._path.name}: {len(self._data.entries)} tutorials")
        except (OSError, ValueError) as exc:
            self._data = None
            self._status.config(text=f"Could not read {self._path.name}: {exc}")
        if self._data:
            for key, labels in (("chapter", self._data.chapters), ("category", self._data.categories),
                                ("initial", self._data.initials)):
                self._boxes[key].config(values=[self._label(i, k) for i, k in enumerate(labels)])
        self._set_dirty(False)
        self._fill(0 if self._data and self._data.entries else None)

    def _label(self, index: int, key: str) -> str:
        text = preview(self._texts.get(key, ""))
        return f"{index}: {key}" + (f" ({text})" if text else "")

    def _title(self, entry: td.TutorialEntry) -> str:
        return preview(self._texts.get(entry.title_key, "")) or entry.title_key

    def _fill(self, select: Optional[int]) -> None:
        self._tree.delete(*self._tree.get_children())
        for i, e in enumerate(self._data.entries if self._data else []):
            self._tree.insert("", "end", iid=str(i), values=(e.id, e.order, self._title(e), e.function))
        self._index = None
        if select is not None and self._data and self._data.entries:
            select = max(0, min(select, len(self._data.entries) - 1))
            self._tree.selection_set(str(select))
            self._tree.see(str(select))
            self._on_select()

    def _set_dirty(self, dirty: bool) -> None:
        self._dirty = dirty
        self._save_button.config(state="normal" if dirty else "disabled")
        if dirty:
            self._status.config(text="Unsaved changes")

    def _current(self) -> Optional[td.TutorialEntry]:
        return self._data.entries[self._index] if self._data and self._index is not None else None

    def _on_select(self) -> None:
        selection = self._tree.selection()
        self._index = int(selection[0]) if selection else None
        e = self._current()
        if e is None:
            return
        self._loading = True
        try:
            for key in ("id", "title_key", "script", "function", "order"):
                self._vars[key].set(str(getattr(e, key)))
            for key, labels in (("chapter", self._data.chapters), ("category", self._data.categories),
                                ("initial", self._data.initials)):
                value = getattr(e, key)
                self._vars[key].set(self._label(value, labels[value]) if value < len(labels) else str(value))
            for (unlocked, learned), flag in zip(self._flags, e.start_flags):
                unlocked.set(bool(flag & td.UNLOCKED))
                learned.set(bool(flag & td.LEARNED))
            self._title_text.config(text=self._texts.get(e.title_key, "(no text for this message key)"))
        finally:
            self._loading = False

    def _apply(self) -> None:
        e = self._current()
        if self._loading or e is None:
            return
        try:
            new_id, order = int(self._vars["id"].get()), int(self._vars["order"].get())
            if not 0 <= new_id <= MAX_ID or not -128 <= order <= 127:
                raise ValueError
            if any(o is not e and o.id == new_id for o in self._data.entries):
                messagebox.showerror("Duplicate id", f"Another tutorial already uses id {new_id}.", parent=self)
                self._on_select()
                return
            groups = {k: int(self._vars[k].get().split(":", 1)[0]) for k in ("chapter", "category", "initial")}
            texts = {k: self._vars[k].get().strip() for k in ("title_key", "script", "function")}
            for value in texts.values():
                value.encode(td.ENCODING)
        except (ValueError, UnicodeEncodeError):
            messagebox.showerror("Invalid value", f"The id is 0-{MAX_ID}, the order -128 to 127, and the texts "
                                 "Shift-JIS.", parent=self)
            self._on_select()
            return
        flags = [(td.UNLOCKED if u.get() else 0) | (td.LEARNED if l.get() else 0) for u, l in self._flags]
        before = (e.id, e.order, e.chapter, e.category, e.initial, e.title_key, e.script, e.function, e.start_flags)
        e.id, e.order = new_id, order
        e.chapter, e.category, e.initial = groups["chapter"], groups["category"], groups["initial"]
        e.title_key, e.script, e.function = texts["title_key"], texts["script"], texts["function"]
        e.start_flags = flags
        after = (e.id, e.order, e.chapter, e.category, e.initial, e.title_key, e.script, e.function, e.start_flags)
        if after != before:
            self._tree.item(str(self._index), values=(e.id, e.order, self._title(e), e.function))
            self._title_text.config(text=self._texts.get(e.title_key, "(no text for this message key)"))
            self._set_dirty(True)

    def _duplicate(self) -> None:
        e = self._current()
        if e is None:
            return
        used = {o.id for o in self._data.entries}
        free = next((i for i in range(1, MAX_ID + 1) if i not in used), None)
        if free is None:
            messagebox.showerror("No free id", f"All {MAX_ID} tutorial ids are used.", parent=self)
            return
        copy = td.TutorialEntry(free, e.category, e.chapter, max(o.order for o in self._data.entries) + 1,
                                e.initial, list(e.start_flags), e.title_key, e.script, e.function)
        self._data.entries.append(copy)
        self._set_dirty(True)
        self._fill(len(self._data.entries) - 1)

    def _remove(self) -> None:
        if self._current() is None:
            return
        del self._data.entries[self._index]
        self._set_dirty(True)
        self._fill(self._index)

    # -- save -------------------------------------------------------------------------------
    def save(self) -> bool:
        if self._data is None:
            return False
        try:
            self._project.write_keeping_original(self._path, td.build_tut_data(self._data))
        except (OSError, ValueError) as exc:
            messagebox.showerror(f"Could not save {self._path.name}", str(exc), parent=self)
            return False
        self._changelog.append(self._path.name, f"Saved {len(self._data.entries)} tutorials")
        self._set_dirty(False)
        self._status.config(text=f"Saved {self._path.name}")
        return True

    def _revert(self) -> None:
        if self._dirty and not self._confirm_discard():
            return
        self._load()

    def _confirm_discard(self) -> bool:
        return messagebox.askyesno("Discard changes?", "The tutorials have unsaved changes. Discard them?",
                                   parent=self)
