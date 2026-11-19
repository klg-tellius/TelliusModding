import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fe_modding import map_props
from fe_modding.formats.map_file import MapObject


class PakNameTests(unittest.TestCase):
    def test_every_map_object_flag_bit_has_one_named_control(self):
        groups = map_props.PROP_FLAG_GROUPS
        self.assertEqual([g[0] for g in groups], ["flag_bits_a", "flag_bits_b", "flag_bits_c", "effect_type"])
        for _field, _title, controls in groups:
            self.assertEqual([mask for mask, _label in controls], [1 << bit for bit in range(8)])
            self.assertTrue(all(label and "bit " not in label.lower() for _mask, label in controls))
            self.assertTrue(all("unknown" not in label.lower() for _mask, label in controls))

    def test_radiant_dawn_groups_by_game_name_or_enum(self):
        from fe_modding.games import Game
        self.assertIs(map_props.prop_flag_groups("fe10"), map_props.RD_PROP_FLAG_GROUPS)
        self.assertIs(map_props.prop_flag_groups(Game.RADIANT_DAWN), map_props.RD_PROP_FLAG_GROUPS)
        self.assertIs(map_props.prop_flag_groups(Game.PATH_OF_RADIANCE), map_props.PROP_FLAG_GROUPS)
        self.assertIs(map_props.prop_flag_groups(), map_props.PROP_FLAG_GROUPS)

    def test_radiant_dawn_toggle_merge_preserves_unexposed_bits(self):
        obj = MapObject(0, 0, 0, 0, 0, 0, 0x82, 0x38, 0x81, 0x45, "test")
        values = map_props.merge_prop_flag_toggles(obj, (
            ("flag_bits_a", 0x01, True),
            ("flag_bits_a", 0x40, False),
            ("flag_bits_b", 0x04, True),
            ("flag_bits_c", 0x02, False),
            ("effect_type", 0x20, True),
        ))
        self.assertEqual(values, {
            "flag_bits_a": 0x83,
            "flag_bits_b": 0x3C,
            "flag_bits_c": 0x81,
            "effect_type": 0x65,
        })

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


class FlagGroupTests(unittest.TestCase):
    def test_radiant_dawn_maps_get_their_own_map_role_labels(self):
        from types import SimpleNamespace
        rd = SimpleNamespace(layout=SimpleNamespace(game="fe10"))
        por = SimpleNamespace(layout=SimpleNamespace(game="fe9"))
        self.assertIs(map_props.prop_flag_groups(por), map_props.PROP_FLAG_GROUPS)
        groups = map_props.prop_flag_groups(rd)
        self.assertEqual(dict(groups[0][2])[0x40], "Start hidden (Radiant Dawn)")
        # seen in game (MAP-04 sweep): A4 hides an object on RD; B0 and effect bit 0x10 carry RD notes
        self.assertIn("Hide this object", dict(groups[0][2])[0x10])
        self.assertIn("no visible change", dict(groups[1][2])[0x01])
        self.assertIn("unlit", dict(groups[3][2])[0x10])
        for rd_group, por_group in zip(groups, map_props.PROP_FLAG_GROUPS):     # same bytes, same masks
            self.assertEqual(rd_group[0], por_group[0])
            self.assertEqual([m for m, _l in rd_group[2]], [m for m, _l in por_group[2]])
        self.assertEqual(groups[2], map_props.PROP_FLAG_GROUPS[2])


@unittest.skipUnless(os.environ.get("FE10_EXTRACTED_FILES"), "set FE10_EXTRACTED_FILES to an extracted files/ directory")
class MissingAnimationTests(unittest.TestCase):
    """A prop told to load its .ga without one in the pack hangs the opening event (MAP-04 sweep): Check warns."""

    def test_flagged_stall_without_ga_is_reported_and_retail_is_clean(self):
        from fe_modding.formats import map_file
        path = os.path.join(os.environ["FE10_EXTRACTED_FILES"], "zmap", "bmap0101", "map.cmp")
        files = map_props.map_pack_files(path)
        self.assertEqual(map_props.objects_missing_animation(files), [])
        data = map_file.read_map_bytes(files["map.bin"])
        stall = next(o for o in data.build_desc if (o.filename or "").startswith("mrkt"))
        files["map.bin"] = map_file.patch_object_field(files["map.bin"], stall, "flag_bits_c",
                                                       stall.flag_bits_c | map_props.FLAG_C_LOAD_ANIMATION)
        self.assertEqual(map_props.objects_missing_animation(files), [stall.filename])


if __name__ == "__main__":
    unittest.main()
