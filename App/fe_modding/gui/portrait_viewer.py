"""Portraits page: every dialogue portrait (``Face/*.cms``), its pictures and
its face record (``Face/facedata.bin``), plus new portraits for new
characters.

A texture set is a C8 TPL: the 192x128 body (texture 0), the mouth frames
(two sets of three), the eye frames (three per eye) and, on small portraits,
a 64x64 menu face with its own palette. The body has transparent holes where
the eyes and mouth are drawn. Replacing a picture either makes a new palette
for the set from all its pictures (default: the new picture keeps its
colours) or matches the picture to the current palette (``tpl.replace_image``).

The face record says where the parts go, which texture is the menu face,
the depth order and the nameplate key; it is saved straight to the loose
``Face/facedata.bin`` (the build copies it into ``system.cmp``). **New
portrait...** writes ``FID_<NAME>`` and ``FID_L_<NAME>`` (the game pairs a
small face with the large one of the same name) and can set a character's
FID. See ``fe_modding/portraits.py``.

Radiant Dawn keeps one 15-image ``.cms`` plus one 48-byte face row per slot,
with separate normal and widescreen copies. New slots clone the selected
row and texture set in both aspect folders, preserving their distinct part
coordinates; subsequent picture replacement customizes the clone.
"""

from __future__ import annotations

import io
import tkinter as tk
from dataclasses import replace
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from PIL import Image, ImageTk

from .. import portraits
from ..formats import fe10_faces, fe10data, fe8data, lz10, tpl
from ..formats.fe9_portraits import FaceAsset, FaceRecord
from ..games import Game
from ..project import ModProject
from .changelog import ChangeLog
from .editor_panel import EditorPanel

PREVIEW_MAX_SIZE = (300, 300)
THUMB_SIZE = (56, 56)
IMAGE_TYPES = [("Images", "*.png *.jpg *.jpeg *.bmp *.gif"), ("All files", "*.*")]


def _on_grey(image: Image.Image, size=None) -> Image.Image:
    image = image.convert("RGBA")
    if size:
        image = image.copy()
        image.thumbnail(size)
    backing = Image.new("RGBA", image.size, (128, 128, 128, 255))
    backing.alpha_composite(image)
    return backing


