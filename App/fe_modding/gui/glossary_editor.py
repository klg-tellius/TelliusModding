"""Glossary (Radiant Dawn): ``dictionary.bin`` entries and their ``dictionaryF.bin`` unlock flags
(see :mod:`fe_modding.formats.fe10_dictionary`)."""

from __future__ import annotations

from pathlib import Path

from ..formats import fe10_dictionary as fd
from ..game_profile import files_root_of
from .message_reference import language_texts
from .record_tables_editor import Column, RecordTablesEditor, TableSpec

FLAG_COLUMNS = [Column("name", "Unlock flag", width=180, linked=True,
                       note="Scripts set it by this name; the prefix picks the save's bit array."),
                Column("bit", "Bit", "int", width=50, linked=True)]


class GlossaryEditor(RecordTablesEditor):
    display_name = "Glossary"
    subject = "Glossary"
    help_text = ("The glossary under Info: people, the relation chart's lines and frames, and terms. Each entry "
                 "has an unlock flag in dictionaryF.bin (entry n of a table unlocks record n), set by the "
                 "event scripts; the bits live in the save's system record. Keys are messages in "
                 "Mess/e_dic.m. Chart positions are screen pixels on the relation chart; -1000 keeps a "
                 "person off it.")

    def load_tables(self) -> list[TableSpec]:
        files = files_root_of(self._project)
        self._dict_path = Path(files) / "dictionary.bin"
        self._flags_path = Path(files) / "dictionaryF.bin"
        self._dictionary = fd.read_dictionary(self._dict_path.read_bytes())
        self._flags = fd.read_dictionary_flags(self._flags_path.read_bytes())
        d, f = self._dictionary, self._flags

        def flag(prefix):
            return lambda row: fd.FlagEntry(0, prefix)

        return [
            TableSpec("people", "People", d.people, [
                Column("pid", "PID", width=160),
                Column("nation", "Nation key", "key", width=140),
                Column("text", "Description key", "key", width=150),
                Column("x", "Chart x", "int", width=60),
                Column("y", "Chart y", "int", width=60),
                Column("faded", "Faded portrait", "int", width=95,
                       note="Non-zero draws the chart portrait faded (retail: the characters dead by now)."),
            ] + FLAG_COLUMNS, new_row=lambda: fd.Person("PID_", None, "MDIC_"), linked=f.tables[0],
                new_linked=flag("DF_人物"),
                note="Records with the same PID in a row are one entry: the game shows the last unlocked one."),
            TableSpec("relations", "Relations", d.relations, [
                Column("image", "Line image", "optional", width=200, note="Drawn as RID_<name> (RectRelationLine*)."),
                Column("image_x", "Image x", "int", width=60),
                Column("image_y", "Image y", "int", width=60),
                Column("label", "Label key", "key", width=120),
                Column("colour", "Label colour", "int", width=60, note="1 and 2 pick two other text colours."),
                Column("label_x", "Label x", "int", width=60),
                Column("label_y", "Label y", "int", width=60),
            ] + FLAG_COLUMNS, new_row=lambda: fd.Relation(None, 0, 0, "MDIL_", 2, 0, 0), linked=f.tables[1],
                new_linked=flag("DF_関係")),
            TableSpec("affiliations", "Affiliations", d.affiliations, [
                Column("frame", "Frame image", "optional", width=180, note="Drawn as RID_<name>."),
                Column("frame_x", "Frame x", "int", width=60),
                Column("frame_y", "Frame y", "int", width=60),
                Column("banner", "Banner / label key", "key", width=180),
                Column("label_x", "Label x", "int", width=60),
                Column("label_y", "Label y", "int", width=60),
            ] + FLAG_COLUMNS, new_row=lambda: fd.Affiliation(None, 0, 0, "MDIB_", 0, 0), linked=f.tables[2],
                new_linked=flag("DF_所属")),
            TableSpec("terms", "Terms", d.terms, [
                Column("name", "Name key", "key", width=160),
                Column("reading", "Reading key", "key", width=160),
                Column("text", "Description key", "key", width=160),
                Column("picture", "Picture", "optional", width=120),
            ] + FLAG_COLUMNS, new_row=lambda: fd.Term("MDIN_", "MDIR_", "MDIC_"), linked=f.tables[3],
                new_linked=flag("DF_用語")),
        ]

    def message_texts(self) -> dict[str, str]:
        return language_texts(self._project, "dic")

    def problems(self) -> list[str]:
        return fd.check(self._dictionary, self._flags)

    def build_files(self) -> dict[Path, bytes]:
        for index, table in enumerate(self._flags.tables):
            used = {e.bit for e in table if e.bit}
            for entry in table:
                if entry.bit == 0:  # a new entry: the next free bit
                    entry.bit = max(used, default=0) + 1
                    used.add(entry.bit)
        return {self._dict_path: fd.build_dictionary(self._dictionary),
                self._flags_path: fd.build_dictionary_flags(self._flags)}
