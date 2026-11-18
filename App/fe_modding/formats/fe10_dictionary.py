"""Radiant Dawn's glossary: ``dictionary.bin`` (entries) and ``dictionaryF.bin`` (unlock flags).

Both are :mod:`pool_file` files. RFEE01's loader ``load_dictionary_tables`` (``0x802639D0``)
walks ``dictionary.bin`` as five back-to-back tables, each a u32 count and fixed-size records:

* **categories** (8 bytes): the tab label key (``MDIK_PERSON``, ``MDIK_WORD``) and a zero word;
  the tab drawer ``0x802643B8`` shows exactly two.
* **people** (20 bytes): PID, nation text key (``MDICN_...`` or none), description key
  (``MDIC_...``), s16 x and y on the relation chart (``-1000`` keeps the entry off the chart),
  and a word that, when non-zero, draws the chart portrait in mode 2 (``0x802652DC``; retail
  sets it on characters who are dead by Radiant Dawn). Consecutive records with the same PID
  are one glossary entry: the list builder ``0x80263E5C`` keeps the last unlocked one.
* **relations** (24 bytes on the US and European discs, 20 on the Japanese one): the chart
  line image (drawn as ``RID_<name>`` from the ``window/RectRelationLine*`` rects) and its s16
  x, y, the label key (``MDIL_...``), the label colour (1 and 2 pick text colours 0x2F and 0x30,
  anything else 0x2E), and the s16 x, y the label is centred on (``0x80265574``). The 24-byte
  records insert the Japanese label point before the translated one (+0x10); RFEE01 reads
  only the point at +0x14.
* **affiliations** (16 bytes): the frame image (``RID_<name>``; ``枠デイン`` and ``枠ゴルドア``
  switch to ``RID_<name>2`` until system flag 0x18C0 bit 31 is set) and its s16 x, y, then the
  banner image / label key and the s16 x, y it is centred on (``0x80265840``).
* **terms** (16 bytes): name (``MDIN_``), reading (``MDIR_``) and description (``MDIC_``) keys
  and a picture name: ``用語<nation>`` on the nine nation terms, zero elsewhere (no reader of it
  was traced).

A ``0xFFFFFFFF`` word follows the last table. The keys are message IDs in the system message
file; the PIDs are characters in ``FE10Data.cms``.

``dictionaryF.bin`` holds four tables of ``(bit, flag name)`` pairs, read by
``load_dictionary_flag_tables`` (``0x80263AB4``). Entry *n* of each table unlocks record *n* of
the matching ``dictionary.bin`` table (people, relations, affiliations, terms). The flag
function ``dictionary_flag`` (``0x8025F6B8``) finds a name by its prefix and keeps the bits in
the system save record: ``DF_人物`` people at +0x18B4, ``DF_関係`` relations at +0x18C8,
``DF_国`` / ``DF_所属`` affiliations at +0x18D4, ``DF_用語`` terms at +0x18E0.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass, field

from .pool_file import PoolFile, TableWriter, build_pool_file, read_pool_file

HIDDEN = -1000  # chart position of an entry that is not on the relation chart
TRAILER = b"\xff\xff\xff\xff"

#: dictionaryF prefix -> (table index, system-record offset of its bits)
FLAG_PREFIXES = {
    "DF_人物": (0, 0x18B4),
    "DF_関係": (1, 0x18C8),
    "DF_国": (2, 0x18D4),
    "DF_所属": (2, 0x18D4),
    "DF_用語": (3, 0x18E0),
}
TABLE_NAMES = ("people", "relations", "affiliations", "terms")
#: bits each table's set holds: each is a bit-set object (a header word, then its data words) that
#: save_write_system_record (0x80245888) writes as 16, 8, 8 and 8 bytes
FLAG_CAPACITY = (128, 64, 64, 64)


class DictionaryError(ValueError):
    pass


@dataclass
class Category:
    label: str | None
    value: int = 0


@dataclass
class Person:
    pid: str | None
    nation: str | None
    text: str | None
    x: int = HIDDEN
    y: int = HIDDEN
    faded: int = 0

    @property
    def on_chart(self) -> bool:
        return self.x >= 0


@dataclass
class Relation:
    image: str | None
    image_x: int
    image_y: int
    label: str | None
    colour: int
    label_x: int
    label_y: int
    #: the Japanese label point the 24-byte records keep at +0x10; ``None`` on 20-byte records
    original_label: tuple[int, int] | None = None


@dataclass
class Affiliation:
    frame: str | None
    frame_x: int
    frame_y: int
    banner: str | None
    label_x: int
    label_y: int


@dataclass
class Term:
    name: str | None
    reading: str | None
    text: str | None
    picture: str | None = None


@dataclass
class Dictionary:
    categories: list[Category] = field(default_factory=list)
    people: list[Person] = field(default_factory=list)
    relations: list[Relation] = field(default_factory=list)
    affiliations: list[Affiliation] = field(default_factory=list)
    terms: list[Term] = field(default_factory=list)
    trailer: bytes = TRAILER
    header_tail: bytes = bytes(12)
    symbols: list[tuple[str, int]] = field(default_factory=list)
    relation_size: int = 24

    def table(self, index: int) -> list:
        return [self.people, self.relations, self.affiliations, self.terms][index]


@dataclass
class FlagEntry:
    bit: int
    name: str


@dataclass
class DictionaryFlags:
    tables: list[list[FlagEntry]] = field(default_factory=lambda: [[], [], [], []])
    trailer: bytes = b""
    header_tail: bytes = bytes(12)
    symbols: list[tuple[str, int]] = field(default_factory=list)


# ------------------------------------------------------------------ dictionary.bin

def _s16(body: bytes, offset: int) -> tuple[int, int]:
    return struct.unpack_from(">hh", body, offset)


def read_dictionary(data: bytes) -> Dictionary:
    doc = read_pool_file(data)
    for relation_size in (24, 20):
        try:
            out = _read_tables(doc, relation_size)
        except (DictionaryError, struct.error):
            continue
        if out.trailer == TRAILER:
            return out
    raise DictionaryError("dictionary.bin's tables do not match the known layout.")


def _read_tables(doc: PoolFile, relation_size: int) -> Dictionary:
    body, pointers = doc.body, doc.pointers
    out = Dictionary(header_tail=doc.header_tail, symbols=list(doc.symbols), relation_size=relation_size)
    used = set()
    at = 0

    def count(size: int) -> int:
        nonlocal at
        value = struct.unpack_from(">I", body, at)[0]
        at += 4
        if at + value * size > len(body):
            raise DictionaryError("dictionary.bin ends inside its tables.")
        return value

    def ptr(offset: int) -> str | None:
        if offset in pointers:
            used.add(offset)
            return pointers[offset]
        if struct.unpack_from(">I", body, offset)[0]:
            raise DictionaryError(f"Expected a pointer or zero at {offset:#x}.")
        return None

    def word(offset: int) -> int:
        if offset in pointers:
            raise DictionaryError(f"Unexpected pointer at {offset:#x}.")
        return struct.unpack_from(">I", body, offset)[0]

    for _ in range(count(8)):
        out.categories.append(Category(ptr(at), word(at + 4)))
        at += 8
    for _ in range(count(20)):
        x, y = _s16(body, at + 12)
        out.people.append(Person(ptr(at), ptr(at + 4), ptr(at + 8), x, y, word(at + 16)))
        at += 20
    for _ in range(count(relation_size)):
        ix, iy = _s16(body, at + 4)
        original = _s16(body, at + 16) if relation_size == 24 else None
        lx, ly = _s16(body, at + relation_size - 4)
        out.relations.append(Relation(ptr(at), ix, iy, ptr(at + 8), word(at + 12), lx, ly, original))
        at += relation_size
    for _ in range(count(16)):
        fx, fy = _s16(body, at + 4)
        lx, ly = _s16(body, at + 12)
        out.affiliations.append(Affiliation(ptr(at), fx, fy, ptr(at + 8), lx, ly))
        at += 16
    for _ in range(count(16)):
        out.terms.append(Term(ptr(at), ptr(at + 4), ptr(at + 8), ptr(at + 12)))
        at += 16
    if used != set(pointers):
        raise DictionaryError("dictionary.bin has pointers outside its tables.")
    out.trailer = body[at:]
    return out


def build_dictionary(dictionary: Dictionary) -> bytes:
    w = TableWriter()
    w.word(len(dictionary.categories))
    for c in dictionary.categories:
        w.text(c.label)
        w.word(c.value)
    w.word(len(dictionary.people))
    for p in dictionary.people:
        w.text(p.pid)
        w.text(p.nation)
        w.text(p.text)
        w.pack(">hhI", p.x, p.y, p.faded)
    w.word(len(dictionary.relations))
    for r in dictionary.relations:
        w.text(r.image)
        w.pack(">hh", r.image_x, r.image_y)
        w.text(r.label)
        w.word(r.colour)
        if dictionary.relation_size == 24:
            w.pack(">hh", *(r.original_label or (r.label_x, r.label_y)))
        w.pack(">hh", r.label_x, r.label_y)
    w.word(len(dictionary.affiliations))
    for a in dictionary.affiliations:
        w.text(a.frame)
        w.pack(">hh", a.frame_x, a.frame_y)
        w.text(a.banner)
        w.pack(">hh", a.label_x, a.label_y)
    w.word(len(dictionary.terms))
    for t in dictionary.terms:
        w.text(t.name)
        w.text(t.reading)
        w.text(t.text)
        w.text(t.picture)
    w.raw(dictionary.trailer)
    return build_pool_file(PoolFile(bytes(w.body), w.pointers, dictionary.symbols, dictionary.header_tail))


# ------------------------------------------------------------------ dictionaryF.bin

def read_dictionary_flags(data: bytes) -> DictionaryFlags:
    doc = read_pool_file(data)
    body = doc.body
    out = DictionaryFlags(header_tail=doc.header_tail, symbols=list(doc.symbols))
    at = 0
    for table in out.tables:
        if at + 4 > len(body):
            raise DictionaryError("dictionaryF.bin ends inside its tables.")
        (n,) = struct.unpack_from(">I", body, at)
        at += 4
        if at + 8 * n > len(body):
            raise DictionaryError("dictionaryF.bin ends inside its tables.")
        for _ in range(n):
            table.append(FlagEntry(struct.unpack_from(">I", body, at)[0], doc.pointers.get(at + 4, "")))
            at += 8
    out.trailer = body[at:]
    return out


def build_dictionary_flags(flags: DictionaryFlags) -> bytes:
    w = TableWriter()
    for table in flags.tables:
        w.word(len(table))
        for entry in table:
            w.word(entry.bit)
            w.text(entry.name)
    w.raw(flags.trailer)
    return build_pool_file(PoolFile(bytes(w.body), w.pointers, flags.symbols, flags.header_tail))


def flag_location(name: str) -> tuple[int, int] | None:
    """``(table index, system-record offset)`` the game uses for a flag name, by its prefix."""
    for prefix, location in FLAG_PREFIXES.items():
        if name.startswith(prefix):
            return location
    return None


def check(dictionary: Dictionary, flags: DictionaryFlags) -> list[str]:
    """Problems the game would trip over: a table whose flag list has another length, a flag
    whose prefix names another table, or two flags of one table on the same bit."""
    problems = []
    for index, name in enumerate(TABLE_NAMES):
        entries, table = dictionary.table(index), flags.tables[index]
        if len(entries) != len(table):
            problems.append(f"{name}: {len(entries)} entries but {len(table)} flags.")
        bits = {}
        for entry in table:
            location = flag_location(entry.name)
            if location is None or location[0] != index:
                problems.append(f"{name}: flag {entry.name} does not start with this table's prefix.")
            if not 0 <= entry.bit < FLAG_CAPACITY[index]:
                problems.append(f"{name}: {entry.name} uses bit {entry.bit}; the save keeps bits "
                                f"0-{FLAG_CAPACITY[index] - 1}.")
            if entry.bit in bits:
                problems.append(f"{name}: {entry.name} and {bits[entry.bit]} share bit {entry.bit}.")
            bits[entry.bit] = entry.name
    return problems


def add_entry(dictionary: Dictionary, flags: DictionaryFlags, table: int, entry, flag_name: str) -> int:
    """Append ``entry`` to a table with a new flag on the next free bit; returns the bit."""
    used = {f.bit for f in flags.tables[table]}
    bit = max(used, default=0) + 1
    dictionary.table(table).append(entry)
    flags.tables[table].append(FlagEntry(bit, flag_name))
    return bit


def remove_entry(dictionary: Dictionary, flags: DictionaryFlags, table: int, index: int) -> None:
    del dictionary.table(table)[index]
    del flags.tables[table][index]
