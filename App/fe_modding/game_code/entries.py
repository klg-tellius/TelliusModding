"""The patches and tunables of the game-code tab, per retail version.

Site addresses were found in the US executable (Ghidra) and carried to PAL and JP with the
byte-level function maps plus masked-signature search; ``tests/test_game_code.py`` and
``verify_catalog`` check every one against the real executables.
"""

from __future__ import annotations

import struct

from . import ppc
from .catalog import CATALOG, CAVE_ADDRESS, Edit, Field, Patch, Tunable, in_cave
from .versions import VERSIONS

US, EU, JP = "GFEE01", "GFEP01", "GFEJ01"
ALL = (US, EU, JP)

# roll_percent_chance / roll_true_hit: the combat RNG entry points
ROLL_PERCENT = {US: 0x8000CE68, EU: 0x8000CF90, JP: 0x8000CE38}
ROLL_TRUE_HIT = {US: 0x8000CD88, EU: 0x8000CEB0, JP: 0x8000CD58}

G_COMBAT = "Combat rules"
G_PROCS = "Skill activation"


def _word(value: int) -> bytes:
    return value.to_bytes(4, "big")


def _fields(kind: str, expect: bytes, sites: dict[str, tuple[int, ...]]) -> dict[str, tuple[Field, ...]]:
    return {version: tuple(Field(a, kind, expect) for a in addresses) for version, addresses in sites.items()}


# -- combat constants -----------------------------------------------------------------------------
CATALOG.add(Tunable(
    "combat.crit_multiplier", G_COMBAT, "Critical hit damage multiplier",
    "Damage is multiplied by this on a critical hit (vanilla x3).",
    default=3, minimum=1, maximum=9, unit="x",
    versions=_fields("imm16s", b"\x1c\x00", {US: (0x801A68B0,), EU: (0x801A8CE8,), JP: (0x801A4640,)})))

CATALOG.add(Tunable(
    "combat.double_attack_threshold", G_COMBAT, "Double-attack speed gap",
    "A unit attacks twice when its attack speed reaches the opponent's plus this (vanilla 4).",
    default=4, minimum=1, maximum=30, unit="AS",
    versions=_fields("imm16s", b"\x38\x03", {US: (0x801A4E68, 0x801A4F00), EU: (0x801A72A0, 0x801A7338),
                                             JP: (0x801A2C1C, 0x801A2CB4)})))

CATALOG.add(Tunable(
    "combat.wrath_crit_bonus", G_COMBAT, "Wrath critical bonus",
    "Critical rate added by Wrath at half HP or less (vanilla 50).",
    default=50, minimum=0, maximum=100, unit="%",
    versions=_fields("imm16s", b"\x38\x03", {US: (0x801A6830,), EU: (0x801A8C68,), JP: (0x801A45C0,)})))

_TRUE_HIT_SITE = {US: 0x801A8AB0, EU: 0x801AAEF8, JP: 0x801A6840}
CATALOG.add(Patch(
    "combat.single_roll_hit", G_COMBAT, "Single-roll hit chance",
    "Replaces the two-roll averaged 'true hit' with one plain roll, so displayed hit % is the real chance.",
    versions={v: (Edit(a, _word(ppc.bl(a, ROLL_TRUE_HIT[v])), _word(ppc.bl(a, ROLL_PERCENT[v]))),)
              for v, a in _TRUE_HIT_SITE.items()}))


# Weapon effectiveness doubles the attacker's Atk (`slwi r0,r0,1` in compute_forecast_stats); the
# patch turns the shift into a multiply so the factor becomes a number.
_EFFECTIVE_SITE = {US: 0x801A9084, EU: 0x801AB4CC, JP: 0x801A6E14}
_effective_hook = Patch(
    "combat.effective.hook", G_COMBAT, "Effectiveness multiplier hook", "Makes the effectiveness factor a number.",
    versions={v: (Edit(a, _word(0x5400083C), _word(0x1C000002), wild=((2, 2),)),) for v, a in _EFFECTIVE_SITE.items()},
    internal=True)
CATALOG.add(_effective_hook)
CATALOG.add(Tunable(
    "combat.effective_multiplier", G_COMBAT, "Weapon effectiveness multiplier",
    "Atk is multiplied by this against a unit the weapon is effective against (vanilla x2).",
    default=2, minimum=1, maximum=9, unit="x",
    versions=_fields("imm16s", b"\x1c\x00", {v: (a,) for v, a in _EFFECTIVE_SITE.items()}),
    requires=(_effective_hook,)))


# -- experience and growth ---------------------------------------------------------------------------
G_EXP = "Experience and growth"

# compute_growth_adjusted_value runs every EXP award and growth rate through the unit's skills:
# Elite (id 0x0B) doubles it, Frac90 (id 0x4B, the hard-mode handicap) takes 7/10 of it, and
# the result is capped at 100 (one level).
_ELITE_SITE = {US: 0x8003D0D4, EU: 0x8003D274, JP: 0x8003C3C4}
_elite_hook = Patch(
    "exp.elite.hook", G_EXP, "Elite multiplier hook", "Makes the Elite factor a number.",
    versions={v: (Edit(a, _word(0x57FF083C), _word(0x1FFF0002), wild=((2, 2),)),) for v, a in _ELITE_SITE.items()},
    internal=True)
CATALOG.add(_elite_hook)
CATALOG.add(Tunable(
    "exp.elite_multiplier", G_EXP, "Elite EXP multiplier",
    "Units with the Elite skill multiply the EXP they earn (and their growth rates) by this (vanilla x2).",
    default=2, minimum=1, maximum=9, unit="x",
    versions=_fields("imm16s", bytes.fromhex("1fff"), {v: (a,) for v, a in _ELITE_SITE.items()}),
    requires=(_elite_hook,)))
CATALOG.add(Tunable(
    "exp.frac90_tenths", G_EXP, "Frac90 EXP fraction",
    "Units with the Frac90 skill keep this many tenths of the EXP they earn (vanilla 7, at least 1 point).",
    default=7, minimum=0, maximum=20, unit="/10",
    versions=_fields("imm16s", b"\x1c\x1f", {US: (0x8003D0EC,), EU: (0x8003D28C,), JP: (0x8003C3DC,)})))
