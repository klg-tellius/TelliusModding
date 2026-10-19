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
        packed = lz10.decompress(hub_creation.avatar_deployment(renamed, "PID_HUB", 3, 4, "JID_RANGER"))
        entry = pak.read_pak_entries(packed)[0]
        doc = dispo.parse_dispo(pak.read_pak_file_content(packed, entry))
        player = doc.section("bmap33_avatar_c")
        self.assertNotIn("_mikata_", player.name)
        self.assertEqual(len(player.units), 1)
        self.assertEqual(player.units[0][dispo.FIELD["pid"]], "PID_HUB")
        self.assertEqual(player.units[0][dispo.FIELD["jid"]], "JID_RANGER")
        for field, name in hub_creation.AVATAR_AI.items():
            self.assertEqual(player.units[0][dispo.FIELD[field]], name)
        self.assertEqual((player.units[0][dispo.FIELD["pos_x"]], player.units[0][dispo.FIELD["pos_y"]]), (3, 4))
        self.assertFalse(doc.section("bmap33_first_c").units)
        with tempfile.TemporaryDirectory() as tmp:
            deployment = Path(tmp) / "dispos.cmp"
            deployment.write_bytes(lz10.compress(packed))
            self.assertEqual(hub._deployment_pids(deployment), ({"PID_HUB"}, {"PID_HUB"}))

    def test_avatar_ai_repair_preserves_other_units_and_custom_ai(self):
        from fe_modding import hub_creation
        from tests.dispo_fixture import build_minimal_dispo_bytes
        document = dispo.parse_dispo(build_minimal_dispo_bytes((b"bmap33_avatar_c",)))
        unit = dispo.new_unit_values()
        unit[dispo.FIELD["pid"]] = "PID_HUB"
        unit[dispo.FIELD["seq_move"]] = "SEQ_CUSTOM_MOVE"
        other = list(unit)
        other[dispo.FIELD["pid"]] = "PID_OTHER"
        document.section("bmap33_avatar_c").units = [unit, other]
        archive = lz10.compress(pak.pack_pak([("dispos_c.bin", dispo.build_dispo(document))]))
        repaired = hub_creation.repair_avatar_deployment(archive, "PID_HUB", "JID_RANGER")
        self.assertEqual(hub_creation.repair_avatar_deployment(repaired, "PID_HUB", "JID_OTHER"), repaired)
        raw = lz10.decompress(repaired)
        result = dispo.parse_dispo(pak.read_pak_file_content(raw, pak.read_pak_entries(raw)[0]))
        self.assertEqual(result.section("bmap33_avatar_c").units[1], other)
        avatar = result.section("bmap33_avatar_c").units[0]
        self.assertEqual(avatar[dispo.FIELD["jid"]], "JID_RANGER")
        self.assertEqual(avatar[dispo.FIELD["seq_move"]], "SEQ_CUSTOM_MOVE")
        for field in ("seq_attack", "seq_heal", "mtype"):
            self.assertEqual(avatar[dispo.FIELD[field]], hub_creation.AVATAR_AI[field])

    def test_opening_deploys_avatar_then_focuses_and_reveals_map(self):
        from fe_modding import hub_creation
        source = hub_creation.opening_source(33, "bmap33_avatar_c", "PID_HUB")
        compile_source(source)
        self.assertLess(source.index('InstantDisposFirst'), source.index('InstantUnitFocusByPID'))
        self.assertLess(source.index('InstantSetMapCamera'), source.index('Fade(2, 500)'))
        self.assertTrue(source.endswith('    FadeWait()\n'))
        self.assertNotIn('Opening2', source)  # no preparations menu

    def test_flat_map_has_selected_dimensions_and_only_ground(self):
        from fe_modding import hub_creation
        from fe_modding.formats import gs_file, lz10, map_file, pak, tpl
        from PIL import Image
        import io
        from tests.test_map_heights import _map_bin

        original_tpl = tpl.build_tpl([(Image.new("RGBA", (8, 8), "red"), tpl.FORMAT_RGB565)])
        donor = lz10.compress(pak.pack_pak([("map.bin", _map_bin()), ("flat.gs", b"donor"),
                                          ("texpack.tpl", original_tpl)]))
        for width, height in ((4, 4), (23, 17), (63, 63)):
            packed = lz10.decompress(hub_creation.blank_map(donor, width, height))
            files = {entry.name: pak.read_pak_file_content(packed, entry) for entry in pak.read_pak_entries(packed)}
            parsed = map_file.read_map_bytes(files["map.bin"])
            self.assertEqual((parsed.capacity.x_size, parsed.capacity.y_size), (width, height))
            self.assertEqual(len(parsed.build_inst), 1)
            self.assertEqual(set(t for column in map_file.terrain_grid(files["map.bin"]) for t in column),
                             {hub_creation.GRASS})
            self.assertEqual(gs_file.read_gs(files["flat.gs"]).bbox_max[::2], (width * 5.0, height * 5.0))
            ground = gs_file.read_gs(files["flat.gs"])
            images = tpl.read_tpl_images(io.BytesIO(files["texpack.tpl"]))
            self.assertEqual(images[0].tobytes(), tpl.read_tpl_images(io.BytesIO(original_tpl))[0].tobytes())
            for material in ground.materials:
                self.assertNotIn(material.name, {"map_base", "map_wall", "map_water"})
                self.assertEqual(len(material.textures), 2)
                for texture in material.textures:
                    self.assertEqual(texture.tex_id, 1)
                    self.assertEqual(images[texture.tex_id].tobytes(), b"\xff" * (8 * 8 * 4))

    def test_flat_map_accepts_color_and_stretched_or_tiled_image(self):
        from fe_modding import hub_creation
        from fe_modding.formats import gs_file, lz10, map_file, pak, tpl
        from PIL import Image
        import io
        from tests.test_map_heights import _map_bin

        donor_tpl = tpl.build_tpl([(Image.new("RGBA", (8, 8), "red"), tpl.FORMAT_RGB565)])
        donor = lz10.compress(pak.pack_pak([("map.bin", _map_bin()), ("flat.gs", b"donor"),
                                           ("texpack.tpl", donor_tpl)]))

        colored = lz10.decompress(hub_creation.blank_map(donor, 8, 6, ground_color=(20, 40, 60)))
        files = {entry.name: pak.read_pak_file_content(colored, entry) for entry in pak.read_pak_entries(colored)}
        material = gs_file.read_gs(files["flat.gs"]).materials[0]
        loaded_rgb = tuple(round(channel * 1.25) for channel in material.color0[:3])
        self.assertEqual(loaded_rgb, (20, 40, 60))

        picture = Image.new("RGBA", (16, 8), (12, 34, 56, 255))
        for tiled in (False, True):
            packed = lz10.decompress(hub_creation.blank_map(
                donor, 8, 6, ground_color=(1, 2, 3), ground_image=picture, tile_ground_image=tiled))
            files = {entry.name: pak.read_pak_file_content(packed, entry)
                     for entry in pak.read_pak_entries(packed)}
            ground = gs_file.read_gs(files["flat.gs"])
            material = ground.materials[0]
            images = tpl.read_tpl_images(io.BytesIO(files["texpack.tpl"]))
            self.assertEqual(tuple(round(channel * 1.25) for channel in material.color0[:3]),
                             (255, 255, 255))
            decoded = images[material.textures[0].tex_id].getpixel((0, 0))[:3]
            self.assertTrue(all(abs(actual - expected) <= 4
                                for actual, expected in zip(decoded, (12, 34, 56))))
            uvs = [(u / (1 << ground.uv_frac), v / (1 << ground.uv_frac)) for u, v in ground.uvs]
            self.assertAlmostEqual(max(uv[0] for uv in uvs), 8.0 if tiled else 1.0)
            self.assertAlmostEqual(max(uv[1] for uv in uvs), 6.0 if tiled else 1.0)

    def test_existing_flat_hub_ground_can_change_without_touching_map_data(self):
        from fe_modding import hub_creation
        from fe_modding.formats import lz10, pak, tpl
        from PIL import Image
        import io
        from tests.test_map_heights import _map_bin

        donor_tpl = tpl.build_tpl([(Image.new("RGBA", (8, 8), "red"), tpl.FORMAT_RGB565)])
        donor = lz10.compress(pak.pack_pak([("map.bin", _map_bin()), ("flat.gs", b"donor"),
                                           ("texpack.tpl", donor_tpl)]))
        packed = lz10.decompress(hub_creation.blank_map(donor, 9, 7))
        entries = pak.read_pak_entries(packed)
        files = {entry.name: pak.read_pak_file_content(packed, entry) for entry in entries}
        original_map = files["map.bin"]

        picture = Image.new("RGBA", (32, 16), (80, 120, 160, 255))
        hub_creation.replace_flat_ground(entries, files, ground_image=picture, tile_ground_image=True)
        self.assertEqual(files["map.bin"], original_map)
        appearance = hub_creation.flat_ground_appearance(files)
        self.assertIsNotNone(appearance.image)
        self.assertTrue(appearance.tiled)
        self.assertTrue(all(abs(actual - expected) <= 8 for actual, expected in zip(
            appearance.image.getpixel((0, 0))[:3], (80, 120, 160))))

        hub_creation.replace_flat_ground(entries, files, ground_color=(30, 60, 90))
        appearance = hub_creation.flat_ground_appearance(files)
        self.assertIsNone(appearance.image)
        self.assertFalse(appearance.tiled)
        self.assertEqual(appearance.color, (30, 60, 90))
        self.assertLessEqual(len(tpl.read_tpl_images(io.BytesIO(files["texpack.tpl"]))), 2)

    def test_custom_terrain_requires_opt_in_then_becomes_flat_image_ground(self):
        from fe_modding import hub_creation
        from fe_modding.formats import gs_file, lz10, pak, tpl
        from PIL import Image
        from tests.test_map_heights import _map_bin

        donor_tpl = tpl.build_tpl([(Image.new("RGBA", (8, 8), "red"), tpl.FORMAT_RGB565)])
        donor = lz10.compress(pak.pack_pak([("map.bin", _map_bin()), ("flat.gs", b"donor"),
                                           ("texpack.tpl", donor_tpl)]))
        packed = lz10.decompress(hub_creation.blank_map(donor, 10, 8))
        entries = pak.read_pak_entries(packed)
        files = {entry.name: pak.read_pak_file_content(packed, entry) for entry in entries}
        model = gs_file.read_gs(files["flat.gs"])
        model.materials[0].name = "custom_terrain"
        files["flat.gs"] = gs_file.write_gs(model)

        with self.assertRaisesRegex(ValueError, "Blank map"):
            hub_creation.replace_flat_ground(entries, files, ground_image=Image.new("RGBA", (8, 8), "blue"))
        hub_creation.replace_flat_ground(entries, files, ground_image=Image.new("RGBA", (8, 8), "blue"),
                                         replace_custom_terrain=True)
        self.assertEqual(gs_file.read_gs(files["flat.gs"]).materials[0].name, "hub_ground")
        self.assertIsNotNone(hub_creation.flat_ground_appearance(files).image)

