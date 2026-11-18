"""Radiant Dawn save edits loaded by the game and kept through its own save (SAVE-02/05/07, RD Units tab).

Every check starts from the chapter sweep's save that continues into 1-1 (``003_chapter02``), edited
through ``save_file_fe10`` as the Saves page does (the retail run loads the same file unedited). The
game loads it from the title, plays to 1-1's first player phase (units read from RAM), ends the turn
(1-1 is won by an appended victory) and writes its chapter-end save, which is read back.
"""
from __future__ import annotations

from .core import SWEEP_SAVES, Check
from .ram_view import GameRam

START_SAVE = SWEEP_SAVES["rd"] / "003_chapter02_FE10_US.dat"
CHAPTER = "0102"
TEST_FLAG = 127


def _setup_for(chapter):
    def setup(ctx):
        from tools.chapter_sweep.build import add_auto_win
        add_auto_win(ctx.project, chapter)
    return setup


def _first_file(save):
    return next(r for r in save.active_records() if not r.checkpoint and r.logical_slot is not None)


def _support_counts(project, record):
    return record.support_slot_counts_from_fe10data(project.read_logical("game_data"))


def _unit(record, counts, pid):
    number = record.id_of("character", pid)
    return next(u for u in record.unit_records(counts) if not u.empty and u.person_number == number)


def _edited_card(edit, start=START_SAVE):
    """card(ctx, variant): the start save, edited by ``edit(ctx, record)`` in the mod run only."""
    def card(ctx, variant):
        from fe_modding.formats import save_file_fe10 as sf
        save = sf.SaveFile.from_bytes(start.read_bytes())
        record = _first_file(save)
        if variant == "mod":
            edit(ctx, record)
        return {"FE10_US.dat": save.to_bytes([record])}
    return card


# -- edits ---------------------------------------------------------------------------------------------

def edit_unit(ctx, record):
    """Micaiah: class Light Sage, an Elixir in a free slot, one more skill, Edward support at C."""
    from fe_modding.formats import fe8data, fe10data, save_file_fe10 as sf
    counts = _support_counts(ctx.project, record)
    unit = _unit(record, counts, "PID_MICAIAH")
    record.set_unit_class(unit, record.id_of("class", "JID_LIGHTSAGE"))
    free = next(i.slot for i in unit.items if i.item_number == 0)
    record.set_unit_item(unit, free, record.id_of("item", "IID_ELIXIR"), 3, 0)
    unit = _unit(record, counts, "PID_MICAIAH")
    owned = {s.skill_number for s in unit.skills}
    skill = next(n for n in (record.id_of("skill", s) for s in ("SID_PARAGON", "SID_ADEPT", "SID_RESOLVE"))
                 if n not in owned)
    record.set_unit_skills(unit, [*unit.skills, sf.SavedSkill(skill, 2, 0)])
    data = ctx.project.read_logical("game_data")
    micaiah = next(r for r in fe10data.read_fe10data(data).table("support") if r.id == "PID_MICAIAH")
    slot = next(k for k, (partner, _f, _s) in enumerate(micaiah.lists["partners"]) if partner == "PID_EDDIE")
    threshold = data[fe8data.section_start(data, "RelianceParam")]
    unit = _unit(record, counts, "PID_MICAIAH")
    record.set_unit_support_points(unit, slot, threshold)
    names = record.id_name_lists()
    ctx.facts.update(skill=names["skill"][skill], support_slot=slot, support_points=threshold, item_slot=free)


def edit_convoy(ctx, record):
    free = next(i.slot for i in record.convoy_items() if i.item_number == 0)
    record.set_convoy_item(free, record.id_of("item", "IID_IRONSWORD"), 46 << 8)
    ctx.facts.update(convoy_slot=free)


