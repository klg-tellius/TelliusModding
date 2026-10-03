"""Game Code: patches and tunable constants written straight into ``sys/main.dol``
(``game_code/``), for the US, PAL and JP builds of Path of Radiance.

Each change is saved to the extracted ``main.dol`` at once and listed in the session's
changes; building packages it like any other extracted file. An entry whose code was not
found in the project's build is shown greyed with the reason, never written blind."""

from __future__ import annotations

import tkinter as tk
from tkinter import messagebox, ttk

from ...exceptions import ModdingError
from ...game_code.catalog import CATALOG, Patch, State, Tunable
from ...game_code.editor import CodeEditor
from ...game_code.entries import G_GROWTH, G_PROCS, PROCS, SCALE_DENOMINATOR, STATS
from ..shell import Page
from ..widgets import ScrollFrame, section_header

GROUP_NOTES = {
    "Combat rules": "Numbers the battle engine uses. The vanilla value is shown beside each field.",
    G_PROCS: "A skill's chance is its formula (for example Skill / 2) times the multiplier, plus the bonus; "
             "the game caps it at 100. Deathblow only has a multiplier: its chance is 0 unless the hit "
             "is a critical.",
    G_GROWTH: "How many points a level-up gives. Random mode rolls each stat (+1 per 100% of growth and per "
              "success); fixed mode adds the growth rate to a hidden counter and pays out when it passes the "
              "threshold. The mode is chosen per save unless forced here.",
}


class _Row:
    """One editable value: a spinbox bound to a tunable (shown = stored * factor)."""

    def __init__(self, page: "CodePage", parent: tk.Misc, tunable: Tunable, factor: float = 1.0, width: int = 7):
        self.page, self.tunable, self.factor = page, tunable, factor
        self.is_float = any(f.kind == "f32" for fields in tunable.versions.values() for f in fields)
        step = 0.25 if self.is_float else factor
        self.var = tk.StringVar()
        self.box = ttk.Spinbox(
            parent, textvariable=self.var, width=width, increment=step,
            from_=tunable.minimum * factor, to=tunable.maximum * factor, command=self.apply)
        self.box.bind("<Return>", lambda e: self.apply())
        self.box.bind("<FocusOut>", lambda e: self.apply())

    def refresh(self) -> None:
        status = self.page.editor.status(self.tunable)
        available = status.state not in (State.UNAVAILABLE, State.CONFLICT)
        self.box.configure(state="normal" if available else "disabled")
        value = status.value if status.value is not None else self.tunable.default
        self.var.set(f"{value * self.factor:g}")

    def apply(self) -> None:
        try:
            value = float(self.var.get()) / self.factor
            value = value if self.is_float else round(value)
        except ValueError:
            self.refresh()
            return
        value = max(self.tunable.minimum, min(self.tunable.maximum, value))
        if value == self.page.editor.status(self.tunable).value:
            self.refresh()
            return
        self.page.run(lambda: self.page.editor.set_value(self.tunable, value))


