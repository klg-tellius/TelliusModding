"""Chapter edits loaded by the game (1.0 checklist section 3).

Deployments: one enemy's start and destination tiles move by one step and its level goes up. The game
can move a unit after reading the deployment (an opening event, a destination tile), so the judge
compares with the retail run: the unit must be exactly that step away from where it is there, at the
edited level.
"""
from __future__ import annotations

from .core import Check, Jump
from .ram_view import GameRam

STEP = (1, 0)
LEVEL_UP = 2


def _dispos_targets(ctx, folder: str):
    """[(name, document)] of the deployment variants the Hard jump reads."""
    from fe_modding.formats import dispo
    if ctx.wii:
        from fe_modding.game_profile import files_root_of
        path = files_root_of(ctx.project) / "zmap" / folder / "dispos_h.bin"
        return [(path, dispo.parse_dispo(path.read_bytes()))]
    return [(name, doc) for name, doc in ctx.dispos(folder).items() if name == "dispos_h.bin"]


def dispo_edit(folder: str, section_suffix: str, pid: str, index: int):
    """Move the ``index``-th ``pid`` of the section ending with ``section_suffix`` by STEP, level +2."""
    def fixture(ctx):
        from fe_modding.formats import dispo
        field = dispo.FIELD
        (where, doc), = _dispos_targets(ctx, folder)
        same = [(s, u) for s in doc.sections for u in s.units if u[field["pid"]] == pid]
        mine = [n for n, (s, _u) in enumerate(same) if s.name.endswith(section_suffix)]
        order = mine[index]
        unit = same[order][1]
        ctx.facts.update(pid=pid, order=order, old_level=unit[field["level"]], new_level=unit[field["level"]] + LEVEL_UP,
                         file_pos=[unit[field["pos_x"]], unit[field["pos_y"]]])
        for axis, step in zip("xy", STEP):
            unit[field[f"pos_{axis}"]] += step
            if unit[field[f"pos2_{axis}"]] or unit[field[f"pos2_{'y' if axis == 'x' else 'x'}"]]:
                unit[field[f"pos2_{axis}"]] += step
        unit[field["level"]] += LEVEL_UP
        dest = "pos2" if unit[field["pos2_x"]] or unit[field["pos2_y"]] else "pos"
        ctx.facts.update(dest=[unit[field[f"{dest}_x"]], unit[field[f"{dest}_y"]]])
        if ctx.wii:
            ctx.project.write_keeping_original(where, dispo.build_dispo(doc))
        else:
            ctx.write_dispos(folder, {where: doc})
    return fixture


def play_units(driver, facts):
    driver.to_player_phase()
    game = GameRam(driver.ram, driver.build.game_id)
    lay = game.layout
    units = [u for u in game.units() if u.pid == facts["pid"]]
    units.sort(key=lambda u: u.handle)
    obs = {"units": [{"handle": u.handle, "x": u.x, "y": u.y, "level": u.level,
                      "raw": game.record(u.address, lay.stride).hex()} for u in units],
           "shot": str(driver.snap("map"))}
    return obs


def judge_dispo(mod, retail, facts):
    """Units of the same character are matched by tile, not by handle (Radiant Dawn doesn't number them
    in deployment order): exactly one retail tile is gone and one tile STEP away from it is new."""
    from collections import Counter
    def tiles(obs):
        return Counter((u["x"], u["y"], u["level"]) for u in obs["units"])
    a, b = tiles(retail), tiles(mod)
    gone, new = list((a - b).elements()), list((b - a).elements())
    if len(gone) != 1 or len(new) != 1:
        return False, f"{facts['pid']}: tiles gone {gone}, new {new} (expected one of each)"
    (x0, y0, l0), (x1, y1, l1) = gone[0], new[0]
    dest = tuple(facts["dest"])     # the unit stands on its destination tile (pos2 when set) at the map start
    ok = (x1, y1) == dest and l0 == facts["old_level"] and l1 == facts["new_level"]
    return ok, f"{facts['pid']}: the edited unit is at {(x1, y1)} level {l1} (edited destination {dest}, level " \
               f"{facts['old_level']} -> {facts['new_level']}); in retail at {(x0, y0)} level {l0}"


