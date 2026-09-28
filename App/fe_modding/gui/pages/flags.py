"""Flags: the 96 named on/off switches event scripts remember things with
(``formats/event_flags.py``), in three tabs.

* **Campaign flags** - the engine's eight ``gf_*`` flags and the ones
  ``startup.cmb`` registers in ``RegistGlobalFlags``. New ones are appended
  (or a reserved slot renamed), so saves keep their meaning.
* **Chapter flags** - what one chapter's ``Startup`` registers, where each is
  used, and how many slots are left. New ones are appended after the last
  registration.
* **Save file** - the flags of a ``.gci`` save block, by name; ticking one
  rewrites the block and its checksum.

Adding a flag rewrites the script right away (compiled onto the current
``.cmb``, source kept in ``script_sources/``). The Script tab of a chapter
shows the change the next time the file is opened there, and a file with
unsaved edits in that tab is left alone."""

from __future__ import annotations

import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, simpledialog, ttk
from typing import Optional

from ... import chapters, script_sources
from ...formats import event_flags as ef
from ...formats.cmb import CompileError
from ...formats.cmb.parser import ParseError, parse
from ..shell import Page
from .chapters import open_script
from .. import theme

TABS = {"campaign": "Campaign flags", "chapter": "Chapter flags", "save": "Save file"}
ON, OFF = "☑", "☐"


