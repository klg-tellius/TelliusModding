"""References that matter when removing streamed music and THP videos.

The front-end uses native code rather than chapter scripts for a few assets.
Those assets may be replaced, but deleting them leaves the title/file-menu
flow asking the DVD system for a file which is no longer present.  Everything
else can be removed deliberately; callers are reported so the editor can make
the risk visible without pretending every retail file is mandatory.
"""

from __future__ import annotations

import re
from pathlib import Path
from .game_files import as_path


# ``opening.thp`` is started by the title/demo flow.  The other retail THPs
# are chapter/ending movies (or the shared chapter-title movie).
FRONT_END_VIDEOS = frozenset({"opening.thp"})

# Native front-end cue names.  ENV_TITLE is sequenced in the retail catalog
# rather than backed by an STM; SELECT1/2 are streamed selection/menu themes.
# Keeping all three here also documents the executable-owned names if a region
# or modified catalog maps ENV_TITLE to a stream later.
FRONT_END_BGM_CUES = frozenset({"BGM_ENV_TITLE1", "BGM_SELECT1", "BGM_SELECT2"})

_BGM = re.compile(rb"BGM_[A-Z0-9_]+")
_MOVIE = re.compile(rb"(?i:movie/[a-z0-9_.-]+\.thp)")


def executable_bgm_cues(main_dol: Path | str) -> frozenset[str]:
    """ASCII BGM names embedded in ``main.dol`` (native, not script-owned)."""
    try:
        data = Path(main_dol).read_bytes()
    except OSError:
        return frozenset()
    return frozenset(match.group().decode("ascii") for match in _BGM.finditer(data))


def executable_video_paths(main_dol: Path | str) -> frozenset[str]:
    """Normalized THP paths embedded in ``main.dol``."""
    try:
        data = Path(main_dol).read_bytes()
    except OSError:
        return frozenset()
    return frozenset(match.group().decode("ascii").replace("\\", "/").lower()
                     for match in _MOVIE.finditer(data))


def front_end_video_reason(path: Path | str) -> str:
    if Path(path).name.casefold() in FRONT_END_VIDEOS:
        return "It is the title/demo movie used by the game's front-end menu. Replace it instead."
    return ""


def front_end_track_cues(cue_names: list[str] | tuple[str, ...] | set[str]) -> list[str]:
    """Front-end native cues among the cues which target one STM track."""
    return sorted(FRONT_END_BGM_CUES.intersection(cue_names))


def script_video_users(scripts_dir: Path | str, video_name: str) -> list[str]:
    """Chapter script files containing a literal path to ``video_name``.

    CMB string pools retain the path as ASCII, so a case-insensitive byte scan
    is sufficient and avoids decompiling every script merely for a warning.
    """
    needle = ("movie/" + Path(video_name).name).encode("ascii", "ignore").lower()
    users = []
    root = as_path(scripts_dir)
    if not root.is_dir() or not needle:
        return users
    for script in sorted(root.glob("*.cmb")):
        try:
            if needle in script.read_bytes().lower():
                users.append(script.stem)
        except OSError:
            continue
    return users
