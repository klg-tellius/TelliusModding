import os
import stat
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fe_modding import config, tools, vanilla_store
from fe_modding.exceptions import ProjectError
from fe_modding.formats import gcdisc

BOOT = b"GFEE01\x00\x01" + bytes(0x438)
TREE = {
    "sys/boot.bin": BOOT,
    "sys/bi2.bin": b"bi2",
    "sys/apploader.img": b"apploader",
    "sys/main.dol": b"dol",
    "sys/fst.bin": b"fst",
    "files/FE8Data.bin": b"data",
    "files/mess/common.m": b"common",
}


def write_tree(root: Path, tree=TREE) -> None:
    for rel, data in tree.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)


def fst_sizes(_data):
    return {rel[len("files/"):]: len(data) for rel, data in TREE.items() if rel.startswith("files/")}


class VanillaStoreTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._cleanup)
        self.tmp = Path(self._tmp.name)
        for patch in (mock.patch.object(config, "load_setting",
                                        lambda key, default=None: str(self.tmp / "stores")
                                        if key == vanilla_store.SETTING_KEY else default),
                      mock.patch.object(gcdisc, "read_fst_sizes", fst_sizes)):
            patch.start()
            self.addCleanup(patch.stop)
        self.disc = self.tmp / "disc.iso"
        self.disc.write_bytes(b"image")

    def _cleanup(self):
        for path in self.tmp.rglob("*"):
            if path.is_file():
                os.chmod(path, stat.S_IREAD | stat.S_IWRITE)
        self._tmp.cleanup()

    def _fake_extract(self, source, dest, *, overwrite, wii):
        write_tree(Path(dest))

    def test_ensure_store_extracts_once_and_marks_files_read_only(self):
        with mock.patch.object(tools, "extract_disc", side_effect=self._fake_extract) as extract:
            store = vanilla_store.ensure_store(self.disc, wii=False)
            again = vanilla_store.ensure_store(self.disc, wii=False)
        self.assertEqual(extract.call_count, 2)  # the disc is read to learn its key...
        self.assertEqual(again.root, store.root)  # ...but the existing store is kept
        self.assertEqual(store.disc_id, "GFEE01")
        self.assertEqual(store.revision, 1)
        self.assertTrue(store.key.startswith("GFEE01-1-"))
        self.assertEqual((store.root / "files/FE8Data.bin").read_bytes(), b"data")
        with self.assertRaises(PermissionError):
            (store.root / "files/FE8Data.bin").write_bytes(b"x")
        self.assertEqual(store.verify(), [])
        self.assertEqual(store.verify(full=True), [])
        self.assertEqual([s.key for s in vanilla_store.list_stores()], [store.key])
        self.assertFalse([p for p in (self.tmp / "stores").iterdir() if p.name.startswith(".extract-")])

    def test_quick_verify_notices_a_change(self):
        with mock.patch.object(tools, "extract_disc", side_effect=self._fake_extract):
            store = vanilla_store.ensure_store(self.disc, wii=False)
        target = store.root / "files/mess/common.m"
        os.chmod(target, stat.S_IREAD | stat.S_IWRITE)
        target.write_bytes(b"changed")
        self.assertEqual(store.verify(), ["files/mess/common.m: size changed"])

    def test_failed_extraction_leaves_no_store(self):
        with mock.patch.object(tools, "extract_disc", side_effect=tools.ToolError("bad disc")):
            with self.assertRaises(tools.ToolError):
                vanilla_store.ensure_store(self.disc, wii=False)
        self.assertEqual(vanilla_store.list_stores(), [])
        self.assertFalse([p for p in (self.tmp / "stores").iterdir() if p.is_dir()])

    def test_adopt_folder_finds_the_partition_and_leaves_it_alone(self):
        dump = self.tmp / "dolphin dump"
        write_tree(dump / "DATA")
        store = vanilla_store.adopt_folder(dump, wii=False)
        self.assertEqual(store.root, (dump / "DATA").resolve())
        self.assertTrue(store.adopted)
        self.assertFalse((dump / "DATA" / vanilla_store.MANIFEST).exists())
        with self.assertRaises(PermissionError):
            (dump / "DATA/files/FE8Data.bin").write_bytes(b"x")
        self.assertEqual(store.verify(), [])
        self.assertEqual(vanilla_store.get_store(store.key).root, store.root)

    def test_adopt_folder_rejects_an_incomplete_dump(self):
        dump = self.tmp / "dump"
        write_tree(dump, {k: v for k, v in TREE.items() if k != "files/mess/common.m"})
        with self.assertRaisesRegex(ProjectError, "mess/common.m"):
            vanilla_store.adopt_folder(dump, wii=False)
        write_tree(dump)
        with self.assertRaisesRegex(ProjectError, "ticket.bin"):
            vanilla_store.adopt_folder(dump, wii=True)

    def test_unlink_shared_keeps_the_store_file_read_only(self):
        with mock.patch.object(tools, "extract_disc", side_effect=self._fake_extract):
            store = vanilla_store.ensure_store(self.disc, wii=False)
        shared = store.root / "files/FE8Data.bin"
        link = self.tmp / "link.bin"
        try:
            link.hardlink_to(shared)
        except OSError:
            self.skipTest("no hard links on this file system")
        vanilla_store.unlink_shared(link, shared)
        self.assertFalse(link.exists())
        self.assertFalse(os.stat(shared).st_mode & stat.S_IWRITE)

    def test_forget_store_deletes_only_app_made_files(self):
        dump = self.tmp / "dump"
        write_tree(dump)
        adopted = vanilla_store.adopt_folder(dump, wii=False)
        vanilla_store.forget_store(adopted)
        (dump / "files/FE8Data.bin").write_bytes(b"writable again")
        with mock.patch.object(tools, "extract_disc", side_effect=self._fake_extract):
            store = vanilla_store.ensure_store(self.disc, wii=False)
        vanilla_store.forget_store(store)
        self.assertFalse(store.root.exists())
        self.assertEqual(vanilla_store.list_stores(), [])


if __name__ == "__main__":
    unittest.main()
