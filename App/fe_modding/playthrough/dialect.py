"""Profile-selected contracts for the shared tactical chapter runner.

The playthrough used to treat Path of Radiance's four factions, seven-word CP
instructions and 96 flags as universal.  This module is the single boundary
where those engine differences are selected.  Runtime code consumes these
small contracts and consequently never has to infer a game from a file name.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..formats import cp_data
from ..formats.cmb.catalog import triggers
from ..game_profile import GameProfile, PATH_OF_RADIANCE_PROFILE, profile_of


@dataclass(frozen=True)
class ArmyModel:
    """Turn order and force allegiance for one game's tactical maps."""

    phase_order: tuple[int, ...]
    names: dict[int, str]
    enemy_teams: frozenset[int]

    def relation(self, a: int, b: int) -> str:
        if a == b:
            return "same"
        if (a in self.enemy_teams) != (b in self.enemy_teams):
            return "opposing"
        return "other"

    def hostile(self, a: int, b: int) -> bool:
        return self.relation(a, b) == "opposing"


FE9_ARMIES = ArmyModel((0, 1, 2, 3), {0: "Player", 1: "Enemy", 2: "Ally", 3: "Partner"},
                       frozenset({1}))
# RFEE01 schedules the player, enemy and partner/other force phases.  A force
# list remains distinct from its acting team on Part 4 maps; SimUnit stores both.
FE10_ARMIES = ArmyModel((0, 1, 2), {0: "Player", 1: "Enemy", 2: "Partner"}, frozenset({1}))


@dataclass(frozen=True)
class PlaythroughDialect:
    name: str
    profile: GameProfile
    cp: cp_data.Dialect
    army: ArmyModel
    flag_slots: int
    openings: tuple[str, ...]

    @property
    def trigger_catalogue(self):
        return triggers(self.name)


FE9 = PlaythroughDialect("fe9", PATH_OF_RADIANCE_PROFILE, cp_data.FE9, FE9_ARMIES, 96,
                         ("Startup", "Opening0", "Opening1", "Opening2"))


def dialect_for(value=None) -> PlaythroughDialect:
    """Return the tactical dialect for a profile, project, or dialect name."""
    if isinstance(value, PlaythroughDialect):
        return value
    if value == "fe10" or getattr(value, "script_dialect", None) == "fe10":
        from ..game_profile import RADIANT_DAWN_PROFILE
        return PlaythroughDialect("fe10", RADIANT_DAWN_PROFILE, cp_data.FE10, FE10_ARMIES, 128,
                                  ("Startup", "Opening0", "Opening1", "Opening2"))
    if value is not None and not isinstance(value, (str, GameProfile)):
        value = profile_of(value)
    if isinstance(value, GameProfile) and value.script_dialect == "fe10":
        return dialect_for("fe10")
    return FE9
