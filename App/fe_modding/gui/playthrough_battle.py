"""Plays a playthrough fight with the battle models (:class:`.battle_window.BattleWindow`).

The playthrough hands over the fight's :class:`battle_sim.BattleLog`; the
fight plays once, then ``on_done`` runs (also when the window is closed or
Skip is pressed).
"""

from __future__ import annotations

import tkinter as tk
from pathlib import Path
from tkinter import ttk
from typing import Callable, Optional

from .battle_window import BattleWindow


class BattleAnimationWindow(BattleWindow):
    def __init__(self, parent: tk.Misc, files: Path, rules, fe8):
        super().__init__(parent, files, rules, fe8)
        self._on_done: Optional[Callable[[], None]] = None
        self._finish_job: Optional[str] = None
        self.scenery = tk.StringVar(value="(none)")
        ttk.Button(self.top, text="Skip", command=self._finish).pack(side="right")
        self._scenery_box = ttk.Combobox(self.top, textvariable=self.scenery, state="readonly", width=24)
        self._scenery_box.pack(side="right", padx=(4, 12))
        ttk.Label(self.top, text="Scenery").pack(side="right")
        self.view.on_finished = lambda: self._finish_later(600)

    def play(self, log, distance: int, on_done: Callable[[], None]) -> None:  # type: ignore[override]
        """Play ``log``; ``on_done()`` runs once it has finished or was skipped."""
        self._cancel_finish()
        self._finish_pending()
        self._on_done = on_done
        self._scenery_box["values"] = ["(none)"] + self.sceneries()
        scenery = self.scenery.get()
        if not super().play(log, distance, None if scenery.startswith("(") else scenery):
            self._finish_later(1200)

    def _finish_later(self, ms: int) -> None:
        self._cancel_finish()
        self._finish_job = self.after(ms, self._finish)

    def _cancel_finish(self) -> None:
        """Drop a scheduled close, so it can't end the next battle early."""
        if self._finish_job is not None:
            self.after_cancel(self._finish_job)
            self._finish_job = None

    def _finish_pending(self) -> None:
        if self._on_done is not None:
            done, self._on_done = self._on_done, None
            done()

    def _finish(self) -> None:
        self._cancel_finish()
        super().close()
        self._finish_pending()

    def close(self) -> None:
        self._finish()
