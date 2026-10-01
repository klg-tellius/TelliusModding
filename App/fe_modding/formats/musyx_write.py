"""Editing the MusyX banks (``gcfesnd*.pool/.proj/.sdir/.samp``): adding one
new mono sound as a sample + macro + FX table entry, so that a cue of
``gcfesnd.bin`` can play it. The layouts are in ``musyx.py``; the extra
rules used here come from the public MusyX decompilation
(https://github.com/AxioDL/musyx, ``s_data.c``/``synthdata.c``):

- the ``.sdir`` is binary-searched by sample id, so a new record goes in
  sorted position; every record's ADPCM-info offset counts from the start of
  the ``.sdir``, so inserting a 32-byte record shifts all of them by 32;
- the ``.pool`` macro table is a linked list (``u32 size, u16 id, u16 pad``,
  commands) ended by ``0xFFFFFFFF``; the header offsets after it shift;
- the ``.proj`` group headers hold absolute offsets, all of which move when
  bytes are inserted in an earlier place; a group only loads the macros and
  samples listed in its id lists, and its FX table (binary-searched by id,
  so ascending) names the macro a sound id starts.

Nothing here has been tried in the game itself."""

from __future__ import annotations

import struct
import wave
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from . import dsp_adpcm, gcfesnd
from .musyx import (FX_ENTRY_SIZE, GROUP_HEADER_SIZE, GROUP_TYPE_FX, SDIR_END_ID, SDIR_RECORD_SIZE,
                    FxEntry, MusyxError, SoundBanks)

OP_START = 0x10
ADPCM_INFO_SIZE = 0x28
SAMP_ALIGN = 0x20
DEFAULT_BASE_KEY = 60
# Commands of a one-shot macro, copied from the game's own simple cues
# (macro 866 and friends) minus their fixed-key command: 0x38 is sent first
# by every macro seen, then start sample, wait for the sample to end, stop.
MACRO_PRELUDE = (0x00000038, 0x00107AC0)
MACRO_WAIT = (0x01000107, 0xFFFF0000)
MACRO_TAIL = ((0x00000011, 0), (0x00000031, 0), (0, 0))
# group header words holding offsets (nextOff, then lists / tables)
GROUP_POINTER_FIELDS = (0x00, 0x08, 0x0C, 0x10, 0x14, 0x18, 0x1C, 0x20, 0x24)
FIELD_MACRO_LIST = 0x08
FIELD_SAMPLE_LIST = 0x0C
FIELD_FX_TABLE = 0x1C


@dataclass
class NewSound:
    sample_id: int
    macro_id: int
    fx_id: int
    bank_name: str


# -- .sdir / .samp -------------------------------------------------------------

def _sdir_record_count(sdir: bytes) -> int:
    count = 0
    while (count + 1) * SDIR_RECORD_SIZE <= len(sdir) and struct.unpack_from(">H", sdir, count * SDIR_RECORD_SIZE)[0] != SDIR_END_ID:
        count += 1
    return count


def add_sample(sdir: bytes, samp: bytes, sample_id: int, pcm: list[int], sample_rate: int,
               base_key: int = DEFAULT_BASE_KEY) -> tuple[bytes, bytes]:
    """Encode ``pcm`` (mono PCM16) as DSP-ADPCM and register it as sample ``sample_id``."""
    if not pcm:
        raise MusyxError("The audio is empty.")
    if not 0 <= sample_id < SDIR_END_ID:
        raise MusyxError(f"Sample id {sample_id} is out of range.")
    count = _sdir_record_count(sdir)
    ids = [struct.unpack_from(">H", sdir, i * SDIR_RECORD_SIZE)[0] for i in range(count)]
    if sample_id in ids:
        raise MusyxError(f"Sample id {sample_id} already exists in this bank.")

    info = dsp_adpcm.AdpcmInfo()
    adpcm = dsp_adpcm.encode(list(pcm), info)

    samp_out = bytearray(samp)
    samp_out += bytes(-len(samp_out) % SAMP_ALIGN)
    offset = len(samp_out)
    samp_out += adpcm
    samp_out += bytes(-len(samp_out) % SAMP_ALIGN)

    index = sum(1 for existing in ids if existing < sample_id)
    shifted = bytearray(sdir)
    for i in range(count):  # every ADPCM-info offset moves down by one record
        position = i * SDIR_RECORD_SIZE + 28
        extra = struct.unpack_from(">I", shifted, position)[0]
        if extra:
            struct.pack_into(">I", shifted, position, extra + SDIR_RECORD_SIZE)
    info_offset = len(sdir) + SDIR_RECORD_SIZE
    record = struct.pack(">HHIIIIIII", sample_id, 0, offset, 0, (base_key << 24) | sample_rate,
                         len(pcm), 0, 0, info_offset)
    first_two = adpcm[:2].ljust(2, b"\0")
    block = struct.pack(">H", 8) + first_two + struct.pack(">hh", 0, 0) + struct.pack(">16h", *info.coef)
    if len(block) != ADPCM_INFO_SIZE:
        raise MusyxError("Internal error: ADPCM info block has the wrong size.")
    sdir_out = bytes(shifted[:index * SDIR_RECORD_SIZE]) + record + bytes(shifted[index * SDIR_RECORD_SIZE:]) + block
    return sdir_out, bytes(samp_out)


