"""Run a built disc image in the Dolphin emulator.

Dolphin plays the GameCube image the project builds (CISO). It is found from the
``dolphin_path`` setting, then the usual install folders and the ``PATH``. Nothing here is
Tk code; the Disc & Patch page and the Settings dialog use it.

A chapter can also be played without building: Dolphin boots an extracted disc tree when given
its ``sys/main.dol`` (``DiscIO/DirectoryBlob.cpp``). :func:`prepare_chapter_run` makes such a
tree in ``build/dolphin_run``: copies of ``extracted/sys`` with a ``main.dol`` that boots into the
chosen chapter (``game_code.chapter_jump``), and ``files`` as a directory junction to
``extracted/files``, so the project's own files are read in place and its ``main.dol`` is
never touched.
"""

from __future__ import annotations

import os
import shutil
import struct
import subprocess
import sys
from pathlib import Path
from typing import Callable, Optional

from .config import load_setting
from .exceptions import ModdingError
from .game_profile import PLAY
from .games import Game, detect_from_extracted, profile

SETTING_KEY = "dolphin_path"
EXECUTABLE_NAMES = ("Dolphin.exe", "Dolphin", "dolphin-emu")


class EmulatorError(ModdingError):
    """Dolphin is missing or could not be started."""


def candidate_paths(environ=None) -> list[Path]:
    """Where Dolphin is usually installed on Windows (the portable/zip build has no installer)."""
    env = os.environ if environ is None else environ
    roots = [env.get(name) for name in ("ProgramFiles", "ProgramFiles(x86)", "LOCALAPPDATA", "USERPROFILE")]
    found = []
    for root in filter(None, roots):
        base = Path(root)
        for folder in ("Dolphin-x64", "Dolphin", "Dolphin Emulator", "Programs/Dolphin Emulator"):
            found.append(base / folder / "Dolphin.exe")
    return found


def find_dolphin(configured: Optional[str] = None, *, environ=None,
                 is_file: Callable[[Path], bool] = Path.is_file,
                 which: Callable[[str], Optional[str]] = shutil.which) -> Optional[Path]:
    """The Dolphin executable: the configured path if it exists, else an install folder, else the PATH."""
    if configured:
        path = Path(configured)
        return path if is_file(path) else None
    for path in candidate_paths(environ):
        if is_file(path):
            return path
    for name in EXECUTABLE_NAMES:
        hit = which(name)
        if hit:
            return Path(hit)
    return None


def configured_dolphin() -> Optional[Path]:
    """:func:`find_dolphin` with the saved setting."""
    return find_dolphin(load_setting(SETTING_KEY) or None)


def command(dolphin: Path | str, image: Path | str, *, batch: bool = True,
            save_state: Optional[Path | str] = None) -> list[str]:
    """The command line: ``--exec`` runs the image; ``--batch`` closes Dolphin with the game
    (no game list window); ``--save_state`` loads a state once the game starts."""
    args = [str(dolphin), "--exec=" + str(image)]
    if batch:
        args.append("--batch")
    if save_state:
        args.append("--save_state=" + str(save_state))
    return args


def launch(image: Path | str, dolphin: Optional[Path | str] = None, *, batch: bool = True,
           save_state: Optional[Path | str] = None, popen=subprocess.Popen) -> subprocess.Popen:
    """Start Dolphin on ``image`` and return at once. ``dolphin`` defaults to the configured/found one."""
    image = Path(image)
    if not image.is_file():
        raise EmulatorError(f"There is no disc image at {image}; build the project first.")
    dolphin = Path(dolphin) if dolphin else configured_dolphin()
    if dolphin is None:
        raise EmulatorError("Dolphin was not found. Set its location in Settings > Preferences.")
    if not Path(dolphin).is_file():
        raise EmulatorError(f"Dolphin was not found at {dolphin}. Set its location in Settings > Preferences.")
    try:
        return popen(command(dolphin, image, batch=batch, save_state=save_state))
    except OSError as exc:
        raise EmulatorError(f"Dolphin could not be started: {exc}") from exc


