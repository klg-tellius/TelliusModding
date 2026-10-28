"""One story-flow interface for both games, so the chapter pages edit it through the same controls.

Path of Radiance keeps its flow in :mod:`.chapter_flow` (a successor table, chapter numbers 1-89,
"32" the ending) and Radiant Dawn in :mod:`.rd_story` (successor, army and part tables, retail
numbers 0-55 and custom 56-79). A :class:`StoryFlow` speaks in chapter-page ids (``"05"``,
``"0407a"``, ``"final"``) and hides the numbering; the per-game extras ride along as optional
fields: PoR's "second part" (:attr:`StoryFlow.parts`) and RD's chapter armies
(:attr:`StoryFlow.armies`).

:func:`open_story_flow` opens the flow of a project's ``main.dol``.
"""

from __future__ import annotations

from typing import Optional

from . import chapter_flow, rd_story


class StoryFlow:
    """The story order of a project, in chapter-page ids. Every change is saved at once."""

    #: The id the story ends on.
    ending = ""
    #: Label of the ending when it has no chapter page (PoR's "32 · Ending"), else empty.
    ending_label = ""
    #: Whether chapters carry an army (RD); :meth:`army` and the rest are only used then.
    armies = False
    #: Whether the army can be changed (its runtime is verified in game).
    armies_editable = False
    #: Why the army can't be changed yet.
    armies_note = ""

    def __init__(self, editor):
        self.editor = editor

    # -- reading ------------------------------------------------------------------------------
    @property
    def available(self) -> bool:
        raise NotImplementedError

    @property
    def unavailable_reason(self) -> str:
        raise NotImplementedError

    def order(self) -> list[str]:
        """The chapters a new game plays, in order (PoR's ending, which has no page, left out)."""
        raise NotImplementedError

    def next_of(self, chapter: str) -> Optional[str]:
        """The chapter played after ``chapter`` (None: none, the story stops)."""
        raise NotImplementedError

    def predecessors(self, chapter: str) -> list[str]:
        raise NotImplementedError

    def knows(self, chapter: str) -> bool:
        """Whether ``chapter`` has a story number (a record the flow can point at)."""
        raise NotImplementedError

    def outside_reason(self, chapter: str) -> str:
        """Why ``chapter`` can't have a next chapter (empty when it can)."""
        raise NotImplementedError

    def can_follow(self, chapter: str) -> bool:
        """Whether ``chapter`` may be picked as another chapter's next chapter."""
        raise NotImplementedError

    def locked(self, chapter: str) -> bool:
        """Retail chapters keep their place in the story order (their successor can still change)."""
        raise NotImplementedError

    def removable(self, chapter: str) -> bool:
        """Whether **Take out of the story** applies (an added chapter in the story)."""
        return not self.locked(chapter) and chapter in self.order()

    def start(self) -> str:
        order = self.order()
        return order[0] if order else ""

    def label(self, chapter: str, titles: dict) -> str:
        from .. import chapters
        if chapter == self.ending and self.ending_label:
            return self.ending_label
        return f"{chapter} · {chapters.chapter_display_title(chapter, titles)}"

    def notes(self, chapter: str) -> list[str]:
        """Per-game remarks shown under the chapter's flow."""
        if not self.locked(chapter) and chapter not in self.order() and self.knows(chapter):
            return ["Not reached from the start of the story: pick it as the next chapter of a story chapter."]
        return []

    # -- writing ------------------------------------------------------------------------------
    def set_next(self, chapter: str, nxt: str) -> str:
        return self.set_many({chapter: nxt})

    def set_many(self, changes: dict[str, str]) -> str:
        raise NotImplementedError

    def remove(self, chapter: str) -> str:
        """Take ``chapter`` out of the story: whatever led to it goes to its successor instead."""
        raise NotImplementedError

    def insert_after(self, after: str, new: str) -> str:
        """``after`` leads to ``new``, which leads to where ``after`` used to go."""
        following = self.next_of(after)
        changes = {after: new}
        if following is not None:
            changes[new] = following
        return self.set_many(changes)

    def set_order(self, order: list[str]) -> str:
        """Make the story play ``order`` (every chapter, first to last)."""
        raise NotImplementedError

    # -- per-game extras ----------------------------------------------------------------------
    @property
    def parts(self):
        """PoR's :class:`~.chapter_parts.ChapterParts` ("the next chapter is this chapter's second
        part"), or None where the game has no such switch."""
        return None

    def army(self, chapter: str):
        return None

    def effective_army(self, chapter: str):
        return None

    def army_choices(self) -> list:
        return []

    def set_army(self, chapter: str, army) -> str:
        raise ValueError("This game has no chapter armies.")


