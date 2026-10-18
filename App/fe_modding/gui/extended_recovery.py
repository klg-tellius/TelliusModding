"""Resolve an interrupted flag transaction before opening project editors."""
import json
import os
import tkinter as tk
from tkinter import ttk, messagebox

from ..project_transaction import JOURNAL, recover
from ..script_sources import CompileContext


def resolve_recovery(parent, project):
    journal = project.directory / JOURNAL
    if not journal.exists():
        return True
    completed = False
    try:
        completed = json.loads((journal / "manifest.json").read_text(encoding="utf-8")).get("state") == "complete"
    except (OSError, ValueError, AttributeError):
        pass
    dialog = tk.Toplevel(parent)
    dialog.title("Recover project installation")
    dialog.transient(parent)
    dialog.resizable(False, False)
    result = [False]
    frame = ttk.Frame(dialog, padding=18)
    frame.pack(fill="both", expand=True)
    text = ("The installation finished, but its recovery files still need cleanup."
            if completed else "An installation was interrupted. Recover the previous files before opening this project.")
    ttk.Label(frame, text=text, wraplength=450).pack(anchor="w", pady=(0, 12))
    ttk.Label(frame, text="Close any other window or process writing to this project first.",
              wraplength=450).pack(anchor="w", pady=(0, 12))

    def restore():
        try:
            recover(project.directory)
        except (OSError, ValueError, KeyError, TypeError, RuntimeError) as exc:
            messagebox.showerror("Recovery could not finish", f"{exc}\n\nRecovery files have been retained.", parent=dialog)
            return
        CompileContext._cache.clear()
        result[0] = True
        dialog.destroy()

    def open_folder():
        try:
            os.startfile(str(journal))
        except (OSError, AttributeError) as exc:
            messagebox.showerror("Could not open recovery folder", f"{journal}\n\n{exc}", parent=dialog)

    buttons = ttk.Frame(frame)
    buttons.pack(fill="x")
    ttk.Button(buttons, text="Finish cleanup" if completed else "Recover previous files", command=restore).pack(side="left")
    ttk.Button(buttons, text="Open recovery folder", command=open_folder).pack(side="left", padx=8)
    ttk.Button(buttons, text="Cancel", command=dialog.destroy).pack(side="right")
    dialog.protocol("WM_DELETE_WINDOW", dialog.destroy)
    dialog.grab_set()
    parent.wait_window(dialog)
    return result[0]
