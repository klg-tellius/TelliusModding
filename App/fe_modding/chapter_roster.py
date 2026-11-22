"""A chapter's **roster** on Path of Radiance: who plays it, where they start, who is
set aside, and who joins or leaves the army when it ends. The Chapters page's
**Roster** tab shows and edits it; nothing here needs Tk.

A roster is stored in the chapter's own files, so the Build and Script tabs show
the same data:

- the **team group**: the player section of ``dispos.cmp`` the chapter's script
  deploys first (``InstantDisposFirst("bmap05_mikata_c")``). Its records are the
  team and their tiles;
- the **mode** is the group's name. ``main.dol`` deploys a group whose name
  contains ``_mikata_`` from the player's army (the first units of the reserve,
  whoever is listed), any other name places the listed characters themselves
  (see :mod:`fe_modding.playthrough.setup`). An *army* roster keeps or restores
  ``_mikata_``; a *fixed* roster renames the group to ``_avatar_`` and updates
  the script's calls, so a save with a big army cannot put someone else on a
  team member's tile;
- **set aside every other unit** (fixed rosters): a block after the team's
  deployment that sends every other player unit on the map back to the reserve;
- **end of chapter**: a block at the start of the ``@on_complete`` function.
  Joining characters come from a ``<map>_roster_join_c`` group (``Join``);
  leaving characters go to force 7, where vanilla ``C05`` keeps Oscar and Boyd
  while they are away (a later deployment that names them brings them back).

The generated blocks sit between ``# >>> Roster tab`` and ``# <<< Roster tab``
comment lines; applying the roster again replaces them.

:func:`check_roster` plays the chapter's opening in the playthrough simulator up
to the first player phase, once with a new save (empty army) and once with a
save holding every character the project's chapters give the player, and
reports who is on the map, with warnings for the usual traps.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from . import chapters, script_sources
from .formats import dispo, fe8data, lz10, map_file, pak
from .formats.cmb import compile_source, read_cmb
from .game_profile import files_root_of, profile_of

ARMY, FIXED = "army", "fixed"
ARMY_MARK, FIXED_MARK = "_mikata_", "_avatar_"
BLOCK_START, BLOCK_END = "# >>> Roster tab", "# <<< Roster tab"
SET_ASIDE_TITLE = "set aside every unit outside the team"
END_TITLE = "army changes at the end of the chapter"
LEAVE_FORCE = 7
DEPLOY_CALL = re.compile(r"\b(\w*Dispos\w*)\(([^()\n]*)\)")
STRING = re.compile(r'"((?:[^"\\\n]|\\.)*)"')
F = dispo.FIELD


class RosterError(ValueError):
    """The chapter's files don't allow the roster asked for."""


@dataclass
class Member:
    pid: str
    x: int
    y: int


@dataclass
class ChapterRoster:
    chapter_id: str
    folder: str  # the map folder (first phase)
    groups: list  # the team's section names: one, or the _n/_h/_m trio of a SetMode call
    mode: str = ARMY
    members: list = field(default_factory=list)  # Member
    set_aside: bool = False
    joins: list = field(default_factory=list)  # PIDs
    leaves: list = field(default_factory=list)  # PIDs
    other_player_groups: list = field(default_factory=list)  # other player sections the script deploys

    @property
    def team(self) -> list:
        return [m.pid for m in self.members]

    def renamed_groups(self) -> dict:
        """old -> new section names the mode asks for."""
        out = {}
        for name in self.groups:
            new = (name.replace(ARMY_MARK, FIXED_MARK) if self.mode == FIXED
                   else name.replace(FIXED_MARK, ARMY_MARK))
            if new != name:
                out[name] = new
        return out

    @property
    def join_group(self) -> str:
        return f"{self.folder}_roster_join_c"


@dataclass
class RosterPlan:
    """What applying a roster writes: the new ``dispos.cmp`` and script source."""

    roster: ChapterRoster
    deployment_path: Path
    deployment: bytes
    script_path: Path
    source: str
    documents: list  # the new dispos documents, for check_roster


# -- reading ----------------------------------------------------------------------------------------


def is_supported(project) -> bool:
    """Path of Radiance only: Radiant Dawn's armies follow other rules (``rd_armies``)."""
    try:
        return profile_of(project).script_dialect == "fe9"
    except Exception:  # noqa: BLE001 - a project without a known game has no roster
        return False


