"""Census of FE9 runtime state: named heaps and writable globals.

Run from the repository root::

    python App/tools/census_runtime_state.py heaps
    python App/tools/census_runtime_state.py globals EXPORT_DIR [--tsv OUT.tsv]

``heaps`` reads the US executable directly. It lists every named heap the
engine's process scripts create or pop (process opcode table 1, slots 5 and 6)
and the fixed native heap scopes recorded in ``NATIVE_HEAP_SCOPES``.

``globals`` reads a Ghidra export made by
``research/main_dol/scripts/export/CensusDump.java`` (``blocks.tsv``,
``functions.tsv`` and ``refs.tsv``). Every code reference into a writable
section is grouped by the data item that contains it. Each function is given a
service from its name, unnamed functions inherit the majority service of their
call-graph neighbours, and each global is owned by the service that writes it
most. The report gives, per global, the writers, readers, owning service,
whether a re-initializer or a save routine touches it, and how ambiguous the
ownership is.
"""

from __future__ import annotations

import argparse
import csv
import re
import struct
import sys
from collections import Counter, defaultdict
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DOL = ROOT / "research" / "main_dol" / "dols" / "GFEE01.dol"

# Process-script opcodes: arg << 16 | len << 12 | table << 8 | slot.
CREATE_HEAP_OP = 0x3105  # table 1 slot 5: create_named_heap_block(name, size)
POP_HEAP_OP = 0x1106  # table 1 slot 6: pop the newest low-stack heap

# Heap scopes opened by native code rather than by process-script opcodes.
NATIVE_HEAP_SCOPES = [
    ("Base", "low", "0x533333", "init_gx_render_system (boot)", "never popped"),
    ("LOGO", "high", "0xC0000", "E_OpeningLogo start (0x800C78D0)", "E_OpeningLogo end (0x800C7884)"),
    ("BATTLE_FILE", "low", "0xB00000", "load_battle_file (debug battle preview)", "FUN_80005EB4"),
    ("BMAP_MEM", "low", "0x180000", "load_chapter_map_and_battle_stage_resources", "unload_bmap_common_resources (2nd pop)"),
    ("BMAP_FILE", "low", "all free space", "load_chapter_map_and_battle_stage_resources, load_bmap_file_and_initialize_map", "unload_bmap_common_resources (1st pop), FUN_8002D44C before battles/class change"),
    ("BATTLE_FILE", "low", "all free space", "load_and_write_battle_file (full battle)", "FUN_80028674 after the battle"),
    ("ENDING_MEM", "low", "0x180000", "init_ending_sequence", "unload_ending_resources (2nd pop)"),
    ("ENDING_FILE", "low", "all free space", "init_ending_sequence", "unload_ending_resources (1st pop)"),
]


def load_dol(path: Path):
    blob = path.read_bytes()
    offsets = struct.unpack(">18I", blob[:72])
    addresses = struct.unpack(">18I", blob[72:144])
    sizes = struct.unpack(">18I", blob[144:216])
    return blob, [(a, o, s) for o, a, s in zip(offsets, addresses, sizes) if o and s]


def read(blob, sections, address, size=4):
    for start, offset, length in sections:
        if start <= address < start + length:
            return blob[offset + address - start: offset + address - start + size]
    return b""


def cstring(blob, sections, address):
    out = bytearray()
    while len(out) < 64:
        byte = read(blob, sections, address + len(out), 1)
        if not byte or byte == b"\0":
            break
        out += byte
    return out.decode("ascii", "replace")


def heaps(dol: Path) -> None:
    blob, sections = load_dol(dol)
    print("Process-script heap scopes (US):")
    for start, offset, length in sections:
        if start < 0x80267A80:  # skip code
            continue
        for i in range(0, length - 12, 4):
            word = struct.unpack_from(">I", blob, offset + i)[0]
            address = start + i
            if word & 0xFFFF == CREATE_HEAP_OP:
                name_ptr, size = struct.unpack_from(">II", blob, offset + i + 4)
                print(f"  {address:08X}  create  {cstring(blob, sections, name_ptr):<10} 0x{size:X}")
            elif word == POP_HEAP_OP:
                print(f"  {address:08X}  pop")
    print("\nNative heap scopes:")
    for name, side, size, opened, closed in NATIVE_HEAP_SCOPES:
        print(f"  {name:<12} {side:<4} {size:<15} open: {opened}; close: {closed}")


