"""chapter_form + game_adapter: one Chapter data form on both games, and Radiant Dawn battle scenes
that can gain rows and backdrop names."""

import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fe_modding import chapter_form
from fe_modding.formats.fe8data import BattleTerrainRow

FE9 = os.environ.get("FE9_EXTRACTED_FILES")
FE10 = os.environ.get("FE10_EXTRACTED_FILES")


def _keys(sections):
    keys = []
    for section in sections:
        for spec in section.fields:
            keys += ([spec.key.format(i=i) for i in range(len(spec.names))] if spec.kind == chapter_form.BYTES
                     else [spec.key])
    return keys


class SameFormTests(unittest.TestCase):
    def test_both_games_share_the_section_layout(self):
        # the first three sections are the same on both games; each adds its own last section
        from fe_modding.game_adapter import PorDataAdapter, RdDataAdapter
        for adapter in (PorDataAdapter, RdDataAdapter):
            self.assertTrue(hasattr(adapter, "chapter_sections"))
        self.assertEqual(RdDataAdapter.chapter_actions, ("title_card",))
        self.assertEqual(PorDataAdapter.chapter_actions, ())


@unittest.skipUnless(FE9, "set FE9_EXTRACTED_FILES to an extracted Path of Radiance files/ directory")
class PorChapterFormTests(unittest.TestCase):
    def setUp(self):
        from fe_modding.formats import fe8data
        from fe_modding.game_adapter import PorDataAdapter
        self.data = (Path(FE9) / "FE8Data.bin").read_bytes()
        self.adapter = PorDataAdapter(SimpleNamespace(data=self.data, fe8=fe8data.read_fe8data(self.data)))

    def test_chapter_nine(self):
        records = self.adapter.chapter_records("09", "bmap09")
        self.assertEqual(self.adapter.chapter_summary(records[0])[2:], ("C09", 9))
        sections = self.adapter.chapter_sections(records[0])
        self.assertEqual([s.title for s in sections], ["Identity and files", "Objectives (text keys)", "Scenes",
                                                       "Enemy levels and trial grades"])
        for key in _keys(sections):
            self.adapter.chapter_value(self.data, records[0], key)
        self.assertEqual(self.adapter.chapter_value(self.data, records[0], "map_name"), "bmap09")
        data = self.adapter.write_chapter_value(self.data, records[0], "bgm", "BGM_NEW")
        self.assertEqual(self.adapter.chapter_value(data, records[0], "bgm"), "BGM_NEW")
        data = self.adapter.write_chapter_value(self.data, records[0], "enemy_bonus_level2", 5)
        self.assertEqual(self.adapter.chapter_value(data, records[0], "enemy_bonus_level2"), "5")


@unittest.skipUnless(FE10, "set FE10_EXTRACTED_FILES to an extracted Radiant Dawn files/ directory")
class RdChapterFormTests(unittest.TestCase):
    def setUp(self):
        from fe_modding.formats import fe10data, lz10
        from fe_modding.game_adapter import RdDataAdapter
        self.fe10data = fe10data
        self.data = lz10.decompress((Path(FE10) / "FE10Data.cms").read_bytes())
        self.adapter = RdDataAdapter(SimpleNamespace(data=self.data, fe10=fe10data.read_fe10data(self.data)))

    def test_every_field_reads_and_writes_back(self):
        index = self.adapter.chapter_records("0407a", "bmap0407a")[0]
        self.assertEqual(self.adapter.chapter_summary(index)[3], "C0407a")
        sections = self.adapter.chapter_sections(index)
        self.assertEqual([s.title for s in sections][:3], ["Identity and files", "Objectives (text keys)", "Scenes"])
        data = self.data
        for section in sections:
            for spec in section.fields:
                shown = self.adapter.chapter_value(data, index, spec.key)
                value = int(shown) if spec.kind == chapter_form.NUMBER else shown
                data = self.adapter.write_chapter_value(data, index, spec.key, value)
        self.assertEqual([r.values for r in self.fe10data.read_table(data, "chapter")],
                         [r.values for r in self.fe10data.read_table(self.data, "chapter")])

    def test_ids_and_numbers_stay_unique(self):
        index = self.adapter.chapter_records("0102", None)[0]
        with self.assertRaisesRegex(ValueError, "number 1"):
            self.adapter.write_chapter_value(self.data, index, "number", 1)
        with self.assertRaisesRegex(ValueError, "C0101"):
            self.adapter.write_chapter_value(self.data, index, "cid", "C0101")
        data = self.adapter.write_chapter_value(self.data, index, "lord", "")
        self.assertEqual(self.adapter.chapter_value(data, index, "lord"), "")
        self.assertEqual(self.adapter.chapter_records("final", None),
                         [r.index for r in self.fe10data.read_table(self.data, "chapter")
                          if r.values["cid"] == "CFINAL"])


@unittest.skipUnless(FE10, "set FE10_EXTRACTED_FILES to an extracted Radiant Dawn files/ directory")
class RdBattleSceneryTests(unittest.TestCase):
    """A scratch Radiant Dawn project with FE10Data.cms, FE10Battle.cms and two zbg/ folders."""

    def setUp(self):
        from fe_modding.formats import fe10data
        from fe_modding.game_adapter import RdDataAdapter
        from fe_modding.games import Game
        from fe_modding.project import ModProject

        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        project = ModProject.create(Path(tmp.name), "rd scenes", Game.RADIANT_DAWN)
        files = project.files_dir
        for rel in ("FE10Data.cms", "FE10Battle.cms", "zbg/bg0101twn/bf.cmp"):
            (files / rel).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy(Path(FE10) / rel, files / rel)
            (files / rel).chmod(0o666)
        self.fe10data = fe10data
        data = project.read_logical("game_data")
        self.session = SimpleNamespace(data=data, fe10=fe10data.read_fe10data(data), project=project)
        self.adapter = RdDataAdapter(self.session)
        self.project = project

    def test_backdrop_names_find_their_folders(self):
        models = self.adapter.scene_models(self.project)
        self.assertEqual(models["bg0101街"].parent.name, "bg0101twn")

    def test_new_row_and_new_name(self):
        rows = self.adapter.battle_scenery_rows()
        count = len(rows[0].scenes)
        row = self.adapter.new_scenery_row("bmap0501", count)
        row.scenes[3] = "bg汎用02森林"  # an FE10Battle backdrop no retail row lists
        data = self.adapter.write_battle_scenery_rows(rows + [row])
        names = self.fe10data.battle_scenery_names(data)
        self.assertEqual(names[-2:], ["bg魔法", "bg汎用02森林"])
        written = self.fe10data.read_table(data, "battle_scenery")
        self.assertEqual(written[-1].values["map"], "bmap0501")
        self.assertEqual(written[-1].lists["scenery"][:4], [len(names) - 2, 0xFFFF, 0xFFFF, len(names) - 1])
        self.assertEqual([r.values for r in written[:-1]], [r.values for r in
                                                           self.fe10data.read_table(self.session.data, "battle_scenery")])
        with self.assertRaisesRegex(ValueError, "FE10BMapData"):
            self.adapter.write_battle_scenery_rows([BattleTerrainRow(rows[0].map_name, ["bgNothing"] * count)]
                                                   + rows[1:])


if __name__ == "__main__":
    unittest.main()
