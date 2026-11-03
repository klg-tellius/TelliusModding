"""Phase 7 of the PoR/RD parity plan: Tutorials and Battle Weapons on Radiant Dawn, effect removal and
Animation Data editing on Path of Radiance."""

import os
import sys
import unittest
from dataclasses import replace
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fe_modding.game_profile import (BATTLE_WEAPONS, PATH_OF_RADIANCE_PROFILE, RADIANT_DAWN_PROFILE, TUTORIALS)

FE9 = os.environ.get("FE9_EXTRACTED_FILES")
FE10 = os.environ.get("FE10_EXTRACTED_FILES")


class ProfileTests(unittest.TestCase):
    def test_tools_on_both_games(self):
        for feature in (TUTORIALS, BATTLE_WEAPONS):
            self.assertTrue(PATH_OF_RADIANCE_PROFILE.supports(feature), feature)
            self.assertTrue(RADIANT_DAWN_PROFILE.supports(feature), feature)
        self.assertEqual(PATH_OF_RADIANCE_PROFILE.tutorial_files[0][1], "tut_data_en.bin")
        self.assertEqual([rel for _l, rel in RADIANT_DAWN_PROFILE.tutorial_files][:2],
                         ["Tutorial/tut_data_n_en.bin", "Tutorial/tut_data_h_en.bin"])
        self.assertEqual(len(RADIANT_DAWN_PROFILE.tutorial_flag_names), 4)
        self.assertEqual((PATH_OF_RADIANCE_PROFILE.battle_dialect, RADIANT_DAWN_PROFILE.battle_dialect),
                         ("zdbx", "fe10"))


@unittest.skipUnless(FE10, "set FE10_EXTRACTED_FILES to an extracted Radiant Dawn files/ directory")
class RdTests(unittest.TestCase):
    def test_every_tutorial_list_round_trips(self):
        from fe_modding.formats import tut_data
        for _label, rel in RADIANT_DAWN_PROFILE.tutorial_files:
            raw = (Path(FE10) / rel).read_bytes()
            doc = tut_data.read_tut_data(raw)
            self.assertEqual(tut_data.build_tut_data(doc), raw, rel)
            self.assertTrue(all(len(e.start_flags) == 4 for e in doc.entries))

    def test_weapon_rows(self):
        from fe_modding.formats import fe10_battle_weapons as fw, lz10
        data = lz10.decompress((Path(FE10) / "FE10Battle.cms").read_bytes())
        weapons = fw.read_weapons(data)
        self.assertEqual(len(weapons), 192)
        iron = next(w for w in weapons if w.labels["key"] == "IRONSWORD" and w.labels["model"] == "IRONSWORD")
        self.assertEqual((iron.type, iron.labels["hit"]), (1, "EID_K_ATTK1"))
        self.assertEqual(fw.weapon_types(data)[1], "sw (剣)")
        fire = next(w for w in weapons if w.labels["key"] == "FIRE")
        self.assertEqual((fire.labels["effect"], fire.labels["target"]), ("EID_K_FIRE", "EID_K_HEAD_FIRE"))
        edited = fw.set_weapon(data, iron.index, labels={"effect": "EID_K_FIRE"}, type=2)
        after = fw.read_weapons(edited)[iron.index]
        self.assertEqual((after.labels["effect"], after.type), ("EID_K_FIRE", 2))
        back = fw.set_weapon(edited, iron.index, labels={"effect": None}, type=1)
        self.assertEqual(back, data)


@unittest.skipUnless(FE9, "set FE9_EXTRACTED_FILES to an extracted Path of Radiance files/ directory")
class PorTests(unittest.TestCase):
    def test_effect_add_then_remove_is_the_original(self):
        from fe_modding.formats import effect_registry, effects
        data = (Path(FE9) / "FE8Effect.bin").read_bytes()
        added = effects.add_registry_record(data, "EID_PARITY_TEST", flags=0x500)
        self.assertEqual(effects.remove_registry_record(added, "EID_PARITY_TEST"), data)
        chained = next(r for r in effect_registry.read_effect_registry(data) if r.next_in_chain)
        with self.assertRaisesRegex(effects.EffectError, "chained"):
            effects.remove_registry_record(data, chained.next_in_chain)

    def test_anim_record_edit(self):
        from fe_modding.formats import anim_registry
        data = (Path(FE9) / "FE8Anim.bin").read_bytes()
        records = anim_registry.read_anim_registry(data)
        self.assertEqual(anim_registry.build_anim_registry(records), data)
        records[0] = replace(records[0], texture_ids=(9, 8, 7, 6), blend_weight=20)
        again = anim_registry.read_anim_registry(anim_registry.build_anim_registry(records))
        self.assertEqual((again[0].texture_ids, again[0].blend_weight), ((9, 8, 7, 6), 20))
        self.assertEqual(again[1:], anim_registry.read_anim_registry(data)[1:])


if __name__ == "__main__":
    unittest.main()
