"""Event script editor: edit a chapter's ``Scripts/CNN.cmb`` as readable
``.fe9s`` source (see :mod:`fe_modding.formats.cmb` and
``docs/app/script-language.md``).

The chapter's source text is the single source of truth. The function list,
the trigger form and the "Insert call" dialog are all ways of editing that
text; saving compiles it (with the current ``.cmb`` as the base, so
untouched content keeps its exact bytes) and writes the file.

The source itself - with the user's own names and comments, which bytecode
can't hold - is kept next to the project in ``script_sources/CNN.fe9s``. It
is reused on the next load only while it still compiles to the chapter's
current ``.cmb``; otherwise the file is decompiled fresh.
"""

from __future__ import annotations

import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk
from typing import Optional

from .. import script_sources
from ..exceptions import ProjectError
from ..script_suggestions import KIND_TITLES, ScriptSuggestions, chapter_of_script, resolve_kind
from ..formats.cmb import CompileError, compile_source
from ..formats.cmb.catalog import SPECIAL_ENTRY_POINTS, load_externs, triggers
from ..game_profile import profile_of
from ..formats.cmb.model import Label
from ..formats.cmb.parser import ParseError
from ..formats.cmb import source_tools as st
from ..project import ModProject
from .changelog import ChangeLog
from . import theme
from .code_editor import CodeEditor
from .editor_panel import EditorPanel

SOURCES_DIR = script_sources.SOURCES_DIR
_BUILTINS = ["printf", "streq", "strne", "lit", "strofs", "extern"]


def disassemble(fn) -> str:
    names = {}
    for item in fn.code:
        if isinstance(item, Label):
            names[id(item)] = f"L{len(names) + 1}"
    lines = []
    for item in fn.code:
        if isinstance(item, Label):
            lines.append(f"{names[id(item)]}:")
            continue
        ops = [names[id(o)] if isinstance(o, Label) else repr(o) for o in item.operands]
        lines.append(f"    {item.name:<18}{', '.join(ops)}")
    return "\n".join(lines)


