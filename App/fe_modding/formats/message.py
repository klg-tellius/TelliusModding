"""Parse a chapter's dialogue file (``Mess/cNN.m`` - one per chapter,
matching ``Scripts/CNN.cmb``). Unlike most other formats here, these are
stored uncompressed, not inside a ``.cmp``.

Layout: 32-byte header, then the message-text blob, then a table of
(string_offset, name_offset) pointer pairs (one per message, both 0-based
from where their respective blob starts), then the speaker-name blob.

Decoded with cp437: not because the text is really cp437 (it isn't, see
below), but because cp437 happens to be a full round-trip for every byte
value 0-255 (unlike, say, ASCII or UTF-8, which reject or misinterpret
plenty of raw bytes) - reading with cp437 and writing back with cp437 is
guaranteed to reproduce the exact original bytes, whatever they were, even
before this module understood what any given byte meant. That's what makes
``write_messages(read_messages(x))`` a safe, lossless round trip regardless
of how much of the *content* is actually decoded.

**Control code language** (decoded in a follow-up pass; previously this
docstring called it entirely unreverse-engineered). Plain dialogue text
turns out to be interleaved with an inline scripting mini-language, every
command written as printable ASCII starting with ``$`` - so most of it was
already readable through the cp437 approximation without any extra work;
the earlier "renders as arbitrary symbols" concern turned out to apply to
only two specific commands (``$R``/``$B``, below), not the language as a
whole. ``tokenize_control_codes()`` splits a message's text into plain-text
runs and recognized commands - display-only, not used by
read_messages()/write_messages(), so an incomplete or wrong decode here
can never corrupt a write. Commands confirmed or strongly evidenced by
real dialogue (see CODEBOOK for the complete list, including several
recognized-but-undecoded ones kept out of the "confirmed" set):

- ``$R<tag>|`` - the dialogue box's *layout mode* for this message.
  Confirmed by decoding the tag bytes as Shift-JIS, which for every real
  tag found gives back a real Japanese phrase describing a presentation
  style: 上下会話 ("up-down conversation" - the standard two-portrait
  layout, by far the most common), 背景会話 ("background conversation"),
  GMAP会話 ("GMAP conversation" - narration on the world-map screen,
  matching the ``gmap/`` folder), 背景なし会話 ("no-background
  conversation"), のみ会話 ("conversation only"). A handful of special
  shop-greeting messages reuse the exact same ``$R<tag>|`` slot for a
  plain ASCII identifier instead (``BASES_WSHOP_MESS``, ``_ISHOP_``,
  ``_FSHOP_``, and a previously-unseen ``_SSHOP_`` - a fourth shop
  category shop.py's own file-level investigation never found a
  matching inventory file for) - Shift-JIS decodes pure ASCII bytes
  unchanged, so the same decode step handles both cases correctly with no
  special-casing needed.
- ``$B<tag>|`` - the scene's *background image*, same Shift-JIS
  confirmation: real tags decode to real location/time descriptions
  (村-崖 "village-cliff", 平原-昼 "plains-day", 街外れ "town outskirts",
  森の前 "in front of the forest") - i.e. this is the field that actually
  connects a dialogue scene to one of the background images `s/` holds.
- ``$FCL_<name>|`` / ``$FC<name>|`` - load a specific character's portrait
  by internal name (plain ASCII, no Shift-JIS involved) into whichever
  portrait slot is currently selected.
- ``$F<0-8>`` - select portrait slot N (up to 9 portrait "seats" on
  screen at once); ``$FD`` removes the selected portrait; ``$FS``/``$FA``
  pick its first/second mouth set; ``$Fc``/``$Fh``/``$Fo``/``$Fd`` close,
  half-open, hold open or restore its eyes.
- ``$c<0-3><name>|`` - set dialogue box N's displayed speaker name;
  ``$s<0-3>`` - select box N; ``$d<0-3>`` - dismiss box N.
- ``$MC ... $MD`` - stop and restart the speaker's mouth motion; vanilla
  wraps ``--`` and ``...`` in it so the mouth stays still on them.
- ``$K`` - end of the current text box / wait for player input to
  continue - the single most common code in the game by a wide margin.
- ``$w<1-6>`` - pause 2^n frames.
- ``$P`` - clear the current box and start a new page of text.
- ``$SD``/``$SE`` - skip disable/enable: while ``$SD`` is in force, B no
  longer skips the conversation and advances text like A instead (used
  around choices). ``$DC`` sets the same flag but is unused.
- ``$<``/``$>`` - fade the screen in/out over the ``$=`` duration; the text
  keeps running during the fade.
- ``$=<4 digits>`` - that transition duration in milliseconds (9999 means
  the default 267).
- ``$O<0-9>`` - text-typing sound ``SFX_SYS_MSG<n>`` (0 silent): 1 dialogue,
  2 ancient language, 3 world-map narration, 4 tutorial. Draws nothing.
- ``$H`` yields to the event script (the message resumes later); ``$N``
  starts a new line (``$ND`` toggles the nametag); ``$UB``/``$Ub`` release
  the event script waiting on the message, normally right before ``$H``;
  ``$Y`` ends the current text tick without waiting for input; ``$G``
  logs the following text as narration (no speaker name in the text log).
  See research/CONVERSATION_RENDERING.md.
  A separate ``#F<2 digits>`` tag selects the game font for the rest of the
  line (``#F01`` = the Tellius alphabet); see research/FONT_NOTES.md.
"""

