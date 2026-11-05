"""Radiant Dawn music: adding and removing tracks and cues.

A cue (``BGM_*`` in ``Sound/sound_data_en.cms``, :mod:`formats.fe10_sound`) names a sound of
``Sound/sound_us.brsar`` (``STRM_BGM_*``, :mod:`formats.brsar`), and that stream sound names a
loose ``Sound/strm/<name>.brstm``. A new track adds all three; a new cue adds only the first.
Only what the mod added can be removed: the game's own cues and sounds stay.
"""

from __future__ import annotations

import re
from pathlib import Path

from .exceptions import ProjectError
from .formats import brsar, fe10_sound, lz10
from .game_profile import files_root_of

ARCHIVE = "Sound/sound_us.brsar"
TRACK_RE = re.compile(r"[a-z0-9_]{1,40}")


def _sound_dir(project) -> Path:
    return files_root_of(project) / "Sound"


def _archive_path(project) -> Path:
    return files_root_of(project) / ARCHIVE


def _archive(project) -> bytes:
    return _archive_path(project).read_bytes()


def _vanilla_archive(project) -> bytes:
    data = project.extracted_bytes(_archive_path(project))
    return data if data is not None else _archive(project)


def _cues(project) -> bytes:
    return project.read_logical("sound_data")


def _vanilla_cues(project) -> bytes:
    raw = project.extracted_bytes(project.logical_path("sound_data"))
    return lz10.decompress(raw) if raw is not None else _cues(project)


def stream_sounds(project, stream: Path) -> list[brsar.BrsarSound]:
    """The archive's stream sounds playing ``Sound/strm/<stream>``."""
    name = Path(stream).name.casefold()
    return [sound for sound in brsar.read_brsar(_archive(project)).sounds
            if sound.sound_type == 2 and sound.external_path
            and Path(sound.external_path).name.casefold() == name]


def added_cues(project) -> set[str]:
    """Cue names the mod added (absent from the extracted sound data)."""
    original = set(fe10_sound.cue_map(_vanilla_cues(project)))
    return {name for name in fe10_sound.cue_map(_cues(project)) if name not in original}


def is_added_stream(project, stream: Path) -> bool:
    original = {sound.name for sound in brsar.read_brsar(_vanilla_archive(project)).sounds}
    sounds = stream_sounds(project, stream)
    return bool(sounds) and all(sound.name not in original for sound in sounds)


def _template_cue(project, resource: str | None) -> str:
    cues = fe10_sound.read_sound_data(_cues(project))
    same = next((cue.name for cue in cues if cue.resource == resource), None)
    return same or next(cue.name for cue in cues if cue.name.startswith("BGM_"))


def add_cue(project, name: str, stream: Path) -> str:
    """A new ``BGM_`` cue playing ``stream``'s sound (copying the settings of a cue that already
    plays it, else of the first music cue)."""
    sounds = stream_sounds(project, stream)
    if not sounds:
        raise ProjectError(f"No sound of {ARCHIVE} plays {Path(stream).name}.")
    resource = sounds[0].name
    try:
        data = fe10_sound.add_cue(_cues(project), name, resource, _template_cue(project, resource))
    except fe10_sound.Fe10SoundError as exc:
        raise ProjectError(str(exc)) from exc
    project.write_logical("sound_data", data)
    return resource


def remove_cue(project, name: str) -> None:
    try:
        data = fe10_sound.remove_cue(_cues(project), name, _vanilla_cues(project))
    except fe10_sound.Fe10SoundError as exc:
        raise ProjectError(str(exc)) from exc
    project.write_logical("sound_data", data)


def add_track(project, track: str, brstm_bytes: bytes, template_stream: Path, channels: int) -> tuple[str, str]:
    """Write ``Sound/strm/<track>.brstm`` and register it: a stream sound ``STRM_BGM_<TRACK>``
    (copying ``template_stream``'s sound: its player, volume and 3D settings) and a cue
    ``BGM_<TRACK>``. Returns (cue, sound)."""
    if not TRACK_RE.fullmatch(track):
        raise ProjectError("A track name is lowercase letters, digits and _ (up to 40).")
    dest = _sound_dir(project) / "strm" / f"{track}.brstm"
    if dest.exists():
        raise ProjectError(f"strm/{dest.name} already exists.")
    templates = stream_sounds(project, template_stream)
    if not templates:
        raise ProjectError(f"No sound of {ARCHIVE} plays {Path(template_stream).name}.")
    sound_name, cue = f"STRM_BGM_{track.upper()}", f"BGM_{track.upper()}"
    archive_bytes = _archive(project)
    archive = brsar.read_brsar(archive_bytes)
    try:
        spec = brsar.stream_spec(archive, templates[0].index, sound_name, f"strm/{dest.name}", len(brstm_bytes),
                                 channels)
        new_archive = brsar.add_stream_sound(archive_bytes, spec)
        new_cues = fe10_sound.add_cue(_cues(project), cue, sound_name, _template_cue(project, templates[0].name))
    except (brsar.BrsarError, fe10_sound.Fe10SoundError) as exc:
        raise ProjectError(str(exc)) from exc
    project.write_keeping_original(dest, brstm_bytes)
    project.write_keeping_original(_archive_path(project), new_archive)
    project.write_logical("sound_data", new_cues)
    return cue, sound_name


def remove_track(project, stream: Path) -> list[str]:
    """Remove a track the mod added: its cues, its stream sound and its file. Returns the cues
    removed. The game's own tracks refuse."""
    if not is_added_stream(project, stream):
        raise ProjectError(f"{Path(stream).name} is one of the game's own tracks: replace its audio instead.")
    sounds = {sound.name for sound in stream_sounds(project, stream)}
    cues = [cue.name for cue in fe10_sound.read_sound_data(_cues(project))
            if cue.resource in sounds and cue.name in added_cues(project)]
    data = _cues(project)
    archive = _archive(project)
    vanilla, vanilla_cues = _vanilla_archive(project), _vanilla_cues(project)
    try:
        for cue in cues:
            data = fe10_sound.remove_cue(data, cue, vanilla_cues)
        for sound in sounds:
            archive = brsar.remove_added_sound(archive, vanilla, sound)
    except (brsar.BrsarError, fe10_sound.Fe10SoundError) as exc:
        raise ProjectError(str(exc)) from exc
    project.write_logical("sound_data", data)
    project.write_keeping_original(_archive_path(project), archive)
    stream.unlink()
    return cues
