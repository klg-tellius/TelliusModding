"""FE10Battle.cms readers and editors on a synthetic file (no disc needed, runs in CI).

The retail checks in ``test_fe10_battle_rows`` / ``test_fe10_corpus`` need ``FE10_EXTRACTED_FILES``;
these build the file from :func:`synthetic_data.fe10_battle_file` instead.
"""

import unittest

from synthetic_data import fe10_battle_file

from fe_modding.formats import fe10_battle, fe10_battle_scenery, fe10_battle_units, fe10_battle_weapons


class Fe10BattleRoundTripTests(unittest.TestCase):
    def setUp(self):
        self.data = fe10_battle_file()
        self.doc = fe10_battle.read_fe10_battle(self.data)

    def test_unchanged_document_rebuilds_byte_identically(self):
        self.assertEqual(fe10_battle.build_fe10_battle(self.doc), self.data)

    def test_rebuilt_document_without_source_reads_back_equal(self):
        from dataclasses import replace
        rebuilt = fe10_battle.build_fe10_battle(replace(self.doc, _source=b""))
        again = fe10_battle.read_fe10_battle(rebuilt)
        self.assertEqual([[r.strings for r in t.records] for t in again.tables],
                         [[r.strings for r in t.records] for t in self.doc.tables])
        self.assertEqual(again.arrays, self.doc.arrays)

    def test_structures_are_decoded(self):
        self.assertEqual([m.map_name for m in self.doc.map_data], ["MAP_A", "MAP_B"])
        self.assertEqual(self.doc.map_data[0].model_indices, (0, None, 1, None, None))
        self.assertEqual([[c.file_index for c in g.choices] for g in self.doc.camera_groups], [[0, 2], [1]])
        self.assertEqual(self.doc.camera_context_names[3], "t03")
        self.assertEqual(self.doc.camera_lists[0].group_indices[0], (0, 1))
        self.assertEqual(self.doc.camera_lists[0].group_indices[1], (None, None))
        self.assertEqual([len(u.mappings) for u in self.doc.unit_texture_sets], [2, 1])
        self.assertEqual(self.doc.map_models[0].translation, (10, -20, 30))

    def test_map_model_fallback_order(self):
        record = self.doc.map_data[0]
        self.assertEqual(self.doc.map_model(record, 3).record_index, 1)  # 3 falls back to 2
        self.assertEqual(self.doc.map_model(record, 4).record_index, 0)  # then to 0
        self.assertIsNone(self.doc.map_model(self.doc.map_data[1], 0))
        with self.assertRaises(IndexError):
            self.doc.map_model(record, 5)

    def test_missing_symbol_is_refused(self):
        damaged = self.data.replace(b"FE10BSky\0", b"FE10BSkz\0")
        with self.assertRaisesRegex(ValueError, "missing symbols"):
            fe10_battle.read_fe10_battle(damaged)

    def test_wrong_row_size_is_refused(self):
        from dataclasses import replace
        table = self.doc.table("FE10BSky")
        bad = replace(table, records=(replace(table.records[0], raw=b"\0" * 4),))
        doc = replace(self.doc, tables=tuple(bad if t.name == "FE10BSky" else t for t in self.doc.tables))
        with self.assertRaisesRegex(ValueError, "wrong size"):
            fe10_battle.build_fe10_battle(doc)


