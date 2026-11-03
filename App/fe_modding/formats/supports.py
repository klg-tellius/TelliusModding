"""Supports, bonds and affinities in ``FE8Data.bin`` (Path of Radiance).

Four pieces of data drive the support system; all of them live in
``FE8Data.bin`` and are found through the container's symbol table:

``RelianceData`` - the support lists. A count word, then one variable-length
block per character::

    +0  ptr   owner PID
    +4  u32   slot count (the game reads the low byte)
    +8  slot count x 8-byte slots:
            +0 ptr  partner PID (0 = empty slot)
            +4 u8   C threshold
            +5 u8   B threshold
            +6 u8   A threshold
            +7 u8   unused (0)

The loader (``resolve_reliance_partner_references``) stores each block's
address at ``CharacterData+0x50`` and turns partner PIDs into character
pointers. A unit's support points live at ``unit+0x214+slot`` (10 bytes,
saved with the unit), so a slot's *index* is what a save remembers: removing
a partner leaves an empty slot rather than shifting the others, as the
vanilla lists do.

Points and ranks: at the end of a chapter every player unit on the map gains
1 point with each partner also on the map, unless it already can rank up
(points equal to a threshold) or either unit has 5 support stars. Rank is
``points > C`` -> C, ``> B`` -> B, ``> A`` -> A. Viewing the conversation in
the base adds the final point to both units. Stars: C=1, B=2, A=3, at most 5
per unit.

``KiznaData`` - bonds. A count word, then 12-byte records ended by a zero
word::

    +0 ptr PID 1   +4 ptr PID 2   +8 u8 kind   +9 s8 value   +10 2 bytes 0

Kind 1: while the two units stand next to each other (same army), each gets
``value`` Critical. Kind 2: while PID 2 stands next to PID 1, the opponent's
Critical against PID 2 is 0.

``DivineData`` - the affinity table: a count word (9), then 12-byte records
``name ptr, 8 signed bytes``. Bytes 0-5 are Attack, Defence, Hit, Avoid,
Critical and Critical avoid per support rank; bytes 6-7 are unused. The
index of an affinity is fixed by the executable (``get_affinity_index``):
0 none, 1 fire, 2 thunder, 3 wind, 4 water, 5 dark, 6 light, 7 heaven,
8 telius (shown as Earth).

Affinity of a character: the pointer at character record ``+0x14`` names
one of those strings.

Combat bonus (``apply_support_combat_bonus``): for every partner of the same
army within 3 tiles, add ``rank x`` the unit's affinity row and ``rank x`` the
partner's affinity row; after all partners, halve each total (rounding toward
minus infinity) and add it to the unit's battle Attack, Defence, Hit, Avoid,
Critical and Critical avoid.

Research reference: ``research/SUPPORT_NOTES.md``.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass, field
from typing import Optional

from . import fe8data

HEADER_SIZE = fe8data.HEADER_SIZE

#: Affinity strings in executable index order (index 0 is "no affinity").
AFFINITY_KEYS = ["none", "fire", "thunder", "wind", "water", "dark", "light", "heaven", "telius"]
#: The names the player sees.
AFFINITY_NAMES = ["None", "Fire", "Thunder", "Wind", "Water", "Dark", "Light", "Heaven", "Earth"]
#: The six bonus bytes of an affinity row, in order.
BONUS_NAMES = ["Attack", "Defence", "Hit", "Avoid", "Critical", "Crit avoid"]
RANK_NAMES = ["-", "C", "B", "A"]

#: Support points are kept in 10 bytes per unit (``unit+0x214``); a list
#: longer than that would overwrite the next unit field.
MAX_SLOTS = 10
#: Support stars a unit may hold (C=1, B=2, A=3).
MAX_STARS = 5

BOND_CRIT = 1
BOND_NO_CRIT = 2
BOND_KIND_NAMES = {BOND_CRIT: "Critical bonus when adjacent", BOND_NO_CRIT: "Cannot be critted next to PID 1"}

CHARACTER_AFFINITY_OFFSET = 0x14


@dataclass
class SupportSlot:
    partner: Optional[str]  # PID, None for an empty slot
    c: int
    b: int
    a: int
    pad: int = 0

    @property
    def empty(self) -> bool:
        return self.partner is None


@dataclass
class SupportList:
    owner: str  # PID
    slots: list = field(default_factory=list)  # list[SupportSlot]

    def slot_of(self, pid: str) -> int:
        for i, s in enumerate(self.slots):
            if s.partner == pid:
                return i
        return -1


@dataclass
class Bond:
    pid1: str
    pid2: str
    kind: int
    value: int
    tail: bytes = b"\x00\x00"


@dataclass
class AffinityRow:
    key: str  # the string the table names ("fire")
    bonus: list  # 8 signed ints; 0-5 are BONUS_NAMES


# -- low-level container helpers ------------------------------------------------

def _u32(data, offset: int) -> int:
    return struct.unpack_from(">I", data, offset)[0]


def _symbol(data: bytes, name: str) -> int:
    """Absolute file offset of a named symbol."""
    return fe8data.section_start(data, name)


def _label(data, ptr: int) -> Optional[str]:
    return fe8data._resolve(bytes(data), ptr) if ptr else None


def _label_ptr(data: bytes, label: str) -> int:
    ptr = fe8data._label_offset(data, label)
    if ptr is None:
        raise ValueError(f"Label {label!r} is not in FE8Data.bin.")
    return ptr


_replace_section = fe8data.replace_section


# -- RelianceData (support lists) ------------------------------------------------

def _reliance_span(data: bytes) -> tuple[int, int, int]:
    start = _symbol(data, "RelianceData")
    count = _u32(data, start)
    o = start + 4
    for _ in range(count):
        o += 8 + 8 * (_u32(data, o + 4) & 0xFF)
    return start, count, o


def read_support_lists(data: bytes) -> list[SupportList]:
    start, count, _end = _reliance_span(data)
    lists = []
    o = start + 4
    for _ in range(count):
        owner = _label(data, _u32(data, o))
        n = _u32(data, o + 4) & 0xFF
        slots = []
        for j in range(n):
            e = o + 8 + 8 * j
            c, b, a, pad = data[e + 4:e + 8]
            slots.append(SupportSlot(_label(data, _u32(data, e)), c, b, a, pad))
        lists.append(SupportList(owner or "", slots))
        o += 8 + 8 * n
    return lists


def validate_support_lists(lists: list[SupportList]) -> list[str]:
    """Problems that would break the game (errors) or behave oddly
    (warnings), as readable lines starting with ``Error:``/``Warning:``."""
    problems = []
    by_owner = {}
    for sl in lists:
        if sl.owner in by_owner:
            problems.append(f"Error: {sl.owner} has two support lists; the game uses the last one.")
        by_owner[sl.owner] = sl
    for sl in lists:
        if len(sl.slots) > MAX_SLOTS:
            problems.append(f"Error: {sl.owner} has {len(sl.slots)} slots; a unit stores points for {MAX_SLOTS}.")
        seen = set()
        for s in sl.slots:
            if s.empty:
                continue
            if s.partner in seen:
                problems.append(f"Error: {sl.owner} lists {s.partner} twice.")
            seen.add(s.partner)
            if not (s.c < s.b < s.a < 255):
                problems.append(f"Error: {sl.owner} / {s.partner}: thresholds must rise (C < B < A < 255).")
            other = by_owner.get(s.partner)
            back = other.slots[other.slot_of(sl.owner)] if other and other.slot_of(sl.owner) >= 0 else None
            if back is None:
                problems.append(
                    f"Error: {s.partner} does not list {sl.owner}; ranking up this pair writes outside the "
                    "partner's support points.")
            elif (back.c, back.b, back.a) != (s.c, s.b, s.a) and sl.owner < s.partner:
                problems.append(
                    f"Warning: {sl.owner} / {s.partner} thresholds differ between the two lists "
                    f"({s.c}/{s.b}/{s.a} vs {back.c}/{back.b}/{back.a}); each unit ranks by its own.")
    return problems


def write_support_lists(data: bytes, lists: list[SupportList]) -> bytes:
    """Return ``data`` with ``RelianceData`` rebuilt from ``lists``. Refuses
    lists with errors (see :func:`validate_support_lists`)."""
    errors = [p for p in validate_support_lists(lists) if p.startswith("Error")]
    if errors:
        raise ValueError("\n".join(errors))
    block = bytearray(struct.pack(">I", len(lists)))
    pointers = []
    for sl in lists:
        pointers.append(len(block))
        block += struct.pack(">II", _label_ptr(data, sl.owner), len(sl.slots))
        for s in sl.slots:
            if s.empty:
                block += struct.pack(">I", 0)
            else:
                pointers.append(len(block))
                block += struct.pack(">I", _label_ptr(data, s.partner))
            block += bytes([s.c & 0xFF, s.b & 0xFF, s.a & 0xFF, s.pad & 0xFF])
    _start, _count, end = _reliance_span(data)
    return _replace_section(data, "RelianceData", end, bytes(block), pointers)


# -- pair-level editing (keeps both lists in step) -------------------------------

def pairs(lists: list[SupportList]) -> list[tuple[str, str, SupportSlot]]:
    """Every support pair once, as ``(pid_a, pid_b, slot of pid_a)``."""
    result, done = [], set()
    for sl in lists:
        for s in sl.slots:
            if s.empty:
                continue
            key = frozenset((sl.owner, s.partner))
            if key in done:
                continue
            done.add(key)
            result.append((sl.owner, s.partner, s))
    return result


def _list_for(lists: list[SupportList], pid: str, create: bool) -> Optional[SupportList]:
    for sl in lists:
        if sl.owner == pid:
            return sl
    if not create:
        return None
    sl = SupportList(pid, [])
    lists.append(sl)
    return sl


def set_pair(lists: list[SupportList], pid_a: str, pid_b: str, c: int, b: int, a: int) -> None:
    """Add or change the pair ``pid_a``/``pid_b`` in both lists. A new
    partner takes the first empty slot (its saved points are always 0),
    otherwise a new slot at the end."""
    if pid_a == pid_b:
        raise ValueError("A character cannot support itself.")
    for owner, partner in ((pid_a, pid_b), (pid_b, pid_a)):
        sl = _list_for(lists, owner, create=True)
        i = sl.slot_of(partner)
        if i < 0:
            i = next((k for k, s in enumerate(sl.slots) if s.empty), -1)
            if i < 0:
                if len(sl.slots) >= MAX_SLOTS:
                    raise ValueError(f"{owner} already has {MAX_SLOTS} support slots.")
                sl.slots.append(SupportSlot(None, 0, 1, 2))
                i = len(sl.slots) - 1
        sl.slots[i] = SupportSlot(partner, c, b, a)


def remove_pair(lists: list[SupportList], pid_a: str, pid_b: str) -> None:
    """Empty the pair's slot in both lists (slot indices, and so saves, stay
    valid). Empty slots keep vanilla's filler thresholds 0/1/2."""
    for owner, partner in ((pid_a, pid_b), (pid_b, pid_a)):
        sl = _list_for(lists, owner, create=False)
        if sl is None:
            continue
        i = sl.slot_of(partner)
        if i >= 0:
            sl.slots[i] = SupportSlot(None, 0, 1, 2)


