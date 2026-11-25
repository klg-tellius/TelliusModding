import os
import unittest
from pathlib import Path

from fe_modding.formats import staffroll as sr


class StaffRollTests(unittest.TestCase):
    def test_build_then_read(self):
        roll = sr.StaffRoll("2026/10/13 12:00:00", "Tester", [("", "#F04Movie", ""), ("Producer", "", "A B"), ("", "", "")])
        again = sr.read_staffroll(sr.build_staffroll(roll))
        self.assertEqual(again, roll)

    @unittest.skipUnless(os.environ.get("FE9_EXTRACTED_FILES"), "set FE9_EXTRACTED_FILES")
    def test_retail_files_round_trip(self):
        # The US disc has both; the European one only staffroll_noa.bin, the Japanese one only
        # staffroll.bin (the Staff Credits page opens whichever the disc has).
        found = [path for name in ("staffroll.bin", "staffroll_noa.bin")
                 if (path := Path(os.environ["FE9_EXTRACTED_FILES"]) / "ending" / name).is_file()]
        if not found:
            self.skipTest("this disc has no ending/staffroll*.bin")
        for path in found:
            data = path.read_bytes()
            self.assertEqual(sr.build_staffroll(sr.read_staffroll(data)), data, path.name)
