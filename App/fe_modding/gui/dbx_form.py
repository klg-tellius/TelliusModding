"""Typed views of a ``.dbx`` table for the DBX Files page: a **Form** (every
block with its fields, an English note per known key, edit/add/remove a
field, duplicate/remove a block) and a **Layout** (the blocks that have a
``pos`` drawn on the 640 x 480 screen, dragged to move them: the battle
screen, ``system.dbx`` and the ``ztool/`` windows).

Both work on the page's text: each edit parses the current text, changes it
through :class:`~fe_modding.formats.dbx.DbxDoc` (which keeps every other byte)
and hands the result back, so Save, the Text tab and Undo stay the page's.
"""

from __future__ import annotations

import re
import tkinter as tk
from tkinter import messagebox, simpledialog, ttk
from typing import Callable, Optional

from .. import battle_dbx_notes
from ..formats import dbx
from . import theme

SCREEN = (640, 480)
_NUMBER = re.compile(r"-?\d+(?:\.\d+)?")


def _block_label(block: dbx.Block) -> str:
    parts = [p for p in (block.cls, block.name) if p]
    return " ".join(parts) or "(block)"


class DbxForm(ttk.Frame):
    def __init__(self, parent, get_text: Callable[[], str], set_text: Callable[[str], None]):
        super().__init__(parent)
        self._get_text = get_text
        self._set_text = set_text
        self._path = ""
        self._editable = False

        self._note = ttk.Label(self, text="", style="Muted.TLabel", wraplength=640, justify="left")
        self._note.pack(anchor="w", pady=(0, 4))
        frame = ttk.Frame(self)
        frame.pack(fill="both", expand=True)
        self._tree = ttk.Treeview(frame, columns=("value", "note"), selectmode="browse")
        self._tree.heading("#0", text="Block / key")
        self._tree.heading("value", text="Value")
        self._tree.heading("note", text="Note")
        self._tree.column("#0", width=220)
        self._tree.column("value", width=220)
        self._tree.column("note", width=360)
        bar = ttk.Scrollbar(frame, command=self._tree.yview)
        self._tree.configure(yscrollcommand=bar.set)
        self._tree.pack(side="left", fill="both", expand=True)
        bar.pack(side="right", fill="y")
        self._tree.bind("<Double-1>", lambda e: self._edit())
        self._tree.bind("<Return>", lambda e: self._edit())
        self._tree.bind("<Delete>", lambda e: self._remove())

        buttons = ttk.Frame(self)
        buttons.pack(anchor="w", pady=(6, 0))
        self._buttons = []
        for text, command in (("Edit value…", self._edit), ("Add field…", self._add_field),
                              ("Remove", self._remove), ("Duplicate block…", self._duplicate)):
            button = ttk.Button(buttons, text=text, command=command)
            button.pack(side="left", padx=(0, 6))
            self._buttons.append(button)

    # -- showing -----------------------------------------------------------------
    def show(self, path: str, editable: bool) -> None:
        self._path = path or ""
        self._editable = editable
        for button in self._buttons:
            button.configure(state="normal" if editable else "disabled")
        self._note.configure(text=battle_dbx_notes.LIST_NOTES.get(self._path, ""))
        self.refresh()

    def refresh(self, select: Optional[str] = None) -> None:
        select = select or (self._tree.selection() or [None])[0]
        open_blocks = {iid for iid in self._tree.get_children() if self._tree.item(iid, "open")}
        self._tree.delete(*self._tree.get_children())
        doc = dbx.parse(self._get_text())
        blocks = doc.blocks()
        many = len(blocks) > 1
        for block in blocks:
            iid = f"b{block.start}"
            self._tree.insert("", "end", iid=iid, text=_block_label(block),
                              values=("", f"{len(block.fields)} fields"),
                              open=(not many) or iid in open_blocks or len(blocks) <= 3)
            for field in block.fields:
                note = battle_dbx_notes.note(self._path, field.key)
                comment = field.comment.lstrip("#").strip()
                if comment and not note:
                    note = comment
                self._tree.insert(iid, "end", iid=f"f{field.line}", text=field.key, values=(field.value, note))
        if select and self._tree.exists(select):
            self._tree.selection_set(select)
            self._tree.see(select)

    def select_block(self, start: int) -> None:
        iid = f"b{start}"
        if self._tree.exists(iid):
            self._tree.item(iid, open=True)
            self._tree.selection_set(iid)
            self._tree.see(iid)

    # -- edits -----------------------------------------------------------------
    def _selected(self, doc: dbx.DbxDoc):
        """(block, field or None) under the selection."""
        selection = self._tree.selection()
        if not selection:
            return None, None
        iid = selection[0]
        line = int(iid[1:])
        for block in doc.blocks():
            if iid.startswith("b") and block.start == line:
                return block, None
            for field in block.fields:
                if iid.startswith("f") and field.line == line:
                    return block, field
        return None, None

    def _apply(self, doc: dbx.DbxDoc, select: Optional[str]) -> None:
        self._set_text(doc.text)
        self.refresh(select)

    def _edit(self) -> None:
        if not self._editable:
            return
        doc = dbx.parse(self._get_text())
        block, field = self._selected(doc)
        if field is None:
            return
        value = simpledialog.askstring("Edit value", f"{field.key}:", initialvalue=field.value, parent=self)
        if value is None or value == field.value:
            return
        if "\n" in value or "#" in value:
            messagebox.showerror("Edit value", "A value is one line without #.", parent=self)
            return
        doc.set_value(field, value.strip())
        self._apply(doc, f"f{field.line}")

    def _add_field(self) -> None:
        if not self._editable:
            return
        doc = dbx.parse(self._get_text())
        block, field = self._selected(doc)
        if block is None:
            messagebox.showinfo("Add field", "Select a block or a field first.", parent=self)
            return
        entry = simpledialog.askstring("Add field", "Key and value, separated by a space:", parent=self)
        if not entry or not entry.strip():
            return
        key, _, value = entry.strip().partition(" ")
        if "#" in entry or not key:
            messagebox.showerror("Add field", "Give a key, then its value, without #.", parent=self)
            return
        doc.add_field(block, key, value.strip(), after=field)
        line = (field.line if field else (block.fields[-1].line if block.fields else block.start)) + 1
        self._apply(doc, f"f{line}")

    def _remove(self) -> None:
        if not self._editable:
            return
        doc = dbx.parse(self._get_text())
        block, field = self._selected(doc)
        if block is None:
            return
        if field is not None:
            doc.remove_field(field)
            self._apply(doc, f"b{block.start}")
            return
        if not messagebox.askyesno("Remove block", f"Remove the block {_block_label(block)}?", parent=self):
            return
        doc.remove_block(block)
        self._apply(doc, None)

    def _duplicate(self) -> None:
        if not self._editable:
            return
        doc = dbx.parse(self._get_text())
        block, _field = self._selected(doc)
        if block is None:
            return
        name = None
        if block.name is not None:
            name = simpledialog.askstring("Duplicate block", "Name of the copy:", initialvalue=f"{block.name}_2",
                                          parent=self)
            if not name:
                return
        try:
            doc.duplicate_block(block, name.strip() if name else None)
        except dbx.DbxError as exc:
            messagebox.showerror("Duplicate block", str(exc), parent=self)
            return
        self._apply(doc, f"b{block.end + 2}")


