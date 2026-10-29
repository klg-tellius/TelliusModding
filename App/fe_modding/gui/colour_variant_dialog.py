"""The Colour variant dialog: recolour a character's (or one army's look of a
class's) battle texture, map texture and portrait, with a live preview
(the game data adapter does the work: ``fe_modding/colour_variants.py`` on
Path of Radiance, ``colour_variants_fe10.py`` on Radiant Dawn).

:func:`open_colour_variant` is the entry point for the character page and
the class form: it saves the shared game-data file first (the variant writes
the file on disk), runs the dialog and reloads the session afterwards. The
army and "Also for" choices appear only where the game's adapter offers them.
"""

from __future__ import annotations

import colorsys
import io
import threading
import tkinter as tk
from tkinter import colorchooser, messagebox, ttk
from typing import Callable, Optional

from PIL import Image, ImageTk

from .. import colour_variants
from ..exceptions import ProjectError
from ..game_adapter import data_adapter
from ..project import ModProject
from ..recolour import Recolour, recolour_tpl
from ..formats import tpl

PREVIEW_SIZE = 260
ARMY_LABELS = {key: f"{name} army ({key})" for key, name in colour_variants.ARMY_NAMES.items()}


def open_colour_variant(parent: tk.Misc, project: ModProject, session, changelog, *, pid: str | None = None,
                        jid: str | None = None, on_done: Optional[Callable[[], None]] = None) -> None:
    """Run the dialog for a character (``pid``) or a class (``jid``)."""
    label = getattr(session, "file_label", "the game data")
    adapter = data_adapter(session)
    if adapter is None:
        messagebox.showerror("Colour variant", "This project has no game data.", parent=parent)
        return
    if session is not None and getattr(session, "dirty", False):
        if not messagebox.askyesno(f"Save {label}?", "A colour variant changes portraits and animation IDs "
                                   f"in {label} on disk. Save its unsaved edits first?", parent=parent):
            return
        try:
            session.save()
        except (OSError, ValueError) as exc:
            messagebox.showerror(f"Could not save {label}", str(exc), parent=parent)
            return
    try:
        dialog = ColourVariantDialog(parent, project, adapter, pid=pid, jid=jid)
    except ProjectError as exc:
        messagebox.showerror("Colour variant", str(exc), parent=parent)
        return
    parent.wait_window(dialog)
    if dialog.result is None:
        return
    if session is not None and getattr(session, "available", False):
        session.revert()
        for callback in list(getattr(session, "on_saved", ())):
            callback()  # the project index: pages show the new portrait and models
    changelog.append(dialog.result_label, "; ".join(dialog.result))
    if on_done is not None:
        on_done()


