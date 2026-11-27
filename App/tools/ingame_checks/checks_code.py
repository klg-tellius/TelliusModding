"""Game Code rows seen in a fight (1.0 checklist section 5).

Both runs append one event to the first map, at the start of player phase 1: the attacker gets 99
EXP, then fights the defender with ``NetuzoBattle`` with its first strike forced to a critical that can't
kill (``NetuzoSet(0, 2, 0x400)``) and the defender's counter forced to miss. Both runs force random
growth. The edited run also sets the critical multiplier to 2 (retail 3) and every "gain per growth
success" to 3 (retail 1).

Judged from RAM once the player phase is free: the defender's HP loss must be exactly 2/3 of the
retail run's, and the attacker's level-up must have raised its stats only by 0 or 3 (retail: 0 or 1).
"""
from __future__ import annotations

from pathlib import Path

from .core import ROOT, Check, Jump
from .ram_view import GameRam

NEW_MULTIPLIER = 2
GAIN = 3

EVENT = '''
# In-game check: a scripted battle with a forced critical and a level-up
@on_phase(turn_from=1, turn_to=1, phase="player")
def CheckForcedCritical():
    UnitSetEXP(UnitGetByPID("{attacker}"), 99)
    NetuzoInit()
    NetuzoSet(0, 2, 1024)
    NetuzoSet(1, 4, 0)
    NetuzoSet(2, 4, 1024)
    NetuzoSet(3, 4, 1024)
    NetuzoBattle(UnitGetByPID("{attacker}"), UnitGetByPID("{defender}"), 0)
'''


def setup_for(chapter, attacker, defender, wii):
    def setup(ctx):
        ctx.append_chapter_script(chapter, EVENT.format(attacker=attacker, defender=defender))
        ctx.set_code("rd.growth.force_random" if wii else "growth.force_random")
    return setup


def fixture_for(wii):
    def fixture(ctx):
        if wii:
            ctx.set_code("rd.combat.crit_multiplier", NEW_MULTIPLIER) if "rd.combat.crit_multiplier" in _ids() \
                else ctx.set_code("combat.crit_multiplier", NEW_MULTIPLIER)
            for stat in range(8):
                ctx.set_code(f"rd.growth.random.{stat}", GAIN)
        else:
            ctx.set_code("combat.crit_multiplier", NEW_MULTIPLIER)
            for stat in range(8):
                ctx.set_code(f"growth.random.{stat}", GAIN)
    return fixture


def _ids():
    from fe_modding.game_code import entries, entries_fe10  # noqa: F401
    from fe_modding.game_code.catalog import CATALOG
    return CATALOG.entries


def play_for(attacker, defender):
    def play(driver, facts):
        game = GameRam(driver.ram, driver.build.game_id)

        def defender_on_map(_state):
            try:
                return game.unit(defender).hp > 0
            except (KeyError, OSError, ValueError):
                return False
        driver.until(defender_on_map, 6, label="defender on the map")
        full_hp = game.unit(defender).hp           # before the player phase event fights
        before = game.unit(attacker)
        before = {"level": before.level, "raw": game.record(before.address, game.layout.stride).hex()}
        driver.to_player_phase(8)
        att, dfn = game.unit(attacker), game.unit(defender)
        stride = game.layout.stride
        return {"before": before, "attacker": {"level": att.level, "hp": att.hp, "raw": game.record(att.address, stride).hex()},
                "defender": {"hp": dfn.hp, "full_hp": full_hp, "raw": game.record(dfn.address, stride).hex()},
                "shot": str(driver.snap("after_battle"))}
    return play


def judge_for(wii):
    def judge(mod, retail, facts):
        lost_retail = retail["defender"]["full_hp"] - retail["defender"]["hp"]
        lost_mod = mod["defender"]["full_hp"] - mod["defender"]["hp"]
        crit_ok = lost_retail > 0 and lost_mod * 3 == lost_retail * NEW_MULTIPLIER
        text = f"forced critical: defender lost {lost_retail} HP (retail ×3), {lost_mod} (edited ×{NEW_MULTIPLIER})"
        if wii:      # the RD stat-gain bytes aren't named yet: report the level only
            return crit_ok, text + f"; attacker level {retail['attacker']['level']} / {mod['attacker']['level']}"
        def gains(obs):
            a = bytes.fromhex(obs["before"]["raw"])[0x1AB:0x1B3]
            b = bytes.fromhex(obs["attacker"]["raw"])[0x1AB:0x1B3]
            return [y - x for x, y in zip(a, b)], (obs["before"]["level"], obs["attacker"]["level"])
        (gr, lr), (gm, lm) = gains(retail), gains(mod)
        levelled = lr[1] == lr[0] + 1 and lm[1] == lm[0] + 1
        growth_ok = levelled and all(g in (0, GAIN) for g in gm) and any(gm) and all(g in (0, 1) for g in gr)
        return crit_ok and growth_ok, text + f"; level-up {lr}/{lm}, gains retail {gr}, edited {gm}"
    return judge


def _check(cid, game, chapter, attacker, defender, start):
    wii = game == "rd"
    return Check(cid, game, "Critical multiplier and growth gain rows in a scripted fight",
                 ["1.0 §5 Game Code ⭐ (combat row)", "Level-up growth rows"],
                 play=play_for(attacker, defender), judge=judge_for(wii),
                 setup=setup_for(chapter, attacker, defender, wii), fixture=fixture_for(wii), start=start)


#: Parked 2026-11-18: in both runs the fight starts (E_Netuzo, E_BattleSubProc) but the attacker gains no
#: EXP (no level-up from 99) and the defender's HP in RAM is unchanged, so a NetuzoBattle fight can't
#: show these rows. A real player attack, driven through the map menus, is the next thing to try.
PARKED = [
    _check("K1", "por", "02", "PID_IKE", "PID_BANDIT_MOU", Jump(2)),
    _check("K1r", "rd", "0101", "PID_EDDIE", "PID_GOON", Jump("0101")),
]

CHECKS: list = []


# -- a real attack driven through the menus ---------------------------------------------------------------
#
# PoR chapter 1: a bandit is moved next to Ike's start tile; Ike's Iron Sword gets 255 hit and 255 critical
# in both runs, so every strike of his is a critical; the edited run sets the critical multiplier to 1
# (retail 3). On the first player phase the driver selects Ike (the cursor starts on him), stays on his
# tile and presses A through Attack, the weapon and the target until a battle starts.

ATTACK_TILE = (12, 16)     # north of Ike's start (12, 17) in bmap02


def setup_attack(ctx):
    from fe_modding.formats import dispo
    ctx.set_character  # noqa: B018  (PoR context)
    data = ctx.fe8
    from fe_modding.formats import fe8data
    sword = next(i for i in ctx.data.items if i.iid == "IID_IRONSWORD")
    data = fe8data.patch_item_field(data, sword.index, "hit", 255)
    data = fe8data.patch_item_field(data, sword.index, "crit", 255)
    ctx.fe8 = data
    docs = {n: d for n, d in ctx.dispos("bmap02").items() if n == "dispos_h.bin"}
    field = dispo.FIELD
    for doc in docs.values():
        unit = next(u for s in doc.sections if s.name.endswith("_first_h") for u in s.units
                    if u[field["pid"]] == "PID_BANDIT_MOU" and (u[field["pos_x"]], u[field["pos_y"]]) == (7, 16))
        for key in ("pos", "pos2"):
            unit[field[f"{key}_x"]], unit[field[f"{key}_y"]] = ATTACK_TILE
    ctx.write_dispos("bmap02", docs)


