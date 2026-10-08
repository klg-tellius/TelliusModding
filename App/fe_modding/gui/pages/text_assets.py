"""Assets › Conversations and Assets › Scripts: every message file
(``Mess/*.m``) and every event script (``Scripts/*.cmb``) as a card.

A chapter's own file opens where its chapter page shows it: the Dialogue or
Script tab. A shared script (``startup.cmb``) opens in a chapter's Script tab
too, whose File box is made for it. A message file that is no chapter's
(``common.m``) has no chapter page, so it opens here, in the same editor the
Dialogue tab uses (route ``("asset", "conversations", file name)``). While a
game has no chapter pages (Radiant Dawn until its chapters are decoded), every
file opens here: scripts in the Script tab's editor (route ``("asset",
"scripts", file name)``)."""

from __future__ import annotations

import re
from pathlib import Path
from tkinter import ttk

from ... import chapters, script_sources
from ...formats import fe10_message
from ...game_profile import CHAPTERS, profile_of
from ..dialogue_editor import DialogueEditor
from ..editor_panel import EditorPanel
from ..script_editor import ScriptEditor
from ..widgets import Card, CardGrid, Link, ScrollFrame, section_header
from .chapters import open_script


def _chapter_file_re(project, extension: str) -> re.Pattern:
    """``c<id>.<extension>`` with the id pattern of the project's game."""
    return re.compile(rf"^c({profile_of(project).chapter_id_pattern})\.{extension}$", re.IGNORECASE)


def _chapter_key(chapter_id: str) -> str:
    """Compare ids across file kinds: ``01`` and ``1`` are one chapter, ``0407A`` and ``0407a`` too."""
    return (chapter_id.lstrip("0") or "0") if chapter_id.isdigit() else chapter_id.lower()


def message_files(project) -> list[tuple[Path, str | None]]:
    """``(path, chapter id or None)`` of every ``Mess/*.m``: chapters' in
    chapter order, then the others by name."""
    folder = project.extracted_dir / "files" / "Mess"
    ids = set(chapters.list_chapter_ids(project))
    return _ordered(project, folder.glob("*.m") if folder.is_dir() else (), _chapter_file_re(project, "m"), ids)


def script_files(project) -> list[tuple[Path, str | None]]:
    """``(path, chapter id or None)`` of every ``Scripts/*.cmb``, ordered like
    :func:`message_files`. A ``CNN.cmb`` whose chapter has no page (no
    ``cNN.m``) counts as shared."""
    folder = script_sources.scripts_dir(project)
    ids = set(chapters.list_chapter_ids(project))
    return _ordered(project, folder.glob("*.cmb") if folder.is_dir() else (), _chapter_file_re(project, "cmb"), ids)


def _ordered(project, paths, pattern: re.Pattern, chapter_ids: set[str]) -> list[tuple[Path, str | None]]:
    by_key = {_chapter_key(cid): cid for cid in chapter_ids}
    owned, shared = [], []
    for path in paths:
        match = pattern.match(path.name)
        cid = by_key.get(_chapter_key(match.group(1))) if match else None
        (owned if cid is not None else shared).append((path, cid))
    owned.sort(key=lambda entry: profile_of(project).chapter_sort_key(entry[1]))
    shared.sort(key=lambda entry: (entry[0].stem.lower() != "startup", entry[0].name.lower()))
    return owned + shared


