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
