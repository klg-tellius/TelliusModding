"""Checks for the wiki lessons' features that had none yet (PoR chapter 1, bmap02, jump on Hard).

* NC1 (lesson 10): a new character (Game Data › New, a copy of Oscar) deployed in Oscar's place is on the map.
* SK1 (18): Ike given Astra (SID_STARTRICK) with Game Code's Astra chance +100: his attack hurts much more.
* DF1 (20): ChapterData's enemy bonus levels +5: the enemies come out stronger (more HP in RAM).
* BQ1 (14): the boss's battle quote (chapter 1's messages in capitals) shows when Ike attacks Zawanar.
* AIS1 (43-44): the AI script SEQ_ALLUNITATTACK100 made SEQ_NOATTACK's: nobody is attacked in enemy phase 1.
* ZN1 (66): a one-tile player zone added north of Ike (script_zones.add_zone) gives him a Silver Sword
  when he moves onto it and waits.
* RF1 (32): the z01 reinforcement moved to a new tile, deployed by an event: it appears on the new tile.
* LY1 (39): inline code: the top/bottom talks ($R上下会話) switched to the no-background layout.
* BG1 (38): Add New Background (flat magenta, RID_INGAME_CHECK) shown by an event with RectBuild.
* DB1 (60): Game Code's debug menus: the map pause menu holds more entries.
"""
from __future__ import annotations

import time

from .checks_code import BATTLE, attack_play
from .core import Check, Jump
from .oracles import magenta_pixels, region_diff
from .ram_view import GameRam

START = Jump(2)
IKE = (12, 17)
NORTH = (12, 16)


def _dispos_h(ctx):
    return {n: d for n, d in ctx.dispos("bmap02").items() if n == "dispos_h.bin"}


def _edit_c02(ctx, edit):
    from fe_modding import script_sources
    script = script_sources.load(ctx.project, script_sources.chapter_script(ctx.project, "02"))
    script_sources.save(ctx.project, script, edit(script.source))


def on_turn_one(body: str, name: str) -> str:
    lines = "\n".join("    " + line for line in body.strip().splitlines())
    return f'\n\n# In-game check\n@on_phase(turn_from=1, turn_to=1, phase="player")\ndef {name}():\n{lines}\n'


# -- NC1 ------------------------------------------------------------------------------------------------------------

def fixture_new_character(ctx):
    from fe_modding.formats import dispo, fe8data
    oscar = ctx.character("PID_OSCAR")
    data, index = fe8data.add_record(ctx.fe8, "character", "PID_INGAME_HERO", copy_from=oscar.index)
    ctx.fe8 = data
    field = dispo.FIELD
    docs = _dispos_h(ctx)
    for doc in docs.values():
        for section in doc.sections:
            for unit in section.units:
                if unit[field["pid"]] == "PID_OSCAR":
                    unit[field["pid"]] = "PID_INGAME_HERO"
    ctx.write_dispos("bmap02", docs)
    ctx.facts.update(change=f"PID_INGAME_HERO (record {index}, a copy of Oscar) deployed in Oscar's place")


def play_units(driver, facts):
    driver.to_player_phase(8)
    game = GameRam(driver.ram, driver.build.game_id)
    return {"units": [[u.pid, u.x, u.y, u.hp, u.level] for u in game.units()], "shot": str(driver.snap("map"))}


def judge_new_character(mod, retail, facts):
    pids = {u[0] for u in mod["units"]}
    ok = "PID_INGAME_HERO" in pids and "PID_OSCAR" not in pids and "PID_OSCAR" in {u[0] for u in retail["units"]}
    return ok, f"{facts['change']}: on the map: {'PID_INGAME_HERO' in pids}; Oscar still there: {'PID_OSCAR' in pids}"


# -- SK1 / BQ1 (the menu-driven attack, on a bandit or on the boss) ------------------------------------------------

def _move_enemy(ctx, pid: str, at=NORTH, index: int = 0):
    from fe_modding.formats import dispo
    field = dispo.FIELD
    docs = _dispos_h(ctx)
    for doc in docs.values():
        units = [u for s in doc.sections if s.name.endswith("_first_h") for u in s.units if u[field["pid"]] == pid]
        unit = units[index]
        for key in ("pos", "pos2"):
            unit[field[f"{key}_x"]], unit[field[f"{key}_y"]] = at
    ctx.write_dispos("bmap02", docs)


