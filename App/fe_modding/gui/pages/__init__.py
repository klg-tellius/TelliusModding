"""The workspace pages, by route kind (see ``shell.py``)."""

from __future__ import annotations

from .assets import ASSET_TOOLS, AssetPage, AssetsHub
from .chapters import ChapterPage, ChaptersHub
from .code import CodePage
from .characters import CharacterPage, CharactersHub
from .data import GameDataPage
from .disc import DiscPage
from .home import HomePage
from .saves import SaveEditorPage

PAGE_FACTORIES = {
    page.kind: page
    for page in (HomePage, ChaptersHub, ChapterPage, CharactersHub, CharacterPage, GameDataPage,
                 SaveEditorPage,
                 AssetsHub, AssetPage, CodePage, DiscPage)
}

__all__ = ["ASSET_TOOLS", "PAGE_FACTORIES"]
