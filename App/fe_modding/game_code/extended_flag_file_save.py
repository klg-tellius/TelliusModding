"""Verified US/EU file-save fragment; not a complete or installable runtime.

Adds preflight before retail touches a target block and appends XFLG before CRC
finalization. Japan uses a different writer ABI and is explicitly unsupported
here. Container isolation, versions, load hooks, checkpoints and snapshots must
be integrated before any production installer may use this fragment.
"""
from __future__ import annotations

import hashlib

from . import ppc
from .catalog import Edit
from .dol import Dol, DolError
from .extended_flag_runtime import NativeImage, FUNCTION_OFFSETS, _address
from .extended_flag_sites import PARTY

GUARD_OFFSET = 0x1A00
APPEND_OFFSET = 0x1C00
SITES = {
    "GFEE01": {
        "writer": (0x801E1CB4, 0x360, "e789f586051b518fe3cdc1e1758f251b02fc3b1765b4fa3d06a9ca394429e19e"),
        "set_error": (0x800EB760, 20, "14ab088976f35224ae0c067e4bda69f615db70ac44c85ea5292481cc115163e5"),
        "error_branch": (0x800EB788, 92, "f28efc4b73fe397f112b2126452bc83d53e2801187cc4b13d3ff3b44d5b7d363"),
        "caller": (0x801E2084, 64, "03477199998ea4b2de1360dfeacde55afca3fb977f601c4ce0a87bccb6352a3a"),
        "process": (0x80299E10, 80, "b3d0bc0c1ecc1ce6dbb92d73ec3e09da9f72a7c54875219ab3a09dc2f5ec3918"),
    },
    "GFEP01": {
        "writer": (0x801E4DB4, 0x360, "ad5758e170108739a47227d15a6f4bef324008b46e589e0cee132eb896d249b9"),
        "set_error": (0x800EBFAC, 20, "6db07ca4829cd350264d37a4265cc6b25df1a6fd4f14f0702ace448541f306da"),
        "error_branch": (0x800EBFD4, 92, "8ca21cfb422fc830f9a16e9dd86ac255b09608039e9d1a62f410afbf2dc5dd0f"),
        "caller": (0x801E5184, 64, "bf20fd2eec72bca2df340a4a1c2b7442be7ca611c83ad7aa6cb0dfd15a263040"),
        "process": (0x802A4088, 80, "957e48a40fb5a335daeaa18c40e36b4fda298953d33786ae85a1f8db62e1b46d"),
    },
}
UNIT_ARRAY = {"GFEE01": 0x802B14E4, "GFEP01": 0x802BB9C4}


def build_file_save_fragment(dol: Dol, version: str, core: NativeImage) -> NativeImage:
    """Return a new, still incomplete image; never modify either input."""
    if version not in SITES:
        raise ValueError("File-save hooks currently verified only for US/EU")
    sites = SITES[version]
    for edit in core.edits:
        if dol.read(edit.address, len(edit.original)) != edit.original:
            raise DolError("File-save fragment requires a core for the same retail executable")
    for name, (address, size, digest) in sites.items():
        if hashlib.sha256(dol.read(address, size)).hexdigest() != digest:
            raise DolError(f"file save {name}: retail code differs")
    for name in ("save_preflight", "record_write"):
        if core.functions.get(name) != core.base + FUNCTION_OFFSETS[name]:
            raise ValueError("File-save fragment requires the matching generated core")
    writer = sites["writer"][0]
    set_error, error_branch = sites["set_error"][0], sites["error_branch"][0]
    # CARD_RESULT_INSSPACE. Follow the existing process's label-99 path so it
    # cannot dereference a stale +0x54 output or schedule a card write.
    guard = [
        ppc.stwu(1, -32, 1), ppc.MFLR_R0, ppc.stw(0, 36, 1),
        ppc.stw(3, 8, 1), ppc.stw(4, 12, 1),
        *_address(3, UNIT_ARRAY[version]), *_address(4, PARTY[version] + 0x55),
        ppc.lbz(4, 0, 4), ppc.li(5, 0x4000), ("bl", core.functions["save_preflight"]),
        ppc.cmpwi(3, 0), ("ne", "accepted"),
        ppc.li(3, -9), ("bl", set_error), ppc.lwz(3, 12, 1), ("bl", error_branch),
        ppc.lwz(0, 36, 1), ppc.MTLR_R0, ppc.addi(1, 1, 32), ppc.BLR,
        "accepted", ppc.lwz(3, 8, 1), ppc.lwz(4, 12, 1),
        ppc.lwz(0, 36, 1), ppc.MTLR_R0, ppc.addi(1, 1, 32),
        dol.u32(writer), ("b", writer + 4),
    ]
    after_terrain = writer + 0x2F8
    append = [
        # Retail frame is intact: stream +8, block r31, process r29. The return
        # address is already saved at +0x34, so nested calls may change LR.
        ppc.addi(3, 1, 8), ppc.addi(4, 31, 0x4000),
        ("bl", core.functions["record_write"]), ppc.cmpwi(3, 0), ("eq", "failed"),
        dol.u32(after_terrain), ("b", after_terrain + 4),
        "failed", ppc.li(3, -9), ("bl", set_error),
        ppc.mr(3, 29), ("bl", error_branch), ("b", writer + 0x340),
    ]
    data = bytearray(core.data)
    edits = list(core.edits)
    functions = dict(core.functions)
    for name, offset, limit, site, program in (
        ("file_save_guard", GUARD_OFFSET, APPEND_OFFSET, writer, guard),
        ("file_save_append", APPEND_OFFSET, 0x1E00, after_terrain, append),
    ):
        words = ppc.assemble(core.base + offset, program)
        code = b"".join(word.to_bytes(4, "big") for word in words)
        if offset + len(code) > limit or any(data[offset:limit]):
            raise ValueError("File-save code slot is occupied or too small")
        data[offset:offset + len(code)] = code
        functions[name] = core.base + offset
        edits.append(Edit(site, dol.read(site, 4), ppc.b(site, core.base + offset).to_bytes(4, "big")))
    return NativeImage(core.base, bytes(data), tuple(edits), functions)
