"""Adding, removing and editing FE8Data.bin records and the smaller sections,
on a small but complete container (every section found through its symbol,
like the real file)."""

import os
import struct
import unittest
from dataclasses import asdict
from pathlib import Path

from fe_modding import fe8_references
from fe_modding.formats import fe8data, supports

H = fe8data.HEADER_SIZE


class _Builder:
    def __init__(self):
        self.data = bytearray()
        self.pointers: list[int] = []
        self.symbols: dict[str, int] = {}
        self.strings: dict[str, int] = {}
        self.pending: list[tuple[int, str]] = []

    def align(self):
        while len(self.data) % 4:
            self.data.append(0)

    def symbol(self, name: str):
        self.align()
        self.symbols[name] = len(self.data)

    def word(self, value: int = 0):
        self.data += struct.pack(">I", value)

    def ref(self, label):
        """A pointer word naming ``label`` (None: null), resolved in finish()."""
        if label is None:
            self.word(0)
        else:
            self.pending.append((len(self.data), label))
            self.pointers.append(len(self.data))
            self.word(0)

    def record(self, size: int, pointers: dict, raw: dict = None):
        start = len(self.data)
        self.data += bytes(size)
        for offset, label in pointers.items():
            if label is not None:
                self.pending.append((start + offset, label))
                self.pointers.append(start + offset)
        for offset, value in (raw or {}).items():
            self.data[start + offset] = value

    def finish(self) -> bytes:
        self.align()
        for _at, label in self.pending:
            if label not in self.strings:
                self.data.append(0)
                self.strings[label] = len(self.data)
                self.data += fe8data._encode_label(label) + b"\x00"
        self.align()
        for at, label in self.pending:
            struct.pack_into(">I", self.data, at, self.strings[label])
        names, table = bytearray(), bytearray()
        for name, off in self.symbols.items():
            table += struct.pack(">II", off, len(names))
            names += name.encode("ascii") + b"\x00"
        pointers = sorted(self.pointers)
        tail = struct.pack(f">{len(pointers)}I", *pointers) + table + names
        header = struct.pack(">IIII", H + len(self.data) + len(tail), len(self.data), len(pointers),
                             len(self.symbols)) + bytes(16)
        return bytes(header + self.data + tail)


def build() -> bytes:
    b = _Builder()
    b.symbol("DatabaseHead")
    b.word(0)
    b.ref("2005/06/29 10:11:21")
    b.ref("金子")
    b.symbol("PersonData")
    b.word(3)
    for pid, jid, sid in (("PID_IKE", "JID_RANGER", "SID_ELITE"), ("PID_MIST", "JID_CLERIC", None),
                          ("PID_BOLE", "JID_RANGER", None)):
        b.record(fe8data.CHARACTER_RECORD_SIZE, {0x00: pid, 0x04: "MPID_" + pid[4:], 0x10: jid, 0x14: "fire",
                                                 0x1C: sid}, {0x36: 1, 0x41: 50})
    b.symbol("JobData")
    b.word(2)
    b.record(fe8data.CLASS_RECORD_SIZE, {0x00: "JID_RANGER", 0x0C: "JID_CLERIC", 0x14: "D--------",
                                         0x2C: "human"}, {0x3E: 6, 0x40: 15})
    b.record(fe8data.CLASS_RECORD_SIZE, {0x00: "JID_CLERIC", 0x14: "-------D-", 0x2C: "human"}, {0x3E: 5})
    b.symbol("ItemData")
    b.word(1)
    b.record(fe8data.ITEM_RECORD_SIZE, {0x00: "IID_IRONSWORD", 0x0C: "sword", 0x10: "sword", 0x14: "E"},
             {0x43: 5})
    b.symbol("SkillData")
    b.word(2)
    for i, sid in enumerate(("SID_ELITE", "SID_COUNTER")):
        b.symbol(sid)
        b.record(fe8data.SKILL_RECORD_SIZE, {0x00: sid, 0x08: "MSID_" + sid[4:]}, {0x18: i, 0x19: i + 1})
    restriction = len(b.data)
    b.ref("PID_IKE")
    b.ref("JID_RANGER")
    struct.pack_into(">I", b.data, b.symbols["SID_ELITE"] + 0x24, restriction)
    b.pointers.append(b.symbols["SID_ELITE"] + 0x24)
    b.data[b.symbols["SID_ELITE"] + 0x1C] = 2
    b.symbol("GameData")
    b.data += bytes(range(28))
    b.symbol("TerrainData")
    b.word(0)
    b.symbol("BattleTerrData")
    b.data += struct.pack(">HH", 2, 2)
    for name, scenes in (("Map6", ("map01_woods", "map01_plain")), ("bmap01", (None, "map02_castle"))):
        b.ref(name)
        for scene in scenes:
            b.ref(scene)
    b.symbol("BattleSkyData")
    b.data += bytes([2, 0, 0, 0])
    b.ref("sky_01")
    b.ref(None)
    b.symbol("RelianceData")
    b.word(1)
    b.ref("PID_IKE")
    b.word(1)
    b.ref("PID_MIST")
    b.data += bytes([3, 7, 11, 0])
    b.symbol("ChapterData")
    b.word(2)
    for cid, script in ((0, "C00"), (1, "C01")):
        b.record(fe8data.CHAPTER_RECORD_SIZE, {0x00: f"MCT0{cid}", 0x04: f"bmap0{cid}", 0x08: script},
                 {0x3C: cid, 0x3F: 2})
    b.symbol("GroupData")
    b.word(2)
    b.ref(None)
    b.ref("MG_クリミア軍")
    b.symbol("KiznaData")
    b.word(1)
    b.ref("PID_IKE")
    b.ref("PID_MIST")
    b.data += bytes([1, 10, 0, 0])
    b.word(0)
    return b.finish()


