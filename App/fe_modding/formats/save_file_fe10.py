"""Radiant Dawn (RFEE01) Dolphin NAND saves (``FE10_US.dat``).

The unencrypted NAND file is 0x124000 bytes: one 0x4000-byte ``FE10ASYS``
system record, six 0x18000-byte file-save records and six 0x18000-byte
checkpoint records.  Each bank has one record for each of the six visible
files; they are not rotating A/B copies. Empty records are filled with
``0xff``.

Every populated record has a CRC-32 at +0x18.  The game clears that word,
computes the ordinary reflected CRC-32 across the complete record and stores
the result big-endian.  Data records contain the native tagged stream
``ITBL/BMST/MDST/UNIP/SOKO/FGPT/T  T/RELD/KZND/DEBU``.  This module deliberately
keeps the stream in place: edits replace bytes inside a decoded section and
all unrecognised/reserved bytes survive unchanged.

Research reference: ``research/rd/SAVE_NOTES.md``.
"""

from __future__ import annotations

import struct
import zlib
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Mapping, Optional

FILE_NAME = "FE10_US.dat"
FILE_SIZE = 0x124000
SYSTEM_SIZE = 0x4000
BLOCK_SIZE = 0x18000
RECORDS_PER_BANK = 6
TOTAL_BLOCKS = 12
CONVOY_SLOTS = 316
SCRIPT_FLAG_COUNT = 128
SCRIPT_FLAG_BYTES = SCRIPT_FLAG_COUNT // 8
BMST_FIXED_SIZE = 0xD8
BMST_VIRTUAL_SIZE = 0x10
BMST_LINK_RECORD_SIZE = 5
BMST_FLAGS_OFFSET = (BMST_FIXED_SIZE + 2 * BMST_VIRTUAL_SIZE
                     + 2 * BMST_LINK_RECORD_SIZE)  # 0x102
RUNTIME_BOND_SIZE = 6
TACTICAL_RECORD_COUNT = 0x80
TACTICAL_RECORD_SIZE = 8
TACTICAL_BLOB_SIZE = 0x200
TACTICAL_STATE_SIZE = (TACTICAL_RECORD_COUNT * TACTICAL_RECORD_SIZE
                       + 4 + TACTICAL_BLOB_SIZE + 4)  # 0x608
RUNTIME_RELATION_SIZE = 5
UNIT_SLOT_COUNT = 0xFE
OLD_UNIT_SLOT_COUNT = 0x9F
UNIT_SKILL_SLOTS = 18
UNIT_ITEM_SLOTS = 7
SYSTEM_MAGIC = b"FE10ASYS"
DATA_MAGIC = b"FE10ADAT"
SYSTEM_VERSION = 0x20061002
DATA_VERSION = 0x20060920
FORMAT_VERSION = 0x11
CRC_OFFSET = 0x18
HEADER_SIZE = 0x40
REGULAR_BASE = SYSTEM_SIZE
CHECKPOINT_BASE = SYSTEM_SIZE + RECORDS_PER_BANK * BLOCK_SIZE  # 0x94000

# The final on-disc tag is the four bytes DEBU; the executable's source string is DEBUG.
STREAM_TAGS = (b"ITBL", b"BMST", b"MDST", b"UNIP", b"SOKO", b"FGPT", b"T  T",
               b"RELD", b"KZND", b"DEBU")


def _u32(data: bytes | bytearray, offset: int) -> int:
    return struct.unpack_from(">I", data, offset)[0]


def _u64(data: bytes | bytearray, offset: int) -> int:
    return struct.unpack_from(">Q", data, offset)[0]


def signed_crc(data: bytes | bytearray) -> int:
    """RFEE01's record CRC: CRC word zeroed, then zlib/IEEE CRC-32."""
    work = bytearray(data)
    if len(work) < CRC_OFFSET + 4:
        raise ValueError("save record is too short for its checksum")
    work[CRC_OFFSET:CRC_OFFSET + 4] = bytes(4)
    return zlib.crc32(work) & 0xFFFFFFFF


@dataclass(frozen=True)
class SaveSection:
    """One section of a populated ``FE10ADAT`` stream."""

    name: str
    tag_offset: int                 # record-relative
    data_offset: int                # record-relative
    end_offset: int                 # record-relative, exclusive

    @property
    def size(self) -> int:
        return self.end_offset - self.data_offset


