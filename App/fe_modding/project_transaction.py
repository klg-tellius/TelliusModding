"""Recoverable multi-file project writes with stale-input checks.

Each replacement is atomic, but the group is not filesystem-atomic. A journal
keeps before/after bytes until completion so interrupted writes can be rolled
back. Callers must stop other project writers while committing or recovering.
"""
from pathlib import Path
import json
import os
import shutil
import hashlib
from contextlib import contextmanager

JOURNAL = ".extended-flags-transaction"
LOCK = ".extended-flags.lock"


@contextmanager
def _exclusive(root):
    """An OS lock prevents recovery racing another live installer."""
    path = root / LOCK
    if path.is_symlink():
        raise ValueError("Transaction lock must not be a symbolic link")
    with path.open("a+b") as handle:
        if handle.tell() == 0:
            handle.write(b"\0")
            handle.flush()
        handle.seek(0)
        try:
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            raise RuntimeError("Another installation or recovery is using this project") from exc
        try:
            yield
        finally:
            handle.seek(0)
            if os.name == "nt":
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def _target(root, path):
    path = Path(path).absolute()
    # Check the spelling supplied by the caller before resolving it so a
    # symlink cannot be used to escape and then re-enter the project.  Resolve
    # afterwards because Windows may spell the same path through an 8.3 alias
    # (for example RUNNER~1 versus runneradmin on GitHub Actions).
    cursor = Path(path.anchor)
    for part in path.parts[1:]:
        cursor /= part
        if cursor.is_symlink():
            raise ValueError("Transaction targets must not traverse symbolic links")
    path = path.resolve()
    relative = path.relative_to(root)
    if not relative.parts or relative.parts[0] in (JOURNAL, LOCK):
        raise ValueError("Transaction target overlaps its journal")
    return path


def _read(path):
    return path.read_bytes() if path.exists() else None


def _store(path, data):
    with path.open("wb") as handle:
        handle.write(data)
        handle.flush()
        os.fsync(handle.fileno())


def _replace(path, data, journal):
    if data is None:
        path.unlink(missing_ok=True)
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = journal / "replace.tmp"
    _store(temporary, data)
    os.replace(temporary, path)


def _manifest(journal, data):
    temporary = journal / "manifest.tmp"
    _store(temporary, json.dumps(data).encode("utf-8"))
    os.replace(temporary, journal / "manifest.json")


def recover(root):
    """Roll back an interrupted transaction; refuse to overwrite later edits."""
    root = Path(root).resolve()
    with _exclusive(root):
        return _recover(root)


def _recover(root):
    journal = root / JOURNAL
    if not journal.exists():
        return False
    if journal.is_symlink():
        raise ValueError("Transaction journal must not be a symbolic link")
    manifest = json.loads((journal / "manifest.json").read_text(encoding="utf-8"))
    if manifest.get("version") != 1 or manifest.get("state") not in ("pending", "complete"):
        raise ValueError("Unrecognized transaction journal")
    entries = []
    seen = set()
    for i, entry in enumerate(manifest["files"]):
        path = _target(root, root / entry["path"])
        if path in seen:
            raise ValueError("Duplicate transaction recovery target")
        seen.add(path)
        before = (journal / f"{i}.before").read_bytes() if entry["existed"] else None
        after = (journal / f"{i}.after").read_bytes()
        if ((hashlib.sha256(before).hexdigest() if before is not None else None) != entry["before_sha256"]
                or hashlib.sha256(after).hexdigest() != entry["after_sha256"]):
            raise ValueError("Transaction recovery data failed its checksum")
        allowed = (after,) if manifest["state"] == "complete" else (before, after)
        if _read(path) not in allowed:
            raise ValueError(f"Recovery refused: file changed outside the transaction: {path}")
        entries.append((path, before))
    if manifest["state"] == "pending":
        for path, before in reversed(entries):
            _replace(path, before, journal)
    shutil.rmtree(journal)
    return True


def commit(root, changes, dependencies=(), *, validate=None):
    """Commit objects with path/before/after fields, retaining recovery on failure.

    Existing journals are never automatically overwritten. Recovery is explicit,
    allowing the app to report an interrupted transaction before further edits.
    """
    root = Path(root).resolve()
    with _exclusive(root):
        return _commit(root, changes, dependencies, validate)


def _commit(root, changes, dependencies, validate):
    if validate is not None:
        validate()
    checked = []
    seen = set()
    for change in changes:
        path = _target(root, change.path)
        if (path in seen or not isinstance(change.after, bytes)
                or change.before is not None and not isinstance(change.before, bytes)):
            raise ValueError("Duplicate target or invalid transaction payload")
        seen.add(path)
        if _read(path) != change.before:
            raise ValueError(f"Project changed before commit: {path}")
        checked.append((path, change.before, change.after))
    inputs = [(_target(root, path), before) for path, before in dependencies]
    for path, before in inputs:
        if _read(path) != before:
            raise ValueError(f"Project changed before commit: {path}")
    journal = root / JOURNAL
    journal.mkdir()  # exclusive lock: refuses existing interrupted transactions
    ready = False
    try:
        entries = []
        for i, (path, before, after) in enumerate(checked):
            if before is not None:
                _store(journal / f"{i}.before", before)
            _store(journal / f"{i}.after", after)
            entries.append({"path": path.relative_to(root).as_posix(), "existed": before is not None,
                            "before_sha256": hashlib.sha256(before).hexdigest() if before is not None else None,
                            "after_sha256": hashlib.sha256(after).hexdigest()})
        manifest = {"version": 1, "state": "pending", "files": entries}
        _manifest(journal, manifest)
        ready = True
        if validate is not None:
            validate()
        for path, before in inputs:
            if _read(path) != before:
                raise ValueError(f"Project changed during staging: {path}")
        for path, before, after in checked:
            if _read(path) != before:
                raise ValueError(f"Project changed during commit: {path}")
            _replace(path, after, journal)
        manifest["state"] = "complete"
        _manifest(journal, manifest)
    except Exception as error:
        if ready:
            try:
                _recover(root)
            except Exception as recovery_error:
                raise RuntimeError(f"Transaction failed; recovery files retained in {journal}: {recovery_error}") from error
        else:
            shutil.rmtree(journal)
        raise
    shutil.rmtree(journal)