def fixture_crit_one(ctx):
    ctx.set_code("combat.crit_multiplier", 1)


BATTLE = ("E_Battle", "E_Kiri", "E_BattleSubProc", "E_Netuzo", "BattleProc", "E_BtlMain")


#: battle frames per fight and the time between them: four a second, so a spell's phases are each caught in
#: both runs and frames_differ can match them whatever the timing (2026-11-24: frames a second apart caught the
#: two runs at different phases of the same spell and read that as a 22% change)
BATTLE_FRAMES = 40
BATTLE_FRAME_GAP = 0.25


#: Radiant Dawn's two battle units (attacker, defender; 0x4A0 bytes each) and their s16 raw hit, avoid and final
#: hit (research/rd/COMBAT_NOTES.md). Read once the battle process is up, before the first strike.
RD_BATTLE_UNITS = (0x803C8E80, 0x803C9320)
RD_ODDS = {"raw_hit": 0x44E, "avoid": 0x450, "hit": 0x452}


def battle_odds(driver) -> dict | None:
    """Each side's hit numbers in the starting battle (Radiant Dawn US only; None elsewhere)."""
    import struct
    if driver.build.game_id != "RFEE01":
        return None
    sides = {}
    for side, base in zip(("attacker", "defender"), RD_BATTLE_UNITS):
        raw = driver.ram.read(base + 0x44E, 6)
        sides[side] = dict(zip(RD_ODDS, struct.unpack(">3h", raw)))
    return sides


def attack_play(attacker: str = "PID_IKE", tile=ATTACK_TILE, frames: int | None = None):
    """The cursor starts on ``attacker``: A selects it, A stays, then A through Attack, weapon and target
    until a battle process appears. Observes the target's HP and the attacker's record before and after."""
    def play(driver, facts):
        import time
        game = GameRam(driver.ram, driver.build.game_id)
        stride = game.layout.stride
        driver.to_player_phase(8)
        target = next((u for u in game.units() if (u.x, u.y) == tuple(tile)), None)
        if target is None:
            driver.snap("no_target")
            raise RuntimeError(f"no unit on {tile}: {[(u.pid, u.x, u.y) for u in game.units()]}")
        me = game.unit(attacker)
        before = {"target_hp": target.hp, "level": me.level, "raw": game.record(me.address, stride).hex()}
        for stale in list((driver.out / "shots").glob("battle_*.png")) + list((driver.out / "shots").glob("quote_*.png")):
            stale.unlink()          # frames of an earlier run of this check would mix with this one's
        driver.snap("before")
        started = False
        for _ in range(8):
            driver.press("A", gap=1.5)
            if any(n.startswith(BATTLE) for n in driver.state().names):
                started = True
                break
        if not started:
            driver.snap("no_battle")
            raise RuntimeError(f"no battle started after 8 A presses ({sorted(driver.state().names)})")
        odds = battle_odds(driver)
        deadline = time.time() + 180 / driver.speed
        seen: set = set()
        frame, next_frame, quotes = 0, time.time(), 0
        while time.time() < deadline and (any(n.startswith(BATTLE) for n in driver.state().names)
                                          or not {"E_BMapPlph"} <= driver.state().names):
            names = driver.state().names
            seen |= set(names)
            talking = any(n.startswith(("E_Talk", "E_LevelUp", "E_Lvup", "E_GrowUp")) for n in names)
            # BATTLE_FRAMES frames, BATTLE_FRAME_GAP apart; none while a quote is up (a boss's quote filled every frame of
            # the RD Prologue fight, round 3)
            if time.time() >= next_frame and frame < (frames or BATTLE_FRAMES) and not talking:
                driver.snap(f"battle_{frame:03d}")
                frame, next_frame = frame + 1, time.time() + BATTLE_FRAME_GAP
            # a battle conversation (a boss's or a talk event's quote) or the level-up window waits for A
            if talking:
                if quotes < 6 and any(n.startswith("E_Talk") for n in names):   # the quote's own frames
                    time.sleep(0.6)
                    driver.snap(f"quote_{quotes:02d}")
                    quotes += 1
                driver.press("A", gap=1.0)
            time.sleep(0.5)
        time.sleep(3)
        after = next((u for u in game.units() if u.handle == target.handle), None)
        me = game.unit(attacker)
        return {"before": before, "target_hp_after": after.hp if after else 0, "battle_processes": sorted(seen),
                "odds": odds,
                "after": {"level": me.level, "raw": game.record(me.address, stride).hex()},
                "shot": str(driver.snap("after"))}
    return play


play_attack = attack_play()


def judge_attack(mod, retail, facts):
    full = retail["before"]["target_hp"]
    lost_r = full - retail["target_hp_after"]
    lost_m = mod["before"]["target_hp"] - mod["target_hp_after"]
    if lost_m <= 0:
        return False, f"edited run: the bandit lost {lost_m} HP"
    if retail["target_hp_after"] > 0:
        ok = lost_r == 3 * lost_m
        how = "exactly"
    else:                       # retail's critical killed: the edited one must be a third of enough to kill
        ok = 3 * lost_m >= full and mod["target_hp_after"] > 0
        how = "at least (retail killed it)"
    return ok, f"bandit {full} HP: lost {lost_r} with ×3 criticals, {lost_m} with ×1 ({how} a third)"


CHECKS.append(Check("K2", "por", "Critical multiplier in a real attack", ["1.0 §5 Game Code ⭐ (combat row)"],
                    play=play_attack, judge=judge_attack, setup=setup_attack, fixture=fixture_crit_one,
                    start=Jump(2)))


# -- level-up growth through the same attack ------------------------------------------------------------------
#
# Ike gets 99 EXP from an event at the start of player phase 1, so the attack levels him up (a miss still gives
# EXP). Both runs force random growth; the edited one gains 3 per successful roll (retail 1).

EXP_EVENT = '''
# In-game check: one EXP short of a level
@on_phase(turn_from=1, turn_to=1, phase="player")
def CheckExpToLevel():
    UnitSetEXP(UnitGetByPID("PID_IKE"), 99)
'''


def setup_growth(ctx):
    setup_attack(ctx)
    ctx.append_chapter_script("02", EXP_EVENT)
    ctx.set_code("growth.force_random")


def fixture_gain_three(ctx):
    for stat in range(8):
        ctx.set_code(f"growth.random.{stat}", GAIN)


def judge_growth(mod, retail, facts):
    def gains(obs):
        a = bytes.fromhex(obs["before"]["raw"])[0x1AB:0x1B3]
        b = bytes.fromhex(obs["after"]["raw"])[0x1AB:0x1B3]
        return [y - x for x, y in zip(a, b)], (obs["before"]["level"], obs["after"]["level"])
    (gr, lr), (gm, lm) = gains(retail), gains(mod)
    levelled = lr[1] == lr[0] + 1 and lm[1] == lm[0] + 1
    ok = levelled and any(gm) and all(g in (0, GAIN) for g in gm) and all(g in (0, 1) for g in gr)
    return ok, f"Ike level {lr[0]}->{lr[1]} / {lm[0]}->{lm[1]}; stat gains retail {gr}, edited (3 per success) {gm}"


CHECKS.append(Check("K3", "por", "Growth gain per success in a real level-up", ["Level-up growth rows (POR)"],
                    play=play_attack, judge=judge_growth, setup=setup_growth, fixture=fixture_gain_three,
                    start=Jump(2)))


