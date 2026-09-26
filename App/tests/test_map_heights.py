import struct
import sys
import unittest
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fe_modding import map_heights
from fe_modding.formats import map_file


def _map_bin(width=2, height=2, panel_elevation=0, prop_height=-0.2) -> bytes:
    """A small but complete map.bin: header, sections, string pool, pointer
    list, section table and names. One terrain object ``flat`` at placement
    (0, 0) and one prop ``tree`` on tile (0, 0); every tile shares panel
    record 0 (all corners ``panel_elevation``, terrain type ``plain``)."""
    pool = [b"flat\x00", b"tree\x00", b"plain\x00"]
    sections = [
        ("mapcapacity", struct.pack(">HHHHf", width, height, 2, 2, 2000.0), []),
        ("mapbuilddesc", struct.pack(">ffffffBBBBI", 0, 0, 0, 20, 1, 20, 0xC0, 0, 0, 0, 0)
         + struct.pack(">ffffffBBBBI", 0, 0, 0, 1, 1, 1, 0, 0, 0, 0, 0), [(28, 0), (60, 1)]),
        ("mapbuildinst", struct.pack(">8b", 0, 0, 0, 0, 0, 0, 0, 0) + struct.pack(">f", 0.0)
         + struct.pack(">8b", 0, 0, 0, 1, 0, 0, 0, 0) + struct.pack(">f", prop_height), []),
        ("panelindex", bytes(2 * width * height) + bytes(-(2 * width * height) % 4), []),
        ("uniquepanel", struct.pack(">hhhhI", *([panel_elevation] * 4), 0), [(8, 2)]),
        ("panelindexBase", bytes(2 * width * height) + bytes(-(2 * width * height) % 4), []),
        ("uniquepanelBase", struct.pack(">hhhhI", *([panel_elevation] * 4), 0), [(8, 2)]),
        ("mapextra", struct.pack(">BBBBBBBBI", 0, 0, 1, 1, 64, 0, 0, 0, 0), []),
    ]
    data = bytearray()
    addresses, fields = [], []
    for _name, payload, pointers in sections:
        addresses.append(len(data))
        fields += [(len(data) + offset, target) for offset, target in pointers]
        data += payload
    pool_at = []
    for s in pool:
        pool_at.append(len(data))
        data += s
    data += bytes(-len(data) % 4)
    for offset, target in fields:
        struct.pack_into(">I", data, offset, pool_at[target])
    names = b"".join(n.encode() + b"\x00" for n, _p, _q in sections)
    name_offsets, at = [], 0
    for n, _p, _q in sections:
        name_offsets.append(at)
        at += len(n) + 1
    tail = struct.pack(f">{len(fields)}I", *sorted(o for o, _t in fields))
    tail += b"".join(struct.pack(">II", a, o) for a, o in zip(addresses, name_offsets)) + names
    header = struct.pack(">IIII", 0x20 + len(data) + len(tail), len(data), len(fields), len(sections)) + bytes(16)
    return header + bytes(data) + tail


def _surface(heights):
    """Triangles over a grid of vertices 5 units apart (``heights[i][j]`` at
    x = 5i, z = 5j), each cell split along its (i, j)-(i+1, j+1) diagonal."""
    tris = []
    for i in range(len(heights) - 1):
        for j in range(len(heights[0]) - 1):
            a, b = (5 * i, heights[i][j], 5 * j), (5 * i + 5, heights[i + 1][j], 5 * j)
            c, d = (5 * i, heights[i][j + 1], 5 * j + 5), (5 * i + 5, heights[i + 1][j + 1], 5 * j + 5)
            tris += [[a, b, d], [a, d, c]]
    return np.array(tris, dtype=float)


