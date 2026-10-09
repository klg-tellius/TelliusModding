"""Canonical chapter identity across the four per-chapter file formats.

Each chapter-scoped editor (dialogue, deployment, script, map) used to derive
its own chapter list independently, from a different naming convention:
``Mess/c01.m``, ``zmap/bmap01/dispos.cmp``, ``Scripts/C01.cmb``,
``zmap/bmap01/map.cmp``. Picking "chapter 1" meant doing that four separate
times, in four different pickers, across four separate windows. This module
is the single place that maps a chapter number to all four paths, so the
workspace's chapter page (see ``fe_modding/gui/pages/chapters.py``) can drive
every chapter-scoped editor from one selection. Paths below are relative to
``extracted/files/`` - one level below ``ModProject.extracted_dir`` itself,
matching the actual disc-extraction layout.

The dialogue file (``Mess/cNN.m``) is treated as the authoritative source of
"what chapters exist" - it's the one format that's reliably one file per
story chapter, with no sub-phase variants. Some chapters have more than one
battle map (``zmap/bmap06``, ``zmap/bmap06_2``, ...) for a mid-chapter phase
change; ``chapter_paths()`` resolves the primary (unsuffixed) folder, and
``chapter_phases()``/``phase_paths()`` list and resolve every phase (the
chapter page's Phase selector). Chapter titles come from the game's own
text (``chapter_titles()``, ``MCTnn``).

``duplicate_chapter()`` copies an existing chapter's file set (dialogue,
script, every map folder) under a new number, renaming the ``bmapNN``
names its deployments and script use. ``add_story_chapter()`` builds a
playable chapter on top of that: a ``ChapterData`` record naming the new
files, a battle-scene row, base shops, a title (``MCTnn``) and its place in
the story flow (``game_code.chapter_flow``: the next-chapter table patched
into ``main.dol``). Chapter numbers are the ``ChapterData`` ids the game
loads by; 0-31 are the retail story, 32 plays the ending, 51/52/58 and
80-82 are other records and 90 up are trial maps, so new story chapters
take the free ids of :data:`NEW_CHAPTER_IDS`.
"""

from __future__ import annotations

import re
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from .formats import dispo, lz10, pak
from .game_profile import GAME_DATA, files_dir_of, logical_path_of, profile_of
from .project import ModProject

def _chapter_file_re(project: ModProject):
    return re.compile(rf"^c({profile_of(project).chapter_id_pattern})\.m$", re.IGNORECASE)


@dataclass(frozen=True)
class ChapterPaths:
    chapter_id: str  # zero-padded number, e.g. "01"
    dialogue: Optional[Path]
    script: Optional[Path]
    deployment: Optional[Path]
    map: Optional[Path]


def list_chapter_ids(project: ModProject) -> list[str]:
    """Every chapter number that has a ``Mess/cNN.m`` dialogue file, sorted
    numerically. This is the list the Chapters page shows."""
    mess_dir = files_dir_of(project) / "Mess"
    if not mess_dir.is_dir():
        return []

    pattern = _chapter_file_re(project)
    ids = []
    for path in mess_dir.glob("c*.m"):
        match = pattern.match(path.name)
        if match:
            ids.append(match.group(1))
    return sorted(set(ids), key=profile_of(project).chapter_sort_key)


def _first_deployment_difficulty(project: ModProject, folder: str) -> str:
    """The difficulty letter of the first deployment file the map folder has (only Radiant Dawn
    keeps one file per difficulty); empty on Path of Radiance, where ``dispos.cmp`` holds them all."""
    profile = profile_of(project)
    if "{diff}" not in profile.deployment:
        return ""
    for diff in profile.deployment_difficulties:
        if profile.deployment_path(files_dir_of(project), folder, diff).exists():
            return diff
    return profile.deployment_difficulties[0]


