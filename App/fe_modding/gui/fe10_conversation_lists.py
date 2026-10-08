"""Conversation lists (Radiant Dawn): the tables of ``FE10Conversation.cms``.

Three tabs: the base Info conversations (which chapter, which event name the chapter script
registers, the title and message they show, the characters pictured, the seen flag), the Path of
Radiance supports the Extras Conversation Room replays, and each character's support chat lines.
Edits go through ``formats/fe10_conversation_data.py``; Save writes the file back LZ10-compressed
through the project (the extracted file is kept in ``originals/``)."""
from __future__ import annotations

import tkinter as tk
from tkinter import messagebox, simpledialog, ttk

from ..exceptions import ProjectError
from ..formats import fe10_conversation_data as cd
from ..formats import fe10_message, message
from ..game_profile import profile_of
from ..project import ModProject
from .changelog import ChangeLog
from .editor_panel import EditorPanel

FILE_LABEL = "FE10Conversation.cms"


class Fe10ConversationLists(EditorPanel):
    display_name = "Conversation lists"

    def __init__(self, parent, project: ModProject, changelog: ChangeLog):
        super().__init__(parent)
        self._project = project
        self._changelog = changelog
        self._data = b""
        self._lists: cd.ConversationData | None = None
        self._dirty = False
        self._names: dict[str, str] | None = None
        self._form_vars: dict[str, tk.StringVar] = {}
        self._shown = None   # (tab, index)
        self._build()
        self._load()

    # -- data ---------------------------------------------------------------------------------
    def _load(self) -> None:
        if not profile_of(self._project).has_file("conversation_data"):
            self._status.configure(text=f"{profile_of(self._project).display_name} has no conversation lists file.")
            return
        try:
            self._data = self._project.read_logical("conversation_data")
            self._lists = cd.read_conversation_data(self._data)
        except (ProjectError, ValueError, KeyError, IndexError) as exc:
            self._lists = None
            self._status.configure(text=str(exc))
            return
        self._refresh()

    def _text(self, key: str | None) -> str:
        """English text of a common.m key (titles, character names), '' when unknown."""
        if not key:
            return ""
        if self._names is None:
            self._names = {}
            folder = self._project.extracted_dir / "files" / "Mess"
            for name in ("common.m", "e_common.m"):
                path = folder / name
                if path.is_file():
                    for msg in message.read_messages_path(path):
                        try:
                            self._names[msg.speaker.encode("cp437").decode("cp932")] = fe10_message.plain_text(msg.text)
                        except UnicodeError:
                            continue
        return self._names.get(key, "")

    def _person(self, pid: str | None) -> str:
        if not pid:
            return ""
        name = self._text("M" + pid) if pid.startswith("PID_") else self._text(pid)
        return name or pid

    def _replace(self, data: bytes, what: str) -> None:
        self._data = data
        self._lists = cd.read_conversation_data(data)
        self._dirty = True
        self._save_button.configure(state="normal")
        self._status.configure(text=f"{what} (unsaved)")
        self._changelog.append(FILE_LABEL, what)
        self._refresh(keep=True)

    def save(self) -> None:
        if not self._dirty:
            return
        try:
            self._project.write_logical("conversation_data", self._data)
        except OSError as exc:
            messagebox.showerror(f"Could not save {FILE_LABEL}", str(exc), parent=self)
            return
        self._dirty = False
        self._save_button.configure(state="disabled")
        self._status.configure(text=f"Saved {FILE_LABEL}.")
        self._changelog.append(FILE_LABEL, "Saved the conversation lists")

    def _revert(self) -> None:
        if self._dirty and not self._confirm_discard():
            return
        self._dirty = False
        self._save_button.configure(state="disabled")
        self._load()
        self._status.configure(text="Changes discarded.")

    def _confirm_discard(self) -> bool:
        return messagebox.askyesno("Unsaved changes", "Discard the unsaved conversation list changes?", parent=self)

    # -- layout -------------------------------------------------------------------------------
    def _build(self) -> None:
        top = ttk.Frame(self, padding=(8, 8, 8, 4))
        top.pack(fill="x")
        ttk.Label(top, text="Conversation lists", style="Title.TLabel").pack(side="left")
        self._save_button = ttk.Button(top, text="Save", command=self.save, state="disabled", style="Accent.TButton")
        self._save_button.pack(side="right")
        ttk.Button(top, text="Discard changes", command=self._revert).pack(side="right", padx=(0, 6))
        self._status = ttk.Label(top, style="Muted.TLabel")
        self._status.pack(side="right", padx=8)
        ttk.Label(self, padding=(8, 0), style="Muted.TLabel", wraplength=1100, justify="left", text=(
            "FE10Conversation.cms. Base conversations appear in a chapter's base when its script registers a base "
            "event of the same name; the Extras Conversation Room lists them all. The message ID is played from the "
            "chapter's Mess file and the title key comes from common.m.")).pack(anchor="w")
        self._notebook = ttk.Notebook(self)
        self._notebook.pack(fill="both", expand=True, padx=8, pady=8)
        self._trees: dict[str, ttk.Treeview] = {}
        self._forms: dict[str, ttk.Frame] = {}
        specs = {
            "info": ("Base conversations", (("chapter", "Chapter", 70), ("name", "Event name", 150),
                                            ("title", "Title", 170), ("people", "Characters", 360),
                                            ("number", "No.", 40))),
            "fe8": ("Conversation Room supports", (("a", "Character 1", 130), ("b", "Character 2", 130),
                                                   ("messages", "Conversations", 420))),
            "mini": ("Support chat lines", (("pid", "Character", 160), ("file", "Mess file", 170),
                                            ("count", "Partners", 70))),
        }
        for key, (title, columns) in specs.items():
            tab = ttk.Frame(self._notebook, padding=4)
            self._notebook.add(tab, text=title)
            paned = ttk.PanedWindow(tab, orient="horizontal")
            paned.pack(fill="both", expand=True)
            left = ttk.Frame(paned)
            paned.add(left, weight=3)
            if key == "info":
                bar = ttk.Frame(left)
                bar.pack(fill="x", pady=(0, 4))
                ttk.Button(bar, text="Add (copy of selected)…", command=self._add_info).pack(side="left")
                ttk.Button(bar, text="Remove", command=self._remove_info).pack(side="left", padx=4)
            tree = ttk.Treeview(left, columns=[c[0] for c in columns], show="headings", selectmode="browse")
            for column, heading, width in columns:
                tree.heading(column, text=heading)
                tree.column(column, width=width, stretch=column in ("people", "messages", "title"))
            scroll = ttk.Scrollbar(left, orient="vertical", command=tree.yview)
            tree.configure(yscrollcommand=scroll.set)
            tree.pack(side="left", fill="both", expand=True)
            scroll.pack(side="left", fill="y")
            tree.bind("<<TreeviewSelect>>", lambda e, k=key: self._on_select(k))
            self._trees[key] = tree
            form = ttk.Frame(paned, padding=8)
            paned.add(form, weight=2)
            self._forms[key] = form

    def _refresh(self, keep: bool = False) -> None:
        if self._lists is None:
            return
        for key, tree in self._trees.items():
            selection = tree.selection()
            tree.delete(*tree.get_children())
            if key == "info":
                for r in self._lists.info:
                    tree.insert("", "end", iid=str(r.index), values=(
                        r.values["chapter"] or "", r.name, self._text(r.values["title"]) or r.values["title"] or "",
                        ", ".join(self._person(p) for p in r.pids), r.values["number"]))
            elif key == "fe8":
                for r in self._lists.fe8_yells:
                    v = r.values
                    tree.insert("", "end", iid=str(r.index), values=(
                        self._text(v["mpid_a"]) or v["mpid_a"], self._text(v["mpid_b"]) or v["mpid_b"],
                        ", ".join(filter(None, (v["message_1"], v["message_2"], v["message_3"])))))
            else:
                for r in self._lists.mini_yells:
                    tree.insert("", "end", iid=str(r.index), values=(self._person(r.pid), r.file or "",
                                                                     len(r.partners)))
            if keep and selection and tree.exists(selection[0]):
                tree.selection_set(selection)
                tree.see(selection[0])
        if keep and self._shown is not None:
            self._build_form(*self._shown)
        else:
            self._status.configure(text=f"{len(self._lists.info)} base conversations, {len(self._lists.fe8_yells)} "
                                        f"Conversation Room supports, {len(self._lists.mini_yells)} characters with "
                                        "support chat lines")

    # -- forms --------------------------------------------------------------------------------
    def _on_select(self, key: str) -> None:
        selection = self._trees[key].selection()
        if selection:
            self._build_form(key, int(selection[0]))

    def _clear(self, key: str) -> ttk.Frame:
        form = self._forms[key]
        for child in form.winfo_children():
            child.destroy()
        return form

    def _field(self, form, label: str, value, commit) -> None:
        row = ttk.Frame(form)
        row.pack(fill="x", pady=2)
        ttk.Label(row, text=label, width=22).pack(side="left")
        var = tk.StringVar(value="" if value is None else str(value))
        entry = ttk.Entry(row, textvariable=var)
        entry.pack(side="left", fill="x", expand=True)
        original = var.get()

        def apply(_event=None):
            if var.get() != original:
                try:
                    commit(var.get().strip())
                except (ValueError, IndexError, KeyError, UnicodeError) as exc:
                    messagebox.showerror("Not applied", str(exc), parent=self)
                    var.set(original)
        entry.bind("<Return>", apply)
        entry.bind("<FocusOut>", apply)

    def _build_form(self, key: str, index: int) -> None:
        self._shown = (key, index)
        form = self._clear(key)
        if self._lists is None:
            return
        if key == "info":
            r = self._lists.info[index]
            ttk.Label(form, text=f"Base conversation {index}", style="Heading.TLabel").pack(anchor="w")
            ttk.Label(form, text=r.symbol or "(no symbol: never listed in a base)", style="Muted.TLabel").pack(anchor="w")
            self._field(form, "Event name", r.name,
                        lambda v: self._replace(cd.rename_info(self._data, index, v), f"Renamed base conversation {index}"))
            for field_key in cd.INFO_FIELDS:
                self._field(form, cd.INFO_LABELS[field_key], r.values[field_key],
                            lambda v, k=field_key: self._replace(cd.patch_info(self._data, index, k, v),
                                                                 f"Base conversation {index}: {cd.INFO_LABELS[k]}"))
            title = self._text(r.values["title"])
            if title:
                ttk.Label(form, text=f"Title shown: {title}", style="Muted.TLabel").pack(anchor="w", pady=(6, 0))
        elif key == "fe8":
            r = self._lists.fe8_yells[index]
            ttk.Label(form, text=f"Conversation Room support {index}", style="Heading.TLabel").pack(anchor="w")
            for field_key in cd.FE8_YELL_FIELDS:
                self._field(form, cd.FE8_YELL_LABELS[field_key], r.values[field_key],
                            lambda v, k=field_key: self._replace(cd.patch_fe8_yell(self._data, index, k, v),
                                                                 f"Support {index}: {cd.FE8_YELL_LABELS[k]}"))
            ttk.Label(form, text="Text: Mess/e_yell_fe8.m", style="Muted.TLabel").pack(anchor="w", pady=(6, 0))
        else:
            r = self._lists.mini_yells[index]
            ttk.Label(form, text=self._person(r.pid), style="Heading.TLabel").pack(anchor="w")
            self._field(form, "Mess file", r.file,
                        lambda v: self._replace(cd.patch_mini_yell_file(self._data, index, v),
                                                f"Support chat file of {r.pid}"))
            ttk.Label(form, text="The game adds the language prefix (e_ for English) to the file name.",
                      style="Muted.TLabel").pack(anchor="w")
            partners = ttk.Treeview(form, columns=("partner", "said", "answered"), show="headings", height=14,
                                    selectmode="browse")
            for column, heading in (("partner", "Partner"), ("said", "Line said"), ("answered", "Line answered")):
                partners.heading(column, text=heading)
                partners.column(column, width=150)
            partners.pack(fill="both", expand=True, pady=(6, 4))
            for j, (pid, said, answered) in enumerate(r.partners):
                partners.insert("", "end", iid=str(j), values=(self._person(pid), said or "", answered or ""))
            editor = ttk.Frame(form)
            editor.pack(fill="x")

            def edit(_event=None):
                for child in editor.winfo_children():
                    child.destroy()
                chosen = partners.selection()
                if not chosen:
                    return
                j = int(chosen[0])
                for column, label in enumerate(("Partner PID", "Line said", "Line answered")):
                    self._field(editor, label, r.partners[j][column],
                                lambda v, c=column, jj=j: self._replace(
                                    cd.patch_mini_yell(self._data, index, jj, c, v),
                                    f"Support chat {r.pid}: entry {jj}"))
            partners.bind("<<TreeviewSelect>>", edit)

    # -- base conversation records ------------------------------------------------------------
    def _selected_info(self) -> int | None:
        selection = self._trees["info"].selection()
        return int(selection[0]) if selection else None

    def _add_info(self) -> None:
        index = self._selected_info()
        if index is None or self._lists is None:
            messagebox.showinfo("Add base conversation", "Select the conversation to copy first.", parent=self)
            return
        name = simpledialog.askstring("Add base conversation",
                                      "Event name (the name the chapter script registers):", parent=self)
        if not name:
            return
        try:
            data, new = cd.add_info(self._data, index, name.strip())
        except ValueError as exc:
            messagebox.showerror("Add base conversation", str(exc), parent=self)
            return
        self._replace(data, f"Added base conversation {name.strip()}")
        self._trees["info"].selection_set(str(new))
        self._trees["info"].see(str(new))

    def _remove_info(self) -> None:
        index = self._selected_info()
        if index is None:
            return
        record = self._lists.info[index]
        if not messagebox.askyesno("Remove base conversation", f"Remove {record.symbol or index}?", parent=self):
            return
        try:
            data = cd.remove_info(self._data, index)
        except ValueError as exc:
            messagebox.showerror("Remove base conversation", str(exc), parent=self)
            return
        self._shown = None
        self._clear("info")
        self._replace(data, f"Removed base conversation {record.symbol or index}")
