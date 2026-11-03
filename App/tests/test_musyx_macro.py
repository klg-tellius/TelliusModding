import struct
import sys
import unittest
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fe_modding.formats import musyx, musyx_macro, musyx_song

# Opcodes with their own case in the game's jump table (0x8029F430); every
# other value of the low 7 bits goes to the "next command" default.
GAME_CASES = (set(range(0x00, 0x26)) | set(range(0x28, 0x2D)) | set(range(0x30, 0x3A)) | set(range(0x40, 0x4F))
              | {0x50, 0x58, 0x59, 0x5A, 0x5E, 0x5F} | set(range(0x60, 0x66)) | {0x70, 0x71})


def _cmd(word0: int, word1: int) -> musyx_macro.Command:
    return musyx_macro.decode(word0, word1)


class MacroCommandTests(unittest.TestCase):
    def test_every_game_case_has_a_spec(self):
        self.assertEqual(set(musyx_macro.SPECS), GAME_CASES)

    def test_fields_of_shipped_commands(self):
        self.assertEqual(_cmd(0x0100F418, 0x00000100).fields,
                         {"add": -12, "detune": 0, "from_original": 1, "time": 0, "in_ms": 1})
        self.assertEqual(_cmd(0x3F003C17, 0x00000001).fields,
                         {"low": 60, "high": 63, "detune": 0, "relative": 0, "random_detune": 1})
        wait = _cmd(0x01000107, 0xFFFF0000)
        self.assertEqual((wait.name, wait.fields["key_release"], wait.fields["sample_end"], wait.fields["time"]),
                         ("wait_ms", 1, 1, 0xFFFF))
        self.assertEqual(_cmd(0x00000070, 0x00420015).fields,
                         {"a_ctrl": 0, "a": 0, "b_ctrl": 0, "b": 21, "invert": 0, "step": 0x42})
        self.assertEqual(_cmd(0x00150064, 0x00000115).fields,
                         {"dest_ctrl": 0, "dest": 0x15, "a_ctrl": 0, "a": 0x15, "value": 1})
        self.assertEqual(_cmd(0x00000065, 0x0000FFF6).fields["value"], -10)
        pan = _cmd(0xFF9C7E41, 0x00000001)
        self.assertEqual((pan.name, pan.fields["controller"], pan.fields["scale_percent"], pan.fields["combine"]),
                         ("panning_select", 126, -100, 1))
        self.assertEqual(_cmd(0x00641E42, 0x00000100).fields["from_variable"], 1)
        self.assertEqual(_cmd(0x006E5013, 0x00000009).fields, {"threshold": 0x50, "macro": 0x6E, "step": 9})
        self.assertEqual(_cmd(0x00032B10, 0).fields["sample"], 811)
        self.assertEqual(_cmd(0x0000020C, 0).fields, {"table": 2, "dls": 0})

    def test_unknown_opcode_and_high_bit(self):
        unknown = _cmd(0x00000026, 0)
        self.assertFalse(unknown.known)
        self.assertEqual(unknown.name, "op_26")
        self.assertEqual(_cmd(0x00000086, 0).name, "goto")  # the interpreter masks bit 7

    def test_curve_tables_are_little_endian_adsr(self):
        curve = struct.pack(">IHH", 16, 1, 0) + struct.pack("<4H", 500, 1000, 0x1000, 1003)
        pool = struct.pack(">4I", 0, 0x10, 0, 0) + curve + b"\xFF" * 4
        tables = musyx_macro.parse_curve_tables(pool)
        adsr = musyx_macro.adsr_table(1, tables[1])
        self.assertEqual((adsr.attack_ms, adsr.decay_ms, adsr.release_ms), (500, 1000, 1003))
        self.assertEqual(adsr.sustain_level, 1.0)

    def test_id_list_ranges(self):
        data = struct.pack(">6H", 0x8001, 0x0004, 0x0009, 0x800B, 0x000C, 0xFFFF)
        self.assertEqual(musyx_macro.parse_id_list(data, 0), [1, 2, 3, 4, 9, 11, 12])
        self.assertEqual(musyx_macro.id_list_size(data, 0), 12)