def chapter_paths(project: ModProject, chapter_id: str) -> ChapterPaths:
    """Resolve one chapter number to its dialogue/script/deployment/map
    paths - any of the four may be None if that file doesn't exist for this
    chapter (e.g. a tutorial-only or trial-map chapter)."""
    profile = profile_of(project)
    extracted = files_dir_of(project)
    folder = profile.map_folder(chapter_id)

    dialogue = profile.mess_path(extracted, chapter_id)
    script = profile.script_path(extracted, chapter_id)
    deployment = profile.deployment_path(extracted, folder, _first_deployment_difficulty(project, folder))
    map_bin = extracted / "zmap" / folder / "map.cmp"

    return ChapterPaths(
        chapter_id=chapter_id,
        dialogue=dialogue if dialogue.exists() else None,
        script=script if script.exists() else None,
        deployment=deployment if deployment.exists() else None,
        map=map_bin if map_bin.exists() else None,
    )


_PHASE_FOLDER_RE = re.compile(r"^bmap(\d+)(?:_(\d+))?$", re.IGNORECASE)


def chapter_phases(project: ModProject, chapter_id: str) -> list[str]:
    """The chapter's map folders in play order: ``bmapNN`` first, then
    ``bmapNN_2``, ``bmapNN_3``... (a mid-chapter map change)."""
    zmap = project.extracted_dir / "files" / "zmap"
    if not zmap.is_dir():
        return []
    phases = []
    for folder in zmap.iterdir():
        match = _PHASE_FOLDER_RE.match(folder.name)
        if folder.is_dir() and match and int(match.group(1)) == int(chapter_id):
            phases.append((int(match.group(2) or 1), folder.name))
    return [name for _n, name in sorted(phases)]


def phase_paths(project: ModProject, folder: str) -> tuple[Optional[Path], Optional[Path]]:
    """``(dispos.cmp, map.cmp)`` of one map folder, None where missing."""
    base = files_dir_of(project) / "zmap" / folder
    deployment = profile_of(project).deployment_path(files_dir_of(project), folder, _first_deployment_difficulty(project, folder))
    map_cmp = base / "map.cmp"
    return (deployment if deployment.exists() else None, map_cmp if map_cmp.exists() else None)


def chapter_of_map_folder(folder: str) -> Optional[str]:
    """``bmap06_2`` -> ``"06"``; None for folders that aren't chapter maps."""
    match = _PHASE_FOLDER_RE.match(folder)
    return match.group(1).zfill(2) if match else None


def chapter_titles(project: ModProject) -> dict[str, str]:
    """Chapter id -> the game's own title (``MCTnn`` in ``mess/common.m``, e.g.
    ``"Prologue: Mercenaries"``). The loose ``Mess/common.m`` is read when it
    exists (it holds titles added since the last build; the build copies it
    into ``system.cmp``), else the copy in ``system.cmp``. Empty when the text
    can't be read (Radiant Dawn keeps it elsewhere)."""
    from .formats import fe8data

    if profile_of(project).message_dialect == "fe10":
        return _fe10_chapter_titles(project)
    try:
        loose = _common_messages_path(project)
        if loose is not None:
            texts = {key: m.text for key, m in _common_messages(loose).items()}
        else:
            system_cmp = logical_path_of(project, "system_archive") if profile_of(project).has_file("system_archive") else None
            texts = fe8data.read_message_texts(system_cmp) if system_cmp is not None and system_cmp.exists() else {}
    except Exception:  # noqa: BLE001 - titles are presentation only
        return {}
    titles = {}
    for key, text in texts.items():
        match = re.fullmatch(r"MCT(\d+)", key)
        if match and text.strip():
            titles[match.group(1).zfill(2)] = text.strip()
    # A chapter can point at a newly created key that is not named MCTnn.
    # Prefer the key selected in its ChapterData record when available.
    try:
        for record in fe8data.read_chapter_data(project.read_logical("game_data")):
            title = texts.get(record.title_key or "", "").strip()
            if title:
                titles[f"{record.chapter_id:02d}"] = title
    except Exception:  # noqa: BLE001 - titles are presentation only
        pass
    return titles


