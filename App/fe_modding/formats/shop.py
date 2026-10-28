"""Shop inventories - ``shop/shopitem_<n|h|m>.bin``, one file per difficulty
(Easy and any unknown difficulty fall back to ``n``).

The file is a "labeled section" container like a dispos variant: a 0x20-byte
header (file size, relocation-table offset, relocation count, section count),
a body, a label pool, the relocation table (the HEADER_SIZE-relative offset of
every body word that holds a pool pointer), a section table of (address,
name offset) pairs sorted by name, and the section names. The body starts
with two pointer words (the file's build timestamp and author, e.g.
``2005/02/25 11:27:12`` and a staff name), followed by 96 sections:

- ``WSHOP_ITEMS_Cnn`` (armory) and ``ISHOP_ITEMS_Cnn`` (vendor): a list of
  ``IID_`` pointers ended by a zero word.
- ``FSHOP_ITEMS_Cnn`` (forge): a fixed table of 45 (item, base) pointer
  pairs - 5 rows (swords, lances, axes, bows, tomes in vanilla) of 9 base
  columns tagged ``MDV_IRN/SLM/STL/SLV/HND/FI/TH/WD/LIT``. A zero item is a
  base the forge does not offer in that row. No terminator.

``nn`` is the current-chapter byte (``partyStruct+0x10``), which is the
chapter's disc file number (Prologue = 01): the game formats the name with
``"WSHOP_ITEMS_C%02d"`` and looks the section up by name. A chapter whose
section is missing gets an empty armory/vendor and the forge's built-in
default table. There is no fourth inventory: ``SSHOP`` is the sell shop.

``parse_shop()`` reads a file into a :class:`ShopDocument` whose pointers are
label strings; ``build_shop()`` lays it out again (byte-identical for an
unedited vanilla file).
"""

from __future__ import annotations

import re
import struct
from dataclasses import dataclass, field as dataclass_field
from typing import Optional, Union

from .common import HEADER_SIZE, decode_str, read_cstring_table

#: A body word: a label string for a pool pointer, else the raw number (0).
Value = Union[int, str]

_LABEL_CODEC = "shift_jis"  # the author label of shopitem_n.bin is Japanese
_SECTION_NAME_RE = re.compile(r"^([WIF])SHOP_ITEMS_C(\d+)$")
_SECTION_NAME_FE10_RE = re.compile(r"^([WIF])SHOP_ITEMS_C(\d{4}[a-z]?)$", re.IGNORECASE)

SHOP_KINDS = ("W", "I", "F")
SHOP_KIND_NAMES = {"W": "Armory", "I": "Vendor", "F": "Forge"}
DIFFICULTY_FILES = {"n": "shopitem_n.bin", "h": "shopitem_h.bin", "m": "shopitem_m.bin"}
DIFFICULTY_NAMES = {"n": "Normal / Easy", "h": "Hard", "m": "Maniac"}

FORGE_ROWS = 5
FORGE_BASES = ("MDV_IRN", "MDV_SLM", "MDV_STL", "MDV_SLV", "MDV_HND", "MDV_FI", "MDV_TH", "MDV_WD", "MDV_LIT")
FORGE_ROW_NAMES = ("Swords", "Lances", "Axes", "Bows", "Tomes")  # what each row holds in vanilla
FORGE_BASE_NAMES = {"MDV_IRN": "Iron", "MDV_SLM": "Slim", "MDV_STL": "Steel", "MDV_SLV": "Silver",
                    "MDV_HND": "Thrown", "MDV_FI": "Fire", "MDV_TH": "Thunder", "MDV_WD": "Wind",
                    "MDV_LIT": "Light"}
