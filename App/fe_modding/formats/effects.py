"""Visual effects: ``FE8Effect.bin`` (the ``EID_`` registry) joined with ``yme/EID_*.cmp``.

An effect is an LZ10-compressed ``pack`` archive holding ``<name>.g`` (skeleton),
``.gs`` (meshes), ``.ga`` (animation) and, for all but two of the vanilla packs,
``.tpl`` (texture). The registry maps an ``EID_`` name to a flags word and an
optional chain pointer; the pack is found by name. The vanilla disc has 295
registry records and 324 packs, so 29 packs are unregistered ("orphans").

Pure bytes-in/bytes-out helpers; the GUI does the file writes.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from . import effect_registry, lz10, pak

REGISTRY_FILE = "FE8Effect.bin"
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

    @property
    def category(self) -> int:
        return (self.flags >> 24) & 0xFF


def registry_path(files_dir: Path) -> Path:
    return Path(files_dir) / REGISTRY_FILE


def pack_path(files_dir: Path, name: str) -> Path:
    return Path(files_dir) / PACK_DIR / f"{name}.cmp"


def list_effects(files_dir: Path) -> list[EffectEntry]:
    """Every registered effect plus every pack with no registry record, by name."""
    files_dir = Path(files_dir)
    reg = registry_path(files_dir)
    records = effect_registry.read_effect_registry(reg.read_bytes()) if reg.exists() else []
    packs = {p.stem for p in (files_dir / PACK_DIR).glob("EID_*.cmp")}
    out = [
        EffectEntry(r.eid_name, True, r.eid_name in packs, r.flags, r.next_in_chain)
        for r in records
    ]
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
    registry: bytes, name: str, *, flags: int, next_in_chain: Optional[str] = None
) -> bytes:
    """Append an ``EID_`` record to a registry file's bytes."""
    if not NAME_RE.match(name):
        raise EffectError("Effect names look like EID_SOMETHING (letters, digits, underscore).")
    records = effect_registry.read_effect_registry(registry)
    if any(r.eid_name == name for r in records):
        raise EffectError(f"{name} is already in the registry.")
    if next_in_chain and all(r.eid_name != next_in_chain for r in records):
        raise EffectError(f"Chain target {next_in_chain} is not in the registry.")
    records.append(effect_registry.make_record(name, flags, next_in_chain))
    return effect_registry.build_effect_registry(records)
