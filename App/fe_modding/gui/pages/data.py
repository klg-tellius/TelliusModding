"""Game Data: classes, items, skills, terrain types, chapters, the general
tables and supports (``FE8Data.bin``), the script flags and the AI scripts.

The hub (route ``("data",)``) shows a tile per section, like Assets; a tile
opens that section full-page (``("data", key[, record])``). The sections are
the pages of one notebook whose tab strip is hidden, so the hub is the only way
between them. Characters live in the same file but have their own pages; both edit one
shared session (``fe8_session.py``). Each tab lists its records as tiles
(the item and skill tiles show their icon; classes have no icon, and are filtered
as unpromoted, promoted or laguz like items by weapon type); a tile opens
the record's form, and fields apply as soon as they are left. The Flags tab
holds the 96 script flags (campaign, chapter, save file). The Supports tab
lists every support pair (a character's partners and bonds are edited on their
page), edits the affinity bonus table and the support conversations
(``Mess/yell.m``, through a Dialogue editor)."""

from __future__ import annotations

from tkinter import ttk

from ...game_profile import DATA_TABLES, GAME_DATA, SCRIPTS
from .flags import FlagsPanel
from ..cp_data_editor import CpDataPanel
from ..dialogue_editor import DialogueEditor
from ..fe10_data_editor import TAB_KEYS as FE10_TAB_KEYS, TAB_TITLES as FE10_TAB_TITLES, Fe10DataEditor
from ..shell import Page
from ..stats_editor import TAB_KEYS, StatsEditor
from ..support_editor import SupportEditorPanel
from ..widgets import Card, CardGrid, ScrollFrame, section_header

TABS = {"classes": "Classes", "items": "Items", "skills": "Skills", "terrain": "Terrain", "chapters": "Chapters",
        "general": "General", "supports": "Supports", "flags": "Flags", "ai": "AI (CP)"}
#: key -> (icon, description) of the hub tiles.
TILES = {
    "classes": ("♞", "Stats, weapon ranks, innate skills, movement and build"),
    "items": ("⚔", "Weapons, staves and items: combat, price, effects, bonuses"),
    "skills": ("✦", "Parameters, icon and who can have each skill"),
    "terrain": ("▦", "Movement cost per movement type, bonuses, healing"),
    "chapters": ("⚑", "Chapter records: files, objectives, scenes, enemy levels"),
    "general": ("≡", "Difficulty constants, army groups, battle skies"),
    "supports": ("♥", "Support pairs, affinity bonuses and support conversations"),
    "flags": ("⚐", "The 96 named script flags: campaign, chapter and save file"),
    "ai": ("⌬", "Enemy AI scripts (cp_data.bin): readable script editor"),
}
SECTIONS = (("game_data", ("classes", "items", "skills", "terrain", "chapters", "general", "supports")),
            ("Scripts and AI", ("flags", "ai")))


