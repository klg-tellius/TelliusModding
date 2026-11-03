"""Blender discovery and headless export orchestration, without Blender."""

import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fe_modding import blender


class FindTests(unittest.TestCase):
    def test_configured_path_wins_and_must_exist(self):
        exists = lambda path: Path(path) == Path("/tools/blender.exe")  # noqa: E731
        self.assertEqual(
            blender.find_blender("/tools/blender.exe", is_file=exists),
            Path("/tools/blender.exe"),
        )
        self.assertIsNone(blender.find_blender("/missing.exe", is_file=exists))

    def test_path_lookup_is_used_when_no_setting_exists(self):
        found = blender.find_blender(
            None,
            environ={},
            is_file=lambda path: False,
            which=lambda name: "/usr/bin/blender" if name == "blender" else None,
        )
        self.assertEqual(found, Path("/usr/bin/blender"))


class ExportTests(unittest.TestCase):
    def test_export_writes_inputs_runs_headless_and_requires_output(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            executable = root / "blender.exe"
            executable.write_bytes(b"exe")
            target = root / "map.blend"
            matrix = ((1.0, 0.0, 0.0, 0.25), (0.0, 0.0, 1.0, 0.5), (0.0, 0.0, 0.0, 1.0))
            material = blender.TerrainMaterial(
                "map_base",
                Image.new("RGBA", (2, 2), "red"),
                Image.new("RGBA", (2, 2), "grey"),
                Image.new("RGBA", (2, 2), "white"),
                matrix,
                matrix,
            )
            observed = {}

            def run(args, **kwargs):
                observed["args"] = args
                observed["kwargs"] = kwargs
                separator = args.index("--")
                glb, manifest, output = map(Path, args[separator + 1:])
                observed["glb"] = glb.read_bytes()
                observed["manifest"] = json.loads(manifest.read_text(encoding="utf-8"))
                self.assertIn("ShaderNodeMixRGB", Path(args[args.index("--python") + 1]).read_text(encoding="utf-8"))
                output.write_bytes(b"BLENDER")
                return SimpleNamespace(returncode=0, stdout="", stderr="")

            self.assertEqual(
                blender.export_blend(b"glTF", [material], target, executable, run=run),
                target.resolve(),
            )
            self.assertEqual(observed["glb"], b"glTF")
            record = observed["manifest"]["materials"][0]
            self.assertEqual(record["name"], "map_base")
            self.assertEqual(record["selector_matrix"][0][3], 0.25)
            self.assertEqual(record["selector_matrix"][1][:3], [0.0, -1.0, 0.0])
            self.assertEqual(observed["args"][1:4], ["--background", "--factory-startup", "--disable-autoexec"])
            self.assertTrue(observed["kwargs"]["capture_output"])
            self.assertEqual(target.read_bytes(), b"BLENDER")

    def test_failure_reports_blender_output(self):
        with tempfile.TemporaryDirectory() as folder:
            executable = Path(folder) / "blender.exe"
            executable.write_bytes(b"exe")
            with self.assertRaisesRegex(blender.BlenderError, "bad material"):
                blender.export_blend(
                    b"glTF", [], Path(folder) / "missing.blend", executable,
                    run=lambda *args, **kwargs: SimpleNamespace(returncode=1, stdout="", stderr="bad material"),
                )

    def test_model_export_tags_collection_and_packs_file(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            executable = root / "blender.exe"
            executable.write_bytes(b"exe")
            target = root / "fighter.blend"
            observed = {}

            def run(args, **kwargs):
                separator = args.index("--")
                glb, output, model_name = args[separator + 1:]
                observed["glb"] = Path(glb).read_bytes()
                observed["model_name"] = model_name
                script = Path(args[args.index("--python") + 1]).read_text(encoding="utf-8")
                self.assertIn('collection["fe9_model_collection"] = True', script)
                self.assertIn("bpy.ops.file.pack_all()", script)
                Path(output).write_bytes(b"BLENDER MODEL")
                return SimpleNamespace(returncode=0, stdout="", stderr="")

            self.assertEqual(
                blender.export_model_blend(b"model glTF", target, executable, "ymu/lord", run=run),
                target.resolve(),
            )
            self.assertEqual(observed["glb"], b"model glTF")
            self.assertEqual(observed["model_name"], "ymu/lord")

    def test_blend_import_exports_only_the_tagged_terrain_to_glb(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            executable = root / "blender.exe"
            executable.write_bytes(b"exe")
            source = root / "map.blend"
            source.write_bytes(b"BLENDER")
            observed = {}

            def run(args, **kwargs):
                observed["args"] = args
                separator = args.index("--")
                blend_path, output, terrain_name = args[separator + 1:]
                self.assertEqual(Path(blend_path), source.resolve())
                self.assertEqual(terrain_name, "bmap01")
                script = Path(args[args.index("--python") + 1]).read_text(encoding="utf-8")
                self.assertIn('obj.get("fe9_map_terrain")', script)
                Path(output).write_bytes(b"glTF result")
                return SimpleNamespace(returncode=0, stdout="", stderr="")

            self.assertEqual(
                blender.blend_to_glb(source, "bmap01", executable, run=run),
                b"glTF result",
            )
            self.assertTrue(observed["args"][0].endswith("blender.exe"))

    def test_model_blend_import_exports_tagged_collection_to_glb(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            executable = root / "blender.exe"
            executable.write_bytes(b"exe")
            source = root / "fighter.blend"
            source.write_bytes(b"BLENDER")

            def run(args, **kwargs):
                separator = args.index("--")
                blend_path, output = args[separator + 1:]
                self.assertEqual(Path(blend_path), source.resolve())
                script = Path(args[args.index("--python") + 1]).read_text(encoding="utf-8")
                self.assertIn('collection.get("fe9_model_collection")', script)
                self.assertIn("export_animations=True", script)
                Path(output).write_bytes(b"model glTF result")
                return SimpleNamespace(returncode=0, stdout="", stderr="")

            self.assertEqual(
                blender.model_blend_to_glb(source, executable, run=run),
                b"model glTF result",
            )


if __name__ == "__main__":
    unittest.main()
