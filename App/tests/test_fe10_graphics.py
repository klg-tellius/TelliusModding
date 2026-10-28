import tempfile
import unittest
import struct
from pathlib import Path
from types import SimpleNamespace

from PIL import Image

from fe_modding.formats import effects, fe8data, fe10_anim, fe10_battle, fe10_effect_registry, fe10_faces, lz10, pak
from fe_modding.formats.packed_texture import read_packed_tpl, replace_packed_tpl
from fe_modding.formats.fe10_faces import FaceRecord, compose_face
from fe_modding.games import Game
from fe_modding.gui.icon_viewer import SHEETS, icon_users
from fe_modding.gui import model_viewer


class Fe10PortraitTests(unittest.TestCase):
    @staticmethod
    def _table(records: list[fe10_faces.FaceRecord]) -> bytes:
        body = bytearray(struct.pack(">II", len(records), 8))
        body += bytes(len(records) * fe10_faces.RECORD_SIZE)
        pointers = [4]
        labels = {}
        for index, record in enumerate(records):
            offset = 8 + index * fe10_faces.RECORD_SIZE
            for field, value in enumerate((record.fid, record.large_fid, record.name_id, record.filename)):
                if value not in labels:
                    labels[value] = len(body)
                    body += value.encode("cp932") + b"\0"
                struct.pack_into(">I", body, offset + field * 4, labels[value])
                pointers.append(offset + field * 4)
            struct.pack_into(">16h", body, offset + 16, *record.eye_a, *record.eye_b, *record.mouth,
                             *record.cut_in_origin, *record.extra)
        body += bytes(-len(body) % 4)
        tail = struct.pack(f">{len(pointers)}I", *pointers)
        return struct.pack(">4I", 0x20 + len(body) + len(tail), len(body), len(pointers), 0) + bytes(16) + body + tail

    @staticmethod
    def _record(name: str, value: int = 0) -> fe10_faces.FaceRecord:
        return fe10_faces.FaceRecord(f"FID_{name}", f"FID_L_{name}", "MPID_SHARED", f"{name}.cms",
                                     (value, 2), (3, 4), (5, 6), (7, 8), (9, 10, 11, 12, 13, 14, 15, 16))

    def test_compose_uses_body_parts_and_cut_in(self):
        transparent = Image.new("RGBA", (8, 8), (0, 0, 0, 0))
        cut_in = Image.new("RGBA", (4, 4), (1, 2, 3, 255))
        body = Image.new("RGBA", (8, 8), (20, 30, 40, 255))
        body.putpixel((1, 1), (0, 0, 0, 0))
        body.putpixel((6, 1), (0, 0, 0, 0))
        body.putpixel((3, 4), (0, 0, 0, 0))
        mouths = [Image.new("RGBA", (2, 2), (200, 0, 0, 255)) for _ in range(6)]
        eyes_a = [Image.new("RGBA", (1, 1), (0, 200, 0, 255)) for _ in range(3)]
        eyes_b = [Image.new("RGBA", (1, 1), (0, 0, 200, 255)) for _ in range(3)]
        images = [cut_in, body, *mouths, *eyes_a, *eyes_b, transparent]
        record = FaceRecord("FID_TEST", "FID_L_TEST", "MPID_TEST", "TEST.cms",
                            (1, 1), (6, 1), (3, 4), (2, 2), (0,) * 8)

        large = compose_face(record, images, large=True)
        self.assertEqual(large.getpixel((1, 1)), (0, 200, 0, 255))
        self.assertEqual(large.getpixel((6, 1)), (0, 0, 200, 255))
        self.assertEqual(large.getpixel((3, 4)), (200, 0, 0, 255))
        self.assertEqual(compose_face(record, images).size, (4, 4))

    def test_face_table_patch_add_and_remove_keep_relocations_valid(self):
        original = self._table([self._record("A"), self._record("B", 1)])
        replacement = fe10_faces.FaceRecord("FID_A", "FID_L_A", "MPID_NEW", "A.cms",
                                             (20, 21), (22, 23), (24, 25), (26, 27), tuple(range(8)))
        patched = fe10_faces.patch_face_record(original, 0, replacement)
        self.assertEqual(fe10_faces.read_face_data(patched)[0], replacement)

        grown, index = fe10_faces.add_face_record(patched, 1, "NEW", "MPID_NEW")
        self.assertEqual(index, 2)
        self.assertEqual(fe10_faces.read_face_data(grown)[2].filename, "NEW.cms")
        self.assertEqual(len(fe8data.pointer_list(grown)[1]), 1 + 4 * 3)
        restored = fe10_faces.remove_face_record(grown, index)
        self.assertEqual(fe10_faces.read_face_data(restored), fe10_faces.read_face_data(patched))

        without_first = fe10_faces.remove_face_record(original, 0)
        self.assertEqual(fe10_faces.read_face_data(without_first), [self._record("B", 1)])
        self.assertEqual(fe8data.pointer_list(without_first)[1], [4, 8, 12, 16, 20])

    def test_new_face_slot_rejects_duplicate_and_unsafe_names(self):
        table = self._table([self._record("A")])
        with self.assertRaisesRegex(ValueError, "already exists"):
            fe10_faces.add_face_record(table, 0, "A", "MPID_A")
        with self.assertRaisesRegex(ValueError, "capital letters"):
            fe10_faces.add_face_record(table, 0, "bad-name", "MPID_A")