def read_documents(data: bytes) -> tuple[list, dict]:
    """``(pack entries, {entry name: DispoDocument})`` of a ``dispos.cmp``."""
    packed = lz10.decompress(data)
    entries = pak.read_pak_entries(packed)
    documents = {entry.name: dispo.parse_dispo(pak.read_pak_file_content(packed, entry))
                 for entry in entries if entry.name.startswith("dispos_")}
    return entries, documents


def _sections(documents) -> dict:
    out = {}
    for document in documents:
        for section in document.sections:
            if not section.is_link:
                out.setdefault(section.name, section)
    return out


def is_player_section(section) -> bool:
    return bool(section.units) and all(int(u[F["faction"]] or 0) == 0 for u in section.units)


def deployed_groups(source: str, sections: dict) -> list:
    """Each Dispos-family call's groups, in source order: ``[(line, [names])]``. A
    ``...Rank("x")`` call names the ``x_n``/``x_h``/``x_m`` trio."""
    out = []
    for number, line in enumerate(source.splitlines(), 1):
        code = line.split("#", 1)[0]
        for match in DEPLOY_CALL.finditer(code):
            names = STRING.findall(match.group(2))
            if not names:
                continue
            if match.group(1).endswith("Rank"):
                names = [f"{names[0]}_{d}" for d in "nhm"]
            out.append((number, names))
    return out


def team_groups(source: str, sections: dict) -> tuple[list, int, list]:
    """``(team section names, line of their first deployment, other player groups)``."""
    found, other = None, []
    for line, names in deployed_groups(source, sections):
        existing = [n for n in names if n in sections]
        if not existing or not all(is_player_section(sections[n]) for n in existing):
            continue
        if found is None:
            found = (existing, line)
        elif sorted(existing) != sorted(found[0]):
            other.extend(n for n in existing if n not in other and n not in found[0])
    if found is None:
        return [], 0, other
    return found[0], found[1], other


def _block(source: str, title: str) -> Optional[tuple[int, int]]:
    """0-based (first, last) line indexes of a generated block, or None."""
    lines = source.splitlines()
    for i, line in enumerate(lines):
        if line.strip() == f"{BLOCK_START}: {title}":
            for j in range(i + 1, len(lines)):
                if lines[j].strip() == BLOCK_END:
                    return i, j
    return None


def _block_lines(source: str, title: str) -> list:
    span = _block(source, title)
    return source.splitlines()[span[0]:span[1] + 1] if span else []


def read_roster(project, chapter_id: str, *, source: Optional[str] = None) -> ChapterRoster:
    """The chapter's roster as its files have it (``source``: an unsaved script)."""
    paths = chapters.chapter_paths(project, chapter_id)
    if paths.deployment is None or paths.script is None:
        raise RosterError("This chapter has no deployment or no script.")
    folder = paths.deployment.parent.name
    _entries, documents = read_documents(paths.deployment.read_bytes())
    sections = _sections(documents.values())
    if source is None:
        source = script_sources.peek(project, paths.script)
    groups, _line, other = team_groups(source, sections)
    roster = ChapterRoster(chapter_id, folder, groups, other_player_groups=other)
    if not groups:
        return roster
    roster.mode = ARMY if any(ARMY_MARK in name for name in groups) else FIXED
    main = sections[groups[0]]
    roster.members = [Member(u[F["pid"]], int(u[F["pos_x"]]), int(u[F["pos_y"]]))
                      for u in main.units if isinstance(u[F["pid"]], str)]
    roster.set_aside = bool(_block(source, SET_ASIDE_TITLE))
    for line in _block_lines(source, END_TITLE):
        leave = re.search(r'UnitTransferToForceByPID\("([^"]+)",\s*(\d+)\)', line)
        if leave:
            roster.leaves.append(leave.group(1))
    if any(f'Join("{roster.join_group}")' in line for line in _block_lines(source, END_TITLE)):
        join = sections.get(roster.join_group)
        roster.joins = [u[F["pid"]] for u in join.units] if join is not None else []
    return roster


