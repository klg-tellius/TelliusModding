"""RFEE01 patches whose sites are confirmed against the retail US executable.

The public address repository is useful as an index, but entries live here only
after their complete original byte sequence has been checked against RFEE01
SHA-1 ``d1b8deabfec5a96bf38945665ffe203867612c1c``.  Addresses in the sheet are
file offsets; RFEE01 text1 maps them to RAM with the constant delta below.
"""

from __future__ import annotations

from . import ppc
from . import rd_regions as _rd_regions
from .catalog import CATALOG, CAVE_ADDRESS, Edit, Field, Patch, Tunable, in_cave

RFEE01 = "RFEE01"
TEXT1_DELTA = 0x800042C0

# Path of Radiance's group names (entries.py), so the Game Code page reads the same on both games
G_RD_SKILLS = "Skill activation"
G_RD_RULES = "Map and camera"
G_RD_COMBAT = "Combat rules"
G_RD_EXP = "Experience and growth"
G_RD_GROWTH = "Level-up growth"
G_RD_LAGUZ = "Laguz transformation"
G_RD_TRIANGLE = "Triangle Attack"
G_RD_RANDOM = "Random numbers"
G_RD_ECONOMY = "Gold and forge"
G_RD_PROMOTION = "Promotion"


def _at(file_offset: int) -> int:
    return TEXT1_DELTA + file_offset


def _raw(value: str) -> bytes:
    return bytes.fromhex(value)


def _word(value: int) -> bytes:
    return value.to_bytes(4, "big")


def _patch(patch_id: str, group: str, name: str, description: str,
           edits: tuple[tuple[int, str, str], ...]) -> Patch:
    return CATALOG.add(Patch(
        patch_id, group, name, description,
        {RFEE01: tuple(Edit(_at(offset), _raw(original), _raw(changed))
                       for offset, original, changed in edits)}))


def _tunable(tunable_id: str, group: str, name: str, description: str,
             default: float, minimum: float, maximum: float,
             fields: tuple[Field, ...], unit: str = "",
             requires: tuple[Patch, ...] = ()) -> Tunable:
    return CATALOG.add(Tunable(
        tunable_id, group, name, description, default, minimum, maximum,
        {RFEE01: fields}, unit=unit, requires=requires))


# -- Core combat rules ---------------------------------------------------------------------------
#
# These sites were recovered from RFEE01's combat pipeline rather than copied
# from PoR.  Hooks are deliberately local: the replacement instruction has the
# same inputs and output register as the retail two-instruction multiply-by-3.

_crit_multiplier_hook = CATALOG.add(Patch(
    "rd.combat.crit_multiplier.hook", G_RD_COMBAT, "Critical multiplier hook",
    "Internal instruction replacement used by the critical multiplier setting.",
    {RFEE01: (Edit(0x800288D4, _raw("5460103A7C030050"),
                    _word(ppc.mulli(0, 3, 3)) + _word(ppc.NOP), wild=((2, 2),)),)},
    internal=True))

_tunable(
    "rd.combat.crit_multiplier", G_RD_COMBAT, "Critical damage multiplier",
    "Multiplies a critical hit's final damage. Radiant Dawn normally deals triple damage.",
    3, 1, 9, (Field(0x800288D4, "imm16s", b"\x1c\x03"),), "x",
    (_crit_multiplier_hook,))

_tunable(
    "rd.combat.doubling_threshold", G_RD_COMBAT, "Doubling speed threshold",
    "Required attack-speed advantage for a follow-up attack.",
    4, 1, 30,
    (Field(0x8002B9F4, "imm16s", b"\x38\x63"),
     Field(0x8002BA88, "imm16s", b"\x38\x63")), "AS")

_tunable(
    "rd.skill.wrath.crit_bonus", G_RD_SKILLS, "Wrath critical bonus",
    "Critical-hit bonus granted by Wrath while its HP condition is met.",
    50, 0, 100, (Field(0x80028820, "imm16s", b"\x38\x63"),), "%")

CATALOG.add(Patch(
    "rd.combat.single_roll_hit", G_RD_COMBAT, "Use one RN for hit rates",
    "Uses one random number for ordinary hit checks instead of Radiant Dawn's averaged two-RN roll.",
    {RFEE01: (Edit(0x8002FF9C, _word(ppc.bl(0x8002FF9C, 0x80089DE8)),
                    _word(ppc.bl(0x8002FF9C, 0x80089D68))),)}))

_effectiveness_hook = CATALOG.add(Patch(
    "rd.combat.effectiveness.hook", G_RD_COMBAT, "Effectiveness multiplier hook",
    "Internal instruction replacement used by the effectiveness setting.",
    {RFEE01: (Edit(0x8002F37C, _raw("5460103A7C030050"),
                    _word(ppc.mulli(0, 3, 3)) + _word(ppc.NOP), wild=((2, 2),)),)},
    internal=True))

_tunable(
    "rd.combat.effectiveness_multiplier", G_RD_COMBAT, "Effective weapon multiplier",
    "Multiplier applied to the weapon-power portion of attack when a weapon is effective.",
    3, 1, 9, (Field(0x8002F37C, "imm16s", b"\x1c\x03"),), "x",
    (_effectiveness_hook,))

CATALOG.add(Patch(
    "rd.combat.no_random_crits", G_RD_COMBAT, "Disable random critical hits",
    "Makes the ordinary critical-hit roll use a zero rate. Forced combat outcomes such as triangle attacks remain separate.",
    {RFEE01: (Edit(0x8002FFB0, _raw("A87F0458"), _word(ppc.li(3, 0))),)}))

# build_combat_unit_derived_stats (0x8002F220) adds FUN_8010EF98's result to the critical rate of a
# unit with SID_CRITRISE (0x8002F838). That getter, called from nowhere else, reads GameData +0x60,
# one s16 per difficulty (the Game Data "Critical bonus with SID_CRITRISE" row, 0 on all three retail
# discs, where no class or character has the skill either). The hook rewrites
# its tail: the four difficulty indices are stored already doubled, which frees the shift, and the
# freed word multiplies the loaded bonus.
_CLASS_CRIT_TAIL = 0x8010EFF4
_class_crit_code = b"".join(_word(w) for w in (
    ppc.li(0, 2), ppc.b(0x8010EFF8, 0x8010F010), ppc.li(0, 4), ppc.b(0x8010F000, 0x8010F010),
    ppc.li(0, 6), ppc.b(0x8010F008, 0x8010F010), ppc.li(0, 0),
    ppc.add(3, 31, 0), ppc.lwz(31, 0x0C, 1), ppc.lwz(0, 0x14, 1), ppc.lha(3, 0x60, 3), ppc.MTLR_R0,
    ppc.mulli(3, 3, 1), ppc.addi(1, 1, 0x10), ppc.BLR))
