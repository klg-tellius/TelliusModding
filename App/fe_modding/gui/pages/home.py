"""Home: the project dashboard - the ways in (chapters, characters, game
data, flags, assets, and Disc & Patch for extracting, building and
patches), where you were last and this session's changes."""

from __future__ import annotations

from tkinter import ttk

from ..shell import Page
from ..widgets import Card, CardGrid, ScrollFrame, section_header


class HomePage(Page):
    kind = "home"

    def __init__(self, shell):
        super().__init__(shell)
        self._scroll = ScrollFrame(self, padding=(28, 12, 28, 28))
        self._scroll.pack(fill="both", expand=True)

    def crumbs(self, route):
        return [("Home", None)]

    def show(self, route) -> bool:
        self._render()
        return True

    def index_changed(self) -> None:
        if self.winfo_ismapped():
            self._render()

    def _render(self) -> None:
        body = self._scroll.body
        for child in body.winfo_children():
            child.destroy()
        project, shell = self.project, self.shell

        ttk.Label(body, text=project.name, style="Title.TLabel").pack(anchor="w")
        ttk.Label(body, text=f"{project.game_info.display_name}  ·  {project.game_info.platform}  ·  {project.directory}",
                  style="Muted.TLabel").pack(anchor="w", pady=(2, 18))

        index = shell.index
        if not shell.extracted:
            ttk.Label(body, text="Choose and extract the source disc in Disc & Patch to browse and edit its "
                      "chapters, characters and assets.", style="Muted.TLabel").pack(anchor="w")
        section_header(body, "Browse").pack(anchor="w", pady=(28 if not shell.extracted else 10, 10))
        browse = CardGrid(body, card_width=250)
        browse.pack(fill="x")
        chapters = f"{len(index.chapters)} chapters" if index else "Indexing…"
        playable = len(index.main_characters("playable")) if index and index.characters else 0
        characters = f"{playable} playable, {len(index.main_characters()) if index else 0} in all" if index else "Indexing…"
        tiles = (
            ("chapters", "▦", "Chapters", chapters, "Maps, deployment, dialogue and scripts, per chapter"),
            ("characters", "☺", "Characters", characters, "Stats, portrait, models and every appearance"),
            ("data", "≡", "Game Data", "Classes · Items · Skills · Terrain", "Everything else in FE8Data.bin"),
            ("flags", "⚑", "Flags", "Campaign · Chapter · Save file", "On/off switches scripts remember things with"),
            ("saves", "◫", "Saves", "Units · Convoy · Forges · Flags", "Open a .gci save and edit its blocks"),
            ("assets", "▣", "Assets", "Portraits, art, music, videos, 3D models", "Browse and replace game files"),
            ("disc", "◎", "Disc & Patch", project.source_iso if shell.extracted else "Not extracted yet",
             "Extract the source disc, build a playable image, make a patch to share"),
        )
        for key, icon, title, subtitle, caption in tiles:
            if not shell.extracted and key != "disc":
                continue
            browse.add(key, Card(browse, title=title, subtitle=subtitle, caption=caption, icon=icon, width=250,
                                 on_click=lambda k=key: shell.navigate((k,))))
        browse.done()
        if not shell.extracted:
            return

        if shell.visited:
            section_header(body, "Jump back in").pack(anchor="w", pady=(28, 10))
            recent = CardGrid(body, card_width=250)
            recent.pack(fill="x")
            for i, (route, label) in enumerate(shell.visited[:8]):
                kind = {"chapter": "Chapter", "character": "Character", "asset": "Tool", "data": "Game Data"}.get(
                    route[0], route[0].title())
                recent.add(i, Card(recent, title=label, subtitle=kind, width=250,
                                   on_click=lambda r=route: shell.navigate(r)))
            recent.done()

        entries = shell.changelog.recent_first()
        section_header(body, "Changes this session", f"{len(entries)} so far").pack(anchor="w", pady=(28, 8))
        if not entries:
            ttk.Label(body, text="Nothing saved yet. Every save and import will be listed here.",
                      style="Muted.TLabel").pack(anchor="w")
        for entry in entries[:10]:
            row = ttk.Frame(body, style="Page.TFrame")
            row.pack(fill="x", pady=1)
            ttk.Label(row, text=entry.timestamp, style="Faint.TLabel", width=10).pack(side="left")
            ttk.Label(row, text=entry.scope, style="Strong.TLabel").pack(side="left", padx=(0, 8))
            ttk.Label(row, text=entry.description, style="Muted.TLabel").pack(side="left")
        if len(entries) > 10:
            ttk.Button(body, text="Show all changes", command=shell.toggle_activity).pack(anchor="w", pady=(8, 0))