# -- the critical attack on Radiant Dawn (Prologue: Micaiah, whom the cursor starts on) -------------------------

RD_TILE = (10, 10)          # north of Micaiah's start (10, 11) on bmap0101


def setup_attack_rd(ctx):
    from fe_modding.formats import dispo, fe10data
    from fe_modding.game_profile import files_root_of
    data = ctx.project.read_logical("game_data")
    light = next(r for r in fe10data.read_table(data, "item") if r.id == "IID_LIGHT")
    for key in ("hit", "crit"):
        data = fe10data.patch_field(data, "item", light.index, key, 255)
    ctx.project.write_logical("game_data", data)
    path = files_root_of(ctx.project) / "zmap" / "bmap0101" / "dispos_h.bin"
    doc = dispo.parse_dispo(path.read_bytes())
    field = dispo.FIELD
    unit = [u for s in doc.sections if s.name.endswith("_teki_h") for u in s.units if u[field["pid"]] == "PID_GOON"][1]
    for key in ("pos", "pos2"):
        unit[field[f"{key}_x"]], unit[field[f"{key}_y"]] = RD_TILE
    ctx.project.write_keeping_original(path, dispo.build_dispo(doc))


def fixture_crit_one_rd(ctx):
    ctx.set_code("rd.combat.crit_multiplier", 1)


CHECKS.append(Check("K2r", "rd", "Critical multiplier in a real attack", ["1.0 §5 Game Code ⭐ (combat row, RD)"],
                    play=attack_play("PID_MICAIAH", RD_TILE), judge=judge_attack, setup=setup_attack_rd,
                    fixture=fixture_crit_one_rd, start=Jump("0101")))


# -- level-up growth on Radiant Dawn: the same attack as K2r, Micaiah one EXP short of a level -------------------

RD_EXP_EVENT = EXP_EVENT.replace("PID_IKE", "PID_MICAIAH")


def setup_growth_rd(ctx):
    setup_attack_rd(ctx)
    ctx.append_chapter_script("0101", RD_EXP_EVENT)
    ctx.set_code("rd.growth.force_random")


def fixture_gain_three_rd(ctx):
    for stat in range(8):
        ctx.set_code(f"rd.growth.random.{stat}", GAIN)


#: Radiant Dawn's eight stat gains (HP .. Res) in the runtime unit, after current HP (+0x114). Seen in Dolphin
#: (K3r, 2026-11-18): a level-up raises bytes of +0x119..+0x120 only; +0x10F also rises by 1 (not a stat).
RD_STATS = range(0x119, 0x121)


def judge_growth_rd(mod, retail, facts):
    """Every stat gain that went up must have gone up by 1 in retail and by 3 in the edited run."""
    def rises(obs):
        a, b = bytes.fromhex(obs["before"]["raw"]), bytes.fromhex(obs["after"]["raw"])
        return {i: b[i] - a[i] for i in RD_STATS if b[i] > a[i]}
    r, m = rises(retail), rises(mod)
    levelled = all(o["after"]["level"] == o["before"]["level"] + 1 for o in (retail, mod))
    ok = levelled and r and m and set(r.values()) == {1} and set(m.values()) == {GAIN}
    return ok, f"Micaiah levelled up in both: {levelled}; stat gains that rose, retail {[(hex(i), v) for i, v in r.items()]}, "                f"edited {[(hex(i), v) for i, v in m.items()]}"


CHECKS.append(Check("K3r", "rd", "Growth gain per success in a real level-up", ["Level-up growth rows (RD)"],
                    play=attack_play("PID_MICAIAH", RD_TILE), judge=judge_growth_rd, setup=setup_growth_rd,
                    fixture=fixture_gain_three_rd, start=Jump("0101")))


# -- Battle Weapons: the Iron Sword's weapon effect set to EID_FIRE2_WP (a retail fire effect; EID_K_FIRE is no PoR label), as the Battle Weapons
# page does through the item's weapon_effect; the same attack as K2. The fight must bring processes retail's
# fight doesn't (the effect's), and finish without new invalid accesses.

def fixture_fire_effect(ctx):
    """The Battle Weapons edit: xwp/IRONSWORD.dbx made a wave blade like the Sonic Sword's (kind 8, missile 2)
    with the Flame Lance's fire effects, and the item's FE8Data effects to match. E1 isolations (2026-11-24):
    the FE8Data effects alone on a plain-sword table turn a range-2 fight flat magenta (E1, E1p, E1w), while the
    retail Sonic Sword at range 2 draws fine (E1s) - the xwp table is what the battle reads."""
    from fe_modding import battle_tables
    from fe_modding.formats import battle_weapons, fe8data
    text = battle_tables.read_entry(ctx.project, "xwp/IRONSWORD.dbx")
    # the Sonic Sword's pattern in fire: the wave effect, then the _WP effect on the target (round 12 with the
    # Flame Lance's projectile effect as the wave: the fight worked, then the screen turned magenta)
    for field, value in (("kind", "8"), ("missile", "2"), ("effectId", "EID_K_FIRE2"),
                         ("damageEffId", "EID_K_FIRE2_WP")):
        text = battle_weapons.set_weapon_field(text, field, value)
    battle_tables.write_entry(ctx.project, "xwp/IRONSWORD.dbx", text)
    sword = next(i for i in ctx.data.items if i.iid == "IID_IRONSWORD")
    ctx.facts.update(old=getattr(sword, "weapon_effect", None),
                     change=f"Iron Sword weapon effect {getattr(sword, 'weapon_effect', None)} -> EID_FIRE2_WP")
    ctx.fe8 = fe8data.patch_item_field(ctx.fe8, sword.index, "weapon_effect", "EID_FIRE2_WP")
    # round 7 (2026-11-24): the weapon effect alone left every frame as retail; the Flame Lance carries both
    ctx.fe8 = fe8data.patch_item_field(ctx.fe8, sword.index, "effect", "EID_FIRE2")
    ctx.facts.update(change=ctx.facts["change"] + ", effect -> EID_FIRE2; xwp/IRONSWORD kind 8, missile 2, "
                            "effectId EID_K_FIRE2, damageEffId EID_K_FIRE2_WP")


def judge_new_processes(mod, retail, facts):
    extra = sorted(set(mod.get("battle_processes", [])) - set(retail.get("battle_processes", [])))
    return bool(extra), (f"weapon effect {facts.get('old')} -> EID_FIRE2_WP: processes only in the edited "
                         f"fight {extra[:8]} (frames in shots/battle_*.png)")


RANGED_TILE = (12, 15)      # two tiles north of Ike's start: a magic weapon casts its spell only at range 2


def setup_attack_ranged(ctx):
    """setup_attack, then the bandit two tiles away and the Iron Sword given range 1-2 like the Flame Lance (both
    runs). Round 7 (2026-11-24): in melee the fire effects left every frame as retail, as a magic weapon fights
    physically next to its target."""
    from fe_modding.formats import dispo, fe8data
    setup_attack(ctx)
    sword = next(i for i in ctx.data.items if i.iid == "IID_IRONSWORD")
    ctx.fe8 = fe8data.patch_item_field(ctx.fe8, sword.index, "max_range", 2)
    docs = {n: d for n, d in ctx.dispos("bmap02").items() if n == "dispos_h.bin"}
    field = dispo.FIELD
    for doc in docs.values():
        unit = next(u for s in doc.sections if s.name.endswith("_first_h") for u in s.units
                    if (u[field["pos_x"]], u[field["pos_y"]]) == ATTACK_TILE)
        for key in ("pos", "pos2"):
            unit[field[f"{key}_x"]], unit[field[f"{key}_y"]] = RANGED_TILE
    ctx.write_dispos("bmap02", docs)


