"""Japanese file-save hooks, whose writer starts its own blocking child.

The menu advances to state 0x268, then reads the card result and displays
FM_ERR_SAVE on failure. Refusal returns without creating a child or touching
the target block. This remains a proposed fragment, not an installer.
"""
import hashlib

from . import ppc
from .catalog import Edit
from .dol import DolError
from .extended_flag_checkpoint import ERROR_SETTERS, UNIT_ARRAY
from .extended_flag_runtime import NativeImage, _address
from .extended_flag_sites import PARTY

REGION = "GFEJ01"
WRITER = 0x801DE77C
GUARDS = (
    (0x801D2228, 0x18, "4b71ed4ac013e7672c6e7ccc10f43a1918b2f60455408511741991968b573179"),
    (WRITER, 0x374, "b7175473d6cb16bd2c5b932c7d294973eaba8c21891897400d467ddb204a7c77"),
    (0x801D54E0, 0xA0, "62f4db0eea60f47058402484b6f91df03d613c3c69d2e577b6f3fd4e3ac4bb0f"),
    (0x8009D1C0, 0x60, "8b6255420eac02413412d21228046962611f025a5bba7fbb9b324488528eb854"),
    (0x800E9120, 20, "f7771b62e954f197772bffd850aecae718a6e0998e96b86b5b0845f51a4b1aac"),
    ERROR_SETTERS[REGION],
)


def build_jp_file_save_fragment(dol, version, core):
    if version != REGION:
        raise ValueError("Japanese file-save fragment requires GFEJ01")
    for edit in core.edits:
        if dol.read(edit.address, len(edit.original)) != edit.original:
            raise DolError("Japanese file-save fragment requires matching retail inputs")
    for at, size, digest in GUARDS:
        if hashlib.sha256(dol.read(at, size)).hexdigest() != digest:
            raise DolError("Japanese file writer or caller differs from retail")
    error = ERROR_SETTERS[REGION][0]
    guard = [
        ppc.stwu(1, -32, 1), ppc.MFLR_R0, ppc.stw(0, 36, 1),
        ppc.stw(3, 8, 1), ppc.stw(4, 12, 1), ppc.stw(5, 16, 1),
        *_address(3, UNIT_ARRAY[REGION]), *_address(4, PARTY[REGION] + 0x55),
        ppc.lbz(4, 0, 4), ppc.li(5, 0x4000), ("bl", core.functions["save_preflight"]),
        ppc.cmpwi(3, 0), ("ne", "accepted"),
        ppc.li(3, -9), ("bl", error),
        ppc.lwz(0, 36, 1), ppc.MTLR_R0, ppc.addi(1, 1, 32), ppc.BLR,
        "accepted", ppc.lwz(3, 8, 1), ppc.lwz(4, 12, 1), ppc.lwz(5, 16, 1),
        ppc.lwz(0, 36, 1), ppc.MTLR_R0, ppc.addi(1, 1, 32),
        dol.u32(WRITER), ("b", WRITER + 4),
    ]
    append_site = WRITER + 0x2FC
    append = [
        ppc.addi(3, 1, 8), ppc.addi(4, 31, 0x4000), ("bl", core.functions["record_write"]),
        ppc.cmpwi(3, 0), ("eq", "failed"), dol.u32(append_site), ("b", append_site + 4),
        "failed", ppc.li(3, -9), ("bl", error), ("b", WRITER + 0x354),
    ]
    data, edits, functions = bytearray(core.data), list(core.edits), dict(core.functions)
    for name, offset, site, program in (
        ("file_save_guard", 0x1A00, WRITER, guard),
        ("file_save_append", 0x1C00, append_site, append),
    ):
        code = b"".join(w.to_bytes(4, "big") for w in ppc.assemble(core.base + offset, program))
        if len(code) > 0x200 or any(data[offset:offset + 0x200]):
            raise ValueError("Japanese file-save code slot occupied or too small")
        data[offset:offset + len(code)] = code
        functions[name] = core.base + offset
        edits.append(Edit(site, dol.read(site, 4), ppc.b(site, core.base + offset).to_bytes(4, "big")))
    return NativeImage(core.base, bytes(data), tuple(edits), functions)
