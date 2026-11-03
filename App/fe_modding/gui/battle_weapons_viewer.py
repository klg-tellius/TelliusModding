"""Battle weapons page: every ``xwp/<NAME>.dbx`` table of ``zdbx.cmp``.

The table tells the battle engine which weapon actor an item gets, how it
is held (``kind``), whether it flies (``missile``) and which effects play
with it (``formats/battle_weapons.py``). Edits are written to ``zdbx.cmp``
at once; the first one keeps the vanilla archive for "Restore original"."""

from __future__ import annotations

from tkinter import messagebox, simpledialog

from ..formats import battle_weapons as bw
from .battle_table_viewer import BattleTableViewer, choice_label
from ..game_profile import files_root_of


class BattleWeaponsViewer(BattleTableViewer):
    display_name = "Battle weapons"
    changelog_scope = "Battle weapons"
    folder = "xwp"
    noun = "weapon"
    plural = "weapons"
    columns = (
        ("name", "Weapon", 190, "w"),
        ("kind", "Type", 170, "w"),
        ("missile", "Flight", 100, "w"),
        ("effect", "Effect", 140, "w"),
    )
    fields = (
        ("Type", "kind", bw.KINDS),
        ("Flight", "missile", bw.MISSILES),
        ("Effect", "effectId", None),
        ("Target effect", "damageEffId", None),
    )

    def name_of(self, path):
        return path[len("xwp/"):-len(".dbx")]

    def parse(self, text):
        return bw.read_weapon(text)

    def model_of(self, name):
        folder = files_root_of(self._project) / "xwp" / name.lower()
        pack = folder / f"{name.lower()}.cmp"
        if pack.is_file():
            return f"xwp/{name.lower()}", pack
        return f"No model in xwp/{name.lower()}/."

    def row(self, name, t):
        return (name, choice_label(bw.KINDS, t.kind), bw.MISSILES.get(t.missile, str(t.missile)), t.effect_id or "")

    def values(self, t):
        return {"kind": choice_label(bw.KINDS, t.kind), "missile": choice_label(bw.MISSILES, t.missile),
                "effectId": t.effect_id or "", "damageEffId": t.damage_effect_id or ""}

    def describe(self, name, t):
        return f"Model: {t.model_folder}/{t.model}.cmp" if t.model_folder else "No Model block (no 3D weapon)"

    def set_field(self, text, key, value):
        return bw.set_weapon_field(text, key, value)

    def note(self):
        return "Effect names are EID_ entries (see Visual Effects); leave a box empty for none."

    def new_entry(self):
        name = simpledialog.askstring("Add weapon", "Item name without IID_ (e.g. DEVILAXE):", parent=self)
        if not name:
            return None
        name = name.strip().upper()
        has_model = messagebox.askyesno(
            "Add weapon", f"Does the weapon have a model, files/xwp/{name}/{name}.cmp?\n"
            "No means a tome-like weapon without a 3D model.", parent=self)
        return name, bw.new_weapon_dbx(name, kind=0, missile=0, model=name if has_model else None)


