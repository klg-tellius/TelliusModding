"""The project check: dangling references and missing chapter files, on the small synthetic
FE8Data.bin of test_fe8data_tables and on tiny extracted trees."""

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fe_modding import validator
from fe_modding.formats import fe8data
from fe_modding.games import Game
from fe_modding.project import ModProject
from test_fe8data_tables import build


def _messages(issues, area=None):
    return [i.message for i in issues if area is None or i.area == area]


class Fe8DataChecks(unittest.TestCase):
    def test_clean_records_raise_only_the_fixture_support_error(self):
        issues = validator.validate_fe8data(build())
        # the fixture lists MIST as IKE's partner without the reverse list
        self.assertEqual([i.area for i in issues if i.severity == validator.ERROR], ["Supports"])
        for area in ("Characters", "Classes", "Items", "Skills", "Chapters"):
            self.assertEqual(_messages(issues, area), [], area)

    def test_character_with_missing_class_or_skill(self):
        data = fe8data.add_label(build(), "JID_NOPE")
        data = fe8data.patch_character_field(data, 0, "jid", "JID_NOPE")
        messages = _messages(validator.validate_fe8data(data), "Characters")
        self.assertEqual(messages, ["PID_IKE has class JID_NOPE, which does not exist."])

    def test_removed_class_leaves_dangling_references(self):
        data = fe8data.remove_record(build(), "class", 1)  # JID_CLERIC: Mist's class, Ranger's promotion
        messages = _messages(validator.validate_fe8data(data))
        self.assertIn("PID_MIST has class JID_CLERIC, which does not exist.", messages)
        self.assertIn("JID_RANGER promotes to JID_CLERIC, which does not exist.", messages)

    def test_duplicate_ids(self):
        data, _ = fe8data.add_record(build(), "character", "PID_IKF", copy_from=0)
        data = data.replace(b"PID_IKF\x00", b"PID_IKE\x00")  # a second string, same ID
        self.assertIn("PID PID_IKE is used by more than one record; the game finds only one.",
                      _messages(validator.validate_fe8data(data), "Characters"))

    def test_support_partner_must_exist(self):
        data = fe8data.remove_record(build(), "character", 1)  # PID_MIST
        messages = _messages(validator.validate_fe8data(data), "Supports")
        self.assertIn("PID_IKE has support partner PID_MIST, which does not exist.", messages)

    def test_unreadable_file_is_a_warning_not_an_exception(self):
        issues = validator.validate_fe8data(b"not a container")
        self.assertEqual([i.severity for i in issues], [validator.WARNING])


class ProjectChecks(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.project = ModProject.create(Path(self._tmp.name), "T", Game.PATH_OF_RADIANCE)
        self.files = self.project.extracted_dir / "files"
        self.files.mkdir(parents=True, exist_ok=True)

    def write(self, relative: str, data: bytes) -> None:
        path = self.files / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)

    def test_needs_an_extracted_project(self):
        report = validator.validate_project(self.project)
        self.assertFalse(report.ok)
        self.assertIn("extract", report.errors[0].message)

    def test_missing_chapter_files_are_errors(self):
        self.write("FE8Data.bin", build())
        report = validator.validate_project(self.project)
        paths = {i.where for i in report.errors if i.area == "Chapter 01"}
        self.assertEqual(paths, {"Scripts/C01.cmb", "zmap/bmap01/map.cmp", "zmap/bmap01/dispos.cmp"})

    def test_present_chapter_files_clear_the_errors(self):
        self.write("FE8Data.bin", build())
        for cid in ("00", "01"):
            self.write(f"Scripts/C{cid}.cmb", b"")
            self.write(f"zmap/bmap{cid}/map.cmp", b"")
            self.write(f"zmap/bmap{cid}/dispos.cmp", b"")
        report = validator.validate_project(self.project)
        self.assertEqual([i for i in report.issues if i.area.startswith("Chapter ") and i.severity == validator.ERROR], [])

    def test_script_naming_a_missing_record_is_a_warning(self):
        self.write("FE8Data.bin", build())
        self.write("Scripts/C01.cmb", b"\x00PID_IKE\x00PID_GHOST\x00XPID_OTHER\x00")
        warnings = [i for i in validator.validate_project(self.project).warnings if i.where == "Scripts/C01.cmb"]
        self.assertEqual([i.message for i in warnings], ["The script names PID_GHOST, which does not exist."])
        self.assertEqual(warnings[0].route, ("chapter", "01", "script"))

    def test_unreachable_story_chapter_needs_the_flow(self):
        class Flow:
            available = True
            def next_of(self, chapter):
                return chapter + 1 if chapter < 1 else 32
        data, _ = fe8data.add_record(build(), "chapter", None, copy_from=1)  # id 33
        self.write("FE8Data.bin", data)
        warnings = [i for i in validator.validate_project(self.project, Flow()).warnings if i.area == "Chapter 33"]
        self.assertTrue(any("story flow" in i.message for i in warnings))
        self.assertFalse(any("story flow" in i.message for i in validator.validate_project(self.project).warnings))


if __name__ == "__main__":
    unittest.main()
