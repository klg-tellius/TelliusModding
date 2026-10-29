"""Start a campaign in one step: several new chapters in story order, and a starter cast.

The pieces already exist one at a time: :func:`chapters.add_story_chapter` adds a chapter copied
from a template and places it in the story flow, and ``fe8data.add_record`` adds a character.
This module chains them so a modder can describe a campaign ("five chapters after chapter 31,
modelled on these chapters, with these characters") and get all of it, checked first:

- :func:`check_campaign` lists every problem that would stop the build, before anything is written;
- :func:`add_campaign` adds the chapters in order (each leads to the next, the last leads where
  ``after`` used to) and then the characters, and returns the new ``FE8Data.bin`` bytes for the
  caller's session, like :func:`chapters.add_story_chapter`;
- :func:`blank_chapter_units` empties a new chapter's deployments but the player's army, for a
  chapter that should not keep the template's enemies and other units.

:func:`check_campaign_fe10` and :func:`add_campaign_fe10` do the same for Radiant Dawn: chapters
through :func:`chapters_fe10.add_story_chapter` (custom numbers 56-79, ids ``05NN``), characters as
``FE10Data.cms`` records whose name is an ``MPID_`` text in ``Mess/e_common.m`` and ``common.m``.
The pages reach both through their game's data adapter (``campaign_problems`` / ``add_campaign``).

Nothing here uses Tk.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

from . import chapters
from .formats import dispo, fe8data, lz10, message, pak
from .project import ModProject

_PID_RE = re.compile(r"^PID_[A-Z0-9_]+$")


@dataclass
class ChapterSpec:
    """One chapter to add: its title and the existing chapter it is copied from (``"05"``)."""
    title: str
    template: str
    blank_units: bool = False  # empty its deployments after copying


@dataclass
class CharacterSpec:
    """One character to add: a copy of the character ``template`` (a PID) under a new ``pid``.
    ``name`` becomes the in-game name (an ``MPID_`` text in ``common.m``); empty keeps the template's."""
    pid: str
    template: str
    name: str = ""
    jid: Optional[str] = None  # a different class


@dataclass
class CampaignResult:
    fe8data: bytes
    chapter_ids: list = field(default_factory=list)
    pids: list = field(default_factory=list)
    warnings: list = field(default_factory=list)


def mpid_for(pid: str) -> str:
    return "MPID_" + pid[len("PID_"):]


def check_campaign(project: ModProject, fe8: bytes, chapter_specs: list, character_specs: list = (),
                   after: Optional[int] = None) -> list:
    """Every reason :func:`add_campaign` would fail, as readable lines (empty: it can go ahead)."""
    problems = []
    records = fe8data.read_chapter_data(fe8)
    have = {f"{r.chapter_id:02d}" for r in records}
    free = chapters.free_chapter_ids(project, [r.chapter_id for r in records])
    if len(chapter_specs) > len(free):
        problems.append(f"{len(chapter_specs)} chapters asked for, but only {len(free)} chapter numbers are free.")
    if after is not None and after not in {r.chapter_id for r in records}:
        problems.append(f"Chapter {after:02d}, which the campaign should follow, has no ChapterData record.")
    for n, spec in enumerate(chapter_specs, 1):
        label = f"Chapter {n} ({spec.title or 'untitled'})"
        if spec.template.zfill(2) not in have:
            problems.append(f"{label}: the template chapter {spec.template} does not exist.")
        elif chapters.chapter_paths(project, spec.template).script is None:
            problems.append(f"{label}: the template chapter {spec.template} has no script to copy.")
        try:
            spec.title.encode("ascii")
        except UnicodeEncodeError:
            problems.append(f"{label}: titles are limited to plain ASCII text.")
    fe = fe8data.read_fe8data(fe8)
    pids = {c.pid for c in fe.characters}
    new_pids = set()
    for spec in character_specs:
        if not _PID_RE.match(spec.pid):
            problems.append(f"{spec.pid!r}: a character ID is PID_ followed by capital letters, digits or _.")
        elif spec.pid in pids or spec.pid in new_pids:
            problems.append(f"{spec.pid} already exists.")
        new_pids.add(spec.pid)
        if spec.template not in pids:
            problems.append(f"{spec.pid}: the template character {spec.template} does not exist.")
        if spec.jid is not None and spec.jid not in {k.jid for k in fe.classes}:
            problems.append(f"{spec.pid}: the class {spec.jid} does not exist.")
        if spec.name:
            try:
                spec.name.encode("ascii")
            except UnicodeEncodeError:
                problems.append(f"{spec.pid}: names are limited to plain ASCII text.")
    return problems


