"""FE9 custom item-use hook for the optional ItemRestrictionData export.

The hook adds an allow-list test after each retail usability predicate returns
success.  It uses its own DOL text section, leaving the shared 0x80001800 code
cave and all existing game-code options untouched.
"""

from __future__ import annotations

import struct

from . import ppc
from .dol import Dol, DolError

MAGIC = b"IRCH"
SIZE = 0x600
OFF_EQUIP = 0x40
OFF_USE = 0xB0
OFF_EQUIP_TRAMP = 0x120
OFF_USE_TRAMP = 0x130
OFF_MATCH = 0x140
OFF_EQUAL = 0x300
OFF_NAME = 0x400
NAME = b"ItemRestrictionData\x00"

# equipment restrictions, item-use handler check, symbol hash lookup, skill bit test
SITES = {
    "GFEE01": (0x800940B0, 0x80091F70, 0x8000D354, 0x80105BC0),
    "GFEP01": (0x800956C8, 0x80093588, 0x8000D47C, 0x80106398),
    "GFEJ01": (0x80092614, 0x800904D4, 0x8000D330, 0x80103538),
}
PROLOGUES = (0x9421FFE0, 0x9421FFF0)


def _words(origin: int, program) -> bytes:
    return b"".join(struct.pack(">I", word) for word in ppc.assemble(origin, program))


def _address(reg: int, address: int) -> list[int]:
    return [ppc.lis(reg, ((address + 0x8000) >> 16) & 0xFFFF),
            ppc.addi(reg, reg, ppc.sext16(address & 0xFFFF))]


def _equal(address: int) -> bytes:
    return _words(address, [
        ppc.cmpwi(3, 0), ("eq", "false"), ppc.cmpwi(4, 0), ("eq", "false"),
        "loop", ppc.lbz(5, 0, 3), ppc.lbz(6, 0, 4), ppc.cmplw(5, 6), ("ne", "false"),
        ppc.cmpwi(5, 0), ("eq", "true"), ppc.addi(3, 3, 1), ppc.addi(4, 4, 1), ("b", "loop"),
        "true", ppc.li(3, 1), ppc.BLR,
        "false", ppc.li(3, 0), ppc.BLR,
    ])


def _wrapper(address: int, trampoline: int, matcher: int) -> bytes:
    return _words(address, [
        ppc.stwu(1, -0x30, 1), ppc.MFLR_R0, ppc.stw(0, 0x34, 1),
        ppc.stw(29, 0x24, 1), ppc.stw(30, 0x28, 1), ppc.stw(31, 0x2C, 1),
        ppc.mr(30, 3), ppc.mr(31, 4), ("bl", trampoline),
        ppc.mr(29, 3), ppc.cmpwi(29, 0), ("eq", "done"),
        ppc.mr(3, 30), ppc.mr(4, 31), ("bl", matcher),
        ppc.cmpwi(3, 0), ("eq", "done"), ppc.mr(3, 29),
        "done", ppc.lwz(29, 0x24, 1), ppc.lwz(30, 0x28, 1), ppc.lwz(31, 0x2C, 1),
        ppc.lwz(0, 0x34, 1), ppc.MTLR_R0, ppc.addi(1, 1, 0x30), ppc.BLR,
    ])


def _matcher(address: int, equal: int, name: int, lookup: int, skill: int) -> bytes:
    program = [
        ppc.stwu(1, -0x80, 1), ppc.MFLR_R0, ppc.stw(0, 0x84, 1),
        ppc.stmw(17, 0x40, 1), ppc.mr(31, 3), ppc.mr(30, 4),
        *_address(3, name), ("bl", lookup), ppc.cmpwi(3, 0), ("eq", "allow"),
        ppc.lhz(28, 6, 3), ppc.addi(27, 3, 8),
        "record", ppc.cmpwi(28, 0), ("eq", "allow"),
        ppc.lbz(24, 5, 27), ppc.lbz(23, 6, 27), ppc.lbz(22, 7, 27),
        ppc.add(26, 24, 23), ppc.mulli(26, 26, 4), ppc.mulli(0, 22, 8),
        ppc.add(26, 26, 0), ppc.addi(26, 26, 8), ppc.add(26, 27, 26),
        ppc.lwz(3, 0, 27), ppc.lwz(4, 0, 30), ("bl", equal),
        ppc.cmpwi(3, 0), ("eq", "next"),
        ppc.li(21, 0), ppc.li(20, 0), ppc.addi(18, 27, 8),
        # Any one character ID; r19 is the end of this group.
        ppc.cmpwi(24, 0), ("eq", "class_setup"),
        ppc.addi(21, 21, 1), ppc.mulli(19, 24, 4), ppc.add(19, 18, 19),
        ppc.lwz(25, 0x188, 31), ppc.cmpwi(25, 0), ("eq", "pid_end"), ppc.lwz(25, 0, 25),
        "pid_loop", ppc.cmplw(18, 19), ("ge", "pid_end"),
        ppc.lwz(3, 0, 18), ppc.mr(4, 25), ("bl", equal),
        ppc.cmpwi(3, 0), ("ne", "pid_yes"), ppc.addi(18, 18, 4), ("b", "pid_loop"),
        "pid_yes", ppc.addi(20, 20, 1),
        "pid_end", ppc.mr(18, 19),
        "class_setup", ppc.cmpwi(23, 0), ("eq", "skill_setup"),
        ppc.addi(21, 21, 2), ppc.mulli(19, 23, 4), ppc.add(19, 18, 19),
        ppc.lwz(25, 0x18C, 31), ppc.cmpwi(25, 0), ("eq", "jid_end"), ppc.lwz(25, 0, 25),
        "jid_loop", ppc.cmplw(18, 19), ("ge", "jid_end"),
        ppc.lwz(3, 0, 18), ppc.mr(4, 25), ("bl", equal),
        ppc.cmpwi(3, 0), ("ne", "jid_yes"), ppc.addi(18, 18, 4), ("b", "jid_loop"),
        "jid_yes", ppc.addi(20, 20, 2),
        "jid_end", ppc.mr(18, 19),
        "skill_setup", ppc.cmpwi(22, 0), ("eq", "decide"),
        ppc.addi(21, 21, 4), ppc.mulli(19, 22, 8), ppc.add(19, 18, 19),
        "sid_loop", ppc.cmplw(18, 19), ("ge", "decide"),
        ppc.addi(3, 31, 0x1BC), ppc.lwz(4, 4, 18), ("bl", skill),
        ppc.cmpwi(3, 0), ("ne", "sid_yes"), ppc.addi(18, 18, 8), ("b", "sid_loop"),
        "sid_yes", ppc.addi(20, 20, 4),
        "decide", ppc.lbz(0, 4, 27), ppc.cmpwi(0, 1), ("eq", "all"),
        ppc.cmpwi(21, 0), ("eq", "allow"),
        ppc.cmpwi(20, 0), ("ne", "allow"), ("b", "deny"),
        "all", ppc.cmplw(20, 21), ("eq", "allow"), ("b", "deny"),
        "next", ppc.mr(27, 26), ppc.addi(28, 28, -1), ("b", "record"),
        "allow", ppc.li(3, 1), ("b", "return"),
        "deny", ppc.li(3, 0),
        "return", ppc.lmw(17, 0x40, 1), ppc.lwz(0, 0x84, 1), ppc.MTLR_R0,
        ppc.addi(1, 1, 0x80), ppc.BLR,
    ]
    return _words(address, program)


