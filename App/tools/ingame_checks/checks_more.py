"""The rest of the 1.0 checklist that shows in the game (PoR chapter 1 unless noted).

* TT1: Game Data › Terrain: Thicket's avoid 10 -> 40 (both runs paint Ike's tile to Thicket); the terrain window.
* TH1: Build › Tile heights: Ike's tile raised (+40 on every corner); the map.
* PP1: Build › Place prop: a tree (``tree_01``) placed next to Ike; the map.
* OB1: Chapter data: the objective Seize -> Rout (normal and Hard keys); the objective window.
* AD1: Animation Data: the fighters' enemy texture number set to the player's (the bandits); the map.
* AI1: deployments' AI: every chapter 1 bandit set to SEQ_NOMOVE; after the first enemy phase, how many moved.
* BC1: Battle Cameras: the unit cameras' ``dist`` doubled (zdbx/camera.dbx); the attack's battle frames.
* FT1: Fonts: Comic Sans imported over the talk font; the first talk window.

Most are screen comparisons with retail; every picture is kept, and the results table says how much moved.
"""
from __future__ import annotations

from .checks_chapters import play_first_talk, terrain_fixture
from .checks_code import judge_fight_looks_different, play_attack, setup_attack
from .core import Check, Jump
from .oracles import map_shot, region_diff
from .ram_view import GameRam

IKE_TILE = (12, 17)
START = Jump(2)


def _map_files(ctx, folder="bmap02"):
    from fe_modding.formats import lz10, pak
    from fe_modding.game_profile import files_root_of
    path = files_root_of(ctx.project) / "zmap" / folder / "map.cmp"
    raw = path.read_bytes()
    compressed = raw[:1] == b"\x10"
    packed = lz10.decompress(raw) if compressed else raw
    entries = pak.read_pak_entries(packed)
    return path, compressed, entries, {e.name: pak.read_pak_file_content(packed, e) for e in entries}


def _write_map(ctx, path, compressed, entries, files):
    from fe_modding.formats import lz10, pak
    names = [e.name for e in entries] + [n for n in files if n not in {e.name for e in entries}]
    reserved = [e.reserved for e in entries] + [0] * (len(names) - len(entries))
    out = pak.pack_pak([(n, files[n]) for n in names], reserved)
    ctx.project.write_keeping_original(path, lz10.compress(out) if compressed else out)


def judge_screen(box=(0.0, 0.0, 1.0, 1.0), at_least=0.002, label=""):
    def judge(mod, retail, facts):
        share = region_diff(retail["shot"], mod["shot"], box)
        return share > at_least, f"{facts.get('change', label)}: {share:.2%} of the {label or 'screen'} differs from retail"
    return judge


# -- TT1 ---------------------------------------------------------------------------------------------------------

def setup_paint(ctx):
    terrain_fixture("bmap02", IKE_TILE)(ctx)


def fixture_thicket_avoid(ctx):
    from fe_modding.formats import fe8data
    from dataclasses import replace
    t = next(t for t in fe8data.read_terrain_types(ctx.fe8) if t.name == "茂み")
    ctx.fe8 = fe8data.patch_terrain_stats(ctx.fe8, t.index, fe8data.terrain_stats_block(replace(t, avoid=40)),
                                          own_block=True)
    ctx.facts.update(change=f"Thicket avoid {t.avoid} -> 40")


# -- TH1 / PP1 ----------------------------------------------------------------------------------------------------

def fixture_raise_tile(ctx):
    from fe_modding import map_heights
    from fe_modding.formats import map_file
    path, compressed, entries, files = _map_files(ctx)
    data = map_file.read_map_bytes(files["map.bin"])
    corners = map_heights.tile_corners(data, IKE_TILE)
    raised = {layer: tuple(v + 40 for v in values) for layer, values in corners.items()}
    files["map.bin"] = map_heights.set_tile_corners(files["map.bin"], {IKE_TILE: raised})
    _write_map(ctx, path, compressed, entries, files)
    ctx.facts.update(change=f"tile {IKE_TILE} corners {corners} raised by 40")


