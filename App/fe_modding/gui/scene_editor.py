"""Step list + stage editor for one FE9 message (Dialogue tab).

Works on ``formats/fe9_message_scene.py`` steps, so the raw message text is
always ``compile_steps(steps)`` and untouched steps keep their exact bytes.
The stage shows the scene state after the selected step, computed with the
same timeline the preview plays (``fe9_conversation.build_timeline``)."""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from PIL import Image, ImageTk

from ..formats import fe9_message_scene as ms
from . import theme
from ..formats.fe9_conversation import InitialContext, build_timeline, tokenize
from ..formats.fe9_conversation_render import ICON_SHEET, SCENE_SIZE, icon_cell

THUMB = 48
# Layouts with at most this many seats pair one textbox with each seat
# ($c/$s/$d: 上下会話, 背景上下会話, TUT会話, ダイアログ会話); larger ones are
# driven through $F seats (背景会話, GMAP会話, のみ会話, ...).
BOX_STYLE_MAX_SEATS = 5
SUPPORT_BACKGROUND = "支援背景"  # chapter-dependent alias, not a rect resource


def _short(fid: str) -> str:
    return fid.removeprefix("FID_")


class _Thumbnails:
    def __init__(self):
        self._assets = None
        self._cache = {}

    def _check(self, assets):
        if assets is not self._assets:
            self._assets, self._cache = assets, {}

    def portrait(self, assets, name, size=THUMB):
        self._check(assets)
        key = ("face", name, size)
        if key not in self._cache:
            image = assets.face(name).compose(mouth_variant=1)
            box = image.getbbox()
            if box:
                image = image.crop(box)
            width, height = image.size
            image = image.crop((0, 0, width, min(height, width)))  # the face, not the torso
            image.thumbnail((size, size))
            self._cache[key] = ImageTk.PhotoImage(image)
        return self._cache[key]

    def background(self, assets, name, size=(304, 224)):
        self._check(assets)
        key = ("bg", name, size)
        if key not in self._cache:
            image = Image.new("RGBA", SCENE_SIZE, (0, 0, 0, 255))
            assets.draw_resource(image, "RID_" + name)
            image.thumbnail(size)
            self._cache[key] = ImageTk.PhotoImage(image)
        return self._cache[key]


def portrait_names(assets) -> list[tuple[str, str]]:
    result = []
    for fid in sorted(assets.faces):
        try:
            label = assets.display_name(fid)
        except ValueError:
            label = ""
        result.append((_short(fid), label))
    return result


def face_details(assets, name: str) -> str:
    """facedata.bin fields the stage does not show (read-only)."""
    record = assets.faces["FID_" + _short(name)]
    mini = "none" if record.mini_portrait == 0xFFFF else f"texture {record.mini_portrait}"
    return "\n".join((f"{record.filename}   depth {record.depth}", f"64x64 menu face: {mini}",
                      f"Lowered in menu panels by {record.menu_offset}px"))


def display_name(assets, name: str) -> str:
    if assets is None or not name:
        return ""
    try:
        return assets.display_name("FID_" + _short(name))
    except ValueError:
        return ""


def background_names(assets) -> list[str]:
    names = [r.removeprefix("RID_") for r, resource in assets.rects.items()
             if not r.isascii() and not any(p.kind in (2, 4) for p in resource.parts)]
    return sorted(names) + [SUPPORT_BACKGROUND]


def layout_names(assets) -> list[str]:
    return [r.removeprefix("RID_") for r, resource in assets.rects.items()
            if any(p.kind == 2 for p in resource.parts)]


def layout_labels(assets) -> list[str]:
    """Combobox entries: 'English name (ID)', vanilla's most common layouts first."""
    names = layout_names(assets)
    order = list(ms.LAYOUT_NAMES)
    names.sort(key=lambda n: (order.index(n) if n in order else len(order), n))
    return [ms.layout_label(n) for n in names]


