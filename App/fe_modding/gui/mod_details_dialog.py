"""Mod details: the name, author, version and credits a patch carries (see ``patch.py``).
Saved in the project file; whoever applies the patch sees them."""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from ..project import ModProject


class ModDetailsDialog(tk.Toplevel):
    def __init__(self, parent: tk.Misc, project: ModProject, on_saved=None):
        super().__init__(parent)
        self.title("Mod details")
        self.resizable(False, False)
        self.transient(parent.winfo_toplevel())
        self._project, self._on_saved = project, on_saved

        body = ttk.Frame(self, padding=20)
        body.pack(fill="both", expand=True)
        ttk.Label(body, text="Mod details", style="Subtitle.TLabel").pack(anchor="w")
        ttk.Label(body, text="Shown to players when they apply your patch.", style="Muted.TLabel").pack(
            anchor="w", pady=(2, 12))
        self._name_var = self._field(body, "Name", project.name)
        self._author = self._field(body, "Author", project.author)
        self._version = self._field(body, "Version", project.version)
        ttk.Label(body, text="Description", style="Strong.TLabel").pack(anchor="w")
        self._description = tk.Text(body, width=60, height=3, wrap="word")
        self._description.insert("1.0", project.description)
        self._description.pack(fill="x", pady=(2, 8))
        ttk.Label(body, text="Credits (who made or allowed what)", style="Strong.TLabel").pack(anchor="w")
        self._credits = tk.Text(body, width=60, height=4, wrap="word")
        self._credits.insert("1.0", project.credits)
        self._credits.pack(fill="x", pady=(2, 8))

        buttons = ttk.Frame(body)
        buttons.pack(fill="x", pady=(8, 0))
        ttk.Button(buttons, text="Cancel", command=self.destroy).pack(side="right")
        ttk.Button(buttons, text="Save", style="Accent.TButton", command=self._save).pack(side="right", padx=(0, 8))
        self.bind("<Escape>", lambda e: self.destroy())
        self.grab_set()
        self.focus_set()

    @staticmethod
    def _field(parent: tk.Misc, label: str, value: str) -> tk.StringVar:
        ttk.Label(parent, text=label, style="Strong.TLabel").pack(anchor="w")
        var = tk.StringVar(value=value)
        ttk.Entry(parent, textvariable=var, width=62).pack(fill="x", pady=(2, 8))
        return var

    def _save(self) -> None:
        project = self._project
        project.name = self._name_var.get().strip() or project.name
        project.author = self._author.get().strip()
        project.version = self._version.get().strip()
        project.description = self._description.get("1.0", "end").strip()
        project.credits = self._credits.get("1.0", "end").strip()
        project.save()
        if self._on_saved:
            self._on_saved()
        self.destroy()
