"""``FE10Conversation.cms``: Radiant Dawn's conversation lists (LZ10 around the data container of
``fe8data``). Three tables, then the string pool:

``CONV_INFO_DATA``: the base "Info" conversations, a count then 48-byte records::

    +0x00 chapter (C0105)   +0x04 title key (MID_0105_街の中で, in common.m: "In Town")
    +0x08 message ID played (MID_0105_街の中で会話, in the chapter's Mess file)
    +0x0C seen flag (FLG_0105_街の中で)   +0x10 seven PIDs (the characters shown; null pads)
    +0x2C a number 1-3 (not identified; 1 is the most common)

  Every record also has its own symbol ``CONV_INFO_DATA_<chapter>_<name>``. The base menu builds that
  name from the chapter and the name of each base event the chapter script registered (event kind
  0x0E) and looks the record up by it (US ``FUN_8024044c``; symbols are found through the engine's
  name hash, ``FUN_80076f54``). A record without its symbol is never listed in a base.
  The Extras Conversation Room lists every record and checks its flag (``FUN_8027ce60``).

``CONVERSATION_FE8_YELL_DATA``: the Path of Radiance support conversations the Conversation Room
replays (``FUN_8027d14c``, text in ``Mess/e_yell_fe8.m``), a count then 44-byte records::

    +0x00 MPID of one character   +0x04 MPID of the other
    +0x08, +0x10, +0x18 the three conversations in order (vanilla IDs end _A, _B, _C), each
                          followed by a null word
    +0x20, +0x24, +0x28 their flags (FLG_8_..._A, _B, _C)

``CONVERSATION_MINI_YELL_DATA``: the support chat lines. A count of characters; per character its
PID, a count of partners, the Mess file of its lines (``Mess/yell_mini_N.m``, the language prefix is
added at run time, ``FUN_80047b18``), then per partner ``(partner PID, line said, line answered)``.

Every table and every string reads back byte for byte (``test_fe10_conversation_data``).
"""
from __future__ import annotations

import struct
from dataclasses import dataclass, field
from typing import Optional

from . import fe8data
from .fe10data import delete_bytes, insert_bytes
from .fe8data import HEADER_SIZE

ENCODING = "cp932"
INFO_SYMBOL = "CONV_INFO_DATA"
FE8_YELL_SYMBOL = "CONVERSATION_FE8_YELL_DATA"
MINI_YELL_SYMBOL = "CONVERSATION_MINI_YELL_DATA"
INFO_SIZE = 0x30
FE8_YELL_SIZE = 0x2C
PID_SLOTS = 7

#: field key -> (offset, kind) of an info record and of a Path of Radiance support record.
INFO_FIELDS = {"chapter": (0x00, "label"), "title": (0x04, "label"), "message": (0x08, "label"),
               "flag": (0x0C, "label"), **{f"pid_{i + 1}": (0x10 + 4 * i, "label") for i in range(PID_SLOTS)},
               "number": (0x2C, "u32")}
FE8_YELL_FIELDS = {"mpid_a": (0x00, "label"), "mpid_b": (0x04, "label"),
                   "message_1": (0x08, "label"), "message_2": (0x10, "label"), "message_3": (0x18, "label"),
                   "flag_1": (0x20, "label"), "flag_2": (0x24, "label"), "flag_3": (0x28, "label")}
INFO_LABELS = {"chapter": "Chapter", "title": "Title key", "message": "Message ID", "flag": "Seen flag",
               **{f"pid_{i + 1}": f"Character {i + 1}" for i in range(PID_SLOTS)},
               "number": "Number (1-3, not identified)"}
FE8_YELL_LABELS = {"mpid_a": "Character 1 (name key)", "mpid_b": "Character 2 (name key)",
                   "message_1": "Conversation 1", "message_2": "Conversation 2", "message_3": "Conversation 3",
                   "flag_1": "Flag 1", "flag_2": "Flag 2", "flag_3": "Flag 3"}


@dataclass
class InfoConversation:
    index: int
    offset: int                     # absolute offset of the record
    symbol: Optional[str]
    values: dict = field(default_factory=dict)

    @property
    def name(self) -> str:
        """The event name the chapter script uses (the symbol after ``CONV_INFO_DATA_<chapter>_``)."""
        prefix = f"{INFO_SYMBOL}_{self.values.get('chapter') or ''}_"
        return self.symbol[len(prefix):] if self.symbol and self.symbol.startswith(prefix) else ""

    @property
    def pids(self) -> list[str]:
        return [self.values[f"pid_{i + 1}"] for i in range(PID_SLOTS) if self.values[f"pid_{i + 1}"]]


@dataclass
class Fe8Yell:
    index: int
    offset: int
    values: dict = field(default_factory=dict)


