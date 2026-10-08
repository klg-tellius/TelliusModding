import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fe_modding import games
from fe_modding.game_profile import (AI, GAME_DATA, PATH_OF_RADIANCE_PROFILE, RADIANT_DAWN_PROFILE, SHOPS,
                                     files_dir_of, game_for_disc_id, get_profile, logical_path_of, profile_of)
from fe_modding.games import Game


def _boot(root: Path, disc_id: bytes) -> None:
    (root / "sys").mkdir(parents=True, exist_ok=True)
    (root / "sys" / "boot.bin").write_bytes(disc_id + b"\x00\x01" + bytes(0x438))


class ProfileTests(unittest.TestCase):
    def test_every_game_has_a_profile_with_its_disc_prefix(self):
        for game in Game:
            self.assertIs(get_profile(game).game, game)
            self.assertIs(games.profile(game), get_profile(game))
        self.assertEqual(PATH_OF_RADIANCE_PROFILE.disc_id_prefix, "GFE")
        self.assertEqual(RADIANT_DAWN_PROFILE.disc_id_prefix, "RFE")
        self.assertFalse(PATH_OF_RADIANCE_PROFILE.wii)
        self.assertTrue(RADIANT_DAWN_PROFILE.wii)

    def test_logical_files_map_to_each_games_names(self):
        files = Path("x/files")
        self.assertEqual(PATH_OF_RADIANCE_PROFILE.path(files, "game_data"), files / "FE8Data.bin")
        self.assertEqual(RADIANT_DAWN_PROFILE.path(files, "game_data"), files / "FE10Data.cms")
        self.assertEqual(PATH_OF_RADIANCE_PROFILE.path(files, "battle_data"), files / "zdbx.cmp")
        self.assertEqual(RADIANT_DAWN_PROFILE.path(files, "battle_data"), files / "FE10Battle.cms")
        self.assertEqual(RADIANT_DAWN_PROFILE.path(files, "ai_data"), files / "Cp" / "cp_data.cms")
        self.assertTrue(RADIANT_DAWN_PROFILE.logical("game_data").compressed)
        self.assertFalse(PATH_OF_RADIANCE_PROFILE.logical("game_data").compressed)
        self.assertEqual(RADIANT_DAWN_PROFILE.file_label("game_data"), "FE10Data.cms")
        self.assertEqual(PATH_OF_RADIANCE_PROFILE.file_label("game_data"), "FE8Data.bin")
        self.assertFalse(RADIANT_DAWN_PROFILE.has_file("system_archive"))
        self.assertIsNone(RADIANT_DAWN_PROFILE.path_or_none(files, "system_archive"))
        with self.assertRaises(KeyError):
            RADIANT_DAWN_PROFILE.path(files, "system_archive")

    def test_chapter_files(self):
        files = Path("f")
        por, rd = PATH_OF_RADIANCE_PROFILE, RADIANT_DAWN_PROFILE
        self.assertEqual(por.script_path(files, "5"), files / "Scripts" / "C05.cmb")
        self.assertEqual(por.mess_path(files, "05"), files / "Mess" / "c05.m")
        self.assertEqual(por.map_folder("5"), "bmap05")
        self.assertEqual(por.deployment_path(files, "bmap05"), files / "zmap" / "bmap05" / "dispos.cmp")
        self.assertEqual(rd.script_path(files, "0407a"), files / "Scripts" / "C0407a.cmb")
        self.assertEqual(rd.mess_path(files, "0101"), files / "Mess" / "c0101.m")
        self.assertEqual(rd.map_folder("0101"), "bmap0101")
        self.assertEqual(rd.deployment_path(files, "bmap0101", "h"), files / "zmap" / "bmap0101" / "dispos_h.bin")
        self.assertEqual(rd.shop_path(files, "n"), files / "Shop" / "shopitem_n.bin")
        self.assertEqual(por.shop_path(files, "m"), files / "shop" / "shopitem_m.bin")

    def test_chapter_ids_sort_in_story_order(self):
        rd = RADIANT_DAWN_PROFILE
        ids = ["final", "0407b", "0102", "0407a", "0101", "0406"]
        self.assertEqual(sorted(ids, key=rd.chapter_sort_key), ["0101", "0102", "0406", "0407a", "0407b", "final"])
        self.assertEqual(sorted(["10", "02", "1"], key=PATH_OF_RADIANCE_PROFILE.chapter_sort_key), ["1", "02", "10"])

    def test_features_gate_what_has_a_decoder(self):
        self.assertTrue(PATH_OF_RADIANCE_PROFILE.supports(GAME_DATA))
        self.assertFalse(RADIANT_DAWN_PROFILE.supports(GAME_DATA))
        self.assertEqual(RADIANT_DAWN_PROFILE.unavailable(SHOPS), "Shop editing is not available for Radiant Dawn yet.")
        self.assertIn("AI editing", RADIANT_DAWN_PROFILE.unavailable(AI))

    def test_disc_ids(self):
        self.assertIs(game_for_disc_id("GFEE01"), Game.PATH_OF_RADIANCE)
        self.assertIs(game_for_disc_id("GFEJ01"), Game.PATH_OF_RADIANCE)
        self.assertIs(game_for_disc_id("RFEP01"), Game.RADIANT_DAWN)
        self.assertIsNone(game_for_disc_id("RSBE01"))
        self.assertIsNone(game_for_disc_id(""))

    def test_detect_from_extracted_reads_boot_bin(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.assertIsNone(games.detect_from_extracted(root))
            self.assertEqual(games.read_disc_id(root), "")
            _boot(root, b"RFEE01")
            self.assertEqual(games.read_disc_id(root), "RFEE01")
            self.assertIs(games.detect_from_extracted(root), Game.RADIANT_DAWN)
            _boot(root, b"GFEP01")
            self.assertIs(games.detect_from_extracted(root), Game.PATH_OF_RADIANCE)
            _boot(root, b"ABCD01")
            self.assertIsNone(games.detect_from_extracted(root))

    def test_image_header_ids(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            iso = root / "a.iso"
            iso.write_bytes(b"GFEE01" + bytes(100))
            wbfs = root / "b.wbfs"
            wbfs.write_bytes(bytes(0x200) + b"RFEE01" + bytes(100))
            ciso = root / "c.ciso"
            ciso.write_bytes(bytes(0x8000) + b"GFEP01" + bytes(100))
            rvz = root / "d.rvz"
            rvz.write_bytes(b"RVZ\x01" + bytes(100))
            self.assertEqual(games.read_image_disc_id(iso), "GFEE01")
            self.assertEqual(games.read_image_disc_id(wbfs), "RFEE01")
            self.assertEqual(games.read_image_disc_id(ciso), "GFEP01")
            self.assertEqual(games.read_image_disc_id(rvz), "")
            self.assertEqual(games.read_image_disc_id(root / "missing.iso"), "")

    def test_rvz_is_an_accepted_disc_format_for_both_games(self):
        for info in games.all_games():
            self.assertIn(".rvz", info.disc_formats)
            self.assertIn(".rvz", games.DOLPHIN_ONLY_FORMATS)

    def test_profile_of_tolerates_stand_ins(self):
        self.assertIs(profile_of(SimpleNamespace()), PATH_OF_RADIANCE_PROFILE)
        self.assertIs(profile_of(SimpleNamespace(game=Game.RADIANT_DAWN)), RADIANT_DAWN_PROFILE)
        stand_in = SimpleNamespace(extracted_dir=Path("e"))
        self.assertEqual(files_dir_of(stand_in), Path("e") / "files")
        self.assertEqual(logical_path_of(stand_in, "game_data"), Path("e") / "files" / "FE8Data.bin")


class ChapterKeyTests(unittest.TestCase):
    def test_ids_match_across_padding_and_case(self):
        from fe_modding.gui.pages.text_assets import _chapter_key

        self.assertEqual(_chapter_key("01"), _chapter_key("1"))
        self.assertEqual(_chapter_key("00"), "0")
        self.assertEqual(_chapter_key("0407A"), _chapter_key("0407a"))
        self.assertEqual(_chapter_key("final"), "final")


if __name__ == "__main__":
    unittest.main()
