"""Game Data: classes, items, skills, terrain types, chapters, the general
tables and supports (``FE8Data.bin``),
and the props of every chapter map (Map Objects, read from the ``map.cmp`` files).

Characters live in the same file but have their own pages; both edit one
shared session (``fe8_session.py``). Each tab lists its records as tiles
(the item and skill tiles show their icon; classes have no icon, and are filtered
as unpromoted, promoted or laguz like items by weapon type); a tile opens
the record's form, and fields apply as soon as they are left. The Flags tab
holds the 96 script flags (campaign, chapter, save file). The Supports tab
lists every support pair (a character's partners and bonds are edited on their
page), edits the affinity bonus table and the support conversations
(``Mess/yell.m``, through a Dialogue editor)."""

from __future__ import annotations

from .flags import FlagsPanel
from ..cp_data_editor import CpDataPanel
from ..dialogue_editor import DialogueEditor
from ..prop_browser import MapObjectsPanel
from ..shell import Page
from ..stats_editor import TAB_KEYS, StatsEditor
from ..support_editor import SupportEditorPanel

TABS = {"classes": "Classes", "items": "Items", "skills": "Skills", "terrain": "Terrain", "chapters": "Chapters",
        "general": "General", "supports": "Supports", "props": "Map Objects", "flags": "Flags", "ai": "AI (CP)"}


class GameDataPage(Page):
    kind = "data"

    def __init__(self, shell):
        super().__init__(shell)
        self._editor = StatsEditor(self, self.project, shell.changelog, shell.session, navigate=shell.navigate)
        self._editor.pack(fill="both", expand=True)
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
        self._props = MapObjectsPanel(self._editor._notebook, self.project)
        self._editor._notebook.add(self._props, text=TABS["props"])
        self._flags = FlagsPanel(self._editor._notebook, shell)
        self._editor._notebook.add(self._flags, text=TABS["flags"])
        self._ai = CpDataPanel(self._editor._notebook, self.project, shell.changelog,
                               session_provider=lambda: shell.session if shell.session.available else None)
        self._editor._notebook.add(self._ai, text=TABS["ai"])

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

    def cleanup(self) -> None:
        super().cleanup()
        self._props.browser.cleanup()

    def flush(self) -> None:
        self._editor.flush()
        if self._supports is not None:
            self._supports.flush()

    def _on_tab(self) -> None:
        self.flush()
        current = self._editor._notebook.select()
        self._tab = next((key for key, widget in self._tab_widgets().items() if str(widget) == current), self._tab)
        if self.shell.route and self.shell.route[0] == self.kind and self.shell.route[1:2] != (self._tab,):
            self.shell.replace_route((self.kind, self._tab))

    def _tab_widgets(self) -> dict:
        tabs = self._editor._notebook.tabs()
        widgets = {key: tabs[i] for i, key in enumerate(TAB_KEYS) if i < len(tabs)}
        if self._supports is not None:
            widgets["supports"] = self._supports
        widgets["props"] = self._props
        widgets["flags"] = self._flags
        widgets["ai"] = self._ai
        return widgets

    def show(self, route) -> bool:
        tab = route[1] if len(route) > 1 and route[1] in TABS else self._tab
        self._tab = tab
        if tab in ("supports", "props", "flags", "ai"):
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
        tab = route[1] if len(route) > 1 and route[1] in TABS else self._tab
        return [("Game Data", ("data",)), (TABS[tab], None)]

    def history_label(self, route):
        tab = route[1] if len(route) > 1 and route[1] in TABS else self._tab
        return f"Game Data › {TABS[tab]}"
