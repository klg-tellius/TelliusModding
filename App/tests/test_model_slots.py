import struct
import sys
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from fe_modding import model_slots
from fe_modding.exceptions import ProjectError
from fe_modding.formats import anim_registry, fe8data, lz10, pak, zdbx
from fe_modding.games import Game
from fe_modding.project import ModProject
from test_formats import _build_synthetic_fe8data

JOB_LIST = "#\r\n{\r\n\t\tclass JobList\r\n\t\tJID_FIGHTER\t\tfig1\t\t#戦士\r\n\t\tJID_ARCHER\t\tPID_LOFA=arc2\t\t#x\r\n}\r\n\\\r\n"
MODEL = "{\r\n\tclass\tModel\r\n\tname\tfig1\r\n\tfolder\tzu/fig1\r\n\tmodel\tfig1\r\n\tax_攻撃1\tfig1_at1_ax\r\n}\r\n"
PARAM = "{\r\n\tclass\tParam\r\n\tname\tfig1\r\n\ttexnum\t2\r\n\t自軍\tfig1\r\n\tPID_BOLE\tbole\r\n\t移動速度\t0.8\r\n}\r\n"


def _record(aid, folder, weapon=0, textures=(1, 2, 3, 4), mask=0b11):
    return anim_registry.AnimRecord(aid_name=aid, class_folder=folder, weapon_type=weapon, blend_weight=9,
                                    body_type=5, texture_ids=textures, animation_mask=mask)


def _fe8data_with_header() -> bytes:
    data = bytearray(_build_synthetic_fe8data())
    struct.pack_into(">II", data, 0, len(data), len(data) - fe8data.HEADER_SIZE)
    return bytes(data)


class AnimRegistryWriteTests(unittest.TestCase):
    def test_build_round_trips_and_pools_sorted_strings(self):
        records = [_record("AID_B_N", "b/"), _record("AID_A_AX", "a/", weapon=2, textures=(4, 4, 4, 4), mask=0x1bcf)]
        data = anim_registry.build_anim_registry(records)

        read = anim_registry.read_anim_registry(data)
        self.assertEqual([replace(r, address=0) for r in read], records)
        self.assertEqual(read[1].base_aid, "AID_A")
        self.assertIn("atk1", read[1].actions)
        self.assertNotIn("crit", read[1].actions)
        size, data_size, pointers, symbols = struct.unpack(">4I", data[:16])
        self.assertEqual((size, pointers, symbols), (len(data), 4, 1))
        pool = data[0x20 + 4 + 2 * anim_registry.RECORD_SIZE : 0x20 + data_size].split(b"\x00")
        self.assertEqual([s for s in pool if s], sorted([b"AID_B_N", b"b/", b"AID_A_AX", b"a/"]))
        self.assertTrue(data.endswith(b"AnimData\x00"))


class Fe8DataAddLabelTests(unittest.TestCase):
    def test_add_label_appends_once_and_character_can_point_at_it(self):
        data = _fe8data_with_header()
        added = fe8data.add_label(data, "AID_NEWMODEL")
        self.assertEqual(len(added) % 4, 0)
        self.assertEqual(struct.unpack(">I", added[:4])[0], len(added))
        self.assertEqual(fe8data.add_label(added, "AID_NEWMODEL"), added)
        # a label that only appears as the tail of another one still gets its own copy
        self.assertNotEqual(fe8data.add_label(data, "TESTMODEL"), data)

        patched = fe8data.patch_character_field(added, 0, "aid_promoted", "AID_NEWMODEL")
        char = fe8data.read_fe8data(patched).characters[0]
        self.assertEqual((char.aid_unpromoted, char.aid_promoted), ("AID_TESTMODEL", "AID_NEWMODEL"))


class Fe8DataPointerListTests(unittest.TestCase):
    def test_null_pointer_leaves_the_pointer_list_and_comes_back(self):
        data = fe8data.add_label(_fe8data_with_header(), "AID_NEWMODEL")

        def listed(d):
            _size, data_size, count = struct.unpack(">III", d[:12])
            return set(struct.unpack_from(f">{count}I", d, fe8data.HEADER_SIZE + data_size))

        field = fe8data.CHARACTER_TABLE_OFFSET + 0x28 - fe8data.HEADER_SIZE  # character 0's aid_unpromoted
        with_aid = fe8data.patch_character_field(data, 0, "aid_unpromoted", "AID_NEWMODEL")
        self.assertIn(field, listed(with_aid))
        cleared = fe8data.patch_character_field(with_aid, 0, "aid_unpromoted", None)
        self.assertNotIn(field, listed(cleared))
        self.assertEqual(struct.unpack(">I", cleared[:4])[0], len(cleared))
        self.assertIsNone(fe8data.read_fe8data(cleared).characters[0].aid_unpromoted)
        again = fe8data.patch_character_field(cleared, 0, "aid_unpromoted", "AID_NEWMODEL")
        self.assertEqual(again, with_aid)


