"""Terrain kits: paint data I/O, compiling onto an import, Blender orchestration."""

import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fe_modding import blender, terrain_kit
from fe_modding import terrain_paint as tp
from fe_modding.formats import gltf_import


class NewMapFileTests(unittest.TestCase):
    def test_creates_separate_map_container_without_replacing_template(self):
        from fe_modding.gui import model_viewer as mv

        with tempfile.TemporaryDirectory() as folder:
            files = Path(folder) / "extracted" / "files"
            source = files / "zmap" / "bmap01" / "map.cmp"
            source.parent.mkdir(parents=True)
            source.write_bytes(b"template map")
            project = SimpleNamespace(files_dir=files)
            with patch.object(mv, "is_map_container", return_value=True):
                created = mv.create_new_map_file(project, source, "bmap_new")
            self.assertEqual(created, files / "zmap" / "bmap_new" / "map.cmp")
            self.assertEqual(created.read_bytes(), b"template map")
            self.assertEqual(source.read_bytes(), b"template map")

    def test_refuses_existing_or_unsafe_map_name(self):
        from fe_modding.gui import model_viewer as mv

        with tempfile.TemporaryDirectory() as folder:
            files = Path(folder) / "extracted" / "files"
            source = files / "zmap" / "bmap01" / "map.cmp"
            source.parent.mkdir(parents=True)
            source.write_bytes(b"template map")
            project = SimpleNamespace(files_dir=files)
            with patch.object(mv, "is_map_container", return_value=True):
                with self.assertRaises(FileExistsError):
                    mv.create_new_map_file(project, source, "BMAP01")
                with self.assertRaises(ValueError):
                    mv.create_new_map_file(project, source, "../outside")


def layout() -> tp.AtlasLayout:
    return tp.AtlasLayout(512, 1024, [tp.Swatch("Grass", 0, 0, 512, 512), tp.Swatch("Road", 0, 768, 128, 128)])


def paint(light: bool = True) -> terrain_kit.PaintData:
    weights = np.zeros((64, 64), np.float32)
    weights[:, 0:2] = 1.0  # 10 units per pixel: x 0 to 20
    return terrain_kit.PaintData(
        layout(), [tp.Layer("Grass", 0), tp.Layer("Road", 1, weights)],
        Image.new("RGBA", (512, 1024), (20, 120, 30, 255)), False,
        Image.new("L", (32, 32), 200) if light else None,
    )


def flat_scene(size: float = 40.0, material: str = "ground") -> gltf_import.ImportedScene:
    up = ((0.0, 1.0, 0.0),) * 3
    tris = []
    for x0 in range(0, int(size), 10):
        for z0 in range(0, int(size), 10):
            a, b, c, d = (x0, 0.0, z0), (x0 + 10, 0.0, z0), (x0 + 10, 0.0, z0 + 10), (x0, 0.0, z0 + 10)
            for tri in ((a, c, b), (a, d, c)):
                tris.append(gltf_import.ImportedTriangle(tri, up, ((0.0, 0.0),) * 3))
    return gltf_import.ImportedScene([gltf_import.ImportedMaterial(material)], {0: tris})


