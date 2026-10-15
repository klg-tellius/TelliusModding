import glob
import os
import struct
import unittest
import zlib

from fe_modding.formats import save_file as sf


def unit_record(character: int, job: int, army: int = 0, prev: int = 0, nxt: int = 0, item: int = 0) -> bytes:
    rec = bytearray(sf.UNIT_RECORD_SIZE)
    struct.pack_into(">HH", rec, 0, character, job)
    rec[4], rec[5], rec[6] = army, prev, nxt
    rec[9] = 5  # level
    rec[23] = 20  # current HP (+0x1A8)
    struct.pack_into(">HBB", rec, 58, item, 30, 0x80)  # item 1
    return bytes(rec)


def build_block(units: list) -> bytes:
    """A 0x4000 file block: header, SYSF, then the tagged stream."""
    b = bytearray(0x4000)
    b[0x40:0x44] = sf.SAVE_MAGIC
    struct.pack_into(">III", b, 0x44, sf.SAVE_VERSION, 9, 0x4000)
    b[0x60], b[0x64], b[0x65], b[0x66] = 2, 5, 4, 1
    b[0x70:0x74] = b"SYSF"
    struct.pack_into(">I", b, 0x74, sf.SAVE_VERSION)
    stream = bytearray(b"BMST")
    party = bytearray(sf.PartyState.SIZE)
    struct.pack_into(">I", party, 0x18, 1234)  # gold
    party[0x1F4:0x1FA] = b"bmap05"
    party[0xA8] = 0b101  # flags 0 and 2
    stream += party + b"MDST" + bytes(sf.MapState.SIZE) + b"UNIP"
    for slot in range(sf.UNIT_SLOTS):
        stream += units[slot] if slot < len(units) and units[slot] else b"\0\0"
    stream += b"SOKO" + bytes(4 * sf.CONVOY_SLOTS) + b"FWEP" + bytes(0x18 * sf.FORGE_RECORDS)
    stream += b"T  T" + bytes(sf.TerrainTable.SIZE)
    b[0xB8:0xB8 + len(stream)] = stream
    struct.pack_into(">I", b, 0x50, zlib.crc32(bytes(b[0x70:])))
    return bytes(b)


def build_gci(block: bytes) -> bytes:
    gci = bytearray(sf.GCI_HEADER_SIZE + 0x26000)
    at = sf.GCI_HEADER_SIZE + sf.BLOCK_LOCATIONS[0][0]
    gci[at:at + len(block)] = block
    return bytes(gci)


