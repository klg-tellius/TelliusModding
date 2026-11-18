"""The chapter sweep's script edits (tools/chapter_sweep/build.py)."""
import unittest

from tools.chapter_sweep.build import STORY, auto_win_source

MULTIPART = '''@on_complete(flag="goal1")
def End1():
    Complete18(1)

@on_complete(flag="goal2")
def End2():
    Complete18(2)

@on_complete(flag="gf_complete")
def EndAll():
    pass

def Opening18_2():
    set("part2")

def Opening18_3():
    set("part3")
'''


class AutoWinTest(unittest.TestCase):
    def test_single_part_wins_before_the_enemy_phase(self):
        block = auto_win_source("def Startup():\n    pass\n", "05")
        self.assertIn('@before_phase(turn_from=1, turn_to=1, phase="enemy")', block)
        self.assertIn("def SweepWinAfterPlayerTurnOne():", block)
        self.assertIn('    set("gf_complete")', block)
        self.assertNotIn("XFT", block)

    def test_on_phase_trigger_kept_on_request(self):
        block = auto_win_source("", "0101", trigger="on_phase")
        self.assertIn('@on_phase(turn_from=1, turn_to=1, phase="enemy")', block)

    def test_multipart_chapter_wins_the_current_part(self):
        block = auto_win_source(MULTIPART, "18")
        self.assertIn('if get("part3"):\n        set("gf_complete")', block)
        self.assertIn('elif get("part2"):\n        set("goal2")', block)
        self.assertIn('else:\n        set("goal1")', block)

    def test_story_scripts_only(self):
        por = [n for n in ("C00", "C01", "C31", "C80", "C96") if STORY["por"].match(n)]
        rd = [n for n in ("C0000", "C0101", "C0407e", "CFINAL", "T01") if STORY["rd"].match(n)]
        self.assertEqual(por, ["C01", "C31"])
        self.assertEqual(rd, ["C0101", "C0407e"])


if __name__ == "__main__":
    unittest.main()
