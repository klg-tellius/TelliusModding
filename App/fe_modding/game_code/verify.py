"""Check the catalog against real executables: ``python -m fe_modding.game_code.verify GFEE01.dol ...``."""

from __future__ import annotations

import sys
from pathlib import Path

from . import entries  # noqa: F401  (registers the catalog)
from .catalog import CATALOG, Patch, Session, State, Tunable
from .dol import Dol, DolError
from .versions import identify


def verify(dol: Dol) -> list[str]:
    """Problems found when the catalog meets ``dol`` (empty when every entry is sound).

    On a retail DOL every entry that has sites for its version must read as original; then all
    entries are switched on, read back, and switched off again, which must restore the file
    byte for byte."""
    ident = identify(dol)
    if ident.version is None or not ident.pristine:
        return [f"Not a retail main.dol ({ident.note or 'unknown'})."]
    problems: list[str] = []
    session = Session(dol, ident.version)
    before = dol.sha1()
    for entry in CATALOG.entries.values():
        if ident.version.code not in entry.versions:
            problems.append(f"{entry.id}: no sites for {ident.version.code}")
            continue
        if not entry.versions[ident.version.code]:
            continue          # an option this build does not have
        status = session.status(entry)
        if status.state != State.ORIGINAL:
            problems.append(f"{entry.id}: expected original, found {status.state.value} {status.detail}")
    if problems:
        return problems
    def apply(entry) -> bool:
        if isinstance(entry, Patch):
            session.set_patch(entry, True)
        else:
            session.set_tunable(entry, entry.maximum)
        return True

    def revert_all() -> None:
        pending = [e for e in CATALOG.entries.values() if session.status(e).state != State.UNAVAILABLE]
        for _ in range(len(pending) + 1):       # an option can only be undone once its rival is
            left = []
            for entry in pending:               # values first, then the patches (hooks) they needed
                try:
                    session.reset(entry)
                except DolError:
                    left.append(entry)
            for entry in pending:
                if isinstance(entry, Patch):
                    try:
                        session.set_patch(entry, False)
                    except DolError:
                        if entry not in left:
                            left.append(entry)
            if not left:
                return
            pending = left
        problems.append("Could not revert: " + ", ".join(e.id for e in pending))

    def check_applied(entry) -> None:
        status = session.status(entry)
        want = State.APPLIED if isinstance(entry, Patch) else State.CUSTOM
        if status.state != want:
            problems.append(f"{entry.id}: after applying, found {status.state.value} {status.detail}")

    # entries that share bytes with another (mutually exclusive options) cannot all be on at once:
    # they are applied first-come, and the ones left out are then tried on their own
    deferred = []
    for entry in CATALOG.entries.values():
        if session.status(entry).state == State.UNAVAILABLE:
            continue
        try:
            apply(entry)
        except DolError:
            deferred.append(entry)
    for entry in CATALOG.entries.values():
        if entry not in deferred and session.status(entry).state != State.UNAVAILABLE:
            check_applied(entry)
    revert_all()
    for entry in deferred:
        try:
            apply(entry)
            check_applied(entry)
        except DolError as exc:
            problems.append(f"{entry.id}: cannot be applied on its own: {exc}")
        revert_all()
    if dol.sha1() != before:
        problems.append("Reverting everything did not restore the original file.")
    return problems


def main(argv: list[str]) -> int:
    failed = 0
    for path in argv:
        dol = Dol.open(Path(path))
        problems = verify(dol)
        print(f"{path}: {'ok' if not problems else str(len(problems)) + ' problem(s)'}")
        for line in problems:
            print("  ", line)
        failed += bool(problems)
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
