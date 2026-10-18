"""PowerPC core for a separate FE9 flag bank.

Builds code, immutable scoped name tables, live-registration masks, and the save
record. This module does NOT install a playable patch: persistence hooks and
regional Dolphin validation must also pass before the release gate can open.
All addresses are in a newly reserved region, never inside party_data.
"""
from __future__ import annotations

import hashlib
import struct
from dataclasses import dataclass

from . import ppc
from .catalog import Edit
from .dol import Dol, DolError
from .extended_flag_sites import PARTY, SITES, SKILL_TEST
from ..formats import extended_flags as xf
from ..formats.event_flags import flag_hash

BASE = 0x803A0000
MAX_END = 0x80500000
RECORD_OFFSET = 0x4000
LIVE_OFFSET = RECORD_OFFSET + xf.RECORD_SIZE
GLOBAL_INDEX_OFFSET = 0x4200
LOCAL_INDEX_OFFSET = 0x4400
TABLE_OFFSET = 0x5000
SNAPSHOT_OFFSET = 0x4C00
SNAPSHOT_SIZE = xf.RECORD_SIZE + 160
SNAPSHOT_OWNER_OFFSET = SNAPSHOT_OFFSET + SNAPSHOT_SIZE
ENTRY_SIZE = 20
FUNCTION_OFFSETS = {
    "arena_low": 0, "find": 0x100,
    "flag_register_local": 0x400, "flag_register_global": 0x600,
    "flag_get": 0x800, "flag_set": 0xA00, "flag_clear": 0xC00,
    "flag_reset_locals": 0xE00, "flag_init": 0x1000,
    "flag_clear_playthrough": 0x1200,
    "record_write": 0x1400, "record_read": 0x1600,
    "save_preflight": 0x1800,
}


def _address(reg: int, address: int) -> list[int]:
    return [ppc.lis(reg, ((address + 0x8000) >> 16) & 0xFFFF), ppc.addi(reg, reg, address & 0xFFFF)]


def _or(dest: int, left: int, right: int) -> int:
    return ppc._x_form(left, dest, right, 444)


@dataclass(frozen=True)
class NativeImage:
    base: int
    data: bytes
    edits: tuple[Edit, ...]
    functions: dict[str, int]

    @property
    def record_address(self) -> int:
        return self.base + RECORD_OFFSET

    @property
    def hub_address(self) -> int:
        return self.record_address + xf.HEADER.size


