"""Chapters: a card per chapter, and a page per chapter gathering its map and
deployment (the Build tab), dialogue, script, base shops and battle scenes
(the map's ``BattleTerrData`` row, ``battle_scene_editor.py``), with an
overview of who is in it, what is said and which script events it has.

Chapter IDs are disc file numbers (the Prologue is ``01``); titles come from
the game's own text (``MCTnn``). A chapter with a mid-chapter map change has
several map folders (``bmap06``, ``bmap06_2``): the **Phase** selector picks
which one the Build, Settings and Battle scenes tabs show.

The **Settings** tab (``chapter_settings.py``) edits the phase map's lighting,
fog, grid colour and grid border, and the chapter's Game Data › Chapters record.

**Add chapter** creates a playable chapter (``chapters.add_story_chapter``) and
places it in the story flow; each chapter's Overview shows and changes which
chapter comes next (``game_code.chapter_flow``, a table patched into ``main.dol``).

**Play in Dolphin** boots the extracted files straight into the chapter, with a fresh army, on
the chosen difficulty (``emulator.prepare_chapter_run``, ``game_code.chapter_jump``).
"""

from __future__ import annotations

import re
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk

from ... import chapters, script_sources
from ...exceptions import ModdingError
from ...config import load_setting, save_setting
from ...game_code import chapter_flow, chapter_jump
from ...formats.cmb.catalog import TRIGGERS
from ...game_profile import CHAPTERS, profile_of
from ...project_index import difficulty_name
from ..battle_scene_editor import BattleScenePanel
from ..chapter_settings import ChapterSettingsPanel
from ..deployment_editor import DeploymentEditor
from ..dialogue_editor import DialogueEditor
from ..map_builder import MapBuilder
from ..map_editor import MapEditor
from ..script_editor import ScriptEditor
from ..shop_editor import ShopEditor
from ..shell import Page, plain_text
from ..widgets import Card, CardGrid, Link, ScrollFrame, section_header

TABS = ["overview", "build", "settings", "dialogue", "script", "shops", "battle"]
#: Old routes to tabs that were merged into another.
TAB_ALIASES = {"map": "build", "deployment": "build"}
TAB_LABELS = {"overview": "Overview", "build": "Build", "settings": "Settings", "dialogue": "Dialogue", "script": "Script", "shops": "Shops",
              "battle": "Battle scenes"}


def open_flow(project) -> tuple[chapter_flow.ChapterFlow | None, str]:
    """The project's story flow, or None and why it can't be edited."""
    from ...game_code.editor import CodeEditor
    try:
        flow = chapter_flow.ChapterFlow(CodeEditor(project.extracted_dir, project.write_keeping_original))
    except (OSError, ModdingError) as exc:
        return None, f"Could not open sys/main.dol: {exc}"
    return (flow, "") if flow.available else (None, flow.unavailable_reason)


