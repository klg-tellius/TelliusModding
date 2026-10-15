import io
import struct
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fe_modding.formats import stm


class StmBlockTests(unittest.TestCase):
    def _write(self, count, loop_start=None):
        ramp = [(i * 37) % 2000 - 1000 for i in range(count)]
        data = stm.write_stm(stm.StmAudio(sample_rate=32000, channels=[ramp, ramp], loop_start=loop_start))
        return data, stm.read_stm(io.BytesIO(data))

    def test_channel_size_is_whole_blocks(self):
        for count in (1000, 5600, 4321):
            data, _ = self._write(count)
            self.assertEqual(struct.unpack_from(">I", data, 8)[0] % 32, 0, count)

    def test_one_shot_padded_with_silence(self):
        _, back = self._write(1000)
        self.assertEqual(len(back.channels[0]), 1008)
        self.assertTrue(all(abs(v) < 64 for v in back.channels[0][1000:]))

    def test_loop_kept(self):
        _, back = self._write(4321, loop_start=100)
        self.assertEqual(back.loop_start, 100)
        self.assertEqual(len(back.channels[0]) % stm.SAMPLES_PER_BLOCK, 0)


if __name__ == "__main__":
    unittest.main()
