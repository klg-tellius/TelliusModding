import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fe_modding import game_files
from fe_modding.exceptions import ProjectError
from fe_modding.formats import gcdisc
from fe_modding.game_files import LegacyFiles, OverlayFiles, write_atomic

DISC = {
    "sys/main.dol": b"dol",
    "sys/boot.bin": b"boot",
    "files/FE8Data.bin": b"data",
    "files/mess/common.m": b"common",
    "files/mess/c01.m": b"c01",
    "files/zmap/bmap01/map.cmp": b"map",
}


def fake_fst_paths(_data):
    return [rel[len("files/"):] for rel in DISC if rel.startswith("files/")]


class ContractMixin:
    """What every backend must do; ``make()`` returns a backend over a copy of :data:`DISC`."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        patcher = mock.patch.object(gcdisc, "read_fst_paths", fake_fst_paths)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.files = self.make()

    def test_reads_the_disc(self):
        self.assertEqual(self.files.read("files/FE8Data.bin"), b"data")
        self.assertTrue(self.files.is_dir("files/mess"))
        self.assertIsNone(self.files.path("files/none.bin"))
        with self.assertRaises(ProjectError):
            self.files.read("files/none.bin")
        self.assertTrue(self.files.has_files)

    def test_rejects_paths_outside_the_tree(self):
        with self.assertRaises(ProjectError):
            self.files.read("files/../../x")
        with self.assertRaises(ProjectError):
            self.files.rel(self.root.parent / "elsewhere.bin")

    def test_accepts_its_own_paths_back(self):
        real = self.files.path("files/mess/c01.m")
        self.assertEqual(self.files.rel(real), "files/mess/c01.m")
        self.assertEqual(self.files.rel("files\\mess\\c01.m"), "files/mess/c01.m")

    def test_write_then_read_and_vanilla_stays(self):
        self.files.write("files/FE8Data.bin", b"edited")
        self.files.write("files/FE8Data.bin", b"edited twice")
        self.assertEqual(self.files.read("files/FE8Data.bin"), b"edited twice")
        self.assertEqual(self.files.vanilla("files/FE8Data.bin"), b"data")
        self.assertTrue(self.files.is_modified("files/FE8Data.bin"))
        self.assertFalse(self.files.is_added("files/FE8Data.bin"))
        self.assertFalse(self.files.is_modified("files/mess/common.m"))
        self.assertEqual(self.files.vanilla("files/mess/common.m"), b"common")

    def test_added_file(self):
        self.files.write("files/mess/new.m", b"new")
        self.assertTrue(self.files.is_added("files/mess/new.m"))
        self.assertTrue(self.files.is_modified("files/mess/new.m"))
        self.assertIsNone(self.files.vanilla("files/mess/new.m"))
        self.assertIn("new.m", self.files.listdir("files/mess"))
        self.assertTrue(self.files.revert("files/mess/new.m"))
        self.assertFalse(self.files.exists("files/mess/new.m"))

    def test_revert(self):
        self.files.write("files/mess/c01.m", b"x")
        self.assertEqual(self.files.modified_in("files/mess"), ["files/mess/c01.m"])
        self.assertTrue(self.files.revert("files/mess/c01.m"))
        self.assertEqual(self.files.read("files/mess/c01.m"), b"c01")
        self.assertEqual(self.files.modified_in("files/mess"), [])
        self.assertFalse(self.files.revert("files/mess/c01.m"))

    def test_merged_listing_and_glob(self):
        self.files.write("files/mess/c02.m", b"c02")
        self.files.write("files/mess/c01.m", b"edited")
        self.assertEqual(self.files.listdir("files/mess"), ["c01.m", "c02.m", "common.m"])
        self.assertEqual(self.files.glob("files/mess", "C0*.M"), ["files/mess/c01.m", "files/mess/c02.m"])
        self.assertEqual(self.files.glob("files", "*", dirs=True), ["files/mess", "files/zmap"])
        self.assertEqual(self.files.glob("files", "map.cmp", recursive=True), ["files/zmap/bmap01/map.cmp"])
        self.assertEqual(self.files.iter_files("files/mess"),
                         ["files/mess/c01.m", "files/mess/c02.m", "files/mess/common.m"])

    def test_remove_and_bring_back(self):
        self.files.remove("files/mess/c01.m")
        self.assertFalse(self.files.exists("files/mess/c01.m"))
        self.assertTrue(self.files.is_removed("files/mess/c01.m"))
        self.assertNotIn("c01.m", self.files.listdir("files/mess"))
        self.assertEqual(self.files.changes().removed, ["files/mess/c01.m"])
        self.files.write("files/mess/c01.m", b"back")
        self.assertEqual(self.files.read("files/mess/c01.m"), b"back")
        self.assertFalse(self.files.is_removed("files/mess/c01.m"))

    def test_remove_folder(self):
        self.files.remove("files/zmap")
        self.assertFalse(self.files.exists("files/zmap/bmap01/map.cmp"))
        self.assertNotIn("zmap", self.files.listdir("files"))
        self.assertEqual(self.files.changes().removed, ["files/zmap/bmap01/map.cmp"])

    def test_changes(self):
        self.files.write("files/FE8Data.bin", b"edited")
        self.files.write("files/added.bin", b"new")
        self.files.remove("files/mess/common.m")
        changes = self.files.changes()
        self.assertEqual(changes.replaced, ["files/FE8Data.bin"])
        self.assertEqual(changes.added, ["files/added.bin"])
        self.assertEqual(changes.removed, ["files/mess/common.m"])

    def test_writable_copy_edits_only_the_mod(self):
        real = self.files.writable_copy("files/mess/common.m")
        real.write_bytes(b"in place")
        self.assertEqual(self.files.read("files/mess/common.m"), b"in place")
        self.assertEqual(self.files.vanilla("files/mess/common.m"), b"common")

    def test_failed_write_leaves_the_file(self):
        with mock.patch.object(game_files.os, "replace", side_effect=OSError("disk full")):
            with self.assertRaises(OSError):
                self.files.write("files/FE8Data.bin", b"edited")
        self.assertEqual(self.files.read("files/FE8Data.bin"), b"data")
        folder = self.files.path("files")
        self.assertFalse([p for p in folder.rglob("*.tmp")])


def _make_tree(root: Path) -> None:
    for rel, data in DISC.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    (root / "sys" / "fst.bin").write_bytes(b"fst")


class LegacyContractTests(ContractMixin, unittest.TestCase):
    def make(self):
        _make_tree(self.root / "extracted")
        return LegacyFiles(self.root / "extracted", self.root / "originals")

    def test_keeps_the_original_beside_the_tree(self):
        self.files.write("files/FE8Data.bin", b"edited")
        self.assertEqual((self.root / "originals" / "files" / "FE8Data.bin").read_bytes(), b"data")


class OverlayContractTests(ContractMixin, unittest.TestCase):
    def make(self):
        _make_tree(self.root / "input")
        return OverlayFiles(self.root / "input", self.root / "project" / "output",
                            self.root / "project" / "overlay.json")

    def tearDown(self):
        # The input is never written, whatever the test did.
        for rel, data in DISC.items():
            self.assertEqual((self.root / "input" / rel).read_bytes(), data, rel)

    def test_output_holds_only_the_changes(self):
        self.files.write("files/FE8Data.bin", b"edited")
        output = self.root / "project" / "output"
        self.assertEqual([p.relative_to(output).as_posix() for p in output.rglob("*") if p.is_file()],
                         ["files/FE8Data.bin"])

    def test_records_the_input_each_file_replaced(self):
        self.files.write("files/FE8Data.bin", b"edited")
        state = json.loads((self.root / "project" / "overlay.json").read_text(encoding="utf-8"))
        self.assertEqual(state["base"], {"files/FE8Data.bin": game_files.sha1_of(self.root / "input/files/FE8Data.bin")})

    def test_state_survives_reopening(self):
        self.files.remove("files/mess/c01.m")
        again = OverlayFiles(self.root / "input", self.root / "project" / "output",
                             self.root / "project" / "overlay.json")
        self.assertTrue(again.is_removed("files/mess/c01.m"))

    def test_writing_into_a_removed_folder_keeps_its_other_files_removed(self):
        self.files.remove("files/mess")
        self.files.write("files/mess/c01.m", b"back")
        self.assertEqual(self.files.listdir("files/mess"), ["c01.m"])
        self.assertEqual(self.files.changes().removed, ["files/mess/common.m"])


class WriteAtomicTests(unittest.TestCase):
    def test_replaces_a_hard_link_instead_of_writing_through_it(self):
        with tempfile.TemporaryDirectory() as tmp:
            shared, link = Path(tmp) / "shared.bin", Path(tmp) / "link.bin"
            shared.write_bytes(b"vanilla")
            try:
                link.hardlink_to(shared)
            except OSError:
                self.skipTest("no hard links on this file system")
            write_atomic(link, b"edited")
            self.assertEqual(shared.read_bytes(), b"vanilla")
            self.assertEqual(link.read_bytes(), b"edited")


if __name__ == "__main__":
    unittest.main()
