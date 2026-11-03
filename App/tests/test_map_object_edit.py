import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fe_modding import map_props


class PakNameTests(unittest.TestCase):
    def test_every_map_object_flag_bit_has_one_named_control(self):
        groups = map_props.PROP_FLAG_GROUPS
        self.assertEqual([g[0] for g in groups], ["flag_bits_a", "flag_bits_b", "flag_bits_c", "effect_type"])
        for _field, _title, controls in groups:
            self.assertEqual([mask for mask, _label in controls], [1 << bit for bit in range(8)])
            self.assertTrue(all(label and "bit " not in label.lower() for _mask, label in controls))
            self.assertTrue(all("unknown" not in label.lower() for _mask, label in controls))

    def test_rd_controls_expose_every_retail_active_traced_bit(self):
        groups = map_props.prop_flag_groups("fe10")
        self.assertEqual(
            {field: {mask for mask, _label in controls} for field, _title, controls in groups},
            {"flag_bits_a": {0x01, 0x08, 0x10, 0x20, 0x40},
             "flag_bits_b": {0x01, 0x02, 0x04, 0x40, 0x80},
             "flag_bits_c": {0x02, 0x04, 0x08, 0x10, 0x20, 0x40},
             "effect_type": {0x02, 0x10, 0x20, 0x80}},
        )
        self.assertIs(map_props.prop_flag_groups("fe9"), map_props.PROP_FLAG_GROUPS)

    def test_rd_toggle_merge_preserves_every_unexposed_bit(self):
        from fe_modding.formats import map_file
        obj = map_file.MapObject(0, 0, 0, 1, 1, 1, 0xA5, 0xDA, 0xE3, 0xA1,
                                 "door", layout="fe10")
        values = map_props.merge_prop_flag_toggles(
            obj, (("flag_bits_a", 0x01, False), ("flag_bits_a", 0x08, True),
                  ("flag_bits_b", 0x01, True), ("flag_bits_b", 0x40, True),
                  ("flag_bits_b", 0x80, False), ("flag_bits_c", 0x02, False),
                  ("flag_bits_c", 0x10, True), ("flag_bits_c", 0x20, False),
                  ("effect_type", 0x02, True), ("effect_type", 0x10, False),
                  ("effect_type", 0x20, False), ("effect_type", 0x80, True)))
        self.assertEqual(values, {"flag_bits_a": 0xAC, "flag_bits_b": 0x5B,
                                  "flag_bits_c": 0xD1, "effect_type": 0x83})
        self.assertEqual((obj.flag_bits_a, obj.flag_bits_b, obj.flag_bits_c,
                          obj.effect_type), (0xA5, 0xDA, 0xE3, 0xA1))

    def test_full_width_name_round_trips(self):
        from fe_modding.formats import pak
        files = [("ｆlowerpot_01.g", b"abc"), ("map.bin", b"x")]
        data = pak.pack_pak(files, [0, 0])
        self.assertIn(b"\x82\x86lowerpot_01.g\x00", data)
        entries = pak.read_pak_entries(data)
        self.assertEqual([(e.name, pak.read_pak_file_content(data, e)) for e in entries], files)


@unittest.skipUnless(os.environ.get("FE9_EXTRACTED_FILES"), "set FE9_EXTRACTED_FILES to an extracted files/ directory")
class MapObjectEditTests(unittest.TestCase):
    def setUp(self):
        from fe_modding.games import Game
        from fe_modding.project import ModProject
        source = Path(os.environ["FE9_EXTRACTED_FILES"])
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.project = ModProject.create(Path(tmp.name), "props", Game.PATH_OF_RADIANCE)
        zmap = self.project.extracted_dir / "files" / "zmap"
        zmap.mkdir(parents=True)
        for folder in ("bmap02", "bmap04"):
            shutil.copytree(source / "zmap" / folder, zmap / folder)
        self.path = zmap / "bmap02" / "map.cmp"

    def test_edit_one_map_and_the_same_prop_elsewhere(self):
        prop = next(p for p in map_props.map_props_info(self.path) if p.name == "wave_99")
        others = map_props.maps_with_same_prop(self.project.extracted_dir, self.path, prop.name)
        self.assertEqual([o.parent.name for o in others], ["bmap04"])
        changes = {"size_y": prop.obj.size_y + 1, "flag_bits_b": prop.obj.flag_bits_b | 2}
        for path in [self.path, *others]:
            self.assertTrue(map_props.edit_prop(self.project, path, prop.name, changes))
            edited = next(p for p in map_props.map_props_info(path) if p.name == prop.name)
            self.assertEqual(edited.obj.flag_bits_b, changes["flag_bits_b"])
        self.assertFalse(map_props.edit_prop(self.project, self.path, prop.name, changes))

    def test_refusals(self):
        with self.assertRaises(ValueError):
            map_props.edit_prop(self.project, self.path, "wave_99", {"filename": "x"})
        with self.assertRaises(ValueError):
            map_props.edit_prop(self.project, self.path, "wave_99", {"flag_bits_a": 300})
        with self.assertRaises(ValueError):
            map_props.edit_prop(self.project, self.path, "no_such_prop", {"size_y": 1.0})


if __name__ == "__main__":
    unittest.main()
