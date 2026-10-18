"""Prepare compatible layout and script updates for a verified installation."""
from pathlib import Path

from . import chapters, script_sources
from .extended_hub import HubProjectUpdate, PreparedFile, project_inventories
from .formats import event_flags as ef
from .formats.extended_flags import FlagLayout, FlagCompileContext, MANIFEST_NAME
from .formats.cmb import compile_source, read_cmb, write_cmb
from .formats.cmb.parser import parse
from .game_code.dol import Dol
from .game_code.extended_flag_installation import (
    inspect_project, RuntimeState, RECEIPT_NAME, rebuild_installed, receipt_for,
)
from .game_code.versions import read_boot_code


def prepare_runtime_update(project, layout: FlagLayout, sources=None):
    """Return one transaction for a layout edit and all accompanying script edits."""
    status = inspect_project(project)
    if status.state != RuntimeState.MATCHING:
        raise ValueError(f"Cannot update extended project: {status.state.value}: {status.detail}")
    layout.require_compatible(status.layout)
    inventories = project_inventories(project)
    changes = {Path(path): text for path, text in (sources or {}).items()}
    dependencies, outputs = {}, {}

    def snapshot(path):
        path = Path(path)
        if path not in dependencies:
            dependencies[path] = path.read_bytes() if path.exists() else None
        return dependencies[path]

    manifest_path = project.directory / MANIFEST_NAME
    receipt_path = project.directory / RECEIPT_NAME
    previous = FlagLayout.from_json(snapshot(manifest_path).decode("utf-8"))
    if previous != status.layout:
        raise ValueError("Manifest changed during update preparation")
    receipt = snapshot(receipt_path).decode("utf-8")
    executable = project.extracted_dir / "sys" / "main.dol"
    original = snapshot(executable)
    snapshot(project.extracted_dir / "sys" / "boot.bin")
    snapshot(project.directory / "hub.json")
    startup = script_sources.startup_path(project)
    paths = {path: None for path in script_sources.shared_scripts(project)}
    paths[startup] = None
    for cid in chapters.list_chapter_ids(project):
        path = script_sources.chapter_script(project, cid)
        if path is not None:
            paths[path] = int(cid)
    if set(changes) - set(paths):
        raise ValueError("Script update contains a path outside the project's script inventory")
    texts = {}
    for path in paths:
        snapshot(path)
        snapshot(script_sources.sidecar_path(project, path))
        texts[path] = changes[path] if path in changes else script_sources.peek(project, path)
    startup_module = parse(texts[startup])
    globals_ = ef.global_flags(startup_module)
    locals_ = {cid: ef.local_flags(parse(texts[path])) for path, cid in paths.items() if cid is not None}
    layout.validate_registrations(globals_, locals_)
    helpers = ef.exported_functions(startup_module)
    for path, source in texts.items():
        result = compile_source(source, base=read_cmb(dependencies[path]),
                                known_script_functions={} if path == startup else helpers,
                                global_flags=globals_, flag_context=FlagCompileContext(layout, paths[path]))
        if path in changes:
            outputs[path] = write_cmb(result.script)
            outputs[script_sources.sidecar_path(project, path)] = source.encode("utf-8")
    if layout != previous:
        candidate = rebuild_installed(Dol(original), read_boot_code(project.extracted_dir), previous, layout, receipt)
        outputs[executable] = candidate.executable
        outputs[manifest_path] = layout.to_json().encode("utf-8")
        outputs[receipt_path] = receipt_for(candidate, layout).encode("utf-8")
    update = HubProjectUpdate(tuple(PreparedFile(path, snapshot(path), data) for path, data in outputs.items()),
                              tuple(dependencies.items()), None, inventories)
    update.verify_unchanged()
    return update


