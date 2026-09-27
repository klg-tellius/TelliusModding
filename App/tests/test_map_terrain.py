import io
import os
import sys
import unittest
from pathlib import Path

import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from fe_modding.formats import gltf_import, gs_file, map_file, tpl
from fe_modding.gui import model_viewer as mv
from test_formats import _build_map_object, _quad_glb


class UnsavedMapTerrainTests(unittest.TestCase):
    """The Build tab exports and imports the terrain of its open map, whose
    files may differ from the saved map.cmp (here there is none at all)."""

    def _map(self):
        from fe_modding.formats import pak, skeleton
        from test_map_heights import _map_bin

        texpack = tpl.build_tpl([(Image.new("RGBA", (8, 8), (0, 255, 0, 255)), tpl.FORMAT_CMPR)])
        scene = gltf_import.read_gltf(_quad_glb(translation=(5.0, 0.0, 5.0), with_texture=False), Path("."))
        ground = gltf_import.build_static_gs(scene, bone=0, bone_world=skeleton.IDENTITY_3X4, name="flat", tex_id_base=0,
                                             extra_textures=(gs_file.GsTexture((1, 0), 0, (257, 0, 0, 0, 0), 1.0, 1.0, 0),))
        files = {"map.bin": _map_bin(), "texpack.tpl": texpack, "flat.gs": gs_file.write_gs(ground.gs)}
        entries = [pak.PakEntry(name, 0, 0) for name in files]
        return entries, files

    def test_export_and_import_use_the_given_contents(self):
        import tempfile

        entries, files = self._map()
        path = Path("zmap") / "flat" / "map.cmp"  # never read: the contents are passed
        glb = mv.export_map_terrain_glb(path, files)
        self.assertEqual(glb[:4], b"glTF")
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "ground.glb"
            source.write_bytes(_quad_glb(translation=(5.0, 1.0, 5.0)))
            before = dict(files)
            result = mv.replace_map_terrain_with_glb(path, source, contents=(entries, files))
        self.assertEqual(files, before)  # the open map is left alone until the review is accepted
        new_entries, new_files = mv._unpack(path, result.outputs[path])
        self.assertEqual([e.name for e in new_entries], [e.name for e in entries])
        self.assertNotEqual(new_files["flat.gs"], files["flat.gs"])
        terrain = map_file.read_map_bytes(new_files["map.bin"]).build_desc[0]
        self.assertEqual((terrain.filename, terrain.offset_y), ("flat", 1.0))


class TplAppendTests(unittest.TestCase):
    def test_existing_images_keep_bytes_and_index(self):
        red = Image.new("RGBA", (16, 8), (255, 0, 0, 255))
        grey = Image.new("RGBA", (8, 8), (90, 90, 90, 255))
        base = tpl.build_tpl([(red, tpl.FORMAT_CMPR), (grey, tpl.FORMAT_RGB565)])
        before = tpl.read_tpl_images(io.BytesIO(base))

        white = Image.new("RGBA", (8, 8), (255, 255, 255, 255))
        blue = Image.new("RGBA", (32, 32), (0, 0, 255, 255))
        data, first = tpl.append_images(base, [(blue, tpl.FORMAT_CMPR, tpl.WRAP_REPEAT), (white, tpl.FORMAT_I4, tpl.WRAP_CLAMP)])

        self.assertEqual(first, 2)
        after = tpl.read_tpl_images(io.BytesIO(data))
        self.assertEqual(len(after), 4)
        for old, new in zip(before, after):
            self.assertEqual(old.tobytes(), new.tobytes())
        self.assertEqual(after[3].convert("RGBA").getpixel((2, 2)), (255, 255, 255, 255))
        info = tpl.read_tpl_image_info(io.BytesIO(data))
        self.assertEqual([i.wrap_s for i in info], [tpl.WRAP_REPEAT, tpl.WRAP_REPEAT, tpl.WRAP_REPEAT, tpl.WRAP_CLAMP])
        self.assertTrue(all(i.data_addr % 32 == 0 for i in info))