class MapSectionWriterTests(unittest.TestCase):
    def test_synthetic_map_reads(self):
        data = map_file.read_map_bytes(_map_bin())
        self.assertEqual([o.filename for o in data.build_desc], ["flat", "tree"])
        self.assertEqual(len(data.unique_panel), 1)

    def test_rewriting_a_layer_unchanged_is_identity(self):
        raw = _map_bin()
        data = map_file.read_map_bytes(raw)
        records = [(p.top_left_elevation, p.top_right_elevation, p.bottom_left_elevation, p.bottom_right_elevation, p.terrain_type_ptr) for p in data.unique_panel]
        self.assertEqual(map_file.write_panel_layer(raw, "panelindex", "uniquepanel", data.panel_index, records), raw)

    def test_growing_a_layer_moves_pointers_and_later_sections(self):
        raw = _map_bin()
        data = map_file.read_map_bytes(raw)
        ptr = data.unique_panel[0].terrain_type_ptr
        grid = [[0, 1], [1, 0]]
        out = map_file.write_panel_layer(raw, "panelindex", "uniquepanel", grid, [(0, 0, 0, 0, ptr), (-400, 0, 0, 0, ptr)])
        new = map_file.read_map_bytes(out)
        self.assertEqual(len(out), len(raw) + 12 + 4)
        self.assertEqual(new.panel_index, grid)
        self.assertEqual([p.top_left_elevation for p in new.unique_panel], [0, -400])
        self.assertEqual({p.terrain_type_ptr for p in new.unique_panel}, {ptr + 12})
        self.assertEqual(new.unique_panel_base[0].terrain_type_ptr, ptr + 12)
        self.assertEqual([o.filename for o in new.build_desc], ["flat", "tree"])
        self.assertEqual((new.extra.half_x_size, new.extra.texture_projection_extent_x2), (1, 64))
        self.assertEqual(struct.unpack(">I", out[8:12])[0], 5)


class FollowTerrainTests(unittest.TestCase):
    def test_raised_corner_moves_both_layers_and_the_prop(self):
        raw = _map_bin(prop_height=-0.2)
        flat = _surface([[0.0] * 3 for _ in range(3)])
        raised = _surface([[0.0, 0.0, 0.0], [0.0, 2.0, 0.0], [0.0, 0.0, 0.0]])  # tile corner (1, 1)
        update = map_heights.follow_terrain(raw, "flat", flat, raised)
        data = map_file.read_map_bytes(update.map_bin)
        self.assertEqual(update.corners_changed, 1)
        self.assertEqual(update.tiles_changed, 4)
        for layer, grid in ((data.unique_panel, data.panel_index), (data.unique_panel_base, data.panel_index_base)):
            self.assertEqual(layer[grid[0][0]].bottom_right_elevation, -800)
            self.assertEqual(layer[grid[1][1]].top_left_elevation, -800)
            self.assertEqual(layer[grid[1][1]].bottom_right_elevation, 0)
        # the prop on tile (0, 0) stands at its centre (2.5, 2.5), halfway up the diagonal
        prop = data.build_inst[1]
        self.assertAlmostEqual(-5 * prop.height(), 1.0 + 1.0, places=4)
        self.assertEqual(update.props_moved, 1)

    def test_corners_standing_on_a_prop_keep_their_height(self):
        raw = _map_bin(panel_elevation=-1200)  # every corner 3 units up: a floor above the ground
        flat = _surface([[0.0] * 3 for _ in range(3)])
        heights = [[0.0] * 3 for _ in range(3)]
        heights[1][1] = 2.0
        update = map_heights.follow_terrain(raw, "flat", flat, _surface(heights))
        self.assertEqual((update.corners_changed, update.corners_on_props, update.tiles_changed), (1, 1, 0))
        data = map_file.read_map_bytes(update.map_bin)
        self.assertEqual({p.bottom_right_elevation for p in data.unique_panel_base}, {-1200})

    def test_a_prop_off_the_old_ground_keeps_its_height(self):
        raw = _map_bin(prop_height=2.4)  # pos_y = -12: sunk far below the flat ground
        flat = _surface([[0.0] * 3 for _ in range(3)])
        heights = [[0.0] * 3 for _ in range(3)]
        heights[1][1] = 2.0
        update = map_heights.follow_terrain(raw, "flat", flat, _surface(heights))
        self.assertEqual((update.props_moved, update.props_kept), (0, 1))
        self.assertAlmostEqual(map_file.read_map_bytes(update.map_bin).build_inst[1].height(), 2.4, places=4)

    def test_unchanged_surface_changes_nothing(self):
        raw = _map_bin()
        flat = _surface([[0.0] * 3 for _ in range(3)])
        self.assertEqual(map_heights.follow_terrain(raw, "flat", flat, flat.copy()).map_bin, raw)


