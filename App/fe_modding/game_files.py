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

:meth:`GameFiles.at` gives a :class:`GamePath`, a :class:`~pathlib.Path` look-alike whose joins,
reads, listings and writes all go through the layer. Code written against paths
(``files_dir / "Face" / name``, ``folder.glob("*.cms")``, ``path.write_bytes(data)``) works on it
unchanged, which is how most of the app reaches game files.
"""

from __future__ import annotations

import fnmatch
import hashlib
import io
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
    #: The project folder (``project.json``, manifests, receipts) beside the game files.
    project_dir: Path

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
        """The disc-relative POSIX path of ``path`` (a relative path, a :class:`GamePath`, or a
        path under a root)."""
        if isinstance(path, GamePath):
            return path.rel
        if isinstance(path, str) and os.path.isabs(path):
            path = Path(path)
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

    def at(self, path: RelPath = "") -> "GamePath":
        """``path`` as a :class:`GamePath` (``files.at("files")`` is the disc's file tree)."""
        return GamePath(self, self.rel(path))

    def find(self, path: RelPath) -> Optional["GamePath"]:
        """``path`` as a :class:`GamePath` when it exists, else None. What to hand out and keep:
        a GamePath reads whichever real file is current, where a real path from :meth:`path`
        would go on naming the vanilla file after the mod replaced it."""
        rel = self.rel(path)
        return GamePath(self, rel) if self.exists(rel) else None

    def path(self, path: RelPath) -> Optional[Path]:
        """The real file or folder to read for ``path``; None when there is none."""
        raise NotImplementedError

    def target(self, path: RelPath) -> Path:
        """The real path a write of ``path`` goes to (whether or not it exists yet): what to key
        a plan of pending writes by. Read through :meth:`path`, write through :meth:`write`."""
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


class _WriteOnClose(io.BytesIO):
    """What :meth:`GamePath.open` returns for writing: the bytes go through the layer on close."""

    def __init__(self, files: GameFiles, rel: str, initial: bytes = b""):
        super().__init__()
        self._files, self._rel = files, rel
        if initial:
            self.write(initial)

    def close(self) -> None:
        if not self.closed:
            self._files.write(self._rel, self.getvalue())
        super().close()


class GamePath(os.PathLike):
    """A game file or folder of one project, used like a :class:`~pathlib.Path`.

    Joins (``/``, :meth:`joinpath`, :attr:`parent`) stay virtual; reads go to the real file the
    layer picks (:meth:`GameFiles.path`); :meth:`iterdir` and :meth:`glob` list the merged tree;
    writes, :meth:`unlink` and :meth:`mkdir` go through the layer. ``os.fspath`` gives the real
    file to read, or where a write would go when there is none, for code and tools that need a
    real path (opening such a path to write bypasses the layer: use :meth:`write_bytes`)."""

    __slots__ = ("files", "rel")

    def __init__(self, files: GameFiles, rel: str):
        self.files = files
        self.rel = rel

    # -- names ---------------------------------------------------------------------------------------
    def _child(self, rel: str) -> "GamePath":
        return GamePath(self.files, self.files.rel(rel))

    def __truediv__(self, other) -> "GamePath":
        other = str(other).replace("\\", "/")
        return self._child(f"{self.rel}/{other}" if self.rel else other)

    def joinpath(self, *parts) -> "GamePath":
        result = self
        for part in parts:
            result = result / part
        return result

    @property
    def name(self) -> str:
        return self.rel.rsplit("/", 1)[-1] if self.rel else ""

    @property
    def stem(self) -> str:
        return PurePosixPath(self.name).stem

    @property
    def suffix(self) -> str:
        return PurePosixPath(self.name).suffix

    @property
    def suffixes(self) -> list[str]:
        return PurePosixPath(self.name).suffixes

    @property
    def parts(self) -> tuple[str, ...]:
        return tuple(self.rel.split("/")) if self.rel else ()

    @property
    def parent(self) -> "GamePath":
        return GamePath(self.files, self.rel.rsplit("/", 1)[0] if "/" in self.rel else "")

    @property
    def parents(self) -> tuple["GamePath", ...]:
        parts = self.parts
        return tuple(GamePath(self.files, "/".join(parts[:i])) for i in range(len(parts) - 1, -1, -1))

    def with_name(self, name: str) -> "GamePath":
        return self.parent / name

    def with_suffix(self, suffix: str) -> "GamePath":
        return self.parent / (self.stem + suffix)

    def with_stem(self, stem: str) -> "GamePath":
        return self.parent / (stem + self.suffix)

    def relative_to(self, other) -> PurePosixPath:
        base = other.rel if isinstance(other, GamePath) else self.files.rel(other)
        if base and self.rel.lower() != base.lower() and not self.rel.lower().startswith(base.lower() + "/"):
            raise ValueError(f"{self.rel!r} is not in {base!r}")
        return PurePosixPath(self.rel[len(base):].lstrip("/") or ".")

    def is_relative_to(self, other) -> bool:
        try:
            self.relative_to(other)
            return True
        except (ValueError, ProjectError):
            return False

    def as_posix(self) -> str:
        return self.rel

    def resolve(self, strict: bool = False) -> "GamePath":
        return self

    def absolute(self) -> "GamePath":
        return self

    def is_absolute(self) -> bool:
        return True

    def real(self) -> Path:
        """The real file to read, or where a write would go when there is none."""
        found = self.files.path(self.rel)
        return found if found is not None else self.files.target(self.rel)

    def __fspath__(self) -> str:
        return str(self.real())

    def __str__(self) -> str:
        return str(self.real())

    def __repr__(self) -> str:
        return f"GamePath({self.rel!r})"

    def __eq__(self, other) -> bool:
        """Equal to the same game file, and to the real path it reads from or writes to (so
        code mixing the two, as dict keys or in lists, keeps working)."""
        if isinstance(other, GamePath):
            return other.files is self.files and other.rel.lower() == self.rel.lower()
        if isinstance(other, Path):
            return other == self.files.target(self.rel) or other == self.files.path(self.rel)
        return NotImplemented

    def __lt__(self, other) -> bool:
        if isinstance(other, GamePath):
            return self.rel.lower() < other.rel.lower()
        return NotImplemented

    def __hash__(self) -> int:
        return hash(self.files.target(self.rel))   # as the real path of the write target

    # -- reading -------------------------------------------------------------------------------------
    def exists(self) -> bool:
        return self.files.exists(self.rel)

    def is_file(self) -> bool:
        return self.files.is_file(self.rel)

    def is_dir(self) -> bool:
        return self.files.is_dir(self.rel)

    def is_symlink(self) -> bool:
        return False

    def _existing(self) -> Path:
        """The real file, raising FileNotFoundError (an OSError, as :class:`~pathlib.Path` would)
        when there is none."""
        found = self.files.path(self.rel)
        if found is None:
            raise FileNotFoundError(2, "No such game file", self.rel)
        return found

    def stat(self):
        return self._existing().stat()

    def read_bytes(self) -> bytes:
        return self._existing().read_bytes()

    def read_text(self, encoding: Optional[str] = None, errors: Optional[str] = None) -> str:
        return self._existing().read_text(encoding=encoding, errors=errors)

    def iterdir(self) -> Iterator["GamePath"]:
        prefix = f"{self.rel}/" if self.rel else ""
        for name in self.files.listdir(self.rel):
            yield GamePath(self.files, prefix + name)

    def glob(self, pattern: str) -> Iterator["GamePath"]:
        """``*.ext``-style patterns in this folder, ``**/<pattern>`` below it, and
        ``<folder pattern>/<pattern>`` one level down (matched without case)."""
        parts = pattern.replace("\\", "/").split("/")
        yield from self._glob(parts)

    def _glob(self, parts: list[str]) -> Iterator["GamePath"]:
        head, rest = parts[0], parts[1:]
        if head == "**":
            if not rest:
                yield self
                for rel in self.files.iter_files(self.rel):
                    yield GamePath(self.files, rel)
                return
            seen = set()
            for folder in [self, *self._folders_below()]:
                for match in folder._glob(rest):
                    if match not in seen:
                        seen.add(match)
                        yield match
            return
        for child in self.iterdir():
            if fnmatch.fnmatchcase(child.name.lower(), head.lower()):
                if not rest:
                    yield child
                elif child.is_dir():
                    yield from child._glob(rest)

    def _folders_below(self) -> list["GamePath"]:
        folders = set()
        for rel in self.files.iter_files(self.rel):
            parts = rel.split("/")[:-1]
            for i in range(len(self.parts) + 1, len(parts) + 1):
                folders.add("/".join(parts[:i]))
        return [GamePath(self.files, rel) for rel in sorted(folders)]

    def rglob(self, pattern: str) -> Iterator["GamePath"]:
        return self.glob(f"**/{pattern}")

    def open(self, mode: str = "r", buffering: int = -1, encoding: Optional[str] = None,
             errors: Optional[str] = None, newline: Optional[str] = None):
        if not any(flag in mode for flag in "wax+"):
            return open(self._existing(), mode, buffering, encoding, errors, newline)
        initial = self.files.read(self.rel) if ("a" in mode or "+" in mode) and self.is_file() else b""
        raw = _WriteOnClose(self.files, self.rel, initial)
        if "b" in mode:
            return raw
        return io.TextIOWrapper(raw, encoding=encoding or "utf-8", errors=errors, newline=newline,
                                write_through=True)

    # -- writing -------------------------------------------------------------------------------------
    def write_bytes(self, data) -> int:
        data = bytes(data)
        self.files.write(self.rel, data)
        return len(data)

    def write_text(self, data: str, encoding: Optional[str] = None, errors: Optional[str] = None,
                   newline: Optional[str] = None) -> int:
        if newline is None:
            data = data.replace("\n", os.linesep)
        elif newline:
            data = data.replace("\n", newline)
        self.files.write(self.rel, data.encode(encoding or "utf-8", errors or "strict"))
        return len(data)

    def unlink(self, missing_ok: bool = False) -> None:
        if not self.is_file():
            if missing_ok:
                return
            raise FileNotFoundError(self.rel)
        self.files.remove(self.rel)

    def mkdir(self, mode: int = 0o777, parents: bool = False, exist_ok: bool = False) -> None:
        if self.exists() and not exist_ok:
            raise FileExistsError(self.rel)
        self.files.mkdir(self.rel)

    def rmdir(self) -> None:
        """Remove an empty folder (OSError when it holds anything, as for a real folder)."""
        if self.files.listdir(self.rel):
            raise OSError(39, "Directory not empty", self.rel)
        self.files.remove(self.rel)

    def touch(self, exist_ok: bool = True) -> None:
        if not self.exists():
            self.files.write(self.rel, b"")

    def replace(self, target) -> "GamePath":
        target = target if isinstance(target, GamePath) else self._child(self.files.rel(target))
        target.write_bytes(self.read_bytes())
        self.files.remove(self.rel)
        return target

    rename = replace


# -- the layout older projects use ---------------------------------------------------------------------


class LegacyFiles(GameFiles):
    """``extracted/`` edited in place, with first copies of replaced files in ``originals/``."""

    def __init__(self, extracted: Path, originals: Path):
        self.root = Path(extracted)
        self.originals = Path(originals)
        self.roots = (self.originals, self.root)
        self.project_dir = self.root.parent
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

    def target(self, path: RelPath) -> Path:
        return self.root / self.rel(path)

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
        self.project_dir = self.output.parent
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

    def target(self, path: RelPath) -> Path:
        return self.output / self.rel(path)

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


def remove_tree(path) -> None:
    """``shutil.rmtree`` for a real folder, or the layer's remove for a :class:`GamePath`."""
    if isinstance(path, GamePath):
        path.files.remove(path.rel)
    else:
        shutil.rmtree(path)


def as_path(path) -> "Path | GamePath":
    """``Path(path)``, except that a :class:`GamePath` stays one (``Path()`` of it would give the
    real file and leave the layer). Use it where a function takes a folder as ``Path | str``."""
    return path if isinstance(path, GamePath) else Path(path)


def as_files(source) -> GameFiles:
    """A layer for ``source``: a :class:`GameFiles` as it is, the layer of a :class:`GamePath`, a
    project (:func:`files_of`), or the ``files/`` folder of a plain extracted disc (tools and
    tests reading a retail tree; read only)."""
    if isinstance(source, GameFiles):
        return source
    if isinstance(source, GamePath):
        return source.files
    if isinstance(source, (str, Path)):
        root = Path(source).parent
        return LegacyFiles(root, root / "originals")
    return files_of(source)


def files_of(project) -> GameFiles:
    """The file layer of ``project``, or of a light stand-in some tests pass around (an object
    with ``extracted_dir`` and maybe ``originals_dir``: treated as the older layout)."""
    files = getattr(project, "files", None)
    if isinstance(files, GameFiles):
        return files
    if getattr(project, "extracted_dir", None) is not None:
        extracted = Path(project.extracted_dir)
    elif getattr(project, "files_dir", None) is not None:
        extracted = Path(project.files_dir).parent    # a stand-in that only names its files/ folder
    else:
        extracted = Path(project.directory) / "extracted"
    originals = getattr(project, "originals_dir", None)
    return LegacyFiles(extracted, Path(originals) if originals else extracted.parent / "originals")

