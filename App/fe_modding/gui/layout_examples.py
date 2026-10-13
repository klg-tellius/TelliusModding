"""Read-only examples of every FE9 dialogue layout."""
from __future__ import annotations

import hashlib
import tkinter as tk
from tkinter import ttk

from PIL import Image, ImageTk

from ..formats.fe9_conversation import Event, Portrait, Scene, Textbox
from ..formats.fe9_conversation_render import ConversationRenderer
from ..formats.fe9_message_scene import layout_from_label
from .scene_editor import background_names, layout_labels
from .widgets import tip

#: Scene width in pixels; a seat placed beyond it (some layouts park seats at x 1080-1528) is never seen.
SCENE_WIDTH = 608
SEAT_MARGIN = 64


def distinct_sample_faces(assets, limit=9):
    """Choose visually distinct faces instead of distinct IDs/aliases."""
    faces = []
    fingerprints = set()
    for fid in sorted(assets.faces):
        if not fid.startswith("FID_"):
            continue
        try:
            image = assets.face(fid).compose(mouth_frame=2, left_eye_frame=0,
                                             right_eye_frame=0).convert("RGBA")
        except (OSError, ValueError, KeyError, IndexError):
            continue
        fingerprint = (image.size, hashlib.sha256(image.tobytes()).digest())
        if fingerprint in fingerprints:
            continue
        fingerprints.add(fingerprint)
        faces.append(fid)
        if len(faces) == limit:
            break
    return faces


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
        self._faces = distinct_sample_faces(self._assets)
        self._seat_enabled = [tk.BooleanVar(value=True) for _ in range(9)]

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
        seats = ttk.Frame(right)
        seats.pack(fill="x", pady=(0, 6))
        tip(ttk.Label(seats, text="Show seats:"),
            "Seats 0-3 each have their text box: hiding the seat hides its box too. A greyed seat is "
            "off-screen in this layout (no portrait there is ever seen).").pack(side="left", padx=(0, 4))
        self._seat_checks = []
        for i, enabled in enumerate(self._seat_enabled):
            check = ttk.Checkbutton(seats, text=str(i), variable=enabled,
                                    command=self._render)
            check.pack(side="left", padx=(0, 3))
            self._seat_checks.append(check)
        self._image = ttk.Label(right)
        self._image.pack(fill="both", expand=True)
        self._status = ttk.Label(right, wraplength=600)
        self._status.pack(anchor="w", pady=(6, 0))
        if self._labels:
            index = self._labels.index(selected_layout) if selected_layout in self._labels else 0
            self._list.selection_set(index)
            self._list.see(index)
            self._render()

    def _render(self, _event=None):
        selection = self._list.curselection()
        if not selection:
            return
        label = self._labels[selection[0]]
        layout = layout_from_label(label)
        try:
            seats = self._assets.seats(layout)
            count = min(9, len(seats))
            visible = [i < count and -SEAT_MARGIN <= seats[i][0] <= SCENE_WIDTH + SEAT_MARGIN for i in range(9)]
            for i, check in enumerate(self._seat_checks):
                check.state(("!disabled",) if visible[i] else ("disabled",))
            portraits = tuple(Portrait(fid=self._faces[i % len(self._faces)])
                              if self._faces and visible[i] and self._seat_enabled[i].get()
                              else Portrait()
                              for i in range(9))
            definitions = [part for part in self._assets.layout(layout).parts
                           if part.kind == 2]
            # box i belongs to seat i (the speaker seat lights both): a hidden seat hides its box
            boxes = tuple(Textbox(text=f"Textbox {i + 1}",
                                  visible=i < len(definitions) and (i >= count or self._seat_enabled[i].get()))
                          for i in range(4))
            scene = Scene(layout=layout, background=self._background.get(),
                          portraits=portraits, boxes=boxes, speaker_seat=-1,
                          nametag=False)
            event = Event(index=0, time_ms=0, source_offset=0, kind="text", state=scene)
            result = self._renderer.render(event)
            image = result.image.resize((608, 448), Image.Resampling.LANCZOS)
            self._photo = ImageTk.PhotoImage(image)
            self._image.configure(image=self._photo)
            on_screen = sum(visible)
            shown = sum(enabled.get() for enabled, seen in zip(self._seat_enabled, visible) if seen)
            note = (f"{on_screen} seat{'s' if on_screen != 1 else ''} on screen ({shown} shown)"
                    + (f", {count - on_screen} off-screen" if count > on_screen else "") + "; "
                    f"{min(4, len(definitions))} textbox{'es' if len(definitions) != 1 else ''}.")
            if result.diagnostics:
                note += "  " + "; ".join(d.description for d in result.diagnostics)
            self._status.configure(text=note)
        except (OSError, ValueError, KeyError, IndexError) as error:
            self._image.configure(image="")
            self._photo = None
            self._status.configure(text=f"Unable to render {label}: {error}")
