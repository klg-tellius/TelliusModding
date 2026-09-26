import os
import struct
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from fe_modding.formats import dispo, lz10, pak
from fe_modding.formats.common import HEADER_SIZE

from test_formats import _build_minimal_dispo_bytes

F = dispo.FIELD


class DispoDocumentTests(unittest.TestCase):
    def test_round_trip_is_byte_identical(self):
        data = _build_minimal_dispo_bytes()
        self.assertEqual(dispo.build_dispo(dispo.parse_dispo(data)), data)

    def test_parse_resolves_pointers_to_labels(self):
        doc = dispo.parse_dispo(_build_minimal_dispo_bytes())
        self.assertEqual([s.name for s in doc.sections], ["DATE", "SECA", "SECB"])
        self.assertTrue(doc.sections[0].is_link)
        self.assertEqual(doc.sections[0].header, "DATE")
        unit = doc.section("SECA").units[0]
        self.assertEqual(unit[F["pid"]], "PID_TEST")
        self.assertEqual(unit[F["jid"]], "JID_TEST")
        self.assertEqual(unit[F["item0"]], 0)

    def test_new_labels_are_appended_and_relocated(self):
        doc = dispo.parse_dispo(_build_minimal_dispo_bytes())
        unit = dispo.new_unit_values()
        unit[F["pid"]], unit[F["jid"]], unit[F["item0"]] = "PID_OSCAR", "JID_LANCEKNIGHT", "IID_IRONLANCE"
        unit[F["level"]] = 7
        dispo.move_unit(unit, 5, 6)
        dispo.add_unit(doc, "SECB", unit)
        data = dispo.build_dispo(doc)

        sections = dispo.read_dispo_bytes(data)
        new = sections[2].units[1]
        self.assertEqual(new.fields[0].label, b"PID_OSCAR")
        self.assertEqual(new.fields[1].label, b"JID_LANCEKNIGHT")
        self.assertEqual(new.fields[3].label, b"IID_IRONLANCE")
        self.assertEqual(new.fields[F["level"]].value, 7)
        self.assertEqual((new.fields[F["pos_x"]].value, new.fields[F["pos_y"]].value), (5, 6))
        # the old units still resolve after the pool moved
        self.assertEqual(sections[1].units[0].fields[0].label, b"PID_TEST")
        self.assertEqual(sections[0].linked_label, b"DATE")

        total, pool_size, relocations, section_count = struct.unpack_from(">4I", data, 0)
        self.assertEqual(total, len(data))
        self.assertEqual(section_count, 3)
        # date + 2 old units x 2 + the new unit's 3 pointers
        self.assertEqual(relocations, 8)
        pool_end = pool_size + HEADER_SIZE
        table = struct.unpack_from(f">{relocations}I", data, pool_end)
        layout = dispo._scan_layout(__import__("io").BytesIO(data))
        self.assertEqual(
            dispo.build_replacement_table(data, layout.label_map, layout.label_map_start),
            b"".join(struct.pack(">I", r) for r in table),
        )
        # and the rebuilt file round-trips
        self.assertEqual(dispo.build_dispo(dispo.parse_dispo(data)), data)

    def test_setting_a_null_pointer_adds_a_relocation(self):
        doc = dispo.parse_dispo(_build_minimal_dispo_bytes())
        doc.section("SECA").units[0][F["skill0"]] = "SID_CHARISMA"
        data = dispo.build_dispo(doc)
        self.assertEqual(struct.unpack_from(">I", data, 8)[0], 6)
        self.assertEqual(dispo.read_dispo_bytes(data)[1].units[0].fields[F["skill0"]].label, b"SID_CHARISMA")

    def test_remove_unit_drops_unused_labels(self):
        doc = dispo.parse_dispo(_build_minimal_dispo_bytes())
        unit = dispo.new_unit_values()
        unit[F["pid"]] = "PID_ONLY_HERE"
        dispo.add_unit(doc, "SECA", unit)
        data = dispo.build_dispo(doc)
        self.assertIn(b"PID_ONLY_HERE", data)
        doc = dispo.parse_dispo(data)
        dispo.remove_unit(doc, "SECA", 1)
        data = dispo.build_dispo(doc)
        self.assertNotIn(b"PID_ONLY_HERE", data)
        self.assertEqual(data, _build_minimal_dispo_bytes())

    def test_link_sections_refuse_units(self):
        doc = dispo.parse_dispo(_build_minimal_dispo_bytes())
        with self.assertRaises(ValueError):
            dispo.add_unit(doc, "DATE", dispo.new_unit_values())

    def test_move_unit_keeps_the_second_tile_offset(self):
        unit = dispo.new_unit_values()
        unit[F["pos_x"]], unit[F["pos_y"]], unit[F["pos2_x"]], unit[F["pos2_y"]] = 15, 16, 13, 16
        dispo.move_unit(unit, 10, 4)
        self.assertEqual(unit[F["pos_x"]:F["pos2_y"] + 1], [10, 4, 8, 4])


