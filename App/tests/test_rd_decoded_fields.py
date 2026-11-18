"""Radiant Dawn fields decoded for 1.0: typed record fields, the sound_data tables, FE10Battle's
typed fields and motion sets, and the ``.ga`` compact footer (events, tracks, particles).

The synthetic tests build their own bytes; the disc tests run with ``FE10_EXTRACTED_FILES`` set to
an extracted Radiant Dawn ``files/`` directory."""

import os
import struct
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fe_modding.formats import animation, fe8data, fe10_battle, fe10_battle_fields as bf
from fe_modding.formats import fe10_sound, fe10_sound_tables as st, particle_editor
from fe_modding.formats.common import HEADER_SIZE
from fe_modding.formats.record_fields import BIT, LABEL, Field, FieldError, parse_number, read_numbers, write_numbers

FE10 = os.environ.get("FE10_EXTRACTED_FILES")


# -- record_fields ---------------------------------------------------------------------------------

class RecordFieldTests(unittest.TestCase):
    FIELDS = (Field("a", 0, "u8", "A"), Field("b", 1, "s8", "B"), Field("c", 2, "hex16", "C"),
              Field("d", 4, "f32", "D"), Field("e", 8, BIT, "E", bit=2), Field("n", 12, LABEL, "N"))

    def test_read_write_round_trip_keeps_other_bytes(self):
        raw = bytes(range(16))
        values = read_numbers(raw, 0, self.FIELDS)
        self.assertNotIn("n", values)
        self.assertEqual(write_numbers(raw, 0, self.FIELDS, values), raw)
        out = write_numbers(raw, 0, self.FIELDS, {"a": 200, "b": -3, "c": "BEEF", "e": "no", "n": "ignored"})
        self.assertEqual((out[0], out[1], out[2:4], out[8] & 4), (200, 0xFD, b"\xbe\xef", 0))
        self.assertEqual(out[12:], raw[12:])
        self.assertEqual(out[8] & ~4 & 0xFF, raw[8] & ~4 & 0xFF)

    def test_parse_checks_ranges_and_forms(self):
        self.assertEqual(parse_number(self.FIELDS[0], "7 - seven"), 7)
        self.assertEqual(parse_number(self.FIELDS[4], "yes"), 1)
        for field, value in ((self.FIELDS[0], 256), (self.FIELDS[1], "128"), (self.FIELDS[0], "x"),
                             (self.FIELDS[4], 2)):
            with self.assertRaises(FieldError):
                parse_number(field, value)


# -- sound_data tables -----------------------------------------------------------------------------

def _sound_data() -> bytes:
    """A cue (SFX_A -> res_a) and two tables: SND_SFX_MAYA_DATA (codes 1000, 1002) and
    SND_CHAPTER_GROUP_DATA (one row), with their names in a string pool."""
    pool, strings = bytearray(), {}

    def text(name):
        if name not in strings:
            strings[name] = len(pool)
            pool.extend(name.encode() + b"\0")
        return strings[name]

    for name in ("SFX_A", "res_a", "SFX_B", "C0101", "SND_GROUP_C0101"):
        text(name)
    cue_at, maya_at = 0, 0x24
    group_at = maya_at + 4 + 2 * 8
    pool_at = group_at + 4 + 0x10
    body = bytearray(pool_at)
    struct.pack_into(">II", body, cue_at, pool_at + strings["SFX_A"], pool_at + strings["res_a"])
    struct.pack_into(">BBh", body, cue_at + 8, 2, 100, -12)
    struct.pack_into(">I", body, maya_at, 2)
    struct.pack_into(">IIII", body, maya_at + 4, 1000, pool_at + strings["SFX_A"], 1002, pool_at + strings["SFX_B"])
    struct.pack_into(">I", body, group_at, 1)
    struct.pack_into(">IIBxxxI", body, group_at + 4, pool_at + strings["C0101"], 0, 0,
                     pool_at + strings["SND_GROUP_C0101"])
    body += pool + bytes(-len(pool) % 4)
    pointers = [0, 4, maya_at + 8, maya_at + 16, group_at + 4, group_at + 16]
    symbols = [("SFX_A", cue_at), ("SND_SFX_MAYA_DATA", maya_at), ("SND_CHAPTER_GROUP_DATA", group_at)]
    names = b"".join(n.encode() + b"\0" for n, _ in symbols)
    table, name_at = b"", 0
    for name, offset in symbols:
        table += struct.pack(">II", offset, name_at)
        name_at += len(name) + 1
    tail = struct.pack(f">{len(pointers)}I", *pointers) + table + names
    header = struct.pack(">IIII", HEADER_SIZE + len(body) + len(tail), len(body), len(pointers),
                         len(symbols)) + bytes(16)
    return header + bytes(body) + tail