def _upper_text(text: str, wii: bool) -> str:
    """The message with every ASCII letter of its plain text in capitals; control codes untouched."""
    from fe_modding.formats import message
    raw = text.encode(message.ENCODING)
    if wii:
        from fe_modding.formats import fe10_message
        out = b"".join(t.raw.upper() if t.kind == "text" and t.raw.isascii() else t.raw
                       for t in fe10_message.tokenize(raw))
    else:
        out = b"".join(part.encode(message.ENCODING).upper() if isinstance(part, str) else part.raw.encode(message.ENCODING)
                       for part in message.tokenize_control_codes(text))
    return out.decode(message.ENCODING)


def dialogue_upper(name: str):
    def fixture(ctx):
        from fe_modding.formats import message
        from fe_modding.game_profile import files_root_of
        path = files_root_of(ctx.project) / "Mess" / name
        messages = message.read_messages_path(path)
        order = message.read_text_order_path(path) if ctx.wii else None
        changed = [message.Message(m.speaker, _upper_text(m.text, ctx.wii)) for m in messages]
        ctx.facts.update(changed=sum(a.text != b.text for a, b in zip(messages, changed)))
        ctx.project.write_keeping_original(path, message.write_messages(changed, order))
    return fixture


def play_first_talk(driver, facts):
    """No input at all: the chapter's opening runs by itself until its first talk window has its text."""
    import time
    driver.until(lambda s: any(n.startswith("E_TalkKeyWait") for n in s.names)
                 or ("E_TalkWindow" in s.names and time.time() - driver.since > 3), 4, policy=False, label="talk")
    time.sleep(1.0)
    return {"shot": str(driver.snap("talk"))}


def judge_talk(mod, retail, facts):
    from PIL import Image, ImageChops
    a, b = Image.open(retail["shot"]).convert("L"), Image.open(mod["shot"]).convert("L")
    w, h = a.size
    diff = ImageChops.difference(a, b).point(lambda v: 255 if v > 40 else 0)
    def share(box):
        region = diff.crop(box)
        return sum(1 for v in region.getdata() if v) / (region.size[0] * region.size[1])
    top, bottom = share((0, 0, w, int(h * 0.55))), share((0, int(h * 0.55), w, h))
    ok = facts["changed"] > 0 and bottom > 0.005 and bottom > 3 * top
    return ok, f"{facts['changed']} messages in capitals; first talk window differs from retail on " \
               f"{bottom:.1%} of the lower screen, {top:.1%} of the upper (see shots)"


def _session(ctx):
    from fe_modding.gui.changelog import ChangeLog
    from fe_modding.gui.fe8_session import Fe8DataSession, Fe10DataSession
    return (Fe10DataSession if ctx.wii else Fe8DataSession)(ctx.project, ChangeLog())


def win_turn_one(*chapters):
    def setup(ctx):
        from tools.chapter_sweep.build import add_auto_win
        for chapter in chapters:
            add_auto_win(ctx.project, chapter)
    return setup


def add_chapter(source: str, after: str):
    """Chapters › Add chapter as the page does it: a copy of ``source`` placed after ``after``."""
    def fixture(ctx):
        from fe_modding.game_code.story_flow import open_story_flow
        from tools.chapter_sweep.build import add_auto_win
        session = _session(ctx)
        adapter = session.adapter
        flow, why = open_story_flow(ctx.project)
        if flow is None:
            raise RuntimeError(f"no story flow: {why}")
        new_id = adapter.free_chapters(ctx.project)[0]
        data, _warnings = adapter.add_story_chapter(ctx.project, source, new_id, "Test chapter", after, flow)
        session.data = data
        session.changed(None)
        session.save()
        ctx.drop_editor()
        add_auto_win(ctx.project, new_id)
        ctx.facts.update(new_id=new_id)
    return fixture


