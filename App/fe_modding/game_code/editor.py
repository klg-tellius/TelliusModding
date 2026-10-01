"""The project's ``sys/main.dol`` opened for editing: the model behind the Game Code page.

Every change is written to disk at once (atomically), like the other editors, since building
packages whatever is in ``extracted/``."""

from __future__ import annotations

import os
from pathlib import Path

from . import entries  # noqa: F401  (registers the catalog)
from .catalog import CATALOG, Entry, Patch, Session, State, Status, Tunable
from .dol import Dol
from .versions import Identification, identify, read_boot_code


def _format(value) -> str:
    return f"{value:g}" if isinstance(value, (int, float)) else str(value)


class CodeEditor:
    def __init__(self, extracted_dir: Path | str, writer=None):
        """``writer(path, data)`` saves the file (the project's keeps an original copy)."""
        self._writer = writer
        self.extracted_dir = Path(extracted_dir)
        self.path = self.extracted_dir / "sys" / "main.dol"
        self.dol = Dol.open(self.path)
        self.identification: Identification = identify(self.dol, read_boot_code(self.extracted_dir))
        self.session = Session(self.dol, self.identification.version)

    @property
    def version(self):
        return self.identification.version

    @property
    def supported(self) -> bool:
        return self.version is not None

    def status(self, entry: Entry) -> Status:
        if not self.supported:
            return Status(State.UNAVAILABLE, self.identification.note or "Unrecognised main.dol.")
        return self.session.status(entry)

    def modified_entries(self) -> list[Entry]:
        return [e for e in CATALOG.entries.values() if not getattr(e, "internal", False)
                and self.status(e).state in (State.APPLIED, State.CUSTOM)]

    # -- edits: each returns the change-log description -----------------------------------------
    def set_patch(self, patch: Patch, enabled: bool) -> str:
        self.session.set_patch(patch, enabled)
        self._save()
        return f"{patch.name}: {'on' if enabled else 'off'}"

    def set_value(self, tunable, value: float) -> str:
        old = self.status(tunable).value
        self.session.set_tunable(tunable, value)
        self._save()
        return f"{tunable.name}: {_format(old)} -> {_format(value)}"

    def reset(self, entry: Entry) -> str:
        self.session.reset(entry)
        self._save()
        return f"{entry.name}: reset"

    def reset_all(self) -> int:
        changed = self.modified_entries()
        for entry in changed:
            self.session.reset(entry)
        self._save()
        return len(changed)

    def _drop_idle_hooks(self) -> None:
        """Take out hooks whose tunables are all back at their defaults (vanilla again)."""
        for hook in CATALOG.entries.values():
            if not (isinstance(hook, Patch) and hook.internal):
                continue
            users = [e for e in CATALOG.entries.values() if isinstance(e, Tunable) and hook in e.requires]
            if self.session.patch_status(hook).state == State.APPLIED and all(
                    self.session.tunable_status(u).state == State.ORIGINAL for u in users):
                self.session.set_patch(hook, False)

    def _save(self) -> None:
        self._drop_idle_hooks()
        if self._writer is not None:
            self._writer(self.path, bytes(self.dol.data))
            return
        partial = self.path.with_name(self.path.name + ".part")
        try:
            partial.write_bytes(bytes(self.dol.data))
            os.replace(partial, self.path)
        finally:
            partial.unlink(missing_ok=True)
