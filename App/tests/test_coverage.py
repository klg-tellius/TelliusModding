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

        events = animation.write_event_block([animation.EventKey(1, (0, 1, 2, 5, 6, 7, 9, 10, 11,
                                                                     12, 13, 14, 15, 16, 17, 18,
                                                                     19, 30, 31, 32, 33,
                                                                     34, 35, 36, 37, 38, 39, 42,
                                                                     43, 44, 45, 46, 47, 48, 49,
                                                                     50, 51, 52, 53, 54, 55, 56,
                                                                     58, 60, 1000))])
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


    def test_radiant_dawn_footer_chain(self):
        import struct
        from fe_modding.formats import animation

        events = animation.write_event_block([animation.EventKey(1, (1000,))])
        odd = b"4Vx"
        first, second = 0x30, 0x30 + len(odd)
        tail = second + len(events)
        footer = tail + 12
        header = struct.pack(">12I", footer, 0, 0x1000000, 0x11, 0, 0, 0x40, 0, 0x30, 0x30, 0, 0x30)
        data = (header + odd + events + struct.pack(">3I", 0, second, 0)
                + struct.pack(">3I", 9, first, tail))
        self.assertEqual(animation.fe10_footer_chain(data, footer), [(footer, 9, first), (tail, 0, second)])
        report = Report()
        Walker(report).child("rd.ga", data)
        totals = report.formats["animation"]
        self.assertEqual(totals.failures, [])
        self.assertEqual(totals.counts[UNCLASSIFIED], 0)
        self.assertEqual(totals.fields[(UNDECODED, "RD footer slot 9 block")][0], 4)

    def test_radiant_dawn_event_track_reader(self):
        import struct
        from fe_modding.formats import animation

        block = (struct.pack(">HHI3H", 3, 0, 0, 16, 0xFFFF, 24) + b"\0\0"
                 + struct.pack(">HBB2H", 2, 0, 1, 0x1F, 0xFFFF)
                 + struct.pack(">HBB4H", 9, 0, 2, 3, 0, 1000, 5))
        self.assertEqual(animation.read_fe10_event_block(block), [
            animation.Fe10EventKey(2, ((0x1F, -1),)),
            animation.Fe10EventKey(9, ((3, 0), (1000, 5))),
        ])
        with self.assertRaises(animation.AnimationError):
            animation.read_fe10_event_block(block[:32])

    def test_radiant_dawn_sound_data(self):
        """Cue fields, a SND_* table, the strings and an unexported cue record."""
        import struct

        from fe_modding.formats import coverage_handlers
        from fe_modding.formats.common import HEADER_SIZE
        from tests.test_fe10data import _container

        cue = struct.pack(">II", 0x60, 0x68) + bytes(range(1, 9)) + b"\0" + bytes(range(9, 23)) + b"\0" + bytes(4)
        table = struct.pack(">III", 1, 1000, 0)  # SND_SFX_MAYA_DATA: code 1000 -> cue at 0
        body = cue + table + cue + bytes(0x60 - 0x24 - 12 - 0x24) + b"SFX_A\0\0\0" + b"SE_A\0\0\0\0"
        pointers = [0, 4, 0x28, 0x30, 0x34]
        data = _container(body, pointers, [("SFX_A", 0), ("SND_SFX_MAYA_DATA", 0x24)])
        cov = FileCoverage(data, "fe10 sound data", "sound_data.cms#")
        coverage_handlers.fe10_sound_data(cov, None)
        record = HEADER_SIZE + 0x30
        self.assertEqual(set(cov.status[record:record + 0x24]), {UNREAD})
        rest = cov.status[:record] + cov.status[record + 0x24:]
        self.assertFalse({UNCLASSIFIED, UNDECODED, PLAUSIBLE, UNREAD} & set(rest[0x18:]))

    def test_radiant_dawn_slots_are_decoded(self):
        """Slot 5 events, slot 0/6-12 key tables and slot 13 particles."""
        import struct

        events = struct.pack(">HHIH", 1, 0, 0, 10) + struct.pack(">HBB2H", 4, 0, 1, 3, 0)
        tracks = struct.pack(">HHI2H", 2, 0, 0, 0xFFFF, 12) + struct.pack(">HH2h", 1, 0, 0, 255)
        name = b"|root|\0\0"
        body = 0x30
        blocks = [(5, events), (0, tracks), (6, tracks), (9, tracks)]
        layout, at = [], body
        for slot, data in blocks:
            layout.append((slot, at, data))
            at += len(data)
        particles_at = at
        rec = particles_at + 8
        name_at = rec + 0x34
        stages_at = name_at + len(name)
        ranges_at = stages_at + 12
        curves_at = ranges_at + 8
        keys_at = curves_at + 12
        particles = bytearray(keys_at + 4 - particles_at)
        struct.pack_into(">IHH", particles, 0, 0x12345678, 0, 1)
        struct.pack_into(">IHHHh", particles, 8, name_at, 0, 0x0014, 0, 2)
        struct.pack_into(">HH", particles, 8 + 0x1C, 7, 1)  # bone index, one stage
        struct.pack_into(">4I", particles, 8 + 0x20, stages_at, ranges_at, curves_at, keys_at)
        particles[name_at - particles_at:stages_at - particles_at] = name
        struct.pack_into(">Hhh3h", particles, stages_at - particles_at, 0, 0, 10, 64, 0, 0)
        struct.pack_into(">4H", particles, ranges_at - particles_at, 0, 0, 0, 1)
        struct.pack_into(">HBBHHI", particles, curves_at - particles_at, 4, 0, 0, 0, 1, 0)
        struct.pack_into(">Hh", particles, keys_at - particles_at, 0, 255)
        layout.append((13, particles_at, bytes(particles)))
        payload = b"".join(data for _, _, data in layout)
        desc_at = body + len(payload)
        # As on the disc, header word 0 names the last descriptor in the file
        # and each ``next`` points back to the one before it.
        descriptors = b""
        for i, (slot, block_at, _) in enumerate(layout):
            descriptors += struct.pack(">3I", slot, block_at, desc_at + 12 * (i - 1) if i else 0)
        header = struct.pack(">12I", desc_at + 12 * (len(layout) - 1), 0, 0x1000000, 0x11, 0, 0, 0x40, 0, 0x30, 0x30, 0, 0x30)
        report = Report()
        Walker(report).child("rd.ga", header + payload + descriptors)
        totals = report.formats["animation"]
        self.assertEqual(totals.failures, [])
        self.assertEqual(totals.counts[UNCLASSIFIED], 0)
        # Only the emitter's +0x0C word has no identified reader.
        self.assertEqual(totals.counts[UNDECODED], 0, totals.fields)
        self.assertEqual(totals.counts[UNREAD], 2, totals.fields)
        self.assertEqual({name for (status, name) in totals.fields if status == PLAUSIBLE},
                         {"particle curve last key frame", "particle stage local index",
                          "particle emitter local index", "particle emitter first global stage"})


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
    def test_compressed_cp_data_uses_its_phase_four_codec(self):
        from fe_modding.formats import cp_data, lz10

        document = cp_data.CpDocument(
            [cp_data.Section("CP_ATKSEQ_LIST", ["SEQ_TEST", 0]),
             cp_data.Section("SEQ_TEST", [0] * 20)],
            [],
            leading_words=[0, 0],
        )
        compressed = lz10.compress(cp_data.build_cp_data(document))
        report = Report()
        Walker(report).child("Cp/cp_data.cms", compressed)

        self.assertEqual(report.formats["lz10"].failures, [])
        totals = report.formats["cp_data"]
        self.assertEqual(totals.failures, [])
        self.assertEqual(totals.counts[DECODED], len(lz10.decompress(compressed)))
        self.assertEqual(totals.counts[UNCLASSIFIED], 0)
        self.assertNotIn("fe10 container", report.formats)

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


