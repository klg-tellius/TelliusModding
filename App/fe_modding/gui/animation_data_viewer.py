"""Animation-registry browser for both Tellius games, with one Edit… button: a Path of Radiance
``FE8Anim.bin`` record's folder, blend weight and per-army texture numbers, or a Radiant Dawn
``FE10AnimData`` variant byte."""

from __future__ import annotations

import tkinter as tk
from tkinter import messagebox, simpledialog, ttk

from ..formats import anim_registry, fe10_anim
from ..games import Game
from ..project import ModProject
from .changelog import ChangeLog
from .editor_panel import EditorPanel


class AnimationDataViewer(EditorPanel):
    display_name = "Animation Data"

    def __init__(self, parent: tk.Misc, project: ModProject, changelog: ChangeLog):
        super().__init__(parent)
        self._project = project
        self._changelog = changelog
        self._data = b""
        self._document: fe10_anim.Fe10Anim | None = None
        self._dirty = False
        self._label = project.profile.file_label("anim_data")

        top = ttk.Frame(self, padding=8)
        top.pack(fill="x")
        ttk.Label(top, text=project.profile.file_label("anim_data"), font=("Segoe UI", 12, "bold")).pack(
            side="left")
        ttk.Label(top, text="Decoded fields are labeled and editable with Edit…; unknown values remain raw.",
                  style="Muted.TLabel").pack(side="left", padx=(12, 0))
        self._save_button = ttk.Button(top, text="Save", command=self.save, state="disabled")
        self._save_button.pack(side="right")
        ttk.Button(top, text="Discard changes", command=self._revert).pack(side="right", padx=(0, 6))
        self._edit_button = ttk.Button(top, text="Edit…", command=self._edit, state="disabled")
        self._edit_button.pack(side="right", padx=(0, 6))

        body = ttk.PanedWindow(self, orient="horizontal")
        body.pack(fill="both", expand=True, padx=8, pady=(0, 8))
        left, right = ttk.Frame(body), ttk.Frame(body)
        body.add(left, weight=2)
        body.add(right, weight=5)
        self._tables = ttk.Treeview(left, columns=("name", "rows", "size"), show="headings", selectmode="browse")
        for key, title, width in (("name", "Table", 180), ("rows", "Rows", 65), ("size", "Row size", 65)):
            self._tables.heading(key, text=title)
            self._tables.column(key, width=width, stretch=key == "name")
        self._tables.pack(fill="both", expand=True)
        self._tables.bind("<<TreeviewSelect>>", lambda _e: self._show_table())

        self._title = ttk.Label(right, text="Select a table", font=("Segoe UI", 12, "bold"))
        self._title.pack(anchor="w")
        self._rows = ttk.Treeview(right, columns=("index", "names", "values"), show="headings", selectmode="browse")
        for key, title, width in (("index", "#", 45), ("names", "Names", 380), ("values", "Values", 320)):
            self._rows.heading(key, text=title)
            self._rows.column(key, width=width, stretch=key != "index")
        self._rows.pack(fill="both", expand=True, pady=(5, 4))
        self._rows.bind("<<TreeviewSelect>>", lambda _e: self._row_selected())
        self._detail = tk.Text(right, height=9, wrap="word", font=("Consolas", 9), state="disabled")
        self._detail.pack(fill="x")
        self._status = ttk.Label(self, style="Muted.TLabel", padding=8)
        self._status.pack(anchor="w")
        self.refresh_from_archive()

    def refresh_from_archive(self) -> bool:
        self._tables.delete(*self._tables.get_children())
        self._rows.delete(*self._rows.get_children())
        try:
            raw = self._project.read_logical("anim_data")
            self._data = raw
            if self._project.game is Game.RADIANT_DAWN:
                self._document = fe10_anim.read_fe10_anim(raw)
                for table in self._document.tables:
                    self._tables.insert("", "end", iid=table.name,
                                        values=(table.name, len(table.records), table.record_size))
                self._status.configure(text=(f"{sum(len(table.records) for table in self._document.tables)} rows; "
                                             f"{len(self._document.string_pool):,} string-pool bytes."))
            else:
                self._document = None
                records = anim_registry.read_anim_registry(raw)
                self._por_records = records
                self._tables.insert("", "end", iid="AnimData",
                                    values=("AnimData", len(records), anim_registry.RECORD_SIZE))
                self._status.configure(text=f"{len(records)} animation records.")
        except Exception as exc:  # noqa: BLE001
            self._status.configure(text=f"Could not read animation data: {exc}")
            return False
        return True

    def _row_selected(self) -> None:
        self._show_row()
        table = self._tables.selection()
        # Path of Radiance has one table of editable records; Radiant Dawn edits its model variants
        enabled = table and self._rows.selection() and (self._document is None or table[0] == "FE10AnimData")
        self._edit_button.configure(state="normal" if enabled else "disabled")

    def _edit(self) -> None:
        if self._document is None:
            self._edit_record()
        else:
            self._edit_variant()

    def _edit_record(self) -> None:
        """A Path of Radiance record's class folder, blend weight and texture numbers (one per army)."""
        if not self._rows.selection():
            return
        index = int(self._rows.selection()[0])
        record = self._por_records[index]
        dialog = _RecordDialog(self, record)
        self.wait_window(dialog)
        if dialog.result is None or dialog.result == record:
            return
        records = list(self._por_records)
        records[index] = dialog.result
        self._data = anim_registry.build_anim_registry(records)
        self._por_records = anim_registry.read_anim_registry(self._data)
        self._dirty = True
        self._save_button.configure(state="normal")
        self._changelog.append(self._label, f"{record.aid_name}: edited the registry record")
        self._show_table()
        self._rows.selection_set(str(index))
        self._row_selected()
        self._status.configure(text="Animation record changed (unsaved).")

    def _edit_variant(self) -> None:
        if self._document is None or not self._rows.selection():
            return
        model_index = int(self._rows.selection()[0])
        shared = [header.aid_name for header in self._document.headers if header.model_index == model_index]
        weapon = simpledialog.askinteger(
            "Animation weapon", "Weapon row (0–8):\n" +
            ", ".join(f"{index}={item.archive_suffix}" for index, item in enumerate(self._document.weapons)),
            parent=self, minvalue=0, maxvalue=fe10_anim.WEAPON_SLOTS - 1)
        if weapon is None:
            return
        motion = simpledialog.askinteger(
            "Animation motion", "Motion row (0–47):\n" +
            ", ".join(f"{index}={item.file_stem}" for index, item in enumerate(self._document.motions)),
            parent=self, minvalue=0, maxvalue=fe10_anim.MOTION_SLOTS - 1)
        if motion is None:
            return
        current = self._document.models[model_index].variants[weapon][motion]
        variant = simpledialog.askinteger(
            "Animation variant",
            f"Variant byte for model #{model_index}, {self._document.weapons[weapon].archive_suffix}/"
            f"{self._document.motions[motion].file_stem}.\n0 disables it; current value: {current}.\n\n"
            f"This shared model affects {len(shared)} AID row(s): {', '.join(shared[:8])}"
            + ("…" if len(shared) > 8 else ""),
            parent=self, minvalue=0, maxvalue=255, initialvalue=current)
        if variant is None or variant == current:
            return
        self._data = fe10_anim.set_animation_variant(
            self._data, model_index, weapon, motion, variant)
        self._document = fe10_anim.read_fe10_anim(self._data)
        self._dirty = True
        self._save_button.configure(state="normal")
        self._changelog.append(self._label,
                               f"model #{model_index} {weapon}/{motion}: variant {current} -> {variant}")
        self._show_table()
        self._rows.selection_set(str(model_index))
        self._row_selected()
        self._status.configure(text="Animation variant changed (unsaved).")

    def save(self) -> bool:
        if not self._dirty:
            return True
        try:
            self._project.write_logical("anim_data", self._data)
        except OSError as exc:
            messagebox.showerror(f"Could not save {self._label}", str(exc), parent=self)
            return False
        self._dirty = False
        self._save_button.configure(state="disabled")
        self._status.configure(text=f"Saved {self._label}.")
        self._changelog.append(self._label, "Saved animation registry changes")
        return True

    def _revert(self) -> None:
        if self._dirty and not self._confirm_discard():
            return
        self._dirty = False
        self._save_button.configure(state="disabled")
        self.refresh_from_archive()

    def _confirm_discard(self) -> bool:
        return messagebox.askyesno(
            "Unsaved changes", "Discard the unsaved animation-data changes?", parent=self)

    def _show_table(self) -> None:
        selection = self._tables.selection()
        if not selection:
            return
        name = selection[0]
        self._rows.delete(*self._rows.get_children())
        self._set_detail("")
        if self._document is None:
            self._title.configure(text="AnimData")
            for index, record in enumerate(self._por_records):
                values = (f"{record.weapon_type_name}; blend {record.blend_weight}; "
                          f"textures {','.join(map(str, record.texture_ids))}")
                self._rows.insert("", "end", iid=str(index),
                                  values=(index, f"{record.aid_name}; {record.class_folder}", values))
            return
        table = self._document.table(name)
        self._title.configure(text=f"{name} — {len(table.records)} × {table.record_size} bytes")
        for index, record in enumerate(table.records):
            names = "; ".join(f"+{offset:#04x} {value or '(null)'}" for offset, value in record.strings)
            if name == "FE10AnimHeader":
                header = self._document.headers[index]
                values = f"model #{header.model_index}; texture {header.texture_name}; flags {header.flags:#06x}"
            elif name == "FE10AnimData":
                model = self._document.models[index]
                active = sum(bool(value) for row in model.variants for value in row)
                values = f"{active}/{fe10_anim.WEAPON_SLOTS * fe10_anim.MOTION_SLOTS} animation variants"
            elif name == "FE10AnimMotion":
                motion = self._document.motions[index]
                values = f"stem {motion.file_stem}; flags {motion.flags:#010x}"
            else:
                weapon = self._document.weapons[index]
                values = f"archive {weapon.archive_suffix}.pak"
            self._rows.insert("", "end", iid=str(index), values=(index, names, values))

    def _show_row(self) -> None:
        table_selection, row_selection = self._tables.selection(), self._rows.selection()
        if not table_selection or not row_selection:
            return
        index = int(row_selection[0])
        if self._document is None:
            record = self._por_records[index]
            self._set_detail(
                f"{record.aid_name}\nFolder: {record.class_folder}\nWeapon: {record.weapon_type_name}\n"
                f"Blend: {record.blend_weight}\nBody type: {record.body_type}\n"
                f"Actions: {', '.join(record.actions) or '(none)'}")
            return
        record = self._document.table(table_selection[0]).records[index]
        lines = [f"Record {index}, file address {record.address:#x}"]
        table_name = table_selection[0]
        if table_name == "FE10AnimHeader":
            header = self._document.headers[index]
            lines += [f"AID: {header.aid_name}", f"Description: {header.description}",
                      f"Ordinal: {header.ordinal}; flags: {header.flags:#06x}",
                      f"Texture: {header.texture_name}", f"FE10AnimData record: {header.model_index}"]
        elif table_name == "FE10AnimData":
            model = self._document.models[index]
            lines += [f"Model folder: {model.folder}", f"Movement sound: {model.movement_sound or '(none)'}",
                      f"Floor movement sound: {model.floor_movement_sound or '(none)'}",
                      f"Extra movement sound: {model.extra_movement_sound or '(none)'}",
                      "Parameters +0x10..+0x17: " + ", ".join(map(str, model.parameters))]
            active = [(self._document.weapons[w].archive_suffix if w < len(self._document.weapons) else str(w),
                       self._document.motions[m].file_stem if m < len(self._document.motions) else str(m), value)
                      for w, row in enumerate(model.variants) for m, value in enumerate(row) if value]
            lines.append(f"Animation variants: {len(active)}")
            lines += [f"  {weapon}/{motion}: variant {variant}" for weapon, motion, variant in active[:40]]
            if len(active) > 40:
                lines.append(f"  … {len(active) - 40} more")
        elif table_name == "FE10AnimMotion":
            motion = self._document.motions[index]
            lines += [f"Description: {motion.description}", f"Filename stem: {motion.file_stem}",
                      f"Flags: {motion.flags:#010x}"]
        elif table_name == "FE10AnimWeapon":
            weapon = self._document.weapons[index]
            lines += [f"Description: {weapon.description}", f"Archive suffix: {weapon.archive_suffix}.pak"]
        lines += [""] + [f"+{word_index * 4:03X}: {word:08X}"
                          for word_index, word in enumerate(record.words)]
        if record.strings:
            lines += ["", "Relocated strings:"] + [f"+{offset:#04x}: {value or '(null)'}"
                                                     for offset, value in record.strings]
        self._set_detail("\n".join(lines))

    def _set_detail(self, text: str) -> None:
        self._detail.configure(state="normal")
        self._detail.delete("1.0", "end")
        self._detail.insert("1.0", text)
        self._detail.configure(state="disabled")


