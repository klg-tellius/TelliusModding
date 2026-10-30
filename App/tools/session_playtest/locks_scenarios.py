"""The in-game checks that keep Radiant Dawn controls locked (``build --set locks``).

Each test settles one thing the app still refuses to edit or labels vaguely on RFEE01:

- L1: Build › Object flags on Radiant Dawn maps. The flag bits are Path of Radiance's traced meanings
  (research/rd/MAP_NOTES.md); the app keeps the dialog read-only on RD (``MapEditor.verified_us_map_layout``)
  until the visible ones behave the same in game.
- L2-L6: the four start-flag slots of RD's ``Tutorial/tut_data_*.bin`` (Tutorials editor, "Slot 1-4",
  ``RADIANT_DAWN_PROFILE.tutorial_flag_names``). Retail Normal English entries are ``(0, 2, 2, 0)``;
  marking every tutorial learned in one slot shows whether a Normal game reads that slot.

Army switching (the story flow's Army combo, ``rd_armies``) is not here yet: it needs a save from
Part 4 (NOT_COVERED).
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


TUTORIAL_STEPS = ["Skip the opening talk with Start. When the map appears, wait a few seconds without "
                  "pressing anything, then move Micaiah once.",
                  "Note whether a tutorial window (a help box explaining the controls) opens by itself."]

SCENARIOS: list[Scenario] = [
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
    ("Story flow › Army on RD (rd_armies: startup.cmb TEAM_<id>_ED hand-overs, ChapterData +0x8F/+0xA4)",
     "The chapter jump starts a fresh party with none of Part 4's units, and the only RD save here is a "
     "Part 1 start. Needs a save taken at the base before 4-1 (or anywhere in Part 4): then 4-1 set to "
     "Micaiah's army should open with the Silver Army on the Greil Army's map."),
    ("RD map flags in Map settings (capacity extras, other map flags)",
     "Read-only on RD for the same reason as object flags, but no flag has a visible effect to test without "
     "the RFEE01 loader traced."),
    ("Tutorial slots on Hard (tut_data_h_en.bin)",
     "Run after L3-L6: the Hard file has the same retail pattern, so the slot found on Normal is checked "
     "there next."),
]


def by_id() -> dict[str, Scenario]:
    return {s.id: s for s in SCENARIOS}
