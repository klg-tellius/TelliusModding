"""Phase 8 of the PoR/RD parity plan: the Tools on Radiant Dawn (project check, text export, saves,
Game Code)."""

import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fe_modding.game_profile import Game
from fe_modding.project import ModProject

FE10 = os.environ.get("FE10_EXTRACTED_FILES")


@unittest.skipUnless(FE10, "set FE10_EXTRACTED_FILES to an extracted Radiant Dawn files/ directory")
class RdCheckTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.project = ModProject.create(Path(self._tmp.name), "T", Game.RADIANT_DAWN)
        self.files = self.project.extracted_dir / "files"
        self.files.mkdir(parents=True, exist_ok=True)
        self.write("FE10Data.cms", (Path(FE10) / "FE10Data.cms").read_bytes())

    def write(self, relative: str, data: bytes) -> None:
        path = self.files / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)

    def test_deployment_naming_a_missing_record(self):
        from fe_modding import validator
        from fe_modding.formats import dispo

        raw = (Path(FE10) / "zmap/bmap0101/dispos_n.bin").read_bytes()
        self.write("zmap/bmap0101/dispos_n.bin", raw)
        clean = validator.validate_project(self.project)
        self.assertEqual([i for i in clean.issues if i.where.startswith("zmap/bmap0101/dispos")], [])

        doc = dispo.parse_dispo(raw)
        section = next(s for s in doc.sections if s.units)
        unit = section.units[0]
        unit[dispo.FIELD["pid"]] = "PID_GHOST"
        unit[dispo.FIELD["item0"]] = "IID_NOPE/D"  # the /D drop flag is not part of the ID
        self.write("zmap/bmap0101/dispos_n.bin", dispo.build_dispo(doc))
        errors = [i for i in validator.validate_project(self.project).errors if i.where == "zmap/bmap0101/dispos_n.bin"]
        self.assertEqual(sorted(i.message for i in errors),
                         [f"section {section.name}, unit 1 carries IID_NOPE, which does not exist.",
                          f"section {section.name}, unit 1 is PID_GHOST, which does not exist."])
        self.assertEqual(errors[0].route, ("chapter", "0101"))

    def test_scripts_and_shops(self):
        from fe_modding import validator
        from fe_modding.formats import shop

        self.write("Scripts/C0101.cmb", b"\x00PID_MICAIAH\x00PID_GHOST\x00")
        raw = (Path(FE10) / "Shop/shopitem_n.bin").read_bytes()
        doc = shop.parse_shop(raw)
        section = next(s for s in doc.sections if any(isinstance(i, str) and i.startswith("IID_") for i in s.items))
        at = next(n for n, i in enumerate(section.items) if isinstance(i, str) and i.startswith("IID_"))
        section.items[at] = "IID_NOPE"
        self.write("Shop/shopitem_n.bin", shop.build_shop(doc))
        report = validator.validate_project(self.project)
        script = [i for i in report.warnings if i.where == "Scripts/C0101.cmb"]
        self.assertEqual([i.message for i in script], ["The script names PID_GHOST, which does not exist."])
        self.assertEqual(script[0].route, ("chapter", "0101", "script"))
        self.assertEqual([i.message for i in report.errors if i.area == "Shops"],
                         [f"{section.name} sells IID_NOPE, which does not exist."])

    def test_retail_project_has_no_errors(self):
        from fe_modding import validator_fe10

        # the deployment files of every map and the shops, against the retail database
        for path in Path(FE10).glob("zmap/*/dispos_*.bin"):
            self.write(f"zmap/{path.parent.name}/{path.name}", path.read_bytes())
        for path in (Path(FE10) / "Shop").glob("*.bin"):
            self.write(f"Shop/{path.name}", path.read_bytes())
        report = validator_fe10.validate_fe10_project(self.project)
        self.assertEqual([i for i in report.errors if i.area != "Chapters"], [])
        self.assertTrue(any("PID_TIBARN_EV" in i.message for i in report.warnings))

    def test_text_export_deployments_shops_and_sound(self):
        import json
        import shutil

        from fe_modding import text_export

        for rel in ("zmap/bmap0101/dispos_n.bin", "Shop/shopitem_n.bin", "Sound/sound_data_en.cms",
                    "Sound/sound_us.brsar"):
            self.write(rel, (Path(FE10) / rel).read_bytes())
        out = Path(self._tmp.name) / "out"
        _written, problems = text_export.export_project(self.project, out, parts={"deployments", "shops", "sound"})
        self.assertEqual(problems, [])
        sections = json.loads((out / "deployments/bmap0101/dispos_n.json").read_text(encoding="utf-8"))
        unit = next(s for s in sections if s["name"] == "bmap0101_mikata_n")["units"][0]
        self.assertEqual((unit["pid"], unit["jid"], unit["item0"]), ("PID_MICAIAH", "JID_LIGHTMAGE", "IID_LIGHT"))
        self.assertIn("SHOP_PERSON_C0101", json.loads((out / "shops/shopitem_n.json").read_text(encoding="utf-8")))
        bgm = (out / "sound/bgm_cues.tsv").read_text(encoding="utf-8").splitlines()
        self.assertTrue(any(line.startswith("BGM_BASE1\tSTRM_BGM_SYS_KYOTEN1\t") for line in bgm))
        sounds = (out / "sound/brsar_sounds.tsv").read_text(encoding="utf-8")
        self.assertIn("strm/fe10_bgm_sys_title1_32k.brstm", sounds)
        shutil.rmtree(out)


if __name__ == "__main__":
    unittest.main()
