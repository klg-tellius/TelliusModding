import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fe_modding import hub
from fe_modding import chapters, script_sources
from fe_modding.formats import dispo, fe8data, lz10, pak
from fe_modding.formats.cmb import compile_source, read_cmb, write_cmb
from fe_modding.game_code import chapter_flow, hub_flow
from fe_modding.game_code.catalog import CAVE_ADDRESS, State
from fe_modding.game_code.editor import CodeEditor
from tests.test_chapter_flow import MiniPPC, PARTY, RETAIL_DIR, _code


class HubRouterTests(unittest.TestCase):
    def setUp(self):
        self.code = _code("GFEE01")
        for edit in hub_flow.HUB_PATCH.versions["GFEE01"]:
            if edit.address >= CAVE_ADDRESS and edit.address != hub_flow.HUB_CONFIG:
                for i in range(0, len(edit.patched), 4):
                    self.code[edit.address + i] = int.from_bytes(edit.patched[i:i + 4], "big")
        self.set_chapter = chapter_flow._SITES["GFEE01"][0]

    def route(self, current, normal, *, active=True, destination=0, pending=0, history=()):
        config = hub_flow.validate_slots(40, 30, 32, 40)
        memory = {hub_flow.HUB_CONFIG + i: b for i, b in enumerate(config)}
        memory[PARTY + 0x10] = current
        bits = PARTY + hub_flow.FLAG_BITS_OFFSET
        memory[bits + 3] = 0x40 if active else 0
        memory[bits + 4] = destination
        memory[bits + 5] = pending
        for i, chapter in enumerate(history):
            memory[PARTY + hub_flow.HISTORY_OFFSET + i * 8] = chapter
        cpu = MiniPPC(self.code, memory)
        cpu.r[3], cpu.r[4] = PARTY, normal
        self.assertEqual(cpu.run(chapter_flow.FLOW_HOOK, {self.set_chapter}), self.set_chapter)
        return cpu.r[4], memory[bits + 5], memory[bits + 4], memory

    def test_activation_selection_return_and_story_advance(self):
        self.assertEqual(self.route(5, 6)[:3], (40, 6, 0))
        self.assertEqual(self.route(40, 40, destination=8, pending=6)[:3], (8, 6, 8))
        self.assertEqual(self.route(8, 9, destination=8, pending=6)[:3], (40, 6, 8))
        self.assertEqual(self.route(6, 7, destination=6, pending=6)[:3], (40, 7, 6))

    def test_disabling_hub_resumes_pending_story(self):
        self.assertEqual(self.route(8, 9, active=False, destination=8, pending=6)[:3], (6, 0, 0))
        self.assertEqual(self.route(6, 7, active=False, destination=6, pending=6)[:3], (7, 0, 0))

    def test_multipart_chapter_stays_together(self):
        self.assertEqual(self.route(28, 29, pending=28)[:3], (29, 28, 0))
        self.assertEqual(self.route(29, 30, pending=28)[:3], (40, 30, 0))

    def test_hub_clear_history_row_is_erased(self):
        result, pending, destination, memory = self.route(
            40, 40, destination=8, pending=6, history=(5, 40))
        self.assertEqual((result, pending, destination), (8, 6, 8))
        self.assertEqual(memory[PARTY + hub_flow.HISTORY_OFFSET], 5)
        self.assertEqual(memory[PARTY + hub_flow.HISTORY_OFFSET + 8], 0)


class HubPatchTests(unittest.TestCase):
    def test_install_preserves_the_existing_story_flow(self):
        path = RETAIL_DIR / "GFEE01.dol"
        if not path.is_file():
            self.skipTest("no retail DOL")
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "sys").mkdir()
            shutil.copy(path, root / "sys" / "main.dol")
            (root / "sys" / "boot.bin").write_bytes(b"GFEE01\0\0" + bytes(0x438))
            editor = CodeEditor(root)
            flow = chapter_flow.ChapterFlow(editor)
            flow.set_next(40, 40)
            router = hub_flow.HubFlow(editor)
            router.install(40, 30, 32, 40)
            self.assertTrue(router.installed)
            self.assertEqual(router.config(), bytes((40, 3, 0x40, 4, 5)))
            self.assertEqual(flow.status.state, State.APPLIED)
            self.assertEqual(chapter_flow.ChapterFlow(CodeEditor(root)).next_of(40), 40)
            with self.assertRaises(ValueError):
                flow.set_next(5, 40)
            with self.assertRaises(ValueError):
                flow.remove(40)
            router.remove()
            self.assertEqual(flow.status.state, State.APPLIED)


