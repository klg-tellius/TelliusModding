"""Minimal reader for the MusyX sound banks next to ``Sound/gcfesnd.bin``
(``gcfesnd``, ``gcfesnd_etc`` and ``gcfesnd_magic``, each a ``.pool`` +
``.sdir`` + ``.samp`` trio). Just enough to turn an ``SFX_*`` cue's sound id
into playable PCM; it is not a MusyX sequencer.

- ``.proj``: a chain of groups (``u32 next_offset, u16 id, u16 type``, then
  offsets to macro/sample/curve/keymap/layer lists and three type-specific
  offsets). Type 0 is a *song* group, type 1 an *FX* group whose third
  offset points at the FX table: ``u16 count, u16 pad`` then 10-byte entries
  ``u16 fx_id, u16 macro, u8 max_voices, u8 priority, u8 volume, u8 pan,
  u8 key, u8 voice_group``. A cue's ``sound_id`` is an FX id. Its "macro" is
  an object id: with the ``0x8000`` flag it names a *layer* instead (layout
  from the public MusyX decompilation, https://github.com/AxioDL/musyx).
- ``.pool``: 4 big-endian offsets: sound macros (``0x10``), tables, keymaps
  (unused here, 0) and layers. Each macro is ``u32 size`` (including this 8-byte header),
  ``u16 id``, ``u16`` pad, then 8-byte commands. A command's opcode is the low
  byte of its first word; ``0x10`` (start sample) carries the sample id in the
  two bytes above it, ``0x08`` (play macro) the target macro id the same way,
  ``0x00`` ends the macro. Sample ids are one id space across the three banks,
  so a macro's sample may sit in another bank; macro ids do not overlap
  between banks either. A layer is ``u32 size, u16 id (0x8000 flag), u16 pad,
  u32 count`` then 12-byte entries ``u16 macro, u8 key_low, u8 key_high,
  s8 transpose, u8 volume, s8 priority_offset, u8 span, u8 pan`` + 3 pad: the
  macros it starts together (typically a left/right pair, pan 0 and 127).
  The layer list ends with ``0xFFFFFFFF``. Checked against the game's own
  audio: a layered cue plays the layer's macros, not the macro with the
  same number.
- ``.sdir``: 32-byte sample records sorted by id (the game binary-searches
  them) and ended by a 4-byte record with id ``0xFFFF``, followed by the ADPCM
  info blocks; each record is ``u16 id, u16 pad, u32 samp_offset,
  u32 pad, u8 base_key, u24 sample_rate, u8 format + u24 sample_count,
  u32 loop_offset, u32 loop_length, u32 adpcm_info_offset``. The ADPCM info
  (offset into the ``.sdir`` itself) is 0x28 bytes: 8 bytes of unknown header,
  then the 16 DSP-ADPCM coefficients (found by trying offsets: only this one
  decodes to smooth audio).
- ``.samp``: the raw sample data (DSP-ADPCM frames for format 0).

Only the first start-sample command reachable from a macro is used, played at
the sample's own rate: pitch, ADSR and layering commands are ignored, so a cue
that layers or transposes samples will sound approximate. Not decoded:
non-ADPCM sample formats (reported as unsupported)."""

from __future__ import annotations

import struct
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from . import dsp_adpcm

BANKS = ("gcfesnd", "gcfesnd_etc", "gcfesnd_magic")
SDIR_RECORD_SIZE = 32
SDIR_END_ID = 0xFFFF
OP_END = 0x00
OP_PLAY_MACRO = 0x08
OP_START_SAMPLE = 0x10
OP_ADD_KEY = 0x18
OP_SET_KEY = 0x19
OP_RANDOM_KEY = 0x17
OP_WAIT_MS = 0x07
WAIT_FOREVER = 0xFFFF
LOOP_PREVIEW_SECONDS = 4.0   # a looping sample sounds until the game stops it; preview this long
FORMAT_DSP_ADPCM = 0
MAX_MACRO_DEPTH = 8
GROUP_HEADER_SIZE = 0x28
GROUP_TYPE_SONG = 0
GROUP_TYPE_FX = 1
PAGE_SIZE = 6
MIDI_SETUP_SIZE = 0x54
END_OF_PAGES = 0xFF
FX_ENTRY_SIZE = 10
MACRO_ID_MASK = 0x7FFF
LAYER_FLAG = 0x8000
LAYER_ENTRY_SIZE = 12


