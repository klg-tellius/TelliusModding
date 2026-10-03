"""Settings: app-wide preferences, kept in ``~/.tellius_modding/settings.json``
(see ``config.py``). Changes apply at once; there is nothing to confirm."""

from __future__ import annotations

import tkinter as tk
from tkinter import filedialog, ttk

from .. import emulator
from ..config import load_setting, save_setting
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

        play = ttk.LabelFrame(body, text="Emulator", padding=(12, 8))
        play.pack(fill="x", pady=(12, 0))
        ttk.Label(play, text="Dolphin location (Dolphin.exe)").pack(anchor="w")
        row = ttk.Frame(play)
        row.pack(fill="x", pady=2)
        self._dolphin = tk.StringVar(value=load_setting(emulator.SETTING_KEY) or "")
        entry = ttk.Entry(row, textvariable=self._dolphin, width=48)
        entry.pack(side="left")
        entry.bind("<FocusOut>", lambda e: self._save_dolphin())
        ttk.Button(row, text="Browse…", command=self._browse_dolphin).pack(side="left", padx=(6, 0))
        found = emulator.configured_dolphin()
        ttk.Label(play, text=f"Found: {found}" if found else "Not found. Leave empty to search the usual folders.",
                  style="Muted.TLabel").pack(anchor="w")

        ttk.Button(body, text="Close", command=self.destroy).pack(anchor="e", pady=(16, 0))
        self.bind("<Escape>", lambda e: self.destroy())
        self.grab_set()
        self.focus_set()

    def _browse_dolphin(self) -> None:
        path = filedialog.askopenfilename(parent=self, title="Choose Dolphin.exe",
                                          filetypes=[("Dolphin", "Dolphin.exe"), ("All files", "*.*")])
        if path:
            self._dolphin.set(path)
            self._save_dolphin()

    def _save_dolphin(self) -> None:
        save_setting(emulator.SETTING_KEY, self._dolphin.get().strip())

    def _apply_theme(self) -> None:
        theme.set_mode(self._root, self._theme.get())
