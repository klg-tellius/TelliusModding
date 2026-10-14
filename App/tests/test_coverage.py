import os
import unittest
from pathlib import Path

from fe_modding.formats import coverage as cov_module
from fe_modding.formats.coverage import (DECODED, PADDING, PLAUSIBLE, UNCLASSIFIED, UNDECODED, UNREAD, FileCoverage,
                                         Report, Walker)


class FileCoverageTest(unittest.TestCase):
    def test_bits_judge_the_set_bits(self):
        cov = FileCoverage(bytes([0x03, 0x10, 0x30]), "t", "t")
        cov.bits(0, 1, known=0x03)
        cov.bits(1, 1, known=0x03, plausible=0x10)
        cov.bits(2, 1, known=0x03, plausible=0x10)
        self.assertEqual(list(cov.status), [DECODED, PLAUSIBLE, UNDECODED])

    def test_zero_is_padding_only_when_zero(self):
        cov = FileCoverage(bytes([0, 0, 5, 0]), "t", "t")
        cov.zero(0, 2, "a")
        cov.zero(2, 2, "b", nonzero=UNREAD)
        self.assertEqual(list(cov.status), [PADDING, PADDING, UNREAD, UNREAD])

    def test_fill_only_touches_unplaced_bytes(self):
        cov = FileCoverage(bytes([1, 0, 2, 0]), "t", "t")
        cov.mark(0, 1, DECODED)
        cov.fill(PADDING, only_zero=True)
        self.assertEqual(list(cov.status), [DECODED, PADDING, UNCLASSIFIED, PADDING])
        self.assertEqual(cov.open_fields()[(UNCLASSIFIED, "(unplaced bytes)")], 1)

    def test_unknown_file_is_reported_unclassified(self):
        report = Report()
        Walker(report).child("x/strange.qqq", b"abcd")
        totals = report.formats["unknown .qqq"]
        self.assertEqual(totals.counts[UNCLASSIFIED], 4)


class AnimationCoverageTest(unittest.TestCase):
    def test_known_material_track_and_hit_events_are_not_open(self):
        import struct
        from fe_modding.formats import animation

        events = animation.write_event_block([animation.EventKey(1, (0, 1, 2, 5, 9, 10, 11,
                                                                     12, 13, 14, 30, 31, 32, 33,
                                                                     34, 35, 36, 37, 38, 39, 42,
                                                                     43, 44, 45, 46, 49, 51, 52,
                                                                     53, 54, 55, 56, 58, 60))])
        material = struct.pack(">HHIH", 1, 0, 0, 10) + struct.pack(">HHHh", 1, 0, 0, 128)
        blocks = [events, material, None, material, material] + [None] * 3 + [b"\x12\x34\x56\x78"]
        anim = animation.GaAnimation(
            header=animation.GaHeader((0, 0, 0, 0x11, 0, 0, 2, 0, 0, 0, 0, 0)),
            groups=[], curves=[], footer=animation.GaFooter(blocks=blocks, order=[0, 1, 3, 4, 8]),
        )
        report = Report()
        Walker(report).child("test.ga", animation.write_animation(anim))
        totals = report.formats["animation"]
        self.assertEqual(totals.failures, [])
        self.assertEqual(totals.counts[UNCLASSIFIED], 0)
        self.assertEqual(totals.counts[PLAUSIBLE], 0)
        self.assertEqual(totals.fields[(UNDECODED, "particle table details")][0], 4)