# -- .pool -----------------------------------------------------------------------

def _macro_list_end(pool: bytes) -> int:
    """Position of the 0xFFFFFFFF that ends the macro linked list."""
    position = struct.unpack_from(">I", pool, 0)[0]
    while True:
        size = struct.unpack_from(">I", pool, position)[0]
        if size == 0xFFFFFFFF:
            return position
        if size < 8:
            raise MusyxError("Corrupt macro table.")
        position += size


def add_macro(pool: bytes, macro_id: int, sample_id: int) -> bytes:
    """Add a one-shot macro that starts ``sample_id`` and waits for it to end."""
    end = _macro_list_end(pool)
    position = struct.unpack_from(">I", pool, 0)[0]
    while position < end:
        size, existing = struct.unpack_from(">IH", pool, position)
        if existing == macro_id:
            raise MusyxError(f"Macro id {macro_id} already exists in this bank.")
        position += size
    commands = [MACRO_PRELUDE, (OP_START | (sample_id << 8), 0), MACRO_WAIT, *MACRO_TAIL]
    body = b"".join(struct.pack(">II", a, b) for a, b in commands)
    entry = struct.pack(">IHH", 8 + len(body), macro_id, 0) + body
    out = bytearray(pool[:end]) + entry + bytearray(pool[end:])
    for field in (4, 8, 12):  # curve / keymap / layer table offsets follow the macro list
        value = struct.unpack_from(">I", out, field)[0]
        if value > end:
            struct.pack_into(">I", out, field, value + len(entry))
    return bytes(out)


# -- .proj -----------------------------------------------------------------------

def _groups(proj: bytes) -> list[int]:
    """Start offsets of the groups (the 0xFFFFFFFF terminator is not one)."""
    starts = []
    position = 0
    while position + GROUP_HEADER_SIZE <= len(proj):
        next_offset = struct.unpack_from(">I", proj, position)[0]
        if next_offset == 0xFFFFFFFF:
            break
        starts.append(position)
        if next_offset <= position:
            raise MusyxError("Corrupt project group chain.")
        position = next_offset
    return starts


def _insert_in_proj(proj: bytes, at: int, blob: bytes, group_start: int, extended_field: int | None) -> bytes:
    """Insert ``blob`` at ``at`` inside the group at ``group_start`` and move
    every offset that points at or after it. ``extended_field`` is the header
    field whose list/table is being grown: its own start never moves."""
    added = len(blob)
    out = bytearray(proj)
    for start in _groups(proj):
        for field in GROUP_POINTER_FIELDS:
            value = struct.unpack_from(">I", out, start + field)[0]
            if value in (0, 0xFFFFFFFF):
                continue
            if start == group_start and field == 0:
                struct.pack_into(">I", out, start, value + added)  # this group's end
            elif start == group_start and field == extended_field:
                if value > at:
                    struct.pack_into(">I", out, start + field, value + added)
            elif value >= at:
                struct.pack_into(">I", out, start + field, value + added)
    out[at:at] = blob
    return bytes(out)


def _group_with_fx(proj: bytes, group_id: int) -> int:
    for start in _groups(proj):
        gid, gtype = struct.unpack_from(">HH", proj, start + 4)
        if gid == group_id and gtype == GROUP_TYPE_FX:
            return start
    raise MusyxError(f"No FX group {group_id} in this bank.")