class Fe10BattleEditTests(unittest.TestCase):
    def setUp(self):
        self.data = fe10_battle_file()

    def read(self, data):
        return fe10_battle.read_fe10_battle(data)

    def test_update_record_adds_a_new_string(self):
        out = fe10_battle.update_battle_record(self.data, "FE10BWeapon", 1, strings={8: "handaxe"})
        self.assertEqual(dict(self.read(out).table("FE10BWeapon").records[1].strings)[8], "handaxe")
        with self.assertRaises(IndexError):
            fe10_battle.update_battle_record(self.data, "FE10BWeapon", 9)
        with self.assertRaises(ValueError):
            fe10_battle.update_battle_record(self.data, "FE10BWeapon", 0, strings={2: "x"})
        with self.assertRaises(ValueError):
            fe10_battle.update_battle_record(self.data, "FE10BWeapon", 0, raw=b"\0")

    def test_clone_and_remove_map_model(self):
        out, index = fe10_battle.clone_map_model(self.data, 0, "bg99")
        self.assertEqual(index, 3)
        self.assertEqual(self.read(out).map_models[3].archive_name, "bg99")
        with self.assertRaisesRegex(ValueError, "MAP_A"):
            fe10_battle.remove_map_model(out, 0)
        # model 2 is unused: removing it keeps MAP_A's indices; removing 0 after unlinking shifts them
        self.assertEqual(self.read(fe10_battle.remove_map_model(out, 2)).map_data[0].model_indices,
                         (0, None, 1, None, None))
        unlinked = fe10_battle.set_map_model_variant(self.data, 0, 0, None)
        shifted = self.read(fe10_battle.remove_map_model(unlinked, 0))
        self.assertEqual(shifted.map_data[0].model_indices, (None, None, 0, None, None))

    def test_set_map_model_variant_checks_ranges(self):
        out = fe10_battle.set_map_model_variant(self.data, 1, 4, 2)
        self.assertEqual(self.read(out).map_data[1].model_indices[4], 2)
        self.assertEqual(len(out), len(self.data))
        for args in ((5, 0, 0), (0, 5, 0), (0, 0, 9)):
            with self.assertRaises(IndexError):
                fe10_battle.set_map_model_variant(self.data, *args)

    def test_camera_files(self):
        out, index = fe10_battle.clone_camera_file(self.data, 1, "cam99", "new clip")
        rows = self.read(out).table("FE10BCamFile").records
        self.assertEqual(dict(rows[index].strings), {0: "new clip", 4: "cam99"})
        with self.assertRaisesRegex(ValueError, "already registered"):
            fe10_battle.clone_camera_file(out, 0, "cam99")
        with self.assertRaisesRegex(ValueError, "still used"):
            fe10_battle.remove_camera_file(self.data, 0)
        removed = self.read(fe10_battle.remove_camera_file(out, 3))
        self.assertEqual(len(removed.table("FE10BCamFile").records), 3)

    def test_removing_a_camera_file_remaps_later_choices(self):
        # free clip 1 by pointing group 1 at clip 0, then remove clip 1: clip 2 becomes 1
        doc = self.read(self.data)
        from dataclasses import replace
        doc = fe10_battle._replace_array(doc, "FE10BCamFileIndex", bytes([0, 2, 0]))
        data = fe10_battle.build_fe10_battle(replace(doc, _source=b""))
        out = self.read(fe10_battle.remove_camera_file(data, 1))
        self.assertEqual([[c.file_index for c in g.choices] for g in out.camera_groups], [[0, 1], [0]])

    def test_camera_weights_and_dispatch(self):
        out = fe10_battle.set_camera_choice_weight(self.data, 0, 1, 75)
        self.assertEqual(self.read(out).camera_groups[0].choices[1].selection_weight, 75)
        with self.assertRaises(ValueError):
            fe10_battle.set_camera_choice_weight(self.data, 0, 0, 101)
        with self.assertRaises(IndexError):
            fe10_battle.set_camera_choice_weight(self.data, 1, 1, 10)
        out = fe10_battle.set_camera_dispatch_group(self.data, 0, 2, 1, 1)
        self.assertEqual(self.read(out).camera_lists[0].group_indices[2], (None, 1))
        out = fe10_battle.set_camera_dispatch_group(out, 0, 0, 0, None)
        self.assertEqual(self.read(out).camera_lists[0].group_indices[0], (None, 1))
        with self.assertRaises(IndexError):
            fe10_battle.set_camera_dispatch_group(self.data, 0, 16, 0, 0)
        with self.assertRaises(IndexError):
            fe10_battle.set_camera_dispatch_group(self.data, 0, 0, 0, 2)

    def test_unit_models_and_textures(self):
        out, index = fe10_battle.clone_unit_model(self.data, 0, "modelC", "UNIT_C")
        doc = self.read(out)
        self.assertEqual(doc.unit_texture_sets[index].model_name, "modelC")
        self.assertEqual(len(doc.unit_texture_sets[index].mappings), 2)
        with self.assertRaisesRegex(ValueError, "already exists"):
            fe10_battle.clone_unit_model(out, 0, "modelC", "x")
        with self.assertRaisesRegex(ValueError, "still used"):
            fe10_battle.remove_unit_model(self.data, 0)
        self.assertEqual(len(self.read(fe10_battle.remove_unit_model(out, index)).table("FE10BTex").records), 3)

        out = fe10_battle.set_unit_texture(self.data, 1, "PID_BETA", "zu/modelB/beta.tpl")
        sets = self.read(out).unit_texture_sets
        self.assertEqual([m.condition for m in sets[1].mappings], ["ARMY_A", "PID_BETA"])
        self.assertEqual(len(sets[0].mappings), 2)
        out = fe10_battle.set_unit_texture(out, 1, "ARMY_A", "zu/modelB/b2.tpl")
        self.assertEqual(self.read(out).unit_texture_sets[1].mappings[0].texture_name, "zu/modelB/b2.tpl")
        with self.assertRaisesRegex(ValueError, "already has"):
            fe10_battle.add_unit_texture(out, 1, "PID_BETA", "x")
        out = fe10_battle.remove_unit_texture(out, 0, "PID_ALPHA")
        sets = self.read(out).unit_texture_sets
        self.assertEqual([m.condition for m in sets[0].mappings], ["ARMY_A"])
        self.assertEqual(sets[1].mappings[0].texture_name, "zu/modelB/b2.tpl")
        with self.assertRaises(ValueError):
            fe10_battle.remove_unit_texture(out, 0, "PID_ALPHA")

    def test_selectors(self):
        doc = self.read(self.data)
        self.assertEqual(fe10_battle.select_battle_row(doc, None, "PID_ALPHA", "JID_SWORD"), 0)
        self.assertEqual(fe10_battle.select_battle_row(doc, None, "PID_OTHER", "JID_LANCE"), 1)
        self.assertEqual(fe10_battle.select_battle_row(doc, None, "PID_ALPHA", "JID_LANCE"), 0)
        self.assertIsNone(fe10_battle.select_battle_row(doc, "AID_X", None, None))

        out, index = fe10_battle.clone_battle_selector(self.data, 1, "UNIT_A", aid="AID_NEW")
        self.assertEqual(fe10_battle.select_battle_row(self.read(out), "AID_NEW", None, None), index)
        self.assertNotIn(8, dict(self.read(out).table("FE10BAnimData").records[index].strings))
        with self.assertRaises(ValueError):
            fe10_battle.clone_battle_selector(self.data, 0, "UNIT_A")
        out = fe10_battle.update_battle_selector(out, index, pid="PID_GAMMA")
        self.assertEqual(dict(self.read(out).table("FE10BAnimData").records[index].strings),
                         {4: "PID_GAMMA", 12: "UNIT_A"})
        out = fe10_battle.set_battle_selector_target(out, index, "UNIT_B", "UNIT_A")
        self.assertEqual(dict(self.read(out).table("FE10BAnimData").records[index].strings)[16], "UNIT_A")
        with self.assertRaisesRegex(ValueError, "No FE10BUnit"):
            fe10_battle.set_battle_selector_target(out, index, "NOPE")
        out = fe10_battle.remove_battle_selector(out, index)
        self.assertEqual(len(self.read(out).table("FE10BAnimData").records), 2)