class ParticleLayoutTest(unittest.TestCase):
    def test_particle_header_stages_and_keys_are_classified_without_guessing_controls(self):
        import struct
        from fe_modding.formats import animation, coverage_handlers

        name = b"|root|\0"
        block = bytearray(8 + 0x34 + len(name) + 12 + 8 + 12 + 8)
        struct.pack_into(">IHH", block, 0, 0x12345678, 0, 1)
        block[8 + 0x34:8 + 0x34 + len(name)] = name
        header = animation.GaHeader((0, 0, 0, 0x11, 0, 0, 10, 0, 0, 0, 0, 0))
        footer = animation.GaFooter(blocks=[None] * 8 + [bytes(block)], order=[8])
        anim = animation.GaAnimation(header=header, groups=[], curves=[], footer=footer)
        initial = animation.write_animation(anim)
        footer_at = struct.unpack_from(">I", initial)[0]
        slot_at = struct.unpack_from(">I", initial, footer_at + 32)[0]
        name_at = slot_at + 8 + 0x34
        stages_at = name_at + len(name)
        ranges_at = stages_at + 12
        curves_at = ranges_at + 8
        keys_at = curves_at + 12
        struct.pack_into(">I", block, 8, name_at)
        struct.pack_into(">H", block, 8 + 6, 0x5004)  # textured, alpha/additive, no depth test
        struct.pack_into(">h", block, 8 + 0x0A, 2)
        struct.pack_into(">H", block, 8 + 0x0C, 0x0780)
        struct.pack_into(">2h", block, 8 + 0x16, 64, 128)
        struct.pack_into(">h", block, 8 + 0x1A, 5760)  # 90 degrees
        struct.pack_into(">H", block, 8 + 0x1E, 1)
        struct.pack_into(">4I", block, 8 + 0x20, stages_at, ranges_at, curves_at, keys_at)
        pos = 8 + 0x34 + len(name)
        struct.pack_into(">Hhhhhh", block, pos, 0, 0, 10, 64, 0, 0)
        struct.pack_into(">4H", block, pos + 12, 0, 0, 0, 1)
        struct.pack_into(">HBBHHI", block, pos + 20, 0, 6, 0, 10, 2, 0)
        struct.pack_into(">HhHh", block, pos + 32, 0, 0, 10, 64)
        anim.footer.blocks[8] = bytes(block)
        data = animation.write_animation(anim)
        layout = animation.read_particle_table_layout(data)
        self.assertEqual((layout.emitters[0].name_path, layout.emitters[0].material_index,
                          layout.emitters[0].first_stage_index, layout.emitters[0].draw_flags,
                          layout.emitters[0].unresolved_control, layout.emitters[0].initial_scale_st,
                          layout.emitters[0].initial_rotation_degrees,
                          layout.emitters[0].stage_count, layout.emitters[0].curve_count),
                         ("|root|", 2, 0, 0x5004, 0x0780, (1.0, 2.0), 90.0, 1, 1))
        stage = animation.read_particle_stage(data, layout.emitters[0], 0)
        self.assertEqual((stage.local_index, stage.global_index, stage.start_frame, stage.end_frame,
                          stage.initial_position, stage.first_curve, stage.curve_count),
                         (0, 0, 0, 10, (1.0, 0.0, 0.0), 0, 1))
        curve = animation.read_particle_curve(data, layout.emitters[0], stage.first_curve)
        self.assertEqual((curve.channel_name, curve.scale_shift, curve.last_key_frame,
                          curve.key_count, curve.first_key),
                         ("velocity X", 6, 10, 2, 0))
        keys = animation.read_particle_curve_keys(data, layout.emitters[0], curve)
        self.assertEqual(keys, ((0, 0.0), (10, 1.0)))
        self.assertEqual([animation.sample_particle_curve(keys, frame) for frame in (-1, 5, 12)],
                         [0.0, 0.5, 1.0])
        cov = FileCoverage(data, "animation", "particle.ga")
        coverage_handlers._ga_particle_table(cov, slot_at, len(data))
        self.assertEqual(set(cov.status[keys_at:keys_at + 8]), {DECODED})
        self.assertEqual(cov.status[slot_at + 8 + 4], PLAUSIBLE)
        self.assertEqual(set(cov.status[stages_at:stages_at + 2]), {PLAUSIBLE})
        self.assertEqual(set(cov.status[curves_at + 4:curves_at + 6]), {PLAUSIBLE})
        self.assertEqual(set(cov.status[slot_at + 8 + 6:slot_at + 8 + 8]), {DECODED})
        self.assertEqual(set(cov.status[slot_at + 8 + 0x0C:slot_at + 8 + 0x0E]), {UNDECODED})
        self.assertEqual(set(cov.status[slot_at + 8 + 0x0E:slot_at + 8 + 0x1A]), {DECODED})

        struct.pack_into(">H", block, 8 + 6, 1)
        struct.pack_into(">h", block, 8 + 0x0E, 96)
        anim.footer.blocks[8] = bytes(block)
        mode1_data = animation.write_animation(anim)
        mode1_layout = animation.read_particle_table_layout(mode1_data)
        self.assertEqual(mode1_layout.emitters[0].initial_scale_st, (1.5, 1.5))
        mode1_cov = FileCoverage(mode1_data, "animation", "particle_mode1.ga")
        coverage_handlers._ga_particle_table(mode1_cov, slot_at, len(mode1_data))
        self.assertEqual(set(mode1_cov.status[slot_at + 8 + 0x0E:slot_at + 8 + 0x1A]), {DECODED})

        struct.pack_into(">H", block, 8 + 0x1E, 0)
        struct.pack_into(">2I", block, 8 + 0x20, ranges_at, ranges_at)
        anim.footer.blocks[8] = bytes(block)
        orphan_data = animation.write_animation(anim)
        orphan_cov = FileCoverage(orphan_data, "animation", "particle_orphan.ga")
        coverage_handlers._ga_particle_table(orphan_cov, slot_at, len(orphan_data))
        self.assertEqual(set(orphan_cov.status[ranges_at:ranges_at + 8]), {PLAUSIBLE})


