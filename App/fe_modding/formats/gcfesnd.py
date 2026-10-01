"""``Sound/gcfesnd.bin`` - the game-specific sound cue catalog layered above
the raw MusyX resources (see musyx.py's write-up in the Tellius Archive).
Holds every ``BGM_*``/``SFX_*`` cue name plus, for BGM, the streamed
``.stm`` file each cue plays.

The outer container is a real instance of the "labeled section" format
(see labeled_section-equivalent notes in CONTAINER_FORMATS.md/common.py):
``HEADER_SIZE`` (0x20) bytes of header, then a flat, self-terminating array
of records starting immediately after it. Confirmed byte-for-byte against
a real ``Sound/gcfesnd.bin`` and independently against a live Dolphin
memory dump of the loaded resource (see research/MUSIC_NOTES.md section 7
for the full derivation). The array holds 148 twelve-byte ``BGM_*`` records
(``read_bgm_cues`` returns the file-backed ones) followed by 1,154 twenty-byte
``SFX_*`` records (``read_sfx_cues``, layout below), ended by a zero length byte.

Each BGM record is 12 bytes, self-describing its own length:

- +0x00 (4B): pool-relative offset of the cue's name string (``BGM_...``)
  - add HEADER_SIZE for the real file offset, same convention as every
  other "labeled section" pointer in this codebase.
- +0x04 (1B): record length - always 12 for a BGM record (the SFX records
  that follow use 20 and a different layout). A record with length 0 ends
  the array; this is exactly how the game's own loader (``init_sound_scenes``)
  walks the table at boot.
- +0x05 (1B): type byte - ``0x06`` on every real, file-backed BGM cue in
  the retail game, ``0x0e`` on every cue whose path is the shared
  "sound/fe_dummy_32k" placeholder (no backing file anywhere on the real
  disc). Never seen any other value.
- +0x06 (1B): a per-cue value in 0-127, roughly volume/attenuation-shaped
  but not confirmed further - see research/MUSIC_NOTES.md.
- +0x07 (1B): always 0x40 across every real BGM record sampled - unexplained,
  safe to copy verbatim.
- +0x08 (4B): pool-relative offset of the target resource path string,
  e.g. ``sound/gcfe_bgm_evt_ike1_32k`` (no ``.stm`` extension, lowercase
  ``sound/`` - matches the real, case-sensitive ``Sound/*.stm`` files once
  extension and case are restored).

``repoint_bgm_cue()`` is the only write operation: point one cue's path at
a brand-new string (appended past the file's current end - the loader
reads the whole file as one contiguous block, so this is safe; the
relocation table between the label pool and the section table is confirmed
build-time-only bookkeeping, not read by the game) and give it a known-good
control word, without touching any of the file's other cues. This is
deliberately narrower than a general "add a new record" operation - nobody
has confirmed the loader tolerates a longer record array, so the supported
workflow is repointing one of the retail game's own already-registered but
unused cue names (its target file doesn't exist on disc) rather than
growing the table.

Each SFX record is 20 bytes (all big-endian):

- +0x00 (4B): pool-relative offset of the ``SFX_*`` name string.
- +0x04 (1B): record length, always 20.
- +0x05 (1B): flags. The low 2 bits pick the voice class (``record+5 & 3``
  in ``play_sound_effect_by_name``); seen values 0, 1 and 8.
- +0x06 (1B): default volume (0-127; 0x7D and 0x7F dominate).
- +0x07 (1B): pan (0x40 = centre on 1,131 of 1,154 records).
- +0x08 (4B): sound id - the MusyX-side id the name resolves to (several
  cues share one id, e.g. every ``0x158`` cue is the silent dummy).
- +0x0C (4B): four small bytes, first one usually 0x1E (30): priority /
  range-like values read by the ``get_priority_source``/``get_max_range``
  accessors at +0xC and +0xF.
- +0x10 (4B): a distance-like value (2000, 100, 200, 150, 750 ...).

The meaning of +0x0C and +0x10 is inferred from accessor offsets, not proven.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass
from pathlib import Path

from .common import HEADER_SIZE

BGM_RECORD_SIZE = 12
BGM_TYPE_REAL = 0x06
BGM_TYPE_DUMMY = 0x0E

# A known-good control word copied verbatim from real, working retail cues
# (e.g. BGM_EVT_IKE1) - size=12, type=REAL, volume-ish byte=127 (the single
# most common value among real cues), trailing byte=0x40.
DEFAULT_CONTROL_WORD = (BGM_RECORD_SIZE << 24) | (BGM_TYPE_REAL << 16) | (127 << 8) | 0x40


SFX_RECORD_SIZE = 20


class GcfesndError(Exception):
    pass


@dataclass
class BgmCue:
    offset: int  # absolute file offset of this record's own 12 bytes
    name: str
    name_offset: int  # raw stored value (pool-relative, add HEADER_SIZE for file offset)
    path: str
    path_offset: int
    control_word: int

    @property
    def is_dummy(self) -> bool:
        return ((self.control_word >> 16) & 0xFF) == BGM_TYPE_DUMMY


def _read_cstring_at(data: bytes, file_offset: int, max_len: int = 128) -> str:
    end = data.find(b"\x00", file_offset, file_offset + max_len)
    if end == -1:
        raise GcfesndError(f"Unterminated string at offset {file_offset:#x}.")
    return data[file_offset:end].decode("ascii")


def read_bgm_cues(data: bytes) -> list[BgmCue]:
    """Parse the flat, self-terminating BGM record array starting right
    after the header, stopping at the first record whose own length byte
    isn't 12 (the retail file's SFX records start with length 20 right
    after the last BGM one - this is the same boundary the game's own
    ``init_sound_scenes`` loop stops effectively re-deriving), or - since a
    handful of trailing "BGM_ENV_*" ambient-loop records also use length 12
    but repurpose the third field for something that isn't a label-pool
    string at all (not decoded by this module) - the first record whose
    name/path can't be read as a clean ASCII string."""
    cues = []
    offset = HEADER_SIZE
    while offset + BGM_RECORD_SIZE <= len(data):
        name_raw, control_word, path_raw = struct.unpack_from(">III", data, offset)
        record_len = (control_word >> 24) & 0xFF
        if record_len != BGM_RECORD_SIZE:
            break
        try:
            name = _read_cstring_at(data, name_raw + HEADER_SIZE)
            path = _read_cstring_at(data, path_raw + HEADER_SIZE)
        except (GcfesndError, UnicodeDecodeError):
            break
        if not path.startswith("sound/"):
            # A handful of trailing "BGM_ENV_*" records also happen to
            # decode as valid ASCII here by coincidence (see docstring) -
            # every genuine BGM record's path starts with "sound/", so this
            # is the reliable boundary, not just the length/decode checks.
            break
        cues.append(BgmCue(offset=offset, name=name, name_offset=name_raw, path=path, path_offset=path_raw, control_word=control_word))
        offset += BGM_RECORD_SIZE
    return cues