class PorStoryFlow(StoryFlow):
    """Path of Radiance: :class:`.chapter_flow.ChapterFlow` (two-digit ids, 32 the ending)."""

    ending = f"{chapter_flow.GAME_CLEARED:02d}"
    ending_label = f"{chapter_flow.GAME_CLEARED} · Ending"

    def __init__(self, editor):
        super().__init__(editor)
        self.flow = chapter_flow.ChapterFlow(editor)

    @property
    def available(self) -> bool:
        return self.flow.available

    @property
    def unavailable_reason(self) -> str:
        return self.flow.unavailable_reason

    @staticmethod
    def _id(number: int) -> str:
        return f"{number:02d}"

    @staticmethod
    def _number(chapter: str) -> int:
        return int(chapter)

    def order(self) -> list[str]:
        return [self._id(n) for n in self.flow.order()]

    def next_of(self, chapter: str) -> Optional[str]:
        return self._id(self.flow.next_of(self._number(chapter)))

    def predecessors(self, chapter: str) -> list[str]:
        return [self._id(n) for n in self.flow.predecessors(self._number(chapter))]

    def knows(self, chapter: str) -> bool:
        return chapter.isdigit()

    def outside_reason(self, chapter: str) -> str:
        if not chapter.isdigit():
            return "This chapter has no story number."
        if not chapter_flow.can_have_successor(int(chapter)):
            return "Trial maps are played from the trial menu, not in the story."
        return ""

    def can_follow(self, chapter: str) -> bool:
        return chapter.isdigit() and chapter_flow.can_follow(int(chapter))

    def locked(self, chapter: str) -> bool:
        return not chapter.isdigit() or int(chapter) <= chapter_flow.LAST_RETAIL_STORY

    def notes(self, chapter: str) -> list[str]:
        notes = []
        number = self._number(chapter)
        if chapter_flow.CONTINUED_PART in (number, number - 1):
            notes.append("Chapters 28 and 29 are the two halves of Ch.27: the game skips the save menu and the "
                         "army cleanup between them, whatever the flow says.")
        return notes + super().notes(chapter)

    def set_many(self, changes: dict[str, str]) -> str:
        return self.flow.set_many({self._number(c): self._number(n) for c, n in changes.items()})

    def remove(self, chapter: str) -> str:
        return self.flow.remove(self._number(chapter))

    def set_order(self, order: list[str]) -> str:
        from .. import campaign
        return campaign.set_story_order(self.flow, [self._number(c) for c in order])

    @property
    def parts(self):
        from .chapter_parts import ChapterParts
        parts = ChapterParts(self.editor)
        return parts if parts.available else None


