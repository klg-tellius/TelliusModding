import hashlib
import unittest
from pathlib import Path

from fe_modding.formats.extended_flags import FlagLayout
from fe_modding.game_code.dol import Dol, DolError
from fe_modding.game_code.extended_flag_candidate import build_candidate
from fe_modding.game_code.extended_flag_versions import SITES

RETAIL = Path(__file__).resolve().parents[2] / "research/main_dol/dols"


class CandidateTests(unittest.TestCase):
    def test_hub_candidate_routes_from_separate_bytes_and_preserves_story_flow(self):
        from fe_modding.game_code.catalog import Session
        from fe_modding.game_code.versions import VERSIONS
        from fe_modding.game_code import chapter_flow as flow, hub_flow as hub
        from tests.test_chapter_flow import MiniPPC, PARTY
        for region in SITES:
            if not (RETAIL / f"{region}.dol").exists():
                self.skipTest("retail DOL unavailable")
            for existing_hub in (False, True):
                dol = Dol.open(RETAIL / f"{region}.dol")
                session = Session(dol, VERSIONS[region])
                session.set_patch(flow.FLOW_PATCH, True)
                session._write(flow.FLOW_TABLE + 5, b"\x08")
                if existing_hub:
                    session.set_patch(hub.HUB_PATCH, True)
                    session._write(hub.HUB_CONFIG, hub.validate_slots(40, 30, 32, 40))
                before = bytes(dol.data)
                candidate = build_candidate(dol, region, FlagLayout(), hub_chapter=40)
                patched = Dol(candidate.executable)
                self.assertEqual(bytes(dol.data), before)
                self.assertEqual(patched.read(flow.FLOW_TABLE + 5, 1), b"\x08")
                self.assertEqual(patched.read(flow.FLOW_TABLE + 40, 1), b"\x28")
                code = {at: patched.u32(at) for at in range(hub.HUB_HOOK, hub.HUB_CONFIG, 4)}
                state = candidate.image.hub_address
                memory = {hub.HUB_CONFIG: 40, PARTY + 0x10: 5,
                          state: 1, state + 1: 0, state + 2: 0}
                for i in range(12):
                    memory[PARTY + hub.FLAG_BITS_OFFSET + i] = 0xA5
                cpu = MiniPPC(code, memory)
                cpu.r[3], cpu.r[4] = PARTY, 8
                target = flow._SITES[region][0]
                self.assertEqual(cpu.run(hub.HUB_HOOK, {target}), target)
                self.assertEqual(cpu.r[4], 40)
                self.assertEqual(memory[state + 2], 8)
                self.assertEqual([memory[PARTY + hub.FLAG_BITS_OFFSET + i] for i in range(12)], [0xA5] * 12)

    def test_full_normal_card_candidate_round_trip_all_regions(self):
        for region in SITES:
            if not (RETAIL / f"{region}.dol").exists():
                self.skipTest("retail DOL unavailable")
            dol = Dol.open(RETAIL / f"{region}.dol")
            original = bytes(dol.data)
            layout = FlagLayout()
            candidate = build_candidate(dol, region, layout)
            patched = Dol(candidate.executable)
            image = candidate.image
            self.assertEqual(candidate.source_sha256, hashlib.sha256(original).hexdigest())
            self.assertEqual(candidate.layout_identity, layout.identity)
            self.assertEqual(bytes(dol.data), original)
            self.assertEqual(patched.read(image.base, len(image.data)), image.data)
            for name in ("file_save_guard", "file_save_append", "checkpoint_guard", "new_game_append",
                         "card_open_guard", "block_version_finalize"):
                self.assertIn(name, image.functions)
            for edit in image.edits:
                self.assertEqual(patched.read(edit.address, len(edit.patched)), edit.patched)
                patched.write(edit.address, edit.original)
            patched.remove_section_at(image.base)
            self.assertEqual(bytes(patched.data), original)

    def test_late_validation_failure_leaves_source_unchanged(self):
        for region in SITES:
            if not (RETAIL / f"{region}.dol").exists():
                self.skipTest("retail DOL unavailable")
            dol = Dol.open(RETAIL / f"{region}.dol")
            # This comparison is not guarded by earlier writer fragments.
            dol.write(SITES[region]["compare"][0][0], bytes(4))
            original = bytes(dol.data)
            with self.assertRaises(DolError):
                build_candidate(dol, region, FlagLayout())
            self.assertEqual(bytes(dol.data), original)

    def test_hub_conflicts_leave_original_executable_untouched(self):
        from fe_modding.game_code.catalog import Session
        from fe_modding.game_code.versions import VERSIONS
        from fe_modding.game_code import chapter_flow as flow, hub_flow as hub
        path = RETAIL / "GFEE01.dol"
        if not path.exists():
            self.skipTest("retail DOL unavailable")
        for conflict in ("tail", "padding", "chapter"):
            dol = Dol.open(path)
            session = Session(dol, VERSIONS["GFEE01"])
            session.set_patch(flow.FLOW_PATCH, True)
            session.set_patch(hub.HUB_PATCH, True)
            session._write(hub.HUB_CONFIG, hub.validate_slots(40, 30, 32, 40))
            if conflict == "tail":
                session._write(hub.HUB_PATCH.versions["GFEE01"][0].address, bytes(4))
            elif conflict == "padding":
                session._write(hub.HUB_CONFIG - 4, b"test")
            original = bytes(dol.data)
            with self.assertRaises((DolError, ValueError)):
                build_candidate(dol, "GFEE01", FlagLayout(), hub_chapter=41 if conflict == "chapter" else 40)
            self.assertEqual(bytes(dol.data), original)


if __name__ == "__main__":
    unittest.main()
