import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fe_modding.formats import game_text
from fe_modding.formats.fe9_font import char_of, code_of


class GameTextTests(unittest.TestCase):
    def tearDown(self):
        game_text.use_game_id(None)

    def test_us_and_jp_are_cp932(self):
        for game_id in ("GFEE01", "GFEJ01"):
            game_text.use_game_id(game_id)
            raw = "アイク".encode("cp932")
            self.assertEqual(game_text.decode(raw), "アイク")
            self.assertEqual(game_text.encode("アイク"), raw)
            self.assertEqual(game_text.from_raw(raw.decode("cp437")), "アイク")
            self.assertEqual(code_of("ア"), 0x8341)

    def test_pal_mixes_latin1_letters_and_two_byte_kana(self):
        game_text.use_game_id("GFEP01")
        raw = b"D\xe9j\xe0 " + "会話".encode("cp932")
        text = game_text.decode(raw)
        self.assertEqual(text, "Déjà 会話")
        self.assertEqual(game_text.encode(text), raw)
        self.assertEqual(code_of("à"), 0xE0)
        self.assertEqual(char_of(0xFC), "ü")
        self.assertEqual(char_of(0x8341), "ア")
        with self.assertRaises(UnicodeEncodeError):
            game_text.encode(bytes((0xE0, 0x40)).decode("cp932"))      # CP932 lead byte 0xE0+: no PAL code
        self.assertEqual(game_text.to_raw(game_text.from_raw(raw.decode("cp437"))), raw.decode("cp437"))

    def test_stray_bytes_survive(self):
        for game_id in ("GFEE01", "GFEP01"):
            game_text.use_game_id(game_id)
            raw = b"A\x1d\xed"
            self.assertEqual(game_text.encode(game_text.decode(raw)), raw)

    def test_mode_follows_boot_bin(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            sys_dir = Path(tmp) / "sys"
            sys_dir.mkdir()
            (sys_dir / "boot.bin").write_bytes(b"GFEP01" + bytes(10))
            game_text.use_for_extraction(Path(tmp) / "files")
            self.assertEqual(game_text.mode(), game_text.PAL)
            game_text.use_for_extraction(Path(tmp))
            self.assertEqual(game_text.mode(), game_text.PAL)


if __name__ == "__main__":
    unittest.main()
