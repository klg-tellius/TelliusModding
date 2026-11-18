"""Battle Cameras page: each game's battle-camera data on one :class:`BattleBrowser`.

* Path of Radiance (:class:`PorCameraAdapter`): the camera scripts (``xcam/*.dbx``), edited as a
  keyframe table with a fight preview, and the camera rigs (``zdbx/camera.dbx``) field by field; see
  ``formats/battle_camera.py``. Apply writes to ``zdbx.cmp`` at once; the first change keeps the
  vanilla archive for Restore original.
* Radiant Dawn (:class:`Fe10CameraAdapter`): the ``xcam/*.ga`` clips against ``FE10Battle.cms``'s
  clip registry, with a preview on the camera rig; clips are replaced or added from glTF, and the
  registry's group weights and dispatch are edited and saved together."""

from __future__ import annotations

import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, simpledialog, ttk

from .. import battle_tables
from ..exceptions import ProjectError
from ..formats import animation, dbx, fe10_battle, gltf_import
from ..formats import battle_camera as bc
from ..game_profile import files_root_of
from ..project import ModProject
from .battle_browser import BattleBrowser, BrowserAdapter, Group, Item
from .changelog import ChangeLog
from .editor_panel import EditorPanel
from .widgets import tip

RIG_ENTRY = "zdbx/camera.dbx"
NO_SCENERY = "(no scenery)"
FRAME_COLUMNS = (
    ("n", "#", 36), ("pos", "Position x, y, z", 150), ("rot", "Rotation x, y, z", 150),
    ("dist", "Distance", 70), ("time", "Time", 60),
)
RIG_FIELDS = (
    ("Position", "pos"), ("Rotation", "rot"), ("Distance", "dist"), ("Look-at offset", "offs"),
    ("Destination", "dest"), ("Speed", "speed"), ("Attract (0/1)", "attract"), ("Eye center (0/1)", "eyeCenter"),
    ("Enabled (0/1)", "enable"), ("Entity class", "entityClass"), ("Follows 1st", "entityName"),
    ("Follows 2nd", "entityName1"), ("Follows 3rd", "entityName2"),
)


