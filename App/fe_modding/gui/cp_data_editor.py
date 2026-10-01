"""AI (CP) editor: ``cp_data.bin`` (see :mod:`fe_modding.formats.cp_data`).

The file holds the computer player's data. Five tabs edit it, and one Save
writes it back (the build copies the file into ``system.cmp``):

- **Attack / Move scripts** - the ``SEQ_*`` AI scripts a unit's dispo record
  (``seq_attack`` / ``seq_move``) names. Two views of the same script:
  *Readable code* (one line per entry, see :mod:`fe_modding.formats.cp_ai_lang`)
  and *Raw entries* (the opcode and its six words, with the field meanings
  from :mod:`fe_modding.formats.cp_ops`). Code is applied to the script when
  it compiles - on Apply, when switching tab or script, and on Save. The code
  you applied, comments included, is kept in ``ai_sources/SEQ_*.fe9ai`` next
  to the project and reused while it still matches the script.
- **Heal** - when a unit retreats and whether it tries healing items first.
- **Movement types** - the tile-scoring weights behind a unit's ``mtype``.
- **Steal items** - what the AI's thieves may take.
- **Routes & targets** - the waypoint lists scripts follow and the character
  lists they use as target filters.

Every script, heal record and movement type has an id: its position in the
matching id list, saved in the save file. New records are appended to their
list, so existing ids never move; deleting one that isn't last is refused.
"""

from __future__ import annotations

import threading
import tkinter as tk
from collections import namedtuple
from pathlib import Path
from tkinter import messagebox, simpledialog, ttk
from typing import Callable, Optional

from .. import fe8_references
from ..formats import cp_ai_lang as lang
from ..formats import cp_data as cp
from ..formats import cp_ops
from ..games import Game
from ..project import ModProject
from .changelog import ChangeLog
from .code_editor import CodeEditor
from .editor_panel import EditorPanel

FILE_NAME = "cp_data.bin"
SOURCES_DIR = "ai_sources"
ENTRY_COLUMNS = ("op", "name", "a", "b", "c", "d", "e", "f", "code")
_Completion = namedtuple("_Completion", "text label replace")
_KEYWORDS = ("goto", "if", "found", "not", "start", "True", "False", "None", "keep", "none")
_GROUPS = (("Flow", lambda op: op < 100 or op >= 1000), ("Actions", lambda op: 100 <= op < 200),
           ("Movement", lambda op: 200 <= op < 500), ("Registers", lambda op: 500 <= op < 1000))


def show_value(value: cp.Value) -> str:
    return lang.field_text(value)


