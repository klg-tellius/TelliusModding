"""Chapters: a card per chapter, and a page per chapter gathering its map,
deployment, dialogue, script and base shops, with an overview of who is in it, what is
said and which script events it has.

Chapter IDs are disc file numbers (the Prologue is ``01``); titles come from
the game's own text (``MCTnn``). A chapter with a mid-chapter map change has
several map folders (``bmap06``, ``bmap06_2``): the **Phase** selector picks
which one the Map and Deployment tabs show.
"""

from __future__ import annotations

import re
import tkinter as tk
from tkinter import messagebox, ttk

from ... import chapters
from ...formats.cmb.catalog import TRIGGERS
from ...project_index import difficulty_name
from ..deployment_editor import DeploymentEditor
from ..dialogue_editor import DialogueEditor
from ..map_builder import MapBuilder
from ..map_editor import MapEditor
from ..script_editor import ScriptEditor
from ..shop_editor import ShopEditor
from ..shell import Page, plain_text
from ..widgets import Card, CardGrid, Link, ScrollFrame, section_header

TABS = ["overview", "build", "deployment", "dialogue", "script", "shops"]
#: Old routes to tabs that were merged into another.
TAB_ALIASES = {"map": "build"}
TAB_LABELS = {"overview": "Overview", "build": "Build", "deployment": "Deployment",
              "dialogue": "Dialogue", "script": "Script", "shops": "Shops"}


class ChaptersHub(Page):
    kind = "chapters"

    def __init__(self, shell):
        super().__init__(shell)
        top = ttk.Frame(self, style="Page.TFrame", padding=(28, 12, 28, 8))
        top.pack(fill="x")
        ttk.Label(top, text="Chapters", style="Title.TLabel").pack(side="left")
        self._query = tk.StringVar()
        search = ttk.Entry(top, textvariable=self._query, width=30)
        search.pack(side="right")
        ttk.Label(top, text="Filter", style="Muted.TLabel").pack(side="right", padx=(0, 8))
        self._query.trace_add("write", lambda *_: (self._filter(), self._scroll.scroll_top()))
        self._scroll = ScrollFrame(self, padding=(28, 4, 28, 28))
        self._scroll.pack(fill="both", expand=True)
        self._grid = CardGrid(self._scroll.body, card_width=260)
        self._grid.pack(fill="x")
        self._note = ttk.Label(self._scroll.body, style="Muted.TLabel", wraplength=900, justify="left",
                               text="Chapter IDs are the disc's file numbers (the Prologue is 01). "
                                    "An added chapter is a copy of another one's files: the game has no way to "
                                    "reach it through normal play.")
        self._note.pack(anchor="w", pady=(12, 0))
        self._built_for = None
        self._keys: dict = {}

    def crumbs(self, route):
        return [("Chapters", None)]

    def show(self, route) -> bool:
        if self._built_for is not self.shell.index:
            self._build()
        return True

    def index_changed(self) -> None:
        if self.winfo_ismapped():
            self._build()

    def _build(self) -> None:
        index = self.shell.index
        self._built_for = index
        self._grid.clear()
        if index is None:
            self._grid.add(None, ttk.Label(self._grid, text="Indexing…", style="Muted.TLabel"))
            self._grid.done()
            return
        self._keys = {}
        for c in index.chapters:
            chips = []
            if c.message_count:
                chips.append(f"{c.message_count} messages")
            if c.units_by_difficulty:
                chips.append(f"{c.units_by_difficulty.get('n', max(c.units_by_difficulty.values()))} units")
            if len(c.phases) > 1:
                chips.append((f"+{len(c.phases) - 1} phase{'s' if len(c.phases) > 2 else ''}", "accent_bg"))
            if not c.has_map:
                chips.append(("no map", "chip_named"))
            key = (c.id, c.title)
            self._keys[key] = True
            self._grid.add(key, Card(self._grid, title=c.title, subtitle=f"Disc {c.id}  ·  " + ", ".join(c.phases or ("no map folder",)),
                                     chips=tuple(chips), width=260,
                                     on_click=lambda cid=c.id: self.shell.navigate(("chapter", cid))))
        self._grid.add(("+", "add chapter"), Card(self._grid, title="Add chapter…",
                                                   subtitle="Copy a chapter's files under a new number",
                                                   icon="+", width=260, on_click=self._add_chapter))
        self._grid.done()
        self._filter()

    def _filter(self) -> None:
        words = self._query.get().casefold().split()
        self._grid.filter(lambda key: key is None or all(w in f"{key[0]} {key[1]}".casefold() for w in words))

    def _add_chapter(self) -> None:
        ids = chapters.list_chapter_ids(self.project)
        if not ids:
            return
        dialog = AddChapterDialog(self, ids)
        self.wait_window(dialog)
        if dialog.result is None:
            return
        source_id, new_id = dialog.result
        try:
            chapters.duplicate_chapter(self.project, source_id, new_id)
        except ValueError as exc:
            messagebox.showerror("Could not add chapter", str(exc), parent=self)
            return
        page = self.shell.existing_page("chapter")
        if page is not None:
            page.refresh_chapter_lists()
        self.shell.changelog.append(
            f"Chapter {new_id}", f"Added chapter {new_id} (duplicated from {source_id}) - not reachable via normal play")
        self.shell.navigate(("chapter", new_id.zfill(2)))


