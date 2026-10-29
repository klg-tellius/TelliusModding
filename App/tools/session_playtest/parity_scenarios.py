"""The PoR/RD parity checks that need someone at the controller (``build --set parity``).

Everything else in ``docs/app/parity-test-plan.md`` was run unattended (a scripted pad, the file
log and screenshots); its results are in the plan's Results section. These tests boot Radiant Dawn
with the RD chapter jump: a fresh party, so only chapter 1-1 (``0101``) has an army.
"""
from __future__ import annotations

from .harness import Scenario

RD = "RFEE01"
RD_JUMP_NOTE = ("Dolphin starts Radiant Dawn and goes straight into Part 1, Chapter 1 (the Prologue), past "
                "the title and file menu. Press Start to skip the opening and the talks. The map menu is on "
                "Z (End is the last line). The game saves to its own NAND folder; your real saves are not used.")


def build_g1(ctx):
    """Every stat gains 3 for each growth success."""
    from fe_modding.game_code import entries_fe10  # noqa: F401 - registers the RD catalogue
    for stat in range(8):
        ctx.tune(**{f"rd.growth.random.{stat}": 3})
    ctx.facts["gain"] = 3


def build_a1(ctx):
    """Micaiah gets Adept, and the Skill activation grid's bonus makes it certain (+100)."""
    from fe_modding.formats import fe10data
    from fe_modding.game_code import entries_fe10  # noqa: F401
    data = ctx.project.read_logical("game_data")
    db = fe10data.read_fe10data(data)
    rec = next(r for r in db.characters if r.id == "PID_MICAIAH")
    ctx.project.write_logical("game_data", fe10data.set_list(data, "character", rec.index, "skills",
                                                             [*rec.lists["skills"], "SID_ADEPT"]))
    ctx.tune(**{"rd.skill.adept.activation_scale": 4, "rd.skill.adept.activation_bonus": 100})


SCENARIOS: list[Scenario] = [
    Scenario(
        "G1", "Radiant Dawn: Game Code", "Level-up growth: 3 points per success",
        "Game Code > Level-up growth on RFEE01 (rd.growth.random.N, the shared growth grid)",
        steps=["Skip to the map. Fight the bandits with Micaiah and Edward until one of them levels up "
               "(two or three kills; Micaiah's Light is safest from range).",
               "Watch the level-up screen."],
        checks=["Every stat that rises on the level-up screen rises by 3, not 1.",
                "The game keeps running after the level-up (no freeze)."],
        build=build_g1, chapter="0101", difficulty="Normal", anim_speed=None, region=RD, minutes=10,
        notes=[RD_JUMP_NOTE]),
    Scenario(
        "A1", "Radiant Dawn: Game Code", "Skill activation grid: Adept always",
        "Game Code > Skill activation on RFEE01 (rd.skill.adept.activation_bonus = 100, PROC_ROWS grid)",
        steps=["Skip to the map. Attack a bandit with Micaiah (or wait for the enemy phase: they attack her).",
               "Watch three or four of her battles with animations on."],
        checks=["Adept's name appears in every battle where Micaiah attacks, and she attacks twice in a row.",
                "Nothing else about the battles changes (damage, hit rates)."],
        build=build_a1, chapter="0101", difficulty="Hard", anim_speed=None, region=RD, minutes=6,
        optional=True, notes=[RD_JUMP_NOTE,
                              "Optional: the unattended run already compared the effect files of a +100 and a 0x run."]),
]

NOT_COVERED = [
    ("RD Supports list (a partner added to Ike)",
     "Needs a save from Part 3 or later with both units; the only RD save on this machine is a Part 1 start."),
    ("RD Saves > Convoy edit loaded in game",
     "The convoy is not reachable in Part 1's first chapters; needs a later save."),
    ("RD Add chapter: the added chapter's opening",
     "The copy of 1-1 (chapter 0501, number 56) reaches its map and hangs before any unit is placed. "
     "That is a bug to find in RFEE01 (custom chapter numbers), not something to look at in game."),
]


def by_id() -> dict[str, Scenario]:
    return {s.id: s for s in SCENARIOS}