def play_chapter_after(driver, facts):
    """Win the jumped-to chapter on turn 1 and play into the next one: which chapter is it?"""
    first = driver.to_player_phase(8)
    driver.end_turns = True
    nxt = driver.until(lambda s: s.chapter not in (0, first.chapter), 10, label="next chapter")
    driver.end_turns = False
    st = driver.to_player_phase(10)
    return {"first": first.chapter, "next": nxt.chapter, "played": st.chapter, "shot": str(driver.snap("next"))}


def judge_next(mod, retail, facts):
    ok = mod["first"] == retail["first"] and mod["next"] != retail["next"] and mod["played"] == mod["next"]
    return ok, (f"after chapter {mod['first']} retail goes to {retail['next']}, the edited disc to {mod['next']} "
                f"(the added chapter {facts.get('new_id', '')}), whose map reaches its player phase")


def story_skip(chapter: str, nxt: str):
    """Chapters › Story order: ``chapter`` leads to ``nxt`` (skipping the one in between)."""
    def fixture(ctx):
        from fe_modding.game_code.story_flow import open_story_flow
        flow, why = open_story_flow(ctx.project)
        if flow is None:
            raise RuntimeError(f"no story flow: {why}")
        ctx.facts.update(retail_next=flow.next_of(chapter), new_next=nxt)
        flow.set_next(chapter, nxt)
        ctx.drop_editor()
    return fixture


def judge_skip(mod, retail, facts):
    ok = mod["first"] == retail["first"] and mod["next"] == retail["next"] + 1 and mod["played"] == mod["next"]
    return ok, (f"after chapter {mod['first']} retail goes to {retail['next']}, the edited disc to {mod['next']} "
                f"(story order {facts['retail_next']} -> {facts['new_next']}), whose map reaches its player phase")


CHECKS = [
    Check("O1", "por", "Story order: chapter 1 leads to chapter 3", ["1.0 §3 Story order (POR)"],
          play=play_chapter_after, judge=judge_skip, setup=win_turn_one("02"),
          fixture=story_skip("02", "04"), start=Jump(2), minutes=15),
    Check("O1r", "rd", "Story order: 1-1 leads to 1-3", ["1.0 §3 Story order (RD)"],
          play=play_chapter_after, judge=judge_skip, setup=win_turn_one("0102"),
          fixture=story_skip("0102", "0104"), start=Jump("0102"), minutes=15),
    Check("A1", "por", "Add chapter after chapter 1: the game plays it next", ["1.0 §3 Add chapter ⭐ (POR)"],
          play=play_chapter_after, judge=judge_next, setup=win_turn_one("02"),
          fixture=add_chapter("02", "02"), start=Jump(2), minutes=15),
    Check("A1r", "rd", "Add chapter after 1-1: the game plays it next", ["1.0 §3 Add chapter ⭐ (RD)"],
          play=play_chapter_after, judge=judge_next, setup=win_turn_one("0102"),
          fixture=add_chapter("0102", "0102"), start=Jump("0102"), minutes=15),
    Check("T1", "por", "Dialogue: an edited line is what the talk window shows", ["1.0 §3 Dialogue ⭐ (POR)"],
          play=play_first_talk, judge=judge_talk, fixture=dialogue_upper("c02.m"), start=Jump(2)),
    Check("T1r", "rd", "Dialogue: an edited line is what the talk window shows", ["1.0 §3 Dialogue ⭐ (RD)"],
          play=play_first_talk, judge=judge_talk, fixture=dialogue_upper("e_c0101.m"), start=Jump("0101")),
    Check("D1", "por", "Deployment: an enemy's tile and level", ["1.0 §3 Build/Deployment (POR)"],
          play=play_units, judge=judge_dispo, fixture=dispo_edit("bmap02", "_first_h", "PID_BANDIT_MOU", 1),
          start=Jump(2)),
    Check("D1r", "rd", "Deployment: an enemy's tile and level", ["1.0 §3 Build/Deployment (RD)"],
          play=play_units, judge=judge_dispo, fixture=dispo_edit("bmap0101", "_teki_h", "PID_GOON", 1),
          start=Jump("0101")),
]


