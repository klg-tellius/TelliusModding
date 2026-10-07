"""CPU-player data - ``cp_data.bin`` ("CP" = computer player).

The file holds everything the enemy/NPC AI reads: the *AI scripts*
(``SEQ_*``), the movement-scoring weight tables (``MTYPE_*``), the
heal-behaviour thresholds, the waypoint/target tables those scripts point at
(``TBL_*``), and the id lists that map a save-file byte back to a name.
It is *not* support data. It is the same "labeled section" container as the
shop files (:mod:`shop`): a 0x20-byte header (file size, relocation-table
offset, relocation count, section count), a body, a pool of NUL-terminated
label strings, the relocation table (body offset of every pointer word), a
section table of (address, name offset) pairs sorted by name, and the
section names. The engine registers every section name in its global hash
table (``load_relocatable_resource``) so the dispo ``seq_attack`` /
``seq_move`` / ``seq_heal`` / ``mtype`` keys and the script externCalls
``UnitSetCpAttackSeq`` etc. resolve a section by name.

A body word is a number, a pointer to a pool label (``str``) or a pointer
to another section's first word (:class:`SectionRef`).

Sections (US PoR: 134), in file order:

``CP_DataHead`` (9 words)
    ``0``, build timestamp, author, then the default ``TBL_STEALITEMS``,
    ``MTYPE_NORMAL``, ``SEQ_NOATTACK``, ``SEQ_NOMOVE``, ``SEQ_NOHEAL`` and
    ``ATK_SEQID_LIST``. Never looked up by name by the game.
``TBL_STEALITEMS``
    Items the AI thieves may steal (``IID_`` labels; mostly skill scrolls and
    drops). Zero-terminated; the game finds it by name.
``TBL_PID_<x>``
    Zero-terminated ``PID_`` list. A script entry's ``e`` slot points at it
    to restrict a target filter to those characters.
``TBL_MAPnn_ROUTE*``
    Waypoint list: one word per point, ``(x << 16) | y``, ended by
    ``0xFFFF0000`` (x = -1). Used by script opcode 216.
``MTYPE_<x>`` (6 words)
    Tile-scoring weights of an AI movement type, see :class:`MType`.
``SEQ_<x>`` attack / move scripts and ``SEQ_*HEAL*`` heal records, see
:class:`Entry`, :class:`Script` and :class:`HealRecord`.
``ATK_SEQID_LIST`` / ``MOV_SEQID_LIST`` / ``HEAL_SEQID_LIST`` / ``MTYPE_TABLEID_LIST``
    Zero-terminated name lists. A record's *position* in its list is the id
    byte saved in the save file (``serialize AI block``, ``FUN_8003c3cc``):
    it must equal the id stored in the record.

An AI script is a list of 28-byte entries (7 words ``op a b c d e f``). The
first two are a header (``op -2`` with the script's own name in ``e``;
``op -1`` with the id in ``a``). From then on the engine runs the entry
selected by a per-unit program counter (``actor+0x250`` attack,
``+0x251`` move): it looks the opcode up in a table of 52 handlers
(``0x80273000``), the handler does its work and normally moves the counter
on by one. ``op 0`` entries are *labels* (``c`` = label id); jumps go to
the first ``op 0`` entry with the wanted ``c``; label 0 / ``d = 0`` means
"back to the first entry". :mod:`cp_ops` describes every opcode and
:mod:`cp_ai_lang` turns a script into readable code and back.

``parse_cp_data()`` reads a file into a :class:`CpDocument`;
``build_cp_data()`` lays it out again (byte-identical for the vanilla file).
"""

from __future__ import annotations

import struct
from dataclasses import dataclass, field as dataclass_field
from typing import NamedTuple, Optional, Union

from .common import HEADER_SIZE, decode_str, read_cstring_table
from .cp_ops import OPS


class SectionRef(NamedTuple):
    """A pointer to the first word of the named section."""

    name: str