class FlagsPage(Page):
    kind = "flags"

    def __init__(self, shell):
        super().__init__(shell)
        head = ttk.Frame(self, style="Page.TFrame", padding=(28, 12, 28, 4))
        head.pack(fill="x")
        ttk.Label(head, text="Flags", style="Title.TLabel").pack(anchor="w")
        ttk.Label(head, style="Muted.TLabel", wraplength=1000, justify="left",
                  text="Scripts remember things (a chest opened, a character recruited) in 96 named on/off "
                       "flags. Campaign flags last the whole playthrough; chapter flags last one chapter. "
                       "A save stores only the 96 bits, so a flag's meaning in a save is its slot: new flags "
                       "are always added after the existing ones.").pack(anchor="w", pady=(2, 8))
        self._notebook = ttk.Notebook(self)
        self._notebook.pack(fill="both", expand=True, padx=28, pady=(0, 20))
        self._campaign = _CampaignTab(self._notebook, self)
        self._chapter = _ChapterTab(self._notebook, self)
        self._save = _SaveTab(self._notebook, self)
        for key, tab in (("campaign", self._campaign), ("chapter", self._chapter), ("save", self._save)):
            self._notebook.add(tab, text=TABS[key])
        self._tab = "campaign"
        self._notebook.bind("<<NotebookTabChanged>>", lambda e: self._on_tab(), add="+")
        self._budget: Optional[dict] = None  # chapter id -> chapter flag count, from a background scan
        self._scan_running = False

    # -- routing ----------------------------------------------------------------------
    def show(self, route) -> bool:
        tab = route[1] if len(route) > 1 and route[1] in TABS else self._tab
        self._tab = tab
        self._notebook.select(list(TABS).index(tab))
        if tab == "chapter" and len(route) > 2:
            self._chapter.select(route[2])
        self.refresh()
        return True

    def crumbs(self, route):
        tab = route[1] if len(route) > 1 and route[1] in TABS else self._tab
        return [("Flags", ("flags",)), (TABS[tab], None)]

    def history_label(self, route):
        tab = route[1] if len(route) > 1 and route[1] in TABS else self._tab
        return f"Flags › {TABS[tab]}"

    def _on_tab(self) -> None:
        self._tab = list(TABS)[self._notebook.index("current")]
        if self.shell.route and self.shell.route[0] == self.kind and self.shell.route[1:2] != (self._tab,):
            self.shell.replace_route((self.kind, self._tab))

    def refresh(self) -> None:
        self._campaign.refresh()
        self._chapter.refresh()
        self._scan_budget()

    def index_changed(self) -> None:
        self._chapter.fill_chapters()

    # -- shared services ------------------------------------------------------------------
    def global_flags(self) -> list[str]:
        """The project's global flags (engine flags first), from its startup.cmb."""
        path = script_sources.startup_path(self.project)
        try:
            return ef.global_flags(parse(script_sources.peek(self.project, path)))
        except (OSError, ValueError, ParseError):
            return ef.global_flags_vanilla()

    def chapter_title(self, chapter_id: str) -> str:
        index = self.shell.index
        if index is not None and chapter_id in index.by_chapter:
            return index.by_chapter[chapter_id].title
        return f"Chapter {chapter_id}"

    def script_editor(self):
        page = self.shell.existing_page("chapter")
        return getattr(page, "_script", None) if page is not None else None

    def edit_script(self, path: Path, transform, what: str) -> bool:
        """Rewrite ``path``'s source with ``transform`` and save it. Refuses when
        the Script tab holds unsaved edits of the same file."""
        editor = self.script_editor()
        if editor is not None and editor.current_path == path and editor.dirty:
            messagebox.showwarning(
                "Unsaved script", f"{path.name} has unsaved changes in the Script tab. Save or revert them first.",
                parent=self)
            return False
        try:
            loaded = script_sources.load(self.project, path)
            new_source = transform(loaded.source)
            result = script_sources.save(self.project, loaded, new_source)
        except CompileError as e:
            errors = [str(d) for d in e.diagnostics if d.severity == "error"]
            messagebox.showerror("Could not update the script", "\n".join(errors[:8]), parent=self)
            return False
        except (OSError, ValueError, ParseError) as exc:
            messagebox.showerror("Could not update the script", str(exc), parent=self)
            return False
        self.shell.changelog.append(path.name, what)
        flag_warnings = [str(d) for d in result.warnings if "flag" in d.message or "slot" in d.message]
        if flag_warnings:
            messagebox.showwarning("Saved with warnings", "\n".join(flag_warnings[:6]), parent=self)
        if editor is not None:
            editor.reload_if_open(path)
        self._budget = None
        self.refresh()
        return True

    def open_in_script_editor(self, path: Path, function: Optional[str] = None,
                              chapter_id: Optional[str] = None) -> None:
        """Show ``path`` in a chapter's Script tab (startup.cmb opens in the
        current or first chapter's)."""
        open_script(self.shell, path, function, chapter_id)

    # -- chapter budget scan ----------------------------------------------------------------
    def budget(self) -> Optional[dict]:
        return self._budget

    def _scan_budget(self) -> None:
        if self._budget is not None or self._scan_running:
            return
        self._scan_running = True
        project = self.project
        ids = chapters.list_chapter_ids(project)
        result: dict = {}

        def work():
            for chapter_id in ids:
                path = script_sources.chapter_script(project, chapter_id)
                if path is None:
                    continue
                try:
                    result[chapter_id] = len(ef.local_flags(parse(script_sources.peek(project, path))))
                except Exception:  # noqa: BLE001 - one broken script shouldn't stop the scan
                    continue

        def done():
            self._scan_running = False
            self._budget = result
            self._campaign.refresh_budget()

        thread = threading.Thread(target=lambda: (work(), self.after(0, done)), daemon=True)
        thread.start()


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


def _ask_name(parent: tk.Misc, title: str, prompt: str, taken, initial: str = "") -> Optional[str]:
    while True:
        name = simpledialog.askstring(title, prompt, initialvalue=initial, parent=parent)
        if name is None:
            return None
        name = name.strip()
        problem = ef.check_flag_name(name, taken)
        if problem is None:
            return name
        messagebox.showerror(title, f"Can't use this name: {problem}.", parent=parent)
        initial = name