CATALOG.add(Tunable(
    "exp.cap", G_EXP, "EXP and growth cap",
    "Upper limit of a single EXP award and of a growth rate after skill adjustment (vanilla 100).",
    default=100, minimum=1, maximum=255, unit="",
    versions={
        US: (Field(0x8003D114, "imm16s", b",\x1f"), Field(0x8003D11C, "imm16s", bytes.fromhex("3be0"))),
        EU: (Field(0x8003D2B4, "imm16s", b",\x1f"), Field(0x8003D2BC, "imm16s", bytes.fromhex("3be0"))),
        JP: (Field(0x8003C404, "imm16s", b",\x1f"), Field(0x8003C40C, "imm16s", bytes.fromhex("3be0"))),
    }))
CATALOG.add(Tunable(
    "exp.promoted_level_bonus", G_EXP, "Promoted-class level bonus (EXP)",
    "Levels added to a promoted unit when EXP awards are computed (vanilla 20).",
    default=20, minimum=0, maximum=60, unit="levels",
    versions=_fields("imm16s", b"8\x03", {US: (0x80038668, 0x80038618), EU: (0x80038808, 0x800387B8),
                                              JP: (0x80037958, 0x80037908)})))


# -- Laguz transformation gauge ----------------------------------------------------------------------
G_LAGUZ = "Laguz transformation"

# update_laguz_transform_gauge_step (per turn) and FUN_8003bf5c (when struck) add to the gauge
# at `unit+0x19c` unless the unit is in the Lycanthrope (transformed) state, which drains it.
_GAUGE_MAX = {
    US: ((0x8003C0E4, 0x2C00), (0x8003C0EC, 0x3800), (0x8003C008, 0x2C00), (0x8003C010, 0x3800),
         (0x8003C184, 0x3800), (0x8003C1F0, 0x3800), (0x8003C13C, 0x3860)),
    EU: ((0x8003C284, 0x2C00), (0x8003C28C, 0x3800), (0x8003C1A8, 0x2C00), (0x8003C1B0, 0x3800),
         (0x8003C324, 0x3800), (0x8003C390, 0x3800), (0x8003C2DC, 0x3860)),
    JP: ((0x8003B3D4, 0x2C00), (0x8003B3DC, 0x3800), (0x8003B2F8, 0x2C00), (0x8003B300, 0x3800),
         (0x8003B474, 0x3800), (0x8003B4E0, 0x3800), (0x8003B42C, 0x3860)),
}


def _gauge_fields(sites: dict[str, int], opcode: bytes = b"8`") -> dict[str, tuple[Field, ...]]:
    return {v: (Field(a, "imm16s", opcode),) for v, a in sites.items()}


CATALOG.add(Tunable(
    "laguz.turn_gain", G_LAGUZ, "Gauge gain per turn",
    "Transformation gauge a Laguz gains each turn while in human form (vanilla 2).",
    default=2, minimum=0, maximum=20, unit="",
    versions=_gauge_fields({US: 0x8003C0AC, EU: 0x8003C24C, JP: 0x8003B39C})))
CATALOG.add(Tunable(
    "laguz.turn_drain", G_LAGUZ, "Gauge change per turn while transformed",
    "Added to the gauge each turn while transformed (vanilla -1; 0 keeps the form forever).",
    default=-1, minimum=-20, maximum=0, unit="",
    versions=_gauge_fields({US: 0x8003C0B4, EU: 0x8003C254, JP: 0x8003B3A4})))
CATALOG.add(Tunable(
    "laguz.hit_gain", G_LAGUZ, "Gauge gain when struck",
    "Transformation gauge a Laguz in human form gains when damaged (vanilla 4).",
    default=4, minimum=0, maximum=20, unit="",
    versions=_gauge_fields({US: 0x8003BFD0, EU: 0x8003C170, JP: 0x8003B2C0})))
CATALOG.add(Tunable(
    "laguz.hit_drain", G_LAGUZ, "Gauge change when struck while transformed",
    "Added to the gauge when a transformed Laguz is damaged (vanilla -3).",
    default=-3, minimum=-20, maximum=0, unit="",
    versions=_gauge_fields({US: 0x8003BFD8, EU: 0x8003C178, JP: 0x8003B2C8})))
CATALOG.add(Tunable(
    "laguz.gauge_max", G_LAGUZ, "Gauge size",
    "Gauge points needed to transform, which is also the most a gauge holds (vanilla 20). The on-screen gauge "
    "bar is drawn from its own scale.",
    default=20, minimum=1, maximum=100, unit="",
    versions={v: tuple(Field(a, "imm16s", op.to_bytes(2, "big")) for a, op in sites) for v, sites in _GAUGE_MAX.items()}))


# -- skill activation -----------------------------------------------------------------------------
# name, skill id, formula, (site per version), bonus allowed
PROCS = (
    ("astra", "Astra", 0x31, "Skill / 2", {US: 0x801A6638, EU: 0x801A8A70, JP: 0x801A43C8}, True),
    ("aether", "Aether", 0x4C, "Skill", {US: 0x801A66E4, EU: 0x801A8B1C, JP: 0x801A4474}, True),
    ("continue", "Continue", 0x32, "Skill", {US: 0x801A6780, EU: 0x801A8BB8, JP: 0x801A4510}, True),
    ("deathblow", "Deathblow", 0x33, "50% on a critical hit", {US: 0x801A57AC, EU: 0x801A7BE4, JP: 0x801A3560}, False),
    ("luna", "Luna", 0x30, "Skill", {US: 0x801A582C, EU: 0x801A7C64, JP: 0x801A35D4}, True),
    ("sunlight", "Sunlight", 0x5A, "Skill", {US: 0x801A58B4, EU: 0x801A7CEC, JP: 0x801A365C}, True),
    ("rumbling", "Rumbling", 0x38, "Skill", {US: 0x801A59C8, EU: 0x801A7E00, JP: 0x801A3770}, True),
    ("corrosion", "Corrosion", 0x34, "Skill", {US: 0x801A5A58, EU: 0x801A7E90, JP: 0x801A3800}, True),
    ("impact", "Impact", 0x39, "Skill / 2", {US: 0x801A5B18, EU: 0x801A7F50, JP: 0x801A38C0}, True),
    ("counter", "Counter", 0x37, "Defender's Skill / 2", {US: 0x801A5BD0, EU: 0x801A8008, JP: 0x801A396C}, True),
    ("pray", "Pray", 0x2E, "Defender's Luck", {US: 0x801A5D1C, EU: 0x801A8154, JP: 0x801A3AB8}, True),
    ("cancel", "Cancel", 0x2C, "Skill", {US: 0x801A5E10, EU: 0x801A8248, JP: 0x801A3BAC}, True),
    ("snipe", "Snipe", 0x35, "Skill / 2", {US: 0x801A5E7C, EU: 0x801A82B4, JP: 0x801A3C18}, True),
    ("wing_guard", "Wing Guard", 0x2D, "Defender's Skill", {US: 0x801A5F08, EU: 0x801A8340, JP: 0x801A3CA4}, True),
    ("sol", "Sol", 0x2F, "Skill", {US: 0x801A5FD4, EU: 0x801A840C, JP: 0x801A3D64}, True),
)

