"""Path of Radiance three-tier executable hooks for US, PAL, and JP.

The region-specific instruction sites are kept separate from the data-side
provisioner.  All edits verify retail bytes before writing.
"""

from __future__ import annotations

from . import ppc
from .catalog import CATALOG, CAVE_ADDRESS, Edit, Field, Patch, Tunable, in_cave

US, EU, JP = "GFEE01", "GFEP01", "GFEJ01"

# Function addresses and class-change effect descriptor in each retail DOL.
# The promotion/EXP functions have identical instruction layouts at these
# offsets; the skill loop bounds differ in the Japanese build.
_SITES = {
    US: (0x8003D538, 0x8003D13C, 0x8003863C, 0x800385E4,
         0x80196078, 0x80296734, 0x8000D3EC, 0x80196794, 0x80196704, 4),
    EU: (0x8003D6D8, 0x8003D2DC, 0x800387DC, 0x80038784,
         0x801983CC, 0x802A085C, 0x8000D514, 0x80198AE8, 0x80198A58, 4),
    JP: (0x8003C828, 0x8003C42C, 0x8003792C, 0x800378D4,
         0x80193E2C, 0x8029125C, 0x8000D3C8, 0x80194548, 0x801944B8, 2),
}

# Two disjoint gaps in the shared code cave.  The story-flow name table ends
# at +0x14B0; its process hooks start at +0x1600.
CAN_FLAG = CAVE_ADDRESS + 0xEAC
CAN_TARGET = CAVE_ADDRESS + 0xEE0
EXP_FLAG = CAVE_ADDRESS + 0xF20
EXP_TARGET = CAVE_ADDRESS + 0xF70
BASE_EXP = CAVE_ADDRESS + 0x14B0
TABLE_EXP = CAVE_ADDRESS + 0x14E0
SEAL_PREDICATE = CAVE_ADDRESS + 0x1510
CROWN_PREDICATE = CAVE_ADDRESS + 0x1530
REGISTER_CROWN = CAVE_ADDRESS + 0x1570
CROWN_DESCRIPTOR = CAVE_ADDRESS + 0x15A0
CROWN_NAME = CAVE_ADDRESS + 0x15B0
CROWN_LEVEL_CHECK = CAVE_ADDRESS + 0x15C8
AUTO_MODE = CAVE_ADDRESS + 0x15F0  # 0 = auto + Crown; 1 = Crown only
CROWN_MIN_LEVEL = CAVE_ADDRESS + 0x15F1

# All retail compare-immediate 98 sites that iterate the SkillData records.
# The two other cmpwi 98 instructions in this DOL belong to script/dialogue
# handling and are deliberately absent.
_SKILL_BOUNDS_US = """
8007DDEC:2C1B 8007DE80:2C1B 8007DE88:2C1B 8007DEA0:2C1A
8007DF34:2C1C 8007DF3C:2C1C 8007DF50:2C1A
8009FB14:2C1D 8009FBA4:2C1E 8009FC38:2C1D
80105B94:2800 80105E64:2800
80130A08:2C1C 80130AB4:2C1D
8017ABB0:2C19 8017AD50:2C1F 8017AE4C:2C1A
8017B104:2C19 8017B1DC:2C1B 8017B480:2C19
8017B9AC:2C1D 8017BA78:2C1D 8017BB44:2C1B
8017BC38:2C1D 8017BD38:2C1C 8017BDD4:2C1D
8017BF28:2C1F 8017C2E4:2C1F
801BA19C:2C1A 801BAF58:2C19 801BE9F4:2C1D
"""
_SKILL_BOUNDS_EU = """
8007EA8C:2C1B 8007EB20:2C1B 8007EB28:2C1B 8007EB40:2C1A
8007EBD4:2C1C 8007EBDC:2C1C 8007EBF0:2C1A
800A1718:2C1D 800A17A8:2C1E 800A183C:2C1D
8010636C:2800 8010663C:2800
801317D8:2C1C 80131884:2C1D
8017C5F4:2C19 8017C794:2C1F 8017C890:2C1A
8017CB80:2C1A 8017CC58:2C1B 8017CEFC:2C19
8017D428:2C1D 8017D4F4:2C1D 8017D5C0:2C1B
8017D6B4:2C1D 8017D7B4:2C1C 8017D850:2C1D
8017D9A4:2C1F 8017DD60:2C1F
801BCE9C:2C1A 801BDC58:2C19 801C16F4:2C1D
"""
_SKILL_BOUNDS_JP = """
8007CB18:2C1B 8007CBAC:2C1B 8007CBB4:2C1B 8007CBCC:2C1A
8007CC60:2C1C 8007CC68:2C1C 8007CC7C:2C1A
8009DF84:2C1D 8009E014:2C1E 8009E0A8:2C1D
8010350C:2800 801037DC:2800
8012E0F0:2C1C 8012E19C:2C1D
80178304:2C19 801784A4:2C1F 801785A0:2C1A
80178858:2C19 80178930:2C1B 80178BD4:2C19
80179160:2C1D 8017922C:2C1D 801792F8:2C1B
801793EC:2C1D 801794EC:2C1C 80179588:2C1D
801796DC:2C1F 80179A98:2C1F
801B7AA8:2C1A 801B8864:2C19 801BC300:2C1D
"""
_SKILL_BOUNDS = {US: _SKILL_BOUNDS_US, EU: _SKILL_BOUNDS_EU, JP: _SKILL_BOUNDS_JP}


