"""Radiant Dawn Game Code on the European and Japanese discs.

Every RD entry is written against RFEE01. This module gives each one its RFEP01 and RFEJ01
sites by moving the US sites through a stored address table (``rd_region_table``, made by
``tools/build_rd_region_table.py`` from the three retail executables with
:mod:`region_map`):

* a site address moves to the same instruction or data in the other build;
* inside the bytes, a branch to code outside the edit is re-aimed, and an address built
  from ``lis`` + a low half, or read off r2/r13, is rebuilt for the other build.

Only entries the generator checked against the other retail executable (every original
byte equal after the move) get the region; the rest stay US only.
"""

from __future__ import annotations

from dataclasses import replace
from typing import Callable

from . import ppc
from .catalog import CAVE_ADDRESS, CAVE_SIZE, Edit, Field, Patch, Tunable, in_cave
from .ppc import sext16

US = "RFEE01"
EU = "RFEP01"
JP = "RFEJ01"
REGIONS = (EU, JP)

# Addresses below this are the OS globals and the cave, which every build shares.
_FIRST_MOVABLE = 0x80004000
_LAST_MOVABLE = 0x80600000
# RFEE01's code ends here; sites past it are data, whose pointer words move instead
US_TEXT_END = 0x800068A0 + 0x35A100

_D_FORM = set(range(32, 56)) | {14}
_GPR_LOADS = {32, 33, 34, 35, 40, 41, 42, 43}
_UPDATE_FORMS = {33, 35, 37, 39, 41, 43, 45, 47, 49, 51, 53, 55}
_RA_WRITERS = {20, 21, 23, 24, 25, 26, 27, 28, 29}
_RD_WRITERS = {7, 8, 12, 13, 14, 15}

Translate = Callable[[int], "int | None"]


class NotPortable(Exception):
    """An entry's bytes can't be moved to the other build."""


def _movable(address: int, start: int, end: int) -> bool:
    return (_FIRST_MOVABLE <= address < _LAST_MOVABLE and not start <= address < end
            and not in_cave(address))


def relocate(data: bytes, us_at: int, at: int, translate: Translate,
             sda_us: tuple[int | None, int | None], sda: tuple[int | None, int | None]) -> bytes:
    """``data`` (US bytes placed at ``us_at``) rebuilt for placing at ``at`` in the other build."""
    if len(data) % 4 or us_at % 4:
        return data
    words = [int.from_bytes(data[i:i + 4], "big") for i in range(0, len(data), 4)]
    out = list(words)
    end = us_at + len(data)
    # lis register -> [word index, US high half, new high half or None]
    lis: dict[int, list] = {}

    def moved(address: int) -> int:
        if us_at <= address < end:
            return at + (address - us_at)
        if not _movable(address, us_at, end):
            return address
        new = translate(address)
        if new is None:
            raise NotPortable(f"{address:08X} has no counterpart")
        return new

    for i, w in enumerate(words):
        op, rd, ra, imm = w >> 26, (w >> 21) & 31, (w >> 16) & 31, w & 0xFFFF
        here_us, here = us_at + 4 * i, at + 4 * i
        if op == 18:
            li = w & 0x03FFFFFC
            if li & 0x02000000:
                li -= 0x04000000
            target = (li if w & 2 else here_us + li) & 0xFFFFFFFF
            new = moved(target)
            delta = new if w & 2 else new - here
            if not -0x02000000 <= delta < 0x02000000:
                raise NotPortable(f"branch at {here_us:08X} out of range")
            out[i] = (w & 0xFC000003) | (delta & 0x03FFFFFC)
            if w & 1:
                for r in range(0, 13):
                    lis.pop(r, None)
            continue
        if op == 16:
            bd = w & 0xFFFC
            if bd & 0x8000:
                bd -= 0x10000
            target = (bd if w & 2 else here_us + bd) & 0xFFFFFFFF
            new = moved(target)
            delta = new if w & 2 else new - here
            if not -0x8000 <= delta < 0x8000:
                raise NotPortable(f"conditional branch at {here_us:08X} out of range")
            out[i] = (w & 0xFFFF0003) | (delta & 0xFFFC)
            continue
        if op == 15 and ra == 0:
            lis[rd] = [i, imm, None]
            continue
        if op in _D_FORM or op == 24:
            src = rd if op == 24 else ra
            if src in lis:
                index, high, new_high = lis[src]
                address = ((high << 16) | imm) if op == 24 else ((high << 16) + sext16(imm)) & 0xFFFFFFFF
                if _movable(address, us_at, end) or us_at <= address < end:
                    new = moved(address)
                    if new_high is None:
                        new_high = (new >> 16) if op == 24 else ((new + 0x8000) >> 16) & 0xFFFF
                        lis[src][2] = new_high
                        out[index] = (words[index] & 0xFFFF0000) | new_high
                    low = new - (new_high << 16)
                    if op == 24:
                        if not 0 <= low <= 0xFFFF:
                            raise NotPortable(f"ori at {here_us:08X} no longer fits")
                    elif not -0x8000 <= low < 0x8000:
                        raise NotPortable(f"low half at {here_us:08X} no longer fits")
                    out[i] = (w & 0xFFFF0000) | (low & 0xFFFF)
            elif op != 24 and src in (2, 13):
                base_us, base = (sda_us[0], sda[0]) if src == 2 else (sda_us[1], sda[1])
                if base_us is not None and base is not None:
                    address = (base_us + sext16(imm)) & 0xFFFFFFFF
                    new = moved(address)
                    low = new - base
                    if not -0x8000 <= low < 0x8000:
                        raise NotPortable(f"small-data access at {here_us:08X} no longer fits")
                    out[i] = (w & 0xFFFF0000) | (low & 0xFFFF)
        # register writes end a lis pairing
        if op == 14 or op in _GPR_LOADS:
            lis.pop(rd, None)
        if op in _UPDATE_FORMS:
            lis.pop(ra, None)
        if op == 31:
            lis.pop(rd, None)
            lis.pop(ra, None)
        elif op in _RA_WRITERS:
            lis.pop(ra, None)
        elif op in _RD_WRITERS and op != 15:
            lis.pop(rd, None)
        elif op == 15:
            lis.pop(rd, None)
    return b"".join(x.to_bytes(4, "big") for x in out)


