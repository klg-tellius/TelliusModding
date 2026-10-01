"""Battle cameras page: the camera scripts (``xcam/*.dbx``) and the camera
rigs (``zdbx/camera.dbx``) of ``zdbx.cmp``; see ``formats/battle_camera.py``.

Scripts are edited as a keyframe table (position, rotation, distance and
time per keyframe). Rigs are edited field by field. Every change is written
to ``zdbx.cmp`` at once and the first one keeps the vanilla archive for
"Restore original"."""

from __future__ import annotations

import tkinter as tk
from tkinter import messagebox, simpledialog, ttk

from .. import battle_tables
from ..exceptions import ProjectError
from ..formats import battle_camera as bc
from ..formats import dbx
from ..project import ModProject
from .changelog import ChangeLog
from .editor_panel import EditorPanel

RIG_ENTRY = "zdbx/camera.dbx"
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


class BattleCameraViewer(EditorPanel):
    display_name = "Battle cameras"

    def __init__(self, parent: tk.Misc, project: ModProject, changelog: ChangeLog):
        super().__init__(parent)
        self._project = project
        self._changelog = changelog
        self._scripts: dict[str, bc.CameraScript] = {}
        self._frames: list[bc.Keyframe] = []
        self._rigs: dict[str, bc.CameraRig] = {}
        self._edited: set[str] = set()
        notebook = ttk.Notebook(self)
        notebook.pack(fill="both", expand=True, padx=8, pady=8)
        scripts, rigs = ttk.Frame(notebook), ttk.Frame(notebook)
        notebook.add(scripts, text="Camera scripts (xcam)")
        notebook.add(rigs, text="Camera rigs (camera.dbx)")
        self._build_scripts(scripts)
        self._build_rigs(rigs)
        self._status = ttk.Label(self, text="", style="Muted.TLabel", padding=(8, 0, 8, 6))
        self._status.pack(anchor="w")
        self._load()

    # -- scripts tab -----------------------------------------------------------
    def _build_scripts(self, tab: ttk.Frame) -> None:
        body = ttk.PanedWindow(tab, orient="horizontal")
        body.pack(fill="both", expand=True, pady=8)
        left = ttk.Frame(body)
        body.add(left, weight=2)
        self._script_tree = ttk.Treeview(left, columns=("name", "camera", "n", "state"), show="headings", selectmode="browse")
        for key, title, width in (("name", "Script", 150), ("camera", "Camera", 100), ("n", "Keys", 40), ("state", "", 60)):
            self._script_tree.heading(key, text=title)
            self._script_tree.column(key, width=width, anchor="w", stretch=key == "name")
        self._script_tree.pack(fill="both", expand=True)
        self._script_tree.bind("<<TreeviewSelect>>", lambda _e: self._show_script())

        right = ttk.Frame(body, padding=(12, 0, 0, 0))
        body.add(right, weight=4)
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
                                        selectmode="browse", height=8)
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
        bottom = ttk.Frame(right)
        bottom.pack(anchor="w", pady=8)
        ttk.Button(bottom, text="Apply script", command=self._apply_script).pack(side="left")
        ttk.Button(bottom, text="Restore original", command=self._restore_script).pack(side="left", padx=(6, 0))
        ttk.Button(bottom, text="Add script...", command=self._add_script).pack(side="left", padx=(6, 0))

    # -- rigs tab ----------------------------------------------------------------
    def _build_rigs(self, tab: ttk.Frame) -> None:
        body = ttk.PanedWindow(tab, orient="horizontal")
        body.pack(fill="both", expand=True, pady=8)
        left = ttk.Frame(body)
        body.add(left, weight=1)
        self._rig_tree = ttk.Treeview(left, columns=("name", "kind"), show="headings", selectmode="browse")
        self._rig_tree.heading("name", text="Rig")
        self._rig_tree.heading("kind", text="Follows")
        self._rig_tree.column("name", width=130)
        self._rig_tree.column("kind", width=80)
        self._rig_tree.pack(fill="both", expand=True)
        self._rig_tree.bind("<<TreeviewSelect>>", lambda _e: self._show_rig())
        right = ttk.Frame(body, padding=(12, 0, 0, 0))
        body.add(right, weight=2)
        self._rig_title = ttk.Label(right, text="(no rig selected)", font=("Segoe UI", 12, "bold"))
        self._rig_title.pack(anchor="w", pady=(0, 6))
        form = ttk.Frame(right)
        form.pack(anchor="w", fill="x")
        form.columnconfigure(1, weight=1)
        self._rig_vars = {key: tk.StringVar() for _l, key in RIG_FIELDS}
        for row, (label, key) in enumerate(RIG_FIELDS):
            ttk.Label(form, text=label).grid(row=row, column=0, sticky="w", pady=2)
            ttk.Entry(form, textvariable=self._rig_vars[key], width=28).grid(row=row, column=1, sticky="ew", padx=(8, 0), pady=2)
        ttk.Label(right, text="An empty box means the rig has no such line. Angles are degrees.",
                  style="Muted.TLabel").pack(anchor="w", pady=(6, 0))
        buttons = ttk.Frame(right)
        buttons.pack(anchor="w", pady=8)
        ttk.Button(buttons, text="Apply rig", command=self._apply_rig).pack(side="left")
        ttk.Button(buttons, text="Restore camera.dbx", command=self._restore_rigs).pack(side="left", padx=(6, 0))

    # -- loading -----------------------------------------------------------------
    def _load(self) -> None:
        try:
            texts = battle_tables.read_entries(self._project, "xcam")
            rig_text = battle_tables.read_entry(self._project, RIG_ENTRY)
            self._edited = battle_tables.modified_entries(self._project, "xcam") | (
                {RIG_ENTRY} if battle_tables.is_modified(self._project, RIG_ENTRY) else set())
        except (ProjectError, OSError) as exc:
            self._status.config(text=f"Could not read zdbx.cmp: {exc}. Extract the project first.")
            return
        self._scripts = {}
        for path, text in texts.items():
            try:
                self._scripts[path[5:-4]] = bc.read_script(text)
            except dbx.DbxError:
                continue
        self._rigs = {r.name: r for r in bc.read_rigs(rig_text)}
        self._camera_box.config(values=sorted(self._rigs))
        selected = self._selected_script()
        self._script_tree.delete(*self._script_tree.get_children())
        for name, s in sorted(self._scripts.items()):
            self._script_tree.insert("", "end", iid=name, values=(
                name, s.camera, len(s.keyframes), "edited" if f"xcam/{name}.dbx" in self._edited else ""))
        if selected and self._script_tree.exists(selected):
            self._script_tree.selection_set(selected)
        selected_rig = self._selected_rig()
        self._rig_tree.delete(*self._rig_tree.get_children())
        for name, rig in self._rigs.items():
            self._rig_tree.insert("", "end", iid=name, values=(name, rig.entity_class or "-"))
        if selected_rig and self._rig_tree.exists(selected_rig):
            self._rig_tree.selection_set(selected_rig)

    def _selected_script(self) -> str | None:
        selection = self._script_tree.selection()
        return selection[0] if selection else None

    def _selected_rig(self) -> str | None:
        selection = self._rig_tree.selection()
        return selection[0] if selection else None

    def _say(self, message: str) -> None:
        self.after(50, lambda: self._status.config(text=message))

    def _changed(self, message: str) -> None:
        self._changelog.append("Battle cameras", message)
        self._load()
        self._say(message + ".")

    def _fail(self, exc: Exception) -> None:
        messagebox.showerror(self.display_name, str(exc), parent=self)

    # -- scripts -------------------------------------------------------------------
    def _show_script(self) -> None:
        name = self._selected_script()
        if name is None:
            return
        script = self._scripts[name]
        self._script_title.config(text=name)
        self._caption.set(script.caption)
        self._camera.set(script.camera)
        self._frames = list(script.keyframes)
        self._fill_frames()
        self._status.config(text="")

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
            self._fail(exc)
            return
        self._fill_frames(i)

    def _add_frame(self) -> None:
        try:
            frame = self._frame_from_fields()
        except bc.CameraError as exc:
            self._fail(exc)
            return
        self._frames.append(frame)
        self._fill_frames(len(self._frames) - 1)

    def _delete_frame(self) -> None:
        i = self._selected_frame()
        if i is None:
            return
        if len(self._frames) == 1:
            messagebox.showinfo(self.display_name, "A script needs at least one keyframe.", parent=self)
            return
        del self._frames[i]
        self._fill_frames(min(i, len(self._frames) - 1))

    def _move_frame(self, step: int) -> None:
        i = self._selected_frame()
        if i is None or not 0 <= i + step < len(self._frames):
            return
        self._frames[i], self._frames[i + step] = self._frames[i + step], self._frames[i]
        self._fill_frames(i + step)

    def _apply_script(self) -> None:
        name = self._selected_script()
        if name is None:
            return
        path = f"xcam/{name}.dbx"
        try:
            text = battle_tables.read_entry(self._project, path)
            new = bc.set_script_keyframes(text, self._frames)
            new = bc.set_script_field(new, "caption", self._caption.get())
            new = bc.set_script_field(new, "camera", self._camera.get())
            if new == text:
                self._say("No change.")
                return
            battle_tables.write_entry(self._project, path, new)
        except (dbx.DbxError, ProjectError) as exc:
            self._fail(exc)
            return
        self._changed(f"Edited camera script {name}")

    def _restore_script(self) -> None:
        name = self._selected_script()
        if name is None:
            return
        path = f"xcam/{name}.dbx"
        if not battle_tables.is_modified(self._project, path):
            self._say("Already the original.")
            return
        battle_tables.restore_entry(self._project, path)
        self._changed(f"Restored camera script {name}")
        self._show_script()

    def _add_script(self) -> None:
        name = simpledialog.askstring("Add script", "New script name (e.g. atk_custom_l):", parent=self)
        if not name:
            return
        name = name.strip()
        camera = self._camera.get() or "camCharaL0"
        try:
            if name in self._scripts:
                raise bc.CameraError(f"{name} already exists.")
            battle_tables.write_entry(self._project, f"xcam/{name}.dbx", bc.new_script(name, camera, name), create=True)
        except (dbx.DbxError, ProjectError) as exc:
            self._fail(exc)
            return
        self._changed(f"Added camera script {name}")

    # -- rigs ------------------------------------------------------------------------
    def _show_rig(self) -> None:
        name = self._selected_rig()
        if name is None:
            return
        rig = self._rigs[name]
        self._rig_title.config(text=name)
        for _label, key in RIG_FIELDS:
            self._rig_vars[key].set(rig.get(key))

    def _apply_rig(self) -> None:
        name = self._selected_rig()
        if name is None:
            return
        try:
            text = battle_tables.read_entry(self._project, RIG_ENTRY)
            new, rig = text, self._rigs[name]
            for _label, key in RIG_FIELDS:
                value = self._rig_vars[key].get().strip()
                if value == rig.get(key):
                    continue  # untouched (also keeps vanilla's malformed rot on cam1)
                if not value and key not in ("entityName1", "entityName2"):
                    raise bc.CameraError(f"{key} cannot be emptied; remove the line in the file instead.")
                new = bc.set_rig_field(new, name, key, value)
            if new == text:
                self._say("No change.")
                return
            battle_tables.write_entry(self._project, RIG_ENTRY, new)
        except (dbx.DbxError, ProjectError) as exc:
            self._fail(exc)
            return
        self._changed(f"Edited camera rig {name}")

    def _restore_rigs(self) -> None:
        if not battle_tables.is_modified(self._project, RIG_ENTRY):
            self._say("Already the original.")
            return
        battle_tables.restore_entry(self._project, RIG_ENTRY)
        self._changed("Restored camera.dbx")
        self._show_rig()
