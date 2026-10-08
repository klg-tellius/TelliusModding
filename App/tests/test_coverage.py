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


class Fe10ContainerTest(unittest.TestCase):
    def test_decompressed_cms_container_is_walked(self):
        import struct

        data_size = 0x10
        body = struct.pack(">I", 4) + b"ABC" + bytes([0]) + bytes(8)  # a pointer to the string "ABC"
        relocations = struct.pack(">I", 0)
        symbols = struct.pack(">II", 0, 0) + b"Sym" + bytes([0])
        size = 0x20 + data_size + len(relocations) + len(symbols)
        blob = struct.pack(">4I", size, data_size, 1, 1) + bytes(16) + body + relocations + symbols
        report = Report()
        Walker(report).child("FE10Test.cms#", blob)
        totals = report.formats["fe10 container"]
        self.assertEqual(totals.failures, [])
        self.assertEqual(totals.counts[UNCLASSIFIED], 0)
        # the 16 body bytes: the pointer word (4) and the string (4) are decoded, the rest is records
        self.assertEqual(totals.counts[UNDECODED], 8)
        self.assertEqual(totals.fields[(UNDECODED, "Sym records")][0], 8)

    def test_other_cms_names_are_not_taken_for_containers(self):
        report = Report()
        Walker(report).child("Fonts/system.cms", bytes(64))
        self.assertNotIn("fe10 container", report.formats)


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
