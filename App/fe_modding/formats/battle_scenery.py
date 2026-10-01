"""``zbg/<scenery>/param.dbx`` - per-scenery battle parameters (``zdbx.cmp``).

Each battle scenery (``zbg/<folder>``, listed by ``zdbx/bgList.dbx``'s
``TerrainList`` block: Japanese name -> folder) has one ``param.dbx`` with a
single ``class Param`` block:

- ``name``: the folder name.
- ``roomFlag``: 1 for indoor sceneries (rooms, passages, altars), else 0.
- ``footEffect``: the effect under the fighters' feet while they move.
- ``footSound``: the footstep sound.

The value meanings are read off which sceneries use them (a scenery's
footEffect/footSound are 0 on ships, bridges and floors, 1 on dirt, 2 in
rivers, seas and swamps, 3 on Daein's snowy ground and 4 on grass, villages
and forts); the engine's use of them is not traced further.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from . import dbx

NAME_RE = re.compile(r"^[A-Za-z0-9_]+$")
FOOT_EFFECTS = {0: "None", 1: "Dust (dirt)", 2: "Splash (water)", 3: "Snow", 4: "Grass"}
FOOT_SOUNDS = {0: "None", 1: "Dirt", 2: "Water", 3: "Snow", 4: "Grass"}
ROOM_FLAGS = {0: "Outdoors", 1: "Indoors"}
FIELDS = {"roomFlag": ROOM_FLAGS, "footEffect": FOOT_EFFECTS, "footSound": FOOT_SOUNDS}


class SceneryError(dbx.DbxError):
    pass


@dataclass(frozen=True)
class SceneryParam:
    name: str
    room_flag: int
    foot_effect: int
    foot_sound: int


def read_scenery(text: str) -> SceneryParam:
    try:
        block = dbx.parse(text).find("Param")
        return SceneryParam(block.name or "", int(block.get("roomFlag", "0")),
                            int(block.get("footEffect", "0")), int(block.get("footSound", "0")))
    except dbx.DbxError as exc:
        raise SceneryError("No Param block.") from exc
    except ValueError as exc:
        raise SceneryError(f"Bad number in Param block: {exc}") from exc


def set_scenery_field(text: str, field: str, value: int | str) -> str:
    """Set one ``Param`` field (a whole number from the field's table)."""
    if field not in FIELDS:
        raise SceneryError(f"Unknown scenery field {field!r}.")
    try:
        number = int(str(value).strip())
    except ValueError as exc:
        raise SceneryError(f"{field} must be a whole number.") from exc
    if number not in FIELDS[field]:
        raise SceneryError(f"{field} must be one of {sorted(FIELDS[field])}.")
    doc = dbx.parse(text)
    block = doc.find("Param")
    existing = next((f for f in block.fields if f.key == field), None)
    if existing is None:
        doc.add_field(block, field, str(number))
    else:
        doc.set_value(existing, str(number))
    return doc.text


def clone_scenery(text: str, new_name: str) -> str:
    """A ``param.dbx`` for a new scenery folder: ``name`` replaced, the rest kept."""
    if not NAME_RE.match(new_name):
        raise SceneryError("Scenery name must be letters, digits and underscores.")
    doc = dbx.parse(text)
    block = doc.find("Param")
    field = next((f for f in block.fields if f.key == "name"), None)
    if field is None:
        raise SceneryError("The Param block has no name.")
    doc.set_value(field, new_name)
    return doc.text


def terrain_labels(bg_list_text: str) -> dict[str, str]:
    """Scenery folder -> Japanese name, from ``zdbx/bgList.dbx``'s TerrainList."""
    try:
        block = dbx.parse(bg_list_text).find("TerrainList")
    except dbx.DbxError:
        return {}
    return {f.value.split()[0]: f.key for f in block.fields if f.key != "class" and f.value}
