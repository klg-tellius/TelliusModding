"""Read game state from a running Dolphin: runtime units, the party data, the records they point to.

Unit layouts, seen in Dolphin on 2026-11-18 (US builds):

* Path of Radiance: 159 units of 0x280 bytes from ``0x802B14E4`` (``FUN_80015DEC``). +0x188 person record
  (FE8Data, its +0 points to the PID), +0x18C class record, +0x198 handle, +0x19A level, +0x19E/+0x19F
  tile X/Y, +0x1A8 current HP, +0x1AB.. eight stat gains (HP, Str, Mag, Skl, Spd, Lck, Def, Res), +0x1CC
  items (8 bytes each: item record pointer, uses, flags).
* Radiant Dawn: the unit array is allocated; the word at ``0x804CB810`` points to it (0x3F0-byte units,
  handle = slot + 1). +0xEC person record (FE10Data PersonData, +0 points to the PID), +0xF0 class,
  +0xFC handle, +0xFE level, +0x102/+0x103 tile X/Y, +0x114 HP, +0x1BC seven items of 0x28 bytes (record pointer,
  uses).

A record's first word points to its ID string in both games (PID, JID, IID).
"""
from __future__ import annotations

import struct
from dataclasses import dataclass, field

from tools.dolphin_ram import DolphinRam


@dataclass(frozen=True)
class Layout:
    units: int            # address of the first unit (PoR) or of the pointer to the array (RD)
    indirect: bool
    stride: int
    count: int
    person: int
    job: int
    handle: int
    x: int
    hp: int
    items: int
    item_stride: int
    item_count: int
    level: int = -1
    party: int = 0


LAYOUTS = {
    "GFEE01": Layout(0x802B14E4, False, 0x280, 159, 0x188, 0x18C, 0x198, 0x19E, 0x1A8, 0x1CC, 8, 8, 0x19A,
                     0x80330708),
    "RFEE01": Layout(0x804CB810, True, 0x3F0, 254, 0xEC, 0xF0, 0xFC, 0x102, 0x114, 0x1BC, 0x28, 7, 0xFE,
                     0x803CAB38),
}

#: Radiant Dawn's European and Japanese builds: the party data comes from the region table
#: (``rd_region_table``); the process pool and the unit-array pointer are assumed to keep their US
#: distance from it (same .bss block). :func:`check_region` confirms the pool on a running game.
RD_PARTY = {"RFEP01": 0x803C34D8, "RFEJ01": 0x803AE338}
_US = LAYOUTS["RFEE01"]
_POOL_FROM_PARTY = 0x803D9A58 - _US.party
_UNITS_FROM_PARTY = _US.units - _US.party
#: the word pointing at the unit array, found by the DISC_e / DISC_j runs (2026-11-18): the US distance from
#: the party data does not carry over (EU and JP move the .bss blocks differently)
RD_UNIT_POINTERS = {"RFEP01": 0x804C6A18, "RFEJ01": 0x804A8180}
for _code, _party in RD_PARTY.items():
    LAYOUTS[_code] = Layout(RD_UNIT_POINTERS[_code], True, _US.stride, _US.count, _US.person, _US.job,
                            _US.handle, _US.x, _US.hp, _US.items, _US.item_stride, _US.item_count, _US.level, _party)


def region_pools() -> dict:
    """``{game id: (process pool, slot size)}`` for the European and Japanese Radiant Dawn builds."""
    return {code: (party + _POOL_FROM_PARTY, 0xB0) for code, party in RD_PARTY.items()}


@dataclass
class Unit:
    address: int
    handle: int
    pid: str
    jid: str
    x: int
    y: int
    hp: int
    level: int
    items: list = field(default_factory=list)     # [(iid, uses)]
    person: int = 0                                 # record addresses
    job: int = 0


class GameRam:
    def __init__(self, ram: DolphinRam, region: str):
        self.ram = ram
        self.layout = LAYOUTS[region]

    def id_of(self, record: int) -> str:
        if not 0x80000000 <= record < 0x81800000:
            return ""
        return self.ram.cstring(self.ram.u32(record), 48)

    def unit_base(self) -> int:
        lay = self.layout
        return self.ram.u32(lay.units) if lay.indirect else lay.units

    def units(self) -> list[Unit]:
        lay = self.layout
        base = self.unit_base()
        if not base:
            return []
        raw = self.ram.read(base, lay.stride * lay.count)
        out = []
        for slot in range(lay.count):
            off = slot * lay.stride
            person = struct.unpack_from(">I", raw, off + lay.person)[0]
            if not 0x80000000 <= person < 0x81800000:
                continue
            job = struct.unpack_from(">I", raw, off + lay.job)[0]
            items = []
            for k in range(lay.item_count):
                ptr, uses = struct.unpack_from(">IB", raw, off + lay.items + k * lay.item_stride)
                if 0x80000000 <= ptr < 0x81800000:
                    items.append((self.id_of(ptr), uses, ptr))
            out.append(Unit(base + off, raw[off + lay.handle], self.id_of(person), self.id_of(job),
                            raw[off + lay.x], raw[off + lay.x + 1], raw[off + lay.hp],
                            raw[off + lay.level] if lay.level >= 0 else -1, items, person, job))
        return out

    def unit(self, pid: str) -> Unit:
        for u in self.units():
            if u.pid == pid:
                return u
        raise KeyError(f"{pid} is not on the map")

    def skills(self, unit: Unit) -> list[str]:
        """Radiant Dawn: the skill IDs in the unit's skill block (+0x12C, record pointers among other
        words). Empty on Path of Radiance (skills are a bit mask there)."""
        if not self.layout.indirect:
            return []
        out = []
        for word in struct.unpack(">36I", self.ram.read(unit.address + 0x12C, 36 * 4)):
            name = self.id_of(word) if 0x80000000 <= word < 0x81800000 else ""
            if name.startswith("SID_"):
                out.append(name)
        return out

    def record(self, address: int, length: int) -> bytes:
        return self.ram.read(address, length)

    def party(self) -> dict:
        raw = self.ram.read(self.layout.party + 0x10, 4)
        return {"chapter": raw[0], "phase": raw[1], "turn": int.from_bytes(raw[2:4], "big")}
