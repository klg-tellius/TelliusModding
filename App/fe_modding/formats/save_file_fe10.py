"""Radiant Dawn (RFEE01) Dolphin NAND saves (``FE10_US.dat``).

The unencrypted NAND file is 0x124000 bytes: one 0x4000-byte ``FE10ASYS``
system record, six 0x18000-byte file-save records and six 0x18000-byte
checkpoint records.  Each record of a bank is one of the game's six visible
files (header +0x30 holds its number, File 1 = 0).  Empty records are filled
with ``0xff``.

The header keeps what the file menu shows: +0x35 the difficulty as the US game
names it (0 Easy, 1 Normal, 2 Hard) and +0x36 the chapter number, which BMST
+0x10 repeats.

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

import re
import struct
import zlib
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Mapping, Optional, Sequence

FILE_NAME = "FE10_US.dat"
FILE_SIZE = 0x124000
#: Each build's NAND file. The European build writes the US layout with the region letter E in its
#: magics. The Japanese file (letter J) is 0xAC000 bytes (main.dol 0x8023DE54 creates it with
#: 0xB0000 - 0x4000): the US layout cut after the first checkpoint record, so the 0x4000 system
#: record, six file records and one checkpoint at 0x94000. Checked on files the European and
#: Japanese games made in Dolphin (2026-11-16): file slot 1 is record 0 on both, and the Japanese
#: menu lists six slots.
FILE_NAMES = {"RFEE01": "FE10_US.dat", "RFEP01": "FE10_EU.dat", "RFEJ01": "FE10_JP.dat"}
#: The builds whose file this module reads.
READABLE = ("RFEE01", "RFEP01", "RFEJ01")
JP_FILE_SIZE = 0xAC000
#: Each build's file size.
FILE_SIZES = {"RFEE01": 0x124000, "RFEP01": 0x124000, "RFEJ01": JP_FILE_SIZE}
#: Each build's Wii title ID (the disc ID's first four letters in hex): the NAND data folder.
TITLE_IDS = {"RFEE01": "52464545", "RFEP01": "52464550", "RFEJ01": "5246454a"}


def data_path(disc_id: str) -> Path:
    """The save folder of ``disc_id`` under a Dolphin user folder (``Wii/title/00010000/<id>/data``)."""
    return Path("Wii/title/00010000") / TITLE_IDS[disc_id] / "data"


def file_name(disc_id: str) -> str:
    """The save file name of ``disc_id`` (``FE10_US.dat`` for an unknown one)."""
    return FILE_NAMES.get(disc_id, FILE_NAME)
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
# UNIP slot fixed header (2026-11-04, every unit of five saves within its class caps; Edward and
# Micaiah matched in Dolphin): +0x09 level, +0x0A EXP (255 = maxed), +0x1B current HP, then at
# +0x1E eight signed stat gains over PersonData's bonus + JobData's base.
UNIT_LEVEL = 0x09
UNIT_EXP = 0x0A
UNIT_HP = 0x1B
UNIT_STAT_GAINS = 0x1E
UNIT_STATS = ("hp", "str", "mag", "skl", "spd", "lck", "def", "res")
UNIT_CLASS = 0x02         # u16 class number (ITBL classes)
UNIT_ARMY = 0x04          # u8 army
UNIT_SKILLS = 0x2E        # u8 skill count, then four bytes per skill
# An item's state word: uses in the high byte, flags in the low byte (2026-11-15, 83 units of an Endgame
# file: every uses byte within the item's maximum). 0x80 is set on the equipped weapon only, 0x20 marks a
# forged item (a name and the forge payload follow); 0x10 is set on some army-0 units' first item, meaning
# not known.
ITEM_EQUIPPED = 0x80
ITEM_FORGED = 0x20
# A skill's first byte: where the unit has it from (Endgame file: 0 the character's own skills, 1 the
# class's, 2 skills taught with a scroll). The second byte is 3, 2, 1 or 0 alongside; meaning not known.
SKILL_SOURCES = {0: "Character", 1: "Class", 2: "Learned"}
# The support state, present only for characters with RelianceData slots: 12 bytes, the active partner
# (u16 character number, 0 = none), the slot count, one points byte per slot, then the three
# conversation-seen bit sets (A, B, C; 12 bytes each). get_unit_support_rank (0x8012E8BC) compares the
# points with RelianceParam's three thresholds; a rank-up adds one past the threshold.
SUPPORT_HEADER = 15
SUPPORT_PARTNER = 12
SUPPORT_SEEN_SIZE = 12

# The system record (FE10ASYS), as 0x80245888 writes it: the header's first 0x1C bytes, then these
# parts. Their sizes follow the RAM layout at 0x80427820 and add up to the 0x3B4 bytes every save holds.
# Kinds: "words" is a bit set the game keeps in big-endian 32-bit words (game bit n is bit n % 32 of word
# n / 32); "bytes" a bit array indexed byte by byte, lowest bit first.
SYSTEM_PARTS = (
    ("Clears and unlocks", 0x1C, 8, "words"),       # RAM +0x20
    ("Characters met", 0x24, 16, "words"),          # RAM +0x2C, by PersonData +0x1C (0x80245104)
    ("Conversations seen", 0x34, 0x60, "bytes"),    # RAM +0x183C, 768 bits (0x8024519C / 0x80245368)
    ("Sound Room tracks", 0x94, 16, "words"),       # RAM +0x18A0 (0x8024542C, read by 0x8026D63C)
    ("Glossary: people", 0xA4, 16, "words"),        # RAM +0x18B4, dictionary_flag DF_人物
    ("Glossary: relations", 0xB4, 8, "words"),      # RAM +0x18C8, DF_関係
    ("Glossary: affiliations", 0xBC, 8, "words"),   # RAM +0x18D4, DF_国 / DF_所属
    ("Glossary: terms", 0xC4, 8, "words"),          # RAM +0x18E0, DF_用語
    ("Glossary view", 0xCC, 16, "u16"),             # RAM +0x18E8..+0x18F7 (0x80260140 / 0x802636F0)
    ("Clear records", 0xDC, 0x2D0, "records"),      # RAM +0x18F8, 30 x 24 bytes (0x80245614)
    ("Language", 0x3AC, 1, "u8"),                   # RAM +0x1BC8, GetLanguage
    ("Checkpoint file", 0x3AD, 1, "u8"),            # RAM +0x1BC9, read by _intr
    ("Bytes +0x3AE", 0x3AE, 2, "u16"),              # RAM +0x1BCA, no reader found
    ("Word +0x3B0", 0x3B0, 4, "u32"),               # RAM +0x1BCC, no reader found
)
SYSTEM_PART_NOTES = {
    "Clears and unlocks": "Bits 0-3: the game was cleared on Easy, Normal, Hard, Maniac (set with each clear "
                          "record; any of them adds the Options menu's extra choices). Bit 5: the full opening "
                          "movie (SetAvailableGrandOpening). Bit 4 is set on cleared files; its reader was not "
                          "found. Bit 49 makes chapters load a debug deployment; no retail code sets it.",
    "Characters met": "One bit per character number (PersonData +0x1C), set whenever that character's unit "
                      "is created.",
    "Conversations seen": "768 bits in the order the game registers the names from FE10Conversation's "
                          "CONV_INFO_DATA records, then three per FE8 yell record; the Conversation Room "
                          "lists a conversation once its bit is set (TstConversationFlag).",
    "Sound Room tracks": "One bit per Sound Room track number, set the first time the track plays. The "
                         "code at 0x8019AEA8 sets all 128 at once when a game-state counter is above 2.",
    "Glossary: people": "The glossary's unlock bits: bit n is the dictionaryF.bin flag with bit n "
                        "(DF_人物 names).",
    "Glossary: relations": "Glossary relation-chart lines (DF_関係 flags).",
    "Glossary: affiliations": "Glossary affiliations (DF_国 and DF_所属 flags).",
    "Glossary: terms": "Glossary terms (DF_用語 flags).",
    "Glossary view": "Where the glossary was left: tab, people cursor, term cursor, two chart scroll pairs "
                     "(the game saves the first pair twice and never the second), chart zoom; 0xFFFF is unset.",
    "Clear records": "One record per finished playthrough, newest last; when all 30 are used the oldest is "
                     "dropped.",
    "Language": "Index of the message-folder prefix (Mess/e_..., the European languages); 1 on US files.",
    "Checkpoint file": "The file the chapter checkpoint saves to (0xFF on a new system record).",
}
SYSTEM_USED = 0x3B4
#: system bit names for "Clears and unlocks", by game bit
SYSTEM_UNLOCK_BITS = {0: "Cleared on Easy", 1: "Cleared on Normal", 2: "Cleared on Hard",
                      3: "Cleared on Maniac", 4: "Set on cleared files (reader not found)",
                      5: "Full opening movie", 49: "Debug deployment (no retail writer)"}
GLOSSARY_VIEW = ("Tab", "People cursor", "Term cursor", "Chart x", "Chart y", "Chart x (unused)",
                 "Chart y (unused)", "Chart zoom")
#: a clear record's difficulty byte (the game's own numbers; the US menu calls 0-2 Easy, Normal, Hard)
CLEAR_DIFFICULTIES = {0: "Normal", 1: "Hard", 2: "Maniac", 3: "Easy"}


@dataclass
class ClearRecord:
    """One of the system record's 30 clear records (0x80245614, filled by 0x800434A0)."""
    game_id: int        # +0x00 u64: the game state's +0x10 id, which the file headers also carry
    difficulty: int     # +0x08 s8: -1 is an empty slot
    playthrough: int    # +0x09 u8: the game state's +0x34
    character: int      # +0x0A u16: a character number (PersonData +0x1C) from 0x80287358
    turns: int          # +0x0C u32: total turns over the chapter history
    time: int           # +0x10 u64: total of the chapter history's time values

    @property
    def empty(self) -> bool:
        return self.difficulty < 0


