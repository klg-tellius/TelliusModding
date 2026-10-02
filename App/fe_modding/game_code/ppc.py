"""PowerPC helpers: instruction fields and masking of relocatable operands.

Masking makes a code window comparable across builds: branch targets, ``lis`` immediates and
the low halves of address-forming instructions (lis-based, or r2/r13 small-data) are zeroed,
so two builds of the same function compare equal even though their addresses differ.
"""

from __future__ import annotations

_D_FORM_MEMORY = set(range(32, 56))                      # lwz .. stfdu
_GPR_LOADS = {32, 33, 34, 35, 40, 41, 42, 43}
_UPDATE_FORMS = {33, 35, 37, 39, 41, 43, 45, 47, 49, 51, 53, 55}
_RA_WRITERS = {20, 21, 23, 25, 26, 27, 28, 29}
_RD_WRITERS = {7, 8, 12, 13}


def sext16(value: int) -> int:
    return value - 0x10000 if value & 0x8000 else value


def mask_words(words, sda: tuple[int | None, int | None]) -> list[int]:
    """Return ``words`` with relocatable operands zeroed (see module docstring)."""
    r2, r13 = sda
    masked: list[int] = []
    lis: dict[int, int] = {}
    for w in words:
        op, rd, ra = w >> 26, (w >> 21) & 31, (w >> 16) & 31
        m = w
        if op == 18:                                       # b / bl
            m = w & 0xFC000003
            if w & 1:
                for r in range(3, 13):
                    lis.pop(r, None)
        elif op == 16:                                     # bc
            m = w & 0xFFFF0003
        elif op == 15 and ra == 0:                         # lis
            m = w & 0xFFFF0000
            lis[rd] = 1
        elif op in (14, 24) or op in _D_FORM_MEMORY:
            src = rd if op == 24 else ra
            relocatable = src in lis or (op != 24 and ((src == 13 and r13 is not None) or (src == 2 and r2 is not None)))
            if relocatable:
                m = w & 0xFFFF0000
            if op == 14 or op in _GPR_LOADS:
                lis.pop(rd, None)
            elif op == 24:
                lis.pop(ra, None)
            if op in _UPDATE_FORMS:
                lis.pop(ra, None)
        elif op == 31:
            lis.pop(rd, None)
            lis.pop(ra, None)
        elif op in _RA_WRITERS:
            lis.pop(ra, None)
        elif op in _RD_WRITERS:
            lis.pop(rd, None)
        masked.append(m)
    return masked


# -- encoders (big-endian 32-bit instruction words) ------------------------------------------------
def _branch(opcode_lk: int, source: int, target: int) -> int:
    delta = target - source
    if delta % 4 or not -0x2000000 <= delta < 0x2000000:
        raise ValueError(f"Branch {source:08X} -> {target:08X} is out of range.")
    return 0x48000000 | (delta & 0x03FFFFFC) | opcode_lk


def b(source: int, target: int) -> int:
    return _branch(0, source, target)


def bl(source: int, target: int) -> int:
    return _branch(1, source, target)


def _d_form(op: int, rd: int, ra: int, imm: int) -> int:
    return (op << 26) | (rd << 21) | (ra << 16) | (imm & 0xFFFF)


def li(rd: int, imm: int) -> int:
    return _d_form(14, rd, 0, imm)


def addi(rd: int, ra: int, imm: int) -> int:
    return _d_form(14, rd, ra, imm)


def mulli(rd: int, ra: int, imm: int) -> int:
    return _d_form(7, rd, ra, imm)


def srawi(ra: int, rs: int, sh: int) -> int:
    return (31 << 26) | (rs << 21) | (ra << 16) | (sh << 11) | (824 << 1)


def andc(ra: int, rs: int, rb: int) -> int:
    return (31 << 26) | (rs << 21) | (ra << 16) | (rb << 11) | (60 << 1)


NOP = 0x60000000
BLR = 0x4E800020


def lwz(rd: int, offset: int, ra: int) -> int:
    return _d_form(32, rd, ra, offset)


def stw(rs: int, offset: int, ra: int) -> int:
    return _d_form(36, rs, ra, offset)


