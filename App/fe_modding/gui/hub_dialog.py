"""Create a hub chapter: a copy of a template chapter whose units are the avatar alone.

The links to other chapters are placed afterwards on the new chapter's Build
tab (``hub_tool.py``), with every other chapter tool at hand.
"""

from __future__ import annotations

import tkinter as tk
from pathlib import Path
from tkinter import colorchooser, filedialog, messagebox, ttk

from ..hub_creation import DEFAULT_GROUND_COLOR, MAX_SIZE, MIN_SIZE
from .widgets import info, tip


class CreateHubDialog(tk.Toplevel):
    """Return the new chapter choices, including blank-map ground appearance."""

    def __init__(self, parent, *, free: list[int], templates: dict[str, str], avatars: dict[str, str],
                 activations: dict[str, int]):
        super().__init__(parent)
        self.title("Create hub")
        self.resizable(False, False)
        self.result = None
        self._templates = templates
        self._avatars = avatars
        self._activations = activations
        self._chapter = tk.StringVar(value=f"{free[0]:02d}" if free else "")
        self._title = tk.StringVar(value="Hub")
        self._template = tk.StringVar(value=next(iter(templates), ""))
        self._keep_map = tk.BooleanVar(value=True)
        self._width = tk.StringVar(value="16")
        self._height = tk.StringVar(value="12")
        self._ground_mode = tk.StringVar(value="color")
        self._ground_color = "#" + "".join(f"{channel:02X}" for channel in DEFAULT_GROUND_COLOR)
        self._ground_color_text = tk.StringVar(value=self._ground_color)
        self._ground_image = tk.StringVar()
        self._ground_fit = tk.StringVar(value="stretch")
        self._avatar = tk.StringVar(value=next(iter(avatars), ""))
        self._activation = tk.StringVar(value=next(iter(activations), ""))

        body = ttk.Frame(self, padding=16)
        body.pack(fill="both", expand=True)
        rows = (
            ("Chapter number", ttk.Combobox(body, textvariable=self._chapter, values=[f"{n:02d}" for n in free],
                                            state="readonly", width=8),
             "A free chapter number; the hub stays out of the story order."),
            ("Title", ttk.Entry(body, textvariable=self._title, width=30), ""),
            ("Template chapter", ttk.Combobox(body, textvariable=self._template, values=list(templates),
                                              state="readonly", width=40),
             "The hub is a copy of this chapter, as Add chapter makes: its chapter data, map and assets. Its "
             "units are replaced by the avatar, its events by an empty opening."),
            ("Avatar", ttk.Combobox(body, textvariable=self._avatar, values=list(avatars), state="readonly",
                                    width=40),
             "The character the player walks around the hub with. It must not be deployed in any other "
             "chapter: create one in Game Data › Characters first if none is listed."),
            ("Opens after", ttk.Combobox(body, textvariable=self._activation, values=list(activations),
                                         state="readonly", width=40),
             "The hub opens once this chapter is won."),
        )
        for r, (label, widget, help_text) in enumerate(rows):
            tip(ttk.Label(body, text=label), help_text).grid(row=r, column=0, sticky="w", pady=3, padx=(0, 10))
            widget.grid(row=r, column=1, sticky="w", pady=3)
        r = len(rows)
        tip(ttk.Label(body, text="Map"), "Keep the template's map to decorate it, or start from a flat grass "
                                         "ground and paint it.").grid(row=r, column=0, sticky="nw", pady=3)
        maps = ttk.Frame(body)
        maps.grid(row=r, column=1, sticky="w", pady=3)
        ttk.Radiobutton(maps, text="Copy the template's map", variable=self._keep_map, value=True,
                        command=self._sync).pack(anchor="w")
        blank = ttk.Frame(maps)
        blank.pack(anchor="w", pady=(2, 0))
        ttk.Radiobutton(blank, text="Blank map", variable=self._keep_map, value=False,
                        command=self._sync).pack(side="left")
        self._size_entries = []
        for var in (self._width, self._height):
            entry = ttk.Entry(blank, textvariable=var, width=4)
            entry.pack(side="left", padx=(6, 0))
            self._size_entries.append(entry)
        tip(ttk.Label(blank, text="tiles", style="Muted.TLabel"),
            f"Width × height: {MIN_SIZE}–{MAX_SIZE} tiles per side.").pack(side="left", padx=(4, 0))
        ground = ttk.LabelFrame(maps, text="Blank-map ground", padding=(8, 4))
        ground.pack(fill="x", pady=(8, 0))
        self._ground_mode_buttons = []
        color_row = ttk.Frame(ground)
        color_row.pack(fill="x", pady=2)
        color_mode = ttk.Radiobutton(color_row, text="Color", variable=self._ground_mode, value="color",
                                     command=self._sync)
        color_mode.pack(side="left")
        self._ground_mode_buttons.append(color_mode)
        self._color_button = ttk.Button(color_row, text="Choose…", command=self._choose_color)
        self._color_button.pack(side="left", padx=(8, 4))
        self._color_swatch = tk.Label(color_row, width=3, relief="sunken", background=self._ground_color)
        self._color_swatch.pack(side="left")
        ttk.Label(color_row, textvariable=self._ground_color_text, style="Muted.TLabel").pack(
            side="left", padx=(5, 0))
        image_row = ttk.Frame(ground)
        image_row.pack(fill="x", pady=2)
        image_mode = ttk.Radiobutton(image_row, text="Image", variable=self._ground_mode, value="image",
                                     command=self._sync)
        image_mode.pack(side="left")
        self._ground_mode_buttons.append(image_mode)
        self._image_entry = ttk.Entry(image_row, textvariable=self._ground_image, width=27, state="readonly")
        self._image_entry.pack(side="left", padx=(8, 4))
        self._image_button = ttk.Button(image_row, text="Browse…", command=self._choose_image)
        self._image_button.pack(side="left")
        self._fit_picker = ttk.Combobox(image_row, textvariable=self._ground_fit,
                                        values=("stretch", "tile"), state="readonly", width=8)
        self._fit_picker.pack(side="left", padx=(5, 0))
        tip(self._fit_picker, "Stretch draws the image once over the whole hub. Tile repeats it once per map tile.")
        note = ttk.Frame(body)
        note.grid(row=r + 1, column=0, columnspan=2, sticky="w", pady=(10, 0))
        ttk.Label(note, text="The chapter then opens on its Build tab, with the Hub tool.",
                  style="Muted.TLabel").pack(side="left")
        info(note, "On the Build tab the Hub tool places the links to other chapters: an action tile each "
                   "(Arrive enters the chapter, Visit shows its description) and the tile the avatar comes "
                   "back to. Install hub then writes the events and the chapter routing.").pack(
            side="left", padx=(6, 0))
        bottom = ttk.Frame(self, padding=(16, 0, 16, 16))
        bottom.pack(fill="x")
        ttk.Button(bottom, text="Cancel", command=self.destroy).pack(side="right")
        ttk.Button(bottom, text="Create hub", style="Accent.TButton", command=self._accept).pack(
            side="right", padx=(0, 8))
        self._sync()
        self.transient(parent.winfo_toplevel())
        self.grab_set()

    def _sync(self) -> None:
        blank = not self._keep_map.get()
        for entry in self._size_entries:
            entry.configure(state="normal" if blank else "disabled")
        for button in self._ground_mode_buttons:
            button.configure(state="normal" if blank else "disabled")
        self._color_button.configure(state="normal" if blank and self._ground_mode.get() == "color" else "disabled")
        image = blank and self._ground_mode.get() == "image"
        self._image_entry.configure(state="readonly" if image else "disabled")
        self._image_button.configure(state="normal" if image else "disabled")
        self._fit_picker.configure(state="readonly" if image else "disabled")

    def _choose_color(self) -> None:
        _rgb, chosen = colorchooser.askcolor(self._ground_color, parent=self, title="Hub ground color")
        if chosen:
            self._ground_color = chosen.upper()
            self._ground_color_text.set(self._ground_color)
            self._color_swatch.configure(background=self._ground_color)

    def _choose_image(self) -> None:
        chosen = filedialog.askopenfilename(
            parent=self, title="Hub ground image",
            filetypes=(("Images", "*.png *.jpg *.jpeg *.bmp *.tga *.webp"), ("All files", "*.*")))
        if chosen:
            self._ground_image.set(chosen)

    def _accept(self) -> None:
        try:
            if not self._chapter.get():
                raise ValueError("No free chapter number from 33 to 89.")
            title = self._title.get().strip()
            if not title or not title.isascii():
                raise ValueError("The chapter title must be plain ASCII text.")
            if self._template.get() not in self._templates:
                raise ValueError("Choose a template chapter.")
            if self._avatar.get() not in self._avatars:
                raise ValueError("Choose the avatar.")
            if self._activation.get() not in self._activations:
                raise ValueError("Choose the chapter after which the hub opens.")
            size = None
            if not self._keep_map.get():
                try:
                    size = int(self._width.get()), int(self._height.get())
                except ValueError:
                    size = None
                if size is None or not all(MIN_SIZE <= n <= MAX_SIZE for n in size):
                    raise ValueError(f"A blank map is {MIN_SIZE} to {MAX_SIZE} tiles per side.")
                if self._ground_mode.get() == "image":
                    if not self._ground_image.get():
                        raise ValueError("Choose an image for the blank-map ground.")
                    if not Path(self._ground_image.get()).is_file():
                        raise ValueError("The selected ground image no longer exists.")
        except ValueError as exc:
            messagebox.showerror("Create hub", str(exc), parent=self)
            return
        color = tuple(int(self._ground_color[i:i + 2], 16) for i in (1, 3, 5))
        image = self._ground_image.get() if self._ground_mode.get() == "image" else None
        self.result = (int(self._chapter.get()), title, self._templates[self._template.get()],
                       bool(self._keep_map.get()), size, self._avatars[self._avatar.get()],
                       self._activations[self._activation.get()], color, image,
                       self._ground_fit.get() == "tile")
        self.destroy()


