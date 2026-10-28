"""Read-only vanilla copies of each disc, shared by every project made from it.

A store is one extracted disc (``sys/``, ``files/`` and, for Wii, ``disc/`` plus the partition's
``ticket.bin``/``tmd.bin``/``cert.bin``) and a ``vanilla.json`` describing it: disc ID, revision and
each file's size, modification time and SHA-1. An app-made store is ``<store root>/<key>/disc/``
with the description beside it in ``<store root>/<key>/vanilla.json``; an adopted folder's
description is kept at the same place, so the disc tree holds the disc's files only. Projects in the input/output layout read their
unchanged files from it (:class:`~fe_modding.game_files.OverlayFiles`).

Two kinds:

- extracted by the app from a disc image into ``<store root>/<key>/``; its files are marked
  read-only, so a stray write fails instead of changing the vanilla file for every project;
- a folder the user already extracted (Dolphin's "Extract Entire Disc", WIT...), registered where
  it is. Its files are marked read-only too (and made writable again when it is forgotten);
  nothing else in it changes.

The key is ``<disc id>-<revision>-<first 8 hex digits of the SHA-1 of sys/fst.bin>``, so two dumps of
the same disc share a store and another revision never does.
"""

from __future__ import annotations

import json
import os
import shutil
import stat
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

from . import config, tools
from .exceptions import ProjectError
from .game_files import _walk_files, sha1_of, write_atomic

SETTING_KEY = "vanilla_store_root"
MANIFEST = "vanilla.json"
REGISTRY = "stores.json"
FORMAT_VERSION = 1

GAMECUBE_REQUIRED = ("sys/boot.bin", "sys/bi2.bin", "sys/apploader.img", "sys/main.dol", "sys/fst.bin")
WII_REQUIRED = ("disc", "ticket.bin", "tmd.bin", "cert.bin")


def store_root() -> Path:
    """Where the app keeps its stores and the registry (a setting; default in the app folder)."""
    configured = config.load_setting(SETTING_KEY)
    return Path(configured) if configured else config.APP_DIR / "vanilla"


