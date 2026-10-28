"""The fields of a chapter's ``ChapterData`` record, described once per game for the one Chapter data form.

Path of Radiance reads them from ``FE8Data.bin`` (:mod:`formats.fe8data`), Radiant Dawn from
``FE10Data.cms`` (:mod:`formats.fe10data`). :class:`gui.stats_editor.ChapterRecordPanel` and Game
Data › Chapters build the same form from these sections on both games; a field only one game has is
an extra row of its section ("Same + fields").

The game adapters (:mod:`game_adapter`) pick the functions of their game: ``*_sections`` lists the
form, ``*_value`` gives what a field shows ("" for an empty label) and ``*_write`` stores what the user
typed (the form turns number fields into ints within ``low``/``high`` first).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional

from .formats import fe8data, fe10data

#: Field kinds: a free text or label (``prefix`` makes it a message key with its text beside it),
#: a label from ``options``, one number, or a row of numbers (``names`` head the columns; the key
#: holds ``{i}``).
TEXT, CHOICE, NUMBER, BYTES = "text", "choice", "number", "bytes"


@dataclass(frozen=True)
class ChapterField:
    label: str
    key: str
    kind: str = TEXT
    note: str = ""
    prefix: Optional[str] = None
    #: ("Open in Music ›", ("asset", "music")): a button opening the route plus the field's value.
    link: Optional[tuple] = None
    options: tuple = ()
    names: tuple = ()
    header: bool = True
    name_help: dict = field(default_factory=dict)
    low: int = 0
    high: int = 255


@dataclass(frozen=True)
class ChapterSection:
    title: str
    fields: tuple
    note: str = ""


# -- Path of Radiance -------------------------------------------------------------------------------

_POR_LISTS = {"objective": "objectives", "hard_objective": "hard_objectives",
              "maniac_objective": "maniac_objectives", "enemy_bonus_level": "enemy_bonus_levels",
              "trial_turn_grade": "trial_turn_grades", "trial_loss_grade": "trial_loss_grades",
              "trial_score_grade": "trial_score_grades"}
_SLOTS = ("Goal", "Goal second line", "Defeat condition", "Defeat second line")


def _por_record(data: bytes, index: int) -> fe8data.ChapterRecord:
    return fe8data.read_chapter_data(data)[index]


def por_sections(data: bytes, index: int) -> list[ChapterSection]:
    record = _por_record(data, index)
    title = (ChapterField("Title", "title_text", note="The Japanese release stores the displayed title directly "
                                                       "in this record.")
             if fe8data.japanese_chapter_layout(data) else ChapterField("Title key", "title_key", prefix="MCT"))
    identity = (title,
                ChapterField("Chapter id", "chapter_id", NUMBER,
                             "Scripts change to a chapter by this id; 90 and up are the trial maps."),
                ChapterField("Map", "map_name", note="The map folder: zmap/<name>/."),
                ChapterField("Script", "script", note="The event script: Scripts/<name>.cmb."),
                ChapterField("Message file", "message", note="The text file: Mess/<name>.m; empty: none."),
                ChapterField("Map music", "bgm", link=("Open in Music ›", ("asset", "music"))))
    objectives = [ChapterField(label, f"objective{k}", prefix="ML_" if k >= 2 else "MW_")
                  for k, label in enumerate(_SLOTS)]
    for mode, key in (("Hard", "hard_objective"), ("Maniac", "maniac_objective")):
        objectives += [ChapterField(f"{mode}: {_SLOTS[slot].lower()}", f"{key}{k}",
                                    prefix="ML_" if slot == 3 else "MW_") for k, slot in enumerate((0, 1, 3))]
    backgrounds = ("Open in Backgrounds ›", ("asset", "backgrounds"))
    scenes = (ChapterField("Base background", "base_background", link=backgrounds),
              ChapterField("Conversation background", "talk_background", link=backgrounds),
              ChapterField("Class-change scene map", "scene_map"),
              ChapterField("Class-change scene sky", "scene_sky", note="A Battle scenes sky name."))
    grades = ("A", "B", "C", "D")
    levels = (
        ChapterField("Enemy levels +", "enemy_bonus_level{i}", BYTES,
                     "Levels added to auto-levelled enemies on each difficulty (capped at level 20).",
                     names=fe8data.DIFFICULTY_NAMES[:len(record.enemy_bonus_levels)],
                     name_help={"Easy": "Easy (the North American mode) has no deployment or shop files of its "
                                        "own: it uses Normal's. Only this bonus differs."}),
        ChapterField("Turns", "trial_turn_grade{i}", BYTES, "Trial maps only: the most turns for each grade.",
                     names=grades),
        ChapterField("Units lost", "trial_loss_grade{i}", BYTES,
                     "Trial maps only: the most units lost for each grade.", names=grades, header=False),
        ChapterField("Kills", "trial_score_grade{i}", BYTES,
                     "Trial maps only: the fewest kills for each grade (fewer than D gives E).", names=grades,
                     header=False))
    return [ChapterSection("Identity and files", identity), ChapterSection("Objectives (text keys)", tuple(objectives)),
            ChapterSection("Scenes", scenes), ChapterSection("Enemy levels and trial grades", levels)]


def por_value(data: bytes, index: int, key: str) -> str:
    record = _por_record(data, index)
    match = re.fullmatch(r"([a-z_]+?)(\d+)", key)
    if match and match.group(1) in _POR_LISTS:
        value = getattr(record, _POR_LISTS[match.group(1)])[int(match.group(2))]
    else:
        value = getattr(record, key)
    return "" if value is None else str(value)


def por_write(data: bytes, index: int, key: str, value) -> bytes:
    return fe8data.patch_chapter_field(data, index, key, value)


# -- Radiant Dawn ---------------------------------------------------------------------------------

def _rd_used(data: bytes, key: str) -> tuple:
    """The values the chapter records already use for ``key``, offered in its combo box (any label is accepted)."""
    return tuple(sorted({r.values.get(key) for r in fe10data.read_table(data, "chapter")} - {None}))


def rd_sections(data: bytes, index: int) -> list[ChapterSection]:
    identity = (ChapterField("Title key", "title", prefix="MCT"),
                ChapterField("Chapter id", "cid", note="The record's ID: C<chapter page id> (C0101, C0407a, CFINAL)."),
                ChapterField("Number", "number", NUMBER,
                             "The chapter's number: setting the current chapter looks the record up by it (0-55: "
                             "the story, 80-83: the tutorials). Each record needs its own."),
                ChapterField("Map", "map", note="The map folder: zmap/<name>/."),
                ChapterField("Script", "script", note="The event script: Scripts/<name>.cmb."),
                ChapterField("Message file", "messages", note="The text files: Mess/<name>.m and e_<name>.m."))
    objectives = []
    for d in range(3):
        mode = f"Difficulty {d + 1}"
        objectives += [ChapterField(f"{mode}: goal", f"win_{d}", prefix="MW_"),
                       ChapterField(f"{mode}: goal second line", f"win2_{d}", prefix="MW_")]
        objectives += [ChapterField(f"{mode}: defeat {i + 1}", f"lose{i}_{d}", prefix="ML_") for i in range(4)]
    scenery = tuple(n for n in dict.fromkeys(fe10data.battle_scenery_names(data)) if n)
    scenes = (ChapterField("Base background", "base_scene", CHOICE, "A rect RID (Game Data › Rect RIDs).",
                           options=_rd_used(data, "base_scene")),
              ChapterField("Second scene", "scene_2", CHOICE, options=_rd_used(data, "scene_2")),
              ChapterField("Battle background", "battle_background", CHOICE,
                           "A BattleTerrName entry (Game Data › Battle scenery).", options=scenery),
              ChapterField("Weather", "weather", CHOICE, options=_rd_used(data, "weather")),
              ChapterField("Affinity", "affinity", CHOICE, options=_rd_used(data, "affinity")),
              ChapterField("Lord", "lord", CHOICE,
                           options=tuple(fe10data.labels_with_prefix(data, "PID_")),
                           link=("Open character ›", ("character",))))
    settings = (ChapterField("Gold account", "gold_account", NUMBER,
                             "Which party's gold account the chapter uses."),
                ChapterField("Convoy", "convoy", NUMBER, "Which party's convoy the chapter uses."),
                ChapterField("Unknown +0x88", "unknown_88", NUMBER),
                *(ChapterField(f"Unknown +0x{o:02X}", f"unknown_{o:02x}", NUMBER,
                               "Attached records (C0401a/b) have 128 here: the advance only enters them on "
                               "their route." if o == 0x8D else "") for o in range(0x8B, 0x90)))
    return [ChapterSection("Identity and files", identity), ChapterSection("Objectives (text keys)", tuple(objectives)),
            ChapterSection("Scenes", scenes),
            ChapterSection("Parties", settings, "Bytes whose meaning is not known yet edit as numbers.")]


def rd_value(data: bytes, index: int, key: str) -> str:
    value = fe10data.record(data, "chapter", index).values.get(key)
    return "" if value is None else str(value)


def rd_write(data: bytes, index: int, key: str, value) -> bytes:
    if key == "number":
        others = [r.index for r in fe10data.read_table(data, "chapter")
                  if r.values.get("number") == value and r.index != index]
        if others:
            raise ValueError(f"chapter record {others[0]} already has the number {value}")
    elif key == "cid":
        value = (value or "").strip()
        if not value:
            raise ValueError("a chapter record needs an ID")
        others = [r.index for r in fe10data.read_table(data, "chapter")
                  if r.values.get("cid") == value and r.index != index]
        if others:
            raise ValueError(f"chapter record {others[0]} already has the ID {value}")
    elif isinstance(value, str):
        value = value.strip() or None
    return fe10data.patch_field(data, "chapter", index, key, value)
