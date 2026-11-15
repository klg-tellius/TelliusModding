"""Radiant Dawn checks that need someone at the controller (``build --set rdcheck``, parity Phase 7).

The parity audit's in-game list (section 7) left these unchecked on RFEE01. The rest of that list ran
unattended on 2026-11-15 (the Prologue booted with the chapter jump, screenshots compared with
retail): placement mirror and sub-tile offsets, the water flag, the archer's rig round trip, an
edited staff roll and fitted skeletons. Their results are in the parity audit.

Saves come from ``--saves`` (``rd/made_after_1-1_FE10_US.dat``: Micaiah's army after 1-1;
``rd/made_4P_start_FE10_US.dat``: the start of 4-P).
"""
from __future__ import annotations

from .harness import Scenario
from .parity_scenarios import RD

AFTER_1_1 = "rd/made_after_1-1_FE10_US.dat"
MADE_4P = "rd/made_4P_start_FE10_US.dat"
#: an event-flag slot no retail script uses before Part 2 (BMST flags 0..127)
TEST_FLAG = 127
LOAD_NOTE = ("Dolphin starts at the title. Press A through the title, choose Load and the file the steps name. "
             "The game saves to its own NAND folder; your real saves are not used.")


def _first_file(save):
    return next(r for r in save.active_records() if not r.checkpoint and r.logical_slot is not None)


def _unit(record, data, pid):
    tables = record.id_tables()
    number = tables.characters.index(pid.removeprefix("PID_")) + 1
    units = record.unit_records(record.support_slot_counts_from_fe10data(data))
    return next(u for u in units if not u.empty and u.person_number == number)


def card_support(ctx):
    """Micaiah and Edward's support points exactly at the C threshold: the support menu offers C."""
    from fe_modding.formats import fe8data, fe10data, save_file_fe10 as sf

    data = ctx.project.read_logical("game_data")
    db = fe10data.read_fe10data(data)
    micaiah = next(r for r in db.table("support") if r.id == "PID_MICAIAH")
    slot = next(k for k, (partner, _flag, _speed) in enumerate(micaiah.lists["partners"]) if partner == "PID_EDDIE")
    thresholds = tuple(data[fe8data.section_start(data, "RelianceParam"):][:3])   # C, B, A
    save = sf.SaveFile.from_bytes((ctx.saves / AFTER_1_1).read_bytes())
    record = _first_file(save)
    unit = _unit(record, data, "PID_MICAIAH")
    record.set_unit_support_points(unit, slot, thresholds[0])
    ctx.facts.update(slot=slot, points=thresholds[0])
    return {"FE10_US.dat": save.to_bytes([record])}


def card_flag(ctx):
    """One unused event flag set in the save: the game must load it and write it back."""
    from fe_modding.formats import save_file_fe10 as sf

    save = sf.SaveFile.from_bytes((ctx.saves / AFTER_1_1).read_bytes())
    record = _first_file(save)
    record.set_script_flag(TEST_FLAG, True)
    return {"FE10_US.dat": save.to_bytes([record])}


def after_flag(card_dir, ctx):
    """Read the save the game wrote: is the flag still set in every file?"""
    from fe_modding.formats import save_file_fe10 as sf

    path = card_dir / "FE10_US.dat"
    if not path.is_file():
        return ["No FE10_US.dat after the run."]
    save = sf.SaveFile.from_bytes(path.read_bytes())
    lines = []
    for record in save.active_records():
        if record.logical_slot is None:
            continue
        flags = record.script_flags()
        lines.append(f"File {record.logical_slot + 1}{' (checkpoint)' if record.checkpoint else ''}: "
                     f"flag {TEST_FLAG} {'set' if flags[TEST_FLAG] else 'CLEAR'}")
    return lines or ["The save holds no files."]


