"""Path of Radiance memory-card saves (``.gci``): every byte of a save block.

A ``.gci`` is a 0x40-byte GameCube directory entry followed by 0x26000 bytes:
0x2000 of banner/icon images, six 0x4000-byte file blocks (body
``0x2000 + i * 0x4000``) and two 0x6000-byte checkpoint (suspend) blocks at
``0x1A000`` and ``0x20000``. A file block belongs to the file slot in its
header (0-4); at boot the card loader keeps, per slot, the valid block with
the highest sequence number and invalidates the others, and a new save goes
into an invalid block (``build_save_block_for_deferred_write``).

Block layout (``finalize_save_block_header_and_compute_crc``, the writers
``build_save_block_for_deferred_write``, ``write_chapter_checkpoint_save_block``,
``init_party_and_write_new_playthrough_save_block``)::

    +0x00  char[32]  title text (FM_TITLE)          +0x20 char[32] date text
    +0x40  "FE8J"    +0x44 0x20050201   +0x48 sequence   +0x4C block size
    +0x50  CRC-32 of block[0x70:size]   +0x54 4 bytes 0
    +0x58  u64 play time (OS ticks, party_data+0x58)
    +0x60  save kind   +0x61 playthrough id   +0x62 file slot (0-4)
    +0x63  file slot a checkpoint belongs to   +0x64 chapter
    +0x65  resume point   +0x66 difficulty   +0x67..0x6F 0
    +0x70  system data (0x48 bytes, see SystemData)
    +0xB8  tagged stream: BMST, MDST, UNIP, SOKO, FWEP, "T  T", then zeros

Save kind: 2 file save, 3 checkpoint, 1 a consumed copy (only its first
0x2000 bytes are written, its CRC is not checked, and the card loader
discards it). Resume point (``resume_game_from_save_data``): see
``RESUME_POINTS``. The stream has no length fields; every record has a fixed
size except ``UNIP``, whose 159 slots are 2 bytes when empty and 143 bytes
otherwise. Characters, classes and items are stored as 1-based FE8Data table
numbers (``CharacterData+0x18``, ``JobData+0x38``, ``ItemData+0x0E``).

Research reference: ``research/SAVE_NOTES.md``.
"""

from __future__ import annotations

import struct
import zlib
from dataclasses import dataclass, field, fields
from typing import Optional

GCI_HEADER_SIZE = 0x40
SAVE_MAGIC = b"FE8J"
SAVE_VERSION = 0x20050201
SYSF_MAGIC = b"SYSF"
CRC_START = 0x70
CRC_EXEMPT = 0x12345678
STREAM_START = 0xB8
UNIT_SLOTS = 159
UNIT_RECORD_SIZE = 143
CONVOY_SLOTS = 200
FORGE_RECORDS = 48
TERRAIN_ENTRIES = 64

# (body offset, size) of the eight blocks.
BLOCK_LOCATIONS = tuple((0x2000 + i * 0x4000, 0x4000) for i in range(6)) + ((0x1A000, 0x6000), (0x20000, 0x6000))

SAVE_KINDS = {1: "consumed copy", 2: "file save", 3: "checkpoint"}
RESUME_POINTS = {
    1: "base", 2: "battle preparations", 3: "new game", 4: "chapter start",
    5: "chapter part 2", 6: "chapter part 3", 7: "chapter part 4", 8: "suspended map", 10: "trial map",
}
# Resume points whose load starts the chapter afresh: initialize_chapter_start_state
# then unregisters every chapter-local flag and clears its bit.
FRESH_START_RESUME_POINTS = (3, 4, 10)
DIFFICULTIES = {0: "Normal", 1: "Hard", 2: "Maniac", 3: "Easy"}
ARMIES = {0: "Player", 1: "Enemy", 2: "Ally", 3: "Other", 4: "Free", 5: "Reserve", 6: "Inactive", 7: "Removed"}
TERRAIN_TYPES = {
    4: "breakable", 6: "range overlay", 7: "ballista", 9: "pit", 10: "rolling rock",
    0x21: "door opened", 0x22: "roof opened", 0x23: "chest opened", 0x24: "village visited",
    0x25: "building destroyed",
}
WEAPON_EXP_TYPES = ("Sword", "Lance", "Axe", "Bow", "Fire", "Thunder", "Wind", "Staff")
UNIT_STATS = ("HP", "Str", "Mag", "Skl", "Spd", "Lck", "Def", "Res")
# Weapon EXP thresholds of the E..S ranks.
WEAPON_RANKS = (("S", 251), ("A", 181), ("B", 121), ("C", 71), ("D", 31), ("E", 1))