class ScriptEditor(EditorPanel):
    display_name = "Scripts"

    def __init__(self, parent: tk.Misc, project: ModProject, changelog: ChangeLog):
        super().__init__(parent)
        self._project = project
        self._changelog = changelog
        self._current_path: Optional[Path] = None
        self._chapter_path: Optional[Path] = None  # the chapter page's script ("This chapter" in the File box)
        self._script: Optional[script_sources.LoadedScript] = None
        self._base = None  # ScriptFile of the .cmb as currently on disk
        self._spans: list[st.FunctionSpan] = []
        self._selected: Optional[str] = None
        self._compiled = None  # last successful CompileResult
        self._dirty = False
        self._reparse_job = None
        self._suggestions = ScriptSuggestions(project)
        self._dialect = profile_of(project).script_dialect  # the game's script language variant
        self._externs = load_externs(self._dialect)
        self._listeners: list = []

        self._build_widgets()

    # -- layout -------------------------------------------------------------
    def _build_widgets(self) -> None:
        toolbar = ttk.Frame(self, padding=(8, 6))
        toolbar.pack(fill="x")
        self._save_button = ttk.Button(toolbar, text="Save", command=self._save, state="disabled")
        self._save_button.pack(side="left")
        ttk.Button(toolbar, text="Check", command=self._check).pack(side="left", padx=(6, 0))
        ttk.Button(toolbar, text="Insert call…", command=self._insert_call).pack(side="left", padx=(6, 0))
        ttk.Button(toolbar, text="Revert to file", command=self._revert).pack(side="left", padx=(6, 0))
        self._file_var = tk.StringVar()
        self._file_box = ttk.Combobox(toolbar, textvariable=self._file_var, state="readonly", width=44)
        self._file_box.pack(side="right")
        self._file_box.bind("<<ComboboxSelected>>", lambda e: self._on_file_picked())
        ttk.Label(toolbar, text="File", style="Muted.TLabel").pack(side="right", padx=(12, 6))
        self._file_choices: list[tuple[str, Path]] = []
        self._status = ttk.Label(toolbar, text="Select a chapter.", style="Muted.TLabel")
        self._status.pack(side="left", padx=(12, 0))

        right_frame = ttk.Frame(self, padding=(8, 0, 8, 8))
        right_frame.pack(fill="both", expand=True)

        fn_row = ttk.Frame(right_frame)
        fn_row.pack(fill="x", pady=(0, 6))
        ttk.Label(fn_row, text="Function").pack(side="left")
        self._fn_var = tk.StringVar()
        self._fn_box = ttk.Combobox(fn_row, textvariable=self._fn_var, state="readonly", width=60, height=30)
        self._fn_box.pack(side="left", padx=(6, 0))
        self._fn_box.bind("<<ComboboxSelected>>", lambda e: self._on_function_selected())
        self._fn_index: Optional[int] = None  # index into self._spans of the chosen function
        ttk.Button(fn_row, text="New", command=self._new_function).pack(side="left", padx=(12, 0))
        ttk.Button(fn_row, text="Duplicate", command=self._duplicate_function).pack(side="left", padx=(4, 0))
        ttk.Button(fn_row, text="Delete", command=self._delete_function).pack(side="left", padx=(4, 0))

        self._form = TriggerForm(right_frame, self._apply_form, self._name_values, self._dialect)
        self._form.pack(fill="x")
        right = ttk.PanedWindow(right_frame, orient="vertical")
        right.pack(fill="both", expand=True, pady=(4, 0))

        self._tabs = ttk.Notebook(right)
        right.add(self._tabs, weight=5)
        self._editor = CodeEditor(
            self._tabs,
            completions=self._completions,
            signature=self._signature,
            is_known_call=self._is_known_call,
            on_change=self._on_text_changed,
            on_status=lambda text: self._hint.config(text=text),
        )
        self._tabs.add(self._editor, text="Code")
        self._editor.text.bind("<ButtonRelease-1>", lambda e: self.after_idle(self._sync_selection_to_cursor), add="+")
        bytecode_frame = ttk.Frame(self._tabs)
        self._bytecode = tk.Text(bytecode_frame, wrap="none", font=self._editor._font)
        scroll = ttk.Scrollbar(bytecode_frame, command=self._bytecode.yview)
        self._bytecode.configure(yscrollcommand=scroll.set)
        scroll.pack(side="right", fill="y")
        self._bytecode.pack(fill="both", expand=True)
        self._tabs.add(bytecode_frame, text="Bytecode")
        self._tabs.bind("<<NotebookTabChanged>>", lambda e: self._refresh_bytecode())

        bottom = ttk.Frame(right)
        right.add(bottom, weight=1)
        self._hint = ttk.Label(bottom, text="", style="Ok.TLabel")
        self._hint.pack(anchor="w")
        self._problems = tk.Listbox(bottom, height=5)
        self._problems.pack(fill="both", expand=True)
        self._problems.bind("<<ListboxSelect>>", lambda e: self._goto_problem())
        self._problem_lines: list[int] = []

    # -- loading ------------------------------------------------------------
    def refresh_chapter_list(self) -> None:
        """Nothing to cache - chapters are chosen on the chapter page."""

    def select_chapter(self, path: Path | None) -> None:
        """The chapter page switched chapter. An open shared script (startup.cmb)
        stays open; picking "This chapter" in the File box then opens the new one."""
        previous_chapter = self._chapter_path
        self._chapter_path = Path(path) if path is not None and Path(path).exists() else None
        showing_shared = self._current_path is not None and self._current_path != previous_chapter
        self._fill_file_choices()
        if showing_shared or self._chapter_path is None or self._chapter_path == self._current_path:
            return
        if not self.confirm_navigate_away():
            return
        self._load(self._chapter_path)

    def open_file(self, path: Path) -> bool:
        """Show ``path`` (a chapter or shared script). False if the user kept unsaved edits."""
        path = Path(path)
        if path == self._current_path:
            return True
        if not self.confirm_navigate_away():
            return False
        self._load(path)
        return True

    @property
    def current_path(self) -> Optional[Path]:
        return self._current_path

    @property
    def showing_chapter_script(self) -> bool:
        return self._current_path is None or self._current_path == self._chapter_path

    def show_chapter_script(self) -> bool:
        """Switch back to the chapter's own script (False if the user kept unsaved edits)."""
        return self._chapter_path is not None and self.open_file(self._chapter_path)

    def reload_if_open(self, path: Path) -> None:
        """``path`` was rewritten elsewhere (the Flags page): show the new file
        if it is open here without unsaved edits."""
        if self._current_path is not None and Path(path) == self._current_path and not self._dirty:
            self._load(self._current_path)

    # -- the chapter script, for the Build tab's map zones -----------------------
    def add_listener(self, callback) -> None:
        """``callback()`` runs after the source parses again (edits, loading, saving)."""
        self._listeners.append(callback)

    def _notify(self) -> None:
        for callback in list(self._listeners):
            callback()

    @property
    def has_chapter_script(self) -> bool:
        return self._chapter_path is not None

    @property
    def chapter_path(self) -> Optional[Path]:
        """The chapter's own script file, whichever file is open."""
        return self._chapter_path

    def chapter_source(self) -> Optional[str]:
        """The chapter script's source as edited here, or None when no chapter
        script is loaded (none, or a shared script is open instead)."""
        if self._script is None or self._chapter_path is None or self._current_path != self._chapter_path:
            return None
        return self._editor.get()

    def edit_chapter_source(self, source: str, select: Optional[str] = None) -> None:
        """Replace the chapter script's source (an edit made elsewhere, like the
        Build tab's zones); it is unsaved until Save, like a typed edit."""
        if self.chapter_source() is None:
            raise RuntimeError("The chapter script isn't open.")
        self._set_source(source, select=select)

    def source_snapshot(self) -> Optional[tuple]:
        """(path, source) of the chapter script, for :meth:`restore_source` (undo)."""
        source = self.chapter_source()
        return None if source is None else (self._current_path, source)

    def restore_source(self, state: Optional[tuple]) -> None:
        if state is None or self.chapter_source() is None:
            return
        path, source = state
        if path == self._current_path and source != self._editor.get():
            self._set_source(source)

    def save(self) -> bool:
        return self._save()

    def _fill_file_choices(self) -> None:
        choices = []
        if self._chapter_path is not None:
            choices.append((f"This chapter ({self._chapter_path.name})", self._chapter_path))
        for shared in script_sources.shared_scripts(self._project):
            what = "shared helpers and campaign flags" if shared.stem.lower() == "startup" else "shared script"
            choices.append((f"{shared.name} - {what}", shared))
        if self._current_path is not None and all(p != self._current_path for _label, p in choices):
            choices.insert(0, (self._current_path.name, self._current_path))  # a chapter script opened directly
        self._file_choices = choices
        self._file_box.configure(values=[label for label, _p in choices])
        self._file_var.set(next((label for label, p in choices if p == self._current_path), ""))

    def _on_file_picked(self) -> None:
        path = dict(self._file_choices).get(self._file_var.get())
        if path is None or not self.open_file(path):
            self._fill_file_choices()

    def _sidecar(self, path: Path) -> Path:
        return script_sources.sidecar_path(self._project, path)

    def _load(self, path: Path, *, ignore_sidecar: bool = False) -> None:
        try:
            loaded = script_sources.load(self._project, path, ignore_sidecar=ignore_sidecar)
        except ProjectError as exc:  # the game has no script codec yet: say so in the status line
            self._script = None
            self._current_path = None
            self._save_button.config(state="disabled")
            self._status.config(text=str(exc))
            return
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror("Could not read script", str(exc), parent=self)
            return
        self._script = loaded
        self._current_path = path
        self._suggestions.invalidate()  # pick up videos, maps, groups... added since
        self._base = loaded.base
        source, note = loaded.source, loaded.note
        self._fill_file_choices()
        self._editor.set(source)
        self._dirty = False
        self._selected = None
        self._save_button.config(state="normal")
        self._status.config(text=f"{path.name} - {note}")
        self._reparse()
        self._check(quiet=True)
        self._notify()

    # -- source analysis ----------------------------------------------------
    def _on_text_changed(self) -> None:
        self._dirty = True
        self._status.config(text=f"{self._current_path.name if self._current_path else ''} - unsaved changes")
        if self._reparse_job is not None:
            self.after_cancel(self._reparse_job)
        self._reparse_job = self.after(700, self._reparse)

    def _reparse(self) -> None:
        if self._reparse_job is not None:  # a direct reparse makes a pending one redundant
            self.after_cancel(self._reparse_job)
        self._reparse_job = None
        try:
            spans = st.function_spans(self._editor.get(), self._dialect)
        except ParseError as e:
            self._show_problems([_Problem("error", e.line, e.message)])
            return
        self._spans = spans
        self._fill_function_list()
        if self._dirty:
            self._check(quiet=True)
        self._notify()

    @staticmethod
    def _function_label(span: st.FunctionSpan) -> str:
        summary = span.description.splitlines()[0] if span.description else ""
        return f"{span.name}  -  {summary}" if summary else span.name

    def _fill_function_list(self) -> None:
        self._fn_box.configure(values=[self._function_label(s) for s in self._spans])
        names = [s.name for s in self._spans]
        if self._selected in names:
            self._set_function_index(names.index(self._selected))
            self._show_span(self._spans[self._fn_index], move_cursor=False)
        else:
            self._set_function_index(None)

    def _set_function_index(self, index: Optional[int]) -> None:
        """Point the Function box at ``self._spans[index]`` (None clears it)."""
        self._fn_index = index
        self._fn_var.set("" if index is None else self._function_label(self._spans[index]))

    def _current_span(self) -> Optional[st.FunctionSpan]:
        if self._fn_index is None or self._fn_index >= len(self._spans):
            return None
        return self._spans[self._fn_index]

    def _on_function_selected(self) -> None:
        self._choose_function(self._fn_box.current())

    def _choose_function(self, index: int) -> None:
        if index < 0 or index >= len(self._spans):
            return
        self._set_function_index(index)
        span = self._spans[index]
        move = span.name != self._selected or not self._cursor_in(span)
        self._selected = span.name
        self._show_span(span, move_cursor=move)

    def _cursor_in(self, span: st.FunctionSpan) -> bool:
        return span.first_line <= self._editor.cursor_line() <= span.last_line

    def _show_span(self, span: st.FunctionSpan, move_cursor: bool) -> None:
        self._editor.highlight_function(span.first_line, span.last_line)
        if move_cursor:
            self._editor.goto_line(span.def_line)
        self._form.show(span)
        self._refresh_bytecode()

    def select_function(self, name: str) -> None:
        """Select a function of the loaded script by name (no-op if absent)."""
        for i, span in enumerate(self._spans):
            if span.name == name:
                self._choose_function(i)
                return

    def _sync_selection_to_cursor(self) -> None:
        line = self._editor.cursor_line()
        for i, span in enumerate(self._spans):
            if span.first_line <= line <= span.last_line:
                if span.name != self._selected:
                    self._selected = span.name
                    self._set_function_index(i)
                    self._show_span(span, move_cursor=False)
                return

    # -- compile / problems ---------------------------------------------------
    def _compile(self, source: str):
        """Compile the open script with what the project's startup.cmb provides
        (its campaign flags and exported helpers)."""
        context = script_sources.CompileContext.for_script(self._project, self._current_path, source)
        return compile_source(source, base=self._base, known_script_functions=context.helpers,
                              global_flags=context.global_flags)

    def _check(self, quiet: bool = False) -> bool:
        if self._base is None:
            return False
        try:
            result = self._compile(self._editor.get())
        except CompileError as e:
            self._show_problems(e.diagnostics)
            if not quiet:
                self._tabs.select(0)
            return False
        self._compiled = result
        self._show_problems(result.diagnostics)
        if not quiet:
            self._status.config(text=f"No errors ({len(result.warnings)} warning(s))")
        self._refresh_bytecode()
        return True

    def _show_problems(self, diagnostics: list) -> None:
        self._editor.mark_diagnostics(diagnostics)
        self._problems.delete(0, "end")
        self._problem_lines = []
        for d in sorted(diagnostics, key=lambda d: (d.severity != "error", d.line)):
            self._problems.insert("end", f"{'✖' if d.severity == 'error' else '⚠'}  line {d.line}: {d.message}")
            self._problems.itemconfig("end", foreground=theme.color("danger") if d.severity == "error" else theme.color("warn"))
            self._problem_lines.append(d.line)

    def _goto_problem(self) -> None:
        sel = self._problems.curselection()
        if sel:
            self._editor.goto_line(self._problem_lines[sel[0]], select=True)

    def _refresh_bytecode(self) -> None:
        if self._tabs.index("current") != 1:
            return
        self._bytecode.config(state="normal")
        self._bytecode.delete("1.0", "end")
        span = self._current_span()
        if self._compiled is None or span is None:
            self._bytecode.insert("1.0", "Select a function (the code must compile).")
        else:
            index = [s.name for s in self._spans].index(span.name)
            fns = self._compiled.script.functions
            if index < len(fns):
                fn = fns[index]
                header = f"# function {index}: type {fn.type}, params {fn.params}, {fn.num_args} args, {fn.num_vars} slots\n"
                self._bytecode.insert("1.0", header + disassemble(fn))
        self._bytecode.config(state="disabled")

    # -- completions / hints ------------------------------------------------
    def _local_defs(self) -> dict:
        return {s.name: s for s in self._spans}

    def _completions(self, before: str, after: str, force: bool) -> list:
        """Popup entries: values for the argument being typed (characters,
        videos, music, groups...), else function names."""
        return self._suggestions.completions(
            before, after, force=force, externs=self._externs, identifiers=self._identifiers,
            chapter_id=chapter_of_script(self._current_path, self._project),
            pool=self._base.pool if self._base is not None else (), source=self._editor.get(),
        )

    def _identifiers(self, prefix: str) -> list[str]:
        low = prefix.lower()
        names = list(self._local_defs()) + _BUILTINS + list(self._externs)
        starts = [n for n in names if n.lower().startswith(low)]
        contains = [n for n in names if low in n.lower() and n not in starts]
        return sorted(set(starts), key=lambda n: (-self._uses(n), n)) + sorted(contains)[:10]

    def _uses(self, name: str) -> int:
        sig = self._externs.get(name)
        return sig.uses if sig else 10_000

    def _signature(self, name: str) -> Optional[str]:
        local = self._local_defs().get(name)
        if local is not None:
            return f"{name}({', '.join(local.params)})  - function in this script"
        sig = self._externs.get(name)
        if sig is None:
            return None
        where = {"native": "game function", "script": "defined in startup.cmb"}.get(sig.source, sig.source)
        text = f"{sig.signature()}  - {where}, used {sig.uses}× in vanilla"
        kinds = [f"{i + 1}: {KIND_TITLES[k]}" for i in range(sig.argc)
                 if (k := resolve_kind(name, i, self._externs)) and k not in (sig.arg_kind(i),)]
        if kinds:
            text += f"  [args {', '.join(kinds)}]"
        return text + (f"  ({sig.note})" if sig.note else "")

    def _is_known_call(self, name: str) -> bool:
        return name in self._externs or name in self._local_defs() or name in _BUILTINS

    def _name_values(self, kind: str) -> list[str]:
        """Suggestions for a value of the given kind (pid, iid, movie, group, ...)."""
        pool = self._base.pool if self._base is not None else []
        if kind in KIND_TITLES:
            return [s.text for s in self._suggestions.values(
                kind, chapter_id=chapter_of_script(self._current_path, self._project), pool=pool,
                source=self._editor.get())]
        prefixes = {"mpid": "MPID_"}
        if kind in prefixes:
            return sorted({s for s in pool if s.upper().startswith(prefixes[kind])})
        if kind in ("label", "str"):
            return sorted({s for s in pool if s and not any(s.startswith(p) for p in ("PID_", "IID_", "JID_", "MS_", "BGM_"))})
        return []

    # -- editing actions ----------------------------------------------------
    def _set_source(self, source: str, select: Optional[str] = None) -> None:
        view = self._editor.text.yview()[0]
        self._editor.set(source)
        self._editor.text.yview_moveto(view)
        self._on_text_changed()
        if select:
            self._selected = select
        self._reparse()
        span = self._local_defs().get(select) if select else None
        if span is not None:
            self._editor.goto_line(span.def_line)

    def _apply_form(self, span: st.FunctionSpan, name: str, description: str, export_id: Optional[str],
                    trigger_type: int, values: dict, raw_params: Optional[list]) -> None:
        if not st.parser_identifier(name):
            messagebox.showerror("Invalid name", f"{name!r} isn't a valid function name.", parent=self)
            return
        if name != span.name and name in self._local_defs():
            messagebox.showerror("Name taken", f"There is already a function named {name!r}.", parent=self)
            return
        decorators = st.decorator_source(export_id, name, trigger_type, values, raw_params, self._dialect)
        self._set_source(st.replace_decorators(self._editor.get(), span, decorators, name, description), select=name)

    def _new_function(self) -> None:
        if self._base is None:
            return
        source, name = st.new_function_source(self._editor.get(), dialect=self._dialect)
        self._set_source(source, select=name)

    def _duplicate_function(self) -> None:
        span = self._current_span()
        if span is None:
            return
        source, name = st.duplicate_function_source(self._editor.get(), span)
        self._set_source(source, select=name)

    def _delete_function(self) -> None:
        span = self._current_span()
        if span is None:
            return
        if not messagebox.askyesno(
            "Delete function",
            f"Delete {span.name}?\n\nFunctions after it move up one position. Calls between functions in this "
            "script are recompiled by name, so they stay correct.",
            parent=self,
        ):
            return
        self._selected = None
        self._set_source(st.delete_function_source(self._editor.get(), span))

    def _insert_call(self) -> None:
        if self._base is None:
            return
        dialog = InsertCallDialog(self, self._externs, self._local_defs(), self._name_values)
        self.wait_window(dialog)
        if dialog.result:
            self._editor.insert_at_cursor(dialog.result)

    def _revert(self) -> None:
        if self._current_path is None:
            return
        if not messagebox.askyesno(
            "Revert", f"Throw away the source text and decompile {self._current_path.name} again?", parent=self
        ):
            return
        self._load(self._current_path, ignore_sidecar=True)

    # -- save -------------------------------------------------------------
    def _save(self) -> bool:
        if self._current_path is None or self._base is None:
            return False
        source = self._editor.get()
        try:
            result = script_sources.save(self._project, self._script, source)
        except CompileError as e:
            self._show_problems(e.diagnostics)
            errors = [d for d in e.diagnostics if d.severity == "error"]
            messagebox.showerror(
                "Script has errors", f"{len(errors)} error(s) - nothing was saved.\n\n" + "\n".join(map(str, errors[:8])),
                parent=self,
            )
            return False
        except OSError as exc:
            messagebox.showerror("Could not save script", str(exc), parent=self)
            return False
        self._base = self._script.base
        self._compiled = result
        self._dirty = False
        self._show_problems(result.diagnostics)
        self._status.config(text=f"Saved {self._current_path.name} ({len(result.warnings)} warning(s))")
        self._changelog.append(self._current_path.name, "Saved script")
        self._notify()
        return True

    def _confirm_discard(self) -> bool:
        return messagebox.askyesno(
            "Discard changes?",
            f"{self._current_path.name if self._current_path else 'This script'} has unsaved changes. Discard them?",
            parent=self
        )


