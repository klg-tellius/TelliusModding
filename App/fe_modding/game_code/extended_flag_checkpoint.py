"""Bounded checkpoint writer fragments for all retail regions, release-gated.

The checkpoint writer schedules its own child card-write process. On failure it
must set the card error and return without starting that child. Its callers then
follow their existing close/error paths. User-visible capacity-specific messaging
and complete persistence integration are still required before release.
"""
import hashlib

from . import ppc
from .catalog import Edit
from .dol import DolError
from .extended_flag_runtime import NativeImage, _address
from .extended_flag_sites import PARTY
from .extended_flag_file_save import SITES as FILE_SITES, UNIT_ARRAY as FILE_UNITS

SITES = {
    "GFEE01": (0x801E047C, 0x390, "49c6c03f8594d78929329e1fc20a98d12abf6a985fdcb87be93355028c466dc8", 0x31C, 0x37C, 29),
    "GFEP01": (0x801E3584, 0x390, "8d9715f424227cbd8fb788cd48baddc6dd354fe47785cfcbc9b410a93563fed5", 0x31C, 0x37C, 29),
    "GFEJ01": (0x801DD57C, 0x30C, "1336decb165ae3721cc1f0c4ab27c078b3fa867a7a8c5063fb630b36454bab14", 0x290, 0x2F0, 31),
}
ERROR_SETTERS = {**{code: sites["set_error"] for code, sites in FILE_SITES.items()},
                 "GFEJ01": (0x800E910C, 20, "b975fdf489aad8007e96d635fb23aa9cd2aa4175d674e3470bf623b155344cb4")}
UNIT_ARRAY = {**FILE_UNITS, "GFEJ01": 0x802AF5E4}
GUARD_OFFSET, APPEND_OFFSET = 0x1E00, 0x2000


def build_checkpoint_fragment(dol, version, core):
    if version not in SITES:
        raise ValueError("Unsupported checkpoint region")
    for edit in core.edits:
        if dol.read(edit.address, len(edit.original)) != edit.original:
            raise DolError("Checkpoint fragment requires a matching retail core")
    writer, size, digest, after, epilogue, block_reg = SITES[version]
    error, error_size, error_digest = ERROR_SETTERS[version]
    for address, length, expected in ((writer, size, digest), (error, error_size, error_digest)):
        if hashlib.sha256(dol.read(address, length)).hexdigest() != expected:
            raise DolError("Checkpoint writer/error helper differs from retail")
    guard = [
        ppc.stwu(1, -32, 1), ppc.MFLR_R0, ppc.stw(0, 36, 1),
        ppc.stw(3, 8, 1), ppc.stw(4, 12, 1),
        *_address(3, UNIT_ARRAY[version]), *_address(4, PARTY[version] + 0x55),
        ppc.lbz(4, 0, 4), ppc.li(5, 0x6000), ("bl", core.functions["save_preflight"]),
        ppc.cmpwi(3, 0), ("ne", "accepted"),
        ppc.li(3, -9), ("bl", error),
        ppc.lwz(0, 36, 1), ppc.MTLR_R0, ppc.addi(1, 1, 32), ppc.BLR,
        "accepted", ppc.lwz(3, 8, 1), ppc.lwz(4, 12, 1),
        ppc.lwz(0, 36, 1), ppc.MTLR_R0, ppc.addi(1, 1, 32),
        dol.u32(writer), ("b", writer + 4),
    ]
    append = [
        ppc.addi(3, 1, 8), ppc.addi(4, block_reg, 0x6000),
        ("bl", core.functions["record_write"]), ppc.cmpwi(3, 0), ("eq", "failed"),
        dol.u32(writer + after), ("b", writer + after + 4),
        "failed", ppc.li(3, -9), ("bl", error), ("b", writer + epilogue),
    ]
    data, edits, functions = bytearray(core.data), list(core.edits), dict(core.functions)
    for name, offset, site, program in (
        ("checkpoint_guard", GUARD_OFFSET, writer, guard),
        ("checkpoint_append", APPEND_OFFSET, writer + after, append),
    ):
        code = b"".join(word.to_bytes(4, "big") for word in ppc.assemble(core.base + offset, program))
        if len(code) > 0x200 or any(data[offset:offset + 0x200]):
            raise ValueError("Checkpoint code slot occupied or too small")
        data[offset:offset + len(code)] = code
        functions[name] = core.base + offset
        edits.append(Edit(site, dol.read(site, 4), ppc.b(site, core.base + offset).to_bytes(4, "big")))
    return NativeImage(core.base, bytes(data), tuple(edits), functions)