def _name_tables(base: int, layout: xf.FlagLayout) -> bytes:
    """Entry = hash, name pointer, value pointer, live pointer, mask, kind, pad.

    Global/hub index followed by 256 chapter indexes, each (pointer, count).
    Lookup scans only the global bucket and current chapter's bucket. Names are
    owned by this image, not by chapter scripts that can be unloaded.
    """
    groups = [[] for _ in range(257)]
    value_base = base + RECORD_OFFSET + xf.HEADER.size
    live_base = base + LIVE_OFFSET
    for name, (byte, bit) in xf.HUB_ALIASES.items():
        groups[0].append((name, value_base + byte, 0, 1 << bit, 0))
    for entry in layout.entries:
        if entry.deleted:
            continue
        campaign = entry.scope == "campaign"
        offset = 0 if campaign else xf.CAMPAIGN_SLOTS // 8
        group = 0 if campaign else entry.chapter + 1
        groups[group].append((entry.name, value_base + xf.HUB_BYTES + offset + entry.slot // 8,
                              live_base + offset + entry.slot // 8, 1 << (entry.slot % 8), 1 if campaign else 2))
    count = sum(map(len, groups))
    names_start = TABLE_OFFSET + count * ENTRY_SIZE
    encoded = [name.encode("shift_jis") + b"\0" for group in groups for name, *_ in group]
    total = (names_start + sum(map(len, encoded)) + 31) & ~31
    if base + total > MAX_END:
        raise ValueError("Extended flag names exceed the reserved runtime image budget")
    data = bytearray(total)
    data[RECORD_OFFSET:RECORD_OFFSET + xf.RECORD_SIZE] = xf.ExtendedState.for_layout(layout).build()
    table_at, name_at, name_index = TABLE_OFFSET, names_start, 0
    for index, group in enumerate(groups):
        index_at = GLOBAL_INDEX_OFFSET if index == 0 else LOCAL_INDEX_OFFSET + (index - 1) * 8
        struct.pack_into(">II", data, index_at, base + table_at, len(group))
        for name, value_ptr, live_ptr, mask, kind in group:
            raw = encoded[name_index]
            struct.pack_into(">IIIIBBH", data, table_at, flag_hash(name), base + name_at,
                             value_ptr, live_ptr, mask, kind, 0)
            data[name_at:name_at + len(raw)] = raw
            table_at += ENTRY_SIZE
            name_at += len(raw)
            name_index += 1
    return bytes(data)


def _find(base: int, party: int) -> list:
    """Leaf: r4=name, r5=0 both/1 global/2 local; r3=entry or zero.

    Uses only volatile GPRs and CR0. Full byte comparison after hashing handles
    collisions, including signed Shift-JIS bytes in the engine's hash function.
    """
    return [
        ppc.cmpwi(4, 0), ("eq", "missing"), ppc.li(6, 0), ppc.mr(7, 4),
        "hash", ppc.lbz(8, 0, 7), ppc.cmpwi(8, 0), ("eq", "hashed"),
        ppc.extsb(8, 8), ppc.mulli(6, 6, 37), ppc.add(6, 6, 8),
        ppc.addi(7, 7, 1), ("b", "hash"),
        "hashed", ppc.cmpwi(5, 2), ("eq", "local"), ppc.li(12, 0),
        *_address(3, base + GLOBAL_INDEX_OFFSET), ppc.lwz(7, 4, 3), ppc.lwz(3, 0, 3), ("b", "scan"),
        "local", ppc.li(12, 1), *_address(8, party + 0x10), ppc.lbz(8, 0, 8),
        ppc.mulli(8, 8, 8), *_address(3, base + LOCAL_INDEX_OFFSET), ppc.add(3, 3, 8),
        ppc.lwz(7, 4, 3), ppc.lwz(3, 0, 3),
        "scan", ppc.cmpwi(7, 0), ("eq", "bucket_end"), ppc.lwz(8, 0, 3),
        ppc.cmplw(8, 6), ("ne", "next"), ppc.lwz(9, 4, 3), ppc.mr(10, 4),
        "compare", ppc.lbz(8, 0, 9), ppc.lbz(11, 0, 10), ppc.cmplw(8, 11), ("ne", "next"),
        ppc.cmpwi(8, 0), ("eq", "found"), ppc.addi(9, 9, 1), ppc.addi(10, 10, 1), ("b", "compare"),
        "next", ppc.addi(3, 3, ENTRY_SIZE), ppc.addi(7, 7, -1), ("b", "scan"),
        "bucket_end", ppc.cmpwi(12, 1), ("eq", "missing"), ppc.cmpwi(5, 1), ("ne", "local"),
        "missing", ppc.li(3, 0), "found", ppc.BLR,
    ]


def _access(base: int, party: int, operation: str, original: int, first_word: int) -> list:
    """Scoped name registration and get/set/clr; fallback executes the displaced instruction."""
    scope = 1 if operation == "flag_register_global" else 2 if operation == "flag_register_local" else 0
    program = [
        *_address(6, party + 0xB4), ppc.cmplw(3, 6), ("ne", "original"),
        ppc.stwu(1, -32, 1), ppc.MFLR_R0, ppc.stw(0, 36, 1), ppc.stw(3, 8, 1), ppc.stw(4, 12, 1),
        ppc.li(5, scope), ("bl", base + FUNCTION_OFFSETS["find"]), ppc.cmpwi(3, 0), ("eq", "fallback"),
        ppc.lbz(6, 16, 3), ppc.lwz(7, 12, 3),  # mask and live registration pointer (zero for hub)
    ]
    if scope:
        program += [ppc.cmpwi(7, 0), ("eq", "return_zero"), ppc.lbz(8, 0, 7),
                    _or(8, 8, 6), ppc.stb(8, 0, 7)]
        if scope == 1:
            program += [ppc.lwz(7, 8, 3), ppc.lbz(8, 0, 7), ppc.andc(8, 8, 6), ppc.stb(8, 0, 7)]
        program += [("b", "return_zero")]
    else:
        program += [ppc.cmpwi(7, 0), ("eq", "registered"), ppc.lbz(8, 0, 7),
                    ppc.and_(8, 8, 6), ppc.cmpwi(8, 0), ("eq", "return_zero"),
                    "registered", ppc.lwz(7, 8, 3), ppc.lbz(8, 0, 7)]
        if operation == "flag_get":
            program += [ppc.and_(8, 8, 6), ppc.cmpwi(8, 0), ("eq", "return_zero"),
                        ppc.li(3, 1), ("b", "return")]
        else:
            program += [(_or(8, 8, 6) if operation == "flag_set" else ppc.andc(8, 8, 6)),
                        ppc.stb(8, 0, 7)]
    program += [
        "return_zero", ppc.li(3, 0), "return", ppc.lwz(0, 36, 1), ppc.MTLR_R0,
        ppc.addi(1, 1, 32), ppc.BLR,
        "fallback", ppc.lwz(3, 8, 1), ppc.lwz(4, 12, 1), ppc.lwz(0, 36, 1), ppc.MTLR_R0,
        ppc.addi(1, 1, 32), "original", first_word, ("b", original + 4),
    ]
    return program


def _zero_ranges(base: int, party: int, operation: str, original: int, first_word: int) -> list:
    bits = base + RECORD_OFFSET + xf.HEADER.size
    live = base + LIVE_OFFSET
    if operation == "flag_init":
        ranges = [(bits, xf.PAYLOAD_SIZE), (live, 160), (base + SNAPSHOT_OWNER_OFFSET, 4)]
    elif operation == "flag_clear_playthrough":
        ranges = [(bits, xf.PAYLOAD_SIZE), (live + 128, 32), (base + SNAPSHOT_OWNER_OFFSET, 4)]
    else:
        ranges = [(bits + xf.HUB_BYTES + 128, 32), (live + 128, 32)]
    program = [*_address(6, party + 0xB4), ppc.cmplw(3, 6), ("ne", "original"), ppc.li(4, 0)]
    for i, (start, size) in enumerate(ranges):
        program += [*_address(5, start), ppc.li(6, size // 4), f"zero{i}", ppc.stw(4, 0, 5),
                    ppc.addi(5, 5, 4), ppc.addi(6, 6, -1), ppc.cmpwi(6, 0), ("ne", f"zero{i}")]
    return program + ["original", first_word, ("b", original + 4)]


def _record_io(base: int, *, reading: bool) -> list:
    """Leaf: r3=stream, r4=hard buffer end; return 1/0, commit only on success.

    Retail streams claim a 1 MiB capacity even for 16 KiB card blocks, so the
    caller must supply the actual allocation end. Byte copies support unaligned
    unit records. Registration masks are deliberately not part of this record.
    """
    program = [
        ppc.lwz(5, 0, 3), ppc.lwz(6, 4, 3),
        *_address(7, 0x80000000), ppc.cmplw(5, 7), ("lt", "fail"),
        *_address(7, 0x81800000), ppc.cmplw(4, 7), ("gt", "fail"),
        ppc.cmplw(6, 5), ("lt", "fail"),
        ppc.addi(8, 6, xf.RECORD_SIZE), ppc.cmplw(8, 6), ("lt", "fail"),
        ppc.cmplw(8, 4), ("gt", "fail"),
        *_address(7, base + RECORD_OFFSET),
    ]
    if reading:
        program += [
            ppc.mr(9, 6), ppc.mr(10, 7), ppc.li(11, xf.HEADER.size),
            "header", ppc.lbz(5, 0, 9), ppc.lbz(12, 0, 10),
            ppc.cmplw(5, 12), ("ne", "fail"), ppc.addi(9, 9, 1),
            ppc.addi(10, 10, 1), ppc.addi(11, 11, -1), ppc.cmpwi(11, 0), ("ne", "header"),
            ppc.lbz(5, 0, 9), ppc.cmplwi(5, 3), ("gt", "fail"),
            ppc.lbz(5, 3, 9), ppc.cmpwi(5, 0), ("ne", "fail"),
            ppc.li(11, xf.PAYLOAD_SIZE),
        ]
    else:
        program += [ppc.mr(9, 7), ppc.mr(10, 6), ppc.li(11, xf.RECORD_SIZE)]
    return program + [
        "copy", ppc.lbz(5, 0, 9), ppc.stb(5, 0, 10),
        ppc.addi(9, 9, 1), ppc.addi(10, 10, 1),
        ppc.addi(11, 11, -1), ppc.cmpwi(11, 0), ("ne", "copy"),
        ppc.stw(8, 4, 3), ppc.li(3, 1), ppc.BLR,
        "fail", ppc.li(3, 0), ppc.BLR,
    ]


def _save_preflight(skill_test: int) -> list:
    """r3=159 unit slots, r4=faction masking, r5=block bytes; size or 0.

    Must run before any target block is cleared. Calls the same skill predicate
    as retail, without temporarily moving units between factions. Invalid faction
    IDs fail closed. This helper alone does not implement the UI failure path.
    """
    return [
        ppc.stwu(1, -48, 1), ppc.MFLR_R0, ppc.stw(0, 52, 1),
        ppc.stw(3, 8, 1), ppc.stw(4, 12, 1), ppc.stw(5, 16, 1),
        ppc.li(6, 159), ppc.stw(6, 20, 1), ppc.li(6, 3558 + xf.RECORD_SIZE), ppc.stw(6, 24, 1),
        "unit", ppc.lwz(3, 8, 1), ppc.lwz(6, 0x188, 3), ppc.cmpwi(6, 0), ("eq", "next"),
        ppc.lwz(6, 12, 1), ppc.cmpwi(6, 0), ("eq", "occupied"),
        ppc.lwz(6, 0x190, 3), ppc.cmpwi(6, 0), ("eq", "fail"),
        ppc.lbz(6, 8, 6), ppc.cmplwi(6, 7), ("gt", "fail"),
        ppc.cmpwi(6, 0), ("eq", "occupied"), ppc.cmpwi(6, 5), ("ge", "occupied"),
        ppc.cmpwi(6, 4), ("eq", "next"),
        ppc.addi(3, 3, 0x1BC), ppc.li(4, 0x59), ("bl", skill_test),
        ppc.cmpwi(3, 0), ("eq", "next"),
        "occupied", ppc.lwz(6, 24, 1), ppc.addi(6, 6, 141), ppc.stw(6, 24, 1),
        "next", ppc.lwz(3, 8, 1), ppc.addi(3, 3, 0x280), ppc.stw(3, 8, 1),
        ppc.lwz(6, 20, 1), ppc.addi(6, 6, -1), ppc.stw(6, 20, 1),
        ppc.cmpwi(6, 0), ("ne", "unit"),
        ppc.lwz(3, 24, 1), ppc.lwz(5, 16, 1), ppc.cmplw(3, 5), ("le", "return"),
        "fail", ppc.li(3, 0), "return", ppc.lwz(0, 52, 1), ppc.MTLR_R0,
        ppc.addi(1, 1, 48), ppc.BLR,
    ]


def build_core(dol: Dol, version: str, layout: xf.FlagLayout, *, base: int = BASE) -> NativeImage:
    """Generate a verified core image and proposed entry edits without changing dol.

    This deliberately omits an install API: core hooks alone would lose progress
    on save/load. The complete installer must apply persistence hooks atomically.
    """
    if version not in SITES:
        raise ValueError("Unsupported extended flag runtime region")
    if base % 32 or base < BASE:
        raise ValueError("Runtime base must be 32-byte aligned above the retail boot stacks")
    from .extended_flag_metadata import append_metadata
    data = bytearray(append_metadata(_name_tables(base, layout), version, layout))
    end = base + len(data)
    if end > MAX_END:
        raise ValueError("Extended runtime metadata exceeds the reserved image budget")
    if base < dol.bss_address + dol.bss_size and end > dol.bss_address:
        raise DolError("Extended runtime overlaps BSS")
    if any(base < s.address + s.size and end > s.address for s in dol.sections):
        raise DolError("Extended runtime overlaps a DOL section")
    if len(dol.text_sections) >= 7:
        raise DolError("No DOL text section slot for the extended runtime")
    sites = SITES[version]
    for name, (address, size, digest) in {**sites, "skill_test": SKILL_TEST[version]}.items():
        if hashlib.sha256(dol.read(address, size)).hexdigest() != digest:
            raise DolError(f"{name}: retail code differs; refusing partial extended flag hooks")
    party = PARTY[version]
    programs = {"find": _find(base, party),
                "record_write": _record_io(base, reading=False),
                "record_read": _record_io(base, reading=True),
                "save_preflight": _save_preflight(SKILL_TEST[version][0])}
    edits = []
    for name, (address, _, _) in sites.items():
        first = dol.u32(address)
        if name == "arena_low":
            # OSInit calls OSSetArenaLo before clearing RAM. Every later setter
            # also respects this bound, including the debug/alternate boot path.
            programs[name] = [*_address(4, end), ppc.cmplw(3, 4), ("ge", "store"),
                              ppc.mr(3, 4), "store", first, ppc.BLR]
        elif name in ("flag_init", "flag_reset_locals", "flag_clear_playthrough"):
            programs[name] = _zero_ranges(base, party, name, address, first)
        else:
            programs[name] = _access(base, party, name, address, first)
        edits.append(Edit(address, first.to_bytes(4, "big"),
                          ppc.b(address, base + FUNCTION_OFFSETS[name]).to_bytes(4, "big")))
    functions = {name: base + offset for name, offset in FUNCTION_OFFSETS.items()}
    ordered = sorted(FUNCTION_OFFSETS.items(), key=lambda item: item[1])
    for i, (name, offset) in enumerate(ordered):
        limit = ordered[i + 1][1] if i + 1 < len(ordered) else RECORD_OFFSET
        code = b"".join(word.to_bytes(4, "big") for word in ppc.assemble(base + offset, programs[name]))
        if offset + len(code) > limit:
            raise ValueError(f"Extended runtime function {name} exceeds its code slot")
        data[offset:offset + len(code)] = code
    return NativeImage(base, bytes(data), tuple(edits), functions)
