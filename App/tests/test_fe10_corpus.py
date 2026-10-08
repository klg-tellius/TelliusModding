"""Corpus tests against an extracted Radiant Dawn disc (skipped unless the variables are set).

``FE10_EXTRACTED_FILES`` is the ``files/`` folder of an extracted RFEE01 disc and ``FE10_EXTRACTED``
its root (the folder holding ``sys/`` and ``files/``); either alone enables the tests that need
only it. They mirror ``FE9_EXTRACTED_FILES`` / ``FE9_EXTRACTED`` for Path of Radiance.
Each decoder added for Radiant Dawn adds its byte-identical round trip here.
"""

import os
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fe_modding import games
from fe_modding.formats import fe8data, lz10, message
from fe_modding.game_profile import RADIANT_DAWN_PROFILE
from fe_modding.games import Game


def _files() -> Path | None:
    value = os.environ.get("FE10_EXTRACTED_FILES")
    if value:
        return Path(value)
    root = os.environ.get("FE10_EXTRACTED")
    return Path(root) / "files" if root else None


FILES = _files()
ROOT = Path(os.environ["FE10_EXTRACTED"]) if os.environ.get("FE10_EXTRACTED") else (FILES.parent if FILES else None)

#: The data containers: LZ10 files that share the FE8Data container header.
DATA_FILES = ("FE10Data.cms", "FE10Growth.cms", "FE10Anim.cms", "FE10Battle.cms", "FE10Effect.cms",
              "FE10Conversation.cms", "Cp/cp_data.cms")


@unittest.skipUnless(FILES, "set FE10_EXTRACTED_FILES to the files/ folder of an extracted Radiant Dawn disc")
class Fe10FilesTest(unittest.TestCase):
    def test_every_profile_file_is_on_the_disc(self):
        for name in RADIANT_DAWN_PROFILE.files:
            path = RADIANT_DAWN_PROFILE.path(FILES, name)
            with self.subTest(name=name):
                self.assertTrue(path.is_file(), path)

    def test_data_files_decompress_and_recompress_byte_identically(self):
        for rel in DATA_FILES:
            raw = (FILES / rel).read_bytes()
            inner = lz10.decompress(raw)
            with self.subTest(rel=rel):
                self.assertEqual(lz10.compress(inner), raw)

    def test_data_files_use_the_fe8data_container(self):
        for rel in DATA_FILES:
            inner = lz10.decompress((FILES / rel).read_bytes())
            with self.subTest(rel=rel):
                file_size = int.from_bytes(inner[0:4], "big")
                self.assertEqual(file_size, len(inner))
        symbols = fe8data.symbol_offsets(lz10.decompress((FILES / "FE10Data.cms").read_bytes()))
        self.assertIn("ChapterData", symbols)
        self.assertGreater(len(symbols), 100)

    def test_coverage_walker_places_every_byte_of_the_containers(self):
        from fe_modding.formats.coverage import UNCLASSIFIED, Report, Walker

        report = Report()
        walker = Walker(report)
        for rel in DATA_FILES:
            walker.child(rel, (FILES / rel).read_bytes())
        totals = report.formats["fe10 container"]
        self.assertEqual(totals.files, len(DATA_FILES))
        self.assertEqual(totals.failures, [])
        self.assertEqual(totals.counts[UNCLASSIFIED], 0)

    def test_every_mess_file_parses(self):
        paths = sorted((FILES / "Mess").glob("*.m"))
        self.assertGreater(len(paths), 200)
        for path in paths:
            with self.subTest(path=path.name):
                self.assertTrue(message.read_messages_path(path) is not None)

    def test_chapters_use_part_and_chapter_ids(self):
        from types import SimpleNamespace

        from fe_modding import chapters

        project = SimpleNamespace(extracted_dir=FILES.parent, game=Game.RADIANT_DAWN)
        ids = chapters.list_chapter_ids(project)
        self.assertIn("0101", ids)
        self.assertIn("0407a", ids)
        self.assertEqual(ids, sorted(ids, key=RADIANT_DAWN_PROFILE.chapter_sort_key))
        paths = chapters.chapter_paths(project, "0101")
        for found in (paths.dialogue, paths.script, paths.deployment, paths.map):
            self.assertIsNotNone(found)

    def test_wii_fonts_and_maps_are_where_the_profile_says(self):
        self.assertTrue((FILES / "zmap" / "bmap0101" / "map.cmp").is_file())
        for diff in RADIANT_DAWN_PROFILE.deployment_difficulties:
            self.assertTrue(RADIANT_DAWN_PROFILE.deployment_path(FILES, "bmap0101", diff).is_file(), diff)
        for diff in RADIANT_DAWN_PROFILE.shop_difficulties:
            self.assertTrue(RADIANT_DAWN_PROFILE.shop_path(FILES, diff).is_file(), diff)


@unittest.skipUnless(ROOT and (ROOT / "sys" / "boot.bin").is_file(),
                     "set FE10_EXTRACTED to an extracted Radiant Dawn disc (the folder with sys/ and files/)")
class Fe10DiscTest(unittest.TestCase):
    def test_wii_layout_and_detection(self):
        for name in ("sys/boot.bin", "sys/main.dol", "sys/fst.bin", "disc", "ticket.bin", "tmd.bin", "cert.bin"):
            self.assertTrue((ROOT / name).exists(), name)
        self.assertTrue(games.read_disc_id(ROOT).startswith("RFE"))
        self.assertIs(games.detect_from_extracted(ROOT), Game.RADIANT_DAWN)

    def test_disc_mismatch_warning_on_a_real_boot_bin(self):
        import shutil
        import tempfile

        from fe_modding.project import ModProject

        with tempfile.TemporaryDirectory() as tmp:
            for game, warns in ((Game.RADIANT_DAWN, False), (Game.PATH_OF_RADIANCE, True)):
                project = ModProject.create(Path(tmp), game.value, game)
                (project.extracted_dir / "sys").mkdir()
                shutil.copy2(ROOT / "sys" / "boot.bin", project.extracted_dir / "sys" / "boot.bin")
                with self.subTest(game=game):
                    self.assertEqual(project.disc_mismatch_warning() is not None, warns)


if __name__ == "__main__":
    unittest.main()