class HubScriptTests(unittest.TestCase):
    def test_scripts_compile_and_reconfigure_without_duplicates(self):
        setup = hub.HubSetup(40, 5, "PID_HUB", (hub.Destination(6, 2, 3, 4, 5),
                                                hub.Destination(8, 6, 7, 8, 9)))
        original = '@export\ndef Startup():\n    pass\n'
        generated = hub.hub_script(original, setup)
        self.assertEqual(hub.hub_script(generated, setup), generated)
        self.assertEqual(generated.count("def HubGoTo6"), 1)
        compile_source(generated, global_flags=[hub.ACTIVE, hub.STARTED, *hub.DEST, *hub.PENDING])
        activation = hub.activation_script(original)
        self.assertEqual(hub.activation_script(activation), activation)
        compile_source(activation, global_flags=[hub.ACTIVE, hub.STARTED])

    def test_optional_description_uses_separate_visit_action(self):
        setup = hub.HubSetup(40, 5, "PID_HUB", (
            hub.Destination(6, 2, 3, 4, 5, "A short chapter description"),
            hub.Destination(8, 6, 7, 8, 9),
        ))
        source = hub.hub_script("# Fresh hub\n", setup)
        self.assertIn('@on_location(x=2, y=3, action="visit", name=None)', source)
        self.assertIn('TalkEvent("MS_HUB_06_INFO")', source)
        self.assertEqual(source.count('action="arrive"'), 2)
        self.assertEqual(source.count('action="visit"'), 1)
        compile_source(source, global_flags=[hub.ACTIVE, hub.STARTED, *hub.DEST, *hub.PENDING])

    def test_flag_bytes_are_aligned_without_reordering_existing_slots(self):
        names, dest_slot = hub.flag_names(30)
        self.assertEqual((dest_slot, len(names)), (32, 18))
        self.assertEqual(names[:2], [hub.ACTIVE, hub.STARTED])
        self.assertEqual(names[-8:], list(hub.PENDING))
        self.assertEqual(hub_flow.validate_slots(40, 30, dest_slot, dest_slot + 8),
                         bytes((40, 3, 0x40, 4, 5)))


class HubCreationTests(unittest.TestCase):
    def test_avatar_deployment_clears_copied_units(self):
        from fe_modding import chapters, hub_creation
        from fe_modding.formats import dispo, lz10, pak
        from tests.dispo_fixture import build_minimal_dispo_bytes

        source = build_minimal_dispo_bytes((b"bmap05_mikata_c", b"bmap05_first_c"))
        donor = lz10.compress(pak.pack_pak([("dispos_c.bin", source)]))
        renamed = chapters._renumber_dispos(donor, "05", "33")
        packed = lz10.decompress(hub_creation.avatar_deployment(renamed, "PID_HUB", 3, 4))
        entry = pak.read_pak_entries(packed)[0]
        doc = dispo.parse_dispo(pak.read_pak_file_content(packed, entry))
        player = doc.section("bmap33_mikata_c")
        self.assertEqual(len(player.units), 1)
        self.assertEqual(player.units[0][dispo.FIELD["pid"]], "PID_HUB")
        self.assertEqual((player.units[0][dispo.FIELD["pos_x"]], player.units[0][dispo.FIELD["pos_y"]]), (3, 4))
        self.assertFalse(doc.section("bmap33_first_c").units)

    def test_flat_map_has_selected_dimensions_and_only_ground(self):
        from fe_modding import hub_creation
        from fe_modding.formats import gs_file, lz10, map_file, pak
        from tests.test_map_heights import _map_bin

        donor = lz10.compress(pak.pack_pak([("map.bin", _map_bin()), ("flat.gs", b"donor")]))
        for width, height in ((4, 4), (23, 17), (63, 63)):
            packed = lz10.decompress(hub_creation.blank_map(donor, width, height))
            files = {entry.name: pak.read_pak_file_content(packed, entry) for entry in pak.read_pak_entries(packed)}
            parsed = map_file.read_map_bytes(files["map.bin"])
            self.assertEqual((parsed.capacity.x_size, parsed.capacity.y_size), (width, height))
            self.assertEqual(len(parsed.build_inst), 1)
            self.assertEqual(set(t for column in map_file.terrain_grid(files["map.bin"]) for t in column),
                             {hub_creation.GRASS})
            self.assertEqual(gs_file.read_gs(files["flat.gs"]).bbox_max[::2], (width * 5.0, height * 5.0))