_CLASS_CRIT_MULLI = _CLASS_CRIT_TAIL + _class_crit_code.index(_word(ppc.mulli(3, 3, 1)))
_class_crit_hook = CATALOG.add(Patch(
    "rd.combat.class_crit.hook", G_RD_COMBAT, "Class critical bonus hook",
    "Internal rewrite of the SID_CRITRISE bonus getter used by the class critical bonus setting.",
    {RFEE01: (Edit(_CLASS_CRIT_TAIL,
                   _raw("38000001480000183800000248000010380000034800000838000000"
                        "5400083C7C7F021483E1000C80010014A86300607C0803A638210010"
                        "4E800020"),
                   _class_crit_code, wild=((_CLASS_CRIT_MULLI - _CLASS_CRIT_TAIL + 2, 2),)),)},
    internal=True))
_tunable(
    "rd.combat.class_crit_multiplier", G_RD_COMBAT, "Class critical bonus multiplier",
    "Multiplies the critical bonus that units with SID_CRITRISE get (vanilla x1, 0 removes it). Path of "
    "Radiance's class critical bonus; in retail Radiant Dawn no class or character has the skill and the "
    "bonus (the Game Data Difficulty row 'Critical bonus with SID_CRITRISE') is 0, so this changes nothing "
    "until a class gets the skill and the bonus is set.",
    1, 0, 9, (Field(_CLASS_CRIT_MULLI, "imm16s", b"\x1c\x63"),), "x",
    (_class_crit_hook,))

# Every combat-unit constructor calls 0x8002F14C to copy the current terrain
# record's Defence, Resistance and Avoid bytes to +0x464..+0x466.  Parity uses
# the adjacent 0x8002F20C helper to clear exactly those three fields.  A tail
# branch to that native helper therefore suppresses terrain combat bonuses in
# all six construction paths without affecting terrain movement/healing or the
# later support, authority, biorhythm and map-affinity additions.
CATALOG.add(Patch(
    "rd.combat.no_terrain_bonus", G_RD_COMBAT, "Disable terrain combat bonuses",
    "Terrain grants no Defence, Resistance or Avoid in combat. Movement costs, terrain healing, supports, authority, biorhythm and map-affinity bonuses are unchanged.",
    {RFEE01: (Edit(0x8002F14C, _raw("9421FFF0"),
                    _word(ppc.b(0x8002F14C, 0x8002F20C))),)}))

# This comparator has exactly three callers: the player steal-target builder,
# the AI steal-target scan, and the AI movement search for a stealable target.
# Inventory, item eligibility, allegiance and capacity are checked by their
# respective callers after this returns.
CATALOG.add(Patch(
    "rd.combat.steal_ignores_speed", G_RD_COMBAT, "Steal from faster units",
    "A thief may steal from any eligible target regardless of Speed. Item, inventory, allegiance and capacity checks remain active for both player and AI thieves.",
    {RFEE01: (Edit(0x8011F010, _raw("54030FFE"), _word(ppc.li(3, 1))),)}))


# The shared affinity-bonus helper at 0x8002FC64 is used by battle and summary
# consumers. It accepts a paired unit within `cmplwi distance,3`, adds both
# partners' six-byte affinity vectors at their current relationship rank, then
# calls 0x80119760 once to round-and-halve all six totals. These two controls
# alter only that range gate and final halving operation.
_tunable(
    "rd.support.range", G_RD_COMBAT, "Support bonus range",
    "Farthest distance at which a paired unit grants affinity bonuses in combat.",
    3, 1, 30, (Field(0x8002FD04, "imm16u", b"\x28\x00"),), "tiles")

CATALOG.add(Patch(
    "rd.support.full_bonus", G_RD_COMBAT, "Double support bonuses",
    "Does not halve the two partners' combined affinity bonuses, doubling the retail Attack, Defence, Hit, Avoid, Critical and Critical-avoid results.",
    {RFEE01: (Edit(0x8002FD60, _raw("480E9A01"), _word(ppc.NOP)),)}))


# -- Triangle Attacks ----------------------------------------------------------------------------

CATALOG.add(Patch(
    "rd.triangle.a_allow_unpromoted", G_RD_TRIANGLE,
    "Triangle A: allow unpromoted units",
    "Removes Triangle A's Higher/Highest skill requirement while preserving its unit, weapon, position and target checks.",
    {RFEE01: (Edit(0x8002D56C, _raw("418200A4"), _word(ppc.NOP)),)}))

CATALOG.add(Patch(
    "rd.triangle.b_allow_any_weapon", G_RD_TRIANGLE,
    "Triangle B: allow any weapon type",
    "Removes Triangle B's weapon-type limit while preserving its unit, position and target checks.",
    {RFEE01: (Edit(0x8002D5F4, _raw("4181001C"), _word(ppc.NOP)),)}))

# After Triangle B has collected at least three valid SID_TRI_B units and checked
# each unit's state, equipped weapon, target reach and weapon type, this sole call
# tests whether the target point lies inside a triangle made from three candidates.
# Returning true here keeps the populated participant list and bypasses geometry only.
CATALOG.add(Patch(
    "rd.triangle.b_relaxed_formation", G_RD_TRIANGLE,
    "Triangle B: relax formation",
    "The target need not lie inside the triangle formed by the participants. Three eligible Triangle B units must still have valid equipped weapons that can reach the target.",
    {RFEE01: (Edit(0x8002D854, _raw("4BFFFAF5"), _word(ppc.li(3, 1))),)}))


# -- Experience -----------------------------------------------------------------------------------

_paragon_hook = CATALOG.add(Patch(
    "rd.exp.paragon_multiplier.hook", G_RD_EXP, "Paragon multiplier hook",
    "Internal instruction replacement used by the Paragon multiplier setting.",
    {RFEE01: (Edit(0x801207F4, _raw("57FF083C"), _word(ppc.mulli(31, 31, 2)),
                    wild=((2, 2),)),)}, internal=True))

_tunable(
    "rd.exp.paragon_multiplier", G_RD_EXP, "Paragon EXP multiplier",
    "Multiplier applied to combat experience when the unit has Paragon.",
    2, 1, 9, (Field(0x801207F4, "imm16s", b"\x1f\xff"),), "x",
    (_paragon_hook,))

_tunable(
    "rd.exp.combat_award_cap", G_RD_EXP, "Combat EXP award cap",
    "Maximum experience a single combat award may grant after Paragon and Blossom are applied.",
    100, 1, 255,
    (Field(0x80120818, "imm16u", b"\x2c\x1f"),
     Field(0x80120820, "imm16u", b"\x3b\xe0")), "EXP")


