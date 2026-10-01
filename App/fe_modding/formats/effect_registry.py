"""Parse ``FE8Effect.bin`` - the visual-effect registry (Path of Radiance).

Never opened before this pass. Its label prefix was previously guessed at
(this codebase's own notes once called it "RID_-style", by loose analogy
with ``window/RectDesc.bin``'s real ``RID_`` labels) - that guess was wrong.
The real prefix is **``EID_``** (Effect ID), confirmed by opening the file:
263 real entries, names like ``EID_FIRE``/``EID_FIRE2``/``EID_FIRE3``/
``EID_FIRE4`` (spell tiers), ``EID_BREATHRED``/``EID_BREATHWHITE`` (dragon
breath), ``EID_CLASSCHANGE``, ``EID_COUNTER``, ``EID_DEATH``,
``EID_GODDESS``, ``EID_CLOUDOFDUST``/``EID_CLOUDOFSNOW`` (terrain dust
effects) - unambiguously a catalog of battle/combat visual effects, not a UI
layout table.

**Same 9-word (0x24-byte) header as ``anim_registry.py``'s ``FE8Anim.bin``**
- word 8 (file offset ``0x20``) is a plain record count (263) rather than a
label-pool-start pointer, confirmed the same way: a 9-word header makes the
record table (263 x 12-byte records) reach the label pool with zero leftover
bytes, where the usual 8-word header leaves a stray 4. Not a coincidence
that both files agree - this looks like a second, distinct "flat ID
registry" container shared by at least these two files, separate from
``dispo.py``/``map_file.py``/``shop.py``'s "labeled section" format.

**Record table**: 263 x 12-byte records, ``>III`` (3 big-endian u32
fields), one per ``EID_`` name (100% of records resolve their name pointer
- zero exceptions):

- Field 0: pointer to this record's own ``EID_`` name.
- Field 1: a flags word, decoded byte-by-byte. Byte 2 is **confirmed
  constant** ``5`` in all 263 records - plausibly a fixed record-type/format
  tag rather than per-effect data. Byte 0 takes only 5 distinct values (0,
  2, 4, 5, 6) across the whole file - a plausible effect-category enum,
  unconfirmed. Byte 1 ranges continuously across small integers (0-66, 55
  distinct values seen) - structurally similar to ``fe8data.py``'s skill
  ``params[0]`` finding (a small confirmed-real ID space with an unconfirmed
  meaning), but not independently confirmed as an exhaustive 0..N sequence
  the way that one was. Byte 3 is 0 on the large majority of records (252 of
  263), with a handful of small nonzero values (2, 3, 5, 7, 10) on the rest
  - too rare a signal to name with any confidence.
- Field 2: 0 on most records (210 of 263); on the other 53, a second
  pointer into the same ``EID_`` name pool. Confirmed to be a **chain
  pointer**, not a fixed sibling reference: following field 2 repeatedly
  from a "tiered" spell effect (e.g. ``EID_FIRE4`` -> ``EID_FIRE4_2`` ->
  ``EID_FIRE4_3`` -> ``EID_FIRE4_2D``) always eventually reaches a
  ``_2D``-suffixed terminal entry - real chains found up to 3 hops long.
  ``chain()`` walks this. Simpler cases are a single hop straight to a
  ``_2D`` sibling (e.g. ``EID_MEDALLION`` -> ``EID_MEDALLION_2D``). Read as
  "next effect stage/fallback to play," not decoded further (no cycles were
  found in the real file, but this wasn't proven impossible - ``chain()``
  guards against one defensively rather than assuming the data can't have
  one).

``build_effect_registry`` rebuilds the file (vanilla records give the vanilla
file byte for byte) so the Visual Effects tile can append an ``EID_`` entry.
The file is 295 records on the real disc (the 263 above was an earlier count).
"""

from __future__ import annotations

import struct
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from .common import HEADER_SIZE

TRUE_HEADER_SIZE = 0x24  # 9 words - see module docstring; NOT common.HEADER_SIZE
RECORD_SIZE = 0x0C  # 12 bytes: eid_ptr, flags, chain_ptr
SYMBOL_NAME = b"EffectData"