# -- terrain paint: the lord's start tile painted to Thicket (茂み, Avo 10 Def 1 on both games), as the Build
# tab's paint does; the terrain window (top left, the cursor starts on the lord) must change.

THICKET = "茂み"
TERRAIN_WINDOW = (0.05, 0.05, 0.37, 0.20)


def terrain_fixture(folder: str, tile):
    def fixture(ctx):
        from fe_modding.formats import lz10, map_file, pak
        from fe_modding.game_profile import files_root_of
        path = files_root_of(ctx.project) / "zmap" / folder / "map.cmp"
        raw = path.read_bytes()
        compressed = raw[:1] == b"\x10"
        packed = lz10.decompress(raw) if compressed else raw
        entries = pak.read_pak_entries(packed)
        files = [(e.name, pak.read_pak_file_content(packed, e)) for e in entries]
        files = [(n, map_file.set_tile_terrains(c, {tuple(tile): THICKET}) if n == "map.bin" else c) for n, c in files]
        out = pak.pack_pak(files, [e.reserved for e in entries])
        ctx.project.write_keeping_original(path, lz10.compress(out) if compressed else out)
        ctx.facts.update(tile=list(tile))
    return fixture


def judge_terrain(mod, retail, facts):
    from .oracles import region_diff
    window = region_diff(retail["shot"], mod["shot"], TERRAIN_WINDOW)
    return window > 0.03, f"tile {tuple(facts['tile'])} painted to Thicket: the terrain window differs from retail on " \
                          f"{window:.1%} of its area (see shots)"


# -- weather (RD): Prologue's ChapterData weather from cloudy (曇り) to snow (雪), as Chapter data does.

def weather_fixture(chapter_id: str, weather: str):
    def fixture(ctx):
        from fe_modding.formats import fe10data
        data = ctx.project.read_logical("game_data")
        rec = next(r for r in fe10data.read_table(data, "chapter") if r.id == chapter_id)
        ctx.facts.update(old=rec.values["weather"], new=weather)
        ctx.project.write_logical("game_data", fe10data.patch_field(data, "chapter", rec.index, "weather", weather))
    return fixture


def judge_weather(mod, retail, facts):
    from .oracles import region_diff
    share = region_diff(retail["shot"], mod["shot"], (0.0, 0.2, 1.0, 0.85))
    return share > 0.05, f"weather {facts['old']} -> {facts['new']}: the map differs from retail on {share:.1%} " \
                         f"of the screen below the windows (see shots)"


from .oracles import map_shot  # noqa: E402

CHECKS += [
    Check("T2", "por", "Terrain paint: the lord's tile is Thicket", ["1.0 §3 Build ⭐ terrain paint (POR)"],
          play=map_shot(), judge=judge_terrain, fixture=terrain_fixture("bmap02", (12, 17)), start=Jump(2)),
    Check("T2r", "rd", "Terrain paint: the lord's tile is Thicket", ["1.0 §3 Build ⭐ terrain paint (RD)"],
          play=map_shot(), judge=judge_terrain, fixture=terrain_fixture("bmap0101", (10, 11)), start=Jump("0101")),
    Check("W1r", "rd", "Chapter weather: Prologue in snow", ["1.0 §3 RD weather (open since 2026-10-28)"],
          play=map_shot(), judge=judge_weather, fixture=weather_fixture("C0101", "雪"), start=Jump("0101")),
]
