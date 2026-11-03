import struct
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

from fe_modding.formats import extended_flags as xf, save_file as sf
from tests.test_save_file import build_block, build_gci, unit_record


class LayoutTests(unittest.TestCase):
    def test_append_rename_and_delete_keep_slot_identity(self):
        layout = xf.FlagLayout().add("Unlocked", "campaign").add("Visited", "chapter", 18)
        identity = layout.identity
        renamed = layout.rename(layout.entries[0], "DoorUnlocked")
        self.assertEqual(renamed.entries[0].slot, 0)
        deleted = renamed.delete(renamed.entries[0]).add("Next", "campaign")
        self.assertEqual(deleted.entries[-1].slot, 1)
        self.assertEqual(deleted.identity, identity)
        self.assertEqual(deleted, xf.FlagLayout.from_json(deleted.to_json()))
        self.assertIsNone(deleted.find("DoorUnlocked"))

    def test_local_ids_are_independent_between_chapters(self):
        layout = xf.FlagLayout().add("Visited", "chapter", 18).add("Visited", "chapter", 19)
        self.assertEqual([e.slot for e in layout.entries], [0, 0])
        self.assertEqual(layout.find("Visited", 19).chapter, 19)
        self.assertIsNone(layout.find("Visited", 20))

    def test_capacity_includes_deleted_slots(self):
        for scope, chapter, capacity in (("campaign", None, 1024), ("chapter", 18, 256)):
            with self.subTest(scope=scope):
                layout = xf.FlagLayout(entries=(xf.FlagEntry("Last", scope, capacity - 1, chapter),))
                self.assertEqual(layout.remaining(scope, chapter), 0)
                layout = layout.delete(layout.entries[0])
                with self.assertRaises(ValueError):
                    layout.add("Overflow", scope, chapter)

    def test_names_and_slots_cannot_be_ambiguous(self):
        layout = xf.FlagLayout().add("Shared", "campaign")
        for scope, chapter in (("campaign", None), ("chapter", 18)):
            with self.assertRaises(ValueError):
                layout.add("Shared", scope, chapter)
        with self.assertRaises(ValueError):
            xf.FlagLayout(entries=(xf.FlagEntry("First", "campaign", 0),
                                   xf.FlagEntry("Second", "campaign", 0)))
        for name in ("HUB_ACTIVE", "gf_complete", "With\x00Nul", "With\rReturn"):
            with self.assertRaises(ValueError):
                layout.add(name, "campaign")

    def test_registrations_must_match_scope_and_not_collide_with_vanilla(self):
        layout = xf.FlagLayout().add("Extended", "chapter", 18)
        layout.validate_registrations(["Vanilla"], {18: ["Extended"]})
        for campaign, chapters in (([], {}), (["Extended"], {18: ["Extended"]}),
                                   ([], {18: ["Extended", "Extended"]})):
            with self.assertRaises(ValueError):
                layout.validate_registrations(campaign, chapters)

    def test_invalid_manifest_rejected(self):
        for raw in ('{}', '[]', '{"version":2,"identity":"x","entries":[]}',
                    '{"version":1,"identity":"00000000000000000000000000000000","entries":[]}'):
            with self.assertRaises(ValueError):
                xf.FlagLayout.from_json(raw)

    def test_compatibility_rejects_slot_moves_and_tombstone_reuse(self):
        original = xf.FlagLayout().add("One", "campaign").add("Two", "campaign")
        original.add("Three", "campaign").require_compatible(original)
        original.rename(original.entries[0], "Renamed").require_compatible(original)
        moved = replace(original, entries=(replace(original.entries[0], slot=1),
                                           replace(original.entries[1], slot=0)))
        with self.assertRaises(ValueError):
            moved.require_compatible(original)
        deleted = original.delete(original.entries[0])
        with self.assertRaises(ValueError):
            original.require_compatible(deleted)
        with self.assertRaises(ValueError):
            replace(original, entries=original.entries[1:]).require_compatible(original)


