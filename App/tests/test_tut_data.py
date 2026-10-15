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

    @unittest.skipUnless(os.environ.get("FE9_EXTRACTED_FILES"), "set FE9_EXTRACTED_FILES")
    def test_retail_files_round_trip(self):
        for name in ("tut_data.bin", "tut_data_en.bin"):
            data = (Path(os.environ["FE9_EXTRACTED_FILES"]) / name).read_bytes()
            self.assertEqual(td.build_tut_data(td.read_tut_data(data)), data, name)
