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
from pathlib import Path

from .core import SWEEP_SAVES, Check, Jump
from .oracles import region_diff

POR_BASE_SAVE = SWEEP_SAVES["por"] / "010_chapter09_01-GFEE-FIREEMBLEM8J.gci"   # base before Ch.8
RD_4_1_SAVE = SWEEP_SAVES["rd"] / "035_chapter35_FE10_US.dat"                 # continues into 4-1
RD_1_2_SAVE = SWEEP_SAVES["rd"] / "004_chapter03_FE10_US.dat"                 # continues into 1-2, Micaiah in the
#                                                                                 party (a jump fields Laura alone)
RD_1_9_SAVE = SWEEP_SAVES["rd"] / "011_chapter10_FE10_US.dat"                 # continues into 1-9


def card_from(path, name):
    return lambda ctx, variant: {name: path.read_bytes()}


def walk(reach, presses, minutes: float = 10.0, settle: float = 1.5, hold: str = ""):
    """Play (sweep policy) until ``reach(state)``, then press each entry of ``presses`` (a button, or
    ``"X+Y"`` for a chord: X held while Y is pressed) and screenshot after each."""
    def play(driver, facts):
        driver.until(reach, minutes, label="walk start")     # at once: the sweep policy leaves a base after 1 s
        time.sleep(settle)
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
        good = [shot for shot in shots if shot not in ("None", "") and Path(shot).is_file()
                and Path(shot).stat().st_size > 1000]
        if len(good) < len(shots):          # a screenshot can fail now and then (SH1 retail, 2026-11-24): retake
            time.sleep(1.0)
            again = driver.snap(f"walk_{len(presses):02d}_again")
            good += [str(again)] if again else []
        return {"shot": good[-1] if good else "", "shots": shots, "names": sorted(driver.state().names)}
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
#: base menu (cursor on Outfit): Outfit, Ike, his Shop command (four rows down), then Armory, the first entry of
#: the shop list (PROBE_por_base3, 2026-11-19; the old path opened Info)
SHOP_PATH = ["A", "A", "Down", "Down", "Down", "Down", "A", "A", "wait2"]


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
    """A screenshot every second for as long as the world map is up (the route line draws at some point in the
    scene; the narration windows are advanced with A every few seconds)."""
    driver.until(lambda s: "E_GMapDisp" in s.names, 10, label="world map")
    k, names = 0, set()
    deadline = time.time() + 120
    while time.time() < deadline and k < 60:
        st = driver.state()
        if "E_GMapDisp" not in st.names:
            break
        names |= set(st.names)
        driver.snap(f"map_{k:02d}")
        k += 1
        if k % 4 == 0:
            driver.press("A", gap=0.3)
        time.sleep(1.0)
    return {"frames": k, "names": sorted(names), "shot": str(driver.snap("world_map"))}


def judge_world_map(mod, retail, facts):
    from pathlib import Path as _P
    shares = []
    for k in range(min(mod["frames"], retail["frames"])):
        a, b = _P(retail["shot"]).parent / f"map_{k:02d}.png", _P(mod["shot"]).parent / f"map_{k:02d}.png"
        if a.is_file() and b.is_file():
            shares.append(region_diff(str(a), str(b)))
    best = max(shares, default=0.0)
    lines = [n for n in mod["names"] if "Curve" in n or "Line" in n or "Route" in n]
    return best > 0.003, (f"{facts['change']}: across {len(shares)} world-map frames the most different one "
                          f"differs from retail on {best:.2%}; route processes {lines} (map_*.png)")


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
          card=card_from(POR_BASE_SAVE, "01-GFEE-FIREEMBLEM8J.gci"), retail=False, minutes=12, probe=True),
    Check("PROBE_por_base2", "por", "probe: PoR base menu from its first entry (Outfit, then Manage)", [],
          play=probe(lambda s: bool(s.names & BASE), ["A", "Down", "Down", "B", "Down", "A", "Down", "Down"]),
          judge=lambda m, r, f: (True, "probe"), card=card_from(POR_BASE_SAVE, "01-GFEE-FIREEMBLEM8J.gci"),
          retail=False, minutes=12, probe=True),
    Check("PROBE_por_base3", "por", "probe: PoR base Outfit, Ike picked, his command list", [],
          play=probe(lambda s: bool(s.names & BASE), ["A", "A", "Down", "Down", "Down", "Down", "A"]),
          judge=lambda m, r, f: (True, "probe"), card=card_from(POR_BASE_SAVE, "01-GFEE-FIREEMBLEM8J.gci"),
          retail=False, minutes=12, probe=True),
    Check("PROBE_por_extras", "por", "probe: PoR title extras", [], play=probe(
          lambda s: bool({"E_Title", "TitleProc"} & s.names), ["A", "Down", "A", "Down", "A", "Down", "A"], 3),
          judge=lambda m, r, f: (True, "probe"), retail=False, probe=True),
    Check("PROBE_rd_extras", "rd", "probe: RD title extras", [], play=probe(
          lambda s: bool({"E_Title", "TitleProc"} & s.names), ["A", "Down", "A", "Down", "A", "Down", "A"], 3),
          judge=lambda m, r, f: (True, "probe"), retail=False, probe=True),
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
    # the title's attract movie (TitleMovieProc) plays first; s1 comes after New Game
    driver.until(lambda s: "E_THPP" in s.names and "TitleMovieProc" not in s.names, 15, label="s1 movie")
    best, shots = 0, []
    deadline = time.time() + 240
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