# Effective level (0x80126BA4): the unit's level (+0xFE), plus 40 with SID_HIGHEST (third tier,
# r13-0x7B5C), plus 20 with SID_HIGHER (second tier, r13-0x7B60), nothing with SID_ANIMALIZE (laguz).
# Combat EXP compares it (0x8006CA04), and so do a skill check in battle setup (0x8002A0B8), level
# comparisons (0x80121E3C) and the AI (0x8016B038, 0x8016B90C, 0x8016C21C).
_tunable(
    "rd.exp.tier2_level_bonus", G_RD_EXP, "Second-tier level bonus",
    "Levels added to a second-tier unit's effective level (vanilla 20). Combat EXP uses it, and so do "
    "some skill and AI level comparisons.",
    20, 0, 100, (Field(0x80126C08, "imm16s", b"\x3b\xff"),), "levels")
_tunable(
    "rd.exp.tier3_level_bonus", G_RD_EXP, "Third-tier level bonus",
    "Levels added to a third-tier unit's effective level (vanilla 40). Combat EXP uses it, and so do "
    "some skill and AI level comparisons.",
    40, 0, 100, (Field(0x80126BEC, "imm16s", b"\x3b\xff"),), "levels")


# -- Level-up growth -----------------------------------------------------------------------------

# Actual level-ups converge on 0x8006DCF0. Ordinary gains call 0x8006D380;
# BEXP calls 0x8006D790, which first calls the same ordinary routine and then
# trims/fills the result to its target stat count. 0x8006D380 keeps the stat
# index in nonvolatile r15 while its sole 0x8006D2C8 call returns the number of
# successful 100%-chunks/rolls in r3. The wrapper preserves the native roll,
# Blossom and cap behavior, then multiplies that result by an indexed byte.
# The all-miss fallback deliberately stays at +1: retail checks only that the
# chosen stat has some room, so a larger direct fallback could cross its cap.
_RD_GROWTH_STUB = CAVE_ADDRESS + 0xB00
_RD_GROWTH_VALUES = CAVE_ADDRESS + 0xB30
_RD_GROWTH_ROLL = 0x8006D2C8
_RD_GROWTH_CALL = 0x8006D520
_RD_GROWTH_STATS = ("HP", "Strength", "Magic", "Skill", "Speed", "Luck", "Defense", "Resistance")


def _rd_growth_stub(address: int) -> bytes:
    words = (
        ppc.stwu(1, -0x10, 1),
        ppc.MFLR_R0,
        ppc.stw(0, 0x14, 1),
        ppc.bl(address + 12, _RD_GROWTH_ROLL),
        ppc.lis(4, _RD_GROWTH_VALUES >> 16),
        ppc.addi(4, 4, _RD_GROWTH_VALUES & 0xFFFF),
        ppc.lbzx(0, 4, 15),
        ppc.mullw(3, 3, 0),
        ppc.lwz(0, 0x14, 1),
        ppc.MTLR_R0,
        ppc.addi(1, 1, 0x10),
        ppc.BLR,
    )
    return b"".join(_word(word) for word in words)


_rd_growth_code = _rd_growth_stub(_RD_GROWTH_STUB)
assert len(_rd_growth_code) == _RD_GROWTH_VALUES - _RD_GROWTH_STUB
assert in_cave(_RD_GROWTH_STUB, len(_rd_growth_code) + len(_RD_GROWTH_STATS))
_rd_growth_hook = CATALOG.add(Patch(
    "rd.growth.random_gain.hook", G_RD_GROWTH, "Growth-success payout hook",
    "Internal indexed wrapper used by the eight growth-success payout settings.",
    {RFEE01: (
        Edit(_RD_GROWTH_CALL, _raw("4BFFFDA9"),
             _word(ppc.bl(_RD_GROWTH_CALL, _RD_GROWTH_STUB))),
        Edit(_RD_GROWTH_STUB, bytes(len(_rd_growth_code)), _rd_growth_code),
        Edit(_RD_GROWTH_VALUES, bytes(len(_RD_GROWTH_STATS)),
             bytes([1]) * len(_RD_GROWTH_STATS), wild=((0, len(_RD_GROWTH_STATS)),)),
    )}, internal=True))

for _index, _stat in enumerate(_RD_GROWTH_STATS):
    _tunable(
        f"rd.growth.random.{_index}", G_RD_GROWTH,
        f"{_stat} gain per growth success",
        f"Points of {_stat} gained for each 100% growth chunk and successful remainder roll. "
        "This also affects the initial random roll used by BEXP level-ups; the separate all-miss fallback remains a cap-safe +1.",
        1, 0, 9,
        (Field(_RD_GROWTH_VALUES + _index, "u8"),),
        requires=(_rd_growth_hook,))

# BEXP counts nonzero stat gains, removes the lowest-growth gains above the
# target, and adds the highest-growth eligible stats below it. These are the
# only three comparisons against the retail value 3, and all must agree.
_tunable(
    "rd.growth.bexp_stat_count", G_RD_GROWTH, "BEXP target stat count",
    "Number of different stats a BEXP level-up tries to raise. It may grant fewer when too many stats are capped or have zero growth.",
    3, 0, 8,
    (Field(0x8006D8E8, "imm16s", b"\x2c\x14"),
     Field(0x8006DAB4, "imm16s", b"\x2c\x14"),
     Field(0x8006DCD4, "imm16s", b"\x2c\x14")), "stats")

# The dispatcher normally uses two BEXP-process predicates to choose between
# 0x8006D380 (ordinary random) and 0x8006D790 (random, then target-stat
# adjustment). Branching from the first predicate call to either native setup
# block forces that route without duplicating either growth implementation.
_patch(
    "rd.growth.force_random", G_RD_GROWTH, "Use random growth for every level",
    "Uses ordinary random growth even for BEXP level-ups, bypassing BEXP's target-stat adjustment.",
    ((0x69A4C, "481660E1", _word(ppc.b(0x8006DD0C, 0x8006DD24)).hex()),))

_patch(
    "rd.growth.force_bexp", G_RD_GROWTH, "Use BEXP growth for every level",
    "Applies the native BEXP target-stat adjustment to ordinary and BEXP level-ups.",
    ((0x69A4C, "481660E1", _word(ppc.b(0x8006DD0C, 0x8006DD34)).hex()),))

# After all eight ordinary rolls, retail forces the eligible missed stat with
# the highest growth to gain its configured payout. Skipping only that fallback
# permits a genuinely empty ordinary level while leaving every roll and cap
# check intact. BEXP may still fill to its target unless its route is bypassed.
_patch(
    "rd.growth.allow_empty_level", G_RD_GROWTH, "Allow empty random level-ups",
    "Does not force a stat gain when every ordinary growth roll misses. BEXP target-stat adjustment remains separate.",
    ((0x69430, "2C110000", _word(ppc.b(0x8006D6F0, 0x8006D77C)).hex()),))

# The shared success counter receives the unit's SID_BLOSSOM result in r4.
# Retail's sole branch selects one remainder roll when false and two attempts
# when true. Replacing that branch can apply either native behavior globally.
_patch(
    "rd.growth.blossom_for_everyone", G_RD_GROWTH, "Give everyone Blossom growth rolls",
    "Every unit gets Blossom's two attempts at each growth rate's remainder roll. Complete 100% chunks are unchanged.",
    ((0x69060, "4182002C", _word(ppc.NOP).hex()),))