class TerrainHelperTests(unittest.TestCase):
    def test_surface_heights_interpolate_and_take_the_top(self):
        low = mv._Triangle((0, 0, 0), (10, 0, 0), (0, 0, 10), (0, 1, 0), (0, 0, 0))
        slope = mv._Triangle((0, 0, 0), (10, 10, 0), (0, 0, 10), (0, 1, 0), (0, 0, 0))
        heights = mv.surface_heights([low, slope], [(2, 2), (20, 20)])
        self.assertAlmostEqual(heights[0], 2.0)
        self.assertTrue(heights[1] != heights[1])  # nan: nothing above

    def test_tactical_corners_start_at_the_panel_offset_inside_the_buffer(self):
        data = map_file.MapData(
            capacity=map_file.MapCapacity(x_size=8, y_size=6, build_desc_count=0, build_inst_count=0, scale_unit=2000.0),
            extra=map_file.MapExtra(panel_offset_x=10, panel_offset_y=4, half_x_size=4, half_y_size=3,
                                    texture_projection_extent_x2=64, grid_buffer=1, unused=(0, 0), unknown_tail=0),
        )
        corners = mv.map_tactical_corners(data)
        self.assertEqual(len(corners), 7 * 5)
        self.assertEqual(min(corners), (55.0, 25.0))
        self.assertEqual(max(corners), (85.0, 45.0))

    def test_terrain_name_prefers_the_folder_name_and_skips_water(self):
        terrain = _build_map_object(flag_bits_a=0xC0, filename="bmap09")
        water = _build_map_object(flag_bits_a=0xC0, filename="bmap09_water0")
        prop = _build_map_object(filename="tree_01")
        files = {"bmap09.gs": b"", "bmap09_water0.gs": b"", "tree_01.gs": b""}
        data = map_file.MapData(build_desc=[water, prop, terrain])
        self.assertEqual(mv.map_terrain_name(files, data, "bmap09"), "bmap09")
        self.assertEqual(mv.map_terrain_name(files, data, "other"), "bmap09")
        with self.assertRaises(gltf_import.GltfImportError):
            mv.map_terrain_name({"bmap09_water0.gs": b""}, data, "bmap09")


class StaticBuildTextureBaseTests(unittest.TestCase):
    def test_texture_ids_start_at_the_base_and_extra_records_follow(self):
        scene = gltf_import.read_gltf(_quad_glb())
        white = gs_file.GsTexture((1, 0), 9, (28192, 0, 0, 0, 0), 1.0, 1.0, 0)
        build = gltf_import.build_static_gs(scene, tex_id_base=7, extra_textures=(white,))
        self.assertEqual([t.tex_id for t in build.gs.materials[0].textures], [7, 9])
        self.assertEqual(len(build.images), 1)


class ConformToTilesTests(unittest.TestCase):
    def test_bump_inside_a_tile_is_flattened_onto_its_panels(self):
        from fe_modding import map_heights, terrain_conform

        # four triangles over [0, 10]^2 around a centre vertex raised to 3
        c = (5.0, 3.0, 5.0)
        corners = [(0.0, 0.0, 0.0), (10.0, 0.0, 0.0), (10.0, 0.0, 10.0), (0.0, 0.0, 10.0)]
        tris = []
        for k in range(4):
            a, b = corners[k], corners[(k + 1) % 4]
            tris.append(gltf_import.ImportedTriangle(positions=(a, c, b), normals=((0, 1, 0),) * 3,
                                                     uvs=((a[0] / 10, a[2] / 10), (0.5, 0.5), (b[0] / 10, b[2] / 10))))
        scene = gltf_import.ImportedScene(materials=[gltf_import.ImportedMaterial("ground")], triangles={0: tris})
        cut = terrain_conform.conform_to_tiles(scene, 0.0, 10.0, 0.0, 10.0)
        self.assertGreater(cut, 0)
        out = scene.triangles[0]
        ys = {round(p[1], 6) for t in out for p in t.positions}
        # the centre is a tile corner (surface height 3), so panels meet there
        self.assertEqual(ys, {0.0, 3.0})
        for t in out:  # UVs follow position (u = x / 10, v = z / 10)
            for p, uv in zip(t.positions, t.uvs):
                self.assertAlmostEqual(uv[0], p[0] / 10, places=5)
                self.assertAlmostEqual(uv[1], p[2] / 10, places=5)
        arr = np.array([t.positions for t in out])
        probe = map_heights.surface_heights(arr, [(4.0, 4.0), (7.5, 1.0)])
        self.assertAlmostEqual(probe[0], 1.8, places=5)  # tile (0, 0)'s upper half: plane through 0, 0 and 3
        self.assertAlmostEqual(probe[1], 0.6, places=5)

    def test_triangles_outside_the_area_are_untouched(self):
        from fe_modding import terrain_conform

        tri = gltf_import.ImportedTriangle(positions=((20, 1, 20), (30, 1, 20), (20, 1, 30)), normals=((0, 1, 0),) * 3,
                                           uvs=((0, 0), (1, 0), (0, 1)))
        scene = gltf_import.ImportedScene(materials=[gltf_import.ImportedMaterial("g")], triangles={0: [tri]})
        self.assertEqual(terrain_conform.conform_to_tiles(scene, 0.0, 10.0, 0.0, 10.0), 0)
        self.assertIs(scene.triangles[0][0], tri)


