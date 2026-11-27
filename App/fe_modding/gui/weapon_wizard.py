"""New weapon... (Battle Weapons page, both games): an item copied from a weapon, its own model
slot under ``xwp/`` (optionally with a new mesh) and its battle entry with chosen effects, in one
dialog. The work is :func:`fe_modding.weapon_slots.add_weapon`; this is its form.

The effect boxes list first the effects the game's own weapons of the template's type play in
that slot, then every other registered effect; a choice no vanilla weapon of that type plays
(or a clone of one) is flagged in red, since such an effect can crash the battle."""

from __future__ import annotations

import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import Callable

from .. import weapon_slots
from ..formats import effects, fe8data
from ..game_profile import files_root_of
from ..games import Game

TEMPLATE_MODEL = "Copy the template's model"
OTHER_MODEL = "Copy this model:"
NO_MODEL = "No 3D model (tome-like)"
KEEP = "(as the template)"
NONE = "(none)"


class NewWeaponDialog(tk.Toplevel):
    def __init__(self, parent: tk.Misc, project, changelog, session, on_done: Callable[[str], None]):
        super().__init__(parent)
        self.title("New weapon")
        self.transient(parent.winfo_toplevel())
        self.resizable(False, False)
        self._project, self._changelog, self._session, self._on_done = project, changelog, session, on_done
        self._rd = project.game is Game.RADIANT_DAWN
        self._entries = {e.key.upper(): e for e in weapon_slots.weapon_entries(project)}
        self._uses = weapon_slots.effect_uses(project)
        self._templates = weapon_slots.weapon_templates(project, session.data)
        try:
            registered = [e.name for e in effects.list_effects(files_root_of(project), project.game) if e.registered]
        except Exception:  # noqa: BLE001 - effects are optional in the form
            registered = []
        self._registered = registered
        self._fields = ("hit", "crit", "effect", "target") if self._rd else ("effect", "target")

        body = ttk.Frame(self, padding=12)
        body.pack(fill="both", expand=True)
        body.columnconfigure(1, weight=1)
        row = 0

        def line(label, widget, hint=""):
            nonlocal row
            ttk.Label(body, text=label).grid(row=row, column=0, sticky="w", pady=3)
            widget.grid(row=row, column=1, columnspan=2, sticky="ew", padx=(8, 0), pady=3)
            row += 1
            if hint:
                ttk.Label(body, text=hint, style="Muted.TLabel", wraplength=420, justify="left").grid(
                    row=row, column=1, columnspan=2, sticky="w", padx=(8, 0))
                row += 1

        self._key = tk.StringVar(value="IID_")
        line("Item ID", ttk.Entry(body, textvariable=self._key, width=36),
             "The battle finds the weapon by this ID without IID_; the model folder is its lower case.")
        self._template = tk.StringVar(value=self._templates[0] if self._templates else "")
        box = ttk.Combobox(body, textvariable=self._template, values=self._templates, state="readonly", width=34)
        box.bind("<<ComboboxSelected>>", lambda _e: self._template_changed())
        line("Copy of", box, "Stats, ranks, weapon type, battle type and item effects are copied: "
                             "edit them later in Game Data and Battle Weapons.")
        self._item_name = tk.StringVar()
        line("Name", ttk.Entry(body, textvariable=self._item_name), "Empty: the template's name.")
        self._help_text = tk.StringVar()
        line("Description", ttk.Entry(body, textvariable=self._help_text), "Empty: the template's help text.")

        ttk.Separator(body).grid(row=row, column=0, columnspan=3, sticky="ew", pady=6)
        row += 1
        self._model_mode = tk.StringVar(value=TEMPLATE_MODEL)
        models = weapon_slots.weapon_models(project)
        self._model = tk.StringVar(value=models[0] if models else "")
        for mode in (TEMPLATE_MODEL, OTHER_MODEL, NO_MODEL):
            ttk.Radiobutton(body, text=mode, value=mode, variable=self._model_mode).grid(
                row=row, column=0, columnspan=1 if mode == OTHER_MODEL else 3, sticky="w")
            if mode == OTHER_MODEL:
                ttk.Combobox(body, textvariable=self._model, values=models, state="readonly", width=30).grid(
                    row=row, column=1, columnspan=2, sticky="ew", padx=(8, 0))
            row += 1
        self._mesh = tk.StringVar()
        mesh_row = ttk.Frame(body)
        ttk.Entry(mesh_row, textvariable=self._mesh, width=30).pack(side="left", fill="x", expand=True)
        ttk.Button(mesh_row, text="Browse...", command=self._browse).pack(side="left", padx=(6, 0))
        line("New mesh (.glb)", mesh_row,
             "Optional: replaces the copied mesh (as 3D Models > Import .glb). Model it over the "
             "template's exported .glb so the grip stays in the hand. A .blend goes through 3D Models.")

        ttk.Separator(body).grid(row=row, column=0, columnspan=3, sticky="ew", pady=6)
        row += 1
        self._effects: dict[str, tk.StringVar] = {}
        self._effect_boxes: dict[str, ttk.Combobox] = {}
        for key in self._fields:
            var = tk.StringVar(value=KEEP)
            var.trace_add("write", lambda *_: self._check_effects())
            box = ttk.Combobox(body, textvariable=var, width=34)
            self._effects[key], self._effect_boxes[key] = var, box
            line(weapon_slots.FIELD_LABELS[key], box)
        self._trail = tk.StringVar(value=KEEP)
        if not self._rd:
            colours = [KEEP] + [f"{i}: {name}" for i, (name, _rgba) in enumerate(fe8data.ITEM_TRAIL_COLORS)]
            line("Trail colour", ttk.Combobox(body, textvariable=self._trail, values=colours, state="readonly"),
                 "The coloured streak of the swing: always visible, safe on every weapon.")
        self._warning = ttk.Label(body, text="", foreground="#c0392b", wraplength=440, justify="left")
        self._warning.grid(row=row, column=0, columnspan=3, sticky="w", pady=(6, 0))
        row += 1

        buttons = ttk.Frame(body)
        buttons.grid(row=row, column=0, columnspan=3, sticky="e", pady=(10, 0))
        ttk.Button(buttons, text="Cancel", command=self.destroy).pack(side="right")
        ttk.Button(buttons, text="Create", command=self._create).pack(side="right", padx=(0, 6))
        self._template_changed()
        self.grab_set()

    # -- form ---------------------------------------------------------------------------------------
    def _source(self):
        return self._entries.get(self._template.get().removeprefix("IID_").upper())

    def _template_changed(self) -> None:
        source = self._source()
        if source is None:
            return
        for key, box in self._effect_boxes.items():
            safe = weapon_slots.safe_effects(self._project, source.group, key, self._uses)
            current = source.effects.get(key)
            rest = [e for e in self._registered if e not in safe]
            box.configure(values=[KEEP, NONE] + safe + rest)
            self._effects[key].set(KEEP)
        self._check_effects()

    def _chosen_effects(self) -> dict:
        out = {}
        for key, var in self._effects.items():
            value = var.get().strip()
            if value == KEEP:
                continue
            out[key] = "" if value in (NONE, "") else value
        return out

    def _check_effects(self) -> None:
        source = self._source()
        if source is None or not hasattr(self, "_warning"):
            return
        chosen = {k: source.effects.get(k) for k in self._fields}
        chosen.update({k: v or None for k, v in self._chosen_effects().items()})
        notes = weapon_slots.effect_warnings(self._project, source.group, chosen, self._uses)
        self._warning.config(text="\n".join(notes))

    def _browse(self) -> None:
        chosen = filedialog.askopenfilename(parent=self, title="Weapon mesh",
                                            filetypes=[("glTF", "*.glb *.gltf"), ("All files", "*.*")])
        if chosen:
            self._mesh.set(chosen)

    # -- create -------------------------------------------------------------------------------------
    def _create(self) -> None:
        mode = self._model_mode.get()
        model_from = None if mode == TEMPLATE_MODEL else (self._model.get() if mode == OTHER_MODEL else "")
        trail = self._trail.get()
        spec = weapon_slots.WeaponSpec(
            key=self._key.get().strip().upper().removeprefix("IID_"), template=self._template.get(),
            name=self._item_name.get(), description=self._help_text.get(), model_from=model_from,
            effects=self._chosen_effects(),
            trail_colour=None if trail == KEEP or self._rd else int(trail.split(":")[0]))
        if self._session.dirty and not messagebox.askyesno(
                "New weapon", "Game Data has unsaved edits. They are saved together with the new item. Continue?",
                parent=self):
            return
        if self._warning.cget("text") and not messagebox.askyesno(
                "New weapon", self._warning.cget("text") + "\n\nCreate the weapon anyway?", icon="warning",
                parent=self):
            return
        try:
            result = weapon_slots.add_weapon(self._project, self._session.data, spec)
            self._session.data = result.game_data
            self._session.changed(self)
            self._session.save()
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror("New weapon", str(exc), parent=self)
            return
        notes = list(result.warnings)
        mesh = self._mesh.get().strip()
        if mesh and result.model:
            notes += self._import_mesh(result.model, Path(mesh))
        elif mesh:
            notes.append("No model slot: the mesh was not imported.")
        message = f"Added IID_{spec.key}" + (f" with model xwp/{result.model}" if result.model else "")
        self._changelog.append("Battle weapons", message)
        self.destroy()
        if notes:
            messagebox.showwarning("New weapon", message + ".\n\n" + "\n".join(notes))
        self._on_done(spec.key)

    def _import_mesh(self, model: str, mesh: Path) -> list[str]:
        from .model_viewer import replace_set_with_static_glb

        pack = files_root_of(self._project) / "xwp" / model / f"{model}.cmp"
        try:
            result = replace_set_with_static_glb(pack, mesh)
            for path, data in result.outputs.items():
                self._project.write_keeping_original(path, data)
        except Exception as exc:  # noqa: BLE001
            return [f"The mesh was not imported ({exc}). Use 3D Models > Import .glb on xwp/{model}."]
        return list(result.warnings)
