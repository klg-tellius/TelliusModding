"""Reproduce the static JP/PAL difficulty and regional-content audit.

The retail trees are research inputs, not redistributed application assets.  This
tool reports section sizes/values, filesystem identity, and the US-to-regional
function matches that support ``wiki/systems/difficulty-and-regions.md``.
"""
from __future__ import annotations

import csv
import argparse
import hashlib
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "App"))

from fe_modding.formats.fe8data import GAME_DATA_ROWS, HEADER_SIZE, symbol_offsets


RESEARCH = ROOT / "research" / "main_dol"
BUILDS = {
    "JP": RESEARCH / "extracted" / "GFEJ01" / "P-GFEJ" / "files",
    "PAL": RESEARCH / "extracted" / "GFEP01" / "P-GFEP" / "files",
}
RELEVANT_FUNCTIONS = {
    "apply_fixed_growth_level_up",
    "read_dispos_unit_record",
    "get_chapter_field_by_difficulty",
    "is_fixed_growth_mode_enabled",
    "compute_crc32",
    "deserialize_all_unit_slots_from_stream",
    "serialize_all_unit_slots_to_stream",
    "deserialize_camera_and_cursor_state_from_stream",
    "serialize_camera_and_cursor_state_to_stream",
    "deserialize_forge_record_pool",
    "serialize_forge_record_pool",
    "deserialize_party_data_from_stream",
    "serialize_party_data_to_stream",
}


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def game_data(path: Path) -> tuple[int, list[tuple[str, tuple[int, ...]]]]:
    data = path.read_bytes()
    symbols = symbol_offsets(data)
    start = symbols["GameData"]
    end = min(value for value in symbols.values() if value > start)
    raw = data[HEADER_SIZE + start : HEADER_SIZE + end]
    rows = []
    for index in range(len(raw) // 4):
        name = GAME_DATA_ROWS[index][0] if index < len(GAME_DATA_ROWS) else f"row_{index}"
        rows.append((name, tuple(raw[4 * index : 4 * index + 4])))
    return len(raw), rows


def files(root: Path) -> dict[str, Path]:
    return {path.relative_to(root).as_posix(): path for path in root.rglob("*") if path.is_file()}


def mapped_functions(path: Path) -> dict[str, tuple[str, str, str]]:
    result = {}
    with path.open(encoding="utf-8", newline="") as stream:
        for row in csv.DictReader(stream, delimiter="\t"):
            if row["src_name"] in RELEVANT_FUNCTIONS:
                result[row["src_name"]] = (row["src_addr"], row["dst_addr"], row["confidence"])
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--us-files", type=Path, help="optional clean GFEE01 files directory")
    args = parser.parse_args()
    builds = dict(BUILDS)
    if args.us_files:
        builds["US"] = args.us_files

    for build, root in builds.items():
        size, rows = game_data(root / "FE8Data.bin")
        print(f"{build} GameData: {size} bytes, {len(rows)} rows")
        for name, values in rows:
            print(f"  {name}: {values}")

    jp, pal = files(BUILDS["JP"]), files(BUILDS["PAL"])
    common = jp.keys() & pal.keys()
    identical = {name for name in common if digest(jp[name]) == digest(pal[name])}
    print(
        "filesystem:",
        f"JP={len(jp)} PAL={len(pal)} common={len(common)} ",
        f"identical={len(identical)} different={len(common) - len(identical)} ",
        f"JP-only={len(jp.keys() - pal.keys())} PAL-only={len(pal.keys() - jp.keys())}",
    )
    for name in ("shop/shopitem_n.bin", "shop/shopitem_h.bin", "shop/shopitem_m.bin"):
        print(f"  {name}: {'identical' if name in identical else 'different'} {digest(jp[name])}")
        if "US" in builds:
            us_path = builds["US"] / name
            print(f"    US matches JP/PAL: {us_path.is_file() and digest(us_path) == digest(jp[name])}")

    for region, filename in (("PAL", "us_eu_function_map.tsv"), ("JP", "us_jp_function_map.tsv")):
        matches = mapped_functions(RESEARCH / filename)
        print(f"{region} relevant function matches: {sum(bool(dst) for _, dst, _ in matches.values())}/{len(matches)}")
        for name in sorted(matches):
            src, dst, confidence = matches[name]
            print(f"  {name}: {src} -> {dst or 'unmatched'} ({confidence or 'none'})")


if __name__ == "__main__":
    main()
