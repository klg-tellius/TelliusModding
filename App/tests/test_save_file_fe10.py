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


class Fe10SaveTests(unittest.TestCase):
    def setUp(self):
        self.data = save_bytes()
        self.save = sf.SaveFile.from_bytes(self.data)

    def test_layout_and_rotating_slots(self):
        self.assertEqual(len(self.save.records), 12)
        first = self.save.records[0]
        self.assertTrue(first.valid)
        self.assertEqual((first.logical_slot, first.copy_name, first.checkpoint), (0, "A", False))
        self.assertEqual([record.index for record in self.save.active_records()], [0])
        self.assertTrue(self.save.records[1].empty)
        self.assertEqual(self.save.records[6].offset, sf.CHECKPOINT_BASE)

    def test_sections_are_ordered_and_sized(self):
        record_ = self.save.records[0]
        self.assertEqual([section.name for section in record_.sections],
                         [tag.decode("ascii") for tag in sf.STREAM_TAGS])
        self.assertEqual(record_.section_bytes("BMST"), bytes(range(20)))
        self.assertEqual(record_.section("FGPT").size, 12)

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
        soko = struct.pack(">HH", 5, 0x20) + bytes(range(32)) + bytes((sf.CONVOY_SLOTS - 1) * 4)
        stream = (b"ITBL" + b"BMST" + bytes(20) + b"MDST" + b"UNIP" + bytes(508)
                  + b"SOKO" + soko + b"FGPT" + bytes(12) + b"T  T" + b"RELD" + bytes(4)
                  + b"KZND" + bytes(4) + b"DEBU" + bytes(8))
        candidate = sf.SaveRecord(record(sf.DATA_MAGIC, sf.DATA_VERSION, sf.BLOCK_SIZE, 1, stream),
                                  sf.SYSTEM_SIZE, index=0)
        self.assertTrue(candidate.convoy_items()[0].forged)
        with self.assertRaisesRegex(ValueError, "read-only"):
            candidate.set_convoy_item(0, 6, 0x20)

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


if __name__ == "__main__":
    unittest.main()
