"""The app shows its version, read from ``fe_modding.__version__`` (the one source)."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fe_modding import __version__
from fe_modding.gui.app import about_text, window_title


class AppVersionTests(unittest.TestCase):
    def test_window_title_carries_the_version(self):
        self.assertEqual(window_title(), f"Tellius Modding {__version__}")

    def test_window_title_with_a_project(self):
        self.assertEqual(window_title("My mod"), f"My mod - Tellius Modding {__version__}")

    def test_about_text_carries_the_version(self):
        self.assertIn(f"Version {__version__}", about_text())


if __name__ == "__main__":
    unittest.main()