_patch(
    "rd.growth.disable_blossom_reroll", G_RD_GROWTH, "Disable Blossom growth rerolls",
    "Uses one remainder roll for every unit, so Blossom no longer changes level-up growth chances.",
    ((0x69060, "4182002C", _word(ppc.b(0x8006D320, 0x8006D34C)).hex()),))


# -- Skill conditions and effects ----------------------------------------------------------------

_tunable(
    "rd.skill.resolve_hp_ratio", G_RD_SKILLS, "Resolve HP threshold",
    "Resolve becomes eligible at or below this fraction of maximum HP.",
    0.5, 0.0, 1.0, (Field(0x804CCCC8, "f32"),), "HP ratio")

_tunable(
    "rd.skill.wrath_hp_ratio", G_RD_SKILLS, "Wrath HP threshold",
    "Wrath becomes eligible at or below this fraction of maximum HP.",
    0.30000001192092896, 0.0, 1.0, (Field(0x804CCCCC, "f32"),), "HP ratio")

for _id, _name, _address, _default in (
    ("crit_up_25", "Critical +25 bonus", 0x8002F860, 25),
    ("crit_up_20", "Critical +20 bonus", 0x8002F880, 20),
    ("crit_up_15", "Critical +15 bonus", 0x8002F8A0, 15),
    ("crit_up_10", "Critical +10 bonus", 0x8002F8C0, 10),
    ("crit_up_5", "Critical +5 bonus", 0x8002F8E0, 5),
):
    _tunable(
        f"rd.skill.{_id}.bonus", G_RD_SKILLS, _name,
        "Critical-hit bonus supplied by the corresponding class skill.",
        _default, 0, 100, (Field(_address, "imm16s", b"\x38\x03"),), "%")

_tunable(
    "rd.skill.vigilance_bonus", G_RD_SKILLS, "Vigilance bonus",
    "Hit and avoid bonus granted by Vigilance.",
    20, 0, 100,
    (Field(0x8002F970, "imm16s", b"\x38\x84"),
     Field(0x8002F974, "imm16s", b"\x38\x03")), "%")

_tunable(
    "rd.skill.insight_hit_bonus", G_RD_SKILLS, "Insight hit bonus",
    "Hit bonus granted by Insight.",
    20, 0, 100, (Field(0x8002F998, "imm16s", b"\x38\x03"),), "%")

_tunable(
    "rd.skill.celerity_move_bonus", G_RD_SKILLS, "Celerity movement bonus",
    "Movement added by Celerity before equipped-item and status modifiers.",
    2, 0, 20, (Field(0x80126960, "imm16s", b"\x3b\xc0"),), "Move")

_tunable(
    "rd.skill.provoke_ai_priority", G_RD_SKILLS, "Provoke AI priority modifier",
    "AI-targeting priority added when a unit has Provoke.",
    50, -127, 127, (Field(0x80126AD4, "imm16s", b"\x3b\xe0"),))

_tunable(
    "rd.skill.shade_ai_priority", G_RD_SKILLS, "Shade AI priority modifier",
    "AI-targeting priority added when a unit has Shade; the retail value is negative.",
    -50, -127, 127, (Field(0x80126AEC, "imm16s", b"\x3b\xe0"),))

_tunable(
    "rd.skill.guard_c_bonus", G_RD_SKILLS, "Guard C-rank chance bonus",
    "Activation-rate bonus supplied by a C-rank paired-unit relationship when Guard is eligible.",
    15, 0, 100, (Field(0x8002DB1C, "imm16s", b"\x3a\xd6"),), "%")

_tunable(
    "rd.skill.guard_b_bonus", G_RD_SKILLS, "Guard B-rank chance bonus",
    "Activation-rate bonus supplied by a B-rank paired-unit relationship when Guard is eligible.",
    20, 0, 100, (Field(0x8002DB24, "imm16s", b"\x3a\xd6"),), "%")

_tunable(
    "rd.skill.guard_a_bonus", G_RD_SKILLS, "Guard A-rank chance bonus",
    "Activation-rate bonus supplied by an A-rank paired-unit relationship when Guard is eligible.",
    25, 0, 100, (Field(0x8002DB2C, "imm16s", b"\x3a\xd6"),), "%")


# Numeric activation controls. At each site r3 already contains the complete
# native chance (the named stat formula plus the current biorhythm/temporary
# modifier). The stub applies (chance * scale) / 4, adds a percentage-point
# bonus, clamps negative results to zero, and tail-calls the retail 1RN helper.
# Values above 100 intentionally remain guaranteed under the native comparison.
_RD_PROC_SCALE_DENOMINATOR = 4
_RD_PROC_STUB_BASE = CAVE_ADDRESS + 0x900
_RD_PROC_STUB_SIZE = 0x20
_RD_ROLL_PERCENT = 0x80089D68


def _rd_proc_stub(address: int) -> bytes:
    words = (
        ppc.mulli(3, 3, _RD_PROC_SCALE_DENOMINATOR),
        ppc.srawi(3, 3, 2),
        ppc.addi(3, 3, 0),
        ppc.srawi(0, 3, 31),
        ppc.andc(3, 3, 0),
        ppc.b(address + 20, _RD_ROLL_PERCENT),
    )
    return b"".join(_word(word) for word in words)


# key, label, native formula, unique roll call. These are deliberately limited
# to PoR parity rows with a direct RD semantic counterpart.
_RD_NUMERIC_PROCS = (
    ("astra", "Astra", "Skill / 2", 0x80027F4C),
    ("aether", "Aether", "Skill / 2", 0x8002803C),
    ("adept", "Adept", "Speed", 0x800280F8),
    ("luna", "Luna", "Skill / 2", 0x80029208),
    ("sol", "Sol", "Skill / 2", 0x80029868),
    ("colossus", "Colossus", "Skill / 2", 0x80028FCC),
    ("corrosion", "Corrosion", "Skill / 2", 0x8002A098),
    ("counter", "Counter", "defender Skill", 0x8002A2E4),
    ("miracle", "Miracle", "defender Luck", 0x80028E10),
    ("cancel", "Cancel", "Skill", 0x8002A228),
    ("deadeye", "Deadeye", "Skill / 2", 0x800290F0),
    ("pavise", "Pavise", "defender Skill", 0x80028CA8),
)

assert in_cave(_RD_PROC_STUB_BASE, len(_RD_NUMERIC_PROCS) * _RD_PROC_STUB_SIZE)
#: The Skill activation grid's rows: (skill, activates on, scale tunable id, bonus tunable id).
PROC_ROWS = tuple((name, formula, f"rd.skill.{key}.activation_scale", f"rd.skill.{key}.activation_bonus")
                  for key, name, formula, _site in _RD_NUMERIC_PROCS)

