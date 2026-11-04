"""Radiant Dawn Battle Sceneries (FE10BMapModel) and Battle Unit Parameters (FE10BUnit) rows."""

import os
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fe_modding.game_profile import (BATTLE_PARAMS, BATTLE_SCENERIES, PATH_OF_RADIANCE_PROFILE,
                                     RADIANT_DAWN_PROFILE)

FE10 = os.environ.get("FE10_EXTRACTED_FILES")


class ProfileTests(unittest.TestCase):
    def test_both_games_have_the_pages(self):
        for feature in (BATTLE_SCENERIES, BATTLE_PARAMS):
            self.assertTrue(PATH_OF_RADIANCE_PROFILE.supports(feature), feature)
            self.assertTrue(RADIANT_DAWN_PROFILE.supports(feature), feature)

    def test_the_pages_pick_the_game(self):
        from fe_modding.gui import fe10_battle_rows as rows
        from fe_modding.gui.pages.assets import ASSET_FEATURES, TOOLS_BY_KEY
        self.assertIs(TOOLS_BY_KEY["battle_sceneries"][4], rows.battle_sceneries_panel)
        self.assertIs(TOOLS_BY_KEY["battle_params"][4], rows.battle_params_panel)
        self.assertEqual((ASSET_FEATURES["battle_sceneries"], ASSET_FEATURES["battle_params"]),
                         (BATTLE_SCENERIES, BATTLE_PARAMS))

    def test_parameter_steps(self):
        from fe_modding.formats import fe10_battle_units as fu
        self.assertEqual((fu.to_raw("5"), fu.to_raw("1.5"), fu.to_raw(-0.5)), (1280, 384, -128))
        with self.assertRaises(ValueError):
            fu.to_raw("200")
        with self.assertRaises(ValueError):
            fu.to_raw("fast")


@unittest.skipUnless(FE10, "set FE10_EXTRACTED_FILES to an extracted Radiant Dawn files/ directory")
class RdTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from fe_modding.formats import lz10
        cls.data = lz10.decompress((Path(FE10) / "FE10Battle.cms").read_bytes())

    def test_scenery_rows(self):
        from fe_modding.formats import fe10_battle_scenery as fs
        rows = fs.read_sceneries(self.data)
        self.assertEqual(len(rows), 146)
        town = rows[1]
        self.assertEqual((town.folder, town.sound_group, town.flags, town.foot_effect, town.ground),
                         ("bg0101twn", "SND_GROUP_C0101", 0x01, 1, 5))
        self.assertEqual((town.position, town.rotation, town.scale, town.scale_value()), ((-20, 0, 0), 10, 0x300, 3.0))
        room = rows[3]
        self.assertEqual((room.folder, room.indoors, room.flag_names()[1]), ("bg0103rom_a", True, "Indoors (no weather or sky)"))
        self.assertEqual(sum(r.flight_height == 70 for r in rows), 91)
        self.assertTrue(all(r.move_limit == r.camera_limit == 0 for r in rows))
        self.assertEqual(fs.foot_effects(self.data)[3], "Water spray (水煙)")
        self.assertIn(("bg0101街", 0), fs.map_uses(self.data)[1])

    def test_scenery_edit_keeps_other_bytes(self):
        from fe_modding.formats import fe10_battle_scenery as fs
        edited = fs.set_scenery(self.data, 1, flags=0x03, foot_effect=3, ground=2, flight_height=40,
                                position=(1, -2, 3), rotation=-90, scale=512)
        self.assertEqual(len(edited), len(self.data))
        after = fs.read_sceneries(edited)
        self.assertEqual((after[1].flags, after[1].foot_effect, after[1].ground, after[1].flight_height,
                          after[1].position, after[1].rotation, after[1].scale),
                         (0x03, 3, 2, 40, (1, -2, 3), -90, 512))
        self.assertEqual(after[0], fs.read_sceneries(self.data)[0])
        self.assertEqual(sum(a != b for a, b in zip(edited, self.data)), 12)
        old = fs.read_sceneries(self.data)[1]
        back = fs.set_scenery(edited, 1, flags=old.flags, foot_effect=old.foot_effect, ground=old.ground,
                              flight_height=old.flight_height, position=old.position, rotation=old.rotation,
                              scale=old.scale)
        self.assertEqual(back, self.data)
        with self.assertRaises(ValueError):
            fs.set_scenery(self.data, 1, ground=300)

    def test_unit_rows(self):
        from fe_modding.formats import fe10_battle_units as fu
        units = fu.read_units(self.data)
        self.assertEqual(len(units), 240)
        sword = units[0]
        self.assertEqual((sword.description, sword.model, sword.flags, sword.sound), ("剣士一般", "swoL", 1 << 17, 1))
        params = fu.param_names(self.data)
        self.assertEqual((len(params), params[1], params[5]), (20, "Attack range (間合い)", "Move speed (移動速度)"))
        self.assertEqual((sword.value(0), sword.value(1)), (1.5, 5.0))
        flags = fu.flag_names(self.data)
        self.assertEqual((len(flags), flags[0], flags[1], flags[17]), (18, "Large (大型)", "Flying (飛行系)", "Sound check (サウンド判定)"))
        self.assertEqual(fu.sound_sets(self.data)[2], "Armour (鎧系)")

    def test_unit_edit_keeps_other_bytes(self):
        from fe_modding.formats import fe10_battle_units as fu
        old = fu.read_units(self.data)[0]
        edited = fu.set_unit(self.data, 0, flags=old.flags | 0b11, params={1: fu.to_raw(7.25)}, sound=2)
        after = fu.read_units(edited)[0]
        self.assertEqual((after.flags, after.value(1), after.sound, after.params[0]), (old.flags | 0b11, 7.25, 2, 384))
        self.assertEqual(fu.read_units(edited)[1:], fu.read_units(self.data)[1:])
        back = fu.set_unit(edited, 0, flags=old.flags, params=dict(enumerate(old.params)), sound=old.sound)
        self.assertEqual(back, self.data)
        with self.assertRaises(ValueError):
            fu.set_unit(self.data, 0, sound=99)


if __name__ == "__main__":
    unittest.main()
