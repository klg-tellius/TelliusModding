import os
import unittest
from pathlib import Path

from fe_modding.formats import coverage as c
from fe_modding.formats import por_captions as pc


def _movies():
    return [
        pc.MovieCaptions("movie/s01.thp", [pc.Caption("MMC_SCENE01_01", 14667, 17500),
                                           pc.Caption("MMC_SCENE01_02", 29500, 30667)]),
        pc.MovieCaptions("movie/s08.thp", [pc.Caption("MMC_SCENE08_17", 112333, 136667, 1)]),
    ]


class PorCaptionsTests(unittest.TestCase):
    def test_build_then_read(self):
        data = pc.build_captions(_movies())
        self.assertEqual(pc.read_captions(data), _movies())
        self.assertEqual(pc.build_captions(pc.read_captions(data)), data)

    def test_layout(self):
        data = pc.build_captions(_movies())
        body = data[0x20:]
        self.assertEqual(body[:4], (2).to_bytes(4, "big"))
        first_list = int.from_bytes(body[8:12], "big")
        # two 16-byte rows, then the zero that ends the list, then the next movie's list
        self.assertEqual(int.from_bytes(body[16:20], "big"), first_list + 2 * 16 + 4)
        self.assertEqual(int.from_bytes(body[first_list + 4:first_list + 8], "big"), 14667)

    def test_rejects_an_end_before_the_start(self):
        with self.assertRaises(pc.CaptionError):
            pc.build_captions([pc.MovieCaptions("movie/s01.thp", [pc.Caption("MMC_X", 10, 5)])])

    def test_coverage_decodes_every_byte(self):
        report = c.Report()
        c.Walker(report).child("MovieCaptionData.bin", pc.build_captions(_movies()))
        counts = report.formats["MovieCaptionData.bin"].counts
        self.assertEqual(counts[c.UNDECODED] + counts[c.UNCLASSIFIED], 0)

    @unittest.skipUnless(os.environ.get("FE9_EXTRACTED_FILES"), "set FE9_EXTRACTED_FILES")
    def test_retail_file_round_trips(self):
        path = Path(os.environ["FE9_EXTRACTED_FILES"]) / pc.FILE_NAME
        if not path.is_file():
            self.skipTest("only the European disc (GFEP01) has movie subtitles")
        data = path.read_bytes()
        movies = pc.read_captions(data)
        self.assertEqual(pc.build_captions(movies), data)
        self.assertEqual([m.movie for m in movies], ["movie/s01.thp", "movie/s02.thp", "movie/s05.thp", "movie/s08.thp"])
