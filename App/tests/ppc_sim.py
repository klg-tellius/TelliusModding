"""A tiny PowerPC interpreter for testing generated hooks: only the instructions they use.

Memory is a sparse byte map; calls to addresses in ``stubs`` run a Python function instead
(``stub(cpu)``) and return. :meth:`Cpu.run` stops when the program returns to ``STOP``.
"""

from __future__ import annotations

STOP = 0x81FFFFF0


def _s16(value: int) -> int:
    return value - 0x10000 if value & 0x8000 else value


class Cpu:
    def __init__(self):
        self.r = [0] * 32
        self.lr = 0
        self.cr = [0, 0, 0, 0]      # cr0 bits lt, gt, eq, so
        self.mem: dict[int, int] = {}
        self.stubs: dict[int, callable] = {}

    # memory
    def write(self, address: int, data: bytes) -> None:
        for i, b in enumerate(data):
            self.mem[address + i] = b

    def read(self, address: int, length: int) -> bytes:
        return bytes(self.mem.get(address + i, 0) for i in range(length))

    def u8(self, address: int) -> int:
        return self.mem.get(address, 0)

    def u32(self, address: int) -> int:
        return int.from_bytes(self.read(address, 4), "big")

    def set_u32(self, address: int, value: int) -> None:
        self.write(address, (value & 0xFFFFFFFF).to_bytes(4, "big"))

    def _ea(self, ra: int, d: int) -> int:
        return ((self.r[ra] if ra else 0) + d) & 0xFFFFFFFF

    def _compare(self, a: int, b: int) -> None:
        self.cr = [int(a < b), int(a > b), int(a == b), 0]

    def run(self, pc: int, limit: int = 10000) -> None:
        for _ in range(limit):
            if pc == STOP:
                return
            if pc in self.stubs:
                self.stubs[pc](self)
                pc = self.lr
                continue
            word = self.u32(pc)
            op = word >> 26
            rd, ra, rb = (word >> 21) & 31, (word >> 16) & 31, (word >> 11) & 31
            imm = _s16(word & 0xFFFF)
            nxt = pc + 4
            if op == 14:
                self.r[rd] = self._ea(ra, imm)
            elif op == 15:
                self.r[rd] = ((self.r[ra] if ra else 0) + (imm << 16)) & 0xFFFFFFFF
            elif op == 32:
                self.r[rd] = self.u32(self._ea(ra, imm))
            elif op == 34:
                self.r[rd] = self.u8(self._ea(ra, imm))
            elif op == 36:
                self.set_u32(self._ea(ra, imm), self.r[rd])
            elif op == 37:
                address = self._ea(ra, imm)
                self.set_u32(address, self.r[rd])
                self.r[ra] = address
            elif op == 38:
                self.mem[self._ea(ra, imm)] = self.r[rd] & 0xFF
            elif op == 10:
                self._compare(self.r[ra], word & 0xFFFF)
            elif op == 11:
                value = self.r[ra] - 0x100000000 if self.r[ra] & 0x80000000 else self.r[ra]
                self._compare(value, imm)
            elif op == 16:
                bo, bi = rd, ra
                bd = word & 0xFFFC
                bd = bd - 0x10000 if bd & 0x8000 else bd
                taken = (bo & 0x14) == 0x14 or bool(self.cr[bi]) == bool(bo & 8)
                if word & 1:
                    self.lr = nxt
                if taken:
                    nxt = pc + bd
            elif op == 18:
                li = word & 0x03FFFFFC
                li = li - 0x04000000 if li & 0x02000000 else li
                if word & 1:
                    self.lr = nxt
                nxt = (li if word & 2 else pc + li) & 0xFFFFFFFF
            elif op == 19 and (word >> 1) & 0x3FF == 16:
                nxt = self.lr
            elif op == 31:
                xo = (word >> 1) & 0x3FF
                if xo == 87:
                    self.r[rd] = self.u8(self._ea(ra, self.r[rb]))
                elif xo == 215:
                    self.mem[self._ea(ra, self.r[rb])] = self.r[rd] & 0xFF
                elif xo == 28:
                    self.r[ra] = self.r[rd] & self.r[rb]
                elif xo == 444:
                    self.r[ra] = self.r[rd] | self.r[rb]
                elif xo == 32:
                    self._compare(self.r[ra], self.r[rb])
                elif xo == 339 and ((word >> 11) & 0x3FF) == 0x100:
                    self.r[rd] = self.lr
                elif xo == 467 and ((word >> 11) & 0x3FF) == 0x100:
                    self.lr = self.r[rd]
                else:
                    raise NotImplementedError(f"{pc:08X}: {word:08X}")
            else:
                raise NotImplementedError(f"{pc:08X}: {word:08X}")
            pc = nxt
        raise RuntimeError("the program did not return")
