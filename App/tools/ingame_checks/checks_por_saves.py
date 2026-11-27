"""Path of Radiance save edits loaded by the game (1.0 checklist section 5, Saves POR ⭐).

The chapter sweep's save that continues into chapter 1 is loaded from the title; the edited run sets Ike's
level to 15 with the save editor's code (re-signed with ``play_copy``), the retail run loads it unedited.
"""
from __future__ import annotations

from .core import SWEEP_SAVES, Check
from .ram_view import GameRam

START = SWEEP_SAVES["por"] / "003_chapter02_01-GFEE-FIREEMBLEM8J.gci"
CARD_NAME = "01-GFEE-FIREEMBLEM8J.gci"
NEW_LEVEL = 15


def card(ctx, variant):
    from fe_modding.formats import save_file as sf
    save = sf.SaveFile.from_bytes(START.read_bytes())
    index = next(i for i, b in enumerate(save.blocks)
                 if b.decoded and b.header.save_kind == 2 and not b.is_checkpoint and any(b.units))
    if variant == "mod":
        unit = ctx.unit(save.blocks[index], "PID_IKE")
        ctx.facts.update(old_level=unit.level)
        unit.level = NEW_LEVEL
    return {CARD_NAME: sf.play_copy(save, index, rebuild=(index,))}


def play(driver, facts):
    driver.to_player_phase(10)
    ike = GameRam(driver.ram, "GFEE01").unit("PID_IKE")
    return {"level": ike.level, "chapter": driver.state().chapter, "shot": str(driver.snap("map"))}


def judge(mod, retail, facts):
    ok = mod["level"] == NEW_LEVEL and retail["level"] == facts["old_level"] and mod["chapter"] == retail["chapter"]
    return ok, f"Ike on chapter {mod['chapter']}'s map: level {mod['level']} (edited {facts['old_level']} -> " \
               f"{NEW_LEVEL}), retail {retail['level']}"


CHECKS = [Check("S10", "por", "A .gci level edit loads (Ike level 15)", ["1.0 §5 Saves POR ⭐"],
                play=play, judge=judge, card=card, minutes=10)]
