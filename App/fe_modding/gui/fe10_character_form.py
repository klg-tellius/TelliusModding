"""Radiant Dawn character panels hosted by the shared Characters page."""

from __future__ import annotations

import tkinter as tk
from tkinter import messagebox, simpledialog, ttk
from typing import Callable, Optional

from ..formats import fe10data
from .fe8_session import Fe10DataSession
from .widgets import Link


PREFIXES = {
    "pid": "PID_", "mpid": "MPID_", "mnpid": "MNPID_", "fid": "FID_", "jid": "JID_",
    "aid_1": "AID_", "aid_2": "AID_", "aid_3": "AID_", "aid_4": "AID_",
}

STAT_KEYS = tuple(name.lower() for name in fe10data.STAT_NAMES)
IDENTITY_FIELDS = ("pid", "mpid", "mnpid", "fid", "jid", "affinity", "weapon_ranks")
ANIMATION_FIELDS = ("aid_1", "aid_2", "aid_3", "aid_4")
UNIT_FIELDS = ("level", "sex", "authority", "biorhythm")
GAUGE_FIELDS = ("gauge_turn", "gauge_battle", "gauge_turn_transformed", "gauge_battle_transformed")
KNOWN_FIELDS = frozenset(IDENTITY_FIELDS + ANIMATION_FIELDS + UNIT_FIELDS + GAUGE_FIELDS
                         + tuple(f"bonus_{key}" for key in STAT_KEYS) + ("bonus_weight",)
                         + tuple(f"growth_{key}" for key in STAT_KEYS))


class Fe10CharacterForm(ttk.Frame):
    """The FE10 PersonData record, arranged like the Path of Radiance character form."""

    def __init__(self, parent: tk.Misc, session: Fe10DataSession, *,
                 on_open_class: Optional[Callable[[str], None]] = None,
                 on_open_character: Optional[Callable[[Optional[str]], None]] = None):
        super().__init__(parent, style="Page.TFrame")
        self._session = session
        self._on_open_class = on_open_class
        self._on_open_character = on_open_character
        self._index: Optional[int] = None
        self._vars: dict[str, tk.StringVar] = {}
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
        left = ttk.Frame(top, style="Page.TFrame")
        left.pack(side="left", fill="both", padx=(0, 12))
        identity = self._group(left, "Identity")
        for row, key in enumerate(IDENTITY_FIELDS):
            self._field(identity, row, definitions[key], record.values.get(key))
        if record.values.get("jid") and self._on_open_class:
            Link(identity, "Open class", lambda jid=record.values["jid"]: self._on_open_class(jid)).grid(
                row=4, column=2, sticky="w", padx=(8, 0))

        animations = self._group(left, "Animations")
        animations.master.pack(fill="x", pady=(12, 0))
        for row, key in enumerate(ANIMATION_FIELDS):
            self._field(animations, row, definitions[key], record.values.get(key))

        skills = self._group(top, "Skills")
        skills.master.pack(side="left", fill="both", expand=True)
        ttk.Label(skills, text="Personal skills", style="Surface.TLabel").grid(row=0, column=0, sticky="nw",
                                                                                padx=(0, 8))
        self._skills = tk.StringVar(value=", ".join(v for v in record.lists.get("skills", []) if v))
        skill_entry = ttk.Combobox(skills, textvariable=self._skills,
                                   values=self._session.labels_by_prefix.get("SID_", []), width=70)
        skill_entry.grid(row=0, column=1, sticky="w")
        ttk.Label(skills, text="Separate multiple IDs with commas.", style="SurfaceMuted.TLabel").grid(
            row=1, column=1, sticky="w", pady=(2, 8))
        ttk.Label(skills, text="Class innate skills", style="SurfaceMuted.TLabel").grid(
            row=2, column=0, sticky="w", padx=(0, 8))
        innate = ", ".join(v for v in (cls.lists.get("skills", []) if cls else []) if v)
        ttk.Label(skills, text=innate or "None", style="SurfaceMuted.TLabel", wraplength=430,
                  justify="left").grid(row=2, column=1, sticky="w")

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

    def _group(self, parent: tk.Misc, title: str) -> ttk.Frame:
        outer = ttk.Frame(parent, style="Surface.TFrame", padding=14)
        outer.pack(fill="x")
        ttk.Label(outer, text=title, style="SurfaceHeading.TLabel").pack(anchor="w", pady=(0, 8))
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
        note = fe10data.FIELD_NOTES.get(definition.key)
        if note:
            ttk.Label(parent, text=note, style="SurfaceMuted.TLabel", wraplength=360, justify="left").grid(
                row=row, column=2, sticky="w", padx=(10, 0))

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


