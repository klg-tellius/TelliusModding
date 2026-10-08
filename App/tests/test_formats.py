import io
import json
import math
import os
import struct
import sys
import tempfile
import unittest
from pathlib import Path

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fe_modding.formats import animation, dispo, engine_pose, face_data, gcdisc, dsp_adpcm, event_script, fe8data, gltf_export, gltf_import, gs_file, gs_stats, lz10, map_file, message, model, pak, portrait_anim, shop, skeleton, stm, thp, tpl
from fe_modding.gui import map_scene, model_viewer


class SkeletonBoneTests(unittest.TestCase):
    _IDENTITY_ROTATION = ((1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0))

    def _build_synthetic_g_bytes(self, rotations=None):
        num_bones = 2
        bones_start = skeleton.BONES_START
        string_pool_offset = bones_start + skeleton.BONE_RECORD_SIZE * num_bones
        if rotations is None:
            rotations = [self._IDENTITY_ROTATION, self._IDENTITY_ROTATION]

        def build_record(parent_index, position, rotation, name_offset):
            floats = [0.0] * 55
            for row, offset in zip(rotation, skeleton._ROTATION_ROW_OFFSETS):
                floats[offset], floats[offset + 1], floats[offset + 2] = row
                floats[offset + 3] = 999.0  # the excluded 4th column - must never leak into .rotation
            floats[24], floats[25], floats[26] = position
            floats[27], floats[28], floats[29] = position  # real files duplicate this triple verbatim
            return struct.pack(skeleton.BONE_RECORD_FORMAT, parent_index, 0, 0, 0, *floats, 0, 0, name_offset)

        header = struct.pack(">IIII", 0, string_pool_offset, num_bones, bones_start)
        record0 = build_record(-1, (0.0, 0.0, 0.0), rotations[0], 0)
        record1 = build_record(0, (1.5, 2.5, -3.5), rotations[1], 5)
        names = b"root\x00child\x00"
        return header + record0 + record1 + names

    def test_position_reads_the_confirmed_offset(self):
        bones = skeleton.read_skeleton(io.BytesIO(self._build_synthetic_g_bytes()))
        self.assertEqual(len(bones), 2)
        self.assertEqual(bones[0].name, "root")
        self.assertEqual(bones[0].parent_index, -1)
        self.assertEqual(bones[0].position, (0.0, 0.0, 0.0))
        self.assertEqual(bones[1].name, "child")
        self.assertEqual(bones[1].parent_index, 0)
        self.assertEqual(bones[1].position, (1.5, 2.5, -3.5))

    def test_rotation_reads_the_confirmed_rows_and_excludes_the_4th_column(self):
        # a 90-degree rotation about Z: X axis -> Y axis, Y axis -> -X axis
        rotate_z_90 = ((0.0, -1.0, 0.0), (1.0, 0.0, 0.0), (0.0, 0.0, 1.0))
        data = self._build_synthetic_g_bytes(rotations=[self._IDENTITY_ROTATION, rotate_z_90])
        bones = skeleton.read_skeleton(io.BytesIO(data))
        self.assertEqual(bones[0].rotation, self._IDENTITY_ROTATION)
        self.assertEqual(bones[1].rotation, rotate_z_90)
        # the sentinel placed at indices 3/7/11 must not appear anywhere in .rotation
        self.assertNotIn(999.0, [v for row in bones[1].rotation for v in row])


def _rig_bone(name, parent, pivot, flags=0x180, translate=(0.0, 0.0, 0.0), skin=None, scale=1.0):
    """A bone in the engine's layout: skin matrix, value block (scale 1,
    rotate 0, the given translate, rotate/scale pivot) and the +0xBC seed
    the engine derives from them."""
    values = [0.0] * engine_pose.VALUE_COUNT
    values[0:3] = [scale, scale, scale]
    values[6:9] = translate
    values[12:15] = pivot
    values[15:18] = pivot
    seed = engine_pose.local_matrix(values, flags | engine_pose.ALL_CHANNELS)
    values[31:43] = [c for row in seed for c in row]
    skin = skin or skeleton.IDENTITY_3X4
    floats = tuple(c for row in skin for c in row) + tuple(values)
    return skeleton.Bone(name, parent, (-1, -1, flags), floats, (0, 1))


def _curve(bone, channel, keys, shift=0):
    return animation.AnimCurve(bone, channel, shift, keys[-1][0], [animation.Keyframe(f, v) for f, v in keys])


def _animation_of(curves_by_bone, end_frame=10, events=()):
    groups, curves = [], []
    for bone, (mask, bone_curves) in sorted(curves_by_bone.items()):
        groups.append(animation.BoneGroup(bone, mask, len(curves), len(bone_curves)))
        curves += bone_curves
    header = animation.GaHeader(words=(0, 0, 0, 0x11, 0, 1, end_frame, 0, 0, 0, 0, 0))
    footer = None
    if events:
        footer = animation.GaFooter(blocks=[animation.write_event_block(list(events))] + [None] * 8, order=[0])
    anim = animation.GaAnimation(header=header, groups=groups, curves=curves, events=list(events), footer=footer)
    return animation.read_animation_bytes(animation.write_animation(anim))


class EnginePoseTests(unittest.TestCase):
    def test_seed_matches_the_value_block(self):
        bone = _rig_bone("b", -1, (1.0, 2.0, 3.0), translate=(0.5, 0.0, 0.0))
        self.assertEqual(engine_pose.local_matrices([bone])[0], skeleton.local_bind_matrix(bone))

    def test_curve_values_are_absolute_scaled_and_clamped(self):
        curve = _curve(0, 3, [(2, 256), (6, 512)], shift=8)  # 1.0 then 2.0
        self.assertEqual(engine_pose.curve_value(curve, 0.0), 1.0)
        self.assertEqual(engine_pose.curve_value(curve, 4.0), 1.5)
        self.assertEqual(engine_pose.curve_value(curve, 9.0), 2.0)

    def test_rotation_turns_about_the_rotate_pivot(self):
        bones = [_rig_bone("root", -1, (0.0, 0.0, 0.0)), _rig_bone("arm", 0, (1.0, 0.0, 0.0))]
        anim = _animation_of({1: (animation.MASK_ROTATE, [_curve(1, 5, [(0, 0), (10, 90)])])})
        world, palette = engine_pose.pose(bones, anim, 10.0)
        x, y, z = engine_pose.apply(palette[1], (2.0, 0.0, 0.0))
        self.assertAlmostEqual(x, 1.0, places=6)
        self.assertAlmostEqual(y, 1.0, places=6)
        self.assertAlmostEqual(z, 0.0, places=6)

    def test_parent_rotation_carries_the_child(self):
        bones = [_rig_bone("root", -1, (0.0, 0.0, 0.0)), _rig_bone("child", 0, (1.0, 0.0, 0.0))]
        anim = _animation_of({0: (animation.MASK_ROTATE, [_curve(0, 5, [(0, 0), (10, 90)])])})
        world, _palette = engine_pose.pose(bones, anim, 10.0)
        x, y, _z = engine_pose.apply(world[1], (1.0, 0.0, 0.0))
        self.assertAlmostEqual(x, 0.0, places=6)
        self.assertAlmostEqual(y, 1.0, places=6)

    def test_euler_decomposition_round_trips(self):
        for angles in ((10.0, 20.0, 30.0), (-120.0, 45.0, 170.0), (5.0, 90.0, 0.0)):
            m = engine_pose.euler_matrix(1, *angles)
            again = engine_pose.euler_matrix(1, *engine_pose.euler_from_matrix(engine_pose.decompose(m)[1]))
            for r in range(3):
                for c in range(3):
                    self.assertAlmostEqual(m[r][c], again[r][c], places=9)

    def test_zero_scale_decomposes(self):
        _t, rot, scale = engine_pose.decompose(engine_pose.scaling(0.0, 0.0, 0.0))
        self.assertEqual(scale, (0.0, 0.0, 0.0))
        self.assertEqual(rot, ((1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0)))


class DispoFieldNamesTests(unittest.TestCase):
    def test_fields_are_named(self):
        self.assertEqual(dispo.field_name(0), "pid")
        self.assertEqual(dispo.field_name(1), "jid")
        self.assertEqual(dispo.field_name(7), "item4")
        self.assertEqual(dispo.field_name(10), "item7")
        self.assertEqual(dispo.field_name(11), "skill0")
        self.assertEqual(dispo.field_name(19), "bonus_hp")
        self.assertEqual(dispo.field_name(26), "bonus_res")
        self.assertEqual(dispo.field_name(28), "seq_attack")
        self.assertEqual(dispo.field_name(31), "mtype")
        self.assertEqual(dispo.field_name(36), "level")
        self.assertEqual(dispo.field_name(37), "faction")
        self.assertEqual(dispo.field_name(38), "flags")
        self.assertEqual(dispo.field_name(39), "ai_order")
        self.assertEqual(dispo.field_name(40), "item0_flag")

    def test_skipped_fields_return_none(self):
        for index in (2, 16, 17, 18):
            self.assertIsNone(dispo.field_name(index))


class DispoReplacementTableTests(unittest.TestCase):
    def test_build_replacement_table_lists_only_resolving_positions(self):
        from fe_modding.formats.common import HEADER_SIZE

        # four 4-byte-aligned "fields" right after the header: resolves,
        # doesn't resolve, resolves, null (doesn't resolve either)
        data = bytearray(HEADER_SIZE + 16)
        struct.pack_into(">I", data, HEADER_SIZE + 0, 100)
        struct.pack_into(">I", data, HEADER_SIZE + 4, 999)
        struct.pack_into(">I", data, HEADER_SIZE + 8, 200)
        struct.pack_into(">I", data, HEADER_SIZE + 12, 0)
        label_map = {100: b"PID_TEST", 200: b"JID_TEST"}
        label_map_start = HEADER_SIZE + 16

        table = dispo.build_replacement_table(bytes(data), label_map, label_map_start)

        # only offsets 0 and 8 (HEADER_SIZE-relative) resolve - 4 and 12 don't
        self.assertEqual(table, struct.pack(">II", 0, 8))


from dispo_fixture import build_minimal_dispo_bytes as _build_minimal_dispo_bytes  # noqa: E402


def _unit_sections(sections):
    return [s for s in sections if s.count > 0]


class DispoInsertUnitTests(unittest.TestCase):
    def test_fixture_parses_as_expected(self):
        sections = dispo.read_dispo_bytes(_build_minimal_dispo_bytes())
        self.assertEqual([s.name for s in sections], ["DATE", "SECA", "SECB"])
        self.assertEqual(sections[0].linked_label, b"DATE")
        for section in _unit_sections(sections):
            self.assertEqual(section.units[0].fields[0].label, b"PID_TEST")
            self.assertEqual(section.units[0].fields[1].label, b"JID_TEST")

    def test_insert_unit_appends_and_preserves_every_other_labels_field(self):
        data = _build_minimal_dispo_bytes()
        sections = _unit_sections(dispo.read_dispo_bytes(data))
        field_values = [f.value for f in sections[0].units[0].fields]

        new_data = dispo.insert_unit(data, sections, sections[0], field_values)
        new_sections = dispo.read_dispo_bytes(new_data)

        self.assertEqual([len(s.units) for s in new_sections], [0, 2, 1])
        self.assertEqual(new_sections[0].linked_label, b"DATE")
        for unit in new_sections[1].units + new_sections[2].units:
            self.assertEqual(unit.fields[0].label, b"PID_TEST")
            self.assertEqual(unit.fields[1].label, b"JID_TEST")
            for f in unit.fields[2:]:
                self.assertEqual(f.value, 0)
        self.assertEqual(struct.unpack_from(">I", new_data, 0)[0], len(new_data))
        self.assertEqual(struct.unpack_from(">I", new_data, 8)[0], 7)  # date + 3 units x 2 pointers

    def test_insert_unit_twice_into_different_sections(self):
        data = _build_minimal_dispo_bytes()
        sections = _unit_sections(dispo.read_dispo_bytes(data))
        data = dispo.insert_unit(data, sections, sections[0], [f.value for f in sections[0].units[0].fields])

        sections = _unit_sections(dispo.read_dispo_bytes(data))
        data = dispo.insert_unit(data, sections, sections[1], [f.value for f in sections[1].units[0].fields])

        sections = _unit_sections(dispo.read_dispo_bytes(data))
        self.assertEqual([len(s.units) for s in sections], [2, 2])
        for section in sections:
            for unit in section.units:
                self.assertEqual(unit.fields[0].label, b"PID_TEST")
                self.assertEqual(unit.fields[1].label, b"JID_TEST")

    def test_insert_unit_rejects_full_section(self):
        full_section = dispo.DispoSection(name="X", address=0, count=127, linked_label=None, units=[])
        with self.assertRaises(ValueError):
            dispo.insert_unit(b"", [], full_section, [0] * len(dispo.FIELD_LAYOUT))

    def test_insert_unit_rejects_wrong_field_count(self):
        section = dispo.DispoSection(name="X", address=0, count=0, linked_label=None, units=[])
        with self.assertRaises(ValueError):
            dispo.insert_unit(b"", [], section, [0] * 10)


class DispoRenameChapterSectionsTests(unittest.TestCase):
    def test_renames_matching_sections_and_preserves_everything_else(self):
        data = _build_minimal_dispo_bytes((b"bmap01_a", b"bmap01_b"))
        sections = dispo.read_dispo_bytes(data)
        self.assertEqual([s.name for s in sections], ["DATE", "bmap01_a", "bmap01_b"])

        renamed = dispo.rename_chapter_sections(data, "01", "32")
        new_sections = dispo.read_dispo_bytes(renamed)
        self.assertEqual([s.name for s in new_sections], ["DATE", "bmap32_a", "bmap32_b"])

        # every byte outside the renamed digits is untouched
        self.assertEqual(len(renamed), len(data))
        diff_positions = [i for i in range(len(data)) if data[i] != renamed[i]]
        self.assertEqual(len(diff_positions), 4)  # 2 digits x 2 section names

    def test_rejects_mismatched_length_chapter_numbers(self):
        with self.assertRaises(ValueError):
            dispo.rename_chapter_sections(b"bmap01_a\x00", "01", "132")


def _build_map_object(flag_bits_a=0, flag_bits_c=0, filename="prop_01") -> "map_file.MapObject":
    return map_file.MapObject(
        offset_x=0.0, offset_y=0.0, offset_z=0.0, size_x=1.0, size_y=1.0, size_z=1.0,
        flag_bits_a=flag_bits_a, flag_bits_b=0, flag_bits_c=flag_bits_c, effect_type=0, filename=filename,
    )


class MapFileFlagBitsTests(unittest.TestCase):
    def test_is_base_terrain_object_requires_both_top_bits(self):
        # confirmed against every real chapter map: both bits are always
        # set together on the map's own base terrain/water model, never
        # independently - see MapObject's docstring
        self.assertTrue(map_file.is_base_terrain_object(_build_map_object(flag_bits_a=0b11000000, filename="bmap01")))
        self.assertFalse(map_file.is_base_terrain_object(_build_map_object(flag_bits_a=0b10000000)))
        self.assertFalse(map_file.is_base_terrain_object(_build_map_object(flag_bits_a=0b01000000)))
        self.assertFalse(map_file.is_base_terrain_object(_build_map_object(flag_bits_a=0)))

    def test_has_ga_animation_checks_bit_1_only(self):
        # confirmed with zero exceptions against real archive contents that
        # bit 1 (not bit 0, despite the old "no .ga file" guess) is what
        # tracks a real matching .ga file - see MapObject's docstring
        self.assertTrue(map_file.has_ga_animation(_build_map_object(flag_bits_c=0b00000010)))
        self.assertFalse(map_file.has_ga_animation(_build_map_object(flag_bits_c=0b00000001)))
        self.assertFalse(map_file.has_ga_animation(_build_map_object(flag_bits_c=0)))


def _build_minimal_map_bytes(sections: list[tuple[str, bytes]]) -> bytes:
    from fe_modding.formats.common import HEADER_SIZE

    out = bytearray(HEADER_SIZE)
    section_addrs = []
    for _name, payload in sections:
        section_addrs.append(len(out))
        out += payload

    table_start = len(out)
    names = b""
    name_offsets = {}
    for name, _payload in sections:
        name_offsets[name] = len(names)
        names += name.encode("ascii") + b"\x00"

    for (name, _payload), address in zip(sections, section_addrs):
        out += struct.pack(">II", address - HEADER_SIZE, name_offsets[name])
    out += names

    struct.pack_into(">III", out, 0, len(out), table_start - HEADER_SIZE, 0)
    return bytes(out)


class MapFileGridTests(unittest.TestCase):
    def test_sparse_link_grid_uses_the_same_x_y_indexing_as_panel_grids(self):
        capacity = struct.pack(">HHHHf", 3, 2, 0, 0, 2000.0)
        link = struct.pack(">H", 2) + bytes([2, 1, 0xA5, 0, 1, 0x11])
        data = _build_minimal_map_bytes([("mapcapacity", capacity), ("maplink", link)])

        parsed = map_file.read_map_bytes(data)

        self.assertEqual(len(parsed.link), 3)
        self.assertEqual(len(parsed.link[0]), 2)
        self.assertEqual(parsed.link[2][1], 0xA5)
        self.assertEqual(parsed.link[0][1], 0x11)
        self.assertEqual(parsed.link[1][1], -1)

    def test_compose_link_status_matches_native_section_order(self):
        data = map_file.MapData(
            capacity=map_file.MapCapacity(2, 2, 0, 0, 2000.0),
            link=[[0x03, -1], [-1, -1]],
            link_at=[[0x0B, -1], [-1, 0x05]],
            link_abs=[[0x06, -1], [-1, -1]],
        )

        status = map_file.compose_link_status_grid(data, apply_height_rules=False)

        # maplinkAbs is applied after maplinkAt by the native loader and
        # replaces the cell with low nibble + inverted low nibble.
        self.assertEqual(status[0][0], 0x96)
        self.assertEqual(status[1][1], 0x0500 | map_file.LINK_DEFAULT_OPEN)  # not in maplink: open
        self.assertEqual(status[0][1], map_file.LINK_DEFAULT_OPEN)  # listed nowhere
        self.assertEqual(map_file.link_passable_directions(status[0][0]), ("east", "south"))

    def test_link_height_rules_clear_only_blocked_direction_bits(self):
        panels = [
            map_file.UniquePanel(100, 100, 100, 100, 0),
            map_file.UniquePanel(600, 100, 600, 100, 0),
            map_file.UniquePanel(100, 100, 100, 100, 0),
        ]
        data = map_file.MapData(
            capacity=map_file.MapCapacity(3, 1, 0, 0, 2000.0),
            panel_index=[[0], [1], [2]],
            unique_panel=panels,
            link=[[map_file.LINK_PASS_EAST], [map_file.LINK_PASS_WEST | map_file.LINK_PASS_EAST], [map_file.LINK_PASS_WEST]],
        )

        status = map_file.compose_link_status_grid(data)

        self.assertEqual(status[0][0], 0)
        self.assertEqual(status[1][0] & map_file.LINK_PASS_WEST, 0)
        self.assertEqual(status[1][0] & map_file.LINK_PASS_EAST, map_file.LINK_PASS_EAST)
        self.assertEqual(status[2][0] & map_file.LINK_PASS_WEST, map_file.LINK_PASS_WEST)

    def test_link_tiles_are_adjacent_passable_uses_source_direction_bit(self):
        status = [[0, 0, 0], [0, map_file.LINK_PASS_NORTH | map_file.LINK_PASS_EAST, 0], [0, 0, 0]]

        self.assertTrue(map_file.link_tiles_are_adjacent_passable(status, 1, 1, 1, 0))
        self.assertTrue(map_file.link_tiles_are_adjacent_passable(status, 1, 1, 2, 1))
        self.assertFalse(map_file.link_tiles_are_adjacent_passable(status, 1, 1, 1, 2))
        self.assertFalse(map_file.link_tiles_are_adjacent_passable(status, 1, 1, 0, 1))
        self.assertFalse(map_file.link_tiles_are_adjacent_passable(status, 1, 1, 2, 2))


