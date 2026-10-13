"""The editable ``FE8Data.bin`` record of one character, as shown on the
character page: identity and class, skills, map/battle animation IDs, level
and build, biorhythm, the personal stat bonus and growth rows next to the
class's own values for reference, and the fixed level-up accumulators.

Edits go to the shared :class:`~.fe8_session.Fe8DataSession` on **Apply**;
**Save** writes the file for every view of it. **New character…** appends a
record (empty or a copy), **Remove** drops this one once nothing names it
(:mod:`.record_actions`).
"""

from __future__ import annotations

import struct
import tkinter as tk
from tkinter import messagebox, ttk
from typing import Callable, Optional

from ..formats import fe8data
from . import record_actions, message_reference
from .fe8_session import Fe8DataSession
from .widgets import tip

STAT_HELP = {
    "level": "Base level.", "build": "Constitution added to the class's (rescue and weight checks).",
    "weight": "Weight added to the class's (who can rescue whom).",
    "start_transform_gauge": "A laguz's transformation gauge when deployed (0-20).",
    "roster_order": "Default position in the unit lists.",
    "biorhythm_pattern": "The biorhythm curve (0: a random one).",
    "biorhythm_phase": "Where on the curve the unit starts (0 = 30).",
}
ROW_HELP = {
    "Class base": "The class's base stats, read-only here: edit them in Game Data › Classes.",
    "Personal bonus": "Added to the class's base stats.",
    "Class growth %": "The class's rates, used for autolevelled units (read-only here).",
    "Personal growth %": "The character's growth rates.",
    "Fixed growth start": "The accumulators the fixed ('Fraction') level-up mode starts from.",
}

POINTER_FIELDS = ["pid", "mpid", "fid", "jid", "sid0", "sid1", "sid2", "aid_unpromoted", "aid_promoted",
                  "weapon_ranks"]
BYTE_FIELDS = ["level", "build", "weight", "start_transform_gauge", "roster_order", "biorhythm_pattern",
               "biorhythm_phase"]