STUB_SIZE = 0x20
SCALE_DENOMINATOR = 4      # the stub computes (chance * scale) >> 2 + bonus, so scale 4 is vanilla


def _stub(version: str, address: int) -> tuple[int, ...]:
    """Adjust the chance in r3, clamp it at 0, then tail-call the real roll."""
    return (ppc.mulli(3, 3, SCALE_DENOMINATOR), ppc.srawi(3, 3, 2), ppc.addi(3, 3, 0),
            ppc.srawi(0, 3, 31), ppc.andc(3, 3, 0), ppc.b(address + 20, ROLL_PERCENT[version]))


for _index, (_key, _name, _sid, _formula, _sites, _bonus) in enumerate(PROCS):
    _stub_address = CAVE_ADDRESS + _index * STUB_SIZE
    _hook = Patch(
        f"proc.{_key}.hook", G_PROCS, f"{_name} activation hook",
        f"Routes {_name}'s activation roll through an adjustable stub.",
        versions={v: (
            Edit(site, _word(ppc.bl(site, ROLL_PERCENT[v])), _word(ppc.bl(site, _stub_address))),
            Edit(_stub_address, bytes(24), b"".join(_word(w) for w in _stub(v, _stub_address)),
                 wild=((2, 2), (10, 2))),     # the scale and bonus immediates belong to the tunables
        ) for v, site in _sites.items()}, internal=True)
    CATALOG.add(_hook)
    CATALOG.add(Tunable(
        f"proc.{_key}.scale", G_PROCS, f"{_name} activation scale",
        f"{_name} activates on {_formula}; this multiplies that chance, in quarters (4 = vanilla, 8 = double).",
        default=SCALE_DENOMINATOR, minimum=0, maximum=16, unit="/4",
        versions={v: (Field(_stub_address, "imm16s", b"\x1c\x63"),) for v in _sites},
        requires=(_hook,)))
    if _bonus:
        CATALOG.add(Tunable(
            f"proc.{_key}.bonus", G_PROCS, f"{_name} activation bonus",
            f"Percentage points added to {_name}'s chance after scaling (negative lowers it).",
            default=0, minimum=-100, maximum=100, unit="%",
            versions={v: (Field(_stub_address + 8, "imm16s", b"\x38\x63"),) for v in _sites},
            requires=(_hook,)))

assert set(VERSIONS) == set(ALL)


# -- developer tools -------------------------------------------------------------------------------
G_DEV = "Developer tools"

# Pause-menu root list: [base, 0, Kaneko, Kaneko2, Face, Akiyama, Murakami, 0]. The 0 after the
# base entry ends the list in retail, hiding the debug roots behind it; moving the roots in front
# of it shows them (Ralf's PAL codes, carried to the other builds through the function maps).
# version: (array address, base, Kaneko, Kaneko2, Face, Akiyama, Murakami)
_PAUSE_ROOTS = {
    US: (0x80286F50, 0x80367370, 0x80367790, 0x80367798, 0x803677AC, 0x803679BC, 0x80367ACC),
    EU: (0x80290F00, 0x80375638, 0x80375A58, 0x80375A60, 0x80375A74, 0x80375C64, 0x80375D7C),
    JP: (0x80281A38, 0x80364D70, 0x80365190, 0x80365198, 0x803651AC, 0x803653B4, 0x803654C4),
}


def _words(*values: int) -> bytes:
    return b"".join(_word(v) for v in values)


CATALOG.add(Patch(
    "dev.pause_menus", G_DEV, "Debug menus in the map pause menu",
    "Adds the developer menus to the pause menu on the map: Kaneko (battle and display tools, unit "
    "editor), Akiyama (storage, bases), Murakami (dialogue, flags) and Face.",
    versions={v: (Edit(a,
                       _words(base, 0, kaneko, kaneko2, face, akiyama),
                       _words(kaneko, akiyama, murakami, face, base, 0)),)
              for v, (a, base, kaneko, kaneko2, face, akiyama, murakami) in _PAUSE_ROOTS.items()}))

# GameController label 2 starts the title screen through a pointer in its process script; the
# retail game also keeps an unused development title (Import/Export memory card, Battle Previewer,
# chapter and difficulty select, build information). Label 5 then opens the file menu, which the
# cave predicate skips when the development menu chose another label (Ralf's "development mode").
# version: (start-title pointer, title script, dev title script, file-menu call operand,
#           file-menu function, "Production version" action's li r3,2)
_DEV_BOOT = {
    US: (0x802833E8, 0x8028C8E0, 0x8028C870, 0x80283408, 0x801D3B7C, 0x800A9DA8),
    EU: (0x8028D300, 0x8029685C, 0x80296800, 0x8028D320, 0x801D6BA0, 0x800AA0C0),
    JP: (0x8027E04C, 0x8028749C, 0x8028742C, 0x8027E06C, 0x801D1C88, 0x800A80F8),
}
DEV_PREDICATE = CAVE_ADDRESS + 0x1E0


def _dev_predicate(file_menu: int) -> bytes:
    """Open the file menu only when GameController's next label is still 5."""
    return _words(0x80030060, 0x28000005, 0x4C820020, ppc.b(DEV_PREDICATE + 12, file_menu))