class BlockTests(unittest.TestCase):
    def setUp(self):
        self.raw = build_block([unit_record(1, 2, prev=0, nxt=2, item=7), unit_record(3, 4, prev=1, nxt=0)])
        self.save = sf.SaveFile.from_bytes(build_gci(self.raw))
        self.block = self.save.blocks[0]

    def test_decodes_every_chunk(self):
        b = self.block
        self.assertTrue(b.decoded, b.error)
        self.assertTrue(b.crc_ok)
        self.assertEqual(b.party.gold, 1234)
        self.assertEqual(b.party.chapter_name, "bmap05")
        self.assertEqual([s for s, _ in b.unit_slots()], [1, 2])
        ike = b.units[0]
        self.assertEqual((ike.character, ike.job, ike.level, ike.hp, ike.next_slot), (1, 2, 5, 20, 2))
        self.assertEqual((ike.items[0].item, ike.items[0].uses), (7, 30))
        self.assertTrue(ike.items[0].equipped)
        self.assertEqual(len(b.convoy), 200)
        self.assertEqual(len(b.forges), 48)
        self.assertEqual(b.header.resume_point, 4)
        self.assertTrue(b.flags_stale)

    def test_pal_block_magic_is_read_and_kept(self):
        raw = bytearray(self.raw)
        raw[0x40:0x44] = b"FE8X"                      # PAL: "FE8X", version 0x20050801
        struct.pack_into(">I", raw, 0x44, 0x20050801)
        struct.pack_into(">I", raw, 0x50, zlib.crc32(bytes(raw[0x70:])))
        gci = build_gci(bytes(raw))
        save = sf.SaveFile.from_bytes(gci)
        block = save.blocks[0]
        self.assertTrue(block.decoded, block.error)
        self.assertEqual((block.header.magic, block.header.version), (b"FE8X", 0x20050801))
        self.assertEqual(save.to_bytes(), gci)

    def test_round_trip_is_byte_exact(self):
        self.assertEqual(self.block.build(), self.raw)
        self.assertEqual(self.save.to_bytes(), self.save.data)

    def test_edit_rewrites_the_checksum(self):
        self.block.party.gold = 99
        out = self.block.build()
        self.assertEqual(struct.unpack_from(">I", out, 0x50)[0], zlib.crc32(out[0x70:0x4000]))
        again = sf.SaveBlock.parse(out, 0, 0x4000)
        self.assertEqual(again.party.gold, 99)

    def test_named_options_preserve_other_bits_and_round_trip(self):
        party = self.block.party
        options = bytearray(party.options)
        options[2] = 0x15
        party.options = bytes(options)
        self.assertFalse(party.option_enabled(0x01))
        self.assertFalse(party.option_enabled(0x10))
        party.set_option_enabled(0x10, True)
        self.assertEqual(party.options[2], 0x05)
        party.set_option_enabled(0x01, True)
        self.assertEqual(party.options[2], 0x04)
        party.set_option_enabled(0x10, False)
        self.assertEqual(party.options[2], 0x14)
        again = sf.SaveBlock.parse(self.block.build(), 0, 0x4000)
        self.assertTrue(again.crc_ok)
        self.assertEqual(again.party.options[2], 0x14)

    def test_named_party_and_unused_unit_fields_round_trip(self):
        party = self.block.party
        party.reinforcement_uses = 2
        party.faction_command_records = bytes((1, 2, 8, 9, 3, 4, 255, 255))
        party.set_bm_value(4, -123)
        unit = self.block.units[0]
        unit.unused_19d = 27
        unit.unused_230 = 1234
        unit.unused_232 = 5678
        unit.unused_235 = 7
        again = sf.SaveBlock.parse(self.block.build(), 0, 0x4000)
        self.assertTrue(again.crc_ok)
        self.assertEqual(again.party.reinforcement_uses, 2)
        self.assertEqual(again.party.faction_command_records, party.faction_command_records)
        self.assertEqual(again.party.bm_value(4), -123)
        self.assertEqual((again.units[0].unused_19d, again.units[0].unused_230,
                          again.units[0].unused_232, again.units[0].unused_235), (27, 1234, 5678, 7))

    def test_adding_a_unit_moves_the_later_chunks(self):
        clone = sf.SaveBlock.parse(self.raw, 0, 0x4000).units[1]
        slot = self.block.add_unit(clone, after=2)
        self.assertEqual(slot, 3)
        self.assertEqual(self.block.units[1].next_slot, 3)
        self.assertEqual(self.block.units[2].prev_slot, 2)
        out = self.block.build()
        self.assertEqual(out.find(b"SOKO") - self.raw.find(b"SOKO"), sf.UNIT_RECORD_SIZE - 2)
        again = sf.SaveBlock.parse(out, 0, 0x4000)
        self.assertTrue(again.crc_ok)
        self.assertEqual([s for s, _ in again.unit_slots()], [1, 2, 3])

    def test_removing_a_unit_closes_the_army_list(self):
        self.block.remove_unit(1)
        self.assertIsNone(self.block.units[0])
        self.assertEqual(self.block.units[1].prev_slot, 0)
        again = sf.SaveBlock.parse(self.block.build(), 0, 0x4000)
        self.assertEqual([s for s, _ in again.unit_slots()], [2])

    def test_skill_bits_use_big_endian_words(self):
        u = self.block.units[0]
        u.set_skill(33, True)
        self.assertEqual(u.skills[4:8], b"\0\0\0\x02")
        self.assertTrue(u.has_skill(33))
        u.set_skill(33, False)
        self.assertFalse(u.has_skill(33))

    def test_validate_flags_a_missing_forge_record(self):
        self.block.units[0].items[0].flags = 0x80 | 3
        problems = sf.validate(self.block)
        self.assertTrue(any("forge record 3" in p for p in problems), problems)

    def test_a_consumed_copy_is_kept_raw(self):
        raw = bytearray(self.raw)
        raw[0x60] = 1
        raw[0x2000:] = bytes(0x2000)  # only the first half is ever written
        block = sf.SaveBlock.parse(bytes(raw), 0, 0x4000)
        self.assertFalse(block.decoded)
        self.assertEqual(block.build(), bytes(raw))

    def test_weapon_rank_letters(self):
        self.assertEqual([sf.weapon_rank(x) for x in (0, 1, 31, 70, 71, 251)], ["-", "E", "D", "D", "C", "S"])