@dataclass(frozen=True)
class ConvoyItem:
    """One serialized SOKO item slot.

    Ordinary and empty slots are four bytes. A forged item appends a NUL-terminated name (at most
    24 bytes including the terminator) and eight FE10-only bytes. The suffix is retained verbatim;
    its numeric fields are not exposed until their meanings are closed.
    """

    slot: int
    offset: int                    # SOKO-payload-relative
    item_number: int
    state: int
    forge_data: bytes = b""

    @property
    def forged(self) -> bool:
        return bool(self.item_number and self.state & 0x20)

    @property
    def size(self) -> int:
        return 4 + len(self.forge_data)

    @property
    def forge_name_bytes(self) -> bytes:
        """The forged name without its terminator, or empty bytes for an ordinary item."""
        return self.forge_data[:-8].rstrip(b"\x00") if self.forged else b""

    @property
    def forge_payload(self) -> bytes:
        """The eight-byte FE10 forge payload in its native packed representation."""
        return self.forge_data[-8:] if self.forged else b""

    @property
    def forge_values(self) -> Optional["ForgePayload"]:
        return ForgePayload.from_bytes(self.forge_payload) if self.forged else None


@dataclass(frozen=True)
class ForgePayload:
    """The saved forge modifiers and RGBA weapon colour.

    The first four signed bytes are the native forge step counts. The last four bytes are returned
    verbatim by ``get_item_colour`` for forged instances; the default is ``80 80 80 FF``.
    """

    might_steps: int
    hit_steps: int
    critical_steps: int
    weight_reduction_steps: int
    red: int
    green: int
    blue: int
    alpha: int

    @classmethod
    def from_bytes(cls, data: bytes) -> "ForgePayload":
        if len(data) != 8:
            raise ValueError(f"forge payload must be 8 bytes, found {len(data)}")
        return cls(*struct.unpack(">bbbbBBBB", data))

    def to_bytes(self) -> bytes:
        for name, value in zip(("might", "hit", "critical", "weight reduction"),
                               (self.might_steps, self.hit_steps, self.critical_steps,
                                self.weight_reduction_steps)):
            if not -0x80 <= value <= 0x7F:
                raise ValueError(f"forge {name} steps must fit in a signed byte")
        for name, value in zip(("red", "green", "blue", "alpha"),
                               (self.red, self.green, self.blue, self.alpha)):
            if not 0 <= value <= 0xFF:
                raise ValueError(f"forge {name} must fit in an unsigned byte")
        return struct.pack(">bbbbBBBB", self.might_steps, self.hit_steps, self.critical_steps,
                           self.weight_reduction_steps, self.red, self.green, self.blue, self.alpha)


@dataclass(frozen=True)
class SaveIdTables:
    """The eight counted name tables serialized by ``ITBL``.

    Names omit their native PID/JID/IID/SID/SEQ/MTYPE prefixes, exactly as the game writes them.
    The first three tables are one-based in save records; skills are zero-based.
    """

    characters: tuple[str, ...]
    classes: tuple[str, ...]
    items: tuple[str, ...]
    skills: tuple[str, ...]
    attack_sequences: tuple[str, ...]
    move_sequences: tuple[str, ...]
    heal_sequences: tuple[str, ...]
    move_types: tuple[str, ...]


@dataclass(frozen=True)
class SavedItem:
    """One variable-length item record embedded in a unit or the convoy."""

    slot: int
    offset: int
    item_number: int
    state: int
    forge_data: bytes = b""

    @property
    def forged(self) -> bool:
        return bool(self.item_number and self.state & 0x20)

    @property
    def size(self) -> int:
        return 4 + len(self.forge_data)

    @property
    def forge_name_bytes(self) -> bytes:
        return self.forge_data[:-8].rstrip(b"\x00") if self.forged else b""

    @property
    def forge_payload(self) -> bytes:
        return self.forge_data[-8:] if self.forged else b""

    @property
    def forge_values(self) -> Optional[ForgePayload]:
        return ForgePayload.from_bytes(self.forge_payload) if self.forged else None


@dataclass(frozen=True)
class SavedSkill:
    """One occupied entry from a unit's 18-slot skill array."""

    skill_number: int
    value_1: int
    value_2: int


@dataclass(frozen=True)
class SavedUnit:
    """One structurally framed UNIP slot.

    ``raw`` contains the complete native record, including the still-semantic-unknown fixed
    substructures. Rejoining every record's raw bytes therefore rebuilds UNIP without scanning for
    tags or dropping opaque state.
    """

    slot: int
    offset: int
    raw: bytes
    person_number: int
    class_number: int = 0
    army: int = 0
    linked_slots: tuple[int, int, int] = (0, 0, 0)
    skills: tuple[SavedSkill, ...] = ()
    items: tuple[SavedItem, ...] = ()
    support_slot_count: int = 0

    @property
    def empty(self) -> bool:
        return self.person_number == 0

    @property
    def size(self) -> int:
        return len(self.raw)


