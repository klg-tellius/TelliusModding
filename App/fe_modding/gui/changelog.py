"""A running, in-session record of every edit made across every editor -
the "what have I actually changed in this mod so far" view that the flat
row of popup editors never had. Session-scoped only (not persisted to
disk): it exists to let a user review/audit a mod-in-progress before
building, not as a durable log.

Every editor gets a ``ChangeLog`` instance from ``MainWindow`` at
construction and calls ``changelog.append(...)`` alongside its existing
"Saved"/"Unsaved changes" status-label updates - one line, added next to
code that's already there, not a new tracking mechanism layered on top of
existing state.
"""

from __future__ import annotations

import datetime
from dataclasses import dataclass, field


@dataclass(frozen=True)
class ChangeEntry:
    timestamp: str
    scope: str  # e.g. a chapter id, a character PID, or a global editor name
    description: str  # e.g. "Ike's level: 1 -> 7"

    def format(self) -> str:
        return f"[{self.timestamp}] {self.scope}: {self.description}"


@dataclass
class ChangeLog:
    entries: list = field(default_factory=list)
    _listeners: list = field(default_factory=list)

    def append(self, scope: str, description: str) -> None:
        entry = ChangeEntry(timestamp=datetime.datetime.now().strftime("%H:%M:%S"), scope=scope, description=description)
        self.entries.append(entry)
        for listener in self._listeners:
            listener(entry)

    def subscribe(self, listener) -> None:
        """listener(entry: ChangeEntry) is called for every future append()."""
        self._listeners.append(listener)

    def recent_first(self) -> list:
        return list(reversed(self.entries))
