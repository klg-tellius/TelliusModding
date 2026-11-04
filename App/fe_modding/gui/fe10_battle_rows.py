"""Radiant Dawn's Battle Sceneries and Battle Unit Parameters pages: the Path of Radiance pages'
list and form over ``FE10Battle.cms`` rows (``FE10BMapModel`` and ``FE10BUnit``; see
:mod:`formats.fe10_battle_scenery` and :mod:`formats.fe10_battle_units`). Rows are edited in
place, not added; "Restore original" puts back the extracted disc's row."""

from __future__ import annotations

from tkinter import messagebox

from ..formats import fe10_battle_scenery as fs, fe10_battle_units as fu, lz10
from ..game_profile import files_root_of
from .battle_table_viewer import BattleTableViewer, choice_label

YES_NO = {0: "No", 1: "Yes"}


def _number(text: str) -> int:
    return int(str(text).split(" - ", 1)[0].strip())


class Fe10BattleRowViewer(BattleTableViewer):
    """Subclass contract: ``read_rows(data)`` (rows with ``index`` and ``label()``),
    ``prepare(data)`` (choices that come from the file), ``changes(row)`` (the form as
    ``write`` keywords, ``ValueError`` when a box is wrong), ``write(data, index, **changes)``
    and ``fields_of(row)`` (a row's values in ``changes`` form)."""

    can_add = False
    form_columns = 2

    def read_rows(self, data: bytes) -> list:
        raise NotImplementedError

    def prepare(self, data: bytes) -> None:
        pass

    def changes(self, row) -> dict:
        raise NotImplementedError

    def fields_of(self, row) -> dict:
        raise NotImplementedError

    def write(self, data: bytes, index: int, **changes) -> bytes:
        raise NotImplementedError

    def _original(self):
        raw = self._project.extracted_bytes(self._project.logical_path("battle_data"))
        return self.read_rows(lz10.decompress(raw)) if raw is not None else None

    def _load(self) -> None:
        self._tables.clear()
        self._paths.clear()
        try:
            self._data = self._project.read_logical("battle_data")
            self.prepare(self._data)
            rows = self.read_rows(self._data)
            self._originals = self._original()
        except Exception as exc:  # noqa: BLE001 - missing or unreadable file
            self._count.config(text=f"Could not read {self._project.profile.file_label('battle_data')}: {exc}")
            return
        self._edited = set()
        for row in rows:
            name = row.label()
            self._tables[name] = row
            self._paths[name] = name
            old = self._originals[row.index] if self._originals and row.index < len(self._originals) else None
            if old is not None and self.fields_of(old) != self.fields_of(row):
                self._edited.add(name)
        self._refresh()

    def _refresh(self) -> None:
        # rows in file order (sorting by label would put #10 before #2)
        query = self._query.get().strip().lower()
        selected = self._selected()
        self._tree.delete(*self._tree.get_children())
        for name, row in sorted(self._tables.items(), key=lambda item: item[1].index):
            if query and query not in (name + " " + self.describe(name, row)).lower():
                continue
            self._tree.insert("", "end", iid=name, values=(*self.row(name, row), "edited" if name in self._edited else ""))
        self._count.config(text=f"{len(self._tree.get_children())} of {len(self._tables)} {self.plural}")
        if selected and self._tree.exists(selected):
            self._tree.selection_set(selected)

    def _apply(self) -> None:
        name = self._selected()
        if name is None:
            return
        row = self._tables[name]
        try:
            changes = self.changes(row)
        except ValueError as exc:
            messagebox.showerror(self.display_name, str(exc), parent=self)
            return
        if changes == self.fields_of(row):
            self._status.config(text="No change.")
            return
        try:
            self._project.write_logical("battle_data", self.write(self._data, row.index, **changes))
        except (ValueError, IndexError, OSError) as exc:
            messagebox.showerror(self.display_name, str(exc), parent=self)
            return
        self._after_edit(name, f"Edited {self.noun} {name}")

    def _restore(self) -> None:
        name = self._selected()
        if name is None:
            return
        row = self._tables[name]
        if name not in self._edited or not self._originals or row.index >= len(self._originals):
            self._status.config(text="Already the original.")
            return
        old = self._originals[row.index]
        self._project.write_logical("battle_data", self.write(self._data, row.index, **self.fields_of(old)))
        self._after_edit(name, f"Restored {self.noun} {name}")


_SCENERY_FLAGS = tuple(fs.FLAGS.items())
_SCENERY_NUMBERS = (("Flight height", "flight_height"), ("Move limit", "move_limit"),
                    ("Camera limit", "camera_limit"), ("Position X", "x"), ("Position Y", "y"),
                    ("Position Z", "z"), ("Rotation (°)", "rotation"), ("Scale (1/256)", "scale"))


