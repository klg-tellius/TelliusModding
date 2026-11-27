import io
import os
import sys
import unittest
from dataclasses import replace
from pathlib import Path

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from fe_modding import map_props
from fe_modding.formats import gs_file, map_file, pak, tpl
from test_formats import _quad_glb
from test_map_heights import _map_bin


def _files():
    texpack = tpl.build_tpl([(Image.new("RGBA", (8, 8), (0, 255, 0, 255)), tpl.FORMAT_CMPR)])
    files = {"map.bin": _map_bin(), "texpack.tpl": texpack, "tree.g": b"skeleton"}
    entries = [pak.PakEntry(name, 0, 0) for name in files]
    return entries, files


class MapPropTests(unittest.TestCase):
    def test_import_can_scale_widest_side_to_tiles(self):
        entries, files = _files()
        warnings = map_props.import_prop(
            entries, files, _quad_glb(translation=(2.5, 0.0, 2.5)), "stone", scale_tiles=3)
        stone = map_file.read_map_bytes(files["map.bin"]).build_desc[2]
        self.assertAlmostEqual(max(stone.size_x - stone.offset_x, stone.size_z - stone.offset_z), 15.0)
        self.assertTrue(any("3 tiles" in warning for warning in warnings))

    def test_import_place_replace_and_remove(self):
        entries, files = _files()
        warnings = map_props.import_prop(entries, files, _quad_glb(translation=(2.5, 0.0, 2.5)), "stone")
        self.assertEqual(warnings, [])
        data = map_file.read_map_bytes(files["map.bin"])
        self.assertEqual([o.filename for o in data.build_desc], ["flat", "tree", "stone"])
        stone = data.build_desc[2]
        self.assertEqual((stone.offset_x, stone.size_x, stone.flag_bits_c), (1.5, 3.5, 1))
        self.assertEqual(data.capacity.build_desc_count, 3)
        self.assertEqual(files["stone.g"], b"skeleton")
        self.assertIn("stone.gs", [e.name for e in entries])
        # image 0 is used by no model here, so the import's compaction drops it
        self.assertEqual(len(tpl.read_tpl_image_info(io.BytesIO(files["texpack.tpl"]))), 1)
        self.assertEqual(map_props.used_texture_ids(files), {0})
        self.assertEqual(map_props.prop_names(files, data), ["stone"])

        index = map_props.place_prop(files, "stone", 1, 0, 64)
        placed = map_file.read_map_bytes(files["map.bin"])
        self.assertEqual(placed.capacity.build_inst_count, 3)
        inst = placed.build_inst[index]
        self.assertEqual((inst.x, inst.y, inst.angle & 0xFF, inst.desc_index), (1, 0, 64, 2))
        self.assertEqual(inst.height(), 0.0)  # no terrain model: ground level

        # the same name replaces the model; its old image goes, the new one takes its place
        map_props.import_prop(entries, files, _quad_glb(translation=(12.5, 1.0, 2.5)), "stone")
        self.assertEqual(len(tpl.read_tpl_image_info(io.BytesIO(files["texpack.tpl"]))), 1)
        again = map_file.read_map_bytes(files["map.bin"])
        self.assertEqual(len(again.build_desc), 3)
        self.assertEqual(again.build_desc[2].offset_y, 1.0)
        self.assertEqual((again.build_inst[index].x2, again.build_inst[index].y2,
                          again.build_inst[index].end_x2, again.build_inst[index].end_y2), (1, 0, 1, 2))

        map_props.remove_instance(files, index)
        self.assertEqual(map_file.read_map_bytes(files["map.bin"]).capacity.build_inst_count, 2)

    def test_move_and_rotate_instance(self):
        entries, files = _files()
        map_props.import_prop(entries, files, _quad_glb(translation=(2.5, 0.0, 2.5)), "stone")
        index = map_props.place_prop(files, "stone", 1, 0, 0)
        before = map_file.read_map_bytes(files["map.bin"]).build_inst[index]
        rect = (before.x2 - before.x, before.y2 - before.y, before.end_x2 - before.x, before.end_y2 - before.y)

        map_props.move_instance(files, index, 3, 2)
        moved = map_file.read_map_bytes(files["map.bin"]).build_inst[index]
        self.assertEqual((moved.x, moved.y, moved.desc_index), (3, 2, before.desc_index))
        self.assertEqual((moved.x2 - 3, moved.y2 - 2, moved.end_x2 - 3, moved.end_y2 - 2), rect)
        self.assertEqual(moved.height(), before.height())  # flat ground: same height

        map_props.rotate_instance(files, index, 128)
        turned = map_file.read_map_bytes(files["map.bin"]).build_inst[index]
        self.assertEqual((turned.x, turned.y, turned.angle & 0xFF), (3, 2, 128))
        self.assertEqual(map_file.read_map_bytes(files["map.bin"]).capacity.build_inst_count, 3)

    def test_props_stand_on_the_ground_layer(self):
        # a ship's deck: the ground panel layer is 5 units up while no terrain mesh is under it
        # (bmap13: deck 16.1, sea floor below), so a chest put there must stand on the deck
        entries, files = _files()
        files["map.bin"] = _map_bin(width=4, height=4, panel_elevation=-2000)
        map_props.import_prop(entries, files, _quad_glb(translation=(2.5, 0.0, 2.5)), "stone")
        data = map_file.read_map_bytes(files["map.bin"])
        self.assertEqual(map_props.standing_heights(files, data, [(1, 1)]), [-1.0])
        index = map_props.place_prop(files, "stone", 1, 1)
        self.assertEqual(map_file.read_map_bytes(files["map.bin"]).build_inst[index].height(), -1.0)
        map_props.move_instance(files, index, 2, 3)
        self.assertEqual(map_file.read_map_bytes(files["map.bin"]).build_inst[index].height(), -1.0)

    def test_compaction_drops_middle_images_and_renumbers(self):
        entries, files = _files()
        map_props.import_prop(entries, files, _quad_glb(translation=(2.5, 0.0, 2.5)), "stone")
        map_props.import_prop(entries, files, _quad_glb(translation=(2.5, 0.0, 2.5)), "rock")
        rock_image = tpl.read_tpl_images(io.BytesIO(files["texpack.tpl"]))[1].tobytes()
        # the stone's image sits before the rock's; replacing the stone with an
        # untextured model leaves it unused in the middle
        del files["stone.gs"]
        removed, saved = map_props.compact_texpack(files)
        self.assertEqual((removed, saved > 0), (1, True))
        images = tpl.read_tpl_images(io.BytesIO(files["texpack.tpl"]))
        self.assertEqual(len(images), 1)
        self.assertEqual(images[0].tobytes(), rock_image)
        self.assertEqual(map_props.used_texture_ids(files), {0})
        self.assertEqual(map_props.compact_texpack(files), (0, 0))

    def test_instance_footprint_follows_the_quarter_turn(self):
        wide = map_file.MapObject(0, 0, 0, 15.0, 1.0, 10.0, 0, 0, 1, 0, "wall")  # 3 x 2 tiles
        expected = {0: (5, 5, 7, 6), 64: (4, 5, 5, 7), 128: (3, 4, 5, 5), 192: (5, 3, 6, 5)}
        for angle, rect in expected.items():
            record = map_file.instance_record(wide, 0, 5, 5, angle, 0.0)
            self.assertEqual(tuple(record[4:8]), rect, angle)

    def test_switching_object_recomputes_footprint(self):
        _entries, files = _files()
        wide = map_file.MapObject(0, 0, 0, 15.0, 1.0, 10.0, 0, 0, 1, 0, "wall")
        files["map.bin"], desc_index = map_file.add_build_object(files["map.bin"], wide)
        before = map_file.read_map_bytes(files["map.bin"]).build_inst[1]
        map_props.set_instance_object(files, 1, desc_index)
        after = map_file.read_map_bytes(files["map.bin"]).build_inst[1]
        self.assertEqual((after.desc_index, after.x2, after.y2, after.end_x2, after.end_y2),
                         (desc_index, 0, 0, 2, 1))
        self.assertEqual(after.height(), before.height())

    def test_bad_names_are_refused(self):
        entries, files = _files()
        with self.assertRaises(Exception):
            map_props.import_prop(entries, files, _quad_glb(), "bad name")
        with self.assertRaises(Exception):
            map_props.import_prop(entries, files, _quad_glb(), "flat")

    def test_copy_prop_between_maps(self):
        source_entries, source = _files()
        map_props.import_prop(source_entries, source, _quad_glb(translation=(2.5, 0.0, 2.5)), "stone")
        entries, files = _files()
        before = tpl.image_keys(files["texpack.tpl"])

        self.assertEqual(map_props.copy_prop(source, "stone", entries, files), "stone")
        data = map_file.read_map_bytes(files["map.bin"])
        self.assertEqual([o.filename for o in data.build_desc], ["flat", "tree", "stone"])
        copied, original = data.build_desc[2], map_file.read_map_bytes(source["map.bin"]).build_desc[2]
        self.assertEqual(copied.__dict__ | {"address": 0}, original.__dict__ | {"address": 0})
        self.assertIn("stone.gs", [e.name for e in entries])
        # the image is added after the map's own, which stay as they were
        keys = tpl.image_keys(files["texpack.tpl"])
        self.assertEqual(keys[: len(before)], before)
        self.assertEqual(len(keys), len(before) + 1)
        self.assertEqual(map_props.used_texture_ids({"stone.gs": files["stone.gs"]}), {len(before)})
        self.assertTrue(map_props.same_prop(source, "stone", files, "stone"))
        map_props.place_prop(files, "stone", 1, 0)

        # a second copy under a free name shares the image
        name = map_props.free_prop_name(files, data, "stone")
        self.assertEqual(name, "stone_2")
        map_props.copy_prop(source, "stone", entries, files, name)
        self.assertEqual(len(tpl.image_keys(files["texpack.tpl"])), len(before) + 1)
        self.assertTrue(map_props.same_prop(source, "stone", files, "stone_2"))
        with self.assertRaises(map_file.MapFileError):
            map_props.copy_prop(source, "stone", entries, files)
        with self.assertRaises(map_file.MapFileError):
            map_props.copy_prop(source, "flat", entries, files, "other")

    def test_tile_corners_set_and_deduced(self):
        from fe_modding import map_heights

        entries, files = _files()
        files["map.bin"] = map_file.set_tile_terrains(files["map.bin"], {(0, 1): "forest"})
        terrains = map_file.terrain_grid(files["map.bin"])
        files["map.bin"] = map_heights.set_tile_corners(files["map.bin"], {(0, 1): {"combined": (-400, -400, 0, 0)}})
        data = map_file.read_map_bytes(files["map.bin"])
        self.assertEqual(map_heights.tile_corners(data, (0, 1)), {"combined": (-400, -400, 0, 0), "ground": (0, 0, 0, 0)})
        self.assertEqual(map_heights.tile_corners(data, (1, 1))["combined"], (0, 0, 0, 0))  # shared record left alone
        self.assertEqual(map_file.terrain_grid(files["map.bin"]), terrains)
        with self.assertRaises(map_file.MapFileError):
            map_heights.set_tile_corners(files["map.bin"], {(0, 1): {"ground": (0, 0, 0, 40000)}})

        # a prop vanilla doesn't know rises to its model's top; the tile next to it copies the ground
        map_props.import_prop(entries, files, _quad_glb(translation=(2.5, 1.0, 2.5)), "stone")
        map_props.place_prop(files, "stone", 1, 1)
        data = map_file.read_map_bytes(files["map.bin"])
        deduced = map_heights.deduce_corners(files, data, [(1, 1), (0, 1)])
        self.assertEqual(deduced[(1, 1)]["combined"], (-400,) * 4)
        self.assertEqual(deduced[(1, 1)]["ground"], (0,) * 4)  # no terrain model: the ground is kept
        self.assertEqual(deduced[(0, 1)]["combined"], (0,) * 4)

    def test_prop_rise_uses_the_vanilla_table(self):
        from fe_modding import map_heights
        from fe_modding.prop_heights import RISE

        obj = map_file.MapObject(0, 0, 0, 5, 6, 5, 0, 0, 1, 0, "tree_02")
        self.assertEqual(map_heights.prop_rise("tree_02", obj, 6.0), RISE["tree_02"])
        self.assertEqual(map_heights.prop_rise("tree_02_2", obj, 6.0), RISE["tree_02"])  # a copy
        self.assertEqual(map_heights.prop_rise("my_rock", obj, 3.0), 3.0)
        self.assertIsNone(map_heights.prop_rise("my_bush", replace(obj, flag_bits_c=0x43), 3.0))

    def test_copy_images_keeps_bytes(self):
        a = tpl.build_tpl([(Image.new("RGBA", (8, 8), (255, 0, 0, 255)), tpl.FORMAT_CMPR)])
        b = tpl.build_tpl([(Image.new("RGBA", (4, 4), c), tpl.FORMAT_RGB5A3) for c in ((0, 0, 255, 255), (9, 9, 9, 255))])
        merged, first = tpl.copy_images(a, b, [1])
        self.assertEqual(first, 1)
        self.assertEqual(tpl.image_keys(merged), [tpl.image_keys(a)[0], tpl.image_keys(b)[1]])
        self.assertEqual(tpl.read_tpl_images(io.BytesIO(merged))[1].getpixel((0, 0)), (8, 8, 8, 255))

