"""Support editor: everything about one character's supports - affinity,
support partners and their thresholds, bonds, and the support conversations
- plus the affinity bonus table (``FE8Data.bin`` RelianceData, DivineData,
KiznaData; see :mod:`fe_modding.formats.supports`), and the conversation
text itself (``Mess/yell.m``).

The character is chosen from tiles (:class:`~.widgets.TileBrowser`, with
their portrait when the host passes ``request_portrait``). Values are
written as soon as a field is left or a choice is made; nothing waits for an
Apply button. The panel reads and writes the FE8Data bytes through the
``get_data``/``set_data`` callables and calls ``on_dirty`` after every
change, so the host decides when the file is saved. The conversations tab is
a Dialogue editor on ``yell.m`` with its own Save.
"""

from __future__ import annotations

import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk
from typing import Callable, Optional

from ..formats import fe8data, message, supports
from ..formats.fe9_message_scene import TEMPLATES
from .widgets import ScrollFrame, TileBrowser

RANKS = ("C", "B", "A")
DEFAULT_THRESHOLDS = (1, 3, 5)  # the most common real (non-filler) thresholds in vanilla


def _int(text: str, low: int, high: int, what: str) -> int:
    try:
        value = int(text.strip())
    except ValueError:
        raise ValueError(f"{what} must be a whole number.") from None
    if not low <= value <= high:
        raise ValueError(f"{what} must be between {low} and {high}.")
    return value


def conversation_id(pid_a: str, pid_b: str, rank: str) -> str:
    """``MYELL_<A>_<B>_<rank>``: the two names without ``PID_``, in alphabetical order."""
    a, b = sorted(p[4:] if p.startswith("PID_") else p for p in (pid_a, pid_b))
    return f"MYELL_{a}_{b}_{rank}"


