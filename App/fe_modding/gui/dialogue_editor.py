"""Dialogue editor: browse and edit a project's chapter text files
(``files/Mess/*.m``) directly in the extracted project tree.

Messages are identified by ID (the ``speaker`` field of ``message.Message``);
event scripts play them by ID string (``TalkEvent("MS_02_OP_01")``), not by
index. The game finds an ID through its global name hash, so file order does
not matter to it, but IDs must not share a hash key with another loaded ID
(``message.engine_name_hash``). Every vanilla file keeps its IDs in ascending
byte order; the editor keeps that convention (research/CHAPTER_DATA_NOTES.md §5.4).
``message.write_messages()`` rebuilds the whole file, so messages can be
added, renamed and deleted freely; a new message plays only once a script
calls its ID.

The message is picked in the Message ID box and edited as readable text with
highlighted actions. The right-hand seat panel and playback share byte/source maps
with the editor; the on-disc message dialect remains unchanged."""

from __future__ import annotations

import html
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, simpledialog, ttk

from ..formats import dialogue_notation as notation, fe10_message, message
from ..formats.fe9_message_scene import TEMPLATES, decompile, layout_from_label, layout_label, line_plain_text, to_display, to_raw
from ..game_profile import DIALOGUE, profile_of
from ..formats.fe9_conversation_context import resolve_context, context_after_message
from ..formats.event_script import ScriptError, read_script_path
from ..project import ModProject
from .changelog import ChangeLog
from .conversation_preview import ConversationPreview
from . import theme
from .editor_panel import EditorPanel
from .scene_editor import DialogueStage, background_names, layout_labels

SCRIPT_SOURCES_DIR = "script_sources"  # ScriptEditor's .fe9s sidecar folder


def _sort_key(msg: message.Message) -> bytes:
    return msg.speaker.encode(message.ENCODING)


