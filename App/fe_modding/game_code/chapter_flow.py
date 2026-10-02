"""Story flow: which chapter follows which, as a table in ``main.dol``.

Retail moves to ``current + 1`` when a chapter is cleared (``advance_chapter_on_complete``, both of
its ``set_current_chapter`` calls), and the save menu refuses any chapter above 31 (the two
``cmplwi r0,31`` of ``check_chapter_special_context_state`` / ``check_chapter_save_state_validity``,
which show ``MH_SAL_TRIAL_SAVE_NG``). The hook below replaces both:

- the ``set_current_chapter`` calls go through :data:`FLOW_HOOK`, which looks the cleared chapter up
  in :data:`FLOW_TABLE` (256 bytes, one per chapter id) and uses the entry when it is not 0;
- the save checks go through :data:`SAVE_CHECK`: chapters 0-31 as before, and a chapter above 31
  counts as a story chapter (saving allowed) when it has a table entry. 32 (game cleared) and the
  trial maps never get one, so they keep their retail behaviour.

With every entry 0 the hook changes nothing; the editor then takes it out again.
"""

from __future__ import annotations

from . import ppc
from .catalog import CATALOG, CAVE_ADDRESS, CAVE_SIZE, Edit, Patch, State, in_cave

US, EU, JP = "GFEE01", "GFEP01", "GFEJ01"

FLOW_HOOK = CAVE_ADDRESS + 0x1600
SAVE_CHECK = CAVE_ADDRESS + 0x1620
FLOW_TABLE = CAVE_ADDRESS + 0x1700
assert in_cave(FLOW_TABLE, 0x100) and FLOW_TABLE + 0x100 == CAVE_ADDRESS + CAVE_SIZE

GAME_CLEARED = 32          # the chapter number that plays the ending
LAST_RETAIL_STORY = 31
FIRST_TRIAL = 90           # ChapterData ids >= 90 are trial maps
CONTINUED_PART = 28        # Ch.27 part 1: its successor skips the save menu and the army cleanup

# version: (set_current_chapter, its call in the Ch.27-1 branch, its call in the normal branch,
#           the two `cmplwi r0,31` save checks)
_SITES = {
    US: (0x8014D2B0, 0x8002E234, 0x8002E3B8, (0x8011BB4C, 0x8011BC5C)),
    EU: (0x8014E638, 0x8002E3D4, 0x8002E558, (0x8011C5A4, 0x8011C6B4)),
    JP: (0x8014A6C8, 0x8002D608, 0x8002D78C, (0x8011937C, 0x8011948C)),
}
_CMPLWI_R0_31 = ppc.cmplwi(0, LAST_RETAIL_STORY)


def _word(value: int) -> bytes:
    return value.to_bytes(4, "big")


def _words(values) -> bytes:
    return b"".join(_word(v) for v in values)


def _flow_hook(set_chapter: int) -> bytes:
    """``set_current_chapter(r3 = party, r4 = cleared + 1)`` with r4 replaced by the table entry."""
    return _words(ppc.assemble(FLOW_HOOK, [
        ppc.lbz(5, 0x10, 3),                         # the chapter just cleared
        ppc.lis(6, 0x8000), ppc.addi(6, 6, FLOW_TABLE & 0xFFFF),
        ppc.lbzx(5, 6, 5),
        ppc.cmpwi(5, 0), ("eq", "keep"),
        ppc.mr(4, 5),
        "keep",
        ("b", set_chapter),
    ]))


def _save_check() -> bytes:
    """Sets cr0 for the caller's ``ble`` (save allowed) from the chapter in r0."""
    return _words(ppc.assemble(SAVE_CHECK, [
        _CMPLWI_R0_31, ("le", "done"),               # retail story chapters
        ppc.lis(12, 0x8000), ppc.addi(12, 12, FLOW_TABLE & 0xFFFF),
        ppc.lbzx(12, 12, 0),
        ppc.cmplwi(12, 0), ("ne", "story"),
        _CMPLWI_R0_31, ppc.BLR,                      # not in the flow: "greater", as retail
        "story",
        ppc.cmplw(0, 0),                             # "equal": the caller's ble takes it
        "done",
        ppc.BLR,
    ]))


def _edits(version: str) -> tuple[Edit, ...]:
    set_chapter, call_part, call_normal, checks = _SITES[version]
    hook, check = _flow_hook(set_chapter), _save_check()
    assert FLOW_HOOK + len(hook) <= SAVE_CHECK and SAVE_CHECK + len(check) <= FLOW_TABLE
    return (
        Edit(call_part, _word(ppc.bl(call_part, set_chapter)), _word(ppc.bl(call_part, FLOW_HOOK))),
        Edit(call_normal, _word(ppc.bl(call_normal, set_chapter)), _word(ppc.bl(call_normal, FLOW_HOOK))),
        *(Edit(a, _word(_CMPLWI_R0_31), _word(ppc.bl(a, SAVE_CHECK))) for a in checks),
        Edit(FLOW_HOOK, bytes(len(hook)), hook),
        Edit(SAVE_CHECK, bytes(len(check)), check),
    )


