"""The Radiant Dawn character form hosted by the shared Characters page (its Supports tab is the shared
:class:`.support_editor.CharacterSupportsPanel`)."""

from __future__ import annotations

import tkinter as tk
from tkinter import messagebox, simpledialog, ttk
from typing import Callable, Optional

from ..formats import fe10data
from . import message_reference
from .character_form import weapon_rank_grid
from .fe8_session import Fe10DataSession
from .widgets import Link, tip


PREFIXES = {
    "pid": "PID_", "mpid": "MPID_", "mnpid": "MNPID_", "fid": "FID_", "jid": "JID_",
    "aid_1": "AID_", "aid_2": "AID_", "aid_3": "AID_", "aid_4": "AID_",
}

STAT_KEYS = tuple(name.lower() for name in fe10data.STAT_NAMES)
IDENTITY_FIELDS = ("pid", "mpid", "mnpid", "fid", "jid", "affinity")
#: The weapon types of a Radiant Dawn rank string, in order (from the classes' starting and maximum
#: ranks: Swordmaster first letter, Thief fifth, the laguz classes' "*" sixth, Priest last).
WEAPON_TYPES = ("Sword", "Lance", "Axe", "Bow", "Knife", "Strike", "Fire", "Thunder", "Wind", "Light", "Dark",
                "Staff")
#: Fields whose value is a message ID: the message's text is shown beside them.
MESSAGE_FIELDS = ("mpid", "mnpid")
ANIMATION_FIELDS = ("aid_1", "aid_2", "aid_3", "aid_4")
UNIT_FIELDS = ("level", "sex", "authority", "biorhythm")
GAUGE_FIELDS = ("gauge_turn", "gauge_battle", "gauge_turn_transformed", "gauge_battle_transformed")
KNOWN_FIELDS = frozenset(IDENTITY_FIELDS + ("weapon_ranks",) + ANIMATION_FIELDS + UNIT_FIELDS + GAUGE_FIELDS
                         + tuple(f"bonus_{key}" for key in STAT_KEYS) + ("bonus_weight",)
                         + tuple(f"growth_{key}" for key in STAT_KEYS))