class Fe10IconTests(unittest.TestCase):
    def test_rd_sheets_are_item_and_skill_addressable(self):
        item, skill = SHEETS[Game.RADIANT_DAWN][:2]
        self.assertTrue(item.item_icons)
        self.assertTrue(skill.skill_icons)
        self.assertIsNotNone(item.wide)
        self.assertIsNotNone(skill.wide)

    def test_rd_record_values_label_icon_cells(self):
        record = lambda **values: SimpleNamespace(values=values)
        database = SimpleNamespace(
            items=[record(iid="IID_IRON_SWORD", icon=12), record(iid="IID_SLIM_SWORD", icon=12)],
            skills=[record(sid="SID_WRATH", icon=7), record(sid="SID_HIDDEN", icon=0)],
        )
        items, skills = icon_users(database, Game.RADIANT_DAWN)
        self.assertEqual(items, {12: ["IRON_SWORD", "SLIM_SWORD"]})
        self.assertEqual(skills, {7: ["WRATH"]})


class Fe10ModelLayoutTests(unittest.TestCase):
    def test_rd_battle_body_and_animations_are_joined(self):
        with tempfile.TemporaryDirectory() as tmp:
            extracted = Path(tmp) / "extracted"
            folder = extracted / "files" / "zu" / "hero"
            folder.mkdir(parents=True)
            body = pak.pack_pak([("body.gs", b"mesh"), ("skeleton.g", b"rig")])
            (folder / "pack.cmp").write_bytes(lz10.compress(body))
            (folder / "sw.pak").write_bytes(pak.pack_pak([("attack_sw.ga", b"animation")]))
            (folder / "hero.tpl").write_bytes(b"texture")
            project = SimpleNamespace(extracted_dir=extracted)

            sets = model_viewer._iter_model_sets(project)
            self.assertEqual(sets, [("zu/hero", folder / "pack.cmp")])
            files, animations = model_viewer._set_contents(folder / "pack.cmp")
            self.assertEqual(files["body.gs"], b"mesh")
            self.assertEqual(files["skeleton.g"], b"rig")
            self.assertEqual(files["hero.tpl"], b"texture")
            self.assertEqual(animations, [("attack_sw.ga", b"animation")])


