"""Shared plumbing for the interactive Dolphin test session.

A *patch* is the list of files one test changes against the clean extracted disc, stored
under ``<package>/patches/<id>/`` with the same ``sys/`` and ``files/`` paths as the disc.
A *run tree* is what Dolphin boots: ``sys/`` copied, ``files/`` rebuilt as real folders whose
files are hard links to the clean disc (no space used) except the patched ones, which are
copied. Dolphin ignores junctions nested inside a tree, so links are made file by file. A run
tree is only ever read by Dolphin; nothing writes through its hard links.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

APP = Path(__file__).resolve().parents[2]
if str(APP) not in sys.path:
    sys.path.insert(0, str(APP))

from fe_modding.games import Game  # noqa: E402
from fe_modding.project import ModProject  # noqa: E402

#: Files whose hashes the runner checks on the clean disc before every launch.
WATCHED = ("sys/main.dol", "files/FE8Data.bin", "files/system.cmp", "files/Scripts/startup.cmb")
MANIFEST = "manifest.json"


def sha256(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def write_lf(path: Path, text: str) -> None:
    """Repository rule: LF line endings, UTF-8."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as stream:
        stream.write(text)


def write_cmd(path: Path, text: str) -> None:
    """Windows batch files keep CRLF."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\r\n") as stream:
        stream.write(text)


# -- the work project ---------------------------------------------------------------------------

def _snapshot(root: Path) -> dict[str, tuple[int, int]]:
    out = {}
    for folder, _dirs, files in os.walk(root):
        for name in files:
            path = Path(folder) / name
            st = path.stat()
            out[path.relative_to(root).as_posix()] = (st.st_size, st.st_mtime_ns)
    return out


class WorkProject:
    """One full copy of the clean disc in a throw-away project. Each fixture edits it through the
    app's own functions; :meth:`collect` lists what changed and :meth:`revert` puts it back."""

    def __init__(self, base: Path, directory: Path, region: str = "GFEE01", game: Game = Game.PATH_OF_RADIANCE):
        self.base = base
        self.directory = directory
        self.region = region
        if not (directory / "project.json").is_file():
            directory.parent.mkdir(parents=True, exist_ok=True)
            self.project = ModProject.create(directory.parent, directory.name, game)
        else:
            self.project = ModProject.load(directory)
        self.extracted = self.project.extracted_dir
        if not (self.extracted / "sys" / "main.dol").is_file():
            print(f"Copying the clean disc to {self.extracted} (once)...", flush=True)
            shutil.copytree(base, self.extracted, dirs_exist_ok=True)
        self.snapshot = _snapshot(self.extracted)
        self.revert()

    def _clean_project_folder(self) -> None:
        keep = {"project.json", "extracted"}
        for item in self.directory.iterdir():
            if item.name in keep:
                continue
            if item.is_dir() and not item.is_symlink():
                shutil.rmtree(item)
            else:
                item.unlink()
        for sub in ("source", "build", "originals"):
            (self.directory / sub).mkdir(exist_ok=True)

    def changed(self) -> list[str]:
        """Relative paths under ``extracted/`` that differ from the clean disc."""
        out = []
        for folder, _dirs, files in os.walk(self.extracted):
            for name in files:
                path = Path(folder) / name
                rel = path.relative_to(self.extracted).as_posix()
                st = path.stat()
                if self.snapshot.get(rel) == (st.st_size, st.st_mtime_ns):
                    continue
                clean = self.base / rel
                if clean.is_file() and clean.stat().st_size == st.st_size and clean.read_bytes() == path.read_bytes():
                    continue
                out.append(rel)
        missing = [rel for rel in self.snapshot if not (self.extracted / rel).is_file()]
        if missing:
            raise RuntimeError(f"A fixture deleted disc files: {missing[:5]}")
        return sorted(out)

    def revert(self) -> None:
        for folder, _dirs, files in os.walk(self.extracted):
            for name in files:
                path = Path(folder) / name
                rel = path.relative_to(self.extracted).as_posix()
                st = path.stat()
                if self.snapshot.get(rel) == (st.st_size, st.st_mtime_ns):
                    continue
                if rel in self.snapshot:
                    shutil.copy2(self.base / rel, path)
                    st = path.stat()
                    self.snapshot[rel] = (st.st_size, st.st_mtime_ns)
                else:
                    path.unlink()
        for folder, dirs, files in os.walk(self.extracted, topdown=False):
            if not dirs and not files and Path(folder) != self.extracted:
                rel = Path(folder).relative_to(self.extracted).as_posix()
                if not (self.base / rel).is_dir():
                    Path(folder).rmdir()
        self._clean_project_folder()
        # A fresh project object: nothing cached from the previous fixture.
        self.project = ModProject.load(self.directory)