def system_word_bit(offset: int, bit: int) -> tuple[int, int]:
    """``(file offset, mask)`` of game bit ``bit`` in a "words" set that starts at ``offset``."""
    return offset + 4 * (bit >> 5) + 3 - ((bit & 31) >> 3), 1 << (bit & 7)
# Tile record types: Path of Radiance's names (formats/save_file.TERRAIN_TYPES). Radiant Dawn files use the
# same numbers for the ones seen (6 live on 4-7e, 0x23 in records left from earlier maps); the rest are not
# checked on Radiant Dawn.
TILE_TYPES = {4: "breakable", 6: "range overlay", 7: "ballista", 9: "pit", 10: "rolling rock",
              0x21: "door opened", 0x22: "roof opened", 0x23: "chest opened", 0x24: "village visited",
              0x25: "building destroyed"}
SYSTEM_RECORD_COUNT = 30
SYSTEM_RECORD_SIZE = 0x18
SYSTEM_MAGIC = b"FE10ASYS"
DATA_MAGIC = b"FE10ADAT"
#: The magic's fifth byte names the region: A on the US file, E on the European one (FE10ESYS /
#: FE10EDAT, seen on a file the European game made in Dolphin), J presumably on the Japanese one.
#: Everything after it is the same layout.
REGION_LETTERS = {b"A": "US", b"E": "Europe", b"J": "Japan"}