for _index, (_key, _name, _formula, _roll_site) in enumerate(_RD_NUMERIC_PROCS):
    _stub_address = _RD_PROC_STUB_BASE + _index * _RD_PROC_STUB_SIZE
    _hook = CATALOG.add(Patch(
        f"rd.skill.{_key}.activation_hook", G_RD_SKILLS, f"{_name} activation hook",
        f"Internal hook for {_name}'s numeric activation controls.",
        {RFEE01: (
            Edit(_roll_site, _word(ppc.bl(_roll_site, _RD_ROLL_PERCENT)),
                 _word(ppc.bl(_roll_site, _stub_address))),
            Edit(_stub_address, bytes(24), _rd_proc_stub(_stub_address),
                 wild=((2, 2), (10, 2))),
        )}, internal=True))
    _tunable(
        f"rd.skill.{_key}.activation_scale", G_RD_SKILLS, f"{_name} activation scale",
        f"{_name}'s native chance is {_formula} plus its current modifier. This multiplies that complete chance in quarters (4 = vanilla, 8 = double).",
        _RD_PROC_SCALE_DENOMINATOR, 0, 16,
        (Field(_stub_address, "imm16s", b"\x1c\x63"),), "/4", (_hook,))
    _tunable(
        f"rd.skill.{_key}.activation_bonus", G_RD_SKILLS, f"{_name} activation bonus",
        f"Percentage points added to {_name}'s chance after scaling.",
        0, -100, 100,
        (Field(_stub_address + 8, "imm16s", b"\x38\x63"),), "%", (_hook,))


# Halfshift's special 1.5x path is shared by the stat accessors. Full
# transformation uses separate integer shifts in every accessor and is not
# exposed until all of those sites can be changed atomically.
_tunable(
    "rd.laguz.halfshift_multiplier", G_RD_LAGUZ, "Halfshift stat multiplier",
    "Multiplier used for a Halfshifted laguz unit's transformed stat bonuses.",
    1.5, 0.25, 4.0, (Field(0x804CDD08, "f32"),), "x")


# -- Random numbers -----------------------------------------------------------------------------

# The main thread reads the system tick at 0x80022924 and seeds the native
# three-halfword battle/script generator, then reads it again at 0x8002292C
# and seeds the separate general-purpose generator.  Save/restore routines
# write the generator states directly and are intentionally left untouched.
_fixed_seed = CATALOG.add(Patch(
    "rd.random.fixed_seed", G_RD_RANDOM, "Same random numbers every boot",
    "Seeds both native random-number generators with an editable fixed value instead of the console timer, making the same action sequence repeat after a reset.",
    {RFEE01: (
        Edit(0x80022924, _raw("482FE121"), _word(ppc.li(3, 0)), wild=((2, 2),)),
        Edit(0x8002292C, _raw("482FE119"), _word(ppc.li(3, 0)), wild=((2, 2),)),
    )}))

_tunable(
    "rd.random.seed", G_RD_RANDOM, "Random seed",
    "Fixed seed used by both generators. Changing it turns on the fixed-seed patch and produces a different repeatable sequence.",
    0, 0, 32767,
    (Field(0x80022924, "imm16s", b"\x38\x60"),
     Field(0x8002292C, "imm16s", b"\x38\x60")),
    requires=(_fixed_seed,))


# -- Economy ------------------------------------------------------------------------------------

# The chapter record selects one of five layouts for the three party gold
# accounts.  The central setter at 0x800615DC clamps each layout with its own
# materialization of 9,999,999; all five must agree.
_tunable(
    "rd.economy.gold_cap", G_RD_ECONOMY, "Gold cap",
    "Most gold the party may hold across the active chapter accounts. Lowering the cap takes effect the next time gold is set; values above the retail seven-digit limit are intentionally unavailable.",
    9999999, 0, 9999999,
    tuple(Field(address, "lis_addi8", b"\x3c\x60\x38\x03") for address in (
        0x80061668, 0x800616B8, 0x80061708, 0x80061758,
    )) + (Field(0x800617A8, "lis_addi", b"\x3c\x60\x38\x03"),), "gold")


# RD stores the actual forge deltas in the item instance. The forge input loop
# changes Hit by +/-5 and Critical by +/-3; the ordinary item-stat accessors and
# every preview then consume those bytes directly. Cost is based on the square
# of delta / step, so replace each compiler-generated constant-division sequence
# with a local signed divw whose denominator is the same editable immediate.
def _forge_cost_hook(patch_id: str, denominator_at: int,
                     replacements: tuple[tuple[int, str], ...], default: int) -> Patch:
    return CATALOG.add(Patch(
        patch_id, G_RD_ECONOMY, "Forge cost divisor hook",
        "Internal instruction replacement that keeps forge pricing tied to the editable stat step.",
        {RFEE01: (
            Edit(denominator_at, _word(0x3CC00000 | (0x6666 if default == 5 else 0x5555)),
                 _word(ppc.li(6, default)), wild=((2, 2),)),
        ) + tuple(Edit(address, _raw(original),
                       _word(ppc.divw(3, 4, 6)) if index == 0 else _word(ppc.NOP))
                  for index, (address, original) in enumerate(replacements))},
        internal=True))


_forge_hit_cost_hook = _forge_cost_hook(
    "rd.economy.forge_hit_step.hook", 0x80112198,
    ((0x801121A8, "38666667"), (0x801121B0, "7C632096"),
     (0x801121C4, "7C630E70"), (0x801121CC, "54640FFE"),
     (0x801121D0, "7C632214")), 5)

_forge_crit_cost_hook = _forge_cost_hook(
    "rd.economy.forge_crit_step.hook", 0x80112250,
    ((0x80112260, "38665556"), (0x80112268, "7C832096"),
     (0x80112280, "54830FFE"), (0x80112284, "7C641A14")), 3)

_tunable(
    "rd.economy.forge_hit_step", G_RD_ECONOMY, "Forge Hit per step",
    "Hit gained or lost per forge input (vanilla 5). Pricing uses the same step. The fixed +/-25 Hit limit may clamp the final input when the step does not divide 25 evenly.",
    5, 1, 25,
    (Field(0x80219E80, "imm16s", b"\x38\x03"),
     Field(0x80219F10, "imm16neg", b"\x38\x03"),
     Field(0x80112198, "imm16s", b"\x38\xc0")),
    requires=(_forge_hit_cost_hook,))

_tunable(
    "rd.economy.forge_crit_step", G_RD_ECONOMY, "Forge Critical per step",
    "Critical gained or lost per forge input (vanilla 3). Pricing uses the same step. The fixed +/-15 Critical limit may clamp the final input when the step does not divide 15 evenly.",
    3, 1, 15,
    (Field(0x80219F88, "imm16s", b"\x38\x03"),
     Field(0x8021A014, "imm16neg", b"\x38\x03"),
     Field(0x80112250, "imm16s", b"\x38\xc0")),
    requires=(_forge_crit_cost_hook,))


