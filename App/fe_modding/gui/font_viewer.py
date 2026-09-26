"""Fonts: view the five game fonts and replace one from a TrueType/OpenType file.

Path of Radiance draws all text from five bitmap fonts (``fe9_font.FONT_FILES``): system for
menus, talk for dialogue, fe_font for the Tellius alphabet, bigkana for the title and file
menus, alpha for the staff roll. An import renders the chosen file into the game font's line
metrics; glyphs the file lacks keep their game bitmaps.

The system font is saved as the LZ10 ``Fonts/system.cms``; the others as loose ``.gcf`` files,
which the build copies into ``system.cmp`` (``ModProject.sync_system_archive``).
"""

from __future__ import annotations

import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import Optional

from PIL import Image, ImageTk

from ..formats import fe9_font, lz10
from ..formats.fe9_font import GameFont, ImportOptions
from ..games import Game
from ..project import ModProject
from . import theme
from .changelog import ChangeLog
from .editor_panel import EditorPanel

USES = {
    "system": "Menus, status, forecast, shops, tutorials, nameplates",
    "fe_font": "The Tellius alphabet (ancient-language lines, #F01)",
    "talk": "Dialogue textboxes and the backlog",
    "bigkana": "Title-menu and file-menu labels (#F03)",
    "alpha": "Staff-roll names (#F04)",
}
SAMPLES = {
    "system": "Ike  Lv 20  HP 42/42  Steel Sword",
    "fe_font": "Leanne! Is it really you?",
    "talk": "Mist, stay back! I'll handle this.",
    "bigkana": "New Game  Continue",
    "alpha": "STAFF  Director",
}
SCALE = 2
BACKDROP = (32, 40, 72, 255)


def render_sample(font: GameFont, text: str, width: int = 560) -> Image.Image:
    height = (font.ascent + font.descent + 12) * max(1, text.count("\n") + 1)
    image = Image.new("RGBA", (width, height), BACKDROP)
    try:
        font.draw(image, text, (8, 6), line_height=font.ascent + font.descent + 6)
    except ValueError:
        pass  # a character with no game encoding; the dialog reports it
    return image


