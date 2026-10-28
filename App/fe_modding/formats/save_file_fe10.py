"""Radiant Dawn (RFEE01) Dolphin NAND saves (``FE10_US.dat``).

The unencrypted NAND file is 0x124000 bytes: one 0x4000-byte ``FE10ASYS``
system record, six 0x18000-byte file-save records and six 0x18000-byte
checkpoint records.  The six records in each bank are two rotating copies of
the three visible file slots.  Empty records are filled with ``0xff``.

Every populated record has a CRC-32 at +0x18.  The game clears that word,
computes the ordinary reflected CRC-32 across the complete record and stores
the result big-endian.  Data records contain the native tagged stream
``ITBL/BMST/MDST/UNIP/SOKO/FGPT/T  T/RELD/KZND/DEBU``.  This module deliberately
keeps the stream in place: edits replace bytes inside a decoded section and
all unrecognised/reserved bytes survive unchanged.

``ITBL`` is the save's own name tables (:meth:`SaveRecord.id_tables`): the other sections name
characters, classes, items and skills by their number in these lists, so a save stays readable after the
database is reordered.

Research reference: ``research/rd/SAVE_NOTES.md``.
"""

from __future__ import annotations

import struct
import zlib
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Optional

FILE_NAME = "FE10_US.dat"
FILE_SIZE = 0x124000
SYSTEM_SIZE = 0x4000
BLOCK_SIZE = 0x18000
COPIES_PER_BANK = 6
TOTAL_BLOCKS = 12
CONVOY_SLOTS = 316
SYSTEM_MAGIC = b"FE10ASYS"
DATA_MAGIC = b"FE10ADAT"
SYSTEM_VERSION = 0x20061002
DATA_VERSION = 0x20060920
FORMAT_VERSION = 0x11
FORGE_TAIL = 8  # bytes after a forged item's name
CRC_OFFSET = 0x18
HEADER_SIZE = 0x40
REGULAR_BASE = SYSTEM_SIZE
CHECKPOINT_BASE = SYSTEM_SIZE + COPIES_PER_BANK * BLOCK_SIZE  # 0x94000

#: ITBL's lists in file order: (name, ID prefix the file leaves out, number of the first entry).
#: Written by RFEE01 0x80242920; the four AI lists are CP_ATKSEQ/MOVSEQ/HEALSEQ/MTYPE_LIST.
ITBL_LISTS = (("character", "PID_", 1), ("class", "JID_", 1), ("item", "IID_", 1), ("skill", "SID_", 0),
              ("attack_sequence", "SEQ_", 0), ("move_sequence", "SEQ_", 0), ("heal_sequence", "SEQ_", 0),
              ("move_type", "MTYPE_", 0))

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
    """One serialized SOKO item slot (RFEE01 0x80111d68).

    Ordinary and empty slots are four bytes: the item number (ITBL ``item``) and the state word.
    A forged item (state bit 0x20) follows them with its name, NUL-terminated, and eight bytes,
    kept verbatim here (their fields are not exposed until their meanings are checked).
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
    def forged_name(self) -> str:
        """The name the player gave a forged item ("" for others)."""
        return self.forge_data[:-FORGE_TAIL - 1].decode("shift_jis", errors="replace") if self.forged else ""

    @property
    def size(self) -> int:
        return 4 + len(self.forge_data)


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
        bank_index = self.index - COPIES_PER_BANK if self.checkpoint else self.index
        return bank_index // 2

    @property
    def copy_name(self) -> str:
        if self.index is None:
            return "System"
        bank_index = self.index - COPIES_PER_BANK if self.checkpoint else self.index
        return "A" if bank_index % 2 == 0 else "B"

    def section(self, name: str) -> Optional[SaveSection]:
        wanted = name[:4]
        return next((section for section in self.sections if section.name == wanted), None)

    def section_bytes(self, name: str) -> bytes:
        section = self.section(name)
        if section is None:
            raise KeyError(f"save record has no {name} section")
        return bytes(self.raw[section.data_offset:section.end_offset])

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
            end = cursor + 4
            if forged:
                name_end = data.find(b"\0", end)
                end = len(data) + 1 if name_end < 0 else name_end + 1 + FORGE_TAIL
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
        refused because their 32-byte forge payload is not yet semantically decoded.
        """
        if not 0 <= item_number <= 0xFFFF or not 0 <= state <= 0xFFFF:
            raise ValueError("item number and state must fit in 16 bits")
        item = self.convoy_items()[slot]
        if item.forged or (item_number and state & 0x20):
            raise ValueError("forged convoy items are read-only until their FE10 payload is decoded")
        if item_number == 0:
            state = 0
        self.replace_section_bytes("SOKO", item.offset, struct.pack(">HH", item_number, state))

    def id_tables(self) -> dict[str, list[str]]:
        """ITBL as full IDs: ``{"character": ["PID_IKE", ...], "item": [...], ...}`` (see ITBL_LISTS)."""
        data = self.section_bytes("ITBL")
        tables, cursor = {}, 0
        for name, prefix, _first in ITBL_LISTS:
            if cursor + 4 > len(data):
                raise ValueError(f"ITBL ends before its {name} list")
            count = _u32(data, cursor)
            cursor += 4
            names = []
            for _ in range(count):
                end = data.find(b"\0", cursor)
                if end < 0:
                    raise ValueError(f"ITBL's {name} list is truncated")
                names.append(prefix + data[cursor:end].decode("shift_jis", errors="replace"))
                cursor = end + 1
            tables[name] = names
        if cursor != len(data):
            raise ValueError(f"ITBL has {len(data) - cursor} unexpected trailing byte(s)")
        return tables

    def id_of(self, table: str, number: int) -> Optional[str]:
        """The ID a section's ``number`` names in ITBL list ``table``; None when out of range."""
        first = next(f for name, _prefix, f in ITBL_LISTS if name == table)
        names = self.id_tables()[table]
        return names[number - first] if 0 <= number - first < len(names) else None

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
                                      checkpoint=index >= COPIES_PER_BANK))
        return cls(data, system, records)

    @classmethod
    def from_path(cls, path: Path | str) -> "SaveFile":
        path = Path(path)
        if path.is_dir():
            path = path / FILE_NAME
        return cls.from_bytes(path.read_bytes())

    def active_records(self) -> list[SaveRecord]:
        """Newest valid rotating copy for each regular/checkpoint logical slot."""
        active = []
        for checkpoint in (False, True):
            bank = [record for record in self.records if record.checkpoint == checkpoint]
            for slot in range(3):
                choices = [record for record in bank if record.logical_slot == slot and record.valid]
                if choices:
                    active.append(max(choices, key=lambda record: record.sequence))
        return active

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
    base = f"{kind} {record.logical_slot + 1}, copy {record.copy_name}"
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
        where = f"{'checkpoint' if record.checkpoint else 'file'} slot {record.logical_slot + 1} copy {record.copy_name}"
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