#: A body word: a raw u32, a pool label, or a pointer to a section.
Value = Union[int, str, SectionRef]

_LABEL_CODEC = "shift_jis"

# -- script opcodes -------------------------------------------------------------------

#: opcode -> (short name, summary); the full typed description is :mod:`cp_ops`.
OPCODES: dict[int, tuple[str, str]] = {op: (spec.key, spec.summary) for op, spec in OPS.items()}

OP_ENTRY_WORDS = 7
OP_ENTRY_BYTES = 4 * OP_ENTRY_WORDS
SCRIPT_HEADER_ENTRIES = 2

# -- section kinds --------------------------------------------------------------------

ID_LISTS = {
    "ATK_SEQID_LIST": "attack",
    "MOV_SEQID_LIST": "move",
    "HEAL_SEQID_LIST": "heal",
    "MTYPE_TABLEID_LIST": "mtype",
}
HEAD_SECTION = "CP_DataHead"
STEAL_SECTION = "TBL_STEALITEMS"
MTYPE_WORDS = 6
HEAL_WORDS = 2

# MTYPE byte layout, offsets within the 24-byte record (offset 0..3 = name pointer).
MTYPE_FIELDS = (
    (4, "id", "Position in MTYPE_TABLEID_LIST (saved in the save file)"),
    (5, "damage_dealt", "Weight (32nds) of the expected damage, damage x hit^1.75 (x2 on a double attack); "
                        "+50 when the weighted value reaches the target's HP"),
    (6, "hp_ratio", "Weight of how wounded the target already is, 10 x (max HP - HP) / max HP"),
    (7, "adjacent_foes", "Weight of the units of the attacker's side around the attack tile "
                         "(the (dx, dy, weight) table at 0x80272F44)"),
    (8, "class_bonus", "Weight of the per-class bonuses below (summed over the target's class flags)"),
    (9, "turn_number", "Weight x current turn number"),
    (10, "skill_bonus", "Weight of the target's Provoke (+50) or Shade (-50)"),
    (11, "damage_taken", "Weight of the expected counter damage, hit^2.125 (subtracted; +50 when it reaches "
                         "the attacker's HP)"),
    (12, "terrain", "Weight of the attack tile's threat (ai_threat_map), subtracted"),
    (13, "hp_after_ratio", "Weight of how wounded the attacker already is, 10 x (max HP - HP) / max HP "
                           "(subtracted)"),
    (14, "class_flag_0", "Bonus when the target's class flag bit 0 is set"),
    (15, "class_flag_1", "Bonus for class flag bit 1"),
    (16, "class_flag_2", "Bonus for class flag bit 2"),
    (17, "class_flag_3", "Bonus for class flag bit 3"),
    (18, "class_flag_4", "Bonus for class flag bit 4"),
    (19, "class_flag_5", "Bonus for class flag bit 5"),
    (20, "class_flag_6", "Bonus for class flag bit 6"),
    (21, "class_flag_7", "Bonus for class flag bit 7"),
    (22, "class_flag_8", "Bonus for class flag bit 8"),
    (23, "class_flag_10", "Bonus for class flag bit 10"),
)
MTYPE_FIELD_NAMES = tuple(f[1] for f in MTYPE_FIELDS)


@dataclass
class Section:
    name: str
    words: list[Value] = dataclass_field(default_factory=list)


@dataclass
class CpDocument:
    sections: list[Section]
    pool: list[str]  # label strings in file order (pool is rebuilt compactly on build)
    header_tail: bytes = bytes(16)  # header bytes 0x10..0x1F, all zero in vanilla

    def section(self, name: str) -> Optional[Section]:
        for s in self.sections:
            if s.name == name:
                return s
        return None

    def names(self, prefix: str = "") -> list[str]:
        return [s.name for s in self.sections if s.name.startswith(prefix)]


# -- parse / build --------------------------------------------------------------------

