"""pytest only (the suite itself is unittest): settings for parallel runs (``-n auto``).

Several workers creating a ``tkinter.Tk`` at the same moment on Windows sometimes fail Tk's
start-up ("This probably means that tk wasn't installed properly"). The failure passes on a
retry, so ``Tk()`` is retried a few times here before the error reaches a test.
"""

from __future__ import annotations

import time
import tkinter

_tk_init = tkinter.Tk.__init__


def _patient_tk_init(self, *args, **kwargs):
    for attempt in range(5):
        try:
            return _tk_init(self, *args, **kwargs)
        except tkinter.TclError as exc:
            if attempt == 4 or "installed properly" not in str(exc):
                raise
            time.sleep(0.2 * (attempt + 1))


tkinter.Tk.__init__ = _patient_tk_init
