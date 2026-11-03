"""Persistent app-level settings (kept outside any project folder)."""

from __future__ import annotations

import json
from pathlib import Path

APP_DIR = Path.home() / ".tellius_modding"
RECENT_PROJECTS_FILE = APP_DIR / "recent_projects.json"
MAX_RECENT_PROJECTS = 10


def load_recent_projects() -> list[Path]:
    if not RECENT_PROJECTS_FILE.exists():
        return []
    try:
        with RECENT_PROJECTS_FILE.open("r", encoding="utf-8") as f:
            paths = json.load(f)
    except (json.JSONDecodeError, OSError):
        return []
    return [Path(p) for p in paths if isinstance(p, str)]


def add_recent_project(directory: Path) -> None:
    directory = Path(directory).resolve()
    recent = [p for p in load_recent_projects() if p.resolve() != directory]
    recent.insert(0, directory)
    recent = recent[:MAX_RECENT_PROJECTS]

    APP_DIR.mkdir(parents=True, exist_ok=True)
    with RECENT_PROJECTS_FILE.open("w", encoding="utf-8") as f:
        json.dump([str(p) for p in recent], f, indent=2)


def remove_recent_project(directory: Path) -> None:
    directory = Path(directory).resolve()
    recent = [p for p in load_recent_projects() if p.resolve() != directory]
    APP_DIR.mkdir(parents=True, exist_ok=True)
    with RECENT_PROJECTS_FILE.open("w", encoding="utf-8") as f:
        json.dump([str(p) for p in recent], f, indent=2)


SETTINGS_FILE = APP_DIR / "settings.json"


def load_setting(key: str, default=None):
    try:
        with SETTINGS_FILE.open("r", encoding="utf-8") as f:
            settings = json.load(f)
    except (json.JSONDecodeError, OSError):
        return default
    return settings.get(key, default) if isinstance(settings, dict) else default


def save_setting(key: str, value) -> None:
    try:
        with SETTINGS_FILE.open("r", encoding="utf-8") as f:
            settings = json.load(f)
        if not isinstance(settings, dict):
            settings = {}
    except (json.JSONDecodeError, OSError):
        settings = {}
    settings[key] = value
    APP_DIR.mkdir(parents=True, exist_ok=True)
    with SETTINGS_FILE.open("w", encoding="utf-8") as f:
        json.dump(settings, f, indent=2)