# -- KiznaData (bonds) -----------------------------------------------------------

def _kizna_span(data: bytes) -> tuple[int, int]:
    start = _symbol(data, "KiznaData")
    o = start + 4
    while _u32(data, o):
        o += 12
    return start, o + 4


def read_bonds(data: bytes) -> list[Bond]:
    start, end = _kizna_span(data)
    bonds = []
    for o in range(start + 4, end - 4, 12):
        bonds.append(Bond(_label(data, _u32(data, o)) or "", _label(data, _u32(data, o + 4)) or "",
                          data[o + 8], struct.unpack_from(">b", data, o + 9)[0], bytes(data[o + 10:o + 12])))
    return bonds


def write_bonds(data: bytes, bonds: list[Bond]) -> bytes:
    for bd in bonds:
        if bd.kind not in BOND_KIND_NAMES:
            raise ValueError(f"Bond {bd.pid1}/{bd.pid2}: kind must be 1 or 2.")
        if not bd.pid1 or not bd.pid2:
            raise ValueError("A bond needs two characters.")
    block = bytearray(struct.pack(">I", len(bonds)))
    pointers = []
    for bd in bonds:
        pointers += [len(block), len(block) + 4]
        block += struct.pack(">IIBb", _label_ptr(data, bd.pid1), _label_ptr(data, bd.pid2), bd.kind, bd.value)
        block += bytes(bd.tail[:2]).ljust(2, b"\x00")
    block += bytes(4)
    _start, end = _kizna_span(data)
    return _replace_section(data, "KiznaData", end, bytes(block), pointers)


