"""Painted terrain layers -> the game's two-sample map_base blend."""

import io
import os
import sys
import unittest
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fe_modding import terrain_paint as tp


def grid(size: float, cell: float = 5.0, height=lambda x, z: 0.0) -> np.ndarray:
    """A terrain of ``size`` x ``size`` units, two triangles per cell, wound
    so the normals point up."""
    tris = []
    steps = int(size / cell)
    for i in range(steps):
        for j in range(steps):
            x0, z0, x1, z1 = i * cell, j * cell, (i + 1) * cell, (j + 1) * cell
            a, b, c, d = ((x, height(x, z), z) for x, z in ((x0, z0), (x1, z0), (x1, z1), (x0, z1)))
            tris += [(a, c, b), (a, d, c)]
    return np.array(tris, float)


def layout() -> tp.AtlasLayout:
    return tp.AtlasLayout(512, 1024, [
        tp.Swatch("Grass", 0, 0, 512, 512),
        tp.Swatch("Road", 0, 768, 128, 128),
        tp.Swatch("Rock", 256, 768, 256, 256),
        tp.Swatch("Flowers", 128, 768, 128, 128),
    ])


def stripe(x0: float, x1: float, size: int = 256) -> np.ndarray:
    weights = np.zeros((size, size), np.float32)
    px, _ = tp.pixel_centres(size)
    weights[(px >= x0) & (px < x1)] = 1.0
    return weights


class GeometryTests(unittest.TestCase):
    def test_cut_keeps_area_winding_and_interpolates(self):
        tri = np.array([[[0, 0, 0], [0, 0, 10], [10, 0, 0]]], float)
        attrs = {"uv": np.array([[[0, 0], [0, 1], [1, 0]]], float)}
        normal = tp.triangle_normals(tri)[0]
        cut, cut_attrs, origin = tp.cut_planes(tri, attrs, 0, [4.0])
        self.assertEqual(len(cut), 3)
        self.assertTrue(np.all(origin == 0))
        area = lambda t: np.linalg.norm(np.cross(t[:, 1] - t[:, 0], t[:, 2] - t[:, 0]), axis=1).sum() / 2  # noqa: E731
        self.assertAlmostEqual(area(cut), 50.0)
        self.assertTrue(np.allclose(tp.triangle_normals(cut), normal))
        # attributes follow the positions linearly (uv.x = x / 10 here)
        self.assertTrue(np.allclose(cut_attrs["uv"][:, :, 0], cut[:, :, 0] / 10))

    def test_rasterize_picks_the_highest_surface(self):
        low = grid(10, 10)
        high = grid(10, 10, lambda x, z: 3.0)
        ids, depth = tp.rasterize_top(np.concatenate([low, high]), 64, 20.0)
        covered = ids >= 0
        self.assertTrue(np.all(ids[covered] >= 2))
        self.assertTrue(np.allclose(depth[covered], 3.0))
        self.assertFalse(covered[-1, -1])

    def test_planar_uvs_follow_the_vanilla_density_inside_the_swatch(self):
        tri = np.array([[[20, 0, 20], [20, 0, 25], [25, 0, 20]]], float)
        uv = tp.planar_uvs(tri, np.array([1]), layout(), np.array([False]))[0]
        texels = uv * (512, 1024)
        self.assertTrue(np.all(texels[:, 0] >= 0) and np.all(texels[:, 0] <= 128))
        self.assertTrue(np.all(texels[:, 1] >= 768) and np.all(texels[:, 1] <= 896))
        # 5 units = 32 texels (6.4 per unit), less the half-texel inset scale
        self.assertAlmostEqual(texels[2, 0] - texels[0, 0], 32 * 127 / 128)