@unittest.skipUnless(os.environ.get("FE9_EXTRACTED_FILES"), "set FE9_EXTRACTED_FILES to an extracted files/ directory")
class DiscWaterTests(unittest.TestCase):
    def test_water_round_trip_and_new_water(self):
        root = Path(os.environ["FE9_EXTRACTED_FILES"]) / "zmap"
        entries, files = map_props.read_map_container(root / "bmap01" / "map.cmp")
        self.assertEqual(map_props.water_terrain_mismatch(files), (0, 0))  # the river covers exactly the river tiles
        glb = map_props.export_prop_glb(files, "bmap01_water0")
        before = [t.tex_id for t in gs_file.read_gs(files["bmap01_water0.gs"]).materials[0].textures]
        self.assertEqual(map_props.import_water(entries, files, glb, "bmap01_water0"), [])
        material = gs_file.read_gs(files["bmap01_water0.gs"]).materials[0]
        self.assertEqual((material.name, [t.tex_id for t in material.textures]), ("map_water", before))

        _e, donor = map_props.read_map_container(root / "bmap01" / "map.cmp")
        dry_entries, dry = map_props.read_map_container(root / "bmap06" / "map.cmp")
        map_props.import_water(dry_entries, dry, glb, None, donor=donor)
        data = map_file.read_map_bytes(dry["map.bin"])
        self.assertEqual(map_props.water_names(dry, data), ["bmap06_water0"])
        self.assertTrue(data.extra.unknown_tail & map_props.MAP_FLAG_WATER)
        self.assertEqual(dry["bmap06_water0.ga"], donor["bmap01_water0.ga"])