# -- run trees ------------------------------------------------------------------------------------

def _remove_tree(path: Path) -> None:
    """Delete a run tree. It only holds copies and hard links, never junctions; refuse otherwise."""
    if not path.exists():
        return
    for folder, dirs, _files in os.walk(path):
        for name in dirs:
            sub = Path(folder) / name
            if sub.is_symlink() or (hasattr(sub, "is_junction") and sub.is_junction()):
                raise RuntimeError(f"{sub} is a link; remove it by hand (rmdir) before deleting {path}.")
    shutil.rmtree(path)


def assemble_run_tree(base: Path, patch: Path, run: Path) -> Path:
    """Build ``run`` from the clean disc ``base`` plus the patch folder; returns its main.dol."""
    _remove_tree(run / "sys")
    _remove_tree(run / "files")
    overlay = {p.relative_to(patch).as_posix(): p for p in patch.rglob("*") if p.is_file()
               and p.relative_to(patch).parts[0] in ("sys", "files")}
    (run / "sys").mkdir(parents=True)
    for item in (base / "sys").iterdir():
        if item.is_file():
            shutil.copyfile(overlay.pop(f"sys/{item.name}", item), run / "sys" / item.name)
    same_volume = os.path.splitdrive(str(base.resolve()))[0].lower() == os.path.splitdrive(str(run.resolve()))[0].lower()
    files = base / "files"
    for folder, _dirs, names in os.walk(files):
        target_dir = run / "files" / Path(folder).relative_to(files)
        target_dir.mkdir(parents=True, exist_ok=True)
        for name in names:
            source = Path(folder) / name
            rel = (Path("files") / source.relative_to(files)).as_posix()
            target = target_dir / name
            if rel in overlay:
                shutil.copyfile(overlay.pop(rel), target)
            elif same_volume:
                os.link(source, target)
            else:
                shutil.copyfile(source, target)
    for rel, source in overlay.items():           # files the patch adds to the disc
        target = run / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
    # a Wii disc's partition metadata (ticket.bin, tmd.bin, cert.bin, h3.bin, disc/) sits beside sys and files
    for item in base.iterdir():
        if item.is_file() and item.suffix == ".bin":
            shutil.copyfile(item, run / item.name)
        elif item.is_dir() and item.name == "disc":
            shutil.copytree(item, run / "disc", dirs_exist_ok=True)
    return run / "sys" / "main.dol"


# -- Dolphin ----------------------------------------------------------------------------------

DOLPHIN_CONFIG_FILES = ("Dolphin.ini", "GFX.ini", "GCPadNew.ini", "GCKeyNew.ini", "Hotkeys.ini", "Qt.ini")


def prepare_dolphin_user(user: Path, source_config: Optional[Path]) -> None:
    """An isolated Dolphin user folder, seeded once from the normal one so the controller and
    graphics settings are the usual ones. The tester's real saves and settings are never used."""
    config = user / "Config"
    if (config / "Dolphin.ini").is_file():
        return
    config.mkdir(parents=True, exist_ok=True)
    if source_config is not None and source_config.is_dir():
        for name in DOLPHIN_CONFIG_FILES:
            if (source_config / name).is_file():
                shutil.copy2(source_config / name, config / name)


