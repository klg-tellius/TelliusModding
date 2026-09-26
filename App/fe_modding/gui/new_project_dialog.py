"""Modal dialog for creating a new mod project."""

from __future__ import annotations

import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import Optional

from ..exceptions import ProjectError
from ..games import Game, all_games
from ..project import ModProject, sanitize_folder_name


class NewProjectDialog(tk.Toplevel):
    """Collects game, name, and target location, then creates the project.

    On success, ``self.result`` holds the created ModProject; otherwise None.
    """

    def __init__(self, parent: tk.Misc):
        super().__init__(parent)
        self.title("New Project")
        self.resizable(False, False)
        self.transient(parent)
        self.result: Optional[ModProject] = None

        self._game_var = tk.StringVar(value=Game.PATH_OF_RADIANCE.value)
        self._name_var = tk.StringVar(value="My Fire Emblem Mod")
        self._location_var = tk.StringVar(value=str(Path.home()))
        self._name_var.trace_add("write", lambda *_: self._update_preview())
        self._location_var.trace_add("write", lambda *_: self._update_preview())

        self._build_widgets()
        self._update_preview()

        self.protocol("WM_DELETE_WINDOW", self._on_cancel)
        self.grab_set()
        self.wait_visibility()
        self.focus_set()

    def _build_widgets(self) -> None:
        pad = {"padx": 12, "pady": 6}
        frame = ttk.Frame(self)
        frame.pack(fill="both", expand=True)

        # Game selection
        game_frame = ttk.LabelFrame(frame, text="Game")
        game_frame.pack(fill="x", **pad)
        for info in all_games():
            ttk.Radiobutton(
                game_frame,
                text=f"{info.display_name}  ({info.platform})",
                value=info.id.value,
                variable=self._game_var,
            ).pack(anchor="w", padx=8, pady=2)

        # Project name
        name_frame = ttk.Frame(frame)
        name_frame.pack(fill="x", **pad)
        ttk.Label(name_frame, text="Project name:").pack(anchor="w")
        ttk.Entry(name_frame, textvariable=self._name_var).pack(fill="x")

        # Location
        loc_frame = ttk.Frame(frame)
        loc_frame.pack(fill="x", **pad)
        ttk.Label(loc_frame, text="Create in:").pack(anchor="w")
        loc_row = ttk.Frame(loc_frame)
        loc_row.pack(fill="x")
        ttk.Entry(loc_row, textvariable=self._location_var).pack(side="left", fill="x", expand=True)
        ttk.Button(loc_row, text="Browse...", command=self._browse).pack(side="left", padx=(6, 0))

        self._preview_label = ttk.Label(frame, text="", style="Muted.TLabel")
        self._preview_label.pack(fill="x", padx=12, pady=(0, 6))

        # Buttons
        button_row = ttk.Frame(frame)
        button_row.pack(fill="x", padx=12, pady=(0, 12))
        ttk.Button(button_row, text="Cancel", command=self._on_cancel).pack(side="right")
        ttk.Button(button_row, text="Create Project", command=self._on_create).pack(side="right", padx=(0, 6))

    def _browse(self) -> None:
        chosen = filedialog.askdirectory(
            title="Choose where to create the project",
            initialdir=self._location_var.get() or str(Path.home()),
            parent=self,
        )
        if chosen:
            self._location_var.set(chosen)

    def _update_preview(self) -> None:
        location = self._location_var.get().strip()
        name = self._name_var.get().strip()
        try:
            folder = sanitize_folder_name(name) if name else "<name>"
        except ProjectError:
            folder = "<invalid name>"
        self._preview_label.config(text=f"Project folder: {location}\\{folder}" if location else "")

    def _on_create(self) -> None:
        name = self._name_var.get().strip()
        location = self._location_var.get().strip()

        if not name:
            messagebox.showerror("Missing name", "Please enter a project name.", parent=self)
            return
        if not location:
            messagebox.showerror("Missing location", "Please choose a folder to create the project in.", parent=self)
            return

        try:
            project = ModProject.create(
                parent_directory=location,
                name=name,
                game=Game(self._game_var.get()),
            )
        except ProjectError as exc:
            messagebox.showerror("Could not create project", str(exc), parent=self)
            return

        self.result = project
        self.destroy()

    def _on_cancel(self) -> None:
        self.result = None
        self.destroy()
