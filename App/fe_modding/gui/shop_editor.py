"""Shops editor: one chapter's armory, vendor and forge in
``shop/shopitem_<n|h|m>.bin`` (see :mod:`fe_modding.formats.shop`).

The three files hold every chapter's shops, so this panel loads them once
and keeps its edits when the chapter page switches chapter; one Save writes
every difficulty file that changed. The armory and vendor are ordered lists
of items; the forge is a fixed grid of 5 rows by 9 base columns where each
cell names the item offered (or nothing). Chapter ``NN``'s shops are the
sections ending in ``CNN``; a chapter without them (an added chapter) can
get a copy of another chapter's.

The armory and vendor lists show each item's icon (``window/icon.tpl``, see
:mod:`fe_modding.formats.icons`) and price. The price is not a shop setting:
the game charges an item's cost per use times its uses, both in the item's
``FE8Data.bin`` record, so **Edit price...** changes that cost in the shared
:class:`~.fe8_session.Fe8DataSession` - the same price in every chapter and
difficulty - after warning so. Save writes FE8Data.bin too when it has
unsaved edits.

Path of Radiance only: Radiant Dawn's shop files use a different layout.
"""

from __future__ import annotations

import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk
from typing import Callable, Optional

from PIL import ImageTk

from ..formats import fe8data, icons, shop
from ..game_profile import SHOPS, profile_of
from ..project import ModProject
from .changelog import ChangeLog
from .editor_panel import EditorPanel

NONE_LABEL = "(none)"
LIST_KINDS = ("W", "I")
KIND_HINTS = {"W": "Weapons sold at the base's armory.", "I": "Staves and consumables sold at the vendor."}