def setup_bandit_no_crit(ctx):
    """A bandit north of Ike; the Iron Sword always hits and never crits (crit 0, so damage is steady)."""
    from fe_modding.formats import fe8data
    sword = next(i for i in ctx.data.items if i.iid == "IID_IRONSWORD")
    ctx.fe8 = fe8data.patch_item_field(ctx.fe8, sword.index, "hit", 255)
    _move_enemy(ctx, "PID_BANDIT_MOU", index=3)          # the one at (7, 16), as K2
    ctx.set_code("combat.no_crits")


def fixture_astra(ctx):
    slot = ctx.character("PID_IKE").sids.index(None)
    ctx.set_character("PID_IKE", **{f"sid{slot}": "SID_STARTRICK"})
    ctx.set_code("proc.astra.bonus", 100)
    ctx.facts.update(change="Ike given SID_STARTRICK (Astra), Astra chance +100")


def judge_astra(mod, retail, facts):
    lost_r = retail["before"]["target_hp"] - retail["target_hp_after"]
    lost_m = mod["before"]["target_hp"] - mod["target_hp_after"]
    ok = lost_m > lost_r * 1.5 or (mod["target_hp_after"] == 0 < retail["target_hp_after"])
    return ok, f"{facts['change']}: the bandit lost {lost_m} HP (retail {lost_r}; Astra strikes five times)"


def setup_boss(ctx):
    _move_enemy(ctx, "PID_ZAWANAR")


def fixture_caps_c02(ctx):
    from .checks_chapters import dialogue_upper
    dialogue_upper("c02.m")(ctx)
    ctx.facts.update(change=f"{ctx.facts['changed']} chapter 1 messages in capitals (the boss's quote among them)")


def judge_boss_quote(mod, retail, facts):
    from .checks_code import frames_differ
    share = frames_differ(mod, retail, 0, 9)
    return share > 0.01, f"{facts['change']}: the battle's frames (its quote first) differ from retail by up to {share:.1%}"


# -- DF1 ------------------------------------------------------------------------------------------------------------

def fixture_bonus_levels(ctx):
    from fe_modding.formats import fe8data
    record = ctx.chapter_record(2)
    raw = ctx.fe8
    for i in range(4):
        old = raw[record.offset + 0x3D + i]
        ctx.fe8 = fe8data.patch_chapter_field(ctx.fe8, record.index, f"enemy_bonus_level{i}", min(255, old + 5))
    ctx.facts.update(change="chapter 1 enemy bonus levels +5 on every difficulty")


def judge_bonus_levels(mod, retail, facts):
    def enemies(obs):
        return [u for u in obs["units"] if u[0].startswith(("PID_BANDIT", "PID_ZAWANAR"))]
    hp_r, hp_m = sum(u[3] for u in enemies(retail)), sum(u[3] for u in enemies(mod))
    return hp_m > hp_r, f"{facts['change']}: enemy HP on the map {hp_m} (retail {hp_r})"


# -- AIS1 -----------------------------------------------------------------------------------------------------------

def fixture_ai_script(ctx):
    from fe_modding.formats import cp_data
    from fe_modding.game_profile import files_root_of
    path = files_root_of(ctx.project) / "cp_data.bin"
    doc = cp_data.parse_cp_data(path.read_bytes())
    sections = {s.name: s for s in doc.sections}
    script = cp_data.read_script(sections["SEQ_NOATTACK"])
    cp_data.write_script(sections["SEQ_ALLUNITATTACK100"], script)
    ctx.project.write_keeping_original(path, cp_data.build_cp_data(doc))
    ctx.facts.update(change="AI script SEQ_ALLUNITATTACK100 replaced by SEQ_NOATTACK's")


def play_first_enemy_phase(driver, facts):
    driver.to_player_phase(8)
    game = GameRam(driver.ram, driver.build.game_id)
    side = {"PID_IKE", "PID_OSCAR", "PID_BOLE", "PID_TIAMAT"}
    before = {u.pid: u.hp for u in game.units() if u.pid in side}
    driver.end_turns = True
    driver.until(lambda s: s.turn >= 2 and "E_BMapPlph" in s.names, 8, label="turn 2")
    after = {u.pid: u.hp for u in game.units() if u.pid in side}
    return {"lost": sum(before[p] - after.get(p, 0) for p in before), "shot": str(driver.snap("turn2"))}


def judge_no_attack(mod, retail, facts):
    return mod["lost"] == 0 and retail["lost"] > 0, (f"{facts['change']}: HP the player's units lost in enemy "
                                                     f"phase 1: edited {mod['lost']}, retail {retail['lost']}")


# -- ZN1 ------------------------------------------------------------------------------------------------------------

