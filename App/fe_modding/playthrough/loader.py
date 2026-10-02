"""Reading a chapter's files into a :class:`~.world.World`."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from ..formats import cp_data, map_file, message
from ..formats.cmb.binary import read_cmb
from . import setup
from .world import World


def link_grid(map_data) -> Optional[list]:
    """The composed link grid, or None when the map has no link sections (everything open)."""
    if map_data is None or not any(g is not None for g in (map_data.link, map_data.link_at, map_data.link_abs)):
        return None
    try:
        return map_file.compose_link_status_grid(map_data)
    except map_file.MapFileError:
        return None


def playable_area(map_data) -> Optional[tuple]:
    cap, extra = map_data.capacity, map_data.extra
    if extra is not None and 0 < extra.grid_buffer * 2 < min(cap.x_size, cap.y_size):
        b = extra.grid_buffer
        return (b, cap.x_size - b, b, cap.y_size - b)
    return None


def chapter_script(files: Path, script_path: Optional[Path], source: Optional[str] = None,
                   problems: Optional[list] = None):
    """The chapter's compiled script; its unsaved ``source`` when given and it compiles."""
    if script_path is None or not Path(script_path).exists():
        return None
    base = read_cmb(Path(script_path).read_bytes())
    if source is None:
        return base
    try:
        from ..formats.cmb.compiler import compile_source

        return compile_source(source, base=base).script
    except Exception as exc:  # noqa: BLE001 - play the saved file instead
        if problems is not None:
            problems.append(f"The edited script doesn't compile ({exc}); playing the saved file.")
        return base


def load_messages(files: Path, chapter_stem: Optional[str]) -> dict:
    out = {}
    names = ["common.m"] + ([f"{chapter_stem.lower()}.m"] if chapter_stem else [])
    for name in names:
        path = files / "Mess" / name
        if not path.exists():
            continue
        try:
            for m in message.read_messages_path(path):
                out.setdefault(m.speaker, m.text)
        except Exception:  # noqa: BLE001 - a broken message file only loses its texts
            continue
    return out


def load_world(files: Path, *, map_data, terrain_grid, terrain_types, documents, fe8, script=None,
               difficulty: str = "n", names: Optional[dict] = None, chapter_stem: Optional[str] = None,
               problems: Optional[list] = None) -> World:
    """``files`` is the extracted disc's ``files/`` folder; ``documents`` the
    chapter's dispos variants; ``script`` the chapter's compiled script (or
    None); ``chapter_stem`` its file stem (``C05``), which names the chapter's
    message file (``Mess/c05.m``)."""
    problems = problems if problems is not None else []
    cap = map_data.capacity
    scripts, script_names = [], []
    if script is not None:
        scripts.append(script)
        script_names.append("chapter")
    startup = files / "Scripts" / "startup.cmb"
    if startup.exists():
        try:
            scripts.append(read_cmb(startup.read_bytes()))
            script_names.append("startup.cmb")
        except Exception as exc:  # noqa: BLE001
            problems.append(f"startup.cmb could not be read: {exc}")
    cp = None
    cp_path = files / "cp_data.bin"
    if cp_path.exists():
        try:
            cp = cp_data.parse_cp_data(cp_path.read_bytes())
        except Exception as exc:  # noqa: BLE001
            problems.append(f"cp_data.bin could not be read ({exc}): the AI uses its built-in fallback")
    world = World(
        width=cap.x_size, height=cap.y_size, terrain=terrain_grid or [[""] * cap.y_size for _ in range(cap.x_size)],
        terrain_types=list(terrain_types or []), fe8=fe8, link=link_grid(map_data), playable=playable_area(map_data),
        scripts=scripts, script_names=script_names, cp=cp, messages=load_messages(files, chapter_stem),
        groups=setup.groups(documents), difficulty=difficulty, names=dict(names or {}),
    )
    return world
