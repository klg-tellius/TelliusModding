"""The in-game checks that keep Radiant Dawn controls locked (``build --set locks``).

Each test settles one thing the app still refuses to edit or labels vaguely on RFEE01:

- L1: Build › Object flags on Radiant Dawn maps. The flag bits are Path of Radiance's traced meanings
  (research/rd/MAP_NOTES.md); the app keeps the dialog read-only on RD (``MapEditor.verified_us_map_layout``)
  until the visible ones behave the same in game.
- L2-L6: the four start-flag slots of RD's ``Tutorial/tut_data_*.bin`` (Tutorials editor, "Slot 1-4",
  ``RADIANT_DAWN_PROFILE.tutorial_flag_names``). Retail Normal English entries are ``(0, 2, 2, 0)``;
  marking every tutorial learned in one slot shows whether a Normal game reads that slot.

- A1: the story flow's Army combo (``rd_armies``). It starts from a GameFAQs save (Nassaro30, 2024,
  decrypted from the SD export into ``<saves>/rd/gamefaqs_30509_FE10_US.dat``) whose File 3 is at the
  Endgame; the fixture moves that file back to 4-P (chapter number 32).
"""
from __future__ import annotations

from fe_modding import map_props
from fe_modding.formats import map_file, tut_data
from fe_modding.game_profile import files_root_of

from .harness import Scenario
from .parity_scenarios import RD, RD_JUMP_NOTE

MAP = "bmap0101"
#: (prop, field, mask, what the tester looks for); one bit per prop, each prop visible from the start.
FLAG_TESTS = (
    ("boat01", "flag_bits_b", 0x01, "the three small boats on the canal (the row of water across the "
                                    "lower half of the map)"),
    ("cart01", "flag_bits_b", 0x02, "the five handcarts (one beside the market, others in the streets)"),
    ("mrkt_day01", "effect_type", 0x40, "the market stall in the middle of the map, north of the "
                                        "starting units"),
)
TUTORIAL_FILE = "Tutorial/tut_data_n_en.bin"
#: The Part 4 save (see the module docstring) and the slot moved back to 4-P.
ARMY_SAVE = "rd/gamefaqs_30509_FE10_US.dat"
ARMY_FILE_SLOT = 2           # File 3 (logical slots count from 0)
FOUR_P = 32                  # C0401's chapter number


def build_l1(ctx):
    """One flag bit on three props of the Prologue map, through the map editor's own edit_prop."""
    path = files_root_of(ctx.project) / "zmap" / MAP / "map.cmp"
    _entries, files = map_props.read_map_container(path)
    data = map_file.read_map_bytes(files["map.bin"])
    for name, field, mask, _where in FLAG_TESTS:
        obj = next(o for o in data.build_desc if o.filename == name)
        map_props.edit_prop(ctx.project, path, name, {field: getattr(obj, field) | mask})


def tutorial_slot_build(slot: int):
    def build(ctx):
        """Every Normal English tutorial starts unlocked and learned in ``slot`` only."""
        path = files_root_of(ctx.project) / TUTORIAL_FILE
        tut = tut_data.read_tut_data(path.read_bytes())
        for entry in tut.entries:
            entry.start_flags[slot] = tut_data.UNLOCKED | tut_data.LEARNED
        ctx.project.write_keeping_original(path, tut_data.build_tut_data(tut))
        ctx.facts["slot"] = slot + 1
    build.__doc__ = f"Every Normal English tutorial starts learned in slot {slot + 1}."
    return build


def build_army(ctx):
    """4-1 (C0402) played with Micaiah's army instead of Ike's, through the story flow and rd_armies,
    with an automatic win at 4-P's first enemy phase. Test-only: TEAM_0401_OP also collects force 5,
    because the save comes from after the Endgame merge, where every unit is in force 5."""
    from fe_modding import rd_armies, script_sources
    from fe_modding.game_code.rd_story import Army
    from fe_modding.game_code.story_flow import open_story_flow

    flow, why = open_story_flow(ctx.project)
    if flow is None:
        raise RuntimeError(why)
    flow.set_army("0402", Army.DIVISION_1)
    flow, _ = open_story_flow(ctx.project)
    plan = rd_armies.plan(ctx.project, flow, ctx.project.read_logical("game_data"))
    if plan.problems:
        raise RuntimeError("; ".join(plan.problems))
    rd_armies.apply_scripts(ctx.project, plan)
    ctx.project.write_logical("game_data", rd_armies.apply_records(ctx.project.read_logical("game_data"), plan))
    ctx.facts["handover"] = ", ".join(f"{name}: {transfers}" for name, transfers in plan.functions.items())
    path = files_root_of(ctx.project) / "Scripts" / "startup.cmb"
    loaded = script_sources.load(ctx.project, path)
    bodies = rd_armies.function_bodies(loaded.source)
    old = bodies["TEAM_0401_OP"]
    new = rd_armies._with_transfers(old, [(5, 7), *rd_armies.transfers_of(old)])
    script_sources.save(ctx.project, loaded, loaded.source.replace("\n".join(old), "\n".join(new), 1))
    ctx.append_script("0401", '\n# Session playtest: automatic victory\n'
                              '@before_phase(turn_from=1, turn_to=1, phase="enemy")\n'
                              'def SessionAutoWin():\n    set("gf_complete")\n')


def card_army(ctx):
    """The Part 4 save with File 3 moved back to 4-P."""
    from fe_modding.formats import save_file_fe10 as sf

    save = sf.SaveFile.from_bytes((ctx.saves / ARMY_SAVE).read_bytes())
    record = next(r for r in save.active_records() if not r.checkpoint and r.logical_slot == ARMY_FILE_SLOT)
    ctx.facts["was_chapter"] = record.chapter_number
    record.chapter_number = FOUR_P
    return {"FE10_US.dat": save.to_bytes([record])}


