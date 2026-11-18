"""Radiant Dawn: a support formed or raised in the base plays a full conversation, as in Path of Radiance.

Retail Radiant Dawn plays nothing when the base's Support screen forms a pair ("Create a support
relationship?" Yes, or "Strengthen"): the screen's process (``BaseSupportProc``, script at
0x8038F5C8) calls ``establish_or_rank_up_support_pair`` (0x80215D04) in a once step (0x200f) and then
waits in 0x802160C0 (a 0x201a step, called each frame until it moves the script on).

The patch points those two script words at cave routines:

* **Yes step.** Reads the two units (process +0x44 / +0x48), works out the rank they are about to
  reach (``get_unit_support_rank`` + 1) and builds ``MSUP_<A>_<B>_<C|B|A>`` from the two PIDs without
  ``PID_``, in alphabetical order. When the loaded messages hold that ID (``e_common.m``, always loaded
  in the base), it sets every panel of the Support screen to scale 0 (+0x2C, +0x30: the panel and all
  on it vanish) and starts the conversation on the process (``0x8014BED4``, as the ``TalkEvent``
  script function does), which holds the process until the conversation ends. Otherwise it forms the
  pair at once, as retail does.
* **Wait step.** While ``E_Talk`` runs it does nothing; then it puts the panels back and forms the
  pair (the rank-up and its "Support level raised" report), and from then on it is retail's step.

Checked in Dolphin on RFEE01 (2026-11-18): Micaiah and Edward, C from the I:4 base and B by
Strengthen, each played its conversation full screen and then raised the rank; a pair without a
conversation (Micaiah and Nolan) behaved as in retail.
The European and Japanese sites are matched from the US code (see :data:`SITES`) and not
checked in game.
"""

from __future__ import annotations

import struct

from . import ppc
from .catalog import CATALOG, CAVE_ADDRESS, Edit, Patch, in_cave

RFEE01 = "RFEE01"
G_RD_SUPPORTS = "Supports"

#: The message file the conversations go in (always loaded in the base); the disc's language prefix
#: (``e_`` on the US disc) is added in front of the name.
MESSAGE_FILE = "common.m"
PREFIX = "MSUP_"
RANK_LETTERS = {1: "C", 2: "B", 3: "A"}

ESTABLISH = 0x80215D04          # establish_or_rank_up_support_pair(process)
AFTER = 0x802160C0              # BaseSupportProc's step after it
UNIT_OF = 0x801E7A28            # unit handle -> unit
SLOT_OF = 0x8012E9B4            # find_support_slot_by_unit(unit, other)
RANK_OF = 0x8012E8BC            # get_unit_support_rank(unit, slot)
SNPRINTF = 0x80290D04
MESSAGE_TEXT = 0x800D0864       # a message's text, or the ID itself when there is no such message
TALK = 0x8014BED4               # start a conversation (message ID, parent process)
FIND_PROCESS = 0x80085708       # a live process by name
E_TALK = 0x80363B74             # "E_Talk"
SCRIPT_ESTABLISH = 0x8038F6A4   # BaseSupportProc: 0x200f -> ESTABLISH
SCRIPT_AFTER = 0x8038F6AC       # BaseSupportProc: 0x201a -> AFTER

#: The same sites on each disc. European and Japanese ones were found by matching each function's code
#: with relocatable operands masked (one match each), and the two script words through the pointer to
#: the "BaseSupportProc" name; each holds that disc's establish and after-step addresses.
SITES = {
    RFEE01: dict(ESTABLISH=ESTABLISH, AFTER=AFTER, UNIT_OF=UNIT_OF, SLOT_OF=SLOT_OF, RANK_OF=RANK_OF,
                 SNPRINTF=SNPRINTF, MESSAGE_TEXT=MESSAGE_TEXT, TALK=TALK, FIND_PROCESS=FIND_PROCESS,
                 E_TALK=E_TALK, SCRIPT_ESTABLISH=SCRIPT_ESTABLISH, SCRIPT_AFTER=SCRIPT_AFTER),
    "RFEP01": dict(ESTABLISH=0x801FCFD4, AFTER=0x801FD390, UNIT_OF=0x801CEA08, SLOT_OF=0x80114CA8,
                   RANK_OF=0x80114BB0, SNPRINTF=0x802938B8, MESSAGE_TEXT=0x800B5C20, TALK=0x801321F8,
                   FIND_PROCESS=0x80069ED0, E_TALK=0x803648D4, SCRIPT_ESTABLISH=0x80391304,
                   SCRIPT_AFTER=0x8039130C),
    "RFEJ01": dict(ESTABLISH=0x8020C774, AFTER=0x8020CB30, UNIT_OF=0x801DDF0C, SLOT_OF=0x8012702C,
                   RANK_OF=0x80126F34, SNPRINTF=0x802867DC, MESSAGE_TEXT=0x800CAAB4, TALK=0x801440EC,
                   FIND_PROCESS=0x80082030, E_TALK=0x8034EA34, SCRIPT_ESTABLISH=0x80379474,
                   SCRIPT_AFTER=0x8037947C),
}

