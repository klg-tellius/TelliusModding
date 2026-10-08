"""The two sides of a simulated battle, built from ``FE8Data.bin`` records.

A :class:`Combatant` is a free-standing copy of what the battle needs: stats,
build, skills, class categories, the equipped :class:`Weapon` and the
terrain under the unit. The simulator's stat and skill fields edit this copy
only; nothing here writes to the game data.

Starting stats follow the loader as :mod:`fe_modding.formats.fe8data`
documents it: class base stats plus the character's personal bonus, except
Luck, whose class base byte the loader skips. Build (Con) is the character's
plus the class's (``get_unit_build``). Skills are the character's three plus
the class's five. The weapon's held-item bonuses (``ItemEntry.stat_bonus``,
Con included) are added by the rules, not baked into these stats.

Above the base level, stats follow the fixed ("Fraction") growth mode, which
is deterministic: a stat's counter gains its growth rate each level and pays
a point per 100 (90 with Frac90). A promotion resets the level to 1, halves
the counters and keeps the gains, so the new class's bases and caps apply.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Iterable, Optional

from ..formats import fe8data

STAT_NAMES = fe8data.STAT_NAMES  # HP Str Mag Skl Spd Lck Def Res
HP, STR, MAG, SKL, SPD, LCK, DEF, RES = range(8)

#: Attack-type tokens that make a weapon hit with Mag against Res (item 0x10, engine values 4-7).
MAGIC_ATTACK_TYPES = frozenset({"flame", "thunder", "wind", "rod"})


@dataclass
class Weapon:
    """The battle-relevant fields of an item record (:class:`fe8data.ItemEntry`)."""

    iid: str = ""
    weapon_type: str = ""  # ITEM_WEAPON_TYPES token: sword, lance, axe, bow, flame, ..., knife, fang
    attack_type: str = ""  # decides physical vs. magic
    might: int = 0
    hit: int = 0
    crit: int = 0
    weight: int = 0
    min_range: int = 1
    max_range: int = 1  # 255 = Mag / 2
    properties: frozenset = frozenset()  # ITEM_PROPERTY_TOKENS: twice, crit0, sealcrit, weakA, sfxseal...
    effective: frozenset = frozenset()  # ITEM_CATEGORY_TOKENS the weapon is effective against
    stat_bonus: tuple = (0,) * 10  # ITEM_STAT_BONUS_NAMES order: STAT_NAMES, Mov, Con
    effect: str = ""  # EID_ played when it is used (a tome's spell)

    @property
    def magic(self) -> bool:
        return self.attack_type in MAGIC_ATTACK_TYPES or "magsw" in self.properties

    @property
    def is_staff(self) -> bool:
        return self.weapon_type == "rod" and not self.might

    def in_range(self, distance: int, magic_stat: int = 0) -> bool:
        high = max(1, magic_stat // 2) if self.max_range == 255 else self.max_range
        return self.min_range <= distance <= high


def weapon_from_item(item: fe8data.ItemEntry) -> Weapon:
    bonus = tuple(item.stat_bonus) + (0,) * (10 - len(item.stat_bonus))
    return Weapon(
        iid=item.iid or "", weapon_type=item.weapon_type or "", attack_type=item.attack_type or "",
        might=item.might, hit=item.hit, crit=item.crit, weight=item.weight,
        min_range=item.min_range, max_range=item.max_range,
        properties=frozenset(p for p in item.properties if p),
        effective=frozenset(c for c in item.categories if c), stat_bonus=bonus[:10],
        effect=item.effect or "",
    )


@dataclass
class Combatant:
    name: str = "Unit"
    pid: Optional[str] = None
    jid: Optional[str] = None
    aid: Optional[str] = None  # battle animation ID (zdbx.battle_model_for)
    level: int = 1
    stats: list = field(default_factory=lambda: [20] + [5] * 7)  # maximums, STAT_NAMES order
    hp: Optional[int] = None  # current HP; None = full
    build: int = 5  # Con
    skills: list = field(default_factory=list)  # SID_ labels
    categories: frozenset = frozenset()  # class category tokens: armor, fly, knight, beast...
    weapon: Optional[Weapon] = None  # None = unarmed (cannot attack)
    terrain: tuple = (0, 0, 0)  # avoid, defence, resistance bonus of the tile
    boss: bool = False
    final_boss: bool = False
    blessed_armor: bool = False  # only weakA weapons damage it
    status_condition: bool = False  # under a status: attackers' Hit becomes 100

    def __post_init__(self):
        self.stats = list(self.stats)
        if self.hp is None:
            self.hp = self.stats[HP]

    def copy(self) -> "Combatant":
        return replace(self, stats=list(self.stats), skills=list(self.skills))

    def has(self, sid: str) -> bool:
        return sid in self.skills


def _class(fe8: fe8data.Fe8Data, jid: Optional[str]) -> Optional[fe8data.ClassEntry]:
    return next((c for c in fe8.classes if c.jid == jid), None) if jid else None


def _skills(*lists: Iterable) -> list:
    out = []
    for values in lists:
        for sid in values or ():
            if sid and sid not in out:
                out.append(sid)
    return out


MAX_LEVEL = 20
#: An unpromoted unit can promote from this level (get_remaining_exp_to_level_or_promotion_cap).
PROMOTION_LEVEL = 10
LUCK_CAP = 40  # compute_lck_stat_capped: no class lookup, a fixed cap
FIXED_THRESHOLD, FRAC90_THRESHOLD = 100, 90


def linked_class(fe8: fe8data.Fe8Data, cls: Optional[fe8data.ClassEntry]) -> Optional[fe8data.ClassEntry]:
    """The class ``promotes_to`` links to (the link runs both ways)."""
    linked = _class(fe8, cls.promotes_to) if cls is not None else None
    return linked if linked is not cls else None


def class_kind(fe8: fe8data.Fe8Data, cls: Optional[fe8data.ClassEntry]) -> str:
    """``fe8data.CLASS_CATEGORIES`` name: Unpromoted, Promoted or Laguz."""
    return fe8data.class_category(cls, fe8.classes) if cls is not None else "Unpromoted"


def promotion_of(fe8: fe8data.Fe8Data, cls: Optional[fe8data.ClassEntry]) -> Optional[fe8data.ClassEntry]:
    """The class an unpromoted human class promotes to, else None."""
    linked = linked_class(fe8, cls)
    if class_kind(fe8, cls) == "Unpromoted" and linked is not None and class_kind(fe8, linked) == "Promoted":
        return linked
    return None


def _value(cls: Optional[fe8data.ClassEntry], bonus: list, gains: list, i: int) -> int:
    """A stat as the compute_*_stat_capped getters build it: min(cap, class base + personal bonus
    + gains); Luck has no class base and a fixed cap of 40."""
    base = 0 if i == LCK or cls is None else cls.base_stats[i]
    cap = LUCK_CAP if i == LCK else (cls.stat_caps[i] if cls is not None and cls.stat_caps else 0)
    value = base + bonus[i] + gains[i]
    return min(cap, value) if cap else value


def _grow(cls, bonus: list, gains: list, counters: list, rates: list, levels: int, threshold: int) -> None:
    """``levels`` fixed-growth level-ups (apply_fixed_growth_level_up): each adds the rate to the
    stat's counter and pays a point per full threshold, trimmed to the class cap."""
    for _ in range(max(0, levels)):
        for i in range(8):
            counters[i] += max(0, rates[i])
            gain = 0
            while counters[i] >= threshold:
                counters[i] -= threshold
                gain += 1
            if gain:
                cap = LUCK_CAP if i == LCK else (cls.stat_caps[i] if cls is not None and cls.stat_caps else 0)
                room = cap - _value(cls, bonus, gains, i) if cap else gain
                gains[i] += max(0, min(gain, room))


