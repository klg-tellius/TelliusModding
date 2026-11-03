"""Bounded native card-record validation and restore, for the gated runtime.

Validation runs before retail block selection/deserialization. The restore hook
requires the card-open guard: returning failure from the retail void reader alone
would let its caller continue with partially restored game state. These are still
gated fragments, not a complete installable save-format patch.
"""
import hashlib

from . import ppc
from .catalog import Edit
from .dol import DolError
from .extended_flag_checkpoint import ERROR_SETTERS
from .extended_flag_file_save import SITES as FILE_SITES
from .extended_flag_runtime import NativeImage, _address, SNAPSHOT_OWNER_OFFSET
from ..formats import extended_flags as xf

VALIDATE_OFFSET = 0x2600
RESTORE_OFFSET = 0x2C00
CONTAINER_OFFSET = 0x2E00
OPEN_OFFSET = 0x3200
OPEN_SITES = {
    "GFEE01": (0x801E31C8, "ff8a8e5486c8b32fcf62947a86ca797175ef66a0e00f9fa223341236bd0718de",
                0x80299E04, "22e4b18fb7f6bde71def77cfcc0e65c57f294b5961718cdd45b7e58d6441a694", 0x801E2620),
    "GFEP01": (0x801E634C, "2a540b0dfc6eacd6a3c1ba1d0bb734ea9b9ada778000d581357881d322587604",
                0x802A407C, "f8e328abaa8f3eec85df2e91010a5f46ccb2ed26cedb1e078322d7a4b17eb760", 0x801E5720),
    "GFEJ01": (0x801DFB8C, "51819f627b338230074458f900bfdf7ce52fc1429a942c74da6b05dde153cfc7",
                0x8029840C, "6de548c8fb547191f73aa99873230b6ddba62863c565a2c78d109b596cd31ab8", 0x801DF034),
}
ERROR_BRANCHES = {**{code: sites["error_branch"] for code, sites in FILE_SITES.items()},
                  "GFEJ01": (0x800E9134, 92, "21efbb1572902fced2ddbad3996f92a37f519f815b5f1cfe2177094a8bb61938")}
READ_SITES = {
    "GFEE01": (0x801E379C, "dbf0bb8c57aa30e793b1d11f00751b7619b24433b359839ec8d23c1759a870ea"),
    "GFEP01": (0x801E69D8, "69aa98ab8e3ec2c8abe1416bcca015b78b1b511c319902454c0c6cc9981eb9fe"),
    "GFEJ01": (0x801E0158, "1c8b8720e7c22438f3de73511fa90bcddee0989ae5977f592b49d3764a824415"),
}


def _validate(core, version):
    """r3=aligned block base, r4=physical size; record address or zero.

    Checks byte layout, region/version, UUID and reserved bits without changing
    memory. The retail CRC and game-data ID validators still remain necessary.
    """
    magic = b"FE8X" if version == "GFEP01" else b"FE8J"
    program = [
        ppc.cmplwi(4, 0x4000), ("eq", "size_ok"),
        ppc.cmplwi(4, 0x6000), ("ne", "fail"),
        "size_ok", *_address(5, 0x80000000), ppc.cmplw(3, 5), ("lt", "fail"),
        ppc.add(7, 3, 4), ppc.cmplw(7, 3), ("lt", "fail"),
        *_address(5, 0x81800000), ppc.cmplw(7, 5), ("gt", "fail"),
        ppc.lwz(5, 0x4C, 3), ppc.cmplw(5, 4), ("ne", "fail"),
        ppc.lwz(5, 0x40, 3), *_address(6, int.from_bytes(magic, "big")),
        ppc.cmplw(5, 6), ("ne", "fail"),
        ppc.lwz(5, 0x44, 3), *_address(6, xf.SAVE_VERSIONS[magic]),
        ppc.cmplw(5, 6), ("ne", "fail"),
        # Save kind 2 file, 3 Suspend, or 1: a Suspend the game has already marked as used. The
        # Japanese build marks the copy in memory before it deserializes it, so the restore sees
        # kind 1. The card-open guard skips kind 1 itself (on the card those copies are partial).
        ppc.lbz(5, 0x60, 3), ppc.cmplwi(5, 1), ("lt", "fail"),
        ppc.cmplwi(5, 3), ("gt", "fail"),
        ppc.addi(6, 3, 0xB8),
    ]

    def chunk(tag, payload):
        result = [ppc.addi(5, 6, 4 + payload), ppc.cmplw(5, 7), ("gt", "fail")]
        for i, byte in enumerate(tag):
            result += [ppc.lbz(5, i, 6), ppc.cmplwi(5, byte), ("ne", "fail")]
        return result + [ppc.addi(6, 6, 4 + payload)]

    program += chunk(b"BMST", 0x214) + chunk(b"MDST", 0x20) + chunk(b"UNIP", 0)
    program += [
        ppc.li(8, 159), "unit", ppc.addi(5, 6, 2), ppc.cmplw(5, 7), ("gt", "fail"),
        ppc.lbz(9, 0, 6), ppc.cmpwi(9, 0), ("ne", "occupied"),
        ppc.lbz(9, 1, 6), ppc.cmpwi(9, 0), ("eq", "empty"),
        "occupied", ppc.addi(5, 6, 143), ppc.cmplw(5, 7), ("gt", "fail"),
        "empty", ppc.mr(6, 5), ppc.addi(8, 8, -1), ppc.cmpwi(8, 0), ("ne", "unit"),
    ]
    program += chunk(b"SOKO", 800) + chunk(b"FWEP", 1152) + chunk(b"T  T", 516)
    program += [
        ppc.addi(5, 6, xf.RECORD_SIZE), ppc.cmplw(5, 7), ("gt", "fail"),
        ppc.mr(10, 6), *_address(11, core.record_address), ppc.li(12, xf.HEADER.size),
        "header", ppc.lbz(5, 0, 10), ppc.lbz(9, 0, 11),
        ppc.cmplw(5, 9), ("ne", "fail"), ppc.addi(10, 10, 1), ppc.addi(11, 11, 1),
        ppc.addi(12, 12, -1), ppc.cmpwi(12, 0), ("ne", "header"),
        ppc.lbz(5, 0, 10), ppc.cmplwi(5, 3), ("gt", "fail"),
        ppc.lbz(5, 3, 10), ppc.cmpwi(5, 0), ("ne", "fail"),
        ppc.mr(3, 6), ppc.BLR, "fail", ppc.li(3, 0), ppc.BLR,
    ]
    return program