RUN_FOLDER = "dolphin_run"


def _is_link(path: Path) -> bool:
    return path.is_symlink() or (hasattr(path, "is_junction") and path.is_junction())


def _link_directory(link: Path, target: Path) -> None:
    """Point ``link`` at the directory ``target``: a junction on Windows (no admin rights
    needed), a symbolic link elsewhere. An existing link is replaced; a real folder is not."""
    if _is_link(link):
        current = os.readlink(link).removeprefix("\\\\?\\")
        if Path(current).resolve() == target.resolve():
            return
        if sys.platform == "win32":
            os.rmdir(link)              # removes the junction only, not what it points to
        else:
            os.unlink(link)
    elif link.exists():
        raise EmulatorError(f"{link} is a real folder, not a link; move it away first.")
    if sys.platform == "win32":
        import _winapi
        _winapi.CreateJunction(str(target.resolve()), str(link))
    else:
        os.symlink(target.resolve(), link, target_is_directory=True)


def chapter_position(fe8data: bytes, chapter_id: int) -> int:
    """Position of chapter ``chapter_id``'s record in ``ChapterData`` (what the game's chapter
    select passes, rather than the id)."""
    from .formats import fe8data as fe8

    try:
        records = fe8.read_chapter_data(fe8data)
    except (ValueError, IndexError, struct.error) as exc:
        raise EmulatorError(f"FE8Data.bin could not be read ({exc}).") from exc
    for record in records:
        if record.chapter_id == chapter_id:
            return record.index
    raise EmulatorError(f"Chapter {chapter_id:02d} has no ChapterData record.")


def prepare_chapter_run(extracted_dir: Path | str, run_dir: Path | str, chapter_id: int, difficulty: int) -> Path:
    """Make ``run_dir`` a disc tree that boots into chapter ``chapter_id`` (a ``ChapterData`` id)
    on ``difficulty`` (a ``chapter_jump.DIFFICULTIES`` value) with a fresh army; returns its
    ``sys/main.dol`` for Dolphin. ``FE8Data.bin`` is read from disk, as the game will read it
    (copy it into ``system.cmp`` first: ``ModProject.sync_system_archive``)."""
    from .game_code import chapter_jump, entries  # noqa: F401  (entries: the whole catalog)
    from .game_code.catalog import Session
    from .game_code.dol import Dol, DolError
    from .game_code.versions import identify, read_boot_code

    extracted_dir, run_dir = Path(extracted_dir), Path(run_dir)
    source_sys, files = extracted_dir / "sys", extracted_dir / "files"
    if not (source_sys / "main.dol").is_file() or not files.is_dir():
        raise EmulatorError(f"{extracted_dir} has no sys/main.dol or files folder; extract the disc first.")
    detected = detect_from_extracted(extracted_dir)
    if detected is not None and not profile(detected).supports(PLAY):
        raise EmulatorError(profile(detected).unavailable(PLAY))
    position = chapter_position(profile(detected or Game.PATH_OF_RADIANCE).path(files, "game_data").read_bytes(),
                                chapter_id)
    dol = Dol.open(source_sys / "main.dol")
    version = identify(dol, read_boot_code(extracted_dir)).version
    if version is None:
        raise EmulatorError("This main.dol is not a supported Path of Radiance build.")
    try:
        chapter_jump.install(Session(dol, version), position, difficulty)
    except (DolError, ValueError) as exc:
        raise EmulatorError(f"Could not patch main.dol for the jump: {exc}") from exc

    sys_dir = run_dir / "sys"
    sys_dir.mkdir(parents=True, exist_ok=True)
    for item in source_sys.iterdir():
        if item.is_file() and item.name != "main.dol":
            shutil.copyfile(item, sys_dir / item.name)
    (sys_dir / "main.dol").write_bytes(bytes(dol.data))
    _link_directory(run_dir / "files", files)
    return sys_dir / "main.dol"