def read_bgm_cues_path(path: Path | str) -> list[BgmCue]:
    return read_bgm_cues(Path(path).read_bytes())


def find_cue(cues: list[BgmCue], name: str) -> BgmCue:
    for cue in cues:
        if cue.name == name:
            return cue
    raise GcfesndError(f"No BGM cue named {name!r}.")


def repoint_bgm_cue(data: bytes, cue: BgmCue, new_path: str, control_word: int = DEFAULT_CONTROL_WORD) -> bytes:
    """Return a copy of data with `cue`'s target path repointed at
    `new_path` (no extension, matching the format's own convention - e.g.
    "sound/ex_32k" for "Sound/ex_32k.stm"), appending a fresh string rather
    than reusing whatever `cue` pointed at before, so cues that used to
    share one string (e.g. the 24 unused cues all sharing
    "sound/fe_dummy_32k") aren't affected by repointing just one of them.
    Also updates the header's filesize field, which is an exact byte count
    on this file (confirmed - no "+1" convention like other labeled-section
    files use)."""
    if "\x00" in new_path:
        raise GcfesndError("A path can't contain a NUL byte.")

    out = bytearray(data)
    new_string_offset = len(out)
    out += new_path.encode("ascii") + b"\x00"

    new_raw = new_string_offset - HEADER_SIZE
    struct.pack_into(">I", out, cue.offset + 4, control_word)
    struct.pack_into(">I", out, cue.offset + 8, new_raw)
    struct.pack_into(">I", out, 0x00, len(out))
    return bytes(out)


