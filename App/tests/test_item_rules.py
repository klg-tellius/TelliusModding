import sys
import struct
import unittest
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fe_modding.formats import fe8data, item_rules
from fe_modding.game_code.dol import Dol, DolError
from fe_modding.game_code import item_restrictions as code
from fe_modding.playthrough.world import World
from test_formats import _build_synthetic_fe8data
from test_game_code import build_dol


def _complete_fixture() -> bytes:
    """Wrap the old bare-table fixture in a relocatable HSDArc container."""
    raw = bytearray(_build_synthetic_fe8data())
    for kind in ("character", "class", "item"):
        _name, _size, default = fe8data.TABLES[kind]
        struct.pack_into(">I", raw, default - 4, 1)
    symbols = [(default - fe8data.HEADER_SIZE - 4, name)
               for name, _size, default in fe8data.TABLES.values() if default is not None]
    names = bytearray()
    entries = bytearray()
    for offset, name in symbols:
        entries += struct.pack(">II", offset, len(names))
        names += name.encode("ascii") + b"\0"
    struct.pack_into(">IIII", raw, 0, len(raw) + len(entries) + len(names),
                     len(raw) - fe8data.HEADER_SIZE, 0, len(symbols))
    return bytes(raw + entries + names)


class ItemRuleDataTests(unittest.TestCase):
    def setUp(self):
        self.data = _complete_fixture()
        self.rule = item_rules.ItemRule("IID_TESTITEM", "all", ("PID_TEST",),
                                        ("JID_TESTCLASS",), ("SID_TESTSKILL",))

    def test_archive_round_trip_and_replace(self):
        edited = item_rules.write_item_rules(self.data, {self.rule.iid: self.rule})
        self.assertEqual(item_rules.read_item_rules(edited), {self.rule.iid: self.rule})
        self.assertEqual(fe8data.read_fe8data(edited).item_rules[self.rule.iid], self.rule)
        replacement = item_rules.ItemRule(self.rule.iid, "any", (), (), ("SID_TESTSKILL2",))
        edited = item_rules.write_item_rules(edited, {replacement.iid: replacement})
        self.assertEqual(item_rules.read_item_rules(edited), {replacement.iid: replacement})
        self.assertEqual(item_rules.read_item_rules(item_rules.write_item_rules(edited, {})), {})

    def test_id_rename_copy_and_remove_follow_rules(self):
        edited = item_rules.write_item_rules(self.data, {self.rule.iid: self.rule})
        edited = fe8data.patch_item_field(edited, 0, "iid", "IID_RENAMED")
        self.assertIn("IID_RENAMED", item_rules.read_item_rules(edited))
        edited, copied = fe8data.add_record(edited, "item", "IID_COPIED", 0)
        self.assertIn("IID_COPIED", item_rules.read_item_rules(edited))
        edited = fe8data.remove_record(edited, "item", copied)
        self.assertNotIn("IID_COPIED", item_rules.read_item_rules(edited))

    def test_missing_id_is_rejected(self):
        rule = item_rules.ItemRule("IID_TESTITEM", pids=("PID_MISSING",))
        with self.assertRaisesRegex(ValueError, "PID_MISSING"):
            item_rules.write_item_rules(self.data, {rule.iid: rule})

    def test_match_modes(self):
        self.assertTrue(item_rules.rule_matches(self.rule, "PID_TEST", "JID_TESTCLASS", {"SID_TESTSKILL"}))
        self.assertFalse(item_rules.rule_matches(self.rule, "PID_TEST", "JID_TESTCLASS", set()))
        either = item_rules.ItemRule(self.rule.iid, "any", self.rule.pids, self.rule.jids, self.rule.sids)
        self.assertTrue(item_rules.rule_matches(either, "PID_TEST", "JID_OTHER", set()))
        self.assertFalse(item_rules.rule_matches(either, "PID_OTHER", "JID_OTHER", set()))

    def test_simulator_checks_current_class_and_skills(self):
        fe = fe8data.read_fe8data(item_rules.write_item_rules(self.data, {self.rule.iid: self.rule}))
        world = World(0, 0, [], [], fe)
        item = fe.items[0]
        unit = SimpleNamespace(pid="PID_TEST", jid="JID_TESTCLASS", skills=["SID_TESTSKILL"])
        self.assertTrue(world.custom_item_allowed(unit, item))
        unit.skills.clear()
        self.assertFalse(world.custom_item_allowed(unit, item))
        unit.skills.append("SID_TESTSKILL")
        unit.jid = "JID_TESTCLASS2"
        self.assertFalse(world.custom_item_allowed(unit, item))


class HookTests(unittest.TestCase):
    def test_hook_code_fits_its_section(self):
        base = 0x8036D000
        self.assertLessEqual(code.OFF_EQUIP + len(code._wrapper(base + code.OFF_EQUIP,
                            base + code.OFF_EQUIP_TRAMP, base + code.OFF_MATCH)), code.OFF_USE)
        self.assertLessEqual(code.OFF_MATCH + len(code._matcher(base + code.OFF_MATCH,
                            base + code.OFF_EQUAL, base + code.OFF_NAME, 0x8000D354, 0x80105BC0)),
                            code.OFF_EQUAL)

    def test_conflicting_prologue_refused(self):
        dol = build_dol()
        with self.assertRaises(DolError):
            code.install(dol, "GFEE01")


if __name__ == "__main__":
    unittest.main()
