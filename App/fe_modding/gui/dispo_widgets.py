"""Form pieces shared by the Deployment and Build tabs for the deployment
bytes that are not plain numbers or labels: the unit flags (field 38), the
per-item flags (fields 40-47), the army (field 37) and a section's header
(its ``GroupData`` army, the occupied-tile byte and the mode byte).
"""

from __future__ import annotations

import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk
from typing import Optional

from ..formats import dispo, fe8data


class FlagChecks(ttk.Frame):
    """One checkbox per bit of ``bits`` (``(mask, label, help)`` rows).
    :meth:`value` returns ``original`` with those bits set or cleared, so
    bits the list doesn't name are kept."""

    def __init__(self, parent: tk.Misc, original: int, bits, *, columns: int = 1, show_help: bool = False):
        super().__init__(parent)
        self._original = int(original)
        self._vars: dict[int, tk.BooleanVar] = {}
        for i, (mask, label, help_text) in enumerate(bits):
            var = tk.BooleanVar(value=bool(self._original & mask))
            self._vars[mask] = var
            cell = ttk.Frame(self)
            cell.grid(row=i // columns, column=i % columns, sticky="w", padx=(0, 8))
            ttk.Checkbutton(cell, text=label, variable=var).pack(anchor="w")
            if show_help:
                ttk.Label(cell, text=help_text, style="Muted.TLabel", wraplength=340,
                          justify="left").pack(anchor="w", padx=(22, 0))

    def value(self) -> int:
        value = self._original
        for mask, var in self._vars.items():
            value = (value | mask) if var.get() else (value & ~mask)
        return value


def faction_choices() -> list[str]:
    return [f"{k} {name}" for k, name in dispo.FACTION_NAMES.items()]


def faction_text(value: int) -> str:
    return f"{value} {dispo.FACTION_NAMES[value]}" if value in dispo.FACTION_NAMES else str(value)


def parse_leading_int(text: str) -> int:
    """``"3 Partner"`` -> 3; also plain numbers (``"0x10"`` too)."""
    token = text.strip().split(" ", 1)[0]
    return int(token, 0)


def read_group_keys(files_dir: Path) -> list[Optional[str]]:
    """The project's ``GroupData`` keys, or an empty list when unreadable."""
    try:
        return fe8data.read_group_keys((files_dir / "FE8Data.bin").read_bytes())
    except Exception:  # noqa: BLE001 - a broken FE8Data.bin just leaves numbers
        return []


def group_choices(keys: list[Optional[str]]) -> list[str]:
    return [fe8data.group_label(i, keys) for i in range(max(len(keys), 1))]


def group_text(value: int, keys: list[Optional[str]]) -> str:
    return fe8data.group_label(value, keys) if keys or value == 0 else str(value)


class SectionHeaderFrame(ttk.Frame):
    """Army, occupied-tile and mode controls for one section header."""

    def __init__(self, parent: tk.Misc, header: dispo.SectionHeader, keys: list[Optional[str]]):
        super().__init__(parent)
        self._keys = keys
        ttk.Label(self, text="Army").grid(row=0, column=0, sticky="w", pady=2, padx=(0, 6))
        self._group = tk.StringVar(value=group_text(header.group, keys))
        ttk.Combobox(self, textvariable=self._group, values=group_choices(keys), width=28).grid(
            row=0, column=1, sticky="w", pady=2)
        ttk.Label(self, text="Every unit of the section joins this army (0 keeps each unit's current one).",
                  style="Muted.TLabel", wraplength=340, justify="left").grid(row=1, column=0, columnspan=2, sticky="w")
        self._occupied = tk.BooleanVar(value=bool(header.occupied_ok))
        self._occupied_raw = header.occupied_ok
        ttk.Checkbutton(self, text="Place units even on occupied tiles", variable=self._occupied).grid(
            row=2, column=0, columnspan=2, sticky="w", pady=(6, 2))
        ttk.Label(self, text="Mode").grid(row=3, column=0, sticky="w", pady=2)
        self._mode = tk.StringVar(value=str(header.mode))
        ttk.Spinbox(self, from_=0, to=255, textvariable=self._mode, width=5).grid(row=3, column=1, sticky="w", pady=2)
        ttk.Label(self, text="4 on every vanilla section.", style="Muted.TLabel").grid(
            row=4, column=0, columnspan=2, sticky="w")

    def header(self) -> dispo.SectionHeader:
        """The edited header; raises ValueError on bad input."""
        try:
            group = parse_leading_int(self._group.get())
            mode = int(self._mode.get(), 0)
        except ValueError:
            raise ValueError("Army and mode must be numbers (pick an army from the list).") from None
        occupied = (self._occupied_raw or 1) if self._occupied.get() else 0
        header = dispo.SectionHeader(mode, occupied, group)
        for value in (header.mode, header.group):
            if not 0 <= value <= 255:
                raise ValueError(f"{value} is outside 0..255.")
        return header


class SectionDialog(tk.Toplevel):
    """Edit a unit section's header; ``result`` is the new header or None."""

    def __init__(self, parent: tk.Misc, section_name: str, header: dispo.SectionHeader, keys):
        super().__init__(parent)
        self.title(f"Section {section_name}")
        self.resizable(False, False)
        self.result: Optional[dispo.SectionHeader] = None
        frame = ttk.Frame(self, padding=12)
        frame.pack(fill="both", expand=True)
        self._form = SectionHeaderFrame(frame, header, keys)
        self._form.pack(anchor="w")
        buttons = ttk.Frame(frame)
        buttons.pack(fill="x", pady=(10, 0))
        ttk.Button(buttons, text="Cancel", command=self.destroy).pack(side="right")
        ttk.Button(buttons, text="Apply", command=self._apply).pack(side="right", padx=(0, 6))
        self.transient(parent)
        self.grab_set()

    def _apply(self) -> None:
        try:
            self.result = self._form.header()
        except ValueError as exc:
            messagebox.showerror("Section", str(exc), parent=self)
            return
        self.destroy()
