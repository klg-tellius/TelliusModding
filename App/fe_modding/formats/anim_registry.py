"""Read and write ``FE8Anim.bin`` - the map-model registry (Path of Radiance).

Each record names one ``AID_`` animation set (a map model holding one weapon
type) and says which ``ymu/`` folder holds it. The file is also bundled in
``system.cmp``; the game reads it from there (see ``project.py``).

**Container**: the standard GameCube data container - a 0x20-byte header
(file size, data size, pointer count, symbol count), a data section, a list
of data-relative offsets of every pointer field, and a symbol table (one
symbol, ``AnimData``, at data offset 0). The data section is a record count,
the records, then the pool of every string the records point at, sorted and
unique. Pointers are data-relative (add ``common.HEADER_SIZE`` for a file
offset). :func:`build_anim_registry` rebuilds the vanilla file byte for byte.

**Record** (20 bytes; the engine copies it into a 20-byte runtime record in
``load_master_game_database`` and registers it by name, so order does not
matter and records can be appended):

- ``+0x00`` pointer to the ``AID_`` name: a character's or class's base
  animation ID plus a weapon suffix (``_N``, ``_SW``, ``_AX``, ``_HA``,
  ``_SP``, ``_JA``, ``_BW``; ``WEAPON_SUFFIXES``). The engine builds the
  name with ``"%s%s"`` from the unit's base ID (``FE8Data.bin`` character
  ``aid_unpromoted``/``aid_promoted``) and the weapon suffix.
- ``+0x04`` pointer to the ``ymu/`` folder name, ending in ``/``.
- ``+0x08`` weapon type (``WEAPON_ANIM_TYPES``, the index into
  ``WEAPON_SUFFIXES``).
- ``+0x09`` blend weight: when a map unit switches animation the engine
  cross-fades over 16 frames up to 20, rising linearly to 32 frames at 40
  and above (armour 40, dragons 60); a second use times a step at
  ``weight * 0.6`` frames, at least 8.
- ``+0x0A`` always 0; ``+0x0B`` undecoded (signed, nearly one value per
  folder, positive on fliers; no reader found).
- ``+0x0C`` four texture numbers, one per army (player, enemy, other, ally):
  the engine loads ``ymu/<folder>tex_<n>.tpl`` for the unit's army
  (``format_texture_path_indexed``). Generic classes use four colours
  (``fighter/``: 32, 97, 162, 227); named characters repeat one number
  (``AID_FIGHTER_BO_*``: 4, 4, 4, 4). Every number on the disc names an
  existing ``tex_N.tpl``.
- ``+0x10`` animation mask: bit *n* set when the folder has the action
  ``MAP_ACTIONS[n]`` for this weapon (``<action><suffix>.ga``, loose or in
  ``pack.cmp``). An action whose bit is clear plays ``tackle`` instead.
  Every set bit on the disc has its file.

Character tags in AID names (``AID_KNIGHT_KE_N``, ``AID_FIGHTER_BO_AX``) are
per-character sets; ``zdbx/jobList.dbx`` confirms the same overrides for
battle models (see ``zdbx.py``).
"""

from __future__ import annotations

import re
import struct
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from .common import HEADER_SIZE

RECORD_SIZE = 0x14
SYMBOL_NAME = b"AnimData"

# Weapon type (record +0x08) - the index into the engine's suffix table.
WEAPON_ANIM_TYPES: dict[int, str] = {
    0: "unarmed",
    1: "sword",
    2: "axe",
    3: "hand_axe",
    4: "spear",
    5: "javelin",
    6: "bow",
}
WEAPON_SUFFIXES = ("_N", "_SW", "_AX", "_HA", "_SP", "_JA", "_BW", "_EX")

# Bit order of the animation mask (record +0x10), from the engine's action table.
MAP_ACTIONS = (
    "wait", "move", "atk1", "atk2", "crit", "rod", "tackle", "escape", "ready",
    "damage", "trans", "dead", "magic1", "magic2", "crit2", "move2", "event",
)

ARMIES = ("player", "enemy", "other", "ally")

_CHARACTER_TAG_RE = re.compile(r"^AID_[A-Z0-9]+_([A-Z]{2})_[A-Z]{1,3}$")