@dataclass(frozen=True)
class EffectRecord:
    address: int
    eid_name: str
    category: int  # flags byte 0 - 5 distinct values seen, meaning unconfirmed
    variant_id: int  # flags byte 1 - continuous small int (0-66), meaning unconfirmed
    subtype: int  # flags byte 3 - mostly 0, rare small values, low confidence
    next_in_chain: Optional[str]  # field 2, resolved - see module docstring
    flags: int = 0  # the raw flags word (field 1), kept so a rebuild is lossless


def _read_cstring(data: bytes, addr: int) -> str:
    end = data.index(b"\x00", addr)
    return data[addr:end].decode("ascii", errors="replace")


def read_effect_registry(data: bytes) -> list[EffectRecord]:
    (record_count,) = struct.unpack(">I", data[HEADER_SIZE : HEADER_SIZE + 4])
    records = []
    for i in range(record_count):
        base = TRUE_HEADER_SIZE + i * RECORD_SIZE
        eid_ptr, flags, chain_ptr = struct.unpack(">III", data[base : base + RECORD_SIZE])
        records.append(
            EffectRecord(
                address=base,
                eid_name=_read_cstring(data, eid_ptr + HEADER_SIZE),
                category=(flags >> 24) & 0xFF,
                variant_id=(flags >> 16) & 0xFF,
                subtype=flags & 0xFF,
                next_in_chain=_read_cstring(data, chain_ptr + HEADER_SIZE) if chain_ptr else None,
                flags=flags,
            )
        )
    return records


def build_effect_registry(records: list[EffectRecord]) -> bytes:
    """Build an ``FE8Effect.bin`` from records, in record order.

    Layout mirrors ``anim_registry.build_anim_registry``: count word, 12-byte
    records, a sorted NUL-separated name pool, pad to 4, then the pointer
    table (every non-zero record pointer field), a zero pair and the
    ``EffectData`` symbol name.
    """
    names = {r.eid_name for r in records} | {r.next_in_chain for r in records if r.next_in_chain}
    pool_start = 4 + len(records) * RECORD_SIZE
    offsets, pool = {}, bytearray()
    for name in sorted(names):
        offsets[name] = pool_start + len(pool)
        pool += name.encode("ascii") + b"\x00"
    data = bytearray(struct.pack(">I", len(records)))
    pointers = []
    for i, r in enumerate(records):
        base = 4 + i * RECORD_SIZE
        pointers.append(base)
        chain_ptr = 0
        if r.next_in_chain:
            pointers.append(base + 8)
            chain_ptr = offsets[r.next_in_chain]
        data += struct.pack(">III", offsets[r.eid_name], r.flags, chain_ptr)
    data += pool
    data += bytes(-len(data) % 4)
    tail = struct.pack(f">{len(pointers)}I", *pointers) + struct.pack(">II", 0, 0) + SYMBOL_NAME + b"\x00"
    size = TRUE_HEADER_SIZE - 4 + len(data) + len(tail)
    header = struct.pack(">4I", size, len(data), len(pointers), 1) + bytes(16)
    return header + bytes(data) + tail


def make_record(name: str, flags: int, next_in_chain: Optional[str] = None) -> EffectRecord:
    return EffectRecord(
        address=0,
        eid_name=name,
        category=(flags >> 24) & 0xFF,
        variant_id=(flags >> 16) & 0xFF,
        subtype=flags & 0xFF,
        next_in_chain=next_in_chain,
        flags=flags,
    )


def read_effect_registry_path(path: Path | str) -> list[EffectRecord]:
    return read_effect_registry(Path(path).read_bytes())


def chain(records: list[EffectRecord], start_name: str, _max_hops: int = 16) -> list[str]:
    """Follow next_in_chain from `start_name` to its end, returning every
    name visited (start_name first). Guards against a cycle defensively
    (see module docstring) rather than looping forever."""
    by_name = {r.eid_name: r for r in records}
    seen = []
    name = start_name
    while name is not None and name not in seen and len(seen) < _max_hops:
        seen.append(name)
        record = by_name.get(name)
        name = record.next_in_chain if record else None
    return seen
