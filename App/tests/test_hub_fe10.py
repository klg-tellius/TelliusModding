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
            shutil.copy(files / "Mess" / name, ex / "files" / "Mess")
        for folder in ("bmap0101", "bmap0103"):
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
                      destinations=(hub.Destination(3, 7, 20, 6, 20),), start_x=6, start_y=20)
        values.update(changes)
        return hub.HubSetup(**values)

    def test_install_writes_flags_events_and_routing_then_uninstall_removes_them(self):
        from fe_modding import hub, hub_fe10, script_sources
        from fe_modding.formats import event_flags as ef
        from fe_modding.formats.cmb.parser import parse
        from fe_modding.game_code import rd_hub, rd_story
        from fe_modding.game_code.dol import Dol

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
        self.assertIn('@on_location(x=7, y=20, action="arrive", name=None)', hub_source)
        self.assertIn(f"UnitTransferToForce(unit, {hub_fe10.RELEASE_FORCE})", hub_source)
        self.assertIn('set("HUB_ACTIVE")', script_sources.peek(project, script_sources.chapter_script(project, "0101")))
        self.assertTrue(hub.config_path(project).is_file())

        hub_fe10.uninstall(project)
        self.assertFalse(hub.config_path(project).is_file())
        for page, source in before.items():
            after = script_sources.peek(project, script_sources.chapter_script(project, page))
            self.assertNotIn(hub.START_MARK, after)
        dol = Dol.open(project.extracted_dir / "sys" / "main.dol")
        self.assertEqual(dol.read(rd_hub.DONE, 4), (0x80010024).to_bytes(4, "big"))   # lwz r0, 0x24(r1)

    def test_bad_setups_are_refused(self):
        from fe_modding import hub, hub_fe10
        cases = [
            (dict(chapter=3), "added chapter"),
            (dict(activation_chapter=56), "activation chapter"),
            (dict(avatar_pid="PID_MICAIAH"), "avatar PID_MICAIAH alone"),
            (dict(avatar_pid="PID_NOBODY"), "no character record"),
            (dict(destinations=()), "at least one destination"),
            (dict(destinations=(hub.Destination(2, 7, 20, 6, 20),)), "missing its script, map or deployment"),
            (dict(destinations=(hub.Destination(3, 7, 20, 6, 20, "Go"),)), "descriptions"),
        ]
        for changes, message in cases:
            with self.subTest(changes=changes), self.assertRaisesRegex(ValueError, message):
                hub_fe10.prepare(self.project, self.setup(**changes))


if __name__ == "__main__":
    unittest.main()
