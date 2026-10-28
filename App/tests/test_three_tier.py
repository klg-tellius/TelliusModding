"""Retail-image regression checks for the opt-in three-tier patch."""

import io
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fe_modding.formats import fe8data, message
from fe_modding.game_code.catalog import Session, State
from fe_modding.game_code.dol import Dol
from fe_modding.game_code.editor import CodeEditor
from fe_modding.game_code.three_tier_code import PATCH
from fe_modding.game_code.three_tier_data import provision, provision_messages
from fe_modding.game_code.versions import VERSIONS
from fe_modding.gui.pages.code import CodePage


ROOT = Path(__file__).resolve().parents[2] / "research" / "main_dol" / "extracted"
REGIONS = (("GFEP01", "P-GFEP", 98), ("GFEJ01", "P-GFEJ", 97))


class ThreeTierRetailTests(unittest.TestCase):
    def test_regional_data_and_messages(self):
        for version, folder, count in REGIONS:
            root = ROOT / version / folder
            with self.subTest(version=version):
                if not root.exists():
                    continue
                source = (root / "files" / "FE8Data.bin").read_bytes()
                patched = provision(source, version)
                before, after = fe8data.read_fe8data(source), fe8data.read_fe8data(patched)
                self.assertEqual(len(after.skills), count + 1)
                self.assertEqual(after.skills[-1].sid, "SID_TIER3")
                self.assertEqual(after.skills[-1].index, count)
                self.assertEqual(after.items[-1].iid, "IID_MASTERCROWN")
                self.assertEqual(before.characters, after.characters)
                self.assertEqual(before.classes, after.classes)
                self.assertEqual(before.items, after.items[:-1])
                self.assertEqual(provision(patched, version), patched)
                names = {"GFEP01": ("common.m", "d_common.m", "f_common.m",
                                      "i_common.m", "s_common.m"),
                         "GFEJ01": ("common.m",)}[version]
                for filename in names:
                    lang = {"d": "de", "f": "fr", "i": "it", "s": "es"}.get(filename[0], "en")
                    original = (root / "files" / "Mess" / filename).read_bytes()
                    updated = provision_messages(original, version, lang)
                    keys = {m.speaker for m in message.read_messages(io.BytesIO(updated))}
                    self.assertIn("MIID_MASTERCROWN", keys)
                    self.assertIn("MH_I_MASTERCROWN", keys)
                    self.assertEqual(provision_messages(updated, version, lang), updated)

    def test_regional_dol_round_trip(self):
        for version, folder, _ in REGIONS:
            path = ROOT / version / folder / "sys" / "main.dol"
            with self.subTest(version=version):
                if not path.exists():
                    continue
                dol = Dol(path.read_bytes())
                original = bytes(dol.data)
                session = Session(dol, VERSIONS[version])
                self.assertEqual(session.patch_status(PATCH).state, State.ORIGINAL)
                session.set_patch(PATCH, True)
                self.assertEqual(session.patch_status(PATCH).state, State.APPLIED)
                session.set_patch(PATCH, False)
                self.assertEqual(bytes(dol.data), original)

    def test_page_enable_provisions_every_european_language(self):
        source = ROOT / "GFEP01" / "P-GFEP"
        if not source.exists():
            self.skipTest("Extracted European retail image is unavailable")
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            paths = ["sys/main.dol", "sys/boot.bin", "files/FE8Data.bin"] + [
                f"files/Mess/{name}" for name in
                ("common.m", "d_common.m", "f_common.m", "i_common.m", "s_common.m")]
            for name in paths:
                destination = root / name
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(source / name, destination)

            class Project:
                extracted_dir = root

                @staticmethod
                def write_keeping_original(path, data):
                    path.write_bytes(data)

            class DataSession:
                available = True
                file_label = "FE8Data.bin"
                dirty = False

                def __init__(self):
                    self.data = (root / "files/FE8Data.bin").read_bytes()

                def changed(self, _source):
                    fe8data.read_fe8data(self.data)
                    self.dirty = True

            class Changelog:
                def append(self, *_args):
                    pass

            project = Project()
            session = DataSession()
            page = SimpleNamespace(project=project,
                                   editor=CodeEditor(root, project.write_keeping_original),
                                   shell=SimpleNamespace(session=session, changelog=Changelog()))
            CodePage._enable_three_tiers(page, PATCH)
            self.assertTrue(session.dirty)
            self.assertEqual(fe8data.read_fe8data(session.data).skills[-1].sid, "SID_TIER3")
            self.assertEqual(page.editor.status(PATCH).state, State.APPLIED)
            for name in ("common.m", "d_common.m", "f_common.m", "i_common.m", "s_common.m"):
                entries = message.read_messages_path(root / "files/Mess" / name)
                self.assertIn("MIID_MASTERCROWN", {entry.speaker for entry in entries})


class CrownLevelCheckTests(unittest.TestCase):
    """The Master Crown's level gate runs: it read address 0x2DF1 (an r0-based load) and crashed."""

    def test_second_tier_reads_the_minimum_level_from_the_cave(self):
        from fe_modding.game_code import three_tier_code as ttc
        from tests.test_chapter_flow import MiniPPC

        for version in ttc._SITES:
            can = ttc._SITES[version][0]
            code = {}
            for edit in ttc.edits_for(version):
                if edit.address == ttc.CROWN_LEVEL_CHECK:
                    for i in range(0, len(edit.patched), 4):
                        code[edit.address + i] = int.from_bytes(edit.patched[i:i + 4], "big")
            unit = 0x80400000
            for flags, expected in ((4, 13), (0, 10)):          # +0x1BC bit 2: already promoted
                memory = {ttc.CROWN_MIN_LEVEL: 13, unit + 0x1BF: flags}
                cpu = MiniPPC(code, memory)
                cpu.r[31] = unit
                self.assertEqual(cpu.run(ttc.CROWN_LEVEL_CHECK, {can + 0x9C}), can + 0x9C)
                self.assertEqual(cpu.r[0], expected, (version, flags))


if __name__ == "__main__":
    unittest.main()