class CompileTests(unittest.TestCase):
    def test_a_painted_road_becomes_uv1_and_white_mask(self):
        mesh = grid(80)
        layers = [tp.Layer("Grass", 0), tp.Layer("Road", 1, stripe(20, 40))]
        result = tp.compile_paint(mesh, layers, layout())
        self.assertEqual(result.conflict_share, 0.0)
        centre = result.positions.mean(axis=1)
        on_road = (centre[:, 0] > 21) & (centre[:, 0] < 39)
        self.assertTrue(np.all(result.pairs[on_road] == (0, 1)))
        self.assertTrue(np.all(result.pairs[centre[:, 0] > 50] == (0, 0)))
        # every UV stays inside its triangle's swatch
        for uvs, swatches in ((result.uv0, result.pairs[:, 0]), (result.uv1, result.pairs[:, 1])):
            for tri_uv, s in zip(uvs, swatches):
                rect = layout().swatches[s]
                t = tri_uv * (512, 1024)
                self.assertTrue(np.all(t[:, 0] >= rect.x) and np.all(t[:, 0] <= rect.x + rect.w))
                self.assertTrue(np.all(t[:, 1] >= rect.y) and np.all(t[:, 1] <= rect.y + rect.h))
        px, pz = tp.pixel_centres(tp.MASK_SIZE)
        inside = (px > 22) & (px < 38) & (pz < 78)
        self.assertTrue(np.all(result.mask[inside] == 255))
        self.assertTrue(np.all(result.mask[(px > 45) & (px < 78) & (pz < 78)] == 0))

    def test_cuts_follow_the_smallest_swatch_repeat(self):
        mesh = np.array([[[0, 0, 0], [0, 0, 60], [60, 0, 0]]], float)
        layers = [tp.Layer("Grass", 0), tp.Layer("Road", 1, np.full((64, 64), 0.5, np.float32))]
        result = tp.compile_paint(mesh, layers, layout())
        # the road repeats every 20 units: no triangle crosses x or z = 20, 40
        for axis in (0, 2):
            coords = result.positions[:, :, axis]
            for line in (20.0, 40.0):
                self.assertFalse(np.any((coords.min(axis=1) < line - 1e-6) & (coords.max(axis=1) > line + 1e-6)))

    def test_three_overlapping_layers_report_conflicts(self):
        mesh = grid(60)
        layers = [
            tp.Layer("Grass", 0, None),
            tp.Layer("Road", 1, stripe(0, 30)),
            tp.Layer("Flowers", 3, np.full((256, 256), 0.5, np.float32)),
        ]
        result = tp.compile_paint(mesh, layers, layout())
        self.assertGreater(result.conflict_share, 0.0)
        self.assertTrue(any("conflict" in line for line in result.report(layout())))

    def test_without_base_two_details_are_drawn(self):
        mesh = grid(40)
        layers = [
            tp.Layer("Grass", 0),
            tp.Layer("Rock", 2, np.ones((64, 64), np.float32)),
            tp.Layer("Road", 1, stripe(0, 20, 64) * 0.5),
        ]
        result = tp.compile_paint(mesh, layers, layout())
        left = result.positions.mean(axis=1)[:, 0] < 18
        self.assertTrue(np.all(result.pairs[left] == (2, 1)))
        self.assertEqual(result.conflict_share, 0.0)

    def test_steep_faces_use_a_side_projection_and_one_swatch(self):
        wall = np.array([[[0, 0, 0], [0, 10, 0], [10, 0, 0]], [[10, 0, 0], [0, 10, 0], [10, 10, 0]]], float)
        layers = [tp.Layer("Grass", 0), tp.Layer("Rock", 2, None, slopes=True)]
        result = tp.compile_paint(wall, layers, layout())
        self.assertTrue(result.steep.all())
        self.assertTrue(np.all(result.pairs == 2))
        texels = result.uv0 * (512, 1024)
        heights = texels[:, :, 1].max(axis=1) - texels[:, :, 1].min(axis=1)
        self.assertGreater(heights.max(), 60)  # 10 units tall, not squashed flat

    def test_decompile_reproduces_compiled_layers(self):
        mesh = grid(80)
        road = stripe(20, 40, 512)
        layers = [tp.Layer("Grass", 0), tp.Layer("Road", 1, road)]
        result = tp.compile_paint(mesh, layers, layout())
        back = tp.decompile(result.positions, result.uv0, result.uv1, result.mask, layout(), 512)
        self.assertEqual([layer.swatch for layer in back], [0, 1])
        px, pz = tp.pixel_centres(512)
        area = (pz < 78) & (px < 78) & ((px < 18) | (px > 22)) & ((px < 38) | (px > 42))
        self.assertLess(np.abs(back[1].weights[area] - road[area]).mean(), 0.01)

    def test_detected_swatches_are_the_ones_used(self):
        mesh = grid(80)
        layers = [tp.Layer("Grass", 0), tp.Layer("Road", 1, stripe(0, 40, 256))]
        result = tp.compile_paint(mesh, layers, layout())
        found = tp.detect_swatches(result.positions, [result.uv0, result.uv1], 512, 1024)
        self.assertEqual(found, [(0, 0, 512, 512), (0, 768, 128, 128)])
        detected = tp.layout_from_uvs(result.positions, result.uv0, result.uv1, 512, 1024)
        self.assertEqual(detected.swatches[detected.base].name, "Base")
        self.assertEqual((detected.swatches[detected.base].w, detected.swatches[detected.base].h), (512, 512))