class PaintDataTests(unittest.TestCase):
    def test_paint_folder_round_trip(self):
        with tempfile.TemporaryDirectory() as folder:
            terrain_kit.write_paint_dir(Path(folder), paint(), {"map": "bmap01", "budget": 9000})
            back = terrain_kit.read_paint_dir(Path(folder))
        self.assertEqual(back.layout, layout())
        self.assertEqual([(l.name, l.swatch) for l in back.layers], [("Grass", 0), ("Road", 1)])
        self.assertIsNone(back.layers[0].weights)
        self.assertTrue(np.array_equal(back.layers[1].weights, paint().layers[1].weights))
        self.assertEqual(back.light.size, (32, 32))
        self.assertEqual(back.extra["map"], "bmap01")

    def test_a_layer_with_an_unknown_swatch_is_refused(self):
        data = paint()
        data.layers[1].swatch = 7
        with tempfile.TemporaryDirectory() as folder:
            terrain_kit.write_paint_dir(Path(folder), data)
            with self.assertRaises(ValueError):
                terrain_kit.read_paint_dir(Path(folder))

    def test_new_water_marker_survives_the_kit_manifest(self):
        body = terrain_kit.WaterBody(
            "bmap99_water0", -2.0,
            np.array([[(0, -2, 0), (0, -2, 10), (10, -2, 10)]], dtype=float),
            None, -1, False, True,
        )
        water = terrain_kit.WaterData((0, 0), [body], None, {}, [], {})
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            manifest = terrain_kit.write_water_dir(root, water)
            self.assertTrue(manifest["bodies"][0]["new"])
            edit = terrain_kit.read_water_edit(root, {**manifest, "removed": [], "fade_changed": False})
            self.assertTrue(edit.bodies[0].new)

    def test_unused_cells_become_swatches(self):
        table = layout()
        added = terrain_kit.add_unused_cells(table)
        # the bottom half has 4 x 4 cells of 128; the road takes one
        self.assertEqual(added, 15)
        self.assertEqual(terrain_kit.add_unused_cells(table), 0)

    def test_unused_cells_get_names_from_their_pixels(self):
        table = layout()
        atlas = Image.new("RGBA", (512, 1024), (35, 130, 45, 255))
        terrain_kit.add_unused_cells(table, atlas=atlas)
        self.assertTrue(all(s.name.startswith("Smooth green ") for s in table.swatches[2:]))

    def test_old_colour_only_auto_names_are_upgraded(self):
        table = tp.AtlasLayout(128, 128, [tp.Swatch("Grass 1,1", 0, 0, 128, 128)])
        terrain_kit._name_generic_swatches(table, Image.new("RGBA", (128, 128), (35, 130, 45, 255)))
        self.assertEqual(table.swatches[0].name, "Smooth green 1,1")

    def test_unused_cells_infer_rectangular_indoor_grid(self):
        table = tp.AtlasLayout(256, 512, [
            tp.Swatch("Base", 0, 0, 256, 256),
            tp.Swatch("Wall", 0, 256, 64, 32),
            tp.Swatch("Trim", 64, 256, 128, 64),
        ])
        terrain_kit.add_unused_cells(table)
        generated = [swatch for swatch in table.swatches if swatch.name.startswith("Cell ")]
        self.assertTrue(generated)
        self.assertTrue(all((swatch.w, swatch.h) == (64, 32) for swatch in generated))

    def test_visually_continuous_minimum_cells_are_merged(self):
        table = tp.AtlasLayout(128, 96, [tp.Swatch("Base", 0, 64, 128, 32)])
        atlas = np.zeros((96, 128, 4), np.uint8)
        atlas[..., 3] = 255
        # Two coherent 64x64 regions, each internally continuous across the
        # 32-texel measurement cells, with a strong boundary between them.
        atlas[:64, :64, :3] = 45
        atlas[:64, 64:, 0] = 210
        atlas[:64, 64:, 1:3] = 30
        terrain_kit.add_unused_cells(table, cell=(32, 32), atlas=Image.fromarray(atlas, "RGBA"))
        generated = table.swatches[1:]
        self.assertEqual([(s.x, s.y, s.w, s.h) for s in generated], [(0, 0, 64, 64), (64, 0, 64, 64)])

    def test_matching_edge_pixels_do_not_bridge_different_terrains(self):
        table = tp.AtlasLayout(64, 64, [tp.Swatch("Base", 0, 32, 64, 32)])
        atlas = np.zeros((64, 64, 4), np.uint8)
        atlas[..., 3] = 255
        atlas[:32, :32, :3] = 40
        atlas[:32, 32:, 0] = 210
        atlas[:32, 32:, 1:3] = 30
        # Make the shared edge identical. The old seam-only shortcut merged
        # these cells despite their clearly different interiors.
        atlas[:32, 31, :3] = (120, 60, 40)
        atlas[:32, 32, :3] = (120, 60, 40)
        terrain_kit.add_unused_cells(table, cell=(32, 32), atlas=Image.fromarray(atlas, "RGBA"))
        self.assertEqual([(s.x, s.y, s.w, s.h) for s in table.swatches[1:]],
                         [(0, 0, 32, 32), (32, 0, 32, 32)])

    def test_same_colour_different_texture_scale_stays_separate(self):
        table = tp.AtlasLayout(128, 128, [tp.Swatch("Base", 0, 64, 128, 64)])
        atlas = np.zeros((128, 128, 4), np.uint8)
        atlas[..., 3] = 255
        yy, xx = np.indices((64, 64))
        coarse = ((xx // 12 + yy // 12) % 2) * 80 + 80
        fine = ((xx // 2 + yy // 2) % 2) * 80 + 80
        atlas[:64, :64, :3] = coarse[..., None]
        atlas[:64, 64:, :3] = fine[..., None]
        terrain_kit.add_unused_cells(table, cell=(64, 64), atlas=Image.fromarray(atlas, "RGBA"))
        self.assertEqual([(s.x, s.y, s.w, s.h) for s in table.swatches[1:]],
                         [(0, 0, 64, 64), (64, 0, 64, 64)])

    def test_dense_indoor_grid_groups_structural_tile_sets(self):
        table = tp.AtlasLayout(256, 256, [tp.Swatch("Base", 0, 224, 256, 32)])
        atlas = np.zeros((256, 256, 4), np.uint8)
        atlas[..., 3] = 255
        # The top-left 2 x 2 kit has deliberately different interiors (as do
        # wall corners/edges) but its shared borders continue.  A strong edge
        # separates it from the neighbouring packed texture.
        colours = ((45, 55, 65), (95, 75, 45), (35, 85, 55), (105, 45, 70))
        for index, colour in enumerate(colours):
            row, column = divmod(index, 2)
            atlas[row * 32:(row + 1) * 32, column * 32:(column + 1) * 32, :3] = colour
        atlas[:64, 31:33, :3] = 70
        atlas[31:33, :64, :3] = 70
        atlas[:64, 64:, :3] = (210, 25, 20)
        terrain_kit.add_unused_cells(table, cell=(32, 32), atlas=Image.fromarray(atlas, "RGBA"))
        generated = [(s.x, s.y, s.w, s.h) for s in table.swatches[1:]]
        self.assertIn((0, 0, 64, 64), generated)
        self.assertNotIn((0, 0, 32, 32), generated)
        self.assertFalse(any(x == 0 and y == 0 and w > 64 for x, y, w, h in generated))

    def test_mixed_uv_rectangle_splits_at_strong_material_boundaries(self):
        table = tp.AtlasLayout(256, 256, [
            tp.Swatch("Base", 0, 0, 256, 128),
            tp.Swatch("UV bounds", 0, 128, 256, 128),
        ])
        atlas = np.zeros((256, 256, 4), np.uint8)
        atlas[..., 3] = 255
        for column, colour in enumerate(((35, 50, 20), (150, 145, 130),
                                         (55, 80, 120), (180, 45, 30))):
            atlas[128:, column * 64:(column + 1) * 64, :3] = colour
        terrain_kit._split_mixed_swatches(table, Image.fromarray(atlas, "RGBA"))
        self.assertEqual([(s.x, s.y, s.w, s.h) for s in table.swatches[1:]],
                         [(0, 128, 64, 128), (64, 128, 64, 128),
                          (128, 128, 64, 128), (192, 128, 64, 128)])

    def test_saved_layout_and_custom_atlas_win_over_detection(self):
        source = SimpleNamespace(atlas=Image.new("RGBA", (512, 1024)), positions=np.zeros((0, 3, 3)),
                                 uv0=np.zeros((0, 3, 2)), uv1=np.zeros((0, 3, 2)))
        with tempfile.TemporaryDirectory() as folder:
            project = Path(folder)
            detected, _atlas, custom = terrain_kit.load_layout(source, project, "bmap01")
            self.assertFalse(custom)
            self.assertEqual(detected.swatches[0].name, "Base")
            terrain_kit.save_layout(project, "bmap01", layout(), Image.new("RGBA", (512, 1024), "red"))
            saved, atlas, custom = terrain_kit.load_layout(source, project, "bmap01")
            self.assertEqual(saved.swatches[:2], layout().swatches)
            self.assertGreater(len(saved.swatches), 2)
            self.assertLess(len(saved.swatches), 17)  # continuous empty cells are grouped
            self.assertTrue(all(not s.name.startswith(("Cell ", "Swatch ")) for s in saved.swatches))
            self.assertTrue(custom)
            self.assertEqual(atlas.getpixel((0, 0)), (255, 0, 0, 255))
            terrain_kit.save_layout(project, "bmap01", layout(), clear_custom=True)
            self.assertFalse(terrain_kit.custom_atlas_path(project, "bmap01").exists())

    def test_project_tilesets_round_trip_independently_of_map_layouts(self):
        with tempfile.TemporaryDirectory() as folder:
            project = Path(folder)
            atlas = Image.new("RGBA", (512, 1024), (30, 80, 120, 255))
            created = terrain_kit.save_project_tileset(project, "Castle Floors", "bmap16", layout(), atlas)
            self.assertEqual(created.key, "castle_floors")
            loaded = terrain_kit.load_project_tileset(project, created.key)
            self.assertEqual((loaded.name, loaded.source_map), ("Castle Floors", "bmap16"))
            self.assertEqual(loaded.layout, layout())
            self.assertEqual(loaded.atlas.getpixel((0, 0)), (30, 80, 120, 255))
            self.assertEqual([item.key for item in terrain_kit.project_tilesets(project)], ["castle_floors"])

    def test_project_tileset_rejects_an_atlas_with_the_wrong_size(self):
        with tempfile.TemporaryDirectory() as folder:
            with self.assertRaises(ValueError):
                terrain_kit.save_project_tileset(
                    Path(folder), "Bad", "bmap01", layout(), Image.new("RGBA", (64, 64))
                )


class ApplyPaintTests(unittest.TestCase):
    def test_compiles_onto_the_scene_and_renames_a_single_material(self):
        scene = flat_scene()
        outcome = terrain_kit.apply_paint(scene, paint())
        self.assertEqual(scene.materials[0].name, "map_base")
        self.assertEqual(scene.materials[0].image.size, (512, 1024))
        tris = scene.triangles[0]
        self.assertTrue(all(t.uvs2 is not None for t in tris))
        # the road repeats every 20 units: the 10-unit cells need no cut
        self.assertEqual(len(tris), 32)
        self.assertEqual(outcome.mask.size, (tp.MASK_SIZE, tp.MASK_SIZE))
        self.assertEqual(set(outcome.previews), {"Game", "Painted", "Conflicts", "Mask"})
        road = [t for t in tris if np.mean([p[0] for p in t.positions]) < 20]
        self.assertTrue(road and all(min(uv[1] for uv in t.uvs2) >= 0.75 for t in road))

    def test_several_materials_need_a_map_base(self):
        scene = flat_scene()
        scene.materials.append(gltf_import.ImportedMaterial("other"))
        with self.assertRaises(gltf_import.GltfImportError):
            terrain_kit.apply_paint(scene, paint())


class BlenderOrchestrationTests(unittest.TestCase):
    def test_new_map_kit_uses_a_reusable_project_tileset(self):
        from fe_modding.gui import model_viewer as mv

        source = SimpleNamespace(terrain="bmap_new", triangles=1000)
        water = terrain_kit.WaterData((0, 0), [], None, {}, [], {})
        saved = terrain_kit.ProjectTileset(
            "castle", "Castle", "bmap16", layout(), Image.new("RGBA", (512, 1024), "purple")
        )
        captured = {}

        def export(_glb, write_inputs, target, _blender):
            with tempfile.TemporaryDirectory() as folder:
                write_inputs(Path(folder))
                captured["paint"] = terrain_kit.read_paint_dir(Path(folder))
            return target

        with tempfile.TemporaryDirectory() as folder, \
             patch.object(terrain_kit, "read_terrain", return_value=source), \
             patch.object(terrain_kit, "read_water", return_value=water), \
             patch.object(terrain_kit, "load_project_tileset", return_value=saved) as load_saved, \
             patch.object(terrain_kit, "load_layout") as load_map, \
             patch.object(mv, "export_map_terrain_glb", return_value=b"glb"), \
             patch.object(mv.blender_tool, "export_terrain_kit", side_effect=export):
            root = Path(folder)
            mv.export_new_map_kit(
                root / "zmap" / "new" / "map.cmp", root / "zmap" / "bmap16" / "map.cmp",
                root / "kit.blend", 20, (16, 16), (2, 2), False, project_dir=root,
                project_tileset_key="castle",
            )
        load_saved.assert_called_once()
        load_map.assert_not_called()
        self.assertTrue(captured["paint"].custom_atlas)
        self.assertEqual(captured["paint"].atlas.getpixel((0, 0)), (128, 0, 128, 255))

    def test_addon_ships_the_shared_compiler(self):
        files = blender.addon_files()
        self.assertIn("__init__.py", files)
        self.assertIn("kit.py", files)
        for shared in blender.ADDON_SHARED:
            self.assertEqual(files[shared.name], shared.read_bytes())
        self.assertIn("water_kit.py", files)
        with tempfile.TemporaryDirectory() as folder:
            archive = blender.addon_zip(Path(folder) / "addon.zip")
            import zipfile

            names = zipfile.ZipFile(archive).namelist()
        self.assertIn("tellius_terrain/terrain_paint.py", names)

    def test_kit_export_runs_blender_headless_on_the_inputs(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            exe = root / "blender.exe"
            exe.write_bytes(b"")
            target = root / "kit.blend"
            seen = {}

            def run(args, **kwargs):
                tail = args[args.index("--") + 1:]
                seen["args"] = args
                seen["package"] = (Path(tail[0]) / "tellius_terrain" / "kit.py").is_file()
                seen["manifest"] = (Path(tail[2]) / "kit.json").is_file()
                Path(tail[3]).write_bytes(b"blend")
                return SimpleNamespace(returncode=0, stdout="", stderr="")

            blender.export_terrain_kit(b"glb", lambda inputs: terrain_kit.write_paint_dir(inputs, paint()),
                                       target, exe, run=run)
            self.assertTrue(target.is_file())
        self.assertIn("--factory-startup", seen["args"])
        self.assertTrue(seen["package"] and seen["manifest"])

    def test_import_conversion_returns_the_kit_paint(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            exe = root / "blender.exe"
            exe.write_bytes(b"")
            source = root / "kit.blend"
            source.write_bytes(b"blend")

            def run(args, **kwargs):
                out = Path(args[args.index("--") + 3])
                terrain_kit.write_paint_dir(out, paint())
                (out / "terrain.glb").write_bytes(b"glb")
                return SimpleNamespace(returncode=0, stdout="", stderr="")

            converted = blender.blend_terrain_for_import(source, "bmap01", exe, run=run)
        self.assertEqual(converted.glb, b"glb")
        self.assertEqual(converted.paint.layout, layout())

    def test_install_needs_blender_to_confirm(self):
        with tempfile.TemporaryDirectory() as folder:
            exe = Path(folder) / "blender.exe"
            exe.write_bytes(b"")
            quiet = lambda args, **kwargs: SimpleNamespace(returncode=0, stdout="", stderr="")  # noqa: E731
            with self.assertRaises(blender.BlenderError):
                blender.install_addon(exe, run=quiet)
            confirmed = lambda args, **kwargs: SimpleNamespace(  # noqa: E731
                returncode=0, stdout="TELLIUS_ADDON_INSTALLED\n", stderr="")
            self.assertEqual(blender.install_addon(exe, run=confirmed), exe)


FILES = os.environ.get("FE9_EXTRACTED_FILES")


@unittest.skipUnless(FILES, "set FE9_EXTRACTED_FILES to an extracted files/ directory")
class PaintedImportTests(unittest.TestCase):
    def test_prologue_imports_its_own_paint(self):
        from fe_modding.gui import model_viewer as mv

        with tempfile.TemporaryDirectory() as folder:
            container = Path(folder) / "zmap" / "bmap01" / "map.cmp"
            container.parent.mkdir(parents=True)
            shutil.copy(Path(FILES) / "zmap" / "bmap01" / "map.cmp", container)
            source = terrain_kit.read_terrain(container)
            table, atlas, custom = terrain_kit.load_layout(source, None, "bmap01")
            data = terrain_kit.kit_paint(source, table, atlas, custom, 512)
            glb = Path(folder) / "terrain.glb"
            glb.write_bytes(mv.export_map_terrain_glb(container))
            result = mv.replace_map_terrain_with_glb(container, glb, True, True, True, None, False,
                                                     paint=data, light=data.light)
        self.assertEqual(list(result.outputs), [container])
        self.assertIn("Game", result.previews)
        self.assertTrue(any("Painted texturing" in w for w in result.warnings))
        self.assertTrue(result.texturing[0].endswith(")."))


@unittest.skipUnless(FILES, "set FE9_EXTRACTED_FILES to an extracted files/ directory")
class WaterKitDataTests(unittest.TestCase):
    def read(self, name):
        with tempfile.TemporaryDirectory() as folder:
            container = Path(folder) / "zmap" / name / "map.cmp"
            container.parent.mkdir(parents=True)
            shutil.copy(Path(FILES) / "zmap" / name / "map.cmp", container)
            return terrain_kit.read_water(container)

    def test_river_with_fade_and_shore_waves(self):
        water = self.read("bmap02")
        self.assertEqual([b.name for b in water.bodies], ["bmap02_water0"])
        body = water.bodies[0]
        self.assertAlmostEqual(body.level, 2.0)
        self.assertEqual(body.scroll, (-1.0, -0.5, -0.5, -1.0))
        self.assertTrue(body.fade)
        self.assertEqual(water.fade.shape, (512, 512))
        self.assertAlmostEqual(float(water.fade.max()), 0.8, places=2)
        self.assertEqual(water.origin, (-57, -41))
        self.assertEqual(len([w for w in water.waves if w.name == "wave_99"]), 64)
        self.assertIn("wave_99", water.wave_models)
        # every wave sits over the water surface it laps
        from fe_modding import water_kit
        centres_x = [5 * w.column + 2.5 for w in water.waves]
        centres_z = [5 * w.row + 2.5 for w in water.waves]
        self.assertTrue(water_kit.covered(body.positions, centres_x, centres_z).all())
        with tempfile.TemporaryDirectory() as folder:
            manifest = terrain_kit.write_water_dir(Path(folder), water)
            self.assertEqual(manifest["bodies"][0]["file"], "bmap02_water0".join(("water_", ".npy")))
            self.assertFalse(manifest["bodies"][0]["new"])
            stored = np.load(Path(folder) / manifest["bodies"][0]["file"])
            self.assertTrue(np.allclose(stored, body.positions, atol=1e-4))
            self.assertEqual(np.load(Path(folder) / manifest["textures"][str(body.texture)]).shape[2], 4)
            self.assertEqual(len(manifest["waves"]), len(water.waves))

    def test_open_sea_has_no_fade(self):
        water = self.read("bmap14")
        self.assertEqual(len(water.bodies), 1)
        self.assertFalse(water.bodies[0].fade)
        self.assertIsNone(water.fade)
        self.assertTrue({w.name for w in water.waves} <= set(terrain_kit.WAVE_OBJECTS))

    def test_dry_map(self):
        water = self.read("bmap06")
        self.assertEqual(water.bodies, [])
        self.assertIsNone(water.fade)

    # -- applying a kit's water (terrain_kit.apply_water) ---------------------------------

    def unpack(self, name):
        from fe_modding import map_props
        return map_props.read_map_container(Path(FILES) / "zmap" / name / "map.cmp")

    def edit_of(self, name):
        water = self.read(name)
        return terrain_kit.WaterEdit(water.bodies, [], water.fade, False, water.waves, water.origin)

    def test_untouched_water_changes_nothing(self):
        for name in ("bmap02", "bmap13"):
            entries, files = self.unpack(name)
            before = dict(files)
            outcome = terrain_kit.apply_water(entries, files, self.edit_of(name))
            self.assertEqual({k for k in files if files[k] != before.get(k)}, set(), name)
            self.assertIn("0 of 1 water surfaces rebuilt, 0 removed.", outcome.notes)
            self.assertIn("Water", outcome.previews)

    def test_flow_waves_and_fade(self):
        from fe_modding import map_props
        from fe_modding.formats import map_file, tpl
        import io

        entries, files = self.unpack("bmap02")
        edit = self.edit_of("bmap02")
        edit.bodies[0].scroll = (0.25, -0.5, 1.0, 0.0)
        first, second = edit.waves[0], edit.waves[1]
        first.column += 1
        first.angle = 64
        edit.waves.remove(second)
        edit.waves.append(terrain_kit.WaveInstance(-1, "wave_99", first.column, first.row + 3, 0, first.height))
        edit.fade = np.zeros_like(edit.fade)
        edit.fade[:, :256] = 0.8
        edit.fade_changed = True
        outcome = terrain_kit.apply_water(entries, files, edit)
        self.assertEqual(map_props.water_scroll(files["bmap02_water0.ga"]), (0.25, -0.5, 1.0, 0.0))
        data = map_file.read_map_bytes(files["map.bin"])
        waves = [i for i in data.build_inst if data.build_desc[i.desc_index].filename == "wave_99"]
        self.assertEqual(len(waves), 64)
        ox, oy = edit.origin
        self.assertIn((first.column + ox, first.row + oy, 64), [(i.x, i.y, i.angle % 256) for i in waves])
        self.assertIn("Shore props: 1 moved or turned, 1 removed, 1 added.", outcome.notes)
        image = np.asarray(tpl.read_tpl_images(io.BytesIO(files[map_props.texpack_name(files)]))[3].convert("L"))
        self.assertGreater(image[:, :200].mean(), 190)
        self.assertLess(image[:, 300:].mean(), 10)

    def test_raised_water_is_rebuilt(self):
        from fe_modding import map_props

        entries, files = self.unpack("bmap02")
        edit = self.edit_of("bmap02")
        edit.bodies[0].positions = edit.bodies[0].positions + (0.0, 1.0, 0.0)
        terrain_kit.apply_water(entries, files, edit)
        surface = terrain_kit._model_triangles(files["bmap02_water0.gs"])
        self.assertTrue(np.allclose(surface[..., 1], 3.0))
        self.assertEqual(map_props.water_scroll(files["bmap02_water0.ga"]), (-1.0, -0.5, -0.5, -1.0))

    def test_new_water_and_waves_on_a_dry_map(self):
        from fe_modding import map_props, water_kit
        from fe_modding.formats import map_file

        entries, files = self.unpack("bmap06")
        _e, donor = self.unpack("bmap02")
        pond = water_kit.shoreline(np.array([[(0, -1, 0), (0, -1, 50), (50, -1, 50)], [(0, -1, 0), (50, -1, 50), (50, -1, 0)]]),
                                   0.0, margin=0.0, bounds=(0, 0, 50, 50))
        body = terrain_kit.WaterBody("bmap06_water0", 0.0, pond, None, -1, True, True)
        origin = self.read("bmap06").origin
        wave = terrain_kit.WaveInstance(-1, "wave_99", 2, 2, 0, water_kit.wave_height(0.0))
        edit = terrain_kit.WaterEdit([body], [], None, False, [wave], origin)
        self.assertEqual(terrain_kit.water_needs_donor(files, edit), ["water", "wave_99"])
        with self.assertRaises(terrain_kit.WaterDonorNeeded):
            terrain_kit.apply_water(entries, dict(files), edit)
        outcome = terrain_kit.apply_water(entries, files, edit, donor)
        data = map_file.read_map_bytes(files["map.bin"])
        self.assertEqual(map_props.water_names(files, data), ["bmap06_water0"])
        self.assertTrue(data.extra.unknown_tail & map_props.MAP_FLAG_WATER)
        self.assertIn("wave_99", {o.filename for o in data.build_desc})
        self.assertTrue(any("donor map's shoreline fade" in w for w in outcome.warnings))

    def test_removed_water_clears_the_flag(self):
        from fe_modding import map_props
        from fe_modding.formats import map_file

        entries, files = self.unpack("bmap02")
        edit = self.edit_of("bmap02")
        edit.removed = [edit.bodies[0].name]
        edit.bodies = []
        terrain_kit.apply_water(entries, files, edit)
        data = map_file.read_map_bytes(files["map.bin"])
        self.assertFalse([i for i in data.build_inst if data.build_desc[i.desc_index].filename == "bmap02_water0"])
        self.assertFalse(data.extra.unknown_tail & map_props.MAP_FLAG_WATER)

    def test_repaint_tiles(self):
        from fe_modding import map_props

        entries, files = self.unpack("bmap13")
        from fe_modding.formats import map_file

        before = map_file.terrain_grid(files["map.bin"])
        outcome = terrain_kit.apply_water(entries, files, self.edit_of("bmap13"), repaint=("海", "平地"))
        note = next(n for n in outcome.notes if n.startswith("Tiles repainted:"))
        after = map_file.terrain_grid(files["map.bin"])
        changed = [(b, a) for cb, ca in zip(before, after) for b, a in zip(cb, ca) if b != a]
        # vanilla bmap13 mostly agrees with the rule: few changes, only natural ground floods
        self.assertLess(len(changed), 80, note)
        self.assertTrue(all(a == "平地" or b.startswith(terrain_kit.FLOODABLE_PREFIXES) for b, a in changed))
        dry, uncovered = map_props.water_terrain_mismatch(files)
        self.assertEqual(uncovered, 0)


@unittest.skipUnless(FILES and os.environ.get("FE9_BLENDER"),
                     "set FE9_EXTRACTED_FILES and FE9_BLENDER (blender.exe) to build a real kit")
class RealBlenderKitTests(unittest.TestCase):
    def test_kit_builds_and_converts_back(self):
        from fe_modding.gui import model_viewer as mv

        with tempfile.TemporaryDirectory() as folder:
            container = Path(folder) / "zmap" / "bmap01" / "map.cmp"
            container.parent.mkdir(parents=True)
            shutil.copy(Path(FILES) / "zmap" / "bmap01" / "map.cmp", container)
            kit = Path(folder) / "kit.blend"
            mv.export_terrain_kit(container, kit, (), os.environ["FE9_BLENDER"], None, 4.0)
            converted = blender.blend_terrain_for_import(kit, "bmap01", os.environ["FE9_BLENDER"])
        self.assertGreater(len(converted.glb), 1000)
        self.assertGreaterEqual(len(converted.paint.layers), 2)
        self.assertEqual(converted.paint.extra["map"], "bmap01")

    def test_kit_carries_the_water_and_its_waves(self):
        import json
        import subprocess

        from fe_modding.gui import model_viewer as mv

        check = (
            "import bpy, json, sys\n"
            "sys.path.insert(0, sys.argv[-1])\n"
            "from tellius_terrain import kit\n"
            "scene = bpy.context.scene\n"
            "waves = kit.wave_objects(scene)\n"
            "stored = {w['index']: [w['column'], w['row'], w['angle'], round(w['height'], 4)]\n"
            "          for w in json.loads(scene[kit.KIT_KEY])['water']['waves']}\n"
            "back = {o['fe9_instance']: [*kit.wave_placement(o)[:3], round(kit.wave_placement(o)[3], 4)] for o in waves}\n"
            "print('WATERKIT ' + json.dumps({'water': [o['fe9_water'] for o in kit.water_objects(scene)],\n"
            "      'waves': len(waves), 'same': back == stored}))\n"
        )
        with tempfile.TemporaryDirectory() as folder:
            container = Path(folder) / "zmap" / "bmap02" / "map.cmp"
            container.parent.mkdir(parents=True)
            shutil.copy(Path(FILES) / "zmap" / "bmap02" / "map.cmp", container)
            kit = Path(folder) / "kit.blend"
            mv.export_terrain_kit(container, kit, (), os.environ["FE9_BLENDER"], None, 4.0)
            script = Path(folder) / "check.py"
            script.write_text(check, encoding="utf-8")
            blender.stage_addon(Path(folder) / "addon")
            run = subprocess.run([os.environ["FE9_BLENDER"], "-b", "--factory-startup", str(kit), "--python",
                                  str(script), "--", str(Path(folder) / "addon")], capture_output=True, text=True)
        line = next(line for line in run.stdout.splitlines() if line.startswith("WATERKIT "))
        result = json.loads(line[len("WATERKIT "):])
        self.assertEqual(result, {"water": ["bmap02_water0"], "waves": 64, "same": True})

    def test_kit_water_round_trip(self):
        import subprocess

        from fe_modding import map_props
        from fe_modding.formats import gs_file, lz10, pak
        from fe_modding.gui import model_viewer as mv

        edit = (
            "import bpy, sys\n"
            "sys.path.insert(0, sys.argv[sys.argv.index('--') + 1])\n"
            "import tellius_terrain\n"
            "tellius_terrain.register()\n"
            "from tellius_terrain import kit\n"
            "sc = bpy.context.scene\n"
            "w = kit.active_water(sc)\n"
            "sc.fe9_water = w\n"
            "tri = kit.triangles_of(w)\n"
            "x, z = tri[len(tri) // 2].mean(axis=0)[[0, 2]]\n"
            "sc.cursor.location = (x, -z, 0)\n"
            "sc.fe9_water_level = sc.fe9_water_level + 1.0\n"
            "sc.fe9_water_open_sea = True\n"
            "bpy.ops.tellius.cut_shoreline()\n"
            "bpy.ops.tellius.make_fade()\n"
            "sc.fe9_flow1_dir, sc.fe9_flow1_speed = 90.0, 2.0\n"
            "bpy.ops.wm.save_as_mainfile(filepath=sys.argv[-1])\n"
        )

        def imported(container, kit):
            converted = blender.blend_terrain_for_import(kit, "bmap01", os.environ["FE9_BLENDER"])
            glb = kit.with_suffix(".glb")
            glb.write_bytes(converted.glb)
            result = mv.replace_map_terrain_with_glb(container, glb, True, True, True, None, True,
                                                     paint=converted.paint, water=converted.water)
            raw = lz10.decompress(result.outputs[container])
            return result, {e.name: pak.read_pak_file_content(raw, e) for e in pak.read_pak_entries(raw)}

        with tempfile.TemporaryDirectory() as folder:
            container = Path(folder) / "zmap" / "bmap01" / "map.cmp"
            container.parent.mkdir(parents=True)
            shutil.copy(Path(FILES) / "zmap" / "bmap01" / "map.cmp", container)
            _entries, original = map_props.read_map_container(container)
            kit = Path(folder) / "kit.blend"
            mv.export_terrain_kit(container, kit, (), os.environ["FE9_BLENDER"], None, 4.0)
            untouched, files = imported(container, kit)
            script = Path(folder) / "edit.py"
            script.write_text(edit, encoding="utf-8")
            blender.stage_addon(Path(folder) / "addon")
            edited_kit = Path(folder) / "edited.blend"
            subprocess.run([os.environ["FE9_BLENDER"], "-b", "--factory-startup", str(kit), "--python", str(script),
                            "--", str(Path(folder) / "addon"), str(edited_kit)], capture_output=True, text=True, check=True)
            edited, changed = imported(container, edited_kit)
        # untouched: the same water, its texture ids renumbered by the terrain import only
        self.assertIn("0 of 1 water surfaces rebuilt, 0 removed.", untouched.water_notes)
        self.assertEqual(files["bmap01_water0.ga"], original["bmap01_water0.ga"])
        gs = gs_file.read_gs(files["bmap01_water0.gs"])
        vanilla = gs_file.read_gs(original["bmap01_water0.gs"]).materials[0].textures
        for record, before in zip(gs.materials[0].textures, vanilla):
            record.tex_id = before.tex_id
        self.assertEqual(gs_file.write_gs(gs), original["bmap01_water0.gs"])
        # edited: raised one unit, recut, new flow and fade
        self.assertIn("1 of 1 water surfaces rebuilt, 0 removed.", edited.water_notes)
        self.assertIn("Shoreline fade replaced.", edited.water_notes)
        self.assertTrue(np.allclose(terrain_kit._model_triangles(changed["bmap01_water0.gs"])[..., 1], -1.0))
        self.assertEqual(map_props.water_scroll(changed["bmap01_water0.ga"])[:2], (0.0, -2.0))
        self.assertIn("Water", edited.water_previews)

    def test_water_panel_operators(self):
        import json
        import subprocess

        from fe_modding.gui import model_viewer as mv

        drive = (
            "import bpy, json, sys\n"
            "sys.path.insert(0, sys.argv[-1])\n"
            "import tellius_terrain\n"
            "tellius_terrain.register()\n"
            "from tellius_terrain import kit\n"
            "sc = bpy.context.scene\n"
            "water = kit.active_water(sc)\n"
            "sc.fe9_water = water\n"
            "tri = kit.triangles_of(water)\n"
            "x, z = tri[len(tri) // 2].mean(axis=0)[[0, 2]]\n"
            "sc.cursor.location = (x, -z, 0)\n"
            "sc.fe9_water_level = sc.fe9_water_level + 1.0\n"
            "out = {'level': round(max(v.co.z for v in water.data.vertices), 3)}\n"
            "out['cut'] = list(bpy.ops.tellius.cut_shoreline())\n"
            "out['fade'] = list(bpy.ops.tellius.make_fade())\n"
            "sc.fe9_flow1_dir, sc.fe9_flow1_speed = 90.0, 2.0\n"
            "out['scroll'] = [round(v, 3) for v in water['fe9_scroll']]\n"
            "out['waves'] = [list(bpy.ops.tellius.place_waves()), len(kit.wave_objects(sc))]\n"
            "out['check'] = [list(bpy.ops.tellius.water_check()), sc.fe9_water_report.splitlines()[0]]\n"
            "print('WATERPANEL ' + json.dumps(out))\n"
        )
        with tempfile.TemporaryDirectory() as folder:
            container = Path(folder) / "zmap" / "bmap13" / "map.cmp"
            container.parent.mkdir(parents=True)
            shutil.copy(Path(FILES) / "zmap" / "bmap13" / "map.cmp", container)
            kit = Path(folder) / "kit.blend"
            mv.export_terrain_kit(container, kit, (), os.environ["FE9_BLENDER"], None, 4.0)
            script = Path(folder) / "drive.py"
            script.write_text(drive, encoding="utf-8")
            blender.stage_addon(Path(folder) / "addon")
            run = subprocess.run([os.environ["FE9_BLENDER"], "-b", "--factory-startup", str(kit), "--python",
                                  str(script), "--", str(Path(folder) / "addon")], capture_output=True, text=True)
        line = next((line for line in run.stdout.splitlines() if line.startswith("WATERPANEL ")), None)
        self.assertIsNotNone(line, run.stdout[-2000:] + run.stderr[-2000:])
        result = json.loads(line[len("WATERPANEL "):])
        self.assertEqual(result["level"], 4.0)
        self.assertEqual(result["cut"], ["FINISHED"])
        self.assertEqual(result["fade"], ["FINISHED"])
        self.assertEqual(result["scroll"][:2], [0.0, -2.0])  # drifting south (+z) at 2
        self.assertEqual(result["waves"][0], ["FINISHED"])
        self.assertGreater(result["waves"][1], 100)
        self.assertEqual(result["check"], [["FINISHED"], "0 water tiles without a surface (red)"])


if __name__ == "__main__":
    unittest.main()
