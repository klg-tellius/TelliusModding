"""Battle Data page: the battle engine's native tables, on one :class:`BattleBrowser`.

* Path of Radiance (:class:`DbxAdapter`): every text ``.dbx`` entry of ``zdbx.cmp``, grouped by
  folder, edited as a Form (blocks and fields with English notes), a Layout (widgets on the
  640 x 480 screen) or the raw Text (``gui/dbx_form.py``); files can be added, deleted and restored.
* Radiant Dawn (:class:`Fe10BattleAdapter`): ``FE10Battle.cms``, one group per fixed-row table and
  one for the camera arrays; names and decoded links are editable, other fields read-only."""

from __future__ import annotations

import tkinter as tk
from tkinter import messagebox, simpledialog, ttk

from .. import battle_tables
from ..exceptions import ProjectError
from ..formats import dbx, fe10_battle
from ..project import ModProject
from .battle_browser import BattleBrowser, BrowserAdapter, Group, Item
from .changelog import ChangeLog
from .dbx_form import DbxForm, DbxLayout
from .editor_panel import EditorPanel


class DbxAdapter(BrowserAdapter):
    display_name = "Battle Data"
    source = "zdbx.cmp"
    note = "Every text table of the battle engine (.dbx). Edit one as a form, on its screen layout or as text."
    label_title = "Archive path"
    columns = (("state", "State", 75),)
    keeps_changes = True

    def __init__(self, project: ModProject, changelog: ChangeLog):
        super().__init__(project, changelog)
        self._inventory: dict[str, str] = {}
        self._path: str | None = None
        self._new = False
        self._saved_text = ""
        self._line_ending = "\r\n"
        self._loading = False

    # -- list -------------------------------------------------------------------------
    def load(self) -> list[Group]:
        self._inventory = battle_tables.inventory(self.project)
        groups: dict[str, Group] = {}
        for path, state in sorted(self._inventory.items()):
            folder, slash, name = path.partition("/")
            if not slash:
                folder, name = "", path
            group = groups.setdefault(folder, Group(folder, (folder or "(top)") + "/"))
            group.items.append(Item(path, (state,), label=name))
        for group in groups.values():
            group.info = str(len(group.items))
        return list(groups.values())

    def summary(self) -> str:
        return f"{len(self._inventory)} DBX files (including deleted originals)."

    # -- editor -----------------------------------------------------------------------
    def build_detail(self, parent: ttk.Frame) -> None:
        self._title = ttk.Label(parent, text="Select a DBX file", font=("Segoe UI", 12, "bold"))
        self._title.pack(anchor="w", pady=(0, 5))
        self._tabs = ttk.Notebook(parent)
        self._tabs.pack(fill="both", expand=True)
        self._form = DbxForm(self._tabs, self._current_text, self._replace_text)
        self._layout = DbxLayout(self._tabs, self._current_text, self._replace_text, self._layout_selected)
        text_tab = ttk.Frame(self._tabs)
        self._tabs.add(self._form, text="Form")
        self._tabs.add(self._layout, text="Layout")
        self._tabs.add(text_tab, text="Text")
        self._tabs.bind("<<NotebookTabChanged>>", lambda e: self._refresh_views())
        self._editor = tk.Text(text_tab, wrap="none", undo=True, font=("Consolas", 10))
        self._editor.pack(fill="both", expand=True)
        self._editor.bind("<<Modified>>", self._text_modified)

    def actions(self):
        return (("Add DBX...", self._add), ("Delete", self._delete), ("Restore original", self._restore))

    def _text_modified(self, _event=None) -> None:
        if self._editor.edit_modified():
            self._editor.edit_modified(False)
            if not self._loading:
                self.changed()

    def _current_text(self) -> str:
        return self._editor.get("1.0", "end-1c")

    def _replace_text(self, text: str) -> None:
        """Put a Form/Layout edit into the text (one undo step), keeping the view."""
        top = self._editor.yview()[0]
        self._editor.edit_separator()
        self._editor.delete("1.0", "end")
        self._editor.insert("1.0", text)
        self._editor.edit_separator()
        self._editor.yview_moveto(top)
        self.changed()

    def _editable(self) -> bool:
        return bool(self._path) and self._inventory.get(self._path) != "deleted" or self._new

    def _refresh_views(self) -> None:
        current = self._tabs.select()
        if current == str(self._form):
            self._form.show(self._path or "", self._editable())
        elif current == str(self._layout):
            self._layout.show(self._editable())

    def _layout_selected(self, start: int) -> None:
        self._form.refresh()
        self._form.select_block(start)

    def show(self, key: str | None) -> None:
        self._open(key)

    def _open(self, path: str | None, *, new: bool = False) -> None:
        try:
            state = self._inventory.get(path) if path else None
            text = battle_tables.read_entry(self.project, path) if path and state != "deleted" and not new else ""
        except (ProjectError, OSError, UnicodeError) as exc:
            self.error(self.display_name, exc)
            return
        self._loading = True
        self._path = path
        self._new = new
        self._line_ending = "\r\n" if "\r\n" in text else "\n"
        display_text = text.replace("\r\n", "\n").replace("\r", "\n")
        self._saved_text = display_text
        self._title.configure(text=(path or "Select a DBX file") + (" (new)" if new else ""))
        self._editor.configure(state="normal")
        self._editor.delete("1.0", "end")
        self._editor.insert("1.0", display_text)
        self._editor.edit_reset()
        self._editor.edit_modified(False)
        self._editor.configure(state="disabled" if not path or state == "deleted" else "normal")
        self._loading = False
        has_layout = DbxLayout.has_layout(display_text)
        self._tabs.tab(self._layout, state="normal" if has_layout else "disabled")
        if not has_layout and self._tabs.select() == str(self._layout):
            self._tabs.select(self._form)
        self._refresh_views()
        self.changed()

    # -- saving -------------------------------------------------------------------------
    @property
    def dirty(self) -> bool:
        return bool(self._path) and self._current_text() != self._saved_text

    def leave(self) -> bool:
        if not self.dirty:
            return True
        answer = messagebox.askyesnocancel("Unsaved DBX text", "Save changes before leaving this file?",
                                           parent=self.page)
        if answer is None:
            return False
        if answer:
            return self.save()
        self.discard()
        return True

    def discard(self) -> None:
        self._open(None if self._new else self._path)

    def save(self) -> bool:
        if not self._path:
            return False
        text = self._current_text()
        encoded_text = text.replace("\n", self._line_ending)
        problems = dbx.check(text)
        if problems and not messagebox.askyesno(
                "DBX text has problems",
                "\n".join(problems[:12]) + ("\n…" if len(problems) > 12 else "")
                + "\n\nThe fields after a problem are lost to the Form and Layout tabs, and the game may not "
                  "read them either. Save anyway?", icon="warning", default="no", parent=self.page):
            return False
        try:
            if self._new:
                battle_tables.add_entry(self.project, self._path, encoded_text)
                verb = "Added"
            elif text != self._saved_text:
                battle_tables.write_entry(self.project, self._path, encoded_text)
                verb = "Edited"
            else:
                return True
        except (ProjectError, OSError, ValueError) as exc:
            self.error(self.display_name, exc)
            return False
        self._after_change(f"{verb} {self._path}", self._path)
        return True

    def _after_change(self, message: str, path: str | None) -> None:
        self.changelog.append(self.display_name, message)
        self._saved_text = self._current_text()
        self._new = False
        self.reload(path)
        self.status(message + ".")

    def _add(self) -> None:
        if not self.leave():
            return
        name = simpledialog.askstring("Add DBX", "Archive path (for example xcam/new_script.dbx):", parent=self.page)
        if name is None:
            return
        try:
            path = battle_tables.validate_entry_name(name.strip())
            if any(n.casefold() == path.casefold() for n in self._inventory):
                raise ProjectError(f"zdbx.cmp already has {path}; select it to restore or edit it.")
        except ProjectError as exc:
            self.error(self.display_name, exc)
            return
        self.page.select(None)
        self._open(path, new=True)
        self.status("Enter DBX text, then Save to add the file.")

    def _delete(self) -> None:
        path = self._path
        if not path or self._new or self._inventory.get(path) == "deleted" or not self.leave():
            return
        if not messagebox.askyesno("Delete DBX", f"Delete {path} from zdbx.cmp?\n\nOriginal entries can be "
                                   "restored here.", parent=self.page):
            return
        try:
            battle_tables.remove_entry(self.project, path)
        except (ProjectError, OSError) as exc:
            self.error(self.display_name, exc)
            return
        self._after_change(f"Deleted {path}", path)

    def _restore(self) -> None:
        path = self._path
        if not path or self._new or self._inventory.get(path) not in ("edited", "deleted", "added") \
                or not self.leave():
            return
        try:
            battle_tables.restore_entry(self.project, path)
        except (ProjectError, OSError) as exc:
            self.error(self.display_name, exc)
            return
        self._after_change(f"Restored {path}", path)


