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
    pool = struct.pack(">4I", 0x10, 0, 0, 0x10 + len(macros)) + macros
    # one ADPCM frame (14 samples): predictor 0, scale 2^1, every nibble +1
    frame = bytes([0x01]) + bytes([0x11] * 7)
    info = bytes(8) + struct.pack(">16h", *([0x800, 0] + [0] * 14))
    record = struct.pack(">HHIIIIIII", 3, 0, 0, 0, (60 << 24) | 32000, 14, 0, 0, SDIR_INFO_OFFSET)
    sdir = record + info
    # FX group 1: fx id 7 -> macro 5 (with the 0x8000 flag set)
    table = struct.pack(">HH", 1, 0) + struct.pack(">HH6B", 7, 0x8000 | 5, 1, 10, 127, 64, 60, 0)
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
