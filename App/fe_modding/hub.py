"""Set up a prepared FE9 chapter as a reusable campaign hub.

The map and dedicated avatar character are supplied by the modder.  This module
generates the event-script glue and installs conditional chapter routing.
"""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path

from . import chapters, script_sources, map_props
from .formats import dispo, event_flags as ef, fe8data, fe9_message_scene, lz10, map_file, message, pak
from .formats.cmb import compile_source, read_cmb, write_cmb
from .formats.cmb.parser import parse
from .game_code.catalog import Session, State
from .game_code.chapter_flow import ChapterFlow, FLOW_PATCH, GAME_CLEARED
from .game_code.dol import Dol
from .game_code.editor import CodeEditor
from .game_code.hub_flow import HUB_CONFIG, HUB_PATCH, HubFlow, validate_slots
from .game_profile import disc_root_of, files_root_of, profile_of

CONFIG_NAME = "hub.json"
START_MARK = "# BEGIN TELLIUS HUB SETUP"
END_MARK = "# END TELLIUS HUB SETUP"
ENTRANCE_OBJECT = "tellius_hub_entrance"


def entrance_markers(project, map_path: Path, setup) -> bytes:
    """Replace app-owned entrance placements with native Arrive indicators."""
    entries, files = map_props.read_map_container(map_path)
    data = map_file.read_map_bytes(files["map.bin"])
    index = next((i for i, obj in enumerate(data.build_desc)
                  if obj.filename == ENTRANCE_OBJECT), None)
    if index is None:
        # Prefer the retail Arrive marker; use Seize if the project only has
        # early chapters. Copy all resources and remap shared texture indices.
        candidates = sorted((files_root_of(project) / "zmap").glob("*/map.cmp"))
        preferred = files_root_of(project) / "zmap/bmap18/map.cmp"
        if preferred in candidates:
            candidates.remove(preferred)
            candidates.insert(0, preferred)
        donor = None
        for path in candidates:
            _, source = map_props.read_map_container(path)
            objects = map_file.read_map_bytes(source["map.bin"]).build_desc
            name = next((name for name in ("attainment_01", "ascendancy_01")
                         if any(o.filename == name for o in objects) and f"{name}.gs" in source), None)
            if name:
                donor = source, name
                break
        if donor is None:
            raise ValueError("Hub entrances need a native Arrive or Seize marker from an extracted chapter map.")
        map_props.copy_prop(*donor, entries, files, name=ENTRANCE_OBJECT)
        data = map_file.read_map_bytes(files["map.bin"])
        index = next(i for i, obj in enumerate(data.build_desc) if obj.filename == ENTRANCE_OBJECT)
    records = map_file.instance_records(files["map.bin"])
    files["map.bin"] = map_file.set_build_instances(files["map.bin"],
        [record for record, inst in zip(records, data.build_inst) if inst.desc_index != index])
    for destination in setup.destinations:
        map_props.place_prop(files, ENTRANCE_OBJECT, destination.x, destination.y)
    return lz10.compress(pak.pack_pak([(e.name, files[e.name]) for e in entries],
                                    [e.reserved for e in entries]))
ACTIVE = "HUB_ACTIVE"
STARTED = "HUB_STARTED"
DEST = tuple(f"HUB_DEST_{i}" for i in range(8))
PENDING = tuple(f"HUB_PENDING_{i}" for i in range(8))


@dataclass(frozen=True)
class Destination:
    chapter: int
    x: int
    y: int
    return_x: int
    return_y: int
    description: str = ""


@dataclass(frozen=True)
class HubSetup:
    chapter: int
    activation_chapter: int
    avatar_pid: str
    destinations: tuple[Destination, ...]
    start_x: int | None = None
    start_y: int | None = None


def description_key(chapter: int) -> str:
    return f"MS_HUB_{chapter:02d}_INFO"


def config_path(project) -> Path:
    return project.directory / CONFIG_NAME


def saved_setup(project) -> dict | None:
    path = config_path(project)
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else None


DRAFT_NAME = "hub_draft.json"


def draft_path(project) -> Path:
    return project.directory / DRAFT_NAME


def working_setup(project) -> dict | None:
    """The hub being edited: its draft (changes not installed yet), else the installed setup."""
    path = draft_path(project)
    if path.is_file():
        return json.loads(path.read_text(encoding="utf-8"))
    return saved_setup(project)


