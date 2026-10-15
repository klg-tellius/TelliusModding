"""How Path of Radiance's message bytes map to characters, by release.

Message files are kept byte for byte (``message.ENCODING`` is cp437, one character per byte);
this module turns those bytes into the text the game draws, and back.

- US (GFEE01) and JP (GFEJ01): CP932, Shift-JIS plus the NEC ``0x87xx`` row the fonts carry.
- PAL (GFEP01): a hybrid. Bytes ``0x81``-``0x9F`` start a two-byte Shift-JIS character (kana and
  kanji still appear in labels and a few symbols), every other byte is one Latin-1 character:
  the PAL fonts have glyphs ``0xA1``-``0xFF`` for the accented letters (``0xE0`` is "à").

The release is chosen once per opened project (:func:`use_for_extraction`); the default is
CP932, which is also correct for every ASCII-only US text.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

CP932, PAL = "cp932", "pal"
_BY_GAME_ID = {"GFEE01": CP932, "GFEJ01": CP932, "GFEP01": PAL}
_mode = CP932


def mode() -> str:
    return _mode


def use_game_id(game_id: Optional[str]) -> None:
    """Select the text rules of a release (unknown or None: CP932)."""
    global _mode
    _mode = _BY_GAME_ID.get((game_id or "")[:6], CP932)


def use_for_extraction(extracted_dir: Path | str) -> None:
    """Select the rules from ``sys/boot.bin`` of an extraction (``extracted/`` or its ``files/``)."""
    root = Path(extracted_dir)
    for boot in (root / "sys" / "boot.bin", root.parent / "sys" / "boot.bin"):
        try:
            use_game_id(boot.read_bytes()[:6].decode("ascii"))
            return
        except (OSError, UnicodeDecodeError):
            continue


def is_lead_byte(byte: int) -> bool:
    """True when ``byte`` starts a two-byte character."""
    if _mode == PAL:
        return 0x81 <= byte <= 0x9F
    return 0x81 <= byte <= 0x9F or 0xE0 <= byte <= 0xFC


def decode(data: bytes) -> str:
    """Game bytes -> text. Bytes that are no character stay as surrogate escapes."""
    if _mode != PAL:
        return data.decode(CP932, "surrogateescape")
    out = []
    i = 0
    while i < len(data):
        if is_lead_byte(data[i]) and i + 1 < len(data):
            out.append(data[i:i + 2].decode(CP932, "surrogateescape"))
            i += 2
        else:
            out.append(data[i:i + 1].decode("latin-1"))
            i += 1
    return "".join(out)


def encode(text: str) -> bytes:
    """Text -> game bytes; UnicodeEncodeError for a character the release cannot write."""
    if _mode != PAL:
        return text.encode(CP932, "surrogateescape")
    out = bytearray()
    for i, char in enumerate(text):
        code = ord(char)
        if code < 0x80 or 0xA0 <= code <= 0xFF:
            out.append(code)
            continue
        raw = char.encode(CP932, "surrogateescape")
        if len(raw) == 2 and is_lead_byte(raw[0]):
            out += raw
        elif len(raw) == 1 and 0xDC80 <= code <= 0xDCFF:     # an escaped stray byte
            out += raw
        else:
            raise UnicodeEncodeError("pal", text, i, i + 1, "no PAL encoding for this character")
    return bytes(out)


def from_raw(raw: str) -> str:
    """A message string as read by ``message.py`` (cp437 bytes) -> the text it shows."""
    return decode(raw.encode("cp437"))


def to_raw(text: str) -> str:
    """The inverse of :func:`from_raw`."""
    return encode(text).decode("cp437")


def char_code(char: str) -> int:
    """The font code of one character (``font_find_glyph`` key)."""
    raw = encode(char)
    return raw[0] if len(raw) == 1 else int.from_bytes(raw[:2], "big")
