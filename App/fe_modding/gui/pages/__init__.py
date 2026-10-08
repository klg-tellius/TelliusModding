"""The workspace pages, by route kind (see ``shell.py``)."""

from __future__ import annotations

from .assets import ASSET_TOOLS, AssetPage, AssetsHub
from .chapters import ChapterPage, ChaptersHub
from .check import CheckPage
from .code import CodePage
from .characters import CharacterPage, CharactersHub
from .data import game_data_page
from .disc import DiscPage
from .home import HomePage
from .saves import SaveEditorPage
from .tools import ToolsHub

PAGE_FACTORIES = {
    page.kind: page
    for page in (HomePage, ChaptersHub, ChapterPage, CharactersHub, CharacterPage, game_data_page,
                 SaveEditorPage, ToolsHub,
                 AssetsHub, AssetPage, CodePage, CheckPage, DiscPage)
}

__all__ = ["ASSET_TOOLS", "PAGE_FACTORIES"]