class _Picker(tk.Toplevel):
    """Searchable list with a preview image of the selected entry."""

    def __init__(self, parent, title, entries, preview, initial="", info=None):
        super().__init__(parent)
        self._info = info
        self.title(title)
        self.transient(parent.winfo_toplevel())
        self.result = None
        self._entries, self._preview = entries, preview
        self._search = tk.StringVar()
        search = ttk.Entry(self, textvariable=self._search)
        search.pack(fill="x", padx=8, pady=(8, 4))
        body = ttk.Frame(self)
        body.pack(fill="both", expand=True, padx=8)
        self._tree = ttk.Treeview(body, columns=("value", "label"), show="headings", height=18)
        self._tree.heading("value", text="ID")
        self._tree.heading("label", text="Name")
        self._tree.column("value", width=170)
        self._tree.column("label", width=150)
        scroll = ttk.Scrollbar(body, orient="vertical", command=self._tree.yview)
        self._tree.configure(yscrollcommand=scroll.set)
        self._tree.pack(side="left", fill="both", expand=True)
        scroll.pack(side="left", fill="y")
        side = ttk.Frame(body)
        side.pack(side="left", fill="both", padx=(8, 0))
        self._image = ttk.Label(side, width=40, anchor="center")
        self._image.pack(fill="both", expand=True)
        self._details = ttk.Label(side, style="Muted.TLabel", justify="left", wraplength=280)
        self._details.pack(anchor="w")
        buttons = ttk.Frame(self)
        buttons.pack(fill="x", padx=8, pady=8)
        ttk.Button(buttons, text="Cancel", command=self.destroy).pack(side="right")
        ttk.Button(buttons, text="OK", command=self._accept).pack(side="right", padx=4)
        self._search.trace_add("write", lambda *_: self._fill())
        self._tree.bind("<<TreeviewSelect>>", lambda e: self._show())
        self._tree.bind("<Double-1>", lambda e: self._accept())
        search.bind("<Return>", lambda e: self._accept())
        self.bind("<Escape>", lambda e: self.destroy())
        self._fill(initial)
        search.focus_set()
        self.grab_set()
        self.wait_window()

    def _fill(self, initial=""):
        query = self._search.get().casefold()
        self._tree.delete(*self._tree.get_children())
        for value, label in self._entries:
            if query in value.casefold() or query in label.casefold():
                self._tree.insert("", "end", iid=value, values=(value, label))
        target = initial if initial and self._tree.exists(initial) else next(iter(self._tree.get_children()), None)
        if target:
            self._tree.selection_set(target)
            self._tree.see(target)

    def _show(self):
        selection = self._tree.selection()
        image = None
        if selection:
            try:
                image = self._preview(selection[0])
            except (ValueError, OSError, KeyError, IndexError):
                image = None
        self._image.configure(image=image or "", text="" if image else "No preview")
        self._image.image = image
        details = ""
        if selection and self._info is not None:
            try:
                details = self._info(selection[0])
            except (ValueError, KeyError):
                details = ""
        self._details.configure(text=details)

    def _accept(self):
        selection = self._tree.selection()
        if selection:
            self.result = selection[0]
        self.destroy()


