"""Radiant Dawn's small table files: the shared pool-file writer and the codecs built on it.

The disc checks run on every Radiant Dawn disc given:

    FE10_EXTRACTED / FE10_EXTRACTED_FILES   the US one
    FE10_EU_EXTRACTED, FE10_JP_EXTRACTED     the European and Japanese ones
"""

from __future__ import annotations

import os
import unittest
from pathlib import Path

from fe_modding.formats import fe10_conversation_room as cr
from fe_modding.formats import fe10_dictionary as fd
from fe_modding.formats import fe10_epilogue as ep
from fe_modding.formats import fe10_intro as fi
from fe_modding.formats import pool_file as pf


def discs() -> list[Path]:
    """Every distinct extracted ``files/`` folder named by the environment."""
    found = []
    for name in ("FE10_EXTRACTED_FILES", "FE10_EXTRACTED", "FE10_EU_EXTRACTED", "FE10_JP_EXTRACTED"):
        value = os.environ.get(name)
        if not value:
            continue
        root = Path(value)
        files = root if name.endswith("_FILES") else root / "files"
        if files.is_dir() and files.resolve() not in {f.resolve() for f in found}:
            found.append(files)
    return found


def disc_files(name: str) -> list[Path]:
    return [files / name for files in discs() if (files / name).is_file()]


class PoolFileTests(unittest.TestCase):
    def test_strings_are_pooled_once_and_sorted(self):
        doc = pf.PoolFile(bytes(12), {0: "b", 4: "a", 8: "b"}, [("TABLE", 0)])
        data = pf.build_pool_file(doc)
        again = pf.read_pool_file(data)
        self.assertEqual(again.pointers, {0: "b", 4: "a", 8: "b"})
        self.assertEqual(again.symbols, [("TABLE", 0)])
        payload = data[0x20:0x20 + int.from_bytes(data[4:8], "big")]
        self.assertEqual(payload[12:], b"a\0b\0")
        self.assertEqual(pf.build_pool_file(again), data)

    def test_rejects_a_field_outside_the_tables(self):
        with self.assertRaises(pf.PoolFileError):
            pf.build_pool_file(pf.PoolFile(bytes(4), {4: "x"}))

    def test_retail_files_rebuild_unchanged(self):
        names = ("dictionary.bin", "dictionaryF.bin", "conversationroom.bin", "FE10Epilogue.bin", "FE10Intro.bin")
        paths = [p for n in names for p in disc_files(n)]
        if not paths:
            self.skipTest("set FE10_EXTRACTED (and the EU/JP variables) to extracted Radiant Dawn discs")
        for path in paths:
            data = path.read_bytes()
            self.assertEqual(pf.build_pool_file(pf.read_pool_file(data)), data, path)


class DictionaryTests(unittest.TestCase):
    def _pairs(self):
        pairs = [(f / "dictionary.bin", f / "dictionaryF.bin") for f in discs() if (f / "dictionary.bin").is_file()]
        if not pairs:
            self.skipTest("set FE10_EXTRACTED to an extracted Radiant Dawn disc")
        return pairs

    def test_retail_glossary_reads_and_rebuilds(self):
        for entries, flags in self._pairs():
            data, flag_data = entries.read_bytes(), flags.read_bytes()
            dictionary = fd.read_dictionary(data)
            table = fd.read_dictionary_flags(flag_data)
            self.assertEqual(fd.build_dictionary(dictionary), data, entries)
            self.assertEqual(fd.build_dictionary_flags(table), flag_data, flags)
            self.assertEqual([len(dictionary.table(i)) for i in range(4)], [103, 56, 18, 61])
            self.assertEqual(fd.check(dictionary, table), [])
            self.assertEqual([c.label for c in dictionary.categories], ["MDIK_PERSON", "MDIK_WORD"])
            ike = dictionary.people[0]
            self.assertEqual((ike.pid, ike.text, ike.on_chart), ("PID_IKE", "MDIC_IKE", True))

    def test_japanese_relations_are_shorter(self):
        for entries, _flags in self._pairs():
            dictionary = fd.read_dictionary(entries.read_bytes())
            japanese = all(r.original_label is None for r in dictionary.relations)
            self.assertEqual(dictionary.relation_size, 20 if japanese else 24)

    def test_adding_an_entry_keeps_the_tables_in_step(self):
        entries, flags = self._pairs()[0]
        dictionary = fd.read_dictionary(entries.read_bytes())
        table = fd.read_dictionary_flags(flags.read_bytes())
        bit = fd.add_entry(dictionary, table, 3, fd.Term("MDIN_NEW", None, "MDIC_NEW"), "DF_用語新しい")
        self.assertEqual(bit, 62)
        again = fd.read_dictionary(fd.build_dictionary(dictionary))
        again_flags = fd.read_dictionary_flags(fd.build_dictionary_flags(table))
        self.assertEqual(again.terms[-1], fd.Term("MDIN_NEW", None, "MDIC_NEW"))
        self.assertEqual(again_flags.tables[3][-1], fd.FlagEntry(62, "DF_用語新しい"))
        self.assertEqual(fd.check(again, again_flags), [])
        fd.remove_entry(again, again_flags, 3, len(again.terms) - 1)
        self.assertEqual(fd.build_dictionary(again), entries.read_bytes())

    def test_check_names_mismatched_tables(self):
        dictionary = fd.Dictionary(people=[fd.Person("PID_A", None, "MDIC_A")])
        flags = fd.DictionaryFlags(tables=[[fd.FlagEntry(1, "DF_用語A"), fd.FlagEntry(1, "DF_人物B")], [], [], []])
        problems = fd.check(dictionary, flags)
        self.assertTrue(any("1 entries but 2 flags" in p for p in problems))
        self.assertTrue(any("prefix" in p for p in problems))
        self.assertTrue(any("share bit 1" in p for p in problems))


