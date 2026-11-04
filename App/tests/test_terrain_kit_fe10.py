"""The terrain and water kits on Radiant Dawn maps (``FE10_EXTRACTED_FILES``).

RD map objects carry no base-terrain flag: the ground and water planes are
found by their ``map_base`` / ``map_wall`` / ``map_water`` materials
(``map_file.is_base_terrain_object``)."""

from __future__ import annotations

import os
import shutil
import tempfile
import unittest
from pathlib import Path

from fe_modding import map_props, terrain_kit
from fe_modding.formats import map_file

FILES = os.environ.get("FE10_EXTRACTED_FILES")


def _copy(folder: str, name: str) -> Path:
    container = Path(folder) / "zmap" / name / "map.cmp"
    container.parent.mkdir(parents=True)
    shutil.copy(Path(FILES) / "zmap" / name / "map.cmp", container)
    return container


@unittest.skipUnless(FILES, "set FE10_EXTRACTED_FILES to an extracted Radiant Dawn files/ directory")
class RdBaseTerrainTests(unittest.TestCase):
    def test_ground_and_water_are_found_by_material(self):
        _entries, files = map_props.read_map_container(Path(FILES) / "zmap" / "bmap0101" / "map.cmp")
        data = map_file.read_map_bytes(files["map.bin"])
        base = {o.filename for o in data.build_desc if map_file.is_base_terrain_object(o, files)}
        self.assertEqual(base, {"bmap0101", "bmap0101_water0"})
        # without the models an RD record never claims to be terrain (its A6 bit means "hidden")
        self.assertFalse(any(map_file.is_base_terrain_object(o) for o in data.build_desc))
        props = map_props.prop_names(files, data)
        self.assertNotIn("bmap0101", props)
        self.assertIn("house_day09", props)
        self.assertEqual(map_props.water_names(files, data), ["bmap0101_water0"])

    def test_a_map_reusing_another_maps_ground(self):
        # 3-8 draws 3-7's ground model under its own folder name
        _entries, files = map_props.read_map_container(Path(FILES) / "zmap" / "bmap0308" / "map.cmp")
        data = map_file.read_map_bytes(files["map.bin"])
        from fe_modding.gui import model_viewer as mv
        self.assertEqual(mv.map_terrain_name(files, data, "bmap0308"), "bmap0307")

    def test_a_map_without_a_ground_model_says_so(self):
        from fe_modding.formats import gltf_import
        with tempfile.TemporaryDirectory() as folder:
            with self.assertRaisesRegex(gltf_import.GltfImportError, "no ground model"):
                terrain_kit.read_terrain(_copy(folder, "bmap0103"))  # an indoor map built from props


@unittest.skipUnless(FILES, "set FE10_EXTRACTED_FILES to an extracted Radiant Dawn files/ directory")
class RdKitTests(unittest.TestCase):
    def test_kit_reads_terrain_paint_and_projection(self):
        with tempfile.TemporaryDirectory() as folder:
            source = terrain_kit.read_terrain(_copy(folder, "bmap0101"))
        self.assertEqual(source.terrain, "bmap0101")
        self.assertIsNotNone(source.light_matrix)
        self.assertIsNotNone(source.playable)
        layout = terrain_kit.detect_layout(source)
        paint = terrain_kit.kit_paint(source, layout, source.atlas, False)
        self.assertEqual(len(paint.layers), 1)  # 1-1 is a paved town: its blend mask is almost empty
        with tempfile.TemporaryDirectory() as folder:
            source = terrain_kit.read_terrain(_copy(folder, "bmap0204"))
        paint = terrain_kit.kit_paint(source, terrain_kit.detect_layout(source), source.atlas, False)
        self.assertGreater(len(paint.layers), 3)

    def test_painted_import_rebuilds_the_terrain(self):
        from fe_modding.gui import model_viewer as mv

        with tempfile.TemporaryDirectory() as folder:
            container = _copy(folder, "bmap0101")
            source = terrain_kit.read_terrain(container)
            table, atlas, custom = terrain_kit.load_layout(source, None, "bmap0101")
            data = terrain_kit.kit_paint(source, table, atlas, custom, 512)
            glb = Path(folder) / "terrain.glb"
            glb.write_bytes(mv.export_map_terrain_glb(container))
            result = mv.replace_map_terrain_with_glb(container, glb, True, True, True, None, False,
                                                     paint=data, light=data.light)
            self.assertEqual(list(result.outputs), [container])
            self.assertIn("Game", result.previews)
            self.assertTrue(any("Painted texturing" in w for w in result.warnings))
            # the rewritten map still reads with Radiant Dawn's section names
            _entries, files = map_props.read_map_container(container)
            out = map_file.read_map_bytes(files["map.bin"])
            self.assertEqual(map_file.map_layout(files["map.bin"]).prefix, "bmap0101:")
            self.assertIsNotNone(out.capacity)
            self.assertIsNotNone(terrain_kit.read_terrain(container).light_matrix)

    def test_water_reads_and_untouched_water_changes_nothing(self):
        with tempfile.TemporaryDirectory() as folder:
            water = terrain_kit.read_water(_copy(folder, "bmap0101"))
        self.assertEqual([b.name for b in water.bodies], ["bmap0101_water0"])
        entries, files = map_props.read_map_container(Path(FILES) / "zmap" / "bmap0101" / "map.cmp")
        before = dict(files)
        edit = terrain_kit.WaterEdit(water.bodies, [], water.fade, False, water.waves, water.origin)
        outcome = terrain_kit.apply_water(entries, files, edit)
        self.assertEqual({k for k in files if files[k] != before.get(k)}, set())
        self.assertIn("0 of 1 water surfaces rebuilt, 0 removed.", outcome.notes)

    def test_story_maps_with_a_ground_model_all_read(self):
        read = failed = 0
        for folder in sorted((Path(FILES) / "zmap").glob("bmap*")):
            container = folder / "map.cmp"
            if not container.exists():
                continue
            _entries, files = map_props.read_map_container(container)
            data = map_file.read_map_bytes(files["map.bin"])
            if not any(map_file.is_base_terrain_object(o, files) and "water" not in o.filename.lower()
                       for o in data.build_desc):
                continue  # floors built from props only (indoor, desert, tower)
            try:
                terrain_kit.read_terrain(container)
                read += 1
            except Exception:  # noqa: BLE001
                failed += 1
        self.assertEqual(failed, 0)
        self.assertEqual(read, 33)


if __name__ == "__main__":
    unittest.main()
