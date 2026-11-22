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
    PLAYER_CONTROLS, _CURSOR_HINT, _DISPATCH_SITES, _NEXT_UNDONE, _PARTY, _RETAIL, _SITES,
    _UNIT_CATEGORY, value_address,
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


def _controls(version: str) -> tuple[dict[int, int], list[int]]:
    """(every word of the patch, the cave addresses in order: list, army, category, hint, dispatch)."""
    words, caves = {}, []
    for edit in PLAYER_CONTROLS.versions[version]:
        for i in range(0, len(edit.patched), 4):
            words[edit.address + i] = int.from_bytes(edit.patched[i:i + 4], "big")
        if edit.address >= CAVE_ADDRESS:
            caves.append(edit.address)
    return words, caves


class PlayerControlsTests(unittest.TestCase):
    def test_sites_branch_to_their_caves(self):
        for version in _SITES:
            words, caves = _controls(version)
            sites = (_NEXT_UNDONE[version] + 8, _NEXT_UNDONE[version] + 0x2C, _UNIT_CATEGORY[version] + 0xD8,
                     _CURSOR_HINT[version], _DISPATCH_SITES[version] + 0x1C)
            for site, cave in zip(sites, caves):
                cpu = MiniPPC(words, {})
                self.assertEqual(cpu.run(site, {cave}), cave, (version, hex(site)))

    def test_next_unit_search_walks_the_current_army(self):
        for version in _SITES:
            words, caves = _controls(version)
            party, search, table = _PARTY[version], _NEXT_UNDONE[version], 0x802CA264
            memory = {party + 0x11: 3}
            memory.update({table + 0x24 + i: b for i, b in enumerate((0x80, 0x12, 0x34, 0x56))})
            cpu = MiniPPC(words, memory)
            cpu.r[4] = table
            self.assertEqual(cpu.run(caves[0], {search + 0xC}), search + 0xC)
            self.assertEqual(cpu.r[4], 0x80123456)
            for army, same in ((3, True), (0, False)):
                cpu = MiniPPC(words, {party + 0x11: 3})
                cpu.r[0] = army
                self.assertEqual(cpu.run(caves[1], {search + 0x30}), search + 0x30)
                self.assertEqual(cpu.cr0[2], same)

    def test_blue_units_act_only_in_the_player_phase(self):
        for version in _SITES:
            words, caves = _controls(version)
            party, category = _PARTY[version], _UNIT_CATEGORY[version]
            done, acts = category + 0xF0, category + 0xDC
            for army, phase, expected in ((0, 0, acts), (0, 3, done), (0, 1, done), (3, 3, acts)):
                cpu = MiniPPC(words, {party + 0x11: phase})
                cpu.r[29], cpu.r[30], cpu.r[31] = 0x81000000, army, party
                self.assertEqual(cpu.run(caves[2], {done, acts}), expected, (version, army, phase))
                if expected == done:
                    self.assertEqual(cpu.r[3], 3)

    def test_cursor_hint_of_a_blue_unit(self):
        for version in _SITES:
            words, caves = _controls(version)
            party, end = _PARTY[version], _CURSOR_HINT[version] + 0x68
            for phase, hint in ((0, 3), (3, 4)):
                cpu = MiniPPC(words, {party + 0x11: phase})
                self.assertEqual(cpu.run(caves[3], {end}), end)
                self.assertEqual(cpu.memory[party + 0x51D], hint)

    def test_partner_phase_played_by_the_player_starts_no_computer_phase(self):
        for version in _SITES:
            words, caves = _controls(version)
            dispatch = _DISPATCH_SITES[version]
            stop, retail = dispatch + 0x5C, dispatch + 0x20
            for controller, expected in ((1, stop), (2, retail)):
                cpu = MiniPPC(words, {PARTY + 0x17: controller})
                cpu.r[30], cpu.r[3] = PARTY + 0x14, 0x80330000
                self.assertEqual(cpu.run(caves[4], {stop, retail}), expected)

    def test_tunables_require_it(self):
        for tunable in PHASE_TUNABLES:
            self.assertIn(PLAYER_CONTROLS, tunable.requires)


class RetailSiteTests(unittest.TestCase):
    def test_sites_hold_the_four_stores(self):
        for version, site in _SITES.items():
            path = RETAIL_DIR / f"{version}.dol"
            if not path.is_file():
                self.skipTest("no retail DOL")
            dol = Dol(path.read_bytes())
            self.assertEqual(tuple(dol.words(site, 4)), _RETAIL, version)

    def test_player_controls_sites_hold_retail_code(self):
        for version in _SITES:
            path = RETAIL_DIR / f"{version}.dol"
            if not path.is_file():
                self.skipTest("no retail DOL")
            dol = Dol(path.read_bytes())
            for edit in PLAYER_CONTROLS.versions[version]:
                if edit.address < CAVE_ADDRESS:
                    self.assertEqual(dol.read(edit.address, 4), edit.original, (version, hex(edit.address)))
            party = _PARTY[version]       # the lis/addi pair of the unit category routine
            lis, addi = dol.words(_UNIT_CATEGORY[version] + 0x4C, 2)
            self.assertEqual(((lis & 0xFFFF) << 16) + ((addi & 0xFFFF) ^ 0x8000) - 0x8000, party, version)


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
        self.assertEqual(editor.status(PLAYER_CONTROLS).state, State.APPLIED)
        self.assertEqual(editor.dol.read(value_address(1), 1), b"\x01")
        self.assertEqual(editor.status(PHASE_TUNABLES[2]).value, 2)
        editor.reset(enemy)
        self.assertEqual((self.root / "sys" / "main.dol").read_bytes(), self.retail)


if __name__ == "__main__":
    unittest.main()