@dataclass(frozen=True)
class AnimRecord:
    aid_name: str  # e.g. "AID_KNIGHT_SW"
    class_folder: str  # e.g. "knight/" - a ymu/ subfolder name
    weapon_type: int  # +0x08 - see WEAPON_ANIM_TYPES
    blend_weight: int  # +0x09 - animation cross-fade weight: 16 frames up to 20, 32 from 40 (heavier units blend slower)
    body_type: int  # +0x0B - undecoded (signed; nearly one value per folder, positive on fliers); no reader found
    texture_ids: tuple[int, int, int, int]  # +0x0C - tex_N.tpl per army (ARMIES order)
    animation_mask: int  # +0x10 - bit n = MAP_ACTIONS[n] exists
    address: int = 0  # file offset of the record when read

    @property
    def weapon_type_name(self) -> str:
        return WEAPON_ANIM_TYPES.get(self.weapon_type, f"unknown_{self.weapon_type}")

    @property
    def base_aid(self) -> str:
        """The name without its weapon suffix - what a character record stores."""
        suffix = WEAPON_SUFFIXES[self.weapon_type] if self.weapon_type < len(WEAPON_SUFFIXES) else ""
        return self.aid_name[: -len(suffix)] if suffix and self.aid_name.endswith(suffix) else self.aid_name

    @property
    def actions(self) -> list[str]:
        return [name for bit, name in enumerate(MAP_ACTIONS) if self.animation_mask >> bit & 1]

    @property
    def character_tag(self) -> Optional[str]:
        """The 2-letter character tag in aid_name, if it has one (e.g. "KE" in AID_KNIGHT_KE_N)."""
        match = _CHARACTER_TAG_RE.match(self.aid_name)
        return match.group(1) if match else None


def _read_cstring(data: bytes, addr: int) -> str:
    end = data.index(b"\x00", addr)
    return data[addr:end].decode("ascii", errors="replace")


def read_anim_registry(data: bytes) -> list[AnimRecord]:
    (record_count,) = struct.unpack(">I", data[HEADER_SIZE : HEADER_SIZE + 4])
    records = []
    for i in range(record_count):
        base = HEADER_SIZE + 4 + i * RECORD_SIZE
        aid_ptr, folder_ptr = struct.unpack(">II", data[base : base + 8])
        weapon, b1, _b2, b3 = data[base + 8 : base + 12]
        (mask,) = struct.unpack(">I", data[base + 0x10 : base + 0x14])
        records.append(
            AnimRecord(
                aid_name=_read_cstring(data, aid_ptr + HEADER_SIZE),
                class_folder=_read_cstring(data, folder_ptr + HEADER_SIZE),
                weapon_type=weapon,
                blend_weight=b1,
                body_type=b3,
                texture_ids=tuple(data[base + 12 : base + 16]),
                animation_mask=mask,
                address=base,
            )
        )
    return records


def read_anim_registry_path(path: Path | str) -> list[AnimRecord]:
    return read_anim_registry(Path(path).read_bytes())


def build_anim_registry(records: list[AnimRecord]) -> bytes:
    """Build an ``FE8Anim.bin`` from records (vanilla records give the vanilla file)."""
    strings = sorted({s.encode("ascii") for r in records for s in (r.aid_name, r.class_folder)})
    pool_start = 4 + len(records) * RECORD_SIZE
    offsets = {}
    pool = bytearray()
    for s in strings:
        offsets[s] = pool_start + len(pool)
        pool += s + b"\x00"
    data = bytearray(struct.pack(">I", len(records)))
    pointers = []
    for i, r in enumerate(records):
        base = 4 + i * RECORD_SIZE
        pointers += [base, base + 4]
        data += struct.pack(">II", offsets[r.aid_name.encode("ascii")], offsets[r.class_folder.encode("ascii")])
        data += bytes((r.weapon_type, r.blend_weight, 0, r.body_type)) + bytes(r.texture_ids)
        data += struct.pack(">I", r.animation_mask)
    data += pool
    data += bytes(-len(data) % 4)
    tail = struct.pack(f">{len(pointers)}I", *pointers) + struct.pack(">II", 0, 0) + SYMBOL_NAME + b"\x00"
    size = HEADER_SIZE + len(data) + len(tail)
    header = struct.pack(">4I", size, len(data), len(pointers), 1) + bytes(16)
    return header + bytes(data) + tail
