"""Background viewer/importer: browse every conversation-scene background
(``files/s/*``) and replace one with a custom image.

Backgrounds are standalone (not `.cmp`-compressed, not pak'd) CMPR .tpl
files, confirmed by cross-checking files this editor lists against s/rect.bin
(fe_modding.formats.rect): the same filenames turn up there with resolved
resource names, and every one decoded so far has been full-scene art (not a
portrait, UI element, or anything else `.tpl` also gets used for elsewhere
in the game) - see CLAUDE.md for how that was confirmed.

A single background file can hold more than one image (day/night variants,
damage states, ...); each is listed and replaced independently.
"""

from __future__ import annotations

import io
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from PIL import Image, ImageTk

from ..formats import rect, tpl
from ..project import ModProject
from .changelog import ChangeLog
from .editor_panel import EditorPanel

PREVIEW_MAX_SIZE = (480, 300)
THUMB_SIZE = (120, 74)


class BackgroundViewer(EditorPanel):
    display_name = "Backgrounds"

    def __init__(self, parent: tk.Misc, project: ModProject, changelog: ChangeLog):
        super().__init__(parent)
        self._project = project
        self._changelog = changelog
        self._current_path: Path | None = None
        self._current_bytes: bytes | None = None
        self._infos: list[tpl.TplImageInfo] = []
        self._decoded_images: list[Image.Image] = []
        self._selected_index: int | None = None
        self._dirty = False
        self._thumb_photos: list[ImageTk.PhotoImage] = []  # keep references alive
        self._preview_photo: ImageTk.PhotoImage | None = None

        self._build_widgets()
        self._load_background_list()

    # -- layout -------------------------------------------------------------
    def _build_widgets(self) -> None:
        paned = ttk.PanedWindow(self, orient="horizontal")
        paned.pack(fill="both", expand=True)

        # left: background file list
        left = ttk.Frame(paned, padding=8)
        paned.add(left, weight=1)
        ttk.Label(left, text="Backgrounds").pack(anchor="w")

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

        # right: thumbnails + preview + import
        right = ttk.Frame(paned, padding=8)
        paned.add(right, weight=2)

        ttk.Label(right, text="Images in this file").pack(anchor="w")
        self._thumb_frame = ttk.Frame(right)
        self._thumb_frame.pack(fill="x", pady=(4, 8))

        self._preview_label = ttk.Label(right, relief="groove")
        self._preview_label.pack(pady=(0, 8))

        self._info_label = ttk.Label(right, text="", style="Muted.TLabel")
        self._info_label.pack(anchor="w")

        button_row = ttk.Frame(right)
        button_row.pack(fill="x", pady=(8, 0))
        self._import_button = ttk.Button(
            button_row, text="Import Replacement Image...", command=self._import_image, state="disabled"
        )
        self._import_button.pack(side="left")
        self._save_button = ttk.Button(button_row, text="Save", command=self._save, state="disabled")
        self._save_button.pack(side="left", padx=(8, 0))
        self._status_label = ttk.Label(button_row, text="", style="Muted.TLabel")
        self._status_label.pack(side="left", padx=(8, 0))

    # -- data loading ---------------------------------------------------------
    def _load_background_list(self) -> None:
        background_dir = self._project.extracted_dir / "files" / "s"
        self._all_files = sorted(p for p in background_dir.glob("*") if p.is_file()) if background_dir.exists() else []

        self._names_by_file: dict[str, str] = {}
        try:
            rect_path = self._project.extracted_dir / "files" / "s" / "rect.bin"
            if rect_path.exists():
                for entry in rect.read_rects_path(rect_path):
                    for image in entry.images:
                        file_name = image.file_name.decode("ascii", errors="replace")
                        short_name = file_name.split("/")[-1]
                        label = entry.resource_id.decode("shift-jis", errors="replace")
                        self._names_by_file.setdefault(short_name, label)
        except Exception:  # noqa: BLE001 - naming is a convenience, never block listing files over it
            pass

        self._apply_filter("")

        if not self._all_files:
            ttk.Label(
                self._file_list.master,
                text="No background files found.\nExtract the project first.",
                style="Muted.TLabel",
            ).pack(pady=8)

    def _apply_filter(self, query: str) -> None:
        query = query.strip().lower()
        self._filtered_files = [
            p
            for p in self._all_files
            if p.name != "rect.bin"
            and (query in p.name.lower() or query in self._names_by_file.get(p.name, "").lower())
        ]
        self._file_list.delete(0, "end")
        for path in self._filtered_files:
            label = self._names_by_file.get(path.name)
            self._file_list.insert("end", f"{path.name}   ({label})" if label else path.name)

    def _on_file_selected(self) -> None:
        selection = self._file_list.curselection()
        if not selection:
            return
        if self._dirty and not self._confirm_discard():
            self._file_list.selection_clear(0, "end")
            if self._current_path in self._filtered_files:
                self._file_list.selection_set(self._filtered_files.index(self._current_path))
            return

        self._current_path = self._filtered_files[selection[0]]
        try:
            self._current_bytes = self._current_path.read_bytes()
            self._infos = tpl.read_tpl_image_info_path(self._current_path)
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror("Could not read background", str(exc), parent=self)
            return

        self._dirty = False
        self._save_button.config(state="disabled")
        self._refresh_thumbnails()
        if self._infos:
            self._select_image(0)

    def _refresh_thumbnails(self) -> None:
        for child in self._thumb_frame.winfo_children():
            child.destroy()
        self._thumb_photos.clear()

        try:
            self._decoded_images = tpl.read_tpl_images(io.BytesIO(self._current_bytes))
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror("Could not decode background", str(exc), parent=self)
            self._decoded_images = []
            return

        for i, image in enumerate(self._decoded_images):
            thumb = image.copy()
            thumb.thumbnail(THUMB_SIZE)
            photo = ImageTk.PhotoImage(thumb)
            self._thumb_photos.append(photo)
            btn = ttk.Button(self._thumb_frame, image=photo, command=lambda i=i: self._select_image(i))
            btn.pack(side="left", padx=(0, 6))

    def _select_image(self, index: int) -> None:
        self._selected_index = index
        image = self._decoded_images[index]
        preview = image.copy()
        preview.thumbnail(PREVIEW_MAX_SIZE)
        self._preview_photo = ImageTk.PhotoImage(preview)
        self._preview_label.config(image=self._preview_photo)

        info = self._infos[index]
        importable = info.format in tpl.ENCODABLE_FORMATS
        format_note = tpl.format_name(info.format) if importable else f"{tpl.format_name(info.format)} (view-only, can't import)"
        self._info_label.config(text=f"Image {index}: {info.width} x {info.height}, {format_note}")
        self._import_button.config(state="normal" if importable else "disabled")

    # -- import / save --------------------------------------------------------
    def _import_image(self) -> None:
        if self._selected_index is None or self._current_bytes is None:
            return
        info = self._infos[self._selected_index]

        chosen = filedialog.askopenfilename(
            title=f"Choose a replacement image ({info.width}x{info.height} - it will be stretched to fit)",
            filetypes=[("Images", "*.png *.jpg *.jpeg *.bmp *.gif"), ("All files", "*.*")],
            parent=self,
        )
        if not chosen:
            return

        try:
            new_image = Image.open(chosen)
            self._current_bytes = tpl.replace_image(self._current_bytes, self._selected_index, new_image)
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror("Could not import image", str(exc), parent=self)
            return

        self._refresh_thumbnails()
        self._select_image(self._selected_index)
        self._dirty = True
        self._save_button.config(state="normal")
        self._status_label.config(text="Unsaved changes")

    def _save(self) -> None:
        if self._current_path is None or self._current_bytes is None:
            return
        try:
            self._current_path.write_bytes(self._current_bytes)
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror("Could not save background", str(exc), parent=self)
            return
        self._dirty = False
        self._save_button.config(state="disabled")
        self._status_label.config(text=f"Saved {self._current_path.name}")
        self._changelog.append(self._current_path.name, "Saved (image replaced)")

    def _confirm_discard(self) -> bool:
        return messagebox.askyesno(
            "Discard changes?", "This background has unsaved changes. Discard them?", parent=self
        )
