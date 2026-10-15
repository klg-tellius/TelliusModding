"""Sound Room tracks editor: the 64 music cues of the Sound Room menu.

The list is a table in ``sys/main.dol`` (see :mod:`fe_modding.game_code.sound_room_tracks`), so
it is saved into the executable; the Game Code page and the chapter pages edit the same file and
reread it whenever they are shown. The pictures behind the menu are the Soundroom Images panel.
"""

from __future__ import annotations

import tkinter as tk
from tkinter import messagebox, ttk
from typing import Optional

from ..formats import gcfesnd
from ..game_code import sound_room_tracks as tracks
from ..game_code.dol import Dol
from ..game_code.versions import identify, read_boot_code
from ..project import ModProject
from .changelog import ChangeLog
from .editor_panel import EditorPanel


class SoundRoomTracksEditor(EditorPanel):
    display_name = "Sound Room Tracks"

    def __init__(self, parent: tk.Misc, project: ModProject, changelog: ChangeLog):
        super().__init__(parent)
        self._project = project
        self._changelog = changelog
        self._path = project.extracted_dir / "sys" / "main.dol"
        self._version: Optional[str] = None
        self._names: list[str] = []
        self._index: Optional[int] = None
        self._dirty = False
        self._loading = False
        self._build_widgets()
        self._load()

    # -- layout ---------------------------------------------------------------------------
    def _build_widgets(self) -> None:
        bar = ttk.Frame(self, padding=(8, 8, 8, 4))
        bar.pack(fill="x")
        self._save_button = ttk.Button(bar, text="Save tracks", style="Accent.TButton", command=self.save,
                                       state="disabled")
        self._save_button.pack(side="left")
        ttk.Button(bar, text="Revert", command=self._revert).pack(side="left", padx=(6, 0))
        self._status = ttk.Label(bar, text="", style="Muted.TLabel")
        self._status.pack(side="left", padx=(10, 0))
        ttk.Label(self, style="Muted.TLabel", wraplength=1000, justify="left", padding=(8, 2), text=(
            f"The {tracks.TRACK_COUNT} music cues listed in the Sound Room menu, in menu order. The list lives in "
            "the game code (sys/main.dol) and always has 64 entries; the names share a fixed amount of space, so a "
            "longer name needs shorter ones elsewhere (a track listed twice is stored once). Any BGM cue of "
            "Sound/gcfesnd.bin works, including ones added on the Music page.")).pack(fill="x")

        body = ttk.Frame(self, padding=8)
        body.pack(fill="both", expand=True)
        left = ttk.Frame(body)
        left.pack(side="left", fill="y", padx=(0, 12))
        columns = ("n", "name")
        self._tree = ttk.Treeview(left, columns=columns, show="headings", selectmode="browse", height=24)
        for column, text, width in zip(columns, ("#", "Cue"), (34, 260)):
            self._tree.heading(column, text=text)
            self._tree.column(column, width=width, anchor="e" if column == "n" else "w", stretch=False)
        scroll = ttk.Scrollbar(left, orient="vertical", command=self._tree.yview)
        self._tree.configure(yscrollcommand=scroll.set)
        self._tree.pack(side="left", fill="y")
        scroll.pack(side="left", fill="y")
        self._tree.bind("<<TreeviewSelect>>", lambda e: self._on_select())

        right = ttk.Frame(body)
        right.pack(side="left", fill="both", expand=True)
        ttk.Label(right, text="Cue").grid(row=0, column=0, sticky="w")
        self._name_var = tk.StringVar()
        self._name_box = ttk.Combobox(right, textvariable=self._name_var, width=36)
        self._name_box.grid(row=0, column=1, sticky="w", padx=(6, 0))
        for event in ("<<ComboboxSelected>>", "<Return>", "<FocusOut>"):
            self._name_box.bind(event, lambda e: self._apply())
        buttons = ttk.Frame(right)
        buttons.grid(row=1, column=0, columnspan=2, sticky="w", pady=(8, 0))
        ttk.Button(buttons, text="▲", width=3, command=lambda: self._move(-1)).pack(side="left", padx=(0, 4))
        ttk.Button(buttons, text="▼", width=3, command=lambda: self._move(1)).pack(side="left")
        self._space = ttk.Label(right, text="", style="Muted.TLabel")
        self._space.grid(row=2, column=0, columnspan=2, sticky="w", pady=(10, 0))

    # -- data -----------------------------------------------------------------------------
    def _open(self) -> tuple[Dol, str]:
        dol = Dol.open(self._path)
        version = identify(dol, read_boot_code(self._project.extracted_dir)).version
        if version is None or version.code not in tracks.LAYOUT:
            raise ValueError("This main.dol is not a known Path of Radiance build.")
        return dol, version.code

    def _load(self) -> None:
        self._loading = True
        try:
            try:
                cues = gcfesnd.read_bgm_cues_path(self._project.extracted_dir / "files" / "Sound" / "gcfesnd.bin")
                self._name_box.config(values=sorted({c.name for c in cues}))
            except Exception:  # noqa: BLE001 - the suggestions are optional
                self._name_box.config(values=[])
            try:
                dol, self._version = self._open()
                self._names = tracks.read_tracks(dol, self._version)
            except Exception as exc:  # noqa: BLE001
                self._version, self._names = None, []
                self._status.config(text=f"Could not read the track list: {exc}")
            self._set_dirty(False)
            self._fill(0 if self._names else None)
        finally:
            self._loading = False

    def _fill(self, select: Optional[int]) -> None:
        self._tree.delete(*self._tree.get_children())
        for i, name in enumerate(self._names):
            self._tree.insert("", "end", iid=str(i), values=(i + 1, name))
        self._index = None
        if select is not None:
            self._tree.selection_set(str(select))
            self._tree.see(str(select))
            self._on_select()
        self._show_space()

    def _show_space(self) -> None:
        if self._version is None:
            self._space.config(text="")
            return
        used, room = tracks.packed_size(self._names), tracks.capacity(self._version)
        self._space.config(text=f"Name space: {used} of {room} bytes", style="Warn.TLabel" if used > room
                           else "Muted.TLabel")

    def _set_dirty(self, dirty: bool) -> None:
        self._dirty = dirty
        self._save_button.config(state="normal" if dirty else "disabled")
        if dirty:
            self._status.config(text="Unsaved changes")
        elif self._version:
            self._status.config(text=f"{len(self._names)} tracks ({self._version})")

    # -- edits ----------------------------------------------------------------------------
    def _on_select(self) -> None:
        selection = self._tree.selection()
        self._index = int(selection[0]) if selection else None
        self._loading = True
        try:
            self._name_var.set(self._names[self._index] if self._index is not None else "")
        finally:
            self._loading = False

    def _apply(self) -> None:
        if self._loading or self._index is None:
            return
        name = self._name_var.get().strip()
        if not name or name == self._names[self._index]:
            return
        if not (name.isascii() and name.isprintable()):
            messagebox.showerror("Invalid name", "A cue name is plain ASCII text, such as BGM_MAP01_ROOM.", parent=self)
            self._name_var.set(self._names[self._index])
            return
        self._names[self._index] = name
        self._tree.item(str(self._index), values=(self._index + 1, name))
        self._set_dirty(True)
        self._show_space()

    def _move(self, step: int) -> None:
        i = self._index
        if i is None or not 0 <= i + step < len(self._names):
            return
        self._names[i], self._names[i + step] = self._names[i + step], self._names[i]
        self._set_dirty(True)
        self._fill(i + step)

    # -- save -----------------------------------------------------------------------------
    def save(self) -> bool:
        if not self._names:
            return False
        try:
            dol, version = self._open()        # reread: other pages may have changed main.dol since
            tracks.write_tracks(dol, version, self._names)
            self._project.write_keeping_original(self._path, bytes(dol.data))
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror("Could not save the Sound Room tracks", str(exc), parent=self)
            return False
        self._changelog.append("main.dol", "Saved the Sound Room track list")
        self._set_dirty(False)
        return True

    def _revert(self) -> None:
        if self._dirty and not self._confirm_discard():
            return
        self._load()

    def _confirm_discard(self) -> bool:
        return messagebox.askyesno("Discard changes?", "The Sound Room track list has unsaved changes. Discard them?",
                                   parent=self)