def add_campaign(project: ModProject, fe8: bytes, chapter_specs: list, character_specs: list = (),
                 after: Optional[int] = None, flow=None, *,
                 add_chapter: Callable = chapters.add_story_chapter) -> CampaignResult:
    """Add the chapters (in story order, after chapter ``after`` when given) and the characters.

    Raises ``ValueError`` listing the problems of :func:`check_campaign` before writing anything.
    A failure while adding chapters (disk, a template that turns out unusable) leaves the chapters
    added so far in place and says which in the error; ``FE8Data.bin`` is never written here."""
    problems = check_campaign(project, fe8, chapter_specs, character_specs, after)
    if problems:
        raise ValueError("The campaign cannot be added:\n  " + "\n  ".join(problems))
    result = CampaignResult(fe8)
    previous = after
    for spec in chapter_specs:
        records = fe8data.read_chapter_data(result.fe8data)
        new_id = chapters.free_chapter_ids(project, [r.chapter_id for r in records])[0]
        try:
            plan = add_chapter(project, result.fe8data, spec.template, new_id, spec.title, previous, flow)
            if spec.blank_units:
                blank_chapter_units(project, f"{new_id:02d}")
        except (ValueError, OSError) as exc:
            done = ", ".join(f"{c:02d}" for c in result.chapter_ids) or "none"
            raise ValueError(f"Chapter {new_id:02d} ({spec.title}) failed: {exc}\n"
                             f"Chapters added before it: {done}.") from exc
        result.fe8data = plan.fe8data
        result.warnings += plan.warnings
        result.chapter_ids.append(new_id)
        previous = new_id
    for spec in character_specs:
        result.fe8data = add_character(project, result.fe8data, spec, result.warnings)
        result.pids.append(spec.pid)
    return result


def add_character(project: ModProject, fe8: bytes, spec: CharacterSpec, warnings: Optional[list] = None) -> bytes:
    """Add one character as a copy of ``spec.template``. A ``name`` gets its own ``MPID_`` key and
    text in ``Mess/common.m`` (written at once); without one the copy shares the template's name."""
    warnings = warnings if warnings is not None else []
    source = next(c for c in fe8data.read_fe8data(fe8).characters if c.pid == spec.template)
    data, index = fe8data.add_record(fe8, "character", spec.pid, copy_from=source.index)
    if spec.jid:
        data = fe8data.patch_character_field(data, index, "jid", spec.jid)
    if spec.name.strip():
        key = mpid_for(spec.pid)
        data = fe8data.patch_character_field(data, index, "mpid", key)
        path = chapters._common_messages_path(project)
        if path is None:
            warnings.append(f"No Mess/common.m: {spec.pid} has no name text.")
        else:
            messages = message.read_messages_path(path)
            messages = [m for m in messages if m.speaker != key] + [message.Message(key, spec.name.strip())]
            project.write_keeping_original(path, message.write_messages(messages))
    return data


