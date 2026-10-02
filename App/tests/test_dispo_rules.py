import unittest

from fe_modding.formats import dispo, dispo_rules


class DispoRulesTests(unittest.TestCase):
    def test_ai_hidden_on_inert_player_units_only(self):
        inert = ("SEQ_NOATTACK", "SEQ_NOMOVE", "SEQ_NOHEAL", 0)
        self.assertFalse(dispo_rules.show_ai(0, *inert))
        self.assertTrue(dispo_rules.show_ai(1, *inert))
        self.assertTrue(dispo_rules.show_ai(3, *inert))
        self.assertTrue(dispo_rules.show_ai(0, "SEQ_ALLUNITATTACK100", "SEQ_NOMOVE", "SEQ_NOHEAL", 0))
        self.assertTrue(dispo_rules.show_ai(0, *inert[:3], 4))

    def test_gauge_needs_laguz_or_existing_value(self):
        self.assertTrue(dispo_rules.show_laguz_gauge(True, 0))
        self.assertFalse(dispo_rules.show_laguz_gauge(False, 0))
        self.assertTrue(dispo_rules.show_laguz_gauge(False, 5))

    def test_laguz_lookup_without_data(self):
        self.assertFalse(dispo_rules.laguz_lookup(None)("JID_X", "PID_X"))

    def test_ring_flag_only_on_rings(self):
        self.assertTrue(dispo_rules.is_ring_item("IID_MAGESRING"))
        self.assertTrue(dispo_rules.is_ring_item("IID_COIN"))
        self.assertFalse(dispo_rules.is_ring_item("IID_VULNERARY"))
        masks = [b[0] for b in dispo_rules.item_flag_bits("IID_VULNERARY", 0)]
        self.assertEqual(masks, [dispo.ITEM_FLAG_DROP])
        masks = [b[0] for b in dispo_rules.item_flag_bits("IID_VULNERARY", dispo.ITEM_FLAG_RING)]
        self.assertIn(dispo.ITEM_FLAG_RING, masks)

    def test_unused_flag_bits_appear_when_set(self):
        self.assertNotIn(0x80, [b[0] for b in dispo_rules.unit_flag_bits(0x01)])
        self.assertIn(0x80, [b[0] for b in dispo_rules.unit_flag_bits(0x81)])
        self.assertIn(0x10, [b[0] for b in dispo_rules.unit_flag_bits(0x01)])

    def test_warnings(self):
        self.assertEqual(dispo_rules.warnings(1, True, 5, [("IID_COIN", 3)]), [])
        found = dispo_rules.warnings(0, False, 5, [("IID_VULNERARY", 3), ("IID_X", 1)])
        self.assertEqual(len(found), 3)


if __name__ == "__main__":
    unittest.main()
