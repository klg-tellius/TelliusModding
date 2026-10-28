"""Radiant Dawn battle-camera clip browser, registry editor, and native-rig preview."""

from __future__ import annotations

import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, simpledialog, ttk

from ..formats import animation, fe10_battle, gltf_import
from ..games import Game
from ..project import ModProject
from .battle_camera_viewer import BattleCameraViewer
from .changelog import ChangeLog
from .editor_panel import EditorPanel
from .model_viewer import _ModelPreview, _build_loaded_set


class Fe10CameraViewer(EditorPanel):
    display_name = "Battle cameras"

    def __init__(self, parent: tk.Misc, project: ModProject, changelog: ChangeLog):
        super().__init__(parent)
        self._project = project
        self._changelog = changelog
        self._data = b""
        self._battle: fe10_battle.Fe10Battle | None = None
        self._dirty = False
        self._clips: dict[str, tuple[Path | None, str, int, int, int | None, tuple[str, ...]]] = {}

        top = ttk.Frame(self, padding=8)
        top.pack(fill="x")
        ttk.Label(top, text="Search").pack(side="left")
        self._query = tk.StringVar()
        ttk.Entry(top, textvariable=self._query).pack(side="left", fill="x", expand=True, padx=(6, 12))
        self._query.trace_add("write", lambda *_: self._fill())
        self._save_button = ttk.Button(top, text="Save", command=self.save, state="disabled")
        self._save_button.pack(side="right")
        ttk.Button(top, text="Discard changes", command=self._revert).pack(side="right", padx=(0, 6))
        ttk.Button(top, text="Edit dispatch…", command=self._edit_dispatch).pack(side="right", padx=(0, 6))
        ttk.Button(top, text="Edit group weight…", command=self._edit_group_weight).pack(
            side="right", padx=(0, 6))
        ttk.Button(top, text="New clip…", command=self._new_clip).pack(side="right", padx=(0, 6))
        ttk.Button(top, text="Replace clip…", command=self._replace_clip).pack(side="right", padx=(0, 6))
        ttk.Label(top, text="Clip imports and registry choices are editable.",
                  style="Muted.TLabel").pack(side="right", padx=(0, 12))

        body = ttk.PanedWindow(self, orient="horizontal")
        body.pack(fill="both", expand=True, padx=8, pady=(0, 8))
        left, right = ttk.Frame(body), ttk.Frame(body, padding=(12, 0, 0, 0))
        body.add(left, weight=2)
        body.add(right, weight=5)
        self._tree = ttk.Treeview(left, columns=("name", "frames", "curves", "state"),
                                  show="headings", selectmode="browse")
        for key, title, width in (("name", "Clip", 170), ("frames", "Frames", 55),
                                  ("curves", "Curves", 50), ("state", "Registry", 75)):
            self._tree.heading(key, text=title)
            self._tree.column(key, width=width, stretch=key == "name")
        scroll = ttk.Scrollbar(left, command=self._tree.yview)
        self._tree.configure(yscrollcommand=scroll.set)
        scroll.pack(side="right", fill="y")
        self._tree.pack(side="left", fill="both", expand=True)
        self._tree.bind("<<TreeviewSelect>>", lambda _e: self._show())

        self._title = ttk.Label(right, text="Select a camera clip", font=("Segoe UI", 12, "bold"))
        self._title.pack(anchor="w")
        self._detail = ttk.Label(right, style="Muted.TLabel", justify="left", wraplength=620)
        self._detail.pack(anchor="w", pady=(3, 6))
        self._preview = _ModelPreview(right)
        self._preview.pack(fill="both", expand=True)
        self._status = ttk.Label(self, style="Muted.TLabel", padding=8)
        self._status.pack(anchor="w")
        self._load()

    def cleanup(self) -> None:
        self._preview.cleanup()

    def _load(self, data: bytes | None = None) -> None:
        xcam = self._project.files_dir / "xcam"
        try:
            if data is None:
                data = self._project.read_logical("battle_data")
            battle = fe10_battle.read_fe10_battle(data)
        except Exception as exc:  # noqa: BLE001
            self._status.configure(text=f"Could not read FE10Battle.cms: {exc}")
            return
        self._data = data
        self._battle = battle
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
        for name in sorted(files.keys() | registered.keys(), key=str.casefold):
            path = files.get(name)
            description, flags, row = registered.get(name, ("", 0, None))
            frames = curves = 0
            if path is not None:
                parsed = animation.read_animation_bytes(path.read_bytes())
                frames, curves = parsed.length_in_frames, len(parsed.curves)
            self._clips[name] = (path, description, frames, curves, row,
                                 tuple(memberships.get(row, ())) if row is not None else ())
        self._fill()
        registered_with_file = sum(path is not None and row is not None
                                   for path, _description, _frames, _curves, row, _groups
                                   in self._clips.values())
        self._status.configure(
            text=(f"{len(files)} .ga clips; {len(registered)} registry rows; "
                  f"{registered_with_file} matched, {len(files) - registered_with_file} loose clips; "
                  f"dispatch uses {len(battle.camera_context_names)} weapon types.")
        )

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
            "First groups: " + ", ".join(
                f"{index}={self._row_label(group_table, index)}"
                for index in range(min(24, len(battle.camera_groups)))),
            parent=self, minvalue=0, maxvalue=len(battle.camera_groups) - 1)
        if group_index is None:
            return
        group = battle.camera_groups[group_index]
        if not group.choices:
            messagebox.showinfo("Camera group", "This camera group has no choices.", parent=self)
            return
        file_table = battle.table("FE10BCamFile")
        choice_index = simpledialog.askinteger(
            "Camera choice", f"Choice within {self._row_label(group_table, group_index)} "
            f"(0–{len(group.choices) - 1}).\n\n" + ", ".join(
                f"{index}={self._row_label(file_table, choice.file_index)} "
                f"({choice.selection_weight}%)"
                for index, choice in enumerate(group.choices)),
            parent=self, minvalue=0, maxvalue=len(group.choices) - 1)
        if choice_index is None:
            return
        choice = group.choices[choice_index]
        weight = simpledialog.askinteger(
            "Selection weight", "Relative selection weight (0–100).\n"
            "The engine chooses among the group using these percentages; update the other choices "
            "as needed to keep the group total at 100.\n\n"
            f"Current: {choice.selection_weight}", parent=self, minvalue=0, maxvalue=100,
            initialvalue=choice.selection_weight)
        if weight is None or weight == choice.selection_weight:
            return
        self._data = fe10_battle.set_camera_choice_weight(
            self._data, group_index, choice_index, weight)
        self._mark_changed(
            f"camera group {group_index} choice {choice_index}: "
            f"weight {choice.selection_weight} -> {weight}")

    def _edit_dispatch(self) -> None:
        battle = self._battle
        if battle is None:
            return
        list_table = battle.table("FE10BCamList")
        list_index = simpledialog.askinteger(
            "Camera list", f"Camera-list row (0–{len(battle.camera_lists) - 1}).\n\n"
            "First lists: " + ", ".join(
                f"{index}={self._row_label(list_table, index)}"
                for index in range(min(24, len(battle.camera_lists)))),
            parent=self, minvalue=0, maxvalue=len(battle.camera_lists) - 1)
        if list_index is None:
            return
        context_index = simpledialog.askinteger(
            "Weapon context", "Weapon/context row:\n" + ", ".join(
                f"{index}={name}" for index, name in enumerate(battle.camera_context_names)),
            parent=self, minvalue=0, maxvalue=len(battle.camera_context_names) - 1)
        if context_index is None:
            return
        motion_table = battle.table("FE10BMotion")
        motion_count = len(motion_table.records)
        motion_index = simpledialog.askinteger(
            "Battle motion", f"Motion row (0–{motion_count - 1}).\n\n"
            "Motions: " + ", ".join(
                f"{index}={self._row_label(motion_table, index)}"
                for index in range(motion_count)),
            parent=self, minvalue=0, maxvalue=motion_count - 1)
        if motion_index is None:
            return
        current = battle.camera_lists[list_index].group_indices[context_index][motion_index]
        group_index = simpledialog.askinteger(
            "Camera group", f"Camera-group row, or -1 for no dispatch. Current: "
            f"{'-1' if current is None else current}.\n\n"
            f"Valid rows: 0–{len(battle.camera_groups) - 1}.",
            parent=self, minvalue=-1, maxvalue=len(battle.camera_groups) - 1,
            initialvalue=-1 if current is None else current)
        if group_index is None:
            return
        replacement = None if group_index < 0 else group_index
        if replacement == current:
            return
        self._data = fe10_battle.set_camera_dispatch_group(
            self._data, list_index, context_index, motion_index, replacement)
        self._mark_changed(
            f"camera list {list_index}, {battle.camera_context_names[context_index]}, "
            f"motion {motion_index}: group {current} -> {replacement}")

    def _mark_changed(self, description: str) -> None:
        self._dirty = True
        self._save_button.configure(state="normal")
        self._changelog.append("FE10Battle.cms", description)
        self._load(self._data)
        self._status.configure(text="Camera registry changed (unsaved).")

    def _import_clip(self, template: bytes) -> tuple[bytes, str] | None:
        source = filedialog.askopenfilename(
            parent=self, title="Import battle-camera animation",
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
                selected = simpledialog.askstring(
                    "Camera animation", "Animation name:\n" + ", ".join(names),
                    initialvalue=selected, parent=self)
                if selected is None:
                    return None
                if selected not in names:
                    raise ValueError(f"The glTF has no animation named {selected}.")
            skeleton_data = (self._project.files_dir / "xcam" / "cam.g").read_bytes()
            ga, _warnings = gltf_import.import_animation(
                source_data, skeleton_data, animation_name=selected,
                template=template, base_dir=source_path.parent)
            animation.read_animation_bytes(ga)
            return ga, source_path.name
        except (OSError, ValueError, animation.AnimationError, gltf_import.GltfImportError) as exc:
            messagebox.showerror("Could not import camera", str(exc), parent=self)
            return None

    def _replace_clip(self) -> None:
        selection = self._tree.selection()
        if not selection:
            return
        name = selection[0]
        path = self._clips[name][0]
        if path is None:
            messagebox.showinfo("Replace camera", "This registry row has no template clip.", parent=self)
            return
        imported = self._import_clip(path.read_bytes())
        if imported is None:
            return
        ga, source_name = imported
        try:
            self._project.write_keeping_original(path, ga)
        except OSError as exc:
            messagebox.showerror("Could not save camera", str(exc), parent=self)
            return
        self._changelog.append("Battle cameras", f"Replaced {name} from {source_name}")
        self._load(self._data)
        self._tree.selection_set(name)
        self._show()

    def _new_clip(self) -> None:
        battle = self._battle
        selection = self._tree.selection()
        if battle is None or not selection:
            messagebox.showinfo("New camera", "Select the camera clip to use as a template.", parent=self)
            return
        donor_name = selection[0]
        donor_path, _description, _frames, _curves, donor_row, _groups = self._clips[donor_name]
        if donor_path is None or donor_row is None:
            messagebox.showinfo("New camera", "Choose a registered clip with a file as the template.", parent=self)
            return
        name = simpledialog.askstring(
            "New camera", "New clip name (letters, digits and underscore):", parent=self)
        if name is None:
            return
        name = name.strip()
        if not name or not name.replace("_", "a").isalnum() or name in self._clips:
            messagebox.showerror("New camera", "Use a unique name containing letters, digits and underscore.", parent=self)
            return
        description = simpledialog.askstring(
            "New camera", "Description:", initialvalue=f"Copy of {donor_name}", parent=self)
        if description is None:
            return
        imported = self._import_clip(donor_path.read_bytes())
        if imported is None:
            return
        ga, source_name = imported
        try:
            rebuilt, _row = fe10_battle.clone_camera_file(
                self._data, donor_row, name, description)
            animation.read_animation_bytes(ga)
            path = self._project.files_dir / "xcam" / f"{name}.ga"
            self._project.write_keeping_original(path, ga)
            self._project.write_logical("battle_data", rebuilt)
        except (OSError, ValueError, IndexError) as exc:
            messagebox.showerror("Could not create camera", str(exc), parent=self)
            return
        self._data = rebuilt
        self._dirty = False
        self._save_button.configure(state="disabled")
        self._changelog.append("Battle cameras", f"Created {name} from {source_name}")
        self._load(rebuilt)
        self._tree.selection_set(name)
        self._show()

    def save(self) -> bool:
        if not self._dirty:
            return True
        try:
            self._project.write_logical("battle_data", self._data)
        except OSError as exc:
            messagebox.showerror("Could not save FE10Battle.cms", str(exc), parent=self)
            return False
        self._dirty = False
        self._save_button.configure(state="disabled")
        self._status.configure(text="Saved FE10Battle.cms camera registry.")
        self._changelog.append("FE10Battle.cms", "Saved camera-registry changes")
        return True

    def _revert(self) -> None:
        if self._dirty and not messagebox.askyesno(
                "Unsaved changes", "Discard the unsaved camera-registry changes?", parent=self):
            return
        self._dirty = False
        self._save_button.configure(state="disabled")
        self._load()

    def _fill(self) -> None:
        query = self._query.get().strip().casefold()
        selected = self._tree.selection()
        selected_name = selected[0] if selected else None
        self._tree.delete(*self._tree.get_children())
        for name, (path, _description, frames, curves, row, _groups) in self._clips.items():
            if query and query not in name.casefold():
                continue
            state = "registered" if row is not None else "loose"
            if path is None:
                state = "no file"
            self._tree.insert("", "end", iid=name, values=(name, frames or "", curves or "", state))
        if selected_name and self._tree.exists(selected_name):
            self._tree.selection_set(selected_name)

    def _show(self) -> None:
        selection = self._tree.selection()
        if not selection:
            return
        name = selection[0]
        path, description, frames, curves, row, groups = self._clips[name]
        self._title.configure(text=name)
        registry = f"FE10BCamFile row {row}" if row is not None else "not in FE10BCamFile"
        group_text = ", ".join(groups) if groups else "not selected by a camera group"
        self._detail.configure(text=(f"{description or '(no description)'}\n{registry}; "
                                     f"{frames} frames, {curves} curves\nGroups: {group_text}"))
        if path is None:
            self._preview.show(None, "The registered test clip has no xcam .ga file.")
            return
        xcam = self._project.files_dir / "xcam"
        try:
            loaded = _build_loaded_set(
                f"xcam/{name}",
                {"cam.g": (xcam / "cam.g").read_bytes(), "cam.gs": (xcam / "cam.gs").read_bytes()},
                [(path.name, path.read_bytes())],
            )
            self._preview.show(loaded)
            self._preview.select_animation(path.name)
        except Exception as exc:  # noqa: BLE001
            self._preview.show(None, f"Could not preview this clip: {exc}")


def battle_camera_viewer(parent: tk.Misc, project: ModProject, changelog: ChangeLog) -> EditorPanel:
    if project.game is Game.RADIANT_DAWN:
        return Fe10CameraViewer(parent, project, changelog)
    return BattleCameraViewer(parent, project, changelog)
