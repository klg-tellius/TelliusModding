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
    requires=(PHASE_HOOK,), choices=CHOICES)) for i, (army, default) in enumerate(zip(ARMIES, DEFAULTS)))