# -- planning ---------------------------------------------------------------------------------------


def _character_classes(project) -> dict:
    try:
        data = project.read_logical("game_data")
    except Exception:  # noqa: BLE001 - new records then take the character's class at run time
        return {}
    return {c.pid: c for c in fe8data.read_fe8data(data).characters if c.pid}


AI_FIELDS = ("seq_attack", "seq_move", "seq_heal", "mtype")


def _record(existing, pid: str, x: int, y: int, character, template=None) -> dispo.DispoUnitValues:
    """``existing`` (the character's own record) on a new tile, or a new record: the character's
    class and base level, the AI names of ``template`` (another record of the group)."""
    if existing is not None:
        record = dispo.DispoUnitValues(existing)
    else:
        record = dispo.new_unit_values()
        record[F["pid"]] = pid
        record[F["jid"]] = character.jid if character is not None and character.jid else 0
        record[F["level"]] = character.level if character is not None else 1
        if template is not None:
            for name in AI_FIELDS:
                record[F[name]] = template[F[name]]
    record[F["pos_x"]], record[F["pos_y"]] = x, y
    record[F["pos2_x"]], record[F["pos2_y"]] = x, y
    return record


def _set_units(section, members: list, characters: dict) -> None:
    by_pid = {u[F["pid"]]: u for u in section.units}
    template = section.units[0] if section.units else None
    section.units[:] = [_record(by_pid.get(m.pid), m.pid, m.x, m.y, characters.get(m.pid), template)
                        for m in members]


def _indent_of(line: str) -> str:
    return line[:len(line) - len(line.lstrip())]


def _remove_block(lines: list, title: str) -> list:
    span = _block("\n".join(lines), title)
    if span is None:
        return lines
    return lines[:span[0]] + lines[span[1] + 1:]


def set_aside_block(indent: str, team: list) -> list:
    """Every player unit on the map whose character isn't in ``team`` goes back to the reserve."""
    test = " or ".join(f'UnitQueryPID(roster_unit, "{pid}")' for pid in team) or "False"
    return [f"{indent}{BLOCK_START}: {SET_ASIDE_TITLE}",
            f"{indent}roster_unit = ForceGetFirst(0)",
            f"{indent}while roster_unit:",
            f"{indent}    roster_next = UnitGetNext(roster_unit)",
            f"{indent}    if not ({test}):",
            f"{indent}        UnitEscape(roster_unit, 0)",
            f"{indent}    roster_unit = roster_next",
            f"{indent}{BLOCK_END}"]


def end_block(indent: str, roster: ChapterRoster) -> list:
    lines = [f"{indent}{BLOCK_START}: {END_TITLE}"]
    if roster.joins:
        lines.append(f'{indent}Join("{roster.join_group}")')
    lines += [f'{indent}UnitTransferToForceByPID("{pid}", {LEAVE_FORCE})' for pid in roster.leaves]
    return lines + [f"{indent}{BLOCK_END}"]


def _complete_function(lines: list) -> Optional[int]:
    """The 0-based index of the first ``@on_complete`` function's ``def`` line."""
    for i, line in enumerate(lines):
        if line.strip().startswith("@on_complete"):
            for j in range(i + 1, len(lines)):
                if lines[j].lstrip().startswith("def "):
                    return j
    return None