@unittest.skipUnless(os.environ.get("FE9_EXTRACTED_FILES"), "set FE9_EXTRACTED_FILES to an extracted files/ directory")
class DiscAnimatedPropTests(unittest.TestCase):
    def test_animated_prop_round_trip_then_static_over_it(self):
        from fe_modding.formats import animation

        root = Path(os.environ["FE9_EXTRACTED_FILES"]) / "zmap"
        entries, files = map_props.read_map_container(root / "bmap11" / "map.cmp")
        glb = map_props.export_prop_glb(files, "candle_02")
        warnings = map_props.import_prop(entries, files, glb, "candle_new")
        self.assertTrue(any(w.startswith("Animated prop") for w in warnings))
        obj = next(o for o in map_file.read_map_bytes(files["map.bin"]).build_desc if o.filename == "candle_new")
        self.assertTrue(obj.flag_bits_c & map_props.FLAG_C_ANIMATED)
        anim = animation.read_animation_bytes(files["candle_new.ga"])
        self.assertEqual(anim.header.words[4], 1)  # loops
        self.assertTrue(anim.curves)

        map_props.import_prop(entries, files, _quad_glb(translation=(2.5, 0.0, 2.5)), "candle_new")
        obj = next(o for o in map_file.read_map_bytes(files["map.bin"]).build_desc if o.filename == "candle_new")
        self.assertFalse(obj.flag_bits_c & map_props.FLAG_C_ANIMATED)
        self.assertNotIn("candle_new.ga", files)
        self.assertNotIn("candle_new.ga", [e.name for e in entries])