class ShopEditor(EditorPanel):
    display_name = "Shops"

    def __init__(self, parent: tk.Misc, project: ModProject, changelog: ChangeLog,
                 index_provider: Callable[[], object] = lambda: None,
                 session_provider: Callable[[], object] = lambda: None):
        super().__init__(parent)
        self._project = project
        self._changelog = changelog
        self._index_provider = index_provider
        self._session_provider = session_provider
        self._folder = profile_of(project).shop_folder(project.extracted_dir / "files")
        self._docs: dict[str, shop.ShopDocument] = {}
        self._edited: set[str] = set()
        self._loaded = False
        self._chapter: Optional[int] = None
        self._difficulty = "n"
        self._dirty = False
        self._labels: dict[str, str] = {}  # IID -> "Name (IID)"
        self._by_label: dict[str, str] = {}
        self._forge_labels: dict[str, str] = {}  # IID -> its name alone when no other item shares it
        self._by_forge_label: dict[str, str] = {}
        self._prices: dict[str, int] = {}
        self._items: dict[str, object] = {}  # IID -> FE8Data.bin ItemEntry
        self._icon_images: list = []
        self._icon_stamp: Optional[int] = None
        self._icon_photos: dict[int, ImageTk.PhotoImage] = {}
        self._subscribed = None  # the FE8Data session whose changes re-read the prices
        self._build_widgets()

    # -- layout ---------------------------------------------------------------------------
    def _build_widgets(self) -> None:
        bar = ttk.Frame(self, padding=(8, 8, 8, 4))
        bar.pack(fill="x")
        ttk.Label(bar, text="Difficulty").pack(side="left")
        self._difficulty_var = tk.StringVar(value=shop.DIFFICULTY_NAMES["n"])
        self._difficulty_box = ttk.Combobox(bar, textvariable=self._difficulty_var, state="readonly", width=16,
                                            values=list(shop.DIFFICULTY_NAMES.values()))
        self._difficulty_box.pack(side="left", padx=(6, 12))
        self._difficulty_box.bind("<<ComboboxSelected>>", lambda e: self._set_difficulty())
        self._save_button = ttk.Button(bar, text="Save Shops", style="Accent.TButton", command=self._save,
                                       state="disabled")
        self._save_button.pack(side="left")
        self._copy_button = ttk.Button(bar, text="Copy to other difficulties", command=self._copy_to_difficulties,
                                       state="disabled")
        self._copy_button.pack(side="left", padx=(6, 0))
        self._status = ttk.Label(bar, text="", style="Muted.TLabel")
        self._status.pack(side="left", padx=(10, 0))

        self._message = ttk.Label(self, text="", style="Muted.TLabel", wraplength=900, justify="left",
                                  padding=(8, 4))
        self._message.pack(fill="x")
        self._add_frame = ttk.Frame(self, padding=(8, 0))
        self._add_frame.pack(fill="x")
        self._add_button = ttk.Button(self._add_frame, text="", command=self._add_chapter_shops)

        self._body = ttk.Frame(self, padding=(8, 4, 8, 8))
        self._body.pack(fill="both", expand=True)
        forge = ttk.Frame(self._body)
        forge.pack(side="bottom", fill="x", pady=(14, 0))
        lists = ttk.Frame(self._body)
        lists.pack(fill="both", expand=True)
        self._lists: dict[str, ttk.Treeview] = {}
        self._pickers: dict[str, tk.StringVar] = {}
        self._picker_boxes: list[ttk.Combobox] = []
        self._counts: dict[str, ttk.Label] = {}
        for column, kind in enumerate(LIST_KINDS):
            frame = ttk.Frame(lists, padding=(0 if column == 0 else 12, 0, 0, 0))
            frame.grid(row=0, column=column, sticky="nsew")
            lists.columnconfigure(column, weight=1)
            head = ttk.Frame(frame)
            head.pack(fill="x")
            ttk.Label(head, text=shop.SHOP_KIND_NAMES[kind], style="Heading.TLabel").pack(side="left")
            self._counts[kind] = ttk.Label(head, text="", style="Muted.TLabel")
            self._counts[kind].pack(side="left", padx=(8, 0))
            ttk.Label(frame, text=KIND_HINTS[kind], style="Muted.TLabel").pack(anchor="w")
            tree = ttk.Treeview(frame, columns=("iid", "price"), show="tree headings", height=8,
                                selectmode="browse")
            tree.heading("#0", text="Item")
            tree.column("#0", width=190, anchor="w")
            for col, text, width, anchor in (("iid", "ID", 150, "w"), ("price", "Price", 70, "e")):
                tree.heading(col, text=text)
                tree.column(col, width=width, anchor=anchor, stretch=col != "price")
            tree.pack(fill="both", expand=True, pady=(4, 0))
            tree.bind("<Delete>", lambda e, k=kind: self._remove(k))
            tree.bind("<Double-1>", lambda e, k=kind: self._edit_price(k))
            self._lists[kind] = tree
            buttons = ttk.Frame(frame)
            buttons.pack(fill="x", pady=(4, 0))
            ttk.Button(buttons, text="▲", width=3, command=lambda k=kind: self._move(k, -1)).pack(side="left")
            ttk.Button(buttons, text="▼", width=3, command=lambda k=kind: self._move(k, 1)).pack(side="left",
                                                                                                padx=(4, 0))
            ttk.Button(buttons, text="Remove", command=lambda k=kind: self._remove(k)).pack(side="left", padx=(8, 0))
            ttk.Button(buttons, text="Edit price...", command=lambda k=kind: self._edit_price(k)).pack(
                side="left", padx=(8, 0))
            add = ttk.Frame(frame)
            add.pack(fill="x", pady=(4, 0))
            var = tk.StringVar()
            box = ttk.Combobox(add, textvariable=var, width=34)
            box.pack(side="left", fill="x", expand=True)
            box.bind("<Return>", lambda e, k=kind: self._add(k))
            box.bind("<<ComboboxSelected>>", lambda e, k=kind: self._add(k))
            ttk.Button(add, text="Add", command=lambda k=kind: self._add(k)).pack(side="left", padx=(6, 0))
            self._pickers[kind] = var
            self._picker_boxes.append(box)

        ttk.Label(forge, text="Forge", style="Heading.TLabel").pack(anchor="w")
        ttk.Label(forge, style="Muted.TLabel", wraplength=900, justify="left", text=(
            "Each row is a weapon family (Swords, Lances, etc.); each fixed column is a base choice "
            "(Iron, Slim, Steel, etc.). At their intersection, choose the item the player can forge. "
            "(none) removes that choice. This table is separate for each chapter and difficulty. "
            "Changing a cell changes the offered item, not its stats or price; click Save Shops to write it.")
                  ).pack(anchor="w")
        grid = ttk.Frame(forge)
        grid.pack(anchor="w", pady=(4, 0))
        for c, base in enumerate(shop.FORGE_BASES):
            ttk.Label(grid, text=shop.FORGE_BASE_NAMES[base]).grid(row=0, column=c + 1, sticky="w", padx=2)
        self._forge_vars: list[tk.StringVar] = []
        self._forge_boxes: list[ttk.Combobox] = []
        for r, row_name in enumerate(shop.FORGE_ROW_NAMES):
            ttk.Label(grid, text=row_name).grid(row=r + 1, column=0, sticky="w", padx=(0, 6), pady=1)
            for c in range(len(shop.FORGE_BASES)):
                var = tk.StringVar()
                box = ttk.Combobox(grid, textvariable=var, state="readonly", width=14)
                box.grid(row=r + 1, column=c + 1, padx=2, pady=1)
                cell = r * len(shop.FORGE_BASES) + c
                box.bind("<<ComboboxSelected>>", lambda e, i=cell: self._set_forge(i))
                self._forge_vars.append(var)
                self._forge_boxes.append(box)

    # -- loading ------------------------------------------------------------------------------
    def _path(self, difficulty: str) -> Path:
        return self._folder / shop.DIFFICULTY_FILES[difficulty]

    def _load(self) -> None:
        self._loaded = True
        self._docs = {}
        if not profile_of(self._project).supports(SHOPS):
            return
        for difficulty in shop.DIFFICULTY_FILES:
            path = self._path(difficulty)
            if not path.is_file():
                continue
            try:
                self._docs[difficulty] = shop.parse_shop(path.read_bytes())
            except Exception as exc:  # noqa: BLE001
                messagebox.showerror("Could not read shops", f"{path.name}: {exc}", parent=self)
        self._edited = set()
        self._dirty = False

    def _refresh_catalog(self) -> None:
        """Item choices: every IID in FE8Data.bin (with unsaved edits), named
        from the project index when it's ready."""
        session = self._session_provider()
        index = self._index_provider()
        names = getattr(index, "item_names", {}) or {}
        items = session.fe8.items if session is not None and session.available else []
        if session is not None and session is not self._subscribed:
            session.subscribe(self._on_session_changed)
            self._subscribed = session
        self._items = {it.iid: it for it in items if it.iid}
        self._prices = {it.iid: it.cost * it.uses for it in items if it.iid}
        self._weapon = {it.iid: it.weapon_type for it in items if it.iid}
        iids = sorted(self._prices, key=lambda i: (names.get(i) or i).casefold())
        self._labels = {iid: f"{names[iid]} ({iid})" if names.get(iid) else iid for iid in iids}
        self._by_label = {label: iid for iid, label in self._labels.items()}
        named = [names.get(iid) for iid in iids]
        self._forge_labels = {iid: name if name and named.count(name) == 1 else self._labels[iid]
                              for iid, name in zip(iids, named)}
        self._by_forge_label = {label: iid for iid, label in self._forge_labels.items()}
        labels = list(self._labels.values())
        for box in self._picker_boxes:
            box["values"] = labels
        for box in self._forge_boxes:
            box["values"] = [NONE_LABEL] + list(self._forge_labels.values())

    def _label(self, value) -> str:
        if not value:
            return NONE_LABEL
        return self._labels.get(value, value)

    def _iid_from(self, text: str) -> str:
        text = text.strip()
        if text in self._by_label:
            return self._by_label[text]
        if text.startswith("(") or not text:
            raise ValueError("Pick an item.")
        if text.endswith(")") and "(" in text:
            text = text[text.rindex("(") + 1:-1]
        if text not in self._prices:
            raise ValueError(f"{text!r} isn't an item ID in FE8Data.bin.")
        return text

    # -- chapter page -------------------------------------------------------------------------
    def refresh_chapter_list(self) -> None:
        """Nothing to re-scan: the shop files hold every chapter."""

    def select_chapter(self, chapter_id: Optional[str]) -> None:
        if not self._loaded:
            self._load()
        self._chapter = int(chapter_id) if chapter_id and chapter_id.isdigit() else None
        self._refresh_catalog()
        self._render()

    def _doc(self) -> Optional[shop.ShopDocument]:
        return self._docs.get(self._difficulty)

    def _sections(self) -> dict[str, shop.ShopSection]:
        doc = self._doc()
        if doc is None or self._chapter is None:
            return {}
        return {kind: s for kind in shop.SHOP_KINDS if (s := doc.shop(kind, self._chapter)) is not None}

    def _render(self) -> None:
        sections = self._sections()
        self._add_button.pack_forget()
        if not profile_of(self._project).supports(SHOPS):
            message = profile_of(self._project).unavailable(SHOPS)
        elif not self._docs:
            message = "No shop files found (shop/shopitem_n.bin). Extract the project first."
        elif self._doc() is None:
            message = f"{shop.DIFFICULTY_FILES[self._difficulty]} is missing."
        elif self._chapter is None:
            message = ""
        elif len(sections) < len(shop.SHOP_KINDS):
            message = (f"Chapter {self._chapter:02d} has no shops in {shop.DIFFICULTY_FILES[self._difficulty]}: "
                       "the base shows an empty armory and vendor and the forge's built-in list.")
            if self._chapter <= 99:
                template = self._template_chapter()
                self._add_button.configure(text=f"Add shops for chapter {self._chapter:02d}" + (
                    f" (copy of chapter {template:02d})" if template is not None else ""))
                self._add_button.pack(anchor="w", pady=(0, 6))
        else:
            message = (f"Chapter {self._chapter:02d}'s base shops in {shop.DIFFICULTY_FILES[self._difficulty]} "
                       f"(sections …_C{self._chapter:02d}). Easy uses the Normal file.")
        self._message.configure(text=message)
        editable = len(sections) == len(shop.SHOP_KINDS)
        if editable:
            self._body.pack(fill="both", expand=True)
        else:
            self._body.pack_forget()
        self._copy_button.configure(state="normal" if editable and len(self._docs) > 1 else "disabled")
        for kind in LIST_KINDS:
            tree = self._lists[kind]
            tree.delete(*tree.get_children())
            section = sections.get(kind)
            for i, iid in enumerate(section.items if section else []):
                price = self._prices.get(iid)
                photo = self._icon_photo(iid)
                tree.insert("", "end", iid=str(i), text=self._item_name(iid), image=photo if photo is not None else "",
                            values=(iid, "" if price is None else price))
            count = len(section.items) if section else 0
            self._counts[kind].configure(text=f"{count} item{'s' if count != 1 else ''}")
        forge = sections.get("F")
        cells = shop.forge_cells(forge) if forge else []
        for i, var in enumerate(self._forge_vars):
            item = cells[i][0] if i < len(cells) else None
            var.set("" if item is None else self._forge_labels.get(item, item) if item else NONE_LABEL)
        self._update_status()

    def _item_name(self, iid) -> str:
        """The item's English name, or its ID when the index has none."""
        label = self._labels.get(iid, iid)
        return label[:label.rindex(" (")] if label.endswith(")") and " (" in label else str(iid)

    def _icons(self) -> list:
        """The images of window/icon.tpl, re-read when the file changes."""
        path = icons.icon_path(self._project.extracted_dir / "files")
        try:
            stamp = path.stat().st_mtime_ns
        except OSError:
            return []
        if stamp != self._icon_stamp:
            try:
                self._icon_images = icons.read_icon_images(path.read_bytes())
            except Exception:  # noqa: BLE001 - icons are a convenience
                self._icon_images = []
            self._icon_stamp = stamp
            self._icon_photos = {}
        return self._icon_images

    def _icon_photo(self, iid) -> Optional[ImageTk.PhotoImage]:
        item = self._items.get(iid)
        if item is None:
            return None
        images = self._icons()
        if item.icon not in self._icon_photos:
            image = icons.item_icon(images, item.icon) if images else None
            if image is None:
                return None
            try:
                self._icon_photos[item.icon] = ImageTk.PhotoImage(image)
            except tk.TclError:
                return None
        return self._icon_photos[item.icon]

    def _session_dirty(self) -> bool:
        session = self._session_provider()
        return bool(session is not None and session.dirty)

    def _update_status(self) -> None:
        fe8_dirty = self._session_dirty()
        self._save_button.configure(state="normal" if self._dirty or fe8_dirty else "disabled")
        names = [shop.DIFFICULTY_NAMES[d] for d in shop.DIFFICULTY_FILES if d in self._edited and self._dirty]
        if fe8_dirty:
            names.append("FE8Data.bin")
        self._status.configure(text=f"Unsaved changes ({', '.join(names)})" if names else "")

    def _on_session_changed(self, source) -> None:
        """FE8Data.bin changed or was saved (here or on another page): re-read names, icons and prices."""
        if source is self or not self._loaded:
            return
        try:
            self._refresh_catalog()
            self._render()
        except tk.TclError:
            pass

    def _set_difficulty(self) -> None:
        names = {v: k for k, v in shop.DIFFICULTY_NAMES.items()}
        self._difficulty = names.get(self._difficulty_var.get(), "n")
        self._render()

    # -- edits ----------------------------------------------------------------------------------
    def _changed(self, difficulties, log_text: str) -> None:
        self._edited.update(difficulties)
        self._dirty = True
        self._changelog.append(f"Chapter {self._chapter:02d}", log_text)
        self._render()

    def _where(self, kind: str) -> str:
        return f"{shop.SHOP_KIND_NAMES[kind]} ({shop.DIFFICULTY_NAMES[self._difficulty]})"

    def _selected(self, kind: str) -> Optional[int]:
        selection = self._lists[kind].selection()
        return int(selection[0]) if selection else None

    def _select(self, kind: str, index: int) -> None:
        tree = self._lists[kind]
        if tree.exists(str(index)):
            tree.selection_set(str(index))
            tree.see(str(index))

    def _add(self, kind: str) -> None:
        section = self._sections().get(kind)
        if section is None:
            return
        try:
            iid = self._iid_from(self._pickers[kind].get())
        except ValueError as exc:
            messagebox.showerror("Add item", str(exc), parent=self)
            return
        if iid in section.items:
            messagebox.showinfo("Add item", f"{self._label(iid)} is already sold here.", parent=self)
            return
        at = self._selected(kind)
        at = len(section.items) if at is None else at + 1
        section.items.insert(at, iid)
        self._pickers[kind].set("")
        self._changed([self._difficulty], f"{self._where(kind)}: added {iid}")
        self._select(kind, at)

    def _remove(self, kind: str) -> None:
        section = self._sections().get(kind)
        index = self._selected(kind)
        if section is None or index is None:
            return
        iid = section.items.pop(index)
        self._changed([self._difficulty], f"{self._where(kind)}: removed {iid}")
        self._select(kind, min(index, len(section.items) - 1))

    def _move(self, kind: str, step: int) -> None:
        section = self._sections().get(kind)
        index = self._selected(kind)
        if section is None or index is None or not 0 <= index + step < len(section.items):
            return
        items = section.items
        items[index], items[index + step] = items[index + step], items[index]
        self._changed([self._difficulty], f"{self._where(kind)}: moved {items[index + step]}")
        self._select(kind, index + step)

    def _set_forge(self, cell: int) -> None:
        section = self._sections().get("F")
        if section is None:
            return
        text = self._forge_vars[cell].get()
        iid = 0 if text == NONE_LABEL else self._by_forge_label.get(text, 0)
        if section.items[2 * cell] == iid:
            return
        shop.set_forge_item(section, cell, iid)
        row, base = divmod(cell, len(shop.FORGE_BASES))
        where = f"{shop.FORGE_ROW_NAMES[row]} / {shop.FORGE_BASE_NAMES[shop.FORGE_BASES[base]]}"
        self._changed([self._difficulty], f"{self._where('F')}: {where} = {iid or 'none'}")

    def _edit_price(self, kind: str) -> None:
        section = self._sections().get(kind)
        index = self._selected(kind)
        if section is None or index is None:
            return
        iid = section.items[index]
        session = self._session_provider()
        item = self._items.get(iid)
        if session is None or not session.available or item is None:
            messagebox.showerror("Edit price", f"{iid} isn't an item in FE8Data.bin.", parent=self)
            return
        if item.uses == 0:
            messagebox.showinfo("Edit price", f"{self._item_name(iid)} has 0 uses, so its price (cost per use x uses) "
                                              "is always 0. Give it uses in Game Data › Items first.", parent=self)
            return
        dialog = _PriceDialog(self, self._item_name(iid), iid, item, self._icon_photo(iid))
        self.wait_window(dialog)
        cost = dialog.result
        if cost is None or cost == item.cost:
            return
        try:
            session.data = fe8data.patch_item_field(session.data, item.index, "cost", cost)
        except ValueError as exc:
            messagebox.showerror("Edit price", str(exc), parent=self)
            return
        old = item.cost * item.uses
        self._changelog.append("FE8Data.bin", f"{iid}: price {old} -> {cost * item.uses} "
                                              f"(cost per use {item.cost} -> {cost}), every chapter")
        session.changed(self)
        self._refresh_catalog()
        self._render()
        self._select(kind, index)

    def _template_chapter(self) -> Optional[int]:
        doc = self._doc()
        chapters = [c for c in doc.chapters() if all(doc.shop(k, c) for k in shop.SHOP_KINDS)] if doc else []
        below = [c for c in chapters if c < (self._chapter or 0)]
        return max(below) if below else (chapters[-1] if chapters else None)

    def _add_chapter_shops(self) -> None:
        if self._chapter is None:
            return
        template = self._template_chapter()
        changed = []
        try:
            for difficulty, doc in self._docs.items():
                if not any(doc.shop(k, self._chapter) for k in shop.SHOP_KINDS):
                    shop.add_chapter(doc, self._chapter, template)
                    changed.append(difficulty)
        except ValueError as exc:
            messagebox.showerror("Add shops", str(exc), parent=self)
            return
        source = f" from chapter {template:02d}" if template is not None else ""
        self._changed(changed, f"Added shops for chapter {self._chapter:02d}{source}")

    def _copy_to_difficulties(self) -> None:
        doc = self._doc()
        others = [d for d in self._docs if d != self._difficulty]
        if doc is None or self._chapter is None or not others:
            return
        names = " and ".join(shop.DIFFICULTY_NAMES[d] for d in others)
        if not messagebox.askyesno(
                "Copy shops?", f"Replace chapter {self._chapter:02d}'s armory, vendor and forge in {names} "
                               f"with the {shop.DIFFICULTY_NAMES[self._difficulty]} ones?", parent=self):
            return
        for difficulty in others:
            target = self._docs[difficulty]
            if not any(target.shop(k, self._chapter) for k in shop.SHOP_KINDS):
                shop.add_chapter(target, self._chapter)
            for kind in shop.SHOP_KINDS:
                source, dest = doc.shop(kind, self._chapter), target.shop(kind, self._chapter)
                if source is not None and dest is not None:
                    dest.items = list(source.items)
        self._changed(others, f"Copied chapter {self._chapter:02d} shops "
                              f"from {shop.DIFFICULTY_NAMES[self._difficulty]} to {names}")

    # -- save -------------------------------------------------------------------------------------
    def save(self) -> bool:
        return self._save()

    def _save(self) -> bool:
        saved = []
        try:
            for difficulty in sorted(self._edited):
                self._project.write_keeping_original(self._path(difficulty),
                                                     shop.build_shop(self._docs[difficulty]))
                saved.append(shop.DIFFICULTY_FILES[difficulty])
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror("Could not save shops", str(exc), parent=self)
            return False
        if saved:
            self._changelog.append("Shops", f"Saved {', '.join(saved)}")
        self._edited = set()
        self._dirty = False
        if self._session_dirty():
            try:
                self._session_provider().save()  # item prices; also any other page's FE8Data.bin edits
            except OSError as exc:
                messagebox.showerror("Could not save FE8Data.bin", str(exc), parent=self)
                self._update_status()
                return False
            saved.append("FE8Data.bin")
        self._update_status()
        self._status.configure(text=f"Saved {', '.join(saved)}" if saved else "")
        return True

    def _confirm_discard(self) -> bool:
        if not messagebox.askyesno("Discard changes?", "The shops have unsaved changes. Discard them?",
                                   icon="warning", parent=self):
            return False
        self._load()
        self._render()
        return True


