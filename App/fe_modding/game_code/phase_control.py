"""Who plays each army's phase.

``party_data + 0x14..0x17`` hold one byte per army (player, enemy, other, partner): 0 the army has
no phase, 1 the player gives its orders, 2 the AI plays it. ``initialize_chapter_start_state``
writes 1, 2, 2, 2 with four ``stb`` (``r3`` = 1 for the player, ``r0`` = 2 for the rest) and nothing
else in retail changes them except the developer menu. On a phase whose byte is 1 the game runs the
player's map controls (``start_blocking_process_if_faction_active``); on 2 it runs the AI
(``dispatch_to_blocking_process_by_faction``); on 0 the army is skipped.

Retail's dispatcher special-cases faction 0 and always starts player controls, without consulting
whether its controller is 1 or 2.  The hook also redirects that case through a small cave routine:
controller 2 enters the same AI process used by the other factions, while controller 1 retains the
normal player-control path.  The downstream AI order builder already indexes the current faction's
unit list and therefore handles the player army without further changes.

:data:`PHASE_HOOK` replaces the first ``stb`` with a call to a cave routine that stores the four
bytes from its own ``li`` immediates, and turns the other three into ``nop``. Each army's choice is
the low byte of one ``li`` (a :class:`Tunable` with a field in the cave), so it applies from the
next chapter start. Saves made before the change keep the values they were saved with.

A phase given to the player runs the player's map process (``E_BMapPlph``, started for any army
whose byte is 1), whose code was written for the blue army. :data:`PLAYER_CONTROLS` makes it follow
the army whose phase it is (party ``+0x11``):

- the unit category behind the A button (US ``0x800284B4``) lets a blue unit act in any phase
  (its other cases already compare the unit's army with the current one); outside the player
  phase a blue unit is now only looked at, like an army that is not the player's;
- the "next unit not yet done" search (US ``0x800AA5F0``), used by the automatic end of the
  phase after an action and by the next-unit button, walks the blue list (``0x802CA264``, one
  list every ``0xC`` bytes) and rejects units of other armies: the phase ended as soon as no
  blue unit was left to act. It now walks the current army's list;
- the cursor hint (party ``+0x51D``, US ``0x800296B4``) shows a blue unit outside the player
  phase as done;
- after the player ends the partner phase, the dispatcher starts the computer phase process for
  that army (retail runs it in a mode chosen by party ``+0x98``), which played every partner unit
  not yet moved. With the partner army's controller at 1 it now starts nothing, as for the enemy
  and other armies.
"""

from __future__ import annotations

from . import ppc
from .catalog import CATALOG, CAVE_ADDRESS, Edit, Field, Patch, Tunable, in_cave

US, EU, JP = "GFEE01", "GFEP01", "GFEJ01"
G_PHASES = "Army phases"

PHASE_ROUTINE = CAVE_ADDRESS + 0x660
PLAYER_AI_ROUTINE = CAVE_ADDRESS + 0x690
ARMIES = ("player", "enemy", "other", "partner")
DEFAULTS = (1, 2, 2, 2)
CHOICES = ("No phase", "Player", "Computer")
_ROUTINE_WORDS = 2 * len(ARMIES) + 1
assert in_cave(PHASE_ROUTINE, 4 * _ROUTINE_WORDS) and PHASE_ROUTINE + 4 * _ROUTINE_WORDS <= CAVE_ADDRESS + 0x700

# initialize_chapter_start_state's `stb r3,0x14(r31)` (the three `stb r0` follow it)
_SITES = {US: 0x8014D960, EU: 0x8014ECE8, JP: 0x8014AD88}
_DISPATCH_SITES = {US: 0x8002E6C0, EU: 0x8002E860, JP: 0x8002DA94}
_RETAIL = (0x987F0014, 0x981F0015, 0x981F0016, 0x981F0017)


def _word(value: int) -> bytes:
    return value.to_bytes(4, "big")


def _words(values) -> bytes:
    return b"".join(_word(v) for v in values)