@dataclass(frozen=True)
class RuntimeBond:
    """One KZND runtime support/bond record.

    The two identifiers are indices in the save's serialized PID table. ``kind`` and
    ``critical_bonus`` retain the native unsigned/signed byte representation.
    """

    first_pid: int
    second_pid: int
    kind: int
    critical_bonus: int


@dataclass(frozen=True)
class TacticalTableState:
    """Structurally decoded ``T  T`` payload; field semantics remain unknown."""

    records: tuple[bytes, ...]
    value_after_records: int
    blob: bytes
    final_value: int


@dataclass(frozen=True)
class RuntimeRelation:
    """One RELD relation record using two ITBL PID indices and an unsigned byte."""

    first_pid: int
    second_pid: int
    value: int


def _find_sections(raw: bytes | bytearray) -> list[SaveSection]:
    """Find the ordered RFEE01 tag stream without mistaking ITBL strings for tags."""
    if not raw.startswith(DATA_MAGIC):
        return []
    found: list[tuple[bytes, int]] = []
    cursor = HEADER_SIZE
    for tag in STREAM_TAGS:
        at = raw.find(tag, cursor)
        if at < 0:
            # Old revisions may end before RELD/KZND; keep every confirmed prefix.
            break
        found.append((tag, at))
        cursor = at + 4
    sections = []
    for i, (tag, at) in enumerate(found):
        end = found[i + 1][1] if i + 1 < len(found) else _used_end(raw, at + 4)
        sections.append(SaveSection(tag.decode("ascii"), at, at + 4, end))
    return sections


def _used_end(raw: bytes | bytearray, minimum: int) -> int:
    """End of the serialized prefix; record padding is 0xff."""
    end = len(raw)
    while end > minimum and raw[end - 1] == 0xFF:
        end -= 1
    return end


def _require(data: bytes | bytearray, cursor: int, size: int, what: str) -> None:
    if cursor < 0 or cursor + size > len(data):
        raise ValueError(f"{what} is truncated at stream offset 0x{cursor:X}")


def _read_saved_item(data: bytes | bytearray, cursor: int, slot: int,
                     *, what: str) -> tuple[SavedItem, int]:
    _require(data, cursor, 4, what)
    item_number, state = struct.unpack_from(">HH", data, cursor)
    forged = bool(item_number and state & 0x20)
    end = cursor + 4
    if forged:
        name_start = end
        name_end = bytes(data).find(b"\x00", name_start, min(name_start + 24, len(data)))
        if name_end < 0:
            raise ValueError(f"{what} forged item has no name terminator within 24 bytes")
        end = name_end + 1 + 8
        _require(data, cursor, end - cursor, what)
    return SavedItem(slot, cursor, item_number, state,
                     bytes(data[cursor + 4:end]) if forged else b""), end