class ConversationRoomTests(unittest.TestCase):
    def test_retail_lists(self):
        paths = disc_files("conversationroom.bin")
        if not paths:
            self.skipTest("set FE10_EXTRACTED to an extracted Radiant Dawn disc")
        for path in paths:
            data = path.read_bytes()
            room = cr.read_conversation_room(data)
            self.assertEqual(cr.build_conversation_room(room), data, path)
            self.assertEqual((len(room.chapters), len(room.characters)), (35, 69))
            self.assertEqual((room.chapters[0].value, room.characters[-1].value), ("C0105", cr.OTHER))

    def test_edit_round_trips(self):
        room = cr.ConversationRoom([cr.ListItem("C0101")], [cr.ListItem("PID_IKE"), cr.ListItem(cr.OTHER)])
        again = cr.read_conversation_room(cr.build_conversation_room(room))
        self.assertEqual(again.chapters, room.chapters)
        self.assertEqual(again.characters, room.characters)


class EpilogueTests(unittest.TestCase):
    def test_retail_endings(self):
        paths = disc_files("FE10Epilogue.bin")
        if not paths:
            self.skipTest("set FE10_EXTRACTED to an extracted Radiant Dawn disc")
        for path in paths:
            data = path.read_bytes()
            endings = ep.read_epilogues(data)
            self.assertEqual(ep.build_epilogues(endings), data, path)
            self.assertEqual(len(endings.entries), 72)
            micaiah = endings.entries[0]
            self.assertEqual((micaiah.pid, micaiah.alive_partner, micaiah.alive_ending),
                             ("PID_MICAIAH", "PID_PELLEAS", "MEP_ALIVE_MICAIAH_2"))
            self.assertEqual(ep.check(endings), [])

    def test_check_wants_both_halves_of_an_alternative(self):
        data = ep.EpilogueData(entries=[ep.Epilogue("PID_A", "MEP_ALIVE_A", support_partner="PID_B")])
        self.assertTrue(ep.check(data))
        again = ep.read_epilogues(ep.build_epilogues(data))
        self.assertEqual(again.entries, data.entries)


class IntroTests(unittest.TestCase):
    def test_retail_class_introductions(self):
        paths = disc_files("FE10Intro.bin")
        if not paths:
            self.skipTest("set FE10_EXTRACTED to an extracted Radiant Dawn disc")
        for path in paths:
            data = path.read_bytes()
            intros = fi.read_intros(data)
            self.assertEqual(fi.build_intros(intros), data, path)
            self.assertEqual(len(intros.entries), 68)
            first = intros.entries[0]
            self.assertEqual((first.jid, first.picture, first.text), ("JID_BLADE", "blade", "MS_INTRO_BLADE"))
            for entry in intros.entries:
                self.assertTrue((path.parent / "intro" / f"{entry.picture}.cms").is_file(), entry.picture)

    def test_motion_list_edits(self):
        intro = fi.ClassIntro(1, "u", "JID_X", "bg", "sky", "cam", "pic", "MS_INTRO_X")
        intro.motion_list = "攻撃１, 構え"
        self.assertEqual(intro.motions, ["攻撃１", "構え"])
        with self.assertRaises(fi.IntroError):
            intro.motion_list = "a,b,c,d,e,f"
        again = fi.read_intros(fi.build_intros(fi.IntroData([intro])))
        self.assertEqual(again.entries, [intro])


if __name__ == "__main__":
    unittest.main()
