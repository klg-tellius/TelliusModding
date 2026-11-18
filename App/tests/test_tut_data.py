import os
import unittest
from pathlib import Path

from fe_modding.formats import tut_data as td


class TutDataTests(unittest.TestCase):
    def test_build_then_read(self):
        tut = td.TutData("2026/10/13 12:00:00", "Tester", 0, ["MT_CN", "MT_C00"], ["MT_CAT0"], ["MT_INI0"], [
            td.TutorialEntry(1, 1, 1, 0, 1, [2, 3, 3, 2], "MT_C01_sX", "Scripts/C80.cmb", "tut_01_X"),
            td.TutorialEntry(2, 1, 1, -1, 1, [0, 3, 3, 0], "MT_C01_sY", "Scripts/C80.cmb", "tut_01_Y"),
        ])
        self.assertEqual(td.read_tut_data(td.build_tut_data(tut)), tut)

    def test_japanese_disc_rows_have_three_start_flags(self):
        # GFEJ01 has no Easy mode: 20-byte rows, three start flags, no padding
        tut = td.TutData("2005/03/01 12:00:00", "Tester", 0, ["MT_CN"], ["MT_CAT0"], ["MT_INI0"], [
            td.TutorialEntry(1, 0, 0, 11, 2, [2, 3, 3], "MT_C00_sX", "Scripts/C80.cmb", "tut_00_X"),
            td.TutorialEntry(2, 0, 0, 12, 2, [0, 3, 3], "MT_C00_sY", "Scripts/C80.cmb", "tut_00_Y"),
        ])
        data = td.build_tut_data(tut)
        self.assertEqual(len(data), len(td.build_tut_data(td.TutData(
            tut.build_time, tut.author, 0, tut.chapters, tut.categories, tut.initials,
            [td.TutorialEntry(e.id, e.category, e.chapter, e.order, e.initial, e.start_flags + [0], e.title_key,
                              e.script, e.function) for e in tut.entries]))) - 2 * 4)
        self.assertEqual(td.read_tut_data(data), tut)
        mixed = td.TutData(tut.build_time, tut.author, 0, [], [], [], [tut.entries[0], td.TutorialEntry(
            3, 0, 0, 0, 0, [0, 0, 0, 0], "MT_C00_sZ", "Scripts/C80.cmb", "tut_00_Z")])
        with self.assertRaises(td.TutDataError):
            td.build_tut_data(mixed)

    @unittest.skipUnless(os.environ.get("FE9_EXTRACTED_FILES"), "set FE9_EXTRACTED_FILES")
    def test_retail_files_round_trip(self):
        # US: tut_data.bin and tut_data_en.bin; Europe: one per language; Japan: tut_data.bin (20-byte rows)
        paths = sorted(Path(os.environ["FE9_EXTRACTED_FILES"]).glob("tut_data*.bin"))
        self.assertTrue(paths)
        for path in paths:
            data = path.read_bytes()
            self.assertEqual(td.build_tut_data(td.read_tut_data(data)), data, path.name)