class Fe10BattleAdapter(BrowserAdapter):
    display_name = "Battle Data"
    source = "FE10Battle.cms"
    note = "Each table's rows. Names and decoded links are editable; the other fields are shown read-only."
    label_title = "Table / row"
    columns = (("strings", "Names", 300), ("words", "Values", 300))
    keeps_changes = True

    def __init__(self, project: ModProject, changelog: ChangeLog):
        super().__init__(project, changelog)
        self._data: bytes | None = None
        self._document: fe10_battle.Fe10Battle | None = None
        self._dirty = False

    # -- list -------------------------------------------------------------------------
    def load(self) -> list[Group]:
        if self._data is None or not self._dirty:
            self._data = self.project.read_logical("battle_data")
        self._document = doc = fe10_battle.read_fe10_battle(self._data)
        groups = []
        for table in doc.tables:
            group = Group(table.name, table.name, info=f"{len(table.records)} × {table.record_size} B")
            for index, record in enumerate(table.records):
                strings = "; ".join(f"+{offset:#04x} {value or '(null)'}" for offset, value in record.strings)
                group.items.append(Item(f"{table.name}:{index}", (strings, self._values(table, index)),
                                        label=f"{table.name} #{index}"))
            groups.append(group)
        arrays = Group("arrays", "Camera arrays", info=f"{len(doc.arrays)} arrays")
        for name, data in doc.arrays:
            arrays.items.append(Item("array:" + name, ("", f"{len(data)} bytes"), label=name))
        groups.append(arrays)
        return groups

    def summary(self) -> str:
        doc = self._document
        text = (f"{len(doc.tables)} fixed-row tables, {len(doc.arrays)} camera arrays, "
                f"{len(doc.string_pool):,} string-pool bytes.")
        return text + (" Unsaved changes." if self._dirty else "")

    def _values(self, table: fe10_battle.BattleTable, index: int) -> str:
        doc = self._document
        if table.name == "FE10BMapModel":
            model = doc.map_models[index]
            return f"xyz {model.translation}; rot {model.rotation_value}; scale {model.scale_value}"
        if table.name == "FE10BMapData":
            return "model variants " + ", ".join("—" if v is None else str(v) for v in doc.map_data[index].model_indices)
        if table.name == "FE10BUnit":
            return f"{len(doc.unit_texture_sets[index].mappings)} texture mappings"
        if table.name == "FE10BTex":
            mapping = doc.texture_mappings[index]
            return f"{mapping.condition} → {mapping.texture_name}"
        words = table.records[index].words
        return " ".join(f"{word:08X}" for word in words[:8]) + (" …" if len(words) > 8 else "")

    def _row(self, key: str | None) -> tuple[fe10_battle.BattleTable, int] | None:
        if not key or key.startswith("array:") or self._document is None:
            return None
        name, _colon, index = key.rpartition(":")
        return self._document.table(name), int(index)

    # -- editor -----------------------------------------------------------------------
    def build_detail(self, parent: ttk.Frame) -> None:
        self._title = ttk.Label(parent, text="Select a row", font=("Segoe UI", 12, "bold"))
        self._title.pack(anchor="w")
        self._detail = tk.Text(parent, wrap="word", font=("Consolas", 9), state="disabled")
        self._detail.pack(fill="both", expand=True, pady=(5, 0))

    def actions(self):
        return (("Edit names…", self._edit_strings), ("Edit scenery choice…", self._edit_map_variant))

    def show(self, key: str | None) -> None:
        if key and key.startswith("array:"):
            name = key[6:]
            data = dict(self._document.arrays)[name]
            self._title.configure(text=f"{name} — {len(data)} bytes")
            self._set_detail(" ".join(f"{value:02X}" for value in data[:512]) + (" …" if len(data) > 512 else ""))
            return
        row = self._row(key)
        if row is None:
            self._title.configure(text="Select a row")
            self._set_detail("")
            return
        table, index = row
        self._title.configure(text=f"{table.name} #{index} — {table.record_size} bytes")
        self._set_detail("\n".join(self._detail_lines(table, index)))

    def _detail_lines(self, table: fe10_battle.BattleTable, index: int) -> list[str]:
        doc = self._document
        record = table.records[index]
        lines = [f"Record {index}, file address {record.address:#x}", ""]
        if table.name == "FE10BMapModel":
            model = doc.map_models[index]
            lines += [f"Scenery archive: zbg/{model.archive_name}",
                      f"Sound group: {model.sound_group or '(none)'}", f"Flags: {model.flags:#04x}",
                      "Parameters +0x09..+0x0D: " + ", ".join(map(str, model.parameters)),
                      f"Translation: {model.translation}", f"Rotation value: {model.rotation_value}",
                      f"Scale value: {model.scale_value}", ""]
        elif table.name == "FE10BMapData":
            map_record = doc.map_data[index]
            lines += [f"Map key: {map_record.map_name}",
                      "Model variants: " + ", ".join("—" if v is None else str(v) for v in map_record.model_indices),
                      "Resolved: " + ", ".join(
                          (doc.map_model(map_record, variant).archive_name
                           if doc.map_model(map_record, variant) else "—") for variant in range(5)), ""]
        elif table.name == "FE10BUnit":
            texture_set = doc.unit_texture_sets[index]
            lines += [f"Unit/model: {texture_set.unit_name} / {texture_set.model_name}",
                      f"Texture mappings: {len(texture_set.mappings)}"]
            lines += [f"  {m.condition} → {m.texture_name}" for m in texture_set.mappings]
            lines.append("")
        elif table.name == "FE10BTex":
            mapping = doc.texture_mappings[index]
            lines += [f"Condition: {mapping.condition}", f"Texture: {mapping.texture_name}", ""]
        lines += [f"+{i * 4:03X}: {word:08X}" for i, word in enumerate(record.words)]
        if record.strings:
            lines += ["", "Relocated strings:"] + [f"+{offset:#04x}: {value or '(null)'}"
                                                     for offset, value in record.strings]
        return lines

    def _set_detail(self, text: str) -> None:
        self._detail.configure(state="normal")
        self._detail.delete("1.0", "end")
        self._detail.insert("1.0", text)
        self._detail.configure(state="disabled")

    # -- edits ----------------------------------------------------------------------------
    def _edit_strings(self) -> None:
        key = self.selected()
        row = self._row(key)
        if row is None or not row[0].records[row[1]].strings:
            messagebox.showinfo(self.display_name, "Select a row that has names.", parent=self.page)
            return
        table, index = row
        changed: dict[int, str] = {}
        for offset, value in table.records[index].strings:
            replacement = simpledialog.askstring(f"{table.name} row {index}", f"Relocated string at +{offset:#04x}:",
                                                 initialvalue=value, parent=self.page)
            if replacement is None:
                return
            if replacement != value:
                changed[offset] = replacement
        if not changed:
            return
        try:
            data = fe10_battle.update_battle_record(self._data, table.name, index, strings=changed)
        except (ValueError, IndexError) as exc:
            self.error("Could not edit battle data", exc)
            return
        self._edited(data, f"Edited {table.name} row {index} strings", key)

    def _edit_map_variant(self) -> None:
        key = self.selected()
        row = self._row(key)
        if row is None or row[0].name != "FE10BMapData":
            messagebox.showinfo(self.display_name, "Select an FE10BMapData row.", parent=self.page)
            return
        doc, map_index = self._document, row[1]
        map_record = doc.map_data[map_index]
        variant = simpledialog.askinteger(
            "Scenery variant", "Variant slot to edit (0–4).\n"
            "Slot 3 falls back to slot 2; every missing slot then falls back to slot 0.",
            parent=self.page, minvalue=0, maxvalue=4)
        if variant is None:
            return
        current = map_record.model_indices[variant]
        model_index = simpledialog.askinteger(
            "Scenery model",
            f"FE10BMapModel row for {map_record.map_name}, variant {variant}.\n"
            f"Use -1 for no direct model (the runtime fallback applies). Current: "
            f"{'-1' if current is None else current}.\n\n"
            "Model rows begin: " + ", ".join(
                f"{model.record_index}={model.archive_name}" for model in doc.map_models[:24]) + "…",
            parent=self.page, minvalue=-1, maxvalue=len(doc.map_models) - 1,
            initialvalue=-1 if current is None else current)
        if model_index is None:
            return
        replacement = None if model_index < 0 else model_index
        if replacement == current:
            return
        data = fe10_battle.set_map_model_variant(self._data, map_index, variant, replacement)
        self._edited(data, f"{map_record.map_name} variant {variant}: {current} -> {replacement}", key)

    def _edited(self, data: bytes, message: str, key: str | None) -> None:
        self._data = data
        self._dirty = True
        self.changelog.append("FE10Battle.cms", message)
        self.reload(key)
        self.status(message + " (unsaved).")

    # -- saving -------------------------------------------------------------------------
    @property
    def dirty(self) -> bool:
        return self._dirty

    def save(self) -> bool:
        if not self._dirty:
            return True
        try:
            self.project.write_logical("battle_data", self._data)
        except OSError as exc:
            self.error("Could not save FE10Battle.cms", exc)
            return False
        self._dirty = False
        self.changelog.append("FE10Battle.cms", "Saved battle-data changes")
        self.status("Saved FE10Battle.cms.")
        return True

    def discard(self) -> None:
        self._dirty = False
        self._data = None


def battle_data_viewer(parent: tk.Misc, project: ModProject, changelog: ChangeLog) -> EditorPanel:
    """The Battle Data page with the project's battle-data format (``GameProfile.battle_dialect``)."""
    adapter = Fe10BattleAdapter if project.profile.battle_dialect == "fe10" else DbxAdapter
    return BattleBrowser(parent, adapter(project, changelog))
