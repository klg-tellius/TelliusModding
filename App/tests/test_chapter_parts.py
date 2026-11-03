import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fe_modding.game_code import chapter_parts
from fe_modding.game_code.catalog import CAVE_ADDRESS, State
from fe_modding.game_code.chapter_parts import HISTORY_TEST, PART_LIST, PART_TEST, PARTS_PATCH
from test_chapter_flow import PARTY, RETAIL_DIR, MiniPPC

HISTORY = PARTY + chapter_parts.HISTORY_OFFSET


def _code(version: str) -> dict[int, int]:
    words = {}
    for edit in PARTS_PATCH.versions[version]:
        if edit.address >= CAVE_ADDRESS:
            for i in range(0, len(edit.patched), 4):
                words[edit.address + i] = int.from_bytes(edit.patched[i:i + 4], "big")
    return words


class StubTests(unittest.TestCase):
    def setUp(self):
        self.code = _code("GFEE01")

    def _carries_on(self, chapter: int, listed: list[int]) -> bool:
        cpu = MiniPPC(self.code, {PART_LIST + i: c for i, c in enumerate(listed)})
        cpu.r[0] = chapter
        self.assertEqual(cpu.run(PART_TEST, set()), -1)
        self.assertEqual(cpu.r[0], chapter)                 # the caller's r0 is kept
        return cpu.cr0[2]

    def _last_continued(self, entries: list[tuple[int, int, int]]) -> bool:
        memory = {}
        for i, (chapter, flag, turns) in enumerate(entries):
            memory[HISTORY + 8 * i] = chapter
            memory[HISTORY + 8 * i + 1] = flag
            memory[HISTORY + 8 * i + 2], memory[HISTORY + 8 * i + 3] = turns >> 8, turns & 0xFF
        cpu = MiniPPC(self.code, memory)
        cpu.r[0], cpu.r[3] = 29, PARTY
        self.assertEqual(cpu.run(HISTORY_TEST, set()), -1)
        self.assertEqual((cpu.r[0], cpu.r[3]), (29, PARTY))  # the support site still needs both
        return cpu.cr0[2]

    def test_chapter_28_and_listed_chapters_carry_on(self):
        self.assertTrue(self._carries_on(28, []))
        self.assertFalse(self._carries_on(12, []))
        self.assertTrue(self._carries_on(12, [40, 12]))
        self.assertFalse(self._carries_on(13, [40, 12]))

    def test_the_last_clear_decides(self):
        self.assertFalse(self._last_continued([]))
        self.assertTrue(self._last_continued([(27, 0, 9), (28, 1, 12)]))
        self.assertFalse(self._last_continued([(28, 1, 12), (29, 0, 7)]))
        self.assertTrue(self._last_continued([(c, c == 40, 5) for c in range(1, 41)]))   # all 40 slots used


class EditorTests(unittest.TestCase):
    def setUp(self):
        path = RETAIL_DIR / "GFEE01.dol"
        if not path.is_file():
            self.skipTest("no retail DOL")
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        (self.root / "sys").mkdir()
        shutil.copy(path, self.root / "sys" / "main.dol")
        (self.root / "sys" / "boot.bin").write_bytes(b"GFEE01\x00\x00" + bytes(0x438))
        self.retail = path.read_bytes()

    def _parts(self):
        from fe_modding.game_code.editor import CodeEditor
        return chapter_parts.ChapterParts(CodeEditor(self.root))

    def test_set_then_clear_restores_retail(self):
        parts = self._parts()
        self.assertEqual(parts.continued(), {28})
        parts.set_continued(12, True)
        parts.set_continued(40, True)
        reopened = self._parts()
        self.assertEqual(reopened.status.state, State.APPLIED)
        self.assertEqual(reopened.continued(), {12, 28, 40})
        self.assertEqual(reopened.editor.modified_entries(), [])     # internal hook
        reopened.set_continued(12, False)
        reopened.set_continued(40, False)
        self.assertEqual(self._parts().continued(), {28})
        self.assertEqual((self.root / "sys" / "main.dol").read_bytes(), self.retail)

    def test_28_and_the_ending_are_refused(self):
        parts = self._parts()
        with self.assertRaises(ValueError):
            parts.set_continued(28, False)
        with self.assertRaises(ValueError):
            parts.set_continued(32, True)


if __name__ == "__main__":
    unittest.main()
