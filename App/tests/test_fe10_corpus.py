"""Corpus tests against an extracted Radiant Dawn disc (skipped unless the variables are set).

``FE10_EXTRACTED_FILES`` is the ``files/`` folder of an extracted RFEE01 disc and ``FE10_EXTRACTED``
its root (the folder holding ``sys/`` and ``files/``); either alone enables the tests that need
only it. They mirror ``FE9_EXTRACTED_FILES`` / ``FE9_EXTRACTED`` for Path of Radiance.
Each decoder added for Radiant Dawn adds its byte-identical round trip here.
"""

import io
import os
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fe_modding import games
from fe_modding.formats import (animation, dispo, fe8data, fe10_anim, fe10_battle, fe10_effect_registry, fe10_faces, gs_file, lz10, map_file,
                                message, pak, shop, skeleton, tpl)
from fe_modding.formats.packed_texture import read_packed_tpl
from fe_modding.game_profile import RADIANT_DAWN_PROFILE
from fe_modding.games import Game


def _files() -> Path | None:
    value = os.environ.get("FE10_EXTRACTED_FILES")
    if value:
        return Path(value)
    root = os.environ.get("FE10_EXTRACTED")
    return Path(root) / "files" if root else None


FILES = _files()
ROOT = Path(os.environ["FE10_EXTRACTED"]) if os.environ.get("FE10_EXTRACTED") else (FILES.parent if FILES else None)

#: The data containers: LZ10 files that share the FE8Data container header.
DATA_FILES = ("FE10Data.cms", "FE10Growth.cms", "FE10Anim.cms", "FE10Battle.cms", "FE10Effect.cms",
              "FE10Conversation.cms", "Cp/cp_data.cms")


