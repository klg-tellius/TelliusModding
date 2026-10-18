import unittest
from pathlib import Path

from fe_modding.formats.extended_flags import FlagLayout, ExtendedState, HUB_ALIASES
from fe_modding.formats.event_flags import flag_hash
from fe_modding.game_code.dol import Dol, DolError
from fe_modding.game_code.extended_flag_runtime import build_core, LIVE_OFFSET, BASE
from fe_modding.game_code.extended_flag_sites import PARTY, SITES, SKILL_TEST
from tests.ppc_flag_cpu import CPU

RETAIL = Path(__file__).resolve().parents[2] / "research/main_dol/dols"


class NativeFlagTests(unittest.TestCase):
    def setUp(self):
        if not all((RETAIL / f"{code}.dol").is_file() for code in SITES):
            self.skipTest("retail regional DOLs are not available")
        self.layout = (FlagLayout().add("Aa", "campaign").add("B<", "campaign")
                       .add("拡張", "campaign").add("Visited", "chapter", 18)
                       .add("OtherChapter", "chapter", 19))

    def setup_region(self, code):
        self.code = code
        self.dol = Dol.open(RETAIL / f"{code}.dol")
        self.image = build_core(self.dol, code, self.layout)
        self.cpu = CPU(self.image)
        self.cpu.r[13] = self.dol.sda_bases()[1]
        self.cpu.write(PARTY[code] + 0x10, 18, 1)
        for r in range(14, 32):
            self.cpu.r[r] = 0x55550000 + r

    def call(self, operation, name="", *, foreign=False):
        cpu = self.cpu
        raw = name.encode("shift_jis") + b"\0"
        for i, byte in enumerate(raw):
            cpu.write(0x81000000 + i, byte, 1)
        cpu.r[3] = PARTY[self.code] + 0xB4 + (0x1000 if foreign else 0)
        cpu.r[4] = 0x81000000
        cpu.lr = CPU.RETURN
        initial_stack = cpu.r[1]
        original = SITES[self.code][operation][0]
        stopped = cpu.run(self.image.functions[operation], {original + 4})
        self.assertEqual(cpu.lr, CPU.RETURN)
        self.assertEqual(cpu.r[14:], [0x55550000 + r for r in range(14, 32)])
        if stopped == CPU.RETURN:
            self.assertEqual(cpu.r[1], initial_stack)
        else:
            # A displaced stwu must execute exactly once before falling back.
            first = self.dol.u32(original)
            stack_delta = ((first & 0xFFFF) - 65536) if first >> 26 == 37 else 0
            self.assertEqual(cpu.r[1], initial_stack + stack_delta)
            cpu.r[1] = initial_stack
        return stopped, cpu.r[3]

    def state(self):
        at = self.image.record_address
        raw = bytes(self.cpu.memory[at + i] for i in range(188))
        return ExtendedState.parse(raw)

    def test_registration_hash_collisions_and_signed_names_in_every_region(self):
        self.assertEqual(flag_hash("Aa"), flag_hash("B<"))
        for code in SITES:
            with self.subTest(region=code):
                self.setup_region(code)
                for name in ("Aa", "B<", "拡張"):
                    # An embedded name still needs its registration to become live.
                    self.call("flag_set", name)
                    self.assertEqual(self.call("flag_get", name), (CPU.RETURN, 0))
                    self.call("flag_register_global", name)
                    self.call("flag_set", name)
                    self.assertEqual(self.call("flag_get", name), (CPU.RETURN, 1))
                self.call("flag_clear", "B<")
                self.assertEqual(self.call("flag_get", "Aa")[1], 1)
                self.assertEqual(self.call("flag_get", "B<")[1], 0)
                self.assertEqual(self.call("flag_get", "拡張")[1], 1)
                self.call("flag_register_global", "Aa")
                self.assertEqual(self.call("flag_get", "Aa")[1], 0)

    def test_local_reset_new_game_and_boot_have_distinct_lifetimes(self):
        for code in SITES:
            with self.subTest(region=code):
                self.setup_region(code)
                self.call("flag_register_global", "Aa")
                self.call("flag_set", "Aa")
                self.call("flag_register_local", "Visited")
                self.call("flag_set", "Visited")
                self.call("flag_register_local", "Visited")
                self.assertEqual(self.call("flag_get", "Visited")[1], 1)
                self.call("flag_set", "HUB_ACTIVE")
                self.call("flag_reset_locals")
                self.assertEqual(self.call("flag_get", "Visited")[1], 0)
                self.assertEqual(self.call("flag_get", "Aa")[1], 1)
                self.assertEqual(self.call("flag_get", "HUB_ACTIVE")[1], 1)
                self.cpu.write(PARTY[code] + 0x10, 19, 1)
                self.call("flag_register_local", "OtherChapter")
                self.call("flag_set", "OtherChapter")
                self.assertEqual(self.call("flag_get", "OtherChapter")[1], 1)
                self.assertNotEqual(self.call("flag_get", "Visited")[0], CPU.RETURN)
                self.call("flag_clear_playthrough")
                self.assertEqual(self.state().hub, bytes(4))
                self.assertEqual(self.state().campaign, bytes(128))
                self.assertEqual(self.state().chapter, bytes(32))
                # Global registrations survive new-game clearing, as in retail.
                self.call("flag_set", "Aa")
                self.assertEqual(self.call("flag_get", "Aa")[1], 1)
                self.call("flag_init")
                self.call("flag_set", "Aa")
                self.assertEqual(self.call("flag_get", "Aa")[1], 0)

    def test_hub_aliases_use_no_legacy_storage_and_foreign_tables_fall_back(self):
        for code in SITES:
            with self.subTest(region=code):
                self.setup_region(code)
                legacy = PARTY[code] + 0x3B4
                for i in range(12):
                    self.cpu.write(legacy + i, 0xA5, 1)
                for name in HUB_ALIASES:
                    self.call("flag_set", name)
                    self.assertEqual(self.call("flag_get", name), (CPU.RETURN, 1))
                self.assertEqual(self.state().hub, bytes((3, 255, 255, 0)))
                self.assertEqual([self.cpu.read(legacy + i, 1) for i in range(12)], [0xA5] * 12)
                before = self.state().build()
                for op in ("flag_set", "flag_clear", "flag_get", "flag_register_global",
                           "flag_register_local", "flag_reset_locals", "flag_init", "flag_clear_playthrough"):
                    self.assertNotEqual(self.call(op, "HUB_ACTIVE", foreign=True)[0], CPU.RETURN)
                self.assertEqual(self.state().build(), before)

    def test_arena_setter_protects_image_and_preserves_higher_requests(self):
        for code in SITES:
            with self.subTest(region=code):
                self.setup_region(code)
                end = self.image.base + len(self.image.data)
                original = SITES[code]["arena_low"][0]
                word = self.dol.u32(original)
                displacement = word & 65535
                displacement -= 65536 if displacement & 32768 else 0
                destination = self.cpu.r[13] + displacement
                for requested in (0x80300000, end, end + 0x10000):
                    self.cpu.lr = CPU.RETURN
                    self.cpu.r[3] = requested
                    self.cpu.run(self.image.functions["arena_low"])
                    self.assertEqual(self.cpu.read(destination, 4), max(end, requested))

    def test_code_conflicts_and_overlaps_fail_without_mutating_dol(self):
        self.setup_region("GFEE01")
        before = bytes(self.dol.data)
        build_core(self.dol, self.code, self.layout)
        self.assertEqual(bytes(self.dol.data), before)
        self.dol.add_text_section(BASE, bytes(32))
        with self.assertRaisesRegex(DolError, "overlaps"):
            build_core(self.dol, self.code, self.layout)
        self.setup_region("GFEE01")
        address = SITES[self.code]["flag_get"][0]
        self.dol.write(address + 8, bytes(4))
        with self.assertRaisesRegex(DolError, "retail code differs"):
            build_core(self.dol, self.code, self.layout)

    def record_io(self, operation, cursor, end, buffer=0x81100000):
        stream = 0x81010000
        self.cpu.write(stream, buffer, 4)
        self.cpu.write(stream + 4, cursor, 4)
        self.cpu.write(stream + 8, 0x100000, 4)  # deliberately untrustworthy retail capacity
        self.cpu.r[3], self.cpu.r[4] = stream, end
        self.cpu.lr = CPU.RETURN
        stack = self.cpu.r[1]
        self.assertEqual(self.cpu.run(self.image.functions[operation]), CPU.RETURN)
        self.assertEqual(self.cpu.r[1], stack)
        self.assertEqual(self.cpu.r[14:], [0x55550000 + r for r in range(14, 32)])
        return self.cpu.r[3], self.cpu.read(stream + 4, 4)

    def test_native_record_io_matches_codec_at_unaligned_cursor(self):
        for code in SITES:
            with self.subTest(region=code):
                self.setup_region(code)
                expected = ExtendedState.for_layout(self.layout)
                expected.hub = bytes((3, 18, 19, 0))
                expected.campaign = bytes(range(128))
                expected.chapter = bytes(range(32))
                raw = expected.build()
                cursor = 0x81100001
                for i, byte in enumerate(raw):
                    self.cpu.write(cursor + i, byte, 1)
                live = self.image.base + LIVE_OFFSET
                self.cpu.write(live, 0xA5, 1)
                self.assertEqual(self.record_io("record_read", cursor, cursor + len(raw)), (1, cursor + len(raw)))
                self.assertEqual(self.state(), expected)
                self.assertEqual(self.cpu.read(live, 1), 0xA5)
                destination = cursor + 1000
                self.cpu.write(destination - 1, 0xAA, 1)
                self.cpu.write(destination + len(raw), 0xBB, 1)
                self.assertEqual(self.record_io("record_write", destination, destination + len(raw)),
                                 (1, destination + len(raw)))
                self.assertEqual(bytes(self.cpu.read(destination + i, 1) for i in range(len(raw))), raw)
                self.assertEqual(self.cpu.read(destination - 1, 1), 0xAA)
                self.assertEqual(self.cpu.read(destination + len(raw), 1), 0xBB)

    def test_native_record_io_rejects_invalid_data_without_partial_commit(self):
        for code in SITES:
            with self.subTest(region=code):
                self.setup_region(code)
                raw = self.state().build()
                cursor = 0x81100001
                # All header fields, UUID bytes, and reserved hub bits are checked
                # before touching either the active state or stream cursor.
                for damaged in list(range(24)) + [24, 27]:
                    bad = bytearray(raw)
                    bad[damaged] ^= 0x80
                    for i, byte in enumerate(bad):
                        self.cpu.write(cursor + i, byte, 1)
                    before = dict(self.cpu.memory)
                    self.assertEqual(self.record_io("record_read", cursor, cursor + 188), (0, cursor))
                    self.assertEqual(self.state().build(), raw)
                    self.assertEqual({k: self.cpu.memory[k] for k in before}, before)
                for operation in ("record_read", "record_write"):
                    for at, end, start in ((cursor, cursor + 187, cursor),
                                           (cursor, cursor + 188, cursor + 1),
                                           (0xFFFFFFF0, 0x81800000, cursor),
                                           (cursor, 0x81800001, cursor),
                                           (cursor, cursor + 188, 0x7FFFFFFF)):
                        before = {k: v for k, v in self.cpu.memory.items()
                                  if not 0x81010000 <= k < 0x8101000C}
                        self.assertEqual(self.record_io(operation, at, end, start), (0, at))
                        self.assertEqual({k: v for k, v in self.cpu.memory.items()
                                          if not 0x81010000 <= k < 0x8101000C}, before)

    def preflight(self, units, masked, size):
        array, factions = 0x81200000, 0x81300000
        skills = {}
        for i in range(159):
            unit = array + i * 0x280
            occupied, faction, special = units[i] if i < len(units) else (False, 0, False)
            self.cpu.write(unit + 0x188, 0x81400000 if occupied else 0, 4)
            self.cpu.write(unit + 0x190, factions + i * 16, 4)
            self.cpu.write(factions + i * 16 + 8, faction, 1)
            skills[unit + 0x1BC] = special
        before = {k: v for k, v in self.cpu.memory.items() if k < 0x817EF000}
        self.cpu.r[3:6] = [array, int(masked), size]
        self.cpu.lr = CPU.RETURN
        stack = self.cpu.r[1]
        predicate = SKILL_TEST[self.code][0]
        at = self.image.functions["save_preflight"]
        while True:
            at = self.cpu.run(at, {predicate})
            if at == CPU.RETURN:
                break
            self.assertEqual(self.cpu.r[4], 0x59)
            result = int(skills[self.cpu.r[3]])
            at = self.cpu.lr
            # Model the external retail predicate ABI, including volatile clobbers.
            self.cpu.r[3:13] = [result] + [0xCCCCCCCC] * 9
        self.assertEqual(self.cpu.r[1], stack)
        self.assertEqual(self.cpu.r[14:], [0x55550000 + r for r in range(14, 32)])
        self.assertEqual({k: v for k, v in self.cpu.memory.items() if k < 0x817EF000}, before)
        return self.cpu.r[3]

    def test_save_preflight_matches_codec_limits_and_retail_faction_masking(self):
        from fe_modding.formats import save_file as sf
        from tests.test_save_file import build_block, unit_record
        block = sf.SaveBlock.parse(build_block([]), 0, 0x4000)
        block.header.version = 0x54460101
        block.extended_flags = ExtendedState.for_layout(self.layout)
        empty_size = block.build().index(b"XFLG") + len(block.extended_flags.build())
        unit = sf.SaveBlock.parse(build_block([unit_record(1, 2)]), 0, 0x4000).units[0]
        block.units[0] = unit
        stride = block.build().index(b"XFLG") + 188 - empty_size
        for code in SITES:
            with self.subTest(region=code):
                self.setup_region(code)
                for size, maximum in ((0x4000, 89), (0x6000, 147)):
                    for count in (0, 1, maximum, maximum + 1, 159):
                        required = empty_size + stride * count
                        self.assertEqual(self.preflight([(True, 0, False)] * count, False, size),
                                         required if required <= size else 0)
                mixed = [(True, faction, special) for faction in range(8) for special in (False, True)]
                # Player + reserve/inactive/removed (8), skill exceptions in factions 1..3 (3).
                self.assertEqual(self.preflight(mixed, True, 0x4000), empty_size + 11 * stride)
                self.assertEqual(self.preflight(mixed, False, 0x4000), empty_size + 16 * stride)
                self.assertEqual(self.preflight([(True, 8, False)], True, 0x4000), 0)


if __name__ == "__main__":
    unittest.main()
