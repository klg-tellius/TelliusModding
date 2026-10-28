import importlib.util
import json
from pathlib import Path
import tempfile
import struct
import unittest
from unittest.mock import patch
from types import SimpleNamespace

from fe_modding.formats.cmb import compile_source, read_cmb, write_cmb, decompile
from fe_modding.formats.extended_flags import FlagLayout, FlagCompileContext, ExtendedState, SAVE_VERSIONS, MANIFEST_NAME
from fe_modding.formats.save_file import SaveFile
from tests.test_save_file import build_block, build_gci


def tool(name):
    path = Path(__file__).resolve().parents[1] / "tools" / (name + ".py")
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class PlaytestTests(unittest.TestCase):
    def test_fast_finish_only_applies_once_to_connected_chapters(self):
        build = tool("prepare_extended_flag_playtest")
        sources = {Path(f"C{cid:02d}.cmb"): '@export\ndef Startup():\n    pass\n'
                   for cid in (1, 2, 3, 18, 33)}
        setup = SimpleNamespace(destinations=[SimpleNamespace(chapter=cid) for cid in (2, 3, 18)])
        project = SimpleNamespace(extracted_dir=Path("extracted"))
        def write(_project, path, source, _layout):
            sources[path] = source
        with patch.object(build.script_sources, "chapter_script", side_effect=lambda _p, cid: Path(f"C{cid}.cmb")), \
             patch.object(build.script_sources, "peek", side_effect=lambda _p, path: sources[path]), \
             patch.object(build, "write_script", side_effect=write) as writer, \
             patch("fe_modding.game_code.editor.CodeEditor") as editor:
            build.apply_test_quality_of_life(project, setup, FlagLayout())
            build.apply_test_quality_of_life(project, setup, FlagLayout())
            self.assertEqual(writer.call_count, 3)
            self.assertEqual(editor.return_value.set_value.call_args.args[1], 2.0)
        for cid in (2, 3, 18):
            text = sources[Path(f"C{cid:02d}.cmb")]
            self.assertIn('@on_phase(turn_from=1, turn_to=1, phase="enemy")', text)
            self.assertEqual(text.count('set("gf_complete")'), 1)
            compile_source(text)
        for cid in (1, 33):
            self.assertNotIn("gf_complete", sources[Path(f"C{cid:02d}.cmb")])

    def test_multipart_fast_finish_ends_the_current_part(self):
        # Setting gf_complete in part 1 ran Chapter 17's final ending, whose UnitBreakup(Ike)
        # read through a null partner. Each part must end on its own goal flag instead.
        build = tool("prepare_extended_flag_playtest")
        source = (
            '@export\ndef Startup():\n    regist("C1")\n    regist("C2")\n    regist("S2")\n\n'
            '@on_complete(flag="C1")\ndef func_1():\n    clr("C1")\n\n    Complete18(1)\n\n'
            '@export\ndef Opening18_2():\n    set("S2")\n    if get("C1"):\n        set("Other")\n\n'
            '@on_complete(flag="C2")\ndef func_2():\n    Complete18(2)\n\n'
            '@export\ndef Opening18_3():\n    set("S3")\n\n'
            '@on_complete(flag="gf_complete")\ndef func_3():\n    pass\n'
            '\n# XFT automatic test victory\n@on_phase(turn_from=1, turn_to=1, phase="enemy")\n'
            'def XftFinishAfterPlayerTurnOne():\n    set("gf_complete")\n')
        self.assertEqual(build.part_goals(source, 18), [("S3", "gf_complete"), ("S2", "C2"), (None, "C1")])
        setup = SimpleNamespace(destinations=[SimpleNamespace(chapter=18)])
        sources = {Path("C18.cmb"): source}
        with patch.object(build.script_sources, "chapter_script", side_effect=lambda _p, cid: Path(f"C{cid}.cmb")), \
             patch.object(build.script_sources, "peek", side_effect=lambda _p, path: sources[path]), \
             patch.object(build, "write_script", side_effect=lambda _p, path, text, _l: sources.__setitem__(path, text)), \
             patch("fe_modding.game_code.editor.CodeEditor"):
            build.apply_test_quality_of_life(SimpleNamespace(extracted_dir=Path("extracted")), setup, FlagLayout())
        text = sources[Path("C18.cmb")]
        self.assertEqual(text.count(build.VICTORY_MARKER), 1)
        handler = text[text.index(build.VICTORY_MARKER):]
        self.assertIn('    if get("S3"):\n        set("gf_complete")\n', handler)
        self.assertIn('    elif get("S2"):\n        set("C2")\n', handler)
        self.assertIn('    else:\n        set("C1")\n', handler)
        compile_source(text)

    def test_boot_archive_uses_edited_startup_and_chapter_database(self):
        build = tool("prepare_extended_flag_playtest")
        from fe_modding.project import ModProject
        from fe_modding.games import Game
        from fe_modding.formats import lz10, pak
        with tempfile.TemporaryDirectory() as tmp:
            project = ModProject.create(Path(tmp), "fixture", Game.PATH_OF_RADIANCE)
            project.files_dir.mkdir()
            (project.files_dir / "scripts").mkdir()
            (project.files_dir / "scripts/startup.cmb").write_bytes(b"new campaign registrations")
            (project.files_dir / "FE8Data.bin").write_bytes(b"new hub chapter record")
            original = pak.pack_pak([("scripts/startup.cmb", b"old registrations"),
                                     ("FE8Data.bin", b"old chapter table")], [0, 0])
            project.logical_path("system_archive").write_bytes(lz10.compress(original))
            self.assertEqual(set(build.sync_boot_archive(project)), {"scripts/startup.cmb", "FE8Data.bin"})
            unpacked = lz10.decompress(project.logical_path("system_archive").read_bytes())
            for entry in pak.read_pak_entries(unpacked):
                self.assertEqual(pak.read_pak_file_content(unpacked, entry),
                                 (project.files_dir / entry.name).read_bytes())
            self.assertEqual(build.sync_boot_archive(project), [])

    def test_packaged_executable_check_rejects_wrong_bytes(self):
        build = tool("prepare_extended_flag_playtest")
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "fixture.ciso"
            boot = bytearray(0x440)
            boot[:6] = b"GFEE01"
            struct.pack_into(">I", boot, 0x420, 0x1000)
            expected = b"verified executable"
            build.gcdisc._write_ciso(path, iter(((0, bytes(boot)), (0x1000, expected))), 0x2000)
            build.verify_packaged_executable(path, expected, "GFEE01")
            with self.assertRaisesRegex(ValueError, "differs"):
                build.verify_packaged_executable(path, b"wrong", "GFEE01")

    def test_probe_compiles_without_automatic_writes(self):
        build = tool("prepare_extended_flag_playtest")
        layout = FlagLayout()
        for name in build.CAMPAIGN:
            layout = layout.add(name, "campaign")
        for name in build.LOCALS:
            layout = layout.add(name, "chapter", 1)
        source = '@export\ndef Startup():\n' + ''.join(f'    regist("{name}")\n' for name in build.LOCALS)
        source += build.probe_source()
        compiled = compile_source(source, global_flags=build.CAMPAIGN, flag_context=FlagCompileContext(layout, 1))
        result = decompile(read_cmb(write_cmb(compiled.script)))[0]
        self.assertIn('MS_XFT_CAMPAIGN_SET', result)
        self.assertIn('MS_XFT_LOCAL_MIXED', result)
        self.assertNotIn('@on_phase', result)
        self.assertNotIn('@after_action', result)

    def test_inspector_reads_saved_values_without_modifying_card(self):
        inspect = tool("inspect_extended_flag_playtest").inspect
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            region = root / "GFEE01"
            card = region / "DolphinUser/GC/USA/Card A"
            card.mkdir(parents=True)
            layout = FlagLayout()
            (region / MANIFEST_NAME).write_text(layout.to_json(), encoding="utf-8")
            save = SaveFile.from_bytes(build_gci(build_block([])))
            block = save.blocks[0]
            block.header.version = SAVE_VERSIONS[block.header.magic]
            block.extended_flags = ExtendedState.for_layout(layout)
            block.extended_flags.set("campaign", 99, True)
            block.extended_flags.set("chapter", 79, True)
            path = card / "fixture.gci"
            path.write_bytes(save.to_bytes())
            before = path.read_bytes()
            result = inspect(root)["GFEE01"][0]["blocks"][0]
            self.assertTrue(result["crc_ok"])
            self.assertTrue(result["layout_matches"])
            self.assertEqual(result["campaign_probe_set"], 1)
            self.assertEqual(result["local_first_80_set"], 1)
            self.assertEqual(path.read_bytes(), before)

    def test_builder_refuses_existing_output_before_any_writes(self):
        build = tool("prepare_extended_flag_playtest")
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            sentinel = root / "existing-save.gci"
            sentinel.write_bytes(b"do not overwrite")
            args = ["prepare", "--output", tmp, "--source-root", tmp, "--dolphin", tmp,
                    "--controller-config", tmp]
            with patch("sys.argv", args), self.assertRaises(SystemExit):
                build.main()
            self.assertEqual(sentinel.read_bytes(), b"do not overwrite")


if __name__ == "__main__":
    unittest.main()