class JobListTests(unittest.TestCase):
    def test_lookup_order_matches_the_engine(self):
        models = zdbx.job_list_models(JOB_LIST + "\t\tAID_ARCHER_LO\t\tarc3\r\n")
        self.assertEqual(models["JID_ARCHER+PID_LOFA"], "arc2")
        self.assertEqual(zdbx.battle_model_for(models, "JID_ARCHER", "PID_LOFA"), "arc2")
        self.assertEqual(zdbx.battle_model_for(models, "JID_ARCHER", "PID_LOFA", "AID_ARCHER_LO"), "arc3")
        self.assertEqual(zdbx.battle_model_for(models, "JID_FIGHTER", "PID_BOLE"), "fig1")

    def test_set_job_model_adds_then_replaces(self):
        text = zdbx.set_job_model(JOB_LIST, "bol2", jid="JID_FIGHTER", pid="PID_BOLE", comment="Boyd")
        self.assertIn("\t\tJID_FIGHTER\t\tPID_BOLE=bol2\t\t#Boyd\r\n}", text)
        text = zdbx.set_job_model(text, "bol3", jid="JID_FIGHTER", pid="PID_BOLE")
        self.assertEqual(text.count("PID_BOLE"), 1)
        models = zdbx.job_list_models(text)
        self.assertEqual((models["JID_FIGHTER"], models["JID_FIGHTER+PID_BOLE"]), ("fig1", "bol3"))
        with self.assertRaises(ValueError):
            zdbx.set_job_model(text, "toolong", jid="JID_FIGHTER")

    def test_param_textures_keep_the_count(self):
        text = zdbx.set_param_texture(PARAM, "PID_BOLE", "bole2")
        text = zdbx.set_param_texture(text, "AID_FIGHTER_X", "x")
        self.assertEqual(zdbx.param_textures(text), {"自軍": "fig1", "PID_BOLE": "bole2", "AID_FIGHTER_X": "x"})
        self.assertIn("\ttexnum\t3\r\n", text)
        self.assertIn("\t移動速度\t0.8", text)


class ModelSlotProjectTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.project = ModProject.create(Path(tmp.name), "Slots", Game.PATH_OF_RADIANCE)
        files = self.project.extracted_dir / "files"
        (files / "zu" / "fig1").mkdir(parents=True)
        (files / "zu" / "fig1" / "fig1_ax.pak").write_bytes(pak.pack_pak([("fig1.gs", b"gs")]))
        (files / "zu" / "fig1" / "bole.tpl").write_bytes(b"tpl")
        tables = [(zdbx.JOB_LIST, JOB_LIST), ("zu/fig1.dbx", MODEL), ("zu/fig1_prm.dbx", PARAM)]
        (files / "zdbx.cmp").write_bytes(zdbx.build_zdbx_archive([(n, zdbx.encode_dbx(t)) for n, t in tables]))
        (files / "ymu" / "fighter").mkdir(parents=True)
        (files / "ymu" / "fighter" / "tex_4.tpl").write_bytes(b"tex")
        records = [_record("AID_FIGHTER_BO_N", "fighter/"), _record("AID_FIGHTER_BO_AX", "fighter/", weapon=2)]
        (files / "FE8Anim.bin").write_bytes(anim_registry.build_anim_registry(records))
        (files / "FE8Data.bin").write_bytes(_fe8data_with_header())
        self.files = files

    def test_clone_and_assign_battle_model(self):
        written = model_slots.clone_battle_model(self.project, "fig1", "bol2")
        self.assertEqual(sorted(p.name for p in written), ["bol2_ax.pak", "bole.tpl"])
        self.assertEqual(model_slots.battle_model_codes(self.project), ["bol2", "fig1"])
        model_slots.assign_battle_model(self.project, "bol2", jid="JID_FIGHTER", pid="PID_BOLE")
        model_slots.set_battle_texture(self.project, "bol2", "PID_BOLE", "bole_purple")

        tables = {e.name: e.text for e in zdbx.read_zdbx_path(self.files / "zdbx.cmp")}
        self.assertIn("\tfolder\tzu/bol2\r\n", tables["zu/bol2.dbx"])
        self.assertIn("\tmodel\tfig1\r\n", tables["zu/bol2.dbx"])
        self.assertEqual(model_slots.battle_textures(self.project, "bol2")["PID_BOLE"], "bole_purple")
        self.assertEqual(model_slots.battle_textures(self.project, "fig1")["PID_BOLE"], "bole")
        models = zdbx.job_list_models(tables[zdbx.JOB_LIST])
        self.assertEqual(zdbx.battle_model_for(models, "JID_FIGHTER", "PID_BOLE"), "bol2")
        self.assertTrue((self.project.originals_dir / "files" / "zdbx.cmp").is_file())
        with self.assertRaises(ProjectError):
            model_slots.clone_battle_model(self.project, "fig1", "bol2")

    def test_clone_and_assign_map_model(self):
        written = model_slots.clone_map_model(self.project, "AID_FIGHTER_BO", "AID_FIGHTER_NEW", "fighter_new",
                                              texture_ids=(4, 4, 4, 4))
        self.assertEqual([p.name for p in written], ["tex_4.tpl"])
        added = [r for r in model_slots.map_model_records(self.project) if r.base_aid == "AID_FIGHTER_NEW"]
        self.assertEqual(sorted(r.aid_name for r in added), ["AID_FIGHTER_NEW_AX", "AID_FIGHTER_NEW_N"])
        self.assertEqual({r.class_folder for r in added}, {"fighter_new/"})
        self.assertEqual({r.texture_ids for r in added}, {(4, 4, 4, 4)})

        model_slots.assign_map_model(self.project, "PID_TEST", "AID_FIGHTER_NEW")
        char = fe8data.read_fe8data((self.files / "FE8Data.bin").read_bytes()).characters[0]
        self.assertEqual(char.aid_unpromoted, "AID_FIGHTER_NEW")
        with self.assertRaises(ProjectError):
            model_slots.assign_map_model(self.project, "PID_TEST", "AID_MISSING")

    def test_remove_battle_model_restores_redirected_vanilla_lines(self):
        model_slots.clone_battle_model(self.project, "fig1", "bol2")
        model_slots.assign_battle_model(self.project, "bol2", jid="JID_FIGHTER")  # replaces a vanilla line
        model_slots.assign_battle_model(self.project, "bol2", jid="JID_FIGHTER", pid="PID_BOLE")
        model_slots.remove_battle_texture(self.project, "bol2", "PID_BOLE")
        self.assertNotIn("PID_BOLE", model_slots.battle_textures(self.project, "bol2"))
        with self.assertRaises(ProjectError):
            model_slots.remove_battle_model(self.project, "fig1")

        self.assertEqual(model_slots.remove_battle_model(self.project, "bol2"), 2)
        self.assertFalse((self.files / "zu" / "bol2").exists())
        names = {e.name for e in zdbx.read_zdbx_path(self.files / "zdbx.cmp")}
        self.assertNotIn("zu/bol2.dbx", names)
        self.assertEqual(
            [(k, c) for k, c, _ in model_slots.job_list(self.project)],
            [("JID_FIGHTER", "fig1"), ("JID_ARCHER+PID_LOFA", "arc2")],
        )
        model_slots.remove_job_line(self.project, "JID_ARCHER+PID_LOFA")
        self.assertEqual(len(model_slots.job_list(self.project)), 1)

    def test_remove_map_model_restores_characters_and_folder(self):
        model_slots.clone_map_model(self.project, "AID_FIGHTER_BO", "AID_FIGHTER_NEW", "fighter_new")
        model_slots.assign_map_model(self.project, "PID_TEST", "AID_FIGHTER_NEW")
        model_slots.set_map_textures(self.project, "AID_FIGHTER_NEW", (7, 8, 9, 10))
        self.assertEqual(
            {r.texture_ids for r in model_slots.map_model_records(self.project) if r.base_aid == "AID_FIGHTER_NEW"},
            {(7, 8, 9, 10)},
        )
        with self.assertRaises(ProjectError):
            model_slots.remove_map_model(self.project, "AID_FIGHTER_BO")

        changes = model_slots.remove_map_model(self.project, "AID_FIGHTER_NEW")
        self.assertEqual(len(changes), 3)
        self.assertFalse((self.files / "ymu" / "fighter_new").exists())
        self.assertTrue((self.files / "ymu" / "fighter").exists())
        self.assertEqual({r.base_aid for r in model_slots.map_model_records(self.project)}, {"AID_FIGHTER_BO"})
        vanilla = fe8data.read_fe8data(_fe8data_with_header()).characters[0].aid_unpromoted
        char = fe8data.read_fe8data((self.files / "FE8Data.bin").read_bytes()).characters[0]
        self.assertEqual(char.aid_unpromoted, vanilla)

    def test_build_syncs_edited_loose_files_into_system_archive(self):
        system = [("FE8Data.bin", (self.files / "FE8Data.bin").read_bytes()), ("mess/common.m", b"text")]
        (self.files / "system.cmp").write_bytes(lz10.compress(pak.pack_pak(system)))
        self.assertEqual(self.project.sync_system_archive(), [])
        model_slots.assign_map_model(self.project, "PID_TEST", None, promoted=False)

        self.assertEqual(self.project.sync_system_archive(), ["FE8Data.bin"])
        unpacked = lz10.decompress((self.files / "system.cmp").read_bytes())
        contents = {e.name: pak.read_pak_file_content(unpacked, e) for e in pak.read_pak_entries(unpacked)}
        self.assertEqual(contents["FE8Data.bin"], (self.files / "FE8Data.bin").read_bytes())
        self.assertEqual(contents["mess/common.m"], b"text")


if __name__ == "__main__":
    unittest.main()
