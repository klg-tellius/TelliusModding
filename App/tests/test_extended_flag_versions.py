import unittest
from pathlib import Path

from fe_modding.formats.extended_flags import FlagLayout
from fe_modding.game_code.dol import Dol, DolError
from fe_modding.game_code.extended_flag_runtime import build_core
from fe_modding.game_code.extended_flag_load import build_card_open_fragment
from fe_modding.game_code.extended_flag_container import build_container_fragment
from fe_modding.game_code.extended_flag_versions import build_version_fragment, SITES
from tests.ppc_flag_cpu import CPU

RETAIL = Path(__file__).resolve().parents[2] / "research/main_dol/dols"


class VersionTests(unittest.TestCase):
    def prepare(self, region):
        if not (RETAIL / f"{region}.dol").exists():
            self.skipTest("retail DOL unavailable")
        dol = Dol.open(RETAIL / f"{region}.dol")
        core = build_core(dol, region, FlagLayout())
        core = build_card_open_fragment(dol, region, core)
        core = build_container_fragment(dol, region, core)
        image = build_version_fragment(dol, region, core)
        return dol, core, image

    def test_all_block_comparisons_accept_only_regional_extended_version(self):
        for region, sites in SITES.items():
            dol, core, image = self.prepare(region)
            edits = {e.address: e.patched for e in image.edits}
            expected = 0x54460102 if region == "GFEP01" else 0x54460101
            cpu = CPU(image)
            for at, raw in sites["compare"]:
                for offset in range(0, 12, 4):
                    word = edits.get(at + offset, dol.read(at + offset, 4))
                    cpu.write(at + offset, int.from_bytes(word, "big"), 4)
                ra = (dol.u32(at) >> 16) & 31
                for value in (expected, expected ^ 3, 0x20050201, 0x20050801):
                    cpu.r[ra] = 0x81100000
                    cpu.write(0x81100044, value, 4)
                    cpu.run(at, {at + 12})
                    self.assertEqual(cpu.cr[2], value == expected, (region, hex(at), hex(value)))

    def test_finalizer_preserves_registers_and_condition_for_system_data(self):
        for region, sites in SITES.items():
            _, _, image = self.prepare(region)
            cpu = CPU(image)
            for condition in ((True, False, False), (False, False, True)):
                cpu.r[0] = 0x20050801
                cpu.r[4] = 0x20050201
                cpu.r[12] = 0x12345678
                cpu.r[29] = 0x81100000
                cpu.cr = condition
                registers, lr = list(cpu.r), cpu.lr
                cpu.run(image.functions["block_version_finalize"], {sites["finalize"][0] + 4})
                self.assertEqual(cpu.r, registers)
                self.assertEqual(cpu.lr, lr)
                self.assertEqual(cpu.cr, condition)
                self.assertEqual(cpu.read(0x81100044, 4),
                                 0x54460102 if region == "GFEP01" else 0x54460101)

    def test_constructor_values_and_system_data_comparisons(self):
        for region, sites in SITES.items():
            dol, _, image = self.prepare(region)
            edits = {e.address: e.patched for e in image.edits}
            cpu = CPU(image)
            for at, _ in sites["construct"]:
                cpu.r[3:] = [0x81100000] * 29
                for offset in range(0, 12, 4):
                    word = edits.get(at + offset, dol.read(at + offset, 4))
                    cpu.write(at + offset, int.from_bytes(word, "big"), 4)
                cpu.run(at, {at + 12})
                target = (dol.u32(at + 8) >> 21) & 31
                self.assertEqual(cpu.r[target], 0x54460102 if region == "GFEP01" else 0x54460101)
            blocks, system = [], []
            # Independently inventory every negative retail-date comparison.
            for section in dol.text_sections:
                for at in range(section.address + 4, section.address + section.size - 4, 4):
                    word = dol.u32(at)
                    if word >> 26 != 15 or word & 0xFFFF != 0xDFFB:
                        continue
                    load, compare = dol.u32(at - 4), dol.u32(at + 4)
                    self.assertEqual(load >> 26, 32)
                    self.assertEqual(compare >> 26, 10)
                    offset = load & 0xFFFF
                    self.assertIn(offset, (0x44, 0x74))
                    if offset == 0x44:
                        blocks.append(at - 4)
                    else:
                        system.append(at)
                        for word_at in (at - 4, at, at + 4):
                            self.assertNotIn(word_at, edits)
            self.assertEqual(blocks, [at for at, _ in sites["compare"]])
            self.assertEqual(len(system), 4 if region == "GFEJ01" else 8)

    def test_atomic_guards_and_no_overlapping_edits(self):
        for region in SITES:
            dol, core, image = self.prepare(region)
            original = bytes(dol.data)
            occupied = set()
            for edit in image.edits:
                addresses = set(range(edit.address, edit.address + len(edit.original)))
                self.assertFalse(occupied & addresses)
                occupied.update(addresses)
            self.assertEqual(bytes(dol.data), original)
            with self.assertRaises(ValueError):
                build_version_fragment(dol, region, image)
            dol.write(SITES[region]["compare"][-1][0], bytes(4))
            with self.assertRaises(DolError):
                build_version_fragment(dol, region, core)


if __name__ == "__main__":
    unittest.main()
