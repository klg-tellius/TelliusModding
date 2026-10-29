"""Radiant Dawn's Add chapter: a playable chapter copied from another (the counterpart of
:func:`chapters.add_story_chapter`).

A new chapter takes a custom story number from 56 to 79 (:mod:`game_code.rd_story`: the hook routes
those through its successor table, and every ChapterData user but the retail advance finds a record
by number, so the record is appended after the tutorials) and the page id ``05NN`` (56 -> ``0501``),
so its files are named like retail ones of the same length:

- ``zmap/bmap05NN`` (``map.cmp`` with its models renamed after the new map,
  :func:`chapters.rename_map_pack`; ``dispos_{c,n,h}.bin`` with their ``bmap<template>`` section
  names renamed), ``Scripts/C05NN.cmb`` (its own ``bmap<template>`` strings renamed);
- ``Mess/c05NN.m``, ``e_c05NN.m``, ``n05NN.m``, ``e_n05NN.m`` copied (the script's message keys
  keep naming the template's, which the copies hold);
- a ``ChapterData`` record copied from the template's with the new number, ID and names, and a
  ``BattleTerrIndex`` row copied from the template map's;
- the template's ``SHOP_PERSON`` / armory / vendor / forge sections in each shop file;
- the ``MCT05NN`` title in ``Mess/e_common.m`` and ``common.m``, and the title card
  ``window/title/e_ch05NN.cms`` drawn from it.

:func:`remove_story_chapter` (Delete chapter) takes all of that back out. Only added chapters can be
deleted: the retail advance walks ChapterData by index, so removing a retail record would shift the
chapters after it; a retail chapter is taken out of the story with the story flow instead.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from . import chapters
from .formats import dispo, fe10data, message, shop
from .game_code import rd_story
from .game_files import files_of, game_path
from .game_profile import profile_of
from .project import ModProject

NUMBERS = range(rd_story.CUSTOM_FIRST, rd_story.CUSTOM_LAST + 1)
MESSAGE_FILES = ("c{id}.m", "e_c{id}.m", "n{id}.m", "e_n{id}.m")
TITLE_FILES = ("e_common.m", "common.m")


def chapter_id_for(number: int) -> str:
    """Page id of custom story number ``number``: 56 -> ``0501``."""
    if number not in NUMBERS:
        raise ValueError(f"Added Radiant Dawn chapters take a number from {NUMBERS.start} to {NUMBERS.stop - 1}.")
    return f"05{number - NUMBERS.start + 1:02d}"


def number_for(chapter_id: str) -> Optional[int]:
    """The custom story number of page id ``05NN``, or None for any other id."""
    if len(chapter_id) == 4 and chapter_id.isdigit() and chapter_id.startswith("05"):
        number = NUMBERS.start + int(chapter_id[2:]) - 1
        return number if number in NUMBERS else None
    return None


def _records(fe10: bytes) -> list:
    return fe10data.read_table(fe10, "chapter")


def templates(project: ModProject, fe10: bytes) -> list[str]:
    """Chapters a new one can copy: a four-digit id (the names are renamed in place), a record whose
    map, script and message names are the chapter's own, and its map, script and dialogue files."""
    profile = profile_of(project)
    by_id = {r.values.get("cid"): r for r in _records(fe10)}
    result = []
    for cid in chapters.list_chapter_ids(project):
        record = by_id.get(rd_story.chapter_record_id(cid))
        if not (len(cid) == 4 and cid.isdigit() and record is not None):
            continue
        values = record.values
        if (values.get("map"), values.get("script"), values.get("messages")) != (
                profile.map_folder(cid), f"C{cid}", f"C{cid}"):
            continue
        paths = chapters.chapter_paths(project, cid)
        if paths.map is not None and paths.script is not None and paths.dialogue is not None:
            result.append(cid)
    return result


def free_chapters(project: ModProject, fe10: bytes) -> list[str]:
    """Page ids a new chapter can take: a number no record uses and an id no file or map folder has."""
    used = {r.values.get("number") for r in _records(fe10)}
    ids = set(chapters.list_chapter_ids(project))
    folders = {name.lower() for name in files_of(project).listdir(game_path("zmap"))}
    profile = profile_of(project)
    return [chapter_id_for(n) for n in NUMBERS
            if n not in used and chapter_id_for(n) not in ids
            and profile.map_folder(chapter_id_for(n)).lower() not in folders]


@dataclass
class RdChapterPlan:
    """What :func:`add_story_chapter` writes; ``fe10data`` is left to the caller's session."""
    fe10data: bytes
    number: int
    chapter_id: str
    files: dict = field(default_factory=dict)       # path under files/ -> new bytes
    warnings: list = field(default_factory=list)


