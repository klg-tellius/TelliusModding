"""Radiant Dawn hub setup on a scratch project made from an extracted RFEE01 disc."""

import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

FE10 = os.environ.get("FE10_EXTRACTED_FILES")
AVATAR = "PID_DJ_GREIL"   # in no retail deployment


@unittest.skipUnless(FE10, "set FE10_EXTRACTED_FILES to an extracted Radiant Dawn files/ directory")
class RdHubSetupTests(unittest.TestCase):
    def setUp(self):
        from fe_modding import chapters_fe10, script_sources
        from fe_modding.formats import dispo
        from fe_modding.formats.cmb import compile_source, read_cmb, write_cmb
        from fe_modding.formats.cmb.parser import parse
        from fe_modding.games import Game
        from fe_modding.project import ModProject

        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        files = Path(FE10)
        project = self.project = ModProject.create(Path(tmp.name), "RD", Game.RADIANT_DAWN)
        ex = project.extracted_dir
        shutil.copytree(files.parent / "sys", ex / "sys")
        (ex / "files" / "Scripts").mkdir(parents=True)
        (ex / "files" / "Mess").mkdir()
        shutil.copy(files / "FE10Data.cms", ex / "files")
        for name in ("startup", "C0101", "C0102", "C0103"):
            shutil.copy(files / "Scripts" / f"{name}.cmb", ex / "files" / "Scripts")
        for name in ("c0101.m", "e_c0101.m", "e_common.m", "common.m"):
            if (files / "Mess" / name).is_file():       # no e_ files on the Japanese disc
                shutil.copy(files / "Mess" / name, ex / "files" / "Mess")
        for folder in ("bmap0101", "bmap0103"):      # bmap0103 also gives the Arrive marker (tttu01)
            shutil.copytree(files / "zmap" / folder, ex / "files" / "zmap" / folder)
        plan = chapters_fe10.add_story_chapter(project, project.read_logical("game_data"), "0101", "0501", "Hub")
        project.write_logical("game_data", plan.fe10data)
        for path in (ex / "files" / "zmap" / "bmap0501").glob("dispos_*.bin"):
            doc = dispo.parse_dispo(path.read_bytes())
            for section in doc.sections:
                if "_mikata" in section.name and section.units:
                    section.units[0][dispo.FIELD["pid"]] = AVATAR
                    del section.units[1:]
            path.write_bytes(dispo.build_dispo(doc))
        script = script_sources.chapter_script(project, "0501")
        source = script_sources.peek(project, script)
        lines = source.split("\n")
        for fd in sorted((f for f in parse(source).functions if any(d.name == "on_complete" for d in f.decorators)),
                         key=lambda f: -f.line):
            begin = fd.line - 1 - len(fd.decorators)
            end = begin + 1
            while end < len(lines) and (lines[end].startswith((" ", "\t")) or not lines[end].strip()):
                end += 1
            del lines[begin:end]
        script.write_bytes(write_cmb(compile_source("\n".join(lines), base=read_cmb(script.read_bytes())).script))

    def setup(self, **changes):
        from fe_modding import hub
        values = dict(chapter=56, activation_chapter=1, avatar_pid=AVATAR,
                      destinations=(hub.Destination(3, 7, 20, 6, 20, "The old road, where Nolan waits."),),
                      start_x=6, start_y=20)
        values.update(changes)
        return hub.HubSetup(**values)

    def test_install_writes_flags_events_and_routing_then_uninstall_removes_them(self):
        from fe_modding import hub, hub_fe10, script_sources
        from fe_modding.formats import event_flags as ef
        from fe_modding.formats.cmb.parser import parse
        from fe_modding.game_code import rd_hub, rd_story
        from fe_modding.game_code.dol import Dol
        from fe_modding.formats import fe10_message

        project = self.project
        before = {page: script_sources.peek(project, script_sources.chapter_script(project, page))
                  for page in ("0101", "0501")}
        saved = hub_fe10.install(project, self.setup())
        self.assertEqual(saved["slots"], {"active": 27, "destination": 32, "pending": 40})
        globals_ = ef.global_flags(parse(script_sources.peek(project, script_sources.startup_path(project))),
                                   ef.FE10_FLAGS)
        self.assertEqual(globals_[27:29], [hub.ACTIVE, hub.STARTED])
        self.assertEqual(globals_[32:48], [*hub.DEST, *hub.PENDING])
        dol = Dol.open(project.extracted_dir / "sys" / "main.dol")
        self.assertEqual(dol.read(rd_hub.HUB_CONFIG, 5), bytes((56, 3, 0x08, 4, 5)))
        self.assertEqual(dol.read(rd_story.MAGIC, 4), rd_story.MAGIC_BYTES)
        self.assertEqual(dol.read(rd_hub.DONE, 4), rd_hub.PATCH.versions["RFEE01"][0].patched)
        hub_source = script_sources.peek(project, script_sources.chapter_script(project, "0501"))
        self.assertIn('@on_location(x=7, y=20, action="arrive", name=None)\ndef HubGoTo3():\n'
                      '    if Check():\n        return 1\n    else:\n', hub_source)
        self.assertIn(f"UnitTransferToForce(unit, {hub_fe10.RELEASE_FORCE})", hub_source)
        self.assertIn('set("HUB_ACTIVE")', script_sources.peek(project, script_sources.chapter_script(project, "0101")))
        self.assertIn('@on_location(x=7, y=20, action="visit", name=None)', hub_source)
        self.assertIn('TalkEvent("MS_HUB_03_INFO")', hub_source)
        self.assertTrue(hub.config_path(project).is_file())
        self.assertEqual(self.markers(), [(7, 20)])
        info = self.messages().get("MS_HUB_03_INFO")
        self.assertEqual(fe10_message.to_display(info),
                         "<R:ダイアログ会話><sd>The old road, where Nolan\nwaits.<wait>")

        hub_fe10.uninstall(project)
        self.assertEqual(self.markers(), [])
        self.assertNotIn("MS_HUB_03_INFO", self.messages())
        self.assertFalse(hub.config_path(project).is_file())
        for page, source in before.items():
            after = script_sources.peek(project, script_sources.chapter_script(project, page))
            self.assertNotIn(hub.START_MARK, after)
        dol = Dol.open(project.extracted_dir / "sys" / "main.dol")
        self.assertEqual(dol.read(rd_hub.DONE, 4), (0x80010024).to_bytes(4, "big"))   # lwz r0, 0x24(r1)

    def markers(self):
        from fe_modding import chapters, map_props
        from fe_modding.formats import map_file
        _entries, files = map_props.read_map_container(chapters.chapter_paths(self.project, "0501").map)
        data = map_file.read_map_bytes(files["map.bin"])
        return [(i.x, i.y) for i in data.build_inst if data.build_desc[i.desc_index].filename == "tttu01"]

    def messages(self):
        from fe_modding import chapters
        from fe_modding.formats import message
        path = chapters.chapter_paths(self.project, "0501").dialogue
        from tests.corpus import per_disc
        self.assertEqual(path.name, per_disc(FE10, "e_c0501.m", jp="c0501.m"))
        return {m.speaker: m.text for m in message.read_messages_path(path)}

    def test_create_chapter_leaves_the_avatar_alone_and_a_plain_opening(self):
        from fe_modding import hub, hub_creation_fe10, hub_fe10, script_sources
        from fe_modding.formats import dispo

        project = self.project
        plan = hub_creation_fe10.create_chapter(project, project.read_logical("game_data"), "0101", "0502", "Hub",
                                                "PID_DJ_GREIL")
        self.assertEqual(plan.number, 57)
        project.write_logical("game_data", plan.fe10data)
        armies = 0
        for path in hub_fe10._deployments(project, "0502"):
            for section in dispo.parse_dispo(path.read_bytes()).sections:
                pids = [u[dispo.FIELD["pid"]] for u in section.units]
                if "_mikata" in section.name:
                    self.assertEqual(pids, ["PID_DJ_GREIL"])
                    # on the tile Micaiah stands on in 1-1 (her spawn (6, 20) is where she walks in from;
                    # links placed around it were out of reach in the game)
                    avatar = section.units[0]
                    self.assertEqual([avatar[dispo.FIELD[k]] for k in ("pos_x", "pos_y", "pos2_x", "pos2_y")],
                                     [10, 11, 10, 11])
                    armies += 1
                else:
                    self.assertEqual(pids, [], section.name)
        self.assertEqual(armies, 2)        # Normal and Hard; dispos_c.bin has none
        source = script_sources.peek(project, script_sources.chapter_script(project, "0502"))
        self.assertIn('MapLoad("bmap0502")', source)
        self.assertIn('SallySetByGroupRank("bmap0502_mikata")', source)
        self.assertNotIn("on_complete", source)
        self.assertEqual(hub.chapter_page(project, 57), "0502")
        self.assertEqual(hub.chapter_number(project, "0502"), 57)
        self.assertNotIn(0, hub_fe10.link_candidates(project, 57))   # the test map
        # the setUp hub 0501 deploys the same avatar: not offered, and refused on install
        self.assertNotIn("PID_DJ_GREIL", dict(hub_fe10.avatar_candidates(project, plan.fe10data, "0502")))
        self.assertIn("PID_DJ_GREIL", dict(hub_fe10.avatar_candidates(project, plan.fe10data, "0502",
                                                                      keep="PID_DJ_GREIL")))
        with self.assertRaisesRegex(ValueError, "also appears in chapter 0501"):
            hub_fe10.prepare(project, self.setup(chapter=57))

    def test_create_chapter_on_a_blank_map(self):
        from fe_modding import chapters, hub_creation, hub_creation_fe10, hub_fe10, map_props
        from fe_modding.formats import dispo, map_file

        project = self.project
        plan = hub_creation_fe10.create_chapter(project, project.read_logical("game_data"), "0101", "0502", "Hub",
                                                "PID_DJ_GREIL", blank_size=(14, 9), ground_color=(90, 140, 70))
        project.write_logical("game_data", plan.fe10data)
        _entries, files = map_props.read_map_container(chapters.chapter_paths(project, "0502").map)
        data = map_file.read_map_bytes(files["map.bin"])
        # named after the new map, or the game finds neither its sections nor its ground (Dolphin)
        self.assertIn("bmap0502.gs", files)
        self.assertNotIn("bmap0101.gs", files)
        self.assertIn(b"bmap0502:mapdata", files["map.bin"])
        self.assertNotIn(b"bmap0101:", files["map.bin"])
        self.assertEqual((data.capacity.x_size, data.capacity.y_size, len(data.build_inst)), (14, 9, 1))
        self.assertEqual(data.rd.version, map_file.read_map_bytes(
            map_props.read_map_container(chapters.chapter_paths(project, "0101").map)[1]["map.bin"]).rd.version)
        ground = [o for o in data.build_desc if map_file.is_base_terrain_object(o, files)
                  and "water" not in o.filename]
        self.assertEqual(len(ground), 1)       # found by its map_base material, as the game finds it
        appearance = hub_creation.flat_ground_appearance(files)
        self.assertEqual(appearance.color, (90, 140, 70))
        self.assertIsNone(appearance.image)      # the colour texture reads back as the plain colour
        from fe_modding.formats import gs_file, tpl
        import io
        material = gs_file.read_gs(files[f"{ground[0].filename}.gs"]).materials[0]
        base = tpl.read_tpl_images(io.BytesIO(files["texpack.tpl"]))[material.textures[0].tex_id].convert("RGBA")
        self.assertEqual(base.getpixel((0, 0)), (90, 140, 70, 255))    # map_base draws the texture's colour
        for path in hub_fe10._deployments(project, "0502"):
            for section in dispo.parse_dispo(path.read_bytes()).sections:
                if "_mikata" in section.name and section.units:
                    unit = section.units[0]
                    # 1-1's tile (10, 11) is outside a 14 x 9 map: the avatar starts in the middle
                    self.assertEqual((unit[dispo.FIELD["pos_x"]], unit[dispo.FIELD["pos_y"]]), (7, 4))

    def test_bad_setups_are_refused(self):
        from fe_modding import hub, hub_fe10
        cases = [
            (dict(chapter=3), "added chapter"),
            (dict(activation_chapter=56), "activation chapter"),
            (dict(avatar_pid="PID_MICAIAH"), "avatar PID_MICAIAH alone"),
            (dict(avatar_pid="PID_NOBODY"), "no character record"),
            (dict(destinations=()), "at least one destination"),
            (dict(destinations=(hub.Destination(2, 7, 20, 6, 20),)), "missing its script, map or deployment"),
            (dict(destinations=(hub.Destination(3, 7, 20, 6, 20, "word " * 30),)), "at most 4 lines"),
            (dict(destinations=(hub.Destination(3, 7, 20, 6, 20, "a <tag>"),)), "cannot hold"),
        ]
        for changes, message in cases:
            with self.subTest(changes=changes), self.assertRaisesRegex(ValueError, message):
                hub_fe10.prepare(self.project, self.setup(**changes))


if __name__ == "__main__":
    unittest.main()
