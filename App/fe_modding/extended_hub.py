"""Prepare an existing hub's flag-storage migration without writing files.

Only app-owned padding registrations are removed. The eighteen functional names
stay registered and are intercepted by the extended runtime. Existing saves are
not migrated; the new layout/container starts a fresh playthrough.
"""
from copy import deepcopy
from dataclasses import dataclass, asdict
import re
import json
from pathlib import Path

from . import hub
from .formats import event_flags as ef
from .formats.extended_flags import FlagLayout, FlagCompileContext, HUB_ALIASES
from .formats.cmb import compile_source
from .formats.cmb.parser import parse
from .game_profile import files_root_of, sys_root_of


@dataclass(frozen=True)
class HubMigration:
    startup_source: str
    configuration: dict
    vanilla_globals: tuple[str, ...]
    removed_padding: tuple[str, ...]


def prepare_migration(startup_source: str, chapter_sources: dict[int, str],
                      configuration: dict, layout: FlagLayout) -> HubMigration:
    """Validate all chapter budgets and return reviewable source/config changes.

    Callers must supply every chapter script. Executable installation and file
    transaction handling remain separate, gated operations.
    """
    if configuration.get("version") not in (1, 2) or configuration.get("storage") is not None:
        raise ValueError("Migration requires an installed legacy hub configuration")
    chapter = configuration.get("chapter")
    if type(chapter) is not int or not 33 <= chapter < 90:
        raise ValueError("Invalid installed hub chapter")
    slots = configuration.get("slots", {})
    start = slots.get("active")
    if type(start) is not int or not 0 <= start < 96:
        raise ValueError("Invalid legacy hub flag slots")
    expected, destination = hub.flag_names(start)
    from .game_code.hub_flow import validate_slots
    validate_slots(chapter, start, destination, destination + 8)
    if (configuration.get("flags") != expected or
            slots != {"active": start, "destination": destination, "pending": destination + 8}):
        raise ValueError("Legacy hub flag layout differs from the generated layout")
    module = parse(startup_source)
    globals_ = ef.global_flags(module)
    if globals_[start:start + len(expected)] != expected:
        raise ValueError("Hub registration order differs from the installed configuration")
    if any(globals_.count(name) != 1 for name in expected):
        raise ValueError("Hub flags must be registered exactly once")
    if chapter not in chapter_sources or configuration.get("activation_chapter") not in chapter_sources:
        raise ValueError("Hub and activation scripts are required for migration")
    padding = tuple(name for name in expected if name not in HUB_ALIASES)
    for index, source in enumerate((startup_source, *chapter_sources.values())):
        uses = ef.flag_uses(parse(source))
        for name in padding:
            if any(native != "global" for _, native in uses.get(name, [])):
                raise ValueError(f"{name} is used by event logic; it cannot be removed as padding")
        if index and any(name in uses for name in padding):
            raise ValueError("Hub padding is registered outside startup.cmb")
    lines = startup_source.splitlines(keepends=True)
    sites = ef.registration_sites(module, "RegistGlobalFlags", "global")
    for site in sites:
        if site.name not in padding:
            continue
        # Only remove a simple generated statement; never erase other logic on
        # the same line, or part of a multiline expression.
        pattern = (r'\s*extern\(\s*[\"\x27]global[\"\x27]\s*,\s*[\"\x27]'
                   + re.escape(site.name) + r'[\"\x27]\s*\)\s*(?:#.*)?')
        line = lines[site.line - 1].rstrip("\r\n")
        if not re.fullmatch(pattern, line):
            raise ValueError(f"Padding registration {site.name} is not a standalone statement")
        # A comment keeps source line numbers stable for diagnostics.
        indent = line[:len(line) - len(line.lstrip())]
        ending = "\r\n" if lines[site.line - 1].endswith("\r\n") else "\n"
        lines[site.line - 1] = indent + "# Hub padding removed for extended storage." + ending
    migrated = "".join(lines)
    new_module = parse(migrated)
    new_globals = ef.global_flags(new_module)
    if new_globals != [name for name in globals_ if name not in padding]:
        raise ValueError("Padding removal changed unrelated registrations")
    locals_ = {cid: ef.local_flags(parse(source)) for cid, source in chapter_sources.items()}
    layout.validate_registrations(new_globals, locals_)
    compile_source(migrated, flag_context=FlagCompileContext(layout))
    helpers = ef.exported_functions(new_module)
    for cid, source in chapter_sources.items():
        compile_source(source, known_script_functions=helpers, global_flags=new_globals,
                       flag_context=FlagCompileContext(layout, cid))
    result = deepcopy(configuration)
    result.pop("slots")
    result.update(version=3, storage="extended", layout_identity=layout.identity, flags=list(HUB_ALIASES))
    return HubMigration(migrated, result, tuple(layout.vanilla_names(new_globals, "campaign")), padding)


