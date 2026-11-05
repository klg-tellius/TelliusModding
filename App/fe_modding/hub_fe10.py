"""Set up an added Radiant Dawn chapter as a campaign hub (the counterpart of :mod:`hub`).

The modder prepares the hub: an added chapter (``05NN``, story number 56-79, from Add chapter)
whose player army is one dedicated avatar, taken out of the story order. Installing writes:

- the hub flags, appended to ``startup.cmb``'s ``RegistGlobalFlags`` (after RD's 27 globals:
  ``HUB_ACTIVE``, ``HUB_STARTED``, padding to a whole byte, then the destination and pending
  chapter bytes), so a save keeps them;
- the hub script's events (:func:`hub_script`): on turn 1 the avatar is placed by the destination
  it came back from; arriving on a destination's tile sets the destination byte and wins the map;
  on the win the avatar leaves the player army (force 1, the enemy army, which no chapter carries
  over: forces 0, 5 and 7-10 are the player's);
- the activation chapter's win event, which turns the hub on once;
- the router (:mod:`game_code.rd_hub`) with the hub's number and the flag bytes.

- an Arrive marker on each action tile: the retail ``tttu01`` object (到達, the one 1-2's Arrive tile
  carries), copied from a chapter map that has it;
- each destination's description, if any: a Visit event on its tile that shows ``MS_HUB_NN_INFO``
  from the hub's message file in the in-map dialog box (``<R:ダイアログ会話>``, as 1-2's help line).

Destinations are ChapterData story numbers. Not done on Radiant Dawn: removing the hub visit from
the clear history.
"""

from __future__ import annotations

import json
import re
from dataclasses import asdict
from pathlib import Path

from . import chapters, chapters_fe10, script_sources
from .formats import dispo, event_flags as ef, fe10_message, fe10data, lz10, map_file, message, pak
from .formats.cmb import compile_source, read_cmb, write_cmb
from .formats.cmb.parser import parse
from .game_code import rd_hub, rd_story
from .game_code.editor import CodeEditor
from .game_profile import disc_root_of, files_root_of, profile_of
from .hub import (ACTIVE, DEST, END_MARK, PENDING, START_MARK, STARTED, Destination, HubSetup,
                  _remove_generated, _replace_generated, activation_script, config_path, description_key,
                  draft_path, flag_names, saved_setup, setup_from)

RELEASE_FORCE = 1
MARKER = "tttu01"          # the retail Arrive marker object
DESCRIPTION_LAYOUT = "ダイアログ会話"
LINE_WIDTH = 30            # characters per line of the dialog box (retail help lines are 28-30)
MAX_LINES = 4
TEST_MAP = 0      # C0000, the developers' test map: not a story chapter


def _flag_assignments(chapter: int) -> list[str]:
    return [f'    {"set" if chapter & (1 << i) else "clr"}("{name}")' for i, name in enumerate(DEST)]


def _destination_expression(chapter: int) -> str:
    return " and ".join(f'get("{name}") == {(chapter >> i) & 1}' for i, name in enumerate(DEST))


def hub_script(source: str, setup: HubSetup) -> str:
    """Replace only the app-owned event block of the hub's script."""
    body = [START_MARK,
            'def HubPositionAvatar():',
            f'    unit = UnitGetByPID("{setup.avatar_pid}")',
            '    if unit:']
    for dest in setup.destinations:
        body += [f'        if {_destination_expression(dest.chapter)}:',
                 f'            UnitSetPos(unit, {dest.return_x}, {dest.return_y})']
    body += ['        MapUpdate()',
             '', '@on_phase(turn_from=1, turn_to=1, phase="player")',
             'def HubPlaceAvatar():', '    HubPositionAvatar()',
             '', '@on_complete(flag="gf_complete")', 'def HubReleaseAvatar():',
             f'    unit = UnitGetByPID("{setup.avatar_pid}")',
             '    if unit:', f'        UnitTransferToForce(unit, {RELEASE_FORCE})']
    for dest in setup.destinations:
        body += ['', f'@on_location(x={dest.x}, y={dest.y}, action="arrive", name=None)',
                 f'def HubGoTo{dest.chapter}():', *_flag_assignments(dest.chapter),
                 '    set("gf_complete")']
        if dest.description.strip():
            body += ['', f'@on_location(x={dest.x}, y={dest.y}, action="visit", name=None)',
                     f'def HubDescribe{dest.chapter}():',
                     f'    TalkEvent("{description_key(dest.chapter)}")']
    body += [END_MARK]
    return _replace_generated(source, "\n".join(body))