def judge_fire_wave(mod, retail, facts):
    """The fire wave: damage at range, fire on screen (orange pixels), no magenta. No retail comparison: retail's
    Iron Sword given range 2 is a melee actor attacking from range, which is the magenta case itself."""
    from PIL import Image
    def orange(path):
        img = Image.open(path).convert("RGB").resize((96, 51))
        px = list(img.get_flattened_data() if hasattr(img, "get_flattened_data") else img.getdata())
        return sum(1 for r, g, b in px if r > 200 and 60 < g < 180 and b < 80) / len(px)
    frames = sorted(Path(mod["shot"]).parent.glob("battle_*.png"))
    fire = max((orange(f) for f in frames), default=0.0)
    lost = mod["before"]["target_hp"] - mod["target_hp_after"]
    magenta = flat_magenta_frames(mod)
    return lost > 0 and fire > 0.03 and not magenta, (
        f"{facts['change']}: from two tiles the bandit lost {lost} HP, fire covers up to {fire:.0%} of a frame, "
        f"{magenta} magenta frames (battle_*.png)")


CHECKS.append(Check("E1", "por", "Battle Weapons: the Iron Sword fights with the fire effect",
                    ["1.0 §4 Battle Weapons fire effect (POR)"], play=attack_play("PID_IKE", RANGED_TILE),
                    judge=judge_fire_wave, setup=setup_attack_ranged, fixture=lambda ctx: fixture_fire_no_crit(ctx),
                    start=Jump(2), retail=False))


# -- Battle Data: zdbx/param.dbx's InitPosL (the left combatant's start, -20) moved to -30 through battle_tables, as
# the Battle Data form writes it; the same attack as K2 must run to its end with no new invalid access.

def fixture_param_dbx(ctx):
    from fe_modding import battle_tables
    text = battle_tables.read_entry(ctx.project, "zdbx/param.dbx")
    old = next(line for line in text.splitlines() if line.strip().startswith("InitPosL"))
    new = old.replace("-20.0", "-30.0", 1)
    if new == old:
        raise RuntimeError(f"unexpected InitPosL line: {old!r}")
    battle_tables.write_entry(ctx.project, "zdbx/param.dbx", text.replace(old, new, 1))
    ctx.facts.update(line=new.strip())


def judge_fight_runs(mod, retail, facts):
    lost = mod["before"]["target_hp"] - mod["target_hp_after"]
    fought = any(n.startswith(BATTLE) for n in mod.get("battle_processes", []))
    return fought and lost > 0, f"{facts.get('line') or facts.get('change')}: the fight ran to its end (bandit lost {lost} HP), no new invalid " \
                                f"access (frames in shots/battle_*.png)"


CHECKS.append(Check("BD1", "por", "Battle Data: an edited param.dbx and a fight with animations",
                    ["1.0 §4 Battle Data ⭐ (POR param.dbx Form)"], play=play_attack, judge=judge_fight_runs,
                    setup=setup_attack, fixture=fixture_param_dbx, start=Jump(2)))


# -- more battle visuals, all with the same menu-driven attack (the frames are kept for a look) -----------------

def _frame(path: Path):
    from PIL import Image
    return Image.open(path).convert("L").resize((240, 127))


def _share(a, b, threshold: int = 40) -> float:
    from PIL import ImageChops
    hist = ImageChops.difference(a, b).point(lambda v: 255 if v > threshold else 0).histogram()
    return hist[255] / max(1, a.width * a.height)


def frames_differ(mod, retail, first: int = 0, last: int | None = None, window: int = 8,
                  sustained: int = 4) -> float:
    """How unlike retail the edited fight looks: each edited battle frame is matched with the closest retail frame
    within ``window`` frames of it (the two runs drift by a frame or more). The ``sustained``-th worst match is
    returned: a change has to show on that many frames (one second at four frames a second). A timing offset
    matches a neighbour, and a single flash of a spell caught in one run only is ignored (W2b, 2026-11-24: one
    frame at 26%, the others at 0-6%)."""
    def frames(obs):
        return sorted(Path(obs["shot"]).parent.glob("battle_*.png"))
    ours, theirs = frames(mod), frames(retail)
    if not ours or not theirs:
        return 0.0
    ours = ours[first:None if last is None else last + 1]
    loaded = [_frame(p) for p in theirs]
    matches = []
    for offset, path in enumerate(ours, first):
        frame = _frame(path)
        near = loaded[max(0, offset - window):offset + window + 1] or loaded
        matches.append(min(_share(frame, other) for other in near))
    matches.sort(reverse=True)
    return matches[min(sustained, len(matches)) - 1]


def flat_magenta_frames(obs) -> int:
    """Battle frames that are nearly all magenta: Dolphin's missing-texture colour, seen when a fight asks for
    an effect its weapon actor can't play (E1, 2026-11-24)."""
    from PIL import Image
    count = 0
    for path in sorted(Path(obs["shot"]).parent.glob("battle_*.png")) + [Path(obs["shot"])]:
        px = Image.open(path).convert("RGB").resize((96, 51)).get_flattened_data()             if hasattr(Image.Image, "get_flattened_data") else Image.open(path).convert("RGB").resize((96, 51)).getdata()
        px = list(px)
        count += sum(1 for r, g, b in px if r > 150 and b > 150 and g < 40) > len(px) // 2
    return count


def judge_fight_looks_different(mod, retail, facts):
    lost = mod["before"]["target_hp"] - mod["target_hp_after"]
    magenta = flat_magenta_frames(mod)
    if magenta:
        return False, (f"{facts.get('change', '')}: {magenta} frames of the edited fight are flat magenta (a "
                       f"missing texture), the screen is broken")
    share = frames_differ(mod, retail)
    return lost > 0 and share > 0.05, (f"{facts.get('change', '')}: the fight ran to its end (target lost {lost} HP); "
                                       f"the most different battle frame differs from retail on {share:.0%} of the "
                                       f"screen (battle_*.png)")


def setup_attack_rd_animated(ctx):
    """setup_attack_rd plus SetConfig(0, 0) at turn 1: the full battle scene (KA0 probe, 2026-11-19: 0 brings
    E_BUnitActor/E_BCamActor/E_BSkyActor, 1 and 2 the on-map fight, the jump's default the map fight)."""
    setup_attack_rd(ctx)
    ctx.append_chapter_script("0101", ANIMATIONS_ON)


#: an event that switches RD's battle animations on (SetConfig(0, 0)) at the first player phase
ANIMATIONS_ON = """
@on_phase(turn_from=1, turn_to=1, phase="player")
def CheckAnimationsOn():
    SetConfig(0, 0)
"""


def fixture_scenery(ctx):
    """Battle scenes: chapter 1's row (bmap02) fights its plains on the night backdrop."""
    from fe_modding.formats import fe8data
    rows = fe8data.read_battle_terrain(ctx.fe8)
    row = next(r for r in rows if r.map_name == "bmap02")
    old = list(row.scenes)
    # round 7 (2026-11-24): only the first scene changed left the fight as retail; every scene of the row now
    row.scenes[:] = ["crimea_night" if scene else scene for scene in row.scenes]
    ctx.fe8 = fe8data.write_battle_terrain(ctx.fe8, rows)
    ctx.facts.update(change=f"bmap02 battle scenes {old} -> crimea_night")


