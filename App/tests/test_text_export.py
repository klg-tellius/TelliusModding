import json
import os
import shutil
import sys
import tempfile
import unittest
from types import SimpleNamespace
from unittest import mock
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


class RadiantDawnTextExportTests(unittest.TestCase):
    def setUp(self):
        from fe_modding.games import Game
        from fe_modding.project import ModProject
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.project = ModProject.create(self.root, "RD export", Game.RADIANT_DAWN)

    def test_radiant_dawn_has_its_implemented_export_parts(self):
        self.assertEqual([name for name, _label in text_export.parts_for(self.project)],
                         ["FE10Data", "FE10Growth", "messages", "scripts"])

    def test_fe10_records_export_semantic_values_without_binary_offsets(self):
        record = SimpleNamespace(values={"pid": "PID_IKE", "level": 11, "block": 0x1234},
                                 lists={"skills": ["SID_AETHER"]}, bonuses=None)
        database = SimpleNamespace(table=lambda _kind: [record])
        out = self.root / "out"
        with mock.patch("fe_modding.formats.fe10data.read_fe10data", return_value=database), \
                mock.patch("fe_modding.formats.fe10data.ALL_KINDS", ("character",)):
            written = text_export._fe10data(SimpleNamespace(read_logical=lambda _name: b"data"), out)
        self.assertEqual(written, [out / "FE10Data" / "character.json"])
        row = json.loads(written[0].read_text(encoding="utf-8"))[0]
        self.assertEqual(row, {"pid": "PID_IKE", "level": 11, "skills": ["SID_AETHER"]})

    def test_fe10_messages_use_lossless_readable_notation(self):
        from fe_modding.games import Game
        from fe_modding.formats import fe10_message, message

        mess = self.project.files_dir / "Mess" / "e_c0101.m"
        mess.parent.mkdir(parents=True)
        raw = fe10_message.to_raw("<speaker:04>Hello.<wait>")
        message.write_messages_path(mess, [message.Message("MS_TEST", raw)])
        written = text_export._messages(self.project, self.root / "out")
        exported = written[0].read_text(encoding="utf-8")
        self.assertIn("## MS_TEST", exported)
        self.assertIn("<speaker:04>Hello.<wait>", exported)


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
