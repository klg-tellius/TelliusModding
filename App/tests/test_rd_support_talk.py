"""Radiant Dawn base support conversations: the Game Code patch and the pair's message IDs."""

import os
import struct
import unittest
from pathlib import Path

from fe_modding.game_code import entries_fe10  # noqa: F401  (registers the RD catalogue)
from fe_modding.game_code import rd_support_talk as talk
from fe_modding.game_code.catalog import CATALOG
from fe_modding.supports_model import PorSupports, RdSupports


class ConversationIdTests(unittest.TestCase):
    def test_ids_use_both_names_in_alphabetical_order(self):
        self.assertEqual(talk.conversation_id("PID_MICAIAH", "PID_EDDIE", "C"), "MSUP_EDDIE_MICAIAH_C")
        self.assertEqual(talk.conversation_id("PID_EDDIE", "PID_MICAIAH", "A"), "MSUP_EDDIE_MICAIAH_A")
        self.assertEqual(RdSupports.talk_id("PID_MICAIAH", "PID_EDDIE", "B"), "MSUP_EDDIE_MICAIAH_B")
        self.assertEqual(RdSupports.conversation_ranks, ("C", "B", "A"))

    def test_path_of_radiance_keeps_its_own_ids(self):
        self.assertEqual(PorSupports.talk_id("PID_IKE", "PID_MIST", "C"), "MYELL_IKE_MIST_C")


class PatchTests(unittest.TestCase):
    def test_patch_is_listed_and_repoints_the_two_script_steps(self):
        patch = CATALOG.entries["rd.support.base_talk"]
        edits = {e.address: e for e in patch.versions["RFEE01"]}
        self.assertEqual(edits[talk.SCRIPT_ESTABLISH].original, struct.pack(">I", talk.ESTABLISH))
        self.assertEqual(edits[talk.SCRIPT_ESTABLISH].patched, struct.pack(">I", talk.CODE))
        self.assertEqual(edits[talk.SCRIPT_AFTER].original, struct.pack(">I", talk.AFTER))
        self.assertEqual(edits[talk.SCRIPT_AFTER].patched, struct.pack(">I", talk.LABELS["wait"]))

    def test_code_and_data_fit_their_cave_ranges(self):
        self.assertLessEqual(talk.CODE + len(talk.CODE_BYTES), talk.FLAG)
        self.assertEqual(talk.DATA[:4], b"NCBA")
        self.assertTrue(talk.DATA[4:].startswith(b"MSUP_%s_%s_%c\0"))

    def test_retail_executable_holds_the_expected_script_words(self):
        root = os.environ.get("FE10_EXTRACTED_FILES")
        dol = Path(root).parent / "sys" / "main.dol" if root else None
        if dol is None or not dol.is_file():
            self.skipTest("set FE10_EXTRACTED_FILES to the files/ folder of an extracted Radiant Dawn disc")
        from fe_modding.game_code.dol import Dol
        retail = Dol.open(dol)
        if retail.read(talk.SCRIPT_ESTABLISH, 4) != struct.pack(">I", talk.ESTABLISH):
            self.skipTest("not the US disc")
        self.assertEqual(retail.read(talk.SCRIPT_AFTER, 4), struct.pack(">I", talk.AFTER))


if __name__ == "__main__":
    unittest.main()