class PayloadTests(unittest.TestCase):
    def test_bit_order_boundaries_and_round_trip(self):
        layout = xf.FlagLayout()
        state = xf.ExtendedState.for_layout(layout)
        for scope, last in (("campaign", 1023), ("chapter", 255)):
            for slot in (0, 7, 8, last):
                state.set(scope, slot, True)
                self.assertTrue(state.get(scope, slot))
            self.assertEqual(getattr(state, scope)[0], 0x81)
            self.assertEqual(getattr(state, scope)[1], 1)
            with self.assertRaises(ValueError):
                state.set(scope, last + 1, True)
            with self.assertRaises(ValueError):
                state.get(scope, -1)
        state.hub_flag("HUB_ACTIVE", True)
        state.hub_flag("HUB_DEST_7", True)
        self.assertEqual(state.hub, bytes((1, 128, 0, 0)))
        state.hub_flag("HUB_DEST_7", False)
        raw = state.build()
        self.assertEqual(len(raw), 188)
        self.assertEqual(state, xf.ExtendedState.parse(raw))
        state.require_layout(layout.add("New", "campaign"))
        with self.assertRaises(ValueError):
            state.require_layout(xf.FlagLayout())

    def test_new_visit_clears_only_local_state(self):
        state = xf.ExtendedState.for_layout(xf.FlagLayout())
        state.set("campaign", 10, True)
        state.set("chapter", 10, True)
        state.hub_flag("HUB_STARTED", True)
        state.clear_chapter()
        self.assertTrue(state.get("campaign", 10))
        self.assertFalse(state.get("chapter", 10))
        self.assertTrue(state.hub_flag("HUB_STARTED"))

    def test_malformed_payload_fails_closed(self):
        raw = xf.ExtendedState.for_layout(xf.FlagLayout()).build()
        for offset in (0, 5, 7, 24, 27):
            broken = bytearray(raw)
            broken[offset] ^= 0x80
            with self.assertRaises(ValueError):
                xf.ExtendedState.parse(bytes(broken))
        for invalid in (b"", raw[:-1], raw + b"\0"):
            with self.assertRaises(ValueError):
                xf.ExtendedState.parse(invalid)