def system_magic(region: bytes = b"A") -> bytes:
    return b"FE10" + region + b"SYS"


def data_magic(region: bytes = b"A") -> bytes:
    return b"FE10" + region + b"DAT"
SYSTEM_VERSION = 0x20061002
DATA_VERSION = 0x20060920
FORMAT_VERSION = 0x11
FORGE_TAIL = 8  # bytes after a forged item's name
CRC_OFFSET = 0x18
HEADER_SIZE = 0x40
REGULAR_BASE = SYSTEM_SIZE
CHECKPOINT_BASE = SYSTEM_SIZE + RECORDS_PER_BANK * BLOCK_SIZE  # 0x94000
HEADER_CHAPTER = 0x36
BMST_AFFINITY = 0x92      # state +0x92: the chapter's DivineData row (0x80061584 sets it with the chapter)
BMST_RESUME_STEP = 0x9B   # where the file resumes in its chapter; +0x9C is the preparations flag
HEADER_RESUME_STEP = 0x37  # the same step, for the file menu (Start Chapter / Continue)
RESUME_CHAPTER_END = 9    # what the game writes when it saves at a chapter's end
BMST_PREFIX = 0xD8
MAP_NAME_SIZE = 0x18      # state +0x914, the C string the file load gives load_map (0x800CD9F0)
_MAP_NAME = re.compile(rb"[be]map[0-9A-Za-z_]+\0")

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
    def forged_name(self) -> str:
        """The name the player gave a forged item ("" for others)."""
        return self.forge_data[:-FORGE_TAIL - 1].decode("shift_jis", errors="replace") if self.forged else ""

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

    @property
    def uses(self) -> int:
        return self.state >> 8

    @property
    def flags(self) -> int:
        return self.state & 0xFF


