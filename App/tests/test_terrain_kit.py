"""Terrain kits: paint data I/O, compiling onto an import, Blender orchestration."""

import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fe_modding import blender, terrain_kit
from fe_modding import terrain_paint as tp
from fe_modding.formats import gltf_import


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

    def test_unused_cells_become_swatches(self):
        table = layout()
        added = terrain_kit.add_unused_cells(table)
        # the bottom half has 4 x 4 cells of 128; the road takes one
        self.assertEqual(added, 15)
        self.assertEqual(terrain_kit.add_unused_cells(table), 0)

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
            self.assertEqual(saved, layout())
            self.assertTrue(custom)
            self.assertEqual(atlas.getpixel((0, 0)), (255, 0, 0, 255))
            terrain_kit.save_layout(project, "bmap01", layout(), clear_custom=True)
            self.assertFalse(terrain_kit.custom_atlas_path(project, "bmap01").exists())


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
    def test_addon_ships_the_shared_compiler(self):
        files = blender.addon_files()
        self.assertIn("__init__.py", files)
        self.assertIn("kit.py", files)
        self.assertEqual(files["terrain_paint.py"], blender.ADDON_SHARED.read_bytes())
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


if __name__ == "__main__":
    unittest.main()