@unittest.skipUnless(FILES, "set FE10_EXTRACTED_FILES to the files/ folder of an extracted Radiant Dawn disc")
class Fe10FilesTest(unittest.TestCase):
    def test_every_profile_file_is_on_the_disc(self):
        for name in RADIANT_DAWN_PROFILE.files:
            path = RADIANT_DAWN_PROFILE.path(FILES, name)
            with self.subTest(name=name):
                self.assertTrue(path.is_file(), path)

    def test_data_files_decompress_and_recompress_byte_identically(self):
        for rel in DATA_FILES:
            raw = (FILES / rel).read_bytes()
            inner = lz10.decompress(raw)
            with self.subTest(rel=rel):
                self.assertEqual(lz10.compress(inner), raw)

    def test_data_files_use_the_fe8data_container(self):
        for rel in DATA_FILES:
            inner = lz10.decompress((FILES / rel).read_bytes())
            with self.subTest(rel=rel):
                file_size = int.from_bytes(inner[0:4], "big")
                self.assertEqual(file_size, len(inner))
        symbols = fe8data.symbol_offsets(lz10.decompress((FILES / "FE10Data.cms").read_bytes()))
        self.assertIn("ChapterData", symbols)
        self.assertGreater(len(symbols), 100)

    def test_phase6_texture_corpus_uses_the_shared_tpl_codec(self):
        expected = {"Face": 634, "illust": 172, "window": 213, "gmap": 14, "etc": 21}
        for folder, count in expected.items():
            paths = sorted(p for p in (FILES / folder).rglob("*")
                           if p.is_file() and p.suffix.lower() in (".tpl", ".cms"))
            with self.subTest(folder=folder):
                self.assertEqual(len(paths), count)
            for path in paths:
                raw = path.read_bytes()
                inner = lz10.decompress(raw) if path.suffix.lower() == ".cms" else raw
                with self.subTest(path=path.relative_to(FILES)):
                    self.assertTrue(tpl.read_tpl_image_info(io.BytesIO(inner)))

    def test_phase6_portraits_have_matching_normal_and_wide_slots(self):
        normal = fe10_faces.FaceLibrary(FILES)
        wide = fe10_faces.FaceLibrary(FILES, wide=True)
        self.assertEqual(len(normal.records), 316)
        self.assertEqual(len(wide.records), 316)
        for record in normal.records:
            counterpart = FILES / "Face" / "wide" / record.filename
            self.assertTrue(counterpart.is_file(), counterpart)
            regular_info = tpl.read_tpl_image_info(io.BytesIO(lz10.decompress(
                (FILES / "Face" / record.filename).read_bytes())))
            wide_info = tpl.read_tpl_image_info(io.BytesIO(lz10.decompress(counterpart.read_bytes())))
            self.assertEqual(len(regular_info), len(wide_info), record.filename)

    def test_phase6_face_tables_support_safe_new_slots(self):
        rebuilt = []
        for relative in (Path("Face/facedata.bin"), Path("Face/wide/facedata.bin")):
            raw = (FILES / relative).read_bytes()
            before = fe10_faces.read_face_data(raw)
            grown, index = fe10_faces.add_face_record(raw, 1, "CODEX_TEST", before[1].name_id)
            after = fe10_faces.read_face_data(grown)
            with self.subTest(relative=relative):
                self.assertEqual((len(before), len(after), index), (316, 317, 316))
                self.assertEqual((after[-1].fid, after[-1].large_fid, after[-1].filename),
                                 ("FID_CODEX_TEST", "FID_L_CODEX_TEST", "CODEX_TEST.cms"))
                self.assertEqual(after[-1].extra, before[1].extra)
                self.assertEqual(len(fe8data.pointer_list(grown)[1]), 1 + 4 * len(after))
                self.assertEqual(fe10_faces.read_face_data(fe10_faces.remove_face_record(grown, index)), before)
            rebuilt.append(after[-1])
        self.assertNotEqual(rebuilt[0].eye_a, rebuilt[1].eye_a)

    def test_phase6_packed_sky_and_scenery_textures_use_the_shared_tpl_codec(self):
        expected = {"sky": (22, 22, 69), "zbg": (129, 127, 1281)}
        for folder, (archive_count, texture_count, image_count) in expected.items():
            paths = sorted((FILES / folder).rglob("*.cmp"))
            textures = []
            for path in paths:
                try:
                    textures.append(read_packed_tpl(path.read_bytes()))
                except ValueError as exc:
                    self.assertIn("found 0", str(exc), path)
            with self.subTest(folder=folder):
                self.assertEqual(len(paths), archive_count)
                self.assertEqual(len(textures), texture_count)
                self.assertEqual(sum(len(tpl.read_tpl_image_info(io.BytesIO(data))) for data in textures),
                                 image_count)

    def test_phase6_model_components_and_archives_round_trip_byte_identically(self):
        archives = sorted(
            p for folder in ("ymu", "zu", "yme", "xwp", "zbg")
            for p in (FILES / folder).rglob("*")
            if p.is_file() and p.suffix.lower() in (".cmp", ".pak")
        )
        self.assertEqual(len(archives), 2291)
        components = {".gs": 0, ".g": 0, ".ga": 0}

        def check(name: str, data: bytes) -> None:
            suffix = Path(name).suffix.lower()
            if suffix == ".gs":
                rebuilt = gs_file.write_gs(gs_file.read_gs(data))
            elif suffix == ".g":
                rebuilt = skeleton.write_skeleton_file(skeleton.read_skeleton_file(data))
            elif suffix == ".ga":
                rebuilt = animation.write_animation(animation.read_animation_bytes(data))
            else:
                return
            components[suffix] += 1
            self.assertEqual(rebuilt, data, name)

        for path in archives:
            raw = path.read_bytes()
            inner = raw if path.suffix.lower() == ".pak" else lz10.decompress(raw)
            entries = pak.read_pak_entries(inner)
            rebuilt = pak.pack_pak(
                [(entry.name, pak.read_pak_file_content(inner, entry)) for entry in entries],
                [entry.reserved for entry in entries],
            )
            self.assertEqual(rebuilt, inner, path.relative_to(FILES))
            for entry in entries:
                check(str(path.relative_to(FILES) / entry.name), pak.read_pak_file_content(inner, entry))

        for folder in ("ymu", "xcam"):
            for path in sorted((FILES / folder).rglob("*")):
                if path.is_file() and path.suffix.lower() in components:
                    check(str(path.relative_to(FILES)), path.read_bytes())
        self.assertEqual(components, {".gs": 5342, ".g": 5342, ".ga": 16415})

    def test_phase6_animation_registry_is_structurally_accounted_for(self):
        raw = lz10.decompress((FILES / "FE10Anim.cms").read_bytes())
        document = fe10_anim.read_fe10_anim(raw)
        self.assertEqual(fe10_anim.build_fe10_anim(document), raw)
        self.assertEqual([(table.name, len(table.records), table.record_size) for table in document.tables], [
            ("FE10AnimHeader", 390, 20), ("FE10AnimData", 245, 456),
            ("FE10AnimMotion", 48, 12), ("FE10AnimWeapon", 9, 8),
        ])
        headers = document.table("FE10AnimHeader").records
        self.assertEqual(len({record.linked_model for record in headers}), 244)
        self.assertEqual(sum(12 in dict(record.strings)
                             for record in document.table("FE10AnimData").records), 39)
        self.assertEqual([header.ordinal for header in document.headers], list(range(390)))
        self.assertEqual({header.flags for header in document.headers}, {0, 1})
        self.assertEqual([weapon.archive_suffix for weapon in document.weapons],
                         ["no", "sw", "sp", "ja", "ax", "ha", "bw", "rd", "bg"])
        self.assertEqual(len(document.motions), 48)
        self.assertEqual(sum(bool(value) for model in document.models
                             for row in model.variants for value in row), 6461)
        self.assertEqual(document.animation_filename(1, 0, 0), "wait_1.ga")
        model_pack = lz10.decompress(
            (FILES / "ymu" / document.models[1].folder / "pack.cmp").read_bytes())
        self.assertIn(document.animation_filename(1, 0, 0),
                      {entry.name for entry in pak.read_pak_entries(model_pack)})
        self.assertEqual(len(document.string_pool), 16488)

    def test_phase6_effect_registry_matches_the_yme_inventory(self):
        raw = lz10.decompress((FILES / "FE10Effect.cms").read_bytes())
        registry = fe10_effect_registry.read_fe10_effect_registry(raw)
        self.assertEqual(fe10_effect_registry.build_fe10_effect_registry(registry), raw)
        self.assertEqual(len(registry.records), 632)
        self.assertEqual(len(registry.eid_table), 25)
        self.assertEqual(tuple(effect_id for effect_id, _eid in registry.eid_table),
                         (500, 510, 520, 530, 531, 532, 540, 550, 551, 560, 570, 571,
                          580, 590, 600, 610, 620, 630, 640, 650, 710, 720, 721, 730, 740))
        self.assertEqual(len({record.eid_name for record in registry.records}), 632)
        self.assertEqual(registry.records[15].child_effect_indices, (16, None))
        self.assertEqual(registry.records[20].child_effect_indices, (None, 21))
        self.assertTrue(all(child is None or child < len(registry.records)
                            for record in registry.records for child in record.child_effect_indices))
        packs = {path.stem for path in (FILES / "yme").glob("*.cmp")}
        registered = {record.eid_name for record in registry.records}
        self.assertEqual(len(packs), 702)
        self.assertEqual(len(registered & packs), 626)

    def test_phase6_battle_tables_are_structurally_accounted_for(self):
        raw = lz10.decompress((FILES / "FE10Battle.cms").read_bytes())
        battle = fe10_battle.read_fe10_battle(raw)
        self.assertEqual(fe10_battle.build_fe10_battle(battle), raw)
        counts = {table.name: (len(table.records), table.record_size) for table in battle.tables}
        self.assertEqual(counts["FE10BWeapon"], (192, 36))
        self.assertEqual(counts["FE10BMapModel"], (146, 24))
        self.assertEqual(counts["FE10BCamFile"], (113, 12))
        self.assertEqual(counts["FE10BUnit"], (240, 340))
        self.assertEqual(counts["FE10BTex"], (1112, 8))
        self.assertEqual([(name, len(data)) for name, data in battle.arrays], [
            ("FE10BCamFileIndex", 100), ("FE10BCamFileRate", 100),
            ("FE10BCamGroupIndex", 18720),
        ])
        self.assertEqual((len(battle.camera_groups), len(battle.camera_lists)), (93, 39))
        choices = [choice for group in battle.camera_groups for choice in group.choices]
        self.assertEqual(len(choices), 100)
        self.assertEqual({weight: sum(choice.selection_weight == weight for choice in choices)
                          for weight in (0, 50, 100)}, {0: 4, 50: 8, 100: 88})
        self.assertTrue(all(len(camera_list.group_indices) == 16
                            and all(len(context) == 30 for context in camera_list.group_indices)
                            for camera_list in battle.camera_lists))
        self.assertEqual([(choice.file_index, choice.selection_weight)
                          for choice in battle.camera_groups[1].choices],
                         [(16, 100), (21, 0), (22, 0), (23, 0)])
        self.assertEqual(battle.camera_context_names,
                         ("no", "sw", "sp", "ax", "kn", "ja", "ha", "kt",
                          "ms", "mg", "bw", "bg", "cr", "br", "rd", "ar"))
        self.assertEqual((len(battle.map_models), len(battle.map_data)), (146, 119))
        self.assertEqual(battle.map_data[7].model_indices, (7, None, None, None, 9))
        self.assertEqual(battle.map_model(battle.map_data[7], 3).archive_name, "bg0104grd")
        self.assertEqual(battle.map_models[1].translation, (-20, 0, 0))
        self.assertEqual((battle.map_models[1].rotation_value, battle.map_models[1].scale_value), (10, 768))
        self.assertEqual(len(battle.texture_mappings), 1112)
        self.assertEqual(sum(len(texture_set.mappings) for texture_set in battle.unit_texture_sets), 1112)
        self.assertEqual(battle.unit_texture_sets[0].model_name, "swoL")
        self.assertEqual([(mapping.condition, mapping.texture_name)
                          for mapping in battle.unit_texture_sets[0].mappings[:2]],
                         [("自軍", "swoL"), ("敵軍", "swoL")])
        self.assertEqual(len(battle.string_pool), 34092)

    def test_phase6_variable_registry_rebuilds_reparse(self):
        anim_raw = lz10.decompress((FILES / "FE10Anim.cms").read_bytes())
        anim, model_index = fe10_anim.clone_anim_model(anim_raw, 0, "phase6_test")
        anim, header_index = fe10_anim.clone_anim_header(
            anim, 0, "AID_PHASE6_TEST", model_index)
        parsed_anim = fe10_anim.read_fe10_anim(anim)
        self.assertEqual(parsed_anim.headers[header_index].model_index, model_index)
        self.assertEqual(parsed_anim.models[model_index].folder, "phase6_test")

        effect_raw = lz10.decompress((FILES / "FE10Effect.cms").read_bytes())
        effect = fe10_effect_registry.clone_effect_record(
            effect_raw, 0, "EID_PHASE6_TEST")
        effect = fe10_effect_registry.update_effect_record(
            effect, 632, child_effect_indices=(0, None))
        parsed_effect = fe10_effect_registry.read_fe10_effect_registry(effect)
        self.assertEqual(parsed_effect.child_eids(parsed_effect.records[-1]),
                         (parsed_effect.records[0].eid_name,))

        battle_raw = lz10.decompress((FILES / "FE10Battle.cms").read_bytes())
        battle = fe10_battle.read_fe10_battle(battle_raw)
        source_description = dict(battle.table("FE10BUnit").records[0].strings)[0]
        selector_index = next(
            i for i, record in enumerate(battle.table("FE10BAnimData").records)
            if dict(record.strings).get(12) == source_description)
        selector = dict(battle.table("FE10BAnimData").records[selector_index].strings)
        rebuilt, unit_index = fe10_battle.clone_unit_model(
            battle_raw, 0, "phase6Unit", "Editor model phase6Unit")
        rebuilt, new_selector = fe10_battle.clone_battle_selector(
            rebuilt, selector_index, "Editor model phase6Unit",
            aid=selector.get(0), pid=selector.get(4), jid=selector.get(8))
        parsed_battle = fe10_battle.read_fe10_battle(rebuilt)
        self.assertEqual(parsed_battle.unit_texture_sets[unit_index].model_name, "phase6Unit")
        self.assertEqual(dict(parsed_battle.table("FE10BAnimData").records[new_selector].strings)[12],
                         "Editor model phase6Unit")

    def test_phase6_camera_registry_matches_xcam_clips(self):
        battle = fe10_battle.read_fe10_battle(lz10.decompress((FILES / "FE10Battle.cms").read_bytes()))
        registered = {dict(record.strings)[4] for record in battle.table("FE10BCamFile").records}
        paths = sorted((FILES / "xcam").glob("*.ga"))
        clips = {path.stem for path in paths}
        parsed = [animation.read_animation_bytes(path.read_bytes()) for path in paths]
        self.assertEqual((len(registered), len(clips), len(registered & clips)), (113, 196, 112))
        self.assertEqual(registered - clips, {"onmaptest"})
        self.assertEqual(len(clips - registered), 84)
        self.assertEqual(sum(len(clip.curves) for clip in parsed), 1566)
        self.assertEqual((min(clip.length_in_frames for clip in parsed),
                          max(clip.length_in_frames for clip in parsed)), (15, 2400))
        rig = skeleton.read_skeleton_file((FILES / "xcam" / "cam.g").read_bytes())
        self.assertEqual([bone.name for bone in rig.bones], ["locator1", "camera1"])

    def test_phase6_fixed_width_registry_patches_preserve_other_bytes(self):
        anim_raw = lz10.decompress((FILES / "FE10Anim.cms").read_bytes())
        anim_changed = fe10_anim.set_animation_variant(anim_raw, 1, 0, 0, 2)
        self.assertEqual(sum(before != after for before, after in zip(anim_raw, anim_changed)), 1)
        self.assertEqual(fe10_anim.read_fe10_anim(anim_changed).models[1].variants[0][0], 2)

        battle_raw = lz10.decompress((FILES / "FE10Battle.cms").read_bytes())
        map_changed = fe10_battle.set_map_model_variant(battle_raw, 7, 1, 8)
        self.assertEqual(sum(before != after for before, after in zip(battle_raw, map_changed)), 2)
        self.assertEqual(fe10_battle.read_fe10_battle(map_changed).map_data[7].model_indices[1], 8)

        weight_changed = fe10_battle.set_camera_choice_weight(battle_raw, 1, 0, 99)
        self.assertEqual(sum(before != after for before, after in zip(battle_raw, weight_changed)), 1)
        self.assertEqual(fe10_battle.read_fe10_battle(
            weight_changed).camera_groups[1].choices[0].selection_weight, 99)

        battle = fe10_battle.read_fe10_battle(battle_raw)
        old_group = battle.camera_lists[0].group_indices[0][0]
        replacement = None if old_group is not None else 0
        dispatch_changed = fe10_battle.set_camera_dispatch_group(
            battle_raw, 0, 0, 0, replacement)
        self.assertEqual(sum(before != after for before, after in zip(battle_raw, dispatch_changed)), 1)
        self.assertEqual(fe10_battle.read_fe10_battle(
            dispatch_changed).camera_lists[0].group_indices[0][0], replacement)

    def test_coverage_walker_places_every_byte_of_the_containers(self):
        from fe_modding.formats.coverage import UNCLASSIFIED, Report, Walker

        report = Report()
        walker = Walker(report)
        for rel in DATA_FILES:
            walker.child(rel, (FILES / rel).read_bytes())
        totals = report.formats["fe10 container"]
        cp_totals = report.formats.get("cp_data")
        self.assertEqual(totals.files + (cp_totals.files if cp_totals else 0), len(DATA_FILES))
        self.assertEqual(totals.failures, [])
        self.assertEqual(totals.counts[UNCLASSIFIED], 0)
        if cp_totals:
            self.assertEqual(cp_totals.failures, [])
            self.assertEqual(cp_totals.counts[UNCLASSIFIED], 0)

    def test_every_mess_file_parses(self):
        paths = sorted((FILES / "Mess").glob("*.m"))
        self.assertGreater(len(paths), 200)
        for path in paths:
            with self.subTest(path=path.name):
                self.assertTrue(message.read_messages_path(path) is not None)

    def test_chapters_use_part_and_chapter_ids(self):
        from types import SimpleNamespace

        from fe_modding import chapters

        project = SimpleNamespace(extracted_dir=FILES.parent, game=Game.RADIANT_DAWN)
        ids = chapters.list_chapter_ids(project)
        self.assertIn("0101", ids)
        self.assertIn("0407a", ids)
        self.assertEqual(ids, sorted(ids, key=RADIANT_DAWN_PROFILE.chapter_sort_key))
        paths = chapters.chapter_paths(project, "0101")
        for found in (paths.dialogue, paths.script, paths.deployment, paths.map):
            self.assertIsNotNone(found)

    def test_wii_fonts_and_maps_are_where_the_profile_says(self):
        self.assertTrue((FILES / "zmap" / "bmap0101" / "map.cmp").is_file())
        for diff in RADIANT_DAWN_PROFILE.deployment_difficulties:
            self.assertTrue(RADIANT_DAWN_PROFILE.deployment_path(FILES, "bmap0101", diff).is_file(), diff)
        for diff in RADIANT_DAWN_PROFILE.shop_difficulties:
            self.assertTrue(RADIANT_DAWN_PROFILE.shop_path(FILES, diff).is_file(), diff)

    def test_every_deployment_round_trips_byte_identically(self):
        paths = sorted((FILES / "zmap").glob("*/dispos_*.bin"))
        self.assertGreater(len(paths), 190)
        for path in paths:
            with self.subTest(path=path.relative_to(FILES)):
                raw = path.read_bytes()
                document = dispo.parse_dispo(raw)
                self.assertEqual(document.dialect, "fe10")
                self.assertEqual(dispo.build_dispo(document), raw)

    def test_every_map_uses_the_shared_codec(self):
        paths = sorted((FILES / "zmap").glob("*/map.cmp"))
        self.assertGreater(len(paths), 120)
        for path in paths:
            with self.subTest(path=path.relative_to(FILES)):
                packed = lz10.decompress(path.read_bytes())
                entry = next(e for e in pak.read_pak_entries(packed) if e.name == "map.bin")
                self.assertIsInstance(map_file.read_map_bytes(pak.read_pak_file_content(packed, entry)),
                                      map_file.MapData)

    def test_shop_files_round_trip_with_person_and_forge_sections(self):
        for difficulty in RADIANT_DAWN_PROFILE.shop_difficulties:
            path = RADIANT_DAWN_PROFILE.shop_path(FILES, difficulty)
            raw = path.read_bytes()
            document = shop.parse_shop(raw)
            with self.subTest(difficulty=difficulty):
                self.assertEqual(document.dialect, "fe10")
                self.assertTrue(any(s.name.startswith("SHOP_PERSON_") for s in document.sections))
                self.assertEqual(shop.build_shop(document), raw)