def _door_map(footprint_bit=True, size=3):
    """A 3x3 map with a roof layer whose ``tree`` object is an openable door model."""
    data = _map_bin(width=size, height=size, roof_elevations=[0])
    parsed = map_file.read_map_bytes(data)
    data = map_file.patch_object_field(data, parsed.build_desc[1], "flag_bits_c", 0x13)
    if footprint_bit:
        data = map_file.patch_extra_field(data, parsed.extra, "unknown_tail", map_file.MAP_EXTRA_FOOTPRINT_MASK)
    return {"map.bin": data}


def _roof_terrain(files, x, y):
    parsed = map_file.read_map_bytes(files["map.bin"])
    return map_file.pointer_string(files["map.bin"], parsed.unique_panel_roof[parsed.panel_index_roof[x][y]].terrain_type_ptr)


def _terrain(files, x, y):
    return map_file.terrain_grid(files["map.bin"])[x][y]


class DoorTerrainTests(unittest.TestCase):
    """A closed door blocks its tiles through the roof layer's terrain (main.dol 0x80044450)."""

    def test_placed_door_gets_roof_door_terrain_and_keeps_its_floor(self):
        files = _door_map()
        self.assertEqual(_roof_terrain(files, 0, 0), "plain")  # the map's own door, never synced
        index = map_props.place_prop(files, "tree", 2, 1)
        self.assertEqual((_roof_terrain(files, 2, 1), _roof_terrain(files, 0, 0)), ("扉", "扉"))
        self.assertEqual(_terrain(files, 2, 1), "plain")  # combined layer: what the open door leaves
        self.assertEqual(_roof_terrain(files, 1, 1), "plain")
        parsed = map_file.read_map_bytes(files["map.bin"])
        roof = parsed.unique_panel_roof[parsed.panel_index_roof[2][1]]
        combined = parsed.unique_panel[parsed.panel_index[2][1]]
        self.assertEqual((roof.top_left_elevation, roof.bottom_right_elevation),
                         (combined.top_left_elevation, combined.bottom_right_elevation))
        self.assertEqual(map_file.door_warnings(parsed), [])

        map_props.move_instance(files, index, 1, 2)
        self.assertEqual((_roof_terrain(files, 2, 1), _roof_terrain(files, 1, 2)), ("plain", "扉"))
        map_props.remove_instance(files, index)
        self.assertEqual(_roof_terrain(files, 1, 2), "plain")

    def test_sync_is_stable_and_keeps_permanent_door_terrain(self):
        files = _door_map()
        before = files["map.bin"] = map_file.sync_door_terrain(files["map.bin"])[0]
        self.assertEqual(map_file.sync_door_terrain(before), (before, []))
        # 扉 in both layers without a door model is a permanent door tile: left alone
        files["map.bin"] = map_file.set_tile_terrains(files["map.bin"], {(2, 2): "扉"})
        parsed = map_file.read_map_bytes(files["map.bin"])
        grid = [list(c) for c in parsed.panel_index_roof]
        records = [(p.top_left_elevation, p.top_right_elevation, p.bottom_left_elevation, p.bottom_right_elevation,
                    p.terrain_type_ptr) for p in parsed.unique_panel_roof]
        grid[2][2] = grid[0][0]
        files["map.bin"] = map_file.write_panel_layer(files["map.bin"], "panelindexRoof", "uniquepanelRoof", grid, records)
        map_props.sync_doors(files)
        self.assertEqual((_terrain(files, 2, 2), _roof_terrain(files, 2, 2)), ("扉", "扉"))

    def test_warns_when_the_game_would_ignore_doors(self):
        files = _door_map(footprint_bit=False)
        self.assertIn("0x10000000", " ".join(map_props.sync_doors(files)))
        no_roof = {"map.bin": _map_bin(width=3, height=3)}
        parsed = map_file.read_map_bytes(no_roof["map.bin"])
        no_roof["map.bin"] = map_file.patch_object_field(no_roof["map.bin"], parsed.build_desc[1], "flag_bits_c", 0x13)
        self.assertIn("roof layer", " ".join(map_props.sync_doors(no_roof)))