def _with_title(path, key: str, title: str) -> bytes:
    messages = message.read_messages_path(path)
    order = message.read_text_order_path(path)
    existing = next((i for i, m in enumerate(messages) if m.speaker == key), None)
    if existing is None:
        messages.append(message.Message(key, title))
    else:
        messages[existing] = message.Message(key, title)
    return message.write_messages(messages, order)


def plan_story_chapter(project: ModProject, fe10: bytes, source_id: str, new_id: str,
                       title: str = "") -> RdChapterPlan:
    """Every change for chapter ``new_id`` modelled on ``source_id``, without writing anything
    (``fe10`` is the current decompressed ``FE10Data.cms``, unsaved edits included)."""
    profile = profile_of(project)
    files = files_of(project)
    number = number_for(new_id)
    if number is None:
        raise ValueError(f"{new_id} is not an added-chapter id (0501-{chapter_id_for(NUMBERS.stop - 1)}).")
    if new_id not in free_chapters(project, fe10):
        raise ValueError(f"Chapter {new_id} (number {number}) is already used.")
    if source_id not in templates(project, fe10):
        raise ValueError(f"Chapter {source_id} can't be used as a template.")
    title = title.strip() or f"Chapter {new_id}"
    if not title.isascii():
        raise ValueError("Chapter titles are limited to plain ASCII text.")
    template = next(r for r in _records(fe10) if r.values.get("cid") == rd_story.chapter_record_id(source_id))
    old_map, new_map = profile.map_folder(source_id), profile.map_folder(new_id)
    warnings: list[str] = []

    data, index = fe10data.add_record(fe10, "chapter", template.index, rd_story.chapter_record_id(new_id))
    for key, value in (("number", number), ("title", f"MCT{new_id}"), ("map", new_map),
                       ("script", f"C{new_id}"), ("messages", f"C{new_id}")):
        data = fe10data.patch_field(data, "chapter", index, key, value)
    rows = fe10data.read_table(data, "battle_scenery")
    row = next((r for r in rows if r.values.get("map") == old_map), None)
    if row is not None:
        data, _row = fe10data.add_battle_scenery(data, row.index, new_map)
    else:
        warnings.append(f"{old_map} has no battle-scenery row to copy: battles use the game's default backdrop.")

    out: dict = {}
    for folder in chapters.chapter_phases(project, source_id):
        target = new_map + folder[len(old_map):]
        if files.exists(game_path("zmap", target)):
            raise ValueError(f"zmap/{target} already exists.")
        for rel in files.iter_files(game_path("zmap", folder)):
            inner = rel[len(game_path("zmap", folder)) + 1:]
            content = files.read(rel)
            if inner.lower().startswith("dispos_"):
                content = dispo.rename_chapter_sections(content, source_id, new_id)
            elif inner.lower() == "map.cmp":
                content = chapters.rename_map_pack(content, folder, target)
            out[game_path("zmap", target, inner)] = content
    script = chapters.chapter_paths(project, source_id).script
    out[game_path(profile.chapter_script.format(id=new_id))] = chapters._renumber_script(
        script.read_bytes(), source_id, new_id)
    for name in MESSAGE_FILES:
        path = files.find(game_path("Mess", name.format(id=source_id)))
        if path is not None and path.is_file():
            out[game_path("Mess", name.format(id=new_id))] = path.read_bytes()

    for difficulty in profile.shop_difficulties:
        rel = game_path(profile.shop_dir, profile.shop_file.format(diff=difficulty))
        path = files.find(rel)
        if path is None or not path.is_file():
            continue
        doc = shop.parse_shop(path.read_bytes())
        has_template = any(doc.shop(kind, source_id) for kind in shop.SHOP_KINDS)
        shop.add_chapter(doc, new_id, source_id if has_template else None)
        out[rel] = shop.build_shop(doc)

    key = f"MCT{new_id}"
    bucket = message.engine_name_hash(key, profile.name_hash_buckets)
    for name in TITLE_FILES:
        path = files.find(game_path("Mess", name))
        if path is None or not path.is_file():
            continue
        clash = next((m.speaker for m in message.read_messages_path(path)
                      if m.speaker != key and message.engine_name_hash(m.speaker, profile.name_hash_buckets) == bucket),
                     None)
        if clash is not None:
            warnings.append(f"{key} shares its lookup hash with {clash!r} in {name}: the game may show that text.")
        out[game_path("Mess", name)] = _with_title(path, key, title)
    if not any(game_path("Mess", name) in out for name in TITLE_FILES):
        warnings.append("No Mess/e_common.m or common.m: the chapter has no title text.")

    from . import chapter_images
    card = chapter_images.fe10_title_card(files, new_id, title, template_id=source_id)
    if card is None:
        warnings.append("The title card could not be drawn (no template card or no Fonts/talk.cms).")
    else:
        out[game_path(chapter_images.FE10_CARD_FOLDER, chapter_images.fe10_card_name(new_id))] = card[1]
    return RdChapterPlan(data, number, new_id, out, warnings)


