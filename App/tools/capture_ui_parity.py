"""Capture matching FE9/FE10 routes from the real Tk app for UI parity review.

The projects are opened read-only by this tool: it navigates and captures, but never invokes an
editor save action. User settings and recent-project state are replaced with in-memory stand-ins.
"""

from __future__ import annotations

import argparse
import ctypes
import json
import sys
import time
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "App"))

try:
    ctypes.windll.shcore.SetProcessDpiAwareness(2)
except (AttributeError, OSError):
    pass

from PIL import ImageGrab  # noqa: E402

from fe_modding import config  # noqa: E402


ROUTES = (
    ("home",),
    ("characters",),
    ("data",),
    ("data", "classes"),
    ("asset", "conversations"),
    ("asset", "fonts"),
    ("asset", "scripts"),
    ("data", "flags"),
    ("data", "ai"),
)
SIZE = (1440, 900)


def _neutralize_user_config() -> None:
    settings: dict[str, object] = {}
    real_load = config.load_setting
    config.load_setting = lambda key, default=None: settings.get(key, real_load(key, default))
    config.save_setting = lambda key, value: settings.__setitem__(key, value)
    config.load_recent_projects = lambda: []
    config.add_recent_project = lambda _directory: None
    config.remove_recent_project = lambda _directory: None


def _pump(app, seconds: float) -> None:
    until = time.monotonic() + seconds
    while time.monotonic() < until:
        app.update()
        time.sleep(0.025)


def _wait_for_index(app, timeout: float = 120.0) -> None:
    until = time.monotonic() + timeout
    while time.monotonic() < until:
        app.update()
        shell = app._shell
        if shell is not None and shell.index is not None and getattr(shell.index, "ready", True):
            return
        time.sleep(0.05)
    raise TimeoutError("project index did not become ready")


def _frame_bounds(top) -> tuple[int, int, int, int]:
    hwnd = int(top.wm_frame(), 16)
    rect = (ctypes.c_long * 4)()
    try:
        ctypes.windll.dwmapi.DwmGetWindowAttribute(hwnd, 9, ctypes.byref(rect), ctypes.sizeof(rect))
        if rect[2] > rect[0]:
            return rect[0], rect[1], rect[2], rect[3]
    except (AttributeError, OSError):
        pass
    x, y = top.winfo_rootx(), top.winfo_rooty()
    return x, y, x + top.winfo_width(), y + top.winfo_height()


def _capture(app, target: Path) -> list[int]:
    app.lift()
    app.attributes("-topmost", True)
    _pump(app, 0.35)
    image = ImageGrab.grab(bbox=_frame_bounds(app), all_screens=True)
    app.attributes("-topmost", False)
    target.parent.mkdir(parents=True, exist_ok=True)
    image.save(target, optimize=True)
    return list(image.size)


def capture_project(project: Path, game: str, out: Path) -> list[dict]:
    from fe_modding.gui.app import MainWindow
    from fe_modding.gui.pages.flags import FlagsPanel

    scan_budget = FlagsPanel._scan_budget
    FlagsPanel._scan_budget = lambda _self: None  # avoid an irrelevant background scan during capture
    app = MainWindow()
    app.state("normal")
    app.geometry(f"{SIZE[0]}x{SIZE[1]}+20+20")
    records = []
    try:
        app._load_project(project)
        _wait_for_index(app)
        for route in ROUTES:
            item = {"game": game, "route": list(route)}
            try:
                app._shell.navigate(route)
                _pump(app, 1.0)
                filename = f"{game}_{'_'.join(route)}.png"
                item.update(file=filename, size=_capture(app, out / filename), status="captured")
                print(f"captured {game} {'/'.join(route)}", flush=True)
            except Exception as exc:  # one route should not hide the remaining evidence
                item.update(status="failed", error=f"{type(exc).__name__}: {exc}")
                print(f"FAILED {game} {'/'.join(route)}: {exc}", flush=True)
            records.append(item)
    finally:
        app.destroy()
        FlagsPanel._scan_budget = scan_budget
    return records


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--fe9-project", type=Path, required=True)
    parser.add_argument("--fe10-project", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)
    _neutralize_user_config()
    records = capture_project(args.fe9_project, "fe9", args.out)
    records += capture_project(args.fe10_project, "fe10", args.out)
    manifest = {"captured": date.today().isoformat(), "window": list(SIZE), "routes": records}
    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return 1 if any(item["status"] != "captured" for item in records) else 0


if __name__ == "__main__":
    raise SystemExit(main())
