import os
import tempfile
import unittest
from argparse import Namespace
from pathlib import Path

from tools import release_checks as rc


def _disc(folder: Path, disc_id: str) -> Path:
    (folder / "sys").mkdir(parents=True)
    (folder / "files").mkdir()
    (folder / "sys" / "boot.bin").write_bytes(disc_id.encode() + bytes(26))
    return folder


class ReleaseChecksTests(unittest.TestCase):
    def test_finds_each_disc_once_and_orders_them(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            _disc(root / "rd" / "RFEJ01", "RFEJ01")
            _disc(root / "rd" / "RFEE01", "RFEE01")
            _disc(root / "rd" / "edit_test", "RFEE01")  # a project's copy: the RFEE01 folder wins
            _disc(root / "por" / "GFEE01", "GFEE01")
            (root / "rd" / "_audit").mkdir()
            discs = rc.find_discs([root / "rd", root / "por"])
            self.assertEqual([(d.disc_id, d.root.name) for d in discs],
                             [("GFEE01", "GFEE01"), ("RFEE01", "RFEE01"), ("RFEJ01", "RFEJ01")])
            # a disc given by its own path is always kept
            self.assertEqual([d.root.name for d in rc.find_discs([root / "rd" / "edit_test"])], ["edit_test"])

    def test_environment_sets_only_the_game_s_variables(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            por = rc.Disc(_disc(root / "GFEE01", "GFEE01"), "GFEE01")
            us = rc.Disc(_disc(root / "RFEE01", "RFEE01"), "RFEE01")
            eu = rc.Disc(_disc(root / "RFEP01", "RFEP01"), "RFEP01")
            args = Namespace(full=True, saves=None, blender=None)
            env = rc.disc_environment(por, args)
            self.assertEqual(env["FE9_EXTRACTED_FILES"], str(por.files))
            self.assertNotIn("FE10_EXTRACTED", env)
            self.assertEqual(env["TELLIUS_CORPUS"], "full")
            env = rc.disc_environment(us, args, {"E": us, "P": eu})
            self.assertEqual(env["FE10_EXTRACTED"], str(us.root))
            self.assertEqual(env["FE10_EU_EXTRACTED"], str(eu.root))
            self.assertNotIn("FE9_EXTRACTED_FILES", env)
            self.assertNotIn("FE10_EU_EXTRACTED", rc.disc_environment(eu, args))

    def test_counts_a_module_s_results(self):
        result = rc.run_module("test_release_checks_missing", dict(os.environ), 60)  # no such file: nothing ran
        self.assertEqual(result.ran, 0)


if __name__ == "__main__":
    unittest.main()
