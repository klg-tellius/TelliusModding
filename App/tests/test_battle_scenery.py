import os
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fe_modding.formats import battle_scenery as bs
from fe_modding.formats import dbx, zdbx

PARAM = "#\r\n# Terrain\r\n#\r\n\r\n{\r\n\tclass\tParam\r\n\tname\tmap01_woods\r\n\troomFlag\t0\r\n\tfootEffect\t1\r\n\tfootSound\t0\r\n}\r\n\\\r\n"
BG_LIST = "{\r\n\tclass\t\tTerrainList\r\n\tWoods\t\tmap01_woods\r\n\tRoom\t\tbegnion_room\r\n}\r\n"


class SceneryTests(unittest.TestCase):
    def test_read_and_set(self):
        self.assertEqual(bs.read_scenery(PARAM), bs.SceneryParam("map01_woods", 0, 1, 0))
        text = bs.set_scenery_field(PARAM, "footSound", 4)
        self.assertEqual(bs.read_scenery(text).foot_sound, 4)
        self.assertEqual(text.replace("footSound\t4", "footSound\t0"), PARAM)

    def test_set_adds_missing_field(self):
        text = bs.set_scenery_field(PARAM.replace("\tfootSound\t0\r\n", ""), "footSound", "2")
        self.assertEqual(bs.read_scenery(text).foot_sound, 2)

    def test_rejects_bad_values(self):
        for field, value in (("footSound", "9"), ("roomFlag", "x"), ("bogus", "1")):
            with self.assertRaises(bs.SceneryError):
                bs.set_scenery_field(PARAM, field, value)
        with self.assertRaises(bs.SceneryError):
            bs.read_scenery("{\r\n}\r\n")

    def test_clone(self):
        text = bs.clone_scenery(PARAM, "map99_new")
        self.assertEqual(bs.read_scenery(text), bs.SceneryParam("map99_new", 0, 1, 0))
        with self.assertRaises(bs.SceneryError):
            bs.clone_scenery(PARAM, "bad name")

    def test_terrain_labels(self):
        self.assertEqual(bs.terrain_labels(BG_LIST), {"map01_woods": "Woods", "begnion_room": "Room"})
        self.assertEqual(bs.terrain_labels(""), {})

    @unittest.skipUnless(os.environ.get("FE9_ZDBX"), "set FE9_ZDBX to a zdbx.cmp to run the corpus test")
    def test_corpus(self):
        files = zdbx.read_zdbx_files(Path(os.environ["FE9_ZDBX"]).read_bytes())
        seen = 0
        for name, raw in files:
            if name.startswith("zbg/") and name.endswith("/param.dbx"):
                text = raw.decode("shift_jis")
                self.assertEqual(dbx.parse(text).text, text)
                param = bs.read_scenery(text)
                self.assertIn(param.foot_effect, bs.FOOT_EFFECTS)
                self.assertIn(param.foot_sound, bs.FOOT_SOUNDS)
                self.assertIn(param.room_flag, bs.ROOM_FLAGS)
                seen += 1
        self.assertEqual(seen, 117)


if __name__ == "__main__":
    unittest.main()