class PackedTextureTests(unittest.TestCase):
    def test_replacement_preserves_other_members_order_and_reserved_words(self):
        archive = pak.pack_pak(
            [("body.gs", b"mesh"), ("texpack.tpl", b"old texture"), ("rig.g", b"rig")],
            [1, 0, 7],
        )
        raw = lz10.compress(archive)
        self.assertEqual(read_packed_tpl(raw), b"old texture")

        rebuilt = lz10.decompress(replace_packed_tpl(raw, b"new texture"))
        entries = pak.read_pak_entries(rebuilt)
        self.assertEqual([(entry.name, entry.reserved) for entry in entries],
                         [("body.gs", 1), ("texpack.tpl", 0), ("rig.g", 7)])
        self.assertEqual([pak.read_pak_file_content(rebuilt, entry) for entry in entries],
                         [b"mesh", b"new texture", b"rig"])

    def test_archive_must_have_exactly_one_texture(self):
        no_texture = lz10.compress(pak.pack_pak([("body.gs", b"mesh")]))
        two_textures = lz10.compress(pak.pack_pak([("a.tpl", b"a"), ("b.tpl", b"b")]))
        with self.assertRaisesRegex(ValueError, "found 0"):
            read_packed_tpl(no_texture)
        with self.assertRaisesRegex(ValueError, "found 2"):
            replace_packed_tpl(two_textures, b"replacement")


