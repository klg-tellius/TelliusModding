"""Normalized tactical records for FE9 and FE10.

Only fields used by map play and combat are exposed.  The adapter deliberately
keeps undecoded FE10 fields neutral instead of borrowing a Path of Radiance
value; corpus validation can therefore identify a missing relationship rather
than quietly producing PoR behaviour.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from types import SimpleNamespace

from ..battle_sim import units as battle_units

RD_DIFFICULTY_ROWS = (
    "kill_exp_base", "action_exp_base", "kill_exp_multiplier", "action_exp_multiplier",
    "second_tier_level_adjustment", "third_tier_level_adjustment", "animalize_level_adjustment",
    "boss_kill_bonus", "steal_kill_bonus", "weapon_exp_multiplier",
)


def _stats(values: dict, prefix: str) -> list[int]:
    return [int(values.get(f"{prefix}_{name}", 0) or 0)
            for name in ("hp", "str", "mag", "skl", "spd", "lck", "def", "res")]


@dataclass
class TacticalData:
    characters: list
    classes: list
    items: list
    skills: list
    terrain: list = field(default_factory=list)
    difficulty: dict = field(default_factory=dict)
    item_rules: dict = field(default_factory=dict)
    raw: object = None
    game: str = "fe9"

    def combatant(self, pid: str, jid: str | None = None):
        if self.game == "fe9":
            return battle_units.from_character(self.raw, pid, jid=jid)
        char = next((c for c in self.characters if c.pid == pid), None)
        cls = next((c for c in self.classes if c.jid == (jid or getattr(char, "jid", None))), None)
        if cls is None:
            raise KeyError(jid or getattr(char, "jid", None))
        bonus = list(getattr(char, "bonus_stats", (0,) * 8)) if char else [0] * 8
        stats = [max(1 if i == 0 else 0, cls.base_stats[i] + bonus[i]) for i in range(8)]
        stats = [min(v, cls.stat_caps[i]) if cls.stat_caps[i] else v for i, v in enumerate(stats)]
        skills = list(dict.fromkeys(list(getattr(cls, "skills", ())) + list(getattr(char, "skills", ()))))
        tier = 1 + int(bool(getattr(cls, "demotes_to", None)))
        previous = next((c for c in self.classes if c.jid == getattr(cls, "demotes_to", None)), None)
        if previous is not None and getattr(previous, "demotes_to", None):
            tier = 3
        return battle_units.Combatant(name=pid, pid=pid, jid=cls.jid,
                                      aid=(getattr(char, "aid_1", None) if char else None) or cls.aid,
                                      level=getattr(char, "level", 1), stats=stats,
                                      build=cls.build + int(getattr(char, "bonus_weight", 0)),
                                      skills=skills, categories=frozenset(cls.categories), tier=tier,
                                      effective_level=getattr(char, "level", 1) + (tier - 1) * 20,
                                      authority=int(getattr(char, "authority", 0)))

    def class_combatant(self, jid: str):
        if self.game == "fe9":
            return battle_units.from_class(self.raw, jid)
        cls = next((c for c in self.classes if c.jid == jid), None)
        if cls is None:
            raise KeyError(jid)
        return battle_units.Combatant(name=jid, jid=jid, aid=cls.aid,
                                      stats=list(cls.base_stats), build=cls.build,
                                      skills=list(cls.skills), categories=frozenset(cls.categories))


def fe9_data(data) -> TacticalData:
    return TacticalData(list(data.characters), list(data.classes), list(data.items), list(data.skills),
                        item_rules=dict(getattr(data, "item_rules", {})), raw=data, game="fe9")


def fe10_data(data) -> TacticalData:
    chars = []
    for r in data.characters:
        v = r.values
        chars.append(SimpleNamespace(pid=v.get("pid"), mpid=v.get("mpid"), jid=v.get("jid"), level=int(v.get("level", 1)),
                                     aid_1=v.get("aid_1"), aid_2=v.get("aid_2"),
                                     aid_3=v.get("aid_3"), aid_4=v.get("aid_4"),
                                     weapon_ranks=v.get("weapon_ranks") or "", skills=list(r.lists.get("skills", ())),
                                     growth=_stats(v, "growth"), bonus_stats=_stats(v, "bonus"),
                                     bonus_weight=int(v.get("bonus_weight", 0)), biorhythm=int(v.get("biorhythm", 255)),
                                     authority=int(v.get("authority", 0)), gauge=(int(v.get("gauge_turn", 0)),
                                         int(v.get("gauge_battle", 0)), int(v.get("gauge_turn_transformed", 0)),
                                         int(v.get("gauge_battle_transformed", 0)))))
    classes = []
    for r in data.classes:
        v = r.values
        sounds = list(r.lists.get("sounds", ()))
        categories = [s.removeprefix("SFXC_").lower() for s in sounds if isinstance(s, str)]
        classes.append(SimpleNamespace(jid=v.get("jid"), mjid=v.get("mjid"), movement=int(v.get("movement", 0)), movement_type=0,
                                       build=int(v.get("weight", 0)), innate_weapon=v.get("innate_weapon"),
                                       weapon_ranks=v.get("weapon_ranks") or "", max_weapon_ranks=v.get("max_weapon_ranks") or "",
                                       promotes_to=v.get("promotes_to"), demotes_to=v.get("demotes_to"), other_form=v.get("other_form"),
                                       skills=list(r.lists.get("skills", ())) + ([v.get("extra_skill")] if v.get("extra_skill") else []),
                                       categories=categories, base_stats=_stats(v, "base"), stat_caps=_stats(v, "cap"),
                                       growths=_stats(v, "growth"), aid=v.get("aid")))
    items = []
    for r in data.items:
        v = r.values
        props = [x for x in r.lists.get("attributes", ()) if x]
        effective = [x for x in r.lists.get("effective", ()) if x]
        bonus = list(r.bonuses or (0,) * 10)
        items.append(SimpleNamespace(iid=v.get("iid"), miid=v.get("miid"), weapon_type=v.get("weapon_type") or "",
                                     attack_type=v.get("weapon_type") or "", rank=v.get("rank") or "",
                                     might=int(v.get("might", 0)), hit=int(v.get("hit", 0)), crit=int(v.get("crit", 0)),
                                     weight=int(v.get("weight", 0)), uses=int(v.get("uses", 0)), wexp=int(v.get("wexp", 0)),
                                     min_range=int(v.get("range_min", 1)), max_range=int(v.get("range_max", 1)),
                                     properties=props, attributes=props, categories=effective, effective=effective,
                                     stat_bonus=bonus, effect=v.get("effect") or ""))
    skills = [SimpleNamespace(**r.values) for r in data.skills]
    terrain = []
    for r in data.tables.get("terrain", ()):
        v = r.values
        terrain.append(SimpleNamespace(name=v.get("name") or str(r.index), name_key=v.get("name_key"),
                                       avoid=int(v.get("avoid", 0)), defense=int(v.get("defense", 0)),
                                       resistance=int(v.get("resistance", 0)),
                                       alt_bonus=(int(v.get("alternate_avoid", 0)), int(v.get("alternate_defense", 0)),
                                                  int(v.get("alternate_resistance", 0))),
                                       move_costs=list(r.lists.get("move_costs", ())), index=r.index))
    difficulty = {}
    for name, record in zip(RD_DIFFICULTY_ROWS, data.tables.get("difficulty", ())):
        difficulty[name] = tuple(int(record.values.get(f"value_{i}", 0)) for i in range(4))
    return TacticalData(chars, classes, items, skills, terrain=terrain, difficulty=difficulty,
                        raw=data, game="fe10")


def adapt(data) -> TacticalData:
    if isinstance(data, TacticalData):
        return data
    return fe10_data(data) if data.__class__.__name__ == "Fe10Data" else fe9_data(data)