class FontViewer(EditorPanel):
    display_name = "Fonts"

    def __init__(self, parent: tk.Misc, project: ModProject, changelog: ChangeLog):
        super().__init__(parent)
        self._project = project
        self._changelog = changelog
        self._files = project.extracted_dir / "files"
        self._fonts = [(name, self._files / rel) for name, rel in fe9_font.FONT_FILES
                       if project.game == Game.PATH_OF_RADIANCE and (self._files / rel).is_file()]
        self._pending: dict[str, bytes] = {}  # font name -> unsaved GCF bytes
        self._loaded: dict[str, GameFont] = {}
        self._name: Optional[str] = None
        self._dirty = False
        self._photos: dict[str, ImageTk.PhotoImage] = {}  # kept alive while shown
        self._build_widgets()
        if self._fonts:
            self._list.selection_set(self._fonts[0][0])
        else:
            self._status.config(text="No fonts found. Fonts are supported for Path of Radiance projects.")

    # -- data -------------------------------------------------------------------
    def _path(self, name: str) -> Path:
        return dict(self._fonts)[name]

    def _read_disk(self, name: str) -> bytes:
        data = self._path(name).read_bytes()
        return lz10.decompress(data) if self._path(name).suffix.lower() == ".cms" else data

    def _font(self, name: str) -> GameFont:
        if name not in self._loaded:
            self._loaded[name] = GameFont(self._pending.get(name) or self._read_disk(name))
        return self._loaded[name]

    def _state(self, name: str) -> str:
        if name in self._pending:
            return "Unsaved"
        path = self._path(name)
        return "Modified" if path in self._project.originals_in(path.parent) else "Vanilla"

    # -- widgets ------------------------------------------------------------------
    def _build_widgets(self) -> None:
        paned = ttk.PanedWindow(self, orient="horizontal")
        paned.pack(fill="both", expand=True)
        left = ttk.Frame(paned, padding=8)
        paned.add(left, weight=2)
        self._list = ttk.Treeview(left, columns=("state", "use"), show="tree headings", height=6,
                                  selectmode="browse")
        self._list.heading("#0", text="Font")
        self._list.heading("state", text="State")
        self._list.heading("use", text="Used for")
        self._list.column("#0", width=90, stretch=False)
        self._list.column("state", width=70, stretch=False)
        self._list.column("use", width=260)
        for name, _path in self._fonts:
            self._list.insert("", "end", iid=name, text=name, values=(self._state(name), USES[name]))
        self._list.pack(fill="x")
        self._list.bind("<<TreeviewSelect>>", lambda _e: self._select())
        ttk.Label(left, text="Message text switches font with #F00-#F04 (the Font menu of a Line step).\n"
                  "Fonts 1-4 are also bundled in system.cmp; the build refreshes those copies.",
                  style="Muted.TLabel", justify="left").pack(anchor="w", pady=(6, 10))
        self._info = ttk.Label(left, text="", justify="left")
        self._info.pack(anchor="w")

        buttons = ttk.Frame(left)
        buttons.pack(fill="x", pady=(10, 0))
        ttk.Button(buttons, text="Import TrueType/OpenType font...", command=self._import).pack(fill="x")
        ttk.Button(buttons, text="Export sheets as PNG...", command=self._export).pack(fill="x", pady=(4, 0))
        self._restore_button = ttk.Button(buttons, text="Restore original file", command=self._restore)
        self._restore_button.pack(fill="x", pady=(4, 0))
        ttk.Separator(left).pack(fill="x", pady=10)
        row = ttk.Frame(left)
        row.pack(fill="x")
        self._save_button = ttk.Button(row, text="Save", command=self._save, state="disabled", style="Accent.TButton")
        self._save_button.pack(side="left")
        self._revert_button = ttk.Button(row, text="Discard changes", command=self._revert, state="disabled")
        self._revert_button.pack(side="left", padx=(8, 0))
        self._status = ttk.Label(left, text="", style="Muted.TLabel", wraplength=380, justify="left")
        self._status.pack(anchor="w", pady=(8, 0))

        right = ttk.Frame(paned, padding=8)
        paned.add(right, weight=3)
        sample_row = ttk.Frame(right)
        sample_row.pack(fill="x")
        ttk.Label(sample_row, text="Preview text").pack(side="left")
        self._sample = tk.StringVar()
        entry = ttk.Entry(sample_row, textvariable=self._sample)
        entry.pack(side="left", fill="x", expand=True, padx=(6, 0))
        self._sample.trace_add("write", lambda *_: self._draw_sample())
        self._sample_label = ttk.Label(right)
        self._sample_label.pack(anchor="w", pady=(6, 10))

        sheet_row = ttk.Frame(right)
        sheet_row.pack(fill="x")
        ttk.Label(sheet_row, text="Sheet").pack(side="left")
        self._sheet = tk.IntVar(value=0)
        self._sheet_box = ttk.Spinbox(sheet_row, from_=0, to=0, textvariable=self._sheet, width=5,
                                      command=self._draw_sheet, state="readonly")
        self._sheet_box.pack(side="left", padx=(6, 0))
        self._sheet_info = ttk.Label(sheet_row, text="", style="Muted.TLabel")
        self._sheet_info.pack(side="left", padx=(10, 0))
        frame = ttk.Frame(right)
        frame.pack(fill="both", expand=True, pady=(6, 0))
        self._canvas = tk.Canvas(frame, highlightthickness=0, background=theme.color("surface_alt"))
        ybar = ttk.Scrollbar(frame, orient="vertical", command=self._canvas.yview)
        xbar = ttk.Scrollbar(frame, orient="horizontal", command=self._canvas.xview)
        self._canvas.configure(yscrollcommand=ybar.set, xscrollcommand=xbar.set)
        self._canvas.grid(row=0, column=0, sticky="nsew")
        ybar.grid(row=0, column=1, sticky="ns")
        xbar.grid(row=1, column=0, sticky="ew")
        frame.rowconfigure(0, weight=1)
        frame.columnconfigure(0, weight=1)
        theme.on_change(self, lambda: self._canvas.configure(background=theme.color("surface_alt")))

    # -- display --------------------------------------------------------------------
    def _select(self) -> None:
        selection = self._list.selection()
        if not selection:
            return
        self._name = selection[0]
        try:
            font = self._font(self._name)
        except (OSError, ValueError) as exc:
            messagebox.showerror("Could not read font", f"{self._name}: {exc}", parent=self)
            return
        self._sheet_box.configure(to=font.sheet_count - 1)
        self._sheet.set(0)
        self._sample.set(SAMPLES[self._name])
        self._refresh()

    def _refresh(self) -> None:
        name = self._name
        if name is None:
            return
        font = self._font(name)
        size = len(self._pending.get(name) or self._read_disk(name))
        self._info.configure(text=f"{self._path(name).relative_to(self._files).as_posix()}\n"
                                  f"{len(font.glyphs)} glyphs on {font.sheet_count} sheets of "
                                  f"{font.width}x{font.height}\nAscent {font.ascent}, descent {font.descent}\n"
                                  f"{size // 1024} KB uncompressed")
        for font_name, _path in self._fonts:
            self._list.set(font_name, "state", self._state(font_name))
        path = self._path(name)
        self._restore_button.configure(state="normal" if path in self._project.originals_in(path.parent) else "disabled")
        self._draw_sample()
        self._draw_sheet()

    def _draw_sample(self) -> None:
        if self._name is None:
            return
        photo = ImageTk.PhotoImage(render_sample(self._font(self._name), self._sample.get()))
        self._photos["sample"] = photo
        self._sample_label.configure(image=photo)

    def _draw_sheet(self) -> None:
        if self._name is None:
            return
        font = self._font(self._name)
        index = min(max(0, self._sheet.get()), font.sheet_count - 1)
        sheet = font.sheet(index)
        shown = Image.merge("RGBA", (sheet, sheet, sheet, Image.new("L", sheet.size, 255)))
        shown = shown.resize((sheet.width * SCALE, sheet.height * SCALE), Image.NEAREST)
        photo = ImageTk.PhotoImage(shown)
        self._photos["sheet"] = photo
        self._canvas.delete("all")
        self._canvas.create_image(0, 0, image=photo, anchor="nw")
        self._canvas.configure(scrollregion=(0, 0, shown.width, shown.height))
        count = sum(1 for g in font.glyphs.values() if g.sheet == index)
        self._sheet_info.configure(text=f"{count} glyphs")

    # -- actions -------------------------------------------------------------------
    def _import(self) -> None:
        if self._name is None:
            return
        dialog = ImportDialog(self, self._name, self._font(self._name))
        self.wait_window(dialog)
        if dialog.result is None:
            return
        self._pending[self._name] = dialog.result.data
        self._loaded.pop(self._name, None)
        self._dirty = True
        self._save_button.configure(state="normal")
        self._revert_button.configure(state="normal")
        result = dialog.result
        self._status.configure(text=f"{self._name}: {len(result.replaced)} glyphs replaced, "
                                    f"{len(result.added)} added from {dialog.source.name} at {result.size} px. "
                                    "Save to write the font file.")
        self._refresh()

    def _export(self) -> None:
        if self._name is None:
            return
        folder = filedialog.askdirectory(parent=self, title="Export font sheets to")
        if not folder:
            return
        font = self._font(self._name)
        for index in range(font.sheet_count):
            font.sheet(index).save(Path(folder) / f"{self._name}_{index:02d}.png")
        self._status.configure(text=f"Exported {font.sheet_count} sheets of {self._name}.")

    def _save(self) -> None:
        saved = []
        self.configure(cursor="watch")
        self.update_idletasks()
        try:
            for name, data in sorted(self._pending.items()):
                path = self._path(name)
                try:
                    self._project.write_keeping_original(
                        path, lz10.compress(data) if path.suffix.lower() == ".cms" else data)
                except OSError as exc:
                    messagebox.showerror("Could not save", f"{path.name}: {exc}", parent=self)
                    return
                saved.append(path.name)
                self._changelog.append(path.name, "Saved (font imported)")
        finally:
            self.configure(cursor="")
        self._pending.clear()
        self._loaded.clear()
        self._dirty = False
        self._save_button.configure(state="disabled")
        self._revert_button.configure(state="disabled")
        self._status.configure(text="Saved " + ", ".join(saved))
        self._refresh()

    def _revert(self) -> None:
        if not self._confirm_discard():
            return
        self._pending.clear()
        self._loaded.clear()
        self._dirty = False
        self._save_button.configure(state="disabled")
        self._revert_button.configure(state="disabled")
        self._status.configure(text="Changes discarded.")
        self._refresh()

    def _restore(self) -> None:
        name = self._name
        if name is None:
            return
        path = self._path(name)
        if not messagebox.askyesno("Restore original?", f"Put back the extracted {path.name}?", parent=self):
            return
        self._project.restore_original(path)
        self._pending.pop(name, None)
        self._loaded.pop(name, None)
        if not self._pending:
            self._dirty = False
            self._save_button.configure(state="disabled")
            self._revert_button.configure(state="disabled")
        self._changelog.append(path.name, "Restored original")
        self._status.configure(text=f"Restored {path.name}.")
        self._refresh()

    def _confirm_discard(self) -> bool:
        return messagebox.askyesno("Discard changes?", "Imported fonts have not been saved. Discard them?", parent=self)


