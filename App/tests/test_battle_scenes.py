"""The chapter page's Battle scenes tab: finding a map's row and the scenes to pick from."""

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from fe_modding.formats.fe8data import BattleTerrainRow
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
            _scene_models=lambda: {"map01_woods": Path("woods.cmp"),
                                   "map02_cliff01": Path("cliff.cmp")},
        )
        bse.BattleScenePanel._update_note(panel, 1, rows, 1)
        self.assertEqual(note.options["text"], "first terrain scene: map01_woods")
        panel._map = "unknown"
        bse.BattleScenePanel._update_note(panel, 1, rows, None)
        self.assertEqual(note.options["text"], "first terrain scene: map02_cliff01")

    def test_rows_and_users(self):
        self.assertEqual(bse.find_row(ROWS, "bmap02"), 2)
        self.assertEqual(bse.find_row(ROWS, "Map6"), 0)
        self.assertIsNone(bse.find_row(ROWS, "bmap03"))
        users = bse.scene_users(ROWS)
        self.assertEqual(users["map01_woods"], ["Shared default (row 0: Map6)", "bmap02"])
        self.assertEqual(users["castle_in"], ["bmap01"])


if __name__ == "__main__":
    unittest.main()
