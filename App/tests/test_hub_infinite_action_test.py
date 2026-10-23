import struct
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

import build_hub_infinite_action_test as patch
from fe_modding.game_code import ppc


class HubInfiniteActionPlaytestTests(unittest.TestCase):
    def test_stubs_clear_in_hub_and_keep_vanilla_fallback(self):
        for origin, actor, return_address in (
            (patch.NORMAL_STUB, 3, patch.NORMAL_RETURN),
            (patch.ASYNC_STUB, 5, patch.ASYNC_RETURN),
        ):
            data = patch._chapter_guarded_store(origin, actor, return_address)
            words = struct.unpack(f">{len(data) // 4}I", data)
            self.assertIn(patch.CLEAR_ACTED_R0, words)
            self.assertIn(patch.SET_ACTED_R0, words)
            self.assertIn(ppc.stw(0, 0x1A0, actor), words)
            self.assertEqual(words[-1], ppc.b(origin + len(data) - 4, return_address))

    def test_async_stub_preserves_r5_actor_pointer(self):
        data = patch._chapter_guarded_store(patch.ASYNC_STUB, 5, patch.ASYNC_RETURN)
        words = struct.unpack(f">{len(data) // 4}I", data)
        before_store = words[:words.index(ppc.stw(0, 0x1A0, 5))]
        self.assertNotIn(ppc.lis(5, (patch.HUB_CONFIG >> 16) & 0xFFFF), before_store)
        self.assertNotIn(ppc.lbz(5, patch.HUB_CONFIG & 0xFFFF, 5), before_store)
        self.assertIn(ppc.lis(6, (patch.HUB_CONFIG >> 16) & 0xFFFF), before_store)
        self.assertIn(ppc.lbz(6, patch.HUB_CONFIG & 0xFFFF, 6), before_store)


if __name__ == "__main__":
    unittest.main()