class RdStoryFlow(StoryFlow):
    """Radiant Dawn: :class:`.rd_story.StorySequence` (ChapterData ``C0101`` -> page ``0101``)."""

    ending = "final"
    armies = True
    armies_editable = rd_story.ARMY_RUNTIME_READY
    armies_note = ("Army switching is locked until force-slot persistence and moved division prompts pass "
                   "RFEE01 runtime validation.")

    def __init__(self, editor, chapter_ids: dict[int, str]):
        super().__init__(editor)
        self.story = rd_story.StorySequence(editor, chapter_ids)

    @property
    def available(self) -> bool:
        return self.story.available

    @property
    def unavailable_reason(self) -> str:
        return self.story.unavailable_reason

    @staticmethod
    def page_id(record_id: str) -> str:
        """``C0101`` -> ``0101``, ``C0407e`` -> ``0407e``, ``CFINAL`` -> ``final``."""
        return "final" if record_id == "CFINAL" else record_id[1:].lower()

    def register(self, number: int, chapter: str) -> None:
        """Make a chapter whose record was just added known to the flow."""
        self.story.chapter_ids[number] = rd_story.chapter_record_id(chapter)

    def _numbers(self) -> dict[str, int]:
        return {self.page_id(cid): number for number, cid in self.story.chapter_ids.items()}

    def number(self, chapter: str) -> Optional[int]:
        return self._numbers().get(chapter)

    def _id(self, number: Optional[int]) -> Optional[str]:
        if number is None:
            return None
        cid = self.story.chapter_ids.get(number)
        return self.page_id(cid) if cid else f"#{number}"

    def _require(self, chapter: str) -> int:
        number = self.number(chapter)
        if number is None:
            raise ValueError(f"Chapter {chapter} has no ChapterData story record.")
        return number

    def order(self) -> list[str]:
        return [self._id(n) for n in self.story.order()]

    def next_of(self, chapter: str) -> Optional[str]:
        number = self.number(chapter)
        return None if number is None else self._id(self.story.next_of(number))

    def predecessors(self, chapter: str) -> list[str]:
        number = self.number(chapter)
        return [] if number is None else [self._id(n) for n in self.story.predecessors(number)]

    def knows(self, chapter: str) -> bool:
        return self.number(chapter) is not None

    def outside_reason(self, chapter: str) -> str:
        number = self.number(chapter)
        if number is None:
            return "This chapter has no ChapterData story record."
        if number == rd_story.ENDING:
            return ""
        if not rd_story.is_story_number(number):
            return "This chapter's number is outside the story range (0-55 retail, 56-79 added)."
        return ""

    def can_follow(self, chapter: str) -> bool:
        number = self.number(chapter)
        return number is not None and number != 0 and rd_story.is_story_number(number)

    def locked(self, chapter: str) -> bool:
        number = self.number(chapter)
        return number is None or number < rd_story.CUSTOM_FIRST

    def set_many(self, changes: dict[str, str]) -> str:
        numbers = {self._require(c): self._require(n) for c, n in changes.items()}
        if rd_story.ENDING in numbers:
            raise ValueError("The final chapter ends the story: it has no next chapter.")
        self.story.set_successors(numbers)
        return ", ".join(f"after {c}: {n}" for c, n in sorted(changes.items()))

    def remove(self, chapter: str) -> str:
        number = self._require(chapter)
        if number < rd_story.CUSTOM_FIRST:
            raise ValueError(f"Chapter {chapter} is a retail chapter; change the chapter before it instead.")
        following = self.story.next_of(number)
        changes = {before: following for before in self.story.predecessors(number) if before != number}
        changes[number] = None
        self.story.set_successors(changes)
        return f"removed {chapter} from the story flow"

    def set_order(self, order: list[str]) -> str:
        if not order:
            raise ValueError("The story needs at least one chapter.")
        if len(set(order)) != len(order):
            raise ValueError("A chapter can only appear once in the story order.")
        if order[-1] != self.ending:
            raise ValueError("The final chapter must be the last chapter in the story order.")
        changes = {a: b for a, b in zip(order, order[1:]) if self.next_of(a) != b}
        return self.set_many(changes) if changes else "story order unchanged"

    def army(self, chapter: str):
        number = self.number(chapter)
        return None if number is None else self.story.configured_army(number)

    def effective_army(self, chapter: str):
        number = self.number(chapter)
        return None if number is None else self.story.effective_army(number)

    def army_choices(self) -> list:
        return list(rd_story.Army)

    def set_army(self, chapter: str, army) -> str:
        number = self._require(chapter)
        steps = [rd_story.ChapterStep(step.chapter, step.chapter_id, army)
                 if isinstance(step, rd_story.ChapterStep) and step.chapter == number else step
                 for step in self.story.steps()]
        return self.story.set_steps(steps)


def open_story_flow(project) -> tuple[Optional[StoryFlow], str]:
    """The project's story flow, or None and why it can't be edited."""
    from ..exceptions import ModdingError
    from ..game_profile import CHAPTER_FLOW, disc_root_of, profile_of
    from .editor import CodeEditor

    profile = profile_of(project)
    if not profile.supports(CHAPTER_FLOW):
        return None, profile.unavailable(CHAPTER_FLOW)
    try:
        editor = CodeEditor(disc_root_of(project), project.write_keeping_original)
        if profile.script_dialect == "fe10":
            flow = RdStoryFlow(editor, rd_story.chapter_number_map(project.read_logical("game_data")))
        else:
            flow = PorStoryFlow(editor)
    except (OSError, ModdingError, ValueError) as exc:
        return None, f"Could not open the story flow: {exc}"
    return (flow, "") if flow.available else (None, flow.unavailable_reason)
