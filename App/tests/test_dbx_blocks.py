import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fe_modding import battle_dbx_notes
from fe_modding.formats import dbx

TEXT = "#x\r\n{\r\n\tclass\tPicture\r\n\tname\tA\r\n\tpos\t1,2\r\n}\r\n"


class DbxBlockTests(unittest.TestCase):
    def test_duplicate_renames_the_copy(self):
        doc = dbx.parse(TEXT)
        doc.duplicate_block(doc.blocks()[0], "B")
        self.assertEqual([b.name for b in doc.blocks()], ["A", "B"])
        self.assertEqual(doc.blocks()[1].get("pos"), "1,2")
        self.assertNotIn("\n\n\n", doc.text.replace("\r", ""))

    def test_remove_undoes_duplicate(self):
        doc = dbx.parse(TEXT)
        doc.duplicate_block(doc.blocks()[0], "B")
        doc.remove_block(doc.blocks()[1])
        self.assertEqual(doc.text, TEXT)

    def test_duplicate_without_name_field(self):
        doc = dbx.parse("{\n\tkey\tvalue\n}")
        doc.duplicate_block(doc.blocks()[0])
        self.assertEqual(len(doc.blocks()), 2)
        with self.assertRaises(dbx.DbxError):
            doc.duplicate_block(doc.blocks()[0], "named")

    def test_check_finds_structural_problems(self):
        self.assertEqual(dbx.check(TEXT + "\\\r\n"), [])  # retail files end with a lone backslash
        self.assertEqual(dbx.check("{\n\tclass\tA\n"), ["Line 1: this block is never closed."])
        self.assertEqual(dbx.check("}\n"), ["Line 1: } closes no block."])
        self.assertEqual(dbx.check("{\n{\n}\n"), ["Line 2: { opens a block inside the block opened on line 1."])
        self.assertEqual(dbx.check("\tname\tA\n"), ["Line 1: “name\tA” is outside every block."])

    def test_param_notes(self):
        self.assertIn("counter", battle_dbx_notes.note("zdbx/param.dbx", "WaitAtk2"))
        self.assertEqual(battle_dbx_notes.note("zdbx/battle.dbx", "pos"), battle_dbx_notes.WIDGET_NOTES["pos"])


if __name__ == "__main__":
    unittest.main()