class CpDataPanel(EditorPanel):
    display_name = "AI (CP)"

    def __init__(self, parent: tk.Misc, project: ModProject, changelog: ChangeLog,
                 session_provider: Callable[[], object] = lambda: None):
        super().__init__(parent)
        self._project = project
        self._changelog = changelog
        self._session_provider = session_provider
        self._path = project.extracted_dir / "files" / FILE_NAME
        self._doc: Optional[cp.CpDocument] = None
        self._dirty = False
        self._loading = False
        self._script: Optional[cp.Script] = None
        self._sources: dict[str, str] = {}  # applied readable code per script, comments included
        self._source_pending = False  # the code view has edits not yet applied
        self._source_lines: list[int] = []  # code line of each entry, from the last compile
        self._check_job = None
        self._names = lang.Names()
        self._value_lists: dict[str, list[str]] = {}
        self._build_widgets()
        self._load()

    @property
    def dirty(self) -> bool:
        return self._dirty or self._source_pending

    # -- layout ---------------------------------------------------------------------------
    def _build_widgets(self) -> None:
        bar = ttk.Frame(self, padding=(8, 8, 8, 4))
        bar.pack(fill="x")
        self._save_button = ttk.Button(bar, text="Save AI data", style="Accent.TButton", command=self.save,
                                       state="disabled")
        self._save_button.pack(side="left")
        self._status = ttk.Label(bar, text="", style="Muted.TLabel")
        self._status.pack(side="left", padx=(10, 0))
        self._message = ttk.Label(self, text="", style="Muted.TLabel", wraplength=900, justify="left", padding=(8, 2))
        self._message.pack(fill="x")
        self._notebook = ttk.Notebook(self)
        self._notebook.pack(fill="both", expand=True, padx=8, pady=(0, 8))
        self._build_scripts()
        self._build_heal()
        self._build_mtypes()
        self._build_steal()
        self._build_routes()

    def _tree(self, parent: tk.Misc, columns, widths, height: int = 14) -> ttk.Treeview:
        tree = ttk.Treeview(parent, columns=columns, show="headings", height=height, selectmode="browse")
        for column, width in zip(columns, widths):
            tree.heading(column, text=column)
            tree.column(column, width=width, anchor="w", stretch=column == columns[-1])
        return tree

    def _side_list(self, parent: tk.Misc, title: str, width: int = 260):
        frame = ttk.Frame(parent)
        frame.pack(side="left", fill="y", padx=(0, 8))
        ttk.Label(frame, text=title, style="Heading.TLabel").pack(anchor="w")
        tree = self._tree(frame, ("id", "name"), (36, width - 36), height=18)
        tree.pack(fill="y", expand=True, pady=(4, 0))
        return frame, tree

    # scripts
    def _build_scripts(self) -> None:
        page = ttk.Frame(self._notebook, padding=8)
        self._notebook.add(page, text="Attack / Move scripts")
        frame, self._script_list = self._side_list(page, "Scripts")
        self._script_list.configure(height=14)
        self._script_kind = tk.StringVar(value="attack")
        kinds = ttk.Frame(frame)
        kinds.pack(fill="x", before=self._script_list)
        for kind, text in (("attack", "Attack"), ("move", "Move")):
            ttk.Radiobutton(kinds, text=text, value=kind, variable=self._script_kind,
                            command=self._on_kind_changed).pack(side="left", padx=(0, 8))
        buttons = ttk.Frame(frame)
        buttons.pack(fill="x", pady=(4, 0))
        ttk.Button(buttons, text="Copy as new...", command=self._copy_script).pack(side="left")
        ttk.Button(buttons, text="Delete", command=self._delete_script).pack(side="left", padx=(6, 0))
        self._script_list.bind("<<TreeviewSelect>>", lambda e: self._select_script())
        uses = ttk.Frame(frame)
        uses.pack(fill="x", pady=(10, 0))
        ttk.Label(uses, text="Used by", style="Heading.TLabel").pack(side="left")
        ttk.Button(uses, text="Find", command=self._find_uses).pack(side="right")
        self._uses = tk.Listbox(frame, height=7, exportselection=False)
        self._uses.pack(fill="x", pady=(4, 0))

        right = ttk.Frame(page)
        right.pack(side="left", fill="both", expand=True)
        self._script_info = ttk.Label(right, text="", style="Muted.TLabel", wraplength=760, justify="left")
        self._script_info.pack(anchor="w")
        self._views = ttk.Notebook(right)
        self._views.pack(fill="both", expand=True, pady=(4, 0))
        self._build_code_view()
        self._build_raw_view()
        self._views.bind("<<NotebookTabChanged>>", lambda e: self._on_view_changed())
        self._current_view = 0

    def _build_code_view(self) -> None:
        page = ttk.Frame(self._views, padding=(0, 6, 0, 0))
        self._views.add(page, text="Readable code")
        tools = ttk.Frame(page)
        tools.pack(fill="x")
        ttk.Button(tools, text="Apply", command=self._apply_source).pack(side="left")
        ttk.Button(tools, text="Check", command=self._check_source).pack(side="left", padx=(6, 0))
        insert = ttk.Menubutton(tools, text="Insert")
        menu = tk.Menu(insert, tearoff=False)
        submenus = {title: tk.Menu(menu, tearoff=False) for title, _ in _GROUPS}
        for title, sub in submenus.items():
            menu.add_cascade(label=title, menu=sub)
        flow = submenus["Flow"]
        for label, text in lang.statement_templates()[:5]:
            flow.add_command(label=text, command=lambda t=text: self._insert_statement(t))
        for label, text in lang.statement_templates()[5:]:
            spec = cp_ops.BY_NAME[label]
            group = next(title for title, test in _GROUPS if test(spec.op))
            submenus[group].add_command(label=f"{text}    ({spec.op})",
                                        command=lambda t=text: self._insert_statement(t))
        insert["menu"] = menu
        insert.pack(side="left", padx=(6, 0))
        ttk.Button(tools, text="Reload from data", command=self._reload_source).pack(side="left", padx=(6, 0))
        self._source_state = ttk.Label(tools, text="", style="Muted.TLabel")
        self._source_state.pack(side="left", padx=(12, 0))
        panes = ttk.PanedWindow(page, orient="vertical")
        panes.pack(fill="both", expand=True, pady=(6, 0))
        self._code = CodeEditor(panes, completions=self._completions, signature=lang.signature,
                                is_known_call=lambda name: name in cp_ops.BY_NAME or name in ("op", "ref"),
                                on_change=self._on_source_changed,
                                on_status=lambda text: self._code_hint.configure(text=text))
        panes.add(self._code, weight=5)
        bottom = ttk.Frame(panes)
        panes.add(bottom, weight=1)
        self._code_hint = ttk.Label(bottom, text="", style="Muted.TLabel", wraplength=760, justify="left")
        self._code_hint.pack(anchor="w")
        self._problems = tk.Listbox(bottom, height=4)
        self._problems.pack(fill="both", expand=True)
        self._problems.bind("<<ListboxSelect>>", lambda e: self._goto_problem())
        self._problem_lines: list[int] = []

    def _build_raw_view(self) -> None:
        page = ttk.Frame(self._views, padding=(0, 6, 0, 0))
        self._views.add(page, text="Raw entries")
        self._entries = self._tree(page, ENTRY_COLUMNS, (44, 150, 50, 56, 50, 50, 140, 110, 260), height=10)
        self._entries.pack(fill="both", expand=True)
        self._entries.bind("<<TreeviewSelect>>", lambda e: self._select_entry())
        row = ttk.Frame(page)
        row.pack(fill="x", pady=(4, 0))
        for text, command in (("▲", lambda: self._move_entry(-1)), ("▼", lambda: self._move_entry(1)),
                              ("Insert below", self._insert_entry), ("Delete entry", self._delete_entry)):
            ttk.Button(row, text=text, width=3 if len(text) == 1 else None, command=command).pack(
                side="left", padx=(0, 4))
        form = ttk.Frame(page)
        form.pack(fill="x", pady=(8, 0))
        self._op_var = tk.StringVar()
        ttk.Label(form, text="Opcode").grid(row=0, column=0, sticky="w")
        self._op_box = ttk.Combobox(form, textvariable=self._op_var, width=34, state="readonly",
                                    values=[self._op_label(op) for op in sorted(cp_ops.OPS) if op >= 0])
        self._op_box.grid(row=0, column=1, columnspan=3, sticky="w", padx=4)
        self._op_box.bind("<<ComboboxSelected>>", lambda e: self._apply_entry())
        self._field_vars: dict[str, tk.StringVar] = {}
        self._field_boxes: dict[str, ttk.Combobox] = {}
        self._field_labels: dict[str, ttk.Label] = {}
        for i, key in enumerate("abcdef"):
            r, c = 1 + i // 3, (i % 3) * 2
            label = ttk.Label(form, text=key)
            label.grid(row=r, column=c, sticky="e", pady=2, padx=(8, 0))
            var = tk.StringVar()
            box = ttk.Combobox(form, textvariable=var, width=24 if key in "ef" else 14)
            box.grid(row=r, column=c + 1, sticky="w", padx=4)
            box.bind("<Return>", lambda e: self._apply_entry())
            box.bind("<FocusOut>", lambda e: self._apply_entry())
            box.bind("<<ComboboxSelected>>", lambda e: self._apply_entry())
            self._field_vars[key] = var
            self._field_boxes[key] = box
            self._field_labels[key] = label
        self._op_help = ttk.Label(page, text="", style="Muted.TLabel", wraplength=760, justify="left")
        self._op_help.pack(anchor="w", pady=(6, 0))

    @staticmethod
    def _op_label(op: int) -> str:
        spec = cp_ops.OPS.get(op)
        return f"{op}  {spec.key}  ({spec.name})" if spec else str(op)

    # heal
    def _build_heal(self) -> None:
        page = ttk.Frame(self._notebook, padding=8)
        self._notebook.add(page, text="Heal")
        frame, self._heal_list = self._side_list(page, "Heal behaviours", 240)
        self._heal_list.bind("<<TreeviewSelect>>", lambda e: self._select_heal())
        form = ttk.Frame(page)
        form.pack(side="left", fill="both", expand=True)
        self._heal_vars: dict[str, tk.IntVar] = {}
        rows = (("retreat_below", "Retreat below HP %", "The unit starts retreating to heal when its HP drops under this."),
                ("resume_at", "Stop retreating at HP %", "Once retreating, it keeps going until its HP reaches this."),
                ("priority", "Try healing items first (0/1)", "Non-zero: the unit uses its own healing items before moving."))
        for r, (key, text, hint) in enumerate(rows):
            ttk.Label(form, text=text).grid(row=r, column=0, sticky="w", pady=4)
            var = tk.StringVar()
            spin = ttk.Spinbox(form, from_=0, to=255, width=6, textvariable=var, command=self._apply_heal)
            spin.grid(row=r, column=1, padx=8)
            spin.bind("<FocusOut>", lambda e: self._apply_heal())
            spin.bind("<Return>", lambda e: self._apply_heal())
            ttk.Label(form, text=hint, style="Muted.TLabel").grid(row=r, column=2, sticky="w")
            self._heal_vars[key] = var

    # movement types
    def _build_mtypes(self) -> None:
        page = ttk.Frame(self._notebook, padding=8)
        self._notebook.add(page, text="Movement types")
        frame, self._mtype_list = self._side_list(page, "Movement types", 240)
        self._mtype_list.bind("<<TreeviewSelect>>", lambda e: self._select_mtype())
        form = ttk.Frame(page)
        form.pack(side="left", fill="both", expand=True)
        ttk.Label(form, style="Muted.TLabel", wraplength=700, justify="left", text=(
            "How a unit scores the tiles it could attack from: every weight multiplies one term of the score "
            "(signed, -128 to 127). The highest-scoring tile wins.")).grid(row=0, column=0, columnspan=6,
                                                                           sticky="w", pady=(0, 6))
        self._mtype_vars: dict[str, tk.StringVar] = {}
        fields = [f for f in cp.MTYPE_FIELDS if f[1] != "id"]
        for i, (_, key, text) in enumerate(fields):
            r, c = 1 + i % 10, (i // 10) * 3
            ttk.Label(form, text=key.replace("_", " ")).grid(row=r, column=c, sticky="w", pady=2, padx=(0, 6))
            var = tk.StringVar()
            spin = ttk.Spinbox(form, from_=-128, to=127, width=6, textvariable=var, command=self._apply_mtype)
            spin.grid(row=r, column=c + 1)
            spin.bind("<FocusOut>", lambda e: self._apply_mtype())
            spin.bind("<Return>", lambda e: self._apply_mtype())
            self._tip(spin, text)
            ttk.Label(form, text="", width=3).grid(row=r, column=c + 2)
            self._mtype_vars[key] = var
        self._mtype_help = ttk.Label(form, text="", style="Muted.TLabel", wraplength=700)
        self._mtype_help.grid(row=12, column=0, columnspan=6, sticky="w", pady=(8, 0))

    def _tip(self, widget: tk.Misc, text: str) -> None:
        widget.bind("<Enter>", lambda e: self._mtype_help.configure(text=text), add="+")

    # steal
    def _build_steal(self) -> None:
        page = ttk.Frame(self._notebook, padding=8)
        self._notebook.add(page, text="Steal items")
        ttk.Label(page, style="Muted.TLabel", wraplength=700, justify="left",
                  text="Items an AI thief may steal (TBL_STEALITEMS). Earlier items are preferred.").pack(anchor="w")
        self._steal_list = self._tree(page, ("item",), (300,), height=16)
        self._steal_list.pack(side="left", fill="y", pady=(4, 0))
        side = ttk.Frame(page)
        side.pack(side="left", fill="y", padx=8, pady=(4, 0))
        self._steal_var = tk.StringVar()
        self._steal_box = ttk.Combobox(side, textvariable=self._steal_var, width=28)
        self._steal_box.pack()
        ttk.Button(side, text="Add", command=self._add_steal).pack(fill="x", pady=(4, 0))
        ttk.Button(side, text="Remove selected", command=self._remove_steal).pack(fill="x", pady=(4, 0))

    # routes & targets
    def _build_routes(self) -> None:
        page = ttk.Frame(self._notebook, padding=8)
        self._notebook.add(page, text="Routes & targets")
        frame, self._table_list = self._side_list(page, "Tables", 260)
        self._table_list.heading("id", text="kind")
        self._table_list.bind("<<TreeviewSelect>>", lambda e: self._select_table())
        right = ttk.Frame(page)
        right.pack(side="left", fill="both", expand=True)
        self._table_info = ttk.Label(right, text="", style="Muted.TLabel", wraplength=700, justify="left")
        self._table_info.pack(anchor="w")
        self._table_items = self._tree(right, ("#", "value"), (40, 260), height=14)
        self._table_items.pack(fill="both", expand=True, pady=(4, 0))
        row = ttk.Frame(right)
        row.pack(fill="x", pady=(4, 0))
        self._table_var = tk.StringVar()
        ttk.Entry(row, textvariable=self._table_var, width=24).pack(side="left")
        ttk.Button(row, text="Add", command=self._add_table_item).pack(side="left", padx=4)
        ttk.Button(row, text="Remove selected", command=self._remove_table_item).pack(side="left")
        ttk.Label(right, style="Muted.TLabel",
                  text="Route points are typed as x,y. Target lists take PID_ names.").pack(anchor="w", pady=(4, 0))

    # -- loading --------------------------------------------------------------------------
    def _load(self) -> None:
        self._doc = None
        self._dirty = False
        self._source_pending = False
        self._script = None
        if self._project.game != Game.PATH_OF_RADIANCE:
            self._message.configure(text="The AI data editor works on Path of Radiance projects only.")
            return
        if not self._path.is_file():
            self._message.configure(text=f"{FILE_NAME} was not found in the extracted files.")
            return
        try:
            self._doc = cp.parse_cp_data(self._path.read_bytes())
        except Exception as exc:  # noqa: BLE001
            self._message.configure(text=f"Could not read {FILE_NAME}: {exc}")
            return
        self._sources = self._read_sources()
        problems = cp.id_problems(self._doc)
        self._message.configure(text=("Warning: " + "; ".join(problems[:3])) if problems else (
            "AI scripts, movement scoring, heal thresholds and thief targets. Ids are positions in the id lists; "
            "new records are appended."))
        self._refresh_choices()
        self._fill_scripts()
        self._fill_heal()
        self._fill_mtypes()
        self._fill_steal()
        self._fill_tables()
        self._update_status()

    def _sources_dir(self) -> Path:
        return Path(self._project.directory) / SOURCES_DIR

    def _read_sources(self) -> dict[str, str]:
        sources = {}
        folder = self._sources_dir()
        if folder.is_dir():
            for path in folder.glob("*.fe9ai"):
                try:
                    sources[path.stem] = path.read_text(encoding="utf-8")
                except OSError:
                    pass
        return sources

    def _refresh_choices(self) -> None:
        session = self._session_provider()
        fe8 = getattr(session, "fe8", None) if session is not None else None
        iids = sorted(i.iid for i in fe8.items if i.iid) if fe8 is not None else []
        pids = sorted({c.pid for c in fe8.characters if getattr(c, "pid", None)}) if fe8 is not None else []
        jids = sorted({c.jid for c in fe8.classes if getattr(c, "jid", None)}) if fe8 is not None else []
        sids = sorted(s.sid for s in fe8.skills if s.sid) if fe8 is not None else []
        tables = self._doc.names("TBL_")
        attack, move = cp.attack_scripts(self._doc), cp.move_scripts(self._doc)
        self._names = lang.Names(pids=set(pids), jids=set(jids), iids=set(iids), sids=set(sids),
                                 attack_scripts=set(attack), move_scripts=set(move),
                                 sections={s.name for s in self._doc.sections})
        self._value_lists = {
            "pid": pids, "jid": jids, "iid": iids, "sid": sids, "seq": sorted(attack + move),
            "pid_table": [t for t in tables if t.startswith("TBL_PID_")],
            "route": [t for t in tables if t.startswith("TBL_MAP")],
            "tiles": [t for t in tables if t.startswith("TBL_MAP")],
            "bool": ["False", "True"],
        }
        self._choices = sorted(set(iids + pids + jids + sids + tables + attack + move))
        self._steal_box["values"] = iids

    def _update_status(self) -> None:
        self._save_button.configure(state="normal" if self.dirty else "disabled")
        self._status.configure(text="Unsaved changes" if self.dirty else "")

    def _changed(self, description: str) -> None:
        self._dirty = True
        self._changelog.append(FILE_NAME, description)
        self._update_status()

    # -- scripts --------------------------------------------------------------------------
    def _script_names(self) -> list[str]:
        if self._doc is None:
            return []
        return cp.attack_scripts(self._doc) if self._script_kind.get() == "attack" else cp.move_scripts(self._doc)

    def _on_kind_changed(self) -> None:
        if not self._leave_source():
            self._script_kind.set("move" if self._script_kind.get() == "attack" else "attack")
            return
        self._fill_scripts()

    def _fill_scripts(self, select: Optional[str] = None) -> None:
        self._loading = True
        self._script_list.delete(*self._script_list.get_children())
        names = self._script_names()
        for index, name in enumerate(names):
            self._script_list.insert("", "end", iid=name, values=(index, name))
        self._loading = False
        if names:
            target = select if select in names else names[0]
            self._script_list.selection_set(target)
            self._script_list.see(target)
            self._select_script()
        else:
            self._script = None
            self._entries.delete(*self._entries.get_children())

    def _select_script(self) -> None:
        selection = self._script_list.selection()
        if self._loading or not selection or self._doc is None:
            return
        if self._script is not None and selection[0] == self._script.name:
            return
        if not self._leave_source():
            self._loading = True
            self._script_list.selection_set(self._script.name)
            self._loading = False
            return
        self._script = cp.read_script(self._doc.section(selection[0]))
        self._uses.delete(0, "end")
        self._fill_entries()
        self._load_source()

    def _kind_of(self, name: str) -> str:
        return "attack" if name in cp.attack_scripts(self._doc) else "move"

    def _fill_entries(self, select: Optional[int] = None) -> None:
        self._entries.delete(*self._entries.get_children())
        script = self._script
        if script is None:
            return
        labels = cp.script_labels(script)
        kind = self._kind_of(script.name)
        self._script_info.configure(text=f"{script.name} - {kind} script, id {script.script_id}, "
                                         f"{len(script.entries)} entries, labels {labels}.")
        for i, (e, code) in enumerate(zip(script.entries, lang.entry_lines(script.entries))):
            self._entries.insert("", "end", iid=str(i), values=(
                e.op, cp_ops.OPS[e.op].key if e.op in cp_ops.OPS else "?",
                *(show_value(v) for v in (e.a, e.b, e.c, e.d, e.e, e.f)), code))
        if script.entries:
            index = min(select or 0, len(script.entries) - 1)
            self._entries.selection_set(str(index))
            self._entries.see(str(index))

    def _selected_entry(self) -> Optional[int]:
        selection = self._entries.selection()
        return int(selection[0]) if selection and self._script is not None else None

    def _select_entry(self) -> None:
        index = self._selected_entry()
        if index is None:
            return
        entry = self._script.entries[index]
        spec = cp_ops.OPS.get(entry.op)
        self._loading = True
        self._op_var.set(self._op_label(entry.op))
        for key in "abcdef":
            field = spec.field(key) if spec else None
            if field is not None:
                text, values = f"{key}  {field.name}", self._value_lists.get(field.kind, [])
            elif key == "b" and spec is not None:
                text, values = "b  threat limit", []
            else:
                text, values = f"{key}  (unused)" if spec else key, self._choices if key in "ef" else []
            if field is not None and field.kind == "label":
                values = ["0"] + [str(n) for n in cp.script_labels(self._script) if n]
            self._field_labels[key].configure(text=text)
            self._field_boxes[key]["values"] = values
            self._field_vars[key].set(show_value(getattr(entry, key)))
        self._op_help.configure(text=cp_ops.describe(entry.op))
        self._loading = False

    def _store_script(self, description: str) -> None:
        section = self._doc.section(self._script.name)
        cp.write_script(section, self._script)
        self._changed(f"{self._script.name}: {description}")

    def _after_raw_edit(self, select: int) -> None:
        """A raw edit changed the entries: refresh both views."""
        self._sources.pop(self._script.name, None)
        self._fill_entries(select)
        self._load_source()

    def _apply_entry(self) -> None:
        index = self._selected_entry()
        if index is None or self._loading:
            return
        entry = self._script.entries[index]
        try:
            op = int(self._op_var.get().split()[0])
            spec = cp_ops.OPS.get(op)
            values = {}
            for key in "abcdef":
                field = spec.field(key) if spec else None
                kind = field.kind if field is not None else "any"
                values[key] = lang.parse_field_text(self._field_vars[key].get(), kind)
        except (ValueError, IndexError) as exc:
            messagebox.showerror("Invalid value", str(exc), parent=self)
            return
        new = cp.Entry(op, **values)
        if op != entry.op and spec is not None and not spec.uses_b and entry.b == cp_ops.OPS.get(
                entry.op, spec).b_default:
            new.b = spec.b_default  # a new opcode starts with its own default threat limit word
        if new == entry:
            return
        self._script.entries[index] = new
        self._store_script(f"entry {index} set to {cp_ops.OPS[op].key if op in cp_ops.OPS else op}")
        self._after_raw_edit(index)

    def _insert_entry(self) -> None:
        if self._script is None or not self._leave_source():
            return
        index = self._selected_entry()
        position = len(self._script.entries) if index is None else index + 1
        self._script.entries.insert(position, cp.Entry(202, 0, 0xFFFF))  # a no-op to edit
        self._store_script(f"entry inserted at {position}")
        self._after_raw_edit(position)

    def _delete_entry(self) -> None:
        index = self._selected_entry()
        if index is None or not self._leave_source():
            return
        del self._script.entries[index]
        self._store_script(f"entry {index} deleted")
        self._after_raw_edit(index)

    def _move_entry(self, step: int) -> None:
        index = self._selected_entry()
        if index is None or not 0 <= index + step < len(self._script.entries) or not self._leave_source():
            return
        entries = self._script.entries
        entries[index], entries[index + step] = entries[index + step], entries[index]
        self._store_script(f"entry {index} moved to {index + step}")
        self._after_raw_edit(index + step)

    def _copy_script(self) -> None:
        if self._script is None or not self._leave_source():
            return
        name = simpledialog.askstring("Copy script", "Name of the new script (SEQ_...):", parent=self,
                                      initialvalue=self._script.name + "_COPY")
        if not name:
            return
        name = name.strip()
        if not name.startswith("SEQ_") or " " in name or not name.isascii() or self._doc.section(name):
            messagebox.showerror("Invalid name", "Use a new ASCII name starting with SEQ_ and no spaces.", parent=self)
            return
        kind_list = "ATK_SEQID_LIST" if self._script_kind.get() == "attack" else "MOV_SEQID_LIST"
        new_id = cp.add_to_id_list(self._doc, kind_list, name)
        section = cp.Section(name, [])
        cp.write_script(section, cp.Script(name, new_id, [cp.Entry(e.op, e.a, e.b, e.c, e.d, e.e, e.f)
                                                           for e in self._script.entries]))
        self._doc.sections.insert(self._doc.sections.index(self._doc.section(kind_list)), section)
        if self._script.name in self._sources:
            self._sources[name] = self._sources[self._script.name]
        self._changed(f"{name}: new script (id {new_id}) copied from {self._script.name}")
        self._refresh_choices()
        self._fill_scripts(select=name)

    def _delete_script(self) -> None:
        if self._script is None:
            return
        names = self._script_names()
        name = self._script.name
        if names[-1] != name:
            messagebox.showinfo("Cannot delete", "Only the last script of a list can be deleted: later scripts' ids "
                                "are saved in save files and must not move.", parent=self)
            return
        users = [s.name for s in self._doc.sections if s.name != name and any(
            w == name for w in s.words) and s.name not in ("ATK_SEQID_LIST", "MOV_SEQID_LIST")]
        if users:
            messagebox.showinfo("Cannot delete", f"{', '.join(users[:4])} still point at {name}.", parent=self)
            return
        if not messagebox.askyesno("Delete script", f"Delete {name}? Dispo records naming it will stop working.",
                                   icon="warning", parent=self):
            return
        kind_list = "ATK_SEQID_LIST" if self._script_kind.get() == "attack" else "MOV_SEQID_LIST"
        items = cp.read_list(self._doc.section(kind_list))
        items.remove(name)
        cp.write_list(self._doc.section(kind_list), items)
        self._doc.sections.remove(self._doc.section(name))
        self._sources.pop(name, None)
        self._script = None
        self._source_pending = False
        self._changed(f"{name}: script deleted")
        self._refresh_choices()
        self._fill_scripts()

    # -- uses -----------------------------------------------------------------------------
    def _find_uses(self) -> None:
        if self._script is None:
            return
        name = self._script.name
        inside = [f"cp_data.bin: {s.name}" for s in self._doc.sections
                  if s.name != name and not s.name.endswith("_LIST") and name in s.words]
        self._uses.delete(0, "end")
        self._uses.insert("end", "Searching the game files...")

        def work():
            try:
                found = [str(r) for r in fe8_references.file_references(self._project, name)]
            except Exception as exc:  # noqa: BLE001
                found = [f"search failed: {exc}"]
            self.after(0, lambda: self._show_uses(name, inside + found))

        threading.Thread(target=work, daemon=True).start()

    def _show_uses(self, name: str, lines: list[str]) -> None:
        if self._script is None or self._script.name != name:
            return
        self._uses.delete(0, "end")
        for line in lines or ["nothing names it"]:
            self._uses.insert("end", line)

    # -- readable code --------------------------------------------------------------------
    def _load_source(self) -> None:
        """Show the script as code: the kept source while it still compiles to
        the same entries, else freshly decompiled."""
        script = self._script
        text = self._sources.get(script.name)
        if text is not None:
            result = lang.compile_source(text, check=False)
            if result.errors or result.entries != [lang._normalised(e) for e in script.entries]:
                text = None
        if text is None:
            text = lang.decompile(script, self._kind_of(script.name))
        self._code.set(text)
        self._source_pending = False
        self._check_source(quiet=True)
        self._update_source_state()

    def _reload_source(self) -> None:
        if self._script is None:
            return
        if self._source_pending and not messagebox.askyesno(
                "Reload code", "Throw away the code changes that aren't applied?", parent=self):
            return
        self._sources.pop(self._script.name, None)
        self._load_source()
        self._update_status()

    def _on_source_changed(self) -> None:
        if self._script is None:
            return
        self._source_pending = True
        self._update_source_state()
        self._update_status()
        if self._check_job is not None:
            self.after_cancel(self._check_job)
        self._check_job = self.after(400, lambda: self._check_source(quiet=True))

    def _update_source_state(self) -> None:
        self._source_state.configure(text="Code changes not applied yet" if self._source_pending else "")

    def _compile(self) -> lang.CompileResult:
        fallthrough = lang.fallthrough_labels(self._doc.sections, self._script.name)
        return lang.compile_source(self._code.get(), self._names, fallthrough)

    def _check_source(self, quiet: bool = False) -> Optional[lang.CompileResult]:
        self._check_job = None
        if self._script is None:
            return None
        result = self._compile()
        self._code.mark_diagnostics(result.diagnostics)
        self._source_lines = result.lines
        self._problems.delete(0, "end")
        self._problem_lines = []
        for d in result.diagnostics:
            self._problems.insert("end", str(d))
            self._problem_lines.append(d.line)
        if not quiet:
            errors = len(result.errors)
            warnings = len(result.diagnostics) - errors
            self._code_hint.configure(text=f"{len(result.entries)} entries, {errors} error(s), {warnings} warning(s).")
        return result

    def _apply_source(self) -> bool:
        """Compile the code into the script. False (and the problems shown) on errors."""
        if self._script is None:
            return True
        result = self._check_source(quiet=True)
        if result.errors:
            self._code_hint.configure(text=f"Not applied: {len(result.errors)} error(s), see the list below.")
            return False
        text = self._code.get()
        if result.entries != [lang._normalised(e) for e in self._script.entries]:
            self._script.entries = result.entries
            self._store_script(f"code applied ({len(result.entries)} entries)")
            self._fill_entries(self._entry_at_cursor())
        self._sources[self._script.name] = text
        self._source_pending = False
        self._update_source_state()
        self._update_status()
        self._code_hint.configure(text="Applied." + (f" {len(result.diagnostics)} warning(s)." if result.diagnostics
                                                    else ""))
        return True

    def _leave_source(self) -> bool:
        """Before leaving the current script's code: apply it. False keeps the user there."""
        if not self._source_pending or self._script is None:
            return True
        if self._apply_source():
            return True
        if messagebox.askyesno("Code has errors", f"The code of {self._script.name} has errors and can't be applied. "
                               "Throw away the changes?", icon="warning", parent=self):
            self._source_pending = False
            self._load_source()
            self._update_status()
            return True
        self._views.select(0)
        return False

    def _entry_at_cursor(self) -> int:
        line = self._code.cursor_line()
        index = 0
        for i, entry_line in enumerate(self._source_lines):
            if entry_line <= line:
                index = i
        return index

    def _on_view_changed(self) -> None:
        new = self._views.index(self._views.select())
        if new == self._current_view:
            return
        if new == 1:  # to raw
            if not self._leave_source():
                return
            self._fill_entries(self._entry_at_cursor())
        else:
            index = self._selected_entry()
            if index is not None and index < len(self._source_lines):
                self._code.goto_line(self._source_lines[index])
        self._current_view = new

    def _goto_problem(self) -> None:
        selection = self._problems.curselection()
        if selection and self._problem_lines[selection[0]] > 0:
            self._code.goto_line(self._problem_lines[selection[0]], select=True)

    def _insert_statement(self, text: str) -> None:
        line = self._code.cursor_line()
        current = self._code.text.get(f"{line}.0", f"{line}.end")
        if current.strip():
            self._code.replace_lines(line + 1, line, [text])
            self._code.goto_line(line + 1)
        else:
            self._code.replace_lines(line, line, [text])
            self._code.goto_line(line)
        self._on_source_changed()

    def _completions(self, before: str, after: str, force: bool) -> list:
        word = ""
        for ch in reversed(before):
            if ch.isalnum() or ch in "_.":
                word = ch + word
            else:
                break
        if not word and not force:
            return []
        prefix = before[:len(before) - len(word)]
        candidates: list[str] = []
        call = self._enclosing_call(prefix)
        if call is not None and prefix.rstrip().endswith("="):
            name, keyword = call, prefix.rstrip()[:-1].split("(")[-1].split(",")[-1].strip()
            kind = lang.field_kind_at(name, keyword)
            if kind == "label":
                candidates = ["start"] + [f"L{n}" for n in self._labels_in_code()]
            elif kind:
                candidates = self._value_lists.get(kind, [])
            elif keyword == "threat_limit":
                candidates = ["none", "keep"]
        elif call is not None:
            spec = cp_ops.BY_NAME.get(call)
            if spec is not None:
                candidates = [f.name + "=" for f in spec.fields if not (spec.form == "assign" and f.slot == "a")]
                if not spec.uses_b:
                    candidates.append("threat_limit=")
        elif prefix.rstrip().endswith("goto"):
            candidates = ["start"] + [f"L{n}" for n in self._labels_in_code()]
        else:
            candidates = lang.function_names() + list(_KEYWORDS)
        lowered = word.lower()
        matches = [c for c in candidates if c.lower().startswith(lowered) and c != word]
        if not matches and len(word) >= 3:
            matches = [c for c in candidates if lowered in c.lower() and c != word]
        return [_Completion(c, c, len(word)) for c in matches[:60]]

    @staticmethod
    def _enclosing_call(prefix: str) -> Optional[str]:
        depth = 0
        for i in range(len(prefix) - 1, -1, -1):
            ch = prefix[i]
            if ch == ")":
                depth += 1
            elif ch == "(":
                if depth == 0:
                    j = i
                    while j > 0 and (prefix[j - 1].isalnum() or prefix[j - 1] == "_"):
                        j -= 1
                    return prefix[j:i] or None
                depth -= 1
        return None

    def _labels_in_code(self) -> list[int]:
        result = lang.compile_source(self._code.get(), check=False)
        return sorted({e.c for e in result.entries if e.op == 0 and isinstance(e.c, int) and e.c})

    # -- heal -----------------------------------------------------------------------------
    def _fill_heal(self, select: Optional[str] = None) -> None:
        self._heal_list.delete(*self._heal_list.get_children())
        for index, name in enumerate(cp.heal_records(self._doc)):
            self._heal_list.insert("", "end", iid=name, values=(index, name))
        names = cp.heal_records(self._doc)
        if names:
            self._heal_list.selection_set(select if select in names else names[0])

    def _select_heal(self) -> None:
        selection = self._heal_list.selection()
        if not selection:
            return
        record = cp.read_heal(self._doc.section(selection[0]))
        self._loading = True
        for key, var in self._heal_vars.items():
            var.set(str(getattr(record, key)))
        self._loading = False

    def _apply_heal(self) -> None:
        selection = self._heal_list.selection()
        if not selection or self._loading:
            return
        section = self._doc.section(selection[0])
        record = cp.read_heal(section)
        try:
            for key, var in self._heal_vars.items():
                value = int(var.get())
                if not 0 <= value <= 255:
                    raise ValueError
                setattr(record, key, value)
        except ValueError:
            messagebox.showerror("Invalid value", "Use whole numbers from 0 to 255.", parent=self)
            return
        before = list(section.words)
        cp.write_heal(section, record)
        if section.words != before:
            self._changed(f"{record.name}: retreat {record.retreat_below}%, resume {record.resume_at}%, "
                          f"priority {record.priority}")

    # -- movement types ----------------------------------------------------------------------
    def _fill_mtypes(self, select: Optional[str] = None) -> None:
        self._mtype_list.delete(*self._mtype_list.get_children())
        names = cp.mtype_tables(self._doc)
        for index, name in enumerate(names):
            self._mtype_list.insert("", "end", iid=name, values=(index, name))
        if names:
            self._mtype_list.selection_set(select if select in names else names[0])

    def _select_mtype(self) -> None:
        selection = self._mtype_list.selection()
        if not selection:
            return
        mtype = cp.read_mtype(self._doc.section(selection[0]))
        self._loading = True
        for key, var in self._mtype_vars.items():
            var.set(str(mtype.values[key]))
        self._loading = False

    def _apply_mtype(self) -> None:
        selection = self._mtype_list.selection()
        if not selection or self._loading:
            return
        section = self._doc.section(selection[0])
        mtype = cp.read_mtype(section)
        try:
            for key, var in self._mtype_vars.items():
                value = int(var.get())
                if not -128 <= value <= 127:
                    raise ValueError
                mtype.values[key] = value
        except ValueError:
            messagebox.showerror("Invalid value", "Use whole numbers from -128 to 127.", parent=self)
            return
        before = list(section.words)
        cp.write_mtype(section, mtype)
        if section.words != before:
            self._changed(f"{mtype.name}: weights edited")

    # -- steal items --------------------------------------------------------------------------
    def _steal_section(self) -> cp.Section:
        return self._doc.section(cp.STEAL_SECTION)

    def _fill_steal(self) -> None:
        self._steal_list.delete(*self._steal_list.get_children())
        for i, item in enumerate(cp.read_list(self._steal_section())):
            self._steal_list.insert("", "end", iid=str(i), values=(item,))

    def _add_steal(self) -> None:
        iid = self._steal_var.get().strip()
        if not iid.startswith("IID_"):
            messagebox.showerror("Invalid item", "Pick or type an IID_ name.", parent=self)
            return
        section = self._steal_section()
        items = cp.read_list(section)
        if iid in items:
            return
        cp.write_list(section, items + [iid])
        self._changed(f"thieves may steal {iid}")
        self._fill_steal()

    def _remove_steal(self) -> None:
        selection = self._steal_list.selection()
        if not selection:
            return
        section = self._steal_section()
        items = cp.read_list(section)
        removed = items.pop(int(selection[0]))
        cp.write_list(section, items)
        self._changed(f"thieves may no longer steal {removed}")
        self._fill_steal()

    # -- routes & targets -----------------------------------------------------------------------
    def _fill_tables(self, select: Optional[str] = None) -> None:
        self._table_list.delete(*self._table_list.get_children())
        names = []
        for section in self._doc.sections:
            if cp.is_route_section(section) or cp.is_pid_table(section):
                kind = "route" if cp.is_route_section(section) else "targets"
                self._table_list.insert("", "end", iid=section.name, values=(kind, section.name))
                names.append(section.name)
        if names:
            self._table_list.selection_set(select if select in names else names[0])

    def _selected_table(self) -> Optional[cp.Section]:
        selection = self._table_list.selection()
        return self._doc.section(selection[0]) if selection else None

    def _select_table(self) -> None:
        section = self._selected_table()
        self._table_items.delete(*self._table_items.get_children())
        if section is None:
            return
        route = cp.is_route_section(section)
        self._table_info.configure(text=(
            f"{section.name}: waypoints an AI unit walks along (follow_route, opcode 216), or the tiles "
            "rock_attack_force tries." if route else
            f"{section.name}: characters a script's targets= filter names."))
        values = [f"{x}, {y}" for x, y in cp.read_route(section)] if route else [str(v) for v in cp.read_list(section)]
        for i, value in enumerate(values):
            self._table_items.insert("", "end", iid=str(i), values=(i, value))

    def _table_values(self, section: cp.Section) -> list:
        return cp.read_route(section) if cp.is_route_section(section) else cp.read_list(section)

    def _write_table(self, section: cp.Section, values: list) -> None:
        (cp.write_route if cp.is_route_section(section) else cp.write_list)(section, values)

    def _add_table_item(self) -> None:
        section = self._selected_table()
        text = self._table_var.get().strip()
        if section is None or not text:
            return
        values = self._table_values(section)
        if cp.is_route_section(section):
            try:
                x, y = (int(p) for p in text.replace(";", ",").split(","))
                if not (0 <= x < 0xFFFF and 0 <= y < 0xFFFF):
                    raise ValueError
            except ValueError:
                messagebox.showerror("Invalid point", "Type a point as x,y (whole numbers).", parent=self)
                return
            values.append((x, y))
        else:
            if not text.startswith("PID_"):
                messagebox.showerror("Invalid character", "Type a PID_ name.", parent=self)
                return
            values.append(text)
        self._write_table(section, values)
        self._changed(f"{section.name}: added {text}")
        self._select_table()

    def _remove_table_item(self) -> None:
        section = self._selected_table()
        selection = self._table_items.selection()
        if section is None or not selection:
            return
        values = self._table_values(section)
        removed = values.pop(int(selection[0]))
        self._write_table(section, values)
        self._changed(f"{section.name}: removed {removed}")
        self._select_table()

    # -- save -----------------------------------------------------------------------------------
    def save(self) -> bool:
        if self._doc is None:
            return True
        if not self._leave_source():
            return False
        try:
            problems = cp.id_problems(self._doc)
            if problems:
                raise ValueError("; ".join(problems[:3]))
            self._project.write_keeping_original(self._path, cp.build_cp_data(self._doc))
            self._write_sources()
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror("Could not save AI data", str(exc), parent=self)
            return False
        self._dirty = False
        self._changelog.append(FILE_NAME, "Saved")
        self._update_status()
        self._status.configure(text=f"Saved {FILE_NAME}")
        return True

    def _write_sources(self) -> None:
        """Keep the applied code of every script that has some (comments included)."""
        live = {s.name for s in self._doc.sections}
        folder = self._sources_dir()
        for name, text in self._sources.items():
            if name not in live:
                continue
            folder.mkdir(parents=True, exist_ok=True)
            with open(folder / f"{name}.fe9ai", "w", encoding="utf-8", newline="\n") as handle:
                handle.write(text)

    def _confirm_discard(self) -> bool:
        if not messagebox.askyesno("Discard changes?", "The AI data has unsaved changes. Discard them?",
                                   icon="warning", parent=self):
            return False
        self._load()
        return True
