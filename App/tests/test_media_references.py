import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fe_modding import media_references as media


class MediaReferenceTests(unittest.TestCase):
    def test_finds_native_cues_and_movie_paths(self):
        with tempfile.TemporaryDirectory() as tmp:
            dol = Path(tmp) / "main.dol"
            dol.write_bytes(b"xBGM_SELECT1\0BGM_EVT_IKE1\0Movie/Opening.thp\0movie/s01.thp\0")
            self.assertEqual(media.executable_bgm_cues(dol), {"BGM_SELECT1", "BGM_EVT_IKE1"})
            self.assertEqual(media.executable_video_paths(dol), {"movie/opening.thp", "movie/s01.thp"})

    def test_front_end_assets_are_protected(self):
        self.assertTrue(media.front_end_video_reason("OPENING.THP"))
        self.assertFalse(media.front_end_video_reason("s01.thp"))
        self.assertEqual(media.front_end_track_cues({"BGM_EVT_IKE1", "BGM_SELECT2"}), ["BGM_SELECT2"])

    def test_finds_scripts_with_literal_video_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            scripts = Path(tmp)
            (scripts / "C01.cmb").write_bytes(b"xxmovie/S01.thp\0")
            (scripts / "C02.cmb").write_bytes(b"unrelated")
            self.assertEqual(media.script_video_users(scripts, "s01.thp"), ["C01"])

    def test_missing_executable_is_an_empty_audit(self):
        self.assertEqual(media.executable_bgm_cues("missing.dol"), set())
        self.assertEqual(media.executable_video_paths("missing.dol"), set())


if __name__ == "__main__":
    unittest.main()