def normal_volume(source_config: Optional[Path]) -> int:
    """The tester's own Dolphin volume (DSP Volume), 75 when unknown."""
    try:
        for line in (source_config / "Dolphin.ini").read_text(encoding="utf-8", errors="replace").splitlines():
            key, _, value = line.partition("=")
            if key.strip() == "Volume" and value.strip().isdigit() and int(value) > 0:
                return int(value)
    except (OSError, TypeError):
        pass
    return 75


#: Radiant Dawn's NAND save folder under a Dolphin user folder.
RD_NAND_DATA = Path("Wii/title/00010000/52464545/data")


def dolphin_command(dolphin: Path, user: Path, main_dol: Path, card: Path, *, gdb: bool = False,
                    volume: int = 75) -> list[str]:
    command = [str(dolphin), "--user", str(user), "--batch", "--exec", str(main_dol),
               f"--config=Dolphin.DSP.Volume={volume}",
               "--config=Dolphin.Core.SlotA=8",
               f"--config=Dolphin.Core.GCIFolderAPathOverride={card.resolve()}",
               "--config=Dolphin.Core.SlotB=0",
               "--config=Dolphin.Core.EnableCheats=False",
               "--config=Dolphin.Analytics.Enabled=False",
               "--config=Dolphin.Analytics.PermissionAsked=True"]
    if gdb:
        command.append("--config=Dolphin.General.GDBPort=55020")
    return command


def run_dolphin(command: list[str], watch: Optional[str] = None, repo: Optional[Path] = None) -> int:
    """Run Dolphin until it closes; with ``watch``, also open research/live_watch.py in its own console."""
    process = subprocess.Popen(command)
    if watch and repo is not None:
        subprocess.Popen(["cmd", "/c", "start", f"live_watch {watch}", "cmd", "/k",
                          sys.executable, str(repo / "research" / "live_watch.py"), watch], cwd=repo)
    return process.wait()


# -- manifests ------------------------------------------------------------------------------------

@dataclass
class Check:
    text: str                      # what the tester looks at; PASS when it is true


@dataclass
class Scenario:
    id: str
    block: str
    title: str
    covers: str                    # which app feature / open question this settles
    steps: list[str]
    checks: list[str]
    build: Optional[Callable] = None        # build(ctx) -> None, edits the work project
    boot: str = "chapter"                   # "chapter" (dev jump), "title" (normal boot), "none" (app only)
    chapter: Optional[int] = None           # ChapterData id for boot="chapter"
    difficulty: str = "Hard"                # Hard: the tutorials never run (tut_data start flags)
    card: Optional[Callable] = None         # card(ctx) -> {gci name: bytes}
    card_from: Optional[str] = None         # start from the card another test left behind
    anim_speed: Optional[float] = 2.0       # None: leave the animation speed alone
    auto_win: dict = field(default_factory=dict)   # {chapter id: turn}: victory when that enemy phase starts
    after: Optional[Callable] = None        # after(card_dir, ctx) -> list[str], run when Dolphin closes
    boots: int = 1
    minutes: int = 3
    region: str = "GFEE01"
    gdb: bool = False
    watch: Optional[str] = None             # research/live_watch.py session started next to Dolphin
    image: Optional[str] = None             # boot="image": a disc image Dolphin boots as is
    optional: bool = False
    app_steps: list[str] = field(default_factory=list)   # done in the app before booting
    notes: list[str] = field(default_factory=list)

    def to_json(self) -> dict:
        return {k: v for k, v in self.__dict__.items() if not callable(v) and k not in ("build", "card", "after")}


def load_manifest(package: Path) -> dict:
    path = package / MANIFEST
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}