def parse_cp_data(data: bytes) -> CpDocument:
    total, pool_end, relocation_count, section_count = struct.unpack_from(">4I", data, 0)
    if total != len(data):
        raise ValueError("cp_data: header size doesn't match the file")
    pool_end += HEADER_SIZE
    table_start = pool_end + 4 * relocation_count
    entries = [struct.unpack_from(">II", data, table_start + 8 * i) for i in range(section_count)]
    names = read_cstring_table(data[table_start + 8 * section_count:])
    relocations = {struct.unpack_from(">I", data, pool_end + 4 * i)[0] for i in range(relocation_count)}

    name_of = {address: decode_str(names.get(offset, b"")) for address, offset in entries}
    addresses = sorted(name_of)
    targets = {struct.unpack_from(">I", data, HEADER_SIZE + r)[0] for r in relocations}
    non_section = [t for t in targets if t not in name_of]
    pool_start = min(non_section) if non_section else pool_end - HEADER_SIZE

    pool, by_offset, position = [], {}, pool_start
    for raw in data[HEADER_SIZE + pool_start:pool_end].split(b"\x00"):
        if raw:
            label = raw.decode(_LABEL_CODEC)
            pool.append(label)
            by_offset[position] = label
        position += len(raw) + 1

    def word(offset: int) -> Value:
        (value,) = struct.unpack_from(">I", data, HEADER_SIZE + offset)
        if offset in relocations:
            if value in name_of:
                return SectionRef(name_of[value])
            if value in by_offset:
                return by_offset[value]
            raise ValueError(f"Pointer at {offset:#x} points at neither a section nor a label")
        return value

    sections = []
    for i, address in enumerate(addresses):
        end = addresses[i + 1] if i + 1 < len(addresses) else pool_start
        sections.append(Section(name_of[address], [word(o) for o in range(address, end, 4)]))
    return CpDocument(sections, pool, data[0x10:HEADER_SIZE])


def build_cp_data(doc: CpDocument) -> bytes:
    """Lay a document out as a cp_data file. Sections keep the document's order;
    the pool keeps the labels still used, in order, then new ones in order of
    first use."""
    addresses: dict[str, int] = {}
    body_words: list[Value] = []
    for section in doc.sections:
        if section.name in addresses:
            raise ValueError(f"Two sections are called {section.name}")
        addresses[section.name] = 4 * len(body_words)
        body_words += section.words

    used = list(dict.fromkeys(w for w in body_words if isinstance(w, str)))
    in_use = set(used)
    pool_labels = [label for label in doc.pool if label in in_use]
    kept = set(pool_labels)
    pool_labels += [label for label in used if label not in kept]

    pool_start = 4 * len(body_words)
    offsets, pool = {}, bytearray()
    for label in pool_labels:
        offsets[label] = pool_start + len(pool)
        pool += label.encode(_LABEL_CODEC) + b"\x00"
    pool += bytes(-len(pool) % 4)

    body, relocations = bytearray(), []
    for i, value in enumerate(body_words):
        if isinstance(value, SectionRef):
            if value.name not in addresses:
                raise ValueError(f"Pointer to missing section {value.name}")
            relocations.append(4 * i)
            value = addresses[value.name]
        elif isinstance(value, str):
            relocations.append(4 * i)
            value = offsets[value]
        body += struct.pack(">I", value & 0xFFFFFFFF)

    ordered = sorted(doc.sections, key=lambda s: s.name.encode("ascii"))
    names, name_offsets = bytearray(), []
    for section in ordered:
        name_offsets.append(len(names))
        names += section.name.encode("ascii") + b"\x00"
    table = b"".join(struct.pack(">II", addresses[s.name], o) for s, o in zip(ordered, name_offsets))

    pool_end = HEADER_SIZE + pool_start + len(pool)
    tail = b"".join(struct.pack(">I", r) for r in relocations) + table + bytes(names)
    header = struct.pack(">4I", pool_end + len(tail), pool_end - HEADER_SIZE, len(relocations), len(ordered))
    return header + doc.header_tail + bytes(body) + bytes(pool) + tail