CATALOG.add(Patch(
    "dev.boot_menu", G_DEV, "Development menu at startup",
    "Starts the game on the developer title menu: battle previewer, chapter and difficulty select, memory "
    "card import/export, build information. 'Production version' there continues to the normal file menu.",
    versions={v: (
        Edit(ptr, _word(title), _word(dev)),
        Edit(call, _word(file_menu), _word(DEV_PREDICATE)),
        Edit(DEV_PREDICATE, bytes(16), _dev_predicate(file_menu)),
        Edit(production, _word(ppc.li(3, 2)), _word(ppc.li(3, 5))),
    ) for v, (ptr, title, dev, call, file_menu, production) in _DEV_BOOT.items()}))


# -- animation ---------------------------------------------------------------------------------
G_ANIM = "Animation"

# Ally and NPC battles skip their animation because of a test on the combatant's allegiance byte
# (`bne` after `lbz r0,8(r3)`); two of them, one per side of the exchange (Ralf's PAL codes).
_ALLY_ANIM_SITES = {US: (0x801A5164, 0x801A5460), EU: (0x801A759C, 0x801A7898), JP: (0x801A2F18, 0x801A3214)}
CATALOG.add(Patch(
    "anim.ally_npc_battles", G_ANIM, "Animate ally and NPC battles",
    "Battles between non-player units play their animation instead of resolving instantly.",
    versions={v: tuple(Edit(a, _word(0x408200B4), _word(ppc.NOP)) for a in sites)
              for v, sites in _ALLY_ANIM_SITES.items()}))

# gactor_process_tick calls gactor_update_animation_timer once per GActor per frame; the hook
# scales the actor's frame-advance rate (+0x5C) around that call, from a float in the cave.
_ANIM_CALL = {US: (0x800541D4, 0x80060060), EU: (0x8005435C, 0x8005FF88), JP: (0x80053490, 0x8005F320)}
ANIM_HOOK = CAVE_ADDRESS + 0x200
ANIM_SCALE = CAVE_ADDRESS + 0x250


def _anim_hook_code(timer: int) -> bytes:
    return _words(
        ppc.stwu(1, -16, 1), ppc.MFLR_R0, ppc.stw(0, 20, 1), ppc.stw(3, 8, 1),
        ppc.lfs(0, 0x5C, 3), ppc.stfs(0, 12, 1), ppc.lis(4, 0x8000), ppc.lfs(1, ANIM_SCALE & 0xFFFF, 4),
        ppc.fmuls(0, 0, 1), ppc.stfs(0, 0x5C, 3), ppc.bl(ANIM_HOOK + 40, timer),
        ppc.lwz(3, 8, 1), ppc.lwz(0, 12, 1), ppc.stw(0, 0x5C, 3), ppc.lwz(0, 20, 1), ppc.MTLR_R0,
        ppc.addi(1, 1, 16), ppc.BLR)


_anim_hook = Patch(
    "anim.speed.hook", G_ANIM, "Animation speed hook", "Scales GActor animation time.",
    versions={v: (
        Edit(call, _word(ppc.bl(call, timer)), _word(ppc.bl(call, ANIM_HOOK))),
        Edit(ANIM_HOOK, bytes(72), _anim_hook_code(timer)),
        Edit(ANIM_SCALE, bytes(4), _word(0x3F800000), wild=((0, 4),)),     # 1.0f; the tunable's
    ) for v, (call, timer) in _ANIM_CALL.items()}, internal=True)
CATALOG.add(_anim_hook)
CATALOG.add(Tunable(
    "anim.speed", G_ANIM, "Animation speed",
    "Multiplies the speed of every 3D actor animation (battle scenes, units on the map, event models). "
    "Logic keyed to animation events keeps its timing; scenes timed by fixed delays may look rushed above 2x.",
    default=1.0, minimum=0.25, maximum=8.0, unit="x",
    versions={v: (Field(ANIM_SCALE, "f32"),) for v in _ANIM_CALL}, requires=(_anim_hook,)))


# Level-up growth sites (found in apply_random_growth_level_up / apply_fixed_growth_level_up)
_GROWTH_RANDOM = {   # 4 sites per stat (HP, Str, Mag, Skl, Spd, Lck, Def, Res): the first `li`, then three `addi`
    US: (
        0x8003428C, 0x800342A0, 0x800342D0, 0x800342E8,
        0x80034300, 0x80034318, 0x80034348, 0x80034360,
        0x80034378, 0x80034390, 0x800343C0, 0x800343D8,
        0x800343F0, 0x80034408, 0x80034438, 0x80034450,
        0x80034468, 0x80034480, 0x800344B0, 0x800344C8,
        0x800344E0, 0x800344F8, 0x80034528, 0x80034540,
        0x80034558, 0x80034570, 0x800345A0, 0x800345B8,
        0x800345D0, 0x800345E8, 0x80034618, 0x80034630,
    ),
    EU: (
        0x8003442C, 0x80034440, 0x80034470, 0x80034488,
        0x800344A0, 0x800344B8, 0x800344E8, 0x80034500,
        0x80034518, 0x80034530, 0x80034560, 0x80034578,
        0x80034590, 0x800345A8, 0x800345D8, 0x800345F0,
        0x80034608, 0x80034620, 0x80034650, 0x80034668,
        0x80034680, 0x80034698, 0x800346C8, 0x800346E0,
        0x800346F8, 0x80034710, 0x80034740, 0x80034758,
        0x80034770, 0x80034788, 0x800347B8, 0x800347D0,
    ),
    JP: (
        0x8003357C, 0x80033590, 0x800335C0, 0x800335D8,
        0x800335F0, 0x80033608, 0x80033638, 0x80033650,
        0x80033668, 0x80033680, 0x800336B0, 0x800336C8,
        0x800336E0, 0x800336F8, 0x80033728, 0x80033740,
        0x80033758, 0x80033770, 0x800337A0, 0x800337B8,
        0x800337D0, 0x800337E8, 0x80033818, 0x80033830,
        0x80033848, 0x80033860, 0x80033890, 0x800338A8,
        0x800338C0, 0x800338D8, 0x80033908, 0x80033920,
    ),
}
_GROWTH_FIXED = {     # the `addi r3,r3,1` that adds a stat's gain, in stat order
    US: (
        0x80034C24, 0x80034C44, 0x80034C64, 0x80034C84,
        0x80034CA4, 0x80034CC4, 0x80034CE4, 0x80034D04,
    ),
    EU: (
        0x80034DC4, 0x80034DE4, 0x80034E04, 0x80034E24,
        0x80034E44, 0x80034E64, 0x80034E84, 0x80034EA4,
    ),
    JP: (
        0x80033F14, 0x80033F34, 0x80033F54, 0x80033F74,
        0x80033F94, 0x80033FB4, 0x80033FD4, 0x80033FF4,
    ),
}
_GROWTH_THRESHOLDS = {US: (0x80034BF8, 0x80034C00), EU: (0x80034D98, 0x80034DA0), JP: (0x80033EE8, 0x80033EF0)}
_GROWTH_MODE_SITE = {US: 0x8014DA80, EU: 0x8014EE08, JP: 0x8014AEA8}


