"""Export a Tellius project's game data as text, for version control
and diffs (Disc & Patch › **Export as text…**).

One folder, rewritten on each export, in a stable order so two exports of
nearly the same project differ only where the data does:

- ``FE8Data/``: characters, classes, items, skills, chapters, terrain types,
  battle scenes, battle skies, army groups and difficulty constants (JSON,
  one record per object, file offsets left out);
- ``deployments/<map folder>/<dispos file>.json``: every section and unit,
  each field by name with its label (``PID_``, ``IID_``...) or number;
- ``shops/``: each shop section's item list per difficulty file;
- ``messages/<file>.txt``: every message as ``## ID`` then its text;
- ``scripts/<CNN>.fe9s``: every event script decompiled to the app's script
  language;
- ``sound/``: music and sound-effect cues (TSV);
- ``faces.tsv``: the face table;
- ``zdbx/``: every battle-engine DBX table, as UTF-8 text.

Radiant Dawn exports the same parts where its files have them, with its own database files:

- ``FE10Data/``: every editable database table as semantic JSON;
- ``FE10Growth/characters.json``: the per-level stat lines;
- ``deployments/``, ``shops/``: as above, from ``zmap/<folder>/dispos_<diff>.bin`` and ``Shop/``;
- ``messages/``: message bytecode in the editor's readable ``<...>`` notation;
- ``scripts/*.fe10s``: event scripts decompiled with the FE10 dialect;
- ``sound/``: the cue registry (``sound_data_en.cms``) and the BRSAR's sounds (TSV).

Export only: the binary files stay the source of truth. Each part is
optional; a part that cannot be read is listed in the returned problems
instead of stopping the export.
"""

from __future__ import annotations

import dataclasses
import enum
import json
import shutil
from pathlib import Path
from typing import Callable, Optional
from .game_profile import files_root_of, profile_of

SKIP_KEYS = {"offset", "address"}
MARKER = ".tellius_text_export"