@dataclass(frozen=True)
class SavedSkill:
    """One occupied entry from a unit's 18-slot skill array."""

    skill_number: int
    value_1: int
    value_2: int

    @property
    def source(self) -> int:
        """0 the character's own, 1 the class's, 2 learned (:data:`SKILL_SOURCES`)."""
        return self.value_1


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
    support_offset: int = 0     # where the support state starts in ``raw`` (0 when the unit has none)

    @property
    def empty(self) -> bool:
        return self.person_number == 0

    @property
    def active_partner(self) -> int:
        """The character number (save ITBL) of the unit's support partner, 0 for none."""
        if not self.support_slot_count:
            return 0
        return struct.unpack_from(">H", self.raw, self.support_offset + SUPPORT_PARTNER)[0]

    @property
    def support_points(self) -> tuple[int, ...]:
        """One points byte per RelianceData slot of the character, in RelianceData order."""
        start = self.support_offset + SUPPORT_HEADER
        return tuple(self.raw[start:start + self.support_slot_count])

    @property
    def size(self) -> int:
        return len(self.raw)

    @property
    def level(self) -> int:
        return self.raw[UNIT_LEVEL] if not self.empty else 0

    @property
    def experience(self) -> int:
        """0-99; 255 once the unit can gain no more (shown as --)."""
        return self.raw[UNIT_EXP] if not self.empty else 0

    @property
    def current_hp(self) -> int:
        return self.raw[UNIT_HP] if not self.empty else 0

    @property
    def stat_gains(self) -> tuple[int, ...]:
        """The eight signed gains on top of the character's and the class's bases, in
        :data:`UNIT_STATS` order: a shown stat is PersonData bonus + JobData base + this gain."""
        if self.empty:
            return (0,) * len(UNIT_STATS)
        return tuple(struct.unpack_from(">8b", self.raw, UNIT_STAT_GAINS))


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
    """Structurally decoded ``T  T`` payload: the map's tile records (:meth:`SaveRecord.tile_records`),
    the live-record count, then a 0x200-byte block and a word whose meaning is open."""

    records: tuple[bytes, ...]
    value_after_records: int
    blob: bytes
    final_value: int


@dataclass(frozen=True)
class TileRecord:
    """One record of a map's tile table (``T  T``): x, y, type (:data:`TILE_TYPES`), subtype, four values."""

    x: int
    y: int
    type: int
    subtype: int
    values: bytes


@dataclass(frozen=True)
class RuntimeRelation:
    """One RELD relation record using two ITBL PID indices and an unsigned byte."""

    first_pid: int
    second_pid: int
    value: int