def description_lines(text: str) -> list[str]:
    """``text`` wrapped for the dialog box; ValueError when it doesn't fit or can't be shown."""
    text = " ".join(text.split())
    if any(c in text for c in "<>#@$"):
        raise ValueError("A description cannot hold < > # @ or $.")
    try:
        text.encode(fe10_message.ENCODING)
    except UnicodeEncodeError as exc:
        raise ValueError("The description has a character the game cannot show.") from exc
    lines, line = [], ""
    for word in text.split(" "):
        candidate = f"{line} {word}".strip()
        if len(candidate) <= LINE_WIDTH:
            line = candidate
            continue
        if line:
            lines.append(line)
        line = word
        if len(line) > LINE_WIDTH:
            raise ValueError(f"A word of the description is longer than {LINE_WIDTH} characters.")
    if line:
        lines.append(line)
    if len(lines) > MAX_LINES:
        raise ValueError(f"A description is at most {MAX_LINES} lines of {LINE_WIDTH} characters.")
    return lines


def description_raw(text: str) -> str:
    """The message text of a destination's description."""
    return fe10_message.to_raw(f"<R:{DESCRIPTION_LAYOUT}><sd>" + "\n".join(description_lines(text)) + "<wait>")


def _without_markers(files: dict[str, bytes]) -> bool:
    """Remove every ``tttu01`` placement from ``files["map.bin"]``; whether there was one."""
    data = map_file.read_map_bytes(files["map.bin"])
    index = next((i for i, obj in enumerate(data.build_desc) if obj.filename == MARKER), None)
    if index is None:
        return False
    records = map_file.instance_records(files["map.bin"])
    kept = [r for r, inst in zip(records, data.build_inst) if inst.desc_index != index]
    files["map.bin"] = map_file.set_build_instances(files["map.bin"], kept)
    return len(kept) != len(records)


def _pack_map(entries, files) -> bytes:
    return lz10.compress(pak.pack_pak([(e.name, files[e.name]) for e in entries], [e.reserved for e in entries]))


def entrance_markers(project, map_path: Path, setup: HubSetup) -> bytes:
    """The hub's ``map.cmp`` with one Arrive marker per action tile (and none elsewhere)."""
    from . import map_props
    entries, files = map_props.read_map_container(map_path)
    data = map_file.read_map_bytes(files["map.bin"])
    if not any(obj.filename == MARKER for obj in data.build_desc):
        donors = sorted((files_root_of(project) / "zmap").glob("*/map.cmp"))
        preferred = files_root_of(project) / "zmap/bmap0103/map.cmp"
        if preferred in donors:
            donors.remove(preferred)
            donors.insert(0, preferred)
        for donor in donors:
            if donor == map_path:
                continue
            _, source = map_props.read_map_container(donor)
            if any(o.filename == MARKER for o in map_file.read_map_bytes(source["map.bin"]).build_desc) \
                    and f"{MARKER}.gs" in source:
                map_props.copy_prop(source, MARKER, entries, files)
                break
        else:
            raise ValueError(f"Hub markers need the Arrive marker ({MARKER}) from an extracted chapter map.")
    _without_markers(files)
    for dest in setup.destinations:
        map_props.place_prop(files, MARKER, dest.x, dest.y)
    return _pack_map(entries, files)