def _fe10_chapter_titles(project: ModProject) -> dict[str, str]:
    """Radiant Dawn: chapter id (``0102``, ``0407a``, ``final``) -> the title of its ``ChapterData``
    record (``MCT0102`` in ``Mess/e_common.m``, else the Japanese ``common.m``), e.g.
    ``"I:1-Maiden of Miracles"``."""
    from .formats import fe10_message, fe10data, message

    try:
        records = fe10data.read_fe10data(project.read_logical("game_data")).table("chapter")
        mess = project.extracted_dir / "files" / "Mess"
        path = next((p for p in (mess / "e_common.m", mess / "common.m") if p.is_file()), None)
        texts = {}
        if path is not None:
            for msg in message.read_messages_path(path):
                texts[msg.speaker.encode("cp437").decode("cp932", errors="replace")] = fe10_message.plain_text(msg.text)
    except Exception:  # noqa: BLE001 - titles are presentation only
        return {}
    titles = {}
    for record in records:
        cid, key = record.values.get("cid") or "", record.values.get("title")
        if cid[:1] in "Cc" and key and texts.get(key):
            titles[cid[1:].lower() if not cid[1:].isdigit() else cid[1:]] = texts[key]
    return titles


def _common_messages_path(project: ModProject) -> Optional[Path]:
    path = logical_path_of(project, "common_mess")
    return path if path.is_file() else None


def _common_messages(path: Path) -> dict:
    """``common.m``'s messages by key (keys re-decoded from the reader's cp437 as Shift-JIS)."""
    from .formats import message

    result = {}
    for m in message.read_messages_path(path):
        try:
            key = m.speaker.encode(message.ENCODING).decode("shift_jis")
        except (UnicodeEncodeError, UnicodeDecodeError):
            key = m.speaker
        result.setdefault(key, m)
    return result


def chapter_display_title(chapter_id: str, titles: dict[str, str]) -> str:
    """The game's title, else ``Chapter <id>`` (ids are disc numbers)."""
    return titles.get(chapter_id.zfill(2)) or f"Chapter {chapter_id}"


#: Free numbers for new story chapters: above 32 (the ending) and below the trial maps (90+).
#: Numbers a ``ChapterData`` record already uses (51, 52, 58, 80-82 in retail) are skipped.
NEW_CHAPTER_IDS = range(33, 90)


def free_chapter_ids(project: ModProject, used_record_ids=()) -> list[int]:
    """Numbers a new story chapter can take: in :data:`NEW_CHAPTER_IDS`, used by no
    ``ChapterData`` record and by no chapter file or map folder."""
    taken = {int(c) for c in list_chapter_ids(project)} | set(used_record_ids)
    zmap = project.extracted_dir / "files" / "zmap"
    if zmap.is_dir():
        taken |= {int(m.group(1)) for f in zmap.iterdir() if (m := _PHASE_FOLDER_RE.match(f.name))}
    return [n for n in NEW_CHAPTER_IDS if n not in taken]


def _phase_target(folder: str, source_padded: str, new_padded: str) -> str:
    """``bmap09_2`` -> ``bmap33_2``."""
    return "bmap" + new_padded + folder[len("bmap") + len(source_padded):]


