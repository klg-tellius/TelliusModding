"""Convert a project from the extracted layout (1) to the input/output layout (2).

A layout-1 project holds a whole extracted disc in ``extracted/`` that edits overwrote, with some
first copies in ``originals/``. Converting it:

1. finds the vanilla store for its disc: the source disc extracted into the store (or found there
   already), a folder the user extracted, or, without either, a vanilla tree rebuilt from the
   project's own files (``extracted/`` with ``originals/`` laid over it, checked against the
   disc's file table);
2. compares ``extracted/`` with the store file by file (size, then SHA-1). Not ``originals/``
   alone: files some older editors wrote kept no original;
3. writes the files that differ or that the disc lacks into ``output/``, the disc files missing
   from ``extracted/`` into ``overlay.json`` as removed, and checks the copies;
4. switches ``project.json`` to layout 2 and moves ``extracted/``, ``originals/`` and ``source/``
   into ``.layout1-backup/``, deleted only when the user asks (:func:`delete_backup`).

``project.json`` is rewritten last, so a conversion that fails part way leaves the project in
layout 1 as it was. ``python -m fe_modding.layout_migration PROJECT [--disc IMAGE | --folder DIR]``
converts from the command line.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

from . import vanilla_store
from .exceptions import ProjectError
from .game_files import OVERLAY_FILE, _walk_files, copy_atomic, sha1_of, write_atomic
from .project import (EXTRACTED_DIR, LAYOUT_EXTRACTED, LAYOUT_OVERLAY, ORIGINALS_DIR, OUTPUT_DIR,
                      SOURCE_DIR, ModProject)

BACKUP_DIR = ".layout1-backup"

Progress = Optional[Callable[[str], None]]


@dataclass
class MigrationPlan:
    """What converting a project will do (all paths disc-relative)."""

    store: vanilla_store.VanillaStore
    replaced: list[str] = field(default_factory=list)
    added: list[str] = field(default_factory=list)
    removed: list[str] = field(default_factory=list)
    hashes: dict[str, str] = field(default_factory=dict)    # SHA-1 of each output file
    warnings: list[str] = field(default_factory=list)

    def describe(self) -> str:
        return (f"{len(self.replaced)} replaced, {len(self.added)} added and {len(self.removed)} removed "
                f"files go to output/; every other file is read from {self.store.root}.")


def _say(progress: Progress, text: str) -> None:
    if progress is not None:
        progress(text)


def _rebuilt_store(project: ModProject, progress: Progress) -> tuple[vanilla_store.VanillaStore, list[str]]:
    """A store made from the project's own files: ``extracted/`` with ``originals/`` over it, minus
    files the disc's table does not list. Files changed without a kept original are taken as
    vanilla, so they cannot be told apart; the warning says so."""
    from .formats import gcdisc
    extracted, originals = project.extracted_dir, project.originals_dir
    root = vanilla_store.store_root()
    root.mkdir(parents=True, exist_ok=True)
    try:
        sizes = gcdisc.read_fst_sizes((extracted / "sys" / "fst.bin").read_bytes())
    except (OSError, ValueError) as exc:
        raise ProjectError(f"The project's sys/fst.bin could not be read: {exc}") from exc
    disc = {f"files/{name}" for name in sizes}
    with tempfile.TemporaryDirectory(prefix=".rebuild-", dir=root) as temporary:
        tree = Path(temporary) / "disc"
        _say(progress, "Rebuilding the vanilla files from the project…")
        for rel in _walk_files(extracted):
            if rel.startswith("files/") and rel not in disc:
                continue    # a file the mod added
            kept = originals / rel
            source = kept if kept.is_file() else extracted / rel
            (tree / rel).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, tree / rel)
        missing = sorted(rel for rel in disc if not (tree / rel).is_file())
        if missing:
            raise ProjectError("The vanilla files cannot be rebuilt without the disc: the project no longer "
                               f"has {', '.join(missing[:5])}{' …' if len(missing) > 5 else ''}. Choose the disc image "
                               "or an extracted folder instead.")
        try:
            store = vanilla_store.register_tree(tree, wii=project.profile.wii)
        except ProjectError as exc:
            raise ProjectError("The vanilla files cannot be rebuilt without the disc (files were changed "
                               f"without keeping their original): {exc} Choose the disc image or an "
                               "extracted folder instead.") from exc
    warning = ("The vanilla files were rebuilt from the project itself. Files an editor changed without "
               "keeping a copy of the original are taken as vanilla, so they are not in output/.")
    return store, [warning]


def find_store(project: ModProject, *, disc: Optional[Path] = None, folder: Optional[Path] = None,
               progress: Progress = None) -> tuple[vanilla_store.VanillaStore, list[str]]:
    """The store to convert against, and any warning about it (see the module docstring)."""
    if folder is not None:
        _say(progress, "Checking the extracted folder…")
        return vanilla_store.adopt_folder(folder, wii=project.profile.wii), []
    image = Path(disc) if disc is not None else project.source_path
    if image is not None and image.is_file():
        _say(progress, f"Extracting {image.name} into the vanilla files…")
        return vanilla_store.ensure_store(image, wii=project.profile.wii), []
    return _rebuilt_store(project, progress)


def plan_migration(project: ModProject, store: vanilla_store.VanillaStore, warnings=(),
                   progress: Progress = None) -> MigrationPlan:
    """Compare the project's ``extracted/`` with ``store`` (nothing is written)."""
    if project.layout != LAYOUT_EXTRACTED:
        raise ProjectError("The project already uses the input/output layout.")
    if not project.has_extracted_files:
        raise ProjectError("The project has no extracted files to convert.")
    from .games import read_disc_id
    found = read_disc_id(project.extracted_dir)
    if found and found != store.disc_id:
        raise ProjectError(f"The project's disc is {found}, but these vanilla files are {store.disc_id}.")
    plan = MigrationPlan(store=store, warnings=list(warnings))
    vanilla = store.manifest()["files"]
    seen = set()
    names = list(_walk_files(project.extracted_dir))
    for index, rel in enumerate(names):
        if index % 500 == 0:
            _say(progress, f"Comparing the project's files ({index}/{len(names)})…")
        path = project.extracted_dir / rel
        entry = vanilla.get(rel)
        if entry is None:
            plan.added.append(rel)
            plan.hashes[rel] = sha1_of(path)
            continue
        seen.add(rel)
        if path.stat().st_size == entry["size"]:
            digest = sha1_of(path)
            if digest == entry["sha1"]:
                continue
        else:
            digest = sha1_of(path)
        plan.replaced.append(rel)
        plan.hashes[rel] = digest
    plan.removed = sorted(set(vanilla) - seen)
    return plan