def _word(word: int) -> bytes:
    return word.to_bytes(4, "big")


def _words(origin: int, program) -> bytes:
    return b"".join(map(_word, ppc.assemble(origin, program)))


def _stub(address: int, end: int, program) -> Edit:
    code = _words(address, program)
    if address + len(code) > end or not in_cave(address, len(code)):
        raise ValueError(f"Three-tier stub at {address:08X} exceeds its code cave.")
    return Edit(address, bytes(len(code)), code)


def _hook(address: int, old: int, target: int) -> Edit:
    return Edit(address, _word(old), _word(ppc.b(address, target)))


def _skill_bound_edits(version: str) -> list[Edit]:
    edits = []
    old_count = 97 if version == JP else 98
    for site in _SKILL_BOUNDS[version].split():
        address, prefix = site.split(":")
        address, prefix = int(address, 16), int(prefix, 16)
        edits.append(Edit(address, _word(prefix << 16 | old_count),
                          _word(prefix << 16 | old_count + 1)))
    return edits


def edits_for(version: str) -> tuple[Edit, ...]:
    """Retail-verified hooks, generated without reading a mutable project."""
    can, exp, base, table, register, descriptor, register_fn, seal_fn, handler, tier_bit = _SITES[version]
    edits = [
        _hook(can + 0x24, 0x4182000C, CAN_FLAG),
        _hook(can + 0x84, 0x28030000, CAN_TARGET),
        _hook(can + 0x98, 0x3800000A, CROWN_LEVEL_CHECK),
        _hook(exp + 0x98, 0x4182000C, EXP_FLAG),
        _hook(exp + 0xF8, 0x28030000, EXP_TARGET),
        _hook(base + 0x2C, 0x38030014, BASE_EXP),
        _hook(table + 0x34, 0x38030014, TABLE_EXP),
        _hook(register + 0x108, 0x80010014, REGISTER_CROWN),
        Edit(descriptor, _word(seal_fn), _word(SEAL_PREDICATE)),
        _stub(CAN_FLAG, CAN_TARGET, [
            ppc.cmpwi(3, 0), ("eq", "allow"),
            ppc.lwz(0, 0x1C8, 31), ppc.andi_(0, 0, tier_bit),
            ("ne", "reject"), "allow", ("b", can + 0x30),
            "reject", ("b", can + 0x28),
        ]),
        _stub(CAN_TARGET, EXP_FLAG, [
            ppc.cmplwi(3, 0), ("eq", "done"),
            ppc.lwz(0, 0x1BC, 31), ppc.andi_(0, 0, 4), ("eq", "done"),
            ppc.lwz(0, 0x28, 3), ppc.andi_(0, 0, tier_bit), ("ne", "done"),
            ppc.li(3, 0), "done", ppc.cmplwi(3, 0), ("b", can + 0x88),
        ]),
        _stub(EXP_FLAG, EXP_TARGET, [
            ppc.cmpwi(0, 0), ("eq", "allow"),
            ppc.lwz(0, 0x1C8, 31), ppc.andi_(0, 0, tier_bit), ("ne", "reject"),
            ppc.lis(4, 0x8000), ppc.lbz(4, AUTO_MODE & 0xFFFF, 4),
            ppc.cmpwi(4, 0), ("ne", "reject"),
            "allow", ("b", exp + 0xA4), "reject", ("b", exp + 0x9C),
        ]),
        _stub(EXP_TARGET, CAVE_ADDRESS + 0x1000, [
            ppc.cmplwi(3, 0), ("eq", "done"),
            ppc.lwz(0, 0x1BC, 31), ppc.andi_(0, 0, 4), ("eq", "done"),
            ppc.lwz(0, 0x28, 3), ppc.andi_(0, 0, tier_bit), ("ne", "done"),
            ppc.li(3, 0), "done", ppc.cmplwi(3, 0), ("b", exp + 0xFC),
        ]),
    ]
    for origin, resume, end in ((BASE_EXP, base + 0x30, TABLE_EXP),
                                (TABLE_EXP, table + 0x38, SEAL_PREDICATE)):
        edits.append(_stub(origin, end, [
            ppc.lwz(0, 0x1C8, 31), ppc.andi_(0, 0, tier_bit), ("eq", "second"),
            ppc.addi(0, 3, 40), ("b", resume),
            "second", ppc.addi(0, 3, 20), ("b", resume),
        ]))
    edits += [
        _stub(SEAL_PREDICATE, CROWN_PREDICATE, [
            ppc.lwz(0, 0x1BC, 3), ppc.andi_(0, 0, 4), ("ne", "reject"),
            ("b", can), "reject", ppc.li(3, 0), ppc.BLR,
        ]),
        _stub(CROWN_PREDICATE, REGISTER_CROWN, [
            ppc.lwz(0, 0x1BC, 3), ppc.andi_(0, 0, 4), ("eq", "reject"),
            ppc.lwz(0, 0x1C8, 3), ppc.andi_(0, 0, tier_bit), ("ne", "reject"),
            ppc.lbz(0, 0x19A, 3), ppc.lis(4, 0x8000),
            ppc.lbz(4, CROWN_MIN_LEVEL & 0xFFFF, 4), ppc.cmplw(0, 4),
            ("lt", "reject"),
            ("b", can), "reject", ppc.li(3, 0), ppc.BLR,
        ]),
        _stub(REGISTER_CROWN, CROWN_DESCRIPTOR, [
            ppc.lis(3, 0x8000), ppc.addi(3, 3, CROWN_NAME & 0xFFFF),
            ppc.lis(4, 0x8000), ppc.addi(4, 4, CROWN_DESCRIPTOR & 0xFFFF),
            ("bl", register_fn), ppc.lwz(0, 0x14, 1), ("b", register + 0x10C),
        ]),
        Edit(CROWN_DESCRIPTOR, bytes(16), _word(CROWN_PREDICATE) + _word(0x01010000)
             + _word(0) + _word(handler)),
        Edit(CROWN_NAME, bytes(len(b"IID_MASTERCROWN_UFX\x00")), b"IID_MASTERCROWN_UFX\x00"),
        _stub(CROWN_LEVEL_CHECK, AUTO_MODE, [
            ppc.lwz(0, 0x1BC, 31), ppc.andi_(0, 0, 4), ("eq", "first"),
            ppc.lis(0, 0x8000), ppc.lbz(0, CROWN_MIN_LEVEL & 0xFFFF, 0),
            ("b", can + 0x9C),
            "first", ppc.li(0, 10), ("b", can + 0x9C),
        ]),
        Edit(AUTO_MODE, b"\x00", b"\x00", wild=((0, 1),)),
        Edit(CROWN_MIN_LEVEL, b"\x00", b"\x0A", wild=((0, 1),)),
    ]
    edits.extend(_skill_bound_edits(version))
    return tuple(edits)


