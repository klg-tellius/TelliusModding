"""game_adapter: the per-game table operations behind the shared pages."""

import os
import re
import unittest
from pathlib import Path
from types import SimpleNamespace

from fe_modding.game_adapter import EntityRow, PorDataAdapter, RdDataAdapter, data_adapter
from fe_modding.game_profile import (CHAPTER_RECORD_FORM, CHARACTER_FORM, DATA_WORKSPACE, PATH_OF_RADIANCE_PROFILE,
                                     RADIANT_DAWN_PROFILE, SAVE_UNITS, SUPPORT_LIST)

APP = Path(__file__).resolve().parents[1] / "fe_modding"


def _fe10_session(*records_by_kind):
    tables = {kind: [SimpleNamespace(index=i, id=rid, values={}, lists={}) for i, rid in enumerate(ids)]
              for kind, ids in records_by_kind}
    return SimpleNamespace(data=b"data", fe10=SimpleNamespace(tables=tables))


class DataAdapterChoiceTests(unittest.TestCase):
    def test_sessions_carry_their_game_adapter(self):
        from fe_modding.gui.fe8_session import Fe8DataSession, Fe10DataSession

        project = SimpleNamespace(profile=PATH_OF_RADIANCE_PROFILE, logical_path=lambda name: Path("missing"))
        self.assertIsInstance(data_adapter(Fe8DataSession(project, None)), PorDataAdapter)
        project = SimpleNamespace(profile=RADIANT_DAWN_PROFILE, logical_path=lambda name: Path("missing"))
        self.assertIsInstance(data_adapter(Fe10DataSession(project, None)), RdDataAdapter)

    def test_stand_in_sessions_pick_by_database(self):
        self.assertIsInstance(data_adapter(_fe10_session()), RdDataAdapter)
        self.assertIsInstance(data_adapter(SimpleNamespace(data=b"", fe8=None)), PorDataAdapter)
        self.assertIsNone(data_adapter(None))


class RdAdapterTests(unittest.TestCase):
    def setUp(self):
        self.adapter = RdDataAdapter(_fe10_session(("character", ["PID_IKE", "PID_MICAIAH"])))

    def test_records_and_lookup(self):
        self.assertEqual(self.adapter.records("character"),
                         [EntityRow(0, "PID_IKE"), EntityRow(1, "PID_MICAIAH")])
        self.assertEqual(self.adapter.index_of("character", "PID_MICAIAH"), 1)
        self.assertIsNone(self.adapter.index_of("character", "PID_NOBODY"))
        self.assertEqual(self.adapter.records("class"), [])

    def test_new_record_must_copy_and_use_a_free_id(self):
        self.assertFalse(self.adapter.can_start_empty)
        with self.assertRaisesRegex(ValueError, "copy"):
            self.adapter.add_record("character", "PID_NEW", None)
        with self.assertRaisesRegex(ValueError, "already used"):
            self.adapter.add_record("character", "PID_IKE", 0)

    def test_no_excel_layout_yet(self):
        self.assertIsNone(self.adapter.excel_sheet("character"))
        with self.assertRaises(ValueError):
            self.adapter.export_excel("out.xlsx", "character")

    def test_maps_without_a_row_fight_on_one_backdrop(self):
        self.assertEqual(self.adapter.no_row_scene, "bg魔法")
        self.assertEqual(self.adapter.scene_models(SimpleNamespace()), {})  # no FE10Battle.cms to map names


