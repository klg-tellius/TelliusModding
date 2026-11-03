import struct
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fe_modding.formats import musyx_song


def _song_blob() -> bytes:
    """One track on MIDI channel 0: pattern 0 at tick 0 (program change, then
    a note 10 ticks in), pattern 1 at tick 100 looping back to entry 1."""
    pattern0 = struct.pack(">III", 8, 0, 0) + struct.pack(">HBB", 0, 0x85, 0) \
        + struct.pack(">HBBH", 10, 60, 100, 48) + struct.pack(">HBB", 0, 0xFF, 0xFF)
    body = bytearray(0x18)
    track_table = len(body)
    body += bytes(4 * 64)
    pattern_table = len(body)
    body += bytes(4)
    channel_table = len(body)
    body += bytes([0xFF, 0] + [0xFF] * 62)
    track = len(body)
    body += struct.pack(">IBBHHbb", 0, 0xFF, 0xFF, 0, 0, 2, 0)
    body += struct.pack(">IBBHHbb", 480, 0xFF, 0xFF, 0, 0xFFFE, 0, 0)[:10] + struct.pack(">H", 0) + b"\0\0"
    pattern = len(body)
    body += pattern0
    struct.pack_into(">I", body, track_table + 4, track)
    struct.pack_into(">I", body, pattern_table, pattern)
    struct.pack_into(">6I", body, 0, track_table, pattern_table, channel_table, 0, 120, 0)
    return struct.pack(">I", 0x20 + len(body)) + b"\xff" * 28 + bytes(body)


class MusyxSongTests(unittest.TestCase):
    def test_split_and_parse(self):
        data = _song_blob() * 2
        blobs = musyx_song.split_slib(data)
        self.assertEqual(len(blobs), 2)
        song = musyx_song.parse_song(data, *blobs[1])
        self.assertEqual(song.bpm, 120)
        self.assertEqual(len(song.tracks[1]), 2)
        timeline = musyx_song.build_timeline(song)
        self.assertEqual(len(timeline.notes), 1)
        note = timeline.notes[0]
        self.assertEqual((note.tick, note.key, note.velocity, note.length), (10, 62, 100, 48))
        self.assertIn((0, 0, 0, 5), timeline.controllers)
        self.assertEqual(timeline.end_tick, 480)

    def test_tempo_map(self):
        tempo = musyx_song.TempoMap([(0, 120), (384, 60)])
        self.assertAlmostEqual(tempo.seconds(384), 0.5)
        self.assertAlmostEqual(tempo.seconds(768), 1.5)


if __name__ == "__main__":
    unittest.main()
