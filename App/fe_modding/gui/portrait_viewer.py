"""Portrait viewer/importer: browse every character's dialogue portrait
(``files/Face/*.cms``) and replace one of its images with a custom picture.

Confirmed against a real file (IKE.cms): LZ10-decompresses directly to a TPL
(no pak archive in between, unlike backgrounds/maps/dispo) holding 14 images
- one 192x128 base face plus several tiny (24x24/16x16) pieces that read
  like eye-blink/mouth-flap animation frames, all sharing one 256-color C8
  palette, plus a 13th unrelated 64x64 image on its own separate palette.
The base face has real alpha=0 holes cut out right where those small pieces
would be composited (confirmed by compositing over a solid color) - that's
expected, not a decode bug.

Finding this file is also what caught a real bug in fe_modding.formats.tpl:
its C8/palette-indexed decode path was unverified until this file was
decoded against it, and the fix (a wrong bit checked for opaque-vs-alpha in
the palette color format) is now confirmed correct - see tpl._rgb5a3().

Import is constrained by the shared palette (see tpl.replace_image()'s
docstring) - a replacement image's colors get matched to whatever palette
that character's portrait already has, not given a fresh one, because other
images in the same file depend on that exact palette too.
"""

from __future__ import annotations

import io
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from PIL import Image, ImageTk

from ..formats import lz10, tpl
from ..project import ModProject
from .changelog import ChangeLog
from .editor_panel import EditorPanel

PREVIEW_MAX_SIZE = (400, 300)
THUMB_SIZE = (72, 72)


class PortraitViewer(EditorPanel):
    display_name = "Portraits"

    def __init__(self, parent: tk.Misc, project: ModProject, changelog: ChangeLog):
        super().__init__(parent)
        self._project = project
        self._changelog = changelog
        self._current_path: Path | None = None
        self._current_bytes: bytes | None = None  # decompressed TPL bytes
        self._infos: list[tpl.TplImageInfo] = []
        self._decoded_images: list[Image.Image] = []
        self._selected_index: int | None = None
        self._dirty = False
        self._thumb_photos: list[ImageTk.PhotoImage] = []  # keep references alive
        self._preview_photo: ImageTk.PhotoImage | None = None

        self._build_widgets()
        self._load_portrait_list()

    # -- layout -------------------------------------------------------------
    def _build_widgets(self) -> None:
        paned = ttk.PanedWindow(self, orient="horizontal")
        paned.pack(fill="both", expand=True)

        # left: character list
        left = ttk.Frame(paned, padding=8)
        paned.add(left, weight=1)
        ttk.Label(left, text="Characters").pack(anchor="w")

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

        ttk.Label(right, text="Images in this portrait (base face + animation pieces)").pack(anchor="w")
        thumb_container = ttk.Frame(right)
        thumb_container.pack(fill="x", pady=(4, 8))
        self._thumb_frame = ttk.Frame(thumb_container)
        self._thumb_frame.pack(fill="x")

        self._preview_label = ttk.Label(right, relief="groove")
        self._preview_label.pack(pady=(0, 8))

        self._info_label = ttk.Label(right, text="", style="Muted.TLabel")
        self._info_label.pack(anchor="w")

        ttk.Label(
            right,
            text="Import matches your image's colors to this character's existing\n"
            "portrait palette (shared with the other images shown above) - it\n"
            "won't come out exactly like the source picture, especially for\n"
            "very different colors.",
            style="Muted.TLabel",
            justify="left",
        ).pack(anchor="w", pady=(4, 0))

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
    def _load_portrait_list(self) -> None:
        face_dir = self._project.extracted_dir / "files" / "Face"
        self._all_files = sorted(p for p in face_dir.glob("*.cms") if p.is_file()) if face_dir.exists() else []
        self._apply_filter("")

        if not self._all_files:
            ttk.Label(
                self._file_list.master,
                text="No portrait files found.\nExtract the project first.",
                style="Muted.TLabel",
            ).pack(pady=8)

    def _apply_filter(self, query: str) -> None:
        query = query.strip().lower()
        self._filtered_files = [p for p in self._all_files if query in p.stem.lower()]
        self._file_list.delete(0, "end")
        for path in self._filtered_files:
            self._file_list.insert("end", path.stem)

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
            self._current_bytes = lz10.decompress(self._current_path.read_bytes())
            self._infos = tpl.read_tpl_image_info(io.BytesIO(self._current_bytes))
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror("Could not read portrait", str(exc), parent=self)
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
            messagebox.showerror("Could not decode portrait", str(exc), parent=self)
            self._decoded_images = []
            return

        row_frame = None
        for i, image in enumerate(self._decoded_images):
            if i % 8 == 0:
                row_frame = ttk.Frame(self._thumb_frame)
                row_frame.pack(anchor="w")
            thumb = image.copy()
            thumb.thumbnail(THUMB_SIZE)
            # composite over a mid-gray so alpha holes (eye/mouth cutouts) are visible in the thumbnail
            backing = Image.new("RGBA", thumb.size, (128, 128, 128, 255))
            backing.alpha_composite(thumb.convert("RGBA"))
            photo = ImageTk.PhotoImage(backing)
            self._thumb_photos.append(photo)
            btn = ttk.Button(row_frame, image=photo, command=lambda i=i: self._select_image(i))
            btn.pack(side="left", padx=(0, 4), pady=(0, 4))

    def _select_image(self, index: int) -> None:
        self._selected_index = index
        image = self._decoded_images[index]

        backing = Image.new("RGBA", image.size, (128, 128, 128, 255))
        backing.alpha_composite(image.convert("RGBA"))
        preview = backing.copy()
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
            self._current_path.write_bytes(lz10.compress(self._current_bytes))
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror("Could not save portrait", str(exc), parent=self)
            return
        self._dirty = False
        self._save_button.config(state="disabled")
        self._status_label.config(text=f"Saved {self._current_path.name}")
        self._changelog.append(self._current_path.stem, "Saved portrait (image replaced)")

    def _confirm_discard(self) -> bool:
        return messagebox.askyesno(
            "Discard changes?", "This portrait has unsaved changes. Discard them?", parent=self
        )

    # -- workspace navigation -------------------------------------------------
    def select_character(self, name: str) -> None:
        """Jump to a character's portrait file by (case-insensitive, prefix)
        name match - used by cross-reference links from other editors. A
        character often has several portrait file variants (IKE.cms,
        IKE2.cms, IKEa.cms, ...); this selects the first match."""
        if not self.confirm_navigate_away():
            return
        needle = name.strip().upper()
        for i, path in enumerate(self._filtered_files):
            if path.stem.upper().startswith(needle):
                self._file_list.selection_clear(0, "end")
                self._file_list.selection_set(i)
                self._file_list.see(i)
                self._on_file_selected()
                return