def _description_messages(path: Path, setup: HubSetup, buckets: int) -> bytes:
    kept = [m for m in message.read_messages_path(path) if not re.fullmatch(r"MS_HUB_\d{2}_INFO", m.speaker)]
    for dest in setup.destinations:
        if not dest.description.strip():
            continue
        key = description_key(dest.chapter)
        clash = next((m.speaker for m in kept
                      if message.engine_name_hash(m.speaker, buckets) == message.engine_name_hash(key, buckets)), None)
        if clash:
            raise ValueError(f"The message ID for destination {dest.chapter} collides with {clash}.")
        kept.append(message.Message(key, description_raw(dest.description)))
    return message.write_messages(kept, message.read_text_order_path(path))


def _fe10(project) -> bytes:
    return project.read_logical("game_data")


def _deployments(project, chapter_id: str) -> list[Path]:
    """Every difficulty's deployment file of the chapter's map folders."""
    profile = profile_of(project)
    root = files_root_of(project)
    out = []
    for folder in chapters.chapter_phases(project, chapter_id):
        for diff in profile.deployment_difficulties:
            path = root / "zmap" / folder / profile.deployment.format(diff=diff)
            if path.is_file():
                out.append(path)
    return out


def _pids(path: Path) -> tuple[set[str], set[str]]:
    doc = dispo.parse_dispo(path.read_bytes())
    pids, player = set(), set()
    for section in doc.sections:
        if section.is_link:
            continue
        names = {u[dispo.FIELD["pid"]] for u in section.units if u[dispo.FIELD["pid"]]}
        pids |= names
        if "_mikata" in section.name:
            player |= names
    return pids, player


def _positioned(path: Path, pid: str, x: int, y: int) -> bytes:
    doc = dispo.parse_dispo(path.read_bytes())
    found = False
    for section in doc.sections:
        for unit in section.units:
            if unit[dispo.FIELD["pid"]] == pid:
                dispo.move_unit(unit, x, y)
                found = True
    if not found:
        raise ValueError(f"{path.name} has no {pid} unit to position.")
    return dispo.build_dispo(doc)


def _story(project, fe10: bytes):
    editor = CodeEditor(disc_root_of(project), project.write_keeping_original)
    return editor, rd_story.StorySequence(editor, rd_story.chapter_number_map(fe10))


def _page_id(number: int, ids: dict[int, str]) -> str | None:
    cid = ids.get(number)
    return None if cid is None else ("final" if cid == "CFINAL" else cid[1:])


