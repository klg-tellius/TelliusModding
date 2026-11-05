"""Radiant Dawn's staff credits: Mess/<lang>ending.m lines and StaffRollData.bin timings."""

import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fe_modding.formats import fe10_staffroll as fs
from fe_modding.game_profile import PATH_OF_RADIANCE_PROFILE, RADIANT_DAWN_PROFILE, STAFF_CREDITS
from fe_modding.games import Game

FE10 = os.environ.get("FE10_EXTRACTED_FILES")


class ProfileTests(unittest.TestCase):
    def test_both_games_have_staff_credits(self):
        self.assertTrue(PATH_OF_RADIANCE_PROFILE.supports(STAFF_CREDITS))
        self.assertTrue(RADIANT_DAWN_PROFILE.supports(STAFF_CREDITS))


@unittest.skipUnless(FE10, "set FE10_EXTRACTED_FILES to an extracted Radiant Dawn files/ directory")
class RdTests(unittest.TestCase):
    def _raw(self, name):
        return (Path(FE10) / "Mess" / name).read_bytes()

    def test_both_lists_read_and_rebuild_unchanged(self):
        for name, count in (("e_ending.m", 358), ("ending.m", 341)):
            roll = fs.read_rd_staffroll(self._raw(name))
            self.assertEqual((len(roll.lines), roll.title, roll.others), (count, "Staff Credit", []))
            self.assertEqual(roll.lines[0], ("Producer", "", "Thoru Narihiro"))
            self.assertEqual(roll.copyright[2], "reserved by NINTENDO")
            self.assertEqual(fs.build_rd_staffroll(roll), self._raw(name))

    def test_edited_lines_rebuild_with_the_new_count(self):
        roll = fs.read_rd_staffroll(self._raw("e_ending.m"))
        roll.lines.insert(1, ("Modder", "", "Someone"))
        roll.lines.append(("", "Thanks", ""))
        roll.title = "Credits"
        again = fs.read_rd_staffroll(fs.build_rd_staffroll(roll))
        self.assertEqual((len(again.lines), again.lines[1], again.lines[-1], again.title),
                         (360, ("Modder", "", "Someone"), ("", "Thanks", ""), "Credits"))
        roll.lines[0] = ("Producer", "", "名前" + "€")  # the euro sign has no Shift-JIS code
        with self.assertRaises(fs.Fe10StaffRollError):
            fs.build_rd_staffroll(roll)

    def test_timings(self):
        data = (Path(FE10) / "StaffRollData.bin").read_bytes()
        timings = fs.read_timings(data)
        self.assertEqual((timings["LBL_STAFFROLL_SCROLLSPEED"], timings["LBL_STAFFROLL_SCROLLWAIT_END"],
                          timings["LBL_STAFFROLL_SOUND1A"]), (0.5, 3000, 313))
        out = fs.set_timing(data, "LBL_STAFFROLL_SCROLLSPEED", 1.25)
        out = fs.set_timing(out, "LBL_STAFFROLL_SCROLLWAIT_END", 5000)
        after = fs.read_timings(out)
        self.assertEqual((after["LBL_STAFFROLL_SCROLLSPEED"], after["LBL_STAFFROLL_SCROLLWAIT_END"]), (1.25, 5000))
        self.assertEqual(len(out), len(data))
        with self.assertRaises(fs.Fe10StaffRollError):
            fs.set_timing(data, "LBL_STAFFROLL_SCROLLWAIT_END", -1)

    def test_the_page_saves_lines_and_timings(self):
        import tkinter as tk
        from fe_modding.gui.staffroll_editor import Fe10StaffRollEditor, staff_credits_panel
        from fe_modding.project import ModProject
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        project = ModProject.create(Path(tmp.name), "credits", Game.RADIANT_DAWN)
        files = project.extracted_dir / "files"
        for rel in ("Mess/e_ending.m", "Mess/ending.m", "StaffRollData.bin"):
            (files / rel).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy(Path(FE10) / rel, files / rel)
            (files / rel).chmod(0o666)
        try:
            root = tk.Tk()
        except tk.TclError:
            self.skipTest("no display")
        self.addCleanup(root.destroy)
        log = []
        page = staff_credits_panel(root, project, type("Log", (), {"append": lambda s, *a: log.append(a)})())
        self.assertIsInstance(page, Fe10StaffRollEditor)
        self.assertEqual((page._path.name, len(page._roll.lines)), ("e_ending.m", 358))
        page._tree.selection_set("0")
        page._on_select()
        page._vars[2].set("A. Modder")
        page._apply()
        page._timing_vars["LBL_STAFFROLL_SCROLLSPEED"].set("0.75")
        self.assertTrue(page.save())
        roll = fs.read_rd_staffroll((files / "Mess" / "e_ending.m").read_bytes())
        self.assertEqual(roll.lines[0], ("Producer", "", "A. Modder"))
        self.assertEqual(fs.read_timings((files / "StaffRollData.bin").read_bytes())["LBL_STAFFROLL_SCROLLSPEED"], 0.75)
        page._language.set("Japanese")
        page._switch_language()
        self.assertEqual((page._path.name, len(page._roll.lines)), ("ending.m", 341))


if __name__ == "__main__":
    unittest.main()