from __future__ import annotations

import re
import struct
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO, Optional

from .common import HEADER_SIZE, read_cstring

ENCODING = "cp437"

# (pattern matched right after "$", capture group = the code's argument or
# an empty match if it takes none, confirmed/evidenced name, argument
# encoding or None if the code takes no argument) - see the module
# docstring's "Control code language" section for the evidence behind each.
# Order matters: prefix-overlapping patterns (FCL_ vs FC) are listed longest
# first so the longer one always wins.
CODEBOOK: list[tuple[bytes, str, Optional[str]]] = [
    (rb"R([^|]*)\|", "layout_mode", "shift_jis"),
    (rb"B([^|]*)\|", "background", "shift_jis"),
    (rb"FCL_([^|]*)\|", "portrait_by_name", "cp437"),
    (rb"FC([^|]*)\|", "portrait_by_name", "cp437"),
    (rb"c[0-9]([^|]*)\|", "set_speaker_name", "cp437"),
    (rb"F([0-9])", "select_portrait_slot", "cp437"),
    (rb"F([cdho])", "portrait_expression", "cp437"),
    (rb"FA", "mouth_set_second", None),
    (rb"FS", "mouth_set_first", None),
    (rb"FD", "hide_portrait", None),
    (rb"MC", "mouth_still", None),
    (rb"MD", "mouth_moving", None),
    (rb"w([0-9])", "pause", "cp437"),
    (rb"s([0-9])", "select_box", "cp437"),
    (rb"d([0-9])", "dismiss_box", "cp437"),
    (rb"O([0-9])", "typing_sound", "cp437"),
    (rb"=([0-9]{4})", "transition_duration", "cp437"),
    (rb"K", "wait_for_input", None),
    (rb"P", "clear_box", None),
    (rb"H", "yield_to_script", None),
    (rb"ND", "toggle_nametag", None),
    (rb"N", "new_line", None),
    (rb"UB", "release_script", None),
    (rb"Ub", "release_script", None),
    (rb"SD", "disable_skip", None),
    (rb"DC", "disable_skip", None),
    (rb"SE", "enable_skip", None),
    (rb"G", "narration_log", None),
    (rb"Y", "end_text_tick", None),
    (rb"<", "screen_fade_in", None),
    (rb">", "screen_fade_out", None),
]
_COMPILED_CODEBOOK = [(re.compile(rb"\$" + pattern), name, encoding) for pattern, name, encoding in CODEBOOK]


