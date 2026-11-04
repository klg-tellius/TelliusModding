"""Radiant Dawn's LZ10-wrapped ``Sound/sound_data*.cms`` cue registry.

The decompressed file is a normal Tellius relocatable container.  Its 36-byte
records are exported individually under their cue names (``BGM_*``,
``SFX_*``, ``VOICE_*`` and related prefixes).  The first two fields point to
the exported cue name and to the NW4R sound name registered by the BRSAR.

Only those two relationships are named here.  The remaining seven words are
kept verbatim until their runtime consumers have been confirmed.  Repointing
to an already registered resource is consequently a fixed-width operation:
the relocation table and every unrelated byte remain untouched.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass

from .common import HEADER_SIZE
from . import fe8data
from .fe8data import _symbol_entries

RECORD_SIZE = 0x24
CUE_PREFIXES = ("BGM_", "SFX_", "VOICE_", "SE_", "FF_")


class Fe10SoundError(ValueError):
    pass


@dataclass(frozen=True)
class Fe10SoundCue:
    name: str
    resource: str
    record_offset: int  # data-relative
    name_pointer: int
    resource_pointer: int
    raw_words: tuple[int, ...]

    @property
    def family(self) -> str:
        return self.name.split("_", 1)[0]


def _container_shape(data: bytes) -> tuple[int, int, int, int]:
    if len(data) < HEADER_SIZE:
        raise Fe10SoundError("Sound data container is truncated")
    file_size, data_size, pointer_count, symbol_count = struct.unpack_from(">4I", data)
    if file_size != len(data) or HEADER_SIZE + data_size + pointer_count * 4 + symbol_count * 8 > len(data):
        raise Fe10SoundError("Sound data container header does not match the file")
    return file_size, data_size, pointer_count, symbol_count


def _cstring(body: bytes, pointer: int) -> str:
    if not 0 <= pointer < len(body):
        raise Fe10SoundError(f"String pointer {pointer:#x} is outside sound_data")
    end = body.find(b"\0", pointer)
    if end < 0:
        raise Fe10SoundError(f"String at {pointer:#x} is not terminated")
    # One retail JP-base cue contains a malformed Shift-JIS byte before its
    # final digit.  The container export carries the same bytes; replacement
    # decoding preserves the record instead of rejecting the whole catalog.
    return body[pointer:end].decode("shift_jis", errors="replace")


def read_sound_data(data: bytes) -> list[Fe10SoundCue]:
    _file_size, data_size, _pointer_count, _symbol_count = _container_shape(data)
    body = data[HEADER_SIZE:HEADER_SIZE + data_size]
    result = []
    seen = set()
    for _symbol_position, record_offset, symbol_name in _symbol_entries(data):
        if not symbol_name.startswith(CUE_PREFIXES):
            continue
        if record_offset + RECORD_SIZE > len(body):
            raise Fe10SoundError(f"{symbol_name}: record runs past the data section")
        words = struct.unpack_from(">9I", body, record_offset)
        name = _cstring(body, words[0])
        resource = _cstring(body, words[1])
        # The same container also exports aggregate SND_* tables.  A cue
        # export is self-identifying: its first pointer names that export.
        # Skip aggregate symbols instead of interpreting their headers as a
        # 36-byte cue row.
        if not name or (name.isascii() and symbol_name.isascii() and name != symbol_name):
            continue
        if name in seen:
            raise Fe10SoundError(f"Duplicate sound cue {name}")
        seen.add(name)
        result.append(Fe10SoundCue(name, resource, record_offset, words[0], words[1], tuple(words[2:])))
    return result


def cue_map(data: bytes) -> dict[str, Fe10SoundCue]:
    return {cue.name: cue for cue in read_sound_data(data)}


def resources(data: bytes) -> tuple[str, ...]:
    """Every distinct BRSAR resource named by the cue registry."""
    return tuple(dict.fromkeys(cue.resource for cue in read_sound_data(data)))


def repoint_cue(data: bytes, cue_name: str, resource: str) -> bytes:
    """Point one cue at another resource string already present in the file.

    Adding strings is intentionally a separate builder concern; this safe
    primitive covers retail-to-retail repointing without moving the large
    collection of non-record structures also held by ``sound_data.cms``.
    """
    cues = read_sound_data(data)
    by_name = {cue.name: cue for cue in cues}
    try:
        cue = by_name[cue_name]
    except KeyError:
        raise Fe10SoundError(f"Unknown sound cue {cue_name}") from None
    target = next((item.resource_pointer for item in cues if item.resource == resource), None)
    if target is None:
        raise Fe10SoundError(f"Resource {resource} is not registered in this sound-data file")
    out = bytearray(data)
    struct.pack_into(">I", out, HEADER_SIZE + cue.record_offset + 4, target)
    rebuilt = bytes(out)
    changed = cue_map(rebuilt)[cue_name]
    if changed.resource != resource:
        raise Fe10SoundError("Repointed cue did not validate")
    return rebuilt



def _raw_symbols(data: bytes) -> list[tuple[int, bytes]]:
    """(data offset, name bytes) of every export; one retail name is not ASCII, so names stay raw."""
    _size, data_size, pointer_count, count = struct.unpack_from(">IIII", data, 0)
    table = HEADER_SIZE + data_size + 4 * pointer_count
    names = table + 8 * count
    result = []
    for index in range(count):
        offset, name_at = struct.unpack_from(">II", data, table + 8 * index)
        start = names + name_at
        result.append((offset, bytes(data[start:data.index(b"\0", start)])))
    return result


def _set_symbols(data: bytes, symbols: list[tuple[int, bytes]]) -> bytes:
    """``data`` with its symbol table rebuilt from (data offset, name bytes), sorted by name like
    retail."""
    _size, data_size, pointer_count, _count = struct.unpack_from(">IIII", data, 0)
    table = HEADER_SIZE + data_size + 4 * pointer_count
    entries, names = bytearray(), bytearray()
    for offset, name in sorted(symbols, key=lambda item: item[1]):
        entries += struct.pack(">II", offset, len(names))
        names += name + b"\0"
    out = bytearray(data[:table]) + entries + names
    struct.pack_into(">I", out, 0, len(out))
    struct.pack_into(">I", out, 12, len(symbols))
    return bytes(out)


def add_cue(data: bytes, name: str, resource: str, template: str) -> bytes:
    """``data`` with a new cue ``name`` playing BRSAR sound ``resource``: a 36-byte record (the
    name, the resource, then ``template``'s seven other words) appended to the data section and
    exported under its name. The game finds a cue through that export (RFEE01 0x80076F54 looks
    the name up in the global name hash every loaded container's symbols go into), so the new
    cue needs no place in the SND_* tables."""
    if not name.isascii() or not name.startswith(CUE_PREFIXES) or not name.replace("_", "").isalnum():
        raise Fe10SoundError("A cue name is BGM_, SFX_ or VOICE_ followed by capitals, digits and _.")
    cues = cue_map(data)
    if name in cues or name.encode("ascii") in {symbol for _o, symbol in _raw_symbols(data)}:
        raise Fe10SoundError(f"{name} already exists")
    if template not in cues:
        raise Fe10SoundError(f"Unknown template cue {template}")
    out, name_at = fe8data._append_label(data, name)
    out, resource_at = fe8data._append_label(out, resource)
    record = struct.pack(">9I", name_at, resource_at, *cues[template].raw_words)
    out, record_at = fe8data.append_block(out, record, pointer_fields=(0, 4))
    rebuilt = _set_symbols(out, _raw_symbols(out) + [(record_at, name.encode("ascii"))])
    added = cue_map(rebuilt).get(name)
    if added is None or added.resource != resource:
        raise Fe10SoundError("The new cue did not validate")
    return rebuilt


def remove_cue(data: bytes, name: str, vanilla: bytes) -> bytes:
    """``data`` without the export of cue ``name``, one the mod added (its record stays behind,
    unused). Cues of the extracted file refuse."""
    if name in cue_map(vanilla):
        raise Fe10SoundError(f"{name} is one of the game's own cues")
    key = name.encode("ascii")
    symbols = _raw_symbols(data)
    if key not in {symbol for _o, symbol in symbols}:
        raise Fe10SoundError(f"No cue {name}")
    return _set_symbols(data, [(offset, symbol) for offset, symbol in symbols if symbol != key])
