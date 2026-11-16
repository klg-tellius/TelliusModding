"""Build ``fe_modding/game_code/rd_region_table.py``: the RD Game Code's European and Japanese sites.

Usage::

    python -m tools.build_rd_region_table <folder holding RFEE01/, RFEP01/ and RFEJ01/>

Each region's ``sys/main.dol`` must be the retail one. For every RD entry the US sites are
moved with :mod:`fe_modding.game_code.region_map` and :mod:`fe_modding.game_code.rd_regions`,
then checked against the other executable: every original byte (after the move) must be
there, and every value's instruction half must match. Entries that pass are listed in
``VERIFIED``; the others, with the reason, are written as comments.
"""

from __future__ import annotations

import argparse
import hashlib
import sys
from pathlib import Path

APP = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APP))

from fe_modding.game_code import chapter_jump_fe10, entries_fe10, rd_hub, rd_story  # noqa: E402,F401
from fe_modding.game_code import rd_regions, region_map  # noqa: E402
from fe_modding.game_code.catalog import CATALOG, Edit, Patch, in_cave  # noqa: E402
from fe_modding.game_code.dol import Dol, DolError  # noqa: E402
from fe_modding.game_code.versions import RADIANT_DAWN_VERSIONS  # noqa: E402

OUT = APP / "fe_modding" / "game_code" / "rd_region_table.py"
US_DOL: Dol | None = None

# Sites the code alignment can't place, found by hand (the check below still applies).
MANUAL: dict[str, dict[int, int]] = {
    # Not on JP: rd.skill.wrath_hp_ratio. JP's Wrath check (0x80027F74) loads 0.2 and compares
    # strictly (HP ratio < 0.2), where the US loads 0.3 and allows equal: a different rule.
    rd_regions.JP: {
        # Colossus, Luna, Bane/Lethality activation rolls: on JP the roll's rlwinm. comes two
        # instructions later in the same window; the li r3,0 that ends it is at the same place.
        0x80028FA0: 0x800287A4, 0x80028FC7: 0x800287C3,
        0x800291DC: 0x800289D4, 0x80029203: 0x800289FF,
        0x80029414: 0x80028C24, 0x8002943B: 0x80028C4B,
        # promotion item level check: cmpwi r0,10 after the same unit/class loads
        0x8011FFA4: 0x801186B8,
        # the same predicate's SID_EVENT_CC skill test (JP's string read at r13-0x7AE4)
        0x8011FF68: 0x8011867C,
        # the boot script's two database initialisers (read from JP's script at 0x8036D30C)
        0x800CDCEC: 0x800C81B8, 0x800CDF00: 0x800C8390,
    },
}


def _hook_spans(entry) -> list[tuple[int, int]]:
    spans = []
    for patch in getattr(entry, "requires", ()):
        for e in patch.versions.get(rd_regions.US, ()):
            spans.append((e.address, e.address + e.length))
    return spans