def fixture_zone(ctx):
    from fe_modding.formats.cmb import script_zones

    def edit(source):
        source, name = script_zones.add_zone(source, script_zones.AREA, (*NORTH, *NORTH), "player", None,
                                             name="CheckZone")
        return source.replace(f"def {name}():\n    pass",
                              f'def {name}():\n    UnitAddItem(UnitGetByPID("PID_IKE"), "IID_SILVERSWORD")', 1)
    _edit_c02(ctx, edit)
    ctx.facts.update(change=f"player zone {NORTH} added: it gives Ike a Silver Sword")


def play_step_north(driver, facts):
    """Select Ike (the cursor starts on him), move one tile up, then Wait (the menu's last line)."""
    driver.to_player_phase(8)
    for button in ("A", "Up", "A"):
        driver.press(button, gap=1.2)
    time.sleep(1.5)
    driver.press("Up", gap=0.8)          # the action menu wraps: Up reaches Wait
    driver.press("A", gap=1.5)
    driver.until(lambda s: "E_BMapPlph" in s.names and not s.names & {"E_Event", "E_Menu", "E_Talk"}
                 and time.time() - driver.since > 2, 3, policy=False, label="after the move")
    ike = GameRam(driver.ram, driver.build.game_id).unit("PID_IKE")
    return {"tile": [ike.x, ike.y], "items": [i[0] for i in ike.items], "shot": str(driver.snap("moved"))}


def judge_zone(mod, retail, facts):
    ok = tuple(mod["tile"]) == NORTH and "IID_SILVERSWORD" in mod["items"] and "IID_SILVERSWORD" not in retail["items"]
    return ok, f"{facts['change']}: Ike on {tuple(mod['tile'])} with {mod['items']} (retail on {tuple(retail['tile'])} with {retail['items']})"


# -- RF1 ------------------------------------------------------------------------------------------------------------

RF_TILE = (10, 13)


def setup_deploy_z01(ctx):
    ctx.append_chapter_script(2, on_turn_one('Dispos("bmap02_z01_h")', "CheckReinforcements"))


def fixture_move_z01(ctx):
    from fe_modding.formats import dispo
    field = dispo.FIELD
    docs = _dispos_h(ctx)
    for doc in docs.values():
        unit = next(s for s in doc.sections if s.name.endswith("_z01_h")).units[0]
        old = (unit[field["pos_x"]], unit[field["pos_y"]])
        for key in ("pos", "pos2"):
            unit[field[f"{key}_x"]], unit[field[f"{key}_y"]] = RF_TILE
    ctx.write_dispos("bmap02", docs)
    ctx.facts.update(change=f"the z01 reinforcement moved from {old} to {RF_TILE}")


def judge_reinforcement(mod, retail, facts):
    at = [u for u in mod["units"] if (u[1], u[2]) == RF_TILE and u[0].startswith("PID_BANDIT")]
    there = [u for u in retail["units"] if (u[1], u[2]) == RF_TILE and u[0].startswith("PID_BANDIT")]
    return bool(at) and not there, f"{facts['change']}: a bandit on {RF_TILE}: edited {bool(at)}, retail {bool(there)}"


# -- LY1 / BG1 ------------------------------------------------------------------------------------------------------

def fixture_layout(ctx):
    from fe_modding.formats import message
    from fe_modding.game_profile import files_root_of
    path = files_root_of(ctx.project) / "Mess" / "c02.m"
    old, new = "上下会話".encode("shift_jis"), "背景なし会話".encode("shift_jis")
    messages = message.read_messages_path(path)
    changed = []
    for m in messages:
        raw = m.text.encode(message.ENCODING)
        if b"$R" + old + b"|" in raw:
            changed.append(message.Message(m.speaker, raw.replace(b"$R" + old + b"|", b"$R" + new + b"|")
                                           .decode(message.ENCODING)))
        else:
            changed.append(m)
    ctx.project.write_keeping_original(path, message.write_messages(changed))
    ctx.facts.update(change=f"{sum(a.text != b.text for a, b in zip(messages, changed))} talks: layout 上下会話 -> 背景なし会話")


def play_talks(driver, facts):
    """Screenshots of every talk window of the opening (no input until each has its text)."""
    shots, k = [], 0
    deadline = time.time() + 240
    while time.time() < deadline and k < 6:
        try:
            driver.until(lambda s: any(n.startswith("E_TalkKeyWait") for n in s.names), 2, policy=False, label="talk")
        except Exception:  # noqa: BLE001 - no more talks
            break
        time.sleep(0.8)
        shots.append(str(driver.snap(f"talk_{k}")))
        k += 1
        driver.press("A", gap=1.0)
    return {"shots": shots, "shot": shots[0] if shots else ""}