def _flow_label(chapter: int, titles: dict) -> str:
    if chapter == chapter_flow.GAME_CLEARED:
        return "32 · Ending"
    return f"{chapter:02d} · {chapters.chapter_display_title(f'{chapter:02d}', titles)}"


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
        body = self._scroll.body
        self._actions = CardGrid(body, card_width=260)
        self._actions.pack(fill="x")
        self._story_header = section_header(body, "Story", "in the order a new game plays them")
        self._story_header.pack(anchor="w", pady=(20, 8), fill="x")
        self._story = CardGrid(body, card_width=260)
        self._story.pack(fill="x")
        self._other_header = section_header(body, "Other chapters",
                                            "not played in the story: trial maps, tutorials, unused records "
                                            "and added chapters no chapter leads to")
        self._other_header.pack(anchor="w", pady=(20, 8), fill="x")
        self._other = CardGrid(body, card_width=260)
        self._other.pack(fill="x")
        self._note = ttk.Label(body, style="Muted.TLabel", wraplength=900, justify="left",
                               text="Disc numbers are the game's chapter numbers (the Prologue is 01). An added "
                                    "chapter starts as a copy of another one; each chapter's Overview sets what "
                                    "comes next.")
        self._note.pack(anchor="w", pady=(16, 0))
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
        for grid in (self._actions, self._story, self._other):
            grid.clear()
        if index is None:
            self._story.add(None, ttk.Label(self._story, text="Indexing…", style="Muted.TLabel"))
            for grid in (self._actions, self._story, self._other):
                grid.done()
            return
        self._keys = {}
        for key, title, subtitle, icon, command in (
                (("+", "add chapter"), "Add chapter…", "A new playable chapter, from a template", "+",
                 self._add_chapter),
                (("+", "new campaign"), "New campaign…", "Several chapters and characters at once", "+",
                 self._new_campaign),
                (("+", "story order"), "Story order…", "Reorder the chapters you added", "↕", self._story_order)):
            self._actions.add(key, Card(self._actions, title=title, subtitle=subtitle, icon=icon, width=260,
                                        on_click=command))
        self._actions.done()

        flow, _why = open_flow(self.project)
        by_id = {c.id: c for c in index.chapters}
        if flow is not None:
            order = [f"{n:02d}" for n in flow.order()]
        else:  # no story flow to read: the retail story
            order = [c for c in by_id if 1 <= int(c) <= chapter_flow.LAST_RETAIL_STORY]
        position = {cid: n for n, cid in enumerate((c for c in order if c in by_id), 1)}
        story = sorted((c for c in index.chapters if c.id in position), key=lambda c: position[c.id])
        other = [c for c in index.chapters if c.id not in position]
        for grid, rows in ((self._story, story), (self._other, other)):
            for c in rows:
                chips = []
                if c.id in position:
                    chips.append((f"#{position[c.id]}", "accent_bg"))
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
                grid.add(key, Card(grid, title=c.title,
                                   subtitle=f"Disc {c.id}  ·  " + ", ".join(c.phases or ("no map folder",)),
                                   chips=tuple(chips), width=260,
                                   on_click=lambda cid=c.id: self.shell.navigate(("chapter", cid))))
            grid.done()
        if other:
            self._other_header.pack(anchor="w", pady=(20, 8), fill="x", before=self._other)
        else:
            self._other_header.pack_forget()
        self._filter()

    def _filter(self) -> None:
        words = self._query.get().casefold().split()
        for grid in (self._actions, self._story, self._other):
            grid.filter(lambda key: key is None or all(w in f"{key[0]} {key[1]}".casefold() for w in words))

    def _add_chapter(self) -> None:
        ids = chapters.list_chapter_ids(self.project)
        session = self.shell.session
        if not ids or not session.available:
            messagebox.showerror("Could not add chapter", "This project has no chapters or no FE8Data.bin.", parent=self)
            return
        from ...formats import fe8data
        records = fe8data.read_chapter_data(session.data)
        templates = [c for c in ids if any(r.chapter_id == int(c) for r in records)]
        free = chapters.free_chapter_ids(self.project, [r.chapter_id for r in records])
        flow, why = open_flow(self.project)
        if not templates or not free:
            messagebox.showerror("Could not add chapter", "No template chapter or no free chapter number.", parent=self)
            return
        titles = chapters.chapter_titles(self.project)
        dialog = AddChapterDialog(self, templates, free, titles, flow, why)
        self.wait_window(dialog)
        if dialog.result is None:
            return
        source_id, new_id, title, after = dialog.result
        if session.dirty and not messagebox.askyesno(
                "Save FE8Data.bin?", "Adding a chapter saves FE8Data.bin, including its unsaved edits. Continue?",
                parent=self):
            return
        try:
            plan = chapters.add_story_chapter(self.project, session.data, source_id, new_id, title, after, flow)
        except (ValueError, OSError, ModdingError) as exc:
            messagebox.showerror("Could not add chapter", str(exc), parent=self)
            return
        session.data = plan.fe8data
        session.changed(self)
        try:
            session.save()
        except OSError as exc:
            messagebox.showerror("Could not save FE8Data.bin", str(exc), parent=self)
        padded = f"{new_id:02d}"
        where = f"after {after:02d}" if after is not None else "not in the story flow"
        self.shell.changelog.append(f"Chapter {padded}", f"Added chapter {padded} from {source_id} ({where})")
        if plan.warnings:
            messagebox.showwarning("Chapter added", "\n".join(plan.warnings), parent=self)
        page = self.shell.existing_page("chapter")
        if page is not None:
            page.refresh_chapter_lists()
        self.shell.navigate(("chapter", padded))


    def _new_campaign(self) -> None:
        from ... import campaign
        from ..campaign_dialog import NewCampaignDialog
        from ...formats import fe8data

        session = self.shell.session
        ids = chapters.list_chapter_ids(self.project)
        if not ids or not session.available:
            messagebox.showerror("New campaign", "This project has no chapters or no FE8Data.bin.", parent=self)
            return
        records = fe8data.read_chapter_data(session.data)
        titles = chapters.chapter_titles(self.project)
        templates = {chapters.chapter_display_title(c, titles) + f"  ({c})": c
                     for c in ids if any(r.chapter_id == int(c) for r in records)}
        flow, why = open_flow(self.project)
        if flow is None:
            messagebox.showerror("New campaign", f"The story flow can't be edited ({why}), so the chapters "
                                 "could not be put in order.", parent=self)
            return
        order = flow.order()
        after_choices = {_flow_label(c, titles): c for c in order}
        names = {pid: info.name for pid, info in getattr(self.shell.index, "by_pid", {}).items() if info.name}
        characters = {(f"{names[c.pid]}  ({c.pid})" if c.pid in names else c.pid): c.pid
                      for c in fe8data.read_fe8data(session.data).characters if c.pid}
        dialog = NewCampaignDialog(self, templates, after_choices, characters, order[-1] if order else None)
        self.wait_window(dialog)
        if dialog.result is None:
            return
        chapter_specs, cast, after = dialog.result
        problems = campaign.check_campaign(self.project, session.data, chapter_specs, cast, after)
        if problems:
            messagebox.showerror("New campaign", "\n".join(problems), parent=self)
            return
        if session.dirty and not messagebox.askyesno(
                "Save FE8Data.bin?", "Creating the campaign saves FE8Data.bin, including its unsaved edits. Continue?",
                parent=self):
            return
        try:
            result = campaign.add_campaign(self.project, session.data, chapter_specs, cast, after, flow)
        except (ValueError, OSError, ModdingError) as exc:
            messagebox.showerror("New campaign", str(exc), parent=self)
            return
        session.data = result.fe8data
        session.changed(self)
        try:
            session.save()
        except OSError as exc:
            messagebox.showerror("Could not save FE8Data.bin", str(exc), parent=self)
        summary = f"{len(result.chapter_ids)} chapters ({', '.join(f'{c:02d}' for c in result.chapter_ids)}), " \
                  f"{len(result.pids)} characters"
        self.shell.changelog.append("Campaign", f"Added {summary}")
        if result.warnings:
            messagebox.showwarning("Campaign added", "\n".join(result.warnings), parent=self)
        page = self.shell.existing_page("chapter")
        if page is not None:
            page.refresh_chapter_lists()
        if result.chapter_ids:
            self.shell.navigate(("chapter", f"{result.chapter_ids[0]:02d}"))

    def _story_order(self) -> None:
        from ... import campaign
        from ..campaign_dialog import StoryOrderDialog

        flow, why = open_flow(self.project)
        if flow is None:
            messagebox.showerror("Story order", f"The story flow can't be edited ({why}).", parent=self)
            return
        titles = chapters.chapter_titles(self.project)
        order = flow.order()
        labels = {c: _flow_label(c, titles) for c in order}
        dialog = StoryOrderDialog(self, order, labels)
        self.wait_window(dialog)
        if dialog.result is None:
            return
        try:
            campaign.set_story_order(flow, dialog.result)
        except (ValueError, OSError, ModdingError) as exc:
            messagebox.showerror("Story order", str(exc), parent=self)
            return
        self.shell.changelog.append("Story order", "Reordered the story: " + " → ".join(f"{c:02d}" for c in dialog.result))
        self._build()