class _FileList(EditorPanel):
    """A card per file, in two groups: the chapters' files, then the rest."""

    title = ""
    intro = ""
    shared_heading = ""

    def __init__(self, parent, shell):
        super().__init__(parent, style="Page.TFrame")
        self._shell = shell
        self._project = shell.project
        self._list = ScrollFrame(self, padding=(28, 12, 28, 28))
        self._list.pack(fill="both", expand=True)

    def show_list(self) -> None:
        body = self._list.body
        for child in body.winfo_children():
            child.destroy()
        ttk.Label(body, text=self.title, style="Title.TLabel").pack(anchor="w")
        ttk.Label(body, text=self.intro, style="Muted.TLabel", wraplength=900, justify="left").pack(
            anchor="w", pady=(2, 8))
        files = self.files()
        owned = [(p, cid) for p, cid in files if cid is not None]
        shared = [(p, cid) for p, cid in files if cid is None]
        if not files:
            ttk.Label(body, text="No files found. Extract the project first.", style="Muted.TLabel").pack(anchor="w")
        for heading, entries in (("Chapters", owned), (self.shared_heading, shared)):
            if not entries:
                continue
            section_header(body, heading, f"{len(entries)} file{'s' if len(entries) != 1 else ''}").pack(
                anchor="w", pady=(12, 8))
            grid = CardGrid(body, card_width=260)
            grid.pack(fill="x")
            for path, cid in entries:
                grid.add(path.name, self._card(grid, path, cid))
            grid.done()

    @property
    def showing_list(self) -> bool:
        return bool(self._list.winfo_manager())

    def _chapter_title(self, chapter_id: str) -> str:
        index = self._shell.index
        if index is not None and chapter_id in index.by_chapter:
            return index.by_chapter[chapter_id].title
        if getattr(self, "_titles", None) is None:  # no chapter index for this game yet: the titles alone
            try:
                self._titles = chapters.chapter_titles(self._project)
            except Exception:  # noqa: BLE001 - titles are cosmetic
                self._titles = {}
        return chapters.chapter_display_title(chapter_id, self._titles) if self._titles else f"Chapter {chapter_id}"

    def files(self) -> list[tuple[Path, str | None]]:
        raise NotImplementedError

    def _card(self, grid, path: Path, chapter_id: str | None) -> Card:
        raise NotImplementedError


class ConversationsPanel(_FileList):
    """Every message file. Its unsaved state is the hosted editor's."""

    title = "Conversations"
    intro = ("Every message file (Mess/). A chapter's file opens in its Dialogue tab; "
             "the others open here in the same editor.")
    shared_heading = "Other message files"

    def __init__(self, parent, shell):
        super().__init__(parent, shell)
        self._editor: DialogueEditor | None = None
        self._editor_frame = ttk.Frame(self, style="Page.TFrame")
        bar = ttk.Frame(self._editor_frame, style="Page.TFrame", padding=(16, 6, 16, 0))
        bar.pack(fill="x")
        Link(bar, "‹ All conversations", lambda: shell.navigate(("asset", "conversations"))).pack(side="left")
        self._file_label = ttk.Label(bar, text="", style="Muted.TLabel")
        self._file_label.pack(side="left", padx=(12, 0))

    @property
    def display_name(self) -> str:
        path = self._editor.current_path if self._editor is not None else None
        return f"Dialogue ({path.name})" if path is not None else "Dialogue"

    @property
    def dirty(self) -> bool:
        return self._editor is not None and self._editor.dirty

    def _confirm_discard(self) -> bool:
        return self._editor is None or self._editor.confirm_navigate_away()

    def save_changes(self) -> bool:
        return self._editor is None or self._editor.save_changes()

    def cleanup(self) -> None:
        if self._editor is not None:
            self._editor.cleanup()

    def files(self):
        return message_files(self._project)

    def _opens_here(self, chapter_id) -> bool:
        """A file without a chapter page opens in this panel: one that is no chapter's, or any file
        while the game has no chapter pages yet (Radiant Dawn until its chapters are decoded)."""
        return chapter_id is None or not profile_of(self._project).supports(CHAPTERS)

    def _card(self, grid, path, chapter_id):
        if self._opens_here(chapter_id):
            subtitle = "Not one chapter's: opens here" if chapter_id is None else f"Chapter {chapter_id}"
            if profile_of(self._project).message_dialect == "fe10":
                subtitle += f"  ·  {fe10_message.language_of(path.name)}"
            return Card(grid, title=path.name, subtitle=subtitle, width=260,
                        on_click=lambda: self._shell.navigate(("asset", "conversations", path.name)))
        index = self._shell.index
        count = len(index.messages_by_chapter.get(chapter_id, [])) if index is not None else 0
        return Card(grid, title=self._chapter_title(chapter_id), subtitle=f"{path.name}  ·  Disc {chapter_id}",
                    chips=(f"{count} messages",) if count else (), width=260,
                    on_click=lambda: self._shell.navigate(("chapter", chapter_id, "dialogue")))

    def show_list(self) -> None:
        self._editor_frame.pack_forget()
        self._list.pack(fill="both", expand=True)
        super().show_list()

    def open_file(self, name: str) -> bool:
        """Show the message file ``name`` (one that is no chapter's) in the
        hosted editor. False if there is no such file, or the editor kept
        another file's unsaved edits."""
        path = next((p for p, cid in self.files() if p.name == name and self._opens_here(cid)), None)
        if path is None:
            return False
        if self._editor is None:
            self._editor = DialogueEditor(self._editor_frame, self._project, self._shell.changelog)
            self._editor.pack(fill="both", expand=True, padx=16, pady=(0, 8))
        if self._editor.current_path != path:
            if not self._editor.confirm_navigate_away():
                return False
            self._editor.refresh_chapter_list()  # a file added since it was built
            self._editor.select_chapter(path)
        self._list.pack_forget()
        self._editor_frame.pack(fill="both", expand=True)
        self._file_label.configure(text=path.name)
        return True