class Fe10EffectTests(unittest.TestCase):
    @staticmethod
    def _registry() -> bytes:
        strings = b"Fire effect\0EID_FIRE\0SND_FIRE\0"
        description, eid, sound = 0x28, 0x34, 0x3D
        data = (
            struct.pack(">I6I", 1, description, eid, 0x00800000, 0x05006464, 0xFFFFFFFF, sound)
            + struct.pack(">I2I", 1, 0x1F4, eid)
            + strings
        )
        data += bytes(-len(data) % 4)
        pointers = (4, 8, 24, 0x24)
        names = b"EffectData\0EIDTable\0"
        symbols = struct.pack(">4I", 0, 0, 0x1C, len(b"EffectData\0"))
        tail = struct.pack(">4I", *pointers) + symbols + names
        size = 0x20 + len(data) + len(tail)
        return struct.pack(">4I", size, len(data), len(pointers), 2) + bytes(16) + data + tail

    def test_rd_effect_registry_and_listing(self):
        raw = self._registry()
        registry = fe10_effect_registry.read_fe10_effect_registry(raw)
        record = registry.records[0]
        self.assertEqual((record.eid_name, record.description, record.sound_group),
                         ("EID_FIRE", "Fire effect", "SND_FIRE"))
        self.assertEqual(record.parameter_bytes, (5, 0, 100, 100))
        self.assertEqual(record.child_effect_indices, (None, None))
        self.assertEqual(record.parameters, 0x05006464)
        self.assertEqual(record.link, 0xFFFFFFFF)
        self.assertEqual(registry.eid_table, ((0x1F4, "EID_FIRE"),))
        self.assertEqual(registry.numeric_ids("EID_FIRE"), (500,))
        self.assertEqual(registry.child_eids(record), ())

        with tempfile.TemporaryDirectory() as tmp:
            files = Path(tmp)
            (files / "FE10Effect.cms").write_bytes(lz10.compress(raw))
            (files / "yme").mkdir()
            (files / "yme" / "EID_FIRE.cmp").write_bytes(b"pack")
            listed = effects.list_effects(files, Game.RADIANT_DAWN)
            self.assertEqual(len(listed), 1)
            self.assertTrue(listed[0].registered and listed[0].has_pack)
            self.assertEqual(listed[0].sound_group, "SND_FIRE")
            self.assertEqual(listed[0].parameter_bytes, (5, 0, 100, 100))
            self.assertEqual(listed[0].numeric_ids, (500,))

    def test_rd_effect_registry_rebuild_and_reference_remap(self):
        raw = self._registry()
        parsed = fe10_effect_registry.read_fe10_effect_registry(raw)
        self.assertEqual(fe10_effect_registry.build_fe10_effect_registry(parsed), raw)

        cloned = fe10_effect_registry.clone_effect_record(raw, 0, "EID_FIRE_CHILD", "child")
        registry = fe10_effect_registry.read_fe10_effect_registry(cloned)
        self.assertEqual([record.eid_name for record in registry.records],
                         ["EID_FIRE", "EID_FIRE_CHILD"])
        edited = fe10_effect_registry.update_effect_record(
            cloned, 0, parameter_bytes=(1, 2, 3, 4), child_effect_indices=(1, None),
            sound_group="SND_CHANGED",
        )
        registry = fe10_effect_registry.read_fe10_effect_registry(edited)
        self.assertEqual(registry.records[0].parameter_bytes, (1, 2, 3, 4))
        self.assertEqual(registry.child_eids(registry.records[0]), ("EID_FIRE_CHILD",))
        self.assertEqual(registry.records[0].sound_group, "SND_CHANGED")
        with self.assertRaisesRegex(ValueError, "still used"):
            fe10_effect_registry.remove_effect_record(edited, 1)

        unlinked = fe10_effect_registry.update_effect_record(
            edited, 0, child_effect_indices=(None, None))
        removed = fe10_effect_registry.remove_effect_record(unlinked, 0)
        registry = fe10_effect_registry.read_fe10_effect_registry(removed)
        self.assertEqual(tuple(record.eid_name for record in registry.records), ("EID_FIRE_CHILD",))
        self.assertEqual(registry.eid_table, ())

    def test_rd_effect_registry_aliases_and_cycles_are_validated(self):
        raw = self._registry()
        aliased = fe10_effect_registry.set_numeric_aliases(raw, "EID_FIRE", (700, 500))
        self.assertEqual(fe10_effect_registry.read_fe10_effect_registry(aliased).eid_table,
                         ((500, "EID_FIRE"), (700, "EID_FIRE")))
        cloned = fe10_effect_registry.clone_effect_record(raw, 0, "EID_OTHER")
        linked = fe10_effect_registry.update_effect_record(cloned, 0, child_effect_indices=(1, None))
        with self.assertRaisesRegex(ValueError, "cycle"):
            fe10_effect_registry.update_effect_record(linked, 1, child_effect_indices=(0, None))

    def test_rd_effect_service_adds_and_edits_compressed_registry(self):
        compressed = lz10.compress(self._registry())
        added = effects.add_registry_record(
            compressed, "EID_NEW", flags=0x12345678,
            game=Game.RADIANT_DAWN, template_name="EID_FIRE",
        )
        document = fe10_effect_registry.read_fe10_effect_registry(lz10.decompress(added))
        self.assertEqual(document.records[-1].eid_name, "EID_NEW")
        self.assertEqual(document.records[-1].flags, 0x12345678)
        edited = effects.update_rd_registry_record(
            added, "EID_NEW", description="New effect", flags=7,
            parameter_bytes=(1, 2, 3, 4), child_effects=("EID_FIRE", None),
            sound_group="SND_NEW", numeric_ids=(600,),
        )
        document = fe10_effect_registry.read_fe10_effect_registry(lz10.decompress(edited))
        record = document.records[-1]
        self.assertEqual((record.description, record.flags, record.parameter_bytes),
                         ("New effect", 7, (1, 2, 3, 4)))
        self.assertEqual(document.child_eids(record), ("EID_FIRE",))
        self.assertEqual(document.numeric_ids("EID_NEW"), (600,))
        removed = effects.remove_rd_registry_record(
            effects.update_rd_registry_record(
                edited, "EID_NEW", description="New effect", flags=7,
                parameter_bytes=(1, 2, 3, 4), child_effects=(None, None),
                sound_group="SND_NEW", numeric_ids=(600,)),
            "EID_FIRE")
        self.assertEqual(effects.registry_names(removed, Game.RADIANT_DAWN), {"EID_NEW"})


