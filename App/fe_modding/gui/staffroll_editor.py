"""Staff Credits editor: ``ending/staffroll_noa.bin`` (see :mod:`fe_modding.formats.staffroll`).

The credits scroll one line every 48 units; each line has three optional columns: a role drawn
right-aligned to the screen's middle, a centred heading (with its own ``#F`` font code, e.g.
``#F04Movie``) and a name drawn left-aligned after the middle.
"""

from __future__ import annotations

import tkinter as tk
from tkinter import messagebox, ttk
from typing import Optional

from ..formats import fe10_staffroll as fs, staffroll
from ..project import ModProject
from .changelog import ChangeLog
from .editor_panel import EditorPanel
from .widgets import tip
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
        self._path = self._find_path()
        self._roll: Optional[staffroll.StaffRoll] = None
        self._index: Optional[int] = None
        self._dirty = False
        self._loading = False
        self._build_widgets()
        self._load()

    # -- per-game hooks (Radiant Dawn: Fe10StaffRollEditor) ----------------------------------
    intro = ("The staff credits that scroll at the end of the game, one line at a time. Each line has up to three "
             "columns: a role (drawn right-aligned up to the middle of the screen), a centred heading (it carries "
             "its own font code, such as #F04Movie) and a name (drawn left-aligned after the middle). A line with "
             "all three empty is a blank line. The US game plays staffroll_noa.bin; staffroll.bin is the "
             "Japanese list.")

    def _find_path(self):
        folder = files_root_of(self._project) / "ending"
        return next((folder / n for n in FILE_NAMES if (folder / n).is_file()), folder / FILE_NAMES[0])

    def _read(self):
        return staffroll.read_staffroll_path(self._path)

    def _write(self) -> None:
        self._project.write_keeping_original(self._path, staffroll.build_staffroll(self._roll))

    def _build_extra(self, parent) -> None:
        """Controls below the line form (none on Path of Radiance)."""

    def _build_widgets(self) -> None:
        bar = ttk.Frame(self, padding=(8, 8, 8, 4))
        bar.pack(fill="x")
        self._save_button = ttk.Button(bar, text="Save credits", style="Accent.TButton", command=self.save,
                                       state="disabled")
        self._save_button.pack(side="left")
        ttk.Button(bar, text="Revert", command=self._revert).pack(side="left", padx=(6, 0))
        self._status = ttk.Label(bar, text="", style="Muted.TLabel")
        self._status.pack(side="left", padx=(10, 0))
        ttk.Label(self, style="Muted.TLabel", wraplength=1000, justify="left", padding=(8, 2),
                  text=self.intro).pack(fill="x")
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
        extra = ttk.Frame(right)
        extra.grid(row=len(COLUMNS) + 1, column=0, columnspan=2, sticky="w", pady=(16, 0))
        self._build_extra(extra)

    # -- data -------------------------------------------------------------------------------
    def _load(self) -> None:
        try:
            self._roll = self._read()
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

    def _text_encoding(self) -> str:
        """The text table a typed line must fit (Shift-JIS on Path of Radiance)."""
        return staffroll.ENCODING

    def _apply(self) -> None:
        if self._loading or self._index is None or self._roll is None:
            return
        line = tuple(var.get() for var in self._vars)
        try:
            for value in line:
                value.encode(self._text_encoding())
        except UnicodeEncodeError:
            messagebox.showerror("Invalid text", "A character is not in the credits' text table.", parent=self)
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
            self._write()
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


#: Radiant Dawn's ending message files the page edits, by language prefix (``Mess/%s%s.m``); the European
#: ones only exist on the European disc.
RD_LANGUAGES = (("e_", "English"), ("", "Japanese"), ("d_", "German"), ("f_", "French"), ("s_", "Spanish"),
                ("i_", "Italian"))