@unittest.skipUnless(os.environ.get("FE9_EXTRACTED_FILES"), "set FE9_EXTRACTED_FILES for real assets")
class RealAssetIntegrationTests(unittest.TestCase):
    def test_entrance_markers_follow_destinations_without_duplicates(self):
        from types import SimpleNamespace
        from fe_modding import map_props
        from fe_modding.formats import map_file
        from dataclasses import replace
        files = Path(os.environ["FE9_EXTRACTED_FILES"])
        project = SimpleNamespace(files_dir=files)
        setup = hub.HubSetup(33, 1, "PID_HUB", (
            hub.Destination(2, 4, 4, 5, 6), hub.Destination(3, 6, 4, 5, 6)))
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "map.cmp"
            shutil.copy(files / "zmap/bmap05/map.cmp", path)
            _, original = map_props.read_map_container(path)
            original_records = map_file.instance_records(original["map.bin"])
            first = hub.entrance_markers(project, path, setup)
            path.write_bytes(first)
            self.assertEqual(hub.entrance_markers(project, path, setup), first)
            changed = replace(setup, destinations=(hub.Destination(3, 8, 4, 5, 6),))
            path.write_bytes(hub.entrance_markers(project, path, changed))
            _, result = map_props.read_map_container(path)
            data = map_file.read_map_bytes(result["map.bin"])
            index = next(i for i, o in enumerate(data.build_desc) if o.filename == hub.ENTRANCE_OBJECT)
            self.assertEqual([(i.x, i.y) for i in data.build_inst if i.desc_index == index], [(8, 4)])
            self.assertEqual([r for r, i in zip(map_file.instance_records(result["map.bin"]), data.build_inst)
                              if i.desc_index != index], original_records)
            self.assertEqual(map_file.terrain_grid(result["map.bin"]), map_file.terrain_grid(original["map.bin"]))
            for ext in ("gs", "g", "ga"):
                self.assertIn(f"{hub.ENTRANCE_OBJECT}.{ext}", result)

    def test_prepared_hub_installs_and_reconfigures(self):
        from fe_modding import hub_creation
        from fe_modding.games import Game
        from fe_modding.project import ModProject

        source = Path(os.environ["FE9_EXTRACTED_FILES"])
        from fe_modding.formats import fe8data
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
            (files / "zmap/bmap18").mkdir(parents=True)
            shutil.copy(source / "zmap/bmap18/map.cmp", files / "zmap/bmap18/map.cmp")
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

            # Prepare directly in extended storage, without installing a legacy
            # hub or modifying any of the project's files.
            from fe_modding.extended_hub import prepare_fresh_project_update
            from fe_modding.formats.extended_flags import FlagLayout, HUB_ALIASES
            from fe_modding.formats import event_flags as ef
            from fe_modding.formats.cmb.parser import parse
            c18_script = files / "Scripts" / "C18.cmb"
            c18_message = files / "Mess" / "c18.m"
            shutil.copy(source / "Scripts" / "C18.cmb", c18_script)
            shutil.copy(source / "Mess" / "c18.m", c18_message)
            c18_source = script_sources.peek(project, c18_script)
            old_locals = ef.local_flags(parse(c18_source))
            self.assertEqual(len(old_locals), 58)
            for name in ("extended_chapter_a", "extended_chapter_b"):
                c18_source = ef.append_registration(c18_source, "Startup", "regist", name)
            c18_script.write_bytes(write_cmb(compile_source(c18_source, base=read_cmb(c18_script.read_bytes())).script))
            c18_sidecar = script_sources.sidecar_path(project, c18_script)
            c18_sidecar.parent.mkdir(parents=True, exist_ok=True)
            c18_sidecar.write_text(c18_source, encoding="utf-8")
            before = {p: p.read_bytes() for p in project.directory.rglob("*") if p.is_file()}
            layout = (FlagLayout().add("extended_chapter_a", "chapter", 18)
                      .add("extended_chapter_b", "chapter", 18))
            from dataclasses import replace
            fresh_setup = replace(setup, start_x=1, start_y=1,
                                  destinations=(replace(setup.destinations[0], description="Visit chapter five."),))
            update = prepare_fresh_project_update(project, fresh_setup, layout)
            self.assertEqual({p: p.read_bytes() for p in project.directory.rglob("*") if p.is_file()}, before)
            self.assertEqual(update.migration.configuration["storage"], "extended")
            self.assertEqual(update.migration.configuration["layout_identity"], layout.identity)
            self.assertNotIn("slots", update.migration.configuration)
            names = ef.global_flags(parse(update.migration.startup_source))
            self.assertEqual(names[-18:], list(HUB_ALIASES))
            self.assertFalse(any(name.startswith("HUB_PAD_") for name in names))
            self.assertEqual(len(update.migration.vanilla_globals), 30)
            outputs = {item.path: item.after for item in update.changes}
            self.assertIn(hub_path, outputs)
            self.assertIn(script_sources.chapter_script(project, "09"), outputs)
            self.assertIn(chapters.chapter_paths(project, "33").dialogue, outputs)
            self.assertIn(deployment, outputs)
            update.verify_unchanged()
            original_map = map_path.read_bytes()
            map_path.write_bytes(original_map + b"changed")
            with self.assertRaisesRegex(ValueError, "changed after"):
                update.verify_unchanged()
            map_path.write_bytes(original_map)
            with self.assertRaisesRegex(ValueError, "Chapter 18"):
                hub.prepare(project, setup)
            # Exercise installed extended reconfiguration in this isolated
            # fixture, including removal of the old activation event.
            from fe_modding.extended_hub import prepare_reconfigure_project_update
            from fe_modding.game_code.extended_flag_installation import inspect_project, RuntimeState
            for item in update.changes:
                item.path.parent.mkdir(parents=True, exist_ok=True)
                item.path.write_bytes(item.after)
            try:
                self.assertEqual(inspect_project(project).state, RuntimeState.MATCHING)
                installed = {p: p.read_bytes() for p in project.directory.rglob("*") if p.is_file()}
                revised = replace(fresh_setup, activation_chapter=5)
                reconfigured = prepare_reconfigure_project_update(project, revised, layout)
                self.assertEqual({p: p.read_bytes() for p in project.directory.rglob("*") if p.is_file()}, installed)
                names = ef.global_flags(parse(reconfigured.migration.startup_source))
                self.assertEqual(names[-18:], list(HUB_ALIASES))
                self.assertEqual(reconfigured.migration.configuration["normal_successor"], 34)
                revised_outputs = {item.path: item.after for item in reconfigured.changes}
                old_activation = script_sources.chapter_script(project, "09")
                old_text = revised_outputs[script_sources.sidecar_path(project, old_activation)].decode("utf-8")
                self.assertEqual(hub._remove_generated(old_text), old_text)
                for item in reconfigured.changes:
                    item.path.write_bytes(item.after)
                self.assertEqual(inspect_project(project).state, RuntimeState.MATCHING)
            finally:
                for path in tuple(project.directory.rglob("*")):
                    if path.is_file() and path not in before:
                        path.unlink()
                for path, data in before.items():
                    path.write_bytes(data)
            # Keep the pre-existing legacy installation/reconfiguration test
            # independent of the extended-only C18 fixture.
            c18_script.unlink()
            c18_message.unlink()
            c18_sidecar.unlink()

            prepared = hub.prepare(project, setup)
            self.assertEqual(prepared["slots"]["active"], 30)
            first = hub.install(project, setup)
            self.assertEqual(first["chapter"], 33)
            self.assertEqual(hub.install(project, setup)["slots"], first["slots"])
            self.assertEqual(hub.saved_setup(project)["normal_successor"], 34)
            from fe_modding.extended_hub import prepare_install_project_update
            migration = prepare_install_project_update(project, replace(setup, activation_chapter=5), FlagLayout())
            self.assertEqual(hub.saved_setup(project)["version"], first["version"])
            self.assertEqual(migration.migration.configuration["activation_chapter"], 5)
            migrated_names = ef.global_flags(parse(migration.migration.startup_source))
            self.assertEqual(migrated_names[-18:], list(HUB_ALIASES))
            self.assertFalse(any(name.startswith("HUB_PAD_") for name in migrated_names))
            old_activation = script_sources.chapter_script(project, "09")
            migration_outputs = {item.path: item.after for item in migration.changes}
            old_text = migration_outputs[script_sources.sidecar_path(project, old_activation)].decode("utf-8")
            self.assertEqual(hub._remove_generated(old_text), old_text)
            generated = hub_creation.create_chapter(project, project.read_logical("game_data"), "05", 34,
                                                    "Generated Hub", 16, 12, "PID_SOTHE", (1, 1))
            self.assertIsNotNone(generated.fe8data)
            generated_map = chapters.chapter_paths(project, "34").map
            packed_map = lz10.decompress(generated_map.read_bytes())
            map_entry = next(e for e in pak.read_pak_entries(packed_map) if e.name == "map.bin")
            from fe_modding.formats import map_file
            capacity = map_file.read_map_bytes(pak.read_pak_file_content(packed_map, map_entry)).capacity
            self.assertEqual((capacity.x_size, capacity.y_size), (16, 12))