class _Reader:
    def __init__(self, data: bytes, pos: int = 0):
        self.data = data
        self.pos = pos

    def take(self, n: int) -> bytes:
        if self.pos + n > len(self.data):
            raise ValueError(f"save stream ends early at 0x{self.pos:X}")
        out = self.data[self.pos:self.pos + n]
        self.pos += n
        return bytes(out)

    def u8(self) -> int:
        return self.take(1)[0]

    def s8(self) -> int:
        return struct.unpack(">b", self.take(1))[0]

    def u16(self) -> int:
        return struct.unpack(">H", self.take(2))[0]

    def s16(self) -> int:
        return struct.unpack(">h", self.take(2))[0]

    def u32(self) -> int:
        return struct.unpack(">I", self.take(4))[0]

    def u64(self) -> int:
        return struct.unpack(">Q", self.take(8))[0]

    def tag(self, name: bytes) -> None:
        got = self.take(4)
        if got != name:
            raise ValueError(f"expected tag {name!r} at 0x{self.pos - 4:X}, found {got!r}")


def _text(raw: bytes) -> str:
    return raw.split(b"\0")[0].decode("shift_jis", "replace")


def _put_text(text: str, size: int) -> bytes:
    raw = text.encode("shift_jis")
    if len(raw) >= size:
        raise ValueError(f"{text!r} is longer than {size - 1} bytes")
    return raw.ljust(size, b"\0")


def _bit(mask: bytes, index: int) -> bool:
    """The engine's multi-word bitmask: big-endian u32 words, word ``index >> 5``,
    bit ``index & 31`` (``actor_has_flag_or_skill``)."""
    word = struct.unpack_from(">I", mask, (index >> 5) * 4)[0]
    return bool(word >> (index & 31) & 1)


def _set_bit(mask: bytes, index: int, on: bool) -> bytes:
    out = bytearray(mask)
    word = struct.unpack_from(">I", out, (index >> 5) * 4)[0]
    word = word | (1 << (index & 31)) if on else word & ~(1 << (index & 31))
    struct.pack_into(">I", out, (index >> 5) * 4, word)
    return bytes(out)


# -- header and system data ----------------------------------------------------

@dataclass
class BlockHeader:
    title: bytes  # 32 bytes, space padded
    date: bytes  # 32 bytes, space padded
    sequence: int
    size: int
    crc: int
    reserved_54: bytes  # 4 bytes, 0
    play_time: int  # u64 OS ticks (party_data+0x58)
    save_kind: int
    playthrough_id: int  # chapter32_special_param: this playthrough's id in the clear list
    file_slot: int  # 0-4
    owner_slot: int  # checkpoints: the file slot they suspend
    chapter: int
    resume_point: int  # party_resume_point; bit 0x80 is a transient marker
    difficulty: int
    reserved_67: bytes  # 9 bytes, 0
    magic: bytes = SAVE_MAGIC
    version: int = SAVE_VERSION

    SIZE = 0x70

    @classmethod
    def parse(cls, b: bytes) -> "BlockHeader":
        r = _Reader(b)
        title, date, magic = r.take(32), r.take(32), r.take(4)
        version, seq, size, crc = r.u32(), r.u32(), r.u32(), r.u32()
        res54, play = r.take(4), r.u64()
        kind, pid_, slot, owner, chap, resume, diff = (r.u8() for _ in range(7))
        return cls(title, date, seq, size, crc, res54, play, kind, pid_, slot, owner, chap, resume, diff,
                   r.take(9), magic, version)

    def build(self) -> bytes:
        return (self.title + self.date + self.magic
                + struct.pack(">IIII", self.version, self.sequence, self.size, self.crc)
                + self.reserved_54 + struct.pack(">Q", self.play_time)
                + bytes((self.save_kind, self.playthrough_id, self.file_slot, self.owner_slot, self.chapter,
                         self.resume_point, self.difficulty)) + self.reserved_67)


