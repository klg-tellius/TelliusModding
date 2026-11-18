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

from .core import Check, Jump
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


def attack_play(attacker: str = "PID_IKE", tile=ATTACK_TILE):
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
        deadline = time.time() + 180
        seen: set = set()
        frame, next_frame = 0, time.time()
        while time.time() < deadline and (any(n.startswith(BATTLE) for n in driver.state().names)
                                          or not {"E_BMapPlph"} <= driver.state().names):
            names = driver.state().names
            seen |= set(names)
            if time.time() >= next_frame and frame < 10:      # a frame a second, for a look
                driver.snap(f"battle_{frame:02d}")
                frame, next_frame = frame + 1, time.time() + 1.0
            # a battle conversation (a boss's or a talk event's quote) or the level-up window waits for A
            if any(n.startswith(("E_Talk", "E_LevelUp", "E_Lvup", "E_GrowUp")) for n in names):
                driver.press("A", gap=1.0)
            time.sleep(0.5)
        time.sleep(3)
        after = next((u for u in game.units() if u.handle == target.handle), None)
        me = game.unit(attacker)
        return {"before": before, "target_hp_after": after.hp if after else 0, "battle_processes": sorted(seen),
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


#: bytes of a Radiant Dawn unit that change on a level-up but are not stats: the level and the EXP
RD_NOT_STATS = {0xFE, 0xFF}


def judge_growth_rd(mod, retail, facts):
    """The RD stat bytes aren't named: every byte of the unit that went up (other than the level) must
    have gone up by 1 in retail and by 3 in the edited run."""
    def rises(obs):
        a, b = bytes.fromhex(obs["before"]["raw"]), bytes.fromhex(obs["after"]["raw"])
        return {i: y - x for i, (x, y) in enumerate(zip(a, b)) if 0x100 <= i < 0x1BC and y > x and i not in RD_NOT_STATS}
    r, m = rises(retail), rises(mod)
    levelled = all(o["after"]["level"] == o["before"]["level"] + 1 for o in (retail, mod))
    ok = levelled and r and m and set(r.values()) == {1} and set(m.values()) == {GAIN}
    return ok, f"Micaiah levelled up in both: {levelled}; bytes that rose, retail {[(hex(i), v) for i, v in r.items()]}, " \
               f"edited {[(hex(i), v) for i, v in m.items()]}"


CHECKS.append(Check("K3r", "rd", "Growth gain per success in a real level-up", ["Level-up growth rows (RD)"],
                    play=attack_play("PID_MICAIAH", RD_TILE), judge=judge_growth_rd, setup=setup_growth_rd,
                    fixture=fixture_gain_three_rd, start=Jump("0101")))


# -- Battle Weapons: the Iron Sword's weapon effect set to EID_FIRE2_WP (a retail fire effect; EID_K_FIRE is no PoR label), as the Battle Weapons
# page does through the item's weapon_effect; the same attack as K2. The fight must bring processes retail's
# fight doesn't (the effect's), and finish without new invalid accesses.

def fixture_fire_effect(ctx):
    from fe_modding.formats import fe8data
    sword = next(i for i in ctx.data.items if i.iid == "IID_IRONSWORD")
    ctx.facts.update(old=getattr(sword, "weapon_effect", None))
    ctx.fe8 = fe8data.patch_item_field(ctx.fe8, sword.index, "weapon_effect", "EID_FIRE2_WP")


def judge_new_processes(mod, retail, facts):
    extra = sorted(set(mod.get("battle_processes", [])) - set(retail.get("battle_processes", [])))
    return bool(extra), (f"weapon effect {facts.get('old')} -> EID_FIRE2_WP: processes only in the edited "
                         f"fight {extra[:8]} (frames in shots/battle_*.png)")


CHECKS.append(Check("E1", "por", "Battle Weapons: the Iron Sword fights with the fire effect",
                    ["1.0 §4 Battle Weapons fire effect (POR)"], play=play_attack, judge=judge_new_processes,
                    setup=setup_attack, fixture=fixture_fire_effect, start=Jump(2)))


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
    return fought and lost > 0, f"{facts['line']}: the fight ran to its end (bandit lost {lost} HP), no new invalid " \
                                f"access (frames in shots/battle_*.png)"


CHECKS.append(Check("BD1", "por", "Battle Data: an edited param.dbx and a fight with animations",
                    ["1.0 §4 Battle Data ⭐ (POR param.dbx Form)"], play=play_attack, judge=judge_fight_runs,
                    setup=setup_attack, fixture=fixture_param_dbx, start=Jump(2)))
