"""Per-game access to the shared game-data tables, so one widget serves both games.

Path of Radiance keeps its tables in ``FE8Data.bin`` (typed entries, :mod:`formats.fe8data`) and
Radiant Dawn in ``FE10Data.cms`` (generic records, :mod:`formats.fe10data`). A page that edits a
table asks the session's :class:`DataAdapter` for the rows, the record ids, the Excel sheet and the
write call, instead of testing which game it runs on. A capability the adapter lacks for a game is
reported as such (``None``, an empty list or a :class:`ValueError` with the reason), so the page can
hide or refuse the control the same way on both games.

:func:`data_adapter` picks the adapter of a session (``Fe8DataSession`` or ``Fe10DataSession``).
"""

from __future__ import annotations

import struct
from dataclasses import dataclass
from typing import Optional

from . import excel_io
from .formats import fe8data, fe10data
from .formats.fe8data import BattleTerrainRow

#: BattleTerrIndex value of a Radiant Dawn terrain with no battle background.
FE10_NO_SCENERY = 0xFFFF


@dataclass(frozen=True)
class EntityRow:
    """One record of a table: its position and its id label (``PID_IKE``...)."""
    index: int
    id: Optional[str]


class DataAdapter:
    """The game-data operations the pages share. Subclasses implement them per game."""

    #: Whether a new record may start empty (otherwise it must copy an existing one).
    can_start_empty = True
    #: Whether the battle-background names are also the ``zbg/`` folder names (Radiant Dawn's are hashed).
    scene_folders_named = True

    def __init__(self, session) -> None:
        self.session = session

    @property
    def data(self) -> bytes:
        return self.session.data

    # -- records ----------------------------------------------------------------------------
    def records(self, kind: str) -> list[EntityRow]:
        """Every record of ``kind`` (``character``, ``class``, ``item``, ``skill``) in table order."""
        raise NotImplementedError

    def index_of(self, kind: str, record_id: str) -> Optional[int]:
        return next((row.index for row in self.records(kind) if row.id == record_id), None)

    def template_groups(self, kind: str) -> Optional[list[str]]:
        """One group name per record of ``kind``, for the New record dialog's Type filter (or None)."""
        return None

    def add_record(self, kind: str, new_id: Optional[str], copy_from: Optional[int]) -> tuple[bytes, int]:
        """The file with a record appended (a copy of ``copy_from``, or empty) and its index.
        Raises ValueError with the reason when the record cannot be added."""
        raise NotImplementedError

    # -- Excel ------------------------------------------------------------------------------
    def excel_sheet(self, kind: str) -> Optional[str]:
        """The workbook sheet holding ``kind``, or None when this game has no Excel layout for it."""
        return None

    def export_excel(self, path, kind: str) -> None:
        raise ValueError(f"No Excel sheet for {kind} records.")

    def import_excel(self, path, kind: str) -> tuple[bytes, list[str]]:
        """``(new file, errors)`` from the sheet of ``kind`` in workbook ``path``."""
        raise ValueError(f"No Excel sheet for {kind} records.")

    # -- battle scenes and terrain ----------------------------------------------------------
    def terrain_keys(self) -> list[str]:
        """Each terrain type's ``TerrainData`` name, in the engine's index order."""
        raise NotImplementedError

    def battle_scenery_rows(self) -> list[BattleTerrainRow]:
        """The map/terrain → battle background table, background names resolved."""
        raise NotImplementedError

    def write_battle_scenery_rows(self, rows: list[BattleTerrainRow]) -> bytes:
        """The file with ``rows`` written back. Raises ValueError for a change the game's table cannot hold."""
        raise NotImplementedError

    # -- chapters ---------------------------------------------------------------------------
    def chapter_templates(self, project) -> list[str]:
        """Chapter ids Add chapter can copy."""
        raise NotImplementedError

    def free_chapters(self, project) -> list[str]:
        """Chapter ids a new chapter can take, first choice first."""
        raise NotImplementedError

    def default_chapter_title(self, chapter_id: str) -> str:
        return f"Chapter {chapter_id}"

    def add_story_chapter(self, project, source_id: str, new_id: str, title: str, after: Optional[str],
                          flow) -> tuple[bytes, list[str]]:
        """Copy ``source_id`` as chapter ``new_id`` (files written, ``after`` -> new chapter in
        ``flow``, a :class:`~.game_code.story_flow.StoryFlow`). Returns the game-data file for the
        session to save and the warnings."""
        raise NotImplementedError


