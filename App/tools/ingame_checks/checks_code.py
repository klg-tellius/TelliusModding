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
