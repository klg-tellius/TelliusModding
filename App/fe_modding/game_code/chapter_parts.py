"""Two-part chapters: let any chapter carry on into the next one the way chapter 28 does into 29.

Retail treats the step from 28 (Ch.27, first map) to its successor as one chapter carrying on:

- ``advance_chapter_on_complete`` tests ``current_chapter_number == 28`` (``cmplwi r0,28``): the
  successor starts with turn 1 but the army cleanup (units joining the player army, Ike's status
  flag) is skipped, and the clear history entry gets the continued-part flag (1);
- GameController label 19 skips the save menu when ``current_chapter_is_29``;
- ``apply_chapter_end_support_and_unit_flags`` (start of every battle map) skips the support pass
  in chapter 29, and in chapter 18 while ``party_resume_point`` is 5-7 (a ``Complete18`` part).

:data:`PARTS_PATCH` replaces the 28 test with a list of chapters (:data:`PART_LIST`, 28 always
included), and both 29 tests with "the last clear history entry has the continued-part flag", which
is what the 28 branch writes and is saved with the game, so a reload keeps it. Retail's 28 -> 29
behaves as before. After 40 clears the history is full (the game stops recording), so a continued
part reached later is treated as a normal chapter start; the project check warns past 40 clears.

:data:`PART_SUPPORTS_PATCH` drops the chapter-18 test from the ``Complete18`` support skip, so a
chapter split with ``Complete18`` in any chapter counts supports once rather than once per part.
Retail only sets resume points 5-7 in chapter 18, so it changes nothing there.
"""

from __future__ import annotations

from . import ppc
from .catalog import CATALOG, CAVE_ADDRESS, Edit, Patch, State, in_cave

US, EU, JP = "GFEE01", "GFEP01", "GFEJ01"

PART_TEST = CAVE_ADDRESS + 0xA40       # cr0 "eq" when the chapter in r0 carries on into the next
HISTORY_TEST = CAVE_ADDRESS + 0xA80    # cr0 "eq" when the last clear history entry is a continued part
PART_LIST = CAVE_ADDRESS + 0xAE0       # chapter ids, 0-terminated
PART_LIST_SIZE = 0x20
assert in_cave(PART_TEST, PART_LIST + PART_LIST_SIZE - PART_TEST) and PART_LIST + PART_LIST_SIZE == CAVE_ADDRESS + 0xB00

RETAIL_PART = 28
HISTORY_OFFSET = 0x3C4                 # party_data + 0x3C4: 40 entries of 8 bytes
HISTORY_SLOTS = 40

_MFLR_R8 = 0x7D0802A6
_MTLR_R8 = 0x7D0803A6
_BNELR = 0x4C820020

# version: (advance_chapter_on_complete's `cmplwi r0,28`, current_chapter_is_29,
#           apply_chapter_end_support_and_unit_flags' `cmplwi r0,29`, party_data)
_SITES = {
    US: (0x8002E110, 0x80005E98, 0x8002E958, 0x80330708),
    EU: (0x8002E2B0, 0x80005E9C, 0x8002EAF8, 0x8033A708),
    JP: (0x8002D4E4, 0x80005E98, 0x8002DD2C, 0x8032E788),
}


def _word(value: int) -> bytes:
    return value.to_bytes(4, "big")


def _words(values) -> bytes:
    return b"".join(_word(v) for v in values)


def _hi(address: int) -> int:
    return ((address + 0x8000) >> 16) & 0xFFFF


def _lo(address: int) -> int:
    return ppc.sext16(address & 0xFFFF)


def _part_test() -> list[int]:
    return ppc.assemble(PART_TEST, [
        ppc.cmplwi(0, RETAIL_PART), ("eq", "done"),
        ppc.lis(12, _hi(PART_LIST)), ppc.addi(12, 12, _lo(PART_LIST)),
        "next",
        ppc.lbz(11, 0, 12),
        ppc.cmpwi(11, 0), ("eq", "absent"),
        ppc.cmplw(11, 0), ("eq", "done"),
        ppc.addi(12, 12, 1),
        ("b", "next"),
        "absent",
        ppc.cmplwi(12, 0),                           # an address: "not equal"
        "done",
        ppc.BLR,
    ])


def _history_test(party: int) -> list[int]:
    """Keeps r0-r8: the support site still needs r0 (chapter) and r3 (party_data)."""
    history = party + HISTORY_OFFSET
    return ppc.assemble(HISTORY_TEST, [
        ppc.lis(12, _hi(history)), ppc.addi(12, 12, _lo(history)),
        ppc.li(10, HISTORY_SLOTS), ppc.li(11, 0),
        "next",
        ppc.lhz(9, 2, 12),                           # turn count: 0 = free slot
        ppc.cmplwi(9, 0), ("eq", "done"),
        ppc.lbz(11, 1, 12),                          # continued-part flag of this entry
        ppc.addi(12, 12, 8),
        ppc.addi(10, 10, -1),
        ppc.cmpwi(10, 0), ("ne", "next"),
        "done",
        ppc.cmplwi(11, 1),
        ppc.BLR,
    ])


