"""Radiant Dawn music and sound effects: adding and removing tracks, cues and sound effects.

A sound effect is an ``SFX_*`` cue naming a wave sound of the archive; a new one gets its own
one-entry RWSD (``rwsd.single_entry_rwsd``) loaded with the template sound's groups.

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
from .game_profile import files_root_of, profile_of

ARCHIVE = "Sound/sound_us.brsar"   # the US and European name; the Japanese disc has Sound/sound.brsar
TRACK_RE = re.compile(r"[a-z0-9_]{1,40}")


def _sound_dir(project) -> Path:
    return files_root_of(project) / "Sound"


def _archive_path(project) -> Path:
    """The disc's sound archive: ``sound_us.brsar``, or ``sound.brsar`` on the Japanese disc."""
    return profile_of(project).path(files_root_of(project), "sound_archive")


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
        raise ProjectError(f"No sound of {_archive_path(project).name} plays {Path(stream).name}.")
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
        raise ProjectError(f"No sound of {_archive_path(project).name} plays {Path(template_stream).name}.")
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


def wave_template(project, cue: str | None) -> str:
    """The SFX cue a new sound effect copies: ``cue`` when it plays an embedded wave sound, else
    ``SFX_SYS_SELECT1`` (the menu select sound, in the always-loaded GROUP_STATIC)."""
    cues = fe10_sound.cue_map(_cues(project))
    sounds = {sound.name: sound for sound in brsar.read_brsar(_archive(project)).sounds}
    if cue in cues and getattr(sounds.get(cues[cue].resource), "sound_type", None) == 3:
        return cue
    return "SFX_SYS_SELECT1"


def add_sfx(project, cue: str, sample_rate: int, channels, template_cue: str) -> str:
    """A new sound effect ``cue`` (``SFX_...``) playing ``channels`` (lists of 16-bit samples): its
    own one-entry RWSD and wave sound ``SE_<NAME>``, copying ``template_cue``'s wave sound (its
    player, priorities and load groups). The audio is mixed to the template wave's channel count.
    Returns the new wave sound's name."""
    from .formats import rwsd

    if not cue.startswith("SFX_") or not cue[4:] or not cue.replace("_", "").isalnum() or not cue.isascii():
        raise ProjectError("A sound effect name is SFX_ followed by capitals, digits and _.")
    cues = fe10_sound.cue_map(_cues(project))
    if template_cue not in cues:
        raise ProjectError(f"No sound effect {template_cue}.")
    archive_bytes = _archive(project)
    archive = brsar.read_brsar(archive_bytes)
    template = next((sound for sound in archive.sounds if sound.name == cues[template_cue].resource), None)
    if template is None or template.sound_type != 3:
        raise ProjectError(f"{template_cue} is not an embedded wave sound.")
    name = "SE_" + cue[4:]
    source = archive.files[template.file_index]
    try:
        document = rwsd.read_rwsd(source.header, source.wave_data)
        one = rwsd.read_rwsd(*rwsd.single_entry_rwsd(document, template.info_index))
        wanted = len(one.waves[0].channels)
        mixed = [list(channel) for channel in channels]
        if len(mixed) > wanted:
            mixed = [[int(sum(values) / len(values)) for values in zip(*mixed)]]
        while len(mixed) < wanted:
            mixed.append(list(mixed[0]))
        header, wave = rwsd.replace_wave(one, 0, rwsd.RwsdAudio(sample_rate, tuple(tuple(c) for c in mixed)))
        new_archive = brsar.add_wave_sound(archive_bytes, brsar.wave_spec(archive, template.index, name, header, wave))
        new_cues = fe10_sound.add_cue(_cues(project), cue, name, template_cue)
    except (brsar.BrsarError, rwsd.RwsdError, fe10_sound.Fe10SoundError) as exc:
        raise ProjectError(str(exc)) from exc
    project.write_keeping_original(_archive_path(project), new_archive)
    project.write_logical("sound_data", new_cues)
    return name


def remove_sfx(project, cue: str) -> None:
    """Remove a sound effect the mod added: its cue, and its wave sound when no other cue plays it."""
    cues = fe10_sound.cue_map(_cues(project))
    if cue not in added_cues(project):
        raise ProjectError(f"{cue} is one of the game's own sound effects: replace its audio instead.")
    resource = cues[cue].resource
    data = _cues(project)
    archive = _archive(project)
    try:
        data = fe10_sound.remove_cue(data, cue, _vanilla_cues(project))
        added = {sound.name for sound in brsar.read_brsar(archive).sounds} - \
            {sound.name for sound in brsar.read_brsar(_vanilla_archive(project)).sounds}
        if resource in added and not any(other.resource == resource for name, other in cues.items() if name != cue):
            archive = brsar.remove_added_sound(archive, _vanilla_archive(project), resource)
    except (brsar.BrsarError, fe10_sound.Fe10SoundError) as exc:
        raise ProjectError(str(exc)) from exc
    project.write_logical("sound_data", data)
    project.write_keeping_original(_archive_path(project), archive)


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
