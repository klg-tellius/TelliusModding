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