def fixture_light_fire(ctx):
    """RD Battle Weapons: the LIGHT row of FE10Battle's FE10BWeapon table given the FIRE row's effect and target,
    as the Battle Weapons page writes it. Group C (2026-11-24): the item's own ItemData effect fields (effect,
    effect_2) changed nothing drawn; this table is RD's twin of PoR's xwp tables, which the battle reads."""
    from fe_modding.formats import fe10_battle_weapons as bw
    data = ctx.project.read_logical("battle_data")
    rows = bw.read_weapons(data)
    light = next(r for r in rows if r.labels.get("key") == "LIGHT")
    fire = next(r for r in rows if r.labels.get("key") == "FIRE")
    labels = dict(light.labels, effect=fire.labels["effect"], target=fire.labels["target"])
    ctx.project.write_logical("battle_data", bw.set_weapon(data, light.index, labels=labels, type=light.type))
    ctx.facts.update(change=f"FE10BWeapon LIGHT effect/target ({light.labels['effect']}, {light.labels['target']}) "
                            f"-> ({fire.labels['effect']}, {fire.labels['target']})")


def fixture_light_particles(ctx):
    """Visual Effects: every particle emitter of the Light spell drawn four times bigger (particle editor)."""
    from fe_modding.formats import effects, particle_editor
    from fe_modding.formats import animation
    from fe_modding.game_profile import files_root_of
    counts = {}
    for eid in ("EID_K_LIGHT",):     # the LIGHT battle-weapon row's effect (EID_LIGHT/EID_HEAD_LIGHT: nothing, round 6)
        path = effects.pack_path(files_root_of(ctx.project), eid)
        parts = effects.read_effect_pack(path.read_bytes())
        ga = next(blob for name, blob in parts.items() if name.endswith(".ga"))
        layout = animation.read_particle_table_layout(ga)
        if layout is None:              # EID_HEAD_LIGHT has no particle table
            counts[eid] = 0
            continue
        for index, _emitter in enumerate(layout.emitters):
            values = {}
            for key in ("scale_s", "scale_t", "mode1_scale"):
                value = particle_editor.field_value(ga, layout.emitters[index].record_offset,
                                                    particle_editor.EMITTER_FIELDS[key])
                values[key] = max(-32768, min(32767, value * 4))
            ga = particle_editor.edit_emitter(ga, index, **values)
        ctx.project.write_keeping_original(path, effects.build_effect_pack(effects.replace_part(parts, "ga", ga)))
        counts[eid] = len(layout.emitters)
    ctx.facts.update(change=f"Light's emitters drawn four times bigger: {counts}")


def fixture_camera_weight(ctx):
    """RD Battle Data (FE10Battle Edit fields): the first camera choice of the first group made the only one."""
    from fe_modding.formats import fe10_battle
    data = ctx.project.read_logical("battle_data")
    ctx.project.write_logical("battle_data", fe10_battle.set_camera_choice_weight(data, 0, 0, 100))
    ctx.facts.update(change="FE10Battle camera group 0 choice 0 weight 100")


CHECKS += [
    Check("BS1", "por", "Battle scenes: chapter 1 fights its plains on another backdrop", ["1.0 §3 Battle scenes (POR)"],
          play=play_attack, judge=judge_fight_looks_different, setup=setup_attack, fixture=fixture_scenery,
          start=Jump(2)),
    Check("E1r", "rd", "Battle Weapons: Light fights with Fire's spell effect",
          ["1.0 §4 Battle Weapons effect (RD)"], play=attack_play("PID_MICAIAH", RD_TILE),
          judge=judge_fight_looks_different, setup=setup_attack_rd_animated, fixture=fixture_light_fire,
          start=Jump("0101")),
    Check("VX1r", "rd", "Visual Effects: the Light spell's particles four times bigger",
          ["1.0 §4 Visual Effects / particle editor (RD)"], play=attack_play("PID_MICAIAH", RD_TILE),
          judge=judge_fight_looks_different, setup=setup_attack_rd_animated, fixture=fixture_light_particles,
          start=Jump("0101")),
    Check("BD1r", "rd", "Battle Data: an edited FE10Battle field and a fight", ["1.0 §4 Battle Data ⭐ (RD)"],
          play=attack_play("PID_MICAIAH", RD_TILE), judge=judge_fight_runs, setup=setup_attack_rd,
          fixture=fixture_camera_weight, start=Jump("0101")),
]


# -- which SetConfig(0, value) turns RD's full battle scenes on (E1r and VX1r need them: map-only fights draw no
# spell effect). One run per value, the K2r attack, judged by the processes the fight brings.

def setup_config(value: int):
    def setup(ctx):
        setup_attack_rd(ctx)
        ctx.append_chapter_script("0101", f'\n@on_phase(turn_from=1, turn_to=1, phase="player")\n'
                                          f'def CheckConfig():\n    SetConfig(0, {value})\n')
    return setup


#: SetConfig(0, value) -> the fight RD plays (KA probes, 2026-11-19): 0 and 3 the full battle scene, 1 and 2
#: the on-map fight. E1r, VX1r, W1b and W2b rely on 0.
CONFIG_SCENE = {0: "full", 1: "map", 2: "map", 3: "full"}


def judge_config(value: int):
    def judge(mod, retail, facts):
        names = mod.get("battle_processes", [])
        full = [n for n in names if n in ("E_BUnitActor", "E_BCamActor", "E_BSkyActor")]
        on_map = [n for n in names if "OnBt" in n]
        seen = "full" if full else "map" if on_map else "none"
        return seen == CONFIG_SCENE[value], (f"SetConfig(0, {value}) gives the {seen} fight (expected "
                                             f"{CONFIG_SCENE[value]}): full-scene processes {full}, on-map {on_map}")
    return judge


CHECKS += [Check(f"KA{v}", "rd", f"SetConfig(0, {v}) gives the {CONFIG_SCENE[v]} fight", [],
                 play=attack_play("PID_MICAIAH", RD_TILE), judge=judge_config(v), setup=setup_config(v),
                 start=Jump("0101"), retail=False) for v in range(4)]


# -- weather in the battle scene (RD). ChapterData weather is read only for promotion scenes outside a fight
# (E_CCProc modes 1-4, 0x80186144); a fight takes the map's weather id (0x804CB834, set from mapextra by
# 0x8013A35C) unless an event overrides it. So the chapter field must leave the fight's weather as retail. The
# oracle is the weather effect process (E_MapCloud on the Prologue, E_MapSnow with the map set to snow, W4b):
# the frames of three retail-vs-retail-like runs differed by 3.7-4.4%, and the hit numbers are no oracle
# either: the bandit's raw hit and avoid moved by 5-15 between retail runs (biorhythm), which is what the
# 2026-11-04 parity run's "54 -> 69" was.

def _odds_note(mod, retail):
    a, b = mod.get("odds"), retail.get("odds")
    if not a or not b:
        return "hit numbers not read"
    return f"defender hit {a['defender']['hit']} (retail {b['defender']['hit']}; varies by run)"


def _weather_note(mod, retail):
    from .oracles import weather_effects
    ours = weather_effects(mod.get("battle_processes"))
    theirs = weather_effects(retail.get("battle_processes"))
    return ours, theirs, f"weather effect {sorted(ours)} (retail {sorted(theirs)})"


