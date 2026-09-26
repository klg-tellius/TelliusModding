"""Definitions of the games supported by Tellius Modding.

Path of Radiance and Radiant Dawn share the same underlying engine, but ship on
different platforms with different disc/file formats, which is why each game
gets its own entry here even though project handling is otherwise generic.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


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
    """Disc image extensions the bundled WIT tool can read for this game.

    Notably excludes .rvz: that's a Dolphin-only format WIT (last released
    2022) predates and cannot open. Use a .ciso/.wbfs/.iso dump instead.
    """
    build_extension: str
    folder_name: str


GAME_INFO: dict[Game, GameInfo] = {
    Game.PATH_OF_RADIANCE: GameInfo(
        id=Game.PATH_OF_RADIANCE,
        display_name="Fire Emblem: Path of Radiance",
        short_code="PoR",
        platform="Nintendo GameCube",
        disc_formats=(".iso", ".gcm", ".ciso", ".wdf", ".wia"),
        build_extension=".ciso",
        folder_name="FE9",
    ),
    Game.RADIANT_DAWN: GameInfo(
        id=Game.RADIANT_DAWN,
        display_name="Fire Emblem: Radiant Dawn",
        short_code="RD",
        platform="Nintendo Wii",
        disc_formats=(".iso", ".wbfs", ".ciso", ".wdf", ".wia"),
        build_extension=".wbfs",
        folder_name="FE10",
    ),
}


def get_game_info(game: Game) -> GameInfo:
    return GAME_INFO[game]


def all_games() -> list[GameInfo]:
    return list(GAME_INFO.values())