class _Problem:
    def __init__(self, severity: str, line: int, message: str):
        self.severity, self.line, self.message = severity, line, message


class TriggerForm(ttk.LabelFrame):
    """Name/export/trigger fields for the selected function."""

    def __init__(self, parent: tk.Misc, on_apply, name_values, dialect="fe9"):
        super().__init__(parent, text="Function", padding=8)
        self._on_apply = on_apply
        self._name_values = name_values
        self._triggers = triggers(dialect)
        self._choices = [f"{t.type} - {t.title}" for t in self._triggers.values()]
        self._span: Optional[st.FunctionSpan] = None

        row = ttk.Frame(self)
        row.pack(fill="x")
        ttk.Label(row, text="Name").pack(side="left")
        self._name_var = tk.StringVar()
        ttk.Entry(row, textvariable=self._name_var, width=24).pack(side="left", padx=(4, 12))
        self._export = tk.BooleanVar()
        ttk.Checkbutton(row, text="Exported as", variable=self._export,
                        command=self._sync_export).pack(side="left")
        self._export_id = tk.StringVar()
        self._export_entry = ttk.Entry(row, textvariable=self._export_id, width=20)
        self._export_entry.pack(side="left", padx=(4, 12))
        ttk.Label(row, text="Trigger").pack(side="left")
        self._type = tk.StringVar()
        self._type_box = ttk.Combobox(row, textvariable=self._type, values=self._choices, state="readonly", width=36)
        self._type_box.pack(side="left", padx=(4, 0))
        self._type_box.bind("<<ComboboxSelected>>", lambda e: self._build_params({}))

        desc_row = ttk.Frame(self)
        desc_row.pack(fill="x", pady=(6, 0))
        ttk.Label(desc_row, text="Description").pack(side="left")
        self._description = tk.StringVar()
        ttk.Entry(desc_row, textvariable=self._description).pack(side="left", fill="x", expand=True, padx=(4, 0))

        self._params = ttk.Frame(self)
        self._params.pack(fill="x", pady=(6, 0))
        bottom = ttk.Frame(self)
        bottom.pack(fill="x", pady=(6, 0))
        self._apply_button = ttk.Button(bottom, text="Apply to code", command=self._apply, state="disabled")
        self._apply_button.pack(side="left")
        self._note = ttk.Label(bottom, text="", style="Muted.TLabel")
        self._note.pack(side="left", padx=(8, 0))
        self._vars: dict = {}
        self._raw_var: Optional[tk.StringVar] = None

    def _sync_export(self) -> None:
        if self._export.get() and not self._export_id.get():
            self._export_id.set(self._name_var.get())
        self._export_entry.config(state="normal" if self._export.get() else "disabled")

    def show(self, span: st.FunctionSpan) -> None:
        self._span = span
        self._name_var.set(span.name)
        self._description.set(" ".join(span.description.splitlines()))
        self._export.set(span.export_id is not None)
        self._export_id.set(span.export_id or "")
        self._sync_export()
        self._type.set(next((c for c in self._choices if c.startswith(f"{span.trigger_type} -")),
                            f"{span.trigger_type} - (unknown)"))
        self._build_params(span.trigger_values, span.raw_params)
        self._apply_button.config(state="normal")
        self._note.config(text=SPECIAL_ENTRY_POINTS.get(span.export_id or "", ""))

    def _selected_type(self) -> int:
        try:
            return int(self._type.get().split(" - ")[0])
        except ValueError:
            return 0

    def _build_params(self, values: dict, raw: Optional[list] = None) -> None:
        for child in self._params.winfo_children():
            child.destroy()
        self._vars = {}
        self._raw_var = None
        kind = self._triggers.get(self._selected_type())
        if raw is not None or kind is None:
            ttk.Label(self._params, text="Raw params (comma-separated numbers)").grid(row=0, column=0, sticky="w")
            self._raw_var = tk.StringVar(value=", ".join(str(v) for v in (raw or [])))
            ttk.Entry(self._params, textvariable=self._raw_var, width=40).grid(row=0, column=1, sticky="w", padx=(4, 0))
            return
        for i, spec in enumerate(kind.params):
            col = (i % 3) * 2
            r = i // 3
            ttk.Label(self._params, text=spec.description).grid(row=r, column=col, sticky="w", padx=(0 if col == 0 else 12, 4), pady=2)
            value = values.get(spec.name)
            if spec.enum:
                text = value if isinstance(value, str) else spec.enum.get(value, "" if value is None else str(value))
                var = tk.StringVar(value=text or next(iter(spec.enum.values())))
                widget = ttk.Combobox(self._params, textvariable=var, values=list(spec.enum.values()), width=14)
            elif spec.is_label:
                var = tk.StringVar(value="" if value is None else str(value))
                widget = ttk.Combobox(self._params, textvariable=var, values=self._name_values(spec.kind), width=24)
            else:
                var = tk.StringVar(value=str(value if value is not None else 0))
                widget = ttk.Spinbox(self._params, textvariable=var, from_=0, to=65535, width=8)
            widget.grid(row=r, column=col + 1, sticky="w", pady=2)
            self._vars[spec.name] = (spec, var)

    def _apply(self) -> None:
        if self._span is None:
            return
        trigger_type = self._selected_type()
        values = {}
        raw = None
        if self._raw_var is not None:
            try:
                raw = [int(v, 0) for v in self._raw_var.get().replace(" ", "").split(",") if v]
            except ValueError:
                messagebox.showerror("Invalid params", "Raw params must be numbers.", parent=self)
                return
        for name, (spec, var) in self._vars.items():
            text = var.get().strip()
            if spec.is_label:
                values[name] = text or None
            elif spec.enum:
                if text in spec.enum.values():
                    values[name] = text
                else:
                    try:
                        values[name] = int(text, 0)
                    except ValueError:
                        messagebox.showerror("Invalid value", f"{spec.description}: pick a value from the list.", parent=self)
                        return
            else:
                try:
                    values[name] = int(text or "0", 0)
                except ValueError:
                    messagebox.showerror("Invalid value", f"{spec.description} must be a number.", parent=self)
                    return
        export_id = self._export_id.get().strip() if self._export.get() else None
        self._on_apply(self._span, self._name_var.get().strip(), self._description.get().strip(), export_id,
                       trigger_type, values, raw)