class Fe10BattleSceneryViewer(Fe10BattleRowViewer):
    """Battle Sceneries on Radiant Dawn: one ``FE10BMapModel`` row per placed backdrop model."""

    display_name = "Battle sceneries"
    changelog_scope = "Battle sceneries"
    folder = "zbg"
    noun = "scenery"
    plural = "scenery models"
    columns = (
        ("name", "Scenery", 150, "w"),
        ("room", "Place", 80, "w"),
        ("effect", "Footstep effect", 130, "w"),
        ("sound", "Footstep ground", 100, "w"),
    )
    fields = (
        ("Footstep effect", "foot_effect", None),  # FE10BFootEffect rows, filled in prepare
        ("Footstep ground", "ground", fs.GROUNDS),
        *((name, f"flag_{bit:02x}", YES_NO) for bit, name in _SCENERY_FLAGS),
        *((label, key, None) for label, key in _SCENERY_NUMBERS),
    )

    def read_rows(self, data):
        return fs.read_sceneries(data)

    def prepare(self, data):
        self._effects = fs.foot_effects(data)
        self._uses = fs.map_uses(data)
        self._boxes["foot_effect"].configure(values=[choice_label(self._effects, k) for k in self._effects],
                                             state="readonly")

    def row(self, name, s):
        return (name, "Indoors" if s.indoors else "Outdoors", self._effects.get(s.foot_effect, str(s.foot_effect)),
                fs.GROUNDS.get(s.ground, str(s.ground)))

    def values(self, s):
        out = {"foot_effect": choice_label(self._effects, s.foot_effect), "ground": choice_label(fs.GROUNDS, s.ground)}
        out.update({f"flag_{bit:02x}": choice_label(YES_NO, int(bool(s.flags & bit))) for bit, _ in _SCENERY_FLAGS})
        numbers = {"flight_height": s.flight_height, "move_limit": s.move_limit, "camera_limit": s.camera_limit,
                   "x": s.position[0], "y": s.position[1], "z": s.position[2], "rotation": s.rotation, "scale": s.scale}
        out.update({key: str(value) for key, value in numbers.items()})
        return out

    def describe(self, name, s):
        uses = ", ".join(f"{background} variant {variant}" for background, variant in self._uses.get(s.index, []))
        lines = [f"Row {s.index} of FE10BMapModel · sound group {s.sound_group or 'none'}",
                 f"Used by: {uses or 'no battle background'}"]
        other = s.flags & ~sum(fs.FLAGS)
        if other:
            lines.append(f"Other flag bits: {other:#04x} (kept)")
        return "\n".join(lines)

    def note(self):
        return ("Flight height, move limit and camera limit 0 use the FE10BSetup defaults. Scale 0 means 768 "
                "(3.0). Variants 2 and 3 of a background are the fights in the air. The footstep ground picks "
                "the sound column of each fighter's sound set (Battle Unit Parameters).")

    def model_of(self, name):
        from .battle_scene_editor import find_scene, scene_models

        folder = self._tables[name].folder
        pack = find_scene(scene_models(self._project), folder)
        if pack is None:
            return f"No model in zbg/{folder}/."
        return f"zbg/{pack.parent.name}", pack

    def fields_of(self, s):
        return {"flags": s.flags, "flight_height": s.flight_height, "move_limit": s.move_limit,
                "camera_limit": s.camera_limit, "foot_effect": s.foot_effect, "ground": s.ground,
                "position": tuple(s.position), "rotation": s.rotation, "scale": s.scale}

    def changes(self, s):
        flags = s.flags & ~sum(fs.FLAGS)
        for bit, _ in _SCENERY_FLAGS:
            if _number(self._vars[f"flag_{bit:02x}"].get()):
                flags |= bit
        try:
            numbers = {key: int(self._vars[key].get().strip() or 0) for _, key in _SCENERY_NUMBERS}
        except ValueError as exc:
            raise ValueError("Heights, limits, position, rotation and scale are whole numbers.") from exc
        return {"flags": flags, "flight_height": numbers["flight_height"], "move_limit": numbers["move_limit"],
                "camera_limit": numbers["camera_limit"], "foot_effect": _number(self._vars["foot_effect"].get()),
                "ground": _number(self._vars["ground"].get()),
                "position": (numbers["x"], numbers["y"], numbers["z"]), "rotation": numbers["rotation"],
                "scale": numbers["scale"]}

    def write(self, data, index, **changes):
        return fs.set_scenery(data, index, **changes)


