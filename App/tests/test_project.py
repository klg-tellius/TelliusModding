import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fe_modding.exceptions import ProjectError
from fe_modding.formats import lz10
from fe_modding.games import Game
from fe_modding.project import PROJECT_SUBDIRS, ModProject, sanitize_folder_name


class SanitizeFolderNameTests(unittest.TestCase):
    def test_strips_invalid_characters(self):
        self.assertEqual(sanitize_folder_name('My: Mod?'), "My Mod")

    def test_rejects_empty_result(self):
        with self.assertRaises(ProjectError):
            sanitize_folder_name('???')


class ModProjectTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.parent = Path(self._tmp.name)

    def test_create_and_load_round_trip(self):
        project = ModProject.create(self.parent, "Test Mod", Game.PATH_OF_RADIANCE, description="hello")

        self.assertEqual(project.directory, self.parent / "Test Mod")
        self.assertTrue(project.project_file.exists())
        for sub in PROJECT_SUBDIRS:
            self.assertTrue((project.directory / sub).is_dir())

        loaded = ModProject.load(project.directory)
        self.assertEqual(loaded.name, "Test Mod")
        self.assertEqual(loaded.game, Game.PATH_OF_RADIANCE)
        self.assertEqual(loaded.description, "hello")

    def test_mod_details_are_saved_and_older_projects_load(self):
        project = ModProject.create(self.parent, "Details", Game.PATH_OF_RADIANCE)
        project.author, project.version, project.credits = "Ana", "0.3", "Maps by Bo"
        project.save()
        loaded = ModProject.load(project.directory)
        self.assertEqual((loaded.author, loaded.version, loaded.credits), ("Ana", "0.3", "Maps by Bo"))
        data = project.to_dict()
        for key in ("author", "version", "credits"):
            del data[key]
        project.project_file.write_text(__import__("json").dumps(data), encoding="utf-8")
        self.assertEqual(ModProject.load(project.directory).author, "")

    def test_create_fails_if_folder_not_empty(self):
        target = self.parent / "Existing"
        target.mkdir()
        (target / "file.txt").write_text("data")

        with self.assertRaises(ProjectError):
            ModProject.create(self.parent, "Existing", Game.RADIANT_DAWN)

    def test_load_fails_without_project_file(self):
        empty_dir = self.parent / "empty"
        empty_dir.mkdir()
        with self.assertRaises(ProjectError):
            ModProject.load(empty_dir)


class LogicalFileTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.parent = Path(self._tmp.name)

    def test_profile_follows_the_game(self):
        rd = ModProject.create(self.parent, "RD", Game.RADIANT_DAWN)
        por = ModProject.create(self.parent, "PoR", Game.PATH_OF_RADIANCE)
        self.assertEqual(rd.profile.disc_id_prefix, "RFE")
        self.assertEqual(rd.logical_path("game_data"), rd.extracted_dir / "files" / "FE10Data.cms")
        self.assertEqual(por.logical_path("game_data"), por.extracted_dir / "files" / "FE8Data.bin")

    def test_radiant_dawn_files_are_lz10_transparent(self):
        project = ModProject.create(self.parent, "RD", Game.RADIANT_DAWN)
        path = project.logical_path("game_data")
        path.parent.mkdir(parents=True)
        payload = bytes(range(256)) * 8
        path.write_bytes(lz10.compress(payload))
        self.assertEqual(project.read_logical("game_data"), payload)

        project.write_logical("game_data", payload + b"edited")
        self.assertEqual(lz10.decompress(path.read_bytes()), payload + b"edited")
        self.assertEqual(project.read_logical("game_data"), payload + b"edited")
        original = project.originals_dir / "files" / "FE10Data.cms"
        self.assertEqual(lz10.decompress(original.read_bytes()), payload, "the extracted file is kept")

    def test_path_of_radiance_files_are_stored_as_they_are(self):
        project = ModProject.create(self.parent, "PoR", Game.PATH_OF_RADIANCE)
        path = project.logical_path("game_data")
        path.parent.mkdir(parents=True)
        path.write_bytes(b"\x10raw")
        self.assertEqual(project.read_logical("game_data"), b"\x10raw")
        project.write_logical("game_data", b"new")
        self.assertEqual(path.read_bytes(), b"new")

    def test_missing_and_damaged_files_are_project_errors(self):
        project = ModProject.create(self.parent, "RD", Game.RADIANT_DAWN)
        with self.assertRaises(ProjectError) as caught:
            project.read_logical("game_data")
        self.assertIn("FE10Data.cms", str(caught.exception))
        path = project.logical_path("game_data")
        path.parent.mkdir(parents=True)
        path.write_bytes(b"not lz10")
        with self.assertRaises(ProjectError):
            project.read_logical("game_data")

    def test_unknown_logical_name_for_the_game(self):
        project = ModProject.create(self.parent, "RD", Game.RADIANT_DAWN)
        with self.assertRaises(KeyError):
            project.logical_path("system_archive")
        self.assertEqual(project.sync_system_archive(), [])

    def test_disc_mismatch_warning(self):
        rd = ModProject.create(self.parent, "RD", Game.RADIANT_DAWN)
        self.assertIsNone(rd.disc_mismatch_warning(), "nothing extracted: nothing to compare")
        boot = rd.extracted_dir / "sys" / "boot.bin"
        boot.parent.mkdir(parents=True)
        boot.write_bytes(b"RFEE01\x00\x01" + bytes(0x438))
        self.assertIsNone(rd.disc_mismatch_warning())
        boot.write_bytes(b"GFEE01\x00\x01" + bytes(0x438))
        warning = rd.disc_mismatch_warning()
        self.assertIn("Path of Radiance", warning)
        self.assertIn("Radiant Dawn", warning)
        boot.write_bytes(b"SOUE01\x00\x01" + bytes(0x438))
        self.assertIn("SOUE01", rd.disc_mismatch_warning())

    def test_source_mismatch_warning_reads_the_image_header(self):
        project = ModProject.create(self.parent, "RD", Game.RADIANT_DAWN)
        iso = self.parent / "wrong.iso"
        iso.write_bytes(b"GFEE01" + bytes(64))
        project.set_source(iso)
        self.assertIn("Path of Radiance disc", project.source_mismatch_warning())
        right = self.parent / "right.wbfs"
        right.write_bytes(bytes(0x200) + b"RFEE01" + bytes(64))
        project.set_source(right)
        self.assertIsNone(project.source_mismatch_warning())


if __name__ == "__main__":
    unittest.main()
