"""Radiant Dawn's staff credits: ``Mess/<lang>ending.m`` and ``StaffRollData.bin``.

RFEE01's staff roll (``StaffRollProc``; setup ``0x80288A98``, lines drawn from ``0x80289214``) reads
its text from the ending message file through the language prefix (``Mess/%s%s.m``: ``e_`` English,
none Japanese, ``d_ f_ s_ i_`` on European discs). The file holds:

- ``MED_STAFFROLL_TITLE``, the roll's title, and ``MED_STAFFROLL_COPY1``..``COPY5``, the copyright
  lines;
- ``MED_STAFFROLL_LINES``: the line count as text (`` 358 ``), read with ``atoi`` (``0x8029191C``);
- per line ``nnn`` (``MED_STAFFROLL_L%03d_L`` / ``_C`` / ``_R``, built with that format in the DOL): a
  role, a centred heading and a name, as Path of Radiance's three columns. An empty message is an
  empty column; a line with all three empty is a blank line.

``StaffRollData.bin`` is a small data container of 16 named words (:data:`TIMINGS`): the scroll speed
(a float), waits and the music's begin, fade and next times (milliseconds in the retail values), four
``SOUND`` numbers (313, 327, 300, 313: below the line count, not traced further) and ``LYRIC``.
"""

from __future__ import annotations

import io
import struct
from dataclasses import dataclass, field

from . import fe8data, message
from .common import HEADER_SIZE

LINE_KEY = "MED_STAFFROLL_L{:03d}_{}"
COLUMNS = ("L", "C", "R")  # role, heading, name
TITLE, LINES = "MED_STAFFROLL_TITLE", "MED_STAFFROLL_LINES"
COPYRIGHT = tuple(f"MED_STAFFROLL_COPY{n}" for n in range(1, 6))
MAX_LINES = 1000  # %03d keys
#: StaffRollData.bin label -> (format, meaning)
TIMINGS = {
    "LBL_STAFFROLL_SCROLLSPEED": (">f", "Scroll speed"),
    "LBL_STAFFROLL_SCROLLWAIT_BEGIN": (">I", "Wait before scrolling"),
    "LBL_STAFFROLL_SCROLLWAIT_END": (">I", "Wait after the last line"),
    "LBL_STAFFROLL_SND_BEGIN1": (">I", "Song 1 starts at"),
    "LBL_STAFFROLL_SNDOUT_BEGIN1": (">I", "Song 1 fades out at"),
    "LBL_STAFFROLL_SNDOUT_TIME1": (">I", "Song 1 fade length"),
    "LBL_STAFFROLL_SNDNEXT1": (">I", "Song 1 next at"),
    "LBL_STAFFROLL_SND_BEGIN2": (">I", "Song 2 starts at"),
    "LBL_STAFFROLL_SNDOUT_BEGIN2": (">I", "Song 2 fades out at"),
    "LBL_STAFFROLL_SNDOUT_TIME2": (">I", "Song 2 fade length"),
    "LBL_STAFFROLL_SNDNEXT2": (">I", "Song 2 next at"),
    "LBL_STAFFROLL_SOUND1A": (">I", "SOUND1A"),
    "LBL_STAFFROLL_SOUND1B": (">I", "SOUND1B"),
    "LBL_STAFFROLL_SOUND2A": (">I", "SOUND2A"),
    "LBL_STAFFROLL_SOUND2B": (">I", "SOUND2B"),
    "LBL_STAFFROLL_LYRIC": (">I", "LYRIC"),
}


class Fe10StaffRollError(ValueError):
    pass


@dataclass
class Fe10StaffRoll:
    title: str
    copyright: list[str]
    lines: list[tuple[str, str, str]] = field(default_factory=list)  # role, heading, name
    others: list[message.Message] = field(default_factory=list)       # any other message, kept
    text_order: list[str] = field(default_factory=list)


def read_rd_staffroll(data: bytes) -> Fe10StaffRoll:
    messages = message.read_messages(io.BytesIO(data))
    texts = {m.speaker: m.text for m in messages}
    if LINES not in texts:
        raise Fe10StaffRollError("No MED_STAFFROLL_LINES: not a staff roll message file.")
    try:
        count = int(texts[LINES].strip())
    except ValueError as exc:
        raise Fe10StaffRollError(f"MED_STAFFROLL_LINES is {texts[LINES]!r}, not a number.") from exc
    lines = [tuple(texts.get(LINE_KEY.format(n, column), "") for column in COLUMNS) for n in range(count)]
    known = {TITLE, LINES, *COPYRIGHT} | {LINE_KEY.format(n, c) for n in range(count) for c in COLUMNS}
    return Fe10StaffRoll(texts.get(TITLE, ""), [texts.get(key, "") for key in COPYRIGHT], lines,
                         [m for m in messages if m.speaker not in known],
                         message.read_text_order(io.BytesIO(data)))


def build_rd_staffroll(roll: Fe10StaffRoll) -> bytes:
    """The message file of ``roll``: the copyright lines, every line's three columns, the count and
    the title, in retail order (other messages kept after them). Unchanged, it is the read file."""
    if len(roll.lines) > MAX_LINES:
        raise Fe10StaffRollError(f"At most {MAX_LINES} lines (the keys are numbered with three digits).")
    if len(roll.copyright) != len(COPYRIGHT):
        raise Fe10StaffRollError("The roll has five copyright lines.")
    messages = [message.Message(key, text) for key, text in zip(COPYRIGHT, roll.copyright)]
    for n, line in enumerate(roll.lines):
        role, heading, name = line
        messages += [message.Message(LINE_KEY.format(n, "C"), heading), message.Message(LINE_KEY.format(n, "L"), role),
                     message.Message(LINE_KEY.format(n, "R"), name)]
    messages += [message.Message(LINES, f" {len(roll.lines)} "), message.Message(TITLE, roll.title)]
    messages += roll.others
    for m in messages:
        try:
            m.text.encode(message.ENCODING)
        except UnicodeEncodeError as exc:
            raise Fe10StaffRollError(f"{m.speaker}: the credits are Shift-JIS text.") from exc
    return message.write_messages(messages, roll.text_order)


def read_timings(data: bytes) -> dict[str, float | int]:
    """StaffRollData.bin: label -> value (the scroll speed a float, the rest whole numbers)."""
    body = data[HEADER_SIZE:]
    offsets = {name: offset for _p, offset, name in fe8data._symbol_entries(data)}
    out = {}
    for label, (fmt, _meaning) in TIMINGS.items():
        if label not in offsets:
            raise Fe10StaffRollError(f"StaffRollData.bin has no {label}.")
        out[label] = struct.unpack_from(fmt, body, offsets[label])[0]
    return out


def set_timing(data: bytes, label: str, value) -> bytes:
    """``data`` with one StaffRollData.bin value changed in place."""
    if label not in TIMINGS:
        raise Fe10StaffRollError(f"Unknown staff roll value {label}.")
    fmt = TIMINGS[label][0]
    offsets = {name: offset for _p, offset, name in fe8data._symbol_entries(data)}
    out = bytearray(data)
    if fmt == ">f":
        struct.pack_into(fmt, out, HEADER_SIZE + offsets[label], float(value))
    else:
        if not isinstance(value, int) or not 0 <= value <= 0xFFFFFFFF:
            raise Fe10StaffRollError(f"{TIMINGS[label][1]} is a whole number from 0.")
        struct.pack_into(fmt, out, HEADER_SIZE + offsets[label], value)
    return bytes(out)