class SaveRecord:
    """A system record or one physical copy of an RFEE01 save slot."""

    def __init__(self, raw: bytes, offset: int, *, index: Optional[int] = None,
                 checkpoint: bool = False):
        self.raw = bytearray(raw)
        self.offset = offset
        self.index = index
        self.checkpoint = checkpoint
        self.dirty = False
        self.sections = _find_sections(self.raw)

    @property
    def empty(self) -> bool:
        return bool(self.raw) and all(byte == 0xFF for byte in self.raw[:HEADER_SIZE])

    @property
    def magic(self) -> bytes:
        return bytes(self.raw[:8])

    @property
    def expected_magic(self) -> bytes:
        return SYSTEM_MAGIC if self.index is None else DATA_MAGIC

    @property
    def version(self) -> int:
        return _u32(self.raw, 8) if len(self.raw) >= 12 else 0

    @property
    def format_version(self) -> int:
        return _u32(self.raw, 0x0C) if len(self.raw) >= 0x10 else 0

    @property
    def sequence(self) -> int:
        return _u32(self.raw, 0x1C) if len(self.raw) >= 0x20 and not self.empty else -1

    @property
    def timestamp_created(self) -> int:
        return _u64(self.raw, 0x10) if len(self.raw) >= 0x18 and not self.empty else 0

    @property
    def timestamp_saved(self) -> int:
        return _u64(self.raw, 0x20) if len(self.raw) >= 0x28 and not self.empty else 0

    @property
    def stored_crc(self) -> int:
        return _u32(self.raw, CRC_OFFSET) if len(self.raw) >= CRC_OFFSET + 4 and not self.empty else 0

    @property
    def crc_ok(self) -> bool:
        return not self.empty and self.stored_crc == signed_crc(self.raw)

    @property
    def valid(self) -> bool:
        expected_version = SYSTEM_VERSION if self.index is None else DATA_VERSION
        return (not self.empty and self.magic == self.expected_magic
                and self.version == expected_version and self.crc_ok)

    @property
    def logical_slot(self) -> Optional[int]:
        if self.index is None:
            return None
        return self.index - RECORDS_PER_BANK if self.checkpoint else self.index

    def section(self, name: str) -> Optional[SaveSection]:
        wanted = name[:4]
        return next((section for section in self.sections if section.name == wanted), None)

    def section_bytes(self, name: str) -> bytes:
        section = self.section(name)
        if section is None:
            raise KeyError(f"save record has no {name} section")
        return bytes(self.raw[section.data_offset:section.end_offset])

    def id_tables(self) -> SaveIdTables:
        """Decode ITBL by its eight counts, stopping at the structurally expected BMST tag."""
        section = self.section("ITBL")
        if section is None:
            raise KeyError("save record has no ITBL section")
        cursor = section.data_offset
        tables: list[tuple[str, ...]] = []
        for table_index in range(8):
            _require(self.raw, cursor, 4, f"ITBL table {table_index + 1} count")
            count = _u32(self.raw, cursor)
            cursor += 4
            names = []
            for entry_index in range(count):
                end = self.raw.find(b"\x00", cursor)
                if end < 0:
                    raise ValueError(
                        f"ITBL table {table_index + 1} entry {entry_index + 1} is unterminated")
                names.append(bytes(self.raw[cursor:end]).decode("shift_jis"))
                cursor = end + 1
            tables.append(tuple(names))
        if self.raw[cursor:cursor + 4] != b"BMST":
            raise ValueError(f"ITBL structural end 0x{cursor:X} is not followed by BMST")
        return SaveIdTables(*tables)

    def id_of(self, kind: str, name: str) -> int:
        """Return a serialized ITBL number for a prefixed or unprefixed record name."""
        tables = self.id_tables()
        table, prefix, base = {
            "character": (tables.characters, "PID_", 1),
            "class": (tables.classes, "JID_", 1),
            "item": (tables.items, "IID_", 1),
            "skill": (tables.skills, "SID_", 0),
        }[kind]
        short = name[len(prefix):] if name.startswith(prefix) else name
        try:
            return table.index(short) + base
        except ValueError as exc:
            raise KeyError(f"{name!r} is not in the save's {kind} table") from exc

    def support_slot_counts_from_fe10data(self, data: bytes) -> dict[int, int]:
        """Map every saved PID number to its RelianceData slot count.

        UNIP does not serialize whether a character owns RelianceData; the native reader consults
        the currently loaded database. Supplying the same metadata is therefore required to frame
        the conditional support tail without heuristics.
        """
        from . import fe10data

        tables = self.id_tables()
        counts_by_pid = {record.values["pid"]: len(record.lists["partners"])
                         for record in fe10data.read_table(data, "support")}
        return {index: counts_by_pid.get("PID_" + short_name, 0)
                for index, short_name in enumerate(tables.characters, 1)}

    def unit_records(self, support_slot_counts: Mapping[int, int]) -> tuple[SavedUnit, ...]:
        """Structurally parse UNIP's fixed slot count and verify the following SOKO tag.

        ``support_slot_counts`` must contain every occupied PID number. This mirrors the game's
        RelianceData-dependent branch and makes the end of UNIP deterministic even if item names or
        opaque unit bytes happen to contain a four-byte stream tag.
        """
        section = self.section("UNIP")
        if section is None:
            raise KeyError("save record has no UNIP section")
        cursor = section.data_offset
        slot_count = OLD_UNIT_SLOT_COUNT if self.format_version < 0x0B else UNIT_SLOT_COUNT
        units = []
        for slot in range(slot_count):
            start = cursor
            _require(self.raw, cursor, 2, f"UNIP slot {slot + 1}")
            person_number = struct.unpack_from(">H", self.raw, cursor)[0]
            cursor += 2
            if person_number == 0:
                units.append(SavedUnit(slot, start - section.data_offset,
                                       bytes(self.raw[start:cursor]), 0))
                continue
            if person_number not in support_slot_counts:
                raise ValueError(
                    f"UNIP slot {slot + 1} PID number {person_number} has no support-slot metadata")
            _require(self.raw, start, 46, f"UNIP slot {slot + 1} fixed header")
            class_number = struct.unpack_from(">H", self.raw, start + 2)[0]
            army = self.raw[start + 4]
            linked_slots = tuple(self.raw[start + 5:start + 8])
            cursor = start + 46

            _require(self.raw, cursor, 1, f"UNIP slot {slot + 1} skill count")
            skill_count = self.raw[cursor]
            cursor += 1
            if skill_count > UNIT_SKILL_SLOTS:
                raise ValueError(
                    f"UNIP slot {slot + 1} has {skill_count} skills, maximum is {UNIT_SKILL_SLOTS}")
            _require(self.raw, cursor, 4 * skill_count, f"UNIP slot {slot + 1} skills")
            skills = tuple(SavedSkill(*struct.unpack_from(">HBB", self.raw, cursor + 4 * i))
                           for i in range(skill_count))
            cursor += 4 * skill_count

            items = []
            for item_slot in range(UNIT_ITEM_SLOTS):
                item, cursor = _read_saved_item(
                    self.raw, cursor, item_slot,
                    what=f"UNIP slot {slot + 1} item {item_slot + 1}")
                items.append(item)
            _require(self.raw, cursor, 38, f"UNIP slot {slot + 1} pre-support state")
            cursor += 38  # 24-byte unit block, then six u16 and two u8.

            support_count = support_slot_counts[person_number]
            if not 0 <= support_count <= 0xFF:
                raise ValueError(f"PID number {person_number} support-slot count does not fit in u8")
            if support_count:
                _require(self.raw, cursor, 15, f"UNIP slot {slot + 1} support header")
                serialized_count = self.raw[cursor + 14]
                if serialized_count != support_count:
                    raise ValueError(
                        f"UNIP slot {slot + 1} saves {serialized_count} support points, "
                        f"RelianceData requires {support_count}")
                cursor += 15
                _require(self.raw, cursor, support_count + 36,
                         f"UNIP slot {slot + 1} support state")
                cursor += support_count + 36

            _require(self.raw, cursor, 37, f"UNIP slot {slot + 1} trailing state")
            cursor += 37
            units.append(SavedUnit(
                slot, start - section.data_offset, bytes(self.raw[start:cursor]), person_number,
                class_number, army, linked_slots, skills, tuple(items), support_count))

        if self.raw[cursor:cursor + 4] != b"SOKO":
            raise ValueError(f"UNIP structural end 0x{cursor:X} is not followed by SOKO")
        return tuple(units)

    def replace_section_bytes(self, name: str, relative_offset: int, data: bytes) -> None:
        section = self.section(name)
        if section is None:
            raise KeyError(f"save record has no {name} section")
        start = section.data_offset + relative_offset
        end = start + len(data)
        if relative_offset < 0 or end > section.end_offset:
            raise ValueError(f"{name} edit is outside its {section.size}-byte payload")
        if self.raw[start:end] != data:
            self.raw[start:end] = data
            self.dirty = True

    def _replace_variable_bytes(self, start: int, end: int, data: bytes) -> None:
        """Replace stream bytes while retaining the record's fixed size and 0xFF padding."""
        if not 0 <= start <= end <= len(self.raw):
            raise ValueError("variable stream edit is outside the save record")
        delta = len(data) - (end - start)
        if delta > 0 and any(byte != 0xFF for byte in self.raw[-delta:]):
            raise ValueError("save record has insufficient 0xFF padding for a larger stream edit")
        self.raw[start:end] = data
        if delta > 0:
            del self.raw[-delta:]
        elif delta < 0:
            self.raw.extend(b"\xFF" * -delta)
        self.sections = _find_sections(self.raw)
        self.dirty = True

    def convoy_items(self) -> list[ConvoyItem]:
        """Decode the 316 SOKO item slots written by RFEE01's two inventory arrays."""
        data = self.section_bytes("SOKO")
        items = []
        cursor = 0
        for slot in range(CONVOY_SLOTS):
            if cursor + 4 > len(data):
                raise ValueError(f"SOKO ends in convoy slot {slot + 1}")
            item_number, state = struct.unpack_from(">HH", data, cursor)
            forged = bool(item_number and state & 0x20)
            if forged:
                name_start = cursor + 4
                name_end = data.find(b"\x00", name_start, min(name_start + 24, len(data)))
                if name_end < 0:
                    raise ValueError(f"SOKO forged item in slot {slot + 1} has no terminated name")
                end = name_end + 1 + 8
            else:
                end = cursor + 4
            if end > len(data):
                raise ValueError(f"SOKO forged item in slot {slot + 1} is truncated")
            items.append(ConvoyItem(slot, cursor, item_number, state,
                                    bytes(data[cursor + 4:end]) if forged else b""))
            cursor = end
        if cursor != len(data):
            raise ValueError(f"SOKO has {len(data) - cursor} unexpected trailing byte(s)")
        return items

    def set_convoy_item(self, slot: int, item_number: int, state: int) -> None:
        """Edit an ordinary SOKO slot without changing the variable-length stream shape.

        Forged records are readable and preserved, but changing them or converting to/from them is
        refused because their eight-byte FE10 payload is not yet semantically decoded.
        """
        if not 0 <= item_number <= 0xFFFF or not 0 <= state <= 0xFFFF:
            raise ValueError("item number and state must fit in 16 bits")
        item = self.convoy_items()[slot]
        if item.forged or (item_number and state & 0x20):
            raise ValueError("forged convoy items are read-only until their FE10 payload is decoded")
        if item_number == 0:
            state = 0
        self.replace_section_bytes("SOKO", item.offset, struct.pack(">HH", item_number, state))

    def update_forged_convoy_item(self, slot: int, *, item_number: Optional[int] = None,
                                  name: Optional[str] = None,
                                  payload: Optional[ForgePayload] = None) -> None:
        """Edit an existing forged convoy entry, including a variable-length custom name.

        The state word is deliberately retained: it owns the native forge-pool association. This
        method does not convert ordinary items into forged items because allocating that association
        is a separate runtime operation.
        """
        item = self.convoy_items()[slot]
        if not item.forged:
            raise ValueError("convoy item is not forged")
        number = item.item_number if item_number is None else item_number
        if not 1 <= number <= 0xFFFF:
            raise ValueError("forged item number must be 1..65535")
        if name is None:
            name_bytes = item.forge_data[:-8]
        else:
            encoded = name.encode("shift_jis")
            if b"\x00" in encoded:
                raise ValueError("forge name cannot contain a NUL byte")
            if len(encoded) > 14:
                raise ValueError("forge name must fit in the native 15-byte NUL-terminated buffer")
            name_bytes = encoded + b"\x00"
        payload_bytes = item.forge_payload if payload is None else payload.to_bytes()
        replacement = struct.pack(">HH", number, item.state) + name_bytes + payload_bytes
        section = self.section("SOKO")
        assert section is not None
        start = section.data_offset + item.offset
        self._replace_variable_bytes(start, start + item.size, replacement)

    def script_flags(self) -> tuple[bool, ...]:
        """Return BMST's confirmed 128 saved event-flag bits in slot order."""
        data = self.section_bytes("BMST")
        end = BMST_FLAGS_OFFSET + SCRIPT_FLAG_BYTES
        if len(data) < end:
            raise ValueError("BMST section is too short for its 128 script flags")
        raw = data[BMST_FLAGS_OFFSET:end]
        return tuple(bool(raw[index >> 3] & (1 << (index & 7)))
                     for index in range(SCRIPT_FLAG_COUNT))

    def set_script_flag(self, index: int, value: bool) -> None:
        """Set one BMST event-flag bit without touching adjacent state."""
        if not 0 <= index < SCRIPT_FLAG_COUNT:
            raise ValueError(f"script flag index must be 0..{SCRIPT_FLAG_COUNT - 1}")
        data = self.section_bytes("BMST")
        byte_index = BMST_FLAGS_OFFSET + (index >> 3)
        if len(data) <= byte_index:
            raise ValueError("BMST section is too short for its 128 script flags")
        mask = 1 << (index & 7)
        updated = data[byte_index] | mask if value else data[byte_index] & ~mask
        self.replace_section_bytes("BMST", byte_index, bytes((updated,)))

    def runtime_bonds(self) -> tuple[RuntimeBond, ...]:
        """Decode KZND's counted six-byte runtime support/bond records."""
        data = self.section_bytes("KZND")
        if len(data) < 4:
            raise ValueError("KZND section is too short for its record count")
        count = _u32(data, 0)
        expected = 4 + count * RUNTIME_BOND_SIZE
        if len(data) != expected:
            raise ValueError(f"KZND count requires {expected} bytes, found {len(data)}")
        return tuple(RuntimeBond(*struct.unpack_from(">HHBb", data, 4 + i * RUNTIME_BOND_SIZE))
                     for i in range(count))

    def set_runtime_bond(self, index: int, bond: RuntimeBond) -> None:
        """Replace one KZND record in place, preserving the section's shape."""
        bonds = self.runtime_bonds()
        if not 0 <= index < len(bonds):
            raise IndexError("runtime bond index is out of range")
        if not 0 <= bond.first_pid <= 0xFFFF or not 0 <= bond.second_pid <= 0xFFFF:
            raise ValueError("runtime bond PID indices must fit in 16 bits")
        if not 0 <= bond.kind <= 0xFF:
            raise ValueError("runtime bond kind must fit in 8 bits")
        if not -0x80 <= bond.critical_bonus <= 0x7F:
            raise ValueError("runtime bond critical bonus must fit in a signed byte")
        self.replace_section_bytes(
            "KZND", 4 + index * RUNTIME_BOND_SIZE,
            struct.pack(">HHBb", bond.first_pid, bond.second_pid, bond.kind, bond.critical_bonus))

    def tactical_table_state(self) -> TacticalTableState:
        """Decode the fixed 0x608-byte ``T  T`` section without assigning semantics."""
        data = self.section_bytes("T  T")
        if len(data) != TACTICAL_STATE_SIZE:
            raise ValueError(f"T  T must be {TACTICAL_STATE_SIZE} bytes, found {len(data)}")
        records_end = TACTICAL_RECORD_COUNT * TACTICAL_RECORD_SIZE
        records = tuple(data[offset:offset + TACTICAL_RECORD_SIZE]
                        for offset in range(0, records_end, TACTICAL_RECORD_SIZE))
        value_after_records = _u32(data, records_end)
        blob_start = records_end + 4
        blob_end = blob_start + TACTICAL_BLOB_SIZE
        return TacticalTableState(records, value_after_records, data[blob_start:blob_end],
                                  _u32(data, blob_end))

    def runtime_relations(self) -> tuple[RuntimeRelation, ...]:
        """Decode RELD's counted five-byte relation records."""
        data = self.section_bytes("RELD")
        if len(data) < 4:
            raise ValueError("RELD section is too short for its record count")
        count = _u32(data, 0)
        expected = 4 + count * RUNTIME_RELATION_SIZE
        if len(data) != expected:
            raise ValueError(f"RELD count requires {expected} bytes, found {len(data)}")
        return tuple(RuntimeRelation(*struct.unpack_from(">HHB", data, 4 + i * RUNTIME_RELATION_SIZE))
                     for i in range(count))

    def set_runtime_relation(self, index: int, relation: RuntimeRelation) -> None:
        """Replace one RELD record in place, preserving the section's shape."""
        relations = self.runtime_relations()
        if not 0 <= index < len(relations):
            raise IndexError("runtime relation index is out of range")
        if not 0 <= relation.first_pid <= 0xFFFF or not 0 <= relation.second_pid <= 0xFFFF:
            raise ValueError("runtime relation PID indices must fit in 16 bits")
        if not 0 <= relation.value <= 0xFF:
            raise ValueError("runtime relation value must fit in 8 bits")
        self.replace_section_bytes(
            "RELD", 4 + index * RUNTIME_RELATION_SIZE,
            struct.pack(">HHB", relation.first_pid, relation.second_pid, relation.value))

    def _bmst_value(self, relative_offset: int, size: int) -> int:
        data = self.section_bytes("BMST")
        if relative_offset + size > len(data):
            raise ValueError("BMST section is too short for its battle-state header")
        return int.from_bytes(data[relative_offset:relative_offset + size], "big")

    def _set_bmst_value(self, relative_offset: int, size: int, value: int) -> None:
        if not 0 <= value < 1 << (size * 8):
            raise ValueError(f"value must fit in {size * 8} bits")
        self.replace_section_bytes("BMST", relative_offset, value.to_bytes(size, "big"))

    @property
    def chapter_number(self) -> int:
        """Internal chapter byte from BMST's confirmed fixed header."""
        return self._bmst_value(0x10, 1)

    @chapter_number.setter
    def chapter_number(self, value: int) -> None:
        self._set_bmst_value(0x10, 1, value)

    @property
    def army_phase(self) -> int:
        """Current army/phase byte from BMST's confirmed fixed header."""
        return self._bmst_value(0x11, 1)

    @army_phase.setter
    def army_phase(self, value: int) -> None:
        self._set_bmst_value(0x11, 1, value)

    @property
    def turn(self) -> int:
        """Current turn counter from BMST's confirmed fixed header."""
        return self._bmst_value(0x12, 2)

    @turn.setter
    def turn(self, value: int) -> None:
        self._set_bmst_value(0x12, 2, value)

    def header_u8(self, offset: int) -> int:
        if not 0 <= offset < HEADER_SIZE:
            raise ValueError("header byte offset must be 0..0x3f")
        return self.raw[offset]

    def set_header_u8(self, offset: int, value: int) -> None:
        if not 0 <= value <= 0xFF:
            raise ValueError("header byte must be 0..255")
        if not 0 <= offset < HEADER_SIZE or CRC_OFFSET <= offset < CRC_OFFSET + 4:
            raise ValueError("header byte offset is not editable")
        if self.raw[offset] != value:
            self.raw[offset] = value
            self.dirty = True

    def build(self) -> bytes:
        if self.empty:
            return bytes(self.raw)
        if self.magic == self.expected_magic:
            struct.pack_into(">I", self.raw, CRC_OFFSET, signed_crc(self.raw))
        return bytes(self.raw)