# -- Promotion ----------------------------------------------------------------------------------

# Master Seals and Master Crowns have separate tier/weapon predicates, then converge on
# FUN_8011ff28. Its only level test is `level >= 10`; the third caller passes false for the
# level-test argument and is the base EXP preview, so this immediate covers item eligibility
# without changing the preview, scripted class changes, or automatic promotion.
_tunable(
    "rd.promotion.item_min_level", G_RD_PROMOTION, "Promotion-item minimum level",
    "Minimum level for using a Master Seal or Master Crown. Tier, class-link, weapon and special-class restrictions remain active.",
    10, 1, 20, (Field(0x8011FFA4, "imm16s", b"\x2c\x00"),), "level")


# At a class's level cap FUN_8006d19c normally sets unit flag 0x40000, which the post-combat
# dispatcher consumes to launch automatic promotion. The hook replaces only that OR instruction.
# For a SID_HIGHER (second-tier) unit it returns past the flag/global writes; otherwise it performs
# the original OR and returns normally. Item and scripted promotion paths never use this flag
# writer, and first-to-second-tier automatic promotion is retained.
_RD_CROWN_ONLY_STUB = CAVE_ADDRESS + 0xA80


def _rd_crown_only_stub(address: int) -> bytes:
    program = (
        ppc.stwu(1, -0x10, 1),
        ppc.stw(0, 8, 1),
        ppc.MFLR_R0,
        ppc.stw(0, 0x14, 1),
        ppc.addi(3, 30, 0x12C),
        ppc.lwz(4, -0x7B60, 13),       # PTR_s_SID_HIGHER
        ("bl", 0x8011B77C),           # unit_has_skill
        ppc.cmpwi(3, 0),
        ("eq", "vanilla"),
        ppc.lwz(0, 0x14, 1),
        ppc.addi(0, 0, 0x54),          # 0x8006D23C -> 0x8006D290
        ppc.MTLR_R0,
        ppc.addi(1, 1, 0x10),
        ppc.BLR,
        "vanilla",
        ppc.lwz(0, 0x14, 1),
        ppc.MTLR_R0,
        ppc.lwz(0, 8, 1),
        0x64000004,                    # oris r0,r0,4 (retail instruction)
        ppc.addi(1, 1, 0x10),
        ppc.BLR,
    )
    return b"".join(_word(word) for word in ppc.assemble(address, program))


_crown_only_code = _rd_crown_only_stub(_RD_CROWN_ONLY_STUB)
assert in_cave(_RD_CROWN_ONLY_STUB, len(_crown_only_code))
CATALOG.add(Patch(
    "rd.promotion.third_tier_crown_only", G_RD_PROMOTION,
    "Require a Master Crown for third tier",
    "Prevents second-tier units from promoting automatically at their level cap. Master Crowns and scripted class changes still work, and first-tier units still promote automatically.",
    {RFEE01: (
        Edit(0x8006D238, _raw("64000004"),
             _word(ppc.bl(0x8006D238, _RD_CROWN_ONLY_STUB))),
        Edit(_RD_CROWN_ONLY_STUB, bytes(len(_crown_only_code)), _crown_only_code),
    )}))

# Radiant Dawn's counterpart of Path of Radiance's Ike-and-thieves rule is the SID_EVENT_CC skill: the
# UnitClassChange / InstantUnitClassChange script natives promote only units that have it, and the
# shared item predicate FUN_8011FF28 refuses them (its second skill test, at 0x8011FF68). The patch
# makes that test fail; the laguz test before it, the class's promotion link and the level stay.
CATALOG.add(Patch(
    "rd.promotion.story_units_use_items", G_RD_PROMOTION,
    "Story-promoted units can use promotion items",
    "Units whose class has SID_EVENT_CC (Hero, Rogue, Light Mage and Light Sage: Ike, Sothe and Micaiah, "
    "who normally promote only through the story) can use a Master Seal or Master Crown. A later "
    "scripted class change still promotes them again if their new class has a promotion.",
    {RFEE01: (Edit(0x8011FF68, _word(ppc.bl(0x8011FF68, 0x8011B77C)), _word(ppc.li(3, 0))),)}))


# These routines normally reduce a skill-derived value to a probability.  The
# paired edits replace that calculation with the constant success result used
# by the routine's existing success branch.  Shared routines are intentionally
# represented once (Bane/Lethality and Astra/Aether).
_ACTIVATION_SITES = (
    ("vantage", "Vantage", ((0x271B7, "01", "00"), (0x271C4, "4805", "3860"))),
    ("maelstrom", "Maelstrom", ((0x2632C, "54000463", "38000000"), (0x26353, "00", "01"))),
    ("shriek", "Shriek", ((0x26280, "54000463", "38000000"), (0x262A7, "00", "01"))),
    ("quickclaw", "Quickclaw", ((0x261D4, "54000463", "38000000"), (0x261FB, "00", "01"))),
    ("howl", "Howl", ((0x26128, "54000463", "38000000"), (0x2614F, "00", "01"))),
    ("disarm", "Disarm", ((0x25E88, "54000463", "38000000"), (0x25EB7, "00", "01"))),
    ("corrosion", "Corrosion", ((0x25DAC, "54000463", "38000000"), (0x25DD3, "00", "01"))),
    ("cancel", "Cancel", ((0x25F44, "54000463", "38000000"), (0x25F63, "00", "01"))),
    ("pavise", "Pavise", ((0x249C4, "54000463", "38000000"), (0x249E3, "00", "01"))),
    ("miracle", "Miracle", ((0x24B2C, "54000463", "38000000"), (0x24B4B, "00", "01"))),
    ("adept", "Adept", ((0x23E14, "54000463", "38000000"), (0x23E33, "00", "01"))),
    ("counter", "Counter", ((0x26000, "54000463", "38000000"), (0x2601F, "00", "01"))),
    ("sol", "Sol", ((0x2557C, "54000463", "38000000"), (0x255A3, "00", "01"))),
    ("colossus", "Colossus", ((0x24CE0, "54000463", "38000000"), (0x24D07, "00", "01"))),
    ("luna", "Luna", ((0x24F1C, "54000463", "38000000"), (0x24F43, "00", "01"))),
    ("astra_aether", "Astra and Aether", ((0x23C5C, "54000463", "38000000"), (0x23C87, "00", "01"))),
    ("bane_lethality", "Bane and Lethality", ((0x25154, "54000463", "38000000"), (0x2517B, "00", "01"))),
    ("eclipse", "Eclipse", ((0x2504C, "54000463", "38000000"), (0x2507B, "00", "01"))),
)

for _id, _name, _sites in _ACTIVATION_SITES:
    _patch(f"rd.skill.{_id}.always", G_RD_SKILLS, f"{_name}: always activate",
           f"Makes {_name} pass its normal activation roll whenever its other requirements are met.", _sites)