class ColourVariantDialog(tk.Toplevel):
    def __init__(self, parent: tk.Misc, project: ModProject, adapter, *, pid: str | None = None,
                 jid: str | None = None) -> None:
        super().__init__(parent)
        self._project = project
        self._adapter = adapter
        self._options = adapter.colour_variant_options
        self._pid, self._jid = pid, jid
        self.result: list[str] | None = None
        self.result_label = pid or jid or ""
        self.title(f"Colour variant of {pid or jid}")
        self.transient(parent)
        self._plan: colour_variants.VariantPlan | None = None
        self._sources: dict[int, tuple[bytes, Image.Image]] = {}
        self._photos: list = []
        self._before_scale = 1.0
        self._plan_job: str | None = None
        self._preview_job: str | None = None
        self._busy = False

        body = ttk.Frame(self, padding=10)
        body.pack(fill="both", expand=True)
        left = ttk.Frame(body)
        left.grid(row=0, column=0, sticky="nsw")
        right = ttk.Frame(body)
        right.grid(row=0, column=1, sticky="nsew", padx=(14, 0))
        body.columnconfigure(1, weight=1)
        body.rowconfigure(0, weight=1)
        self._build_options(left)
        self._build_colours(left)
        self._build_preview(right)

        bottom = ttk.Frame(body)
        bottom.grid(row=1, column=0, columnspan=2, sticky="nsew", pady=(10, 0))
        ttk.Label(bottom, text="Changes", style="Muted.TLabel").pack(anchor="w")
        self._changes = tk.Text(bottom, height=9, width=100, wrap="word", state="disabled")
        self._changes.pack(fill="both", expand=True)
        buttons = ttk.Frame(bottom)
        buttons.pack(fill="x", pady=(8, 0))
        self._status = ttk.Label(buttons, text="", style="Muted.TLabel")
        self._status.pack(side="left")
        ttk.Button(buttons, text="Cancel", command=self.destroy).pack(side="right")
        self._create = ttk.Button(buttons, text="Create", style="Accent.TButton", command=self._ok)
        self._create.pack(side="right", padx=(0, 6))
        self._replan()
        self.grab_set()

    # -- options ---------------------------------------------------------------------------
    def _build_options(self, parent) -> None:
        box = ttk.LabelFrame(parent, text="Variant", padding=8)
        box.pack(fill="x")
        self._tag = tk.StringVar(value="RED")
        row = ttk.Frame(box)
        row.pack(fill="x")
        ttk.Label(row, text="Tag").pack(side="left")
        entry = ttk.Entry(row, textvariable=self._tag, width=10)
        entry.pack(side="left", padx=(6, 0))
        ttk.Label(row, text="names the new files and IDs", style="Muted.TLabel").pack(side="left", padx=(6, 0))
        self._tag.trace_add("write", lambda *_: self._schedule_plan())

        self._battle = tk.BooleanVar(value=True)
        self._map = tk.BooleanVar(value=True)
        self._portrait = tk.BooleanVar(value=self._pid is not None)
        what = ttk.Frame(box)
        what.pack(fill="x", pady=(6, 0))
        for text, var in (("Battle texture", self._battle), ("Map texture", self._map)):
            ttk.Checkbutton(what, text=text, variable=var, command=self._schedule_plan).pack(side="left")
        if self._pid is not None:
            ttk.Checkbutton(what, text="Portrait", variable=self._portrait, command=self._schedule_plan).pack(
                side="left")

        self._army = tk.StringVar()
        self._promoted = tk.BooleanVar(value=True)
        self._also: dict[str, tk.BooleanVar] = {}
        if self._pid is not None:
            suggested, others = self._adapter.character_family(self._project, self._pid)
            if suggested or others:
                also = ttk.Frame(box)
                also.pack(fill="x", pady=(6, 0))
                ttk.Label(also, text="Also for").pack(anchor="w")
                for other in suggested + others:
                    var = tk.BooleanVar(value=other in suggested)
                    self._also[other] = var
                    ttk.Checkbutton(also, text=other, variable=var, command=self._schedule_plan).pack(anchor="w")
            self._army.set(ARMY_LABELS["自軍"])
            label = "Colours where nothing of the character's own picks one"
        else:
            self._army.set(ARMY_LABELS["敵軍"])
            ttk.Checkbutton(box, text="Its promoted class too", variable=self._promoted,
                            command=self._schedule_plan).pack(anchor="w", pady=(6, 0))
            label = "Army whose colours change"
        if "armies" not in self._options:
            # Radiant Dawn: a character's colours follow its own animation IDs, whatever its army
            ttk.Label(box, text="Every tier of the character: its map and battle models and its portrait.",
                      style="Muted.TLabel", wraplength=300).pack(anchor="w", pady=(6, 0))
            return
        ttk.Label(box, text=label).pack(anchor="w", pady=(6, 0))
        army = ttk.Combobox(box, textvariable=self._army, values=list(ARMY_LABELS.values()), state="readonly",
                            width=30)
        army.pack(anchor="w")
        army.bind("<<ComboboxSelected>>", lambda e: self._schedule_plan())

    def _army_key(self) -> str:
        return next(key for key, label in ARMY_LABELS.items() if label == self._army.get())

    # -- colours ---------------------------------------------------------------------------
    def _build_colours(self, parent) -> None:
        box = ttk.LabelFrame(parent, text="Colours", padding=8)
        box.pack(fill="x", pady=(10, 0))
        self._from_colour: tuple[int, int, int] | None = None
        self._to_colour: tuple[int, int, int] | None = None
        swatches = ttk.Frame(box)
        swatches.pack(fill="x")
        self._from_swatch = tk.Button(swatches, text="From…", width=8, relief="groove",
                                      command=lambda: self._choose_colour(True))
        self._from_swatch.pack(side="left")
        ttk.Label(swatches, text="→").pack(side="left", padx=6)
        self._to_swatch = tk.Button(swatches, text="To…", width=8, relief="groove",
                                    command=lambda: self._choose_colour(False))
        self._to_swatch.pack(side="left")
        ttk.Label(box, text="Click the Before picture to pick the colour to change.", style="Muted.TLabel",
                  wraplength=330).pack(anchor="w", pady=(4, 6))

        self._sliders: dict[str, tk.DoubleVar] = {}
        grid = ttk.Frame(box)
        grid.pack(fill="x")
        specs = (("hue", "Hue to change (°)", 0, 360, 0), ("band", "Band ± (°)", 0, 180, 12),
                 ("feather", "Soft edge (°)", 0, 60, 8), ("shift", "Turn hue by (°)", -180, 180, 0),
                 ("saturation", "Saturation (%)", 0, 300, 100), ("brightness", "Brightness (%)", 0, 300, 100),
                 ("min_saturation", "Leave greys under (%)", 0, 60, 12))
        for r, (key, label, low, high, value) in enumerate(specs):
            var = tk.DoubleVar(value=value)
            self._sliders[key] = var
            ttk.Label(grid, text=label).grid(row=r, column=0, sticky="w")
            ttk.Scale(grid, from_=low, to=high, variable=var, length=170,
                      command=lambda _v: self._schedule_preview()).grid(row=r, column=1, padx=6)
            shown = ttk.Label(grid, width=5, anchor="e")
            shown.grid(row=r, column=2, sticky="e")
            var.trace_add("write", lambda *_, v=var, s=shown: s.configure(text=f"{v.get():.0f}"))
            shown.configure(text=f"{value:.0f}")

    def _recolour(self) -> Recolour:
        s = {k: v.get() for k, v in self._sliders.items()}
        return Recolour(hue=s["hue"], band=s["band"], feather=s["feather"], shift=s["shift"],
                        saturation=s["saturation"] / 100, brightness=s["brightness"] / 100,
                        min_saturation=s["min_saturation"] / 100)

    def _choose_colour(self, source: bool) -> None:
        current = self._from_colour if source else self._to_colour
        chosen = colorchooser.askcolor(color="#%02x%02x%02x" % current if current else None, parent=self,
                                       title="Colour to change" if source else "New colour")
        if chosen and chosen[0]:
            self._set_colour(source, tuple(int(c) for c in chosen[0]))

    def _set_colour(self, source: bool, rgb: tuple[int, int, int]) -> None:
        if source:
            self._from_colour = rgb
        else:
            self._to_colour = rgb
        swatch = self._from_swatch if source else self._to_swatch
        light = sum(rgb) > 380
        swatch.configure(background="#%02x%02x%02x" % rgb, activebackground="#%02x%02x%02x" % rgb,
                         foreground="black" if light else "white")
        if self._from_colour is not None:
            if self._to_colour is None:
                hue = colorsys.rgb_to_hsv(*(c / 255 for c in self._from_colour))[0] * 360
                self._sliders["hue"].set(round(hue))
            else:
                recolour = Recolour.between(self._from_colour, self._to_colour, band=self._sliders["band"].get())
                self._sliders["hue"].set(round(recolour.hue))
                self._sliders["shift"].set(round(recolour.shift))
                self._sliders["saturation"].set(round(recolour.saturation * 100))
                self._sliders["brightness"].set(round(recolour.brightness * 100))
        self._schedule_preview()

    # -- preview ---------------------------------------------------------------------------
    def _build_preview(self, parent) -> None:
        top = ttk.Frame(parent)
        top.pack(fill="x")
        ttk.Label(top, text="Texture").pack(side="left")
        self._texture = tk.StringVar()
        self._texture_box = ttk.Combobox(top, textvariable=self._texture, state="readonly", width=60)
        self._texture_box.pack(side="left", padx=(6, 0), fill="x", expand=True)
        self._texture_box.bind("<<ComboboxSelected>>", lambda e: self._schedule_preview())
        pictures = ttk.Frame(parent)
        pictures.pack(fill="both", expand=True, pady=(8, 0))
        self._before = tk.Label(pictures, borderwidth=0, cursor="crosshair")
        self._after = tk.Label(pictures, borderwidth=0)
        for column, (text, label) in enumerate((("Before", self._before), ("After", self._after))):
            ttk.Label(pictures, text=text, style="Muted.TLabel").grid(row=0, column=column, sticky="w")
            label.grid(row=1, column=column, sticky="nw", padx=(0 if column == 0 else 10, 0))
        self._before.bind("<Button-1>", self._pick_from_preview)

    def _selected_copy(self) -> int | None:
        if self._plan is None or not self._plan.copies:
            return None
        values = list(self._texture_box.cget("values"))
        return values.index(self._texture.get()) if self._texture.get() in values else 0

    def _schedule_preview(self) -> None:
        if self._preview_job is not None:
            self.after_cancel(self._preview_job)
        self._preview_job = self.after(120, self._update_preview)

    def _update_preview(self) -> None:
        self._preview_job = None
        index = self._selected_copy()
        if index is None:
            self._before.configure(image="", text="")
            self._after.configure(image="", text="")
            return
        if index not in self._sources:
            data = self._plan.copies[index].source_bytes()
            self._sources[index] = (data, tpl.read_tpl_images(io.BytesIO(data))[0])
        data, before = self._sources[index]
        after = tpl.read_tpl_images(io.BytesIO(recolour_tpl(data, self._recolour())))[0]
        scale = min(PREVIEW_SIZE / before.width, PREVIEW_SIZE / before.height)
        self._before_scale = scale
        size = (max(1, round(before.width * scale)), max(1, round(before.height * scale)))
        self._photos = [ImageTk.PhotoImage(image.convert("RGBA").resize(size, Image.NEAREST))
                        for image in (before, after)]
        self._before.configure(image=self._photos[0])
        self._after.configure(image=self._photos[1])

    def _pick_from_preview(self, event) -> None:
        index = self._selected_copy()
        if index is None or index not in self._sources:
            return
        image = self._sources[index][1]
        x, y = int(event.x / self._before_scale), int(event.y / self._before_scale)
        if 0 <= x < image.width and 0 <= y < image.height:
            r, g, b, a = image.convert("RGBA").getpixel((x, y))
            if a:
                self._set_colour(True, (r, g, b))

    # -- plan ------------------------------------------------------------------------------
    def _schedule_plan(self) -> None:
        if self._plan_job is not None:
            self.after_cancel(self._plan_job)
        self._plan_job = self.after(250, self._replan)

    def _replan(self) -> None:
        self._plan_job = None
        try:
            if self._pid is not None:
                self._plan = self._adapter.plan_character_variant(
                    self._project, self._pid, self._tag.get(),
                    also=[p for p, var in self._also.items() if var.get()], battle=self._battle.get(),
                    map_models=self._map.get(), portrait=self._portrait.get(), army=self._army_key())
            else:
                self._plan = self._adapter.plan_class_variant(
                    self._project, self._jid, self._army_key(), self._tag.get(), promoted=self._promoted.get(),
                    battle=self._battle.get(), map_models=self._map.get())
            lines = self._plan.summary() + [f"Note: {note}" for note in self._plan.notes]
        except (ProjectError, ValueError) as exc:
            self._plan = None
            lines = [str(exc)]
        self._changes.configure(state="normal")
        self._changes.delete("1.0", "end")
        self._changes.insert("end", "\n".join(lines))
        self._changes.configure(state="disabled")
        ready = self._plan is not None and not self._plan.empty
        self._create.configure(state="normal" if ready and not self._busy else "disabled")
        labels = [f"{c.kind}: {c.label}" for c in self._plan.copies] if self._plan else []
        previous = self._texture.get()
        self._texture_box.configure(values=labels)
        self._texture.set(previous if previous in labels else (labels[0] if labels else ""))
        self._sources = {}
        self._schedule_preview()

    def _ok(self) -> None:
        if self._plan is None or self._plan.empty or self._busy:
            return
        recolour = self._recolour()
        if recolour.is_identity and not messagebox.askyesno(
                "Colour variant", "The colours are unchanged: create plain copies anyway?", parent=self):
            return
        plan = self._plan
        self._busy = True
        self._create.configure(state="disabled")
        self._status.configure(text="Writing textures…")
        self.configure(cursor="watch")
        outcome: dict = {}

        def work() -> None:
            try:
                outcome["lines"] = self._adapter.apply_variant(self._project, plan, recolour)
            except Exception as exc:  # noqa: BLE001 - shown to the user
                outcome["error"] = exc

        thread = threading.Thread(target=work, daemon=True)
        thread.start()

        def wait() -> None:
            if thread.is_alive():
                self.after(100, wait)
                return
            self._busy = False
            self.configure(cursor="")
            self._status.configure(text="")
            if "error" in outcome:
                messagebox.showerror("Could not create the variant", str(outcome["error"]), parent=self)
                self._replan()
                return
            self.result = [f"{plan.title} ({recolour.describe()})"] + outcome["lines"]
            self.destroy()

        wait()
