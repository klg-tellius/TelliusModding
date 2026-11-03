import os
import struct
import tempfile
import unittest
import zlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fe_modding.formats import save_file_fe10 as sf


def signed(raw: bytearray) -> bytes:
    raw[sf.CRC_OFFSET:sf.CRC_OFFSET + 4] = bytes(4)
    struct.pack_into(">I", raw, sf.CRC_OFFSET, zlib.crc32(raw) & 0xFFFFFFFF)
    return bytes(raw)


def record(magic: bytes, version: int, size: int, sequence: int = 0, stream: bytes = b"") -> bytes:
    raw = bytearray([0xFF]) * size
    raw[:8] = magic
    struct.pack_into(">III", raw, 8, version, sf.FORMAT_VERSION, 0)
    struct.pack_into(">I", raw, 0x1C, sequence)
    raw[0x40:0x40 + len(stream)] = stream
    return signed(raw)


def save_bytes() -> bytes:
    out = bytearray([0xFF]) * sf.FILE_SIZE
    out[:sf.SYSTEM_SIZE] = record(sf.SYSTEM_MAGIC, sf.SYSTEM_VERSION, sf.SYSTEM_SIZE)
    stream = (b"ITBL" + b"abc" + b"BMST" + bytes(range(20)) + b"MDST" + b"xyz"
              + b"UNIP" + bytes(508) + b"SOKO" + bytes(sf.CONVOY_SLOTS * 4)
              + b"FGPT" + bytes(12)
              + b"T  T" + b"t" + b"RELD" + bytes(4) + b"KZND" + bytes(4)
              + b"DEBU" + bytes(8))
    out[sf.SYSTEM_SIZE:sf.SYSTEM_SIZE + sf.BLOCK_SIZE] = record(
        sf.DATA_MAGIC, sf.DATA_VERSION, sf.BLOCK_SIZE, 7, stream)
    return bytes(out)


def itbl_payload() -> bytes:
    tables = (("IKE", "MICAIAH", "SOTHE"), ("RANGER", "THIEF"), ("IRON_SWORD",),
              ("CANTO", "ADEPT"), ("ATK",), ("MOVE",), ("HEAL",), ("WALK",))
    return b"".join(struct.pack(">I", len(table))
                    + b"".join(name.encode("shift_jis") + b"\x00" for name in table)
                    for table in tables)


def occupied_unit_payload() -> bytes:
    prefix = (struct.pack(">HHBBBB", 3, 2, 4, 1, 0, 5)
              + bytes(range(7)) + bytes(range(8)) + bytes(4) + bytes(3)
              + bytes(range(8)) + bytes(range(8, 16)))
    skills = b"\x02" + struct.pack(">HBBHBB", 1, 2, 3, 0, 4, 5)
    forged = struct.pack(">HH", 1, 0x20) + b"Dawn\x00" + bytes(range(8))
    items = forged + bytes(6 * 4)
    pre_support = bytes(38)
    support = bytes(12) + struct.pack(">HB", 2, 2) + b"\x11\x22" + bytes(36)
    tail = bytes(37)
    payload = prefix + skills + items + pre_support + support + tail
    assert len(prefix) == 46
    return payload