# -- level-up growth ---------------------------------------------------------------------------------
G_GROWTH = "Level-up growth"
STATS = ("HP", "Strength", "Magic", "Skill", "Speed", "Luck", "Defense", "Resistance")


def _hex(text: str) -> bytes:
    return bytes.fromhex(text)


# is_fixed_growth_mode_enabled ends with `srwi r3,r0,31` on the save's growth-mode bit; replacing
# that instruction with `li r3,N` pins the mode whatever the save says (Ralf's PAL code).
_MODE_WORD = _word(0x54030FFE)
CATALOG.add(Patch(
    "growth.force_fixed", G_GROWTH, "Force fixed growth mode",
    "Every save levels up with fixed growth (accumulated growth rates), whatever its own setting.",
    versions={v: (Edit(a, _MODE_WORD, _word(ppc.li(3, 1))),) for v, a in _GROWTH_MODE_SITE.items()}))
CATALOG.add(Patch(
    "growth.force_random", G_GROWTH, "Force random growth mode",
    "Every save levels up with random growth (a roll per stat), whatever its own setting.",
    versions={v: (Edit(a, _MODE_WORD, _word(ppc.li(3, 0))),) for v, a in _GROWTH_MODE_SITE.items()}))

# Random growth: each stat adds 1 for every 100% of growth and 1 for a successful roll, in four
# instructions (the first an `li`, the rest `addi`s) using r28 (HP, Magic, Speed, Defense) or r27.
_RANDOM_OPCODES = {28: (_hex("3b80"), _hex("3b9c")), 27: (_hex("3b60"), _hex("3b7b"))}
for _i, _stat in enumerate(STATS):
    _li, _addi = _RANDOM_OPCODES[28 if _i % 2 == 0 else 27]
    CATALOG.add(Tunable(
        f"growth.random.{_i}", G_GROWTH, f"{_stat} gain per growth success (random mode)",
        f"Points of {_stat} gained for each 100% of growth and for a successful roll (vanilla 1).",
        default=1, minimum=0, maximum=9, unit="",
        versions={v: tuple(Field(a, "imm16s", _li if n == 0 else _addi)
                           for n, a in enumerate(sites[4 * _i:4 * _i + 4]))
                  for v, sites in _GROWTH_RANDOM.items()}))
    CATALOG.add(Tunable(
        f"growth.fixed.{_i}", G_GROWTH, f"{_stat} gain per level (fixed mode)",
        f"Points of {_stat} gained each time its accumulated growth reaches the threshold (vanilla 1).",
        default=1, minimum=0, maximum=9, unit="",
        versions={v: (Field(sites[_i], "imm16s", _hex("3863")),) for v, sites in _GROWTH_FIXED.items()}))

CATALOG.add(Tunable(
    "growth.fixed_threshold", G_GROWTH, "Fixed growth threshold",
    "Growth points a stat accumulates per point gained in fixed mode (vanilla 100: a 40% growth gains a point "
    "every 2.5 levels). Lower is faster for every stat.",
    default=100, minimum=10, maximum=200, unit="",
    versions={v: (Field(a[0], "imm16s", _hex("3800")),) for v, a in _GROWTH_THRESHOLDS.items()}))
CATALOG.add(Tunable(
    "growth.fixed_threshold_frac90", G_GROWTH, "Fixed growth threshold with Frac90",
    "The same threshold for units with the Frac90 skill (vanilla 90, slightly easier).",
    default=90, minimum=10, maximum=200, unit="",
    versions={v: (Field(a[1], "imm16s", _hex("3800")),) for v, a in _GROWTH_THRESHOLDS.items()}))


# -- more combat rules -------------------------------------------------------------------------------
# compute_forecast_stats zeroes the crit rate when the weapon forbids criticals: `beq +8` skips it.
_NO_CRIT_SITE = {US: 0x801A9394, EU: 0x801AB7DC, JP: 0x801A70FC}
CATALOG.add(Patch(
    "combat.no_crits", G_COMBAT, "No critical hits",
    "Every unit's critical rate is 0 (what the game does for weapons that cannot crit).",
    versions={v: (Edit(a, _word(0x41820008), _word(ppc.NOP)),) for v, a in _NO_CRIT_SITE.items()}))

# SID_CRITRISE (Berserkers, Snipers, Swordmasters) adds the difficulty table's class bonus (15); the
# `extsb r3,r3` after the lookup becomes a multiply. The JP build has no such bonus.
_CLASS_CRIT_SITE = {US: 0x801A9348, EU: 0x801AB790}
_class_crit_hook = Patch(
    "combat.class_crit.hook", G_COMBAT, "Class critical bonus hook", "Makes the class critical bonus scalable.",
    versions={**{v: (Edit(a, _word(0x7C630774), _word(0x1C630001), wild=((2, 2),)),) for v, a in _CLASS_CRIT_SITE.items()},
              JP: ()}, internal=True)
CATALOG.add(_class_crit_hook)
CATALOG.add(Tunable(
    "combat.class_crit_multiplier", G_COMBAT, "Class critical bonus multiplier",
    "Berserkers, Snipers and Swordmasters add their class critical bonus times this (vanilla x1, 0 removes it, "
    "x2 doubles it). Not present in the Japanese build.",
    default=1, minimum=0, maximum=9, unit="x",
    versions={**{v: (Field(a, "imm16s", _hex("1c63")),) for v, a in _CLASS_CRIT_SITE.items()}, JP: ()},
    requires=(_class_crit_hook,)))