def judge_layout(mod, retail, facts):
    shares = [region_diff(a, b) for a, b in zip(retail["shots"], mod["shots"])]
    return bool(shares) and max(shares) > 0.05, (f"{facts['change']}: the opening's talk windows differ from retail "
                                                 f"by up to {max(shares, default=0):.0%} (talk_*.png)")


def fixture_background(ctx):
    from PIL import Image
    from fe_modding.formats import rect
    from fe_modding.game_profile import files_root_of
    files = files_root_of(ctx.project)
    doc = rect.read_rect_file(files / "s" / "rect.bin")
    rect.add_background(doc, files, "RID_INGAME_CHECK", [Image.new("RGB", (640, 480), (255, 0, 255))])
    rect.write_rect_file(doc, files / "s" / "rect.bin")
    ctx.facts.update(change="RID_INGAME_CHECK (flat magenta) added and shown with RectBuild")


def setup_show_background(ctx):
    ctx.append_chapter_script(2, on_turn_one('RectBuild("RID_INGAME_CHECK")\nWaitM(5000)', "CheckBackground"))


def play_watch_magenta(driver, facts):
    """Sample the screen every 1.5 s from the map's start until the first free player phase."""
    best, k = 0, 0
    deadline = time.time() + 300
    while time.time() < deadline:
        st = driver.state()
        if "E_BMapMain" in st.names:
            path = driver.snap(f"watch_{k % 4}")
            k += 1
            if path:
                best = max(best, magenta_pixels(str(path)))
            if "E_BMapPlph" in st.names and not st.names & {"E_Event", "E_Rect"} and k > 6:
                break
        else:
            driver.step(st)
        time.sleep(1.5)
    return {"best": best, "shot": str(driver.snap("end"))}


def judge_background(mod, retail, facts):
    return mod["best"] > 20000 and retail["best"] < 2000, (f"{facts['change']}: up to {mod['best']} magenta pixels "
                                                          f"on screen (retail {retail['best']})")


# -- DB1 ------------------------------------------------------------------------------------------------------------

def play_pause_menu(driver, facts):
    driver.to_player_phase(8)
    driver.press("Minus", gap=1.5)       # PoR map menu (Z)
    return {"shot": str(driver.snap("pause_menu"))}


CHECKS = [
    Check("NC1", "por", "A new character deployed in a chapter is on the map", ["lesson 10 Create a character"],
          play=play_units, judge=judge_new_character, fixture=fixture_new_character, start=START),
    Check("SK1", "por", "A skill given to Ike activates in a fight (Astra)", ["lesson 18 Skills", "Game Code proc rows"],
          play=attack_play(), judge=judge_astra, setup=setup_bandit_no_crit, fixture=fixture_astra, start=START),
    Check("DF1", "por", "Enemy bonus levels make the enemies stronger", ["lesson 20 Difficulty and armies"],
          play=play_units, judge=judge_bonus_levels, fixture=fixture_bonus_levels, start=START),
    Check("BQ1", "por", "The boss's battle quote shows edited text", ["lesson 14 Recruitment and bosses"],
          play=attack_play("PID_IKE", NORTH), judge=judge_boss_quote, setup=setup_boss, fixture=fixture_caps_c02,
          start=START),
    Check("AIS1", "por", "An edited AI script: the bandits attack nobody", ["lessons 43-45 AI language"],
          play=play_first_enemy_phase, judge=judge_no_attack, fixture=fixture_ai_script, start=START, minutes=12),
    Check("ZN1", "por", "A script zone added on the map fires when Ike steps in", ["lesson 66 Script zones"],
          play=play_step_north, judge=judge_zone, fixture=fixture_zone, start=START),
    Check("RF1", "por", "A reinforcement moved to a new tile appears there", ["lesson 32 Reinforcements"],
          play=play_units, judge=judge_reinforcement, setup=setup_deploy_z01, fixture=fixture_move_z01, start=START),
    Check("LY1", "por", "An inline talk-layout code changes the talk window", ["lesson 39 Inline text"],
          play=play_talks, judge=judge_layout, fixture=fixture_layout, start=START),
    Check("BG1", "por", "Add New Background, shown by an event", ["lesson 38 Backgrounds", "1.0 §4 Backgrounds"],
          play=play_watch_magenta, judge=judge_background, setup=setup_show_background, fixture=fixture_background,
          start=START, minutes=10),
    Check("DB1", "por", "Debug menus in the map pause menu", ["lesson 60 Debug menus"], play=play_pause_menu,
          judge=lambda m, r, f: (region_diff(r["shot"], m["shot"]) > 0.02,
                                 f"the pause menu differs from retail on {region_diff(r['shot'], m['shot']):.1%}"),
          fixture=lambda ctx: ctx.set_code("dev.pause_menus"), start=START),
]