def _roof_map():
    """A 4x4 map: object ``flat`` is the terrain, ``tree`` becomes a 3x2 building roof 6
    units tall on (0, 0) and ``door`` an openable door model."""
    files = _door_map(size=4)
    data = files["map.bin"]
    for field, value in (("flag_bits_c", 0x08), ("effect_type", 0x09), ("size_x", 15.0), ("size_y", 6.0), ("size_z", 10.0)):
        data = map_file.patch_object_field(data, map_file.read_map_bytes(data).build_desc[1], field, value)
    data, _index = map_file.add_build_object(data, map_file.MapObject(0, 0, 0, 5, 5, 3, 0, 0, 0x13, 0, "door"))
    # the map's tree instance on (0, 0): give it the roof's footprint
    records = map_file.instance_records(data)
    records[1] = map_file.instance_record(map_file.read_map_bytes(data).build_desc[1], 1, 0, 0, 0, 0.0)
    files["map.bin"] = map_file.set_build_instances(data, records)
    return files


def _roof_corners(files, x, y):
    parsed = map_file.read_map_bytes(files["map.bin"])
    return parsed.unique_panel_roof[parsed.panel_index_roof[x][y]].top_left_elevation


class RoofTerrainTests(unittest.TestCase):
    """A closed building roof gives its tiles the roof layer; a door in or next to it lifts it."""

    def test_roof_fills_the_roof_layer_and_keeps_the_floor(self):
        files = _roof_map()
        parsed = map_file.read_map_bytes(files["map.bin"])
        self.assertEqual(map_file.roof_instances(parsed), [1])
        self.assertTrue(any("touches no door" in w for w in map_file.door_warnings(parsed)))
        map_props.place_prop(files, "door", 1, 2)  # just below the roof's 3x2 footprint
        for tile in [(0, 0), (2, 1)]:
            self.assertEqual(_roof_terrain(files, *tile), "屋根")
            self.assertEqual(_roof_corners(files, *tile), -2400)  # 6 units above the ground
            self.assertEqual(_terrain(files, *tile), "plain")    # the room the opened roof shows
        self.assertEqual(_roof_terrain(files, 1, 2), "扉")
        self.assertEqual(_roof_terrain(files, 3, 3), "plain")
        self.assertEqual(map_file.door_warnings(map_file.read_map_bytes(files["map.bin"])), [])

    def test_walls_stay_and_a_moved_roof_gives_its_tiles_back(self):
        files = _roof_map()
        files["map.bin"] = map_file.set_tile_terrains(files["map.bin"], {(1, 0): "壁"})
        map_props.sync_doors(files)
        self.assertEqual((_roof_terrain(files, 0, 0), _roof_terrain(files, 1, 0)), ("屋根", "壁"))
        map_props.move_instance(files, 1, 1, 2)
        self.assertEqual(_roof_terrain(files, 0, 0), "plain")
        self.assertEqual(_roof_terrain(files, 2, 3), "屋根")

    def test_deduced_heights_keep_the_roof_up_and_the_floor_down(self):
        from fe_modding import map_heights
        files = _roof_map()
        map_props.sync_doors(files)
        data = map_file.read_map_bytes(files["map.bin"])
        corners = map_heights.deduce_corners(files, data, [(0, 0), (3, 3)])
        self.assertEqual(corners[(0, 0)]["roof"], (-2400,) * 4)
        self.assertEqual(corners[(0, 0)]["combined"], (0,) * 4)
        self.assertEqual(corners[(3, 3)]["roof"], corners[(3, 3)]["combined"])


if __name__ == "__main__":
    unittest.main()
