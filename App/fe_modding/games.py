"""Definitions of the games supported by Tellius Modding.

Path of Radiance and Radiant Dawn share the same underlying engine, but ship on
different platforms with different disc/file formats, which is why each game
gets its own entry here even though project handling is otherwise generic.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Optional


#: Disc formats only Dolphin reads; they go through DolphinTool before WIT.
DOLPHIN_ONLY_FORMATS = (".rvz",)


class Game(Enum):
    PATH_OF_RADIANCE = "path_of_radiance"
    RADIANT_DAWN = "radiant_dawn"


@dataclass(frozen=True)
class GameInfo:
    id: Game
    display_name: str
    short_code: str
    platform: str
    disc_formats: tuple[str, ...]
    """Disc image extensions the app can extract for this game.

    ``.rvz`` is a Dolphin-only format WIT (last released 2022) cannot open;
    :func:`tools.extract_disc` converts it to a temporary ISO with
    DolphinTool first (see :data:`DOLPHIN_ONLY_FORMATS`).
    """
    build_extension: str
    folder_name: str


GAME_INFO: dict[Game, GameInfo] = {
    Game.PATH_OF_RADIANCE: GameInfo(
        id=Game.PATH_OF_RADIANCE,
        display_name="Fire Emblem: Path of Radiance",
        short_code="PoR",
        platform="Nintendo GameCube",
        disc_formats=(".iso", ".gcm", ".ciso", ".wdf", ".wia", ".rvz"),
        build_extension=".ciso",
        folder_name="FE9",
    ),
    Game.RADIANT_DAWN: GameInfo(
        id=Game.RADIANT_DAWN,
        display_name="Fire Emblem: Radiant Dawn",
        short_code="RD",
        platform="Nintendo Wii",
        disc_formats=(".iso", ".wbfs", ".ciso", ".wdf", ".wia", ".rvz"),
        build_extension=".wbfs",
        folder_name="FE10",
    ),
}


def get_game_info(game: Game) -> GameInfo:
    return GAME_INFO[game]


def all_games() -> list[GameInfo]:
    return list(GAME_INFO.values())


def profile(game: Game):
    """The :class:`~fe_modding.game_profile.GameProfile` of ``game`` (file map, chapter scheme, features)."""
    from .game_profile import get_profile
    return get_profile(game)


def read_disc_id(extracted_dir: Path | str) -> str:
    """The six-character disc ID (``GFEE01``, ``RFEE01``...) from ``sys/boot.bin`` of an extracted
    disc, or ``""`` when it is missing or too short."""
    boot = Path(extracted_dir) / "sys" / "boot.bin"
    try:
        with boot.open("rb") as f:
            header = f.read(6)
    except OSError:
        return ""
    return header.decode("ascii", "replace") if len(header) == 6 else ""


def detect_from_extracted(extracted_dir: Path | str) -> Optional[Game]:
    """Which supported game an extracted disc tree is, from the ID in ``sys/boot.bin``
    (``GFE*`` Path of Radiance, ``RFE*`` Radiant Dawn); None when it is neither."""
    from .game_profile import game_for_disc_id
    return game_for_disc_id(read_disc_id(extracted_dir))


#: Where the 6-character disc ID sits in each plain image format (None when it cannot be read cheaply).
_IMAGE_ID_OFFSET = {".iso": 0, ".gcm": 0, ".wbfs": 0x200, ".ciso": 0x8000}


def read_image_disc_id(image: Path | str) -> str:
    """The disc ID (``RFEE01``...) of a disc image file, read from its header without extracting;
    ``""`` for formats that need a tool to open (.rvz, .wdf, .wia) or an unreadable file."""
    image = Path(image)
    offset = _IMAGE_ID_OFFSET.get(image.suffix.lower())
    if offset is None:
        return ""
    try:
        with image.open("rb") as f:
            if image.suffix.lower() == ".wbfs":
                # the disc header follows the first HD sector, whose size is 1 << byte 8 ("WBFS" magic first)
                head = f.read(9)
                if len(head) == 9 and head[:4] == b"WBFS" and 9 <= head[8] <= 16:
                    offset = 1 << head[8]
            f.seek(offset)
            raw = f.read(6)
    except OSError:
        return ""
    if len(raw) != 6 or not all(0x20 <= b < 0x7F for b in raw):
        return ""
    return raw.decode("ascii")