class ChapterPage(Page):
    """Route ``("chapter", id[, tab[, ...]])``; deep links:
    ``dialogue, message_id`` · ``build, folder, difficulty, section, unit`` ·
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
        ttk.Button(right, text="▶ Play in Dolphin…", command=self._play_in_dolphin).pack(side="right", padx=(0, 18))

        self._notebook = ttk.Notebook(self)
        self._notebook.pack(fill="both", expand=True, padx=16, pady=(0, 8))
        self._overview = ScrollFrame(self._notebook, padding=(16, 12))
        self._notebook.add(self._overview, text="Overview")
        project, log = self.project, shell.changelog
        # The map's and the deployment's data; the Build tab shows and edits both
        # (neither editor has a tab of its own).
        self._map = MapEditor(self._notebook, project, log)
        self._deployment = DeploymentEditor(self._notebook, project, log,
                                            on_navigate_to_character=lambda pid: shell.navigate(("character", pid)))
        self._dialogue = DialogueEditor(self._notebook, project, log)
        self._script = ScriptEditor(self._notebook, project, log)
        self._shops = ShopEditor(self._notebook, project, log, index_provider=lambda: shell.index,
                                 session_provider=lambda: shell.session)
        # The Build tab edits the Map, Deployment and Script editors' data; it has none of its own,
        # so it isn't one of panels() (their dirty state covers it). It shows the deployment
        # file's sections and units, and picks which of the phase's files (dispos_n/h/m/c) to show.
        self._build = MapBuilder(self._notebook, project, log, self._map, self._deployment,
                                 index_provider=lambda: shell.index, session_provider=lambda: shell.session,
                                 on_navigate_to_character=lambda pid: shell.navigate(("character", pid)),
                                 navigate=shell.navigate, script_editor=self._script,
                                 on_open_function=lambda name: shell.navigate(("chapter", self._chapter, "script", name)))
        # FE8Data.bin's battle-scene rows: edits go to the shared session (saved with every other
        # FE8Data.bin edit), so it isn't one of panels() either.
        self._battle = BattleScenePanel(self._notebook, project, log, session_provider=lambda: shell.session,
                                        map_editor=self._map)
        # The phase map's settings (through the Build tab) and the chapter's FE8Data.bin record.
        self._settings = ChapterSettingsPanel(self._notebook, self._build,
                                              session_provider=lambda: shell.session, navigate=shell.navigate)
        for key, panel in (("build", self._build), ("settings", self._settings), ("dialogue", self._dialogue),
                           ("script", self._script), ("shops", self._shops), ("battle", self._battle)):
            self._notebook.add(panel, text=TAB_LABELS[key])
        self._notebook.bind("<<NotebookTabChanged>>", lambda e: self._on_tab_changed())
        self._tab = "overview"

    # -- Page ----------------------------------------------------------------------------
    def panels(self):
        return [self._map, self._deployment, self._dialogue, self._script, self._shops]

    def flush(self) -> None:
        self._battle.flush()
        self._settings.flush()

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
        self._battle.select_map(folder)
        if self._chapter is not None:
            self._render_overview()

    def _update_header(self) -> None:
        cid = self._chapter
        self._title.configure(text=self._title_of(cid))

        position = self._ids.index(cid) if cid in self._ids else -1
        self._prev.configure(state="normal" if position > 0 else "disabled")
        self._next.configure(state="normal" if 0 <= position < len(self._ids) - 1 else "disabled")

    def play_in_dolphin(self) -> bool:
        """Open the Play in Dolphin dialog for the open chapter (False: none is open)."""
        if self._chapter is None:
            return False
        self._play_in_dolphin()
        return True

    def _play_in_dolphin(self) -> None:
        if self._chapter is None:
            return
        dialog = PlayChapterDialog(self, self._title_of(self._chapter))
        self.wait_window(dialog)
        if dialog.result is not None:
            self.shell.play_chapter(int(self._chapter), dialog.result)

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
        self._battle.flush()
        self._settings.flush()
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
        elif tab == "build" and len(args) >= 4:
            folder, difficulty, section, unit = args[:4]
            if folder != self._phase:
                self._set_phase(folder)
            self._build.select_unit(difficulty, section, int(unit))

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
        self._render_flow(body)
        self._render_cast(body, index)
        self._render_dialogue(body, index)
        self._render_script(body, index)

    def _render_flow(self, body) -> None:
        """Where the chapter sits in the story: what leads to it and what comes next."""
        chapter = int(self._chapter)
        head = section_header(body, "Story flow", "")
        head.pack(fill="x", pady=(0, 8))
        flow, why = open_flow(self.project)
        if flow is None:
            ttk.Label(body, text=f"The story flow can't be edited: {why}", style="Muted.TLabel").pack(anchor="w")
            ttk.Frame(body, style="Page.TFrame", height=20).pack()
            return
        if not chapter_flow.can_have_successor(chapter):
            ttk.Label(body, text="Trial maps are played from the trial menu, not in the story.",
                      style="Muted.TLabel").pack(anchor="w")
            ttk.Frame(body, style="Page.TFrame", height=20).pack()
            return
        titles = chapters.chapter_titles(self.project)
        in_story = chapter in flow.order()
        box = ttk.Frame(body, style="Surface.TFrame", padding=(14, 10))
        box.pack(fill="x", pady=(0, 20))
        before = flow.predecessors(chapter)
        line = ttk.Frame(box, style="Surface.TFrame")
        line.pack(fill="x", pady=(0, 6))
        ttk.Label(line, text="Played after:", style="SurfaceHeading.TLabel").pack(side="left")
        if before:
            for c in before:
                Link(line, _flow_label(c, titles), lambda c=c: self.shell.navigate(("chapter", f"{c:02d}")),
                     bg_token="surface").pack(side="left", padx=(8, 0))
        else:
            ttk.Label(line, text="no chapter leads here: the game never reaches it" if chapter > 1 else
                      "the start of a new game", style="SurfaceMuted.TLabel").pack(side="left", padx=(8, 0))

        line = ttk.Frame(box, style="Surface.TFrame")
        line.pack(fill="x")
        ttk.Label(line, text="Next chapter:", style="SurfaceHeading.TLabel").pack(side="left")
        choices = [c for c in range(1, chapter_flow.FIRST_TRIAL)
                   if c == chapter_flow.GAME_CLEARED or f"{c:02d}" in self._ids]
        labels = {_flow_label(c, titles): c for c in choices}
        current = flow.next_of(chapter)
        var = tk.StringVar(value=_flow_label(current, titles))
        combo = ttk.Combobox(line, textvariable=var, values=list(labels), state="readonly", width=40)
        combo.pack(side="left", padx=(8, 0))
        combo.bind("<<ComboboxSelected>>", lambda e: self._set_next(chapter, labels[var.get()]))
        if chapter > chapter_flow.LAST_RETAIL_STORY and in_story:
            ttk.Button(line, text="Take out of the story", command=lambda: self._remove_from_flow(chapter)).pack(
                side="right")
        notes = []
        if chapter == chapter_flow.CONTINUED_PART or chapter - 1 == chapter_flow.CONTINUED_PART:
            notes.append("Chapters 28 and 29 are the two halves of Ch.27: the game skips the save menu and the "
                         "army cleanup between them, whatever the flow says.")
        if chapter > chapter_flow.LAST_RETAIL_STORY and not in_story:
            notes.append("Not reached from the Prologue: pick it as the next chapter of a story chapter.")
        for note in notes:
            ttk.Label(box, text=note, style="SurfaceMuted.TLabel", wraplength=820, justify="left").pack(
                anchor="w", pady=(6, 0))

    def _set_next(self, chapter: int, nxt: int) -> None:
        flow, why = open_flow(self.project)
        try:
            if flow is None:
                raise ValueError(why)
            if nxt == flow.next_of(chapter):
                return
            description = flow.set_next(chapter, nxt)
        except (ValueError, OSError, ModdingError) as exc:
            messagebox.showerror("Could not change the story flow", str(exc), parent=self)
        else:
            self.shell.changelog.append("main.dol", f"Story flow: {description}")
        self._render_overview()

    def _remove_from_flow(self, chapter: int) -> None:
        flow, why = open_flow(self.project)
        try:
            if flow is None:
                raise ValueError(why)
            description = flow.remove(chapter)
        except (ValueError, OSError, ModdingError) as exc:
            messagebox.showerror("Could not change the story flow", str(exc), parent=self)
        else:
            self.shell.changelog.append("main.dol", f"Story flow: {description}")
        self._render_overview()

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
            Link(row, "Edit in Build ›", lambda u=first: self.shell.navigate(
                ("chapter", self._chapter, "build", u.folder, u.difficulty, u.section, u.unit_index))
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


def open_script(shell, path, function: str | None = None, chapter_id: str | None = None) -> None:
    """Show ``path`` in a chapter's Script tab: ``chapter_id``'s, else the open
    chapter's, else the first chapter with a script (a shared script such as
    ``startup.cmb`` has no chapter of its own; the tab's File box lists it).
    A game without chapter pages yet (Radiant Dawn) shows it in Assets › Scripts."""
    if not profile_of(shell.project).supports(CHAPTERS):
        if shell.navigate(("asset", "scripts", Path(path).name)) and function:
            editor = shell.page("asset")._panels["scripts"].editor
            editor.after_idle(lambda: editor.select_function(function))
        return
    page = shell.existing_page("chapter")
    chapter_id = chapter_id or getattr(page, "_chapter", None)
    if chapter_id is None:
        ids = [c for c in chapters.list_chapter_ids(shell.project) if script_sources.chapter_script(shell.project, c)]
        if not ids:
            return
        chapter_id = ids[0]
    if not shell.navigate(("chapter", chapter_id, "script")):
        return
    editor = shell.page("chapter")._script
    if editor.open_file(path) and function:
        editor.after_idle(lambda: editor.select_function(function))


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
    """Pick a template chapter, a free number, a title, and the chapter the new
    one is played after. ``result`` is ``(template id, number, title, after)``,
    ``after`` None for a chapter left out of the story."""

    NOT_IN_STORY = "Not in the story (reach it later)"

    def __init__(self, parent: tk.Misc, templates: list[str], free_ids: list[int], titles: dict,
                 flow: chapter_flow.ChapterFlow | None, flow_problem: str = ""):
        super().__init__(parent)
        self.title("Add Chapter")
        self.resizable(False, False)
        self.result: tuple[str, int, str, int | None] | None = None
        frame = ttk.Frame(self, padding=16)
        frame.pack(fill="both", expand=True)
        ttk.Label(
            frame,
            text="Creates a new chapter from a copy of another: its dialogue, script, maps and\n"
                 "deployments (renamed to the new number), its chapter record, battle scenes\n"
                 "and base shops. Edit them afterwards on the new chapter's page.",
            justify="left",
        ).grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 12))

        self._templates = {chapters.chapter_display_title(c, titles) + f"  ({c})": c for c in templates}
        ttk.Label(frame, text="Copy of:").grid(row=1, column=0, sticky="w", pady=4)
        self._source_var = tk.StringVar(value=next(iter(self._templates)))
        ttk.Combobox(frame, textvariable=self._source_var, values=list(self._templates), state="readonly",
                     width=44).grid(row=1, column=1, sticky="w", padx=(6, 0))

        ttk.Label(frame, text="Chapter number:").grid(row=2, column=0, sticky="w", pady=4)
        self._id_var = tk.StringVar(value=f"{free_ids[0]:02d}")
        ttk.Combobox(frame, textvariable=self._id_var, values=[f"{n:02d}" for n in free_ids], state="readonly",
                     width=8).grid(row=2, column=1, sticky="w", padx=(6, 0))

        ttk.Label(frame, text="Title:").grid(row=3, column=0, sticky="w", pady=4)
        self._title_var = tk.StringVar(value=f"Chapter {free_ids[0]}")
        ttk.Entry(frame, textvariable=self._title_var, width=46).grid(row=3, column=1, sticky="w", padx=(6, 0))
        self._id_var.trace_add("write", lambda *_: self._title_var.set(f"Chapter {int(self._id_var.get())}")
                               if self._title_var.get().startswith("Chapter ") else None)

        ttk.Label(frame, text="Played after:").grid(row=4, column=0, sticky="w", pady=4)
        self._after = {self.NOT_IN_STORY: None}
        if flow is not None:
            for c in flow.order():
                self._after[_flow_label(c, titles)] = c
        self._after_var = tk.StringVar(value=list(self._after)[-1] if flow is not None else self.NOT_IN_STORY)
        after_box = ttk.Combobox(frame, textvariable=self._after_var, values=list(self._after), state="readonly",
                                 width=44)
        after_box.grid(row=4, column=1, sticky="w", padx=(6, 0))
        self._hint = ttk.Label(frame, text="", style="Muted.TLabel", wraplength=460, justify="left")
        self._hint.grid(row=5, column=0, columnspan=2, sticky="w", pady=(4, 0))
        self._flow, self._titles = flow, titles
        if flow is None:
            after_box.configure(state="disabled")
            self._hint.configure(text=f"The story flow can't be edited ({flow_problem}); the chapter is created "
                                      "but not reached.")
        self._after_var.trace_add("write", lambda *_: self._update_hint())
        self._update_hint()

        buttons = ttk.Frame(frame)
        buttons.grid(row=6, column=0, columnspan=2, sticky="e", pady=(12, 0))
        ttk.Button(buttons, text="Cancel", command=self.destroy).pack(side="right")
        ttk.Button(buttons, text="Add Chapter", style="Accent.TButton", command=self._on_apply).pack(
            side="right", padx=(0, 6))
        self.transient(parent.winfo_toplevel())
        self.grab_set()

    def _update_hint(self) -> None:
        if self._flow is None:
            return
        after = self._after.get(self._after_var.get())
        if after is None:
            text = "The chapter is created but the game won't reach it until a chapter leads to it."
        else:
            nxt = self._flow.next_of(after)
            text = f"{after:02d} will lead to the new chapter, and the new chapter to {_flow_label(nxt, self._titles)}."
            if after == chapter_flow.CONTINUED_PART:
                text += " Chapter 28 is the first half of Ch.27: the game treats whatever follows it as the second half."
        self._hint.configure(text=text)

    def _on_apply(self) -> None:
        title = self._title_var.get().strip()
        if not title.isascii():
            messagebox.showerror("Invalid title", "Use plain ASCII text for the title.", parent=self)
            return
        self.result = (self._templates[self._source_var.get()], int(self._id_var.get()), title,
                       self._after.get(self._after_var.get()))
        self.destroy()


class PlayChapterDialog(tk.Toplevel):
    """Pick the difficulty a chapter is started on in Dolphin. ``result`` is a
    ``current_difficulty_id`` value (``chapter_jump.DIFFICULTIES``). Given
    ``choices`` (chapter ID -> title) instead of one title, it also picks the
    chapter: ``chapter`` holds the chosen ID."""

    SETTING = "play_chapter_difficulty"
    CHAPTER_SETTING = "play_chapter_last"

    def __init__(self, parent: tk.Misc, chapter_title: str | None = None, *,
                 choices: dict[str, str] | None = None):
        super().__init__(parent)
        self.title("Play in Dolphin")
        self.resizable(False, False)
        self.result: int | None = None
        self.chapter: str | None = None
        self._choices = {f"{title}  ({cid})": cid for cid, title in (choices or {}).items()}
        frame = ttk.Frame(self, padding=16)
        frame.pack(fill="both", expand=True)
        if self._choices:
            pick = ttk.Frame(frame)
            pick.grid(row=0, column=0, columnspan=2, sticky="w")
            ttk.Label(pick, text="Chapter:").pack(side="left")
            last = load_setting(self.CHAPTER_SETTING)
            labels = list(self._choices)
            self._chapter_var = tk.StringVar(
                value=next((k for k, v in self._choices.items() if v == last), labels[0]))
            ttk.Combobox(pick, textvariable=self._chapter_var, values=labels, state="readonly",
                         width=40).pack(side="left", padx=(8, 0))
        else:
            ttk.Label(frame, text=chapter_title or "", style="Heading.TLabel").grid(
                row=0, column=0, columnspan=2, sticky="w")
        ttk.Label(
            frame,
            text="Starts Dolphin on the project's extracted files (no build) and goes straight to this\n"
                 "chapter, past the title screen and the file menu, with a fresh army: only the units\n"
                 "the chapter itself brings in. Saved edits are played; unsaved ones are not.",
            justify="left", style="Muted.TLabel",
        ).grid(row=1, column=0, columnspan=2, sticky="w", pady=(4, 12))
        row = ttk.Frame(frame)
        row.grid(row=2, column=0, columnspan=2, sticky="w")
        ttk.Label(row, text="Difficulty:").pack(side="left")
        saved = load_setting(self.SETTING)
        self._var = tk.StringVar(value=saved if saved in chapter_jump.DIFFICULTIES else "Normal")
        ttk.Combobox(row, textvariable=self._var, values=list(chapter_jump.DIFFICULTIES), state="readonly",
                     width=12).pack(side="left", padx=(8, 0))
        buttons = ttk.Frame(frame)
        buttons.grid(row=3, column=0, columnspan=2, sticky="e", pady=(16, 0))
        ttk.Button(buttons, text="Cancel", command=self.destroy).pack(side="right")
        ttk.Button(buttons, text="Play", style="Accent.TButton", command=self._on_play).pack(side="right", padx=(0, 6))
        self.bind("<Return>", lambda e: self._on_play())
        self.bind("<Escape>", lambda e: self.destroy())
        self.transient(parent.winfo_toplevel())
        self.grab_set()

    def _on_play(self) -> None:
        name = self._var.get()
        save_setting(self.SETTING, name)
        if self._choices:
            self.chapter = self._choices[self._chapter_var.get()]
            save_setting(self.CHAPTER_SETTING, self.chapter)
        self.result = chapter_jump.DIFFICULTIES[name]
        self.destroy()