class LayoutTests(unittest.TestCase):
    def test_json_round_trip_and_validation(self):
        original = layout()
        self.assertEqual(tp.AtlasLayout.from_json(original.to_json()), original)
        broken = tp.AtlasLayout(512, 1024, [tp.Swatch("Too wide", 500, 0, 64, 64)])
        with self.assertRaises(ValueError):
            broken.validate()

    def test_swatch_at_prefers_the_smallest_containing_swatch(self):
        nested = tp.AtlasLayout(512, 1024, [tp.Swatch("All", 0, 0, 512, 1024), tp.Swatch("Road", 0, 768, 128, 128)])
        self.assertEqual(nested.swatch_at(10, 800), 1)
        self.assertEqual(nested.swatch_at(300, 100), 0)

    def test_build_atlas_packs_swatches_below_the_base(self):
        base = np.full((512, 512, 3), 10, np.uint8)
        extras = [("Road", np.full((128, 128, 3), 20, np.uint8)), ("Rock", np.full((256, 256, 3), 30, np.uint8))]
        atlas, built = tp.build_atlas(base, extras)
        self.assertEqual(atlas.shape, (1024, 512, 3))
        rock = next(s for s in built.swatches if s.name == "Rock")
        road = next(s for s in built.swatches if s.name == "Road")
        self.assertEqual((rock.x, rock.y, rock.w), (0, 512, 256))
        self.assertEqual((road.x, road.y), (256, 512))
        self.assertTrue(np.all(atlas[road.y:road.y + 128, road.x:road.x + 128] == 20))
        with self.assertRaises(ValueError):
            tp.build_atlas(base, [("Odd", np.zeros((100, 100, 3), np.uint8))])


class AutoPaintAndLightTests(unittest.TestCase):
    def test_slope_and_height_weights(self):
        hill = grid(40, 5, lambda x, z: max(0.0, x - 20.0) * 2.0)
        slope = tp.slope_weights(hill, 128, 30, 40)
        px, pz = tp.pixel_centres(128)
        self.assertTrue(np.all(slope[(px < 18) & (pz < 38)] == 0))
        self.assertTrue(np.all(slope[(px > 22) & (px < 38) & (pz < 38)] == 1))
        low = tp.height_weights(hill, 128, 0.0, 10.0)
        self.assertTrue(np.all(low[(px < 18) & (pz < 38)] == 1))
        self.assertTrue(np.all(low[(px > 32) & (px < 38) & (pz < 38)] == 0))

    def test_flat_ground_stays_white_and_a_ridge_casts_a_shadow(self):
        matrix = ((1 / 80, 0, 0, 0), (0, 0, 1 / 80, 0), (0, 0, 0, 1))
        flat = tp.bake_light(grid(80), matrix, 64)
        self.assertTrue(np.all(flat == 255))
        ridge = grid(80, 5, lambda x, z: 30.0 if 35 <= x <= 45 else 0.0)
        lit = tp.bake_light(ridge, matrix, 64, sun=(1.0, -1.0, 0.0))
        # the sun shines towards +x: ground just past the ridge is shadowed, before it is not
        self.assertLess(lit[32, 40], 200)
        self.assertEqual(lit[32, 10], 255)


@unittest.skipUnless(os.environ.get("FE9_EXTRACTED_FILES"), "set FE9_EXTRACTED_FILES to an extracted files/ directory")
class VanillaRoundTripTests(unittest.TestCase):
    def test_prologue_layers_recompile_close_to_vanilla(self):
        from fe_modding import terrain_kit

        container = Path(os.environ["FE9_EXTRACTED_FILES"]) / "zmap" / "bmap01" / "map.cmp"
        source = terrain_kit.read_terrain(container)
        found = tp.layout_from_uvs(source.positions, source.uv0, source.uv1, *source.atlas.size)
        self.assertEqual((found.swatches[found.base].w, found.swatches[found.base].h), (512, 512))
        layers = tp.decompile(source.positions, source.uv0, source.uv1, source.mask, found, 1024)
        result = tp.compile_paint(source.positions, layers, found, slope_degrees=89.9)
        atlas = np.asarray(source.atlas.convert("RGB"))
        vanilla = tp.CompileResult(source.positions, {}, source.uv0, source.uv1, np.zeros((0, 2), int),
                                   source.mask, np.zeros_like(source.mask, bool), np.zeros(0, bool))
        a = tp.render_compiled(vanilla, atlas, 512, 290.0).astype(int)
        b = tp.render_compiled(result, atlas, 512, 290.0).astype(int)
        self.assertLess(np.abs(a - b).mean(), 12.0)
        self.assertLess(result.conflict_share, 0.001)
        self.assertLess(len(result.positions), len(source.positions) * 1.1)


if __name__ == "__main__":
    unittest.main()