def edit_copy_remove(ctx, record):
    counts = _support_counts(ctx.project, record)
    slot = record.copy_unit(_unit(record, counts, "PID_EDDIE"), counts)
    names = record.id_name_lists()
    # a unit inside its army list (not the first) and in no rescue pair, which Remove accepts
    target = next(u for u in record.unit_records(counts) if not u.empty and u.linked_slots[0]
                  and not u.linked_slots[2] and u.slot != slot
                  and names["character"][u.person_number - 1] not in ("PID_MICAIAH", "PID_EDDIE"))
    removed = names["character"][target.person_number - 1]
    record.remove_unit(target, counts)
    ctx.facts.update(copy_slot=slot, removed=removed)


def edit_flag(ctx, record):
    record.set_script_flag(TEST_FLAG, True)


# -- play ------------------------------------------------------------------------------------------------

def play_and_resave(driver, facts):
    """Load the file, observe 1-1's units, win, and read the save the game writes at the chapter end."""
    from fe_modding.formats import save_file_fe10 as sf
    driver.to_player_phase(8)
    game = GameRam(driver.ram, "RFEE01")
    obs = {"party": game.party(), "units": [], "shot": str(driver.snap("map"))}
    for u in game.units():
        obs["units"].append({"pid": u.pid, "jid": u.jid, "items": [i[0] for i in u.items],
                             "skills": game.skills(u)})
    driver.end_turns = True
    driver.until(lambda s: driver.save_count >= 1 and s.chapter != obs["party"]["chapter"], 10, label="chapter save")
    saved = sorted((driver.out / "saves").glob("*"))[-1]
    save = sf.SaveFile.from_bytes(saved.read_bytes())
    record = _first_file(save)
    names = record.id_name_lists()
    from fe_modding.project import ModProject  # noqa: F401  (support counts need FE10Data)
    data = (driver.run / "files" / "FE10Data.cms").read_bytes()
    from fe_modding.formats import lz10
    counts = record.support_slot_counts_from_fe10data(lz10.decompress(data))
    units = []
    for u in record.unit_records(counts):
        if u.empty:
            continue
        units.append({"slot": u.slot, "pid": names["character"][u.person_number - 1],
                      "jid": names["class"][u.class_number - 1] if u.class_number else "",
                      "items": [names["item"][i.item_number - 1] for i in u.items if i.item_number],
                      "skills": [names["skill"][s.skill_number] for s in u.skills],
                      "supports": list(u.support_points)})
    obs["saved"] = {"file": saved.name, "units": units,
                    "convoy": [names["item"][c.item_number - 1] for c in record.convoy_items() if c.item_number],
                    "flag": record.script_flags()[TEST_FLAG]}
    return obs


# -- judges ----------------------------------------------------------------------------------------------

def _ram(obs, pid):
    return next(u for u in obs["units"] if u["pid"] == pid)


def _saved(obs, pid):
    return [u for u in obs["saved"]["units"] if u["pid"] == pid]


def judge_unit(mod, retail, facts):
    ram, keep = _ram(mod, "PID_MICAIAH"), _saved(mod, "PID_MICAIAH")[0]
    problems = []
    if ram["jid"] != "JID_LIGHTSAGE" or _ram(retail, "PID_MICAIAH")["jid"] == "JID_LIGHTSAGE":
        problems.append(f"RAM class {ram['jid']}")
    if "IID_ELIXIR" not in ram["items"]:
        problems.append(f"RAM items {ram['items']}")
    if facts["skill"] not in ram["skills"]:
        problems.append(f"RAM skills {ram['skills']}")
    if keep["jid"] != "JID_LIGHTSAGE" or "IID_ELIXIR" not in keep["items"] or facts["skill"] not in keep["skills"]:
        problems.append(f"re-saved {keep['jid']} {keep['items']} {keep['skills']}")
    if keep["supports"][facts["support_slot"]] < facts["support_points"]:
        problems.append(f"re-saved support {keep['supports']}")
    if problems:
        return False, "; ".join(problems)
    return True, (f"in game: Light Sage, Elixir, {facts['skill']}; re-saved by the game with them and "
                  f"Edward support {keep['supports'][facts['support_slot']]} (set {facts['support_points']})")


