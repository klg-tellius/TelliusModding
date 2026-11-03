import os
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fe_modding.formats import battle_params as bp
from fe_modding.formats import dbx, zdbx

PARAM = (
    "#\r\n# unit\r\n#\r\n\r\n{\r\n\tclass\tParam\r\n\tname\tfig1\r\n\ttexnum\t1\r\n\t自軍\tfig1\r\n"
    "\t移動速度\t0.8\r\n\t間合い\t10.0\r\n\tジャンプ攻撃２\t1\r\n}\r\n\\\r\n"
)


class ParamTests(unittest.TestCase):
    def test_read(self):
        p = bp.read_params(PARAM)
        self.assertEqual(p.name, "fig1")
        self.assertEqual(p.values, {"移動速度": "0.8", "間合い": "10.0", "ジャンプ攻撃２": "1"})

    def test_set_add_remove(self):
        text = bp.set_param(PARAM, "移動速度", "0.4")
        self.assertEqual(bp.read_params(text).get("移動速度"), "0.4")
        text = bp.set_param(text, "大型", "1")
        self.assertEqual(bp.read_params(text).get("大型"), "1")
        text = bp.set_param(text, "ジャンプ攻撃２", "0")
        self.assertNotIn("ジャンプ攻撃２", bp.read_params(text).values)
        text = bp.set_param(text, "補間速度", "20")
        self.assertEqual(bp.read_params(text).get("補間速度"), "20")
        self.assertEqual(bp.set_param(PARAM, "移動速度", "0.8"), PARAM)  # no-op keeps the text
        self.assertEqual(bp.set_param(PARAM, "走り回数", ""), PARAM)  # removing an absent key too
        self.assertIn("\t自軍\tfig1\r\n", text)  # textures untouched

    def test_rejects(self):
        for key, value in (("移動速度", ""), ("移動速度", "fast"), ("走り回数", "1.5"), ("大型", "2"),
                           ("間合い", "-1"), ("bogus", "1")):
            with self.assertRaises(bp.ParamError):
                bp.set_param(PARAM, key, value)

    @unittest.skipUnless(os.environ.get("FE9_ZDBX"), "set FE9_ZDBX to a zdbx.cmp to run the corpus test")
    def test_corpus(self):
        seen = 0
        for name, raw in zdbx.read_zdbx_files(Path(os.environ["FE9_ZDBX"]).read_bytes()):
            if name.startswith("zu/") and name.endswith("_prm.dbx"):
                text = raw.decode("shift_jis")
                params = bp.read_params(text)
                for key, value in params.values.items():
                    self.assertEqual(bp.set_param(text, key, value), text)  # valid and a no-op
                seen += 1
        self.assertEqual(seen, 92)


if __name__ == "__main__":
    unittest.main()
