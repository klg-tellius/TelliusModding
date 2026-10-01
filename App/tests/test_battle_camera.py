import os
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fe_modding.formats import battle_camera as bc
from fe_modding.formats import dbx, zdbx

SCRIPT = (
    "#\r\n# Camera\r\n#\r\n\r\n{\r\n\tclass\tCameraAnime\r\n\tname\tstandby\r\n\tfolder\t\r\n\tcaption\tWait\r\n"
    "\tcamera\tcam1\r\n\tnum\t\t2\r\n\tpos\t\t0.00, 0.00, 0.00\r\n\trot\t\t8.00, 180.00, 0.00\r\n\tdist\t170.00\r\n"
    "\ttime\t0\r\n\tpos\t\t0.00, 1.00, 0.00\r\n\trot\t\t8.00, 180.00, 0.00\r\n\tdist\t100.00\r\n\ttime\t20\r\n}\r\n\r\n\\r\n"
)
RIGS = (
    "{\r\n\tclass\tCamera\r\n\tname\tcam1\r\n\tdest\t0.0, 0.0, 0.0, 0.0\r\n\tattract\t1\r\n\tdist\t60.0\r\n"
    "\trot\t\t-2.-2, 180.0, 0.0\r\n}\r\n\r\n# unit\r\n{\r\n\tclass\tCamera\r\n\tname\tcamCharaL0\r\n"
    "\tentityClass\tActor\r\n\tentityName\tcharaAtk\r\n\tentityName1\tcharaDef\r\n\toffs\t0.0, 7.0,0.0\r\n}\r\n"
)


class ScriptTests(unittest.TestCase):
    def test_read(self):
        s = bc.read_script(SCRIPT)
        self.assertEqual((s.name, s.camera, len(s.keyframes)), ("standby", "cam1", 2))
        self.assertEqual(s.keyframes[1], bc.Keyframe((0.0, 1.0, 0.0), (8.0, 180.0, 0.0), 100.0, 20))

    def test_replace_keyframes(self):
        frames = list(bc.read_script(SCRIPT).keyframes)
        frames.append(bc.Keyframe((1.0, 2.0, 3.0), (4.0, 5.0, 6.0), 70.5, 300))
        text = bc.set_script_keyframes(SCRIPT, frames)
        self.assertEqual(bc.read_script(text).keyframes[2], frames[2])
        self.assertIn("\tnum\t\t3\r\n", text)
        self.assertEqual(text.count("\r\n"), SCRIPT.count("\r\n") + 4)
        # same frames in -> same structure out
        again = bc.set_script_keyframes(SCRIPT, list(bc.read_script(SCRIPT).keyframes))
        self.assertEqual(bc.read_script(again), bc.read_script(SCRIPT))
        self.assertTrue(again.endswith("}\r\n\r\n\\r\n"))

    def test_fields_and_errors(self):
        text = bc.set_script_field(SCRIPT, "camera", "camCharaR0")
        self.assertEqual(bc.read_script(text).camera, "camCharaR0")
        with self.assertRaises(bc.CameraError):
            bc.set_script_field(SCRIPT, "camera", "bad name")
        with self.assertRaises(bc.CameraError):
            bc.set_script_keyframes(SCRIPT, [])
        with self.assertRaises(bc.CameraError):
            bc.set_script_keyframes(SCRIPT, [bc.Keyframe((0, 0, 0), (0, 0, 0), 1.0, -1)])
        with self.assertRaises(bc.CameraError):
            bc.read_script(SCRIPT.replace("num\t\t2", "num\t\t3"))

    def test_new_script(self):
        s = bc.read_script(bc.new_script("my_cam", "camCharaL0", "Mine"))
        self.assertEqual((s.name, s.caption, s.camera, len(s.keyframes)), ("my_cam", "Mine", "camCharaL0", 1))


class RigTests(unittest.TestCase):
    def test_read_keeps_typo(self):
        rigs = bc.read_rigs(RIGS)
        self.assertEqual([r.name for r in rigs], ["cam1", "camCharaL0"])
        self.assertEqual(rigs[0].get("rot"), "-2.-2, 180.0, 0.0")
        self.assertIsNone(bc.parse_vec(rigs[0].get("rot")))
        self.assertEqual(rigs[1].entity_class, "Actor")

    def test_set_field(self):
        text = bc.set_rig_field(RIGS, "cam1", "dist", "55")
        self.assertEqual(bc.read_rigs(text)[0].get("dist"), "55")
        self.assertIn("-2.-2, 180.0, 0.0", text)  # untouched
        text = bc.set_rig_field(text, "camCharaL0", "offs", "0, 8, 0")
        self.assertEqual(bc.read_rigs(text)[1].get("offs"), "0.00, 8.00, 0.00")
        text = bc.set_rig_field(text, "camCharaL0", "entityName1", "")
        self.assertEqual(bc.read_rigs(text)[1].get("entityName1"), "")
        text = bc.set_rig_field(text, "camCharaL0", "speed", "0.6")
        self.assertEqual(bc.read_rigs(text)[1].get("speed"), "0.6")

    def test_errors(self):
        for args in (("nope", "dist", "1"), ("cam1", "dist", "x"), ("cam1", "attract", "2"),
                     ("cam1", "pos", "1, 2"), ("cam1", "bogus", "1")):
            with self.assertRaises(bc.CameraError):
                bc.set_rig_field(RIGS, *args)

    @unittest.skipUnless(os.environ.get("FE9_ZDBX"), "set FE9_ZDBX to a zdbx.cmp to run the corpus test")
    def test_corpus(self):
        files = dict(zdbx.read_zdbx_files(Path(os.environ["FE9_ZDBX"]).read_bytes()))
        rigs = bc.read_rigs(files["zdbx/camera.dbx"].decode("shift_jis"))
        self.assertEqual([r.name for r in rigs], ["cam0", "cam1", "camCharaL0", "camCharaL1", "camCharaR0", "camCharaR1"])
        scripts = 0
        for name, raw in files.items():
            if name.startswith("xcam/") and name.endswith(".dbx"):
                text = raw.decode("shift_jis")
                self.assertEqual(dbx.parse(text).text, text)
                script = bc.read_script(text)
                # re-writing the frames must not change what the script says
                self.assertEqual(bc.read_script(bc.set_script_keyframes(text, list(script.keyframes))), script)
                scripts += 1
        self.assertEqual(scripts, 19)


if __name__ == "__main__":
    unittest.main()