def prepare_flag_add(project, name, scope, *, chapter=None, storage="extended"):
    """Assign a bank explicitly and prepare its registration in the same update."""
    status = inspect_project(project)
    if status.state != RuntimeState.MATCHING:
        raise ValueError(f"Extended storage is not ready: {status.state.value}")
    if scope not in ("campaign", "chapter") or storage not in ("vanilla", "extended"):
        raise ValueError("Invalid flag scope or storage bank")
    if scope == "chapter" and (type(chapter) is not int or not 0 <= chapter < 256):
        raise ValueError("A chapter flag requires a chapter number")
    if scope == "campaign" and chapter is not None:
        raise ValueError("Campaign flags do not belong to a chapter")
    startup = script_sources.startup_path(project)
    globals_ = ef.global_flags(parse(script_sources.peek(project, startup)))
    path = startup if scope == "campaign" else script_sources.chapter_script(project, f"{chapter:02d}")
    if path is None:
        raise ValueError("Chapter script is missing")
    source = script_sources.peek(project, path)
    taken = set(globals_) | set(ef.local_flags(parse(source)))
    # A campaign name must not collide with a local name in any chapter.
    if scope == "campaign":
        for cid in chapters.list_chapter_ids(project):
            local_path = script_sources.chapter_script(project, cid)
            if local_path is not None:
                taken.update(ef.local_flags(parse(script_sources.peek(project, local_path))))
    problem = ef.check_flag_name(name, taken)
    if problem or name.startswith(("HUB_", "gf_")):
        raise ValueError(problem or "Hub and engine flag names are reserved")
    layout = status.layout.add(name, scope, chapter) if storage == "extended" else status.layout
    source = ef.append_registration(source, "RegistGlobalFlags" if scope == "campaign" else "Startup",
                                    "global" if scope == "campaign" else "regist", name)
    return prepare_runtime_update(project, layout, {path: source})


def prepare_flag_edit(project, name, *, chapter=None, new_name=None):
    """Rename an extended flag, or retire an unused one, retaining its slot."""
    status = inspect_project(project)
    if status.state != RuntimeState.MATCHING:
        raise ValueError(f"Extended storage is not ready: {status.state.value}")
    entry = status.layout.find(name, chapter)
    if entry is None or (entry.scope == "campaign" and chapter is not None):
        raise ValueError("Only an assigned extended flag can be renamed or retired")
    inventory = project_inventories(project)
    paths = {path: None for path in script_sources.shared_scripts(project)}
    startup = script_sources.startup_path(project)
    paths[startup] = None
    for cid in chapters.list_chapter_ids(project):
        path = script_sources.chapter_script(project, cid)
        if path is not None:
            paths[path] = int(cid)
    dependencies = tuple((path, path.read_bytes() if path.exists() else None)
                         for script in paths for path in (script, script_sources.sidecar_path(project, script)))
    texts = {path: script_sources.peek(project, path) for path in paths}
    if new_name is not None:
        taken = set(ef.global_flags(parse(texts[startup])))
        for path, cid in paths.items():
            if entry.scope == "campaign" or cid == chapter:
                taken.update(ef.local_flags(parse(texts[path])))
        problem = ef.check_flag_name(new_name, taken)
        if problem or new_name.startswith(("HUB_", "gf_")):
            raise ValueError(problem or "Hub and engine flag names are reserved")
    changes = {}
    registration = startup if entry.scope == "campaign" else next(
        (path for path, cid in paths.items() if cid == chapter), None)
    for path, source in texts.items():
        if entry.scope == "chapter" and paths[path] != chapter:
            if paths[path] is None:
                ef.rename_flag_references(source, name, name)
                if name in ef.flag_uses(parse(source)):
                    raise ValueError("Shared scripts reference this chapter flag; review their scope before editing")
            continue
        # Also detects dynamic flag calls whose target cannot be proven safe.
        rewritten = ef.rename_flag_references(source, name, new_name or name)
        if new_name is None:
            if path == registration:
                rewritten = ef.remove_unused_registration(source, name,
                    "RegistGlobalFlags" if entry.scope == "campaign" else "Startup",
                    "global" if entry.scope == "campaign" else "regist")
            elif name in ef.flag_uses(parse(source)):
                raise ValueError(f"{name} is still referenced in {path.name}")
        if rewritten != source:
            changes[path] = rewritten
    layout = status.layout.rename(entry, new_name) if new_name is not None else status.layout.delete(entry)
    update = prepare_runtime_update(project, layout, changes)
    update = HubProjectUpdate(update.changes, update.dependencies + dependencies, update.migration,
                              update.inventories + inventory)
    update.verify_unchanged()
    return update
