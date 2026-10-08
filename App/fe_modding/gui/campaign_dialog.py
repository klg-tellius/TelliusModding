"""Dialogs for starting a campaign (see ``campaign.py``): several chapters and a starter cast in one
step, and the story order of the added chapters."""

from __future__ import annotations

import tkinter as tk
from tkinter import messagebox, ttk

from .. import campaign


class NewCampaignDialog(tk.Toplevel):
    """Rows of chapters (title, the chapter to copy, empty units) and characters (ID, name, the character
    to copy). ``result`` is ``(chapter specs, character specs, after)`` or None."""

    def __init__(self, parent: tk.Misc, templates: dict, after_choices: dict, characters: dict, default_after):
        """``characters`` maps a shown label (``"Oscar  (PID_OSCAR)"``) to the PID; shown sorted."""
        super().__init__(parent)
        self.title("New campaign")
        self.transient(parent.winfo_toplevel())
        self.result = None
        self._templates, self._after_choices = templates, after_choices
        self._characters = dict(sorted(characters.items(), key=lambda kv: kv[0].casefold()))
        self._chapter_rows: list = []
        self._cast_rows: list = []

        frame = ttk.Frame(self, padding=16)
        frame.pack(fill="both", expand=True)
        ttk.Label(frame, justify="left", text=(
            "Adds the chapters below in this order, each leading to the next, and the characters.\n"
            "Every chapter is a copy of a chapter you choose (its maps, script, dialogue, shops);\n"
            "tick 'Empty' to remove the copied units but the player's army. Edit everything afterwards\n"
            "on its own page.")
        ).pack(anchor="w", pady=(0, 10))

        top = ttk.Frame(frame)
        top.pack(fill="x")
        ttk.Label(top, text="Played after:").pack(side="left")
        self._after_var = tk.StringVar(value=next((k for k, v in after_choices.items() if v == default_after),
                                                  next(iter(after_choices))))
        ttk.Combobox(top, textvariable=self._after_var, values=list(after_choices), state="readonly",
                     width=44).pack(side="left", padx=(6, 0))

        ttk.Label(frame, text="Chapters", style="Strong.TLabel").pack(anchor="w", pady=(12, 2))
        self._chapters = ttk.Frame(frame)
        self._chapters.pack(fill="x")
        ttk.Button(frame, text="Add chapter row", command=self._add_chapter_row).pack(anchor="w", pady=(4, 0))

        ttk.Label(frame, text="Characters (optional)", style="Strong.TLabel").pack(anchor="w", pady=(12, 0))
        ttk.Label(frame, style="Muted.TLabel", justify="left", text=(
            "Each new character is a copy of an existing one (class, stats, portrait, models).\n"
            "ID: the character's internal ID, PID_ then capital letters, digits or _.\n"
            "Name: the name shown in game; empty keeps the copied character's name.")).pack(anchor="w", pady=(0, 4))
        header = ttk.Frame(frame)
        header.pack(fill="x")
        for text, width, pad in (("ID", 18, 0), ("Name in game", 18, 4), ("Copy of", 24, 6)):
            ttk.Label(header, text=text, width=width, style="Muted.TLabel").pack(side="left", padx=(pad, 0))
        self._cast = ttk.Frame(frame)
        self._cast.pack(fill="x")
        ttk.Button(frame, text="Add character row", command=self._add_cast_row).pack(anchor="w", pady=(4, 0))

        buttons = ttk.Frame(frame)
        buttons.pack(fill="x", pady=(14, 0))
        ttk.Button(buttons, text="Cancel", command=self.destroy).pack(side="right")
        ttk.Button(buttons, text="Create campaign", style="Accent.TButton", command=self._ok).pack(
            side="right", padx=(0, 6))
        self._add_chapter_row()
        self.grab_set()

    # -- rows ---------------------------------------------------------------------------------
    def _add_chapter_row(self) -> None:
        row = ttk.Frame(self._chapters)
        row.pack(fill="x", pady=1)
        n = len(self._chapter_rows) + 1
        title = tk.StringVar(value=f"New chapter {n}")
        template = tk.StringVar(value=next(iter(self._templates)))
        blank = tk.BooleanVar(value=False)
        ttk.Entry(row, textvariable=title, width=26).pack(side="left")
        ttk.Label(row, text="copy of").pack(side="left", padx=(6, 2))
        ttk.Combobox(row, textvariable=template, values=list(self._templates), state="readonly",
                     width=34).pack(side="left")
        ttk.Checkbutton(row, text="Empty", variable=blank).pack(side="left", padx=(6, 0))
        entry = (row, title, template, blank)
        ttk.Button(row, text="✕", width=3, command=lambda: self._remove(self._chapter_rows, entry)).pack(
            side="left", padx=(6, 0))
        self._chapter_rows.append(entry)

    def _add_cast_row(self) -> None:
        row = ttk.Frame(self._cast)
        row.pack(fill="x", pady=1)
        pid, name = tk.StringVar(value="PID_NEW"), tk.StringVar()
        template = tk.StringVar(value=next(iter(self._characters), ""))
        ttk.Entry(row, textvariable=pid, width=18).pack(side="left")
        ttk.Entry(row, textvariable=name, width=18).pack(side="left", padx=(4, 0))
        ttk.Combobox(row, textvariable=template, values=list(self._characters), state="readonly",
                     width=30).pack(side="left")
        entry = (row, pid, name, template)
        ttk.Button(row, text="✕", width=3, command=lambda: self._remove(self._cast_rows, entry)).pack(
            side="left", padx=(6, 0))
        self._cast_rows.append(entry)

    @staticmethod
    def _remove(rows: list, entry) -> None:
        entry[0].destroy()
        rows.remove(entry)

    def _ok(self) -> None:
        chapters = [campaign.ChapterSpec(title.get().strip(), self._templates[template.get()], blank.get())
                    for _row, title, template, blank in self._chapter_rows]
        cast = [campaign.CharacterSpec(pid.get().strip(), self._characters[template.get()], name.get().strip())
                for _row, pid, name, template in self._cast_rows]
        if not chapters and not cast:
            messagebox.showerror("New campaign", "Add at least one chapter or character.", parent=self)
            return
        self.result = (chapters, cast, self._after_choices[self._after_var.get()])
        self.destroy()