class ScriptsPanel(_FileList):
    """Every event script; each opens in a chapter's Script tab, or here where
    the game has no chapter pages yet. Its unsaved state is the hosted editor's."""

    title = "Scripts"
    shared_heading = "Shared scripts"

    def __init__(self, parent, shell):
        super().__init__(parent, shell)
        self.editor: ScriptEditor | None = None
        self._editor_frame = ttk.Frame(self, style="Page.TFrame")
        bar = ttk.Frame(self._editor_frame, style="Page.TFrame", padding=(16, 6, 16, 0))
        bar.pack(fill="x")
        Link(bar, "‹ All scripts", lambda: shell.navigate(("asset", "scripts"))).pack(side="left")
        self._file_label = ttk.Label(bar, text="", style="Muted.TLabel")
        self._file_label.pack(side="left", padx=(12, 0))

    @property
    def intro(self) -> str:
        if self._hosts_all():
            return ("Every event script (Scripts/). Each one opens here in the script editor; startup.cmb holds "
                    "the helpers every chapter calls and the campaign flags.")
        return ("Every event script (Scripts/). A chapter's script opens in its Script tab; a shared one "
                "(startup.cmb) opens in the Script tab of the chapter you have open, where the File box lists it.")

    def _hosts_all(self) -> bool:
        """No chapter pages for this game yet (Radiant Dawn): every script opens in this panel."""
        return not profile_of(self._project).supports(CHAPTERS)

    @property
    def display_name(self) -> str:
        path = self.editor.current_path if self.editor is not None else None
        return f"Script ({path.name})" if path is not None else "Scripts"

    @property
    def dirty(self) -> bool:
        return self.editor is not None and self.editor.dirty

    def _confirm_discard(self) -> bool:
        return self.editor is None or self.editor.confirm_navigate_away()

    def save_changes(self) -> bool:
        return self.editor is None or self.editor.save_changes()

    def cleanup(self) -> None:
        if self.editor is not None:
            self.editor.cleanup()

    def files(self):
        return script_files(self._project)

    def show_list(self) -> None:
        self._editor_frame.pack_forget()
        self._list.pack(fill="both", expand=True)
        super().show_list()

    def open_file(self, name: str) -> bool:
        """Show the script ``name`` in the hosted editor (only where the game has no chapter
        pages). False if there is no such file, or the editor kept another file's unsaved edits."""
        path = next((p for p, _cid in self.files() if p.name.lower() == name.lower()), None)
        if path is None or not self._hosts_all():
            return False
        if self.editor is None:
            self.editor = ScriptEditor(self._editor_frame, self._project, self._shell.changelog)
            self.editor.pack(fill="both", expand=True, padx=16, pady=(0, 8))
        if self.editor.current_path != path and not self.editor.open_file(path):
            return False
        self._list.pack_forget()
        self._editor_frame.pack(fill="both", expand=True)
        self._file_label.configure(text=path.name)
        return True

    def _card(self, grid, path, chapter_id):
        if self._hosts_all():
            if chapter_id is None:
                what = "Shared helpers and campaign flags" if path.stem.lower() == "startup" else "Shared script"
            else:
                what = f"{self._chapter_title(chapter_id)}  ·  Disc {chapter_id}"
            return Card(grid, title=path.name, subtitle=what, width=260,
                        on_click=lambda: self._shell.navigate(("asset", "scripts", path.name)))
        if chapter_id is None:
            what = "Shared helpers and campaign flags" if path.stem.lower() == "startup" else "Shared script"
            return Card(grid, title=path.name, subtitle=what, width=260,
                        on_click=lambda: open_script(self._shell, path))
        return Card(grid, title=self._chapter_title(chapter_id), subtitle=f"{path.name}  ·  Disc {chapter_id}",
                    width=260, on_click=lambda: self._shell.navigate(("chapter", chapter_id, "script")))
