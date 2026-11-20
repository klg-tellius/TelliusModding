"""Free the slots of chapter flags no event uses (Game Data › Flags › Chapter
flags › Free unused flags…).

Path of Radiance has one 96-slot flag table for the campaign flags and the
running chapter's flags together (``formats/event_flags.py``), so a project
that adds campaign flags - a hub adds 18 - can leave a busy chapter without
room for its own. Vanilla chapters register a few flags nothing reads (left
over from cut events and unused base conversations): removing those
registrations is the safe way to make room. Flags an event still uses are
never touched.
"""

from __future__ import annotations

from pathlib import Path

from . import chapters, script_sources
from .formats import event_flags as ef


def shared_script_text(project) -> str:
    """Every script that is not a chapter's (startup and shared files), as one
    text: a chapter flag named there is treated as used."""
    chapter_names = {path.name.lower() for path in (script_sources.chapter_script(project, cid)
                                                     for cid in chapters.list_chapter_ids(project)) if path}
    root = script_sources.startup_path(project).parent
    texts = []
    for path in sorted(root.glob("*.cmb")):
        if path.name.lower() not in chapter_names:
            try:
                texts.append(script_sources.peek(project, path))
            except Exception:  # noqa: BLE001 - an unreadable shared script only makes the scan stricter
                continue
    return "\n".join(texts)


def unused_chapter_flags(project) -> dict[str, tuple[Path, list[str]]]:
    """Chapter id -> (script, unused flag names), for chapters that have some."""
    from .formats.cmb.decompiler import quote

    shared = shared_script_text(project)
    out = {}
    for cid in chapters.list_chapter_ids(project):
        path = script_sources.chapter_script(project, cid)
        if path is None:
            continue
        names = [name for name in ef.unused_local_flags(script_sources.peek(project, path))
                 if quote(name) not in shared]
        if names:
            out[cid] = (path, names)
    return out


def free_unused_flags(project, chapter_ids=None) -> dict[str, list[str]]:
    """Remove the unused registrations (all chapters, or ``chapter_ids``),
    compiling each script; returns what was removed per chapter."""
    done = {}
    for cid, (path, names) in unused_chapter_flags(project).items():
        if chapter_ids is not None and cid not in chapter_ids:
            continue
        loaded = script_sources.load(project, path)
        script_sources.save(project, loaded, ef.remove_unused_local_flags(loaded.source, names))
        done[cid] = names
    return done
