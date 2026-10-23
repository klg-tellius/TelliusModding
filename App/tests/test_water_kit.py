"""Water outline, shoreline fade, shore waves and flow (water_kit)."""

import io
import math
import os
import sys
import unittest
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fe_modding import water_kit as wk


def grid(size: float, cell: float = 5.0, height=lambda x, z: 0.0) -> np.ndarray:
    """A terrain of ``size`` x ``size`` units, two up-facing triangles per cell."""
    tris = []
    steps = int(size / cell)
    for i in range(steps):
        for j in range(steps):
            x0, z0, x1, z1 = i * cell, j * cell, (i + 1) * cell, (j + 1) * cell
            a, b, c, d = ((x, height(x, z), z) for x, z in ((x0, z0), (x1, z0), (x1, z1), (x0, z1)))
            tris += [(a, c, b), (a, d, c)]
    return np.array(tris, float)


def square(x0, z0, x1, z1, y=0.0) -> np.ndarray:
    a, b, c, d = (x0, y, z0), (x1, y, z0), (x1, y, z1), (x0, y, z1)
    return np.array([(a, d, c), (a, c, b)], float)


def bowl(cx=100.0, cz=100.0):
    """Ground rising from -10 at (cx, cz), 0.1 unit per unit away: at level 0
    the waterline is a circle of radius 100... clipped to 200 units."""
    return grid(200, 2.5, lambda x, z: -10.0 + 0.1 * math.hypot(x - cx, z - cz))


class Coverage(unittest.TestCase):
    def test_points_and_tiles(self):
        tris = square(10, 10, 20, 30)
        self.assertEqual(wk.covered(tris, [15, 25, 10], [20, 20, 10]).tolist(), [True, False, True])
        tiles = wk.covered_tiles(tris, 6, 8)
        self.assertEqual(int(tiles.sum()), 2 * 4)
        self.assertTrue(tiles[2, 2] and tiles[3, 5] and not tiles[4, 2])
        shifted = wk.covered_tiles(tris, 6, 8, origin=(-1, -1))
        # tile c now starts at mesh 5 * (c + 1): the square covers tiles 1-2 x 1-4
        self.assertTrue(shifted[1, 1] and shifted[2, 4] and not shifted[3, 1])

    def test_grid_matches_points(self):
        tris = np.concatenate([square(0, 0, 40, 20), square(50, 50, 70, 90)])
        cover = wk.cover_grid(tris, 128, 160)
        axis = (np.arange(128) + 0.5) * 160 / 128
        x, z = np.meshgrid(axis, axis)
        self.assertTrue((cover == wk.covered(tris, x, z)).all())


class Outline(unittest.TestCase):
    def test_square_outline(self):
        edges = wk.outline_edges(square(0, 0, 10, 10))
        self.assertAlmostEqual(np.linalg.norm(edges[:, 1] - edges[:, 0], axis=1).sum(), 40.0)

    def test_t_junctions_and_overlaps_drop_out(self):
        # one wide rectangle over two narrow ones, plus a copy overlapping the first
        tris = np.concatenate([square(0, 0, 10, 5), square(0, 5, 4, 10), square(4, 5, 10, 10), square(2, 1, 6, 4)])
        edges = wk.outline_edges(tris)
        self.assertAlmostEqual(np.linalg.norm(edges[:, 1] - edges[:, 0], axis=1).sum(), 40.0)

    def test_edge_distance(self):
        dist = wk.edge_distance_grid(wk.outline_edges(square(0, 0, 64, 64)), 64, 64, 10.0)
        self.assertAlmostEqual(dist[32, 32], 10.0)
        self.assertAlmostEqual(dist[32, 2], 2.5)