TUTORIAL_STEPS = ["Skip the opening talk with Start. When the map appears, wait a few seconds without "
                  "pressing anything, then move Micaiah once.",
                  "Note whether a tutorial window (a help box explaining the controls) opens by itself."]

SCENARIOS: list[Scenario] = [
    Scenario(
        "A1", "Radiant Dawn: locked controls", "Army switching: Micaiah's army plays 4-1",
        "Chapter › Overview › Army on RD (rd_armies: TEAM_0401_ED / TEAM_0402_ED, C0402 group 18 and lord "
        "Micaiah)",
        steps=["At the title screen, Continue and load File 3 (it was at the Endgame, chapter {was_chapter}; "
               "the test moved it back to Part 4's Prologue, 4-P).",
               "Let 4-P's opening play (Start skips talks). The army-splitting screen appears: accept it as it is.",
               "In 4-P's battle, end the player phase (Z menu, End). The chapter clears itself when the enemy "
               "phase starts.",
               "Go through the end of 4-P and the save menu, up to 4-1's base or preparations screen.",
               "Open the unit list (Manage units / the army list)."],
        checks=["4-P starts and its splitting screen shows the three armies (no freeze when loading File 3).",
                "4-1's units are Micaiah's army: Micaiah, Sothe, Naesala, Sanaki and the rest of the Silver "
                "Army group from 4-P. Ike, Mist and Tibarn are not in the list.",
                "4-1's map loads with them deployed (Micaiah on a starting tile), and the game runs through "
                "one player phase.",
                "The army is named the Silver Army in 4-1 (unit or army screens)."],
        build=build_army, card=card_army, boot="title", difficulty="Normal", anim_speed=None, region=RD,
        minutes=15,
        notes=["The save is a GameFAQs save (Nassaro30) decrypted from its SD export; File 3 was moved from the "
               "Endgame back to 4-P in the app's save code. If File 3 does not load or 4-P misbehaves "
               "before the split, fail the first check and note what you saw: that is the save edit, not "
               "army switching.",
               "Changes: {handover}. Test only: 4-P's split also collects force 5, because the save is from "
               "after the Endgame merge."]),
    Scenario(
        "L1", "Radiant Dawn: locked controls", "Object flags on a Radiant Dawn map",
        "Build > Object flags… on RD (kept read-only until these bits behave as on Path of Radiance)",
        steps=["Skip the opening talk with Start.",
               "Look over the whole map: scroll with the C-stick or move the cursor to each corner."],
        checks=[f"{where.capitalize()}: not drawn ({name}: {field} bit 0x{mask:02X})."
                for name, field, mask, where in FLAG_TESTS]
        + ["The rest of the town looks as usual (houses, fences, stairs, water).",
           "The game keeps running for a full player and enemy phase (no freeze)."],
        build=build_l1, chapter="0101", difficulty="Hard", anim_speed=None, region=RD, minutes=5,
        notes=[RD_JUMP_NOTE,
               "Three props of the Prologue map each get one flag bit: Do not draw (flags B 0x01) on the "
               "boats, Start hidden (flags B 0x02) on the carts, Do not draw at runtime (effect 0x40) on "
               "the market stall."]),
    Scenario(
        "L2", "Radiant Dawn: tutorial slots", "Tutorials: retail baseline on Normal",
        "Tutorials > start flags on RD: does a Normal game show tutorials at all after the chapter jump?",
        steps=TUTORIAL_STEPS,
        checks=["A tutorial window opens by itself in the first minute of the map (write what it is about "
                "in the note)."],
        build=None, chapter="0101", difficulty="Normal", anim_speed=None, region=RD, minutes=3,
        notes=[RD_JUMP_NOTE, "No change: this is the control for L3-L6. If no tutorial opens here, skip "
               "L3-L6 (s) and say so in the note."]),
    *(Scenario(
        f"L{slot + 3}", "Radiant Dawn: tutorial slots", f"Tutorials: everything learned in slot {slot + 1}",
        f"Tutorials > start flags on RD: which slot a Normal game reads (slot {slot + 1} set to "
        "unlocked + learned for every tutorial)",
        steps=TUTORIAL_STEPS,
        checks=[f"The tutorial window from L2 does NOT open (pass = slot {slot + 1} is the one a Normal game "
                "reads; fail = it still opens)."],
        build=tutorial_slot_build(slot), chapter="0101", difficulty="Normal", anim_speed=None, region=RD,
        minutes=3, notes=[RD_JUMP_NOTE, f"{TUTORIAL_FILE}: every tutorial's start flags get 3 (unlocked + "
                                         f"learned) in slot {slot + 1}; the other slots keep their retail "
                                         "values."])
      for slot in range(4)),
]

NOT_COVERED = [
    ("Army switching between two later Part 4 chapters (4-2 onwards)",
     "A1 covers the hand-over at 4-P's end; the others use the same generated TEAM_<id>_ED functions."),
    ("RD map flags in Map settings (capacity extras, other map flags)",
     "Read-only on RD for the same reason as object flags, but no flag has a visible effect to test without "
     "the RFEE01 loader traced."),
    ("Tutorial slots on Hard (tut_data_h_en.bin)",
     "Run after L3-L6: the Hard file has the same retail pattern, so the slot found on Normal is checked "
     "there next."),
]


def by_id() -> dict[str, Scenario]:
    return {s.id: s for s in SCENARIOS}