def _find_sections(raw: bytes | bytearray) -> list[SaveSection]:
    """Find the ordered RFEE01 tag stream without mistaking ITBL strings for tags."""
    if not (raw[:4] == b"FE10" and bytes(raw[4:5]) in REGION_LETTERS and raw[5:8] == b"DAT"):
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
                 checkpoint: bool = False, region: bytes = b"A"):
        self.region = region
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
        return system_magic(self.region) if self.index is None else data_magic(self.region)

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
            support_offset = cursor - start if support_count else 0
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
                class_number, army, linked_slots, skills, tuple(items), support_count, support_offset))

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
                end = name_end + 1 + FORGE_TAIL
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

    def id_name_lists(self) -> dict[str, list[str]]:
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

    def id_name(self, table: str, number: int) -> Optional[str]:
        """The ID a section's ``number`` names in ITBL list ``table``; None when out of range."""
        first = next(f for name, _prefix, f in ITBL_LISTS if name == table)
        names = self.id_name_lists()[table]
        return names[number - first] if 0 <= number - first < len(names) else None

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

    def tile_records(self) -> tuple[list[TileRecord], int]:
        """``T  T``'s 128 tile records and the live count, laid out as Path of Radiance's 64 (AddTT):
        x, y, type, subtype and four values. A file saved on 4-7e holds eight live range-overlay records
        (type 6) inside the map's grid; records past the count keep stale bytes: records of earlier maps
        (chest opened, 0x23) or RAM addresses on files saved between chapters."""
        state = self.tactical_table_state()
        return [TileRecord(*struct.unpack(">bbBB4s", raw)) for raw in state.records], state.value_after_records

    def set_tile_record(self, index: int, record: "TileRecord") -> None:
        if not 0 <= index < TACTICAL_RECORD_COUNT:
            raise IndexError(f"tile record must be 0..{TACTICAL_RECORD_COUNT - 1}")
        if not -0x80 <= record.x <= 0x7F or not -0x80 <= record.y <= 0x7F:
            raise ValueError("x and y must be -128..127")
        if not 0 <= record.type <= 0xFF or not 0 <= record.subtype <= 0xFF or len(record.values) != 4:
            raise ValueError("type and subtype are bytes; values are four bytes")
        self.replace_section_bytes("T  T", index * TACTICAL_RECORD_SIZE,
                                   struct.pack(">bbBB4s", record.x, record.y, record.type, record.subtype,
                                               bytes(record.values)))

    def set_tile_count(self, count: int) -> None:
        if not 0 <= count <= TACTICAL_RECORD_COUNT:
            raise ValueError(f"the tile count must be 0..{TACTICAL_RECORD_COUNT}")
        self.replace_section_bytes("T  T", TACTICAL_RECORD_COUNT * TACTICAL_RECORD_SIZE, struct.pack(">I", count))

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

    def set_unit_state(self, unit: SavedUnit, *, level: Optional[int] = None, experience: Optional[int] = None,
                       current_hp: Optional[int] = None, stat_gains: Optional[Sequence[int]] = None) -> None:
        """Edit one unit's level, EXP, current HP and stat gains in place (the record's size is unchanged).
        ``unit`` comes from :meth:`unit_records`. The game shows a stat over its class cap at the cap
        (Dolphin, 2026-11-04: Edward set to HP 40, Skill 21, Speed 22 showed 30, 20, 20 as a Myrmidon)."""
        if unit.empty:
            raise ValueError("this UNIP slot holds no unit")
        section = self.section("UNIP")
        if section is None:
            raise KeyError("save record has no UNIP section")
        edits = []
        if level is not None:
            if not 1 <= level <= 40:
                raise ValueError("level must be 1..40")
            edits.append((UNIT_LEVEL, bytes([level])))
        if experience is not None:
            if not (0 <= experience <= 99 or experience == 255):
                raise ValueError("EXP must be 0..99, or 255 for a unit that gains no more")
            edits.append((UNIT_EXP, bytes([experience])))
        if current_hp is not None:
            if not 1 <= current_hp <= 255:
                raise ValueError("current HP must be 1..255")
            edits.append((UNIT_HP, bytes([current_hp])))
        if stat_gains is not None:
            gains = list(stat_gains)
            if len(gains) != len(UNIT_STATS) or any(not -128 <= g <= 127 for g in gains):
                raise ValueError(f"stat gains are {len(UNIT_STATS)} values in -128..127")
            edits.append((UNIT_STAT_GAINS, struct.pack(">8b", *gains)))
        for offset, data in edits:
            self.replace_section_bytes("UNIP", unit.offset + offset, data)

    def _table_size(self, kind: str) -> int:
        tables = self.id_tables()
        return len({"character": tables.characters, "class": tables.classes, "item": tables.items,
                    "skill": tables.skills}[kind])

    def _require_unit(self, unit: SavedUnit) -> SaveSection:
        if unit.empty:
            raise ValueError("this UNIP slot holds no unit")
        section = self.section("UNIP")
        if section is None:
            raise KeyError("save record has no UNIP section")
        return section

    def set_unit_class(self, unit: SavedUnit, class_number: int) -> None:
        """Change a unit's class (a number in the save's class list). Stats are kept as gains over the
        class base, so the shown stats move with the new class's bases; class skills stay as saved."""
        self._require_unit(unit)
        if not 1 <= class_number <= self._table_size("class"):
            raise ValueError(f"class number must be 1..{self._table_size('class')}")
        self.replace_section_bytes("UNIP", unit.offset + UNIT_CLASS, struct.pack(">H", class_number))

    def set_unit_army(self, unit: SavedUnit, army: int) -> None:
        self._require_unit(unit)
        if not 0 <= army <= 0xFF:
            raise ValueError("army must be 0..255")
        self.replace_section_bytes("UNIP", unit.offset + UNIT_ARMY, bytes([army]))

    def set_unit_item(self, unit: SavedUnit, slot: int, item_number: int, uses: int, flags: int) -> None:
        """Replace one of a unit's seven items in place (an empty slot is ``item_number`` 0). Forged items
        are kept: their record is longer, and its forge belongs to the convoy's forge editing."""
        section = self._require_unit(unit)
        if not 0 <= slot < len(unit.items):
            raise IndexError(f"item slot must be 0..{len(unit.items) - 1}")
        item = unit.items[slot]
        if item.forged or (item_number and flags & ITEM_FORGED):
            raise ValueError("forged items can't be changed here")
        if not 0 <= item_number <= self._table_size("item"):
            raise ValueError(f"item number must be 0..{self._table_size('item')}")
        if not 0 <= uses <= 0xFF or not 0 <= flags <= 0xFF:
            raise ValueError("uses and flags must be 0..255")
        state = 0 if item_number == 0 else uses << 8 | flags
        self.replace_section_bytes("UNIP", item.offset - section.data_offset,
                                   struct.pack(">HH", item_number, state))

    def set_unit_skills(self, unit: SavedUnit, skills: Sequence[SavedSkill]) -> None:
        """Replace a unit's skill list (at most 18). The record changes size; read the units again."""
        section = self._require_unit(unit)
        skills = list(skills)
        if len(skills) > UNIT_SKILL_SLOTS:
            raise ValueError(f"a unit has at most {UNIT_SKILL_SLOTS} skills")
        count = self._table_size("skill")
        for skill in skills:
            if not 0 <= skill.skill_number < count:
                raise ValueError(f"skill number must be 0..{count - 1}")
            if not 0 <= skill.value_1 <= 0xFF or not 0 <= skill.value_2 <= 0xFF:
                raise ValueError("a skill's two bytes must be 0..255")
        start = section.data_offset + unit.offset + UNIT_SKILLS
        new = bytes([len(skills)]) + b"".join(struct.pack(">HBB", s.skill_number, s.value_1, s.value_2)
                                              for s in skills)
        self._replace_variable_bytes(start, start + 1 + 4 * len(unit.skills), new)

    def set_unit_support_points(self, unit: SavedUnit, slot: int, points: int) -> None:
        """Set the points of one RelianceData slot of a unit (see :func:`support_rank`)."""
        self._require_unit(unit)
        if not 0 <= slot < unit.support_slot_count:
            raise IndexError("this character has no such support slot")
        if not 0 <= points <= 0xFF:
            raise ValueError("support points must be 0..255")
        self.replace_section_bytes("UNIP", unit.offset + unit.support_offset + SUPPORT_HEADER + slot,
                                   bytes([points]))

    def copy_unit(self, unit: SavedUnit, support_slot_counts: Mapping[int, int]) -> int:
        """Copy ``unit`` into the first empty UNIP slot and return that slot. The copy is linked to
        no unit (its three link bytes cleared) and has no active support partner; everything else,
        items and forge records included, is the original's bytes."""
        self._require_unit(unit)
        units = self.unit_records(support_slot_counts)
        target = next((u for u in units if u.empty), None)
        if target is None:
            raise ValueError("Every unit slot is in use.")
        clone = bytearray(unit.raw)
        clone[5:8] = b"\x00\x00\x00"
        if unit.support_slot_count:
            struct.pack_into(">H", clone, unit.support_offset + SUPPORT_PARTNER, 0)
        section = self.section("UNIP")
        start = section.data_offset + target.offset
        self._replace_variable_bytes(start, start + len(target.raw), bytes(clone))
        return target.slot

    def remove_unit(self, unit: SavedUnit, support_slot_counts: Mapping[int, int]) -> None:
        """Empty ``unit``'s UNIP slot. Refused while another unit links to it (the link bytes hold
        slot numbers counted from 1), so no unit is left pointing at an empty slot."""
        self._require_unit(unit)
        number = unit.slot + 1
        linked = [u.slot for u in self.unit_records(support_slot_counts)
                  if not u.empty and u.slot != unit.slot and number in u.linked_slots]
        if linked:
            raise ValueError(f"Unit slot {number} is linked with slot {', '.join(str(s + 1) for s in linked)}; "
                             "separate them in the game first.")
        section = self.section("UNIP")
        start = section.data_offset + unit.offset
        self._replace_variable_bytes(start, start + len(unit.raw), b"\x00\x00")

    def set_unit_active_partner(self, unit: SavedUnit, person_number: int) -> None:
        """Set a unit's support partner (a character number in the save's list, 0 for none)."""
        self._require_unit(unit)
        if not unit.support_slot_count:
            raise ValueError("this character has no supports")
        if not 0 <= person_number <= self._table_size("character"):
            raise ValueError(f"character number must be 0..{self._table_size('character')}")
        self.replace_section_bytes("UNIP", unit.offset + unit.support_offset + SUPPORT_PARTNER,
                                   struct.pack(">H", person_number))

    def clear_records(self) -> list[ClearRecord]:
        """The system record's 30 clear records (:class:`ClearRecord`), empty slots included."""
        data = self.system_part("Clear records")
        out = []
        for i in range(SYSTEM_RECORD_COUNT):
            row = data[i * SYSTEM_RECORD_SIZE:(i + 1) * SYSTEM_RECORD_SIZE]
            game_id, difficulty, playthrough, character, turns, time = struct.unpack(">QbBHIQ", row)
            out.append(ClearRecord(game_id, difficulty, playthrough, character, turns, time))
        return out

    def system_bit(self, name: str, bit: int) -> bool:
        """Game bit ``bit`` of a bit-set part, numbered as the game numbers it (see :data:`SYSTEM_PARTS`)."""
        _, offset, size, kind = _system_part(name)
        if not 0 <= bit < 8 * size:
            raise ValueError(f"{name} has bits 0-{8 * size - 1}")
        at, mask = system_word_bit(offset, bit) if kind == "words" else (offset + (bit >> 3), 1 << (bit & 7))
        return bool(self.raw[at] & mask)

    def set_system_bit(self, name: str, bit: int, on: bool) -> None:
        _, offset, size, kind = _system_part(name)
        if not 0 <= bit < 8 * size:
            raise ValueError(f"{name} has bits 0-{8 * size - 1}")
        at, mask = system_word_bit(offset, bit) if kind == "words" else (offset + (bit >> 3), 1 << (bit & 7))
        value = self.raw[at] | mask if on else self.raw[at] & ~mask
        self.set_system_bytes(at, bytes([value]))

    def system_part(self, name: str) -> bytes:
        """One part of the system record (:data:`SYSTEM_PARTS`) by its name."""
        _, offset, size, _ = _system_part(name)
        return bytes(self.raw[offset:offset + size])

    def set_system_part(self, name: str, data: bytes) -> None:
        _, offset, size, _ = _system_part(name)
        if len(data) != size:
            raise ValueError(f"{name} is {size} bytes")
        self.set_system_bytes(offset, data)

    def system_value(self, offset: int, size: int) -> int:
        """A big-endian value inside the system record's parts."""
        if not SYSTEM_PARTS[0][1] <= offset <= offset + size <= SYSTEM_USED:
            raise ValueError("outside the system record's parts")
        return int.from_bytes(self.raw[offset:offset + size], "big")

    def set_system_value(self, offset: int, size: int, value: int) -> None:
        if not 0 <= value < 1 << (8 * size):
            raise ValueError(f"value must fit in {8 * size} bits")
        self.set_system_bytes(offset, value.to_bytes(size, "big"))

    def set_system_bytes(self, offset: int, data: bytes) -> None:
        if self.index is not None:
            raise ValueError("only the system record has these parts")
        if not SYSTEM_PARTS[0][1] <= offset <= offset + len(data) <= SYSTEM_USED:
            raise ValueError("outside the system record's parts")
        if self.raw[offset:offset + len(data)] != data:
            self.raw[offset:offset + len(data)] = data
            self.dirty = True

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
        self.set_header_u8(HEADER_CHAPTER, value)  # what the file menu shows

    def _map_name_offset(self) -> Optional[int]:
        """Where BMST holds the map folder; its place follows parts of variable size."""
        match = _MAP_NAME.search(self.section_bytes("BMST"), BMST_PREFIX)
        return match.start() if match else None

    @property
    def map_name(self) -> Optional[str]:
        """The map folder the file loads (``bmap0407a``); None on a file that has none yet."""
        at = self._map_name_offset()
        if at is None:
            return None
        return self.section_bytes("BMST")[at:at + MAP_NAME_SIZE].split(b"\0")[0].decode("ascii")

    def move_to_chapter(self, number: int, map_name: str, affinity_row: int) -> None:
        """Make the file open chapter ``number``: the game loads the map by the saved name, not by
        the chapter, and keeps the chapter's affinity row beside it."""
        at = self._map_name_offset()
        if at is None:
            raise ValueError("This file holds no map name.")
        encoded = map_name.encode("ascii")
        if len(encoded) >= MAP_NAME_SIZE:
            raise ValueError(f"{map_name} is too long for a save file.")
        self.replace_section_bytes("BMST", at, encoded.ljust(MAP_NAME_SIZE, b"\0"))
        self.replace_section_bytes("BMST", BMST_AFFINITY, bytes([affinity_row]))
        self.chapter_number = number

    @property
    def resume_step(self) -> int:
        """Where in its chapter the file resumes (BMST +0x9B, mirrored in header +0x37 for the file
        menu). Files the game wrote: 2 in a base or preparations (with :attr:`in_preparations` set),
        9 after a chapter's end, 0x0B after a chapter's opening event (4-P, right after the army split)."""
        return self._bmst_value(BMST_RESUME_STEP, 1)

    @property
    def in_preparations(self) -> bool:
        """BMST +0x9C: set on files saved in a base or the preparations screen."""
        return bool(self._bmst_value(BMST_RESUME_STEP + 1, 1))

    def start_at_chapter(self, number: int, previous_map: str, affinity_row: int) -> None:
        """Make the file start chapter ``number`` from its beginning, as a file the game saved at the
        end of the chapter before: the file menu offers Start Chapter and the chapter's opening plays.
        :meth:`move_to_chapter` alone keeps a preparations file's resume point, so the game reopens the
        saved preparations instead. ``previous_map`` is the finished chapter's map folder (the game keeps
        it in a chapter-end file). Checked in Dolphin: File 5 of an Endgame save started 4-P this way."""
        self.move_to_chapter(number, previous_map, affinity_row)
        self.army_phase = 1
        self._set_bmst_value(BMST_RESUME_STEP, 1, RESUME_CHAPTER_END)
        self._set_bmst_value(BMST_RESUME_STEP + 1, 1, 0)
        self.set_header_u8(HEADER_RESUME_STEP, RESUME_CHAPTER_END)

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


