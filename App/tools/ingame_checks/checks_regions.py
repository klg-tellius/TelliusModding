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