@dataclass(frozen=True)
class VanillaStore:
    key: str
    root: Path          # the folder holding sys/ and files/
    disc_id: str
    revision: int
    adopted: bool       # a user's folder, registered in place
    source_image: Optional[str] = None

    @property
    def manifest_path(self) -> Path:
        return store_root() / self.key / MANIFEST

    def manifest(self) -> dict:
        try:
            return json.loads(self.manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ProjectError(f"The vanilla files' description {self.manifest_path} could not be read: {exc}") from exc

    def file_hashes(self) -> dict[str, str]:
        return {rel: entry["sha1"] for rel, entry in self.manifest()["files"].items()}

    def size_on_disk(self) -> int:
        return sum(entry["size"] for entry in self.manifest()["files"].values())

    def verify(self, *, full: bool = False) -> list[str]:
        """Files that differ from the description: missing, another size or modification time
        (quick) or, with ``full``, another SHA-1. Empty when the store is intact."""
        problems = []
        for rel, entry in self.manifest()["files"].items():
            path = self.root / rel
            try:
                info = path.stat()
            except OSError:
                problems.append(f"{rel}: missing")
                continue
            if info.st_size != entry["size"]:
                problems.append(f"{rel}: size changed")
            elif full and sha1_of(path) != entry["sha1"]:
                problems.append(f"{rel}: contents changed")
            elif not full and info.st_mtime_ns != entry["mtime_ns"]:
                problems.append(f"{rel}: modified")
        return problems

    def to_dict(self) -> dict:
        return {"root": str(self.root), "disc_id": self.disc_id, "revision": self.revision,
                "adopted": self.adopted, "source_image": self.source_image}


# -- the registry ----------------------------------------------------------------------------------


def _registry_path() -> Path:
    return store_root() / REGISTRY


def _read_registry() -> dict:
    try:
        data = json.loads(_registry_path().read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def _write_registry(data: dict) -> None:
    write_atomic(_registry_path(), (json.dumps(data, indent=2, sort_keys=True) + "\n").encode("utf-8"))


def _from_entry(key: str, entry: dict) -> VanillaStore:
    return VanillaStore(key=key, root=Path(entry["root"]), disc_id=entry["disc_id"],
                        revision=int(entry["revision"]), adopted=bool(entry.get("adopted")),
                        source_image=entry.get("source_image"))


def list_stores() -> list[VanillaStore]:
    return [_from_entry(key, entry) for key, entry in sorted(_read_registry().items())]


def get_store(key: str) -> Optional[VanillaStore]:
    entry = _read_registry().get(key)
    if entry is None or not Path(entry["root"]).is_dir():
        return None
    return _from_entry(key, entry)


def _register(store: VanillaStore) -> None:
    registry = _read_registry()
    registry[store.key] = store.to_dict()
    _write_registry(registry)


# -- reading a tree --------------------------------------------------------------------------------


def _disc_header(tree: Path) -> tuple[str, int]:
    try:
        header = (tree / "sys" / "boot.bin").read_bytes()[:8]
    except OSError as exc:
        raise ProjectError(f"{tree} has no sys/boot.bin: {exc}") from exc
    if len(header) < 8:
        raise ProjectError(f"{tree / 'sys' / 'boot.bin'} is too short to be a disc header.")
    return header[:6].decode("ascii", "replace"), header[7]


def store_key(tree: Path) -> str:
    disc_id, revision = _disc_header(tree)
    return f"{disc_id}-{revision}-{sha1_of(tree / 'sys' / 'fst.bin')[:8]}"


def find_tree(folder: Path) -> Path:
    """The folder holding ``sys/`` and ``files/`` in a user's extraction: the folder itself, or
    the game partition inside it (``DATA/`` or ``P-<id>/`` as Dolphin and WIT name it)."""
    folder = Path(folder)
    if (folder / "sys").is_dir():
        return folder
    for child in sorted(folder.iterdir()) if folder.is_dir() else ():
        if child.is_dir() and (child / "sys").is_dir() and (child.name.upper() == "DATA" or child.name.startswith("P-")):
            return child
    raise ProjectError(f"{folder} does not hold an extracted disc (no sys/ folder).")


def check_tree(tree: Path, *, wii: bool) -> None:
    """Raise ProjectError unless ``tree`` is a complete extracted disc: the system files, every
    file of the disc's file table at its size, and for Wii what rebuilding the disc needs."""
    from .formats import gcdisc
    missing = [rel for rel in GAMECUBE_REQUIRED + (WII_REQUIRED if wii else ()) if not (tree / rel).exists()]
    if missing:
        raise ProjectError(f"{tree} is not a complete extracted disc: missing {', '.join(missing)}.")
    try:
        entries = gcdisc.read_fst_sizes((tree / "sys" / "fst.bin").read_bytes())
    except (OSError, ValueError) as exc:
        raise ProjectError(f"{tree / 'sys' / 'fst.bin'} could not be read: {exc}") from exc
    wrong = []
    for name, size in entries.items():
        path = tree / "files" / name
        if not path.is_file():
            wrong.append(f"{name} (missing)")
        elif path.stat().st_size != size:
            wrong.append(f"{name} (size {path.stat().st_size}, the disc says {size})")
        if len(wrong) >= 5:
            break
    if wrong:
        raise ProjectError(f"{tree} does not match its disc's file table: {', '.join(wrong)}"
                           + (" ..." if len(wrong) >= 5 else ""))


def describe_tree(tree: Path, progress: Optional[Callable[[int, int], None]] = None) -> dict:
    """``vanilla.json`` for ``tree``: every file's size, modification time and SHA-1."""
    disc_id, revision = _disc_header(tree)
    names = list(_walk_files(tree))
    files = {}
    for index, rel in enumerate(names):
        info = (tree / rel).stat()
        files[rel] = {"size": info.st_size, "mtime_ns": info.st_mtime_ns, "sha1": sha1_of(tree / rel)}
        if progress is not None:
            progress(index + 1, len(names))
    return {"format": FORMAT_VERSION, "disc_id": disc_id, "revision": revision, "files": files}


def _set_read_only(tree: Path, read_only: bool) -> None:
    mode = stat.S_IREAD if read_only else stat.S_IREAD | stat.S_IWRITE
    for rel in _walk_files(tree):
        os.chmod(tree / rel, mode)


def _refresh_times(tree: Path, manifest: dict) -> None:
    """Marking files read-only can touch their times on some file systems: record them after."""
    for rel, entry in manifest["files"].items():
        entry["mtime_ns"] = (tree / rel).stat().st_mtime_ns


# -- making stores ---------------------------------------------------------------------------------


def ensure_store(disc_image: Path | str, *, wii: bool,
                 progress: Optional[Callable[[int, int], None]] = None) -> VanillaStore:
    """The store for ``disc_image``, extracting it first when none exists for that disc.

    The disc is extracted into a temporary folder in the store root and renamed into place only
    once complete, so a failed or cancelled extraction never leaves half a store."""
    disc_image = Path(disc_image).resolve()
    root = store_root()
    root.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".extract-", dir=root) as temporary:
        entry = Path(temporary) / "entry"
        tree = entry / "disc"
        tools.extract_disc(disc_image, tree, overwrite=True, wii=wii)
        key = store_key(tree)
        existing = get_store(key)
        if existing is not None and not existing.verify():
            return existing
        check_tree(tree, wii=wii)
        manifest = describe_tree(tree, progress)
        _set_read_only(tree, True)
        _refresh_times(tree, manifest)
        write_atomic(entry / MANIFEST, (json.dumps(manifest, indent=1) + "\n").encode("utf-8"))
        final = root / key
        if final.exists():
            delete_store_files(final)
        os.replace(entry, final)
    store = VanillaStore(key=key, root=final / "disc", disc_id=manifest["disc_id"], revision=manifest["revision"],
                         adopted=False, source_image=str(disc_image))
    _register(store)
    return store


def adopt_folder(folder: Path | str, *, wii: bool,
                 progress: Optional[Callable[[int, int], None]] = None) -> VanillaStore:
    """Register a folder the user extracted as a store, where it is: nothing is copied, and its
    files are marked read-only. Raises ProjectError when it is not a complete extraction."""
    tree = find_tree(Path(folder)).resolve()
    check_tree(tree, wii=wii)
    key = store_key(tree)
    manifest = describe_tree(tree, progress)
    _set_read_only(tree, True)
    _refresh_times(tree, manifest)
    store = VanillaStore(key=key, root=tree, disc_id=manifest["disc_id"], revision=manifest["revision"],
                         adopted=True)
    write_atomic(store.manifest_path, (json.dumps(manifest, indent=1) + "\n").encode("utf-8"))
    _register(store)
    return store


def delete_store_files(folder: Path) -> None:
    """Delete an app-made store's folder (its files are read-only)."""
    _set_read_only(folder, False)
    shutil.rmtree(folder)


def forget_store(store: VanillaStore) -> None:
    """Drop a store from the registry; an app-made store's files are deleted, an adopted folder
    is left where it is with its files writable again."""
    registry = _read_registry()
    registry.pop(store.key, None)
    _write_registry(registry)
    if store.adopted and store.root.is_dir():
        _set_read_only(store.root, False)
    own = store_root() / store.key
    if own.is_dir():
        delete_store_files(own)


def unlink_shared(link: Path, shared: Path) -> None:
    """Remove ``link``, a hard link to the read-only store file ``shared``, keeping ``shared``
    read-only (on Windows a read-only file cannot be unlinked, and clearing the flag on one link
    clears it on the shared file)."""
    os.chmod(link, stat.S_IREAD | stat.S_IWRITE)
    try:
        link.unlink()
    finally:
        if shared.exists():
            os.chmod(shared, stat.S_IREAD)
