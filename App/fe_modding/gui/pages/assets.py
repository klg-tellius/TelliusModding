"""Assets: a tile per resource type, each opening its viewer full-page.

The viewers keep their own file lists - that list belongs to the tool, not to
the workspace navigation. Conversations and Scripts list their files as cards
that open the chapter page's Dialogue and Script tabs (``text_assets.py``)."""

from __future__ import annotations

from tkinter import ttk

from ..background_viewer import BackgroundViewer
from ..battle_camera_viewer import BattleCameraViewer
from ..battle_params_viewer import BattleParamsViewer
from ..battle_scenery_viewer import BattleSceneryViewer
from ..battle_simulator import BattleSimulator
from ..battle_weapons_viewer import BattleWeaponsViewer
from ..editor_panel import EditorPanel
from ..effects_viewer import EffectsViewer
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
from ..prop_browser import MapObjectsPanel
from ..music_editor import MusicEditor
from ..portrait_viewer import PortraitViewer
from ..sfx_viewer import SfxViewer
from ..soundroom_editor import SoundRoomEditor
from ..shell import TOOL_ASSETS, Page
from ..video_viewer import VideoViewer
from ..widgets import Card, CardGrid, ScrollFrame, section_header
from .text_assets import ConversationsPanel, ScriptsPanel

#: (key, label, icon, description, class), in hub order.
ASSET_TOOLS = [
    ("conversations", "Conversations", "✉", "Every message file (Mess/), chapters' and shared", ConversationsPanel),
    ("scripts", "Scripts", "⌘", "Every event script (Scripts/), chapters' and startup.cmb", ScriptsPanel),
    ("portraits", "Portraits", "☺", "Character faces (Face/): view and replace", PortraitViewer),
    ("models", "3D Models", "◈", "Map and battle models, weapons, rigs, animations, map terrain", ModelViewer),
    ("map_objects", "Map Objects", "▲", "Every prop of every chapter map (map.cmp): browse and export", MapObjectsPanel),
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
    ("effects", "Visual Effects", "✺", "Spell and battle effects (FE8Effect.bin, yme/): preview, replace, add", EffectsViewer),
    ("battle_weapons", "Battle Weapons", "⚔", "Weapon actors in battle (zdbx.cmp xwp/): type, flight, effects", BattleWeaponsViewer),
    ("battle_sceneries", "Battle Sceneries", "▨", "Battle backdrops: indoor flag, footstep effect and sound (zbg/)", BattleSceneryViewer),
    ("battle_cameras", "Battle Cameras", "◉", "Battle camera rigs and per-action camera scripts (camera.dbx, xcam/)", BattleCameraViewer),
    ("battle_sim", "Battle Simulator", "⚔", "Two units, their weapons and skills: forecast and a random or fixed fight", BattleSimulator),
    ("battle_params", "Battle Unit Parameters", "⚙", "Battle model speed, range, jump attacks, flying, size (zu/*_prm.dbx)", BattleParamsViewer),
    ("sfx", "Sound Effects", "♪", "Sound effect cues (gcfesnd.bin): names and parameters", SfxViewer),
    ("sound_room", "Soundroom Images", "▦", "Soundroom slideshow pictures (soundroom.bin): order, position, add", SoundRoomEditor),
    ("videos", "Videos", "▶", "THP videos (Movie/): preview, replace, add", VideoViewer),
]
TOOLS_BY_KEY = {t[0]: t for t in ASSET_TOOLS}
#: Tools that list files for other pages to open (they take the shell).
LIST_PANELS = (ConversationsPanel, ScriptsPanel)


class AssetsHub(Page):
    kind = "assets"

    def __init__(self, shell):
        super().__init__(shell)
        scroll = ScrollFrame(self, padding=(28, 12, 28, 28))
        scroll.pack(fill="both", expand=True)
        ttk.Label(scroll.body, text="Assets", style="Title.TLabel").pack(anchor="w")
        ttk.Label(scroll.body, text="Game files shared by every chapter. Replacing one changes it everywhere it's used.",
                  style="Muted.TLabel").pack(anchor="w", pady=(2, 16))
        for title, keys in (("Text, scripts and fonts", ("conversations", "scripts", "fonts")),
                            ("Characters and models", ("portraits", "models", "map_objects")),
                            ("Battle", ("battle_weapons", "battle_sceneries", "battle_cameras", "battle_params", "effects")),
                            ("Images", ("backgrounds", "illustrations", "ending", "world_map", "sound_room",
                                        "icons", "ui_windows", "etc_graphics", "equipment")),
                            ("Sound and video", ("music", "sfx", "videos"))):
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
    """One asset tool full-page; route ``("asset", key[, selection])``
    (for Conversations, the selection is a message file it hosts)."""

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
            if cls in LIST_PANELS:
                panel = cls(self, self.shell)
            elif getattr(cls, "uses_fe8_session", False):
                panel = cls(self, self.project, self.shell.changelog, self.shell.session)
            else:
                panel = cls(self, self.project, self.shell.changelog)
            self._panels[key] = panel
        selection = route[2] if len(route) > 2 else None
        if key == "conversations" and selection and not panel.open_file(selection):
            return False
        if isinstance(panel, LIST_PANELS) and not selection:
            panel.show_list()
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
            elif key == "battle_sim":
                panel.select_character(route[2])
        return True

    def crumbs(self, route):
        label = TOOLS_BY_KEY[route[1]][1]
        if route[1] in TOOL_ASSETS:
            return [("Tools", ("tools",)), (label, None)]
        if route[1] == "conversations" and len(route) > 2 and route[2]:
            return [("Assets", ("assets",)), (label, ("asset", route[1])), (route[2], None)]
        return [("Assets", ("assets",)), (label, None)]

    def index_changed(self) -> None:
        # the list cards show chapter titles and message counts from the index
        panel = self._panels.get(self._key)
        if isinstance(panel, LIST_PANELS) and panel.showing_list:
            panel.show_list()

    def history_label(self, route):
        return TOOLS_BY_KEY[route[1]][1]