class SupportEditorPanel(ttk.Frame):
    def __init__(
        self,
        parent: tk.Misc,
        get_data: Callable[[], bytes],
        set_data: Callable[[bytes], None],
        on_dirty: Callable[[], None] = lambda: None,
        display_name: Optional[Callable[[str], str]] = None,
        make_dialogue_editor: Optional[Callable[[tk.Misc], object]] = None,
        yell_path: Optional[Path] = None,
        request_portrait: Optional[Callable[[str, int, Callable], None]] = None,
    ):
        super().__init__(parent)
        #: ``request_portrait(fid, size, callback)``: the face on a character's tile
        self._request_portrait = request_portrait
        self._get_data = get_data
        self._set_data = set_data
        self._on_dirty = on_dirty
        self._display_name = display_name or (lambda pid: pid)
        self._make_dialogue_editor = make_dialogue_editor
        self._yell_path = yell_path if yell_path is not None and yell_path.is_file() else None
        self._dialogue = None
        self._pid: Optional[str] = None
        self._notebook = ttk.Notebook(self)
        self._notebook.pack(fill="both", expand=True)
        self._build_character_tab()
        self._build_affinity_tab()
        if self._make_dialogue_editor is not None and self._yell_path is not None:
            self._conversation_tab = ttk.Frame(self._notebook)
            self._notebook.add(self._conversation_tab, text="Conversations")
            self._notebook.bind("<<NotebookTabChanged>>", lambda e: self._on_subtab(), add="+")
        self.reload()

    # -- data -------------------------------------------------------------------
    def reload(self) -> None:
        """Re-read everything from the current bytes (call after the host
        reloads or saves FE8Data.bin, or another view edits it)."""
        data = self._get_data()
        self._fe8 = fe8data.read_fe8data(data)
        self._pids = [c.pid for c in self._fe8.characters if c.pid]
        self._pids = list(dict.fromkeys(self._pids))
        self._lists = supports.read_support_lists(data)
        self._rows = supports.read_affinities(data)
        self._bonds = supports.read_bonds(data)
        self._fids = {}
        for c in self._fe8.characters:
            if c.pid and c.fid:
                self._fids.setdefault(c.pid, c.fid)
        self._labels = [self._label(p) for p in self._pids]
        self._label_to_pid = dict(zip(self._labels, self._pids))
        counts = {sl.owner: sum(1 for s in sl.slots if not s.empty) for sl in self._lists}
        self._picker.set_entries(
            [f"{label}  ·  {counts[pid]} partner{'s' if counts[pid] != 1 else ''}" if counts.get(pid) else label
             for pid, label in zip(self._pids, self._labels)],
            [supports.AFFINITY_NAMES[self._affinity_of(p)] for p in self._pids],
            image=self._tile_image if self._request_portrait is not None else None,
            image_keys=[self._fids.get(p) for p in self._pids])
        for box in (self._add_partner_box, self._add_bond_box):
            box["values"] = self._labels
        if self._pid in self._pids:
            self._picker.select(self._pids.index(self._pid), notify=False)
        elif self._picker.current is None and self._pids:
            with_supports = [i for i, p in enumerate(self._pids) if counts.get(p)]
            self._picker.select(with_supports[0] if with_supports else 0, notify=False)
            self._pid = self._pids[self._picker.current]
        self._refresh_character()
        self._refresh_affinity_table()
        problems = supports.validate_support_lists(self._lists)
        self._problems.config(text="\n".join(problems) if problems else "")

    def _commit(self, data: bytes) -> None:
        if data == self._get_data():
            return
        self._set_data(data)
        self._on_dirty()
        self.reload()

    def _fail(self, title: str, error: Exception) -> None:
        messagebox.showerror(title, str(error), parent=self)

    def _label(self, pid: str) -> str:
        name = self._display_name(pid)
        return pid if name == pid else f"{name} ({pid})"

    def _pid_from(self, text: str) -> str:
        text = text.strip()
        if text in self._label_to_pid:
            return self._label_to_pid[text]
        if text in self._pids:
            return text
        raise ValueError(f"Unknown character {text!r}.")

    def _affinity_of(self, pid: str) -> int:
        for c in self._fe8.characters:
            if c.pid == pid:
                return supports.character_affinity(self._get_data(), c.index)
        return 0

    def _tile_image(self, index: int, callback: Callable) -> None:
        fid = self._fids.get(self._pids[index])
        if fid and self._request_portrait is not None:
            self._request_portrait(fid, 56, callback)

    def _fid_name(self, pid: str) -> str:
        for c in self._fe8.characters:
            if c.pid == pid and c.fid and c.fid.startswith("FID_"):
                return c.fid[4:]
        return pid[4:]

    # -- character tab -------------------------------------------------------------
    def _build_character_tab(self) -> None:
        tab = ttk.Frame(self._notebook, style="Page.TFrame")
        self._notebook.add(tab, text="By character")
        self._picker = TileBrowser(tab, "characters", self._on_pick, image_box=(6, 3), tile_width=250)
        self._picker.pack(fill="both", expand=True)
        scroll = ScrollFrame(self._picker.detail, padding=(16, 8, 16, 16))
        scroll.pack(fill="both", expand=True)
        body = scroll.body

        self._title = ttk.Label(body, text="", style="Title.TLabel")
        self._title.pack(anchor="w")
        row = ttk.Frame(body, style="Page.TFrame")
        row.pack(fill="x", pady=(6, 0))
        ttk.Label(row, text="Affinity").pack(side="left")
        self._affinity = tk.StringVar()
        box = ttk.Combobox(row, textvariable=self._affinity, values=supports.AFFINITY_NAMES, state="readonly",
                           width=12)
        box.pack(side="left", padx=(8, 0))
        box.bind("<<ComboboxSelected>>", lambda e: self._set_affinity())
        ttk.Label(row, text="Bonuses reach allies of the same army within 3 tiles; both units' rows count.",
                  style="Muted.TLabel").pack(side="left", padx=(12, 0))

        # partners
        head = ttk.Frame(body, style="Page.TFrame")
        head.pack(fill="x", pady=(16, 4))
        ttk.Label(head, text="Support partners", style="Subtitle.TLabel").pack(side="left")
        self._slot_note = ttk.Label(head, text="", style="Muted.TLabel")
        self._slot_note.pack(side="left", padx=(10, 0), pady=(4, 0))
        columns = ("slot", "partner", "aff", "c", "b", "a", "bonus", "talk")
        tree = ttk.Treeview(body, columns=columns, show="headings", height=supports.MAX_SLOTS, selectmode="browse")
        for col, text, width in (("slot", "Slot", 44), ("partner", "Partner", 200), ("aff", "Partner affinity", 110),
                                 ("c", "C at", 50), ("b", "B at", 50), ("a", "A at", 50),
                                 ("bonus", "Bonus at A (each unit)", 230), ("talk", "Conversations", 110)):
            tree.heading(col, text=text)
            tree.column(col, width=width, anchor="w" if col in ("partner", "aff", "bonus", "talk") else "center")
        tree.pack(fill="x")
        tree.bind("<<TreeviewSelect>>", lambda e: self._on_partner_selected())
        self._partner_tree = tree

        edit = ttk.Frame(body, style="Page.TFrame")
        edit.pack(fill="x", pady=(8, 0))
        self._pair_label = ttk.Label(edit, text="Select a partner to edit the pair.", style="Muted.TLabel")
        self._pair_label.grid(row=0, column=0, columnspan=10, sticky="w")
        self._thresholds = []
        for i, rank in enumerate(RANKS):
            ttk.Label(edit, text=f"{rank} at").grid(row=1, column=2 * i, sticky="w", padx=(0 if i == 0 else 10, 4))
            var = tk.StringVar()
            entry = ttk.Entry(edit, textvariable=var, width=6, state="disabled")
            entry.grid(row=1, column=2 * i + 1, sticky="w", pady=(4, 0))
            entry.bind("<FocusOut>", lambda e: self._apply_thresholds(), add="+")
            entry.bind("<Return>", lambda e: self._apply_thresholds(), add="+")
            self._thresholds.append((var, entry))
        self._remove_button = ttk.Button(edit, text="Remove partner", command=self._remove_partner, state="disabled")
        self._remove_button.grid(row=1, column=6, sticky="w", padx=(16, 0))
        talk = ttk.Frame(edit, style="Page.TFrame")
        talk.grid(row=2, column=0, columnspan=10, sticky="w", pady=(8, 0))
        ttk.Label(talk, text="Conversation").pack(side="left")
        self._talk_buttons = []
        for rank in RANKS:
            button = ttk.Button(talk, text=rank, width=10, state="disabled",
                                command=lambda r=rank: self._open_conversation(r))
            button.pack(side="left", padx=(6, 0))
            self._talk_buttons.append(button)
        add = ttk.Frame(body, style="Page.TFrame")
        add.pack(fill="x", pady=(10, 0))
        ttk.Label(add, text="Add partner").pack(side="left")
        self._add_partner = tk.StringVar()
        self._add_partner_box = ttk.Combobox(add, textvariable=self._add_partner, width=34)
        self._add_partner_box.pack(side="left", padx=(8, 0))
        self._add_partner_box.bind("<Return>", lambda e: self._add_partner_pair())
        ttk.Button(add, text="Add", command=self._add_partner_pair).pack(side="left", padx=(6, 0))
        ttk.Label(body, style="Muted.TLabel", wraplength=820, justify="left", text=(
            "Both units gain 1 point at the end of each chapter they finish on the map together; the base "
            "offers the conversation when the points reach C, B or A, and viewing it raises the rank. A unit "
            "holds at most 5 support stars (C=1, B=2, A=3) and 10 partners. A pair is written to both "
            "characters' lists; a removed partner leaves an empty slot so existing saves keep their points.")
        ).pack(anchor="w", pady=(8, 0))

        # bonds
        ttk.Label(body, text="Bonds", style="Subtitle.TLabel").pack(anchor="w", pady=(18, 4))
        tree = ttk.Treeview(body, columns=("other", "role", "kind", "value"), show="headings", height=4,
                            selectmode="browse")
        for col, text, width in (("other", "With", 220), ("role", "This character is", 110),
                                 ("kind", "Effect", 280), ("value", "Value", 60)):
            tree.heading(col, text=text)
            tree.column(col, width=width, anchor="w")
        tree.pack(fill="x")
        tree.bind("<<TreeviewSelect>>", lambda e: self._on_bond_selected())
        self._bond_tree = tree
        form = ttk.Frame(body, style="Page.TFrame")
        form.pack(fill="x", pady=(6, 0))
        self._bond_kind = tk.StringVar()
        self._bond_value = tk.StringVar()
        kinds = [f"{k}: {v}" for k, v in supports.BOND_KIND_NAMES.items()]
        ttk.Label(form, text="Effect").pack(side="left")
        self._bond_kind_box = ttk.Combobox(form, textvariable=self._bond_kind, values=kinds, state="disabled",
                                           width=34)
        self._bond_kind_box.pack(side="left", padx=(6, 0))
        self._bond_kind_box.bind("<<ComboboxSelected>>", lambda e: self._apply_bond())
        ttk.Label(form, text="Value").pack(side="left", padx=(10, 0))
        self._bond_value_entry = ttk.Entry(form, textvariable=self._bond_value, width=6, state="disabled")
        self._bond_value_entry.pack(side="left", padx=(6, 0))
        self._bond_value_entry.bind("<FocusOut>", lambda e: self._apply_bond(), add="+")
        self._bond_value_entry.bind("<Return>", lambda e: self._apply_bond(), add="+")
        self._bond_remove = ttk.Button(form, text="Remove bond", command=self._remove_bond, state="disabled")
        self._bond_remove.pack(side="left", padx=(12, 0))
        add = ttk.Frame(body, style="Page.TFrame")
        add.pack(fill="x", pady=(8, 0))
        ttk.Label(add, text="Add bond with").pack(side="left")
        self._add_bond = tk.StringVar()
        self._add_bond_box = ttk.Combobox(add, textvariable=self._add_bond, width=34)
        self._add_bond_box.pack(side="left", padx=(8, 0))
        ttk.Button(add, text="Add", command=self._add_bond_record).pack(side="left", padx=(6, 0))
        ttk.Label(body, style="Muted.TLabel", wraplength=820, justify="left", text=(
            "Effect 1: while the two stand next to each other (same army), each gets Value extra Critical. "
            "Effect 2: while the second character stands next to the first, enemies have 0 Critical against "
            "the second (Value unused). Bonds need no support pair.")).pack(anchor="w", pady=(8, 0))
        self._problems = ttk.Label(body, text="", style="Warn.TLabel", wraplength=820, justify="left")
        self._problems.pack(anchor="w", pady=(12, 0))

    def _on_pick(self, index: int) -> None:
        self._pid = self._pids[index]
        self._refresh_character()

    def _refresh_character(self) -> None:
        pid = self._pid
        tree = self._partner_tree
        tree.delete(*tree.get_children())
        self._bond_tree.delete(*self._bond_tree.get_children())
        self._select_pair(None)
        self._select_bond(None)
        if pid is None:
            return
        self._title.config(text=self._label(pid))
        own = self._affinity_of(pid)
        self._affinity.set(supports.AFFINITY_NAMES[own])
        sl = next((x for x in self._lists if x.owner == pid), None)
        talks = self._conversation_ids()
        used = 0
        for i, slot in enumerate(sl.slots if sl else []):
            if slot.empty:
                tree.insert("", "end", iid=f"empty{i}", values=(i, "(empty slot)", "", "", "", "", "", ""),
                            tags=("empty",))
                continue
            used += 1
            other = self._affinity_of(slot.partner)
            bonus = supports.pair_bonus(self._rows, own, other, 3)
            text = ", ".join(f"{n} +{v}" for n, v in zip(supports.BONUS_NAMES, bonus) if v) or "none"
            have = "".join(r if conversation_id(pid, slot.partner, r) in talks else "·" for r in RANKS) \
                if talks is not None else ""
            tree.insert("", "end", iid=slot.partner, values=(
                i, self._label(slot.partner), supports.AFFINITY_NAMES[other], slot.c, slot.b, slot.a, text, have))
        tree.tag_configure("empty", foreground="#888888")
        slots = len(sl.slots) if sl else 0
        self._slot_note.config(text=f"{used} partner{'s' if used != 1 else ''}, {slots} of "
                                    f"{supports.MAX_SLOTS} slots used")
        for i, bd in enumerate(self._bonds):
            if pid not in (bd.pid1, bd.pid2):
                continue
            other = bd.pid2 if bd.pid1 == pid else bd.pid1
            role = "first" if bd.pid1 == pid else "second"
            self._bond_tree.insert("", "end", iid=str(i), values=(
                self._label(other), role, supports.BOND_KIND_NAMES.get(bd.kind, f"unknown {bd.kind}"), bd.value))

    # -- affinity ----------------------------------------------------------------------
    def _set_affinity(self) -> None:
        if self._pid is None:
            return
        affinity = supports.AFFINITY_NAMES.index(self._affinity.get() or "None")
        data = self._get_data()
        for c in self._fe8.characters:
            if c.pid == self._pid:
                data = supports.patch_character_affinity(data, c.index, affinity)
        self._commit(data)

    # -- pairs --------------------------------------------------------------------------
    def _selected_partner(self) -> Optional[str]:
        sel = self._partner_tree.selection()
        return sel[0] if sel and not sel[0].startswith("empty") else None

    def _on_partner_selected(self) -> None:
        self._apply_thresholds()
        self._select_pair(self._selected_partner())

    def _select_pair(self, partner: Optional[str]) -> None:
        self._pair = partner
        state = "normal" if partner else "disabled"
        slot = None
        if partner:
            sl = next((x for x in self._lists if x.owner == self._pid), None)
            slot = sl.slots[sl.slot_of(partner)] if sl and sl.slot_of(partner) >= 0 else None
        for (var, entry), value in zip(self._thresholds, (slot.c, slot.b, slot.a) if slot else ("", "", "")):
            entry.config(state="normal")
            var.set(str(value))
            entry.config(state=state)
        self._remove_button.config(state=state)
        self._pair_label.config(text=(f"{self._label(self._pid)} and {self._label(partner)}: thresholds apply "
                                      "to both lists." if partner else "Select a partner to edit the pair."))
        talks = self._conversation_ids()
        for rank, button in zip(RANKS, self._talk_buttons):
            if not partner or self._yell_path is None:
                button.config(state="disabled", text=rank)
                continue
            exists = talks is not None and conversation_id(self._pid, partner, rank) in talks
            button.config(state="normal", text=f"Edit {rank}" if exists else f"Create {rank}")

    def _apply_thresholds(self) -> None:
        partner = getattr(self, "_pair", None)
        if not partner or self._pid is None:
            return
        sl = next((x for x in self._lists if x.owner == self._pid), None)
        if sl is None or sl.slot_of(partner) < 0:
            return
        slot = sl.slots[sl.slot_of(partner)]
        texts = [var.get() for var, _ in self._thresholds]
        if texts == [str(slot.c), str(slot.b), str(slot.a)]:
            return
        try:
            c = _int(texts[0], 0, 253, "C")
            b = _int(texts[1], 1, 253, "B")
            a = _int(texts[2], 2, 254, "A")
            if not c < b < a:
                raise ValueError("The thresholds must rise: C < B < A.")
            lists = supports.read_support_lists(self._get_data())
            supports.set_pair(lists, self._pid, partner, c, b, a)
            data = supports.write_support_lists(self._get_data(), lists)
        except ValueError as e:
            self._fail("Support thresholds", e)
            return
        self._commit(data)
        if self._partner_tree.exists(partner):
            self._partner_tree.selection_set(partner)

    def _add_partner_pair(self) -> None:
        if self._pid is None:
            return
        try:
            partner = self._pid_from(self._add_partner.get())
            lists = supports.read_support_lists(self._get_data())
            sl = next((x for x in lists if x.owner == self._pid), None)
            if sl is not None and sl.slot_of(partner) >= 0:
                raise ValueError(f"{self._label(partner)} is already a partner.")
            supports.set_pair(lists, self._pid, partner, *DEFAULT_THRESHOLDS)
            data = supports.write_support_lists(self._get_data(), lists)
        except ValueError as e:
            self._fail("Add partner", e)
            return
        self._add_partner.set("")
        self._commit(data)
        if self._partner_tree.exists(partner):
            self._partner_tree.selection_set(partner)

    def _remove_partner(self) -> None:
        partner = self._selected_partner()
        if not partner or self._pid is None:
            return
        try:
            lists = supports.read_support_lists(self._get_data())
            supports.remove_pair(lists, self._pid, partner)
            data = supports.write_support_lists(self._get_data(), lists)
        except ValueError as e:
            self._fail("Remove partner", e)
            return
        self._commit(data)

    # -- bonds --------------------------------------------------------------------------
    def _on_bond_selected(self) -> None:
        sel = self._bond_tree.selection()
        self._select_bond(int(sel[0]) if sel else None)

    def _select_bond(self, index: Optional[int]) -> None:
        self._bond_index = index
        state = "normal" if index is not None else "disabled"
        bd = self._bonds[index] if index is not None else None
        self._bond_kind_box.config(state="readonly" if bd else "disabled")
        self._bond_kind.set(f"{bd.kind}: {supports.BOND_KIND_NAMES.get(bd.kind, '')}" if bd else "")
        self._bond_value_entry.config(state="normal")
        self._bond_value.set(str(bd.value) if bd else "")
        self._bond_value_entry.config(state=state)
        self._bond_remove.config(state=state)

    def _apply_bond(self) -> None:
        index = getattr(self, "_bond_index", None)
        if index is None or index >= len(self._bonds):
            return
        old = self._bonds[index]
        try:
            kind = int((self._bond_kind.get() or "1").split(":")[0])
            value = _int(self._bond_value.get(), -128, 127, "Value")
            if (kind, value) == (old.kind, old.value):
                return
            bonds = list(self._bonds)
            bonds[index] = supports.Bond(old.pid1, old.pid2, kind, value, old.tail)
            data = supports.write_bonds(self._get_data(), bonds)
        except ValueError as e:
            self._fail("Bond", e)
            return
        self._commit(data)
        if self._bond_tree.exists(str(index)):
            self._bond_tree.selection_set(str(index))

    def _add_bond_record(self) -> None:
        if self._pid is None:
            return
        try:
            other = self._pid_from(self._add_bond.get())
            if other == self._pid:
                raise ValueError("A bond needs two different characters.")
            bonds = list(self._bonds) + [supports.Bond(self._pid, other, supports.BOND_CRIT, 10)]
            data = supports.write_bonds(self._get_data(), bonds)
        except ValueError as e:
            self._fail("Add bond", e)
            return
        self._add_bond.set("")
        self._commit(data)
        new = str(len(self._bonds) - 1)
        if self._bond_tree.exists(new):
            self._bond_tree.selection_set(new)

    def _remove_bond(self) -> None:
        index = getattr(self, "_bond_index", None)
        if index is None:
            return
        bonds = [bd for i, bd in enumerate(self._bonds) if i != index]
        self._commit(supports.write_bonds(self._get_data(), bonds))

    # -- affinity table tab --------------------------------------------------------------
    def _build_affinity_tab(self) -> None:
        tab = ttk.Frame(self._notebook, padding=12)
        self._notebook.add(tab, text="Affinity bonuses")
        ttk.Label(tab, text="Bonus per support rank", style="Subtitle.TLabel").grid(
            row=0, column=0, columnspan=7, sticky="w")
        ttk.Label(tab, style="Muted.TLabel", wraplength=760, justify="left", text=(
            "For each partner in range, the unit's row and the partner's row are added and multiplied by the "
            "rank (C=1, B=2, A=3); the total is halved. Values apply when you leave a cell.")).grid(
            row=1, column=0, columnspan=7, sticky="w", pady=(0, 8))
        ttk.Label(tab, text="Affinity").grid(row=2, column=0, sticky="w")
        for j, name in enumerate(supports.BONUS_NAMES):
            ttk.Label(tab, text=name).grid(row=2, column=j + 1, padx=4)
        self._aff_vars = []
        for i, name in enumerate(supports.AFFINITY_NAMES):
            ttk.Label(tab, text=f"{name}  ({supports.AFFINITY_KEYS[i]})").grid(row=i + 3, column=0, sticky="w")
            row_vars = []
            for j in range(6):
                var = tk.StringVar()
                entry = ttk.Entry(tab, textvariable=var, width=6)
                entry.grid(row=i + 3, column=j + 1, padx=4, pady=1)
                entry.bind("<FocusOut>", lambda e: self._apply_affinity_table(), add="+")
                entry.bind("<Return>", lambda e: self._apply_affinity_table(), add="+")
                row_vars.append(var)
            self._aff_vars.append(row_vars)

    def _refresh_affinity_table(self) -> None:
        for row_vars, row in zip(self._aff_vars, self._rows):
            for var, value in zip(row_vars, row.bonus):
                var.set(str(value))

    def _apply_affinity_table(self) -> None:
        data = self._get_data()
        try:
            for i, row_vars in enumerate(self._aff_vars[:len(self._rows)]):
                values = [_int(v.get(), -128, 127, f"{supports.AFFINITY_NAMES[i]} {supports.BONUS_NAMES[j]}")
                          for j, v in enumerate(row_vars)]
                data = supports.patch_affinity_bonus(data, i, values)
        except ValueError as e:
            self._fail("Affinities", e)
            return
        self._commit(data)

    def flush(self) -> None:
        """Apply the field that still has the focus (see StatsEditor.flush)."""
        self._apply_thresholds()
        self._apply_bond()
        self._apply_affinity_table()

    # -- conversations -------------------------------------------------------------------
    def _conversation_ids(self) -> Optional[set]:
        if self._yell_path is None:
            return None
        if self._dialogue is not None and self._dialogue.current_path == self._yell_path:
            return self._dialogue.message_ids()
        try:
            return {m.speaker for m in message.read_messages_path(self._yell_path)}
        except (OSError, ValueError):
            return None

    def _ensure_dialogue(self):
        if self._dialogue is None:
            self._dialogue = self._make_dialogue_editor(self._conversation_tab)
            self._dialogue.pack(fill="both", expand=True)
            self._dialogue.select_chapter(self._yell_path)
        return self._dialogue

    def _on_subtab(self) -> None:
        if str(self._notebook.select()) == str(getattr(self, "_conversation_tab", "")):
            self._ensure_dialogue()
        else:
            self._refresh_character()  # conversations may have been added there

    @property
    def dialogue_editor(self):
        return self._dialogue

    def _open_conversation(self, rank: str) -> None:
        partner = getattr(self, "_pair", None)
        if not partner or self._pid is None or self._yell_path is None:
            return
        msg_id = conversation_id(self._pid, partner, rank)
        dialogue = self._ensure_dialogue()
        if msg_id not in dialogue.message_ids():
            # the Dialogue editor's background-scene template, with the pair's faces
            text = next((t for name, t in TEMPLATES.items() if "FCL_IKE" in t and "FCL_MIST" in t), "")
            text = text.replace("FCL_IKE", "FCL_" + self._fid_name(self._pid)).replace(
                "FCL_MIST", "FCL_" + self._fid_name(partner))
            if not dialogue.add_message(msg_id, text):
                return
        dialogue.select_message(msg_id)
        self._notebook.select(self._conversation_tab)
