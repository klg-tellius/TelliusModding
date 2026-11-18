"""Conversation Room lists (Radiant Dawn): ``conversationroom.bin``
(see :mod:`fe_modding.formats.fe10_conversation_room`)."""

from __future__ import annotations

from pathlib import Path

from ..formats import fe10_conversation_room as cr
from ..game_profile import files_root_of
from .record_tables_editor import Column, RecordTablesEditor, TableSpec


class ConversationRoomEditor(RecordTablesEditor):
    display_name = "Conversation Room"
    subject = "Conversation Room lists"
    help_text = ("The Extras Conversation Room's two orders: the chapters (by chapter) and the characters "
                 "(by character). The conversations themselves, with the chapter and the speakers of "
                 "each, are on the Conversation Lists page (FE10Conversation.cms). A conversation whose "
                 "chapter or character is not listed here may not appear in that order.")

    def load_tables(self) -> list[TableSpec]:
        self._path = Path(files_root_of(self._project)) / "conversationroom.bin"
        self._room = cr.read_conversation_room(self._path.read_bytes())
        return [
            TableSpec("chapters", "Chapters", self._room.chapters,
                      [Column("value", "Chapter ID", width=160, note="As the chapter scripts name it (C0105).")],
                      new_row=lambda: cr.ListItem("C0000")),
            TableSpec("characters", "Characters", self._room.characters,
                      [Column("value", "PID", width=200, note="OTHER closes the list in retail.")],
                      new_row=lambda: cr.ListItem("PID_")),
        ]

    def build_files(self) -> dict[Path, bytes]:
        return {self._path: cr.build_conversation_room(self._room)}
