"""Boot straight into a chapter: the "Play in Dolphin" test launch.

``GameController`` label 2 starts the title screen (``start_child_and_wait E_Title``), then label 5
opens the file menu. The patch makes label 2 ``call`` :data:`JUMP_STUB` instead, which sets the
difficulty byte (``party_data+0xA6``, ``current_difficulty_id``) and calls
``init_chapter_from_mode_table`` the way the developer chapter select does: with a menu entry whose
byte ``+4`` is the chapter's *position* in ``ChapterData``. That function resets the army (a fresh
party, as for a trial map), sets the chapter and the GameController's next label to 10. Label 5
then goes through :data:`JUMP_PREDICATE`, which skips the file menu when the next label is no
longer 5, so the script moves on to label 10: the chapter starts.

Game over returns to the title (label 2), so it restarts the same chapter.

The patch is never written into a project's own ``main.dol``: :func:`install` is used on the copy
``emulator.prepare_chapter_run`` makes for one test launch. It shares the label-5 call with the
development boot menu (``dev.boot_menu``), which :func:`install` therefore turns off in the copy.
"""

from __future__ import annotations

from . import ppc
from .catalog import CATALOG, CAVE_ADDRESS, Edit, Patch, Session, State, in_cave

US, EU, JP = "GFEE01", "GFEP01", "GFEJ01"

JUMP_STUB = CAVE_ADDRESS + 0xA00
JUMP_RECORD = JUMP_STUB + 0x20         # the fake menu entry: byte +4 is the ChapterData position
JUMP_PREDICATE = JUMP_STUB + 0x30
JUMP_END = JUMP_STUB + 0x40
assert in_cave(JUMP_STUB, JUMP_END - JUMP_STUB)

DIFFICULTY_OFFSET = 0xA6               # party_data + 0xA6: current_difficulty_id
#: ``current_difficulty_id`` values, in the order a menu shows them.
DIFFICULTIES = {"Easy": 3, "Normal": 0, "Hard": 1, "Maniac": 2}

_START_CHILD_AND_WAIT = 0x0000201D     # process-script ops (length 2: op word + operand)
_CALL = 0x0000200F
_BNELR = 0x4C820020

# version: (label 2's start_child_and_wait E_Title, the E_Title script, label 5's file-menu call
#           operand, the file-menu routine, init_chapter_from_mode_table, party_data)
_SITES = {
    US: (0x802833E4, 0x8028C8E0, 0x80283408, 0x801D3B7C, 0x800AA078, 0x80330708),
    EU: (0x8028D2FC, 0x8029685C, 0x8028D320, 0x801D6BA0, 0x800AA390, 0x8033A708),
    JP: (0x8027E048, 0x8028749C, 0x8027E06C, 0x801D1C88, 0x800A83C8, 0x8032E788),
}


def _word(value: int) -> bytes:
    return value.to_bytes(4, "big")


def _words(*values: int) -> bytes:
    return b"".join(_word(v) for v in values)


def _cave_code(init_chapter: int, party: int, file_menu: int) -> bytes:
    difficulty = party + DIFFICULTY_OFFSET
    stub = _words(*ppc.assemble(JUMP_STUB, [
        ppc.li(0, DIFFICULTIES["Normal"]),                     # the difficulty (wild: set by install)
        ppc.lis(4, (difficulty + 0x8000) >> 16), ppc.stb(0, ppc.sext16(difficulty & 0xFFFF), 4),
        ppc.lis(3, 0x8000), ppc.addi(3, 3, JUMP_RECORD & 0xFFFF),
        ("b", init_chapter),
    ]))
    record = bytes(8)                                          # byte +4: the position (wild)
    predicate = _words(*ppc.assemble(JUMP_PREDICATE, [         # open the file menu only if still label 5
        ppc.lwz(0, 0x60, 3), ppc.cmpwi(0, 5), _BNELR,
        ("b", file_menu),
    ]))
    data = stub.ljust(JUMP_RECORD - JUMP_STUB, b"\x00") + record
    data = data.ljust(JUMP_PREDICATE - JUMP_STUB, b"\x00") + predicate
    return data.ljust(JUMP_END - JUMP_STUB, b"\x00")


_WILD = ((2, 2), (JUMP_RECORD - JUMP_STUB + 4, 1))


def _edits(version: str) -> tuple[Edit, ...]:
    start, title, call, file_menu, init_chapter, party = _SITES[version]
    code = _cave_code(init_chapter, party, file_menu)
    return (
        Edit(start, _words(_START_CHILD_AND_WAIT, title), _words(_CALL, JUMP_STUB)),
        Edit(call, _word(file_menu), _word(JUMP_PREDICATE)),
        Edit(JUMP_STUB, bytes(len(code)), code, wild=_WILD),
    )


JUMP_PATCH = CATALOG.add(Patch(
    "dev.jump_chapter", "Developer tools", "Boot into a chapter",
    "Skips the title screen and the file menu and starts one chapter with a fresh army (test launches).",
    versions={v: _edits(v) for v in _SITES}, internal=True))


def install(session: Session, position: int, difficulty: int) -> None:
    """Make ``session``'s DOL boot into the ``ChapterData`` record at ``position`` on ``difficulty``
    (a :data:`DIFFICULTIES` value)."""
    if not 0 <= position <= 0x7F:          # the game sign-extends the byte
        raise ValueError(f"ChapterData position {position} is out of range (0-127).")
    if difficulty not in DIFFICULTIES.values():
        raise ValueError(f"Unknown difficulty {difficulty}.")
    boot_menu = CATALOG.entries["dev.boot_menu"]       # shares the label-5 call
    if session.patch_status(boot_menu).state == State.APPLIED:
        session.set_patch(boot_menu, False)
    session.set_patch(JUMP_PATCH, True)
    session._write(JUMP_STUB + 2, difficulty.to_bytes(2, "big"))
    session._write(JUMP_RECORD + 4, bytes([position]))
