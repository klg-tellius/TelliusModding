"""Read-only regional inventory for the extended flag patch.

Run from the repository root:
    python App/tools/audit_extended_flag_hooks.py

Function maps are evidence for locating candidates, not authorization to patch them.
This report deliberately never emits patch edits or changes a DOL.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
from pathlib import Path

APP = Path(__file__).resolve().parents[1]
ROOT = APP.parent
sys.path.insert(0, str(APP))

from fe_modding.game_code.dol import Dol
from fe_modding.game_code.ppc import mask_words
from fe_modding.game_code.versions import VERSIONS

# US entries and body sizes from read-only Ghidra DumpDecompiled.java output.
FUNCTIONS = {
    "flag_read_bits": (0x800BDA9C, 92),
    "flag_write_bits": (0x800BDAF8, 92),
    "flag_clear": (0x800BDBC8, 160),
    "flag_set": (0x800BDC68, 160),
    "flag_get": (0x800BDD08, 196),
    "flag_register_local": (0x800BDDCC, 116),
    "flag_register_global": (0x800BDE40, 152),
    "flag_reset_locals": (0x800BDED8, 400),
    "flag_clear_playthrough": (0x800BE068, 448),
    "flag_init": (0x800BE228, 204),
    "party_read": (0x8014C1B8, 484),
    "party_write": (0x8014C39C, 524),
    "snapshot_read": (0x801E3654, 328),
    "save_read": (0x801E379C, 324),
    "file_save_write": (0x801E1CB4, 864),
    "checkpoint_write": (0x801E047C, 912),
    "new_game_write": (0x801E1540, 1908),
    "allpush": (0x800B72CC, 172),
    "snapshot_write": (0x801E38E0, 384),
    "allpop": (0x800B727C, 80),
    "arena_init": (0x800C5300, 176),
    "save_finalize": (0x801E3CA8, 1236),
    "chapter_start": (0x8014D920, 328),
    "script_init": (0x800C2750, 336),
}

# Missing map entries recovered through corresponding call edges. Extents were
# checked against the regional epilogue (including blr), not copied from US.
# These are research candidates; they do not enable production save hooks.
CALL_EDGE_CANDIDATES = {
    ("GFEP01", "save_finalize"): (0x801E1CB4, 0x334, 0x801E6FD8, 0x6B8),
    ("GFEJ01", "checkpoint_write"): (0x80072C64, 0x14, 0x801DD57C, 0x30C),
}

# JP's file writer takes (card context, file slot, parent process), creates its
# child write process itself, and ends at 0x801DEAF0. It is not the US/EU ABI.
REGIONAL_EXTENTS = {("GFEJ01", "file_save_write"): 0x374}


def direct_call_target(dol: Dol, address: int) -> int:
    word = dol.u32(address)
    if word & 0xFC000003 != 0x48000001:
        raise ValueError(f"Expected relative bl at {address:08X}")
    displacement = word & 0x03FFFFFC
    if displacement & 0x02000000:
        displacement -= 0x04000000
    return address + displacement


def audit(root: Path = ROOT) -> dict:
    research = root / "research" / "main_dol"
    maps = {}
    for code, suffix in (("GFEP01", "eu"), ("GFEJ01", "jp")):
        with (research / f"us_{suffix}_function_map.tsv").open(encoding="utf-8", newline="") as handle:
            maps[code] = {int(r["src_addr"], 16): r for r in csv.DictReader(handle, delimiter="\t")}
    dols = {code: Dol.open(research / "dols" / f"{code}.dol") for code in VERSIONS}
    for code, dol in dols.items():
        if dol.sha1() != VERSIONS[code].dol_sha1:
            raise ValueError(f"{code}: expected an unmodified retail executable")
    result = {"status": "research-only; no installable patch", "regions": {}}
    us = dols["GFEE01"]
    for code, dol in dols.items():
        functions = {}
        for name, (source, size) in FUNCTIONS.items():
            row = maps.get(code, {}).get(source)
            evidence = None
            regional_size = REGIONAL_EXTENTS.get((code, name), size)
            if code != "GFEE01" and (row is None or not row["dst_addr"]):
                candidate = CALL_EDGE_CANDIDATES.get((code, name))
                if candidate is None:
                    functions[name] = {"error": "missing regional function-map candidate"}
                    continue
                caller, offset, expected, regional_size = candidate
                mapped = maps[code][caller]
                callsite = int(mapped["dst_addr"], 16) + offset
                address = direct_call_target(dol, callsite)
                if direct_call_target(us, caller + offset) != source or address != expected:
                    raise ValueError(f"{code} {name}: call-edge evidence changed")
                if dol.u32(address + regional_size - 4) != 0x4E800020:
                    raise ValueError(f"{code} {name}: expected regional epilogue")
                evidence = {"caller": f"0x{callsite:08X}", "target": f"0x{address:08X}",
                            "extent_bytes": regional_size}
            else:
                address = source if code == "GFEE01" else int(row["dst_addr"], 16)
            # The map's size describes the source body. Equality here is only a
            # source-sized comparison, not proof of the regional function's extent.
            raw = dol.read(address, regional_size)
            functions[name] = {
                "address": f"0x{address:08X}", "hashed_bytes": regional_size,
                "compared_bytes": size,
                "sha256": hashlib.sha256(raw).hexdigest(),
                "map_confidence": "call-edge candidate" if evidence else "US decompilation" if row is None else row["confidence"],
                "source_sized_masked_match": mask_words(dol.words(address, size // 4), dol.sda_bases())
                == mask_words(us.words(source, size // 4), us.sda_bases()),
            }
            if evidence:
                functions[name]["call_edge_evidence"] = evidence
        result["regions"][code] = {"retail_sha1": dol.sha1(),
                                     "bss_end": f"0x{dol.bss_address + dol.bss_size:08X}",
                                     "functions": functions}
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = json.dumps(audit(), indent=2) + "\n"
    if args.output:
        args.output.write_text(report, encoding="utf-8")
    else:
        print(report, end="")
