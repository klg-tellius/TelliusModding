"""Endings (Radiant Dawn): ``FE10Epilogue.bin``, the per-character ending lines
(see :mod:`fe_modding.formats.fe10_epilogue`)."""

from __future__ import annotations

from pathlib import Path

from ..formats import fe10_epilogue as ep
from ..game_profile import files_root_of
from .message_reference import epilogue_texts
from .record_tables_editor import Column, RecordTablesEditor, TableSpec


class EpilogueEditor(RecordTablesEditor):
    display_name = "Endings"
    subject = "Endings"
    help_text = ("The epilogue after the final chapter: one entry per character, in the order they are shown. "
                 "A surviving unit gets its ending; a lost one the wounded or killed line. Three optional "
                 "alternatives replace the ending, tried in order: an A support with the active support "
                 "partner, another unit alive, another unit killed. Texts are MEP_ messages in "
                 "Mess/e_epilogue.m; the character's title line is its MNPID_ message there.")

    def load_tables(self) -> list[TableSpec]:
        self._path = Path(files_root_of(self._project)) / "FE10Epilogue.bin"
        self._data = ep.read_epilogues(self._path.read_bytes())
        return [TableSpec("entries", "Endings", self._data.entries, [
            Column("pid", "PID", width=150),
            Column("ending", "Ending", "key", width=170),
            Column("wounded", "If wounded", "key", width=140),
            Column("killed", "If killed", "key", width=140),
            Column("support_partner", "A-support partner", "optional", width=140),
            Column("support_ending", "Ending with A support", "key", width=170),
            Column("alive_partner", "If alive: unit", "optional", width=130),
            Column("alive_ending", "Ending if that unit lives", "key", width=170),
            Column("killed_partner", "If killed: unit", "optional", width=130),
            Column("killed_ending", "Ending if that unit died", "key", width=170),
            Column("always", "Always listed", "int", width=60,
                   note="Non-zero lists the entry even when the unit is not in the army."),
        ], new_row=lambda: ep.Epilogue("PID_", "MEP_ALIVE_"))]

    def message_texts(self) -> dict[str, str]:
        return epilogue_texts(self._project)

    def problems(self) -> list[str]:
        return ep.check(self._data, texts=set(self._texts) or None)

    def build_files(self) -> dict[Path, bytes]:
        return {self._path: ep.build_epilogues(self._data)}