class GameDataPage(Page):
    kind = "data"

    def __init__(self, shell):
        super().__init__(shell)
        self._hub = None
        self._editor = StatsEditor(self, self.project, shell.changelog, shell.session, navigate=shell.navigate)
        style = ttk.Style(self)
        style.layout("Tabless.TNotebook.Tab", [])  # the hub picks the section, not a tab strip
        style.configure("Tabless.TNotebook", borderwidth=0)
        self._editor._notebook.configure(style="Tabless.TNotebook")
        self._editor._notebook.bind("<<NotebookTabChanged>>", lambda e: self._on_tab(), add="+")
        self._tab = "classes"
        self._supports = None
        session = shell.session
        if session.available:
            self._supports = SupportEditorPanel(
                self._editor._notebook,
                get_data=lambda: session.data,
                set_data=lambda b: setattr(session, "data", b),
                on_dirty=lambda: session.changed(self._supports),
                display_name=self._character_name,
                make_dialogue_editor=lambda parent: DialogueEditor(parent, self.project, shell.changelog),
                yell_path=self.project.extracted_dir / "files" / "Mess" / "yell.m",
                open_character=lambda pid: shell.navigate(("character", pid, "supports")),
            )
            self._editor._notebook.add(self._supports, text=TABS["supports"])
            session.subscribe(self._on_session_changed)
        self._flags = FlagsPanel(self._editor._notebook, shell)
        self._editor._notebook.add(self._flags, text=TABS["flags"])
        self._ai = CpDataPanel(self._editor._notebook, self.project, shell.changelog,
                               session_provider=lambda: shell.session if shell.session.available else None)
        self._editor._notebook.add(self._ai, text=TABS["ai"])

    def _build_hub(self) -> ScrollFrame:
        scroll = ScrollFrame(self, padding=(28, 12, 28, 28))
        ttk.Label(scroll.body, text="Game Data", style="Title.TLabel").pack(anchor="w")
        data_file = self.project.profile.file_label("game_data")
        ttk.Label(scroll.body, text=f"The game's tables, shared by every chapter: {data_file}, the script flags "
                  "and the AI scripts.", style="Muted.TLabel").pack(anchor="w", pady=(2, 16))
        if not self.shell.session.available:
            ttk.Label(scroll.body, text=self.shell.session.unavailable_reason, style="Muted.TLabel").pack(anchor="w")
        available = self._tab_widgets()
        for title, keys in SECTIONS:
            title = data_file if title == "game_data" else title
            keys = [key for key in keys if key in available]
            if not keys:
                continue
            section_header(scroll.body, title).pack(anchor="w", pady=(12, 8))
            grid = CardGrid(scroll.body, card_width=280)
            grid.pack(fill="x")
            for key in keys:
                icon, description = TILES[key]
                grid.add(key, Card(grid, title=TABS[key], subtitle=description, icon=icon, width=280,
                                   on_click=lambda k=key: self.shell.navigate((self.kind, k))))
            grid.done()
        return scroll

    def _show_hub(self, hub: bool) -> None:
        if hub:
            self.flush()
            if self._hub is None:
                self._hub = self._build_hub()
            self._editor.pack_forget()
            self._hub.pack(fill="both", expand=True)
        else:
            if self._hub is not None:
                self._hub.pack_forget()
            self._editor.pack(fill="both", expand=True)

    def _character_name(self, pid: str) -> str:
        index = self.shell.index
        info = index.by_pid.get(pid) if index is not None and index.ready else None
        return info.name if info is not None and info.name else pid

    def open_support_conversation(self, pid: str, partner: str, rank: str) -> None:
        """Show (or create) the pair's support conversation in Supports › Conversations."""
        if self._supports is None:
            return
        self.shell.navigate((self.kind, "supports"))
        self._supports.open_conversation(pid, partner, rank)

    def support_conversation_ids(self):
        return self._supports.conversation_ids() if self._supports is not None else None

    def _on_session_changed(self, source) -> None:
        if self._supports is not None and source is not self._supports:
            self._supports.reload()

    def index_changed(self) -> None:
        self._flags.index_changed()

    def panels(self):
        panels = [self._editor, self._ai]
        if self._supports is not None and self._supports.dialogue_editor is not None:
            panels.append(self._supports.dialogue_editor)  # yell.m has its own Save
        return panels

    def flush(self) -> None:
        self._editor.flush()
        if self._supports is not None:
            self._supports.flush()

    def _on_tab(self) -> None:
        self.flush()
        current = self._editor._notebook.select()
        self._tab = next((key for key, widget in self._tab_widgets().items() if str(widget) == current), self._tab)
        if self.shell.route and self.shell.route[0] == self.kind and len(self.shell.route) > 1                 and self.shell.route[1:2] != (self._tab,):
            self.shell.replace_route((self.kind, self._tab))

    def _tab_widgets(self) -> dict:
        tabs = self._editor._notebook.tabs()
        widgets = {key: tabs[i] for i, key in enumerate(TAB_KEYS) if i < len(tabs)}
        if self._supports is not None:
            widgets["supports"] = self._supports
        widgets["flags"] = self._flags
        widgets["ai"] = self._ai
        return widgets

    def show(self, route) -> bool:
        if len(route) < 2 or route[1] not in self._tab_widgets():
            self._show_hub(True)
            return True
        self._show_hub(False)
        tab = self._tab = route[1]
        if tab in ("supports", "flags", "ai"):
            widget = self._tab_widgets().get(tab)
            if widget is not None:
                self._editor._notebook.select(widget)
        else:
            self._editor.select_tab(tab)
        if tab == "flags":
            self._flags.show_sub(tuple(route[2:]))
        elif len(route) > 2 and route[2]:
            if tab == "classes":
                self._editor.select_class(route[2])
            elif tab == "items":
                self._editor.select_item(route[2])
            elif tab == "skills":
                self._editor.select_skill(route[2])
            elif tab == "chapters" and str(route[2]).isdigit():
                self._editor.select_chapter(int(route[2]))
        return True

    def crumbs(self, route):
        if len(route) < 2 or route[1] not in TABS:
            return [("Game Data", None)]
        return [("Game Data", ("data",)), (TABS[route[1]], None)]

    def history_label(self, route):
        if len(route) < 2 or route[1] not in TABS:
            return None
        return f"Game Data › {TABS[route[1]]}"