# -- map and camera ----------------------------------------------------------------------------------
G_MAP = "Map and camera"

# Fog of war is decided per map from a difficulty byte: the four `beq`/`bne +8` (three map kinds in
# the loader, one in the accessor) keep the fog only when the byte matches (Hard in US/PAL, the
# non-zero value in JP). The fourth loader case and the accessor's `li` then give a fixed value.
# version: (branches A, B, C, case-0 `li r5,0`, accessor branch, accessor `li r3,0`, branch word)
_FOG = {
    US: ((0x80040FDC, 0x80041000, 0x80041024), 0x80041038, 0x80048A80, 0x80048A84, 0x41820008),
    EU: ((0x800411A4, 0x800411C8, 0x800411EC), 0x80041200, 0x80048C58, 0x80048C5C, 0x41820008),
    JP: ((0x800402B4, 0x800402D8, 0x800402FC), 0x80040310, 0x80047D3C, 0x80047D40, 0x40820008),
}
_FOG_BRANCH = 0x48000008


def _fog_edits(on: bool) -> dict[str, tuple[Edit, ...]]:
    result = {}
    for v, (branches, case0, accessor, accessor_li, word) in _FOG.items():
        edits = [Edit(a, _word(word), _word(_FOG_BRANCH if on else ppc.NOP)) for a in branches]
        edits.append(Edit(accessor, _word(word), _word(ppc.NOP)))
        if on:
            edits.append(Edit(case0, _word(ppc.li(5, 0)), _word(ppc.li(5, 1))))
            edits.append(Edit(accessor_li, _word(ppc.li(3, 0)), _word(ppc.li(3, 1))))
        result[v] = tuple(edits)
    return result


CATALOG.add(Patch(
    "map.fog_on", G_MAP, "Fog of war on every map",
    "Forces the fog of war on all maps and difficulties (Ralf's PAL codes, found in all three builds).",
    versions=_fog_edits(True)))
CATALOG.add(Patch(
    "map.fog_off", G_MAP, "Fog of war off everywhere",
    "Removes the fog of war, including the maps and difficulty that have it.",
    versions=_fog_edits(False)))

# The bandits' village-burning behaviour is gated on skill 5 (SID_DESTROYVILLAGE): `beq` -> `b`.
_VILLAGE = {US: 0x800F9C6C, EU: 0x800FA450, JP: 0x800F7628}
CATALOG.add(Patch(
    "map.no_village_destruction", G_MAP, "Bandits do not destroy villages",
    "Enemies with the village-destroying skill no longer burn villages.",
    versions={v: (Edit(a, _word(0x418200B8), _word(0x480000B8)),) for v, a in _VILLAGE.items()}))

# The reinforcement skill counts its uses in the party record (+0x50): after two uses the lookup
# answers 3 ("none left"). Storing 1 every time never reaches that (Ralf / ltra043).
_REINFORCE = {  # version: (store, count load, index copy, lookup's index copy, limit compare)
    US: (0x800279B8, 0x800279B4, 0x800279BC, 0x800AA298, 0x80077254),
    EU: (0x80027B58, 0x80027B54, 0x80027B5C, 0x800AA5B0, 0x80077E6C),
    JP: (0x80026D80, 0x80026D7C, 0x80026D84, 0x800A85E8, 0x80075FBC),
}
CATALOG.add(Patch(
    "map.reinforce_unlimited", G_MAP, "Unlimited reinforcement uses",
    "The reinforcement skill can be used any number of times per map.",
    versions={v: (Edit(sites[0], _word(0x381B0001), _word(ppc.li(0, 1))),) for v, sites in _REINFORCE.items()}))
_reinforce_hook = Patch(
    "map.reinforce_limit.hook", G_MAP, "Reinforcement limit hook", "Lets the use count exceed two.",
    versions={v: (Edit(s[1], _word(0x8B640050), _word(0x88640050)),
                  Edit(s[0], _word(0x381B0001), _word(0x38030001)),
                  Edit(s[2], _word(0x7F63DB78), _word(ppc.li(27, 0))),
                  Edit(s[3], _word(0x7C7B1B78), _word(ppc.li(27, 0)))) for v, s in _REINFORCE.items()},
    internal=True)
CATALOG.add(_reinforce_hook)
CATALOG.add(Tunable(
    "map.reinforce_limit", G_MAP, "Reinforcement uses per map",
    "How many times the reinforcement skill works on a map (vanilla 2). Every use calls the first "
    "reinforcement set, so the second call of vanilla is repeated.",
    default=2, minimum=0, maximum=200, unit="uses",
    versions={v: (Field(s[4], "imm16u", _hex("2800")),) for v, s in _REINFORCE.items()},
    requires=(_reinforce_hook,)))

# The map camera turns in 45-degree steps between two clamps with the C-stick; removing the clamps
# (and optionally the edge detection, with a 1-degree step) frees it.
# version: (input word `lwz r3,8(r4)`, step loads (x2), clamp branches (x2), wrap branch)
_CAMERA = {
    US: (0x80019A68, (0x80019AB0, 0x80019AF0), (0x80019AB8, 0x80019AEC), 0x80019B1C),
    EU: (0x80019B70, (0x80019BB8, 0x80019BF8), (0x80019BC0, 0x80019BF4), 0x80019C24),
    JP: (0x8001922C, (0x80019274, 0x800192B4), (0x8001927C, 0x800192B0), 0x800192E0),
}
# `lfs f0,d(r2)` loading the 45.0 step, and the same load pointing at the 1.0 constant
_CAMERA_STEP = {US: (0xC0028198, 0xC0028228), EU: (0xC00281A8, 0xC0028238), JP: (0xC0028198, 0xC0028228)}


def _camera_edits(smooth: bool) -> dict[str, tuple[Edit, ...]]:
    result = {}
    for v, (held, loads, clamps, wrap) in _CAMERA.items():
        if smooth:
            step, one = _CAMERA_STEP[v]
            result[v] = tuple(Edit(a, _word(step), _word(one)) for a in loads) + (
                Edit(held, _word(0x80640008), _word(ppc.li(3, 0))),)
        else:
            result[v] = (Edit(clamps[0], _word(0x40800020), _word(ppc.NOP)),
                         Edit(clamps[1], _word(0x40810024), _word(ppc.NOP)),
                         Edit(wrap, _word(0x40810008), _word(0x48000040)))
    return result