def us_edits() -> tuple[Edit, ...]:
    """Compatibility alias for callers that inspect the US instruction sites."""
    return edits_for(US)


PATCH = CATALOG.add(Patch(
    "promotion.three_tiers", "Promotion", "Three-tier promotions",
    "Adds SID_TIER3, a separate Master Crown item gate, and second-tier promotion. "
    "Configure class links and third-tier models in Game Data after enabling.",
    versions={version: edits_for(version) for version in _SITES},
))
AUTO_SETTING = CATALOG.add(Tunable(
    "promotion.third_tier_crown_only", "Promotion", "Third tier: Crown only (0 = auto + Crown)",
    "When set to 1, tier-two units stop at level 20 until a Master Crown is used.",
    default=0, minimum=0, maximum=1,
    versions={version: (Field(AUTO_MODE, "u8"),) for version in _SITES}, requires=(PATCH,),
))
CROWN_LEVEL_SETTING = CATALOG.add(Tunable(
    "promotion.crown_min_level", "Promotion", "Master Crown minimum level",
    "Minimum level at which a tier-two unit can use a Master Crown.",
    default=10, minimum=1, maximum=20, unit="level",
    versions={version: (Field(CROWN_MIN_LEVEL, "u8"),) for version in _SITES}, requires=(PATCH,),
))
