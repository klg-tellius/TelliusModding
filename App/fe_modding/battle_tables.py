"""Project-level access to single ``.dbx`` entries of ``zdbx.cmp``.

The battle-engine editors (weapons, sceneries, cameras) all read one entry's
text, change it with a pure function from ``formats/`` and write the archive
back through ``ModProject.write_keeping_original`` - so the first edit keeps
the vanilla ``zdbx.cmp`` for "restore". Entry names are archive paths such as
``xwp/IRONSWORD.dbx``.
"""

from __future__ import annotations

from pathlib import Path

from . import model_slots
from .exceptions import ProjectError
from .formats import zdbx
from .project import ModProject


def _archive(project: ModProject) -> Path:
    return model_slots._files(project) / "zdbx.cmp"


def entry_names(project: ModProject, folder: str, suffix: str = ".dbx") -> list[str]:
    """Archive paths under ``folder/`` (e.g. ``xwp``) ending in ``suffix``, in pack order."""
    return [n for n in model_slots._read_zdbx(project) if n.startswith(folder + "/") and n.endswith(suffix)]


def read_entries(project: ModProject, folder: str, suffix: str = ".dbx") -> dict[str, str]:
    """Every ``folder/`` entry's text by archive path (one archive read)."""
    return {n: b.decode("shift_jis") for n, b in model_slots._read_zdbx(project).items()
            if n.startswith(folder + "/") and n.endswith(suffix)}


def modified_entries(project: ModProject, folder: str) -> set[str]:
    """Paths under ``folder/`` that differ from vanilla (or are new)."""
    current = model_slots._read_zdbx(project)
    vanilla = dict(zdbx.read_zdbx_files(model_slots._vanilla_bytes(project, _archive(project))))
    return {n for n, b in current.items() if n.startswith(folder + "/") and vanilla.get(n) != b}


def read_entries(project: ModProject, folder: str, suffix: str = ".dbx") -> dict[str, str]:
    """Every ``folder/`` entry's text by archive path (one archive read)."""
    return {n: b.decode("shift_jis") for n, b in model_slots._read_zdbx(project).items()
            if n.startswith(folder + "/") and n.endswith(suffix)}


def modified_entries(project: ModProject, folder: str) -> set[str]:
    """Paths under ``folder/`` that differ from vanilla (or are new)."""
    current = model_slots._read_zdbx(project)
    vanilla = dict(zdbx.read_zdbx_files(model_slots._vanilla_bytes(project, _archive(project))))
    return {n for n, b in current.items() if n.startswith(folder + "/") and vanilla.get(n) != b}


def read_entry(project: ModProject, name: str) -> str:
    tables = model_slots._read_zdbx(project)
    if name not in tables:
        raise ProjectError(f"zdbx.cmp has no {name}.")
    return tables[name].decode("shift_jis")


def write_entry(project: ModProject, name: str, text: str, *, create: bool = False) -> None:
    """Replace one entry's text; ``create=True`` allows a new entry."""
    tables = model_slots._read_zdbx(project)
    if name not in tables and not create:
        raise ProjectError(f"zdbx.cmp has no {name}.")
    try:
        tables[name] = zdbx.encode_dbx(text)
    except UnicodeEncodeError as exc:
        raise ProjectError(f"{name} has a character Shift-JIS cannot hold: {exc.reason}") from exc
    model_slots._write_zdbx(project, tables)


def remove_entry(project: ModProject, name: str) -> None:
    tables = model_slots._read_zdbx(project)
    if tables.pop(name, None) is None:
        raise ProjectError(f"zdbx.cmp has no {name}.")
    model_slots._write_zdbx(project, tables)


def vanilla_entry(project: ModProject, name: str) -> str | None:
    """The entry as extracted (None when vanilla has no such entry)."""
    data = model_slots._vanilla_bytes(project, _archive(project))
    tables = dict(zdbx.read_zdbx_files(data))
    return tables[name].decode("shift_jis") if name in tables else None


def is_modified(project: ModProject, name: str) -> bool:
    try:
        current = read_entry(project, name)
    except ProjectError:
        current = None
    return current != vanilla_entry(project, name)


def restore_entry(project: ModProject, name: str) -> None:
    """Put one entry back to vanilla (removing it when vanilla has none)."""
    original = vanilla_entry(project, name)
    if original is None:
        remove_entry(project, name)
    else:
        write_entry(project, name, original, create=True)