class Fe10StaffRollEditor(StaffRollEditor):
    """Radiant Dawn: the same line list over ``Mess/<lang>ending.m`` (:mod:`..formats.fe10_staffroll`),
    with the roll's title, its copyright lines and ``StaffRollData.bin``'s timings."""

    intro = ("The staff credits that scroll at the end of the game, one line at a time. Each line has up to three "
             "columns: a role, a centred heading and a name; a line with all three empty is a blank line. The "
             "US game plays Mess/e_ending.m (English); Mess/ending.m is the Japanese list. The title, the "
             "copyright lines and the roll's timings (StaffRollData.bin) are below the line form.")

    def __init__(self, parent: tk.Misc, project: ModProject, changelog: ChangeLog):
        self._language = tk.StringVar(master=parent)
        self._title_var = tk.StringVar(master=parent)
        self._copy_vars = [tk.StringVar(master=parent) for _ in fs.COPYRIGHT]
        self._timing_vars = {label: tk.StringVar(master=parent) for label in fs.TIMINGS}
        self._timings: dict = {}
        super().__init__(parent, project, changelog)

    def _languages(self) -> list[tuple[str, str]]:
        mess = files_root_of(self._project) / "Mess"
        return [(prefix, name) for prefix, name in RD_LANGUAGES if (mess / f"{prefix}ending.m").is_file()]

    def _find_path(self):
        mess = files_root_of(self._project) / "Mess"
        languages = self._languages() or [RD_LANGUAGES[0]]
        prefix = next((p for p, name in languages if name == self._language.get()), languages[0][0])
        self._language.set(dict(RD_LANGUAGES)[prefix])
        return mess / f"{prefix}ending.m"

    def _data_path(self):
        return files_root_of(self._project) / "StaffRollData.bin"

    def _text_encoding(self) -> str:
        from ..formats import fe10_message
        from ..game_profile import disc_root_of
        from ..games import read_disc_id
        try:
            disc = read_disc_id(disc_root_of(self._project))
        except Exception:  # noqa: BLE001 - no readable boot.bin
            disc = ""
        return fe10_message.encoding_for(self._path.name, disc)

    def _read(self):
        roll = fs.read_rd_staffroll(self._path.read_bytes(), self._text_encoding())
        self._title_var.set(roll.title)
        for var, text in zip(self._copy_vars, roll.copyright):
            var.set(text)
        try:
            self._timings = fs.read_timings(self._data_path().read_bytes())
        except (OSError, ValueError):
            self._timings = {}
        for label, var in self._timing_vars.items():
            value = self._timings.get(label)
            var.set("" if value is None else (f"{value:g}" if isinstance(value, float) else str(value)))
        return roll

    def _write(self) -> None:
        self._roll.title = self._title_var.get()
        self._roll.copyright = [var.get() for var in self._copy_vars]
        self._project.write_keeping_original(self._path, fs.build_rd_staffroll(self._roll, self._text_encoding()))
        if self._timings:
            data = self._data_path().read_bytes()
            new = data
            for label, var in self._timing_vars.items():
                text = var.get().strip()
                fmt = fs.TIMINGS[label][0]
                try:
                    value = float(text) if fmt == ">f" else int(text, 0)
                except ValueError as exc:
                    raise ValueError(f"{fs.TIMINGS[label][1]} must be a number.") from exc
                if value != self._timings[label]:
                    new = fs.set_timing(new, label, value)
            if new != data:
                self._project.write_keeping_original(self._data_path(), new)

    def _build_extra(self, parent) -> None:
        row = 0
        ttk.Label(parent, text="Language").grid(row=row, column=0, sticky="w", pady=2)
        box = ttk.Combobox(parent, textvariable=self._language, values=[name for _p, name in self._languages()],
                           state="readonly", width=14)
        box.grid(row=row, column=1, sticky="w", padx=(6, 0), pady=2)
        box.bind("<<ComboboxSelected>>", lambda e: self._switch_language())
        row += 1
        ttk.Label(parent, text="Title").grid(row=row, column=0, sticky="w", pady=2)
        title = ttk.Entry(parent, textvariable=self._title_var, width=36)
        title.grid(row=row, column=1, sticky="w", padx=(6, 0), pady=2)
        title.bind("<KeyRelease>", lambda e: self._set_dirty(True))
        row += 1
        for n, var in enumerate(self._copy_vars, 1):
            ttk.Label(parent, text=f"Copyright {n}").grid(row=row, column=0, sticky="w", pady=2)
            entry = ttk.Entry(parent, textvariable=var, width=36)
            entry.grid(row=row, column=1, sticky="w", padx=(6, 0), pady=2)
            entry.bind("<KeyRelease>", lambda e: self._set_dirty(True))
            row += 1
        ttk.Label(parent, text="Timings (StaffRollData.bin)", style="Muted.TLabel").grid(
            row=row, column=0, columnspan=2, sticky="w", pady=(10, 2))
        row += 1
        for label, (_fmt, meaning) in fs.TIMINGS.items():
            tip(ttk.Label(parent, text=meaning), label).grid(row=row, column=0, sticky="w", pady=1)
            entry = ttk.Entry(parent, textvariable=self._timing_vars[label], width=12)
            entry.grid(row=row, column=1, sticky="w", padx=(6, 0), pady=1)
            entry.bind("<KeyRelease>", lambda e: self._set_dirty(True))
            row += 1
        ttk.Label(parent, style="Muted.TLabel", wraplength=320, justify="left", text=(
            "Times are in the game's units (milliseconds in the retail values). The four SOUND values are below "
            "the line count; what they do has not been traced.")).grid(row=row, column=0, columnspan=2,
                                                                       sticky="w", pady=(4, 0))

    def _switch_language(self) -> None:
        if self._dirty and not self._confirm_discard():
            return
        self._path = self._find_path()
        self._load()


def staff_credits_panel(parent, project, changelog):
    """The Staff Credits page of the project's game (Radiant Dawn's ending message file or Path of
    Radiance's staffroll list)."""
    cls = Fe10StaffRollEditor if project.profile.message_dialect == "fe10" else StaffRollEditor
    return cls(parent, project, changelog)