class SceneryAndWeaponTests(unittest.TestCase):
    def setUp(self):
        self.data = fe10_battle_file()

    def test_sceneries_read_and_edit(self):
        rows = fe10_battle_scenery.read_sceneries(self.data)
        self.assertEqual(rows[0].label(), "bg00 #0")
        self.assertEqual(rows[0].position, (10, -20, 30))
        self.assertEqual((rows[0].rotation, rows[0].scale_value()), (90, 3.0))
        self.assertEqual(rows[2].scale_value(), fe10_battle_scenery.DEFAULT_SCALE)
        self.assertTrue(rows[1].indoors)
        self.assertEqual(rows[1].flag_names(), ["Indoors (no weather or sky)", "Fighters run in"])
        out = fe10_battle_scenery.set_scenery(self.data, 2, flags=8, ground=3, position=(1, 2, 3),
                                              rotation=-45, scale=512)
        self.assertEqual(len(out), len(self.data))
        row = fe10_battle_scenery.read_sceneries(out)[2]
        self.assertEqual((row.flags, row.ground, row.position, row.rotation, row.scale_value()),
                         (8, 3, (1, 2, 3), -45, 2.0))
        for bad in ({"flags": 256}, {"position": (1, 2)}, {"rotation": 40000}, {"colour": 1}):
            with self.assertRaises(ValueError):
                fe10_battle_scenery.set_scenery(self.data, 0, **bad)

    def test_foot_effects_and_map_uses(self):
        self.assertEqual(fe10_battle_scenery.foot_effects(self.data),
                         {0: "None (なし)", 1: "Dust (砂煙)", 2: "custom"})
        self.assertEqual(fe10_battle_scenery.map_uses(self.data), {0: [("MAP_A", 0)], 1: [("MAP_A", 2)]})

    def test_weapons_read_and_edit(self):
        weapons = fe10_battle_weapons.read_weapons(self.data)
        self.assertEqual(weapons[0].label(), "IRONSWORD #0")
        self.assertEqual((weapons[1].type, weapons[1].second), (3, 2))
        self.assertIsNone(weapons[1].labels["model"])
        self.assertEqual(fe10_battle_weapons.weapon_types(self.data)[1], "t01 (型1)")
        out = fe10_battle_weapons.set_weapon(self.data, 1, labels={"model": "handaxe", "name": ""}, type=4)
        edited = fe10_battle_weapons.read_weapons(out)[1]
        self.assertEqual((edited.labels["model"], edited.labels["name"], edited.type), ("handaxe", None, 4))
        self.assertEqual(edited.label(), "HANDAXE #1")
        with self.assertRaises(ValueError):
            fe10_battle_weapons.set_weapon(self.data, 0, type=300)

    def test_units_read_and_edit(self):
        units = fe10_battle_units.read_units(self.data)
        self.assertEqual(units[0].label(), "modelA #0")
        self.assertEqual((units[0].flags, units[0].sound), (0b10, 1))
        self.assertEqual((units[0].value(0), units[0].value(1)), (0.5, -2.0))
        self.assertEqual(fe10_battle_units.param_names(self.data), ["Blend ratio (補間比率)", "Attack range (間合い)"])
        self.assertEqual(fe10_battle_units.flag_names(self.data), ["Large (大型)", "Flying (飛行系)", "新しい"])
        self.assertEqual(fe10_battle_units.sound_sets(self.data), {0: "None (なし)", 1: "Armour (鎧系)"})
        self.assertEqual(fe10_battle_units.to_raw("1.5"), 384)
        for bad in ("x", 200):
            with self.assertRaises(ValueError):
                fe10_battle_units.to_raw(bad)
        out = fe10_battle_units.set_unit(self.data, 1, flags=0b101, params={19: -1}, sound=0)
        self.assertEqual(len(out), len(self.data))
        unit = fe10_battle_units.read_units(out)[1]
        self.assertEqual((unit.flags, unit.params[19], unit.sound), (0b101, -1, 0))
        self.assertEqual(fe10_battle.read_fe10_battle(out).unit_texture_sets[1].mappings,
                         fe10_battle.read_fe10_battle(self.data).unit_texture_sets[1].mappings)
        with self.assertRaises(IndexError):
            fe10_battle_units.set_unit(self.data, 0, params={20: 0})
        with self.assertRaises(ValueError):
            fe10_battle_units.set_unit(self.data, 0, sound=2)
        with self.assertRaises(ValueError):
            fe10_battle_units.set_unit(self.data, 0, flags=-1)


if __name__ == "__main__":
    unittest.main()
