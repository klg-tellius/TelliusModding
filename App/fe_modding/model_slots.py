"""New model slots: copy a battle or map model under a new name and point
characters or classes at it, leaving the vanilla model to its other users.

Battle models (``zu/<code>/``) are chosen through ``zdbx.cmp``: a copy gets
its own folder, its packs renamed to the new code (``<code>_<weapon>.pak``)
and its own ``zu/<code>.dbx``/``zu/<code>_prm.dbx``; a job-list line then
selects it by animation ID, class plus character, or class (see
``formats/zdbx.py``).

Map models (``ymu/<folder>/``) are chosen through ``FE8Anim.bin``: a copy gets
one registry record per weapon type under a new base animation ID, and a
character record points at that ID (``aid_unpromoted``/``aid_promoted`` in
``FE8Data.bin``; see ``formats/anim_registry.py``).
"""

from __future__ import annotations

import re
import shutil
from dataclasses import replace
from pathlib import Path

from .exceptions import ProjectError
from .formats import anim_registry, fe8data, zdbx
from .game_profile import ANIM, BATTLE_TABLES, GAME_DATA, logical_path_of, profile_of
from .project import ModProject

AID_BASE_RE = re.compile(r"^AID_[A-Z0-9_]+$")
FOLDER_RE = re.compile(r"^[a-z0-9_]+$")


def _files(project: ModProject) -> Path:
    return project.extracted_dir / "files"


# The codecs below are Path of Radiance's (zdbx, FE8Anim, FE8Data): another game's file of the same
# role is a different format, so it is refused until its profile lists the feature.
_LOGICAL_FEATURES = {"battle_data": BATTLE_TABLES, "anim_data": ANIM, "game_data": GAME_DATA}


def _logical(project: ModProject, name: str) -> Path:
    profile = profile_of(project)
    feature = _LOGICAL_FEATURES.get(name)
    if feature is not None and not profile.supports(feature):
        raise ProjectError(profile.unavailable(feature))
    return logical_path_of(project, name)


def _vanilla_bytes(project: ModProject, path: Path) -> bytes:
    """The file as extracted: its kept original when an edit replaced it."""
    original = project.originals_dir / path.relative_to(project.extracted_dir)
    return (original if original.is_file() else path).read_bytes()


# -- battle models --------------------------------------------------------------

def _read_zdbx(project: ModProject) -> dict[str, bytes]:
    return dict(zdbx.read_zdbx_files(_logical(project, "battle_data").read_bytes()))


def _write_zdbx(project: ModProject, files: dict[str, bytes]) -> None:
    project.write_keeping_original(_logical(project, "battle_data"), zdbx.build_zdbx_archive(list(files.items())))


def battle_model_codes(project: ModProject) -> list[str]:
    """Codes with both a ``zu/`` folder and a ``zu/<code>.dbx`` table."""
    tables = {name[3:-4] for name in _read_zdbx(project) if name.startswith("zu/") and not name.endswith("_prm.dbx")}
    folder = _files(project) / "zu"
    return sorted(code for code in tables if (folder / code).is_dir())


def clone_battle_model(project: ModProject, source_code: str, new_code: str) -> list[Path]:
    """Copy ``zu/<source_code>/`` to ``zu/<new_code>/`` with its tables; return the new files."""
    if not zdbx.MODEL_CODE_RE.match(new_code):
        raise ProjectError(f"A model code is 4 lowercase letters or digits (got {new_code!r}).")
    source = _files(project) / "zu" / source_code
    dest = _files(project) / "zu" / new_code
    tables = _read_zdbx(project)
    if not source.is_dir() or f"zu/{source_code}.dbx" not in tables:
        raise ProjectError(f"No battle model {source_code!r}.")
    if dest.exists() or f"zu/{new_code}.dbx" in tables:
        raise ProjectError(f"The battle model {new_code!r} already exists.")
    dest.mkdir(parents=True)
    written = []
    for path in sorted(source.iterdir()):
        if not path.is_file():
            continue
        name = path.name
        if name.startswith(f"{source_code}_") and path.suffix in (".pak", ".cmp"):
            name = new_code + name[len(source_code):]
        shutil.copy2(path, dest / name)
        written.append(dest / name)
    model = tables[f"zu/{source_code}.dbx"].decode("shift_jis")
    tables[f"zu/{new_code}.dbx"] = zdbx.encode_dbx(zdbx.clone_model_dbx(model, new_code))
    param = tables.get(f"zu/{source_code}_prm.dbx")
    if param is not None:
        tables[f"zu/{new_code}_prm.dbx"] = zdbx.encode_dbx(zdbx.clone_param_dbx(param.decode("shift_jis"), new_code))
    _write_zdbx(project, tables)
    return written