@dataclass(frozen=True)
class Message:
    speaker: str
    text: str


@dataclass(frozen=True)
class ControlCode:
    """One recognized inline control code from a message's text (see the
    module docstring's "Control code language" section). `name` is a
    short, confirmed/strongly-evidenced label for what the code does -
    "unknown" for a code that's recognized (so tokenize_control_codes()
    doesn't swallow it into plain text) but whose actual effect isn't
    decoded. `arg` is the code's parameter already decoded to a readable
    string where one exists (a background name, a character name, ...) -
    None for codes with no parameter."""

    raw: str
    name: str
    arg: Optional[str] = None


def tokenize_control_codes(text: str) -> list:
    """Split one message's text into a list of plain strings and
    ControlCode objects - a best-effort, DISPLAY-ONLY decode of the
    control-code language. Does not affect read_messages()/
    write_messages(), which keep treating a message's text as one opaque
    cp437 string - the byte-for-byte round-trip guarantee doesn't depend
    on this tokenizer recognizing every code correctly, and an unrecognized
    "$" is passed through as a literal character rather than raising.

    `text` is the cp437-decoded string read_messages() already produced;
    this re-encodes it back to the exact original bytes (cp437 round-trips
    every byte value, so this recovers them losslessly) since $R/$B's
    parameters are Shift-JIS, not cp437, and can only be decoded correctly
    from the raw bytes.
    """
    raw = text.encode(ENCODING)
    tokens: list = []
    plain = bytearray()
    i = 0
    while i < len(raw):
        if raw[i : i + 1] != b"$":
            plain.append(raw[i])
            i += 1
            continue

        for pattern, name, encoding in _COMPILED_CODEBOOK:
            m = pattern.match(raw, i)
            if m:
                if plain:
                    tokens.append(bytes(plain).decode(ENCODING))
                    plain = bytearray()
                arg = m.group(1).decode(encoding, errors="replace") if encoding else None
                tokens.append(ControlCode(raw=raw[i : m.end()].decode(ENCODING), name=name, arg=arg))
                i = m.end()
                break
        else:
            plain.append(raw[i])
            i += 1

    if plain:
        tokens.append(bytes(plain).decode(ENCODING))
    return tokens


def read_messages(stream: BinaryIO) -> list[Message]:
    header = stream.read(32)
    _filesize, pointer_table_start, _unused, num_messages = struct.unpack(">IIII", header[:16])

    name_pointer_base = pointer_table_start + (8 * num_messages) + HEADER_SIZE
    pointer_table_start += HEADER_SIZE

    messages = []
    for i in range(num_messages):
        stream.seek(pointer_table_start + i * 8)
        string_offset, name_offset = struct.unpack(">II", stream.read(8))

        stream.seek(HEADER_SIZE + string_offset)
        text = read_cstring(stream).decode(ENCODING)

        stream.seek(name_pointer_base + name_offset)
        speaker = read_cstring(stream).decode(ENCODING)

        messages.append(Message(speaker=speaker, text=text))

    return messages


def read_messages_path(path: Path | str) -> list[Message]:
    with open(path, "rb") as stream:
        return read_messages(stream)


def read_text_order(stream: BinaryIO) -> list[str]:
    """Message IDs in the order their texts sit in the text blob.

    The pointer table is sorted by ID, but the texts are stored in another
    order (the order the messages were written in). Passing this list back to
    ``write_messages`` rebuilds a vanilla file byte for byte: checked on all
    824 Mess files of the Path of Radiance US and Radiant Dawn US/EU/JP discs."""
    stream.seek(0)
    header = stream.read(32)
    _filesize, pointer_table_start, _unused, num_messages = struct.unpack(">IIII", header[:16])
    name_pointer_base = pointer_table_start + (8 * num_messages) + HEADER_SIZE
    entries = []
    for i in range(num_messages):
        stream.seek(HEADER_SIZE + pointer_table_start + i * 8)
        string_offset, name_offset = struct.unpack(">II", stream.read(8))
        stream.seek(name_pointer_base + name_offset)
        entries.append((string_offset, i, read_cstring(stream).decode(ENCODING)))
    return [name for _offset, _index, name in sorted(entries)]


