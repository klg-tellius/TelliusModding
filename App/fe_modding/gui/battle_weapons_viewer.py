"""Battle weapons page: every ``xwp/<NAME>.dbx`` table of ``zdbx.cmp``.

The table tells the battle engine which weapon actor an item gets, how it
is held (``kind``), whether it flies (``missile``) and which effects play
with it (``formats/battle_weapons.py``). Edits are written to ``zdbx.cmp``
at once; the first one keeps the vanilla archive for "Restore original"."""

from __future__ import annotations

from tkinter import messagebox, simpledialog

from ..formats import battle_weapons as bw
from .battle_table_viewer import BattleTableViewer, choice_label


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