def duplicate_chapter(project: ModProject, source_id: str, new_id: str) -> ChapterPaths:
    """Copy an existing chapter's file set - dialogue, script and every map
    folder (``bmapNN``, ``bmapNN_2``...) - to a new chapter number.

    The deployments' section names and the script's ``bmapNN`` strings
    (``MapLoad("bmap01")``, ``DisposFirst("bmap01_mikata_c")``) embed the
    chapter number; both are renamed to the new one, so the copy loads its
    own maps and deploys its own units. Names of *other* chapters' maps (a
    script that loads a neighbouring chapter's map) are left alone. The
    rename needs a same-length number (real ones are 2 digits); with a
    different digit count the names are carried through unchanged.

    Dialogue text, ``map.cmp`` (its bundled model names are internal and
    consistent) and the script's message keys are copied as they are.
    This only copies files: :func:`add_story_chapter` also makes the game
    load and reach the chapter.
    """
    existing = list_chapter_ids(project)
    if new_id in existing or new_id.zfill(2) in existing:
        raise ValueError(f"Chapter {new_id} already exists.")
    source = chapter_paths(project, source_id)
    if source.dialogue is None:
        raise ValueError(f"Chapter {source_id} has no dialogue file to use as a template.")

    new_padded = new_id.zfill(2)
    source_padded = source_id.zfill(2)
    extracted = project.extracted_dir / "files"
    zmap = extracted / "zmap"
    phases = chapter_phases(project, source_id)
    for folder in phases:
        target = zmap / _phase_target(folder, source_padded, new_padded)
        if target.exists():
            raise ValueError(f"zmap/{target.name} already exists.")

    new_dialogue = extracted / "Mess" / f"c{new_padded}.m"
    new_dialogue.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source.dialogue, new_dialogue)

    if source.script is not None:
        new_script = extracted / "Scripts" / f"C{new_padded}.cmb"
        new_script.parent.mkdir(parents=True, exist_ok=True)
        new_script.write_bytes(_renumber_script(source.script.read_bytes(), source_padded, new_padded))

    for folder in phases:
        target = zmap / _phase_target(folder, source_padded, new_padded)
        target.mkdir(parents=True)
        for item in (zmap / folder).iterdir():
            if item.is_dir():
                shutil.copytree(item, target / item.name)
            elif item.name.lower() == "dispos.cmp":
                (target / item.name).write_bytes(_renumber_dispos(item.read_bytes(), source_padded, new_padded))
            else:
                shutil.copyfile(item, target / item.name)

    return chapter_paths(project, new_padded)


def _renumber_script(data: bytes, source_padded: str, new_padded: str) -> bytes:
    """The script with its own ``bmap<source>`` / ``bmap<source>_...`` pool strings renamed.
    A same-length rename keeps every string offset, so the code is untouched."""
    if len(source_padded) != len(new_padded):
        return data
    import struct

    pool_start, table_start = struct.unpack_from("<II", data, 0x24)
    old, new = f"bmap{source_padded}".encode("ascii"), f"bmap{new_padded}".encode("ascii")
    entries = [new + e[len(old):] if e == old or e.startswith(old + b"_") else e
               for e in data[pool_start:table_start].split(b"\x00")]
    return data[:pool_start] + b"\x00".join(entries) + data[table_start:]


def _renumber_dispos(compressed: bytes, source_padded: str, new_padded: str) -> bytes:
    if len(source_padded) != len(new_padded):
        # can't rename in place - carry the section names through unchanged
        # rather than fail the whole duplicate over a cosmetic mismatch
        return compressed

    decompressed = lz10.decompress(compressed)
    entries = pak.read_pak_entries(decompressed)
    files = []
    reserved = []
    for entry in entries:
        content = pak.read_pak_file_content(decompressed, entry)
        if entry.name.startswith("dispos_"):
            content = dispo.rename_chapter_sections(content, source_padded, new_padded)
        files.append((entry.name, content))
        reserved.append(entry.reserved)

    new_pak_bytes = pak.pack_pak(files, reserved)
    return lz10.compress(new_pak_bytes)


# -- playable chapters -----------------------------------------------------------------------------


@dataclass
class NewChapterPlan:
    """What :func:`add_story_chapter` changes besides the copied files."""
    fe8data: bytes                          # FE8Data.bin with the record and battle-scene row added
    record_index: int
    shops: dict                             # shop file path -> new bytes
    common: Optional[tuple]                 # (Mess/common.m path, new bytes) with the title
    warnings: list
    images: dict = None                     # chapter-name picture path -> bytes (chapter_images)