class MapSceneGameplayGridTests(unittest.TestCase):
    def test_gameplay_grid_is_anchored_to_mapextra_placement_origin(self):
        data = map_file.MapData(
            capacity=map_file.MapCapacity(16, 14, 1, 1, 2000.0),
            build_desc=[_build_map_object(flag_bits_a=0b11000000, filename="bmap01")],
            build_inst=[_build_map_build_instance(x=-22, y=-20, desc_index=0)],
            extra=map_file.MapExtra(22, 20, 8, 7, 64, 3, (0, 0), 0),
        )

        overlay = map_scene.compute_gameplay_grid_overlay(data)

        self.assertEqual((overlay.col_min, overlay.col_max), (3, 13))
        self.assertEqual((overlay.row_min, overlay.row_max), (3, 11))
        self.assertEqual(overlay.origin_col, -22.0)
        self.assertEqual(overlay.origin_row, -20.0)

    def test_gameplay_grid_can_fall_back_to_the_terrain_instance_origin(self):
        data = map_file.MapData(
            capacity=map_file.MapCapacity(3, 2, 1, 1, 2000.0),
            build_desc=[_build_map_object(flag_bits_a=0b11000000, filename="bmap_test")],
            build_inst=[_build_map_build_instance(x=-5, y=-7, desc_index=0)],
        )

        overlay = map_scene.compute_gameplay_grid_overlay(data)

        self.assertEqual(overlay.origin_col, -5.0)
        self.assertEqual(overlay.origin_row, -7.0)

    def test_bmap01_projection_is_derived_from_mapextra_and_terrain_instance(self):
        data = map_file.MapData(
            capacity=map_file.MapCapacity(16, 14, 1, 1, 2000.0),
            build_desc=[_build_map_object(flag_bits_a=0b11000000, filename="bmap01")],
            build_inst=[_build_map_build_instance(x=-22, y=-20, desc_index=0)],
            extra=map_file.MapExtra(22, 20, 8, 7, 64, 3, (0, 0), 0),
        )

        projection = map_scene.compute_map_texture_projection("bmap01", data)

        self.assertIsNotNone(projection)
        self.assertEqual(
            projection.selector_matrix,
            (
                (0.0015625, 0.0, 0.0, 0.0),
                (0.0, 0.0, 0.0015625, 0.0),
                (0.0, 0.0, 0.0, 1.0),
            ),
        )
        self.assertEqual(
            projection.last_matrix,
            (
                (0.003125, 0.0, 0.0, 0.03125),
                (0.0, 0.0, 0.003125, 0.078125),
                (0.0, 0.0, 0.0, 1.0),
            ),
        )

    def test_map_transform_preserves_texture_layers(self):
        layer = model_viewer._TextureLayer(
            uv=((0.0, 0.0), (1.0, 0.0), (0.0, 1.0)),
            texture=object(),
            role="detail",
        )
        tri = model_viewer._Triangle(
            a=(0.0, 0.0, 0.0),
            b=(1.0, 0.0, 0.0),
            c=(0.0, 0.0, 1.0),
            normal=(0.0, 1.0, 0.0),
            color=(255, 255, 255),
            texture_layers=(layer,),
        )

        transformed = map_scene._transform_triangle(
            tri,
            [
                [1.0, 0.0, 0.0, 2.0],
                [0.0, 1.0, 0.0, 3.0],
                [0.0, 0.0, 1.0, 4.0],
                [0.0, 0.0, 0.0, 1.0],
            ],
        )

        self.assertEqual(transformed.a, (2.0, 3.0, 4.0))
        self.assertIs(transformed.texture_layers[0], layer)

    def _view_canvas(self):
        canvas = object.__new__(model_viewer._ModelCanvas)
        canvas._yaw, canvas._pitch, canvas._zoom = 0.6, -0.4, 1.0
        canvas._screen_x_sign, canvas._screen_y_sign = 1.0, -1.0
        canvas._center = canvas._home_center = (1.0, 2.0, 3.0)
        canvas._extent = 10.0
        canvas._schedule_redraw = lambda: None
        canvas.winfo_width = lambda: 400
        canvas.winfo_height = lambda: 300
        return canvas

    @staticmethod
    def _screen_point(canvas, point):
        rx, ry, _rz = canvas._rotate(tuple(p - c for p, c in zip(point, canvas._center)))
        scale = canvas._view_scale()
        return 200 + rx * scale * canvas._screen_x_sign, 150 - ry * scale * canvas._screen_y_sign

    def test_zoom_keeps_the_point_under_the_cursor(self):
        canvas = self._view_canvas()
        point = (3.0, 1.0, 5.0)
        x, y = self._screen_point(canvas, point)
        for _ in range(30):
            canvas._zoom_by(1.15, x, y)
        self.assertGreater(canvas._zoom, 6.0)
        after = self._screen_point(canvas, point)
        self.assertAlmostEqual(after[0], x, places=6)
        self.assertAlmostEqual(after[1], y, places=6)
        canvas._zoom_by(1e9, x, y)
        self.assertEqual(canvas._zoom, model_viewer.ZOOM_MAX)

    def test_pan_moves_content_with_the_cursor(self):
        canvas = self._view_canvas()
        point = (3.0, 1.0, 5.0)
        x, y = self._screen_point(canvas, point)
        canvas._drag_start = None
        canvas._on_pan_start(type("E", (), {"x": 100, "y": 100})())
        canvas._on_pan_motion(type("E", (), {"x": 130, "y": 80})())
        after = self._screen_point(canvas, point)
        self.assertAlmostEqual(after[0], x + 30, places=6)
        self.assertAlmostEqual(after[1], y - 20, places=6)
        canvas.reset_view()
        self.assertEqual(canvas._center, (1.0, 2.0, 3.0))

    def test_top_down_view_matches_game_facing_horizontal_orientation(self):
        canvas = object.__new__(model_viewer._ModelCanvas)
        canvas._yaw = 0.0
        canvas._pitch = 0.0
        canvas._zoom = 1.0
        canvas._schedule_redraw = lambda: None

        canvas.top_down_view()
        right = canvas._rotate((1.0, 0.0, 0.0))
        up = canvas._rotate((0.0, 0.0, 1.0))

        self.assertGreater(right[0] * canvas._screen_x_sign, 0.0)
        self.assertGreater(up[1], 0.0)

    def test_texture_sampling_can_flip_v_for_terrain_detail(self):
        image = Image.new("RGB", (1, 2))
        image.putpixel((0, 0), (0, 0, 255))
        image.putpixel((0, 1), (255, 0, 0))

        self.assertEqual(model_viewer._sample_texture(image, (0.5, 0.0)), (0, 0, 255))
        self.assertEqual(model_viewer._sample_texture(image, (0.5, 0.0), flip_v=True), (255, 0, 0))

    def test_static_gs_texture_sampling_modulates_base_and_light_layer(self):
        atlas = Image.new("RGB", (2, 1))
        atlas.putpixel((0, 0), (0, 0, 100))
        atlas.putpixel((1, 0), (100, 0, 0))
        atlas_array = model_viewer._texture_array(atlas, {})
        light = model_viewer._texture_array(Image.new("RGB", (1, 1), (255, 255, 255)), {})
        ignored = model_viewer._texture_array(Image.new("RGB", (1, 1), (255, 0, 0)), {})

        base_uv = ((0.1, 0.0), (0.1, 0.0), (0.1, 0.0))
        detail_uv = ((0.75, 0.0), (0.75, 0.0), (0.75, 0.0))
        layers = (
            model_viewer._TextureLayer(base_uv, atlas_array, "diffuse", color_scale=(0.5, 0.5, 0.5)),
            model_viewer._TextureLayer(detail_uv, ignored, "unused"),
            model_viewer._TextureLayer(detail_uv, light, "light"),
        )

        one = model_viewer.np.ones((1, 1))
        zero = model_viewer.np.zeros((1, 1))

        sampled = model_viewer._sample_texture_layers(layers, one, zero, zero)

        self.assertEqual(tuple(model_viewer.np.rint(sampled[0, 0, :3]).astype(int)), (0, 0, 65))

    def test_map_callback_uv2_detail_layer_reuses_base_texture_before_light(self):
        atlas = Image.new("RGB", (2, 1))
        atlas.putpixel((0, 0), (0, 0, 100))
        atlas.putpixel((1, 0), (100, 0, 0))
        atlas_array = model_viewer._texture_array(atlas, {})
        light = model_viewer._texture_array(Image.new("RGB", (1, 1), (128, 128, 128)), {})

        base_uv = ((0.1, 0.0), (0.1, 0.0), (0.1, 0.0))
        detail_uv = ((0.75, 0.0), (0.75, 0.0), (0.75, 0.0))
        layers = (
            model_viewer._TextureLayer(base_uv, atlas_array, "diffuse", color_scale=(0.5, 0.5, 0.5)),
            model_viewer._TextureLayer(detail_uv, atlas_array, "callback_uv2_detail", color_scale=(0.5, 0.5, 0.5)),
            model_viewer._TextureLayer(detail_uv, light, "light"),
        )

        one = model_viewer.np.ones((1, 1))
        zero = model_viewer.np.zeros((1, 1))

        sampled = model_viewer._sample_texture_layers(layers, one, zero, zero)

        self.assertEqual(tuple(model_viewer.np.rint(sampled[0, 0, :3]).astype(int)), (30, 0, 20))

    def test_map_callback_selector_lerps_uv0_and_uv2_before_projected_light(self):
        atlas = Image.new("RGB", (2, 1))
        atlas.putpixel((0, 0), (0, 0, 100))
        atlas.putpixel((1, 0), (100, 0, 0))
        atlas_array = model_viewer._texture_array(atlas, {})
        selector = model_viewer._texture_array(Image.new("RGB", (1, 1), (255, 255, 255)), {})
        light = model_viewer._texture_array(Image.new("RGB", (1, 1), (128, 128, 128)), {})

        base_uv = ((0.1, 0.0), (0.1, 0.0), (0.1, 0.0))
        detail_uv = ((0.75, 0.0), (0.75, 0.0), (0.75, 0.0))
        projected_uv = ((0.25, 0.25), (0.25, 0.25), (0.25, 0.25))
        layers = (
            model_viewer._TextureLayer(base_uv, atlas_array, "diffuse", color_scale=(0.5, 0.5, 0.5)),
            model_viewer._TextureLayer(detail_uv, atlas_array, "callback_uv2_detail", color_scale=(0.5, 0.5, 0.5)),
            model_viewer._TextureLayer(projected_uv, selector, "map_selector"),
            model_viewer._TextureLayer(projected_uv, light, "map_projected_light"),
        )

        one = model_viewer.np.ones((1, 1))
        zero = model_viewer.np.zeros((1, 1))

        sampled = model_viewer._sample_texture_layers(layers, one, zero, zero)

        self.assertEqual(tuple(model_viewer.np.rint(sampled[0, 0, :3]).astype(int)), (25, 0, 0))

    def test_map_texture_projection_uses_3x4_matrix_with_q_divide(self):
        projection = model_viewer.MapTextureProjection(
            selector_matrix=((2.0, 0.0, 0.0, 1.0), (0.0, 3.0, 0.0, 2.0), (0.0, 0.0, 0.0, 2.0)),
            last_matrix=((0.0, 0.0, 4.0, 4.0), (0.0, 5.0, 0.0, 5.0), (0.0, 0.0, 0.0, 1.0)),
        )

        self.assertEqual(projection.selector_uv((3.0, 4.0, 5.0)), (3.5, 7.0))
        self.assertEqual(projection.last_uv((3.0, 4.0, 5.0)), (24.0, 25.0))

    def test_model_texture_loader_preserves_tpl_alpha(self):
        container = _build_minimal_format_tpl(4, 4, tpl.FORMAT_RGBA8)
        patched = tpl.replace_image(container, 0, Image.new("RGBA", (4, 4), (12, 34, 56, 78)))

        textures = model_viewer._load_textures({"texpack.tpl": patched})
        sampled = model_viewer._texture_array(textures[0].image, {})

        self.assertEqual(sampled.shape[2], 4)
        self.assertEqual(int(sampled[0, 0, 3]), 78)


def _build_map_build_instance(x=0, y=0, angle=0, desc_index=0, unused=(0, 0, 0, 0)):
    return map_file.MapBuildInstance(
        x=x, y=y, angle=angle, desc_index=desc_index, x2=x, y2=y, end_x2=x, end_y2=y, unused=unused,
    )


def _unused_bytes_for_height(value: float) -> tuple:
    """Pack a float height as the 4 raw (signed) bytes MapBuildInstance.height()
    expects to reinterpret - i.e. the real on-disk encoding, not a plain int."""
    return tuple(struct.unpack(">bbbb", struct.pack(">f", value)))


class MapBuildInstanceTransformTests(unittest.TestCase):
    """Synthetic checks for the placement formula confirmed via live
    emulator debugging - see MAP_PLACEMENT_INVESTIGATION.md's "Session 5"
    and GAME_NOTES.md §12's Twentieth finding for the full evidence trail.
    These test the *math* (matrix composition matches the documented
    formula exactly) with hand-picked values, not real game data - real
    chapter data has no independently-known-correct world position to
    check against, only internal consistency."""

    def test_height_raw_reads_the_four_bytes_as_one_big_endian_uint32(self):
        self.assertEqual(_build_map_build_instance(unused=(0, 0, 0, 1)).height_raw(), 1)
        self.assertEqual(_build_map_build_instance(unused=(0, 0, 1, 0)).height_raw(), 256)
        self.assertEqual(_build_map_build_instance(unused=(1, 0, 0, 0)).height_raw(), 0x01000000)
        self.assertEqual(_build_map_build_instance(unused=(0x12, 0x34, 0x56, 0x78)).height_raw(), 0x12345678)

    def test_height_reinterprets_bits_as_float32_not_numeric_conversion(self):
        # a real bmap01 instance's raw unused bytes - height_raw() alone
        # (float(3190690939)) would put this prop billions of world units
        # underground, physically impossible; the real game reinterprets
        # the same 4 bytes as a float32's raw bits instead, giving a small,
        # sensible value matching every other confirmed height/offset scale
        # in this format (see MapBuildInstance's own docstring).
        inst = _build_map_build_instance(unused=(-66, 46, 20, 123))
        self.assertEqual(inst.height_raw(), 3190690939)
        self.assertAlmostEqual(inst.height(), -0.17, places=2)

        # round-trip: packing a chosen float and reading it back
        for target in (0.0, -0.17, 2.5, -38.0):
            inst = _build_map_build_instance(unused=_unused_bytes_for_height(target))
            self.assertAlmostEqual(inst.height(), target, places=4)

    def test_world_transform_at_angle_zero_reduces_to_translate_then_scale(self):
        # RotateY(0) is identity, and the pivot translate/untranslate pair
        # (T(pivot) * I * T(-pivot)) collapses to identity too, so at
        # angle=0 the whole matrix should reduce to exactly Translate(pos) *
        # Scale(map_scale) - regardless of the pivot or map_scale value.
        inst = _build_map_build_instance(x=3, y=-2, angle=0, unused=_unused_bytes_for_height(10.0))
        m = inst.world_transform(map_scale=2.0)
        self.assertAlmostEqual(inst.height(), 10.0)

        # translation column: pos = (5*x, -5*height, 5*y), untouched by scale
        self.assertAlmostEqual(m[0][3], 5.0 * 3)
        self.assertAlmostEqual(m[1][3], -5.0 * 10)
        self.assertAlmostEqual(m[2][3], 5.0 * -2)

        # linear block: scale * identity (no rotation at angle=0)
        for i in range(3):
            for j in range(3):
                expected = 2.0 if i == j else 0.0
                self.assertAlmostEqual(m[i][j], expected, msg=f"m[{i}][{j}]")

    def test_world_transform_zero_everything_is_identity(self):
        inst = _build_map_build_instance(x=0, y=0, angle=0, unused=(0, 0, 0, 0))
        m = inst.world_transform(map_scale=1.0)
        for i in range(4):
            for j in range(4):
                expected = 1.0 if i == j else 0.0
                self.assertAlmostEqual(m[i][j], expected, msg=f"m[{i}][{j}]")

    def test_world_transform_rotation_matches_rotate_y_around_pivot(self):
        import math

        # angle byte 64 -> 360 - 64*360/256 = 270 degrees (the "64 = 90 degrees"
        # scale is confirmed, but the direction/offset is "360 - ..." per the
        # live-debugged formula, not a bare angle*360/256).
        inst = _build_map_build_instance(x=0, y=0, angle=64, unused=(0, 0, 0, 0))
        m = inst.world_transform(map_scale=1.0)

        angle_rad = math.radians(360.0 - (64 * 360.0) / 256.0)
        c, s = math.cos(angle_rad), math.sin(angle_rad)
        # translating to the pivot, rotating, and translating back leaves the
        # rotation/scale (upper-left 3x3) block identical to a bare RotateY -
        # only the translation column shifts (and here pos/height are both
        # zero, so even that stays put at the origin).
        self.assertAlmostEqual(m[0][0], c)
        self.assertAlmostEqual(m[0][2], s)
        self.assertAlmostEqual(m[2][0], -s)
        self.assertAlmostEqual(m[2][2], c)
        self.assertAlmostEqual(m[1][1], 1.0)  # Y axis untouched by a Y-axis rotation

    def test_world_transform_composes_with_parent_matrix(self):
        inst = _build_map_build_instance(x=1, y=1, angle=0, unused=(0, 0, 0, 0))
        parent = [
            [1.0, 0.0, 0.0, 100.0],
            [0.0, 1.0, 0.0, 200.0],
            [0.0, 0.0, 1.0, 300.0],
            [0.0, 0.0, 0.0, 1.0],
        ]
        m = inst.world_transform(map_scale=1.0, parent_matrix=parent)
        # a pure-translation parent just adds its own offset on top
        self.assertAlmostEqual(m[0][3], 100.0 + 5.0 * 1)
        self.assertAlmostEqual(m[1][3], 200.0)
        self.assertAlmostEqual(m[2][3], 300.0 + 5.0 * 1)


