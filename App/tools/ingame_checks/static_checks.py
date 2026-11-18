"""Checks of the plan that need no Dolphin; they write their rows to the same results table.

    python -m tools.ingame_checks.static_checks

* SC1e / SC1j (RD inventory SCRIPT-01): every script of the European and Japanese discs round-trips
  byte for byte through the binary reader, and decompiles to source that compiles back to a stable file
  (with and without an appended event).
* TX1 / TX1r (1.0 checklist §6, Export as text): the export into an empty folder writes the marker and
  its folders; a second export into the same folder replaces the first (same files, no leftovers).

Run it while no Dolphin check runs: it is CPU-heavy and would slow a driven game, and it opens the shared
work projects, which a running check's build is using.
"""
from __future__ import annotations

import json
import sys
import tempfile
from datetime import datetime
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    __package__ = "tools.ingame_checks"

from .core import BASES, ROOT, work_for  # noqa: E402
from .run import write_table  # noqa: E402

EXTRA = '\n@on_phase(turn_from=1, turn_to=1, phase="enemy")\ndef ZZStaticCheck():\n    set("gf_complete")\n'


def script_round_trips(region: str) -> tuple[bool, str]:
    from fe_modding.formats.cmb import binary, compiler, decompiler
    problems, count = [], 0
    for path in sorted((BASES[region] / "files" / "Scripts").glob("*.cmb")):
        raw = path.read_bytes()
        try:
            script = binary.read_cmb(raw)
            if binary.write_cmb(script) != raw:
                problems.append(f"{path.name}: binary round trip differs")
            source = decompiler.decompile(script, path.name)[0]
            for extra in ("", EXTRA):
                out = binary.write_cmb(compiler.compile_source(source + extra, base=script).script)
                if binary.write_cmb(binary.read_cmb(out)) != out:
                    problems.append(f"{path.name}: compiled file not stable{' (+event)' if extra else ''}")
            count += 1
        except Exception as error:  # noqa: BLE001 - every failing script is reported
            problems.append(f"{path.name}: {type(error).__name__}: {error}")
    return not problems, (f"{count} scripts: byte-identical binary round trip, decompile/compile stable"
                          if not problems else f"{len(problems)} problem(s): {problems[:4]}")


def text_export_twice(region: str) -> tuple[bool, str]:
    from fe_modding import text_export
    project = work_for(region, {}).project
    with tempfile.TemporaryDirectory() as temp:
        dest = Path(temp) / "export"
        dest.mkdir()
        text_export.export_project(project, dest)
        first = sorted(p.relative_to(dest).as_posix() for p in dest.rglob("*") if p.is_file())
        marker = (dest / text_export.MARKER).is_file()
        folders = sorted({f.split("/")[0] for f in first if "/" in f})
        stray = f"{folders[0]}/stray_leftover.txt"         # a part's folder is replaced on each export
        (dest / stray).write_text("from an older export", encoding="utf-8")
        text_export.export_project(project, dest)
        second = sorted(p.relative_to(dest).as_posix() for p in dest.rglob("*") if p.is_file())
    ok = marker and first == second and stray not in second
    return ok, (f"{len(first)} files in {folders}; marker {'written' if marker else 'MISSING'}; second export "
                f"{'replaced the first' if first == second else 'differs'}"
                f"{', a stale file in a part folder was kept' if stray in second else ''}")


def main() -> None:
    results_path = ROOT / "results.json"
    results = json.loads(results_path.read_text(encoding="utf-8")) if results_path.is_file() else {}
    rows = [("SC1e", "RFEP01", "Scripts round-trip on the European disc", ["SCRIPT-01"], script_round_trips),
            ("SC1j", "RFEJ01", "Scripts round-trip on the Japanese disc", ["SCRIPT-01"], script_round_trips),
            ("TX1", "GFEE01", "Export as text twice into one folder", ["1.0 §6 Export as text (POR)"], text_export_twice),
            ("TX1r", "RFEE01", "Export as text twice into one folder", ["1.0 §6 Export as text (RD)"], text_export_twice)]
    for cid, region, title, covers, fn in rows:
        print(f"== {cid}: {title}", flush=True)
        try:
            passed, details = fn(region)
            result = "PASS" if passed else "FAIL"
        except Exception as error:  # noqa: BLE001
            result, details = "ERROR", f"{type(error).__name__}: {error}"
        print(f"   {result}: {details}", flush=True)
        results[cid] = {"region": region, "title": title, "covers": covers, "result": result, "details": details,
                        "when": datetime.now().isoformat(timespec="minutes")}
    write_table(results)


if __name__ == "__main__":
    main()
