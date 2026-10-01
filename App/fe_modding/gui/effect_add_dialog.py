"""Modal dialog to add a visual effect: a new ``yme/EID_*.cmp`` pack (cloned
from an existing effect, or imported from a pack file) plus its record in
``FE8Effect.bin``, or just the record for a pack that has none."""

from __future__ import annotations

import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import Callable

from ..formats import effects
from ..project import ModProject
from .changelog import ChangeLog

CLONE, FILE, KEEP = "clone", "file", "keep"


class EffectAddDialog(tk.Toplevel):
    def __init__(
        self,
        parent: tk.Misc,
        project: ModProject,
        changelog: ChangeLog,
        entries: list[effects.EffectEntry],
        on_done: Callable[[str], None],
        preset: effects.EffectEntry | None = None,
    ):
        """``preset`` is an unregistered pack: the name is fixed and its pack is kept."""
        super().__init__(parent)
        self.title("Register effect" if preset else "Add visual effect")
        self.transient(parent.winfo_toplevel())
        self.resizable(False, False)
        self._project, self._changelog, self._on_done = project, changelog, on_done
        self._files = project.extracted_dir / "files"
        self._entries = entries
        self._registered = [e.name for e in entries if e.registered]
        self._effect_name = tk.StringVar(value=preset.name if preset else "EID_")
        self._mode = tk.StringVar(value=KEEP if preset else CLONE)
        self._clone = tk.StringVar(value=self._registered[0] if self._registered else "")
        self._template = tk.StringVar(value=self._registered[0] if self._registered else "")
        self._file = tk.StringVar()

        body = ttk.Frame(self, padding=12)
        body.pack(fill="both", expand=True)
        body.columnconfigure(1, weight=1)
        row = 0
        ttk.Label(body, text="Effect name").grid(row=row, column=0, sticky="w")
        name_entry = ttk.Entry(body, textvariable=self._effect_name, width=34, state="disabled" if preset else "normal")
        name_entry.grid(row=row, column=1, columnspan=2, sticky="ew", padx=(8, 0))
        row += 1
        if preset:
            ttk.Label(body, text="The existing pack is kept; only the registry record is added.",
                      style="Muted.TLabel").grid(row=row, column=0, columnspan=3, sticky="w", pady=(6, 0))
            row += 1
        else:
            ttk.Radiobutton(body, text="Clone effect", value=CLONE, variable=self._mode).grid(
                row=row, column=0, sticky="w", pady=(8, 0))
            ttk.Combobox(body, textvariable=self._clone, values=self._registered, state="readonly").grid(
                row=row, column=1, columnspan=2, sticky="ew", padx=(8, 0), pady=(8, 0))
            row += 1
            ttk.Radiobutton(body, text="Import pack", value=FILE, variable=self._mode).grid(
                row=row, column=0, sticky="w", pady=(4, 0))
            ttk.Entry(body, textvariable=self._file).grid(row=row, column=1, sticky="ew", padx=(8, 0), pady=(4, 0))
            ttk.Button(body, text="Browse...", command=self._browse).grid(row=row, column=2, padx=(6, 0), pady=(4, 0))
            row += 1
        ttk.Label(body, text="Copy flags from").grid(row=row, column=0, sticky="w", pady=(8, 0))
        ttk.Combobox(body, textvariable=self._template, values=self._registered, state="readonly").grid(
            row=row, column=1, columnspan=2, sticky="ew", padx=(8, 0), pady=(8, 0))
        row += 1
        ttk.Label(body, text="The registry flags are not fully decoded, so a new record copies them\n"
                  "from an existing effect of a similar kind.", style="Muted.TLabel", justify="left").grid(
            row=row, column=0, columnspan=3, sticky="w", pady=(4, 0))
        row += 1
        buttons = ttk.Frame(body)
        buttons.grid(row=row, column=0, columnspan=3, sticky="e", pady=(12, 0))
        ttk.Button(buttons, text="Cancel", command=self.destroy).pack(side="right")
        ttk.Button(buttons, text="Add", command=self._commit).pack(side="right", padx=(0, 6))
        self.grab_set()

    def _browse(self) -> None:
        path = filedialog.askopenfilename(parent=self, title="Effect pack",
                                          filetypes=[("Effect pack", "*.cmp"), ("All files", "*.*")])
        if path:
            self._file.set(path)
            self._mode.set(FILE)

    def _commit(self) -> None:
        name = self._effect_name.get().strip()
        try:
            if not effects.NAME_RE.match(name):
                raise effects.EffectError("Effect names look like EID_SOMETHING (letters, digits, underscore).")
            mode = self._mode.get()
            registry_file = effects.registry_path(self._files)
            registry = registry_file.read_bytes()
            flags = self._template_flags(registry)
            outputs: dict[Path, bytes] = {}
            if mode != KEEP:
                if (self._files / effects.PACK_DIR / f"{name}.cmp").exists():
                    raise effects.EffectError(f"{name}.cmp already exists.")
                source = (self._files / effects.PACK_DIR / f"{self._clone.get()}.cmp" if mode == CLONE
                          else Path(self._file.get()))
                if not source.is_file():
                    raise effects.EffectError("Pick a source effect or pack file.")
                parts = effects.read_effect_pack(source.read_bytes())
                effects.validate_pack(parts)
                outputs[effects.pack_path(self._files, name)] = effects.build_effect_pack(
                    effects.rename_pack(parts, name))
            outputs[registry_file] = effects.add_registry_record(registry, name, flags=flags)
        except (effects.EffectError, OSError) as exc:
            messagebox.showerror("Visual effects", str(exc), parent=self)
            return
        # Every output is built; only now touch the project.
        for path, data in outputs.items():
            path.parent.mkdir(parents=True, exist_ok=True)
            self._project.write_keeping_original(path, data)
        self._changelog.append("Visual effects", f"Added {name}")
        self.destroy()
        self._on_done(name)

    def _template_flags(self, registry: bytes) -> int:
        from ..formats import effect_registry

        template = self._template.get()
        for record in effect_registry.read_effect_registry(registry):
            if record.eid_name == template:
                return record.flags
        return 0x00000500