class Lz10Tests(unittest.TestCase):
    def test_round_trip_repetitive_data(self):
        original = (b"ABCABCABC123" * 50) + b"the quick brown fox" * 20 + bytes(range(256))
        compressed = lz10.compress(original)
        self.assertEqual(lz10.decompress(compressed), original)

    def test_round_trip_empty(self):
        compressed = lz10.compress(b"")
        self.assertEqual(lz10.decompress(compressed), b"")

    def test_decompress_rejects_bad_magic(self):
        with self.assertRaises(lz10.LZ10Error):
            lz10.decompress(b"\x11\x00\x00\x00")


class PakTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.dir = Path(self._tmp.name)

    def test_round_trip(self):
        files = [
            ("first.bin", b"hello world"),
            ("second.txt", b"x" * 1000),
            ("third.dat", b""),
        ]
        archive_bytes = pak.pack_pak(files)

        entries = pak.read_pak_entries(archive_bytes)
        self.assertEqual([e.name for e in entries], [name for name, _ in files])
        for entry, (_, content) in zip(entries, files):
            self.assertEqual(pak.read_pak_file_content(archive_bytes, entry), content)

    def test_extract_then_repack_is_byte_identical(self):
        files = [("a.bin", b"one two three"), ("b.bin", b"four five six seven")]
        original = pak.pack_pak(files)

        archive_path = self.dir / "archive.pak"
        archive_path.write_bytes(original)
        entries = pak.extract_pak(archive_path, self.dir / "extracted")
        rebuilt = pak.repack_pak(self.dir / "extracted", entries)

        self.assertEqual(rebuilt, original)

    def test_rejects_bad_magic(self):
        with self.assertRaises(pak.PakError):
            pak.read_pak_entries(b"nope" + b"\x00" * 20)


class MessageTests(unittest.TestCase):
    def test_round_trip(self):
        original = [
            message.Message(speaker="IKE", text="Let's go!"),
            message.Message(speaker="MIST", text="Be careful,\nbig brother."),
            message.Message(speaker="IKE", text="I will."),  # repeated speaker, shares a name-blob entry
        ]
        data = message.write_messages(original)
        self.assertEqual(message.read_messages(io.BytesIO(data)), original)

    def test_texts_and_table_are_word_aligned(self):
        # The engine's loader masks the table offset (header +4) and every
        # text offset with & ~3: an unaligned one makes it register garbage IDs.
        messages = [message.Message(speaker=f"MS_{i}", text="x" * i) for i in range(7)]
        data = message.write_messages(messages)
        table = struct.unpack_from(">I", data, 4)[0]
        self.assertEqual(table % 4, 0)
        offsets = [struct.unpack_from(">I", data, 0x20 + table + 8 * i)[0] for i in range(len(messages))]
        self.assertTrue(all(o % 4 == 0 for o in offsets), offsets)
        self.assertEqual(message.read_messages(io.BytesIO(data)), messages)

    def test_round_trip_empty(self):
        data = message.write_messages([])
        self.assertEqual(message.read_messages(io.BytesIO(data)), [])

    def test_tokenize_control_codes_round_trips_to_original_text(self):
        # $R's argument is real Shift-JIS bytes (encoded via cp437, same as
        # a real file stores it) - the exact "up-down conversation" tag
        # confirmed against real dialogue files.
        raw_tag = b"\x8f\xe3\x89\xba\x89\xef\x98b"  # 上下会話, Shift-JIS
        text = (
            "$R" + raw_tag.decode(message.ENCODING) + "|"
            "$s1$FS$c1BOLE|$s1That$MC--$MDpause$w2here.$K"
        )
        tokens = message.tokenize_control_codes(text)

        # every token's raw text concatenated must reproduce the input exactly
        rebuilt = "".join(t if isinstance(t, str) else t.raw for t in tokens)
        self.assertEqual(rebuilt, text)

        names = [t.name for t in tokens if not isinstance(t, str)]
        self.assertEqual(
            names,
            [
                "layout_mode", "select_box", "mouth_set_first", "set_speaker_name",
                "select_box", "mouth_still", "mouth_moving", "pause", "wait_for_input",
            ],
        )

        layout = tokens[0]
        self.assertEqual(layout.name, "layout_mode")
        self.assertEqual(layout.arg, "上下会話")

        speaker = next(t for t in tokens if not isinstance(t, str) and t.name == "set_speaker_name")
        self.assertEqual(speaker.arg, "BOLE")

        pause = next(t for t in tokens if not isinstance(t, str) and t.name == "pause")
        self.assertEqual(pause.arg, "2")

        self.assertIn("pause", tokens)
        self.assertIn("here.", tokens)

    def test_tokenize_control_codes_passes_through_unrecognized_dollar(self):
        # an unmatched "$" (not one of CODEBOOK's real codes) is kept as a
        # literal character rather than raising or eating the rest of the text
        tokens = message.tokenize_control_codes("cost: $5")
        self.assertEqual("".join(t if isinstance(t, str) else t.raw for t in tokens), "cost: $5")


class FaceDataTests(unittest.TestCase):
    def test_synthetic_face_data_records_resolve_fid_and_coordinates(self):
        name = b"FID_IKE"
        record = name + b"\x00" * (32 - len(name)) + struct.pack(">hhhh", 10, 20, 30, 40)
        records = face_data.read_face_data(b"FDAT" + struct.pack(">I", 1) + record)

        self.assertEqual(records["FID_IKE"].eye, (10, 20))
        self.assertEqual(records["FID_IKE"].mouth, (30, 40))


class PortraitAnimTests(unittest.TestCase):
    def test_compositor_fills_base_alpha_holes_with_face_parts(self):
        base = Image.new("RGBA", (32, 32), (0, 0, 0, 255))
        for y in range(10, 14):
            for x in range(10, 14):
                base.putpixel((x, y), (0, 0, 0, 0))
        part = Image.new("RGBA", (4, 4), (255, 0, 0, 255))

        rendered = portrait_anim.PortraitAsset(base=base, parts=(part,)).render(frame_ms=0)

        self.assertEqual(rendered.getpixel((12, 12)), (255, 0, 0, 255))


def _build_minimal_tpl(width: int, height: int) -> bytes:
    """A single-CMPR-image TPL container with zeroed pixel data - just
    enough structure for replace_image() to have a real slot to patch."""
    import struct

    image_header_addr = 12 + 8  # header + one image-entry
    data_addr = image_header_addr + 32  # + one image-header
    out = bytearray()
    out += struct.pack(">III", tpl.MAGIC, 1, 12)  # magic, num_images, offset_image
    out += struct.pack(">II", image_header_addr, 0)  # image entry: offset -> image header, palette_offset (unused)
    out += struct.pack(">HHII", height, width, tpl.FORMAT_CMPR, data_addr)
    out += bytes(20)  # unused trailing image-header fields
    out += bytes(tpl.cmpr_data_length(width, height))
    return bytes(out)


def _build_minimal_c8_tpl(width: int, height: int, palette: list) -> bytes:
    """A single-C8-image TPL container with a real (opaque, RGB555-encoded)
    palette and zeroed pixel data."""
    import struct

    image_header_addr = 12 + 8
    palette_header_addr = image_header_addr + 32
    palette_data_addr = palette_header_addr + 12
    data_addr = palette_data_addr + len(palette) * 2

    out = bytearray()
    out += struct.pack(">III", tpl.MAGIC, 1, 12)
    out += struct.pack(">II", image_header_addr, palette_header_addr)
    out += struct.pack(">HHII", height, width, tpl.FORMAT_C8, data_addr)
    out += bytes(20)
    out += struct.pack(">HxxII", len(palette), 2, palette_data_addr)
    for r, g, b, a in palette:
        assert a == 255, "test helper only encodes opaque colors"
        value = 0x8000 | (round(r / 255 * 31) << 10) | (round(g / 255 * 31) << 5) | round(b / 255 * 31)
        out += struct.pack(">H", value)
    out += bytes(tpl.c8_data_length(width, height))
    return bytes(out)


def _build_minimal_format_tpl(width: int, height: int, fmt: int) -> bytes:
    """A single-image TPL container in a given non-palette tiled format,
    with zeroed pixel data - just enough structure for replace_image() to
    have a real slot to patch."""
    import struct

    image_header_addr = 12 + 8
    data_addr = image_header_addr + 32
    data_length = tpl._block_data_length(width, height, *tpl._BLOCK_SPECS[fmt])
    out = bytearray()
    out += struct.pack(">III", tpl.MAGIC, 1, 12)
    out += struct.pack(">II", image_header_addr, 0)
    out += struct.pack(">HHII", height, width, fmt, data_addr)
    out += bytes(20)
    out += bytes(data_length)
    return bytes(out)


def _build_minimal_c4_tpl(width: int, height: int, palette: list) -> bytes:
    """A single-C4-image TPL container with a real (opaque, RGB555-encoded)
    palette and zeroed pixel data - mirrors _build_minimal_c8_tpl."""
    import struct

    image_header_addr = 12 + 8
    palette_header_addr = image_header_addr + 32
    palette_data_addr = palette_header_addr + 12
    data_addr = palette_data_addr + len(palette) * 2
    data_length = tpl._block_data_length(width, height, *tpl._BLOCK_SPECS[tpl.FORMAT_C4])

    out = bytearray()
    out += struct.pack(">III", tpl.MAGIC, 1, 12)
    out += struct.pack(">II", image_header_addr, palette_header_addr)
    out += struct.pack(">HHII", height, width, tpl.FORMAT_C4, data_addr)
    out += bytes(20)
    out += struct.pack(">HxxII", len(palette), 2, palette_data_addr)
    for r, g, b, a in palette:
        assert a == 255, "test helper only encodes opaque colors"
        value = 0x8000 | (round(r / 255 * 31) << 10) | (round(g / 255 * 31) << 5) | round(b / 255 * 31)
        out += struct.pack(">H", value)
    out += bytes(data_length)
    return bytes(out)


class TplTests(unittest.TestCase):
    def test_tpl_image_info_exposes_sampler_state(self):
        container = bytearray(_build_minimal_tpl(16, 16))
        image_header_addr = 12 + 8
        struct.pack_into(">IIIIf", container, image_header_addr + 0x0C, 1, 2, 5, 1, 0.25)

        info = tpl.read_tpl_image_info(io.BytesIO(container))[0]

        self.assertEqual((info.wrap_s, info.wrap_t), (1, 2))
        self.assertEqual((info.min_filter, info.mag_filter), (5, 1))
        self.assertEqual(info.lod_bias, 0.25)

    def test_replace_image_round_trip(self):
        from PIL import Image

        container = _build_minimal_tpl(16, 16)
        source = Image.new("RGB", (16, 16))
        pixels = source.load()
        for y in range(16):
            for x in range(16):
                pixels[x, y] = (255, 0, 0) if x < 8 else (0, 0, 255)

        patched = tpl.replace_image(container, 0, source)
        self.assertEqual(len(patched), len(container))  # in-place: size never changes

        (decoded,) = tpl.read_tpl_images(io.BytesIO(patched))
        self.assertEqual(decoded.size, (16, 16))
        # CMPR quantizes to RGB565 (5-bit red/blue, 6-bit green), so e.g. 255
        # red comes back as 248 - within quantization error, not exact.
        red = decoded.convert("RGB").getpixel((0, 0))
        blue = decoded.convert("RGB").getpixel((15, 15))
        self.assertLess(abs(red[0] - 255) + red[1] + red[2], 16)
        self.assertLess(blue[0] + blue[1] + abs(blue[2] - 255), 16)

    def test_replace_image_rejects_out_of_range_index(self):
        from PIL import Image

        container = _build_minimal_tpl(8, 8)
        with self.assertRaises(tpl.TplError):
            tpl.replace_image(container, 1, Image.new("RGB", (8, 8)))

    def test_rgb5a3_opaque_bit_is_15_not_7(self):
        # Regression test for the bug a real portrait (IKE.cms) caught: the
        # opaque-vs-alpha branch must key off bit 15 (0x8000), not bit 7
        # (0x80). 0x7080 has bit 7 set but not bit 15 - under the old (wrong)
        # check this decoded as opaque RGB555 (alpha forced to 255); it must
        # actually decode as ARGB3444 with a partial alpha value.
        color = tpl._rgb5a3(0x7080)
        self.assertEqual(color[3], 0x20 * ((0x7080 >> 12) & 0b111))
        self.assertNotEqual(color[3], 255)

    def test_replace_c8_image_round_trip_reuses_existing_palette(self):
        from PIL import Image

        palette = [(0, 0, 0, 255), (255, 0, 0, 255), (0, 0, 255, 255)] + [(0, 0, 0, 255)] * 253
        container = _build_minimal_c8_tpl(16, 16, palette)

        # a color NOT in the palette - must snap to the closest entry, not invent one
        source = Image.new("RGB", (16, 16), (250, 10, 10))
        patched = tpl.replace_image(container, 0, source)
        self.assertEqual(len(patched), len(container))

        (decoded,) = tpl.read_tpl_images(io.BytesIO(patched))
        # RGB555 quantizes 5 bits/channel, so full 255 red comes back as 248 - same
        # ceiling as CMPR's RGB565 in test_replace_image_round_trip, different reason.
        self.assertEqual(decoded.convert("RGB").getpixel((0, 0)), (248, 0, 0))

        # palette bytes themselves must be untouched - other images could share them
        info = tpl.read_tpl_image_info(io.BytesIO(container))[0]
        palette_region = slice(info.palette_offset, info.palette_offset + 12 + len(palette) * 2)
        self.assertEqual(container[palette_region], patched[palette_region])

    def test_replace_i4_image_round_trip(self):
        from PIL import Image

        container = _build_minimal_format_tpl(16, 16, tpl.FORMAT_I4)
        source = Image.new("RGB", (16, 16), (136, 136, 136))  # 136 = 8*17, an exact I4 level

        patched = tpl.replace_image(container, 0, source)
        self.assertEqual(len(patched), len(container))
        (decoded,) = tpl.read_tpl_images(io.BytesIO(patched))
        self.assertEqual(decoded.getpixel((0, 0)), (136, 136, 136, 136))  # alpha = intensity, like I8
        self.assertEqual(tpl.replace_image(patched, 0, decoded), patched)

    def test_replace_ia4_image_round_trip(self):
        from PIL import Image

        container = _build_minimal_format_tpl(16, 16, tpl.FORMAT_IA4)
        source = Image.new("RGBA", (16, 16), (170, 170, 170, 85))  # 170=10*17, 85=5*17

        patched = tpl.replace_image(container, 0, source)
        (decoded,) = tpl.read_tpl_images(io.BytesIO(patched))
        self.assertEqual(decoded.getpixel((0, 0)), (170, 170, 170, 85))

    def test_replace_i8_image_round_trip(self):
        from PIL import Image

        container = _build_minimal_format_tpl(12, 6, tpl.FORMAT_I8)  # partial 8x4 blocks on both axes
        info = tpl.read_tpl_image_info(io.BytesIO(container))[0]
        self.assertEqual(tpl.format_name(info.format), "I8")
        self.assertEqual(info.data_length, 2 * 2 * 32)
        source = Image.new("L", (12, 6))
        source.putdata([(x * 21 + y * 7) % 256 for y in range(6) for x in range(12)])

        patched = tpl.replace_image(container, 0, source)
        self.assertEqual(len(patched), len(container))
        (decoded,) = tpl.read_tpl_images(io.BytesIO(patched))
        for y in range(6):
            for x in range(12):
                v = source.getpixel((x, y))
                self.assertEqual(decoded.getpixel((x, y)), (v, v, v, v))  # alpha = intensity
        self.assertEqual(tpl.encode_i8(decoded), patched[info.data_addr : info.data_addr + info.data_length])

    def test_i8_tiling_is_8x4_row_major(self):
        from PIL import Image

        source = Image.new("L", (16, 4))
        source.putdata([y * 16 + x for y in range(4) for x in range(16)])
        encoded = tpl.encode_i8(source)
        # first block: columns 0-7 of rows 0-3, then the block to its right
        self.assertEqual(list(encoded[:8]), list(range(8)))
        self.assertEqual(list(encoded[8:16]), list(range(16, 24)))
        self.assertEqual(list(encoded[32:40]), list(range(8, 16)))

    def test_replace_ia8_image_round_trip(self):
        from PIL import Image

        container = _build_minimal_format_tpl(16, 16, tpl.FORMAT_IA8)
        source = Image.new("RGBA", (16, 16), (200, 200, 200, 77))

        patched = tpl.replace_image(container, 0, source)
        (decoded,) = tpl.read_tpl_images(io.BytesIO(patched))
        self.assertEqual(decoded.getpixel((0, 0)), (200, 200, 200, 77))

    def test_replace_rgb565_image_round_trip(self):
        from PIL import Image

        container = _build_minimal_format_tpl(16, 16, tpl.FORMAT_RGB565)
        source = Image.new("RGB", (16, 16), (255, 0, 0))

        patched = tpl.replace_image(container, 0, source)
        (decoded,) = tpl.read_tpl_images(io.BytesIO(patched))
        # 5-bit red channel: 255 quantizes to 248, same ceiling as CMPR's RGB565.
        red = decoded.convert("RGB").getpixel((0, 0))
        self.assertLess(abs(red[0] - 255) + red[1] + red[2], 16)

    def test_replace_rgb5a3_image_round_trip_opaque_and_alpha_branches(self):
        from PIL import Image

        container = _build_minimal_format_tpl(16, 16, tpl.FORMAT_RGB5A3)
        source = Image.new("RGBA", (16, 16))
        pixels = source.load()
        for y in range(16):
            for x in range(16):
                pixels[x, y] = (0, 255, 0, 255) if x < 8 else (0, 0, 255, 128)

        patched = tpl.replace_image(container, 0, source)
        (decoded,) = tpl.read_tpl_images(io.BytesIO(patched))
        # opaque pixel takes the higher-precision RGB555 branch (full alpha)
        opaque = decoded.getpixel((0, 0))
        self.assertEqual(opaque[3], 255)
        self.assertLess(opaque[1], 256)
        self.assertGreater(opaque[1], 240)
        # partially-transparent pixel takes the ARGB3444 branch - alpha is
        # quantized to 3 bits (multiples of ~32), not exact, but well within range
        translucent = decoded.getpixel((15, 15))
        self.assertLess(abs(translucent[3] - 128), 32)

    def test_replace_rgba8_image_round_trip_is_exact(self):
        from PIL import Image

        container = _build_minimal_format_tpl(16, 16, tpl.FORMAT_RGBA8)
        source = Image.new("RGBA", (16, 16), (12, 200, 77, 190))

        patched = tpl.replace_image(container, 0, source)
        (decoded,) = tpl.read_tpl_images(io.BytesIO(patched))
        # full 8-bit precision on every channel - no quantization at all
        self.assertEqual(decoded.getpixel((0, 0)), (12, 200, 77, 190))
        self.assertEqual(decoded.getpixel((15, 15)), (12, 200, 77, 190))

    def test_replace_c4_image_round_trip_reuses_existing_palette(self):
        from PIL import Image

        palette = [(0, 0, 0, 255), (255, 0, 0, 255), (0, 0, 255, 255)] + [(0, 0, 0, 255)] * 13
        container = _build_minimal_c4_tpl(16, 16, palette)

        source = Image.new("RGB", (16, 16), (250, 10, 10))  # nearest palette entry: red
        patched = tpl.replace_image(container, 0, source)
        self.assertEqual(len(patched), len(container))

        (decoded,) = tpl.read_tpl_images(io.BytesIO(patched))
        self.assertEqual(decoded.convert("RGB").getpixel((0, 0)), (248, 0, 0))

        # palette bytes themselves must be untouched - other images could share them
        info = tpl.read_tpl_image_info(io.BytesIO(container))[0]
        palette_region = slice(info.palette_offset, info.palette_offset + 12 + len(palette) * 2)
        self.assertEqual(container[palette_region], patched[palette_region])


