"""Checks that walk the game's menus (1.0 checklist: Shops, the RD status screen, world-map routes, Sound
Room, tutorials).

A walk loads a chapter-sweep save from the title (or jumps), plays with the sweep policy until a target
screen is up, then presses a fixed list of buttons and screenshots after each (``walk_<n>.png``). The last
screenshot is compared with the retail run's; every step's picture is kept, so a path that lands on the
wrong screen shows at once. The paths were set from probe runs (``probe``); a step list that misses its
screen fails the check rather than passing it.
"""
from __future__ import annotations

import time

from .core import SWEEP_SAVES, Check, Jump
from .oracles import region_diff

POR_BASE_SAVE = SWEEP_SAVES["por"] / "010_chapter09_01-GFEE-FIREEMBLEM8J.gci"   # base before Ch.8
RD_4_1_SAVE = SWEEP_SAVES["rd"] / "035_chapter35_FE10_US.dat"                 # continues into 4-1
RD_1_9_SAVE = SWEEP_SAVES["rd"] / "011_chapter10_FE10_US.dat"                 # continues into 1-9


def card_from(path, name):
    return lambda ctx, variant: {name: path.read_bytes()}


def walk(reach, presses, minutes: float = 10.0, settle: float = 1.5, hold: str = ""):
    """Play (sweep policy) until ``reach(state)``, then press each entry of ``presses`` (a button, or
    ``"X+Y"`` for a chord: X held while Y is pressed) and screenshot after each."""
    def play(driver, facts):
        driver.until(lambda s: reach(s) and time.time() - driver.since > settle, minutes, label="walk start")
        shots = [str(driver.snap("walk_00"))]
        for k, step in enumerate(presses, 1):
            if "+" in step:
                held, tapped = step.split("+")
                driver.chord(held, tapped)
            elif step.startswith("wait"):
                time.sleep(float(step[4:]))
            else:
                driver.press(step, gap=1.2)
            time.sleep(settle)
            shots.append(str(driver.snap(f"walk_{k:02d}")))
        return {"shot": shots[-1], "shots": shots, "names": sorted(driver.state().names)}
    return play


def judge_same(mod, retail, facts):
    share = region_diff(retail["shot"], mod["shot"])
    return share < 0.03, f"{facts.get('change', 'unedited')}: the last screen differs from retail on {share:.1%} " \
                         f"(accepted below 3%; walk_*.png)"


def judge_changed(mod, retail, facts, box=(0.0, 0.0, 1.0, 1.0)):
    share = region_diff(retail["shot"], mod["shot"], box)
    return share > 0.01, f"{facts.get('change', '')}: the last screen differs from retail on {share:.1%} (walk_*.png)"


# -- Shops (PoR, the base before Ch.8): a Silver Sword at the top of chapter 8's armory, all difficulties -------

def shop_fixture(ctx):
    from fe_modding.formats import shop
    from fe_modding.game_profile import files_root_of
    for name in ("shopitem_h.bin", "shopitem_n.bin", "shopitem_m.bin"):
        path = files_root_of(ctx.project) / "Shop" / name
        doc = shop.parse_shop(path.read_bytes())
        for chapter in (8, 9):
            section = doc.section(f"WSHOP_ITEMS_C{chapter:02d}")
            if section is not None and "IID_SILVERSWORD" not in section.items:
                section.items.insert(0, "IID_SILVERSWORD")
        ctx.project.write_keeping_original(path, shop.build_shop(doc))
    ctx.facts.update(change="IID_SILVERSWORD first in the chapter 8/9 armories (h, n, m)")


BASE = {"BasesProc", "BaseProc"}
#: base menu: the Shop entry opens the Armory first (path from the probe run; see the module doc)
SHOP_PATH = ["Down", "Down", "Down", "A", "A"]


# -- R4 (RD 4-1): the army group re-saved through the story flow; the status screen's army name ----------------

def army_fixture(ctx):
    from fe_modding.game_code.story_flow import open_story_flow
    flow, why = open_story_flow(ctx.project)
    if flow is None or not getattr(flow, "armies", None):
        raise RuntimeError(f"no army control in the story flow: {why}")
    army = flow.army("0402")
    flow.set_army("0402", army)
    ctx.drop_editor()
    ctx.facts.update(change=f"4-1's army group written again through Story order ({army})")


