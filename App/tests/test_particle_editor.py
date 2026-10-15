import struct
import unittest

from fe_modding.formats import animation, effects, particle_editor


def sample_ga() -> bytes:
    """One emitter, stage, curve and two keys with real slot-8 pointers."""
    footer = 0x30
    block = footer + 40
    record = block + 8
    stages = record + 0x34
    ranges = stages + 12
    curves = ranges + 8
    keys = curves + 12
    name = keys + 8
    data = bytearray(name + len(b"|root|\0"))
    struct.pack_into(">12I", data, 0, footer, 0, 0, 0x11, 0, 0, 20, 0, 0x30, 0x30, 0, 0x30)
    struct.pack_into(">I", data, footer + 8 * 4, block)
    struct.pack_into(">IHH", data, block, 0x12345678, 0, 1)
    struct.pack_into(">IHHHhH", data, record, name, 0, 4, 0, 1, 0x0600)
    struct.pack_into(">6h", data, record + 0x0E, 64, 64, 64, 64, 64, 64)
    struct.pack_into(">hHH", data, record + 0x1A, 0, 0, 1)
    struct.pack_into(">4I", data, record + 0x20, stages, ranges, curves, keys)
    struct.pack_into(">Hhhhhh", data, stages, 0, 2, 12, 64, 128, -64)
    struct.pack_into(">4H", data, ranges, 0, 0, 0, 1)
    struct.pack_into(">HBBHHI", data, curves, 0, 6, 0, 10, 2, 0)
    struct.pack_into(">HhHh", data, keys, 0, 64, 10, 128)
    data[name:] = b"|root|\0"
    return bytes(data)


def two_emitter_ga() -> bytes:
    data = bytearray(sample_ga()[:0x58])
    block = len(data)
    data += struct.pack(">IHH", 0x12345678, 0, 2) + bytes(2 * 0x34)
    for index in range(2):
        record = block + 8 + index * 0x34
        stages = len(data)
        data += struct.pack(">Hhhhhh", 0, 0, 10, 0, 0, 0)
        ranges = len(data)
        data += struct.pack(">4H", index, 0, 0, 1)
        curves = len(data)
        data += struct.pack(">HBBHHI", 4, 0, 0, 0, 1, 0)
        keys = len(data)
        data += struct.pack(">Hh", 0, 64)
        name = len(data)
        data += f"|emitter{index}|".encode("ascii") + b"\0"
        struct.pack_into(">IHHHhH", data, record, name, index, 4, index, 0, 0)
        struct.pack_into(">H4I", data, record + 0x1E, 1, stages, ranges, curves, keys)
    struct.pack_into(">I", data, 0x30 + 8 * 4, block)
    return bytes(data)


