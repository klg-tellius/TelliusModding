"""Visual effects page: every ``EID_*`` effect of ``FE8Effect.bin`` plus any
unregistered ``yme/`` pack, rendered with the 3D model preview (an effect is
an ordinary skeleton + mesh + animation + texture pack, see ``formats/effects.py``).

An effect's whole pack can be replaced from another ``.cmp``, its texture can
be replaced from an image, and a new effect can be added (``effect_add_dialog.py``).
The preview shows the raw animation only; in-game timing and sequencing of the
effects are not decoded."""

from __future__ import annotations

import io
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, simpledialog, ttk

from PIL import Image, ImageTk

from ..formats import effects, tpl
from ..exceptions import ProjectError
from ..project import ModProject
from .changelog import ChangeLog
from .editor_panel import EditorPanel
from .effect_add_dialog import EffectAddDialog
from .model_viewer import _load_model_set, _ModelPreview

TEXTURE_THUMB = 112
FILTERS = ("All", "Registered", "Unregistered", "Chained")
COLUMNS = (
    ("name", "Effect", 230, "w"),
    ("category", "Cat.", 40, "e"),
    ("chain", "Next in chain", 150, "w"),
    ("status", "Status", 120, "w"),
)


class EffectsViewer(EditorPanel):
    display_name = "Visual effects"

    def __init__(self, parent: tk.Misc, project: ModProject, changelog: ChangeLog):
        super().__init__(parent)
        self._project = project
        self._changelog = changelog
        self._files = project.extracted_dir / "files"
        self._entries: list[effects.EffectEntry] = []
        self._by_iid: dict[str, effects.EffectEntry] = {}
        self._build_widgets()
        self._load()

    # -- layout ---------------------------------------------------------------
    def _build_widgets(self) -> None:
        top = ttk.Frame(self, padding=(8, 8, 8, 0))
        top.pack(fill="x")
        ttk.Label(top, text="Search").pack(side="left")
        self._query = tk.StringVar()
        ttk.Entry(top, textvariable=self._query).pack(side="left", fill="x", expand=True, padx=(6, 12))
        self._query.trace_add("write", lambda *_: self._refresh())
        ttk.Label(top, text="Show").pack(side="left")
        self._filter = tk.StringVar(value=FILTERS[0])
        box = ttk.Combobox(top, textvariable=self._filter, state="readonly", width=12, values=FILTERS)
        box.pack(side="left", padx=(6, 0))
        box.bind("<<ComboboxSelected>>", lambda _e: self._refresh())

        self._count = ttk.Label(self, text="", style="Muted.TLabel", padding=(8, 4))
        self._count.pack(anchor="w")

        body = ttk.PanedWindow(self, orient="horizontal")
        body.pack(fill="both", expand=True, padx=8, pady=(0, 8))
        left = ttk.Frame(body)
        body.add(left, weight=3)
        self._tree = ttk.Treeview(left, columns=[c[0] for c in COLUMNS], show="headings", selectmode="browse")
        for key, title, width, anchor in COLUMNS:
            self._tree.heading(key, text=title)
            self._tree.column(key, width=width, anchor=anchor, stretch=key == "name")
        scroll = ttk.Scrollbar(left, command=self._tree.yview)
        self._tree.config(yscrollcommand=scroll.set)
        self._tree.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")
        self._tree.bind("<<TreeviewSelect>>", lambda _e: self._show_selected())

        right = ttk.Frame(body, padding=(12, 0, 0, 0))
        body.add(right, weight=5)
        self._title = ttk.Label(right, text="(no effect selected)", font=("Segoe UI", 12, "bold"))
        self._title.pack(anchor="w")
        self._detail = ttk.Label(right, text="", justify="left", style="Muted.TLabel")
        self._detail.pack(anchor="w", pady=(2, 6))
        actions = ttk.Frame(right)
        actions.pack(anchor="w", pady=(0, 6))
        ttk.Button(actions, text="Add effect...", command=self._add).pack(side="left")
        self._replace_btn = ttk.Button(actions, text="Replace pack...", command=self._replace_pack, state="disabled")
        self._replace_btn.pack(side="left", padx=(6, 0))
        self._texture_btn = ttk.Button(actions, text="Replace texture...", command=self._replace_texture, state="disabled")
        self._texture_btn.pack(side="left", padx=(6, 0))
        self._register_btn = ttk.Button(actions, text="Register...", command=self._register_effect, state="disabled")
        self._register_btn.pack(side="left", padx=(6, 0))
        self._restore_btn = ttk.Button(actions, text="Restore original", command=self._restore, state="disabled")
        self._restore_btn.pack(side="left", padx=(6, 0))
        self._status = ttk.Label(right, text="", style="Muted.TLabel", wraplength=520, justify="left")
        self._status.pack(anchor="w", pady=(0, 4))
        self._textures = ttk.Label(right)
        self._textures.pack(anchor="w", pady=(0, 6))
        self._texture_photos: list[ImageTk.PhotoImage] = []
        self._preview = _ModelPreview(right)
        self._preview.pack(fill="both", expand=True)
        self._body = body
        self.after(100, lambda: self._body.sashpos(0, 520))

    def cleanup(self) -> None:
        self._preview.cleanup()

    # -- list -----------------------------------------------------------------
    def _load(self) -> None:
        if not effects.registry_path(self._files).exists():
            self._count.config(text=f"{effects.REGISTRY_FILE} not found. Extract the project first.")
            return
        try:
            self._entries = effects.list_effects(self._files)
        except Exception as exc:  # noqa: BLE001 - corrupt registry: say so instead of a blank page
            self._count.config(text=f"Could not read {effects.REGISTRY_FILE}: {exc}")
            return
        self._refresh()

    def _refresh(self) -> None:
        query = self._query.get().strip().lower()
        mode = self._filter.get()
        self._tree.delete(*self._tree.get_children())
        self._by_iid.clear()
        for e in self._entries:
            if query and query not in e.name.lower():
                continue
            if mode == "Registered" and not e.registered or mode == "Unregistered" and e.registered:
                continue
            if mode == "Chained" and not e.next_in_chain:
                continue
            self._by_iid[e.name] = e
            status = ("registered" if e.registered else "unregistered") + ("" if e.has_pack else ", no pack")
            self._tree.insert("", "end", iid=e.name, values=(
                e.name, e.category if e.registered else "", e.next_in_chain or "", status))
        self._count.config(text=f"{len(self._by_iid)} of {len(self._entries)} effects")

    def _selected(self) -> effects.EffectEntry | None:
        selection = self._tree.selection()
        return self._by_iid.get(selection[0]) if selection else None

    def _pack_file(self, entry: effects.EffectEntry) -> Path:
        return effects.pack_path(self._files, entry.name)

    # -- detail / preview -----------------------------------------------------
    def _show_selected(self) -> None:
        entry = self._selected()
        if entry is None:
            return
        path = self._pack_file(entry)
        self._title.config(text=entry.name)
        self._replace_btn.config(state="normal")
        self._texture_btn.config(state="normal" if entry.has_pack else "disabled")
        self._register_btn.config(state="disabled" if entry.registered else "normal")
        self._restore_btn.config(state="normal" if self._has_original(entry) else "disabled")
        lines = [f"Registry flags: {entry.flags:#010x}" if entry.registered else "Not in FE8Effect.bin"]
        if entry.next_in_chain:
            lines.append(f"Chains to {entry.next_in_chain}")
        self._show_textures({})
        if not entry.has_pack:
            self._detail.config(text="\n".join(lines))
            self._status.config(text="No yme pack for this effect. Use Replace pack... to give it one.")
            self._preview.show(None, "No pack for this effect.")
            return
        try:
            parts = effects.read_effect_pack(path.read_bytes())
        except (effects.EffectError, OSError) as exc:
            self._detail.config(text="\n".join(lines))
            self._status.config(text=f"Could not read the pack: {exc}")
            self._preview.show(None, "Unreadable pack.")
            return
        lines.append("Pack: " + ", ".join(f"{n.rsplit('.', 1)[-1]} {len(b):,} B" for n, b in parts.items()))
        self._detail.config(text="\n".join(lines))
        self._status.config(text="")
        self._show_textures(parts)
        try:
            self._preview.show(_load_model_set(entry.name, path), "No model data.")
        except Exception as exc:  # noqa: BLE001 - effect nodes use flags the rig viewer may not pose
            self._preview.show(None, "No preview.")
            self._status.config(text=f"Preview failed: {exc}")

    def _show_textures(self, parts: dict[str, bytes]) -> None:
        """Thumbnails of the pack's texture images: an effect's look lives there,
        the mesh is mostly particle planes."""
        self._texture_photos = []
        tpl_data = next((b for n, b in parts.items() if n.endswith(".tpl")), None)
        if tpl_data is None:
            self._textures.config(image="", text="")
            return
        try:
            images = tpl.read_tpl_images(io.BytesIO(tpl_data))[:4]
        except Exception as exc:  # noqa: BLE001 - an undecodable texture must not block the page
            self._textures.config(image="", text=f"Texture unreadable: {exc}")
            return
        strip = Image.new("RGBA", (TEXTURE_THUMB * len(images) + 6 * (len(images) - 1), TEXTURE_THUMB), (40, 40, 40, 255))
        for i, img in enumerate(images):
            thumb = img.convert("RGBA")
            thumb.thumbnail((TEXTURE_THUMB, TEXTURE_THUMB))
            strip.alpha_composite(thumb, (i * (TEXTURE_THUMB + 6), 0))
        self._texture_photos = [ImageTk.PhotoImage(strip)]
        self._textures.config(image=self._texture_photos[0], text="")

    def _has_original(self, entry: effects.EffectEntry) -> bool:
        return self._pack_file(entry) in self._project.originals_in(self._pack_file(entry).parent)

    # -- editing --------------------------------------------------------------
    def _after_edit(self, name: str, message: str) -> None:
        self._load()
        if name in self._by_iid:
            self._tree.selection_set(name)
            self._tree.see(name)
            self._show_selected()
        self._status.config(text=f"{message} Build the project to use it in the game.")

    def _add(self) -> None:
        if not self._entries:
            messagebox.showinfo("Visual effects", "Extract the project first.", parent=self)
            return
        EffectAddDialog(self, self._project, self._changelog, self._entries,
                        lambda name: self._after_edit(name, f"Added {name}."))

    def _register_effect(self) -> None:
        entry = self._selected()
        if entry is not None and not entry.registered:
            EffectAddDialog(self, self._project, self._changelog, self._entries,
                            lambda name: self._after_edit(name, f"Registered {name}."), preset=entry)

    def _replace_pack(self) -> None:
        entry = self._selected()
        if entry is None:
            return
        source = filedialog.askopenfilename(parent=self, title=f"Replace {entry.name} with pack",
                                            filetypes=[("Effect pack", "*.cmp"), ("All files", "*.*")])
        if not source:
            return
        try:
            parts = effects.read_effect_pack(Path(source).read_bytes())
            effects.validate_pack(parts)
            data = effects.build_effect_pack(effects.rename_pack(parts, entry.name))
        except (effects.EffectError, OSError) as exc:
            messagebox.showerror("Visual effects", str(exc), parent=self)
            return
        self._write_pack(entry, data, f"Replaced the pack of {entry.name}")

    def _replace_texture(self) -> None:
        entry = self._selected()
        if entry is None:
            return
        image_path = filedialog.askopenfilename(parent=self, title=f"New texture for {entry.name}",
                                                filetypes=[("Images", "*.png *.jpg *.jpeg *.bmp"), ("All files", "*.*")])
        if not image_path:
            return
        try:
            parts = effects.read_effect_pack(self._pack_file(entry).read_bytes())
            tpl_name = next((n for n in parts if n.endswith(".tpl")), None)
            if tpl_name is None:
                raise effects.EffectError("This pack has no texture.")
            infos = tpl.read_tpl_image_info(io.BytesIO(parts[tpl_name]))
            index = 0
            if len(infos) > 1:
                index = simpledialog.askinteger("Replace texture", f"Image index (0-{len(infos) - 1}):",
                                                parent=self, initialvalue=0, minvalue=0, maxvalue=len(infos) - 1)
                if index is None:
                    return
            if infos[index].format not in tpl.ENCODABLE_FORMATS:
                raise effects.EffectError(f"Texture format {tpl.format_name(infos[index].format)} cannot be re-encoded.")
            with Image.open(image_path) as img:
                new_tpl = tpl.replace_image(parts[tpl_name], index, img.convert("RGBA"))
            data = effects.build_effect_pack(effects.replace_part(parts, "tpl", new_tpl))
        except (effects.EffectError, OSError, ValueError) as exc:
            messagebox.showerror("Visual effects", str(exc), parent=self)
            return
        self._write_pack(entry, data, f"Replaced the texture of {entry.name}")

    def _write_pack(self, entry: effects.EffectEntry, data: bytes, message: str) -> None:
        path = self._pack_file(entry)
        path.parent.mkdir(parents=True, exist_ok=True)
        self._project.write_keeping_original(path, data)
        self._changelog.append("Visual effects", message)
        self._after_edit(entry.name, message + ".")

    def _restore(self) -> None:
        entry = self._selected()
        if entry is None:
            return
        try:
            self._project.restore_original(self._pack_file(entry))
        except ProjectError as exc:
            messagebox.showerror("Visual effects", str(exc), parent=self)
            return
        self._changelog.append("Visual effects", f"Restored {entry.name}")
        self._after_edit(entry.name, f"Restored {entry.name}.")
