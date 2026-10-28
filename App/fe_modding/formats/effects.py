"""Visual effects: the game's ``EID_`` registry joined with ``yme/EID_*.cmp``.

An effect is an LZ10-compressed ``pack`` archive holding ``<name>.g`` (skeleton),
``.gs`` (meshes), ``.ga`` (animation) and, for all but two of the vanilla packs,
``.tpl`` (texture). The registry maps an ``EID_`` name to a flags word and an
optional chain pointer; the pack is found by name. The vanilla disc has 295
registry records and 324 packs, so 29 packs are unregistered ("orphans").

Radiant Dawn uses ``FE10Effect.cms`` and a larger 24-byte registry record with
two child-effect indices and a numeric-ID alias table. Pure bytes-in/bytes-out
helpers; the GUI does the supported file writes.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from . import effect_registry, fe10_effect_registry, lz10, pak
from ..game_files import as_path
from ..games import Game

REGISTRY_FILES = {
    Game.PATH_OF_RADIANCE: "FE8Effect.bin",
    Game.RADIANT_DAWN: "FE10Effect.cms",
}
REGISTRY_FILE = REGISTRY_FILES[Game.PATH_OF_RADIANCE]
PACK_DIR = "yme"
PART_EXTENSIONS = ("g", "gs", "ga", "tpl")
NAME_RE = re.compile(r"^EID_[A-Za-z0-9_]{1,40}$")


class EffectError(Exception):
    pass


@dataclass(frozen=True)
class EffectEntry:
    name: str
    registered: bool
    has_pack: bool
    flags: int = 0
    next_in_chain: Optional[str] = None
    description: str = ""
    sound_group: Optional[str] = None
    parameter_bytes: tuple[int, int, int, int] = (0, 0, 0, 0)
    child_effects: tuple[str, ...] = ()
    numeric_ids: tuple[int, ...] = ()

    @property
    def category(self) -> int:
        return (self.flags >> 24) & 0xFF


def registry_path(files_root: Path, game: Game = Game.PATH_OF_RADIANCE) -> Path:
    return as_path(files_root) / REGISTRY_FILES[game]


def pack_path(files_root: Path, name: str) -> Path:
    return as_path(files_root) / PACK_DIR / f"{name}.cmp"


def list_effects(files_root: Path, game: Game = Game.PATH_OF_RADIANCE) -> list[EffectEntry]:
    """Every registered effect plus every pack with no registry record, by name."""
    files_root = as_path(files_root)
    reg = registry_path(files_root, game)
    if game is Game.RADIANT_DAWN and reg.exists():
        rd_registry = fe10_effect_registry.read_fe10_effect_registry(lz10.decompress(reg.read_bytes()))
        records = rd_registry.records
    else:
        records = effect_registry.read_effect_registry(reg.read_bytes()) if reg.exists() else []
    packs = {p.stem for p in (files_root / PACK_DIR).glob("EID_*.cmp")}
    if game is Game.RADIANT_DAWN:
        out = [EffectEntry(
            r.eid_name, True, r.eid_name in packs, r.flags, None,
            r.description, r.sound_group, r.parameter_bytes,
            rd_registry.child_eids(r), rd_registry.numeric_ids(r.eid_name),
        ) for r in records]
    else:
        out = [EffectEntry(r.eid_name, True, r.eid_name in packs, r.flags, r.next_in_chain)
               for r in records]
    known = {r.eid_name for r in records}
    out += [EffectEntry(n, False, True) for n in sorted(packs - known)]
    return sorted(out, key=lambda e: e.name)


def read_effect_pack(data: bytes) -> dict[str, bytes]:
    """Decompress a ``.cmp`` effect pack into {file name: bytes}, in archive order."""
    try:
        raw = lz10.decompress(data)
        entries = pak.read_pak_entries(raw)
    except (lz10.LZ10Error, pak.PakError, ValueError, IndexError) as exc:
        raise EffectError(f"Not an effect pack: {exc}") from exc
    return {e.name: pak.read_pak_file_content(raw, e) for e in entries}


def build_effect_pack(parts: dict[str, bytes]) -> bytes:
    return lz10.compress(pak.pack_pak(list(parts.items())))


def validate_pack(parts: dict[str, bytes]) -> str:
    """Return the effect's base name, raising EffectError if the pack is not a usable effect."""
    bases = {n.rsplit(".", 1)[0] for n in parts}
    exts = {n.rsplit(".", 1)[-1] for n in parts}
    if len(bases) != 1:
        raise EffectError("Pack entries do not share one base name.")
    missing = {"g", "gs", "ga"} - exts
    if missing:
        raise EffectError("Pack is missing: " + ", ".join(sorted(missing)))
    return bases.pop()


def rename_pack(parts: dict[str, bytes], new_name: str) -> dict[str, bytes]:
    """Re-key every entry to ``new_name.<ext>`` (used when cloning under a new EID)."""
    if not NAME_RE.match(new_name):
        raise EffectError("Effect names look like EID_SOMETHING (letters, digits, underscore).")
    return {f"{new_name}.{n.rsplit('.', 1)[-1]}": b for n, b in parts.items()}