def read_text_order_path(path: Path | str) -> list[str]:
    with open(path, "rb") as stream:
        return read_text_order(stream)


def write_messages(messages: list[Message], text_order: Optional[list[str]] = None) -> bytes:
    """Serialize messages back to the same layout read_messages() expects.

    ``text_order`` (from ``read_text_order``) lays the texts out in that ID
    order; IDs it does not list follow in table order. With the order of the
    file that was read and the messages unchanged, the output is the original
    file byte for byte. Without it the texts follow the table order, which
    the game accepts just as well (it finds texts through the pointer table).

    Every text starts on a 4-byte boundary, padded with NULs as in every
    vanilla file: the engine's loader (``load_relocatable_resource``, US
    8003f87c) masks the pointer-table offset (header +4) and each text
    offset with ``& ~3``. An unaligned table is read 1-3 bytes early, so
    every ID pointer it registers is garbage (invalid reads in
    ``register_scene_info_by_name`` and a corrupted global name table).
    """
    order = list(range(len(messages)))
    if text_order:
        rank = {}
        for position, name in enumerate(text_order):
            rank.setdefault(name, position)
        order.sort(key=lambda i: (rank.get(messages[i].speaker, len(rank)), i))
    text_blob = bytearray()
    text_offsets = [0] * len(messages)
    for i in order:
        text_offsets[i] = len(text_blob)
        text_blob += messages[i].text.encode(ENCODING) + b"\x00"
        text_blob += bytes(-len(text_blob) % 4)

    name_blob = bytearray()
    name_offsets = []
    name_offset_by_speaker: dict[str, int] = {}
    for message in messages:
        if message.speaker not in name_offset_by_speaker:
            name_offset_by_speaker[message.speaker] = len(name_blob)
            name_blob += message.speaker.encode(ENCODING) + b"\x00"
        name_offsets.append(name_offset_by_speaker[message.speaker])

    pointer_table_start_raw = len(text_blob)  # 0-based from end of header, per the header field's convention

    out = bytearray()
    out += struct.pack(">IIII", 0, pointer_table_start_raw, 0, len(messages))
    out += bytes(16)  # rest of the 32-byte header: read but never used by read_messages()
    out += text_blob
    for string_offset, name_offset in zip(text_offsets, name_offsets):
        out += struct.pack(">II", string_offset, name_offset)
    out += name_blob

    struct.pack_into(">I", out, 0, len(out))  # filesize field, unused by read_messages() but written for completeness
    return bytes(out)


def engine_name_hash(name: str) -> tuple[int, int]:
    """FE9 lookup key of a message ID: ``(bucket, check)``.

    A ``.m`` file is a relocatable resource whose export table is its
    (text, ID) pointer table: ``load_relocatable_resource`` (US 8003f87c)
    registers every ID in the engine's global name hash through
    ``register_scene_info_by_name`` (8000d3ec), and message text is fetched
    with ``hash_lookup_by_name_a`` (8000d354) from ``resolve_ui_string_template``.
    Bucket = ×37 rolling hash mod 509, check = ×31 rolling hash, over
    sign-extended bytes (``extsb``). The lookup compares only ``check`` inside
    the bucket, never the string, so two different IDs with the same key
    shadow each other; the earlier-registered one wins. File order does not
    matter."""
    bucket = check = 0
    for byte in name.encode(ENCODING):
        value = byte - 256 if byte > 127 else byte
        bucket = (bucket * 37 + value) & 0xFFFFFFFF
        check = (check * 31 + value) & 0xFFFFFFFF
    return bucket % 509, check


def write_messages_path(path: Path | str, messages: list[Message], text_order: Optional[list[str]] = None) -> None:
    Path(path).write_bytes(write_messages(messages, text_order))