def _sine_pcm(num_samples: int, freq: float = 440.0, sample_rate: int = 32000, amplitude: int = 12000) -> list[int]:
    import math

    return [round(amplitude * math.sin(2 * math.pi * freq * i / sample_rate)) for i in range(num_samples)]


class DspAdpcmTests(unittest.TestCase):
    def test_round_trip_is_close_to_original(self):
        # Short on purpose - encode() is a real iterative fit, not a quick
        # conversion (~1.5-2x realtime per channel), so keep tests fast.
        pcm = _sine_pcm(3000)
        info = dsp_adpcm.AdpcmInfo()
        encoded = dsp_adpcm.encode(pcm, info)
        decoded = dsp_adpcm.decode(encoded, info, len(pcm))

        self.assertEqual(len(decoded), len(pcm))
        max_diff = max(abs(a - b) for a, b in zip(pcm, decoded))
        # Lossy codec - not exact, but should be well within a few percent
        # of full scale for a clean sine wave.
        self.assertLess(max_diff, 2000)

    def test_silence_round_trips_without_nan_or_crash(self):
        # Regression case: correlate_coefs() divides by recordCount in the
        # reference, which is 0 for fully silent input - see the comment in
        # correlate_coefs() about avoiding NaN coefficients here.
        pcm = [0] * 100
        info = dsp_adpcm.AdpcmInfo()
        encoded = dsp_adpcm.encode(pcm, info)
        decoded = dsp_adpcm.decode(encoded, info, len(pcm))
        self.assertEqual(decoded, [0] * 100)


class StmTests(unittest.TestCase):
    def test_round_trip_with_loop_point(self):
        left = _sine_pcm(2800, freq=440.0)
        right = _sine_pcm(2800, freq=550.0)
        audio = stm.StmAudio(sample_rate=32000, channels=[left, right], loop_start=1400)

        data = stm.write_stm(audio)
        reloaded = stm.read_stm(io.BytesIO(data))

        self.assertEqual(reloaded.sample_rate, 32000)
        self.assertEqual(len(reloaded.channels), 2)
        self.assertEqual(len(reloaded.channels[0]), 2800)
        self.assertEqual(reloaded.loop_start, 1400)

        max_diff = max(abs(a - b) for a, b in zip(left, reloaded.channels[0]))
        self.assertLess(max_diff, 2000)

    def test_wav_round_trip(self):
        with tempfile.TemporaryDirectory() as tmp:
            wav_path = Path(tmp) / "test.wav"
            pcm = _sine_pcm(1600)
            audio = stm.StmAudio(sample_rate=32000, channels=[pcm], loop_start=None)
            stm.stm_to_wav_path(audio, wav_path)

            reloaded = stm.wav_path_to_stm_audio(wav_path)
            self.assertEqual(reloaded.sample_rate, 32000)
            self.assertEqual(reloaded.channels[0], pcm)  # WAV round trip is lossless (plain PCM)


class ThpTests(unittest.TestCase):
    def test_encode_decode_round_trip_with_audio(self):
        from PIL import Image

        width, height = 32, 16  # multiples of 16, tiny to keep the test fast
        num_frames = 5
        fps = 30.0
        frames = [Image.new("RGB", (width, height), (i * 40 % 256, 80, 200)) for i in range(num_frames)]

        sample_rate = 32000
        num_samples = round(num_frames / fps * sample_rate)
        left = _sine_pcm(num_samples, freq=440.0, sample_rate=sample_rate)
        right = _sine_pcm(num_samples, freq=550.0, sample_rate=sample_rate)

        data = thp.encode_thp(frames, [left, right], sample_rate, fps)

        stream = io.BytesIO(data)
        info = thp.read_info(stream)
        self.assertEqual((info.width, info.height), (width, height))
        self.assertEqual(info.num_frames, num_frames)
        self.assertTrue(info.has_audio)
        self.assertEqual(info.audio_channels, 2)

        offsets = thp.iter_frame_offsets(stream, info)
        self.assertEqual(len(offsets), num_frames)
        # last frame's offset (found by walking the neighbor-size chain) must land
        # exactly on the header's own last_frame_offset - the same cross-check
        # that caught the real "next_total_size describes the *next* frame, not
        # its own" bug while first writing the reader.
        (last_frame_offset,) = struct.unpack(">I", data[44:48])
        self.assertEqual(offsets[-1], last_frame_offset)

        decoded_audio = [[], []]
        for i, offset in enumerate(offsets):
            image, audio = thp.read_frame(stream, offset, info)
            self.assertEqual(image.size, (width, height))
            decoded_audio[0].extend(audio[0])
            decoded_audio[1].extend(audio[1])

        self.assertEqual(len(decoded_audio[0]), num_samples)
        max_diff = max(abs(a - b) for a, b in zip(left, decoded_audio[0]))
        self.assertLess(max_diff, 2000)

    def test_encode_rejects_non_multiple_of_16_dimensions(self):
        from PIL import Image

        with self.assertRaises(thp.ThpError):
            thp.encode_thp([Image.new("RGB", (30, 16))], None, 32000, 30.0)


def _build_synthetic_fe8data() -> bytes:
    """A minimal but structurally faithful FE8Data.bin: real fixed table
    offsets/record sizes (see fe8data.py's module constants - not
    parameterized, since they're a fact about the real file, not
    configurable data), with only record 0 of each table populated with
    real-looking pointers; every other slot is left null so the empirical
    class/item table-length scan stops after 1 record."""
    label_pool_start = fe8data.SKILL_TABLE_OFFSET + fe8data.SKILL_RECORD_SIZE * 4
    out = bytearray(label_pool_start + 320)

    labels = {}
    pos = label_pool_start
    for label in [
        "PID_TEST",
        "FID_TEST",
        "JID_TESTCLASS",
        "JID_TESTCLASS2",
        "SID_TESTSKILL",
        "SID_TESTSKILL2",
        "SID_CHANTHP",
        "SID_CHANTSTR",
        "AID_TESTMODEL",
        "IID_TESTITEM",
        "MSID_TESTSKILL",
        "Mess_Help_skill_Test",
        "Mess_Help2_skill_Test",
        "D--------",
        "MIID_TESTITEM",
        "sword",
        "flame",
        "E",
        "twice",
        "fly",
        "EID_FIRE",
    ]:
        encoded = label.encode("ascii") + b"\x00"
        out[pos : pos + len(encoded)] = encoded
        labels[label] = pos - fe8data.HEADER_SIZE
        pos += len(encoded)

    # a 2-word restriction list, reusing JID_TESTCLASS/JID_TESTCLASS2's own
    # label offsets as its entries (no need for separate label strings)
    restriction_list_pos = pos
    struct.pack_into(">I", out, restriction_list_pos, labels["JID_TESTCLASS"])
    struct.pack_into(">I", out, restriction_list_pos + 4, labels["JID_TESTCLASS2"])
    restriction_start = restriction_list_pos - fe8data.HEADER_SIZE
    pos += 8
    # skill 0's one-entry scroll list
    struct.pack_into(">I", out, pos, labels["IID_TESTITEM"])
    scroll_list = pos - fe8data.HEADER_SIZE
    pos += 4

    # character record 0
    off = fe8data.CHARACTER_TABLE_OFFSET
    struct.pack_into(">I", out, off + 0x00, labels["PID_TEST"])
    struct.pack_into(">I", out, off + 0x0C, labels["FID_TEST"])
    struct.pack_into(">I", out, off + 0x10, labels["JID_TESTCLASS"])
    struct.pack_into(">I", out, off + 0x18, labels["D--------"])  # personal weapon ranks
    struct.pack_into(">I", out, off + 0x1C, labels["SID_TESTSKILL"])
    struct.pack_into(">I", out, off + 0x20, 0)
    struct.pack_into(">I", out, off + 0x24, 0)
    struct.pack_into(">H", out, off + 0x32, 45)  # biorhythm pattern
    out[off + 0x35] = 30  # biorhythm phase
    struct.pack_into(">I", out, off + 0x28, labels["AID_TESTMODEL"])
    struct.pack_into(">I", out, off + 0x2C, 0)
    out[off + 0x36] = 7  # level
    out[off + 0x37] = 3  # build
    out[off + 0x38] = 9  # weight
    out[off + 0x39 : off + 0x41] = bytes([20, 5, 0, 6, 7, 4, 3, 2])  # stat bonus
    out[off + 0x41 : off + 0x49] = bytes([60, 40, 10, 50, 45, 30, 25, 20])  # growth
    out[off + 0x49 : off + 0x51] = bytes([10, 15, 0, 5, 20, 0, 0, 0])  # fixed_growth_start

    # class record 0
    off = fe8data.CLASS_TABLE_OFFSET
    struct.pack_into(">I", out, off + 0x00, labels["JID_TESTCLASS"])
    struct.pack_into(">I", out, off + 0x04, 0)
    struct.pack_into(">I", out, off + 0x08, 0)
    struct.pack_into(">I", out, off + 0x0C, labels["JID_TESTCLASS2"])
    struct.pack_into(">I", out, off + 0x14, labels["D--------"])
    struct.pack_into(">I", out, off + 0x18, labels["SID_TESTSKILL"])
    struct.pack_into(">I", out, off + 0x1C, 0)
    struct.pack_into(">I", out, off + 0x20, 0)
    struct.pack_into(">I", out, off + 0x24, 0)
    struct.pack_into(">I", out, off + 0x28, 0)
    out[off + fe8data.CLASS_MOVE_OFFSET] = 6
    out[off + fe8data.CLASS_CAPS_OFFSET : off + fe8data.CLASS_CAPS_OFFSET + 8] = bytes([40, 20, 15, 20, 20, 40, 20, 20])
    out[off + fe8data.CLASS_BASE_STAT_OFFSET : off + fe8data.CLASS_BASE_STAT_OFFSET + 8] = bytes(
        [60, 20, 10, 30, 30, 20, 15, 15]
    )

    # item record 0
    off = fe8data.ITEM_TABLE_OFFSET
    struct.pack_into(">I", out, off + 0x00, labels["IID_TESTITEM"])
    struct.pack_into(">I", out, off + 0x04, labels["MIID_TESTITEM"])
    struct.pack_into(">I", out, off + 0x0C, labels["sword"])  # weapon type
    struct.pack_into(">I", out, off + 0x10, labels["flame"])  # attack type
    struct.pack_into(">I", out, off + 0x14, labels["E"])  # rank
    struct.pack_into(">I", out, off + 0x20, labels["twice"])  # property slot 2
    struct.pack_into(">I", out, off + 0x30, labels["fly"])  # effective against
    struct.pack_into(">I", out, off + 0x38, labels["EID_FIRE"])  # effect
    struct.pack_into(">H", out, off + 0x40, 12)  # cost per use
    out[off + 0x42] = 30  # uses
    out[off + 0x43] = 8  # might
    out[off + 0x44] = 85  # hit
    out[off + 0x45] = 6  # weight
    out[off + 0x46] = 5  # crit
    out[off + 0x47 : off + 0x49] = bytes([1, 2])  # range
    out[off + 0x49] = 2  # icon
    out[off + 0x4A] = 1  # weapon EXP
    out[off + 0x4B] = 7  # HP bonus
    out[off + 0x55 : off + 0x57] = bytes([0xFB, 5])  # growth modifiers -5 / +5
    out[off + 0x5D] = 3  # trail colour

    # skill records: the count word just before the table, then record 0
    # with a scroll, a 2-label restriction list and params
    struct.pack_into(">I", out, fe8data.SKILL_TABLE_OFFSET - 4, 4)
    off = fe8data.SKILL_TABLE_OFFSET
    struct.pack_into(">I", out, off + 0x00, labels["SID_TESTSKILL"])
    struct.pack_into(">I", out, off + 0x04, 0)  # no Japanese name in this synthetic record
    struct.pack_into(">I", out, off + 0x08, labels["MSID_TESTSKILL"])
    struct.pack_into(">I", out, off + 0x0C, labels["Mess_Help_skill_Test"])
    struct.pack_into(">I", out, off + 0x10, labels["Mess_Help2_skill_Test"])
    out[off + 0x19] = 5  # params[0]
    out[off + 0x1A] = 10  # params[1]
    out[off + 0x1B] = 1  # params[2]
    out[off + 0x1C] = 2  # restriction list length
    struct.pack_into(">I", out, off + 0x20, scroll_list)
    struct.pack_into(">I", out, off + 0x24, restriction_start)

    # skill record 1: a list pointer with a zero length reads as no list
    off += fe8data.SKILL_RECORD_SIZE
    struct.pack_into(">I", out, off + 0x00, labels["SID_TESTSKILL2"])
    struct.pack_into(">I", out, off + 0x24, restriction_start)

    # skill records 2-3: SID_CHANTHP/SID_CHANTSTR, sequential and with
    # neither a restriction list nor params - same shape as the real file's
    # Chant variants, for chant_stat_name()
    off += fe8data.SKILL_RECORD_SIZE
    struct.pack_into(">I", out, off + 0x00, labels["SID_CHANTHP"])
    off += fe8data.SKILL_RECORD_SIZE
    struct.pack_into(">I", out, off + 0x00, labels["SID_CHANTSTR"])

    return bytes(out)