class SaveFile:
    """The complete unencrypted RFEE01 NAND data file."""

    def __init__(self, data: bytes, system: SaveRecord, records: list[SaveRecord]):
        self.data = bytes(data)
        self.system = system
        self.records = records

    @classmethod
    def from_bytes(cls, data: bytes) -> "SaveFile":
        if len(data) != FILE_SIZE:
            raise ValueError(f"RFEE01 save must be 0x{FILE_SIZE:X} bytes, found 0x{len(data):X}")
        system = SaveRecord(data[:SYSTEM_SIZE], 0)
        records = []
        for index in range(TOTAL_BLOCKS):
            offset = SYSTEM_SIZE + index * BLOCK_SIZE
            records.append(SaveRecord(data[offset:offset + BLOCK_SIZE], offset, index=index,
                                      checkpoint=index >= RECORDS_PER_BANK))
        return cls(data, system, records)

    @classmethod
    def from_path(cls, path: Path | str) -> "SaveFile":
        path = Path(path)
        if path.is_dir():
            path = path / FILE_NAME
        return cls.from_bytes(path.read_bytes())

    def active_records(self) -> list[SaveRecord]:
        """Every populated valid file and checkpoint record, in physical menu order."""
        return [record for record in self.records if record.valid]

    def to_bytes(self, records: Optional[Iterable[SaveRecord]] = None,
                 *, include_system: bool = True) -> bytes:
        out = bytearray(self.data)
        if include_system and self.system.dirty:
            out[:SYSTEM_SIZE] = self.system.build()
        selected = self.records if records is None else records
        for record in selected:
            if record.dirty or records is not None:
                out[record.offset:record.offset + BLOCK_SIZE] = record.build()
        return bytes(out)