CATALOG.add(Patch(
    "camera.free", G_MAP, "Free camera rotation",
    "The map camera turns with the C-stick left/right beyond its vanilla limits, 45 degrees per push.",
    versions=_camera_edits(False)))
CATALOG.add(Patch(
    "camera.smooth", G_MAP, "Smooth camera rotation",
    "The C-stick turns the camera 1 degree per frame while held instead of 45 degrees per push. "
    "Combine with free rotation to turn all the way round.",
    versions=_camera_edits(True)))


# -- more developer tools ----------------------------------------------------------------------------
# main() draws each debug overlay when its flag byte (set from the debug menu) is non-zero; making
# the load return 1 keeps the overlay on from boot (the menu's toggle then has no effect). The flag
# bytes are `lbz r0,d(r13)` with d ending in the flag number; the PAL build keeps them 0x28 further.
_DEBUG_DISPLAYS = (
    ("performance", "Performance meter", "Frame-time bars along the top of the screen.",
     {US: 0x80014D38, EU: 0x80014E54, JP: 0x80014504}, 0x61),
    ("gp_performance", "GP performance meter", "Graphics processor load bar.",
     {US: 0x80014D50, EU: 0x80014E6C, JP: 0x8001451C}, 0x62),
    ("safe_frame", "Safe-frame guide", "An outline of the TV's safe area.",
     {US: 0x80014D68, EU: 0x80014E84, JP: 0x80014534}, 0x64),
    ("process_tree", "Process tree", "The running process tree as text.",
     {US: 0x80014D90, EU: 0x80014EAC, JP: 0x8001455C}, 0x60),
)
for _key, _name, _what, _sites, _flag in _DEBUG_DISPLAYS:
    CATALOG.add(Patch(
        f"dev.show_{_key}", G_DEV, f"{_name} always on",
        f"{_what} Normally a switch in the debug menu; this keeps it on from startup.",
        versions={v: (Edit(a, _word(0x880D8900 + _flag + (0x28 if v == EU else 0)), _word(ppc.li(0, 1))),)
                  for v, a in _sites.items()}))


# -- battle screen -----------------------------------------------------------------------------------
G_BATTLE = "Battle screen"

# The battle scene's HUD (zdbx/battle.dbx) draws each HP bar through the Gauge widget's draw method
# (kaneko_gauge_draw, a vtable slot). The hook runs it, then prints the fighter's damage, hit and
# critical rate with draw_formatted_text_ui. GaugeL is always the attacker (the scene's left/right
# swap, +0x274, is set to 0 in setup_battle_scene); the gauge's x (+0x48) tells the sides apart, and
# the EXP gauge (mode +0x6C == 2) is skipped. The numbers are the forecast values the strikes roll
# against (CombatActor +0x298 Atk, +0x29A Def, +0x2A2 hit, +0x2A8 crit); the context's flag bit 0
# (+0xCAC) marks an exchange without them (staves), which draws nothing.
# version: (gauge vtable draw slot, kaneko_gauge_draw, set_prim2d_texture_mode_0x13, draw_formatted_text_ui)
_BATTLE_STATS = {
    US: (0x8029678C, 0x80197A78, 0x8008CD34, 0x8001003C),
    EU: (0x802A08B4, 0x80199DCC, 0x8008E308, 0x80010164),
    JP: (0x802912B4, 0x8019582C, 0x8008B384, 0x8000F844),
}
BATTLE_CONTEXT = {US: 0x80330EAC, EU: 0x8033AEAC, JP: 0x8032EEFC}
BATTLE_STATS_HOOK = CAVE_ADDRESS + 0x300
# Data: x nudge, y nudge, text size, 0.0 (f32), position preset (u32), pad, then one (x left, x right,
# y) f32 triple per preset, then the formats. A bare "#C" is a 4-byte token to the text code (it
# would swallow the terminator), so every colour code carries its two digits.
BATTLE_STATS_DATA = CAVE_ADDRESS + 0x480
_STATS_FORMAT = b"#C06Dmg #C01%d  #C06Hit #C01%d  #C06Crit #C01%d\x00"
_STATS_UNARMED = b"#C06Dmg #C01--  #C06Hit #C01--  #C06Crit #C01--\x00"
STATS_PRESETS = (                     # (x left, x right, y) on the 640x480 HUD
    ("under the HP windows", 60.0, 335.0, 96.0),
    ("above the HP windows", 60.0, 335.0, 0.0),
    ("bottom of the screen", 30.0, 380.0, 414.0),
)
_PRESET_TABLE = BATTLE_STATS_DATA + 0x18
_FORMAT_AT = _PRESET_TABLE + 12 * len(STATS_PRESETS)
_UNARMED_AT = _FORMAT_AT + (len(_STATS_FORMAT) + 3) // 4 * 4
_STATS_SIZE = 0.75


def _cave_offset(address: int) -> int:
    """Displacement of a cave address from 0x80000000 (``lis r12,0x8000`` based)."""
    assert in_cave(address) and address & 0xFFFF < 0x8000
    return address & 0xFFFF