def records(data: bytes) -> list:
    """Every decoded record without its file offset, for comparing files
    whose tables moved."""
    fe8 = fe8data.read_fe8data(data)
    out = []
    for table in (fe8.characters, fe8.classes, fe8.items, fe8.skills):
        out.append([{k: v for k, v in asdict(e).items() if k not in ("offset", "raw")} for e in table])
    out.append([{k: v for k, v in asdict(c).items() if k != "offset"} for c in fe8data.read_chapter_data(data)])
    return out


class TableTests(unittest.TestCase):
    def setUp(self):
        self.data = build()

    def test_container_reads(self):
        fe8 = fe8data.read_fe8data(self.data)
        self.assertEqual([c.pid for c in fe8.characters], ["PID_IKE", "PID_MIST", "PID_BOLE"])
        self.assertEqual([c.jid for c in fe8.classes], ["JID_RANGER", "JID_CLERIC"])
        self.assertEqual(fe8.skills[0].restricted_to, ["PID_IKE", "JID_RANGER"])
        self.assertEqual(fe8.classes[0].categories, ["human", None, None])
        self.assertEqual(len(supports.read_support_lists(self.data)), 1)

    def test_rewriting_a_table_unchanged_is_byte_identical(self):
        for kind in ("character", "class", "item", "skill", "chapter"):
            self.assertEqual(fe8data.write_table(self.data, kind, fe8data.read_table(self.data, kind)), self.data, kind)

    def test_add_copy_then_remove(self):
        before = records(self.data)
        for kind, new_id in (("character", "PID_NEW"), ("class", "JID_NEW"), ("item", "IID_NEW"), ("chapter", None)):
            data, index = fe8data.add_record(self.data, kind, new_id, copy_from=0)
            self.assertEqual(index, fe8data.table_count(self.data, kind))
            self.assertEqual(fe8data.table_count(data, kind), index + 1)
            self.assertEqual(struct.unpack_from(">I", data)[0], len(data))
            if kind == "chapter":
                chapters = fe8data.read_chapter_data(data)
                self.assertEqual(chapters[index].script, "C00")
                self.assertEqual(chapters[index].chapter_id, 33)  # the first free story id after the ending (32)
            else:
                fe8 = fe8data.read_fe8data(data)
                table = {"character": fe8.characters, "class": fe8.classes, "item": fe8.items}[kind]
                self.assertEqual(getattr(table[index], {"character": "pid", "class": "jid", "item": "iid"}[kind]),
                                 new_id)
            self.assertEqual(records(fe8data.remove_record(data, kind, index)), before, kind)
            # the other sections still read
            self.assertEqual(len(supports.read_bonds(data)), 1)

    def test_growing_again_uses_the_room_left_after_a_moved_table(self):
        data, _ = fe8data.add_record(self.data, "character", "PID_A")
        grown = len(data)
        data, _ = fe8data.add_record(data, "character", "PID_B")
        self.assertLess(len(data) - grown, fe8data.CHARACTER_RECORD_SIZE)  # only the new ID string
        self.assertEqual([c.pid for c in fe8data.read_fe8data(data).characters][-2:], ["PID_A", "PID_B"])

    def test_remove_and_move_keep_the_pointers(self):
        data = fe8data.remove_record(self.data, "character", 1)
        self.assertEqual([c.pid for c in fe8data.read_fe8data(data).characters], ["PID_IKE", "PID_BOLE"])
        data = fe8data.move_record(self.data, "character", 2, 0)
        fe8 = fe8data.read_fe8data(data)
        self.assertEqual([c.pid for c in fe8.characters], ["PID_BOLE", "PID_IKE", "PID_MIST"])
        self.assertEqual(fe8.characters[1].sids[0], "SID_ELITE")

    def test_refusals(self):
        with self.assertRaises(ValueError):
            fe8data.add_record(self.data, "character", "PID_MIST")  # taken
        with self.assertRaises(ValueError):
            fe8data.add_record(self.data, "class", "NOPREFIX")
        with self.assertRaises(ValueError):
            fe8data.add_record(self.data, "skill")
        with self.assertRaises(ValueError):
            fe8data.remove_record(self.data, "skill", 0)

    def test_references(self):
        refs = [str(r) for r in fe8_references.fe8data_references(self.data, "JID_RANGER")]
        self.assertIn("FE8Data.bin: character PID_IKE jid", refs)
        self.assertIn("FE8Data.bin: class JID_RANGER jid", refs)
        self.assertIn("FE8Data.bin: skill SID_ELITE restriction list", refs)
        refs = [str(r) for r in fe8_references.record_references(None, self.data, "character", 1)]
        self.assertEqual(refs, ["FE8Data.bin: support list of PID_IKE", "FE8Data.bin: bond PID_IKE / PID_MIST"])
        self.assertEqual(fe8_references.record_references(None, self.data, "character", 2), [])