def hub_chapter(project) -> int | None:
    setup = working_setup(project)
    return setup["chapter"] if setup else None


def save_draft(project, setup: dict) -> None:
    keys = ("chapter", "activation_chapter", "avatar_pid", "destinations", "start_x", "start_y")
    data = {key: setup.get(key) for key in keys}
    if setup.get("storage") in ("vanilla", "extended"):
        data["storage"] = setup["storage"]
    with open(draft_path(project), "w", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(data, indent=2) + "\n")


def setup_from(data: dict) -> HubSetup:
    return HubSetup(data["chapter"], data["activation_chapter"], data["avatar_pid"],
                    tuple(Destination(d["chapter"], d["x"], d["y"], d["return_x"], d["return_y"],
                                      d.get("description", "")) for d in data.get("destinations", ())),
                    data.get("start_x"), data.get("start_y"))


def _replace_generated(source: str, block: str) -> str:
    if (START_MARK in source) != (END_MARK in source):
        raise ValueError("A hub-generated script block has only one boundary marker.")
    if START_MARK in source:
        start = source.index(START_MARK)
        end = source.index(END_MARK, start) + len(END_MARK)
        return source[:start].rstrip() + "\n\n" + block + source[end:]
    return source.rstrip() + "\n\n" + block + "\n"


def _remove_generated(source: str) -> str:
    if START_MARK not in source:
        return source
    if END_MARK not in source:
        raise ValueError("A hub-generated script block has no end marker.")
    start = source.index(START_MARK)
    end = source.index(END_MARK, start) + len(END_MARK)
    return source[:start].rstrip() + "\n" + source[end:]


def _remove_opening_hook(source: str, avatar_pid: str) -> str:
    """Remove the positioning call inserted immediately before the generated avatar focus."""
    hook = '    HubPositionAvatar()\n'
    focus = f'    InstantUnitFocusByPID("{avatar_pid}")'
    return source.replace(hook + focus, focus, 1)


def _flag_assignments(chapter: int) -> list[str]:
    return [f'    {"set" if chapter & (1 << i) else "clr"}("{name}")'
            for i, name in enumerate(DEST)]


def _destination_expression(chapter: int) -> str:
    return " and ".join(f'get("{name}") == {(chapter >> i) & 1}' for i, name in enumerate(DEST))


def hub_script(source: str, setup: HubSetup) -> str:
    """Replace only the app-owned event block in a prepared hub script."""
    # Generated openings focus the avatar while the screen is still black.
    # Position it before that focus/fade instead of visibly moving it on turn 1.
    focus = f'    InstantUnitFocusByPID("{setup.avatar_pid}")'
    hook = '    HubPositionAvatar()\n'
    opening = re.search(r"(?m)^def Opening0\(\):\n(?:[ \t].*\n|\n)*", source)
    if opening and focus in opening[0] and hook + focus not in opening[0]:
        source = source[:opening.start()] + opening[0].replace(focus, hook + focus, 1) + source[opening.end():]
    body = [START_MARK,
            '@export',
            'def HubPositionAvatar():',
            f'    unit = UnitGetByPID("{setup.avatar_pid}")',
            '    if unit:']
    for dest in setup.destinations:
        body += [f'        if {_destination_expression(dest.chapter)}:',
                 f'            UnitSetPos(unit, {dest.return_x}, {dest.return_y})']
    body += ['', '@on_phase(turn_from=1, turn_to=1, phase="player")',
             'def HubPlaceAvatar():', '    HubPositionAvatar()',
             '', '@after_action', 'def HubRefreshAvatar():',
             f'    unit = UnitGetByPID("{setup.avatar_pid}")',
             '    if unit:', '        UnitClrStatus(unit, 1)', '        UnitDispReload()', '        MapUpdate()',
             '', '@on_complete(flag="gf_complete")', 'def HubReleaseAvatar():',
             f'    unit = UnitGetByPID("{setup.avatar_pid}")',
             '    if unit:', '        UnitTransferToForce(unit, 4)']
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


def activation_script(source: str) -> str:
    block = "\n".join((START_MARK, '@on_complete(flag="gf_complete")',
                       'def HubActivateOnce():', f'    if not get("{STARTED}"):',
                       f'        set("{ACTIVE}")', f'        set("{STARTED}")', END_MARK))
    return _replace_generated(source, block)


