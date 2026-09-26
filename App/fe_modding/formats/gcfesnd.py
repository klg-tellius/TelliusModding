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
for the full derivation) - only the first 111 records (all ``BGM_*``) are
covered here; the ~1,150 ``SFX_*`` records after them use a different,
20-byte record layout not decoded by this module.

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
