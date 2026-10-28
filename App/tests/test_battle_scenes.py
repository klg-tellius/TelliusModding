"""The chapter page's Battle scenes tab: finding a map's row and the scenes to pick from."""

import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from fe_modding.formats.fe8data import BattleTerrainRow
from fe_modding import game_adapter
from fe_modding.gui import battle_scene_editor as bse

ROWS = [BattleTerrainRow("Map6", ["map01_woods", "map01_plain"]),
        BattleTerrainRow("bmap01", [None, "Castle_In"]),
        BattleTerrainRow("bmap02", ["map01_woods", None])]


class BattleSceneTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        for folder, pack in (("map01_woods", "a.cmp"), ("castle_in", "b.cmp"), ("empty", None)):
            (root / "files" / "zbg" / folder).mkdir(parents=True)
            if pack:
                (root / "files" / "zbg" / folder / pack).write_bytes(b"")
        self.project = SimpleNamespace(extracted_dir=root)

    def tearDown(self):
        self.tmp.cleanup()

    def test_scene_models_list_folders_with_a_pack(self):
        self.assertEqual(sorted(bse.scene_models(self.project)), ["castle_in", "map01_woods"])

    def test_find_scene_ignores_case(self):
        models = bse.scene_models(self.project)
        self.assertEqual(bse.find_scene(models, "Castle_In").parent.name, "castle_in")
        self.assertIsNone(bse.find_scene(models, "map01_plain"))
        self.assertIsNone(bse.find_scene(models, None))

    def test_scene_names_join_folders_and_table(self):
        names = bse.scene_names(bse.scene_models(self.project), ROWS)
        self.assertEqual(names, ["castle_in", "map01_plain", "map01_woods"])

    def test_effective_scene_uses_selected_rows_first_terrain_cell(self):
        rows = [
            BattleTerrainRow("Map6", ["map02_cliff01", None, "map6_bridge"]),
            BattleTerrainRow("bmap01", ["map01_woods", None, "map01_castle"]),
            BattleTerrainRow("empty", [None, None, None]),
        ]
        self.assertEqual(bse.effective_scene(rows, "bmap01", 2), "map01_castle")
        self.assertEqual(bse.effective_scene(rows, "bmap01", 1), "map01_woods")
        self.assertEqual(bse.effective_scene(rows, "unknown", 2), "map6_bridge")
        self.assertEqual(bse.effective_scene(rows, "unknown", 1), "map02_cliff01")
        self.assertIsNone(bse.effective_scene(rows, "empty", 1))
        self.assertIsNone(bse.effective_scene([BattleTerrainRow("Map6", [None, None])], "unknown", 1))
        self.assertIsNone(bse.effective_scene([], "bmap01", 1))

    def test_empty_cell_note_names_the_selected_rows_fallback(self):
        rows = [
            BattleTerrainRow("Map6", ["map02_cliff01", None]),
            BattleTerrainRow("bmap01", ["map01_woods", None]),
        ]

        class Label:
            def configure(self, **options):
                self.options = options

        note = Label()
        panel = SimpleNamespace(
            _cells={1: (None, note)},
            _map="bmap01",
            _session=lambda: None,
            _scene_models=lambda: {"map01_woods": Path("woods.cmp"),
                                   "map02_cliff01": Path("cliff.cmp")},
        )
        bse.BattleScenePanel._update_note(panel, 1, rows, 1)
        self.assertEqual(note.options["text"], "default: map01_woods")
        panel._map = "unknown"
        bse.BattleScenePanel._update_note(panel, 1, rows, None)
        self.assertEqual(note.options["text"], "default: map02_cliff01")

    def test_rows_and_users(self):
        self.assertEqual(bse.find_row(ROWS, "bmap02"), 2)
        self.assertEqual(bse.find_row(ROWS, "Map6"), 0)
        self.assertIsNone(bse.find_row(ROWS, "bmap03"))
        users = bse.scene_users(ROWS)
        self.assertEqual(users["map01_woods"], ["Shared default (row 0: Map6)", "bmap02"])
        self.assertEqual(users["castle_in"], ["bmap01"])