class PorCameraAdapter(BrowserAdapter):
    display_name = "Battle cameras"
    source = "zdbx.cmp"
    note = ("Camera scripts (xcam) and camera rigs (camera.dbx). Apply writes the change at once; the first change "
            "keeps the original for Restore original.")
    label_title = "Script / rig"
    columns = (("info", "Details", 170), ("state", "State", 60))

    def __init__(self, project: ModProject, changelog: ChangeLog):
        super().__init__(project, changelog)
        self._scripts: dict[str, bc.CameraScript] = {}
        self._frames: list[bc.Keyframe] = []
        self._rigs: dict[str, bc.CameraRig] = {}
        self._edited: set[str] = set()
        self._player = None  # the BattlePlayer, made on the first preview

    # -- list -------------------------------------------------------------------------
    def load(self) -> list[Group]:
        texts = battle_tables.read_entries(self.project, "xcam")
        rig_text = battle_tables.read_entry(self.project, RIG_ENTRY)
        self._edited = battle_tables.modified_entries(self.project, "xcam") | (
            {RIG_ENTRY} if battle_tables.is_modified(self.project, RIG_ENTRY) else set())
        self._scripts = {}
        for path, text in texts.items():
            try:
                self._scripts[path[5:-4]] = bc.read_script(text)
            except dbx.DbxError:
                continue
        self._rigs = {r.name: r for r in bc.read_rigs(rig_text)}
        self._camera_box.config(values=sorted(self._rigs))
        scripts = Group("scripts", "Camera scripts (xcam)", info=str(len(self._scripts)))
        for name, s in sorted(self._scripts.items()):
            scripts.items.append(Item("script:" + name, (f"{s.camera}, {len(s.keyframes)} keys",
                                                         "edited" if f"xcam/{name}.dbx" in self._edited else ""),
                                      label=name))
        rigs = Group("rigs", "Camera rigs (camera.dbx)", info=str(len(self._rigs)))
        for name, rig in self._rigs.items():
            rigs.items.append(Item("rig:" + name, (f"follows {rig.entity_class or '-'}",
                                                   "edited" if RIG_ENTRY in self._edited else ""), label=name))
        return [scripts, rigs]

    def summary(self) -> str:
        return f"{len(self._scripts)} camera scripts, {len(self._rigs)} camera rigs."

    def _script_name(self) -> str | None:
        key = self.selected()
        return key[7:] if key and key.startswith("script:") else None

    def _rig_name(self) -> str | None:
        key = self.selected()
        return key[4:] if key and key.startswith("rig:") else None

    def actions(self):
        return (("Add script...", self._add_script), ("Restore original", self._restore))

    # -- editor -----------------------------------------------------------------------
    def build_detail(self, parent: ttk.Frame) -> None:
        self._parent = parent
        self._empty = ttk.Label(parent, text="Select a camera script or rig.", style="Muted.TLabel")
        self._script_frame = ttk.Frame(parent)
        self._rig_frame = ttk.Frame(parent)
        self._build_script(self._script_frame)
        self._build_rig(self._rig_frame)
        self._empty.pack(anchor="w")

    def _build_script(self, right: ttk.Frame) -> None:
        self._script_title = ttk.Label(right, text="(no script selected)", font=("Segoe UI", 12, "bold"))
        self._script_title.pack(anchor="w")
        head = ttk.Frame(right)
        head.pack(anchor="w", fill="x", pady=6)
        head.columnconfigure(1, weight=1)
        self._caption = tk.StringVar()
        self._camera = tk.StringVar()
        ttk.Label(head, text="Caption").grid(row=0, column=0, sticky="w")
        ttk.Entry(head, textvariable=self._caption).grid(row=0, column=1, sticky="ew", padx=(8, 0), pady=2)
        ttk.Label(head, text="Camera rig").grid(row=1, column=0, sticky="w")
        self._camera_box = ttk.Combobox(head, textvariable=self._camera, width=20)
        self._camera_box.grid(row=1, column=1, sticky="w", padx=(8, 0), pady=2)

        self._frame_tree = ttk.Treeview(right, columns=[c[0] for c in FRAME_COLUMNS], show="headings",
                                        selectmode="browse", height=5)
        for key, title, width in FRAME_COLUMNS:
            self._frame_tree.heading(key, text=title)
            self._frame_tree.column(key, width=width, anchor="w")
        self._frame_tree.pack(fill="x")
        self._frame_tree.bind("<<TreeviewSelect>>", lambda _e: self._load_frame_fields())

        edit = ttk.Frame(right)
        edit.pack(anchor="w", pady=6)
        self._frame_vars = {k: tk.StringVar() for k in ("pos", "rot", "dist", "time")}
        for col, (key, label, width) in enumerate((("pos", "Position", 18), ("rot", "Rotation", 18),
                                                   ("dist", "Distance", 8), ("time", "Time", 6))):
            ttk.Label(edit, text=label).grid(row=0, column=col, sticky="w", padx=(0, 6))
            ttk.Entry(edit, textvariable=self._frame_vars[key], width=width).grid(row=1, column=col, padx=(0, 6))

        buttons = ttk.Frame(right)
        buttons.pack(anchor="w")
        for text, command in (("Update keyframe", self._update_frame), ("Add keyframe", self._add_frame),
                              ("Delete keyframe", self._delete_frame), ("Move up", lambda: self._move_frame(-1)),
                              ("Move down", lambda: self._move_frame(1))):
            ttk.Button(buttons, text=text, command=command).pack(side="left", padx=(0, 6))
        ttk.Label(right, text="Time is the keyframe's duration in engine units; 0 cuts straight to it.",
                  style="Muted.TLabel").pack(anchor="w", pady=(6, 0))
        ttk.Button(right, text="Apply script", command=self._apply_script).pack(anchor="w", pady=8)

        preview = ttk.Frame(right)
        preview.pack(fill="x", pady=(4, 0))
        tip(ttk.Button(preview, text="Preview", style="Accent.TButton", command=self._preview),
            "Plays a short fight (Ike with an Iron Sword against a Fighter with an Iron Axe) with this script, "
            "as edited here, driving the camera from the first frame.").pack(side="left")
        ttk.Label(preview, text="Scenery").pack(side="left", padx=(12, 4))
        self._scenery = tk.StringVar(value=NO_SCENERY)
        self._scenery_box = ttk.Combobox(preview, textvariable=self._scenery, state="readonly", width=24,
                                         values=[NO_SCENERY])
        self._scenery_box.pack(side="left")
        self._scenery_box.bind("<<ComboboxSelected>>", lambda _e: self._preview())
        self._player_parent = right

    def _build_rig(self, right: ttk.Frame) -> None:
        self._rig_title = ttk.Label(right, text="(no rig selected)", font=("Segoe UI", 12, "bold"))
        self._rig_title.pack(anchor="w", pady=(0, 6))
        form = ttk.Frame(right)
        form.pack(anchor="w", fill="x")
        form.columnconfigure(1, weight=1)
        self._rig_vars = {key: tk.StringVar() for _l, key in RIG_FIELDS}
        for row, (label, key) in enumerate(RIG_FIELDS):
            ttk.Label(form, text=label).grid(row=row, column=0, sticky="w", pady=2)
            ttk.Entry(form, textvariable=self._rig_vars[key], width=28).grid(row=row, column=1, sticky="ew",
                                                                           padx=(8, 0), pady=2)
        ttk.Label(right, text="An empty box means the rig has no such line. Angles are degrees.",
                  style="Muted.TLabel").pack(anchor="w", pady=(6, 0))
        ttk.Button(right, text="Apply rig", command=self._apply_rig).pack(anchor="w", pady=8)

    def show(self, key: str | None) -> None:
        for frame in (self._empty, self._script_frame, self._rig_frame):
            frame.pack_forget()
        if key and key.startswith("script:"):
            script = self._scripts[key[7:]]
            self._script_title.config(text=key[7:])
            self._caption.set(script.caption)
            self._camera.set(script.camera)
            self._frames = list(script.keyframes)
            self._fill_frames()
            self._script_frame.pack(fill="both", expand=True)
        elif key and key.startswith("rig:"):
            rig = self._rigs[key[4:]]
            self._rig_title.config(text=key[4:])
            for _label, field_key in RIG_FIELDS:
                self._rig_vars[field_key].set(rig.get(field_key))
            self._rig_frame.pack(fill="both", expand=True)
        else:
            self._empty.pack(anchor="w")

    def _preview(self) -> None:
        """Play the preview fight with the selected script as edited (not yet applied)."""
        name = self._script_name()
        if name is None:
            self.status("Select a camera script to preview.")
            return
        from .. import battle_sim
        from ..formats import fe8data
        from .battle_window import BattlePlayer, preview_log

        script = bc.CameraScript(name, self._caption.get(), self._camera.get().strip(), tuple(self._frames))
        try:
            fe8 = fe8data.read_fe8data(self.project.read_logical("game_data"))
        except Exception as exc:  # noqa: BLE001 - no game data: nothing to stage
            self.error(self.display_name, exc)
            return
        rules = battle_sim.Fe9Rules()
        if self._player is None:
            self._player = BattlePlayer(self._player_parent, files_root_of(self.project), rules, fe8)
            self._player.pack(fill="both", expand=True, pady=(6, 0))
            self._scenery_box.configure(values=[NO_SCENERY] + sorted(self._player.sceneries(), key=str.casefold))
            if self._scenery.get() == NO_SCENERY and "map03_ground01" in self._player.sceneries():
                self._scenery.set("map03_ground01")
        scenery = self._scenery.get()
        self._player.play(preview_log(fe8, rules), 1, None if scenery == NO_SCENERY else scenery,
                          camera_script=script)

    def cleanup(self) -> None:
        if self._player is not None:
            self._player.cleanup()

    # -- keyframes ------------------------------------------------------------------------
    def _fill_frames(self, select: int | None = None) -> None:
        self._frame_tree.delete(*self._frame_tree.get_children())
        for i, f in enumerate(self._frames):
            self._frame_tree.insert("", "end", iid=str(i), values=(
                i + 1, bc.format_vec(f.pos), bc.format_vec(f.rot), f"{f.dist:g}", f.time))
        if select is not None and 0 <= select < len(self._frames):
            self._frame_tree.selection_set(str(select))

    def _selected_frame(self) -> int | None:
        selection = self._frame_tree.selection()
        return int(selection[0]) if selection else None

    def _load_frame_fields(self) -> None:
        i = self._selected_frame()
        if i is None:
            return
        f = self._frames[i]
        self._frame_vars["pos"].set(bc.format_vec(f.pos))
        self._frame_vars["rot"].set(bc.format_vec(f.rot))
        self._frame_vars["dist"].set(f"{f.dist:g}")
        self._frame_vars["time"].set(str(f.time))

    def _frame_from_fields(self) -> bc.Keyframe:
        pos, rot = bc.parse_vec(self._frame_vars["pos"].get()), bc.parse_vec(self._frame_vars["rot"].get())
        if pos is None or rot is None:
            raise bc.CameraError("Position and rotation need three numbers, like 0, 7, 0.")
        try:
            return bc.Keyframe(pos, rot, float(self._frame_vars["dist"].get()), int(self._frame_vars["time"].get()))
        except ValueError as exc:
            raise bc.CameraError("Distance must be a number and time a whole number.") from exc

    def _update_frame(self) -> None:
        i = self._selected_frame()
        if i is None:
            return
        try:
            self._frames[i] = self._frame_from_fields()
        except bc.CameraError as exc:
            self.error(self.display_name, exc)
            return
        self._fill_frames(i)

    def _add_frame(self) -> None:
        try:
            frame = self._frame_from_fields()
        except bc.CameraError as exc:
            self.error(self.display_name, exc)
            return
        self._frames.append(frame)
        self._fill_frames(len(self._frames) - 1)

    def _delete_frame(self) -> None:
        i = self._selected_frame()
        if i is None:
            return
        if len(self._frames) == 1:
            messagebox.showinfo(self.display_name, "A script needs at least one keyframe.", parent=self.page)
            return
        del self._frames[i]
        self._fill_frames(min(i, len(self._frames) - 1))

    def _move_frame(self, step: int) -> None:
        i = self._selected_frame()
        if i is None or not 0 <= i + step < len(self._frames):
            return
        self._frames[i], self._frames[i + step] = self._frames[i + step], self._frames[i]
        self._fill_frames(i + step)

    # -- writing ------------------------------------------------------------------------
    def _changed(self, message: str) -> None:
        self.changelog.append("Battle cameras", message)
        self.reload()
        self.status(message + ".")

    def _apply_script(self) -> None:
        name = self._script_name()
        if name is None:
            return
        path = f"xcam/{name}.dbx"
        try:
            text = battle_tables.read_entry(self.project, path)
            new = bc.set_script_keyframes(text, self._frames)
            new = bc.set_script_field(new, "caption", self._caption.get())
            new = bc.set_script_field(new, "camera", self._camera.get())
            if new == text:
                self.status("No change.")
                return
            battle_tables.write_entry(self.project, path, new)
        except (dbx.DbxError, ProjectError) as exc:
            self.error(self.display_name, exc)
            return
        self._changed(f"Edited camera script {name}")

    def _restore(self) -> None:
        name, rig = self._script_name(), self._rig_name()
        path = f"xcam/{name}.dbx" if name else RIG_ENTRY if rig else None
        if path is None:
            self.status("Select a camera script or rig to restore.")
            return
        if not battle_tables.is_modified(self.project, path):
            self.status("Already the original.")
            return
        battle_tables.restore_entry(self.project, path)
        self._changed(f"Restored camera script {name}" if name else "Restored camera.dbx")

    def _add_script(self) -> None:
        name = simpledialog.askstring("Add script", "New script name (e.g. atk_custom_l):", parent=self.page)
        if not name:
            return
        name = name.strip()
        camera = self._camera.get() or "camCharaL0"
        try:
            if name in self._scripts:
                raise bc.CameraError(f"{name} already exists.")
            battle_tables.write_entry(self.project, f"xcam/{name}.dbx", bc.new_script(name, camera, name),
                                      create=True)
        except (dbx.DbxError, ProjectError) as exc:
            self.error(self.display_name, exc)
            return
        self.changelog.append("Battle cameras", f"Added camera script {name}")
        self.reload("script:" + name)
        self.status(f"Added camera script {name}.")

    def _apply_rig(self) -> None:
        name = self._rig_name()
        if name is None:
            return
        try:
            text = battle_tables.read_entry(self.project, RIG_ENTRY)
            new, rig = text, self._rigs[name]
            for _label, key in RIG_FIELDS:
                value = self._rig_vars[key].get().strip()
                if value == rig.get(key):
                    continue  # untouched (also keeps vanilla's malformed rot on cam1)
                if not value and key not in ("entityName1", "entityName2"):
                    raise bc.CameraError(f"{key} cannot be emptied; remove the line in the file instead.")
                new = bc.set_rig_field(new, name, key, value)
            if new == text:
                self.status("No change.")
                return
            battle_tables.write_entry(self.project, RIG_ENTRY, new)
        except (dbx.DbxError, ProjectError) as exc:
            self.error(self.display_name, exc)
            return
        self._changed(f"Edited camera rig {name}")


