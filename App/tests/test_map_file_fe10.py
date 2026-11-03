import io
import os
import unittest
from collections import Counter
from dataclasses import replace
from pathlib import Path

from fe_modding.formats import lz10, map_file, pak


def map_bin(path: Path) -> bytes:
    packed = lz10.decompress(path.read_bytes())
    entry = next(item for item in pak.read_pak_entries(packed) if item.name == "map.bin")
    return pak.read_pak_file_content(packed, entry)


@unittest.skipUnless(os.environ.get("FE10_EXTRACTED_FILES"),
                     "set FE10_EXTRACTED_FILES to RFEE01's extracted files directory")
class Fe10MapCorpusTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root = Path(os.environ["FE10_EXTRACTED_FILES"])
        cls.paths = sorted((cls.root / "zmap").glob("*/map.cmp"))

    def test_every_retail_map_parses_with_rd_counts_and_layers(self):
        self.assertGreaterEqual(len(self.paths), 128)
        randomized = []
        delayed = []
        flag_counts = Counter()
        for path in self.paths:
            with self.subTest(path=path.parent.name):
                raw = map_bin(path)
                parsed = map_file.read_map_bytes(raw)
                self.assertEqual(parsed.layout, "fe10")
                self.assertTrue(parsed.section_prefix)
                self.assertTrue(all(obj.map_prefix == parsed.section_prefix
                                    for obj in parsed.build_desc))
                randomized.extend(obj for obj in parsed.build_desc
                                  if map_file.randomizes_animation_start(obj))
                delayed.extend(obj for obj in parsed.build_desc
                               if map_file.delays_animation_reseed(obj))
                for obj in parsed.build_desc:
                    for field in ("flag_bits_a", "flag_bits_b", "flag_bits_c", "effect_type"):
                        value = getattr(obj, field)
                        for bit in range(8):
                            flag_counts[field, bit] += bool(value & (1 << bit))
                self.assertIsNotNone(parsed.capacity)
                self.assertEqual(len(parsed.build_desc), parsed.capacity.build_desc_count)
                self.assertEqual(len(parsed.build_inst), parsed.capacity.build_inst_count)
                self.assertEqual(len(parsed.panel_index), parsed.capacity.x_size)
                self.assertEqual(len(parsed.panel_index[0]), parsed.capacity.y_size)
                self.assertEqual(map_file.section_bytes(raw, "mapcapacity")[0],
                                 parsed.capacity.address)
                self.assertIsNotNone(parsed.rd_light)
                self.assertIsNotNone(parsed.rd_fog)
                self.assertIsNotNone(parsed.shader)
                if parsed.capacity.version >= 3:
                    self.assertEqual(parsed.capacity.wrap_duration_frames, 64)
                    self.assertIn(parsed.capacity.wrap_enabled, (0, 1))
                if parsed.capacity.version >= 4:
                    self.assertEqual(parsed.capacity.affinity_name, "invalid")
                    self.assertIn(parsed.capacity.terrain_height_ceiling,
                                  (1.0, 2.0, 3.0, 10.0, 20.0))
                    self.assertIn(parsed.capacity.address + 0x20 - map_file.HEADER_SIZE,
                                  map_file._pointer_offsets(raw))
                for name, record in (("maplight", parsed.rd_light), ("mapfog", parsed.rd_fog),
                                     ("mapshader", parsed.shader)):
                    address, size = map_file.section_bytes(raw, name)
                    self.assertEqual((record.address, record.to_bytes()),
                                     (address, raw[address:address + size]))
                    self.assertNotIn(name, parsed.unknown_sections)
        self.assertEqual(len(randomized), 79)
        self.assertTrue(all(obj.flag_bits_c & 0x06 == 0x06 for obj in randomized))
        self.assertEqual([obj.filename for obj in delayed], ["boco01"])
        self.assertTrue(map_file.randomizes_animation_start(delayed[0]))
        self.assertEqual(
            {key: value for key, value in flag_counts.items() if value},
            {("flag_bits_a", 0): 8, ("flag_bits_a", 3): 127,
             ("flag_bits_a", 4): 14, ("flag_bits_a", 5): 19,
             ("flag_bits_a", 6): 1,
             ("flag_bits_b", 0): 2, ("flag_bits_b", 1): 7,
             ("flag_bits_b", 2): 34, ("flag_bits_b", 3): 81,
             ("flag_bits_b", 4): 20, ("flag_bits_b", 6): 1,
             ("flag_bits_b", 7): 79,
             ("flag_bits_c", 0): 1317, ("flag_bits_c", 1): 362,
             ("flag_bits_c", 2): 152, ("flag_bits_c", 3): 44,
             ("flag_bits_c", 4): 36, ("flag_bits_c", 5): 402,
             ("flag_bits_c", 6): 86, ("flag_bits_c", 7): 17,
             ("effect_type", 0): 464, ("effect_type", 1): 328,
             ("effect_type", 2): 17, ("effect_type", 4): 190,
             ("effect_type", 5): 47, ("effect_type", 7): 19},
        )
        self.assertEqual(sum(bool(obj.flag_bits_c & 0x40) and
                             bool(obj.flag_bits_b & 0x80) for obj in randomized), 8)

    def test_rd_object_flag_consumers_match_retail_door(self):
        raw = map_bin(self.root / "zmap" / "bmap0103" / "map.cmp")
        parsed = map_file.read_map_bytes(raw)
        door = next(obj for obj in parsed.build_desc if obj.filename == "indr0103dr01")
        self.assertTrue(map_file.is_openable_door(door))
        self.assertTrue(map_file.uses_terrain_footprint(door))
        self.assertFalse(map_file.is_base_terrain_object(door))

    def test_environment_records_patch_without_changing_section_shape(self):
        raw = map_bin(self.root / "zmap" / "bmap0101" / "map.cmp")
        parsed = map_file.read_map_bytes(raw)

        light = replace(parsed.rd_light, angles=(parsed.rd_light.angles[0] + 1,
                                                *parsed.rd_light.angles[1:]))
        updated = map_file.patch_rd_light(raw, light)
        self.assertEqual(map_file.read_map_bytes(updated).rd_light, light)

        fog = replace(parsed.rd_fog, start_distance=parsed.rd_fog.start_distance + 1)
        updated = map_file.patch_rd_fog(updated, fog)
        self.assertEqual(map_file.read_map_bytes(updated).rd_fog, fog)

        first = bytes((parsed.shader.entries[0][0] ^ 1, *parsed.shader.entries[0][1:]))
        shader = replace(parsed.shader, entries=(first, *parsed.shader.entries[1:]))
        updated = map_file.patch_rd_shader(updated, shader)
        self.assertEqual(map_file.read_map_bytes(updated).shader, shader)
        self.assertEqual(len(updated), len(raw))

        with self.assertRaisesRegex(map_file.MapFileError, "retain"):
            map_file.patch_rd_shader(raw, replace(parsed.shader,
                                                  entries=(*parsed.shader.entries, bytes(4))))

    def test_instance_patch_preserves_rd_only_bytes(self):
        raw = map_bin(self.root / "zmap" / "bmap0101" / "map.cmp")
        parsed = map_file.read_map_bytes(raw)
        inst = next(item for item in parsed.build_inst if item.sub_x or item.sub_y
                    or item.lead or item.trailing_word != 0x40000000)
        before = raw[inst.address:inst.address + 20]
        updated = map_file.patch_build_inst_field(raw, inst, "angle", (inst.angle + 64) & 0xFF)
        after = updated[inst.address:inst.address + 20]
        self.assertEqual(after[:3] + after[4:], before[:3] + before[4:])
        again = map_file.read_map_bytes(updated).build_inst[parsed.build_inst.index(inst)]
        self.assertEqual((again.lead, again.sub_x, again.sub_y, again.trailing_word),
                         (inst.lead, inst.sub_x, inst.sub_y, inst.trailing_word))

    def test_instance_runtime_fields_have_typed_accessors_and_are_patchable(self):
        raw = map_bin(self.root / "zmap" / "bmap0101" / "map.cmp")
        parsed = map_file.read_map_bytes(raw)
        inst = next(item for item in parsed.build_inst if item.sub_x or item.sub_y or item.lead)
        self.assertEqual(inst.sub_tile_x, inst.sub_x / 64.0)
        self.assertEqual(inst.sub_tile_y, inst.sub_y / 64.0)
        self.assertEqual(inst.mirror_x, bool(inst.lead & 1))
        updated = map_file.patch_build_inst_field(raw, inst, "sub_x", -inst.sub_x)
        again = map_file.read_map_bytes(updated).build_inst[parsed.build_inst.index(inst)]
        self.assertEqual(again.sub_x, -inst.sub_x)
        self.assertEqual(again.trailing_word, inst.trailing_word)

    def test_rd_object_and_instance_growth_use_native_record_sizes(self):
        raw = map_bin(self.root / "zmap" / "bmap0101" / "map.cmp")
        parsed = map_file.read_map_bytes(raw)
        source = next(obj for obj in parsed.build_desc if not map_file.is_base_terrain_object(obj))
        added = replace(source, filename="codex_test_prop", address=0)
        grown, index = map_file.add_build_object(raw, added)
        reparsed = map_file.read_map_bytes(grown)
        self.assertEqual(index, len(parsed.build_desc))
        self.assertEqual(len(reparsed.build_desc), len(parsed.build_desc) + 1)
        self.assertEqual(reparsed.build_desc[-1].layout, "fe10")
        self.assertEqual(reparsed.build_desc[-1].filename, "codex_test_prop")
        records = map_file.instance_records(grown)
        self.assertTrue(all(len(record) == 20 for record in records))
        records.append(map_file.instance_record(reparsed.build_desc[-1], index, 2, 3, 64, 0.0))
        grown = map_file.set_build_instances(grown, records)
        final = map_file.read_map_bytes(grown)
        self.assertEqual(len(final.build_inst), len(parsed.build_inst) + 1)
        self.assertEqual((final.build_inst[-1].x, final.build_inst[-1].y,
                          final.build_inst[-1].trailing_word), (2, 3, 0x40000000))

    def test_rd_grid_resize_and_new_link_section_keep_prefixed_layout(self):
        raw = map_bin(self.root / "zmap" / "bmap0101" / "map.cmp")
        resized = map_file.resize_grid(raw, 33, 31)
        parsed = map_file.read_map_bytes(resized)
        self.assertEqual((parsed.capacity.x_size, parsed.capacity.y_size), (33, 31))
        self.assertEqual((len(parsed.panel_index), len(parsed.panel_index[0])), (33, 31))
        self.assertEqual((parsed.extra.half_x_size, parsed.extra.half_y_size), (16, 15))
        self.assertIsNone(parsed.link)
        linked = map_file.set_link_openings(resized, 1, 1, 0)
        final = map_file.read_map_bytes(linked)
        self.assertEqual(final.layout, "fe10")
        self.assertEqual(final.link[1][1], 0)
        self.assertIn("maplink", [name.rsplit(":", 1)[-1] for _address, name in
                                  map_file.read_section_table(
                                      io.BytesIO(linked), map_file._sections(linked)[1], len(linked))])


if __name__ == "__main__":
    unittest.main()
