"""Sound Tables (Radiant Dawn): the cue parameters and ``SND_*`` tables of ``Sound/sound_data*.cms``.

Tabs: each cue's playback parameters, each chapter's music (map, phases, preparations, base, unit
select), the battle themes (boss and pairing music), environment sounds and the map mixer, the
sounds the animation event codes play, and the sound group each chapter loads. Edits go through
:mod:`formats.fe10_sound_tables`; Save writes the file back through the project.
"""

from __future__ import annotations

from ..formats import fe8data, fe10_sound, fe10_sound_tables as st
from ..formats.common import HEADER_SIZE
from ..formats.record_fields import LABEL, Field
from .field_tables_panel import FieldTab, FieldTablesPanel

#: Which cue family each text field offers in its box.
_CUE_FIELDS = {"cue", "map0", "map1", "map2", "map3", "phase_player", "phase_enemy", "phase_third",
               "phase_fourth", "preparations", "base", "select"}
_COLUMNS = {
    "SND_MAP_BGM_DATA": ("chapter", "map0", "phase_player", "phase_enemy"),
    "SND_BATTLE_BGM_DATA": ("cue", "chapter", "pid1", "pid2"),
    "SND_ENV_DATA": ("map", "cue", "emitter_kind"),
    "SND_MAP_DATA": ("map", "mixer_a", "mixer_b"),
    "SND_SFX_MAYA_DATA": ("code", "cue"),
    "SND_CHAPTER_GROUP_DATA": ("chapter", "flag", "group"),
}


def _used(name: str, key: str):
    def values(data: bytes) -> list[str]:
        return sorted({row[key] for row in st.read_rows(data, name) if row[key]})
    return values


def _cues(prefixes: tuple[str, ...]):
    def values(data: bytes) -> list[str]:
        return sorted(c.name for c in fe10_sound.read_sound_data(data) if c.name.startswith(prefixes))
    return values


class Fe10SoundTablesEditor(FieldTablesPanel):
    display_name = "Sound tables"
    logical = "sound_data"
    intro = ("Sound/sound_data_en.cms (sound_data.cms on the Japanese disc). A cue names a BRSAR sound and how it "
             "plays; the tables say which cue each chapter, fight, map and animation event uses. Text boxes take a "
             "cue, chapter ID (C0101), map (bmap0101), PID or flag name; a name the file does not have yet is "
             "added. New music and sound cues are made on the Music and Sound Effects pages.")

    def tabs(self, data: bytes) -> list[FieldTab]:
        cue_names = [c.name for c in fe10_sound.read_sound_data(data)]
        tabs = [FieldTab(
            "cues", "Cue parameters", (Field("resource", 0x04, LABEL, "BRSAR sound",
                                             "Change it on the Music or Sound Effects page."),) + st.CUE_PARAMETERS,
            read=lambda d: [{"resource": c.resource, **st.read_fields(d, HEADER_SIZE + c.record_offset,
                                                                      st.CUE_PARAMETERS)}
                            for c in fe10_sound.read_sound_data(d)],
            write=lambda d, i, v: self._write_cue(d, i, v),
            columns=("resource", "kind", "volume", "max_plays"),
            label=lambda i, _row, names=cue_names: names[i] if i < len(names) else str(i),
            note="Volume, pitch, pans, sends, random variation and distance settings of every cue.")]
        exports = fe8data.symbol_offsets(data)
        for name, table in st.TABLES.items():
            if name not in exports:  # a file without the table shows the others
                continue
            choices = {}
            for f in table.fields:
                if f.kind != LABEL:
                    continue
                if f.key in _CUE_FIELDS:
                    music = name in ("SND_MAP_BGM_DATA", "SND_BATTLE_BGM_DATA")
                    choices[f.key] = _cues(("BGM_",) if music else ("SFX_", "SE_", "FF_", "VOICE_"))
                else:
                    choices[f.key] = _used(name, f.key)
            tabs.append(FieldTab(
                name, table.title, table.fields,
                read=lambda d, n=name: st.read_rows(d, n),
                write=lambda d, i, v, n=name: st.set_row(d, n, i, **v),
                columns=_COLUMNS.get(name, ()), note=f"{table.note} ({name})",
                add=lambda d, i, n=name: st.add_row(d, n, i),
                remove=lambda d, i, n=name: st.remove_row(d, n, i),
                choices=choices))
        return tabs

    @staticmethod
    def _write_cue(data: bytes, index: int, values: dict) -> bytes:
        if "resource" in values:
            raise ValueError("The BRSAR sound is changed on the Music or Sound Effects page.")
        name = fe10_sound.read_sound_data(data)[index].name
        return st.set_cue_parameters(data, name, **values)
