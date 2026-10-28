"""Scoped workbook round trips for asset pages."""
import tempfile
import struct
import unittest
from pathlib import Path

from fe_modding import excel_io, flag_excel
from fe_modding.formats import event_flags, fe8data, fe10growth
from dispo_fixture import build_minimal_dispo_bytes
from fe_modding.formats import dispo
from test_fe8data_tables import _Builder, build
from test_fe10data import _container


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


def growth_data():
    """Two FE10Growth records sharing the same two physical stat lines."""
    records_end = 28
    pid_a, pid_b, lines = records_end, records_end + 8, records_end + 16
    body = bytearray(struct.pack(">H2x", 2))
    body += struct.pack(">IBB2xI", pid_a, 1, 2, lines)
    body += struct.pack(">IBB2xI", pid_b, 1, 2, lines)
    body += b"PID_A\0\0\0PID_B\0\0\0"
    body += bytes(range(10, 18)) + bytes(range(20, 28))
    return _container(bytes(body), [4, 12, 16, 24], [(fe10growth.SYMBOL, 0)])


class AssetExcelTests(unittest.TestCase):
    def test_deployment_export_uses_named_flag_columns(self):
        doc = dispo.parse_dispo(build_minimal_dispo_bytes())
        unit = doc.sections[1].units[0]
        unit[dispo.FIELD["flags"]] = dispo.FLAG_AUTOLEVEL | dispo.FLAG_BRIDGE_BARRIER
        unit[dispo.FIELD["item4_flag"]] = dispo.ITEM_FLAG_RING
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "units.xlsx"
            excel_io.export_fe8(path, b"", {"dispos_n.bin": doc})
            rows = excel_io.read_workbook(path)["Dispo n"]
            header = rows[0]
            self.assertNotIn("flags", header)
            self.assertNotIn("field2", header)
            row = next(r for r in rows[1:] if r[1] == 0 and r[0] == doc.sections[1].name)
            self.assertEqual(row[header.index("autolevel")], "yes")
            self.assertEqual(row[header.index("no_bridge_cover")], "yes")
            self.assertEqual(row[header.index("item1_ignore_first_playthrough")], "yes")
            row[header.index("hold_position")] = "yes"
            row[header.index("autolevel")] = None
            excel_io.write_workbook(path, {"Dispo n": rows})
            _data, docs, errors = excel_io.import_fe8(path, b"", {"dispos_n.bin": doc})
            self.assertEqual(errors, [])
            edited = docs["dispos_n.bin"].sections[1].units[0]
            self.assertEqual(edited[dispo.FIELD["flags"]], dispo.FLAG_HOLD_POSITION | dispo.FLAG_BRIDGE_BARRIER)
            self.assertEqual(edited[dispo.FIELD["item0"]], 0)
            self.assertEqual(edited[dispo.FIELD["pid"]], "PID_TEST")

    def test_rd_deployment_excel_edits_growth_table_flag_and_preserves_unknown_bits(self):
        doc = dispo.parse_dispo(build_minimal_dispo_bytes())
        doc.dialect = "fe10"
        for section in doc.sections:
            section.units = [dispo.DispoUnitValues(unit, raw=bytes(dispo.FE10_RECORD_SIZE))
                             for unit in section.units]
        unit = doc.sections[1].units[0]
        unit[dispo.FE10_GROWTH_FLAGS_FIELD] = dispo.FE10_GROWTH_TABLE | 0x0002

        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "rd_units.xlsx"
            excel_io.export_fe8(path, b"", {"dispos_n.bin": doc})
            sheets = excel_io.read_workbook(path)
            rows = sheets["Dispo n"]
            header = rows[0]
            self.assertIn("use_fe10growth_stats", header)
            self.assertNotIn("field2", header)
            row = next(r for r in rows[1:] if r[1] == 0 and r[0] == doc.sections[1].name)
            growth = header.index("use_fe10growth_stats")
            self.assertEqual(row[growth], "yes")
            row[growth] = None
            excel_io.write_workbook(path, sheets)

            _data, docs, errors = excel_io.import_fe8(path, b"", {"dispos_n.bin": doc})
            self.assertEqual(errors, [])
            edited = docs["dispos_n.bin"].sections[1].units[0]
            self.assertEqual(edited[dispo.FE10_GROWTH_FLAGS_FIELD], 0x0002)

    def test_rd_legacy_raw_growth_flag_column_is_numeric(self):
        doc = dispo.parse_dispo(build_minimal_dispo_bytes())
        doc.dialect = "fe10"
        for section in doc.sections:
            section.units = [dispo.DispoUnitValues(unit, raw=bytes(dispo.FE10_RECORD_SIZE))
                             for unit in section.units]
        section = doc.sections[1]
        rows = [["section", "unit_index", "linked_label", "field2"],
                [section.name, 0, "", 0x0400]]

        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "rd_legacy_units.xlsx"
            excel_io.write_workbook(path, {"Dispo n": rows})
            _data, docs, errors = excel_io.import_fe8(path, b"", {"dispos_n.bin": doc})

        self.assertEqual(errors, [])
        self.assertEqual(docs["dispos_n.bin"].sections[1].units[0][
            dispo.FE10_GROWTH_FLAGS_FIELD], 0x0400)

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


