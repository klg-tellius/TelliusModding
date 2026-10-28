import struct
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fe_modding.game_code import versions
from fe_modding.game_code import entries, entries_fe10, ppc, verify
from fe_modding.game_code import promotion
from fe_modding.game_code.catalog import (CATALOG, CAVE_ADDRESS, CAVE_SIZE, Edit, Field, Patch, Session,
                                          State, Tunable, in_cave, make_signature)
from fe_modding.game_code.dol import Dol, DolError

TEXT_ADDR = 0x80005600
TEXT_SIZE = 0x100
DATA_ADDR = 0x80300000


def build_dol(text: bytes = b"", data: bytes = b"") -> Dol:
    """A DOL with one text section at TEXT_ADDR and one data section at DATA_ADDR."""
    text = text.ljust(TEXT_SIZE, b"\x00")
    data = data.ljust(0x40, b"\x00")
    offsets, addresses, sizes = [0] * 18, [0] * 18, [0] * 18
    offsets[0], addresses[0], sizes[0] = 0x100, TEXT_ADDR, len(text)
    offsets[7], addresses[7], sizes[7] = 0x100 + len(text), DATA_ADDR, len(data)
    header = struct.pack(">18I18I18I3I", *offsets, *addresses, *sizes, 0x80400000, 0x1000, TEXT_ADDR)
    return Dol(header.ljust(0x100, b"\x00") + text + data)


def word(value: int) -> bytes:
    return struct.pack(">I", value)


LI_R3_3 = 0x38600003      # li r3,3
LI_R3_5 = 0x38600005
LI_R4_3 = 0x38800003
NOP = 0x60000000
BLR = 0x4E800020
US, JP = "GFEE01", "GFEJ01"


class DolTests(unittest.TestCase):
    def test_special_tunables_use_the_requested_controls(self):
        self.assertTrue(CATALOG.entries["promotion.third_tier_crown_only"].checkbox)
        self.assertEqual(CATALOG.entries["battle.stats_position"].choices,
                         ("Under the HP windows", "Above the HP windows", "Bottom of the screen"))

    def test_read_write_by_address(self):
        dol = build_dol(word(LI_R3_3))
        self.assertEqual(dol.u32(TEXT_ADDR), LI_R3_3)
        dol.write(TEXT_ADDR, word(LI_R3_5))
        self.assertEqual(dol.u32(TEXT_ADDR), LI_R3_5)
        self.assertTrue(dol.is_text(TEXT_ADDR))
        self.assertFalse(dol.is_text(DATA_ADDR))

    def test_outside_sections_is_rejected(self):
        dol = build_dol()
        with self.assertRaises(DolError):
            dol.read(0x80100000, 4)
        with self.assertRaises(DolError):
            dol.write(TEXT_ADDR + TEXT_SIZE - 2, b"\x00" * 4)


class IdentifyTests(unittest.TestCase):
    def test_modified_dol_is_recognised_by_boot_code_and_size(self):
        dol = build_dol()
        self.assertIsNone(versions.identify(dol).version)
        us = versions.VERSIONS[US]
        real = versions.GameVersion(us.code, us.region, us.label, us.dol_sha1, TEXT_SIZE)
        original = dict(versions.VERSIONS)
        try:
            versions.VERSIONS[US] = real
            found = versions.identify(dol, US)
            self.assertEqual(found.version.code, US)
            self.assertFalse(found.pristine)
            self.assertIsNone(versions.identify(dol, "GFEP01").version)   # wrong size for PAL
            self.assertIsNone(versions.identify(dol, "XXXX00").version)
        finally:
            versions.VERSIONS.update(original)