def assign_battle_model(project: ModProject, code: str, *, jid: str | None = None,
                        pid: str | None = None, aid: str | None = None, comment: str = "") -> None:
    """Add or replace the job-list line selecting ``code`` (see ``zdbx.set_job_model``)."""
    tables = _read_zdbx(project)
    if f"zu/{code}.dbx" not in tables:
        raise ProjectError(f"No battle model {code!r}.")
    text = tables[zdbx.JOB_LIST].decode("shift_jis")
    tables[zdbx.JOB_LIST] = zdbx.encode_dbx(zdbx.set_job_model(text, code, jid=jid, pid=pid, aid=aid, comment=comment))
    _write_zdbx(project, tables)


def set_battle_texture(project: ModProject, code: str, key: str, texture: str) -> None:
    """Make ``zu/<code>/<texture>.tpl`` the texture for an army key (``自軍``,
    ``敵軍``, ``中立``, ``味方``), a ``PID_`` or an ``AID_``."""
    tables = _read_zdbx(project)
    name = f"zu/{code}_prm.dbx"
    if name not in tables:
        raise ProjectError(f"No parameter table for {code!r}.")
    tables[name] = zdbx.encode_dbx(zdbx.set_param_texture(tables[name].decode("shift_jis"), key, texture))
    _write_zdbx(project, tables)


def remove_battle_texture(project: ModProject, code: str, key: str) -> None:
    tables = _read_zdbx(project)
    name = f"zu/{code}_prm.dbx"
    if name not in tables:
        raise ProjectError(f"No parameter table for {code!r}.")
    tables[name] = zdbx.encode_dbx(zdbx.remove_param_texture(tables[name].decode("shift_jis"), key))
    _write_zdbx(project, tables)


def job_list(project: ModProject) -> list[tuple[str, str, str]]:
    """The job list's ``(key, code, comment)`` lines."""
    return zdbx.job_list_lines(_read_zdbx(project)[zdbx.JOB_LIST].decode("shift_jis"))


def remove_job_line(project: ModProject, key: str) -> None:
    tables = _read_zdbx(project)
    text, removed = zdbx.remove_job_lines(tables[zdbx.JOB_LIST].decode("shift_jis"), key=key)
    if not removed:
        raise ProjectError(f"No job-list line {key!r}.")
    tables[zdbx.JOB_LIST] = zdbx.encode_dbx(text)
    _write_zdbx(project, tables)


def vanilla_battle_codes(project: ModProject) -> set[str]:
    tables = zdbx.read_zdbx_files(_vanilla_bytes(project, _logical(project, "battle_data")))
    return {name[3:-4] for name, _data in tables if name.startswith("zu/") and not name.endswith("_prm.dbx")}


def remove_battle_model(project: ModProject, code: str) -> int:
    """Delete a battle model made by :func:`clone_battle_model`: its
    ``zu/<code>/`` folder, its two tables and every job-list line selecting
    it (those characters and classes fall back to their other lines; a line
    the extracted job list also had gets its extracted model back).
    Returns the number of job-list lines changed. Vanilla models refuse."""
    if code in vanilla_battle_codes(project):
        raise ProjectError(f"{code!r} is one of the game's own battle models.")
    tables = _read_zdbx(project)
    if f"zu/{code}.dbx" not in tables:
        raise ProjectError(f"No battle model {code!r}.")
    tables.pop(f"zu/{code}.dbx")
    tables.pop(f"zu/{code}_prm.dbx", None)
    vanilla = dict(zdbx.read_zdbx_files(_vanilla_bytes(project, _logical(project, "battle_data"))))[zdbx.JOB_LIST]
    text, removed = zdbx.release_job_lines(
        tables[zdbx.JOB_LIST].decode("shift_jis"), code, vanilla.decode("shift_jis")
    )
    tables[zdbx.JOB_LIST] = zdbx.encode_dbx(text)
    _write_zdbx(project, tables)
    folder = _files(project) / "zu" / code
    if folder.is_dir():
        shutil.rmtree(folder)
    return removed


def battle_textures(project: ModProject, code: str) -> dict[str, str]:
    param = _read_zdbx(project).get(f"zu/{code}_prm.dbx")
    return zdbx.param_textures(param.decode("shift_jis")) if param else {}


# -- map models -------------------------------------------------------------------

def _anim_path(project: ModProject) -> Path:
    return _logical(project, "anim_data")


def map_model_records(project: ModProject) -> list[anim_registry.AnimRecord]:
    return anim_registry.read_anim_registry(_anim_path(project).read_bytes())