@dataclass
class MiniYellCharacter:
    index: int
    offset: int
    pid: Optional[str]
    file: Optional[str]
    partners: list[tuple[Optional[str], Optional[str], Optional[str]]]   # (partner PID, said, answered)


@dataclass
class ConversationData:
    info: list[InfoConversation]
    fe8_yells: list[Fe8Yell]
    mini_yells: list[MiniYellCharacter]


def _u32(data: bytes, offset: int) -> int:
    return struct.unpack_from(">I", data, offset)[0]


def _label(data: bytes, offset: int, listed: set[int]) -> Optional[str]:
    if offset not in listed:
        return None
    pointer = _u32(data, offset)
    end = data.index(b"\0", HEADER_SIZE + pointer)
    return data[HEADER_SIZE + pointer:end].decode(ENCODING, errors="replace")


def symbols(data: bytes) -> list[tuple[str, int]]:
    """(name, data-relative offset) of every symbol, names decoded as Shift-JIS."""
    _size, data_size, pointer_count, count = struct.unpack_from(">IIII", data)
    table = HEADER_SIZE + data_size + 4 * pointer_count
    names = table + 8 * count
    out = []
    for i in range(count):
        offset, name_offset = struct.unpack_from(">II", data, table + 8 * i)
        end = data.index(b"\0", names + name_offset)
        out.append((data[names + name_offset:end].decode(ENCODING, errors="replace"), offset))
    return out


def write_symbols(data: bytes, entries: list[tuple[str, int]]) -> bytes:
    """Rewrite the symbol table (the last part of the file) sorted by name bytes, like the retail files."""
    _size, data_size, pointer_count, _count = struct.unpack_from(">IIII", data)
    table = HEADER_SIZE + data_size + 4 * pointer_count
    encoded = sorted((name.encode(ENCODING), offset) for name, offset in entries)
    rows, names = bytearray(), bytearray()
    for name, offset in encoded:
        rows += struct.pack(">II", offset, len(names))
        names += name + b"\0"
    out = bytearray(data[:table]) + rows + names
    struct.pack_into(">I", out, 0, len(out))
    struct.pack_into(">I", out, 12, len(encoded))
    return bytes(out)


def _start(data: bytes, name: str) -> int:
    for symbol, offset in symbols(data):
        if symbol == name:
            return HEADER_SIZE + offset
    raise ValueError(f"FE10Conversation.cms has no {name} symbol.")


def read_conversation_data(data: bytes) -> ConversationData:
    listed = fe8data.listed_pointer_fields(data)
    by_offset = {}
    for name, offset in symbols(data):
        if name.startswith(INFO_SYMBOL + "_"):
            by_offset[HEADER_SIZE + offset] = name

    start = _start(data, INFO_SYMBOL)
    info = []
    for i in range(_u32(data, start)):
        at = start + 4 + i * INFO_SIZE
        values = {key: (_label(data, at + off, listed) if kind == "label" else _u32(data, at + off))
                  for key, (off, kind) in INFO_FIELDS.items()}
        info.append(InfoConversation(i, at, by_offset.get(at), values))

    start = _start(data, FE8_YELL_SYMBOL)
    yells = []
    for i in range(_u32(data, start)):
        at = start + 4 + i * FE8_YELL_SIZE
        yells.append(Fe8Yell(i, at, {key: _label(data, at + off, listed) for key, (off, _k) in FE8_YELL_FIELDS.items()}))

    start = _start(data, MINI_YELL_SYMBOL)
    minis = []
    at = start + 4
    for i in range(_u32(data, start)):
        count = _u32(data, at + 4)
        partners = [tuple(_label(data, at + 12 + 12 * j + 4 * k, listed) for k in range(3)) for j in range(count)]
        minis.append(MiniYellCharacter(i, at, _label(data, at, listed), _label(data, at + 8, listed), partners))
        at += 12 + 12 * count
    return ConversationData(info, yells, minis)


# -- editing ---------------------------------------------------------------------------------------
def _patch_label(data: bytes, offset: int, value: Optional[str]) -> bytes:
    if value:
        data, pointer = fe8data._label_pointer(data, value, append=True)
    else:
        pointer = 0
    out = bytearray(data)
    fe8data._pack_pointer(out, offset, pointer)
    return bytes(out)