FE10_TILES = {
    "characters": ("☺", "Levels, classes, skills, stats over the class, growths, laguz gauges"),
    "classes": ("♞", "Caps, bases, growths, promotion gains, skills, movement, capacity"),
    "items": ("⚔", "Weapons, staves and items: combat, price, attributes, stat bonuses"),
    "skills": ("✦", "Capacity, icon, effects and who can or cannot have each skill"),
    "chapters": ("⚑", "Files, objectives per difficulty, scenes, weather, lord"),
    "terrain": ("▦", "Bonuses, healing, step effects and movement costs per type"),
    "supports": ("♥", "Support speed between every pair of characters"),
    "bonds": ("∞", "Bond pairs and their bonus"),
    "affinities": ("☯", "Attack, defense, hit and avoid per affinity"),
    "affinity_pairs": ("⚭", "Values between two affinities"),
    "triangle": ("△", "Weapon triangle damage and hit"),
    "groups": ("⚐", "Army groups and their names"),
    "difficulty": ("≡", "Constants per difficulty (rows not named yet)"),
    "growth": ("↗", "FE10Growth.cms: absolute stats at every level, per character"),
    "battle_scenery": ("⛰", "Battle background per map and terrain type"),
    "biorhythm": ("∿", "Biorhythm rows (four values each, not named yet)"),
}
FE10_SECTIONS = (("Units and items", ("characters", "classes", "items", "skills", "growth")),
                 ("Chapters and maps", ("chapters", "terrain", "battle_scenery")),
                 ("Relations", ("supports", "bonds", "affinities", "affinity_pairs")),
                 ("Rules", ("triangle", "groups", "difficulty", "biorhythm")))


class Fe10GameDataPage(Page):
    """Game Data for a game whose database has only its record tables decoded (Radiant Dawn): a hub
    of the tables and one :class:`Fe10DataEditor` showing the picked one, plus the script flags
    (``("data", "flags"[, tab])``) once the game's scripts are decoded."""

    kind = "data"

    def __init__(self, shell):
        super().__init__(shell)
        self._editor = Fe10DataEditor(self, self.project, shell.changelog)
        self._flags: FlagsPanel | None = None
        self._hub = self._build_hub()

    def _build_hub(self) -> ScrollFrame:
        scroll = ScrollFrame(self, padding=(28, 12, 28, 28))
        ttk.Label(scroll.body, text="Game Data", style="Title.TLabel").pack(anchor="w")
        data_file = self.project.profile.file_label("game_data")
        ttk.Label(scroll.body, text=f"The game's tables, shared by every chapter: {data_file}. Fields whose "
                  "meaning is not known yet are shown as Unknown and edit as numbers.", style="Muted.TLabel",
                  wraplength=720, justify="left").pack(anchor="w", pady=(2, 16))
        for title, keys in FE10_SECTIONS:
            section_header(scroll.body, title).pack(anchor="w", pady=(12, 8))
            grid = CardGrid(scroll.body, card_width=280)
            grid.pack(fill="x")
            for key in keys:
                icon, description = FE10_TILES[key]
                grid.add(key, Card(grid, title=FE10_TAB_TITLES[key], subtitle=description, icon=icon, width=280,
                                   on_click=lambda k=key: self.shell.navigate((self.kind, k))))
            grid.done()
        if self.project.profile.supports(SCRIPTS):
            section_header(scroll.body, "Scripts").pack(anchor="w", pady=(12, 8))
            grid = CardGrid(scroll.body, card_width=280)
            grid.pack(fill="x")
            grid.add("flags", Card(grid, title=TABS["flags"], icon="⚐", width=280,
                                   subtitle="The 128 named script flags: campaign and chapter",
                                   on_click=lambda: self.shell.navigate((self.kind, "flags"))))
            grid.done()
        return scroll

    def show(self, route) -> bool:
        if len(route) > 1 and route[1] == "flags" and self.project.profile.supports(SCRIPTS):
            if self._flags is None:
                self._flags = FlagsPanel(self, self.shell)
            self._hub.pack_forget()
            self._editor.pack_forget()
            self._flags.pack(fill="both", expand=True)
            self._flags.show_sub(tuple(route[2:]))
            return True
        if self._flags is not None:
            self._flags.pack_forget()
        if len(route) < 2 or route[1] not in FE10_TAB_KEYS:
            self._editor.pack_forget()
            self._hub.pack(fill="both", expand=True)
            return True
        self._hub.pack_forget()
        self._editor.pack(fill="both", expand=True)
        self._editor.select_tab(route[1])
        if len(route) > 2 and route[2]:
            self._editor.select_record(str(route[2]))
        return True

    def panels(self):
        return [self._editor]

    def flush(self) -> None:
        self.focus_set()  # a field applies when it loses focus

    def index_changed(self) -> None:
        if self._flags is not None:
            self._flags.index_changed()

    def _title(self, route):
        if len(route) > 1 and route[1] == "flags":
            return TABS["flags"]
        return FE10_TAB_TITLES.get(route[1]) if len(route) > 1 else None

    def crumbs(self, route):
        title = self._title(route)
        if title is None:
            return [("Game Data", None)]
        return [("Game Data", ("data",)), (title, None)]

    def history_label(self, route):
        title = self._title(route)
        return f"Game Data › {title}" if title else None


def game_data_page(shell) -> Page:
    """The Game Data page for the project's game: the full one where the whole database is decoded,
    the tables-only one where just the record tables are (Radiant Dawn)."""
    profile = shell.project.profile
    if not profile.supports(GAME_DATA) and profile.supports(DATA_TABLES):
        return Fe10GameDataPage(shell)
    return GameDataPage(shell)


game_data_page.kind = "data"
