"""The search behind Remove: game files that still name a record's ID, on both games."""

import os
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fe_modding import fe8_references
from fe_modding.formats import lz10
from fe_modding.game_profile import PATH_OF_RADIANCE_PROFILE, RADIANT_DAWN_PROFILE


def _project(root: Path, profile):
    return SimpleNamespace(extracted_dir=root, profile=profile)


class DeploymentFileTests(unittest.TestCase):
    def test_radiant_dawn_searches_every_difficulty_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            folder = root / "files" / "zmap" / "bmap0101"
            folder.mkdir(parents=True)
            (folder / "dispos_n.bin").write_bytes(b"\0PID_TEST\0JID_X\0")
            (folder / "dispos_h.bin").write_bytes(b"\0PID_TEST\0")
            (folder / "dispos_c.bin").write_bytes(b"\0PID_OTHER\0")
            (folder / "map.cmp").write_bytes(lz10.compress(b"\0PID_TEST\0"))  # not a deployment
            refs = fe8_references.file_references(_project(root, RADIANT_DAWN_PROFILE), "PID_TEST")
        self.assertEqual([r.where for r in refs], ["zmap/bmap0101/dispos_h.bin", "zmap/bmap0101/dispos_n.bin"])

    def test_path_of_radiance_reads_its_compressed_dispos(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            folder = root / "files" / "zmap" / "bmap01"
            folder.mkdir(parents=True)
            (folder / "dispos.cmp").write_bytes(lz10.compress(b"\0PID_TEST\0PID_TEST\0"))
            refs = fe8_references.file_references(_project(root, PATH_OF_RADIANCE_PROFILE), "PID_TEST")
        self.assertEqual([str(r) for r in refs], ["zmap/bmap01/dispos.cmp: named 2 times"])

    def test_a_longer_id_is_not_a_use(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            folder = root / "files" / "zmap" / "bmap0101"
            folder.mkdir(parents=True)
            (folder / "dispos_n.bin").write_bytes(b"\0PID_TEST_2\0XPID_TEST\0")
            refs = fe8_references.file_references(_project(root, RADIANT_DAWN_PROFILE), "PID_TEST")
        self.assertEqual(refs, [])


@unittest.skipUnless(os.environ.get("FE10_EXTRACTED"), "set FE10_EXTRACTED to an extracted Radiant Dawn disc")
class RadiantDawnDiscTests(unittest.TestCase):
    def test_retail_ids_are_found_in_scripts_and_deployments(self):
        project = _project(Path(os.environ["FE10_EXTRACTED"]), RADIANT_DAWN_PROFILE)
        micaiah = {r.where for r in fe8_references.file_references(project, "PID_MICAIAH")}
        self.assertIn("Scripts/C0101.cmb", micaiah)
        self.assertIn("zmap/bmap0101/dispos_n.bin", micaiah)
        light_mage = {r.where for r in fe8_references.file_references(project, "JID_LIGHTMAGE")}
        self.assertIn("zmap/bmap0101/dispos_h.bin", light_mage)


if __name__ == "__main__":
    unittest.main()