def record_label(record: SaveRecord, active: Iterable[SaveRecord] = ()) -> str:
    if record.index is None:
        return "System data"
    kind = "Checkpoint" if record.checkpoint else "File"
    base = f"{kind} {record.logical_slot + 1}"
    if record.empty:
        return base + " - empty"
    status = "valid" if record.valid else ("bad checksum" if record.magic == DATA_MAGIC else "invalid")
    loaded = " - active" if any(record is item for item in active) else ""
    return f"{base} - sequence {record.sequence} - {status}{loaded}"


def validate(save: SaveFile) -> list[str]:
    problems = []
    if save.system.magic != SYSTEM_MAGIC:
        problems.append(f"system record magic is {save.system.magic!r}, expected {SYSTEM_MAGIC!r}")
    elif save.system.version != SYSTEM_VERSION:
        problems.append(f"system record version is 0x{save.system.version:08X}")
    elif not save.system.crc_ok:
        problems.append("system record checksum is invalid")
    for record in save.records:
        if record.empty:
            continue
        where = f"{'checkpoint' if record.checkpoint else 'file'} {record.logical_slot + 1}"
        if record.magic != DATA_MAGIC:
            problems.append(f"{where}: invalid magic {record.magic!r}")
        elif record.version != DATA_VERSION:
            problems.append(f"{where}: unsupported version 0x{record.version:08X}")
        elif not record.crc_ok:
            problems.append(f"{where}: checksum is invalid")
        elif not record.sections or record.sections[0].name != "ITBL":
            problems.append(f"{where}: tagged stream is missing or incomplete")
    return problems


def main(argv: Optional[list[str]] = None) -> int:
    import argparse
    import json

    parser = argparse.ArgumentParser(description="Inspect an RFEE01 FE10_US.dat NAND save.")
    parser.add_argument("save", type=Path, help="FE10_US.dat or its containing data folder")
    parser.add_argument("--roundtrip", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    path = args.save / FILE_NAME if args.save.is_dir() else args.save
    save = SaveFile.from_bytes(path.read_bytes())
    active = save.active_records()
    rows = [{"label": record_label(record, active), "offset": record.offset,
             "sections": {section.name: section.size for section in record.sections}}
            for record in save.records]
    if args.json:
        print(json.dumps({"system_crc_ok": save.system.crc_ok, "records": rows}, indent=2))
    else:
        print("system:", "valid" if save.system.valid else "invalid")
        for row in rows:
            print(f"0x{row['offset']:06X} {row['label']}")
    problems = validate(save)
    for problem in problems:
        print("problem:", problem)
    if args.roundtrip and save.to_bytes(records=[]) != save.data:
        print("round trip: differs")
        return 1
    if args.roundtrip:
        print("round trip: ok")
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