class InsertCallDialog(tk.Toplevel):
    """Pick a function (game extern or one of this script's functions), fill
    its arguments with typed fields, and get the call's source text."""

    STRING_KINDS = {"str", "pid", "iid", "jid", "mpid", "mess", "bgm", "sfx", "flag", "label",
                    "skill", "movie", "map", "group", "rect"}

    def __init__(self, parent: tk.Misc, externs: dict, local_defs: dict, name_values):
        super().__init__(parent)
        self.title("Insert call")
        self.geometry("760x520")
        self.result: Optional[str] = None
        self._externs = externs
        self._local = local_defs
        self._name_values = name_values

        top = ttk.Frame(self, padding=8)
        top.pack(fill="both", expand=True)
        search_row = ttk.Frame(top)
        search_row.pack(fill="x")
        ttk.Label(search_row, text="Search").pack(side="left")
        self._query = tk.StringVar()
        entry = ttk.Entry(search_row, textvariable=self._query, width=40)
        entry.pack(side="left", padx=(4, 0))
        entry.focus_set()
        self._query.trace_add("write", lambda *a: self._filter())

        body = ttk.PanedWindow(top, orient="horizontal")
        body.pack(fill="both", expand=True, pady=(6, 0))
        self._tree = ttk.Treeview(body, columns=("args", "where", "uses"), show="tree headings", selectmode="browse")
        self._tree.heading("#0", text="Function")
        self._tree.heading("args", text="Args")
        self._tree.heading("where", text="Group")
        self._tree.heading("uses", text="Vanilla uses")
        self._tree.column("#0", width=200)
        self._tree.column("args", width=40, anchor="center")
        self._tree.column("where", width=130)
        self._tree.column("uses", width=80, anchor="e")
        self._tree.bind("<<TreeviewSelect>>", lambda e: self._on_select())
        self._tree.bind("<Double-Button-1>", lambda e: self._insert())
        body.add(self._tree, weight=3)

        self._detail = ttk.Frame(body, padding=(8, 0))
        body.add(self._detail, weight=2)

        buttons = ttk.Frame(top)
        buttons.pack(fill="x", pady=(8, 0))
        ttk.Button(buttons, text="Insert", command=self._insert).pack(side="right")
        ttk.Button(buttons, text="Cancel", command=self.destroy).pack(side="right", padx=(0, 6))

        self._arg_vars: list = []
        self._entries = self._all_entries()
        self._filter()
        self.transient(parent)
        self.grab_set()

    def _all_entries(self) -> list:
        entries = []
        for name, span in self._local.items():
            entries.append((name, len(span.params), "this script", -1, [("int", p) for p in span.params], ""))
        for name, sig in self._externs.items():
            if sig.source == "unregistered":
                continue
            args = []
            for i in range(sig.argc):
                kind = resolve_kind(name, i, self._externs) or sig.arg_kind(i)
                args.append((kind, (sig.args[i].get("name") if i < len(sig.args) else "") or kind))
            group = "startup.cmb" if sig.source == "script" else sig.group
            entries.append((name, sig.argc, group, sig.uses, args, sig.note))
        return entries

    def _filter(self) -> None:
        q = self._query.get().lower()
        self._tree.delete(*self._tree.get_children())
        rows = [e for e in self._entries if q in e[0].lower()]
        rows.sort(key=lambda e: (e[3] >= 0, -e[3], e[0]))
        for i, (name, argc, group, uses, _, _) in enumerate(rows[:400]):
            self._tree.insert("", "end", iid=name, text=name, values=(argc, group, "" if uses < 0 else uses))
        self._rows = {e[0]: e for e in rows}

    def _on_select(self) -> None:
        for child in self._detail.winfo_children():
            child.destroy()
        sel = self._tree.selection()
        if not sel:
            return
        name, argc, group, uses, args, note = self._rows[sel[0]]
        ttk.Label(self._detail, text=name, font=("TkDefaultFont", 11, "bold")).grid(row=0, column=0, columnspan=2, sticky="w")
        info = f"{group}" + ("" if uses < 0 else f" · used {uses}× in vanilla scripts")
        ttk.Label(self._detail, text=info, style="Muted.TLabel").grid(row=1, column=0, columnspan=2, sticky="w")
        if note:
            ttk.Label(self._detail, text=note, wraplength=260, style="Warn.TLabel").grid(row=2, column=0, columnspan=2, sticky="w")
        self._arg_vars = []
        for i, (kind, label) in enumerate(args):
            ttk.Label(self._detail, text=f"{i + 1}. {label}").grid(row=3 + i, column=0, sticky="w", pady=2)
            var = tk.StringVar(value="" if kind in self.STRING_KINDS else "0")
            values = self._name_values(kind) if kind in self.STRING_KINDS or kind == "chapter" else []
            widget = ttk.Combobox(self._detail, textvariable=var, values=values, width=26) if values \
                else ttk.Entry(self._detail, textvariable=var, width=28)
            widget.grid(row=3 + i, column=1, sticky="w", padx=(6, 0), pady=2)
            self._arg_vars.append((kind, var))
        ttk.Label(
            self._detail, wraplength=260, style="Muted.TLabel",
            text="Argument kinds are inferred from how vanilla scripts call this function. Text values are "
                 "quoted for you; type a variable name or an expression wrapped in ( ) to pass it as-is.",
        ).grid(row=4 + len(args), column=0, columnspan=2, sticky="w", pady=(10, 0))

    def _insert(self) -> None:
        sel = self._tree.selection()
        if not sel:
            return
        parts = []
        for kind, var in self._arg_vars:
            text = var.get().strip()
            if kind in self.STRING_KINDS and not (text.startswith("(") or text.startswith('"')):
                parts.append(st.value_source(text))
            else:
                parts.append(text or "0")
        self.result = f"{sel[0]}({', '.join(parts)})"
        self.destroy()