@dataclass
class SystemData:
    """The system data (``chapter32_special_context``, ``0x80331FB8``), shared by
    every save: the newest block whose copy starts with ``SYSF`` wins at boot."""

    magic: bytes  # "SYSF"
    version: int  # 0x20050201
    system_id: int  # u64 random id made with the system data; a save must match it
    unlocks: int  # u16: bit 0 game cleared (also the clear-record screens), bits 0-2/4/5 trial maps 1-6
    cleared_playthroughs: bytes  # 30 playthrough ids that reached the ending (0 = free)
    met_characters: bytes  # 16-byte bitmask, bit = character number (< 128) ever deployed
    screen_x: int  # s8 screen position (Options > Screen)
    screen_y: int  # s8
    brightness: int  # 0x40 default
    reserved_43: int
    region: int  # +0x44, derived from the console settings when the system data is made
    reserved_45: bytes  # 2 bytes, never saved (0)
    last_file_slot: int

    SIZE = 0x48

    @classmethod
    def parse(cls, b: bytes) -> "SystemData":
        r = _Reader(b)
        magic, version, sid, unlocks = r.take(4), r.u32(), r.u64(), r.u16()
        cleared, met = r.take(30), r.take(16)
        sx, sy = r.s8(), r.s8()
        bright, r43, region = r.u8(), r.u8(), r.u8()
        return cls(magic, version, sid, unlocks, cleared, met, sx, sy, bright, r43, region, r.take(2), r.u8())

    def build(self) -> bytes:
        return (self.magic + struct.pack(">IQH", self.version, self.system_id, self.unlocks)
                + self.cleared_playthroughs + self.met_characters
                + struct.pack(">bbBBB", self.screen_x, self.screen_y, self.brightness, self.reserved_43, self.region)
                + self.reserved_45 + bytes((self.last_file_slot,)))

    @property
    def playthrough_count(self) -> int:
        """``SysGetRound``: 1 + the number of leading used clear slots."""
        n = 0
        for b in self.cleared_playthroughs:
            if not b:
                break
            n += 1
        return n + 1

    def met(self, character_number: int) -> bool:
        return character_number < 128 and _bit(self.met_characters, character_number)

    def set_met(self, character_number: int, on: bool) -> None:
        if character_number < 128:
            self.met_characters = _set_bit(self.met_characters, character_number, on)


# -- BMST: party_data ---------------------------------------------------------------

@dataclass
class ClearRecord:
    """One finished map (``append_chapter_clear_history_entry``)."""

    chapter: int
    continued: int  # 1 when the map is a part that carries on into the next one
    turns: int
    seconds: int  # play time when it was cleared

    @property
    def used(self) -> bool:
        return self.turns != 0


@dataclass
class PartyState:
    """``serialize_party_data_to_stream``: ``party_data`` (``0x80330708``)."""

    head: bytes  # +0x00, 16 bytes (zeroed by reinit_party_struct, no other writer found)
    chapter: int  # +0x10 current_chapter_number
    phase: int  # +0x11 army whose phase it is
    turn: int  # +0x12
    phase_states: bytes  # +0x14, 4 bytes (1,2,2,2 at chapter start)
    gold: int  # +0x18
    bonus_exp: int  # +0x1C
    objective_texts: bytes  # +0x20, 4 x 12-byte keys copied from the chapter record
    byte_50: int  # +0x50, cleared at chapter start
    byte_51: int  # +0x51
    cursor_x: int  # +0x52 map cursor tile
    cursor_y: int  # +0x53
    resume_point: int  # +0x54
    base_opening_done: int  # +0x55: Opening1 already ran; also selects the masked unit save
    deployment_surplus: int  # +0x56
    playthrough: int  # +0x57 playthrough number (SysGetRound at New Game)
    play_time: int  # +0x58 u64 OS ticks
    timer_2: int  # +0x60 u64 OS ticks, a second accumulator
    report_profit: int  # +0x68 chapter report: gold gained
    report_loss: int  # +0x6C gold spent
    report_exp: int  # +0x70 s16 bonus EXP gained
    report_score: int  # +0x72 s16
    tutorials_unlocked: bytes  # +0x74, 128-bit mask (TutorialUnlock/Lock)
    tutorials_learned: bytes  # +0x84, 128-bit mask (TutorialLearn/Forget)
    objective_state: bytes  # +0x94, 8 bytes read by start_chapter_complete_event_if_flag_set
    options: bytes  # +0x9C, 12 bytes, see OPTION_FIELDS
    flag_bits: bytes  # +0xB4 event flag table bits (96 slots)
    clear_history: list  # +0x3C4, 40 ClearRecord
    chapter_name: str  # +0x504, "bmapNN" (0x18 bytes)
    tail: bytes  # 8 bytes, 0

    SIZE = 0x214

    @classmethod
    def parse(cls, r: _Reader) -> "PartyState":
        head, chapter, phase, turn = r.take(16), r.u8(), r.u8(), r.u16()
        states, gold, bexp, texts = r.take(4), r.u32(), r.u32(), r.take(0x30)
        b50, b51, cx, cy, resume, opening, surplus, rnd = (r.u8() for _ in range(8))
        play, timer2, profit, loss = r.u64(), r.u64(), r.u32(), r.u32()
        rexp, score = r.s16(), r.s16()
        tut_u, tut_l, obj, opts, bits = r.take(16), r.take(16), r.take(8), r.take(12), r.take(12)
        history = [ClearRecord(*struct.unpack(">BBHI", r.take(8))) for _ in range(40)]
        name = _text(r.take(0x18))
        return cls(head, chapter, phase, turn, states, gold, bexp, texts, b50, b51, cx, cy, resume, opening,
                   surplus, rnd, play, timer2, profit, loss, rexp, score, tut_u, tut_l, obj, opts, bits, history,
                   name, r.take(8))

    def build(self) -> bytes:
        out = bytearray(self.head)
        out += struct.pack(">BBH", self.chapter, self.phase, self.turn) + self.phase_states
        out += struct.pack(">II", self.gold, self.bonus_exp) + self.objective_texts
        out += bytes((self.byte_50, self.byte_51, self.cursor_x, self.cursor_y, self.resume_point,
                      self.base_opening_done, self.deployment_surplus, self.playthrough))
        out += struct.pack(">QQIIhh", self.play_time, self.timer_2, self.report_profit, self.report_loss,
                           self.report_exp, self.report_score)
        out += self.tutorials_unlocked + self.tutorials_learned + self.objective_state + self.options + self.flag_bits
        for c in self.clear_history:
            out += struct.pack(">BBHI", c.chapter, c.continued, c.turns, c.seconds)
        out += _put_text(self.chapter_name, 0x18) + self.tail
        return bytes(out)

    def objective_text(self, i: int) -> str:
        return _text(self.objective_texts[i * 12:(i + 1) * 12])

    # options byte 10 is the difficulty the game plays at
    @property
    def difficulty(self) -> int:
        return self.options[10]

    @difficulty.setter
    def difficulty(self, value: int) -> None:
        self.options = self.options[:10] + bytes((value,)) + self.options[11:]