# -- scripts --------------------------------------------------------------------------

def _signed(value: int) -> int:
    return value - (1 << 32) if value & 0x80000000 else value


@dataclass
class Entry:
    """One 28-byte script entry. ``a``..``f`` are the words at +4..+0x18;
    ``e`` and ``f`` may be labels or section pointers (PID/IID/SID names,
    ``TBL_*`` tables), the others numbers."""

    op: int
    a: Value = 0
    b: Value = 0
    c: Value = 0
    d: Value = 0
    e: Value = 0
    f: Value = 0

    def words(self) -> list[Value]:
        return [self.op & 0xFFFFFFFF, self.a, self.b, self.c, self.d, self.e, self.f]

    @classmethod
    def from_words(cls, words: list[Value]) -> "Entry":
        op = words[0]
        if isinstance(op, int):
            op = _signed(op)
        return cls(op, *words[1:7])

    @property
    def op_name(self) -> str:
        return OPCODES.get(self.op, (f"OP_{self.op}", ""))[0]


@dataclass
class Script:
    """An attack or move AI script (a ``SEQ_*`` section with entries)."""

    name: str
    script_id: int
    entries: list[Entry]  # the body, after the two header entries
    header_extra: list[Value] = dataclass_field(default_factory=list)  # unused header words, kept as read


def is_script_section(section: Section) -> bool:
    return (section.name.startswith("SEQ_") and len(section.words) >= 2 * OP_ENTRY_WORDS
            and len(section.words) % OP_ENTRY_WORDS == 0
            and section.words[0] == 0xFFFFFFFE)


def is_heal_section(section: Section) -> bool:
    return section.name.startswith("SEQ_") and len(section.words) == HEAL_WORDS and isinstance(section.words[0], str)


def read_script(section: Section) -> Script:
    if not is_script_section(section):
        raise ValueError(f"{section.name} is not an AI script")
    entries = [Entry.from_words(section.words[i:i + OP_ENTRY_WORDS])
               for i in range(0, len(section.words), OP_ENTRY_WORDS)]
    header, ident, body = entries[0], entries[1], entries[2:]
    if header.op != -2 or ident.op != -1 or header.e != section.words[5]:
        raise ValueError(f"{section.name}: bad script header")
    return Script(section.name, int(ident.a), body)


def write_script(section: Section, script: Script) -> None:
    section.words = ([0xFFFFFFFE, 0, 0, 0, 0, script.name, 0]
                     + [0xFFFFFFFF, script.script_id, 0, 0, 0, 0, 0])
    for entry in script.entries:
        section.words += entry.words()


def script_labels(script: Script) -> list[int]:
    return [e.c for e in script.entries if e.op == 0]


@dataclass
class HealRecord:
    name: str
    record_id: int
    retreat_below: int  # enter retreat when HP% < this
    resume_at: int  # leave retreat once HP% >= this
    priority: int  # non-zero: try healing items first


def read_heal(section: Section) -> HealRecord:
    if not is_heal_section(section):
        raise ValueError(f"{section.name} is not a heal record")
    packed = section.words[1]
    return HealRecord(section.name, (packed >> 24) & 0xFF, (packed >> 16) & 0xFF, (packed >> 8) & 0xFF, packed & 0xFF)


def write_heal(section: Section, record: HealRecord) -> None:
    section.words = [record.name,
                     (record.record_id & 0xFF) << 24 | (record.retreat_below & 0xFF) << 16
                     | (record.resume_at & 0xFF) << 8 | (record.priority & 0xFF)]


@dataclass
class MType:
    name: str
    values: dict[str, int]  # MTYPE_FIELD_NAMES -> signed byte (``id`` unsigned)


def is_mtype_section(section: Section) -> bool:
    return section.name.startswith("MTYPE_") and len(section.words) == MTYPE_WORDS and section.name != "MTYPE_TABLEID_LIST"


