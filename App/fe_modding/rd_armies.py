"""Radiant Dawn army switching: the story flow's chapter armies turned into the scripts that move units.

How the retail game does it (research/rd/CHAPTER_DATA_NOTES.md, "Army switching"): army switching
is scripted, not part of the engine. Force 5 holds the army being played (the deployment loader
``0x8010C200`` only places characters already in force 0 or 5), and forces 8, 9 and 10 store the
Micaiah, Ike and Tibarn armies. 4-P (``C0401``) splits the army with ``DivideForce`` and its
``TEAM_0401_OP``/``TEAM_0401_OP_00`` (8 -> 5). Each later Part 4 chapter ends by calling its
``startup.cmb`` function ``TEAM_<chapter>_ED``: the army just played goes back to its store and the
next chapter's army comes out (``TEAM_0402_ED``: 5 -> 9, 10 -> 5). The Endgame's ``TEAM_0407a_OP``
merges the three stores back into force 5. ChapterData +0x8F only names the army (its GroupData:
18 Silver, 19 Greil, 20 Hawk Army) for the units and the chapter's events, and +0xA4 names the
lord, who gets the army's leader mark (Micaiah, Ike, Tibarn).

:func:`plan` reads the flow and the scripts and works out, for every chapter that ends a division
chapter, the transfers its ``TEAM_*_ED`` function must make, and the +0x8F group and +0xA4 lord of
each division chapter. A function whose retail transfers already match is left as it is, so the retail flow
changes nothing. :func:`apply_scripts` writes the scripts through :mod:`script_sources` (the Script
tab's own path) and :func:`apply_records` patches FE10Data.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional

from . import chapters, script_sources
from .formats import fe10data
from .game_code.rd_story import Army
from .game_profile import files_root_of

#: The force that stores each division between its chapters.
STORE = {Army.DIVISION_1: 8, Army.DIVISION_2: 9, Army.DIVISION_3: 10}
#: The GroupData number each division plays under (ChapterData +0x8F).
GROUP = {Army.DIVISION_1: 18, Army.DIVISION_2: 19, Army.DIVISION_3: 20}
#: Each division's leader, the chapter's lord (ChapterData +0xA4), as in every retail Part 4 record.
LORD = {Army.DIVISION_1: "PID_MICAIAH", Army.DIVISION_2: "PID_IKE", Army.DIVISION_3: "PID_TIBARN"}
PLAYING = 5
MERGE = [(8, PLAYING), (9, PLAYING), (10, PLAYING)]
#: The chapter whose script splits the army (``DivideForce``) and brings its first division out in
#: ``TEAM_<id>_OP_00``.
DIVIDE_CHAPTER = "0401"

_TRANSFER = re.compile(r"^(\s*)UnitTransferToForceALL\((\d+),\s*(\d+)\)\s*$")


@dataclass
class ArmyPlan:
    #: startup.cmb function -> the transfers it must make, in order.
    functions: dict[str, list[tuple[int, int]]] = field(default_factory=dict)
    #: chapter page id -> (old call, new call) to rename in the chapter's script.
    renames: dict[str, tuple[str, str]] = field(default_factory=dict)
    #: ChapterData record id (``C0402``) -> fields to set (``unknown_8f`` group, ``lord``).
    records: dict[str, dict] = field(default_factory=dict)
    problems: list[str] = field(default_factory=list)

    @property
    def empty(self) -> bool:
        return not (self.functions or self.renames or self.records)


def _script_source(project, chapter: str) -> Optional[str]:
    paths = chapters.chapter_paths(project, chapter)
    path = paths.script
    return script_sources.peek(project, path) if path is not None and path.exists() else None


def _startup_path(project):
    return files_root_of(project) / "Scripts" / "startup.cmb"


def function_bodies(source: str) -> dict[str, list[str]]:
    """Each top-level function of ``source`` by name, as its lines (def line first)."""
    out: dict[str, list[str]] = {}
    current = None
    for line in source.split("\n"):
        match = re.match(r"def (\w+)\(", line)
        if match:
            current = match.group(1)
            out[current] = [line]
        elif current is not None:
            if line and not line[0].isspace():
                current = None
            else:
                out[current].append(line)
    return out


def transfers_of(lines: list[str]) -> list[tuple[int, int]]:
    return [(int(m.group(2)), int(m.group(3))) for m in (_TRANSFER.match(line) for line in lines) if m]


def _team_calls(source: Optional[str], suffix: str) -> list[str]:
    return sorted(set(re.findall(rf"\b(TEAM_\w+_{suffix})\(\)", source or "")))


def plan(project, flow, fe10: Optional[bytes] = None) -> ArmyPlan:
    """What the scripts and ChapterData need for ``flow``'s chapter armies."""
    result = ArmyPlan()
    order = flow.order()
    armies = {c: flow.effective_army(c) for c in order}
    startup = function_bodies(script_sources.peek(project, _startup_path(project)))
    divided = merged = False
    for i, chapter in enumerate(order):
        army = armies[chapter]
        if chapter == DIVIDE_CHAPTER:
            divided = True
        if army in STORE:
            if not divided:
                result.problems.append(f"{chapter} plays {army.label} before 4-P divides the army.")
                continue
            if merged:
                result.problems.append(f"{chapter} plays {army.label} after the armies were merged again: "
                                       "the divisions can't be split a second time.")
                continue
            result.records[f"C{chapter}" if chapter != "final" else "CFINAL"] = {
                "unknown_8f": GROUP[army], "lord": LORD[army]}
        elif divided and army == Army.MAIN and i and armies[order[i - 1]] in STORE:
            merged = True
        if chapter == DIVIDE_CHAPTER and army in STORE:
            # 4-P brings its first division out itself
            opening = f"TEAM_{chapter}_OP_00"
            want = [(STORE[army], PLAYING)]
            if opening in startup and transfers_of(startup[opening]) != want:
                result.functions[opening] = want
        if army not in STORE or merged:
            continue
        following = order[i + 1] if i + 1 < len(order) else None
        nxt = armies.get(following) if following else None
        if nxt == army:
            want = []
        elif nxt in STORE:
            want = [(PLAYING, STORE[army]), (STORE[nxt], PLAYING)]
        else:
            # back to the whole army: the Endgame merges in its own opening, any other chapter here
            want = [(PLAYING, STORE[army])]
            opening_merges = any(transfers_of(startup.get(name, [])) == MERGE
                                 for name in _team_calls(_script_source(project, following), "OP"))
            if not opening_merges:
                want += MERGE
        source = _script_source(project, chapter)
        calls = _team_calls(source, "ED")
        own = f"TEAM_{chapter}_ED"
        if not calls:
            if want:
                result.problems.append(f"{chapter}'s script calls no TEAM_…_ED function at its end, so its "
                                       f"army can't hand over to {following}'s.")
            continue
        if own not in calls:
            result.renames[chapter] = (calls[0], own)
        if own not in startup or transfers_of(startup[own]) != want or own not in calls:
            result.functions[own] = want
    if fe10 is not None:
        records = {r.values.get("cid"): r for r in fe10data.read_table(fe10, "chapter")}
        result.records = {cid: changes for cid, changes in (
            (cid, {k: v for k, v in fields.items() if records[cid].values.get(k) != v})
            for cid, fields in result.records.items() if cid in records) if changes}
    return result