def flag_names(start: int) -> tuple[list[str], int]:
    """Append active/started flags, align chapter bytes, then reserve two bytes."""
    names = [ACTIVE, STARTED]
    destination_slot = (start + 2 + 7) & ~7
    names.extend(f"HUB_PAD_{i}" for i in range(destination_slot - start - 2))
    names.extend(DEST)
    names.extend(PENDING)
    return names, destination_slot


def _validate_setup(project, setup: HubSetup, current: dict | None, flow: ChapterFlow) -> None:
    if profile_of(project).script_dialect != "fe9":
        raise ValueError("Hub setup currently supports Path of Radiance only.")
    game_data = project.read_logical("game_data")
    records = {record.chapter_id for record in fe8data.read_chapter_data(game_data)}
    available = {int(cid) for cid in chapters.list_chapter_ids(project)} & records
    if setup.chapter not in available or setup.activation_chapter not in available:
        raise ValueError("The hub and activation chapter need playable chapter records and scripts.")
    if not 33 <= setup.chapter < 90 or setup.activation_chapter == setup.chapter:
        raise ValueError("Use a separate added chapter (33-89) for the hub.")
    if setup.activation_chapter == 28:
        raise ValueError("Chapter 28 continues directly into chapter 29; activate the hub after chapter 29 instead.")
    if current is None and flow.predecessors(setup.chapter):
        raise ValueError("Take the hub chapter out of the normal story order before configuring it.")
    if not setup.avatar_pid.startswith("PID_") or '"' in setup.avatar_pid:
        raise ValueError("Choose a valid dedicated PID_ avatar.")
    if setup.avatar_pid not in {entry.pid for entry in fe8data.read_fe8data(game_data).characters}:
        raise ValueError(f"Character {setup.avatar_pid} has no CharacterData record.")
    if not setup.destinations:
        raise ValueError("The hub needs at least one destination tile.")
    if (setup.start_x is None) != (setup.start_y is None):
        raise ValueError("Provide both avatar start coordinates.")
    if setup.start_x is not None and (not 0 <= setup.start_x < 64 or not 0 <= setup.start_y < 64):
        raise ValueError("The avatar start must be on a tile from 0 to 63.")
    ids, tiles = set(), set()
    for dest in setup.destinations:
        if dest.chapter not in available or dest.chapter in (setup.chapter, GAME_CLEARED):
            raise ValueError(f"Destination {dest.chapter} is not a playable chapter.")
        if dest.chapter == 29:
            raise ValueError("Chapter 29 is the second half of chapter 28; select chapter 28 instead.")
        paths = chapters.chapter_paths(project, f"{dest.chapter:02d}")
        if paths.script is None or paths.map is None or paths.deployment is None:
            raise ValueError(f"Destination {dest.chapter} is missing its script, map, or deployment.")
        if dest.chapter in ids or (dest.x, dest.y) in tiles:
            raise ValueError("Destination chapters and action tiles must each be unique.")
        ids.add(dest.chapter)
        tiles.add((dest.x, dest.y))
        if any(not 0 <= coordinate < 64 for coordinate in (dest.x, dest.y, dest.return_x, dest.return_y)):
            raise ValueError("Hub tile coordinates must be between 0 and 63.")
        if len(dest.description) > 240 or any(c in dest.description for c in "$\x00\r\n"):
            raise ValueError(f"Destination {dest.chapter} has an invalid description (240 characters maximum; no control codes).")
        try:
            dest.description.encode(message.ENCODING)
        except UnicodeEncodeError as exc:
            raise ValueError(f"Destination {dest.chapter} has text the game cannot encode.") from exc
    if current and current["chapter"] != setup.chapter:
        raise ValueError("Change the existing hub chapter by removing its setup first.")
    if not flow.available:
        raise ValueError(f"Story flow is unavailable: {flow.unavailable_reason}")
    if script_sources.chapter_script(project, f"{setup.chapter:02d}") is None:
        raise ValueError("The prepared hub has no chapter script.")
    if script_sources.chapter_script(project, f"{setup.activation_chapter:02d}") is None:
        raise ValueError("The activation chapter has no script.")
    phase_folders = chapters.chapter_phases(project, f"{setup.chapter:02d}")
    if len(phase_folders) != 1:
        raise ValueError("The hub needs one prepared map phase.")
    deployment_path, map_path = chapters.phase_paths(project, phase_folders[0])
    if deployment_path is None or map_path is None:
        raise ValueError("The hub needs a map and deployment file.")
    packed = lz10.decompress(map_path.read_bytes())
    map_entry = next((entry for entry in pak.read_pak_entries(packed) if entry.name == "map.bin"), None)
    if map_entry is None:
        raise ValueError("The hub's map archive has no map.bin.")
    capacity = map_file.read_map_bytes(pak.read_pak_file_content(packed, map_entry)).capacity
    if capacity is None:
        raise ValueError("The hub map has no mapcapacity section.")
    for dest in setup.destinations:
        if dest.x >= capacity.x_size or dest.return_x >= capacity.x_size or \
                dest.y >= capacity.y_size or dest.return_y >= capacity.y_size:
            raise ValueError(f"Destination {dest.chapter} has a tile outside the hub map.")
    if setup.start_x is not None and (setup.start_x >= capacity.x_size or setup.start_y >= capacity.y_size):
        raise ValueError("The avatar start is outside the hub map.")
    _hub_units, player_units = _deployment_pids(deployment_path)
    if player_units != {setup.avatar_pid}:
        raise ValueError("The hub's player army must be the dedicated avatar alone; other armies may hold "
                         "decoration units.")
    for chapter_id in chapters.list_chapter_ids(project):
        if int(chapter_id) == setup.chapter:
            continue
        for folder in chapters.chapter_phases(project, chapter_id):
            path, _map = chapters.phase_paths(project, folder)
            if path is not None and setup.avatar_pid in _deployment_pids(path)[0]:
                raise ValueError(f"{setup.avatar_pid} also appears in chapter {chapter_id}'s deployment.")


