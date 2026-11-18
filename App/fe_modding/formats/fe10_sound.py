"""Radiant Dawn's LZ10-wrapped ``Sound/sound_data*.cms`` cue registry.

The decompressed file is a normal Tellius relocatable container.  Its 36-byte
records are exported individually under their cue names (``BGM_*``,
``SFX_*``, ``VOICE_*`` and related prefixes).  The first two fields point to
the exported cue name and to the NW4R sound name registered by the BRSAR.

The other fields were traced to their RFEE01 readers and are listed in
``CUE_FIELDS`` (the sound object keeps the cue at +0xC; update 0x80258c70).
``read_sound_data`` still keeps the seven words verbatim, so repointing to an
already registered resource is a fixed-width operation: the relocation table
and every unrelated byte remain untouched.

The ``SND_*`` exports are u32-counted tables (``SND_TABLES``); their readers
are cited next to each layout.  Pad bytes are left out of the layouts.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass

from .common import HEADER_SIZE
from . import fe8data
from .fe8data import _symbol_entries

RECORD_SIZE = 0x24
CUE_PREFIXES = ("BGM_", "SFX_", "VOICE_", "SE_", "FF_")

_D = 1  # coverage.DECODED (kept local: this module has no coverage import)

# (offset, size, status, name) for the 36-byte cue record; +0x10 and +0x1F
# are pads (zero on every retail disc).
CUE_FIELDS = (
    (0x00, 4, _D, "name"),
    (0x04, 4, _D, "BRSAR sound name"),           # 0x80251c20
    (0x08, 1, _D, "kind (0/1 stream, 2 SFX)"),    # switch 0x8025198c
    (0x09, 1, _D, "volume /127"),                 # 0x80258f80
    (0x0A, 2, _D, "pitch"),                       # pow2 0x80295aa4 -> 0x802a3000
    (0x0C, 1, _D, "pitch divisor"),
    (0x0D, 1, _D, "pan"),                         # 0x802a3008
    (0x0E, 1, _D, "surround pan"),                # 0x802a3010
    (0x0F, 1, _D, "low-pass filter"),             # 0x802a3018
    (0x11, 1, _D, "main send"),                   # 0x802a3020
    (0x12, 1, _D, "effect send"),                 # 0x802a305c
    (0x13, 1, _D, "priority"),                    # 0x8025a880
    (0x14, 1, _D, "no distance attenuation"),
    (0x15, 1, _D, "max simultaneous plays"),      # 0x80252cbc
    (0x16, 2, _D, "random pitch min"),            # 0x80251a68
    (0x18, 2, _D, "random pitch max"),
    (0x1A, 1, _D, "random volume min"),
    (0x1B, 1, _D, "random volume max"),
    (0x1C, 2, _D, "start delay (frames)"),        # 0x80258e74
    (0x1E, 1, _D, "distance low-pass"),           # 0x8025949c..0x80259644
    (0x20, 1, _D, "distance main send"),
    (0x21, 1, _D, "distance effect send"),
    (0x22, 2, _D, "Sound Room index"),            # 0x8024f3c8, 0x800cd7f4
)

# name -> (row size, row layout).  Each export starts with a u32 row count.
SND_TABLES = {
    # 0x8013a8d8: ambient / positioned environment emitters per map.
    "SND_ENV_DATA": (0x18, (
        (0x00, 4, _D, "map"), (0x04, 4, _D, "cue"), (0x08, 1, _D, "emitter kind"),
        (0x09, 1, _D, "emitter state"), (0x0C, 12, _D, "position"))),
    # 0x8013ac48 -> 0x8013ae18: per-map mixer settings.
    "SND_MAP_DATA": (0x14, (
        (0x00, 4, _D, "map"), (0x04, 1, _D, "mixer A /127"), (0x05, 1, _D, "mixer B /127"),
        (0x08, 12, _D, "mixer floats"))),
    # 0x800f14b4: .ga event codes >= 1000 -> SFX cue (binary search).
    "SND_SFX_MAYA_DATA": (8, ((0x00, 4, _D, "event code"), (0x04, 4, _D, "cue"))),
    # 0x80068398..0x800685b0, row match 0x800682c4.
    "SND_MAP_BGM_DATA": (0x34, (
        (0x00, 4, _D, "chapter"), (0x04, 1, _D, "condition kind"),
        (0x08, 16, _D, "map music variants"), (0x18, 16, _D, "phase music"),
        (0x28, 4, _D, "preparations"), (0x2C, 4, _D, "base"), (0x30, 4, _D, "select"))),
    # 0x800689d4, row test 0x80068638: boss / pairing battle themes.
    "SND_BATTLE_BGM_DATA": (0x1C, (
        (0x00, 4, _D, "cue"), (0x04, 4, _D, "chapter"), (0x08, 8, _D, "PIDs"),
        (0x10, 4, _D, "event flag"), (0x14, 2, _D, "classes"), (0x16, 2, _D, "armies"),
        (0x18, 1, _D, "flag state"), (0x19, 1, _D, "either order"))),
    # 0x800680d0: BRSAR group to load per chapter / flag.
    "SND_CHAPTER_GROUP_DATA": (0x10, (
        (0x00, 4, _D, "chapter"), (0x04, 4, _D, "flag"), (0x08, 1, _D, "flag state"),
        (0x0C, 4, _D, "group"))),
}
SND_COUNTS = ("SND_BGM_DATA", "SND_SFX_DATA", "SND_VOICE_DATA")


def looks_like_cue(data: bytes, offset: int) -> bool:
    """An absolute ``offset`` whose first word is a pointer to a cue name."""
    if offset + RECORD_SIZE > len(data):
        return False
    pointer = struct.unpack_from(">I", data, offset)[0]
    at = HEADER_SIZE + pointer
    return 0 < pointer and at < len(data) and data[at:at + 8].startswith(
        tuple(prefix.encode() for prefix in CUE_PREFIXES))


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