class DialogueEditor(EditorPanel):
    display_name = "Dialogue"

    def __init__(self, parent: tk.Misc, project: ModProject, changelog: ChangeLog):
        super().__init__(parent)
        self._project = project
        self._changelog = changelog
        profile = profile_of(project)
        self._fe10 = profile.message_dialect == "fe10"   # Radiant Dawn byte-code, shown in <...> notation
        self._fe9 = not self._fe10 and profile.supports(DIALOGUE)
        self._current_path: Path | None = None
        self._messages: list[message.Message] = []
        self._text_order: list[str] | None = None  # the file's text-blob order, kept on save
        self._dirty = False
        self._drafts = {}
        self._document = None
        self._scene_reload_id = None
        self._current_index: int | None = None

        self._build_widgets()
        self._load_chapter_list()

    # -- layout -------------------------------------------------------------
    def _build_widgets(self) -> None:
        # Chapter selection is driven by the chapter page (see
        # select_chapter() below), not shown here - this listbox is kept as
        # internal selection state only, so the loading logic beneath it
        # doesn't need to change.
        self._chapter_list = tk.Listbox(self, exportselection=False)
        self._chapter_list.bind("<<ListboxSelect>>", lambda e: self._on_chapter_selected())

        # top: message picker + message management + save
        top = ttk.Frame(self, padding=(8, 8, 8, 4))
        top.pack(fill="x")
        ttk.Label(top, text="Message ID:").pack(side="left")
        self._speaker_var = tk.StringVar()
        self._choices: list[int] = []   # message index of each dropdown entry
        self._id_box = ttk.Combobox(top, textvariable=self._speaker_var, width=34, height=25,
                                    postcommand=self._fill_id_choices)
        self._id_box.pack(side="left", padx=(6, 6))
        self._id_box.bind("<<ComboboxSelected>>", lambda e: self._on_id_chosen())
        self._id_box.bind("<Return>", lambda e: self._on_id_typed())
        self._id_box.bind("<FocusOut>", lambda e: self._show_current_id())
        self._manage_buttons = []
        for label, command in (("New…", self._add_message), ("Duplicate", self._duplicate_message),
                               ("Rename…", self._rename_message), ("Delete", self._delete_message)):
            button = ttk.Button(top, text=label, command=command, state="disabled")
            button.pack(side="left", padx=(0, 4))
            self._manage_buttons.append(button)
        self._status_label = ttk.Label(top, text="", style="Muted.TLabel")
        self._status_label.pack(side="right", padx=(8, 0))
        self._save_button = ttk.Button(top, text="Save Chapter", command=self._save, state="disabled")
        self._save_button.pack(side="right")
        self._empty_label = ttk.Label(self, text="", style="Muted.TLabel", padding=(8, 0))
        self._empty_label.pack(anchor="w")
        ttk.Label(
            self,
            text="Type an ID (or part of it) and press Enter, or open the list. Messages are saved sorted by ID, "
            "like vanilla; a new message plays once a chapter script calls its ID "
            "(e.g. TalkEvent(\"MS_05_EV_03\") in the Scripts tab).",
            style="Muted.TLabel", padding=(8, 0),
        ).pack(anchor="w")

        paned = ttk.PanedWindow(self, orient="horizontal")
        paned.pack(fill="both", expand=True)

        left = ttk.Frame(paned, padding=8)
        paned.add(left, weight=3)
        right = ttk.Frame(paned, padding=8)
        paned.add(right, weight=2)
        self._scene = (DialogueStage(right, lambda: self._preview.assets, self._insert_raw)
                       if self._fe9 else None)
        if self._scene is not None:
            self._scene.pack(fill="x", pady=(0, 8))
        self._editor_buttons = []
        self._build_toolbar(left)
        editor = ttk.Frame(left)
        editor.pack(fill="both", expand=True)
        self._text_widget = tk.Text(editor, wrap="word", height=18, undo=True,
                                    autoseparators=True, maxundo=-1, exportselection=False, padx=8, pady=8)
        scroll = ttk.Scrollbar(editor, command=self._text_widget.yview)
        def scrolled(first, last):
            scroll.set(first, last)
        self._text_widget.configure(yscrollcommand=scrolled)
        scroll.pack(side="right", fill="y")
        self._text_widget.pack(side="left", fill="both", expand=True)
        self._text_widget.bind("<<Modified>>", self._on_text_modified)
        self._text_widget.bind("<ButtonRelease-1>", self._cursor_changed)
        self._text_widget.bind("<KeyRelease>", self._cursor_changed)
        self._text_widget.bind("<Control-f>", lambda e: self._find_replace())
        self._text_widget.bind("<Control-h>", lambda e: self._find_replace())
        self._text_widget.bind("<Control-s>", lambda e: (self._save(), "break")[1])
        self._text_widget.bind("<Double-Button-1>", self._edit_action)
        self._text_widget.tag_configure("action", spacing1=2, spacing3=2)
        self._text_widget.tag_configure("notation_error", underline=True,
                                        foreground=theme.color("danger"))
        self._text_widget.tag_configure("playback_position", background=theme.color("highlight"),
                                        foreground=theme.color("fg"))
        self._text_widget.tag_configure("find", background=theme.color("highlight"))
        self._notation_error = ttk.Label(left, text="", style="Danger.TLabel", wraplength=600)
        self._notation_error.pack(anchor="w")
        ttk.Label(left, text="Write dialogue directly. Highlighted <actions> can be typed, inserted with buttons, "
                  "or double-clicked to edit. Pause power n waits 2^n frames.\n"
                  "Import/export uses UTF-8 text for this message. Literal < and >: <Bytes:3C> / <Bytes:3E>.",
                  style="Muted.TLabel", wraplength=600, justify="left").pack(anchor="w", pady=(4, 0))

        preview_frame = ttk.Frame(right)
        preview_frame.pack(fill="both", expand=True)
        ttk.Label(preview_frame, text="Live Preview").pack(anchor="w")
        self._preview = ConversationPreview(preview_frame, self._project)
        self._preview.on_position = self._highlight_playback_position
        self._preview.on_inheritance = self._resolve_preview_inheritance
        if self._scene is not None:
            self._preview.on_context_changed = self._scene.set_context
        self._preview.pack(fill="both", expand=True, pady=(4, 0))

        theme.on_change(self, self._refresh_editor_colors)
        self._editing_enabled(False)

    def _refresh_editor_colors(self):
        self._text_widget.tag_configure("playback_position", background=theme.color("highlight"), foreground=theme.color("fg"))
        self._text_widget.tag_configure("find", background=theme.color("highlight"))
        self._text_widget.tag_configure("notation_error", foreground=theme.color("danger"))
    def _build_toolbar(self, parent):
        row = ttk.Frame(parent)
        row.pack(fill='x', pady=(0, 4))
        for label, callback in (
            ('Undo', lambda: self._edit_event('<<Undo>>')),
            ('Redo', lambda: self._edit_event('<<Redo>>')),
            ('Find / Replace', self._find_replace),
            ('Import…', self._import_text), ('Export…', self._export_text),
        ):
            button = ttk.Button(row, text=label, command=callback)
            button.pack(side='left', padx=(0, 3))
            self._editor_buttons.append(button)
        if self._fe9:
            ttk.Label(row, text="Layout").pack(side="left", padx=(8, 2))
            self._scene_layout_choice = tk.StringVar()
            self._scene_layout_box = ttk.Combobox(
                row, textvariable=self._scene_layout_choice, width=18,
                postcommand=self._refresh_scene_choices)
            self._scene_layout_box.pack(side="left")
            for event in ("<<ComboboxSelected>>", "<Return>", "<FocusOut>"):
                self._scene_layout_box.bind(event, lambda _e: self._set_scene_action("Layout"), add="+")
        row = ttk.Frame(parent)
        row.pack(fill='x', pady=(0, 5))
        common = [('Speaker', 'Speaker' if self._fe10 else 'Select speaker'), ('Portrait', 'Show portrait' if self._fe10 else 'Portrait'),
                  ('Wait', 'Wait'), ('Pause', 'Pause power'), ('Clear', 'New page' if self._fe10 else 'Clear box')]
        for label, action in common:
            button = ttk.Button(row, text=label, command=lambda a=action: self._add_action(a))
            button.pack(side='left', padx=(0, 3))
            self._editor_buttons.append(button)
        button = ttk.Button(row, text='Actions…', command=self._action_palette)
        button.pack(side='left')
        self._editor_buttons.append(button)
        if self._fe9:
            ttk.Label(row, text="Background").pack(side="left", padx=(8, 2))
            self._scene_background_choice = tk.StringVar()
            self._scene_background_box = ttk.Combobox(
                row, textvariable=self._scene_background_choice, width=14,
                postcommand=self._refresh_scene_choices)
            self._scene_background_box.pack(side="left", padx=(0, 4))
            for event in ("<<ComboboxSelected>>", "<Return>", "<FocusOut>"):
                self._scene_background_box.bind(event, lambda _e: self._set_scene_action("Background"), add="+")
            search = ttk.Button(row, text="Search…", width=8, command=self._search_scene_background)
            search.pack(side="left")
            self._editor_buttons.append(search)

    def _refresh_scene_choices(self):
        assets = self._preview.assets if hasattr(self, "_preview") else None
        if assets is None:
            return
        self._scene_layout_box.configure(values=layout_labels(assets))
        self._scene_background_box.configure(values=background_names(assets))

    def _search_scene_background(self):
        if self._scene is None:
            return
        chosen = self._scene._pick_background(self._scene_background_choice.get())
        if chosen is not None:
            self._scene_background_choice.set(chosen)
            self._set_scene_action("Background")

    @staticmethod
    def _scene_value(text: str, name: str) -> str:
        for match in notation.TAG.finditer(text):
            label, separator, value = match.group(1).partition(":")
            if separator and label.strip().casefold() == name.casefold():
                return html.unescape(value)
        return ""

    def _sync_scene_choices(self) -> None:
        if not self._fe9:
            return
        text = self._text_widget.get("1.0", "end-1c")
        self._scene_layout_choice.set(layout_label(self._scene_value(text, "Layout")))
        self._scene_background_choice.set(self._scene_value(text, "Background"))

    def _set_scene_action(self, name: str) -> None:
        if self._selected_index() is None:
            return
        value = (layout_from_label(self._scene_layout_choice.get()) if name == "Layout"
                 else self._scene_background_choice.get().strip())
        self._flush_edit()
        if self._document is None:
            messagebox.showerror("Invalid dialogue", "Fix the message text before changing its scene.",
                                 parent=self)
            return
        widget = self._text_widget
        text = widget.get("1.0", "end-1c")
        if value == self._scene_value(text, name):
            return
        tag = f"<{name}:{notation._escape(value)}>" if value else ""
        if tag:
            try:
                notation.parse(tag, False)
            except ValueError as error:
                messagebox.showerror("Invalid scene", str(error), parent=self)
                self._sync_scene_choices()
                return
        existing = next((m for m in notation.TAG.finditer(text)
                         if m.group(1).partition(":")[0].strip().casefold() == name.casefold()), None)
        widget.edit_separator()
        if existing is not None:
            widget.replace(f"1.0+{existing.start()}c", f"1.0+{existing.end()}c", tag)
        elif tag:
            offset = 0
            if name == "Background":
                first = notation.TAG.match(text)
                if first is not None and first.group(1).partition(":")[0].strip().casefold() == "layout":
                    offset = first.end()
            widget.insert(f"1.0+{offset}c", tag)
        widget.edit_separator()
        self._flush_edit()

    def _edit_event(self, event):
        try:
            self._text_widget.event_generate(event)
        except tk.TclError:
            pass
        self._text_widget.focus_set()

    def _flush_edit(self):
        if hasattr(self, '_text_widget') and self._text_widget.edit_modified():
            self._text_widget.edit_modified(False)
            self._on_field_edited()

    def _parse_editor(self):
        text = self._text_widget.get('1.0', 'end-1c')
        for tag in ('action', 'notation_error', 'playback_position'):
            self._text_widget.tag_remove(tag, '1.0', 'end')
        for tag in self._text_widget.tag_names():
            if tag.startswith('action_frame_'):
                self._text_widget.tag_delete(tag)
        for match in notation.TAG.finditer(text):
            start, end = f'1.0+{match.start()}c', f'1.0+{match.end()}c'
            self._text_widget.tag_add('action', start, end)
        self._text_widget.tag_raise('sel')
        try:
            self._document = notation.parse(text, self._fe10)
        except notation.NotationError as error:
            self._document = None
            self._notation_error.config(text=str(error) + ' — preview uses the last valid text.')
            self._text_widget.tag_add('notation_error', f'1.0+{error.start}c', f'1.0+{error.end}c')
            if self._scene is not None:
                self._scene.enabled = False
            return False
        self._notation_error.config(text='')
        if self._scene is not None:
            self._scene.enabled = self._selected_index() is not None
        return True

    def _cursor_changed(self, event=None):
        if self._document is not None and self._scene is not None:
            position = len(self._text_widget.get('1.0', 'insert'))
            self._scene.highlight_offset(self._document.byte_at(position))

    def _replace_selection(self, text, *, whole=False):
        if self._selected_index() is None:
            return
        widget = self._text_widget
        widget.edit_separator()
        if whole:
            start, end = '1.0', 'end-1c'
        elif widget.tag_ranges('sel'):
            start, end = 'sel.first', 'sel.last'
        else:
            start = end = 'insert'
        widget.replace(start, end, text)
        widget.edit_separator()
        self._flush_edit()
        widget.focus_set()
        self._cursor_changed()

    def _insert_raw(self, raw):
        self._replace_selection(notation.display(raw, self._fe10).text)

    def _add_action(self, name):
        if self._selected_index() is None:
            return
        if name == 'Select speaker':
            scene = self._scene._scene_at_selection()
            name = 'Box' if scene is None or self._scene._box_style(scene.layout) else 'Seat'
        # Asset pickers remain searchable lists with portrait/background previews.
        if self._scene is not None and name in ('Portrait', 'Background'):
            value = self._scene._pick_portrait() if name == 'Portrait' else self._scene._pick_background()
            if value:
                self._replace_selection(f'<{name}:{notation._escape(value)}>')
            return
        defaults = {'Layout': '上下会話', 'Background': '', 'Show speaker': '0IKE',
                    'Portrait': 'IKE', 'Control': '', 'Seat': '04' if self._fe10 else '0',
                    'Box': '0', 'Dismiss box': '0', 'Small box': '0', 'Typing sound': '1',
                    'Pause power': '4', 'Transition ms': '1000', 'Markup': '#C22',
                    'Speaker': '04', 'Show portrait': '4D', 'Show portrait now': '4D',
                    'Attach portrait': '4D', 'Cast': 'IKE|SOREN'}
        if self._fe10 and name not in defaults:
            key = next((key for key, label in notation.FE10_NAMES.items() if label == name), None)
            if key is not None:
                fields = fe10_message.new_step(key).fields
                if key == 'V#:':
                    defaults[name] = fields['n'] + ':' + fields['value']
                elif key.endswith('#'):
                    defaults[name] = fields['n']
                elif key.endswith(':'):
                    defaults[name] = fields['value']
                elif key.endswith('|'):
                    defaults[name] = '|'.join(fields['items'])
                elif 'a' in fields:
                    defaults[name] = fields['a'] + fields['b']
        tag = f'<{name}>'
        if name in defaults:
            prompt = ('Power n (0–9); delay is 2^n frames:' if name == 'Pause power' else
                      'Box number (0–3) followed by portrait ID, e.g. 0IKE:' if name == 'Show speaker' else
                      'Actor hex digit followed by position, e.g. 04:' if self._fe10 and name in ('Speaker', 'Seat') else
                      f'{name}:')
            value = simpledialog.askstring(name, prompt, initialvalue=defaults[name], parent=self)
            if value is None:
                return
            tag = f'<{name}:{notation._escape(value)}>'
        try:
            notation.parse(tag, self._fe10)
        except ValueError as error:
            messagebox.showerror('Invalid action', str(error), parent=self)
            return
        self._replace_selection(tag)

    def _action_palette(self):
        if self._selected_index() is None:
            return
        window = tk.Toplevel(self)
        window.title('Insert action')
        window.transient(self.winfo_toplevel())
        body = ttk.Frame(window, padding=10)
        body.pack(fill='both', expand=True)
        window.geometry("760x620")
        ttk.Label(body, text="Choose an action to insert at the text cursor.").pack(anchor="w")
        names = list(dict.fromkeys(
            list((notation.FE10_NAMES if self._fe10 else notation.FE9_NAMES).values())
            + (["Pause power"] if self._fe10 else ["Markup"])))
        query = tk.StringVar()
        search = ttk.Entry(body, textvariable=query)
        search.pack(fill="x", pady=(6, 8))
        list_frame = ttk.Frame(body)
        list_frame.pack(fill="both", expand=True)
        canvas = tk.Canvas(list_frame, highlightthickness=0)
        scrollbar = ttk.Scrollbar(list_frame, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)
        actions = ttk.Frame(canvas)
        frame_id = canvas.create_window((0, 0), window=actions, anchor="nw")
        actions.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.bind("<Configure>", lambda e: canvas.itemconfigure(frame_id, width=e.width))

        def choose(name):
            window.destroy()
            self._add_action(name)

        def fill(*_args):
            for child in actions.winfo_children():
                child.destroy()
            words = query.get().casefold().split()
            visible = [name for name in names if all(word in name.casefold() for word in words)]
            for i, name in enumerate(visible):
                ttk.Button(actions, text=name, command=lambda n=name: choose(n)).grid(
                    row=i // 3, column=i % 3, sticky="ew", padx=3, pady=3)
            for column in range(3):
                actions.columnconfigure(column, weight=1)

        query.trace_add("write", fill)
        fill()
        search.focus_set()
        window.bind("<MouseWheel>", lambda e: canvas.yview_scroll(-int(e.delta / 120), "units"))
        window.bind("<Escape>", lambda e: window.destroy())
        window.grab_set()

    def _edit_action(self, event):
        position = len(self._text_widget.get('1.0', self._text_widget.index(f'@{event.x},{event.y}')))
        text = self._text_widget.get('1.0', 'end-1c')
        match = next((m for m in notation.TAG.finditer(text) if m.start() <= position < m.end()), None)
        if match is None:
            return
        value = simpledialog.askstring('Edit action', 'Action inside < >:', initialvalue=match.group(1), parent=self)
        if value is not None:
            self._text_widget.tag_remove('sel', '1.0', 'end')
            self._text_widget.tag_add('sel', f'1.0+{match.start()}c', f'1.0+{match.end()}c')
            self._replace_selection('<' + value + '>')
        return 'break'

    def _import_text(self):
        if self._selected_index() is None:
            return
        path = filedialog.askopenfilename(parent=self, title='Import dialogue text', filetypes=[('Text files', '*.txt'), ('All files', '*.*')])
        if not path:
            return
        try:
            text = Path(path).read_text(encoding='utf-8-sig')
        except (OSError, UnicodeError) as error:
            messagebox.showerror('Could not import text', str(error), parent=self)
            return
        replace = messagebox.askyesnocancel('Import dialogue text',
                    'Replace this entire message?\nYes: replace message.\nNo: insert at cursor or replace selected text.\nThis can be undone.', parent=self)
        if replace is not None:
            self._replace_selection(text, whole=replace)

    def _export_text(self):
        index = self._selected_index()
        if index is None:
            return
        path = filedialog.asksaveasfilename(parent=self, title='Export dialogue text', defaultextension='.txt',
                    initialfile='dialogue.txt', filetypes=[('Text files', '*.txt')])
        if not path:
            return
        try:
            Path(path).write_text(self._text_widget.get('1.0', 'end-1c'), encoding='utf-8')
        except (OSError, UnicodeError) as error:
            messagebox.showerror('Could not export text', str(error), parent=self)

    def _find_replace(self):
        if self._selected_index() is None:
            return 'break'
        window = tk.Toplevel(self)
        window.title('Find / Replace')
        window.transient(self.winfo_toplevel())
        body = ttk.Frame(window, padding=10)
        body.pack(fill='both', expand=True)
        find, replacement = tk.StringVar(), tk.StringVar()
        for row, (label, var) in enumerate((('Find', find), ('Replace with', replacement))):
            ttk.Label(body, text=label).grid(row=row, column=0, sticky='w')
            entry = ttk.Entry(body, textvariable=var, width=40)
            entry.grid(row=row, column=1, columnspan=3, sticky='ew')
            if row == 0:
                entry.focus_set()
        status = ttk.Label(body)
        status.grid(row=3, column=0, columnspan=4, sticky='w')
        def next_match():
            self._text_widget.tag_remove('find', '1.0', 'end')
            needle = find.get()
            if not needle:
                return
            index = self._text_widget.search(needle, 'insert', stopindex='end', exact=True)
            if not index:
                index = self._text_widget.search(needle, '1.0', stopindex='end', exact=True)
            if index:
                end = f'{index}+{len(needle)}c'
                self._text_widget.tag_add('find', index, end)
                self._text_widget.mark_set('insert', end)
                self._text_widget.see(index)
            status.config(text='' if index else 'No matches')
        def replace_all():
            needle = find.get()
            if needle:
                text = self._text_widget.get('1.0', 'end-1c')
                count = text.count(needle)
                if count:
                    self._replace_selection(text.replace(needle, replacement.get()), whole=True)
                status.config(text=f'{count} replacement(s)')
        ttk.Button(body, text='Find next', command=next_match).grid(row=2, column=1, pady=6)
        ttk.Button(body, text='Replace all', command=replace_all).grid(row=2, column=2, pady=6)
        def close():
            self._text_widget.tag_remove('find', '1.0', 'end')
            window.destroy()
        ttk.Button(body, text='Close', command=close).grid(row=2, column=3)
        window.protocol('WM_DELETE_WINDOW', close)
        window.bind('<Escape>', lambda e: close())
        return 'break'

    def _highlight_playback_position(self, offset: int, kind: str) -> None:
        self._text_widget.tag_remove("playback_position", "1.0", "end")
        if self._document is None:
            return
        span = self._document.at_byte(offset)
        if span is None:
            return
        if self._scene is not None:
            self._scene.highlight_offset(span.byte_end)
        start, end = f"1.0+{span.start}c", f"1.0+{span.end}c"
        self._text_widget.tag_add("playback_position", start, end)
        self._text_widget.tag_raise("playback_position")
        self._text_widget.tag_raise("sel")
        self._text_widget.see(start)

    def _editing_enabled(self, enabled: bool) -> None:
        state = "normal" if enabled else "disabled"
        self._text_widget.config(state=state)
        for button in self._editor_buttons:
            button.config(state=state)
        if self._fe9:
            self._scene_layout_box.configure(state=state)
            self._scene_background_box.configure(state=state)
        if self._scene is not None:
            self._scene.enabled = enabled
        if self._scene is not None and not enabled:
            self._scene.load("", keep_selection=False)

    # -- data loading ---------------------------------------------------------
    def _load_chapter_list(self) -> None:
        self._chapter_paths = sorted(self._project.extracted_dir.glob("**/Mess/*.m"))
        self._chapter_list.delete(0, "end")
        for path in self._chapter_paths:
            self._chapter_list.insert("end", path.name)

        self._empty_label.config(
            text="No dialogue files found.\nExtract the project first." if not self._chapter_paths else ""
        )

    def _on_chapter_selected(self) -> None:
        self._flush_edit()
        selection = self._chapter_list.curselection()
        if not selection:
            return

        if self._dirty and not self._confirm_discard():
            self._chapter_list.selection_clear(0, "end")
            if self._current_path in self._chapter_paths:
                self._chapter_list.selection_set(self._chapter_paths.index(self._current_path))
            return

        self._current_path = self._chapter_paths[selection[0]]
        try:
            self._messages = message.read_messages_path(self._current_path)
            self._text_order = message.read_text_order_path(self._current_path)
        except Exception as exc:  # noqa: BLE001 - surfaced to the user, not swallowed
            messagebox.showerror("Could not read chapter", str(exc), parent=self)
            return

        self._drafts.clear()
        self._refresh_message_list()
        self._dirty = False
        self._save_button.config(state="normal")
        for button in self._manage_buttons:
            button.config(state="normal")
        status = f"{len(self._messages)} messages"
        if self._fe10:
            name = self._current_path.name
            status += f" · {fe10_message.language_of(name)}"
            if not fe10_message.decoded_language(name):
                status += " (accented letters are not decoded yet and show as other characters)"
        self._status_label.config(text=status)

    def _shown(self, text: str) -> str:
        """What the text widget shows for a message's text."""
        return notation.display(text, self._fe10).text

    def _list_preview(self, text: str) -> str:
        if self._fe10:
            return fe10_message.plain_text(text)[:60]
        if self._fe9:
            try:
                text = "".join(line_plain_text(s.fields["text"]) + " "
                               for s in decompile(text) if s.kind == "line")
            except UnicodeError:
                pass
        return " ".join(text.split())[:60]

    @staticmethod
    def _id_label(msg_id: str) -> str:
        try:
            return to_display(msg_id)
        except UnicodeError:
            return msg_id

    def _choice_label(self, msg: message.Message) -> str:
        preview = self._list_preview(msg.text)
        return self._id_label(msg.speaker) + (f"   —   {preview}" if preview else "")

    def _fill_id_choices(self) -> None:
        """Dropdown entries: every message, or those matching the typed text."""
        typed = self._speaker_var.get().strip().casefold()
        current = self._current_index
        if current is not None and typed == self._id_label(self._messages[current].speaker).casefold():
            typed = ""
        self._choices = [i for i, m in enumerate(self._messages)
                         if not typed or typed in self._choice_label(m).casefold()]
        self._id_box.configure(values=[self._choice_label(self._messages[i]) for i in self._choices])
        if current in self._choices:
            self._id_box.current(self._choices.index(current))
            self._show_current_id()

    def _show_current_id(self) -> None:
        index = self._current_index
        self._speaker_var.set("" if index is None else self._id_label(self._messages[index].speaker))

    def _on_id_chosen(self) -> None:
        position = self._id_box.current()
        if 0 <= position < len(self._choices):
            self._select_index(self._choices[position])
        else:
            self._show_current_id()
        self._id_box.selection_clear()

    def _on_id_typed(self) -> None:
        typed = self._speaker_var.get().strip()
        labels = [self._id_label(m.speaker) for m in self._messages]
        matches = ([labels.index(typed)] if typed in labels else
                   [i for i, label in enumerate(labels) if typed.casefold() in label.casefold()])
        if len(matches) == 1:
            self._select_index(matches[0])
        elif matches:
            self._fill_id_choices()
            self._id_box.event_generate("<Down>")  # open the filtered list
        else:
            self._status_label.config(text=f"No message matches {typed!r}")
            self._show_current_id()

    def _select_index(self, index: int | None) -> None:
        if index is not None and not 0 <= index < len(self._messages):
            index = None
        self._flush_edit()
        self._current_index = index
        self._show_current_id()
        if index is None:
            self._clear_message()
        else:
            self._on_message_selected()

    def _clear_message(self) -> None:
        self._editing_enabled(False)
        self._suspend_edit_tracking = True
        self._text_widget.config(state="normal")
        self._text_widget.delete("1.0", "end")
        self._text_widget.edit_modified(False)
        self._text_widget.config(state="disabled")
        self._suspend_edit_tracking = False
        self._document = None
        self._sync_scene_choices()
        self._preview.update_message("", "")

    def _refresh_message_list(self, select: int | None = None) -> None:
        self._select_index(select if select is not None else (0 if self._messages else None))

    def _selected_index(self) -> int | None:
        return self._current_index

    def _script_path(self) -> Path:
        return self._current_path.parent.parent / 'Scripts' / (self._current_path.stem.upper()+'.cmb')

    def _on_message_selected(self) -> None:
        index = self._selected_index()
        if index is None:
            return
        msg = self._messages[index]

        self._editing_enabled(True)
        self._suspend_edit_tracking = True
        self._text_widget.delete("1.0", "end")
        self._text_widget.insert("1.0", self._drafts.get(msg.speaker, self._shown(msg.text)))
        self._text_widget.edit_reset()
        self._parse_editor()
        self._sync_scene_choices()
        if self._scene is not None:
            self._scene.load(msg.text, keep_selection=False)
        context = None
        sources = ()
        if self._fe9:
            try:
                resolution = resolve_context(self._script_path(), {m.speaker:m.text for m in self._messages}, msg.speaker)
                context = resolution.context
                sources = resolution.sources
                self._preview.context_description = resolution.description
            except (ValueError, OSError, IndexError, UnicodeError, ScriptError) as error:
                self._preview.context_description = f"Initial context could not be resolved: {error}"
            self._preview.update_message(msg.speaker, msg.text, context=context, message_id=(str(self._current_path), msg.speaker))
            self._preview.set_inheritance_source(sources, [m.speaker for m in self._messages if m.speaker != msg.speaker])
        else:
            self._preview.update_message(msg.speaker, msg.text, message_id=(str(self._current_path), msg.speaker))
        self._text_widget.edit_modified(False)
        self._suspend_edit_tracking = False

    # -- editing ----------------------------------------------------------

    def _resolve_preview_inheritance(self, source):
        index = self._selected_index()
        if index is None or self._current_path is None:
            raise ValueError("Select a message first")
        target = self._messages[index].speaker
        messages = {m.speaker:m.text for m in self._messages}
        script = self._script_path()
        return (resolve_context(script, messages, target) if source is None else
                context_after_message(script, messages, source, target))
    _suspend_edit_tracking = False

    def _on_text_modified(self, event=None) -> None:
        if self._text_widget.edit_modified():
            self._text_widget.edit_modified(False)
            self._on_field_edited()

    def _on_field_edited(self) -> None:
        if self._suspend_edit_tracking:
            return
        index = self._selected_index()
        if index is None:
            return
        self._mark_dirty()
        if not self._parse_editor():
            self._drafts[self._messages[index].speaker] = self._text_widget.get("1.0", "end-1c")
            return
        self._drafts.pop(self._messages[index].speaker, None)
        self._sync_scene_choices()
        self._set_current_text(self._document.raw)
        if self._scene is not None:
            if self._scene_reload_id is not None:
                self.after_cancel(self._scene_reload_id)
            self._scene_reload_id = self.after(150, self._reload_scene_from_raw)

    def _reload_scene_from_raw(self) -> None:
        self._scene_reload_id = None
        index = self._selected_index()
        if index is not None and self._scene is not None:
            self._scene.load(self._messages[index].text)
            self._cursor_changed()

    def _set_current_text(self, new_text: str) -> None:
        index = self._selected_index()
        if index is None:
            return
        msg_id = self._messages[index].speaker
        self._messages[index] = message.Message(speaker=msg_id, text=new_text)
        self._preview.update_message(msg_id, new_text, message_id=(str(self._current_path), msg_id))
        self._mark_dirty()

    def _mark_dirty(self) -> None:
        self._dirty = True
        self._status_label.config(text="Unsaved changes")

    # -- message management -------------------------------------------------
    def _id_problem(self, value: str, *, ignore: str | None = None) -> tuple[str | None, str | None]:
        """(raw ID, None) if usable, else (None, reason). `ignore` is the ID being renamed."""
        try:
            raw = to_raw(value)
        except UnicodeEncodeError:
            return None, "The ID contains characters outside Shift-JIS."
        if not value or "|" in value:
            return None, "The ID cannot be empty or contain '|'."
        others = [(m.speaker, self._current_path.name) for m in self._messages if m.speaker != ignore]
        common = self._current_path.parent / "common.m"
        if common != self._current_path:
            try:
                others += [(m.speaker, common.name) for m in message.read_messages_path(common)]
            except (OSError, ValueError):
                pass
        buckets = profile_of(self._project).name_hash_buckets
        key = message.engine_name_hash(raw, buckets)
        for other, where in others:
            if other == raw:
                return None, f"{value} already exists in {where}."
            if message.engine_name_hash(other, buckets) == key:
                # The engine matches IDs by hash only (see message.engine_name_hash).
                return None, (f"{value} has the same engine hash as {self._id_label(other)} ({where}); "
                              "the game could show the wrong message. Choose another ID.")
        return raw, None

    def _ask_id(self, title: str, initial: str, *, ignore: str | None = None) -> str | None:
        while True:
            value = simpledialog.askstring(title, "Message ID:", initialvalue=initial, parent=self)
            if value is None:
                return None
            value = value.strip()
            raw, problem = self._id_problem(value, ignore=ignore)
            if raw is not None:
                return raw
            messagebox.showerror(title, problem, parent=self)
            initial = value

    def _insert_sorted(self, msg: message.Message) -> None:
        self._flush_edit()
        self._messages.append(msg)
        self._messages.sort(key=_sort_key)
        self._refresh_message_list(select=self._messages.index(msg))
        self._mark_dirty()

    def _id_prefix(self) -> str:
        ids = [self._id_label(m.speaker) for m in self._messages]
        return ids[0].rsplit("_", 2)[0] + "_" if ids and ids[0].startswith("MS_") else ""

    def _add_message(self) -> None:
        self._flush_edit()
        if self._current_path is None:
            return
        templates = fe10_message.TEMPLATES if self._fe10 else TEMPLATES
        text = ""
        if self._fe9 or self._fe10:
            dialog = _TemplateDialog(self, self._id_prefix() + "NEW", templates)
            if dialog.result is None:
                return
            name, template = dialog.result
            initial = name
            text = templates.get(template, "")
            if self._fe10:
                text = fe10_message.to_raw(text)
        else:
            initial = self._id_prefix() + "NEW"
        msg_id = self._validated(initial) if self._fe9 or self._fe10 else self._ask_id("New message", initial)
        if msg_id is None:
            return
        self._insert_sorted(message.Message(speaker=msg_id, text=text))
        self._changelog.append(self._current_path.name, f"Added message {self._id_label(msg_id)}")

    def _validated(self, value: str) -> str | None:
        raw, problem = self._id_problem(value.strip())
        if raw is not None:
            return raw
        messagebox.showerror("New message", problem, parent=self)
        return self._ask_id("New message", value)

    def _duplicate_message(self) -> None:
        self._flush_edit()
        index = self._selected_index()
        if index is None:
            return
        source = self._messages[index]
        msg_id = self._ask_id("Duplicate message", self._id_label(source.speaker) + "_COPY")
        if msg_id is None:
            return
        if source.speaker in self._drafts:
            self._drafts[msg_id] = self._drafts[source.speaker]
        self._insert_sorted(message.Message(speaker=msg_id, text=source.text))
        self._changelog.append(self._current_path.name,
                               f"Duplicated {self._id_label(source.speaker)} as {self._id_label(msg_id)}")

    def _script_references(self, msg_id: str) -> list[str]:
        """Where the chapter script passes this ID as a string. Warning only."""
        found = []
        script = self._script_path()
        try:
            count = sum(1 for function in read_script_path(script) for ins in function.instructions
                        if ins[1].startswith("pushstr") and len(ins) > 2 and ins[2] == msg_id)
            if count:
                found.append(f"{script.name}: {count} call(s)")
        except (OSError, ValueError, IndexError, UnicodeError, ScriptError):
            pass
        sidecar = self._project.directory / SCRIPT_SOURCES_DIR / (script.stem + ".fe9s")
        try:
            if f'"{self._id_label(msg_id)}"' in sidecar.read_text(encoding="utf-8"):
                found.append(f"{sidecar.name} (Scripts tab source)")
        except OSError:
            pass
        return found

    def _confirm_references(self, msg_id: str, action: str) -> bool:
        references = self._script_references(msg_id)
        if not references:
            return True
        return messagebox.askyesno(
            f"{action} message",
            f"{self._id_label(msg_id)} is used by:\n  " + "\n  ".join(references) +
            f"\n\n{action} will not update the script, so those calls will no longer find it. Continue?",
            icon="warning", parent=self)

    def _rename_message(self) -> None:
        self._flush_edit()
        index = self._selected_index()
        if index is None:
            return
        old = self._messages[index]
        msg_id = self._ask_id("Rename message", self._id_label(old.speaker), ignore=old.speaker)
        if msg_id is None or not self._confirm_references(old.speaker, "Renaming"):
            return
        if old.speaker in self._drafts:
            self._drafts[msg_id] = self._drafts.pop(old.speaker)
        del self._messages[index]
        self._insert_sorted(message.Message(speaker=msg_id, text=old.text))
        self._changelog.append(self._current_path.name,
                               f"Renamed {self._id_label(old.speaker)} to {self._id_label(msg_id)}")

    def _delete_message(self) -> None:
        self._flush_edit()
        index = self._selected_index()
        if index is None:
            return
        old = self._messages[index]
        if not self._confirm_references(old.speaker, "Deleting"):
            return
        if not messagebox.askyesno("Delete message", f"Delete {self._id_label(old.speaker)}?", parent=self):
            return
        self._drafts.pop(old.speaker, None)
        del self._messages[index]
        self._refresh_message_list(select=min(index, len(self._messages) - 1) if self._messages else None)
        self._mark_dirty()
        self._changelog.append(self._current_path.name, f"Deleted message {self._id_label(old.speaker)}")

    # -- save -------------------------------------------------------------
    def _save(self) -> None:
        if self._current_path is None:
            return
        self._flush_edit()
        if self._drafts:
            messagebox.showerror("Cannot save chapter", "Fix invalid actions before saving: " +
                                 ", ".join(self._id_label(key) for key in self._drafts), parent=self)
            return
        # Order doesn't matter to the game (hash lookup); keep vanilla's sorted layout.
        ordered = sorted(self._messages, key=_sort_key)
        try:
            message.write_messages_path(self._current_path, ordered, self._text_order)
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror("Could not save chapter", str(exc), parent=self)
            return
        if ordered != self._messages:
            index = self._selected_index()
            selected = self._messages[index] if index is not None else None
            self._messages = ordered
            self._refresh_message_list(select=ordered.index(selected) if selected in ordered else None)
        self._dirty = False
        self._status_label.config(text=f"Saved {self._current_path.name}")
        self._changelog.append(self._current_path.name, f"Saved {len(self._messages)} messages")

    def _confirm_discard(self) -> bool:
        return messagebox.askyesno(
            "Discard changes?", "This chapter has unsaved changes. Discard them?", parent=self
        )

    def cleanup(self) -> None:
        if self._scene_reload_id is not None:
            self.after_cancel(self._scene_reload_id)
            self._scene_reload_id = None
        if self._scene is not None:
            self._scene.cleanup()
        self._preview.cleanup()

    # -- workspace navigation -------------------------------------------------
    def refresh_chapter_list(self) -> None:
        """Re-glob for chapter files - this panel is created once and kept
        alive for the rest of the session (see editor_panel.py), so its own
        chapter list otherwise goes stale after a chapter is added at
        runtime (see MainWindow._add_chapter()/chapters.duplicate_chapter())."""
        self._load_chapter_list()

    def select_chapter(self, path: Path | None) -> None:
        """Jump straight to a chapter, called by the chapter page. No-op
        if this chapter has no dialogue file, or if the user cancels a
        pending unsaved-changes prompt."""
        if path is None or path not in self._chapter_paths:
            return
        if not self.confirm_navigate_away():
            return
        index = self._chapter_paths.index(path)
        self._chapter_list.selection_clear(0, "end")
        self._chapter_list.selection_set(index)
        self._chapter_list.see(index)
        self._on_chapter_selected()

    @property
    def current_path(self) -> Path | None:
        return self._current_path

    def message_ids(self) -> set[str]:
        """The IDs of the loaded file as shown (unsaved additions included)."""
        return {self._id_label(m.speaker) for m in self._messages}

    def add_message(self, message_id: str, text: str) -> bool:
        """Add a message to the loaded file and select it; False (after
        telling the user why) when the ID cannot be used."""
        if self._current_path is None:
            return False
        raw, problem = self._id_problem(message_id)
        if raw is None:
            messagebox.showerror("New message", problem, parent=self)
            return False
        self._insert_sorted(message.Message(speaker=raw, text=text))
        self._changelog.append(self._current_path.name, f"Added message {message_id}")
        return True

    def select_message(self, message_id: str) -> None:
        """Select a message of the loaded chapter by ID (no-op if absent)."""
        for i, msg in enumerate(self._messages):
            if msg.speaker == message_id:
                self._select_index(i)
                return


class _TemplateDialog(tk.Toplevel):
    """New message: ID and starting template."""

    def __init__(self, parent, initial_id: str, templates: dict):
        super().__init__(parent)
        self.title("New message")
        self.transient(parent.winfo_toplevel())
        self.result = None
        body = ttk.Frame(self, padding=10)
        body.pack(fill="both", expand=True)
        ttk.Label(body, text="Message ID:").grid(row=0, column=0, sticky="w")
        self._id = tk.StringVar(value=initial_id)
        entry = ttk.Entry(body, textvariable=self._id, width=32)
        entry.grid(row=0, column=1, sticky="ew", pady=2)
        ttk.Label(body, text="Start from:").grid(row=1, column=0, sticky="w")
        self._template = tk.StringVar(value=next(iter(templates)))
        ttk.Combobox(body, textvariable=self._template, values=list(templates), state="readonly",
                     width=30).grid(row=1, column=1, sticky="ew", pady=2)
        buttons = ttk.Frame(body)
        buttons.grid(row=2, column=0, columnspan=2, sticky="e", pady=(8, 0))
        ttk.Button(buttons, text="Create", command=self._accept).pack(side="left")
        ttk.Button(buttons, text="Cancel", command=self.destroy).pack(side="left", padx=(4, 0))
        entry.bind("<Return>", lambda e: self._accept())
        self.bind("<Escape>", lambda e: self.destroy())
        entry.focus_set()
        entry.select_range(0, "end")
        self.grab_set()
        self.wait_window()

    def _accept(self):
        self.result = (self._id.get(), self._template.get())
        self.destroy()