def _base(dol: Dol) -> int:
    end = max(dol.bss_address + dol.bss_size,
              *(section.address + section.size for section in dol.sections
                if section.address < 0x81800000 and
                (section.size != SIZE or dol.read(section.address, 4) != MAGIC)))
    return (end + 0xFFF) & ~0xFFF


def _section(dol: Dol) -> tuple[int, bytes] | None:
    for section in dol.text_sections:
        if section.size == SIZE and dol.read(section.address, 4) == MAGIC:
            return section.address, dol.read(section.address, SIZE)
    base = _base(dol)
    try:
        dol.section_at(base, SIZE)
    except DolError:
        return None
    raise DolError(f"Item-restriction section conflicts at {base:08X}.")


def install(dol: Dol, version: str) -> None:
    """Install once; reject unknown prologues and other mods' conflicting hooks."""
    if version not in SITES:
        raise DolError(f"Unsupported FE9 version {version}.")
    existing = _section(dol)
    if existing is not None:
        base, _data = existing
        if all(dol.u32(site) == ppc.b(site, base + offset)
               for site, offset in zip(SITES[version][:2], (OFF_EQUIP, OFF_USE))):
            return
        raise DolError("Item-restriction hook is only partly installed.")
    equip, use, lookup, skill = SITES[version]
    prologues = (dol.u32(equip), dol.u32(use))
    if prologues != PROLOGUES:
        raise DolError("Item-restriction hook sites differ from the supported retail prologues.")
    base = _base(dol)
    if base + SIZE >= 0x81800000:
        raise DolError("No safe MEM1 address for the item-restriction hook.")
    code = bytearray(SIZE)
    code[:16] = MAGIC + struct.pack(">III", 1, *prologues)
    parts = (
        (OFF_EQUIP, _wrapper(base + OFF_EQUIP, base + OFF_EQUIP_TRAMP, base + OFF_MATCH)),
        (OFF_USE, _wrapper(base + OFF_USE, base + OFF_USE_TRAMP, base + OFF_MATCH)),
        (OFF_EQUIP_TRAMP, struct.pack(">II", prologues[0], ppc.b(base + OFF_EQUIP_TRAMP + 4, equip + 4))),
        (OFF_USE_TRAMP, struct.pack(">II", prologues[1], ppc.b(base + OFF_USE_TRAMP + 4, use + 4))),
        (OFF_MATCH, _matcher(base + OFF_MATCH, base + OFF_EQUAL, base + OFF_NAME, lookup, skill)),
        (OFF_EQUAL, _equal(base + OFF_EQUAL)),
        (OFF_NAME, NAME),
    )
    for offset, data in parts:
        if offset + len(data) > SIZE:
            raise DolError("Item-restriction hook exceeds its DOL section.")
        if any(code[offset:offset + len(data)]):
            raise DolError("Item-restriction hook section layout overlaps.")
        code[offset:offset + len(data)] = data
    dol.add_text_section(base, code)
    dol.write(equip, struct.pack(">I", ppc.b(equip, base + OFF_EQUIP)))
    dol.write(use, struct.pack(">I", ppc.b(use, base + OFF_USE)))


def uninstall(dol: Dol, version: str) -> None:
    existing = _section(dol)
    if existing is None:
        return
    if version not in SITES:
        raise DolError(f"Unsupported FE9 version {version}.")
    base, data = existing
    equip, use = SITES[version][:2]
    if (dol.u32(equip), dol.u32(use)) != (ppc.b(equip, base + OFF_EQUIP),
                                         ppc.b(use, base + OFF_USE)):
        raise DolError("Item-restriction hook sites have changed; refusing to remove it.")
    first, second = struct.unpack_from(">II", data, 8)
    dol.write(equip, struct.pack(">I", first))
    dol.write(use, struct.pack(">I", second))
    dol.remove_section_at(base)
