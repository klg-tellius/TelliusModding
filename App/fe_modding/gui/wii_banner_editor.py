"""Wii Banner (Radiant Dawn): the channel titles and pictures of ``opening.bnr``
(see :mod:`fe_modding.formats.wii_banner`)."""

from __future__ import annotations

import io
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import Optional

from PIL import Image, ImageTk

from ..formats import tpl
from ..formats import wii_banner as wb
from ..game_profile import files_root_of
from ..project import ModProject
from . import theme
from .changelog import ChangeLog
from .editor_panel import EditorPanel
from .widgets import info

PREVIEW = (488, 200)


class WiiBannerEditor(EditorPanel):
    display_name = "Wii Banner"

    def __init__(self, parent: tk.Misc, project: ModProject, changelog: ChangeLog):
        super().__init__(parent)
        self._project = project
        self._changelog = changelog
        self._path = Path(files_root_of(project)) / "opening.bnr"
        self._banner: Optional[wb.Banner] = None
        self._dirty = False
        self._photo = None
        self._title_vars: list[tuple[tk.StringVar, tk.StringVar]] = []
        self._build()
        self._load()

    def _build(self) -> None:
        bar = ttk.Frame(self, padding=(8, 8, 8, 4))
        bar.pack(fill="x")
        self._save_button = ttk.Button(bar, text="Save banner", style="Accent.TButton", command=self.save,
                                       state="disabled")
        self._save_button.pack(side="left")
        ttk.Button(bar, text="Revert", command=self._revert).pack(side="left", padx=(6, 0))
        self._status = ttk.Label(bar, text="", style="Muted.TLabel")
        self._status.pack(side="left", padx=(10, 0))
        info(bar, "opening.bnr is what the Wii Menu shows for the disc: the channel title in each Wii language "
                  "(two lines of up to 21 characters) and the pictures of the animated banner and its icon. The "
                  "game itself never reads it. The layout and animation files are kept as they are; replaced "
                  "pictures keep their size and texture format.").pack(side="right")
        body = ttk.Frame(self, padding=8)
        body.pack(fill="both", expand=True)

        titles = ttk.Frame(body)
        titles.pack(side="left", fill="y", padx=(0, 16))
        ttk.Label(titles, text="Channel titles", style="Heading.TLabel").grid(row=0, column=0, columnspan=3,
                                                                              sticky="w")
        for row, language in enumerate(wb.LANGUAGES, start=1):
            ttk.Label(titles, text=language).grid(row=row, column=0, sticky="w", pady=2)
            first, second = tk.StringVar(), tk.StringVar()
            for column, var in ((1, first), (2, second)):
                entry = ttk.Entry(titles, textvariable=var, width=22)
                entry.grid(row=row, column=column, padx=(6, 0), pady=2)
                entry.bind("<FocusOut>", lambda e: self._apply_titles())
                entry.bind("<Return>", lambda e: self._apply_titles())
            self._title_vars.append((first, second))

        pictures = ttk.Frame(body)
        pictures.pack(side="left", fill="both", expand=True)
        ttk.Label(pictures, text="Pictures", style="Heading.TLabel").pack(anchor="w")
        self._tree = ttk.Treeview(pictures, columns=("part", "file", "size"), show="headings", height=14,
                                  selectmode="browse")
        for column, text, width in (("part", "Part", 90), ("file", "Picture", 200), ("size", "Size", 80)):
            self._tree.heading(column, text=text)
            self._tree.column(column, width=width, stretch=False)
        self._tree.pack(anchor="w", pady=(4, 0))
        self._tree.bind("<<TreeviewSelect>>", lambda e: self._show_picture())
        buttons = ttk.Frame(pictures)
        buttons.pack(anchor="w", pady=(6, 0))
        ttk.Button(buttons, text="Export PNG…", command=self._export).pack(side="left")
        ttk.Button(buttons, text="Replace…", command=self._replace).pack(side="left", padx=(4, 0))
        self._canvas = tk.Canvas(pictures, width=PREVIEW[0], height=PREVIEW[1], highlightthickness=0,
                                 background=theme.color("surface_alt"))
        self._canvas.pack(anchor="w", pady=(8, 0))

    # -- data -----------------------------------------------------------------------------
    def _load(self) -> None:
        self._tree.delete(*self._tree.get_children())
        try:
            self._banner = wb.read_banner(self._path.read_bytes())
        except FileNotFoundError:
            self._banner = None
            self._status.config(text="opening.bnr not found; extract the project first.")
            return
        except (OSError, ValueError) as exc:
            self._banner = None
            self._status.config(text=f"Could not read opening.bnr: {exc}")
            return
        for (first, second), (line1, line2) in zip(self._title_vars, self._banner.titles):
            first.set(line1)
            second.set(line2)
        for part in ("banner.bin", "icon.bin"):
            for entry in self._banner.pictures(part):
                size = "?"
                try:
                    info_ = tpl.read_tpl_image_info(io.BytesIO(entry.data))[0]
                    size = f"{info_.width} x {info_.height}"
                except (ValueError, IndexError, AttributeError):
                    pass
                self._tree.insert("", "end", iid=f"{part}|{entry.path}",
                                  values=(part.split(".")[0], entry.path.rsplit("/", 1)[-1], size))
        self._set_dirty(False)
        self._status.config(text=f"{len(self._tree.get_children())} pictures")

    def _selected(self) -> Optional[tuple[str, wb.U8Entry]]:
        selection = self._tree.selection()
        if not selection or self._banner is None:
            return None
        part, path = selection[0].split("|", 1)
        entry = next(e for e in self._banner.part(part) if e.path == path)
        return part, entry

    def _show_picture(self) -> None:
        self._canvas.delete("all")
        chosen = self._selected()
        if chosen is None:
            return
        try:
            image = tpl.read_tpl_images(io.BytesIO(chosen[1].data))[0].convert("RGBA")
        except (ValueError, IndexError):
            return
        image.thumbnail(PREVIEW)
        self._photo = ImageTk.PhotoImage(image)
        self._canvas.create_image(PREVIEW[0] // 2, PREVIEW[1] // 2, image=self._photo)

    def _apply_titles(self) -> None:
        if self._banner is None:
            return
        titles = [(a.get(), b.get()) for a, b in self._title_vars]
        for line in (line for pair in titles for line in pair):
            if len(line) > wb.TITLE_CHARS:
                messagebox.showerror("Title too long", f"A line holds at most {wb.TITLE_CHARS} characters.",
                                     parent=self)
                return
        if titles != self._banner.titles:
            self._banner.titles = titles
            self._set_dirty(True)

    def _export(self) -> None:
        chosen = self._selected()
        if chosen is None:
            return
        name = chosen[1].path.rsplit("/", 1)[-1].replace(".tpl", ".png")
        target = filedialog.asksaveasfilename(parent=self, defaultextension=".png", initialfile=name,
                                              filetypes=[("PNG", "*.png")])
        if target:
            tpl.read_tpl_images(io.BytesIO(chosen[1].data))[0].save(target)

    def _replace(self) -> None:
        chosen = self._selected()
        if chosen is None:
            return
        source = filedialog.askopenfilename(parent=self, filetypes=[("Images", "*.png *.jpg *.bmp"), ("All", "*")])
        if not source:
            return
        part, entry = chosen
        try:
            old = tpl.read_tpl_images(io.BytesIO(entry.data))[0]
            image = Image.open(source).convert("RGBA")
            if image.size != old.size:
                image = image.resize(old.size, Image.LANCZOS)
            self._banner.replace_file(part, entry.path, tpl.replace_image(entry.data, 0, image))
        except (OSError, ValueError) as exc:
            messagebox.showerror("Could not replace the picture", str(exc), parent=self)
            return
        self._set_dirty(True)
        self._show_picture()

    # -- save -----------------------------------------------------------------------------
    def _set_dirty(self, dirty: bool) -> None:
        self._dirty = dirty
        self._save_button.config(state="normal" if dirty else "disabled")
        if dirty:
            self._status.config(text="Unsaved changes")

    def save(self) -> bool:
        if self._banner is None:
            return False
        self._apply_titles()
        try:
            self._project.write_keeping_original(self._path, wb.build_banner(self._banner))
        except (OSError, ValueError) as exc:
            messagebox.showerror("Could not save opening.bnr", str(exc), parent=self)
            return False
        self._changelog.append("opening.bnr", "Saved the Wii banner")
        self._set_dirty(False)
        self._status.config(text="Saved opening.bnr")
        return True

    def _revert(self) -> None:
        if self._dirty and not self._confirm_discard():
            return
        self._load()

    def _confirm_discard(self) -> bool:
        return messagebox.askyesno("Discard changes?", "The banner has unsaved changes. Discard them?", parent=self)
