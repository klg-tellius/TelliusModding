"""What a fixture can do to the work project. Every edit goes through the app's own functions,
so a test that passes also exercises the code path the editors use."""
from __future__ import annotations

import copy
from pathlib import Path
from typing import Optional

from fe_modding import chapters, script_sources
from fe_modding.formats import dispo, fe8data, lz10, pak, save_file as sf
from fe_modding.game_code import entries  # noqa: F401  (registers the whole catalog)
from fe_modding.game_code.catalog import CATALOG
from fe_modding.game_code.editor import CodeEditor
from fe_modding.game_profile import files_root_of

#: Victory script appended to a chapter when a scenario asks for an automatic win.
AUTO_WIN = ('\n# Session playtest: automatic victory\n'
            '@on_phase(turn_from={turn}, turn_to={turn}, phase="enemy")\n'
            'def SessionAutoWin():\n    set("gf_complete")\n')


class Context:
    def __init__(self, project, saves: Path):
        self.project = project
        self.saves = saves
        self.facts: dict = {}           # values computed while building, shown in the instructions
        self._fe8: Optional[bytes] = None
        self._editor: Optional[CodeEditor] = None

    # -- FE8Data ---------------------------------------------------------------------------------
    @property
    def fe8(self) -> bytes:
        if self._fe8 is None:
            self._fe8 = self.project.read_logical("game_data")
        return self._fe8

    @fe8.setter
    def fe8(self, data: bytes) -> None:
        self._fe8 = data
        self.project.write_logical("game_data", data)

    @property
    def data(self) -> fe8data.Fe8Data:
        return fe8data.read_fe8data(self.fe8)

    def character(self, pid: str) -> fe8data.CharacterEntry:
        return next(c for c in self.data.characters if c.pid == pid)

    def job(self, jid: str) -> fe8data.ClassEntry:
        return next(c for c in self.data.classes if c.jid == jid)

    def item_number(self, iid: str) -> int:
        """1-based item number, as saves and inventories store it."""
        return next(i.index for i in self.data.items if i.iid == iid) + 1

    def job_number(self, jid: str) -> int:
        return self.job(jid).index + 1

    def set_character(self, pid: str, **fields) -> None:
        data = self.fe8
        index = self.character(pid).index
        for key, value in fields.items():
            data = fe8data.patch_character_field(data, index, key, value)
        self.fe8 = data

    def add_character_skill(self, pid: str, sid: str) -> None:
        """Put ``sid`` in the character's first free skill slot."""
        person = self.character(pid)
        if sid in person.sids:
            return
        slot = person.sids.index(None)
        self.set_character(pid, **{f"sid{slot}": sid})

    def set_class(self, jid: str, **fields) -> None:
        data = self.fe8
        index = self.job(jid).index
        for key, value in fields.items():
            data = fe8data.patch_class_field(data, index, key, value)
        self.fe8 = data

    def chapter_record(self, chapter: int) -> fe8data.ChapterRecord:
        return next(r for r in fe8data.read_chapter_data(self.fe8) if r.chapter_id == chapter)

    # -- Game Code -------------------------------------------------------------------------------
    @property
    def code(self) -> CodeEditor:
        if self._editor is None:
            self._editor = CodeEditor(self.project.extracted_dir, self.project.write_keeping_original,
                                      self.project.extracted_bytes)
        return self._editor

    def patch(self, *ids: str) -> None:
        for patch_id in ids:
            self.code.set_patch(CATALOG.entries[patch_id], True)

    def tune(self, **values) -> None:
        """``tune(**{"combat.charisma_bonus": 30})``; dots are not valid keywords, so pass a dict."""
        for tunable_id, value in values.items():
            self.code.set_value(CATALOG.entries[tunable_id], value)

    def tunes(self, values: dict) -> None:
        self.tune(**values)

    def drop_editor(self) -> None:
        """Forget the open main.dol (another module wrote it)."""
        self._editor = None

    # -- scripts ---------------------------------------------------------------------------------
    def chapter_script(self, chapter: int) -> Path:
        path = script_sources.chapter_script(self.project, f"{chapter:02d}")
        if path is None:
            raise ValueError(f"Chapter {chapter:02d} has no script")
        return path

    def script_source(self, chapter: int) -> str:
        return script_sources.peek(self.project, self.chapter_script(chapter))

    def append_script(self, chapter: int, source: str) -> None:
        script = script_sources.load(self.project, self.chapter_script(chapter))
        script_sources.save(self.project, script, script.source + source)

    def replace_script(self, chapter: int, old: str, new: str, count: int = 1) -> None:
        script = script_sources.load(self.project, self.chapter_script(chapter))
        if script.source.count(old) < count:
            raise ValueError(f"C{chapter:02d}: expected text not found: {old!r}")
        script_sources.save(self.project, script, script.source.replace(old, new, count))

    def auto_win(self, chapter: int, turn: int) -> None:
        self.append_script(chapter, AUTO_WIN.format(turn=turn))

    # -- deployments -----------------------------------------------------------------------------
    def dispos_path(self, folder: str) -> Path:
        return files_root_of(self.project) / "zmap" / folder / "dispos.cmp"

    def dispos(self, folder: str) -> dict[str, dispo.DispoDocument]:
        """``{variant file name: document}`` of a map folder's ``dispos.cmp``."""
        packed = lz10.decompress(self.dispos_path(folder).read_bytes())
        return {e.name: dispo.parse_dispo(pak.read_pak_file_content(packed, e)) for e in pak.read_pak_entries(packed)}

    def write_dispos(self, folder: str, docs: dict[str, dispo.DispoDocument]) -> None:
        path = self.dispos_path(folder)
        packed = lz10.decompress(path.read_bytes())
        entries_ = pak.read_pak_entries(packed)
        files = [(e.name, dispo.build_dispo(docs[e.name]) if e.name in docs else pak.read_pak_file_content(packed, e))
                 for e in entries_]
        self.project.write_keeping_original(path, lz10.compress(pak.pack_pak(files, [e.reserved for e in entries_])))

    # -- saves -----------------------------------------------------------------------------------
    def load_save(self, name: str) -> sf.SaveFile:
        return sf.SaveFile.from_bytes((self.saves / name).read_bytes())

    def unit(self, block: sf.SaveBlock, pid: str) -> sf.UnitRecord:
        number = self.character(pid).index + 1
        for unit in block.units:
            if unit is not None and unit.character == number and unit.army in (0, 5):
                return unit
        raise ValueError(f"{pid} is not in the saved army")

    def set_unit_job(self, unit: sf.UnitRecord, jid: str, level: int, exp: int) -> None:
        """Change class and level, keeping every stat within the new class's caps and HP full.

        Class skills are serialized in an FE9 save.  Merely replacing ``job`` therefore leaves
        flags from the old class behind (a promoted unit changed to Mage still has SID_HIGHER;
        a transformed laguz can retain its transformation skills).  Rebuild the mask from the
        character and destination class so fixture reclassing behaves like a freshly created
        unit of that class.
        """
        job = self.job(jid)
        unit.job = job.index + 1
        unit.level, unit.exp = level, exp
        person = self.data.characters[unit.character - 1]
        unit.skills = bytes(len(unit.skills))
        skill_index = {skill.sid: skill.index for skill in self.data.skills}
        for sid in (*person.sids, *job.skills):
            if sid is not None:
                unit.set_skill(skill_index[sid], True)
        gains = bytearray(unit.stats)
        for i in range(8):
            room = job.stat_caps[i] - job.base_stats[i] - person.stat_bonus[i]
            gains[i] = max(0, min(gains[i], room))
        unit.stats = bytes(gains)
        unit.hp = min(job.stat_caps[0], job.base_stats[0] + person.stat_bonus[0] + gains[0])

    def set_items(self, unit: sf.UnitRecord, iids: list[str]) -> None:
        """Replace the inventory: weapons from slot 1, other items from slot 5 (the game's unit screen
        shows slots 1-4 as weapons and 5-8 as items); the first weapon is equipped."""
        items = self.data.items
        weapons, others = [], []
        for iid in iids:
            item = next(i for i in items if i.iid == iid)
            slot = sf.ItemSlot(item.index + 1, max(item.uses, 1), 0)
            (others if fe8data.item_category(item) in ("Item", "Other") else weapons).append(slot)
        if len(weapons) > 4 or len(others) > 4:
            raise ValueError("at most four weapons and four other items")
        if weapons:
            weapons[0].flags = 0x80
        unit.items = (weapons + [sf.ItemSlot() for _ in range(4 - len(weapons))]
                      + others + [sf.ItemSlot() for _ in range(4 - len(others))])

    def save_copy(self, save: sf.SaveFile, index: int, chapter: Optional[int] = None) -> bytes:
        """The card file to test block ``index`` (re-signed); ``chapter`` moves it to that chapter's start."""
        return sf.play_copy(save, index, chapter, rebuild=(index,))


def clone(value):
    return copy.deepcopy(value)
