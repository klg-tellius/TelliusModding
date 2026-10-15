"""Create and remove Path of Radiance map phases."""
from __future__ import annotations

import re
import shutil
from dataclasses import dataclass
from pathlib import Path

from . import chapters, script_sources
from .formats import dispo, fe8data, lz10, pak
from .formats.cmb import source_tools
from .game_profile import files_dir_of


@dataclass(frozen=True)
class PhaseClone:
    folder: str
    files: dict[Path, bytes]
    fe8data: bytes | None
    zmap: Path


def next_folder(project, chapter_id: str) -> str:
    phases = chapters.chapter_phases(project, chapter_id)
    if not phases:
        raise ValueError("This chapter has no map phase to clone.")
    number = max(int(name.rsplit("_", 1)[1]) if "_" in name else 1 for name in phases) + 1
    return f"bmap{int(chapter_id):02d}_{number}"


def _clone_deployment(data: bytes, source: str, target: str) -> bytes:
    archive = lz10.decompress(data)
    entries = pak.read_pak_entries(archive)
    files = []
    for entry in entries:
        content = pak.read_pak_file_content(archive, entry)
        if entry.name.startswith("dispos_"):
            doc = dispo.parse_dispo(content)
            dispo.rename_section_prefix(doc, source, target)
            content = dispo.build_dispo(doc)
        files.append((entry.name, content))
    return lz10.compress(pak.pack_pak(files, [entry.reserved for entry in entries]))


def plan_clone(project, chapter_id: str, source: str, game_data: bytes | None = None) -> PhaseClone:
    phases = chapters.chapter_phases(project, chapter_id)
    if source not in phases:
        raise ValueError(f"{source} is not a phase of chapter {chapter_id}.")
    target = next_folder(project, chapter_id)
    zmap = files_dir_of(project) / "zmap"
    origin, destination = zmap / source, zmap / target
    if destination.exists():
        raise ValueError(f"{target} already exists.")
    files = {}
    for item in origin.rglob("*"):
        if not item.is_file():
            continue
        relative = item.relative_to(origin)
        data = item.read_bytes()
        if item.name.lower().startswith("dispos") and item.suffix.lower() == ".cmp":
            data = _clone_deployment(data, source, target)
        files[destination / relative] = data
    if destination / "map.cmp" not in files:
        raise ValueError(f"{source} has no map.cmp to clone.")
    updated = game_data
    if game_data is not None:
        rows = fe8data.read_battle_terrain(game_data)
        existing = next((row for row in rows if row.map_name == source), None)
        if existing is not None:
            if any(row.map_name == target for row in rows):
                raise ValueError(f"BattleTerrData already contains {target}.")
            updated = fe8data.write_battle_terrain(
                game_data, rows + [fe8data.BattleTerrainRow(target, list(existing.scenes))])
    return PhaseClone(target, files, updated, zmap)


def create_phase(clone: PhaseClone) -> None:
    if not clone.files:
        raise ValueError("The phase has no files.")
    # Every destination must be under the same newly created phase folder.
    root = clone.zmap / clone.folder
    if root.parent.resolve() != clone.zmap.resolve():
        raise ValueError("Phase target is outside zmap.")
    if any(root not in path.parents for path in clone.files):
        raise ValueError("Phase file is outside the target folder.")
    if root.exists():
        raise ValueError(f"{clone.folder} already exists.")
    try:
        for path, data in clone.files.items():
            if root not in path.parents:
                raise ValueError("Phase file is outside the target folder.")
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
    except Exception:
        if root.is_dir() and root.resolve().parent == clone.zmap.resolve():
            shutil.rmtree(root)
        raise


def referenced_in_script(source: str, folder: str) -> bool:
    """Conservatively detect the phase name in calls, section ids or comments."""
    return re.search(rf"(?<![A-Za-z0-9_]){re.escape(folder)}(?![A-Za-z0-9])", source) is not None