def _deployment_pids(path: Path) -> tuple[set[str], set[str]]:
    packed = lz10.decompress(path.read_bytes())
    pids, player_pids = set(), set()
    for entry in pak.read_pak_entries(packed):
        if not entry.name.startswith("dispos_"):
            continue
        doc = dispo.parse_dispo(pak.read_pak_file_content(packed, entry))
        for section in doc.sections:
            if not section.is_link:
                names = {unit[dispo.FIELD["pid"]] for unit in section.units if unit[dispo.FIELD["pid"]]}
                pids.update(names)
                if "mikata" in section.name or "_avatar_" in section.name:
                    player_pids.update(names)
    return pids, player_pids


def _avatar_position_bytes(path: Path, pid: str, x: int, y: int) -> bytes:
    packed = lz10.decompress(path.read_bytes())
    entries = pak.read_pak_entries(packed)
    files, reserved = [], []
    found = False
    for entry in entries:
        content = pak.read_pak_file_content(packed, entry)
        if entry.name.startswith("dispos_"):
            doc = dispo.parse_dispo(content)
            for section in doc.sections:
                for unit in section.units:
                    if unit[dispo.FIELD["pid"]] == pid:
                        dispo.move_unit(unit, x, y)
                        found = True
            content = dispo.build_dispo(doc)
        files.append((entry.name, content))
        reserved.append(entry.reserved)
    if not found:
        raise ValueError(f"The hub deployment has no {pid} unit to position.")
    return lz10.compress(pak.pack_pak(files, reserved))


def prepare(project, setup: HubSetup) -> dict:
    """Validate and compile all source changes without writing project files."""
    from .game_code.extended_flags import require_project_runtime
    require_project_runtime(project)
    return _prepare(project, setup)


