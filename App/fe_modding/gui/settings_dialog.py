"""Settings: app-wide preferences, kept in ``~/.tellius_modding/settings.json``
(see ``config.py``). Changes apply at once; there is nothing to confirm."""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from . import theme


class SettingsDialog(tk.Toplevel):
    def __init__(self, parent: tk.Misc):
        super().__init__(parent)
        self.title("Settings")
        self.resizable(False, False)
        self.transient(parent.winfo_toplevel())
        self._root = parent.winfo_toplevel()

        body = ttk.Frame(self, padding=20)
        body.pack(fill="both", expand=True)
        ttk.Label(body, text="Settings", style="Subtitle.TLabel").pack(anchor="w", pady=(0, 14))

        appearance = ttk.LabelFrame(body, text="Appearance", padding=(12, 8))
        appearance.pack(fill="x")
        ttk.Label(appearance, text="Theme").pack(anchor="w")
        self._theme = tk.StringVar(value=theme.mode())
        for value, label in (("dark", "Dark"), ("light", "Light")):
            ttk.Radiobutton(appearance, text=label, value=value, variable=self._theme,
                            command=self._apply_theme).pack(anchor="w", padx=(8, 0), pady=2)

        ttk.Button(body, text="Close", command=self.destroy).pack(anchor="e", pady=(16, 0))
        self.bind("<Escape>", lambda e: self.destroy())
        self.grab_set()
        self.focus_set()

    def _apply_theme(self) -> None:
        theme.set_mode(self._root, self._theme.get())