class StoryOrderDialog(tk.Toplevel):
    """Reorder the added chapters (above 31). Retail chapters keep their place. ``result`` is the new
    full order or None."""

    def __init__(self, parent: tk.Misc, order: list, labels: dict):
        super().__init__(parent)
        self.title("Story order")
        self.transient(parent.winfo_toplevel())
        self.result = None
        self._order, self._labels, self._original = list(order), labels, list(order)
        frame = ttk.Frame(self, padding=16)
        frame.pack(fill="both", expand=True)
        ttk.Label(frame, justify="left", text="The order a new game plays the added chapters. Retail chapters\n"
                                              "(1-31) keep their place; move the others with the buttons.").pack(anchor="w")
        body = ttk.Frame(frame)
        body.pack(fill="both", expand=True, pady=8)
        self._list = tk.Listbox(body, height=18, width=54, exportselection=False)
        self._list.pack(side="left", fill="both", expand=True)
        side = ttk.Frame(body)
        side.pack(side="left", padx=(8, 0))
        ttk.Button(side, text="Move up", command=lambda: self._move(-1)).pack(fill="x")
        ttk.Button(side, text="Move down", command=lambda: self._move(1)).pack(fill="x", pady=(4, 0))
        buttons = ttk.Frame(frame)
        buttons.pack(fill="x")
        ttk.Button(buttons, text="Cancel", command=self.destroy).pack(side="right")
        ttk.Button(buttons, text="Apply", style="Accent.TButton", command=self._ok).pack(side="right", padx=(0, 6))
        self._fill()
        self.grab_set()

    def _fill(self, select: int | None = None) -> None:
        self._list.delete(0, "end")
        for chapter in self._order:
            self._list.insert("end", ("    " if chapter > 31 else "🔒 ") + self._labels.get(chapter, f"{chapter:02d}"))
        if select is not None:
            self._list.selection_set(select)
            self._list.see(select)

    def _move(self, delta: int) -> None:
        selection = self._list.curselection()
        if not selection:
            return
        i = selection[0]
        j = i + delta
        if not (0 <= j < len(self._order)) or self._order[i] <= 31 or self._order[j] <= 31:
            return
        self._order[i], self._order[j] = self._order[j], self._order[i]
        self._fill(j)

    def _ok(self) -> None:
        self.result = self._order if self._order != self._original else None
        self.destroy()
