import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from PIL import Image

from fe_modding.formats import icons
from fe_modding.gui import model_viewer
from fe_modding.game_profile import ICONS, RADIANT_DAWN_PROFILE


def _sheet(width: int, height: int, size: int) -> Image.Image:
    """A sheet whose cell n is filled with colour (n % 256, 0, 0)."""
    image = Image.new("RGBA", (width, height))
    for cell in range((width // size) * (height // size)):
        row, column = divmod(cell, icons.COLUMNS)
        image.paste((cell % 256, 0, 0, 255), (column * size, row * size, (column + 1) * size, (row + 1) * size))
    return image


def _dbx(*blocks: dict) -> str:
    """A zdbx table: one ``{ key<TAB>value }`` block per dict."""
    return "# table\n" + "".join(
        "{\n" + "".join(f"\t{key}\t{value}\n" for key, value in block.items()) + "}\n" for block in blocks)


class IconCellTests(unittest.TestCase):
    def setUp(self):
        self.images = [_sheet(768, 216, 24), _sheet(1024, 96, 32)]

    def test_item_icon_n_is_cell_96_plus_n(self):
        self.assertEqual(icons.item_cell(0), 96)
        self.assertEqual(icons.item_icon(self.images, 0).getpixel((0, 0))[0], 96)
        self.assertEqual(icons.item_icon(self.images, 186).getpixel((5, 5))[0], 282 % 256)
        self.assertEqual(icons.item_icon(self.images, 0).size, (24, 24))

    def test_radiant_dawn_item_icon_n_is_cell_128_plus_n(self):
        """Seen in Dolphin: RD's Light (icon 115) draws cell 243; 96 + N is another item's picture."""
        from fe_modding.games import Game
        from fe_modding.gui.icon_viewer import SHEETS
        self.assertEqual(icons.item_cell(115, Game.RADIANT_DAWN), 243)
        self.assertEqual(icons.item_cell(115, Game.PATH_OF_RADIANCE), 211)
        rd_items = next(s for s in SHEETS[Game.RADIANT_DAWN] if s.item_icons)
        por_items = next(s for s in SHEETS[Game.PATH_OF_RADIANCE] if s.item_icons)
        self.assertEqual((rd_items.item_first_cell, por_items.item_first_cell), (128, 96))

    def test_radiant_dawn_sheet_path_and_compressed_read(self):
        """The shop lists read RD's icon.cms (LZ10) and its items from cell 128."""
        from unittest import mock
        from fe_modding.formats import lz10
        from fe_modding.games import Game
        self.assertEqual(icons.icon_path("files", Game.RADIANT_DAWN).as_posix(), "files/window/icon.cms")
        self.assertEqual(icons.icon_path("files").as_posix(), "files/window/icon.tpl")
        seen = []
        with mock.patch.object(icons.tpl, "read_tpl_images", lambda stream: seen.append(stream.read()) or self.images):
            images = icons.read_icon_images(lz10.compress(b"TPL bytes"))
        self.assertEqual(seen, [b"TPL bytes"])
        self.assertEqual(icons.item_icon(images, 0, Game.RADIANT_DAWN).getpixel((0, 0))[0], 128)

    def test_item_icon_outside_the_sheet_is_none(self):
        self.assertIsNone(icons.item_icon(self.images, 255))  # cell 351 of 288

    def test_skill_icon_n_is_cell_n_minus_1_and_0_is_none(self):
        self.assertIsNone(icons.skill_icon(self.images, 0))
        self.assertEqual(icons.skill_icon(self.images, 20).getpixel((0, 0))[0], 19)
        self.assertEqual(icons.skill_icon(self.images, 33).getpixel((31, 31))[0], 32)  # second row
        self.assertEqual(icons.skill_icon(self.images, 1).size, (32, 32))

    def test_radiant_dawn_icons_are_enabled(self):
        self.assertTrue(RADIANT_DAWN_PROFILE.supports(ICONS))


class WeaponModelTests(unittest.TestCase):
    TABLES = {
        "IRONSWORD": _dbx({"class": "Model", "name": "IRONSWORD", "folder": "xwp/IRONSWORD", "model": "IRONSWORD"},
                          {"class": "Weapon", "model": "IRONSWORD", "kind": "0"}),
        "STEELAXE": _dbx({"class": "Model", "folder": "xwp/STEELAXE", "model": "STEELAXE"}),
        "FIRE": _dbx({"class": "Weapon", "name": "FIRE", "effectId": "EID_K_FIRE"}),
        "GONE": _dbx({"class": "Model", "folder": "xwp/GONE", "model": "GONE"}),
    }

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.files = Path(self._tmp.name)
        for relative in ("xwp/ironsword/ironsword.cmp", "xwp/forge/ironsword_b.cmp", "xwp/SteelAxe/steelaxe.cmp"):
            (self.files / relative).parent.mkdir(parents=True, exist_ok=True)
            (self.files / relative).write_bytes(b"")

    def tearDown(self):
        self._tmp.cleanup()

    def test_dbx_blocks(self):
        blocks = icons.dbx_blocks(self.TABLES["IRONSWORD"])
        self.assertEqual([b["class"] for b in blocks], ["Model", "Weapon"])
        self.assertEqual(blocks[0]["folder"], "xwp/IRONSWORD")

    def test_model_named_by_the_items_table(self):
        found = icons.weapon_model(self.files, "IID_IRONSWORD", self.TABLES)
        self.assertEqual((found.name, found.folder, found.model), ("IRONSWORD", "xwp/IRONSWORD", "IRONSWORD"))
        self.assertEqual(found.path, self.files / "xwp/ironsword/ironsword.cmp")  # disc paths ignore case
        self.assertEqual(found.label, "xwp/ironsword")
        self.assertEqual(icons.forged_model_path(self.files, "IID_IRONSWORD"),
                         self.files / "xwp/forge/ironsword_b.cmp")

    def test_table_folder_can_differ_from_the_item(self):
        tables = {"MYSWORD": self.TABLES["STEELAXE"]}
        self.assertEqual(icons.weapon_model(self.files, "IID_MYSWORD", tables).path,
                         self.files / "xwp/SteelAxe/steelaxe.cmp")

    def test_no_table_no_model_or_missing_file(self):
        self.assertFalse(icons.weapon_model(self.files, "IID_VULNERARY", self.TABLES).has_table)
        fire = icons.weapon_model(self.files, "IID_FIRE", self.TABLES)
        self.assertTrue(fire.has_table)
        self.assertIsNone(fire.folder)
        gone = icons.weapon_model(self.files, "IID_GONE", self.TABLES)
        self.assertEqual(gone.folder, "xwp/GONE")
        self.assertIsNone(gone.path)
        self.assertIsNone(icons.weapon_model(self.files, None, self.TABLES))
        self.assertIsNone(icons.forged_model_path(self.files, "IID_STEELAXE"))

    def test_weapon_tables_from_zdbx_entries(self):
        entries = [SimpleNamespace(name="xwp/IRONSWORD.dbx", text="a"), SimpleNamespace(name="zu/fig1.dbx", text="b"),
                   SimpleNamespace(name="xwp/ironbow.dbx", text="c")]
        self.assertEqual(icons.weapon_tables(entries), {"IRONSWORD": "a", "IRONBOW": "c"})

    def test_model_viewer_lists_weapons_and_forged_weapons(self):
        extracted = self.files / "extracted"
        (extracted / "files").mkdir(parents=True)
        (self.files / "xwp").rename(extracted / "files" / "xwp")
        labels = [label for label, _path in model_viewer._iter_model_sets(SimpleNamespace(extracted_dir=extracted))]
        self.assertEqual(sorted(labels), ["xwp/SteelAxe", "xwp/forge/ironsword_b", "xwp/ironsword"])


if __name__ == "__main__":
    unittest.main()