def plan_source(source: str, roster: ChapterRoster, sections: dict) -> str:
    """``source`` with the roster's group names and generated blocks."""
    for old, new in roster.renamed_groups().items():
        source = source.replace(f'"{old}"', f'"{new}"')
    lines = source.splitlines()
    lines = _remove_block(lines, SET_ASIDE_TITLE)
    lines = _remove_block(lines, END_TITLE)
    new_names = [roster.renamed_groups().get(n, n) for n in roster.groups]
    renamed_sections = {roster.renamed_groups().get(n, n): s for n, s in sections.items()}
    _groups, line, _other = team_groups("\n".join(lines), renamed_sections)
    if roster.set_aside:
        if roster.mode != FIXED:
            raise RosterError("Only a fixed team can set every other unit aside.")
        if not line:
            raise RosterError(f"The script never deploys {new_names[0]}.")
        lines[line:line] = set_aside_block(_indent_of(lines[line - 1]), roster.team)
    if roster.joins or roster.leaves:
        index = _complete_function(lines)
        if index is None:
            raise RosterError("The script has no @on_complete function to change the army in.")
        body = next((lines[k] for k in range(index + 1, len(lines)) if lines[k].strip()), "    pass")
        lines[index + 1:index + 1] = end_block(_indent_of(body) or "    ", roster)
    return "\n".join(lines) + ("\n" if source.endswith("\n") else "")


def _join_section(document, roster: ChapterRoster, characters: dict) -> None:
    existing = next((s for s in document.sections if s.name == roster.join_group), None)
    if not roster.joins:
        if existing is not None:
            dispo.remove_section(document, roster.join_group)
        return
    if existing is None:
        existing = dispo.add_section(document, roster.join_group)
    by_pid = {u[F["pid"]]: u for u in existing.units}
    existing.units[:] = [_record(by_pid.get(pid), pid, 0, 0, characters.get(pid)) for pid in roster.joins]
    for unit in existing.units:
        unit[F["flags"]] = int(unit[F["flags"]] or 0) | dispo.FLAG_SPAWN_WHEN_ABSENT


def plan_roster(project, roster: ChapterRoster, *, source: Optional[str] = None) -> RosterPlan:
    """The files :func:`apply_roster` would write, checked but not written."""
    if not roster.groups:
        raise RosterError("The chapter's script deploys no player group: add one in the Build tab first.")
    if not roster.members:
        raise RosterError("The team is empty.")
    pids = [m.pid for m in roster.members]
    if len(set(pids)) != len(pids):
        raise RosterError("A character is listed twice in the team.")
    if len(roster.members) > dispo.MAX_SECTION_UNITS:
        raise RosterError(f"A group holds at most {dispo.MAX_SECTION_UNITS} units.")
    paths = chapters.chapter_paths(project, roster.chapter_id)
    entries, documents = read_documents(paths.deployment.read_bytes())
    characters = _character_classes(project)
    renames = roster.renamed_groups()
    all_sections = _sections(documents.values())
    for old, new in renames.items():
        if new in all_sections:
            raise RosterError(f"The deployment already has a group named {new}.")
    for name, document in documents.items():
        for section in document.sections:
            if section.name in roster.groups and not section.is_link:
                _set_units(section, roster.members, characters)
        for old, new in renames.items():
            if any(s.name == old for s in document.sections):
                dispo.rename_section_prefix(document, old, new)
        if name == "dispos_c.bin":
            _join_section(document, roster, characters)
    packed = lz10.decompress(paths.deployment.read_bytes())
    data = lz10.compress(pak.pack_pak(
        [(e.name, dispo.build_dispo(documents[e.name]) if e.name in documents else pak.read_pak_file_content(packed, e))
         for e in entries], [e.reserved for e in entries]))
    if source is None:
        source = script_sources.peek(project, paths.script)
    new_source = plan_source(source, roster, all_sections)
    compile_source(new_source, base=read_cmb(paths.script.read_bytes()),
                   known_script_functions=script_sources.CompileContext.for_project(project).helpers)
    return RosterPlan(roster, paths.deployment, data, paths.script, new_source, list(documents.values()))


def apply_roster(project, roster: ChapterRoster, *, source: Optional[str] = None) -> RosterPlan:
    """Write the roster: the deployment, then the script (compiled; its source kept)."""
    plan = plan_roster(project, roster, source=source)
    loaded = script_sources.load(project, plan.script_path)
    project.write_keeping_original(plan.deployment_path, plan.deployment)
    script_sources.save(project, loaded, plan.source)
    return plan


