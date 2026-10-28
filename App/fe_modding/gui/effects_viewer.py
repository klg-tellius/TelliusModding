"""Visual effects page: every registered ``EID_*`` effect plus any
unregistered ``yme/`` pack, rendered with the 3D model preview (an effect is
an ordinary skeleton + mesh + animation + texture pack, see ``formats/effects.py``).

An effect's whole pack can be replaced from another ``.cmp``, its texture can
be replaced from an image, and a new effect can be added (``effect_add_dialog.py``). Radiant Dawn
uses the same workflows plus its four parameters, two child links and numeric aliases.
The preview shows the raw animation only; in-game timing and sequencing of the
effects are not decoded."""

from __future__ import annotations

import io
import struct
from dataclasses import replace
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, simpledialog, ttk

from PIL import Image, ImageTk

from ..formats import animation, effect_registry, effects, gs_file, skeleton, tpl
from ..exceptions import ProjectError
from ..games import Game
from ..project import ModProject
from .changelog import ChangeLog
from .editor_panel import EditorPanel
from .effect_add_dialog import EffectAddDialog
from .model_viewer import _build_loaded_set, _load_model_set, _ModelPreview
from .particle_editor import ParticleEditor

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
        self._read_only = False
        self._entries: list[effects.EffectEntry] = []
        self._by_iid: dict[str, effects.EffectEntry] = {}
        self._particle_layout: animation.ParticleTableLayout | None = None
        self._particle_data: bytes | None = None
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
        scroll.pack(side="right", fill="y")  # first: a wide list would push it out of view
        self._tree.pack(side="left", fill="both", expand=True)
        self._tree.bind("<<TreeviewSelect>>", lambda _e: self._show_selected())

        right = ttk.Frame(body, padding=(12, 0, 0, 0))
        body.add(right, weight=5)
        self._title = ttk.Label(right, text="(no effect selected)", font=("Segoe UI", 12, "bold"))
        self._title.pack(anchor="w")
        self._detail = ttk.Label(right, text="", justify="left", style="Muted.TLabel", wraplength=520)
        self._detail.pack(anchor="w", pady=(2, 6))
        actions = ttk.Frame(right)
        actions.pack(fill="x", pady=(0, 6))
        self._add_btn = ttk.Button(actions, text="Add effect...", command=self._add,
                                   state="disabled" if self._read_only else "normal")
        self._add_btn.grid(row=0, column=0, sticky="ew", padx=2, pady=2)
        self._replace_btn = ttk.Button(actions, text="Replace pack...", command=self._replace_pack, state="disabled")
        self._replace_btn.grid(row=0, column=1, sticky="ew", padx=2, pady=2)
        self._part_btn = ttk.Button(actions, text="Replace part...", command=self._replace_part, state="disabled")
        self._part_btn.grid(row=0, column=2, sticky="ew", padx=2, pady=2)
        self._texture_btn = ttk.Button(actions, text="Replace texture...", command=self._replace_texture, state="disabled")
        self._texture_btn.grid(row=1, column=0, sticky="ew", padx=2, pady=2)
        self._register_btn = ttk.Button(actions, text="Register...", command=self._register_effect, state="disabled")
        self._register_btn.grid(row=1, column=1, sticky="ew", padx=2, pady=2)
        self._registry_btn = ttk.Button(actions, text="Edit registry...", command=self._edit_registry, state="disabled")
        self._registry_btn.grid(row=1, column=2, sticky="ew", padx=2, pady=2)
        self._restore_btn = ttk.Button(actions, text="Restore original", command=self._restore, state="disabled")
        self._restore_btn.grid(row=2, column=0, sticky="ew", padx=2, pady=2)
        self._remove_btn = ttk.Button(actions, text="Remove added effect", command=self._remove, state="disabled")
        self._remove_btn.grid(row=2, column=1, columnspan=2, sticky="ew", padx=2, pady=2)
        for column in range(3):
            actions.columnconfigure(column, weight=1)
        self._status = ttk.Label(right, text="", style="Muted.TLabel", wraplength=520, justify="left")
        self._status.pack(anchor="w", pady=(0, 4))
        self._particle_btn = ttk.Button(right, text="Edit particles...",
                                        command=self._show_particle_details, state="disabled")
        self._particle_btn.pack(anchor="w", pady=(0, 6))
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
        registry = effects.registry_path(self._files, self._project.game)
        if not registry.exists():
            self._count.config(text=f"{registry.name} not found. Extract the project first.")
            return
        try:
            self._entries = effects.list_effects(self._files, self._project.game)
        except Exception as exc:  # noqa: BLE001 - corrupt registry: say so instead of a blank page
            self._count.config(text=f"Could not read {registry.name}: {exc}")
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
            if mode == "Chained" and not (e.next_in_chain or e.child_effects):
                continue
            self._by_iid[e.name] = e
            status = ("registered" if e.registered else "unregistered") + ("" if e.has_pack else ", no pack")
            chain = e.next_in_chain or ", ".join(e.child_effects)
            self._tree.insert("", "end", iid=e.name, values=(
                e.name, e.category if e.registered else "", chain, status))
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
        self._particle_layout = None
        self._particle_data = None
        self._particle_btn.config(state="disabled")
        writable = not self._read_only
        self._replace_btn.config(state="normal" if writable else "disabled")
        self._part_btn.config(state="normal" if writable and entry.has_pack else "disabled")
        self._texture_btn.config(state="normal" if writable and entry.has_pack else "disabled")
        self._register_btn.config(state="normal" if writable and not entry.registered else "disabled")
        self._registry_btn.config(state="normal" if writable and entry.registered else "disabled")
        self._restore_btn.config(state="normal" if writable and self._has_original(entry) else "disabled")
        removable = (self._project.game is Game.RADIANT_DAWN and entry.registered
                     and not self._is_vanilla_registry_entry(entry.name))
        self._remove_btn.config(state="normal" if removable else "disabled")
        registry_name = effects.REGISTRY_FILES[self._project.game]
        lines = [f"Registry flags: {entry.flags:#010x}" if entry.registered else f"Not in {registry_name}"]
        if entry.description:
            lines.append(f"Description: {entry.description}")
        if entry.sound_group:
            lines.append(f"Sound: {entry.sound_group}")
        if self._project.game is Game.RADIANT_DAWN and entry.registered:
            lines.append("Parameters +0C..+0F: " + ", ".join(map(str, entry.parameter_bytes)))
            if entry.numeric_ids:
                lines.append("Numeric effect IDs: " + ", ".join(map(str, entry.numeric_ids)))
            if entry.child_effects:
                lines.append("Child effects: " + ", ".join(entry.child_effects))
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
        ga_data = next((blob for name, blob in parts.items() if name.endswith(".ga")), None)
        if ga_data is not None:
            try:
                particles = animation.read_particle_table_layout(ga_data)
            except animation.AnimationError as exc:
                lines.append(f"Particle table unreadable: {exc}")
            else:
                if particles is not None:
                    self._particle_layout = particles
                    self._particle_data = ga_data
                    self._particle_btn.config(state="normal" if writable else "disabled")
                    count = len(particles.emitters)
                    stages = sum(emitter.stage_count for emitter in particles.emitters)
                    lines.append(f"Particle emitters: {count} ({stages} stages)")
                    names = [emitter.name_path for emitter in particles.emitters[:4]]
                    if names:
                        lines.append("Paths: " + ", ".join(names) + ("..." if count > 4 else ""))
        self._detail.config(text="\n".join(lines))
        self._status.config(text=("Particle stages render during animation playback (preview geometry)."
                                  if self._particle_layout is not None else ""))
        self._show_textures(parts)
        try:
            loaded = _load_model_set(entry.name, path)
            self._preview.show(loaded, "No model data.")
            if loaded.animations:
                self._preview.select_animation(loaded.animations[0][0])
        except Exception as exc:  # noqa: BLE001 - effect nodes use flags the rig viewer may not pose
            self._preview.show(None, "No preview.")
            self._status.config(text=f"Preview failed: {exc}")

    def _show_particle_details(self) -> None:
        layout = self._particle_layout
        data = self._particle_data
        if layout is None or data is None:
            return
        entry = self._selected()
        if entry is None:
            return
        expected_ga = data

        def save_particle(new_ga: bytes) -> None:
            nonlocal expected_ga
            parts = effects.read_effect_pack(self._pack_file(entry).read_bytes())
            current_ga = next((blob for name, blob in parts.items() if name.endswith(".ga")), None)
            if current_ga != expected_ga:
                raise effects.EffectError("This effect changed since the particle editor opened. Reopen it before saving.")
            gs_data = next((blob for name, blob in parts.items() if name.endswith(".gs")), None)
            if gs_data is not None:
                material_count = len(gs_file.read_gs(gs_data).materials)
                layout = animation.read_particle_table_layout(new_ga)
                previous_layout = animation.read_particle_table_layout(expected_ga)
                for index, emitter in enumerate(layout.emitters if layout else ()):
                    previous = (previous_layout.emitters[index].material_index
                                if previous_layout and index < len(previous_layout.emitters) else None)
                    if (emitter.material_index != previous and emitter.material_index != -1
                            and not 0 <= emitter.material_index < material_count):
                        raise effects.EffectError(
                            f"Emitter {index} uses material {emitter.material_index}; this effect has {material_count} materials.")
            new_pack = effects.build_effect_pack(effects.replace_part(parts, "ga", new_ga))
            self._write_pack(entry, new_pack, f"Edited particles of {entry.name}")
            expected_ga = new_ga

        try:
            current_parts = effects.read_effect_pack(self._pack_file(entry).read_bytes())
            gs_data = next((blob for name, blob in current_parts.items() if name.endswith(".gs")), None)
            material_count = len(gs_file.read_gs(gs_data).materials) if gs_data else 0
        except (effects.EffectError, gs_file.GsFileError, OSError) as exc:
            messagebox.showerror("Particle editor", str(exc), parent=self)
            return
        animation_name = next((name for name in current_parts if name.endswith(".ga")), None)
        try:
            preview_loaded = _build_loaded_set(entry.name, current_parts, [])
        except Exception:  # noqa: BLE001 - the inspector remains usable when preview decoding fails
            preview_loaded = None
        ParticleEditor(self, entry.name, data, save_particle, material_count,
                       preview_loaded, animation_name)

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

    def _is_vanilla_registry_entry(self, name: str) -> bool:
        path = effects.registry_path(self._files, self._project.game)
        original = self._project.originals_dir / path.relative_to(self._project.extracted_dir)
        source = original if original.is_file() else path
        try:
            return name in effects.registry_names(source.read_bytes(), self._project.game)
        except Exception:  # noqa: BLE001 - a corrupt original is protected, never made removable
            return True

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

    def _edit_registry(self) -> None:
        entry = self._selected()
        if entry is None or not entry.registered:
            return
        flags_text = simpledialog.askstring("Effect registry", "Raw flags (hex or decimal):",
                                            initialvalue=f"0x{entry.flags:08X}", parent=self)
        if flags_text is None:
            return
        if self._project.game is Game.RADIANT_DAWN:
            self._edit_rd_registry(entry, flags_text)
            return
        chain_text = simpledialog.askstring("Effect registry", "Next effect in chain (blank for none):",
                                            initialvalue=entry.next_in_chain or "", parent=self)
        if chain_text is None:
            return
        try:
            flags = int(flags_text.strip(), 0)
            if not 0 <= flags <= 0xFFFFFFFF:
                raise ValueError("Flags must be a 32-bit unsigned number.")
            chain = chain_text.strip() or None
            path = effects.registry_path(self._files)
            records = effect_registry.read_effect_registry(path.read_bytes())
            names = {record.eid_name for record in records}
            if chain is not None and chain not in names:
                raise ValueError(f"Unknown chain target: {chain}")
            index = next(i for i, record in enumerate(records) if record.eid_name == entry.name)
            records[index] = replace(records[index], flags=flags, next_in_chain=chain)
            if chain is not None and entry.name in effect_registry.chain(records, chain):
                raise ValueError("The chain would contain a cycle.")
            self._project.write_keeping_original(path, effect_registry.build_effect_registry(records))
        except (OSError, ValueError, StopIteration, IndexError) as exc:
            messagebox.showerror("Effect registry", str(exc), parent=self)
            return
        self._changelog.append("Visual effects", f"Edited registry entry {entry.name}")
        self._after_edit(entry.name, f"Edited registry entry {entry.name}.")

    def _edit_rd_registry(self, entry: effects.EffectEntry, flags_text: str) -> None:
        description = simpledialog.askstring(
            "Effect registry", "Description:", initialvalue=entry.description, parent=self)
        if description is None:
            return
        parameters = simpledialog.askstring(
            "Effect registry", "Four parameter bytes (0-255, comma-separated):",
            initialvalue=", ".join(map(str, entry.parameter_bytes)), parent=self)
        if parameters is None:
            return
        children = simpledialog.askstring(
            "Effect registry", "Up to two child EIDs (comma-separated; blank for none):",
            initialvalue=", ".join(entry.child_effects), parent=self)
        if children is None:
            return
        sound = simpledialog.askstring(
            "Effect registry", "Sound group (blank for none):",
            initialvalue=entry.sound_group or "", parent=self)
        if sound is None:
            return
        aliases = simpledialog.askstring(
            "Effect registry", "Numeric effect IDs (comma-separated; blank for none):",
            initialvalue=", ".join(map(str, entry.numeric_ids)), parent=self)
        if aliases is None:
            return
        try:
            flags = int(flags_text.strip(), 0)
            if not 0 <= flags <= 0xFFFFFFFF:
                raise ValueError("Flags must be a 32-bit unsigned number.")
            values = tuple(int(value.strip(), 0) for value in parameters.split(",") if value.strip())
            if len(values) != 4 or any(not 0 <= value <= 255 for value in values):
                raise ValueError("Enter exactly four parameter bytes from 0 to 255.")
            child_names = tuple(value.strip() for value in children.split(",") if value.strip())
            if len(child_names) > 2:
                raise ValueError("An RD effect has at most two child effects.")
            child_slots = (child_names + (None, None))[:2]
            numeric_ids = tuple(int(value.strip(), 0) for value in aliases.split(",") if value.strip())
            path = effects.registry_path(self._files, self._project.game)
            rebuilt = effects.update_rd_registry_record(
                path.read_bytes(), entry.name, description=description, flags=flags,
                parameter_bytes=values, child_effects=child_slots,
                sound_group=sound.strip() or None, numeric_ids=numeric_ids,
            )
            self._project.write_keeping_original(path, rebuilt)
        except (OSError, ValueError, effects.EffectError) as exc:
            messagebox.showerror("Effect registry", str(exc), parent=self)
            return
        self._changelog.append("Visual effects", f"Edited registry entry {entry.name}")
        self._after_edit(entry.name, f"Edited registry entry {entry.name}.")

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

    def _replace_part(self) -> None:
        entry = self._selected()
        if entry is None or not entry.has_pack:
            return
        source = filedialog.askopenfilename(parent=self, title=f"Replace a part of {entry.name}",
                                            filetypes=[("Effect members", "*.g *.gs *.ga *.tpl"),
                                                       ("All files", "*.*")])
        if not source:
            return
        try:
            source_path = Path(source)
            ext = source_path.suffix.lower().lstrip(".")
            if ext not in effects.PART_EXTENSIONS:
                raise effects.EffectError("Choose a .g, .gs, .ga, or .tpl file.")
            blob = source_path.read_bytes()
            if ext == "g":
                skeleton.read_skeleton_file(blob)
            elif ext == "gs":
                gs_file.read_gs(blob)
            elif ext == "ga":
                animation.read_animation_bytes(blob)
                animation.read_particle_table_layout(blob)
            else:
                tpl.read_tpl_image_info(io.BytesIO(blob))
            parts = effects.read_effect_pack(self._pack_file(entry).read_bytes())
            data = effects.build_effect_pack(effects.replace_part(parts, ext, blob))
        except (OSError, ValueError, IndexError, struct.error, effects.EffectError,
                animation.AnimationError, gs_file.GsFileError, tpl.TplError) as exc:
            messagebox.showerror("Visual effects", str(exc), parent=self)
            return
        self._write_pack(entry, data, f"Replaced {entry.name}.{ext}")

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

    def _remove(self) -> None:
        entry = self._selected()
        if entry is None or self._project.game is not Game.RADIANT_DAWN:
            return
        if self._is_vanilla_registry_entry(entry.name):
            messagebox.showerror("Remove effect", "The game's original registry rows are protected.", parent=self)
            return
        if not messagebox.askyesno(
                "Remove added effect", f"Remove {entry.name} from FE10Effect.cms and delete its added pack?",
                parent=self):
            return
        registry = effects.registry_path(self._files, self._project.game)
        pack = self._pack_file(entry)
        try:
            rebuilt = effects.remove_rd_registry_record(registry.read_bytes(), entry.name)
            self._project.write_keeping_original(registry, rebuilt)
            original = self._project.originals_dir / pack.relative_to(self._project.extracted_dir)
            if pack.is_file() and not original.exists():
                pack.unlink()
        except (OSError, ValueError, effects.EffectError) as exc:
            messagebox.showerror("Remove effect", str(exc), parent=self)
            return
        self._changelog.append("Visual effects", f"Removed added effect {entry.name}")
        self._load()