# -- world-map routes (RD 1-9's opening): every route line moved 150 px right --------------------------------------

def curves_fixture(ctx):
    from fe_modding.formats import fe10_gmap_curve as curves
    from fe_modding.game_profile import files_root_of
    folder = files_root_of(ctx.project) / "gmap" / "curve"
    count = 0
    for path in sorted(folder.glob("curve0*.bin")):
        curve = curves.read_curve(path.read_bytes())
        for point in curve.points:
            point.x += 150
        ctx.project.write_keeping_original(path, curves.build_curve(curve))
        count += 1
    ctx.facts.update(change=f"{count} route curves moved 150 px right")


def play_world_map(driver, facts):
    driver.until(lambda s: "E_GMapDisp" in s.names, 10, label="world map")
    time.sleep(6)               # let the line draw (65-300 frames)
    return {"shot": str(driver.snap("world_map")), "names": sorted(driver.state().names)}


def judge_world_map(mod, retail, facts):
    share = region_diff(retail["shot"], mod["shot"])
    return share > 0.003, f"{facts['change']}: the world map differs from retail on {share:.2%} (see world_map.png)"


# -- probes: screenshots of a path, to set the paths above ------------------------------------------------------

def probe(reach, presses, minutes=10.0):
    return walk(reach, presses, minutes)


CHECKS = [
    Check("SH1", "por", "Shops: an item added to the Armory is listed in the base", ["1.0 §3 Shops (POR)"],
          play=walk(lambda s: bool(s.names & BASE), SHOP_PATH),
          judge=lambda m, r, f: judge_changed(m, r, f, (0.0, 0.15, 1.0, 0.9)), fixture=shop_fixture,
          card=card_from(POR_BASE_SAVE, "01-GFEE-FIREEMBLEM8J.gci"), minutes=12),
    Check("R4", "rd", "Story order army group: 4-1's status screen still names the army",
          ["rdcheck R4"], play=walk(lambda s: "E_BMapPlph" in s.names and s.chapter == 35, ["WB+B"]),
          judge=judge_same, fixture=army_fixture, card=card_from(RD_4_1_SAVE, "FE10_US.dat"), minutes=15),
    Check("WM1r", "rd", "World Map Routes: moved route lines are drawn where edited", ["1.0 §4 World Map Routes (RD)"],
          play=play_world_map, judge=judge_world_map, fixture=curves_fixture,
          card=card_from(RD_1_9_SAVE, "FE10_US.dat"), minutes=12),
]

#: probe runs (no fixture): ``run --set menus --only PROBE_...``, then read out/<id>_mod/shots/walk_*.png
PROBES = [
    Check("PROBE_por_base", "por", "probe: PoR base menu", [], play=probe(lambda s: bool(s.names & BASE),
          ["Down", "Down", "Down", "A", "B", "Down", "A", "B"]), judge=lambda m, r, f: (True, "probe"),
          card=card_from(POR_BASE_SAVE, "01-GFEE-FIREEMBLEM8J.gci"), retail=False, minutes=12),
    Check("PROBE_por_extras", "por", "probe: PoR title extras", [], play=probe(
          lambda s: bool({"E_Title", "TitleProc"} & s.names), ["A", "Down", "A", "Down", "A", "Down", "A"], 3),
          judge=lambda m, r, f: (True, "probe"), retail=False),
    Check("PROBE_rd_extras", "rd", "probe: RD title extras", [], play=probe(
          lambda s: bool({"E_Title", "TitleProc"} & s.names), ["A", "Down", "A", "Down", "A", "Down", "A"], 3),
          judge=lambda m, r, f: (True, "probe"), retail=False),
]
CHECKS += PROBES


# -- EU movie subtitles (RD, RFEP01): every caption picture of the s1 movie made flat magenta ---------------------

def captions_fixture(ctx):
    import io
    from PIL import Image
    from fe_modding.formats import lz10, tpl
    from fe_modding.game_profile import files_root_of
    path = files_root_of(ctx.project) / "Movie" / "Caption" / "e_s1.cms"
    data = lz10.decompress(path.read_bytes())
    infos = tpl.read_tpl_image_info(io.BytesIO(data))
    for index, info in enumerate(infos):
        data = tpl.replace_image(data, index, Image.new("RGBA", (info.width, info.height), (255, 0, 255, 255)))
    ctx.project.write_keeping_original(path, lz10.compress(data))
    ctx.facts.update(change=f"e_s1.cms: {len(infos)} caption pictures made magenta")