class DbxLayout(ttk.Frame):
    """The blocks with a ``pos`` on the 640 x 480 screen; drag one to move it."""

    def __init__(self, parent, get_text: Callable[[], str], set_text: Callable[[str], None],
                 on_select: Callable[[int], None]):
        super().__init__(parent)
        self._get_text = get_text
        self._set_text = set_text
        self._on_select = on_select
        self._editable = False
        self._scale = 1.0
        self._items: dict[int, int] = {}  # canvas rectangle -> block start line
        self._drag: Optional[tuple] = None
        top = ttk.Frame(self)
        top.pack(fill="x", pady=(0, 4))
        self._show_hidden = tk.BooleanVar(value=True)
        ttk.Checkbutton(top, text="Show hidden widgets (show 0)", variable=self._show_hidden,
                        command=self.refresh).pack(side="left")
        self._status = ttk.Label(top, text="", style="Muted.TLabel")
        self._status.pack(side="left", padx=(12, 0))
        self._canvas = tk.Canvas(self, width=SCREEN[0], height=SCREEN[1], highlightthickness=0,
                                 background=theme.color("surface"))
        self._canvas.pack(fill="both", expand=True)
        self._canvas.bind("<Configure>", lambda e: self.refresh())
        self._canvas.bind("<ButtonPress-1>", self._press)
        self._canvas.bind("<B1-Motion>", self._motion)
        self._canvas.bind("<ButtonRelease-1>", self._release)

    @staticmethod
    def has_layout(text: str) -> bool:
        return sum(1 for b in dbx.parse(text).blocks() if b.get("pos") and b.cls != "Layer") >= 2

    def show(self, editable: bool) -> None:
        self._editable = editable
        self.refresh()

    @staticmethod
    def _pair(value: Optional[str]) -> Optional[tuple[float, float]]:
        numbers = _NUMBER.findall(value or "")
        return (float(numbers[0]), float(numbers[1])) if len(numbers) >= 2 else None

    def refresh(self) -> None:
        canvas = self._canvas
        canvas.delete("all")
        self._items.clear()
        width, height = max(canvas.winfo_width(), 200), max(canvas.winfo_height(), 150)
        self._scale = min(width / SCREEN[0], height / SCREEN[1])
        s = self._scale
        canvas.create_rectangle(0, 0, SCREEN[0] * s, SCREEN[1] * s, outline="#888")
        blocks = dbx.parse(self._get_text()).blocks()
        textures = {b.name: b for b in blocks if b.cls == "Texture"}
        shown = 0
        for block in blocks:
            pos = self._pair(block.get("pos"))
            if pos is None or block.cls == "Layer":  # layers group widgets; they are not drawn
                continue
            hidden = (block.get("show") or "").strip() in ("", "0")
            if hidden and not self._show_hidden.get():
                continue
            size = self._pair(block.get("size"))
            if size is None and block.get("texName") in textures:
                size = self._pair(textures[block.get("texName")].get("cellSize"))
            w, h = size if size and size[0] > 0 and size[1] > 0 else (40, 16)
            x, y = pos
            colour = "#7a7a7a" if hidden else "#4aa3df"
            rect = canvas.create_rectangle(x * s, y * s, (x + w) * s, (y + h) * s, outline=colour,
                                           dash=(3, 3) if hidden else None, width=2)
            canvas.create_text(x * s + 3, y * s + 2, text=block.name or block.cls or "", anchor="nw",
                               fill=colour, font=("Segoe UI", 8))
            self._items[rect] = block.start
            shown += 1
        self._status.configure(text=f"{shown} widgets. Drag one to move it." if self._editable else f"{shown} widgets.")

    def _hit(self, event) -> Optional[int]:
        for item in reversed(self._canvas.find_overlapping(event.x, event.y, event.x, event.y)):
            if item in self._items:
                return item
        return None

    def _press(self, event) -> None:
        item = self._hit(event)
        if item is None:
            return
        self._on_select(self._items[item])
        if self._editable:
            self._drag = (item, event.x, event.y)

    def _motion(self, event) -> None:
        if self._drag is None:
            return
        item, x, y = self._drag
        dx, dy = event.x - x, event.y - y
        self._canvas.move(item, dx, dy)
        self._drag = (item, event.x, event.y)

    def _release(self, event) -> None:
        if self._drag is None:
            return
        item, _x, _y = self._drag
        self._drag = None
        x0, y0, _x1, _y1 = self._canvas.coords(item)
        start = self._items[item]
        doc = dbx.parse(self._get_text())
        block = next(b for b in doc.blocks() if b.start == start)
        field = next(f for f in block.fields if f.key == "pos")
        old = field.value
        numbers = _NUMBER.findall(old)
        new_xy = [round(x0 / self._scale), round(y0 / self._scale)]
        if [round(float(n)) for n in numbers[:2]] == new_xy:
            self.refresh()
            return
        separator = ", " if ", " in old else ","
        rest = numbers[2:]
        doc.set_value(field, separator.join(str(v) for v in new_xy + rest))
        self._set_text(doc.text)
        self.refresh()
        self._on_select(start)