class _CampaignTab(ttk.Frame):
    def __init__(self, parent: tk.Misc, page: FlagsPage):
        super().__init__(parent, padding=12)
        self._page = page
        ttk.Label(self, style="Muted.TLabel", wraplength=980, justify="left",
                  text="Registered once at power-on: slots 0-7 by the engine, the rest by RegistGlobalFlags in "
                       "startup.cmb. Any chapter can set, clear or test them with set(\"name\"), clr(\"name\"), "
                       "get(\"name\"). Each campaign flag takes one slot away from every chapter.").pack(anchor="w")
        bar = ttk.Frame(self)
        bar.pack(side="bottom", fill="x")
        ttk.Button(bar, text="Add campaign flag…", command=self._add).pack(side="left")
        self._rename_button = ttk.Button(bar, text="Rename reserved slot…", command=self._rename, state="disabled")
        self._rename_button.pack(side="left", padx=(6, 0))
        ttk.Button(bar, text="Open startup.cmb in the Script editor",
                   command=self._open_startup).pack(side="left", padx=(6, 0))
        self._budget = ttk.Label(bar, style="Muted.TLabel")
        self._budget.pack(side="right")
        self._tree = _tree(self, {"slot": ("Slot", 60, False), "name": ("Name", 280, False),
                                  "meaning": ("Meaning", 360, True), "source": ("Registered by", 150, False)})
        self._tree.bind("<<TreeviewSelect>>", lambda e: self._sync_buttons())
        self._tree.bind("<Double-1>", lambda e: self._rename() if self._rename_button.instate(["!disabled"]) else None)
        self._flags: list[str] = []
        self._sites: list[ef.Registration] = []

    def refresh(self) -> None:
        project = self._page.project
        path = script_sources.startup_path(project)
        try:
            module = parse(script_sources.peek(project, path))
            self._sites = ef.registration_sites(module, "RegistGlobalFlags", "global")
        except (OSError, ValueError, ParseError):
            self._sites = []
        self._flags = list(ef.ENGINE_FLAGS) + [s.name for s in self._sites]
        self._tree.delete(*self._tree.get_children())
        seen = set()
        for slot, name in enumerate(self._flags):
            if slot < len(ef.ENGINE_FLAGS):
                meaning, source = ef.FLAG_GLOSSES.get(name, ""), "engine"
            else:
                meaning = ef.FLAG_GLOSSES.get(name, "")
                if name == ef.RESERVED_GLOBAL:
                    meaning = "Reserved, unused" + (" (and unreachable by name)" if name in seen else "")
                source = "startup.cmb"
            seen.add(name)
            tags = ("muted",) if name == ef.RESERVED_GLOBAL or slot < len(ef.ENGINE_FLAGS) else ()
            self._tree.insert("", "end", iid=str(slot), values=(slot, name, meaning, source), tags=tags)
        self.refresh_budget()
        self._sync_buttons()

    def refresh_budget(self) -> None:
        budget = self._page.budget()
        used = len(self._flags)
        if not budget:
            self._budget.config(text=f"{used} of 96 slots · counting chapter flags…")
            return
        chapter_id, most = max(budget.items(), key=lambda kv: kv[1])
        free = ef.SLOT_COUNT - used - most - 1
        self._budget.config(
            text=f"{used} of 96 slots · busiest chapter: {self._page.chapter_title(chapter_id)} with {most} "
                 f"chapter flags · {free} slot(s) to spare", style="Muted.TLabel" if free > 0 else "Warn.TLabel")

    def _selected_slot(self) -> Optional[int]:
        sel = self._tree.selection()
        return int(sel[0]) if sel else None

    def _sync_buttons(self) -> None:
        slot = self._selected_slot()
        renamable = slot is not None and slot >= len(ef.ENGINE_FLAGS) and self._flags[slot] == ef.RESERVED_GLOBAL
        self._rename_button.configure(state="normal" if renamable else "disabled")

    def _add(self) -> None:
        name = _ask_name(self, "Add campaign flag",
                         "Name of the new campaign flag (it is added at the end of RegistGlobalFlags):", self._flags)
        if name is None:
            return
        budget = self._page.budget() or {}
        most = max(budget.values(), default=0)
        problem = ef.capacity_problem(len(self._flags) + 1, most)
        if problem and not messagebox.askyesno("Table nearly full", f"{problem}.\n\nAdd it anyway?", parent=self):
            return
        self._page.edit_script(script_sources.startup_path(self._page.project),
                               lambda src: ef.append_registration(src, "RegistGlobalFlags", "global", name),
                               f"Added campaign flag {name}")

    def _rename(self) -> None:
        slot = self._selected_slot()
        if slot is None or slot < len(ef.ENGINE_FLAGS):
            return
        site = self._sites[slot - len(ef.ENGINE_FLAGS)]
        name = _ask_name(self, "Rename reserved slot",
                         f"New name for slot {slot} (unused in vanilla, so no save depends on it):", self._flags)
        if name is None:
            return
        self._page.edit_script(script_sources.startup_path(self._page.project),
                               lambda src: ef.rename_registration(src, site, site.name, name),
                               f"Renamed campaign flag slot {slot} to {name}")

    def _open_startup(self) -> None:
        self._page.open_in_script_editor(script_sources.startup_path(self._page.project), "RegistGlobalFlags")


