"""Radiant Dawn hub routing: the router run on a small PowerPC interpreter, behind the story hook."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from fe_modding.game_code import ppc, rd_hub, rd_story
from ppc_sim import STOP, Cpu

HUB = 56
ACTIVE, DEST, PENDING = 27, 32, 40   # slots: the hub flags appended after RD's 27 globals
CONFIG = rd_hub.validate_slots(HUB, ACTIVE, DEST, PENDING)


def _edit(patch, address):
    return next(e for e in patch.versions[rd_story.RFEE01] if e.address == address)


class RouterTests(unittest.TestCase):
    def setUp(self):
        cpu = self.cpu = Cpu()
        for edit in (*rd_story.PATCH.versions[rd_story.RFEE01], *rd_hub.PATCH.versions[rd_story.RFEE01]):
            if edit.address not in rd_story._CALLS:
                cpu.write(edit.address, edit.patched)
        cpu.write(rd_hub.HUB_CONFIG, CONFIG)
        self.calls = []

        def advance(c):     # the retail advance: the retail successor
            following = rd_story.retail_next(cpu.u8(rd_story._CURRENT_CHAPTER))
            if following is not None:
                cpu.mem[rd_story._CURRENT_CHAPTER] = following
            c.r[3] = 1

        def set_chapter(c):
            self.assertEqual(c.r[3], rd_story._PARTY)
            self.calls.append(c.r[4])
            cpu.mem[rd_story._CURRENT_CHAPTER] = c.r[4]

        cpu.stubs = {rd_story._ADVANCE: advance, rd_story._SET_CHAPTER: set_chapter}

    def finish(self, chapter, *, active=False, dest=0, pending=0):
        cpu = self.cpu
        cpu.mem[rd_story._CURRENT_CHAPTER] = chapter
        cpu.mem[rd_hub.FLAG_BITS + ACTIVE // 8] = (1 << ACTIVE % 8) if active else 0
        cpu.mem[rd_hub.FLAG_BITS + DEST // 8] = dest
        cpu.mem[rd_hub.FLAG_BITS + PENDING // 8] = pending
        cpu.r[1] = 0x81000000
        cpu.lr = STOP
        self.calls.clear()
        cpu.run(rd_story.HOOK)
        self.assertEqual(cpu.r[1], 0x81000000)
        self.assertEqual(cpu.r[3], 1)
        return (cpu.u8(rd_story._CURRENT_CHAPTER), cpu.u8(rd_hub.FLAG_BITS + DEST // 8),
                cpu.u8(rd_hub.FLAG_BITS + PENDING // 8))

    def test_inactive_hub_leaves_the_story_alone(self):
        self.assertEqual(self.finish(1), (2, 0, 0))
        self.assertEqual(self.calls, [])

    def test_activation_goes_to_the_hub_and_keeps_the_story_chapter_pending(self):
        self.assertEqual(self.finish(1, active=True), (HUB, 0, 2))
        self.assertEqual(self.cpu.u8(rd_story._RESUME_POINT), 4)

    def test_hub_with_a_destination_goes_there(self):
        self.assertEqual(self.finish(HUB, active=True, dest=3, pending=2), (3, 3, 2))

    def test_side_chapter_returns_to_the_hub(self):
        self.assertEqual(self.finish(3, active=True, dest=3, pending=2), (HUB, 3, 2))

    def test_hub_without_destination_continues_the_story(self):
        self.assertEqual(self.finish(HUB, active=True, pending=2), (2, 0, 0))

    def test_finishing_the_pending_chapter_moves_the_story_on(self):
        self.assertEqual(self.finish(2, active=True, dest=2, pending=2), (HUB, 2, 3))

    def test_story_chapter_after_the_pending_one_was_cleared(self):
        self.assertEqual(self.finish(2, active=True), (HUB, 0, 3))

    def test_deactivated_hub_continues_with_the_pending_chapter(self):
        self.assertEqual(self.finish(3, dest=3, pending=2), (2, 0, 0))

    def test_ending_is_untouched(self):
        self.assertEqual(self.finish(rd_story.ENDING, active=True), (rd_story.ENDING, 0, 0))
        self.assertEqual(self.calls, [])

    def test_custom_story_chapter_uses_its_successor_then_the_hub(self):
        successors = bytearray(0x100)
        successors[57] = 4
        self.cpu.write(rd_story.SUCCESSORS, bytes(successors))
        self.assertEqual(self.finish(57, active=True), (HUB, 0, 4))
        self.assertEqual(self.calls, [4, HUB])

    def test_unconfigured_router_does_nothing(self):
        self.cpu.write(rd_hub.HUB_CONFIG, bytes(5))
        self.assertEqual(self.finish(1, active=True), (2, 0, 0))


class PatchTests(unittest.TestCase):
    def test_router_replaces_the_hooks_first_done_instruction(self):
        done = _edit(rd_hub.PATCH, rd_hub.DONE)
        self.assertEqual(done.original, ppc.lwz(0, 0x24, 1).to_bytes(4, "big"))
        hook = _edit(rd_story.PATCH, rd_story.HOOK).patched
        self.assertEqual(hook[rd_hub.DONE - rd_story.HOOK:][:4], done.original)
        self.assertEqual(hook[rd_hub.DONE - rd_story.HOOK + 4:][:4], ppc.MTLR_R0.to_bytes(4, "big"))

    def test_story_patch_tolerates_the_router_branch(self):
        hook = _edit(rd_story.PATCH, rd_story.HOOK)
        seen = bytearray(hook.patched)
        at = rd_hub.DONE - rd_story.HOOK
        seen[at:at + 4] = _edit(rd_hub.PATCH, rd_hub.DONE).patched
        self.assertTrue(hook.matches(bytes(seen), hook.patched))

    def test_slots_are_checked(self):
        self.assertEqual(CONFIG, bytes((HUB, 3, 0x08, 4, 5)))
        with self.assertRaises(ValueError):
            rd_hub.validate_slots(40, ACTIVE, DEST, PENDING)
        with self.assertRaises(ValueError):
            rd_hub.validate_slots(HUB, ACTIVE, 33, 41)
        with self.assertRaises(ValueError):
            rd_hub.validate_slots(HUB, 130, DEST, PENDING)


if __name__ == "__main__":
    unittest.main()
