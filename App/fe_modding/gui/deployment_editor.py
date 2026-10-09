"""Deployment editor: browse and edit a chapter's unit deployment data
(who spawns where, as what class, at what level, with what items/AI).

Each ``dispos.cmp`` is LZ10-compressed and holds a small pak archive with up
to four difficulty variants (see fe_modding.formats.dispo's docstring). This
editor parses every variant into a ``dispo.DispoDocument`` on open, edits
the documents, and on save lays each variant out again
(``dispo.build_dispo()``), repacks and recompresses the whole ``dispos.cmp``;
an untouched variant comes out byte for byte as it was.

Because the document holds label *strings*, a field can be set to any label
(any PID/JID/IID/SID/SEQ...), not only the ones the file already uses.
"Add Unit" duplicates the selected unit into its section, "Delete Unit"
removes it. Flags, item flags and the army get checkboxes and lists
(``dispo_widgets``); "Edit Section..." (or double-clicking a section) edits
the section header: its army, the occupied-tile byte and the mode byte.

The chapter page shows no tab for this editor: it holds the chapter's
deployment data, and the Build tab (``map_builder.py``) shows and edits the
documents through ``document()``/``apply()``/``save()``.
"""

from __future__ import annotations

import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import Callable, Optional

from ..formats import dispo, lz10, pak
from .. import excel_io
from ..project import ModProject
from . import dispo_widgets
from .changelog import ChangeLog
from .editor_panel import EditorPanel


