"""rd_armies: the story flow's Radiant Dawn chapter armies written as startup.cmb's TEAM_<id>_ED
hand-overs and ChapterData groups and lords."""

import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fe_modding import rd_armies

FILES = os.environ.get("FE10_EXTRACTED_FILES")

STARTUP = """global g0 @ 0

# function 1
@export
def TEAM_0402_ED():
    UnitTransferToForceALL(5, 9)
    UnitTransferToForceALL(10, 5)
    DumpUnit()

# function 2
@export
def TEAM_0406_ED():
    UnitTransferToForceALL(5, 10)
    DumpUnit()
"""


class SourceTests(unittest.TestCase):
    def test_function_bodies_and_transfers(self):
        bodies = rd_armies.function_bodies(STARTUP)
        self.assertEqual(sorted(bodies), ["TEAM_0402_ED", "TEAM_0406_ED"])
        self.assertEqual(rd_armies.transfers_of(bodies["TEAM_0402_ED"]), [(5, 9), (10, 5)])
        self.assertEqual(rd_armies.transfers_of(bodies["TEAM_0406_ED"]), [(5, 10)])

    def test_with_transfers_keeps_the_other_lines(self):
        lines = rd_armies.function_bodies(STARTUP)["TEAM_0402_ED"]
        out = rd_armies._with_transfers(lines, [(5, 8), (9, 5)])
        self.assertEqual(out[:4], ["def TEAM_0402_ED():", "    UnitTransferToForceALL(5, 8)",
                                   "    UnitTransferToForceALL(9, 5)", "    DumpUnit()"])
        self.assertEqual(rd_armies._with_transfers(["def X():"], []), ["def X():", "    pass"])


@unittest.skipUnless(FILES, "set FE10_EXTRACTED_FILES to the files/ folder of an extracted Radiant Dawn disc")
class RetailTests(unittest.TestCase):
    """A scratch project with the disc's main.dol, FE10Data and scripts."""

    def setUp(self):
        from fe_modding.games import Game
        from fe_modding.project import ModProject

        source = Path(FILES)
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.project = ModProject.create(Path(tmp.name), "rd armies", Game.RADIANT_DAWN)
        files = self.project.files_dir
        files.mkdir(parents=True, exist_ok=True)
        shutil.copy(source / "FE10Data.cms", files / "FE10Data.cms")
        shutil.copytree(source / "Scripts", files / "Scripts")
        sys_dir = self.project.extracted_dir / "sys"
        sys_dir.mkdir(exist_ok=True)
        for name in ("main.dol", "boot.bin"):
            shutil.copy(source.parent / "sys" / name, sys_dir / name)
        for path in [*files.rglob("*"), *sys_dir.iterdir()]:
            if path.is_file():
                path.chmod(0o666)

    def _flow(self):
        from fe_modding.game_code.story_flow import open_story_flow
        flow, why = open_story_flow(self.project)
        self.assertIsNotNone(flow, why)
        return flow

    def test_retail_flow_changes_nothing(self):
        plan = rd_armies.plan(self.project, self._flow(), self.project.read_logical("game_data"))
        self.assertTrue(plan.empty, plan)
        self.assertEqual(plan.problems, [])

    def test_changed_armies_rewrite_the_hand_overs(self):
        from fe_modding import script_sources
        from fe_modding.formats import fe10data
        from fe_modding.game_code.rd_story import Army

        flow = self._flow()
        flow.set_army("0402", Army.DIVISION_1)   # Micaiah's army again after 4-P
        flow.set_army("0403", Army.DIVISION_2)
        flow = self._flow()
        plan = rd_armies.plan(self.project, flow, self.project.read_logical("game_data"))
        self.assertEqual(plan.functions, {"TEAM_0401_ED": [], "TEAM_0402_ED": [(5, 8), (9, 5)],
                                          "TEAM_0403_ED": [(5, 9), (8, 5)]})
        self.assertEqual(plan.records, {"C0402": {"unknown_8f": 18, "lord": "PID_MICAIAH"},
                                        "C0403": {"unknown_8f": 19, "lord": "PID_IKE"}})
        rd_armies.apply_scripts(self.project, plan)
        self.project.write_logical("game_data", rd_armies.apply_records(self.project.read_logical("game_data"),
                                                                        plan))
        again = rd_armies.plan(self.project, self._flow(), self.project.read_logical("game_data"))
        self.assertTrue(again.empty, again)
        startup = rd_armies.function_bodies(script_sources.peek(
            self.project, self.project.files_dir / "Scripts" / "startup.cmb"))
        self.assertEqual(rd_armies.transfers_of(startup["TEAM_0402_ED"]), [(5, 8), (9, 5)])
        record = next(r for r in fe10data.read_table(self.project.read_logical("game_data"), "chapter")
                      if r.values["cid"] == "C0403")
        self.assertEqual((record.values["unknown_8f"], record.values["lord"]), (19, "PID_IKE"))

    def test_division_after_the_merge_is_refused(self):
        from fe_modding.game_code.rd_story import Army

        flow = self._flow()
        with self.assertRaises(ValueError):
            flow.set_army("0407b", Army.DIVISION_2)


if __name__ == "__main__":
    unittest.main()