class SceneEditor(ttk.Frame):
    """The step list (toolbar + tree) is this frame. The stage (``self.stage``, a
    child of ``stage_parent``) and the step form (``self.form_page``, a child of
    ``form_parent``) are placed wherever the caller wants."""

    def __init__(self, parent, stage_parent, form_parent, get_assets):
        super().__init__(parent)
        self._get_assets = get_assets
        self._steps: list[ms.Step] = []
        self._context = InitialContext()
        self._timeline_cache = None
        self._thumbs = _Thumbnails()
        self._playing = None
        self._form_step = None
        self._stage_after = None
        self.on_change = None           # (text) -> None
        self.on_step_selected = None    # (end_offset) -> None, preview shows the scene before it

        toolbar = ttk.Frame(self)
        toolbar.pack(fill="x", pady=(0, 4))
        add = ttk.Menubutton(toolbar, text="Add step")
        add.pack(side="left")
        add_menu = tk.Menu(add, tearoff=False)
        add["menu"] = add_menu
        groups = {}
        for kind in ms.STEP_KINDS.values():
            if kind.group not in groups:
                groups[kind.group] = tk.Menu(add_menu, tearoff=False)
                add_menu.add_cascade(label=kind.group, menu=groups[kind.group])
            groups[kind.group].add_command(label=kind.label, command=lambda k=kind.kind: self._add(k))
        for label, command in (("Duplicate", self._duplicate), ("Delete", self._delete),
                               ("Move up", lambda: self._move(-1)), ("Move down", lambda: self._move(1))):
            ttk.Button(toolbar, text=label, command=command).pack(side="left", padx=(4, 0))

        tree_frame = ttk.Frame(self)
        tree_frame.pack(fill="both", expand=True)
        self._tree = ttk.Treeview(tree_frame, columns=("step", "detail"), show="headings", selectmode="extended")
        self._tree.heading("step", text="Step")
        self._tree.heading("detail", text="Details")
        self._tree.column("step", width=130, stretch=False)
        self._tree.column("detail", width=320)
        scroll = ttk.Scrollbar(tree_frame, orient="vertical", command=self._tree.yview)
        self._tree.configure(yscrollcommand=scroll.set)
        self._tree.pack(side="left", fill="both", expand=True)
        scroll.pack(side="left", fill="y")
        self._paint_tree_tags()
        theme.on_change(self._tree, self._paint_tree_tags)
        self._tree.bind("<<TreeviewSelect>>", lambda e: self._on_select())
        self._tree.bind("<Delete>", lambda e: self._delete())
        self._tree.bind("<Alt-Up>", lambda e: (self._move(-1), "break")[1])
        self._tree.bind("<Alt-Down>", lambda e: (self._move(1), "break")[1])

        self.stage = stage = ttk.LabelFrame(stage_parent, text="Stage after the selected step", padding=4)
        self._stage_info = ttk.Label(stage, style="Muted.TLabel")
        self._stage_info.pack(anchor="w")
        self._tiles = ttk.Frame(stage)
        self._tiles.pack(fill="x", pady=(2, 0))
        ttk.Label(stage, text="Click an empty seat to load a portrait; right-click a portrait for more actions.",
                  style="Muted.TLabel").pack(anchor="w")
        self.form_page = ttk.Frame(form_parent, padding=6)
        self._form = ttk.LabelFrame(self.form_page, text="Step", padding=6)
        self._form.pack(fill="both", expand=True)
        self._form_error = ttk.Label(self._form, style="Danger.TLabel")

    # -- public API -----------------------------------------------------------
    def load(self, text: str, *, keep_selection: bool = True) -> None:
        """Replace the steps with ``text``'s (optionally keeping the selected position)."""
        selected = self._selected_indices() if keep_selection else []
        self._playing = None
        self._steps = ms.decompile(text)
        self._timeline_cache = None
        self._refresh_tree()
        if selected and self._steps:
            self._select(min(selected[0], len(self._steps) - 1))
        else:
            self._select(None)

    def set_context(self, context: InitialContext) -> None:
        if context == self._context:
            return
        self._context = context
        self._timeline_cache = None
        if self._tree.exists("start"):
            self._tree.item("start", values=("Starting scene", self._describe_context()))
        self._refresh_stage()

    def text(self) -> str:
        return ms.compile_steps(self._steps)

    def highlight_offset(self, offset: int) -> None:
        index = ms.step_at_offset(ms.step_offsets(self._steps), offset) if self._steps else None
        if index == self._playing:
            return
        previous, self._playing = self._playing, index
        for i in (previous, index):
            if i is not None and self._tree.exists(str(i)):
                self._tree.item(str(i), tags=self._tags(i))
        if index is not None and self._tree.exists(str(index)):
            self._tree.see(str(index))

    # -- tree -----------------------------------------------------------------
    def _tags(self, index):
        tags = []
        if ms.STEP_KINDS[self._steps[index].kind].confidence != "Confirmed":
            tags.append("undecoded")
        if index == self._playing:
            tags.append("playing")
        return tuple(tags)

    def _describe_context(self) -> str:
        context = self._context
        seats = [f"{i}: {_short(f)}" for i, f in enumerate(context.portraits) if f]
        if context == InitialContext():
            return "Fresh scene (no layout inherited, nothing on stage)"
        parts = [ms.layout_label(context.layout) if context.layout else "no layout"]
        if context.background:
            parts.append(context.background)
        parts.append(("seats " + ", ".join(seats)) if seats else "no portraits")
        return "Inherited: " + " · ".join(parts)

    def _refresh_tree(self) -> None:
        self._tree.delete(*self._tree.get_children())
        self._tree.insert("", "end", iid="start", values=("Starting scene", self._describe_context()), tags=("start",))
        for i, step in enumerate(self._steps):
            self._tree.insert("", "end", iid=str(i), values=(ms.STEP_KINDS[step.kind].label, ms.summary(step)),
                              tags=self._tags(i))

    def _update_row(self, index: int) -> None:
        step = self._steps[index]
        self._tree.item(str(index), values=(ms.STEP_KINDS[step.kind].label, ms.summary(step)), tags=self._tags(index))

    def _selected_indices(self) -> list[int]:
        return sorted(int(i) for i in self._tree.selection() if i != "start")

    def _select(self, index) -> None:
        iid = "start" if index is None else str(index)
        if self._tree.exists(iid):
            self._tree.selection_set(iid)
            self._tree.focus(iid)
            self._tree.see(iid)
        self._on_select()

    def _on_select(self) -> None:
        indices = self._selected_indices()
        self._build_form(indices[0] if len(indices) == 1 else None)
        self._refresh_stage()
        if self.on_step_selected is not None:
            self.on_step_selected(self._end_offset(indices[-1]) if indices else 0)

    def _end_offset(self, index: int) -> int:
        offsets = ms.step_offsets(self._steps)
        return offsets[index] + len(ms.render_step(self._steps[index]))

    # -- editing --------------------------------------------------------------
    def _changed(self, select=None) -> None:
        self._timeline_cache = None
        if select is not None:
            self._refresh_tree()
            self._tree.selection_set([str(i) for i in select if self._tree.exists(str(i))] or ["start"])
            if select:
                self._tree.see(str(select[0]))
            self._on_select()
        else:
            self._schedule_stage()
        if self.on_change is not None:
            self.on_change(self.text())

    def _insert_position(self) -> int:
        indices = self._selected_indices()
        if indices:
            return indices[-1] + 1
        return 0 if "start" in self._tree.selection() else len(self._steps)

    def insert_steps(self, steps: list[ms.Step]) -> None:
        position = self._insert_position()
        self._steps[position:position] = steps
        self._changed(select=list(range(position, position + len(steps))))

    def _box_style(self, layout: str) -> bool:
        assets = self._get_assets()
        try:
            return 0 < len(assets.seats(layout)) <= BOX_STYLE_MAX_SEATS
        except (AttributeError, ValueError):
            return layout in ("上下会話", "背景上下会話")

    def _add(self, kind: str) -> None:
        step = ms.new_step(kind)
        scene = self._scene_at_selection()
        if kind == "line" and scene is not None:
            box_style = self._box_style(scene.layout)
            step.fields.update(select="s" if box_style else "F", index=max(0, scene.seat),
                               flush=not box_style)
        elif scene is not None and "seat" in step.fields:
            step.fields["seat"] = scene.seat
        self.insert_steps([step])

    def _duplicate(self) -> None:
        indices = self._selected_indices()
        if not indices:
            return
        copies = [ms.Step(self._steps[i].kind, dict(self._steps[i].fields), self._steps[i].raw) for i in indices]
        self._steps[indices[-1] + 1:indices[-1] + 1] = copies
        self._changed(select=list(range(indices[-1] + 1, indices[-1] + 1 + len(copies))))

    def _delete(self) -> None:
        indices = self._selected_indices()
        if not indices:
            return
        for i in reversed(indices):
            del self._steps[i]
        after = min(indices[0], len(self._steps) - 1)
        self._changed(select=[after] if after >= 0 else [])

    def _move(self, delta: int) -> None:
        indices = self._selected_indices()
        if not indices:
            return
        first, last = indices[0], indices[-1]
        if indices != list(range(first, last + 1)) or first + delta < 0 or last + delta >= len(self._steps):
            return
        block = self._steps[first:last + 1]
        del self._steps[first:last + 1]
        self._steps[first + delta:first + delta] = block
        self._changed(select=list(range(first + delta, last + 1 + delta)))

    # -- form -----------------------------------------------------------------
    def _build_form(self, index) -> None:
        for child in self._form.winfo_children():
            if child is not self._form_error:
                child.destroy()
        self._form_error.configure(text="")
        self._form_step = index
        self._getters = {}
        if index is None:
            self._form.configure(text="Step")
            text = ("Starting scene: the state this message inherits from the chapter script. "
                    "Change it with 'Inherit from message' / 'Initial scene context' in the preview."
                    if "start" in self._tree.selection() else "Select one step to edit it.")
            ttk.Label(self._form, text=text, wraplength=300, style="Muted.TLabel", justify="left").pack(anchor="w")
            return
        step = self._steps[index]
        kind = ms.STEP_KINDS[step.kind]
        self._form.configure(text=kind.label)
        description = ttk.Label(self._form, text=kind.description + ("" if kind.confidence == "Confirmed"
                                                                     else f"  [{kind.confidence}]"),
                                style="Muted.TLabel", justify="left", font=("Segoe UI", 8))
        description.pack(anchor="w", fill="x", pady=(0, 4))
        description.bind("<Configure>", lambda e: description.configure(wraplength=max(200, e.width - 4)))
        for spec in kind.fields:
            self._field_widget(spec, step.fields.get(spec.name), step)
        self._form_error.pack(anchor="w", pady=(6, 0))

    def _field_widget(self, spec, value, step) -> None:
        row = ttk.Frame(self._form)
        row.pack(fill="x", pady=2, expand=spec.type == "text")
        if spec.type not in ("bool", "text"):
            ttk.Label(row, text=spec.label, width=11).pack(side="left")
        commit = self._commit
        if spec.type in ("seat", "seat_opt", "box"):
            values = [str(i) for i in range(4 if spec.type == "box" else 9)]
            if spec.type == "seat_opt":
                values = ["current"] + values
            var = tk.StringVar(value="current" if value is None else str(value))
            box = ttk.Combobox(row, textvariable=var, values=values, width=9, state="readonly")
            box.pack(side="left")
            box.bind("<<ComboboxSelected>>", lambda e: commit())
            self._getters[spec.name] = lambda: None if var.get() == "current" else int(var.get())
        elif spec.type == "choice":
            labels = dict(spec.choices)
            var = tk.StringVar(value=labels.get(value, value))
            box = ttk.Combobox(row, textvariable=var, values=list(labels.values()), state="readonly", width=30)
            box.pack(side="left", fill="x", expand=True)
            box.bind("<<ComboboxSelected>>", lambda e: commit())
            reverse = {v: k for k, v in spec.choices}
            self._getters[spec.name] = lambda: reverse[var.get()]
        elif spec.type == "int":
            var = tk.StringVar(value=str(value))
            box = ttk.Spinbox(row, textvariable=var, from_=0, to=9999, width=8, command=commit)
            box.pack(side="left")
            var.trace_add("write", lambda *_: commit())
            self._getters[spec.name] = lambda: int(var.get())
        elif spec.type == "bool":
            var = tk.BooleanVar(value=bool(value))
            ttk.Checkbutton(row, text=spec.label, variable=var, command=commit).pack(side="left")
            self._getters[spec.name] = var.get
        elif spec.type in ("fid", "background", "layout"):
            var = tk.StringVar(value=ms.layout_label(value or "") if spec.type == "layout" else value or "")
            assets = self._get_assets()
            if spec.type == "layout":
                entry = ttk.Combobox(row, textvariable=var, values=layout_labels(assets) if assets else (), width=24)
                entry.bind("<<ComboboxSelected>>", lambda e: commit())
            else:
                entry = ttk.Entry(row, textvariable=var, width=24)
                picker = self._pick_portrait if spec.type == "fid" else self._pick_background
                ttk.Button(row, text="Pick…", command=lambda: self._set_picked(var, picker(var.get()))).pack(side="right")
            entry.pack(side="left", fill="x", expand=True)
            if spec.type == "fid":
                name = ttk.Label(row, style="Muted.TLabel", width=12)
                name.pack(side="right", padx=4)
                name.configure(text=display_name(assets, var.get()))
                var.trace_add("write", lambda *_: name.configure(text=display_name(self._get_assets(), var.get())))
            var.trace_add("write", lambda *_: commit())
            if spec.type == "layout":
                self._getters[spec.name] = lambda: ms.layout_from_label(var.get())
            else:
                self._getters[spec.name] = lambda: var.get().strip()
        elif spec.type == "line_target":
            options = [("", 0, "Current box/seat (no select)")]
            options += [("F", i, f"Seat {i}  ($F{i})") for i in range(9)]
            options += [("s", i, f"Box {i}  ($s{i})") for i in range(4)]
            options += [("W", i, f"Small window {i}  ($W{i})") for i in range(4)]
            by_label = {label: (code, i) for code, i, label in options}
            current = next(label for code, i, label in options
                           if code == step.fields["select"] and (not code or i == step.fields["index"]))
            var = tk.StringVar(value=current)
            box = ttk.Combobox(row, textvariable=var, values=[o[2] for o in options], state="readonly", width=30)
            box.pack(side="left", fill="x", expand=True)
            box.bind("<<ComboboxSelected>>", lambda e: commit())
            self._getters["select"] = lambda: by_label[var.get()][0]
            self._getters["index"] = lambda: by_label[var.get()][1]
        elif spec.type == "text":
            self._text_field(row, spec, value, step.kind == "line")
        else:
            raise ValueError(spec.type)

    def _set_picked(self, var, value):
        if value is not None:
            var.set(value)

    def _text_field(self, row, spec, value, line: bool) -> None:
        top = ttk.Frame(row)
        top.pack(fill="x")
        ttk.Label(top, text=spec.label).pack(side="left")
        hint = ttk.Label(row, style="Muted.TLabel")
        text = tk.Text(row, height=6, wrap="word", undo=True, font=("Segoe UI", 10))
        text.pack(fill="both", expand=True)
        text.insert("1.0", value)
        text.edit_modified(False)
        text.tag_configure("code", background=theme.color("accent_bg"), foreground=theme.color("accent"))
        if line:
            insert = ttk.Menubutton(top, text="Insert")
            insert.pack(side="right")
            menu = tk.Menu(insert, tearoff=False)
            insert["menu"] = menu
            for code, label in ms.INLINE_CODES:
                menu.add_command(label=f"{label}    {code}", command=lambda c=code: (text.insert("insert", c), text.focus_set()))
            menu.add_separator()
            menu.add_command(label="Icon…    #Pnnn", command=lambda: self._insert_icon(text))
            fonts = ttk.Menubutton(top, text="Font")
            fonts.pack(side="right", padx=(0, 4))
            font_menu = tk.Menu(fonts, tearoff=False)
            fonts["menu"] = font_menu
            for index, label, code in ms.FONT_CHOICES:
                font_menu.add_command(label=f"{label}    {code}",
                                      command=lambda i=index: self._restyle(text, lambda t, s, e: ms.apply_font(t, s, e, i)))
            font_menu.add_separator()
            font_menu.add_command(label="Remove font codes (selection, or all of this text)",
                                  command=lambda: self._restyle(text, ms.strip_fonts))
            hint.pack(anchor="w")
        idle_hint = "Font: select text to draw it in another font; a switch lasts one textbox line." if line else ""
        hint.configure(text=idle_hint)

        def highlight():
            text.tag_remove("code", "1.0", "end")
            try:
                source = ms.to_raw(text.get("1.0", "end-1c"))
            except UnicodeEncodeError:
                return
            position = 0
            tokens = tokenize(source)
            for i, token in enumerate(tokens):
                end = tokens[i + 1].offset if i + 1 < len(tokens) else len(source)
                length = len(ms.to_display(source[token.offset:end]))
                if token.code != "text":
                    text.tag_add("code", f"1.0+{position}c", f"1.0+{position + length}c")
                position += length

        def modified(_event=None):
            if text.edit_modified():
                text.edit_modified(False)
                highlight()
                self._commit()

        def hover(event):
            index = text.index(f"@{event.x},{event.y}")
            ranges = text.tag_prevrange("code", index + "+1c")
            if ranges and text.compare(ranges[0], "<=", index) and text.compare(index, "<", ranges[1]):
                hint.configure(text=ms.describe_inline(text.get(*ranges)))
            else:
                hint.configure(text=idle_hint)

        highlight()
        text.bind("<<Modified>>", modified)
        text.bind("<Motion>", hover)
        self._getters[spec.name] = lambda: text.get("1.0", "end-1c")

    def _insert_icon(self, text: tk.Text) -> None:
        """Pick a window/icon.tpl cell and insert its #Pnnn code (drawn 24px wide, centred)."""
        assets = self._get_assets()
        if assets is None:
            return
        try:
            sheet = assets.textures(ICON_SHEET)[0]
        except (ValueError, OSError, KeyError, IndexError):
            return
        count = (sheet.width // 24) * (sheet.height // 24)
        entries = [(f"{i:03X}", ms.ICON_LABELS.get(i, "")) for i in range(count)]

        def preview(value):
            image = icon_cell(sheet, int(value, 16)).resize((96, 96), Image.NEAREST)
            return ImageTk.PhotoImage(image)

        picker = _Picker(self, "Insert icon", entries, preview)
        if picker.result:
            text.insert("insert", "#P" + picker.result)
            text.focus_set()

    @staticmethod
    def _restyle(text: tk.Text, change) -> None:
        """Apply ``change(text, start, end) -> (text, start, end)`` to the selection (or cursor)."""
        source = text.get("1.0", "end-1c")
        if text.tag_ranges("sel"):
            start, end = (len(text.get("1.0", index)) for index in ("sel.first", "sel.last"))
        else:
            start = end = len(text.get("1.0", "insert"))
        new, start, end = change(source, start, end)
        if new != source:
            text.delete("1.0", "end")
            text.insert("1.0", new)
        text.tag_remove("sel", "1.0", "end")
        if start != end:
            text.tag_add("sel", f"1.0+{start}c", f"1.0+{end}c")
        text.mark_set("insert", f"1.0+{end}c")
        text.focus_set()

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
        new = step.edited(**values)
        error = ms.validate_step(new)
        self._form_error.configure(text=error or "")
        if error:
            return
        self._steps[index] = new
        self._update_row(index)
        self._changed()

    # -- pickers --------------------------------------------------------------
    def _pick_portrait(self, initial=""):
        assets = self._get_assets()
        if assets is None:
            return None
        return _Picker(self, "Choose portrait", portrait_names(assets),
                       lambda name: self._thumbs.portrait(assets, name, 220), _short(initial),
                       info=lambda name: face_details(assets, name)).result

    def _pick_background(self, initial=""):
        assets = self._get_assets()
        if assets is None:
            return None
        entries = [(name, "") for name in background_names(assets)]
        return _Picker(self, "Choose background", entries,
                       lambda name: self._thumbs.background(assets, name), initial).result

    # -- stage ----------------------------------------------------------------
    def _timeline(self):
        if self._timeline_cache is None:
            self._timeline_cache = build_timeline(self.text(), context=self._context)
        return self._timeline_cache

    def _scene_at_selection(self):
        try:
            timeline = self._timeline()
        except ValueError:
            return None
        indices = self._selected_indices()
        if not indices:
            return timeline.events[0].state
        end = self._end_offset(indices[-1])
        return max((e for e in timeline.events if e.source_offset < end),
                   key=lambda e: e.index, default=timeline.events[0]).state

    def _schedule_stage(self) -> None:
        if self._stage_after is None:
            self._stage_after = self.after(150, self._refresh_stage)

    def _refresh_stage(self) -> None:
        if self._stage_after is not None:
            self.after_cancel(self._stage_after)
            self._stage_after = None
        for child in self._tiles.winfo_children():
            child.destroy()
        scene = self._scene_at_selection()
        if scene is None:
            self._stage_info.configure(text="Scene could not be evaluated")
            return
        assets = self._get_assets()
        try:
            count = len(assets.seats(scene.layout)) if assets else 9
        except ValueError:
            count = 9
        box_style = self._box_style(scene.layout)
        self._stage_info.configure(text=f"Layout {ms.layout_label(scene.layout) if scene.layout else '—'}   ·   Background {scene.background or '—'}"
                                        f"   ·   {'box style ($c/$s/$d)' if box_style else 'seat style ($F)'}")
        if count == 0:
            ttk.Label(self._tiles, text="This layout has no portrait seats.").pack(side="left")
            return
        for seat in range(count):
            self._tile(seat, scene, assets, box_style)

    def _paint_tree_tags(self) -> None:
        self._tree.tag_configure("start", foreground=theme.color("muted"), background=theme.color("surface_alt"))
        self._tree.tag_configure("undecoded", foreground=theme.color("warn"))
        self._tree.tag_configure("playing", background=theme.color("highlight"))

    def _tile(self, seat, scene, assets, box_style) -> None:
        portrait = scene.portraits[seat]
        speaking = scene.speaker_seat == seat
        frame = tk.Frame(self._tiles, bd=2, relief="solid" if speaking else "groove",
                         background=theme.color("highlight" if speaking else "surface"), width=THUMB + 14,
                         height=THUMB + 40)
        frame.pack(side="left", padx=2)
        frame.pack_propagate(False)
        image = None
        if portrait.fid and assets is not None:
            try:
                image = self._thumbs.portrait(assets, portrait.fid)
            except (ValueError, OSError, IndexError, KeyError):
                image = None
        picture = tk.Label(frame, image=image or "", text="" if image else ("?" if portrait.fid else "+"),
                           background=frame["background"], font=("Segoe UI", 16), foreground=theme.color("faint"))
        picture.image = image
        picture.pack(fill="both", expand=True)
        label = (display_name(assets, portrait.fid) or _short(portrait.fid)) if portrait.fid else "empty"
        caption = tk.Label(frame, text=f"{'Box' if box_style else 'Seat'} {seat}\n{label}", font=("Segoe UI", 8),
                           background=frame["background"], foreground=theme.color("fg"))
        caption.pack(fill="x")
        for widget in (frame, picture, caption):
            widget.bind("<Button-1>", lambda e, s=seat: self._seat_clicked(s, box_style))
            widget.bind("<Button-3>", lambda e, s=seat, p=portrait: self._seat_menu(e, s, p, box_style))

    def _load_step(self, seat, fid, box_style):
        if box_style and seat < 4:
            return ms.new_step("show_speaker", box=seat, fid=fid)
        return ms.new_step("load_portrait", seat=seat, fid=fid)

    def _seat_clicked(self, seat, box_style) -> None:
        scene = self._scene_at_selection()
        if scene is not None and scene.portraits[seat].fid:
            return
        fid = self._pick_portrait()
        if fid:
            self.insert_steps([self._load_step(seat, fid, box_style)])

    def _seat_menu(self, event, seat, portrait, box_style) -> None:
        menu = tk.Menu(self, tearoff=False)
        box = box_style and seat < 4

        def replace():
            fid = self._pick_portrait(portrait.fid)
            if fid:
                self.insert_steps([self._load_step(seat, fid, box_style)])

        menu.add_command(label="Load portrait…" if not portrait.fid else "Replace portrait…", command=replace)
        if portrait.fid:
            menu.add_command(label="Speak a line", command=lambda: self.insert_steps([ms.new_step(
                "line", select="s" if box else "F", index=seat, flush=not box)]))
            menu.add_command(label="Dismiss box and portrait" if box else "Remove portrait",
                             command=lambda: self.insert_steps([ms.new_step("dismiss_box", box=seat) if box
                                                                else ms.new_step("remove_portrait", seat=seat)]))
            for kind, field_name in (("eyes", "mode"), ("blink", "speed"), ("mouth_set", "set")):
                sub = tk.Menu(menu, tearoff=False)
                spec = ms.STEP_KINDS[kind].fields[1]
                for value, label in spec.choices:
                    sub.add_command(label=label, command=lambda k=kind, f=field_name, v=value: self.insert_steps(
                        [ms.new_step(k, seat=seat, **{f: v})]))
                menu.add_cascade(label=ms.STEP_KINDS[kind].label, menu=sub)
        menu.tk_popup(event.x_root, event.y_root)