# (byte, mask, name). Bits marked "off" are 1 when the option is turned off.
OPTION_FIELDS = (
    (0, 0x01, "Option bit 0 (off)"), (0, 0x02, "Unit window (off)"), (0, 0x04, "Terrain window (off)"),
    (0, 0x18, "Message speed (0 slow - 3 max)"), (0, 0x20, "Option byte 0 bit 5"), (0, 0xC0, "Option byte 0 bits 6-7"),
    (1, 0x01, "Option byte 1 bit 0 (off)"), (1, 0x02, "Option byte 1 bit 1 (off)"), (1, 0x0C, "Option byte 1 bits 2-3"),
    (1, 0x10, "Option byte 1 bit 4 (off)"), (1, 0x20, "Option byte 1 bit 5 (off)"), (1, 0xC0, "Option byte 1 bits 6-7"),
    (2, 0x01, "Option byte 2 bit 0 (off)"), (2, 0x02, "Option byte 2 bit 1 (off)"), (2, 0x0C, "Sound output (stereo 1)"),
    (2, 0x10, "Option byte 2 bit 4 (off)"), (2, 0x20, "Option byte 2 bit 5 (off)"), (2, 0x40, "Option byte 2 bit 6 (off)"),
    (2, 0x80, "Option byte 2 bit 7 (off)"),
    (3, 0x10, "Option byte 3 bit 4 (off)"), (3, 0x20, "Message sounds (off)"), (3, 0x40, "Show other units' moves"),
    (3, 0x80, "Fixed growths"),
)
OPTION_BYTES = ("Bits 0", "Bits 1", "Bits 2", "Bits 3", "Unit speed", "Brightness", "Screen X", "Screen Y",
                "Music volume", "Sound effect volume", "Difficulty", "Byte 11")


# -- MDST ------------------------------------------------------------------------------

MAP_STATE_BYTES = ("restore camera", "sight mode", "weather", "fog type", "fog start", "fog end", "fog colour",
                   "0x80367291", "0x80367292", "0x80367294", "0x80367295", "0x80367298", "0x80367299",
                   "0x8036729A", "0x8036729C", "0x8036729D", "0x8036729E")


@dataclass
class MapState:
    """``serialize_camera_and_cursor_state_to_stream``: map display state and camera."""

    values: bytes  # 17 bytes, MAP_STATE_BYTES
    camera_rotation: int
    camera_x: int  # s16, camera position x 0.01 tile
    camera_y: int
    padding: bytes  # 10 bytes, 0

    SIZE = 0x20

    @classmethod
    def parse(cls, r: _Reader) -> "MapState":
        return cls(r.take(17), r.u8(), r.s16(), r.s16(), r.take(10))

    def build(self) -> bytes:
        return self.values + struct.pack(">Bhh", self.camera_rotation, self.camera_x, self.camera_y) + self.padding


# -- UNIP / SOKO ---------------------------------------------------------------------------

