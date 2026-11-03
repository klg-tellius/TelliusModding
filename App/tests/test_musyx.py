import struct
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fe_modding.formats import musyx


def _macro(macro_id, commands):
    body = b"".join(struct.pack(">II", w0, w1) for w0, w1 in commands)
    return struct.pack(">IHH", 8 + len(body), macro_id, 0) + body


def _write_bank(directory: Path, name: str) -> None:
    # macro 5 plays macro 9, which starts sample 3
    macros = _macro(5, [(0x08 | (9 << 8), 0), (0, 0)]) + _macro(9, [(0x38, 0), (0x10 | (3 << 8), 0), (0, 0)])
    # layer 0x8001: macro 9 twice, panned left and right, the right one a fifth up for keys 0-127
    entry = lambda macro, transpose, pan: struct.pack(">HBBbBbBB3x", macro, 0, 127, transpose, 127, 0, 0, pan)
    layers = struct.pack(">IHHI", 12 + 24, 0x8001, 0, 2) + entry(9, 0, 0) + entry(9, 7, 127) + bytes([0xFF] * 4)
    pool = struct.pack(">4I", 0x10, 0, 0, 0x10 + len(macros)) + macros + layers
    # one ADPCM frame (14 samples): predictor 0, scale 2^1, every nibble +1
    frame = bytes([0x01]) + bytes([0x11] * 7)
    info = bytes(8) + struct.pack(">16h", *([0x800, 0] + [0] * 14))
    record = struct.pack(">HHIIIIIII", 3, 0, 0, 0, (60 << 24) | 32000, 14, 0, 0, SDIR_INFO_OFFSET)
    sdir = record + info
    # FX group 1: fx id 7 -> macro 5, fx id 8 -> layer 0x8001
    table = (struct.pack(">HH", 2, 0) + struct.pack(">HH6B", 7, 5, 1, 10, 127, 64, 60, 0)
             + struct.pack(">HH6B", 8, 0x8001, 1, 10, 127, 64, 60, 0))
    header = struct.pack(">IHH8I", 0x28 + len(table), 1, 1, 0, 0, 0, 0, 0, 0x28, 0, 0)
    (directory / f"{name}.proj").write_bytes(header + table)
    (directory / f"{name}.pool").write_bytes(pool)
    (directory / f"{name}.sdir").write_bytes(sdir)
    (directory / f"{name}.samp").write_bytes(frame)


SDIR_INFO_OFFSET = musyx.SDIR_RECORD_SIZE


class MusyxTests(unittest.TestCase):
    def test_resolves_fx_id_through_play_macro_and_decodes(self):
        with tempfile.TemporaryDirectory() as tmp:
            _write_bank(Path(tmp), "gcfesnd")
            banks = musyx.SoundBanks(tmp)
            bank, sample_id = banks.resolve(7)
            self.assertEqual((bank.name, sample_id), ("gcfesnd", 3))
            sfx = banks.render(7)
            self.assertEqual(sfx.sample_rate, 32000)
            self.assertEqual(len(sfx.samples), 14)
            self.assertTrue(all(v > 0 for v in sfx.samples))

    def test_layer_plays_every_entry(self):
        with tempfile.TemporaryDirectory() as tmp:
            _write_bank(Path(tmp), "gcfesnd")
            banks = musyx.SoundBanks(tmp)
            self.assertEqual([(v[1], v[2]) for v in banks.voices(0x8001, 60)], [(3, 60), (3, 67)])
            self.assertIsNone(banks.voice_for_macro(0x8001, 60))      # not macro 1
            self.assertEqual(banks.resolve(8)[1], 3)
            self.assertEqual(len(banks.render(8).samples), 14)          # the longer, unshifted voice

    def test_timed_wait_before_the_sample_delays_it(self):
        # wait 600 ms, then a wait-until-sample-end (byte 3 set) that must not count
        macro = _macro(1, [(0x07, 600 << 16), (0x10 | (3 << 8), 0), (0x01000107, 0xFFFF0000), (0, 0)])
        pool = struct.pack(">4I", 0x10, 0, 0, 0x10 + len(macro)) + macro
        bank = musyx.Bank("b", pool, struct.pack(">H", 0xFFFF), Path("unused"))
        self.assertEqual(bank.start_delay_ms(1), 600)

    def test_random_key_plays_the_middle_of_its_range(self):
        # random key 46..49 (bytes 1 and 3), then start sample 3
        macro = _macro(1, [(0x17 | (46 << 8) | (49 << 24), 1), (0x10 | (3 << 8), 0), (0, 0)])
        pool = struct.pack(">4I", 0x10, 0, 0, 0x10 + len(macro)) + macro
        bank = musyx.Bank("b", pool, struct.pack(">H", 0xFFFF), Path("unused"))
        self.assertEqual(bank.first_voice(1, 60), (3, 48))

    def test_unknown_sound_id(self):
        with tempfile.TemporaryDirectory() as tmp:
            _write_bank(Path(tmp), "gcfesnd")
            banks = musyx.SoundBanks(tmp)
            self.assertIsNone(banks.resolve(77))
            with self.assertRaises(musyx.MusyxError):
                banks.render(77)

    def test_missing_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(musyx.MusyxError):
                musyx.SoundBanks(tmp)


if __name__ == "__main__":
    unittest.main()
