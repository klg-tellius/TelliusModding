"""Small instruction interpreter for the generated integer-only flag routines.

Independent decoding of instruction words; no calls into the runtime's Python
model. Not a substitute for Dolphin's memory/boot/save lifecycle validation.
"""


def signed(value, width=32):
    return value - (1 << width) if value & (1 << (width - 1)) else value


class CPU:
    RETURN = 0x80000000

    def __init__(self, image):
        self.memory = {image.base + i: byte for i, byte in enumerate(image.data)}
        self.r = [0] * 32
        self.r[1] = 0x817F0000
        self.lr = self.RETURN
        self.cr = (False, False, False)

    def read(self, at, size):
        assert 0x80000000 <= at <= 0x81800000 - size, f"invalid read {at:08x}"
        return int.from_bytes(bytes(self.memory.get(at + i, 0) for i in range(size)), "big")

    def write(self, at, value, size):
        assert 0x80000000 <= at <= 0x81800000 - size, f"invalid write {at:08x}"
        for i, byte in enumerate((value & ((1 << (size * 8)) - 1)).to_bytes(size, "big")):
            self.memory[at + i] = byte

    def compare(self, left, right, is_signed):
        if is_signed:
            left, right = signed(left), signed(right)
        self.cr = left < right, left > right, left == right

    def run(self, pc, stop=()):
        for _ in range(1000000):
            if pc == self.RETURN or pc in stop:
                return pc
            w = self.read(pc, 4)
            op, rd, ra, rb, imm = w >> 26, (w >> 21) & 31, (w >> 16) & 31, (w >> 11) & 31, w & 0xFFFF
            xo = (w >> 1) & 1023
            base = self.r[ra] if ra else 0
            nxt = pc + 4
            if op == 14:
                self.r[rd] = base + signed(imm, 16)
            elif op == 15:
                self.r[rd] = base + (signed(imm, 16) << 16)
            elif op == 7:
                self.r[rd] = self.r[ra] * signed(imm, 16)
            elif op in (32, 34, 40):
                self.r[rd] = self.read((base + signed(imm, 16)) & 0xFFFFFFFF, {32: 4, 34: 1, 40: 2}[op])
            elif op in (36, 37, 38):
                at = (base + signed(imm, 16)) & 0xFFFFFFFF
                self.write(at, self.r[rd], 1 if op == 38 else 4)
                if op == 37:
                    self.r[ra] = at
            elif op in (10, 11):
                self.compare(self.r[ra], (signed(imm, 16) & 0xFFFFFFFF) if op == 11 else imm, op == 11)
            elif op == 18:
                if w & 1:
                    self.lr = nxt
                nxt = pc + signed(w & 0x03FFFFFC, 26)
            elif op == 16:
                assert ra < 3 and rd in (4, 12), f"unsupported condition {w:08x}"
                if self.cr[ra] == bool(rd & 8):
                    nxt = pc + signed(w & 0xFFFC, 16)
            elif w == 0x4E800020:
                nxt = self.lr
            elif w == 0x7C0802A6:
                self.r[0] = self.lr
            elif w == 0x7C0803A6:
                self.lr = self.r[0]
            elif op == 31 and xo == 32:
                self.compare(self.r[ra], self.r[rb], False)
            elif op == 31 and xo == 266:
                self.r[rd] = self.r[ra] + self.r[rb]
            elif op == 31 and xo == 444:
                self.r[ra] = self.r[rd] | self.r[rb]
            elif op == 31 and xo == 28:
                self.r[ra] = self.r[rd] & self.r[rb]
            elif op == 31 and xo == 60:
                self.r[ra] = self.r[rd] & ~self.r[rb]
            elif op == 31 and xo == 954:
                self.r[ra] = signed(self.r[rd] & 255, 8)
            else:
                raise AssertionError(f"unsupported instruction {w:08x} at {pc:08x}")
            self.r = [r & 0xFFFFFFFF for r in self.r]
            pc = nxt
        raise AssertionError("instruction limit exceeded")
