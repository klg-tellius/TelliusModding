"""FE10Conversation.cms: base conversations, Conversation Room supports, support chat lines
(formats/fe10_conversation_data.py). Corpus tests need ``FE10_EXTRACTED_FILES`` / ``FE10_EXTRACTED``."""

import os
import struct
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fe_modding.formats import fe10_conversation_data as cd
from fe_modding.formats import fe8data, lz10


def _files() -> Path | None:
    value = os.environ.get("FE10_EXTRACTED_FILES")
    if value:
        return Path(value)
    root = os.environ.get("FE10_EXTRACTED")
    return Path(root) / "files" if root else None


FILES = _files()


def container(symbols: list[tuple[bytes, int]]) -> bytes:
    """A minimal container: 8 data bytes, no pointers, the given symbols (in the given order)."""
    rows, names = bytearray(), bytearray()
    for name, offset in symbols:
        rows += struct.pack(">II", offset, len(names))
        names += name + b"\0"
    body = bytes(8) + rows + names
    return struct.pack(">IIII", 32 + len(body), 8, 0, len(symbols)) + bytes(16) + body


class SymbolTableTest(unittest.TestCase):
    def test_symbols_are_written_sorted_by_name_bytes(self):
        data = container([(b"B", 4), (b"A", 0)])
        self.assertEqual(cd.symbols(data), [("B", 4), ("A", 0)])
        sorted_data = cd.write_symbols(data, cd.symbols(data))
        self.assertEqual(cd.symbols(sorted_data), [("A", 0), ("B", 4)])
        self.assertEqual(struct.unpack_from(">I", sorted_data, 0)[0], len(sorted_data))
        japanese = cd.write_symbols(data, [("CONV_INFO_DATA_C0105_街", 0)])
        self.assertEqual(cd.symbols(japanese), [("CONV_INFO_DATA_C0105_街", 0)])


@unittest.skipUnless(FILES, "set FE10_EXTRACTED_FILES to the files/ folder of an extracted Radiant Dawn disc")
class CorpusTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = lz10.decompress((FILES / "FE10Conversation.cms").read_bytes())
        cls.lists = cd.read_conversation_data(cls.data)

    def test_tables(self):
        lists = self.lists
        self.assertEqual((len(lists.info), len(lists.fe8_yells), len(lists.mini_yells)), (101, 68, 71))
        first = lists.info[0]
        self.assertEqual(first.symbol, "CONV_INFO_DATA_C0105_街の中で")
        self.assertEqual(first.name, "街の中で")
        self.assertEqual(first.values["message"], "MID_0105_街の中で会話")
        self.assertEqual(first.pids, ["PID_MICAIAH", "PID_SOTHE", "PID_MEG"])
        self.assertTrue(all(r.symbol for r in lists.info))
        self.assertTrue(all(r.values["number"] in (1, 2, 3) for r in lists.info))
        yell = lists.fe8_yells[1]
        self.assertEqual((yell.values["mpid_a"], yell.values["mpid_b"]), ("MPID_IKE", "MPID_OSCAR"))
        self.assertEqual(yell.values["message_1"], "MYELL_8_IKE_OSCAR_A")
        ike = lists.mini_yells[0]
        self.assertEqual((ike.pid, ike.file, len(ike.partners)), ("PID_IKE", "Mess/yell_mini_1.m", 71))
        self.assertTrue(all(len(c.partners) == 71 for c in lists.mini_yells))

    def test_the_tables_end_where_the_string_pool_starts(self):
        last = self.lists.mini_yells[-1]
        end = last.offset + 12 + 12 * len(last.partners)
        targets = [struct.unpack_from(">I", self.data, f)[0] for f in fe8data.listed_pointer_fields(self.data)]
        self.assertEqual(end - 0x20, min(targets))

    def test_symbol_rewrite_is_identity(self):
        self.assertEqual(cd.write_symbols(self.data, cd.symbols(self.data)), self.data)

    def test_edits(self):
        data = cd.patch_info(self.data, 0, "pid_4", "PID_IKE")
        self.assertEqual(cd.read_conversation_data(data).info[0].pids[-1], "PID_IKE")
        data = cd.patch_info(self.data, 0, "number", 2)
        self.assertEqual(cd.read_conversation_data(data).info[0].values["number"], 2)
        data = cd.patch_info(self.data, 0, "chapter", "C0106")
        self.assertEqual(cd.read_conversation_data(data).info[0].symbol, "CONV_INFO_DATA_C0106_街の中で")
        data = cd.rename_info(self.data, 0, "外")
        self.assertEqual(cd.read_conversation_data(data).info[0].name, "外")
        with self.assertRaises(ValueError):
            cd.rename_info(self.data, 1, "街の中で")  # 0 already has that symbol in C0105
        data = cd.patch_fe8_yell(self.data, 0, "flag_1", "FLG_NEW")
        self.assertEqual(cd.read_conversation_data(data).fe8_yells[0].values["flag_1"], "FLG_NEW")
        data = cd.patch_mini_yell(self.data, 0, 1, 2, "MMY_NEW")
        self.assertEqual(cd.read_conversation_data(data).mini_yells[0].partners[1][2], "MMY_NEW")

    def test_add_then_remove_restores_the_file(self):
        data, index = cd.add_info(self.data, 5, "テスト")
        lists = cd.read_conversation_data(data)
        self.assertEqual(index, 101)
        self.assertEqual(lists.info[index].symbol, "CONV_INFO_DATA_C0106_テスト")
        self.assertEqual(lists.info[index].values, self.lists.info[5].values)
        self.assertEqual(lists.fe8_yells[0].values, self.lists.fe8_yells[0].values)
        self.assertEqual(lists.mini_yells[-1].partners, self.lists.mini_yells[-1].partners)
        self.assertEqual(cd.remove_info(data, index), self.data)
        with self.assertRaises(ValueError):
            cd.add_info(self.data, 0, "街の中で")
        removed = cd.read_conversation_data(cd.remove_info(self.data, 0))
        self.assertEqual(len(removed.info), 100)
        self.assertEqual(removed.info[0].symbol, self.lists.info[1].symbol)


if __name__ == "__main__":
    unittest.main()