def _plain(value):
    """``value`` as JSON-friendly data (dataclasses as dicts, bytes as text or hex)."""
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return {f.name: _plain(getattr(value, f.name)) for f in dataclasses.fields(value) if f.name not in SKIP_KEYS}
    if isinstance(value, enum.Enum):
        return value.value
    if isinstance(value, (bytes, bytearray)):
        try:
            return bytes(value).decode("ascii")
        except UnicodeDecodeError:
            return bytes(value).hex()
    if isinstance(value, dict):
        return {str(k): _plain(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain(v) for v in value]
    return value


def _write_json(path: Path, data) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(_plain(data), ensure_ascii=False, indent=1)
    path.write_text(text + "\n", encoding="utf-8", newline="\n")
    return path


def _write_text(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(text.replace("\r\n", "\n"))
    return path


def _fe8data(files: Path, out: Path) -> list[Path]:
    from .formats import fe8data

    data = (files / "FE8Data.bin").read_bytes()
    fe = fe8data.read_fe8data(data)
    written = [_write_json(out / "FE8Data" / f"{name}.json", getattr(fe, name))
               for name in ("characters", "classes", "items", "skills")]
    for name, reader in (("chapters", fe8data.read_chapter_data), ("terrain", fe8data.read_terrain_types),
                         ("battle_scenes", fe8data.read_battle_terrain), ("battle_skies", fe8data.read_battle_skies),
                         ("army_groups", fe8data.read_group_keys), ("difficulty", fe8data.read_game_data)):
        written.append(_write_json(out / "FE8Data" / f"{name}.json", reader(data)))
    return written


def _semantic_record(record) -> dict:
    """An FE10 record without binary offsets/pointers, suitable for stable diffs."""
    row = {key: value for key, value in record.values.items() if key != "block"}
    row.update(record.lists)
    if record.bonuses is not None:
        row["bonuses"] = record.bonuses
    return row


def _fe10data(project, out: Path) -> list[Path]:
    from .formats import fe10data

    database = fe10data.read_fe10data(project.read_logical("game_data"))
    return [_write_json(out / "FE10Data" / f"{kind}.json",
                        [_semantic_record(record) for record in database.table(kind)])
            for kind in fe10data.ALL_KINDS]


def _fe10growth(project, out: Path) -> list[Path]:
    from .formats import fe10growth

    records = fe10growth.read_growth(project.read_logical("growth_data"))
    rows = [{"pid": record.pid, "first": record.first, "last": record.last,
             "levels": {str(record.level_of(i)): dict(zip(fe10growth.STAT_NAMES, stats))
                        for i, stats in enumerate(record.lines)}}
            for record in records]
    return [_write_json(out / "FE10Growth" / "characters.json", rows)]


def _deployments(project, out: Path) -> list[Path]:
    from .formats import dispo, lz10, pak

    files, profile = files_root_of(project), profile_of(project)
    if "{diff}" in profile.deployment:  # one loose dispos_<diff>.bin per difficulty (Radiant Dawn)
        written = []
        for path in sorted((files / "zmap").glob("*/" + profile.deployment.format(diff="*"))):
            doc = dispo.parse_dispo(path.read_bytes())
            fields = sorted(dispo.supported_fields(doc))
            sections = [{"name": section.name,
                         "units": [{(dispo.field_name_for(f, doc.dialect) or f"field_{f}"): unit[f] for f in fields}
                                   for unit in section.units]}
                        for section in doc.sections]
            written.append(_write_json(out / "deployments" / path.parent.name / f"{path.stem}.json", sections))
        return written
    written = []
    for cmp_path in sorted((files / "zmap").glob("*/dispos.cmp")):
        raw = lz10.decompress(cmp_path.read_bytes())
        for entry in pak.read_pak_entries(raw):
            if not entry.name.startswith("dispos_"):
                continue
            sections = []
            for section in dispo.read_dispo_bytes(pak.read_pak_file_content(raw, entry)):
                units = []
                for unit in section.units:
                    units.append({(dispo.field_name(f.index) or f"field_{f.index}"):
                                  (f.label.decode("ascii", "replace") if f.label else f.value) for f in unit.fields})
                sections.append({"name": section.name, "units": units})
            written.append(_write_json(out / "deployments" / cmp_path.parent.name / f"{Path(entry.name).stem}.json",
                                       sections))
    return written


def _shops(project, out: Path) -> list[Path]:
    from .formats import shop

    profile = profile_of(project)
    written = []
    for path in sorted(profile.shop_folder(files_root_of(project)).glob(profile.shop_file.format(diff="*"))):
        doc = shop.parse_shop(path.read_bytes())
        written.append(_write_json(out / "shops" / f"{path.stem}.json",
                                   {s.name: s.items for s in doc.sections}))
    return written


def _messages(project, out: Path) -> list[Path]:
    from .formats import fe10_message, game_text, message

    files = files_root_of(project)
    fe10 = profile_of(project).message_dialect == "fe10"

    def readable(text: str) -> str:  # message.py reads bytes as cp437; show the game's own characters
        return game_text.decode(text.encode(message.ENCODING))

    written = []
    for path in sorted((files / "Mess").glob("*.m")):
        lines = []
        for m in message.read_messages_path(path):
            body = fe10_message.to_display(m.text) if fe10 else readable(m.text)
            lines.append(f"## {readable(m.speaker)}\n{body}\n")
        written.append(_write_text(out / "messages" / f"{path.stem}.txt", "\n".join(lines)))
    return written


def _scripts(project, out: Path) -> list[Path]:
    from .formats.cmb import decompile, read_cmb_path

    files = files_root_of(project)
    extension = f".{profile_of(project).script_dialect}s"
    written = []
    for path in sorted((files / "Scripts").glob("*.cmb")):
        source = decompile(read_cmb_path(path))
        source = source[0] if isinstance(source, tuple) else source
        written.append(_write_text(out / "scripts" / f"{path.stem}{extension}", source))
    return written


def _sound(project, out: Path) -> list[Path]:
    from .formats import gcfesnd

    if "sound_data" in profile_of(project).files:
        return _fe10_sound(project, out)
    data = (files_root_of(project) / "Sound" / "gcfesnd.bin").read_bytes()
    bgm = ["name\tpath\tvolume"] + [f"{c.name}\t{c.path}\t{(c.control_word >> 8) & 0xFF}"
                                    for c in gcfesnd.read_bgm_cues(data)]
    sfx = ["name\tsound_id\tvolume\tpan\tflags\trange"] + [
        f"{c.name}\t{c.sound_id}\t{c.volume}\t{c.pan}\t{c.flags}\t{c.range_value}" for c in gcfesnd.read_sfx_cues(data)]
    return [_write_text(out / "sound" / "bgm_cues.tsv", "\n".join(bgm) + "\n"),
            _write_text(out / "sound" / "sfx_cues.tsv", "\n".join(sfx) + "\n")]


def _fe10_sound(project, out: Path) -> list[Path]:
    """Radiant Dawn: the cue registry's cues (name, BRSAR sound, the seven undecoded words) and the
    BRSAR's own sounds."""
    from .formats import brsar, fe10_sound

    cues = fe10_sound.read_sound_data(project.read_logical("sound_data"))
    head = "\t".join(["name", "resource", *(f"word_{i}" for i in range(2, 9))])

    def table(chosen) -> str:
        rows = [head] + ["\t".join([c.name, c.resource, *(f"{w:#x}" for w in c.raw_words)]) for c in chosen]
        return "\n".join(rows) + "\n"

    archive = brsar.read_brsar(project.read_logical("sound_archive"))
    sounds = ["\t".join(("name", "type", "volume", "priority", "file", "bank", "external_path"))] + [
        "\t".join(str(v) for v in (s.name, s.sound_type, s.volume, s.player_priority, s.file_index,
                                   "" if s.bank_index is None else s.bank_index, s.external_path or ""))
        for s in archive.sounds]
    return [_write_text(out / "sound" / "bgm_cues.tsv", table(c for c in cues if c.family == "BGM")),
            _write_text(out / "sound" / "sfx_cues.tsv", table(c for c in cues if c.family != "BGM")),
            _write_text(out / "sound" / "brsar_sounds.tsv", "\n".join(sounds) + "\n")]


def _faces(files: Path, out: Path) -> list[Path]:
    from .formats.fe9_portraits import read_face_table

    rows = ["fid\tname_key\tfile\tleft_eye\tright_eye\tmouth\tparts\tmenu_face\tauto_mouth\tdepth\tmenu_offset"]
    for r in read_face_table((files / "Face" / "facedata.bin").read_bytes()).values():
        rows.append("\t".join(str(v) for v in (r.fid, r.name_id, r.filename, r.left_eye, r.right_eye, r.mouth,
                                                r.flags, r.mini_portrait, r.default_mouth, r.depth, r.menu_offset)))
    return [_write_text(out / "faces.tsv", "\n".join(rows) + "\n")]


def _zdbx(project, out: Path) -> list[Path]:
    from . import battle_tables

    written = []
    for name, state in sorted(battle_tables.inventory(project).items()):
        if state == "deleted":
            continue
        written.append(_write_text(out / "zdbx" / name, battle_tables.read_entry(project, name)))
    return written


PART_LABELS: dict[str, str] = {
    "FE8Data": "Characters, classes, items, skills, chapters and the other FE8Data tables",
    "FE10Data": "Characters, classes, items, skills and the other FE10Data tables",
    "FE10Growth": "Character level-stat tables",
    "deployments": "Deployments of every chapter map",
    "shops": "Shops",
    "messages": "Messages",
    "scripts": "Event scripts (decompiled)",
    "sound": "Music and sound-effect cues",
    "faces": "Face table",
    "zdbx": "Battle-engine DBX tables",
}


def parts_for(project) -> tuple[tuple[str, str], ...]:
    """The semantic exports implemented for the project's game, as ``(name, label)``."""
    return tuple((name, PART_LABELS[name]) for name in profile_of(project).text_export_parts)


def export_project(project, dest: Path, parts: Optional[set[str]] = None,
                   progress: Optional[Callable[[str], None]] = None) -> tuple[list[Path], list[str]]:
    """Write the text export to ``dest`` (the parts' folders are replaced) and
    return ``(written files, problems)``."""
    files = files_root_of(project)
    dest = Path(dest)
    marker = dest / MARKER
    if dest.is_dir() and any(dest.iterdir()) and not marker.is_file():
        raise ValueError(f"{dest} is not empty and holds no earlier text export ({MARKER}); "
                         "choose an empty folder or a previous export's folder.")
    dest.mkdir(parents=True, exist_ok=True)
    marker.write_text("Written by Tellius Modding's Export as text; its folders are replaced on each export.\n",
                      encoding="utf-8", newline="\n")
    runners = {
        "FE8Data": lambda: _fe8data(files, dest), "deployments": lambda: _deployments(project, dest),
        "FE10Data": lambda: _fe10data(project, dest), "FE10Growth": lambda: _fe10growth(project, dest),
        "shops": lambda: _shops(project, dest), "messages": lambda: _messages(project, dest),
        "scripts": lambda: _scripts(project, dest), "sound": lambda: _sound(project, dest),
        "faces": lambda: _faces(files, dest), "zdbx": lambda: _zdbx(project, dest),
    }
    written, problems = [], []
    for name, label in parts_for(project):
        if parts is not None and name not in parts:
            continue
        if progress is not None:
            progress(label)
        target = dest / ("faces.tsv" if name == "faces" else name)
        if target.is_dir():
            shutil.rmtree(target)
        try:
            written += runners[name]()
        except FileNotFoundError as exc:
            problems.append(f"{label}: missing {Path(exc.filename).name if exc.filename else exc}")
        except Exception as exc:  # noqa: BLE001 - one unreadable part must not stop the rest
            problems.append(f"{label}: {exc}")
    return written, problems