class Fe8DataTests(unittest.TestCase):
    def test_read_character_class_item_records(self):
        data = _build_synthetic_fe8data()
        fe8 = fe8data.read_fe8data(data)

        char = fe8.characters[0]
        self.assertEqual(char.pid, "PID_TEST")
        self.assertEqual(char.fid, "FID_TEST")
        self.assertEqual(char.jid, "JID_TESTCLASS")
        self.assertEqual(char.sids, ["SID_TESTSKILL", None, None])
        self.assertEqual(char.weapon_ranks, "D--------")
        self.assertEqual((char.biorhythm_pattern, char.biorhythm_phase), (45, 30))
        self.assertEqual(char.aid_unpromoted, "AID_TESTMODEL")
        self.assertIsNone(char.aid_promoted)
        self.assertEqual(char.level, 7)
        self.assertEqual(char.build, 3)
        self.assertEqual(char.weight, 9)
        self.assertEqual(char.stat_bonus, [20, 5, 0, 6, 7, 4, 3, 2])
        self.assertEqual(char.growth, [60, 40, 10, 50, 45, 30, 25, 20])
        self.assertEqual(char.fixed_growth_start, [10, 15, 0, 5, 20, 0, 0, 0])

        self.assertEqual(len(fe8.classes), 1)
        self.assertEqual(fe8.classes[0].jid, "JID_TESTCLASS")
        self.assertEqual(fe8.classes[0].promotes_to, "JID_TESTCLASS2")
        self.assertEqual(fe8.classes[0].movement, 6)
        self.assertEqual(fe8.classes[0].stat_caps, [40, 20, 15, 20, 20, 40, 20, 20])
        self.assertEqual(fe8.classes[0].base_stats, [60, 20, 10, 30, 30, 20, 15, 15])
        self.assertEqual(fe8.classes[0].weapon_ranks, "D--------")
        self.assertEqual(fe8data.class_weapon_rank_map(fe8.classes[0]), {"Sword": "D"})
        self.assertEqual(fe8.classes[0].skills, ["SID_TESTSKILL", None, None, None, None])

        self.assertEqual(len(fe8.items), 1)
        item = fe8.items[0]
        self.assertEqual(item.iid, "IID_TESTITEM")
        self.assertEqual(item.uses, 30)
        self.assertEqual(item.might, 8)
        self.assertEqual(item.hit, 85)
        self.assertEqual(item.weight, 6)
        self.assertEqual(item.miid, "MIID_TESTITEM")
        self.assertEqual((item.weapon_type, item.attack_type, item.rank), ("sword", "flame", "E"))
        self.assertEqual(item.properties, [None, None, "twice", None, None, None])
        self.assertEqual(item.categories, ["fly", None])
        self.assertEqual((item.effect, item.weapon_effect), ("EID_FIRE", None))
        self.assertEqual((item.cost, item.crit, item.min_range, item.max_range), (12, 5, 1, 2))
        self.assertEqual((item.icon, item.weapon_exp, item.trail_color), (2, 1, 3))
        self.assertEqual(item.stat_bonus, [7] + [0] * 9)
        self.assertEqual(item.growth_bonus, [-5, 5] + [0] * 6)

        self.assertEqual(len(fe8.skills), 4)
        skill = fe8.skills[0]
        self.assertEqual(skill.sid, "SID_TESTSKILL")
        self.assertEqual(skill.msid, "MSID_TESTSKILL")
        self.assertIsNone(skill.japanese_name)
        self.assertEqual(skill.help_key, "Mess_Help_skill_Test")
        self.assertEqual(skill.help2_key, "Mess_Help2_skill_Test")
        self.assertEqual(skill.restricted_to, ["JID_TESTCLASS", "JID_TESTCLASS2"])
        self.assertEqual(skill.params, (5, 10, 1))
        self.assertEqual(skill.skill_items, ["IID_TESTITEM"])

        # record 1: a restriction pointer with a zero length is no list
        self.assertEqual(fe8.skills[1].sid, "SID_TESTSKILL2")
        self.assertEqual(fe8.skills[1].restricted_to, [])

    def test_chant_stat_name_uses_table_position_not_a_stored_field(self):
        data = _build_synthetic_fe8data()
        fe8 = fe8data.read_fe8data(data)

        chanthp = next(s for s in fe8.skills if s.sid == "SID_CHANTHP")
        chantstr = next(s for s in fe8.skills if s.sid == "SID_CHANTSTR")
        self.assertEqual(fe8data.chant_stat_name(fe8.skills, chanthp), "HP")
        self.assertEqual(fe8data.chant_stat_name(fe8.skills, chantstr), "Str")

        # a skill that isn't one of the 8 SID_CHANT<STAT> variants (including
        # plain SID_CHANT itself, which has no single stat) returns None
        other_skill = fe8.skills[0]  # SID_TESTSKILL
        self.assertIsNone(fe8data.chant_stat_name(fe8.skills, other_skill))

    def test_read_skill_descriptions_resolves_help_keys(self):
        # A minimal system.cmp stand-in: LZ10-compressed pack archive with a
        # mess/common.m entry in message.py's own format, holding the two
        # keys a skill record's help_key/help2_key point at.
        common_m = message.write_messages(
            [
                message.Message(speaker="Mess_Help_skill_Test", text="Short description."),
                message.Message(speaker="Mess_Help2_skill_Test", text="Long description."),
                message.Message(speaker="Ike", text="Not a help entry."),
            ]
        )
        archive = pak.pack_pak([("mess/common.m", common_m)])
        compressed = lz10.compress(archive)

        with tempfile.TemporaryDirectory() as tmp:
            system_cmp = Path(tmp) / "system.cmp"
            system_cmp.write_bytes(compressed)
            descriptions = fe8data.read_skill_descriptions(system_cmp)

        self.assertEqual(descriptions["Mess_Help_skill_Test"], "Short description.")
        self.assertEqual(descriptions["Mess_Help2_skill_Test"], "Long description.")
        self.assertNotIn("Ike", descriptions)

    def test_patch_character_field_round_trips(self):
        data = _build_synthetic_fe8data()
        patched = fe8data.patch_character_field(data, 0, "level", 99)
        patched = fe8data.patch_character_field(patched, 0, "stat_bonus3", -1)  # signed, like retail Rhys's Def
        patched = fe8data.patch_character_field(patched, 0, "jid", "JID_TESTCLASS2")
        patched = fe8data.patch_character_field(patched, 0, "fixed_growth_start2", 35)

        fe8 = fe8data.read_fe8data(patched)
        self.assertEqual(fe8.characters[0].level, 99)
        self.assertEqual(fe8.characters[0].stat_bonus[3], -1)
        with self.assertRaises(ValueError):
            fe8data.patch_character_field(patched, 0, "stat_bonus3", 128)
        self.assertEqual(fe8.characters[0].jid, "JID_TESTCLASS2")
        self.assertEqual(fe8.characters[0].fixed_growth_start[2], 35)
        # untouched fixed_growth_start entries and other fields survive
        self.assertEqual(fe8.characters[0].fixed_growth_start[0], 10)
        self.assertEqual(fe8.characters[0].pid, "PID_TEST")

    def test_patch_character_field_rejects_unknown_label(self):
        data = _build_synthetic_fe8data()
        with self.assertRaises(ValueError):
            fe8data.patch_character_field(data, 0, "jid", "JID_NOT_IN_THIS_FILE")

    def test_patch_item_field_round_trips(self):
        data = _build_synthetic_fe8data()
        patched = fe8data.patch_item_field(data, 0, "might", 40)
        fe8 = fe8data.read_fe8data(patched)
        self.assertEqual(fe8.items[0].might, 40)
        self.assertEqual(fe8.items[0].uses, 30)  # untouched

    def test_patch_item_field_covers_every_field(self):
        data = bytearray(_build_synthetic_fe8data())
        # a real container header (sizes, empty pointer list) so new strings are appended after the data
        struct.pack_into(">III", data, 0, len(data), len(data) - fe8data.HEADER_SIZE, 0)
        data = bytes(data)
        patch = fe8data.patch_item_field
        patched = patch(data, 0, "stat_bonus8", -2)
        patched = patch(patched, 0, "growth_bonus7", 30)
        patched = patch(patched, 0, "cost", 1000)
        patched = patch(patched, 0, "trail_color", 8)
        patched = patch(patched, 0, "rank", "S")
        patched = patch(patched, 0, "weapon_type", "axe")  # not in the pool yet: added
        patched = patch(patched, 0, "properties", ["twice", "revatr"])
        patched = patch(patched, 0, "categories", [])
        patched = patch(patched, 0, "effect", None)
        patched = patch(patched, 0, "iid", "IID_RENAMED")
        item = fe8data.read_fe8data(patched).items[0]
        self.assertEqual(item.stat_bonus[8], -2)
        self.assertEqual(item.growth_bonus[7], 30)
        self.assertEqual((item.cost, item.trail_color, item.rank, item.weapon_type), (1000, 8, "S", "axe"))
        self.assertEqual(item.properties, ["revatr", None, "twice", None, None, None])  # twice kept its slot
        self.assertEqual(item.categories, [None, None])
        self.assertIsNone(item.effect)
        self.assertEqual(item.iid, "IID_RENAMED")
        self.assertEqual(item.might, 8)  # untouched
        for field, value in (("stat_bonus0", 128), ("trail_color", 9), ("cost", 70000), ("rank", "Z"),
                             ("weapon_type", None), ("categories", ["fly", "armor", "beast"]),
                             ("properties", ["poison"]), ("miid", "MIID_NOT_IN_FILE")):
            if field == "properties":
                value = list(fe8data.ITEM_PROPERTY_TOKENS)[:7]
            with self.assertRaises(ValueError, msg=field):
                patch(data, 0, field, value)

    def test_item_category(self):
        item = fe8data.read_fe8data(_build_synthetic_fe8data()).items[0]
        self.assertEqual(fe8data.item_category(item), "Sword")
        item.weapon_type = "rod"
        self.assertEqual(fe8data.item_category(item), "Light")  # a rod with might is a tome
        item.might = 0
        self.assertEqual(fe8data.item_category(item), "Staff")

    def test_class_category(self):
        def cls(jid, link, hp_cap, movement=5, categories=(), innate=None):
            return fe8data.ClassEntry(0, 0, jid, None, None, link, None, movement, [hp_cap] + [20] * 7, [0] * 8,
                                      [0] * 8, 0, None, [None] * 5, b"", innate_weapon=innate,
                                      categories=list(categories))
        classes = [cls("JID_RANGER", "JID_HERO", 40), cls("JID_HERO", "JID_RANGER", 60, 6),
                   cls("JID_LION", "JID_LION_F", 60, categories=("alize", "beast")),
                   cls("JID_LION_F", "JID_LION", 60, 6), cls("JID_CAT", None, 60, innate="IID_CLAW"),
                   cls("JID_LORD", None, 60), cls("JID_SOLDIER", None, 40)]
        self.assertEqual([fe8data.class_category(c, classes) for c in classes],
                         ["Unpromoted", "Promoted", "Laguz", "Laguz", "Laguz", "Promoted", "Unpromoted"])

    def test_item_short_tokens_are_not_found_inside_tables(self):
        # "E" as plain bytes inside the character table must not be taken for the rank string
        data = bytearray(_build_synthetic_fe8data())
        data[fe8data.CHARACTER_TABLE_OFFSET + 0x60 : fe8data.CHARACTER_TABLE_OFFSET + 0x63] = b"\x00D\x00"
        item_off = fe8data.ITEM_TABLE_OFFSET
        pointer_fields = [item_off + o - fe8data.HEADER_SIZE for o in (0x00, 0x04, 0x0C, 0x10, 0x14)]
        pointer_list = struct.pack(f">{len(pointer_fields)}I", *pointer_fields)
        data = bytes(data) + pointer_list
        struct_data = bytearray(data)
        data_size = len(data) - len(pointer_list) - fe8data.HEADER_SIZE
        struct.pack_into(">III", struct_data, 0, len(struct_data), data_size, len(pointer_fields))
        patched = fe8data.patch_item_field(bytes(struct_data), 0, "rank", "D")
        self.assertEqual(fe8data.read_fe8data(patched).items[0].rank, "D")
        (ptr,) = struct.unpack_from(">I", patched, item_off + 0x14)
        self.assertGreater(ptr + fe8data.HEADER_SIZE, fe8data.SKILL_TABLE_OFFSET)

    def test_patch_class_field_round_trips(self):
        data = _build_synthetic_fe8data()
        patched = fe8data.patch_class_field(data, 0, "promotes_to", None)
        patched = fe8data.patch_class_field(patched, 0, "movement", 9)
        patched = fe8data.patch_class_field(patched, 0, "cap0", 60)
        patched = fe8data.patch_class_field(patched, 0, "base_stat2", 50)
        fe8 = fe8data.read_fe8data(patched)
        self.assertIsNone(fe8.classes[0].promotes_to)
        self.assertEqual(fe8.classes[0].movement, 9)
        self.assertEqual(fe8.classes[0].stat_caps[0], 60)
        self.assertEqual(fe8.classes[0].base_stats[2], 50)
        # untouched stat_caps/base_stats entries survive
        self.assertEqual(fe8.classes[0].stat_caps[1], 20)
        self.assertEqual(fe8.classes[0].base_stats[0], 60)

    def test_patch_class_weapon_ranks_adds_a_new_string(self):
        data = bytearray(_build_synthetic_fe8data())
        # a real container header (sizes, empty pointer list) so the new string is appended after the data
        struct.pack_into(">III", data, 0, len(data), len(data) - fe8data.HEADER_SIZE, 0)
        data = bytes(data)
        patched = fe8data.patch_class_field(data, 0, "weapon_ranks", "c-e------")
        self.assertEqual(fe8data.read_fe8data(patched).classes[0].weapon_ranks, "C-E------")
        with self.assertRaises(ValueError):
            fe8data.patch_class_field(data, 0, "weapon_ranks", "CX")

    def test_patch_record_bytes_refuses_pointer_words(self):
        data = _build_synthetic_fe8data()
        record = bytearray(fe8data.record_bytes(data, "item", 0))
        record[0x50] ^= 0x01
        patched = fe8data.patch_record_bytes(data, "item", 0, bytes(record))
        self.assertEqual(fe8data.record_bytes(patched, "item", 0)[0x50], record[0x50])
        record[0x03] ^= 0x04  # inside the IID pointer
        with self.assertRaises(ValueError):
            fe8data.patch_record_bytes(data, "item", 0, bytes(record))


def _build_synthetic_event_script() -> bytes:
    """A minimal but structurally faithful .cmb: real header/label-pool/
    function-table layout (see event_script.py - reverse-engineered from
    real chapter files, not documented anywhere), holding one function with
    four instructions: push8(7), externCall(<label>, 1), pop, return."""
    HEADER_SIZE = 0x2C
    label_pool = b"TestFunc\x00OtherFunc\x00"  # offsets: TestFunc=0, OtherFunc=9
    label_map_start = HEADER_SIZE
    function_table_start = label_map_start + len(label_pool)

    first_function_start = function_table_start + 8  # table head (4 bytes) + 4 bytes padding
    function_record_size = 20  # "<IIIbbbbhh"
    params = struct.pack("<HH", 5, 10)  # 2 trigger params, right after the fixed header
    address_code = first_function_start + function_record_size + len(params)

    instructions = bytes([25, 7])  # push8(7)
    instructions += bytes([56]) + struct.pack(">h", 0) + bytes([1])  # externCall(TestFunc@0, 1)
    instructions += bytes([32])  # pop
    instructions += bytes([57])  # return

    out = bytearray(address_code + len(instructions))
    struct.pack_into("<I", out, 0x24, label_map_start)
    struct.pack_into("<I", out, 0x28, function_table_start)
    out[label_map_start : label_map_start + len(label_pool)] = label_pool
    struct.pack_into("<I", out, function_table_start, first_function_start)
    struct.pack_into(
        "<IIIbbbbhh", out, first_function_start,
        0, address_code, 0, 0, 0, 2, 0, 0, 0,  # id_string_ptr, address_code, address_parent, type, args, params, pad, index, vars
    )
    out[first_function_start + function_record_size : first_function_start + function_record_size + len(params)] = params
    out[address_code : address_code + len(instructions)] = instructions
    return bytes(out)


class EventScriptTests(unittest.TestCase):
    def test_read_function_and_instructions(self):
        data = _build_synthetic_event_script()
        script = event_script.read_event_script_bytes(data)

        self.assertEqual(len(script.functions), 1)
        # trailing NUL after the last label produces one extra empty entry -
        # a real quirk of the format (same split-on-NUL logic runs against
        # real files), not a synthetic-data artifact to paper over.
        self.assertEqual(script.labels, {0: "TestFunc", 9: "OtherFunc", 19: ""})

        fn = script.functions[0]
        self.assertEqual(
            fn.instructions,
            [[0, "push8", 7], [2, "externCall", "TestFunc", 1], [6, "pop"], [7, "return"]],
        )

    def test_patch_numeric_operand_round_trips(self):
        data = _build_synthetic_event_script()
        script = event_script.read_event_script_bytes(data)
        fn = script.functions[0]

        patched = event_script.patch_instruction_operand(data, script.labels, fn, fn.instructions[0], 0, 42)
        reloaded = event_script.read_event_script_bytes(patched)
        self.assertEqual(reloaded.functions[0].instructions[0], [0, "push8", 42])
        # every other instruction untouched
        self.assertEqual(reloaded.functions[0].instructions[1:], fn.instructions[1:])

    def test_patch_label_operand_round_trips(self):
        data = _build_synthetic_event_script()
        script = event_script.read_event_script_bytes(data)
        fn = script.functions[0]

        patched = event_script.patch_instruction_operand(
            data, script.labels, fn, fn.instructions[1], 0, "OtherFunc"
        )
        reloaded = event_script.read_event_script_bytes(patched)
        self.assertEqual(reloaded.functions[0].instructions[1], [2, "externCall", "OtherFunc", 1])

    def test_patch_second_operand_of_externcall(self):
        data = _build_synthetic_event_script()
        script = event_script.read_event_script_bytes(data)
        fn = script.functions[0]

        patched = event_script.patch_instruction_operand(data, script.labels, fn, fn.instructions[1], 1, 3)
        reloaded = event_script.read_event_script_bytes(patched)
        self.assertEqual(reloaded.functions[0].instructions[1], [2, "externCall", "TestFunc", 3])

    def test_patch_rejects_unknown_label(self):
        data = _build_synthetic_event_script()
        script = event_script.read_event_script_bytes(data)
        fn = script.functions[0]

        with self.assertRaises(event_script.ScriptError):
            event_script.patch_instruction_operand(data, script.labels, fn, fn.instructions[1], 0, "NoSuchLabel")

    def test_patch_rejects_out_of_range_byte(self):
        data = _build_synthetic_event_script()
        script = event_script.read_event_script_bytes(data)
        fn = script.functions[0]

        with self.assertRaises(event_script.ScriptError):
            event_script.patch_instruction_operand(data, script.labels, fn, fn.instructions[0], 0, 999)

    def test_describe_function_trigger_uses_special_id_string(self):
        fn = event_script.ScriptFunction(
            index=1, id_string=b"Startup", address_parent=0, type=0, num_args=0, num_vars=0, params=[],
            instructions=[],
        )
        description = event_script.describe_function_trigger(fn)
        self.assertTrue(description.startswith("Called automatically at the beginning of the chapter"))

    def test_describe_function_trigger_reports_params_by_type(self):
        fn = event_script.ScriptFunction(
            index=6, id_string=b"", address_parent=0, type=6, num_args=0, num_vars=3, params=[0, 0, 1],
            instructions=[],
        )
        description = event_script.describe_function_trigger(fn)
        self.assertIn("start of a phase", description)
        self.assertIn("Phase (0=player, 1=enemy)=1", description)

    def test_describe_function_trigger_resolves_label_params_when_given_labels(self):
        # type 9 (fight starts): params[0]/[1] are Character ID 1/2, confirmed
        # to be string-pool PID_ label references - see FUNCTION_TRIGGERS'
        # module-level comment for how this was confirmed against real scripts
        fn = event_script.ScriptFunction(
            index=0, id_string=b"", address_parent=0, type=9, num_args=0, num_vars=0,
            params=[100, 200, 1, 300], instructions=[],
        )
        labels = {100: "PID_IKE", 200: "PID_TIAMAT", 300: "IkeVsTiamat"}

        without_labels = event_script.describe_function_trigger(fn)
        self.assertIn("Character ID 1=100", without_labels)

        with_labels = event_script.describe_function_trigger(fn, labels)
        self.assertIn("Character ID 1=PID_IKE", with_labels)
        self.assertIn("Character ID 2=PID_TIAMAT", with_labels)
        # the 0/1 flag (index 2) is NOT a label param - stays a raw number
        self.assertIn("flag, meaning unclear (almost never a label - stays a raw number)=1", with_labels)
        self.assertIn("Event name (debug label for this battle trigger, not gameplay-visible)=IkeVsTiamat", with_labels)

    def test_describe_function_trigger_falls_back_for_undocumented_type(self):
        fn = event_script.ScriptFunction(
            index=0, id_string=b"", address_parent=0, type=99, num_args=0, num_vars=0, params=[], instructions=[],
        )
        self.assertEqual(event_script.describe_function_trigger(fn), "type 99 (undocumented)")

    def test_patch_function_param_round_trips(self):
        data = _build_synthetic_event_script()
        script = event_script.read_event_script_bytes(data)
        fn = script.functions[0]
        self.assertEqual(fn.params, [5, 10])

        patched = event_script.patch_function_param(data, fn, 1, 42)
        reloaded = event_script.read_event_script_bytes(patched)
        self.assertEqual(reloaded.functions[0].params, [5, 42])
        # instructions and everything else untouched
        self.assertEqual(reloaded.functions[0].instructions, fn.instructions)

    def test_patch_function_param_rejects_out_of_range_index(self):
        data = _build_synthetic_event_script()
        script = event_script.read_event_script_bytes(data)
        fn = script.functions[0]
        with self.assertRaises(event_script.ScriptError):
            event_script.patch_function_param(data, fn, 5, 0)

    def test_patch_function_param_rejects_value_too_large(self):
        data = _build_synthetic_event_script()
        script = event_script.read_event_script_bytes(data)
        fn = script.functions[0]
        with self.assertRaises(event_script.ScriptError):
            event_script.patch_function_param(data, fn, 0, 100000)