class _ChapterTab(ttk.Frame):
    def __init__(self, parent: tk.Misc, page: FlagsPage):
        super().__init__(parent, padding=12)
        self._page = page
        top = ttk.Frame(self)
        top.pack(fill="x")
        ttk.Label(top, text="Chapter").pack(side="left")
        self._chapter_var = tk.StringVar()
        self._combo = ttk.Combobox(top, textvariable=self._chapter_var, state="readonly", width=48)
        self._combo.pack(side="left", padx=(6, 12))
        self._combo.bind("<<ComboboxSelected>>", lambda e: self.refresh())
        self._summary = ttk.Label(top, style="Muted.TLabel")
        self._summary.pack(side="left")
        ttk.Label(self, style="Muted.TLabel", wraplength=980, justify="left",
                  text="Registered by the chapter's Startup, from slot 95 downward, and cleared when the next "
                       "chapter starts. Talk, battle and base-conversation events use a flag named by their "
                       "label to run only once.").pack(anchor="w", pady=(8, 0))
        bar = ttk.Frame(self)
        bar.pack(side="bottom", fill="x")
        ttk.Button(bar, text="Add chapter flag…", command=self._add).pack(side="left")
        ttk.Button(bar, text="Open in the Script editor", command=self._open).pack(side="left", padx=(6, 0))
        self._tree = _tree(self, {"slot": ("Slot", 60, False), "name": ("Name", 260, False),
                                  "where": ("Registered in", 170, False), "uses": ("Used by", 420, True)})
        self._tree.bind("<Double-1>", lambda e: self._open())
        self._choices: list[tuple[str, str]] = []  # (label, chapter id)
        self._sites: list[ef.Registration] = []
        self._chapter_id: Optional[str] = None

    def fill_chapters(self) -> None:
        project = self._page.project
        ids = [c for c in chapters.list_chapter_ids(project) if script_sources.chapter_script(project, c)]
        self._choices = [(f"{c} · {self._page.chapter_title(c)}", c) for c in ids]
        self._combo.configure(values=[label for label, _c in self._choices])
        if self._chapter_id not in ids:
            self._chapter_id = ids[0] if ids else None
        self._chapter_var.set(next((label for label, c in self._choices if c == self._chapter_id), ""))

    def select(self, chapter_id: str) -> None:
        self._chapter_id = chapter_id
        self.fill_chapters()

    def refresh(self) -> None:
        if not self._choices:
            self.fill_chapters()
        picked = dict(self._choices).get(self._chapter_var.get())
        if picked:
            self._chapter_id = picked
        self._tree.delete(*self._tree.get_children())
        self._sites = []
        path = script_sources.chapter_script(self._page.project, self._chapter_id) if self._chapter_id else None
        if path is None:
            self._summary.config(text="No script for this chapter.")
            return
        try:
            module = parse(script_sources.peek(self._page.project, path))
        except (OSError, ValueError, ParseError) as exc:
            self._summary.config(text=f"Could not read {path.name}: {exc}")
            return
        self._sites = ef.registration_sites(module, "Startup", "regist")
        uses = ef.flag_uses(module)
        globals_ = self._page.global_flags()
        slots = ef.slot_names(globals_, [s.name for s in self._sites])
        # Registration i lands in the i-th filled slot counting down from 95 (none if the table is full).
        positions = [n for n in range(ef.SLOT_COUNT - 1, len(globals_) - 1, -1) if slots[n] is not None]
        for i, site in enumerate(self._sites):
            users = sorted({f"{fn} ({kind})" for fn, kind in uses.get(site.name, [])
                            if not (fn == site.function and kind == "regist")})
            slot = positions[i] if i < len(positions) else "none"
            self._tree.insert("", "end", iid=str(i), values=(slot, site.name, site.function, ", ".join(users) or "—"),
                              tags=() if users else ("muted",))
        self._summary.config(text=self._capacity_text(len(globals_), len(self._sites)))

    def _capacity_text(self, global_count: int, local_count: int) -> str:
        free = ef.SLOT_COUNT - global_count - local_count - 1
        problem = ef.capacity_problem(global_count, local_count)
        if problem:
            return problem
        return f"{local_count} chapter flags · {global_count} campaign flags · {free} slot(s) free"

    def _add(self) -> None:
        if not self._chapter_id:
            return
        path = script_sources.chapter_script(self._page.project, self._chapter_id)
        if path is None:
            return
        taken = [s.name for s in self._sites] + self._page.global_flags()
        name = _ask_name(self, "Add chapter flag",
                         f"Name of the new flag for chapter {self._chapter_id} (added after the last "
                         "registration in Startup):", taken)
        if name is None:
            return
        problem = ef.capacity_problem(len(self._page.global_flags()), len(self._sites) + 1)
        if problem:
            messagebox.showerror("Table full", f"{problem}.", parent=self)
            return
        self._page.edit_script(path, lambda src: ef.append_registration(src, "Startup", "regist", name),
                               f"Added chapter flag {name}")

    def _open(self) -> None:
        if not self._chapter_id:
            return
        path = script_sources.chapter_script(self._page.project, self._chapter_id)
        if path is None:
            return
        sel = self._tree.selection()
        function = self._sites[int(sel[0])].function if sel else "Startup"
        self._page.open_in_script_editor(path, function, self._chapter_id)


