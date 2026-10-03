"""Run a built disc image in the Dolphin emulator.

Dolphin plays the GameCube image the project builds (CISO). It is found from the
``dolphin_path`` setting, then the usual install folders and the ``PATH``. Nothing here is
Tk code; the Disc & Patch page and the Settings dialog use it.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path
from typing import Callable, Optional

from .config import load_setting
from .exceptions import ModdingError

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