def _build_synthetic_event_script_two_functions() -> bytes:
    """A two-function .cmb exercising every absolute-address field
    insert_label() has to shift: function B has a real id_string_ptr (an
    inline ID string) and an address_parent word deliberately set to
    function A's address, and function B's own bytecode references function
    A's label - letting a test confirm a pool-relative operand stays correct
    across the insert, every real absolute pointer (id_string_ptr/
    address_code) shifts, and address_parent's raw bytes are deliberately
    left untouched (see ScriptFunction's own docstring for why treating it
    as a real address was a refuted guess)."""
    HEADER_SIZE = 0x2C
    label_pool = b"FuncA\x00FuncB\x00"  # offsets: FuncA=0, FuncB=6
    label_map_start = HEADER_SIZE
    function_table_start = label_map_start + len(label_pool)

    function_a_addr = function_table_start + 12  # 2 table entries (4 bytes each) + 4 bytes padding, same convention _build_synthetic_event_script() uses
    function_a_instructions = bytes([57])  # return
    function_a_size = 20 + len(function_a_instructions)  # header, no params, no id string

    function_b_addr = function_a_addr + function_a_size
    function_b_id_string = b"FuncB_ID\x00"
    function_b_id_ptr = function_b_addr + 20
    function_b_address_code = function_b_id_ptr + len(function_b_id_string)
    function_b_instructions = bytes([56]) + struct.pack(">h", 0) + bytes([0])  # externCall(FuncA@0, 0)
    function_b_instructions += bytes([57])  # return

    total_size = function_b_address_code + len(function_b_instructions)

    out = bytearray(total_size)
    struct.pack_into("<I", out, 0x24, label_map_start)
    struct.pack_into("<I", out, 0x28, function_table_start)
    out[label_map_start : label_map_start + len(label_pool)] = label_pool
    struct.pack_into("<I", out, function_table_start, function_a_addr)
    struct.pack_into("<I", out, function_table_start + 4, function_b_addr)

    struct.pack_into(
        "<IIIbbbbhh", out, function_a_addr,
        0, function_a_addr + 20, 0, 0, 0, 0, 0, 0, 0,  # id_string_ptr, address_code, address_parent, type, args, params, pad, index, vars
    )
    out[function_a_addr + 20 : function_a_addr + 20 + len(function_a_instructions)] = function_a_instructions

    struct.pack_into(
        "<IIIbbbbhh", out, function_b_addr,
        function_b_id_ptr, function_b_address_code, function_a_addr, 0, 0, 0, 0, 1, 0,
    )
    out[function_b_id_ptr : function_b_id_ptr + len(function_b_id_string)] = function_b_id_string
    out[function_b_address_code : function_b_address_code + len(function_b_instructions)] = function_b_instructions

    return bytes(out)


class EventScriptInsertLabelTests(unittest.TestCase):
    def test_insert_label_shifts_every_absolute_pointer_correctly(self):
        data = _build_synthetic_event_script_two_functions()
        script = event_script.read_event_script_bytes(data)
        fn_a, fn_b = script.functions
        self.assertEqual(fn_b.id_string, b"FuncB_ID")
        self.assertEqual(fn_b.address_parent, fn_a.address)  # true only because of how the fixture set it up initially
        self.assertEqual(fn_b.instructions[0], [0, "externCall", "FuncA", 0])

        new_data = event_script.insert_label(data, script, "Movie/s99.thp")
        reloaded = event_script.read_event_script_bytes(new_data)

        self.assertIn("Movie/s99.thp", reloaded.labels.values())
        new_a, new_b = reloaded.functions

        # every existing label still resolves - pool-relative offsets never moved
        self.assertEqual(new_b.instructions[0], [0, "externCall", "FuncA", 0])
        self.assertEqual(new_a.instructions, fn_a.instructions)

        # real absolute-address fields correctly shifted
        self.assertEqual(new_b.id_string, b"FuncB_ID")
        self.assertNotEqual(new_a.address, fn_a.address)  # actually moved, not a no-op

        # address_parent is deliberately NOT shifted - main.dol's own script loader
        # (FUN_800140b4) overwrites this word unconditionally at load time regardless
        # of the stored file value, so it isn't a real relocatable address (see
        # ScriptFunction's docstring) - its raw on-disk bytes should be untouched
        self.assertEqual(new_b.address_parent, fn_b.address_parent)
        self.assertNotEqual(new_b.address_parent, new_a.address)

    def test_insert_label_then_point_an_operand_at_it(self):
        data = _build_synthetic_event_script_two_functions()
        script = event_script.read_event_script_bytes(data)
        fn_b = script.functions[1]

        data = event_script.insert_label(data, script, "Movie/s99.thp")
        script = event_script.read_event_script_bytes(data)
        fn_b = next(f for f in script.functions if f.index == fn_b.index)

        offset = event_script.find_label_offset(script.labels, "Movie/s99.thp")
        self.assertIsNotNone(offset)

        patched = event_script.patch_instruction_operand(
            data, script.labels, fn_b, fn_b.instructions[0], 0, "Movie/s99.thp"
        )
        reloaded = event_script.read_event_script_bytes(patched)
        new_fn_b = next(f for f in reloaded.functions if f.index == fn_b.index)
        self.assertEqual(new_fn_b.instructions[0], [0, "externCall", "Movie/s99.thp", 0])

    def test_insert_label_rejects_nul_byte(self):
        data = _build_synthetic_event_script_two_functions()
        script = event_script.read_event_script_bytes(data)
        with self.assertRaises(event_script.ScriptError):
            event_script.insert_label(data, script, "bad\x00label")

    def test_insert_label_separates_from_a_pool_with_no_trailing_nul(self):
        # Regression test: a real chapter script's pool was found to NOT end
        # with a NUL byte before function_table_start - the last label is
        # implicitly terminated by simply reaching the function table. Naively
        # appending "label + NUL" there silently merged onto the tail of that
        # existing last label instead of creating a separate entry.
        HEADER_SIZE = 0x2C
        label_pool = b"FuncA\x00FuncB"  # deliberately no trailing NUL
        label_map_start = HEADER_SIZE
        function_table_start = label_map_start + len(label_pool)
        function_addr = function_table_start + 8  # 1 entry (4 bytes) + 4 bytes padding

        out = bytearray(function_addr + 21)  # header(20) + return(1)
        struct.pack_into("<I", out, 0x24, label_map_start)
        struct.pack_into("<I", out, 0x28, function_table_start)
        out[label_map_start : label_map_start + len(label_pool)] = label_pool
        struct.pack_into("<I", out, function_table_start, function_addr)
        struct.pack_into("<IIIbbbbhh", out, function_addr, 0, function_addr + 20, 0, 0, 0, 0, 0, 0, 0)
        out[function_addr + 20] = 57  # return
        data = bytes(out)

        script = event_script.read_event_script_bytes(data)
        self.assertEqual(script.labels, {0: "FuncA", 6: "FuncB"})

        new_data = event_script.insert_label(data, script, "Movie/s99.thp")
        reloaded = event_script.read_event_script_bytes(new_data)
        self.assertIn("FuncB", reloaded.labels.values())  # untouched, not merged with the new label
        self.assertIn("Movie/s99.thp", reloaded.labels.values())


def _synthetic_gs_file() -> gs_file.GsFile:
    """A two-list, bone-subset-carrying mesh exercising every block type."""
    dl = bytes([0x98, 0x00, 0x03]) + b"".join(struct.pack(">BHHH", 3 * i, i, 0, i) for i in range(3))
    dl += bytes(-len(dl) % 32)
    return gs_file.GsFile(
        root_name="unknown", date=0x20040723, model_id=0x25,
        bbox_min=(-1.0, 0.0, -1.0), bbox_max=(1.0, 2.0, 1.0),
        pos_frac=12, norm_frac=6, uv_frac=14,
        positions=[(0, 0, 0), (4096, 0, 0), (0, 8192, 0)],
        normals=[(0, 64, 0)],
        uvs=[(0, 0), (16384, 0), (0, 16384)],
        materials=[gs_file.GsMaterial("lambert1", (0, 0), 0, (204, 204, 204, 255), (0, 0, 0, 255), (0, 0, 0, 0),
                                      [gs_file.GsTexture((1, 0), 0, (0, 0, 0, 0, 0), 1.0, 1.0, 0)])],
        meshes=[gs_file.GsMesh("none", (0.0, 0.0, 0.0), (1.0, 2.0, 0.0), 1)],
        chunk_lists=(
            [gs_file.GsChunk(0, 0x3802, 0, 1, 0, 0x4601, dl, [1, 2, 3])],
            [gs_file.GsChunk(0, 0x3040, 0, 1, 0, 0x4600, dl[:32], None)],
            [],
        ),
    )


class GsFileTests(unittest.TestCase):
    def test_round_trip_is_byte_identical(self):
        data = gs_file.write_gs(_synthetic_gs_file())
        self.assertEqual(gs_file.write_gs(gs_file.read_gs(data)), data)

    def test_relocation_table_lists_every_nonzero_pointer(self):
        data = gs_file.write_gs(_synthetic_gs_file())
        size, reloc_offset, reloc_count = struct.unpack_from(">3I", data, 0)
        self.assertEqual(size, len(data))
        entries = struct.unpack_from(f">{reloc_count}I", data, 0x20 + reloc_offset)
        self.assertEqual(list(entries), sorted(entries))
        for entry in entries:
            (target,) = struct.unpack_from(">I", data, 0x20 + entry)
            self.assertTrue(0 < target < reloc_offset)

    def test_display_lists_are_32_byte_aligned_and_chunk_lists_linked(self):
        body = gs_file.write_gs(_synthetic_gs_file())[0x20:]
        list6, list7 = struct.unpack_from(">2I", body, 0x3C)
        for chunk_ptr in (list6, list7):
            (dl_ptr,) = struct.unpack_from(">I", body, chunk_ptr + 0x14)
            self.assertEqual((dl_ptr + 0x20) % 32, 0)
            self.assertEqual(body[dl_ptr], 0x98)
            (next_ptr,) = struct.unpack_from(">I", body, chunk_ptr + 4)
            self.assertEqual(next_ptr, 0)

    def test_semantic_reader_agrees_with_container(self):
        parsed = model.read_model_bytes(gs_file.write_gs(_synthetic_gs_file()))
        self.assertEqual(len(parsed.chunks), 2)
        self.assertEqual(parsed.chunks[0].bone_subset, [1, 2, 3])
        self.assertEqual(parsed.materials[0].name, "lambert1")


class SkeletonFileTests(unittest.TestCase):
    def test_round_trip_is_byte_identical(self):
        floats = tuple([1.0, 0.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 0.0, 1.0, 0.0] + [0.5] * 43)
        skel = skeleton.SkeletonFile(
            root_name="[unknown]",
            bones=[
                skeleton.Bone("root", -1, (-1, 1, 0x180), floats, (0, 1)),
                skeleton.Bone("hip1", 0, (-1, -1, 0x180), floats, (1, 1)),
            ],
        )
        data = skeleton.write_skeleton_file(skel)
        self.assertEqual(skeleton.write_skeleton_file(skeleton.read_skeleton_file(data)), data)
        self.assertEqual([b.name for b in skeleton.read_skeleton(io.BytesIO(data))], ["root", "hip1"])


def _synthetic_animation() -> animation.GaAnimation:
    curves = [
        animation.AnimCurve(1, 3, 7, 10, [animation.Keyframe(0, 0), animation.Keyframe(10, 256)]),
        animation.AnimCurve(4, 5, 7, 8, [animation.Keyframe(0, -5), animation.Keyframe(8, 5)]),
    ]
    groups = [animation.BoneGroup(1, animation.MASK_ROTATE, 0, 1), animation.BoneGroup(4, animation.MASK_ROTATE, 1, 1)]
    block = struct.pack(">HHIH", 1, 0, 0, 0) + struct.pack(">HHHH", 0, 2, 50, 1900)
    footer = animation.GaFooter(blocks=[block] + [None] * 8, order=[0])
    header = animation.GaHeader(words=(0, 0, 0, 5, 0, 1, 10, 0, 0, 0, 0, 0))
    return animation.GaAnimation(header=header, groups=groups, curves=curves, footer=footer)


class AnimationWriteTests(unittest.TestCase):
    def test_round_trip_is_byte_identical(self):
        data = animation.write_animation(_synthetic_animation())
        self.assertEqual(animation.write_animation(animation.read_animation_bytes(data)), data)

    def test_groups_start_at_0x30_and_assign_bones(self):
        anim = animation.read_animation_bytes(animation.write_animation(_synthetic_animation()))
        self.assertEqual(anim.header.group_table_addr, 0x30)
        self.assertEqual([c.bone_index for c in anim.curves], [1, 4])
        self.assertEqual(anim.events, [animation.EventKey(0, (50, 1900))])

    def test_event_block_writer_matches_the_stored_layout(self):
        events = [animation.EventKey(3, (1,)), animation.EventKey(9, (25, 1550))]
        block = animation.write_event_block(events)
        self.assertEqual(animation.read_event_block(block), events)
        self.assertEqual(len(block) % 4, 0)
        self.assertEqual(struct.unpack_from(">HHI2H", block, 0), (2, 0, 0, 12, 18))


class GltfExportTests(unittest.TestCase):
    def test_exported_glb_is_well_formed(self):
        gs = model.read_model_bytes(gs_file.write_gs(_synthetic_gs_file()))
        identity = (1.0, 0.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 0.0, 1.0, 0.0)
        bones = [
            _rig_bone(name, parent, pos)
            for name, parent, pos in [("root", -1, (0.0, 0.0, 0.0)), ("a", 0, (0.0, 1.0, 0.0)),
                                      ("b", 1, (0.0, 2.0, 0.0)), ("c", 2, (0.0, 3.0, 0.0))]
        ]
        anim = animation.read_animation_bytes(animation.write_animation(_synthetic_animation()))
        glb = gltf_export.export_glb([("body", gs)], bones, {0: Image.new("RGBA", (4, 4), (255, 0, 0, 255))}, [("atk", anim)])
        magic, version, total = struct.unpack_from("<4sII", glb, 0)
        self.assertEqual((magic, version, total), (b"glTF", 2, len(glb)))
        json_len, json_type = struct.unpack_from("<I4s", glb, 12)
        self.assertEqual(json_type, b"JSON")
        doc = json.loads(glb[20 : 20 + json_len])
        self.assertEqual(len(doc["skins"][0]["joints"]), 4)
        self.assertEqual(doc["animations"][0]["name"], "atk")
        self.assertEqual(len(doc["meshes"][0]["primitives"]), 1)
        self.assertEqual(doc["animations"][0]["extras"]["end_frame"], 10)


def _quad_glb(translation=(0.0, 0.0, 0.0), with_texture=True, alpha_mode=None, double_sided=False) -> bytes:
    """A one-node glTF: a 2x2 quad facing +Y (counter-clockwise from above),
    optionally textured with a 4x4 red PNG."""
    positions = [(-1.0, 0.0, -1.0), (1.0, 0.0, -1.0), (1.0, 0.0, 1.0), (-1.0, 0.0, 1.0)]
    uvs = [(0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0)]
    indices = [0, 2, 1, 0, 3, 2]
    binary = bytearray()
    views = []

    def view(data: bytes) -> int:
        views.append({"buffer": 0, "byteOffset": len(binary), "byteLength": len(data)})
        binary.extend(data + bytes(-len(data) % 4))
        return len(views) - 1

    pos_view = view(b"".join(struct.pack("<3f", *v) for v in positions))
    uv_view = view(b"".join(struct.pack("<2f", *v) for v in uvs))
    idx_view = view(b"".join(struct.pack("<H", i) for i in indices))
    doc = {
        "asset": {"version": "2.0"},
        "scene": 0,
        "scenes": [{"nodes": [0]}],
        "nodes": [{"name": "quad", "mesh": 0, "translation": list(translation)}],
        "meshes": [{"primitives": [{"attributes": {"POSITION": 0, "TEXCOORD_0": 1}, "indices": 2, "material": 0}]}],
        "materials": [{"name": "floor", "pbrMetallicRoughness": {"baseColorFactor": [1.0, 0.5, 0.25, 1.0]}}],
        "accessors": [
            {"bufferView": pos_view, "componentType": 5126, "count": 4, "type": "VEC3"},
            {"bufferView": uv_view, "componentType": 5126, "count": 4, "type": "VEC2"},
            {"bufferView": idx_view, "componentType": 5123, "count": 6, "type": "SCALAR"},
        ],
    }
    if with_texture:
        png = io.BytesIO()
        Image.new("RGBA", (4, 4), (255, 0, 0, 255)).save(png, format="PNG")
        doc["images"] = [{"bufferView": view(png.getvalue()), "mimeType": "image/png"}]
        doc["textures"] = [{"source": 0}]
        doc["materials"][0]["pbrMetallicRoughness"]["baseColorTexture"] = {"index": 0}
    if alpha_mode:
        doc["materials"][0]["alphaMode"] = alpha_mode
    if double_sided:
        doc["materials"][0]["doubleSided"] = True
    doc["bufferViews"] = views
    doc["buffers"] = [{"byteLength": len(binary)}]
    return gltf_export._pack_glb(doc, bytes(binary))


def _static_bone(name, parent, local_translation, scale=1.0):
    """A bone whose +0xBC matrix is scale + translation."""
    tx, ty, tz = local_translation
    local = (scale, 0.0, 0.0, tx, 0.0, scale, 0.0, ty, 0.0, 0.0, scale, tz)
    return skeleton.Bone(name, parent, (-1, -1, 0), (0.0,) * 43 + local, (0, 1))


class TplBuildTests(unittest.TestCase):
    def test_build_tpl_round_trips_lossless_formats(self):
        image = Image.new("RGBA", (8, 8))
        image.putdata([(x * 30, y * 30, 7, 255 if x < 4 else 128) for y in range(8) for x in range(8)])
        data = tpl.build_tpl([(image, tpl.FORMAT_RGBA8), (image.resize((16, 8)), tpl.FORMAT_CMPR)])
        infos = tpl.read_tpl_image_info(io.BytesIO(data))
        self.assertEqual([(i.width, i.height, i.format) for i in infos], [(8, 8, 6), (16, 8, 14)])
        self.assertTrue(all(i.data_addr % 32 == 0 for i in infos))
        self.assertEqual(list(tpl.read_tpl_images(io.BytesIO(data))[0].getdata()), list(image.getdata()))

    def test_cmpr_keeps_one_bit_alpha_and_cutouts_pick_cmpr(self):
        image = Image.new("RGBA", (8, 8))
        image.putdata([(200, 40, 40, 0 if (x + y) % 3 == 0 else 255) for y in range(8) for x in range(8)])
        self.assertEqual(gltf_import.texture_for_tpl(image)[1], tpl.FORMAT_CMPR)
        decoded = tpl.read_tpl_images(io.BytesIO(tpl.build_tpl([(image, tpl.FORMAT_CMPR)])))[0]
        self.assertEqual(list(decoded.getchannel("A").getdata()), list(image.getchannel("A").getdata()))
        for got, want in zip(decoded.getdata(), image.getdata()):
            if want[3]:
                self.assertLessEqual(max(abs(got[c] - want[c]) for c in range(3)), 8)
        image.putpixel((0, 0), (200, 40, 40, 128))
        self.assertEqual(gltf_import.texture_for_tpl(image)[1], tpl.FORMAT_RGB5A3)


