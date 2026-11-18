"""Sharing a mod (1.0 checklist section 6 ⭐): Create patch, then Tellius Patcher on a retail disc image.

The edited tree (G1's edit: Ike's Str bonus +2, no chapter jump) is turned into a ``.tpatch`` with
``patch.create_patch`` and applied to the retail US disc image with ``patch.apply_patch_to_disc``, the code
Tellius Patcher runs. Dolphin boots the image it built; the driver starts a New Game (Difficult) and plays
to the Prologue's first player phase, where Ike's person record in RAM must carry the edit. Retail: G1's
retail run (the same record from a chapter jump into the Prologue).
"""
from __future__ import annotations

import json
from pathlib import Path

from .checks_gamedata import por_edit
from .core import BASES, ROOT, Check, Title
from .oracles import map_start, record_edit

RETAIL_IMAGE = Path("G:/ROM/Fire Emblem - Path of Radiance (USA).ciso")


def package(run: Path, variant: str) -> None:
    from fe_modding import patch
    from fe_modding.games import Game
    from tools.session_playtest.harness import assemble_run_tree
    disc = run / "disc_tree"         # the edited disc alone (the run folder also holds patch/, card/...)
    assemble_run_tree(BASES["GFEE01"], run / "patch", disc)
    tpatch = run / "mod.tpatch"
    patch.create_patch(BASES["GFEE01"], disc, tpatch, game=Game.PATH_OF_RADIANCE, name="In-game check X1")
    patch.apply_patch_to_disc(tpatch, RETAIL_IMAGE, run / "image.iso")


def judge(mod, retail, facts):
    path = ROOT / "out" / "G1_retail" / "observations.json"
    if not path.is_file():
        return False, "run G1 first (its retail run is the reference)"
    retail = json.loads(path.read_text(encoding="utf-8"))
    passed, text = record_edit("PID_IKE", "person")(mod, retail, facts)
    return passed, f"image built by the patcher from the .tpatch: {text}"


CHECKS = [Check("X1", "por", "Create patch + Tellius Patcher: the patched image carries the edit",
                ["1.0 §6 Create patch ⭐", "1.0 §6 TelliusPatcher ⭐"], play=map_start(["PID_IKE"], minutes=12), judge=judge,
                fixture=por_edit("character", "PID_IKE", "stat_bonus1", 2), start=Title(), package=package,
                retail=False, minutes=12)]