def _stats(cls, bonus: list, gains: list) -> list:
    stats = [max(0, _value(cls, bonus, gains, i)) for i in range(8)]
    stats[HP] = max(1, stats[HP])
    return stats


def _levelled(fe8, start_cls, cls, bonus, rates_for, counters, start_level, level, promoted_at, threshold):
    """Gains after levelling from ``start_level`` to ``level``. With ``promoted_at``, the unit
    levels in ``start_cls`` up to that level, promotes (promote_unit_to_linked_class: level 1,
    fixed-growth counters halved) and levels to ``level`` in ``cls``."""
    gains = [0] * 8
    if promoted_at is not None and start_cls is not None and start_cls is not cls:
        promoted_at = max(start_level, min(MAX_LEVEL, promoted_at))
        _grow(start_cls, bonus, gains, counters, rates_for(start_cls), promoted_at - start_level, threshold)
        counters[:] = [c // 2 for c in counters]
        start_level = 1
    _grow(cls, bonus, gains, counters, rates_for(cls), min(MAX_LEVEL, level) - start_level, threshold)
    return gains


def _modifiers(cls) -> list:
    return list(getattr(cls, "growth_modifiers", None) or [0] * 8) + [0] * 8


def from_class(fe8: fe8data.Fe8Data, jid: str, *, name: Optional[str] = None, level: int = 1,
               promoted_from: Optional[str] = None, promoted_at: int = MAX_LEVEL) -> Combatant:
    """A generic unit of a class: its base stats (Luck 0), build and skills, levelled from 1 to
    ``level`` on the class growth rates (fixed growth). With ``promoted_from``, it first levels
    in that class to ``promoted_at`` and then promotes into ``jid``."""
    cls = _class(fe8, jid)
    if cls is None:
        raise KeyError(jid)
    start = _class(fe8, promoted_from) if promoted_from else None
    skills = _skills(cls.skills)
    threshold = FRAC90_THRESHOLD if "SID_FRAC90" in skills else FIXED_THRESHOLD
    gains = _levelled(fe8, start, cls, [0] * 8, lambda c: list(c.growths[:8]), [0] * 8, 1, level,
                      promoted_at if start is not None else None, threshold)
    return Combatant(
        name=name or jid, jid=jid, aid=cls.aid, level=max(1, min(MAX_LEVEL, level)),
        stats=_stats(cls, [0] * 8, gains), build=cls.build,
        skills=skills, categories=frozenset(c for c in cls.categories if c),
    )


def from_character(fe8: fe8data.Fe8Data, pid: str, *, name: Optional[str] = None,
                   jid: Optional[str] = None, level: Optional[int] = None,
                   promoted_at: Optional[int] = None) -> Combatant:
    """A character in their own class or ``jid``, at their base level or levelled up to
    ``level`` with fixed growth: the personal growth rates plus the class growth modifiers,
    the counters starting from ``fixed_growth_start``. With ``promoted_at``, the character
    levels in their own class to that level, then promotes into ``jid``."""
    char = next((c for c in fe8.characters if c.pid == pid), None)
    if char is None:
        raise KeyError(pid)
    jid = jid or char.jid
    cls = _class(fe8, jid)
    own = _class(fe8, char.jid)
    bonus = list(char.stat_bonus[:8])
    skills = _skills(char.sids, cls.skills if cls else ())
    threshold = FRAC90_THRESHOLD if "SID_FRAC90" in skills else FIXED_THRESHOLD
    start_level = char.level if promoted_at is not None or level is None else min(char.level, level)
    gains = _levelled(fe8, own, cls, bonus,
                      lambda c: [g + m for g, m in zip(char.growth[:8], _modifiers(c))],
                      list(char.fixed_growth_start[:8]) + [0] * (8 - len(char.fixed_growth_start)),
                      start_level, char.level if level is None else level, promoted_at, threshold)
    promoted = cls is not None and jid != char.jid
    aid = (char.aid_promoted if promoted else char.aid_unpromoted) or (cls.aid if cls else None)
    return Combatant(
        name=name or pid, pid=pid, jid=jid, aid=aid,
        level=char.level if level is None else max(1, min(MAX_LEVEL, level)),
        stats=_stats(cls, bonus, gains),
        build=char.build + (cls.build if cls else 0),
        skills=skills,
        categories=frozenset(c for c in (cls.categories if cls else ()) if c),
    )