def check(entry, ported, dol: Dol) -> str:
    """'' when the ported sites hold the expected retail bytes in ``dol``, else why not."""
    if isinstance(entry, Patch):
        for edit in ported:
            if in_cave(edit.address, edit.length) or edit.all_wild:
                continue
            try:
                seen = dol.read(edit.address, edit.length)
            except DolError:
                return f"{edit.address:08X} is outside the executable"
            if edit.original_sha1:
                if hashlib.sha1(seen).hexdigest() != edit.original_sha1:
                    return f"{edit.address:08X}: the retail code differs"
            elif not edit.matches(seen, edit.original):
                return f"{edit.address:08X}: expected {edit.original.hex()}, found {seen.hex()}"
        return ""
    spans = _hook_spans(entry)
    for us_field, f in zip(entry.versions[rd_regions.US], ported):
        if in_cave(f.address, f.span) or any(a <= us_field.address < b for a, b in spans):
            continue
        try:
            seen = dol.read(f.address, f.span)
        except DolError:
            return f"{f.address:08X} is outside the executable"
        if f.kind in ("lis_addi", "lis_addi8"):
            low_at = 8 if f.kind == "lis_addi8" else 4
            got = seen[0:2] + seen[low_at:low_at + 2]
        else:
            got = seen[:len(f.expect)]
        if f.expect and got != f.expect:
            return f"{f.address:08X}: expected {f.expect.hex()}, found {got.hex()}"
        # a retail value is the same on every build: the whole instruction or datum must match
        retail = US_DOL.read(us_field.address, us_field.span)
        if seen != retail:
            return f"{f.address:08X}: retail {retail.hex()}, found {seen.hex()}"
    return ""


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("rd_work", type=Path)
    args = parser.parse_args(argv)
    global US_DOL
    us = US_DOL = Dol.open(args.rd_work / rd_regions.US / "sys" / "main.dol")
    if us.sha1() != RADIANT_DAWN_VERSIONS[rd_regions.US].dol_sha1:
        raise SystemExit("RFEE01 main.dol is not the retail one")
    entries = [e for e in CATALOG.entries_for(rd_regions.US) if rd_regions.US in e.versions]
    entries += [rd_story.PATCH, rd_hub.PATCH]          # installed by their own pages, not listed
    sda = {rd_regions.US: us.sda_bases()}
    table: dict[int, list] = {}
    verified: dict[str, list[str]] = {}
    failed: dict[str, list[tuple[str, str]]] = {}
    for column, code in enumerate(rd_regions.REGIONS):
        other = Dol.open(args.rd_work / code / "sys" / "main.dol")
        sda[code] = other.sda_bases()
        amap = region_map.build(us, other)
        used: dict[int, int] = {}

        def translate(address: int, amap=amap, used=used, manual=MANUAL.get(code, {})):
            new = manual.get(address)
            if new is None:
                new = amap.translate(address)
            if new is not None:
                used[address] = new
            return new
        verified[code], failed[code] = [], []
        for entry in entries:
            used.clear()
            try:
                ported = rd_regions.port_sites(entry, translate, sda[rd_regions.US], sda[code])
            except rd_regions.NotPortable as error:
                failed[code].append((entry.id, str(error)))
                continue
            why = check(entry, ported, other)
            if why:
                failed[code].append((entry.id, why))
                continue
            verified[code].append(entry.id)
            for address, new in used.items():
                table.setdefault(address, [None] * len(rd_regions.REGIONS))[column] = new
        print(f"{code}: {len(verified[code])} of {len(entries)} entries")
    lines = [
        '"""Radiant Dawn Game Code addresses on RFEP01 and RFEJ01 (generated; do not edit).',
        "",
        "Made by ``python -m tools.build_rd_region_table`` from the retail executables; see",
        ":mod:`fe_modding.game_code.rd_regions`.",
        '"""',
        "",
        "# RFEE01 address: (RFEP01 address, RFEJ01 address); None where the build has none",
        "TABLE: dict[int, tuple[int | None, int | None]] = {",
    ]
    for address in sorted(table):
        row = ", ".join("None" if a is None else f"0x{a:08X}" for a in table[address])
        lines.append(f"    0x{address:08X}: ({row}),")
    lines.append("}")
    lines.append("")
    lines.append("# (r2, r13) small-data bases")
    lines.append("SDA: dict[str, tuple[int, int]] = {")
    for code, (r2, r13) in sda.items():
        lines.append(f'    "{code}": (0x{r2:08X}, 0x{r13:08X}),')
    lines.append("}")
    lines.append("")
    lines.append("# entries checked against the region's retail main.dol")
    lines.append("VERIFIED: dict[str, frozenset[str]] = {")
    for code in rd_regions.REGIONS:
        lines.append(f'    "{code}": frozenset({{')
        lines.extend(f'        "{entry_id}",' for entry_id in verified[code])
        lines.append("    }),")
    lines.append("}")
    lines.append("")
    for code in rd_regions.REGIONS:
        lines.append(f"# Not on {code}:")
        lines.extend(f"#   {entry_id}: {why}" for entry_id, why in failed[code])
    lines.append("")
    OUT.write_bytes("\n".join(lines).encode("utf-8"))
    print(f"wrote {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