def apply_migration(project: ModProject, plan: MigrationPlan, progress: Progress = None) -> None:
    """Write ``output/`` and ``overlay.json``, switch the project to layout 2 and move the old
    layout's folders into :data:`BACKUP_DIR`."""
    directory = project.directory
    output = directory / OUTPUT_DIR
    if output.exists() and any(output.iterdir()):
        raise ProjectError(f"{output} already holds files; move them away first.")
    partial = directory / f".{OUTPUT_DIR}.partial"
    if partial.exists():
        shutil.rmtree(partial)
    _say(progress, "Copying the mod's files to output/…")
    for rel in plan.replaced + plan.added:
        copy_atomic(project.extracted_dir / rel, partial / rel)
        os.chmod(partial / rel, 0o666)
        if sha1_of(partial / rel) != plan.hashes[rel]:
            raise ProjectError(f"The copy of {rel} does not match the project's file.")
    vanilla = plan.store.file_hashes()
    state = {"removed": plan.removed, "base": {rel: vanilla[rel] for rel in plan.replaced}}
    if output.exists():
        output.rmdir()
    if partial.exists():
        os.replace(partial, output)
    else:
        output.mkdir()
    write_atomic(directory / OVERLAY_FILE, (json.dumps(state, indent=2) + "\n").encode("utf-8"))

    project.layout = LAYOUT_OVERLAY
    project.input_key = plan.store.key
    project._files = None
    project.save()     # the switch: from here the project opens in layout 2

    backup = directory / BACKUP_DIR
    backup.mkdir(exist_ok=True)
    for name in (EXTRACTED_DIR, ORIGINALS_DIR, SOURCE_DIR):
        if (directory / name).exists():
            _say(progress, f"Moving {name}/ to {BACKUP_DIR}/…")
            os.replace(directory / name, backup / name)


def has_backup(project: ModProject) -> bool:
    return (project.directory / BACKUP_DIR).is_dir()


def delete_backup(project: ModProject) -> None:
    """Delete the old layout's folders kept by :func:`apply_migration`."""
    if project.layout != LAYOUT_OVERLAY:
        raise ProjectError("The project has not been converted.")
    backup = project.directory / BACKUP_DIR
    if backup.is_dir():
        def clear(function, path, _info):
            os.chmod(path, 0o666)
            function(path)
        shutil.rmtree(backup, onerror=clear)


def convert(project: ModProject, *, disc: Optional[Path] = None, folder: Optional[Path] = None,
            progress: Progress = None) -> MigrationPlan:
    """Find the store, plan and apply the conversion; returns the plan that was applied."""
    store, warnings = find_store(project, disc=disc, folder=folder, progress=progress)
    plan = plan_migration(project, store, warnings, progress)
    apply_migration(project, plan, progress)
    return plan


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Convert a project to the input/output layout.")
    parser.add_argument("project", type=Path)
    source = parser.add_mutually_exclusive_group()
    source.add_argument("--disc", type=Path, help="the source disc image (else the project's own)")
    source.add_argument("--folder", type=Path, help="a folder already holding the extracted disc")
    parser.add_argument("--dry-run", action="store_true", help="only report what would change")
    args = parser.parse_args(argv)
    try:
        project = ModProject.load(args.project)
        store, warnings = find_store(project, disc=args.disc, folder=args.folder, progress=print)
        plan = plan_migration(project, store, warnings, progress=print)
        for warning in plan.warnings:
            print("Warning:", warning)
        print(plan.describe())
        if not args.dry_run:
            apply_migration(project, plan, progress=print)
            print(f"Converted. The old folders are in {project.directory / BACKUP_DIR}.")
    except ProjectError as exc:
        print(exc, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
