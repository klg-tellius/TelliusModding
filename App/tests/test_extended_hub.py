import copy
import unittest
import tempfile
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from fe_modding import hub
from fe_modding.extended_hub import prepare_migration, prepare_project_update
from fe_modding.formats import event_flags as ef
from fe_modding.formats.extended_flags import FlagLayout, HUB_ALIASES
from fe_modding.formats.cmb.decompiler import quote
from fe_modding.formats.cmb.parser import parse


class HubMigrationTests(unittest.TestCase):
    def fixture(self, extra_global=True):
        names = [name for name, _ in ef.VANILLA_GLOBAL_FLAGS]
        if extra_global:
            names.append("custom_before_hub")
        start = len(ef.ENGINE_FLAGS) + len(names)
        flags, destination = hub.flag_names(start)
        names += flags + ["custom_after_hub"]
        source = "# keep this comment\ndef RegistGlobalFlags():\n" + "".join(
            f'    extern("global", {quote(name)})\n' for name in names)
        setup = hub.HubSetup(40, 5, "PID_HUB", (hub.Destination(8, 1, 2, 3, 4),))
        chapters = {
            5: hub.activation_script("def Startup():\n    regist(\"activation_local\")\n"),
            40: hub.hub_script("def Startup():\n    regist(\"hub_local\")\n", setup),
            18: "def Startup():\n" + "".join(f"    regist(\"local_{i}\")\n" for i in range(58)),
        }
        config = {"version": 2, "chapter": 40, "activation_chapter": 5, "flags": flags,
                  "slots": {"active": start, "destination": destination, "pending": destination + 8},
                  "normal_successor": 41, "destinations": [{"chapter": 8}]}
        return source, chapters, config

    def test_removes_only_padding_and_preserves_scripts_and_configuration(self):
        for padded in (False, True):
            source, chapters, config = self.fixture(padded)
            original = copy.deepcopy(config)
            original_chapters = dict(chapters)
            layout = FlagLayout()
            result = prepare_migration(source, chapters, config, layout)
            self.assertEqual(config, original)
            self.assertEqual(chapters, original_chapters)
            expected = [name for name in ef.global_flags(parse(source)) if not name.startswith("HUB_")]
            self.assertEqual(list(result.vanilla_globals), expected)
            self.assertEqual(len(result.removed_padding), 7 if padded else 0)
            globals_ = ef.global_flags(parse(result.startup_source))
            self.assertTrue(all(globals_.count(name) == 1 for name in HUB_ALIASES))
            self.assertTrue(result.startup_source.startswith("# keep this comment\n"))
            self.assertEqual(result.configuration["storage"], "extended")
            self.assertEqual(result.configuration["layout_identity"], layout.identity)
            self.assertNotIn("slots", result.configuration)
            self.assertEqual(result.configuration["normal_successor"], 41)
            result.configuration["destinations"][0]["chapter"] = 9
            self.assertEqual(config, original)

    def test_rejects_changed_layout_duplicates_and_padding_used_as_logic(self):
        for issue in ("slot", "order", "duplicate", "logic", "missing"):
            source, chapters, config = self.fixture()
            if issue == "slot":
                config["slots"]["pending"] += 1
            elif issue == "order":
                source = source.replace('extern("global", "HUB_ACTIVE")', 'extern("global", "wrong_name")')
            elif issue == "duplicate":
                source += '    extern("global", "HUB_ACTIVE")\n'
            elif issue == "logic":
                chapters[18] += '    set("HUB_PAD_0")\n'
            else:
                del chapters[40]
            with self.subTest(issue=issue), self.assertRaises(ValueError):
                prepare_migration(source, chapters, config, FlagLayout())

    def test_two_extended_flags_and_remaining_vanilla_budget(self):
        source, chapters, config = self.fixture()
        layout = FlagLayout().add("new_a", "chapter", 18).add("new_b", "chapter", 18)
        chapters[18] += '    regist("new_a")\n    regist("new_b")\n'
        result = prepare_migration(source, chapters, config, layout)
        self.assertEqual(len(result.vanilla_globals), 32)
        self.assertEqual(ef.local_flags(parse(chapters[18]))[-2:], ["new_a", "new_b"])
        chapters[18] += "".join(f'    regist("overflow_{i}")\n' for i in range(6))
        from fe_modding.formats.cmb import CompileError
        with self.assertRaises(CompileError):
            prepare_migration(source, chapters, config, layout)

    def test_project_proposal_contains_matching_files_and_detects_stale_inputs(self):
        from fe_modding import script_sources, chapters as chapter_api
        from fe_modding.formats.cmb import compile_source, write_cmb, read_cmb
        from fe_modding.game_code.dol import Dol
        from fe_modding.game_code.extended_flag_runtime import RECORD_OFFSET, BASE
        retail = Path(__file__).resolve().parents[2] / "research/main_dol/dols/GFEE01.dol"
        if not retail.exists():
            self.skipTest("retail DOL unavailable")
        source, chapters, config = self.fixture()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project = SimpleNamespace(directory=root, extracted_dir=root / "extracted")
            system = project.extracted_dir / "sys"
            system.mkdir(parents=True)
            (system / "main.dol").write_bytes(retail.read_bytes())
            (system / "boot.bin").write_bytes(b"GFEE01\0\0" + bytes(0x438))
            (root / "hub.json").write_text(json.dumps(config))
            startup = root / "startup.cmb"
            sources = {startup: source, **{root / f"C{cid}.cmb": text for cid, text in chapters.items()}}
            for path, text in sources.items():
                path.write_bytes(write_cmb(compile_source(text).script))
                path.with_suffix(".txt").write_text(text, encoding="utf-8")
            before = {p: p.read_bytes() for p in root.rglob("*") if p.is_file()}
            layout = FlagLayout()
            with patch.object(script_sources, "startup_path", return_value=startup), \
                 patch.object(script_sources, "chapter_script", side_effect=lambda p, cid: root / f"C{int(cid)}.cmb"), \
                 patch.object(script_sources, "sidecar_path", side_effect=lambda p, path: path.with_suffix(".txt")), \
                 patch.object(script_sources, "peek", side_effect=lambda p, path: path.with_suffix(".txt").read_text(encoding="utf-8")), \
                 patch.object(chapter_api, "list_chapter_ids", return_value=list(map(str, chapters))):
                update = prepare_project_update(project, layout)
            self.assertEqual({p: p.read_bytes() for p in root.rglob("*") if p.is_file()}, before)
            self.assertEqual(len(update.changes), 6)
            outputs = {change.path: change.after for change in update.changes}
            self.assertEqual(json.loads(outputs[root / "extended_flags.json"])["identity"], layout.identity)
            self.assertEqual(json.loads(outputs[root / "hub.json"])["layout_identity"], layout.identity)
            executable = Dol(outputs[system / "main.dol"])
            self.assertEqual(executable.read(BASE + RECORD_OFFSET + 8, 16), bytes.fromhex(layout.identity))
            self.assertIsNotNone(read_cmb(outputs[startup]))
            update.verify_unchanged()
            (root / "C18.txt").write_text("# changed after review\n")
            with self.assertRaisesRegex(ValueError, "changed after"):
                update.verify_unchanged()


if __name__ == "__main__":
    unittest.main()