def plan_remove(project, chapter_id: str, folder: str, source: str | None = None,
                game_data: bytes | None = None) -> tuple[Path, bytes | None]:
    phases = chapters.chapter_phases(project, chapter_id)
    if folder not in phases:
        raise ValueError(f"{folder} is not a phase of chapter {chapter_id}.")
    if folder == f"bmap{int(chapter_id):02d}":
        raise ValueError("The primary map phase cannot be removed.")
    if source is not None and referenced_in_script(source, folder):
        raise ValueError(f"The chapter script still references {folder}. Remove those references first.")
    scripts = script_sources.scripts_dir(project)
    if scripts.is_dir():
        for script_path in scripts.glob("*.cmb"):
            saved_source = script_sources.peek(project, script_path)
            if referenced_in_script(saved_source, folder):
                raise ValueError(
                    f"{script_path.name} still references {folder}. Save the script after removing "
                    "those references before removing this phase.")
    updated = game_data
    if game_data is not None:
        rows = fe8data.read_battle_terrain(game_data)
        if any(row.map_name == folder for row in rows):
            updated = fe8data.write_battle_terrain(
                game_data, [row for row in rows if row.map_name != folder])
    return files_dir_of(project) / "zmap" / folder, updated


def remove_phase(project, path: Path) -> None:
    zmap = (files_dir_of(project) / "zmap").resolve()
    if (not path.is_dir() or not re.fullmatch(r"bmap\d+_\d+", path.name, re.IGNORECASE)
            or path.is_symlink() or path.parent.resolve() != zmap
            or path.resolve().parent != zmap):
        raise ValueError("Only a numbered secondary map phase inside this project's zmap can be removed.")
    shutil.rmtree(path)


def next_part(source: str) -> int:
    exports = {span.export_id for span in source_tools.function_spans(source)}
    present = [part for part in (2, 3, 4) if f"Opening18_{part}" in exports]
    if present != list(range(2, 2 + len(present))):
        raise ValueError("Chapter part openings have a gap; repair the script before adding another part.")
    part = len(present) + 2
    if part > 4:
        raise ValueError("The game supports at most four playable parts per chapter.")
    return part


def add_part_opening(source: str, part: int, folder: str) -> str:
    if part != next_part(source):
        raise ValueError("The playable parts must be added in order.")
    block = (f'@export\ndef Opening18_{part}():\n'
             f'    MapLoad("{folder}")\n')
    return source.rstrip() + "\n\n\n" + block


def playable_part_folders(source: str, phases: list[str] | tuple[str, ...]) -> dict[str, int]:
    """Map folders loaded by numbered battle openings, including the first part.

    Extra map folders without a numbered opening are map phases, not playable parts.
    """
    if not phases:
        return {}
    lines = source.splitlines()
    parts = {}
    for span in source_tools.function_spans(source):
        match = re.fullmatch(r"Opening18_([234])", span.export_id or "")
        if match is None:
            continue
        body = "\n".join(lines[span.def_line - 1:span.last_line])
        for folder in phases[1:]:
            if re.search(rf'\bMapLoad\s*\(\s*["\x27]{re.escape(folder)}["\x27]', body):
                parts[folder] = int(match.group(1))
                break
    return {phases[0]: 1, **parts} if parts else {}


def part_setup_issues(source: str, folder: str) -> tuple[int, list[str]] | None:
    """The part that loads this folder and its remaining guided setup steps."""
    lines = source.splitlines()
    for span in source_tools.function_spans(source):
        match = re.fullmatch(r"Opening18_([234])", span.export_id or "")
        if match is None:
            continue
        body = "\n".join(lines[span.def_line - 1:span.last_line])
        if not re.search(rf'\bMapLoad\s*\(\s*["\x27]{re.escape(folder)}["\x27]', body):
            continue
        part = int(match.group(1))
        issues = []
        if not re.search(rf'\b(?:Dispos\w*|SelectAuxiliary)\s*\([^)]*["\x27]{re.escape(folder)}_', body):
            issues.append("deployment")
        if not re.search(rf'\bComplete18\s*\(\s*{part - 1}\s*\)', source):
            issues.append("previous victory")
        return part, issues
    return None
