"""Step list + step form for one Radiant Dawn message (Dialogue tab).

Works on ``formats/fe10_message.py`` steps: the message text is always the steps' notation joined,
and a step keeps its exact bytes until it is edited. The list is this frame; the form
(``self.form_page``) goes wherever the caller puts it, like ``scene_editor.SceneEditor``."""
from __future__ import annotations

import re
import tkinter as tk
from tkinter import ttk

from ..formats import fe10_message as fm
from . import theme

HEX = tuple("0123456789ABCDEF")
POSITIONS = tuple("012345678")
FACINGS = (("D", "Default (D)"), ("L", "Left (L)"), ("R", "Right (R)"))

# Codes the Insert menu of a line offers: (notation, label).
INLINE = (("<w1>", "Short pause"), ("<w2>", "Pause"), ("<w4>", "Long pause"), ("<w6>", "Very long pause"),
          ("<mc>", "Mouth still (before '...')"), ("<md>", "Mouth moving again"), ("\n", "New line"),
          ("#F01", "Font 1 (Tellius alphabet)"), ("#F02", "Font 2 (dialogue)"), ("@[A]", "A button icon"))


class Fe10StepEditor(ttk.Frame):
    def __init__(self, parent, form_parent):
        super().__init__(parent)
        self._steps: list[fm.Step] = []
        self._form_step = None
        self._getters = {}
        self._playing = None
        self.on_change = None           # (cp437 text) -> None
        self.on_step_selected = None    # (display offset of the step's end) -> None

        toolbar = ttk.Frame(self)
        toolbar.pack(fill="x", pady=(0, 4))
        add = ttk.Menubutton(toolbar, text="Add step")
        add.pack(side="left")
        menu = tk.Menu(add, tearoff=False)
        add["menu"] = menu
        groups = {}
        for kind in fm.ADDABLE:
            group = "Text" if kind in ("line", "raw") else fm.COMMANDS[kind].group
            if group not in groups:
                groups[group] = tk.Menu(menu, tearoff=False)
                menu.add_cascade(label=group, menu=groups[group])
            groups[group].add_command(label=fm.step_label(kind), command=lambda k=kind: self._add(k))
        for label, command in (("Duplicate", self._duplicate), ("Delete", self._delete),
                               ("Move up", lambda: self._move(-1)), ("Move down", lambda: self._move(1))):
            ttk.Button(toolbar, text=label, command=command).pack(side="left", padx=(4, 0))

        frame = ttk.Frame(self)
        frame.pack(fill="both", expand=True)
        self._tree = ttk.Treeview(frame, columns=("step", "detail"), show="headings", selectmode="extended")
        self._tree.heading("step", text="Step")
        self._tree.heading("detail", text="Details")
        self._tree.column("step", width=140, stretch=False)
        self._tree.column("detail", width=320)
        scroll = ttk.Scrollbar(frame, orient="vertical", command=self._tree.yview)
        self._tree.configure(yscrollcommand=scroll.set)
        self._tree.pack(side="left", fill="both", expand=True)
        scroll.pack(side="left", fill="y")
        self._paint_tags()
        theme.on_change(self._tree, self._paint_tags)
        self._tree.bind("<<TreeviewSelect>>", lambda e: self._on_select())
        self._tree.bind("<Delete>", lambda e: self._delete())
        self._tree.bind("<Alt-Up>", lambda e: (self._move(-1), "break")[1])
        self._tree.bind("<Alt-Down>", lambda e: (self._move(1), "break")[1])

        self.form_page = ttk.Frame(form_parent, padding=6)
        self._form = ttk.LabelFrame(self.form_page, text="Step", padding=6)
        self._form.pack(fill="both", expand=True)
        self._form_error = ttk.Label(self._form, style="Danger.TLabel")

    # -- public API -------------------------------------------------------------------------
    def load(self, text: str, *, keep_selection: bool = True) -> None:
        selected = self._selected() if keep_selection else []
        self._playing = None
        try:
            self._steps = fm.decompile(text)
        except ValueError:
            self._steps = []
        self._refresh()
        self._select(min(selected[0], len(self._steps) - 1) if selected and self._steps else None)

    def text(self) -> str:
        return fm.compile_steps(self._steps)

    def highlight_step(self, index: int | None) -> None:
        if index == self._playing:
            return
        previous, self._playing = self._playing, index
        for i in (previous, index):
            if i is not None and self._tree.exists(str(i)):
                self._tree.item(str(i), tags=self._tags(i))
        if index is not None and self._tree.exists(str(index)):
            self._tree.see(str(index))

    # -- tree ---------------------------------------------------------------------------------
    def _paint_tags(self) -> None:
        self._tree.tag_configure("plausible", foreground=theme.color("warn"))
        self._tree.tag_configure("playing", background=theme.color("highlight"))

    def _tags(self, index: int) -> tuple:
        tags = []
        info = fm.COMMANDS.get(self._steps[index].kind)
        if self._steps[index].kind == "raw" or (info is not None and info.confidence != "Confirmed"):
            tags.append("plausible")
        if index == self._playing:
            tags.append("playing")
        return tuple(tags)

    def _row(self, index: int) -> tuple[str, str]:
        step = self._steps[index]
        return fm.step_label(step.kind), fm.summary(step, fm.cast_of(self._steps[:index + 1]))

    def _refresh(self) -> None:
        self._tree.delete(*self._tree.get_children())
        for i in range(len(self._steps)):
            self._tree.insert("", "end", iid=str(i), values=self._row(i), tags=self._tags(i))

    def _selected(self) -> list[int]:
        return sorted(int(i) for i in self._tree.selection())

    def _select(self, index) -> None:
        self._tree.selection_set(() if index is None else (str(index),))
        if index is not None:
            self._tree.focus(str(index))
            self._tree.see(str(index))
        self._on_select()

    def _on_select(self) -> None:
        indices = self._selected()
        self._build_form(indices[0] if len(indices) == 1 else None)
        if self.on_step_selected is not None and indices:
            self.on_step_selected(sum(len(s.display) for s in self._steps[:indices[-1] + 1]))

    # -- editing ----------------------------------------------------------------------------
    def _changed(self, select=None) -> None:
        if select is not None:
            self._refresh()
            self._tree.selection_set([str(i) for i in select if self._tree.exists(str(i))])
            if select and self._tree.exists(str(select[0])):
                self._tree.see(str(select[0]))
            self._on_select()
        if self.on_change is not None:
            self.on_change(self.text())

    def _insert_position(self) -> int:
        indices = self._selected()
        return indices[-1] + 1 if indices else len(self._steps)

    def insert_steps(self, steps: list[fm.Step]) -> None:
        position = self._insert_position()
        self._steps[position:position] = steps
        self._changed(select=list(range(position, position + len(steps))))

    def _add(self, kind: str) -> None:
        self.insert_steps([fm.new_step(kind)])

    def _duplicate(self) -> None:
        indices = self._selected()
        if not indices:
            return
        copies = [fm.Step(self._steps[i].kind, self._steps[i].display, dict(self._steps[i].fields)) for i in indices]
        at = indices[-1] + 1
        self._steps[at:at] = copies
        self._changed(select=list(range(at, at + len(copies))))

    def _delete(self) -> None:
        indices = self._selected()
        if not indices:
            return
        for i in reversed(indices):
            del self._steps[i]
        after = min(indices[0], len(self._steps) - 1)
        self._changed(select=[after] if after >= 0 else [])

    def _move(self, delta: int) -> None:
        indices = self._selected()
        if not indices:
            return
        first, last = indices[0], indices[-1]
        if indices != list(range(first, last + 1)) or first + delta < 0 or last + delta >= len(self._steps):
            return
        block = self._steps[first:last + 1]
        del self._steps[first:last + 1]
        self._steps[first + delta:first + delta] = block
        self._changed(select=list(range(first + delta, last + 1 + delta)))

    # -- form -------------------------------------------------------------------------------
    def _build_form(self, index) -> None:
        for child in self._form.winfo_children():
            if child is not self._form_error:
                child.destroy()
        self._form_error.configure(text="")
        self._form_step = index
        self._getters = {}
        if index is None:
            self._form.configure(text="Step")
            ttk.Label(self._form, text="Select one step to edit it.", style="Muted.TLabel").pack(anchor="w")
            return
        step = self._steps[index]
        self._form.configure(text=fm.step_label(step.kind))
        info = fm.COMMANDS.get(step.kind)
        if step.kind == "line":
            about = ("Text the speaker says. Codes in <...> are kept inside the line: pauses (<w2>), the mouth "
                     "(<mc>...<md>). A line usually ends by waiting for A.")
        elif step.kind == "raw":
            about = "Code the step list does not break down; edit it in the notation."
        else:
            about = info.description + ("" if info.confidence == "Confirmed" else f"  [{info.confidence}]")
        label = ttk.Label(self._form, text=about, style="Muted.TLabel", justify="left", font=("Segoe UI", 8))
        label.pack(anchor="w", fill="x", pady=(0, 4))
        label.bind("<Configure>", lambda e: label.configure(wraplength=max(200, e.width - 4)))
        cast = fm.cast_of(self._steps[:index])
        kind, fields = step.kind, step.fields
        if kind == "line":
            self._text(fields["text"])
            self._choice("end", "Ending", fields["end"], fm.LINE_ENDINGS)
        elif kind in ("speaker", "seat"):
            actors = [(c, f"{c}  {cast[int(c, 16)]}" if int(c, 16) < len(cast) else c) for c in HEX]
            self._choice("a", "Actor", fields["a"], actors)
            self._choice("b", "Position", fields["b"], [(p, p) for p in POSITIONS])
        elif kind in ("show", "show_now", "attach"):
            self._choice("a", "Position", fields["a"], [(p, p) for p in POSITIONS])
            self._choice("b", "Facing", fields["b"], FACINGS)
        elif kind == "skip":
            self._entry("a", "Byte 1", fields["a"], width=4)
            self._entry("b", "Byte 2", fields["b"], width=4)
        elif kind.endswith("|"):
            self._entry("items", "Items", " | ".join(fields["items"]),
                        convert=lambda v: [part.strip() for part in v.split("|") if part.strip()])
            hint = "Portrait names without FID_, separated by |." if kind == "FL|" else "Fields separated by |."
            ttk.Label(self._form, text=hint, style="Muted.TLabel").pack(anchor="w")
        elif kind == "R:":
            self._layout(fields["value"])
        elif kind.endswith(":"):
            if kind == "V#:":
                self._choice("n", "Channel", fields["n"], [(c, c) for c in "0123"])
            self._entry("value", "Value", fields["value"])
        elif kind.endswith("#"):
            self._choice("n", "Value", fields["n"], [(c, c) for c in "0123456789"])
        elif kind == "raw":
            self._entry("source", "Code", fields["source"])
        self._form_error.pack(anchor="w", pady=(6, 0))

    def _row_frame(self, label: str) -> ttk.Frame:
        row = ttk.Frame(self._form)
        row.pack(fill="x", pady=2)
        ttk.Label(row, text=label, width=10).pack(side="left")
        return row

    def _choice(self, name, label, value, options) -> None:
        row = self._row_frame(label)
        labels = dict(options)
        var = tk.StringVar(value=labels.get(value, value))
        box = ttk.Combobox(row, textvariable=var, values=list(labels.values()), state="readonly", width=30)
        box.pack(side="left", fill="x", expand=True)
        box.bind("<<ComboboxSelected>>", lambda e: self._commit())
        reverse = {v: k for k, v in options}
        self._getters[name] = lambda: reverse[var.get()]

    def _entry(self, name, label, value, width=30, convert=None) -> None:
        row = self._row_frame(label)
        var = tk.StringVar(value=value)
        ttk.Entry(row, textvariable=var, width=width).pack(side="left", fill="x", expand=True)
        var.trace_add("write", lambda *_: self._commit())
        self._getters[name] = (lambda: convert(var.get())) if convert else var.get

    def _layout(self, value) -> None:
        row = self._row_frame("Layout")
        var = tk.StringVar(value=fm.layout_label(value))
        box = ttk.Combobox(row, textvariable=var, values=[fm.layout_label(n) for n in fm.LAYOUT_NAMES], width=30)
        box.pack(side="left", fill="x", expand=True)
        box.bind("<<ComboboxSelected>>", lambda e: self._commit())
        var.trace_add("write", lambda *_: self._commit())
        self._getters["value"] = lambda: fm.layout_from_label(var.get())

    def _text(self, value) -> None:
        top = ttk.Frame(self._form)
        top.pack(fill="x")
        ttk.Label(top, text="Text").pack(side="left")
        insert = ttk.Menubutton(top, text="Insert")
        insert.pack(side="right")
        text = tk.Text(self._form, height=6, wrap="word", undo=True, font=("Segoe UI", 10))
        text.pack(fill="both", expand=True)
        menu = tk.Menu(insert, tearoff=False)
        insert["menu"] = menu
        for code, label in INLINE:
            shown = "line break" if code == "\n" else code
            menu.add_command(label=f"{label}    {shown}", command=lambda c=code: (text.insert("insert", c), text.focus_set()))
        text.insert("1.0", value)
        text.edit_modified(False)
        text.tag_configure("code", background=theme.color("accent_bg"), foreground=theme.color("accent"))
        hint = ttk.Label(self._form, style="Muted.TLabel")
        hint.pack(anchor="w")

        def highlight():
            text.tag_remove("code", "1.0", "end")
            content = text.get("1.0", "end-1c")
            position = 0
            for part in _split_tags(content):
                if part.startswith("<"):
                    text.tag_add("code", f"1.0+{position}c", f"1.0+{position + len(part)}c")
                position += len(part)

        def modified(_event=None):
            if text.edit_modified():
                text.edit_modified(False)
                highlight()
                self._commit()

        def hover(event):
            index = text.index(f"@{event.x},{event.y}")
            ranges = text.tag_prevrange("code", index + "+1c")
            if ranges and text.compare(ranges[0], "<=", index) and text.compare(index, "<", ranges[1]):
                try:
                    tokens = fm.tokenize(fm.to_raw(text.get(*ranges)).encode("cp437"))
                    hint.configure(text=fm.describe(tokens[0]) if tokens else "")
                except (ValueError, UnicodeError):
                    hint.configure(text="Not a valid code")
            else:
                hint.configure(text="")

        highlight()
        text.bind("<<Modified>>", modified)
        text.bind("<Motion>", hover)
        self._getters["text"] = lambda: text.get("1.0", "end-1c")

    def _commit(self) -> None:
        index = self._form_step
        if index is None or index >= len(self._steps):
            return
        try:
            values = {name: getter() for name, getter in self._getters.items()}
        except (ValueError, KeyError):
            self._form_error.configure(text="Invalid value")
            return
        step = self._steps[index]
        if all(step.fields.get(k) == v for k, v in values.items()):
            return
        new = fm.edited(step, **values)
        error = fm.validate_step(new)
        self._form_error.configure(text=error or "")
        if error:
            return
        self._steps[index] = new
        self._tree.item(str(index), values=self._row(index), tags=self._tags(index))
        self._changed()


def _split_tags(text: str) -> list[str]:
    """Text and ``<...>`` tags in order (an unmatched ``<`` stays text)."""
    return [part for part in re.split(r"(<[^<>]*>)", text) if part]