class DeploymentEditor(EditorPanel):
    display_name = "Deployment"

    def __init__(
        self,
        parent: tk.Misc,
        project: ModProject,
        changelog: ChangeLog,
        on_navigate_to_character: Optional[Callable[[str], None]] = None,
    ):
        super().__init__(parent)
        self._project = project
        self._changelog = changelog
        self._on_navigate_to_character = on_navigate_to_character
        self._current_path: Path | None = None
        self._pak_entries: list[pak.PakEntry] = []
        self._pak_contents: dict[str, bytes] = {}  # entry name -> bytes as loaded (untouched variants are written back as-is)
        self._pak_reserved: dict[str, int] = {}
        self._docs: dict[str, dispo.DispoDocument] = {}
        self._edited: set[str] = set()
        self._current_variant: str | None = None
        self._selected: tuple[str, int] | None = None  # (section name, unit index) in the current variant
        self._listeners: list[Callable[[], None]] = []
        self._dirty = False
        self._group_keys: list | None = None  # GroupData army keys, read on first use

        self._build_widgets()
        self._load_chapter_list()

    # -- layout -------------------------------------------------------------
    def _build_widgets(self) -> None:
        # Chapter selection is driven by the chapter page (see
        # select_chapter() below), not shown here - this listbox is kept as
        # internal selection state only.
        self._chapter_list = tk.Listbox(self, exportselection=False)
        self._chapter_list.bind("<<ListboxSelect>>", lambda e: self._on_chapter_selected())

        paned = ttk.PanedWindow(self, orient="horizontal")
        paned.pack(fill="both", expand=True)

        # left: variant picker
        left = ttk.Frame(paned, padding=8)
        paned.add(left, weight=1)
        self._empty_label = ttk.Label(left, text="", style="Muted.TLabel")
        self._empty_label.pack(anchor="w")
        ttk.Label(left, text="Difficulty variant").pack(anchor="w")
        self._variant_var = tk.StringVar()
        self._variant_combo = ttk.Combobox(left, textvariable=self._variant_var, state="readonly")
        self._variant_combo.pack(fill="x", pady=(4, 0))
        self._variant_combo.bind("<<ComboboxSelected>>", lambda e: self._load_variant())

        # middle: sections/units tree
        middle = ttk.Frame(paned, padding=8)
        paned.add(middle, weight=2)
        ttk.Label(middle, text="Sections / Units").pack(anchor="w")
        self._unit_tree = ttk.Treeview(middle, columns=("summary",), show="tree headings")
        self._unit_tree.heading("#0", text="Section")
        self._unit_tree.heading("summary", text="Character / Class")
        self._unit_tree.column("#0", width=180)
        self._unit_tree.pack(fill="both", expand=True, pady=(4, 0))
        self._unit_tree.bind("<<TreeviewSelect>>", lambda e: self._on_unit_selected())
        self._unit_tree.bind("<Double-Button-1>", self._on_tree_double_click)
        self._section_button = ttk.Button(middle, text="Edit Section...", command=self._edit_section, state="disabled")
        self._section_button.pack(anchor="w", pady=(6, 0))

        # right: field table
        right = ttk.Frame(paned, padding=8)
        paned.add(right, weight=2)
        ttk.Label(right, text="Fields (double-click to edit)").pack(anchor="w")
        columns = ("index", "value")
        self._field_tree = ttk.Treeview(right, columns=columns, show="headings")
        self._field_tree.heading("index", text="#")
        self._field_tree.heading("value", text="Value")
        self._field_tree.column("index", width=140, stretch=False)
        self._field_tree.column("value", width=300)
        self._field_tree.pack(fill="both", expand=True, pady=(4, 0))
        self._field_tree.bind("<Double-Button-1>", lambda e: self._edit_selected_field())

        button_row = ttk.Frame(right)
        button_row.pack(fill="x", pady=(8, 0))
        self._save_button = ttk.Button(button_row, text="Save Chapter", command=self._save, state="disabled")
        self._save_button.pack(side="left")
        ttk.Button(button_row, text="Export Excel…", command=self._export_excel).pack(side="left", padx=(8, 0))
        ttk.Button(button_row, text="Import Excel…", command=self._import_excel).pack(side="left", padx=(6, 0))
        self._add_unit_button = ttk.Button(
            button_row, text="Add Unit (duplicate selected)", command=self._add_unit, state="disabled"
        )
        self._add_unit_button.pack(side="left", padx=(6, 0))
        self._delete_unit_button = ttk.Button(button_row, text="Delete Unit", command=self._delete_unit, state="disabled")
        self._delete_unit_button.pack(side="left", padx=(6, 0))
        self._status_label = ttk.Label(button_row, text="", style="Muted.TLabel")
        self._status_label.pack(side="left", padx=(8, 0))

    # -- data loading ---------------------------------------------------------
    def _load_chapter_list(self) -> None:
        self._chapter_paths = sorted(self._project.extracted_dir.glob("**/zmap/*/dispos.cmp"))
        self._chapter_list.delete(0, "end")
        for path in self._chapter_paths:
            self._chapter_list.insert("end", path.parent.name)

        self._empty_label.config(
            text="No deployment files found.\nExtract the project first." if not self._chapter_paths else ""
        )

    def _on_chapter_selected(self) -> None:
        selection = self._chapter_list.curselection()
        if not selection:
            return
        if self._dirty and not self._confirm_discard():
            self._chapter_list.selection_clear(0, "end")
            if self._current_path in self._chapter_paths:
                self._chapter_list.selection_set(self._chapter_paths.index(self._current_path))
            return

        path = self._chapter_paths[selection[0]]
        try:
            decompressed = lz10.decompress(path.read_bytes())
            entries = pak.read_pak_entries(decompressed)
            contents = {e.name: pak.read_pak_file_content(decompressed, e) for e in entries}
            docs = {name: dispo.parse_dispo(data) for name, data in contents.items() if name.startswith("dispos_")}
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror("Could not read chapter", str(exc), parent=self)
            return

        self._current_path = path
        self._pak_entries = entries
        self._pak_contents = contents
        self._pak_reserved = {e.name: e.reserved for e in entries}
        self._docs = docs
        self._edited = set()
        self._dirty = False
        variants = list(docs)
        self._variant_combo.config(values=variants)
        self._current_variant = None
        if variants:
            self._variant_var.set(variants[0])
            self._load_variant()
        self._notify()

    def _load_variant(self) -> None:
        variant = self._variant_var.get()
        if not variant or variant not in self._docs:
            return
        self._current_variant = variant
        self._selected = None
        self._refresh_unit_tree()
        self._save_button.config(state="normal")
        self._update_status()

    def _update_status(self) -> None:
        if self._dirty:
            self._status_label.config(text="Unsaved changes")
        elif self._current_variant:
            doc = self._docs[self._current_variant]
            self._status_label.config(text=f"{self._current_variant}: {sum(len(s.units) for s in doc.sections)} units")

    def _refresh_unit_tree(self) -> None:
        self._unit_tree.delete(*self._unit_tree.get_children())
        self._unit_index: dict[str, tuple[str, int]] = {}  # tree iid -> (section name, unit index)
        self._section_index: dict[str, str] = {}  # tree iid -> section name
        doc = self._docs.get(self._current_variant)
        if doc is not None:
            for si, section in enumerate(doc.sections):
                label = section.name + (f"  (-> {section.header!r})" if section.is_link else "")
                section_iid = f"s{si}"
                army = "" if section.is_link else                     "Army: " + dispo_widgets.group_text(dispo.section_header(section).group, self.group_keys())
                self._unit_tree.insert("", "end", iid=section_iid, text=label, values=(army,), open=False)
                self._section_index[section_iid] = section.name
                for ui, unit in enumerate(section.units):
                    unit_iid = f"s{si}u{ui}"
                    summary = f"{unit[dispo.FIELD['pid']] or '-'} / {unit[dispo.FIELD['jid']] or '-'}"
                    self._unit_tree.insert(section_iid, "end", iid=unit_iid, text="", values=(summary,))
                    self._unit_index[unit_iid] = (section.name, ui)
        self._field_tree.delete(*self._field_tree.get_children())
        self._add_unit_button.config(state="disabled")
        self._delete_unit_button.config(state="disabled")
        self._section_button.config(state="disabled")
        if self._selected is not None:
            self._show_unit(*self._selected)

    def _current_unit(self) -> list | None:
        if self._selected is None or self._current_variant is None:
            return None
        section = self._docs[self._current_variant].section(self._selected[0])
        if section is None or self._selected[1] >= len(section.units):
            return None
        return section.units[self._selected[1]]

    def _on_unit_selected(self) -> None:
        selection = self._unit_tree.selection()
        section = self._selected_section_name()
        self._section_button.config(state="normal" if section and not self._section_is_link(section) else "disabled")
        if not selection or selection[0] not in self._unit_index:
            return
        self._selected = self._unit_index[selection[0]]
        self._fill_fields()

    def _fill_fields(self) -> None:
        unit = self._current_unit()
        self._field_tree.delete(*self._field_tree.get_children())
        if unit is None:
            return
        self._add_unit_button.config(state="normal")
        self._delete_unit_button.config(state="normal")
        for index, value in enumerate(unit):
            name = dispo.field_name(index)
            label = f"{index} ({name})" if name else f"{index} (unread)"
            self._field_tree.insert("", "end", iid=str(index), values=(label, dispo.describe_field(index, value)))

    def _show_unit(self, section_name: str, index: int) -> None:
        iid = next((i for i, key in self._unit_index.items() if key == (section_name, index)), None)
        if iid is None:
            self._selected = None
            return
        self._selected = (section_name, index)
        self._unit_tree.item(iid.split("u")[0], open=True)
        self._unit_tree.selection_set(iid)
        self._unit_tree.see(iid)
        self._fill_fields()

    # -- shared-document API (the Build tab) ------------------------------------
    @property
    def current_path(self) -> Path | None:
        return self._current_path

    def variants(self) -> list[str]:
        return list(self._docs)

    @property
    def current_variant(self) -> str | None:
        return self._current_variant

    def document(self, variant: str) -> dispo.DispoDocument | None:
        return self._docs.get(variant)

    def add_listener(self, callback: Callable[[], None]) -> None:
        """``callback()`` runs after every change to the documents (and after
        a chapter loads)."""
        self._listeners.append(callback)

    def _notify(self) -> None:
        for callback in list(self._listeners):
            callback()

    def apply(self, edit: Callable[[dict[str, dispo.DispoDocument]], None], log_text: str | None, variants=None) -> None:
        """Run ``edit(documents)`` on the loaded variants, mark the chapter
        edited and refresh every view. ``variants`` names the variants the
        edit touches (all of them by default)."""
        edit(self._docs)
        self._edited.update(variants if variants is not None else self._docs)
        self._dirty = True
        self._refresh_unit_tree()
        self._update_status()
        if log_text and self._current_path is not None:
            self._changelog.append(self._current_path.parent.name, log_text)
        self._notify()

    def snapshot(self) -> dict[str, bytes]:
        """Every variant laid out as bytes, for undo."""
        return {name: dispo.build_dispo(doc) for name, doc in self._docs.items()}

    def restore(self, snapshot: dict[str, bytes]) -> None:
        self._docs = {name: dispo.parse_dispo(data) for name, data in snapshot.items()}
        self._edited.update(snapshot)
        self._dirty = True
        self._refresh_unit_tree()
        self._update_status()
        self._notify()

    def save(self) -> bool:
        return self._save()

    # -- editing ----------------------------------------------------------
    def _edit_selected_field(self) -> None:
        unit = self._current_unit()
        if unit is None:
            return
        selection = self._field_tree.selection()
        if not selection:
            return
        field_index = int(selection[0])
        choices = dispo.labels_by_prefix(self._docs.values())
        dialog = _FieldEditDialog(self, field_index, unit[field_index], choices,
                                  on_navigate_to_character=self._on_navigate_to_character)
        self.wait_window(dialog)
        if dialog.result is None:
            return
        variant, (section_name, index) = self._current_variant, self._selected
        value = dialog.result

        def edit(docs):
            docs[variant].section(section_name).units[index][field_index] = value

        name = dispo.field_name(field_index) or f"field {field_index}"
        self.apply(edit, f"{variant} {section_name}[{index}]: {name} = {value}", [variant])

    def group_keys(self) -> list:
        """The project's ``GroupData`` army keys (read once)."""
        if self._group_keys is None:
            self._group_keys = dispo_widgets.read_group_keys(self._project.extracted_dir / "files")
        return self._group_keys

    def _selected_section_name(self) -> str | None:
        selection = self._unit_tree.selection()
        if not selection:
            return None
        iid = selection[0]
        if iid in self._section_index:
            return self._section_index[iid]
        if iid in self._unit_index:
            return self._unit_index[iid][0]
        return None

    def _section_is_link(self, name: str) -> bool:
        section = self._docs[self._current_variant].section(name) if self._current_variant else None
        return section is None or section.is_link

    def _on_tree_double_click(self, event) -> None:
        if self._unit_tree.identify_row(event.y) in self._section_index:
            self._edit_section()

    def _edit_section(self) -> None:
        name = self._selected_section_name()
        if name is None or self._current_variant is None or self._section_is_link(name):
            return
        variant = self._current_variant
        header = dispo.section_header(self._docs[variant].section(name))
        dialog = dispo_widgets.SectionDialog(self, name, header, self.group_keys())
        self.wait_window(dialog)
        if dialog.result is None or dialog.result == header:
            return
        new = dialog.result
        self.apply(lambda docs: dispo.set_section_header(docs[variant].section(name), new),
                   f"{variant} {name}: army {new.group}, occupied tiles {new.occupied_ok}, mode {new.mode}", [variant])

    def _add_unit(self) -> None:
        unit = self._current_unit()
        if unit is None:
            return
        variant, (section_name, _index) = self._current_variant, self._selected
        pid, jid = unit[dispo.FIELD["pid"]], unit[dispo.FIELD["jid"]]
        if not messagebox.askyesno(
            "Add unit?",
            f"Add a new unit to section {section_name!r} by duplicating the selected unit "
            f"({pid} / {jid})? You can then edit its fields (position, items, ...) individually.",
            parent=self,
        ):
            return
        try:
            dispo.add_unit(self._docs[variant], section_name, list(unit))
        except ValueError as exc:
            messagebox.showerror("Could not add unit", str(exc), parent=self)
            return
        new_index = len(self._docs[variant].section(section_name).units) - 1
        self._selected = (section_name, new_index)
        self.apply(lambda docs: None, f"Added unit (duplicated {pid} / {jid}) to {section_name}", [variant])

    def _delete_unit(self) -> None:
        unit = self._current_unit()
        if unit is None:
            return
        variant, (section_name, index) = self._current_variant, self._selected
        pid = unit[dispo.FIELD["pid"]]
        if not messagebox.askyesno("Delete unit?", f"Delete {pid} from {section_name!r} in {variant}?", parent=self):
            return
        self._selected = None
        self.apply(lambda docs: dispo.remove_unit(docs[variant], section_name, index),
                   f"Deleted {pid} from {section_name}", [variant])

    # -- save -------------------------------------------------------------
    def _export_excel(self) -> None:
        if not self._docs:
            messagebox.showinfo("Export Excel", "Load a chapter first.", parent=self)
            return
        path = filedialog.asksaveasfilename(parent=self, title="Export deployment", defaultextension=".xlsx", filetypes=(("Excel workbook", "*.xlsx"),))
        if not path:
            return
        try:
            excel_io.export_fe8(path, b"", self._docs)
        except Exception as exc:
            # A deployment-only workbook does not need FE8Data; export the sheets directly.
            try:
                sheets = {}
                headers = ["section", "unit_index", "linked_label", *excel_io.DISPO_FIELDS]
                for name, doc in self._docs.items():
                    rows = [headers]
                    for section in doc.sections:
                        if section.is_link:
                            rows.append([section.name, "", section.header, *([""] * len(excel_io.DISPO_FIELDS))])
                        else:
                            rows.extend([[section.name, i, "", *unit] for i, unit in enumerate(section.units)])
                    sheets["Dispo " + name.removeprefix("dispos_").removesuffix(".bin")] = rows
                excel_io.write_workbook(path, sheets)
            except Exception as inner:
                messagebox.showerror("Could not export Excel", str(inner), parent=self)
                return
        self._status_label.config(text=f"Exported {Path(path).name}")

    def _import_excel(self) -> None:
        if not self._docs:
            messagebox.showinfo("Import Excel", "Load a chapter first.", parent=self)
            return
        path = filedialog.askopenfilename(parent=self, title="Import deployment", filetypes=(("Excel workbook", "*.xlsx"),))
        if not path:
            return
        try:
            _data, docs, errors = excel_io.import_fe8(path, b"", self._docs)
            if errors:
                messagebox.showerror("Excel import has errors", "\n".join(errors[:30]), parent=self)
                return
            self._docs = docs or self._docs
            self._edited.update(self._docs)
            self._dirty = True
            self._refresh_unit_tree()
            self._update_status()
            self._notify()
        except Exception as exc:
            messagebox.showerror("Could not import Excel", str(exc), parent=self)
    def _save(self) -> bool:
        if self._current_path is None:
            return False
        try:
            contents = dict(self._pak_contents)
            for variant in self._edited:
                contents[variant] = dispo.build_dispo(self._docs[variant])
            files = [(entry.name, contents[entry.name]) for entry in self._pak_entries]
            reserved = [self._pak_reserved[entry.name] for entry in self._pak_entries]
            new_compressed = lz10.compress(pak.pack_pak(files, reserved))
            self._project.write_keeping_original(self._current_path, new_compressed)
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror("Could not save chapter", str(exc), parent=self)
            return False
        self._pak_contents = contents
        self._dirty = False
        self._status_label.config(text=f"Saved {self._current_path.parent.name}/dispos.cmp")
        self._changelog.append(self._current_path.parent.name, "Saved deployment")
        self._notify()
        return True

    def _confirm_discard(self) -> bool:
        return messagebox.askyesno(
            "Discard changes?", "This chapter has unsaved changes. Discard them?", parent=self
        )

    # -- workspace navigation -------------------------------------------------
    def refresh_chapter_list(self) -> None:
        """Re-glob for chapter files - see dialogue_editor.py's version of
        this method for why it's needed."""
        self._load_chapter_list()

    def select_chapter(self, path: Path | None) -> None:
        if path is None or path not in self._chapter_paths:
            return
        if not self.confirm_navigate_away():
            return
        index = self._chapter_paths.index(path)
        self._chapter_list.selection_clear(0, "end")
        self._chapter_list.selection_set(index)
        self._chapter_list.see(index)
        self._on_chapter_selected()

    def select_unit(self, difficulty: str, section: str, unit_index: int) -> None:
        """Show one unit of the loaded chapter: difficulty letter (n/h/m/c),
        section name and index within the section."""
        variant = f"dispos_{difficulty}.bin"
        if variant not in self._docs:
            return
        if variant != self._current_variant:
            self._variant_var.set(variant)
            self._load_variant()
        self._show_unit(section, unit_index)