def clone_map_model(project: ModProject, source_aid: str, new_aid: str, new_folder: str | None = None,
                    texture_ids: tuple[int, int, int, int] | None = None) -> list[Path]:
    """Register every weapon set of ``source_aid`` (a base ID such as
    ``AID_FIGHTER_BO``) again as ``new_aid``. With ``new_folder``, the
    source's ``ymu/`` folder is copied there and the new records use it;
    ``texture_ids`` replaces the four per-army texture numbers."""
    if not AID_BASE_RE.match(new_aid):
        raise ProjectError(f"An animation ID is AID_ followed by capitals, digits or _ (got {new_aid!r}).")
    records = map_model_records(project)
    sources = [r for r in records if r.base_aid == source_aid]
    if not sources:
        raise ProjectError(f"No map model {source_aid!r}.")
    if any(r.base_aid == new_aid for r in records):
        raise ProjectError(f"The animation ID {new_aid!r} already exists.")
    written = []
    folder = sources[0].class_folder
    if new_folder:
        if not FOLDER_RE.match(new_folder):
            raise ProjectError(f"A folder name is lowercase letters, digits or _ (got {new_folder!r}).")
        dest = _files(project) / "ymu" / new_folder
        if dest.exists():
            raise ProjectError(f"ymu/{new_folder}/ already exists.")
        shutil.copytree(_files(project) / "ymu" / folder.rstrip("/"), dest)
        written = sorted(p for p in dest.rglob("*") if p.is_file())
        folder = f"{new_folder}/"
    added = [
        replace(r, aid_name=new_aid + r.aid_name[len(source_aid):], class_folder=folder,
                texture_ids=texture_ids or r.texture_ids, address=0)
        for r in sources
    ]
    project.write_keeping_original(_anim_path(project), anim_registry.build_anim_registry(records + added))
    return written


def set_map_textures(project: ModProject, base_aid: str, texture_ids: tuple[int, int, int, int]) -> None:
    """Set the four per-army texture numbers (``tex_<n>.tpl``) of every
    weapon set of ``base_aid``."""
    records = map_model_records(project)
    if not any(r.base_aid == base_aid for r in records):
        raise ProjectError(f"No map model {base_aid!r}.")
    records = [replace(r, texture_ids=tuple(texture_ids)) if r.base_aid == base_aid else r for r in records]
    project.write_keeping_original(_anim_path(project), anim_registry.build_anim_registry(records))


def vanilla_map_aids(project: ModProject) -> set[str]:
    return {r.base_aid for r in anim_registry.read_anim_registry(_vanilla_bytes(project, _anim_path(project)))}


def remove_map_model(project: ModProject, base_aid: str) -> list[str]:
    """Delete a map model made by :func:`clone_map_model`: its
    ``FE8Anim.bin`` records, its copied ``ymu/`` folder when no other record
    uses it, and every character or class pointing at it, which gets its
    extracted value back. Returns what was changed. Vanilla IDs refuse."""
    if base_aid in vanilla_map_aids(project):
        raise ProjectError(f"{base_aid!r} is one of the game's own animation IDs.")
    records = map_model_records(project)
    removed = [r for r in records if r.base_aid == base_aid]
    if not removed:
        raise ProjectError(f"No map model {base_aid!r}.")
    kept = [r for r in records if r.base_aid != base_aid]
    project.write_keeping_original(_anim_path(project), anim_registry.build_anim_registry(kept))
    changes = [f"Removed {len(removed)} FE8Anim.bin records"]

    vanilla_folders = {r.class_folder for r in anim_registry.read_anim_registry(_vanilla_bytes(project, _anim_path(project)))}
    for folder in sorted({r.class_folder for r in removed}):
        path = _files(project) / "ymu" / folder.rstrip("/")
        if folder not in vanilla_folders and not any(r.class_folder == folder for r in kept) and path.is_dir():
            shutil.rmtree(path)
            changes.append(f"Deleted ymu/{folder}")

    path = _logical(project, "game_data")
    data = path.read_bytes()
    vanilla = fe8data.read_fe8data(_vanilla_bytes(project, path))
    current = fe8data.read_fe8data(data)
    for character, original in zip(current.characters, vanilla.characters):
        for field in ("aid_unpromoted", "aid_promoted"):
            if getattr(character, field) == base_aid:
                data = fe8data.patch_character_field(data, character.index, field, getattr(original, field))
                changes.append(f"{character.pid} {field} back to {getattr(original, field)}")
    for job, original in zip(current.classes, vanilla.classes):
        if job.aid == base_aid:
            data = fe8data.patch_class_field(data, job.index, "aid", original.aid)
            changes.append(f"{job.jid} aid back to {original.aid}")
    if data != path.read_bytes():
        project.write_keeping_original(path, data)
    return changes


def assign_map_model(project: ModProject, pid: str, aid: str | None, *, promoted: bool = False) -> None:
    """Point a character's unpromoted (or promoted) animation ID at ``aid``."""
    if aid is not None and not any(r.base_aid == aid for r in map_model_records(project)):
        raise ProjectError(f"No map model {aid!r}.")
    path = _logical(project, "game_data")
    data = path.read_bytes()
    characters = fe8data.read_fe8data(data).characters
    index = next((c.index for c in characters if c.pid == pid), None)
    if index is None:
        raise ProjectError(f"No character {pid!r}.")
    if aid is not None:
        data = fe8data.add_label(data, aid)
    field = "aid_promoted" if promoted else "aid_unpromoted"
    project.write_keeping_original(path, fe8data.patch_character_field(data, index, field, aid))