class Fe10BattleParamsViewer(Fe10BattleRowViewer):
    """Battle Unit Parameters on Radiant Dawn: one ``FE10BUnit`` row per battle model description,
    with its FE10BParam values, FE10BFlags bits and footstep sound set."""

    display_name = "Battle unit parameters"
    changelog_scope = "Battle unit parameters"
    folder = "zu"
    noun = "model"
    plural = "models"
    columns = (
        ("name", "Model", 90, "w"),
        ("description", "Description", 150, "w"),
        ("range", "Range", 60, "w"),
        ("flags", "Flags", 220, "w"),
    )
    form_columns = 3

    def __init__(self, parent, project, changelog):
        # the form's rows are the file's FE10BParam and FE10BFlags names
        try:
            data = project.read_logical("battle_data")
            self._params, self._flags = fu.param_names(data), fu.flag_names(data)
        except Exception:  # noqa: BLE001 - _load says why the file cannot be read
            self._params, self._flags = [], []
        self.fields = (
            ("Footstep sounds", "sound", None),  # FE10BSFXList rows, filled in prepare
            *((label, f"p{i}", None) for i, label in enumerate(self._params)),
            *((label, f"f{i}", YES_NO) for i, label in enumerate(self._flags)),
        )
        super().__init__(parent, project, changelog)

    def read_rows(self, data):
        return fu.read_units(data)

    def prepare(self, data):
        self._sounds = fu.sound_sets(data)
        self._boxes["sound"].configure(values=[choice_label(self._sounds, k) for k in self._sounds], state="readonly")
        self._range = next((i for i, label in enumerate(self._params) if label.endswith("(間合い)")), None)

    def row(self, name, u):
        flags = ", ".join(label.split(" (", 1)[0] for i, label in enumerate(self._flags) if u.flags >> i & 1)
        return (u.model, u.description, f"{u.value(self._range):g}" if self._range is not None else "", flags)

    def values(self, u):
        out = {"sound": choice_label(self._sounds, u.sound)}
        out.update({f"p{i}": f"{u.value(i):g}" for i in range(len(self._params))})
        out.update({f"f{i}": choice_label(YES_NO, u.flags >> i & 1) for i in range(len(self._flags))})
        return out

    def describe(self, name, u):
        lines = [f"{u.description} · row {u.index} of FE10BUnit · model zu/{u.model}"]
        other = u.flags >> len(self._flags)
        if other:
            lines.append(f"Flag bits past FE10BFlags: {other << len(self._flags):#x} (kept)")
        return "\n".join(lines)

    def note(self):
        return ("Values are in steps of 1/256. The game looks each value and flag up by its FE10BParam / "
                "FE10BFlags name. Footstep sounds: the column comes from the scenery's ground.")

    def model_of(self, name):
        model = self._tables[name].model
        folder = files_root_of(self._project) / "zu" / model
        packs = sorted(folder.glob("*.cmp")) if folder.is_dir() else []
        return (f"zu/{model}", packs[0]) if packs else f"No model in zu/{model}/."

    def fields_of(self, u):
        return {"flags": u.flags, "params": dict(enumerate(u.params)), "sound": u.sound}

    def changes(self, u):
        flags = u.flags & ~((1 << len(self._flags)) - 1)
        for i in range(len(self._flags)):
            if _number(self._vars[f"f{i}"].get()):
                flags |= 1 << i
        params = dict(enumerate(u.params))
        for i, label in enumerate(self._params):
            text = self._vars[f"p{i}"].get().strip()
            try:
                raw = fu.to_raw(text)
            except ValueError as exc:
                raise ValueError(f"{label}: {exc}") from exc
            # keep the stored step when the box still shows the same rounded value
            if f"{u.value(i):g}" != text:
                params[i] = raw
        return {"flags": flags, "params": params, "sound": _number(self._vars["sound"].get())}

    def write(self, data, index, **changes):
        return fu.set_unit(data, index, **changes)


def battle_sceneries_panel(parent, project, changelog):
    """The Battle Sceneries page of the project's battle-data format."""
    from .battle_scenery_viewer import BattleSceneryViewer

    cls = Fe10BattleSceneryViewer if project.profile.battle_dialect == "fe10" else BattleSceneryViewer
    return cls(parent, project, changelog)


def battle_params_panel(parent, project, changelog):
    """The Battle Unit Parameters page of the project's battle-data format."""
    from .battle_params_viewer import BattleParamsViewer

    cls = Fe10BattleParamsViewer if project.profile.battle_dialect == "fe10" else BattleParamsViewer
    return cls(parent, project, changelog)