def _validate(project, setup: HubSetup, current: dict | None, fe10: bytes, story) -> dict[int, str]:
    """Raise ValueError for a setup that can't be installed; return number -> page id."""
    if profile_of(project).script_dialect != "fe10":
        raise ValueError("This is the Radiant Dawn hub setup.")
    numbers = {n: _page_id(n, story.chapter_ids) for n in story.chapter_ids}
    hub_id = chapters_fe10.number_for(numbers.get(setup.chapter) or "")
    if hub_id is None or setup.chapter not in numbers:
        raise ValueError("The hub must be an added chapter (05NN, numbers 56-79) with a ChapterData record.")
    if setup.activation_chapter not in numbers or setup.activation_chapter in (setup.chapter, rd_story.ENDING):
        raise ValueError("The activation chapter must be another story chapter, before the ending.")
    if not story.available:
        raise ValueError(f"Story flow is unavailable: {story.unavailable_reason}")
    if current is None and story.predecessors(setup.chapter):
        raise ValueError("Take the hub chapter out of the story order before setting it up.")
    if current and current["chapter"] != setup.chapter:
        raise ValueError("Change the hub chapter by removing its setup first.")
    if not setup.avatar_pid.startswith("PID_") or '"' in setup.avatar_pid:
        raise ValueError("Choose a valid dedicated PID_ avatar.")
    if setup.avatar_pid not in {r.values.get("pid") for r in fe10data.read_table(fe10, "character")}:
        raise ValueError(f"Character {setup.avatar_pid} has no character record.")
    if not setup.destinations:
        raise ValueError("The hub needs at least one destination tile.")
    if (setup.start_x is None) != (setup.start_y is None):
        raise ValueError("Give both avatar start coordinates.")
    hub_page = numbers[setup.chapter]
    for page in (hub_page, numbers[setup.activation_chapter]):
        if script_sources.chapter_script(project, page) is None:
            raise ValueError(f"Chapter {page} has no script.")
    seen_chapters, tiles = set(), set()
    for dest in setup.destinations:
        if dest.chapter not in numbers or dest.chapter in (setup.chapter, rd_story.ENDING) \
                or not rd_story.is_story_number(dest.chapter):
            raise ValueError(f"Destination {dest.chapter} is not a playable story chapter.")
        paths = chapters.chapter_paths(project, numbers[dest.chapter])
        if paths.script is None or paths.map is None or paths.deployment is None:
            raise ValueError(f"Destination {numbers[dest.chapter]} is missing its script, map or deployment.")
        if dest.chapter in seen_chapters or (dest.x, dest.y) in tiles:
            raise ValueError("Destination chapters and their tiles must each be unique.")
        seen_chapters.add(dest.chapter)
        tiles.add((dest.x, dest.y))
        if any(not 0 <= c < 64 for c in (dest.x, dest.y, dest.return_x, dest.return_y)):
            raise ValueError("Hub tiles must be between 0 and 63.")
        if dest.description.strip():
            try:
                description_lines(dest.description)
            except ValueError as exc:
                raise ValueError(f"Destination {numbers[dest.chapter]}: {exc}") from None
    if len(chapters.chapter_phases(project, hub_page)) != 1:
        raise ValueError("The hub needs one map.")
    deployments = _deployments(project, hub_page)
    if not deployments:
        raise ValueError("The hub has no deployment file.")
    armies = 0
    for path in deployments:     # dispos_c.bin holds the cutscene units, with no player army
        player = _pids(path)[1]
        if player and player != {setup.avatar_pid}:
            raise ValueError(f"The hub's player army ({path.name}) must be the avatar {setup.avatar_pid} alone.")
        armies += bool(player)
    if not armies:
        raise ValueError(f"The hub's deployment has no player army with {setup.avatar_pid}.")
    for page in numbers.values():
        if page is None or page == hub_page:
            continue
        for path in _deployments(project, page):
            if setup.avatar_pid in _pids(path)[0]:
                raise ValueError(f"{setup.avatar_pid} also appears in chapter {page}'s deployment ({path.name}).")
    return numbers


