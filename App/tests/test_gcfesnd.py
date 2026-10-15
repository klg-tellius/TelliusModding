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


def _container(bgm, sfx_names, outside=None):
    """A gcfesnd.bin with its header and relocation table: bgm is a list of
    (name, path); ``outside`` repoints the last BGM cue at a string appended
    after the tables, as earlier app versions did."""
    strings = sorted({s for pair in bgm for s in pair} | set(sfx_names))
    count = len(bgm) + len(sfx_names)
    records_size = 12 * len(bgm) + 20 * len(sfx_names) + 12
    pool, offsets = bytearray(), {}
    for text in strings:
        offsets[text] = records_size + len(pool)
        pool += text.encode("ascii") + b"\0"
        pool += bytes(-len(pool) % 4)
    body, relocs = bytearray(), []
    for name, path in bgm:
        relocs += [len(body), len(body) + 8]
        body += struct.pack(">III", offsets[name], (12 << 24) | (6 << 16) | (127 << 8) | 0x40, offsets[path])
    for name in sfx_names:
        relocs.append(len(body))
        body += struct.pack(">IBBBBI4sI", offsets[name], 20, 0, 100, 64, 7, b"\x1e\0\0\0", 100)
    body += bytes(12) + pool
    assert count and len(body) == records_size + len(pool)
    tail = struct.pack(f">{len(relocs)}I", *relocs)
    data = bytearray(struct.pack(">8I", 32 + len(body) + len(tail), len(body), len(relocs), 0, 0, 0, 0, 0))
    data += body + tail
    if outside:
        struct.pack_into(">I", data, 32 + 12 * (len(bgm) - 1) + 8, len(data) - 32)
        data += outside.encode("ascii") + b"\0"
        struct.pack_into(">I", data, 0, len(data))
    return bytes(data)


class BgmCueTests(unittest.TestCase):
    def setUp(self):
        self.data = _container([("BGM_A", "sound/a_32k"), ("BGM_DUMMY_1", "sound/fe_dummy_32k")], ["SFX_X"])

    def test_add_and_remove(self):
        data = gcfesnd.add_bgm_cue(self.data, "BGM_NEW", "sound/new_32k")
        cues = gcfesnd.read_bgm_cues(data)
        self.assertEqual([(c.name, c.path) for c in cues],
                         [("BGM_A", "sound/a_32k"), ("BGM_DUMMY_1", "sound/fe_dummy_32k"), ("BGM_NEW", "sound/new_32k")])
        self.assertEqual(cues[-1].control_word >> 16, (12 << 8) | 6)
        self.assertEqual([c.name for c in gcfesnd.read_sfx_cues(data)], ["SFX_X"])
        self.assertEqual(gcfesnd.remove_bgm_cue(data, "BGM_NEW"), self.data)

    def test_add_after_added_sfx(self):
        data = gcfesnd.add_sfx_cue(self.data, "SFX_Y", flags=0, volume=1, pan=2, sound_id=3,
                                   extra=b"\0\0\0\0", range_value=4)
        data = gcfesnd.add_bgm_cue(data, "BGM_NEW", "sound/new_32k")
        self.assertEqual(gcfesnd.read_bgm_cues(data)[-1].path, "sound/new_32k")
        self.assertEqual([c.name for c in gcfesnd.read_sfx_cues(data)], ["SFX_X", "SFX_Y"])

    def test_refusals(self):
        for name, path in (("BGM_A", "sound/x"), ("MUSIC", "sound/x"), ("BGM_X", "x"), ("BGM_X", "sound/x.stm")):
            with self.assertRaises(gcfesnd.GcfesndError):
                gcfesnd.add_bgm_cue(self.data, name, path)

    def test_string_outside_the_tables_is_kept(self):
        data = _container([("BGM_A", "sound/a_32k"), ("BGM_DUMMY_1", "sound/fe_dummy_32k")], ["SFX_X"],
                          outside="sound/old_32k")
        self.assertEqual(gcfesnd.read_bgm_cues(data)[1].path, "sound/old_32k")
        data = gcfesnd.add_bgm_cue(data, "BGM_NEW", "sound/new_32k")
        self.assertEqual([c.path for c in gcfesnd.read_bgm_cues(data)], ["sound/a_32k", "sound/old_32k", "sound/new_32k"])

    def test_repoint_writes_inside_the_pool(self):
        cue = gcfesnd.find_cue(gcfesnd.read_bgm_cues(self.data), "BGM_DUMMY_1")
        data = gcfesnd.repoint_bgm_cue(self.data, cue, "sound/mine_32k")
        cues = gcfesnd.read_bgm_cues(data)
        self.assertEqual(cues[1].path, "sound/mine_32k")
        self.assertLess(cues[1].path_offset, struct.unpack_from(">I", data, 4)[0])
        data = gcfesnd.add_bgm_cue(data, "BGM_NEW", "sound/new_32k")
        self.assertEqual(gcfesnd.read_bgm_cues(data)[1].path, "sound/mine_32k")


if __name__ == "__main__":
    unittest.main()