class ExtendedSaveTests(unittest.TestCase):
    def make_block(self, magic=b"FE8J"):
        block = sf.SaveBlock.parse(build_block([unit_record(1, 2)]), 0, 0x4000)
        block.header.magic = magic
        block.header.version = xf.SAVE_VERSIONS[magic]
        block.extended_flags = xf.ExtendedState.for_layout(xf.FlagLayout())
        block.extended_flags.set("chapter", 255, True)
        block.extended_flags.set("campaign", 1023, True)
        block.extended_flags.hub_flag("HUB_STARTED", True)
        return block

    def test_regional_round_trip_and_moving_variable_records(self):
        for magic in (b"FE8J", b"FE8X"):
            with self.subTest(magic=magic):
                block = self.make_block(magic)
                raw = block.build()
                loaded = sf.SaveBlock.parse(raw, 0, 0x4000)
                self.assertTrue(loaded.decoded, loaded.error)
                self.assertTrue(loaded.crc_ok)
                self.assertEqual(loaded.build(), raw)
                loaded.units[0] = None
                loaded.party.gold += 42
                moved = loaded.build()
                self.assertEqual(moved.index(xf.TAG), raw.index(xf.TAG) - 141)
                again = sf.SaveBlock.parse(moved, 0, 0x4000)
                self.assertTrue(again.crc_ok)
                self.assertEqual(again.extended_flags, block.extended_flags)

    def test_retarget_clears_locals_but_preserves_hub_and_campaign(self):
        save = sf.SaveFile.from_bytes(build_gci(self.make_block().build()))
        block = save.blocks[0]
        sf.retarget_to_chapter_start(block, 18)
        self.assertFalse(block.extended_flags.get("chapter", 255))
        self.assertTrue(block.extended_flags.get("campaign", 1023))
        self.assertTrue(block.extended_flags.hub_flag("HUB_STARTED"))

    def test_missing_extension_or_wrong_version_is_not_editable(self):
        raw = bytearray(self.make_block().build())
        at = raw.index(xf.TAG)
        raw[at:at + xf.RECORD_SIZE] = bytes(xf.RECORD_SIZE)
        invalid = sf.SaveBlock.parse(bytes(raw), 0, 0x4000)
        self.assertFalse(invalid.decoded)
        self.assertEqual(invalid.build(), raw)
        raw = bytearray(self.make_block().build())
        struct.pack_into(">I", raw, 0x44, sf.SAVE_VERSION)
        self.assertFalse(sf.SaveBlock.parse(bytes(raw), 0, 0x4000).decoded)

    def test_payload_cannot_be_written_under_retail_version(self):
        block = self.make_block()
        block.header.version = sf.SAVE_VERSION
        with self.assertRaises(ValueError):
            block.build()

    def test_overflow_does_not_change_original_bytes(self):
        block = self.make_block()
        original = block.raw
        block.units = [block.units[0]] * sf.UNIT_SLOTS
        with self.assertRaisesRegex(ValueError, "no longer fits"):
            block.build()
        self.assertEqual(block.raw, original)

    def test_future_version_and_bad_container_size_are_read_only(self):
        for offset, value in ((0x44, 0x54460103), (0x4C, 0x6000)):
            raw = bytearray(self.make_block().build())
            struct.pack_into(">I", raw, offset, value)
            block = sf.SaveBlock.parse(bytes(raw), 0, 0x4000)
            self.assertFalse(block.decoded)
            self.assertEqual(block.build(), raw)

    def test_exact_file_and_checkpoint_capacity_boundaries(self):
        for size, maximum in ((0x4000, 89), (0x6000, 147)):
            with self.subTest(size=size):
                block = self.make_block()
                block.size = block.header.size = size
                block.header.save_kind = 2 if size == 0x4000 else 3
                block.header.resume_point = 4 if size == 0x4000 else 8
                unit = block.units[0]
                block.units = [unit] * maximum + [None] * (sf.UNIT_SLOTS - maximum)
                raw = block.build()
                self.assertEqual(len(raw), size)
                loaded = sf.SaveBlock.parse(raw, 0, size)
                self.assertTrue(loaded.decoded, loaded.error)
                self.assertTrue(loaded.crc_ok)
                self.assertEqual(loaded.extended_flags, block.extended_flags)
                block.units[maximum] = unit
                with self.assertRaisesRegex(ValueError, "no longer fits"):
                    block.build()


class SaveEditorTests(unittest.TestCase):
    def test_extended_and_hub_toggles_mark_dirty_without_touching_retail_bits(self):
        from fe_modding.gui.pages.saves import SaveEditorPage
        state = xf.ExtendedState.for_layout(xf.FlagLayout())
        block = SimpleNamespace(extended_flags=state, decoded=True)
        for selected in ("ext:campaign:1023", "ext:chapter:255", "hub:HUB_STARTED"):
            updates, dirtied = [], []
            tree = SimpleNamespace(selection=lambda: (selected,), set=lambda *args: updates.append(args))
            editor = SimpleNamespace(block=block, _flag_tree=tree, mark_dirty=lambda: dirtied.append(True))
            SaveEditorPage._toggle_flag(editor)
            self.assertEqual(len(updates), 1)
            self.assertEqual(dirtied, [True])
        self.assertTrue(state.get("campaign", 1023))
        self.assertTrue(state.get("chapter", 255))
        self.assertTrue(state.hub_flag("HUB_STARTED"))