def find_in(folder: Path) -> Path:
    """The save file in a NAND data folder: whichever build's file is there (US first)."""
    for name in FILE_NAMES.values():
        if (folder / name).is_file():
            return folder / name
    return folder / FILE_NAME


class SaveFile:
    """The complete unencrypted RFEE01 NAND data file."""

    def __init__(self, data: bytes, system: SaveRecord, records: list[SaveRecord]):
        self.data = bytes(data)
        self.system = system
        self.records = records

    @classmethod
    def from_bytes(cls, data: bytes) -> "SaveFile":
        if len(data) not in (FILE_SIZE, JP_FILE_SIZE):
            raise ValueError(f"A Radiant Dawn save must be 0x{FILE_SIZE:X} bytes (0x{JP_FILE_SIZE:X} on the "
                             f"Japanese disc), found 0x{len(data):X}")
        blocks = TOTAL_BLOCKS if len(data) == FILE_SIZE else RECORDS_PER_BANK + 1
        region = data[4:5] if data[4:5] in REGION_LETTERS else b"A"
        system = SaveRecord(data[:SYSTEM_SIZE], 0, region=region)
        records = []
        for index in range(blocks):
            offset = SYSTEM_SIZE + index * BLOCK_SIZE
            records.append(SaveRecord(data[offset:offset + BLOCK_SIZE], offset, index=index,
                                      checkpoint=index >= RECORDS_PER_BANK, region=region))
        return cls(data, system, records)

    @classmethod
    def from_path(cls, path: Path | str) -> "SaveFile":
        path = Path(path)
        if path.is_dir():
            path = find_in(path)
        return cls.from_bytes(path.read_bytes())

    def active_records(self) -> list[SaveRecord]:
        """Every valid record: each one is a file of its own."""
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