def plan_story_chapter(project: ModProject, fe8: bytes, source_id: str, new_id: int,
                       title: str = "") -> NewChapterPlan:
    """Every data change for a new chapter ``new_id`` modelled on ``source_id``, without
    writing anything (``fe8`` is the current ``FE8Data.bin``, unsaved edits included):

    - a ``ChapterData`` record copied from the template's, with the new id and the new
      ``bmapNN`` / ``CNN`` / ``MCTNN`` names (objectives, music, backgrounds stay the template's);
    - a ``BattleTerrData`` row for the new map, copied from the template map's;
    - the three shop sections in each difficulty's shop file, copied from the template's;
    - the ``MCTNN`` title in ``Mess/common.m``;
    - the chapter's name pictures (``window/chapter2/chapNN.cms`` in the file menu's save slots,
      ``window/chapter/chapNN.cms`` at the chapter start), drawn from the title."""
    from .formats import fe8data, message, shop

    if new_id not in NEW_CHAPTER_IDS:
        raise ValueError(f"New chapters take a number from {NEW_CHAPTER_IDS.start} to {NEW_CHAPTER_IDS.stop - 1}.")
    records = fe8data.read_chapter_data(fe8)
    if any(r.chapter_id == new_id for r in records):
        raise ValueError(f"A ChapterData record already uses the number {new_id}.")
    if f"{new_id:02d}" in list_chapter_ids(project):
        raise ValueError(f"Chapter {new_id:02d} already has files.")
    source_number = int(source_id)
    template = next((r for r in records if r.chapter_id == source_number), None)
    if template is None:
        raise ValueError(f"Chapter {source_id} has no ChapterData record to copy.")
    padded = f"{new_id:02d}"
    warnings: list[str] = []

    data, index = fe8data.add_record(fe8, "chapter", copy_from=template.index)
    data = fe8data.patch_chapter_field(data, index, "chapter_id", new_id)
    data = fe8data.patch_chapter_field(data, index, "map_name", f"bmap{padded}")
    data = fe8data.patch_chapter_field(data, index, "script", f"C{padded}")
    if template.message is not None:
        data = fe8data.patch_chapter_field(data, index, "message", f"C{padded}")
    data = fe8data.patch_chapter_field(data, index, "title_key", f"MCT{padded}")

    rows = fe8data.read_battle_terrain(data)
    row = next((r for r in rows if r.map_name == template.map_name), None)
    if row is not None and not any(r.map_name == f"bmap{padded}" for r in rows):
        data = fe8data.write_battle_terrain(data, rows + [fe8data.BattleTerrainRow(f"bmap{padded}", list(row.scenes))])

    shops: dict[Path, bytes] = {}
    folder = project.extracted_dir / "files" / "shop"
    for name in shop.DIFFICULTY_FILES.values():
        path = folder / name
        if not path.is_file():
            continue
        doc = shop.parse_shop(path.read_bytes())
        if any(doc.shop(kind, new_id) for kind in shop.SHOP_KINDS):
            continue
        has_template = any(doc.shop(kind, source_number) for kind in shop.SHOP_KINDS)
        shop.add_chapter(doc, new_id, source_number if has_template else None)
        shops[path] = shop.build_shop(doc)

    common = None
    common_path = _common_messages_path(project)
    title = title.strip() or f"Chapter {new_id}"
    if common_path is None:
        warnings.append("No Mess/common.m: the chapter has no title text.")
    else:
        try:
            title.encode("ascii")
        except UnicodeEncodeError:
            raise ValueError("Chapter titles are limited to plain ASCII text.") from None
        messages = message.read_messages_path(common_path)
        key = f"MCT{padded}"
        key_hash = message.engine_name_hash(key)
        clash = next((m.speaker for m in messages
                      if m.speaker != key and message.engine_name_hash(m.speaker) == key_hash), None)
        if clash is not None:
            warnings.append(f"{key} shares its lookup hash with {clash!r}: the game may show that text instead.")
        existing = next((i for i, m in enumerate(messages) if m.speaker == key), None)
        if existing is None:
            messages.append(message.Message(key, title))
        else:
            messages[existing] = message.Message(key, title)
        common = (common_path, message.write_messages(messages))

    from . import chapter_images

    images = chapter_images.chapter_name_images(project.extracted_dir / "files", new_id, title, source_number)
    if len(images) < 2:
        warnings.append("The chapter-name pictures could not be drawn (no template picture or no "
                        "Fonts/bigkana.gcf): the file menu shows an empty box for this chapter.")
    return NewChapterPlan(data, index, shops, common, warnings, images)