class FieldTests(unittest.TestCase):
    def setUp(self):
        self.data = build()

    def test_character_fields(self):
        data = fe8data.patch_character_field(self.data, 0, "mpid", "MPID_NEWNAME")
        data = fe8data.patch_character_field(data, 0, "weapon_ranks", "b-------*")
        data = fe8data.patch_character_field(data, 0, "biorhythm_pattern", 300)
        data = fe8data.patch_character_field(data, 0, "biorhythm_phase", 12)
        data = fe8data.patch_character_field(data, 0, "fixed_growth_start3", 40)
        c = fe8data.read_fe8data(data).characters[0]
        self.assertEqual((c.mpid, c.weapon_ranks, c.biorhythm_pattern, c.biorhythm_phase, c.fixed_growth_start[3]),
                         ("MPID_NEWNAME", "B-------*", 300, 12, 40))
        with self.assertRaises(ValueError):
            fe8data.patch_character_field(self.data, 0, "pid", "PID_MIST")
        with self.assertRaises(ValueError):
            fe8data.patch_character_field(self.data, 0, "jid", "JID_NOSUCHCLASS")  # links must exist
        with self.assertRaises(ValueError):
            fe8data.patch_character_field(self.data, 0, "weapon_ranks", "DD")

    def test_class_fields(self):
        data = fe8data.patch_class_field(self.data, 0, "categories", ["armor", "human"])
        data = fe8data.patch_class_field(data, 0, "innate_weapon", "IID_IRONSWORD")
        data = fe8data.patch_class_field(data, 0, "vision", 3)
        data = fe8data.patch_class_field(data, 0, "growth_modifier2", -10)
        data = fe8data.patch_class_field(data, 1, "jid", "JID_PRIEST")
        fe8 = fe8data.read_fe8data(data)
        c = fe8.classes[0]
        self.assertEqual((c.categories, c.innate_weapon, c.vision, c.growth_modifiers[2]),
                         (["armor", "human", None], "IID_IRONSWORD", 3, -10))
        self.assertEqual(fe8.classes[1].jid, "JID_PRIEST")
        with self.assertRaises(ValueError):
            fe8data.patch_class_field(self.data, 0, "categories", ["nope"])

    def test_skill_fields(self):
        data = fe8data.patch_skill_field(self.data, 0, "sid", "SID_PARAGON")
        self.assertIn("SID_PARAGON", fe8data.symbol_offsets(data))
        self.assertNotIn("SID_ELITE", fe8data.symbol_offsets(data))
        self.assertEqual(fe8data.symbol_offsets(data)["SID_PARAGON"], fe8data.symbol_offsets(self.data)["SID_ELITE"])
        data = fe8data.patch_skill_field(data, 0, "restricted_to", ["PID_MIST"])  # shorter: in place
        self.assertEqual(len(data), len(fe8data.patch_skill_field(data, 0, "restricted_to", ["PID_IKE"])))
        data = fe8data.patch_skill_field(data, 0, "restricted_to", ["PID_IKE", "PID_MIST", "JID_CLERIC"])
        data = fe8data.patch_skill_field(data, 1, "skill_items", ["IID_IRONSWORD"])
        data = fe8data.patch_skill_field(data, 1, "japanese_name", "カウンター")
        skills = fe8data.read_fe8data(data).skills
        self.assertEqual(skills[0].sid, "SID_PARAGON")
        self.assertEqual(skills[0].restricted_to, ["PID_IKE", "PID_MIST", "JID_CLERIC"])
        self.assertEqual((skills[1].skill_items, skills[1].params[2], skills[1].japanese_name),
                         (["IID_IRONSWORD"], 1, "カウンター"))
        with self.assertRaises(ValueError):
            fe8data.patch_skill_field(self.data, 0, "sid", "SID_COUNTER")

    def test_small_sections(self):
        data = fe8data.patch_game_data(self.data, "boss_exp_bonus", 2, 99)
        self.assertEqual(fe8data.read_game_data(data)["boss_exp_bonus"][2], 99)
        data = fe8data.write_group_names(data, fe8data.read_group_names(data) + ["MG_新軍"])
        self.assertEqual(fe8data.read_group_names(data), [None, "MG_クリミア軍", "MG_新軍"])
        data = fe8data.write_battle_skies(data, ["cloudy_01", "sky_01", "night_01"])
        self.assertEqual(fe8data.read_battle_skies(data), ["cloudy_01", "sky_01", "night_01"])
        rows = fe8data.read_battle_terrain(data)
        rows.append(fe8data.BattleTerrainRow("bmap02", ["map01_woods", None]))
        data = fe8data.write_battle_terrain(data, rows)
        self.assertEqual([r.map_name for r in fe8data.read_battle_terrain(data)], ["Map6", "bmap01", "bmap02"])
        data = fe8data.patch_chapter_field(data, 1, "bgm", "BGM_NEW")
        data = fe8data.patch_chapter_field(data, 1, "trial_loss_grade2", 4)
        chapter = fe8data.read_chapter_data(data)[1]
        self.assertEqual((chapter.bgm, chapter.trial_loss_grades[2]), ("BGM_NEW", 4))
        with self.assertRaises(ValueError):
            fe8data.patch_chapter_field(data, 1, "chapter_id", 0)
        data = fe8data.patch_database_head(data, "today", "me")
        self.assertEqual(fe8data.read_database_head(data), ("today", "me"))
        self.assertEqual([c.pid for c in fe8data.read_fe8data(data).characters], ["PID_IKE", "PID_MIST", "PID_BOLE"])