def judge_weather_battle(mod, retail, facts):
    sky = "E_BSkyActor" in mod.get("battle_processes", [])
    ours, theirs, note = _weather_note(mod, retail)
    return sky and ours == theirs, (
        f"weather {facts['old']} -> {facts['new']}: full battle scene {'on' if sky else 'OFF'}; {note} "
        f"(expected: as retail); frames differ by {frames_differ(mod, retail):.1%}; {_odds_note(mod, retail)}")


def judge_map_weather_battle(mod, retail, facts):
    sky = "E_BSkyActor" in mod.get("battle_processes", [])
    ours, theirs, note = _weather_note(mod, retail)
    return sky and "E_MapSnow" in ours and "E_MapSnow" not in theirs, (
        f"map weather code {facts['old']} -> {facts['new']}: full battle scene {'on' if sky else 'OFF'}; {note}; "
        f"snowflakes in the fight (battle_*.png); {_odds_note(mod, retail)}")


def _weather(chapter_id, weather):
    from .checks_chapters import weather_fixture
    return weather_fixture(chapter_id, weather)


def _map_weather(folder, code):
    from .checks_chapters import map_weather_fixture
    return map_weather_fixture(folder, code)


CHECKS += [
    Check(f"W{n}b", "rd", f"Chapter weather: Prologue fights in {label} look and hit as retail",
          ["RD weather (known bug)"],
          play=attack_play("PID_MICAIAH", RD_TILE), judge=judge_weather_battle, setup=setup_attack_rd_animated,
          fixture=_weather("C0101", weather), start=Jump("0101"))
    for n, label, weather in ((1, "snow", "雪"), (2, "the night", "夜"))
] + [
    Check("W4b", "rd", "Map weather: Prologue's fights in snow", ["RD weather: Map settings weather"],
          play=attack_play("PID_MICAIAH", RD_TILE), judge=judge_map_weather_battle, setup=setup_attack_rd_animated,
          fixture=_map_weather("bmap0101", 5), start=Jump("0101")),
]


# -- E1 isolation: the range-2 fire fight turned the screen magenta for good (round 8). Is it the effect not being
# loaded for the chapter? The same edit, with a bandit far away carrying a real Flame Lance (EID_FIRE2 in use).

def setup_attack_ranged_lance_loaded(ctx):
    """setup_attack_ranged with a Flame Lance on the (4, 4) bandit (round 9: still 33 of 40 frames magenta)."""
    from fe_modding.formats import dispo
    setup_attack_ranged(ctx)
    docs = {n: d for n, d in ctx.dispos("bmap02").items() if n == "dispos_h.bin"}
    field = dispo.FIELD
    for doc in docs.values():
        far = next(u for s in doc.sections if s.name.endswith("_first_h") for u in s.units
                   if str(u[field["pid"]]).startswith("PID_BANDIT") and (u[field["pos_x"]], u[field["pos_y"]]) == (4, 4))
        far[field["item1"]] = "IID_FRAMELANCE"
    ctx.write_dispos("bmap02", docs)


def judge_no_magenta(mod, retail, facts):
    from PIL import Image
    def share(path):
        px = list(Image.open(path).convert("RGB").resize((96, 51)).getdata())
        return sum(1 for r, g, b in px if r > 150 and b > 150 and g < 40) / len(px)
    frames = sorted(Path(mod["shot"]).parent.glob("battle_*.png"))
    magenta = sum(share(f) > 0.5 for f in frames)
    return magenta == 0, (f"{facts['change']}: {magenta} of {len(frames)} battle frames flat magenta "
                          f"(the bandit {mod['before']['target_hp']} -> {mod['target_hp_after']} HP)")


CHECKS.append(Check("E1p", "por", "E1 isolation: the fire effects with a Flame Lance in the chapter", [],
                    play=attack_play("PID_IKE", RANGED_TILE), judge=judge_no_magenta,
                    setup=setup_attack_ranged_lance_loaded, fixture=fixture_fire_effect, start=Jump(2), retail=False))



# -- E1 isolation 2: the Flame Lance's fire on a sword, or any magic-sword effect at range? The Sonic Sword's wind.

def fixture_wind_effect(ctx):
    from fe_modding.formats import fe8data
    sword = next(i for i in ctx.data.items if i.iid == "IID_IRONSWORD")
    ctx.fe8 = fe8data.patch_item_field(ctx.fe8, sword.index, "weapon_effect", "EID_WIND2_WP")
    ctx.fe8 = fe8data.patch_item_field(ctx.fe8, sword.index, "effect", "EID_WIND2")
    ctx.facts.update(change="Iron Sword effects -> EID_WIND2 / EID_WIND2_WP (the Sonic Sword's)")


CHECKS.append(Check("E1w", "por", "E1 isolation: a sword's own magic (Sonic Sword wind) at range 2", [],
                    play=attack_play("PID_IKE", RANGED_TILE), judge=judge_no_magenta,
                    setup=setup_attack_ranged, fixture=fixture_wind_effect, start=Jump(2), retail=False))



# -- E1 isolation 3: the retail Sonic Sword itself (its own effects, nothing edited but Ike's sword rank) at range 2.
# Round 10: any magic effect put on the Iron Sword turned a range-2 fight magenta (fire and wind alike).

def fixture_real_sonic_sword(ctx):
    from fe_modding.formats import dispo
    ctx.set_character("PID_IKE", weapon_ranks="B--------")
    docs = {n: d for n, d in ctx.dispos("bmap02").items() if n == "dispos_h.bin"}
    field = dispo.FIELD
    for doc in docs.values():
        ike = next(u for s in doc.sections for u in s.units if u[field["pid"]] == "PID_IKE")
        ike[field["item0"]] = "IID_SONICBLADE"
    ctx.write_dispos("bmap02", docs)
    ctx.facts.update(change="Ike holds the retail Sonic Sword (sword rank B)")


CHECKS.append(Check("E1s", "por", "E1 isolation: the retail Sonic Sword at range 2", [],
                    play=attack_play("PID_IKE", RANGED_TILE), judge=judge_no_magenta,
                    setup=setup_attack_ranged, fixture=fixture_real_sonic_sword, start=Jump(2), retail=False))



# -- E1 isolation 4 (round 13: the fire wave blade killed with a forced critical, then 11 frames went magenta;
# the retail Sonic Sword, which did not kill, drew none). E1c: E1 without the forced critical. E1k: the retail
# Sonic Sword with 255 critical, so it kills at range.

def fixture_fire_no_crit(ctx):
    from fe_modding.formats import fe8data
    fixture_fire_effect(ctx)
    sword = next(i for i in ctx.data.items if i.iid == "IID_IRONSWORD")
    ctx.fe8 = fe8data.patch_item_field(ctx.fe8, sword.index, "crit", 0)
    ctx.facts.update(change=ctx.facts["change"] + "; crit 0")


def fixture_sonic_kills(ctx):
    from fe_modding.formats import fe8data
    fixture_real_sonic_sword(ctx)
    blade = next(i for i in ctx.data.items if i.iid == "IID_SONICBLADE")
    ctx.fe8 = fe8data.patch_item_field(ctx.fe8, blade.index, "crit", 255)
    ctx.fe8 = fe8data.patch_item_field(ctx.fe8, blade.index, "hit", 255)
    ctx.facts.update(change=ctx.facts["change"] + "; Sonic Sword hit and crit 255 (kills at range)")


