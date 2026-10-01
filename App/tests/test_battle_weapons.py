import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fe_modding import battle_tables
from fe_modding.exceptions import ProjectError
from fe_modding.formats import battle_weapons as bw
from fe_modding.formats import dbx, zdbx
from fe_modding.games import Game
from fe_modding.project import ModProject

SWORD = (
    "#\r\n# Sword\r\n#\r\n\r\n{\r\n\tclass\tModel\r\n\tname\tALONDITE\r\n\tfolder\txwp/ALONDITE\r\n"
    "\tmodel\tALONDITE\r\n}\r\n\r\n{\r\n\tclass\tWeapon\r\n\tname\tALONDITE\r\n\tmodel\tALONDITE\r\n"
    "\tshow\t\t1\r\n\tkind\t0\r\n\tmissile\t0\r\n\teffectId\tEID_REPPU2\r\n}\r\n\\r\n"
)


class DbxTests(unittest.TestCase):
    def test_round_trip_and_noop_set(self):
        doc = dbx.parse(SWORD)
        self.assertEqual(doc.text, SWORD)
        for block in doc.blocks():
            for f in block.fields:
                doc.set_value(f, f.value)
        self.assertEqual(doc.text, SWORD)

    def test_set_value_keeps_spacing_and_comment(self):
        doc = dbx.parse("{\r\n\tclass\tX\r\n\tdist\t60.0   # far\r\n}\r\n")
        doc.set_value(doc.find("X").fields[1], "50.0")
        self.assertEqual(doc.text, "{\r\n\tclass\tX\r\n\tdist\t50.0   # far\r\n}\r\n")

    def test_repeated_keys_and_missing_block(self):
        doc = dbx.parse("{\n class A\n time 1\n time 2\n}\n")
        self.assertEqual(doc.find("A").get_all("time"), ["1", "2"])
        with self.assertRaises(dbx.DbxError):
            doc.find("B")


class WeaponTests(unittest.TestCase):
    def test_read(self):
        w = bw.read_weapon(SWORD)
        self.assertEqual((w.name, w.model_folder, w.kind, w.missile, w.effect_id), ("ALONDITE", "xwp/ALONDITE", 0, 0, "EID_REPPU2"))

    def test_set_add_remove(self):
        text = bw.set_weapon_field(SWORD, "kind", "1")
        self.assertEqual(bw.read_weapon(text).kind, 1)
        text = bw.set_weapon_field(text, "damageEffId", "EID_K_FIRE2_WP")
        self.assertEqual(bw.read_weapon(text).damage_effect_id, "EID_K_FIRE2_WP")
        text = bw.set_weapon_field(text, "effectId", "")
        self.assertIsNone(bw.read_weapon(text).effect_id)
        self.assertIn("\r\n", text)
        self.assertNotIn("\n\n", text.replace("\r\n", ""))

    def test_rejects_bad_input(self):
        with self.assertRaises(bw.WeaponError):
            bw.set_weapon_field(SWORD, "kind", "x")
        with self.assertRaises(bw.WeaponError):
            bw.set_weapon_field(SWORD, "effectId", "FIRE")
        with self.assertRaises(bw.WeaponError):
            bw.set_weapon_field(SWORD, "bogus", "1")
        with self.assertRaises(bw.WeaponError):
            bw.new_weapon_dbx("bad name", kind=0, missile=0)

    def test_new_weapon(self):
        text = bw.new_weapon_dbx("DEVILAXE", kind=2, missile=0, model="DEVILAXE", effect_id="EID_K_FIRE2")
        w = bw.read_weapon(text)
        self.assertEqual((w.name, w.model_folder, w.kind, w.effect_id), ("DEVILAXE", "xwp/DEVILAXE", 2, "EID_K_FIRE2"))
        tome = bw.read_weapon(bw.new_weapon_dbx("FIRE", kind=4, missile=1))
        self.assertIsNone(tome.model_folder)

    @unittest.skipUnless(os.environ.get("FE9_ZDBX"), "set FE9_ZDBX to a zdbx.cmp to run the corpus test")
    def test_corpus(self):
        files = zdbx.read_zdbx_files(Path(os.environ["FE9_ZDBX"]).read_bytes())
        seen = 0
        for name, raw in files:
            if name.startswith("xwp/") and name.endswith(".dbx"):
                text = raw.decode("shift_jis")
                self.assertEqual(dbx.parse(text).text, text)
                bw.read_weapon(text)
                seen += 1
        self.assertEqual(seen, 91)


class BattleTablesProjectTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.project = ModProject.create(Path(tmp.name), "Tables", Game.PATH_OF_RADIANCE)
        files = self.project.extracted_dir / "files"
        files.mkdir(parents=True, exist_ok=True)
        entries = [("xwp/ALONDITE.dbx", zdbx.encode_dbx(SWORD)), ("zdbx/skill.dbx", b"{}")]
        (files / "zdbx.cmp").write_bytes(zdbx.build_zdbx_archive(entries))

    def test_edit_restore_add_remove(self):
        name = "xwp/ALONDITE.dbx"
        self.assertEqual(battle_tables.entry_names(self.project, "xwp"), [name])
        self.assertFalse(battle_tables.is_modified(self.project, name))
        battle_tables.write_entry(self.project, name, bw.set_weapon_field(SWORD, "kind", "2"))
        self.assertTrue(battle_tables.is_modified(self.project, name))
        self.assertEqual(bw.read_weapon(battle_tables.read_entry(self.project, name)).kind, 2)
        self.assertTrue((self.project.originals_dir / "files" / "zdbx.cmp").exists())
        battle_tables.restore_entry(self.project, name)
        self.assertEqual(battle_tables.read_entry(self.project, name), SWORD)

        new = "xwp/DEVILAXE.dbx"
        with self.assertRaises(ProjectError):
            battle_tables.write_entry(self.project, new, "x")
        battle_tables.write_entry(self.project, new, bw.new_weapon_dbx("DEVILAXE", kind=2, missile=0), create=True)
        self.assertEqual(len(battle_tables.entry_names(self.project, "xwp")), 2)
        battle_tables.restore_entry(self.project, new)  # vanilla has none: removed
        self.assertEqual(battle_tables.entry_names(self.project, "xwp"), [name])

    def test_unencodable_text(self):
        with self.assertRaises(ProjectError):
            battle_tables.write_entry(self.project, "xwp/ALONDITE.dbx", chr(0x1F600))


if __name__ == "__main__":
    unittest.main()