class GltfImportTests(unittest.TestCase):
    def test_stripify_keeps_every_triangle_and_its_winding(self):
        grid = [(r * 4 + c, r * 4 + c + 1, (r + 1) * 4 + c) for r in range(3) for c in range(3)]
        grid += [(r * 4 + c + 1, (r + 1) * 4 + c + 1, (r + 1) * 4 + c) for r in range(3) for c in range(3)]
        strips = gltf_import.stripify(grid)

        def canonical(t):
            i = t.index(min(t))
            return t[i:] + t[:i]

        drawn = sorted(canonical(t) for s in strips for t in gltf_import.strip_triangles(s))
        self.assertEqual(drawn, sorted(canonical(t) for t in grid))
        self.assertLess(len(strips), len(grid))

    def test_static_import_builds_a_readable_gs_and_tpl(self):
        gs_bytes, tpl_bytes, warnings = gltf_import.import_static_model(_quad_glb(), name="quad")
        self.assertEqual(warnings, [])
        raw = gs_file.read_gs(gs_bytes)
        self.assertEqual(gs_file.write_gs(raw), gs_bytes)
        self.assertEqual(raw.materials[0].color0, (204, 102, 51, 255))  # base color / 1.25
        self.assertEqual(raw.materials[0].textures[0].tex_id, 0)
        self.assertEqual((raw.bbox_min, raw.bbox_max), ((-1.0, 0.0, -1.0), (1.0, 0.0, 1.0)))
        chunk = raw.chunks[0]
        self.assertEqual((chunk.flags, chunk.attr_mask, len(chunk.display_list) % 32), (0x3000, 0x4600, 0))
        decoded = model.read_model_bytes(gs_bytes)
        tris = [t for s in decoded.chunks[0].strips for t in gltf_export._strip_triangles(s)]
        self.assertEqual(len(tris), 2)
        for a, b, c in tris:  # back in glTF winding, every triangle faces +Y
            u = [b.position[i] - a.position[i] for i in range(3)]
            v = [c.position[i] - a.position[i] for i in range(3)]
            self.assertGreater(u[2] * v[0] - u[0] * v[2], 0)
        info = tpl.read_tpl_image_info(io.BytesIO(tpl_bytes))
        self.assertEqual([(i.width, i.height, i.format) for i in info], [(8, 8, tpl.FORMAT_CMPR)])

    def test_alpha_mode_picks_the_draw_list_and_round_trips(self):
        for mode, list_index in (("OPAQUE", 0), ("MASK", 1), ("BLEND", 2)):
            two_sided = mode == "MASK"
            gs_bytes, _tpl, _w = gltf_import.import_static_model(
                _quad_glb(alpha_mode=mode, double_sided=two_sided), name="quad"
            )
            raw = gs_file.read_gs(gs_bytes)
            self.assertEqual([len(lst) for lst in raw.chunk_lists], [int(i == list_index) for i in range(3)])
            self.assertEqual(raw.chunks[0].flags & 0x6000, (list_index + 1) << 13)
            glb = gltf_export.export_glb([("quad", model.read_model_bytes(gs_bytes))], [], {})
            doc = json.loads(glb[20 : 20 + struct.unpack_from("<I", glb, 12)[0]])
            self.assertEqual(doc["materials"][0].get("alphaMode", "OPAQUE"), mode)
            self.assertEqual(doc["materials"][0]["doubleSided"], two_sided)

    def test_static_import_stores_vertices_in_the_bone_space(self):
        bones = [_static_bone("root", -1, (0.0, 0.0, 0.0)), _static_bone("prop", 0, (0.0, 5.0, 0.0), scale=2.0)]
        skel = skeleton.write_skeleton_file(skeleton.SkeletonFile("unknown", bones))
        gs_bytes, _tpl, _warn = gltf_import.import_static_model(
            _quad_glb(translation=(0.0, 5.0, 0.0), with_texture=False), skeleton_data=skel, bone=1
        )
        raw = gs_file.read_gs(gs_bytes)
        scale = 1 << raw.pos_frac
        local = sorted(tuple(c / scale for c in p) for p in raw.positions)
        self.assertEqual(local, [(-0.5, 0.0, -0.5), (-0.5, 0.0, 0.5), (0.5, 0.0, -0.5), (0.5, 0.0, 0.5)])
        self.assertEqual({c.bone for c in raw.chunks}, {1})
        self.assertEqual(raw.bbox_max, (1.0, 5.0, 1.0))

    def test_export_then_import_reproduces_the_mesh(self):
        original = model.read_model_bytes(gs_file.write_gs(_synthetic_gs_file()))
        glb = gltf_export.export_glb([("m", original)])
        rebuilt = model.read_model_bytes(gltf_import.import_static_model(glb)[0])

        def triangles(m):
            out = []
            for ch in m.chunks:
                for s in ch.strips:
                    for t in gltf_export._strip_triangles(s):
                        ps = [tuple(round(c, 3) for c in v.position) for v in t]
                        if len(set(ps)) < 3:  # degenerate triangles are dropped on import
                            continue
                        i = ps.index(min(ps))
                        out.append(tuple(ps[i:] + ps[:i]))
            return sorted(out)

        self.assertEqual(triangles(rebuilt), triangles(original))



def _skinned_scene(bones):
    """Two quads, one per bone, as glTF-space triangles bound to joints."""
    scene = gltf_import.ImportedScene(materials=[gltf_import.ImportedMaterial("skin")])
    tris = []
    for bone_name, y in (("root", 0.0), ("arm", 2.0)):
        quad = [(-1.0, y, -1.0), (1.0, y, -1.0), (1.0, y, 1.0), (-1.0, y, 1.0)]
        for a, b, c in ((0, 2, 1), (0, 3, 2)):
            corners = (quad[a], quad[b], quad[c])
            tris.append(
                gltf_import.ImportedTriangle(
                    corners, ((0.0, 1.0, 0.0),) * 3, ((0.0, 0.0),) * 3, None, (((bone_name, 1.0),),) * 3
                )
            )
    scene.triangles[0] = tris
    return scene


def _roll_joint(glb: bytes, node_index: int, angle_degrees: float) -> bytes:
    """What a tool re-orienting one leaf joint does: the joint frame turns by
    C about its own X axis, its inverse bind becomes C^-1 x IBM, and its
    animated rotations are multiplied by C. The mesh is untouched."""
    doc, binary = gltf_import._split_glb(glb)
    binary = bytearray(binary)
    half = math.radians(angle_degrees) / 2
    c = (math.sin(half), 0.0, 0.0, math.cos(half))

    def qmul(a, b):
        ax, ay, az, aw = a
        bx, by, bz, bw = b
        return (aw * bx + ax * bw + ay * bz - az * by, aw * by - ax * bz + ay * bw + az * bx,
                aw * bz + ax * by - ay * bx + az * bw, aw * bw - ax * bx - ay * by - az * bz)

    def rewrite(accessor_index, fn):
        acc = doc["accessors"][accessor_index]
        view = doc["bufferViews"][acc["bufferView"]]
        width = {"VEC4": 4, "MAT4": 16}[acc["type"]]
        base = view.get("byteOffset", 0) + acc.get("byteOffset", 0)
        for k in range(acc["count"]):
            values = struct.unpack_from(f"<{width}f", binary, base + k * width * 4)
            struct.pack_into(f"<{width}f", binary, base + k * width * 4, *fn(k, values))

    node = doc["nodes"][node_index]
    node["rotation"] = list(qmul(tuple(node.get("rotation", (0.0, 0.0, 0.0, 1.0))), c))
    inv = gltf_import._node_matrix({"rotation": [-c[0], -c[1], -c[2], c[3]]})
    skin = doc["skins"][0]
    k_joint = skin["joints"].index(node_index)
    rewrite(skin["inverseBindMatrices"], lambda k, m: gltf_import._mat4_mul(inv, list(m)) if k == k_joint else m)
    for anim in doc.get("animations", []):
        for ch in anim["channels"]:
            if ch["target"] == {"node": node_index, "path": "rotation"}:
                rewrite(anim["samplers"][ch["sampler"]]["output"], lambda k, q: qmul(q, c))
    return gltf_export._pack_glb(doc, bytes(binary))


class SkinnedImportTests(unittest.TestCase):
    def setUp(self):
        self.bones = [_rig_bone("root", -1, (0.0, 0.0, 0.0)), _rig_bone("arm", 0, (0.0, 2.0, 0.0))]
        self.skel = skeleton.write_skeleton_file(skeleton.SkeletonFile("unknown", self.bones))
        self.anim = _animation_of(
            {1: (animation.MASK_ROTATE, [_curve(1, 3, [(0, 0), (6, 30 * 256), (12, -45 * 256)], shift=8),
                                         _curve(1, 5, [(0, 0), (12, 20 * 256)], shift=8)])},
            end_frame=12,
            events=[animation.EventKey(6, (1,))],
        )
        build = gltf_import.build_skinned_gs(_skinned_scene(self.bones), self.bones)
        self.gs_bytes = gs_file.write_gs(build.gs)

    def _mesh_by_bone(self, gs_bytes):
        m = model.read_model_bytes(gs_bytes)
        out = {}
        for ch in m.chunks:
            for s in ch.strips:
                for v in s:
                    out.setdefault(v.bone_indices[0], set()).add(tuple(round(c, 4) for c in v.position))
        return out

    def test_skinned_build_uses_multi_matrix_shapes(self):
        raw = gs_file.read_gs(self.gs_bytes)
        chunk = raw.chunks[0]
        self.assertEqual((chunk.flags & 0x3, chunk.attr_mask, chunk.bone_subset), (0x2, 0x4601, [0, 1]))
        self.assertEqual(self._mesh_by_bone(self.gs_bytes)[1], {(-1.0, 2.0, -1.0), (1.0, 2.0, -1.0), (1.0, 2.0, 1.0), (-1.0, 2.0, 1.0)})

    def test_export_then_import_keeps_mesh_and_animation(self):
        glb = gltf_export.export_glb([("body", model.read_model_bytes(self.gs_bytes))], self.bones, None, [("atk", self.anim)])
        for rolled in (glb, _roll_joint(glb, 1, 70.0)):
            gs_bytes, _images, _warnings = gltf_import.import_skinned_model(rolled, self.skel)
            self.assertEqual(self._mesh_by_bone(gs_bytes), self._mesh_by_bone(self.gs_bytes))
            ga, warnings = gltf_import.import_animation(rolled, self.skel, animation_name="atk")
            self.assertEqual(warnings, [])
            back = animation.read_animation_bytes(ga)
            self.assertEqual(back.events, [animation.EventKey(6, (1,))])
            self.assertEqual(back.header.end_frame, 12)
            for frame in range(13):
                _w0, p0 = engine_pose.pose(self.bones, self.anim, float(frame))
                _w1, p1 = engine_pose.pose(self.bones, back, float(frame))
                for a, b in zip(engine_pose.apply(p0[1], (1.0, 2.0, 1.0)), engine_pose.apply(p1[1], (1.0, 2.0, 1.0))):
                    self.assertAlmostEqual(a, b, delta=2e-3)

    def test_children_of_a_hidden_bone_keep_their_place(self):
        # a weapon bone scaled to 0 at rest (hidden), shown by the animation,
        # with an attachment point below it
        bones = [
            _rig_bone("root", -1, (0.0, 0.0, 0.0)),
            _rig_bone("weapon", 0, (0.0, 2.0, 0.0), flags=0x18C, scale=0.0),
            _rig_bone("_sw1_", 1, (0.0, 3.0, 0.0)),
        ]
        skel = skeleton.write_skeleton_file(skeleton.SkeletonFile("unknown", bones))
        show = [_curve(1, c, [(0, 0), (4, 256), (12, 256)], shift=8) for c in (0, 1, 2)]
        anim = _animation_of({1: (animation.MASK_SCALE | animation.MASK_TRANSLATE,
                                  show + [_curve(1, 6, [(0, 0), (12, 512)], shift=8)])}, end_frame=12)
        glb = gltf_export.export_glb([], bones, None, [("atk", anim)])
        back = animation.read_animation_bytes(gltf_import.import_animation(glb, skel, animation_name="atk")[0])
        for frame in range(13):
            w0, _p0 = engine_pose.pose(bones, anim, float(frame))
            w1, _p1 = engine_pose.pose(bones, back, float(frame))
            for a, b in zip(engine_pose.apply(w0[2], (0.0, 3.0, 0.0)), engine_pose.apply(w1[2], (0.0, 3.0, 0.0))):
                self.assertAlmostEqual(a, b, delta=2e-3)
        self.assertEqual({c.bone_index for c in back.curves}, {1})

    def test_new_skeleton_from_the_armature(self):
        glb = gltf_export.export_glb([("body", model.read_model_bytes(self.gs_bytes))], self.bones, None, [("atk", self.anim)])
        built, warnings = gltf_import.build_skeleton(glb)
        self.assertEqual(warnings, [])
        data = skeleton.write_skeleton_file(built)
        self.assertEqual(skeleton.write_skeleton_file(skeleton.read_skeleton_file(data)), data)
        root, arm = built.bones
        self.assertEqual((root.name, root.parent_index, root.unknown_ints), ("root", -1, (-1, 1, 0x180)))
        self.assertEqual((arm.name, arm.parent_index, arm.unknown_ints), ("arm", 0, (-1, -1, 0x180)))
        for axis, expected in enumerate((0.0, 2.0, 0.0)):
            self.assertAlmostEqual(engine_pose.rest_pivot(arm)[axis], expected, places=5)
        self.assertEqual(engine_pose.skin_matrix(arm), skeleton.IDENTITY_3X4)
        self.assertEqual(skeleton.local_bind_matrix(arm), skeleton.IDENTITY_3X4)
        # the body and the animation rebuilt on the new skeleton move like the original
        gs_bytes, _images, _w = gltf_import.import_skinned_model(glb, data)
        self.assertEqual(self._mesh_by_bone(gs_bytes), self._mesh_by_bone(self.gs_bytes))
        back = animation.read_animation_bytes(gltf_import.import_animation(glb, data, animation_name="atk")[0])
        for frame in range(13):
            _w0, p0 = engine_pose.pose(self.bones, self.anim, float(frame))
            _w1, p1 = engine_pose.pose(built.bones, back, float(frame))
            for a, b in zip(engine_pose.apply(p0[1], (1.0, 2.0, 1.0)), engine_pose.apply(p1[1], (1.0, 2.0, 1.0))):
                self.assertAlmostEqual(a, b, delta=2e-3)

    def test_rig_check_requires_the_anchor_bones(self):
        old = self.bones + [_rig_bone("_sw1_", 1, (0.0, 3.0, 0.0))]
        errors, _warnings = gltf_import.check_rig_against(self.bones, old)
        self.assertEqual(len(errors), 1)
        self.assertIn("_sw1_", errors[0])
        moved = self.bones + [_rig_bone("_sw1_", 1, (0.0, 5.0, 0.0))]
        errors, warnings = gltf_import.check_rig_against(moved, old)
        self.assertEqual(errors, [])
        self.assertIn("_sw1_ (2.0 units)", warnings[0])

    def test_template_events_are_retimed(self):
        glb = gltf_export.export_glb([("body", model.read_model_bytes(self.gs_bytes))], self.bones, None, [("atk", self.anim)])
        doc, binary = gltf_import._split_glb(glb)
        del doc["animations"][0]["extras"]
        template = animation.write_animation(_animation_of({}, end_frame=24, events=[animation.EventKey(12, (1,))]))
        ga, warnings = gltf_import.import_animation(gltf_export._pack_glb(doc, binary), self.skel, template=template)
        self.assertEqual(animation.read_animation_bytes(ga).events, [animation.EventKey(6, (1,))])
        self.assertTrue(any("retimed" in w for w in warnings))

    def _blended_scene(self):
        """The two quads, with the arm quad weighted 3:1 to arm and root."""
        scene = _skinned_scene(self.bones)
        for t in scene.triangles[0][2:]:
            t.influences = ((("arm", 0.75), ("root", 0.25)),) * 3
        return scene

    def test_blended_vertices_go_to_a_composite_shape(self):
        build = gltf_import.build_skinned_gs(self._blended_scene(), self.bones, animations=(self.anim,))
        gs_bytes = gs_file.write_gs(build.gs)
        raw = gs_file.read_gs(gs_bytes)
        self.assertEqual(gs_file.write_gs(raw), gs_bytes)
        flags = sorted((ch.flags & 0x3, ch.attr_mask, ch.bone_subset) for ch in raw.chunks)
        self.assertEqual(flags, [(0x1, 0x4600, None), (0x2, 0x4601, [0])])
        comp = raw.composite
        (record,) = comp.weights
        self.assertEqual(record[:8], (1, 0, -1, -1, 192, 64, 0, 0))
        offset, size, add, count, per_vertex, nbt = record[8:]
        self.assertEqual((offset % 32, (offset + add) % 12, count, per_vertex, nbt, size % 32), (0, 0, 2, 4, 0, 0))
        self.assertEqual(comp.unk1, 1)  # records shared by several vertices
        excess = gltf_import.composite_range_excess(raw, self.bones, [self.anim])
        self.assertTrue(0.5 < excess <= 1.0)
        # the engine's blend: sum of weight x (world x skin) x v
        m = model.read_model_bytes(gs_bytes)
        blended = [v for ch in m.chunks if ch.format & 1 for s in ch.strips for v in s]
        self.assertEqual({(tuple(v.bone_indices), tuple(v.bone_weights)) for v in blended}, {((1, 0), (0.75, 0.25))})
        for frame in range(0, 13, 3):
            _w, pal = engine_pose.pose(self.bones, self.anim, float(frame))
            for v in blended:
                got = [sum(w * engine_pose.apply(pal[b], v.position)[axis] for b, w in zip(v.bone_indices, v.bone_weights))
                       for axis in range(3)]
                arm, root = engine_pose.apply(pal[1], v.position), engine_pose.apply(pal[0], v.position)
                for axis in range(3):
                    self.assertAlmostEqual(got[axis], 0.75 * arm[axis] + 0.25 * root[axis], delta=1e-3)

    def test_rigid_build_keeps_the_heaviest_joint(self):
        build = gltf_import.build_skinned_gs(self._blended_scene(), self.bones, smooth=False)
        self.assertIsNone(build.gs.composite)
        self.assertEqual({ch.flags & 0x3 for ch in build.gs.chunks}, {0x2})
        self.assertTrue(any("rigid skinning" in w for w in build.warnings))

    def test_blended_build_stats_and_joint_map(self):
        scene = self._blended_scene()
        for t in scene.triangles[0][2:]:
            t.influences = ((("arm_twist", 0.75), ("root", 0.25)),) * 3
        scene.joint_parents["arm_twist"] = "arm"
        build = gltf_import.build_skinned_gs(scene, self.bones, animations=(self.anim,))
        self.assertEqual(build.joint_map["root"], ("root", "name"))
        self.assertEqual(build.joint_map["arm_twist"], ("arm", "parent arm"))
        stats = gs_stats.model_stats(gs_file.write_gs(build.gs))
        self.assertEqual((stats.triangles, stats.multi_matrix_shapes, stats.composite_shapes), (4, 1, 1))
        self.assertEqual((stats.positions, stats.blended_vertices, stats.bones_used), (4, 4, 2))
        shift = build.gs.composite.unk0 >> 8
        self.assertEqual(stats.blended_step, 1 / (1 << shift))

    def test_bone_weights_are_quantized_to_256ths(self):
        matched = {"a": 0, "b": 1, "c": 2, "d": 3, "e": 4, "f": 5}
        weights = gltf_import._bone_weights(
            [("a", 0.4), ("b", 0.2), ("c", 0.2), ("d", 0.1), ("e", 0.1), ("f", 0.0001)], matched, {}, set()
        )
        self.assertEqual(len(weights), 4)
        self.assertEqual(sum(w for _, w in weights), 256)
        self.assertEqual([b for b, _ in weights], [0, 1, 2, 3])
        # an unmatched joint adds its weight to its matched parent
        weights = gltf_import._bone_weights([("a", 0.5), ("x", 0.5)], {"a": 0, "b": 1}, {"x": "b"}, set())
        self.assertEqual(weights, ((0, 128), (1, 128)))
        self.assertEqual(gltf_import._bone_weights([("a", 1.0), ("b", 0.001)], matched, {}, set()), ((0, 256),))


