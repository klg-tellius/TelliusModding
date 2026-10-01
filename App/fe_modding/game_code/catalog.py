"""Patch and tunable definitions, and the engine that applies them to a DOL.

Two kinds of entry, both defined per game version:

- :class:`Patch` - an on/off change made of byte edits (``original`` -> ``patched``).
- :class:`Tunable` - a number stored in an instruction immediate or a data word.

A site is found at its stored address when the bytes there are what the catalog expects. When
they are not (an unlisted revision, or a version the entry has no address for) and the site
carries a :class:`Signature`, the DOL's text is scanned for the masked instruction window. A
site that is found nowhere makes the entry unavailable; nothing is ever written blind.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass, field
from enum import Enum

from .dol import Dol, DolError
from .ppc import mask_words
from .versions import GameVersion


class State(Enum):
    UNAVAILABLE = "unavailable"    # no site for this version, or a site that was not found
    ORIGINAL = "original"          # retail bytes (patch off / tunable at its default)
    APPLIED = "applied"            # patch on
    CUSTOM = "custom"              # tunable set to a non-default value
    CONFLICT = "conflict"          # bytes match neither the retail nor the patched form


@dataclass(frozen=True)
class Status:
    state: State
    detail: str = ""
    value: float | int | None = None


@dataclass(frozen=True)
class Signature:
    """A masked instruction window that locates a site without a fixed address.

    ``words`` are :func:`ppc.mask_words` output; ``offset`` is the byte distance from the start
    of the window to the site."""
    words: tuple[int, ...]
    offset: int = 0


@dataclass(frozen=True)
class Edit:
    """One byte range of a patch."""
    address: int
    original: bytes
    patched: bytes
    signature: Signature | None = None
    wild: tuple[tuple[int, int], ...] = ()   # (offset, length) ranges a tunable may change after install

    def __post_init__(self):
        if len(self.original) != len(self.patched):
            raise ValueError("A patch edit must not change length.")

    @property
    def all_wild(self) -> bool:
        return sum(length for _, length in self.wild) >= len(self.original)

    def matches(self, seen: bytes, reference: bytes) -> bool:
        if not self.wild:
            return seen == reference
        keep = bytearray([255]) * len(reference)
        for offset, length in self.wild:
            keep[offset:offset + length] = bytes(length)
        return all((a ^ b) & k == 0 for a, b, k in zip(seen, reference, keep))


CAVE_ADDRESS = 0x80001800    # unused OS-reserved RAM (where Gecko's code handler lives); holds new code
CAVE_SIZE = 0x1800


def in_cave(address: int, length: int = 1) -> bool:
    return CAVE_ADDRESS <= address and address + length <= CAVE_ADDRESS + CAVE_SIZE


KINDS = {"imm16s": 2, "imm16u": 2, "u8": 1, "u16": 2, "u32": 4, "f32": 4}


@dataclass(frozen=True)
class Field:
    """A number held at ``address``.

    ``imm16s``/``imm16u`` are the low halfword of an instruction (signed / unsigned); the
    instruction's other half, ``expect`` (the two high bytes), is checked before every access.
    The other kinds are big-endian data words."""
    address: int
    kind: str
    expect: bytes = b""
    signature: Signature | None = None

    @property
    def width(self) -> int:
        return KINDS[self.kind]

    @property
    def span(self) -> int:
        return 4 if self.kind.startswith("imm16") else self.width


@dataclass(frozen=True)
class Patch:
    id: str
    group: str
    name: str
    description: str
    versions: dict[str, tuple[Edit, ...]]
    internal: bool = False      # a hook that tunables depend on; never listed on its own


@dataclass(frozen=True)
class Tunable:
    id: str
    group: str
    name: str
    description: str
    default: float
    minimum: float
    maximum: float
    versions: dict[str, tuple[Field, ...]]
    unit: str = ""
    requires: tuple[Patch, ...] = ()     # patches (hooks, stubs) that must be on for the value to act


Entry = Patch | Tunable


# -- locating sites --------------------------------------------------------------------------------
class _TextIndex:
    """Masked text of a DOL, searchable by instruction window."""

    def __init__(self, dol: Dol):
        sda = dol.sda_bases()
        self.blocks: list[tuple[int, list[int]]] = []
        self.first: dict[int, list[tuple[int, int]]] = {}
        for section in dol.text_sections:
            words = list(dol.words(section.address, section.size // 4))
            masked = mask_words(words, sda)
            block = len(self.blocks)
            self.blocks.append((section.address, masked))
            for i, w in enumerate(masked):
                self.first.setdefault(w, []).append((block, i))

    def find(self, signature: Signature) -> list[int]:
        found = []
        n = len(signature.words)
        for block, i in self.first.get(signature.words[0], ()):
            address, masked = self.blocks[block]
            if masked[i:i + n] == list(signature.words):
                found.append(address + i * 4 + signature.offset)
        return found


def make_signature(dol: Dol, address: int, before: int = 4, after: int = 4) -> Signature:
    """Signature of the window around ``address`` (``before``/``after`` instructions)."""
    start = address - before * 4
    words = mask_words(dol.words(start, before + after), dol.sda_bases())
    return Signature(tuple(words), before * 4)


# -- the engine ------------------------------------------------------------------------------------
class Session:
    """A DOL, its identified version, and the operations on catalog entries."""

    def __init__(self, dol: Dol, version: GameVersion | None):
        self.dol = dol
        self.version = version
        self._index: _TextIndex | None = None

    # locating
    def _search(self, signature: Signature) -> int | None:
        if self._index is None:
            self._index = _TextIndex(self.dol)
        hits = self._index.find(signature)
        return hits[0] if len(hits) == 1 else None

    def _sites(self, entry: Entry) -> tuple:
        """This version's sites; when the entry has none for it, the signature-carrying sites of
        another version (located by signature only, see :meth:`_foreign`)."""
        if self.version is not None and self.version.code in entry.versions:
            return tuple(entry.versions[self.version.code])
        for sites in entry.versions.values():
            if sites and all(s.signature is not None for s in sites):
                return tuple(sites)
        return ()

    def _foreign(self, entry: Entry) -> bool:
        return self.version is None or self.version.code not in entry.versions

    def _try_read(self, address: int, length: int) -> bytes | None:
        if in_cave(address, length) and not self.dol.has_section_at(CAVE_ADDRESS):
            return bytes(length)            # the cave is created on first write; until then it is zeros
        try:
            return self.dol.read(address, length)
        except DolError:
            return None

    def _write(self, address: int, data: bytes) -> None:
        if in_cave(address, len(data)) and not self.dol.has_section_at(CAVE_ADDRESS):
            self.dol.add_text_section(CAVE_ADDRESS, bytes(CAVE_SIZE))
        self.dol.write(address, data)

    def _prune_cave(self) -> None:
        """Remove the cave section once every byte of it is back to zero."""
        if self.dol.has_section_at(CAVE_ADDRESS) and not any(self.dol.read(CAVE_ADDRESS, CAVE_SIZE)):
            self.dol.remove_section_at(CAVE_ADDRESS)

    def _locate_edit(self, edit: Edit, foreign: bool = False) -> int | None:
        seen = None if foreign else self._try_read(edit.address, len(edit.original))
        if seen is not None and self._known(edit, seen):
            return edit.address
        if edit.signature is not None:
            found = self._search(edit.signature)
            if found is not None and self._known(edit, self._try_read(found, len(edit.original))):
                return found
        return edit.address if seen is not None else None

    @staticmethod
    def _known(edit: Edit, seen: bytes | None) -> bool:
        return seen is not None and (edit.matches(seen, edit.original) or edit.matches(seen, edit.patched))

    def _locate_field(self, f: Field, foreign: bool = False) -> int | None:
        if not foreign and self._field_ok(f, f.address):
            return f.address
        if f.signature is not None:
            found = self._search(f.signature)
            if found is not None and self._field_ok(f, found):
                return found
        return None

    def _field_ok(self, f: Field, address: int) -> bool:
        seen = self._try_read(address, f.span)
        if seen is None:
            return False
        return not f.expect or seen[:len(f.expect)] == f.expect

    # patches
    def patch_status(self, patch: Patch) -> Status:
        sites = self._sites(patch)
        if not sites:
            return Status(State.UNAVAILABLE, "No site for this version.")
        original = applied = 0
        sites = [e for e in sites if not e.all_wild]        # a fully tunable edit says nothing on its own
        for edit in sites:
            address = self._locate_edit(edit, self._foreign(patch))
            seen = self._try_read(address, len(edit.original)) if address is not None else None
            if seen is not None and edit.matches(seen, edit.original):
                original += 1
            elif seen is not None and edit.matches(seen, edit.patched):
                applied += 1
            else:
                where = f"{address:08X}" if address is not None else f"{edit.address:08X}"
                return Status(State.CONFLICT, f"Unexpected bytes at {where}.")
        if applied == len(sites):
            return Status(State.APPLIED)
        if original == len(sites):
            return Status(State.ORIGINAL)
        return Status(State.CONFLICT, "Only some of the patch's edits are applied.")

    def set_patch(self, patch: Patch, enabled: bool) -> None:
        status = self.patch_status(patch)
        if status.state in (State.UNAVAILABLE, State.CONFLICT):
            raise DolError(f"{patch.name}: {status.detail}")
        if status.state == (State.APPLIED if enabled else State.ORIGINAL):
            return
        for edit in self._sites(patch):
            address = self._locate_edit(edit, self._foreign(patch))
            self._write(address, edit.patched if enabled else edit.original)
        self._prune_cave()

    # tunables
    def _read_field(self, f: Field, address: int) -> float:
        raw = self.dol.read(address, f.span)
        if f.kind == "imm16s":
            return struct.unpack(">h", raw[2:])[0]
        if f.kind == "imm16u":
            return struct.unpack(">H", raw[2:])[0]
        if f.kind == "u8":
            return raw[0]
        if f.kind == "u16":
            return struct.unpack(">H", raw)[0]
        if f.kind == "u32":
            return struct.unpack(">I", raw)[0]
        return struct.unpack(">f", raw)[0]

    def _pack(self, f: Field, address: int, value: float) -> bytes:
        if f.kind.startswith("imm16"):
            fmt = ">h" if f.kind == "imm16s" else ">H"
            return self.dol.read(address, 2) + struct.pack(fmt, int(value))
        if f.kind == "f32":
            return struct.pack(">f", value)
        return int(value).to_bytes(f.width, "big")

    def tunable_status(self, tunable: Tunable) -> Status:
        sites = self._sites(tunable)
        if not sites:
            return Status(State.UNAVAILABLE, "No site for this version.")
        for required in tunable.requires:
            needed = self.patch_status(required)
            if needed.state in (State.UNAVAILABLE, State.CONFLICT):
                return Status(needed.state, needed.detail)
            if needed.state == State.ORIGINAL:
                return self._unhooked_status(tunable, sites)
        values = []
        for f in sites:
            address = self._locate_field(f, self._foreign(tunable))
            if address is None:
                return Status(State.UNAVAILABLE, f"Site {f.address:08X} not found.")
            values.append(self._read_field(f, address))
        if len(set(values)) > 1:
            return Status(State.CONFLICT, "The tunable's sites hold different values.", values[0])
        value = values[0]
        state = State.ORIGINAL if value == tunable.default else State.CUSTOM
        return Status(state, value=value)

    def _unhooked_status(self, tunable: Tunable, sites: tuple[Field, ...]) -> Status:
        """With its hook off a tunable is vanilla, unless its field lives in untouched vanilla code
        (then it may still hold a value written earlier)."""
        values = set()
        for f in sites:
            address = self._locate_field(f, self._foreign(tunable))
            if address is None or CAVE_ADDRESS <= address < CAVE_ADDRESS + CAVE_SIZE:
                return Status(State.ORIGINAL, value=tunable.default)     # lives in the cave
            try:
                values.add(self._read_field(f, address))
            except (DolError, TypeError):      # the field lives in the cave, which does not exist yet
                return Status(State.ORIGINAL, value=tunable.default)
        if len(values) == 1 and (value := values.pop()) != tunable.default:
            return Status(State.CUSTOM, value=value)
        return Status(State.ORIGINAL, value=tunable.default)

    def set_tunable(self, tunable: Tunable, value: float) -> None:
        if not tunable.minimum <= value <= tunable.maximum:
            raise DolError(f"{tunable.name}: {value} is outside {tunable.minimum}..{tunable.maximum}.")
        for required in tunable.requires:
            if self.patch_status(required).state == State.ORIGINAL:
                self.set_patch(required, True)
        status = self.tunable_status(tunable)
        if status.state in (State.UNAVAILABLE, State.CONFLICT):
            raise DolError(f"{tunable.name}: {status.detail}")
        for f in self._sites(tunable):
            address = self._locate_field(f, self._foreign(tunable))
            self._write(address, self._pack(f, address, value))

    # dispatch
    def status(self, entry: Entry) -> Status:
        return self.patch_status(entry) if isinstance(entry, Patch) else self.tunable_status(entry)

    def reset(self, entry: Entry) -> None:
        if isinstance(entry, Patch):
            self.set_patch(entry, False)
        elif self.tunable_status(entry).state != State.ORIGINAL:
            self.set_tunable(entry, entry.default)


@dataclass
class Catalog:
    entries: dict[str, Entry] = field(default_factory=dict)

    def add(self, entry: Entry) -> Entry:
        if entry.id in self.entries:
            raise ValueError(f"Duplicate catalog id {entry.id}")
        self.entries[entry.id] = entry
        return entry

    def groups(self) -> dict[str, list[Entry]]:
        grouped: dict[str, list[Entry]] = {}
        for entry in self.entries.values():
            grouped.setdefault(entry.group, []).append(entry)
        return grouped


CATALOG = Catalog()