class PorDataAdapter(DataAdapter):
    """Path of Radiance: ``FE8Data.bin`` through :mod:`formats.fe8data`."""

    _TABLES = {"character": "characters", "class": "classes", "item": "items", "skill": "skills"}
    _IDS = {"character": "pid", "class": "jid", "item": "iid", "skill": "sid"}
    _SHEETS = {"character": "Characters", "item": "Items", "terrain": "Terrain"}

    def records(self, kind: str) -> list[EntityRow]:
        fe8 = self.session.fe8
        if fe8 is None or kind not in self._TABLES:
            return []
        key = self._IDS[kind]
        return [EntityRow(entry.index, getattr(entry, key)) for entry in getattr(fe8, self._TABLES[kind])]

    def template_groups(self, kind: str) -> Optional[list[str]]:
        fe8 = self.session.fe8
        if kind == "item" and fe8 is not None:
            return [fe8data.item_category(item) for item in fe8.items]
        return None

    def add_record(self, kind, new_id, copy_from):
        return fe8data.add_record(self.data, kind, new_id, copy_from)

    def excel_sheet(self, kind: str) -> Optional[str]:
        return self._SHEETS.get(kind)

    def export_excel(self, path, kind: str) -> None:
        excel_io.export_fe8(path, self.data, only=self._sheet(kind))

    def import_excel(self, path, kind: str) -> tuple[bytes, list[str]]:
        data, _docs, errors = excel_io.import_fe8(path, self.data, only=self._sheet(kind))
        return data, errors

    def _sheet(self, kind: str) -> str:
        sheet = self.excel_sheet(kind)
        if sheet is None:
            raise ValueError(f"No Excel sheet for {kind} records.")
        return sheet

    def terrain_keys(self) -> list[str]:
        try:
            return [t.name for t in fe8data.read_terrain_types(self.data)]
        except (KeyError, ValueError, IndexError, struct.error):
            return []

    def battle_scenery_rows(self) -> list[BattleTerrainRow]:
        try:
            return fe8data.read_battle_terrain(self.data)
        except (KeyError, ValueError, struct.error):
            return []

    def write_battle_scenery_rows(self, rows):
        return fe8data.write_battle_terrain(self.data, rows)

    def chapter_templates(self, project) -> list[str]:
        from . import chapters
        numbers = {r.chapter_id for r in fe8data.read_chapter_data(self.data)}
        return [c for c in chapters.list_chapter_ids(project) if c.isdigit() and int(c) in numbers]

    def free_chapters(self, project) -> list[str]:
        from . import chapters
        used = [r.chapter_id for r in fe8data.read_chapter_data(self.data)]
        return [f"{n:02d}" for n in chapters.free_chapter_ids(project, used)]

    def default_chapter_title(self, chapter_id: str) -> str:
        return f"Chapter {int(chapter_id)}"

    def add_story_chapter(self, project, source_id, new_id, title, after, flow):
        from . import chapters
        plan = chapters.add_story_chapter(project, self.data, source_id, int(new_id), title,
                                          int(after) if after is not None else None,
                                          getattr(flow, "flow", None))
        return plan.fe8data, plan.warnings


class RdDataAdapter(DataAdapter):
    """Radiant Dawn: ``FE10Data.cms`` through :mod:`formats.fe10data`."""

    can_start_empty = False
    scene_folders_named = False

    def records(self, kind: str) -> list[EntityRow]:
        fe10 = self.session.fe10
        if fe10 is None:
            return []
        return [EntityRow(record.index, record.id) for record in fe10.tables.get(kind, [])]

    def add_record(self, kind, new_id, copy_from):
        if copy_from is None:
            raise ValueError("A new Radiant Dawn record starts as a copy of an existing one: pick one to copy.")
        if new_id and self.index_of(kind, new_id) is not None:
            raise ValueError(f"{new_id} is already used.")
        return fe10data.add_record(self.data, kind, copy_from, new_id or None)

    def terrain_keys(self) -> list[str]:
        fe10 = self.session.fe10
        return [record.values.get("name") or "" for record in fe10.tables.get("terrain", [])] if fe10 else []

    def _scenery_records(self) -> list:
        fe10 = self.session.fe10
        return fe10.tables.get("battle_scenery", []) if fe10 is not None else []

    def battle_scenery_rows(self) -> list[BattleTerrainRow]:
        # the table stores BattleTerrName indices (0xFFFF: none); the editors work with the names
        names = fe10data.battle_scenery_names(self.data)
        return [BattleTerrainRow(record.values.get("map"),
                                 [names[i] if i < len(names) else None for i in record.lists.get("scenery", [])])
                for record in self._scenery_records()]

    def write_battle_scenery_rows(self, rows):
        current = self._scenery_records()
        if len(rows) != len(current):
            raise ValueError("Adding Radiant Dawn battle-scenery rows is not decoded yet.")
        data = self.data
        names = fe10data.battle_scenery_names(data)
        index = {name: i for i, name in reversed(list(enumerate(names))) if name}
        for i, (row, record) in enumerate(zip(rows, current)):
            if row.map_name != record.values.get("map"):
                raise ValueError("Renaming Radiant Dawn battle-scenery rows is not decoded yet.")
            for terrain, (new, old) in enumerate(zip(row.scenes, record.lists.get("scenery", []))):
                if new is not None and new not in index:
                    raise ValueError(f"{new} is not a BattleTerrName entry; adding Radiant Dawn battle "
                                     "backgrounds is not decoded yet.")
                new = index[new] if new is not None else FE10_NO_SCENERY
                if new != old:
                    data = fe10data.set_battle_scenery(data, i, terrain, new)
        return data

    def chapter_templates(self, project) -> list[str]:
        from . import chapters_fe10
        return chapters_fe10.templates(project, self.data)

    def free_chapters(self, project) -> list[str]:
        from . import chapters_fe10
        return chapters_fe10.free_chapters(project, self.data)

    def add_story_chapter(self, project, source_id, new_id, title, after, flow):
        from . import chapters_fe10
        plan = chapters_fe10.add_story_chapter(project, self.data, source_id, new_id, title, after, flow)
        return plan.fe10data, plan.warnings


def data_adapter(session) -> Optional[DataAdapter]:
    """The adapter of a game-data session (None for no session). Light stand-ins with an ``fe10``
    database are read as Radiant Dawn, anything else as Path of Radiance."""
    if session is None:
        return None
    adapter = getattr(session, "adapter", None)
    if isinstance(adapter, DataAdapter):
        return adapter
    return RdDataAdapter(session) if getattr(session, "fe10", None) is not None else PorDataAdapter(session)
