"""What a playthrough reads but never changes: the map, the game data, the
chapter's scripts, AI data and messages."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from ..battle_sim import Fe9Rules
from ..formats import fe8data

#: Weapon types a unit can fight with (``fe8data.ITEM_WEAPON_TYPES`` tokens).
COMBAT_WEAPON_TYPES = frozenset({"sword", "lance", "axe", "bow", "knife", "flame", "thunder", "wind", "rod", "fang"})
IMPASSABLE = 255


def rank_columns(item: fe8data.ItemEntry) -> set:
    """The class rank columns (``WEAPON_TYPE_NAMES``) that may wield ``item``:
    knives go with swords, light tomes with light, staves with staff."""
    return {"flame": {"Fire"}, "thunder": {"Thunder"}, "wind": {"Wind"}, "rod": {"Light", "Staff"},
            "knife": {"Sword"}, "sword": {"Sword"}, "lance": {"Lance"}, "axe": {"Axe"},
            "bow": {"Bow"}}.get(item.weapon_type or "", set())


@dataclass
class World:
    width: int
    height: int
    terrain: list  # [x][y] terrain-type name (``map_file.terrain_grid``)
    terrain_types: list  # fe8data.TerrainType, engine order
    fe8: fe8data.Fe8Data
    link: Optional[list] = None  # [x][y] composed link status (``map_file.compose_link_status_grid``), None = all open
    playable: Optional[tuple] = None  # (x0, x1, y0, y1): the area inside the map's border, x1/y1 exclusive
    scripts: list = field(default_factory=list)  # cmb ScriptFile, the chapter's first, then startup.cmb
    script_names: list = field(default_factory=list)  # a display name per script
    cp: object = None  # cp_data.CpDocument
    messages: dict = field(default_factory=dict)  # message id -> text
    groups: dict = field(default_factory=dict)  # deployment section name -> dispo.DocSection (setup.groups)
    difficulty: str = "n"  # n (normal), h (hard), m (maniac)
    names: dict = field(default_factory=dict)  # PID_ -> display name
    item_names: dict = field(default_factory=dict)  # IID_ -> display name
    game_data: dict = field(default_factory=dict)  # fe8data.read_game_data: row -> (Normal, Hard, Maniac, Easy)

    def exp_constants(self) -> Optional[dict]:
        """The difficulty's GameData EXP values (``calculate_battle_exp``), or None without GameData."""
        if not self.game_data:
            return None
        column = {"n": 0, "h": 1, "m": 2}.get(self.difficulty, 0)
        return {name: values[column] for name, values in self.game_data.items()}

    def __post_init__(self) -> None:
        self.rules = Fe9Rules(self.fe8.skills)
        self.terrain_by_name: dict = {}
        for t in self.terrain_types:
            self.terrain_by_name.setdefault(t.name, t)
        self.characters = {c.pid: c for c in self.fe8.characters if c.pid}
        self.classes = {c.jid: c for c in self.fe8.classes if c.jid}
        self.items = {i.iid: i for i in self.fe8.items if i.iid}

    # -- map ------------------------------------------------------------------------------------
    def inside(self, x: int, y: int) -> bool:
        if not (0 <= x < self.width and 0 <= y < self.height):
            return False
        if self.playable is not None:
            x0, x1, y0, y1 = self.playable
            return x0 <= x < x1 and y0 <= y < y1
        return True

    def terrain_at(self, x: int, y: int) -> Optional[fe8data.TerrainType]:
        try:
            return self.terrain_by_name.get(self.terrain[x][y])
        except (IndexError, TypeError):
            return None

    def terrain_name(self, x: int, y: int) -> str:
        t = self.terrain_at(x, y)
        return (t.name_key.removeprefix("MT_") if t is not None and t.name_key else (t.name if t else "")) or "?"

    def move_cost(self, x: int, y: int, movement_type: int) -> int:
        """Cost of entering (x, y), :data:`IMPASSABLE` when it can't be entered."""
        if not self.inside(x, y):
            return IMPASSABLE
        t = self.terrain_at(x, y)
        if t is None or not t.move_costs:
            return 1
        if not 0 <= movement_type < len(t.move_costs):
            return 1
        return t.move_costs[movement_type]

    def linked(self, fx: int, fy: int, tx: int, ty: int) -> bool:
        """Whether the map's links let a unit step from one tile to the next."""
        if self.link is None:
            return True
        from ..formats import map_file

        return map_file.link_tiles_are_adjacent_passable(self.link, fx, fy, tx, ty)

    # -- data -----------------------------------------------------------------------------------
    def name(self, pid) -> str:
        if not isinstance(pid, str):
            return "?"
        return self.names.get(pid) or pid.removeprefix("PID_")

    def item_name(self, iid) -> str:
        if not isinstance(iid, str):
            return "?"
        return self.item_names.get(iid) or iid.removeprefix("IID_")

    def can_wield(self, unit, item: fe8data.ItemEntry) -> bool:
        """Whether ``unit`` (a SimUnit) may use ``item`` as a weapon or staff."""
        if item is None or item.weapon_type not in COMBAT_WEAPON_TYPES:
            return False
        cls = self.classes.get(unit.jid)
        if item.weapon_type == "fang":
            return cls is not None and (cls.innate_weapon == item.iid or "fang" in unit.categories
                                        or bool(set(unit.categories) & {"beast", "bird", "dragon", "alize"}))
        if cls is None:
            return True
        ranks = fe8data.class_weapon_rank_map(cls)
        return bool(rank_columns(item) & set(ranks))
