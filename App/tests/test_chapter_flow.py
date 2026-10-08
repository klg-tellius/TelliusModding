import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fe_modding.game_code import chapter_flow
from fe_modding.game_code.catalog import CAVE_ADDRESS, State
from fe_modding.game_code.chapter_flow import FLOW_HOOK, FLOW_PATCH, FLOW_TABLE, SAVE_CHECK

RETAIL_DIR = Path(__file__).resolve().parents[2] / "research" / "main_dol" / "dols"
PARTY = 0x80330708


def _s16(value: int) -> int:
    return value - 0x10000 if value & 0x8000 else value


class MiniPPC:
    """Just enough of a PowerPC to run the two flow stubs: memory is a dict of bytes."""

    def __init__(self, code: dict[int, int], memory: dict[int, int]):
        self.code, self.memory = code, memory
        self.r = [0] * 32
        self.cr0 = (False, False, False)        # lt, gt, eq

    def _compare(self, a: int, b: int, signed: bool) -> None:
        if signed:
            a, b = (a - (1 << 32) if a & 0x80000000 else a), (b - (1 << 32) if b & 0x80000000 else b)
        self.cr0 = (a < b, a > b, a == b)

    def run(self, pc: int, until: set[int]) -> int:
        """Run from ``pc`` until it reaches an address of ``until`` (returned) or a ``blr`` (-1)."""
        for _ in range(100):
            if pc in until:
                return pc
            w = self.code[pc]
            op = w >> 26
            rd, ra, rb, imm = (w >> 21) & 31, (w >> 16) & 31, (w >> 11) & 31, w & 0xFFFF
            base = self.r[ra] if ra else 0
            nxt = pc + 4
            if op == 34:                                    # lbz
                self.r[rd] = self.memory.get((base + _s16(imm)) & 0xFFFFFFFF, 0)
            elif op == 15:                                  # lis
                self.r[rd] = (imm << 16) & 0xFFFFFFFF
            elif op == 14:                                  # addi / li
                self.r[rd] = (base + _s16(imm)) & 0xFFFFFFFF
            elif op == 11:                                  # cmpwi
                self._compare(self.r[ra], _s16(imm) & 0xFFFFFFFF, True)
            elif op == 10:                                  # cmplwi
                self._compare(self.r[ra], imm, False)
            elif op == 31 and (w >> 1) & 0x3FF == 87:       # lbzx
                self.r[rd] = self.memory.get((base + self.r[rb]) & 0xFFFFFFFF, 0)
            elif op == 31 and (w >> 1) & 0x3FF == 32:       # cmplw
                self._compare(self.r[ra], self.r[rb], False)
            elif op == 31 and (w >> 1) & 0x3FF == 444:      # or (mr)
                self.r[ra] = self.r[rd] | self.r[rb]
            elif op == 18:                                  # b
                delta = w & 0x03FFFFFC
                nxt = pc + (delta - 0x04000000 if delta & 0x02000000 else delta)
            elif op == 16:                                  # bc on cr0
                bo, bi = rd, ra
                bit = self.cr0[bi]
                if bit == bool(bo & 8):
                    nxt = pc + _s16(w & 0xFFFC)
            elif w == 0x4E800020:                           # blr
                return -1
            else:
                raise AssertionError(f"unexpected instruction {w:08X} at {pc:08X}")
            pc = nxt
        raise AssertionError("runaway")


def _code(version: str) -> dict[int, int]:
    words = {}
    for edit in FLOW_PATCH.versions[version]:
        if edit.address >= CAVE_ADDRESS:
            for i in range(0, len(edit.patched), 4):
                words[edit.address + i] = int.from_bytes(edit.patched[i:i + 4], "big")
    return words


class StubTests(unittest.TestCase):
    def setUp(self):
        self.set_chapter = chapter_flow._SITES["GFEE01"][0]
        self.code = _code("GFEE01")

    def _advance(self, current: int, table: dict[int, int]) -> int:
        memory = {PARTY + 0x10: current, **{FLOW_TABLE + c: n for c, n in table.items()}}
        cpu = MiniPPC(self.code, memory)
        cpu.r[3], cpu.r[4] = PARTY, (current + 1) & 0xFF
        self.assertEqual(cpu.run(FLOW_HOOK, {self.set_chapter}), self.set_chapter)
        self.assertEqual(cpu.r[3], PARTY)
        return cpu.r[4]

    def _save_allowed(self, chapter: int, table: dict[int, int]) -> bool:
        cpu = MiniPPC(self.code, {FLOW_TABLE + c: n for c, n in table.items()})
        cpu.r[0] = chapter
        self.assertEqual(cpu.run(SAVE_CHECK, set()), -1)
        return not cpu.cr0[1]                   # the caller's `ble` takes it unless "greater"

    def test_next_chapter_comes_from_the_table(self):
        self.assertEqual(self._advance(5, {}), 6)
        self.assertEqual(self._advance(5, {5: 40}), 40)
        self.assertEqual(self._advance(40, {5: 40, 40: 6}), 6)
        self.assertEqual(self._advance(31, {}), 32)

    def test_saving_is_allowed_for_story_chapters_only(self):
        table = {5: 40, 40: 6}
        for chapter in (0, 1, 31):
            self.assertTrue(self._save_allowed(chapter, table), chapter)
        self.assertTrue(self._save_allowed(40, table))
        for chapter in (32, 41, 91):
            self.assertFalse(self._save_allowed(chapter, table), chapter)

    def test_every_version_branches_to_its_own_set_current_chapter(self):
        for version, (set_chapter, *_rest) in chapter_flow._SITES.items():
            cpu = MiniPPC(_code(version), {PARTY + 0x10: 3})
            cpu.r[3], cpu.r[4] = PARTY, 4
            self.assertEqual(cpu.run(FLOW_HOOK, {set_chapter}), set_chapter, version)


