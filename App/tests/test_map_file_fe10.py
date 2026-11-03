"""Radiant Dawn's map.bin: the same container as Path of Radiance's with renamed, folder-prefixed
sections, a merged ``mapdata`` header and wider object/placement records (map_file.MapLayout)."""

import os
import struct
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fe_modding.formats import map_file

PREFIX = "bmap9901:"


def _rd_map_bin(width=3, height=2, link=None) -> bytes:
    """A small Radiant Dawn map.bin: version-4 mapdata (capacity, mapextra, mapgrid, two more words),
    two 36-byte objects, two 20-byte placements, the panel layers, light/fog/shader kept raw and an
    optional maplink with a u32 record count."""
    pool = [b"bmap9901\x00", b"tree\x00", "平地".encode("shift_jis") + b"\x00"]
    mapdata = (struct.pack(">BBBBHHf", 4, 0, width, height, 2, 2, 2000.0)
               + struct.pack(">BBBBBBBBI", 0x17, 0x13, width // 2, height // 2, 0x40, 1, 0, 0, 0x301400B6)
               + bytes((0x1E, 0x32, 0x32, 0x32)) + struct.pack(">II", 0x40, 0x37AA) + struct.pack(">f", 1.0))
    desc = (struct.pack(">ffffffBBBBI", 0, -5, 0, 5 * width, 15, 5 * height, 0x08, 0, 1, 0x12, 0) + bytes((80, 72, 0, 0))
            + struct.pack(">ffffffBBBBI", 0, 0, 0, 5, 6, 5, 0, 0, 1, 0, 0) + bytes((1, 1, 0, 0)))
    inst = (struct.pack(">BbbBbbHbbbb", 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0) + struct.pack(">fI", 0.0, 0x40000000)
            + struct.pack(">BbbBbbHbbbb", 1, 2, 1, 0x40, -8, 16, 1, 2, 1, 2, 1) + struct.pack(">fI", -0.5, 0x40000000))
    grid = bytes(2 * width * height) + bytes(-(2 * width * height) % 4)
    panel = struct.pack(">hhhhI", 0, 0, 0, 0, 0)
    sections = [
        ("mapdata", mapdata, []),
        ("mapdesc", desc, [(28, 0), (64, 1)]),
        ("mapinst", inst, []),
        ("panelindex", grid, []),
        ("uniquepanel", panel, [(8, 2)]),
        ("baseindex", grid, []),
        ("basepanel", panel, [(8, 2)]),
        ("maplight", bytes(range(32)), []),
        ("mapfog", bytes(12), []),
        ("mapshader", bytes(20), []),
    ]
    if link is not None:
        payload = struct.pack(">I", len(link)) + b"".join(bytes(r) for r in link)
        sections.append(("maplink", payload + bytes(-len(payload) % 4), []))
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
    full = [PREFIX + n for n, _p, _q in sections]
    names = b"".join(n.encode() + b"\x00" for n in full)
    name_offsets, at = [], 0
    for n in full:
        name_offsets.append(at)
        at += len(n) + 1
    tail = struct.pack(f">{len(fields)}I", *sorted(o for o, _t in fields))
    tail += b"".join(struct.pack(">II", a, o) for a, o in zip(addresses, name_offsets)) + names
    header = struct.pack(">IIII", 0x20 + len(data) + len(tail), len(data), len(fields), len(sections)) + bytes(16)
    return header + bytes(data) + tail


class Fe10MapReadTests(unittest.TestCase):
    def setUp(self):
        self.raw = _rd_map_bin()
        self.data = map_file.read_map_bytes(self.raw)

    def test_layout_is_recognised_from_the_section_names(self):
        self.assertEqual(self.data.layout.game, "fe10")
        self.assertEqual(self.data.layout.prefix, PREFIX)
        self.assertEqual(map_file.map_layout(self.raw).file_name("panelindexRoof"), PREFIX + "roofindex")

    def test_mapdata_holds_capacity_extra_and_grid(self):
        cap = self.data.capacity
        self.assertEqual((cap.x_size, cap.y_size, cap.build_desc_count, cap.build_inst_count, cap.scale_unit),
                         (3, 2, 2, 2, 2000.0))
        self.assertEqual((self.data.extra.panel_offset_x, self.data.extra.half_x_size, self.data.extra.grid_buffer),
                         (0x17, 1, 1))
        self.assertEqual((self.data.grid.red, self.data.grid.green), (0x32, 0x32))

    def test_wide_records(self):
        self.assertEqual([o.filename for o in self.data.build_desc], ["bmap9901", "tree"])
        self.assertEqual(self.data.build_desc[0].footprint, (80, 72, 0, 0))
        prop = self.data.build_inst[1]
        self.assertEqual((prop.lead, prop.x, prop.y, prop.angle, prop.offset_x, prop.offset_y, prop.desc_index),
                         (1, 2, 1, 0x40, -8, 16, 1))
        self.assertAlmostEqual(prop.height(), -0.5)
        self.assertEqual(prop.tail, 0x40000000)

    def test_light_fog_and_shader_stay_raw(self):
        self.assertIsNone(self.data.light)
        self.assertIsNone(self.data.fog)
        self.assertEqual(set(self.data.unknown_sections), {"maplight", "mapfog", "mapshader"})

    def test_terrain_names_resolve(self):
        self.assertEqual(map_file.terrain_grid(self.raw)[2][1], "平地")


class Fe10MapWriteTests(unittest.TestCase):
    def setUp(self):
        self.raw = _rd_map_bin(link=[(1, 1, 0x0F)])

    def test_unchanged_writes_are_identity(self):
        self.assertEqual(map_file.set_build_instances(self.raw, map_file.instance_records(self.raw)), self.raw)
        data = map_file.read_map_bytes(self.raw)
        panels = [(p.top_left_elevation, p.top_right_elevation, p.bottom_left_elevation, p.bottom_right_elevation,
                   p.terrain_type_ptr) for p in data.unique_panel]
        self.assertEqual(map_file.write_panel_layer(self.raw, "panelindex", "uniquepanel", data.panel_index, panels),
                         self.raw)
        self.assertEqual(map_file.resize_grid(self.raw, 3, 2), self.raw)

    def test_resize_writes_byte_sizes_and_floor_halves(self):
        data = map_file.read_map_bytes(map_file.resize_grid(self.raw, 5, 4))
        self.assertEqual((data.capacity.x_size, data.capacity.y_size), (5, 4))
        self.assertEqual((data.extra.half_x_size, data.extra.half_y_size), (2, 2))
        self.assertEqual((len(data.panel_index), len(data.panel_index[0])), (5, 4))
        self.assertEqual(data.link[1][1], 0x0F)
        self.assertEqual(len(data.build_inst), 2)

    def test_new_placement_is_widened(self):
        data = map_file.read_map_bytes(self.raw)
        record = map_file.instance_record(data.build_desc[1], 1, 2, 0, 64, 0.25)
        out = map_file.set_build_instances(self.raw, map_file.instance_records(self.raw) + [record])
        added = map_file.read_map_bytes(out).build_inst[-1]
        self.assertEqual((added.x, added.y, added.angle, added.desc_index, added.offset_x, added.tail),
                         (2, 0, 64, 1, 0, map_file.FE10_INST_TAIL))
        self.assertAlmostEqual(added.height(), 0.25)
        self.assertEqual(len(map_file.instance_records(out)[-1]), 20)

    def test_new_object_gets_footprint_bytes(self):
        tree = map_file.read_map_bytes(self.raw).build_desc[1]
        obj = map_file.MapObject(0, 0, 0, 10, 4, 5, 0, 0, 1, 0, "rock_01")
        out, index = map_file.add_build_object(self.raw, obj)
        data = map_file.read_map_bytes(out)
        self.assertEqual(data.build_desc[index].filename, "rock_01")
        self.assertEqual(data.build_desc[index].footprint, (2, 1, 0, 0))
        self.assertEqual(data.build_desc[1].footprint, tree.footprint)
        self.assertEqual(data.capacity.build_desc_count, 3)

    def test_height_and_field_patches_use_the_wide_offsets(self):
        data = map_file.read_map_bytes(self.raw)
        out = map_file.patch_build_inst_height(self.raw, data.build_inst[1], 1.5)
        out = map_file.patch_build_inst_field(out, data.build_inst[1], "desc_index", 0)
        prop = map_file.read_map_bytes(out).build_inst[1]
        self.assertAlmostEqual(prop.height(), 1.5)
        self.assertEqual((prop.desc_index, prop.offset_x), (0, -8))

    def test_link_openings_use_the_u32_count(self):
        out = map_file.set_link_openings(self.raw, 0, 1, 0x03)
        data = map_file.read_map_bytes(out)
        self.assertEqual((data.link[0][1], data.link[1][1]), (0x03, 0x0F))
        fresh = map_file.set_link_openings(_rd_map_bin(), 2, 0, 0x01)
        self.assertEqual(map_file.read_map_bytes(fresh).link[2][0], 0x01)

    def test_terrain_edit(self):
        out = map_file.set_tile_terrains(self.raw, {(0, 1): "砦"})
        grid = map_file.terrain_grid(out)
        self.assertEqual((grid[0][1], grid[1][1]), ("砦", "平地"))


def _rd_maps():
    from fe_modding.formats import lz10, pak
    root = Path(os.environ["FE10_EXTRACTED_FILES"]) / "zmap"
    for path in sorted(root.glob("*/map.cmp")):
        raw = lz10.decompress(path.read_bytes())
        yield path.parent.name, {e.name: pak.read_pak_file_content(raw, e) for e in pak.read_pak_entries(raw)}


@unittest.skipUnless(os.environ.get("FE10_EXTRACTED_FILES"),
                     "set FE10_EXTRACTED_FILES to an extracted Radiant Dawn files/ directory")
class DiscFe10MapTests(unittest.TestCase):
    def test_every_map_reads_and_round_trips(self):
        count = 0
        for folder, files in _rd_maps():
            with self.subTest(folder):
                raw = files["map.bin"]
                data = map_file.read_map_bytes(raw)
                cap = data.capacity
                self.assertEqual(data.layout.prefix, folder + ":")
                self.assertEqual(len(data.build_desc), cap.build_desc_count)
                self.assertEqual(len(data.build_inst), cap.build_inst_count)
                self.assertTrue(all(0 <= i.desc_index < cap.build_desc_count for i in data.build_inst))
                self.assertEqual((len(data.panel_index), len(data.panel_index[0])), (cap.x_size, cap.y_size))
                self.assertEqual((data.extra.half_x_size, data.extra.half_y_size), (cap.x_size // 2, cap.y_size // 2))
                self.assertEqual(map_file.set_build_instances(raw, map_file.instance_records(raw)), raw)
                self.assertEqual(map_file.resize_grid(raw, cap.x_size, cap.y_size), raw)
                self.assertEqual(len(map_file.terrain_grid(raw)), cap.x_size)
                count += 1
        self.assertGreaterEqual(count, 120)


if __name__ == "__main__":
    unittest.main()
