"""RFEE01 test-launch patch: boot an extracted Wii tree directly into a chapter.

The retail ``GameController`` process initializes the databases at label 2, opens the title at
label 5, and enters a loaded/new game at label 11.  For a test launch we replace the two label-2
calls with a cave stub followed by ``goto 11``.  The stub preserves both retail initializers,
selects the story mode, stores the requested RD difficulty, calls the retail chapter setter
and party reinitializer, and selects the same resume point used by chapter advance.

This patch is only applied to the disposable ``build/dolphin_run/sys/main.dol`` copy.
"""

from __future__ import annotations

from . import ppc
from .catalog import CATALOG, CAVE_ADDRESS, Edit, Patch, Session, in_cave

RFEE01 = "RFEE01"

JUMP_STUB = CAVE_ADDRESS + 0x800
JUMP_END = JUMP_STUB + 0xA0
assert in_cave(JUMP_STUB, JUMP_END - JUMP_STUB)

# RD's native IDs.  The North-American menu names these Easy, Normal and Hard; its scripts call
# the same values Normal, Hard and Maniac.  The separate internal Easy value remains useful for
# testing scripts which explicitly call Easy().
DIFFICULTIES = {"Normal": 0, "Hard": 1, "Maniac": 2, "Easy": 3}

_SCRIPT_SITE = 0x803833A4
_SCRIPT_ORIGINAL = bytes.fromhex(
    "0000200f800cdcec"  # call init_database_files
    "0000200f800cdf00"  # call the second database initializer
)
_CALL = 0x0000200F
_GOTO_11 = 0x000B100C
_SLEEP = 0x0000100A

_PARTY = 0x803CAB38
_RESUME_POINT = 0x803CABD4
_GET_STATE = 0x80060728
_SET_CHAPTER = 0x80061584
#: The low two bits of the state word (``_GET_STATE``) are the game mode. 1 is a trial map: at a
#: chapter's end FUN_800437D0 then opens the trial result (GameController label 0x24), which loads
#: ``window/achieve.cms`` (not on the retail disc) and never returns. 0 is the story.
_STORY_MODE = 0
_REINIT_PARTY = 0x8006132C
_REFRESH_PARTY_STATE = 0x801097FC
_INIT_DATABASES = 0x800CDCEC
_INIT_DATABASES_2 = 0x800CDF00


def _word(value: int) -> bytes:
    return value.to_bytes(4, "big")


def _words(*values: int) -> bytes:
    return b"".join(_word(value) for value in values)


def _address(reg: int, address: int) -> tuple[int, int]:
    return ppc.lis(reg, (address + 0x8000) >> 16), ppc.addi(reg, reg, ppc.sext16(address & 0xFFFF))


def _stub() -> bytes:
    words = ppc.assemble(JUMP_STUB, [
        ppc.stwu(1, -0x20, 1), ppc.MFLR_R0, ppc.stw(0, 0x24, 1), ppc.stw(31, 0x1C, 1),
        ppc.mr(31, 3),
        ("bl", _INIT_DATABASES), ("bl", _INIT_DATABASES_2),
        *_address(3, _PARTY), ("bl", _GET_STATE),
        ppc.lwz(5, 0, 3), ppc.andi_(5, 5, 0xFFFC), ppc.li(6, _STORY_MODE), ppc.add(5, 5, 6),
        ppc.stw(5, 0, 3),
        ppc.li(0, DIFFICULTIES["Normal"]), ppc.stb(0, 0x11, 3),
        *_address(3, _PARTY), ppc.li(4, 0), ("bl", _SET_CHAPTER),
        *_address(3, _PARTY), ("bl", _REINIT_PARTY),
        # FUN_800cd5f4 ends every file-menu outcome this way: the getter leaves the current
        # state pointer in r3 for the final refresh routine.
        *_address(3, _PARTY), ("bl", _GET_STATE), ("bl", _REFRESH_PARTY_STATE),
        *_address(4, _RESUME_POINT), ppc.li(0, 4), ppc.stb(0, 0, 4),
        ppc.li(0, 11), ppc.stw(0, 0x60, 31), ppc.mr(3, 31),
        ppc.lwz(31, 0x1C, 1), ppc.lwz(0, 0x24, 1), ppc.MTLR_R0,
        ppc.addi(1, 1, 0x20), ppc.BLR,
    ])
    return _words(*words).ljust(JUMP_END - JUMP_STUB, b"\x00")


_CODE = _stub()
# Halfwords inside ``li r0,difficulty`` and ``li r4,chapter`` are populated by install().
_DIFFICULTY_HALFWORD = _CODE.index(_word(ppc.li(0, 0))) + 2
_CHAPTER_HALFWORD = _CODE.index(_word(ppc.li(4, 0))) + 2

JUMP_PATCH = CATALOG.add(Patch(
    "rd.dev.jump_chapter", "Radiant Dawn developer tools", "Boot into a chapter",
    "Skips the title and starts an RFEE01 chapter with a fresh party (test launches only).",
    versions={RFEE01: (
        Edit(_SCRIPT_SITE, _SCRIPT_ORIGINAL,
             _words(_CALL, JUMP_STUB, _GOTO_11, _SLEEP)),
        Edit(JUMP_STUB, bytes(len(_CODE)), _CODE,
             wild=((_DIFFICULTY_HALFWORD, 2), (_CHAPTER_HALFWORD, 2))),
    )}, internal=True,
))


def install(session: Session, chapter_number: int, difficulty: int) -> None:
    """Install the RFEE01 jump using the chapter's internal one-byte number."""
    if session.version is None or session.version.code != RFEE01:
        raise ValueError("The Radiant Dawn chapter jump currently supports RFEE01 only.")
    if not 0 <= chapter_number <= 0xFF:
        raise ValueError(f"Chapter number {chapter_number} is out of range (0-255).")
    if difficulty not in DIFFICULTIES.values():
        raise ValueError(f"Unknown difficulty {difficulty}.")
    session.set_patch(JUMP_PATCH, True)
    session._write(JUMP_STUB + _DIFFICULTY_HALFWORD, difficulty.to_bytes(2, "big"))
    session._write(JUMP_STUB + _CHAPTER_HALFWORD, chapter_number.to_bytes(2, "big"))
