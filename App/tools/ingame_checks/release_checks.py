"""Release 1.0 package checks (1.0 checklist §0 and §7) on a Windows ZIP, built here or downloaded from CI.

    python -m tools.ingame_checks.release_checks <TelliusModding-Windows-x64.zip>

* RZ1: the ZIP extracts into a new folder; ``TelliusModding.exe --self-test`` and
  ``TelliusPatcher.exe --self-test`` pass from an empty working folder with a clean environment
  (``release/build_windows.py``'s smoke test); ``_internal`` sits next to the executable.
* RZ2: ``START-HERE.txt`` names the MIT licence, and every link in it is to the project's site or
  repository; the release notes start with ``# Tellius Modding v<__version__>``.

Results go to the in-game results table. Getting the ZIP needs a download (the CI artifact) or
PyInstaller (``release/requirements-build.txt``); neither is fetched by this script.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tempfile
import zipfile
from datetime import datetime
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    __package__ = "tools.ingame_checks"

from .core import ROOT  # noqa: E402
from .run import write_table  # noqa: E402
from fe_modding import __version__  # noqa: E402

REPO = Path(__file__).resolve().parents[3]


def clean_env() -> dict:
    env = dict(os.environ)
    env["PATH"] = str(Path(os.environ["SystemRoot"]) / "System32")
    for key in ("PYTHONHOME", "PYTHONPATH"):
        env.pop(key, None)
    env["PYTHONNOUSERSITE"] = "1"
    return env


def self_test(exe: Path, report: Path) -> tuple[bool, str]:
    with tempfile.TemporaryDirectory(prefix="tellius-release-") as cwd:
        proc = subprocess.run([str(exe), "--self-test", str(report)], cwd=cwd, env=clean_env(), timeout=300)
    if not report.is_file():
        return False, f"{exe.name}: no report (exit {proc.returncode})"
    result = json.loads(report.read_text(encoding="utf-8"))
    return bool(result.get("ok")), f"{exe.name}: {'ok' if result.get('ok') else result}"


def check_zip(zip_path: Path) -> list[tuple[str, str, list, str, str]]:
    rows = []
    with tempfile.TemporaryDirectory(prefix="tellius-zip-") as temp:
        folder = Path(temp) / "TelliusModding"
        with zipfile.ZipFile(zip_path) as archive:
            archive.extractall(folder)
        exe = next(folder.rglob("TelliusModding.exe"), None)
        patcher = next(folder.rglob("TelliusPatcher.exe"), None)
        details, ok = [], exe is not None and patcher is not None
        if exe is not None:
            ok &= (exe.parent / "_internal").is_dir()
            passed, text = self_test(exe, Path(temp) / "app.json")
            ok &= passed
            details.append(text)
        if patcher is not None:
            passed, text = self_test(patcher, Path(temp) / "patcher.json")
            ok &= passed
            details.append(text)
        rows.append(("RZ1", "Release ZIP: extracts, the app and the patcher pass their self-tests",
                     ["1.0 §0 Préparation"], "PASS" if ok else "FAIL",
                     "; ".join(details) or "TelliusModding.exe or TelliusPatcher.exe missing"))
        start = next(folder.rglob("START-HERE.txt"), None)
        text = start.read_text(encoding="utf-8", errors="replace") if start else ""
        links = re.findall(r"https?://\S+", text)
        foreign = [u for u in links if "klg-tellius" not in u and "github.com/klg-tellius" not in u]
        notes = (REPO / "release" / "RELEASE-NOTES.md").read_text(encoding="utf-8").splitlines()
        ok = bool(start) and "MIT" in text and not foreign and notes[:1] == [f"# Tellius Modding v{__version__}"]
        rows.append(("RZ2", "START-HERE and release notes", ["1.0 §7 Documentation"], "PASS" if ok else "FAIL",
                     f"START-HERE {'found' if start else 'MISSING'}, MIT {'named' if 'MIT' in text else 'MISSING'}, "
                     f"{len(links)} links ({len(foreign)} elsewhere: {foreign[:3]}); notes start {notes[:1]}"))
    return rows


def main() -> None:
    zip_path = Path(sys.argv[1])
    results_path = ROOT / "results.json"
    results = json.loads(results_path.read_text(encoding="utf-8")) if results_path.is_file() else {}
    for cid, title, covers, result, details in check_zip(zip_path):
        print(f"{cid}: {result}: {details}")
        results[cid] = {"region": "Windows", "title": title, "covers": covers, "result": result,
                        "details": details, "when": datetime.now().isoformat(timespec="minutes")}
    write_table(results)


if __name__ == "__main__":
    main()
