"""Mod patches: distribute a mod without distributing the game.

A patch (``.tpatch``) is a zip archive holding only what a mod changes
relative to the retail disc, plus a ``manifest.json``:

- ``files/<path>``: every file of the extracted disc tree the mod replaced
  or added, stored whole at its path relative to ``extracted/`` (so
  ``files/sys/main.dol``, ``files/files/FE8Data.bin``...).
- the manifest lists them with their SHA-1 (``replace`` also carries the
  SHA-1 of the retail file it replaces), the retail files the mod removed
  (``remove``), the game, and the base disc's ID and revision.

Applying one extracts the base disc, checks it is the disc the patch was
made from (same disc ID, and every file the patch replaces or removes
matches the retail hash), writes the patch's files over the tree and packs
it in the game's build format - the same path as building a project.

A file-level patch rather than a byte-level one (xdelta, BPS...) because
building re-lays out the disc: one resized file moves every file after it,
so a byte diff of two images is mostly noise, while the changed files are
exactly what the mod is.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import sys
import tempfile
import zipfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Optional

from . import tools
from .exceptions import ModdingError
from .games import Game, get_game_info, profile as game_profile
from .project import ModProject, build_image

PATCH_EXTENSION = ".tpatch"
FORMAT_VERSION = 1
MANIFEST_NAME = "manifest.json"
FILES_PREFIX = "files/"
_CHUNK = 1 << 20


class PatchError(ModdingError):
    """Raised for an unreadable patch, or one that does not fit the base disc."""


@dataclass
class PatchSummary:
    replaced: list[str] = field(default_factory=list)
    added: list[str] = field(default_factory=list)
    removed: list[str] = field(default_factory=list)
    size: int = 0  # bytes of the patch file

    @property
    def empty(self) -> bool:
        return not (self.replaced or self.added or self.removed)

    def describe(self) -> str:
        return (f"{len(self.replaced)} replaced, {len(self.added)} added, {len(self.removed)} removed "
                f"({self.size / (1 << 20):.1f} MiB)")


@dataclass
class PatchInfo:
    """A patch's manifest."""
    game: Game
    name: str
    description: str
    disc_id: str
    created_at: str
    replace: dict[str, dict]
    add: dict[str, dict]
    remove: dict[str, dict]
    author: str = ""
    version: str = ""
    credits: str = ""

    @property
    def title(self) -> str:
        """``Name 1.2 by Author``, whichever parts the patch has."""
        text = " ".join(part for part in (self.name, self.version) if part)
        return f"{text} by {self.author}" if text and self.author else text or (f"by {self.author}" if self.author else "")


# -- trees -----------------------------------------------------------------------------------------
def _sha1(path: Path) -> str:
    digest = hashlib.sha1()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(_CHUNK), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _same_file(a: Path, b: Path) -> bool:
    if a.stat().st_size != b.stat().st_size:
        return False
    with a.open("rb") as fa, b.open("rb") as fb:
        while True:
            chunk_a, chunk_b = fa.read(_CHUNK), fb.read(_CHUNK)
            if chunk_a != chunk_b:
                return False
            if not chunk_a:
                return True


def _tree(root: Path) -> dict[str, Path]:
    """Every file under ``root`` by its relative POSIX path."""
    return {p.relative_to(root).as_posix(): p for p in root.rglob("*") if p.is_file()}


def disc_id(extracted_dir: Path | str) -> str:
    """``GFEE01 rev 0``-style identity of an extracted disc, from sys/boot.bin
    (game code + maker code at 0x0, disc revision at 0x7)."""
    boot = Path(extracted_dir) / "sys" / "boot.bin"
    if not boot.is_file():
        return ""
    header = boot.read_bytes()[:8]
    if len(header) < 8:
        return ""
    return f"{header[:6].decode('ascii', 'replace')} rev {header[7]}"


def _safe_relative(name: str) -> str:
    """Reject absolute paths and ``..`` in a patch entry (zip slip)."""
    path = PurePosixPath(name)
    if not name or path.is_absolute() or ".." in path.parts or ":" in name or "\\" in name:
        raise PatchError(f"Invalid path in patch: {name!r}")
    return path.as_posix()


