"""Asset edits shown by the game (1.0 checklist section 4).

Portraits: every picture of the first speaker's portrait file is replaced with flat magenta, as
Portraits › Replace picture does (C8 files get a new palette); the first talk window of the chapter
must then show magenta where the retail run shows the face.
"""
from __future__ import annotations

from .checks_chapters import play_first_talk
from .core import Check, Jump

MAGENTA = (255, 0, 255)


def portrait_fixture(*names: str):
    """``names``: portrait files under Face/ (RD: also Face/wide/<name>, the 16:9 copy)."""
    def fixture(ctx):
        import io
        from PIL import Image
        from fe_modding import portraits
        from fe_modding.formats import lz10, tpl
        face = portraits.face_dir(ctx.project)
        paths = [face / n for n in names]
        if ctx.wii:
            paths += [face / "wide" / n for n in names if (face / "wide" / n).is_file()]
        for path in paths:
            data = lz10.decompress(path.read_bytes())
            infos = tpl.read_tpl_image_info(io.BytesIO(data))
            images = {i: Image.new("RGBA", (info.width, info.height), MAGENTA + (255,)) for i, info in enumerate(infos)}
            if all(i.format == tpl.FORMAT_C8 for i in infos):
                data = portraits.rebuild_with_new_palette(data, images)
            else:
                for index, image in images.items():
                    data = tpl.replace_image(data, index, image)
            ctx.project.write_keeping_original(path, lz10.compress(data))
        ctx.facts.update(files=[p.name for p in paths])
    return fixture


def _magenta_share(path: str) -> float:
    from PIL import Image
    image = Image.open(path).convert("RGB")
    pixels = list(image.getdata())
    # the game draws the face through its own colour pass: magenta comes out near (184, 0, 184)
    return sum(1 for r, g, b in pixels if r > 140 and b > 140 and g < 60 and abs(r - b) < 40) / len(pixels)


def judge_portrait(mod, retail, facts):
    a, b = _magenta_share(retail["shot"]), _magenta_share(mod["shot"])
    return b > 0.01 and a < 0.001, f"magenta on {b:.1%} of the first talk window (retail {a:.2%}); files {facts['files']}"


CHECKS = [
    Check("P1", "por", "Portraits: a replaced picture is the face the talk window shows", ["1.0 §4 Portraits ⭐ (POR)"],
          play=play_first_talk, judge=judge_portrait, fixture=portrait_fixture("TIAMAT.cms", "L_TIAMAT.cms"),
          start=Jump(2)),
    Check("P1r", "rd", "Portraits: a replaced picture is the face the talk window shows (4:3 and 16:9 files)",
          ["1.0 §4 Portraits ⭐ (RD)"], play=play_first_talk, judge=judge_portrait,
          fixture=portrait_fixture("EDDIE.cms"), start=Jump("0101")),
]


# -- item icons: the Iron Sword's (PoR) / Light's (RD) icon replaced with flat magenta, as
# Icons › Replace icon does (RD: the 16:9 sheet too). The lord's unit window at the first player phase shows it.

def icon_fixture(iid: str):
    def fixture(ctx):
        from PIL import Image
        from fe_modding.formats import lz10, tpl
        from fe_modding.game_profile import files_root_of
        if ctx.wii:
            from fe_modding.formats import fe10data
            data = ctx.project.read_logical("game_data")
            icon = next(r for r in fe10data.read_table(data, "item") if r.id == iid).values["icon"]
            sheets = [("window/icon.cms", 0, (24, 24)), ("window/icon_wide.cms", 0, (18, 24))]
        else:
            icon = next(i for i in ctx.data.items if i.iid == iid).icon
            sheets = [("window/icon.tpl", 0, (24, 24))]
        cell = 96 + icon
        for rel, image, (cw, ch) in sheets:
            path = files_root_of(ctx.project) / rel
            raw = path.read_bytes()
            compressed = raw[:1] == b"\x10"
            data = lz10.decompress(raw) if compressed else raw
            import io
            width = tpl.read_tpl_image_info(io.BytesIO(data))[image].width
            cols = width // cw
            x, y = (cell % cols) * cw, (cell // cols) * ch
            data = tpl.replace_region(data, image, (x, y, x + cw, y + ch), Image.new("RGBA", (cw, ch), MAGENTA + (255,)))
            ctx.project.write_keeping_original(path, lz10.compress(data) if compressed else data)
        ctx.facts.update(icon=icon, cell=cell)
    return fixture


def judge_icon(mod, retail, facts):
    from .oracles import magenta_pixels
    a, b = magenta_pixels(retail["shot"]), magenta_pixels(mod["shot"])
    return b >= 40 and a < 5, f"icon {facts['icon']} (sheet cell {facts['cell']}): {b} magenta pixels on the map " \
                              f"screen with the unit window open (retail {a})"


from .oracles import map_shot  # noqa: E402

CHECKS += [
    Check("I1", "por", "Icons: a replaced item icon is what the unit window shows", ["1.0 §4 Icons (POR)"],
          play=map_shot(), judge=judge_icon, fixture=icon_fixture("IID_IRONSWORD"), start=Jump(2)),
    Check("I1r", "rd", "Icons: a replaced item icon is what the unit window shows (4:3 and 16:9 sheets)",
          ["1.0 §4 Icons (RD)"], play=map_shot(), judge=judge_icon, fixture=icon_fixture("IID_LIGHT"),
          start=Jump("0101")),
]


# -- videos: Movie/opening.thp replaced with 4 s of flat magenta (silent audio) made by the app's THP encoder,
# the same size, frame rate and audio layout as retail; the game plays it after the logo with no input.

from .core import Title  # noqa: E402


def video_fixture(rel: str = "Movie/opening.thp", seconds: float = 4.0):
    def fixture(ctx):
        from PIL import Image
        from fe_modding.formats import thp
        from fe_modding.game_profile import files_root_of
        path = files_root_of(ctx.project) / rel
        info = thp.read_info_path(path)
        frames = [Image.new("RGB", (info.width, info.height), MAGENTA)] * int(info.fps * seconds)
        pcm = [[0] * int(info.audio_frequency * seconds) for _ in range(info.audio_channels)] if info.has_audio else None
        data = thp.encode_thp(frames, pcm, info.audio_frequency or 32000, info.fps, audio_tracks=info.audio_tracks)
        ctx.project.write_keeping_original(path, data)
        ctx.facts.update(size=[info.width, info.height], fps=info.fps, frames=len(frames))
    return fixture


def play_movie(driver, facts):
    import time
    driver.until(lambda s: "E_THPP" in s.names and time.time() - driver.since > 1.5, 3, policy=False, label="movie")
    return {"shot": str(driver.snap("movie"))}


def judge_movie(mod, retail, facts):
    from .oracles import magenta_pixels
    from PIL import Image
    total = Image.open(mod["shot"]).size
    share = magenta_pixels(mod["shot"]) / (total[0] * total[1])
    base = magenta_pixels(retail["shot"]) / (total[0] * total[1])
    return share > 0.3 and base < 0.01, f"the opening movie is magenta on {share:.0%} of the screen (retail " \
                                        f"{base:.1%}); {facts['frames']} frames {facts['size']} at {facts['fps']} fps"


CHECKS.append(Check("V1", "por", "Videos: a replaced opening movie is what plays", ["1.0 §4 Videos (POR)"],
                    play=play_movie, judge=judge_movie, fixture=video_fixture(), start=Title()))
