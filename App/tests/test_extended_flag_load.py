import struct
import unittest
from pathlib import Path

from fe_modding.formats import save_file as sf, extended_flags as xf
from fe_modding.game_code.dol import Dol
from fe_modding.game_code.extended_flag_runtime import build_core, LIVE_OFFSET, SNAPSHOT_OWNER_OFFSET
from fe_modding.game_code.extended_flag_load import (
    build_load_helpers, build_card_open_fragment, build_card_read_fragment,
    OPEN_SITES, READ_SITES, ERROR_SETTERS, ERROR_BRANCHES,
)
from tests.ppc_flag_cpu import CPU
from tests.test_save_file import build_block, unit_record

RETAIL = Path(__file__).resolve().parents[2] / "research/main_dol/dols"


class CardLoadTests(unittest.TestCase):
    def setup_region(self, region):
        if not (RETAIL / f"{region}.dol").exists():
            self.skipTest("retail DOL unavailable")
        self.layout = xf.FlagLayout().add("Visited", "chapter", 18)
        dol = Dol.open(RETAIL / f"{region}.dol")
        self.dol = dol
        self.core = build_core(dol, region, self.layout)
        self.image = build_load_helpers(region, self.core)
        self.cpu = CPU(self.image)
        self.magic = b"FE8X" if region == "GFEP01" else b"FE8J"

    def block(self, occupied=1, size=0x4000):
        b = sf.SaveBlock.parse(build_block([unit_record(1, 2)]), 0, 0x4000)
        b.header.magic = self.magic
        b.header.version = xf.SAVE_VERSIONS[self.magic]
        b.size = b.header.size = size
        b.header.save_kind = 2 if size == 0x4000 else 3
        b.units = [b.units[0]] * occupied + [None] * (159 - occupied)
        b.extended_flags = xf.ExtendedState.for_layout(self.layout)
        b.extended_flags.hub_flag("HUB_STARTED", True)
        b.extended_flags.set("campaign", 1023, True)
        b.extended_flags.set("chapter", 0, True)
        return b.build()

    def call(self, name, raw, *, size=None, address=0x81100000):
        cpu = self.cpu
        for i, byte in enumerate(raw):
            cpu.write(address + i, byte, 1)
        cpu.r[3:5] = [address, len(raw) if size is None else size]
        cpu.lr = CPU.RETURN
        for r in range(14, 32):
            cpu.r[r] = 0x55550000 + r
        stack = cpu.r[1]
        self.assertEqual(cpu.run(self.image.functions[name]), CPU.RETURN)
        self.assertEqual(cpu.r[1], stack)
        self.assertEqual(cpu.r[14:], [0x55550000 + r for r in range(14, 32)])
        self.assertEqual(bytes(cpu.read(address + i, 1) for i in range(len(raw))), raw)
        return cpu.r[3]

    def test_native_scanner_matches_codec_for_variable_sized_unit_lists(self):
        for region in ("GFEE01", "GFEP01", "GFEJ01"):
            self.setup_region(region)
            for size, maximum in ((0x4000, 89), (0x6000, 147)):
                for count in (0, 1, 2, maximum):
                    with self.subTest(region=region, size=size, count=count):
                        raw = self.block(count, size)
                        before = self.image.data
                        self.assertEqual(self.call("card_validate", raw), 0x81100000 + raw.index(b"XFLG"))
                        self.assertEqual(bytes(self.cpu.read(self.image.base + i, 1) for i in range(len(before))), before)

    def test_malformed_layout_and_identity_leave_active_state_untouched(self):
        for region in ("GFEE01", "GFEP01", "GFEJ01"):
            self.setup_region(region)
            raw = self.block()
            extension = raw.index(b"XFLG")
            offsets = [0x40, 0x44, 0x4C, 0x60]
            offsets += [raw.index(tag) for tag in (b"BMST", b"MDST", b"UNIP", b"SOKO", b"FWEP", b"T  T")]
            offsets += list(range(extension, extension + 24)) + [extension + 24, extension + 27]
            before = self.image.data
            for offset in offsets:
                with self.subTest(region=region, corrupt=offset):
                    damaged = bytearray(raw)
                    damaged[offset] ^= 0x80
                    self.assertEqual(self.call("card_restore", bytes(damaged)), 0)
                    self.assertEqual(bytes(self.cpu.read(self.image.base + i, 1) for i in range(len(before))), before)
            for size in (0, 188, 0x3FFF, 0x6000):
                self.assertEqual(self.call("card_restore", raw, size=size), 0)

    def test_oversized_stream_is_rejected_before_copying_extended_state(self):
        self.setup_region("GFEE01")
        # A valid checkpoint layout cannot masquerade as a file block. Its unit
        # records run beyond the physical file boundary despite a forged header.
        raw = bytearray(self.block(147, 0x6000))
        struct.pack_into(">I", raw, 0x4C, 0x4000)
        raw[0x60] = 2
        self.assertEqual(self.call("card_restore", bytes(raw), size=0x4000), 0)

    def test_restore_preserves_registrations_and_can_repeat_after_startup_reset(self):
        for region in ("GFEE01", "GFEP01", "GFEJ01"):
            self.setup_region(region)
            raw = self.block()
            live = self.image.base + LIVE_OFFSET
            self.cpu.write(live, 0xA5, 1)
            self.cpu.write(live + 128, 1, 1)
            owner = self.image.base + SNAPSHOT_OWNER_OFFSET
            self.cpu.write(owner, 0x81200000, 4)
            for _ in range(2):
                self.assertEqual(self.call("card_restore", raw), 1)
                self.assertEqual(bytes(self.cpu.read(self.image.record_address + i, 1) for i in range(188)),
                                 raw[raw.index(b"XFLG"):raw.index(b"XFLG") + 188])
                self.assertEqual(self.cpu.read(live, 1), 0xA5)
                self.assertEqual(self.cpu.read(live + 128, 1), 1)
                self.assertEqual(self.cpu.read(owner, 4), 0)
                # Simulate the intervening startup local reset, then registration.
                for i in range(32):
                    self.cpu.write(self.image.record_address + 156 + i, 0, 1)

    def test_restore_accepts_a_suspend_already_marked_used(self):
        # JP marks the Suspend copy used (save kind 1) in memory before deserializing it; the
        # restore rejected kind 1, so campaign and local flags were lost on every resume.
        for region in ("GFEE01", "GFEP01", "GFEJ01"):
            self.setup_region(region)
            raw = bytearray(self.block(size=0x6000))
            for kind, restored in ((1, 1), (3, 1), (0, 0), (4, 0)):
                raw[0x60] = kind
                with self.subTest(region=region, kind=kind):
                    self.assertEqual(self.call("card_restore", bytes(raw), size=0x6000), restored)

    def test_card_open_checks_all_blocks_before_retail_selection(self):
        for region in OPEN_SITES:
            for invalid in (False, True):
                with self.subTest(region=region, invalid=invalid):
                    self.setup_region(region)
                    self.image = build_card_open_fragment(self.dol, region, self.image)
                    cpu = self.cpu = CPU(self.image)
                    context, card, parent = 0x81000000, 0x81100000, 0x81200000
                    cpu.write(context, card, 4)
                    raw = self.block(147, 0x6000)
                    # Last checkpoint tests the complete physical-block traversal.
                    cpu.memory.update({card + 0x20000 + i: byte for i, byte in enumerate(raw)})
                    consumed = bytearray(self.block())
                    consumed[0x60] = 1
                    consumed[consumed.index(b"XFLG")] = 0
                    cpu.memory.update({card + 0x2000 + i: byte for i, byte in enumerate(consumed)})
                    if invalid:
                        cpu.write(card + 0x20000 + raw.index(b"XFLG") + 8, 0, 1)
                        cpu.write(card + 0x20000 + raw.index(b"XFLG") + 9, 0, 1)
                        # Guaranteed UUID mismatch regardless of generated UUID.
                        for i in range(16):
                            cpu.write(card + 0x20000 + raw.index(b"XFLG") + 8 + i, 0, 1)
                    before = dict(cpu.memory)
                    cpu.r[3:5] = [context, 1]
                    cpu.r[31] = parent
                    selection = OPEN_SITES[region][4]
                    setter, branch = ERROR_SETTERS[region][0], ERROR_BRANCHES[region][0]
                    calls = []
                    pc = self.image.functions["card_open_guard"]
                    stack = cpu.r[1]
                    while True:
                        pc = cpu.run(pc, {selection, setter, branch})
                        if pc == CPU.RETURN:
                            break
                        calls.append((pc, cpu.r[3], cpu.r[4]))
                        pc = cpu.lr
                        cpu.r[3:13] = [0xCCCCCCCC] * 10
                    self.assertEqual(cpu.r[1], stack)
                    self.assertEqual(cpu.r[31], parent)
                    self.assertEqual({k: cpu.memory[k] for k in before}, before)
                    if invalid:
                        self.assertEqual([(at, arg) for at, arg, _ in calls],
                                         [(setter, 0xFFFFFFFC), (branch, parent)])
                    else:
                        self.assertEqual(calls, [(selection, context, 1)])

    def test_deserializer_hook_requires_guard_and_restores_on_each_read(self):
        for region in READ_SITES:
            with self.subTest(region=region):
                self.setup_region(region)
                with self.assertRaisesRegex(ValueError, "pre-selection"):
                    build_card_read_fragment(self.dol, region, self.image)
                self.image = build_card_open_fragment(self.dol, region, self.image)
                self.image = build_card_read_fragment(self.dol, region, self.image)
                cpu = self.cpu = CPU(self.image)
                raw, block = self.block(), 0x81100000
                cpu.memory.update({block + i: byte for i, byte in enumerate(raw)})
                cpu.r[1] -= 0x30
                cpu.r[31] = block
                cpu.write(cpu.r[1] + 0x34, CPU.RETURN, 4)
                cpu.write(self.image.base + LIVE_OFFSET + 128, 1, 1)
                stop = READ_SITES[region][0] + 0xFC
                for _ in range(2):
                    self.assertEqual(cpu.run(self.image.functions["card_read_restore"], {stop}), stop)
                    self.assertEqual(cpu.r[31], block)
                    self.assertEqual(cpu.read(cpu.r[1] + 0x34, 4), CPU.RETURN)
                    self.assertEqual(cpu.read(self.image.record_address + 156, 1), 1)
                    self.assertEqual(cpu.read(self.image.base + LIVE_OFFSET + 128, 1), 1)
                    cpu.write(self.image.record_address + 156, 0, 1)

    def test_load_hooks_compose_with_writer_and_snapshot_fragments(self):
        from fe_modding.game_code.extended_flag_file_save import build_file_save_fragment
        from fe_modding.game_code.extended_flag_checkpoint import build_checkpoint_fragment
        from fe_modding.game_code.extended_flag_snapshot import build_snapshot_fragment
        for region in READ_SITES:
            self.setup_region(region)
            original = bytes(self.dol.data)
            candidate = self.core
            if region != "GFEJ01":
                candidate = build_file_save_fragment(self.dol, region, candidate)
            candidate = build_checkpoint_fragment(self.dol, region, candidate)
            candidate = build_snapshot_fragment(self.dol, region, candidate)
            candidate = build_card_open_fragment(self.dol, region, candidate)
            candidate = build_card_read_fragment(self.dol, region, candidate)
            self.assertEqual(len(candidate.data), len(self.core.data))
            self.assertEqual(len(set(e.address for e in candidate.edits)), len(candidate.edits))
            self.assertEqual(bytes(self.dol.data), original)
            with self.assertRaises(ValueError):
                build_card_read_fragment(self.dol, region, candidate)


if __name__ == "__main__":
    unittest.main()