# -- checking ---------------------------------------------------------------------------------------


@dataclass
class Scenario:
    title: str
    army: list  # PIDs in the reserve before the chapter
    on_map: list = field(default_factory=list)  # (pid, x, y) of the player units at the first player phase
    log: list = field(default_factory=list)  # what the simulator said about deployments
    error: str = ""


@dataclass
class RosterReport:
    scenarios: list
    warnings: list


def army_candidates(project, before: Optional[str] = None) -> list:
    """Every character the project's chapters deploy for the player (player records of every
    chapter's deployment, in chapter order), up to chapter ``before`` excluded: a save that
    recruited everyone."""
    characters = _character_classes(project)
    order = profile_of(project).chapter_sort_key
    out = []
    for chapter_id in chapters.list_chapter_ids(project):
        if before is not None and order(chapter_id) >= order(before):
            break
        for folder in chapters.chapter_phases(project, chapter_id):
            deployment, _map = chapters.phase_paths(project, folder)
            if deployment is None:
                continue
            try:
                _entries, documents = read_documents(deployment.read_bytes())
            except Exception:  # noqa: BLE001 - an unreadable deployment adds nobody
                continue
            for section in _sections(documents.values()).values():
                for unit in section.units:
                    pid = unit[F["pid"]]
                    if (isinstance(pid, str) and int(unit[F["faction"]] or 0) == 0 and pid in characters
                            and pid not in out):
                        out.append(pid)
    return out


def chapter_world(project, chapter_id: str, *, documents=None, source: Optional[str] = None,
                  difficulty: str = "n"):
    """The playthrough world of the chapter's first map phase, with ``documents`` and
    ``source`` in place of the saved deployment and script when given."""
    from .playthrough import loader

    paths = chapters.chapter_paths(project, chapter_id)
    if paths.map is None:
        raise RosterError("This chapter has no map to play.")
    packed = lz10.decompress(paths.map.read_bytes())
    contents = {e.name: pak.read_pak_file_content(packed, e) for e in pak.read_pak_entries(packed)}
    if "map.bin" not in contents:
        raise RosterError("The chapter's map archive has no map.bin.")
    files = files_root_of(project)
    profile = profile_of(project)
    game_data = project.read_logical("game_data")
    if documents is None:
        documents = list(read_documents(paths.deployment.read_bytes())[1].values())
    script = None
    if paths.script is not None:
        base = read_cmb(paths.script.read_bytes())
        script = compile_source(source, base=base).script if source is not None else base
    terrain_types = fe8data.read_terrain_types(profile.path(files, "game_data").read_bytes())
    world = loader.load_world(files, map_data=map_file.read_map_bytes(contents["map.bin"]),
                              terrain_grid=map_file.terrain_grid(contents["map.bin"]),
                              terrain_types=terrain_types, documents=documents,
                              data=fe8data.read_fe8data(game_data), profile=profile, script=script,
                              difficulty=difficulty, chapter_stem=paths.script.stem if paths.script else None)
    return world


def play_to_first_turn(world, army: list, *, groups: Optional[set] = None) -> Scenario:
    """Run the opening to the first player phase (messages play on, choices take their default)."""
    from .playthrough import setup
    from .playthrough.simulation import INPUT, Simulation
    from .playthrough.state import PLAYER

    scenario = Scenario("", list(army))
    state = setup.initial_state(world, army=tuple(army))
    sim = Simulation(world, state)
    try:
        sim.run(INPUT)
    except Exception as exc:  # noqa: BLE001 - the report shows how far the opening got
        scenario.error = f"{type(exc).__name__}: {exc}"
    st = sim.state
    if st.over == "stopped" and not scenario.error:
        scenario.error = "The opening stopped on a script error (see the Playthrough window)."
    scenario.on_map = [(u.pid, u.x, u.y) for u in sorted(st.living(PLAYER), key=lambda u: u.uid)]
    for entry in sim.history:
        for step in entry.steps:
            for output in getattr(step, "outputs", []) or []:
                text = getattr(output, "text", "")
                if "slot" in text or (groups is None and ("Deployed" in text or "not found" in text)):
                    scenario.log.append(text)
                elif groups is not None and any(re.search(rf"\b{re.escape(g)}\b", text) for g in groups):
                    scenario.log.append(text)
    return scenario


