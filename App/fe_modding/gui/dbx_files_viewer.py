"""Browse and edit every text DBX entry inside Path of Radiance's zdbx.cmp."""

from __future__ import annotations

import tkinter as tk
from tkinter import messagebox, simpledialog, ttk

from .. import battle_tables
from ..exceptions import ProjectError
from ..project import ModProject
from .changelog import ChangeLog
from .editor_panel import EditorPanel


class DbxFilesViewer(EditorPanel):
    display_name = "DBX Files"

    def __init__(self, parent: tk.Misc, project: ModProject, changelog: ChangeLog):
        super().__init__(parent)
        self._project = project
        self._changelog = changelog
        self._inventory: dict[str, str] = {}
        self._path: str | None = None
        self._saved_text = ""
        self._line_ending = "\r\n"
        self._new = False
        self._loading = False
        self._dirty = False

        top = ttk.Frame(self, padding=8)
        top.pack(fill="x")
        ttk.Label(top, text="Search").pack(side="left")
        self._query = tk.StringVar()
        ttk.Entry(top, textvariable=self._query).pack(side="left", fill="x", expand=True, padx=8)
        self._query.trace_add("write", lambda *_: self._fill_list())
        ttk.Button(top, text="Refresh", command=self.refresh_from_archive).pack(side="left")

        body = ttk.PanedWindow(self, orient="horizontal")
        body.pack(fill="both", expand=True, padx=8)
        left = ttk.Frame(body)
        right = ttk.Frame(body)
        body.add(left, weight=2)
        body.add(right, weight=4)
        self._tree = ttk.Treeview(left, columns=("path", "state"), show="headings", selectmode="browse")
        self._tree.heading("path", text="Archive path")
        self._tree.heading("state", text="State")
        self._tree.column("path", width=280, stretch=True)
        self._tree.column("state", width=75, stretch=False)
        scrollbar = ttk.Scrollbar(left, command=self._tree.yview)
        self._tree.configure(yscrollcommand=scrollbar.set)
        self._tree.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        self._tree.bind("<<TreeviewSelect>>", self._select)

        self._title = ttk.Label(right, text="Select a DBX file", font=("Segoe UI", 12, "bold"))
        self._title.pack(anchor="w", pady=(0, 5))
        self._editor = tk.Text(right, wrap="none", undo=True, font=("Consolas", 10))
        self._editor.pack(fill="both", expand=True)
        self._editor.bind("<<Modified>>", self._text_modified)
        actions = ttk.Frame(right)
        actions.pack(anchor="w", pady=8)
        self._save_btn = ttk.Button(actions, text="Save", command=self.save, state="disabled")
        self._save_btn.pack(side="left")
        ttk.Button(actions, text="Add DBX...", command=self._add).pack(side="left", padx=(6, 0))
        self._delete_btn = ttk.Button(actions, text="Delete", command=self._delete, state="disabled")
        self._delete_btn.pack(side="left", padx=(6, 0))
        self._restore_btn = ttk.Button(actions, text="Restore original", command=self._restore, state="disabled")
        self._restore_btn.pack(side="left", padx=(6, 0))
        self._status = ttk.Label(self, text="", style="Muted.TLabel", padding=8)
        self._status.pack(anchor="w")
        self.refresh_from_archive()

    def _text_modified(self, _event=None) -> None:
        if self._editor.edit_modified():
            self._editor.edit_modified(False)
            if not self._loading:
                self._dirty = self._editor.get("1.0", "end-1c") != self._saved_text
                self._save_btn.configure(state="normal" if self._path and self._dirty else "disabled")

    def _confirm_discard(self) -> bool:
        if not self._dirty:
            return True
        answer = messagebox.askyesnocancel("Unsaved DBX text", "Save changes before leaving this file?", parent=self)
        if answer is None:
            return False
        if answer:
            return self.save()
        self._dirty = False
        return True

    def _fill_list(self) -> None:
        query = self._query.get().strip().casefold()
        selected = self._path
        self._loading = True
        self._tree.delete(*self._tree.get_children())
        for path, state in sorted(self._inventory.items()):
            if query and query not in path.casefold():
                continue
            self._tree.insert("", "end", iid=path, values=(path, state))
        if selected and self._tree.exists(selected):
            self._tree.selection_set(selected)
        self._loading = False

    def refresh_from_archive(self) -> bool:
        if not self._confirm_discard():
            return False
        try:
            self._inventory = battle_tables.inventory(self._project)
        except (ProjectError, OSError, ValueError) as exc:
            self._status.configure(text=f"Could not read zdbx.cmp: {exc}")
            return False
        path = self._path if self._path in self._inventory else None
        self._fill_list()
        self._open(path)
        self._status.configure(text=f"{len(self._inventory)} DBX files (including deleted originals).")
        return True

    def _select(self, _event=None) -> None:
        if self._loading:
            return
        selected = self._tree.selection()
        path = selected[0] if selected else None
        if path == self._path:
            return
        if not self._confirm_discard():
            self._loading = True
            self._tree.selection_remove(*selected)
            if self._path and self._tree.exists(self._path):
                self._tree.selection_set(self._path)
            self._loading = False
            return
        self._open(path)

    def _open(self, path: str | None, *, new: bool = False) -> None:
        try:
            state = self._inventory.get(path) if path else None
            text = battle_tables.read_entry(self._project, path) if path and state != "deleted" and not new else ""
        except (ProjectError, OSError, UnicodeError) as exc:
            messagebox.showerror(self.display_name, str(exc), parent=self)
            return
        self._loading = True
        self._path = path
        self._new = new
        self._line_ending = "\r\n" if "\r\n" in text else "\n"
        display_text = text.replace("\r\n", "\n").replace("\r", "\n")
        self._saved_text = display_text
        self._dirty = False
        self._title.configure(text=(path or "Select a DBX file") + (" (new)" if new else ""))
        self._editor.configure(state="normal")
        self._editor.delete("1.0", "end")
        self._editor.insert("1.0", display_text)
        self._editor.edit_reset()
        self._editor.edit_modified(False)
        self._editor.configure(state="disabled" if not path or state == "deleted" else "normal")
        self._save_btn.configure(state="disabled")
        self._delete_btn.configure(state="normal" if path and state != "deleted" and not new else "disabled")
        self._restore_btn.configure(state="normal" if state in ("edited", "deleted", "added") and not new else "disabled")
        self._loading = False

    def _after_change(self, message: str, path: str | None) -> None:
        self._changelog.append(self.display_name, message)
        self._path = path
        self._dirty = False
        self.refresh_from_archive()
        self._status.configure(text=message + ".")

    def save(self) -> bool:
        if not self._path:
            return False
        text = self._editor.get("1.0", "end-1c")
        encoded_text = text.replace("\n", self._line_ending)
        try:
            if self._new:
                battle_tables.add_entry(self._project, self._path, encoded_text)
                verb = "Added"
            elif text != self._saved_text:
                battle_tables.write_entry(self._project, self._path, encoded_text)
                verb = "Edited"
            else:
                self._dirty = False
                return True
        except (ProjectError, OSError, ValueError) as exc:
            messagebox.showerror(self.display_name, str(exc), parent=self)
            return False
        self._after_change(f"{verb} {self._path}", self._path)
        return True

    def _add(self) -> None:
        if not self._confirm_discard():
            return
        name = simpledialog.askstring("Add DBX", "Archive path (for example xcam/new_script.dbx):", parent=self)
        if name is None:
            return
        try:
            path = battle_tables.validate_entry_name(name.strip())
            if any(n.casefold() == path.casefold() for n in self._inventory):
                raise ProjectError(f"zdbx.cmp already has {path}; select it to restore or edit it.")
        except ProjectError as exc:
            messagebox.showerror(self.display_name, str(exc), parent=self)
            return
        self._tree.selection_remove(*self._tree.selection())
        self._open(path, new=True)
        self._status.configure(text="Enter DBX text, then Save to add the file.")

    def _delete(self) -> None:
        path = self._path
        if not path or self._new or not self._confirm_discard():
            return
        if not messagebox.askyesno("Delete DBX", f"Delete {path} from zdbx.cmp?\n\nOriginal entries can be restored here.", parent=self):
            return
        try:
            battle_tables.remove_entry(self._project, path)
        except (ProjectError, OSError) as exc:
            messagebox.showerror(self.display_name, str(exc), parent=self)
            return
        self._after_change(f"Deleted {path}", path)

    def _restore(self) -> None:
        path = self._path
        if not path or not self._confirm_discard():
            return
        try:
            battle_tables.restore_entry(self._project, path)
        except (ProjectError, OSError) as exc:
            messagebox.showerror(self.display_name, str(exc), parent=self)
            return
        self._after_change(f"Restored {path}", path)
