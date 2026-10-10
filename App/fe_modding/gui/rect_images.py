"""Game Data browser for rect RIDs, images, and their references."""
from __future__ import annotations

import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, simpledialog, ttk

from PIL import Image, ImageTk

from .. import rect_catalog as catalog
from ..project import ModProject
from .changelog import ChangeLog
from .editor_panel import EditorPanel


class RectImagesPanel(EditorPanel):
    display_name = "Rect Images"

    def __init__(self, parent: tk.Misc, project: ModProject, changelog: ChangeLog, shell=None):
        super().__init__(parent)
        self._project = project
        self._changelog = changelog
        self._shell = shell
        self._editable = False
        self._paths: dict[str, Path] = {}
        self._doc = None
        self._resource = None
        self._visible_rids: list[str] = []
        self._layers: list[tuple[int, object]] = []
        self._preview_photo = None
        self._build()
        self.refresh()

    def _build(self):
        bar = ttk.Frame(self, padding=(12, 10))
        bar.pack(fill="x")
        ttk.Label(bar, text="Rect file").pack(side="left")
        self._file_var = tk.StringVar()
        self._file_box = ttk.Combobox(bar, textvariable=self._file_var, state="readonly", width=48)
        self._file_box.pack(side="left", padx=(8, 8))
        self._file_box.bind("<<ComboboxSelected>>", lambda _event: self._file_changed())
        ttk.Button(bar, text="Refresh", command=self.refresh).pack(side="left")

        split = ttk.PanedWindow(self, orient="horizontal")
        split.pack(fill="both", expand=True)
        left = ttk.Frame(split, padding=(12, 0, 8, 12))
        split.add(left, weight=1)
        ttk.Label(left, text="RIDs in this file").pack(anchor="w")
        self._search = tk.StringVar()
        ttk.Entry(left, textvariable=self._search).pack(fill="x", pady=(5, 5))
        self._search.trace_add("write", lambda *_: self._filter_rids())
        list_frame = ttk.Frame(left)
        list_frame.pack(fill="both", expand=True)
        self._rid_list = tk.Listbox(list_frame, exportselection=False)
        self._rid_list.pack(side="left", fill="both", expand=True)
        scrollbar = ttk.Scrollbar(list_frame, command=self._rid_list.yview)
        scrollbar.pack(side="right", fill="y")
        self._rid_list.configure(yscrollcommand=scrollbar.set)
        self._rid_list.bind("<<ListboxSelect>>", lambda _event: self._select_rid())
        actions = ttk.Frame(left)
        actions.pack(fill="x", pady=(8, 0))
        self._add_button = ttk.Button(actions, text="Add RID…", command=self._add)
        self._add_button.pack(side="left")
        self._rename_button = ttk.Button(actions, text="Rename RID…", command=self._rename)
        self._rename_button.pack(side="left", padx=(8, 0))

        right = ttk.Frame(split, padding=(8, 0, 12, 12))
        split.add(right, weight=2)
        self._rid_heading = ttk.Label(right, text="Select a RID", style="Title.TLabel")
        self._rid_heading.pack(anchor="w")
        ttk.Label(right, text="Images").pack(anchor="w", pady=(10, 3))
        self._image_list = tk.Listbox(right, height=5, exportselection=False)
        self._image_list.pack(fill="x")
        self._image_list.bind("<<ListboxSelect>>", lambda _event: self._select_image())
        self._replace_button = ttk.Button(right, text="Replace selected image…", command=self._replace)
        self._replace_button.pack(anchor="w", pady=(5, 6))
        self._preview = ttk.Label(right, relief="groove", anchor="center")
        self._preview.pack(fill="both", expand=True)
        self._image_status = ttk.Label(right, text="", style="Muted.TLabel", wraplength=700)
        self._image_status.pack(anchor="w", pady=(4, 8))
        self._refs_heading = ttk.Label(right, text="Referenced in")
        self._refs_heading.pack(anchor="w")
        refs_frame = ttk.Frame(right)
        refs_frame.pack(fill="both", expand=True)
        self._refs_list = tk.Listbox(refs_frame, height=8, exportselection=False)
        self._refs_list.pack(side="left", fill="both", expand=True)
        ref_scroll = ttk.Scrollbar(refs_frame, command=self._refs_list.yview)
        ref_scroll.pack(side="right", fill="y")
        self._refs_list.configure(yscrollcommand=ref_scroll.set)
        self._status = ttk.Label(self, text="", style="Muted.TLabel", padding=(12, 3))
        self._status.pack(fill="x")

    def refresh(self, preferred_file: str | None = None, preferred_rid: str | None = None):
        current = preferred_file or self._file_var.get()
        paths = catalog.rect_paths(self._project)
        self._paths = {path.relative_to(self._project.files_dir).as_posix(): path for path in paths}
        names = list(self._paths)
        self._file_box.configure(values=names)
        self._file_var.set(current if current in self._paths else names[0] if names else "")
        self._load_selected_file(preferred_rid)
        if not names:
            self._status.configure(text="No rect files found. Extract the project first.")

    def _file_changed(self):
        self._search.set("")
        self._load_selected_file()

    def _load_selected_file(self, preferred_rid: str | None = None):
        self._doc = None
        self._resource = None
        self._editable = False
        self._set_edit_state()
        self._clear_details()
        path = self._paths.get(self._file_var.get())
        if path is None:
            self._rid_list.delete(0, "end")
            return
        try:
            self._doc = catalog.read_doc(self._project, path)
        except Exception as exc:
            self._status.configure(text=f"Could not read {self._file_var.get()}: {exc}")
            self._rid_list.delete(0, "end")
            return
        try:
            self._editable = not catalog.is_fe10(self._project) or self._doc.build() == path.read_bytes()
        except Exception:
            self._editable = False
        self._set_edit_state()
        note = "" if self._editable else " · This file cannot be rewritten byte-for-byte; editing is disabled."
        self._status.configure(text=f"{len(self._doc.resources)} RIDs in {self._file_var.get()}{note}")
        self._filter_rids(preferred_rid)

    def _set_edit_state(self):
        state = "normal" if self._editable else "disabled"
        for button in (self._add_button, self._rename_button, self._replace_button):
            button.configure(state=state)

    def _can_edit(self):
        if not self._editable:
            return False
        if self._shell is None:
            return True
        unsaved = self._shell.unsaved(flush=True)
        if unsaved:
            messagebox.showinfo(
                "Unsaved changes",
                "Save or revert the other open editors before changing rect resources:\n\n"
                + "\n".join(unsaved),
                parent=self,
            )
            return False
        return True

    def _filter_rids(self, preferred: str | None = None):
        names = [item.name for item in self._doc.resources] if self._doc is not None else []
        query = self._search.get().casefold().strip()
        self._visible_rids = [name for name in names if query in name.casefold()]
        self._rid_list.delete(0, "end")
        for name in self._visible_rids:
            self._rid_list.insert("end", name)
        if preferred in self._visible_rids:
            index = self._visible_rids.index(preferred)
            self._rid_list.selection_set(index)
            self._rid_list.see(index)
            self._select_rid()

    def _clear_details(self):
        self._rid_heading.configure(text="Select a RID")
        self._image_list.delete(0, "end")
        self._refs_list.delete(0, "end")
        self._refs_heading.configure(text="Referenced in")
        self._image_status.configure(text="")
        self._preview.configure(image="", text="")
        self._preview_photo = None
        self._layers = []

    def _select_rid(self):
        selected = self._rid_list.curselection()
        if not selected or self._doc is None:
            return
        rid = self._visible_rids[selected[0]]
        self._resource = self._doc.find(rid)
        self._clear_details()
        self._rid_heading.configure(text=rid)
        self._layers = list(catalog.image_layers(self._resource))
        for index, layer in self._layers:
            self._image_list.insert("end", f"Layer {index}: {layer.file}  ·  texture {layer.texture}")
        if not self._layers:
            self._image_status.configure(text="This RID has no textured layers.")
        else:
            self._image_list.selection_set(0)
            self._select_image()
        try:
            refs = catalog.collect_references(self._project, rid)
        except Exception as exc:
            self._refs_list.insert("end", f"Reference scan failed: {exc}")
            return
        self._refs_heading.configure(text=f"Referenced in ({len(refs)})")
        if not refs:
            self._refs_list.insert("end", "No references found")
        for ref in refs:
            relative = ref.path.relative_to(self._project.files_dir).as_posix()
            self._refs_list.insert("end", f"{ref.kind}: {relative} — {ref.location}")

    def _select_image(self):
        chosen = self._image_list.curselection()
        if not chosen or not self._layers:
            return
        _index, layer = self._layers[chosen[0]]
        try:
            image = catalog.preview_image(self._project, layer)
            image.thumbnail((580, 320), Image.Resampling.LANCZOS)
            backing = Image.new("RGBA", image.size, (110, 110, 110, 255))
            backing.alpha_composite(image.convert("RGBA"))
            self._preview_photo = ImageTk.PhotoImage(backing)
            self._preview.configure(image=self._preview_photo, text="")
            self._image_status.configure(text=f"{layer.file}, texture {layer.texture} — {image.width} × {image.height} preview")
        except Exception as exc:
            self._preview_photo = None
            self._preview.configure(image="", text="Preview unavailable")
            self._image_status.configure(text=f"{layer.file}: {exc}")

    def _selected_path(self):
        return self._paths.get(self._file_var.get())

    def _save(self, changes, note, rid):
        catalog.save_changes(self._project, changes, self._changelog, note)
        self.refresh(self._file_var.get(), rid)

    def _rename(self):
        if not self._can_edit():
            return
        if self._resource is None:
            messagebox.showinfo("Rename RID", "Select a RID first.", parent=self)
            return
        old = self._resource.name
        new = simpledialog.askstring("Rename RID", "New RID:", initialvalue=old, parent=self)
        if not new or new.strip() == old:
            return
        new = new.strip()
        try:
            refs = catalog.collect_references(self._project, old)
            changes = catalog.prepare_rename(self._project, old, new)
            files = "\n".join(sorted(str(path.relative_to(self._project.files_dir)) for path in changes))
            if not messagebox.askyesno("Rename RID",
                f"Rename {old} to {new}?\n\n{len(refs)} references; {len(changes)} files will change:\n{files}",
                parent=self):
                return
            self._save(changes, f"Renamed {old} to {new}", new)
        except Exception as exc:
            messagebox.showerror("Could not rename RID", str(exc), parent=self)

    def _add(self):
        if not self._can_edit():
            return
        path = self._selected_path()
        if path is None:
            messagebox.showinfo("Add RID", "Select a rect file first.", parent=self)
            return
        names = filedialog.askopenfilenames(
            title="Choose images for the new RID",
            filetypes=[("Images", "*.png *.jpg *.jpeg *.bmp *.gif"), ("All files", "*.*")],
            parent=self)
        if not names:
            return
        rid = simpledialog.askstring("Add RID", "New RID:", initialvalue="RID_", parent=self)
        if not rid:
            return
        rid = rid.strip()
        try:
            images = []
            for name in names:
                with Image.open(name) as opened:
                    images.append(opened.convert("RGBA"))
            changes = catalog.prepare_add(self._project, path, rid, images)
            self._save(changes, f"Added {rid}", rid)
        except Exception as exc:
            messagebox.showerror("Could not add RID", str(exc), parent=self)

    def _replace(self):
        if not self._can_edit():
            return
        path = self._selected_path()
        selected = self._image_list.curselection()
        if path is None or self._resource is None or not selected:
            messagebox.showinfo("Replace image", "Select a RID image first.", parent=self)
            return
        index, _layer = self._layers[selected[0]]
        name = filedialog.askopenfilename(
            title="Choose replacement image",
            filetypes=[("Images", "*.png *.jpg *.jpeg *.bmp *.gif"), ("All files", "*.*")],
            parent=self)
        if not name:
            return
        try:
            with Image.open(name) as opened:
                image = opened.convert("RGBA")
            changes = catalog.prepare_replace(self._project, path, self._resource.name, index, image)
            rid = self._resource.name
            self._save(changes, f"Replaced image of {rid}, layer {index}", rid)
        except Exception as exc:
            messagebox.showerror("Could not replace image", str(exc), parent=self)