class ChapterPage(Page):
    """Route ``("chapter", id[, tab[, ...]])``; deep links:
    ``dialogue, message_id`` · ``deployment, folder, difficulty, section, unit`` ·
    ``script, function``."""

    kind = "chapter"

    def __init__(self, shell):
        super().__init__(shell)
        self._chapter: str | None = None
        self._phase: str | None = None
        self._difficulty = "n"
        self._ids: list[str] = []

        header = ttk.Frame(self, style="Page.TFrame", padding=(28, 6, 28, 8))
        header.pack(fill="x")
        left = ttk.Frame(header, style="Page.TFrame")
        left.pack(side="left", fill="x", expand=True)
        self._title = ttk.Label(left, text="", style="Title.TLabel")
        self._title.pack(anchor="w")
        self._subtitle = ttk.Label(left, text="", style="Muted.TLabel")
        self._subtitle.pack(anchor="w")
        right = ttk.Frame(header, style="Page.TFrame")
        right.pack(side="right")
        self._phase_var = tk.StringVar()
        self._phase_label = ttk.Label(right, text="Phase", style="Muted.TLabel")
        self._phase_combo = ttk.Combobox(right, textvariable=self._phase_var, state="readonly", width=12)
        self._phase_combo.bind("<<ComboboxSelected>>", lambda e: self._set_phase(self._phase_var.get()))
        self._prev = ttk.Button(right, text="‹ Previous", command=lambda: self._step(-1))
        self._next = ttk.Button(right, text="Next ›", command=lambda: self._step(1))
        self._next.pack(side="right")
        self._prev.pack(side="right", padx=(0, 6))

        self._notebook = ttk.Notebook(self)
        self._notebook.pack(fill="both", expand=True, padx=16, pady=(0, 8))
        self._overview = ScrollFrame(self._notebook, padding=(16, 12))
        self._notebook.add(self._overview, text="Overview")
        project, log = self.project, shell.changelog
        # The map's data; the Build tab shows and edits it (the MapEditor has no tab of its own).
        self._map = MapEditor(self._notebook, project, log)
        self._deployment = DeploymentEditor(self._notebook, project, log,
                                            on_navigate_to_character=lambda pid: shell.navigate(("character", pid)))
        self._dialogue = DialogueEditor(self._notebook, project, log)
        self._script = ScriptEditor(self._notebook, project, log)
        self._shops = ShopEditor(self._notebook, project, log, index_provider=lambda: shell.index,
                                 session_provider=lambda: shell.session)
        # The Build tab edits the Map and Deployment editors' data; it has none of its own,
        # so it isn't one of panels() (their dirty state covers it).
        self._build = MapBuilder(self._notebook, project, log, self._map, self._deployment,
                                 index_provider=lambda: shell.index, session_provider=lambda: shell.session,
                                 on_navigate_to_character=lambda pid: shell.navigate(("character", pid)))
        for key, panel in (("build", self._build), ("deployment", self._deployment), ("dialogue", self._dialogue),
                           ("script", self._script), ("shops", self._shops)):
            self._notebook.add(panel, text=TAB_LABELS[key])
        self._notebook.bind("<<NotebookTabChanged>>", lambda e: self._on_tab_changed())
        self._tab = "overview"

    # -- Page ----------------------------------------------------------------------------
    def panels(self):
        return [self._map, self._deployment, self._dialogue, self._script, self._shops]

    def refresh_chapter_lists(self) -> None:
        for panel in self.panels():
            panel.refresh_chapter_list()

    @staticmethod
    def _route_tab(route):
        tab = route[2] if len(route) > 2 else None
        tab = TAB_ALIASES.get(tab, tab)
        return tab if tab in TABS else None

    def crumbs(self, route):
        title = self._title_of(route[1])
        tab = self._route_tab(route) or "overview"
        crumbs = [("Chapters", ("chapters",)), (title, ("chapter", route[1]))]
        if tab != "overview":
            crumbs.append((TAB_LABELS[tab], None))
        return crumbs

    def history_label(self, route):
        return self._title_of(route[1])

    def index_changed(self) -> None:
        if self._chapter is not None:
            self._update_header()
            self._render_overview()

    def show(self, route) -> bool:
        chapter_id = route[1] if len(route) > 1 else None
        self._ids = chapters.list_chapter_ids(self.project)
        if chapter_id not in self._ids:
            return False
        if chapter_id != self._chapter:
            if not self._switch_to(chapter_id):
                return False
        tab = self._route_tab(route)
        if tab is not None:
            self._select_tab(tab)
            self._deep_link(tab, route[3:])
        elif self._tab not in TABS:
            self._select_tab("overview")
        return True

    # -- loading a chapter -------------------------------------------------------------------
    def _switch_to(self, chapter_id: str) -> bool:
        # An open shared script (startup.cmb) isn't this chapter's: it stays open with its edits.
        # The shop files hold every chapter's shops, so their edits stay too.
        dirty = [p for p in self.panels() if p.dirty and p is not self._shops
                 and (p is not self._script or self._script.showing_chapter_script)]
        if dirty:
            names = ", ".join(p.display_name for p in dirty)
            if not messagebox.askyesno(
                    "Discard changes?",
                    f"{self._title_of(self._chapter)} has unsaved changes in: {names}.\n\n"
                    "Opening another chapter discards them. Continue?", icon="warning", parent=self):
                return False
            for panel in dirty:
                panel._dirty = False  # the user chose to drop them; the panels reload below
        self._chapter = chapter_id
        paths = chapters.chapter_paths(self.project, chapter_id)
        phases = chapters.chapter_phases(self.project, chapter_id)
        self._dialogue.select_chapter(paths.dialogue)
        self._script.select_chapter(paths.script)
        self._shops.select_chapter(chapter_id)
        self._phase_combo.configure(values=phases)
        if len(phases) > 1:
            self._phase_label.pack(side="left", padx=(0, 6))
            self._phase_combo.pack(side="left", padx=(0, 18))
        else:
            self._phase_label.pack_forget()
            self._phase_combo.pack_forget()
        self._phase = None
        self._set_phase(phases[0] if phases else None)
        self._update_header()
        self._render_overview()
        return True

    def _set_phase(self, folder: str | None) -> None:
        if folder == self._phase:
            return
        self._phase = folder
        self._phase_var.set(folder or "")
        deployment, map_cmp = chapters.phase_paths(self.project, folder) if folder else (None, None)
        self._deployment.select_chapter(deployment)
        self._map.select_chapter(map_cmp)
        if self._chapter is not None:
            self._render_overview()

    def _update_header(self) -> None:
        cid = self._chapter
        self._title.configure(text=self._title_of(cid))
        paths = chapters.chapter_paths(self.project, cid)
        files = [p.name for p in (paths.dialogue, paths.script) if p is not None]
        phases = chapters.chapter_phases(self.project, cid)
        self._subtitle.configure(text="  ·  ".join([f"Disc {cid}"] + files + [", ".join(phases)] if phases else
                                                   [f"Disc {cid}"] + files))
        position = self._ids.index(cid) if cid in self._ids else -1
        self._prev.configure(state="normal" if position > 0 else "disabled")
        self._next.configure(state="normal" if 0 <= position < len(self._ids) - 1 else "disabled")

    def _title_of(self, chapter_id) -> str:
        index = self.shell.index
        if index is not None and chapter_id in index.by_chapter:
            return index.by_chapter[chapter_id].title
        return f"Chapter {chapter_id}"

    def _step(self, step: int) -> None:
        position = self._ids.index(self._chapter) + step
        if 0 <= position < len(self._ids):
            self.shell.navigate(("chapter", self._ids[position], self._tab))

    # -- tabs ------------------------------------------------------------------------------------
    def _select_tab(self, tab: str) -> None:
        self._tab = tab
        self._notebook.select(TABS.index(tab))

    def _on_tab_changed(self) -> None:
        self._tab = TABS[self._notebook.index("current")]
        route = self.shell.route
        if route and route[0] == self.kind and self._chapter is not None and route[2:3] != (self._tab,):
            self.shell.replace_route(("chapter", self._chapter, self._tab))

    def _deep_link(self, tab: str, args: tuple) -> None:
        if not args:
            return
        if tab == "dialogue":
            self._dialogue.select_message(args[0])
        elif tab == "script":
            if self._script.show_chapter_script():
                self.after_idle(lambda: self._script.select_function(args[0]))
        elif tab == "deployment" and len(args) >= 4:
            folder, difficulty, section, unit = args[:4]
            if folder != self._phase:
                self._set_phase(folder)
            self._deployment.select_unit(difficulty, section, int(unit))

    # -- overview --------------------------------------------------------------------------------
    def _render_overview(self) -> None:
        body = self._overview.body
        for child in body.winfo_children():
            child.destroy()
        self._overview.scroll_top()
        index = self.shell.index
        if index is None:
            ttk.Label(body, text="Indexing…", style="Muted.TLabel").pack(anchor="w")
            return
        self._render_cast(body, index)
        self._render_dialogue(body, index)
        self._render_script(body, index)

    def _render_cast(self, body, index) -> None:
        head = section_header(body, "Cast", self._phase or "")
        head.pack(fill="x", pady=(0, 8))
        if self._phase is None:
            ttk.Label(body, text="This chapter has no map folder.", style="Muted.TLabel").pack(anchor="w")
            return
        difficulties = sorted({d.difficulty for d in index.deployments if d.folder == self._phase},
                              key=lambda x: "nhmc".find(x))
        if difficulties:
            if self._difficulty not in difficulties:
                self._difficulty = difficulties[0]
            var = tk.StringVar(value=difficulty_name(self._difficulty))
            names = {difficulty_name(d): d for d in difficulties}
            combo = ttk.Combobox(head, textvariable=var, values=list(names), state="readonly", width=16)
            combo.pack(side="right")
            ttk.Label(head, text="Deployment file", style="Muted.TLabel").pack(side="right", padx=(0, 8))
            combo.bind("<<ComboboxSelected>>", lambda e: self._set_difficulty(names[var.get()]))
        units = index.cast(self._phase, self._difficulty)
        if not units:
            ttk.Label(body, text="No units in this deployment file.", style="Muted.TLabel").pack(anchor="w")
            return
        sections: dict[str, list] = {}
        for unit in units:
            sections.setdefault(unit.section, []).append(unit)
        for section, members in sections.items():
            row = ttk.Frame(body, style="Page.TFrame")
            row.pack(fill="x", pady=(10, 6))
            ttk.Label(row, text=_section_title(section), style="Heading.TLabel").pack(side="left")
            ttk.Label(row, text=f"{section}  ·  {len(members)} unit{'s' if len(members) != 1 else ''}",
                      style="Faint.TLabel").pack(side="left", padx=(8, 0))
            first = members[0]
            Link(row, "Edit in Deployment ›", lambda u=first: self.shell.navigate(
                ("chapter", self._chapter, "deployment", u.folder, u.difficulty, u.section, u.unit_index))
                 ).pack(side="right")
            grid = CardGrid(body, card_width=230, gap=8)
            grid.pack(fill="x")
            for i, unit in enumerate(members):
                character = index.by_pid.get(unit.pid)
                name = character.name if character and character.name else unit.pid
                card = Card(grid, title=name, subtitle=index.class_names.get(unit.jid) or unit.jid,
                            caption=f"{unit.pid}  ·  tile {unit.x}, {unit.y}", width=230, image_box=(4, 2),
                            on_click=lambda pid=unit.pid: self.shell.navigate(("character", pid)))
                grid.add(i, card)
                if character is not None:
                    self.shell.portraits.request(character.fid, 44, lambda photo, c=card: _set_image(c, photo))
            grid.done()

    def _set_difficulty(self, difficulty: str) -> None:
        self._difficulty = difficulty
        self._render_overview()

    def _render_dialogue(self, body, index) -> None:
        messages = index.messages_by_chapter.get(self._chapter, [])
        head = section_header(body, "Dialogue", f"{len(messages)} messages")
        head.pack(fill="x", pady=(28, 8))
        Link(head, "Open Dialogue ›", lambda: self.shell.navigate(("chapter", self._chapter, "dialogue"))).pack(side="right")
        groups: dict[str, list] = {}
        for msg_id, text in messages:
            groups.setdefault(_message_group(msg_id), []).append((msg_id, text))
        for group, items in groups.items():
            box = ttk.Frame(body, style="Surface.TFrame", padding=(14, 10))
            box.pack(fill="x", pady=(0, 8))
            ttk.Label(box, text=f"{group}  ({len(items)})", style="SurfaceHeading.TLabel").pack(anchor="w", pady=(0, 4))
            for msg_id, text in items:
                line = ttk.Frame(box, style="Surface.TFrame")
                line.pack(fill="x")
                Link(line, msg_id, lambda m=msg_id: self.shell.navigate(("chapter", self._chapter, "dialogue", m)),
                     bg_token="surface").pack(side="left")
                ttk.Label(line, text=plain_text(text)[:110], style="SurfaceMuted.TLabel").pack(side="left", padx=(10, 0))

    def _render_script(self, body, index) -> None:
        functions = index.script_functions(self._chapter)
        events = [(name, kind) for name, kind in functions if kind or not name.startswith("func_")]
        head = section_header(body, "Script", f"{len(functions)} functions, {len(events)} named or triggered")
        head.pack(fill="x", pady=(28, 8))
        Link(head, "Open Script ›", lambda: self.shell.navigate(("chapter", self._chapter, "script"))).pack(side="right")
        if not functions:
            ttk.Label(body, text="No script for this chapter.", style="Muted.TLabel").pack(anchor="w")
            return
        box = ttk.Frame(body, style="Surface.TFrame", padding=(14, 10))
        box.pack(fill="x")
        for i, (name, kind) in enumerate(events):
            trigger = TRIGGERS.get(kind)
            r, c = divmod(i, 2)
            cell = ttk.Frame(box, style="Surface.TFrame")
            cell.grid(row=r, column=c, sticky="w", padx=(0, 40), pady=1)
            Link(cell, name, lambda n=name: self.shell.navigate(("chapter", self._chapter, "script", n)),
                 bg_token="surface").pack(side="left")
            if kind:
                ttk.Label(cell, text=trigger.title if trigger else f"trigger {kind}",
                          style="SurfaceMuted.TLabel").pack(side="left", padx=(8, 0))