def _prepare(project, setup: HubSetup, *, extended_layout=None, migration=None) -> dict:
    """Shared read-only preparation; extended callers must use the gated commit."""
    current = saved_setup(project)
    if migration is not None:
        current = migration.configuration
    elif extended_layout is not None and current is not None:
        from .game_code.extended_flag_installation import inspect_project, RuntimeState
        status = inspect_project(project)
        if status.state != RuntimeState.MATCHING or current.get("storage") != "extended":
            raise ValueError("Reconfiguration requires a verified extended hub")
        extended_layout.require_compatible(status.layout)
    editor = CodeEditor(disc_root_of(project), project.write_keeping_original)
    flow = ChapterFlow(editor)
    _validate_setup(project, setup, current, flow)
    deployment_path, _map = chapters.phase_paths(project, chapters.chapter_phases(project, f"{setup.chapter:02d}")[0])
    marked_map = entrance_markers(project, _map, setup)
    deployment_data = (_avatar_position_bytes(deployment_path, setup.avatar_pid, setup.start_x, setup.start_y)
                       if setup.start_x is not None else None)
    from .hub_creation import repair_avatar_deployment, avatar_class
    deployment_data = repair_avatar_deployment(deployment_data if deployment_data is not None
                                      else deployment_path.read_bytes(), setup.avatar_pid,
                                      avatar_class(project.read_logical("game_data"), setup.avatar_pid))
    startup = script_sources.startup_path(project)
    hub_path = script_sources.chapter_script(project, f"{setup.chapter:02d}")
    activation_path = script_sources.chapter_script(project, f"{setup.activation_chapter:02d}")
    scripts = {p: script_sources.peek(project, p) for p in (startup, hub_path, activation_path)}
    if migration is not None:
        scripts[startup] = migration.startup_source
    hub_base = _remove_generated(scripts[hub_path]) if current else scripts[hub_path]
    if any(decorator.name == "on_complete" for function in parse(hub_base).functions
           for decorator in function.decorators):
        raise ValueError("The prepared hub script still has a chapter-completion event. Remove its old victory "
                         "event before installing hub destinations.")
    original_globals = ef.global_flags(parse(scripts[startup]))
    if extended_layout is not None:
        from .formats.extended_flags import HUB_ALIASES
        if current:
            if ([name for name in original_globals if name.startswith("HUB_")] != list(HUB_ALIASES)):
                raise ValueError("Installed hub aliases differ from the generated registrations")
        elif any(name.startswith("HUB_") for name in original_globals):
            raise ValueError("A hub flag name already exists in startup.cmb.")
        slots = None
        expected = list(HUB_ALIASES)
        if current is None:
            for name in expected:
                scripts[startup] = ef.append_registration(scripts[startup], "RegistGlobalFlags", "global", name)
    elif current:
        slots = current["slots"]
        expected = current["flags"]
        if original_globals[slots["active"]:slots["active"] + len(expected)] != expected:
            raise ValueError("Hub flag slots changed since setup; restore their registration order first.")
    else:
        taken = set(original_globals)
        names, dest_slot = flag_names(len(original_globals))
        if any(name in taken for name in names):
            raise ValueError("A hub flag name already exists in startup.cmb.")
        slots = {"active": len(original_globals), "destination": dest_slot, "pending": dest_slot + 8}
        for name in names:
            scripts[startup] = ef.append_registration(scripts[startup], "RegistGlobalFlags", "global", name)
        expected = names
    router_config = (bytes((setup.chapter, 0, 1, 1, 2)) if extended_layout is not None else
                     validate_slots(setup.chapter, slots["active"], slots["destination"], slots["pending"]))
    if current and extended_layout is None and HubFlow(editor).config() != router_config:
        raise ValueError("The executable's hub routing differs from the saved hub setup.")
    new_globals = ef.global_flags(parse(scripts[startup]))
    global_count = (len(extended_layout.vanilla_names(new_globals, "campaign"))
                    if extended_layout is not None else len(new_globals))
    if global_count >= 96:
        raise ValueError("The hub flags leave no room for chapter-local flags.")
    local_registrations, script_chapters = {}, {}
    for cid in chapters.list_chapter_ids(project):
        path = script_sources.chapter_script(project, cid)
        if path is None:
            continue
        source = scripts[path] if path in scripts else script_sources.peek(project, path)
        locals_ = ef.local_flags(parse(source))
        local_registrations[int(cid)] = locals_
        script_chapters[path] = int(cid)
        local_count = (len(extended_layout.vanilla_names(locals_, "chapter", int(cid)))
                       if extended_layout is not None else len(locals_))
        problem = ef.capacity_problem(global_count, local_count)
        if problem:
            raise ValueError(f"Chapter {cid}: {problem}")
    if extended_layout is not None:
        extended_layout.validate_registrations(new_globals, local_registrations)
        from .formats.extended_flags import FlagCompileContext
        for cid in chapters.list_chapter_ids(project):
            path = script_sources.chapter_script(project, cid)
            if path is not None:
                source = scripts[path] if path in scripts else script_sources.peek(project, path)
                FlagCompileContext(extended_layout, int(cid)).vanilla_counts(
                    new_globals, ef.local_flags(parse(source)))
    if current and current["activation_chapter"] != setup.activation_chapter:
        old_path = script_sources.chapter_script(project, f'{current["activation_chapter"]:02d}')
        scripts[old_path] = _remove_generated(script_sources.peek(project, old_path))
    scripts[activation_path] = activation_script(scripts[activation_path])
    scripts[hub_path] = hub_script(scripts[hub_path], setup)
    dialogue = chapters.chapter_paths(project, f"{setup.chapter:02d}").dialogue
    if dialogue is None:
        raise ValueError("The hub has no chapter message file.")
    old_messages = message.read_messages_path(dialogue)
    messages = [m for m in old_messages if not re.fullmatch(r"MS_HUB_\d{2}_INFO", m.speaker)]
    for dest in setup.destinations:
        if dest.description.strip():
            key = description_key(dest.chapter)
            collision = next((m.speaker for m in messages
                              if message.engine_name_hash(m.speaker) == message.engine_name_hash(key)), None)
            if collision:
                raise ValueError(f"The message ID for destination {dest.chapter} collides with {collision}.")
            raw = fe9_message_scene.to_raw("$RGMAP会話|$O3$G" + dest.description.strip() + "$K")
            messages.append(message.Message(key, raw))
    message_data = message.write_messages(messages, message.read_text_order_path(dialogue))
    helpers = ef.exported_functions(parse(scripts[startup]))
    compiled = {}
    for path, source in scripts.items():
        base = read_cmb(path.read_bytes())
        context = (FlagCompileContext(extended_layout, None if path == startup else script_chapters[path])
                   if extended_layout is not None else None)
        result = compile_source(source, base=base,
                                known_script_functions={} if path == startup else helpers,
                                global_flags=new_globals, flag_context=context)
        compiled[path] = (source, write_cmb(result.script))
    if current is None:
        normal_successor = flow.next_of(setup.chapter)
    else:
        normal_successor = current["normal_successor"]
    if editor.status(FLOW_PATCH).state == State.CONFLICT:
        raise ValueError("The executable's chapter-flow hook conflicts with another patch.")
    scratch_dol = Dol(bytes(editor.dol.data))
    if current and extended_layout is not None and migration is None:
        from .game_code.extended_flag_installation import _restore, RECEIPT_NAME
        scratch_dol = _restore(scratch_dol, json.loads((project.directory / RECEIPT_NAME).read_text(encoding="utf-8")))
    scratch = Session(scratch_dol, editor.version, editor.session.retail)
    if scratch.patch_status(FLOW_PATCH).state == State.ORIGINAL:
        scratch.set_patch(FLOW_PATCH, True)
    hub_status = scratch.patch_status(HUB_PATCH)
    if hub_status.state not in (State.ORIGINAL, State.APPLIED):
        raise ValueError("The executable's hub code cave conflicts with another patch.")
    tail = HUB_PATCH.versions[editor.version.code][0]
    expected_tail = tail.patched if hub_status.state == State.APPLIED else tail.original
    if scratch.dol.read(tail.address, 4) != expected_tail:
        raise ValueError("The executable's chapter-flow tail branch conflicts with another patch.")
    scratch.set_patch(HUB_PATCH, True)
    scratch._write(HUB_CONFIG, router_config)
    return {"editor": editor, "flow": flow, "compiled": compiled, "slots": slots,
            "flags": expected, "normal_successor": normal_successor,
            "message": (dialogue, message_data),
            "map": (_map, marked_map),
            "deployment": (deployment_path, deployment_data) if deployment_data is not None else None}


