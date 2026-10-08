import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fe_modding.games import Game


def _boot(root: Path, disc_id: bytes) -> None:
    (root / "sys").mkdir(parents=True, exist_ok=True)
    (root / "sys" / "boot.bin").write_bytes(disc_id + bytes([0, 1]) + bytes(0x438))


class UnavailableStateTests(unittest.TestCase):
    """Features without a Radiant Dawn codec report it instead of reading the wrong layout."""

    def setUp(self):
        from fe_modding.project import ModProject

        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.project = ModProject.create(Path(self._tmp.name), "RD", Game.RADIANT_DAWN)
        # a disc whose root FE8Data.bin (a leftover Path of Radiance database) must not be mistaken
        # for the game data
        files = self.project.files_dir
        files.mkdir(parents=True, exist_ok=True)
        (files / "FE8Data.bin").write_bytes(bytes(64))

    def test_validator_reports_instead_of_checking(self):
        from fe_modding import validator

        report = validator.validate_project(self.project)
        self.assertEqual([i.severity for i in report.issues], [validator.WARNING])
        self.assertIn("not available for Radiant Dawn yet", report.issues[0].message)

    def test_character_index_is_not_built(self):
        from fe_modding import project_index

        self.assertFalse(project_index.supported(self.project))

    def test_game_data_session_is_unavailable_with_a_reason(self):
        from fe_modding.gui.changelog import ChangeLog
        from fe_modding.gui.fe8_session import Fe8DataSession

        session = Fe8DataSession(self.project, ChangeLog(self.project))
        self.assertFalse(session.available)
        self.assertIn("not available for Radiant Dawn yet", session.unavailable_reason)
        self.assertEqual(session.file_label, "FE10Data.cms")

    def test_play_in_dolphin_refuses_cleanly(self):
        from fe_modding import emulator

        root = self.project.extracted_dir
        _boot(root, b"RFEE01")
        (root / "sys" / "main.dol").write_bytes(b"x")
        with self.assertRaises(emulator.EmulatorError) as caught:
            emulator.prepare_chapter_run(root, Path(self._tmp.name) / "run", 1, 0)
        self.assertIn("not available for Radiant Dawn yet", str(caught.exception))

    def test_chapter_listing_uses_the_radiant_dawn_scheme(self):
        from fe_modding import chapters

        mess = self.project.files_dir / "Mess"
        mess.mkdir(parents=True)
        for name in ("c0102", "c0101", "c0407a", "cfinal", "common", "e_c0101", "c0000"):
            (mess / f"{name}.m").write_bytes(b"")
        self.assertEqual(chapters.list_chapter_ids(self.project), ["0000", "0101", "0102", "0407a", "final"])


if __name__ == "__main__":
    unittest.main()
