"""Scoped workbook round trips for asset pages."""
import tempfile
import unittest
from pathlib import Path

from fe_modding import excel_io, flag_excel
from fe_modding.formats import event_flags, fe8data
from test_fe8data_tables import _Builder, build


def terrain_data():
    builder = _Builder()
    builder.symbol("TerrainData")
    builder.word(77)
    block = len(builder.data) + 77 * 12
    for _ in range(77):
        builder.ref("plain")
        builder.ref("MT_plain")
        builder.pointers.append(len(builder.data))
        builder.word(block)
    builder.data += bytes([0] * 8 + [1] * 15 + [1])
    return builder.finish()


class AssetExcelTests(unittest.TestCase):
    def test_character_and_item_exports_are_separate(self):
        data = build()
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "assets.xlsx"
            for sheet in ("Characters", "Items"):
                excel_io.export_fe8(path, data, only=sheet)
                self.assertEqual(list(excel_io.read_workbook(path)), [sheet])
                unchanged, _, errors = excel_io.import_fe8(path, data, only=sheet)
                self.assertEqual(errors, [])
                self.assertEqual(unchanged, data)
            _, _, errors = excel_io.import_fe8(path, data, only="Characters")
            self.assertIn("Characters", errors[0])

    def test_terrain_export_and_import_isolate_shared_stats(self):
        data = terrain_data()
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "terrain.xlsx"
            excel_io.export_fe8(path, data, only="Terrain")
            sheets = excel_io.read_workbook(path)
            self.assertEqual(list(sheets), ["Terrain"])
            self.assertEqual(len(sheets["Terrain"]), 78)
            avoid = sheets["Terrain"][0].index("avoid")
            sheets["Terrain"][1][avoid] = 5
            excel_io.write_workbook(path, sheets)
            changed, _, errors = excel_io.import_fe8(path, data, only="Terrain")
            self.assertEqual(errors, [])
            records = fe8data.read_terrain_types(changed)
            self.assertEqual(records[0].avoid, 5)
            self.assertEqual(records[1].avoid, 0)
            self.assertEqual(fe8data.read_terrain_types(data)[0].avoid, 0)

    def test_wrong_sheet_and_invalid_terrain_do_not_apply(self):
        data = terrain_data()
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "wrong.xlsx"
            excel_io.write_workbook(path, {"Items": [["index", "iid"]]})
            unchanged, _, errors = excel_io.import_fe8(path, data, only="Terrain")
            self.assertEqual(unchanged, data)
            self.assertIn("Terrain", errors[0])
            excel_io.write_workbook(path, {"Terrain": [["index", "avoid"], [0, 200]]})
            unchanged, _, errors = excel_io.import_fe8(path, data, only="Terrain")
            self.assertEqual(unchanged, data)
            self.assertIn("avoid", errors[0])


class FlagExcelTests(unittest.TestCase):
    def test_round_trip_and_append_only_validation(self):
        campaign = ["gf_complete", "G_one"]
        chapters = {"C00": ["door"], "C01": []}
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "flags.xlsx"
            flag_excel.export_flags(path, campaign, chapters)
            sheets = excel_io.read_workbook(path)
            self.assertEqual(set(sheets), {"Campaign Flags", "Chapter Flags"})
            additions, errors = flag_excel.plan_flag_import(
                path, campaign, chapters, 96, event_flags.check_flag_name)
            self.assertEqual(errors, [])
            self.assertEqual(additions, {"campaign": [], "C00": [], "C01": []})
            sheets["Campaign Flags"].append([2, "G_two"])
            sheets["Chapter Flags"].append(["C00", 1, "chest"])
            excel_io.write_workbook(path, sheets)
            additions, errors = flag_excel.plan_flag_import(
                path, campaign, chapters, 96, event_flags.check_flag_name)
            self.assertEqual(errors, [])
            self.assertEqual(additions["campaign"], ["G_two"])
            self.assertEqual(additions["C00"], ["chest"])
            sheets["Campaign Flags"][1][1] = "changed"
            excel_io.write_workbook(path, sheets)
            _, errors = flag_excel.plan_flag_import(
                path, campaign, chapters, 96, event_flags.check_flag_name)
            self.assertTrue(any("existing slots" in error for error in errors))


if __name__ == "__main__":
    unittest.main()
