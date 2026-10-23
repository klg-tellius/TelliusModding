"""Interactive runner: pick the next test, rebuild its run tree, show what to do, start Dolphin,
then record PASS / FAIL for each check. Started by ``Start-Session.cmd`` in the package.

Results go to ``<package>/results.json`` and ``RESULTS.md``; nothing in the package's patches or
cards is changed, and the clean disc is only read (its key files are hash-checked first).
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import textwrap
from datetime import datetime
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    __package__ = "tools.session_playtest"

from .harness import (assemble_run_tree, dolphin_command, load_manifest, normal_volume,  # noqa: E402
                      prepare_dolphin_user, run_dolphin, sha256, write_lf)
from . import docs  # noqa: E402

RESULTS = "results.json"
WIDTH = 100


def say(text: str = "", indent: str = "") -> None:
    for line in text.splitlines() or [""]:
        print(textwrap.fill(line, WIDTH, initial_indent=indent, subsequent_indent=indent + "   ") if line else "")


def load_results(package: Path) -> dict:
    path = package / RESULTS
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}


def save_results(package: Path, manifest: dict, results: dict) -> None:
    write_lf(package / RESULTS, json.dumps(results, indent=2, ensure_ascii=False) + "\n")
    docs.write_results(package, manifest, results)


def status_of(test_id: str, results: dict) -> str:
    entry = results.get(test_id)
    if not entry:
        return "todo"
    marks = [c["result"] for c in entry["checks"]]
    if "FAIL" in marks:
        return "FAIL"
    if marks and all(m == "PASS" for m in marks):
        return "pass"
    return "partial"


def verify_base(manifest: dict) -> None:
    for region, base in manifest["bases"].items():
        for rel, digest in manifest["base_hashes"][region].items():
            if sha256(Path(base) / rel) != digest:
                raise SystemExit(f"The clean {region} disc changed since the build ({Path(base) / rel}). "
                                 "Rebuild the package.")


def show(test: dict) -> None:
    print("=" * WIDTH)
    say(f"{test['id']}  {test['title']}   (about {test['minutes']} min)")
    say(f"Covers: {test['covers']}", "  ")
    for note in test.get("notes", []):
        say(f"Note: {note}", "  ")
    if test.get("app_steps"):
        print("\nIn the app first:")
        for i, step in enumerate(test["app_steps"], 1):
            say(f"{i}. {step}", "  ")
    if test.get("steps"):
        print("\nIn the game:")
        for i, step in enumerate(test["steps"], 1):
            say(f"{i}. {step}", "  ")
    print("\nPASS when:")
    for i, check in enumerate(test["checks"], 1):
        say(f"[{i}] {check}", "  ")
    print("=" * WIDTH)


def ask(prompt: str, allowed: str) -> str:
    while True:
        answer = input(prompt).strip().lower()
        if answer[:1] in allowed:
            return answer[:1]


def record(test: dict, after_lines: list[str]) -> dict:
    checks = []
    for i, check in enumerate(test["checks"], 1):
        say(f"[{i}] {check}")
        mark = ask("    p = pass, f = fail, s = not tested: ", "pfs")
        note = input("    note (Enter for none): ").strip()
        checks.append({"check": check, "result": {"p": "PASS", "f": "FAIL", "s": "NOT TESTED"}[mark], "note": note})
    general = input("Anything else you noticed (Enter for none): ").strip()
    return {"title": test["title"], "when": datetime.now().isoformat(timespec="seconds"), "checks": checks,
            "note": general, "after": after_lines}


def run_after(test_id: str, card: Path, manifest: dict) -> list[str]:
    from fe_modding.project import ModProject  # noqa: F401  (path setup check)
    from .context import Context
    from .scenarios import by_id

    scenario = by_id().get(test_id)
    if scenario is None or scenario.after is None:
        return []

    class _RunProject:                      # read-only view of the run tree for the after-check
        def __init__(self, extracted: Path):
            self.extracted_dir = extracted

        def read_logical(self, name: str) -> bytes:
            assert name == "game_data"
            return (self.extracted_dir / "files" / "FE8Data.bin").read_bytes()

    run = Path(manifest["run_root"]) / test_id
    try:
        return scenario.after(card, Context(_RunProject(run), Path(manifest["saves"])))
    except Exception as exc:  # noqa: BLE001
        return [f"The automatic check failed: {exc!r}"]


def launch(test: dict, manifest: dict, package: Path) -> list[str]:
    run_root = Path(manifest["run_root"])
    run = run_root / test["id"]
    card = run / "card_a"
    if test["boot"] == "image":
        main_dol = Path(test["image"])
        if not main_dol.is_file():
            print(f"{main_dol} is missing.")
            return []
    else:
        print("Building the run tree (hard links to the clean disc)...", flush=True)
        main_dol = assemble_run_tree(Path(manifest["bases"][test["region"]]), package / "patches" / test["id"], run)
    if card.exists():
        shutil.rmtree(card)
    card.mkdir(parents=True)
    if test.get("card_from"):
        previous = run_root / test["card_from"] / "card_a"
        if not any(previous.glob("*.gci")):
            print(f"Run {test['card_from']} first: this test continues from the saves it leaves.")
            return []
        for gci in previous.glob("*.gci"):
            shutil.copy2(gci, card / gci.name)
    for gci in (package / "cards" / test["id"]).glob("*.gci"):
        shutil.copy2(gci, card / gci.name)
    user = run_root / "DolphinUser"
    source_config = Path(os.environ.get("APPDATA", "")) / "Dolphin Emulator" / "Config"
    prepare_dolphin_user(user, source_config)
    command = dolphin_command(Path(manifest["dolphin"]), user, main_dol, card, gdb=test.get("gdb", False),
                              volume=normal_volume(source_config))
    write_lf(run / "INSTRUCTIONS.txt", docs.test_text(test))
    os.startfile(run / "INSTRUCTIONS.txt") if hasattr(os, "startfile") else None
    for boot in range(1, test.get("boots", 1) + 1):
        if boot > 1:
            input(f"Boot {boot} of {test['boots']}: press Enter to start Dolphin again (same card)...")
        print(f"Starting Dolphin (boot {boot}). Close Dolphin when you are done; this window waits.", flush=True)
        run_dolphin(command, test.get("watch"), Path(manifest["app"]).parent)
    return run_after(test["id"], card, manifest)


def menu(package: Path) -> None:
    manifest = load_manifest(package)
    if not manifest:
        raise SystemExit(f"No manifest in {package}: run the build first.")
    verify_base(manifest)
    tests = manifest["tests"]
    while True:
        results = load_results(package)
        print("\nTests:")
        for test_id in manifest["order"]:
            test = tests.get(test_id)
            if test is None:
                continue
            optional = " (optional)" if test.get("optional") else ""
            print(f"  {status_of(test_id, results):8} {test_id:5} {test['title']}{optional}")
        pending = [t for t in manifest["order"] if t in tests and status_of(t, results) == "todo"
                   and not tests[t].get("optional")]
        default = pending[0] if pending else None
        choice = input(f"\nTest id to run{f' (Enter = {default})' if default else ''}, r = results, q = quit: ").strip()
        if choice.lower() == "q":
            return
        if choice.lower() == "r":
            print((package / "RESULTS.md").read_text(encoding="utf-8") if (package / "RESULTS.md").is_file() else "None yet.")
            continue
        test_id = choice.upper() if choice else default
        if test_id not in tests:
            print("Unknown test.")
            continue
        test = tests[test_id]
        show(test)
        if test.get("boot") == "none":
            input("Do the app steps above, then press Enter to record the results...")
            after = []
        else:
            if input("Press Enter to start (s = skip this test): ").strip().lower() == "s":
                continue
            after = launch(test, manifest, package)
        if after:
            print("\nAutomatic check of the saved card:")
            for line in after:
                say(line, "  ")
        results[test_id] = record(test, after)
        save_results(package, manifest, results)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--package", type=Path, required=True)
    menu(parser.parse_args().package.resolve())


if __name__ == "__main__":
    main()