_patch("rd.skill.renewal.twenty_percent", G_RD_SKILLS, "Renewal heals 20%",
       "Changes Renewal's per-turn healing amount to 20% of maximum HP.",
       ((0x503AE, "16", "0E"),))


# Damage-only changes preserve each skill's secondary effect.
for _id, _name, _offset, _original, _changed, _description in (
    ("deadeye", "Deadeye", 0x24E94, "B019045A", "60000000", "normal damage while retaining sleep"),
    ("sol", "Sol", 0x2561C, "B019045A", "60000000", "normal damage while retaining healing"),
    ("luna", "Luna", 0x24EF8, "7F23CB78", "60000000", "normal damage while retaining defense negation"),
    ("eclipse", "Eclipse", 0x250DC, "5400103A", "5400041E", "double rather than quintuple Strength"),
    ("savage", "Savage", 0x25AB8, "B079045A", "60000000", "normal damage while retaining Skill halving"),
    ("stun", "Stun", 0x25728, "B019045A", "60000000", "normal damage while retaining stun"),
    ("tear", "Tear", 0x25BF0, "B079045A", "60000000", "normal damage while retaining Speed halving"),
    ("rend", "Rend", 0x25980, "B079045A", "60000000", "normal damage while retaining shock"),
    ("colossus", "Colossus", 0x24D78, "5400083C", "5400057C", "double rather than triple Strength"),
    ("roar", "Roar", 0x25848, "B079045A", "60000000", "normal damage while retaining shock"),
):
    _patch(f"rd.skill.{_id}.reduced_damage", G_RD_SKILLS, f"{_name}: reduced damage",
           f"Makes {_name} deal {_description}.", ((_offset, _original, _changed),))


# Fog of war: the map loader (0x8013A35C, called from 0x8013632C) decodes mapextra bits 18-19 into the
# fog mode byte at r13-0x6810 (sight 1 -> 3, 2 -> 1, 3 -> 2), with no difficulty test, unlike Path of
# Radiance. `rlwinm r4,r4,0,12,13` becomes a constant sight code. Scripts set the byte through the
# native whose argument copy is at 0x800DC0D8 (`mr r3,r30`); "off" makes it store 0 too. A file
# resumed mid-chapter reloads its saved mode (0x80134BA8) until the next map load.
_FOG_DECODE, _FOG_SCRIPT = 0x8013A364, 0x800DC0D8
CATALOG.add(Patch(
    "rd.map.fog_off", G_RD_RULES, "Fog of war off everywhere",
    "Removes the fog of war on every map, including the scripts that turn it on during a chapter.",
    {RFEE01: (Edit(_FOG_DECODE, _raw("5484031A"), _word(ppc.li(4, 0))),
              Edit(_FOG_SCRIPT, _raw("7FC3F378"), _word(ppc.li(3, 0))))}))
CATALOG.add(Patch(
    "rd.map.fog_on", G_RD_RULES, "Fog of war on every map",
    "Every map starts with the fog of war (the mode of 3-1 and 4-2's night maps). A chapter script can "
    "change it during the chapter.",
    {RFEE01: (Edit(_FOG_DECODE, _raw("5484031A"), _word(ppc.lis(4, 8))),)}))

# Village destruction: the AI routine around 0x8015B788 asks the unit's skills for SID_VILLAGEDESTROY
# (name pointer at r13-0x7B38, held by JID_BANDIT) and skips the village search when it is absent.
# `beq` -> `b` skips it for every unit.
CATALOG.add(Patch(
    "rd.map.no_village_destruction", G_RD_RULES, "Bandits do not destroy villages",
    "Units with the village-destroying skill (SID_VILLAGEDESTROY, the Bandit class) no longer go for villages.",
    {RFEE01: (Edit(0x8015B798, _raw("418200C4"), _raw("480000C4")),)}))

# Map camera rotation: the GameCube-controller camera (method 0x80131828, vtable 0x80385EE0) turns the
# angle at +4 by 45.0 on the C-stick bits 0x01000000 / 0x02000000 of the pad's pressed word (pad method
# +0x48, `held & (held ^ previous)`), while it is under 45 / over -45, then clamps it to +-45 and snaps
# |angle| < 22.5 to 0. The same code as Path of Radiance's camera.* patches, one for one.
_RD_CAMERA_CLAMPS = (0x801318EC, 0x8013191C)     # `bge` / `ble` skipping the step at the limit
_RD_CAMERA_WRAP = 0x80131948                     # `ble +8` into the final clamps and the snap
_RD_CAMERA_STEPS = (0x801318E4, 0x80131920)      # `lfs f0,-0x6C90(r2)`, the 45.0 step (and limit)
_RD_CAMERA_ONE = 0xC002800C                      # `lfs f0,-0x7FF4(r2)`, a 1.0 constant
_RD_CAMERA_INPUT = 0x8013188C                    # `lwz r12,0x48(r12)`: the pad's pressed buttons
# The analog camera (map_camera_stick_update 0x80131628, vtable 0x80385EC0) turns the same angle by
# stick / 48 and pulls it back past -45 (bge 0x80131748) and +45 (ble 0x8013176C), then, with the stick
# centred, eases it toward 0 inside +-5 (bne 0x80131798). Free rotation makes the three branches skip.
_RD_STICK_LIMITS = ((0x80131748, "40800018", "48000018"), (0x8013176C, "40810014", "48000014"),
                    (0x80131798, "40820034", "48000034"))
CATALOG.add(Patch(
    "rd.camera.free", G_RD_RULES, "Free camera rotation",
    "The map camera turns beyond its vanilla limits: with the C-stick 45 degrees per push (GameCube "
    "controller), with the analog stick freely, without being pulled back to the front.",
    {RFEE01: (Edit(_RD_CAMERA_CLAMPS[0], _raw("4080001C"), _word(ppc.NOP)),
              Edit(_RD_CAMERA_CLAMPS[1], _raw("40810020"), _word(ppc.NOP)),
              Edit(_RD_CAMERA_WRAP, _raw("40810008"), _raw("48000040")),
              *(Edit(address, _raw(old), _raw(new)) for address, old, new in _RD_STICK_LIMITS))}))
CATALOG.add(Patch(
    "rd.camera.smooth", G_RD_RULES, "Smooth camera rotation",
    "The C-stick turns the camera 1 degree per frame while held instead of 45 degrees per push "
    "(GameCube controller). Combine with free rotation to turn all the way round.",
    {RFEE01: tuple(Edit(a, _raw("C0029370"), _word(_RD_CAMERA_ONE)) for a in _RD_CAMERA_STEPS)
     + (Edit(_RD_CAMERA_INPUT, _raw("818C0048"), _raw("818C0034")),)}))

_patch("rd.hard_mode.show_information", G_RD_RULES,
       "Hard mode: show triangle, affinity and ranges",
       "Restores weapon-triangle indicators, map-affinity information and enemy range display in Hard mode.",
       ((0x18D84B, "024082", "034082"),
        (0x4EA1B, "024182", "034182"),
        (0x639DF, "024182", "034182"),
        (0x2662B, "024182", "034182"),
        (0xF5553, "024182", "034182")))


