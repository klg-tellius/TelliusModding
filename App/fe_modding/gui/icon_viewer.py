"""Icons: every generic icon sheet, one icon at a time.

The game draws its small icons - item and weapon icons, menu glyphs, skill
and status badges - from a few TPL sheets cut into a fixed grid:

- ``window/icon.tpl`` (Path of Radiance) / ``window/icon.cms`` (Radiant
  Dawn): image 0 is the 24x24 grid (menu glyphs, then the item icons from
  cell 96: an item's ``icon`` field N is cell 96 + N), image 1 the 32x32
  grid (skills, statuses, affinities; a skill record's icon byte N is cell
  N - 1). Radiant Dawn keeps a squeezed copy
  for 16:9 in ``window/icon_wide.cms`` (18x24 and 24x32 cells, same grid);
  replacing an icon updates both unless told otherwise.
- ``etc/icon.tpl``: a 16x16 grid.
- ``window/cardicon.tpl``: four 32x32 images.
- Radiant Dawn only: ``etc/eventicon.tpl`` and ``etc/terricon.tpl``, the
  32x32 event/terrain markers of the debug map view.

Path of Radiance also bundles ``window/icon.tpl`` in ``system.cmp``; the
build copies the edited loose file in (``ModProject.sync_system_archive``).

Game Data's item and skill forms link here through :meth:`IconViewer.select_icon`
(route ``("asset", "icons", "item:<N>")`` or ``"skill:<N>"``).

An icon is replaced through ``tpl.replace_region``: the rest of the sheet
decodes exactly as before, and the new icon's colors go into the sheet's
spare palette entries.
"""

from __future__ import annotations

import io
import tkinter as tk
from dataclasses import dataclass
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import Optional

from PIL import Image, ImageTk

from ..formats import fe8data, icons, lz10, tpl
from ..game_profile import GAME_DATA, profile_of
from ..games import Game
from ..project import ModProject
from . import theme
from .changelog import ChangeLog
from .editor_panel import EditorPanel

#: The item-icon number of an item record is the cell number minus this.
ITEM_ICON_FIRST_CELL = icons.ITEM_FIRST_CELL
PREVIEW_SIZE = 128
ZOOMS = ("1x", "2x", "3x", "4x")


@dataclass(frozen=True)
class IconSheet:
    label: str
    path: str  # under files/
    image: int
    cell: tuple[int, int]
    wide: Optional[tuple[str, int, tuple[int, int]]] = None  # (path, image, cell) of the 16:9 twin
    item_icons: bool = False  # cell 96 + N is item icon N
    skill_icons: bool = False  # cell N - 1 is skill icon N


SHEETS = {
    Game.PATH_OF_RADIANCE: [
        IconSheet("Items and menu icons", "window/icon.tpl", 0, (24, 24), item_icons=True),
        IconSheet("Skill and status icons", "window/icon.tpl", 1, (32, 32), skill_icons=True),
        IconSheet("Small icons", "etc/icon.tpl", 0, (16, 16)),
        *(IconSheet(f"Card icons {n + 1}", "window/cardicon.tpl", n, (32, 32)) for n in range(4)),
    ],
    Game.RADIANT_DAWN: [
        IconSheet("Items and menu icons", "window/icon.cms", 0, (24, 24), wide=("window/icon_wide.cms", 0, (18, 24))),
        IconSheet("Skill and status icons", "window/icon.cms", 1, (32, 32), wide=("window/icon_wide.cms", 1, (24, 32))),
        IconSheet("Small icons", "etc/icon.tpl", 0, (16, 16)),
        *(IconSheet(f"Card icons {n + 1}", "window/cardicon.tpl", n, (32, 32)) for n in range(4)),
        IconSheet("Event markers (debug)", "etc/eventicon.tpl", 0, (32, 32)),
        IconSheet("Terrain markers (debug)", "etc/terricon.tpl", 0, (32, 32)),
    ],
}


def _is_compressed(path: Path) -> bool:
    return path.suffix.lower() == ".cms"


def _with_backing(image: Image.Image) -> Image.Image:
    backing = Image.new("RGBA", image.size, (128, 128, 128, 255))
    backing.alpha_composite(image.convert("RGBA"))
    return backing


