"""The project's game files, read and written through one layer.

Every editor reaches the disc's files through ``project.files`` instead of joining paths onto the
extracted folder, so where a file really lives is decided here alone:

- :class:`LegacyFiles` is the layout older projects use: one writable tree in ``extracted/`` that
  edits overwrite, with the file as extracted kept in ``originals/`` the first time it is replaced.
- :class:`OverlayFiles` is the input/output layout: a read-only vanilla tree shared by every project
  of that disc (the input), and ``output/`` holding only the files the mod replaced or added. A
  file is read from the output when it is there, else from the input, unless the mod removed it
  (``overlay.json``).

Paths are disc-relative POSIX strings, as in the disc's file table plus the ``sys/`` folder:
``"files/FE8Data.bin"``, ``"sys/main.dol"``. A :class:`~pathlib.Path` under one of the layer's
roots is accepted too and turned into its relative path, so code holding a path it got from
:meth:`GameFiles.path` can pass it back.
"""

from __future__ import annotations

import fnmatch
import hashlib
import json
import os
import shutil
import struct
import tempfile
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import Iterator, Optional, Union

from .exceptions import ProjectError

RelPath = Union[str, PurePosixPath, Path]

FILES = "files"   # the disc's file tree, where the game profile's paths are relative to
SYS = "sys"       # boot.bin, bi2.bin, apploader.img, main.dol, fst.bin

OVERLAY_FILE = "overlay.json"


@dataclass
class Changes:
    """What a mod changes relative to its input, as disc-relative paths (sorted)."""

    replaced: list[str] = field(default_factory=list)
    added: list[str] = field(default_factory=list)
    removed: list[str] = field(default_factory=list)

    def __bool__(self) -> bool:
        return bool(self.replaced or self.added or self.removed)


def game_path(*parts: str) -> str:
    """``"files/<parts...>"``: a path in the disc's file tree."""
    return str(PurePosixPath(FILES, *parts))


def write_atomic(path: Path, data: bytes) -> None:
    """Write ``data`` to ``path`` through a temporary file in the same folder, then replace.

    A reader never sees half a file, an exception leaves the old file as it was, and a hard link
    at ``path`` is replaced rather than written through (so a file shared with another tree by a
    link is never changed by this write)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, temporary = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(handle, "wb") as out:
            out.write(data)
        os.replace(temporary, path)
    except BaseException:
        try:
            os.unlink(temporary)
        except OSError:
            pass
        raise


def copy_atomic(source: Path, path: Path) -> None:
    """Copy ``source`` to ``path`` the way :func:`write_atomic` writes (metadata kept)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, temporary = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    os.close(handle)
    try:
        shutil.copy2(source, temporary)
        os.replace(temporary, path)
    except BaseException:
        try:
            os.unlink(temporary)
        except OSError:
            pass
        raise


def sha1_of(path: Path) -> str:
    digest = hashlib.sha1()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _is_temporary(name: str) -> bool:
    return name.startswith(".") and name.endswith(".tmp")


def _walk_files(root: Path) -> Iterator[str]:
    """Relative POSIX paths of every file under ``root`` (none when it is missing)."""
    if not root.is_dir():
        return
    for folder, dirs, names in os.walk(root):
        dirs.sort()
        base = Path(folder)
        for name in sorted(names):
            if not _is_temporary(name):
                yield (base / name).relative_to(root).as_posix()


