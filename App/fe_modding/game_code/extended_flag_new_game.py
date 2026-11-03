"""Extended new-playthrough save fragments for all three retail regions.

Preflight follows party initialization, before writing the gameplay payload.
Retail has already initialized a free block's header at this point. Failure
sets the card error and bypasses CRC finalization and write scheduling.
"""
import hashlib

from . import ppc
from .catalog import Edit
from .dol import DolError
from .extended_flag_runtime import NativeImage, _address
from .extended_flag_sites import PARTY
from .extended_flag_checkpoint import ERROR_SETTERS, UNIT_ARRAY

SITES = {
    "GFEE01": (0x801E1540, "8be8b9f3d6cc4d1ae965305cbe712e977d8eadccc3cae3ffb2ce4d13b3f1c14c"),
    "GFEP01": (0x801E4640, "066dd3c5c62ffa8f01ad38ab40b078f6e9ac8a1baaa6ee1f3a7f7bba53c4f76f"),
    "GFEJ01": (0x801DE008, "ae0165f7d7cd1bee1e60b347020980ea17ad5311ea497277d03a4bb296186d00"),
}


def build_new_game_fragment(dol, version, core):
    if version not in SITES:
        raise ValueError("Unsupported new-game region")
    for edit in core.edits:
        if dol.read(edit.address, len(edit.original)) != edit.original:
            raise DolError("New-game fragment requires matching retail inputs")
    writer, digest = SITES[version]
    for at, size, expected in ((writer, 0x774, digest), ERROR_SETTERS[version]):
        if hashlib.sha256(dol.read(at, size)).hexdigest() != expected:
            raise DolError("New-game writer or error helper differs from retail")
    guard_site, append_site, epilogue = writer + 0x5D4, writer + 0x700, writer + 0x760
    error = [ppc.li(3, -9), ("bl", ERROR_SETTERS[version][0]), ("b", epilogue)]
    guard = [
        *_address(3, UNIT_ARRAY[version]), *_address(4, PARTY[version] + 0x55),
        ppc.lbz(4, 0, 4), ppc.li(5, 0x4000), ("bl", core.functions["save_preflight"]),
        ppc.cmpwi(3, 0), ("eq", "failed"), dol.u32(guard_site), ("b", guard_site + 4),
        "failed", *error,
    ]
    append = [
        ppc.addi(3, 1, 8), ppc.addi(4, 31, 0x4000), ("bl", core.functions["record_write"]),
        ppc.cmpwi(3, 0), ("eq", "failed"), dol.u32(append_site), ("b", append_site + 4),
        "failed", *error,
    ]
    data, edits, functions = bytearray(core.data), list(core.edits), dict(core.functions)
    for name, offset, site, program in (
        ("new_game_guard", 0x3600, guard_site, guard),
        ("new_game_append", 0x3800, append_site, append),
    ):
        code = b"".join(w.to_bytes(4, "big") for w in ppc.assemble(core.base + offset, program))
        if len(code) > 0x200 or any(data[offset:offset + 0x200]):
            raise ValueError("New-game code slot occupied or too small")
        data[offset:offset + len(code)] = code
        functions[name] = core.base + offset
        edits.append(Edit(site, dol.read(site, 4), ppc.b(site, core.base + offset).to_bytes(4, "big")))
    return NativeImage(core.base, bytes(data), tuple(edits), functions)