# Army phases. bmap_phase_control_types (0x803CAB4C, state 0x803CAB38 + 0x14) is one byte per phase
# (player, enemy, other, partner): 0 the phase is skipped, 1 the player gives the orders
# (0x80043048 starts E_BMapPlph when the byte is 1), 2 the computer (0x80043078 dispatches the AI when
# it is not 0). Two chapter-start routines write 1, 2, 2, 2 with four stb on r31 (0x80060DEC in
# 0x80060D68, 0x80061140 in 0x800610F4, called from 0x800A25B4); no retail script calls the
# BMSetTanto native (setter 0x80061A78), which is left alone so a mod's script can still change them.
# As on Path of Radiance (phase_control.py), each site's first stb becomes a call to a cave routine
# that stores the four bytes from its own li immediates, and the other three become nop.
G_RD_PHASES = "Army phases"
_RD_PHASE_ROUTINE = CAVE_ADDRESS + 0x1000
_RD_PHASE_SITES = ((0x80060DEC, "9BBF0014"), (0x80061140, "9BDF0014"))  # stb r29 / stb r30, 0x14(r31)
_RD_PHASE_REST = "981F0015981F0016981F0017"  # stb r0, 0x15..0x17(r31)
_RD_PHASE_ARMIES = ("player", "enemy", "other", "partner")
_RD_PHASE_DEFAULTS = (1, 2, 2, 2)
_RD_PHASE_CHOICES = ("No phase", "Player", "Computer")


def _rd_phase_routine() -> bytes:
    words = []
    for army, default in enumerate(_RD_PHASE_DEFAULTS):
        words += [ppc.li(12, default), ppc.stb(12, 0x14 + army, 31)]
    return b"".join(_word(w) for w in words + [ppc.BLR])


_rd_phase_code = _rd_phase_routine()
assert in_cave(_RD_PHASE_ROUTINE, len(_rd_phase_code))
_RD_PHASE_HOOK = CATALOG.add(Patch(
    "rd.phases.controller.hook", G_RD_PHASES, "Army phase controller hook",
    "Chapter start reads each army's phase controller from the cave.",
    {RFEE01: tuple(Edit(site, _raw(first + _RD_PHASE_REST),
                        _word(ppc.bl(site, _RD_PHASE_ROUTINE)) + _word(ppc.NOP) * 3)
                   for site, first in _RD_PHASE_SITES)
     + (Edit(_RD_PHASE_ROUTINE, bytes(len(_rd_phase_code)), _rd_phase_code,
             wild=tuple((8 * army + 3, 1) for army in range(len(_RD_PHASE_ARMIES)))),)},
    internal=True))
for _index, (_army, _default) in enumerate(zip(_RD_PHASE_ARMIES, _RD_PHASE_DEFAULTS)):
    CATALOG.add(Tunable(
        f"rd.phases.{_army}", G_RD_PHASES, f"{_army.capitalize()} phase",
        f"Who plays the {_army} army's phase, from the next chapter start: the player, the computer, or "
        "nobody (the phase is skipped). A save keeps the setting it was made with.",
        default=_default, minimum=0, maximum=2,
        versions={RFEE01: (Field(_RD_PHASE_ROUTINE + 8 * _index + 3, "u8"),)},
        requires=(_RD_PHASE_HOOK,), choices=_RD_PHASE_CHOICES))


# -- Animation -------------------------------------------------------------------------------------
G_RD_ANIM = "Animation"

# FUN_8002C86C picks the battle's presentation: battle-flag bit 31 set is a map battle, clear the
# animated scene (FUN_80044E88). The animated path needs a player unit on one side: after the
# attacker's force byte (+0xF4 -> +8) is non-zero, `bne` at 0x8002CB68 sends a non-player defender
# to the map battle. Then FUN_801220A0 gives the unit's animation setting (0 animated; 1 and 2 are
# map battles here) and turns 0 into 1 for any non-player unit (`li r3,1` at 0x801221CC); its other
# callers only test for 2.
CATALOG.add(Patch(
    "rd.anim.ally_npc_battles", G_RD_ANIM, "Animate ally and NPC battles",
    "Battles between non-player units (allied, other and enemy armies) play the animated scene when "
    "the Animation option is On, instead of the map battle.",
    {RFEE01: (Edit(0x8002CB68, _raw("408200E8"), _word(ppc.NOP)),
              Edit(0x801221CC, _raw("38600001"), _word(ppc.NOP)))}))

# Every actor animation timer runs through FUN_800081D4, which multiplies the actor's frame rate
# (+0x5C) by a global speed float (0x804CA040, 1.0, read and written by the game through
# 0x80006CF8 / 0x80006D00) and adds it to the actor's time. The hook replaces that one global load
# with a call that also multiplies it by a float in the cave, so the game's own speed changes
# keep working on top of it.
_RD_ANIM_STUB = CAVE_ADDRESS + 0xC00
_RD_ANIM_SCALE = CAVE_ADDRESS + 0xC20
_rd_anim_code = b"".join(_word(w) for w in (
    0xC02D8000,                                   # lfs f1, speed(r13)
    ppc.lis(12, _RD_ANIM_SCALE >> 16), ppc.lfs(0, _RD_ANIM_SCALE & 0xFFFF, 12),
    ppc.fmuls(1, 1, 0), ppc.BLR))
assert in_cave(_RD_ANIM_STUB, _RD_ANIM_SCALE + 4 - _RD_ANIM_STUB)
assert len(_rd_anim_code) <= _RD_ANIM_SCALE - _RD_ANIM_STUB
_rd_anim_hook = CATALOG.add(Patch(
    "rd.anim.speed.hook", G_RD_ANIM, "Animation speed hook", "Scales the actor animation timer.",
    {RFEE01: (Edit(0x8000820C, _raw("C02D8000"), _word(ppc.bl(0x8000820C, _RD_ANIM_STUB))),
              Edit(_RD_ANIM_STUB, bytes(len(_rd_anim_code)), _rd_anim_code),
              Edit(_RD_ANIM_SCALE, bytes(4), _word(0x3F800000), wild=((0, 4),)))},
    internal=True))
CATALOG.add(Tunable(
    "rd.anim.speed", G_RD_ANIM, "Animation speed",
    "Multiplies the speed of every 3D actor animation (battle scenes, units on the map, event models). "
    "Logic keyed to animation events keeps its timing; scenes timed by fixed delays may look rushed above 2x.",
    default=1.0, minimum=0.25, maximum=8.0, unit="x",
    versions={RFEE01: (Field(_RD_ANIM_SCALE, "f32"),)}, requires=(_rd_anim_hook,)))


# European and Japanese sites, moved from the ones above (rd_regions)
_rd_regions.install(CATALOG)