@dataclass(frozen=True)
class PreparedFile:
    path: Path
    before: bytes | None
    after: bytes


@dataclass(frozen=True)
class HubProjectUpdate:
    """A complete, read-only migration proposal; production installation is gated."""
    changes: tuple[PreparedFile, ...]
    dependencies: tuple[tuple[Path, bytes | None], ...]
    migration: HubMigration | None
    inventories: tuple = ()

    def verify_unchanged(self):
        for path, expected in self.inventories:
            if _inventory(path) != expected:
                raise ValueError(f"Project inventory changed after preparation: {path}")
        for path, before in self.dependencies:
            seen = path.read_bytes() if path.exists() else None
            if seen != before:
                raise ValueError(f"Project changed after migration preparation: {path}")


def _inventory(path):
    return tuple(sorted(p.name + ("/" if p.is_dir() else "") for p in path.iterdir())) if path.exists() else None


def project_inventories(project):
    return tuple((path, _inventory(path)) for path in
                 (files_root_of(project) / name for name in ("Scripts", "Mess", "zmap")))


def prepare_project_update(project, layout: FlagLayout) -> HubProjectUpdate:
    """Compile and pair startup, sidecar, config, manifest and DOL changes.

    The caller can review the proposal without editing the project. Every input
    is retained for stale-plan detection before a future transaction commits it.
    """
    from . import chapters, script_sources
    from .formats.cmb import read_cmb, write_cmb
    from .formats.extended_flags import MANIFEST_NAME
    from .game_code.editor import CodeEditor
    from .game_code.extended_flag_candidate import build_candidate

    inventories = project_inventories(project)
    dependencies = {}

    def snapshot(path):
        path = Path(path)
        if path not in dependencies:
            dependencies[path] = path.read_bytes() if path.exists() else None
        return dependencies[path]

    config_path = hub.config_path(project)
    config_raw = snapshot(config_path)
    if config_raw is None:
        raise ValueError("Install a legacy hub before preparing its storage migration")
    configuration = json.loads(config_raw)
    manifest_path = project.directory / MANIFEST_NAME
    manifest_raw = snapshot(manifest_path)
    if manifest_raw is not None:
        layout.require_compatible(FlagLayout.from_json(manifest_raw.decode("utf-8")))
    startup = script_sources.startup_path(project)

    def source(path):
        snapshot(path)
        snapshot(script_sources.sidecar_path(project, path))
        return script_sources.peek(project, path)

    startup_source = source(startup)
    chapter_sources = {}
    for cid in chapters.list_chapter_ids(project):
        path = script_sources.chapter_script(project, cid)
        if path is not None:
            chapter_sources[int(cid)] = source(path)
    migration = prepare_migration(startup_source, chapter_sources, configuration, layout)
    executable_path = sys_root_of(project) / "main.dol"
    snapshot(executable_path)
    snapshot(sys_root_of(project) / "boot.bin")
    editor = CodeEditor(project.extracted_dir)
    if editor.version is None:
        raise ValueError("Cannot identify the project's executable region")
    candidate = build_candidate(editor.dol, editor.version.code, layout, hub_chapter=configuration["chapter"])
    from .game_code.extended_flag_installation import RECEIPT_NAME, receipt_for
    compiled = compile_source(migration.startup_source, base=read_cmb(dependencies[startup]),
                              flag_context=FlagCompileContext(layout))
    outputs = {
        executable_path: candidate.executable,
        startup: write_cmb(compiled.script),
        script_sources.sidecar_path(project, startup): migration.startup_source.encode("utf-8"),
        config_path: (json.dumps(migration.configuration, indent=2) + "\n").encode("utf-8"),
        manifest_path: layout.to_json().encode("utf-8"),
        project.directory / RECEIPT_NAME: receipt_for(candidate, layout).encode("utf-8"),
    }
    result = HubProjectUpdate(tuple(PreparedFile(path, snapshot(path), data) for path, data in outputs.items()),
                              tuple(dependencies.items()), migration, inventories)
    result.verify_unchanged()
    return result


