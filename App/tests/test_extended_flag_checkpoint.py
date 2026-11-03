import unittest
from pathlib import Path

from fe_modding.formats.extended_flags import FlagLayout
from fe_modding.game_code.dol import Dol, DolError
from fe_modding.game_code.extended_flag_runtime import build_core
from fe_modding.game_code.extended_flag_file_save import build_file_save_fragment
from fe_modding.game_code.extended_flag_checkpoint import (
    build_checkpoint_fragment, SITES, UNIT_ARRAY, ERROR_SETTERS,
)
from tests.ppc_flag_cpu import CPU

RETAIL = Path(__file__).resolve().parents[2] / "research/main_dol/dols"


class CheckpointTests(unittest.TestCase):
    def setup_region(self, code):
        if not (RETAIL / f"{code}.dol").exists():
            self.skipTest("retail DOL unavailable")
        self.code = code
        self.dol = Dol.open(RETAIL / f"{code}.dol")
        self.core = build_core(self.dol, code, FlagLayout())
        self.image = build_checkpoint_fragment(self.dol, code, self.core)
        self.cpu = CPU(self.image)
        self.errors = []

    def run_native(self, name, stops):
        error = ERROR_SETTERS[self.code][0]
        pc = self.image.functions[name]
        while True:
            pc = self.cpu.run(pc, {*stops, error})
            if pc != error:
                return pc
            self.errors.append(self.cpu.r[3])
            pc = self.cpu.lr
            self.cpu.r[3:13] = [0xCCCCCCCC] * 10

    def test_capacity_boundary_and_refusal_without_scheduling_write(self):
        for code in SITES:
            for count in (147, 148):
                with self.subTest(code=code, count=count):
                    self.setup_region(code)
                    cpu = self.cpu
                    for i in range(count):
                        cpu.write(UNIT_ARRAY[code] + i * 0x280 + 0x188, 0x81200000, 4)
                    context, parent, block = 0x81000000, 0x81001000, 0x81100000
                    cpu.write(context, block, 4)
                    cpu.write(context + 4, 0x12345678, 4)
                    for i in range(0x6000):
                        cpu.write(block + i, 0xA5, 1)
                    before = dict(cpu.memory)
                    cpu.r[3:5] = [context, parent]
                    stack = cpu.r[1]
                    writer = SITES[code][0]
                    result = self.run_native("checkpoint_guard", {writer + 4})
                    if count == 147:
                        self.assertEqual(result, writer + 4)
                        self.assertEqual(cpu.r[3:5], [context, parent])
                        self.assertEqual(cpu.r[1], stack - (0x30 if code == "GFEJ01" else 0x40))
                        self.assertEqual(self.errors, [])
                    else:
                        self.assertEqual(result, CPU.RETURN)
                        self.assertEqual(cpu.r[1], stack)
                        self.assertEqual(self.errors, [0xFFFFFFF7])
                    self.assertEqual(cpu.lr, CPU.RETURN)
                    self.assertEqual({k: cpu.memory[k] for k in before}, before)

    def test_append_uses_regional_block_register_and_failure_epilogue(self):
        for code in SITES:
            for fits in (True, False):
                with self.subTest(code=code, fits=fits):
                    self.setup_region(code)
                    cpu = self.cpu
                    writer, _, _, after, epilogue, block_reg = SITES[code]
                    cpu.r[1] -= 0x30 if code == "GFEJ01" else 0x40
                    block = 0x81100000
                    for r in range(14, 32):
                        cpu.r[r] = 0x55550000 + r
                    cpu.r[block_reg] = block
                    saved = cpu.r[14:]
                    cursor = block + 0x6000 - (188 if fits else 187)
                    cpu.write(cpu.r[1] + 8, block + 0xB8, 4)
                    cpu.write(cpu.r[1] + 12, cursor, 4)
                    stops = {writer + after + 4, writer + epilogue}
                    self.assertEqual(self.run_native("checkpoint_append", stops),
                                     writer + (after + 4 if fits else epilogue))
                    self.assertEqual(cpu.r[14:], saved)
                    self.assertEqual(cpu.read(cpu.r[1] + 12, 4), cursor + (188 if fits else 0))
                    if fits:
                        self.assertEqual(bytes(cpu.read(cursor + i, 1) for i in range(188)),
                                         bytes(cpu.read(self.image.record_address + i, 1) for i in range(188)))
                        self.assertEqual(self.errors, [])
                    else:
                        self.assertEqual(cpu.read(cursor, 1), 0)
                        self.assertEqual(self.errors, [0xFFFFFFF7])

    def test_fragments_compose_without_mutating_inputs_and_reject_conflicts(self):
        for code in SITES:
            self.setup_region(code)
            before = bytes(self.dol.data)
            if code != "GFEJ01":
                file_image = build_file_save_fragment(self.dol, code, self.core)
                combined = build_checkpoint_fragment(self.dol, code, file_image)
                self.assertIn("file_save_guard", combined.functions)
                self.assertIn("checkpoint_guard", combined.functions)
                self.assertEqual(len(combined.data), len(self.core.data))
            self.assertEqual(bytes(self.dol.data), before)
            with self.assertRaises(ValueError):
                build_checkpoint_fragment(self.dol, code, self.image)
            self.dol.write(SITES[code][0] + 8, bytes(4))
            with self.assertRaises(DolError):
                build_checkpoint_fragment(self.dol, code, self.core)


if __name__ == "__main__":
    unittest.main()