class SoundTableTests(unittest.TestCase):
    def setUp(self):
        self.data = _sound_data()

    def _pointers_resolve(self, data):
        size = struct.unpack_from(">I", data, 4)[0]
        for field in fe8data.listed_pointer_fields(data):
            self.assertLess(struct.unpack_from(">I", data, field)[0], size)

    def test_reads_cues_and_rows(self):
        self.assertEqual([c.name for c in fe10_sound.read_sound_data(self.data)], ["SFX_A"])
        params = st.cue_parameters(self.data, "SFX_A")
        self.assertEqual((params["kind"], params["volume"], params["pitch"]), (2, 100, -12))
        self.assertEqual(st.read_rows(self.data, "SND_SFX_MAYA_DATA"),
                         [{"code": 1000, "cue": "SFX_A"}, {"code": 1002, "cue": "SFX_B"}])
        self.assertEqual(st.read_rows(self.data, "SND_CHAPTER_GROUP_DATA")[0]["group"], "SND_GROUP_C0101")

    def test_cue_parameters_write_in_place(self):
        out = st.set_cue_parameters(self.data, "SFX_A", volume=80, pitch=-300)
        self.assertEqual(len(out), len(self.data))
        self.assertEqual((st.cue_parameters(out, "SFX_A")["volume"], st.cue_parameters(out, "SFX_A")["pitch"]),
                         (80, -300))
        with self.assertRaises(FieldError):
            st.set_cue_parameters(self.data, "SFX_A", volume=300)

    def test_new_label_goes_to_the_pool(self):
        out = st.set_row(self.data, "SND_CHAPTER_GROUP_DATA", 0, chapter="C0203", flag="FLAG_X")
        row = st.read_rows(out, "SND_CHAPTER_GROUP_DATA")[0]
        self.assertEqual((row["chapter"], row["flag"], row["group"]), ("C0203", "FLAG_X", "SND_GROUP_C0101"))
        self._pointers_resolve(out)

    def test_sorted_table_stays_sorted(self):
        out = st.set_row(self.data, "SND_SFX_MAYA_DATA", 0, code=1005)
        self.assertEqual([r["code"] for r in st.read_rows(out, "SND_SFX_MAYA_DATA")], [1002, 1005])
        out, index = st.add_row(self.data, "SND_SFX_MAYA_DATA", 0)
        self.assertEqual(index, 1)
        self.assertEqual([r["cue"] for r in st.read_rows(out, "SND_SFX_MAYA_DATA")], ["SFX_A", "SFX_A", "SFX_B"])
        self._pointers_resolve(out)

    def test_add_and_remove_rows(self):
        out, index = st.add_row(self.data, "SND_CHAPTER_GROUP_DATA")
        self.assertEqual((index, st.row_count(out, "SND_CHAPTER_GROUP_DATA")), (1, 2))
        out = st.set_row(out, "SND_CHAPTER_GROUP_DATA", 1, chapter="C0102")
        out = st.remove_row(out, "SND_CHAPTER_GROUP_DATA", 0)
        self.assertEqual([r["chapter"] for r in st.read_rows(out, "SND_CHAPTER_GROUP_DATA")], ["C0102"])
        self._pointers_resolve(out)
        self.assertEqual([c.name for c in fe10_sound.read_sound_data(out)], ["SFX_A"])
        with self.assertRaises(st.SoundTableError):
            st.remove_row(out, "SND_CHAPTER_GROUP_DATA", 0)

    def test_missing_table_is_a_clear_error(self):
        with self.assertRaises(st.SoundTableError):
            st.read_rows(self.data, "SND_ENV_DATA")


# -- FE10Battle fields -------------------------------------------------------------------------------

class BattleFieldTests(unittest.TestCase):
    def test_fields_do_not_overlap(self):
        for table, fields in bf.FIELDS.items():
            used = {}
            for f in fields:
                for at in range(f.offset, f.offset + f.size):
                    other = used.get(at)
                    if other is not None:
                        self.assertTrue(f.kind == BIT and other.kind == BIT and f.bit != other.bit,
                                        f"{table}: {f.key} overlaps {other.key}")
                    used[at] = f

    def test_unit_motion_bits(self):
        raw = bytearray(0x150)
        struct.pack_into(">4I", raw, bf.MOTIONS_OFFSET + 16 * 3, 0x80000001, 0, 0, 0x2)
        record = fe10_battle.BattleRecord(0, bytes(raw), ())
        motions = bf.unit_motions(record)
        self.assertEqual(len(motions), bf.WEAPON_TYPES)
        self.assertEqual(motions[3], {0, 31, 97})
        self.assertTrue(all(not m for i, m in enumerate(motions) if i != 3))


