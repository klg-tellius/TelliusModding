"""Radiant Dawn colour variants (colour_variants_fe10): map animation IDs, battle selectors and
texture rows, portraits. Checked in Dolphin: Micaiah's map sprite, battle model and portrait."""

import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fe_modding.game_profile import COLOUR_VARIANTS, RADIANT_DAWN_PROFILE, Game

FE10 = os.environ.get("FE10_EXTRACTED_FILES")


class ProfileTests(unittest.TestCase):
    def test_on_radiant_dawn(self):
        self.assertTrue(RADIANT_DAWN_PROFILE.supports(COLOUR_VARIANTS))


@unittest.skipUnless(FE10, "set FE10_EXTRACTED_FILES to an extracted Radiant Dawn files/ directory")
class RdVariantTests(unittest.TestCase):
    def setUp(self):
        from fe_modding.project import ModProject

        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.project = ModProject.create(Path(tmp.name), "variant", Game.RADIANT_DAWN)
        self.files = self.project.extracted_dir / "files"
        source = Path(FE10)
        rels = ["FE10Data.cms", "FE10Anim.cms", "FE10Battle.cms", "Face/facedata.bin", "Face/wide/facedata.bin",
                "Face/MICAIAH.cms", "Face/wide/MICAIAH.cms"]
        rels += [f"ymu/mikaya{n}/mikaya{n}.tpl" for n in (1, 2, 3)]
        rels += [f"zu/{m}/{m}.tpl" for m in ("micL", "micU", "micS")]
        for rel in rels:
            (self.files / rel).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy(source / rel, self.files / rel)
            (self.files / rel).chmod(0o666)

    def test_character_variant(self):
        from fe_modding import colour_variants_fe10 as cv
        from fe_modding.formats import fe10_anim, fe10_battle, fe10_faces, fe10data
        from fe_modding.recolour import Recolour

        plan = cv.plan_character_variant(self.project, "PID_MICAIAH", "TEST")
        self.assertEqual(len(plan.copies), 3 + 3 + 2)  # three tiers' map and battle textures, two portraits
        self.assertEqual(plan.notes, [])
        cv.apply_variant(self.project, plan, Recolour(band=180, shift=120))

        db = fe10data.read_fe10data(self.project.read_logical("game_data"))
        micaiah = next(r for r in db.characters if r.id == "PID_MICAIAH")
        self.assertEqual([micaiah.values[f"aid_{n}"] for n in (1, 2, 3)],
                         ["AID_MIKAYA1_TEST", "AID_MIKAYA2_TEST", "AID_MIKAYA3_TEST"])
        self.assertEqual(micaiah.values["fid"], "FID_MICAIAH_TEST")

        anim = fe10_anim.read_fe10_anim(self.project.read_logical("anim_data"))
        headers = {h.aid_name: (i, h) for i, h in enumerate(anim.headers)}
        row, header = headers["AID_MIKAYA1_TEST"]
        self.assertEqual((header.texture_name, header.ordinal, header.model_index),
                         ("mikaya1_test", row, headers["AID_MIKAYA1"][1].model_index))
        self.assertTrue((self.files / "ymu/mikaya1/mikaya1_test.tpl").is_file())

        battle = fe10_battle.read_fe10_battle(self.project.read_logical("battle_data"))
        selectors = [dict(r.strings) for r in battle.table("FE10BAnimData").records]
        clone = next(s for s in selectors if s.get(0) == "AID_MIKAYA1_TEST")
        self.assertEqual((clone.get(4), clone.get(8), clone.get(12)), ("PID_MICAIAH", "JID_LIGHTMAGE", "光魔道士ミカヤ"))
        unit = next(u for u in battle.unit_texture_sets if u.model_name == "micL")
        self.assertEqual(unit.mappings[-1].condition, "PID_MICAIAH")
        self.assertEqual(unit.mappings[-1].texture_name, "micL_test")
        self.assertTrue((self.files / "zu/micL/micL_test.tpl").is_file())

        for folder in ("Face", "Face/wide"):
            faces = fe10_faces.read_face_data((self.files / folder / "facedata.bin").read_bytes())
            record = next(r for r in faces if r.fid == "FID_MICAIAH_TEST")
            self.assertEqual(record.filename, "MICAIAH_TEST.cms")
            self.assertTrue((self.files / folder / "MICAIAH_TEST.cms").is_file())
        with self.assertRaisesRegex(Exception, "already exists"):  # never overwrites a texture
            cv.apply_variant(self.project, plan, Recolour(band=180, shift=60))

    def test_battle_only_keeps_the_animation_ids(self):
        from fe_modding import colour_variants_fe10 as cv

        plan = cv.plan_character_variant(self.project, "PID_MICAIAH", "BLUE", map_models=False, portrait=False)
        self.assertEqual({c.kind for c in plan.copies}, {"battle"})
        self.assertEqual((plan.anim_clones, plan.selector_clones, plan.rd_character_aids), ([], [], []))
        self.assertEqual(len(plan.unit_textures), 3)


if __name__ == "__main__":
    unittest.main()