def patch_info(data: bytes, index: int, key: str, value) -> bytes:
    """Change one field of info record ``index``. Changing the chapter keeps the record's symbol in
    step (``CONV_INFO_DATA_<chapter>_<name>``)."""
    record = read_conversation_data(data).info[index]
    offset, kind = INFO_FIELDS[key]
    if kind == "u32":
        value = int(value)
        if not 0 <= value <= 0xFFFFFFFF:
            raise ValueError("The number is out of range.")
        out = bytearray(data)
        struct.pack_into(">I", out, record.offset + offset, value)
        return bytes(out)
    if key == "chapter" and not value:
        raise ValueError("An info conversation needs a chapter.")
    data = _patch_label(data, record.offset + offset, value or None)
    if key == "chapter" and record.symbol:
        data = rename_info(data, index, record.name, chapter=value)
    return data


def patch_fe8_yell(data: bytes, index: int, key: str, value: Optional[str]) -> bytes:
    record = read_conversation_data(data).fe8_yells[index]
    return _patch_label(data, record.offset + FE8_YELL_FIELDS[key][0], value or None)


def patch_mini_yell(data: bytes, index: int, partner: int, column: int, value: Optional[str]) -> bytes:
    """Change a character's support chat line: ``column`` 0 partner PID, 1 line said, 2 line answered."""
    character = read_conversation_data(data).mini_yells[index]
    if not 0 <= column <= 2 or not 0 <= partner < len(character.partners):
        raise IndexError("No such support chat entry.")
    return _patch_label(data, character.offset + 12 + 12 * partner + 4 * column, value or None)


def patch_mini_yell_file(data: bytes, index: int, value: str) -> bytes:
    character = read_conversation_data(data).mini_yells[index]
    return _patch_label(data, character.offset + 8, value)


def _check_name(name: str) -> None:
    if not name or any(c in name for c in " \t\r\n\0"):
        raise ValueError("A base conversation name cannot be empty or contain spaces.")
    try:
        name.encode(ENCODING)
    except UnicodeEncodeError:
        raise ValueError("A base conversation name must be Shift-JIS text.") from None


def rename_info(data: bytes, index: int, name: str, chapter: Optional[str] = None) -> bytes:
    """Give info record ``index`` the symbol ``CONV_INFO_DATA_<chapter>_<name>`` (the event name its
    chapter script registers)."""
    _check_name(name)
    record = read_conversation_data(data).info[index]
    chapter = chapter or record.values["chapter"] or ""
    symbol = f"{INFO_SYMBOL}_{chapter}_{name}"
    entries = [(n, o) for n, o in symbols(data) if HEADER_SIZE + o != record.offset or not n.startswith(INFO_SYMBOL + "_")]
    if any(n == symbol for n, _o in entries):
        raise ValueError(f"{symbol} already exists.")
    entries.append((symbol, record.offset - HEADER_SIZE))
    return write_symbols(data, entries)


def add_info(data: bytes, copy_of: int, name: str) -> tuple[bytes, int]:
    """Append a copy of info record ``copy_of`` (same chapter, title, message, flag and characters)
    with its own symbol for event ``name``; returns the file and the new index."""
    _check_name(name)
    conversations = read_conversation_data(data)
    source = conversations.info[copy_of]
    chapter = source.values["chapter"] or ""
    symbol = f"{INFO_SYMBOL}_{chapter}_{name}"
    if any(n == symbol for n, _o in symbols(data)):
        raise ValueError(f"{symbol} already exists.")
    listed = fe8data.listed_pointer_fields(data)
    block = bytes(data[source.offset:source.offset + INFO_SIZE])
    fields = [off for off in range(0, INFO_SIZE, 4) if source.offset + off in listed]
    at = conversations.info[-1].offset + INFO_SIZE
    data = insert_bytes(data, at, block, fields)
    out = bytearray(data)
    count_at = _start(data, INFO_SYMBOL)
    struct.pack_into(">I", out, count_at, _u32(out, count_at) + 1)
    data = write_symbols(bytes(out), symbols(bytes(out)) + [(symbol, at - HEADER_SIZE)])
    return data, len(conversations.info)


def remove_info(data: bytes, index: int) -> bytes:
    """Remove info record ``index`` and its symbol (the records after it move up one)."""
    conversations = read_conversation_data(data)
    if len(conversations.info) <= 1:
        raise ValueError("The last info conversation cannot be removed.")
    record = conversations.info[index]
    data = write_symbols(data, [(n, o) for n, o in symbols(data)
                                if not (HEADER_SIZE + o == record.offset and n.startswith(INFO_SYMBOL + "_"))])
    out = bytearray(data)
    for off in range(0, INFO_SIZE, 4):
        if record.offset + off in fe8data.listed_pointer_fields(bytes(out)):
            fe8data._pack_pointer(out, record.offset + off, 0)
    data = delete_bytes(bytes(out), record.offset, INFO_SIZE)
    out = bytearray(data)
    count_at = _start(data, INFO_SYMBOL)
    struct.pack_into(">I", out, count_at, _u32(out, count_at) - 1)
    return bytes(out)