class _FieldEditDialog(tk.Toplevel):
    """Edit one field with the widget its kind needs: a label list for the
    pointer fields (any label, typed or picked from the ones the chapter's
    variants use, or 0 for none), checkboxes for the unit flags and the item
    flags, a list for the army, and a number for the rest."""

    def __init__(self, parent: tk.Misc, index: int, value, choices: dict[str, list[str]], on_navigate_to_character=None):
        super().__init__(parent)
        name = dispo.field_name(index)
        self.title(f"Edit field {index} ({name})" if name else f"Edit field {index}")
        self.resizable(False, False)
        self.result = None
        self._index = index
        self._pointer = index in dispo.POINTER_FIELDS
        offset, size, signed = dispo.FIELD_LAYOUT[index]
        self._range = (-(2 ** (size * 8 - 1)), 2 ** (size * 8 - 1) - 1) if signed else (0, 2 ** (size * 8) - 1)
        self._flags: dispo_widgets.FlagChecks | None = None

        frame = ttk.Frame(self, padding=12)
        frame.pack(fill="both", expand=True)
        ttk.Label(frame, text=dispo.FIELD_HELP.get(index, ""), wraplength=360, justify="left").pack(anchor="w")
        ttk.Label(frame, text=f"Current value: {dispo.describe_field(index, value)}",
                  style="Muted.TLabel").pack(anchor="w", pady=(2, 6))

        self._var = tk.StringVar(value=str(value))
        if self._pointer:
            prefix = value.split("_", 1)[0] if isinstance(value, str) else None
            options = choices.get(prefix, []) if prefix else sorted(label for labels in choices.values() for label in labels)
            ttk.Label(frame, text="Label (type any label, or 0 for none):", style="Muted.TLabel").pack(anchor="w")
            ttk.Combobox(frame, textvariable=self._var, values=options, width=36).pack(fill="x", pady=(0, 8))
        elif index == dispo.FIELD["flags"]:
            self._flags = dispo_widgets.FlagChecks(frame, value, dispo.FLAG_BITS, show_help=True)
            self._flags.pack(anchor="w", pady=(0, 8))
        elif index >= dispo.FIELD["item0_flag"]:
            self._flags = dispo_widgets.FlagChecks(frame, value, dispo.ITEM_FLAG_BITS, show_help=True)
            self._flags.pack(anchor="w", pady=(0, 8))
        elif index == dispo.FIELD["faction"]:
            self._var.set(dispo_widgets.faction_text(value))
            ttk.Combobox(frame, textvariable=self._var, values=dispo_widgets.faction_choices(), width=20).pack(
                anchor="w", pady=(0, 8))
        else:
            low, high = self._range
            if index == dispo.FIELD["level"]:
                low, high = 1, 40
            elif index == dispo.FIELD["laguz_gauge"]:
                low, high = 0, 20
            ttk.Label(frame, text=f"Valid range: {low} to {high}", style="Muted.TLabel").pack(anchor="w")
            ttk.Spinbox(frame, from_=low, to=high, textvariable=self._var, width=10).pack(anchor="w", pady=(0, 8))

        if isinstance(value, str) and value.startswith("PID_") and on_navigate_to_character is not None:
            ttk.Button(frame, text="View Stats...",
                       command=lambda: self._navigate_to_character(on_navigate_to_character, value)).pack(anchor="w", pady=(0, 8))

        button_row = ttk.Frame(frame)
        button_row.pack(fill="x", pady=(8, 0))
        ttk.Button(button_row, text="Cancel", command=self.destroy).pack(side="right")
        ttk.Button(button_row, text="Apply", command=self._on_apply).pack(side="right", padx=(0, 6))

        self.transient(parent)
        self.grab_set()

    def _navigate_to_character(self, on_navigate_to_character, pid_text: str) -> None:
        self.destroy()
        on_navigate_to_character(pid_text)

    def _on_apply(self) -> None:
        if self._flags is not None:
            self.result = self._flags.value()
            self.destroy()
            return
        text = self._var.get().strip()
        try:
            number = dispo_widgets.parse_leading_int(text) if self._index == dispo.FIELD["faction"] else int(text, 0)
        except ValueError:
            number = None
        if number is None and self._pointer and text:
            if not text.isascii() or " " in text:
                messagebox.showerror("Invalid value", "A label is ASCII without spaces.", parent=self)
                return
            self.result = text
        elif number is None:
            messagebox.showerror("Invalid value", "Enter a whole number.", parent=self)
            return
        elif not self._range[0] <= number <= self._range[1]:
            messagebox.showerror("Value out of range", f"{number} is outside {self._range[0]}..{self._range[1]}.", parent=self)
            return
        else:
            self.result = number
        self.destroy()
