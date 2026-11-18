"""The in-game check harness without Dolphin: RAM unit parsing and the judges."""
import struct
import unittest

from tools.ingame_checks import oracles
from tools.ingame_checks.ram_view import LAYOUTS, GameRam


class FakeRam:
    """A sparse big-endian memory: {address: bytes}."""

    def __init__(self):
        self.mem = bytearray(0x100000)
        self.base = 0x80700000

    def put(self, address: int, data: bytes) -> None:
        self.mem[address - self.base:address - self.base + len(data)] = data

    def read(self, address: int, length: int) -> bytes:
        if address < self.base:
            return bytes(length)
        return bytes(self.mem[address - self.base:address - self.base + length])

    def u32(self, address: int) -> int:
        return struct.unpack(">I", self.read(address, 4))[0]

    def cstring(self, address: int, limit: int = 64) -> str:
        return self.read(address, limit).split(b"\0", 1)[0].decode("latin-1")


class RamViewTests(unittest.TestCase):
    def test_rd_units_through_the_array_pointer(self):
        ram = FakeRam()
        lay = LAYOUTS["RFEE01"]
        array = 0x80710000
        strings = {"PID_MICAIAH": 0x80720000, "JID_LIGHTMAGE": 0x80720020, "IID_LIGHT": 0x80720040}
        for text, address in strings.items():
            ram.put(address, text.encode() + b"\0")
        person, job, item = 0x80721000, 0x80721100, 0x80721200
        ram.put(person, struct.pack(">I", strings["PID_MICAIAH"]))
        ram.put(job, struct.pack(">I", strings["JID_LIGHTMAGE"]))
        ram.put(item, struct.pack(">I", strings["IID_LIGHT"]))
        unit = array + 3 * lay.stride
        ram.put(unit + lay.person, struct.pack(">II", person, job))
        ram.put(unit + lay.handle, bytes([4]))
        ram.put(unit + lay.x, bytes([10, 11]))
        ram.put(unit + lay.hp, bytes([15]))
        ram.put(unit + lay.items, struct.pack(">IB", item, 40))
        game = GameRam(ram, "RFEE01")
        game.layout = lay.__class__(**{**lay.__dict__, "units": 0x80700000})
        ram.put(0x80700000, struct.pack(">I", array))
        units = game.units()
        self.assertEqual(len(units), 1)
        u = units[0]
        self.assertEqual((u.handle, u.pid, u.jid, u.x, u.y, u.hp), (4, "PID_MICAIAH", "JID_LIGHTMAGE", 10, 11, 15))
        self.assertEqual(u.items, [("IID_LIGHT", 40, item)])


class JudgeTests(unittest.TestCase):
    def _obs(self, person: bytes) -> dict:
        return {"records": {"PID_X": {"person": person.hex(), "job": "", "items": {}}}}

    def test_record_edit(self):
        judge = oracles.record_edit("PID_X", "person")
        retail = bytes([1, 2, 3, 4])
        ok, text = judge(self._obs(bytes([1, 4, 3, 4])), self._obs(retail), {"old": 2, "new": 4})
        self.assertTrue(ok, text)
        ok, text = judge(self._obs(retail), self._obs(retail), {"old": 2, "new": 4})
        self.assertFalse(ok)
        self.assertIn("not loaded", text)
        ok, _ = judge(self._obs(bytes([9, 9, 9, 4])), self._obs(retail), {"old": 2, "new": 4})
        self.assertFalse(ok)

    def test_negative_values_compare_as_bytes(self):
        judge = oracles.record_edit("PID_X", "person")
        ok, text = judge(self._obs(bytes([0xFE])), self._obs(bytes([0])), {"old": 0, "new": -2})
        self.assertTrue(ok, text)


if __name__ == "__main__":
    unittest.main()
