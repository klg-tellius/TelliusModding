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

from . import chapter_form, excel_io
from .supports_model import PorSupports, RdSupports
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
    #: The backdrop of a map with no battle-scenery row of its own, on every terrain type; None: such a
    #: map uses the table's first row (Path of Radiance).
    no_row_scene: Optional[str] = None

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

    def categories(self, kind: str) -> Optional[tuple[list[str], list[str]]]:
        """``(one category per record, the category order)`` for the filter chips of ``kind``
        (``class``: tier or laguz, ``item``: weapon type), or None when the table has none."""
        return None

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
        """The file with ``rows`` written back (rows may be appended). Raises ValueError for a change the
        game's table cannot hold."""
        raise NotImplementedError

    def new_scenery_row(self, map_name: str, terrain_count: int) -> BattleTerrainRow:
        """A row for a map that had none, fighting where the map fought before."""
        return BattleTerrainRow(map_name, [None] * terrain_count)

    def scene_models(self, project) -> dict:
        """Battle-background name -> its model pack (``zbg/<folder>/*.cmp``)."""
        return zbg_packs(project)

    # -- supports ---------------------------------------------------------------------------
    #: The Supports tab's model class (:mod:`supports_model`), built from the file's bytes.
    supports_model = PorSupports

    # -- chapters ---------------------------------------------------------------------------
    #: Extra buttons of the Chapter data form (``"title_card"``: draw the title card from the title).
    chapter_actions: tuple = ()

    def chapter_records(self, chapter_id: Optional[str], map_name: Optional[str]) -> list[int]:
        """The ``ChapterData`` records of a chapter page, the one using ``map_name`` first."""
        raise NotImplementedError

    def chapter_summary(self, index: int) -> tuple:
        """``(title key, title text, script, id)`` of a record, for its label in pickers."""
        raise NotImplementedError

    def chapter_sections(self, index: int) -> list:
        """The Chapter data form of a record: :class:`chapter_form.ChapterSection` items."""
        raise NotImplementedError

    def chapter_value(self, data: bytes, index: int, key: str) -> str:
        raise NotImplementedError

    def write_chapter_value(self, data: bytes, index: int, key: str, value) -> bytes:
        """``data`` with one chapter field set. Raises ValueError with the reason when refused."""
        raise NotImplementedError

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

    def deletable(self, chapter_id: str) -> bool:
        """Whether Delete chapter can remove ``chapter_id``."""
        raise NotImplementedError

    def delete_rule(self) -> str:
        """Which chapters can be deleted, for the refusal message."""
        raise NotImplementedError

    def remove_story_chapter(self, project, chapter_id: str, flow) -> bytes:
        """Delete chapter ``chapter_id`` and its files; chapters that led to it lead to its successor
        in ``flow`` (a :class:`~.game_code.story_flow.StoryFlow`). Returns the game-data file for the
        session to save."""
        raise NotImplementedError

    # -- colour variants (Colour variant… on the character page and the class form) ----------------
    #: Which choices the Colour variant dialog offers: "armies" (the army whose colours a variant
    #: takes), "family" (the character's other records), "classes" (class variants).
    colour_variant_options: frozenset = frozenset()

    def character_family(self, project, pid: str) -> tuple[list[str], list[str]]:
        """Records the character's variant should also cover: (suggested, others)."""
        return [], []

    def plan_character_variant(self, project, pid: str, tag: str, **options):
        raise NotImplementedError

    def plan_class_variant(self, project, jid: str, army: str, tag: str, **options):
        raise ValueError("Class colour variants are not available for this game.")

    def apply_variant(self, project, plan, recolour) -> list[str]:
        raise NotImplementedError

    def campaign_problems(self, project, chapter_specs: list, character_specs: list, after: Optional[str]) -> list:
        """Why New campaign can't add these chapters (``campaign.ChapterSpec``, templates as chapter page
        ids) and characters after chapter ``after``; empty: it can."""
        raise NotImplementedError

    def add_campaign(self, project, chapter_specs: list, character_specs: list, after: Optional[str], flow):
        """Add the campaign (chapters in story order after ``after``, then the characters). Returns the
        game-data file for the session to save, the new chapter page ids and the warnings."""
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

    def categories(self, kind):
        fe8 = self.session.fe8
        if fe8 is None:
            return None
        if kind == "class":
            return [fe8data.class_category(c, fe8.classes) for c in fe8.classes], list(fe8data.CLASS_CATEGORIES)
        if kind == "item":
            return [fe8data.item_category(it) for it in fe8.items], list(fe8data.ITEM_CATEGORIES)
        return None

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

    def chapter_records(self, chapter_id, map_name):
        try:
            records = fe8data.read_chapter_data(self.data)
        except (KeyError, ValueError, struct.error):
            return []
        number = int(chapter_id) if chapter_id and chapter_id.isdigit() else None
        found = [r.index for r in records if (r.chapter_id == number if number is not None
                                              else bool(map_name and r.map_name == map_name))]
        if number is not None and map_name:
            found.sort(key=lambda i: records[i].map_name != map_name)
        return found

    def chapter_summary(self, index):
        record = fe8data.read_chapter_data(self.data)[index]
        return record.title_key, record.title_text, record.script, record.chapter_id

    def chapter_sections(self, index):
        return chapter_form.por_sections(self.data, index)

    def chapter_value(self, data, index, key):
        return chapter_form.por_value(data, index, key)

    def write_chapter_value(self, data, index, key, value):
        return chapter_form.por_write(data, index, key, value)

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

    def deletable(self, chapter_id):
        from . import chapters
        return chapter_id.isdigit() and int(chapter_id) in chapters.DELETABLE_CHAPTER_IDS

    def delete_rule(self):
        return "The Prologue starts every new game and the Ending completes it, so those chapters cannot be deleted."

    def remove_story_chapter(self, project, chapter_id, flow):
        from . import chapters
        return chapters.remove_story_chapter(project, self.data, chapter_id, getattr(flow, "flow", flow)).fe8data

    colour_variant_options = frozenset({"armies", "family", "classes"})

    def character_family(self, project, pid):
        from . import colour_variants
        return colour_variants.character_family(project, pid)

    def plan_character_variant(self, project, pid, tag, **options):
        from . import colour_variants
        return colour_variants.plan_character_variant(project, pid, tag, **options)

    def plan_class_variant(self, project, jid, army, tag, **options):
        from . import colour_variants
        return colour_variants.plan_class_variant(project, jid, army, tag, **options)

    def apply_variant(self, project, plan, recolour):
        from . import colour_variants
        return colour_variants.apply_variant(project, plan, recolour)

    def campaign_problems(self, project, chapter_specs, character_specs, after):
        from . import campaign
        return campaign.check_campaign(project, self.data, chapter_specs, character_specs,
                                       int(after) if after is not None else None)

    def add_campaign(self, project, chapter_specs, character_specs, after, flow):
        from . import campaign
        result = campaign.add_campaign(project, self.data, chapter_specs, character_specs,
                                       int(after) if after is not None else None, getattr(flow, "flow", flow))
        return result.fe8data, [f"{c:02d}" for c in result.chapter_ids], result.warnings