def _with_transfers(lines: list[str], transfers: list[tuple[int, int]]) -> list[str]:
    """A function's lines with its UnitTransferToForceALL calls replaced by ``transfers``."""
    indent = next((m.group(1) for m in (_TRANSFER.match(line) for line in lines) if m), "    ")
    kept = [line for line in lines if not _TRANSFER.match(line)]
    head = 1
    while head < len(kept) and kept[head].strip().startswith("var "):
        head += 1
    new = [f"{indent}UnitTransferToForceALL({a}, {b})" for a, b in transfers]
    body = kept[:head] + new + kept[head:]
    if len(body) == 1 or all(not line.strip() for line in body[1:]):
        body.insert(1, f"{indent}pass")
    return body


def apply_scripts(project, result: ArmyPlan) -> list[str]:
    """Write the planned startup.cmb functions and chapter renames; the files written."""
    written = []
    if result.functions:
        path = _startup_path(project)
        loaded = script_sources.load(project, path)
        lines = loaded.source.split("\n")
        bodies = function_bodies(loaded.source)
        for name, transfers in result.functions.items():
            if name in bodies:
                start = next(i for i, line in enumerate(lines) if line.startswith(f"def {name}("))
                old = bodies[name]
                lines[start:start + len(old)] = _with_transfers(old, transfers)
            else:
                lines += ["", "", "# Army switching (Radiant Dawn story flow)", "@export", f"def {name}():"]
                lines += [f"    UnitTransferToForceALL({a}, {b})" for a, b in transfers] or ["    pass"]
        script_sources.save(project, loaded, "\n".join(lines))
        written.append(path.name)
    for chapter, (old, new) in result.renames.items():
        path = chapters.chapter_paths(project, chapter).script
        loaded = script_sources.load(project, path)
        script_sources.save(project, loaded, re.sub(rf"\b{re.escape(old)}\(\)", f"{new}()", loaded.source))
        written.append(path.name)
    return written


def apply_records(fe10: bytes, result: ArmyPlan) -> bytes:
    """FE10Data with the planned ChapterData group and lord changes."""
    records = {r.values.get("cid"): r.index for r in fe10data.read_table(fe10, "chapter")}
    for cid, changes in result.records.items():
        for key, value in changes.items():
            if cid in records:
                fe10 = fe10data.patch_field(fe10, "chapter", records[cid], key, value)
    return fe10