class Fe10BattleTests(unittest.TestCase):
    def test_structural_reader_uses_relocations_for_strings(self):
        order = (
            "FE10BAnimData", "FE10BFootEffect", "FE10BSFXList", "FE10BSFXData", "FE10BSetup",
            "FE10BWeapon", "FE10BWeaponType", "FE10BMapModel", "FE10BMapData", "FE10BSky",
            "FE10BSkill", "FE10BMotion", "FE10BFlags", "FE10BParam", "FE10BCamFile",
            "FE10BCamGroup", "FE10BCamFileIndex", "FE10BCamFileRate", "FE10BCamEffect",
            "FE10BCamList", "FE10BCamGroupIndex", "FE10BCamType", "FE10BUnit", "FE10BTex",
        )
        data = bytearray()
        offsets = {}
        weapon_row = None
        for name in order:
            offsets[name] = len(data)
            if name == "FE10BWeapon":
                data += struct.pack(">HH", 1, 0)
                weapon_row = len(data)
                data += bytes(fe10_battle.TABLE_SIZES[name])
            elif name == "FE10BMotion":
                data += struct.pack(">HH", 1, 0) + bytes(fe10_battle.TABLE_SIZES[name])
            elif name == "FE10BCamFile":
                data += struct.pack(">HH", 1, 0) + bytes(fe10_battle.TABLE_SIZES[name])
            elif name == "FE10BWeaponType":
                data += struct.pack(">HH", 16, 0) + bytes(16 * fe10_battle.TABLE_SIZES[name])
            elif name == "FE10BCamGroup":
                data += struct.pack(">HH", 1, 0) + bytes(11) + b"\x01" + bytes(8)
            elif name == "FE10BCamList":
                data += struct.pack(">HH", 1, 0) + bytes(fe10_battle.TABLE_SIZES[name])
            elif name in fe10_battle.TABLE_SIZES:
                data += struct.pack(">HH", 0, 0)
            else:
                data += {"FE10BCamFileIndex": b"\x00", "FE10BCamFileRate": b"\x64",
                         "FE10BCamGroupIndex": b"\x00" + b"\xFF" * 15}[name]
        description = len(data)
        data += b"Bronze sword\0"
        weapon = len(data)
        data += b"BRONZESWORD\0"
        struct.pack_into(">II", data, weapon_row, description, weapon)
        data += bytes(-len(data) % 4)

        pointers = (weapon_row, weapon_row + 4)
        names = bytearray()
        symbol_rows = bytearray()
        for name in sorted(order):
            symbol_rows += struct.pack(">II", offsets[name], len(names))
            names += name.encode("ascii") + b"\0"
        tail = struct.pack(">2I", *pointers) + symbol_rows + names
        size = 0x20 + len(data) + len(tail)
        raw = struct.pack(">4I", size, len(data), len(pointers), len(order)) + bytes(16) + data + tail

        battle = fe10_battle.read_fe10_battle(raw)
        self.assertEqual(fe10_battle.build_fe10_battle(battle), raw)
        record = battle.table("FE10BWeapon").records[0]
        self.assertEqual(record.strings[:2], ((0, "Bronze sword"), (4, "BRONZESWORD")))
        self.assertEqual(dict(battle.arrays)["FE10BCamFileIndex"], b"\x00")
        self.assertEqual(battle.camera_groups[0].choices,
                         (fe10_battle.CameraChoice(file_index=0, selection_weight=100),))
        self.assertEqual(battle.camera_lists[0].group_indices[0], (0,))
        self.assertEqual(battle.camera_lists[0].group_indices[1], (None,))
        self.assertEqual(battle.camera_context_names,
                         tuple(f"type_{index}" for index in range(16)))
        weighted = fe10_battle.set_camera_choice_weight(raw, 0, 0, 37)
        self.assertEqual(fe10_battle.read_fe10_battle(
            weighted).camera_groups[0].choices[0].selection_weight, 37)
        dispatched = fe10_battle.set_camera_dispatch_group(raw, 0, 1, 0, 0)
        self.assertEqual(fe10_battle.read_fe10_battle(
            dispatched).camera_lists[0].group_indices[1], (0,))
        cleared = fe10_battle.set_camera_dispatch_group(dispatched, 0, 1, 0, None)
        self.assertEqual(fe10_battle.read_fe10_battle(
            cleared).camera_lists[0].group_indices[1], (None,))
        rebuilt = fe10_battle.update_battle_record(
            raw, "FE10BWeapon", 0, strings={0: "Forged sword", 4: "FORGEDSWORD"})
        record = fe10_battle.read_fe10_battle(rebuilt).table("FE10BWeapon").records[0]
        self.assertEqual(dict(record.strings), {0: "Forged sword", 4: "FORGEDSWORD"})
        cloned, camera_index = fe10_battle.clone_camera_file(
            raw, 0, "new_camera", "New camera")
        camera_rows = fe10_battle.read_fe10_battle(cloned).table("FE10BCamFile").records
        self.assertEqual(dict(camera_rows[camera_index].strings),
                         {0: "New camera", 4: "new_camera"})
        removed = fe10_battle.remove_camera_file(cloned, camera_index)
        self.assertEqual(len(fe10_battle.read_fe10_battle(removed).table("FE10BCamFile").records), 1)
        with self.assertRaisesRegex(ValueError, "still used"):
            fe10_battle.remove_camera_file(raw, 0)