# -- E1 group E (2026-11-25): E1's fire wave blade ends its fight with ~2.5 s of flat magenta; the retail Sonic
# Sword never does. The xwp tables differ only in model and effects (the fire and wind pairs ship the same
# _WP/_2D variants in yme/). E1m: E1 with the Iron Sword's Model block pointed at the Sonic Sword's model.
# E1f: the real Sonic Sword (its model and item) with E1's fire effects in place of wind.

def fire_on_model(model: str):
    """E1's edit with the Iron Sword's Model block pointed at another sword's model."""
    def fixture(ctx):
        from fe_modding import battle_tables
        from fe_modding.formats import dbx
        fixture_fire_no_crit(ctx)
        doc = dbx.parse(battle_tables.read_entry(ctx.project, "xwp/IRONSWORD.dbx"))
        for field in doc.find("Model").fields:
            if field.key == "folder":
                doc.set_value(field, f"xwp/{model}")
            elif field.key == "model":
                doc.set_value(field, model)
        battle_tables.write_entry(ctx.project, "xwp/IRONSWORD.dbx", doc.text)
        ctx.facts.update(change=ctx.facts["change"] + f"; Model block -> xwp/{model}/{model}")
    return fixture


fixture_fire_sonic_model = fire_on_model("SONICBLADE")


def fixture_sonic_in_fire(ctx):
    from fe_modding import battle_tables
    from fe_modding.formats import battle_weapons, fe8data
    fixture_real_sonic_sword(ctx)
    text = battle_tables.read_entry(ctx.project, "xwp/SONICBLADE.dbx")
    for field, value in (("effectId", "EID_K_FIRE2"), ("damageEffId", "EID_K_FIRE2_WP")):
        text = battle_weapons.set_weapon_field(text, field, value)
    battle_tables.write_entry(ctx.project, "xwp/SONICBLADE.dbx", text)
    blade = next(i for i in ctx.data.items if i.iid == "IID_SONICBLADE")
    ctx.fe8 = fe8data.patch_item_field(ctx.fe8, blade.index, "effect", "EID_FIRE2")
    ctx.fe8 = fe8data.patch_item_field(ctx.fe8, blade.index, "weapon_effect", "EID_FIRE2_WP")
    ctx.facts.update(change=ctx.facts["change"] + "; xwp/SONICBLADE effectId EID_K_FIRE2, damageEffId "
                            "EID_K_FIRE2_WP; item effects EID_FIRE2 / EID_FIRE2_WP")


CHECKS += [
    Check("E1m", "por", "E1 isolation: the fire wave blade on the Sonic Sword's model", [],
          play=attack_play("PID_IKE", RANGED_TILE), judge=judge_no_magenta, setup=setup_attack_ranged,
          fixture=fixture_fire_sonic_model, start=Jump(2), retail=False, probe=True),
    Check("E1t", "por", "E1 isolation: the fire wave blade on the Steel Sword's model", [],
          play=attack_play("PID_IKE", RANGED_TILE), judge=judge_no_magenta, setup=setup_attack_ranged,
          fixture=fire_on_model("STEELSWORD"), start=Jump(2), retail=False, probe=True),
    Check("E1f", "por", "E1 isolation: the retail Sonic Sword with fire effects", [],
          play=attack_play("PID_IKE", RANGED_TILE), judge=judge_no_magenta, setup=setup_attack_ranged,
          fixture=fixture_sonic_in_fire, start=Jump(2), retail=False, probe=True),
]

CHECKS += [
    Check("E1c", "por", "E1 isolation: the fire wave blade without a forced critical", [],
          play=attack_play("PID_IKE", RANGED_TILE), judge=judge_no_magenta, setup=setup_attack_ranged,
          fixture=fixture_fire_no_crit, start=Jump(2), retail=False),
    Check("E1k", "por", "E1 isolation: the retail Sonic Sword killing at range", [],
          play=attack_play("PID_IKE", RANGED_TILE), judge=judge_no_magenta, setup=setup_attack_ranged,
          fixture=fixture_sonic_kills, start=Jump(2), retail=False),
]



# -- E1p / E1w as checks of game behaviour: a melee battle table attacking from range turns the screen magenta
# for good (whatever effects the item has), and the project check warns about the weapon in the same build.

def with_ranged_melee_warning(fixture):
    def wrapped(ctx):
        from fe_modding import validator
        fixture(ctx)
        issues: list = []
        validator.check_ranged_melee_weapons(ctx.project, ctx.data, issues)
        ctx.facts.update(warned=[i.where for i in issues])
    return wrapped


def judge_magenta_warned(mod, retail, facts):
    magenta = flat_magenta_frames(mod)
    warned = "xwp/IRONSWORD.dbx" in facts.get("warned", [])
    return magenta > 0 and warned, (f"{facts['change']}: {magenta} flat magenta frames (a melee battle table "
                                    f"attacking from range); the project check "
                                    f"{'warns about xwp/IRONSWORD.dbx' if warned else 'says nothing'}")


def fixture_fire_fe8_only(ctx):
    """The Flame Lance's effects on the Iron Sword in FE8Data only (its battle table stays a melee one)."""
    from fe_modding.formats import fe8data
    sword = next(i for i in ctx.data.items if i.iid == "IID_IRONSWORD")
    ctx.fe8 = fe8data.patch_item_field(ctx.fe8, sword.index, "weapon_effect", "EID_FIRE2_WP")
    ctx.fe8 = fe8data.patch_item_field(ctx.fe8, sword.index, "effect", "EID_FIRE2")
    ctx.facts.update(change="Iron Sword effects -> EID_FIRE2 / EID_FIRE2_WP in FE8Data (battle table untouched)")


for _check in CHECKS:
    if _check.id == "E1p":
        _check.fixture = fixture_fire_fe8_only     # E1's fixture now also rewrites the battle table
    if _check.id in ("E1p", "E1w"):
        _check.title = _check.title.replace("E1 isolation: ", "Ranged melee weapon: ") + " - magenta, and warned"
        _check.fixture = with_ranged_melee_warning(_check.fixture)
        _check.judge = judge_magenta_warned


# -- group E (2026-11-25): the flash at the end of E1's fight comes from the Iron Sword's model, which lacks the
# blade's marker quads (E1m on the Sonic Sword's model and E1t on the Steel Sword's: no magenta). E1 now builds
# the fire wave blade on the Steel Sword's model and must draw cleanly with no warning; E1c keeps the Iron
# Sword's model and must flash, with the project check warning about it.

def with_wave_warning(fixture):
    def wrapped(ctx):
        from fe_modding import validator
        fixture(ctx)
        issues: list = []
        validator.check_wave_blade_models(ctx.project, issues)
        ctx.facts.update(wave_warned=[i.where for i in issues])
    return wrapped


def judge_fire_wave_unwarned(mod, retail, facts):
    ok, details = judge_fire_wave(mod, retail, facts)
    warned = facts.get("wave_warned", [])
    return ok and not warned, f"{details}; the project check {'warns about ' + str(warned) if warned else 'is quiet'}"


def judge_wave_magenta_warned(mod, retail, facts):
    magenta = flat_magenta_frames(mod)
    warned = "xwp/IRONSWORD.dbx" in facts.get("wave_warned", [])
    return magenta > 0 and warned, (f"{facts['change']}: {magenta} flat magenta frames at the end of the fight; the "
                                    f"project check {'warns about xwp/IRONSWORD.dbx' if warned else 'says nothing'}")