@unittest.skipUnless(ROOT and (ROOT / "sys" / "boot.bin").is_file(),
                     "set FE10_EXTRACTED to an extracted Radiant Dawn disc (the folder with sys/ and files/)")
class Fe10DiscTest(unittest.TestCase):
    def test_wii_layout_and_detection(self):
        for name in ("sys/boot.bin", "sys/main.dol", "sys/fst.bin", "disc", "ticket.bin", "tmd.bin", "cert.bin"):
            self.assertTrue((ROOT / name).exists(), name)
        self.assertTrue(games.read_disc_id(ROOT).startswith("RFE"))
        self.assertIs(games.detect_from_extracted(ROOT), Game.RADIANT_DAWN)

    def test_disc_mismatch_warning_on_a_real_boot_bin(self):
        import shutil
        import tempfile

        from fe_modding.project import ModProject

        with tempfile.TemporaryDirectory() as tmp:
            for game, warns in ((Game.RADIANT_DAWN, False), (Game.PATH_OF_RADIANCE, True)):
                project = ModProject.create(Path(tmp), game.value, game)
                (project.extracted_dir / "sys").mkdir()
                shutil.copy2(ROOT / "sys" / "boot.bin", project.extracted_dir / "sys" / "boot.bin")
                with self.subTest(game=game):
                    self.assertEqual(project.disc_mismatch_warning() is not None, warns)


if __name__ == "__main__":
    unittest.main()
