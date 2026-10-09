"""The Build tab's Disposition window: the deployment file shown on the Build
canvas (``dispos_n/h/m/c.bin``) with all its sections.

- The left list shows every section: its name, unit count and army (link
  sections, like ``<map>_date_<d>``, are listed but hold no units).
- Selecting one shows its header (army, occupied-tile byte, mode - the
  ``dispo_widgets.SectionHeaderFrame`` the unit panel uses) and the chapter
  script functions that deploy it: every call whose string argument is the
  section's name, or that name without its difficulty letter (the prefix
  the ...Rank calls take), found with ``source_tools.string_references()``.
  Each function is a link to it in the Script tab.
- Below, a table of the section's units with their main fields. Double-click
  a cell to edit it in place; "All fields..." edits the rest.
- "Highlight the section's units on the map" outlines the selected
  section's units on the Build canvas and dims the others; "Show on map"
  scrolls the canvas to them.

Selecting a unit in the table selects it on the Build canvas (and the other
way round). Every edit goes through the :class:`~.map_builder.MapBuilder`,
so it is on the Build tab's Undo/Redo and follows "Same edit on every
difficulty" like the unit panel: shared fields reach the same unit in the
other files, level stays per file."""

from __future__ import annotations

import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from typing import Optional

from ..formats import dispo
from .. import excel_io
from . import dispo_widgets
from .map_builder import F, _LabelPicker
from .map_windows import _Window
from .widgets import Link

BYTE_RANGE = (-128, 127)
#: (column key, heading, width, kind); the key is the dispo field name. Kinds:
#: "characters"/"classes"/"items" (label pickers), "SEQ"/"MTYPE" (AI labels),
#: "number", "faction" and "flags".
COLUMNS = (
    ("pid", "Character", 130, "characters"),
    ("jid", "Class", 130, "classes"),
    ("level", "Lv", 36, "number"),
    ("faction", "Faction", 72, "faction"),
    ("pos_x", "X", 36, "number"),
    ("pos_y", "Y", 36, "number"),
    ("pos2_x", "To X", 44, "number"),
    ("pos2_y", "To Y", 44, "number"),
    *((f"item{i}", f"Item {i + 1}", 120, "items") for i in range(4)),
    ("seq_attack", "Attack AI", 130, "SEQ"),
    ("seq_move", "Move AI", 130, "SEQ"),
    ("mtype", "Movement AI", 110, "MTYPE"),
    ("ai_order", "Order", 46, "number"),
    ("flags", "Flags", 170, "flags"),
)
KINDS = {key: kind for key, _title, _width, kind in COLUMNS}


def _short(display: str, label: str) -> str:
    """"Iron Sword (IID_IRONSWORD)" -> "Iron Sword"."""
    suffix = f" ({label})"
    return display[: -len(suffix)] if display.endswith(suffix) and len(display) > len(suffix) else display


