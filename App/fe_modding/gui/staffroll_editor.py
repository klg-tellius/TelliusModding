"""Staff Credits editor: ``ending/staffroll_noa.bin`` (see :mod:`fe_modding.formats.staffroll`).

The credits scroll one line every 48 units; each line has three optional columns: a role drawn
right-aligned to the screen's middle, a centred heading (with its own ``#F`` font code, e.g.
``#F04Movie``) and a name drawn left-aligned after the middle.
"""

from __future__ import annotations

import tkinter as tk
from tkinter import messagebox, ttk
from typing import Optional

from ..formats import staffroll
from ..project import ModProject
from .changelog import ChangeLog
from .editor_panel import EditorPanel
from ..game_profile import files_root_of

#: The file each build plays (the US game loads only the NOA list).
FILE_NAMES = ("staffroll_noa.bin", "staffroll.bin")
COLUMNS = ("Role", "Heading", "Name")


class StaffRollEditor(EditorPanel):
    display_name = "Staff Credits"

    def __init__(self, parent: tk.Misc, project: ModProject, changelog: ChangeLog):
        super().__init__(parent)
        self._project = project
        self._changelog = changelog
        folder = files_root_of(project) / "ending"
        self._path = next((folder / n for n in FILE_NAMES if (folder / n).is_file()), folder / FILE_NAMES[0])
        self._roll: Optional[staffroll.StaffRoll] = None
        self._index: Optional[int] = None
        self._dirty = False
        self._loading = False
        self._build_widgets()
        self._load()

    def _build_widgets(self) -> None:
        bar = ttk.Frame(self, padding=(8, 8, 8, 4))
        bar.pack(fill="x")
        self._save_button = ttk.Button(bar, text="Save credits", style="Accent.TButton", command=self.save,
                                       state="disabled")
        self._save_button.pack(side="left")
        ttk.Button(bar, text="Revert", command=self._revert).pack(side="left", padx=(6, 0))
        self._status = ttk.Label(bar, text="", style="Muted.TLabel")
        self._status.pack(side="left", padx=(10, 0))
        ttk.Label(self, style="Muted.TLabel", wraplength=1000, justify="left", padding=(8, 2), text=(
            "The staff credits that scroll at the end of the game, one line at a time. Each line has up to three "
            "columns: a role (drawn right-aligned up to the middle of the screen), a centred heading (it carries "
            "its own font code, such as #F04Movie) and a name (drawn left-aligned after the middle). A line with "
            "all three empty is a blank line. The US game plays staffroll_noa.bin; staffroll.bin is the "
            "Japanese list.")).pack(fill="x")
        body = ttk.Frame(self, padding=8)
        body.pack(fill="both", expand=True)
        left = ttk.Frame(body)
        left.pack(side="left", fill="both", expand=True)
        columns = ("n", *COLUMNS)
        self._tree = ttk.Treeview(left, columns=columns, show="headings", selectmode="browse", height=24)
        for column, width in zip(columns, (40, 220, 200, 240)):
            self._tree.heading(column, text="#" if column == "n" else column)
            self._tree.column(column, width=width, anchor="e" if column == "n" else "w", stretch=column != "n")
        scroll = ttk.Scrollbar(left, orient="vertical", command=self._tree.yview)
        self._tree.configure(yscrollcommand=scroll.set)
        self._tree.pack(side="left", fill="both", expand=True)
        scroll.pack(side="left", fill="y")
        self._tree.bind("<<TreeviewSelect>>", lambda e: self._on_select())

        right = ttk.Frame(body, padding=(12, 0, 0, 0))
        right.pack(side="left", fill="y")
        self._vars = []
        for row, label in enumerate(COLUMNS):
            ttk.Label(right, text=label).grid(row=row, column=0, sticky="w", pady=2)
            var = tk.StringVar()
            entry = ttk.Entry(right, textvariable=var, width=36)
            entry.grid(row=row, column=1, sticky="w", padx=(6, 0), pady=2)
            for event in ("<Return>", "<FocusOut>"):
                entry.bind(event, lambda e: self._apply())
            self._vars.append(var)
        buttons = ttk.Frame(right)
        buttons.grid(row=len(COLUMNS), column=0, columnspan=2, sticky="w", pady=(10, 0))
        for text, command in (("▲", lambda: self._move(-1)), ("▼", lambda: self._move(1)),
                              ("Insert line", self._insert), ("Remove", self._remove)):
            ttk.Button(buttons, text=text, width=3 if len(text) == 1 else None, command=command).pack(
                side="left", padx=(0, 4))

    # -- data -------------------------------------------------------------------------------
    def _load(self) -> None:
        try:
            self._roll = staffroll.read_staffroll_path(self._path)
            self._status.config(text=f"{self._path.name}: {len(self._roll.lines)} lines")
        except (OSError, ValueError) as exc:
            self._roll = None
            self._status.config(text=f"Could not read {self._path.name}: {exc}")
        self._set_dirty(False)
        self._fill(0 if self._roll and self._roll.lines else None)

    def _fill(self, select: Optional[int]) -> None:
        self._tree.delete(*self._tree.get_children())
        for i, line in enumerate(self._roll.lines if self._roll else []):
            self._tree.insert("", "end", iid=str(i), values=(i + 1, *line))
        self._index = None
        if select is not None and self._roll and self._roll.lines:
            select = max(0, min(select, len(self._roll.lines) - 1))
            self._tree.selection_set(str(select))
            self._tree.see(str(select))
            self._on_select()

    def _set_dirty(self, dirty: bool) -> None:
        self._dirty = dirty
        self._save_button.config(state="normal" if dirty else "disabled")
        if dirty:
            self._status.config(text="Unsaved changes")

    def _on_select(self) -> None:
        selection = self._tree.selection()
        self._index = int(selection[0]) if selection else None
        self._loading = True
        try:
            line = self._roll.lines[self._index] if self._index is not None else ("", "", "")
            for var, value in zip(self._vars, line):
                var.set(value)
        finally:
            self._loading = False

    def _apply(self) -> None:
        if self._loading or self._index is None or self._roll is None:
            return
        line = tuple(var.get() for var in self._vars)
        try:
            for value in line:
                value.encode(staffroll.ENCODING)
        except UnicodeEncodeError:
            messagebox.showerror("Invalid text", "The credits are Shift-JIS text.", parent=self)
            return
        if line != self._roll.lines[self._index]:
            self._roll.lines[self._index] = line
            self._tree.item(str(self._index), values=(self._index + 1, *line))
            self._set_dirty(True)

    def _move(self, step: int) -> None:
        i = self._index
        if self._roll is None or i is None or not 0 <= i + step < len(self._roll.lines):
            return
        lines = self._roll.lines
        lines[i], lines[i + step] = lines[i + step], lines[i]
        self._set_dirty(True)
        self._fill(i + step)

    def _insert(self) -> None:
        if self._roll is None:
            return
        at = 0 if self._index is None else self._index + 1
        self._roll.lines.insert(at, ("", "", ""))
        self._set_dirty(True)
        self._fill(at)

    def _remove(self) -> None:
        if self._roll is None or self._index is None:
            return
        del self._roll.lines[self._index]
        self._set_dirty(True)
        self._fill(self._index)

    # -- save -------------------------------------------------------------------------------
    def save(self) -> bool:
        if self._roll is None:
            return False
        try:
            self._project.write_keeping_original(self._path, staffroll.build_staffroll(self._roll))
        except (OSError, ValueError) as exc:
            messagebox.showerror(f"Could not save {self._path.name}", str(exc), parent=self)
            return False
        self._changelog.append(self._path.name, f"Saved {len(self._roll.lines)} staff credit lines")
        self._set_dirty(False)
        self._status.config(text=f"Saved {self._path.name}")
        return True

    def _revert(self) -> None:
        if self._dirty and not self._confirm_discard():
            return
        self._load()

    def _confirm_discard(self) -> bool:
        return messagebox.askyesno("Discard changes?", "The staff credits have unsaved changes. Discard them?",
                                   parent=self)
