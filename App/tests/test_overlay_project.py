"""A project in the input/output layout, end to end: extract into the shared store, edit, build,
patch and reopen, with the vanilla files never changing."""

import json
import os
import stat
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fe_modding import config, patch, project as project_module, tools, vanilla_store
from fe_modding.exceptions import ProjectError
from fe_modding.formats import gcdisc
from fe_modding.game_files import OverlayFiles
from fe_modding.games import Game
from fe_modding.project import LAYOUT_OVERLAY, ModProject

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
}


def write_tree(root: Path) -> None:
    for rel, data in TREE.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)


class OverlayProjectTests(unittest.TestCase):
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
        self.disc = self.tmp / "Path of Radiance.iso"
        self.disc.write_bytes(b"GFEE01" + bytes(64))
        self.project = ModProject.create(self.tmp, "Mod", Game.PATH_OF_RADIANCE, layout=LAYOUT_OVERLAY)
        self.project.set_source(self.disc)
        self.project.extract()

    def _cleanup(self):
        for path in self.tmp.rglob("*"):
            if path.is_file():
                os.chmod(path, stat.S_IREAD | stat.S_IWRITE)
        self._tmp.cleanup()

    def _store_files(self) -> dict:
        root = self.project.input_root
        return {p.relative_to(root).as_posix(): p.read_bytes() for p in root.rglob("*") if p.is_file()}

    def test_extract_fills_the_shared_store_once(self):
        project = self.project
        self.assertIsInstance(project.files, OverlayFiles)
        self.assertTrue(project.has_extracted_files)
        self.assertFalse((project.directory / "extracted").exists())
        self.assertEqual(self._store_files(), TREE)
        other = ModProject.create(self.tmp, "Other", Game.PATH_OF_RADIANCE, layout=LAYOUT_OVERLAY)
        other.set_source(self.disc)
        other.extract()
        self.assertEqual(other.input_root, project.input_root)
        self.assertEqual(len(vanilla_store.list_stores()), 1)

    def test_edits_go_to_the_output_and_survive_reopening(self):
        self.project.write_logical("game_data", b"edited")
        (self.project.files_root / "Mess" / "c02.m").write_bytes(b"added")
        self.assertEqual(sorted(p.relative_to(self.project.output_dir).as_posix()
                                for p in self.project.output_dir.rglob("*") if p.is_file()),
                         ["files/FE8Data.bin", "files/Mess/c02.m"])
        self.assertEqual(self._store_files(), TREE)
        again = ModProject.load(self.project.directory)
        self.assertEqual(again.layout, LAYOUT_OVERLAY)
        self.assertEqual(again.read_logical("game_data"), b"edited")
        self.assertEqual(again.files.vanilla("files/FE8Data.bin"), b"data")
        saved = json.loads(again.project_file.read_text(encoding="utf-8"))
        self.assertEqual((saved["layout"], saved["input"]), (LAYOUT_OVERLAY, again.input_key))

    def test_build_reads_the_merged_stage(self):
        self.project.write_logical("game_data", b"edited")
        seen = {}

        def build(game, tree, dest, overwrite=True):
            seen.update({p.relative_to(tree).as_posix(): p.read_bytes() for p in Path(tree).rglob("*")
                         if p.is_file() and not p.name.startswith(".")})
            return None
        with mock.patch.object(project_module, "build_image", side_effect=build), \
                mock.patch("fe_modding.game_code.extended_flags.require_project_runtime"):
            self.project.build()
        self.assertEqual(seen, {**TREE, "files/FE8Data.bin": b"edited"})
        self.assertEqual(self._store_files(), TREE)

    def test_patch_needs_no_disc(self):
        self.project.write_logical("game_data", b"edited")
        (self.project.files_root / "Mess" / "c02.m").write_bytes(b"added")
        self.project.files.remove("files/Mess/c01.m")
        self.disc.unlink()
        dest = self.tmp / "mod.tpatch"
        summary = patch.create_project_patch(self.project, dest)
        self.assertEqual((summary.replaced, summary.added, summary.removed),
                         (["files/FE8Data.bin"], ["files/Mess/c02.m"], ["files/Mess/c01.m"]))
        with zipfile.ZipFile(dest) as archive:
            manifest = json.loads(archive.read(patch.MANIFEST_NAME))
            self.assertEqual(archive.read("files/files/FE8Data.bin"), b"edited")
        self.assertEqual(manifest["disc_id"], "GFEE01 rev 0")
        self.assertEqual(manifest["replace"]["files/FE8Data.bin"]["base_sha1"], patch._sha1(
            self.project.input_root / "files" / "FE8Data.bin"))

    def test_unchanged_rewrite_is_not_in_the_patch(self):
        self.project.write_logical("game_data", b"data")
        summary = patch.create_project_patch(self.project, self.tmp / "mod.tpatch")
        self.assertTrue(summary.empty)

    def test_input_problems_name_a_changed_or_missing_store(self):
        self.assertEqual(self.project.input_problems(), [])
        self.project.write_logical("game_data", b"edited")
        state = json.loads((self.project.directory / "overlay.json").read_text(encoding="utf-8"))
        state["base"]["files/FE8Data.bin"] = "0" * 40
        (self.project.directory / "overlay.json").write_text(json.dumps(state), encoding="utf-8")
        again = ModProject.load(self.project.directory)
        self.assertEqual(again.input_problems(), ["files/FE8Data.bin: the mod's file was made from another version of it"])
        vanilla_store.forget_store(again.input_store)
        gone = ModProject.load(self.project.directory)
        self.assertFalse(gone.has_extracted_files)
        self.assertIn("not available", gone.input_problems()[0])

    def test_use_input_folder_registers_a_users_extraction(self):
        dump = self.tmp / "dump"
        write_tree(dump / "DATA")
        project = ModProject.create(self.tmp, "Adopted", Game.PATH_OF_RADIANCE, layout=LAYOUT_OVERLAY)
        project.use_input_folder(dump)
        self.assertEqual(project.input_root, (dump / "DATA").resolve())
        self.assertEqual(project.read_logical("game_data"), b"data")
        rd = ModProject.create(self.tmp, "RD", Game.RADIANT_DAWN, layout=LAYOUT_OVERLAY)
        with self.assertRaises(ProjectError):
            rd.use_input_folder(dump)


if __name__ == "__main__":
    unittest.main()
