"""Radiant Dawn's FE10Data.cms: the byte moves on a synthetic container, and the record layouts and
edits against the retail file (``FE10_EXTRACTED_FILES`` / ``FE10_EXTRACTED``)."""

import os
import struct
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fe_modding.formats import fe8data, fe10data, lz10
from fe_modding.formats.fe8data import HEADER_SIZE


def _container(body: bytes, pointer_fields: list[int], symbols: list[tuple[str, int]]) -> bytes:
    """A minimal container: header, ``body`` as the data section, its pointer list and symbols."""
    names = b"".join(name.encode("ascii") + b"\0" for name, _ in symbols)
    table, name_at = b"", 0
    for name, offset in symbols:
        table += struct.pack(">II", offset, name_at)
        name_at += len(name) + 1
    tail = struct.pack(f">{len(pointer_fields)}I", *pointer_fields) + table + names
    header = struct.pack(">IIII", HEADER_SIZE + len(body) + len(tail), len(body), len(pointer_fields),
                         len(symbols)) + bytes(16)
    return header + body + tail


class ByteMoveTests(unittest.TestCase):
    def setUp(self):
        # data: [ptr -> "B"] [ptr -> "A"] [8 spare] "A\0\0\0" "B\0\0\0"; symbols on word 0 and on "A"
        body = struct.pack(">II", 20, 16) + bytes(8) + b"A\0\0\0B\0\0\0"
        self.data = _container(body, [0, 4], [("First", 0), ("Strings", 16)])

    def test_insert_moves_targets_fields_and_symbols(self):
        out = fe10data.insert_bytes(self.data, HEADER_SIZE + 8, bytes(8))
        self.assertEqual(fe10data.resolve(out, struct.unpack_from(">I", out, HEADER_SIZE)[0]), "B")
        self.assertEqual(fe10data.resolve(out, struct.unpack_from(">I", out, HEADER_SIZE + 4)[0]), "A")
        self.assertEqual(fe8data.symbol_offsets(out), {"First": 0, "Strings": 24})
        self.assertEqual(struct.unpack_from(">II", out, 0), (len(out), 24 + 8))

    def test_insert_then_delete_restores_the_file(self):
        out = fe10data.insert_bytes(self.data, HEADER_SIZE + 8, struct.pack(">I", 16), [0])
        self.assertIn(8, fe8data.pointer_list(out)[1])
        self.assertEqual(fe10data.resolve(out, struct.unpack_from(">I", out, HEADER_SIZE + 8)[0]), "A")
        out = bytearray(out)
        fe8data._pack_pointer(out, HEADER_SIZE + 8, 0)
        self.assertEqual(fe10data.delete_bytes(bytes(out), HEADER_SIZE + 8, 4), self.data)

    def test_delete_refuses_a_span_something_still_points_into(self):
        with self.assertRaises(ValueError):
            fe10data.delete_bytes(self.data, HEADER_SIZE + 16, 4)


def _files() -> Path | None:
    value = os.environ.get("FE10_EXTRACTED_FILES")
    if value:
        return Path(value)
    root = os.environ.get("FE10_EXTRACTED")
    return Path(root) / "files" if root else None


FILES = _files()


