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

``s/rect.bin`` says how the game shows those files (see ``formats/rect.py``):
each ``RID_`` resource lists the images it uses, the period they are
cross-faded over, a brightness and an optional weather overlay. The panel edits
those properties, and adds a new resource with its own TPL, which an event
script then shows with ``RectBuild("RID_...")``.
"""

from __future__ import annotations

import io
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, simpledialog, ttk

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
        self._rect_doc: rect.RectFile | None = None
        self._resource: rect.RectResource | None = None

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
        ttk.Button(left, text="Add New Background...", command=self._add_background).pack(fill="x", pady=(8, 0))

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

        self._build_resource_frame(right)

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

    def _build_resource_frame(self, parent: tk.Misc) -> None:
        frame = ttk.LabelFrame(parent, text="Rect resource (s/rect.bin)", padding=6)
        frame.pack(fill="x", pady=(8, 0))
        self._resource_choice = tk.StringVar()
        self._resource_box = ttk.Combobox(frame, textvariable=self._resource_choice, state="readonly", width=34)
        self._resource_box.grid(row=0, column=0, columnspan=4, sticky="we")
        self._resource_box.bind("<<ComboboxSelected>>", lambda e: self._show_resource())
        self._resource_layers = ttk.Label(frame, text="", style="Muted.TLabel")
        self._resource_layers.grid(row=1, column=0, columnspan=4, sticky="w", pady=(2, 4))

        self._mode_var = tk.StringVar()
        self._period_var = tk.StringVar()
        self._brightness_var = tk.StringVar()
        self._effect_var = tk.StringVar()
        ttk.Label(frame, text="Layers:").grid(row=2, column=0, sticky="w")
        ttk.Combobox(frame, textvariable=self._mode_var, state="readonly", width=12,
                     values=list(rect.MODE_NAMES.values())).grid(row=2, column=1, sticky="w", padx=(2, 12))
        ttk.Label(frame, text="Period (s):").grid(row=2, column=2, sticky="w")
        ttk.Spinbox(frame, textvariable=self._period_var, from_=0.1, to=60, increment=0.1, width=6).grid(
            row=2, column=3, sticky="w")
        ttk.Label(frame, text="Brightness:").grid(row=3, column=0, sticky="w", pady=(4, 0))
        ttk.Spinbox(frame, textvariable=self._brightness_var, from_=0, to=255, width=6).grid(
            row=3, column=1, sticky="w", padx=(2, 12), pady=(4, 0))
        ttk.Label(frame, text="Overlay:").grid(row=3, column=2, sticky="w", pady=(4, 0))
        ttk.Combobox(frame, textvariable=self._effect_var, state="readonly", width=14,
                     values=list(rect.EFFECT_NAMES.values())).grid(row=3, column=3, sticky="w", pady=(4, 0))
        self._resource_apply = ttk.Button(frame, text="Save Resource", command=self._save_resource, state="disabled")
        self._resource_apply.grid(row=4, column=0, columnspan=2, sticky="w", pady=(6, 0))
        ttk.Label(frame, text="Layers cross-fade over the period; 255 brightness is unchanged.",
                  style="Muted.TLabel").grid(row=4, column=2, columnspan=2, sticky="w", pady=(6, 0))

    def _load_rect_doc(self) -> None:
        self._rect_doc = None
        path = self._project.extracted_dir / "files" / "s" / "rect.bin"
        try:
            if path.exists():
                self._rect_doc = rect.read_rect_file(path)
        except Exception:  # noqa: BLE001 - the resource panel is optional, never block the file list on it
            self._rect_doc = None

    def _resources_using(self, path: Path | None) -> list[rect.RectResource]:
        if self._rect_doc is None or path is None:
            return []
        wanted = f"s/{path.name}"
        return [r for r in self._rect_doc.resources if any(layer.file == wanted for layer in r.layers)]

    def _show_resources_for_current_file(self) -> None:
        resources = self._resources_using(self._current_path)
        self._resource_box.config(values=[r.name for r in resources])
        self._resource_choice.set(resources[0].name if resources else "")
        self._show_resource()

    def _show_resource(self) -> None:
        name = self._resource_choice.get()
        self._resource = self._rect_doc.find(name) if self._rect_doc is not None and name else None
        resource = self._resource
        if resource is None:
            self._resource_layers.config(text="No rect resource uses this file.")
            for var in (self._mode_var, self._period_var, self._brightness_var, self._effect_var):
                var.set("")
            self._resource_apply.config(state="disabled")
            return
        width, height = resource.size
        textures = ", ".join(str(layer.texture) for layer in resource.layers)
        self._resource_layers.config(text=f"{len(resource.layers)} layer(s), {width}x{height}, texture {textures}")
        self._mode_var.set(rect.MODE_NAMES.get(resource.mode, str(resource.mode)))
        self._period_var.set(f"{resource.duration:g}")
        self._brightness_var.set(str(resource.brightness))
        self._effect_var.set(rect.EFFECT_NAMES.get(resource.effect, str(resource.effect)))
        self._resource_apply.config(state="normal")

    def _save_resource(self) -> None:
        resource = self._resource
        if resource is None or self._rect_doc is None:
            return
        try:
            mode = {v: k for k, v in rect.MODE_NAMES.items()}[self._mode_var.get()]
            effect = {v: k for k, v in rect.EFFECT_NAMES.items()}[self._effect_var.get()]
            duration = float(self._period_var.get())
            brightness = int(self._brightness_var.get())
            if not 0 < duration <= 600 or not 0 <= brightness <= 255:
                raise ValueError("Period must be 0-600 seconds and brightness 0-255.")
        except (KeyError, ValueError) as exc:
            messagebox.showerror("Invalid resource values", str(exc), parent=self)
            return
        resource.mode, resource.effect, resource.duration, resource.brightness = mode, effect, duration, brightness
        self._write_rect_doc(f"Edited {resource.name}")

    def _write_rect_doc(self, note: str) -> bool:
        path = self._project.extracted_dir / "files" / "s" / "rect.bin"
        try:
            rect.write_rect_file(self._rect_doc, path)
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror("Could not save rect.bin", str(exc), parent=self)
            return False
        self._changelog.append("rect.bin", note)
        self._status_label.config(text=note)
        return True

    def _add_background(self) -> None:
        if self._rect_doc is None:
            messagebox.showinfo("Add background", "s/rect.bin was not found; extract the project first.", parent=self)
            return
        chosen = filedialog.askopenfilenames(
            title="Choose the image(s) of the new background (several are cross-faded as an animation)",
            filetypes=[("Images", "*.png *.jpg *.jpeg *.bmp *.gif"), ("All files", "*.*")],
            parent=self,
        )
        if not chosen:
            return
        name = simpledialog.askstring(
            "Resource name",
            'Name for the new resource. An event script shows it with RectBuild("<name>").',
            initialvalue="RID_",
            parent=self,
        )
        if not name:
            return
        name = name.strip()
        try:
            images = [Image.open(path).convert("RGB") for path in chosen]
            if len({image.size for image in images}) != 1:
                first = images[0].size
                images = [image.resize(first, Image.LANCZOS) for image in images]
            rect.add_background(self._rect_doc, self._project.extracted_dir / "files", name, images)
        except Exception as exc:  # noqa: BLE001
            self._load_rect_doc()  # drop the half-added resource
            messagebox.showerror("Could not add background", str(exc), parent=self)
            return
        if not self._write_rect_doc(f"Added {name}"):
            return
        self._load_background_list()
        self._show_resources_for_current_file()
        messagebox.showinfo(
            "Background added",
            f'{name} is in s/rect.bin and its image is in files/s/. Build the project, then show it from an '
            f'event script with RectBuild("{name}").',
            parent=self,
        )

    # -- data loading ---------------------------------------------------------
    def _load_background_list(self) -> None:
        background_dir = self._project.extracted_dir / "files" / "s"
        self._all_files = sorted(p for p in background_dir.glob("*") if p.is_file()) if background_dir.exists() else []

        self._names_by_file: dict[str, str] = {}
        self._load_rect_doc()
        if self._rect_doc is not None:
            for resource in self._rect_doc.resources:
                for layer in resource.layers:
                    self._names_by_file.setdefault(layer.file.split("/")[-1], resource.name)

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

    def select_resource(self, resource_name: str) -> bool:
        """Open the first image file used by an RID_* background resource."""
        resource = self._rect_doc.find(resource_name) if self._rect_doc is not None else None
        if resource is None:
            return False
        self._apply_filter("")
        for layer in resource.layers:
            filename = layer.file.rsplit("/", 1)[-1]
            for index, path in enumerate(self._filtered_files):
                if path.name == filename:
                    self._file_list.selection_clear(0, "end")
                    self._file_list.selection_set(index)
                    self._file_list.activate(index)
                    self._file_list.see(index)
                    self._on_file_selected()
                    if self._current_path != path:
                        return False
                    self._resource_choice.set(resource_name)
                    self._show_resource()
                    return True
        return False

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
        self._show_resources_for_current_file()

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