def repoint_bgm_cue_path(path: Path | str, cue_name: str, new_path: str, control_word: int = DEFAULT_CONTROL_WORD) -> None:
    path = Path(path)
    data = path.read_bytes()
    cue = find_cue(read_bgm_cues(data), cue_name)
    path.write_bytes(repoint_bgm_cue(data, cue, new_path, control_word))


@dataclass
class SfxCue:
    offset: int  # absolute file offset of this record's own 20 bytes
    name: str
    name_offset: int  # raw stored value (pool-relative)
    flags: int
    volume: int
    pan: int
    sound_id: int
    extra: bytes  # +0x0C..+0x0F
    range_value: int  # +0x10

    @property
    def voice_class(self) -> int:
        return self.flags & 3

    @property
    def group(self) -> str:
        """Category taken from the name: ``SFX_SYS_SELECT1`` -> ``SYS``."""
        parts = self.name.split("_")
        return parts[1] if len(parts) > 2 and parts[0] == "SFX" else "OTHER"


def read_sfx_cues(data: bytes) -> list[SfxCue]:
    """Walk the whole record array (12-byte BGM records, 20-byte SFX records,
    zero length byte = end) and decode the SFX ones."""
    cues = []
    offset = HEADER_SIZE
    while offset + 5 <= len(data):
        record_len = data[offset + 4]
        if record_len == 0:
            break
        if record_len == SFX_RECORD_SIZE:
            if offset + SFX_RECORD_SIZE > len(data):
                raise GcfesndError(f"Truncated SFX record at {offset:#x}.")
            name_raw = struct.unpack_from(">I", data, offset)[0]
            flags, volume, pan = data[offset + 5], data[offset + 6], data[offset + 7]
            sound_id = struct.unpack_from(">I", data, offset + 8)[0]
            range_value = struct.unpack_from(">I", data, offset + 0x10)[0]
            cues.append(SfxCue(offset=offset, name=_read_cstring_at(data, name_raw + HEADER_SIZE),
                               name_offset=name_raw, flags=flags, volume=volume, pan=pan, sound_id=sound_id,
                               extra=bytes(data[offset + 0xC:offset + 0x10]), range_value=range_value))
        elif record_len != BGM_RECORD_SIZE:
            raise GcfesndError(f"Unexpected record length {record_len} at {offset:#x}.")
        offset += record_len
    return cues


def read_sfx_cues_path(path: Path | str) -> list[SfxCue]:
    return read_sfx_cues(Path(path).read_bytes())


# -- growing the file ---------------------------------------------------------
#
# The file is an HSDArc-style "labeled section" container (CONTAINER_FORMATS.md
# section 2): 0x20-byte header, data (the cue records, the ENV/REV/SFX tables,
# then the label pool), a relocation table listing every data position that
# holds a pointer, then the section table. Inserting bytes in the middle
# therefore means shifting every listed pointer value and position that lies
# after the insertion, every section address, and the header sizes - exactly
# what the game's own loader relies on being consistent. Nothing here has been
# tried in the game itself.

SFX_NAME_MAX = 60


def _read_container(data: bytes) -> tuple[int, int, int, int]:
    filesize, data_size, reloc_count, section_count, import_count = struct.unpack_from(">5I", data, 0)
    if filesize != len(data):
        raise GcfesndError(f"Header file size {filesize:#x} does not match the file ({len(data):#x}).")
    if import_count:
        raise GcfesndError("gcfesnd.bin with an import table is not supported.")
    return data_size, reloc_count, section_count, HEADER_SIZE + data_size


def _insert_data(data: bytes, pos: int, blob: bytes, *, shift_pointers_at_pos: bool = True) -> bytes:
    """Insert ``blob`` at data position ``pos`` (relative to the end of the
    header), keeping every pointer consistent."""
    data_size, reloc_count, section_count, reloc_start = _read_container(data)
    if not 0 <= pos <= data_size:
        raise GcfesndError(f"Insert position {pos:#x} is outside the data area.")
    added = len(blob)
    relocs = list(struct.unpack_from(f">{reloc_count}I", data, reloc_start))
    sections_start = reloc_start + 4 * reloc_count

    body = bytearray(data[HEADER_SIZE:HEADER_SIZE + data_size])

    def moves(value: int) -> bool:
        return value > pos or (shift_pointers_at_pos and value == pos)

    for position in relocs:
        value = struct.unpack_from(">I", body, position)[0]
        if moves(value):
            struct.pack_into(">I", body, position, value + added)
    body[pos:pos] = blob
    relocs = [position + added if position >= pos else position for position in relocs]

    sections = bytearray(data[sections_start:])
    for i in range(section_count):
        address = struct.unpack_from(">I", sections, 8 * i)[0]
        if moves(address):
            struct.pack_into(">I", sections, 8 * i, address + added)

    header = bytearray(data[:HEADER_SIZE])
    struct.pack_into(">II", header, 0, len(data) + added, data_size + added)
    return bytes(header) + bytes(body) + struct.pack(f">{len(relocs)}I", *relocs) + bytes(sections)