FLOW_PATCH = CATALOG.add(Patch(
    "chapters.flow.hook", "Chapters", "Story flow table",
    "Makes the next chapter after each chapter come from a table, and lets added chapters be saved.",
    versions={v: _edits(v) for v in _SITES}, internal=True))


def can_have_successor(chapter: int) -> bool:
    """Chapters whose next chapter may be chosen (not "game cleared", not a trial map)."""
    return 0 <= chapter < FIRST_TRIAL and chapter != GAME_CLEARED


def can_follow(chapter: int) -> bool:
    """Chapters that may be chosen as a next chapter (32 plays the ending)."""
    return 1 <= chapter < FIRST_TRIAL


class ChapterFlow:
    """The story flow of a project's ``main.dol``, through its :class:`~.editor.CodeEditor`.

    Every change is saved at once, like the editor's other edits."""

    def __init__(self, editor):
        self.editor = editor

    @property
    def status(self):
        return self.editor.status(FLOW_PATCH)

    @property
    def available(self) -> bool:
        return self.status.state in (State.ORIGINAL, State.APPLIED)

    @property
    def unavailable_reason(self) -> str:
        status = self.status
        return "" if self.available else (status.detail or "main.dol cannot be patched.")

    def overrides(self) -> dict[int, int]:
        """Chapter -> next chapter, for every chapter that does not simply go to ``+ 1``."""
        if self.status.state != State.APPLIED:
            return {}
        table = self.editor.dol.read(FLOW_TABLE, 0x100)
        return {chapter: nxt for chapter, nxt in enumerate(table) if nxt}

    def next_of(self, chapter: int) -> int:
        return self.overrides().get(chapter, chapter + 1)

    def is_story(self, chapter: int) -> bool:
        """Saving is allowed in this chapter (retail story chapters, and added ones in the flow)."""
        return 0 <= chapter <= LAST_RETAIL_STORY or chapter in self.overrides()

    def set_next(self, chapter: int, nxt: int) -> str:
        return self.set_many({chapter: nxt})

    def set_many(self, changes: dict[int, int]) -> str:
        """Set several successors in one save. A chapter above 31 always keeps an entry (that is
        what makes it a story chapter for the save menu); retail chapters going to ``+ 1`` don't."""
        if not self.available:
            raise ValueError(f"Story flow: {self.unavailable_reason}")
        for chapter, nxt in changes.items():
            if not can_have_successor(chapter):
                raise ValueError(f"Chapter {chapter} cannot have a next chapter.")
            if not can_follow(nxt):
                raise ValueError(f"Chapter {nxt} cannot follow a chapter (1-89).")
        return self._store({c: 0 if c <= LAST_RETAIL_STORY and n == c + 1 else n for c, n in changes.items()},
                           ", ".join(f"after {c:02d}: {n:02d}" for c, n in sorted(changes.items())))

    def _store(self, raw: dict[int, int], description: str) -> str:
        """Write table bytes (0 = retail ``+ 1``), installing or removing the hook as needed."""
        session = self.editor.session
        if self.status.state == State.ORIGINAL and any(raw.values()):
            session.set_patch(FLOW_PATCH, True)
        if self.status.state == State.APPLIED:
            for chapter, value in raw.items():
                session._write(FLOW_TABLE + chapter, bytes([value]))
            if not any(self.editor.dol.read(FLOW_TABLE, 0x100)):
                session.set_patch(FLOW_PATCH, False)
        self.editor.save()
        return description

    def remove(self, chapter: int) -> str:
        """Take ``chapter`` out of the flow: whatever led to it goes to its successor instead."""
        if not self.available:
            raise ValueError(f"Story flow: {self.unavailable_reason}")
        overrides = self.overrides()
        if chapter <= LAST_RETAIL_STORY:
            raise ValueError(f"Chapter {chapter} is a retail chapter; change the chapter before it instead.")
        after = self.next_of(chapter)
        raw = {c: 0 if c <= LAST_RETAIL_STORY and after == c + 1 else after
               for c, n in overrides.items() if n == chapter and c != chapter}
        raw[chapter] = 0
        return self._store(raw, f"removed {chapter:02d} from the story flow")

    def order(self, start: int = 1, limit: int = 256) -> list[int]:
        """The chapters a new game plays, from ``start`` up to the ending (32), in order."""
        seen, chapter, result = set(), start, []
        while chapter != GAME_CLEARED and chapter not in seen and len(result) < limit:
            seen.add(chapter)
            result.append(chapter)
            chapter = self.next_of(chapter)
        return result

    def predecessors(self, chapter: int) -> list[int]:
        """Chapters whose next chapter is ``chapter``."""
        overrides = self.overrides()
        result = [c for c, n in overrides.items() if n == chapter]
        if 1 <= chapter - 1 <= LAST_RETAIL_STORY and chapter - 1 not in overrides:
            result.append(chapter - 1)
        return sorted(result)