def value_address(army: int) -> int:
    """The byte holding ``army``'s controller: the low byte of its ``li r12,value``."""
    return PHASE_ROUTINE + 8 * army + 3


def _routine() -> list[int]:
    words = []
    for army, default in enumerate(DEFAULTS):
        words += [ppc.addi(12, 0, default), 0x99800000 | (31 << 16) | (0x14 + army)]   # li r12 ; stb r12,0x14+army(r31)
    return words + [ppc.BLR]


def _edits(site: int, dispatch: int) -> tuple[Edit, ...]:
    routine = _routine()
    player_ai = ppc.assemble(PLAYER_AI_ROUTINE, [
        ppc.lbz(0, 0, 30),
        ppc.cmplwi(0, 2),
        ("ne", "player_controls"),
        ("b", dispatch + 0x54),
        "player_controls",
        ("b", dispatch + 0x10),
    ])
    return (
        Edit(site, _words(_RETAIL), _words([ppc.bl(site, PHASE_ROUTINE), ppc.NOP, ppc.NOP, ppc.NOP])),
        Edit(PHASE_ROUTINE, bytes(4 * len(routine)), _words(routine),
             wild=tuple((8 * army + 3, 1) for army in range(len(ARMIES)))),
        # At dispatch+4 retail branches faction 0 directly to player controls.  Retarget it to the
        # otherwise unreachable instruction at +0x0C, which has room for an unconditional cave hook.
        Edit(dispatch + 4, _word(ppc.bc("eq", dispatch + 4, dispatch + 0x10)),
             _word(ppc.bc("eq", dispatch + 4, dispatch + 0x0C))),
        Edit(dispatch + 0x0C, _word(ppc.b(dispatch + 0x0C, dispatch + 0x5C)),
             _word(ppc.b(dispatch + 0x0C, PLAYER_AI_ROUTINE))),
        Edit(PLAYER_AI_ROUTINE, bytes(4 * len(player_ai)), _words(player_ai)),
    )


# -- the player's map process in another army's phase ----------------------------------------
CONTROLS_CAVE = CAVE_ADDRESS + 0x810
_PARTY = {US: 0x80330708, EU: 0x8033A708, JP: 0x8032E788}
_NEXT_UNDONE = {US: 0x800AA5F0, EU: 0x800AA908, JP: 0x800A8930}
_UNIT_CATEGORY = {US: 0x800284B4, EU: 0x80028654, JP: 0x8002787C}
_CURSOR_HINT = {US: 0x800296B4, EU: 0x80029854, JP: 0x80028A7C}   # `lis r3` of the blue-unit case


def _ha(value: int) -> int:
    return ((value + 0x8000) >> 16) & 0xFFFF


def _lo(value: int) -> int:
    return ppc.sext16(value & 0xFFFF)


def _current_army(rd: int, party: int) -> list[int]:
    """``rd`` = party ``+0x11``, the army whose phase it is."""
    return [ppc.lis(rd, ppc.sext16(_ha(party + 0x11))), ppc.lbz(rd, _lo(party + 0x11), rd)]