def commit_project_update(project, update: HubProjectUpdate):
    """Commit only after regional release approval, including kept originals.

    No region is approved yet. The transaction engine is independently testable;
    this entry point must not install unvalidated native code into user projects.
    """
    from .exceptions import ProjectError
    from .game_code.extended_flags import EXTENDED_FLAGS_PATCH, UNAVAILABLE_REASON
    from .game_code.versions import read_boot_code
    from .project_transaction import commit

    region = read_boot_code(project.extracted_dir)
    if region not in EXTENDED_FLAGS_PATCH.versions:
        raise ProjectError(UNAVAILABLE_REASON)
    update.verify_unchanged()
    changes = list(update.changes)
    dependencies = list(update.dependencies)
    for change in update.changes:
        original = project._original_of(change.path)
        if original is None or change.before is None:
            continue
        kept = original.read_bytes() if original.exists() else None
        dependencies.append((original, kept))
        if kept is None:
            changes.insert(0, PreparedFile(original, None, change.before))
    commit(project.directory, changes, dependencies, validate=update.verify_unchanged)
    from .script_sources import CompileContext
    CompileContext._cache.clear()


def prepare_fresh_project_update(project, setup: hub.HubSetup, layout: FlagLayout) -> HubProjectUpdate:
    """Prepare a new hub directly in extended storage, without a legacy install.

    Reuses the map, avatar, destination, message and script validation performed
    by ordinary hub setup. All outputs go through the same gated transaction.
    """
    return _prepare_hub_update(project, setup, layout, reconfigure=False)


def prepare_reconfigure_project_update(project, setup: hub.HubSetup, layout: FlagLayout) -> HubProjectUpdate:
    """Atomically replace a verified extended hub's scripts and configuration."""
    return _prepare_hub_update(project, setup, layout, reconfigure=True)


def prepare_install_project_update(project, setup, layout):
    """Choose fresh installation, legacy migration or extended reconfiguration."""
    current = hub.saved_setup(project)
    if current is None:
        return prepare_fresh_project_update(project, setup, layout)
    if current.get("storage") == "extended":
        return prepare_reconfigure_project_update(project, setup, layout)
    migration_update = prepare_project_update(project, layout)
    update = _prepare_hub_update(project, setup, layout, reconfigure=False,
                                 migration=migration_update.migration)
    combined = HubProjectUpdate(update.changes, update.dependencies + migration_update.dependencies,
                                update.migration, update.inventories + migration_update.inventories)
    combined.verify_unchanged()
    return combined