# -- creating --------------------------------------------------------------------------------------
def create_patch(base_dir: Path | str, mod_dir: Path | str, dest: Path | str, *, game: Game,
                 name: str = "", description: str = "", author: str = "", version: str = "",
                 credits: str = "") -> PatchSummary:
    """Write a patch turning the extracted tree ``base_dir`` into ``mod_dir``. ``author``,
    ``version`` and ``credits`` are shown to whoever applies it."""
    base_dir, mod_dir, dest = Path(base_dir), Path(mod_dir), Path(dest)
    base, mod = _tree(base_dir), _tree(mod_dir)
    summary = PatchSummary()
    manifest = {
        "format": "tellius-patch",
        "version": FORMAT_VERSION,
        "game": game.value,
        "name": name,
        "description": description,
        "author": author,
        "mod_version": version,  # "version" is the patch format's own
        "credits": credits,
        "disc_id": disc_id(base_dir),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "replace": {}, "add": {}, "remove": {},
    }
    dest.parent.mkdir(parents=True, exist_ok=True)
    partial = dest.with_name(dest.name + ".part")
    try:
        with zipfile.ZipFile(partial, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
            for rel in sorted(mod):
                path = mod[rel]
                if rel in base:
                    if _same_file(base[rel], path):
                        continue
                    manifest["replace"][rel] = {"sha1": _sha1(path), "base_sha1": _sha1(base[rel])}
                    summary.replaced.append(rel)
                else:
                    manifest["add"][rel] = {"sha1": _sha1(path)}
                    summary.added.append(rel)
                archive.write(path, FILES_PREFIX + rel)
            for rel in sorted(set(base) - set(mod)):
                manifest["remove"][rel] = {"base_sha1": _sha1(base[rel])}
                summary.removed.append(rel)
            archive.writestr(MANIFEST_NAME, json.dumps(manifest, indent=2))
        partial.replace(dest)
    finally:
        partial.unlink(missing_ok=True)
    summary.size = dest.stat().st_size
    return summary


def create_project_patch(project: ModProject, dest: Path | str) -> PatchSummary:
    """Patch from the project's source disc to its current extracted files.

    Extracts the source disc again into a temporary folder beside the project
    (the retail files an editor overwrote are not kept anywhere else)."""
    if project.source_path is None or not project.source_path.is_file():
        raise PatchError("The project's source disc image is missing - choose it again first.")
    if not project.has_extracted_files:
        raise PatchError("Nothing extracted yet - extract the source disc image first.")
    project.sync_system_archive()  # as a build would: system.cmp carries copies of loose files (none on Radiant Dawn)
    with tempfile.TemporaryDirectory(prefix=".patch_base_", dir=project.directory) as temp:
        base = Path(temp) / "disc"
        tools.extract_disc(project.source_path, base, overwrite=True, wii=project.profile.wii)
        return create_patch(base, project.extracted_dir, dest, game=project.game,
                            name=project.name, description=project.description, author=project.author,
                            version=project.version, credits=project.credits)


# -- reading and applying --------------------------------------------------------------------------
def read_patch(path: Path | str) -> PatchInfo:
    try:
        with zipfile.ZipFile(path) as archive:
            manifest = json.loads(archive.read(MANIFEST_NAME).decode("utf-8"))
    except (OSError, KeyError, zipfile.BadZipFile, json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise PatchError(f"Not a readable Tellius patch: {path}\n{exc}") from exc
    if manifest.get("format") != "tellius-patch":
        raise PatchError(f"Not a Tellius patch: {path}")
    if manifest.get("version", 0) > FORMAT_VERSION:
        raise PatchError("This patch was made by a newer version of the app.")
    try:
        game = Game(manifest["game"])
    except (KeyError, ValueError) as exc:
        raise PatchError("The patch names no game this app supports.") from exc
    return PatchInfo(game=game, name=manifest.get("name", ""), description=manifest.get("description", ""),
                     disc_id=manifest.get("disc_id", ""), created_at=manifest.get("created_at", ""),
                     replace=manifest.get("replace", {}), add=manifest.get("add", {}),
                     remove=manifest.get("remove", {}), author=manifest.get("author", ""),
                     version=manifest.get("mod_version", ""), credits=manifest.get("credits", ""))


def apply_patch(patch_path: Path | str, target_dir: Path | str) -> PatchInfo:
    """Apply a patch onto an extracted retail tree, in place.

    The base is checked before the first file is written, so a patch that
    doesn't fit the tree leaves it untouched."""
    info = read_patch(patch_path)
    target_dir = Path(target_dir)
    found = disc_id(target_dir)
    if info.disc_id and found != info.disc_id:
        raise PatchError(f"This patch is for disc {info.disc_id}, but the base disc is {found or 'unknown'}.")
    for rel in (*info.replace, *info.add, *info.remove):
        _safe_relative(rel)
    mismatched = []
    for rel, entry in (*info.replace.items(), *info.remove.items()):
        path = target_dir / _safe_relative(rel)
        if not path.is_file() or _sha1(path) != entry.get("base_sha1"):
            mismatched.append(rel)
    if mismatched:
        listed = "\n  ".join(mismatched[:10]) + ("\n  â€¦" if len(mismatched) > 10 else "")
        raise PatchError("The base disc doesn't match the one the patch was made from "
                         f"(a different version, or an already modified disc). Differing files:\n  {listed}")
    with zipfile.ZipFile(patch_path) as archive:
        for rel, entry in (*info.replace.items(), *info.add.items()):
            path = target_dir / _safe_relative(rel)
            path.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(FILES_PREFIX + rel) as src, path.open("wb") as out:
                shutil.copyfileobj(src, out, _CHUNK)
            if _sha1(path) != entry.get("sha1"):
                raise PatchError(f"The patch is damaged: {rel} does not match its checksum.")
    for rel in info.remove:
        (target_dir / _safe_relative(rel)).unlink()
    return info


def apply_patch_to_disc(patch_path: Path | str, base_disc: Path | str, dest: Path | str) -> Optional[str]:
    """Build a patched disc image at ``dest`` from a retail disc image.

    Returns the build warning, if any (see :func:`project.build_image`)."""
    info = read_patch(patch_path)
    base_disc, dest = Path(base_disc), Path(dest)
    allowed = get_game_info(info.game).disc_formats
    if base_disc.suffix.lower() not in allowed:
        raise PatchError(f"'{base_disc.suffix}' is not a disc image format the bundled tool can read. "
                         f"Supported: {', '.join(allowed)}.")
    dest.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".patch_apply_", dir=dest.parent) as temp:
        tree = Path(temp) / "disc"
        tools.extract_disc(base_disc, tree, overwrite=True, wii=game_profile(info.game).wii)
        apply_patch(patch_path, tree)
        return build_image(info.game, tree, dest, overwrite=True)


def main(argv: Optional[list[str]] = None) -> int:
    """``python -m fe_modding.patch apply PATCH BASE_DISC OUTPUT``"""
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) != 4 or argv[0] != "apply":
        print("usage: python -m fe_modding.patch apply PATCH BASE_DISC OUTPUT", file=sys.stderr)
        return 2
    try:
        warning = apply_patch_to_disc(argv[1], argv[2], argv[3])
    except ModdingError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    if warning:
        print(f"warning: {warning}", file=sys.stderr)
    print(f"Built {argv[3]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