class Fe10CameraAdapter(BrowserAdapter):
    display_name = "Battle cameras"
    source = "FE10Battle.cms"
    note = ("Camera clips (xcam/*.ga) and their registry. Clips are replaced or added from glTF at once; group "
            "weights and dispatch are saved with Save.")
    label_title = "Clip"
    columns = (("frames", "Frames", 55), ("curves", "Curves", 50), ("state", "Registry", 75))
    keeps_changes = True

    def __init__(self, project: ModProject, changelog: ChangeLog):
        super().__init__(project, changelog)
        self._data: bytes | None = None
        self._battle: fe10_battle.Fe10Battle | None = None
        self._dirty = False
        self._clips: dict[str, tuple[Path | None, str, int, int, int | None, tuple[str, ...]]] = {}
        self._summary = ""

    # -- list -------------------------------------------------------------------------
    def load(self) -> list[Group]:
        if self._data is None or not self._dirty:
            self._data = self.project.read_logical("battle_data")
        battle = self._battle = fe10_battle.read_fe10_battle(self._data)
        xcam = files_root_of(self.project) / "xcam"
        registered = {}
        for index, record in enumerate(battle.table("FE10BCamFile").records):
            strings = dict(record.strings)
            registered[strings.get(4, f"row_{index}")] = (strings.get(0, ""), record.words[2], index)
        group_rows = battle.table("FE10BCamGroup").records
        contexts_by_group: dict[int, set[str]] = {}
        for camera_list in battle.camera_lists:
            for context_index, motion_groups in enumerate(camera_list.group_indices):
                for group_index in motion_groups:
                    if group_index is not None:
                        contexts_by_group.setdefault(group_index, set()).add(
                            battle.camera_context_names[context_index])
        memberships: dict[int, list[str]] = {}
        for group in battle.camera_groups:
            group_name = dict(group_rows[group.record_index].strings).get(4, f"group_{group.record_index}")
            contexts = ", ".join(sorted(contexts_by_group.get(group.record_index, ()))) or "unreferenced"
            for choice in group.choices:
                memberships.setdefault(choice.file_index, []).append(
                    f"{group_name} ({choice.selection_weight}%; weapon types: {contexts})")
        files = {path.stem: path for path in xcam.glob("*.ga")}
        self._clips.clear()
        clips = Group("clips", "Camera clips")
        for name in sorted(files.keys() | registered.keys(), key=str.casefold):
            path = files.get(name)
            description, _flags, row = registered.get(name, ("", 0, None))
            frames = curves = 0
            if path is not None:
                parsed = animation.read_animation_bytes(path.read_bytes())
                frames, curves = parsed.length_in_frames, len(parsed.curves)
            self._clips[name] = (path, description, frames, curves, row,
                                 tuple(memberships.get(row, ())) if row is not None else ())
            state = "no file" if path is None else "registered" if row is not None else "loose"
            clips.items.append(Item(name, (frames or "", curves or "", state), label=name))
        matched = sum(p is not None and r is not None for p, _d, _f, _c, r, _g in self._clips.values())
        self._summary = (f"{len(files)} .ga clips; {len(registered)} registry rows; {matched} matched, "
                         f"{len(files) - matched} loose clips; dispatch uses "
                         f"{len(battle.camera_context_names)} weapon types."
                         + (" Unsaved registry changes." if self._dirty else ""))
        return [clips]

    def summary(self) -> str:
        return self._summary

    def actions(self):
        return (("Replace clip…", self._replace_clip), ("New clip…", self._new_clip),
                ("Edit group weight…", self._edit_group_weight), ("Edit dispatch…", self._edit_dispatch))

    # -- editor -----------------------------------------------------------------------
    def build_detail(self, parent: ttk.Frame) -> None:
        from .model_viewer import _ModelPreview

        self._title = ttk.Label(parent, text="Select a camera clip", font=("Segoe UI", 12, "bold"))
        self._title.pack(anchor="w")
        self._detail = ttk.Label(parent, style="Muted.TLabel", justify="left", wraplength=620)
        self._detail.pack(anchor="w", pady=(3, 6))
        self._preview = _ModelPreview(parent)
        self._preview.pack(fill="both", expand=True)

    def cleanup(self) -> None:
        self._preview.cleanup()

    def show(self, key: str | None) -> None:
        from .model_viewer import _build_loaded_set

        if key is None or key not in self._clips:
            self._title.configure(text="Select a camera clip")
            self._detail.configure(text="")
            self._preview.show(None, "")
            return
        path, description, frames, curves, row, groups = self._clips[key]
        self._title.configure(text=key)
        registry = f"FE10BCamFile row {row}" if row is not None else "not in FE10BCamFile"
        group_text = ", ".join(groups) if groups else "not selected by a camera group"
        self._detail.configure(text=(f"{description or '(no description)'}\n{registry}; "
                                     f"{frames} frames, {curves} curves\nGroups: {group_text}"))
        if path is None:
            self._preview.show(None, "The registered test clip has no xcam .ga file.")
            return
        xcam = files_root_of(self.project) / "xcam"
        try:
            loaded = _build_loaded_set(
                f"xcam/{key}",
                {"cam.g": (xcam / "cam.g").read_bytes(), "cam.gs": (xcam / "cam.gs").read_bytes()},
                [(path.name, path.read_bytes())],
            )
            self._preview.show(loaded)
            self._preview.select_animation(path.name)
        except Exception as exc:  # noqa: BLE001
            self._preview.show(None, f"Could not preview this clip: {exc}")

    # -- registry edits ---------------------------------------------------------------------
    @staticmethod
    def _row_label(table: fe10_battle.BattleTable, index: int) -> str:
        strings = dict(table.records[index].strings)
        return strings.get(4) or strings.get(0) or f"row {index}"

    def _edit_group_weight(self) -> None:
        battle = self._battle
        if battle is None:
            return
        group_table = battle.table("FE10BCamGroup")
        group_index = simpledialog.askinteger(
            "Camera group", f"Camera-group row (0–{len(battle.camera_groups) - 1}).\n\n"
            "First groups: " + ", ".join(f"{index}={self._row_label(group_table, index)}"
                                          for index in range(min(24, len(battle.camera_groups)))),
            parent=self.page, minvalue=0, maxvalue=len(battle.camera_groups) - 1)
        if group_index is None:
            return
        group = battle.camera_groups[group_index]
        if not group.choices:
            messagebox.showinfo("Camera group", "This camera group has no choices.", parent=self.page)
            return
        file_table = battle.table("FE10BCamFile")
        choice_index = simpledialog.askinteger(
            "Camera choice", f"Choice within {self._row_label(group_table, group_index)} "
            f"(0–{len(group.choices) - 1}).\n\n" + ", ".join(
                f"{index}={self._row_label(file_table, choice.file_index)} ({choice.selection_weight}%)"
                for index, choice in enumerate(group.choices)),
            parent=self.page, minvalue=0, maxvalue=len(group.choices) - 1)
        if choice_index is None:
            return
        choice = group.choices[choice_index]
        weight = simpledialog.askinteger(
            "Selection weight", "Relative selection weight (0–100).\n"
            "The engine chooses among the group using these percentages; update the other choices "
            "as needed to keep the group total at 100.\n\n"
            f"Current: {choice.selection_weight}", parent=self.page, minvalue=0, maxvalue=100,
            initialvalue=choice.selection_weight)
        if weight is None or weight == choice.selection_weight:
            return
        self._mark_changed(fe10_battle.set_camera_choice_weight(self._data, group_index, choice_index, weight),
                           f"camera group {group_index} choice {choice_index}: "
                           f"weight {choice.selection_weight} -> {weight}")

    def _edit_dispatch(self) -> None:
        battle = self._battle
        if battle is None:
            return
        list_table = battle.table("FE10BCamList")
        list_index = simpledialog.askinteger(
            "Camera list", f"Camera-list row (0–{len(battle.camera_lists) - 1}).\n\n"
            "First lists: " + ", ".join(f"{index}={self._row_label(list_table, index)}"
                                         for index in range(min(24, len(battle.camera_lists)))),
            parent=self.page, minvalue=0, maxvalue=len(battle.camera_lists) - 1)
        if list_index is None:
            return
        context_index = simpledialog.askinteger(
            "Weapon context", "Weapon/context row:\n" + ", ".join(
                f"{index}={name}" for index, name in enumerate(battle.camera_context_names)),
            parent=self.page, minvalue=0, maxvalue=len(battle.camera_context_names) - 1)
        if context_index is None:
            return
        motion_table = battle.table("FE10BMotion")
        motion_count = len(motion_table.records)
        motion_index = simpledialog.askinteger(
            "Battle motion", f"Motion row (0–{motion_count - 1}).\n\n"
            "Motions: " + ", ".join(f"{index}={self._row_label(motion_table, index)}" for index in range(motion_count)),
            parent=self.page, minvalue=0, maxvalue=motion_count - 1)
        if motion_index is None:
            return
        current = battle.camera_lists[list_index].group_indices[context_index][motion_index]
        group_index = simpledialog.askinteger(
            "Camera group", f"Camera-group row, or -1 for no dispatch. Current: "
            f"{'-1' if current is None else current}.\n\nValid rows: 0–{len(battle.camera_groups) - 1}.",
            parent=self.page, minvalue=-1, maxvalue=len(battle.camera_groups) - 1,
            initialvalue=-1 if current is None else current)
        if group_index is None:
            return
        replacement = None if group_index < 0 else group_index
        if replacement == current:
            return
        self._mark_changed(
            fe10_battle.set_camera_dispatch_group(self._data, list_index, context_index, motion_index, replacement),
            f"camera list {list_index}, {battle.camera_context_names[context_index]}, "
            f"motion {motion_index}: group {current} -> {replacement}")

    def _mark_changed(self, data: bytes, description: str) -> None:
        self._data = data
        self._dirty = True
        self.changelog.append("FE10Battle.cms", description)
        self.reload()
        self.status("Camera registry changed (unsaved).")

    # -- clips ----------------------------------------------------------------------------
    def _import_clip(self, template: bytes) -> tuple[bytes, str] | None:
        source = filedialog.askopenfilename(parent=self.page, title="Import battle-camera animation",
                                            filetypes=[("glTF", "*.glb *.gltf"), ("All files", "*.*")])
        if not source:
            return None
        source_path = Path(source)
        try:
            source_data = source_path.read_bytes()
            names = gltf_import.list_animations(source_data, source_path.parent)
            if not names:
                raise ValueError("The glTF file has no animations.")
            selected = names[0]
            if len(names) > 1:
                selected = simpledialog.askstring("Camera animation", "Animation name:\n" + ", ".join(names),
                                                  initialvalue=selected, parent=self.page)
                if selected is None:
                    return None
                if selected not in names:
                    raise ValueError(f"The glTF has no animation named {selected}.")
            skeleton_data = (files_root_of(self.project) / "xcam" / "cam.g").read_bytes()
            ga, _warnings = gltf_import.import_animation(source_data, skeleton_data, animation_name=selected,
                                                         template=template, base_dir=source_path.parent)
            animation.read_animation_bytes(ga)
            return ga, source_path.name
        except (OSError, ValueError, animation.AnimationError, gltf_import.GltfImportError) as exc:
            self.error("Could not import camera", exc)
            return None

    def _replace_clip(self) -> None:
        name = self.selected()
        if name is None:
            messagebox.showinfo("Replace camera", "Select the camera clip to replace.", parent=self.page)
            return
        path = self._clips[name][0]
        if path is None:
            messagebox.showinfo("Replace camera", "This registry row has no template clip.", parent=self.page)
            return
        imported = self._import_clip(path.read_bytes())
        if imported is None:
            return
        ga, source_name = imported
        try:
            self.project.write_keeping_original(path, ga)
        except OSError as exc:
            self.error("Could not save camera", exc)
            return
        self.changelog.append("Battle cameras", f"Replaced {name} from {source_name}")
        self.reload(name)

    def _new_clip(self) -> None:
        donor_name = self.selected()
        if self._battle is None or donor_name is None:
            messagebox.showinfo("New camera", "Select the camera clip to use as a template.", parent=self.page)
            return
        donor_path, _description, _frames, _curves, donor_row, _groups = self._clips[donor_name]
        if donor_path is None or donor_row is None:
            messagebox.showinfo("New camera", "Choose a registered clip with a file as the template.",
                                parent=self.page)
            return
        if self._dirty and not messagebox.askyesno(
                "New camera", "Adding a clip saves FE10Battle.cms, with the unsaved registry changes. Continue?",
                parent=self.page):
            return
        name = simpledialog.askstring("New camera", "New clip name (letters, digits and underscore):",
                                      parent=self.page)
        if name is None:
            return
        name = name.strip()
        if not name or not name.replace("_", "a").isalnum() or name in self._clips:
            messagebox.showerror("New camera", "Use a unique name containing letters, digits and underscore.",
                                 parent=self.page)
            return
        description = simpledialog.askstring("New camera", "Description:", initialvalue=f"Copy of {donor_name}",
                                             parent=self.page)
        if description is None:
            return
        imported = self._import_clip(donor_path.read_bytes())
        if imported is None:
            return
        ga, source_name = imported
        try:
            rebuilt, _row = fe10_battle.clone_camera_file(self._data, donor_row, name, description)
            animation.read_animation_bytes(ga)
            path = files_root_of(self.project) / "xcam" / f"{name}.ga"
            self.project.write_keeping_original(path, ga)
            self.project.write_logical("battle_data", rebuilt)
        except (OSError, ValueError, IndexError) as exc:
            self.error("Could not create camera", exc)
            return
        self._data = rebuilt
        self._dirty = False
        self.changelog.append("Battle cameras", f"Created {name} from {source_name}")
        self.reload(name)

    # -- saving -------------------------------------------------------------------------
    @property
    def dirty(self) -> bool:
        return self._dirty

    def save(self) -> bool:
        if not self._dirty:
            return True
        try:
            self.project.write_logical("battle_data", self._data)
        except OSError as exc:
            self.error("Could not save FE10Battle.cms", exc)
            return False
        self._dirty = False
        self.changelog.append("FE10Battle.cms", "Saved camera-registry changes")
        self.status("Saved FE10Battle.cms camera registry.")
        return True

    def discard(self) -> None:
        self._dirty = False
        self._data = None


def battle_camera_viewer(parent: tk.Misc, project: ModProject, changelog: ChangeLog) -> EditorPanel:
    """The Battle cameras page with the project's battle-data format (``GameProfile.battle_dialect``)."""
    adapter = Fe10CameraAdapter if project.profile.battle_dialect == "fe10" else PorCameraAdapter
    return BattleBrowser(parent, adapter(project, changelog))