class ExtendedRouterTests(unittest.TestCase):
    def test_all_regions_route_using_only_the_separate_hub_state(self):
        from fe_modding.game_code import chapter_flow, hub_flow
        from tests.test_chapter_flow import MiniPPC, PARTY
        # Deliberately exercises signed low-half address materialization.
        state_address = 0x80408000
        cases = (
            # current, normal successor, control byte, dest, pending -> next, new pending, new dest
            (5, 6, 1, 0, 0, 40, 6, 0),
            (40, 40, 3, 8, 6, 8, 6, 8),
            (8, 9, 1, 8, 6, 40, 6, 8),
            (6, 7, 1, 6, 6, 40, 7, 6),
            (8, 9, 2, 8, 6, 6, 0, 0),  # STARTED alone must not activate routing
            (6, 7, 0, 6, 6, 7, 0, 0),
            (28, 29, 1, 28, 28, 29, 28, 28),
            (29, 30, 1, 28, 28, 40, 30, 28),
        )
        for region, sites in chapter_flow._SITES.items():
            target = sites[0]
            raw = hub_flow._router(target, hub_state_address=state_address)
            code = {hub_flow.HUB_HOOK + i: int.from_bytes(raw[i:i + 4], "big")
                    for i in range(0, len(raw), 4)}
            for current, normal, control, dest, pending, next_, new_pending, new_dest in cases:
                with self.subTest(region=region, current=current, control=control):
                    memory = {hub_flow.HUB_CONFIG: 40, PARTY + 0x10: current,
                              state_address: control, state_address + 1: dest,
                              state_address + 2: pending, state_address + 3: 0}
                    legacy = PARTY + hub_flow.FLAG_BITS_OFFSET
                    memory.update({legacy + i: 0xA5 for i in range(12)})
                    if current == 40:
                        memory[PARTY + hub_flow.HISTORY_OFFSET] = 5
                        memory[PARTY + hub_flow.HISTORY_OFFSET + 8] = 40
                    cpu = MiniPPC(code, memory)
                    cpu.r[3], cpu.r[4] = PARTY, normal
                    self.assertEqual(cpu.run(hub_flow.HUB_HOOK, {target}), target)
                    self.assertEqual((cpu.r[4], memory[state_address + 2], memory[state_address + 1]),
                                     (next_, new_pending, new_dest))
                    self.assertEqual([memory[legacy + i] for i in range(12)], [0xA5] * 12)
                    self.assertEqual(memory[state_address], control)
                    if current == 40:
                        self.assertEqual(memory[PARTY + hub_flow.HISTORY_OFFSET], 5)
                        self.assertEqual(memory[PARTY + hub_flow.HISTORY_OFFSET + 8], 0)


class ReleaseGateTests(unittest.TestCase):
    def test_manifest_projects_cannot_build_or_write_scripts_without_runtime(self):
        from fe_modding.exceptions import ProjectError
        from fe_modding.game_code.extended_flags import require_project_runtime
        from fe_modding import hub, script_sources
        from fe_modding.project import ModProject
        with tempfile.TemporaryDirectory() as tmp:
            project = SimpleNamespace(directory=Path(tmp))
            require_project_runtime(project)
            path = project.directory / xf.MANIFEST_NAME
            source = xf.FlagLayout().to_json()
            path.write_text(source, encoding="utf-8")
            for operation in (lambda: require_project_runtime(project), lambda: ModProject.build(project),
                              lambda: script_sources.save(project, None, ""), lambda: hub.prepare(project, None)):
                with self.assertRaisesRegex(ProjectError, "not approved"):
                    operation()
            self.assertEqual(path.read_text(encoding="utf-8"), source)
            self.assertEqual(list(Path(tmp).iterdir()), [path])

    def test_runtime_release_approval_is_regional_and_not_a_catalog_patch(self):
        from fe_modding.game_code.catalog import Session, State
        from fe_modding.game_code.dol import Dol, DolError
        from fe_modding.game_code.extended_flags import EXTENDED_FLAGS_PATCH
        from fe_modding.game_code.versions import VERSIONS
        root = Path(__file__).resolve().parents[2] / "research" / "main_dol" / "dols"
        self.assertEqual(set(EXTENDED_FLAGS_PATCH.versions), {"GFEE01", "GFEP01"})
        path = root / "GFEJ01.dol"
        if not path.is_file():
            self.skipTest("retail GFEJ01 DOL is not available")
        dol = Dol.open(path)
        before = bytes(dol.data)
        session = Session(dol, VERSIONS["GFEJ01"])
        self.assertEqual(session.status(EXTENDED_FLAGS_PATCH).state, State.UNAVAILABLE)
        with self.assertRaises(DolError):
            session.set_patch(EXTENDED_FLAGS_PATCH, True)
        self.assertEqual(bytes(dol.data), before)


if __name__ == "__main__":
    unittest.main()
