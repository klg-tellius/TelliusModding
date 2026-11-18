"""Radiant Dawn's glossary tables (``dictionary.bin`` / ``dictionaryF.bin``) on synthetic files
(no disc needed, runs in CI)."""

import unittest

from fe_modding.formats import fe10_dictionary as fd


def _dictionary(relation_size: int = 24) -> fd.Dictionary:
    return fd.Dictionary(
        categories=[fd.Category("MDIK_PERSON"), fd.Category("MDIK_WORD")],
        people=[fd.Person("PID_ALPHA", "MDICN_A", "MDIC_ALPHA", 10, 20),
                fd.Person("PID_ALPHA", None, "MDIC_ALPHA_2", faded=1),
                fd.Person("PID_BETA", "MDICN_A", "MDIC_BETA")],
        relations=[fd.Relation("線1", 1, 2, "MDIL_FRIEND", 1, 30, 40,
                               (31, 41) if relation_size == 24 else None)],
        affiliations=[fd.Affiliation("枠A", 5, 6, "旗A", 7, 8)],
        terms=[fd.Term("MDIN_LAND", "MDIR_LAND", "MDIC_LAND", "用語A"), fd.Term("MDIN_X", None, "MDIC_X")],
        relation_size=relation_size)


def _flags() -> fd.DictionaryFlags:
    return fd.DictionaryFlags(tables=[
        [fd.FlagEntry(1, "DF_人物_A"), fd.FlagEntry(2, "DF_人物_A2"), fd.FlagEntry(3, "DF_人物_B")],
        [fd.FlagEntry(1, "DF_関係_1")],
        [fd.FlagEntry(1, "DF_国_A")],
        [fd.FlagEntry(1, "DF_用語_LAND"), fd.FlagEntry(2, "DF_用語_X")],
    ])


class DictionaryTests(unittest.TestCase):
    def test_both_relation_layouts_round_trip(self):
        for size in (24, 20):
            source = _dictionary(size)
            data = fd.build_dictionary(source)
            back = fd.read_dictionary(data)
            self.assertEqual(back.relation_size, size)
            self.assertEqual((back.people, back.relations, back.affiliations, back.terms),
                             (source.people, source.relations, source.affiliations, source.terms))
            self.assertEqual(fd.build_dictionary(back), data)

    def test_flags_round_trip_and_check(self):
        data = fd.build_dictionary_flags(_flags())
        flags = fd.read_dictionary_flags(data)
        self.assertEqual(flags.tables, _flags().tables)
        self.assertEqual(fd.build_dictionary_flags(flags), data)
        self.assertEqual(fd.check(_dictionary(), flags), [])

    def test_check_reports_problems(self):
        dictionary, flags = _dictionary(), _flags()
        flags.tables[0][2] = fd.FlagEntry(2, "DF_用語_WRONG")
        flags.tables[1].append(fd.FlagEntry(64, "DF_関係_FAR"))
        problems = fd.check(dictionary, flags)
        self.assertTrue(any("does not start with this table's prefix" in p for p in problems))
        self.assertTrue(any("share bit 2" in p for p in problems))
        self.assertTrue(any("1 entries but 2 flags" in p for p in problems))
        self.assertTrue(any("bits 0-63" in p for p in problems))

    def test_add_and_remove_entry(self):
        dictionary, flags = _dictionary(), _flags()
        bit = fd.add_entry(dictionary, flags, 3, fd.Term("MDIN_NEW", None, "MDIC_NEW"), "DF_用語_NEW")
        self.assertEqual(bit, 3)
        self.assertEqual(fd.check(dictionary, flags), [])
        again = fd.read_dictionary(fd.build_dictionary(dictionary))
        self.assertEqual(again.terms[-1].name, "MDIN_NEW")
        fd.remove_entry(dictionary, flags, 0, 1)
        self.assertEqual([p.text for p in dictionary.people], ["MDIC_ALPHA", "MDIC_BETA"])
        self.assertEqual(fd.check(dictionary, flags), [])

    def test_flag_locations_and_chart(self):
        self.assertEqual(fd.flag_location("DF_所属_X"), (2, 0x18D4))
        self.assertIsNone(fd.flag_location("EID_X"))
        self.assertTrue(_dictionary().people[0].on_chart)
        self.assertFalse(_dictionary().people[2].on_chart)

    def test_damaged_file_is_refused(self):
        data = fd.build_dictionary(_dictionary())
        with self.assertRaises(ValueError):  # the pool file itself is cut
            fd.read_dictionary(data[:0x30])
        # a category count of 9 runs the tables out of step with the pointers
        damaged = data[:0x20] + (9).to_bytes(4, "big") + data[0x24:]
        with self.assertRaisesRegex(fd.DictionaryError, "known layout"):
            fd.read_dictionary(damaged)


if __name__ == "__main__":
    unittest.main()