@unittest.skipUnless(os.environ.get("FE9_EXTRACTED_FILES"), "set FE9_EXTRACTED_FILES for real assets")
class RealAssetIntegrationTests(unittest.TestCase):
    def test_prepared_hub_installs_and_reconfigures(self):
        from fe_modding import hub_creation
        from fe_modding.games import Game
        from fe_modding.project import ModProject

        source = Path(os.environ["FE9_EXTRACTED_FILES"])
        from fe_modding.formats import fe8data
        if fe8data.japanese_chapter_layout((source / "FE8Data.bin").read_bytes()):
            self.skipTest("Japanese chapter records are read-only")
        with tempfile.TemporaryDirectory() as tmp:
            project = ModProject.create(Path(tmp), "hub test", Game.PATH_OF_RADIANCE)
            files = project.extracted_dir / "files"
            for folder in ("Mess", "Scripts", "zmap/bmap05", "zmap/bmap09", "window/chapter",
                           "window/chapter2", "Fonts"):
                (files / folder).mkdir(parents=True, exist_ok=True)
            for name in ("c05.m", "c09.m", "common.m"):
                shutil.copy(source / "Mess" / name, files / "Mess" / name)
            for name in ("C05.cmb", "C09.cmb", "startup.cmb"):
                shutil.copy(source / "Scripts" / name, files / "Scripts" / name)
            for name in ("map.cmp", "dispos.cmp"):
                shutil.copy(source / "zmap" / "bmap05" / name, files / "zmap" / "bmap05" / name)
                shutil.copy(source / "zmap" / "bmap09" / name, files / "zmap" / "bmap09" / name)
            shutil.copy(source / "FE8Data.bin", files / "FE8Data.bin")
            shutil.copy(source / "Fonts" / "bigkana.gcf", files / "Fonts" / "bigkana.gcf")
            for folder in ("window/chapter", "window/chapter2"):
                shutil.copy(source / folder / "chap5.cms", files / folder / "chap5.cms")
            shutil.copytree(source / "shop", files / "shop")
            (project.extracted_dir / "sys").mkdir(exist_ok=True)
            shutil.copy(RETAIL_DIR / "GFEE01.dol", project.extracted_dir / "sys" / "main.dol")
            (project.extracted_dir / "sys" / "boot.bin").write_bytes(b"GFEE01\0\0" + bytes(0x438))

            plan = chapters.add_story_chapter(project, (files / "FE8Data.bin").read_bytes(), "05", 33, "Hub")
            project.write_logical("game_data", plan.fe8data)
            deployment, map_path = chapters.phase_paths(project, "bmap33")
            packed = lz10.decompress(deployment.read_bytes())
            entries, contents = pak.read_pak_entries(packed), []
            avatar = next(row for entry in entries if entry.name.startswith("dispos_")
                          for section in dispo.parse_dispo(pak.read_pak_file_content(packed, entry)).sections
                          for row in section.units if row[dispo.FIELD["pid"]] == "PID_MAIZIN")
            for entry in entries:
                content = pak.read_pak_file_content(packed, entry)
                if entry.name.startswith("dispos_"):
                    document = dispo.parse_dispo(content)
                    for section in document.sections:
                        if not section.is_link:
                            section.units.clear()
                    if entry.name == "dispos_c.bin":
                        player = next(section for section in document.sections if "mikata" in section.name)
                        avatar[dispo.FIELD["pid"]] = "PID_SOTHE"
                        avatar[dispo.FIELD["faction"]] = 0
                        player.units.append(avatar)
                    content = dispo.build_dispo(document)
                contents.append((entry.name, content))
            deployment.write_bytes(lz10.compress(pak.pack_pak(contents, [entry.reserved for entry in entries])))

            setup = hub.HubSetup(33, 9, "PID_SOTHE", (hub.Destination(5, 2, 3, 4, 5),))
            with self.assertRaisesRegex(ValueError, "old victory event"):
                hub.prepare(project, setup)
            hub_path = script_sources.chapter_script(project, "33")
            base = read_cmb(hub_path.read_bytes())
            hub_path.write_bytes(write_cmb(compile_source("# Prepared hub script\n", base=base).script))

            prepared = hub.prepare(project, setup)
            self.assertEqual(prepared["slots"]["active"], 30)
            first = hub.install(project, setup)
            self.assertEqual(first["chapter"], 33)
            self.assertEqual(hub.install(project, setup)["slots"], first["slots"])
            self.assertEqual(hub.saved_setup(project)["normal_successor"], 34)
            generated = hub_creation.create_chapter(project, project.read_logical("game_data"), "05", 34,
                                                    "Generated Hub", 16, 12, "PID_SOTHE", (1, 1))
            self.assertIsNotNone(generated.fe8data)
            generated_map = chapters.chapter_paths(project, "34").map
            packed_map = lz10.decompress(generated_map.read_bytes())
            map_entry = next(e for e in pak.read_pak_entries(packed_map) if e.name == "map.bin")
            from fe_modding.formats import map_file
            capacity = map_file.read_map_bytes(pak.read_pak_file_content(packed_map, map_entry)).capacity
            self.assertEqual((capacity.x_size, capacity.y_size), (16, 12))


if __name__ == "__main__":
    unittest.main()