@dataclass
class ItemSlot:
    item: int = 0  # 1-based ItemData number, 0 = empty
    uses: int = 0
    flags: int = 0  # 0x80 equipped, 0x40 dropped on defeat, low 6 bits forge record (1-48, 0 none)

    @classmethod
    def parse(cls, r: _Reader) -> "ItemSlot":
        item = r.u16()
        uses, flags = r.u8(), r.u8()
        return cls(item, uses, flags)

    def build(self) -> bytes:
        return struct.pack(">HBB", self.item, self.uses, self.flags)

    @property
    def forge(self) -> int:
        return self.flags & 0x3F

    @property
    def equipped(self) -> bool:
        return bool(self.flags & 0x80)

    @property
    def drops(self) -> bool:
        return bool(self.flags & 0x40)


@dataclass
class UnitRecord:
    """One used unit slot (``FUN_8003ca94`` / ``deserialize_unit_slot_from_stream``).
    Slot references are 1-based unit slot numbers, 0 = none."""

    character: int  # 1-based PersonData number
    job: int  # 1-based JobData number
    army: int  # ARMIES
    prev_slot: int  # army list links (+0x180/+0x184)
    next_slot: int
    linked_slot: int  # carried/rescued unit (+0x194)
    group: int  # +0x199 deployment group (army name)
    level: int
    exp: int  # 255 = no EXP (max level)
    transform_gauge: int
    byte_19d: int  # +0x19D 0-100
    x: int
    y: int
    state_flags: int  # +0x1A0 u32
    status: bytes  # +0x1A4, 4 bytes of temporary status and bonuses
    hp: int  # current HP
    build_bonus: int
    move_bonus: int
    stats: bytes  # +0x1AB, 8 bytes UNIT_STATS gained on top of the class base
    growth_points: bytes  # +0x1B4, 8 fixed-growth accumulators
    skills: bytes  # +0x1BC, 128-bit mask by FE8Data skill index
    items: list  # 8 ItemSlot
    weapon_exp: bytes  # +0x20C, 8 bytes WEAPON_EXP_TYPES
    battles: int  # +0x228 (biorhythm battle counter)
    kills: int  # +0x22A lifetime
    map_kills: int  # +0x22C
    tiles_moved: int  # +0x22E
    counter_230: int
    counter_232: int
    last_kill_chapter: int  # +0x234
    byte_235: int
    supports: bytes  # +0x214, 10 support points by RelianceData slot
    ai_attack: int  # index in ATK_SEQID_LIST
    ai_move: int  # MOV_SEQID_LIST
    ai_heal: int  # HEAL_SEQID_LIST
    ai_mtype: int  # MTYPE_TABLEID_LIST
    ai_attack_pc: int  # +0x250
    ai_move_pc: int  # +0x251
    ai_flags: int  # +0x254
    ai_258: int
    ai_25a: int
    ai_order: int  # +0x248 turn order
    field_15c: int
    padding: bytes  # 4 bytes, 0

    @classmethod
    def parse(cls, r: _Reader) -> "UnitRecord":
        ch, job = r.u16(), r.u16()
        head = [r.u8() for _ in range(11)]
        state, status = r.u32(), r.take(4)
        hp, bld, mov = r.u8(), r.u8(), r.u8()
        stats, growth, skills = r.take(8), r.take(8), r.take(16)
        items = [ItemSlot.parse(r) for _ in range(8)]
        wexp = r.take(8)
        counters = [r.u16() for _ in range(6)]
        last, b235 = r.u8(), r.u8()
        sup = r.take(10)
        ai = [r.u8() for _ in range(6)]
        aflags, a258, a25a, order = r.u32(), r.u16(), r.u16(), r.u8()
        f15c, pad = r.u16(), r.take(4)
        return cls(ch, job, *head, state, status, hp, bld, mov, stats, growth, skills, items, wexp, *counters,
                   last, b235, sup, *ai, aflags, a258, a25a, order, f15c, pad)

    def build(self) -> bytes:
        out = bytearray(struct.pack(">HH", self.character, self.job))
        out += bytes((self.army, self.prev_slot, self.next_slot, self.linked_slot, self.group, self.level, self.exp,
                      self.transform_gauge, self.byte_19d, self.x, self.y))
        out += struct.pack(">I", self.state_flags) + self.status
        out += bytes((self.hp, self.build_bonus, self.move_bonus)) + self.stats + self.growth_points + self.skills
        for it in self.items:
            out += it.build()
        out += self.weapon_exp
        out += struct.pack(">6HBB", self.battles, self.kills, self.map_kills, self.tiles_moved, self.counter_230,
                           self.counter_232, self.last_kill_chapter, self.byte_235)
        out += self.supports
        out += bytes((self.ai_attack, self.ai_move, self.ai_heal, self.ai_mtype, self.ai_attack_pc, self.ai_move_pc))
        out += struct.pack(">IHHBH", self.ai_flags, self.ai_258, self.ai_25a, self.ai_order, self.field_15c)
        out += self.padding
        assert len(out) == UNIT_RECORD_SIZE
        return bytes(out)

    def has_skill(self, index: int) -> bool:
        return _bit(self.skills, index)

    def set_skill(self, index: int, on: bool) -> None:
        self.skills = _set_bit(self.skills, index, on)