CODE = CAVE_ADDRESS + 0x1300    # Radiant Dawn leaves 0x1300-0x17FF of the cave free
FLAG = CAVE_ADDRESS + 0x1600    # 1 while a formed pair waits for its conversation to end
LETTERS = CAVE_ADDRESS + 0x1604
FMT = CAVE_ADDRESS + 0x1608
BUF = CAVE_ADDRESS + 0x1620     # the message ID, 0x40 bytes
SAVE = CAVE_ADDRESS + 0x1660    # the panels' X and Y scale, 8 bytes each
MAX_PANELS = 32
END = SAVE + 8 * MAX_PANELS

_MFLR, _MTLR, _CRCLR6 = 0x7C0802A6, 0x7C0803A6, 0x4CC63182


def conversation_id(pid_a: str, pid_b: str, rank: str) -> str:
    """The message the patch plays when ``pid_a`` and ``pid_b`` reach ``rank`` (``"C"``, ``"B"`` or ``"A"``)."""
    a, b = sorted(p[4:] if p.startswith("PID_") else p for p in (pid_a, pid_b))
    return f"{PREFIX}{a}_{b}_{rank}"


def _hi(address: int) -> int:
    return (address + 0x8000) >> 16 & 0xFFFF


def _lo(address: int) -> int:
    return ppc.sext16(address & 0xFFFF)


def _program(site: dict) -> list:
    return [
        "yes",
        ppc.stwu(1, -0x40, 1), _MFLR, ppc.stw(0, 0x44, 1), ppc.stmw(26, 0x28, 1),
        ppc.mr(31, 3),
        ppc.lwz(3, 0x44, 31), ("bl", site["UNIT_OF"]), ppc.mr(30, 3),
        ppc.lwz(3, 0x48, 31), ("bl", site["UNIT_OF"]), ppc.mr(29, 3),
        ppc.mr(3, 30), ppc.mr(4, 29), ("bl", site["SLOT_OF"]), ppc.extsb(4, 3), ppc.mr(3, 30), ("bl", site["RANK_OF"]),
        ppc.andi_(28, 3, 0xFF), ppc.addi(28, 28, 1), ppc.cmpwi(28, 3), ("le", "rank_ok"), ppc.li(28, 3),
        "rank_ok",
        ppc.lwz(3, 0xEC, 30), ppc.lwz(27, 0, 3), ppc.addi(27, 27, 4),      # PersonData +0: the PID
        ppc.lwz(3, 0xEC, 29), ppc.lwz(26, 0, 3), ppc.addi(26, 26, 4),
        ppc.mr(3, 27), ppc.mr(4, 26), ("bl", "strcmp"), ppc.cmpwi(3, 0), ("le", "ordered"),
        ppc.mr(3, 27), ppc.mr(27, 26), ppc.mr(26, 3),
        "ordered",
        ppc.lis(3, _hi(BUF)), ppc.addi(3, 3, _lo(BUF)), ppc.li(4, 0x40),
        ppc.lis(5, _hi(FMT)), ppc.addi(5, 5, _lo(FMT)), ppc.mr(6, 27), ppc.mr(7, 26),
        ppc.lis(8, _hi(LETTERS)), ppc.addi(8, 8, _lo(LETTERS)), ppc.lbzx(8, 8, 28),
        _CRCLR6, ("bl", site["SNPRINTF"]),
        ppc.lis(3, _hi(BUF)), ppc.addi(3, 3, _lo(BUF)), ("bl", site["MESSAGE_TEXT"]),
        ppc.lis(4, _hi(BUF)), ppc.addi(4, 4, _lo(BUF)), ppc.cmplw(3, 4), ("eq", "no_talk"),
        ppc.mr(3, 31), ppc.li(4, 0), ("bl", "panels"),
        ppc.lis(3, _hi(BUF)), ppc.addi(3, 3, _lo(BUF)), ppc.mr(4, 31), ("bl", site["TALK"]),
        ppc.li(0, 1), ppc.lis(4, _hi(FLAG)), ppc.stw(0, _lo(FLAG), 4), ("b", "yes_end"),
        "no_talk",
        ppc.mr(3, 31), ("bl", site["ESTABLISH"]),
        "yes_end",
        ppc.lmw(26, 0x28, 1), ppc.lwz(0, 0x44, 1), _MTLR, ppc.addi(1, 1, 0x40), ppc.BLR,

        "wait",
        ppc.stwu(1, -0x20, 1), _MFLR, ppc.stw(0, 0x24, 1), ppc.stw(31, 0x1C, 1), ppc.mr(31, 3),
        ppc.lis(3, _hi(site["E_TALK"])), ppc.addi(3, 3, _lo(site["E_TALK"])), ("bl", site["FIND_PROCESS"]),
        ppc.cmpwi(3, 0), ("ne", "wait_end"),
        ppc.lis(4, _hi(FLAG)), ppc.lwz(0, _lo(FLAG), 4), ppc.cmpwi(0, 0), ("eq", "after"),
        ppc.li(0, 0), ppc.stw(0, _lo(FLAG), 4),
        ppc.mr(3, 31), ppc.li(4, 1), ("bl", "panels"),
        ppc.mr(3, 31), ("bl", site["ESTABLISH"]), ("b", "wait_end"),
        "after",
        ppc.mr(3, 31), ("bl", site["AFTER"]),
        "wait_end",
        ppc.lwz(31, 0x1C, 1), ppc.lwz(0, 0x24, 1), _MTLR, ppc.addi(1, 1, 0x20), ppc.BLR,

        # panels(process, restore): every top-level panel of the process, its X and Y scale saved and set
        # to 0, or put back
        "panels",
        ppc.addi(5, 3, 0x38), ppc.lwz(6, 0x3C, 3), ppc.lis(7, _hi(SAVE)), ppc.addi(7, 7, _lo(SAVE)), ppc.li(8, 0),
        "panel",
        ppc.cmplw(5, 6), ("eq", "panels_done"), ppc.cmpwi(8, MAX_PANELS), ("ge", "panels_done"),
        ppc.lwz(9, 0, 5), ppc.lwz(9, 8, 9), ppc.cmpwi(4, 0), ("ne", "restore"),
        ppc.lwz(10, 0x2C, 9), ppc.stw(10, 0, 7), ppc.lwz(10, 0x30, 9), ppc.stw(10, 4, 7),
        ppc.li(10, 0), ppc.stw(10, 0x2C, 9), ppc.stw(10, 0x30, 9), ("b", "next_panel"),
        "restore", ppc.lwz(10, 0, 7), ppc.stw(10, 0x2C, 9), ppc.lwz(10, 4, 7), ppc.stw(10, 0x30, 9),
        "next_panel", ppc.addi(7, 7, 8), ppc.addi(8, 8, 1), ppc.lwz(5, 0, 5), ("b", "panel"),
        "panels_done", ppc.BLR,

        "strcmp",
        ppc.lbz(5, 0, 3), ppc.lbz(6, 0, 4), ppc.cmplw(5, 6), ("ne", "differ"),
        ppc.cmpwi(5, 0), ("eq", "same"), ppc.addi(3, 3, 1), ppc.addi(4, 4, 1), ("b", "strcmp"),
        "differ", ppc.subf(3, 6, 5), ppc.BLR,
        "same", ppc.li(3, 0), ppc.BLR,
    ]


