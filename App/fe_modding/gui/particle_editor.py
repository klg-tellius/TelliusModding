"""Inspector for the editable particle fields of one effect animation."""

from __future__ import annotations

import struct
import tkinter as tk
from dataclasses import replace
from tkinter import messagebox, simpledialog, ttk

from ..formats import animation, particle_editor as edits
from .model_viewer import _LoadedSet, _ModelPreview


FIELD_LABELS = {
    "material": "Material index", "draw_flags": "Draw flags (hex or decimal)",
    "raw_control": "Unknown control +0C (raw)", "mode1_scale": "Mode 1 scale",
    "line_width": "Line width", "mode2_scale": "Mode 2 scale",
    "mode2_alpha": "Mode 2 alpha", "scale_s": "Initial S scale",
    "scale_t": "Initial T scale", "rotation": "Initial rotation (degrees)",
    "start": "Start frame", "end": "End frame", "x": "Initial X",
    "y": "Initial Y", "z": "Initial Z", "channel": "Channel",
    "scale_shift": "Value divisor shift", "frame": "Local frame", "value": "Raw value",
}
TRACK_NAMES = {1: "Material alpha", 2: "Material colour (RGB565)",
               3: "Texture U scroll", 4: "Texture V scroll"}


class ParticleEditor(tk.Toplevel):
    def __init__(self, parent: tk.Misc, effect_name: str, ga: bytes, on_save,
                 material_count: int = 0, preview_loaded: _LoadedSet | None = None,
                 animation_name: str | None = None):
        super().__init__(parent)
        self.title(f"Particle editor — {effect_name}")
        self.geometry("1450x760" if preview_loaded is not None else "1070x650")
        self._original = ga
        self._data = ga
        self._undo: list[bytes] = []
        self._on_save = on_save
        self._material_count = material_count
        self._preview_base = preview_loaded
        self._animation_name = animation_name
        self._fields: dict[str, tk.StringVar] = {}
        self._selected: tuple[int, ...] | None = None
        self._build()
        self._populate()
        self._refresh_preview()
        self.protocol("WM_DELETE_WINDOW", self._close)

    def _build(self) -> None:
        outer = ttk.Frame(self, padding=10)
        outer.pack(fill="both", expand=True)
        header = ttk.Frame(outer)
        header.pack(fill="x", pady=(0, 8))
        ttk.Label(header, text="Select an emitter, stage, curve, or key. Values with /64 are stored as fixed point.",
                  style="Muted.TLabel").pack(side="left")
        ttk.Button(header, text="Add emitter...", command=lambda: self._guard(self._add_emitter)).pack(side="right")
        body = ttk.PanedWindow(outer, orient="horizontal")
        body.pack(fill="both", expand=True)
        self._body = body
        self.after(100, self._place_sashes)
        left = ttk.Frame(body)
        body.add(left, weight=3)
        self._tree = ttk.Treeview(left, columns=("details",), show="tree headings", selectmode="browse")
        self._tree.heading("#0", text="Particle")
        self._tree.heading("details", text="Details")
        self._tree.column("#0", width=290)
        self._tree.column("details", width=240)
        self._tree.pack(side="left", fill="both", expand=True)
        scrollbar = ttk.Scrollbar(left, orient="vertical", command=self._tree.yview)
        scrollbar.pack(side="right", fill="y")
        self._tree.configure(yscrollcommand=scrollbar.set)
        self._tree.bind("<<TreeviewSelect>>", self._select)
        self._tree.bind("<<TreeviewOpen>>", self._open_item)
        right = ttk.Frame(body, padding=(14, 0, 0, 0))
        body.add(right, weight=2)
        self._heading = ttk.Label(right, text="Select a particle item", font=("Segoe UI", 11, "bold"))
        self._heading.pack(anchor="w", pady=(0, 8))
        self._properties = ttk.Frame(right)
        self._properties.pack(fill="both", expand=True)
        self._chart = tk.Canvas(right, height=110, background="#20232a", highlightthickness=0)
        self._chart.pack(fill="x", pady=(4, 6))
        self._help = ttk.Label(right, text="", wraplength=380, justify="left", style="Muted.TLabel")
        self._help.pack(anchor="w", pady=(8, 5))
        row = ttk.Frame(right)  # one row, so the actions stay in view below tall field lists
        row.pack(fill="x")
        ttk.Button(row, text="Apply fields", command=self._apply).pack(side="right")
        self._actions = ttk.Frame(row)
        self._actions.pack(side="left", fill="x", expand=True)
        self._preview = None
        if self._preview_base is not None:
            preview_host = ttk.Frame(body, padding=(10, 0, 0, 0))
            body.add(preview_host, weight=4)
            ttk.Label(preview_host, text="Approximate preview; check final appearance in Dolphin.",
                      style="Muted.TLabel").pack(anchor="w", pady=(0, 5))
            self._preview = _ModelPreview(preview_host)
            self._preview.pack(fill="both", expand=True)
        bar = ttk.Frame(outer)
        bar.pack(side="bottom", fill="x", pady=(10, 0), before=body)  # kept visible when the fields are tall
        self._status = ttk.Label(bar, text="No changes", style="Muted.TLabel")
        self._status.pack(side="left")
        ttk.Button(bar, text="Save effect", command=self._save).pack(side="right", padx=(6, 0))
        ttk.Button(bar, text="Close", command=self._close).pack(side="right", padx=(6, 0))
        ttk.Button(bar, text="Undo", command=self._undo_last).pack(side="right", padx=(6, 0))
        ttk.Button(bar, text="Discard edits", command=self._discard).pack(side="right")

    def _place_sashes(self, tries: int = 30) -> None:
        """Share the width between the panes: they open at their requested widths, which left the
        field panel too narrow to show its values. Retried until the window has its real size."""
        try:
            width = self._body.winfo_width()
            if width < 600 and tries > 0:
                self.after(100, lambda: self._place_sashes(tries - 1))
                return
            if len(self._body.panes()) == 3:  # tree | fields | preview
                self._body.sashpos(0, int(width * 0.28))
                self._body.sashpos(1, int(width * 0.58))
            else:
                self._body.sashpos(0, int(width * 0.5))
        except tk.TclError:
            pass

    def _populate(self, keep: str | None = None) -> None:
        self._tree.delete(*self._tree.get_children())
        events = animation.read_animation_bytes(self._data).events
        self._tree.insert("", "end", iid="events", text="Timing events", values=(f"{len(events)} events",))
        for index, event in enumerate(events):
            self._tree.insert("events", "end", iid=f"event:{index}", text=f"Frame {event.frame}",
                              values=(", ".join(str(code) for code in event.codes),))
        anim = animation.read_animation_bytes(self._data)
        for slot, title in TRACK_NAMES.items():
            block = anim.footer.blocks[slot] if anim.footer else None
            tracks = animation.read_material_tracks(block) if block else {}
            if block:
                self._material_count = max(self._material_count, struct.unpack_from(">H", block)[0])
            root = f"material:{slot}"
            self._tree.insert("", "end", iid=root, text=title, values=(f"{len(tracks)} tracks",))
            for index, track in tracks.items():
                self._tree.insert(root, "end", iid=f"{root}:{index}", text=f"Material {index}",
                                  values=(f"{len(track.keys)} keys; mode {track.mode}",))
        layout = animation.read_particle_table_layout(self._data)
        if layout is None:
            return
        for eidx, emitter in enumerate(layout.emitters):
            eid = f"e:{eidx}"
            self._tree.insert("", "end", iid=eid, text=f"{eidx}: {emitter.name_path}",
                              values=(f"material {emitter.material_index}; {emitter.stage_count} stages",))
            if emitter.stage_count:
                self._tree.insert(eid, "end", iid=f"{eid}:pending")
        if keep:
            parts = keep.split(":")
            for depth in (2, 4, 6):
                if len(parts) > depth:
                    parent = ":".join(parts[:depth])
                    if self._tree.exists(parent):
                        self._fill_children(parent)
                        self._tree.item(parent, open=True)
            if self._tree.exists(keep):
                self._tree.selection_set(keep)
                self._tree.see(keep)
                self._show_fields(keep)

    def _open_item(self, _event=None) -> None:
        iid = self._tree.focus()
        if iid:
            self._fill_children(iid)

    def _fill_children(self, iid: str) -> None:
        pending = f"{iid}:pending"
        if not self._tree.exists(pending):
            return
        self._tree.delete(pending)
        parts = iid.split(":")
        eidx = int(parts[1])
        emitter = animation.read_particle_table_layout(self._data).emitters[eidx]
        if len(parts) == 2:
            for sidx in range(emitter.stage_count):
                stage = animation.read_particle_stage(self._data, emitter, sidx)
                sid = f"{iid}:s:{sidx}"
                self._tree.insert(iid, "end", iid=sid, text=f"Stage {sidx}",
                                  values=(f"frames {stage.start_frame}–{stage.end_frame}; {stage.curve_count} curves",))
                if stage.curve_count:
                    self._tree.insert(sid, "end", iid=f"{sid}:pending")
        elif len(parts) == 4:
            stage = animation.read_particle_stage(self._data, emitter, int(parts[3]))
            for cidx in range(stage.first_curve, stage.first_curve + stage.curve_count):
                curve = animation.read_particle_curve(self._data, emitter, cidx)
                cid = f"{iid}:c:{cidx}"
                self._tree.insert(iid, "end", iid=cid, text=f"{curve.channel_name} [{cidx}]",
                                  values=(f"{curve.key_count} keys; /{1 << curve.scale_shift}",))
                if curve.key_count:
                    self._tree.insert(cid, "end", iid=f"{cid}:pending")
        elif len(parts) == 6:
            curve = animation.read_particle_curve(self._data, emitter, int(parts[5]))
            keys_at = emitter.keys_offset + curve.first_key * 4
            for kidx in range(curve.key_count):
                frame, raw = struct.unpack_from(">Hh", self._data, keys_at + kidx * 4)
                self._tree.insert(iid, "end", iid=f"{iid}:k:{kidx}", text=f"Key {kidx}",
                                  values=(f"frame {frame}: {raw / (1 << curve.scale_shift):g}",))

    def _select(self, _event=None) -> None:
        selected = self._tree.selection()
        if selected:
            self._show_fields(selected[0])

    def _show_fields(self, iid: str) -> None:
        for child in self._properties.winfo_children():
            child.destroy()
        self._fields = {}
        if iid == "events" or iid.startswith("event:"):
            self._show_event_fields(iid)
            return
        if iid.startswith("material:"):
            self._show_material_fields(iid)
            return
        parts = iid.split(":")
        eidx = int(parts[1])
        emitter = animation.read_particle_table_layout(self._data).emitters[eidx]
        address = emitter.record_offset
        fieldset = edits.EMITTER_FIELDS
        kind = "Emitter"
        if len(parts) >= 4:
            sidx = int(parts[3])
            address = emitter.stages_offset + sidx * 12
            fieldset = edits.STAGE_FIELDS
            kind = "Stage"
        if len(parts) >= 6:
            cidx = int(parts[5])
            address = emitter.curves_offset + cidx * 12
            fieldset = edits.CURVE_FIELDS
            kind = "Curve"
        if len(parts) >= 8:
            kidx = int(parts[7])
            curve = animation.read_particle_curve(self._data, emitter, cidx)
            address = emitter.keys_offset + (curve.first_key + kidx) * 4
            fieldset = edits.KEY_FIELDS
            kind = "Key"
        self._heading.config(text=f"{kind} properties")
        first_row = 0
        if kind == "Emitter":
            ttk.Label(self._properties, text="Emitter path").grid(row=0, column=0, sticky="w", pady=3)
            self._fields["name_path"] = tk.StringVar(value=emitter.name_path)
            ttk.Entry(self._properties, textvariable=self._fields["name_path"]).grid(
                row=0, column=1, sticky="ew", padx=(10, 0), pady=3)
            first_row = 1
        for row, (name, field) in enumerate(fieldset.items(), start=first_row):
            ttk.Label(self._properties, text=FIELD_LABELS[name]).grid(row=row, column=0, sticky="w", pady=3)
            value = edits.field_value(self._data, address, field)
            if name == "scale_shift":
                value &= 0x3F
            initial = f"0x{value:04X}" if name in ("draw_flags", "raw_control") else str(value)
            variable = tk.StringVar(value=initial)
            self._fields[name] = variable
            ttk.Entry(self._properties, textvariable=variable, width=16).grid(row=row, column=1, sticky="ew", padx=(10, 0), pady=3)
            if field.scale != 1:
                ttk.Label(self._properties, text=f"÷ {field.scale}", style="Muted.TLabel").grid(row=row, column=2, padx=5)
        self._properties.columnconfigure(1, weight=1)
        if kind == "Emitter":
            help_text = ("The +0C control has no confirmed meaning. Draw flags: low 3 bits choose "
                         "the draw path; 0x0800 visibility gate, 0x1000 additive blend, "
                         "0x2000 subtractive blend, 0x4000 no depth test, 0x8000 alternate TEV order.")
        elif kind == "Curve":
            help_text = "Channels 0–2: velocity XYZ; 3: common scale; 4: alpha; 5–7: RGB; 8–9: scale S/T; 10: rotation Z."
        elif kind == "Key":
            help_text = "The displayed raw value is divided by 2^shift during playback. Key frames are local to the stage."
        else:
            help_text = "Stage positions are signed values divided by 64; start and end use animation frames."
        self._help.config(text=help_text)
        self._draw_curve(emitter, int(parts[5]) if len(parts) >= 6 else None)
        for child in self._actions.winfo_children():
            child.destroy()
        if kind == "Emitter":
            self._action("Add stage", lambda: self._change(edits.add_stage(self._data, eidx), iid))
            self._action("Duplicate emitter", lambda: self._change(
                edits.duplicate_emitter(self._data, eidx),
                f"e:{len(animation.read_particle_table_layout(self._data).emitters)}"))
            self._action("Remove emitter", lambda: self._remove(
                lambda: edits.remove_emitter(self._data, eidx), "events"))
        elif kind == "Stage":
            self._action("Duplicate", lambda: self._change(edits.duplicate_stage(self._data, eidx, sidx), iid))
            self._action("Move up", lambda: self._change(edits.move_stage(self._data, eidx, sidx, -1), iid))
            self._action("Move down", lambda: self._change(edits.move_stage(self._data, eidx, sidx, 1), iid))
            self._action("Add curve", lambda: self._add_curve(eidx, sidx, iid))
            self._action("Remove stage", lambda: self._remove(
                lambda: edits.remove_stage(self._data, eidx, sidx), f"e:{eidx}"))
        elif kind == "Curve":
            self._action("Add key", lambda: self._add_key(eidx, cidx, iid))
            self._action("Remove curve", lambda: self._remove(
                lambda: edits.remove_curve(self._data, eidx, sidx, cidx), f"e:{eidx}:s:{sidx}"))
        elif kind == "Key":
            self._action("Remove key", lambda: self._remove(
                lambda: edits.remove_key(self._data, eidx, cidx, kidx),
                f"e:{eidx}:s:{sidx}:c:{cidx}"))
        self._seek_selected_particle(emitter, parts)

    def _seek_selected_particle(self, emitter: animation.ParticleEmitterLayout,
                                parts: list[str]) -> None:
        if self._preview is None or self._preview._current_animation is None:
            return
        if len(parts) >= 4:
            stage = animation.read_particle_stage(self._data, emitter, int(parts[3]))
        elif emitter.stage_count:
            stage = animation.read_particle_stage(self._data, emitter, 0)
        else:
            return
        frame = stage.start_frame
        if len(parts) >= 8:
            curve = animation.read_particle_curve(self._data, emitter, int(parts[5]))
            key_address = emitter.keys_offset + (curve.first_key + int(parts[7])) * 4
            frame += struct.unpack_from(">H", self._data, key_address)[0]
        self._preview._frame_scale.set(max(0, min(frame, self._preview._current_animation.length_in_frames)))

    def _action(self, label: str, command) -> None:
        index = len(self._actions.winfo_children())
        ttk.Button(self._actions, text=label, command=lambda: self._guard(command)).grid(
            row=index // 2, column=index % 2, sticky="ew", padx=(0, 5), pady=3)
        self._actions.columnconfigure(index % 2, weight=1)

    def _show_event_fields(self, iid: str) -> None:
        for child in self._actions.winfo_children():
            child.destroy()
        self._draw_curve(None, None)
        if iid == "events":
            self._heading.config(text="Timing events")
            self._help.config(text="Events can trigger effect movement, hits, sound, and other game actions. Preserve unfamiliar codes.")
            self._action("Add event", self._add_event)
            return
        index = int(iid.split(":")[1])
        event = animation.read_animation_bytes(self._data).events[index]
        self._heading.config(text=f"Event {index}")
        self._help.config(text="Enter event codes as comma-separated decimal or hex numbers. Their meanings depend on the game action.")
        for row, (label, value) in enumerate((("Frame", str(event.frame)),
                                               ("Codes", ", ".join(str(code) for code in event.codes)))):
            key = "frame" if row == 0 else "codes"
            ttk.Label(self._properties, text=label).grid(row=row, column=0, sticky="w", pady=3)
            self._fields[key] = tk.StringVar(value=value)
            ttk.Entry(self._properties, textvariable=self._fields[key]).grid(
                row=row, column=1, sticky="ew", padx=(10, 0), pady=3)
        self._properties.columnconfigure(1, weight=1)
        self._action("Remove event", lambda: self._remove(
            lambda: edits.replace_events(self._data,
                                         [item for n, item in enumerate(animation.read_animation_bytes(self._data).events)
                                          if n != index]), "events"))

    def _tracks(self, slot: int) -> dict[int, animation.MaterialTrack]:
        anim = animation.read_animation_bytes(self._data)
        block = anim.footer.blocks[slot] if anim.footer else None
        return animation.read_material_tracks(block) if block else {}

    def _show_material_fields(self, iid: str) -> None:
        for child in self._actions.winfo_children():
            child.destroy()
        self._draw_curve(None, None)
        parts = iid.split(":")
        slot = int(parts[1])
        title = TRACK_NAMES[slot]
        self._heading.config(text=title)
        if len(parts) == 2:
            self._help.config(text="Tracks are indexed by .gs material. Values are stored as signed 16-bit integers."
                                   + (" Alpha uses 0–255." if slot == 1 else ""))
            self._action("Add track", lambda: self._add_material_track(slot))
            return
        index = int(parts[2])
        track = self._tracks(slot)[index]
        self._help.config(text="Keys: frame:value pairs separated by commas. Mode 0 interpolates; mode 1 holds values.")
        for row, (label, value) in enumerate((("Mode", str(track.mode)),
                                               ("Keys", ", ".join(f"{frame}:{value}" for frame, value in track.keys)))):
            key = "mode" if row == 0 else "keys"
            ttk.Label(self._properties, text=label).grid(row=row, column=0, sticky="w", pady=3)
            self._fields[key] = tk.StringVar(value=value)
            ttk.Entry(self._properties, textvariable=self._fields[key]).grid(
                row=row, column=1, sticky="ew", padx=(10, 0), pady=3)
        self._properties.columnconfigure(1, weight=1)
        self._action("Remove track", lambda: self._remove(
            lambda: self._replace_track(slot, index, None), f"material:{slot}"))

    def _replace_track(self, slot: int, index: int, track: animation.MaterialTrack | None) -> bytes:
        tracks = self._tracks(slot)
        if track is None:
            tracks.pop(index, None)
        else:
            tracks[index] = track
        return edits.replace_material_tracks(self._data, slot, tracks, self._material_count)

    def _add_material_track(self, slot: int) -> None:
        if self._material_count <= 0:
            raise edits.ParticleEditError("This effect has no materials.")
        index = simpledialog.askinteger("Add material track", f"Material index (0–{self._material_count - 1}):",
                                        parent=self, minvalue=0, maxvalue=self._material_count - 1)
        if index is None:
            return
        if index in self._tracks(slot):
            raise edits.ParticleEditError("That material already has a track.")
        initial = 255 if slot == 1 else 0
        self._change(self._replace_track(slot, index, animation.MaterialTrack(0, ((0, initial),))),
                     f"material:{slot}:{index}")

    def _parse_track_keys(self, text: str) -> tuple[tuple[int, int], ...]:
        if not text.strip():
            return ()
        keys = []
        for piece in text.split(","):
            frame_text, value_text = piece.strip().split(":", 1)
            keys.append((int(frame_text.strip(), 0), int(value_text.strip(), 0)))
        return tuple(keys)

    def _parse_codes(self, text: str) -> tuple[int, ...]:
        return tuple(int(piece.strip(), 0) for piece in text.split(",") if piece.strip())

    def _add_event(self) -> None:
        frame = simpledialog.askinteger("Add event", "Frame:", parent=self, minvalue=0, maxvalue=65535)
        if frame is None:
            return
        codes_text = simpledialog.askstring("Add event", "Codes (comma-separated decimal or hex):",
                                             parent=self)
        if codes_text is None:
            return
        events = animation.read_animation_bytes(self._data).events
        events.append(animation.EventKey(frame, self._parse_codes(codes_text)))
        events.sort(key=lambda item: item.frame)
        self._change(edits.replace_events(self._data, events), "events")

    def _draw_curve(self, emitter: animation.ParticleEmitterLayout | None, curve_index: int | None) -> None:
        canvas = self._chart
        canvas.delete("all")
        if curve_index is None:
            canvas.create_text(12, 12, anchor="nw", text="Select a curve or key to see its values.",
                               fill="#b9c1cc")
            return
        curve = animation.read_particle_curve(self._data, emitter, curve_index)
        keys = animation.read_particle_curve_keys(self._data, emitter, curve)
        if not keys:
            canvas.create_text(12, 12, anchor="nw", text="This curve has no keys.", fill="#b9c1cc")
            return
        canvas.update_idletasks()
        width = max(240, canvas.winfo_width())
        height = max(90, canvas.winfo_height())
        left, right, top, bottom = 38, width - 16, 20, height - 24
        values = [value for _, value in keys]
        min_value, max_value = min(values), max(values)
        if min_value == max_value:
            min_value -= 1
            max_value += 1
        last_frame = max(1, keys[-1][0])
        points = [(left + (right - left) * frame / last_frame,
                   bottom - (bottom - top) * (value - min_value) / (max_value - min_value))
                  for frame, value in keys]
        canvas.create_line(left, top, left, bottom, right, bottom, fill="#77818f")
        canvas.create_text(4, top, anchor="nw", text=f"{max_value:g}", fill="#b9c1cc")
        canvas.create_text(4, bottom, anchor="sw", text=f"{min_value:g}", fill="#b9c1cc")
        canvas.create_text(right, bottom + 5, anchor="nw", text=str(last_frame), fill="#b9c1cc")
        if len(points) > 1:
            canvas.create_line(*(coordinate for point in points for coordinate in point),
                               fill="#64c8f5", width=2)
        for x, y in points:
            canvas.create_oval(x - 3, y - 3, x + 3, y + 3, fill="#f9d66c", outline="")

    def _guard(self, command) -> None:
        try:
            command()
        except (ValueError, animation.AnimationError, struct.error) as exc:
            messagebox.showerror("Particle editor", str(exc), parent=self)

    def _change(self, updated: bytes, keep: str | None) -> None:
        if updated != self._data:
            self._undo.append(self._data)
            if len(self._undo) > 20:
                del self._undo[0]
            self._data = updated
            self._status.config(text="Unsaved changes")
            self._populate(keep)
            self._refresh_preview()

    def _refresh_preview(self) -> None:
        if self._preview is None or self._preview_base is None:
            return
        frame = self._preview._frame_scale.get() if self._preview._current_animation else 0
        animations = [(name, self._data if name == self._animation_name else raw)
                      for name, raw in self._preview_base.animations]
        loaded = replace(self._preview_base, animations=animations)
        self._preview.show(loaded)
        if self._animation_name:
            self._preview.select_animation(self._animation_name)
            if self._preview._current_animation is not None:
                self._preview._frame_scale.set(min(frame, self._preview._current_animation.length_in_frames))

    def _remove(self, operation, keep: str) -> None:
        if messagebox.askyesno("Particle editor", "Remove this item?", parent=self):
            self._change(operation(), keep)

    def _add_curve(self, eidx: int, sidx: int, keep: str) -> None:
        channel = simpledialog.askinteger("Add curve", "Channel (0–10):", parent=self,
                                          minvalue=0, maxvalue=10)
        if channel is not None:
            self._change(edits.add_curve(self._data, eidx, sidx, channel), keep)

    def _add_emitter(self) -> None:
        name = simpledialog.askstring("Add emitter", "Emitter path:", parent=self,
                                      initialvalue="|root|")
        if name is None:
            return
        count = len(animation.read_particle_table_layout(self._data).emitters)
        self._change(edits.add_emitter(self._data, name.strip()), f"e:{count}")

    def _add_key(self, eidx: int, cidx: int, keep: str) -> None:
        frame = simpledialog.askinteger("Add key", "Local frame:", parent=self,
                                        minvalue=0, maxvalue=65535)
        if frame is None:
            return
        value = simpledialog.askinteger("Add key", "Raw value:", parent=self,
                                        minvalue=-32768, maxvalue=32767)
        if value is not None:
            self._change(edits.add_key(self._data, eidx, cidx, frame, value), keep)

    def _apply(self) -> None:
        selected = self._tree.selection()
        if not selected:
            return
        iid = selected[0]
        if iid == "events":
            return
        if iid.startswith("event:"):
            try:
                index = int(iid.split(":")[1])
                events = animation.read_animation_bytes(self._data).events
                events[index] = animation.EventKey(int(self._fields["frame"].get().strip(), 0),
                                                    self._parse_codes(self._fields["codes"].get()))
                events.sort(key=lambda item: item.frame)
                self._change(edits.replace_events(self._data, events), "events")
            except (ValueError, animation.AnimationError, struct.error) as exc:
                messagebox.showerror("Particle editor", str(exc), parent=self)
            return
        if iid.startswith("material:"):
            parts = iid.split(":")
            if len(parts) == 2:
                return
            try:
                slot, index = int(parts[1]), int(parts[2])
                track = animation.MaterialTrack(int(self._fields["mode"].get().strip(), 0),
                                                self._parse_track_keys(self._fields["keys"].get()))
                self._change(self._replace_track(slot, index, track), iid)
            except (ValueError, animation.AnimationError, struct.error) as exc:
                messagebox.showerror("Particle editor", str(exc), parent=self)
            return
        parts = iid.split(":")
        try:
            values = {name: int(variable.get().strip(), 0) for name, variable in self._fields.items()
                      if name != "name_path"}
            eidx = int(parts[1])
            if len(parts) == 2:
                updated = edits.edit_emitter(self._data, eidx, **values)
                updated = edits.edit_emitter_name(updated, eidx, self._fields["name_path"].get().strip())
            elif len(parts) == 4:
                updated = edits.edit_stage(self._data, eidx, int(parts[3]), **values)
            elif len(parts) == 6:
                updated = edits.edit_curve(self._data, eidx, int(parts[5]), **values)
            else:
                updated = edits.edit_key(self._data, eidx, int(parts[5]), int(parts[7]), **values)
        except (ValueError, animation.AnimationError, struct.error) as exc:
            messagebox.showerror("Particle editor", str(exc), parent=self)
            return
        if updated != self._data:
            self._change(updated, iid)

    def _undo_last(self) -> None:
        if self._undo:
            self._data = self._undo.pop()
            self._status.config(text="Unsaved changes" if self._data != self._original else "No changes")
            self._populate(self._tree.selection()[0] if self._tree.selection() else None)
            self._refresh_preview()

    def _discard(self) -> None:
        self._data = self._original
        self._undo.clear()
        self._status.config(text="No changes")
        self._populate()
        self._refresh_preview()

    def _save(self) -> None:
        if self._data == self._original:
            return
        try:
            self._on_save(self._data)
        except Exception as exc:  # noqa: BLE001 - filesystem and pack errors are shown in the editor
            messagebox.showerror("Particle editor", str(exc), parent=self)
            return
        self._original = self._data
        self._undo.clear()
        self._status.config(text="Saved")

    def _close(self) -> None:
        if self._data != self._original and not messagebox.askyesno(
                "Particle editor", "Discard unsaved particle edits?", parent=self):
            return
        if self._preview is not None:
            self._preview.cleanup()
        self.destroy()
