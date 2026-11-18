"""Build and run in-game checks unattended, then write the results table.

    python -m tools.ingame_checks.run --set gamedata [--only G1 G2] [--no-build] [--reuse-retail]

Run from ``App`` with ``TELLIUS_DOLPHIN`` set (default ``G:\\Dolphin-x64\\Dolphin.exe``). Only one driven
Dolphin may run at a time (the keys are global); the runner refuses to start next to another one.
Output: ``G:/ROM/tellius_test/ingame/out/<id>_<variant>/`` (log, shots, observations) and
``G:/ROM/tellius_test/ingame/results.json`` + ``RESULTS.md``.
"""
from __future__ import annotations

import argparse
import importlib
import json
import subprocess
import sys
import time
import traceback
from datetime import datetime
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    __package__ = "tools.ingame_checks"

from .core import ROOT, VARIANTS, build_variant  # noqa: E402
from .driver import Driver  # noqa: E402
from tools.session_playtest.harness import write_lf  # noqa: E402

SETS = ("gamedata", "saves", "chapters", "assets", "maps", "code")


def dolphin_running() -> bool:
    out = subprocess.run(["tasklist", "/FI", "IMAGENAME eq Dolphin.exe"], capture_output=True, text=True).stdout
    return "Dolphin.exe" in out


def run_variant(check, variant: str, facts: dict) -> dict:
    """One run; a timeout (a stalled boot, a slow PC) is retried once from scratch."""
    obs = _run_once(check, variant, facts)
    if obs.get("error", "").startswith("Timeout"):
        print(f"   {variant}: {obs['error']}; retrying once", flush=True)
        obs = _run_once(check, variant, facts)
    return obs


def _run_once(check, variant: str, facts: dict) -> dict:
    run = ROOT / "run" / f"{check.id}_{variant}"
    out = ROOT / "out" / f"{check.id}_{variant}"
    driver = Driver(run, out, check.region)
    started = time.time()
    obs: dict = {}
    try:
        driver.start_session()
        obs = check.play(driver, facts) or {}
        obs["invalid_accesses"] = driver.invalid_accesses()
    except Exception as error:  # noqa: BLE001 - a failed run is a result, not a crash of the runner
        driver.snap("error")
        obs = {"error": f"{type(error).__name__}: {error}", "trace": traceback.format_exc(),
               "invalid_accesses": driver.invalid_accesses() if driver.user.exists() else []}
    finally:
        driver.close()
    obs["seconds"] = round(time.time() - started, 1)
    write_lf(out / "observations.json", json.dumps(obs, indent=2, default=str) + "\n")
    return obs


def judge(check, mod: dict, retail, facts: dict) -> tuple[str, str]:
    if "error" in mod:
        return "FAIL", f"mod run: {mod['error']}"
    if retail is not None and "error" in retail:
        return "ERROR", f"retail run: {retail['error']}"
    new_invalid = sorted(set(mod.get("invalid_accesses", [])) - set((retail or {}).get("invalid_accesses", [])))
    try:
        passed, text = check.judge(mod, retail, facts)
    except Exception as error:  # noqa: BLE001
        return "ERROR", f"judge: {type(error).__name__}: {error}"
    if new_invalid:
        return "FAIL", f"{text}; new invalid accesses: {new_invalid[:3]}"
    return ("PASS" if passed else "FAIL"), text


def write_table(results: dict) -> None:
    write_lf(ROOT / "results.json", json.dumps(results, indent=2) + "\n")
    lines = ["# In-game check results", "", "| Id | Game | Check | Result | Details | Covers | When |",
             "| --- | --- | --- | --- | --- | --- | --- |"]
    for cid, r in sorted(results.items()):
        details = r["details"].replace("|", "/").replace("\n", " ")
        lines.append(f"| {cid} | {r['region']} | {r['title']} | **{r['result']}** | {details} | "
                     f"{'; '.join(r['covers'])} | {r['when']} |")
    write_lf(ROOT / "RESULTS.md", "\n".join(lines) + "\n")


def rejudge(checks) -> None:
    results_path = ROOT / "results.json"
    results = json.loads(results_path.read_text(encoding="utf-8")) if results_path.is_file() else {}
    for check in checks:
        def load(variant):
            path = ROOT / "out" / f"{check.id}_{variant}" / "observations.json"
            return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else None
        mod, retail = load("mod"), load("retail") if check.retail else None
        manifest = ROOT / "run" / f"{check.id}_mod" / "check.json"
        if mod is None or not manifest.is_file():
            print(f"{check.id}: no stored observations")
            continue
        facts = json.loads(manifest.read_text(encoding="utf-8"))["facts"]
        result, details = judge(check, mod, retail, facts)
        print(f"{check.id}: {result}: {details}", flush=True)
        results[check.id] = {"region": check.region, "title": check.title, "covers": check.covers,
                             "result": result, "details": details,
                             "when": datetime.now().isoformat(timespec="minutes")}
    write_table(results)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--set", choices=SETS, required=True)
    parser.add_argument("--only", nargs="*")
    parser.add_argument("--no-build", action="store_true", help="reuse the run trees already built")
    parser.add_argument("--reuse-retail", action="store_true", help="reuse the retail observations if present")
    parser.add_argument("--rejudge", action="store_true",
                        help="judge the stored observations again (after a judge fix); no build, no Dolphin")
    args = parser.parse_args()
    module = importlib.import_module(f".checks_{args.set}", __package__)
    checks = [c for c in module.CHECKS if not args.only or c.id in args.only]
    if args.rejudge:
        rejudge(checks)
        return
    if dolphin_running():
        sys.exit("Another Dolphin is running; close it first (the keys are global).")
    results_path = ROOT / "results.json"
    results = json.loads(results_path.read_text(encoding="utf-8")) if results_path.is_file() else {}
    works: dict = {}
    for check in checks:
        print(f"== {check.id}: {check.title}", flush=True)
        manifests = {}
        variants = VARIANTS if check.retail else ("mod",)
        try:
            for variant in variants:
                manifest_path = ROOT / "run" / f"{check.id}_{variant}" / "check.json"
                if args.no_build and manifest_path.is_file():
                    manifests[variant] = json.loads(manifest_path.read_text(encoding="utf-8"))
                else:
                    manifests[variant] = build_variant(check, variant, works)
        except Exception as error:  # noqa: BLE001
            traceback.print_exc()
            results[check.id] = {"region": check.region, "title": check.title, "covers": check.covers,
                                 "result": "ERROR", "details": f"build: {type(error).__name__}: {error}",
                                 "when": datetime.now().isoformat(timespec="minutes")}
            write_table(results)
            continue
        facts = manifests["mod"]["facts"]
        retail = None
        if check.retail:
            cached = ROOT / "out" / f"{check.id}_retail" / "observations.json"
            if args.reuse_retail and cached.is_file():
                retail = json.loads(cached.read_text(encoding="utf-8"))
            else:
                retail = run_variant(check, "retail", facts)
        mod = run_variant(check, "mod", facts)
        result, details = judge(check, mod, retail, facts)
        print(f"   {result}: {details}", flush=True)
        results[check.id] = {"region": check.region, "title": check.title, "covers": check.covers,
                             "result": result, "details": details, "when": datetime.now().isoformat(timespec="minutes")}
        write_table(results)
    for work in works.values():
        work.revert()


if __name__ == "__main__":
    main()
