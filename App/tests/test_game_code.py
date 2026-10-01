import struct
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fe_modding.game_code import versions
from fe_modding.game_code import entries, ppc, verify
from fe_modding.game_code.catalog import (CATALOG, CAVE_ADDRESS, CAVE_SIZE, Edit, Field, Patch, Session,
                                          State, Tunable, make_signature)
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
        self.assertEqual(ppc.fctiwz(0, 1), 0xFC00081E)
        self.assertEqual(ppc.stfd(0, 0x18, 1), 0xD8010018)
        self.assertEqual(ppc.andi_(0, 0, 1), 0x70000001)

    def test_assemble_resolves_labels(self):
        words = ppc.assemble(0x80001000, [("eq", "end"), ("bl", 0x80001100), "end", ppc.BLR])
        self.assertEqual(words, [ppc.bc("eq", 0x80001000, 0x80001008), ppc.bl(0x80001004, 0x80001100), ppc.BLR])


RETAIL_DIR = Path(__file__).resolve().parents[2] / "research" / "main_dol" / "dols"


class RetailCatalogTests(unittest.TestCase):
    """Every catalog entry against the real executables (skipped when they are not extracted)."""

    def test_catalog_entries_ids_are_unique_and_versioned(self):
        for entry in CATALOG.entries.values():
            self.assertEqual(set(entry.versions), set(entries.ALL), entry.id)

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

    def test_unknown_executable_is_not_editable(self):
        from fe_modding.game_code.editor import CodeEditor
        (self.root / "sys" / "boot.bin").write_bytes(b"GXXX01\x00\x00" + bytes(0x438))
        data = bytearray(self.retail)
        data[0x2700] ^= 0xFF
        (self.root / "sys" / "main.dol").write_bytes(bytes(data))
        editor = CodeEditor(self.root)
        self.assertFalse(editor.supported)
        self.assertEqual(editor.status(CATALOG.entries["combat.crit_multiplier"]).state, State.UNAVAILABLE)


if __name__ == "__main__":
    unittest.main()