class GameFiles:
    """The common interface; see the module docstring."""

    #: Roots a :class:`~pathlib.Path` argument may be under, most specific first.
    roots: tuple[Path, ...] = ()

    def _canonical(self, rel: str, trees: tuple[Path, ...]) -> str:
        """``rel`` with each part spelled as the first of ``trees`` that has it spells it, so one
        file has one name however its case was given (the file system ignores case, and the
        game's own paths mix ``Mess`` and ``mess``). Folder listings are cached; a name the cache
        lacks lists the folder again."""
        if not rel:
            return rel
        cache = self.__dict__.setdefault("_names", {})
        out: list[str] = []
        for part in rel.split("/"):
            key, real = part.lower(), None
            for tree in trees:
                folder = tree.joinpath(*out)
                names = cache.get(folder)
                if names is None or key not in names:
                    try:
                        names = {name.lower(): name for name in os.listdir(folder)}
                    except OSError:
                        names = {}
                    cache[folder] = names
                real = names.get(key)
                if real is not None:
                    break
            out.append(real or part)
        return "/".join(out)

    # -- paths ---------------------------------------------------------------------------------------
    def rel(self, path: RelPath) -> str:
        """The disc-relative POSIX path of ``path`` (a relative path, or a path under a root)."""
        if isinstance(path, Path) and path.is_absolute():
            resolved = path.resolve()
            for root in self.roots:
                try:
                    return resolved.relative_to(root.resolve()).as_posix()
                except ValueError:
                    continue
            raise ProjectError(f"{path} is not one of the project's game files.")
        text = PurePosixPath(str(path).replace("\\", "/")).as_posix()
        parts = [p for p in text.split("/") if p not in ("", ".")]
        if any(p == ".." for p in parts):
            raise ProjectError(f"{path} leaves the game's file tree.")
        return "/".join(parts)

    def path(self, path: RelPath) -> Optional[Path]:
        """The real file or folder to read for ``path``; None when there is none."""
        raise NotImplementedError

    def require(self, path: RelPath) -> Path:
        """:meth:`path`, raising ProjectError when the file is missing."""
        found = self.path(path)
        if found is None:
            raise ProjectError(f"{self.rel(path)} was not found. Extract the project first.")
        return found

    # -- reading -------------------------------------------------------------------------------------
    def exists(self, path: RelPath) -> bool:
        return self.path(path) is not None

    def is_file(self, path: RelPath) -> bool:
        found = self.path(path)
        return found is not None and found.is_file()

    def is_dir(self, path: RelPath) -> bool:
        found = self.path(path)
        return found is not None and found.is_dir()

    def read(self, path: RelPath) -> bytes:
        return self.require(path).read_bytes()

    def read_or_none(self, path: RelPath) -> Optional[bytes]:
        found = self.path(path)
        return found.read_bytes() if found is not None and found.is_file() else None

    def size(self, path: RelPath) -> int:
        return self.require(path).stat().st_size

    def listdir(self, folder: RelPath = "") -> list[str]:
        """Names directly in ``folder`` (files and folders, merged over both trees), sorted."""
        raise NotImplementedError

    def iter_files(self, folder: RelPath = "") -> list[str]:
        """Relative paths of every file under ``folder``, recursively, sorted."""
        raise NotImplementedError

    def glob(self, folder: RelPath, pattern: str = "*", *, recursive: bool = False,
             dirs: bool = False) -> list[str]:
        """Relative paths in ``folder`` whose name matches ``pattern`` (case-insensitive, as on
        the Windows file system the app runs on): files only unless ``dirs``; recursive matches
        every file below ``folder``."""
        base = self.rel(folder)
        pattern = pattern.lower()
        if recursive:
            found = self.iter_files(base)
            return [p for p in found if fnmatch.fnmatchcase(p.rsplit("/", 1)[-1].lower(), pattern)]
        out = []
        for name in self.listdir(base):
            if not fnmatch.fnmatchcase(name.lower(), pattern):
                continue
            child = f"{base}/{name}" if base else name
            if self.is_dir(child) == dirs:
                out.append(child)
        return out

    @property
    def has_files(self) -> bool:
        """Whether the game's files are there to edit (``sys/main.dol`` and ``files/``)."""
        return self.is_file("sys/main.dol") and self.is_dir(FILES)

    # -- the vanilla files ---------------------------------------------------------------------------
    def vanilla_path(self, path: RelPath) -> Optional[Path]:
        """The file as it was on the disc; None when the disc had none."""
        raise NotImplementedError

    def vanilla(self, path: RelPath) -> Optional[bytes]:
        found = self.vanilla_path(path)
        return found.read_bytes() if found is not None and found.is_file() else None

    # -- writing -------------------------------------------------------------------------------------
    def write(self, path: RelPath, data: bytes) -> Path:
        """Write a game file and return the real path written."""
        raise NotImplementedError

    def import_file(self, path: RelPath, source: Path) -> Path:
        """Write the contents of the file ``source`` as game file ``path``."""
        return self.write(path, Path(source).read_bytes())

    def writable_copy(self, path: RelPath) -> Path:
        """A real path to change ``path`` in place (for tools that edit a file where it is): the
        current file is first put where edits go. Prefer :meth:`write`."""
        raise NotImplementedError

    def remove(self, path: RelPath) -> None:
        """Remove a game file (a folder: every file under it)."""
        raise NotImplementedError

    def revert(self, path: RelPath) -> bool:
        """Drop the mod's change to ``path``: back to the disc's file, or gone when the mod added
        it. Returns whether anything changed."""
        raise NotImplementedError

    def mkdir(self, folder: RelPath) -> None:
        """Make sure an (empty) folder exists where edits go."""
        raise NotImplementedError

    # -- what changed --------------------------------------------------------------------------------
    def is_modified(self, path: RelPath) -> bool:
        """Whether the mod replaced or added ``path``."""
        raise NotImplementedError

    def is_added(self, path: RelPath) -> Optional[bool]:
        """Whether ``path`` is a file the disc did not have; None when that cannot be told."""
        raise NotImplementedError

    def is_removed(self, path: RelPath) -> bool:
        raise NotImplementedError

    def modified_in(self, folder: RelPath) -> list[str]:
        """Files directly in ``folder`` that the mod replaced (not added), sorted."""
        raise NotImplementedError

    def changes(self) -> Changes:
        raise NotImplementedError


