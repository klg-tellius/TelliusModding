import os
import stat
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fe_modding import config, layout_migration, tools, vanilla_store
from fe_modding.exceptions import ProjectError
from fe_modding.formats import gcdisc
from fe_modding.game_files import OverlayFiles
from fe_modding.games import Game
from fe_modding.project import LAYOUT_EXTRACTED, LAYOUT_OVERLAY, ModProject

BOOT = b"GFEE01\x00\x00" + bytes(0x438)
TREE = {
    "sys/boot.bin": BOOT,
    "sys/bi2.bin": b"bi2",
    "sys/apploader.img": b"apploader",
    "sys/main.dol": b"dol",
    "sys/fst.bin": b"fst",
    "files/FE8Data.bin": b"data",
    "files/Mess/common.m": b"common",
    "files/Mess/c01.m": b"c01",
    "files/Mess/c02.m": b"c02",
}


def write_tree(root: Path, tree=TREE) -> None:
    for rel, data in tree.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)


class LayoutMigrationTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._cleanup)
        self.tmp = Path(self._tmp.name)
        sizes = {rel[len("files/"):]: len(data) for rel, data in TREE.items() if rel.startswith("files/")}
        for patcher in (
                mock.patch.object(config, "load_setting", lambda key, default=None: str(self.tmp / "stores")
                                  if key == vanilla_store.SETTING_KEY else default),
                mock.patch.object(gcdisc, "read_fst_sizes", lambda _data: sizes),
                mock.patch.object(tools, "extract_disc", lambda source, dest, **_: write_tree(Path(dest)))):
            patcher.start()
            self.addCleanup(patcher.stop)
        self.disc = self.tmp / "disc.iso"
        self.disc.write_bytes(b"GFEE01" + bytes(64))
        self.project = ModProject.create(self.tmp, "Old", Game.PATH_OF_RADIANCE)
        self.project.set_source(self.disc)
        write_tree(self.project.extracted_dir)
        self.project.write_keeping_original(self.project.extracted_dir / "files" / "FE8Data.bin", b"edited")
        (self.project.extracted_dir / "files" / "Mess" / "c01.m").write_bytes(b"c0X")  # no copy kept
        (self.project.extracted_dir / "files" / "Mess" / "c99.m").write_bytes(b"added")
        (self.project.extracted_dir / "files" / "Mess" / "c02.m").unlink()
        self.before = {p.relative_to(self.project.extracted_dir).as_posix(): p.read_bytes()
                       for p in self.project.extracted_dir.rglob("*") if p.is_file()}

    def _cleanup(self):
        for path in self.tmp.rglob("*"):
            if path.is_file():
                os.chmod(path, stat.S_IREAD | stat.S_IWRITE)
        self._tmp.cleanup()

    def _reads(self, project):
        files = project.files
        return {rel: files.read(rel) for rel in files.iter_files("")}

    def test_converts_against_the_disc_and_reads_the_same_files(self):
        plan = layout_migration.convert(self.project)
        self.assertEqual(plan.replaced, ["files/FE8Data.bin", "files/Mess/c01.m"])
        self.assertEqual(plan.added, ["files/Mess/c99.m"])
        self.assertEqual(plan.removed, ["files/Mess/c02.m"])
        again = ModProject.load(self.project.directory)
        self.assertEqual(again.layout, LAYOUT_OVERLAY)
        self.assertIsInstance(again.files, OverlayFiles)
        self.assertEqual(self._reads(again), self.before)
        self.assertEqual(sorted(p.relative_to(again.output_dir).as_posix()
                                for p in again.output_dir.rglob("*") if p.is_file()),
                         ["files/FE8Data.bin", "files/Mess/c01.m", "files/Mess/c99.m"])
        self.assertFalse((again.directory / "extracted").exists())
        self.assertTrue(layout_migration.has_backup(again))
        self.assertEqual(again.input_problems(), [])
        layout_migration.delete_backup(again)
        self.assertFalse(layout_migration.has_backup(again))

    def test_without_the_disc_the_vanilla_files_are_rebuilt(self):
        self.disc.unlink()
        with self.assertRaisesRegex(ProjectError, "c02.m"):     # deleted, and no copy was kept
            layout_migration.find_store(self.project)
        (self.project.extracted_dir / "files" / "Mess" / "c02.m").write_bytes(b"c02")
        store, warnings = layout_migration.find_store(self.project)
        self.assertIn("rebuilt", warnings[0])
        plan = layout_migration.plan_migration(self.project, store, warnings)
        # c01.m was changed without a kept original: it is taken as vanilla.
        self.assertEqual(plan.replaced, ["files/FE8Data.bin"])
        self.assertEqual(plan.removed, [])
        self.assertEqual((store.root / "files" / "FE8Data.bin").read_bytes(), b"data")

    def test_a_dump_of_another_disc_is_refused(self):
        dump = self.tmp / "dump"
        write_tree(dump, {**TREE, "sys/boot.bin": b"GFEP01\x00\x00" + bytes(0x438)})
        store, _ = layout_migration.find_store(self.project, folder=dump)
        with self.assertRaisesRegex(ProjectError, "GFEP01"):
            layout_migration.plan_migration(self.project, store)

    def test_a_failed_copy_leaves_layout_1(self):
        store, warnings = layout_migration.find_store(self.project)
        plan = layout_migration.plan_migration(self.project, store, warnings)
        with mock.patch.object(layout_migration, "copy_atomic", side_effect=OSError("disk full")):
            with self.assertRaises(OSError):
                layout_migration.apply_migration(self.project, plan)
        again = ModProject.load(self.project.directory)
        self.assertEqual(again.layout, LAYOUT_EXTRACTED)
        self.assertEqual(self._reads(again), self.before)

    def test_command_line_dry_run_changes_nothing(self):
        with mock.patch("builtins.print"):
            self.assertEqual(layout_migration.main([str(self.project.directory), "--dry-run"]), 0)
        self.assertEqual(ModProject.load(self.project.directory).layout, LAYOUT_EXTRACTED)


if __name__ == "__main__":
    unittest.main()
