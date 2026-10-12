"""Property editor and illustrative preview for Path of Radiance RID resources."""
from __future__ import annotations

import copy
import tkinter as tk
from tkinter import messagebox, ttk

from PIL import ImageTk

from .. import rect_catalog, rect_editor
from ..formats import rect


class RectDetail(tk.Toplevel):
    def __init__(self, parent, project, path, resource, changelog, can_save, on_save):
        super().__init__(parent)
        self.title(f"Edit {resource.name}")
        self.transient(parent.winfo_toplevel())
        self.geometry("1100x760")
        self.minsize(850, 570)
        self._project = project
        self._path = path
        self._original = path.read_bytes()
        self._resource = copy.deepcopy(resource)
        self._initial = copy.deepcopy(resource)
        self._can_save = can_save
        self._changelog = changelog
        self._on_save = on_save
        self._selected = None
        self._inputs = {}
        self._photo = None
        self._build()
        self.protocol("WM_DELETE_WINDOW", self._close)
        self._parts.selection_set(0)
        self._select()

    def _build(self):
        body = ttk.PanedWindow(self, orient="horizontal")
        body.pack(fill="both", expand=True, padx=10, pady=10)
        left = ttk.Frame(body)
        body.add(left, weight=1)
        ttk.Label(left, text=self._resource.name, style="Title.TLabel").pack(anchor="w", pady=(0, 8))
        ttk.Label(left, text="Select the RID settings or a layer").pack(anchor="w")
        self._parts = tk.Listbox(left, exportselection=False, height=14)
        self._parts.pack(fill="both", expand=True, pady=(5, 0))
        self._parts.insert("end", "RID settings")
        for index, layer in enumerate(self._resource.layers):
            self._parts.insert("end", f"Layer {index}: {type(layer).__name__.removesuffix('Layer')}")
        self._parts.bind("<<ListboxSelect>>", self._select)
        self._meaning = ttk.Label(left, wraplength=270, justify="left", style="Muted.TLabel")
        self._meaning.pack(fill="x", pady=(12, 0))

        middle = ttk.Frame(body)
        body.add(middle, weight=2)
        ttk.Label(middle, text="Properties", style="Heading.TLabel").pack(anchor="w")
        self._canvas = tk.Canvas(middle, highlightthickness=0)
        bar = ttk.Scrollbar(middle, orient="vertical", command=self._canvas.yview)
        self._canvas.configure(yscrollcommand=bar.set)
        self._canvas.pack(side="left", fill="both", expand=True)
        bar.pack(side="right", fill="y")
        self._form = ttk.Frame(self._canvas, padding=5)
        self._form_window = self._canvas.create_window((0, 0), window=self._form, anchor="nw")
        self._form.bind("<Configure>", lambda _e: self._canvas.configure(scrollregion=self._canvas.bbox("all")))
        self._canvas.bind("<Configure>", lambda e: self._canvas.itemconfigure(self._form_window, width=e.width))

        right = ttk.Frame(body)
        body.add(right, weight=3)
        ttk.Label(right, text="Illustrative preview (608 × 448)", style="Heading.TLabel").pack(anchor="w")
        self._preview = ttk.Label(right, relief="groove", anchor="center")
        self._preview.pack(fill="both", expand=True, pady=(5, 5))
        self._preview_note = ttk.Label(right, style="Muted.TLabel", wraplength=470, justify="left")
        self._preview_note.pack(fill="x")

        footer = ttk.Frame(self, padding=(10, 0, 10, 10))
        footer.pack(fill="x")
        self._status = ttk.Label(footer, style="Muted.TLabel")
        self._status.pack(side="left", fill="x", expand=True)
        ttk.Button(footer, text="Revert", command=self._revert).pack(side="right", padx=(8, 0))
        ttk.Button(footer, text="Apply", command=self._apply).pack(side="right", padx=(8, 0))
        ttk.Button(footer, text="Refresh preview", command=self._refresh_preview).pack(side="right")

    def _target(self, selection):
        return self._resource if selection == 0 else self._resource.layers[selection - 1]

    def _collect(self):
        if self._selected is None:
            return True
        target = self._target(self._selected)
        values = {name: widget.get("1.0", "end-1c") if isinstance(widget, tk.Text) else widget.get()
                  for name, widget in self._inputs.items()}
        try:
            replacement = rect_editor.update(target, values)
        except ValueError as exc:
            self._status.configure(text=str(exc))
            return False
        if self._selected == 0:
            self._resource = replacement
        else:
            self._resource.layers[self._selected - 1] = replacement
        self._status.configure(text="")
        return True

    def _select(self, _event=None):
        selected = self._parts.curselection()
        if not selected:
            return
        index = selected[0]
        if index == self._selected:
            return
        if not self._collect():
            self._parts.selection_clear(0, "end")
            self._parts.selection_set(self._selected)
            return
        self._selected = index
        for child in self._form.winfo_children():
            child.destroy()
        self._inputs = {}
        target = self._target(index)
        meaning = ("Settings shared by all layers. The game builds each layer using these timing and draw settings."
                   if index == 0 else rect_editor.describe(target))
        if isinstance(target, rect.TextLayer):
            resolved = rect_editor.resolved_text(self._project, target.text)
            if resolved:
                meaning += f"\n\nResolved text: {resolved[:180]}"
        if isinstance(target, rect.TextboxLayer):
            known = self._resources()
            links = [f"{slot}: {getattr(target, slot)} ({'found' if getattr(target, slot) in known else 'missing'})"
                     for slot in ("window", "panel", "marker") if getattr(target, slot)]
            if links:
                meaning += "\n\n" + "\n".join(links)
        self._meaning.configure(text=meaning)
        fields = rect_editor.fields_for(target)
        if not fields:
            ttk.Label(self._form, text="This layer has no decoded editable fields; its bytes are preserved.", wraplength=400).pack(anchor="w")
        for field in fields:
            ttk.Label(self._form, text=field.label).pack(anchor="w", pady=(9, 2))
            value = rect_editor.display(target, field)
            if field.kind == "seats":
                widget = tk.Text(self._form, height=max(4, min(12, len(target.seats) + 1)), wrap="none")
                widget.insert("1.0", value)
            else:
                widget = ttk.Entry(self._form)
                widget.insert(0, value)
            widget.pack(fill="x")
            self._inputs[field.name] = widget
        self._refresh_preview(collect=False)

    def _resources(self):
        result = {}
        for path in rect_catalog.rect_paths(self._project):
            try:
                result.update({item.name: item for item in rect_catalog.read_doc(self._project, path).resources})
            except Exception:
                continue
        result[self._resource.name] = self._resource
        return result

    def _refresh_preview(self, *, collect=True):
        if collect and not self._collect():
            return
        try:
            image, notes = rect_editor.render(self._project, self._resource, self._resources())
            image.thumbnail((485, 450))
            self._photo = ImageTk.PhotoImage(image)
            self._preview.configure(image=self._photo, text="")
            self._preview_note.configure(text="; ".join(notes) if notes else "Text and portrait samples illustrate layout; runtime effects may differ.")
        except Exception as exc:
            self._photo = None
            self._preview.configure(image="", text="Preview unavailable")
            self._preview_note.configure(text=str(exc))

    def _apply(self):
        if not self._collect() or not self._can_save():
            return
        try:
            changes = rect_editor.prepare_edit(self._project, self._path, self._resource.name, self._resource, self._original)
            if changes:
                rect_catalog.save_changes(self._project, changes, self._changelog, f"Edited {self._resource.name}")
                self._original = self._path.read_bytes()
                self._initial = copy.deepcopy(self._resource)
                self._on_save(self._resource.name)
                self._status.configure(text="Saved")
            else:
                self._status.configure(text="No changes to save")
        except Exception as exc:
            messagebox.showerror("Could not edit RID", str(exc), parent=self)

    def _revert(self):
        self._resource = copy.deepcopy(self._initial)
        selected = self._selected
        self._selected = None
        self._parts.selection_clear(0, "end")
        self._parts.selection_set(selected if selected is not None else 0)
        self._select()

    def _close(self):
        if self._collect() and self._resource != self._initial:
            if not messagebox.askyesno("Discard RID edits", "Discard unsaved RID changes?", parent=self):
                return
        elif not self._collect():
            if not messagebox.askyesno("Discard RID edits", "Discard invalid unsaved values?", parent=self):
                return
        self.destroy()
