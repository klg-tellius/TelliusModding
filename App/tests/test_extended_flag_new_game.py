import unittest
from pathlib import Path

from fe_modding.formats.extended_flags import FlagLayout
from fe_modding.game_code.dol import Dol, DolError
from fe_modding.game_code.extended_flag_runtime import build_core
from fe_modding.game_code.extended_flag_new_game import build_new_game_fragment, SITES
from fe_modding.game_code.extended_flag_checkpoint import UNIT_ARRAY, ERROR_SETTERS
from fe_modding.game_code.extended_flag_load import build_card_open_fragment
from fe_modding.game_code.extended_flag_container import build_container_fragment
from fe_modding.game_code.extended_flag_versions import build_version_fragment
from fe_modding.game_code.extended_flag_checkpoint import build_checkpoint_fragment
from fe_modding.game_code.extended_flag_file_save import build_file_save_fragment
from fe_modding.game_code.extended_flag_snapshot import build_snapshot_fragment
from fe_modding.game_code.extended_flag_load import build_card_read_fragment
from tests.ppc_flag_cpu import CPU

RETAIL = Path(__file__).resolve().parents[2] / "research/main_dol/dols"


class NewGameTests(unittest.TestCase):
    def prepare(self, region):
        if not (RETAIL / f"{region}.dol").exists():
            self.skipTest("retail DOL unavailable")
        dol = Dol.open(RETAIL / f"{region}.dol")
        core = build_core(dol, region, FlagLayout())
        return dol, core, build_new_game_fragment(dol, region, core)

    def run_hook(self, cpu, image, name, region, stops):
        pc, errors = image.functions[name], []
        error = ERROR_SETTERS[region][0]
        while True:
            pc = cpu.run(pc, {*stops, error})
            if pc != error:
                return pc, errors
            errors.append(cpu.r[3])
            pc = cpu.lr
            cpu.r[3:13] = [0xCCCCCCCC] * 10

    def test_initialized_party_capacity_before_payload_writes(self):
        for region, (writer, _) in SITES.items():
            _, _, image = self.prepare(region)
            for count in (89, 90):
                cpu = CPU(image)
                for i in range(count):
                    cpu.write(UNIT_ARRAY[region] + i * 0x280 + 0x188, 0x81200000, 4)
                cpu.r[31] = 0x81100000
                for i in range(0x4000):
                    cpu.write(cpu.r[31] + i, 0xA5, 1)
                saved, stack = cpu.r[14:], cpu.r[1]
                end, errors = self.run_hook(cpu, image, "new_game_guard", region,
                                            {writer + 0x5D8, writer + 0x760})
                self.assertEqual(end, writer + (0x5D8 if count == 89 else 0x760))
                self.assertEqual(errors, [] if count == 89 else [0xFFFFFFF7])
                self.assertEqual(cpu.r[14:], saved)
                self.assertEqual(cpu.r[1], stack)
                self.assertTrue(all(cpu.read(0x81100000 + i, 1) == 0xA5 for i in range(0x4000)))

    def test_append_boundary_and_failure_bypasses_finalization(self):
        for region, (writer, _) in SITES.items():
            _, _, image = self.prepare(region)
            for fits in (True, False):
                cpu = CPU(image)
                cpu.r[31] = 0x81100000
                cursor = cpu.r[31] + 0x4000 - (188 if fits else 187)
                cpu.write(cpu.r[1] + 8, cpu.r[31] + 0xB8, 4)
                cpu.write(cpu.r[1] + 12, cursor, 4)
                saved = cpu.r[14:]
                end, errors = self.run_hook(cpu, image, "new_game_append", region,
                                            {writer + 0x704, writer + 0x760})
                self.assertEqual(end, writer + (0x704 if fits else 0x760))
                self.assertEqual(errors, [] if fits else [0xFFFFFFF7])
                self.assertEqual(cpu.r[14:], saved)
                self.assertEqual(cpu.read(cpu.r[1] + 12, 4), cursor + (188 if fits else 0))
                expected = image.data[image.record_address - image.base: image.record_address - image.base + 188]
                actual = bytes(cpu.read(cursor + i, 1) for i in range(188))
                self.assertEqual(actual, expected if fits else bytes(188))

    def test_composition_and_retail_guards(self):
        for region, (writer, _) in SITES.items():
            dol, core, image = self.prepare(region)
            before = bytes(dol.data)
            image = build_checkpoint_fragment(dol, region, image)
            image = build_snapshot_fragment(dol, region, image)
            if region != "GFEJ01":
                image = build_file_save_fragment(dol, region, image)
            combined = build_card_open_fragment(dol, region, image)
            combined = build_card_read_fragment(dol, region, combined)
            combined = build_container_fragment(dol, region, combined)
            combined = build_version_fragment(dol, region, combined)
            self.assertIn("new_game_append", combined.functions)
            occupied = set()
            for edit in combined.edits:
                addresses = set(range(edit.address, edit.address + len(edit.original)))
                self.assertFalse(occupied & addresses)
                occupied.update(addresses)
            self.assertEqual(bytes(dol.data), before)
            with self.assertRaises(ValueError):
                build_new_game_fragment(dol, region, image)
            dol.write(writer + 8, bytes(4))
            with self.assertRaises(DolError):
                build_new_game_fragment(dol, region, core)


if __name__ == "__main__":
    unittest.main()
