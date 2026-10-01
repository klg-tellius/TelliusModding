"""Battle unit parameters page: the tuning keys of every ``zu/<code>_prm.dbx``
(speed, range, jump attacks, flying, size; see ``formats/battle_params.py``).
Texture lines of the same files are edited under Assets > 3D Models."""

from __future__ import annotations

from ..formats import battle_params as bp
from .battle_table_viewer import BattleTableViewer

YES_NO = {0: "No", 1: "Yes"}


class BattleParamsViewer(BattleTableViewer):
    display_name = "Battle unit parameters"
    changelog_scope = "Battle unit parameters"
    folder = "zu"
    entry_suffix = "_prm.dbx"
    noun = "model"
    plural = "models"
    can_add = False
    columns = (
        ("name", "Model", 90, "w"),
        ("speed", "Speed", 60, "w"),
        ("range", "Range", 60, "w"),
        ("flags", "Flags", 260, "w"),
    )
    fields = (
        *((label, key, None) for key, label in {**bp.FLOAT_KEYS, **bp.INT_KEYS}.items()),
        *((label, key, YES_NO) for key, label in bp.FLAG_KEYS.items()),
    )

    def name_of(self, path):
        return path[len("zu/"):-len("_prm.dbx")]

    def parse(self, text):
        return bp.read_params(text)

    def row(self, name, p):
        flags = ", ".join(label for key, label in bp.FLAG_KEYS.items() if p.get(key) == "1")
        return (name, p.get("移動速度"), p.get("間合い"), flags)

    def values(self, p):
        out = {key: p.get(key) for key in (*bp.FLOAT_KEYS, *bp.INT_KEYS)}
        out.update({key: f"{int(p.get(key) == '1')} - {YES_NO[int(p.get(key) == '1')]}" for key in bp.FLAG_KEYS})
        return out

    def describe(self, name, p):
        return f"zu/{name}_prm.dbx  (an empty box removes the line)"

    def set_field(self, text, key, value):
        return bp.set_param(text, key, value)

    def note(self):
        return "Speeds and ranges are engine units, not measured. Flags are on (1) or absent."
