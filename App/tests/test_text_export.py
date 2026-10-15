import json
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fe_modding import text_export


class TextExportGuardTests(unittest.TestCase):
    def setUp(self):
        from fe_modding.games import Game
        from fe_modding.project import ModProject
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.project = ModProject.create(self.root, "export", Game.PATH_OF_RADIANCE)

    def test_refuses_a_foreign_folder(self):
        foreign = self.root / "foreign"
        (foreign / "scripts").mkdir(parents=True)
        (foreign / "scripts" / "keep.txt").write_text("mine")
        with self.assertRaises(ValueError):
            text_export.export_project(self.project, foreign)
        self.assertTrue((foreign / "scripts" / "keep.txt").is_file())

    def test_missing_files_are_problems_not_errors(self):
        written, problems = text_export.export_project(self.project, self.root / "out")
        self.assertEqual(written, [])
        # the single-file parts report their missing file; folder parts just export nothing
        self.assertEqual(sorted(p.split(':')[0] for p in problems),
                         sorted(label for name, label in text_export.PARTS if name in ('FE8Data', 'sound', 'faces', 'zdbx')))
        self.assertTrue((self.root / "out" / text_export.MARKER).is_file())


@unittest.skipUnless(os.environ.get("FE9_EXTRACTED_FILES"), "set FE9_EXTRACTED_FILES to an extracted files/ directory")
class TextExportRetailTests(unittest.TestCase):
    def test_tables_and_messages(self):
        from fe_modding.games import Game
        from fe_modding.project import ModProject
        source = Path(os.environ["FE9_EXTRACTED_FILES"])
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        project = ModProject.create(Path(tmp.name), "export", Game.PATH_OF_RADIANCE)
        files = project.extracted_dir / "files"
        (files / "Mess").mkdir(parents=True)
        shutil.copy(source / "FE8Data.bin", files / "FE8Data.bin")
        shutil.copy(source / "Mess" / "c01.m", files / "Mess" / "c01.m")
        out = Path(tmp.name) / "out"
        written, problems = text_export.export_project(project, out, parts={"FE8Data", "messages"})
        self.assertFalse(problems)
        characters = json.loads((out / "FE8Data" / "characters.json").read_text(encoding="utf-8"))
        self.assertIn("PID_IKE", [c["pid"] for c in characters])
        self.assertNotIn("offset", characters[0])
        self.assertIn("$R上下会話|", (out / "messages" / "c01.txt").read_text(encoding="utf-8"))
        again, _ = text_export.export_project(project, out, parts={"FE8Data", "messages"})
        self.assertEqual(sorted(again), sorted(written))


if __name__ == "__main__":
    unittest.main()