def _id_list_end(proj: bytes, list_offset: int) -> tuple[int, set[int]]:
    """(position of the 0xFFFF terminator, ids listed) of a u16 id list."""
    position = list_offset
    ids: set[int] = set()
    while True:
        value = struct.unpack_from(">H", proj, position)[0]
        if value == 0xFFFF:
            return position, ids
        if value & 0x8000:
            ids.update(range(value & 0x3FFF, struct.unpack_from(">H", proj, position + 2)[0] + 1))
            position += 4
        else:
            ids.add(value)
            position += 2


def add_fx(proj: bytes, group_id: int, fx_id: int, macro_id: int, sample_id: int, *, volume: int = 127,
           pan: int = 64, key: int = DEFAULT_BASE_KEY, priority: int = 10, max_voices: int = 1,
           voice_group: int = 0) -> bytes:
    """List the macro and sample in an FX group and add the FX table entry
    ``fx_id`` -> ``macro_id`` (kept in ascending id order: the game binary-searches it)."""
    start = _group_with_fx(proj, group_id)
    table = struct.unpack_from(">I", proj, start + FIELD_FX_TABLE)[0]
    count = struct.unpack_from(">H", proj, table)[0]
    ids = [struct.unpack_from(">H", proj, table + 4 + FX_ENTRY_SIZE * i)[0] for i in range(count)]
    if fx_id in ids:
        raise MusyxError(f"FX id {fx_id} already exists in group {group_id}.")
    if ids and fx_id < max(ids):
        raise MusyxError("New FX ids must be larger than the group's existing ones.")

    # from the highest position down so earlier positions stay valid
    entry = struct.pack(">HH6B", fx_id, macro_id, max_voices, priority, volume, pan, key, voice_group)
    entry += bytes(-len(entry) % 4)
    end_of_table = table + 4 + FX_ENTRY_SIZE * count
    grown = bytearray(_insert_in_proj(proj, end_of_table, entry, start, FIELD_FX_TABLE))
    struct.pack_into(">H", grown, table, count + 1)
    out = bytes(grown)

    sample_list = struct.unpack_from(">I", out, start + FIELD_SAMPLE_LIST)[0]
    position, listed = _id_list_end(out, sample_list)
    if sample_id not in listed:
        out = _insert_in_proj(out, position, struct.pack(">H", sample_id), start, FIELD_SAMPLE_LIST)
    macro_list = struct.unpack_from(">I", out, start + FIELD_MACRO_LIST)[0]
    position, listed = _id_list_end(out, macro_list)
    if macro_id not in listed:
        out = _insert_in_proj(out, position, struct.pack(">H", macro_id), start, FIELD_MACRO_LIST)
    return _pad_groups(out)


def _pad_groups(proj: bytes) -> bytes:
    """The two id-list insertions add 2 bytes each; nothing needs padding when
    both happened, but a single one would leave later groups 2-byte aligned."""
    misaligned = [s for s in _groups(proj) if s % 4]
    if misaligned:
        raise MusyxError("Project groups lost their 4-byte alignment.")
    return proj


# -- putting it together ------------------------------------------------------------

