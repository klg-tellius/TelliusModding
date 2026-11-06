"""Radiant Dawn chapter titles: the parts the game reads besides MCTnnnn."""

import unittest

from fe_modding import chapters_fe10


class TitlePartsTests(unittest.TestCase):
    TEMPLATE = {"_0": "Part I", "_0_2": "I", "_1": "Ch.2", "_2": "The Dispossessed", "_3": "Ch.2"}

    def test_retail_forms(self):
        self.assertEqual(chapters_fe10.title_parts("I:2-The Dispossessed", {}),
                         {"_0": "Part I", "_0_2": "I", "_1": "Ch.2", "_2": "The Dispossessed", "_3": "Ch.2"})
        self.assertEqual(chapters_fe10.title_parts("I: Prologue-Under Gray Skies", {}),
                         {"_0": "Part I", "_0_2": "I", "_1": "Prologue", "_2": "Under Gray Skies", "_3": "Prologue"})

    def test_a_plain_title_takes_the_template_part(self):
        for title in ("Hub", "Mid-Year Hub"):
            self.assertEqual(chapters_fe10.title_parts(title, self.TEMPLATE),
                             {"_0": "Part I", "_0_2": "I", "_1": "", "_2": title, "_3": ""})


if __name__ == "__main__":
    unittest.main()
