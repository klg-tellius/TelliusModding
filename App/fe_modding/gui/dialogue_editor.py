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

The message is picked in the Message ID box. For Path of Radiance its steps
are listed on the left; the right side edits the selected step (with the
stage, ``scene_editor.py``) or the raw text. Both edit the same bytes."""

from __future__ import annotations

import tkinter as tk
from pathlib import Path
from tkinter import messagebox, simpledialog, ttk

from ..formats import message
from ..formats.fe9_message_scene import TEMPLATES, decompile, line_plain_text, to_display, to_raw
from ..game_profile import DIALOGUE, profile_of
from ..formats.fe9_conversation_context import resolve_context, context_after_message
from ..formats.event_script import ScriptError, read_script_path
from ..project import ModProject
from .changelog import ChangeLog
from .conversation_preview import ConversationPreview
from . import theme
from .editor_panel import EditorPanel
from .scene_editor import SceneEditor

SCRIPT_SOURCES_DIR = "script_sources"  # ScriptEditor's .fe9s sidecar folder


def _sort_key(msg: message.Message) -> bytes:
    return msg.speaker.encode(message.ENCODING)


class DialogueEditor(EditorPanel):
    display_name = "Dialogue"

    def __init__(self, parent: tk.Misc, project: ModProject, changelog: ChangeLog):
        super().__init__(parent)
        self._project = project
        self._changelog = changelog
        self._fe9 = profile_of(project).supports(DIALOGUE)  # step editing; Radiant Dawn text is raw-only for now
        self._current_path: Path | None = None
        self._messages: list[message.Message] = []
        self._dirty = False
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

        # left: the message's steps over the selected step's form (FE9), or its raw text (FE10);
        # right: the stage (FE9) over the live preview
        left = ttk.Frame(paned, padding=8)
        paned.add(left, weight=2)
        right = ttk.Frame(paned, padding=(8, 8, 8, 8))
        paned.add(right, weight=3)

        if self._fe9:
            left_split = ttk.PanedWindow(left, orient="vertical")
            left_split.pack(fill="both", expand=True)
            steps_frame = ttk.Frame(left_split)
            left_split.add(steps_frame, weight=1)
            ttk.Label(steps_frame, text="Steps").pack(anchor="w")
            self._notebook = ttk.Notebook(left_split)
            left_split.add(self._notebook, weight=1)
            self._scene = SceneEditor(steps_frame, right, self._notebook, lambda: self._preview.assets)
            self._scene.pack(fill="both", expand=True, pady=(4, 4))
            self._scene.on_change = self._on_scene_changed
            self._scene.on_step_selected = lambda offset: self._preview.seek_before(offset)
            self._scene.stage.pack(fill="x", pady=(0, 8))
            self._notebook.add(self._scene.form_page, text="Step")

            # The steps take the top half of the column, the form the bottom half.
            def place_sash(event):
                if event.height > 100:
                    left_split.sashpos(0, event.height // 2)
                    left_split.unbind("<Configure>", binding)
            binding = left_split.bind("<Configure>", place_sash, add="+")
            raw_tab = ttk.Frame(self._notebook, padding=4)
            self._notebook.add(raw_tab, text="Raw text")
            text_parent = raw_tab
        else:
            self._scene = None
            ttk.Label(left, text="Text:").pack(anchor="w")
            text_parent = left

        self._text_widget = tk.Text(text_parent, wrap="word", height=11)
        self._text_widget.pack(fill="both", expand=True)
        self._text_widget.bind("<<Modified>>", self._on_text_modified)
        self._text_widget.tag_configure("playback_position", background=theme.color("highlight"),
                                        foreground=theme.color("fg"))
        ttk.Label(
            text_parent,
            text="Raw message source: dialogue text interleaved with $ commands\n"
            "(portraits, boxes, waits...)." + (" The step list edits the same bytes." if self._fe9 else ""),
            style="Muted.TLabel",
            justify="left",
        ).pack(anchor="w", pady=(4, 0))

        preview_frame = ttk.Frame(right)
        preview_frame.pack(fill="both", expand=True)
        ttk.Label(preview_frame, text="Live Preview").pack(anchor="w")
        self._preview = ConversationPreview(preview_frame, self._project)
        self._preview.on_position = self._highlight_playback_position
        self._preview.on_inheritance = self._resolve_preview_inheritance
        if self._scene is not None:
            self._preview.on_context_changed = self._scene.set_context
        self._preview.pack(fill="both", expand=True, pady=(4, 0))

        self._editing_enabled(False)

    def _highlight_playback_position(self, offset: int, kind: str) -> None:
        # The editor preserves one cp437 character per source byte. Do not move
        # the insertion cursor or selection, and never modify message contents.
        scene = getattr(self, "_scene", None)
        if scene is not None:
            scene.highlight_offset(offset)
        self._text_widget.tag_remove("playback_position", "1.0", "end")
        text = self._text_widget.get("1.0", "end-1c")
        if not text:
            return
        offset = min(offset, len(text)-1)
        end = offset+1
        if text[offset:offset+1] == "$":
            end = min(len(text), offset+2)
        start_index, end_index = f"1.0+{offset}c", f"1.0+{end}c"
        self._text_widget.tag_add("playback_position", start_index, end_index)
        if self._text_widget.focus_get() is not self._text_widget:
            self._text_widget.see(start_index)

    def _editing_enabled(self, enabled: bool) -> None:
        state = "normal" if enabled else "disabled"
        self._text_widget.config(state=state)
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
        except Exception as exc:  # noqa: BLE001 - surfaced to the user, not swallowed
            messagebox.showerror("Could not read chapter", str(exc), parent=self)
            return

        self._refresh_message_list()
        self._dirty = False
        self._save_button.config(state="normal")
        for button in self._manage_buttons:
            button.config(state="normal")
        self._status_label.config(text=f"{len(self._messages)} messages")

    def _list_preview(self, text: str) -> str:
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
        self._text_widget.insert("1.0", msg.text)
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
        self._set_current_text(self._text_widget.get("1.0", "end-1c"))
        if self._scene is not None:
            if self._scene_reload_id is not None:
                self.after_cancel(self._scene_reload_id)
            self._scene_reload_id = self.after(300, self._reload_scene_from_raw)

    def _reload_scene_from_raw(self) -> None:
        self._scene_reload_id = None
        index = self._selected_index()
        if index is not None and self._scene is not None:
            self._scene.load(self._messages[index].text)

    def _on_scene_changed(self, text: str) -> None:
        index = self._selected_index()
        if index is None:
            return
        self._suspend_edit_tracking = True
        self._text_widget.delete("1.0", "end")
        self._text_widget.insert("1.0", text)
        self._text_widget.edit_modified(False)
        self._suspend_edit_tracking = False
        self._set_current_text(text)

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
        key = message.engine_name_hash(raw)
        for other, where in others:
            if other == raw:
                return None, f"{value} already exists in {where}."
            if message.engine_name_hash(other) == key:
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
        self._messages.append(msg)
        self._messages.sort(key=_sort_key)
        self._refresh_message_list(select=self._messages.index(msg))
        self._mark_dirty()

    def _id_prefix(self) -> str:
        ids = [self._id_label(m.speaker) for m in self._messages]
        return ids[0].rsplit("_", 2)[0] + "_" if ids and ids[0].startswith("MS_") else ""

    def _add_message(self) -> None:
        if self._current_path is None:
            return
        template = ""
        if self._fe9:
            dialog = _TemplateDialog(self, self._id_prefix() + "NEW")
            if dialog.result is None:
                return
            name, template = dialog.result
            initial = name
        else:
            initial = self._id_prefix() + "NEW"
        msg_id = self._ask_id("New message", initial) if not self._fe9 else self._validated(initial)
        if msg_id is None:
            return
        self._insert_sorted(message.Message(speaker=msg_id, text=TEMPLATES.get(template, "")))
        self._changelog.append(self._current_path.name, f"Added message {self._id_label(msg_id)}")

    def _validated(self, value: str) -> str | None:
        raw, problem = self._id_problem(value.strip())
        if raw is not None:
            return raw
        messagebox.showerror("New message", problem, parent=self)
        return self._ask_id("New message", value)

    def _duplicate_message(self) -> None:
        index = self._selected_index()
        if index is None:
            return
        source = self._messages[index]
        msg_id = self._ask_id("Duplicate message", self._id_label(source.speaker) + "_COPY")
        if msg_id is None:
            return
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
        index = self._selected_index()
        if index is None:
            return
        old = self._messages[index]
        msg_id = self._ask_id("Rename message", self._id_label(old.speaker), ignore=old.speaker)
        if msg_id is None or not self._confirm_references(old.speaker, "Renaming"):
            return
        del self._messages[index]
        self._insert_sorted(message.Message(speaker=msg_id, text=old.text))
        self._changelog.append(self._current_path.name,
                               f"Renamed {self._id_label(old.speaker)} to {self._id_label(msg_id)}")

    def _delete_message(self) -> None:
        index = self._selected_index()
        if index is None:
            return
        old = self._messages[index]
        if not self._confirm_references(old.speaker, "Deleting"):
            return
        if not messagebox.askyesno("Delete message", f"Delete {self._id_label(old.speaker)}?", parent=self):
            return
        del self._messages[index]
        self._refresh_message_list(select=min(index, len(self._messages) - 1) if self._messages else None)
        self._mark_dirty()
        self._changelog.append(self._current_path.name, f"Deleted message {self._id_label(old.speaker)}")

    # -- save -------------------------------------------------------------
    def _save(self) -> None:
        if self._current_path is None:
            return
        # Order doesn't matter to the game (hash lookup); keep vanilla's sorted layout.
        ordered = sorted(self._messages, key=_sort_key)
        try:
            message.write_messages_path(self._current_path, ordered)
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
    """New FE9 message: ID and starting template."""

    def __init__(self, parent, initial_id: str):
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
        self._template = tk.StringVar(value=next(iter(TEMPLATES)))
        ttk.Combobox(body, textvariable=self._template, values=list(TEMPLATES), state="readonly",
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
