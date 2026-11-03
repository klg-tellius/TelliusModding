from __future__ import annotations

import contextlib
import io
import sys
import unittest
from pathlib import Path


TOOLS = Path(__file__).resolve().parents[1] / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

import census_runtime_state as census  # noqa: E402


class NameServiceTests(unittest.TestCase):
    def test_unnamed_code_has_no_service(self) -> None:
        self.assertIsNone(census.name_service("FUN_800c47e8"))
        self.assertIsNone(census.name_service("lib_800c5a48"))

    def test_domain_words_beat_infrastructure_words(self) -> None:
        self.assertEqual(census.name_service("script_UnitMoveDir_handler"), "units")
        self.assertEqual(census.name_service("draw_map_grid_overlay"), "map")

    def test_infrastructure_priority_is_fixed(self) -> None:
        self.assertEqual(census.name_service("kaneko_debug_log_menu_entry"), "debug")
        self.assertEqual(census.name_service("kaneko_widget_construct"), "ui")

    def test_domain_ties_go_to_the_first_word(self) -> None:
        self.assertEqual(census.name_service("play_sound_texture"), "audio")
        self.assertEqual(census.name_service("draw_texture_sound"), "render")


class HeapScanTests(unittest.TestCase):
    @unittest.skipUnless(census.DEFAULT_DOL.is_file(), "US DOL not extracted")
    def test_us_process_scripts_open_and_close_every_heap(self) -> None:
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            census.heaps(census.DEFAULT_DOL)
        lines = out.getvalue().split("Native heap scopes:")[0].splitlines()
        creates = [line for line in lines if " create " in line]
        pops = [line for line in lines if line.rstrip().endswith("pop")]
        self.assertEqual(len(creates), 13)
        self.assertEqual(len(creates), len(pops))
        names = {line.split()[2] for line in creates}
        self.assertEqual(names, {"TITLE", "FILEMENU", "TrialMenu", "JOYBOOT",
                                 "SoundRoom", "CC", "MovieRoom", "IllustRoom"})


if __name__ == "__main__":
    unittest.main()