# -- the layout older projects use ---------------------------------------------------------------------


class LegacyFiles(GameFiles):
    """``extracted/`` edited in place, with first copies of replaced files in ``originals/``."""

    def __init__(self, extracted: Path, originals: Path):
        self.root = Path(extracted)
        self.originals = Path(originals)
        self.roots = (self.originals, self.root)
        self._fst_cache: Optional[tuple[float, dict[str, str]]] = None

    def _disc_paths(self) -> Optional[dict[str, str]]:
        """The disc's files (``files/...`` from ``sys/fst.bin``, which a build never rewrites) by
        lower-cased path, the way the case-insensitive file system matches them; None when the
        table is missing or unreadable."""
        from .formats import gcdisc
        fst = self.root / SYS / "fst.bin"
        try:
            stamp = fst.stat().st_mtime
        except OSError:
            return None
        if self._fst_cache is None or self._fst_cache[0] != stamp:
            try:
                names = gcdisc.read_fst_sizes(fst.read_bytes())
            except (OSError, ValueError, struct.error):
                return None
            self._fst_cache = (stamp, {f"{FILES}/{n}".lower(): f"{FILES}/{n}" for n in names})
        return self._fst_cache[1] or None

    def rel(self, path: RelPath) -> str:
        return self._canonical(super().rel(path), (self.root, self.originals))

    def path(self, path: RelPath) -> Optional[Path]:
        real = self.root / self.rel(path)
        return real if real.exists() else None

    def listdir(self, folder: RelPath = "") -> list[str]:
        real = self.root / self.rel(folder)
        if not real.is_dir():
            return []
        return sorted(p.name for p in real.iterdir() if not _is_temporary(p.name))

    def iter_files(self, folder: RelPath = "") -> list[str]:
        base = self.rel(folder)
        prefix = f"{base}/" if base else ""
        return [prefix + p for p in _walk_files(self.root / base)]

    def vanilla_path(self, path: RelPath) -> Optional[Path]:
        rel = self.rel(path)
        original = self.originals / rel
        if original.is_file():
            return original
        current = self.root / rel
        if not current.is_file() or self.is_added(rel):
            return None
        return current   # never replaced through the layer: the extracted file itself

    def _keep_original(self, rel: str) -> None:
        current, original = self.root / rel, self.originals / rel
        if current.is_file() and not original.exists() and self.is_added(rel) is not True:
            original.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(current, original)

    def write(self, path: RelPath, data: bytes) -> Path:
        rel = self.rel(path)
        self._keep_original(rel)
        real = self.root / rel
        write_atomic(real, data)
        return real

    def writable_copy(self, path: RelPath) -> Path:
        rel = self.rel(path)
        self._keep_original(rel)
        return self.root / rel

    def remove(self, path: RelPath) -> None:
        rel = self.rel(path)
        real = self.root / rel
        if real.is_dir():
            for child in self.iter_files(rel):
                self.remove(child)
            shutil.rmtree(real, ignore_errors=True)
            return
        if real.is_file():
            self._keep_original(rel)
            real.unlink()

    def revert(self, path: RelPath) -> bool:
        rel = self.rel(path)
        original, current = self.originals / rel, self.root / rel
        if original.is_file():
            copy_atomic(original, current)
            original.unlink()
            return True
        if current.is_file() and self.is_added(rel):
            current.unlink()
            return True
        return False

    def mkdir(self, folder: RelPath) -> None:
        (self.root / self.rel(folder)).mkdir(parents=True, exist_ok=True)

    def is_modified(self, path: RelPath) -> bool:
        rel = self.rel(path)
        return (self.originals / rel).is_file() or (self.root / rel).is_file() and self.is_added(rel) is True

    def is_added(self, path: RelPath) -> Optional[bool]:
        rel = self.rel(path)
        if not rel.startswith(f"{FILES}/"):
            return False   # sys/ files are fixed: the disc always has them
        disc = self._disc_paths()
        return None if disc is None else rel.lower() not in disc

    def is_removed(self, path: RelPath) -> bool:
        rel = self.rel(path)
        disc = self._disc_paths() or {}
        return rel.lower() in disc and not (self.root / rel).exists()

    def modified_in(self, folder: RelPath) -> list[str]:
        base = self.rel(folder)
        kept = self.originals / base
        if not kept.is_dir():
            return []
        prefix = f"{base}/" if base else ""
        return [prefix + p.name for p in sorted(kept.iterdir()) if p.is_file()]

    def changes(self) -> Changes:
        replaced = [rel for rel in _walk_files(self.originals) if (self.root / rel).is_file()]
        disc = self._disc_paths() or {}
        present = {rel.lower(): rel for rel in self.iter_files(FILES)}
        added = sorted(rel for key, rel in present.items() if key not in disc) if disc else []
        removed = sorted(rel for key, rel in disc.items() if key not in present)
        return Changes(sorted(replaced), added, removed)