def _labels(program: list) -> dict[str, int]:
    labels, address = {}, CODE
    for item in program:
        if isinstance(item, str):
            labels[item] = address
        else:
            address += 4
    return labels


def _word(value: int) -> bytes:
    return struct.pack(">I", value)


_PROGRAM = _program(SITES[RFEE01])
CODE_BYTES = b"".join(_word(w) for w in ppc.assemble(CODE, _PROGRAM))
LABELS = _labels(_PROGRAM)
DATA = b"NCBA" + b"MSUP_%s_%s_%c".ljust(BUF - FMT, b"\0")   # rank letters, then the ID's format
assert CODE + len(CODE_BYTES) <= FLAG and in_cave(CODE, END - CODE)


def _edits(site: dict) -> tuple[Edit, ...]:
    program = _program(site)
    code = b"".join(_word(w) for w in ppc.assemble(CODE, program))
    labels = _labels(program)
    return (Edit(site["SCRIPT_ESTABLISH"], _word(site["ESTABLISH"]), _word(labels["yes"])),
            Edit(site["SCRIPT_AFTER"], _word(site["AFTER"]), _word(labels["wait"])),
            Edit(CODE, bytes(len(code)), code),
            Edit(LETTERS, bytes(BUF - LETTERS), DATA))


PATCH = CATALOG.add(Patch(
    "rd.support.base_talk", G_RD_SUPPORTS, "Support conversations in the base",
    "Forming or strengthening a support on the base's Support screen plays the pair's conversation "
    f"first, full screen, as in Path of Radiance: the message {PREFIX}<A>_<B>_<C, B or A> in "
    f"{MESSAGE_FILE} (the two characters' IDs without PID_, in alphabetical order). Write them on a "
    "character's Supports tab. Pairs without one form at once, as in the retail game.",
    {code: _edits(site) for code, site in SITES.items()}))