class PatchTests(unittest.TestCase):
    def setUp(self):
        self.dol = build_dol(word(LI_R3_3) + word(NOP) + word(BLR))
        self.session = Session(self.dol, versions.VERSIONS[US])
        self.patch = Patch("t.patch", "Test", "Patch", "", {
            US: (Edit(TEXT_ADDR, word(LI_R3_3), word(LI_R3_5)),),
        })

    def moved_dol(self):
        """The same code, two instructions further down than the stored address."""
        return build_dol(word(NOP) * 2 + word(LI_R3_3) + word(NOP) + word(BLR))

    def signed_patch(self, pid):
        signature = make_signature(self.dol, TEXT_ADDR, before=0, after=3)
        return Patch(pid, "Test", "Sig", "", {
            US: (Edit(TEXT_ADDR, word(LI_R3_3), word(LI_R3_5), signature),),
        })

    def test_apply_and_revert_round_trip(self):
        before = self.dol.sha1()
        self.assertEqual(self.session.patch_status(self.patch).state, State.ORIGINAL)
        self.session.set_patch(self.patch, True)
        self.assertEqual(self.session.patch_status(self.patch).state, State.APPLIED)
        self.session.set_patch(self.patch, True)               # idempotent
        self.assertEqual(self.dol.u32(TEXT_ADDR), LI_R3_5)
        self.session.set_patch(self.patch, False)
        self.assertEqual(self.dol.sha1(), before)

    def test_unexpected_bytes_are_a_conflict_and_never_written(self):
        self.dol.write(TEXT_ADDR, word(LI_R4_3))
        self.assertEqual(self.session.patch_status(self.patch).state, State.CONFLICT)
        with self.assertRaises(DolError):
            self.session.set_patch(self.patch, True)
        self.assertEqual(self.dol.u32(TEXT_ADDR), LI_R4_3)

    def test_version_without_sites_is_unavailable(self):
        session = Session(self.dol, versions.VERSIONS[JP])
        self.assertEqual(session.patch_status(self.patch).state, State.UNAVAILABLE)

    def test_signature_finds_a_moved_site(self):
        moved = self.moved_dol()
        patch = self.signed_patch("t.sig")
        session = Session(moved, versions.VERSIONS[US])
        self.assertEqual(session.patch_status(patch).state, State.ORIGINAL)
        session.set_patch(patch, True)
        self.assertEqual(moved.u32(TEXT_ADDR + 8), LI_R3_5)
        self.assertEqual(moved.u32(TEXT_ADDR), NOP)

    def test_other_version_is_reached_through_signature_only(self):
        moved = self.moved_dol()
        patch = self.signed_patch("t.sig2")
        session = Session(moved, versions.VERSIONS[JP])
        self.assertEqual(session.patch_status(patch).state, State.ORIGINAL)
        session.set_patch(patch, True)
        self.assertEqual(moved.u32(TEXT_ADDR + 8), LI_R3_5)

    def test_signature_fallback_never_crosses_game_families(self):
        moved = self.moved_dol()
        patch = self.signed_patch("t.no_cross_game")
        session = Session(moved, versions.RADIANT_DAWN_VERSIONS["RFEE01"])
        self.assertEqual(session.patch_status(patch).state, State.UNAVAILABLE)

    def test_signature_masks_relocatable_operands(self):
        lis_addi = word(0x3C608030) + word(0x38631234) + word(BLR)   # lis r3,0x8030 ; addi r3,r3,0x1234
        other = word(0x3C608040) + word(0x38635678) + word(BLR)
        a, b = build_dol(lis_addi), build_dol(other)
        self.assertEqual(make_signature(a, TEXT_ADDR, 0, 3).words, make_signature(b, TEXT_ADDR, 0, 3).words)