class _PriceDialog(tk.Toplevel):
    """Asks for an item's new price; ``result`` is the new cost per use, or None."""

    def __init__(self, parent: tk.Misc, name: str, iid: str, item, photo):
        super().__init__(parent)
        self.title("Edit price")
        self.transient(parent.winfo_toplevel())
        self.resizable(False, False)
        self.result: Optional[int] = None
        self._item = item
        body = ttk.Frame(self, padding=14)
        body.pack(fill="both", expand=True)
        head = ttk.Frame(body)
        head.pack(fill="x")
        if photo is not None:
            ttk.Label(head, image=photo).pack(side="left", padx=(0, 8))
        ttk.Label(head, text=f"{name} ({iid})" if name != iid else iid, style="Heading.TLabel").pack(side="left")
        ttk.Label(body, wraplength=420, justify="left", style="Warn.TLabel", text=(
            "Warning: an item has a single price for the whole game, not one per chapter. It is stored in "
            "FE8Data.bin (cost per use x uses), so changing it changes this item's price in every chapter's "
            "shops, on every difficulty, and wherever else the game uses it.")).pack(anchor="w", pady=(10, 8))
        form = ttk.Frame(body)
        form.pack(fill="x")
        ttk.Label(form, text="Price").grid(row=0, column=0, sticky="w")
        self._price_var = tk.StringVar(value=str(item.cost * item.uses))
        entry = ttk.Entry(form, textvariable=self._price_var, width=10)
        entry.grid(row=0, column=1, sticky="w", padx=(8, 0))
        self._note = ttk.Label(form, style="Muted.TLabel")
        self._note.grid(row=1, column=0, columnspan=2, sticky="w", pady=(4, 0))
        self._price_var.trace_add("write", lambda *_: self._update_note())
        self._update_note()
        buttons = ttk.Frame(body)
        buttons.pack(fill="x", pady=(12, 0))
        ttk.Button(buttons, text="Cancel", command=self.destroy).pack(side="right")
        self._ok = ttk.Button(buttons, text="Change price everywhere", style="Accent.TButton", command=self._accept)
        self._ok.pack(side="right", padx=(0, 6))
        entry.bind("<Return>", lambda e: self._accept())
        self.bind("<Escape>", lambda e: self.destroy())
        entry.focus_set()
        entry.select_range(0, "end")
        try:
            self.grab_set()
        except tk.TclError:
            pass

    def _cost(self) -> Optional[int]:
        """The cost per use closest to the typed price, or None when it isn't a price."""
        try:
            price = int(self._price_var.get().strip())
        except ValueError:
            return None
        if price < 0:
            return None
        uses = self._item.uses
        cost = (price + uses // 2) // uses
        return cost if cost <= 0xFFFF else None

    def _update_note(self) -> None:
        uses, cost = self._item.uses, self._cost()
        if cost is None:
            text = f"Enter a whole number up to {0xFFFF * uses}."
        else:
            text = f"{uses} uses x {cost} per use = {cost * uses}"
            try:
                if cost * uses != int(self._price_var.get().strip()):
                    text += f" (the price must be a multiple of {uses})"
            except ValueError:
                pass
        self._note.configure(text=text)

    def _accept(self) -> None:
        cost = self._cost()
        if cost is None:
            self.bell()
            return
        self.result = cost
        self.destroy()
