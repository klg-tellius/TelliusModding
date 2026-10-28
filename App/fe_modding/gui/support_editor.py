"""Support editing, in two places.

:class:`CharacterSupportsPanel` is everything about one character's supports
- affinity, support partners and their thresholds, bonds - and sits in the
**Supports** tab of that character's page. :class:`SupportEditorPanel` is the
Game Data **Supports** tab: every support pair at a glance (each opening the
characters' pages), the affinity bonus table, and the support conversations
(``Mess/yell.m``). The FE8Data tables are RelianceData, DivineData and
KiznaData; see :mod:`fe_modding.formats.supports`.

Values are written as soon as a field is left or a choice is made; nothing
waits for an Apply button. Both panels read and write the FE8Data bytes
through the ``get_data``/``set_data`` callables and call ``on_dirty`` after
every change, so the host decides when the file is saved. The conversations
tab is a Dialogue editor on ``yell.m`` with its own Save.
"""

from __future__ import annotations

import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk
from typing import Callable, Optional

from ..formats import fe8data, message, supports
from ..formats.fe9_message_scene import TEMPLATES
from ..supports_model import RANKS, PorSupports, SupportsModel, conversation_id



def _int(text: str, low: int, high: int, what: str) -> int:
    try:
        value = int(text.strip())
    except ValueError:
        raise ValueError(f"{what} must be a whole number.") from None
    if not low <= value <= high:
        raise ValueError(f"{what} must be between {low} and {high}.")
    return value


def read_conversation_ids(yell_path: Optional[Path]) -> Optional[set]:
    """The message IDs in ``yell.m`` as saved (None: no readable file)."""
    if yell_path is None or not yell_path.is_file():
        return None
    try:
        return {m.speaker for m in message.read_messages_path(yell_path)}
    except (OSError, ValueError):
        return None


class _Fe8View:
    """What both panels read from the FE8Data bytes: the characters and
    their affinities, the support lists, the affinity rows and the bonds."""

    def __init__(self, data: bytes):
        self.fe8 = fe8data.read_fe8data(data)
        self.pids = list(dict.fromkeys(c.pid for c in self.fe8.characters if c.pid))
        self.lists = supports.read_support_lists(data)
        self.rows = supports.read_affinities(data)
        self.bonds = supports.read_bonds(data)
        self.affinities: dict[str, int] = {}
        for c in self.fe8.characters:
            if c.pid and c.pid not in self.affinities:
                self.affinities[c.pid] = supports.character_affinity(data, c.index)

    def affinity_of(self, pid: str) -> int:
        return self.affinities.get(pid, 0)

    def list_of(self, pid: str):
        return next((x for x in self.lists if x.owner == pid), None)

    def fid_name(self, pid: str) -> str:
        for c in self.fe8.characters:
            if c.pid == pid and c.fid and c.fid.startswith("FID_"):
                return c.fid[4:]
        return pid[4:]


