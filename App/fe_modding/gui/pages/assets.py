"""Assets: a tile per resource type, each opening its viewer full-page.

The viewers keep their own file lists - that list belongs to the tool, not to
the workspace navigation."""

from __future__ import annotations

from tkinter import ttk

from ..background_viewer import BackgroundViewer
from ..editor_panel import EditorPanel
from ..graphics_viewers import (
    EndingViewer,
    EquipmentViewer,
    EtcGraphicsViewer,
    IllustrationViewer,
    WindowGraphicsViewer,
    WorldMapViewer,
)
from ..font_viewer import FontViewer
from ..icon_viewer import IconViewer
from ..model_viewer import ModelViewer
from ..music_editor import MusicEditor
from ..portrait_viewer import PortraitViewer
from ..shell import Page
from ..video_viewer import VideoViewer
from ..widgets import Card, CardGrid, ScrollFrame, section_header

#: (key, label, icon, description, class), in hub order.
ASSET_TOOLS = [
    ("portraits", "Portraits", "☺", "Character faces (Face/): view and replace", PortraitViewer),
    ("models", "3D Models", "◈", "Map and battle models, weapons, rigs, animations, map terrain", ModelViewer),
    ("backgrounds", "Backgrounds", "▭", "Conversation backgrounds (s/)", BackgroundViewer),
    ("illustrations", "Illustrations", "✎", "Textures in illust/", IllustrationViewer),
    ("ending", "Ending Art", "✦", "Textures in ending/", EndingViewer),
    ("world_map", "World Map", "◎", "Textures in gmap/", WorldMapViewer),
    ("icons", "Icons", "◆", "Item, menu and skill icons: view and replace one by one", IconViewer),
    ("fonts", "Fonts", "A", "The five text fonts: view, import a TrueType/OpenType font", FontViewer),
    ("ui_windows", "UI Windows", "▤", "Window textures (window/)", WindowGraphicsViewer),
    ("etc_graphics", "Misc Graphics", "▧", "Textures in etc/", EtcGraphicsViewer),
    ("equipment", "Equipment", "⚔", "Loose .tpl textures in zu/", EquipmentViewer),
    ("music", "Music", "♫", "Music streams (Sound/): preview, replace, add", MusicEditor),
    ("videos", "Videos", "▶", "THP videos (Movie/): preview, replace, add", VideoViewer),
]
TOOLS_BY_KEY = {t[0]: t for t in ASSET_TOOLS}


class AssetsHub(Page):
    kind = "assets"

    def __init__(self, shell):
        super().__init__(shell)
        scroll = ScrollFrame(self, padding=(28, 12, 28, 28))
        scroll.pack(fill="both", expand=True)
        ttk.Label(scroll.body, text="Assets", style="Title.TLabel").pack(anchor="w")
        ttk.Label(scroll.body, text="Game files shared by every chapter. Replacing one changes it everywhere it's used.",
                  style="Muted.TLabel").pack(anchor="w", pady=(2, 16))
        for title, keys in (("Characters and models", ("portraits", "models")),
                            ("Art", ("backgrounds", "illustrations", "ending", "world_map")),
                            ("Interface", ("icons", "fonts", "ui_windows", "etc_graphics", "equipment")),
                            ("Sound and video", ("music", "videos"))):
            section_header(scroll.body, title).pack(anchor="w", pady=(12, 8))
            grid = CardGrid(scroll.body, card_width=280)
            grid.pack(fill="x")
            for key in keys:
                _k, label, icon, description, _cls = TOOLS_BY_KEY[key]
                grid.add(key, Card(grid, title=label, subtitle=description, icon=icon, width=280,
                                   on_click=lambda k=key: shell.navigate(("asset", k))))
            grid.done()

    def crumbs(self, route):
        return [("Assets", None)]


class AssetPage(Page):
    """One asset tool full-page; route ``("asset", key[, selection])``."""

    kind = "asset"

    def __init__(self, shell):
        super().__init__(shell)
        self._panels: dict[str, EditorPanel] = {}
        self._key = None

    def panels(self):
        return list(self._panels.values())

    def show(self, route) -> bool:
        key = route[1] if len(route) > 1 else None
        if key not in TOOLS_BY_KEY:
            return False
        panel = self._panels.get(key)
        if panel is None:
            cls = TOOLS_BY_KEY[key][4]
            panel = cls(self, self.project, self.shell.changelog)
            self._panels[key] = panel
        if key != self._key:
            for other in self._panels.values():
                other.pack_forget()
            panel.pack(fill="both", expand=True)
            self._key = key
        if len(route) > 2 and route[2]:
            if key == "portraits":
                panel.select_character(route[2])
            elif key == "models":
                panel.select_set(route[2])
            elif key == "icons":
                panel.select_icon(route[2])
        return True

    def crumbs(self, route):
        return [("Assets", ("assets",)), (TOOLS_BY_KEY[route[1]][1], None)]

    def history_label(self, route):
        return TOOLS_BY_KEY[route[1]][1]