class Fe10SaveTests(unittest.TestCase):
    def setUp(self):
        self.data = save_bytes()
        self.save = sf.SaveFile.from_bytes(self.data)

    def test_layout_and_six_files(self):
        self.assertEqual(len(self.save.records), 12)
        first = self.save.records[0]
        self.assertTrue(first.valid)
        self.assertEqual((first.logical_slot, first.checkpoint), (0, False))
        self.assertEqual(self.save.records[5].logical_slot, 5)
        self.assertEqual(self.save.records[11].logical_slot, 5)
        self.assertEqual([record.index for record in self.save.active_records()], [0])
        self.assertTrue(self.save.records[1].empty)
        self.assertEqual(self.save.records[6].offset, sf.CHECKPOINT_BASE)

    def test_move_to_chapter_needs_a_map_name(self):
        with self.assertRaises(ValueError):
            self.save.records[0].move_to_chapter(32, "bmap0401", 5)

    def test_records_with_different_sequences_are_independent_files(self):
        out = bytearray(self.data)
        stream = (b"ITBL" + b"BMST" + bytes(20) + b"MDST" + b"UNIP" + bytes(508)
                  + b"SOKO" + bytes(sf.CONVOY_SLOTS * 4) + b"FGPT" + bytes(12)
                  + b"T  T" + b"RELD" + bytes(4) + b"KZND" + bytes(4) + b"DEBU" + bytes(8))
        second = sf.SYSTEM_SIZE + sf.BLOCK_SIZE
        out[second:second + sf.BLOCK_SIZE] = record(
            sf.DATA_MAGIC, sf.DATA_VERSION, sf.BLOCK_SIZE, 99, stream)
        save = sf.SaveFile.from_bytes(bytes(out))
        self.assertEqual([item.index for item in save.active_records()], [0, 1])
        self.assertEqual([item.logical_slot for item in save.active_records()], [0, 1])
        self.assertEqual(sf.record_label(save.records[0]), "File 1 - sequence 7 - valid")
        self.assertEqual(sf.record_label(save.records[1]), "File 2 - sequence 99 - valid")

    def test_sections_are_ordered_and_sized(self):
        record_ = self.save.records[0]
        self.assertEqual([section.name for section in record_.sections],
                         [tag.decode("ascii") for tag in sf.STREAM_TAGS])
        self.assertEqual(record_.section_bytes("BMST"), bytes(range(20)))
        self.assertEqual(record_.section("FGPT").size, 12)

    def test_itbl_and_unip_are_structurally_framed(self):
        occupied = occupied_unit_payload()
        unip = occupied + bytes((sf.UNIT_SLOT_COUNT - 1) * 2)
        stream = (b"ITBL" + itbl_payload() + b"BMST" + bytes(20) + b"MDST" + b"xyz"
                  + b"UNIP" + unip + b"SOKO" + bytes(sf.CONVOY_SLOTS * 4)
                  + b"FGPT" + bytes(12) + b"T  T" + b"RELD" + bytes(4)
                  + b"KZND" + bytes(4) + b"DEBU" + bytes(8))
        candidate = sf.SaveRecord(record(sf.DATA_MAGIC, sf.DATA_VERSION, sf.BLOCK_SIZE, 1, stream),
                                  sf.SYSTEM_SIZE, index=0)
        tables = candidate.id_tables()
        self.assertEqual(tables.characters, ("IKE", "MICAIAH", "SOTHE"))
        self.assertEqual(candidate.id_of("character", "PID_SOTHE"), 3)
        self.assertEqual(candidate.id_of("skill", "SID_CANTO"), 0)
        units = candidate.unit_records({3: 2})
        self.assertEqual(len(units), sf.UNIT_SLOT_COUNT)
        self.assertEqual(b"".join(unit.raw for unit in units), unip)
        self.assertEqual((units[0].person_number, units[0].class_number, units[0].army), (3, 2, 4))
        self.assertEqual(units[0].linked_slots, (1, 0, 5))
        self.assertEqual(units[0].skills[0], sf.SavedSkill(1, 2, 3))
        self.assertTrue(units[0].items[0].forged)
        self.assertEqual(units[0].support_slot_count, 2)
        self.assertTrue(units[1].empty)

    def test_unip_requires_reliance_metadata_for_occupied_units(self):
        unip = occupied_unit_payload() + bytes((sf.UNIT_SLOT_COUNT - 1) * 2)
        stream = (b"ITBL" + itbl_payload() + b"BMST" + bytes(20) + b"MDST" + b"xyz"
                  + b"UNIP" + unip + b"SOKO" + bytes(sf.CONVOY_SLOTS * 4)
                  + b"FGPT" + bytes(12) + b"T  T" + b"RELD" + bytes(4)
                  + b"KZND" + bytes(4) + b"DEBU" + bytes(8))
        candidate = sf.SaveRecord(record(sf.DATA_MAGIC, sf.DATA_VERSION, sf.BLOCK_SIZE, 1, stream),
                                  sf.SYSTEM_SIZE, index=0)
        with self.assertRaisesRegex(ValueError, "support-slot metadata"):
            candidate.unit_records({})

    def test_noop_round_trip_is_byte_exact(self):
        self.assertEqual(self.save.to_bytes(), self.data)

    def test_section_edit_recomputes_only_record_crc(self):
        before_system = bytes(self.save.system.raw)
        block = self.save.records[0]
        block.replace_section_bytes("BMST", 3, b"\xFE")
        rebuilt = self.save.to_bytes()
        self.assertEqual(rebuilt[:sf.SYSTEM_SIZE], before_system)
        again = sf.SaveFile.from_bytes(rebuilt)
        self.assertEqual(again.records[0].section_bytes("BMST")[3], 0xFE)
        self.assertTrue(again.records[0].crc_ok)

    def test_battle_state_header_fields_are_editable(self):
        block = self.save.records[0]
        self.assertEqual((block.chapter_number, block.army_phase, block.turn), (0x10, 0x11, 0x1213))
        block.chapter_number = 3
        block.army_phase = 1
        block.turn = 42
        rebuilt = sf.SaveFile.from_bytes(self.save.to_bytes()).records[0]
        self.assertEqual((rebuilt.chapter_number, rebuilt.army_phase, rebuilt.turn), (3, 1, 42))
        self.assertTrue(rebuilt.crc_ok)

    def test_bmst_script_flags_edit_only_the_selected_bit(self):
        block = self.save.records[0]
        bmst = bytearray(sf.BMST_FLAGS_OFFSET + sf.SCRIPT_FLAG_BYTES)
        bmst[sf.BMST_FLAGS_OFFSET] = 0b10000001
        stream = (b"ITBL" + b"BMST" + bytes(bmst) + b"MDST" + b"UNIP" + bytes(508)
                  + b"SOKO" + bytes(sf.CONVOY_SLOTS * 4) + b"FGPT" + bytes(12)
                  + b"T  T" + b"RELD" + bytes(4) + b"KZND" + bytes(4) + b"DEBU" + bytes(8))
        block = sf.SaveRecord(record(sf.DATA_MAGIC, sf.DATA_VERSION, sf.BLOCK_SIZE, 1, stream),
                              sf.SYSTEM_SIZE, index=0)
        self.assertTrue(block.script_flags()[0])
        self.assertTrue(block.script_flags()[7])
        self.assertFalse(block.script_flags()[8])
        block.set_script_flag(8, True)
        block.set_script_flag(7, False)
        flags = block.script_flags()
        self.assertEqual([i for i, enabled in enumerate(flags) if enabled], [0, 8])
        self.assertEqual(block.section_bytes("BMST")[sf.BMST_FLAGS_OFFSET:sf.BMST_FLAGS_OFFSET + 2],
                         b"\x01\x01")
        with self.assertRaisesRegex(ValueError, "0..127"):
            block.set_script_flag(128, True)

    def test_kznd_runtime_bonds_parse_and_edit_in_place(self):
        kznd = struct.pack(">IHHBbHHBb", 2, 3, 9, 1, 12, 4, 10, 2, -5)
        stream = (b"ITBL" + b"BMST" + bytes(20) + b"MDST" + b"UNIP" + bytes(508)
                  + b"SOKO" + bytes(sf.CONVOY_SLOTS * 4) + b"FGPT" + bytes(12)
                  + b"T  T" + b"RELD" + bytes(4) + b"KZND" + kznd + b"DEBU" + bytes(8))
        block = sf.SaveRecord(record(sf.DATA_MAGIC, sf.DATA_VERSION, sf.BLOCK_SIZE, 1, stream),
                              sf.SYSTEM_SIZE, index=0)
        self.assertEqual(block.runtime_bonds(), (
            sf.RuntimeBond(3, 9, 1, 12), sf.RuntimeBond(4, 10, 2, -5)))
        before_debu = block.section("DEBU").tag_offset
        block.set_runtime_bond(1, sf.RuntimeBond(8, 11, 3, 20))
        self.assertEqual(block.runtime_bonds()[1], sf.RuntimeBond(8, 11, 3, 20))
        self.assertEqual(block.section("DEBU").tag_offset, before_debu)

    def test_kznd_count_must_match_section_size(self):
        stream = (b"ITBL" + b"BMST" + bytes(20) + b"MDST" + b"UNIP" + bytes(508)
                  + b"SOKO" + bytes(sf.CONVOY_SLOTS * 4) + b"FGPT" + bytes(12)
                  + b"T  T" + b"RELD" + bytes(4) + b"KZND" + struct.pack(">I", 1)
                  + b"DEBU" + bytes(8))
        block = sf.SaveRecord(record(sf.DATA_MAGIC, sf.DATA_VERSION, sf.BLOCK_SIZE, 1, stream),
                              sf.SYSTEM_SIZE, index=0)
        with self.assertRaisesRegex(ValueError, "requires 10 bytes"):
            block.runtime_bonds()

    def test_tactical_table_fixed_layout(self):
        records = b"".join(bytes((index,)) * sf.TACTICAL_RECORD_SIZE
                           for index in range(sf.TACTICAL_RECORD_COUNT))
        payload = (records + struct.pack(">I", 0x12345678)
                   + bytes((i & 0xFF for i in range(sf.TACTICAL_BLOB_SIZE)))
                   + struct.pack(">I", 0x90ABCDEF))
        stream = (b"ITBL" + b"BMST" + bytes(20) + b"MDST" + b"UNIP" + bytes(508)
                  + b"SOKO" + bytes(sf.CONVOY_SLOTS * 4) + b"FGPT" + bytes(12)
                  + b"T  T" + payload + b"RELD" + bytes(4) + b"KZND" + bytes(4)
                  + b"DEBU" + bytes(8))
        block = sf.SaveRecord(record(sf.DATA_MAGIC, sf.DATA_VERSION, sf.BLOCK_SIZE, 1, stream),
                              sf.SYSTEM_SIZE, index=0)
        state = block.tactical_table_state()
        self.assertEqual(len(state.records), sf.TACTICAL_RECORD_COUNT)
        self.assertEqual(state.records[5], b"\x05" * 8)
        self.assertEqual(state.value_after_records, 0x12345678)
        self.assertEqual(len(state.blob), sf.TACTICAL_BLOB_SIZE)
        self.assertEqual(state.final_value, 0x90ABCDEF)

    def test_reld_runtime_relations_parse_and_edit(self):
        reld = struct.pack(">IHHBHHB", 2, 3, 9, 7, 4, 10, 8)
        stream = (b"ITBL" + b"BMST" + bytes(20) + b"MDST" + b"UNIP" + bytes(508)
                  + b"SOKO" + bytes(sf.CONVOY_SLOTS * 4) + b"FGPT" + bytes(12)
                  + b"T  T" + b"x" + b"RELD" + reld + b"KZND" + bytes(4) + b"DEBU" + bytes(8))
        block = sf.SaveRecord(record(sf.DATA_MAGIC, sf.DATA_VERSION, sf.BLOCK_SIZE, 1, stream),
                              sf.SYSTEM_SIZE, index=0)
        self.assertEqual(block.runtime_relations(), (
            sf.RuntimeRelation(3, 9, 7), sf.RuntimeRelation(4, 10, 8)))
        block.set_runtime_relation(0, sf.RuntimeRelation(5, 11, 12))
        self.assertEqual(block.runtime_relations()[0], sf.RuntimeRelation(5, 11, 12))

    def test_convoy_slots_edit_without_moving_later_sections(self):
        block = self.save.records[0]
        before_fgpt = block.section("FGPT").tag_offset
        self.assertEqual(len(block.convoy_items()), sf.CONVOY_SLOTS)
        block.set_convoy_item(12, 37, 9)
        rebuilt = sf.SaveFile.from_bytes(self.save.to_bytes()).records[0]
        item = rebuilt.convoy_items()[12]
        self.assertEqual((item.item_number, item.state), (37, 9))
        self.assertEqual(rebuilt.section("FGPT").tag_offset, before_fgpt)
        self.assertTrue(rebuilt.crc_ok)

    def test_forged_convoy_slot_is_preserved_but_read_only(self):
        suffix = b"Silver Dawn\x00" + bytes(range(8))
        soko = struct.pack(">HH", 5, 0x20) + suffix + bytes((sf.CONVOY_SLOTS - 1) * 4)
        stream = (b"ITBL" + b"BMST" + bytes(20) + b"MDST" + b"UNIP" + bytes(508)
                  + b"SOKO" + soko + b"FGPT" + bytes(12) + b"T  T" + b"RELD" + bytes(4)
                  + b"KZND" + bytes(4) + b"DEBU" + bytes(8))
        candidate = sf.SaveRecord(record(sf.DATA_MAGIC, sf.DATA_VERSION, sf.BLOCK_SIZE, 1, stream),
                                  sf.SYSTEM_SIZE, index=0)
        forged = candidate.convoy_items()[0]
        self.assertTrue(forged.forged)
        self.assertEqual(forged.forge_name_bytes, b"Silver Dawn")
        self.assertEqual(forged.forged_name, "Silver Dawn")
        self.assertEqual(forged.forge_payload, bytes(range(8)))
        self.assertEqual(forged.forge_values, sf.ForgePayload(0, 1, 2, 3, 4, 5, 6, 7))
        self.assertEqual(forged.size, 4 + len(suffix))
        with self.assertRaisesRegex(ValueError, "read-only"):
            candidate.set_convoy_item(0, 6, 0x20)

    def test_forged_convoy_name_and_stats_are_editable(self):
        suffix = b"Old\x00" + sf.ForgePayload(1, 2, 3, -1, 0x80, 0x80, 0x80, 0xFF).to_bytes()
        soko = struct.pack(">HH", 5, 0x20) + suffix + bytes((sf.CONVOY_SLOTS - 1) * 4)
        stream = (b"ITBL" + b"BMST" + bytes(20) + b"MDST" + b"UNIP" + bytes(508)
                  + b"SOKO" + soko + b"FGPT" + bytes(12) + b"T  T" + b"RELD" + bytes(4)
                  + b"KZND" + bytes(4) + b"DEBU" + bytes(8))
        candidate = sf.SaveRecord(record(sf.DATA_MAGIC, sf.DATA_VERSION, sf.BLOCK_SIZE, 1, stream),
                                  sf.SYSTEM_SIZE, index=0)
        old_fgpt = candidate.section("FGPT").tag_offset
        values = sf.ForgePayload(5, 10, 3, 2, 0x20, 0x40, 0x60, 0xFF)
        candidate.update_forged_convoy_item(0, item_number=7, name="Radiant Dawn", payload=values)
        forged = candidate.convoy_items()[0]
        self.assertEqual((forged.item_number, forged.state), (7, 0x20))
        self.assertEqual(forged.forge_name_bytes, b"Radiant Dawn")
        self.assertEqual(forged.forge_values, values)
        self.assertGreater(candidate.section("FGPT").tag_offset, old_fgpt)
        rebuilt = sf.SaveRecord(candidate.build(), sf.SYSTEM_SIZE, index=0)
        self.assertTrue(rebuilt.crc_ok)
        self.assertEqual(rebuilt.convoy_items()[0].forge_values, values)
        with self.assertRaisesRegex(ValueError, "15-byte"):
            candidate.update_forged_convoy_item(0, name="X" * 15)

    def test_forged_convoy_name_must_terminate_within_24_bytes(self):
        soko = struct.pack(">HH", 5, 0x20) + b"X" * 24 + bytes(8) + bytes((sf.CONVOY_SLOTS - 1) * 4)
        stream = (b"ITBL" + b"BMST" + bytes(20) + b"MDST" + b"UNIP" + bytes(508)
                  + b"SOKO" + soko + b"FGPT" + bytes(12) + b"T  T" + b"RELD" + bytes(4)
                  + b"KZND" + bytes(4) + b"DEBU" + bytes(8))
        candidate = sf.SaveRecord(record(sf.DATA_MAGIC, sf.DATA_VERSION, sf.BLOCK_SIZE, 1, stream),
                                  sf.SYSTEM_SIZE, index=0)
        with self.assertRaisesRegex(ValueError, "terminated name"):
            candidate.convoy_items()

    def test_itbl_names_the_numbers(self):
        lists = [[b"IKE", b"MIST"], [b"BRAVE"], [b"IRONSWORD", b"VULNERARY"], [b"HERO"], [], [], [], [b"NORMAL"]]
        itbl = b"".join(struct.pack(">I", len(names)) + b"".join(n + b"\0" for n in names) for names in lists)
        stream = (b"ITBL" + itbl + b"BMST" + bytes(20) + b"MDST" + b"UNIP" + bytes(508)
                  + b"SOKO" + struct.pack(">HH", 2, 1) + bytes((sf.CONVOY_SLOTS - 1) * 4) + b"FGPT" + bytes(12)
                  + b"T  T" + b"RELD" + bytes(4) + b"KZND" + bytes(4) + b"DEBU" + bytes(8))
        candidate = sf.SaveRecord(record(sf.DATA_MAGIC, sf.DATA_VERSION, sf.BLOCK_SIZE, 1, stream),
                                  sf.SYSTEM_SIZE, index=0)
        tables = candidate.id_name_lists()
        self.assertEqual(tables["character"], ["PID_IKE", "PID_MIST"])
        self.assertEqual(tables["move_type"], ["MTYPE_NORMAL"])
        # characters, classes and items count from 1, skills from 0
        self.assertEqual(candidate.id_name("item", candidate.convoy_items()[0].item_number), "IID_VULNERARY")
        self.assertEqual((candidate.id_name("character", 1), candidate.id_name("skill", 0)), ("PID_IKE", "SID_HERO"))
        self.assertIsNone(candidate.id_name("item", 0))

    def test_bad_checksum_is_reported(self):
        damaged = bytearray(self.data)
        damaged[sf.SYSTEM_SIZE + 0x80] ^= 1
        save = sf.SaveFile.from_bytes(bytes(damaged))
        self.assertTrue(any("checksum" in problem for problem in sf.validate(save)))

    def test_folder_open(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / sf.FILE_NAME
            path.write_bytes(self.data)
            self.assertEqual(sf.SaveFile.from_path(Path(temp)).data, self.data)


@unittest.skipUnless(os.environ.get("FE10_SAVES"), "set FE10_SAVES to a folder containing FE10_US.dat files")
class Fe10RealSaveTests(unittest.TestCase):
    def test_corpus_round_trips(self):
        root = Path(os.environ["FE10_SAVES"])
        paths = [root] if root.is_file() else list(root.rglob(sf.FILE_NAME))
        self.assertTrue(paths)
        for path in paths:
            save = sf.SaveFile.from_bytes(path.read_bytes())
            self.assertEqual(sf.validate(save), [], str(path))
            self.assertEqual(save.to_bytes(), save.data, str(path))
            for record in save.active_records():
                tables = record.id_name_lists()  # reads ITBL to its last byte
                self.assertEqual(tables["character"][0], "PID_IKE", str(path))
                self.assertEqual(len(record.convoy_items()), sf.CONVOY_SLOTS, str(path))

            for candidate in save.active_records():
                with self.subTest(path=path, record=candidate.index):
                    self.assertEqual(candidate.header_u8(0x30), candidate.logical_slot)
                    self.assertEqual(len(candidate.convoy_items()), sf.CONVOY_SLOTS)
                    self.assertEqual(len(candidate.script_flags()), sf.SCRIPT_FLAG_COUNT)
                    self.assertIsInstance(candidate.runtime_bonds(), tuple)
                    self.assertEqual(len(candidate.tactical_table_state().records),
                                     sf.TACTICAL_RECORD_COUNT)
                    self.assertIsInstance(candidate.runtime_relations(), tuple)

    @unittest.skipUnless(os.environ.get("FE10_EXTRACTED_FILES"),
                         "set FE10_EXTRACTED_FILES to the extracted RFEE01 files folder")
    def test_real_unip_streams_end_exactly_at_soko(self):
        from fe_modding.formats import lz10

        root = Path(os.environ["FE10_EXTRACTED_FILES"])
        database_paths = list(root.rglob("FE10Data.cms"))
        self.assertTrue(database_paths)
        database = lz10.decompress(database_paths[0].read_bytes())
        save_root = Path(os.environ["FE10_SAVES"])
        paths = [save_root] if save_root.is_file() else list(save_root.rglob(sf.FILE_NAME))
        self.assertTrue(paths)
        for path in paths:
            save = sf.SaveFile.from_bytes(path.read_bytes())
            for candidate in save.active_records():
                with self.subTest(path=path, record=candidate.index):
                    counts = candidate.support_slot_counts_from_fe10data(database)
                    units = candidate.unit_records(counts)
                    self.assertEqual(len(units), sf.UNIT_SLOT_COUNT)
                    self.assertEqual(b"".join(unit.raw for unit in units),
                                     candidate.section_bytes("UNIP"))


if __name__ == "__main__":
    unittest.main()
