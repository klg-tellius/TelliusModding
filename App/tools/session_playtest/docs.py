"""The package's readable files: START-HERE.md (the whole session on one page), one instruction
sheet per test, and RESULTS.md (regenerated after every recorded test)."""
from __future__ import annotations

from pathlib import Path

from .harness import write_lf


def test_text(test: dict) -> str:
    lines = [f"{test['id']}  {test['title']}  (about {test['minutes']} min)", "", f"Covers: {test['covers']}"]
    lines += [f"Note: {n}" for n in test.get("notes", [])]
    if test.get("app_steps"):
        lines += ["", "In the app first:"] + [f"  {i}. {s}" for i, s in enumerate(test["app_steps"], 1)]
    if test.get("steps"):
        lines += ["", "In the game:"] + [f"  {i}. {s}" for i, s in enumerate(test["steps"], 1)]
    lines += ["", "PASS when:"] + [f"  [{i}] {c}" for i, c in enumerate(test["checks"], 1)]
    return "\n".join(lines) + "\n"


def write_docs(package: Path, manifest: dict, scenarios=None) -> None:
    tests = [manifest["tests"][t] for t in manifest["order"] if t in manifest["tests"]]
    total = sum(t["minutes"] for t in tests if not t.get("optional"))
    size = sum(t.get("patch_bytes", 0) for t in tests)
    out = ["# In-game test session", "",
           f"{len(tests)} tests, about {total} minutes without the optional ones. Patches take "
           f"{size / 1e6:.0f} MB in all (a disc image is 1.4 GB each).", "",
           "## How it works", "",
           "1. Double-click **Start-Session.cmd**. It lists the tests; press Enter to run the next one.",
           "2. The runner rebuilds that test's disc tree (hard links to the clean disc plus the few patched "
           "files), opens its instruction sheet in Notepad, and starts Dolphin with an isolated user folder "
           "and a memory card holding only that test's save.",
           "3. Do the steps, close Dolphin, then answer p / f / s for each check (add a note when something "
           "looks off). Results are saved after every test in results.json and RESULTS.md.",
           "", "Tests that boot with **chapter jump** skip the title and file menu: press A on the warning "
           "screen and the chapter starts. Start skips cutscenes; Tab (Dolphin's default hotkey) turns the "
           "speed limit off. Map animations run at 2x unless a test is about animation.",
           "", "Your normal Dolphin settings and saves are never used or changed: the controller and graphics "
           "settings are copied once into the session's own Dolphin user folder.", "",
           "Send RESULTS.md back in the chat when you are done (or after any FAIL you want looked at now).", "",
           "## Order", "", "| Test | What | Min | |", "| --- | --- | ---: | --- |"]
    for t in tests:
        out.append(f"| {t['id']} | {t['title']} | {t['minutes']} | {'optional' if t.get('optional') else ''} |")
    current = None
    for t in tests:
        if t["block"] != current:
            current = t["block"]
            out += ["", f"## {current}"]
        out += ["", f"### {t['id']} - {t['title']}", "", f"*Covers:* {t['covers']}", ""]
        out += [f"*Note:* {n}" for n in t.get("notes", [])]
        if t.get("app_steps"):
            out += ["**In the app first**", ""] + [f"{i}. {s}" for i, s in enumerate(t["app_steps"], 1)] + [""]
        if t.get("steps"):
            out += ["**In the game**", ""] + [f"{i}. {s}" for i, s in enumerate(t["steps"], 1)] + [""]
        out += ["**PASS when**", ""] + [f"- [ ] {c}" for c in t["checks"]]
    if scenarios is None:
        from . import scenarios
    NOT_COVERED = scenarios.NOT_COVERED
    out += ["", "## Not in this session", "", "| Open question | Why it is left out |", "| --- | --- |"]
    out += [f"| {what} | {why} |" for what, why in NOT_COVERED]
    write_lf(package / "START-HERE.md", "\n".join(out) + "\n")


def write_results(package: Path, manifest: dict, results: dict) -> None:
    out = ["# Session results", "", "| Test | Check | Result | Note |", "| --- | --- | --- | --- |"]
    for test_id in manifest["order"]:
        entry = results.get(test_id)
        if not entry:
            continue
        for c in entry["checks"]:
            out.append(f"| {test_id} | {c['check']} | {c['result']} | {c['note']} |")
        if entry.get("note"):
            out.append(f"| {test_id} | (general) | | {entry['note']} |")
        for line in entry.get("after", []):
            out.append(f"| {test_id} | (automatic) | | {line} |")
    missing = [t for t in manifest["order"] if t in manifest["tests"] and t not in results]
    if missing:
        out += ["", "Not run yet: " + ", ".join(missing)]
    write_lf(package / "RESULTS.md", "\n".join(out) + "\n")
