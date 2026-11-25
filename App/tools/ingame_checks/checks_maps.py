"""Radiant Dawn map data in the game (RD inventory MAP-01, MAP-02, MAP-04), on the Prologue's ``bmap0101``.

Every check jumps into the Prologue (Hard) and screenshots the first player phase. ``MAPBASE`` is the
unedited reference all the others are compared with (one retail run instead of one per check):

* ``MS_<field>``: one ``mapshader`` control changed (8-bit values inverted, the signed one negated), as
  Map Settings writes it (``patch_shader_field``). The water pass is already confirmed.
* ``MP_<group>_<bit>``: one prop-flag bit flipped on the market stalls (``mrkt_*``, on screen at the start)
  through ``patch_object_field``, as the map's prop panel writes it.
* ``MC``: the terrain-height ceiling (MAP-02) from 1.0 to 0.25.

The judge records how much of the map changed and keeps the shots; what a change means is read from the
pictures (the results table says "differs" or "no visible change"). A bit with no visible change can still
work off screen, so "no visible change" is reported, not failed.
"""
from __future__ import annotations

import json

from .core import ROOT, Check, Jump
from .oracles import map_shot, region_diff

FOLDER = "bmap0101"
STALLS = "mrkt"
MAP_AREA = (0.0, 0.22, 1.0, 0.88)
SKIP_SHADER = {"water"}


def _edit_map_bin(ctx, edit):
    from fe_modding.formats import lz10, map_file, pak
    from fe_modding.game_profile import files_root_of
    path = files_root_of(ctx.project) / "zmap" / FOLDER / "map.cmp"
    raw = path.read_bytes()
    compressed = raw[:1] == b"\x10"
    packed = lz10.decompress(raw) if compressed else raw
    entries = pak.read_pak_entries(packed)
    files = [(e.name, pak.read_pak_file_content(packed, e)) for e in entries]
    files = [(n, edit(c, map_file.read_map_bytes(c)) if n == "map.bin" else c) for n, c in files]
    out = pak.pack_pak(files, [e.reserved for e in entries])
    ctx.project.write_keeping_original(path, lz10.compress(out) if compressed else out)


def shader_fixture(field: str):
    def fixture(ctx):
        from fe_modding.formats import map_file

        def edit(data, parsed):
            old = parsed.shader.values[field]
            fmt = map_file.RD_SHADER_FIELDS[field][1]
            new = -old if fmt == ">h" else (255 - old)
            if new == old:
                new = (old + 128) % 256
            ctx.facts.update(change=f"mapshader {field} {old} -> {new}")
            return map_file.patch_shader_field(data, parsed.shader, field, new)
        _edit_map_bin(ctx, edit)
    return fixture


def prop_fixture(group: str, bit: int, label: str):
    def fixture(ctx):
        from fe_modding.formats import map_file

        def edit(data, parsed):
            stalls = [o for o in parsed.build_desc if (o.filename or "").startswith(STALLS)]
            if not stalls:
                raise RuntimeError(f"no {STALLS}* objects on {FOLDER}")
            for o in stalls:
                data = map_file.patch_object_field(data, o, group, getattr(o, group) ^ bit)
            ctx.facts.update(change=f"{group} bit {bit:#04x} ({label}) flipped on {len(stalls)} stall descriptor(s)")
            return data
        _edit_map_bin(ctx, edit)
    return fixture


def ceiling_fixture(value: float):
    def fixture(ctx):
        from fe_modding.formats import map_file

        def edit(data, parsed):
            ctx.facts.update(change=f"terrain_height_ceiling {parsed.rd.terrain_height_ceiling} -> {value}")
            return map_file.patch_rd_map_field(data, parsed.rd, "terrain_height_ceiling", value)
        _edit_map_bin(ctx, edit)
    return fixture


def judge_vs_base(mod, retail, facts):
    path = ROOT / "out" / "MAPBASE_mod" / "observations.json"
    if not path.is_file():
        return False, "run MAPBASE first"
    base = json.loads(path.read_text(encoding="utf-8"))
    share = region_diff(base["shot"], mod["shot"], MAP_AREA)
    seen = "differs" if share > 0.01 else "no visible change"
    return True, f"{facts['change']}: {seen} ({share:.1%} of the map against MAPBASE; see shots)"


# -- MP_c_02: stalls told to load a .ga they don't have: the opening event never ends (game behaviour, 2026-11-18).
# The check asserts the hang and that the project check warns about it on the same edit.

def hang_fixture(group: str, bit: int, label: str):
    edit = prop_fixture(group, bit, label)

    def fixture(ctx):
        from fe_modding import validator
        edit(ctx)
        issues: list = []
        validator.check_map_animations(ctx.project, issues)
        ctx.facts.update(warned=[i.message[:90] for i in issues if FOLDER in i.where])
    return fixture


def play_until_hang(minutes: float = 4.0):
    def play(driver, facts):
        try:
            driver.to_player_phase(minutes)
        except Exception as error:  # noqa: BLE001 - the expected outcome
            return {"hung": True, "why": str(error)[:160], "shot": str(driver.snap("hang"))}
        return {"hung": False, "shot": str(driver.snap("map"))}
    return play


def judge_hang_warned(mod, retail, facts):
    warned = facts.get("warned", [])
    return mod["hung"] and bool(warned), (
        f"{facts['change']}: the opening {'never ends' if mod['hung'] else 'ends'} "
        f"({mod.get('why', 'player phase reached')}); the project check "
        f"{'warns: ' + warned[0] if warned else 'says nothing'}")


def judge_base(mod, retail, facts):
    return True, "reference screenshot of the unedited Prologue"


def _checks():
    from fe_modding.formats import map_file
    from fe_modding.map_props import PROP_FLAG_GROUPS, _RD_MAP_ROLE
    out = [Check("MAPBASE", "rd", "Map reference: the Prologue as extracted", ["MAP-01/02/04 reference"],
                 play=map_shot(), judge=judge_base, start=Jump("0101"), retail=False)]
    for field in map_file.RD_SHADER_FIELDS:
        if field not in SKIP_SHADER:
            out.append(Check(f"MS_{field}", "rd", f"mapshader {field} changed", ["MAP-01 mapshader"],
                             play=map_shot(), judge=judge_vs_base, fixture=shader_fixture(field),
                             start=Jump("0101"), retail=False))
    groups = [_RD_MAP_ROLE, *PROP_FLAG_GROUPS[1:]]
    for group, _title, bits in groups:
        for bit, label in bits:
            if group == "flag_bits_c" and bit == 0x02:
                out.append(Check("MP_c_02", "rd", f"prop flag {group} {bit:#04x}: {label} - the opening hangs and "
                                 f"the project check warns", ["MAP-04 prop flags"], play=play_until_hang(),
                                 judge=judge_hang_warned, fixture=hang_fixture(group, bit, label),
                                 start=Jump("0101"), retail=False))
                continue
            out.append(Check(f"MP_{group.removeprefix('flag_bits_')}_{bit:02x}", "rd", f"prop flag {group} {bit:#04x}: "
                             f"{label}", ["MAP-04 prop flags"], play=map_shot(), judge=judge_vs_base,
                             fixture=prop_fixture(group, bit, label), start=Jump("0101"), retail=False))
    out.append(Check("MC", "rd", "terrain-height ceiling 1.0 -> 0.25", ["MAP-02 ceiling"], play=map_shot(),
                     judge=judge_vs_base, fixture=ceiling_fixture(0.25), start=Jump("0101"), retail=False))
    return out


CHECKS = _checks()
