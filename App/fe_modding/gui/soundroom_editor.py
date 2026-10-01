"""Sound Room editor: ``soundroom.bin`` (see :mod:`fe_modding.formats.soundroom`).

The Sound Room shows one picture at a time behind its track menu and steps
through this list as a slideshow (A on a track, or A/Left/Right with the menu
hidden). Each picture is an ``s/rect.bin`` resource (the same ``RID_`` names
an event's ``RectBuild`` uses; new ones are made on the Backgrounds page)
placed at an X/Y screen offset. The preview draws the picture's first layer
on the 608x448 screen; drag it to move it.
"""

from __future__ import annotations

import io
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk
from typing import Optional

from PIL import Image, ImageDraw, ImageTk

from ..formats import rect, soundroom, tpl
from ..formats.soundroom import SCREEN_SIZE, SoundRoomEntry
from ..project import ModProject
from . import theme
from .changelog import ChangeLog
from .editor_panel import EditorPanel

FILE_NAME = "soundroom.bin"
PREVIEW_SIZE = (560, 420)
#: Brightness kept for the part of the picture that is off screen.
OFFSCREEN_DIM = 0.35


class SoundRoomEditor(EditorPanel):
    display_name = "Sound Room"

    def __init__(self, parent: tk.Misc, project: ModProject, changelog: ChangeLog):
        super().__init__(parent)
        self._project = project
        self._changelog = changelog
        self._files = project.extracted_dir / "files"
        self._path = self._files / FILE_NAME
        self._entries: list[SoundRoomEntry] = []
        self._rects: Optional[rect.RectFile] = None
        self._pictures: dict[str, Optional[Image.Image]] = {}
        self._index: Optional[int] = None
        self._dirty = False
        self._loading = False
        self._photo: Optional[ImageTk.PhotoImage] = None
        self._view = (0, 0, 1.0)  # canvas origin in screen pixels, and scale
        self._drag: Optional[tuple[int, int, int, int]] = None
        self._build_widgets()
        self._load()

    # -- layout ---------------------------------------------------------------------------
    def _build_widgets(self) -> None:
        bar = ttk.Frame(self, padding=(8, 8, 8, 4))
        bar.pack(fill="x")
        self._save_button = ttk.Button(bar, text="Save Sound Room", style="Accent.TButton", command=self.save,
                                       state="disabled")
        self._save_button.pack(side="left")
        ttk.Button(bar, text="Revert", command=self._revert).pack(side="left", padx=(6, 0))
        self._status = ttk.Label(bar, text="", style="Muted.TLabel")
        self._status.pack(side="left", padx=(10, 0))
        ttk.Label(self, style="Muted.TLabel", wraplength=1000, justify="left", padding=(8, 2), text=(
            "The pictures behind the Sound Room's track menu, shown as a slideshow: playing a track (A) shows "
            "the next one; with the menu hidden (X), A/Right shows the next and Left the previous. Each picture "
            "is an s/rect.bin resource (add new ones on the Backgrounds page) placed at an X/Y screen offset. "
            "The track list is fixed in the game code and does not come from this file.")).pack(fill="x")

        body = ttk.Frame(self, padding=8)
        body.pack(fill="both", expand=True)

        left = ttk.Frame(body)
        left.pack(side="left", fill="y", padx=(0, 12))
        ttk.Label(left, text="Pictures, in slideshow order", style="Heading.TLabel").pack(anchor="w")
        columns = ("n", "name", "x", "y")
        self._tree = ttk.Treeview(left, columns=columns, show="headings", selectmode="browse", height=20)
        for column, text, width in zip(columns, ("#", "Resource", "X", "Y"), (34, 230, 50, 50)):
            self._tree.heading(column, text=text)
            self._tree.column(column, width=width, anchor="w" if column == "name" else "e", stretch=False)
        self._tree.pack(fill="y", expand=True, pady=(4, 0))
        self._tree.bind("<<TreeviewSelect>>", lambda e: self._on_select())
        buttons = ttk.Frame(left)
        buttons.pack(fill="x", pady=(6, 0))
        for text, command in (("▲", lambda: self._move(-1)), ("▼", lambda: self._move(1)),
                              ("Add", self._add), ("Duplicate", self._duplicate), ("Remove", self._remove)):
            ttk.Button(buttons, text=text, width=3 if len(text) == 1 else None, command=command).pack(
                side="left", padx=(0, 4))

        right = ttk.Frame(body)
        right.pack(side="left", fill="both", expand=True)
        form = ttk.Frame(right)
        form.pack(fill="x")
        ttk.Label(form, text="Resource").grid(row=0, column=0, sticky="w")
        self._name_var = tk.StringVar()
        self._name_box = ttk.Combobox(form, textvariable=self._name_var, width=40)
        self._name_box.grid(row=0, column=1, columnspan=5, sticky="w", padx=(6, 0))
        self._name_box.bind("<<ComboboxSelected>>", lambda e: self._apply_form())
        self._name_box.bind("<Return>", lambda e: self._apply_form())
        self._name_box.bind("<FocusOut>", lambda e: self._apply_form())
        self._x_var, self._y_var = tk.StringVar(), tk.StringVar()
        for column, (label, var) in enumerate((("X", self._x_var), ("Y", self._y_var))):
            ttk.Label(form, text=label).grid(row=1, column=column * 2, sticky="w", pady=(6, 0),
                                             padx=(0 if column == 0 else 12, 0))
            box = ttk.Spinbox(form, textvariable=var, from_=-2000, to=2000, increment=2, width=7,
                              command=self._apply_form)
            box.grid(row=1, column=column * 2 + 1, sticky="w", padx=(6, 0), pady=(6, 0))
            box.bind("<Return>", lambda e: self._apply_form())
            box.bind("<FocusOut>", lambda e: self._apply_form())
        place = ttk.Frame(form)
        place.grid(row=1, column=4, columnspan=2, sticky="w", padx=(16, 0), pady=(6, 0))
        for text, where in (("Top-left", "origin"), ("Centre", "centre")):
            ttk.Button(place, text=text, command=lambda w=where: self._place(w)).pack(side="left", padx=(0, 4))
        self._info = ttk.Label(right, text="", style="Muted.TLabel")
        self._info.pack(anchor="w", pady=(6, 4))
        self._canvas = tk.Canvas(right, width=PREVIEW_SIZE[0], height=PREVIEW_SIZE[1], highlightthickness=0,
                                 background=theme.color("surface_alt"), cursor="fleur")
        self._canvas.pack(anchor="w")
        self._canvas.bind("<ButtonPress-1>", self._drag_start)
        self._canvas.bind("<B1-Motion>", self._drag_move)
        self._canvas.bind("<ButtonRelease-1>", lambda e: setattr(self, "_drag", None))
        ttk.Label(right, style="Muted.TLabel", text=(
            "The outlined box is the 608x448 screen; the dimmed part of the picture is off screen. "
            "Drag the picture to move it.")).pack(anchor="w", pady=(4, 0))

    # -- data -----------------------------------------------------------------------------
    def _load(self) -> None:
        self._loading = True
        try:
            self._rects = None
            rect_path = self._files / "s" / "rect.bin"
            try:
                if rect_path.exists():
                    self._rects = rect.read_rect_file(rect_path)
            except Exception:  # noqa: BLE001 - the picture names and previews are optional
                self._rects = None
            self._name_box.config(values=sorted(r.name for r in self._rects.resources) if self._rects else [])
            self._pictures.clear()
            if not self._path.exists():
                self._entries = []
                self._status.config(text=f"{FILE_NAME} not found (Path of Radiance only; extract the project first).")
            else:
                try:
                    self._entries = soundroom.read_soundroom_path(self._path)
                    self._status.config(text=f"{len(self._entries)} pictures")
                except Exception as exc:  # noqa: BLE001
                    self._entries = []
                    self._status.config(text=f"Could not read {FILE_NAME}: {exc}")
            self._set_dirty(False)
            self._fill_tree(0 if self._entries else None)
        finally:
            self._loading = False

    def _fill_tree(self, select: Optional[int]) -> None:
        self._tree.delete(*self._tree.get_children())
        for i, entry in enumerate(self._entries):
            self._tree.insert("", "end", iid=str(i), values=self._row(i, entry))
        self._index = None
        if select is not None and self._entries:
            select = max(0, min(select, len(self._entries) - 1))
            self._tree.selection_set(str(select))
            self._tree.see(str(select))
            self._on_select()
        else:
            self._show_entry()

    def _row(self, i: int, entry: SoundRoomEntry) -> tuple:
        missing = self._rects is not None and self._rects.find(entry.name) is None
        return i, entry.name + ("   (missing)" if missing else ""), entry.x, entry.y

    def _refresh_row(self) -> None:
        if self._index is not None:
            self._tree.item(str(self._index), values=self._row(self._index, self._entries[self._index]))

    def _set_dirty(self, dirty: bool) -> None:
        self._dirty = dirty
        self._save_button.config(state="normal" if dirty else "disabled")
        if dirty:
            self._status.config(text="Unsaved changes")

    def _changed(self) -> None:
        self._refresh_row()
        self._set_dirty(True)
        self._draw()

    # -- selection and form ---------------------------------------------------------------
    def _on_select(self) -> None:
        selection = self._tree.selection()
        self._index = int(selection[0]) if selection else None
        self._show_entry()

    def _current(self) -> Optional[SoundRoomEntry]:
        return self._entries[self._index] if self._index is not None else None

    def _show_entry(self) -> None:
        entry = self._current()
        self._loading = True
        try:
            self._name_var.set(entry.name if entry else "")
            self._x_var.set(str(entry.x) if entry else "")
            self._y_var.set(str(entry.y) if entry else "")
        finally:
            self._loading = False
        self._draw()

    def _apply_form(self) -> None:
        entry = self._current()
        if entry is None or self._loading:
            return
        name = self._name_var.get().strip()
        try:
            x, y = int(self._x_var.get()), int(self._y_var.get())
            if not (-0x8000 <= x < 0x8000 and -0x8000 <= y < 0x8000):
                raise ValueError
            name.encode(soundroom.ENCODING)
        except (ValueError, UnicodeEncodeError):
            messagebox.showerror("Invalid value", "X and Y must be whole numbers from -32768 to 32767, and the "
                                 "name must be Shift-JIS text.", parent=self)
            self._show_entry()
            return
        if not name:
            self._show_entry()
            return
        if (name, x, y) != (entry.name, entry.x, entry.y):
            entry.name, entry.x, entry.y = name, x, y
            self._changed()

    def _place(self, where: str) -> None:
        entry = self._current()
        if entry is None:
            return
        picture = self._picture(entry.name)
        width, height = picture.size if picture else SCREEN_SIZE
        if where == "origin":
            entry.x, entry.y = 0, 0
        else:
            entry.x, entry.y = (SCREEN_SIZE[0] - width) // 2, (SCREEN_SIZE[1] - height) // 2
        self._show_entry()
        self._changed()

    # -- list edits -----------------------------------------------------------------------
    def _move(self, step: int) -> None:
        i = self._index
        if i is None or not 0 <= i + step < len(self._entries):
            return
        self._entries[i], self._entries[i + step] = self._entries[i + step], self._entries[i]
        self._set_dirty(True)
        self._fill_tree(i + step)

    def _add(self) -> None:
        name = self._name_box.cget("values")[0] if self._name_box.cget("values") else "RID_"
        position = len(self._entries) if self._index is None else self._index + 1
        self._entries.insert(position, SoundRoomEntry(name))
        self._set_dirty(True)
        self._fill_tree(position)
        self._name_box.focus_set()

    def _duplicate(self) -> None:
        entry = self._current()
        if entry is None:
            return
        self._entries.insert(self._index + 1, SoundRoomEntry(entry.name, entry.x, entry.y))
        self._set_dirty(True)
        self._fill_tree(self._index + 1)

    def _remove(self) -> None:
        if self._index is None:
            return
        if len(self._entries) == 1:
            messagebox.showinfo("Remove picture", "The Sound Room needs at least one picture.", parent=self)
            return
        index = self._index
        del self._entries[index]
        self._set_dirty(True)
        self._fill_tree(index)

    # -- preview --------------------------------------------------------------------------
    def _picture(self, name: str) -> Optional[Image.Image]:
        """The resource's first layer, as the engine sizes the rect."""
        if name in self._pictures:
            return self._pictures[name]
        picture = None
        resource = self._rects.find(name) if self._rects is not None else None
        quads = resource.quads() if resource is not None else []
        if quads:
            layer = quads[0]
            try:
                images = tpl.read_tpl_images(io.BytesIO((self._files / layer.file).read_bytes()))
                texture = images[layer.texture].convert("RGBA")
                x0, y0, x1, y1 = layer.src
                picture = texture.crop((min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1)))
                if x1 < x0:
                    picture = picture.transpose(Image.Transpose.FLIP_LEFT_RIGHT)
                if y1 < y0:
                    picture = picture.transpose(Image.Transpose.FLIP_TOP_BOTTOM)
            except Exception:  # noqa: BLE001 - a missing/undecodable texture just has no preview
                picture = None
        self._pictures[name] = picture
        return picture

    def _draw(self) -> None:
        self._canvas.delete("all")
        entry = self._current()
        screen_w, screen_h = SCREEN_SIZE
        if entry is None:
            self._info.config(text="")
            return
        picture = self._picture(entry.name)
        if picture is None:
            self._info.config(text=f"{entry.name}: no such s/rect.bin resource, or its texture could not be read.")
            width, height = SCREEN_SIZE
        else:
            width, height = picture.size
            self._info.config(text=f"{entry.name}: {width}x{height}, shown at {entry.x}, {entry.y}")
        left, top = min(0, entry.x), min(0, entry.y)
        right, bottom = max(screen_w, entry.x + width), max(screen_h, entry.y + height)
        scale = min(PREVIEW_SIZE[0] / (right - left), PREVIEW_SIZE[1] / (bottom - top))
        self._view = (left, top, scale)

        frame = Image.new("RGBA", (right - left, bottom - top), (0, 0, 0, 0))
        at = (entry.x - left, entry.y - top)
        screen_box = (-left, -top, screen_w - left, screen_h - top)
        if picture is not None:
            dimmed = picture.point(lambda v: int(v * OFFSCREEN_DIM))
            dimmed.putalpha(picture.getchannel("A"))
            frame.alpha_composite(dimmed, at)
        on_screen = Image.new("RGBA", frame.size, (0, 0, 0, 255))
        if picture is not None:
            on_screen.alpha_composite(picture, at)
        frame.paste(on_screen.crop(screen_box), screen_box[:2])
        size = (max(1, round(frame.width * scale)), max(1, round(frame.height * scale)))
        frame = frame.resize(size, Image.Resampling.BILINEAR)
        ImageDraw.Draw(frame).rectangle(
            (round(-left * scale), round(-top * scale), round((screen_w - left) * scale) - 1,
             round((screen_h - top) * scale) - 1), outline=(255, 214, 102, 255), width=2)
        self._photo = ImageTk.PhotoImage(frame)
        self._canvas.create_image(0, 0, image=self._photo, anchor="nw")

    def _drag_start(self, event) -> None:
        entry = self._current()
        if entry is not None:
            self._drag = (event.x, event.y, entry.x, entry.y)

    def _drag_move(self, event) -> None:
        entry = self._current()
        if entry is None or self._drag is None:
            return
        start_x, start_y, x, y = self._drag
        scale = self._view[2]
        new = (x + round((event.x - start_x) / scale), y + round((event.y - start_y) / scale))
        new = tuple(max(-0x8000, min(0x7FFF, v)) for v in new)
        if new != (entry.x, entry.y):
            entry.x, entry.y = new
            self._x_var.set(str(entry.x))
            self._y_var.set(str(entry.y))
            self._changed()

    # -- save -----------------------------------------------------------------------------
    def save(self) -> bool:
        if not self._entries:
            return False
        try:
            soundroom.write_soundroom(self._entries, self._path)
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror(f"Could not save {FILE_NAME}", str(exc), parent=self)
            return False
        self._changelog.append(FILE_NAME, f"Saved {len(self._entries)} Sound Room pictures")
        self._set_dirty(False)
        self._status.config(text=f"Saved {FILE_NAME}")
        return True

    def _revert(self) -> None:
        if self._dirty and not self._confirm_discard():
            return
        self._load()

    def _confirm_discard(self) -> bool:
        return messagebox.askyesno("Discard changes?", "The Sound Room has unsaved changes. Discard them?",
                                   parent=self)