def _system_part(name: str) -> tuple[str, int, int, str]:
    part = next((p for p in SYSTEM_PARTS if p[0] == name), None)
    if part is None:
        raise KeyError(f"the system record has no part {name!r}")
    return part


def support_rank(points: int, thresholds: Sequence[int]) -> int:
    """0 (none) to 3 (A): how many of RelianceParam's thresholds (C, B, A) the points are past. Points
    exactly at a threshold wait for the rank-up (the support menu's), so they count as the rank below."""
    return sum(points > threshold for threshold in thresholds)


def rank_points(rank: int, thresholds: Sequence[int]) -> int:
    """The points the game holds just after a rank-up to ``rank`` (0 for no support)."""
    if not 0 <= rank <= len(thresholds):
        raise ValueError(f"rank must be 0..{len(thresholds)}")
    return thresholds[rank - 1] + 1 if rank else 0


def chapter_ids_for_map(map_name: Optional[str]) -> list[str]:
    """Chapter ids whose script may own a file's flags, best first: ``bmap0407a`` gives ``0407a`` then
    ``0407``; ``emap0401a`` (4-P's opening event) gives ``0401a`` then ``0401``."""
    if not map_name:
        return []
    key = re.sub(r"^[be]map", "", map_name).split("_")[0]
    ids = [key]
    while key and key[-1].isalpha() and len(key) > 4:
        key = key[:-1]
        ids.append(key)
    return ids


