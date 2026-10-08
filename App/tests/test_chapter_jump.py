import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fe_modding import emulator
from fe_modding.game_code import chapter_jump, entries  # noqa: F401  (registers the catalog)
from fe_modding.game_code.catalog import CATALOG, Session, State
from fe_modding.game_code.chapter_jump import (DIFFICULTIES, JUMP_PATCH, JUMP_PREDICATE, JUMP_RECORD, JUMP_STUB,
                                               _SITES)
from fe_modding.game_code.dol import Dol
from fe_modding.game_code.versions import VERSIONS

from test_chapter_flow import RETAIL_DIR, _s16


class JumpPPC:
    """Just enough of a PowerPC to run the jump stub and the label-5 check: memory is a dict of bytes."""

    def __init__(self, code: dict[int, int], memory: dict[int, int]):
        self.code, self.memory = code, memory
        self.r = [0] * 32
        self.eq = False

    def run(self, pc: int, until: set[int]) -> int:
        """Run from ``pc`` until it reaches an address of ``until`` (returned) or returns (-1)."""
        for _ in range(100):
            if pc in until:
                return pc
            w = self.code[pc]
            op, rd, ra, imm = w >> 26, (w >> 21) & 31, (w >> 16) & 31, w & 0xFFFF
            address = ((self.r[ra] if ra else 0) + _s16(imm)) & 0xFFFFFFFF
            nxt = pc + 4
            if op == 14:                                    # addi / li
                self.r[rd] = address
            elif op == 15:                                  # lis
                self.r[rd] = (imm << 16) & 0xFFFFFFFF
            elif op == 38:                                  # stb
                self.memory[address] = self.r[rd] & 0xFF
            elif op == 32:                                  # lwz
                self.r[rd] = int.from_bytes(bytes(self.memory.get(address + i, 0) for i in range(4)), "big")
            elif op == 11:                                  # cmpwi
                self.eq = self.r[ra] == _s16(imm) & 0xFFFFFFFF
            elif w == 0x4C820020:                           # bnelr
                if not self.eq:
                    return -1
            elif op == 18:                                  # b
                delta = w & 0x03FFFFFC
                nxt = pc + (delta - 0x04000000 if delta & 0x02000000 else delta)
            else:
                raise AssertionError(f"unexpected instruction {w:08X} at {pc:08X}")
            pc = nxt
        raise AssertionError("runaway")


def _retail(code: str) -> Dol:
    path = RETAIL_DIR / f"{code}.dol"
    if not path.is_file():
        raise unittest.SkipTest("no retail DOL")
    return Dol.open(path)


class StubTests(unittest.TestCase):
    def _installed(self, code: str, position: int, difficulty: int) -> Dol:
        dol = _retail(code)
        chapter_jump.install(Session(dol, VERSIONS[code]), position, difficulty)
        return dol

    def test_stub_sets_difficulty_and_passes_the_position(self):
        for code in VERSIONS:
            start, _title, call, file_menu, init_chapter, party = _SITES[code]
            for position, difficulty in ((44, DIFFICULTIES["Maniac"]), (2, DIFFICULTIES["Easy"])):
                with self.subTest(code=code, position=position):
                    dol = self._installed(code, position, difficulty)
                    self.assertEqual(list(dol.words(start, 2)), [0x200F, JUMP_STUB])
                    self.assertEqual(dol.words(call, 1)[0], JUMP_PREDICATE)
                    cave = dol.read(JUMP_STUB, 0x40)
                    code_words = {JUMP_STUB + i: int.from_bytes(cave[i:i + 4], "big") for i in range(0, 0x40, 4)}
                    memory = {JUMP_STUB + i: b for i, b in enumerate(cave)}
                    cpu = JumpPPC(code_words, memory)
                    self.assertEqual(cpu.run(JUMP_STUB, {init_chapter}), init_chapter)
                    self.assertEqual(memory[party + 0xA6], difficulty)
                    self.assertEqual(cpu.r[3], JUMP_RECORD)
                    self.assertEqual(memory[cpu.r[3] + 4], position)

    def test_file_menu_only_while_the_next_label_is_5(self):
        for code in VERSIONS:
            file_menu = _SITES[code][3]
            dol = self._installed(code, 1, 0)
            cave = dol.read(JUMP_STUB, 0x40)
            code_words = {JUMP_STUB + i: int.from_bytes(cave[i:i + 4], "big") for i in range(0, 0x40, 4)}
            for label, expected in ((5, file_menu), (10, -1)):
                cpu = JumpPPC(code_words, {0x1000 + 0x63: label})
                cpu.r[3] = 0x1000
                self.assertEqual(cpu.run(JUMP_PREDICATE, {file_menu}), expected, (code, label))

    def test_install_replaces_the_boot_menu_and_reverts_to_retail(self):
        dol = _retail("GFEE01")
        retail = bytes(dol.data)
        session = Session(dol, VERSIONS["GFEE01"])
        boot_menu = CATALOG.entries["dev.boot_menu"]
        session.set_patch(boot_menu, True)
        chapter_jump.install(session, 5, 1)
        self.assertEqual(session.patch_status(JUMP_PATCH).state, State.APPLIED)
        # the boot menu's title pointer is back, its label-5 call now belongs to the jump
        self.assertEqual(session.patch_status(boot_menu).state, State.CONFLICT)
        session.set_patch(JUMP_PATCH, False)
        self.assertEqual(session.patch_status(boot_menu).state, State.ORIGINAL)
        self.assertEqual(bytes(dol.data), retail)

    def test_bad_values_are_refused(self):
        session = Session(_retail("GFEE01"), VERSIONS["GFEE01"])
        with self.assertRaises(ValueError):
            chapter_jump.install(session, 200, 0)
        with self.assertRaises(ValueError):
            chapter_jump.install(session, 1, 7)