class TunableTests(unittest.TestCase):
    def setUp(self):
        self.dol = build_dol(word(LI_R3_3) + word(BLR), struct.pack(">HBxf", 7, 9, 1.5))
        self.session = Session(self.dol, versions.VERSIONS[US])

    def tunable(self, kind, address, default, lo, hi, expect=b""):
        return Tunable("t.tun", "Test", "Tun", "", default, lo, hi, {US: (Field(address, kind, expect),)})

    def test_instruction_immediate(self):
        t = self.tunable("imm16s", TEXT_ADDR, 3, -100, 100, expect=word(LI_R3_3)[:2])
        self.assertEqual(self.session.tunable_status(t).state, State.ORIGINAL)
        self.session.set_tunable(t, -2)
        status = self.session.tunable_status(t)
        self.assertEqual((status.state, status.value), (State.CUSTOM, -2))
        self.assertEqual(self.dol.u32(TEXT_ADDR), 0x3860FFFE)      # opcode/register half untouched
        self.session.reset(t)
        self.assertEqual(self.dol.u32(TEXT_ADDR), LI_R3_3)

    def test_negated_instruction_immediate(self):
        dol = build_dol(word(0x3803FFFB) + word(BLR))       # subi r0,r3,5
        session = Session(dol, versions.VERSIONS[US])
        t = Tunable("t.neg", "Test", "Neg", "", 5, 1, 25,
                    {US: (Field(TEXT_ADDR, "imm16neg", bytes.fromhex("3803")),)})
        self.assertEqual(session.tunable_status(t).value, 5)
        session.set_tunable(t, 7)
        self.assertEqual(session.tunable_status(t).value, 7)
        self.assertEqual(dol.u32(TEXT_ADDR), 0x3803FFF9)
        session.reset(t)
        self.assertEqual(dol.u32(TEXT_ADDR), 0x3803FFFB)

    def test_wrong_instruction_makes_it_unavailable(self):
        t = self.tunable("imm16s", TEXT_ADDR + 4, 3, 0, 9, expect=word(LI_R3_3)[:2])
        self.assertEqual(self.session.tunable_status(t).state, State.UNAVAILABLE)
        with self.assertRaises(DolError):
            self.session.set_tunable(t, 4)

    def test_data_kinds(self):
        for kind, offset, default, new in (("u16", 0, 7, 300), ("u8", 2, 9, 200), ("f32", 4, 1.5, 2.25)):
            t = self.tunable(kind, DATA_ADDR + offset, default, 0, 1000)
            self.assertEqual(self.session.tunable_status(t).value, default)
            self.session.set_tunable(t, new)
            self.assertEqual(self.session.tunable_status(t).value, new)

    def test_lis_addi_constant(self):
        dol = build_dol(word(0x3CA00099) + word(0x3805967F))          # lis r5,0x99; addi r0,r5,-0x6981
        session = Session(dol, versions.VERSIONS[US])
        t = Tunable("t.gold", "Test", "Gold", "", 9999999, 0, 9999999,
                    {US: (Field(TEXT_ADDR, "lis_addi", bytes.fromhex("3ca03805")),)})
        self.assertEqual(session.tunable_status(t).state, State.ORIGINAL)
        for value, hi, lo in ((50000, 0x0001, 0x3805C350 & 0xFFFF), (32767, 0x0000, 0x7FFF), (0, 0, 0)):
            session.set_tunable(t, value)
            self.assertEqual(session.tunable_status(t).value, value)
            self.assertEqual((dol.u32(TEXT_ADDR), dol.u32(TEXT_ADDR + 4)), (0x3CA00000 | hi, 0x38050000 | lo))
        session.reset(t)
        self.assertEqual((dol.u32(TEXT_ADDR), dol.u32(TEXT_ADDR + 4)), (0x3CA00099, 0x3805967F))

    def test_lis_addi_constant_with_intervening_instruction(self):
        dol = build_dol(word(0x3C600099) + word(NOP) + word(0x3803967F))
        session = Session(dol, versions.VERSIONS[US])
        t = Tunable("t.gold.gap", "Test", "Gold", "", 9999999, 0, 9999999,
                    {US: (Field(TEXT_ADDR, "lis_addi8", bytes.fromhex("3c603803")),)})
        self.assertEqual(session.tunable_status(t).value, 9999999)
        session.set_tunable(t, 50000)
        self.assertEqual(session.tunable_status(t).value, 50000)
        self.assertEqual(dol.u32(TEXT_ADDR + 4), NOP)
        session.reset(t)
        self.assertEqual((dol.u32(TEXT_ADDR), dol.u32(TEXT_ADDR + 8)), (0x3C600099, 0x3803967F))

    def test_signed_byte(self):
        dol = build_dol(data=bytes([0xF6, 0x0A]))                       # -10, +10
        session = Session(dol, versions.VERSIONS[US])
        t = Tunable("t.s8", "Test", "Signed", "", -10, -100, 0, {US: (Field(DATA_ADDR, "s8"),)})
        self.assertEqual(session.tunable_status(t).state, State.ORIGINAL)
        session.set_tunable(t, -25)
        self.assertEqual((session.tunable_status(t).value, dol.read(DATA_ADDR, 1)), (-25, b"\xe7"))

    def test_range_is_enforced(self):
        t = self.tunable("u8", DATA_ADDR + 2, 9, 0, 100)
        with self.assertRaises(DolError):
            self.session.set_tunable(t, 101)

    def test_disagreeing_sites_are_a_conflict(self):
        t = Tunable("t.multi", "Test", "Multi", "", 7, 0, 1000, {
            US: (Field(DATA_ADDR, "u16"), Field(DATA_ADDR + 4, "f32"))})
        self.assertEqual(self.session.tunable_status(t).state, State.CONFLICT)


class CaveTests(unittest.TestCase):
    def setUp(self):
        self.dol = build_dol(word(LI_R3_3) + word(BLR))
        self.session = Session(self.dol, versions.VERSIONS[US])
        stub = word(ppc.mulli(3, 3, 4)) + word(ppc.b(CAVE_ADDRESS + 4, TEXT_ADDR))
        hook = word(ppc.b(TEXT_ADDR, CAVE_ADDRESS))
        self.patch = Patch("t.cave", "Test", "Cave", "", {US: (
            Edit(TEXT_ADDR, word(LI_R3_3), hook),
            Edit(CAVE_ADDRESS, bytes(8), stub, wild=((2, 2),)),
        )})

    def test_cave_section_is_created_and_pruned(self):
        before = self.dol.sha1()
        self.assertEqual(self.session.patch_status(self.patch).state, State.ORIGINAL)
        self.assertFalse(self.dol.has_section_at(CAVE_ADDRESS))
        self.session.set_patch(self.patch, True)
        self.assertTrue(self.dol.has_section_at(CAVE_ADDRESS))
        self.assertEqual(self.dol.section_at(CAVE_ADDRESS).size, CAVE_SIZE)
        self.assertEqual(self.dol.read(CAVE_ADDRESS, 4), word(ppc.mulli(3, 3, 4)))
        self.session.set_patch(self.patch, False)
        self.assertFalse(self.dol.has_section_at(CAVE_ADDRESS))
        self.assertEqual(self.dol.sha1(), before)

    def test_wild_bytes_do_not_break_the_applied_state(self):
        self.session.set_patch(self.patch, True)
        self.dol.write(CAVE_ADDRESS + 2, b"\x00\x09")          # a tunable changed the immediate
        self.assertEqual(self.session.patch_status(self.patch).state, State.APPLIED)
        self.session.set_patch(self.patch, False)
        self.assertEqual(self.session.patch_status(self.patch).state, State.ORIGINAL)

    def test_tunable_installs_its_requirement(self):
        tunable = Tunable("t.req", "Test", "Req", "", 4, 0, 16,
                          {US: (Field(CAVE_ADDRESS, "imm16s", b"\x1c\x63"),)}, requires=(self.patch,))
        self.assertEqual(self.session.tunable_status(tunable).state, State.ORIGINAL)   # not installed yet
        self.session.set_tunable(tunable, 8)
        self.assertEqual(self.session.patch_status(self.patch).state, State.APPLIED)
        self.assertEqual(self.session.tunable_status(tunable).value, 8)

    def test_new_section_cannot_overlap(self):
        with self.assertRaises(DolError):
            self.dol.add_text_section(TEXT_ADDR + 0x10, bytes(0x20))


