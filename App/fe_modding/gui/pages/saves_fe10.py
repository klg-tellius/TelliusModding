"""Radiant Dawn RFEE01 NAND-save view used by :mod:`.saves`."""

from __future__ import annotations

import os
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import Optional

from ...formats import save_file_fe10 as sf
from ..widgets import info


class Fe10SaveEditor(ttk.Frame):
    """Structural editor for an unencrypted Dolphin ``FE10_US.dat`` save."""

    def __init__(self, parent: tk.Misc, shell):
        super().__init__(parent, style="Page.TFrame")
        self.shell = shell
        self._path: Optional[Path] = None
        self._save: Optional[sf.SaveFile] = None
        self._records: list[sf.SaveRecord] = []
        self._labels: list[str] = []

        head = ttk.Frame(self, style="Page.TFrame", padding=(28, 12, 28, 4))
        head.pack(fill="x")
        title = ttk.Frame(head, style="Page.TFrame")
        title.pack(anchor="w", pady=(0, 8))
        ttk.Label(title, text="Radiant Dawn saves", style="Title.TLabel").pack(side="left")
        info(title, "Open the unencrypted FE10_US.dat from Dolphin's RFEE01 NAND data folder. "
                    "The editor preserves unknown bytes and recomputes the game's CRC-32. Encrypted Wii "
                    "data.bin exports are not supported.").pack(side="left", padx=(8, 0), pady=(8, 0))

        top = ttk.Frame(self, style="Page.TFrame", padding=(28, 0))
        top.pack(fill="x")
        ttk.Button(top, text="Open NAND folder…", command=self._open_folder).pack(side="left")
        ttk.Button(top, text="Open FE10_US.dat…", command=self._open_file).pack(side="left", padx=(6, 0))
        self._save_button = ttk.Button(top, text="Save", command=self._save_file, state="disabled")
        self._save_button.pack(side="left", padx=(6, 0))
        self._copy_button = ttk.Button(top, text="Save data-folder copy…", command=self._save_copy,
                                       state="disabled")
        self._copy_button.pack(side="left", padx=(6, 0))
        self._check_button = ttk.Button(top, text="Check", command=self._check, state="disabled")
        self._check_button.pack(side="left", padx=(6, 0))
        self._play_button = ttk.Button(top, text="Play in Dolphin…", command=self._play, state="disabled")
        self._play_button.pack(side="left", padx=(6, 0))

        self._file_label = ttk.Label(self, text="No save open.", style="Muted.TLabel", padding=(28, 8, 28, 0))
        self._file_label.pack(fill="x")
        row = ttk.Frame(self, style="Page.TFrame", padding=(28, 8, 28, 0))
        row.pack(fill="x")
        ttk.Label(row, text="Record").pack(side="left")
        self._record_var = tk.StringVar()
        self._record_box = ttk.Combobox(row, textvariable=self._record_var, state="readonly", width=88)
        self._record_box.pack(side="left", padx=(6, 12))
        self._record_box.bind("<<ComboboxSelected>>", lambda _event: self._refresh())
        self._status = ttk.Label(row, style="Muted.TLabel")
        self._status.pack(side="left")

        notebook = ttk.Notebook(self)
        notebook.pack(fill="both", expand=True, padx=28, pady=(8, 20))
        overview = ttk.Frame(notebook, padding=12)
        convoy = ttk.Frame(notebook, padding=8)
        units = ttk.Frame(notebook, padding=8)
        flags = ttk.Frame(notebook, padding=8)
        sections = ttk.Frame(notebook, padding=8)
        raw = ttk.Frame(notebook, padding=8)
        notebook.add(overview, text="Overview")
        notebook.add(convoy, text="Convoy")
        notebook.add(units, text="Units")
        notebook.add(flags, text="Flags")
        notebook.add(sections, text="Sections")
        notebook.add(raw, text="Raw")

        self._summary = ttk.Label(overview, justify="left", anchor="nw")
        self._summary.pack(fill="x")
        self._edit_note = ttk.Label(overview, style="Muted.TLabel", wraplength=900, justify="left", text=(
            "The battle-state header below is the currently verified editable subset. Chapter is the "
            "game's internal chapter number; Phase is the internal army/phase byte. Other tagged data is "
            "shown read-only until its serializer has been fully mapped."))
        self._edit_note.pack(anchor="w", pady=(14, 6))
        fields = ttk.Frame(overview)
        fields.pack(anchor="w")
        self._chapter = tk.StringVar()
        self._phase = tk.StringVar()
        self._turn = tk.StringVar()
        for col, (label, variable, width) in enumerate((
                ("Chapter number", self._chapter, 10), ("Phase", self._phase, 8), ("Turn", self._turn, 10))):
            ttk.Label(fields, text=label).grid(row=0, column=col * 2, sticky="w", padx=(0 if col == 0 else 16, 5))
            entry = ttk.Entry(fields, textvariable=variable, width=width)
            entry.grid(row=0, column=col * 2 + 1, sticky="w")
            entry.bind("<Return>", self._commit_bmst)
            entry.bind("<FocusOut>", self._commit_bmst)
        self._field_entries = list(fields.winfo_children())[1::2]

        ttk.Label(convoy, style="Muted.TLabel", wraplength=900, justify="left", text=(
            "All 316 serialized storage slots are shown. Item numbers refer to FE10Data.cms. "
            "Ordinary items expose their state word. Existing forged items also expose their custom "
            "name, Might/Hit/Critical/Weight step counts, and RGBA colour; their pool-owning state "
            "word remains fixed.")).pack(anchor="w", pady=(0, 6))
        convoy_frame = ttk.Frame(convoy)
        convoy_frame.pack(fill="both", expand=True)
        self._convoy_tree = ttk.Treeview(convoy_frame, columns=("slot", "item", "name", "state", "forge"),
                                         show="headings", selectmode="browse", height=14)
        for key, title, width in (("slot", "Slot", 60), ("item", "Item #", 75),
                                  ("name", "Item", 300), ("state", "State", 100),
                                  ("forge", "Forged", 70)):
            self._convoy_tree.heading(key, text=title)
            self._convoy_tree.column(key, width=width, stretch=key == "name")
        convoy_scroll = ttk.Scrollbar(convoy_frame, command=self._convoy_tree.yview)
        self._convoy_tree.configure(yscrollcommand=convoy_scroll.set)
        convoy_scroll.pack(side="right", fill="y")
        self._convoy_tree.pack(side="left", fill="both", expand=True)
        self._convoy_tree.bind("<<TreeviewSelect>>", lambda _event: self._select_convoy())
        edit = ttk.Frame(convoy)
        edit.pack(fill="x", pady=(6, 0))
        self._convoy_item = tk.StringVar()
        self._convoy_state = tk.StringVar()
        ttk.Label(edit, text="Item number").pack(side="left")
        self._convoy_item_entry = ttk.Entry(edit, textvariable=self._convoy_item, width=10)
        self._convoy_item_entry.pack(side="left", padx=(5, 14))
        ttk.Label(edit, text="State (decimal or 0x…)").pack(side="left")
        self._convoy_state_entry = ttk.Entry(edit, textvariable=self._convoy_state, width=12)
        self._convoy_state_entry.pack(side="left", padx=(5, 8))
        self._convoy_apply = ttk.Button(edit, text="Apply", command=self._apply_convoy)
        self._convoy_apply.pack(side="left")
        forge_edit = ttk.Frame(convoy)
        forge_edit.pack(fill="x", pady=(6, 0))
        self._forge_name = tk.StringVar()
        self._forge_might = tk.StringVar()
        self._forge_hit = tk.StringVar()
        self._forge_critical = tk.StringVar()
        self._forge_weight = tk.StringVar()
        self._forge_colour = tk.StringVar()
        self._forge_entries = []
        for label, variable, width in (
                ("Forge name", self._forge_name, 18), ("Mt", self._forge_might, 5),
                ("Hit", self._forge_hit, 5), ("Crit", self._forge_critical, 5),
                ("Wt−", self._forge_weight, 5), ("RGBA", self._forge_colour, 12)):
            ttk.Label(forge_edit, text=label).pack(side="left", padx=(10 if self._forge_entries else 0, 4))
            entry = ttk.Entry(forge_edit, textvariable=variable, width=width)
            entry.pack(side="left")
            self._forge_entries.append(entry)

        ttk.Label(units, style="Muted.TLabel", wraplength=900, justify="left", text=(
            "UNIP is framed from the native 254-slot writer. Character and class names come from "
            "this save's ITBL; RelianceData from the open workspace determines which units carry "
            "the conditional support tail. Remaining unit substructures are preserved read-only."
        )).pack(anchor="w", pady=(0, 6))
        unit_frame = ttk.Frame(units)
        unit_frame.pack(fill="both", expand=True)
        self._unit_tree = ttk.Treeview(
            unit_frame, columns=("slot", "pid", "jid", "army", "skills", "items", "supports", "bytes"),
            show="headings", height=16)
        for key, title, width in (
                ("slot", "Slot", 55), ("pid", "Character", 190), ("jid", "Class", 170),
                ("army", "Army", 55), ("skills", "Skills", 60), ("items", "Items", 55),
                ("supports", "Support slots", 90), ("bytes", "Bytes", 65)):
            self._unit_tree.heading(key, text=title)
            self._unit_tree.column(key, width=width, stretch=key in ("pid", "jid"))
        unit_scroll = ttk.Scrollbar(unit_frame, command=self._unit_tree.yview)
        self._unit_tree.configure(yscrollcommand=unit_scroll.set)
        unit_scroll.pack(side="right", fill="y")
        self._unit_tree.pack(side="left", fill="both", expand=True)
        self._unit_status = ttk.Label(units, style="Muted.TLabel")
        self._unit_status.pack(anchor="w", pady=(6, 0))

        ttk.Label(flags, style="Muted.TLabel", wraplength=900, justify="left", text=(
            "BMST stores 128 event-script bits. Slots are shown in native order: campaign flags "
            "are registered from the low end and chapter flags from the high end. The exact name "
            "of a slot depends on the scripts used by this save, so editing is intentionally by "
            "stable slot number.")).pack(anchor="w", pady=(0, 6))
        flag_frame = ttk.Frame(flags)
        flag_frame.pack(fill="both", expand=True)
        self._flag_tree = ttk.Treeview(flag_frame, columns=("slot", "state"), show="headings",
                                       selectmode="browse", height=15)
        self._flag_tree.heading("slot", text="Slot")
        self._flag_tree.heading("state", text="State")
        self._flag_tree.column("slot", width=100, stretch=False)
        self._flag_tree.column("state", width=140, stretch=True)
        flag_scroll = ttk.Scrollbar(flag_frame, command=self._flag_tree.yview)
        self._flag_tree.configure(yscrollcommand=flag_scroll.set)
        flag_scroll.pack(side="right", fill="y")
        self._flag_tree.pack(side="left", fill="both", expand=True)
        self._flag_tree.bind("<Double-1>", lambda _event: self._toggle_flag())
        flag_actions = ttk.Frame(flags)
        flag_actions.pack(fill="x", pady=(6, 0))
        self._flag_toggle = ttk.Button(flag_actions, text="Toggle selected", command=self._toggle_flag,
                                       state="disabled")
        self._flag_toggle.pack(side="left")
        self._flag_tree.bind("<<TreeviewSelect>>", lambda _event: self._sync_flag_button())

        self._section_tree = ttk.Treeview(sections, columns=("offset", "size"), show="tree headings", height=11)
        self._section_tree.heading("#0", text="Tag")
        self._section_tree.heading("offset", text="Payload offset")
        self._section_tree.heading("size", text="Payload size")
        self._section_tree.column("#0", width=130, stretch=False)
        self._section_tree.column("offset", width=140, stretch=False)
        self._section_tree.column("size", width=140, stretch=False)
        self._section_tree.pack(fill="x")
        self._section_tree.bind("<<TreeviewSelect>>", lambda _event: self._fill_section_preview())
        self._section_text = self._text_area(sections)

        ttk.Label(raw, text="Selected physical record as it will be written (read only).",
                  style="Muted.TLabel").pack(anchor="w")
        self._raw_text = self._text_area(raw)
        self._sync()

    @staticmethod
    def _text_area(parent: tk.Misc) -> tk.Text:
        frame = ttk.Frame(parent)
        frame.pack(fill="both", expand=True, pady=(6, 0))
        text = tk.Text(frame, wrap="none", font=("Consolas", 10), height=15)
        scroll_y = ttk.Scrollbar(frame, orient="vertical", command=text.yview)
        scroll_x = ttk.Scrollbar(frame, orient="horizontal", command=text.xview)
        text.configure(yscrollcommand=scroll_y.set, xscrollcommand=scroll_x.set)
        scroll_y.pack(side="right", fill="y")
        scroll_x.pack(side="bottom", fill="x")
        text.pack(side="left", fill="both", expand=True)
        return text

    @property
    def dirty(self) -> bool:
        return bool(self._save and (self._save.system.dirty or any(r.dirty for r in self._save.records)))

    def _record(self) -> Optional[sf.SaveRecord]:
        value = self._record_var.get()
        return self._records[self._labels.index(value)] if value in self._labels else None

    def _confirm_discard(self) -> bool:
        return not self.dirty or messagebox.askyesno(
            "Discard changes?", "The open save has unsaved changes. Discard them?", parent=self)

    def _open_folder(self) -> None:
        if not self._confirm_discard():
            return
        chosen = filedialog.askdirectory(title="Choose RFEE01's NAND data folder", parent=self)
        if not chosen:
            return
        folder = Path(chosen)
        candidates = (folder / sf.FILE_NAME,
                      folder / "Wii" / "title" / "00010000" / "52464545" / "data" / sf.FILE_NAME,
                      folder / "title" / "00010000" / "52464545" / "data" / sf.FILE_NAME)
        path = next((item for item in candidates if item.is_file()), candidates[0])
        self.open_path(path)

    def _open_file(self) -> None:
        if not self._confirm_discard():
            return
        chosen = filedialog.askopenfilename(title="Open FE10_US.dat", parent=self,
                                            filetypes=[("Radiant Dawn NAND save", "FE10_US.dat"),
                                                       ("DAT files", "*.dat"), ("All files", "*.*")])
        if chosen:
            self.open_path(Path(chosen))

    def open_path(self, path: Path) -> bool:
        try:
            save = sf.SaveFile.from_path(path)
        except (OSError, ValueError) as exc:
            messagebox.showerror("Could not open the save", str(exc), parent=self)
            return False
        if path.is_dir():
            path = path / sf.FILE_NAME
        self._path, self._save = path, save
        self._records = [save.system, *save.records]
        active = save.active_records()
        self._labels = [sf.record_label(record, active) for record in self._records]
        self._record_box.configure(values=self._labels)
        preferred = active[0] if active else save.system
        self._record_var.set(self._labels[self._records.index(preferred)])
        self._file_label.configure(text=str(path))
        self._refresh()
        return True

    def _commit_bmst(self, _event=None) -> None:
        record = self._record()
        if record is None or record.empty or record.section("BMST") is None:
            return
        try:
            chapter, phase, turn = (int(value.get(), 0) for value in (self._chapter, self._phase, self._turn))
            record.chapter_number = chapter
            record.army_phase = phase
            record.turn = turn
        except ValueError as exc:
            messagebox.showerror("Invalid battle state", str(exc), parent=self)
        self._refresh()

    def _refresh(self) -> None:
        record = self._record()
        if record is None:
            self._sync()
            return
        if record.empty:
            summary = f"Offset 0x{record.offset:06X}\nEmpty file record (0xFF-filled)."
        else:
            summary = (f"Offset 0x{record.offset:06X}\nMagic {record.magic.decode('ascii', 'replace')} · "
                       f"version 0x{record.version:08X} · format 0x{record.format_version:08X}\n"
                       f"Sequence {record.sequence} · stored CRC 0x{record.stored_crc:08X} · "
                       f"checksum {'valid' if record.crc_ok else 'invalid'}")
        self._summary.configure(text=summary)
        editable = not record.empty and record.section("BMST") is not None
        for entry in self._field_entries:
            entry.configure(state="normal" if editable else "disabled")
        if editable:
            self._chapter.set(str(record.chapter_number))
            self._phase.set(str(record.army_phase))
            self._turn.set(str(record.turn))
        else:
            self._chapter.set("")
            self._phase.set("")
            self._turn.set("")
        self._section_tree.delete(*self._section_tree.get_children())
        for index, section in enumerate(record.sections):
            self._section_tree.insert("", "end", iid=str(index), text=section.name,
                                      values=(f"0x{section.data_offset:05X}", f"{section.size} (0x{section.size:X})"))
        self._fill_section_preview()
        self._fill_convoy()
        self._fill_units()
        self._fill_flags()
        self._fill_hex(self._raw_text, record.build())
        self._sync()

    def _fill_section_preview(self) -> None:
        record = self._record()
        selected = self._section_tree.selection()
        if record is None or not selected:
            self._set_text(self._section_text, "")
            return
        section = record.sections[int(selected[0])]
        self._fill_hex(self._section_text, record.section_bytes(section.name), base=section.data_offset)

    def _item_name(self, number: int) -> str:
        if not number:
            return "(empty)"
        session = getattr(self.shell, "session", None)
        data = getattr(session, "fe10", None)
        if data is None or not 0 < number <= len(data.items):
            return f"#{number}"
        values = data.items[number - 1].values
        item_id = values.get("iid") or values.get("id") or f"#{number}"
        key = values.get("miid") or values.get("name") or values.get("name_key")
        index = getattr(self.shell, "index", None)
        title = index.text(key) if index is not None and getattr(index, "ready", False) and key else ""
        return f"{title} ({item_id})" if title else str(item_id)

    def _fill_convoy(self) -> None:
        selected = self._convoy_tree.selection()
        self._convoy_tree.delete(*self._convoy_tree.get_children())
        record = self._record()
        if record is None or record.empty or record.section("SOKO") is None:
            self._set_convoy_controls(None)
            return
        try:
            items = record.convoy_items()
        except ValueError:
            self._set_convoy_controls(None)
            return
        for item in items:
            self._convoy_tree.insert("", "end", iid=str(item.slot),
                                     values=(item.slot + 1, item.item_number, self._item_name(item.item_number),
                                             f"0x{item.state:04X}", "yes" if item.forged else ""))
        if selected and self._convoy_tree.exists(selected[0]):
            self._convoy_tree.selection_set(selected[0])
        self._select_convoy()

    def _set_convoy_controls(self, item: Optional[sf.ConvoyItem]) -> None:
        enabled = item is not None
        forged = enabled and item.forged
        self._convoy_item.set(str(item.item_number) if item is not None else "")
        self._convoy_state.set(f"0x{item.state:04X}" if item is not None else "")
        self._convoy_item_entry.configure(state="normal" if enabled else "disabled")
        self._convoy_state_entry.configure(state="normal" if enabled and not forged else "disabled")
        self._convoy_apply.configure(state="normal" if enabled else "disabled")
        values = item.forge_values if forged else None
        self._forge_name.set(item.forge_name_bytes.decode("shift_jis") if forged else "")
        self._forge_might.set(str(values.might_steps) if values else "")
        self._forge_hit.set(str(values.hit_steps) if values else "")
        self._forge_critical.set(str(values.critical_steps) if values else "")
        self._forge_weight.set(str(values.weight_reduction_steps) if values else "")
        self._forge_colour.set(
            f"#{values.red:02X}{values.green:02X}{values.blue:02X}{values.alpha:02X}" if values else "")
        for entry in self._forge_entries:
            entry.configure(state="normal" if forged else "disabled")

    def _fill_units(self) -> None:
        self._unit_tree.delete(*self._unit_tree.get_children())
        record = self._record()
        if record is None or record.empty or record.section("UNIP") is None:
            self._unit_status.configure(text="No serialized unit table in this record.")
            return
        session = getattr(self.shell, "session", None)
        database = getattr(session, "fe10", None)
        if database is None:
            self._unit_status.configure(
                text="Open an extracted Radiant Dawn workspace to frame RelianceData support tails.")
            return
        try:
            tables = record.id_tables()
            counts_by_pid = {
                row.values["pid"]: len(row.lists["partners"])
                for row in database.table("support")
            }
            support_counts = {
                number: counts_by_pid.get("PID_" + short_name, 0)
                for number, short_name in enumerate(tables.characters, 1)
            }
            parsed = record.unit_records(support_counts)
            occupied = [unit for unit in parsed if not unit.empty]
            for unit in occupied:
                pid = ("PID_" + tables.characters[unit.person_number - 1]
                       if 0 < unit.person_number <= len(tables.characters)
                       else f"#{unit.person_number}")
                jid = ("JID_" + tables.classes[unit.class_number - 1]
                       if 0 < unit.class_number <= len(tables.classes)
                       else f"#{unit.class_number}")
                item_count = sum(item.item_number != 0 for item in unit.items)
                self._unit_tree.insert(
                    "", "end", iid=str(unit.slot),
                    values=(unit.slot + 1, pid, jid, unit.army, len(unit.skills), item_count,
                            unit.support_slot_count, unit.size))
            consumed = sum(unit.size for unit in parsed)
            self._unit_status.configure(
                text=f"{len(occupied)} occupied of {len(parsed)} slots · structurally consumed "
                     f"{consumed} bytes")
        except (KeyError, ValueError, IndexError, UnicodeError) as exc:
            self._unit_status.configure(text=f"Could not decode UNIP: {exc}")

    def _select_convoy(self) -> None:
        record = self._record()
        selected = self._convoy_tree.selection()
        if record is None or not selected:
            self._set_convoy_controls(None)
            return
        try:
            item = record.convoy_items()[int(selected[0])]
        except (ValueError, IndexError):
            self._set_convoy_controls(None)
            return
        self._set_convoy_controls(item)

    def _apply_convoy(self) -> None:
        record = self._record()
        selected = self._convoy_tree.selection()
        if record is None or not selected:
            return
        try:
            slot = int(selected[0])
            item = record.convoy_items()[slot]
            if item.forged:
                colour_text = self._forge_colour.get().strip().removeprefix("#").removeprefix("0x")
                if len(colour_text) != 8:
                    raise ValueError("RGBA must contain exactly eight hexadecimal digits")
                colour = bytes.fromhex(colour_text)
                payload = sf.ForgePayload(
                    int(self._forge_might.get(), 0), int(self._forge_hit.get(), 0),
                    int(self._forge_critical.get(), 0), int(self._forge_weight.get(), 0), *colour)
                record.update_forged_convoy_item(
                    slot, item_number=int(self._convoy_item.get(), 0),
                    name=self._forge_name.get(), payload=payload)
            else:
                record.set_convoy_item(slot, int(self._convoy_item.get(), 0),
                                       int(self._convoy_state.get(), 0))
        except (ValueError, IndexError) as exc:
            messagebox.showerror("Invalid convoy item", str(exc), parent=self)
            return
        self._refresh()
        if self._convoy_tree.exists(selected[0]):
            self._convoy_tree.selection_set(selected[0])
            self._convoy_tree.see(selected[0])

    def _fill_flags(self) -> None:
        selected = self._flag_tree.selection()
        self._flag_tree.delete(*self._flag_tree.get_children())
        record = self._record()
        if record is None or record.empty or record.section("BMST") is None:
            self._sync_flag_button()
            return
        try:
            bits = record.script_flags()
        except ValueError:
            self._sync_flag_button()
            return
        for index, enabled in enumerate(bits):
            self._flag_tree.insert("", "end", iid=str(index),
                                   values=(index, "On" if enabled else "Off"))
        if selected and self._flag_tree.exists(selected[0]):
            self._flag_tree.selection_set(selected[0])
        self._sync_flag_button()

    def _sync_flag_button(self) -> None:
        self._flag_toggle.configure(state="normal" if self._flag_tree.selection() else "disabled")

    def _toggle_flag(self) -> None:
        record = self._record()
        selected = self._flag_tree.selection()
        if record is None or not selected:
            return
        index = int(selected[0])
        try:
            record.set_script_flag(index, not record.script_flags()[index])
        except (ValueError, IndexError) as exc:
            messagebox.showerror("Could not edit flag", str(exc), parent=self)
            return
        self._refresh()
        if self._flag_tree.exists(str(index)):
            self._flag_tree.selection_set(str(index))
            self._flag_tree.see(str(index))

    @staticmethod
    def _set_text(widget: tk.Text, value: str) -> None:
        widget.configure(state="normal")
        widget.delete("1.0", "end")
        widget.insert("1.0", value)
        widget.configure(state="disabled")

    def _fill_hex(self, widget: tk.Text, data: bytes, *, base: int = 0) -> None:
        lines = []
        for offset in range(0, len(data), 16):
            row = data[offset:offset + 16]
            ascii_ = "".join(chr(byte) if 32 <= byte < 127 else "." for byte in row)
            lines.append(f"{base + offset:06X}  {row.hex(' '):47}  {ascii_}")
        self._set_text(widget, "\n".join(lines))

    def _write(self, path: Path) -> bool:
        if self._save is None:
            return False
        temp = path.with_name(path.name + ".tmp")
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            temp.write_bytes(self._save.to_bytes())
            os.replace(temp, path)
        except OSError as exc:
            try:
                temp.unlink(missing_ok=True)
            except OSError:
                pass
            messagebox.showerror("Could not write the save", str(exc), parent=self)
            return False
        self.shell.changelog.append(path.name, "Edited Radiant Dawn NAND save")
        return True

    def _save_file(self) -> None:
        if self._path is None or self._save is None:
            return
        selected = self._record_var.get()
        if self._write(self._path) and self.open_path(self._path) and selected in self._labels:
            self._record_var.set(selected)
            self._refresh()

    def _save_copy(self) -> None:
        if self._save is None:
            return
        chosen = filedialog.askdirectory(title="Choose the parent for an RFEE01 data-folder copy", parent=self)
        if not chosen:
            return
        selected = Path(chosen)
        data_dir = selected if selected.name.lower() == "data" else selected / "data"
        destination = data_dir / sf.FILE_NAME
        if destination.exists() and not messagebox.askyesno(
                "Replace save copy?", f"{destination} already exists. Replace it?", parent=self):
            return
        if not self._write(destination):
            return
        banner = self._path.parent / "banner.bin" if self._path else None
        try:
            if banner is not None and banner.is_file():
                (data_dir / "banner.bin").write_bytes(banner.read_bytes())
        except OSError as exc:
            messagebox.showwarning("Save copied without banner", str(exc), parent=self)
        messagebox.showinfo("Save copy created", f"Created {data_dir}", parent=self)

    def _check(self) -> None:
        if self._save is None:
            return
        try:
            rebuilt = sf.SaveFile.from_bytes(self._save.to_bytes())
            problems = sf.validate(rebuilt)
        except ValueError as exc:
            problems = [str(exc)]
        if problems:
            messagebox.showwarning("Problems", "\n".join(problems[:30]), parent=self)
        else:
            messagebox.showinfo("Check", "All populated records have supported headers and valid checksums.",
                                parent=self)

    def _play(self) -> None:
        if self._save is None:
            return
        banner_path = self._path.parent / "banner.bin" if self._path else None
        try:
            banner = banner_path.read_bytes() if banner_path is not None and banner_path.is_file() else None
        except OSError as exc:
            messagebox.showerror("Could not read banner.bin", str(exc), parent=self)
            return
        self.shell.play_from_wii_save(self._save.to_bytes(), banner)

    def _sync(self) -> None:
        has = self._save is not None
        self._save_button.configure(state="normal" if self.dirty else "disabled")
        self._copy_button.configure(state="normal" if has else "disabled")
        self._check_button.configure(state="normal" if has else "disabled")
        self._play_button.configure(state="normal" if has and self.shell.extracted else "disabled")
        self._status.configure(text="Unsaved changes" if self.dirty else "")