#: The forge's built-in grid (``default_forge_shop_items``, 0x80276354), used when a chapter has
#: no forge section: the weapon each row offers for each base, or None. These 19 are the
#: weapons the forge menu is built for.
FORGE_DEFAULT_ITEMS = (
    "IID_IRONSWORD", "IID_SLIMSWORD", "IID_STEELSWORD", "IID_SILVERSWORD", None, None, None, None, None,
    "IID_IRONLANCE", "IID_SLIMLANCE", "IID_STEELLANCE", "IID_SILVERLANCE", "IID_HANDSPEAR", None, None, None, None,
    "IID_IRONAXE", None, "IID_STEELAXE", "IID_SILVERAXE", "IID_HANDAXE", None, None, None, None,
    "IID_IRONBOW", None, "IID_STEELBOW", "IID_SILVERBOW", None, None, None, None, None,
    None, None, None, None, None, "IID_FIRE", "IID_THUNDER", "IID_WIND", "IID_LIGHTNING",
)
FE10_FORGE_ROWS = 6
FE10_FORGE_BASES = (*FORGE_BASES, "MDV_D")
FE10_FORGE_ROW_NAMES = ("Swords", "Lances", "Axes", "Bows", "Knives", "Magic")
FE10_FORGE_FAMILIES = ("MIK_SW", "MIK_LA", "MIK_AX", "MIK_BW", "MIK_KN", "MIK_MG")
FE10_FORGE_DEFAULT_ITEMS = (
    "IID_IRONSWORD", "IID_DELICATESWORD", "IID_STEELSWORD", "IID_SILVERSWORD", None, None, None, None, None, None,
    "IID_IRONLANCE", "IID_DELICATELANCE", "IID_STEELLANCE", "IID_SILVERLANCE", "IID_HANDSPEAR", None, None, None, None, None,
    "IID_IRONAXE", None, "IID_STEELAXE", "IID_SILVERAXE", "IID_HANDAXE", None, None, None, None, None,
    "IID_IRONBOW", None, "IID_STEELBOW", "IID_SILVERBOW", None, None, None, None, None, None,
    "IID_IRONKNIFE", None, "IID_STEELKNIFE", "IID_SILVERKNIFE", None, None, None, None, None, None,
    None, None, None, None, None, "IID_FIRE", "IID_THUNDER", "IID_WIND", "IID_LIGHT", "IID_WORM",
)


def section_name(kind: str, chapter: Union[int, str]) -> str:
    key = f"{chapter:02d}" if isinstance(chapter, int) else str(chapter)
    return f"{kind}SHOP_ITEMS_C{key}"


def parse_section_name(name: str) -> tuple[Optional[str], Optional[Union[int, str]]]:
    """``WSHOP_ITEMS_C07`` -> ``("W", 7)``; ``(None, None)`` for any other name."""
    match = _SECTION_NAME_RE.match(name)
    if not match:
        return None, None
    key = match.group(2)
    return match.group(1), (key.lower() if len(key) >= 4 or key[-1:].isalpha() else int(key))


@dataclass
class ShopSection:
    """One section. For an armory/vendor ``items`` is the list of IIDs (no
    terminator); for a forge it is the flat word list of its (item, base)
    pairs - see :func:`forge_cells`."""

    name: str
    items: list[Value] = dataclass_field(default_factory=list)
    metadata: list[int] = dataclass_field(default_factory=list)
    raw_words: list[Value] = dataclass_field(default_factory=list)
    dialect: str = "fe9"

    @property
    def kind(self) -> Optional[str]:
        return parse_section_name(self.name)[0]

    @property
    def chapter(self) -> Optional[Union[int, str]]:
        return parse_section_name(self.name)[1]

    @property
    def is_forge(self) -> bool:
        return self.kind == "F"


@dataclass
class ShopDocument:
    prelude: list[Value]  # body words before the first section (timestamp, author)
    sections: list[ShopSection]  # file order
    labels: list[str]  # label pool order
    header_tail: bytes  # header words 4-7, kept as they are
    dialect: str = "fe9"

    def section(self, name: str) -> Optional[ShopSection]:
        return next((s for s in self.sections if s.name == name), None)

    def shop(self, kind: str, chapter: int) -> Optional[ShopSection]:
        return self.section(section_name(kind, chapter))

    def chapters(self) -> list[int]:
        return sorted({s.chapter for s in self.sections if s.chapter is not None})