class NameTableTests(unittest.TestCase):
    """The file menu's chapter-name table copied into the cave."""

    def test_copy_starts_with_each_builds_retail_table(self):
        import struct
        from fe_modding.game_code.dol import Dol
        pool, table = chapter_flow._name_data()

        def cave_string(address):
            end = pool.index(b"\x00", address - chapter_flow.NAME_STRINGS)
            return pool[address - chapter_flow.NAME_STRINGS:end].decode()

        copy = [struct.unpack_from(">III", table, 12 * i) for i in range(chapter_flow.NAME_ENTRIES)]
        self.assertEqual(copy[40][0], 33)
        self.assertNotIn(51, [c for c, _n, _h in copy])
        found = 0
        for version, sites in chapter_flow._NAME_SITES.items():
            path = RETAIL_DIR / f"{version}.dol"
            if not path.is_file():
                continue
            found += 1
            dol = Dol(path.read_bytes())
            lis, addi = sites[0][1], sites[1][1]
            low = addi & 0xFFFF
            retail = ((lis & 0xFFFF) << 16) + (low - 0x10000 if low & 0x8000 else low)
            for i in range(40):
                chapter, name, handle = dol.words(retail + 12 * i, 3)
                self.assertEqual(copy[i][0], chapter, (version, i))
                self.assertEqual(cave_string(copy[i][1]), dol.read(name, 32).split(b"\x00")[0].decode())
            # every site now builds the copy's address, and the counts cover 100 entries
            words = {a: chapter_flow._name_site_word(w) for a, w in sites}
            for (a, w), (b, v) in zip(sites, sites[1:]):
                if w >> 26 == 15 and v >> 26 == 14:
                    self.assertEqual((words[a] & 0xFFFF) << 16 | words[b] & 0xFFFF, chapter_flow.NAME_TABLE)
        if not found:
            self.skipTest("no retail DOLs")


class FlowEditorTests(unittest.TestCase):
    """ChapterFlow on a scratch copy of the retail US executable."""

    def setUp(self):
        path = RETAIL_DIR / "GFEE01.dol"
        if not path.is_file():
            self.skipTest("no retail DOL")
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        (self.root / "sys").mkdir()
        shutil.copy(path, self.root / "sys" / "main.dol")
        (self.root / "sys" / "boot.bin").write_bytes(b"GFEE01\x00\x00" + bytes(0x438))
        self.retail = path.read_bytes()

    def _flow(self):
        from fe_modding.game_code.editor import CodeEditor
        return chapter_flow.ChapterFlow(CodeEditor(self.root))

    def test_insert_then_remove_restores_retail(self):
        flow = self._flow()
        self.assertTrue(flow.available)
        self.assertEqual(flow.overrides(), {})
        self.assertEqual(flow.next_of(5), 6)
        flow.set_many({5: 40, 40: 6})
        reopened = self._flow()
        self.assertEqual(reopened.status.state, State.APPLIED)
        self.assertEqual(reopened.overrides(), {5: 40, 40: 6})
        self.assertEqual(reopened.order()[:8], [1, 2, 3, 4, 5, 40, 6, 7])
        self.assertEqual(reopened.predecessors(40), [5])
        self.assertTrue(reopened.is_story(40))
        self.assertFalse(reopened.is_story(41))
        self.assertEqual(reopened.editor.modified_entries(), [])      # the hook is internal
        reopened.remove(40)
        self.assertEqual(self._flow().overrides(), {})
        self.assertEqual((self.root / "sys" / "main.dol").read_bytes(), self.retail)

    def test_other_game_code_edits_keep_the_flow(self):
        from fe_modding.game_code.catalog import CATALOG
        flow = self._flow()
        flow.set_many({31: 33, 33: 32})
        luna = CATALOG.entries["proc.luna.scale"]
        flow.editor.set_value(luna, 8)
        flow.editor.set_value(luna, 4)             # its hook drops out; the flow hook must not
        self.assertEqual(self._flow().overrides(), {31: 33, 33: 32})

    def test_invalid_chapters_are_refused(self):
        flow = self._flow()
        with self.assertRaises(ValueError):
            flow.set_next(32, 33)                  # the ending has no next chapter
        with self.assertRaises(ValueError):
            flow.set_next(5, 95)                   # trial maps are not story chapters
        with self.assertRaises(ValueError):
            flow.remove(5)                         # retail chapters are routed around, not removed


