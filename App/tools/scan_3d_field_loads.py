"""List direct PPC loads overlapping open FE9 3D field offsets in mapped functions.

This is a candidate search, not a proof of pointer provenance or no-reader status.
Run from the repository root: python App/tools/scan_3d_field_loads.py
"""

from __future__ import annotations

import csv
import struct
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
DOLS = ROOT / "research" / "main_dol" / "dols"
MAPS = ROOT / "research" / "main_dol"

# These functions have already been traced as the main skeleton, texture and
# particle paths. Cross-region map entries without reliable matches are skipped.
FUNCTIONS = {
    "gactor_blend_skeleton_pose_from_animations": (0x0C, 4),
    "build_bone_local_matrix": (0x0C, 4),
    "relocate_g_skeleton_bones": (0x0C, 4),
    "bind_gs_material_texture": (0x00, 2, 0x06, 2),
    "draw_actor_material_batches": (0x0C, 2),
    "update_actor_material_runtime": (0x0C, 2),
}

# D-form integer and floating point loads; X-form/indexed and copies require
# separate dataflow review and are deliberately not treated as negative proof.
LOADS = {
    32: ("lwz", 4), 33: ("lwzu", 4),
    34: ("lbz", 1), 35: ("lbzu", 1),
    40: ("lhz", 2), 41: ("lhzu", 2),
    42: ("lha", 2), 43: ("lhau", 2),
    48: ("lfs", 4), 49: ("lfsu", 4),
    50: ("lfd", 8), 51: ("lfdu", 8),
}


def text_sections(blob: bytes):
    for i in range(7):
        file_off, addr, size = (struct.unpack_from(">I", blob, base + 4 * i)[0]
                                for base in (0, 0x48, 0x90))
        if file_off and size and file_off + size <= len(blob):
            yield addr, blob[file_off:file_off + size]


def function_map(path: Path, address_column: str = "dst_addr"):
    with path.open(newline="", encoding="utf-8") as stream:
        for row in csv.DictReader(stream, delimiter="\t"):
            if (row["src_name"] in FUNCTIONS and row[address_column]
                    and (address_column == "src_addr" or row["confidence"] == "high")):
                yield row["src_name"], int(row[address_column], 16), int(row["size"], 16)


def words_in_range(sections, start: int, size: int):
    for addr, data in sections:
        first, last = max(start, addr), min(start + size, addr + len(data))
        for pc in range(first, last, 4):
            yield pc, struct.unpack_from(">I", data, pc - addr)[0]


def candidates(sections, start: int, size: int, fields: tuple[int, ...]):
    field_ranges = list(zip(fields[::2], fields[1::2]))
    for pc, word in words_in_range(sections, start, size):
        op = word >> 26
        if op not in LOADS:
            continue
        mnemonic, width = LOADS[op]
        off = word & 0xFFFF
        if off & 0x8000:
            off -= 0x10000
        for field_off, field_width in field_ranges:
            if off < field_off + field_width and off + width > field_off:
                dest, base = (word >> 21) & 31, (word >> 16) & 31
                yield pc, mnemonic, dest, base, off, field_off


def main():
    us = {n: (a, s) for n, a, s in
          function_map(MAPS / "us_eu_function_map.tsv", "src_addr")}
    regions = {
        "US": (DOLS / "GFEE01.dol", us),
        "PAL": (DOLS / "GFEP01.dol", dict((n, (a, s)) for n, a, s in
               function_map(MAPS / "us_eu_function_map.tsv"))),
        "JP": (DOLS / "GFEJ01.dol", dict((n, (a, s)) for n, a, s in
              function_map(MAPS / "us_jp_function_map.tsv"))),
    }
    for region, (path, mapped) in regions.items():
        sections = list(text_sections(path.read_bytes()))
        print(f"[{region}]")
        for name, fields in FUNCTIONS.items():
            if name not in mapped:
                print(f"  {name}: unmapped")
                continue
            addr, size = mapped[name]
            hits = list(candidates(sections, addr, size, fields))
            print(f"  {name}: {len(hits)} offset candidates")
            for pc, op, dest, base, off, field in hits:
                print(f"    {pc:08X} {op} r{dest},{off:+#x}(r{base}) -> field +{field:#x}")


if __name__ == "__main__":
    main()
