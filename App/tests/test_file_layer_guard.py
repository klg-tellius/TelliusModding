"""Game files are reached only through ``project.files`` (``fe_modding/game_files.py``).

A module that joins paths onto the extracted folder itself would read the wrong file in the
input/output layout, where a file is in the output or the shared input and never in one folder.
This test fails on any use of those names outside the layer, except in the modules still listed in
:data:`NOT_YET_MOVED`. Moving a module to the layer means taking it off that list; nothing is ever
added to it.
"""

import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

FORBIDDEN = re.compile(r"\b(extracted_dir|files_dir|files_dir_of|originals_dir|logical_path_of)\b|[\"']extracted[\"']")

#: The layer itself and what makes or converts projects.
LAYER = frozenset({
    "fe_modding/game_files.py",
    "fe_modding/vanilla_store.py",
    "fe_modding/project.py",
    "fe_modding/layout_migration.py",
})

#: Tools that read a plain extracted disc given on the command line, not a project.
RETAIL_TREE_TOOLS = frozenset({
    "tools/audit_regional_difficulty.py",
    "tools/build_hub_infinite_action_test.py",
    "tools/manifest_3d_unknowns.py",
    "tools/profile_gs_texture_fields.py",
    "tools/verify_conversations.py",
})

#: Test fixtures that build a layout-1 project from a clean extraction on purpose (copy it into
#: extracted/, snapshot and revert it, read Dolphin run trees).
LAYOUT1_FIXTURES = frozenset({
    "tools/prepare_extended_flag_playtest.py",
    "tools/session_playtest/harness.py",
    "tools/session_playtest/run.py",
    "tools/update_extended_flag_playtest.py",
})

#: Modules not moved to the layer yet. Only ever shrinks.
NOT_YET_MOVED = frozenset()


def _sources():
    for folder in ("fe_modding", "tools"):
        for path in sorted((ROOT / folder).rglob("*.py")):
            yield path.relative_to(ROOT).as_posix(), path
    for name in ("main.py", "patcher_main.py"):
        yield name, ROOT / name


class FileLayerGuardTests(unittest.TestCase):
    def test_game_files_are_reached_through_the_layer(self):
        offenders = []
        for rel, path in _sources():
            if rel in LAYER or rel in RETAIL_TREE_TOOLS or rel in LAYOUT1_FIXTURES or rel in NOT_YET_MOVED:
                continue
            for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
                if FORBIDDEN.search(line.split("#", 1)[0]):
                    offenders.append(f"{rel}:{number}: {line.strip()}")
        self.assertEqual(offenders, [], "use project.files (fe_modding/game_files.py) instead")

    def test_moved_modules_leave_the_list(self):
        still_listed = []
        for rel, path in _sources():
            if rel in NOT_YET_MOVED and not any(FORBIDDEN.search(line.split("#", 1)[0])
                                                for line in path.read_text(encoding="utf-8").splitlines()):
                still_listed.append(rel)
        missing = sorted(NOT_YET_MOVED - {rel for rel, _ in _sources()})
        self.assertEqual(still_listed + missing, [], "take these off NOT_YET_MOVED")


if __name__ == "__main__":
    unittest.main()