def weapon_rank(exp: int) -> str:
    for letter, threshold in WEAPON_RANKS:
        if exp >= threshold:
            return letter
    return "-"


# -- FWEP / "T  T" ------------------------------------------------------------------------

@dataclass
class ForgeRecord:
    allocated: int
    name: bytes  # 15 bytes, first byte 0 = no custom name
    might: int  # signed steps
    hit: int  # x5
    crit: int  # x3
    weight: int  # weight reduction steps
    appearance: bytes  # 4 bytes, 80 80 80 FF by default

    @classmethod
    def parse(cls, r: _Reader) -> "ForgeRecord":
        return cls(r.u8(), r.take(15), r.s8(), r.s8(), r.s8(), r.s8(), r.take(4))

    def build(self) -> bytes:
        return (bytes((self.allocated,)) + self.name
                + struct.pack(">bbbb", self.might, self.hit, self.crit, self.weight) + self.appearance)

    @property
    def name_text(self) -> str:
        return _text(self.name)


@dataclass
class TerrainEntry:
    """``AddTT``-style tile record (``DAT_8032BB58``): per-map state of doors,
    chests, villages, breakable walls, ballistae, pits and rocks."""

    x: int
    y: int
    type: int  # TERRAIN_TYPES
    subtype: int
    values: bytes  # 4 bytes; breakable: HP, max HP; ballista: item number low byte, uses; rock: [3] path

    @classmethod
    def parse(cls, r: _Reader) -> "TerrainEntry":
        return cls(r.s8(), r.s8(), r.u8(), r.u8(), r.take(4))

    def build(self) -> bytes:
        return struct.pack(">bbBB", self.x, self.y, self.type, self.subtype) + self.values


@dataclass
class TerrainTable:
    entries: list  # all 64 records (only the first ``count`` are live)
    count: int

    SIZE = 0x204

    @classmethod
    def parse(cls, r: _Reader) -> "TerrainTable":
        return cls([TerrainEntry.parse(r) for _ in range(TERRAIN_ENTRIES)], r.u32())

    def build(self) -> bytes:
        return b"".join(e.build() for e in self.entries) + struct.pack(">I", self.count)

    @property
    def live(self) -> list:
        return self.entries[:self.count]


# -- block --------------------------------------------------------------------------------