def relocate_pointers(data: bytes, us_at: int, at: int, translate: Translate) -> bytes:
    """Data bytes whose aligned 32-bit words that point into the executable are moved."""
    if len(data) % 4 or us_at % 4:
        return data
    out = bytearray(data)
    end = us_at + len(data)
    for i in range(0, len(data), 4):
        w = int.from_bytes(data[i:i + 4], "big")
        if us_at <= w < end:
            new = at + (w - us_at)
        elif _movable(w, us_at, end):
            new = translate(w)
            if new is None:
                raise NotPortable(f"pointer {w:08X} has no counterpart")
        else:
            continue
        out[i:i + 4] = new.to_bytes(4, "big")
    return bytes(out)


def port_edit(edit: Edit, translate: Translate, sda_us, sda) -> Edit:
    if in_cave(edit.address, edit.length):
        at = edit.address
    else:
        at = translate(edit.address)
        if at is None:
            raise NotPortable(f"site {edit.address:08X} has no counterpart")
    if edit.all_wild:
        return replace(edit, address=at, signature=None)
    if US_TEXT_END <= edit.address and not in_cave(edit.address, edit.length):
        def move(data):
            return relocate_pointers(data, edit.address, at, translate)
    else:
        def move(data):
            return relocate(data, edit.address, at, translate, sda_us, sda)
    patched = move(edit.patched)
    original = edit.original if edit.original_sha1 else move(edit.original)
    return replace(edit, address=at, original=original, patched=patched, signature=None)


def port_field(f: Field, translate: Translate) -> Field:
    if in_cave(f.address, f.span):
        return f
    at = translate(f.address)
    if at is None:
        raise NotPortable(f"value {f.address:08X} has no counterpart")
    return replace(f, address=at, signature=None)


def port_sites(entry, translate: Translate, sda_us, sda) -> tuple:
    sites = entry.versions[US]
    if isinstance(entry, Patch):
        return tuple(port_edit(e, translate, sda_us, sda) for e in sites)
    return tuple(port_field(f, translate) for f in sites)


def _table_translate(code: str) -> Translate:
    from .rd_region_table import TABLE
    column = REGIONS.index(code)

    def translate(address: int) -> int | None:
        row = TABLE.get(address)
        return None if row is None else row[column]
    return translate


def install_entry(entry) -> None:
    """Give ``entry`` its European and Japanese sites where the generator checked them (idempotent)."""
    from .rd_region_table import SDA, VERIFIED
    if US not in entry.versions:
        return
    for code in REGIONS:
        if entry.id in VERIFIED[code] and code not in entry.versions:
            entry.versions[code] = port_sites(entry, _table_translate(code), SDA[US], SDA[code])


def install(catalog) -> None:
    """:func:`install_entry` for every RD entry of ``catalog``."""
    for entry in list(catalog.entries.values()):
        install_entry(entry)


__all__ = ["US", "EU", "JP", "REGIONS", "NotPortable", "relocate", "port_edit", "port_field",
           "port_sites", "install", "install_entry", "CAVE_ADDRESS", "CAVE_SIZE", "ppc", "Tunable"]