def prepare(project, setup: HubSetup) -> dict:
    """Validate and compile every change without writing anything."""
    current = saved_setup(project)
    fe10 = _fe10(project)
    editor, story = _story(project, fe10)
    numbers = _validate(project, setup, current, fe10, story)
    table = ef.FE10_FLAGS
    startup = script_sources.startup_path(project)
    hub_path = script_sources.chapter_script(project, numbers[setup.chapter])
    activation_path = script_sources.chapter_script(project, numbers[setup.activation_chapter])
    scripts = {p: script_sources.peek(project, p) for p in (startup, hub_path, activation_path)}
    globals_ = ef.global_flags(parse(scripts[startup]), table)
    if current:
        slots, names = current["slots"], current["flags"]
        if globals_[slots["active"]:slots["active"] + len(names)] != names:
            raise ValueError("The hub flags moved since setup; restore their registration order first.")
    else:
        names, dest_slot = flag_names(len(globals_))
        if any(name in globals_ for name in names):
            raise ValueError("A hub flag name already exists in startup.cmb.")
        slots = {"active": len(globals_), "destination": dest_slot, "pending": dest_slot + 8}
        for name in names:
            scripts[startup] = ef.append_registration(scripts[startup], "RegistGlobalFlags", "global", name)
    config = rd_hub.validate_slots(setup.chapter, slots["active"], slots["destination"], slots["pending"])
    new_globals = ef.global_flags(parse(scripts[startup]), table)
    for page in numbers.values():
        path = script_sources.chapter_script(project, page) if page else None
        if path is None:
            continue
        source = scripts.get(path) or script_sources.peek(project, path)
        problem = ef.capacity_problem(len(new_globals), len(ef.local_flags(parse(source))), table.slot_count)
        if problem:
            raise ValueError(f"Chapter {page}: {problem}")
    if current and current["activation_chapter"] != setup.activation_chapter:
        old = script_sources.chapter_script(project, numbers.get(current["activation_chapter"]) or "")
        if old is not None:
            scripts[old] = _remove_generated(script_sources.peek(project, old))
    hub_base = _remove_generated(scripts[hub_path]) if current else scripts[hub_path]
    if any(d.name == "on_complete" for f in parse(hub_base).functions for d in f.decorators):
        raise ValueError("The hub's script still has a win event. Remove it before installing destinations.")
    scripts[activation_path] = activation_script(scripts[activation_path])
    scripts[hub_path] = hub_script(hub_base, setup)
    helpers = ef.exported_functions(parse(scripts[startup]))
    compiled = {}
    for path, source in scripts.items():
        result = compile_source(source, base=read_cmb(path.read_bytes()),
                                known_script_functions={} if path == startup else helpers,
                                global_flags=new_globals)
        compiled[path] = source, write_cmb(result.script)
    hub_paths = chapters.chapter_paths(project, numbers[setup.chapter])
    if hub_paths.map is None or hub_paths.dialogue is None:
        raise ValueError("The hub has no map or no message file.")
    marked_map = entrance_markers(project, hub_paths.map, setup)
    messages = _description_messages(hub_paths.dialogue, setup, profile_of(project).name_hash_buckets)
    deployments = {}
    if setup.start_x is not None:
        for path in _deployments(project, numbers[setup.chapter]):
            if _pids(path)[1]:
                deployments[path] = _positioned(path, setup.avatar_pid, setup.start_x, setup.start_y)
    session = editor.session
    rd_hub.RdHubFlow(editor).apply(session, config)
    return {"editor": editor, "story": story, "compiled": compiled, "slots": slots, "flags": names,
            "deployments": deployments, "map": (hub_paths.map, marked_map),
            "message": (hub_paths.dialogue, messages)}


def install(project, setup: HubSetup) -> dict:
    """Install the hub and return its saved configuration."""
    prepared = prepare(project, setup)
    for path, (source, data) in prepared["compiled"].items():
        _write_script(project, path, source, data)
    for path, data in prepared["deployments"].items():
        project.write_keeping_original(path, data)
    project.write_keeping_original(*prepared["map"])
    project.write_keeping_original(*prepared["message"])
    story = prepared["story"]
    if story.successors().get(setup.chapter):     # the router decides where the hub leads
        story._store(_without(story, setup.chapter), story._table(rd_story.ARMIES, rd_story._retail_armies()),
                     story._table(rd_story.FLAGS, rd_story._retail_flags()))
    else:
        prepared["editor"].save()
    saved = {**asdict(setup), "version": 1, "game": "fe10", "slots": prepared["slots"],
             "flags": prepared["flags"]}
    with open(config_path(project), "w", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(saved, indent=2) + "\n")
    if draft_path(project).is_file():
        draft_path(project).unlink()
    return saved


def _without(story, chapter: int) -> bytes:
    table = bytearray(story._table(rd_story.SUCCESSORS, bytes(0x100)))
    table[chapter] = 0
    return bytes(table)


