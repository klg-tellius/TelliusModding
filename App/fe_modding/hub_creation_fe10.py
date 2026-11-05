"""Create a Radiant Dawn hub chapter: an added chapter (``05NN``) whose units are the avatar alone.

The counterpart of :mod:`hub_creation`. The chapter is made by Add chapter
(:func:`chapters_fe10.add_story_chapter`, kept out of the story order) from a template, then:

- each difficulty's player army (``dispos_n.bin``, ``dispos_h.bin``) becomes the avatar alone on
  the start tile, and every other section of the deployment (the enemies, other armies and
  ``dispos_c.bin``'s cutscene units) is emptied;
- the script is replaced by a plain opening: the chapter title, the map, the player army, the
  avatar in focus. :mod:`hub_fe10` adds the hub's own events when the hub is installed.

The template's map is kept (Radiant Dawn has no blank-map maker yet).
"""

from __future__ import annotations

from . import chapters, chapters_fe10, script_sources
from .formats import dispo, fe10data
from .formats.cmb import compile_source, read_cmb, write_cmb
from .hub_fe10 import _deployments


def avatar_class(fe10: bytes, avatar_pid: str) -> str:
    record = next((r for r in fe10data.read_table(fe10, "character") if r.values.get("pid") == avatar_pid), None)
    if record is None or not record.values.get("jid"):
        raise ValueError(f"{avatar_pid} needs a character record with a class.")
    return record.values["jid"]


def player_start(project, chapter_id: str) -> tuple[int, int] | None:
    """The first player unit's tile in the chapter's deployment."""
    for path in _deployments(project, chapter_id):
        for section in dispo.parse_dispo(path.read_bytes()).sections:
            if "_mikata" in section.name and section.units:
                unit = section.units[0]
                return unit[dispo.FIELD["pos_x"]], unit[dispo.FIELD["pos_y"]]
    return None


def avatar_deployment(data: bytes, avatar_pid: str, avatar_jid: str, start: tuple[int, int]) -> tuple[bytes, bool]:
    """``data`` with the avatar alone in its player army and every other section emptied; whether
    it has a player army."""
    doc = dispo.parse_dispo(data)
    found = False
    for section in doc.sections:
        if section.is_link:
            continue
        if "_mikata" in section.name and section.units:
            unit = section.units[0]
            unit[dispo.FIELD["pid"]] = avatar_pid
            unit[dispo.FIELD["jid"]] = avatar_jid
            dispo.move_unit(unit, *start)
            del section.units[1:]
            found = True
        else:
            section.units.clear()
    return dispo.build_dispo(doc), found


def opening_source(chapter_id: str, avatar_pid: str) -> str:
    folder = f"bmap{chapter_id}"
    return (f"# Generated hub chapter {chapter_id}; Hub setup owns the destination events.\n\n"
            "@export\n"
            "def Startup():\n"
            "    pass\n\n"
            "@export\n"
            "def Opening0():\n"
            f'    ChapterTitle("C{chapter_id}")\n'
            "    BlackOut()\n"
            f'    MapLoad("{folder}")\n'
            f'    SallySetByGroupRank("{folder}_mikata")\n'
            f'    InstantDisposRank("{folder}_mikata")\n'
            f'    UnitForcedSallyByPID("{avatar_pid}")\n'
            f'    InstantUnitFocusOffsetByPID("{avatar_pid}", 0, 0)\n'
            "    FadeIn_Wait(500)\n")


def create_chapter(project, fe10: bytes, source_id: str, new_id: str, title: str, avatar_pid: str,
                   start: tuple[int, int] | None = None):
    """Add hub chapter ``new_id`` from ``source_id`` and return Add chapter's plan (its ``fe10data``
    is for the caller's session to save)."""
    if len(chapters.chapter_phases(project, source_id)) != 1:
        raise ValueError("Choose a chapter with one map as the template.")
    jid = avatar_class(fe10, avatar_pid)
    start = start or player_start(project, source_id)
    if start is None:
        raise ValueError(f"Chapter {source_id} has no player unit to put the avatar in place of.")
    plan = chapters_fe10.add_story_chapter(project, fe10, source_id, new_id, title)
    armies = 0
    for path in _deployments(project, new_id):
        data, found = avatar_deployment(path.read_bytes(), avatar_pid, jid, start)
        project.write_keeping_original(path, data)
        armies += found
    if not armies:
        raise ValueError(f"Chapter {source_id}'s deployment has no player army.")
    script = script_sources.chapter_script(project, new_id)
    if script is None:
        raise ValueError("The new chapter has no script.")
    source = opening_source(new_id, avatar_pid)
    project.write_keeping_original(script, write_cmb(compile_source(source, base=read_cmb(script.read_bytes())).script))
    sidecar = script_sources.sidecar_path(project, script)
    sidecar.parent.mkdir(parents=True, exist_ok=True)
    with open(sidecar, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(source)
    return plan