class Fe10CharacterForm(ttk.Frame):
    """The FE10 PersonData record, arranged like the Path of Radiance character form."""

    def __init__(self, parent: tk.Misc, session: Fe10DataSession, *,
                 on_open_class: Optional[Callable[[str], None]] = None,
                 on_open_character: Optional[Callable[[Optional[str]], None]] = None,
                 navigate: Optional[Callable[[tuple], None]] = None):
        super().__init__(parent, style="Page.TFrame")
        self._session = session
        self._navigate = navigate
        self._on_open_class = on_open_class
        self._on_open_character = on_open_character
        self._index: Optional[int] = None
        self._vars: dict[str, tk.StringVar] = {}
        self._texts: Optional[dict[str, str]] = None
        session.subscribe(self._session_changed)

        bar = ttk.Frame(self, style="Page.TFrame")
        bar.pack(fill="x", pady=(0, 10))
        ttk.Button(bar, text="Apply", style="Accent.TButton", command=self._apply).pack(side="left")
        ttk.Button(bar, text="Revert", command=lambda: self.show(self._index)).pack(side="left", padx=(6, 0))
        self._save_button = ttk.Button(bar, text=f"Save {session.file_label}", command=self._save)
        self._save_button.pack(side="left", padx=(6, 0))
        ttk.Button(bar, text="New character…", command=self._new).pack(side="left", padx=(18, 0))
        ttk.Button(bar, text="Remove", command=self._remove).pack(side="left", padx=(6, 0))
        self._status = ttk.Label(bar, style="Muted.TLabel")
        self._status.pack(side="left", padx=(12, 0))
        self._body = ttk.Frame(self, style="Page.TFrame")
        self._body.pack(fill="both", expand=True)
        self._refresh_status()

    def show(self, index: Optional[int]) -> None:
        self._index = index
        for child in self._body.winfo_children():
            child.destroy()
        self._vars = {}
        db = self._session.fe10
        if db is None or index is None or not 0 <= index < len(db.characters):
            ttk.Label(self._body, text=self._session.unavailable_reason, style="Muted.TLabel").pack(anchor="w")
            return
        record = db.characters[index]
        cls = next((r for r in db.classes if r.id == record.values.get("jid")), None)
        definitions = {d.key: d for d in fe10data.field_defs("character")}

        top = ttk.Frame(self._body, style="Page.TFrame")
        top.pack(fill="x")
        # The Path of Radiance arrangement: Identity with the map models under it, then Skills with the
        # weapon ranks (the rank table is what makes Skills wide).
        left = ttk.Frame(top, style="Page.TFrame")
        left.pack(side="left", fill="both", padx=(0, 12))
        identity = self._group(left, "Identity")
        for row, key in enumerate(IDENTITY_FIELDS):
            self._field(identity, row, definitions[key], record.values.get(key))
        if record.values.get("jid") and self._on_open_class:
            ttk.Button(identity, text="Open", command=lambda jid=record.values["jid"]: self._on_open_class(jid)).grid(
                row=IDENTITY_FIELDS.index("jid"), column=2, sticky="w", padx=(6, 0))
        if self._navigate is not None and record.values.get("pid"):
            pid = record.values["pid"]
            ttk.Button(identity, text="Open", command=lambda: self._navigate(("asset", "portraits", pid))).grid(
                row=IDENTITY_FIELDS.index("fid"), column=2, sticky="w", padx=(6, 0))
            tip(ttk.Button(identity, text="Supports", command=lambda: self._navigate(("character", pid, "supports"))),
                "The affinity is also set on the Supports tab, with the support partners.").grid(
                row=IDENTITY_FIELDS.index("affinity"), column=2, sticky="w", padx=(6, 0))

        animations = self._group(left, "Map models", "The unit's map animation sets (AID), one per tier; an "
                                                     "empty first one uses the class's own.")
        animations.master.pack(fill="x", pady=(12, 0))
        for row, key in enumerate(ANIMATION_FIELDS):
            self._field(animations, row, definitions[key], record.values.get(key))
            if self._navigate is not None:
                ttk.Button(animations, text="Open", command=lambda k=key: self._open_map_model(k)).grid(
                    row=row, column=2, sticky="w", padx=(6, 0))

        skills = self._group(top, "Skills")
        skills.master.pack(side="left", fill="both", expand=True)
        ttk.Label(skills, text="Personal skills", style="Surface.TLabel").grid(row=0, column=0, sticky="nw",
                                                                                padx=(0, 8))
        own = [v for v in record.lists.get("skills", []) if v]
        self._skills = tk.StringVar(value=", ".join(own))
        skill_entry = ttk.Combobox(skills, textvariable=self._skills,
                                   values=self._session.labels_by_prefix.get("SID_", []), width=52)
        skill_entry.grid(row=0, column=1, sticky="w")
        ttk.Label(skills, text="Separate multiple IDs with commas.", style="SurfaceMuted.TLabel").grid(
            row=1, column=1, sticky="w", pady=(2, 4))
        innate = [v for v in (cls.lists.get("skills", []) if cls else []) if v]
        for row, (label, sids) in enumerate((("Open skill", own), ("Class innate skills", innate)), 2):
            ttk.Label(skills, text=label, style="SurfaceMuted.TLabel").grid(row=row, column=0, sticky="w",
                                                                            padx=(0, 8), pady=2)
            links = ttk.Frame(skills, style="Surface.TFrame")
            links.grid(row=row, column=1, sticky="w")
            if not sids:
                ttk.Label(links, text="None", style="SurfaceMuted.TLabel").pack(side="left")
            for sid in sids:
                if self._navigate is not None:
                    Link(links, sid, lambda sid=sid: self._navigate(("data", "skills", sid)),
                         bg_token="surface").pack(side="left", padx=(0, 10))
                else:
                    ttk.Label(links, text=sid, style="SurfaceMuted.TLabel").pack(side="left", padx=(0, 10))
        weapon_rank_grid(skills, 4, record.values.get("weapon_ranks"), cls.values.get("weapon_ranks") if cls else None,
                         WEAPON_TYPES, self._vars,
                         "The game starts from the class's ranks; a letter here replaces the class's for that "
                         "weapon type. - keeps the class's rank, * makes the type usable without a set rank, E to S "
                         "set the starting rank.", short=3)

        unit = self._group(self._body, "Level, unit details and stats")
        unit.master.pack(fill="x", pady=(12, 0))
        for column, key in enumerate(UNIT_FIELDS):
            definition = definitions[key]
            ttk.Label(unit, text=definition.label, style="Surface.TLabel").grid(
                row=0, column=column * 2, sticky="w", padx=(0, 6))
            self._entry(unit, 0, column * 2 + 1, key, record.values.get(key), 6)

        grid = ttk.Frame(unit, style="Surface.TFrame")
        grid.grid(row=1, column=0, columnspan=8, sticky="w", pady=(12, 0))
        for column, name in enumerate(fe10data.STAT_NAMES, 1):
            ttk.Label(grid, text=name, style="SurfaceMuted.TLabel").grid(row=0, column=column, padx=4)
        rows = (
            ("Class base", "base", False),
            ("Personal bonus", "bonus", True),
            ("Class growth %", "growth", False),
            ("Personal growth %", "growth", True),
        )
        for row, (label, prefix, editable) in enumerate(rows, 1):
            ttk.Label(grid, text=label, style="Surface.TLabel" if editable else "SurfaceMuted.TLabel").grid(
                row=row, column=0, sticky="w", padx=(0, 10), pady=2)
            for column, key in enumerate(STAT_KEYS, 1):
                value = record.values.get(f"{prefix}_{key}") if editable else (
                    cls.values.get(f"{prefix}_{key}") if cls else None)
                if editable:
                    self._entry(grid, row, column, f"{prefix}_{key}", value, 5)
                else:
                    ttk.Label(grid, text="" if value is None else str(value),
                              style="SurfaceMuted.TLabel").grid(row=row, column=column)
        ttk.Label(grid, text="Personal weight", style="Surface.TLabel").grid(
            row=5, column=0, sticky="w", padx=(0, 10), pady=(8, 2))
        self._entry(grid, 5, 1, "bonus_weight", record.values.get("bonus_weight"), 5)

        gauge = self._group(self._body, "Laguz gauge")
        gauge.master.pack(fill="x", pady=(12, 0))
        for column, key in enumerate(GAUGE_FIELDS):
            definition = definitions[key]
            ttk.Label(gauge, text=definition.label, style="Surface.TLabel").grid(
                row=0, column=column * 2, sticky="w", padx=(0, 6))
            self._entry(gauge, 0, column * 2 + 1, key, record.values.get(key), 6)

        other = self._group(self._body, "Other decoded fields")
        other.master.pack(fill="x", pady=(12, 0))
        for row, definition in enumerate(d for d in fe10data.field_defs("character") if d.key not in KNOWN_FIELDS):
            self._field(other, row, definition, record.values.get(definition.key))

    def _open_map_model(self, key: str) -> None:
        """The map model of an AID field; an empty first AID opens the class's own."""
        from .character_form import open_map_model

        aid = self._vars[key].get().strip()
        if not aid and key == "aid_1":
            db = self._session.fe10
            jid = db.characters[self._index].values.get("jid")
            cls = next((r for r in db.classes if r.id == jid), None)
            aid = (cls.values.get("aid") if cls else None) or ""
        open_map_model(self, self._session.project, self._navigate, aid)

    def _group(self, parent: tk.Misc, title: str, help_text: str = "") -> ttk.Frame:
        outer = ttk.Frame(parent, style="Surface.TFrame", padding=14)
        outer.pack(fill="x")
        tip(ttk.Label(outer, text=title, style="SurfaceHeading.TLabel"), help_text).pack(anchor="w", pady=(0, 8))
        inner = ttk.Frame(outer, style="Surface.TFrame")
        inner.pack(fill="both", expand=True)
        return inner

    def _field(self, parent, row: int, definition: fe10data.FieldDef, value) -> None:
        ttk.Label(parent, text=definition.label, style="Surface.TLabel").grid(
            row=row, column=0, sticky="w", padx=(0, 8), pady=2)
        var = self._vars[definition.key] = tk.StringVar(value="" if value is None else str(value))
        if definition.kind == "label":
            prefix = PREFIXES.get(definition.key)
            values = self._session.labels_by_prefix.get(prefix, []) if prefix else []
            widget = ttk.Combobox(parent, textvariable=var, values=values, width=36)
        else:
            widget = ttk.Entry(parent, textvariable=var, width=12)
        widget.grid(row=row, column=1, sticky="w", pady=2)
        if definition.key in MESSAGE_FIELDS:
            shown = tk.StringVar()

            def update(*_args):
                key = var.get().strip()
                text = self._message_texts().get(key, "")
                shown.set(message_reference.preview(text, fe10=True) if text else
                          "(message not found)" if key else "")
            var.trace_add("write", update)
            update()
            ttk.Label(parent, textvariable=shown, style="SurfaceCaption.TLabel", wraplength=260,
                      justify="left").grid(row=row, column=2, sticky="w", padx=(6, 0))
        note = fe10data.FIELD_NOTES.get(definition.key)
        if note:
            ttk.Label(parent, text=note, style="SurfaceMuted.TLabel", wraplength=360, justify="left").grid(
                row=row, column=2, sticky="w", padx=(10, 0))

    def _message_texts(self) -> dict[str, str]:
        if self._texts is None:
            project = self._session.project
            self._texts = {**message_reference.epilogue_texts(project), **message_reference.message_texts(project)}
        return self._texts

    def _entry(self, parent, row: int, column: int, key: str, value, width: int) -> None:
        var = self._vars[key] = tk.StringVar(value="" if value is None else str(value))
        ttk.Entry(parent, textvariable=var, width=width, justify="center").grid(
            row=row, column=column, padx=2, pady=2)

    def _apply(self) -> None:
        db, index = self._session.fe10, self._index
        if db is None or index is None:
            return
        data = self._session.data
        try:
            for definition in fe10data.field_defs("character"):
                text = self._vars[definition.key].get().strip()
                value = (text or None) if definition.kind == "label" else (
                    float(text) if definition.kind == "f32" else int(text))
                current = fe10data.record(data, "character", index).values.get(definition.key)
                if value != current:
                    data = fe10data.patch_field(data, "character", index, definition.key, value)
            skills = [value.strip() for value in self._skills.get().split(",") if value.strip()]
            if skills != fe10data.record(data, "character", index).lists.get("skills", []):
                data = fe10data.set_list(data, "character", index, "skills", skills)
        except (ValueError, OverflowError) as exc:
            messagebox.showerror("Invalid value", str(exc), parent=self)
            return
        if data != self._session.data:
            self._session.replace(data, self)
            self.show(index)

    def _apply_field(self, key: str) -> None:
        """Apply one field for callers that need it; the visible form uses the shared Apply action."""
        db, index = self._session.fe10, self._index
        if db is None or index is None or key not in self._vars:
            return
        current = db.characters[index].values.get(key)
        text = self._vars[key].get().strip()
        definition = next(d for d in fe10data.field_defs("character") if d.key == key)
        try:
            value = (text or None) if definition.kind == "label" else (
                float(text) if definition.kind == "f32" else int(text))
        except ValueError:
            messagebox.showerror("Invalid value", f"{definition.label} must be a number.", parent=self)
            self._vars[key].set("" if current is None else str(current))
            return
        if value == current or (value is None and current is None):
            return
        try:
            data = fe10data.patch_field(self._session.data, "character", index, key, value)
        except ValueError as exc:
            messagebox.showerror("Invalid value", str(exc), parent=self)
            self._vars[key].set("" if current is None else str(current))
            return
        self._session.replace(data, self)
        self._status.configure(text=f"{key} changed (unsaved)", style="Warn.TLabel")

    def _apply_skills(self, _event=None) -> None:
        db, index = self._session.fe10, self._index
        if db is None or index is None:
            return
        values = [v.strip() for v in self._skills.get().split(",") if v.strip()]
        if values == db.characters[index].lists.get("skills", []):
            return
        try:
            data = fe10data.set_list(self._session.data, "character", index, "skills", values)
        except ValueError as exc:
            messagebox.showerror("Invalid skills", str(exc), parent=self)
            return
        self._session.replace(data, self)
        self.show(index)

    def _save(self) -> None:
        try:
            self._session.save()
        except OSError as exc:
            messagebox.showerror("Could not save", str(exc), parent=self)

    def _new(self) -> None:
        db = self._session.fe10
        if db is None or not db.characters:
            return
        source = self._index if self._index is not None else 0
        new_id = simpledialog.askstring("New character", "ID for the copy:", initialvalue="PID_", parent=self)
        if not new_id or new_id == "PID_":
            return
        if any(r.id == new_id for r in db.characters):
            messagebox.showerror("New character", f"{new_id} is already used.", parent=self)
            return
        try:
            data, index = fe10data.add_record(self._session.data, "character", source, new_id)
        except ValueError as exc:
            messagebox.showerror("New character", str(exc), parent=self)
            return
        self._session.replace(data, self)
        if self._on_open_character:
            self._on_open_character(new_id)
        else:
            self.show(index)

    def _remove(self) -> None:
        db, index = self._session.fe10, self._index
        if db is None or index is None:
            return
        pid = db.characters[index].id or f"character {index}"
        users = _references(self._session.fe10, pid, skip=("character", index))
        if users:
            messagebox.showerror("Remove", f"{pid} is still named by: {', '.join(users[:10])}.", parent=self)
            return
        if not messagebox.askyesno("Remove character", f"Remove {pid}?", parent=self):
            return
        self._session.replace(fe10data.remove_record(self._session.data, "character", index), self)
        self._index = None
        if self._on_open_character:
            self._on_open_character(None)

    def _session_changed(self, source) -> None:
        try:
            if source is not self and self._index is not None and self.winfo_exists():
                self.show(self._index)
            self._refresh_status()
        except tk.TclError:
            pass

    def _refresh_status(self) -> None:
        dirty = self._session.dirty
        self._save_button.configure(state="normal" if dirty else "disabled")
        if not self._status.cget("text") or not dirty:
            self._status.configure(text=f"Unsaved changes in {self._session.file_label}" if dirty else "",
                                   style="Warn.TLabel" if dirty else "Muted.TLabel")


def _references(db: fe10data.Fe10Data, label: str, skip: tuple[str, int]) -> list[str]:
    def names(value):
        if isinstance(value, str):
            return (value,)
        if isinstance(value, tuple):
            return tuple(v for v in value if isinstance(v, str))
        return ()

    found = []
    for kind in fe10data.ALL_KINDS:
        for record in db.table(kind):
            if (kind, record.index) == skip:
                continue
            if label in record.values.values() or any(
                    label in names(value) for values in record.lists.values() for value in values):
                found.append(f"{kind} {record.id or record.index}")
    return found