# -- the Radiant Dawn .ga compact footer -------------------------------------------------------------

def _rd_animation() -> bytes:
    """A two-key animation with a Radiant Dawn header (byte 8 = 1) and no footer yet."""
    header = animation.GaHeader(words=(0, 0, 0x01000000, 0x11, 0, 1, 10, 0, 0, 0, 0, 0))
    curves = [animation.AnimCurve(0, 3, 4, 10, [animation.Keyframe(0, 0), animation.Keyframe(5, 8),
                                                animation.Keyframe(10, 16)])]
    data = animation.write_animation(animation.GaAnimation(header, [animation.BoneGroup(0, 16, 0, 1)], curves))
    return data


EVENTS = [animation.Fe10EventKey(2, ((1000, 0),)), animation.Fe10EventKey(7, ((0x1F, -1), (22, 3)))]


class Fe10FooterTests(unittest.TestCase):
    def test_event_block_round_trip(self):
        block = animation.write_fe10_event_block(EVENTS)
        self.assertEqual(animation.read_fe10_event_block(block), EVENTS)
        one = animation.write_fe10_event_block(EVENTS[:1])
        self.assertEqual(struct.unpack_from(">H", one, 8)[0], 10)  # keys follow the offsets, unaligned
        with self.assertRaises(animation.AnimationError):
            animation.write_fe10_event_block(EVENTS[::-1])

    def test_set_block_appends_and_links(self):
        data = _rd_animation()
        self.assertTrue(animation.is_fe10_animation(data))
        out = animation.fe10_set_footer_block(data, animation.FE10_EVENT_SLOT,
                                              animation.write_fe10_event_block(EVENTS))
        self.assertEqual(out[:len(data)][4:], data[4:])  # only header word 0 changed before the end
        self.assertEqual(animation.fe10_events(out), EVENTS)
        self.assertEqual(particle_editor.read_events(out), EVENTS)
        alpha = bytes(range(8))
        both = animation.fe10_set_footer_block(out, 6, alpha)
        self.assertEqual(animation.footer_block(both, 6), alpha)
        self.assertEqual(animation.fe10_events(both), EVENTS)
        replaced = animation.fe10_set_footer_block(both, animation.FE10_EVENT_SLOT,
                                                   animation.write_fe10_event_block(EVENTS[:1]))
        self.assertEqual(animation.fe10_events(replaced), EVENTS[:1])
        removed = animation.fe10_set_footer_block(replaced, animation.FE10_EVENT_SLOT, None)
        self.assertEqual(animation.fe10_events(removed), [])
        self.assertEqual(animation.footer_block(removed, 6), alpha)

    def test_write_animation_moves_the_footer_with_the_keyframes(self):
        out = animation.fe10_set_footer_block(_rd_animation(), animation.FE10_EVENT_SLOT,
                                              animation.write_fe10_event_block(EVENTS))
        out = animation.fe10_set_footer_block(out, 6, bytes(range(8)))
        anim = animation.read_animation_bytes(out)
        self.assertIsNotNone(anim.fe10_region_start)
        self.assertEqual(animation.write_animation(anim), out)
        curve = anim.curves[0]
        shorter = animation.GaAnimation(anim.header, anim.groups,
                                        [animation.AnimCurve(curve.channel, curve.scale_shift, curve.end_frame,
                                                             curve.end_frame, curve.keyframes[::2])],
                                        anim.events, anim.footer, anim.body_trailing, anim.fe10_region_start)
        moved = animation.write_animation(shorter)
        self.assertEqual(len(moved), len(out) - 4)
        self.assertEqual(animation.fe10_events(moved), EVENTS)
        self.assertEqual(animation.footer_block(moved, 6), bytes(range(8)))

    def test_rd_particle_table_in_slot_13(self):
        from tests.test_particle_editor import sample_ga
        data = bytearray(sample_ga())
        block = 0x30 + 40
        data[8] = 1
        data += struct.pack(">3I", animation.FE10_PARTICLE_SLOT, block, 0)
        struct.pack_into(">I", data, 0, len(data) - 12)
        data = bytes(data)
        layout = animation.read_particle_table_layout(data)
        self.assertEqual(len(layout.emitters), 1)
        out = particle_editor.duplicate_emitter(data, 0)
        self.assertEqual(len(animation.read_particle_table_layout(out).emitters), 2)
        self.assertIn(animation.FE10_PARTICLE_SLOT, animation.fe10_footer_blocks(out))
        out = particle_editor.replace_events(out, EVENTS)
        self.assertEqual(particle_editor.read_events(out), EVENTS)
        self.assertEqual(len(animation.read_particle_table_layout(out).emitters), 2)