class HubDraftTests(unittest.TestCase):
    def test_draft_round_trip_and_precedence(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = type("P", (), {"directory": Path(tmp)})()
            self.assertIsNone(hub.working_setup(project))
            draft = {"chapter": 40, "activation_chapter": 5, "avatar_pid": "PID_X",
                     "destinations": [{"chapter": 8, "x": 1, "y": 2, "return_x": 1, "return_y": 3}]}
            hub.save_draft(project, draft)
            self.assertNotIn(b"\r\n", hub.draft_path(project).read_bytes())
            self.assertEqual(hub.hub_chapter(project), 40)
            setup = hub.setup_from(hub.working_setup(project))
            self.assertEqual(setup.destinations, (hub.Destination(8, 1, 2, 1, 3, ""),))
            self.assertIsNone(setup.start_x)
            hub.save_draft(project, {**draft, "storage": "extended"})
            self.assertEqual(hub.working_setup(project)["storage"], "extended")
            hub.config_path(project).write_text('{"chapter": 41}', encoding="utf-8")
            self.assertEqual(hub.hub_chapter(project), 40)  # the draft is what is being edited
            hub.draft_path(project).unlink()
            self.assertEqual(hub.hub_chapter(project), 41)


if __name__ == "__main__":
    unittest.main()
