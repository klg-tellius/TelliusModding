"""Battle sceneries page: every ``zbg/<scenery>/param.dbx`` of ``zdbx.cmp``
(indoor flag, footstep effect and sound; see ``formats/battle_scenery.py``)."""

from __future__ import annotations

from tkinter import messagebox, simpledialog

from .. import battle_tables
from ..formats import battle_scenery as bs
from .battle_table_viewer import BattleTableViewer, choice_label


class BattleSceneryViewer(BattleTableViewer):
    display_name = "Battle sceneries"
    changelog_scope = "Battle sceneries"
    folder = "zbg"
    entry_suffix = "/param.dbx"
    noun = "scenery"
    plural = "sceneries"
    columns = (
        ("name", "Scenery", 170, "w"),
        ("label", "Name", 150, "w"),
        ("room", "Place", 80, "w"),
        ("effect", "Footstep effect", 120, "w"),
        ("sound", "Footstep sound", 100, "w"),
    )
    fields = (
        ("Place", "roomFlag", bs.ROOM_FLAGS),
        ("Footstep effect", "footEffect", bs.FOOT_EFFECTS),
        ("Footstep sound", "footSound", bs.FOOT_SOUNDS),
    )

    def _load(self):
        try:
            self._labels = bs.terrain_labels(battle_tables.read_entry(self._project, "zdbx/bgList.dbx"))
        except Exception:  # noqa: BLE001 - labels are decoration; the list works without them
            self._labels = {}
        super()._load()

    def name_of(self, path):
        return path.split("/")[1]

    def entry_path(self, name):
        return f"zbg/{name}/param.dbx"

    def parse(self, text):
        return bs.read_scenery(text)

    def row(self, name, t):
        return (name, self._labels.get(name, ""), bs.ROOM_FLAGS.get(t.room_flag, "?"),
                bs.FOOT_EFFECTS.get(t.foot_effect, "?"), bs.FOOT_SOUNDS.get(t.foot_sound, "?"))

    def values(self, t):
        return {"roomFlag": choice_label(bs.ROOM_FLAGS, t.room_flag),
                "footEffect": choice_label(bs.FOOT_EFFECTS, t.foot_effect),
                "footSound": choice_label(bs.FOOT_SOUNDS, t.foot_sound)}

    def describe(self, name, t):
        return self._labels.get(name, "Not listed in bgList.dbx")

    def set_field(self, text, key, value):
        return bs.set_scenery_field(text, key, value)

    def note(self):
        return ("Add scenery copies the selected scenery's parameters under a new folder name; "
                "its models go in files/zbg/<name>/ and bgList.dbx must list it to be used.")

    def new_entry(self):
        source = self._selected()
        if source is None:
            messagebox.showinfo(self.display_name, "Select the scenery to copy first.", parent=self)
            return None
        name = simpledialog.askstring("Add scenery", "New scenery folder name:", parent=self)
        if not name:
            return None
        name = name.strip()
        return name, bs.clone_scenery(battle_tables.read_entry(self._project, self.entry_path(source)), name)