def _container(core, version):
    """r3=card context with a 0x26000-byte image pointer; return 1/0.

    Ignore invalid/free blocks and consumed partial copies as retail does, but
    reject occupied blocks with incompatible versions/layouts before selection.
    """
    magic = int.from_bytes(b"FE8X" if version == "GFEP01" else b"FE8J", "big")
    return [
        ppc.stwu(1, -32, 1), ppc.MFLR_R0, ppc.stw(0, 36, 1),
        ppc.lwz(3, 0, 3), *_address(5, 0x80000000), ppc.cmplw(3, 5), ("lt", "fail"),
        *_address(5, 0x26000), ppc.add(5, 3, 5), ppc.cmplw(5, 3), ("lt", "fail"),
        *_address(6, 0x81800000), ppc.cmplw(5, 6), ("gt", "fail"),
        ppc.addi(3, 3, 0x2000), ppc.stw(3, 8, 1), ppc.li(5, 8), ppc.stw(5, 16, 1),
        "block", ppc.lwz(5, 16, 1), ppc.li(4, 0x4000), ppc.cmpwi(5, 2), ("gt", "size"),
        ppc.li(4, 0x6000), "size", ppc.stw(4, 12, 1), ppc.lwz(3, 8, 1),
        ppc.lwz(5, 0x40, 3), *_address(6, magic), ppc.cmplw(5, 6), ("ne", "next"),
        ppc.lbz(5, 0x60, 3), ppc.cmpwi(5, 1), ("eq", "next"),
        ("bl", core.base + VALIDATE_OFFSET), ppc.cmpwi(3, 0), ("eq", "fail"),
        "next", ppc.lwz(3, 8, 1), ppc.lwz(4, 12, 1), ppc.add(3, 3, 4), ppc.stw(3, 8, 1),
        ppc.lwz(5, 16, 1), ppc.addi(5, 5, -1), ppc.stw(5, 16, 1),
        ppc.cmpwi(5, 0), ("ne", "block"), ppc.li(3, 1), ("b", "return"),
        "fail", ppc.li(3, 0), "return", ppc.lwz(0, 36, 1), ppc.MTLR_R0,
        ppc.addi(1, 1, 32), ppc.BLR,
    ]


def build_load_helpers(version, core):
    if version not in ("GFEE01", "GFEP01", "GFEJ01"):
        raise ValueError("Unsupported card-load region")
    # Preserve the same registrations retail startup already established. In
    # modes 1/2/5/6/7 this is called again after startup's local reset.
    restore = [
        ppc.stwu(1, -32, 1), ppc.MFLR_R0, ppc.stw(0, 36, 1),
        ppc.stw(3, 8, 1), ppc.add(5, 3, 4), ppc.stw(5, 16, 1),
        ("bl", core.base + VALIDATE_OFFSET), ppc.cmpwi(3, 0), ("eq", "return"),
        ppc.stw(3, 12, 1), ppc.addi(3, 1, 8), ppc.lwz(4, 16, 1),
        ("bl", core.functions["record_read"]), ppc.cmpwi(3, 0), ("eq", "return"),
        *_address(4, core.base + SNAPSHOT_OWNER_OFFSET), ppc.li(5, 0), ppc.stw(5, 0, 4),
        "return", ppc.lwz(0, 36, 1), ppc.MTLR_R0, ppc.addi(1, 1, 32), ppc.BLR,
    ]
    data, functions = bytearray(core.data), dict(core.functions)
    for name, offset, limit, program in (
        ("card_validate", VALIDATE_OFFSET, RESTORE_OFFSET, _validate(core, version)),
        ("card_restore", RESTORE_OFFSET, 0x2E00, restore),
        ("card_container_validate", CONTAINER_OFFSET, OPEN_OFFSET, _container(core, version)),
    ):
        code = b"".join(word.to_bytes(4, "big") for word in ppc.assemble(core.base + offset, program))
        if offset + len(code) > limit or any(data[offset:limit]):
            raise ValueError("Card-load helper slot occupied or too small")
        data[offset:offset + len(code)] = code
        functions[name] = core.base + offset
    return NativeImage(core.base, bytes(data), core.edits, functions)