# -- the pages -----------------------------------------------------------------------------------------

class PageTests(unittest.TestCase):
    def test_sound_tables_page_is_registered(self):
        from fe_modding.gui.fe10_sound_tables_editor import Fe10SoundTablesEditor
        from fe_modding.gui.pages.assets import ASSET_FILES, TOOLS_BY_KEY
        self.assertIs(TOOLS_BY_KEY["sound_tables"][4], Fe10SoundTablesEditor)
        self.assertEqual(ASSET_FILES["sound_tables"], "sound_data")

    def test_sound_tables_page_tabs(self):
        from fe_modding.gui.fe10_sound_tables_editor import Fe10SoundTablesEditor
        data = _sound_data()
        tabs = Fe10SoundTablesEditor.tabs(object.__new__(Fe10SoundTablesEditor), data)
        self.assertEqual([t.key for t in tabs], ["cues", "SND_SFX_MAYA_DATA", "SND_CHAPTER_GROUP_DATA"])
        cues = tabs[0]
        self.assertEqual(cues.read(data)[0]["volume"], 100)
        out = cues.write(data, 0, {"volume": 90})
        self.assertEqual(st.cue_parameters(out, "SFX_A")["volume"], 90)


class SoundTablesPanelTests(unittest.TestCase):
    """The page itself on a stand-in project: select a row, edit it, save."""

    def setUp(self):
        import tkinter as tk
        try:
            self.root = tk.Tk()
        except tk.TclError as exc:
            self.skipTest(f"no display: {exc}")
        self.root.withdraw()
        self.addCleanup(self.root.destroy)

    def test_edit_and_save(self):
        from types import SimpleNamespace
        from fe_modding.gui.changelog import ChangeLog
        from fe_modding.gui.fe10_sound_tables_editor import Fe10SoundTablesEditor
        saved = {}
        project = SimpleNamespace(read_logical=lambda name: _sound_data(),
                                  write_logical=lambda name, data: saved.__setitem__(name, data),
                                  profile=SimpleNamespace(file_label=lambda name: name))
        page = Fe10SoundTablesEditor(self.root, project, ChangeLog())
        tab = next(t for t in page._tabs if t.key == "SND_CHAPTER_GROUP_DATA")
        page._trees[tab.key].selection_set("0")
        page._on_select(tab)
        page._vars["chapter"].set("C0304")
        page._apply(tab, 0)
        self.assertTrue(page.save())
        self.assertEqual(st.read_rows(saved["sound_data"], "SND_CHAPTER_GROUP_DATA")[0]["chapter"], "C0304")


@unittest.skipUnless(FE10, "set FE10_EXTRACTED_FILES to an extracted Radiant Dawn files/ directory")
class DiscTests(unittest.TestCase):
    def test_battle_fields_round_trip(self):
        from fe_modding.formats import lz10
        data = lz10.decompress((Path(FE10) / "FE10Battle.cms").read_bytes())
        for table in bf.FIELDS:
            rows = bf.read_rows(data, table)
            if rows:
                self.assertEqual(bf.set_row(data, table, 0, **rows[0]), data, table)
        unit = fe10_battle.read_fe10_battle(data).table("FE10BUnit").records[0]
        motions = bf.unit_motions(unit)
        self.assertEqual(bf.set_unit_motions(data, 0, motions), data)
        motions[0] = set(motions[0]) ^ {5}
        out = bf.set_unit_motions(data, 0, motions)
        self.assertEqual(bf.unit_motions(fe10_battle.read_fe10_battle(out).table("FE10BUnit").records[0]), motions)

    def test_sound_tables_read(self):
        from fe_modding.formats import lz10
        path = Path(FE10) / "Sound" / "sound_data_en.cms"
        if not path.exists():
            self.skipTest("no sound_data_en.cms")
        raw = path.read_bytes()
        data = lz10.decompress(raw) if raw[:1] == b"\x10" else raw
        self.assertGreater(st.row_count(data, "SND_MAP_BGM_DATA"), 50)
        codes = [r["code"] for r in st.read_rows(data, "SND_SFX_MAYA_DATA")]
        self.assertEqual(codes, sorted(codes))


if __name__ == "__main__":
    unittest.main()