# --- globals ---------------------------------------------------------------

DOMAIN_TOKENS = {
    "save": "save sysf memory card serialize deserialize suspend gci playthrough clear_history",
    "audio": "sound voice sequencer bgm music ax aram synth adpcm sfx se musyx",
    "render": "gx render texture tev efb xfb vtx material model mesh light matrix vi framebuffer prim2d sprite tileset terrain_texture",
    "camera": "camera gcamera",
    "combat": "battle combat attack damage hit crit forecast exp",
    "units": "unit party character pid class stat level growth faction army inventory convoy item forge weapon skill support bond laguz",
    "map": "map tile terrain grid range movement path bmap zmap door chest village",
    "ai": "ai cp",
    "campaign": "chapter ending opening turn phase objective tutorial trial base",
    "text": "text message mess font string glyph fuki kana markup",
    "effects": "effect animation anim particle motion pose gactor actor",
    "input": "pad input rumble",
    "memory": "heap arena alloc free msl_operator",
    "resources": "module resource dvd file load relocatable archive decompress",
    "os-runtime": "os msl trk exi si dsp ar arq timer time thread interrupt cache stdio printf exception",
}
INFRA_TOKENS = {  # in priority order
    "debug": "debug",
    "script-vm": "script cm event flag",
    "process": "process proc scheduler child task tick controller",
    "ui": "kaneko ui menu window widget panel popup help button cursor draw display dialog",
}
AUDIO_LIBRARY = (0x80240000, 0x80260000)
REINIT_TOKENS = {"init", "initialize", "reset", "clear", "construct", "setup", "start", "load", "reload", "create"}
SAVE_TOKENS = {"save", "serialize", "deserialize", "sysf", "suspend", "gci"}


def tokens(name: str) -> set[str]:
    name = re.sub(r"([a-z])([A-Z])", r"\1_\2", name)
    return {t for t in re.split(r"[^a-zA-Z0-9]+", name.lower()) if t}


def build_lookup(table):
    lookup = {}
    for service, words in table.items():
        for word in words.split():
            lookup.setdefault(word, service)
    return lookup


DOMAIN = build_lookup(DOMAIN_TOKENS)
INFRA = build_lookup(INFRA_TOKENS)


def name_service(name: str) -> str | None:
    """Service implied by a function name, or None for unnamed code.

    Domain words win over infrastructure words. Among domain words the most
    frequent service wins, ties going to the word that appears first in the
    name; infrastructure words are ranked debug > script-vm > process > ui.
    """
    if re.match(r"^(FUN_|lib_|thunk_FUN_|LAB_)", name):
        return None
    words = re.split(r"[^a-z0-9]+", re.sub(r"([a-z])([A-Z])", r"\1_\2", name).lower())
    joined = "_".join(words)
    hits = [DOMAIN[w] for w in words if w in DOMAIN]
    hits += [s for w, s in DOMAIN.items() if "_" in w and w in joined]
    if hits:
        counts = Counter(hits)
        best = max(counts.values())
        return next(s for s in hits if counts[s] == best)
    found = {INFRA[w] for w in words if w in INFRA}
    for service in INFRA_TOKENS:
        if service in found:
            return service
    return None


def load_export(export: Path):
    functions = {}
    with (export / "functions.tsv").open(encoding="utf-8") as stream:
        for line in stream:
            parts = line.rstrip("\n").split("\t")
            if len(parts) >= 2 and re.fullmatch(r"[0-9a-f]{8}", parts[0]):
                functions[parts[0]] = parts[1]
    calls = defaultdict(set)
    accesses = []
    with (export / "refs.tsv").open(encoding="utf-8") as stream:
        for row in csv.reader(stream, delimiter="\t", quoting=csv.QUOTE_NONE):
            if not row:
                continue
            if row[0] == "CALL":
                calls[row[2]].add(row[3])
                calls[row[3]].add(row[2])
            elif len(row) >= 7:
                accesses.append(row)
    return functions, calls, accesses


def assign_services(functions, calls):
    service = {addr: name_service(name) for addr, name in functions.items()}
    for addr in service:
        # The MusyX/AX audio library occupies this contiguous range; many of
        # its pool routines have generic names such as *_instance_acquire.
        if not service[addr] and AUDIO_LIBRARY[0] <= int(addr, 16) < AUDIO_LIBRARY[1]:
            service[addr] = "audio"
    # Synchronous rounds: each round only sees services settled in earlier
    # rounds, so the result does not depend on function order.
    for _ in range(6):
        settled = dict(service)
        for addr in functions:
            if settled[addr]:
                continue
            votes = Counter(settled[n] for n in calls.get(addr, ()) if settled.get(n))
            if votes:
                top = votes.most_common()
                service[addr] = min(s for s, c in top if c == top[0][1])
        if settled == service:
            break
    return service


