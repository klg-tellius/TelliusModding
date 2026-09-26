"""Browsers/importers for TPL-based image folders outside the two already
covered by ``background_viewer.py`` (``files/s/*``) and ``portrait_viewer.py``
(``files/Face/*.cms``). The encodings are exactly the same two this app
already decodes - a raw ``.tpl`` (like backgrounds) or an LZ10-compressed TPL,
usually named ``.cms`` (like portraits) - just appearing under different
folders that were never wired into the GUI:

- ``files/illust/*.tpl`` - CG illustrations (full-screen art)
- ``files/ending/*.tpl`` - end-sequence art
- ``files/window/*.tpl``/``*.cms`` - UI/menu graphics
- ``files/etc/*.tpl``/``*.cms`` - shared misc art (cursor, icons, menu backgrounds)
- ``files/gmap/*.tpl``/``*.cms`` - world map art
- ``files/zu/**/*.tpl`` - equipment appearance (armor/weapon-on-character sprites)

``zu`` also holds region-variant ``.pak`` archives (``amr1_ja.pak`` etc.) -
those are a different container (more images packed inside, not a single TPL)
and are deliberately out of scope here; only the flat ``.tpl`` files directly
under each ``zu/*/`` folder are covered.

``ImageArchiveViewer`` is the shared base for all six panels below - factored
out of ``background_viewer.py`` (still the template to read first) since six
near-identical panels are being added in one pass; unlike this app's four
chapter-scoped editors (which grew independently and stay deliberately
unshared), this is real, current duplication worth factoring once.
``background_viewer.py`` and ``portrait_viewer.py`` themselves are untouched -
both are already validated end-to-end against real disc rebuilds, and
rebasing them onto this new class isn't worth the regression risk.

Every subclass just supplies ``display_name``, ``empty_message``, and
``_iter_files()``; decode/encode dispatch (raw vs. LZ10, by file extension -
``.cms`` is compressed, everything else here is a raw TPL) lives once in the
base class, so a folder mixing both (``window``, ``etc``, ``gmap``) works
without any per-folder special-casing.
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

PREVIEW_MAX_SIZE = (480, 300)
THUMB_SIZE = (100, 74)


class ImageArchiveViewer(EditorPanel):
    display_name = ""
    empty_message = "No files found.\nExtract the project first."

    def __init__(self, parent: tk.Misc, project: ModProject, changelog: ChangeLog):
        super().__init__(parent)
        self._project = project
        self._changelog = changelog
        self._current_path: Path | None = None
        self._current_bytes: bytes | None = None  # decoded (decompressed) TPL bytes
        self._infos: list[tpl.TplImageInfo] = []
        self._decoded_images: list[Image.Image] = []
        self._selected_index: int | None = None
        self._dirty = False
        self._thumb_photos: list[ImageTk.PhotoImage] = []  # keep references alive
        self._preview_photo: ImageTk.PhotoImage | None = None

        self._build_widgets()
        self._load_file_list()

    # -- subclass hooks -------------------------------------------------------
    def _iter_files(self) -> list[Path]:
        raise NotImplementedError

    @staticmethod
    def _is_compressed(path: Path) -> bool:
        return path.suffix.lower() == ".cms"

    def _decode(self, path: Path, raw: bytes) -> bytes:
        return lz10.decompress(raw) if self._is_compressed(path) else raw

    def _encode(self, path: Path, tpl_bytes: bytes) -> bytes:
        return lz10.compress(tpl_bytes) if self._is_compressed(path) else tpl_bytes

    # -- layout -------------------------------------------------------------
    def _build_widgets(self) -> None:
        paned = ttk.PanedWindow(self, orient="horizontal")
        paned.pack(fill="both", expand=True)

        # left: file list
        left = ttk.Frame(paned, padding=8)
        paned.add(left, weight=1)
        ttk.Label(left, text=self.display_name).pack(anchor="w")

        search_var = tk.StringVar()
        ttk.Entry(left, textvariable=search_var).pack(fill="x", pady=(4, 4))
        search_var.trace_add("write", lambda *_: self._apply_filter(search_var.get()))

        self._empty_label = ttk.Label(left, text="", style="Muted.TLabel")
        self._empty_label.pack(anchor="w")

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
    def _load_file_list(self) -> None:
        self._all_files = self._iter_files()
        self._apply_filter("")
        self._empty_label.config(text=self.empty_message if not self._all_files else "")

    def _apply_filter(self, query: str) -> None:
        query = query.strip().lower()
        self._filtered_files = [p for p in self._all_files if query in p.name.lower()]
        self._file_list.delete(0, "end")
        for path in self._filtered_files:
            self._file_list.insert("end", path.name)

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
            raw = self._current_path.read_bytes()
            self._current_bytes = self._decode(self._current_path, raw)
            self._infos = tpl.read_tpl_image_info(io.BytesIO(self._current_bytes))
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror("Could not read file", str(exc), parent=self)
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
            messagebox.showerror("Could not decode file", str(exc), parent=self)
            self._decoded_images = []
            return

        for i, image in enumerate(self._decoded_images):
            thumb = image.copy()
            thumb.thumbnail(THUMB_SIZE)
            backing = Image.new("RGBA", thumb.size, (128, 128, 128, 255))
            backing.alpha_composite(thumb.convert("RGBA"))
            photo = ImageTk.PhotoImage(backing)
            self._thumb_photos.append(photo)
            btn = ttk.Button(self._thumb_frame, image=photo, command=lambda i=i: self._select_image(i))
            btn.pack(side="left", padx=(0, 6))

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
            self._current_path.write_bytes(self._encode(self._current_path, self._current_bytes))
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror("Could not save file", str(exc), parent=self)
            return
        self._dirty = False
        self._save_button.config(state="disabled")
        self._status_label.config(text=f"Saved {self._current_path.name}")
        self._changelog.append(self._current_path.name, "Saved (image replaced)")

    def _confirm_discard(self) -> bool:
        return messagebox.askyesno(
            "Discard changes?", "This file has unsaved changes. Discard them?", parent=self
        )


def _sorted_files(folder: Path, *extensions: str) -> list[Path]:
    if not folder.exists():
        return []
    return sorted(p for p in folder.rglob("*") if p.is_file() and p.suffix.lower() in extensions)


class IllustrationViewer(ImageArchiveViewer):
    display_name = "Illustrations"
    empty_message = "No illustration files found.\nExtract the project first."

    def _iter_files(self) -> list[Path]:
        return _sorted_files(self._project.extracted_dir / "files" / "illust", ".tpl")


class EndingViewer(ImageArchiveViewer):
    display_name = "Ending Art"
    empty_message = "No ending art files found.\nExtract the project first."

    def _iter_files(self) -> list[Path]:
        return _sorted_files(self._project.extracted_dir / "files" / "ending", ".tpl")


class WindowGraphicsViewer(ImageArchiveViewer):
    display_name = "UI Windows"
    empty_message = "No UI graphics files found.\nExtract the project first."

    def _iter_files(self) -> list[Path]:
        return _sorted_files(self._project.extracted_dir / "files" / "window", ".tpl", ".cms")


class EtcGraphicsViewer(ImageArchiveViewer):
    display_name = "Misc Graphics"
    empty_message = "No misc graphics files found.\nExtract the project first."

    def _iter_files(self) -> list[Path]:
        return _sorted_files(self._project.extracted_dir / "files" / "etc", ".tpl", ".cms")


class WorldMapViewer(ImageArchiveViewer):
    display_name = "World Map"
    empty_message = "No world map files found.\nExtract the project first."

    def _iter_files(self) -> list[Path]:
        return _sorted_files(self._project.extracted_dir / "files" / "gmap", ".tpl", ".cms")


class EquipmentViewer(ImageArchiveViewer):
    display_name = "Equipment"
    empty_message = "No equipment graphics files found.\nExtract the project first."

    def _iter_files(self) -> list[Path]:
        # zu/ also holds region-variant .pak archives (amr1_ja.pak etc.) -
        # a different container (multiple packed images, not a single TPL)
        # that's out of scope here; only the flat .tpl files are covered.
        return _sorted_files(self._project.extracted_dir / "files" / "zu", ".tpl")
