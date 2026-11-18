"""The US Radiant Dawn checks again on the European (RFEP01) and Japanese (RFEJ01) discs: a Game Data record,
the story order and a Game Code row (the RD inventory's "EU and JP discs" gap).

The RAM addresses of these builds are derived (``ram_view.RD_PARTY``); the driver stops at boot when the
process pool doesn't hold the game's processes.
"""
from __future__ import annotations

from dataclasses import replace

from . import checks_chapters, checks_code, checks_gamedata


def _copy(check, suffix: str, region: str):
    return replace(check, id=check.id + suffix, region=region, title=f"{check.title} ({region})",
                   covers=[f"{c} on {region}" for c in check.covers])


_BASE = [next(c for c in checks_gamedata.CHECKS if c.id == "G1r"),
         next(c for c in checks_chapters.CHECKS if c.id == "O1r"),
         next(c for c in checks_code.CHECKS if c.id == "K2r")]

CHECKS = [_copy(c, suffix, region) for suffix, region in (("e", "RFEP01"), ("j", "RFEJ01")) for c in _BASE]


# -- discovery: where the unit array and its pointer are on RFEP01 / RFEJ01 (the US-distance guess was wrong) -----

def discover_units(driver, facts):
    import struct
    driver.to_player_phase(8)
    mem = driver.ram.read(0x80000000, 0x1800000)
    stride, handle = 0x3F0, 0xFC
    arrays = [0x80000000 + a for a in range(0, len(mem) - stride * 4 - 0x100, 4)
              if mem[a + handle] == 1 and mem[a + stride + handle] == 2 and mem[a + 2 * stride + handle] == 3
              and mem[a + 3 * stride + handle] == 4]
    pointers = {}
    for array in arrays[:4]:
        packed = struct.pack(">I", array)
        at, found = 0, []
        while True:
            at = mem.find(packed, at)
            if at < 0 or len(found) > 8:
                break
            if at % 4 == 0:
                found.append(hex(0x80000000 + at))
            at += 1
        pointers[hex(array)] = found
    return {"arrays": [hex(a) for a in arrays[:4]], "pointers": pointers, "shot": str(driver.snap("map"))}


def judge_discovery(mod, retail, facts):
    return bool(mod["arrays"]), f"unit arrays {mod['arrays']}; words pointing at them {mod['pointers']}"


from .core import Check as _Check, Jump as _Jump  # noqa: E402

CHECKS += [_Check(f"DISC_{suffix}", "rd", f"discovery: unit array on {region}", [], play=discover_units,
                  judge=judge_discovery, start=_Jump("0101"), region=region, retail=False)
           for suffix, region in (("e", "RFEP01"), ("j", "RFEJ01"))]