class DispoCounterpartTests(unittest.TestCase):
    def _doc(self, letter, pids):
        data = _build_minimal_dispo_bytes((f"bmap02_first_{letter}".encode(), b"bmap02_boss_" + letter.encode()))
        doc = dispo.parse_dispo(data)
        section = doc.sections[1]
        section.units = []
        for i, pid in enumerate(pids):
            unit = dispo.new_unit_values()
            unit[F["pid"]] = pid
            dispo.move_unit(unit, i, i)
            section.units.append(unit)
        return doc

    def test_section_base_strips_the_difficulty_letter(self):
        self.assertEqual(dispo.section_base("bmap02_first_n"), "bmap02_first")
        self.assertEqual(dispo.section_base("bmap05_first_boss2_h"), "bmap05_first_boss2")
        self.assertEqual(dispo.section_base("always"), "always")

    def test_finds_the_same_unit_in_another_variant(self):
        normal = self._doc("n", ["PID_A", "PID_ZAKO", "PID_ZAKO", "PID_B"])
        hard = self._doc("h", ["PID_ZAKO", "PID_A", "PID_ZAKO"])
        unit = normal.sections[1].units[0]
        self.assertEqual(dispo.find_counterpart_unit(hard, "bmap02_first_n", unit, 0), 1)
        self.assertIsNone(dispo.find_counterpart_unit(hard, "bmap02_first_n", normal.sections[1].units[3], 3))
        # a generic unit: same index when that one matches
        self.assertEqual(dispo.find_counterpart_unit(hard, "bmap02_first_n", normal.sections[1].units[2], 2), 2)


class DispoSectionHeaderTests(unittest.TestCase):
    def test_header_bytes_survive_a_rebuild(self):
        doc = dispo.parse_dispo(_build_minimal_dispo_bytes())
        section = doc.section("SECA")
        dispo.set_section_header(section, dispo.SectionHeader(mode=4, occupied_ok=1, group=10))
        dispo.add_unit(doc, "SECA", list(section.units[0]))
        rebuilt = dispo.parse_dispo(dispo.build_dispo(doc)).section("SECA")
        self.assertEqual(dispo.section_header(rebuilt), dispo.SectionHeader(4, 1, 10))
        self.assertEqual(len(rebuilt.units), 2)

    def test_rejects_links_and_out_of_range_bytes(self):
        doc = dispo.parse_dispo(_build_minimal_dispo_bytes())
        with self.assertRaises(ValueError):
            dispo.set_section_header(doc.sections[0], dispo.SectionHeader(4, 0, 1))
        with self.assertRaises(ValueError):
            dispo.set_section_header(doc.section("SECA"), dispo.SectionHeader(4, 0, 256))


class DispoFieldDescriptionTests(unittest.TestCase):
    def test_flags_and_item_flags_are_named(self):
        self.assertEqual(dispo.describe_field(F["flags"], 0x46),
                         "0x46 (Hold position, Group commander, Blocked by bridge cover)")
        self.assertEqual(dispo.describe_field(F["item0_flag"], 3), "3 (drop, ring)")
        self.assertEqual(dispo.describe_field(F["faction"], 3), "3 (Partner)")
        self.assertEqual(dispo.describe_field(F["level"], 7), "7")

    def test_every_field_has_help_and_every_flag_bit_a_label(self):
        self.assertEqual(sorted(dispo.FIELD_HELP), list(range(len(dispo.FIELD_LAYOUT))))
        self.assertEqual(sorted(mask for mask, _l, _h in dispo.FLAG_BITS), [1 << i for i in range(8)])


@unittest.skipUnless(os.environ.get("FE9_EXTRACTED_FILES"), "set FE9_EXTRACTED_FILES to an extracted files/ directory")
class VanillaDispoRoundTripTests(unittest.TestCase):
    def test_every_variant_round_trips(self):
        root = Path(os.environ["FE9_EXTRACTED_FILES"]) / "zmap"
        checked = 0
        for path in sorted(root.glob("*/dispos.cmp")):
            archive = lz10.decompress(path.read_bytes())
            for entry in pak.read_pak_entries(archive):
                data = pak.read_pak_file_content(archive, entry)
                with self.subTest(path=path.parent.name, variant=entry.name):
                    self.assertEqual(dispo.build_dispo(dispo.parse_dispo(data)), data)
                checked += 1
        self.assertGreater(checked, 0)


if __name__ == "__main__":
    unittest.main()