class EditHubGroundDialog(tk.Toplevel):
    """Choose a replacement for an existing generated blank-hub ground."""

    def __init__(self, parent, appearance, *, initial_mode: str | None = None) -> None:
        super().__init__(parent)
        self.title("Edit hub ground")
        self.resizable(False, False)
        self.result = None
        self._has_current_image = appearance.image is not None
        self._mode = tk.StringVar(value=initial_mode or ("image" if self._has_current_image else "color"))
        self._color = "#" + "".join(f"{channel:02X}" for channel in appearance.color)
        self._color_text = tk.StringVar(value=self._color)
        self._image = tk.StringVar(value="Current map image" if self._has_current_image else "")
        self._image_path = ""
        self._fit = tk.StringVar(value="tile" if appearance.tiled else "stretch")

        body = ttk.Frame(self, padding=16)
        body.pack(fill="both", expand=True)
        ttk.Label(body, text="Change only the generated flat ground; tiles, props and hub links are preserved.",
                  style="Muted.TLabel", wraplength=430, justify="left").pack(anchor="w", pady=(0, 10))

        color_row = ttk.Frame(body)
        color_row.pack(fill="x", pady=3)
        ttk.Radiobutton(color_row, text="Solid color", variable=self._mode, value="color",
                        command=self._sync).pack(side="left")
        self._color_button = ttk.Button(color_row, text="Choose…", command=self._choose_color)
        self._color_button.pack(side="left", padx=(8, 4))
        self._swatch = tk.Label(color_row, width=3, relief="sunken", background=self._color)
        self._swatch.pack(side="left")
        ttk.Label(color_row, textvariable=self._color_text, style="Muted.TLabel").pack(side="left", padx=(5, 0))

        image_row = ttk.Frame(body)
        image_row.pack(fill="x", pady=3)
        ttk.Radiobutton(image_row, text="Image", variable=self._mode, value="image",
                        command=self._sync).pack(side="left")
        self._image_entry = ttk.Entry(image_row, textvariable=self._image, width=28, state="readonly")
        self._image_entry.pack(side="left", padx=(8, 4))
        self._image_button = ttk.Button(image_row, text="Browse…", command=self._choose_image)
        self._image_button.pack(side="left")
        self._fit_picker = ttk.Combobox(image_row, textvariable=self._fit, values=("stretch", "tile"),
                                        state="readonly", width=8)
        self._fit_picker.pack(side="left", padx=(5, 0))
        tip(self._fit_picker, "Stretch draws the image once over the whole hub. Tile repeats it once per map tile.")

        bottom = ttk.Frame(self, padding=(16, 0, 16, 16))
        bottom.pack(fill="x")
        ttk.Button(bottom, text="Cancel", command=self.destroy).pack(side="right")
        ttk.Button(bottom, text="Apply", style="Accent.TButton", command=self._accept).pack(
            side="right", padx=(0, 8))
        self._sync()
        self.transient(parent.winfo_toplevel())
        self.grab_set()

    def _sync(self) -> None:
        image = self._mode.get() == "image"
        self._color_button.configure(state="disabled" if image else "normal")
        self._image_entry.configure(state="readonly" if image else "disabled")
        self._image_button.configure(state="normal" if image else "disabled")
        self._fit_picker.configure(state="readonly" if image else "disabled")

    def _choose_color(self) -> None:
        _rgb, chosen = colorchooser.askcolor(self._color, parent=self, title="Hub ground color")
        if chosen:
            self._color = chosen.upper()
            self._color_text.set(self._color)
            self._swatch.configure(background=self._color)

    def _choose_image(self) -> None:
        chosen = filedialog.askopenfilename(
            parent=self, title="Hub ground image",
            filetypes=(("Images", "*.png *.jpg *.jpeg *.bmp *.tga *.webp"), ("All files", "*.*")))
        if chosen:
            self._image_path = chosen
            self._image.set(chosen)

    def _accept(self) -> None:
        use_image = self._mode.get() == "image"
        if use_image and not self._image_path and not self._has_current_image:
            messagebox.showerror("Edit hub ground", "Choose a ground image.", parent=self)
            return
        if self._image_path and not Path(self._image_path).is_file():
            messagebox.showerror("Edit hub ground", "The selected ground image no longer exists.", parent=self)
            return
        color = tuple(int(self._color[i:i + 2], 16) for i in (1, 3, 5))
        self.result = color, self._image_path or None, self._fit.get() == "tile", use_image
        self.destroy()
