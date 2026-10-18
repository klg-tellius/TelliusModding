"""The project's ``sys/main.dol`` opened for editing: the model behind the Game Code page.

Every change is written to disk at once (atomically), like the other editors, since building
packages whatever is in ``extracted/``."""

from __future__ import annotations

import os
from pathlib import Path

from . import entries  # noqa: F401  (registers the catalog)
from .battle_window import GameFiles
from .catalog import CATALOG, Entry, Patch, Session, State, Status, Tunable
from .dol import Dol, DolError
from .versions import Identification, identify, read_boot_code


def _format(value) -> str:
    return f"{value:g}" if isinstance(value, (int, float)) else str(value)


class CodeEditor:
    def __init__(self, extracted_dir: Path | str, writer=None, original=None):
        """``writer(path, data)`` saves a file (the project's keeps an original copy);
        ``original(path)`` returns a file as extracted, or None (for patches that also edit files)."""
        self._writer = writer
        self._original = original
        self.extracted_dir = Path(extracted_dir)
        self.path = self.extracted_dir / "sys" / "main.dol"
        self.dol = Dol.open(self.path)
        from .extended_flag_runtime import BASE
        from .extended_flag_installation import RECEIPT_NAME
        self._extended_owned = (self.dol.has_section_at(BASE) or
                                (self.extracted_dir.parent / RECEIPT_NAME).exists())
        self.identification: Identification = identify(self.dol, read_boot_code(self.extracted_dir))
        self.session = Session(self.dol, self.identification.version, self._retail_reader())

    def _retail_reader(self):
        """Reads the retail main.dol: the project's kept original, or this file as opened when it
        is still retail (the first write keeps it as the original from then on)."""
        version = self.identification.version
        if version is None:
            return None
        retail = None
        if self.dol.sha1() == version.dol_sha1:
            retail = Dol(bytes(self.dol.data))
        elif self._original is not None and (kept := self._original(self.path)) is not None:
            candidate = Dol(kept)
            retail = candidate if candidate.sha1() == version.dol_sha1 else None
        if retail is None:
            return None

        def read(address: int, length: int) -> bytes | None:
            try:
                return retail.read(address, length)
            except DolError:
                return None
        return read

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
        self._patch_files(patch, enabled)
        files = " (with zdbx.cmp and its textures)" if patch.files is not None else ""
        return f"{patch.name}: {'on' if enabled else 'off'}{files}"

    @property
    def game_files(self) -> GameFiles:
        def write(path: Path, data: bytes) -> None:
            if self._writer is not None:
                self._writer(path, data)
            else:
                path.write_bytes(data)
        return GameFiles(self.extracted_dir, write, self._original or (lambda _path: None))

    def _patch_files(self, patch: Patch, enabled: bool) -> None:
        """The disc files a patch needs besides main.dol (installed again when already on)."""
        if patch.files is not None and self.supported:
            install, remove = patch.files
            (install if enabled else remove)(self.game_files)

    def set_value(self, tunable, value: float) -> str:
        old = self.status(tunable).value
        self.session.set_tunable(tunable, value)
        self._save()
        if tunable.choices:
            def _format_choice(v):
                index = int(v - tunable.minimum) if isinstance(v, (int, float)) else -1
                return tunable.choices[index] if 0 <= index < len(tunable.choices) else _format(v)
            return f"{tunable.name}: {_format_choice(old)} -> {_format_choice(value)}"
        return f"{tunable.name}: {_format(old)} -> {_format(value)}"

    def reset(self, entry: Entry) -> str:
        self.session.reset(entry)
        self._save()
        if isinstance(entry, Patch):
            self._patch_files(entry, False)
        return f"{entry.name}: reset"

    def reset_all(self) -> int:
        changed = self.modified_entries()
        for entry in changed:
            self.session.reset(entry)
        self._save()
        for entry in changed:
            if isinstance(entry, Patch):
                self._patch_files(entry, False)
        return len(changed)

    def _drop_idle_hooks(self) -> None:
        """Take out hooks whose tunables are all back at their defaults (vanilla again)."""
        for hook in CATALOG.entries.values():
            if not (isinstance(hook, Patch) and hook.internal):
                continue
            users = [e for e in CATALOG.entries.values() if isinstance(e, Tunable) and hook in e.requires]
            if not users:
                continue        # managed by its own owner (the story flow table), not by tunables
            if self.session.patch_status(hook).state == State.APPLIED and all(
                    self.session.tunable_status(u).state == State.ORIGINAL for u in users):
                self.session.set_patch(hook, False)

    def save(self) -> None:
        """Write the DOL after an edit made through :attr:`session` (see ``chapter_flow``)."""
        self._save()

    def _save(self) -> None:
        self._drop_idle_hooks()
        if self._extended_owned:
            from .extended_flag_installation import inspect_runtime, RECEIPT_NAME, RuntimeState
            from ..formats.extended_flags import FlagLayout, MANIFEST_NAME
            root = self.extracted_dir.parent
            layout = FlagLayout.from_json((root / MANIFEST_NAME).read_text(encoding="utf-8"))
            receipt = (root / RECEIPT_NAME).read_text(encoding="utf-8")
            status = inspect_runtime(self.dol, self.version.code if self.version else None, layout, receipt)
            if status.state != RuntimeState.MATCHING:
                raise ValueError(f"This edit would invalidate the extended flag runtime: {status.detail}")
        if self._writer is not None:
            self._writer(self.path, bytes(self.dol.data))
            return
        partial = self.path.with_name(self.path.name + ".part")
        try:
            partial.write_bytes(bytes(self.dol.data))
            os.replace(partial, self.path)
        finally:
            partial.unlink(missing_ok=True)
