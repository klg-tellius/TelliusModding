"""Class introductions (Radiant Dawn): ``FE10Intro.bin``
(see :mod:`fe_modding.formats.fe10_intro`). The pictures (``intro/*.cms``) are on the Class Intro
Pictures page."""

from __future__ import annotations

from pathlib import Path

from ..formats import fe10_intro as fi
from ..game_profile import files_root_of
from .message_reference import language_texts
from .record_tables_editor import Column, RecordTablesEditor, TableSpec


class ClassIntroEditor(RecordTablesEditor):
    display_name = "Class Introductions"
    subject = "Class introductions"
    help_text = ("The Extras class introductions: each record stages one class in battle (unit, class, "
                 "backdrop, sky, camera, weapon and the motions it plays) beside its picture "
                 "(intro/<picture>.cms) and description (MS_INTRO_ messages in intro.m). The group is "
                 "the list the record belongs to; the scene starts at the first record of a group.")

    def load_tables(self) -> list[TableSpec]:
        files = Path(files_root_of(self._project))
        self._path = files / "FE10Intro.bin"
        self._data = fi.read_intros(self._path.read_bytes())
        self._pictures = files / "intro"
        return [TableSpec("entries", "Classes", self._data.entries, [
            Column("group", "Group", "int", width=50),
            Column("jid", "Class (JID)", width=150),
            Column("unit", "Battle unit", width=130),
            Column("picture", "Picture", width=110, note="intro/<picture>.cms"),
            Column("text", "Description", "key", width=170),
            Column("scenery", "Backdrop", width=110),
            Column("sky", "Sky", width=70),
            Column("camera", "Camera", width=70),
            Column("weapon", "Weapon", width=90),
            Column("motion_list", "Motions", "optional", width=160, note="Up to five, separated by commas."),
            Column("frames", "+0x28", "int", width=50),
        ], new_row=lambda: fi.ClassIntro(0, "剣士一般", "JID_", "bg0104平地2", "曇り", "近距離", "blade",
                                        "MS_INTRO_", motions=["構え"]))]

    def message_texts(self) -> dict[str, str]:
        return language_texts(self._project, "intro")

    def problems(self) -> list[str]:
        return [f"{e.jid}: intro/{e.picture}.cms does not exist." for e in self._data.entries
                if e.picture and not (self._pictures / f"{e.picture}.cms").is_file()]

    def build_files(self) -> dict[Path, bytes]:
        return {self._path: fi.build_intros(self._data)}