class _SaveTab(ttk.Frame):
    def __init__(self, parent: tk.Misc, page: FlagsPage):
        super().__init__(parent, padding=12)
        self._page = page
        top = ttk.Frame(self)
        top.pack(fill="x")
        ttk.Button(top, text="Open save file…", command=self._open).pack(side="left")
        self._file_label = ttk.Label(top, text="No save open (.gci, as exported by Dolphin or GCMM).",
                                     style="Muted.TLabel")
        self._file_label.pack(side="left", padx=(10, 0))
        row = ttk.Frame(self)
        row.pack(fill="x", pady=(8, 0))
        ttk.Label(row, text="Save block").pack(side="left")
        self._block_var = tk.StringVar()
        self._block_box = ttk.Combobox(row, textvariable=self._block_var, state="readonly", width=70)
        self._block_box.pack(side="left", padx=(6, 12))
        self._block_box.bind("<<ComboboxSelected>>", lambda e: self._show_block())
        self._only_set = tk.BooleanVar(value=False)
        ttk.Checkbutton(row, text="Only named or set flags", variable=self._only_set,
                        command=self._show_block).pack(side="left")
        ttk.Label(self, style="Muted.TLabel", wraplength=980, justify="left",
                  text="Double-click a flag (or press Space) to switch it. Chapter flags are named from the "
                       "script of the block's map. Keep the game closed while you overwrite a save it uses."
                  ).pack(anchor="w", pady=(8, 0))
        bar = ttk.Frame(self)
        bar.pack(side="bottom", fill="x")
        self._save_button = ttk.Button(bar, text="Save", command=self._save, state="disabled")
        self._save_button.pack(side="left")
        self._save_as_button = ttk.Button(bar, text="Save as…", command=self._save_as, state="disabled")
        self._save_as_button.pack(side="left", padx=(6, 0))
        self._status = ttk.Label(bar, style="Muted.TLabel")
        self._status.pack(side="left", padx=(12, 0))
        self._tree = _tree(self, {"on": ("Set", 50, False), "slot": ("Slot", 60, False),
                                  "name": ("Name", 280, False), "meaning": ("Meaning", 420, True)})
        self._tree.bind("<Double-1>", lambda e: self._toggle())
        self._tree.bind("<space>", lambda e: self._toggle())
        self._path: Optional[Path] = None
        self._data: Optional[bytearray] = None
        self._blocks: list[ef.SaveBlock] = []
        self._block: Optional[ef.SaveBlock] = None
        self._bits: list[bool] = []
        self._names: list[Optional[str]] = []
        self._dirty = False

    def _open(self) -> None:
        if self._dirty and not messagebox.askyesno("Discard changes?", "The open save has unsaved flag changes. "
                                                   "Discard them?", parent=self):
            return
        chosen = filedialog.askopenfilename(title="Open a save file", parent=self,
                                            filetypes=[("GameCube saves", "*.gci"), ("All files", "*.*")])
        if not chosen:
            return
        try:
            data = bytearray(Path(chosen).read_bytes())
        except OSError as exc:
            messagebox.showerror("Could not open the save", str(exc), parent=self)
            return
        blocks = ef.save_blocks(bytes(data))
        if not blocks:
            messagebox.showerror("Not a Path of Radiance save", "No save blocks were found in this file.", parent=self)
            return
        self._path, self._data, self._blocks, self._dirty = Path(chosen), data, blocks, False
        self._file_label.config(text=str(self._path))
        labels = [self._block_label(b) for b in blocks]
        self._block_box.configure(values=labels)
        newest = max(range(len(blocks)), key=lambda i: blocks[i].sequence)
        self._block_var.set(labels[newest])
        self._show_block()

    @staticmethod
    def _block_label(b: ef.SaveBlock) -> str:
        kind = "checkpoint" if b.size == 0x6000 else "file"
        crc = "" if b.crc_ok else " · CHECKSUM BAD"
        return f"{kind} @0x{b.offset:05x} · {b.chapter_map or '?'} · sequence {b.sequence} · " \
               f"kind {b.save_kind} mode {b.save_mode}{crc}"

    def _chapter_names(self, block: ef.SaveBlock) -> list[Optional[str]]:
        globals_ = self._page.global_flags()
        locals_: list[str] = []
        m = block.chapter_map
        if m.startswith("bmap") and m[4:6].isdigit():
            path = script_sources.chapter_script(self._page.project, m[4:6])
            if path is not None:
                try:
                    locals_ = ef.local_flags(parse(script_sources.peek(self._page.project, path)))
                except (OSError, ValueError, ParseError):
                    pass
        return ef.slot_names(globals_, locals_)

    def _show_block(self) -> None:
        if self._data is None:
            return
        labels = [self._block_label(b) for b in self._blocks]
        if self._block_var.get() not in labels:
            return
        block = self._blocks[labels.index(self._block_var.get())]
        if block is not self._block:
            self._block = block
            self._bits = ef.read_flag_bits(bytes(self._data), block)
            self._names = self._chapter_names(block)
        self._tree.delete(*self._tree.get_children())
        for slot in range(ef.SLOT_COUNT):
            name, on = self._names[slot], self._bits[slot]
            if self._only_set.get() and not on and name is None:
                continue
            meaning = ef.FLAG_GLOSSES.get(name or "", "")
            if name is None:
                meaning = "No name in this chapter"
            elif name == ef.RESERVED_GLOBAL:
                meaning = "Reserved, unused"
            self._tree.insert("", "end", iid=str(slot), values=(ON if on else OFF, slot, name or "", meaning),
                              tags=() if name else ("muted",))
        self._sync()

    def _toggle(self) -> None:
        sel = self._tree.selection()
        if not sel or self._block is None:
            return
        slot = int(sel[0])
        self._bits[slot] = not self._bits[slot]
        self._tree.set(sel[0], "on", ON if self._bits[slot] else OFF)
        ef.write_flag_bits(self._data, self._block, self._bits)
        self._dirty = True
        self._sync()

    def _sync(self) -> None:
        state = "normal" if self._data is not None else "disabled"
        self._save_as_button.configure(state=state)
        self._save_button.configure(state="normal" if self._dirty else "disabled")
        count = sum(self._bits) if self._bits else 0
        self._status.config(text=(f"{count} flag(s) set" + (" · unsaved changes" if self._dirty else ""))
                            if self._block is not None else "")

    def _save(self) -> None:
        if self._path is not None:
            self._write(self._path)

    def _save_as(self) -> None:
        if self._data is None:
            return
        chosen = filedialog.asksaveasfilename(title="Save the edited save as", parent=self, defaultextension=".gci",
                                              initialfile=self._path.name if self._path else "save.gci",
                                              filetypes=[("GameCube saves", "*.gci")])
        if chosen:
            self._write(Path(chosen))

    def _write(self, path: Path) -> None:
        try:
            path.write_bytes(bytes(self._data))
        except OSError as exc:
            messagebox.showerror("Could not write the save", str(exc), parent=self)
            return
        self._path, self._dirty = path, False
        self._file_label.config(text=str(path))
        self._page.shell.changelog.append(path.name, "Edited save flags")
        self._sync()