def _add_reloc(data: bytes, position: int) -> bytes:
    """List a new pointer position in the relocation table."""
    data_size, reloc_count, _sections, reloc_start = _read_container(data)
    relocs = list(struct.unpack_from(f">{reloc_count}I", data, reloc_start))
    if position in relocs:
        return data
    relocs.append(position)
    relocs.sort()
    header = bytearray(data[:HEADER_SIZE])
    struct.pack_into(">I", header, 0, len(data) + 4)
    struct.pack_into(">I", header, 8, reloc_count + 1)
    tail = data[reloc_start + 4 * reloc_count:]
    return bytes(header) + data[HEADER_SIZE:reloc_start] + struct.pack(f">{len(relocs)}I", *relocs) + tail


def _end_of_records(data: bytes) -> int:
    """Data position (file offset - HEADER_SIZE) of the zero-length record that ends the array."""
    offset = HEADER_SIZE
    while offset + 5 <= len(data):
        record_len = data[offset + 4]
        if record_len == 0:
            return offset - HEADER_SIZE
        offset += record_len
    raise GcfesndError("The record array has no terminator.")


def validate_sfx_name(name: str) -> None:
    if not name.startswith("SFX_") or len(name) <= 4:
        raise GcfesndError("A sound effect name must start with SFX_.")
    if len(name) > SFX_NAME_MAX or not all(c.isascii() and (c.isalnum() or c == "_") and not c.islower() for c in name):
        raise GcfesndError(f"Use capital letters, digits and _ only (at most {SFX_NAME_MAX} characters).")


def add_sfx_cue(data: bytes, name: str, *, flags: int, volume: int, pan: int, sound_id: int,
                extra: bytes, range_value: int) -> bytes:
    """Append a new ``SFX_*`` record (and its name in the label pool)."""
    validate_sfx_name(name)
    if name in {c.name for c in read_sfx_cues(data)}:
        raise GcfesndError(f"A cue named {name} already exists.")
    if len(extra) != 4 or not (0 <= volume <= 127 and 0 <= pan <= 127 and 0 <= sound_id <= 0xFFFF):
        raise GcfesndError("Volume and pan must be 0-127, the sound id 0-65535 and extra 4 bytes.")

    record_pos = _end_of_records(data)
    data_size = _read_container(data)[0]
    # the name lands at the end of the label pool, which has moved by one record by then
    name_pos = data_size + SFX_RECORD_SIZE
    record = bytearray(SFX_RECORD_SIZE)
    struct.pack_into(">I", record, 0, name_pos)
    record[4], record[5], record[6], record[7] = SFX_RECORD_SIZE, flags, volume, pan
    struct.pack_into(">I", record, 8, sound_id)
    record[0xC:0x10] = extra
    struct.pack_into(">I", record, 0x10, range_value)

    out = _insert_data(data, record_pos, bytes(record))
    out = _add_reloc(out, record_pos)
    encoded = name.encode("ascii") + b"\0"
    encoded += bytes(-len(encoded) % 4)
    out = _insert_data(out, _read_container(out)[0], encoded, shift_pointers_at_pos=False)
    return out


def set_sfx_sound_id(data: bytes, cue_name: str, sound_id: int) -> bytes:
    """Point an existing cue at another sound (FX) id, leaving everything else alone."""
    if not 0 <= sound_id <= 0xFFFF:
        raise GcfesndError("The sound id must be 0-65535.")
    cue = next((c for c in read_sfx_cues(data) if c.name == cue_name), None)
    if cue is None:
        raise GcfesndError(f"No SFX cue named {cue_name!r}.")
    out = bytearray(data)
    struct.pack_into(">I", out, cue.offset + 8, sound_id)
    return bytes(out)
