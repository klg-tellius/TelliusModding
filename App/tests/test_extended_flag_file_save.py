import unittest
from pathlib import Path

from fe_modding.formats.extended_flags import FlagLayout
from fe_modding.game_code.dol import Dol, DolError
from fe_modding.game_code.extended_flag_runtime import build_core
from fe_modding.game_code.extended_flag_file_save import build_file_save_fragment, SITES, UNIT_ARRAY
from tests.ppc_flag_cpu import CPU

RETAIL = Path(__file__).resolve().parents[2] / "research/main_dol/dols"


class NativeFileSaveTests(unittest.TestCase):
    def setup_region(self, region):
        if not (RETAIL / f"{region}.dol").exists():
            self.skipTest("retail DOL unavailable")
        self.region = region
        self.dol = Dol.open(RETAIL / f"{region}.dol")
        self.core = build_core(self.dol, region, FlagLayout())
        self.image = build_file_save_fragment(self.dol, region, self.core)
        self.cpu = CPU(self.image)
        self.writer = SITES[region]["writer"][0]
        self.process = 0x81000000
        self.context = 0x81001000
        self.block = 0x81100000
        self.calls = []

    def run_with_errors(self, at, stops=()):
        setter = SITES[self.region]["set_error"][0]
        branch = SITES[self.region]["error_branch"][0]
        while True:
            at = self.cpu.run(at, {*stops, setter, branch})
            if at not in (setter, branch):
                return at
            self.calls.append((at, self.cpu.r[3]))
            at = self.cpu.lr
            # External helpers are already body-hash guarded. Model their ABI
            # and clobber volatile registers to exercise caller preservation.
            self.cpu.r[3:13] = [0xCCCCCCCC] * 10

    def test_oversize_refusal_precedes_any_target_write(self):
        for region in SITES:
            with self.subTest(region=region):
                self.setup_region(region)
                for i in range(90):
                    self.cpu.write(UNIT_ARRAY[region] + i * 0x280 + 0x188, 0x81200000, 4)
                self.cpu.write(self.context, self.block, 4)
                self.cpu.write(self.context + 4, 0x12345678, 4)
                self.cpu.write(self.process + 0x54, 0x87654321, 4)
                for i in range(0x4000):
                    self.cpu.write(self.block + i, 0xA5, 1)
                before = dict(self.cpu.memory)
                self.cpu.r[3:5] = [self.context, self.process]
                stack = self.cpu.r[1]
                self.assertEqual(self.run_with_errors(self.image.functions["file_save_guard"], {self.writer + 4}), CPU.RETURN)
                self.assertEqual(self.cpu.r[1], stack)
                self.assertEqual(self.calls, [(SITES[region]["set_error"][0], 0xFFFFFFF7),
                                             (SITES[region]["error_branch"][0], self.process)])
                self.assertEqual({k: self.cpu.memory[k] for k in before}, before)

    def test_guard_preserves_arguments_and_displaced_stack_instruction(self):
        for region in SITES:
            with self.subTest(region=region):
                self.setup_region(region)
                self.cpu.r[3:5] = [self.context, self.process]
                stack = self.cpu.r[1]
                self.assertEqual(self.run_with_errors(self.image.functions["file_save_guard"], {self.writer + 4}), self.writer + 4)
                self.assertEqual(self.cpu.r[3:5], [self.context, self.process])
                self.assertEqual(self.cpu.r[1], stack - 0x30)
                self.assertEqual(self.cpu.lr, CPU.RETURN)
                self.assertEqual(self.calls, [])

    def test_append_commits_before_finalization_or_takes_error_epilogue(self):
        for region in SITES:
            for fits in (True, False):
                with self.subTest(region=region, fits=fits):
                    self.setup_region(region)
                    cpu = self.cpu
                    cpu.r[1] -= 0x30
                    cpu.r[29], cpu.r[31] = self.process, self.block
                    cpu.write(cpu.r[1] + 0x34, CPU.RETURN, 4)
                    cursor = self.block + 0x4000 - (188 if fits else 187)
                    cpu.write(cpu.r[1] + 8, self.block + 0xB8, 4)
                    cpu.write(cpu.r[1] + 12, cursor, 4)
                    before_state = bytes(cpu.read(self.image.record_address + i, 1) for i in range(188))
                    stops = {self.writer + 0x2FC, self.writer + 0x340}
                    result = self.run_with_errors(self.image.functions["file_save_append"], stops)
                    self.assertEqual(result, self.writer + (0x2FC if fits else 0x340))
                    self.assertEqual(cpu.r[29], self.process)
                    self.assertEqual(cpu.r[31], self.block)
                    self.assertEqual(cpu.read(cpu.r[1] + 0x34, 4), CPU.RETURN)
                    if fits:
                        self.assertEqual(bytes(cpu.read(cursor + i, 1) for i in range(188)), before_state)
                        self.assertEqual(cpu.read(cpu.r[1] + 12, 4), cursor + 188)
                        self.assertEqual(self.calls, [])
                    else:
                        self.assertEqual(cpu.read(cpu.r[1] + 12, 4), cursor)
                        self.assertEqual(cpu.read(cursor, 1), 0)
                        self.assertEqual(len(self.calls), 2)

    def test_rejects_conflicting_code_wrong_region_and_duplicate_fragments(self):
        self.setup_region("GFEE01")
        before = bytes(self.dol.data)
        build_file_save_fragment(self.dol, self.region, self.core)
        self.assertEqual(bytes(self.dol.data), before)
        with self.assertRaises(ValueError):
            build_file_save_fragment(self.dol, "GFEJ01", self.core)
        with self.assertRaises(ValueError):
            build_file_save_fragment(self.dol, self.region, self.image)
        process = SITES[self.region]["process"][0]
        self.dol.write(process + 72, bytes(4))  # remove the error label
        with self.assertRaisesRegex(DolError, "process"):
            build_file_save_fragment(self.dol, self.region, self.core)


if __name__ == "__main__":
    unittest.main()
