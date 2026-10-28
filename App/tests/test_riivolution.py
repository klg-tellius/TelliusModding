import os
import stat
import struct
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fe_modding import config, riivolution, tools, vanilla_store
from fe_modding.formats import gcdisc
from fe_modding.game_code.dol import Dol
from fe_modding.games import Game
from fe_modding.project import LAYOUT_OVERLAY, ModProject

TEXT, DATA, BSS = 0x80003100, 0x80004000, 0x80005000


def make_dol(text: bytes = bytes(range(32)), data: bytes = b"D" * 16, entry: int = TEXT) -> bytes:
    header = bytearray(0x100)
    struct.pack_into(">I", header, 0, 0x100)                  # text 0
    struct.pack_into(">I", header, 72, TEXT)
    struct.pack_into(">I", header, 144, len(text))
    struct.pack_into(">I", header, 7 * 4, 0x100 + len(text))   # data 0 (slot 7)
    struct.pack_into(">I", header, 72 + 7 * 4, DATA)
    struct.pack_into(">I", header, 144 + 7 * 4, len(data))
    struct.pack_into(">3I", header, 216, BSS, 0x100, entry)
    return bytes(header) + text + data


class MemoryPatchTests(unittest.TestCase):
    def test_changed_ranges_carry_their_retail_bytes(self):
        text = bytearray(range(32))
        text[4:6] = b"\xff\xff"
        text[9] = 0xEE              # within MERGE_GAP of the first change: one patch
        text[28] = 0xAA
        patches = riivolution.memory_patches(Dol(make_dol()), Dol(make_dol(bytes(text))))
        self.assertEqual([(hex(p.address), p.value, p.original) for p in patches], [
            (hex(TEXT + 4), bytes(text[4:10]), bytes(range(4, 10))),
            (hex(TEXT + 28), b"\xaa", bytes([28])),
        ])

    def test_an_added_section_is_written_whole(self):
        modded = Dol(make_dol())
        modded.add_text_section(0x81700000, b"CAVECODE")
        patches = riivolution.memory_patches(Dol(make_dol()), modded)
        self.assertEqual([(p.address, p.value, p.original) for p in patches], [(0x81700000, b"CAVECODE", None)])

    def test_what_memory_patches_cannot_do_is_refused(self):
        vanilla = Dol(make_dol())
        with self.assertRaisesRegex(riivolution.RiivolutionError, "entry point"):
            riivolution.memory_patches(vanilla, Dol(make_dol(entry=TEXT + 4)))
        in_bss = Dol(make_dol())
        in_bss.add_text_section(BSS + 0x10, b"X" * 8)
        with self.assertRaisesRegex(riivolution.RiivolutionError, "bss"):
            riivolution.memory_patches(vanilla, in_bss)
        with self.assertRaisesRegex(riivolution.RiivolutionError, "smaller"):
            riivolution.memory_patches(vanilla, Dol(make_dol(text=bytes(range(16)))))

    def test_xml_is_a_wiidisc_with_one_option(self):
        xml = riivolution.patch_xml("RFEE01", "My Mod", "My_Mod", [riivolution.MemoryPatch(TEXT, b"\x60\x00\x00\x00", b"\x4e\x80\x00\x20")], True)
        root = ET.fromstring(xml)
        self.assertEqual(root.find("id").get("game"), "RFEE")
        self.assertEqual(root.find("options/section/option/choice/patch").get("id"), "My_Mod")
        patch = root.find("patch")
        self.assertEqual(patch.get("root"), "/My_Mod")
        self.assertEqual(patch.find("folder").get("disc"), "/")
        self.assertEqual(patch.find("memory").attrib, {"offset": "0x80003100", "value": "60000000", "original": "4E800020"})


WII_TREE = {
    "sys/boot.bin": b"RFEE01\x00\x01" + bytes(0x438),
    "sys/bi2.bin": b"bi2", "sys/apploader.img": b"apploader", "sys/fst.bin": b"fst",
    "sys/main.dol": make_dol(),
    "disc/header.bin": b"h", "ticket.bin": b"t", "tmd.bin": b"m", "cert.bin": b"c",
    "files/FE10Data.cms": b"data",
    "files/Mess/e_common.m": b"common",
}


class ExportTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._cleanup)
        self.tmp = Path(self._tmp.name)
        sizes = {rel[len("files/"):]: len(d) for rel, d in WII_TREE.items() if rel.startswith("files/")}

        def extract(source, dest, **_):
            for rel, data in WII_TREE.items():
                (Path(dest) / rel).parent.mkdir(parents=True, exist_ok=True)
                (Path(dest) / rel).write_bytes(data)
        for patcher in (
                mock.patch.object(config, "load_setting", lambda key, default=None: str(self.tmp / "stores")
                                  if key == vanilla_store.SETTING_KEY else default),
                mock.patch.object(gcdisc, "read_fst_sizes", lambda _data: sizes),
                mock.patch.object(tools, "extract_disc", extract)):
            patcher.start()
            self.addCleanup(patcher.stop)
        disc = self.tmp / "rd.wbfs"
        disc.write_bytes(b"x")
        self.project = ModProject.create(self.tmp, "Dawn Mod", Game.RADIANT_DAWN, layout=LAYOUT_OVERLAY)
        self.project.set_source(disc)
        self.project.extract()

    def _cleanup(self):
        for path in self.tmp.rglob("*"):
            if path.is_file():
                os.chmod(path, stat.S_IREAD | stat.S_IWRITE)
        self._tmp.cleanup()

    def test_export_holds_the_changed_files_and_dol_patches(self):
        files = self.project.files
        files.write("files/FE10Data.cms", b"edited")
        files.write("files/Mess/e_c0101.m", b"added")
        files.remove("files/Mess/e_common.m")
        text = bytearray(range(32))
        text[0:4] = b"\x60\x00\x00\x00"
        files.write("sys/main.dol", make_dol(bytes(text)))
        result = riivolution.export_project(self.project)
        self.assertEqual(sorted(result.files), ["files/FE10Data.cms", "files/Mess/e_c0101.m"])
        self.assertEqual((result.folder / "Dawn_Mod" / "files" / "FE10Data.cms").read_bytes(), b"edited")
        self.assertEqual([(p.address, p.value) for p in result.memory], [(TEXT, b"\x60\x00\x00\x00")])
        self.assertIn("e_common.m", result.warnings[0])
        root = ET.parse(result.xml).getroot()
        self.assertEqual(root.find("id").get("game"), "RFEE")
        self.assertEqual(len(root.findall("patch/memory")), 1)

    def test_path_of_radiance_is_refused(self):
        project = ModProject.create(self.tmp, "PoR", Game.PATH_OF_RADIANCE, layout=LAYOUT_OVERLAY)
        with self.assertRaisesRegex(riivolution.RiivolutionError, "Wii"):
            riivolution.export_project(project)


if __name__ == "__main__":
    unittest.main()