@unittest.skipUnless(os.environ.get("FE9_EXTRACTED_FILES"), "set FE9_EXTRACTED_FILES to an extracted files/ directory")
class DiscTableTests(unittest.TestCase):
    def setUp(self):
        self.data = (Path(os.environ["FE9_EXTRACTED_FILES"]) / "FE8Data.bin").read_bytes()

    def test_vanilla_tables_rewrite_identically_and_survive_add_remove(self):
        before = records(self.data)
        groups = fe8data.read_group_names(self.data)
        for kind in ("character", "class", "item", "skill", "chapter"):
            self.assertEqual(fe8data.write_table(self.data, kind, fe8data.read_table(self.data, kind)), self.data)
        self.assertEqual(fe8data.write_group_names(self.data, groups), self.data)
        self.assertEqual(fe8data.write_battle_skies(self.data, fe8data.read_battle_skies(self.data)), self.data)
        self.assertEqual(fe8data.write_battle_terrain(self.data, fe8data.read_battle_terrain(self.data)), self.data)
        for kind, new_id in (("character", "PID_NEW"), ("class", "JID_NEW"), ("item", "IID_NEW"), ("chapter", None)):
            data, index = fe8data.add_record(self.data, kind, new_id, copy_from=0)
            self.assertEqual(len(supports.read_support_lists(data)), len(supports.read_support_lists(self.data)))
            self.assertEqual(records(fe8data.remove_record(data, kind, index)), before, kind)


if __name__ == "__main__":
    unittest.main()