class Fe10AnimTests(unittest.TestCase):
    def test_structural_reader_links_headers_to_model_records(self):
        header_at, model_at, motion_at, weapon_at = 0, 24, 480, 496
        data = bytearray(508)
        struct.pack_into(">HH", data, header_at, 1, 0)
        struct.pack_into(">HH", data, motion_at, 1, 0)
        struct.pack_into(">HH", data, weapon_at, 1, 0)
        pointers = [4, 8, 16, 20, model_at, model_at + 4, model_at + 8,
                    motion_at + 4, motion_at + 8, weapon_at + 4, weapon_at + 8]

        def label(value: str) -> int:
            offset = len(data)
            data.extend(value.encode("shift_jis") + b"\0")
            return offset

        aid, description, header_model = label("AID_TEST"), label("test header"), label("hero_R")
        model, step, floor = label("hero"), label("SFX_STEP"), label("SFX_FLOOR")
        motion, motion_file = label("wait"), label("wait_no")
        weapon, weapon_model = label("sword"), label("sw")
        struct.pack_into(">5I", data, 4, aid, description, 0x1234, header_model, model_at)
        struct.pack_into(">3I", data, model_at, model, step, floor)
        struct.pack_into(">3I", data, motion_at + 4, motion, motion_file, 7)
        struct.pack_into(">2I", data, weapon_at + 4, weapon, weapon_model)
        data += bytes(-len(data) % 4)
        symbol_names = bytearray()
        symbol_table = bytearray()
        for name, offset in (("FE10AnimHeader", header_at), ("FE10AnimData", model_at),
                             ("FE10AnimMotion", motion_at), ("FE10AnimWeapon", weapon_at)):
            symbol_table += struct.pack(">II", offset, len(symbol_names))
            symbol_names += name.encode("ascii") + b"\0"
        tail = struct.pack(f">{len(pointers)}I", *pointers) + symbol_table + symbol_names
        raw = struct.pack(">4I", 0x20 + len(data) + len(tail), len(data), len(pointers), 4) + bytes(16) + data + tail

        document = fe10_anim.read_fe10_anim(raw)
        self.assertEqual([len(table.records) for table in document.tables], [1, 1, 1, 1])
        header = document.table("FE10AnimHeader").records[0]
        self.assertEqual(header.linked_model, 0)
        self.assertEqual(dict(header.strings), {0: "AID_TEST", 4: "test header", 12: "hero_R"})
        self.assertEqual(dict(document.table("FE10AnimData").records[0].strings)[0], "hero")
        self.assertEqual(document.headers[0], fe10_anim.AnimHeader(
            "AID_TEST", "test header", 0, 0x1234, "hero_R", 0))
        self.assertEqual(document.models[0].folder, "hero")
        self.assertEqual(document.models[0].parameters, (0,) * 8)
        self.assertEqual(len(document.models[0].variants), 9)
        self.assertEqual(len(document.models[0].variants[0]), 48)
        self.assertEqual(document.motions[0], fe10_anim.AnimMotion("wait", "wait_no", 7))
        self.assertEqual(document.weapons[0], fe10_anim.AnimWeapon("sword", "sw"))
        self.assertIsNone(document.animation_filename(0, 0, 0))
        changed = fe10_anim.set_animation_variant(raw, 0, 0, 0, 6)
        self.assertEqual(fe10_anim.read_fe10_anim(changed).models[0].variants[0][0], 6)
        differences = [index for index, (before, after) in enumerate(zip(raw, changed))
                       if before != after]
        self.assertEqual(differences, [0x20 + model_at + fe10_anim.MODEL_METADATA_SIZE])
        self.assertGreater(len(document.string_pool), 0)

    def test_rebuild_clone_edit_and_remove(self):
        raw = self._anim_registry()
        document = fe10_anim.read_fe10_anim(raw)
        self.assertEqual(fe10_anim.build_fe10_anim(document), raw)
        cloned, model_index = fe10_anim.clone_anim_model(raw, 0, "hero_clone")
        cloned, header_index = fe10_anim.clone_anim_header(
            cloned, 0, "AID_CLONE", model_index)
        edited = fe10_anim.update_anim_header(
            cloned, header_index, description="clone header", flags=1,
            texture_name="hero_clone_R")
        document = fe10_anim.read_fe10_anim(edited)
        self.assertEqual(document.headers[header_index].aid_name, "AID_CLONE")
        self.assertEqual(document.headers[header_index].model_index, model_index)
        self.assertEqual(document.models[model_index].folder, "hero_clone")
        with self.assertRaisesRegex(ValueError, "still used"):
            fe10_anim.remove_anim_model(edited, model_index)
        edited = fe10_anim.remove_anim_header(edited, header_index)
        edited = fe10_anim.remove_anim_model(edited, model_index)
        document = fe10_anim.read_fe10_anim(edited)
        self.assertEqual((len(document.headers), len(document.models)), (1, 1))

    @staticmethod
    def _anim_registry() -> bytes:
        header_at, model_at, motion_at, weapon_at = 0, 24, 480, 496
        data = bytearray(508)
        struct.pack_into(">HH", data, header_at, 1, 0)
        struct.pack_into(">HH", data, motion_at, 1, 0)
        struct.pack_into(">HH", data, weapon_at, 1, 0)
        pointers = [4, 8, 16, 20, model_at, model_at + 4, model_at + 8,
                    motion_at + 4, motion_at + 8, weapon_at + 4, weapon_at + 8]

        def label(value: str) -> int:
            offset = len(data)
            data.extend(value.encode("shift_jis") + b"\0")
            return offset

        aid, description, header_model = label("AID_TEST"), label("test header"), label("hero_R")
        model, step, floor = label("hero"), label("SFX_STEP"), label("SFX_FLOOR")
        motion, motion_file = label("wait"), label("wait_no")
        weapon, weapon_model = label("sword"), label("sw")
        struct.pack_into(">5I", data, 4, aid, description, 0x1234, header_model, model_at)
        struct.pack_into(">3I", data, model_at, model, step, floor)
        struct.pack_into(">3I", data, motion_at + 4, motion, motion_file, 7)
        struct.pack_into(">2I", data, weapon_at + 4, weapon, weapon_model)
        data += bytes(-len(data) % 4)
        symbol_names = bytearray()
        symbol_table = bytearray()
        for name, offset in (("FE10AnimHeader", header_at), ("FE10AnimData", model_at),
                             ("FE10AnimMotion", motion_at), ("FE10AnimWeapon", weapon_at)):
            symbol_table += struct.pack(">II", offset, len(symbol_names))
            symbol_names += name.encode("ascii") + b"\0"
        tail = struct.pack(f">{len(pointers)}I", *pointers) + symbol_table + symbol_names
        return (struct.pack(">4I", 0x20 + len(data) + len(tail), len(data), len(pointers), 4)
                + bytes(16) + data + tail)


if __name__ == "__main__":
    unittest.main()