class Fe10BattleWeaponsViewer(BattleTableViewer):
    """Radiant Dawn: the same page over the ``FE10BWeapon`` rows of ``FE10Battle.cms``
    (:mod:`formats.fe10_battle_weapons`). Several rows share a weapon key, so each is listed as
    ``KEY #row``; rows are edited, not added."""

    display_name = "Battle weapons"
    changelog_scope = "Battle weapons"
    folder = "xwp"
    noun = "weapon"
    plural = "weapons"
    can_add = False
    columns = (
        ("name", "Weapon", 190, "w"),
        ("kind", "Type", 140, "w"),
        ("effect", "Effect", 160, "w"),
        ("model", "Model", 140, "w"),
    )
    fields = (
        ("Type", "type", None),  # choices are FE10BWeaponType's rows, filled in _load
        ("Model", "model", None),
        ("Hit effect", "hit", None),
        ("Critical hit effect", "crit", None),
        ("Effect", "effect", None),
        ("Target effect", "target", None),
    )

    def _load(self) -> None:
        from ..formats import fe10_battle_weapons as fw

        self._tables.clear()
        self._paths.clear()
        try:
            self._data = self._project.read_logical("battle_data")
            self._types = fw.weapon_types(self._data)
            weapons = fw.read_weapons(self._data)
            original = self._original()
        except Exception as exc:  # noqa: BLE001 - missing or unreadable file
            self._count.config(text=f"Could not read {self._project.profile.file_label('battle_data')}: {exc}")
            return
        type_box = next(w for w in self._form_widgets() if str(w.cget("textvariable")) == str(self._vars["type"]))
        type_box.configure(values=[choice_label(self._types, k) for k in self._types], state="readonly")
        self._edited = set()
        for w in weapons:
            name = w.label()
            self._tables[name] = w
            self._paths[name] = name
            if original is not None and w.index < len(original) and (original[w.index].labels, original[w.index].type) \
                    != (w.labels, w.type):
                self._edited.add(name)
        self._refresh()

    def _form_widgets(self):
        found, stack = [], [self]
        while stack:
            widget = stack.pop()
            if widget.winfo_class() == "TCombobox":
                found.append(widget)
            stack.extend(widget.winfo_children())
        return found

    def _original(self):
        from ..formats import fe10_battle_weapons as fw, lz10

        raw = self._project.extracted_bytes(self._project.logical_path("battle_data"))
        return fw.read_weapons(lz10.decompress(raw)) if raw is not None else None

    def row(self, name, w):
        return (name, choice_label(self._types, w.type), w.labels.get("effect") or "", w.labels.get("model") or "")

    def values(self, w):
        return {"type": choice_label(self._types, w.type), **{key: w.labels.get(key) or "" for key in
                                                              ("model", "hit", "crit", "effect", "target")}}

    def describe(self, name, w):
        lines = [f"{w.labels.get('name') or ''} · row {w.index} of FE10BWeapon"]
        if w.labels.get("magic"):
            lines.append(f"Magic class: {w.labels['magic']}")
        if w.second:
            lines.append(f"Second type byte (+0x21): {w.second}, not decoded")
        return "\n".join(lines)

    def model_of(self, name):
        model = (self._tables[name].labels.get("model") or "").lower()
        if not model:
            return "This row has no 3D weapon."
        pack = files_root_of(self._project) / "xwp" / model / f"{model}.cmp"
        return (f"xwp/{model}", pack) if pack.is_file() else f"No model in xwp/{model}/."

    def note(self):
        return ("Effect names are EID_ entries (see Visual Effects); leave a box empty for none. The model is "
                "an xwp/ folder. Rows are FE10Battle.cms's FE10BWeapon table.")

    def _apply(self) -> None:
        from ..formats import fe10_battle_weapons as fw

        name = self._selected()
        if name is None:
            return
        w = self._tables[name]
        labels = {key: self._vars[key].get().strip() or None for key in ("model", "hit", "crit", "effect", "target")}
        try:
            kind = int(self._vars["type"].get().split(" - ", 1)[0])
        except ValueError:
            kind = w.type
        if labels == {k: w.labels.get(k) for k in labels} and kind == w.type:
            self._status.config(text="No change.")
            return
        try:
            data = fw.set_weapon(self._data, w.index, labels=labels, type=kind)
            self._project.write_logical("battle_data", data)
        except (ValueError, IndexError, OSError) as exc:
            messagebox.showerror(self.display_name, str(exc), parent=self)
            return
        self._after_edit(name, f"Edited {self.noun} {name}")

    def _restore(self) -> None:
        from ..formats import fe10_battle_weapons as fw

        name = self._selected()
        if name is None:
            return
        original = self._original()
        w = self._tables[name]
        if original is None or w.index >= len(original) or name not in self._edited:
            self._status.config(text="Already the original.")
            return
        old = original[w.index]
        data = fw.set_weapon(self._data, w.index, labels=dict(old.labels), type=old.type)
        self._project.write_logical("battle_data", data)
        self._after_edit(name, f"Restored {self.noun} {name}")


def battle_weapons_panel(parent, project, changelog):
    """The Battle Weapons page of the project's battle-data format (``GameProfile.battle_dialect``)."""
    cls = Fe10BattleWeaponsViewer if project.profile.battle_dialect == "fe10" else BattleWeaponsViewer
    return cls(parent, project, changelog)
