from pathlib import Path
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from fe_modding.project import ModProject
from fe_modding.games import Game
from fe_modding.formats.extended_flags import FlagLayout, MANIFEST_NAME
from fe_modding.formats.cmb import compile_source, write_cmb
from fe_modding.formats.event_flags import VANILLA_GLOBAL_FLAGS
from fe_modding.formats.cmb.decompiler import quote
from fe_modding.game_code.dol import Dol
from fe_modding.game_code.extended_flag_candidate import build_candidate
from fe_modding.game_code.extended_flag_installation import receipt_for, RECEIPT_NAME, inspect_project, RuntimeState
from fe_modding.extended_project import prepare_runtime_update
from fe_modding.extended_hub import commit_project_update
from fe_modding import script_sources


class ExtendedProjectTests(unittest.TestCase):
    def setUp(self):
        retail = Path(__file__).resolve().parents[2] / "research/main_dol/dols/GFEE01.dol"
        if not retail.exists():
            self.skipTest("retail DOL unavailable")
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.project = ModProject.create(Path(self.temp.name), "extended", Game.PATH_OF_RADIANCE)
        self.root = self.project.directory
        self.layout = FlagLayout().add("local_custom", "chapter", 18)
        candidate = build_candidate(Dol.open(retail), "GFEE01", self.layout)
        system = self.project.extracted_dir / "sys"
        system.mkdir(parents=True)
        (system / "main.dol").write_bytes(candidate.executable)
        (system / "boot.bin").write_bytes(b"GFEE01")
        (self.root / MANIFEST_NAME).write_text(self.layout.to_json(), encoding="utf-8")
        (self.root / RECEIPT_NAME).write_text(receipt_for(candidate, self.layout), encoding="utf-8")
        folder = self.project.extracted_dir / "files"
        (folder / "Scripts").mkdir(parents=True)
        (folder / "Mess").mkdir()
        (folder / "Mess/c18.m").write_bytes(b"")
        self.startup = folder / "Scripts/startup.cmb"
        self.chapter = folder / "Scripts/C18.cmb"
        self.startup_source = "@export\ndef RegistGlobalFlags():\n" + "".join(
            f'    extern("global", {quote(name)})\n' for name, _ in VANILLA_GLOBAL_FLAGS)
        self.chapter_source = '@export\ndef Startup():\n    regist("local_custom")\n'
        for path, source in ((self.startup, self.startup_source), (self.chapter, self.chapter_source)):
            path.write_bytes(write_cmb(compile_source(source).script))
        self.approval = patch("fe_modding.game_code.extended_flags.EXTENDED_FLAGS_PATCH",
                              SimpleNamespace(versions={"GFEE01": ()}))

    def test_layout_and_registration_commit_together_and_plain_save_keeps_executable(self):
        before = {p: p.read_bytes() for p in self.root.rglob("*") if p.is_file()}
        new = self.layout.add("campaign_custom", "campaign")
        source = self.startup_source + '    extern("global", "campaign_custom")\n'
        update = prepare_runtime_update(self.project, new, {self.startup: source})
        self.assertEqual(len(update.changes), 5)
        self.assertEqual({p: p.read_bytes() for p in self.root.rglob("*") if p.is_file()}, before)
        with self.approval:
            commit_project_update(self.project, update)
            self.assertEqual(inspect_project(self.project).state, RuntimeState.MATCHING)
            executable = self.project.extracted_dir / "sys/main.dol"
            native = executable.read_bytes()
            loaded = script_sources.load(self.project, self.chapter)
            script_sources.save(self.project, loaded, self.chapter_source + '\ndef Event():\n    set("local_custom")\n')
            self.assertEqual(executable.read_bytes(), native)
        self.assertEqual(inspect_project(self.project).layout, new)

    def test_missing_registration_and_stale_inputs_are_rejected(self):
        new = self.layout.add("missing", "chapter", 18)
        with self.assertRaises(ValueError):
            prepare_runtime_update(self.project, new)
        update = prepare_runtime_update(self.project, self.layout, {self.chapter: self.chapter_source})
        self.startup.write_bytes(b"changed")
        with self.assertRaises(ValueError):
            update.verify_unchanged()

    def test_new_chapter_inventory_invalidates_reviewed_update(self):
        update = prepare_runtime_update(self.project, self.layout, {self.chapter: self.chapter_source})
        (self.chapter.parent / "C19.cmb").write_bytes(self.chapter.read_bytes())
        with self.assertRaisesRegex(ValueError, "inventory changed"):
            update.verify_unchanged()

    def test_new_flags_default_to_extended_and_vanilla_is_explicit(self):
        from fe_modding.extended_project import prepare_flag_add
        extended = prepare_flag_add(self.project, "extra", "chapter", chapter=18)
        outputs = {change.path: change.after for change in extended.changes}
        layout = FlagLayout.from_json(outputs[self.root / MANIFEST_NAME].decode("utf-8"))
        self.assertEqual(layout.find("extra", 18).slot, 1)
        vanilla = prepare_flag_add(self.project, "extra", "chapter", chapter=18, storage="vanilla")
        self.assertNotIn(self.root / MANIFEST_NAME, {change.path for change in vanilla.changes})
        with self.assertRaises(ValueError):
            prepare_flag_add(self.project, "HUB_ACTIVE", "campaign")

    def test_rename_and_retire_keep_slot_and_do_not_reuse_it(self):
        from fe_modding.extended_project import prepare_flag_edit, prepare_flag_add
        with self.approval:
            commit_project_update(self.project, prepare_flag_edit(self.project, "local_custom", chapter=18, new_name="renamed"))
            self.assertEqual(inspect_project(self.project).layout.find("renamed", 18).slot, 0)
            self.assertIn('regist("renamed")', script_sources.peek(self.project, self.chapter))
            commit_project_update(self.project, prepare_flag_edit(self.project, "renamed", chapter=18))
            self.assertTrue(inspect_project(self.project).layout.entries[0].deleted)
            commit_project_update(self.project, prepare_flag_add(self.project, "replacement", "chapter", chapter=18))
            self.assertEqual(inspect_project(self.project).layout.find("replacement", 18).slot, 1)

    def test_referenced_flag_cannot_be_retired(self):
        from fe_modding.extended_project import prepare_flag_edit
        source = self.chapter_source + '    set("local_custom")\n'
        self.chapter.write_bytes(write_cmb(compile_source(source).script))
        before = self.chapter.read_bytes()
        with self.assertRaisesRegex(ValueError, "referenced"):
            prepare_flag_edit(self.project, "local_custom", chapter=18)
        self.assertEqual(self.chapter.read_bytes(), before)

    def test_precise_reference_rewriting(self):
        from fe_modding.formats.event_flags import rename_flag_references
        source = ('# set("old")\n@on_talk(name="old", pid1="old", pid2="PID_B")\n'
                  'def Event():\n    set(\n        "old"\n    ) # "old"\n'
                  '    extern("Message", "old")\n    clr("old")\n')
        result = rename_flag_references(source, "old", "new")
        self.assertIn('name="new", pid1="old"', result)
        self.assertIn('        "new"\n', result)
        self.assertIn('extern("Message", "old")', result)
        self.assertIn('# set("old")', result)
        self.assertIn('clr("new")', result)
        with self.assertRaisesRegex(ValueError, "Dynamic"):
            rename_flag_references('def Event(x):\n    set(x)\n', "old", "new")

    def test_campaign_rename_updates_other_scripts_atomically(self):
        from fe_modding.extended_project import prepare_flag_edit, prepare_flag_add
        with self.approval:
            commit_project_update(self.project, prepare_flag_add(self.project, "campaign_custom", "campaign"))
            loaded = script_sources.load(self.project, self.chapter)
            script_sources.save(self.project, loaded, self.chapter_source + '    set("campaign_custom")\n')
            update = prepare_flag_edit(self.project, "campaign_custom", new_name="campaign_renamed")
            paths = {change.path for change in update.changes}
            self.assertIn(self.chapter, paths)
            self.assertIn(self.startup, paths)
            commit_project_update(self.project, update)
            self.assertIn('set("campaign_renamed")', script_sources.peek(self.project, self.chapter))
            self.assertEqual(inspect_project(self.project).layout.find("campaign_renamed").slot, 0)

    def test_shared_local_reference_and_stale_rename_are_rejected(self):
        from fe_modding.extended_project import prepare_flag_edit
        update = prepare_flag_edit(self.project, "local_custom", chapter=18, new_name="renamed")
        source = self.startup_source + '\ndef Helper():\n    set("local_custom")\n'
        self.startup.write_bytes(write_cmb(compile_source(source).script))
        with self.assertRaisesRegex(ValueError, "changed"):
            update.verify_unchanged()
        with self.assertRaisesRegex(ValueError, "Shared scripts"):
            prepare_flag_edit(self.project, "local_custom", chapter=18, new_name="renamed")


if __name__ == "__main__":
    unittest.main()