def _set_image(card: Card, photo) -> None:
    if card.winfo_exists():
        card.set_image(photo)


def _section_title(section: str) -> str:
    """``bmap03_mikata_n`` -> ``Player units``; other sections keep their
    own name (``first_boss``), since only these two are certain."""
    core = re.sub(r"^(?:bmap\d+(?:_\d+)?|always)_", "", section)
    core = re.sub(r"_[nhmc]$", "", core)
    if core == "mikata":
        return "Player units"
    if core.endswith("boss"):
        return "Boss" + (f" ({core})" if core != "boss" else "")
    return core.replace("_", " ").capitalize() or section


def _message_group(message_id: str) -> str:
    """``MS_03_OP_01`` -> ``OP``; death quotes and others by their prefix."""
    parts = message_id.split("_")
    if parts[0] == "MS" and len(parts) > 2:
        return parts[2]
    return parts[0]


class AddChapterDialog(tk.Toplevel):
    """Pick a chapter to copy and a new chapter number. The caveat that the
    game can't reach the copy is shown here, where the choice is made."""

    def __init__(self, parent: tk.Misc, existing_chapter_ids: list[str]):
        super().__init__(parent)
        self.title("Add Chapter")
        self.resizable(False, False)
        self.result: tuple[str, str] | None = None
        frame = ttk.Frame(self, padding=16)
        frame.pack(fill="both", expand=True)
        ttk.Label(
            frame,
            text="Copies an existing chapter's dialogue, script, deployment and map\n"
                 "as a starting template for a new chapter number.\n\n"
                 "This does NOT make the new chapter playable: nothing in the\n"
                 "chapter scripts says which chapter comes after which, so the\n"
                 "game has no way to load it through normal play.",
            style="Warn.TLabel", justify="left",
        ).grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 12))
        ttk.Label(frame, text="Duplicate from:").grid(row=1, column=0, sticky="w", pady=4)
        self._source_var = tk.StringVar(value=existing_chapter_ids[0])
        ttk.Combobox(frame, textvariable=self._source_var, values=existing_chapter_ids, state="readonly",
                     width=12).grid(row=1, column=1, sticky="w", padx=(6, 0))
        ttk.Label(frame, text="New chapter number:").grid(row=2, column=0, sticky="w", pady=4)
        self._new_id_var = tk.StringVar()
        ttk.Entry(frame, textvariable=self._new_id_var, width=14).grid(row=2, column=1, sticky="w", padx=(6, 0))
        self._existing_ids = set(existing_chapter_ids)
        buttons = ttk.Frame(frame)
        buttons.grid(row=3, column=0, columnspan=2, sticky="e", pady=(12, 0))
        ttk.Button(buttons, text="Cancel", command=self.destroy).pack(side="right")
        ttk.Button(buttons, text="Add Chapter", style="Accent.TButton", command=self._on_apply).pack(
            side="right", padx=(0, 6))
        self.transient(parent.winfo_toplevel())
        self.grab_set()

    def _on_apply(self) -> None:
        new_id = self._new_id_var.get().strip()
        if not new_id or not new_id.isdigit():
            messagebox.showerror("Invalid chapter number", "Enter a whole number.", parent=self)
            return
        if new_id in self._existing_ids or new_id.zfill(2) in self._existing_ids:
            messagebox.showerror("Already exists", f"Chapter {new_id} already exists.", parent=self)
            return
        self.result = (self._source_var.get(), new_id)
        self.destroy()