class PortraitViewer(EditorPanel):
    display_name = "Portraits"
    uses_fe8_session = True

    def __init__(self, parent: tk.Misc, project: ModProject, changelog: ChangeLog, session=None):
        super().__init__(parent)
        self._project = project
        self._rd = project.game is Game.RADIANT_DAWN
        self._changelog = changelog
        self._session = session
        self._current_path: Path | None = None
        self._current_bytes: bytes | None = None  # decompressed TPL bytes
        self._infos: list[tpl.TplImageInfo] = []
        self._decoded_images: list[Image.Image] = []
        self._selected_index: int | None = None
        self._dirty = False
        self._wide_bytes: bytes | None = None
        self._wide_dirty = False
        self._faces: list[FaceRecord] = []
        self._record: FaceRecord | None = None
        self._thumb_photos: list[ImageTk.PhotoImage] = []
        self._preview_photo = self._composed_photo = None
        self._record_vars: dict[str, tk.Variable] = {}

        self._build_widgets()
        self._load_portrait_list()

    # -- layout -------------------------------------------------------------
    def _build_widgets(self) -> None:
        paned = ttk.PanedWindow(self, orient="horizontal")
        paned.pack(fill="both", expand=True)

        left = ttk.Frame(paned, padding=8)
        paned.add(left, weight=1)
        ttk.Label(left, text="Portraits").pack(anchor="w")
        search_var = tk.StringVar()
        ttk.Entry(left, textvariable=search_var).pack(fill="x", pady=(4, 4))
        search_var.trace_add("write", lambda *_: self._apply_filter(search_var.get()))
        list_frame = ttk.Frame(left)
        list_frame.pack(fill="both", expand=True)
        self._file_list = tk.Listbox(list_frame, exportselection=False)
        self._file_list.pack(fill="both", expand=True, side="left")
        scrollbar = ttk.Scrollbar(list_frame, command=self._file_list.yview)
        scrollbar.pack(fill="y", side="right")
        self._file_list.config(yscrollcommand=scrollbar.set)
        self._file_list.bind("<<ListboxSelect>>", lambda e: self._on_file_selected())
        buttons = ttk.Frame(left)
        buttons.pack(fill="x", pady=(6, 0))
        self._new_button = ttk.Button(buttons, text="New portrait…", command=self._new_portrait)
        self._new_button.pack(side="left")
        self._remove_button = ttk.Button(buttons, text="Remove", command=self._remove_portrait, state="disabled")
        self._remove_button.pack(side="left", padx=(6, 0))

        right = ttk.Frame(paned, padding=8)
        paned.add(right, weight=3)
        ttk.Label(right, text="Pictures (body, mouth frames, eye frames, menu face)").pack(anchor="w")
        self._thumb_frame = ttk.Frame(right)
        self._thumb_frame.pack(fill="x", pady=(4, 8))

        previews = ttk.Frame(right)
        previews.pack(fill="x")
        picture = ttk.Frame(previews)
        picture.pack(side="left", anchor="n", padx=(0, 16))
        self._preview_label = ttk.Label(picture, relief="groove")
        self._preview_label.pack()
        self._info_label = ttk.Label(picture, text="", style="Muted.TLabel")
        self._info_label.pack(anchor="w")
        composed = ttk.Frame(previews)
        composed.pack(side="left", anchor="n")
        self._composed_label = ttk.Label(composed, relief="groove")
        self._composed_label.pack()
        ttk.Label(composed, text="As the game assembles it", style="Muted.TLabel").pack(anchor="w")

        button_row = ttk.Frame(right)
        button_row.pack(fill="x", pady=(8, 0))
        self._import_button = ttk.Button(button_row, text="Replace picture…", command=self._import_image,
                                         state="disabled")
        self._import_button.pack(side="left")
        self._new_palette = tk.BooleanVar(value=True)
        ttk.Checkbutton(button_row, text="New palette (keeps the picture's colours)",
                        variable=self._new_palette).pack(side="left", padx=(8, 0))
        self._wide_var = tk.BooleanVar(value=True)
        if self._rd:
            ttk.Checkbutton(button_row, text="Also update Face/wide", variable=self._wide_var).pack(
                side="left", padx=(8, 0))
        self._save_button = ttk.Button(button_row, text="Save pictures", command=self._save, state="disabled")
        self._save_button.pack(side="left", padx=(8, 0))
        self._status_label = ttk.Label(button_row, text="", style="Muted.TLabel")
        self._status_label.pack(side="left", padx=(8, 0))

        self._record_frame = ttk.LabelFrame(right, text="Face record (Face/facedata.bin)", padding=8)
        self._record_frame.pack(fill="x", pady=(12, 0))
        self._build_record_form(self._record_frame)

    def _build_record_form(self, frame: ttk.Frame) -> None:
        if self._rd:
            self._build_rd_record_form(frame)
            return
        v = self._record_vars
        row = 0
        ttk.Label(frame, text="Face ID").grid(row=row, column=0, sticky="w")
        v["fid"] = tk.StringVar()
        self._fid_box = ttk.Combobox(frame, textvariable=v["fid"], state="readonly", width=24)
        self._fid_box.grid(row=row, column=1, columnspan=3, sticky="w")
        self._fid_box.bind("<<ComboboxSelected>>", lambda e: self._show_record(v["fid"].get()))
        row += 1
        ttk.Label(frame, text="Name key (nameplate)").grid(row=row, column=0, sticky="w")
        v["name_id"] = tk.StringVar()
        ttk.Entry(frame, textvariable=v["name_id"], width=26).grid(row=row, column=1, columnspan=3, sticky="w")
        for label, key in (("Left eye x, y", "left_eye"), ("Right eye x, y", "right_eye"), ("Mouth x, y", "mouth")):
            row += 1
            ttk.Label(frame, text=label).grid(row=row, column=0, sticky="w")
            for i in range(2):
                v[f"{key}{i}"] = tk.IntVar()
                ttk.Spinbox(frame, from_=-1, to=512, width=6, textvariable=v[f"{key}{i}"]).grid(
                    row=row, column=1 + i, sticky="w", padx=(0, 4))
        row += 1
        v["eyes"], v["mouth_part"] = tk.BooleanVar(), tk.BooleanVar()
        ttk.Checkbutton(frame, text="Has eyes", variable=v["eyes"]).grid(row=row, column=1, columnspan=2, sticky="w")
        ttk.Checkbutton(frame, text="Has mouth", variable=v["mouth_part"]).grid(row=row, column=3, sticky="w")
        for label, key, low, high, tip_text in (
                ("Menu face texture", "mini_portrait", 0, 65535, "65535: none (large portraits)"),
                ("Automatic mouth set", "default_mouth", 0, 255, "0 or 1"),
                ("Depth", "depth", 0, 255, "higher is drawn behind the others"),
                ("Lowered in menus (px)", "menu_offset", -128, 127, "tall characters, so the face stays visible")):
            row += 1
            ttk.Label(frame, text=label).grid(row=row, column=0, sticky="w")
            v[key] = tk.IntVar()
            ttk.Spinbox(frame, from_=low, to=high, width=7, textvariable=v[key]).grid(row=row, column=1, sticky="w")
            ttk.Label(frame, text=tip_text, style="Muted.TLabel").grid(row=row, column=2, columnspan=3, sticky="w")
        row += 1
        bar = ttk.Frame(frame)
        bar.grid(row=row, column=0, columnspan=5, sticky="w", pady=(8, 0))
        self._apply_record_button = ttk.Button(bar, text="Preview", command=self._preview_record, state="disabled")
        self._apply_record_button.pack(side="left")
        self._save_record_button = ttk.Button(bar, text="Save face record", command=self._save_record,
                                              state="disabled")
        self._save_record_button.pack(side="left", padx=(6, 0))

    def _build_rd_record_form(self, frame: ttk.Frame) -> None:
        """Known FE10 face metadata; unknown halfwords remain preserved and read-only."""
        self._fid_box = ttk.Combobox(frame, state="readonly", width=24)
        self._fid_box.grid(row=0, column=1, sticky="w")
        self._fid_box.bind("<<ComboboxSelected>>", lambda _e: self._show_record(self._fid_box.get()))
        ttk.Label(frame, text="Face ID").grid(row=0, column=0, sticky="w", padx=(0, 10))
        ttk.Label(frame, text="Large face ID").grid(row=1, column=0, sticky="w", padx=(0, 10), pady=2)
        self._record_vars["large_fid"] = tk.StringVar()
        ttk.Label(frame, textvariable=self._record_vars["large_fid"]).grid(row=1, column=1, sticky="w")
        ttk.Label(frame, text="Name key").grid(row=2, column=0, sticky="w", padx=(0, 10), pady=2)
        self._record_vars["name_id"] = tk.StringVar()
        ttk.Entry(frame, textvariable=self._record_vars["name_id"], width=26).grid(row=2, column=1, columnspan=2,
                                                                                   sticky="w")
        for row, (label, key) in enumerate((("Eye A", "eye_a"), ("Eye B", "eye_b"),
                                             ("Mouth", "mouth"), ("Cut-in origin", "cut_in_origin")), start=3):
            ttk.Label(frame, text=label).grid(row=row, column=0, sticky="w", padx=(0, 10), pady=2)
            for axis in range(2):
                var = self._record_vars[f"{key}{axis}"] = tk.IntVar()
                ttk.Spinbox(frame, from_=-1, to=512, width=7, textvariable=var).grid(
                    row=row, column=1 + axis, sticky="w", padx=(0, 4))
        ttk.Label(frame, text="Unknown fields").grid(row=7, column=0, sticky="w", padx=(0, 10), pady=2)
        self._record_vars["extra"] = tk.StringVar()
        ttk.Label(frame, textvariable=self._record_vars["extra"], style="Muted.TLabel").grid(
            row=7, column=1, columnspan=3, sticky="w")
        bar = ttk.Frame(frame)
        bar.grid(row=8, column=0, columnspan=4, sticky="w", pady=(8, 0))
        self._apply_record_button = ttk.Button(bar, text="Preview", command=self._preview_record,
                                               state="disabled")
        self._apply_record_button.pack(side="left")
        self._save_record_button = ttk.Button(bar, text="Save face record", command=self._save_record,
                                              state="disabled")
        self._save_record_button.pack(side="left", padx=(6, 0))

    # -- data loading ---------------------------------------------------------
    def _load_faces(self) -> None:
        try:
            if self._rd:
                path = portraits.face_dir(self._project) / "facedata.bin"
                self._faces = fe10_faces.read_face_data(path.read_bytes())
            else:
                self._faces = portraits.load_faces(self._project)
        except (OSError, ValueError):
            self._faces = []

    def _load_portrait_list(self) -> None:
        self._load_faces()
        face_dir = portraits.face_dir(self._project)
        self._all_files = sorted(p for p in face_dir.glob("*.cms") if p.is_file()) if face_dir.exists() else []
        self._apply_filter("")
        if not self._all_files:
            ttk.Label(self._file_list.master, text="No portrait files found.\nExtract the project first.",
                      style="Muted.TLabel").pack(pady=8)

    def _records_of(self, path: Path) -> list[FaceRecord]:
        return [r for r in self._faces if r.filename.casefold() == path.name.casefold()]

    def _apply_filter(self, query: str) -> None:
        query = query.strip().lower()
        self._filtered_files = [p for p in self._all_files
                                if query in p.stem.lower()
                                or any(query in r.fid.lower() for r in self._records_of(p))]
        self._file_list.delete(0, "end")
        for path in self._filtered_files:
            ids = ", ".join(r.fid for r in self._records_of(path))
            self._file_list.insert("end", f"{path.stem}   {ids}" if ids else f"{path.stem}   (no face record)")

    def _on_file_selected(self) -> None:
        selection = self._file_list.curselection()
        if not selection:
            return
        if self._dirty and not self._confirm_discard():
            self._file_list.selection_clear(0, "end")
            if self._current_path in self._filtered_files:
                self._file_list.selection_set(self._filtered_files.index(self._current_path))
            return
        self._open(self._filtered_files[selection[0]])

    def _open(self, path: Path) -> None:
        self._current_path = path
        try:
            self._current_bytes = lz10.decompress(path.read_bytes())
            self._infos = tpl.read_tpl_image_info(io.BytesIO(self._current_bytes))
            wide_path = portraits.face_dir(self._project) / "wide" / path.name
            self._wide_bytes = lz10.decompress(wide_path.read_bytes()) if self._rd and wide_path.is_file() else None
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror("Could not read portrait", str(exc), parent=self)
            return
        self._dirty = False
        self._wide_dirty = False
        self._save_button.config(state="disabled")
        self._status_label.config(text="")
        self._refresh_thumbnails()
        if self._infos:
            self._select_image(0)
        records = self._records_of(path)
        self._fid_box.configure(values=[r.fid for r in records])
        self._show_record(records[0].fid if records else None)
        added = bool(records) and all(r.fid not in self._retail_ids() for r in records)
        self._remove_button.config(state="normal" if added else "disabled")

    def _retail_ids(self) -> set[str]:
        if self._rd:
            path = portraits.face_dir(self._project) / "facedata.bin"
            original = self._project.extracted_bytes(path)
            try:
                return {record.fid for record in fe10_faces.read_face_data(original)} if original else set()
            except ValueError:
                return set()
        from ..formats.fe9_portraits import read_face_table
        data = self._project.extracted_bytes(portraits.face_table_path(self._project))
        try:
            return set(read_face_table(data)) if data else set()
        except ValueError:
            return set()

    def _refresh_thumbnails(self) -> None:
        for child in self._thumb_frame.winfo_children():
            child.destroy()
        self._thumb_photos.clear()
        try:
            self._decoded_images = tpl.read_tpl_images(io.BytesIO(self._current_bytes))
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror("Could not decode portrait", str(exc), parent=self)
            self._decoded_images = []
            return
        row_frame = None
        for i, image in enumerate(self._decoded_images):
            if i % 10 == 0:
                row_frame = ttk.Frame(self._thumb_frame)
                row_frame.pack(anchor="w")
            photo = ImageTk.PhotoImage(_on_grey(image, THUMB_SIZE))
            self._thumb_photos.append(photo)
            ttk.Button(row_frame, image=photo, command=lambda i=i: self._select_image(i)).pack(
                side="left", padx=(0, 4), pady=(0, 4))

    def _select_image(self, index: int) -> None:
        self._selected_index = index
        self._preview_photo = ImageTk.PhotoImage(_on_grey(self._decoded_images[index], PREVIEW_MAX_SIZE))
        self._preview_label.config(image=self._preview_photo)
        info = self._infos[index]
        importable = info.format in tpl.ENCODABLE_FORMATS
        note = tpl.format_name(info.format) if importable else f"{tpl.format_name(info.format)} (view only)"
        self._info_label.config(text=f"Picture {index}: {info.width} x {info.height}, {note}")
        self._import_button.config(state="normal" if importable else "disabled")

    # -- face record ------------------------------------------------------------
    def _show_record(self, fid: str | None) -> None:
        self._record = next((r for r in self._faces if r.fid == fid), None)
        v, r = self._record_vars, self._record
        if self._rd:
            state = "normal" if r else "disabled"
            self._apply_record_button.config(state=state)
            self._save_record_button.config(state=state)
            if r is None:
                self._fid_box.set("")
                for var in v.values():
                    var.set("")
                self._composed_label.config(image="")
                return
            self._fid_box.set(r.fid)
            v["large_fid"].set(r.large_fid)
            v["name_id"].set(r.name_id)
            for key in ("eye_a", "eye_b", "mouth", "cut_in_origin"):
                for axis in range(2):
                    v[f"{key}{axis}"].set(getattr(r, key)[axis])
            v["extra"].set(", ".join(map(str, r.extra)))
            self._draw_composed(r)
            return
        state = "normal" if r else "disabled"
        self._apply_record_button.config(state=state)
        self._save_record_button.config(state=state)
        if r is None:
            v["fid"].set("")
            self._composed_label.config(image="")
            return
        v["fid"].set(r.fid)
        v["name_id"].set(r.name_id)
        for key in ("left_eye", "right_eye", "mouth"):
            for i in range(2):
                v[f"{key}{i}"].set(getattr(r, key)[i])
        v["eyes"].set(bool(r.flags & 1))
        v["mouth_part"].set(bool(r.flags & 2))
        for key in ("mini_portrait", "default_mouth", "depth", "menu_offset"):
            v[key].set(getattr(r, key))
        self._draw_composed(r)

    def _record_from_form(self) -> FaceRecord:
        v, r = self._record_vars, self._record
        if self._rd:
            if r is None:
                raise ValueError("Select a face record first.")
            name_id = v["name_id"].get().strip()
            if not name_id.startswith("MPID_"):
                raise ValueError("The name key is an MPID_ label.")
            points = {key: tuple(v[f"{key}{axis}"].get() for axis in range(2))
                      for key in ("eye_a", "eye_b", "mouth", "cut_in_origin")}
            return replace(r, name_id=name_id, **points)
        name_id = v["name_id"].get().strip()
        if not name_id.startswith("MPID_"):
            raise ValueError("The name key is an MPID_ label.")
        flags = (r.flags & ~3) | (1 if v["eyes"].get() else 0) | (2 if v["mouth_part"].get() else 0)
        return portraits.with_fields(
            r, name_id=name_id, flags=flags,
            left_eye=(v["left_eye0"].get(), v["left_eye1"].get()),
            right_eye=(v["right_eye0"].get(), v["right_eye1"].get()),
            mouth=(v["mouth0"].get(), v["mouth1"].get()),
            mini_portrait=v["mini_portrait"].get(), default_mouth=v["default_mouth"].get(),
            depth=v["depth"].get(), menu_offset=v["menu_offset"].get())

    def _draw_composed(self, record: FaceRecord) -> None:
        try:
            image = (fe10_faces.compose_face(record, self._decoded_images)
                     if self._rd else FaceAsset(record, tuple(self._decoded_images)).compose())
        except (ValueError, tk.TclError) as exc:
            self._composed_label.config(image="", text=f"Cannot assemble: {exc}")
            return
        self._composed_photo = ImageTk.PhotoImage(_on_grey(image, PREVIEW_MAX_SIZE))
        self._composed_label.config(image=self._composed_photo, text="")

    def _preview_record(self) -> None:
        try:
            self._draw_composed(self._record_from_form())
        except (ValueError, tk.TclError) as exc:
            messagebox.showerror("Face record", str(exc), parent=self)

    def _save_record(self) -> None:
        try:
            record = self._record_from_form()
            if self._rd:
                face_dir = portraits.face_dir(self._project)
                path = face_dir / "facedata.bin"
                data = path.read_bytes()
                index = next(i for i, item in enumerate(fe10_faces.read_face_data(data)) if item.fid == record.fid)
                data = fe10_faces.patch_face_record(data, index, record)
                wide_path = face_dir / "wide" / "facedata.bin"
                wide_data = wide_path.read_bytes()
                wide_records = fe10_faces.read_face_data(wide_data)
                wide_index = next(i for i, item in enumerate(wide_records) if item.fid == record.fid)
                wide_record = replace(wide_records[wide_index], large_fid=record.large_fid,
                                      name_id=record.name_id, filename=record.filename)
                wide_data = fe10_faces.patch_face_record(wide_data, wide_index, wide_record)
                self._project.write_keeping_original(path, data)
                self._project.write_keeping_original(wide_path, wide_data)
            else:
                portraits.update_face(self._project, record)
        except (ValueError, tk.TclError, OSError, KeyError, StopIteration) as exc:
            messagebox.showerror("Could not save the face record", str(exc), parent=self)
            return
        self._load_faces()
        self._record = record
        self._draw_composed(record)
        self._changelog.append(record.fid, "Saved face record (Face/facedata.bin)")
        self._status_label.config(text=f"Saved {record.fid}")
        self._portraits_changed()

    # -- import / save --------------------------------------------------------
    def _import_image(self) -> None:
        if self._selected_index is None or self._current_bytes is None:
            return
        info = self._infos[self._selected_index]
        chosen = filedialog.askopenfilename(
            title=f"Choose a picture ({info.width}x{info.height}; it is stretched to fit)",
            filetypes=IMAGE_TYPES, parent=self)
        if not chosen:
            return
        try:
            new_image = Image.open(chosen)
            def replace(data: bytes) -> bytes:
                infos = tpl.read_tpl_image_info(io.BytesIO(data))
                if self._new_palette.get() and all(i.format == tpl.FORMAT_C8 for i in infos):
                    return portraits.rebuild_with_new_palette(data, {self._selected_index: new_image})
                return tpl.replace_image(data, self._selected_index, new_image)

            new_current = replace(self._current_bytes)
            new_wide = self._wide_bytes
            if self._rd and self._wide_var.get() and self._wide_bytes is not None:
                wide_infos = tpl.read_tpl_image_info(io.BytesIO(self._wide_bytes))
                if self._selected_index >= len(wide_infos):
                    raise ValueError("The Face/wide portrait does not have the matching picture slot.")
                new_wide = replace(self._wide_bytes)
            self._current_bytes = new_current
            self._wide_bytes = new_wide
            if self._rd and self._wide_var.get() and self._wide_bytes is not None:
                self._wide_dirty = True
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror("Could not import picture", str(exc), parent=self)
            return
        self._refresh_thumbnails()
        self._select_image(self._selected_index)
        if self._record is not None:
            self._draw_composed(self._record)
        self._dirty = True
        self._save_button.config(state="normal")
        self._status_label.config(text="Unsaved changes")

    def _save(self) -> None:
        if self._current_path is None or self._current_bytes is None:
            return
        try:
            self._project.write_keeping_original(self._current_path, lz10.compress(self._current_bytes))
            if self._rd and self._wide_dirty and self._wide_bytes is not None:
                wide_path = portraits.face_dir(self._project) / "wide" / self._current_path.name
                self._project.write_keeping_original(wide_path, lz10.compress(self._wide_bytes))
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror("Could not save portrait", str(exc), parent=self)
            return
        self._dirty = False
        self._wide_dirty = False
        self._save_button.config(state="disabled")
        self._status_label.config(text=f"Saved {self._current_path.name}")
        self._changelog.append(self._current_path.stem, "Saved portrait (picture replaced)")
        self._portraits_changed()

    def _confirm_discard(self) -> bool:
        return messagebox.askyesno("Discard changes?", "This portrait has unsaved changes. Discard them?",
                                   parent=self)

    def _portraits_changed(self) -> None:
        cache = getattr(getattr(self.master, "shell", None), "portraits", None)
        if cache is not None and hasattr(cache, "clear"):
            cache.clear()

    # -- new / remove ---------------------------------------------------------------
    def _new_portrait(self) -> None:
        if self._rd:
            self._new_rd_portrait()
            return
        if self._dirty and not self._confirm_discard():
            return
        dialog = NewPortraitDialog(self, self._session)
        self.wait_window(dialog)
        if not dialog.result:
            return
        small_id, large_id, pid = dialog.result
        self._changelog.append(small_id, f"Added portraits {small_id} and {large_id}")
        if pid and self._session is not None and self._session.available:
            index = self._session.character_index(pid)
            if index is not None:
                self._session.data = fe8data.patch_character_field(self._session.data, index, "fid", small_id)
                self._session.changed(self)
        self._load_portrait_list()
        self._portraits_changed()
        self.select_character(small_id.removeprefix("FID_"))
        if pid:
            messagebox.showinfo("New portrait", f"{pid} now uses {small_id}. Save FE8Data.bin (Game Data or the "
                                "character page) to keep it.", parent=self)

    def _new_rd_portrait(self) -> None:
        if self._dirty and not self._confirm_discard():
            return
        if self._record is None or self._current_path is None:
            messagebox.showinfo("New portrait", "Select the portrait whose 15 picture slots should be copied.",
                                parent=self)
            return
        dialog = NewRdPortraitDialog(self, self._session, self._record)
        self.wait_window(dialog)
        if not dialog.result:
            return
        name, name_id, pid = dialog.result
        face_dir = portraits.face_dir(self._project)
        path, wide_path = face_dir / "facedata.bin", face_dir / "wide" / "facedata.bin"
        try:
            data, wide_data = path.read_bytes(), wide_path.read_bytes()
            records, wide_records = fe10_faces.read_face_data(data), fe10_faces.read_face_data(wide_data)
            source_index = next(i for i, item in enumerate(records) if item.fid == self._record.fid)
            wide_source = next(i for i, item in enumerate(wide_records) if item.fid == self._record.fid)
            data, new_index = fe10_faces.add_face_record(data, source_index, name, name_id)
            wide_data, _ = fe10_faces.add_face_record(wide_data, wide_source, name, name_id)
            new = fe10_faces.read_face_data(data)[new_index]
            target, wide_target = face_dir / new.filename, face_dir / "wide" / new.filename
            if target.exists() or wide_target.exists():
                raise ValueError(f"Face/{new.filename} already exists.")
            normal_texture = self._current_path.read_bytes()
            source_wide = face_dir / "wide" / self._current_path.name
            wide_texture = source_wide.read_bytes()
            self._project.write_keeping_original(path, data)
            self._project.write_keeping_original(wide_path, wide_data)
            self._project.write_keeping_original(target, normal_texture)
            self._project.write_keeping_original(wide_target, wide_texture)
        except (ValueError, OSError, StopIteration) as exc:
            messagebox.showerror("Could not add portrait", str(exc), parent=self)
            return
        self._changelog.append(new.fid, f"Added portrait slot {new.fid} / {new.large_fid}")
        if pid and self._session is not None and self._session.available:
            index = self._session.character_index(pid)
            if index is not None:
                self._session.data = fe10data.patch_field(self._session.data, "character", index, "fid", new.fid)
                self._session.changed(self)
        self._load_portrait_list()
        self._portraits_changed()
        self.select_character(new.fid)
        if pid:
            messagebox.showinfo("New portrait", f"{pid} now uses {new.fid}. Save FE10Data.cms (Game Data or the "
                                "character page) to keep it.", parent=self)

    def _remove_portrait(self) -> None:
        if self._rd:
            self._remove_rd_portrait()
            return
        records = self._records_of(self._current_path) if self._current_path else []
        if not records:
            return
        fid = records[0].fid
        if not messagebox.askyesno("Remove portrait", f"Remove {fid}, its large/small pair and their files?",
                                   parent=self):
            return
        try:
            removed = portraits.remove_portrait(self._project, fid)
        except (ValueError, OSError) as exc:
            messagebox.showerror("Could not remove", str(exc), parent=self)
            return
        self._changelog.append(fid, "Removed portraits " + ", ".join(removed))
        self._current_path = None
        self._load_portrait_list()
        self._portraits_changed()

    def _remove_rd_portrait(self) -> None:
        records = self._records_of(self._current_path) if self._current_path else []
        if not records:
            return
        record = records[0]
        if record.fid in self._retail_ids():
            messagebox.showerror("Could not remove", "The game's own portraits cannot be removed.", parent=self)
            return
        if not messagebox.askyesno("Remove portrait", f"Remove {record.fid}, its face-table row and both files?",
                                   parent=self):
            return
        face_dir = portraits.face_dir(self._project)
        path, wide_path = face_dir / "facedata.bin", face_dir / "wide" / "facedata.bin"
        try:
            data, wide_data = path.read_bytes(), wide_path.read_bytes()
            normal_records, wide_records = fe10_faces.read_face_data(data), fe10_faces.read_face_data(wide_data)
            index = next(i for i, item in enumerate(normal_records) if item.fid == record.fid)
            wide_index = next(i for i, item in enumerate(wide_records) if item.fid == record.fid)
            data = fe10_faces.remove_face_record(data, index)
            wide_data = fe10_faces.remove_face_record(wide_data, wide_index)
            self._project.write_keeping_original(path, data)
            self._project.write_keeping_original(wide_path, wide_data)
            if not any(item.filename.casefold() == record.filename.casefold()
                       for item in fe10_faces.read_face_data(data)):
                for texture in (face_dir / record.filename, face_dir / "wide" / record.filename):
                    if texture.exists():
                        texture.unlink()
        except (ValueError, OSError, StopIteration) as exc:
            messagebox.showerror("Could not remove portrait", str(exc), parent=self)
            return
        self._changelog.append(record.fid, f"Removed portrait slot {record.fid} / {record.large_fid}")
        self._current_path = None
        self._load_portrait_list()
        self._portraits_changed()

    # -- workspace navigation -------------------------------------------------
    def select_character(self, name: str) -> None:
        """Jump to a portrait by file name, ``FID_`` or ``PID_`` (prefix, case
        insensitive) - used by links from other editors. A character often
        has several variants (IKE.cms, IKE2.cms, IKEa.cms...); this selects
        the first match."""
        if not self.confirm_navigate_away():
            return
        needle = name.strip().upper().removeprefix("PID_").removeprefix("FID_")
        if self._session is not None and self._session.available and name.startswith("PID_"):
            index = self._session.character_index(name)
            if self._rd:
                fid = self._session.fe10.characters[index].values.get("fid") if index is not None else None
            else:
                fid = self._session.fe8.characters[index].fid if index is not None else None
            if fid:
                needle = fid.removeprefix("FID_")
        for i, path in enumerate(self._filtered_files):
            ids = [r.fid.removeprefix("FID_") for r in self._records_of(path)]
            if needle in ids or path.stem.upper().startswith(needle):
                self._file_list.selection_clear(0, "end")
                self._file_list.selection_set(i)
                self._file_list.see(i)
                self._on_file_selected()
                return