class TerrainTypeTests(unittest.TestCase):
    def test_terrain_grid_and_setting_a_new_name(self):
        raw = _map_bin()
        self.assertEqual(map_file.terrain_grid(raw), [["plain", "plain"], ["plain", "plain"]])
        out = map_file.set_tile_terrains(raw, {(1, 0): "砦"})
        grid = map_file.terrain_grid(out)
        self.assertEqual(grid, [["plain", "plain"], ["砦", "plain"]])
        data = map_file.read_map_bytes(out)
        self.assertEqual([o.filename for o in data.build_desc], ["flat", "tree"])
        self.assertEqual(map_file.pointer_string(out, data.unique_panel_base[0].terrain_type_ptr), "plain")
        # a name the map already holds is reused, not appended again
        again = map_file.set_tile_terrains(out, {(0, 1): "砦"})
        self.assertEqual(struct.unpack(">I", again[4:8]), struct.unpack(">I", out[4:8]))
        self.assertEqual(map_file.terrain_grid(again)[0][1], "砦")



class TerrainCatalogTests(unittest.TestCase):
    def test_read_terrain_types_decodes_names_and_stats(self):
        from fe_modding.formats import fe8data

        names = ["平地".encode("shift_jis") + b"\x00", "MT_平地".encode("shift_jis") + b"\x00"]
        block = bytes([10, 1, 0, 0, 3, 3, 10, 0]) + bytes([2] * 14 + [255]) + b"\x00"
        records_at = 4
        pool_at = records_at + 12 * fe8data.TERRAIN_TYPE_COUNT
        block_at = pool_at + len(names[0]) + len(names[1])
        block_at += -block_at % 4
        body = bytearray(block_at + len(block))
        struct.pack_into(">III", body, records_at + 12, pool_at, pool_at + len(names[0]), block_at)
        body[pool_at : pool_at + len(names[0]) + len(names[1])] = names[0] + names[1]
        body[block_at : block_at + 24] = block
        body += bytes(-len(body) % 4)
        symbols = struct.pack(">II", 0, 0) + b"TerrainData\x00"
        header = struct.pack(">IIII", 0x20 + len(body) + len(symbols), len(body), 0, 1) + bytes(16)
        terrain = fe8data.read_terrain_types(header + bytes(body) + symbols)
        self.assertEqual(len(terrain), fe8data.TERRAIN_TYPE_COUNT)
        plain = terrain[1]
        self.assertEqual((plain.name, plain.name_key), ("平地", "MT_平地"))
        self.assertEqual((plain.avoid, plain.defense, plain.resistance, plain.alt_bonus, plain.heal), (10, 1, 0, (0, 3, 3), 10))
        self.assertEqual(plain.move_costs, (2,) * 14 + (255,))
        self.assertFalse(plain.impassable)

    def test_patch_terrain_stats_shared_or_own_block(self):
        from fe_modding.formats import fe8data

        block = bytes([10, 1, 0, 0, 3, 3, 0, 0]) + bytes([1] * 15) + b"\x00"
        block_at = 4 + 12 * fe8data.TERRAIN_TYPE_COUNT
        body = bytearray(block_at + 24)
        for index in (1, 2):  # two types sharing one block
            struct.pack_into(">I", body, 4 + 12 * index + 8, block_at)
        body[block_at : block_at + 24] = block
        pointers = struct.pack(">II", 4 + 12 + 8, 4 + 24 + 8)
        symbols = struct.pack(">II", 0, 0) + b"TerrainData\x00"
        header = struct.pack(">IIII", 0x20 + len(body) + 8 + len(symbols), len(body), 2, 1) + bytes(16)
        data = header + bytes(body) + pointers + symbols
        self.assertEqual(fe8data.terrain_block_users(data, 1), [1, 2])

        new = bytearray(fe8data.terrain_stats_block(fe8data.read_terrain_types(data)[1]))
        self.assertEqual(bytes(new), block)
        new[8 + 3] = 255  # armour can no longer cross
        shared = fe8data.patch_terrain_stats(data, 1, bytes(new))
        self.assertEqual([t.move_costs[3] for t in fe8data.read_terrain_types(shared)[1:3]], [255, 255])

        own = fe8data.patch_terrain_stats(data, 1, bytes(new), own_block=True)
        types = fe8data.read_terrain_types(own)
        self.assertEqual((types[1].move_costs[3], types[2].move_costs[3]), (255, 1))
        self.assertEqual(fe8data.terrain_block_users(own, 1), [1])
        self.assertEqual(struct.unpack(">I", own[:4])[0], len(own))
        self.assertEqual(fe8data.symbol_offsets(own), {"TerrainData": 0})


if __name__ == "__main__":
    unittest.main()