@unittest.skipUnless(os.environ.get("FE9_EXTRACTED_FILES"), "set FE9_EXTRACTED_FILES to an extracted files/ directory")
class AddStoryChapterTests(unittest.TestCase):
    """add_story_chapter on a copy of the pieces of a real extraction it touches."""

    def setUp(self):
        from fe_modding.games import Game
        from fe_modding.project import ModProject
        source = Path(os.environ["FE9_EXTRACTED_FILES"])
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        self.project = ModProject.create(root, "flow", Game.PATH_OF_RADIANCE)
        files = self.project.extracted_dir / "files"
        (files / "Mess").mkdir(parents=True)
        (files / "Scripts").mkdir()
        for name in ("c09.m", "common.m"):
            shutil.copy(source / "Mess" / name, files / "Mess" / name)
        shutil.copy(source / "Scripts" / "C09.cmb", files / "Scripts" / "C09.cmb")
        for folder in ("bmap09", "bmap09_2", "bmap09_3", "bmap09_4", "bmap09_5", "bmap08"):
            shutil.copytree(source / "zmap" / folder, files / "zmap" / folder)
        shutil.copytree(source / "shop", files / "shop")
        (files / "Fonts").mkdir()
        shutil.copy(source / "Fonts" / "bigkana.gcf", files / "Fonts" / "bigkana.gcf")
        for folder in ("window/chapter", "window/chapter2"):
            (files / folder).mkdir(parents=True)
            shutil.copy(source / folder / "chap9.cms", files / folder / "chap9.cms")
        shutil.copy(source / "FE8Data.bin", files / "FE8Data.bin")
        sys_dir = self.project.extracted_dir / "sys"
        sys_dir.mkdir()
        dol = RETAIL_DIR / "GFEE01.dol"
        shutil.copy(dol if dol.is_file() else source.parent / "sys" / "main.dol", sys_dir / "main.dol")
        shutil.copy(source.parent / "sys" / "boot.bin", sys_dir / "boot.bin")
        self.files = files

    def test_new_chapter_is_complete_and_reachable(self):
        from fe_modding import chapters
        from fe_modding.formats import dispo, fe8data, lz10, pak, shop
        from fe_modding.formats.cmb import binary
        from fe_modding.game_code.editor import CodeEditor

        flow = chapter_flow.ChapterFlow(CodeEditor(self.project.extracted_dir))
        fe8 = (self.files / "FE8Data.bin").read_bytes()
        plan = chapters.add_story_chapter(self.project, fe8, "09", 33, "Ch.8x: A New Road", after=9, flow=flow)

        record = fe8data.read_chapter_data(plan.fe8data)[plan.record_index]
        self.assertEqual((record.chapter_id, record.map_name, record.script, record.message, record.title_key),
                         (33, "bmap33", "C33", "C33", "MCT33"))
        self.assertIn("bmap33", [r.map_name for r in fe8data.read_battle_terrain(plan.fe8data)])

        # the copied script loads and deploys its own (renamed) maps; the neighbour's map stays
        pool = binary.read_cmb((self.files / "Scripts" / "C33.cmb").read_bytes()).pool
        self.assertIn("bmap33", pool)
        self.assertIn("bmap33_5", pool)
        self.assertIn("bmap08", pool)
        self.assertFalse([s for s in pool if s.startswith("bmap09")])
        for folder in ("bmap33", "bmap33_2", "bmap33_3", "bmap33_4", "bmap33_5"):
            self.assertTrue((self.files / "zmap" / folder / "map.cmp").is_file(), folder)
        packed = lz10.decompress((self.files / "zmap" / "bmap33" / "dispos.cmp").read_bytes())
        names = []
        for entry in pak.read_pak_entries(packed):
            if entry.name.startswith("dispos_"):
                names += [s.name for s in dispo.read_dispo_bytes(pak.read_pak_file_content(packed, entry))]
        self.assertTrue(names and all("bmap09" not in n for n in names))
        self.assertIn("bmap33_mikata_c", names)

        for name in shop.DIFFICULTY_FILES.values():
            doc = shop.parse_shop((self.files / "shop" / name).read_bytes())
            self.assertIsNotNone(doc.shop("W", 33), name)
        self.assertEqual(chapters.chapter_titles(self.project)["33"], "Ch.8x: A New Road")
        from fe_modding import chapter_images
        strip = chapter_images.preview((self.files / "window/chapter2/chap33.cms").read_bytes())
        card = chapter_images.preview((self.files / "window/chapter/chap33.cms").read_bytes())
        self.assertEqual((strip.size, card.size), ((312, 32), (480, 160)))
        self.assertIsNotNone(strip.getchannel("A").getbbox())        # something was drawn

        reopened = chapter_flow.ChapterFlow(CodeEditor(self.project.extracted_dir))
        self.assertEqual(reopened.order()[:12], [1, 2, 3, 4, 5, 6, 7, 8, 9, 33, 10, 11])
        self.assertNotIn(33, chapters.free_chapter_ids(self.project))


if __name__ == "__main__":
    unittest.main()