def set_story_order(flow, order: list) -> str:
    """Make the story play ``order`` (chapter ids, first to last) and then the ending: every link
    that differs is rewritten, the others are left alone. Chapters are 1-89; ``flow`` is a
    ``game_code.chapter_flow.ChapterFlow``."""
    if not order:
        raise ValueError("The story needs at least one chapter.")
    if len(set(order)) != len(order):
        raise ValueError("A chapter can only appear once in the story order.")
    for chapter in order:
        if not 1 <= chapter < chapters.NEW_CHAPTER_IDS.stop or chapter == 32:
            raise ValueError(f"Chapter {chapter} cannot be part of the story order (1-89).")
    if not flow.available:
        raise ValueError(f"Story flow: {getattr(flow, 'unavailable_reason', 'main.dol cannot be patched.')}")
    ending = 32
    targets = list(order[1:]) + [ending]
    changes = {a: b for a, b in zip(order, targets) if flow.next_of(a) != b}
    if changes:
        return flow.set_many(changes)
    return "story order unchanged"


#: Sections whose name holds this deploy the player's army (the game itself marks their units by
#: it: ``load_reinforcement_group_placement_list``); emptying them leaves the chapter without one.
PLAYER_SECTION_MARK = "mikata"


def blank_dispos_bytes(data: bytes) -> bytes:
    """One difficulty's deployment file with every unit removed except the player's army
    (:data:`PLAYER_SECTION_MARK` sections). Sections and their headers stay, so the script's
    deployment calls still find their sections."""
    doc = dispo.parse_dispo(data)
    for section in doc.sections:
        if not section.is_link and PLAYER_SECTION_MARK not in section.name:
            section.units.clear()
    return dispo.build_dispo(doc)


def blank_chapter_units(project: ModProject, chapter_id: str) -> list:
    """Empty every deployment of the chapter's map folders but the player's army. Returns the files
    changed."""
    changed = []
    if project.profile.wii:   # Radiant Dawn: loose zmap/<folder>/dispos_<diff>.bin files
        from .game_files import files_of, game_path
        files = files_of(project)
        for folder in chapters.chapter_phases(project, chapter_id):
            for rel in files.iter_files(game_path("zmap", folder)):
                if Path(rel).name.lower().startswith("dispos_"):
                    files.write(rel, blank_dispos_bytes(files.read(rel)))
                    changed.append(rel)
        return changed
    for folder in chapters.chapter_phases(project, chapter_id):
        path: Optional[Path] = chapters.phase_paths(project, folder)[0]
        if path is None:
            continue
        packed = lz10.decompress(path.read_bytes())
        entries = pak.read_pak_entries(packed)
        files, reserved = [], []
        for entry in entries:
            content = pak.read_pak_file_content(packed, entry)
            if entry.name.startswith("dispos_"):
                content = blank_dispos_bytes(content)
            files.append((entry.name, content))
            reserved.append(entry.reserved)
        project.write_keeping_original(path, lz10.compress(pak.pack_pak(files, reserved)))
        changed.append(f"zmap/{folder}/dispos.cmp")
    return changed


# -- Radiant Dawn ---------------------------------------------------------------------------------

def check_campaign_fe10(project: ModProject, fe10: bytes, chapter_specs: list, character_specs: list = (),
                        after: Optional[str] = None) -> list:
    """Every reason :func:`add_campaign_fe10` would fail (``fe10``: the decompressed ``FE10Data.cms``;
    chapter ids are page ids, ``"0204"``)."""
    from . import chapters_fe10
    from .formats import fe10data

    problems = []
    free = chapters_fe10.free_chapters(project, fe10)
    if len(chapter_specs) > len(free):
        problems.append(f"{len(chapter_specs)} chapters asked for, but only {len(free)} chapter numbers are free.")
    templates = chapters_fe10.templates(project, fe10)
    for n, spec in enumerate(chapter_specs, 1):
        label = f"Chapter {n} ({spec.title or 'untitled'})"
        if spec.template not in templates:
            problems.append(f"{label}: chapter {spec.template} can't be used as a template.")
        if not spec.title.isascii():
            problems.append(f"{label}: titles are limited to plain ASCII text.")
    db = fe10data.read_fe10data(fe10)
    pids = {r.id for r in db.characters}
    new_pids = set()
    for spec in character_specs:
        if not _PID_RE.match(spec.pid):
            problems.append(f"{spec.pid!r}: a character ID is PID_ followed by capital letters, digits or _.")
        elif spec.pid in pids or spec.pid in new_pids:
            problems.append(f"{spec.pid} already exists.")
        new_pids.add(spec.pid)
        if spec.template not in pids:
            problems.append(f"{spec.pid}: the template character {spec.template} does not exist.")
        if spec.jid is not None and spec.jid not in {r.id for r in db.classes}:
            problems.append(f"{spec.pid}: the class {spec.jid} does not exist.")
        if spec.name and not spec.name.isascii():
            problems.append(f"{spec.pid}: names are limited to plain ASCII text.")
    return problems


