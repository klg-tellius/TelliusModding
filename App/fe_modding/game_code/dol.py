"""Reading and writing a GameCube/Wii DOL executable by memory address."""

from __future__ import annotations

import hashlib
import struct
from dataclasses import dataclass
from pathlib import Path

from ..exceptions import ModdingError

TEXT_SLOTS = 7
SLOTS = 18
HEADER_SIZE = 0x100


class DolError(ModdingError):
    """Raised for a malformed DOL or an access outside its sections."""


@dataclass(frozen=True)
class Section:
    index: int
    offset: int
    address: int
    size: int

    @property
    def is_text(self) -> bool:
        return self.index < TEXT_SLOTS

    def contains(self, address: int, length: int = 1) -> bool:
        return self.address <= address and address + length <= self.address + self.size


class Dol:
    """A DOL image held in memory; edits are made by RAM address."""

    def __init__(self, data: bytes | bytearray):
        if len(data) < HEADER_SIZE:
            raise DolError("File too small to be a DOL.")
        self.data = bytearray(data)
        offsets = struct.unpack(">18I", self.data[0:72])
        addresses = struct.unpack(">18I", self.data[72:144])
        sizes = struct.unpack(">18I", self.data[144:216])
        self.bss_address, self.bss_size, self.entry_point = struct.unpack(">3I", self.data[216:228])
        self.sections = [Section(i, o, a, s) for i, (o, a, s) in enumerate(zip(offsets, addresses, sizes)) if s]
        for section in self.sections:
            if section.offset + section.size > len(self.data):
                raise DolError(f"Section {section.index} runs past the end of the file.")

    @classmethod
    def open(cls, path: Path | str) -> "Dol":
        return cls(Path(path).read_bytes())

    def save(self, path: Path | str) -> None:
        Path(path).write_bytes(bytes(self.data))

    def _set_slot(self, index: int, offset: int, address: int, size: int) -> None:
        struct.pack_into(">I", self.data, index * 4, offset)
        struct.pack_into(">I", self.data, 72 + index * 4, address)
        struct.pack_into(">I", self.data, 144 + index * 4, size)

    def _reload_sections(self) -> None:
        offsets = struct.unpack(">18I", self.data[0:72])
        addresses = struct.unpack(">18I", self.data[72:144])
        sizes = struct.unpack(">18I", self.data[144:216])
        self.sections = [Section(i, o, a, s) for i, (o, a, s) in enumerate(zip(offsets, addresses, sizes)) if s]

    def has_section_at(self, address: int) -> bool:
        return any(s.address == address for s in self.sections)

    def add_text_section(self, address: int, data: bytes) -> Section:
        """Append ``data`` as a new text section loaded at ``address`` (uses a free text slot)."""
        used = {s.index for s in self.sections}
        free = [i for i in range(TEXT_SLOTS) if i not in used]
        if not free:
            raise DolError("No free text section slot.")
        for s in self.sections:
            if address < s.address + s.size and s.address < address + len(data):
                raise DolError(f"Section at {address:08X} would overlap section {s.index}.")
        self.data.extend(bytes(-len(self.data) % 0x20))
        offset = len(self.data)
        self.data.extend(data)
        self._set_slot(free[0], offset, address, len(data))
        self._reload_sections()
        return self.section_at(address)

    def remove_section_at(self, address: int) -> None:
        """Drop the section loaded at ``address``; file bytes past the last remaining section go too."""
        section = next((s for s in self.sections if s.address == address), None)
        if section is None:
            return
        self._set_slot(section.index, 0, 0, 0)
        self._reload_sections()
        end = max((s.offset + s.size for s in self.sections), default=HEADER_SIZE)
        del self.data[end:]

    def sha1(self) -> str:
        return hashlib.sha1(self.data).hexdigest()

    @property
    def text_sections(self) -> list[Section]:
        return [s for s in self.sections if s.is_text]

    def section_at(self, address: int, length: int = 1) -> Section:
        for section in self.sections:
            if section.contains(address, length):
                return section
        raise DolError(f"Address {address:08X} (+{length}) is not inside a DOL section.")

    def is_text(self, address: int) -> bool:
        return any(s.contains(address) for s in self.text_sections)

    def offset_of(self, address: int, length: int = 1) -> int:
        section = self.section_at(address, length)
        return section.offset + address - section.address

    def read(self, address: int, length: int) -> bytes:
        offset = self.offset_of(address, length)
        return bytes(self.data[offset:offset + length])

    def write(self, address: int, data: bytes) -> None:
        offset = self.offset_of(address, len(data))
        self.data[offset:offset + len(data)] = data

    def u32(self, address: int) -> int:
        return struct.unpack(">I", self.read(address, 4))[0]

    def words(self, address: int, count: int) -> tuple[int, ...]:
        return struct.unpack(f">{count}I", self.read(address, count * 4))

    def sda_bases(self) -> tuple[int | None, int | None]:
        """(r2, r13) small-data bases, from the lis/addi pairs of ``__init_registers``."""
        try:
            words = self.words(0x800032B0, 0x24)
        except DolError:
            return None, None
        values: dict[int, int] = {}
        high: dict[int, int] = {}
        for w in words:
            op, rd, ra, imm = w >> 26, (w >> 21) & 31, (w >> 16) & 31, w & 0xFFFF
            if op == 15 and ra == 0:
                high[rd] = imm << 16
            elif op == 14 and ra in high:
                values[rd] = (high[ra] + (imm - 0x10000 if imm & 0x8000 else imm)) & 0xFFFFFFFF
            elif op == 24 and rd in high:
                values[ra] = high[rd] | imm
        return values.get(2), values.get(13)