def install(project, setup: HubSetup) -> dict:
    """Install a validated hub setup and return its saved configuration."""
    prepared = prepare(project, setup)
    for path, (source, data) in prepared["compiled"].items():
        project.write_keeping_original(path, data)
        sidecar = script_sources.sidecar_path(project, path)
        sidecar.parent.mkdir(parents=True, exist_ok=True)
        sidecar.write_text(source, encoding="utf-8")
    project.write_keeping_original(*prepared["message"])
    project.write_keeping_original(*prepared["map"])
    if prepared["deployment"] is not None:
        project.write_keeping_original(*prepared["deployment"])
    flow = prepared["flow"]
    if flow.next_of(setup.chapter) != setup.chapter:
        flow.set_next(setup.chapter, setup.chapter)
    slots = prepared["slots"]
    HubFlow(prepared["editor"]).install(setup.chapter, slots["active"],
                                        slots["destination"], slots["pending"])
    saved = {**asdict(setup), "version": 2, "slots": slots, "flags": prepared["flags"],
             "normal_successor": prepared["normal_successor"]}
    with open(config_path(project), "w", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(saved, indent=2) + "\n")
    if draft_path(project).is_file():
        draft_path(project).unlink()
    return saved


def uninstall(project) -> dict:
    """Remove an installed vanilla hub setup while preserving the chapter and user edits.

    Generated event blocks, Visit messages, entrance placements and executable routing are
    removed.  The appended global registrations remain reserved so later user flags never move
    to different save slots.  Extended-runtime hubs must be removed with that runtime's own
    lifecycle because restoring only its router would invalidate the signed receipt.
    """
    current = saved_setup(project)
    if current is None:
        draft = draft_path(project)
        if draft.is_file():
            draft.unlink()
        return {}
    if current.get("storage", "vanilla") == "extended":
        raise ValueError("Remove the extended flag runtime before deleting its hub chapter.")

    setup = setup_from(current)
    editor = CodeEditor(disc_root_of(project), project.write_keeping_original)
    router = HubFlow(editor)
    if not router.installed:
        raise ValueError("The saved hub configuration exists, but its executable routing is not installed.")
    flow = ChapterFlow(editor)
    if not flow.available:
        raise ValueError(f"Story flow is unavailable: {flow.unavailable_reason}")

    startup = script_sources.startup_path(project)
    hub_path = script_sources.chapter_script(project, f"{setup.chapter:02d}")
    activation_path = script_sources.chapter_script(project, f"{setup.activation_chapter:02d}")
    if hub_path is None or activation_path is None:
        raise ValueError("The hub or activation chapter script is missing.")
    sources = {
        hub_path: _remove_opening_hook(_remove_generated(script_sources.peek(project, hub_path)), setup.avatar_pid),
        activation_path: _remove_generated(script_sources.peek(project, activation_path)),
    }
    globals_ = ef.global_flags(parse(script_sources.peek(project, startup)))
    helpers = ef.exported_functions(parse(script_sources.peek(project, startup)))
    compiled = {}
    for path, source in sources.items():
        base = read_cmb(path.read_bytes())
        result = compile_source(source, base=base, known_script_functions=helpers,
                                global_flags=globals_)
        compiled[path] = source, write_cmb(result.script)

    dialogue = chapters.chapter_paths(project, f"{setup.chapter:02d}").dialogue
    message_update = None
    if dialogue is not None:
        kept = [m for m in message.read_messages_path(dialogue)
                if not re.fullmatch(r"MS_HUB_\d{2}_INFO", m.speaker)]
        message_update = dialogue, message.write_messages(kept, message.read_text_order_path(dialogue))

    map_update = None
    phases = chapters.chapter_phases(project, f"{setup.chapter:02d}")
    if phases:
        _deployment, map_path = chapters.phase_paths(project, phases[0])
        if map_path is not None:
            entries, files = map_props.read_map_container(map_path)
            data = map_file.read_map_bytes(files["map.bin"])
            index = next((i for i, obj in enumerate(data.build_desc)
                          if obj.filename == ENTRANCE_OBJECT), None)
            if index is not None:
                records = map_file.instance_records(files["map.bin"])
                files["map.bin"] = map_file.set_build_instances(
                    files["map.bin"],
                    [record for record, instance in zip(records, data.build_inst)
                     if instance.desc_index != index],
                )
                map_update = map_path, lz10.compress(pak.pack_pak(
                    [(entry.name, files[entry.name]) for entry in entries],
                    [entry.reserved for entry in entries],
                ))

    # Remove the router before restoring the hub chapter's normal successor; ChapterFlow protects
    # the managed hub entry while the router is present.
    router.remove()
    flow = ChapterFlow(CodeEditor(disc_root_of(project), project.write_keeping_original))
    flow.set_next(setup.chapter, int(current["normal_successor"]))
    for path, (source, data) in compiled.items():
        project.write_keeping_original(path, data)
        sidecar = script_sources.sidecar_path(project, path)
        sidecar.parent.mkdir(parents=True, exist_ok=True)
        sidecar.write_text(source, encoding="utf-8")
    if message_update is not None:
        project.write_keeping_original(*message_update)
    if map_update is not None:
        project.write_keeping_original(*map_update)
    config_path(project).unlink()
    if draft_path(project).is_file():
        draft_path(project).unlink()
    return current
