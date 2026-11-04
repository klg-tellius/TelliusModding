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


class RdWeatherTests(unittest.TestCase):
    def test_rd_names_cover_every_id_the_story_maps_use(self):
        from fe_modding.gui.map_windows import RD_WEATHER_NAMES
        self.assertEqual(sorted(RD_WEATHER_NAMES), list(range(map_file.RD_WEATHER_MAX + 1)))
        self.assertTrue(RD_WEATHER_NAMES[5].startswith("Snow"))

    def test_rd_weather_accepts_ids_past_path_of_radiance_17(self):
        import os
        files = os.environ.get("FE10_EXTRACTED_FILES")
        if not files:
            self.skipTest("set FE10_EXTRACTED_FILES")
        from fe_modding import map_props
        _entries, contents = map_props.read_map_container(Path(files) / "zmap" / "bmap0101" / "map.cmp")
        data = contents["map.bin"]
        extra = map_file.read_map_bytes(data).extra
        out = map_file.patch_extra_mode(data, extra, "weather_id", 18)
        after = map_file.read_map_bytes(out).extra
        self.assertEqual(after.weather_id, 18)
        self.assertEqual(after.unknown_tail & ~map_file.MAP_EXTRA_WEATHER_MASK,
                         extra.unknown_tail & ~map_file.MAP_EXTRA_WEATHER_MASK)
        with self.assertRaises(map_file.MapFileError):
            map_file.patch_extra_mode(data, extra, "weather_id", 22)


if __name__ == "__main__":
    unittest.main()