def _u8(files: dict) -> bytes:
    """A U8 archive with one directory holding ``files`` (name -> bytes)."""
    import struct

    names = b"\0" + b"dir\0"
    offsets = []
    for name in files:
        offsets.append(len(names))
        names += name.encode() + b"\0"
    count = 2 + len(files)
    header_size = 12 * count + len(names)
    data_start = (0x20 + header_size + 0x1F) & ~0x1F
    nodes = struct.pack(">III", 0x01000000, 0, count) + struct.pack(">III", 0x01000001, 0, count)
    body, at = b"", data_start
    for (name, blob), name_at in zip(files.items(), offsets):
        nodes += struct.pack(">III", name_at, at, len(blob))
        body += blob + bytes(-len(blob) % 0x20)
        at += len(blob) + (-len(blob) % 0x20)
    head = b"\x55\xaa\x38\x2d" + struct.pack(">III", 0x20, header_size, data_start) + bytes(16)
    table = nodes + names
    return head + table + bytes(data_start - 0x20 - len(table)) + body


class HomeMenuTest(unittest.TestCase):
    def test_u8_members_are_walked(self):
        import struct

        layout = b"RLYT\xfe\xff\x00\x0a" + struct.pack(">IHH", 0x20, 0x10, 1) + b"lyt1" + struct.pack(">I", 0x10) + bytes(8)
        midi = b"MThd" + struct.pack(">I", 6) + bytes(6) + b"MTrk" + struct.pack(">I", 2) + b"\xff\x2f"
        report = Report()
        Walker(report).child("system/HomeButton/test.arc", _u8({"a.brlyt": layout, "b.mid": midi}))
        for fmt in ("u8", "nw4r layout", "midi"):
            self.assertEqual(report.formats[fmt].failures, [], fmt)
            self.assertEqual(report.formats[fmt].counts[UNDECODED] + report.formats[fmt].counts[UNCLASSIFIED], 0, fmt)
        self.assertEqual(report.formats["nw4r layout"].files, 1)
        self.assertEqual(report.formats["midi"].counts[DECODED], len(midi))

    def test_nw4r_section_chain_must_end_at_the_file_size(self):
        import struct

        broken = b"RLAN\xfe\xff\x00\x0a" + struct.pack(">IHH", 0x20, 0x10, 1) + b"pat1" + struct.pack(">I", 0x08) + bytes(8)
        report = Report()
        Walker(report).child("system/HomeButton/x.brlan", broken)
        self.assertEqual(len(report.formats["nw4r layout"].failures), 1)


class Fe10RowsTest(unittest.TestCase):
    def test_unplaced_row_bytes_are_named_by_offset(self):
        from fe_modding.formats.coverage_handlers import _fe10_rows

        cov = FileCoverage(bytes(24), "t", "t")
        layout = {0: (4, "label", ""), 8: (2, UNDECODED, "flags")}
        _fe10_rows(cov, 0, 2, 12, "T", layout)
        fields = cov.open_fields()
        self.assertEqual(fields[(UNDECODED, "T +0x4")], 8)    # bytes 4-7 of both rows
        self.assertEqual(fields[(UNDECODED, "T flags")], 4)   # bytes 8-9 of both rows
        self.assertEqual(fields[(UNDECODED, "T +0xa")], 4)    # bytes 10-11 of both rows
        self.assertEqual(cov.status.count(DECODED), 8)


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
