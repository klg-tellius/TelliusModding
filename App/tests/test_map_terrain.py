import io
import os
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from fe_modding.formats import gltf_export, gltf_import, gs_file, map_file, tpl
from fe_modding.gui import model_viewer as mv
from test_formats import _build_map_object, _quad_glb


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

    def test_export_object_choices_are_modeled_unique_and_exclude_the_land(self):
        terrain = _build_map_object(flag_bits_a=0xC0, filename="bmap09")
        water = _build_map_object(flag_bits_a=0xC0, filename="bmap09_water0")
        tree = _build_map_object(filename="tree_01")
        marker = _build_map_object(filename="logic_only")
        data = map_file.MapData(build_desc=[terrain, water, tree, tree, marker])
        files = {"bmap09.gs": b"", "bmap09_water0.gs": b"", "tree_01.gs": b""}

        self.assertEqual(mv.map_export_object_names(files, data, "bmap09"), ["bmap09_water0", "tree_01"])

    def test_projected_map_materials_require_one_shared_atlas(self):
        material = lambda *ids: SimpleNamespace(textures=[SimpleNamespace(tex_id=i) for i in ids])
        self.assertEqual(mv._shared_map_atlas([material(12, 13), material(12, 13)]), 12)

        for incompatible in ([material(12, 13), material(14, 15)], [material(12, 13), material(99)]):
            with self.subTest(incompatible=incompatible), self.assertRaises(gltf_import.GltfImportError) as raised:
                mv._shared_map_atlas(incompatible)
            self.assertIn("turn off 'Keep map texturing'", str(raised.exception))
            self.assertIn("custom texture", str(raised.exception))

    def test_blender_preview_bake_combines_both_uvs_mask_and_light(self):
        vertex = lambda position, uv, uv2: SimpleNamespace(position=position, uv=uv, uv2=uv2)
        tri = (
            vertex((0.0, 0.0, 0.0), (0.1, 0.1), (0.6, 0.1)),
            vertex((1.0, 0.0, 0.0), (0.1, 0.1), (0.6, 0.1)),
            vertex((0.0, 0.0, 1.0), (0.1, 0.1), (0.6, 0.1)),
        )
        atlas = Image.new("RGBA", (10, 2), (200, 0, 0, 255))
        for x in range(5, 10):
            for y in range(2):
                atlas.putpixel((x, y), (0, 100, 0, 255))
        mask = Image.new("RGBA", (2, 2), (128, 128, 128, 255))
        light = Image.new("RGBA", (2, 2), (128, 128, 128, 255))
        identity_projection = ((0.0, 0.0, 0.0, 0.0), (0.0, 0.0, 0.0, 0.0),
                               (0.0, 0.0, 0.0, 1.0))
        baked, display_uvs = gltf_export._bake_map_texture(
            [tri], atlas, mask, light,
            gltf_export.MapTextureBake(identity_projection, identity_projection),
        )
        # Half red/half green, then half-light: approximately (50, 25, 0).
        r, g, b, a = baked.getpixel((baked.width // 2, baked.height // 2))
        self.assertTrue(48 <= r <= 52 and 24 <= g <= 27)
        self.assertEqual((b, a), (0, 255))
        self.assertEqual(len(display_uvs), 1)


class StaticBuildTextureBaseTests(unittest.TestCase):
    def test_texture_ids_start_at_the_base_and_extra_records_follow(self):
        scene = gltf_import.read_gltf(_quad_glb())
        white = gs_file.GsTexture((1, 0), 9, (28192, 0, 0, 0, 0), 1.0, 1.0, 0)
        build = gltf_import.build_static_gs(scene, tex_id_base=7, extra_textures=(white,))
        self.assertEqual([t.tex_id for t in build.gs.materials[0].textures], [7, 9])
        self.assertEqual(len(build.images), 1)

    def test_untextured_terrain_colour_is_baked_into_an_image(self):
        scene = gltf_import.ImportedScene(
            materials=[gltf_import.ImportedMaterial("map_base", (0.25, 0.0, 0.5, 1.0))],
            triangles={},
        )
        self.assertEqual(mv._bake_untextured_material_colors(scene), ["map_base"])
        material = scene.materials[0]
        self.assertEqual(material.image.getpixel((0, 0)), (64, 0, 128, 255))
        self.assertEqual(material.base_color, (1.0, 1.0, 1.0, 1.0))


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
    def test_bmap16_export_is_only_map_gs_and_embeds_all_its_textures(self):
        import json
        import struct

        source = Path(os.environ["FE9_EXTRACTED_FILES"]) / "zmap" / "bmap16" / "map.cmp"
        _entries, files = mv._read_container(source)
        source_model = mv.model_fmt.read_model_bytes(files["bmap16.gs"])
        glb = mv.export_map_terrain_glb(source)
        json_length = struct.unpack_from("<I", glb, 12)[0]
        doc = json.loads(glb[20 : 20 + json_length])
        mesh_names = {mesh["name"] for mesh in doc["meshes"]}
        image_names = {image.get("name") for image in doc.get("images", [])}
        exported_indices = sum(
            doc["accessors"][primitive["indices"]]["count"]
            for mesh in doc["meshes"] for primitive in mesh["primitives"]
        )
        source_triangles = sum(
            len(strip) - 2 for chunk in source_model.chunks if not chunk.hidden for strip in chunk.strips
        )
        self.assertEqual(mesh_names, {"bmap16"})
        self.assertNotIn("castle_desart_01", mesh_names)
        self.assertTrue({"tex_0", "tex_1", "tex_6"}.issubset(image_names))
        self.assertTrue(any(name and name.startswith("fe9_baked_terrain_") for name in image_names))
        terrain_primitive = next(
            primitive for primitive in doc["meshes"][0]["primitives"]
            if "TEXCOORD_2" in primitive["attributes"]
        )
        terrain_material = doc["materials"][terrain_primitive["material"]]
        self.assertEqual(terrain_material["pbrMetallicRoughness"]["baseColorTexture"].get("texCoord"), 2)
        self.assertEqual(exported_indices, source_triangles * 3)

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
