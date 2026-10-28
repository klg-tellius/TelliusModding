"""Structural browser and safe semantic editor for RD ``FE10Battle.cms``."""

from __future__ import annotations

import tkinter as tk
from tkinter import messagebox, simpledialog, ttk

from ..formats import fe10_battle
from ..games import Game
from ..project import ModProject
from .changelog import ChangeLog
from .dbx_files_viewer import DbxFilesViewer
from .editor_panel import EditorPanel


class Fe10BattleViewer(EditorPanel):
    display_name = "Battle Data"

    def __init__(self, parent: tk.Misc, project: ModProject, changelog: ChangeLog):
        super().__init__(parent)
        self._project = project
        self._changelog = changelog
        self._data = b""
        self._document: fe10_battle.Fe10Battle | None = None
        self._items: dict[str, object] = {}
        self._dirty = False

        top = ttk.Frame(self, padding=8)
        top.pack(fill="x")
        ttk.Label(top, text="FE10Battle.cms", font=("Segoe UI", 12, "bold")).pack(side="left")
        ttk.Label(top, text="Relocated names and decoded relationships are editable; opaque fields remain read-only.",
                  style="Muted.TLabel").pack(side="left", padx=(12, 0))
        self._save_button = ttk.Button(top, text="Save", command=self.save, state="disabled")
        self._save_button.pack(side="right")
        ttk.Button(top, text="Discard changes", command=self._revert).pack(side="right", padx=(0, 6))
        self._edit_button = ttk.Button(top, text="Edit scenery choice…", command=self._edit_map_variant,
                                       state="disabled")
        self._edit_button.pack(side="right", padx=(0, 6))
        self._edit_strings_button = ttk.Button(
            top, text="Edit names…", command=self._edit_strings, state="disabled")
        self._edit_strings_button.pack(side="right", padx=(0, 6))

        body = ttk.PanedWindow(self, orient="horizontal")
        body.pack(fill="both", expand=True, padx=8, pady=(0, 8))
        left, right = ttk.Frame(body), ttk.Frame(body)
        body.add(left, weight=2)
        body.add(right, weight=5)
        self._tables = ttk.Treeview(left, columns=("name", "rows", "size"), show="headings", selectmode="browse")
        for key, title, width in (("name", "Table", 190), ("rows", "Rows / bytes", 80), ("size", "Row size", 65)):
            self._tables.heading(key, text=title)
            self._tables.column(key, width=width, stretch=key == "name")
        self._tables.pack(fill="both", expand=True)
        self._tables.bind("<<TreeviewSelect>>", lambda _e: self._show_table())

        self._title = ttk.Label(right, text="Select a table", font=("Segoe UI", 12, "bold"))
        self._title.pack(anchor="w")
        self._rows = ttk.Treeview(right, columns=("index", "strings", "words"), show="headings", selectmode="browse")
        for key, title, width in (("index", "#", 45), ("strings", "Relocated strings", 360),
                                  ("words", "Raw words", 330)):
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
        try:
            self._data = self._project.read_logical("battle_data")
            self._document = fe10_battle.read_fe10_battle(self._data)
        except Exception as exc:  # noqa: BLE001 - show corrupt/incomplete project data in the panel
            self._status.configure(text=f"Could not read FE10Battle.cms: {exc}")
            return False
        self._tables.delete(*self._tables.get_children())
        self._items.clear()
        for table in self._document.tables:
            key = "table:" + table.name
            self._items[key] = table
            self._tables.insert("", "end", iid=key, values=(table.name, len(table.records), table.record_size))
        for name, data in self._document.arrays:
            key = "array:" + name
            self._items[key] = data
            self._tables.insert("", "end", iid=key, values=(name, f"{len(data)} B", "byte array"))
        self._status.configure(text=(f"{len(self._document.tables)} fixed-row tables, "
                                     f"{len(self._document.arrays)} camera arrays, "
                                     f"{len(self._document.string_pool):,} string-pool bytes."))
        return True

    def _row_selected(self) -> None:
        self._show_row()
        selection = self._tables.selection()
        enabled = (selection and selection[0] == "table:FE10BMapData" and self._rows.selection())
        self._edit_button.configure(state="normal" if enabled else "disabled")
        string_enabled = False
        if selection and self._rows.selection():
            table = self._items.get(selection[0])
            if isinstance(table, fe10_battle.BattleTable):
                string_enabled = bool(table.records[int(self._rows.selection()[0])].strings)
        self._edit_strings_button.configure(state="normal" if string_enabled else "disabled")

    def _edit_strings(self) -> None:
        table_selection, row_selection = self._tables.selection(), self._rows.selection()
        if not table_selection or not row_selection:
            return
        table = self._items.get(table_selection[0])
        if not isinstance(table, fe10_battle.BattleTable):
            return
        index = int(row_selection[0])
        record = table.records[index]
        changed: dict[int, str] = {}
        for offset, value in record.strings:
            replacement = simpledialog.askstring(
                f"{table.name} row {index}", f"Relocated string at +{offset:#04x}:",
                initialvalue=value, parent=self)
            if replacement is None:
                return
            if replacement != value:
                changed[offset] = replacement
        if not changed:
            return
        try:
            self._data = fe10_battle.update_battle_record(
                self._data, table.name, index, strings=changed)
            self._document = fe10_battle.read_fe10_battle(self._data)
        except (ValueError, IndexError) as exc:
            messagebox.showerror("Could not edit battle data", str(exc), parent=self)
            return
        self._dirty = True
        self._save_button.configure(state="normal")
        self._changelog.append(
            "FE10Battle.cms", f"Edited {table.name} row {index} strings")
        self._show_table()
        self._rows.selection_set(str(index))
        self._row_selected()
        self._status.configure(text="Battle-data names changed (unsaved).")

    def _edit_map_variant(self) -> None:
        if self._document is None or not self._rows.selection():
            return
        map_index = int(self._rows.selection()[0])
        map_record = self._document.map_data[map_index]
        variant = simpledialog.askinteger(
            "Scenery variant", "Variant slot to edit (0–4).\n"
            "Slot 3 falls back to slot 2; every missing slot then falls back to slot 0.",
            parent=self, minvalue=0, maxvalue=4)
        if variant is None:
            return
        current = map_record.model_indices[variant]
        model_index = simpledialog.askinteger(
            "Scenery model",
            f"FE10BMapModel row for {map_record.map_name}, variant {variant}.\n"
            f"Use -1 for no direct model (the runtime fallback applies). Current: "
            f"{'-1' if current is None else current}.\n\n"
            "Model rows begin: " + ", ".join(
                f"{model.record_index}={model.archive_name}" for model in self._document.map_models[:24]) + "…",
            parent=self, minvalue=-1, maxvalue=len(self._document.map_models) - 1,
            initialvalue=-1 if current is None else current)
        if model_index is None:
            return
        replacement = None if model_index < 0 else model_index
        if replacement == current:
            return
        self._data = fe10_battle.set_map_model_variant(
            self._data, map_index, variant, replacement)
        self._document = fe10_battle.read_fe10_battle(self._data)
        self._dirty = True
        self._save_button.configure(state="normal")
        self._changelog.append(
            "FE10Battle.cms",
            f"{map_record.map_name} variant {variant}: {current} -> {replacement}")
        self._show_table()
        self._rows.selection_set(str(map_index))
        self._row_selected()
        self._status.configure(text="Scenery choice changed (unsaved).")

    def save(self) -> bool:
        if not self._dirty:
            return True
        try:
            self._project.write_logical("battle_data", self._data)
        except OSError as exc:
            messagebox.showerror("Could not save FE10Battle.cms", str(exc), parent=self)
            return False
        self._dirty = False
        self._save_button.configure(state="disabled")
        self._status.configure(text="Saved FE10Battle.cms.")
        self._changelog.append("FE10Battle.cms", "Saved battle-data changes")
        return True

    def _revert(self) -> None:
        if self._dirty and not self._confirm_discard():
            return
        self._dirty = False
        self._save_button.configure(state="disabled")
        self.refresh_from_archive()

    def _confirm_discard(self) -> bool:
        return messagebox.askyesno(
            "Unsaved changes", "Discard the unsaved battle-data changes?", parent=self)

    def _show_table(self) -> None:
        selection = self._tables.selection()
        if not selection:
            return
        item = self._items[selection[0]]
        self._rows.delete(*self._rows.get_children())
        self._set_detail("")
        if isinstance(item, bytes):
            name = selection[0].split(":", 1)[1]
            self._title.configure(text=f"{name} — {len(item)} bytes")
            preview = " ".join(f"{value:02X}" for value in item[:512])
            self._set_detail(preview + (" …" if len(item) > 512 else ""))
            return
        self._title.configure(text=f"{item.name} — {len(item.records)} × {item.record_size} bytes")
        for index, record in enumerate(item.records):
            strings = "; ".join(f"+{offset:#04x} {value or '(null)'}" for offset, value in record.strings)
            if item.name == "FE10BMapModel":
                model = self._document.map_models[index]
                words = (f"xyz {model.translation}; rot {model.rotation_value}; "
                         f"scale {model.scale_value}")
            elif item.name == "FE10BMapData":
                values = ["—" if value is None else str(value)
                          for value in self._document.map_data[index].model_indices]
                words = "model variants " + ", ".join(values)
            elif item.name == "FE10BUnit":
                texture_set = self._document.unit_texture_sets[index]
                words = f"{len(texture_set.mappings)} texture mappings"
            elif item.name == "FE10BTex":
                mapping = self._document.texture_mappings[index]
                words = f"{mapping.condition} → {mapping.texture_name}"
            else:
                words = " ".join(f"{word:08X}" for word in record.words[:8])
                if len(record.words) > 8:
                    words += " …"
            self._rows.insert("", "end", iid=str(index), values=(index, strings, words))

    def _show_row(self) -> None:
        table_selection, row_selection = self._tables.selection(), self._rows.selection()
        if not table_selection or not row_selection:
            return
        table = self._items[table_selection[0]]
        if not isinstance(table, fe10_battle.BattleTable):
            return
        index = int(row_selection[0])
        record = table.records[index]
        lines = [f"Record {index}, file address {record.address:#x}", ""]
        if table.name == "FE10BMapModel":
            model = self._document.map_models[index]
            lines += [f"Scenery archive: zbg/{model.archive_name}",
                      f"Sound group: {model.sound_group or '(none)'}", f"Flags: {model.flags:#04x}",
                      "Parameters +0x09..+0x0D: " + ", ".join(map(str, model.parameters)),
                      f"Translation: {model.translation}", f"Rotation value: {model.rotation_value}",
                      f"Scale value: {model.scale_value}", ""]
        elif table.name == "FE10BMapData":
            map_record = self._document.map_data[index]
            lines += [f"Map key: {map_record.map_name}",
                      "Model variants: " + ", ".join("—" if value is None else str(value)
                                                     for value in map_record.model_indices),
                      "Resolved: " + ", ".join(
                          (self._document.map_model(map_record, variant).archive_name
                           if self._document.map_model(map_record, variant) else "—")
                          for variant in range(5)), ""]
        elif table.name == "FE10BUnit":
            texture_set = self._document.unit_texture_sets[index]
            lines += [f"Unit/model: {texture_set.unit_name} / {texture_set.model_name}",
                      f"Texture mappings: {len(texture_set.mappings)}"]
            lines += [f"  {mapping.condition} → {mapping.texture_name}"
                      for mapping in texture_set.mappings]
            lines.append("")
        elif table.name == "FE10BTex":
            mapping = self._document.texture_mappings[index]
            lines += [f"Condition: {mapping.condition}", f"Texture: {mapping.texture_name}", ""]
        lines += [f"+{index * 4:03X}: {word:08X}" for index, word in enumerate(record.words)]
        if record.strings:
            lines += ["", "Relocated strings:"] + [f"+{offset:#04x}: {value or '(null)'}"
                                                     for offset, value in record.strings]
        self._set_detail("\n".join(lines))

    def _set_detail(self, text: str) -> None:
        self._detail.configure(state="normal")
        self._detail.delete("1.0", "end")
        self._detail.insert("1.0", text)
        self._detail.configure(state="disabled")


def battle_data_viewer(parent: tk.Misc, project: ModProject, changelog: ChangeLog) -> EditorPanel:
    """Keep the shared Assets route while selecting the game's native representation."""
    if project.game is Game.RADIANT_DAWN:
        return Fe10BattleViewer(parent, project, changelog)
    return DbxFilesViewer(parent, project, changelog)