class ShopTests(unittest.TestCase):
    def _doc(self):
        forge = [w for base in shop.FORGE_BASES * shop.FORGE_ROWS for w in (0, base)]
        forge[0] = "IID_IRONSWORD"
        sections = []
        for kind, items in (("W", ["IID_IRONSWORD", "IID_IRONLANCE"]), ("I", ["IID_VULNERARY"]), ("F", forge)):
            sections += [shop.ShopSection(shop.section_name(kind, c), list(items)) for c in (0, 1)]
        sections.sort(key=lambda s: "WIF".index(s.name[0]))
        return shop.ShopDocument(prelude=["2005/02/25 11:27:12", "author"], sections=sections, labels=[],
                                 header_tail=bytes(16))

    def test_build_then_parse_keeps_every_section(self):
        doc = self._doc()
        data = shop.build_shop(doc)
        parsed = shop.parse_shop(data)
        self.assertEqual(parsed.prelude, doc.prelude)
        self.assertEqual([(s.name, s.items) for s in parsed.sections], [(s.name, s.items) for s in doc.sections])
        self.assertEqual(shop.build_shop(parsed), data)
        # the section table is sorted by name, as the game's files are
        size, pool_end, relocations, count = struct.unpack_from(">4I", data, 0)
        self.assertEqual(size, len(data))
        table = pool_end + 0x20 + 4 * relocations
        names = data[table + 8 * count:].split(b"\0")[:count]
        self.assertEqual(names, sorted(names))

    def test_edits_and_added_chapter(self):
        doc = self._doc()
        doc.shop("W", 1).items.append("IID_SILVERSWORD")
        shop.set_forge_item(doc.shop("F", 1), 1, "IID_SLIMSWORD")
        shop.add_chapter(doc, 90, template=1)
        with self.assertRaises(ValueError):
            shop.add_chapter(doc, 90)
        parsed = shop.parse_shop(shop.build_shop(doc))
        self.assertEqual(parsed.shop("W", 90).items, ["IID_IRONSWORD", "IID_IRONLANCE", "IID_SILVERSWORD"])
        self.assertEqual(shop.forge_cells(parsed.shop("F", 90))[1], ("IID_SLIMSWORD", "MDV_SLM"))
        self.assertEqual(parsed.chapters(), [0, 1, 90])
        self.assertEqual(shop.parse_section_name("ISHOP_ITEMS_C07"), ("I", 7))
        self.assertEqual(shop.parse_section_name("SHOP_PERSON_C0000"), (None, None))


@unittest.skipUnless(os.environ.get("FE9_EXTRACTED_FILES"), "set FE9_EXTRACTED_FILES to an extracted files/ directory")
class RealI8TextureTests(unittest.TestCase):
    def test_zmap_common_tpl_image_2_is_i8(self):
        from fe_modding.formats import lz10, pak

        data = lz10.decompress((Path(os.environ["FE9_EXTRACTED_FILES"]) / "zmap" / "common.cmp").read_bytes())
        (entry,) = [e for e in pak.read_pak_entries(data) if e.name.endswith("common.tpl")]
        tpl_bytes = pak.read_pak_file_content(data, entry)
        info = tpl.read_tpl_image_info(io.BytesIO(tpl_bytes))[2]
        self.assertEqual((info.format, info.width, info.height, info.data_addr), (tpl.FORMAT_I8, 256, 256, 0x2A00))

        image = tpl.read_tpl_images(io.BytesIO(tpl_bytes))[2]
        raw = tpl_bytes[info.data_addr : info.data_addr + info.data_length]
        self.assertEqual(tpl.encode_i8(image), raw)
        self.assertEqual(tpl.replace_image(tpl_bytes, 2, image), tpl_bytes)


@unittest.skipUnless(os.environ.get("FE9_EXTRACTED_FILES"), "set FE9_EXTRACTED_FILES to an extracted files/ directory")
class DiscShopRoundTripTests(unittest.TestCase):
    def test_vanilla_shop_files_round_trip(self):
        folder = Path(os.environ["FE9_EXTRACTED_FILES"]) / "shop"
        for letter in "nhm":
            data = (folder / f"shopitem_{letter}.bin").read_bytes()
            doc = shop.parse_shop(data)
            self.assertEqual(len(doc.sections), 96)
            self.assertEqual(shop.build_shop(doc), data, letter)


@unittest.skipUnless(os.environ.get("FE9_EXTRACTED_FILES"), "set FE9_EXTRACTED_FILES to an extracted files/ directory")
class DiscFe8DataTests(unittest.TestCase):
    def setUp(self):
        self.data = (Path(os.environ["FE9_EXTRACTED_FILES"]) / "FE8Data.bin").read_bytes()

    def test_tables_follow_their_count_words_and_skill_symbols(self):
        fe8 = fe8data.read_fe8data(self.data)
        self.assertEqual((len(fe8.characters), len(fe8.classes), len(fe8.items), len(fe8.skills)), (340, 115, 189, 98))
        symbols = fe8data.symbol_offsets(self.data)
        for skill in fe8.skills:  # each SID_ symbol names its own record
            self.assertEqual(symbols[skill.sid] + fe8data.HEADER_SIZE, skill.offset)
            self.assertEqual(skill.self_index, skill.index)
        by_sid = {s.sid: s for s in fe8.skills}
        self.assertEqual(by_sid["SID_STARTRICK"].restricted_to, ["JID_SWORDMASTER", "JID_SWORDMASTER/F"])
        self.assertEqual(by_sid["SID_SUNMOON"].restricted_to, ["JID_HERO", "JID_HERO_G"])
        self.assertEqual(by_sid["SID_BIGEAR"].restricted_to, ["PID_VULCI"])
        self.assertEqual(by_sid["SID_COUNTER"].skill_items, ["IID_COUNTER"])
        self.assertEqual(by_sid["SID_SUNTRICK"].skill_items, ["IID_ESOTERIC"])

    def test_coverage_map_classifies_every_byte(self):
        from fe_modding.formats import fe8data_coverage

        cov = fe8data_coverage.build_coverage(self.data)
        summary = cov.summary()
        self.assertEqual(sum(sum(c.values()) for c in summary.values()), len(self.data))
        self.assertEqual(sum(c["undecoded"] for c in summary.values()), 0)

    def test_roster_order_gauge_and_chapter_bonus_levels(self):
        fe8 = fe8data.read_fe8data(self.data)
        by_pid = {c.pid: c for c in fe8.characters}
        self.assertEqual([by_pid[p].roster_order for p in ("PID_IKE", "PID_TIAMAT", "PID_OSCAR")], [1, 2, 3])
        self.assertEqual(by_pid["PID_GIFFCA"].start_transform_gauge, 16)
        self.assertEqual(by_pid["PID_IKE"].start_transform_gauge, 0)
        chapters = {c.chapter_id: c for c in fe8data.read_chapter_data(self.data)}
        self.assertEqual(chapters[1].enemy_bonus_levels, (0, 0, 2, 2))
        self.assertEqual(chapters[91].enemy_bonus_levels, (0, 0, 0, 0))
        # params[2] is set on exactly the skills with a scroll
        for skill in fe8.skills:
            self.assertEqual(skill.params[2], int(bool(skill.skill_items)), skill.sid)


@unittest.skipUnless(os.environ.get("FE9_EXTRACTED_FILES"), "set FE9_EXTRACTED_FILES to an extracted files/ directory")
class DiscModelRoundTripTests(unittest.TestCase):
    """Every .gs/.g/.ga on the disc - loose or inside a pack - must survive
    read -> write byte-for-byte."""

    def test_every_model_skeleton_and_animation_round_trips(self):
        writers = {
            ".gs": lambda d: gs_file.write_gs(gs_file.read_gs(d)),
            ".g": lambda d: skeleton.write_skeleton_file(skeleton.read_skeleton_file(d)),
            ".ga": lambda d: animation.write_animation(animation.read_animation_bytes(d)),
        }
        failures, checked = [], 0

        def visit(name, data):
            nonlocal checked
            if data[:4] == b"pack":
                for entry in pak.read_pak_entries(data):
                    visit(f"{name}/{entry.name}", pak.read_pak_file_content(data, entry))
                return
            writer = writers.get(Path(name).suffix.lower())
            if writer is None:
                return
            checked += 1
            if writer(data) != data:
                failures.append(name)

        root = Path(os.environ["FE9_EXTRACTED_FILES"])
        for path in root.rglob("*"):
            if not path.is_file():
                continue
            data = path.read_bytes()
            if path.suffix.lower() == ".cmp":
                try:
                    data = lz10.decompress(data)
                except Exception:  # noqa: BLE001
                    continue
            visit(str(path.relative_to(root)), data)
        self.assertGreater(checked, 0)
        self.assertEqual(failures, [])


class GameCubeDiscTests(unittest.TestCase):
    """build_gamecube_ciso() on a tiny synthetic tree, read back through its
    own CISO block map and FST."""

    def _read_disc(self, ciso: bytes) -> bytes:
        self.assertEqual(ciso[:4], gcdisc.CISO_MAGIC)
        block_size = struct.unpack_from("<I", ciso, 4)[0]
        block_map = ciso[8:gcdisc.CISO_HEADER_SIZE]
        disc = bytearray()
        stored = gcdisc.CISO_HEADER_SIZE
        last = max(i for i, used in enumerate(block_map) if used)
        for i in range(last + 1):
            if block_map[i]:
                disc += ciso[stored:stored + block_size]
                stored += block_size
            else:
                disc += bytes(block_size)
        return bytes(disc)

    def _read_files(self, disc: bytes) -> dict[str, bytes]:
        fst_offset, fst_size = struct.unpack_from(">II", disc, 0x424)
        fst = disc[fst_offset:fst_offset + fst_size]
        count = struct.unpack_from(">I", fst, 8)[0]
        out = {}
        paths = gcdisc._read_fst_order(fst)
        for i, path in enumerate(paths, start=1):
            word, offset, size = struct.unpack_from(">III", fst, i * 12)
            if not word >> 24:
                out[path] = disc[offset:offset + size]
        self.assertEqual(len(paths), count - 1)
        return out

    def test_round_trip_keeps_retail_order_and_appends_new_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "extracted"
            (root / "sys").mkdir(parents=True)
            (root / "sys" / "boot.bin").write_bytes(b"GFEE01" + bytes(0x440 - 6))
            (root / "sys" / "bi2.bin").write_bytes(bytes(0x2000))
            (root / "sys" / "apploader.img").write_bytes(b"A" * 100)
            (root / "sys" / "main.dol").write_bytes(b"D" * 300)
            files = {
                "zeta.bin": b"z" * 5,
                "Sound/b.stm": b"b" * 70,
                "Sound/a.stm": b"a" * 33,
                "Sound/new.stm": b"n" * 9,
                "alpha.bin": b"" * 40,
            }
            for rel, data in files.items():
                (root / "files" / rel).parent.mkdir(parents=True, exist_ok=True)
                (root / "files" / rel).write_bytes(data)
            # A "retail" FST whose order isn't alphabetical: zeta, Sound/{b, a}, alpha.
            retail_root = Path(tmp) / "retail"
            (retail_root / "files" / "Sound").mkdir(parents=True)
            for rel in ("zeta.bin", "Sound/b.stm", "Sound/a.stm", "alpha.bin"):
                (retail_root / "files" / rel).write_bytes(b"x")
            tree = gcdisc._Node(name="", children=[
                gcdisc._Node("zeta.bin", retail_root / "files/zeta.bin"),
                gcdisc._Node("Sound", children=[
                    gcdisc._Node("b.stm", retail_root / "files/Sound/b.stm"),
                    gcdisc._Node("a.stm", retail_root / "files/Sound/a.stm"),
                ]),
                gcdisc._Node("alpha.bin", retail_root / "files/alpha.bin"),
            ])
            (root / "sys" / "fst.bin").write_bytes(gcdisc._build_fst(gcdisc._flatten(tree), 0)[0])

            dest = Path(tmp) / "out.ciso"
            result = gcdisc.build_gamecube_ciso(root, dest)
            disc = self._read_disc(dest.read_bytes())

        self.assertFalse(result.oversized)
        self.assertEqual(disc[:6], b"GFEE01")
        dol_offset = struct.unpack_from(">I", disc, 0x420)[0]
        self.assertEqual(disc[dol_offset:dol_offset + 300], b"D" * 300)
        read_back = self._read_files(disc)
        self.assertEqual(read_back, files)
        self.assertEqual(
            list(read_back),
            ["zeta.bin", "Sound/b.stm", "Sound/a.stm", "Sound/new.stm", "alpha.bin"],
        )



class BattleModelSetTests(unittest.TestCase):
    def test_battle_set_reads_every_weapon_pack(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp) / "zu" / "abc"
            folder.mkdir(parents=True)
            body = [("abc.gs", b"mesh"), ("abc.g", b"skel")]
            (folder / "abc_ax.pak").write_bytes(pak.pack_pak(body + [("abc_at1_ax.ga", b"ax")], [0, 0, 0]))
            (folder / "abc_no.pak").write_bytes(pak.pack_pak(body + [("abc_dam_no.ga", b"no")], [0, 0, 0]))
            (folder / "abc.tpl").write_bytes(b"tex")
            (folder / "other.tpl").write_bytes(b"tex2")
            path = folder / "abc_ax.pak"
            self.assertEqual(model_viewer._set_containers(path), [path, folder / "abc_no.pak"])
            files, animations = model_viewer._set_contents(path, {folder / "abc_no.pak": pak.pack_pak(body + [("abc_dam_no.ga", b"new")], [0, 0, 0])})
            self.assertEqual(sorted(files), ["abc.g", "abc.gs", "abc.tpl"])
            self.assertEqual(animations, [("abc_at1_ax.ga", b"ax"), ("abc_dam_no.ga", b"new")])
            self.assertEqual(model_viewer.set_animation_names(path), ["abc_at1_ax.ga", "abc_dam_no.ga"])
            entries, pack_files = model_viewer._read_container(path)
            self.assertEqual(model_viewer._pack(path, entries, pack_files), path.read_bytes())  # stays uncompressed


class ProjectOriginalsTests(unittest.TestCase):
    def test_first_write_keeps_the_extracted_file_until_restored(self):
        from fe_modding.games import Game
        from fe_modding.project import ModProject

        with tempfile.TemporaryDirectory() as tmp:
            project = ModProject(name="t", game=Game.PATH_OF_RADIANCE, directory=Path(tmp))
            folder = project.extracted_dir / "files" / "ymu" / "archer"
            folder.mkdir(parents=True)
            pack = folder / "pack.cmp"
            pack.write_bytes(b"vanilla")
            project.write_keeping_original(pack, b"first import")
            project.write_keeping_original(pack, b"second import")
            self.assertEqual(pack.read_bytes(), b"second import")
            self.assertEqual(project.originals_in(folder), [pack])
            project.restore_original(pack)
            self.assertEqual(pack.read_bytes(), b"vanilla")
            self.assertEqual(project.originals_in(folder), [])



class TplRegionTests(unittest.TestCase):
    def _sheet(self):
        from PIL import Image

        # four palette entries, two of them duplicates the replacement can reuse
        palette = [(248, 0, 0, 255), (0, 0, 248, 255), (248, 0, 0, 255), (0, 0, 248, 255)]
        container = _build_minimal_c8_tpl(16, 8, palette)
        left = Image.new("RGBA", (8, 8), (248, 0, 0, 255))
        right = Image.new("RGBA", (8, 8), (0, 0, 248, 255))
        container = tpl.replace_region(container, 0, (0, 0, 8, 8), left)
        return tpl.replace_region(container, 0, (8, 0, 16, 8), right)

    def test_replace_region_keeps_rest_of_sheet_and_adds_new_colors(self):
        from PIL import Image

        container = self._sheet()
        green = Image.new("RGBA", (8, 8), (0, 248, 0, 255))
        patched = tpl.replace_region(container, 0, (8, 0, 16, 8), green)

        (decoded,) = tpl.read_tpl_images(io.BytesIO(patched))
        self.assertEqual(decoded.getpixel((0, 0)), (248, 0, 0, 255))  # untouched icon
        self.assertEqual(decoded.getpixel((12, 4)), (0, 248, 0, 255))  # a color the palette didn't have
        self.assertEqual(len(patched), len(container))

    def test_replace_region_round_trips_an_exported_icon(self):
        container = self._sheet()
        (decoded,) = tpl.read_tpl_images(io.BytesIO(container))
        again = tpl.replace_region(container, 0, (0, 0, 8, 8), decoded.crop((0, 0, 8, 8)))
        self.assertEqual(again, container)

    def test_replace_region_rejects_box_outside_image(self):
        from PIL import Image

        with self.assertRaises(tpl.TplError):
            tpl.replace_region(self._sheet(), 0, (8, 0, 24, 8), Image.new("RGBA", (16, 8)))


if __name__ == "__main__":
    unittest.main()