def build_card_open_fragment(dol, version, core):
    """Gate the retail card-open selection call; preserve its error process flow."""
    if version not in OPEN_SITES:
        raise ValueError("Unsupported card-open region")
    caller, digest, process, process_digest, selection = OPEN_SITES[version]
    for edit in core.edits:
        if dol.read(edit.address, len(edit.original)) != edit.original:
            raise DolError("Card-open fragment requires matching retail inputs")
    for at, size, expected in ((caller, 76, digest), (process, 12, process_digest),
                               ERROR_SETTERS[version], ERROR_BRANCHES[version]):
        if hashlib.sha256(dol.read(at, size)).hexdigest() != expected:
            raise DolError("Card-open caller, error helper, or process label differs from retail")
    if "card_container_validate" not in core.functions:
        core = build_load_helpers(version, core)
    program = [
        ppc.stwu(1, -32, 1), ppc.MFLR_R0, ppc.stw(0, 36, 1),
        ppc.stw(3, 8, 1), ppc.stw(4, 12, 1),
        ("bl", core.functions["card_container_validate"]), ppc.cmpwi(3, 0), ("eq", "fail"),
        ppc.lwz(3, 8, 1), ppc.lwz(4, 12, 1), ("bl", selection), ("b", "return"),
        "fail", ppc.li(3, -4), ("bl", ERROR_SETTERS[version][0]),
        ppc.mr(3, 31), ("bl", ERROR_BRANCHES[version][0]),
        "return", ppc.lwz(0, 36, 1), ppc.MTLR_R0, ppc.addi(1, 1, 32), ppc.BLR,
    ]
    code = b"".join(word.to_bytes(4, "big") for word in ppc.assemble(core.base + OPEN_OFFSET, program))
    data = bytearray(core.data)
    if len(code) > 0x200 or any(data[OPEN_OFFSET:OPEN_OFFSET + 0x200]):
        raise ValueError("Card-open code slot occupied or too small")
    data[OPEN_OFFSET:OPEN_OFFSET + len(code)] = code
    site = caller + 0x34
    if dol.u32(site) != ppc.bl(site, selection):
        raise DolError("Unexpected card selection call")
    edit = Edit(site, dol.read(site, 4), ppc.bl(site, core.base + OPEN_OFFSET).to_bytes(4, "big"))
    return NativeImage(core.base, bytes(data), core.edits + (edit,),
                       {**core.functions, "card_open_guard": core.base + OPEN_OFFSET})


def build_card_read_fragment(dol, version, core):
    """Restore on every shared deserializer call, including post-startup reads.

    The input block must have passed card-open validation or have been produced
    by the complete patched writers. Card-container/version installation remains
    a release prerequisite; these fragments must never be installed alone.
    """
    if version not in READ_SITES:
        raise ValueError("Unsupported card-read region")
    if "card_open_guard" not in core.functions:
        raise ValueError("Card restore requires the pre-selection validation guard")
    for edit in core.edits:
        if dol.read(edit.address, len(edit.original)) != edit.original:
            raise DolError("Card-read fragment requires matching retail inputs")
    reader, digest = READ_SITES[version]
    if hashlib.sha256(dol.read(reader, 324)).hexdigest() != digest:
        raise DolError("Card reader differs from retail")
    site, offset = reader + 0xF8, 0x3400
    program = [
        ppc.mr(3, 31), ppc.lwz(4, 0x4C, 31), ("bl", core.functions["card_restore"]),
        ppc.cmpwi(3, 0), ("ne", "done"),
        # Defensive error reporting for an unexpected in-memory mutation after
        # validation; no extended bytes are copied on failure. The retail reader
        # is void, so this is not a replacement for the mandatory earlier guard.
        ppc.li(3, -4), ("bl", ERROR_SETTERS[version][0]),
        "done", dol.u32(site), ("b", site + 4),
    ]
    code = b"".join(word.to_bytes(4, "big") for word in ppc.assemble(core.base + offset, program))
    data = bytearray(core.data)
    if len(code) > 0x200 or any(data[offset:offset + 0x200]):
        raise ValueError("Card restore hook slot occupied or too small")
    data[offset:offset + len(code)] = code
    edit = Edit(site, dol.read(site, 4), ppc.b(site, core.base + offset).to_bytes(4, "big"))
    return NativeImage(core.base, bytes(data), core.edits + (edit,),
                       {**core.functions, "card_read_restore": core.base + offset})