def _write_script(project, path: Path, source: str, data: bytes) -> None:
    project.write_keeping_original(path, data)
    sidecar = script_sources.sidecar_path(project, path)
    sidecar.parent.mkdir(parents=True, exist_ok=True)
    with open(sidecar, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(source)


def uninstall(project) -> dict:
    """Remove the hub's events and routing. The flag registrations stay, so later flags keep
    their save slots."""
    current = saved_setup(project)
    if current is None:
        if draft_path(project).is_file():
            draft_path(project).unlink()
        return {}
    setup = setup_from(current)
    fe10 = _fe10(project)
    editor, story = _story(project, fe10)
    numbers = {n: _page_id(n, story.chapter_ids) for n in story.chapter_ids}
    globals_ = ef.global_flags(parse(script_sources.peek(project, script_sources.startup_path(project))),
                               ef.FE10_FLAGS)
    helpers = ef.exported_functions(parse(script_sources.peek(project, script_sources.startup_path(project))))
    compiled = {}
    for number in (setup.chapter, setup.activation_chapter):
        path = script_sources.chapter_script(project, numbers.get(number) or "")
        if path is None:
            continue
        source = _remove_generated(script_sources.peek(project, path))
        result = compile_source(source, base=read_cmb(path.read_bytes()), known_script_functions=helpers,
                                global_flags=globals_)
        compiled[path] = source, write_cmb(result.script)
    hub_paths = chapters.chapter_paths(project, numbers.get(setup.chapter) or "")
    updates = []
    if hub_paths.map is not None:
        from . import map_props
        entries, files = map_props.read_map_container(hub_paths.map)
        if _without_markers(files):
            updates.append((hub_paths.map, _pack_map(entries, files)))
    if hub_paths.dialogue is not None:
        updates.append((hub_paths.dialogue, _description_messages(hub_paths.dialogue, HubSetup(
            setup.chapter, setup.activation_chapter, setup.avatar_pid, ()), profile_of(project).name_hash_buckets)))
    rd_hub.RdHubFlow(editor).remove()
    for path, (source, data) in compiled.items():
        _write_script(project, path, source, data)
    for path, data in updates:
        project.write_keeping_original(path, data)
    config_path(project).unlink()
    if draft_path(project).is_file():
        draft_path(project).unlink()
    return current


def page_numbers(project, fe10: bytes | None = None) -> dict[int, str]:
    """Story number -> chapter page id (``0101``, ``0501``, ``final``)."""
    fe10 = fe10 if fe10 is not None else _fe10(project)
    return {n: _page_id(n, rd_story.chapter_number_map(fe10)) for n in rd_story.chapter_number_map(fe10)}


def is_hub_candidate(page_id: str) -> bool:
    return chapters_fe10.number_for(page_id) is not None


def activation_candidates(project, hub_number: int, fe10: bytes | None = None) -> dict[int, str]:
    """Story chapters that can open the hub: the others with a script, before the ending."""
    return {n: page for n, page in page_numbers(project, fe10).items()
            if n not in (TEST_MAP, hub_number, rd_story.ENDING)
            and script_sources.chapter_script(project, page) is not None}


def link_candidates(project, hub_number: int, fe10: bytes | None = None) -> dict[int, str]:
    """Story chapters a hub link can enter: script, map and deployment present."""
    out = {}
    for n, page in page_numbers(project, fe10).items():
        if n in (TEST_MAP, hub_number, rd_story.ENDING) or not rd_story.is_story_number(n):
            continue
        paths = chapters.chapter_paths(project, page)
        if paths.script is not None and paths.map is not None and paths.deployment is not None:
            out[n] = page
    return out


def deployed_pids(project, except_page: str | None = None, fe10: bytes | None = None) -> set[str]:
    """Every character in a chapter deployment, but ``except_page``'s."""
    out = set()
    for page in page_numbers(project, fe10).values():
        if page and page != except_page:
            for path in _deployments(project, page):
                out |= _pids(path)[0]
    return out


def avatar_candidates(project, fe10: bytes, except_page: str | None = None, keep: str | None = None) -> list[tuple[str, str]]:
    """``(pid, jid)`` of characters with a class that no other chapter deploys (``keep`` always listed)."""
    used = deployed_pids(project, except_page, fe10)
    return [(r.values["pid"], r.values["jid"]) for r in fe10data.read_table(fe10, "character")
            if (r.values.get("pid") or "").startswith("PID_") and r.values.get("jid")
            and (r.values["pid"] == keep or r.values["pid"] not in used)]


__all__ = ["ACTIVE", "STARTED", "DEST", "PENDING", "Destination", "HubSetup", "hub_script", "prepare",
           "install", "uninstall"]