class CharacterSupportsPanel(ttk.Frame):
    """One character's affinity, support partners and bonds (:meth:`show`
    picks the character), on both games through a :class:`~..supports_model.SupportsModel`
    class (``model``, from ``session.adapter.supports_model``; Path of Radiance's by default).

    ``conversation_ids()`` gives the support conversations that exist (None:
    unknown); ``open_conversation(pid, partner, rank)`` opens or creates one
    (rank None: the game keeps its support talks elsewhere, opened by one link);
    ``open_character(pid)`` shows another character (double-click on a partner
    or bond)."""

    def __init__(
        self,
        parent: tk.Misc,
        get_data: Callable[[], bytes],
        set_data: Callable[[bytes], None],
        on_dirty: Callable[[], None] = lambda: None,
        display_name: Optional[Callable[[str], str]] = None,
        conversation_ids: Callable[[], Optional[set]] = lambda: None,
        open_conversation: Optional[Callable[[str, str, Optional[str]], None]] = None,
        open_character: Optional[Callable[[str], None]] = None,
        model: type = PorSupports,
    ):
        super().__init__(parent, style="Page.TFrame")
        self._get_data = get_data
        self._set_data = set_data
        self._on_dirty = on_dirty
        self._display_name = display_name or (lambda pid: pid)
        self._conversation_ids = conversation_ids
        self._open_conversation_cb = open_conversation
        self._open_character = open_character
        self._make_model = model
        self._pid: Optional[str] = None
        self._pair: Optional[str] = None
        self._bond_index: Optional[int] = None
        self._view: Optional[SupportsModel] = None
        self._layout = model  # the model class also gives the columns and fields
        self._build()

    # -- data -------------------------------------------------------------------
    def show(self, pid: Optional[str]) -> None:
        self.flush()
        self._pid = pid
        self.reload()

    def reload(self) -> None:
        """Re-read everything from the current bytes (call after the host
        reloads or saves the file, or another view edits it)."""
        data = self._get_data()
        self._view = self._make_model(data) if data else None
        self._labels = [self._label(p) for p in self._view.pids] if self._view else []
        self._label_to_pid = dict(zip(self._labels, self._view.pids)) if self._view else {}
        for box in (self._add_partner_box, self._add_bond_box):
            if box is not None:
                box["values"] = [label for label, pid in self._label_to_pid.items() if pid != self._pid]
        self._refresh()
        self._problems.config(text="\n".join(self._view.problems(self._pid) if self._view else []))

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
        if self._view is not None and text in self._view.pids:
            return text
        raise ValueError(f"Unknown character {text!r}.")

    # -- layout -------------------------------------------------------------------
    def _build(self) -> None:
        body = self
        layout = self._layout
        row = ttk.Frame(body, style="Page.TFrame")
        row.pack(fill="x")
        ttk.Label(row, text="Affinity").pack(side="left")
        self._affinity = tk.StringVar()
        self._affinity_box = ttk.Combobox(row, textvariable=self._affinity, state="readonly", width=12)
        self._affinity_box.pack(side="left", padx=(8, 0))
        self._affinity_box.bind("<<ComboboxSelected>>", lambda e: self._set_affinity())
        ttk.Label(row, text=layout.affinity_note, style="Muted.TLabel").pack(side="left", padx=(12, 0))
        # partners
        head = ttk.Frame(body, style="Page.TFrame")
        head.pack(fill="x", pady=(16, 4))
        ttk.Label(head, text="Support partners", style="Subtitle.TLabel").pack(side="left")
        self._slot_note = ttk.Label(head, text="", style="Muted.TLabel")
        self._slot_note.pack(side="left", padx=(10, 0), pady=(4, 0))
        columns = ("slot", "partner", *(f"c{i}" for i in range(len(layout.partner_columns))))
        tree = ttk.Treeview(body, columns=columns, show="headings",
                            height=supports.MAX_SLOTS if layout.can_add_partners else 14, selectmode="browse")
        for col, (text, width) in zip(columns, (("Slot", 44), ("Partner", 200), *layout.partner_columns)):
            tree.heading(col, text=text)
            tree.column(col, width=width, anchor="center" if col == "slot" or text.endswith(" at")
                        or text in ("Flag", "Speed") else "w")
        tree.pack(fill="x")
        tree.bind("<<TreeviewSelect>>", lambda e: self._on_partner_selected())
        tree.bind("<Double-Button-1>", lambda e: self._open_selected_partner())
        self._partner_tree = tree

        edit = ttk.Frame(body, style="Page.TFrame")
        edit.pack(fill="x", pady=(8, 0))
        self._pair_label = ttk.Label(edit, text="Select a partner to edit the pair.", style="Muted.TLabel")
        self._pair_label.grid(row=0, column=0, columnspan=10, sticky="w")
        self._thresholds = []
        for i, field in enumerate(layout.pair_fields):
            ttk.Label(edit, text=field.label).grid(row=1, column=2 * i, sticky="w", padx=(0 if i == 0 else 10, 4))
            var = tk.StringVar()
            entry = ttk.Entry(edit, textvariable=var, width=6, state="disabled")
            entry.grid(row=1, column=2 * i + 1, sticky="w", pady=(4, 0))
            entry.bind("<FocusOut>", lambda e: self._apply_thresholds(), add="+")
            entry.bind("<Return>", lambda e: self._apply_thresholds(), add="+")
            self._thresholds.append((var, entry))
        self._remove_button = None
        if layout.can_add_partners:
            self._remove_button = ttk.Button(edit, text="Remove partner", command=self._remove_partner,
                                             state="disabled")
            self._remove_button.grid(row=1, column=2 * len(layout.pair_fields), sticky="w", padx=(16, 0))
        talk = ttk.Frame(edit, style="Page.TFrame")
        talk.grid(row=2, column=0, columnspan=10, sticky="w", pady=(8, 0))
        self._talk_buttons = []
        if layout.conversation_ranks:
            ttk.Label(talk, text="Conversation").pack(side="left")
            for rank in layout.conversation_ranks:
                button = ttk.Button(talk, text=rank, width=10, state="disabled",
                                    command=lambda r=rank: self._open_conversation(r))
                button.pack(side="left", padx=(6, 0))
                self._talk_buttons.append((rank, button))
        elif self._open_conversation_cb is not None:
            button = ttk.Button(talk, text="Support conversations…", state="disabled",
                                command=lambda: self._open_conversation(None))
            button.pack(side="left")
            self._talk_buttons.append((None, button))
        self._add_partner = tk.StringVar()
        self._add_partner_box = None
        if layout.can_add_partners:
            add = ttk.Frame(body, style="Page.TFrame")
            add.pack(fill="x", pady=(10, 0))
            ttk.Label(add, text="Add partner").pack(side="left")
            self._add_partner_box = ttk.Combobox(add, textvariable=self._add_partner, width=34)
            self._add_partner_box.pack(side="left", padx=(8, 0))
            self._add_partner_box.bind("<Return>", lambda e: self._add_partner_pair())
            ttk.Button(add, text="Add", command=self._add_partner_pair).pack(side="left", padx=(6, 0))
        ttk.Label(body, style="Muted.TLabel", wraplength=820, justify="left", text=layout.pair_note).pack(
            anchor="w", pady=(8, 0))

        # bonds
        ttk.Label(body, text="Bonds", style="Subtitle.TLabel").pack(anchor="w", pady=(18, 4))
        bond_columns = ("other", *(f"c{i}" for i in range(len(layout.bond_columns))))
        tree = ttk.Treeview(body, columns=bond_columns, show="headings", height=4, selectmode="browse")
        for col, (text, width) in zip(bond_columns, (("With", 220), *layout.bond_columns)):
            tree.heading(col, text=text)
            tree.column(col, width=width, anchor="w")
        tree.pack(fill="x")
        tree.bind("<<TreeviewSelect>>", lambda e: self._on_bond_selected())
        tree.bind("<Double-Button-1>", lambda e: self._open_selected_bond())
        self._bond_tree = tree
        form = ttk.Frame(body, style="Page.TFrame")
        form.pack(fill="x", pady=(6, 0))
        self._bond_vars = []
        for i, field in enumerate(layout.bond_fields):
            ttk.Label(form, text=field.label).pack(side="left", padx=(0 if i == 0 else 10, 0))
            var = tk.StringVar()
            if field.options:
                widget = ttk.Combobox(form, textvariable=var, values=[f"{k}: {v}" for k, v in field.options],
                                      state="disabled", width=34)
                widget.bind("<<ComboboxSelected>>", lambda e: self._apply_bond())
            else:
                widget = ttk.Entry(form, textvariable=var, width=6, state="disabled")
                widget.bind("<FocusOut>", lambda e: self._apply_bond(), add="+")
                widget.bind("<Return>", lambda e: self._apply_bond(), add="+")
            widget.pack(side="left", padx=(6, 0))
            self._bond_vars.append((var, widget, field))
        self._bond_remove = ttk.Button(form, text="Remove bond", command=self._remove_bond, state="disabled")
        self._bond_remove.pack(side="left", padx=(12, 0))
        add = ttk.Frame(body, style="Page.TFrame")
        add.pack(fill="x", pady=(8, 0))
        ttk.Label(add, text="Add bond with").pack(side="left")
        self._add_bond = tk.StringVar()
        self._add_bond_box = ttk.Combobox(add, textvariable=self._add_bond, width=34)
        self._add_bond_box.pack(side="left", padx=(8, 0))
        ttk.Button(add, text="Add", command=self._add_bond_record).pack(side="left", padx=(6, 0))
        ttk.Label(body, style="Muted.TLabel", wraplength=820, justify="left", text=layout.bond_note).pack(
            anchor="w", pady=(8, 0))
        self._problems = ttk.Label(body, text="", style="Warn.TLabel", wraplength=820, justify="left")
        self._problems.pack(anchor="w", pady=(12, 0))

    def _refresh(self) -> None:
        pid = self._pid
        tree = self._partner_tree
        tree.delete(*tree.get_children())
        self._bond_tree.delete(*self._bond_tree.get_children())
        self._select_pair(None)
        self._select_bond(None)
        view = self._view
        if pid is None or view is None:
            self._affinity.set("")
            self._slot_note.config(text="")
            return
        self._affinity_box.configure(values=list(view.affinity_names))
        self._affinity.set(view.affinity_of(pid))
        for row in view.partners(pid, self._conversation_ids()):
            if row.partner is None:
                tree.insert("", "end", iid=f"empty{row.slot}", values=(row.slot, "(empty slot)", *row.cells),
                            tags=("empty",))
            elif not tree.exists(row.partner):
                tree.insert("", "end", iid=row.partner, values=(row.slot, self._label(row.partner), *row.cells))
        tree.tag_configure("empty", foreground="#888888")
        self._slot_note.config(text=view.slot_note(pid))
        for bond in view.bonds(pid):
            self._bond_tree.insert("", "end", iid=str(bond.key), values=(self._label(bond.other), *bond.cells))

    # -- affinity ----------------------------------------------------------------------
    def _set_affinity(self) -> None:
        if self._pid is None or self._view is None:
            return
        self._commit(self._view.set_affinity(self._get_data(), self._pid, self._affinity.get()))

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
        values = (self._view.pair_values(self._pid, partner) if partner and self._view
                  else ("",) * len(self._thresholds))
        for (var, entry), value in zip(self._thresholds, values):
            entry.config(state="normal")
            var.set(str(value))
            entry.config(state=state)
        if self._remove_button is not None:
            self._remove_button.config(state=state)
        self._pair_label.config(text=(f"{self._label(self._pid)} and {self._label(partner)}"
                                      + (": thresholds apply to both lists." if self._layout.can_add_partners
                                         else f": {self._label(self._pid)}'s entry.")
                                      if partner else "Select a partner to edit the pair."))
        talks = self._conversation_ids()
        for rank, button in self._talk_buttons:
            if not partner or self._open_conversation_cb is None:
                button.config(state="disabled", **({"text": rank} if rank else {}))
                continue
            if rank is None:
                button.config(state="normal")
                continue
            exists = talks is not None and conversation_id(self._pid, partner, rank) in talks
            button.config(state="normal", text=f"Edit {rank}" if exists else f"Create {rank}")

    def _apply_thresholds(self) -> None:
        partner = self._pair
        if not partner or self._pid is None or self._view is None:
            return
        texts = [var.get() for var, _ in self._thresholds]
        try:
            if tuple(texts) == tuple(self._view.pair_values(self._pid, partner)):
                return
            data = self._view.set_pair(self._get_data(), self._pid, partner, texts)
        except ValueError as e:
            self._fail("Support pair", e)
            return
        self._commit(data)
        if self._partner_tree.exists(partner):
            self._partner_tree.selection_set(partner)

    def _add_partner_pair(self) -> None:
        if self._pid is None or self._view is None:
            return
        try:
            partner = self._pid_from(self._add_partner.get())
            data = self._view.add_partner(self._get_data(), self._pid, partner)
        except ValueError as e:
            self._fail("Add partner", e)
            return
        self._add_partner.set("")
        self._commit(data)
        if self._partner_tree.exists(partner):
            self._partner_tree.selection_set(partner)

    def _remove_partner(self) -> None:
        partner = self._selected_partner()
        if not partner or self._pid is None or self._view is None:
            return
        try:
            data = self._view.remove_partner(self._get_data(), self._pid, partner)
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
        values = self._view.bond_values(index) if index is not None and self._view else ("",) * len(self._bond_vars)
        for (var, widget, field), value in zip(self._bond_vars, values):
            widget.config(state="normal")
            var.set(value)
            widget.config(state=("readonly" if field.options else "normal") if index is not None else "disabled")
        self._bond_remove.config(state="normal" if index is not None else "disabled")

    def _apply_bond(self) -> None:
        index = self._bond_index
        if index is None or self._view is None:
            return
        try:
            data = self._view.set_bond(self._get_data(), index, [var.get() for var, _w, _f in self._bond_vars])
        except (ValueError, IndexError) as e:
            self._fail("Bond", e)
            return
        self._commit(data)
        if self._bond_tree.exists(str(index)):
            self._bond_tree.selection_set(str(index))

    def _add_bond_record(self) -> None:
        if self._pid is None or self._view is None:
            return
        try:
            other = self._pid_from(self._add_bond.get())
            data = self._view.add_bond(self._get_data(), self._pid, other)
        except ValueError as e:
            self._fail("Add bond", e)
            return
        self._add_bond.set("")
        self._commit(data)
        rows = self._view.bonds(self._pid) if self._view else []
        if rows and self._bond_tree.exists(str(rows[-1].key)):
            self._bond_tree.selection_set(str(rows[-1].key))

    def _remove_bond(self) -> None:
        index = self._bond_index
        if index is None or self._view is None:
            return
        try:
            data = self._view.remove_bond(self._get_data(), index)
        except ValueError as e:
            self._fail("Remove bond", e)
            return
        self._commit(data)

    # -- navigation ---------------------------------------------------------------------
    def _open_selected_partner(self) -> None:
        partner = self._selected_partner()
        if partner and self._open_character is not None:
            self._open_character(partner)

    def _open_selected_bond(self) -> None:
        sel = self._bond_tree.selection()
        if not sel or self._view is None or self._open_character is None:
            return
        self._open_character(self._view.bond_other(int(sel[0]), self._pid))

    def _open_conversation(self, rank: Optional[str]) -> None:
        if self._pair and self._pid is not None and self._open_conversation_cb is not None:
            self._open_conversation_cb(self._pid, self._pair, rank)

    def flush(self) -> None:
        """Apply the field that still has the focus (see StatsEditor.flush)."""
        self._apply_thresholds()
        self._apply_bond()