SCENARIOS: list[Scenario] = [
    Scenario(
        "R1", "Radiant Dawn: saves", "Play from the Saves page",
        "Saves page › Play in Dolphin on RFEE01 (emulator.prepare_wii_save_run): an edit reaches the game",
        app_steps=["Open a copy of a Radiant Dawn project in the app and load any FE10_US.dat on the Saves page.",
                   "In the first file, set Micaiah's level to 15 and press Save.",
                   "Press Play in Dolphin."],
        steps=["Load the first file and open Micaiah's status screen."],
        checks=["Micaiah is level 15.", "The game runs normally after loading (move a unit, end a turn)."],
        boot="none", region=RD, minutes=5, notes=[LOAD_NOTE]),
    Scenario(
        "R2", "Radiant Dawn: saves", "An event flag survives the game's own save",
        f"Saves › Flags on RFEE01 (BMST script flag {TEST_FLAG} set in the file)",
        steps=["Load File 1 (after 1-1).", "Go to the next map's preparations and save over File 1 from the "
               "preparations menu.", "Close Dolphin."],
        checks=[f"The runner reads the written save: flag {TEST_FLAG} is still set (shown after Dolphin closes)."],
        card=card_flag, after=after_flag, boot="title", region=RD, minutes=5, anim_speed=None,
        notes=[LOAD_NOTE]),
    Scenario(
        "R3", "Radiant Dawn: saves", "A support edit opens a conversation",
        "Saves › Units › Supports on RFEE01 (Micaiah's points with Edward set to the C threshold)",
        steps=["Load File 1 (after 1-1).", "In the preparations menu, open Support."],
        checks=["Micaiah and Edward's C support is offered.", "Viewing it plays the conversation and the menu "
                "then shows them at C."],
        card=card_support, boot="title", region=RD, minutes=5, anim_speed=None, notes=[LOAD_NOTE]),
    Scenario(
        "R4", "Radiant Dawn: story flow", "The Silver Army name on 4-1",
        "ChapterData +0x8F (army group) as the story flow writes it (rd_armies)",
        steps=["Load File 1 (the start of 4-P). Win 4-P (it ends when the first enemy phase starts).",
               "On 4-1, open a unit's status screen and the unit list."],
        checks=["The army name shown for Micaiah's units is the Silver Army.", "Micaiah has the leader mark."],
        card=lambda ctx: {"FE10_US.dat": (ctx.saves / MADE_4P).read_bytes()}, auto_win={"0401": 1},
        boot="title", region=RD, minutes=10, anim_speed=None, notes=[LOAD_NOTE]),
    Scenario(
        "R5", "Radiant Dawn: hub", "A hub on a blank map",
        "Create hub › Blank map on RFEE01 (HUB-RD-01)",
        app_steps=["In a copy of a Radiant Dawn project: Chapters › Create hub, choose Blank map (any size and "
                   "colour), link it after 1-1 in the story flow, and build the disc."],
        steps=["Play 1-1 (or load a save made at its end) until the hub opens."],
        checks=["The hub loads on the blank ground (no crash, no missing-texture colours).",
                "Its links lead to the next chapter."],
        boot="none", region=RD, minutes=15, optional=True),
    Scenario(
        "R6", "Radiant Dawn: models", "The paired model after a rig round trip",
        "Assets › Models › Replace rig on ymu/sothe1_mikaya2 (paired model, repeated bone names)",
        app_steps=["In a copy of a Radiant Dawn project, export the rig kit of ymu/sothe1_mikaya2 and import it "
                   "back unchanged with Replace rig."],
        steps=["Play to the event where Sothe carries Micaiah."],
        checks=["Both characters look and move as in the retail game."],
        boot="none", region=RD, minutes=10, optional=True),
]

NOT_COVERED = [
    ("Placement mirror and sub-tile offsets, the water flag, the archer's rig round trip, an edited staff roll, "
     "fitted skeletons", "Checked unattended on 2026-11-15 (Prologue, screenshots against retail; parity audit)."),
]


def by_id() -> dict[str, Scenario]:
    return {s.id: s for s in SCENARIOS}