class EncoderTests(unittest.TestCase):
    def test_known_encodings(self):
        self.assertEqual(ppc.srawi(3, 3, 1), 0x7C630E70)
        self.assertEqual(ppc.li(3, 0x32), 0x38600032)
        self.assertEqual(ppc.mulli(0, 0, 3), 0x1C000003)
        self.assertEqual(ppc.bl(0x801A5B18, 0x8000CE68), 0x4BE67351)
        self.assertEqual(ppc.b(0x801A57A8, 0x801A57B0), 0x48000008)
        self.assertEqual(ppc.andc(3, 3, 0), 0x7C630078)
        # words from the US executable (build_strike_forecast_log, kaneko_gauge_draw, draw_formatted_text_ui)
        self.assertEqual(ppc.lha(4, 0x2A2, 29), 0xA89D02A2)
        self.assertEqual(ppc.lwz(0, 0xCAC, 3), 0x80030CAC)
        self.assertEqual(ppc.cmpwi(0, 1), 0x2C000001)
        self.assertEqual(ppc.bc("eq", 0x80197A98, 0x80197AD4), 0x4182003C)
        self.assertEqual(ppc.bc("ge", 0x80197A9C, 0x80197AAC), 0x40800010)
        self.assertEqual(ppc.mr(26, 3), 0x7C7A1B78)
        self.assertEqual(ppc.fmr(30, 1), 0xFFC00890)
        self.assertEqual(ppc.extsb(0, 0), 0x7C000774)
        self.assertEqual(ppc.subf(3, 4, 5), 0x7C642850)
        self.assertEqual(ppc.divw(3, 4, 6), 0x7C6433D6)
        self.assertEqual(ppc.mullw(3, 3, 0), 0x7C6301D6)
        self.assertEqual(ppc.fctiwz(0, 1), 0xFC00081E)
        self.assertEqual(ppc.stfd(0, 0x18, 1), 0xD8010018)
        self.assertEqual(ppc.andi_(0, 0, 1), 0x70000001)

    def test_assemble_resolves_labels(self):
        words = ppc.assemble(0x80001000, [("eq", "end"), ("bl", 0x80001100), "end", ppc.BLR])
        self.assertEqual(words, [ppc.bc("eq", 0x80001000, 0x80001008), ppc.bl(0x80001004, 0x80001100), ppc.BLR])


RETAIL_DIR = Path(__file__).resolve().parents[2] / "research" / "main_dol" / "dols"


