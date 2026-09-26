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

``duplicate_chapter()`` adds a brand-new chapter number by copying an
existing one's full file set - since ``list_chapter_ids()``/``chapter_paths()``
above already discover chapters by an unbounded glob with no fixed range,
nothing here needs to change for a new chapter number to be picked up
automatically, by this module and by every chapter-scoped editor's own
independent glob. **This does not make the new chapter reachable by the
game.** Every real chapter script was searched for anything that says "load
chapter N+1" and nothing was found - no script, no table anywhere in disc
file data references what chapter comes after which (see GAME_NOTES.md's
Music section for the same kind of wall this project hit with the
background-music track lookup). That's almost certainly baked into
``main.dol`` (the executable), which this project has never disassembled.
A duplicated chapter's files exist, are fully browsable/editable through
every existing editor, and will decode/rebuild correctly into a disc image
- they just won't ever load through normal play.
"""

from __future__ import annotations

import re
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from .formats import dispo, lz10, pak
from .project import ModProject

_CHAPTER_FILE_RE = re.compile(r"^c(\d+)\.m$", re.IGNORECASE)


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
    mess_dir = project.extracted_dir / "files" / "Mess"
    if not mess_dir.is_dir():
        return []

    ids = []
    for path in mess_dir.glob("c*.m"):
        match = _CHAPTER_FILE_RE.match(path.name)
        if match:
            ids.append(match.group(1))
    return sorted(set(ids), key=int)


def chapter_paths(project: ModProject, chapter_id: str) -> ChapterPaths:
    """Resolve one chapter number to its dialogue/script/deployment/map
    paths - any of the four may be None if that file doesn't exist for this
    chapter (e.g. a tutorial-only or trial-map chapter)."""
    extracted = project.extracted_dir / "files"
    padded = chapter_id.zfill(2)

    dialogue = extracted / "Mess" / f"c{padded}.m"
    script = extracted / "Scripts" / f"C{padded}.cmb"
    deployment = extracted / "zmap" / f"bmap{padded}" / "dispos.cmp"
    map_bin = extracted / "zmap" / f"bmap{padded}" / "map.cmp"

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
    base = project.extracted_dir / "files" / "zmap" / folder
    deployment, map_cmp = base / "dispos.cmp", base / "map.cmp"
    return (deployment if deployment.exists() else None, map_cmp if map_cmp.exists() else None)


def chapter_of_map_folder(folder: str) -> Optional[str]:
    """``bmap06_2`` -> ``"06"``; None for folders that aren't chapter maps."""
    match = _PHASE_FOLDER_RE.match(folder)
    return match.group(1).zfill(2) if match else None


def chapter_titles(project: ModProject) -> dict[str, str]:
    """Chapter id -> the game's own title (``MCTnn`` in ``system.cmp``, e.g.
    ``"Prologue: Mercenaries"``). Empty when the text can't be read (Radiant
    Dawn keeps it elsewhere)."""
    from .formats import fe8data

    system_cmp = project.extracted_dir / "files" / "system.cmp"
    try:
        texts = fe8data.read_message_texts(system_cmp) if system_cmp.exists() else {}
    except Exception:  # noqa: BLE001 - titles are presentation only
        return {}
    titles = {}
    for key, text in texts.items():
        match = re.fullmatch(r"MCT(\d+)", key)
        if match and text.strip():
            titles[match.group(1).zfill(2)] = text.strip()
    return titles


def chapter_display_title(chapter_id: str, titles: dict[str, str]) -> str:
    """The game's title, else ``Chapter <id>`` (ids are disc numbers)."""
    return titles.get(chapter_id.zfill(2)) or f"Chapter {chapter_id}"


def duplicate_chapter(project: ModProject, source_id: str, new_id: str) -> ChapterPaths:
    """Copy an existing chapter's full file set (dialogue/script/deployment/
    map) to a new chapter number, as a starting template for a brand-new
    chapter - see the module docstring for the "not reachable by the game"
    caveat, which applies regardless of how this is used.

    Files are copied byte-for-byte except ``dispos.cmp``, whose section
    names embed the source chapter number as an ASCII substring (e.g.
    ``"bmap01_date_c"``, confirmed against a real file) - those get
    renumbered via dispo.rename_chapter_sections() so the deployment
    editor's section list reads correctly under the new chapter number.
    That only works for a same-length chapter number (real ones are always
    2 digits); if the new number has a different digit count, the rename is
    skipped and the section names are carried through unchanged rather than
    failing the whole duplicate over a cosmetic mismatch.

    Everything else - map.cmp's own bundled model filenames, the script's
    debug/achievement-flag strings, dialogue text - is left exactly as
    copied. None of that affects whether this app's own editors can open
    and edit the new chapter; it's cosmetic only (confirmed: map.bin's
    placed-object records reference the pak archive's own model filenames
    internally and consistently, and its section names are fixed format
    constants, not per-chapter strings - nothing there needs renaming).
    """
    if new_id in list_chapter_ids(project):
        raise ValueError(f"Chapter {new_id} already exists.")
    source = chapter_paths(project, source_id)
    if source.dialogue is None:
        raise ValueError(f"Chapter {source_id} has no dialogue file to use as a template.")

    new_padded = new_id.zfill(2)
    source_padded = source_id.zfill(2)
    extracted = project.extracted_dir / "files"

    new_dialogue = extracted / "Mess" / f"c{new_padded}.m"
    new_dialogue.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source.dialogue, new_dialogue)

    if source.script is not None:
        new_script = extracted / "Scripts" / f"C{new_padded}.cmb"
        new_script.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source.script, new_script)

    if source.map is not None:
        new_map = extracted / "zmap" / f"bmap{new_padded}" / "map.cmp"
        new_map.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source.map, new_map)

    if source.deployment is not None:
        new_deployment = extracted / "zmap" / f"bmap{new_padded}" / "dispos.cmp"
        new_deployment.parent.mkdir(parents=True, exist_ok=True)
        new_deployment.write_bytes(_renumber_dispos(source.deployment.read_bytes(), source_padded, new_padded))

    return chapter_paths(project, new_id)


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
