"""The Sound Room's track list, a table in ``sys/main.dol``.

The Sound Room menu plays the 64 ``BGM_`` cues named by a table of string pointers (US
``0x80298040``); the count 64 is fixed in the menu code. The names sit in one string pool
right before ``E_SoundTest`` that nothing else reads (the menu code reaches its own strings from
the pool's base at offsets past the BGM names), so the list is rewritten by repacking the names
into that pool. It holds 979 bytes in all three builds, which is room for the 64 names plus their
terminators; a name used twice is stored once.

Pictures behind the menu are ``soundroom.bin`` (:mod:`fe_modding.formats.soundroom`).
"""

from __future__ import annotations

from .dol import Dol, DolError

TRACK_COUNT = 64

# version: (pointer table, string pool start, pool end)
LAYOUT = {
    "GFEE01": (0x80298040, 0x8027D038, 0x8027D40B),
    "GFEP01": (0x802A2168, 0x80286DE8, 0x802871BB),
    "GFEJ01": (0x80292B68, 0x802764D8, 0x802768AB),
}


def _layout(version: str) -> tuple[int, int, int]:
    if version not in LAYOUT:
        raise DolError(f"No Sound Room track table for {version}.")
    return LAYOUT[version]


def _read_name(dol: Dol, address: int) -> str:
    section = dol.section_at(address)
    data = dol.read(address, min(64, section.address + section.size - address))
    return data.split(b"\0", 1)[0].decode("ascii", "replace")


def read_tracks(dol: Dol, version: str) -> list[str]:
    table, _, _ = _layout(version)
    words = dol.read(table, 4 * TRACK_COUNT)
    return [_read_name(dol, int.from_bytes(words[i:i + 4], "big")) for i in range(0, len(words), 4)]


def capacity(version: str) -> int:
    _, start, end = _layout(version)
    return end - start


def packed_size(names: list[str]) -> int:
    return sum(len(n.encode("ascii")) + 1 for n in dict.fromkeys(names))


def write_tracks(dol: Dol, version: str, names: list[str]) -> None:
    """Repack ``names`` (64 ASCII cue names) into the pool and repoint the table."""
    table, start, end = _layout(version)
    if len(names) != TRACK_COUNT:
        raise DolError(f"The Sound Room has exactly {TRACK_COUNT} tracks.")
    for name in names:
        if not name or not name.isascii() or not name.isprintable():
            raise DolError(f"Invalid track name {name!r}: use a cue name such as BGM_MAP01_ROOM.")
    if packed_size(names) > end - start:
        raise DolError(f"The names need {packed_size(names)} bytes; the table's string space holds "
                       f"{end - start}. Use shorter names or repeat a track.")
    pool, where = bytearray(), {}
    for name in names:
        if name not in where:
            where[name] = start + len(pool)
            pool += name.encode("ascii") + b"\0"
    pool += bytes(end - start - len(pool))
    dol.write(start, bytes(pool))
    dol.write(table, b"".join(where[n].to_bytes(4, "big") for n in names))
