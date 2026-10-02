import os
import unittest
from pathlib import Path

from fe_modding.formats import coverage as cov_module
from fe_modding.formats.coverage import (DECODED, PADDING, PLAUSIBLE, UNCLASSIFIED, UNDECODED, UNREAD, FileCoverage,
                                         Report, Walker)


class FileCoverageTest(unittest.TestCase):
    def test_bits_judge_the_set_bits(self):
        cov = FileCoverage(bytes([0x03, 0x10, 0x30]), "t", "t")
        cov.bits(0, 1, known=0x03)
        cov.bits(1, 1, known=0x03, plausible=0x10)
        cov.bits(2, 1, known=0x03, plausible=0x10)
        self.assertEqual(list(cov.status), [DECODED, PLAUSIBLE, UNDECODED])

    def test_zero_is_padding_only_when_zero(self):
        cov = FileCoverage(bytes([0, 0, 5, 0]), "t", "t")
        cov.zero(0, 2, "a")
        cov.zero(2, 2, "b", nonzero=UNREAD)
        self.assertEqual(list(cov.status), [PADDING, PADDING, UNREAD, UNREAD])

    def test_fill_only_touches_unplaced_bytes(self):
        cov = FileCoverage(bytes([1, 0, 2, 0]), "t", "t")
        cov.mark(0, 1, DECODED)
        cov.fill(PADDING, only_zero=True)
        self.assertEqual(list(cov.status), [DECODED, PADDING, UNCLASSIFIED, PADDING])
        self.assertEqual(cov.open_fields()[(UNCLASSIFIED, "(unplaced bytes)")], 1)

    def test_unknown_file_is_reported_unclassified(self):
        report = Report()
        Walker(report).child("x/strange.qqq", b"abcd")
        totals = report.formats["unknown .qqq"]
        self.assertEqual(totals.counts[UNCLASSIFIED], 4)


FILES = os.environ.get("FE9_EXTRACTED_FILES")
#: Small real files, one per handler family that has no other test here.
SAMPLES = ("FE8Data.bin", "FE8Anim.bin", "FE8Effect.bin", "cp_data.bin", "s/rect.bin", "window/RectDesc.bin",
           "tut_data_en.bin", "client.bin", "etc/curb.g", "etc/curb.gs", "etc/curb.ga", "etc/cursor.tpl",
           "zmap/bmap01/map.cmp", "zmap/bmap01/dispos.cmp", "Scripts/C01.cmb", "Sound/gcfesnd.bin",
           "Sound/gcfesnd.sdir", "Sound/gcfesnd.pool", "zbg/map10_house/bf.cmp")


@unittest.skipUnless(FILES, "set FE9_EXTRACTED_FILES to an extracted files/ directory")
class RealFilesTest(unittest.TestCase):
    def test_handlers_place_every_byte(self):
        report = Report()
        walker = Walker(report)
        for rel in SAMPLES:
            walker.child(rel, (Path(FILES) / rel).read_bytes())
        for fmt, totals in report.formats.items():
            self.assertFalse(fmt.startswith("unknown"), fmt)
            self.assertEqual(totals.failures, [], fmt)
            self.assertEqual(totals.counts[UNCLASSIFIED], 0, f"{fmt}: {totals.fields}")
        self.assertGreater(report.formats["map.bin"].files, 1)  # chapter and battle-scenery map.bin
        summary = cov_module.format_summary(report)
        self.assertIn("TOTAL (leaf)", summary)


if __name__ == "__main__":
    unittest.main()