@dataclass
class SaveBlock:
    offset: int  # from the start of the .gci
    size: int
    header: BlockHeader
    raw: bytes  # the block as read
    system: Optional[SystemData] = None
    party: Optional[PartyState] = None
    map_state: Optional[MapState] = None
    units: list = field(default_factory=list)  # 159 entries: UnitRecord or None
    convoy: list = field(default_factory=list)  # 200 ItemSlot
    forges: list = field(default_factory=list)  # 48 ForgeRecord
    terrain: Optional[TerrainTable] = None
    trailing: bytes = b""  # after the stream (zeros)
    error: Optional[str] = None  # why the stream could not be decoded

    @property
    def decoded(self) -> bool:
        return self.party is not None

    @property
    def crc_ok(self) -> bool:
        h = self.header
        return h.crc == CRC_EXEMPT or h.save_kind == 1 or zlib.crc32(self.raw[CRC_START:h.size]) == h.crc

    @property
    def is_checkpoint(self) -> bool:
        return self.offset - GCI_HEADER_SIZE >= 0x1A000

    @property
    def location(self) -> int:
        """Index 0-7 in BLOCK_LOCATIONS."""
        return [o for o, _ in BLOCK_LOCATIONS].index(self.offset - GCI_HEADER_SIZE)

    @property
    def flags_stale(self) -> bool:
        """True when loading this block starts the chapter afresh, so its
        chapter-local flag bits are dropped (a save made between chapters)."""
        return (self.header.resume_point & 0x7F) in FRESH_START_RESUME_POINTS

    @classmethod
    def parse(cls, gci: bytes, offset: int, size: int) -> Optional["SaveBlock"]:
        raw = bytes(gci[offset:offset + size])
        if len(raw) < STREAM_START or raw[0x40:0x44] != SAVE_MAGIC:
            return None
        header = BlockHeader.parse(raw[:BlockHeader.SIZE])
        block = cls(offset, size, header, raw)
        block.system = SystemData.parse(raw[CRC_START:STREAM_START])
        if header.save_kind == 1:
            block.error = "consumed copy (only partly written; the game discards it)"
            return block
        try:
            r = _Reader(raw, STREAM_START)
            r.tag(b"BMST")
            block.party = PartyState.parse(r)
            r.tag(b"MDST")
            block.map_state = MapState.parse(r)
            r.tag(b"UNIP")
            units = []
            for _ in range(UNIT_SLOTS):
                if struct.unpack_from(">H", raw, r.pos)[0] == 0:
                    r.take(2)
                    units.append(None)
                else:
                    units.append(UnitRecord.parse(r))
            block.units = units
            r.tag(b"SOKO")
            block.convoy = [ItemSlot.parse(r) for _ in range(CONVOY_SLOTS)]
            r.tag(b"FWEP")
            block.forges = [ForgeRecord.parse(r) for _ in range(FORGE_RECORDS)]
            r.tag(b"T  T")
            block.terrain = TerrainTable.parse(r)
            block.trailing = raw[r.pos:]
        except (ValueError, struct.error) as exc:
            block.party = None
            block.error = str(exc)
        return block

    def build_stream(self) -> bytes:
        out = bytearray(b"BMST" + self.party.build() + b"MDST" + self.map_state.build() + b"UNIP")
        for u in self.units:
            out += u.build() if u is not None else b"\0\0"
        out += b"SOKO" + b"".join(s.build() for s in self.convoy)
        out += b"FWEP" + b"".join(f.build() for f in self.forges)
        out += b"T  T" + self.terrain.build()
        return bytes(out)

    def build(self) -> bytes:
        """The block re-encoded, padded to its size and re-signed."""
        if not self.decoded:
            return self.raw
        body = self.header.build() + self.system.build() + self.build_stream()
        trailing_len = self.size - len(body)
        if trailing_len < 0:
            raise ValueError(f"the save no longer fits its block (0x{len(body):X} > 0x{self.size:X} bytes)")
        # keep whatever followed the stream when the layout did not move, else zero-fill
        trailing = self.trailing if len(self.trailing) == trailing_len else bytes(trailing_len)
        out = bytearray(body + trailing)
        if self.header.crc != CRC_EXEMPT:
            self.header.crc = zlib.crc32(bytes(out[CRC_START:self.header.size]))
            out[0x50:0x54] = struct.pack(">I", self.header.crc)
        return bytes(out)

    # convenience

    def unit_slots(self) -> list:
        """(1-based slot, UnitRecord) of every used slot."""
        return [(i + 1, u) for i, u in enumerate(self.units) if u is not None]

    def remove_unit(self, slot: int) -> None:
        """Empty ``slot`` and close the army list around it."""
        u = self.units[slot - 1]
        if u is None:
            return
        if u.prev_slot and self.units[u.prev_slot - 1] is not None:
            self.units[u.prev_slot - 1].next_slot = u.next_slot
        if u.next_slot and self.units[u.next_slot - 1] is not None:
            self.units[u.next_slot - 1].prev_slot = u.prev_slot
        for other in self.units:
            if other is not None and other.linked_slot == slot:
                other.linked_slot = 0
        self.units[slot - 1] = None

    def add_unit(self, unit: UnitRecord, after: Optional[int] = None) -> int:
        """Put ``unit`` in the first empty slot and return it. With ``after`` (a
        used slot of the same army) it is linked right behind that unit; without,
        it keeps no links and the loader appends it to its army list."""
        free = next((i for i, u in enumerate(self.units) if u is None), None)
        if free is None:
            raise ValueError("all 159 unit slots are used")
        slot = free + 1
        unit.prev_slot = unit.next_slot = unit.linked_slot = 0
        if after:
            prev = self.units[after - 1]
            unit.prev_slot, unit.next_slot = after, prev.next_slot
            if prev.next_slot:
                self.units[prev.next_slot - 1].prev_slot = slot
            prev.next_slot = slot
        self.units[free] = unit
        return slot


@dataclass
class SaveFile:
    data: bytes
    blocks: list  # SaveBlock, in BLOCK_LOCATIONS order (empty locations omitted)

    @classmethod
    def from_bytes(cls, data: bytes) -> "SaveFile":
        blocks = []
        for rel, size in BLOCK_LOCATIONS:
            b = SaveBlock.parse(data, GCI_HEADER_SIZE + rel, size)
            if b is not None:
                blocks.append(b)
        return cls(bytes(data), blocks)

    def loaded_blocks(self) -> list:
        """The blocks the game would load: per file slot the valid file block
        with the highest sequence, plus the newest valid checkpoint."""
        best: dict = {}
        for b in self.blocks:
            if not b.crc_ok or b.header.save_kind == 1:
                continue
            key = "checkpoint" if b.is_checkpoint else b.header.file_slot
            if key not in best or b.header.sequence > best[key].header.sequence:
                best[key] = b
        return list(best.values())

    def to_bytes(self, blocks: Optional[list] = None) -> bytes:
        """The .gci with ``blocks`` (default: all decoded blocks) re-encoded."""
        out = bytearray(self.data)
        for b in self.blocks if blocks is None else blocks:
            out[b.offset:b.offset + b.size] = b.build()
        return bytes(out)