class Fe10ContainerTest(unittest.TestCase):
    def test_decompressed_cms_container_is_walked(self):
        import struct

        data_size = 0x10
        body = struct.pack(">I", 4) + b"ABC" + bytes([0]) + bytes(8)  # a pointer to the string "ABC"
        relocations = struct.pack(">I", 0)
        symbols = struct.pack(">II", 0, 0) + b"Sym" + bytes([0])
        size = 0x20 + data_size + len(relocations) + len(symbols)
        blob = struct.pack(">4I", size, data_size, 1, 1) + bytes(16) + body + relocations + symbols
        report = Report()
        Walker(report).child("FE10Test.cms#", blob)
        totals = report.formats["fe10 container"]
        self.assertEqual(totals.failures, [])
        self.assertEqual(totals.counts[UNCLASSIFIED], 0)
        # the 16 body bytes: the pointer word (4) and the string (4) are decoded, the rest is records
        self.assertEqual(totals.counts[UNDECODED], 8)
        self.assertEqual(totals.fields[(UNDECODED, "Sym records")][0], 8)

    def test_other_cms_names_are_not_taken_for_containers(self):
        report = Report()
        Walker(report).child("Fonts/system.cms", bytes(64))
        self.assertNotIn("fe10 container", report.formats)


FILES = os.environ.get("FE9_EXTRACTED_FILES")
#: Small real files, one per handler family that has no other test here.
SAMPLES = ("FE8Data.bin", "FE8Anim.bin", "FE8Effect.bin", "cp_data.bin", "s/rect.bin", "window/RectDesc.bin",
           "tut_data_en.bin|tut_data.bin", "client.bin", "etc/curb.g", "etc/curb.gs", "etc/curb.ga", "etc/cursor.tpl",
           "zmap/bmap01/map.cmp", "zmap/bmap01/dispos.cmp", "Scripts/C01.cmb", "Sound/gcfesnd.bin",
           "Sound/gcfesnd.sdir", "Sound/gcfesnd.pool", "zbg/map10_house/bf.cmp")


@unittest.skipUnless(FILES, "set FE9_EXTRACTED_FILES to an extracted files/ directory")
class RealFilesTest(unittest.TestCase):
    def test_handlers_place_every_byte(self):
        report = Report()
        walker = Walker(report)
        for choices in SAMPLES:   # "a|b": the first that exists (the JP disc has one tut_data.bin)
            rel = next((r for r in choices.split("|") if (Path(FILES) / r).is_file()), choices.split("|")[0])
            walker.child(rel, (Path(FILES) / rel).read_bytes())
        for fmt, totals in report.formats.items():
            self.assertFalse(fmt.startswith("unknown"), fmt)
            self.assertEqual(totals.failures, [], fmt)
            self.assertEqual(totals.counts[UNCLASSIFIED], 0, f"{fmt}: {totals.fields}")
        self.assertGreater(report.formats["map.bin"].files, 1)  # chapter and battle-scenery map.bin
        summary = cov_module.format_summary(report)
        self.assertIn("TOTAL (leaf)", summary)

    def test_all_effect_particle_tables_have_valid_ranges(self):
        from fe_modding.formats import animation, effects

        particle_tables = 0
        for path in (Path(FILES) / "yme").glob("EID_*.cmp"):
            parts = effects.read_effect_pack(path.read_bytes())
            ga = next((blob for name, blob in parts.items() if name.endswith(".ga")), None)
            if ga is None:
                continue
            layout = animation.read_particle_table_layout(ga)
            particle_tables += layout is not None
            if layout is not None:
                global_index = 0
                for emitter_index, emitter in enumerate(layout.emitters):
                    self.assertEqual(emitter.local_index, emitter_index)
                    self.assertEqual(emitter.first_stage_index, global_index)
                    for index in range(emitter.stage_count):
                        stage = animation.read_particle_stage(ga, emitter, index)
                        self.assertEqual(stage.local_index, index)
                        self.assertEqual(stage.global_index, global_index)
                        self.assertLessEqual(stage.start_frame, stage.end_frame)
                        global_index += 1
                    for index in range(emitter.curve_count):
                        curve = animation.read_particle_curve(ga, emitter, index)
                        if curve.key_count:
                            key_at = emitter.keys_offset + (curve.first_key + curve.key_count - 1) * 4
                            self.assertEqual(curve.last_key_frame,
                                             int.from_bytes(ga[key_at:key_at + 2], "big"))
        self.assertGreater(particle_tables, 0)


if __name__ == "__main__":
    unittest.main()
