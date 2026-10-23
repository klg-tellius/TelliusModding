import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fe_modding.game_code import entries  # noqa: F401  (registers every entry)
from fe_modding.game_code.catalog import CAVE_ADDRESS, State
from fe_modding.game_code.dol import Dol
from fe_modding.game_code.phase_control import (
    ARMIES, CHOICES, DEFAULTS, PHASE_HOOK, PHASE_ROUTINE, PHASE_TUNABLES, PLAYER_AI_ROUTINE,
    _DISPATCH_SITES, _RETAIL, _SITES, value_address,
)
from test_chapter_flow import PARTY, RETAIL_DIR, MiniPPC


def _routine(version: str) -> dict[int, int]:
    words = {}
    for edit in PHASE_HOOK.versions[version]:
        if edit.address >= CAVE_ADDRESS:
            for i in range(0, len(edit.patched), 4):
                words[edit.address + i] = int.from_bytes(edit.patched[i:i + 4], "big")
    return words


class RoutineTests(unittest.TestCase):
    def test_routine_writes_the_four_controllers(self):
        cpu = MiniPPC(_routine("GFEE01"), {})
        cpu.r[31] = PARTY
        self.assertEqual(cpu.run(PHASE_ROUTINE, set()), -1)
        self.assertEqual([cpu.memory[PARTY + 0x14 + i] for i in range(4)], list(DEFAULTS))

    def test_each_value_is_the_low_byte_of_its_li(self):
        code = _routine("GFEE01")
        for army in range(len(ARMIES)):
            word = code[value_address(army) - 3]
            self.assertEqual(word >> 16, 0x3980)                # li r12,...
            self.assertEqual(word & 0xFF, DEFAULTS[army])

    def test_choices_cover_the_range(self):
        for tunable in PHASE_TUNABLES:
            self.assertEqual(len(tunable.choices), tunable.maximum - tunable.minimum + 1)
        self.assertEqual(CHOICES[1], "Player")

    def test_player_army_dispatches_to_ai_only_for_computer_control(self):
        base = PARTY + 0x14
        dispatch = _DISPATCH_SITES["GFEE01"]
        for controller, target in ((1, dispatch + 0x10), (2, dispatch + 0x54)):
            cpu = MiniPPC(_routine("GFEE01"), {base: controller})
            cpu.r[30] = base
            self.assertEqual(cpu.run(PLAYER_AI_ROUTINE, {dispatch + 0x10, dispatch + 0x54}), target)


class RetailSiteTests(unittest.TestCase):
    def test_sites_hold_the_four_stores(self):
        for version, site in _SITES.items():
            path = RETAIL_DIR / f"{version}.dol"
            if not path.is_file():
                self.skipTest("no retail DOL")
            dol = Dol(path.read_bytes())
            self.assertEqual(tuple(dol.words(site, 4)), _RETAIL, version)


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

    def _editor(self):
        from fe_modding.game_code.editor import CodeEditor
        return CodeEditor(self.root)

    def test_player_enemy_phase_then_reset_restores_retail(self):
        editor = self._editor()
        enemy = PHASE_TUNABLES[1]
        self.assertEqual(editor.status(enemy).state, State.ORIGINAL)
        self.assertEqual(editor.set_value(enemy, 1), "Enemy phase: Computer -> Player")
        editor = self._editor()
        self.assertEqual(editor.status(enemy).state, State.CUSTOM)
        self.assertEqual(editor.status(enemy).value, 1)
        self.assertEqual(editor.status(PHASE_HOOK).state, State.APPLIED)
        self.assertEqual(editor.dol.read(value_address(1), 1), b"\x01")
        self.assertEqual(editor.status(PHASE_TUNABLES[2]).value, 2)
        editor.reset(enemy)
        self.assertEqual((self.root / "sys" / "main.dol").read_bytes(), self.retail)


if __name__ == "__main__":
    unittest.main()