class NewRdPortraitDialog(tk.Toplevel):
    """Create an FE10 slot by cloning the selected normal/wide texture set and row geometry."""

    def __init__(self, viewer: PortraitViewer, session, source: fe10_faces.FaceRecord):
        super().__init__(viewer)
        self.title("New Radiant Dawn portrait")
        self.transient(viewer.winfo_toplevel())
        self.result = None
        body = ttk.Frame(self, padding=12)
        body.pack(fill="both", expand=True)
        labels = sorted(session.labels_by_prefix.get("MPID_", [])) if session and session.available else []
        pids = ([record.values.get("pid") for record in session.fe10.characters
                 if record.values.get("pid")] if session and session.available else [])
        self._name, self._name_key, self._pid = tk.StringVar(), tk.StringVar(value=source.name_id), tk.StringVar()
        ttk.Label(body, text="Name (FID_…)").grid(row=0, column=0, sticky="w")
        ttk.Entry(body, textvariable=self._name, width=26).grid(row=0, column=1, sticky="w")
        ttk.Label(body, text="HERO creates FID_HERO, FID_L_HERO and HERO.cms",
                  style="Muted.TLabel").grid(row=0, column=2, sticky="w", padx=(8, 0))
        ttk.Label(body, text="Name key").grid(row=1, column=0, sticky="w", pady=(4, 0))
        ttk.Combobox(body, textvariable=self._name_key, values=labels, width=26).grid(
            row=1, column=1, sticky="w", pady=(4, 0))
        ttk.Label(body, text="Use for character").grid(row=2, column=0, sticky="w", pady=(4, 0))
        ttk.Combobox(body, textvariable=self._pid, values=[""] + pids, width=26, state="readonly").grid(
            row=2, column=1, sticky="w", pady=(4, 0))
        ttk.Label(body, text=f"Starts as a copy of {source.fid}; replace its individual pictures after creation.",
                  style="Muted.TLabel").grid(row=3, column=0, columnspan=3, sticky="w", pady=(10, 0))
        buttons = ttk.Frame(body)
        buttons.grid(row=4, column=0, columnspan=3, sticky="e", pady=(12, 0))
        ttk.Button(buttons, text="Create", command=self._create).pack(side="left")
        ttk.Button(buttons, text="Cancel", command=self.destroy).pack(side="left", padx=(6, 0))
        self.grab_set()

    def _create(self) -> None:
        name, name_key = self._name.get().strip(), self._name_key.get().strip()
        if not name:
            messagebox.showerror("New portrait", "Enter a face name.", parent=self)
            return
        if not name_key.startswith("MPID_"):
            messagebox.showerror("New portrait", "The name key is an MPID_ label.", parent=self)
            return
        self.result = (name, name_key, self._pid.get() or None)
        self.destroy()