class Shoreline(unittest.TestCase):
    def test_flat_up_facing_surface_past_the_waterline(self):
        water = wk.shoreline(bowl(), 0.0, margin=5.0)
        self.assertTrue(np.allclose(water[..., 1], 0.0))
        normal_y = np.cross(water[:, 1] - water[:, 0], water[:, 2] - water[:, 0])[:, 1]
        self.assertTrue((normal_y > 0).all())
        # the ground meets level 0 at radius 100 from the centre (clipped to the
        # 200-unit terrain); the surface reaches 5 units past it, not further
        x = np.array([100.0, 100.0, 100.0, 100.0])
        z = np.array([100.0, 196.0, 2.0, 100.0])
        self.assertEqual(wk.covered(water, x, z).tolist(), [True, True, True, True])
        ring = wk.shoreline(grid(200, 2.5, lambda x, z: -5.0 + 0.1 * math.hypot(x - 100, z - 100)), 0.0, margin=5.0)
        self.assertTrue(wk.covered(ring, [100 + 50 + 3.5], [100]).all())
        self.assertFalse(wk.covered(ring, [100 + 50 + 7.5], [100]).any())

    def test_seeds_keep_one_basin(self):
        def two_pits(x, z):
            return min(math.hypot(x - 40, z - 40), math.hypot(x - 160, z - 160)) * 0.2 - 4.0
        ground = grid(200, 2.5, two_pits)
        both = wk.shoreline(ground, 0.0, margin=0.0)
        one = wk.shoreline(ground, 0.0, margin=0.0, seeds=[(40, 40)])
        self.assertTrue(wk.covered(both, [40, 160], [40, 160]).all())
        self.assertEqual(wk.covered(one, [40, 160], [40, 160]).tolist(), [True, False])

    def test_fill_empty_reaches_past_the_ground(self):
        ground = grid(50, 2.5, lambda x, z: -1.0)
        open_sea = wk.shoreline(ground, 0.0, margin=0.0, bounds=(0, 0, 100, 100), fill_empty=True)
        self.assertTrue(wk.covered(open_sea, [90], [90]).all())
        lake = wk.shoreline(ground, 0.0, margin=5.0, bounds=(0, 0, 100, 100))
        self.assertFalse(wk.covered(lake, [90], [90]).any())


class Fade(unittest.TestCase):
    def test_land_edge_and_depth(self):
        ground = grid(640, 5.0, lambda x, z: -0.05 * math.hypot(x - 320, z - 320))  # deeper toward the centre... of a hill
        water = square(200, 200, 440, 440, y=-4.0)
        fade = wk.shore_fade(water, ground)
        px = lambda x, z: fade[int(z * 0.8), int(x * 0.8)]
        self.assertAlmostEqual(px(100, 100), wk.FADE_LAND)
        # ground at the centre is 0 (above the water): faded out like a bank
        self.assertGreater(px(320, 320), 0.6)
        # ground 7.1 units under the surface near the corner: clear water
        self.assertLess(px(212, 212), 0.21)
        self.assertTrue((fade >= 0).all() and (fade <= wk.FADE_LAND).all())

    def test_open_sea_past_the_terrain(self):
        # ground (a beach rising out of the sea) only from x = 100; the sea runs to x = 0
        ground = grid(640, 5.0, lambda x, z: (x - 300) * 0.05)
        ground = ground[ground[:, :, 0].min(axis=1) >= 100]
        sea = square(0, 0, 350, 640, y=0.0)
        fade = wk.shore_fade(sea, ground)
        self.assertAlmostEqual(fade[320, 4], 0.0)  # the sea's edge at the map border: open water
        self.assertGreater(fade[320, int(298 * 0.8)], 0.5)  # the waterline at x = 300: faded
        centres = [(s.column + 0.5) * 5 for s in wk.wave_slots(fade)]
        self.assertGreater(centres.count(277.5), 100)  # one file along the waterline
        self.assertFalse([x for x in centres if x < 100])  # none along the border past the terrain

    def test_edge_taper_without_ground(self):
        fade = wk.shore_fade(square(100, 100, 300, 300))
        self.assertAlmostEqual(fade[160, 160], 0.0)  # 100 units inside
        self.assertGreater(fade[81, 160], 0.4)  # half a pixel inside the edge
        self.assertAlmostEqual(fade[10, 10], wk.FADE_LAND)


class Waves(unittest.TestCase):
    def test_angle_matches_vanilla_placement(self):
        # vanilla wave_99 instances: angle byte -> where local +z points
        for angle, direction in ((0, (0, 1)), (192, (1, 0)), (128, (0, -1)), (32, (-0.7071, 0.7071))):
            self.assertTrue(np.allclose(wk.wave_direction(angle), direction, atol=1e-3))
            self.assertEqual(wk.wave_angle(*direction), angle)

    def test_height_matches_vanilla(self):
        # bmap02: water at 2.0, wave origin at y 2.0 (height -0.4), strip 1 unit above
        self.assertAlmostEqual(wk.wave_height(2.0, lift=1.0), -0.4)

    def test_one_file_of_waves_facing_the_shore(self):
        lake = wk.shore_fade(square(200, 200, 440, 440))
        slots = wk.wave_slots(lake)
        self.assertTrue(slots)
        for s in slots:
            cx, cz = (s.column + 0.5) * 5, (s.row + 0.5) * 5
            self.assertTrue(200 <= cx <= 440 and 200 <= cz <= 440)
            # near the edge, facing up the fade toward the bank
            self.assertLess(min(cx - 200, 440 - cx, cz - 200, 440 - cz), 10)
            ahead = lake[int((cz + 4 * s.direction[1]) * 0.8), int((cx + 4 * s.direction[0]) * 0.8)]
            self.assertGreater(ahead, lake[int(cz * 0.8), int(cx * 0.8)])
        tiles = {(s.column, s.row) for s in slots}
        self.assertLess(np.mean([sum((c + dx, r + dz) in tiles for dx in (-1, 0, 1) for dz in (-1, 0, 1)) - 1
                                 for c, r in tiles]), 3.0)

    def test_keep_thins_deterministically(self):
        lake = wk.shore_fade(square(200, 200, 440, 440))
        a = wk.wave_slots(lake, keep=0.4, seed=3)
        b = wk.wave_slots(lake, keep=0.4, seed=3)
        self.assertEqual([(s.column, s.row) for s in a], [(s.column, s.row) for s in b])
        self.assertLess(len(a), len(wk.wave_slots(lake)))