def _battle_stats_data() -> bytes:
    data = struct.pack(">ffffI", 0.0, 0.0, _STATS_SIZE, 0.0, 0) + bytes(4)
    data += b"".join(struct.pack(">fff", *xy) for _, *xy in STATS_PRESETS)
    data += _STATS_FORMAT.ljust(_UNARMED_AT - _FORMAT_AT, b"\x00") + _STATS_UNARMED
    return data.ljust((len(data) + 3) // 4 * 4, b"\x00")


def _battle_stats_code(version: str) -> bytes:
    _slot, draw, texture_mode, text = _BATTLE_STATS[version]
    context = BATTLE_CONTEXT[version]
    data = _cave_offset(BATTLE_STATS_DATA)
    program = [
        ppc.stwu(1, -0x30, 1), ppc.MFLR_R0, ppc.stw(0, 0x34, 1),
        ppc.stw(31, 0x2C, 1), ppc.stw(30, 0x28, 1), ppc.stw(29, 0x24, 1), ppc.mr(31, 3),
        ("bl", draw),
        ppc.lwz(0, 0x6C, 31), ppc.cmpwi(0, 2), ("eq", "done"),                  # the EXP gauge
        ppc.lis(30, (context + 0x8000) >> 16), ppc.addi(30, 30, context & 0xFFFF),
        ppc.lwz(0, 0xCAC, 30), ppc.andi_(0, 0, 1), ("ne", "done"),            # no combat stats
        ("bl", texture_mode),
        ppc.addi(29, 30, 0x2E0),                                                # r30 self, r29 opponent
        ppc.lis(12, 0x8000),
        ppc.lwz(0, data + 0x10, 12), ppc.cmpwi(0, len(STATS_PRESETS) - 1), ("le", "preset"),
        ppc.li(0, 0),
        "preset",
        ppc.mulli(0, 0, 12), ppc.addi(11, 12, _cave_offset(_PRESET_TABLE)), ppc.add(11, 11, 0),
        ppc.lfs(1, 0, 11),
        ppc.lwz(0, 0x48, 31), ppc.cmpwi(0, 200), ("lt", "left"),
        ppc.mr(0, 30), ppc.mr(30, 29), ppc.mr(29, 0), ppc.lfs(1, 4, 11),
        "left",
        ppc.lfs(2, 8, 11),
        ppc.lfs(0, data, 12), ppc.fadds(1, 1, 0), ppc.lfs(0, data + 4, 12), ppc.fadds(2, 2, 0),
        ppc.lha(9, 0x298, 30), ppc.lha(0, 0x29A, 29), ppc.subf(9, 0, 9),       # damage = Atk - Def
        ppc.srawi(0, 9, 31), ppc.andc(9, 9, 0),
        ppc.lha(10, 0x2A2, 30), ppc.lha(11, 0x2A8, 30),
        ppc.addi(8, 12, _cave_offset(_FORMAT_AT)),
        ppc.lbz(0, 0x2C8, 30), ppc.extsb(0, 0), ppc.cmpwi(0, 0), ("gt", "armed"),
        ppc.addi(8, 12, _cave_offset(_UNARMED_AT)),
        "armed",
        ppc.lfs(3, data + 8, 12), ppc.lfs(4, data + 12, 12),
    ]
    if version == JP:
        # (x, y, size, 0.0 as floats; colour, shadow, 0; format; values from r7)
        program += [ppc.li(3, 1), ppc.li(4, 1), ppc.li(5, 0), ppc.mr(6, 8), ppc.mr(7, 9), ppc.mr(8, 10),
                    ppc.mr(9, 11)]
    else:
        # (size, 0.0; x, y, colour, shadow, 0 as ints; format; values in r9, r10, then the stack)
        program += [ppc.fctiwz(0, 1), ppc.stfd(0, 0x18, 1), ppc.lwz(3, 0x1C, 1),
                    ppc.fctiwz(0, 2), ppc.stfd(0, 0x18, 1), ppc.lwz(4, 0x1C, 1),
                    ppc.stw(11, 8, 1), ppc.fmr(1, 3), ppc.fmr(2, 4), ppc.li(5, 1), ppc.li(6, 1), ppc.li(7, 0)]
    program += [
        ppc.CRCLR_6, ("bl", text),
        "done",
        ppc.lwz(29, 0x24, 1), ppc.lwz(30, 0x28, 1), ppc.lwz(31, 0x2C, 1), ppc.lwz(0, 0x34, 1), ppc.MTLR_R0,
        ppc.addi(1, 1, 0x30), ppc.BLR,
    ]
    return _words(*ppc.assemble(BATTLE_STATS_HOOK, program))


def _battle_stats_edits(version: str) -> tuple[Edit, ...]:
    slot, draw = _BATTLE_STATS[version][:2]
    code, data = _battle_stats_code(version), _battle_stats_data()
    assert BATTLE_STATS_HOOK + len(code) <= BATTLE_STATS_DATA
    return (Edit(slot, _word(draw), _word(BATTLE_STATS_HOOK)),
            Edit(BATTLE_STATS_HOOK, bytes(len(code)), code),
            Edit(BATTLE_STATS_DATA, bytes(len(data)), data, wild=((0, 0x14),)))   # the tunables' values


_battle_stats = Patch(
    "battle.show_stats", G_BATTLE, "Damage, hit and critical in battle scenes",
    "Prints each fighter's damage, hit and critical rate on the battle screen while the battle plays "
    "(the same numbers as the map forecast; the hit is the displayed value, not the two-roll true hit). "
    "Staff and other non-combat exchanges show nothing; a fighter that cannot counter shows dashes.",
    versions={v: _battle_stats_edits(v) for v in _BATTLE_STATS})
CATALOG.add(_battle_stats)
_PRESET_NAMES = ", ".join(f"{i} {name}" for i, (name, *_xy) in enumerate(STATS_PRESETS))
for _key, _name, _what, _default, _minimum, _maximum, _unit, _at, _kind in (
        ("position", "Battle stats position", f"Where the lines go: {_PRESET_NAMES}", 0, 0,
         len(STATS_PRESETS) - 1, "", 0x10, "u32"),
        ("x_offset", "Battle stats x nudge", "Pixels added to the preset's horizontal position (both lines)",
         0.0, -300.0, 300.0, "px", 0, "f32"),
        ("y_offset", "Battle stats y nudge", "Pixels added to the preset's vertical position (down is positive)",
         0.0, -300.0, 300.0, "px", 4, "f32"),
        ("size", "Battle stats text size", "Text scale, 1 being the size of the HUD's names",
         _STATS_SIZE, 0.25, 2.0, "x", 8, "f32")):
    CATALOG.add(Tunable(
        f"battle.stats_{_key}", G_BATTLE, _name, f"{_what} (the HUD is 640x480; default {_default:g}).",
        default=_default, minimum=_minimum, maximum=_maximum, unit=_unit,
        versions={v: (Field(BATTLE_STATS_DATA + _at, _kind),) for v in _BATTLE_STATS},
        requires=(_battle_stats,)))


from . import chapter_flow  # noqa: E402,F401  (registers the story-flow hook)