class Fe10CharacterSupportsPanel(ttk.Frame):
    """RD support speeds and personal bonds for the character page."""

    def __init__(self, parent: tk.Misc, session: Fe10DataSession, display_name: Callable[[str], str],
                 open_character: Callable[[str], None]):
        super().__init__(parent, style="Page.TFrame")
        self._session, self._display_name, self._open_character = session, display_name, open_character
        self._pid: Optional[str] = None
        self._support_rows: dict[str, tuple[int, int]] = {}
        self._bond_rows: dict[str, int] = {}
        session.subscribe(self._session_changed)

    def show(self, pid: Optional[str]) -> None:
        self._pid = pid
        for child in self.winfo_children():
            child.destroy()
        db = self._session.fe10
        if db is None or not pid:
            ttk.Label(self, text=self._session.unavailable_reason, style="Muted.TLabel").pack(anchor="w")
            return
        character = next((r for r in db.characters if r.id == pid), None)
        affinity_row = ttk.Frame(self, style="Page.TFrame")
        affinity_row.pack(fill="x", pady=(0, 14))
        ttk.Label(affinity_row, text="Affinity").pack(side="left")
        self._affinity = tk.StringVar(value=(character.values.get("affinity") or "") if character else "")
        affinities = [r.values.get("affinity") for r in db.table("affinity") if r.values.get("affinity")]
        affinity = ttk.Combobox(affinity_row, textvariable=self._affinity, values=affinities,
                                state="readonly", width=22)
        affinity.pack(side="left", padx=(8, 0))
        affinity.bind("<<ComboboxSelected>>", lambda _e: self._apply_affinity())
        ttk.Label(affinity_row, text="The character's affinity also appears on the Stats tab.",
                  style="Muted.TLabel").pack(side="left", padx=(12, 0))
        support = next((r for r in db.table("support") if r.values.get("pid") == pid), None)
        ttk.Label(self, text="Support partners", style="Heading.TLabel").pack(anchor="w")
        ttk.Label(self, text="Select a partner to edit the support flag and growth speed.",
                  style="Muted.TLabel").pack(anchor="w", pady=(2, 6))
        self._support_tree = self._tree(("partner", "name", "flag", "speed"), (190, 190, 70, 70))
        self._support_rows = {}
        if support:
            for k, (partner, flag, speed) in enumerate(support.lists["partners"]):
                iid = str(k)
                self._support_tree.insert("", "end", iid=iid,
                                          values=(partner, self._display_name(partner or ""), flag, speed))
                self._support_rows[iid] = (support.index, k)
        self._support_tree.bind("<<TreeviewSelect>>", lambda _e: self._select_support())
        edit = ttk.Frame(self, style="Page.TFrame")
        edit.pack(fill="x", pady=(6, 14))
        self._support_target = ttk.Label(edit, text="Pick a partner", style="Muted.TLabel")
        self._support_target.pack(side="left")
        self._flag, self._speed = tk.StringVar(), tk.StringVar()
        for label, var in (("Flag", self._flag), ("Speed", self._speed)):
            ttk.Label(edit, text=label).pack(side="left", padx=(12, 4))
            ttk.Entry(edit, textvariable=var, width=6).pack(side="left")
        ttk.Button(edit, text="Apply", command=self._apply_support).pack(side="left", padx=(8, 0))

        ttk.Label(self, text="Bonds", style="Heading.TLabel").pack(anchor="w")
        self._bond_tree = self._tree(("partner", "name", "bonus"), (190, 190, 80), height=6)
        self._bond_rows = {}
        for bond in db.table("bond"):
            a, b = bond.values.get("pid"), bond.values.get("partner")
            if pid not in (a, b):
                continue
            partner = b if a == pid else a
            iid = str(bond.index)
            self._bond_tree.insert("", "end", iid=iid,
                                   values=(partner, self._display_name(partner or ""), bond.values.get("bonus")))
            self._bond_rows[iid] = bond.index
        self._bond_tree.bind("<<TreeviewSelect>>", lambda _e: self._select_bond())
        self._bond_tree.bind("<Return>", lambda _e: self._open_selected(self._bond_tree))
        bond_edit = ttk.Frame(self, style="Page.TFrame")
        bond_edit.pack(fill="x", pady=(6, 0))
        self._bond_target = ttk.Label(bond_edit, text="Pick a bond", style="Muted.TLabel")
        self._bond_target.pack(side="left")
        ttk.Label(bond_edit, text="Bonus").pack(side="left", padx=(12, 4))
        self._bond_bonus = tk.StringVar()
        ttk.Entry(bond_edit, textvariable=self._bond_bonus, width=6).pack(side="left")
        ttk.Button(bond_edit, text="Apply", command=self._apply_bond).pack(side="left", padx=(8, 0))
        ttk.Button(bond_edit, text="New bond…", command=self._add_bond).pack(side="left", padx=(18, 0))
        ttk.Button(bond_edit, text="Remove bond", command=self._remove_bond).pack(side="left", padx=(6, 0))

    def _apply_affinity(self) -> None:
        db = self._session.fe10
        character = next((r for r in db.characters if r.id == self._pid), None) if db else None
        if character is None or self._affinity.get() == (character.values.get("affinity") or ""):
            return
        self._session.replace(fe10data.patch_field(
            self._session.data, "character", character.index, "affinity", self._affinity.get() or None), self)
        self.show(self._pid)

    def _tree(self, columns, widths, height=10):
        holder = ttk.Frame(self, style="Page.TFrame")
        holder.pack(fill="both", expand=True)
        tree = ttk.Treeview(holder, columns=columns, show="headings", height=height, selectmode="browse")
        for key, width in zip(columns, widths):
            tree.heading(key, text=key.title())
            tree.column(key, width=width, stretch=key == "name")
        scroll = ttk.Scrollbar(holder, command=tree.yview)
        tree.configure(yscrollcommand=scroll.set)
        tree.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")
        tree.bind("<Double-Button-1>", lambda _e: self._open_selected(tree))
        return tree

    def _open_selected(self, tree) -> None:
        selected = tree.selection()
        if selected:
            partner = tree.item(selected[0], "values")[0]
            if partner:
                self._open_character(partner)

    def _select_support(self) -> None:
        selected = self._support_tree.selection()
        if not selected:
            return
        values = self._support_tree.item(selected[0], "values")
        self._support_target.configure(text=values[0])
        self._flag.set(str(values[2]))
        self._speed.set(str(values[3]))

    def _apply_support(self) -> None:
        selected = self._support_tree.selection()
        if not selected:
            return
        record, partner = self._support_rows[selected[0]]
        try:
            flag, speed = int(self._flag.get(), 0), int(self._speed.get(), 0)
            current = self._session.fe10.table("support")[record].lists["partners"][partner]
            if (flag, speed) == tuple(current[1:]):
                return
            data = fe10data.set_support(self._session.data, record, partner, flag, speed)
        except ValueError as exc:
            messagebox.showerror("Invalid support", str(exc), parent=self)
            return
        self._session.replace(data, self)
        self.show(self._pid)

    def _select_bond(self) -> None:
        selected = self._bond_tree.selection()
        if not selected:
            return
        values = self._bond_tree.item(selected[0], "values")
        self._bond_target.configure(text=values[0])
        self._bond_bonus.set(str(values[2]))

    def _apply_bond(self) -> None:
        selected = self._bond_tree.selection()
        if not selected:
            return
        index = self._bond_rows[selected[0]]
        try:
            bonus = int(self._bond_bonus.get(), 0)
            data = fe10data.patch_field(self._session.data, "bond", index, "bonus", bonus)
        except ValueError as exc:
            messagebox.showerror("Invalid bond", str(exc), parent=self)
            return
        self._session.replace(data, self)
        self.show(self._pid)

    def _add_bond(self) -> None:
        db = self._session.fe10
        if db is None or not self._pid or not db.table("bond"):
            return
        partner = simpledialog.askstring("New bond", "Partner PID:", initialvalue="PID_", parent=self)
        if not partner or partner == "PID_":
            return
        if partner == self._pid or not any(r.id == partner for r in db.characters):
            messagebox.showerror("New bond", "Choose a different existing character PID.", parent=self)
            return
        if any({r.values.get("pid"), r.values.get("partner")} == {self._pid, partner}
               for r in db.table("bond")):
            messagebox.showerror("New bond", f"A bond with {partner} already exists.", parent=self)
            return
        try:
            data, index = fe10data.add_record(self._session.data, "bond", 0)
            data = fe10data.patch_field(data, "bond", index, "pid", self._pid)
            data = fe10data.patch_field(data, "bond", index, "partner", partner)
            data = fe10data.patch_field(data, "bond", index, "bonus", 10)
        except ValueError as exc:
            messagebox.showerror("New bond", str(exc), parent=self)
            return
        self._session.replace(data, self)
        self.show(self._pid)

    def _remove_bond(self) -> None:
        selected = self._bond_tree.selection()
        if not selected:
            return
        index = self._bond_rows[selected[0]]
        if not messagebox.askyesno("Remove bond", "Remove the selected bond?", parent=self):
            return
        try:
            data = fe10data.remove_record(self._session.data, "bond", index)
        except ValueError as exc:
            messagebox.showerror("Remove bond", str(exc), parent=self)
            return
        self._session.replace(data, self)
        self.show(self._pid)

    def reload(self) -> None:
        self.show(self._pid)

    def flush(self) -> None:
        pass

    def _session_changed(self, source) -> None:
        if source is not self and self._pid and self.winfo_exists():
            self.show(self._pid)


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