@unittest.skipUnless(os.environ.get("FE9_SAVES"), "set FE9_SAVES to a folder of .gci saves")
class RealSaveTests(unittest.TestCase):
    def test_every_block_round_trips(self):
        paths = glob.glob(os.path.join(os.environ["FE9_SAVES"], "*.gci"))
        self.assertTrue(paths)
        decoded = 0
        for path in paths:
            with open(path, "rb") as fh:
                save = sf.SaveFile.from_bytes(fh.read())
            for b in save.blocks:
                if b.header.save_kind == 1:
                    continue
                self.assertTrue(b.decoded, f"{path} block {b.location}: {b.error}")
                self.assertEqual(b.build(), b.raw, f"{path} block {b.location}")
                decoded += 1
        self.assertGreater(decoded, 0)


if __name__ == "__main__":
    unittest.main()


class ForgePoolTests(unittest.TestCase):
    def test_a_full_forge_pool_is_reported(self):
        save = sf.SaveFile.from_bytes(build_gci(build_block([unit_record(1, 2)])))
        block = save.blocks[0]
        self.assertEqual(sf.validate(block), [])
        for record in block.forges:
            record.allocated = 1
        problems = sf.validate(block)
        self.assertEqual(len(problems), 1)
        self.assertIn("convoy slots 198-200", problems[0])

class PlayCopyTests(unittest.TestCase):
    """The run copy for Play in Dolphin: block 0 (slot 0, sequence 9), an older block of the
    same slot at location 1, and a checkpoint of that slot at location 6."""

    def setUp(self):
        newest = build_block([unit_record(1, 2)])
        older = bytearray(newest)
        struct.pack_into(">I", older, 0x48, 3)
        struct.pack_into(">I", older, 0x50, zlib.crc32(bytes(older[0x70:])))
        checkpoint = bytearray(0x6000)
        checkpoint[:0x4000] = newest
        checkpoint[0x60], checkpoint[0x63], checkpoint[0x65] = 3, 0, 8
        struct.pack_into(">I", checkpoint, 0x4C, 0x6000)
        struct.pack_into(">I", checkpoint, 0x50, zlib.crc32(bytes(checkpoint[0x70:])))
        gci = bytearray(build_gci(newest))
        for (rel, _), data in ((sf.BLOCK_LOCATIONS[1], older), (sf.BLOCK_LOCATIONS[6], checkpoint)):
            at = sf.GCI_HEADER_SIZE + rel
            gci[at:at + len(data)] = data
        self.save = sf.SaveFile.from_bytes(bytes(gci))

    def test_chapter_start_with_the_saved_army(self):
        data = sf.play_copy(self.save, 0, chapter=12)
        copy = sf.SaveFile.from_bytes(data)
        loaded = copy.loaded_blocks()
        self.assertEqual([b.location for b in loaded], [0])           # older block and checkpoint gone
        block = loaded[0]
        self.assertTrue(block.crc_ok)
        self.assertEqual((block.header.chapter, block.header.resume_point), (12, 4))
        self.assertEqual((block.party.chapter, block.party.resume_point, block.party.turn), (12, 4, 1))
        self.assertEqual(block.party.gold, 1234)
        self.assertEqual(len(block.unit_slots()), 1)

    def test_as_saved_keeps_the_block_and_leaves_the_editor_copy_alone(self):
        before = self.save.blocks[0].header.chapter
        copy = sf.SaveFile.from_bytes(sf.play_copy(self.save, 0))
        self.assertEqual(copy.loaded_blocks()[0].header.chapter, before)
        sf.play_copy(self.save, 0, chapter=20)
        self.assertEqual(self.save.blocks[0].header.chapter, before)

    def test_an_older_block_is_the_one_loaded_when_chosen(self):
        copy = sf.SaveFile.from_bytes(sf.play_copy(self.save, 1, chapter=7))
        self.assertEqual([(b.location, b.header.chapter) for b in copy.loaded_blocks()], [(1, 7)])

    def test_checkpoints_are_refused(self):
        with self.assertRaises(ValueError):
            sf.play_copy(self.save, 2)
