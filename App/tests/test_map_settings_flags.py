"""Map settings: the map flag check boxes cover separate bits and leave weather and fog of war alone."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fe_modding.formats import map_file
from fe_modding.gui.map_windows import MAP_FLAG_BITS, MapSettingsForm


class MapFlagBitsTests(unittest.TestCase):
    def test_each_box_is_one_bit_outside_weather_and_sight(self):
        seen = 0
        for bit, _label, _help, _us_only in MAP_FLAG_BITS:
            self.assertEqual(bin(bit).count("1"), 1)
            self.assertFalse(bit & seen)
            self.assertFalse(bit & (map_file.MAP_EXTRA_SIGHT_MASK | map_file.MAP_EXTRA_WEATHER_MASK))
            seen |= bit

    def test_object_order_box_is_us_only(self):
        self.assertTrue(MapSettingsForm._flag_mask(True) & map_file.MAP_EXTRA_OBJECT_ORDER_MASK)
        self.assertFalse(MapSettingsForm._flag_mask(False) & map_file.MAP_EXTRA_OBJECT_ORDER_MASK)


if __name__ == "__main__":
    unittest.main()
