import os
import struct
import unittest
from pathlib import Path

from fe_modding.formats import soundroom
from fe_modding.formats.soundroom import SoundRoomEntry


class SoundRoomTests(unittest.TestCase):
    def test_build_then_read_keeps_every_entry(self):
        entries = [SoundRoomEntry("RID_塔", 0, -250), SoundRoomEntry("RID_決意"), SoundRoomEntry("RID_塔", -40, 7)]
        data = soundroom.build_soundroom(entries)
        self.assertEqual(soundroom.read_soundroom(data), entries)
        size, data_size, pointers, symbols = struct.unpack_from(">4I", data, 0)
        self.assertEqual((size, pointers, symbols), (len(data), 3, 0))
        self.assertEqual(data_size % 4, 0)
        # the shared name is pooled once
        self.assertEqual(data.count("RID_塔".encode("shift_jis")), 1)

    def test_rejects_empty_and_out_of_range(self):
        with self.assertRaises(soundroom.SoundRoomError):
            soundroom.build_soundroom([])
        with self.assertRaises(soundroom.SoundRoomError):
            soundroom.build_soundroom([SoundRoomEntry("RID_塔", 0x8000, 0)])

    def test_rejects_bad_header(self):
        data = bytearray(soundroom.build_soundroom([SoundRoomEntry("RID_塔")]))
        data[3] ^= 1
        with self.assertRaises(soundroom.SoundRoomError):
            soundroom.read_soundroom(bytes(data))


@unittest.skipUnless(os.environ.get("FE9_EXTRACTED_FILES"), "set FE9_EXTRACTED_FILES to an extracted files/ directory")
class VanillaSoundRoomTests(unittest.TestCase):
    def test_vanilla_round_trip_and_names_exist_in_rect_bin(self):
        from fe_modding.formats import rect

        root = Path(os.environ["FE9_EXTRACTED_FILES"])
        data = (root / "soundroom.bin").read_bytes()
        entries = soundroom.read_soundroom(data)
        self.assertEqual(len(entries), 21)
        self.assertEqual(soundroom.build_soundroom(entries), data)
        rects = rect.read_rect_file(root / "s" / "rect.bin")
        for entry in entries:
            self.assertIsNotNone(rects.find(entry.name), entry.name)


if __name__ == "__main__":
    unittest.main()