class CharacterForm(ttk.Frame):
    def __init__(self, parent: tk.Misc, session: Fe8DataSession, *,
                 on_open_class: Optional[Callable[[str], None]] = None,
                 on_open_character: Optional[Callable[[Optional[str]], None]] = None, project=None,
                 navigate: Optional[Callable[[tuple], None]] = None):
        super().__init__(parent, style="Page.TFrame")
        self._session = session
        self._on_open_class = on_open_class
        self._on_open_character = on_open_character  # a PID, or None for the character list
        self._navigate = navigate
        self._project = project or session.project
        self._index: Optional[int] = None
        self._vars: dict[str, tk.StringVar] = {}
        session.subscribe(self._on_session_changed)

        bar = ttk.Frame(self, style="Page.TFrame")
        bar.pack(fill="x", pady=(0, 10))
        ttk.Button(bar, text="Apply", style="Accent.TButton", command=self._apply).pack(side="left")
        ttk.Button(bar, text="Revert", command=lambda: self.show(self._index)).pack(side="left", padx=(6, 0))
        self._save_button = ttk.Button(bar, text="Save FE8Data.bin", command=self._save)
        self._save_button.pack(side="left", padx=(6, 0))
        ttk.Button(bar, text="New character…", command=self._new).pack(side="left", padx=(18, 0))
        ttk.Button(bar, text="Remove", command=self._remove).pack(side="left", padx=(6, 0))
        self._status = ttk.Label(bar, text="", style="Muted.TLabel")
        self._status.pack(side="left", padx=(12, 0))
        self._body = ttk.Frame(self, style="Page.TFrame")
        self._body.pack(fill="both", expand=True)
        self._refresh_status()

    # -- rendering -----------------------------------------------------------------
    def show(self, index: Optional[int]) -> None:
        self._index = index
        for child in self._body.winfo_children():
            child.destroy()
        self._vars = {}
        fe8 = self._session.fe8
        if fe8 is None or index is None or index >= len(fe8.characters):
            ttk.Label(self._body, text=self._session.unavailable_reason,
                      style="Muted.TLabel").pack(anchor="w")
            return
        c = fe8.characters[index]
        cls = next((k for k in fe8.classes if k.jid == c.jid), None)

        top = ttk.Frame(self._body, style="Page.TFrame")
        top.pack(fill="x")
        identity = self._group(top, "Identity")
        identity.master.pack(side="left", fill="both", expand=True, padx=(0, 12))
        self._pointer(identity, 0, "Character (PID)", "pid", c.pid, "PID")
        self._pointer(identity, 1, "Name key (MPID)", "mpid", c.mpid, "MPID")
        self._picker(identity, 2, "Portrait (FID)", "fid", c.fid, "FID",
                     open_=(lambda: self._navigate(("asset", "portraits", c.pid))) if self._navigate and c.pid
                     else None)
        self._pointer(identity, 3, "Class (JID)", "jid", c.jid, "JID")
        if c.jid and self._on_open_class is not None:
            link = ttk.Button(identity, text="Open", command=lambda: self._on_open_class(c.jid))
            link.grid(row=3, column=2, sticky="w", padx=(6, 0))

        skills = self._group(top, "Skills")
        skills.master.pack(side="left", fill="both", expand=True, padx=(0, 12))
        for i in range(3):
            self._pointer(skills, i, f"Slot {i}", f"sid{i}", c.sids[i], "SID")
        ttk.Label(skills, text="Class innate skills", style="SurfaceMuted.TLabel").grid(
            row=3, column=0, sticky="w", pady=2, padx=(0, 8))
        innate_skills = ", ".join(sid for sid in cls.skills if sid) if cls else ""
        ttk.Label(skills, text=innate_skills or "None", style="SurfaceMuted.TLabel",
                  wraplength=290, justify="left").grid(row=3, column=1, sticky="w")
        self._weapon_ranks(skills, 4, c.weapon_ranks, cls.weapon_ranks if cls else None)

        models = self._group(top, "Map models", "The unit's map animation set (AID); empty: the class's own.")
        models.master.pack(side="left", fill="both", expand=True)
        for row, (label, field, value) in enumerate((("Unpromoted", "aid_unpromoted", c.aid_unpromoted),
                                                     ("Promoted", "aid_promoted", c.aid_promoted))):
            self._picker(models, row, label, field, value, "AID",
                         open_=(lambda f=field: self._open_map_model(self._vars[f].get())) if self._navigate else None)

        stats = self._group(self._body, "Level, build and stats")
        stats.master.pack(fill="x", pady=(12, 0))
        for col, (label, field, value) in enumerate(
                (("Level", "level", c.level), ("Build", "build", c.build), ("Weight", "weight", c.weight),
                 ("Transform gauge", "start_transform_gauge", c.start_transform_gauge),
                 ("Roster order", "roster_order", c.roster_order),
                 ("Biorhythm", "biorhythm_pattern", c.biorhythm_pattern),
                 ("Phase", "biorhythm_phase", c.biorhythm_phase))):
            tip(ttk.Label(stats, text=label, style="Surface.TLabel"), STAT_HELP.get(field, "")).grid(
                row=0, column=col * 2, sticky="w", padx=(0, 6))
            self._entry(stats, 0, col * 2 + 1, field, value, width=5)
        grid = ttk.Frame(stats, style="Surface.TFrame")
        grid.grid(row=1, column=0, columnspan=12, sticky="w", pady=(12, 0))
        for i, name in enumerate(fe8data.STAT_NAMES):
            ttk.Label(grid, text=name, style="SurfaceMuted.TLabel").grid(row=0, column=i + 1, padx=4)
        rows = [
            ("Class base", cls.base_stats if cls else None, None),
            ("Personal bonus", c.stat_bonus, "stat_bonus"),
            ("Class growth %", cls.growths if cls else None, None),
            ("Personal growth %", c.growth, "growth"),
            ("Fixed growth start", c.fixed_growth_start, "fixed_growth_start"),
        ]
        for r, (label, values, field) in enumerate(rows, start=1):
            tip(ttk.Label(grid, text=label, style="Surface.TLabel" if field else "SurfaceMuted.TLabel"),
                ROW_HELP.get(label, "")).grid(row=r, column=0, sticky="w", padx=(0, 10), pady=2)
            for i in range(8):
                if field:
                    self._entry(grid, r, i + 1, f"{field}{i}", values[i], width=5)
                else:
                    ttk.Label(grid, text="" if values is None else str(values[i]),
                              style="SurfaceMuted.TLabel").grid(row=r, column=i + 1)

    def _group(self, parent: tk.Misc, title: str, help_text: str = "") -> ttk.Frame:
        outer = ttk.Frame(parent, style="Surface.TFrame", padding=14)
        tip(ttk.Label(outer, text=title, style="SurfaceHeading.TLabel"), help_text).pack(anchor="w", pady=(0, 8))
        inner = ttk.Frame(outer, style="Surface.TFrame")
        inner.pack(fill="both", expand=True)
        return inner

    def _pointer(self, parent, row: int, label: str, field: str, value, prefix: str) -> None:
        ttk.Label(parent, text=label, style="Surface.TLabel").grid(row=row, column=0, sticky="w", pady=2, padx=(0, 8))
        var = tk.StringVar(value=value or "")
        options = sorted(self._session.labels_by_prefix.get(prefix, {}).keys())
        if field == "mpid":
            texts = message_reference.message_texts(self._project)
            labels = {f"{key} — {message_reference.preview(text)}": key
                      for key, text in sorted(texts.items()) if key.startswith("MPID")}
            box = ttk.Combobox(parent, textvariable=var,
                               values=["", *labels, message_reference.CREATE_MESSAGE], width=42)
            shown = tk.StringVar()
            def update(*_args):
                key = labels.get(var.get(), var.get())
                shown.set(texts.get(key, "") or ("(message not found)" if key else ""))
            var.trace_add("write", update)
            update()
            ttk.Label(parent, textvariable=shown, style="SurfaceCaption.TLabel", wraplength=300,
                      justify="left").grid(row=row, column=2, sticky="w", padx=(6, 0))
            def chosen(_event):
                selected = var.get()
                if selected != message_reference.CREATE_MESSAGE:
                    var.set(labels.get(selected, selected))
                    return
                var.set(self._session.fe8.characters[self._index].mpid or "")
                initial = message_reference.suggested_id(
                    "MPID_", self._session.fe8.characters[self._index].pid or "NEW", set(texts))
                dialog = message_reference.NewMessageDialog(self, initial)
                if dialog.result is None:
                    return
                name, text = dialog.result
                if not name.startswith("MPID_"):
                    messagebox.showerror("Create message", "ID must start with MPID_.", parent=self)
                    return
                try:
                    data = fe8data.patch_character_field(self._session.data, self._index, "mpid", name)
                    message_reference.create_message(self._project, name, text)
                except (OSError, ValueError) as exc:
                    messagebox.showerror("Create message", str(exc), parent=self)
                    return
                self._session.data = data
                self._session.changed(self)
                texts[name] = text
                labels[f"{name} — {message_reference.preview(text)}"] = name
                box.configure(values=["", *labels, message_reference.CREATE_MESSAGE])
                var.set(name)
            box.bind("<<ComboboxSelected>>", chosen)
        else:
            box = ttk.Combobox(parent, textvariable=var, values=[""] + options, width=26)
        box.grid(row=row, column=1, sticky="w")
        self._vars[field] = var

    def _picker(self, parent, row: int, label: str, field: str, value, prefix: str, open_=None) -> None:
        """A label typed or picked from a list that narrows as you type, with an Open button."""
        from .map_builder import _LabelPicker

        ttk.Label(parent, text=label, style="Surface.TLabel").grid(row=row, column=0, sticky="w", pady=2, padx=(0, 8))
        options = sorted(self._session.labels_by_prefix.get(prefix, {}).keys())
        if value and value not in options:
            options.append(value)
        box = _LabelPicker(parent, width=26)
        box.set_choices([("", "")] + [(o, o) for o in options])
        var = tk.StringVar(value=value or "")
        box.configure(textvariable=var)
        box.grid(row=row, column=1, sticky="w")
        self._vars[field] = var
        if open_ is not None:
            ttk.Button(parent, text="Open", command=open_).grid(row=row, column=2, sticky="w", padx=(6, 0))

    def _weapon_ranks(self, parent, row: int, ranks: Optional[str], class_ranks: Optional[str]) -> None:
        """The class's ranks (read-only) above the character's, one picker per weapon type."""
        tip(ttk.Label(parent, text="Weapon ranks", style="Surface.TLabel"),
            "- can't use, * usable without a set rank, E to S the starting rank. When the character has ranks "
            "of its own, each letter replaces the class's, a - included: Soren (------D--) only uses wind "
            "although Mages have fire and thunder. Tick 'Use the class's' to leave the field empty.").grid(
            row=row, column=0, sticky="nw", pady=2, padx=(0, 8))
        table = ttk.Frame(parent, style="Surface.TFrame")
        table.grid(row=row, column=1, columnspan=2, sticky="w")
        names = fe8data.WEAPON_TYPE_NAMES
        for i, name in enumerate(names):
            ttk.Label(table, text=name[:2], style="SurfaceMuted.TLabel").grid(row=0, column=i + 1)
        ttk.Label(table, text="Class", style="SurfaceMuted.TLabel").grid(row=1, column=0, sticky="w", padx=(0, 4))
        for i, letter in enumerate((class_ranks or "").ljust(len(names), "-")[:len(names)]):
            ttk.Label(table, text=letter, style="SurfaceMuted.TLabel").grid(row=1, column=i + 1)
        ttk.Label(table, text="Own", style="Surface.TLabel").grid(row=2, column=0, sticky="w", padx=(0, 4))
        letters = [tk.StringVar(value=ch) for ch in (ranks or class_ranks or "").ljust(len(names), "-")[:len(names)]]
        use_class = tk.BooleanVar(value=not ranks)
        boxes = []
        for i, var in enumerate(letters):
            box = ttk.Combobox(table, textvariable=var, values=list(fe8data.WEAPON_RANK_CHARS), width=2,
                               state="readonly")
            box.grid(row=2, column=i + 1, padx=1)
            boxes.append(box)

        class _Ranks:
            def get(self) -> str:
                return "" if use_class.get() else "".join(v.get() or "-" for v in letters)

        def sync() -> None:
            for box in boxes:
                box.configure(state="disabled" if use_class.get() else "readonly")

        ttk.Checkbutton(table, text="Use the class's", variable=use_class, command=sync).grid(
            row=3, column=0, columnspan=len(names) + 1, sticky="w", pady=(2, 0))
        sync()
        self._vars["weapon_ranks"] = _Ranks()

    def _open_map_model(self, aid: str) -> None:
        from ..formats import anim_registry
        from ..game_profile import PATH_OF_RADIANCE_PROFILE

        aid = aid.strip()
        if not aid:
            fe8 = self._session.fe8
            c = fe8.characters[self._index]
            cls = next((k for k in fe8.classes if k.jid == c.jid), None)
            aid = cls.aid if cls is not None and cls.aid else ""
        try:
            records = anim_registry.read_anim_registry_path(
                PATH_OF_RADIANCE_PROFILE.path(self._project.extracted_dir / "files", "anim_data"))
        except Exception:  # noqa: BLE001
            records = []
        folder = next((r.class_folder.rstrip("/") for r in records if r.base_aid == aid), None)
        if folder is None:
            messagebox.showinfo("Map model", f"No map model folder is registered for {aid or 'this AID'}.",
                                parent=self)
            return
        self._navigate(("asset", "models", f"ymu/{folder}"))

    def _entry(self, parent, row: int, column: int, field: str, value, width: int) -> None:
        var = tk.StringVar(value=str(value))
        ttk.Entry(parent, textvariable=var, width=width, justify="center").grid(row=row, column=column, padx=2, pady=2)
        self._vars[field] = var

    # -- editing -----------------------------------------------------------------------
    def _apply(self) -> None:
        if self._index is None or not self._vars:
            return
        data = self._session.data
        index = self._index
        try:
            current = fe8data.read_fe8data(data).characters[index]
            for field in POINTER_FIELDS:
                raw = self._vars[field].get().strip()
                old = current.sids[int(field[3])] if field.startswith("sid") else getattr(current, field)
                if (raw or None) != old:
                    data = fe8data.patch_character_field(data, index, field, raw or None)
            for field in BYTE_FIELDS:
                data = fe8data.patch_character_field(data, index, field, int(self._vars[field].get()))
            for i in range(8):
                for row in ("stat_bonus", "growth", "fixed_growth_start"):
                    data = fe8data.patch_character_field(data, index, f"{row}{i}", int(self._vars[f"{row}{i}"].get()))
        except ValueError as exc:
            messagebox.showerror("Invalid value", str(exc), parent=self)
            return
        except (struct.error, OverflowError) as exc:
            messagebox.showerror("Value out of range", f"A field value doesn't fit in one byte.\n{exc}", parent=self)
            return
        self._session.data = data
        self._session.changed(self)
        self.show(index)
        self._refresh_status()

    def _save(self) -> None:
        try:
            self._session.save()
        except OSError as exc:
            messagebox.showerror("Could not save", str(exc), parent=self)

    def _new(self) -> None:
        fe8 = self._session.fe8
        if fe8 is None:
            return
        labels = [f"{c.pid or '?'}  #{c.index}" for c in fe8.characters]
        index = record_actions.add_record(self, self._session, "character", labels, self._index, source=self)
        if index is None:
            return
        pid = self._session.fe8.characters[index].pid
        self._status.configure(text=f"Added {pid}: save FE8Data.bin to list it on the Characters page",
                               style="Warn.TLabel")
        if self._on_open_character is not None:
            self._on_open_character(pid)
        else:
            self.show(index)

    def _remove(self) -> None:
        fe8 = self._session.fe8
        if fe8 is None or self._index is None:
            return
        pid = fe8.characters[self._index].pid or f"character {self._index}"
        if not record_actions.remove_record(self, self._session, self._project, "character", self._index, pid,
                                            source=self):
            return
        self._index = None
        if self._on_open_character is not None:
            self._on_open_character(None)
        else:
            self.show(None)

    def _on_session_changed(self, source) -> None:
        try:
            if source is not self and self._index is not None and self.winfo_exists():
                self.show(self._index)
            self._refresh_status()
        except tk.TclError:
            pass

    def _refresh_status(self) -> None:
        dirty = self._session.dirty
        self._save_button.configure(state="normal" if dirty else "disabled")
        self._status.configure(text="Unsaved changes in FE8Data.bin" if dirty else "",
                               style="Warn.TLabel" if dirty else "Muted.TLabel")