class RetailCatalogTests(unittest.TestCase):
    """Every catalog entry against the real executables (skipped when they are not extracted)."""

    def test_rd_numeric_proc_controls_are_independent(self):
        keys = ("astra", "aether", "adept", "luna", "sol", "colossus", "corrosion",
                "counter", "miracle", "cancel", "deadeye", "pavise")
        hooks = set()
        sites = set()
        for key in keys:
            scale = CATALOG.entries[f"rd.skill.{key}.activation_scale"]
            bonus = CATALOG.entries[f"rd.skill.{key}.activation_bonus"]
            self.assertEqual((scale.default, scale.minimum, scale.maximum), (4, 0, 16))
            self.assertEqual((bonus.default, bonus.minimum, bonus.maximum), (0, -100, 100))
            self.assertEqual(scale.requires, bonus.requires)
            self.assertEqual(len(scale.requires), 1)
            hook = scale.requires[0]
            self.assertTrue(hook.internal)
            hooks.add(hook.id)
            scale_site = scale.versions["RFEE01"][0].address
            bonus_site = bonus.versions["RFEE01"][0].address
            self.assertEqual(bonus_site, scale_site + 8)
            sites.add(scale_site)
        self.assertEqual(len(hooks), len(keys))
        self.assertEqual(len(sites), len(keys))

    def test_rd_growth_controls_cover_roll_fallback_and_bexp_target(self):
        hook = CATALOG.entries["rd.growth.random_gain.hook"]
        self.assertTrue(hook.internal)
        call, code, values = hook.versions["RFEE01"]
        self.assertEqual(call.address, entries_fe10._RD_GROWTH_CALL)
        self.assertEqual(code.address, entries_fe10._RD_GROWTH_STUB)
        self.assertEqual(code.patched, entries_fe10._rd_growth_stub(code.address))
        self.assertEqual(values.address, entries_fe10._RD_GROWTH_VALUES)
        self.assertEqual(values.patched, bytes([1]) * 8)
        for index, stat in enumerate(entries_fe10._RD_GROWTH_STATS):
            growth = CATALOG.entries[f"rd.growth.random.{index}"]
            self.assertEqual((growth.default, growth.minimum, growth.maximum), (1, 0, 9), stat)
            self.assertEqual(growth.requires, (hook,))
            table, = growth.versions["RFEE01"]
            self.assertEqual((table.address, table.kind),
                             (entries_fe10._RD_GROWTH_VALUES + index, "u8"))
        bexp = CATALOG.entries["rd.growth.bexp_stat_count"]
        self.assertEqual((bexp.default, bexp.minimum, bexp.maximum), (3, 0, 8))
        self.assertEqual(tuple(field.address for field in bexp.versions["RFEE01"]),
                         (0x8006D8E8, 0x8006DAB4, 0x8006DCD4))
        force_random = CATALOG.entries["rd.growth.force_random"].versions["RFEE01"][0]
        force_bexp = CATALOG.entries["rd.growth.force_bexp"].versions["RFEE01"][0]
        self.assertEqual((force_random.address, force_bexp.address),
                         (0x8006DD0C, 0x8006DD0C))
        self.assertEqual(force_random.original, force_bexp.original)
        self.assertEqual(force_random.patched,
                         ppc.b(0x8006DD0C, 0x8006DD24).to_bytes(4, "big"))
        self.assertEqual(force_bexp.patched,
                         ppc.b(0x8006DD0C, 0x8006DD34).to_bytes(4, "big"))
        empty = CATALOG.entries["rd.growth.allow_empty_level"].versions["RFEE01"][0]
        self.assertEqual(empty.address, 0x8006D6F0)
        self.assertEqual(empty.patched,
                         ppc.b(0x8006D6F0, 0x8006D77C).to_bytes(4, "big"))
        blossom_all = CATALOG.entries["rd.growth.blossom_for_everyone"].versions["RFEE01"][0]
        blossom_off = CATALOG.entries["rd.growth.disable_blossom_reroll"].versions["RFEE01"][0]
        self.assertEqual((blossom_all.address, blossom_off.address),
                         (0x8006D320, 0x8006D320))
        self.assertEqual(blossom_all.original, blossom_off.original)
        self.assertEqual(blossom_all.patched, ppc.NOP.to_bytes(4, "big"))
        self.assertEqual(blossom_off.patched,
                         ppc.b(0x8006D320, 0x8006D34C).to_bytes(4, "big"))

    def test_rd_promotion_controls_keep_distinct_native_paths(self):
        minimum = CATALOG.entries["rd.promotion.item_min_level"]
        crown_only = CATALOG.entries["rd.promotion.third_tier_crown_only"]
        self.assertEqual((minimum.default, minimum.minimum, minimum.maximum), (10, 1, 20))
        self.assertEqual(minimum.versions["RFEE01"][0].address, 0x8011FFA4)
        self.assertEqual(crown_only.versions["RFEE01"][0].address, 0x8006D238)
        self.assertEqual(crown_only.versions["RFEE01"][1].address,
                         entries_fe10._RD_CROWN_ONLY_STUB)
        self.assertTrue(in_cave(crown_only.versions["RFEE01"][1].address,
                                len(crown_only.versions["RFEE01"][1].patched)))

    def test_rd_no_terrain_bonus_uses_native_parity_clearer(self):
        patch = CATALOG.entries["rd.combat.no_terrain_bonus"]
        edit, = patch.versions["RFEE01"]
        self.assertEqual(edit.address, 0x8002F14C)
        self.assertEqual(edit.original, bytes.fromhex("9421FFF0"))
        self.assertEqual(edit.patched,
                         ppc.b(0x8002F14C, 0x8002F20C).to_bytes(4, "big"))

    def test_rd_relaxed_triangle_b_replaces_only_geometry_result(self):
        patch = CATALOG.entries["rd.triangle.b_relaxed_formation"]
        edit, = patch.versions["RFEE01"]
        self.assertEqual(edit.address, 0x8002D854)
        self.assertEqual(edit.original, bytes.fromhex("4BFFFAF5"))
        self.assertEqual(edit.patched, ppc.li(3, 1).to_bytes(4, "big"))

    def test_rd_support_controls_share_the_native_affinity_helper(self):
        support_range = CATALOG.entries["rd.support.range"]
        full = CATALOG.entries["rd.support.full_bonus"]
        self.assertEqual((support_range.default, support_range.minimum,
                          support_range.maximum), (3, 1, 30))
        range_field, = support_range.versions["RFEE01"]
        self.assertEqual((range_field.address, range_field.kind, range_field.expect),
                         (0x8002FD04, "imm16u", bytes.fromhex("2800")))
        full_edit, = full.versions["RFEE01"]
        self.assertEqual(full_edit.address, 0x8002FD60)
        self.assertEqual(full_edit.original, bytes.fromhex("480E9A01"))
        self.assertEqual(full_edit.patched, ppc.NOP.to_bytes(4, "big"))

    def test_catalog_entries_ids_are_unique_and_versioned(self):
        for entry in CATALOG.entries.values():
            expected = {"RFEE01"} if next(iter(entry.versions)).startswith("R") else set(entries.ALL)
            self.assertEqual(set(entry.versions), expected, entry.id)

    def test_every_version_verifies(self):
        found = 0
        for code in entries.ALL:
            path = RETAIL_DIR / f"{code}.dol"
            if not path.is_file():
                continue
            found += 1
            with self.subTest(code):
                self.assertEqual(verify.verify(Dol.open(path)), [])
        if not found:
            self.skipTest(f"no retail DOLs in {RETAIL_DIR}")

    def test_triangle_attack_options_patch_the_formation_checks(self):
        option_ids = (
            "triangle.a_allow_unpromoted",
            "triangle.b_allow_any_weapon",
            "triangle.b_relaxed_formation",
        )
        found = 0
        for code in entries.ALL:
            path = RETAIL_DIR / f"{code}.dol"
            if not path.is_file():
                continue
            found += 1
            for option_id in option_ids:
                with self.subTest(code=code, option=option_id):
                    dol = Dol.open(path)
                    before = dol.sha1()
                    option = CATALOG.entries[option_id]
                    session = Session(dol, versions.VERSIONS[code], Dol.open(path).read)
                    self.assertEqual(session.status(option).state, State.ORIGINAL)
                    session.set_patch(option, True)
                    self.assertEqual(session.status(option).state, State.APPLIED)
                    session.set_patch(option, False)
                    self.assertEqual(dol.sha1(), before)
        if not found:
            self.skipTest(f"no retail DOLs in {RETAIL_DIR}")

    def test_promotion_magic_choices_gain_separate_rank_handlers(self):
        patch = CATALOG.entries["promotion.anima_weapon_choice"]
        found = 0
        for code in entries.ALL:
            path = RETAIL_DIR / f"{code}.dol"
            if not path.is_file():
                continue
            found += 1
            with self.subTest(code):
                dol = Dol.open(path)
                before = dol.sha1()
                session = Session(dol, versions.VERSIONS[code])
                table, resume = promotion._SITES[code]
                for index in range(3):
                    self.assertEqual(dol.u32(table + (index + 4) * 4), resume)
                session.set_patch(patch, True)
                self.assertEqual(session.status(patch).state, State.APPLIED)
                for index, rank_offset in enumerate(promotion.RANK_OFFSETS):
                    stub = promotion.MAGIC_STUB + index * promotion.STUB_SIZE
                    self.assertEqual(dol.u32(table + (index + 4) * 4), stub)
                    self.assertEqual(dol.read(stub, promotion.STUB_SIZE),
                                     promotion._stub(stub, rank_offset, resume))
                session.set_patch(patch, False)
                self.assertEqual(dol.sha1(), before)
        if not found:
            self.skipTest(f"no retail DOLs in {RETAIL_DIR}")