def block_label(b: SaveBlock) -> str:
    h = b.header
    where = "Checkpoint" if b.is_checkpoint else f"File {h.file_slot + 1}"
    name = b.party.chapter_name if b.party else "?"
    resume = RESUME_POINTS.get(h.resume_point & 0x7F, str(h.resume_point))
    return f"{where} - {name} - {resume} - seq {h.sequence}{'' if b.crc_ok else ' - BAD CRC'}"


# -- validation -----------------------------------------------------------------------------

def validate(block: SaveBlock, fe8=None) -> list:
    """Problems the game would choke on. ``fe8`` (an ``Fe8Data``) adds table checks."""
    out = []
    if not block.decoded:
        return [block.error or "not decoded"]
    n_char = len(fe8.characters) if fe8 else None
    n_job = len(fe8.classes) if fe8 else None
    n_item = len(fe8.items) if fe8 else None

    def item_ok(slot: ItemSlot, where: str) -> None:
        if slot.item and n_item and slot.item > n_item:
            out.append(f"{where}: item number {slot.item} is past the item table ({n_item})")
        if slot.forge and (slot.forge > FORGE_RECORDS or not block.forges[slot.forge - 1].allocated):
            out.append(f"{where}: forge record {slot.forge} is not allocated")

    for slot, u in block.unit_slots():
        where = f"unit slot {slot}"
        if n_char and u.character > n_char:
            out.append(f"{where}: character number {u.character} is past the table ({n_char})")
        if n_job and not 0 < u.job <= n_job:
            out.append(f"{where}: class number {u.job} is not in the table ({n_job})")
        if u.army > 7:
            out.append(f"{where}: army {u.army} is not 0-7")
        for ref in (u.prev_slot, u.next_slot, u.linked_slot):
            if ref and (ref > UNIT_SLOTS or block.units[ref - 1] is None):
                out.append(f"{where}: links to empty slot {ref}")
        for i, it in enumerate(u.items):
            item_ok(it, f"{where} item {i + 1}")
    for i, it in enumerate(block.convoy):
        item_ok(it, f"convoy slot {i + 1}")
    if block.terrain and block.terrain.count > TERRAIN_ENTRIES:
        out.append(f"terrain table count {block.terrain.count} > {TERRAIN_ENTRIES}")
    return out


# -- command line ---------------------------------------------------------------------------

def _jsonable(obj):
    if isinstance(obj, bytes):
        return obj.hex()
    if isinstance(obj, list):
        return [_jsonable(x) for x in obj]
    if obj is None or isinstance(obj, (int, str, bool)):
        return obj
    return {f.name: _jsonable(getattr(obj, f.name)) for f in fields(obj) if f.name not in ("raw",)}


def main(argv: Optional[list] = None) -> int:
    import argparse
    import json
    import sys
    from pathlib import Path

    ap = argparse.ArgumentParser(prog="python -m fe_modding.formats.save_file",
                                 description="List, dump or check a Path of Radiance .gci save.")
    ap.add_argument("gci", type=Path)
    ap.add_argument("--dump", type=int, metavar="N", help="print block N (0-7 location) as JSON")
    ap.add_argument("--roundtrip", action="store_true", help="check every block re-encodes to the same bytes")
    args = ap.parse_args(argv)
    sys.stdout.reconfigure(encoding="utf-8")
    save = SaveFile.from_bytes(args.gci.read_bytes())
    loaded = {id(b) for b in save.loaded_blocks()}
    for b in save.blocks:
        print(f"[{b.location}] 0x{b.offset:05X} {SAVE_KINDS.get(b.header.save_kind, b.header.save_kind):13} "
              f"{block_label(b)}{'  <- loaded' if id(b) in loaded else ''}{'  (' + b.error + ')' if b.error else ''}")
    if args.dump is not None:
        b = next(b for b in save.blocks if b.location == args.dump)
        print(json.dumps(_jsonable(b), indent=1))
    if args.roundtrip:
        bad = [b for b in save.blocks if b.decoded and b.build() != b.raw]
        print("round trip:", "ok" if not bad else f"{len(bad)} block(s) differ")
        return 1 if bad else 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