@unittest.skipUnless(FILES, "set FE10_EXTRACTED_FILES to the files/ folder of an extracted Radiant Dawn disc")
class RetailFe10DataTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = lz10.decompress((FILES / "FE10Data.cms").read_bytes())
        cls.db = fe10data.read_fe10data(cls.data)

    def _ends_match(self, data, db):
        for kind, following in (("character", "class"), ("class", "item"), ("item", "skill")):
            self.assertEqual(db.table(kind)[-1].end, fe10data.table_start(data, following), kind)

    def test_every_table_walks_to_the_next_symbol(self):
        self.assertEqual([len(self.db.table(k)) for k in fe10data.KINDS], [461, 171, 296, 142])
        self._ends_match(self.data, self.db)
        self.assertTrue(fe10data.is_fe10data(self.data))
        for kind in fe10data.KINDS:
            prefix = fe10data.ID_PREFIX[kind]
            for record in self.db.table(kind):
                self.assertTrue((record.id or "").startswith(prefix), (kind, record.index, record.id))

    def test_known_values(self):
        ike = self.db.characters[0]
        self.assertEqual((ike.values["pid"], ike.values["jid"], ike.values["level"]), ("PID_IKE", "JID_BRAVE", 11))
        self.assertEqual(ike.lists["skills"], ["SID_HERO", "SID_EQ_A"])
        self.assertEqual([ike.values[f"growth_{s.lower()}"] for s in fe10data.STAT_NAMES],
                         [65, 55, 10, 60, 35, 30, 40, 15])
        items = {r.id: r for r in self.db.items}
        iron = items["IID_IRONSWORD"].values
        self.assertEqual((iron["might"], iron["hit"], iron["weight"], iron["uses"], iron["range_max"]), (6, 90, 7, 50, 1))
        self.assertEqual(items["IID_ANGELROBE"].bonuses[0], 7)       # HP
        self.assertEqual(items["IID_RAGNELL"].bonuses[6], 5)         # Def
        self.assertEqual(items["IID_BOOTS"].bonuses[8], 2)           # Mov
        classes = {r.id: r for r in self.db.classes}
        self.assertEqual(classes["JID_BRAVE"].values["promotes_to"], "JID_VANGUARD")
        self.assertEqual(classes["JID_VANGUARD"].values["skill_capacity"], 60)
        skills = {r.id: r for r in self.db.skills}
        self.assertIn((1, "JID_PRIEST"), skills["SID_PARITY"].lists["conditions"])
        self.assertIn((0, "SFXC_HUMAN"), skills["SID_PARITY"].lists["requirements"])

    def test_field_edit(self):
        out = fe10data.patch_field(self.data, "character", 0, "level", 20)
        out = fe10data.patch_field(out, "character", 0, "bonus_str", -3)
        out = fe10data.patch_field(out, "item", 2, "price", 600)
        ike = fe10data.record(out, "character", 0)
        self.assertEqual((ike.values["level"], ike.values["bonus_str"]), (20, -3))
        self.assertEqual(fe10data.record(out, "item", 2).values["price"], 600)
        with self.assertRaises(ValueError):
            fe10data.patch_field(self.data, "character", 0, "level", 300)

    def test_label_edit_adds_a_missing_label_and_nulls_leave_the_pointer_list(self):
        out = fe10data.patch_field(self.data, "character", 0, "aid_1", "AID_NEW_TEST")
        self.assertEqual(fe10data.record(out, "character", 0).values["aid_1"], "AID_NEW_TEST")
        offset = fe10data.record(out, "character", 0).offsets["aid_1"]
        self.assertIn(offset, fe8data.listed_pointer_fields(out))
        out = fe10data.patch_field(out, "character", 0, "aid_1", None)
        self.assertNotIn(offset, fe8data.listed_pointer_fields(out))

    def test_growing_and_shrinking_a_character_skill_list(self):
        grown = fe10data.set_list(self.data, "character", 0, "skills", ["SID_HERO", "SID_EQ_A", "SID_ASTRA"])
        db = fe10data.read_fe10data(grown)
        self.assertEqual(db.characters[0].lists["skills"], ["SID_HERO", "SID_EQ_A", "SID_ASTRA"])
        self._ends_match(grown, db)
        for kind in fe10data.KINDS:  # nothing else changed
            before = self.db.table(kind)[1:] if kind == "character" else self.db.table(kind)
            after = db.table(kind)[1:] if kind == "character" else db.table(kind)
            self.assertEqual([(r.values, r.lists, r.bonuses) for r in before],
                             [(r.values, r.lists, r.bonuses) for r in after], kind)
        self.assertEqual(fe10data.set_list(grown, "character", 0, "skills", ["SID_HERO", "SID_EQ_A"]), self.data)

    def test_class_list_and_item_bonus_round_trips(self):
        out = fe10data.set_list(self.data, "class", 0, "sounds", ["SFXC_HUMAN", "SFXC_ARMOR"])
        self.assertEqual(fe10data.record(out, "class", 0).lists["sounds"], ["SFXC_HUMAN", "SFXC_ARMOR"])
        self.assertEqual(fe10data.set_list(out, "class", 0, "sounds", ["SFXC_HUMAN"]), self.data)
        iron = next(r.index for r in self.db.items if r.id == "IID_IRONSWORD")
        out = fe10data.set_item_bonuses(self.data, iron, [0, 2, 0, 0, 0, 0, 0, 0, 0, 0])
        self.assertEqual(fe10data.record(out, "item", iron).bonuses[1], 2)
        self._ends_match(out, fe10data.read_fe10data(out))
        self.assertEqual(fe10data.set_item_bonuses(out, iron, None), self.data)

    def test_skill_condition_list_is_rewritten_and_relisted(self):
        parity = next(r for r in self.db.skills if r.id == "SID_PARITY")
        wanted = parity.lists["conditions"] + [(1, "PID_IKE")]
        out = fe10data.set_list(self.data, "skill", parity.index, "conditions", wanted)
        self.assertEqual(fe10data.record(out, "skill", parity.index).lists["conditions"], wanted)
        self.assertEqual(lz10.decompress(lz10.compress(out)), out)
        cleared = fe10data.set_list(out, "skill", parity.index, "conditions", [])
        self.assertEqual(fe10data.record(cleared, "skill", parity.index).lists["conditions"], [])


if __name__ == "__main__":
    unittest.main()
