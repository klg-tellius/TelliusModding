import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fe_modding.exceptions import ProjectError
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


if __name__ == "__main__":
    unittest.main()