class _RecordDialog(tk.Toplevel):
    """Edit one ``FE8Anim.bin`` record: ``result`` is the changed record, or None."""

    def __init__(self, parent: tk.Misc, record: anim_registry.AnimRecord):
        super().__init__(parent)
        self.title(f"Edit {record.aid_name}")
        self.transient(parent.winfo_toplevel())
        self.result = None
        self._record = record
        body = ttk.Frame(self, padding=12)
        body.pack(fill="both", expand=True)
        self._folder = tk.StringVar(value=record.class_folder)
        self._blend = tk.StringVar(value=str(record.blend_weight))
        self._textures = [tk.StringVar(value=str(t)) for t in record.texture_ids]
        rows = [("Model folder (ymu/)", ttk.Entry(body, textvariable=self._folder, width=24)),
                ("Blend weight", ttk.Entry(body, textvariable=self._blend, width=6))]
        rows += [(f"Texture number, {army}", ttk.Entry(body, textvariable=var, width=6))
                 for army, var in zip(anim_registry.ARMIES, self._textures)]
        for r, (label, widget) in enumerate(rows):
            ttk.Label(body, text=label).grid(row=r, column=0, sticky="w", pady=2)
            widget.grid(row=r, column=1, sticky="w", padx=(8, 0), pady=2)
        ttk.Label(body, style="Muted.TLabel", wraplength=360, justify="left", text=(
            "Each army draws ymu/<folder>/tex_<number>.tpl. The blend weight is the animation cross-fade "
            "(16 frames up to 20, 32 from 40).")).grid(row=len(rows), column=0, columnspan=2, sticky="w", pady=(8, 0))
        buttons = ttk.Frame(body)
        buttons.grid(row=len(rows) + 1, column=0, columnspan=2, sticky="e", pady=(10, 0))
        ttk.Button(buttons, text="Cancel", command=self.destroy).pack(side="right")
        ttk.Button(buttons, text="OK", style="Accent.TButton", command=self._ok).pack(side="right", padx=(0, 6))
        self.grab_set()

    def _ok(self) -> None:
        from dataclasses import replace

        folder = self._folder.get().strip()
        if not folder:
            messagebox.showerror("Edit record", "The record needs a model folder.", parent=self)
            return
        try:
            blend = int(self._blend.get())
            textures = tuple(int(v.get()) for v in self._textures)
            if not 0 <= blend <= 255 or not all(0 <= t <= 255 for t in textures):
                raise ValueError
        except ValueError:
            messagebox.showerror("Edit record", "The blend weight and texture numbers are 0-255.", parent=self)
            return
        self.result = replace(self._record, class_folder=folder if folder.endswith("/") else folder + "/",
                              blend_weight=blend, texture_ids=textures)
        self.destroy()