def parse_shop(data: bytes) -> ShopDocument:
    total, pool_end, relocation_count, section_count = struct.unpack_from(">4I", data, 0)
    pool_end += HEADER_SIZE
    table_start = pool_end + 4 * relocation_count
    entries = [struct.unpack_from(">II", data, table_start + 8 * i) for i in range(section_count)]
    names = read_cstring_table(data[table_start + 8 * section_count:])
    relocations = {struct.unpack_from(">I", data, pool_end + 4 * i)[0] for i in range(relocation_count)}

    addresses = sorted(address + HEADER_SIZE for address, _ in entries)
    # The pool starts where the last section ends: the lowest pointer target.
    targets = [struct.unpack_from(">I", data, HEADER_SIZE + r)[0] + HEADER_SIZE for r in relocations]
    pool_start = min(targets) if targets else pool_end

    labels, by_offset, position = [], {}, pool_start - HEADER_SIZE
    for raw in data[pool_start:pool_end].split(b"\x00"):
        if raw:
            label = raw.decode(_LABEL_CODEC)
            labels.append(label)
            by_offset[position] = label
        position += len(raw) + 1

    def word(offset: int) -> Value:
        (value,) = struct.unpack_from(">I", data, offset)
        if offset - HEADER_SIZE in relocations:
            if value not in by_offset:
                raise ValueError(f"Pointer at {offset:#x} doesn't point at a pool label")
            return by_offset[value]
        return value

    first = addresses[0] if addresses else pool_start
    prelude = [word(o) for o in range(HEADER_SIZE, first, 4)]
    name_of = {address + HEADER_SIZE: decode_str(names.get(offset, b"")) for address, offset in entries}
    dialect = "fe10" if any(name.startswith("SHOP_PERSON_") for name in name_of.values()) else "fe9"
    sections = []
    for i, address in enumerate(addresses):
        end = addresses[i + 1] if i + 1 < len(addresses) else pool_start
        words = [word(o) for o in range(address, end, 4)]
        section = ShopSection(name=name_of[address], dialect=dialect)
        if section.kind == "F":
            if dialect == "fe10" and len(words) % 3:
                raise ValueError(f"Section {section.name} isn't a table of forge triples")
            section.items = words
        elif section.kind in ("W", "I") and dialect == "fe10":
            if not words or words[-1] != 0 or (len(words) - 1) % 2:
                raise ValueError(f"Section {section.name} isn't a terminated Radiant Dawn item list")
            records = words[:-1]
            section.items = records[::2]
            section.metadata = [int(records[2 * j + 1]) for j in range(len(records) // 2)]
        elif section.kind in ("W", "I"):
            if not words or words[-1] != 0 or 0 in words[:-1]:
                raise ValueError(f"Section {section.name} isn't a zero-terminated list")
            section.items = words[:-1]
        else:
            section.raw_words = words
        sections.append(section)
    return ShopDocument(prelude=prelude, sections=sections, labels=labels,
                        header_tail=data[0x10:HEADER_SIZE], dialect=dialect)


def build_shop(doc: ShopDocument) -> bytes:
    """Lay a document out as a shop file. The pool keeps the document's
    labels that are still used, in order, then new ones in order of first
    use; the relocation table, section table (sorted by name) and names are
    rebuilt."""
    body_words: list[Value] = list(doc.prelude)
    addresses: dict[str, int] = {}
    for section in doc.sections:
        forge_width = 3 if doc.dialect == "fe10" else 2
        if section.is_forge and len(section.items) % forge_width:
            raise ValueError(f"Forge section {section.name} has an invalid word count")
        if section.kind in ("W", "I") and 0 in section.items:
            raise ValueError(f"Section {section.name} has an empty entry")
        addresses[section.name] = HEADER_SIZE + 4 * len(body_words)
        if section.kind in ("W", "I") and doc.dialect == "fe10":
            for i, item in enumerate(section.items):
                body_words += [item, section.metadata[i] if i < len(section.metadata) else 0]
            body_words.append(0)
        elif section.kind in ("W", "I"):
            body_words += section.items
            body_words.append(0)
        elif section.is_forge:
            body_words += section.items
        else:
            body_words += section.raw_words
    if len(addresses) != len(doc.sections):
        raise ValueError("Two sections have the same name")

    used = list(dict.fromkeys(w for w in body_words if isinstance(w, str)))
    in_use = set(used)
    pool_labels = [label for label in doc.labels if label in in_use]
    kept = set(pool_labels)
    pool_labels += [label for label in used if label not in kept]

    pool_start = HEADER_SIZE + 4 * len(body_words)
    offsets, pool = {}, bytearray()
    for label in pool_labels:
        offsets[label] = pool_start - HEADER_SIZE + len(pool)
        pool += label.encode(_LABEL_CODEC) + b"\x00"
    pool += bytes(-len(pool) % 4)

    body, relocations = bytearray(), []
    for i, value in enumerate(body_words):
        if isinstance(value, str):
            relocations.append(4 * i)
            value = offsets[value]
        body += struct.pack(">I", value)

    ordered = sorted(doc.sections, key=lambda s: s.name.encode("ascii"))
    names, name_offsets = bytearray(), []
    for section in ordered:
        name_offsets.append(len(names))
        names += section.name.encode("ascii") + b"\x00"
    table = b"".join(struct.pack(">II", addresses[s.name] - HEADER_SIZE, o) for s, o in zip(ordered, name_offsets))

    pool_end = pool_start + len(pool)
    tail = b"".join(struct.pack(">I", r) for r in relocations) + table + bytes(names)
    header = struct.pack(">4I", pool_end + len(tail), pool_end - HEADER_SIZE, len(relocations), len(ordered))
    return header + doc.header_tail + bytes(body) + bytes(pool) + tail


# -- forge table ----------------------------------------------------------------------

def forge_cells(section: ShopSection) -> list[tuple[Value, Value]]:
    """A forge section's (item or 0, base tag) pairs, row by row."""
    if section.dialect == "fe10":
        return [(section.items[i + 2], section.items[i + 1]) for i in range(0, len(section.items), 3)]
    return [(section.items[i], section.items[i + 1]) for i in range(0, len(section.items), 2)]


def set_forge_item(section: ShopSection, cell: int, item: Value) -> None:
    """Put ``item`` (an IID, or 0 for none) in one cell, keeping its base tag."""
    width, item_offset = (3, 2) if section.dialect == "fe10" else (2, 0)
    if not section.is_forge or not 0 <= width * cell < len(section.items):
        raise ValueError(f"No forge cell {cell} in {section.name}")
    section.items[width * cell + item_offset] = item or 0


def forge_layout(dialect: str) -> tuple[tuple[str, ...], tuple[str, ...], tuple[Optional[str], ...]]:
    """(row names, base tags, default items) for a game's forge table."""
    if dialect == "fe10":
        return FE10_FORGE_ROW_NAMES, FE10_FORGE_BASES, FE10_FORGE_DEFAULT_ITEMS
    return FORGE_ROW_NAMES, FORGE_BASES, FORGE_DEFAULT_ITEMS


# -- chapters -------------------------------------------------------------------------

def add_chapter(doc: ShopDocument, chapter: Union[int, str], template: Optional[Union[int, str]] = None) -> None:
    """Give ``chapter`` (0-99) its three sections, copied from ``template``'s
    (empty armory/vendor and an empty forge table when there is none)."""
    if isinstance(chapter, int) and not 0 <= chapter <= 99:
        raise ValueError("The game formats the chapter as two digits: 0-99.")
    if any(doc.shop(kind, chapter) for kind in SHOP_KINDS):
        raise ValueError(f"Chapter {chapter:02d} already has shops.")
    for kind in SHOP_KINDS:
        source = doc.shop(kind, template) if template is not None else None
        if source is not None:
            items = list(source.items)
        elif kind == "F" and doc.dialect == "fe10":
            items = [word for family in FE10_FORGE_FAMILIES for base in FE10_FORGE_BASES
                     for word in (family, base, 0)]
        elif kind == "F":
            items = [w for base in FORGE_BASES * FORGE_ROWS for w in (0, base)]
        else:
            items = []
        new = ShopSection(name=section_name(kind, chapter), items=items, dialect=doc.dialect)
        # after the last section of the same kind, keeping each kind's run together
        same = [i for i, s in enumerate(doc.sections) if s.kind == kind]
        doc.sections.insert(same[-1] + 1 if same else len(doc.sections), new)
    if doc.dialect == "fe10":
        person_name = f"SHOP_PERSON_C{chapter}"
        if not any(section.name == person_name for section in doc.sections):
            template_name = f"SHOP_PERSON_C{template}" if template is not None else ""
            source = next((section for section in doc.sections if section.name == template_name), None)
            raw = list(source.raw_words) if source is not None else [0]
            at = next((i for i, section in enumerate(doc.sections)
                       if section.name.startswith(("WSHOP_", "ISHOP_", "FSHOP_"))), len(doc.sections))
            doc.sections.insert(at, ShopSection(person_name, raw_words=raw, dialect="fe10"))


def remove_chapter(doc: ShopDocument, chapter: Union[int, str]) -> int:
    """Remove every armory, vendor and forge section for ``chapter``.

    Returns the number of sections removed. Missing sections are harmless so
    partially-created chapters can be cleaned up too.
    """
    before = len(doc.sections)
    person_name = f"SHOP_PERSON_C{chapter}" if doc.dialect == "fe10" else ""
    doc.sections[:] = [section for section in doc.sections
                       if section.chapter != chapter and section.name != person_name]
    return before - len(doc.sections)