def _controls_edits(version: str) -> tuple[Edit, ...]:
    party, dispatch = _PARTY[version], _DISPATCH_SITES[version]
    search, category, hint = _NEXT_UNDONE[version], _UNIT_CATEGORY[version], _CURSOR_HINT[version]
    list_cave = CONTROLS_CAVE
    army_cave = list_cave + 0x18
    category_cave = army_cave + 0x10
    hint_cave = category_cave + 0x24
    dispatch_cave = hint_cave + 0x28
    end = dispatch_cave + 0x18
    assert in_cave(CONTROLS_CAVE, end - CONTROLS_CAVE) and end <= CAVE_ADDRESS + 0x900
    # search+8 `lwz r4,0(r4)`: the head of the current army's list (r4 = the list table)
    list_code = _current_army(12, party) + [
        ppc.mulli(12, 12, 0xC), ppc.add(4, 4, 12), ppc.lwz(4, 0, 4), ppc.b(list_cave + 0x14, search + 0xC)]
    # search+0x2C `cmplwi r0,0`: the given unit's army (r0) against the current one
    army_code = _current_army(12, party) + [ppc.cmplw(0, 12), ppc.b(army_cave + 0xC, search + 0x30)]
    # category+0xD8 `lwz r0,0x1A0(r29)` (r30 = the unit's army, r31 = party): a blue unit outside
    # the player phase gets category 3, the one of an army that is not the player's
    category_code = ppc.assemble(category_cave, [
        ppc.cmplwi(30, 0), ("ne", "acts"), ppc.lbz(0, 0x11, 31), ppc.cmplwi(0, 0), ("eq", "acts"),
        ppc.li(3, 3), ("b", category + 0xF0),
        "acts", ppc.lwz(0, 0x1A0, 29), ("b", category + 0xDC)])
    # the cursor hint of a blue unit: 3 (can act) in the player phase, 4 (done) in another one
    hint_code = ppc.assemble(hint_cave, _current_army(12, party) + [
        ppc.li(0, 3), ppc.cmpwi(12, 0), ("eq", "store"), ppc.li(0, 4),
        "store", ppc.lis(3, ppc.sext16(_ha(party))), ppc.addi(3, 3, _lo(party)), ppc.stb(0, 0x51D, 3),
        ("b", hint + 0x68)])
    # dispatch+0x1C `cmplwi r3,0` (partner army, r30 = the controller bytes): a partner phase the
    # player played starts no computer phase afterwards
    dispatch_code = ppc.assemble(dispatch_cave, [
        ppc.lbz(12, 3, 30), ppc.cmplwi(12, 1), ("ne", "computer"), ("b", dispatch + 0x5C),
        "computer", ppc.cmplwi(3, 0), ("b", dispatch + 0x20)])
    blocks = ((list_cave, list_code), (army_cave, army_code), (category_cave, category_code),
              (hint_cave, hint_code), (dispatch_cave, dispatch_code))
    sites = ((search + 0x8, ppc.lwz(4, 0, 4), list_cave), (search + 0x2C, ppc.cmplwi(0, 0), army_cave),
             (category + 0xD8, ppc.lwz(0, 0x1A0, 29), category_cave),
             (hint, ppc.lis(3, ppc.sext16(_ha(party))), hint_cave),
             (dispatch + 0x1C, ppc.cmplwi(3, 0), dispatch_cave))
    return tuple(Edit(site, _word(retail), _word(ppc.b(site, cave))) for site, retail, cave in sites) + tuple(
        Edit(address, bytes(4 * len(code)), _words(code)) for address, code in blocks)


PLAYER_CONTROLS = CATALOG.add(Patch(
    "phases.controller.player_controls", G_PHASES, "Player controls follow the army of the phase",
    "In a phase given to the player, the current army acts: blue units are only looked at outside "
    "the player phase, the phase ends when the current army is done, and the partner units left "
    "are not played by the computer afterwards.",
    versions={v: _controls_edits(v) for v in _SITES}, internal=True))

PHASE_HOOK = CATALOG.add(Patch(
    "phases.controller.hook", G_PHASES, "Army phase controller hook",
    "Chapter start reads each army's phase controller from the cave, including computer control of the player army.",
    versions={v: _edits(site, _DISPATCH_SITES[v]) for v, site in _SITES.items()}, internal=True))

PHASE_TUNABLES = tuple(CATALOG.add(Tunable(
    f"phases.{army}", G_PHASES, f"{army.capitalize()} phase",
    f"Who plays the {army} army's phase, from the next chapter start: the player, the computer, or "
    "nobody (the phase is skipped). A save keeps the setting it was made with.",
    default=default, minimum=0, maximum=2,
    versions={v: (Field(value_address(i), "u8"),) for v in _SITES},
    requires=(PHASE_HOOK, PLAYER_CONTROLS), choices=CHOICES)) for i, (army, default) in enumerate(zip(ARMIES, DEFAULTS)))
