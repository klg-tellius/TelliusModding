"""Tellius Patcher: the small program players run to apply a mod's patch.

A mod author ships ``TelliusPatcher.exe`` with their ``.tpatch``; the player
opens it (or drops the patch on it), picks their own copy of the game and
gets a playable disc image. It is the Apply-a-patch window of the full app
(:class:`.gui.patch_dialog.ApplyPatchDialog`) on its own, with no project.
A patch named on the command line, else the only ``.tpatch`` next to the
program, is filled in.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Optional

from .patch import PATCH_EXTENSION


def program_dir() -> Path:
    """The folder of the running program (the .exe once frozen)."""
    return Path(sys.executable if getattr(sys, "frozen", False) else sys.argv[0]).resolve().parent


def find_patch(argv: list[str], folder: Optional[Path] = None) -> str:
    """The patch to fill in: the first argument, else the only patch in ``folder``."""
    if argv and argv[0].lower().endswith(PATCH_EXTENSION):
        return argv[0]
    folder = folder or program_dir()
    found = sorted(folder.glob(f"*{PATCH_EXTENSION}")) if folder.is_dir() else []
    return str(found[0]) if len(found) == 1 else ""


def self_test(report: str) -> int:
    """The release build's check that the frozen program starts: the patch code imports."""
    from . import patch, tools  # noqa: F401 - importing them is the test

    Path(report).write_text(json.dumps({"ok": True, "program": "TelliusPatcher"}) + "\n", encoding="utf-8")
    return 0


def main(argv: Optional[list[str]] = None) -> None:
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) == 2 and argv[0] == "--self-test":
        raise SystemExit(self_test(argv[1]))
    import tkinter as tk

    from .gui import theme
    from .gui.patch_dialog import ApplyPatchDialog

    root = tk.Tk()
    theme.setup(root)
    root.withdraw()
    try:  # sv-ttk colours plain Tk windows from a <<ThemeChanged>> binding that a fresh root may not get yet
        root.tk.call("configure_colors")
    except tk.TclError:
        pass
    dialog = ApplyPatchDialog(root, patch_path=find_patch(argv), standalone=True)
    dialog.bind("<Destroy>", lambda e: root.destroy() if e.widget is dialog else None)
    root.mainloop()