def add_campaign_fe10(project: ModProject, fe10: bytes, chapter_specs: list, character_specs: list = (),
                      after: Optional[str] = None, flow=None) -> CampaignResult:
    """:func:`add_campaign` for Radiant Dawn: the chapters in story order after ``after`` (a page id,
    or None: outside the story), then the characters. ``FE10Data.cms`` is returned, not written."""
    from . import chapters_fe10

    problems = check_campaign_fe10(project, fe10, chapter_specs, character_specs, after)
    if problems:
        raise ValueError("The campaign cannot be added:\n  " + "\n  ".join(problems))
    result = CampaignResult(fe10)
    previous = after
    for spec in chapter_specs:
        new_id = chapters_fe10.free_chapters(project, result.fe8data)[0]
        try:
            plan = chapters_fe10.add_story_chapter(project, result.fe8data, spec.template, new_id, spec.title,
                                                   previous, flow)
            if spec.blank_units:
                blank_chapter_units(project, new_id)
        except (ValueError, OSError) as exc:
            done = ", ".join(result.chapter_ids) or "none"
            raise ValueError(f"Chapter {new_id} ({spec.title}) failed: {exc}\n"
                             f"Chapters added before it: {done}.") from exc
        result.fe8data = plan.fe10data
        result.warnings += plan.warnings
        result.chapter_ids.append(new_id)
        previous = new_id
    for spec in character_specs:
        result.fe8data = add_character_fe10(project, result.fe8data, spec, result.warnings)
        result.pids.append(spec.pid)
    return result


def add_character_fe10(project: ModProject, fe10: bytes, spec: CharacterSpec, warnings: Optional[list] = None) -> bytes:
    """One Radiant Dawn character copied from ``spec.template``; a ``name`` gets its own ``MPID_``
    text in ``Mess/e_common.m`` and ``common.m`` (written at once)."""
    from .chapters_fe10 import TITLE_FILES
    from .formats import fe10data
    from .game_files import files_of, game_path

    warnings = warnings if warnings is not None else []
    source = next(r for r in fe10data.read_fe10data(fe10).characters if r.id == spec.template)
    data, index = fe10data.add_record(fe10, "character", source.index, spec.pid)
    if spec.jid:
        data = fe10data.patch_field(data, "character", index, "jid", spec.jid)
    if spec.name.strip():
        key = mpid_for(spec.pid)
        data = fe10data.patch_field(data, "character", index, "mpid", key)
        files, wrote = files_of(project), False
        for name in TITLE_FILES:
            path = files.find(game_path("Mess", name))
            if path is None or not path.is_file():
                continue
            messages = [m for m in message.read_messages_path(path) if m.speaker != key]
            messages.append(message.Message(key, spec.name.strip()))
            files.write(game_path("Mess", name), message.write_messages(messages, message.read_text_order_path(path)))
            wrote = True
        if not wrote:
            warnings.append(f"No Mess/e_common.m or common.m: {spec.pid} has no name text.")
    return data