class MusyxError(Exception):
    pass


@dataclass
class SampleEntry:
    sample_id: int
    samp_offset: int
    base_key: int
    sample_rate: int
    fmt: int
    sample_count: int
    loop_offset: int
    loop_length: int
    coef: list[int]


@dataclass
class FxEntry:
    fx_id: int
    macro: int
    max_voices: int
    priority: int
    volume: int
    pan: int
    key: int
    voice_group: int
    group_id: int


@dataclass
class LayerEntry:
    macro: int
    key_low: int
    key_high: int
    transpose: int
    volume: int
    priority_offset: int
    span: int
    pan: int


@dataclass
class Page:
    """Program slot of a song group's page table."""
    macro: int
    priority: int
    max_voices: int
    index: int  # the MIDI program number this slot answers to


@dataclass
class ChannelSetup:
    program: int
    volume: int
    panning: int
    reverb: int
    chorus: int


@dataclass
class SongGroup:
    group_id: int
    pages: dict[int, Page]  # program -> page
    drum_pages: dict[int, Page]
    setups: dict[int, list[ChannelSetup]]  # song id -> 16 channel setups


@dataclass
class Sfx:
    """Decoded, ready-to-play mono PCM16 for one cue."""
    sample_rate: int
    samples: list[int]
    bank: str
    sample_id: int


def _parse_pages(proj: bytes, offset: int) -> dict[int, Page]:
    pages = {}
    while offset + PAGE_SIZE <= len(proj) and proj[offset + 4] != END_OF_PAGES:
        macro, priority, max_voices, index, _reserved = struct.unpack_from(">HBBBB", proj, offset)
        pages[index] = Page(macro, priority, max_voices, index)
        offset += PAGE_SIZE
    return pages


def _parse_song_group(proj: bytes, offset: int, next_offset: int, group_id: int) -> SongGroup:
    normal, drum, setups = struct.unpack_from(">3I", proj, offset + 0x1C)
    end = min(next_offset, len(proj))
    parsed: dict[int, list[ChannelSetup]] = {}
    while setups + MIDI_SETUP_SIZE <= end:
        song_id = struct.unpack_from(">H", proj, setups)[0]
        if song_id == 0xFFFF:
            break
        parsed[song_id] = [ChannelSetup(*proj[setups + 4 + 5 * c:setups + 9 + 5 * c]) for c in range(16)]
        setups += MIDI_SETUP_SIZE
    return SongGroup(group_id, _parse_pages(proj, normal), _parse_pages(proj, drum), parsed)