class ImportDialog(tk.Toplevel):
    """Pick a TrueType/OpenType file and its settings, with a before/after preview."""

    def __init__(self, parent: tk.Misc, name: str, base: GameFont):
        super().__init__(parent)
        self.title(f"Import a font into {name}")
        self.transient(parent.winfo_toplevel())
        self.result: Optional[fe9_font.ImportResult] = None
        self.source: Optional[Path] = None
        self._name, self._base = name, base
        self._pending_job = None
        self._photos = []
        body = ttk.Frame(self, padding=12)
        body.pack(fill="both", expand=True)

        row = ttk.Frame(body)
        row.pack(fill="x")
        ttk.Label(row, text="Font file", width=14).pack(side="left")
        self._file = tk.StringVar()
        ttk.Entry(row, textvariable=self._file, width=50).pack(side="left", fill="x", expand=True)
        ttk.Button(row, text="Browse...", command=self._browse).pack(side="left", padx=(6, 0))

        grid = ttk.Frame(body)
        grid.pack(fill="x", pady=(10, 0))
        self._size = tk.StringVar(value="Auto")
        self._x = tk.IntVar(value=0)
        self._y = tk.IntVar(value=0)
        self._spacing = tk.IntVar(value=0)
        self._antialias = tk.BooleanVar(value=True)
        for column, (label, var, low, high) in enumerate((("Size (px)", self._size, 6, 96),
                                                          ("Move right", self._x, -20, 20),
                                                          ("Move down", self._y, -20, 20),
                                                          ("Extra spacing", self._spacing, -10, 20))):
            ttk.Label(grid, text=label).grid(row=0, column=column, sticky="w", padx=(0, 12))
            values = ["Auto"] + [str(v) for v in range(low, high + 1)] if var is self._size else None
            box = (ttk.Spinbox(grid, textvariable=var, values=values, width=7) if values
                   else ttk.Spinbox(grid, textvariable=var, from_=low, to=high, width=7))
            box.grid(row=1, column=column, sticky="w", padx=(0, 12))
            var.trace_add("write", lambda *_: self._schedule())
        ttk.Checkbutton(grid, text="Smooth edges", variable=self._antialias,
                        command=self._schedule).grid(row=1, column=4, sticky="w")

        chars = ttk.LabelFrame(body, text="Characters", padding=8)
        chars.pack(fill="x", pady=(10, 0))
        self._scope = tk.StringVar(value="all")
        ttk.Radiobutton(chars, text=f"Every character {name} has (glyphs the file lacks are kept)",
                        variable=self._scope, value="all", command=self._schedule).pack(anchor="w")
        only = ttk.Frame(chars)
        only.pack(fill="x")
        ttk.Radiobutton(only, text="Only these:", variable=self._scope, value="only",
                        command=self._schedule).pack(side="left")
        self._only = tk.StringVar(value="ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789")
        ttk.Entry(only, textvariable=self._only).pack(side="left", fill="x", expand=True, padx=(6, 0))
        add = ttk.Frame(chars)
        add.pack(fill="x", pady=(4, 0))
        ttk.Label(add, text="Also add:").pack(side="left")
        self._add = tk.StringVar()
        ttk.Entry(add, textvariable=self._add).pack(side="left", fill="x", expand=True, padx=(6, 0))
        ttk.Label(chars, text="Characters must exist in Shift-JIS (CP932), the game's text encoding; "
                  "accented Latin letters such as é do not.", style="Muted.TLabel").pack(anchor="w", pady=(4, 0))
        for var in (self._only, self._add):
            var.trace_add("write", lambda *_: self._schedule())

        preview = ttk.LabelFrame(body, text="Preview (game font above, import below)", padding=8)
        preview.pack(fill="both", expand=True, pady=(10, 0))
        self._sample = tk.StringVar(value=SAMPLES[name])
        ttk.Entry(preview, textvariable=self._sample).pack(fill="x")
        self._sample.trace_add("write", lambda *_: self._schedule())
        self._before = ttk.Label(preview)
        self._before.pack(anchor="w", pady=(6, 0))
        self._after = ttk.Label(preview)
        self._after.pack(anchor="w", pady=(2, 0))
        self._summary = ttk.Label(preview, text="Choose a font file.", style="Muted.TLabel", wraplength=560,
                                  justify="left")
        self._summary.pack(anchor="w", pady=(6, 0))

        buttons = ttk.Frame(body)
        buttons.pack(fill="x", pady=(10, 0))
        self._ok = ttk.Button(buttons, text="Import", style="Accent.TButton", command=self._accept, state="disabled")
        self._ok.pack(side="right")
        ttk.Button(buttons, text="Cancel", command=self.destroy).pack(side="right", padx=(0, 8))
        self._candidate: Optional[fe9_font.ImportResult] = None
        self._update()
        self.grab_set()

    def _browse(self) -> None:
        chosen = filedialog.askopenfilename(
            parent=self, title="Choose a font file",
            filetypes=[("Font files", "*.ttf *.otf *.ttc"), ("All files", "*.*")])
        if chosen:
            self._file.set(chosen)

    def _import_options(self) -> ImportOptions:
        size = self._size.get().strip()
        return ImportOptions(size=None if size.lower() in ("", "auto") else int(size),
                             characters=self._only.get() if self._scope.get() == "only" else None,
                             add=self._add.get(), antialias=self._antialias.get(),
                             x_offset=self._x.get(), y_offset=self._y.get(), spacing=self._spacing.get())

    def _schedule(self) -> None:
        if self._pending_job is not None:
            self.after_cancel(self._pending_job)
        self._pending_job = self.after(350, self._update)

    def _show(self, label: ttk.Label, font: GameFont, slot: int) -> None:
        photo = ImageTk.PhotoImage(render_sample(font, self._sample.get()))
        self._photos[slot:slot + 1] = [photo]
        label.configure(image=photo)

    def _update(self) -> None:
        self._pending_job = None
        self._photos = [None, None]
        self._show(self._before, self._base, 0)
        self._candidate = None
        self._ok.configure(state="disabled")
        path = Path(self._file.get().strip()) if self._file.get().strip() else None
        if path is None or not path.is_file():
            self._after.configure(image="")
            self._summary.configure(text="Choose a font file.")
            return
        try:
            result = fe9_font.import_truetype(self._base, path, self._import_options())
            font = GameFont(result.data)
        except (OSError, ValueError, tk.TclError) as exc:
            self._after.configure(image="")
            self._summary.configure(text=f"Cannot import: {exc}")
            return
        self._show(self._after, font, 1)
        lines = [f"{result.size} px: {len(result.replaced)} glyphs replaced, {len(result.added)} added."]
        if result.kept:
            lines.append(f"{len(result.kept)} not in the file, kept from the game font"
                         f" (e.g. {''.join(result.kept[:12])}).")
        if result.unencodable:
            lines.append("No game encoding, skipped: " + "".join(result.unencodable[:30]))
        delta = len(result.data) - len(self._base._data)
        if delta:
            lines.append(f"File size {'+' if delta > 0 else ''}{delta // 1024} KB (loaded fonts use game memory).")
        self._summary.configure(text="\n".join(lines))
        if result.replaced or result.added:
            self._candidate = result
            self.source = path
            self._ok.configure(state="normal")

    def _accept(self) -> None:
        if self._pending_job is not None:
            self.after_cancel(self._pending_job)
            self._update()
        if self._candidate is not None:
            self.result = self._candidate
            self.destroy()
