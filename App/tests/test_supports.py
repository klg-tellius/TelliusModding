import struct
import unittest

from fe_modding.formats import fe8data, supports

H = fe8data.HEADER_SIZE


def build_fe8data() -> bytes:
    """A small but complete FE8Data container: three characters at the real
    table offset, a string pool, DivineData, RelianceData (Ike/Mist and an
    empty slot) and KiznaData, then the pointer list and symbol table."""
    data = bytearray(0x10)  # file 0x20..0x30, before the character table
    data += bytes(3 * fe8data.CHARACTER_RECORD_SIZE)
    labels = {}

    def label(text: str) -> int:
        if text not in labels:
            while len(data) % 4:
                data.append(0)
            data.append(0)
            labels[text] = len(data)
            data.extend(text.encode("ascii") + b"\x00")
        return labels[text]

    pointers = []

    def ptr(at: int, value: int) -> None:
        if len(data) < at + 4:
            data.extend(bytes(at + 4 - len(data)))
        struct.pack_into(">I", data, at, value)
        pointers.append(at)

    pids = ["PID_IKE", "PID_MIST", "PID_BOLE"]
    for i, pid in enumerate(pids):
        ptr(0x10 + i * fe8data.CHARACTER_RECORD_SIZE, label(pid))
    for key in supports.AFFINITY_KEYS:
        label(key)
    ptr(0x10 + supports.CHARACTER_AFFINITY_OFFSET, labels["telius"])
    ptr(0x10 + fe8data.CHARACTER_RECORD_SIZE + supports.CHARACTER_AFFINITY_OFFSET, labels["water"])
    while len(data) % 4:
        data.append(0)

    symbols = {}
    symbols["DivineData"] = len(data)
    data += struct.pack(">I", 9)
    bonuses = [[0] * 8, [1, 0, 5, 0, 0, 0, 0, 0], [0, 1, 0, 5, 0, 0, 0, 0], [0, 0, 5, 5, 0, 0, 0, 0],
               [1, 1, 0, 0, 0, 0, 0, 0], [1, 0, 0, 5, 0, 0, 0, 0], [0, 1, 5, 0, 0, 0, 0, 0],
               [0, 0, 10, 0, 0, 0, 0, 0], [0, 0, 0, 10, 0, 0, 0, 0]]
    for key, bonus in zip(supports.AFFINITY_KEYS, bonuses):
        at = len(data)
        data += struct.pack(">I8b", 0, *bonus)
        ptr(at, labels[key])

    symbols["RelianceData"] = len(data)
    data += struct.pack(">I", 2)
    ptr(len(data), labels["PID_IKE"])
    data += struct.pack(">I", 2)
    ptr(len(data), labels["PID_MIST"])
    data += struct.pack(">4B", 3, 7, 11, 0)
    data += struct.pack(">I4B", 0, 0, 1, 2, 0)  # empty slot
    ptr(len(data), labels["PID_MIST"])
    data += struct.pack(">I", 1)
    ptr(len(data), labels["PID_IKE"])
    data += struct.pack(">4B", 3, 7, 11, 0)

    symbols["KiznaData"] = len(data)
    data += struct.pack(">I", 1)
    ptr(len(data), labels["PID_IKE"])
    ptr(len(data), labels["PID_MIST"])
    data += struct.pack(">BbH", 1, 10, 0) + bytes(4)

    pointers.sort()
    names = bytearray()
    table = bytearray()
    for name, off in symbols.items():
        table += struct.pack(">II", off, len(names))
        names += name.encode("ascii") + b"\x00"
    tail = struct.pack(f">{len(pointers)}I", *pointers) + table + names
    header = struct.pack(">IIII", H + len(data) + len(tail), len(data), len(pointers), len(symbols)) + bytes(16)
    return bytes(header + data + tail)


