"""Run the test suite with every project in the input/output layout.

``python tests/run_overlay.py [unittest discover args]``

Each ``ModProject`` reads its ``extracted/`` folder as the vanilla input and writes edits to
``<project>/output/`` (``game_files.OverlayFiles``). Any write, removal or new folder in an input
tree that does not come from test code itself fails with ``InputWritten``: app code that reaches a
game file without the layer would change the vanilla files every project shares.

Tests that check what landed in ``extracted/`` fail here by design (the edit is in ``output/``);
what matters is the app code this run catches.
"""

from __future__ import annotations

import builtins
import os
import shutil
import sys
import traceback
import unittest
from pathlib import Path

APP = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(APP))

from fe_modding import game_files, project as project_module  # noqa: E402

INPUTS: set[str] = set()


class InputWritten(AssertionError):
    pass


def _under_input(path) -> bool:
    try:
        text = os.path.normcase(os.path.abspath(os.fspath(path)))
    except TypeError:
        return False
    return any(text == root or text.startswith(root + os.sep) for root in INPUTS)


def _from_tests() -> bool:
    """Whether the innermost App frame on the stack is test code (fixtures may write anywhere)."""
    for frame in reversed(traceback.extract_stack()[:-2]):
        name = os.path.normcase(frame.filename)
        if os.path.basename(name) == "run_overlay.py":
            continue
        if name.startswith(os.path.normcase(str(APP / "tests"))):
            return True
        if name.startswith(os.path.normcase(str(APP / "fe_modding"))) or name.startswith(os.path.normcase(str(APP / "tools"))):
            return False
    return True


def _check(path, what: str) -> None:
    if _under_input(path) and not _from_tests():
        raise InputWritten(f"{what} {path} - app code wrote into the vanilla input")


def _wrap(module, name: str, what: str, arg: int = 0):
    original = getattr(module, name)

    def guarded(*args, **kwargs):
        if len(args) > arg:
            _check(args[arg], what)
        return original(*args, **kwargs)

    guarded.__wrapped__ = original
    setattr(module, name, guarded)


_open = builtins.open


def _guarded_open(file, mode="r", *args, **kwargs):
    if any(flag in mode for flag in "wax+"):
        _check(file, f"open({mode!r})")
    return _open(file, mode, *args, **kwargs)


def install() -> None:
    builtins.open = _guarded_open
    import io
    io.open = _guarded_open
    for name in ("remove", "unlink", "rmdir", "mkdir", "makedirs"):
        _wrap(os, name, f"os.{name}")
    _wrap(os, "replace", "os.replace", 1)
    _wrap(os, "rename", "os.rename", 1)
    _wrap(shutil, "rmtree", "shutil.rmtree")
    for name in ("copy", "copy2", "copyfile", "copytree", "move"):
        _wrap(shutil, name, f"shutil.{name}", 1)

    real_files = project_module.ModProject.files

    def files(self):
        if self.layout == project_module.LAYOUT_OVERLAY:
            return real_files.fget(self)    # already in the input/output layout
        if self._files is None:
            INPUTS.add(os.path.normcase(os.path.abspath(self.extracted_dir)))
            self._files = game_files.OverlayFiles(self.extracted_dir, self.directory / "output",
                                                  self.directory / game_files.OVERLAY_FILE)
        return self._files

    project_module.ModProject.files = property(files)


if __name__ == "__main__":
    install()
    argv = [sys.argv[0], "discover", "-s", str(APP / "tests"), *sys.argv[1:]]
    unittest.main(module=None, argv=argv)