class Bank:
    def __init__(self, name: str, pool: bytes, sdir: bytes, samp_path: Path, proj: bytes = b""):
        self.name = name
        self._samp_path = samp_path
        self.macros: dict[int, list[tuple[int, int]]] = {}
        self.samples: dict[int, SampleEntry] = {}
        self.fx: dict[int, FxEntry] = {}
        self.layers: dict[int, list[LayerEntry]] = {}  # layer id with its 0x8000 flag
        self.song_groups: list[SongGroup] = []
        self._parse_pool(pool)
        self._parse_sdir(sdir)
        self._parse_proj(proj)

    def _parse_proj(self, proj: bytes) -> None:
        offset = 0
        while offset + GROUP_HEADER_SIZE <= len(proj):
            next_offset, group_id, group_type = struct.unpack_from(">IHH", proj, offset)
            if group_type == GROUP_TYPE_SONG:
                self.song_groups.append(_parse_song_group(proj, offset, next_offset, group_id))
            if group_type == GROUP_TYPE_FX:
                table = struct.unpack_from(">I", proj, offset + 0x1C)[0]
                count = struct.unpack_from(">H", proj, table)[0]
                for i in range(count):
                    fx_id, macro, *rest = struct.unpack_from(">HH6B", proj, table + 4 + FX_ENTRY_SIZE * i)
                    self.fx[fx_id] = FxEntry(fx_id, macro, *rest, group_id)
            if next_offset <= offset:
                break
            offset = next_offset

    def _parse_pool(self, pool: bytes) -> None:
        header = struct.unpack_from(">4I", pool, 0)
        later = [h for h in header[1:] if h > header[0]]
        end = min(later) if later else len(pool)
        offset = header[0]
        while offset + 8 <= end:
            size, macro_id = struct.unpack_from(">IH", pool, offset)
            if size < 8:
                break
            if macro_id not in self.macros:  # a duplicate id keeps its first definition
                self.macros[macro_id] = [
                    struct.unpack_from(">II", pool, i) for i in range(offset + 8, offset + size - 7, 8)]
            offset += size
        self._parse_layers(pool, header[3])

    def _parse_layers(self, pool: bytes, offset: int) -> None:
        while offset and offset + 12 <= len(pool):
            size, layer_id, _pad, count = struct.unpack_from(">IHHI", pool, offset)
            if size == 0xFFFFFFFF or size < 12:
                break
            entries = []
            for i in range(min(count, (size - 12) // LAYER_ENTRY_SIZE)):
                macro, low, high, transpose, volume, priority, span, pan = struct.unpack_from(
                    ">HBBbBbBB", pool, offset + 12 + LAYER_ENTRY_SIZE * i)
                entries.append(LayerEntry(macro, low, high, transpose, volume, priority, span, pan))
            self.layers[layer_id] = entries
            offset += size

    def _parse_sdir(self, sdir: bytes) -> None:
        for offset in range(0, len(sdir) - SDIR_RECORD_SIZE + 1, SDIR_RECORD_SIZE):
            if struct.unpack_from(">H", sdir, offset)[0] == SDIR_END_ID:
                break
            sample_id, _pad, samp_offset, _pad2, key_rate, fmt_count, loop_offset, loop_length, info = \
                struct.unpack_from(">HHIIIIIII", sdir, offset)
            if info + 8 + 32 > len(sdir):
                continue
            coef = list(struct.unpack_from(">16h", sdir, info + 8))
            self.samples[sample_id] = SampleEntry(
                sample_id, samp_offset, key_rate >> 24, key_rate & 0xFFFFFF, fmt_count >> 24,
                fmt_count & 0xFFFFFF, loop_offset, loop_length, coef)

    def first_sample(self, macro_id: int, depth: int = 0) -> int | None:
        """Sample id of the first start-sample command reachable from a macro."""
        plan = self.first_voice(macro_id, 60)
        return plan[0] if plan else None

    def first_voice(self, macro_id: int, note: int, depth: int = 0) -> tuple[int, int] | None:
        """(sample id, MIDI note it plays at) for the first start-sample command
        reachable from a macro started with ``note``. Set-key and add-key
        commands before it change the note (``0x19`` fixes it, ``0x18`` offsets
        it by a signed byte, from the played note if byte 3 is set, ``0x17``
        picks a random note between bytes 1 and 3: the middle one is used,
        which matches the game's audio within the random spread)."""
        if depth > MAX_MACRO_DEPTH or macro_id not in self.macros:
            return None
        current = note
        for word0, _word1 in self.macros[macro_id]:
            opcode = word0 & 0xFF
            if opcode == OP_START_SAMPLE:
                return (word0 >> 8) & 0xFFFF, current
            if opcode == OP_SET_KEY:
                current = (word0 >> 8) & 0x7F
            elif opcode == OP_RANDOM_KEY:
                # the game picks a note in [byte 1, byte 3]; render the middle one
                low, high = (word0 >> 8) & 0x7F, (word0 >> 24) & 0x7F
                current = (min(low, high) + max(low, high) + 1) // 2
            elif opcode == OP_ADD_KEY:
                delta = (word0 >> 8) & 0xFF
                delta -= 256 if delta > 127 else 0
                current = max(0, min(127, (note if (word0 >> 24) else current) + delta))
            elif opcode == OP_PLAY_MACRO:
                found = self.first_voice((word0 >> 8) & 0xFFFF, current, depth + 1)
                if found is not None:
                    return found
            elif opcode == OP_END:
                break
        return None

    def start_delay_ms(self, macro_id: int, depth: int = 0) -> int:
        """Milliseconds of timed waits (``0x07``: ms in the high half of word 1;
        byte 3 set means "until the sample ends" instead) before the first
        start-sample command. The game starts such sounds that much later."""
        if depth > MAX_MACRO_DEPTH or macro_id not in self.macros:
            return 0
        total = 0
        for word0, word1 in self.macros[macro_id]:
            opcode = word0 & 0xFF
            if opcode in (OP_START_SAMPLE, OP_END):
                break
            if opcode == OP_WAIT_MS and not (word0 >> 24) & 1 and (word1 >> 16) != WAIT_FOREVER:
                total += word1 >> 16
            elif opcode == OP_PLAY_MACRO:
                return total + self.start_delay_ms((word0 >> 8) & 0xFFFF, depth + 1)
        return total

    def decode(self, sample_id: int) -> tuple[int, list[int]]:
        entry = self.samples.get(sample_id)
        if entry is None:
            raise MusyxError(f"Sample {sample_id} is not in bank {self.name}.")
        if entry.fmt != FORMAT_DSP_ADPCM:
            raise MusyxError(f"Sample {sample_id} uses unsupported format {entry.fmt}.")
        size = dsp_adpcm.bytes_for_adpcm_samples(entry.sample_count)
        with open(self._samp_path, "rb") as stream:
            stream.seek(entry.samp_offset)
            data = stream.read(size)
        if len(data) < size:
            raise MusyxError(f"Sample {sample_id}: .samp is shorter than the sample data.")
        pcm = dsp_adpcm.decode(data, dsp_adpcm.AdpcmInfo(coef=entry.coef), entry.sample_count)
        return entry.sample_rate, pcm


class SoundBanks:
    """All three banks of a project's ``Sound`` folder."""

    def __init__(self, sound_dir: Path | str):
        sound_dir = Path(sound_dir)
        self.banks: list[Bank] = []
        self._pcm_cache: dict[tuple[str, int], np.ndarray] = {}
        for name in BANKS:
            pool, sdir, samp, proj = (sound_dir / f"{name}.{ext}" for ext in ("pool", "sdir", "samp", "proj"))
            if pool.exists() and sdir.exists() and samp.exists() and proj.exists():
                self.banks.append(Bank(name, pool.read_bytes(), sdir.read_bytes(), samp, proj.read_bytes()))
        if not self.banks:
            raise MusyxError("No gcfesnd .pool/.sdir/.samp/.proj files found.")

    def fx_entry(self, sound_id: int) -> FxEntry | None:
        """The FX table entry a cue's sound id names (first bank that has it)."""
        for bank in self.banks:
            if sound_id in bank.fx:
                return bank.fx[sound_id]
        return None

    def resolve(self, sound_id: int) -> tuple[Bank, int] | None:
        """(bank holding the sample, sample id) of the first voice a cue's
        sound id plays, or None if unresolved."""
        entry = self.fx_entry(sound_id)
        if entry is None:
            return None
        voices = self.voices(entry.macro, entry.key)
        return (voices[0][0], voices[0][1]) if voices else None

    def voices(self, object_id: int, note: int) -> list[tuple[Bank, int, int, float, float]]:
        """(bank, sample id, note, gain, start delay in seconds) for every voice
        an object id starts with ``note``: one for a macro, one per matching
        entry for a layer (``0x8000`` flag)."""
        if not object_id & LAYER_FLAG:
            voice = self.voice_for_macro(object_id, note)
            return [(*voice, 1.0, self._start_delay(object_id))] if voice else []
        layer = next((b.layers[object_id] for b in self.banks if object_id in b.layers), None)
        out = []
        for part in layer or []:
            if part.key_low <= note <= part.key_high:
                voice = self.voice_for_macro(part.macro, max(0, min(127, note + part.transpose)))
                if voice:
                    out.append((*voice, part.volume / 127.0, self._start_delay(part.macro)))
        return out

    def _start_delay(self, macro_id: int) -> float:
        bank = next((b for b in self.banks if macro_id in b.macros), None)
        return bank.start_delay_ms(macro_id) / 1000.0 if bank else 0.0

    def voice_for_macro(self, macro_id: int, note: int) -> tuple[Bank, int, int] | None:
        """(bank holding the sample, sample id, note) for a macro started with
        ``note``. A layer id (``0x8000`` flag) is not a macro: use :meth:`voices`."""
        if macro_id & LAYER_FLAG:
            return None
        for macro_bank in self.banks:
            plan = macro_bank.first_voice(macro_id, note)
            if plan is None:
                continue
            for bank in (macro_bank, *self.banks):
                if plan[0] in bank.samples:
                    return bank, plan[0], plan[1]
        return None

    def sample_pcm(self, bank: Bank, sample_id: int) -> tuple[SampleEntry, np.ndarray]:
        """Decoded mono float samples (-1..1) of a sample, cached."""
        key = (bank.name, sample_id)
        if key not in self._pcm_cache:
            _rate, pcm = bank.decode(sample_id)
            self._pcm_cache[key] = np.asarray(pcm, dtype=np.float32) / 32768.0
        return bank.samples[sample_id], self._pcm_cache[key]

    def render(self, sound_id: int) -> Sfx:
        """Mono render of a cue's sound: every voice it starts (a layer's
        left/right pair is mixed down), resampled by note versus base key and
        delayed by any timed wait before its sample starts. A looping sample
        repeats its loop for a few seconds."""
        entry = self.fx_entry(sound_id)
        if entry is None:
            raise MusyxError(f"Sound id {sound_id} is not an FX id.")
        voices = self.voices(entry.macro, entry.key)
        if not voices:
            raise MusyxError(f"Sound id {sound_id} (object {entry.macro:#06x}) starts no sample: a silent cue.")
        rate = self.sample_pcm(voices[0][0], voices[0][1])[0].sample_rate
        mix = np.zeros(0, dtype=np.float32)
        for bank, sample_id, note, gain, delay in voices:
            info, pcm = self.sample_pcm(bank, sample_id)
            end = info.loop_offset + info.loop_length
            if info.loop_length and end <= len(pcm):
                want = int(LOOP_PREVIEW_SECONDS * info.sample_rate)
                repeats = max(0, -(-(want - end) // info.loop_length))
                pcm = np.concatenate([pcm[:end]] + [pcm[info.loop_offset:end]] * repeats)
            step = 2.0 ** ((note - info.base_key) / 12.0) * info.sample_rate / rate
            if abs(step - 1.0) > 1e-3:
                pcm = np.interp(np.arange(int(len(pcm) / step)) * step, np.arange(len(pcm)), pcm).astype(np.float32)
            start = int(delay * rate)
            if start + len(pcm) > len(mix):
                mix = np.pad(mix, (0, start + len(pcm) - len(mix)))
            mix[start:start + len(pcm)] += pcm * gain / len(voices)
        ints = np.clip(mix * entry.volume / 127.0 * 32768.0, -32768, 32767).astype(np.int16)
        return Sfx(rate, ints.tolist(), voices[0][0].name, voices[0][1])


def read_stbl_names(path: Path | str) -> list[str]:
    """Names of ``gcfesnd.stbl`` entries (32-byte records, NUL-padded name in
    the first 20 bytes; the table ends with an all-zero record)."""
    data = Path(path).read_bytes()
    names = []
    for offset in range(0, len(data) - 31, 32):
        name = data[offset:offset + 20].split(b"\0")[0]
        if not name:
            break
        names.append(name.decode("ascii", "replace"))
    return names
