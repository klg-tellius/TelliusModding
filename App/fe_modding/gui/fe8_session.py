"""One in-memory ``FE8Data.bin`` shared by every view that edits it.

The character page and the Game Data page (classes, items, skills, terrain)
both patch this file. Each keeping its own copy would let one save silently
drop the other's edits, so both work on this session: patches go to
``session.data``, :meth:`changed` tells every other view, and :meth:`save`
writes once for all of them.

Nothing is lost by switching pages - the edits stay here until saved, and the
workspace asks about them when the project closes.
"""

from __future__ import annotations

from typing import Callable, Optional

from ..formats import fe8data
from ..project import ModProject
from .changelog import ChangeLog


class Fe8DataSession:
    def __init__(self, project: ModProject, changelog: ChangeLog):
        self.project = project
        self.changelog = changelog
        self.path = project.extracted_dir / "files" / "FE8Data.bin"
        self.data: bytes = b""
        self.fe8: Optional[fe8data.Fe8Data] = None
        self.labels_by_prefix: dict = {}
        self.dirty = False
        self._listeners: list[Callable[[object], None]] = []
        #: run after every save (the workspace re-indexes: records may have been added or removed)
        self.on_saved: list[Callable[[], None]] = []
        self.load()

    @property
    def available(self) -> bool:
        return self.fe8 is not None

    def load(self) -> None:
        if self.path.exists():
            self.data = self.path.read_bytes()
            self.reparse()
            self.dirty = False

    def reparse(self) -> None:
        self.fe8 = fe8data.read_fe8data(self.data)
        self.labels_by_prefix = fe8data.label_index_by_prefix(self.fe8, self.data)

    def subscribe(self, listener: Callable[[object], None]) -> None:
        """``listener(source)`` runs after every change or save; ``source``
        is whoever made it (views skip their own changes)."""
        self._listeners.append(listener)

    def changed(self, source: object = None) -> None:
        """Call after patching ``data``: reparses, marks unsaved, notifies."""
        self.reparse()
        self.dirty = True
        self._notify(source)

    def save(self) -> None:
        """Write the file (keeping the extracted one in ``originals/``). Raises OSError."""
        self.project.write_keeping_original(self.path, self.data)
        self.dirty = False
        self.changelog.append("FE8Data.bin", "Saved character/class/item/skill/terrain data")
        self._notify(None)
        for callback in list(self.on_saved):
            callback()

    def revert(self) -> None:
        """Drop every unsaved edit: read the file again and tell every view."""
        self.load()
        self._notify(None)

    def character_index(self, pid: str) -> Optional[int]:
        if self.fe8 is None:
            return None
        for c in self.fe8.characters:
            if c.pid == pid:
                return c.index
        return None

    def _notify(self, source: object) -> None:
        for listener in list(self._listeners):
            try:
                listener(source)
            except Exception:  # noqa: BLE001 - a dead view must not block the others
                pass