def _fe10_panel(session, log):
    """The parts of BattleScenePanel that _rows / _write use, around a Radiant Dawn session."""
    panel = SimpleNamespace(_data_file="FE10Data.cms", _changelog=SimpleNamespace(append=lambda *a: log.append(a)))
    panel._session = lambda: session
    return panel


class Fe10BattleSceneTests(unittest.TestCase):
    """Radiant Dawn rows hold BattleTerrName indices (0xFFFF: none); the panel shows them as names."""

    def setUp(self):
        record = SimpleNamespace(values={"map": "bmap0101"}, lists={"scenery": [1, 0xFFFF, 0]})
        self.session = SimpleNamespace(data=b"data", fe10=SimpleNamespace(tables={"battle_scenery": [record]}),
                                       changed=lambda source: None)
        self.log = []
        self.panel = _fe10_panel(self.session, self.log)
        self.names = mock.patch.object(game_adapter.fe10data, "battle_scenery_names", return_value=["bgA", "bgB"])
        self.names.start()

    def tearDown(self):
        self.names.stop()

    def test_rows_show_indices_as_names(self):
        rows = bse.BattleScenePanel._rows(self.panel)
        self.assertEqual(rows, [BattleTerrainRow("bmap0101", ["bgB", None, "bgA"])])
        self.assertEqual(bse.scene_names({}, rows), ["bgA", "bgB"])

    def test_write_stores_names_as_indices(self):
        calls = []

        def set_scenery(data, index, terrain, scenery):
            calls.append((index, terrain, scenery))
            return data + b"!"

        with mock.patch.object(game_adapter.fe10data, "set_battle_scenery", side_effect=set_scenery):
            bse.BattleScenePanel._write(self.panel, [BattleTerrainRow("bmap0101", [None, "bgA", "bgA"])], "edit")
        self.assertEqual(calls, [(0, 0, 0xFFFF), (0, 1, 0)])
        self.assertEqual(self.session.data, b"data!!")
        self.assertEqual(self.log, [("FE10Data.cms", "edit")])

    def test_write_refuses_a_name_outside_the_table(self):
        with self.assertRaises(ValueError):
            bse.BattleScenePanel._write(self.panel, [BattleTerrainRow("bmap0101", ["bgB", "new_bg", "bgA"])], "edit")


@unittest.skipUnless(os.environ.get("FE10_EXTRACTED_FILES"),
                     "set FE10_EXTRACTED_FILES to an extracted Radiant Dawn files/ directory")
class DiscFe10BattleSceneTests(unittest.TestCase):
    def test_retail_rows_round_trip_through_the_panel(self):
        from fe_modding.formats import fe10data, lz10
        data = lz10.decompress((Path(os.environ["FE10_EXTRACTED_FILES"]) / "FE10Data.cms").read_bytes())
        session = SimpleNamespace(data=data, fe10=fe10data.read_fe10data(data), changed=lambda source: None)
        panel = _fe10_panel(session, [])
        rows = bse.BattleScenePanel._rows(panel)
        self.assertEqual(len(rows), 44)
        self.assertTrue(all(isinstance(scene, str) for row in rows for scene in row.scenes if scene is not None))
        bse.BattleScenePanel._write(panel, rows, "unchanged")
        self.assertEqual(session.data, data)
        target = next(name for name in fe10data.battle_scenery_names(data) if name and name != rows[1].scenes[0])
        rows[1].scenes[0] = target
        bse.BattleScenePanel._write(panel, rows, "edit")
        session.fe10 = fe10data.read_fe10data(session.data)
        self.assertEqual(bse.BattleScenePanel._rows(panel)[1].scenes[0], target)


if __name__ == "__main__":
    unittest.main()