class TplTruncateTests(unittest.TestCase):
    def test_truncate_keeps_leading_images_and_shrinks(self):
        images = [(Image.new("RGBA", (32, 32), (i * 60, 0, 0, 255)), tpl.FORMAT_CMPR) for i in range(4)]
        data = tpl.build_tpl(images)
        before = tpl.read_tpl_images(io.BytesIO(data))
        cut = tpl.truncate_images(data, 2)
        after = tpl.read_tpl_images(io.BytesIO(cut))
        self.assertEqual(len(after), 2)
        self.assertLess(len(cut), len(data))
        self.assertEqual([a.tobytes() for a in before[:2]], [b.tobytes() for b in after])

    def test_select_keeps_chosen_images_in_order(self):
        images = [(Image.new("RGBA", (32, 32), (i * 60, 0, 0, 255)), tpl.FORMAT_CMPR) for i in range(4)]
        data = tpl.build_tpl(images)
        before = tpl.read_tpl_images(io.BytesIO(data))
        kept = tpl.select_images(data, [1, 3])
        after = tpl.read_tpl_images(io.BytesIO(kept))
        self.assertEqual([b.tobytes() for b in after], [before[1].tobytes(), before[3].tobytes()])
        whole = tpl.read_tpl_images(io.BytesIO(tpl.select_images(data, range(4))))
        self.assertEqual([b.tobytes() for b in whole], [a.tobytes() for a in before])

@unittest.skipUnless(os.environ.get("FE9_EXTRACTED_FILES"), "set FE9_EXTRACTED_FILES to an extracted files/ directory")
class DiscMapTexturingTests(unittest.TestCase):
    def test_prologue_terrain_round_trip_keeps_map_texturing(self):
        import shutil
        import tempfile

        from fe_modding import map_props
        from fe_modding.formats import gs_file
        from fe_modding.gui import model_viewer as mv

        tmp = Path(tempfile.mkdtemp())
        src = tmp / "bmap01" / "map.cmp"
        src.parent.mkdir()
        shutil.copy2(Path(os.environ["FE9_EXTRACTED_FILES"]) / "zmap" / "bmap01" / "map.cmp", src)
        glb = tmp / "terrain.glb"
        glb.write_bytes(mv.export_map_terrain_glb(src))
        _e, before = map_props.read_map_container(src)
        result = mv.replace_map_terrain_with_glb(src, glb, conform=True, map_texturing=True, keep_light=True)
        out = tmp / "out.cmp"
        out.write_bytes(result.outputs[src])
        _e, after = map_props.read_map_container(out)
        self.assertEqual(after["texpack.tpl"], before["texpack.tpl"])
        material = gs_file.read_gs(after["bmap01.gs"]).materials[0]
        self.assertEqual(material.name, "map_base")
        self.assertEqual([t.tex_id for t in material.textures],
                         [t.tex_id for t in gs_file.read_gs(before["bmap01.gs"]).materials[0].textures])
        self.assertEqual({c.attr_mask for lst in gs_file.read_gs(after["bmap01.gs"]).chunk_lists for c in lst}, {0xC600})



if __name__ == "__main__":
    unittest.main()