for _check in CHECKS:
    if _check.id == "E1":
        _check.title = "Battle Weapons: the Iron Sword as a fire wave blade on the Steel Sword's model"
        _check.fixture = with_wave_warning(fire_on_model("STEELSWORD"))
        _check.judge = judge_fire_wave_unwarned
    if _check.id == "E1c":
        _check.title = "Wave blade on the Iron Sword's model - magenta, and warned"
        _check.fixture = with_wave_warning(fixture_fire_no_crit)
        _check.judge = judge_wave_magenta_warned



# -- VX1t / VX1r (group C, 2026-11-24): Light's particles on screen. Scaling them alone could not be judged from
# screenshots (the beam, one frame long, dominates). Both runs draw EID_K_LIGHT's textures magenta (alpha kept);
# VX1r also draws the particles four times bigger, so its magenta area must clearly exceed VX1t's.

def _light_textures_magenta(ctx):
    import io
    from PIL import Image
    from fe_modding.formats import effects, tpl
    from fe_modding.game_profile import files_root_of
    path = effects.pack_path(files_root_of(ctx.project), "EID_K_LIGHT")
    parts = effects.read_effect_pack(path.read_bytes())
    name = next(n for n in parts if n.endswith(".tpl"))
    data = parts[name]
    images = tpl.read_tpl_images(io.BytesIO(data))
    for index, image in enumerate(images):
        alpha = image.convert("RGBA").getchannel("A")
        flat = Image.new("RGBA", image.size, (255, 0, 255, 255))
        flat.putalpha(alpha)
        data = tpl.replace_image(data, index, flat)
    ctx.project.write_keeping_original(path, effects.build_effect_pack(effects.replace_part(parts, "tpl", data)))
    return len(images)


def fixture_light_magenta(ctx):
    count = _light_textures_magenta(ctx)
    ctx.facts.update(change=f"EID_K_LIGHT: {count} textures magenta (alpha kept)")


def fixture_light_magenta_bigger(ctx):
    count = _light_textures_magenta(ctx)
    fixture_light_particles(ctx)
    ctx.facts.update(change=f"EID_K_LIGHT: {count} textures magenta, particles four times bigger")


def magenta_area(obs) -> float:
    """The most magenta-ish screen share in any battle frame (additive magenta over a dark scene included)."""
    from PIL import Image
    best = 0.0
    for path in sorted(Path(obs["shot"]).parent.glob("battle_*.png")):
        img = Image.open(path).convert("RGB").resize((160, 85))
        px = list(img.get_flattened_data() if hasattr(img, "get_flattened_data") else img.getdata())
        best = max(best, sum(1 for r, g, b in px if r > 110 and b > 110 and g < 0.6 * min(r, b)) / len(px))
    return best


def judge_light_drawn(mod, retail, facts):
    m, r = magenta_area(mod), magenta_area(retail)
    return m > 0.005 and r < 0.001, (f"{facts['change']}: up to {m:.1%} of a battle frame magenta (retail {r:.2%}): "
                                     f"the LIGHT row's effect pack is what the fight draws")


def judge_light_bigger(mod, retail, facts):
    import json
    base = ROOT / "out" / "VX1t_mod" / "observations.json"
    if not base.is_file():
        return False, "run VX1t first"
    t = magenta_area(json.loads(base.read_text(encoding="utf-8")))
    m = magenta_area(mod)
    return m > 1.5 * t and m > 0.005, (f"{facts['change']}: up to {m:.1%} of a frame magenta, against {t:.1%} "
                                       f"with the textures alone (VX1t)")


for _check in CHECKS:
    if _check.id == "VX1r":
        _check.title = "Visual Effects: Light's particles four times bigger (magenta marked)"
        _check.fixture = fixture_light_magenta_bigger
        _check.judge = judge_light_bigger
CHECKS.append(Check("VX1t", "rd", "Visual Effects: Light's effect textures magenta (the pack the fight draws)",
                    ["1.0 §4 Visual Effects (RD)"], play=attack_play("PID_MICAIAH", RD_TILE),
                    judge=judge_light_drawn, setup=setup_attack_rd_animated, fixture=fixture_light_magenta,
                    start=Jump("0101")))



def fire_area(obs) -> float:
    from PIL import Image
    best = 0.0
    for path in sorted(Path(obs["shot"]).parent.glob("battle_*.png")):
        img = Image.open(path).convert("RGB").resize((96, 51))
        px = list(img.get_flattened_data() if hasattr(img, "get_flattened_data") else img.getdata())
        best = max(best, sum(1 for r, g, b in px if r > 200 and 60 < g < 180 and b < 80) / len(px))
    return best


def judge_light_fights_with_fire(mod, retail, facts):
    """Fire on screen in the edited fight and none in retail's (the impact is short: one frame at four a second,
    so the sustained-frames judge can't see it; group C, 2026-11-24)."""
    m, r = fire_area(mod), fire_area(retail)
    lost = mod["before"]["target_hp"] - mod["target_hp_after"]
    return lost > 0 and m > 0.02 and r < 0.005, (f"{facts['change']}: fire covers up to {m:.1%} of a battle frame "
                                                f"(retail {r:.1%}); the target lost {lost} HP")


for _check in CHECKS:
    if _check.id == "E1r":
        _check.judge = judge_light_fights_with_fire



# -- E1rm (group C): what the item's own effect fields drive. The battle scene takes its effects from the
# FE10BWeapon row (E1r); with SetConfig(0, 1) the fight plays on the map, which may use ItemData's EID_* effects.

def fixture_light_item_fire(ctx):
    from fe_modding.formats import fe10data
    data = ctx.project.read_logical("game_data")
    light = next(r for r in fe10data.read_table(data, "item") if r.id == "IID_LIGHT")
    old = (light.values.get("effect"), light.values.get("effect_2"))
    data = fe10data.patch_field(data, "item", light.index, "effect", "EID_HEAD_FIRE")
    data = fe10data.patch_field(data, "item", light.index, "effect_2", "EID_FIRE")
    ctx.project.write_logical("game_data", data)
    ctx.facts.update(change=f"ItemData IID_LIGHT effects {old} -> (EID_HEAD_FIRE, EID_FIRE), on-map fight")


def judge_map_fire(mod, retail, facts):
    """The on-map fight's fireball is small at map scale (under 1% of the screen) and retail's Light draws none."""
    m, r = fire_area(mod), fire_area(retail)
    return m > 0.004 and r < 0.001, (f"{facts['change']}: fire covers up to {m:.1%} of a frame of the on-map "
                                     f"fight (retail {r:.1%}): the item's own effects drive the on-map fight, the "
                                     f"FE10BWeapon row the battle scene (E1r)")


CHECKS.append(Check("E1rm", "rd", "Items: Light's own effect fields in the on-map fight", ["1.0 §4 Items effects (RD)"],
                    play=attack_play("PID_MICAIAH", RD_TILE), judge=judge_map_fire,
                    setup=setup_config(1), fixture=fixture_light_item_fire, start=Jump("0101")))



# VX1t and VX1r at 30% speed with 150 frames: the spell's phases (beam, impact) each land on several frames, so
# the two runs' largest magenta areas compare like with like (at full speed they caught different moments).
for _check in CHECKS:
    if _check.id in ("VX1t", "VX1r", "E1rm"):     # E1rm: the on-map fight is over in a few frames at full speed
        _check.speed, _check.minutes = 0.3, 20
        _check.play = attack_play("PID_MICAIAH", RD_TILE, frames=150)