class RdDataAdapter(DataAdapter):
    """Radiant Dawn: ``FE10Data.cms`` through :mod:`formats.fe10data`."""

    can_start_empty = False
    #: 8011d3a4 (the BattleTerrIndex lookup): a map name found in no row gets this fixed name; a map
    #: with no name gets row 0; an empty cell (0xFFFF) uses the row's first cell.
    no_row_scene = "bg魔法"

    def records(self, kind: str) -> list[EntityRow]:
        fe10 = self.session.fe10
        if fe10 is None:
            return []
        return [EntityRow(record.index, record.id) for record in fe10.tables.get(kind, [])]

    #: Radiant Dawn's classes: laguz carry the SFXC_ALIZE sound class, promoted tiers a tier skill.
    CLASS_CATEGORIES = ["First tier", "Second tier", "Third tier", "Laguz"]
    #: weapon type -> chip, named like Path of Radiance's (``blow`` is the laguz strike).
    ITEM_TYPES = {"sword": "Sword", "lance": "Lance", "axe": "Axe", "bow": "Bow", "knife": "Knife",
                  "flame": "Fire", "thunder": "Thunder", "wind": "Wind", "light": "Light", "dark": "Dark",
                  "rod": "Staff", "blow": "Laguz strike", "ballista": "Ballista", "item": "Item"}
    ITEM_CATEGORIES = [*dict.fromkeys(ITEM_TYPES.values()), "Other"]

    def categories(self, kind):
        fe10 = self.session.fe10
        if fe10 is None:
            return None
        if kind == "class":
            def tier(record):
                if "SFXC_ALIZE" in record.lists.get("sounds", []):
                    return "Laguz"
                skills = record.lists.get("skills", [])
                return "Third tier" if "SID_HIGHEST" in skills else "Second tier" if "SID_HIGHER" in skills \
                    else "First tier"
            return [tier(r) for r in fe10.tables.get("class", [])], list(self.CLASS_CATEGORIES)
        if kind == "item":
            return ([self.ITEM_TYPES.get(r.values.get("weapon_type") or "", "Other")
                     for r in fe10.tables.get("item", [])], list(self.ITEM_CATEGORIES))
        return None

    def add_record(self, kind, new_id, copy_from):
        if copy_from is None:
            raise ValueError("A new Radiant Dawn record starts as a copy of an existing one: pick one to copy.")
        if new_id and self.index_of(kind, new_id) is not None:
            raise ValueError(f"{new_id} is already used.")
        return fe10data.add_record(self.data, kind, copy_from, new_id or None)

    def excel_sheet(self, kind: str) -> Optional[str]:
        return excel_io.FE10_SHEETS.get(kind)

    def export_excel(self, path, kind: str) -> None:
        if self.excel_sheet(kind) is None:
            raise ValueError(f"No Excel sheet for {kind} records.")
        excel_io.export_fe10(path, self.data, kind)

    def import_excel(self, path, kind: str) -> tuple[bytes, list[str]]:
        if self.excel_sheet(kind) is None:
            raise ValueError(f"No Excel sheet for {kind} records.")
        return excel_io.import_fe10(path, self.data, kind)

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
        if len(rows) < len(current):
            raise ValueError("Radiant Dawn battle-scenery rows cannot be removed.")
        data = self.data
        known = self._backdrops()
        for i, row in enumerate(rows):
            if i < len(current) and row.map_name != current[i].values.get("map"):
                raise ValueError("Renaming Radiant Dawn battle-scenery rows is not decoded yet.")
            if not row.scenes or row.scenes[0] is None:
                raise ValueError(f"{row.map_name}: the first terrain type needs a backdrop (empty cells use it).")
            if i < len(current):
                old = current[i].lists.get("scenery", [])
            else:
                data, _index = fe10data.add_battle_scenery(data, 0, row.map_name)
                old = fe10data.read_table(data, "battle_scenery")[i].lists.get("scenery", [])
            for terrain, (new, was) in enumerate(zip(row.scenes, old)):
                if new is None:
                    value = FE10_NO_SCENERY
                else:
                    names = fe10data.battle_scenery_names(data)
                    if new in names:
                        value = names.index(new)
                    elif known is None:
                        raise ValueError(f"{new} is not in BattleTerrName, and FE10Battle.cms could not be read "
                                         "to check it is a backdrop.")
                    elif new not in known:
                        raise ValueError(f"{new} is not a backdrop of FE10Battle.cms (FE10BMapData).")
                    else:
                        data, value = fe10data.add_battle_scenery_name(data, new)
                if value != was:
                    data = fe10data.set_battle_scenery(data, i, terrain, value)
        return data

    def new_scenery_row(self, map_name, terrain_count):
        return BattleTerrainRow(map_name, [self.no_row_scene] + [None] * (terrain_count - 1))

    def _battle_file(self):
        """FE10Battle.cms, parsed once per change of the file (None when missing or unreadable)."""
        project = getattr(self.session, "project", None)
        if project is None:
            return None
        try:
            stamp = project.logical_path("battle_data").stat().st_mtime_ns
        except OSError:
            return None
        cached = getattr(self, "_battle_cache", None)
        if cached is None or cached[0] != stamp:
            try:
                from .formats import fe10_battle
                document = fe10_battle.read_fe10_battle(project.read_logical("battle_data"))
            except Exception:  # noqa: BLE001 - unreadable: names are not checked
                document = None
            self._battle_cache = cached = (stamp, document)
        return cached[1]

    def _backdrops(self) -> Optional[set]:
        """The backdrop names FE10Battle.cms defines (None when it can't be read)."""
        battle = self._battle_file()
        return {m.map_name for m in battle.map_data} if battle is not None else None

    def scene_models(self, project):
        # a backdrop name is an FE10BMapData record whose first model's archive is its zbg/ folder
        battle = self._battle_file()
        if battle is None:
            return {}
        folders = zbg_packs(project)
        found = {}
        for record in battle.map_data:
            model = next((m for m in record.model_indices if m is not None), None)
            if model is not None and model < len(battle.map_models):
                pack = folders.get(battle.map_models[model].archive_name)
                if pack is not None:
                    found[record.map_name] = pack
        return found

    chapter_actions = ("title_card",)
    supports_model = RdSupports

    def chapter_records(self, chapter_id, map_name):
        from .game_code.rd_story import chapter_record_id
        records = self.session.fe10.tables.get("chapter", []) if self.session.fe10 is not None else []
        cid = chapter_record_id(chapter_id) if chapter_id else None
        found = [r.index for r in records if (r.values.get("cid") == cid if cid is not None
                                              else bool(map_name and r.values.get("map") == map_name))]
        if cid is not None and map_name:
            found.sort(key=lambda i: records[i].values.get("map") != map_name)
        return found

    def chapter_summary(self, index):
        values = self.session.fe10.tables["chapter"][index].values
        return values.get("title"), None, values.get("script"), values.get("cid")

    def chapter_sections(self, index):
        return chapter_form.rd_sections(self.data, index)

    def chapter_value(self, data, index, key):
        return chapter_form.rd_value(data, index, key)

    def write_chapter_value(self, data, index, key, value):
        return chapter_form.rd_write(data, index, key, value)

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

    def deletable(self, chapter_id):
        from . import chapters_fe10
        return chapters_fe10.deletable(chapter_id)

    def delete_rule(self):
        return ("Only added chapters (0501 and up) can be deleted: removing a retail chapter's record would shift "
                "the chapters after it. Take a retail chapter out of the story in the story flow instead.")

    def remove_story_chapter(self, project, chapter_id, flow):
        from . import chapters_fe10
        return chapters_fe10.remove_story_chapter(project, self.data, chapter_id, flow).fe10data

    def plan_character_variant(self, project, pid, tag, **options):
        from . import colour_variants_fe10
        kept = {k: v for k, v in options.items() if k in ("battle", "map_models", "portrait")}
        return colour_variants_fe10.plan_character_variant(project, pid, tag, **kept)

    def apply_variant(self, project, plan, recolour):
        from . import colour_variants_fe10
        return colour_variants_fe10.apply_variant(project, plan, recolour)

    def campaign_problems(self, project, chapter_specs, character_specs, after):
        from . import campaign
        return campaign.check_campaign_fe10(project, self.data, chapter_specs, character_specs, after)

    def add_campaign(self, project, chapter_specs, character_specs, after, flow):
        from . import campaign
        result = campaign.add_campaign_fe10(project, self.data, chapter_specs, character_specs, after, flow)
        return result.fe8data, list(result.chapter_ids), result.warnings


def zbg_packs(project) -> dict:
    """``zbg/`` folder name -> its pack, the first ``.cmp`` in the folder."""
    from .game_profile import files_root_of

    zbg = files_root_of(project) / "zbg"
    found = {}
    if zbg.is_dir():
        for folder in sorted(p for p in zbg.iterdir() if p.is_dir()):
            pack = next(iter(sorted(folder.glob("*.cmp"))), None)
            if pack is not None:
                found[folder.name] = pack
    return found


def data_adapter(session) -> Optional[DataAdapter]:
    """The adapter of a game-data session (None for no session). Light stand-ins with an ``fe10``
    database are read as Radiant Dawn, anything else as Path of Radiance."""
    if session is None:
        return None
    adapter = getattr(session, "adapter", None)
    if isinstance(adapter, DataAdapter):
        return adapter
    return RdDataAdapter(session) if getattr(session, "fe10", None) is not None else PorDataAdapter(session)