def fixture_place_tree(ctx):
    from fe_modding import map_props
    path, compressed, entries, files = _map_files(ctx)
    index = map_props.place_prop(files, "tree_01", IKE_TILE[0] + 1, IKE_TILE[1])
    _write_map(ctx, path, compressed, entries, files)
    ctx.facts.update(change=f"tree_01 placed at {(IKE_TILE[0] + 1, IKE_TILE[1])} (instance {index})")


# -- OB1 ----------------------------------------------------------------------------------------------------------

def fixture_objective(ctx):
    from fe_modding.formats import fe8data
    record = ctx.chapter_record(2)
    for field in ("objective0", "hard_objective0"):
        ctx.fe8 = fe8data.patch_chapter_field(ctx.fe8, record.index, field, "MW_全滅")
    ctx.facts.update(change=f"chapter 1 objective {record.objectives[0]} -> MW_全滅 (Rout)")


# -- AD1 ----------------------------------------------------------------------------------------------------------

def fixture_army_texture(ctx):
    from fe_modding import model_slots
    # chapter 1's bandits are fighters; the lord has one texture for every army, generic classes have four
    record = next(r for r in model_slots.map_model_records(ctx.project) if r.base_aid == "AID_FIGHTER")
    ids = record.texture_ids
    new = (ids[0], ids[0], ids[2], ids[3])
    model_slots.set_map_textures(ctx.project, "AID_FIGHTER", new)
    ctx.facts.update(change=f"AID_FIGHTER army textures {ids} -> {new} (enemy fighters in player colours)")


# -- AI1 ----------------------------------------------------------------------------------------------------------

def fixture_bandits_stay(ctx):
    from fe_modding.formats import dispo
    field = dispo.FIELD
    docs = {n: d for n, d in ctx.dispos("bmap02").items() if n == "dispos_h.bin"}
    count = 0
    for doc in docs.values():
        for section in doc.sections:
            if section.name.endswith("_first_h"):
                for unit in section.units:
                    if str(unit[field["pid"]]).startswith("PID_BANDIT"):
                        unit[field["seq_move"]] = "SEQ_NOMOVE"
                        unit[field["seq_attack"]] = "SEQ_NOATTACK"     # the attack order moves units too
                        count += 1
    ctx.write_dispos("bmap02", docs)
    ctx.facts.update(change=f"{count} bandits' orders -> SEQ_NOMOVE / SEQ_NOATTACK")


def play_enemy_phase(driver, facts):
    driver.to_player_phase(8)
    game = GameRam(driver.ram, driver.build.game_id)
    before = {u.handle: (u.pid, u.x, u.y) for u in game.units() if u.pid.startswith("PID_BANDIT")}
    driver.end_turns = True
    driver.until(lambda s: s.turn >= 2 and "E_BMapPlph" in s.names, 8, label="turn 2")
    after = {u.handle: (u.x, u.y) for u in game.units() if u.pid.startswith("PID_BANDIT")}
    moves = [[pid, [x, y], list(after[h])] for h, (pid, x, y) in before.items() if after.get(h) not in (None, (x, y))]
    #: _EV bandits are moved by chapter 1's event script, whatever their AI says
    moved = sum(1 for pid, _a, _b in moves if "_EV" not in pid)
    return {"moved": moved, "moves": moves, "bandits": len(before), "shot": str(driver.snap("turn2"))}


def judge_ai(mod, retail, facts):
    ok = mod["moved"] == 0 and retail["moved"] > 0
    return ok, (f"{facts['change']}: AI-driven bandits that moved in the first enemy phase: edited {mod['moved']} "
                f"of {mod['bandits']}, retail {retail['moved']} of {retail['bandits']}; edited moves "
                f"{mod.get('moves', '(not recorded)')}")


# -- BC1 ----------------------------------------------------------------------------------------------------------