def judge_convoy(mod, retail, facts):
    a, b = retail["saved"]["convoy"].count("IID_IRONSWORD"), mod["saved"]["convoy"].count("IID_IRONSWORD")
    return b == a + 1, f"Iron Swords in the re-saved convoy: retail {a}, edited {b}"


def judge_copy_remove(mod, retail, facts):
    gone = facts["removed"]
    eddies, left = len(_saved(mod, "PID_EDDIE")), len(_saved(mod, gone))
    base = len(_saved(retail, "PID_EDDIE"))
    ok = eddies == base + 1 and left == 0 and not any(u["pid"] == gone for u in mod["units"])
    return ok, f"re-saved: {eddies} Edward records (retail {base}), {left} {gone} (removed); map: " \
               f"{sum(u['pid'] == 'PID_EDDIE' for u in mod['units'])} Edward on the map"


def judge_flag(mod, retail, facts):
    return mod["saved"]["flag"] and not retail["saved"]["flag"], \
        f"flag {TEST_FLAG} after the game's save: edited {mod['saved']['flag']}, retail {retail['saved']['flag']}"


def _check(cid, title, covers, edit, judge, start=START_SAVE, chapter=CHAPTER):
    return Check(cid, "rd", title, covers, play=play_and_resave, judge=judge, setup=_setup_for(chapter),
                 card=_edited_card(edit, start), minutes=12)


CHECKS = [
    _check("S1", "Class, item, skill and support edits load and survive the game's save",
           ["SAVE-07", "rdcheck R3 (points)", "1.0 §5 Saves RD (unit item)"], edit_unit, judge_unit),
    _check("S2", "An Iron Sword added to the convoy is kept", ["SAVE-05 convoy", "1.0 §5 Saves RD ⭐ convoy"],
           edit_convoy, judge_convoy),
    _check("S6", "Copy to new slot and Remove on the RD Units tab", ["RD Units tab Copy/Remove"],
           edit_copy_remove, judge_copy_remove, SWEEP_SAVES["rd"] / "005_chapter04_FE10_US.dat", "0104"),
    _check("S8", "An event flag survives the game's own save", ["rdcheck R2", "SAVE-02"], edit_flag, judge_flag),
]


# -- Start a chapter from its opening (SAVE-05): the 1-1 file made to start 1-4 ---------------------------------

TARGET = "C0105"      # I:4-A Distant Voice


def edit_start_chapter(ctx, record):
    """What Saves › Start a chapter from its opening… does for ``TARGET``."""
    from fe_modding.formats import fe10data
    database = fe10data.read_fe10data(ctx.project.read_logical("game_data"))
    chapters = sorted((r for r in database.table("chapter") if r.values.get("number")), key=lambda r: r.values["number"])
    chosen = next(i for i, r in enumerate(chapters) if r.values["cid"] == TARGET)
    target, before = chapters[chosen], chapters[chosen - 1]
    affinity = next((r.index for r in database.table("affinity")
                     if r.values.get("affinity") == target.values.get("affinity")), 0)
    record.start_at_chapter(target.values["number"], before.values.get("map") or target.values["map"], affinity)
    ctx.facts.update(target=TARGET, number=target.values["number"])


def play_start(driver, facts):
    st = driver.to_player_phase(10)
    return {"chapter": st.chapter, "shot": str(driver.snap("map"))}


def judge_start(mod, retail, facts):
    ok = mod["chapter"] == facts["number"] and retail["chapter"] != facts["number"]
    return ok, f"the file starts chapter {mod['chapter']} (asked {facts['target']} = {facts['number']}); " \
               f"the unedited file starts {retail['chapter']}"


CHECKS.append(Check("S3", "rd", "Start a chapter from its opening: the 1-1 file starts 1-4",
                    ["SAVE-05 move_to_chapter / start_at_chapter"], play=play_start, judge=judge_start,
                    setup=_setup_for("0105"), card=_edited_card(edit_start_chapter), minutes=12))