def replace_part(parts: dict[str, bytes], ext: str, data: bytes) -> dict[str, bytes]:
    """Swap one part (by extension) keeping archive order; adds it at the end if absent."""
    out, done = {}, False
    for n, b in parts.items():
        if n.rsplit(".", 1)[-1] == ext:
            out[n], done = data, True
        else:
            out[n] = b
    if not done:
        base = next(iter(parts)).rsplit(".", 1)[0]
        out[f"{base}.{ext}"] = data
    return out


def add_registry_record(
    registry: bytes, name: str, *, flags: int, next_in_chain: Optional[str] = None,
    game: Game = Game.PATH_OF_RADIANCE, template_name: str | None = None,
) -> bytes:
    """Append an ``EID_`` record to a registry file's bytes."""
    if not NAME_RE.match(name):
        raise EffectError("Effect names look like EID_SOMETHING (letters, digits, underscore).")
    if game is Game.RADIANT_DAWN:
        raw = lz10.decompress(registry)
        document = fe10_effect_registry.read_fe10_effect_registry(raw)
        if any(record.eid_name == name for record in document.records):
            raise EffectError(f"{name} is already in the registry.")
        if template_name is None:
            template_name = document.records[0].eid_name if document.records else None
        try:
            template = next(i for i, record in enumerate(document.records)
                            if record.eid_name == template_name)
        except StopIteration as exc:
            raise EffectError(f"Template effect {template_name} is not in the registry.") from exc
        try:
            built = fe10_effect_registry.clone_effect_record(raw, template, name, name)
            index = len(document.records)
            built = fe10_effect_registry.update_effect_record(built, index, flags=flags)
        except (ValueError, IndexError) as exc:
            raise EffectError(str(exc)) from exc
        return lz10.compress(built)

    records = effect_registry.read_effect_registry(registry)
    if any(r.eid_name == name for r in records):
        raise EffectError(f"{name} is already in the registry.")
    if next_in_chain and all(r.eid_name != next_in_chain for r in records):
        raise EffectError(f"Chain target {next_in_chain} is not in the registry.")
    records.append(effect_registry.make_record(name, flags, next_in_chain))
    return effect_registry.build_effect_registry(records)


def registry_flags(registry: bytes, name: str, game: Game = Game.PATH_OF_RADIANCE) -> int:
    """Flags of one registry row, or zero when it is absent."""
    if game is Game.RADIANT_DAWN:
        records = fe10_effect_registry.read_fe10_effect_registry(lz10.decompress(registry)).records
    else:
        records = effect_registry.read_effect_registry(registry)
    return next((record.flags for record in records if record.eid_name == name), 0)


def registry_names(registry: bytes, game: Game = Game.PATH_OF_RADIANCE) -> set[str]:
    """Stable EID names in registry file bytes (compressed for RD)."""
    if game is Game.RADIANT_DAWN:
        records = fe10_effect_registry.read_fe10_effect_registry(lz10.decompress(registry)).records
    else:
        records = effect_registry.read_effect_registry(registry)
    return {record.eid_name for record in records}


def update_rd_registry_record(
    registry: bytes,
    name: str,
    *,
    description: str,
    flags: int,
    parameter_bytes: tuple[int, int, int, int],
    child_effects: tuple[str | None, str | None],
    sound_group: str | None,
    numeric_ids: tuple[int, ...],
) -> bytes:
    """Edit one RD row by stable EID names and return compressed CMS bytes."""
    raw = lz10.decompress(registry)
    document = fe10_effect_registry.read_fe10_effect_registry(raw)
    by_name = {record.eid_name: index for index, record in enumerate(document.records)}
    if name not in by_name:
        raise EffectError(f"{name} is not in the registry.")
    try:
        children = tuple(None if child is None else by_name[child] for child in child_effects)
    except KeyError as exc:
        raise EffectError(f"Unknown child effect {exc.args[0]}.") from exc
    try:
        raw = fe10_effect_registry.update_effect_record(
            raw, by_name[name], description=description, flags=flags,
            parameter_bytes=parameter_bytes, child_effect_indices=children,
            sound_group=sound_group,
        )
        raw = fe10_effect_registry.set_numeric_aliases(raw, name, numeric_ids)
    except (ValueError, IndexError) as exc:
        raise EffectError(str(exc)) from exc
    return lz10.compress(raw)


def remove_rd_registry_record(registry: bytes, name: str) -> bytes:
    """Remove one RD registry row, refusing live child references."""
    raw = lz10.decompress(registry)
    document = fe10_effect_registry.read_fe10_effect_registry(raw)
    index = next((i for i, record in enumerate(document.records)
                  if record.eid_name == name), None)
    if index is None:
        raise EffectError(f"{name} is not in the registry.")
    try:
        return lz10.compress(fe10_effect_registry.remove_effect_record(raw, index))
    except (ValueError, IndexError) as exc:
        raise EffectError(str(exc)) from exc