def add_story_chapter(project: ModProject, fe8: bytes, source_id: str, new_id: int, title: str = "",
                      after: Optional[int] = None, flow=None) -> NewChapterPlan:
    """Add a playable chapter ``new_id``: copy ``source_id``'s files (:func:`duplicate_chapter`),
    write the shop and title changes of :func:`plan_story_chapter`, and - when ``after`` is
    given - insert it in the story flow (``flow``, a ``game_code.chapter_flow.ChapterFlow``):
    ``after`` then leads to the new chapter, which leads to where ``after`` used to go.

    ``FE8Data.bin`` is not written: the plan's ``fe8data`` is returned for the caller to put in
    its shared session and save. Nothing is written when planning fails."""
    plan = plan_story_chapter(project, fe8, source_id, new_id, title)
    changes = None
    if after is not None:
        from .game_code import chapter_flow

        if flow is None or not flow.available:
            reason = flow.unavailable_reason if flow is not None else "it could not be opened."
            raise ValueError(f"main.dol cannot hold a story flow: {reason}")
        if not chapter_flow.can_have_successor(after):
            raise ValueError(f"Chapter {after} cannot be followed by another chapter.")
        changes = {after: new_id, new_id: flow.next_of(after)}
    duplicate_chapter(project, source_id, f"{new_id:02d}")
    for path, data in {**plan.shops, **(plan.images or {})}.items():
        project.write_keeping_original(path, data)
    if plan.common is not None:
        project.write_keeping_original(*plan.common)
    if changes is not None:
        flow.set_many(changes)
    return plan


def ensure_name_images(project: ModProject) -> list[Path]:
    """Draw the missing name pictures of every added chapter (an id from 33 up with a
    ``ChapterData`` record), from its ``MCTnn`` title on chapter 1's pictures. The story-flow
    patch lists chapters 33-89 in the file menu's picture table, so a save slot of an added
    chapter asks for its picture. Returns the files written."""
    from . import chapter_images
    from .formats import fe8data

    files = project.extracted_dir / "files"
    if not profile_of(project).supports(GAME_DATA):
        return []
    fe8 = logical_path_of(project, "game_data")
    if not fe8.is_file():
        return []
    try:
        records = fe8data.read_chapter_data(fe8.read_bytes())
    except Exception:  # noqa: BLE001 - an unreadable table is reported by its own editor
        return []
    titles = chapter_titles(project)
    written = []
    for record in records:
        chapter = record.chapter_id
        if chapter not in NEW_CHAPTER_IDS:
            continue
        wanted = (files / chapter_images.STRIP_FOLDER / chapter_images.strip_name(chapter),
                  files / chapter_images.CARD_FOLDER / chapter_images.card_name(chapter))
        if all(path.is_file() for path in wanted):
            continue
        title = chapter_display_title(f"{chapter:02d}", titles)
        for path, data in chapter_images.chapter_name_images(files, chapter, title, 1).items():
            if not path.is_file():
                project.write_keeping_original(path, data)
                written.append(path)
    return written
