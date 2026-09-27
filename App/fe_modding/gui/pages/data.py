"""Game Data: classes, items, skills, terrain types, chapters, battle scenes,
the general tables and supports (``FE8Data.bin``),
and the props of every chapter map (Map Objects, read from the ``map.cmp`` files).

Characters live in the same file but have their own pages; both edit one
shared session (``fe8_session.py``). Each tab lists its records as tiles
(the class tiles show a character of the class, the item and skill tiles
their icon, the support tiles the character's portrait); a tile opens the
record's form, and fields apply as soon as they are left. The Supports tab also edits the support conversations
(``Mess/yell.m``) through a Dialogue editor."""

from __future__ import annotations

from ...project_index import GENERIC, NAMED, PLAYABLE
from ..dialogue_editor import DialogueEditor
from ..prop_browser import MapObjectsPanel
from ..shell import Page
from ..stats_editor import TAB_KEYS, StatsEditor
from ..support_editor import SupportEditorPanel

TABS = {"classes": "Classes", "items": "Items", "skills": "Skills", "terrain": "Terrain", "chapters": "Chapters",
        "battle": "Battle scenes", "general": "General", "supports": "Supports", "props": "Map Objects"}


class GameDataPage(Page):
    kind = "data"

    def __init__(self, shell):
        super().__init__(shell)
        self._class_faces: dict[str, str] = {}
        self._class_faces_for = None
        self._editor = StatsEditor(self, self.project, shell.changelog, shell.session, navigate=shell.navigate,
                                   class_portrait=self._class_portrait)
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
                request_portrait=shell.portraits.request,
            )
            self._editor._notebook.add(self._supports, text=TABS["supports"])
            session.subscribe(self._on_session_changed)
        self._props = MapObjectsPanel(self._editor._notebook, self.project)
        self._editor._notebook.add(self._props, text=TABS["props"])

    def _character_name(self, pid: str) -> str:
        index = self.shell.index
        info = index.by_pid.get(pid) if index is not None and index.ready else None
        return info.name if info is not None and info.name else pid

    def _class_portrait(self, jid: str, size: int, callback) -> None:
        """A face for a class tile: the first playable character of the
        class, else a named one, else a generic one (by promoted class last)."""
        index = self.shell.index
        if index is None or not index.ready:
            return
        if self._class_faces_for is not index:
            rank = {PLAYABLE: 0, NAMED: 1, GENERIC: 2}
            best: dict[str, tuple] = {}
            for c in index.characters:
                if not c.fid:
                    continue
                for promoted, class_jid in enumerate((c.jid, c.promoted_jid)):
                    key = (promoted, rank.get(c.category, 3), c.index)
                    if class_jid and (class_jid not in best or key < best[class_jid][0]):
                        best[class_jid] = (key, c.fid)
            self._class_faces = {class_jid: fid for class_jid, (_, fid) in best.items()}
            self._class_faces_for = index
        fid = self._class_faces.get(jid)
        if fid:
            self.shell.portraits.request(fid, size, callback)

    def index_changed(self) -> None:
        self._editor.refresh_class_images()

    def _on_session_changed(self, source) -> None:
        if self._supports is not None and source is not self._supports:
            self._supports.reload()

    def panels(self):
        panels = [self._editor]
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
        return widgets

    def show(self, route) -> bool:
        tab = route[1] if len(route) > 1 and route[1] in TABS else self._tab
        self._tab = tab
        if tab in ("supports", "props"):
            widget = self._tab_widgets().get(tab)
            if widget is not None:
                self._editor._notebook.select(widget)
        else:
            self._editor.select_tab(tab)
        if len(route) > 2 and route[2]:
            if tab == "classes":
                self._editor.select_class(route[2])
            elif tab == "items":
                self._editor.select_item(route[2])
            elif tab == "skills":
                self._editor.select_skill(route[2])
        return True

    def crumbs(self, route):
        tab = route[1] if len(route) > 1 and route[1] in TABS else self._tab
        return [("Game Data", ("data",)), (TABS[tab], None)]

    def history_label(self, route):
        tab = route[1] if len(route) > 1 and route[1] in TABS else self._tab
        return f"Game Data › {TABS[tab]}"
