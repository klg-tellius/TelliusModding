"""Saves: open a Path of Radiance ``.gci`` and edit every decoded part of a
save block (``formats/save_file.py``): party and chapter state, units,
convoy, forged weapons, map objects, flags and the shared system data.

Edits stay in memory until Save; writing re-encodes the block (the unit
list changes size, so later chunks move) and recomputes its checksum. Names
come from the project's FE8Data.bin and message texts; saves store table
numbers, so a project that reordered those tables shows other names."""

from __future__ import annotations

import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import Callable, Optional

from ... import script_sources
from ...formats import event_flags as ef
from ...formats import save_file as sf
from ...formats.cmb.parser import ParseError, parse
from .. import theme
from ..shell import Page
from ..widgets import ScrollFrame, section_header

ON, OFF = "☑", "☐"
TICKS_PER_SECOND = 162_000_000 // 4  # OSGetTime runs at the bus clock / 4
TABS = {"overview": "Overview", "units": "Units", "convoy": "Convoy", "forges": "Forges",
        "map": "Map objects", "flags": "Flags", "system": "System data", "raw": "Raw"}
RANGES = {"u8": (0, 0xFF), "s8": (-0x80, 0x7F), "u16": (0, 0xFFFF), "s16": (-0x8000, 0x7FFF),
          "u32": (0, 0xFFFFFFFF), "u64": (0, 0xFFFFFFFFFFFFFFFF)}


def _tree(parent: tk.Misc, columns: dict, height: int = 12) -> ttk.Treeview:
    frame = ttk.Frame(parent)
    frame.pack(fill="both", expand=True, pady=(6, 6))
    tree = ttk.Treeview(frame, columns=list(columns), show="headings", selectmode="browse", height=height)
    for key, (title, width, stretch) in columns.items():
        tree.heading(key, text=title)
        tree.column(key, width=width, stretch=stretch, anchor="w")
    scroll = ttk.Scrollbar(frame, command=tree.yview)
    tree.configure(yscrollcommand=scroll.set)
    scroll.pack(side="right", fill="y")
    tree.pack(side="left", fill="both", expand=True)
    tree.tag_configure("muted", foreground=theme.color("muted"))
    return tree


class _Fields(ttk.Frame):
    """A grid of labelled value boxes bound to dataclass attributes.

    A field is ``(label, target, attr, kind)``: ``target()`` returns the object,
    ``attr`` names the attribute (or ``(attr, i)`` for byte ``i`` of a bytes
    attribute), ``kind`` is a RANGES key, ``"text:N"`` or a ``{value: name}``
    dict. Values commit on Return or leaving the box."""

    def __init__(self, parent: tk.Misc, editor: "SaveEditorPage", columns: int = 2):
        super().__init__(parent, style="Page.TFrame")
        self._editor = editor
        self._columns = columns
        self._items: list = []

    def add(self, label: str, target: Callable[[], object], attr, kind="u8", on_set: Optional[Callable] = None,
            width: int = 12) -> None:
        n = len(self._items)
        row, col = divmod(n, self._columns)
        ttk.Label(self, text=label).grid(row=row, column=col * 2, sticky="w", padx=(0 if col == 0 else 18, 6), pady=2)
        var = tk.StringVar()
        if isinstance(kind, dict):
            names = [self._choice(v, name) for v, name in kind.items()]
            box = ttk.Combobox(self, textvariable=var, values=names, width=max(width, 28), height=20)
            box.bind("<<ComboboxSelected>>", lambda e, i=n: self._commit(i))
        else:
            box = ttk.Entry(self, textvariable=var, width=width)
        box.grid(row=row, column=col * 2 + 1, sticky="w", pady=2)
        box.bind("<Return>", lambda e, i=n: self._commit(i))
        box.bind("<FocusOut>", lambda e, i=n: self._commit(i))
        self._items.append((target, attr, kind, var, on_set, box))

    @staticmethod
    def _choice(value: int, name: str) -> str:
        return f"{name}  ({value})" if name else str(value)

    def _get(self, target, attr, kind):
        obj = target()
        if obj is None:
            return None
        if isinstance(attr, tuple):
            raw = getattr(obj, attr[0])[attr[1]]
            return raw - 256 if kind == "s8" and raw > 127 else raw
        return getattr(obj, attr)

    def load(self) -> None:
        for target, attr, kind, var, _, box in self._items:
            value = self._get(target, attr, kind)
            state = "disabled" if value is None else "normal"
            box.configure(state=state)
            if value is None:
                var.set("")
            elif isinstance(kind, dict):
                var.set(self._choice(value, kind.get(value, "")))
            else:
                var.set(str(value))

    def _parse(self, text: str, kind):
        text = text.strip()
        if isinstance(kind, dict):
            if text.endswith(")") and "(" in text:
                text = text[text.rindex("(") + 1:-1]
            value = int(text, 0)
            if not 0 <= value <= 0xFFFF:
                raise ValueError("out of range")
            return value
        if kind.startswith("text:"):
            limit = int(kind[5:])
            if len(text.encode("shift_jis")) >= limit:
                raise ValueError(f"at most {limit - 1} bytes")
            return text
        lo, hi = RANGES[kind]
        value = int(text, 0)
        if not lo <= value <= hi:
            raise ValueError(f"must be {lo}..{hi}")
        return value

    def _commit(self, i: int) -> None:
        target, attr, kind, var, on_set, box = self._items[i]
        old = self._get(target, attr, kind)
        if old is None:
            return
        try:
            value = self._parse(var.get(), kind)
        except (ValueError, UnicodeEncodeError) as exc:
            messagebox.showerror("Invalid value", f"{exc}", parent=self)
            self.load()
            return
        if value == old:
            return
        obj = target()
        if isinstance(attr, tuple):
            raw = bytearray(getattr(obj, attr[0]))
            raw[attr[1]] = value & 0xFF
            setattr(obj, attr[0], bytes(raw))
        else:
            setattr(obj, attr, value)
        if on_set:
            on_set(value)
        self._editor.mark_dirty()
        self.load()


