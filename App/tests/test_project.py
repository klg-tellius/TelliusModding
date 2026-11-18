import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fe_modding.exceptions import ProjectError
from fe_modding.formats import gcdisc, lz10, pak
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
        self.assertEqual(rd.logical_path("game_data").rel, "files/FE10Data.cms")
        self.assertEqual(por.logical_path("game_data").rel, "files/FE8Data.bin")

    def test_radiant_dawn_files_are_lz10_transparent(self):
        project = ModProject.create(self.parent, "RD", Game.RADIANT_DAWN)
        path = project.logical_path("game_data")
        extracted = project.extracted_dir / "files" / "FE10Data.cms"   # as the disc had it
        extracted.parent.mkdir(parents=True)
        payload = bytes(range(256)) * 8
        extracted.write_bytes(lz10.compress(payload))
        self.assertEqual(project.read_logical("game_data"), payload)

        project.write_logical("game_data", payload + b"edited")
        self.assertEqual(lz10.decompress(path.read_bytes()), payload + b"edited")
        self.assertEqual(project.read_logical("game_data"), payload + b"edited")
        original = project.files.vanilla("files/FE10Data.cms")
        self.assertEqual(lz10.decompress(original), payload, "the extracted file is kept")

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

    def test_hack_maker_code_reads_as_its_retail_build(self):
        # Four Riders ships as GFEE02: a US disc whose maker code was changed
        from fe_modding.games import read_disc_id, retail_disc_id
        from fe_modding.game_code.versions import read_boot_code
        self.assertEqual(retail_disc_id("GFEE02"), "GFEE01")
        self.assertEqual(retail_disc_id("RFEP99"), "RFEP01")
        self.assertEqual(retail_disc_id("SOUE01"), "SOUE01")
        project = ModProject.create(self.parent, "PoR", Game.PATH_OF_RADIANCE)
        boot = project.extracted_dir / "sys" / "boot.bin"
        boot.parent.mkdir(parents=True)
        boot.write_bytes(b"GFEE02\x00\x00" + bytes(0x438))
        self.assertEqual(read_disc_id(project.extracted_dir), "GFEE01")
        self.assertEqual(read_disc_id(project.extracted_dir, raw=True), "GFEE02")
        self.assertEqual(read_boot_code(project.extracted_dir), "GFEE01")
        self.assertIsNone(project.disc_mismatch_warning())

    def test_fst_names_that_are_not_shift_jis(self):
        # Four Riders' fst.bin has "\xef\xbd\x86lowerpot_01.gmap.cmp" (UTF-8 full-width f);
        # WIT extracts it byte for byte as Latin-1, and building must give the same bytes back
        raw = b"\xef\xbd\x86lowerpot_01.gmap.cmp"
        name = gcdisc.decode_fst_name(raw)
        self.assertEqual(name, raw.decode("latin-1"))
        self.assertEqual(gcdisc.encode_fst_name(name), raw)
        self.assertEqual(gcdisc.decode_fst_name(b"bmap01.cmp"), "bmap01.cmp")

    def test_system_archive_copies_win_over_stale_loose_files(self):
        # Paragon edits system.cmp's FE8Data.bin and leaves the loose one as it was
        project = ModProject.create(self.parent, "PoR", Game.PATH_OF_RADIANCE)
        files = project.extracted_dir / "files"
        (files / "mess").mkdir(parents=True)
        (files / "FE8Data.bin").write_bytes(b"vanilla data")
        (files / "mess" / "common.m").write_bytes(b"same text")
        archive = pak.pack_pak([("FE8Data.bin", b"modded data"), ("mess/common.m", b"same text")], [0, 0])
        (files / "system.cmp").write_bytes(lz10.compress(archive))
        self.assertEqual(project.adopt_system_archive(), ["FE8Data.bin"])
        self.assertEqual(project.read_logical("game_data"), b"modded data")
        self.assertEqual(project.adopt_system_archive(), [])
        self.assertEqual(project.sync_system_archive(), [], "building leaves the mod's data as it is")
        # a loose file the project edited is newer than the archive's copy and stays
        project.write_logical("game_data", b"my edit")
        self.assertEqual(project.adopt_system_archive(), [])
        self.assertEqual(project.read_logical("game_data"), b"my edit")

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


    def test_set_source_records_the_path_without_copying(self):
        project = ModProject.create(self.parent, "Mod", Game.PATH_OF_RADIANCE)
        iso = self.parent / "disc.iso"
        iso.write_bytes(b"GFEE01" + bytes(64))
        self.assertEqual(project.set_source(iso), iso.resolve())
        self.assertFalse((project.directory / "source").exists())
        loaded = ModProject.load(project.directory)
        self.assertEqual(loaded.source_path, iso.resolve())
        self.assertEqual(loaded.source_iso, "disc.iso")
        self.assertFalse(loaded.source_missing)

    def test_older_projects_keep_their_copied_disc(self):
        project = ModProject.create(self.parent, "Old", Game.PATH_OF_RADIANCE)
        copy = project.directory / "source" / "disc.iso"
        copy.parent.mkdir()
        copy.write_bytes(b"x")
        project.source_iso = "disc.iso"
        project.save()
        self.assertEqual(ModProject.load(project.directory).source_path, copy)

    def test_extract_reports_a_moved_disc(self):
        project = ModProject.create(self.parent, "Moved", Game.PATH_OF_RADIANCE)
        iso = self.parent / "disc.iso"
        iso.write_bytes(b"x")
        project.set_source(iso)
        iso.unlink()
        self.assertTrue(project.source_missing)
        with self.assertRaisesRegex(ProjectError, "no longer at"):
            project.extract()

if __name__ == "__main__":
    unittest.main()
