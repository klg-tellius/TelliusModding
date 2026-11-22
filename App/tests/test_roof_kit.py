import sys
import unittest
from pathlib import Path

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from test_map_heights import _map_bin
from test_map_props import _roof_corners, _roof_terrain, _terrain

from fe_modding import roof_kit
from fe_modding.formats import map_file, pak, tpl


def _spec(width=3, depth=2, **kw):
    return roof_kit.RoofSpec(width, depth, roof_kit.preset_image(roof_kit.ROOF_PRESET), **kw)


def _files(size=5):
    data = _map_bin(width=size, height=size, roof_elevations=[0])
    parsed = map_file.read_map_bytes(data)
    data = map_file.patch_extra_field(data, parsed.extra, "unknown_tail", map_file.MAP_EXTRA_FOOTPRINT_MASK)
    texpack = tpl.build_tpl([(Image.new("RGBA", (8, 8), (0, 255, 0, 255)), tpl.FORMAT_CMPR)])
    files = {"map.bin": data, "texpack.tpl": texpack, "tree.g": b"skeleton"}
    return [pak.PakEntry(name, 0, 0) for name in files], files


class RoofKitTests(unittest.TestCase):
    def test_presets_are_square_textures(self):
        for name in roof_kit.PRESETS:
            self.assertEqual(roof_kit.preset_image(name).size, (64, 64), name)

    def test_only_the_roof_is_built_on_top_of_the_walls(self):
        spec = _spec(4, 2)
        points = [p for tri, _uv in roof_kit.roof_triangles(spec) for p in tri]
        xs, ys, zs = zip(*points)
        self.assertEqual((min(xs), max(xs), min(zs), max(zs)), (0.0, 20.0, 0.0, 10.0))
        self.assertAlmostEqual(max(ys), spec.top)
        self.assertEqual(min(ys), spec.wall_height)  # no walls: nothing below the eaves
        flat = roof_kit.roof_triangles(_spec(4, 2, style="flat"))
        self.assertTrue(all(p[1] == spec.wall_height for tri, _uv in flat for p in tri))
        self.assertTrue(roof_kit.roof_glb(spec).startswith(b"glTF"))

    def test_check_spec_rejects_unusable_roofs(self):
        for spec in (_spec(1, 1), _spec(0, 5), _spec(style="dome"), _spec(wall_height=2, rise=1),
                     _spec(wall_height=-1, rise=8)):
            with self.assertRaises(map_file.MapFileError):
                roof_kit.check_spec(spec)
        roof_kit.check_spec(_spec(2, 2))

    def test_add_roof_places_a_working_roof_prop(self):
        entries, files = _files()
        name, index, warnings = roof_kit.add_roof(entries, files, 1, 1, _spec(3, 2))
        self.assertEqual(name, "roof")
        parsed = map_file.read_map_bytes(files["map.bin"])
        obj = next(o for o in parsed.build_desc if o.filename == "roof")
        self.assertTrue(map_file.is_roof_object(obj))
        self.assertEqual(map_file.roof_instances(parsed), [index])
        self.assertEqual(sorted(map_file.clipped_footprint(parsed, parsed.build_inst[index])),
                         [(x, y) for x in range(1, 4) for y in range(1, 3)])
        self.assertTrue(any("touches no door" in w for w in warnings))
        self.assertEqual(_roof_terrain(files, 2, 2), "屋根")
        self.assertEqual(_roof_corners(files, 2, 2), -3000)  # top of the roof: 5-unit walls + 2.5 rise
        self.assertEqual(_terrain(files, 2, 2), "plain")
        self.assertEqual(_roof_terrain(files, 0, 0), "plain")
        # a second roof gets its own name
        self.assertEqual(roof_kit.add_roof(entries, files, 0, 3, _spec(2, 2))[0], "roof_2")

    def test_add_roof_must_fit_the_map(self):
        entries, files = _files(size=4)
        with self.assertRaises(map_file.MapFileError):
            roof_kit.add_roof(entries, files, 2, 2, _spec(3, 2))


if __name__ == "__main__":
    unittest.main()
