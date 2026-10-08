"""Regenerate ``externs_fe9.json`` (or ``externs_fe10.json`` with ``--fe10``).

    python -m fe_modding.formats.cmb.build_catalog [--fe10] <extern tsv> <extracted Scripts dir>

* ``<extern tsv>``: ``research/main_dol/fe9_script_externs.tsv`` (Radiant
  Dawn: ``research/rd/fe10_script_externs.tsv``), exported from ``main.dol``
  by ``ExportExternCatalog.java`` (name, argc, handler).
* ``<Scripts dir>``: a vanilla ``files/Scripts`` folder. Named functions
  exported by ``startup.cmb`` are callable from every chapter, so they are
  catalogued too; every call site in every script is used to infer each
  argument's kind from the literal values vanilla passes.
"""

from __future__ import annotations

import csv
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

from . import ast as A
from .binary import read_cmb_path
from .catalog import CATALOG_PATHS
from .decompiler import Decompiler

STRING_KINDS = [("MPID_", "mpid"), ("PID_", "pid"), ("IID_", "iid"), ("JID_", "jid"), ("MS_", "mess"),
                ("Ms_", "mess"), ("BGM_", "bgm"), ("SE_", "sfx")]
STRING_KINDS_FE10 = STRING_KINDS + [("SFX_", "sfx"), ("MT_", "mess"), ("MSN_", "mess")]


def classify(arg, kinds=STRING_KINDS) -> str | None:
    if isinstance(arg, A.Num) or (isinstance(arg, A.UnOp) and arg.op == "-" and isinstance(arg.operand, A.Num)):
        return "int"
    if isinstance(arg, A.Str):
        for prefix, kind in kinds:
            if arg.value.startswith(prefix):
                return kind
        return "str"
    if isinstance(arg, A.AddrOf):
        return "addr"
    return None


def walk_calls(node, found: list) -> None:
    if isinstance(node, A.Call):
        found.append(node)
    if isinstance(node, list):
        for x in node:
            walk_calls(x, found)
        return
    if hasattr(node, "__dataclass_fields__"):
        for name in node.__dataclass_fields__:
            value = getattr(node, name)
            if isinstance(value, (list, A.Stmt)) or hasattr(value, "__dataclass_fields__"):
                walk_calls(value, found)


def build(tsv: Path, scripts_dir: Path, fe10: bool = False) -> dict:
    kinds_table = STRING_KINDS_FE10 if fe10 else STRING_KINDS
    externs: dict[str, dict] = {}
    with open(tsv, encoding="utf-8") as f:
        for row in csv.DictReader(f, delimiter="\t"):
            externs[row["name"]] = {
                "argc": int(row["argc"]), "source": "native",
                "group": row["hub"].replace("register_", "").replace("_handlers", "").replace("_script", ""),
                "args": [], "uses": 0, "note": "",
            }

    scripts = {p.name: read_cmb_path(p) for p in sorted(scripts_dir.glob("*.cmb"))}
    startup = scripts.get("startup.cmb")
    if startup is not None:
        for fn in startup.functions:
            if fn.id_string and fn.id_string not in externs:
                externs[fn.id_string] = {"argc": fn.num_args, "source": "script", "group": "startup.cmb",
                                         "args": [], "uses": 0, "note": ""}

    # Every named function is registered by name while its script is loaded.
    exported_anywhere = {fn.id_string for script in scripts.values() for fn in script.functions if fn.id_string}
    kinds: dict[str, list[Counter]] = defaultdict(lambda: [Counter() for _ in range(10)])
    unknown = Counter()
    for script in scripts.values():
        known = {n: e["argc"] for n, e in externs.items() if e["source"] == "script"}
        calls: list = []
        decompiler = Decompiler(script, known)
        walk_calls(decompiler.module().functions, calls)
        for call in calls:
            if not isinstance(call.name, str) or (not call.extern and call.name in decompiler.names.def_set):
                continue
            if call.name not in externs:
                if call.name not in exported_anywhere and call.name not in ("streq", "strne"):
                    unknown[call.name] += 1
                continue
            externs[call.name]["uses"] += 1
            for i, arg in enumerate(call.args[:10]):
                kind = classify(arg, kinds_table)
                if kind:
                    kinds[call.name][i][kind] += 1

    for name, entry in externs.items():
        args = []
        for i in range(entry["argc"]):
            counts = kinds[name][i] if name in kinds else Counter()
            kind = counts.most_common(1)[0][0] if counts else "int"
            args.append({"name": "", "kind": kind})
        entry["args"] = args
    for name, uses in unknown.items():
        externs[name] = {"argc": -1, "source": "unregistered", "group": "", "args": [], "uses": uses,
                         "note": "Called by vanilla scripts but registered nowhere: the VM silently returns 0."}
    return {"externs": dict(sorted(externs.items()))}


def main(argv: list[str]) -> int:
    fe10 = "--fe10" in argv
    argv = [a for a in argv if a != "--fe10"]
    if len(argv) != 2:
        print(__doc__)
        return 2
    data = build(Path(argv[0]), Path(argv[1]), fe10)
    path = CATALOG_PATHS["fe10" if fe10 else "fe9"]
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(json.dumps(data, ensure_ascii=False, indent=1) + "\n")
    counts = Counter(e["source"] for e in data["externs"].values())
    print(f"Wrote {path} ({dict(counts)})")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