def _prepare_hub_update(project, setup, layout, *, reconfigure, migration=None):
    from . import chapters, script_sources
    from .formats.extended_flags import MANIFEST_NAME
    from .game_code.extended_flag_candidate import build_candidate

    inventories = project_inventories(project)
    dependencies = {}

    def snapshot(path):
        if path is not None:
            path = Path(path)
            if path not in dependencies:
                dependencies[path] = path.read_bytes() if path.exists() else None
        return dependencies.get(path)

    configuration_path = hub.config_path(project)
    configuration_raw = snapshot(configuration_path)
    if not reconfigure and migration is None and configuration_raw is not None:
        raise ValueError("Use storage migration for an existing hub")
    from .game_code.extended_flag_installation import RECEIPT_NAME, receipt_for, inspect_project, RuntimeState, rebuild_installed
    receipt_raw = snapshot(project.directory / RECEIPT_NAME)
    if reconfigure:
        status = inspect_project(project)
        if configuration_raw is None or status.state != RuntimeState.MATCHING:
            raise ValueError("Reconfiguration requires a verified extended hub")
    manifest_path = project.directory / MANIFEST_NAME
    previous = snapshot(manifest_path)
    if previous is not None:
        layout.require_compatible(FlagLayout.from_json(previous.decode("utf-8")))
    snapshot(project.logical_path("game_data"))
    executable_path = sys_root_of(project) / "main.dol"
    snapshot(executable_path)
    snapshot(sys_root_of(project) / "boot.bin")
    startup = script_sources.startup_path(project)
    snapshot(startup)
    snapshot(script_sources.sidecar_path(project, startup))
    for cid in chapters.list_chapter_ids(project):
        paths = chapters.chapter_paths(project, cid)
        for path in (paths.script, paths.dialogue, paths.map, paths.deployment):
            snapshot(path)
        if paths.script is not None:
            snapshot(script_sources.sidecar_path(project, paths.script))
        for folder in chapters.chapter_phases(project, cid):
            deployment, map_path = chapters.phase_paths(project, folder)
            snapshot(deployment)
            snapshot(map_path)
    draft = hub.draft_path(project)
    snapshot(draft)
    prepared = hub._prepare(project, setup, extended_layout=layout, migration=migration)
    editor = prepared["editor"]
    if editor.version is None:
        raise ValueError("Cannot identify the project's executable region")
    candidate = (rebuild_installed(editor.dol, editor.version.code, status.layout, layout, receipt_raw)
                 if reconfigure else
                 build_candidate(editor.dol, editor.version.code, layout, hub_chapter=setup.chapter))
    configuration = {**asdict(setup), "version": 3, "storage": "extended",
                     "layout_identity": layout.identity, "flags": list(HUB_ALIASES),
                     "normal_successor": prepared["normal_successor"]}
    outputs = {executable_path: candidate.executable,
               configuration_path: (json.dumps(configuration, indent=2) + "\n").encode("utf-8"),
               manifest_path: layout.to_json().encode("utf-8"),
               project.directory / RECEIPT_NAME: receipt_for(candidate, layout).encode("utf-8")}
    for path, (source, data) in prepared["compiled"].items():
        outputs[path] = data
        outputs[script_sources.sidecar_path(project, path)] = source.encode("utf-8")
    outputs[prepared["message"][0]] = prepared["message"][1]
    outputs[prepared["map"][0]] = prepared["map"][1]
    if prepared["deployment"] is not None:
        outputs[prepared["deployment"][0]] = prepared["deployment"][1]
    if dependencies[draft] is not None:
        # Keep the editing draft consistent with the setup selected for this
        # proposal; no stale draft should hide the installed configuration.
        outputs[draft] = (json.dumps({**asdict(setup), "storage": "extended"}, indent=2) + "\n").encode("utf-8")
    startup_source = prepared["compiled"][startup][0]
    migration = HubMigration(startup_source, configuration,
                             tuple(layout.vanilla_names(ef.global_flags(parse(startup_source)), "campaign")), ())
    result = HubProjectUpdate(tuple(PreparedFile(path, snapshot(path), data) for path, data in outputs.items()),
                              tuple(dependencies.items()), migration, inventories)
    result.verify_unchanged()
    return result