def fixture_camera_dist(ctx):
    from fe_modding import battle_tables
    from fe_modding.formats import battle_camera
    text = battle_tables.read_entry(ctx.project, "zdbx/camera.dbx")
    changed = []
    for rig in battle_camera.read_rigs(text):
        if rig.get("dist"):
            value = float(rig.get("dist").split(",")[0]) * 5
            text = battle_camera.set_rig_field(text, rig.name, "dist", f"{value:.1f}")
            changed.append(rig.name)
    # the side view of a normal fight is cam0, the scene camera, which has a position and no dist (round 2:
    # dist x5 alone left every frame as retail)
    text = battle_camera.set_rig_field(text, "cam0", "pos", "0.0, 25.0, 150.0")
    battle_tables.write_entry(ctx.project, "zdbx/camera.dbx", text)
    # round 3: rig edits alone barely changed a fight (2%): each xcam script's keyframes carry their own dist,
    # which films the attack. Every keyframe of every script three times farther.
    from dataclasses import replace
    scripts = 0
    for name in battle_tables.entry_names(ctx.project, "xcam", ".dbx"):
        source = battle_tables.read_entry(ctx.project, name)
        try:
            script = battle_camera.read_script(source)
        except battle_camera.CameraError:
            continue
        frames = [replace(f, dist=f.dist * 3) for f in script.keyframes]
        battle_tables.write_entry(ctx.project, name, battle_camera.set_script_keyframes(source, frames))
        scripts += 1
    ctx.facts.update(change=f"camera dist x5 on {changed}; cam0 pos (0, 9.5, 60) -> (0, 25, 150); "
                            f"every keyframe of {scripts} xcam scripts 3x farther")


# -- FT1 ----------------------------------------------------------------------------------------------------------

def fixture_talk_font(ctx):
    from fe_modding.formats import fe9_font, lz10
    from fe_modding.game_profile import files_root_of
    path = files_root_of(ctx.project) / "Fonts" / "talk.gcf"
    raw = path.read_bytes()
    base = fe9_font.GameFont(lz10.decompress(raw) if raw[:1] == b"\x10" else raw)
    result = fe9_font.import_truetype(base, "C:/Windows/Fonts/comic.ttf")
    ctx.project.write_keeping_original(path, result.data)
    ctx.facts.update(change=f"Comic Sans over the talk font ({len(result.replaced)} glyphs replaced)")


MAP = (0.0, 0.2, 1.0, 0.85)
CHECKS = [
    Check("TT1", "por", "Terrain stats: Thicket's avoid shows in the terrain window", ["1.0 §2 Game Data Terrain (POR)"],
          play=map_shot(), judge=judge_screen((0.05, 0.05, 0.37, 0.2), 0.002, "terrain window"), setup=setup_paint,
          fixture=fixture_thicket_avoid, start=START),
    Check("TH1", "por", "Tile heights: Ike's tile raised", ["1.0 §3 Build Tile heights (POR)"], play=map_shot(),
          judge=judge_screen(MAP, 0.002, "map"), fixture=fixture_raise_tile, start=START),
    Check("PP1", "por", "Place prop: a tree next to Ike", ["1.0 §3 Build Place prop (POR)"], play=map_shot(),
          judge=judge_screen(MAP, 0.002, "map"), fixture=fixture_place_tree, start=START),
    Check("OB1", "por", "Chapter data: the objective shows as Rout", ["1.0 §3 Chapter data objective (POR)"],
          play=map_shot(), judge=judge_screen((0.0, 0.0, 0.4, 0.4), 0.005, "objective window"),
          fixture=fixture_objective, start=START),
    Check("AD1", "por", "Animation Data: enemy fighters drawn with the player texture", ["1.0 §4 Animation Data (POR)"],
          play=map_shot(), judge=judge_screen(MAP, 0.001, "map"), fixture=fixture_army_texture, start=START),
    Check("AI1", "por", "Deployment AI: bandits told not to move stay put", ["1.0 §5 AI (CP)"],
          play=play_enemy_phase, judge=judge_ai, fixture=fixture_bandits_stay, start=START, minutes=12),
    Check("BC1", "por", "Battle Cameras: the unit cameras pulled back", ["1.0 §4 Battle Cameras (POR)"],
          play=play_attack, judge=judge_fight_looks_different, setup=setup_attack, fixture=fixture_camera_dist,
          start=START),
    Check("FT1", "por", "Fonts: an imported TrueType font draws the dialogue", ["1.0 §4 Fonts (POR)"],
          play=play_first_talk, judge=judge_screen((0.0, 0.6, 1.0, 1.0), 0.01, "talk window"),
          fixture=fixture_talk_font, start=START),
]