class EditorTests(unittest.TestCase):
    """CodeEditor on a scratch copy of a retail extraction (skipped without the retail DOLs)."""

    def setUp(self):
        import shutil
        import tempfile
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

    def test_edits_are_saved_and_reset_restores_retail(self):
        from fe_modding.game_code.editor import CodeEditor
        editor = CodeEditor(self.root)
        self.assertTrue(editor.supported)
        crit = CATALOG.entries["combat.crit_multiplier"]
        luna = CATALOG.entries["proc.luna.scale"]
        self.assertIn("3 -> 5", editor.set_value(crit, 5))
        editor.set_value(luna, 8)
        reopened = CodeEditor(self.root)                     # what the page does on every visit
        self.assertEqual(reopened.status(crit).value, 5)
        self.assertEqual(reopened.status(luna).value, 8)
        self.assertEqual(len(reopened.modified_entries()), 2)          # the hook is internal
        reopened.set_value(luna, 4)                                    # back to default: hook drops out
        self.assertFalse(reopened.dol.has_section_at(CAVE_ADDRESS))
        self.assertEqual(reopened.reset_all(), 1)
        self.assertEqual((self.root / "sys" / "main.dol").read_bytes(), self.retail)

    def test_hashed_edit_reverts_from_the_kept_original(self):
        from fe_modding.game_code.editor import CodeEditor
        window = CATALOG.entries["battle.info_window"]
        window_without_files = Patch(window.id, window.group, window.name, window.description, window.versions)
        editor = CodeEditor(self.root)
        editor.set_patch(window_without_files, True)
        stranger = CodeEditor(self.root)                 # no retail copy anywhere: cannot rebuild TRK
        self.assertEqual(stranger.status(window).state, State.APPLIED)
        with self.assertRaises(DolError):
            stranger.set_patch(window_without_files, False)
        kept = CodeEditor(self.root, original=lambda path: self.retail if path.name == "main.dol" else None)
        kept.set_patch(window_without_files, False)
        self.assertEqual((self.root / "sys" / "main.dol").read_bytes(), self.retail)

    def test_unknown_executable_is_not_editable(self):
        from fe_modding.game_code.editor import CodeEditor
        (self.root / "sys" / "boot.bin").write_bytes(b"GXXX01\x00\x00" + bytes(0x438))
        data = bytearray(self.retail)
        data[0x2700] ^= 0xFF
        (self.root / "sys" / "main.dol").write_bytes(bytes(data))
        editor = CodeEditor(self.root)
        self.assertFalse(editor.supported)
        self.assertEqual(editor.status(CATALOG.entries["combat.crit_multiplier"]).state, State.UNAVAILABLE)