def caption_band(path: str) -> tuple[float, float]:
    """(stddev, mean) of the caption band's grey levels: text has a high stddev; the replaced flat pictures a low
    one over a brighter band. Captions are intensity textures, so the magenta fixture shows grey (2026-11-19)."""
    from PIL import Image, ImageStat
    img = Image.open(path).convert("L")
    w, h = img.size
    stat = ImageStat.Stat(img.crop((int(w * 0.33), int(h * 0.90), int(w * 0.67), int(h * 0.95))))
    return stat.stddev[0], stat.mean[0]


def _flat_frames(obs) -> int:
    from pathlib import Path
    count = 0
    for shot in Path(obs["shot"]).parent.glob("movie_*.png"):
        std, mean = caption_band(str(shot))
        count += std < 10 and mean > 80
    return count


def judge_captions(mod, retail, facts):
    m, r = _flat_frames(mod), _flat_frames(retail)
    return m >= 3 and r == 0, (f"{facts['change']}: {m} movie frames show a flat replaced picture in the caption "
                               f"band (retail {r}); captions are intensity textures, so magenta draws grey "
                               f"(movie_*.png)")


# -- R6 (RD): the paired Sothe/Micaiah model after Replace rig, shown by a scripted rescue on 1-1 ------------------

RESCUE_EVENT = """
# In-game check: Sothe picks Micaiah up (the paired model)
@on_phase(turn_from=1, turn_to=1, phase="player")
def CheckPairedModel():
    InstantDisposRank("bmap0103_z01")
    UnitSetPos(UnitGetByPID("PID_MICAIAH"), 15, 22)
    UnitSetPos(UnitGetByPID("PID_SOTHE"), 15, 22)
    UnitRescue(UnitGetByPID("PID_SOTHE"), UnitGetByPID("PID_MICAIAH"))
"""


def rescue_setup(ctx):
    # 1-2: Sothe is its z01 reinforcement (the chapter's script deploys him at turn 3 on (9, 11)); a jump or a
    # turn-1 sweep save never has him in the party, so the event deploys him. The 1-2 save brings Micaiah (a jump
    # fields Laura alone); she is set on (15, 22) and Sothe on the nearest free tile, next to her
    ctx.append_chapter_script("0103", RESCUE_EVENT)


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
    where = {u.pid: [u.x, u.y] for u in game.units() if u.pid in ("PID_SOTHE", "PID_MICAIAH", "PID_LAURA")}
    return {"carrying": bool(status & 0x2), "status": status, "where": where, "shot": str(driver.snap("rescue"))}


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
          card=card_from(RD_1_2_SAVE, "FE10_US.dat"), minutes=12),
]

RD_BASE_SAVE = SWEEP_SAVES["rd"] / "006_chapter05_FE10_US.dat"   # base before 1-4 (forge: SAVE-03)

CHECKS.append(Check("PROBE_rd_base", "rd", "probe: RD base menu (forge path for SAVE-03)", [], play=probe(
    lambda s: bool(s.names & BASE), ["Down", "A", "B", "Down", "A", "B", "Down", "A", "B", "Down", "A", "B"]),
    judge=lambda m, r, f: (True, "probe"), card=card_from(RD_BASE_SAVE, "FE10_US.dat"), retail=False, minutes=12,
    probe=True))