def load_mono_wav(path) -> tuple[int, list[int]]:
    """(sample rate, mono PCM16) of a 16-bit WAV file; stereo is averaged."""
    with wave.open(str(path), "rb") as source:
        channels, width, rate, frames = source.getnchannels(), source.getsampwidth(), source.getframerate(), source.getnframes()
        raw = source.readframes(frames)
    if width != 2:
        raise MusyxError(f"Only 16-bit WAV is supported (this file is {width * 8}-bit).")
    samples = np.frombuffer(raw, dtype="<i2").astype(np.int32)
    if channels > 1:
        samples = samples[:len(samples) // channels * channels].reshape(-1, channels).mean(axis=1).astype(np.int32)
    return rate, samples.astype(int).tolist()


@dataclass
class FxGroupInfo:
    bank: str
    group_id: int
    entries: int


def fx_groups(banks: SoundBanks) -> list[FxGroupInfo]:
    counts: dict[tuple[str, int], int] = {}
    for bank in banks.banks:
        for entry in bank.fx.values():
            counts[(bank.name, entry.group_id)] = counts.get((bank.name, entry.group_id), 0) + 1
    return [FxGroupInfo(bank, group, count) for (bank, group), count in sorted(counts.items())]


def _next_ids(banks: SoundBanks) -> tuple[int, int, int]:
    """(sample id, macro id, FX id), each one above everything in use in any bank."""
    sample = max(max(b.samples, default=0) for b in banks.banks) + 1
    macro = max(max(b.macros, default=0) for b in banks.banks) + 1
    fx = max(max(b.fx, default=0) for b in banks.banks) + 1
    return sample, macro, fx


def add_sound(sound_dir: Path | str, bank_name: str, group_id: int, pcm: list[int], sample_rate: int, *,
              volume: int = 127, pan: int = 64, like: FxEntry | None = None) -> tuple[NewSound, dict[str, bytes]]:
    """Build the new bank files holding one new sound. Returns the ids used
    and ``{file name: new bytes}`` for the bank's .sdir/.samp/.pool/.proj
    (nothing is written)."""
    sound_dir = Path(sound_dir)
    banks = SoundBanks(sound_dir)
    if not any(b.name == bank_name for b in banks.banks):
        raise MusyxError(f"No bank {bank_name}.")
    sample_id, macro_id, fx_id = _next_ids(banks)
    if like is not None:
        settings = dict(volume=like.volume, pan=like.pan, priority=like.priority,
                        max_voices=like.max_voices, voice_group=like.voice_group)
    else:
        settings = dict(volume=volume, pan=pan)
    read = lambda ext: (sound_dir / f"{bank_name}.{ext}").read_bytes()
    sdir, samp = add_sample(read("sdir"), read("samp"), sample_id, pcm, sample_rate)
    pool = add_macro(read("pool"), macro_id, sample_id)
    proj = add_fx(read("proj"), group_id, fx_id, macro_id, sample_id, key=DEFAULT_BASE_KEY, **settings)
    files = {f"{bank_name}.sdir": sdir, f"{bank_name}.samp": samp, f"{bank_name}.pool": pool, f"{bank_name}.proj": proj}
    return NewSound(sample_id, macro_id, fx_id, bank_name), files


def add_cue(sound_dir: Path | str, name: str, bank_name: str, group_id: int, pcm: list[int], sample_rate: int, *,
            flags: int = 0, volume: int = 127, pan: int = 64, extra: bytes = bytes([30, 0, 0, 0]),
            range_value: int = 200) -> tuple[NewSound, dict[str, bytes]]:
    """Everything needed to add a new ``SFX_*`` cue playing ``pcm``."""
    sound_dir = Path(sound_dir)
    gcfesnd.validate_sfx_name(name)
    bin_data = (sound_dir / "gcfesnd.bin").read_bytes()
    sound, files = add_sound(sound_dir, bank_name, group_id, pcm, sample_rate, volume=127, pan=64)
    files["gcfesnd.bin"] = gcfesnd.add_sfx_cue(bin_data, name, flags=flags, volume=volume, pan=pan,
                                               sound_id=sound.fx_id, extra=extra, range_value=range_value)
    return sound, files


def replace_cue(sound_dir: Path | str, cue_name: str, pcm: list[int], sample_rate: int, *,
                bank_name: str | None = None, group_id: int | None = None) -> tuple[NewSound, dict[str, bytes]]:
    """Give an existing cue its own new sound. The new FX entry joins the
    group the cue's old sound came from (so it is loaded in the same places),
    copying that entry's settings; other cues sharing the old sound keep it."""
    sound_dir = Path(sound_dir)
    bin_data = (sound_dir / "gcfesnd.bin").read_bytes()
    cue = next((c for c in gcfesnd.read_sfx_cues(bin_data) if c.name == cue_name), None)
    if cue is None:
        raise MusyxError(f"No SFX cue named {cue_name!r}.")
    banks = SoundBanks(sound_dir)
    old = banks.fx_entry(cue.sound_id)
    if old is not None and (bank_name is None or group_id is None):
        owner = next(b for b in banks.banks if cue.sound_id in b.fx)
        bank_name, group_id = owner.name, old.group_id
    if bank_name is None or group_id is None:
        raise MusyxError(f"{cue_name} does not play an FX sound (it is a sequenced song or an unknown id), so choose the group for its new sound.")
    sound, files = add_sound(sound_dir, bank_name, group_id, pcm, sample_rate, like=old)
    files["gcfesnd.bin"] = gcfesnd.set_sfx_sound_id(bin_data, cue_name, sound.fx_id)
    return sound, files
