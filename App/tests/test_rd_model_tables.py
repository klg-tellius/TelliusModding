"""Radiant Dawn's Model tables: the FE10BAnimData job list, FE10BTex battle textures and the
FE10AnimHeader map textures, through model_slots."""

import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fe_modding.exceptions import ProjectError
from fe_modding.games import Game

FE10 = os.environ.get("FE10_EXTRACTED_FILES")
MICAIAH = ("AID_MIKAYA1", "PID_MICAIAH", "JID_LIGHTMAGE")


@unittest.skipUnless(FE10, "set FE10_EXTRACTED_FILES to an extracted Radiant Dawn files/ directory")
class RdModelTableTests(unittest.TestCase):
    def setUp(self):
        from fe_modding.project import ModProject

        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.project = ModProject.create(Path(tmp.name), "tables", Game.RADIANT_DAWN)
        files = self.project.extracted_dir / "files"
        rels = ["FE10Data.cms", "FE10Anim.cms", "FE10Battle.cms", "ymu/mikaya1/mikaya1.tpl"]
        rels += [f"zu/{m}/{m}.tpl" for m in ("micL", "micU", "micS")]
        for rel in rels:
            (files / rel).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy(Path(FE10) / rel, files / rel)
            (files / rel).chmod(0o666)

    @staticmethod
    def _rows(data):
        from fe_modding.formats import fe10_battle
        document = fe10_battle.read_fe10_battle(data)
        def masked(record):  # the row with its string pointers blanked
            raw = bytearray(record.raw)
            for offset, _value in record.strings:
                raw[offset:offset + 4] = bytes(4)
            return bytes(raw), record.strings
        return [(t.name, [masked(r) for r in t.records]) for t in document.tables]

    def test_the_game_lookup_order(self):
        from fe_modding import model_slots
        from fe_modding.formats import fe10_battle
        battle = fe10_battle.read_fe10_battle(self.project.read_logical("battle_data"))
        self.assertEqual(fe10_battle.select_battle_row(battle, *MICAIAH), 118)
        # a class-only lookup takes the first row with the class, here Micaiah's own
        self.assertEqual(fe10_battle.select_battle_row(battle, None, None, "JID_LIGHTMAGE"), 118)
        self.assertIsNone(fe10_battle.select_battle_row(battle, "AID_NONE", "PID_NONE", "JID_NONE"))
        self.assertEqual(model_slots.rd_battle_model_for(self.project, *MICAIAH), ("micL", None))
        ground, air = model_slots.rd_battle_model_for(self.project, None, None, "JID_PEGASUSKNIGHT")
        self.assertTrue(ground and air and ground != air)

    def test_job_list_lines(self):
        from fe_modding import model_slots
        lines = model_slots.job_list(self.project)
        self.assertEqual(len(lines), 224)
        self.assertEqual(lines[118][:2], ("118: AID_MIKAYA1 / PID_MICAIAH / JID_LIGHTMAGE", "micL"))
        self.assertIn("in the air", lines[126][2])

    def test_set_line_retargets_the_exact_row(self):
        from fe_modding import model_slots
        model_slots.assign_battle_model(self.project, "micU", aid="AID_MIKAYA1", pid="PID_MICAIAH",
                                        jid="JID_LIGHTMAGE")
        self.assertEqual(model_slots.rd_battle_model_for(self.project, *MICAIAH), ("micU", None))
        self.assertEqual(len(model_slots.job_list(self.project)), 224)

    def test_set_line_adds_a_row_that_wins(self):
        from fe_modding import model_slots
        model_slots.assign_battle_model(self.project, "micS", pid="PID_TEST", jid="JID_TESTCLASS")
        self.assertEqual(model_slots.rd_battle_model_for(self.project, None, "PID_TEST", "JID_TESTCLASS"),
                         ("micS", None))
        lines = model_slots.job_list(self.project)
        self.assertEqual(lines[-1][:2], ("224: PID_TEST / JID_TESTCLASS", "micS"))
        model_slots.remove_job_line(self.project, lines[-1][0])
        self.assertEqual(len(model_slots.job_list(self.project)), 224)

    def test_set_line_refuses_a_line_the_game_would_skip(self):
        from fe_modding import model_slots
        before = self.project.read_logical("battle_data")
        with self.assertRaisesRegex(ProjectError, "Row 118"):
            model_slots.assign_battle_model(self.project, "micU", jid="JID_LIGHTMAGE")
        self.assertEqual(self.project.read_logical("battle_data"), before)

    def test_battle_textures(self):
        from fe_modding import model_slots
        before = self.project.read_logical("battle_data")
        self.assertEqual(model_slots.battle_textures(self.project, "micL"),
                         {"自軍": "micL", "敵軍": "micL", "中立": "micL", "味方": "micL"})
        model_slots.set_battle_texture(self.project, "micL", "敵軍", "micL_red")
        model_slots.set_battle_texture(self.project, "micL", "PID_TEST", "micL_test")
        textures = model_slots.battle_textures(self.project, "micL")
        self.assertEqual((textures["敵軍"], textures["PID_TEST"], len(textures)), ("micL_red", "micL_test", 5))
        model_slots.remove_battle_texture(self.project, "micL", "PID_TEST")
        model_slots.set_battle_texture(self.project, "micL", "敵軍", "micL")
        # the same rows as before (the rebuilt string pool may keep the removed names)
        self.assertEqual(self._rows(self.project.read_logical("battle_data")), self._rows(before))
        with self.assertRaises(ProjectError):
            model_slots.remove_battle_texture(self.project, "micL", "PID_NONE")

    def test_map_texture_name(self):
        from fe_modding import model_slots
        record = next(r for r in model_slots.map_model_records(self.project) if r.base_aid == "AID_MIKAYA1")
        self.assertEqual((record.class_folder, record.texture_name), ("mikaya1", "mikaya1"))
        model_slots.set_map_texture_name(self.project, "AID_MIKAYA1", "mikaya1_b")
        record = next(r for r in model_slots.map_model_records(self.project) if r.base_aid == "AID_MIKAYA1")
        self.assertEqual(record.texture_name, "mikaya1_b")
        with self.assertRaises(ProjectError):
            model_slots.set_map_texture_name(self.project, "AID_MIKAYA1", "bad name.tpl")


if __name__ == "__main__":
    unittest.main()