class ParticleEditTests(unittest.TestCase):
    def test_edits_keep_other_bytes_and_reopen(self):
        original = sample_ga()
        updated = particle_editor.edit_stage(original, 0, 0, start=3, x=192)
        updated = particle_editor.edit_key(updated, 0, 0, 1, frame=9, value=256)
        updated = particle_editor.edit_emitter(updated, 0, material=2, raw_control=0x1234)
        updated = particle_editor.edit_curve(updated, 0, 0, channel=1, scale_shift=7)
        emitter = animation.read_particle_table_layout(updated).emitters[0]
        stage = animation.read_particle_stage(updated, emitter, 0)
        curve = animation.read_particle_curve(updated, emitter, 0)
        self.assertEqual((emitter.material_index, emitter.unresolved_control), (2, 0x1234))
        self.assertEqual((stage.start_frame, stage.initial_position[0]), (3, 3.0))
        self.assertEqual((curve.channel, curve.scale_shift, curve.last_key_frame), (1, 7, 9))
        self.assertEqual(animation.read_particle_curve_keys(updated, emitter, curve)[-1], (9, 2.0))
        changed = {i for i, (a, b) in enumerate(zip(original, updated)) if a != b}
        self.assertTrue(changed)
        self.assertEqual(len(original), len(updated))
        self.assertEqual(updated[:0x30], original[:0x30])

    def test_rejects_bad_ranges_and_order(self):
        original = sample_ga()
        with self.assertRaises(particle_editor.ParticleEditError):
            particle_editor.edit_stage(original, 0, 0, start=13)
        with self.assertRaises(particle_editor.ParticleEditError):
            particle_editor.edit_key(original, 0, 0, 1, frame=0)
        with self.assertRaises(particle_editor.ParticleEditError):
            particle_editor.edit_curve(original, 0, 0, scale_shift=16)

    def test_structural_edits_retarget_tables(self):
        original = sample_ga()
        changed = particle_editor.duplicate_stage(original, 0, 0)
        layout = animation.read_particle_table_layout(changed)
        emitter = layout.emitters[0]
        self.assertEqual((emitter.stage_count, emitter.curve_count), (2, 2))
        self.assertEqual(animation.read_particle_stage(changed, emitter, 1).global_index, 1)
        self.assertEqual(changed[:emitter.record_offset], original[:emitter.record_offset])
        changed = particle_editor.add_curve(changed, 0, 1, 4)
        emitter = animation.read_particle_table_layout(changed).emitters[0]
        self.assertEqual(emitter.curve_count, 3)
        changed = particle_editor.add_key(changed, 0, 2, 5, 32)
        emitter = animation.read_particle_table_layout(changed).emitters[0]
        curve = animation.read_particle_curve(changed, emitter, 2)
        self.assertEqual(curve.key_count, 2)
        changed = particle_editor.remove_key(changed, 0, 2, 0)
        changed = particle_editor.remove_curve(changed, 0, 1, 2)
        changed = particle_editor.remove_stage(changed, 0, 1)
        emitter = animation.read_particle_table_layout(changed).emitters[0]
        self.assertEqual((emitter.stage_count, emitter.curve_count), (1, 1))

    def test_pack_save_preserves_other_members(self):
        original = {"EID_TEST.g": b"skeleton", "EID_TEST.gs": b"materials",
                    "EID_TEST.ga": sample_ga(), "EID_TEST.tpl": b"texture"}
        packed = effects.build_effect_pack(original)
        parts = effects.read_effect_pack(packed)
        parts = effects.replace_part(parts, "ga", particle_editor.add_key(parts["EID_TEST.ga"], 0, 0, 5, 96))
        reopened = effects.read_effect_pack(effects.build_effect_pack(parts))
        self.assertEqual({key: value for key, value in reopened.items() if not key.endswith(".ga")},
                         {key: value for key, value in original.items() if not key.endswith(".ga")})
        emitter = animation.read_particle_table_layout(reopened["EID_TEST.ga"]).emitters[0]
        curve = animation.read_particle_curve(reopened["EID_TEST.ga"], emitter, 0)
        self.assertEqual(curve.key_count, 3)

    def test_emitter_path_can_change_without_moving_tables(self):
        original = sample_ga()
        changed = particle_editor.edit_emitter_name(original, 0, "|other|")
        emitter = animation.read_particle_table_layout(changed).emitters[0]
        self.assertEqual(emitter.name_path, "|other|")
        self.assertEqual(changed[:len(original)],
                         original[:emitter.record_offset] +
                         changed[emitter.record_offset:emitter.record_offset + 4] +
                         original[emitter.record_offset + 4:])

    def test_stage_count_change_updates_later_emitter_indices(self):
        original = two_emitter_ga()
        changed = particle_editor.duplicate_stage(original, 0, 0)
        layout = animation.read_particle_table_layout(changed)
        self.assertEqual(layout.emitters[1].first_stage_index, 2)
        self.assertEqual(animation.read_particle_stage(changed, layout.emitters[1], 0).global_index, 2)

    def test_event_resize_rebases_particle_pointers(self):
        original = sample_ga()
        events = [animation.EventKey(4, (0, 12)), animation.EventKey(18, (55,))]
        changed = particle_editor.replace_events(original, events)
        self.assertEqual(animation.read_animation_bytes(changed).events, events)
        emitter = animation.read_particle_table_layout(changed).emitters[0]
        self.assertEqual(emitter.name_path, "|root|")
        self.assertEqual(animation.read_particle_curve_keys(
            changed, emitter, animation.read_particle_curve(changed, emitter, 0)),
            ((0, 1.0), (10, 2.0)))
        self.assertEqual(particle_editor.replace_events(changed, events), changed)
        changed_again = particle_editor.duplicate_stage(changed, 0, 0)
        changed_again = particle_editor.replace_events(changed_again, [animation.EventKey(7, (1,))])
        self.assertEqual(animation.read_particle_table_layout(changed_again).emitters[0].stage_count, 2)

    def test_material_tracks_keep_particle_references_valid(self):
        tracks = {0: animation.MaterialTrack(0, ((0, 0), (10, 255)))}
        changed = particle_editor.replace_material_tracks(sample_ga(), 1, tracks, 1)
        anim = animation.read_animation_bytes(changed)
        self.assertEqual(anim.material_alphas(), tracks)
        self.assertEqual(animation.read_particle_table_layout(changed).emitters[0].name_path, "|root|")
        self.assertEqual(particle_editor.replace_material_tracks(changed, 1, tracks, 1), changed)

    def test_whole_emitter_operations_keep_independent_tables(self):
        original = sample_ga()
        doubled = particle_editor.duplicate_emitter(original, 0)
        layout = animation.read_particle_table_layout(doubled)
        self.assertEqual(len(layout.emitters), 2)
        self.assertEqual(layout.emitters[1].first_stage_index, 1)
        self.assertNotEqual(layout.emitters[0].stages_offset, layout.emitters[1].stages_offset)
        changed = particle_editor.edit_stage(doubled, 1, 0, x=192)
        layout = animation.read_particle_table_layout(changed)
        self.assertEqual(animation.read_particle_stage(changed, layout.emitters[0], 0).initial_position[0], 1.0)
        self.assertEqual(animation.read_particle_stage(changed, layout.emitters[1], 0).initial_position[0], 3.0)
        removed = particle_editor.remove_emitter(changed, 0)
        remaining = animation.read_particle_table_layout(removed).emitters[0]
        self.assertEqual((remaining.local_index, remaining.first_stage_index), (0, 0))
        self.assertEqual(animation.read_particle_stage(removed, remaining, 0).initial_position[0], 3.0)

    def test_add_emitter_to_empty_table(self):
        empty = bytearray(sample_ga())
        struct.pack_into(">H", empty, 0x58 + 6, 0)
        changed = particle_editor.add_emitter(bytes(empty), "|new|")
        emitter = animation.read_particle_table_layout(changed).emitters[0]
        self.assertEqual((emitter.name_path, emitter.stage_count, emitter.material_index),
                         ("|new|", 0, -1))
        changed = particle_editor.add_stage(changed, 0)
        self.assertEqual(animation.read_particle_table_layout(changed).emitters[0].stage_count, 1)

    def test_emitter_record_changes_survive_footer_rewrites(self):
        changed = particle_editor.add_emitter(sample_ga(), "|new|")
        changed = particle_editor.duplicate_emitter(changed, 0)
        changed = particle_editor.remove_emitter(changed, 0)
        changed = particle_editor.replace_events(changed, [animation.EventKey(6, (12,))])
        changed = particle_editor.replace_material_tracks(
            changed, 1, {0: animation.MaterialTrack(0, ((0, 255),))}, 1)
        layout = animation.read_particle_table_layout(changed)
        self.assertEqual([emitter.name_path for emitter in layout.emitters], ["|new|", "|root|"])
        self.assertEqual([emitter.local_index for emitter in layout.emitters], [0, 1])
        self.assertEqual(animation.read_animation_bytes(changed).events,
                         [animation.EventKey(6, (12,))])
        curve = animation.read_particle_curve(changed, layout.emitters[1], 0)
        self.assertEqual(animation.read_particle_curve_keys(changed, layout.emitters[1], curve),
                         ((0, 1.0), (10, 2.0)))


if __name__ == "__main__":
    unittest.main()
