import unittest
from pathlib import Path

from fe_modding.formats.extended_flags import FlagLayout
from fe_modding.game_code.dol import Dol, DolError
from fe_modding.game_code.extended_flag_runtime import build_core
from fe_modding.game_code.extended_flag_jp_file_save import build_jp_file_save_fragment, WRITER, GUARDS
from fe_modding.game_code.extended_flag_checkpoint import UNIT_ARRAY, ERROR_SETTERS
from tests.ppc_flag_cpu import CPU

RETAIL = Path(__file__).resolve().parents[2] / "research/main_dol/dols/GFEJ01.dol"


class JapaneseFileSaveTests(unittest.TestCase):
    def setUp(self):
        if not RETAIL.exists():
            self.skipTest("retail DOL unavailable")
        self.dol = Dol.open(RETAIL)
        self.core = build_core(self.dol, "GFEJ01", FlagLayout())
        self.image = build_jp_file_save_fragment(self.dol, "GFEJ01", self.core)
        self.cpu = CPU(self.image)
        self.errors = []

    def run_hook(self, name, stops):
        pc = self.image.functions[name]
        error = ERROR_SETTERS["GFEJ01"][0]
        while True:
            pc = self.cpu.run(pc, {*stops, error})
            if pc != error:
                return pc
            self.errors.append(self.cpu.r[3])
            pc = self.cpu.lr
            self.cpu.r[3:13] = [0xCCCCCCCC] * 10

    def test_preflight_capacity_and_three_argument_abi(self):
        for count in (89, 90):
            with self.subTest(count=count):
                self.setUp()
                cpu = self.cpu
                for i in range(count):
                    cpu.write(UNIT_ARRAY["GFEJ01"] + i * 0x280 + 0x188, 0x81200000, 4)
                context, block, parent = 0x81000000, 0x81100000, 0x81001000
                cpu.write(context, block, 4)
                cpu.write(context + 4, 0x12345678, 4)
                for i in range(0x4000):
                    cpu.write(block + i, 0xA5, 1)
                before = dict(cpu.memory)
                cpu.r[3:6] = [context, 2, parent]
                stack = cpu.r[1]
                result = self.run_hook("file_save_guard", {WRITER + 4})
                self.assertEqual(result, WRITER + 4 if count == 89 else CPU.RETURN)
                self.assertEqual(cpu.r[1], stack - (0x30 if count == 89 else 0))
                self.assertEqual(cpu.lr, CPU.RETURN)
                self.assertEqual(self.errors, [] if count == 89 else [0xFFFFFFF7])
                if count == 89:
                    self.assertEqual(cpu.r[3:6], [context, 2, parent])
                self.assertEqual({k: cpu.memory[k] for k in before}, before)

    def test_append_boundary_before_crc_and_child_creation(self):
        for fits in (True, False):
            self.setUp()
            cpu = self.cpu
            cpu.r[31] = 0x81100000
            cpu.r[28:31] = [0x81000000, 2, 0x81001000]
            saved = cpu.r[14:]
            cursor = cpu.r[31] + 0x4000 - (188 if fits else 187)
            cpu.write(cpu.r[1] + 8, cpu.r[31] + 0xB8, 4)
            cpu.write(cpu.r[1] + 12, cursor, 4)
            result = self.run_hook("file_save_append", {WRITER + 0x300, WRITER + 0x354})
            self.assertEqual(result, WRITER + (0x300 if fits else 0x354))
            self.assertEqual(cpu.r[14:], saved)
            self.assertEqual(cpu.read(cpu.r[1] + 12, 4), cursor + (188 if fits else 0))
            expected = bytes(cpu.read(self.image.record_address + i, 1) for i in range(188))
            self.assertEqual(bytes(cpu.read(cursor + i, 1) for i in range(188)), expected if fits else bytes(188))
            self.assertEqual(self.errors, [] if fits else [0xFFFFFFF7])

    def test_retail_menu_dispatches_failure_dialog_instead_of_success(self):
        cpu = self.cpu
        for at, size in ((0x801D2228, 0x18), (0x801D5520, 0x60)):
            for i, byte in enumerate(self.dol.read(at, size)):
                cpu.write(at + i, byte, 1)
        for status in (0, 0xFFFFFFF7):
            cpu.r[0] = 0x268
            cpu.r[31], cpu.r[30] = 0x81100000, 0x81000000
            self.assertEqual(cpu.run(0x801D2228, {0x801D5520}), 0x801D5520)
            pc = cpu.run(0x801D5520, {0x800E9120})
            self.assertEqual(pc, 0x800E9120)
            cpu.r[3] = status
            pc = cpu.lr
            dialogs = []
            while True:
                pc = cpu.run(pc, {0x801D6234, 0x80144F04, 0x801D9C2C})
                if pc == 0x801D6234:
                    break
                if pc == 0x801D9C2C:
                    dialogs.append((cpu.r[3], cpu.r[9]))
                pc = cpu.lr
                cpu.r[3:13] = [0xCCCCCCCC] * 10
            self.assertEqual(cpu.read(0x81100000, 4), 0x269 if status == 0 else 0x25D)
            self.assertEqual(dialogs, [] if status == 0 else [(0x8027A1CE, 0x81000000)])
        self.assertEqual(self.dol.read(0x8027A1CE, 12), b"FM_ERR_SAVE\0")

    def test_duplicate_and_modified_caller_rejected_without_mutation(self):
        original = bytes(self.dol.data)
        with self.assertRaises(ValueError):
            build_jp_file_save_fragment(self.dol, "GFEJ01", self.image)
        self.assertEqual(bytes(self.dol.data), original)
        for at, _, _ in GUARDS:
            dol = Dol(original)
            dol.write(at, bytes(4))
            with self.assertRaises(DolError):
                build_jp_file_save_fragment(dol, "GFEJ01", self.core)


if __name__ == "__main__":
    unittest.main()
