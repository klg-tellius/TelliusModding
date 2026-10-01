import struct
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fe_modding.formats import gcfesnd


def _build(bgm_names, sfx):
    """sfx: list of (name, flags, volume, pan, sound_id, extra, range)."""
    pool = bytearray()
    offsets = {}

    def intern(text):
        if text not in offsets:
            offsets[text] = len(pool)
            pool.extend(text.encode("ascii") + b"\0")
        return offsets[text]

    records = bytearray()
    for name in bgm_names:
        records += struct.pack(">III", intern(name), (12 << 24) | (6 << 16) | (127 << 8) | 0x40, intern("sound/x"))
    for name, flags, volume, pan, sound_id, extra, rng in sfx:
        records += struct.pack(">IBBBBI4sI", intern(name), 20, flags, volume, pan, sound_id, extra, rng)
    records += b"\0" * 12
    # string offsets are pool-relative to HEADER_SIZE, so lay the pool right after the records
    base = len(records)
    fixed = bytearray()
    pos = 0
    while pos < len(records) - 12:
        length = records[pos + 4]
        fixed += records[pos:pos + 4] and struct.pack(">I", struct.unpack_from(">I", records, pos)[0] + base)
        fixed += records[pos + 4:pos + length]
        if length == 12:
            fixed[-4:] = struct.pack(">I", struct.unpack_from(">I", records, pos + 8)[0] + base)
        pos += length
    fixed += records[-12:]
    return bytes(32) + bytes(fixed) + bytes(pool)


class SfxCueTests(unittest.TestCase):
    def test_reads_sfx_after_bgm_and_stops_at_terminator(self):
        data = _build(["BGM_A", "BGM_B"], [
            ("SFX_SYS_SELECT1", 0, 0x5F, 0x40, 0x70, b"\x1e\0\0\0", 200),
            ("SFX_BTL_HIT1", 8, 0x7D, 0x50, 0x158, b"\0\0\0\0", 2000),
        ])
        cues = gcfesnd.read_sfx_cues(data)
        self.assertEqual([c.name for c in cues], ["SFX_SYS_SELECT1", "SFX_BTL_HIT1"])
        self.assertEqual((cues[0].volume, cues[0].pan, cues[0].sound_id, cues[0].range_value), (0x5F, 0x40, 0x70, 200))
        self.assertEqual(cues[0].extra, b"\x1e\0\0\0")
        self.assertEqual((cues[0].group, cues[1].group), ("SYS", "BTL"))
        self.assertEqual(cues[1].voice_class, 0)
        self.assertEqual(len(gcfesnd.read_bgm_cues(data)), 2)

    def test_unknown_record_length_raises(self):
        data = bytearray(bytes(32) + struct.pack(">IBBBB", 0, 7, 0, 0, 0) + bytes(20))
        with self.assertRaises(gcfesnd.GcfesndError):
            gcfesnd.read_sfx_cues(bytes(data))


if __name__ == "__main__":
    unittest.main()