class NewPortraitDialog(tk.Toplevel):
    """Pictures and placement for a new small + large portrait pair."""

    def __init__(self, viewer: PortraitViewer, session):
        super().__init__(viewer)
        self.title("New portrait")
        self.transient(viewer.winfo_toplevel())
        self.result = None
        self._viewer = viewer
        self._files: dict[str, list[str]] = {}
        body = ttk.Frame(self, padding=12)
        body.pack(fill="both", expand=True)

        names = sorted(session.labels_by_prefix.get("MPID", {}).keys()) if session and session.available else []
        pids = [c.pid for c in session.fe8.characters if c.pid] if session and session.available else []
        self._face_name = tk.StringVar()
        self._name_key = tk.StringVar()
        self._pid = tk.StringVar()
        ttk.Label(body, text="Name (FID_…)").grid(row=0, column=0, sticky="w")
        ttk.Entry(body, textvariable=self._face_name, width=24).grid(row=0, column=1, sticky="w")
        ttk.Label(body, text="HERO makes FID_HERO and FID_L_HERO", style="Muted.TLabel").grid(
            row=0, column=2, columnspan=4, sticky="w", padx=(8, 0))
        ttk.Label(body, text="Name key (MPID_…)").grid(row=1, column=0, sticky="w")
        ttk.Combobox(body, textvariable=self._name_key, values=names, width=24).grid(row=1, column=1, sticky="w")
        ttk.Label(body, text="Use for character").grid(row=2, column=0, sticky="w")
        ttk.Combobox(body, textvariable=self._pid, values=[""] + pids, width=24, state="readonly").grid(
            row=2, column=1, sticky="w")

        self._positions: dict[str, tk.IntVar] = {}
        row = 3
        for size, label, body_hint in (("small", "Small portrait", "fitted to 192 x 128"),
                                       ("large", "Large portrait", "kept as is (retail up to 256 x 296); "
                                                                   "empty: the small one enlarged")):
            ttk.Separator(body).grid(row=row, column=0, columnspan=6, sticky="ew", pady=8)
            ttk.Label(body, text=label, style="Heading.TLabel").grid(row=row + 1, column=0, sticky="w")
            row += 2
            for part, part_label, hint in (("body", "Body picture", body_hint),
                                           ("mouths", "Mouth frames (6)", "two sets of three; 3rd and 6th closed"),
                                           ("eyes", "Eye frames (6)", "left eye 1-3, right eye 4-6")):
                key = f"{size}_{part}"
                shown = tk.StringVar(value="(none)")
                ttk.Label(body, text=part_label).grid(row=row, column=0, sticky="w")
                ttk.Button(body, text="Choose…", command=lambda k=key, s=shown, many=part != "body":
                           self._choose(k, s, many)).grid(row=row, column=1, sticky="w")
                ttk.Label(body, textvariable=shown, width=28).grid(row=row, column=2, columnspan=2, sticky="w")
                ttk.Label(body, text=hint, style="Muted.TLabel").grid(row=row, column=4, columnspan=2, sticky="w")
                row += 1
            for spot in ("left eye", "right eye", "mouth"):
                ttk.Label(body, text=f"{spot.capitalize()} x, y").grid(row=row, column=0, sticky="w")
                for i in range(2):
                    var = self._positions[f"{size}_{spot}_{i}"] = tk.IntVar(value=-1)
                    ttk.Spinbox(body, from_=-1, to=512, width=6, textvariable=var).grid(
                        row=row, column=1 + i, sticky="w")
                row += 1
        ttk.Separator(body).grid(row=row, column=0, columnspan=6, sticky="ew", pady=8)
        shown = tk.StringVar(value="(cut from the small body)")
        ttk.Label(body, text="Menu face (64 x 64)").grid(row=row + 1, column=0, sticky="w")
        ttk.Button(body, text="Choose…", command=lambda: self._choose("menu", shown, False)).grid(
            row=row + 1, column=1, sticky="w")
        ttk.Label(body, textvariable=shown).grid(row=row + 1, column=2, columnspan=3, sticky="w")
        buttons = ttk.Frame(body)
        buttons.grid(row=row + 2, column=0, columnspan=6, sticky="e", pady=(12, 0))
        ttk.Button(buttons, text="Create", command=self._create).pack(side="left")
        ttk.Button(buttons, text="Cancel", command=self.destroy).pack(side="left", padx=(6, 0))
        self.grab_set()

    def _choose(self, key: str, shown: tk.StringVar, many: bool) -> None:
        if many:
            chosen = sorted(filedialog.askopenfilenames(title="Choose six pictures (sorted by file name)",
                                                        filetypes=IMAGE_TYPES, parent=self))
            if chosen and len(chosen) != 6:
                messagebox.showerror("New portrait", "Choose exactly six pictures.", parent=self)
                return
        else:
            one = filedialog.askopenfilename(title="Choose a picture", filetypes=IMAGE_TYPES, parent=self)
            chosen = [one] if one else []
        if chosen:
            self._files[key] = list(chosen)
            shown.set(", ".join(Path(c).name for c in chosen)[:60])

    def _images(self, key: str):
        paths = self._files.get(key)
        return [Image.open(p) for p in paths] if paths else None

    def _spots(self, size: str):
        values = tuple(tuple(self._positions[f"{size}_{spot}_{i}"].get() for i in range(2))
                       for spot in ("left eye", "right eye", "mouth"))
        return None if all(v == (-1, -1) for v in values) else values

    def _create(self) -> None:
        try:
            body = self._images("small_body")
            if not body:
                raise ValueError("Choose the small portrait's body picture.")
            large = self._images("large_body")
            menu = self._images("menu")
            ids = portraits.add_portrait(
                self._viewer._project, self._face_name.get(), self._name_key.get().strip(), body[0],
                large[0] if large else None,
                small_mouths=self._images("small_mouths"), small_eyes=self._images("small_eyes"),
                small_positions=self._spots("small"),
                large_mouths=self._images("large_mouths"), large_eyes=self._images("large_eyes"),
                large_positions=self._spots("large"), menu_face=menu[0] if menu else None)
        except (ValueError, OSError, tk.TclError) as exc:
            messagebox.showerror("New portrait", str(exc), parent=self)
            return
        self.result = (*ids, self._pid.get() or None)
        self.destroy()