def globals_census(export: Path, tsv: Path | None) -> None:
    functions, calls, accesses = load_export(export)
    service = assign_services(functions, calls)
    items = defaultdict(lambda: {"w": set(), "r": set(), "d": set(), "sym": "", "sec": "", "type": ""})
    for kind, _pc, func, to, symbol, section, data, *_ in accesses:
        key = data.split("@")[-1] if "@" in data else to
        item = items[key]
        item["sym"] = item["sym"] or (symbol if key == to else "")
        item["sec"] = section
        item["type"] = data.split("@")[0] if data else ""
        bucket = {"W": "w", "RW": "w", "R": "r", "D": "d"}[kind]
        item[bucket].add(func)
        if kind == "RW":
            item["r"].add(func)
    mutable = {k: v for k, v in items.items()
               if v["w"] or (v["d"] and v["sec"].startswith("bss"))}
    rows = []
    for key, item in sorted(mutable.items()):
        users = item["w"] | item["r"] | item["d"]
        weights = Counter()
        for func in users:
            if service.get(func):
                weights[service[func]] += 2 if func in item["w"] else 1
        owner, share = ("unassigned", 0.0)
        if weights:
            top = max(weights.values())
            owner = min(s for s, w in weights.items() if w == top)
            share = top / sum(weights.values())
        writer_names = sorted(functions.get(f, f) for f in item["w"])
        reinit = sorted(n for n in writer_names if tokens(n) & REINIT_TOKENS)
        saved = sorted(functions.get(f, f) for f in users if tokens(functions.get(f, "")) & SAVE_TOKENS)
        rows.append({
            "address": key, "symbol": item["sym"], "section": item["sec"], "type": item["type"],
            "owner": owner, "owner_share": f"{share:.2f}",
            "writers": len(item["w"]), "readers": len(item["r"]), "address_taken": len(item["d"]),
            "storage": "dol-initialized" if item["sec"].startswith("data") else "zeroed-at-boot",
            "reinitialized_by": ";".join(reinit[:4]), "save_linked": ";".join(saved[:4]),
            "writer_functions": ";".join(writer_names[:8]),
        })
    by_owner = Counter(r["owner"] for r in rows)
    print(f"Writable data items referenced by code: {len(items)}")
    print(f"Mutable globals (directly written, or address-taken in .bss/.sbss): {len(rows)}")
    print(f"  directly written: {sum(1 for r in rows if r['writers'])}")
    print(f"  with a re-initializer: {sum(1 for r in rows if r['reinitialized_by'])}")
    print(f"  save-linked: {sum(1 for r in rows if r['save_linked'])}")
    print(f"  single-owner (share 1.0): {sum(1 for r in rows if r['owner_share'] == '1.00')}")
    print(f"  contested (share < 0.5): {sum(1 for r in rows if float(r['owner_share']) < 0.5)}")
    named = sum(1 for f, n in functions.items() if name_service(n))
    print(f"Functions: {len(functions)}; service from name {named}; "
          f"after call-graph propagation {sum(1 for s in service.values() if s)}")
    print("Owners:")
    for owner, count in by_owner.most_common():
        written = sum(1 for r in rows if r["owner"] == owner and r["writers"])
        print(f"  {owner:<12} {count:>5}  ({written} directly written)")
    if tsv:
        with tsv.open("w", encoding="utf-8", newline="\n") as stream:
            writer = csv.DictWriter(stream, fieldnames=list(rows[0]), delimiter="\t", lineterminator="\n")
            writer.writeheader()
            writer.writerows(rows)
        print(f"Wrote {tsv}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)
    h = sub.add_parser("heaps")
    h.add_argument("--dol", type=Path, default=DEFAULT_DOL)
    g = sub.add_parser("globals")
    g.add_argument("export", type=Path)
    g.add_argument("--tsv", type=Path)
    args = parser.parse_args()
    if args.command == "heaps":
        heaps(args.dol)
    else:
        globals_census(args.export, args.tsv)


if __name__ == "__main__":
    sys.exit(main())
