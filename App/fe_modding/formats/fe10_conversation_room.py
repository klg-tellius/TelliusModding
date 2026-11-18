"""Radiant Dawn's ``conversationroom.bin``: the Conversation Room's chapter and character lists.

A :mod:`pool_file` file read by ``conversation_room_init`` (``0x8027CE60``): a u32 count and that
many chapter-ID pointers (``C0105`` ... ``C0407e``), then a u32 count and that many character
pointers (69 PIDs and a closing ``OTHER``). The init keeps both lists in the room state
(+0x14/+0x18 and +0x1C/+0x20) next to ``CONV_INFO_DATA`` from ``FE10Conversation.cms``, whose
records name the chapter and the speakers of each conversation. The lists match the room's
two orderings (by chapter, by character); the menu code that walks them was not traced.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass, field

from .pool_file import PoolFile, TableWriter, build_pool_file, read_pool_file

OTHER = "OTHER"


class ConversationRoomError(ValueError):
    pass


@dataclass
class ListItem:
    value: str


@dataclass
class ConversationRoom:
    chapters: list[ListItem] = field(default_factory=list)
    characters: list[ListItem] = field(default_factory=list)
    trailer: bytes = b""
    header_tail: bytes = bytes(12)
    symbols: list[tuple[str, int]] = field(default_factory=list)


def read_conversation_room(data: bytes) -> ConversationRoom:
    doc = read_pool_file(data)
    out = ConversationRoom(header_tail=doc.header_tail, symbols=list(doc.symbols))
    at = 0
    for items in (out.chapters, out.characters):
        if at + 4 > len(doc.body):
            raise ConversationRoomError("conversationroom.bin ends inside its lists.")
        (count,) = struct.unpack_from(">I", doc.body, at)
        at += 4
        for _ in range(count):
            if at not in doc.pointers:
                raise ConversationRoomError(f"Expected a name pointer at {at:#x}.")
            items.append(ListItem(doc.pointers[at]))
            at += 4
    out.trailer = doc.body[at:]
    return out


def build_conversation_room(room: ConversationRoom) -> bytes:
    w = TableWriter()
    for items in (room.chapters, room.characters):
        w.word(len(items))
        for item in items:
            if not item.value:
                raise ConversationRoomError("A list entry is empty.")
            w.text(item.value)
    w.raw(room.trailer)
    return build_pool_file(PoolFile(bytes(w.body), w.pointers, room.symbols, room.header_tail))