def _is_continued(at: int) -> list[int]:
    """The 7-word body of ``current_chapter_is_29``: 1 when the last clear carried on."""
    return [_MFLR_R8, ppc.bl(at + 4, HISTORY_TEST), _MTLR_R8, ppc.li(3, 0), _BNELR, ppc.li(3, 1), ppc.BLR]


def _retail_is_29(party: int) -> list[int]:
    return [ppc.lis(3, _hi(party)), ppc.addi(3, 3, _lo(party)), ppc.lbz(0, 0x10, 3),
            0x2000001D, 0x7C000034, 0x5403D97E, ppc.BLR]      # subfic r0,r0,29; cntlzw; srwi 5


def _edits(version: str) -> tuple[Edit, ...]:
    advance, is29, support, party = _SITES[version]
    part, history = _part_test(), _history_test(party)
    assert PART_TEST + 4 * len(part) <= HISTORY_TEST and HISTORY_TEST + 4 * len(history) <= PART_LIST
    return (
        Edit(advance, _word(ppc.cmplwi(0, RETAIL_PART)), _word(ppc.bl(advance, PART_TEST))),
        Edit(is29, _words(_retail_is_29(party)), _words(_is_continued(is29))),
        Edit(support, _word(ppc.cmplwi(0, 29)), _word(ppc.bl(support, HISTORY_TEST))),
        Edit(PART_TEST, bytes(4 * len(part)), _words(part)),
        Edit(HISTORY_TEST, bytes(4 * len(history)), _words(history)),
    )


PARTS_PATCH = CATALOG.add(Patch(
    "chapters.flow.parts", "Chapters", "Two-part chapters",
    "Lets chapters other than 28 carry on into the next chapter as a second part.",
    versions={v: _edits(v) for v in _SITES}, internal=True))


def _support_edits(version: str) -> tuple[Edit, ...]:
    site = _SITES[version][2] + 8                    # `cmplwi r0,18` after the 29 test's beq
    return (Edit(site, _word(ppc.cmplwi(0, 18)), _word(ppc.cmplw(0, 0))),)


PART_SUPPORTS_PATCH = CATALOG.add(Patch(
    "chapters.parts.supports_once", "Chapters", "Count supports once in split chapters",
    "A chapter split into parts with Complete18 counts support points at the start of each part, "
    "except chapter 18. This makes every chapter count them once, at the first part. Retail only "
    "splits chapter 18, so vanilla play is unchanged.",
    versions={v: _support_edits(v) for v in _SITES}))


class ChapterParts:
    """The two-part chapters of a project's ``main.dol``, through its :class:`~.editor.CodeEditor`."""

    def __init__(self, editor):
        self.editor = editor

    @property
    def status(self):
        return self.editor.status(PARTS_PATCH)

    @property
    def available(self) -> bool:
        return self.status.state in (State.ORIGINAL, State.APPLIED)

    def continued(self) -> set[int]:
        """Chapters whose successor is their second part (28 always)."""
        result = {RETAIL_PART}
        if self.status.state == State.APPLIED:
            for value in self.editor.dol.read(PART_LIST, PART_LIST_SIZE):
                if not value:
                    break
                result.add(value)
        return result

    def set_continued(self, chapter: int, on: bool) -> str:
        if chapter == RETAIL_PART:
            raise ValueError("Chapter 28 always carries on into the next chapter.")
        if not 0 <= chapter < 90 or chapter == 32:
            raise ValueError(f"Chapter {chapter} cannot have a second part.")
        if not self.available:
            raise ValueError(f"Two-part chapters: {self.status.detail or 'main.dol cannot be patched.'}")
        chapters = sorted((self.continued() - {RETAIL_PART} - {chapter}) | ({chapter} if on else set()))
        if len(chapters) >= PART_LIST_SIZE:
            raise ValueError(f"At most {PART_LIST_SIZE - 1} chapters can have a second part.")
        session = self.editor.session
        if chapters and self.status.state == State.ORIGINAL:
            session.set_patch(PARTS_PATCH, True)
        if self.status.state == State.APPLIED:
            session._write(PART_LIST, bytes(chapters).ljust(PART_LIST_SIZE, b"\x00"))
            if not chapters:
                session.set_patch(PARTS_PATCH, False)
        self.editor.save()
        return f"chapter {chapter:02d} {'carries on into' if on else 'no longer carries on into'} its next chapter"
