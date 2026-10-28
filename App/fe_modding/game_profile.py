"""Per-game profile: where a game keeps each kind of data, and what the app can do with it.

Path of Radiance (FE9) and Radiant Dawn (FE10) share the engine and the data containers but not the
file names, the compression, the chapter numbering or the record layouts. Instead of ``if game ==``
checks scattered over the app, code asks the project's :class:`GameProfile`:

* **logical files**: ``game_data`` is ``FE8Data.bin`` on Path of Radiance and the LZ10-compressed
  ``FE10Data.cms`` on Radiant Dawn. :meth:`GameProfile.path` gives the path under ``extracted/files``
  and :meth:`ModProject.read_logical` / ``write_logical`` handle the compression;
* **chapter files**: the script, dialogue, map folder and deployment of a chapter id
  (``01`` on Path of Radiance, ``0101`` and ``0407a`` on Radiant Dawn);
* **features**: which areas have a decoder for this game. An area without one is reported by
  :meth:`GameProfile.unavailable` ("... is not available for Radiant Dawn yet") instead of failing on
  a file layout the code does not understand. A feature is switched on here once its codec exists.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Mapping, Optional

from .formats.fe9_font import FONT_FILES, FONT_FILES_FE10
from .games import Game
from .game_files import as_path


@dataclass(frozen=True)
class LogicalFile:
    """One kind of game file: its path under ``extracted/files`` and whether it is LZ10-wrapped on disc."""
    path: str
    compressed: bool = False
    label: str = ""

    @property
    def name(self) -> str:
        """The file name alone (what the user sees in buttons and messages)."""
        return self.path.rsplit("/", 1)[-1]


# Features the app implements per game. A key missing from GameProfile.features is "not available yet".
GAME_DATA = "game_data"        # characters, classes, items, skills, terrain, chapters, supports
DATA_TABLES = "data_tables"    # the character/class/item/skill tables alone (Radiant Dawn's FE10Data)
CHAPTERS = "chapters"          # per-chapter file set, hub, maps, deployments
DIALOGUE = "dialogue"          # Mess/*.m editing and the conversation preview
SCRIPTS = "scripts"            # chapter event scripts
SHOPS = "shops"
AI = "ai"                      # cp_data
BATTLE_TABLES = "battle_tables"  # zdbx and the battle viewers
BATTLE_DATA = "battle_data"      # native battle-data catalogue / structural browser
BATTLE_CAMERAS = "battle_cameras"  # native battle-camera catalogue and preview
ANIM = "anim"                  # map-model registry
MODELS = "models"              # 3D model viewer / slots / rigs
FONTS = "fonts"
ICONS = "icons"
EFFECTS = "effects"
AUDIO = "audio"
VIDEO = "video"
SAVES = "saves"
GAME_CODE = "game_code"        # main.dol patches and tunables
PLAY = "play"                  # Play in Dolphin / chapter jump
PLAYTHROUGH = "playthrough"    # In-app tactical chapter runner
BATTLE_SIM = "battle_sim"      # Forecast, simulation and rendered fight workflow
PATCHES = "patches"            # .tpatch create / apply
DISC = "disc"                  # extract / rebuild
COLOUR_VARIANTS = "colour_variants"  # recoloured battle/map texture + portrait copies
MAP_DECODED = "map_decoded"    # map.bin sections (capacity, grids, props) decoded for the Build canvas
EXTENDED_FLAGS = "extended_flags"  # main.dol runtime for flags past the vanilla slots
TUTORIALS = "tutorials"        # tutorial pages
STAFF_CREDITS = "staff_credits"  # staff roll
ENDING_ART = "ending_art"      # ending/ illustrations
BATTLE_SKIES = "battle_skies"  # sky/ battle backdrops
# Purpose-built screens a game gets once its data reaches them through the adapters (game_adapter.py);
# until then the page shows that game's generic record view for the same feature.
CHARACTER_FORM = "character_form"  # the Character › Stats form with Open buttons
CHAPTER_RECORD_FORM = "chapter_record_form"  # Chapter › Chapter data: objectives, music, backgrounds
SUPPORT_LIST = "support_list"  # per-partner support list with conversation links
DATA_WORKSPACE = "data_workspace"  # Game Data as one tabbed workspace (supports, flags, AI, rect RIDs as tabs)
SAVE_UNITS = "save_units"      # save editor with Units, Convoy, Forges, Map objects, Flags, System tabs
CHAPTER_FLOW = "chapter_flow"  # editable story flow (game_code.story_flow) and Add chapter
NEW_CAMPAIGN = "new_campaign"  # Chapters › New campaign (several chapters and characters at once)
HUB = "hub"                    # Chapters › Create hub (a hub chapter with links to chapters)
#: Several map folders per chapter (bmap06, bmap06_2: Opening18_N / Complete18 parts). Not on Radiant
#: Dawn: its multi-map chapters are separate ChapterData records (0407a-e) and it has no part natives.
MAP_PHASES = "map_phases"

FEATURE_LABELS = {
    GAME_DATA: "Game data editing", DATA_TABLES: "The character, class, item and skill tables", CHAPTERS: "Chapter editing", DIALOGUE: "Dialogue editing",
    SCRIPTS: "Script editing", SHOPS: "Shop editing", AI: "AI editing", BATTLE_TABLES: "Battle editors",
    BATTLE_DATA: "Battle data", BATTLE_CAMERAS: "Battle cameras",
    ANIM: "The map model registry", MODELS: "3D models", FONTS: "Fonts", ICONS: "Icons",
    EFFECTS: "Effects", AUDIO: "Audio editing", VIDEO: "Video editing", SAVES: "Save files",
    GAME_CODE: "Game Code patches", PLAY: "Play in Dolphin", PLAYTHROUGH: "In-app playthrough",
    BATTLE_SIM: "Battle Simulator and rendered fights", PATCHES: "Patches", DISC: "Disc extraction",
    COLOUR_VARIANTS: "Colour variants", MAP_DECODED: "Map editing", EXTENDED_FLAGS: "Extended flags",
    TUTORIALS: "Tutorials", STAFF_CREDITS: "Staff credits", ENDING_ART: "Ending art", BATTLE_SKIES: "Battle skies",
    CHARACTER_FORM: "The character form", CHAPTER_RECORD_FORM: "The chapter data form",
    SUPPORT_LIST: "The support partner list", DATA_WORKSPACE: "The Game Data workspace",
    SAVE_UNITS: "Save unit, convoy and forge editing",
    CHAPTER_FLOW: "Story flow editing", NEW_CAMPAIGN: "Campaign creation", HUB: "Hub chapters",
    MAP_PHASES: "Map phases",
}


@dataclass(frozen=True)
class GameProfile:
    game: Game
    display_name: str
    disc_id_prefix: str          # first three characters of the disc ID: "GFE" / "RFE"
    wii: bool
    files: Mapping[str, LogicalFile]
    chapter_id_width: int        # digits of a chapter id: "05" -> 2, "0105" -> 4
    chapter_script: str          # template under files/; {id} is the chapter id
    chapter_mess: str
    chapter_id_pattern: str      # regex of a chapter id in a Mess/c<id>.m file name
    map_dir: str                 # folder holding map.cmp (and the deployment)
    deployment: str              # deployment file of a map folder; {folder}, {diff}
    shop_dir: str
    shop_file: str               # {diff}
    shop_difficulties: tuple[str, ...]
    deployment_difficulties: tuple[str, ...]
    features: frozenset[str] = field(default_factory=frozenset)
    #: Message text language: "fe9" ($ commands, formats/fe9_message_scene.py) or
    #: "fe10" (the byte-code of formats/fe10_message.py).
    message_dialect: str = "fe9"
    #: Event-script bytecode and catalogues (``formats/cmb``): "fe9" or "fe10" (a
    #: :class:`~fe_modding.formats.cmb.model.Dialect` name).
    script_dialect: str = "fe9"
    #: Buckets of the engine's name hash (``message.engine_name_hash``): message IDs and container
    #: symbols that share a bucket and check value shadow each other.
    name_hash_buckets: int = 509
    #: (font name, path under files/) of every game font, in the game's font order.
    font_files: tuple[tuple[str, str], ...] = ()
    #: Parts of Disc & Patch › Export as text implemented for this game (``text_export.PART_LABELS`` keys).
    text_export_parts: tuple[str, ...] = ()

    # -- files ------------------------------------------------------------------------------
    def logical(self, name: str) -> LogicalFile:
        try:
            return self.files[name]
        except KeyError:
            raise KeyError(f"{self.display_name} has no logical file {name!r}.") from None

    def has_file(self, name: str) -> bool:
        return name in self.files

    def path(self, files_root: Path | str, name: str) -> Path:
        """Where logical file ``name`` lives, given the ``extracted/files`` folder."""
        return as_path(files_root) / self.logical(name).path

    def path_or_none(self, files_root: Path | str, name: str) -> Optional[Path]:
        """:meth:`path`, or None when this game has no such logical file."""
        return as_path(files_root) / self.files[name].path if name in self.files else None

    def file_label(self, name: str) -> str:
        """Short file name for UI text (``FE8Data.bin`` / ``FE10Data.cms``); falls back to ``name``."""
        entry = self.files.get(name)
        return entry.name if entry else name

    # -- chapters ---------------------------------------------------------------------------
    def chapter_key(self, chapter_id: str) -> str:
        """Normalise a chapter id for file names (zero-padded on Path of Radiance)."""
        return chapter_id.zfill(self.chapter_id_width) if chapter_id.isdigit() else chapter_id

    def script_path(self, files_root: Path | str, chapter_id: str) -> Path:
        key = self.chapter_key(chapter_id)
        return as_path(files_root) / self.chapter_script.format(id=key)

    def mess_path(self, files_root: Path | str, chapter_id: str) -> Path:
        key = self.chapter_key(chapter_id)
        return as_path(files_root) / self.chapter_mess.format(id=key)

    def chapter_sort_key(self, chapter_id: str) -> tuple:
        """Story order of chapter ids: by number, then suffix (``0407a`` after ``0406``); ``final`` last."""
        digits = "".join(ch for ch in chapter_id if ch.isdigit())
        return (int(digits) if digits else 10 ** 9, chapter_id.lower())

    def map_folder(self, chapter_id: str) -> str:
        """``bmap05`` for chapter 5 (the primary map; later phases add ``_2``...)."""
        return self.map_dir.format(id=self.chapter_key(chapter_id))

    def deployment_path(self, files_root: Path | str, folder: str, difficulty: str = "") -> Path:
        return as_path(files_root) / "zmap" / folder / self.deployment.format(diff=difficulty)

    def shop_folder(self, files_root: Path | str) -> Path:
        return as_path(files_root) / self.shop_dir

    def shop_path(self, files_root: Path | str, difficulty: str) -> Path:
        return self.shop_folder(files_root) / self.shop_file.format(diff=difficulty)

    # -- features ---------------------------------------------------------------------------
    def supports(self, feature: str) -> bool:
        return feature in self.features

    def unavailable(self, feature: str) -> str:
        """Message for a screen that cannot work on this game yet."""
        what = FEATURE_LABELS.get(feature, feature)
        return f"{what} is not available for {self.display_name} yet."


_PATH_OF_RADIANCE_FILES = {
    "game_data": LogicalFile("FE8Data.bin"),
    "system_archive": LogicalFile("system.cmp", compressed=True),
    "anim_data": LogicalFile("FE8Anim.bin"),
    "battle_data": LogicalFile("zdbx.cmp", compressed=True),
    "ai_data": LogicalFile("cp_data.bin"),
    "common_mess": LogicalFile("Mess/common.m"),
    "startup_script": LogicalFile("Scripts/startup.cmb"),
}

_RADIANT_DAWN_FILES = {
    "game_data": LogicalFile("FE10Data.cms", compressed=True),
    "growth_data": LogicalFile("FE10Growth.cms", compressed=True),
    "anim_data": LogicalFile("FE10Anim.cms", compressed=True),
    "battle_data": LogicalFile("FE10Battle.cms", compressed=True),
    "effect_data": LogicalFile("FE10Effect.cms", compressed=True),
    "conversation_data": LogicalFile("FE10Conversation.cms", compressed=True),
    "ai_data": LogicalFile("Cp/cp_data.cms", compressed=True),
    "common_mess": LogicalFile("Mess/common.m"),
    "startup_script": LogicalFile("Scripts/startup.cmb"),
    "sound_data": LogicalFile("Sound/sound_data_en.cms", compressed=True),
    "sound_archive": LogicalFile("Sound/sound_us.brsar"),
    "soundroom": LogicalFile("soundroom.bin"),
}

PATH_OF_RADIANCE_PROFILE = GameProfile(
    game=Game.PATH_OF_RADIANCE,
    display_name="Path of Radiance",
    disc_id_prefix="GFE",
    wii=False,
    files=_PATH_OF_RADIANCE_FILES,
    chapter_id_width=2,
    chapter_script="Scripts/C{id}.cmb",
    chapter_mess="Mess/c{id}.m",
    chapter_id_pattern=r"\d+",
    map_dir="bmap{id}",
    deployment="dispos.cmp",
    shop_dir="shop",
    shop_file="shopitem_{diff}.bin",
    shop_difficulties=("n", "h", "m"),
    deployment_difficulties=("c", "n", "h", "m"),
    features=frozenset({GAME_DATA, CHAPTERS, DIALOGUE, SCRIPTS, SHOPS, AI, BATTLE_TABLES, BATTLE_DATA, BATTLE_CAMERAS, ANIM, MODELS, FONTS,
                        ICONS, EFFECTS, AUDIO, VIDEO, SAVES, GAME_CODE, PLAY, PLAYTHROUGH, BATTLE_SIM, PATCHES, DISC,
                        COLOUR_VARIANTS, MAP_DECODED, EXTENDED_FLAGS, TUTORIALS, STAFF_CREDITS, ENDING_ART,
                        CHARACTER_FORM, CHAPTER_RECORD_FORM, SUPPORT_LIST, DATA_WORKSPACE, SAVE_UNITS,
                        CHAPTER_FLOW, NEW_CAMPAIGN, HUB, MAP_PHASES}),
    font_files=FONT_FILES,
    text_export_parts=("FE8Data", "deployments", "shops", "messages", "scripts", "sound", "faces", "zdbx"),
)

# Radiant Dawn: only what is decoded. Each phase of the parity plan switches features on.
RADIANT_DAWN_PROFILE = GameProfile(
    game=Game.RADIANT_DAWN,
    display_name="Radiant Dawn",
    disc_id_prefix="RFE",
    wii=True,
    files=_RADIANT_DAWN_FILES,
    chapter_id_width=4,
    chapter_script="Scripts/C{id}.cmb",
    chapter_mess="Mess/c{id}.m",
    chapter_id_pattern=r"\d{4}[a-z]?|final",
    map_dir="bmap{id}",
    deployment="dispos_{diff}.bin",
    shop_dir="Shop",
    shop_file="shopitem_{diff}.bin",
    shop_difficulties=("n", "h", "m"),
    deployment_difficulties=("c", "n", "h"),
    features=frozenset({DATA_TABLES, CHAPTERS, DIALOGUE, SCRIPTS, SHOPS, AI, BATTLE_DATA, BATTLE_CAMERAS, MODELS, FONTS, ICONS, EFFECTS,
                        AUDIO, VIDEO, SAVES, GAME_CODE, PLAY, BATTLE_SIM, PATCHES, DISC, BATTLE_SKIES,
                        MAP_DECODED, CHAPTER_FLOW, CHAPTER_RECORD_FORM}),
    # playthrough waits for the RFEE01 script runtime: chapter and startup scripts still call natives
    # it does not model (playthrough/natives.py stops on those rather than guessing).
    message_dialect="fe10",
    script_dialect="fe10",
    name_hash_buckets=2027,
    font_files=FONT_FILES_FE10,
    text_export_parts=("FE10Data", "FE10Growth", "messages", "scripts"),
)

PROFILES: dict[Game, GameProfile] = {
    Game.PATH_OF_RADIANCE: PATH_OF_RADIANCE_PROFILE,
    Game.RADIANT_DAWN: RADIANT_DAWN_PROFILE,
}


def get_profile(game: Game) -> GameProfile:
    return PROFILES[game]


def game_for_disc_id(disc_id: str) -> Optional[Game]:
    """The game a disc ID such as ``GFEE01`` or ``RFEP01`` belongs to (None for any other game)."""
    for profile in PROFILES.values():
        if disc_id.upper().startswith(profile.disc_id_prefix):
            return profile.game
    return None


def profile_of(project) -> GameProfile:
    """The profile of a project. Tolerates the light stand-ins some tests and tools pass around:
    an object without a ``profile`` or ``game`` is treated as Path of Radiance."""
    profile = getattr(project, "profile", None)
    if profile is not None:
        return profile
    game = getattr(project, "game", None)
    return PROFILES.get(game, PATH_OF_RADIANCE_PROFILE)


def files_root_of(project):
    """The disc's ``files/`` tree of a project as a ``GamePath`` (see :func:`profile_of` for
    stand-ins, which are read as the older layout)."""
    from .game_files import files_of
    return files_of(project).at("files")


def disc_root_of(project):
    """The project's whole disc tree (``sys/`` and ``files/``) as a ``GamePath``."""
    from .game_files import files_of
    return files_of(project).at("")


def sys_root_of(project):
    """The disc's ``sys/`` folder of a project as a ``GamePath``."""
    from .game_files import files_of
    return files_of(project).at("sys")


def logical_game_path_of(project, name: str):
    """Logical file ``name`` of the project as a ``GamePath``."""
    from .game_files import files_of
    return files_of(project).at(logical_rel_of(project, name))


def logical_rel_of(project, name: str) -> str:
    """Disc-relative path of logical file ``name`` (``files/FE8Data.bin``), for ``project.files``."""
    return f"files/{profile_of(project).logical(name).path}"