class SupportEditorPanel(ttk.Frame):
    """The Game Data Supports tab. A character's partners and bonds are
    edited on their page: ``open_character(pid)`` goes there."""

    def __init__(
        self,
        parent: tk.Misc,
        get_data: Callable[[], bytes],
        set_data: Callable[[bytes], None],
        on_dirty: Callable[[], None] = lambda: None,
        display_name: Optional[Callable[[str], str]] = None,
        make_dialogue_editor: Optional[Callable[[tk.Misc], object]] = None,
        yell_path: Optional[Path] = None,
        open_character: Optional[Callable[[str], None]] = None,
    ):
        super().__init__(parent)
        self._get_data = get_data
        self._set_data = set_data
        self._on_dirty = on_dirty
        self._display_name = display_name or (lambda pid: pid)
        self._make_dialogue_editor = make_dialogue_editor
        self._yell_path = yell_path if yell_path is not None and yell_path.is_file() else None
        self._open_character = open_character
        self._dialogue = None
        self._notebook = ttk.Notebook(self)
        self._notebook.pack(fill="both", expand=True)
        self._build_pairs_tab()
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
        self._view = _Fe8View(self._get_data())
        self._rows = self._view.rows
        self._refresh_pairs()
        self._refresh_affinity_table()

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

    # -- pairs tab ------------------------------------------------------------------
    def _build_pairs_tab(self) -> None:
        tab = ttk.Frame(self._notebook, padding=12)
        self._notebook.add(tab, text="Pairs")
        ttk.Label(tab, style="Muted.TLabel", wraplength=820, justify="left", text=(
            "Every support pair. A character's affinity, partners, thresholds and bonds are edited in the "
            "Supports tab of their character page: double-click a pair to open it.")).pack(anchor="w", pady=(0, 8))
        holder = ttk.Frame(tab)
        holder.pack(fill="both", expand=True)
        columns = ("a", "b", "c_at", "b_at", "a_at", "bonus", "talk")
        tree = ttk.Treeview(holder, columns=columns, show="headings", selectmode="browse")
        for col, text, width in (("a", "Character", 220), ("b", "Partner", 220), ("c_at", "C at", 50),
                                 ("b_at", "B at", 50), ("a_at", "A at", 50),
                                 ("bonus", "Bonus at A (each unit)", 230), ("talk", "Conversations", 110)):
            tree.heading(col, text=text)
            tree.column(col, width=width, anchor="center" if col.endswith("_at") else "w",
                        stretch=col in ("a", "b", "bonus"))
        scroll = ttk.Scrollbar(holder, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=scroll.set)
        scroll.pack(side="right", fill="y")
        tree.pack(side="left", fill="both", expand=True)
        tree.bind("<Double-Button-1>", lambda e: self._open_pair())
        tree.bind("<Return>", lambda e: self._open_pair())
        self._pairs_tree = tree
        self._problems = ttk.Label(tab, text="", style="Warn.TLabel", wraplength=820, justify="left")
        self._problems.pack(anchor="w", pady=(8, 0))

    def _refresh_pairs(self) -> None:
        tree = self._pairs_tree
        tree.delete(*tree.get_children())
        view = self._view
        talks = self.conversation_ids()
        seen = set()
        for sl in view.lists:
            for slot in sl.slots:
                if slot.empty or (slot.partner, sl.owner) in seen:
                    continue
                seen.add((sl.owner, slot.partner))
                bonus = supports.pair_bonus(view.rows, view.affinity_of(sl.owner), view.affinity_of(slot.partner), 3)
                text = ", ".join(f"{n} +{v}" for n, v in zip(supports.BONUS_NAMES, bonus) if v) or "none"
                have = "".join(r if conversation_id(sl.owner, slot.partner, r) in talks else "·" for r in RANKS) \
                    if talks is not None else ""
                tree.insert("", "end", iid=f"{sl.owner}\t{slot.partner}", values=(
                    self._label(sl.owner), self._label(slot.partner), slot.c, slot.b, slot.a, text, have))
        problems = supports.validate_support_lists(view.lists)
        self._problems.config(text="\n".join(problems) if problems else "")

    def _open_pair(self) -> None:
        sel = self._pairs_tree.selection()
        if sel and self._open_character is not None:
            self._open_character(sel[0].split("\t")[0])

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
        self._apply_affinity_table()

    # -- conversations -------------------------------------------------------------------
    def conversation_ids(self) -> Optional[set]:
        """The support conversations in ``yell.m``, unsaved ones included (None: no file)."""
        if self._yell_path is not None and self._dialogue is not None \
                and self._dialogue.current_path == self._yell_path:
            return self._dialogue.message_ids()
        return read_conversation_ids(self._yell_path)

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
            self._refresh_pairs()  # conversations may have been added there

    @property
    def dialogue_editor(self):
        return self._dialogue

    def open_conversation(self, pid: str, partner: str, rank: str) -> None:
        """Show the pair's conversation of that rank in the Conversations tab,
        creating it from the background-scene template when missing."""
        if self._yell_path is None or self._make_dialogue_editor is None:
            return
        msg_id = conversation_id(pid, partner, rank)
        dialogue = self._ensure_dialogue()
        if msg_id not in dialogue.message_ids():
            # the Dialogue editor's background-scene template, with the pair's faces
            text = next((t for name, t in TEMPLATES.items() if "FCL_IKE" in t and "FCL_MIST" in t), "")
            text = text.replace("FCL_IKE", "FCL_" + self._view.fid_name(pid)).replace(
                "FCL_MIST", "FCL_" + self._view.fid_name(partner))
            if not dialogue.add_message(msg_id, text):
                return
        dialogue.select_message(msg_id)
        self._notebook.select(self._conversation_tab)