def record_label(record: SaveRecord, active: Iterable[SaveRecord] = ()) -> str:
    if record.index is None:
        return "System data"
    kind = "Checkpoint" if record.checkpoint else "File"
    base = f"{kind} {record.logical_slot + 1}"
    if record.empty:
        return base + " - empty"
    status = "valid" if record.valid else ("bad checksum" if record.magic == record.expected_magic else "invalid")
    loaded = " - active" if any(record is item for item in active) else ""
    return f"{base} - sequence {record.sequence} - {status}{loaded}"


def validate(save: SaveFile) -> list[str]:
    problems = []
    if save.system.magic != save.system.expected_magic:
        problems.append(f"system record magic is {save.system.magic!r}, expected "
                        f"{save.system.expected_magic!r}")
    elif save.system.version != SYSTEM_VERSION:
        problems.append(f"system record version is 0x{save.system.version:08X}")
    elif not save.system.crc_ok:
        problems.append("system record checksum is invalid")
    for record in save.records:
        if record.empty:
            continue
        where = f"{'checkpoint' if record.checkpoint else 'file'} slot {record.logical_slot + 1}"
        if record.magic != record.expected_magic:
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

    parser = argparse.ArgumentParser(description="Inspect a Radiant Dawn FE10_US.dat or FE10_EU.dat NAND save.")
    parser.add_argument("save", type=Path, help="FE10_US.dat or its containing data folder")
    parser.add_argument("--roundtrip", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    path = find_in(args.save) if args.save.is_dir() else args.save
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