def deletable(chapter_id: str) -> bool:
    """Whether Delete chapter can remove ``chapter_id``: an added chapter (``05NN``)."""
    return number_for(chapter_id) is not None


@dataclass
class RdRemovedChapter:
    """What :func:`remove_story_chapter` did; ``fe10data`` is left to the caller's session."""
    fe10data: bytes
    removed: list = field(default_factory=list)     # paths under files/ that were deleted
    files: dict = field(default_factory=dict)       # path under files/ -> new bytes (shops, titles)


def remove_story_chapter(project: ModProject, fe10: bytes, chapter_id: str, flow) -> RdRemovedChapter:
    """Delete added chapter ``chapter_id``: its ChapterData record and battle-scenery row, its shops,
    title text and title card, its dialogue, script and map folders. Chapters that led to it lead to
    its successor (``flow``, a :class:`game_code.story_flow.RdStoryFlow`). ``FE10Data.cms`` is not
    written: the result's ``fe10data`` is for the caller's session to save."""
    from . import chapter_images

    if not deletable(chapter_id):
        raise ValueError(f"Chapter {chapter_id} is a retail chapter: take it out of the story in the story "
                         "flow instead (removing its record would shift the chapters after it).")
    if flow is None or not flow.available:
        reason = flow.unavailable_reason if flow is not None else "it could not be opened."
        raise ValueError(f"main.dol cannot update the story flow: {reason}")
    profile = profile_of(project)
    files = files_of(project)
    record_id = rd_story.chapter_record_id(chapter_id)
    matching = [r for r in _records(fe10) if r.values.get("cid") == record_id]
    if len(matching) > 1:
        raise ValueError(f"FE10Data.cms has more than one ChapterData record {record_id}.")
    data = fe10data.remove_record(fe10, "chapter", matching[0].index) if matching else fe10
    map_name = profile.map_folder(chapter_id)
    rows = fe10data.read_table(data, "battle_scenery")
    for row in reversed([r for r in rows if r.values.get("map") == map_name]):
        data = fe10data.remove_battle_scenery(data, row.index)

    out: dict = {}
    for difficulty in profile.shop_difficulties:
        rel = game_path(profile.shop_dir, profile.shop_file.format(diff=difficulty))
        path = files.find(rel)
        if path is not None and path.is_file():
            doc = shop.parse_shop(path.read_bytes())
            if shop.remove_chapter(doc, chapter_id):
                out[rel] = shop.build_shop(doc)
    key = f"MCT{chapter_id}"
    for name in TITLE_FILES:
        path = files.find(game_path("Mess", name))
        if path is None or not path.is_file():
            continue
        messages = message.read_messages_path(path)
        kept = [m for m in messages if m.speaker != key]
        if len(kept) != len(messages):
            out[game_path("Mess", name)] = message.write_messages(kept, message.read_text_order_path(path))

    if chapter_id in flow.order() or flow.predecessors(chapter_id):
        flow.remove(chapter_id)
    for rel, content in out.items():
        files.write(rel, content)
    assets = [game_path("Mess", name.format(id=chapter_id)) for name in MESSAGE_FILES]
    assets += [game_path(profile.chapter_script.format(id=chapter_id)),
               game_path(chapter_images.FE10_CARD_FOLDER, chapter_images.fe10_card_name(chapter_id))]
    assets += [game_path("zmap", folder) for folder in chapters.chapter_phases(project, chapter_id)]
    removed = []
    for rel in assets:
        if files.exists(rel):
            removed.append(rel)
            files.remove(rel)
    return RdRemovedChapter(data, removed, out)


def add_story_chapter(project: ModProject, fe10: bytes, source_id: str, new_id: str, title: str = "",
                      after: Optional[str] = None, flow=None) -> RdChapterPlan:
    """Write :func:`plan_story_chapter`'s files and, when ``after`` is given, put the chapter after
    it in ``flow`` (a :class:`game_code.story_flow.RdStoryFlow`). ``FE10Data.cms`` is not written:
    the plan's ``fe10data`` is for the caller's session to save."""
    plan = plan_story_chapter(project, fe10, source_id, new_id, title)
    if after is not None and (flow is None or not flow.available):
        reason = flow.unavailable_reason if flow is not None else "it could not be opened."
        raise ValueError(f"main.dol cannot hold a story flow: {reason}")
    if after is not None and flow.outside_reason(after):
        raise ValueError(f"Chapter {after} cannot be followed by another chapter.")
    if after == getattr(flow, "ending", None):
        raise ValueError("The final chapter ends the story: pick a chapter before it.")
    files = files_of(project)
    for rel, content in plan.files.items():
        files.write(rel, content)
    if after is not None:
        flow.register(plan.number, new_id)
        flow.insert_after(after, new_id)
    return plan
