import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fe_modding.game_code import ppc, rd_story


class RetailSequenceTests(unittest.TestCase):
    def test_hidden_part_four_records_are_attached_to_visible_chapter(self):
        expected = list(range(33)) + [35, 38, 41, 44, 47] + list(range(50, 56))
        sequence = []
        chapter = 0
        while chapter is not None:
            sequence.append(chapter)
            chapter = rd_story.retail_next(chapter)
        self.assertEqual(sequence, expected)
        for hidden in (33, 34, 36, 37, 39, 40, 42, 43, 45, 46, 48, 49):
            self.assertIsNone(rd_story.retail_next(hidden))

    def test_retail_armies_keep_main_and_divisions_logically_distinct(self):
        armies = rd_story._retail_armies()
        self.assertEqual(armies[31], rd_story.Army.MAIN)
        self.assertEqual(armies[32], rd_story.Army.DIVISION_1)
        self.assertEqual(armies[35], rd_story.Army.DIVISION_2)
        self.assertEqual(armies[38], rd_story.Army.DIVISION_3)
        self.assertEqual(armies[50], rd_story.Army.MAIN)


class ValidationTests(unittest.TestCase):
    def setUp(self):
        self.story = object.__new__(rd_story.StorySequence)

    def test_inherit_and_division_validation(self):
        steps = [rd_story.ChapterStep(0, "C0000"),
                 rd_story.ChapterStep(1, "C0101", rd_story.Army.DIVISION_1)]
        problems = "\n".join(self.story.validate(steps))
        self.assertIn("inherits an army", problems)
        self.assertIn("before Divide armies", problems)

    def test_divide_initializes_only_division_choices(self):
        steps = [rd_story.ChapterStep(0, "C0000", rd_story.Army.MAIN),
                 rd_story.PartBoundaryStep(1),
                 rd_story.DivideArmiesStep(1),
                 rd_story.ChapterStep(1, "C0101", rd_story.Army.DIVISION_1),
                 rd_story.ChapterStep(2, "C0102", rd_story.Army.MAIN),
                 rd_story.ChapterStep(rd_story.ENDING, "CFINAL", rd_story.Army.MAIN)]
        self.assertEqual(self.story.validate(steps), [])

    def test_structural_step_needs_a_following_chapter(self):
        problems = self.story.validate([rd_story.ChapterStep(0, "C0000", rd_story.Army.MAIN),
                                        rd_story.PartBoundaryStep(1)])
        self.assertTrue(any("followed by a chapter" in problem for problem in problems))

    def test_ending_is_required_last(self):
        problems = self.story.validate([rd_story.ChapterStep(0, "C0000", rd_story.Army.MAIN)])
        self.assertTrue(any("CFINAL" in problem for problem in problems))


class HookTests(unittest.TestCase):
    def test_retail_calls_are_replaced_only_at_confirmed_sites(self):
        edits = rd_story.PATCH.versions[rd_story.RFEE01]
        for site in rd_story._CALLS:
            edit = next(edit for edit in edits if edit.address == site)
            self.assertEqual(edit.original, ppc.bl(site, rd_story._ADVANCE).to_bytes(4, "big"))
            self.assertEqual(edit.patched, ppc.bl(site, rd_story.HOOK).to_bytes(4, "big"))

    def test_custom_range_and_tables_fit_the_cave(self):
        self.assertLessEqual(rd_story.HOOK + len(rd_story._hook()), rd_story.SUCCESSORS)
        self.assertTrue(rd_story.in_cave(rd_story.MAGIC, 4))


if __name__ == "__main__":
    unittest.main()