class IconViewer(EditorPanel):
    display_name = "Icons"

    def __init__(self, parent: tk.Misc, project: ModProject, changelog: ChangeLog):
        super().__init__(parent)
        self._project = project
        self._changelog = changelog
        self._files = project.extracted_dir / "files"
        self._sheets = [s for s in SHEETS.get(project.game, []) if (self._files / s.path).is_file()]
        self._data: dict[Path, bytes] = {}  # decoded TPL bytes, edited in place until saved
        self._modified: set[Path] = set()
        self._images: dict[tuple[Path, int], Image.Image] = {}
        self._sheet: Optional[IconSheet] = None
        self._cell: Optional[int] = None
        self._dirty = False
        self._sheet_photo = None
        self._preview_photo = None
        self._item_names, self._skill_names = self._load_names()

        self._build_widgets()
        if self._sheets:
            self._sheet_list.selection_set(0)
            self._select_sheet(0)
        else:
            self._status.config(text="No icon sheets found. Extract the project first.")

    # -- data ---------------------------------------------------------------
    def _load_names(self) -> tuple[dict[int, list[str]], dict[int, list[str]]]:
        """Item and skill icon numbers -> the IIDs/SIDs using them (Path of
        Radiance only: the tables this app reads are FE8Data.bin's)."""
        profile = profile_of(self._project)
        path = profile.path(self._files, "game_data")
        if not profile.supports(GAME_DATA) or not path.is_file():
            return {}, {}
        try:
            data = fe8data.read_fe8data_path(path)
        except Exception:  # noqa: BLE001 - labels are a convenience
            return {}, {}
        items: dict[int, list[str]] = {}
        for item in data.items:
            if item.iid:
                items.setdefault(item.icon, []).append(item.iid.removeprefix("IID_"))
        skills: dict[int, list[str]] = {}
        for skill in data.skills:
            if skill.sid and skill.params[0]:
                skills.setdefault(skill.params[0], []).append(skill.sid.removeprefix("SID_"))
        return items, skills

    def select_icon(self, target: str) -> None:
        """Show one icon: ``item:<N>`` (an item's icon field), ``skill:<N>``
        (a skill's icon byte) or a sheet path (``window/icon.tpl``)."""
        kind, _sep, number = target.partition(":")
        if kind in ("item", "skill") and number.isdigit():
            n = int(number)
            wanted = (lambda s: s.item_icons) if kind == "item" else (lambda s: s.skill_icons)
            cell = icons.item_cell(n) if kind == "item" else icons.skill_cell(n)
        else:
            wanted, cell = (lambda s: s.path == target), None
        index = next((i for i, s in enumerate(self._sheets) if wanted(s)), None)
        if index is None:
            return
        self._sheet_list.selection_clear(0, "end")
        self._sheet_list.selection_set(index)
        self._sheet_list.see(index)
        if self._sheets[index] is not self._sheet:
            self._select_sheet(index)
        if cell is not None:
            cols, rows = self._grid()
            if 0 <= cell < cols * rows:
                self._select_cell(cell)
                self._canvas.update_idletasks()
                cw, ch = self._sheet.cell
                scale = self._scale()
                height = rows * ch * scale
                if height > 0:
                    self._canvas.yview_moveto(max(0.0, (cell // cols) * ch * scale - 40) / height)

    def _tpl_bytes(self, path: Path) -> bytes:
        if path not in self._data:
            raw = path.read_bytes()
            self._data[path] = lz10.decompress(raw) if _is_compressed(path) else raw
        return self._data[path]

    def _image(self, path: Path, index: int) -> Image.Image:
        key = (path, index)
        if key not in self._images:
            self._images[key] = tpl.read_tpl_images(io.BytesIO(self._tpl_bytes(path)))[index].convert("RGBA")
        return self._images[key]

    def _set_bytes(self, path: Path, data: bytes) -> None:
        self._data[path] = data
        self._modified.add(path)
        for key in [k for k in self._images if k[0] == path]:
            del self._images[key]

    # -- layout -------------------------------------------------------------
    def _build_widgets(self) -> None:
        paned = ttk.PanedWindow(self, orient="horizontal")
        paned.pack(fill="both", expand=True)

        left = ttk.Frame(paned, padding=8)
        paned.add(left, weight=0)
        ttk.Label(left, text="Icon sheets").pack(anchor="w")
        self._sheet_list = tk.Listbox(left, exportselection=False, width=26)
        self._sheet_list.pack(fill="both", expand=True, pady=(4, 0))
        for sheet in self._sheets:
            self._sheet_list.insert("end", sheet.label)
        self._sheet_list.bind("<<ListboxSelect>>", self._on_sheet_list)

        middle = ttk.Frame(paned, padding=8)
        paned.add(middle, weight=3)
        top = ttk.Frame(middle)
        top.pack(fill="x")
        self._sheet_info = ttk.Label(top, text="", style="Muted.TLabel")
        self._sheet_info.pack(side="left")
        self._zoom = tk.StringVar(value="2x")
        zoom = ttk.Combobox(top, textvariable=self._zoom, values=ZOOMS, width=4, state="readonly")
        zoom.pack(side="right")
        zoom.bind("<<ComboboxSelected>>", lambda _e: self._draw_sheet())
        ttk.Label(top, text="Zoom").pack(side="right", padx=(0, 6))

        canvas_frame = ttk.Frame(middle)
        canvas_frame.pack(fill="both", expand=True, pady=(6, 0))
        self._canvas = tk.Canvas(canvas_frame, highlightthickness=0, background=theme.color("surface_alt"))
        xbar = ttk.Scrollbar(canvas_frame, orient="horizontal", command=self._canvas.xview)
        ybar = ttk.Scrollbar(canvas_frame, orient="vertical", command=self._canvas.yview)
        self._canvas.configure(xscrollcommand=xbar.set, yscrollcommand=ybar.set)
        self._canvas.grid(row=0, column=0, sticky="nsew")
        ybar.grid(row=0, column=1, sticky="ns")
        xbar.grid(row=1, column=0, sticky="ew")
        canvas_frame.rowconfigure(0, weight=1)
        canvas_frame.columnconfigure(0, weight=1)
        self._canvas.bind("<Button-1>", self._on_click)
        self._canvas.bind("<Motion>", self._on_hover)
        self._canvas.bind("<Leave>", lambda _e: self._hover.config(text=""))
        for key, step in (("<Left>", (-1, 0)), ("<Right>", (1, 0)), ("<Up>", (0, -1)), ("<Down>", (0, 1))):
            self._canvas.bind(key, lambda _e, s=step: self._move(*s))
        theme.on_change(self, lambda: self._canvas.configure(background=theme.color("surface_alt")))
        self._hover = ttk.Label(middle, text="", style="Muted.TLabel")
        self._hover.pack(anchor="w", pady=(4, 0))

        right = ttk.Frame(paned, padding=8)
        paned.add(right, weight=1)
        self._preview = ttk.Label(right, relief="groove")
        self._preview.pack(anchor="w")
        self._title = ttk.Label(right, text="", style="Heading.TLabel")
        self._title.pack(anchor="w", pady=(8, 0))
        self._details = ttk.Label(right, text="", style="Muted.TLabel", justify="left", wraplength=260)
        self._details.pack(anchor="w", pady=(2, 8))

        self._wide_var = tk.BooleanVar(value=True)
        self._wide_check = ttk.Checkbutton(right, text="Also update the widescreen sheet", variable=self._wide_var)

        self._buttons = ttk.Frame(right)
        self._buttons.pack(anchor="w", fill="x")
        self._replace_button = ttk.Button(self._buttons, text="Replace icon...", command=self._replace_icon)
        self._export_button = ttk.Button(self._buttons, text="Export icon...", command=self._export_icon)
        self._replace_button.pack(fill="x")
        self._export_button.pack(fill="x", pady=(4, 0))
        ttk.Separator(right).pack(fill="x", pady=10)
        ttk.Button(right, text="Export whole sheet...", command=self._export_sheet).pack(fill="x")
        ttk.Button(right, text="Replace whole sheet...", command=self._replace_sheet).pack(fill="x", pady=(4, 0))
        self._restore_button = ttk.Button(right, text="Restore original file", command=self._restore_original)
        self._restore_button.pack(fill="x", pady=(4, 0))
        ttk.Separator(right).pack(fill="x", pady=10)
        save_row = ttk.Frame(right)
        save_row.pack(fill="x")
        self._save_button = ttk.Button(save_row, text="Save", command=self._save, state="disabled", style="Accent.TButton")
        self._save_button.pack(side="left")
        self._revert_button = ttk.Button(save_row, text="Discard changes", command=self._revert, state="disabled")
        self._revert_button.pack(side="left", padx=(8, 0))
        self._status = ttk.Label(right, text="", style="Muted.TLabel", wraplength=260, justify="left")
        self._status.pack(anchor="w", pady=(8, 0))

    # -- sheet --------------------------------------------------------------
    def _on_sheet_list(self, _event=None) -> None:
        selection = self._sheet_list.curselection()
        if selection:
            self._select_sheet(selection[0])

    def _select_sheet(self, index: int) -> None:
        self._sheet = self._sheets[index]
        self._cell = None
        if self._sheet.wide:
            self._wide_check.pack(anchor="w", pady=(0, 6), before=self._buttons)
        else:
            self._wide_check.pack_forget()
        self._draw_sheet()
        self._select_cell(0)
        self._refresh_restore()

    def _grid(self) -> tuple[int, int]:
        image = self._image(self._files / self._sheet.path, self._sheet.image)
        cw, ch = self._sheet.cell
        return image.width // cw, image.height // ch

    def _scale(self) -> int:
        return int(self._zoom.get().rstrip("x"))

    def _draw_sheet(self) -> None:
        if self._sheet is None:
            return
        path = self._files / self._sheet.path
        try:
            image = self._image(path, self._sheet.image)
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror("Could not read icon sheet", str(exc), parent=self)
            return
        scale = self._scale()
        shown = _with_backing(image).resize((image.width * scale, image.height * scale), Image.NEAREST)
        self._sheet_photo = ImageTk.PhotoImage(shown)
        canvas = self._canvas
        canvas.delete("all")
        canvas.create_image(0, 0, image=self._sheet_photo, anchor="nw")
        cw, ch = self._sheet.cell
        cols, rows = self._grid()
        line = theme.color("border")
        for c in range(1, cols):
            canvas.create_line(c * cw * scale, 0, c * cw * scale, rows * ch * scale, fill=line)
        for r in range(1, rows):
            canvas.create_line(0, r * ch * scale, cols * cw * scale, r * ch * scale, fill=line)
        canvas.configure(scrollregion=(0, 0, shown.width, shown.height))
        info = tpl.read_tpl_image_info(io.BytesIO(self._tpl_bytes(path)))[self._sheet.image]
        self._sheet_info.config(
            text=f"{self._sheet.path}  -  {cols} x {rows} icons of {cw}x{ch}, {tpl.format_name(info.format)}"
        )
        if self._cell is not None:
            self._draw_selection()

    def _draw_selection(self) -> None:
        self._canvas.delete("selection")
        cols, _rows = self._grid()
        cw, ch = self._sheet.cell
        scale = self._scale()
        x, y = (self._cell % cols) * cw * scale, (self._cell // cols) * ch * scale
        self._canvas.create_rectangle(
            x, y, x + cw * scale, y + ch * scale, outline=theme.color("accent"), width=2, tags="selection"
        )

    def _cell_at(self, event) -> Optional[int]:
        if self._sheet is None:
            return None
        x, y = self._canvas.canvasx(event.x), self._canvas.canvasy(event.y)
        cw, ch = self._sheet.cell
        scale = self._scale()
        cols, rows = self._grid()
        col, row = int(x // (cw * scale)), int(y // (ch * scale))
        if 0 <= col < cols and 0 <= row < rows:
            return row * cols + col
        return None

    def _on_click(self, event) -> None:
        self._canvas.focus_set()
        cell = self._cell_at(event)
        if cell is not None:
            self._select_cell(cell)

    def _on_hover(self, event) -> None:
        cell = self._cell_at(event)
        self._hover.config(text="" if cell is None else self._cell_title(cell) + self._used_by(cell, short=True))

    def _move(self, dx: int, dy: int) -> None:
        if self._cell is None:
            return
        cols, rows = self._grid()
        col = min(max(self._cell % cols + dx, 0), cols - 1)
        row = min(max(self._cell // cols + dy, 0), rows - 1)
        self._select_cell(row * cols + col)

    # -- one icon -------------------------------------------------------------
    def _box(self, cell: int, cell_size: Optional[tuple[int, int]] = None) -> tuple[int, int, int, int]:
        cols, _rows = self._grid()
        cw, ch = cell_size or self._sheet.cell
        x, y = (cell % cols) * cw, (cell // cols) * ch
        return x, y, x + cw, y + ch

    def _cell_title(self, cell: int) -> str:
        cols, _rows = self._grid()
        return f"Icon {cell} (row {cell // cols}, column {cell % cols})"

    def _used_by(self, cell: int, short: bool = False) -> str:
        if self._sheet.skill_icons:
            number = cell + 1
            names = self._skill_names.get(number, [])
            if short:
                return f"  -  skill icon {number}" + (f": {', '.join(names)}" if names else "")
            return (f"Skill icon {number}, used by: " + ", ".join(names)) if names else (
                f"Skill icon {number} (no skill uses it; the skill sheet also holds status icons).")
        if not self._sheet.item_icons or cell < ITEM_ICON_FIRST_CELL:
            return ""
        number = cell - ITEM_ICON_FIRST_CELL
        names = self._item_names.get(number, [])
        if short:
            return f"  -  item icon {number}" + (f": {', '.join(names)}" if names else "")
        if not names:
            return f"Item icon {number} (no item uses it)."
        return f"Item icon {number}, used by: " + ", ".join(names)

    def _select_cell(self, cell: int) -> None:
        self._cell = cell
        self._draw_selection()
        image = self._image(self._files / self._sheet.path, self._sheet.image).crop(self._box(cell))
        scale = max(1, PREVIEW_SIZE // max(image.size))
        self._preview_photo = ImageTk.PhotoImage(
            _with_backing(image).resize((image.width * scale, image.height * scale), Image.NEAREST)
        )
        self._preview.config(image=self._preview_photo)
        self._title.config(text=self._cell_title(cell))
        cw, ch = self._sheet.cell
        lines = [f"{cw} x {ch} pixels"]
        used = self._used_by(cell)
        if used:
            lines.append(used)
        self._details.config(text="\n".join(lines))

    def _ask_image(self, title: str) -> Optional[Image.Image]:
        chosen = filedialog.askopenfilename(
            title=title,
            filetypes=[("Images", "*.png *.gif *.bmp *.jpg *.jpeg *.webp"), ("All files", "*.*")],
            parent=self,
        )
        if not chosen:
            return None
        try:
            return Image.open(chosen).convert("RGBA")
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror("Could not open image", str(exc), parent=self)
            return None

    def _replace_icon(self) -> None:
        if self._sheet is None or self._cell is None:
            return
        cw, ch = self._sheet.cell
        image = self._ask_image(f"Replacement icon ({cw}x{ch}, PNG with transparency; other sizes are stretched)")
        if image is None:
            return
        self._apply(image, self._cell)

    def _replace_sheet(self) -> None:
        if self._sheet is None:
            return
        sheet = self._image(self._files / self._sheet.path, self._sheet.image)
        image = self._ask_image(f"Replacement sheet ({sheet.width}x{sheet.height}; other sizes are stretched)")
        if image is None:
            return
        self._apply(image, None)

    def _apply(self, image: Image.Image, cell: Optional[int]) -> None:
        """Paste ``image`` over one icon (or the whole sheet when ``cell`` is None)."""
        sheet = self._sheet
        path = self._files / sheet.path
        full = self._image(path, sheet.image)
        box = self._box(cell) if cell is not None else (0, 0, full.width, full.height)
        try:
            self._set_bytes(path, tpl.replace_region(self._tpl_bytes(path), sheet.image, box, image))
            if sheet.wide and self._wide_var.get():
                wide_path = self._files / sheet.wide[0]
                if wide_path.is_file():
                    wide_full = self._image(wide_path, sheet.wide[1])
                    wide_box = (
                        self._box(cell, sheet.wide[2]) if cell is not None else (0, 0, wide_full.width, wide_full.height)
                    )
                    self._set_bytes(
                        wide_path, tpl.replace_region(self._tpl_bytes(wide_path), sheet.wide[1], wide_box, image)
                    )
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror("Could not replace the icon", str(exc), parent=self)
            return
        self._mark_dirty()
        self._draw_sheet()
        self._select_cell(self._cell if self._cell is not None else 0)
        what = self._cell_title(cell) if cell is not None else "The whole sheet"
        self._status.config(text=f"{what} replaced - not saved yet.")

    def _export_icon(self) -> None:
        if self._sheet is None or self._cell is None:
            return
        stem = Path(self._sheet.path).stem
        target = filedialog.asksaveasfilename(
            title="Export icon",
            defaultextension=".png",
            initialfile=f"{stem}_{self._sheet.image}_icon{self._cell}.png",
            filetypes=[("PNG image", "*.png")],
            parent=self,
        )
        if target:
            self._image(self._files / self._sheet.path, self._sheet.image).crop(self._box(self._cell)).save(target)
            self._status.config(text=f"Exported {Path(target).name}")

    def _export_sheet(self) -> None:
        if self._sheet is None:
            return
        stem = Path(self._sheet.path).stem
        target = filedialog.asksaveasfilename(
            title="Export whole sheet",
            defaultextension=".png",
            initialfile=f"{stem}_{self._sheet.image}.png",
            filetypes=[("PNG image", "*.png")],
            parent=self,
        )
        if target:
            self._image(self._files / self._sheet.path, self._sheet.image).save(target)
            self._status.config(text=f"Exported {Path(target).name}")

    # -- saving ---------------------------------------------------------------
    def _mark_dirty(self) -> None:
        self._dirty = True
        self._save_button.config(state="normal")
        self._revert_button.config(state="normal")

    def _save(self) -> None:
        saved = []
        for path in sorted(self._modified):
            data = self._data[path]
            try:
                self._project.write_keeping_original(path, lz10.compress(data) if _is_compressed(path) else data)
            except Exception as exc:  # noqa: BLE001
                messagebox.showerror("Could not save", f"{path.name}: {exc}", parent=self)
                return
            saved.append(path.name)
            self._changelog.append(path.name, "Saved (icons replaced)")
        self._modified.clear()
        self._dirty = False
        self._save_button.config(state="disabled")
        self._revert_button.config(state="disabled")
        self._status.config(text="Saved " + ", ".join(saved))
        self._refresh_restore()

    def _revert(self) -> None:
        if not self._confirm_discard():
            return
        self._discard()
        self._status.config(text="Changes discarded.")

    def _discard(self) -> None:
        for path in self._modified:
            self._data.pop(path, None)
            for key in [k for k in self._images if k[0] == path]:
                del self._images[key]
        self._modified.clear()
        self._dirty = False
        self._save_button.config(state="disabled")
        self._revert_button.config(state="disabled")
        if self._sheet is not None:
            self._draw_sheet()
            self._select_cell(self._cell or 0)

    def _sheet_paths(self) -> list[Path]:
        paths = [self._files / self._sheet.path]
        if self._sheet.wide:
            paths.append(self._files / self._sheet.wide[0])
        return paths

    def _originals(self) -> list[Path]:
        if self._sheet is None:
            return []
        return [p for p in self._sheet_paths() if p in self._project.originals_in(p.parent)]

    def _refresh_restore(self) -> None:
        self._restore_button.config(state="normal" if self._originals() else "disabled")

    def _restore_original(self) -> None:
        originals = self._originals()
        if not originals:
            return
        names = ", ".join(p.name for p in originals)
        if not messagebox.askyesno(
            "Restore original?",
            f"Put back the extracted {names}? Every icon replaced in it is lost.",
            parent=self,
        ):
            return
        for path in originals:
            self._project.restore_original(path)
            self._modified.discard(path)
            self._data.pop(path, None)
            for key in [k for k in self._images if k[0] == path]:
                del self._images[key]
            self._changelog.append(path.name, "Restored original")
        if not self._modified:
            self._dirty = False
            self._save_button.config(state="disabled")
            self._revert_button.config(state="disabled")
        self._draw_sheet()
        self._select_cell(self._cell or 0)
        self._refresh_restore()
        self._status.config(text=f"Restored {names}.")

    def _confirm_discard(self) -> bool:
        return messagebox.askyesno("Discard changes?", "Replaced icons have not been saved. Discard them?", parent=self)