class MacroPlaybackTests(unittest.TestCase):
    def _bank(self, commands: list[tuple[int, int]]) -> musyx.Bank:
        body = b"".join(struct.pack(">II", *c) for c in commands)
        curve = struct.pack(">IHH", 16, 2, 0) + struct.pack("<4H", 10, 0, 0x1000, 20)
        macros = struct.pack(">IHH", 8 + len(body), 1, 0) + body + b"\xFF" * 4
        pool = struct.pack(">4I", 0x10, 0x10 + len(macros), 0, 0) + macros + curve + b"\xFF" * 4
        return musyx.Bank("test", pool, b"\xFF\xFF\0\0", Path("unused"))

    def test_adsr_and_pitch_wheel_range_before_the_sample(self):
        bank = self._bank([(0x0000020C, 0), (0x000C0833, 0), (0x00000310, 0), (0x0000010C, 0), (0, 0)])
        self.assertEqual(bank.adsr_table_id(1), 2)
        self.assertEqual(bank.pitch_wheel_range(1), (8, 12))
        self.assertEqual(bank.adsr[2].release_ms, 20)

    def test_defaults_without_commands(self):
        bank = self._bank([(0x00000310, 0), (0, 0)])
        self.assertIsNone(bank.adsr_table_id(1))
        self.assertEqual(bank.pitch_wheel_range(1), (2, 2))

    def test_apply_adsr(self):
        table = musyx_macro.AdsrTable(0, attack_ms=10, decay_ms=0, sustain=0x1000, release_ms=5)
        out = musyx.apply_adsr(np.ones(1000, np.float32), 32000, table, key_off=True)
        self.assertAlmostEqual(float(out[0]), 0.0)
        self.assertAlmostEqual(float(out[160]), 0.5, places=2)   # 5 ms into a 10 ms attack
        self.assertAlmostEqual(float(out[500]), 1.0)
        self.assertAlmostEqual(float(out[-1]), 0.0)              # released at the end
        no_sustain = musyx_macro.AdsrTable(0, attack_ms=0, decay_ms=10, sustain=0, release_ms=0)
        self.assertEqual(len(musyx.apply_adsr(np.ones(1000, np.float32), 32000, no_sustain, key_off=False)), 320)


class StreamTests(unittest.TestCase):
    def test_decode_pitch_bend_stream(self):
        data = bytes([0x00, 0x81, 0x00, 0x0C, 0x06, 0x80, 0x10, 0x7F, 0x00, 0xC0, 0x00, 0x80, 0x00])
        events = musyx_song.decode_stream(data, 0, len(data))
        self.assertEqual(events, [(0, 256), (12, 6), (16, -1), (0, -16384)])
        self.assertEqual(musyx_song.stream_size(data, 0, len(data)), len(data))
        self.assertEqual(musyx_song.stream_values(events[:2], 0x2000), [(0, 0x2100), (12, 0x2106)])


class RealBankTests(unittest.TestCase):
    """Optional: set FE9_EXTRACTED_FILES to an extracted US files/ folder."""

    def setUp(self):
        import os
        root = os.environ.get("FE9_EXTRACTED_FILES")
        if not root or not (Path(root) / "Sound" / "gcfesnd.pool").exists():
            self.skipTest("FE9_EXTRACTED_FILES not set")
        self.sound = Path(root) / "Sound"

    def test_every_shipped_command_is_known(self):
        for pool_path in self.sound.glob("*.pool"):
            pool = pool_path.read_bytes()
            pos = struct.unpack_from(">I", pool, 0)[0]
            while (size := struct.unpack_from(">I", pool, pos)[0]) != 0xFFFFFFFF:
                for command in musyx_macro.disassemble(musyx_macro.read_commands(pool, pos, size)):
                    self.assertTrue(command.known, f"{pool_path.name}: {command}")
                pos += size

    def test_adpcm_info_header(self):
        for sdir_path in self.sound.glob("*.sdir"):
            sdir, samp = sdir_path.read_bytes(), sdir_path.with_suffix(".samp").read_bytes()
            pos = 0
            while struct.unpack_from(">H", sdir, pos)[0] != 0xFFFF:
                _id, _r, offset, _p, _kr, fmt_count, *_rest, info = struct.unpack_from(">HHIIIIIII", sdir, pos)
                count, initial_ps = struct.unpack_from(">HB", sdir, info)
                self.assertEqual((count, fmt_count >> 24, initial_ps), (8, 0, samp[offset]))
                pos += 32

    def test_every_pitch_bend_stream_ends(self):
        data = (self.sound / "gcfesnd.slib").read_bytes()
        streams = 0
        for blob, size in musyx_song.split_slib(data):
            song = musyx_song.parse_song(data, blob, size)
            streams += sum(1 for bends in song.bends if bends)
        self.assertGreater(streams, 100)


if __name__ == "__main__":
    unittest.main()
