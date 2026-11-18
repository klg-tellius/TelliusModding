"""3D model round trips (1.0 checklist section 4 ⭐ 3D Models): Export .glb, then Import .glb of the same file
through the Models page's own functions, and Write files.

* B1 / B1r: the lord's map model (``ymu/lord``, ``ymu/mikaya1``): ``export_set_glb`` then
  ``replace_body_with_glb``.
* B2 / B2r: chapter 1's / the Prologue's map terrain: ``export_map_terrain_glb`` then
  ``replace_map_terrain_with_glb`` (defaults: heights followed, conformed).

The files really change (the import rebuilds them), but the map must look the same as retail: the judge
compares the first player phase's screen and accepts a small difference only. The screenshots are kept
for a look.
"""
from __future__ import annotations

import tempfile
from pathlib import Path

from .core import Check, Jump
from .oracles import map_shot, region_diff


def _write(ctx, outputs: dict) -> int:
    changed = 0
    for path, data in outputs.items():
        path = Path(path)
        if not path.is_file() or path.read_bytes() != data:
            changed += 1
        ctx.project.write_keeping_original(path, data)
    return changed


def body_round_trip(folder: str):
    def fixture(ctx):
        from fe_modding.game_profile import files_root_of
        from fe_modding.gui import model_viewer as mv
        container = files_root_of(ctx.project) / "ymu" / folder / "pack.cmp"
        with tempfile.TemporaryDirectory() as temp:
            glb = Path(temp) / f"{folder}.glb"
            glb.write_bytes(mv.export_set_glb(container))
            result = mv.replace_body_with_glb(container, glb)
        ctx.facts.update(files=_write(ctx, result.outputs), warnings=result.warnings[:5], model=f"ymu/{folder}")
    return fixture


def terrain_round_trip(folder: str):
    def fixture(ctx):
        from fe_modding.game_profile import files_root_of
        from fe_modding.gui import model_viewer as mv
        container = files_root_of(ctx.project) / "zmap" / folder / "map.cmp"
        with tempfile.TemporaryDirectory() as temp:
            glb = Path(temp) / f"{folder}.glb"
            glb.write_bytes(mv.export_map_terrain_glb(container))
            result = mv.replace_map_terrain_with_glb(container, glb)
        ctx.facts.update(files=_write(ctx, result.outputs), warnings=result.warnings[:5], model=f"zmap/{folder}")
    return fixture


def judge_same(mod, retail, facts):
    share = region_diff(retail["shot"], mod["shot"], (0.0, 0.2, 1.0, 0.85))
    ok = facts["files"] > 0 and share < 0.03
    return ok, f"{facts['model']}: {facts['files']} file(s) rewritten by the import; the map differs from " \
               f"retail on {share:.1%} of the screen (accepted below 3%)" + \
               (f"; import warnings: {facts['warnings']}" if facts["warnings"] else "")


CHECKS = [
    Check("B1", "por", "3D Models: Ike's map model exported to .glb and imported back", ["1.0 §4 3D Models ⭐ (POR)"],
          play=map_shot(), judge=judge_same, fixture=body_round_trip("lord"), start=Jump(2)),
    Check("B1r", "rd", "3D Models: Micaiah's map model exported to .glb and imported back",
          ["1.0 §4 3D Models ⭐ (RD)"], play=map_shot(), judge=judge_same, fixture=body_round_trip("mikaya1"),
          start=Jump("0101")),
    Check("B2", "por", "3D Models: chapter 1's map terrain exported to .glb and imported back",
          ["1.0 §4 3D Models ⭐ map terrain (POR)"], play=map_shot(), judge=judge_same,
          fixture=terrain_round_trip("bmap02"), start=Jump(2)),
    Check("B2r", "rd", "3D Models: the Prologue's map terrain exported to .glb and imported back",
          ["1.0 §4 3D Models ⭐ map terrain (RD)"], play=map_shot(), judge=judge_same,
          fixture=terrain_round_trip("bmap0101"), start=Jump("0101")),
]