class BattleWindowTests(unittest.TestCase):
    """FE7Dragon's info window (game_code/battle_window.py)."""

    # The MetroTRK library around the space, the same layout in every build: TRKNubMainLoop starts
    # 0x3210 before trk_target_step_out_of_range, trk_debugger_notify_and_dispatch_a ends 0x2668 after.
    TRK_BEFORE, TRK_AFTER = 0x3210, 0x2668

    def test_hooks_return_after_their_sites(self):
        from fe_modding.game_code import battle_window as bw
        from fe_modding.game_code.battle_window_data import HOOKS
        for code in bw.VERSIONS:
            h = HOOKS[bw._KEYS[code]]
            code_bytes = bw.trk_code(code)
            for start, body, site in ((0, h["map"], h["map_site"]),
                                      (bw._FORECAST_OFFSET, h["forecast"], h["forecast_site"])):
                end = h["trk"] + start + len(body)
                self.assertEqual(code_bytes[start + len(body):start + len(body) + 4], word(ppc.b(end, site + 4)))
                for offset in range(0, len(body), 4):          # relative branches stay in the body
                    w = int.from_bytes(body[offset:offset + 4], "big")
                    if w >> 26 == 16:
                        target = offset + ((w & 0xFFFC) ^ 0x8000) - 0x8000
                    elif w >> 26 == 18:
                        self.assertFalse(w & 2, f"{code} +{offset:#x}: absolute branch")
                        target = offset + ((w & 0x03FFFFFC) ^ 0x02000000) - 0x02000000
                    else:
                        continue
                    self.assertTrue(0 <= target <= len(body), f"{code} +{offset:#x}")

    def test_trk_space_is_not_reached_from_outside_trk(self):
        from fe_modding.game_code import battle_window as bw
        from fe_modding.game_code.battle_window_data import HOOKS
        found = 0
        for code in bw.VERSIONS:
            path = RETAIL_DIR / f"{code}.dol"
            if not path.is_file():
                continue
            found += 1
            dol, base = Dol.open(path), HOOKS[bw._KEYS[code]]["trk"]
            low, high = base, base + bw._TRK_SIZE
            outside = []
            for section in dol.sections:
                values = dol.words(section.address, section.size // 4)
                for i, w in enumerate(values):
                    at = section.address + 4 * i
                    if base - self.TRK_BEFORE <= at < base + self.TRK_AFTER:    # TRK calling TRK
                        continue
                    if not section.is_text:
                        if low <= w < high:
                            outside.append(at)
                    elif w >> 26 == 18:
                        target = (w & 0x03FFFFFC) - (0x04000000 if w & 0x02000000 else 0)
                        if low <= (target if w & 2 else at + target) < high:
                            outside.append(at)
            with self.subTest(code):
                self.assertEqual(outside, [])
        if not found:
            self.skipTest(f"no retail DOLs in {RETAIL_DIR}")

    def test_battle_dbx_edit_round_trip(self):
        from fe_modding.game_code import battle_window as bw
        blocks = []
        for (cls, name), fields in bw.DBX_EDITS.items():
            lines = [f"\tclass\t{cls}", f"\tname\t{name}"]
            lines += [f"\t{key}\t{retail}" for key, (retail, _patched) in fields.items() if retail is not None]
            blocks.append("{\r\n" + "\r\n".join(lines) + "\r\n}\r\n")
        retail = "#\r\n# battle.dbx\r\n#\r\n\r\n" + "\r\n".join(blocks)
        patched = bw.edit_battle_dbx(retail, True)
        doc = __import__("fe_modding.formats.dbx", fromlist=["parse"]).parse(patched)
        self.assertEqual(doc.find("Picture", "ParamWin").get("pos"), "221,344")
        self.assertEqual(doc.find("Number", "NumAtkL").get("kerning"), "-4")
        self.assertEqual(bw.edit_battle_dbx(patched, True), patched)
        self.assertEqual(bw.edit_battle_dbx(patched, False), retail)

    @unittest.skipUnless(__import__("os").environ.get("FE9_EXTRACTED_FILES"),
                         "set FE9_EXTRACTED_FILES to an extracted files/ directory")
    def test_files_install_and_remove(self):
        import os
        import shutil
        import tempfile
        from fe_modding.formats import tpl, zdbx
        from fe_modding.game_code import battle_window as bw
        source = Path(os.environ["FE9_EXTRACTED_FILES"]).parent
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for relative in (bw.ARCHIVE, bw.BOX_SOURCE, bw.LABEL_FONT):
                (root / relative).parent.mkdir(parents=True, exist_ok=True)
                shutil.copy(source / relative, root / relative)
            retail = (root / bw.ARCHIVE).read_bytes()
            files = bw.GameFiles(root, lambda p, d: p.write_bytes(d), lambda p: retail if p.name == "zdbx.cmp" else None)
            self.assertEqual(sorted(bw.install_files(files)), sorted([bw.BOX_MEMBER, bw.NUMBER_MEMBER, bw.BATTLE_DBX]))
            self.assertEqual(bw.install_files(files), [])
            self.assertTrue(bw.files_installed(files))
            members = dict(zdbx.read_zdbx_files((root / bw.ARCHIVE).read_bytes()))
            number = tpl.read_tpl_image_info(__import__("io").BytesIO(members[bw.NUMBER_MEMBER]))[0]
            self.assertEqual((number.width, number.height), (200, 50))
            self.assertEqual((root / bw.LOOSE_BOX).read_bytes(), members[bw.BOX_MEMBER])
            bw.remove_files(files)
            self.assertEqual(dict(zdbx.read_zdbx_files((root / bw.ARCHIVE).read_bytes())),
                             dict(zdbx.read_zdbx_files(retail)))
            self.assertFalse((root / "files" / "zdbx").exists())


if __name__ == "__main__":
    unittest.main()


class SoundRoomTrackTests(unittest.TestCase):
    """The track table rewritten on a small fake layout: 64 pointers then a 4-name pool."""

    def setUp(self):
        from fe_modding.game_code import sound_room_tracks
        self.tracks = sound_room_tracks
        self.table, self.pool = DATA_ADDR, DATA_ADDR + 0x100
        names = [b"BGM_A", b"BGM_BB", b"BGM_C", b"BGM_DD"]
        pool, where = b"", []
        for n in names:
            where.append(self.pool + len(pool))
            pool += n + b"\0"
        self.end = self.pool + len(pool)
        table = b"".join(where[i % 4].to_bytes(4, "big") for i in range(64))
        self.dol = build_dol(data=table + pool + b"NEXT")
        sound_room_tracks.LAYOUT["TEST01"] = (self.table, self.pool, self.end)
        self.addCleanup(sound_room_tracks.LAYOUT.pop, "TEST01")

    def test_read_write_round_trip(self):
        before = bytes(self.dol.data)
        names = self.tracks.read_tracks(self.dol, "TEST01")
        self.assertEqual(names[:5], ["BGM_A", "BGM_BB", "BGM_C", "BGM_DD", "BGM_A"])
        self.tracks.write_tracks(self.dol, "TEST01", names)
        self.assertEqual(bytes(self.dol.data), before)

    def test_repeated_names_are_stored_once_and_the_pool_end_is_kept(self):
        names = ["BGM_LONGER1"] * 63 + ["BGM_A"]
        self.tracks.write_tracks(self.dol, "TEST01", names)
        self.assertEqual(self.tracks.read_tracks(self.dol, "TEST01"), names)
        self.assertEqual(self.dol.read(self.end, 4), b"NEXT")

    def test_too_long_or_wrong_count_is_refused(self):
        with self.assertRaises(DolError):
            self.tracks.write_tracks(self.dol, "TEST01", [f"BGM_{i:02d}" for i in range(64)])
        with self.assertRaises(DolError):
            self.tracks.write_tracks(self.dol, "TEST01", ["BGM_A"] * 63)