class _CheckList(ttk.Frame):
    """A two-column ☑ list; ``get(i)``/``set(i, on)`` read and write the state."""

    def __init__(self, parent: tk.Misc, title: str, height: int = 10):
        super().__init__(parent, style="Page.TFrame")
        ttk.Label(self, text=title, style="Muted.TLabel").pack(anchor="w")
        self.tree = _tree(self, {"on": ("", 30, False), "name": ("Name", 240, True)}, height=height)
        self.tree.bind("<Double-1>", lambda e: self._toggle())
        self.tree.bind("<space>", lambda e: self._toggle())
        self._get: Callable[[int], bool] = lambda i: False
        self._set: Callable[[int, bool], None] = lambda i, on: None

    def fill(self, rows: list, get: Callable[[int], bool], set_: Callable[[int, bool], None]) -> None:
        self._get, self._set = get, set_
        self.tree.delete(*self.tree.get_children())
        for key, name in rows:
            self.tree.insert("", "end", iid=str(key), values=(ON if get(key) else OFF, name))

    def _toggle(self) -> None:
        sel = self.tree.selection()
        if not sel:
            return
        key = int(sel[0])
        self._set(key, not self._get(key))
        self.tree.set(sel[0], "on", ON if self._get(key) else OFF)


class SaveEditorPage(Page):
    kind = "saves"

    def __init__(self, shell):
        super().__init__(shell)
        head = ttk.Frame(self, style="Page.TFrame", padding=(28, 12, 28, 4))
        head.pack(fill="x")
        ttk.Label(head, text="Saves", style="Title.TLabel").pack(anchor="w")
        ttk.Label(head, style="Muted.TLabel", wraplength=1000, justify="left",
                  text="Open a memory-card save (.gci, as exported by Dolphin or GCMM) to edit the party, units, "
                       "convoy, forges and flags of one of its blocks. A file slot loads its newest valid block "
                       "(marked “loaded”). Keep the game closed while you overwrite a save it uses."
                  ).pack(anchor="w", pady=(2, 8))
        top = ttk.Frame(self, style="Page.TFrame", padding=(28, 0))
        top.pack(fill="x")
        ttk.Button(top, text="Open save file…", command=self._open).pack(side="left")
        self._save_button = ttk.Button(top, text="Save", command=self._save, state="disabled")
        self._save_button.pack(side="left", padx=(6, 0))
        self._save_as_button = ttk.Button(top, text="Save as…", command=self._save_as, state="disabled")
        self._save_as_button.pack(side="left", padx=(6, 0))
        ttk.Button(top, text="Check", command=self._check).pack(side="left", padx=(6, 0))
        self._file_label = ttk.Label(top, text="No save open.", style="Muted.TLabel")
        self._file_label.pack(side="left", padx=(12, 0))
        row = ttk.Frame(self, style="Page.TFrame", padding=(28, 8, 28, 0))
        row.pack(fill="x")
        ttk.Label(row, text="Block").pack(side="left")
        self._block_var = tk.StringVar()
        self._block_box = ttk.Combobox(row, textvariable=self._block_var, state="readonly", width=90)
        self._block_box.pack(side="left", padx=(6, 12))
        self._block_box.bind("<<ComboboxSelected>>", lambda e: self._select_block())
        self._status = ttk.Label(row, style="Muted.TLabel")
        self._status.pack(side="left")

        self._notebook = ttk.Notebook(self)
        self._notebook.pack(fill="both", expand=True, padx=28, pady=(8, 20))
        self._tabs: dict = {}
        for key, title in TABS.items():
            frame = ttk.Frame(self._notebook, padding=8)
            self._notebook.add(frame, text=title)
            self._tabs[key] = frame
        self._notebook.bind("<<NotebookTabChanged>>", lambda e: self._on_tab(), add="+")
        self._tab = "overview"

        self._path: Optional[Path] = None
        self._savefile: Optional[sf.SaveFile] = None
        self.block: Optional[sf.SaveBlock] = None
        self._labels: list[str] = []
        self._dirty_blocks: set = set()
        self._unit_slot: Optional[int] = None
        self._convoy_slot: Optional[int] = None
        self._forge: Optional[int] = None
        self._terrain: Optional[int] = None
        self._history: Optional[int] = None
        self._fields: list[_Fields] = []

        self._build_overview()
        self._build_units()
        self._build_convoy()
        self._build_forges()
        self._build_map()
        self._build_flags()
        self._build_system()
        self._build_raw()
        self._sync()

    # -- routing ----------------------------------------------------------------------
    def show(self, route) -> bool:
        if len(route) > 1 and route[1] in TABS:
            self._tab = route[1]
            self._notebook.select(list(TABS).index(self._tab))
        return True

    def crumbs(self, route):
        return [("Saves", ("saves",)), (TABS[self._tab], None)]

    def history_label(self, route):
        return "Saves"

    def _on_tab(self) -> None:
        self._tab = list(TABS)[self._notebook.index("current")]
        if self.shell.route and self.shell.route[0] == self.kind and self.shell.route[1:2] != (self._tab,):
            self.shell.replace_route((self.kind, self._tab))
        if self._tab == "raw":
            self._fill_raw()

    # -- names ------------------------------------------------------------------------
    def _fe8(self):
        try:
            session = self.shell.session
        except Exception:  # noqa: BLE001 - no FE8Data.bin: numbers only
            return None
        return session.fe8 if session is not None and session.available else None

    def _text(self, key: Optional[str]) -> str:
        index = self.shell.index
        return index.text(key) if index is not None and index.ready and key else ""

    def character_name(self, number: int) -> str:
        fe8 = self._fe8()
        if fe8 is None or not 0 < number <= len(fe8.characters):
            return f"#{number}"
        c = fe8.characters[number - 1]
        return self._text(c.mpid) or c.pid or f"#{number}"

    def class_name(self, number: int) -> str:
        fe8 = self._fe8()
        if fe8 is None or not 0 < number <= len(fe8.classes):
            return f"#{number}"
        c = fe8.classes[number - 1]
        return self._text(c.mjid) or c.jid or f"#{number}"

    def item_name(self, number: int) -> str:
        if number == 0:
            return ""
        fe8 = self._fe8()
        if fe8 is None or not 0 < number <= len(fe8.items):
            return f"#{number}"
        it = fe8.items[number - 1]
        return self._text(it.miid) or it.iid or f"#{number}"

    def _choices(self, kind: str) -> dict:
        fe8 = self._fe8()
        if fe8 is None:
            return {}
        if kind == "character":
            return {i + 1: self.character_name(i + 1) for i in range(len(fe8.characters))}
        if kind == "class":
            return {i + 1: self.class_name(i + 1) for i in range(len(fe8.classes))}
        out = {0: "(empty)"}
        out.update({i + 1: self.item_name(i + 1) for i in range(len(fe8.items))})
        return out

    # -- file ---------------------------------------------------------------------------
    def mark_dirty(self) -> None:
        if self.block is not None:
            self._dirty_blocks.add(id(self.block))
        self._sync()
        self._refresh_lists()

    def _confirm_discard(self) -> bool:
        return not self._dirty_blocks or messagebox.askyesno(
            "Discard changes?", "The open save has unsaved changes. Discard them?", parent=self)

    def _open(self) -> None:
        if not self._confirm_discard():
            return
        chosen = filedialog.askopenfilename(title="Open a save file", parent=self,
                                            filetypes=[("GameCube saves", "*.gci"), ("All files", "*.*")])
        if chosen:
            self.open_path(Path(chosen))

    def open_path(self, path: Path) -> bool:
        try:
            save = sf.SaveFile.from_bytes(path.read_bytes())
        except OSError as exc:
            messagebox.showerror("Could not open the save", str(exc), parent=self)
            return False
        if not save.blocks:
            messagebox.showerror("Not a Path of Radiance save", "No save blocks were found in this file.",
                                 parent=self)
            return False
        self._path, self._savefile, self._dirty_blocks = path, save, set()
        self._file_label.config(text=str(path))
        loaded = {id(b) for b in save.loaded_blocks()}
        self._labels = [f"[{b.location}] {sf.block_label(b)}{' · loaded' if id(b) in loaded else ''}"
                        + (f" · {b.error}" if b.error else "") for b in save.blocks]
        self._block_box.configure(values=self._labels)
        decoded = [b for b in save.blocks if b.decoded]
        best = max(decoded or save.blocks, key=lambda b: b.header.sequence)
        self._block_var.set(self._labels[save.blocks.index(best)])
        self._select_block()
        return True

    def _select_block(self) -> None:
        if self._savefile is None or self._block_var.get() not in self._labels:
            return
        self.block = self._savefile.blocks[self._labels.index(self._block_var.get())]
        self._unit_slot = self._convoy_slot = self._forge = self._terrain = self._history = None
        self._refresh_all()

    def _write(self, path: Path) -> None:
        dirty = [b for b in self._savefile.blocks if id(b) in self._dirty_blocks]
        try:
            data = self._savefile.to_bytes(dirty)
            path.write_bytes(data)
        except (OSError, ValueError) as exc:
            messagebox.showerror("Could not write the save", str(exc), parent=self)
            return
        self.shell.changelog.append(path.name, f"Edited save ({len(dirty)} block(s))")
        current = self.block.location if self.block else None
        self._dirty_blocks = set()
        self.open_path(path)
        if current is not None:
            for i, b in enumerate(self._savefile.blocks):
                if b.location == current:
                    self._block_var.set(self._labels[i])
                    self._select_block()

    def _save(self) -> None:
        if self._path is not None and self._savefile is not None:
            self._write(self._path)

    def _save_as(self) -> None:
        if self._savefile is None:
            return
        chosen = filedialog.asksaveasfilename(title="Save the edited save as", parent=self, defaultextension=".gci",
                                              initialfile=self._path.name if self._path else "save.gci",
                                              filetypes=[("GameCube saves", "*.gci")])
        if chosen:
            self._write(Path(chosen))

    def _check(self) -> None:
        if self.block is None:
            return
        problems = sf.validate(self.block, self._fe8())
        if not problems:
            try:
                self.block.build()
            except ValueError as exc:
                problems = [str(exc)]
        if problems:
            messagebox.showwarning("Problems", "\n".join(problems[:30]), parent=self)
        else:
            messagebox.showinfo("Check", "No problems found.", parent=self)

    def _sync(self) -> None:
        has = self._savefile is not None
        self._save_as_button.configure(state="normal" if has else "disabled")
        self._save_button.configure(state="normal" if self._dirty_blocks else "disabled")
        if self.block is None:
            self._status.config(text="")
            return
        units = len(self.block.unit_slots()) if self.block.decoded else 0
        self._status.config(text=f"{units} unit(s)" + (" · unsaved changes" if self._dirty_blocks else ""))

    def _refresh_all(self) -> None:
        editable = self.block is not None and self.block.decoded
        for f in self._fields:
            f.load()
        self._refresh_lists()
        self._fill_flags()
        self._fill_system_lists()
        self._fill_raw()
        self._sync()
        if self.block is not None and not editable:
            self._notebook.select(list(TABS).index("raw"))

    def _refresh_lists(self) -> None:
        self._fill_units()
        self._fill_convoy()
        self._fill_forges()
        self._fill_map()
        self._fill_history()

    def _fields_in(self, parent, columns=2) -> _Fields:
        f = _Fields(parent, self, columns)
        self._fields.append(f)
        return f

    # targets
    def _header(self):
        return self.block.header if self.block else None

    def _party(self):
        return self.block.party if self.block else None

    def _system(self):
        return self.block.system if self.block else None

    def _map_state(self):
        return self.block.map_state if self.block else None

    # -- overview -----------------------------------------------------------------------
    def _build_overview(self) -> None:
        body = ScrollFrame(self._tabs["overview"], padding=(4, 4))
        body.pack(fill="both", expand=True)
        b = body.body
        section_header(b, "Block", "header of this save block").pack(anchor="w")
        f = self._fields_in(b, 3)
        f.pack(anchor="w", pady=(4, 12))
        f.add("Save kind", self._header, "save_kind", dict(sf.SAVE_KINDS))
        f.add("File slot (0-4)", self._header, "file_slot")
        f.add("Sequence", self._header, "sequence", "u32")
        f.add("Chapter", self._header, "chapter", on_set=lambda v: setattr(self.block.party, "chapter", v)
              if self.block.party else None)
        f.add("Resume at", self._header, "resume_point", dict(sf.RESUME_POINTS), on_set=self._sync_resume)
        f.add("Difficulty", self._header, "difficulty", dict(sf.DIFFICULTIES), on_set=self._sync_difficulty)
        f.add("Playthrough id", self._header, "playthrough_id")
        f.add("Checkpoint of slot", self._header, "owner_slot")
        f.add("Play time (s, header)", lambda: self._TimeView(self.block.header) if self.block else None,
              "seconds", "u32")

        section_header(b, "Party", "party_data, saved as BMST").pack(anchor="w")
        f = self._fields_in(b, 3)
        f.pack(anchor="w", pady=(4, 12))
        f.add("Gold", self._party, "gold", "u32")
        f.add("Bonus EXP", self._party, "bonus_exp", "u32")
        f.add("Chapter", self._party, "chapter")
        f.add("Map", self._party, "chapter_name", "text:24", width=14)
        f.add("Turn", self._party, "turn", "u16")
        f.add("Phase (army)", self._party, "phase", dict(sf.ARMIES))
        f.add("Playthrough number", self._party, "playthrough")
        f.add("Play time (s)", lambda: self._TimeView(self.block.party) if self.block and self.block.party else None,
              "seconds", "u32")
        f.add("Deployment surplus", self._party, "deployment_surplus")
        f.add("Cursor X", self._party, "cursor_x")
        f.add("Cursor Y", self._party, "cursor_y")
        f.add("Base opening done", self._party, "base_opening_done")
        f.add("Report: gold gained", self._party, "report_profit", "u32")
        f.add("Report: gold spent", self._party, "report_loss", "u32")
        f.add("Report: bonus EXP", self._party, "report_exp", "s16")
        f.add("Report: score", self._party, "report_score", "s16")
        f.add("Byte +0x50", self._party, "byte_50")
        f.add("Byte +0x51", self._party, "byte_51")

        section_header(b, "Options", "the Options menu, saved per file").pack(anchor="w")
        f = self._fields_in(b, 3)
        f.pack(anchor="w", pady=(4, 12))
        for i, name in enumerate(sf.OPTION_BYTES):
            kind = dict(sf.DIFFICULTIES) if i == 10 else ("s8" if i in (6, 7) else "u8")
            f.add(name, self._party, ("options", i), kind,
                  on_set=(lambda v: setattr(self.block.header, "difficulty", v)) if i == 10 else None)
        ttk.Label(b, style="Muted.TLabel", wraplength=900, justify="left",
                  text="Known option bits: byte 0 - 0x02 unit window off, 0x04 terrain window off, 0x18 message "
                       "speed; byte 2 - 0x0C sound output; byte 3 - 0x20 message sounds off, 0x40 show other "
                       "units' moves, 0x80 fixed growths.").pack(anchor="w")

        section_header(b, "Map state", "MDST").pack(anchor="w", pady=(12, 0))
        f = self._fields_in(b, 3)
        f.pack(anchor="w", pady=(4, 12))
        for i, name in enumerate(sf.MAP_STATE_BYTES):
            f.add(name, self._map_state, ("values", i))
        f.add("Camera rotation", self._map_state, "camera_rotation")
        f.add("Camera X", self._map_state, "camera_x", "s16")
        f.add("Camera Y", self._map_state, "camera_y", "s16")

        section_header(b, "Cleared maps", "the 40-entry chapter history").pack(anchor="w")
        self._history_tree = _tree(b, {"n": ("#", 40, False), "chapter": ("Chapter", 80, False),
                                       "cont": ("Continued", 80, False), "turns": ("Turns", 80, False),
                                       "time": ("Time", 120, True)}, height=8)
        self._history_tree.bind("<<TreeviewSelect>>", lambda e: self._pick_history())
        f = self._fields_in(b, 4)
        f.pack(anchor="w", pady=(4, 12))
        rec = lambda: self.block.party.clear_history[self._history] \
            if self.block and self.block.party and self._history is not None else None  # noqa: E731
        f.add("Chapter", rec, "chapter")
        f.add("Continued", rec, "continued")
        f.add("Turns", rec, "turns", "u16")
        f.add("Seconds", rec, "seconds", "u32")
        self._history_fields = f

    class _TimeView:
        """Play time ticks shown as whole seconds."""

        def __init__(self, owner):
            object.__setattr__(self, "_owner", owner)

        @property
        def seconds(self) -> int:
            return min(self._owner.play_time // TICKS_PER_SECOND, 0xFFFFFFFF)

        def __setattr__(self, name, value):
            if name == "seconds":
                self._owner.play_time = value * TICKS_PER_SECOND
            else:
                object.__setattr__(self, name, value)

    def _sync_resume(self, value: int) -> None:
        if self.block.party:
            self.block.party.resume_point = value

    def _sync_difficulty(self, value: int) -> None:
        if self.block.party:
            self.block.party.difficulty = value

    def _fill_history(self) -> None:
        tree = self._history_tree
        tree.delete(*tree.get_children())
        if not self.block or not self.block.party:
            return
        for i, c in enumerate(self.block.party.clear_history):
            if not c.used and i > 0 and not self.block.party.clear_history[i - 1].used:
                continue
            t = c.seconds
            tree.insert("", "end", iid=str(i), values=(i + 1, c.chapter, c.continued, c.turns,
                                                       f"{t // 3600}:{t // 60 % 60:02d}:{t % 60:02d}"),
                        tags=() if c.used else ("muted",))
        if self._history is not None and tree.exists(str(self._history)):
            tree.selection_set(str(self._history))

    def _pick_history(self) -> None:
        sel = self._history_tree.selection()
        self._history = int(sel[0]) if sel else None
        self._history_fields.load()

    # -- units ---------------------------------------------------------------------------
    def _build_units(self) -> None:
        tab = self._tabs["units"]
        left = ttk.Frame(tab)
        left.pack(side="left", fill="y")
        self._unit_tree = _tree(left, {"slot": ("Slot", 44, False), "name": ("Character", 130, False),
                                       "class": ("Class", 120, False), "army": ("Army", 70, False),
                                       "lv": ("Lv", 34, False)}, height=24)
        self._unit_tree.bind("<<TreeviewSelect>>", lambda e: self._pick_unit())
        bar = ttk.Frame(left)
        bar.pack(fill="x")
        ttk.Button(bar, text="Copy to new slot", command=self._copy_unit).pack(side="left")
        ttk.Button(bar, text="Remove", command=self._remove_unit).pack(side="left", padx=(6, 0))
        self._army_filter = tk.StringVar(value="All")
        ttk.Combobox(bar, textvariable=self._army_filter, state="readonly", width=10,
                     values=["All"] + list(sf.ARMIES.values())).pack(side="left", padx=(6, 0))
        self._army_filter.trace_add("write", lambda *a: self._fill_units())

        scroll = ScrollFrame(tab, padding=(16, 4))
        scroll.pack(side="left", fill="both", expand=True)
        b = scroll.body
        unit = lambda: self.block.units[self._unit_slot - 1] \
            if self.block and self.block.decoded and self._unit_slot else None  # noqa: E731
        self._unit = unit

        section_header(b, "Identity").pack(anchor="w")
        f = self._fields_in(b, 2)
        f.pack(anchor="w", pady=(4, 10))
        self._character_field_index = 0
        f.add("Character", unit, "character", {})
        f.add("Class", unit, "job", {})
        f.add("Army", unit, "army", dict(sf.ARMIES))
        f.add("Group", unit, "group")
        f.add("Level", unit, "level")
        f.add("EXP (255 = none)", unit, "exp")
        f.add("Current HP", unit, "hp")
        f.add("Transform gauge", unit, "transform_gauge")
        f.add("Tile X", unit, "x")
        f.add("Tile Y", unit, "y")
        f.add("Build bonus", unit, "build_bonus")
        f.add("Move bonus", unit, "move_bonus")
        self._identity_fields = f

        section_header(b, "Stats", "gained on top of the class base").pack(anchor="w")
        f = self._fields_in(b, 4)
        f.pack(anchor="w", pady=(4, 10))
        for i, name in enumerate(sf.UNIT_STATS):
            f.add(name, unit, ("stats", i), "s8", width=6)
        section_header(b, "Fixed-growth points").pack(anchor="w")
        f = self._fields_in(b, 4)
        f.pack(anchor="w", pady=(4, 10))
        for i, name in enumerate(sf.UNIT_STATS):
            f.add(name, unit, ("growth_points", i), width=6)
        section_header(b, "Weapon EXP", "E 1, D 31, C 71, B 121, A 181, S 251").pack(anchor="w")
        f = self._fields_in(b, 4)
        f.pack(anchor="w", pady=(4, 10))
        for i, name in enumerate(sf.WEAPON_EXP_TYPES):
            f.add(name, unit, ("weapon_exp", i), width=6)

        section_header(b, "Items", "flags: 0x80 equipped, 0x40 dropped, low 6 bits forge record").pack(anchor="w")
        f = self._fields_in(b, 3)
        f.pack(anchor="w", pady=(4, 10))
        for i in range(8):
            slot = (lambda k: lambda: unit().items[k] if unit() else None)(i)
            f.add(f"Item {i + 1}", slot, "item", {})
            f.add("Uses", slot, "uses", width=6)
            f.add("Flags", slot, "flags", width=6)
        self._item_fields = f

        section_header(b, "Supports", "points per support-list slot").pack(anchor="w")
        f = self._fields_in(b, 5)
        f.pack(anchor="w", pady=(4, 10))
        for i in range(10):
            f.add(f"Slot {i + 1}", unit, ("supports", i), width=5)

        section_header(b, "Skills").pack(anchor="w")
        self._skill_list = _CheckList(b, "Double-click to give or remove (FE8Data skill order).", height=8)
        self._skill_list.pack(anchor="w", fill="x", pady=(4, 10))

        section_header(b, "Records").pack(anchor="w")
        f = self._fields_in(b, 3)
        f.pack(anchor="w", pady=(4, 10))
        f.add("Battles", unit, "battles", "u16")
        f.add("Kills", unit, "kills", "u16")
        f.add("Kills this map", unit, "map_kills", "u16")
        f.add("Tiles moved", unit, "tiles_moved", "u16")
        f.add("Counter +0x230", unit, "counter_230", "u16")
        f.add("Counter +0x232", unit, "counter_232", "u16")
        f.add("Last kill chapter", unit, "last_kill_chapter")
        f.add("Byte +0x235", unit, "byte_235")

        section_header(b, "Advanced", "links are unit slots, 0 = none").pack(anchor="w")
        f = self._fields_in(b, 3)
        f.pack(anchor="w", pady=(4, 10))
        f.add("Previous in army", unit, "prev_slot")
        f.add("Next in army", unit, "next_slot")
        f.add("Carried unit", unit, "linked_slot")
        f.add("State flags", unit, "state_flags", "u32")
        for i in range(4):
            f.add(f"Status byte {i}", unit, ("status", i))
        f.add("Byte +0x19D", unit, "byte_19d")
        f.add("AI attack", unit, "ai_attack")
        f.add("AI move", unit, "ai_move")
        f.add("AI heal", unit, "ai_heal")
        f.add("AI mtype", unit, "ai_mtype")
        f.add("AI attack step", unit, "ai_attack_pc")
        f.add("AI move step", unit, "ai_move_pc")
        f.add("AI flags", unit, "ai_flags", "u32")
        f.add("AI +0x258", unit, "ai_258", "u16")
        f.add("AI +0x25A", unit, "ai_25a", "u16")
        f.add("AI turn order", unit, "ai_order")
        f.add("Field +0x15C", unit, "field_15c", "u16")

    def _fill_units(self) -> None:
        tree = self._unit_tree
        tree.delete(*tree.get_children())
        if not self.block or not self.block.decoded:
            return
        want = self._army_filter.get()
        for slot, u in self.block.unit_slots():
            army = sf.ARMIES.get(u.army, str(u.army))
            if want != "All" and army != want:
                continue
            tree.insert("", "end", iid=str(slot), values=(slot, self.character_name(u.character),
                                                          self.class_name(u.job), army, u.level))
        if self._unit_slot and tree.exists(str(self._unit_slot)):
            tree.selection_set(str(self._unit_slot))

    def _pick_unit(self) -> None:
        sel = self._unit_tree.selection()
        slot = int(sel[0]) if sel else None
        if slot == self._unit_slot:
            return
        self._unit_slot = slot
        self._load_unit_choices()
        for f in self._fields:
            f.load()
        self._fill_skills()

    def _load_unit_choices(self) -> None:
        """Fill the character/class/item pickers (lazily: they are long)."""
        chars, jobs, items = self._choices("character"), self._choices("class"), self._choices("item")
        for fields_, wanted in ((self._identity_fields, {"character": chars, "job": jobs}),
                                (self._item_fields, {"item": items})):
            for i, (target, attr, kind, var, on_set, box) in enumerate(fields_._items):
                if isinstance(attr, str) and attr in wanted and wanted[attr]:
                    fields_._items[i] = (target, attr, wanted[attr], var, on_set, box)
                    box.configure(values=[fields_._choice(v, n) for v, n in wanted[attr].items()])

    def _fill_skills(self) -> None:
        unit = self._unit()
        fe8 = self._fe8()
        if unit is None:
            self._skill_list.fill([], lambda i: False, lambda i, on: None)
            return
        count = len(fe8.skills) if fe8 else 128
        rows = []
        for i in range(min(count, 128)):
            s = fe8.skills[i] if fe8 else None
            name = (self._text(s.msid) or s.sid) if s else f"Skill {i}"
            rows.append((i, f"{i:3d}  {name}"))

        def set_(i, on):
            unit.set_skill(i, on)
            self.mark_dirty()
        self._skill_list.fill(rows, unit.has_skill, set_)

    def _copy_unit(self) -> None:
        unit = self._unit()
        if unit is None:
            return
        import copy
        clone = copy.deepcopy(unit)
        for it in clone.items:
            it.flags &= 0xC0  # forge records are per item: the copy gets plain weapons
        try:
            slot = self.block.add_unit(clone, after=self._unit_slot if unit.army == clone.army else None)
        except ValueError as exc:
            messagebox.showerror("No room", str(exc), parent=self)
            return
        self._unit_slot = slot
        self.mark_dirty()

    def _remove_unit(self) -> None:
        if self._unit() is None:
            return
        if not messagebox.askyesno("Remove unit", f"Empty unit slot {self._unit_slot}?", parent=self):
            return
        self.block.remove_unit(self._unit_slot)
        self._unit_slot = None
        self.mark_dirty()
        for f in self._fields:
            f.load()

    # -- convoy / forges / map objects ---------------------------------------------------------
    def _build_convoy(self) -> None:
        tab = self._tabs["convoy"]
        f = self._fields_in(tab, 3)
        f.pack(side="bottom", anchor="w", pady=(6, 0))
        slot = lambda: self.block.convoy[self._convoy_slot] \
            if self.block and self.block.decoded and self._convoy_slot is not None else None  # noqa: E731
        f.add("Item", slot, "item", {})
        f.add("Uses", slot, "uses", width=6)
        f.add("Flags", slot, "flags", width=6)
        self._convoy_fields = f
        self._convoy_tree = _tree(tab, {"slot": ("Slot", 50, False), "item": ("Item", 260, False),
                                        "uses": ("Uses", 60, False), "forge": ("Forge", 60, True)}, height=20)
        self._convoy_tree.bind("<<TreeviewSelect>>", lambda e: self._pick_convoy())

    def _fill_convoy(self) -> None:
        tree = self._convoy_tree
        tree.delete(*tree.get_children())
        if not self.block or not self.block.decoded:
            return
        for i, s in enumerate(self.block.convoy):
            tree.insert("", "end", iid=str(i), values=(i + 1, self.item_name(s.item), s.uses if s.item else "",
                                                      s.forge or ""), tags=() if s.item else ("muted",))
        if self._convoy_slot is not None:
            tree.selection_set(str(self._convoy_slot))

    def _pick_convoy(self) -> None:
        sel = self._convoy_tree.selection()
        self._convoy_slot = int(sel[0]) if sel else None
        items = self._choices("item")
        for i, (target, attr, kind, var, on_set, box) in enumerate(self._convoy_fields._items):
            if attr == "item" and items:
                self._convoy_fields._items[i] = (target, attr, items, var, on_set, box)
                box.configure(values=[_Fields._choice(v, n) for v, n in items.items()])
        self._convoy_fields.load()

    def _build_forges(self) -> None:
        tab = self._tabs["forges"]
        f = self._fields_in(tab, 4)
        f.pack(side="bottom", anchor="w", pady=(6, 0))
        rec = lambda: self.block.forges[self._forge] \
            if self.block and self.block.decoded and self._forge is not None else None  # noqa: E731
        f.add("Allocated", rec, "allocated")
        f.add("Might steps", rec, "might", "s8", width=6)
        f.add("Hit steps (x5)", rec, "hit", "s8", width=6)
        f.add("Crit steps (x3)", rec, "crit", "s8", width=6)
        f.add("Weight steps", rec, "weight", "s8", width=6)
        for i in range(4):
            f.add(f"Look byte {i}", rec, ("appearance", i), width=6)
        self._forge_tree = _tree(tab, {"n": ("#", 40, False), "name": ("Name", 200, False),
                                       "stats": ("Mt / Hit / Crt / Wt", 200, False), "used": ("Used by", 300, True)},
                                 height=18)
        self._forge_tree.bind("<<TreeviewSelect>>", lambda e: self._pick_forge())

    def _fill_forges(self) -> None:
        tree = self._forge_tree
        tree.delete(*tree.get_children())
        if not self.block or not self.block.decoded:
            return
        users: dict = {}
        for slot, u in self.block.unit_slots():
            for it in u.items:
                if it.forge:
                    users.setdefault(it.forge, []).append(f"{self.character_name(u.character)}: {self.item_name(it.item)}")
        for i, s in enumerate(self.block.convoy):
            if s.forge:
                users.setdefault(s.forge, []).append(f"convoy {i + 1}: {self.item_name(s.item)}")
        for i, r in enumerate(self.block.forges):
            tree.insert("", "end", iid=str(i), values=(i + 1, r.name_text if r.allocated else "",
                                                      f"{r.might} / {r.hit} / {r.crit} / {r.weight}" if r.allocated else "",
                                                      ", ".join(users.get(i + 1, []))),
                        tags=() if r.allocated else ("muted",))
        if self._forge is not None:
            tree.selection_set(str(self._forge))

    def _pick_forge(self) -> None:
        sel = self._forge_tree.selection()
        self._forge = int(sel[0]) if sel else None
        for f in self._fields:
            f.load()

    def _build_map(self) -> None:
        tab = self._tabs["map"]
        ttk.Label(tab, style="Muted.TLabel", wraplength=900, justify="left",
                  text="Per-map tile records: opened doors, chests and roofs, visited villages, breakable walls, "
                       "ballistae, pits and rocks. Only the first “count” records are live.").pack(anchor="w")
        f = self._fields_in(tab, 4)
        f.pack(side="bottom", anchor="w", pady=(6, 0))
        tt = lambda: self.block.terrain if self.block and self.block.decoded else None  # noqa: E731
        rec = lambda: self.block.terrain.entries[self._terrain] \
            if self.block and self.block.decoded and self._terrain is not None else None  # noqa: E731
        f.add("Count", tt, "count", "u32")
        f.add("X", rec, "x", "s8", width=6)
        f.add("Y", rec, "y", "s8", width=6)
        f.add("Type", rec, "type", dict(sf.TERRAIN_TYPES))
        f.add("Subtype", rec, "subtype", width=6)
        for i in range(4):
            f.add(f"Value {i}", rec, ("values", i), width=6)
        self._map_tree = _tree(tab, {"n": ("#", 40, False), "xy": ("Tile", 70, False), "type": ("Type", 160, False),
                                     "sub": ("Subtype", 60, False), "values": ("Values", 160, True)}, height=16)
        self._map_tree.bind("<<TreeviewSelect>>", lambda e: self._pick_terrain())

    def _fill_map(self) -> None:
        tree = self._map_tree
        tree.delete(*tree.get_children())
        if not self.block or not self.block.decoded:
            return
        count = self.block.terrain.count
        for i, e in enumerate(self.block.terrain.entries):
            if i >= count and not any(e.build()):
                continue
            tree.insert("", "end", iid=str(i), values=(i + 1, f"{e.x}, {e.y}", sf.TERRAIN_TYPES.get(e.type, e.type),
                                                      e.subtype, " ".join(str(v) for v in e.values)),
                        tags=() if i < count else ("muted",))
        if self._terrain is not None and tree.exists(str(self._terrain)):
            tree.selection_set(str(self._terrain))

    def _pick_terrain(self) -> None:
        sel = self._map_tree.selection()
        self._terrain = int(sel[0]) if sel else None
        for f in self._fields:
            f.load()

    # -- flags ---------------------------------------------------------------------------------
    def _build_flags(self) -> None:
        tab = self._tabs["flags"]
        self._flags_note = ttk.Label(tab, style="Muted.TLabel", wraplength=900, justify="left")
        self._flags_note.pack(anchor="w")
        bar = ttk.Frame(tab)
        bar.pack(side="bottom", fill="x")
        ttk.Button(bar, text="Clear chapter flags", command=self._clear_locals).pack(side="left")
        self._flag_tree = _tree(tab, {"on": ("Set", 50, False), "slot": ("Slot", 60, False),
                                      "name": ("Name", 280, False), "meaning": ("Meaning", 420, True)}, height=20)
        self._flag_tree.bind("<Double-1>", lambda e: self._toggle_flag())
        self._flag_tree.bind("<space>", lambda e: self._toggle_flag())
        self._flag_names: list = []

    def _global_flags(self) -> list:
        try:
            return ef.global_flags(parse(script_sources.peek(self.project, script_sources.startup_path(self.project))))
        except (OSError, ValueError, ParseError, AttributeError):
            return ef.global_flags_vanilla()

    def _slot_names(self) -> list:
        globals_ = self._global_flags()
        locals_: list = []
        m = self.block.party.chapter_name
        if m.startswith("bmap") and m[4:6].isdigit():
            try:
                path = script_sources.chapter_script(self.project, m[4:6])
                if path is not None:
                    locals_ = ef.local_flags(parse(script_sources.peek(self.project, path)))
            except (OSError, ValueError, ParseError, AttributeError):
                pass
        return ef.slot_names(globals_, locals_)

    def _bits(self) -> list:
        raw = self.block.party.flag_bits
        return [bool(raw[i >> 3] & (1 << (i & 7))) for i in range(ef.SLOT_COUNT)]

    def _set_bits(self, bits: list) -> None:
        raw = bytearray(ef.BIT_BYTES)
        for i, on in enumerate(bits):
            if on:
                raw[i >> 3] |= 1 << (i & 7)
        self.block.party.flag_bits = bytes(raw)
        self.mark_dirty()

    def _fill_flags(self) -> None:
        tree = self._flag_tree
        tree.delete(*tree.get_children())
        if not self.block or not self.block.decoded:
            self._flags_note.config(text="")
            return
        self._flag_names = self._slot_names()
        n_globals = len(self._global_flags())
        stale = self.block.flags_stale
        self._flags_note.config(text=(
            "This block was saved between chapters: loading it starts the chapter afresh, which clears "
            "every chapter flag below, so their bits are leftovers of the finished chapter." if stale else
            "Chapter flags are named from the script of the block's map.")
            + " Double-click a flag (or press Space) to switch it.")
        bits = self._bits()
        for slot in range(ef.SLOT_COUNT):
            name, on = self._flag_names[slot], bits[slot]
            meaning = ef.FLAG_GLOSSES.get(name or "", "")
            if name is None:
                meaning = "No name in this chapter"
            elif name == ef.RESERVED_GLOBAL:
                meaning = "Reserved, unused"
            if stale and slot >= n_globals:
                meaning = ("stale - " + meaning) if meaning else "stale"
            if not on and name is None:
                continue
            tree.insert("", "end", iid=str(slot), values=(ON if on else OFF, slot, name or "", meaning),
                        tags=() if name else ("muted",))

    def _toggle_flag(self) -> None:
        sel = self._flag_tree.selection()
        if not sel or not self.block or not self.block.decoded:
            return
        bits = self._bits()
        slot = int(sel[0])
        bits[slot] = not bits[slot]
        self._set_bits(bits)
        self._flag_tree.set(sel[0], "on", ON if bits[slot] else OFF)

    def _clear_locals(self) -> None:
        if not self.block or not self.block.decoded:
            return
        n = len(self._global_flags())
        bits = self._bits()
        self._set_bits([on if i < n else False for i, on in enumerate(bits)])
        self._fill_flags()

    # -- system data -------------------------------------------------------------------------
    def _build_system(self) -> None:
        scroll = ScrollFrame(self._tabs["system"], padding=(4, 4))
        scroll.pack(fill="both", expand=True)
        b = scroll.body
        ttk.Label(b, style="Muted.TLabel", wraplength=900, justify="left",
                  text="Shared by every save on the card: at boot the game takes it from the newest block. Edit "
                       "it in that block (the one with the highest sequence).").pack(anchor="w")
        f = self._fields_in(b, 3)
        f.pack(anchor="w", pady=(6, 10))
        f.add("System id", self._system, "system_id", "u64", width=22)
        f.add("Unlock bits", self._system, "unlocks", "u16")
        f.add("Byte +0x44 (console)", self._system, "region")
        f.add("Screen X", self._system, "screen_x", "s8")
        f.add("Screen Y", self._system, "screen_y", "s8")
        f.add("Brightness", self._system, "brightness")
        f.add("Last file slot", self._system, "last_file_slot")
        f.add("Byte +0x43", self._system, "reserved_43")
        cols = ttk.Frame(b, style="Page.TFrame")
        cols.pack(fill="x")
        self._unlock_list = _CheckList(cols, "Unlocks (game clear, trial maps)", height=7)
        self._unlock_list.pack(side="left", fill="both", expand=True, padx=(0, 8))
        self._met_list = _CheckList(cols, "Characters met (by character number)", height=14)
        self._met_list.pack(side="left", fill="both", expand=True)
        section_header(b, "Finished playthroughs", "ids of playthroughs that reached the ending, 0 = free").pack(
            anchor="w", pady=(10, 0))
        f = self._fields_in(b, 6)
        f.pack(anchor="w", pady=(4, 10))
        for i in range(30):
            f.add(f"{i + 1}", self._system, ("cleared_playthroughs", i), width=4)

    UNLOCK_BITS = ((0, "Game cleared (clear records, trial map 1)"), (1, "Trial map 2"), (2, "Trial map 3"),
                   (3, "Bit 3"), (4, "Trial maps 4 and 5"), (5, "Trial maps 4 and 6"), (6, "Bit 6"), (7, "Bit 7"))

    def _fill_system_lists(self) -> None:
        system = self._system()
        if system is None:
            self._unlock_list.fill([], lambda i: False, lambda i, on: None)
            self._met_list.fill([], lambda i: False, lambda i, on: None)
            return

        def set_unlock(i, on):
            system.unlocks = system.unlocks | (1 << i) if on else system.unlocks & ~(1 << i)
            self.mark_dirty()
            for f in self._fields:
                f.load()

        def set_met(i, on):
            system.set_met(i, on)
            self.mark_dirty()
        self._unlock_list.fill(list(self.UNLOCK_BITS), lambda i: bool(system.unlocks >> i & 1), set_unlock)
        fe8 = self._fe8()
        count = min(len(fe8.characters), 127) if fe8 else 127
        self._met_list.fill([(n, f"{n:3d}  {self.character_name(n)}" + (f"  ({fe8.characters[n - 1].pid})" if fe8 else ""))
                             for n in range(1, count + 1)],
                            system.met, set_met)

    # -- raw -------------------------------------------------------------------------------
    def _build_raw(self) -> None:
        tab = self._tabs["raw"]
        self._raw_note = ttk.Label(tab, style="Muted.TLabel", wraplength=900, justify="left")
        self._raw_note.pack(anchor="w")
        frame = ttk.Frame(tab)
        frame.pack(fill="both", expand=True, pady=(6, 0))
        self._raw_text = tk.Text(frame, wrap="none", font=("Consolas", 10), height=20)
        scroll = ttk.Scrollbar(frame, command=self._raw_text.yview)
        self._raw_text.configure(yscrollcommand=scroll.set)
        scroll.pack(side="right", fill="y")
        self._raw_text.pack(side="left", fill="both", expand=True)

    def _fill_raw(self) -> None:
        if self._tab != "raw" and self.block is not None and self.block.decoded:
            return
        text = self._raw_text
        text.configure(state="normal")
        text.delete("1.0", "end")
        if self.block is not None:
            try:
                data = self.block.build()
            except ValueError as exc:
                data = self.block.raw
                self._raw_note.config(text=str(exc))
            else:
                self._raw_note.config(text=self.block.error or "The block as it will be written (read only).")
            end = len(data.rstrip(b"\0")) + 16
            lines = [f"{o:05X}  {data[o:o + 16].hex(' ')}" for o in range(0, min(end, len(data)), 16)]
            text.insert("1.0", "\n".join(lines))
        text.configure(state="disabled")