def check_roster(project, chapter_id: str, plan: Optional[RosterPlan] = None, *,
                 difficulty: str = "n", army: Optional[list] = None) -> RosterReport:
    """Who is on the map at the first player phase, with a new save and with a full army,
    and what may go wrong. ``plan`` checks a roster before it is applied."""
    roster = plan.roster if plan is not None else read_roster(project, chapter_id)
    characters = _character_classes(project)
    warnings = []
    for member in roster.members:
        if member.pid not in characters:
            warnings.append(f"{member.pid} is not a character of the game data.")
    for pid in roster.joins + roster.leaves:
        if pid not in characters:
            warnings.append(f"{pid} (end of chapter) is not a character of the game data.")
    source = plan.source if plan is not None else None
    paths = chapters.chapter_paths(project, chapter_id)
    text = source if source is not None else script_sources.peek(project, paths.script)
    documents = plan.documents if plan is not None else list(read_documents(paths.deployment.read_bytes())[1].values())
    sections = _sections(documents)
    for _line, names in deployed_groups(text, sections):
        for name in names:
            if name in sections:
                continue
            swapped = name.replace(ARMY_MARK, FIXED_MARK) if ARMY_MARK in name else name.replace(FIXED_MARK, ARMY_MARK)
            if swapped in sections:
                warnings.append(f"The script deploys {name}, but the deployment calls that group {swapped}: "
                                "nobody is placed by that call.")
    if roster.mode == FIXED and any(ARMY_MARK in name for name in roster.groups) and plan is None:
        warnings.append("The team group's name contains _mikata_: the game fills it from the army, not with "
                        "the listed characters. Apply the roster to rename it.")
    army_groups = [name for name in roster.other_player_groups if ARMY_MARK in name]
    if army_groups:
        warnings.append(f"The script also deploys {', '.join(army_groups)} (army group"
                        f"{'s' if len(army_groups) > 1 else ''}): on the paths that use "
                        f"{'them' if len(army_groups) > 1 else 'it'}, the army fills the tiles.")
    if any(f.strip().startswith(("def Opening2", "def Opening1")) for f in text.splitlines()) \
            and "SallySetByGroup" in text:
        warnings.append("The chapter has a preparations screen: the player can still swap units there.")
    if army is None:
        army = army_candidates(project, before=chapter_id)
    scenarios = []
    for title, members in (("New save (empty army)", []), (f"Save with the whole army ({len(army)} characters)", army)):
        try:
            world = chapter_world(project, chapter_id, documents=documents, source=source, difficulty=difficulty)
            player_groups = {name for name, section in sections.items() if is_player_section(section)}
            player_groups |= {n for _l, names in deployed_groups(text, sections) for n in names
                              if ARMY_MARK in n or FIXED_MARK in n}
            scenario = play_to_first_turn(world, members, groups=player_groups)
        except Exception as exc:  # noqa: BLE001 - reported, not raised
            scenario = Scenario(title, list(members), error=f"{type(exc).__name__}: {exc}")
        scenario.title = title
        scenarios.append(scenario)
        placed = [pid for pid, _x, _y in scenario.on_map]
        if roster.mode == FIXED:
            missing = [m.pid for m in roster.members if m.pid not in placed]
            extra = [pid for pid in placed if pid not in roster.team]
            if missing:
                warnings.append(f"{title}: {', '.join(missing)} not on the map at the first player phase.")
            if extra:
                warnings.append(f"{title}: {', '.join(extra)} on the map but not in the team.")
        for pid, x, y in scenario.on_map:
            slot = next((m for m in roster.members if (m.x, m.y) == (x, y)), None)
            if roster.mode == ARMY and slot is not None and slot.pid != pid:
                scenario.log.append(f"{pid} stands on the slot listed for {slot.pid} (army rule).")
    return RosterReport(scenarios, warnings)
