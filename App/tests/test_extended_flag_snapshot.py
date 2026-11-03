import unittest

from fe_modding.game_code.extended_flag_snapshot import build_snapshot_fragment, SITES
from fe_modding.game_code.extended_flag_runtime import SNAPSHOT_OWNER_OFFSET
from fe_modding.game_code.extended_flag_sites import PARTY
from fe_modding.game_code.dol import DolError
from tests import test_extended_flag_runtime as runtime_tests
from tests.ppc_flag_cpu import CPU


class SnapshotTests(unittest.TestCase):
    def setup_region(self, code):
        self.h = runtime_tests.NativeFlagTests()
        self.h.setUp()
        self.h.setup_region(code)
        self.h.image = build_snapshot_fragment(self.h.dol, code, self.h.image)
        self.h.cpu = CPU(self.h.image)
        self.h.cpu.r[13] = self.h.dol.sda_bases()[1]
        for r in range(14, 32):
            self.h.cpu.r[r] = 0x55550000 + r
        self.h.cpu.write(PARTY[code] + 0x10, 18, 1)

    def snapshot(self, name, buffer=0x81100000):
        h = self.h
        cpu = h.cpu
        cpu.r[1] -= 0x20
        cpu.write(cpu.r[1] + 8, buffer, 4)
        cpu.write(cpu.r[1] + 0x24, CPU.RETURN, 4)
        stop = SITES[h.code][name][0] + (0x104 if name == "snapshot_read" else 0x13C)
        self.assertEqual(cpu.run(h.image.functions[name], {stop}), stop)
        self.assertEqual(cpu.read(cpu.r[1] + 0x24, 4), CPU.RETURN)
        self.assertEqual(cpu.r[14:], [0x55550000 + r for r in range(14, 32)])
        cpu.r[1] += 0x20

    def test_tutorial_roundtrip_restores_values_and_registration_masks(self):
        for code in SITES:
            with self.subTest(code=code):
                self.setup_region(code)
                h = self.h
                for operation, name in (("flag_register_global", "Aa"), ("flag_set", "Aa"),
                                        ("flag_register_local", "Visited"), ("flag_set", "Visited"),
                                        ("flag_set", "HUB_ACTIVE")):
                    h.call(operation, name)
                expected = h.state().build()
                self.snapshot("snapshot_write")
                h.call("flag_reset_locals")
                h.call("flag_clear", "Aa")
                h.call("flag_clear", "HUB_ACTIVE")
                h.call("flag_register_global", "B<")
                h.cpu.write(PARTY[code] + 0x10, 19, 1)
                h.call("flag_register_local", "OtherChapter")
                h.call("flag_set", "OtherChapter")
                # Retail AllPop resets tutorial locals and restores party/chapter
                # before the hook restores extended data and its live names.
                h.call("flag_reset_locals")
                h.cpu.write(PARTY[code] + 0x10, 18, 1)
                self.snapshot("snapshot_read")
                self.assertEqual(h.state().build(), expected)
                for name in ("Aa", "Visited", "HUB_ACTIVE"):
                    self.assertEqual(h.call("flag_get", name)[1], 1)
                h.call("flag_set", "B<")
                self.assertEqual(h.call("flag_get", "B<")[1], 0)
                self.assertEqual(h.cpu.read(h.image.base + SNAPSHOT_OWNER_OFFSET, 4), 0)
                # Consumed snapshots cannot be replayed after values change.
                h.call("flag_clear", "Visited")
                self.snapshot("snapshot_read")
                self.assertEqual(h.call("flag_get", "Visited")[1], 0)

    def test_snapshot_owner_and_new_game_invalidation(self):
        for code in SITES:
            with self.subTest(code=code):
                self.setup_region(code)
                h = self.h
                h.call("flag_set", "HUB_ACTIVE")
                self.snapshot("snapshot_write")
                h.call("flag_clear", "HUB_ACTIVE")
                self.snapshot("snapshot_read", 0x81200000)
                self.assertFalse(h.state().hub_flag("HUB_ACTIVE"))
                h.call("flag_clear_playthrough")
                self.snapshot("snapshot_read")
                self.assertFalse(h.state().hub_flag("HUB_ACTIVE"))

    def test_conflicting_serializer_rejected_without_mutation(self):
        self.setup_region("GFEE01")
        h = self.h
        with self.assertRaises(ValueError):
            build_snapshot_fragment(h.dol, h.code, h.image)
        at = SITES[h.code]["snapshot_read"][0]
        h.dol.write(at + 4, bytes(4))
        before = bytes(h.dol.data)
        with self.assertRaises(DolError):
            build_snapshot_fragment(h.dol, h.code, h.image)
        self.assertEqual(bytes(h.dol.data), before)


if __name__ == "__main__":
    unittest.main()