class CodePage(Page):
    kind = "code"

    def __init__(self, shell):
        super().__init__(shell)
        self.editor: CodeEditor | None = None
        self._rows: list[_Row] = []
        self._checks: list[tuple[Patch, tk.BooleanVar, ttk.Checkbutton]] = []
        self._summary: ttk.Label | None = None
        self._note: ttk.Label | None = None
        self._scroll = ScrollFrame(self, padding=(28, 12, 28, 28))
        self._scroll.pack(fill="both", expand=True)

    def crumbs(self, route):
        return [("Tools", ("tools",)), ("Game Code", None)]

    def history_label(self, route):
        return "Game Code"

    def show(self, route) -> bool:
        try:
            self.editor = CodeEditor(self.project.extracted_dir, self.project.write_keeping_original)
        except (OSError, ModdingError) as exc:
            self.editor = None
            self._render(error=f"Could not open sys/main.dol: {exc}")
            return True
        self._render()
        return True

    # -- editing ---------------------------------------------------------------------------------
    def run(self, action) -> None:
        try:
            description = action()
        except ModdingError as exc:
            messagebox.showerror("Game Code", str(exc), parent=self)
        else:
            if description:
                self.shell.changelog.append("main.dol", description)
        self._refresh()

    def _toggle(self, patch: Patch, var: tk.BooleanVar) -> None:
        self.run(lambda: self.editor.set_patch(patch, var.get()))

    def _reset_all(self) -> None:
        if not messagebox.askyesno("Game Code", "Put every game-code value back to vanilla?", parent=self):
            return
        count = self.editor.reset_all()
        self.shell.changelog.append("main.dol", f"Reset {count} game-code setting{'s' if count != 1 else ''}")
        self._refresh()

    def _refresh(self) -> None:
        if self.editor is None or self._summary is None:
            return
        for row in self._rows:
            row.refresh()
        for patch, var, box in self._checks:
            status = self.editor.status(patch)
            box.configure(state="disabled" if status.state in (State.UNAVAILABLE, State.CONFLICT) else "normal")
            var.set(status.state == State.APPLIED)
        self._note.configure(text=("Identical to the retail executable." if self.editor.dol.sha1() == self.editor.version.dol_sha1
                                   else "Differs from the retail executable."))
        count = len(self.editor.modified_entries())
        self._summary.configure(text="Vanilla: nothing changed." if not count else
                                f"{count} setting{'s' if count != 1 else ''} changed from vanilla.")

    # -- layout ----------------------------------------------------------------------------------
    def _render(self, error: str = "") -> None:
        body = self._scroll.body
        for child in body.winfo_children():
            child.destroy()
        self._rows.clear()
        self._checks.clear()
        self._summary = None
        ttk.Label(body, text="Game Code", style="Title.TLabel").pack(anchor="w")
        if error:
            ttk.Label(body, text=error, style="Warn.TLabel", wraplength=720, justify="left").pack(anchor="w", pady=8)
            return
        editor = self.editor
        ident = editor.identification
        title = ident.version.label if ident.version else "Unrecognised executable"
        ttk.Label(body, text=f"{title}  ·  sys/main.dol", style="Muted.TLabel").pack(anchor="w", pady=(2, 14))

        card = ttk.Frame(body, style="Surface.TFrame", padding=18)
        card.pack(fill="x", pady=(0, 6))
        if not editor.supported:
            ttk.Label(card, text=ident.note or "This main.dol is not a known build.", style="SurfaceWarn.TLabel",
                      wraplength=720, justify="left").pack(anchor="w")
            ttk.Label(card, text="Game-code editing supports the US, PAL and JP builds of Path of Radiance.",
                      style="SurfaceMuted.TLabel", wraplength=720, justify="left").pack(anchor="w", pady=(4, 0))
            return
        self._note = ttk.Label(card, text="", style="SurfaceMuted.TLabel", wraplength=720, justify="left")
        self._note.pack(anchor="w")
        bottom = ttk.Frame(card, style="Surface.TFrame")
        bottom.pack(fill="x", pady=(8, 0))
        self._summary = ttk.Label(bottom, text="", style="Surface.TLabel")
        self._summary.pack(side="left")
        ttk.Button(bottom, text="Reset everything to vanilla", command=self._reset_all).pack(side="right")

        for group, entries in CATALOG.groups().items():
            shown = [e for e in entries if not getattr(e, "internal", False)]
            if not shown:
                continue
            section_header(body, group).pack(anchor="w", pady=(24, 4))
            if group in GROUP_NOTES:
                ttk.Label(body, text=GROUP_NOTES[group], style="Muted.TLabel", wraplength=720,
                          justify="left").pack(anchor="w", pady=(0, 8))
            panel = ttk.Frame(body, style="Surface.TFrame", padding=18)
            panel.pack(fill="x")
            if group == G_PROCS:
                self._proc_table(panel)
            elif group == G_GROWTH:
                plain = [e for e in shown if not e.id.startswith(("growth.random.", "growth.fixed."))
                         or e.id.startswith("growth.fixed_")]
                for i, entry in enumerate(plain):
                    if i:
                        ttk.Separator(panel).pack(fill="x", pady=10)
                    self._entry_row(panel, entry)
                ttk.Separator(panel).pack(fill="x", pady=10)
                self._growth_table(panel)
            else:
                for i, entry in enumerate(shown):
                    if i:
                        ttk.Separator(panel).pack(fill="x", pady=10)
                    self._entry_row(panel, entry)
        self._refresh()

    def _entry_row(self, parent: tk.Misc, entry) -> None:
        row = ttk.Frame(parent, style="Surface.TFrame")
        row.pack(fill="x")
        text = ttk.Frame(row, style="Surface.TFrame")
        text.pack(side="left", fill="x", expand=True)
        is_patch = isinstance(entry, Patch)
        if is_patch:
            var = tk.BooleanVar()
            box = ttk.Checkbutton(text, text=entry.name, variable=var, style="Surface.TCheckbutton",
                                  command=lambda p=entry, v=var: self._toggle(p, v))
            box.pack(anchor="w")
            self._checks.append((entry, var, box))
        else:
            ttk.Label(text, text=entry.name, style="Surface.TLabel").pack(anchor="w")
        ttk.Label(text, text=entry.description, style="SurfaceMuted.TLabel", wraplength=560,
                  justify="left").pack(anchor="w", padx=(24 if is_patch else 0, 0))
        if isinstance(entry, Tunable):
            control = ttk.Frame(row, style="Surface.TFrame")
            control.pack(side="right")
            value = _Row(self, control, entry)
            value.box.pack(side="left")
            ttk.Label(control, text=f" {entry.unit}   vanilla {entry.default:g}",
                      style="SurfaceCaption.TLabel").pack(side="left")
            ttk.Button(control, text="Reset", width=6,
                       command=lambda e=entry: self.run(lambda: self.editor.reset(e))).pack(side="left", padx=(8, 0))
            self._rows.append(value)

    def _proc_table(self, parent: tk.Misc) -> None:
        grid = ttk.Frame(parent, style="Surface.TFrame")
        grid.pack(fill="x")
        for column, label in enumerate(("Skill", "Activates on", "Multiplier", "Bonus %")):
            ttk.Label(grid, text=label, style="SurfaceCaption.TLabel").grid(
                row=0, column=column, sticky="w", padx=(0, 18), pady=(0, 6))
        for r, (key, name, _sid, formula, _sites, has_bonus) in enumerate(PROCS, start=1):
            ttk.Label(grid, text=name, style="Surface.TLabel").grid(row=r, column=0, sticky="w", padx=(0, 18), pady=3)
            ttk.Label(grid, text=formula, style="SurfaceMuted.TLabel").grid(row=r, column=1, sticky="w", padx=(0, 18))
            scale = _Row(self, grid, CATALOG.entries[f"proc.{key}.scale"], factor=1 / SCALE_DENOMINATOR)
            scale.box.grid(row=r, column=2, sticky="w", padx=(0, 18))
            self._rows.append(scale)
            if has_bonus:
                bonus = _Row(self, grid, CATALOG.entries[f"proc.{key}.bonus"])
                bonus.box.grid(row=r, column=3, sticky="w")
                self._rows.append(bonus)

    def _growth_table(self, parent: tk.Misc) -> None:
        grid = ttk.Frame(parent, style="Surface.TFrame")
        grid.pack(fill="x")
        for column, label in enumerate(("Stat", "Random mode: gain per success", "Fixed mode: gain per level")):
            ttk.Label(grid, text=label, style="SurfaceCaption.TLabel").grid(
                row=0, column=column, sticky="w", padx=(0, 28), pady=(0, 6))
        for r, stat in enumerate(STATS, start=1):
            ttk.Label(grid, text=stat, style="Surface.TLabel").grid(row=r, column=0, sticky="w", padx=(0, 28), pady=3)
            for column, kind in ((1, "random"), (2, "fixed")):
                row = _Row(self, grid, CATALOG.entries[f"growth.{kind}.{r - 1}"])
                row.box.grid(row=r, column=column, sticky="w", padx=(0, 28))
                self._rows.append(row)