def stwu(rs: int, offset: int, ra: int) -> int:
    return _d_form(37, rs, ra, offset)


def lfs(frd: int, offset: int, ra: int) -> int:
    return _d_form(48, frd, ra, offset)


def stfs(frs: int, offset: int, ra: int) -> int:
    return _d_form(52, frs, ra, offset)


def lis(rd: int, imm: int) -> int:
    return _d_form(15, rd, 0, imm)


def fmuls(frt: int, fra: int, frc: int) -> int:
    return (59 << 26) | (frt << 21) | (fra << 16) | (frc << 6) | (25 << 1)


MFLR_R0 = 0x7C0802A6
MTLR_R0 = 0x7C0803A6
CRCLR_6 = 0x4CC63182      # crxor 6,6,6: no floating-point arguments in registers for a varargs call


def lha(rd: int, offset: int, ra: int) -> int:
    return _d_form(42, rd, ra, offset)


def lbz(rd: int, offset: int, ra: int) -> int:
    return _d_form(34, rd, ra, offset)


def stfd(frs: int, offset: int, ra: int) -> int:
    return _d_form(54, frs, ra, offset)


def cmpwi(ra: int, imm: int) -> int:
    return _d_form(11, 0, ra, imm)


def cmplwi(ra: int, imm: int) -> int:
    return _d_form(10, 0, ra, imm)


def andi_(ra: int, rs: int, imm: int) -> int:
    return _d_form(28, rs, ra, imm)


def _x_form(rd: int, ra: int, rb: int, xo: int, op: int = 31) -> int:
    return (op << 26) | (rd << 21) | (ra << 16) | (rb << 11) | (xo << 1)


def mr(ra: int, rs: int) -> int:
    return _x_form(rs, ra, rs, 444)


def cmplw(ra: int, rb: int) -> int:
    return _x_form(0, ra, rb, 32)


def lbzx(rd: int, ra: int, rb: int) -> int:
    return _x_form(rd, ra, rb, 87)


def add(rd: int, ra: int, rb: int) -> int:
    return _x_form(rd, ra, rb, 266)


def fadds(frd: int, fra: int, frb: int) -> int:
    return _x_form(frd, fra, frb, 21, op=59)


def subf(rd: int, ra: int, rb: int) -> int:
    """rd = rb - ra"""
    return _x_form(rd, ra, rb, 40)


def extsb(ra: int, rs: int) -> int:
    return _x_form(rs, ra, 0, 954)


def fmr(frd: int, frb: int) -> int:
    return _x_form(frd, 0, frb, 72, op=63)


def fctiwz(frd: int, frb: int) -> int:
    return _x_form(frd, 0, frb, 15, op=63)


# conditional branches on cr0: (BO, BI)
_CONDITIONS = {"lt": (12, 0), "gt": (12, 1), "eq": (12, 2), "ge": (4, 0), "le": (4, 1), "ne": (4, 2)}


def bc(condition: str, source: int, target: int) -> int:
    delta = target - source
    if delta % 4 or not -0x8000 <= delta < 0x8000:
        raise ValueError(f"Branch {source:08X} -> {target:08X} is out of range.")
    bo, bi = _CONDITIONS[condition]
    return (16 << 26) | (bo << 21) | (bi << 16) | (delta & 0xFFFC)


def assemble(origin: int, program) -> list[int]:
    """Words of ``program`` placed at ``origin``.

    Items are instruction words, label names (str), or ``(kind, target)`` pairs resolved once
    the labels are known: kind ``"b"``/``"bl"`` or a :func:`bc` condition; the target is a label
    or an absolute address."""
    labels, address = {}, origin
    for item in program:
        if isinstance(item, str):
            labels[item] = address
        else:
            address += 4
    words = []
    for item in program:
        if isinstance(item, str):
            continue
        if isinstance(item, tuple):
            kind, target = item
            source, target = origin + 4 * len(words), labels.get(target, target)
            if kind == "b":
                item = b(source, target)
            elif kind == "bl":
                item = bl(source, target)
            else:
                item = bc(kind, source, target)
        words.append(item)
    return words