class SupportFormatTests(unittest.TestCase):
    def setUp(self):
        self.data = build_fe8data()

    def test_read_support_lists(self):
        lists = supports.read_support_lists(self.data)
        self.assertEqual([sl.owner for sl in lists], ["PID_IKE", "PID_MIST"])
        self.assertEqual(lists[0].slots[0], supports.SupportSlot("PID_MIST", 3, 7, 11))
        self.assertTrue(lists[0].slots[1].empty)
        self.assertEqual(supports.validate_support_lists(lists), [])
        self.assertEqual(len(supports.pairs(lists)), 1)

    def test_round_trips_are_identical(self):
        lists = supports.read_support_lists(self.data)
        self.assertEqual(supports.write_support_lists(self.data, lists), self.data)
        bonds = supports.read_bonds(self.data)
        self.assertEqual(bonds, [supports.Bond("PID_IKE", "PID_MIST", 1, 10)])
        self.assertEqual(supports.write_bonds(self.data, bonds), self.data)

    def test_set_pair_reuses_empty_slot_and_keeps_both_sides(self):
        lists = supports.read_support_lists(self.data)
        supports.set_pair(lists, "PID_IKE", "PID_BOLE", 2, 6, 10)
        self.assertEqual(lists[0].slots[1].partner, "PID_BOLE")  # the empty slot, index kept
        self.assertEqual(lists[-1].owner, "PID_BOLE")
        out = supports.write_support_lists(self.data, lists)
        self.assertNotEqual(fe8data.symbol_offsets(out)["RelianceData"],
                            fe8data.symbol_offsets(self.data)["RelianceData"])  # grew, so moved
        again = supports.read_support_lists(out)
        self.assertEqual(again, lists)
        self.assertEqual(supports.read_bonds(out), supports.read_bonds(self.data))
        # every listed pointer field still resolves inside the data section
        _size, data_size, count = struct.unpack(">III", out[:12])
        listed = struct.unpack_from(f">{count}I", out, H + data_size)
        self.assertTrue(all(struct.unpack_from(">I", out, H + p)[0] < data_size for p in listed))

    def test_remove_pair_leaves_empty_slots(self):
        lists = supports.read_support_lists(self.data)
        supports.remove_pair(lists, "PID_IKE", "PID_MIST")
        self.assertTrue(all(s.empty for sl in lists for s in sl.slots))
        self.assertEqual(len(lists[0].slots), 2)
        out = supports.write_support_lists(self.data, lists)
        _size, data_size, count = struct.unpack(">III", out[:12])
        _s, _d, old_count = struct.unpack(">III", self.data[:12])
        self.assertEqual(count, old_count - 2)  # the two partner pointers left the list

    def test_validation_catches_one_sided_pairs_and_bad_thresholds(self):
        lists = supports.read_support_lists(self.data)
        lists[1].slots = []
        self.assertTrue(any("does not list" in p for p in supports.validate_support_lists(lists)))
        with self.assertRaises(ValueError):
            supports.write_support_lists(self.data, lists)
        lists = supports.read_support_lists(self.data)
        lists[0].slots[0].b = 2
        self.assertTrue(any("must rise" in p for p in supports.validate_support_lists(lists)))

    def test_slot_limit(self):
        lists = [supports.SupportList("PID_IKE", [supports.SupportSlot(f"PID_{i}", 0, 1, 2) for i in range(10)])]
        with self.assertRaises(ValueError):
            supports.set_pair(lists, "PID_IKE", "PID_MIST", 1, 2, 3)

    def test_affinities(self):
        rows = supports.read_affinities(self.data)
        self.assertEqual([r.key for r in rows], supports.AFFINITY_KEYS)
        self.assertEqual(supports.character_affinity(self.data, 0), 8)  # telius = Earth
        self.assertEqual(supports.character_affinity(self.data, 2), 0)
        out = supports.patch_character_affinity(self.data, 2, 1)
        self.assertEqual(supports.character_affinity(out, 2), 1)
        self.assertEqual(supports.patch_character_affinity(out, 2, 0), self.data)
        out = supports.patch_affinity_bonus(self.data, 1, [2, 0, 10, 0, 0, 0])
        self.assertEqual(supports.read_affinities(out)[1].bonus[:6], [2, 0, 10, 0, 0, 0])

    def test_rank_and_bonus_math(self):
        slot = supports.SupportSlot("PID_MIST", 3, 7, 11)
        self.assertEqual([supports.rank_for_points(slot, p) for p in (0, 3, 4, 7, 8, 11, 12)], [0, 0, 1, 1, 2, 2, 3])
        rows = supports.read_affinities(self.data)
        # Earth (Avoid 10) with Water (Atk 1, Def 1) at A: (3*(0+1))>>1 = 1 Atk, 1 Def, 15 Avoid
        self.assertEqual(supports.pair_bonus(rows, 8, 4, 3), [1, 1, 0, 15, 0, 0])


if __name__ == "__main__":
    unittest.main()