class Flow(unittest.TestCase):
    def test_round_trip(self):
        scroll = (-0.124, 0.36, -0.231, -0.572)
        layer1, layer2 = wk.flow_from_scroll(scroll)
        self.assertEqual(layer1, (0.124, -0.36))
        self.assertEqual(wk.scroll_from_flow(layer1, layer2), scroll)
        degrees, speed = wk.polar((0.0, 1.0))
        self.assertAlmostEqual(degrees, 90.0)
        self.assertTrue(np.allclose(wk.from_polar(degrees, speed), (0.0, 1.0)))


@unittest.skipUnless(os.environ.get("FE9_EXTRACTED_FILES"), "set FE9_EXTRACTED_FILES to an extracted files/ directory")
class Vanilla(unittest.TestCase):
    """Generated fades and waves against the shipped maps."""

    def load(self, name):
        from fe_modding import map_heights, map_props
        from fe_modding.formats import gs_file, map_file, tpl

        _, files = map_props.read_map_container(Path(os.environ["FE9_EXTRACTED_FILES"]) / "zmap" / name / "map.cmp")
        data = map_file.read_map_bytes(files["map.bin"])
        names = map_props.water_names(files, data)
        terrain = next(o.filename for o in data.build_desc if map_file.is_base_terrain_object(o) and o.filename not in names)
        water = np.concatenate([map_props._water_triangles(files[f"{n}.gs"]) for n in names])
        ground = map_props._water_triangles(files[f"{terrain}.gs"])
        mat = next(m for m in gs_file.read_gs(files[f"{names[0]}.gs"]).materials if m.name == "map_water")
        image = tpl.read_tpl_images(io.BytesIO(files[map_props.texpack_name(files)]))[mat.textures[0].tex_id + 1]
        origin = map_heights.terrain_origin(data, terrain)
        waves = [(i.x - origin[0], i.y - origin[1], i.angle % 256) for i in data.build_inst
                 if data.build_desc[i.desc_index].filename == "wave_99"]
        return water, ground, np.asarray(image.convert("L"), float) / 255, waves

    def test_depth_fade_matches_vanilla(self):
        for name in ("bmap02", "bmap13", "bmap24"):
            water, ground, vanilla, _ = self.load(name)
            inside = wk.cover_grid(water, wk.FADE_SIZE, wk.FADE_SPAN)
            error = np.abs(wk.shore_fade(water, ground) - vanilla)[inside].mean()
            self.assertLess(error, 0.05, name)

    def test_map_view_shows_foam_and_water(self):
        from fe_modding import map_props
        from fe_modding.gui import map_scene
        from fe_modding.gui import model_viewer as mv

        _, files = map_props.read_map_container(Path(os.environ["FE9_EXTRACTED_FILES"]) / "zmap" / "bmap13" / "map.cmp")
        foam = map_scene._still_triangles(mv.load_named_model_set(files, "wave_99"))
        self.assertEqual({round(t.alpha, 3) for t in foam}, {1.0})
        water = mv.load_named_model_set(files, "bmap13_water0")
        self.assertEqual([layer.role for layer in water.triangles[0].texture_layers],
                         ["diffuse", "water_layer2", "water_fade"])
        self.assertAlmostEqual(water.triangles[0].alpha, mv.MAP_WATER_ALPHA)

    def test_waves_line_up_with_vanilla(self):
        for name in ("bmap02", "bmap13"):
            _, _, fade, waves = self.load(name)
            slots = {(s.column, s.row): s.angle for s in wk.wave_slots(fade)}
            hits = [(c, r, a) for c, r, a in waves if (c, r) in slots]
            self.assertGreater(len(hits) / len(waves), 0.7, name)
            errors = [min((slots[(c, r)] - a) % 256, (a - slots[(c, r)]) % 256) * 360 / 256 for c, r, a in hits]
            self.assertLess(np.median(errors), 15, name)


if __name__ == "__main__":
    unittest.main()
