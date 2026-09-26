"""Load and save event scripts as ``.fe9s`` source, the way the script editor
does: the source kept in ``script_sources/NAME.fe9s`` is reused while it still
compiles to the ``.cmb`` on disk, otherwise the file is decompiled fresh.
Saving compiles onto the current file (so untouched content keeps its bytes),
writes the ``.cmb`` keeping the original, and stores the source next to it.

Also resolves what compiling one script needs to know about the others: the
project's global flags and ``startup.cmb``'s exported helpers."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from .formats import event_flags
from .formats.cmb import CompileError, compile_source, decompile, read_cmb, write_cmb
from .formats.cmb.model import ScriptFile
from .formats.cmb.parser import ParseError, parse
from .project import ModProject

SOURCES_DIR = "script_sources"


def scripts_dir(project: ModProject) -> Path:
    return project.extracted_dir / "files" / "Scripts"


def startup_path(project: ModProject) -> Path:
    return scripts_dir(project) / "startup.cmb"


def sidecar_path(project: ModProject, cmb_path: Path) -> Path:
    return project.directory / SOURCES_DIR / (cmb_path.stem + ".fe9s")


def shared_scripts(project: ModProject) -> list[Path]:
    """The scripts that aren't one chapter's (``startup.cmb`` first)."""
    folder = scripts_dir(project)
    if not folder.is_dir():
        return []
    shared = [p for p in folder.glob("*.cmb") if not (p.stem[:1] in "Cc" and p.stem[1:].isdigit())]
    return sorted(shared, key=lambda p: (p.stem.lower() != "startup", p.stem.lower()))


@dataclass
class LoadedScript:
    path: Path
    source: str
    base: ScriptFile
    note: str  # where the source came from, for a status line


def load(project: ModProject, cmb_path: Path, *, ignore_sidecar: bool = False) -> LoadedScript:
    """Read ``cmb_path`` as source. A kept source that no longer matches the
    file is moved aside to ``.fe9s.bak``."""
    data = cmb_path.read_bytes()
    base = read_cmb(data)
    sidecar = sidecar_path(project, cmb_path)
    if sidecar.exists() and not ignore_sidecar:
        text = sidecar.read_text(encoding="utf-8")
        try:
            if write_cmb(compile_source(text, base=base).script) == data:
                return LoadedScript(cmb_path, text, base, "your saved source")
        except CompileError:
            pass
        backup = sidecar.with_suffix(".fe9s.bak")
        sidecar.replace(backup)
        note = f"the .cmb changed outside the editor - decompiled fresh (old source kept as {backup.name})"
    else:
        note = ""
    source, stats = decompile(base, cmb_path.name)
    return LoadedScript(cmb_path, source, base,
                        note or f"decompiled: {stats.structured} structured, {stats.goto} goto, {stats.asm} asm")


def peek(project: ModProject, cmb_path: Path) -> str:
    """The script's source for reading only: the kept source when it still
    matches the file, else a fresh decompile. Changes nothing on disk."""
    data = cmb_path.read_bytes()
    base = read_cmb(data)
    sidecar = sidecar_path(project, cmb_path)
    if sidecar.exists():
        text = sidecar.read_text(encoding="utf-8")
        try:
            if write_cmb(compile_source(text, base=base).script) == data:
                return text
        except CompileError:
            pass
    return decompile(base, cmb_path.name)[0]


def chapter_script(project: ModProject, chapter_id: str) -> Optional[Path]:
    """``Scripts/CNN.cmb`` of a chapter (map ``bmapNN``), if it exists."""
    path = scripts_dir(project) / f"C{int(chapter_id):02d}.cmb"
    return path if path.exists() else None


def save(project: ModProject, script: LoadedScript, source: str):
    """Compile ``source`` onto ``script.base`` and write both files. Raises
    :class:`CompileError`; returns the CompileResult and updates ``script``."""
    context = CompileContext.for_script(project, script.path, source)
    result = compile_source(source, base=script.base, known_script_functions=context.helpers,
                            global_flags=context.global_flags)
    data = write_cmb(result.script)
    project.write_keeping_original(script.path, data)
    sidecar = sidecar_path(project, script.path)
    sidecar.parent.mkdir(parents=True, exist_ok=True)
    sidecar.write_text(source, encoding="utf-8")
    script.base = read_cmb(data)
    script.source = source
    return result


@dataclass
class CompileContext:
    """What compiling one script should know about ``startup.cmb``."""

    global_flags: Optional[list]
    helpers: dict  # startup.cmb exports -> argument count

    _cache = {}  # startup path -> (mtime, CompileContext)

    @classmethod
    def for_project(cls, project: ModProject) -> "CompileContext":
        path = startup_path(project)
        try:
            stamp = path.stat().st_mtime_ns
        except OSError:
            return cls(None, {})
        cached = cls._cache.get(path)
        if cached is None or cached[0] != stamp:
            try:
                module = parse(decompile(read_cmb(path.read_bytes()), path.name)[0])
                context = cls(event_flags.global_flags(module), event_flags.exported_functions(module))
            except (OSError, ValueError, ParseError, CompileError):
                context = cls(None, {})  # a broken startup.cmb must not block chapter editing
            cached = (stamp, context)
            cls._cache[path] = cached
        return cached[1]

    @classmethod
    def for_script(cls, project: ModProject, cmb_path: Path, source: str) -> "CompileContext":
        """Compiling startup.cmb itself uses its own (edited) source."""
        if cmb_path.name.lower() == "startup.cmb":
            try:
                module = parse(source)
                return cls(event_flags.global_flags(module), {})
            except ParseError:
                return cls(None, {})
        return cls.for_project(project)
