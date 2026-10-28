"""Radiant Dawn story order and per-chapter army metadata (RFEE01).

Radiant Dawn's retail chapter advance routine indexes ``ChapterData`` by the
next chapter *number*.  That happens to work for retail story records 0-55,
but records 56-59 are tutorials whose numbers are 80-83.  Custom story
chapters therefore cannot safely use the retail routine.

The small version-checked hook here keeps the retail routine for retail
chapters (including its processing of hidden ``C0401a``/``C0401b`` records),
then applies an optional successor.  Chapters 56-79 bypass the unsafe retail
lookup and use the successor table directly.

The remaining tables are the editor-owned story model.  They deliberately use
logical army identities; raw force/convoy implementation belongs to the
separate army-switch runtime and is not guessed here.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum
from typing import Iterable

from . import ppc
from .catalog import CAVE_ADDRESS, Edit, Patch, State, in_cave

RFEE01 = "RFEE01"

HOOK = CAVE_ADDRESS
SUCCESSORS = CAVE_ADDRESS + 0x400
ARMIES = CAVE_ADDRESS + 0x500
FLAGS = CAVE_ADDRESS + 0x600
MAGIC = CAVE_ADDRESS + 0x700
MAGIC_BYTES = b"RDS1"

CUSTOM_FIRST = 56
CUSTOM_LAST = 79
ENDING = 55

FLAG_PART_BOUNDARY = 0x01
FLAG_DIVIDE_ARMIES = 0x02

# Successor routing is installed and verified.  Do not let the UI present army
# switching as live until the force-4 persistence and moved DivideForce path
# have both been verified in Dolphin.
ARMY_RUNTIME_READY = False

# RFEE01 addresses confirmed against SHA-1 d1b8deabfec5a96bf38945665ffe203867612c1c.
_ADVANCE = 0x80067EE8
_SET_CHAPTER = 0x80061584
_PARTY = 0x803CAB38
_CURRENT_CHAPTER = 0x803CAB48
_RESUME_POINT = 0x803CABD4
_CALLS = (0x80043B6C, 0x800CD8F8)

assert in_cave(HOOK, 0x704)


class Army(IntEnum):
    INHERIT = 0
    MAIN = 1
    DIVISION_1 = 2       # Micaiah
    DIVISION_2 = 3       # Ike
    DIVISION_3 = 4       # Tibarn

    @property
    def label(self) -> str:
        return {
            Army.INHERIT: "Inherit previous",
            Army.MAIN: "Main army",
            Army.DIVISION_1: "Micaiah division",
            Army.DIVISION_2: "Ike division",
            Army.DIVISION_3: "Tibarn division",
        }[self]


@dataclass(frozen=True)
class ChapterStep:
    chapter: int
    chapter_id: str
    army: Army = Army.INHERIT


@dataclass(frozen=True)
class PartBoundaryStep:
    """A part boundary immediately before ``before``."""

    before: int


@dataclass(frozen=True)
class DivideArmiesStep:
    """The division prompt immediately before ``before``."""

    before: int


StoryStep = ChapterStep | PartBoundaryStep | DivideArmiesStep


def _word(value: int) -> bytes:
    return value.to_bytes(4, "big")


def _words(values) -> bytes:
    return b"".join(_word(value) for value in values)


def _hook() -> bytes:
    """Call retail safely, then apply the configured successor when present."""
    return _words(ppc.assemble(HOOK, [
        ppc.stwu(1, -0x20, 1),
        ppc.MFLR_R0,
        ppc.stw(0, 0x24, 1),
        ppc.lis(12, 0x803D),
        ppc.lbz(5, _CURRENT_CHAPTER - 0x803D0000, 12),
        ppc.stw(5, 8, 1),
        ppc.cmplwi(5, CUSTOM_FIRST), ("ge", "custom"),
        ("bl", _ADVANCE),
        ("b", "lookup"),
        "custom",
        ppc.li(3, 1),
        "lookup",
        ppc.lwz(5, 8, 1),
        ppc.lis(6, SUCCESSORS >> 16),
        ppc.addi(6, 6, SUCCESSORS & 0xFFFF),
        ppc.lbzx(4, 6, 5),
        ppc.cmplwi(4, 0), ("eq", "done"),
        ppc.lis(3, 0x803D),
        ppc.addi(3, 3, _PARTY - 0x803D0000),
        ("bl", _SET_CHAPTER),
        ppc.lis(6, 0x803D),
        ppc.li(5, 4),
        ppc.stb(5, _RESUME_POINT - 0x803D0000, 6),
        ppc.li(3, 1),
        "done",
        ppc.lwz(0, 0x24, 1),
        ppc.MTLR_R0,
        ppc.addi(1, 1, 0x20),
        ppc.BLR,
    ]))


def _retail_armies() -> bytes:
    """Logical defaults inferred from confirmed Part 4 TEAM transitions."""
    values = bytearray(0x100)
    # Before the Part 4 split the currently playing force is the undivided Main army.
    for chapter in range(0, 32):
        values[chapter] = Army.MAIN
    for first, army in ((32, Army.DIVISION_1), (35, Army.DIVISION_2),
                        (38, Army.DIVISION_3), (41, Army.DIVISION_1),
                        (44, Army.DIVISION_2), (47, Army.DIVISION_3)):
        for chapter in range(first, first + 3):       # visible record plus attached a/b records
            values[chapter] = army
    for chapter in range(50, 56):
        values[chapter] = Army.MAIN
    return bytes(values)


def _retail_flags() -> bytes:
    values = bytearray(0x100)
    for chapter in (12, 17, 32):
        values[chapter] |= FLAG_PART_BOUNDARY
    values[32] |= FLAG_DIVIDE_ARMIES
    return bytes(values)


def _edits() -> tuple[Edit, ...]:
    hook = _hook()
    return (
        *(Edit(site, _word(ppc.bl(site, _ADVANCE)), _word(ppc.bl(site, HOOK))) for site in _CALLS),
        Edit(HOOK, bytes(len(hook)), hook),
        Edit(SUCCESSORS, bytes(0x100), bytes(0x100), wild=((0, 0x100),)),
        Edit(ARMIES, bytes(0x100), _retail_armies(), wild=((0, 0x100),)),
        Edit(FLAGS, bytes(0x100), _retail_flags(), wild=((0, 0x100),)),
        Edit(MAGIC, bytes(4), MAGIC_BYTES),
    )


PATCH = Patch(
    "rd.story.runtime", "Chapters", "Radiant Dawn story order",
    "Uses an explicit RFEE01 chapter sequence and stores part, division and logical-army metadata.",
    {RFEE01: _edits()}, internal=True)


class StorySequence:
    """RFEE01 story sequence backed by the version-checked DOL tables."""

    def __init__(self, editor, chapter_ids: dict[int, str] | None = None):
        self.editor = editor
        self.chapter_ids = dict(chapter_ids or {})

    @property
    def status(self):
        return self.editor.status(PATCH)

    @property
    def available(self) -> bool:
        return self.status.state in (State.ORIGINAL, State.APPLIED)

    @property
    def unavailable_reason(self) -> str:
        return "" if self.available else (self.status.detail or "RFEE01 story runtime is unavailable.")

    @property
    def installed(self) -> bool:
        return self.status.state == State.APPLIED

    def _table(self, address: int, default: bytes) -> bytes:
        return self.editor.dol.read(address, 0x100) if self.installed else default

    def successors(self) -> dict[int, int]:
        raw = self._table(SUCCESSORS, bytes(0x100))
        return {chapter: nxt for chapter, nxt in enumerate(raw) if nxt}

    def next_of(self, chapter: int) -> int | None:
        override = self.successors().get(chapter)
        if override is not None:
            return override
        return retail_next(chapter)

    def predecessors(self, chapter: int) -> list[int]:
        return [candidate for candidate in range(0x100) if self.next_of(candidate) == chapter]

    def configured_army(self, chapter: int) -> Army:
        return Army(self._table(ARMIES, _retail_armies())[chapter])

    def flags(self, chapter: int) -> int:
        return self._table(FLAGS, _retail_flags())[chapter]

    def effective_army(self, chapter: int) -> Army | None:
        seen = set()
        current = chapter
        while current not in seen:
            seen.add(current)
            army = self.configured_army(current)
            if army != Army.INHERIT:
                return army
            previous = self.predecessors(current)
            if len(previous) != 1:
                return None
            current = previous[0]
        return None

    def army_initialized(self, chapter: int, army: Army) -> bool:
        if army in (Army.INHERIT, Army.MAIN):
            return True
        for step in self.steps():
            if isinstance(step, DivideArmiesStep):
                return self._comes_before(step.before, chapter)
        return False

    def _comes_before(self, first: int, second: int) -> bool:
        order = self.order()
        return first in order and second in order and order.index(first) <= order.index(second)

    def order(self, start: int = 0, limit: int = 256) -> list[int]:
        result, seen, chapter = [], set(), start
        while chapter is not None and chapter not in seen and len(result) < limit:
            result.append(chapter)
            if chapter == ENDING:
                break
            seen.add(chapter)
            chapter = self.next_of(chapter)
        return result

    def steps(self) -> list[StoryStep]:
        result: list[StoryStep] = []
        for chapter in self.order():
            flags = self.flags(chapter)
            if flags & FLAG_PART_BOUNDARY:
                result.append(PartBoundaryStep(chapter))
            if flags & FLAG_DIVIDE_ARMIES:
                result.append(DivideArmiesStep(chapter))
            result.append(ChapterStep(chapter, self.chapter_ids.get(chapter, f"C{chapter:04d}"),
                                      self.configured_army(chapter)))
        return result

    def validate(self, steps: Iterable[StoryStep]) -> list[str]:
        steps = list(steps)
        chapters = [step for step in steps if isinstance(step, ChapterStep)]
        problems: list[str] = []
        numbers = [step.chapter for step in chapters]
        if len(numbers) != len(set(numbers)):
            problems.append("A chapter can only appear once in the story order.")
        if not chapters:
            problems.append("The story needs at least one chapter.")
        elif chapters[-1].chapter != ENDING:
            problems.append("CFINAL must be the last chapter in the story order.")
        for step in chapters:
            if not (0 <= step.chapter <= ENDING or CUSTOM_FIRST <= step.chapter <= CUSTOM_LAST):
                problems.append(f"{step.chapter_id} has no supported story number (0-55 or 56-79 custom).")
        if any(isinstance(step, (PartBoundaryStep, DivideArmiesStep)) and
               not any(isinstance(later, ChapterStep) for later in steps[i + 1:])
               for i, step in enumerate(steps)):
            problems.append("Part and division steps must be followed by a chapter.")
        if sum(isinstance(step, DivideArmiesStep) for step in steps) > 1:
            problems.append("Divide armies can only appear once.")
        divided = False
        effective: Army | None = None
        for step in steps:
            if isinstance(step, DivideArmiesStep):
                divided = True
            elif isinstance(step, ChapterStep):
                effective = effective if step.army == Army.INHERIT else step.army
                if effective is None:
                    problems.append(f"{step.chapter_id} inherits an army, but no earlier chapter selects one.")
                elif effective in (Army.DIVISION_1, Army.DIVISION_2, Army.DIVISION_3) and not divided:
                    problems.append(f"{step.chapter_id} selects {effective.label} before Divide armies.")
        return problems

    def set_steps(self, steps: Iterable[StoryStep]) -> str:
        steps = list(steps)
        problems = self.validate(steps)
        if problems:
            raise ValueError("Invalid story order:\n  " + "\n  ".join(problems))
        if not self.available:
            raise ValueError(self.unavailable_reason)
        chapters = [step for step in steps if isinstance(step, ChapterStep)]
        if not self.installed:
            self.editor.session.set_patch(PATCH, True)
        successors = bytearray(0x100)
        armies = bytearray(0x100)
        flags = bytearray(0x100)
        for current, following in zip(chapters, chapters[1:]):
            retail = retail_next(current.chapter)
            if following.chapter != retail or current.chapter >= CUSTOM_FIRST:
                successors[current.chapter] = following.chapter
        for step in chapters:
            armies[step.chapter] = int(step.army)
        for i, step in enumerate(steps):
            if isinstance(step, PartBoundaryStep):
                following = next(later for later in steps[i + 1:] if isinstance(later, ChapterStep))
                flags[following.chapter] |= FLAG_PART_BOUNDARY
            elif isinstance(step, DivideArmiesStep):
                following = next(later for later in steps[i + 1:] if isinstance(later, ChapterStep))
                flags[following.chapter] |= FLAG_DIVIDE_ARMIES
        self.editor.session._write(SUCCESSORS, bytes(successors))
        self.editor.session._write(ARMIES, bytes(armies))
        self.editor.session._write(FLAGS, bytes(flags))
        self.editor.save()
        return "updated Radiant Dawn story order"


def chapter_number_map(fe10data_bytes: bytes) -> dict[int, str]:
    """Internal chapter number -> canonical ID, excluding tutorial records."""
    from ..formats import fe10data
    return {record.values["number"]: record.values["cid"] for record in fe10data.read_table(fe10data_bytes, "chapter")
            if record.values["cid"] and not record.values["cid"].startswith("T")}


def retail_next(chapter: int) -> int | None:
    """Retail's visible successor after attached hidden Part 4 transition records."""
    if chapter in (32, 35, 38, 41, 44, 47):
        return chapter + 3
    if 33 <= chapter <= 49 and chapter % 3 in (0, 1):
        return None
    return chapter + 1 if 0 <= chapter < ENDING else None
