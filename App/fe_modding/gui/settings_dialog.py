"""Settings: app-wide preferences, kept in ``~/.tellius_modding/settings.json``
(see ``config.py``). Changes apply at once; there is nothing to confirm."""

from __future__ import annotations

import queue
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from .. import blender, emulator
from ..config import load_setting, save_setting
from . import theme


class SettingsDialog(tk.Toplevel):
    def __init__(self, parent: tk.Misc):
        super().__init__(parent)
        self.title("Settings")
        self.resizable(False, False)
        self.transient(parent.winfo_toplevel())
        self._main_window = parent.winfo_toplevel()

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

        modeling = ttk.LabelFrame(body, text="3D tools", padding=(12, 8))
        modeling.pack(fill="x", pady=(12, 0))
        ttk.Label(modeling, text="Blender location (blender.exe)").pack(anchor="w")
        blender_row = ttk.Frame(modeling)
        blender_row.pack(fill="x", pady=2)
        self._blender = tk.StringVar(value=load_setting(blender.SETTING_KEY) or "")
        blender_entry = ttk.Entry(blender_row, textvariable=self._blender, width=48)
        blender_entry.pack(side="left")
        blender_entry.bind("<FocusOut>", lambda e: self._save_blender())
        ttk.Button(blender_row, text="Browse…", command=self._browse_blender).pack(side="left", padx=(6, 0))
        found_blender = blender.configured_blender()
        ttk.Label(
            modeling,
            text=f"Found: {found_blender}" if found_blender else "Not found. Required only for self-contained .blend export.",
            style="Muted.TLabel",
        ).pack(anchor="w")
        addon_row = ttk.Frame(modeling)
        addon_row.pack(fill="x", pady=(8, 0))
        self._addon_button = ttk.Button(addon_row, text="Install the Tellius Terrain add-on",
                                        command=self._install_addon)
        self._addon_button.pack(side="left")
        self._addon_status = ttk.Label(
            modeling,
            text="Adds the terrain sculpt & paint panel (3D View sidebar, Tellius tab) to your Blender. "
                 "Install it again after updating the app.",
            style="Muted.TLabel", wraplength=420, justify="left",
        )
        self._addon_status.pack(anchor="w")

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

    def _browse_blender(self) -> None:
        path = filedialog.askopenfilename(
            parent=self,
            title="Choose blender.exe",
            filetypes=[("Blender", "blender.exe"), ("All files", "*.*")],
        )
        if path:
            self._blender.set(path)
            self._save_blender()

    def _save_blender(self) -> None:
        save_setting(blender.SETTING_KEY, self._blender.get().strip())

    def _install_addon(self) -> None:
        """Install the add-on with Blender in the background (it saves Blender's preferences)."""
        self._save_blender()
        self._addon_button.state(["disabled"])
        self._addon_status.config(text="Installing… Blender is running in the background.")
        results: "queue.Queue" = queue.Queue()

        def worker() -> None:
            try:
                results.put(("ok", blender.install_addon()))
            except Exception as exc:  # noqa: BLE001
                results.put(("error", str(exc)))

        def poll() -> None:
            try:
                status, payload = results.get_nowait()
            except queue.Empty:
                if self.winfo_exists():
                    self.after(150, poll)
                return
            if not self.winfo_exists():
                return
            self._addon_button.state(["!disabled"])
            if status == "ok":
                self._addon_status.config(text=f"Installed and enabled in {payload}. Restart Blender if it is open.")
            else:
                self._addon_status.config(text="The add-on was not installed.")
                messagebox.showerror("Tellius Terrain add-on", payload, parent=self)

        threading.Thread(target=worker, daemon=True).start()
        self.after(150, poll)

    def _apply_theme(self) -> None:
        theme.set_mode(self._main_window, self._theme.get())