class RunFolderTests(unittest.TestCase):
    def setUp(self):
        dol = RETAIL_DIR / "GFEE01.dol"
        if not dol.is_file():
            self.skipTest("no retail DOL")
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        self.extracted = root / "extracted"
        (self.extracted / "sys").mkdir(parents=True)
        (self.extracted / "files").mkdir()
        shutil.copy(dol, self.extracted / "sys" / "main.dol")
        (self.extracted / "sys" / "boot.bin").write_bytes(b"GFEE01\x00\x00" + bytes(0x438))
        (self.extracted / "sys" / "bi2.bin").write_bytes(b"bi2")
        (self.extracted / "files" / "FE8Data.bin").write_bytes(b"fe8")
        self.run_dir = root / "build" / emulator.RUN_FOLDER
        self.retail = dol.read_bytes()
        self.addCleanup(self._unlink)

    def _unlink(self):
        link = self.run_dir / "files"
        if os.path.lexists(link):
            os.rmdir(link) if sys.platform == "win32" else os.unlink(link)

    def test_tree_boots_the_chapter_and_leaves_the_project_alone(self):
        with mock.patch.object(emulator, "chapter_position", return_value=7) as position:
            main = emulator.prepare_chapter_run(self.extracted, self.run_dir, 8, DIFFICULTIES["Hard"])
            emulator.prepare_chapter_run(self.extracted, self.run_dir, 8, DIFFICULTIES["Hard"])   # reuses the link
        position.assert_called_with(b"fe8", 8)
        self.assertEqual(main, self.run_dir / "sys" / "main.dol")
        self.assertEqual((self.extracted / "sys" / "main.dol").read_bytes(), self.retail)
        self.assertEqual((self.run_dir / "sys" / "bi2.bin").read_bytes(), b"bi2")
        self.assertEqual((self.run_dir / "files" / "FE8Data.bin").read_bytes(), b"fe8")
        dol = Dol.open(main)
        self.assertEqual(dol.read(JUMP_RECORD + 4, 1), bytes([7]))
        self.assertEqual(dol.read(JUMP_STUB + 2, 2), DIFFICULTIES["Hard"].to_bytes(2, "big"))

    def test_a_real_folder_in_the_way_is_not_deleted(self):
        (self.run_dir / "files").mkdir(parents=True)
        (self.run_dir / "files" / "keep.txt").write_text("x")
        with mock.patch.object(emulator, "chapter_position", return_value=1):
            with self.assertRaises(emulator.EmulatorError):
                emulator.prepare_chapter_run(self.extracted, self.run_dir, 2, 0)
        self.assertTrue((self.run_dir / "files" / "keep.txt").is_file())
        shutil.rmtree(self.run_dir / "files")

    def test_unknown_chapter(self):
        with self.assertRaises(emulator.EmulatorError):
            emulator.chapter_position(b"", 5)


if __name__ == "__main__":
    unittest.main()
