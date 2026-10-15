"""Let the promotion weapon picker grant Fire, Thunder, and Wind ranks.

The retail picker offers all nine weapon types from a promoted class's ``*`` rank
positions, but its result jump table sends the three anima choices directly to
cleanup.  The physical choices add a permission flag and then run the rank
initializer.  Anima has numeric ranks at CombatActor+0x210..0x212, so each new
case starts the selected rank at 1 when it is still zero.
"""

from __future__ import annotations

from . import ppc
from .catalog import CATALOG, CAVE_ADDRESS, Edit, Patch, in_cave

US, EU, JP = "GFEE01", "GFEP01", "GFEJ01"
G_PROMOTION = "Promotion"

MAGIC_STUB = CAVE_ADDRESS + 0x600
STUB_SIZE = 6 * 4
RANK_OFFSETS = (0x210, 0x211, 0x212)  # Fire, Thunder, Wind

# (result jump table, common cleanup destination) in each retail executable.
_SITES = {
    US: (0x8029A7AC, 0x801EDDD0),
    EU: (0x802A4A34, 0x801F144C),
    JP: (0x80298BE8, 0x801EA73C),
}


def _word(value: int) -> bytes:
    return value.to_bytes(4, "big")


def _stub(address: int, rank_offset: int, resume: int) -> bytes:
    words = ppc.assemble(address, [
        ppc.lbz(0, rank_offset, 30),
        ppc.cmpwi(0, 0),
        ("ne", "resume"),
        ppc.li(0, 1),
        ppc.stb(0, rank_offset, 30),
        "resume",
        ("b", resume),
    ])
    return b"".join(map(_word, words))


def _edits(version: str) -> tuple[Edit, ...]:
    table, resume = _SITES[version]
    edits = []
    for index, rank_offset in enumerate(RANK_OFFSETS):
        address = MAGIC_STUB + index * STUB_SIZE
        code = _stub(address, rank_offset, resume)
        assert len(code) == STUB_SIZE and in_cave(address, len(code))
        edits.append(Edit(table + (index + 4) * 4, _word(resume), _word(address)))
        edits.append(Edit(address, bytes(STUB_SIZE), code))
    return tuple(edits)


CATALOG.add(Patch(
    "promotion.anima_weapon_choice", G_PROMOTION, "Grant Fire, Thunder, or Wind on promotion",
    "When a promoted class marks Fire, Thunder, or Wind with *, choosing it in the existing "
    "promotion menu starts that weapon rank at E. Existing ranks are preserved.",
    versions={version: _edits(version) for version in _SITES},
))