class Fe10GrowthExcelTests(unittest.TestCase):
    def test_export_and_import_changes_shared_line_once(self):
        data = growth_data()
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "growth.xlsx"
            excel_io.export_fe10_growth(path, data)
            sheets = excel_io.read_workbook(path)
            rows = sheets[excel_io.FE10_GROWTH_SHEET]
            header = rows[0]
            self.assertEqual(header[:3], ["index", "pid", "level"])
            self.assertEqual(header[3:], list(fe10growth.STAT_NAMES))
            first = next(row for row in rows[1:] if row[0:3] == [0, "PID_A", 1])
            alias = next(row for row in rows[1:] if row[0:3] == [1, "PID_B", 1])
            self.assertEqual(first[3:], alias[3:])
            first[header.index("HP")] = 99
            excel_io.write_workbook(path, sheets)

            changed, errors, count = excel_io.import_fe10_growth(path, data)

        self.assertEqual(errors, [])
        self.assertEqual(count, 1)
        records = fe10growth.read_growth(changed)
        self.assertEqual(records[0].lines[0][0], 99)
        self.assertEqual(records[1].lines[0][0], 99)
        self.assertEqual(changed[:records[0].lines_at], data[:records[0].lines_at])

    def test_conflicting_shared_edits_are_atomic(self):
        data = growth_data()
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "growth.xlsx"
            excel_io.export_fe10_growth(path, data)
            sheets = excel_io.read_workbook(path)
            rows = sheets[excel_io.FE10_GROWTH_SHEET]
            hp = rows[0].index("HP")
            next(row for row in rows[1:] if row[0:3] == [0, "PID_A", 1])[hp] = 98
            next(row for row in rows[1:] if row[0:3] == [1, "PID_B", 1])[hp] = 99
            excel_io.write_workbook(path, sheets)
            unchanged, errors, count = excel_io.import_fe10_growth(path, data)

        self.assertEqual(unchanged, data)
        self.assertEqual(count, 0)
        self.assertIn("conflicting edits", errors[0])

    def test_identity_and_stat_ranges_are_validated_atomically(self):
        data = growth_data()
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "growth.xlsx"
            excel_io.export_fe10_growth(path, data)
            sheets = excel_io.read_workbook(path)
            rows = sheets[excel_io.FE10_GROWTH_SHEET]
            rows[1][rows[0].index("pid")] = "PID_WRONG"
            rows[2][rows[0].index("Spd")] = 256
            excel_io.write_workbook(path, sheets)
            unchanged, errors, count = excel_io.import_fe10_growth(path, data)

        self.assertEqual((unchanged, count), (data, 0))
        self.assertEqual(len(errors), 2)
        self.assertIn("not PID_WRONG", errors[0])
        self.assertIn("between 0 and 255", errors[1])


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