def read_mtype(section: Section) -> MType:
    if not is_mtype_section(section):
        raise ValueError(f"{section.name} is not an MTYPE table")
    raw = b"".join(struct.pack(">I", w) for w in section.words[1:])  # bytes at record offsets 4..23
    values = {}
    for offset, key, _ in MTYPE_FIELDS:
        byte = raw[offset - 4]
        values[key] = byte if key == "id" else (byte - 256 if byte >= 128 else byte)
    return MType(section.name, values)


def write_mtype(section: Section, mtype: MType) -> None:
    raw = bytearray(20)
    for offset, key, _ in MTYPE_FIELDS:
        raw[offset - 4] = mtype.values[key] & 0xFF
    section.words = [mtype.name] + list(struct.unpack(">5I", bytes(raw)))


def read_list(section: Section) -> list[Value]:
    """A zero-terminated pointer list's items."""
    words = section.words
    if not words or words[-1] != 0:
        raise ValueError(f"{section.name} isn't zero-terminated")
    return list(words[:-1])


def write_list(section: Section, items: list[Value]) -> None:
    section.words = list(items) + [0]


def read_route(section: Section) -> list[tuple[int, int]]:
    """A waypoint table's (x, y) points."""
    points = []
    for word in section.words:
        if word >> 16 == 0xFFFF:
            return points
        points.append((word >> 16, word & 0xFFFF))
    raise ValueError(f"{section.name} has no 0xFFFF terminator")


def write_route(section: Section, points: list[tuple[int, int]]) -> None:
    section.words = [(x << 16) | y for x, y in points] + [0xFFFF0000]


def is_route_section(section: Section) -> bool:
    return section.name.startswith("TBL_MAP")


def is_pid_table(section: Section) -> bool:
    return section.name.startswith("TBL_PID_")


# -- id lists -------------------------------------------------------------------------

def _id_list(doc: CpDocument, list_name: str) -> list[str]:
    section = doc.section(list_name)
    return [str(w) for w in read_list(section)] if section else []


def attack_scripts(doc: CpDocument) -> list[str]:
    return _id_list(doc, "ATK_SEQID_LIST")


def move_scripts(doc: CpDocument) -> list[str]:
    return _id_list(doc, "MOV_SEQID_LIST")


def heal_records(doc: CpDocument) -> list[str]:
    return _id_list(doc, "HEAL_SEQID_LIST")


def mtype_tables(doc: CpDocument) -> list[str]:
    return _id_list(doc, "MTYPE_TABLEID_LIST")


def id_problems(doc: CpDocument) -> list[str]:
    """Where a record's stored id disagrees with its position in its id list."""
    problems = []
    for list_name, kind in ID_LISTS.items():
        for index, name in enumerate(_id_list(doc, list_name)):
            section = doc.section(name)
            if section is None:
                problems.append(f"{list_name}[{index}] names a missing section {name}")
                continue
            if kind in ("attack", "move"):
                stored = read_script(section).script_id
            elif kind == "heal":
                stored = read_heal(section).record_id
            else:
                stored = read_mtype(section).values["id"]
            if stored != index:
                problems.append(f"{name}: id {stored} but position {index} in {list_name}")
    return problems


def add_to_id_list(doc: CpDocument, list_name: str, name: str) -> int:
    """Append a section to an id list and return its new id."""
    section = doc.section(list_name)
    items = read_list(section)
    items.append(name)
    write_list(section, items)
    return len(items) - 1


def rename_section(doc: CpDocument, old: str, new: str) -> None:
    """Rename a section and every reference to it (own name word, id lists, pointers)."""
    if doc.section(new) is not None:
        raise ValueError(f"{new} already exists")
    for s in doc.sections:
        s.words = [new if (w == old and isinstance(w, str)) else (SectionRef(new) if w == SectionRef(old) else w)
                   for w in s.words]
        if s.name == old:
            s.name = new