def play_movie_captions(driver, facts):
    """New Game plays s1 before the Prologue; screenshots every 2 s while a movie is up."""
    from .oracles import magenta_pixels
    driver.until(lambda s: "E_THPP" in s.names, 12, label="s1 movie")
    best, shots = 0, []
    deadline = time.time() + 90
    k = 0
    while time.time() < deadline and "E_THPP" in driver.state().names:
        path = driver.snap(f"movie_{k:02d}")
        k += 1
        if path:
            count = magenta_pixels(str(path))
            shots.append(count)
            best = max(best, count)
        time.sleep(2)
    return {"best": best, "counts": shots, "shot": str(path) if shots else ""}


def judge_captions(mod, retail, facts):
    return mod["best"] > 300 and retail["best"] < 50, (f"{facts['change']}: up to {mod['best']} magenta pixels "
                                                       f"during the movie, retail {retail['best']} (movie_*.png)")


# -- R6 (RD): the paired Sothe/Micaiah model after Replace rig, shown by a scripted rescue on 1-1 ------------------

RESCUE_EVENT = """
# In-game check: Sothe picks Micaiah up (the paired model)
@on_phase(turn_from=1, turn_to=1, phase="player")
def CheckPairedModel():
    UnitRescue(UnitGetByPID("PID_SOTHE"), UnitGetByPID("PID_MICAIAH"))
"""


def rescue_setup(ctx):
    ctx.append_chapter_script("0102", RESCUE_EVENT)


def rig_fixture(ctx):
    import tempfile
    from pathlib import Path
    from fe_modding.game_profile import files_root_of
    from fe_modding.gui import model_viewer as mv
    container = files_root_of(ctx.project) / "ymu" / "sothe1_mikaya2" / "pack.cmp"
    with tempfile.TemporaryDirectory() as temp:
        glb = Path(temp) / "rig.glb"
        glb.write_bytes(mv.export_set_glb(container))
        result = mv.replace_rig_with_glb(container, glb)
    for path, data in result.outputs.items():
        ctx.project.write_keeping_original(Path(path), data)
    ctx.facts.update(change=f"ymu/sothe1_mikaya2 through Replace rig ({len(result.outputs)} files)")


def play_rescue(driver, facts):
    from .ram_view import GameRam
    driver.to_player_phase(10)
    time.sleep(2)
    game = GameRam(driver.ram, driver.build.game_id)
    sothe = game.unit("PID_SOTHE")
    status = int.from_bytes(game.record(sothe.address + 0x10C, 4), "big")
    return {"carrying": bool(status & 0x2), "shot": str(driver.snap("rescue"))}


def judge_rescue(mod, retail, facts):
    share = region_diff(retail["shot"], mod["shot"], (0.0, 0.2, 1.0, 0.85))
    ok = mod["carrying"] and retail["carrying"] and share < 0.03
    return ok, (f"{facts['change']}: Sothe carries Micaiah (status bit 0x2) in both runs: "
                f"{retail['carrying']}/{mod['carrying']}; the map differs from retail on {share:.1%}")


CHECKS += [
    Check("ST1e", "rd", "Movie Subtitles: replaced caption pictures show in s1 (European disc)",
          ["1.0 §4 Movie Subtitles (RD EU)"], play=play_movie_captions, judge=judge_captions,
          fixture=captions_fixture, region="RFEP01", minutes=15),
    Check("R6", "rd", "Replace rig on the paired Sothe/Micaiah model: a rescue shows it as retail",
          ["rdcheck R6"], play=play_rescue, judge=judge_rescue, setup=rescue_setup, fixture=rig_fixture,
          start=Jump("0102")),
]

RD_BASE_SAVE = SWEEP_SAVES["rd"] / "006_chapter05_FE10_US.dat"   # base before 1-4 (forge: SAVE-03)

CHECKS.append(Check("PROBE_rd_base", "rd", "probe: RD base menu (forge path for SAVE-03)", [], play=probe(
    lambda s: bool(s.names & BASE), ["Down", "A", "B", "Down", "A", "B", "Down", "A", "B", "Down", "A", "B"]),
    judge=lambda m, r, f: (True, "probe"), card=card_from(RD_BASE_SAVE, "FE10_US.dat"), retail=False, minutes=12))