# -- DivineData (affinity bonuses) -----------------------------------------------

def read_affinities(data: bytes) -> list[AffinityRow]:
    start = _symbol(data, "DivineData")
    rows = []
    for i in range(_u32(data, start)):
        o = start + 4 + 12 * i
        rows.append(AffinityRow(_label(data, _u32(data, o)) or "", list(struct.unpack_from(">8b", data, o + 4))))
    return rows


def patch_affinity_bonus(data: bytes, index: int, bonus: list) -> bytes:
    """Overwrite the bonus bytes of affinity ``index`` (6 or 8 values,
    -128..127). The names and their order are fixed by the executable."""
    start = _symbol(data, "DivineData")
    if not 0 <= index < _u32(data, start):
        raise ValueError(f"No affinity {index}.")
    values = list(bonus) + read_affinities(data)[index].bonus[len(bonus):]
    out = bytearray(data)
    struct.pack_into(">8b", out, start + 4 + 12 * index + 4, *values[:8])
    return bytes(out)


# -- character affinity ---------------------------------------------------------

def character_affinity(data: bytes, index: int) -> int:
    """Affinity index (see :data:`AFFINITY_KEYS`) of character record ``index``."""
    off = fe8data.table_start(data, "character") + index * fe8data.CHARACTER_RECORD_SIZE
    key = _label(data, _u32(data, off + CHARACTER_AFFINITY_OFFSET))
    return AFFINITY_KEYS.index(key) if key in AFFINITY_KEYS else 0


def patch_character_affinity(data: bytes, index: int, affinity: int) -> bytes:
    off = fe8data.table_start(data, "character") + index * fe8data.CHARACTER_RECORD_SIZE
    out = bytearray(data)
    value = 0 if affinity == 0 else _label_ptr(data, AFFINITY_KEYS[affinity])
    fe8data._pack_pointer(out, off + CHARACTER_AFFINITY_OFFSET, value)
    return bytes(out)


# -- helpers for display -----------------------------------------------------------

def rank_for_points(slot: SupportSlot, points: int) -> int:
    """0 none, 1 C, 2 B, 3 A - the executable's ``get_support_rank_level``."""
    if points <= slot.c:
        return 0
    if points <= slot.b:
        return 1
    return 2 if points <= slot.a else 3


def pair_bonus(rows: list[AffinityRow], affinity_a: int, affinity_b: int, rank: int) -> list[int]:
    """Bonus one unit gets from one partner at ``rank`` (six values). With
    several partners in range the game sums the doubled values first and
    halves once, so totals can exceed the sum of these."""
    return [(rank * (rows[affinity_a].bonus[i] + rows[affinity_b].bonus[i])) >> 1 for i in range(6)]
