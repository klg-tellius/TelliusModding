"""Read game state from a running Dolphin: runtime units, the party data, the records they point to.

Unit layouts, seen in Dolphin on 2026-11-18 (US builds):

* Path of Radiance: 159 units of 0x280 bytes from ``0x802B14E4`` (``FUN_80015DEC``). +0x188 person record
  (FE8Data, its +0 points to the PID), +0x18C class record, +0x198 handle, +0x19A level, +0x19E/+0x19F
  tile X/Y, +0x1A8 current HP, +0x1AB.. eight stat gains (HP, Str, Mag, Skl, Spd, Lck, Def, Res), +0x1CC
  items (8 bytes each: item record pointer, uses, flags).
* Radiant Dawn: the unit array is allocated; the word at ``0x804CB810`` points to it (0x3F0-byte units,
  handle = slot + 1). +0xEC person record (FE10Data PersonData, +0 points to the PID), +0xF0 class,
  +0xFC handle, +0x102/+0x103 tile X/Y, +0x114 HP, +0x1BC seven items of 0x28 bytes (record pointer,
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
    "RFEE01": Layout(0x804CB810, True, 0x3F0, 254, 0xEC, 0xF0, 0xFC, 0x102, 0x114, 0x1BC, 0x28, 7, -1,
                     0x803CAB38),
}


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

    def record(self, address: int, length: int) -> bytes:
        return self.ram.read(address, length)

    def party(self) -> dict:
        raw = self.ram.read(self.layout.party + 0x10, 4)
        return {"chapter": raw[0], "phase": raw[1], "turn": int.from_bytes(raw[2:4], "big")}
