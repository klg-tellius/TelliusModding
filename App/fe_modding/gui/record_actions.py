"""Adding and removing ``FE8Data.bin`` records from the editors.

Both work on the shared :class:`~.fe8_session.Fe8DataSession`: the new or
shortened table stays unsaved like any other edit. A new record starts
empty or as a copy of an existing one; a record something still names (see
:mod:`fe_modding.fe8_references`) cannot be removed, and removing a
character, class or item warns that saves made before hold its old number.
"""

from __future__ import annotations

import tkinter as tk
from tkinter import messagebox, ttk
from typing import Optional

from .. import fe8_references
from ..formats import fe8data
from ..project import ModProject
from .fe8_session import Fe8DataSession

NOUNS = {"character": "character", "class": "class", "item": "item", "chapter": "chapter record"}
EMPTY = "(empty record)"


class NewRecordDialog(tk.Toplevel):
    """Ask for a new record's ID and the record it starts as a copy of.
    ``result`` is ``(new_id or None, copy_from index or None)``."""

    def __init__(self, parent: tk.Misc, kind: str, templates: list[str], selected: Optional[int] = None):
        super().__init__(parent)
        self.title(f"New {NOUNS[kind]}")
        self.transient(parent)
        self.result: Optional[tuple[Optional[str], Optional[int]]] = None
        self._kind = kind
        self._templates = templates
        body = ttk.Frame(self, padding=12)
        body.pack(fill="both", expand=True)
        row = 0
        self._id = tk.StringVar()
        if kind in fe8data.RECORD_ID_FIELDS:
            prefix = fe8data.RECORD_ID_FIELDS[kind][1]
            self._id.set(prefix)
            ttk.Label(body, text="ID").grid(row=row, column=0, sticky="w", pady=2)
            entry = ttk.Entry(body, textvariable=self._id, width=34)
            entry.grid(row=row, column=1, sticky="we", pady=2, padx=(8, 0))
            entry.focus_set()
            entry.icursor("end")
            row += 1
        self._template = tk.StringVar(value=templates[selected] if selected is not None else EMPTY)
        ttk.Label(body, text="Start as a copy of").grid(row=row, column=0, sticky="w", pady=2)
        ttk.Combobox(body, textvariable=self._template, values=[EMPTY] + templates, width=44,
                     state="readonly").grid(row=row, column=1, sticky="we", pady=2, padx=(8, 0))
        row += 1
        ttk.Label(body, style="Muted.TLabel", wraplength=420, justify="left", text=(
            "The record is added at the end of the table, so the numbers saves hold for the others stay valid. "
            "Its name, description and model keys are copied too: give it its own afterwards.")).grid(
            row=row, column=0, columnspan=2, sticky="w", pady=(8, 0))
        row += 1
        buttons = ttk.Frame(body)
        buttons.grid(row=row, column=0, columnspan=2, sticky="e", pady=(10, 0))
        ttk.Button(buttons, text="Create", style="Accent.TButton", command=self._ok).pack(side="left")
        ttk.Button(buttons, text="Cancel", command=self.destroy).pack(side="left", padx=(6, 0))
        body.columnconfigure(1, weight=1)
        self.bind("<Return>", lambda e: self._ok())
        self.bind("<Escape>", lambda e: self.destroy())
        self.grab_set()

    def _ok(self) -> None:
        template = self._template.get()
        copy_from = self._templates.index(template) if template in self._templates else None
        new_id = self._id.get().strip() if self._kind in fe8data.RECORD_ID_FIELDS else None
        self.result = (new_id, copy_from)
        self.destroy()


def add_record(parent: tk.Misc, session: Fe8DataSession, kind: str, templates: list[str],
               selected: Optional[int] = None, source: object = None) -> Optional[int]:
    """Ask for and append a record; returns its index, or None when
    cancelled or refused (the error is shown)."""
    dialog = NewRecordDialog(parent, kind, templates, selected)
    parent.wait_window(dialog)
    if dialog.result is None:
        return None
    new_id, copy_from = dialog.result
    try:
        data, index = fe8data.add_record(session.data, kind, new_id, copy_from)
    except ValueError as exc:
        messagebox.showerror(f"Could not add the {NOUNS[kind]}", str(exc), parent=parent)
        return None
    session.data = data
    session.changed(source)
    return index


def remove_record(parent: tk.Misc, session: Fe8DataSession, project: Optional[ModProject], kind: str,
                  index: int, label: str, source: object = None) -> bool:
    """Remove a record after checking nothing names it and confirming;
    returns whether it was removed."""
    data = session.data
    try:
        refs = fe8_references.record_references(project, data, kind, index)
    except (ValueError, OSError) as exc:
        messagebox.showerror("Could not check the references", str(exc), parent=parent)
        return False
    if refs:
        shown = "\n".join(f"• {r}" for r in refs[:14])
        more = f"\n… and {len(refs) - 14} more" if len(refs) > 14 else ""
        messagebox.showerror(
            f"{label} is still used",
            f"{label} cannot be removed while these name it:\n\n{shown}{more}\n\n"
            "Point them at another record first.", parent=parent)
        return False
    count = fe8data.table_count(data, kind)
    text = f"Remove {label} from FE8Data.bin?"
    if index < count - 1:
        text += f"\n\nThe {count - 1 - index} records after it move up one number."
        if kind in fe8data.SAVED_BY_NUMBER:
            text += (" Saves hold characters, classes and items by number, so saves made before this change "
                     "will load other records: start a new game with the modded disc.")
    if kind == "chapter":
        text += "\n\nScripts that change to this chapter's id will find no chapter."
    if not messagebox.askyesno(f"Remove {NOUNS[kind]}?", text, icon="warning", parent=parent):
        return False
    try:
        session.data = fe8data.remove_record(data, kind, index)
    except ValueError as exc:
        messagebox.showerror(f"Could not remove the {NOUNS[kind]}", str(exc), parent=parent)
        return False
    session.changed(source)
    return True
