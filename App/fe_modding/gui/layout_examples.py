"""Read-only examples of every FE9 dialogue layout."""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from PIL import Image, ImageTk

from ..formats.fe9_conversation import Event, Portrait, Scene, Textbox
from ..formats.fe9_conversation_render import ConversationRenderer
from ..formats.fe9_message_scene import layout_from_label
from .scene_editor import background_names, layout_labels


class LayoutExamples(tk.Toplevel):
    def __init__(self, parent, assets, selected_layout="", background=""):
        super().__init__(parent)
        self.title("Dialogue layout examples")
        self.transient(parent.winfo_toplevel())
        self.minsize(760, 510)
        self._assets = assets
        self._renderer = ConversationRenderer(assets)
        self._photo = None
        self._labels = layout_labels(assets)
        names = background_names(assets)
        self._background = tk.StringVar(value=background if background in names and background != "支援背景"
                                        else next((name for name in names if
                                                   name != "支援背景"), ""))
        self._faces = self._sample_faces()

        outer = ttk.Frame(self, padding=12)
        outer.pack(fill="both", expand=True)
        ttk.Label(outer, text="Select a layout to see all its seats and textboxes.").pack(
            anchor="w", pady=(0, 8))
        row = ttk.Frame(outer)
        row.pack(fill="both", expand=True)
        left = ttk.Frame(row)
        left.pack(side="left", fill="y", padx=(0, 12))
        ttk.Label(left, text="Layouts").pack(anchor="w")
        self._list = tk.Listbox(left, width=27, height=23, exportselection=False)
        self._list.pack(fill="y", expand=True)
        for label in self._labels:
            self._list.insert("end", label)
        self._list.bind("<<ListboxSelect>>", self._render)
        right = ttk.Frame(row)
        right.pack(side="left", fill="both", expand=True)
        controls = ttk.Frame(right)
        controls.pack(fill="x", pady=(0, 6))
        ttk.Label(controls, text="Background").pack(side="left", padx=(0, 6))
        bg_box = ttk.Combobox(controls, textvariable=self._background,
                              values=[name for name in names if name != "支援背景"],
                              state="readonly", width=24)
        bg_box.pack(side="left")
        bg_box.bind("<<ComboboxSelected>>", self._render)
        self._image = ttk.Label(right)
        self._image.pack(fill="both", expand=True)
        self._status = ttk.Label(right, wraplength=600)
        self._status.pack(anchor="w", pady=(6, 0))
        if self._labels:
            index = self._labels.index(selected_layout) if selected_layout in self._labels else 0
            self._list.selection_set(index)
            self._list.see(index)
            self._render()

    def _sample_faces(self):
        faces = []
        for fid in sorted(self._assets.faces):
            if not fid.startswith("FID_"):
                continue
            try:
                self._assets.face(fid)
            except (OSError, ValueError, KeyError):
                continue
            faces.append(fid)
            if len(faces) == 9:
                break
        return faces

    def _render(self, _event=None):
        selection = self._list.curselection()
        if not selection:
            return
        label = self._labels[selection[0]]
        layout = layout_from_label(label)
        try:
            count = min(9, len(self._assets.seats(layout)))
            portraits = tuple(Portrait(fid=self._faces[i % len(self._faces)])
                              if self._faces and i < count else Portrait()
                              for i in range(9))
            definitions = [part for part in self._assets.layout(layout).parts
                           if part.kind == 2]
            boxes = tuple(Textbox(text=f"Textbox {i + 1}", visible=i < len(definitions))
                          for i in range(4))
            scene = Scene(layout=layout, background=self._background.get(),
                          portraits=portraits, boxes=boxes, speaker_seat=-1,
                          nametag=False)
            event = Event(index=0, time_ms=0, source_offset=0, kind="text", state=scene)
            result = self._renderer.render(event)
            image = result.image.resize((608, 448), Image.Resampling.LANCZOS)
            self._photo = ImageTk.PhotoImage(image)
            self._image.configure(image=self._photo)
            note = (f"{count} seat{'s' if count != 1 else ''}; "
                    f"{min(4, len(definitions))} textbox{'es' if len(definitions) != 1 else ''}.")
            if result.diagnostics:
                note += "  " + "; ".join(d.description for d in result.diagnostics)
            self._status.configure(text=note)
        except (OSError, ValueError, KeyError, IndexError) as error:
            self._image.configure(image="")
            self._photo = None
            self._status.configure(text=f"Unable to render {label}: {error}")