class DispositionWindow(_Window):
    """Every section of the shown deployment file; a section's header, the
    functions that deploy it and its units, editable in place."""

    def __init__(self, builder) -> None:
        super().__init__(builder, "Disposition", "1500x800")
        self._section: Optional[str] = None
        self._editor: Optional[tk.Widget] = None
        self._names: dict[str, dict[str, str]] = {}

        bar = ttk.Frame(self, padding=(8, 8, 8, 4))
        bar.pack(fill="x")
        ttk.Label(bar, text="Deployment file").pack(side="left")
        self._variant_var = tk.StringVar()
        self._variant_box = ttk.Combobox(bar, textvariable=self._variant_var, state="readonly", width=32)
        self._variant_box.pack(side="left", padx=(6, 12))
        self._variant_box.bind("<<ComboboxSelected>>", lambda e: self._variant_picked())
        ttk.Checkbutton(bar, text="Same edit on every difficulty", variable=builder.all_variants_var).pack(side="left")
        ttk.Button(bar, text="Export Excel…", command=self._export_excel).pack(side="left", padx=(10, 0))
        ttk.Button(bar, text="Import Excel…", command=self._import_excel).pack(side="left", padx=(6, 0))
        self._file_note = ttk.Label(bar, text="", style="Muted.TLabel")
        self._file_note.pack(side="right")

        paned = ttk.PanedWindow(self, orient="horizontal")
        paned.pack(fill="both", expand=True, padx=8, pady=(0, 8))

        left = ttk.Frame(paned)
        paned.add(left, weight=0)
        self._sections = ttk.Treeview(left, columns=("name", "units", "army"), show="headings", selectmode="browse")
        for key, title, width in (("name", "Section", 190), ("units", "Units", 50), ("army", "Army", 150)):
            self._sections.heading(key, text=title)
            self._sections.column(key, width=width, stretch=key == "name", anchor="e" if key == "units" else "w")
        bar = ttk.Scrollbar(left, orient="vertical", command=self._sections.yview)
        self._sections.configure(yscrollcommand=bar.set)
        bar.pack(side="right", fill="y")
        self._sections.pack(side="left", fill="both", expand=True)
        self._sections.bind("<<TreeviewSelect>>", lambda e: self._section_picked())

        right = ttk.Frame(paned, padding=(10, 0, 0, 0))
        paned.add(right, weight=1)
        self._section_panel = ttk.Frame(right)
        self._section_panel.pack(fill="x")

        tools = ttk.Frame(right)
        tools.pack(fill="x", pady=(10, 4))
        ttk.Label(tools, text="Units", font=("Segoe UI", 10, "bold")).pack(side="left")
        ttk.Label(tools, text="Double-click a cell to edit it; selecting a unit selects it on the map.",
                  style="Muted.TLabel").pack(side="left", padx=(10, 0))
        self._delete_button = ttk.Button(tools, text="Delete unit", command=self._delete_unit, state="disabled")
        self._delete_button.pack(side="right")
        self._raw_button = ttk.Button(tools, text="All fields...", command=self._raw_fields, state="disabled")
        self._raw_button.pack(side="right", padx=(0, 6))
        self._see_button = ttk.Button(tools, text="Show on map", command=self._see_section)
        self._see_button.pack(side="right", padx=(0, 12))
        self._highlight_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(tools, text="Highlight the section's units on the map", variable=self._highlight_var,
                        command=self._update_highlight).pack(side="right", padx=(0, 6))

        table = ttk.Frame(right)
        table.pack(fill="both", expand=True)
        self._table = ttk.Treeview(table, columns=["index"] + [c[0] for c in COLUMNS], show="headings",
                                   selectmode="browse")
        self._table.heading("index", text="#")
        self._table.column("index", width=36, stretch=False, anchor="e")
        for key, title, width, kind in COLUMNS:
            self._table.heading(key, text=title)
            self._table.column(key, width=width, stretch=False, anchor="e" if kind == "number" else "w")
        ybar = ttk.Scrollbar(table, orient="vertical", command=self._table.yview)
        xbar = ttk.Scrollbar(table, orient="horizontal", command=self._table.xview)
        self._table.configure(yscrollcommand=ybar.set, xscrollcommand=xbar.set)
        xbar.pack(side="bottom", fill="x")
        ybar.pack(side="right", fill="y")
        self._table.pack(side="left", fill="both", expand=True)
        self._table.bind("<<TreeviewSelect>>", lambda e: self._row_picked())
        self._table.bind("<Double-Button-1>", self._start_edit)
        self._table.bind("<Delete>", lambda e: self._delete_unit())
        for sequence in ("<MouseWheel>", "<Button-4>", "<Button-5>", "<Configure>"):
            self._table.bind(sequence, lambda e: self._cancel_edit(), add="+")

        self.units_changed()
        self.show_unit(builder.selected_unit())

    def _export_excel(self) -> None:
        docs = {variant: self.builder.document(variant) for variant in self.builder.variants()}
        docs = {variant: doc for variant, doc in docs.items() if doc is not None}
        if not docs:
            messagebox.showinfo("Export Excel", "No deployment data is loaded.", parent=self)
            return
        path = filedialog.asksaveasfilename(parent=self, title="Export disposition", defaultextension=".xlsx", filetypes=(("Excel workbook", "*.xlsx"),))
        if not path:
            return
        try:
            excel_io.export_fe8(path, b"", docs)
        except Exception as exc:
            messagebox.showerror("Could not export Excel", str(exc), parent=self)

    def _import_excel(self) -> None:
        docs = {variant: self.builder.document(variant) for variant in self.builder.variants()}
        docs = {variant: doc for variant, doc in docs.items() if doc is not None}
        if not docs:
            messagebox.showinfo("Import Excel", "No deployment data is loaded.", parent=self)
            return
        path = filedialog.askopenfilename(parent=self, title="Import disposition", filetypes=(("Excel workbook", "*.xlsx"),))
        if not path:
            return
        try:
            _data, imported, errors = excel_io.import_fe8(path, b"", docs)
            if errors:
                messagebox.showerror("Excel import has errors", "\n".join(errors[:30]), parent=self)
                return
            self.builder._deploy.apply(lambda _docs: None, "Imported deployment", variants=list(imported or docs))
            self.units_changed()
        except Exception as exc:
            messagebox.showerror("Could not import Excel", str(exc), parent=self)
    # -- data ----------------------------------------------------------------------------
    def _variant(self) -> Optional[str]:
        return self.builder.current_variant()

    def _doc(self) -> Optional[dispo.DispoDocument]:
        return self.builder.document(self._variant())

    def _current_section(self) -> Optional[dispo.DocSection]:
        doc = self._doc()
        return doc.section(self._section) if doc is not None and self._section else None

    def _army(self, section: dispo.DocSection) -> str:
        if section.is_link:
            return f"link to {section.header}"
        group = dispo.section_header(section).group
        if group:
            return dispo_widgets.group_text(group, self.builder.group_keys())
        if not section.units:
            return "empty"
        faction = section.units[0][F["faction"]]
        return dispo.FACTION_NAMES.get(faction, f"faction {faction}")

    def units_changed(self) -> None:
        """The deployment files changed, or the Build tab shows another one."""
        if not self.winfo_exists():
            return
        self._cancel_edit()
        self._names = {}
        variants = self.builder.variants()
        self._variant_box.configure(values=[self.builder.variant_name(v) for v in variants])
        variant = self._variant()
        self._variant_var.set(self.builder.variant_name(variant) if variant else "")
        doc = self._doc()
        self._sections.delete(*self._sections.get_children())
        if doc is None:
            self._file_note.configure(text="")
            self._section = None
            self._show_section()
            return
        count = 0
        for section in doc.sections:
            self._sections.insert("", "end", iid=section.name, values=(section.name, len(section.units),
                                                                       self._army(section)))
            count += len(section.units)
        self._file_note.configure(text=f"{len(doc.sections)} sections, {count} units")
        if self._section is not None and doc.section(self._section) is None:
            counterpart = dispo.counterpart_section(doc, self._section)  # another difficulty's file
            self._section = counterpart.name if counterpart is not None else None
        if self._section is None:
            first = next((s.name for s in doc.sections if not s.is_link), None)
            self._section = first or (doc.sections[0].name if doc.sections else None)
        if self._section is not None:
            self._sections.selection_set(self._section)
            self._sections.see(self._section)
        self._show_section()

    def _variant_picked(self) -> None:
        name = self._variant_var.get()
        variant = next((v for v in self.builder.variants() if self.builder.variant_name(v) == name), None)
        if variant is not None:
            self.builder.set_variant(variant)

    def _section_picked(self) -> None:
        selection = self._sections.selection()
        if selection and selection[0] != self._section:
            self._section = selection[0]
            self._show_section()

    # -- the section panel ---------------------------------------------------------------
    def _show_section(self) -> None:
        for child in self._section_panel.winfo_children():
            child.destroy()
        panel = self._section_panel
        section = self._current_section()
        if section is None:
            ttk.Label(panel, text="Select a section.", style="Muted.TLabel").pack(anchor="w")
            self._fill_table()
            return
        ttk.Label(panel, text=section.name, font=("Segoe UI", 12, "bold")).pack(anchor="w")
        columns = ttk.Frame(panel)
        columns.pack(fill="x", pady=(6, 0))

        header_box = ttk.Frame(columns)
        header_box.pack(side="left", anchor="n")
        ttk.Label(header_box, text="Header", font=("Segoe UI", 10, "bold")).pack(anchor="w", pady=(0, 2))
        if section.is_link:
            ttk.Label(header_box, text=f"A link section: it points at the label {section.header!r} and holds no "
                                       "units.", style="Muted.TLabel", wraplength=360, justify="left").pack(anchor="w")
        else:
            form = dispo_widgets.SectionHeaderFrame(header_box, dispo.section_header(section),
                                                    self.builder.group_keys())
            form.pack(anchor="w")
            ttk.Button(header_box, text="Apply header", command=lambda: self._apply_header(section.name, form)).pack(
                anchor="w", pady=(6, 0))

        loaders = ttk.Frame(columns, padding=(24, 0, 0, 0))
        loaders.pack(side="left", anchor="n", fill="x", expand=True)
        ttk.Label(loaders, text="Loaded by", font=("Segoe UI", 10, "bold")).pack(anchor="w", pady=(0, 2))
        refs, problem = self.builder.section_loaders(section.name)
        if problem is not None:
            ttk.Label(loaders, text=problem, style="Muted.TLabel", wraplength=520, justify="left").pack(anchor="w")
        elif not refs:
            ttk.Label(loaders, text="No function of the chapter script names this section. Another script (or "
                                    "a name built at run time) may still deploy it.",
                      style="Muted.TLabel", wraplength=520, justify="left").pack(anchor="w")
        base = dispo.section_base(section.name)
        for ref in refs:
            row = ttk.Frame(loaders)
            row.pack(anchor="w", pady=1)
            Link(row, f"{ref.function}()", lambda f=ref.function: self.builder.open_function(f)).pack(side="left")
            prefix = "  (name prefix)" if ref.value == base and base != section.name else ""
            ttk.Label(row, text=f"  line {ref.line}: {ref.call}(\"{ref.value}\"){prefix}",
                      style="Muted.TLabel").pack(side="left")
        if refs:
            ttk.Label(loaders, text="Click a function to open it in the Script tab.", style="Muted.TLabel").pack(
                anchor="w", pady=(4, 0))
        self._fill_table()

    def _update_highlight(self) -> None:
        section = self._current_section()
        on = self._highlight_var.get() and section is not None and bool(section.units)
        self.builder.highlight_section(self._variant() if on else None, section.name if on else None)

    def _see_section(self) -> None:
        if self._section is not None and self._variant():
            self.builder.see_section(self._variant(), self._section)

    def _apply_header(self, section_name: str, form: dispo_widgets.SectionHeaderFrame) -> None:
        try:
            header = form.header()
        except ValueError as exc:
            messagebox.showerror("Section", str(exc), parent=self)
            return
        self.builder.apply_section_header(self._variant(), section_name, header)

    # -- the unit table ------------------------------------------------------------------
    def _display_names(self, kind: str) -> dict[str, str]:
        """Label -> short display name for a label column."""
        if kind not in self._names:
            (characters, classes, items, _skills), _ai = self.builder.unit_choices()
            pairs = {"classes": classes, "items": items}.get(kind, [])
            self._names[kind] = {label: _short(display, label) for display, label in pairs}
        return self._names[kind]

    def _cell_text(self, key: str, value) -> str:
        kind = KINDS[key]
        if kind == "characters":
            return self.builder.character_name(value)
        if kind == "faction":
            return dispo.FACTION_NAMES.get(value, str(value))
        if kind == "flags":
            return ", ".join(dispo.flag_names(value)) if value else ""
        if kind in ("classes", "items"):
            return self._display_names(kind).get(value, value) if isinstance(value, str) else ("" if not value else str(value))
        if kind in ("SEQ", "MTYPE"):
            return value if isinstance(value, str) else ("" if not value else str(value))
        return str(value)

    def _fill_table(self) -> None:
        selected = self._selected_index()
        self._table.delete(*self._table.get_children())
        section = self._current_section()
        units = section.units if section is not None else []
        for i, unit in enumerate(units):
            self._table.insert("", "end", iid=str(i),
                               values=[i] + [self._cell_text(key, unit[F[key]]) for key, *_rest in COLUMNS])
        if selected is not None and selected < len(units):
            self._select_row(selected)
        self._update_buttons()
        self._update_highlight()

    def _selected_index(self) -> Optional[int]:
        selection = self._table.selection()
        return int(selection[0]) if selection else None

    def _select_row(self, index: Optional[int]) -> None:
        if index is None:
            self._table.selection_remove(self._table.selection())
        elif self._table.exists(str(index)):
            self._table.selection_set(str(index))
            self._table.see(str(index))
        self._update_buttons()

    def _update_buttons(self) -> None:
        state = "normal" if self._selected_index() is not None else "disabled"
        self._delete_button.configure(state=state)
        self._raw_button.configure(state=state)

    def _row_picked(self) -> None:
        self._update_buttons()
        index = self._selected_index()
        if index is not None and self._section is not None and self._variant():
            self.builder.show_unit(self._variant(), self._section, index)

    def show_unit(self, selection) -> None:
        """The Build canvas selected ``selection`` ((variant, section, index) or None)."""
        if not self.winfo_exists():
            return
        if selection is None:
            if self._selected_index() is not None:
                self._select_row(None)
            return
        variant, section_name, index = selection
        if variant != self._variant():
            return
        if section_name != self._section:
            self._section = section_name
            if self._sections.exists(section_name):
                self._sections.selection_set(section_name)
                self._sections.see(section_name)
            self._show_section()
        if self._selected_index() != index:
            self._select_row(index)

    def _delete_unit(self) -> None:
        index = self._selected_index()
        if index is not None and self._section is not None:
            self.builder.delete_unit(self._variant(), self._section, index)

    def _raw_fields(self) -> None:
        index = self._selected_index()
        if index is not None and self._section is not None:
            self.builder.open_raw_fields(self._variant(), self._section, index)

    # -- editing in place ----------------------------------------------------------------
    def _start_edit(self, event) -> None:
        self._cancel_edit()
        row = self._table.identify_row(event.y)
        column = self._table.identify_column(event.x)
        if not row or not column:
            return
        position = int(column.lstrip("#")) - 1  # 0 is the "#" column
        if position <= 0 or position > len(COLUMNS):
            return
        key = COLUMNS[position - 1][0]
        section = self._current_section()
        index = int(row)
        if section is None or index >= len(section.units):
            return
        value = section.units[index][F[key]]
        kind = KINDS[key]
        if kind == "flags":
            self._edit_flags(section.name, index, value)
            return
        bbox = self._table.bbox(row, column)
        if not bbox:
            return
        x, y, width, height = bbox
        editor = self._make_editor(kind, value)
        editor.place(x=x, y=y, width=max(width, 180 if kind not in ("number", "faction") else width + 20),
                     height=height)
        editor.focus_set()
        if isinstance(editor, ttk.Entry) and not isinstance(editor, ttk.Combobox):
            editor.select_range(0, "end")
        self._editor = editor
        commit = lambda e=None: self._commit_edit(section.name, index, key, value)
        editor.bind("<Return>", commit)
        editor.bind("<KP_Enter>", commit)
        editor.bind("<Escape>", lambda e: self._cancel_edit())
        editor.bind("<FocusOut>", lambda e: self.after(150, lambda: self._focus_left(editor, commit)))
        if isinstance(editor, ttk.Combobox):
            editor.bind("<<ComboboxSelected>>", commit)

    def _make_editor(self, kind: str, value) -> tk.Widget:
        if kind in ("characters", "classes", "items", "SEQ", "MTYPE"):
            (characters, classes, items, _skills), ai = self.builder.unit_choices()
            pairs = {"characters": characters, "classes": classes, "items": items}.get(kind)
            if pairs is None:
                pairs = [(label, label) for label in ai.get(kind, [])]
            picker = _LabelPicker(self._table, width=30)
            picker.set_choices(pairs)
            picker.set_label(value)
            return picker
        if kind == "faction":
            box = ttk.Combobox(self._table, values=list(dispo.FACTION_NAMES.values()), state="readonly")
            box.set(dispo.FACTION_NAMES.get(value, str(value)))
            return box
        entry = ttk.Entry(self._table)
        entry.insert(0, str(value))
        return entry

    def _focus_left(self, editor, commit) -> None:
        """Commit when the focus left the editor (not into its drop-down list)."""
        if self._editor is not editor or not editor.winfo_exists():
            return
        try:
            focus = self.focus_get()
        except KeyError:  # a combobox's drop-down list has the focus
            return
        if focus is not None and str(focus).startswith(str(editor)):
            return
        commit()

    def _read_editor(self, key: str):
        text = self._editor.get().strip()
        kind = KINDS[key]
        if kind in ("characters", "classes", "items", "SEQ", "MTYPE"):
            value = self._editor.label()
            if key == "pid" and not isinstance(value, str):
                raise ValueError("Choose a character.")
            return value
        if kind == "faction":
            return next(k for k, name in dispo.FACTION_NAMES.items() if name == text)
        try:
            value = int(text, 0)
        except ValueError:
            raise ValueError(f"{text!r} is not a whole number.") from None
        if not BYTE_RANGE[0] <= value <= BYTE_RANGE[1]:
            raise ValueError(f"{dispo.field_name(F[key])} is a byte: {BYTE_RANGE[0]} to {BYTE_RANGE[1]}.")
        return value

    def _commit_edit(self, section_name: str, index: int, key: str, old) -> None:
        if self._editor is None:
            return
        try:
            value = self._read_editor(key)
        except ValueError as exc:
            editor, self._editor = self._editor, None  # no second commit while the message shows
            messagebox.showerror("Disposition", str(exc), parent=self)
            self._editor = editor
            if editor.winfo_exists():
                editor.focus_set()
            return
        self._cancel_edit()
        if value != old:
            self.builder.edit_unit_fields(self._variant(), section_name, index, {F[key]: value})

    def _cancel_edit(self) -> None:
        editor, self._editor = self._editor, None
        if editor is not None and editor.winfo_exists():
            editor.destroy()
            self._table.focus_set()

    def _edit_flags(self, section_name: str, index: int, value: int) -> None:
        dialog = tk.Toplevel(self)
        dialog.title(f"Flags - {section_name} [{index}]")
        dialog.resizable(False, False)
        frame = ttk.Frame(dialog, padding=12)
        frame.pack(fill="both", expand=True)
        checks = dispo_widgets.FlagChecks(frame, value, dispo.FLAG_BITS, show_help=True)
        checks.pack(anchor="w")
        result = {}

        def ok() -> None:
            result["value"] = checks.value()
            dialog.destroy()

        buttons = ttk.Frame(frame)
        buttons.pack(anchor="e", pady=(10, 0))
        ttk.Button(buttons, text="OK", command=ok).pack(side="left")
        ttk.Button(buttons, text="Cancel", command=dialog.destroy).pack(side="left", padx=(6, 0))
        dialog.bind("<Escape>", lambda e: dialog.destroy())
        dialog.transient(self)
        dialog.grab_set()
        self.wait_window(dialog)
        if "value" in result and result["value"] != value:
            self.builder.edit_unit_fields(self._variant(), section_name, index, {F["flags"]: result["value"]})

    def close(self) -> None:
        self._cancel_edit()
        self.builder.highlight_section(None, None)
        super().close()