# -- the input/output layout ---------------------------------------------------------------------------


class OverlayFiles(GameFiles):
    """A read-only input tree with the mod's files in an output tree laid over it."""

    def __init__(self, input_root: Path, output_root: Path, overlay_file: Path):
        self.input = Path(input_root)
        self.output = Path(output_root)
        self.overlay_file = Path(overlay_file)
        self.roots = (self.output, self.input)
        self._state: Optional[dict] = None

    def rel(self, path: RelPath) -> str:
        """The relative path in the input's own spelling (``files/Mess`` whatever case it was
        given in); parts the input lacks take the output's spelling."""
        return self._canonical(super().rel(path), (self.input, self.output))

    # overlay.json: {"removed": [...], "base": {rel: sha1 of the input file it replaced}}
    def _load(self) -> dict:
        if self._state is None:
            try:
                state = json.loads(self.overlay_file.read_text(encoding="utf-8"))
            except FileNotFoundError:
                state = {}
            except (OSError, json.JSONDecodeError) as exc:
                raise ProjectError(f"{self.overlay_file} could not be read: {exc}") from exc
            self._state = {"removed": sorted(set(state.get("removed", []))),
                           "base": dict(state.get("base", {}))}
        return self._state

    def _save(self) -> None:
        state = self._load()
        text = json.dumps({"removed": sorted(set(state["removed"])), "base": dict(sorted(state["base"].items()))},
                          indent=2) + "\n"
        write_atomic(self.overlay_file, text.encode("utf-8"))

    @property
    def removed(self) -> frozenset[str]:
        return frozenset(self._load()["removed"])

    def _removed_by(self, rel: str) -> bool:
        """Whether ``rel`` or a folder above it is removed."""
        removed = self.removed
        if not removed:
            return False
        parts = rel.split("/")
        return any("/".join(parts[:i]) in removed for i in range(1, len(parts) + 1))

    def path(self, path: RelPath) -> Optional[Path]:
        rel = self.rel(path)
        out = self.output / rel
        if out.exists():
            return out
        if self._removed_by(rel):
            return None
        source = self.input / rel
        return source if source.exists() else None

    def listdir(self, folder: RelPath = "") -> list[str]:
        base = self.rel(folder)
        prefix = f"{base}/" if base else ""
        names: set[str] = set()
        out = self.output / base
        if out.is_dir():
            names.update(p.name for p in out.iterdir() if not _is_temporary(p.name))
        source = self.input / base
        if source.is_dir() and not (base and self._removed_by(base)):
            for p in source.iterdir():
                if not self._removed_by(prefix + p.name) or (out / p.name).exists():
                    names.add(p.name)
        return sorted(names)

    def iter_files(self, folder: RelPath = "") -> list[str]:
        base = self.rel(folder)
        prefix = f"{base}/" if base else ""
        found = {prefix + p for p in _walk_files(self.output / base)}
        for p in _walk_files(self.input / base):
            rel = prefix + p
            if rel not in found and not self._removed_by(rel):
                found.add(rel)
        return sorted(found)

    def vanilla_path(self, path: RelPath) -> Optional[Path]:
        source = self.input / self.rel(path)
        return source if source.is_file() else None

    def _unremove(self, rel: str) -> None:
        """Writing ``rel`` brings it back: drop its own removal and its folders'."""
        state = self._load()
        parts = rel.split("/")
        above = {"/".join(parts[:i]) for i in range(1, len(parts) + 1)}
        kept = [r for r in state["removed"] if r not in above]
        if len(kept) != len(state["removed"]):
            # A removed folder that held other files: keep those removed one by one.
            for folder in sorted(above & set(state["removed"])):
                if folder == rel:
                    continue
                for child in _walk_files(self.input / folder):
                    child_rel = f"{folder}/{child}"
                    if child_rel != rel and not child_rel.startswith(rel + "/"):
                        kept.append(child_rel)
            state["removed"] = sorted(set(kept))
            self._save()

    def _record_base(self, rel: str) -> None:
        state = self._load()
        source = self.input / rel
        if rel not in state["base"] and source.is_file():
            state["base"][rel] = sha1_of(source)
            self._save()

    def write(self, path: RelPath, data: bytes) -> Path:
        rel = self.rel(path)
        if not rel:
            raise ProjectError("A game file needs a path.")
        out = self.output / rel
        write_atomic(out, data)
        self._record_base(rel)
        self._unremove(rel)
        return out

    def import_file(self, path: RelPath, source: Path) -> Path:
        rel = self.rel(path)
        out = self.output / rel
        copy_atomic(Path(source), out)
        self._record_base(rel)
        self._unremove(rel)
        return out

    def writable_copy(self, path: RelPath) -> Path:
        rel = self.rel(path)
        out = self.output / rel
        if not out.exists():
            current = self.path(rel)
            if current is not None and current.is_file():
                copy_atomic(current, out)
                os.chmod(out, 0o666)   # the input's files are read-only; the copy must not be
                self._record_base(rel)
            self._unremove(rel)
        return out

    def remove(self, path: RelPath) -> None:
        rel = self.rel(path)
        out = self.output / rel
        if out.is_dir():
            shutil.rmtree(out)
        elif out.exists():
            out.unlink()
        state = self._load()
        if (self.input / rel).exists() and rel not in state["removed"]:
            state["removed"].append(rel)
        for key in [k for k in state["base"] if k == rel or k.startswith(rel + "/")]:
            del state["base"][key]
        self._save()

    def revert(self, path: RelPath) -> bool:
        rel = self.rel(path)
        changed = False
        out = self.output / rel
        if out.is_file():
            out.unlink()
            changed = True
        state = self._load()
        if rel in state["removed"]:
            state["removed"].remove(rel)
            changed = True
        if state["base"].pop(rel, None) is not None or changed:
            self._save()
        return changed

    def mkdir(self, folder: RelPath) -> None:
        rel = self.rel(folder)
        (self.output / rel).mkdir(parents=True, exist_ok=True)
        self._unremove(rel)

    def is_modified(self, path: RelPath) -> bool:
        return (self.output / self.rel(path)).is_file()

    def is_added(self, path: RelPath) -> Optional[bool]:
        rel = self.rel(path)
        return (self.output / rel).is_file() and not (self.input / rel).is_file()

    def is_removed(self, path: RelPath) -> bool:
        rel = self.rel(path)
        return (self.input / rel).exists() and self.path(rel) is None

    def modified_in(self, folder: RelPath) -> list[str]:
        base = self.rel(folder)
        out = self.output / base
        if not out.is_dir():
            return []
        prefix = f"{base}/" if base else ""
        return [prefix + p.name for p in sorted(out.iterdir())
                if p.is_file() and not _is_temporary(p.name) and (self.input / base / p.name).is_file()]

    def changes(self) -> Changes:
        replaced, added = [], []
        for rel in _walk_files(self.output):
            (replaced if (self.input / rel).is_file() else added).append(rel)
        removed = set()
        for rel in self.removed:
            source = self.input / rel
            if source.is_dir():
                removed.update(f"{rel}/{p}" for p in _walk_files(source))
            elif source.is_file():
                removed.add(rel)
        removed = {r for r in removed if not (self.output / r).is_file()}
        return Changes(replaced, added, sorted(removed))

    def base_hashes(self) -> dict[str, str]:
        """SHA-1 of the input file each replaced file was made from."""
        return dict(self._load()["base"])


def files_of(project) -> GameFiles:
    """The file layer of ``project``, or of a light stand-in some tests pass around (an object
    with ``extracted_dir`` and maybe ``originals_dir``: treated as the older layout)."""
    files = getattr(project, "files", None)
    if isinstance(files, GameFiles):
        return files
    extracted = Path(project.extracted_dir)
    originals = getattr(project, "originals_dir", None)
    return LegacyFiles(extracted, Path(originals) if originals else extracted.parent / "originals")

