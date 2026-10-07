import json
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fe_modding import patch
from fe_modding.games import Game


def _write(root: Path, rel: str, data: bytes) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)


class PatchTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        tmp = Path(self._tmp.name)
        self.base, self.mod, self.target = tmp / "base", tmp / "mod", tmp / "target"
        self.dest = tmp / "mod.tpatch"
        boot = b"GFEE01\x00\x01" + bytes(0x438)
        for root in (self.base, self.mod, self.target):
            _write(root, "sys/boot.bin", boot)
            _write(root, "sys/main.dol", b"dol" * 100)
            _write(root, "files/same.bin", b"unchanged" * 50)
            _write(root, "files/edit.bin", b"retail")
            _write(root, "files/gone.bin", b"deleted later")
        _write(self.mod, "files/edit.bin", b"modded!")
        _write(self.mod, "files/new/track.bin", b"a new file")
        (self.mod / "files" / "gone.bin").unlink()

    def test_patch_holds_only_the_differences(self):
        summary = patch.create_patch(self.base, self.mod, self.dest, game=Game.PATH_OF_RADIANCE, name="Test")
        self.assertEqual(summary.replaced, ["files/edit.bin"])
        self.assertEqual(summary.added, ["files/new/track.bin"])
        self.assertEqual(summary.removed, ["files/gone.bin"])
        with zipfile.ZipFile(self.dest) as archive:
            self.assertEqual(sorted(archive.namelist()),
                             ["files/files/edit.bin", "files/files/new/track.bin", "manifest.json"])
        info = patch.read_patch(self.dest)
        self.assertEqual(info.game, Game.PATH_OF_RADIANCE)
        self.assertEqual(info.disc_id, "GFEE01 rev 1")

    def test_manifest_carries_author_version_and_credits(self):
        patch.create_patch(self.base, self.mod, self.dest, game=Game.PATH_OF_RADIANCE, name="Quest",
                           author="Ana", version="1.2", credits="Music by Bo")
        info = patch.read_patch(self.dest)
        self.assertEqual((info.author, info.version, info.credits), ("Ana", "1.2", "Music by Bo"))
        self.assertEqual(info.title, "Quest 1.2 by Ana")

    def test_older_patches_without_those_fields_still_read(self):
        patch.create_patch(self.base, self.mod, self.dest, game=Game.PATH_OF_RADIANCE)
        info = patch.read_patch(self.dest)
        self.assertEqual((info.author, info.version, info.credits, info.title), ("", "", "", ""))

    def test_apply_turns_the_base_into_the_mod(self):
        patch.create_patch(self.base, self.mod, self.dest, game=Game.PATH_OF_RADIANCE)
        patch.apply_patch(self.dest, self.target)
        self.assertEqual((self.target / "files/edit.bin").read_bytes(), b"modded!")
        self.assertEqual((self.target / "files/new/track.bin").read_bytes(), b"a new file")
        self.assertFalse((self.target / "files/gone.bin").exists())
        self.assertEqual((self.target / "files/same.bin").read_bytes(), b"unchanged" * 50)

    def test_apply_refuses_a_different_base_and_leaves_it_untouched(self):
        patch.create_patch(self.base, self.mod, self.dest, game=Game.PATH_OF_RADIANCE)
        _write(self.target, "files/gone.bin", b"another version")
        with self.assertRaises(patch.PatchError):
            patch.apply_patch(self.dest, self.target)
        self.assertEqual((self.target / "files/edit.bin").read_bytes(), b"retail")
        self.assertFalse((self.target / "files/new").exists())

    def test_apply_refuses_another_disc(self):
        patch.create_patch(self.base, self.mod, self.dest, game=Game.PATH_OF_RADIANCE)
        _write(self.target, "sys/boot.bin", b"GFEP01\x00\x00" + bytes(0x438))
        with self.assertRaises(patch.PatchError):
            patch.apply_patch(self.dest, self.target)

    def test_apply_rejects_paths_outside_the_tree(self):
        manifest = {"format": "tellius-patch", "version": 1, "game": "path_of_radiance",
                    "add": {"../escape.bin": {"sha1": ""}}}
        with zipfile.ZipFile(self.dest, "w") as archive:
            archive.writestr("manifest.json", json.dumps(manifest))
            archive.writestr("files/../escape.bin", b"x")
        with self.assertRaises(patch.PatchError):
            patch.apply_patch(self.dest, self.target)
        self.assertFalse((self.target.parent / "escape.bin").exists())


if __name__ == "__main__":
    unittest.main()