class PorAdapterTests(unittest.TestCase):
    def test_excel_sheets(self):
        adapter = PorDataAdapter(SimpleNamespace(data=b"", fe8=None))
        self.assertEqual(adapter.excel_sheet("character"), "Characters")
        self.assertEqual(adapter.excel_sheet("item"), "Items")
        self.assertIsNone(adapter.excel_sheet("skill"))
        self.assertTrue(adapter.can_start_empty)
        self.assertIsNone(adapter.no_row_scene)
        self.assertEqual(adapter.records("character"), [])

    def test_records_read_typed_entries(self):
        fe8 = SimpleNamespace(characters=[SimpleNamespace(index=0, pid="PID_IKE")], classes=[], items=[], skills=[])
        adapter = PorDataAdapter(SimpleNamespace(data=b"", fe8=fe8))
        self.assertEqual(adapter.records("character"), [EntityRow(0, "PID_IKE")])


class ScreenCapabilityTests(unittest.TestCase):
    """The purpose-built screens are capabilities: PoR has them, RD gets each as its phase lands."""

    def test_capabilities(self):
        for feature in (CHARACTER_FORM, SUPPORT_LIST, DATA_WORKSPACE, SAVE_UNITS):
            self.assertTrue(PATH_OF_RADIANCE_PROFILE.supports(feature), feature)
            self.assertFalse(RADIANT_DAWN_PROFILE.supports(feature), feature)
        # Phase 4: one Chapter data form on both games
        self.assertTrue(PATH_OF_RADIANCE_PROFILE.supports(CHAPTER_RECORD_FORM))
        self.assertTrue(RADIANT_DAWN_PROFILE.supports(CHAPTER_RECORD_FORM))

    def test_converged_pages_hold_no_game_checks(self):
        pattern = re.compile(r'Game\.RADIANT_DAWN|Game\.PATH_OF_RADIANCE|getattr\([^)]*"fe10"'
                             r'|supports\(DATA_TABLES\) and not')
        for rel in ("gui/pages/characters.py", "gui/pages/data.py", "gui/pages/home.py", "gui/pages/saves.py",
                    "gui/chapter_settings.py", "gui/battle_scene_editor.py", "text_export.py"):
            source = (APP / rel).read_text(encoding="utf-8")
            self.assertEqual(pattern.findall(source), [], rel)


@unittest.skipUnless(os.environ.get("FE10_EXTRACTED_FILES"),
                     "set FE10_EXTRACTED_FILES to an extracted Radiant Dawn files/ directory")
class DiscRdAdapterTests(unittest.TestCase):
    def test_copy_a_character(self):
        from fe_modding.formats import fe10data, lz10
        data = lz10.decompress((Path(os.environ["FE10_EXTRACTED_FILES"]) / "FE10Data.cms").read_bytes())
        session = SimpleNamespace(data=data, fe10=fe10data.read_fe10data(data))
        adapter = data_adapter(session)
        count = len(adapter.records("character"))
        new, index = adapter.add_record("character", "PID_ADAPTER_TEST", 0)
        self.assertEqual(index, count)
        session.data, session.fe10 = new, fe10data.read_fe10data(new)
        self.assertEqual(adapter.index_of("character", "PID_ADAPTER_TEST"), count)
        self.assertEqual(len(adapter.terrain_keys()), len(session.fe10.tables["terrain"]))


@unittest.skipUnless(os.environ.get("FE9_EXTRACTED_FILES"),
                     "set FE9_EXTRACTED_FILES to an extracted Path of Radiance files/ directory")
class DiscPorAdapterTests(unittest.TestCase):
    def test_tables_through_the_adapter(self):
        from fe_modding.formats import fe8data
        data = (Path(os.environ["FE9_EXTRACTED_FILES"]) / "FE8Data.bin").read_bytes()
        session = SimpleNamespace(data=data, fe8=fe8data.read_fe8data(data))
        adapter = data_adapter(session)
        self.assertIsNotNone(adapter.index_of("character", "PID_IKE"))
        rows = adapter.battle_scenery_rows()
        self.assertTrue(rows)
        self.assertEqual(adapter.write_battle_scenery_rows(rows), data)
        self.assertEqual(len(adapter.terrain_keys()), 77)
        self.assertIsNotNone(adapter.template_groups("item"))


if __name__ == "__main__":
    unittest.main()
