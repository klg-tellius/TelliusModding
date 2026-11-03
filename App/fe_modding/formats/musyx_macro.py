"""MusyX sound-macro commands: names and fields of every 8-byte command.

A macro (``.pool`` macro chain, see ``musyx.py``) is a list of 8-byte
commands, two big-endian words. The opcode is the low 7 bits of word 0. The
game's interpreter (``macHandleActive`` 0x80253F6C, jump table 0x8029F430,
114 cases) runs up to 32 commands per call and has exactly the MusyX 2.0
command set: the layouts below follow the public MusyX decompilation
(github.com/AxioDL/musyx, ``synthmacros.c``) and were checked case by case
against the game's jump table.

Byte names used in the field tables: ``b0..b3`` are the bytes of word 0 in
file order (``b3`` holds the opcode), ``c0..c3`` those of word 1. Steps
(``step``) count 8-byte commands from the start of the target macro.

The shipped banks use 21 of the 84 commands: end, goto, wait-ms, set ADSR,
start/stop sample, key off, if-random, random/add/set key, set age counter,
pitch-wheel range, age-counter speed, panning / pitch-wheel / surround
selects, variable add / add immediate / set, and if-equal.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass, field
from typing import Callable

COMMAND_SIZE = 8
OPCODE_MASK = 0x7F


def _s8(v: int) -> int:
    return v - 256 if v > 127 else v


def _s16(v: int) -> int:
    return v - 65536 if v > 32767 else v


# Field extractors: (word0, word1) -> int
def _b(i: int) -> Callable[[int, int], int]:
    return lambda w0, w1: (w0 >> (24 - 8 * i)) & 0xFF


def _c(i: int) -> Callable[[int, int], int]:
    return lambda w0, w1: (w1 >> (24 - 8 * i)) & 0xFF


def _sb(i: int) -> Callable[[int, int], int]:
    return lambda w0, w1: _s8((w0 >> (24 - 8 * i)) & 0xFF)


def _sc(i: int) -> Callable[[int, int], int]:
    return lambda w0, w1: _s8((w1 >> (24 - 8 * i)) & 0xFF)


def _bit(get: Callable[[int, int], int]) -> Callable[[int, int], int]:
    return lambda w0, w1: get(w0, w1) & 1


H0 = lambda w0, w1: w0 >> 16                     # bytes b0-b1
H0S = lambda w0, w1: _s16(w0 >> 16)
MID0 = lambda w0, w1: (w0 >> 8) & 0xFFFF         # bytes b1-b2
H1 = lambda w0, w1: w1 >> 16                     # bytes c0-c1
L1 = lambda w0, w1: w1 & 0xFFFF                  # bytes c2-c3
L1S = lambda w0, w1: _s16(w1 & 0xFFFF)
W1 = lambda w0, w1: w1

_JUMP = (("macro", H0), ("step", L1))
_WAIT = (("key_release", _bit(_b(2))), ("random", _bit(_b(1))), ("sample_end", _bit(_b(0))),
         ("absolute", _bit(_c(3))), ("time", H1))
_TIME = (("time", H1), ("in_ms", _bit(_c(2))))
_VOLUME = (("scale", _b(2)), ("add", _b(1)), ("curve", lambda w0, w1: (w0 >> 24) | (w1 & 0xFF) << 8))
_PAN = (("pan", _b(2)), ("time_ms", H0), ("width", _sc(3)))
# Source selects: route an input into a parameter. The input is MIDI controller
# ``controller`` (128 pitch bend, 160/161 LFO 1/2, 162 note, 163 velocity,
# 164 time since start) or, with ``from_variable``, macro variable ``controller``.
# Up to four sources per parameter: ``combine`` 0 replaces the list, then
# 1 adds, 2 multiplies, 3 subtracts. Scale = scale_percent + scale_fraction / 100 %.
_SELECT = (("controller", _b(2)), ("scale_percent", H0S), ("scale_fraction", _sc(1)),
           ("combine", _c(3)), ("from_variable", _c(2)))
_VARS = (("dest_ctrl", _b(2)), ("dest", _b(1)), ("a_ctrl", _b(0)), ("a", _c(3)),
         ("b_ctrl", _c(2)), ("b", _c(1)))
_COMPARE = (("a_ctrl", _b(2)), ("a", _b(1)), ("b_ctrl", _b(0)), ("b", _c(3)),
            ("invert", _c(2)), ("step", H1))


@dataclass(frozen=True)
class CommandSpec:
    opcode: int
    name: str
    fields: tuple = ()
    description: str = ""


SPECS: dict[int, CommandSpec] = {s.opcode: s for s in (
    CommandSpec(0x00, "end", (), "End the macro and free the voice."),
    CommandSpec(0x01, "stop", (), "Same as end."),
    CommandSpec(0x02, "if_key", (("key", _b(2)),) + _JUMP, "Jump if the current note >= key."),
    CommandSpec(0x03, "if_velocity", (("velocity", _b(2)),) + _JUMP, "Jump if the velocity >= value."),
    CommandSpec(0x04, "wait", _WAIT + (("in_ms", _bit(_c(2))),),
                "Wait time ticks/ms (0xFFFF: forever); key_release / sample_end end the wait early."),
    CommandSpec(0x05, "loop", (("key_release", _bit(_b(2))), ("random", _bit(_b(1))),
                               ("sample_end", _bit(_b(0))), ("times", H1), ("step", L1)),
                "Jump back to step of this macro, times times (0xFFFF: forever)."),
    CommandSpec(0x06, "goto", _JUMP, "Continue at step of macro."),
    CommandSpec(0x07, "wait_ms", _WAIT, "wait with the time in milliseconds."),
    CommandSpec(0x08, "play_macro", (("key_add", _sb(2)), ("macro", H0), ("max_voices", _c(0)),
                                     ("priority", _c(1)), ("step", L1)),
                "Start macro at step on a child voice, note + key_add."),
    CommandSpec(0x09, "send_keyoff", (("key_add", _b(2)), ("macro", H0)),
                "Key off the voices playing macro at the original note + key_add."),
    CommandSpec(0x0A, "if_modulation", (("value", _b(2)),) + _JUMP, "Jump if the mod wheel >= value."),
    CommandSpec(0x0B, "piano_pan", (("scale", _sb(2)), ("center_key", _b(1)), ("center_pan", _b(0))),
                "Pan by distance of the note from center_key."),
    CommandSpec(0x0C, "set_adsr", (("table", MID0), ("dls", _b(0))),
                "Volume envelope from pool curve table (see AdsrTable)."),
    CommandSpec(0x0D, "scale_volume", _VOLUME + (("from_original", _c(2)),),
                "volume = volume * scale / 127 + add, through volume curve."),
    CommandSpec(0x0E, "set_panning", _PAN, "Pan (0 left, 64 centre, 127 right), moving by width over time_ms."),
    CommandSpec(0x0F, "envelope", _VOLUME + _TIME, "Ramp the volume to a scaled target over time."),
    CommandSpec(0x10, "start_sample", (("sample", MID0), ("offset_mode", _b(0)), ("offset", W1)),
                "Start sample at offset (mode 1/2: scaled by inverse/velocity)."),
    CommandSpec(0x11, "stop_sample", (), "Stop the voice's sample at once."),
    CommandSpec(0x12, "key_off", (), "Key off: start the ADSR release."),
    CommandSpec(0x13, "if_random", (("threshold", _b(2)),) + _JUMP,
                "Jump unless a random byte < threshold (jump chance (256 - threshold) / 256)."),
    CommandSpec(0x14, "fade_in", _VOLUME + _TIME, "Ramp the volume from 0 to a scaled target over time."),
    CommandSpec(0x15, "set_surround_panning", _PAN, "Front/back pan."),
    CommandSpec(0x16, "adsr_from_ctrl", (("attack_ctrl", _b(2)), ("decay_ctrl", _b(1)),
                                         ("sustain_ctrl", _b(0)), ("release_ctrl", _c(3))),
                "DLS envelope from four MIDI controllers."),
    CommandSpec(0x17, "random_key", (("low", _b(2)), ("high", _b(0)), ("detune", _sb(1)),
                                     ("relative", _c(2)), ("random_detune", _c(3))),
                "Set the note to a random one in [low, high] (relative: around the note)."),
    CommandSpec(0x18, "add_key", (("add", _sb(2)), ("detune", _sb(1)), ("from_original", _b(0))) + _TIME,
                "note += add (from_original: original note + add), then wait."),
    CommandSpec(0x19, "set_key", (("key", lambda w0, w1: (w0 >> 8) & 0x7F), ("detune", _sb(1))) + _TIME,
                "Set the note, then wait."),
    CommandSpec(0x1A, "last_key", (("add", _sb(2)), ("detune", _sb(1))) + _TIME,
                "Note = channel's last note + add, then wait."),
    CommandSpec(0x1B, "portamento", (("mode", _b(2)), ("type", _b(1))) + _TIME, "Portamento on/off and glide time."),
    CommandSpec(0x1C, "vibrato", (("key_range", _sb(2)), ("cent_range", _sb(1)), ("mod_wheel", _b(0))) + _TIME,
                "Vibrato depth and period."),
    CommandSpec(0x1D, "pitch_sweep1", (("times", _b(2)), ("delta_hz", H0S)) + _TIME,
                "Add delta_hz to the pitch times times, one step per time."),
    CommandSpec(0x1E, "pitch_sweep2", (("times", _b(2)), ("delta_hz", H0S)) + _TIME, "Second pitch sweep."),
    CommandSpec(0x1F, "set_pitch", (("hz", lambda w0, w1: w0 >> 8), ("fraction", _c(3))),
                "Play the sample at a fixed frequency."),
    CommandSpec(0x20, "pitch_adsr", (("table", MID0), ("key_range", _sc(3)), ("cent_range", _sc(2))),
                "Pitch envelope from a DLS curve table."),
    CommandSpec(0x21, "scale_volume_dls", (("scale", MID0), ("from_original", _b(0))), "DLS-scale volume."),
    CommandSpec(0x22, "mod2vibrato", (("key_range", _sb(2)), ("cent_range", _sb(1))), "Mod wheel to vibrato depth."),
    CommandSpec(0x23, "setup_tremolo", (("scale", MID0), ("mod_add_scale", L1)), "Tremolo depth."),
    CommandSpec(0x24, "return", (), "Return from gosub."),
    CommandSpec(0x25, "gosub", _JUMP, "Call step of macro (4-deep stack)."),
    CommandSpec(0x28, "trap_event", (("event", _b(2)),) + _JUMP,
                "On event (0 key off, 1 sample end, 2 message) jump to macro/step."),
    CommandSpec(0x29, "untrap_event", (("event", _b(2)),), "Clear an event trap."),
    CommandSpec(0x2A, "send_message", (("by_var", _b(2)), ("macro", H0), ("value_var", _c(2)),
                                       ("target_var", _c(3))), "Post a message to voices of macro."),
    CommandSpec(0x2B, "get_message", (("var", _b(2)),), "Pop a message into var."),
    CommandSpec(0x2C, "get_vid", (("var", _b(2)), ("last_started", _b(1))), "Store a voice id into var."),
    CommandSpec(0x30, "add_age_counter", (("step", H0S),), "Add to the voice age (stealing order)."),
    CommandSpec(0x31, "set_age_counter", (("age", H0),), "Set the voice age (stealing order)."),
    CommandSpec(0x32, "send_flag", (("global", _b(2)), ("value", _b(1))), "Set a global variable."),
    CommandSpec(0x33, "pitch_wheel_range", (("up", _b(2)), ("down", _b(1))), "Pitch-bend range in semitones."),
    CommandSpec(0x34, "scale_reverb", (("scale", _b(2)), ("add", _b(1))), "Reverb send scale and offset."),
    CommandSpec(0x35, "pitchbend_after_keyoff", (), "Keep following the pitch wheel after key off."),
    CommandSpec(0x36, "set_priority", (("priority", _b(2)),), "Voice priority."),
    CommandSpec(0x37, "add_priority", (("add", H0S),), "Add to the voice priority (0-255)."),
    CommandSpec(0x38, "age_counter_speed", (("time", W1),), "Age the voice to 0 over time."),
    CommandSpec(0x39, "age_counter_by_volume", (("base", H0), ("scale", L1)), "Age from velocity."),
    CommandSpec(0x40, "volume_select", _SELECT, "Route a controller into volume."),
    CommandSpec(0x41, "panning_select", _SELECT, "Route a controller into panning."),
    CommandSpec(0x42, "pitch_wheel_select", _SELECT, "Route a controller into the pitch wheel."),
    CommandSpec(0x43, "mod_wheel_select", _SELECT, "Route a controller into the mod wheel."),
    CommandSpec(0x44, "pedal_select", _SELECT, "Route a controller into the sustain pedal."),
    CommandSpec(0x45, "portamento_select", _SELECT, "Route a controller into portamento."),
    CommandSpec(0x46, "reverb_select", _SELECT, "Route a controller into the reverb send."),
    CommandSpec(0x47, "surround_panning_select", _SELECT, "Route a controller into surround panning."),
    CommandSpec(0x48, "doppler_select", _SELECT, "Route a controller into doppler."),
    CommandSpec(0x49, "tremolo_select", _SELECT, "Route a controller into tremolo."),
    CommandSpec(0x4A, "pre_aux_a_select", _SELECT, "Route a controller into the pre-fader aux A send."),
    CommandSpec(0x4B, "pre_aux_b_select", _SELECT, "Route a controller into the pre-fader aux B send."),
    CommandSpec(0x4C, "post_aux_b_select", _SELECT, "Route a controller into the post-fader aux B send."),
    CommandSpec(0x4D, "aux_a_fx_select", _SELECT, "Route a controller into aux A effect parameters."),
    CommandSpec(0x4E, "aux_b_fx_select", _SELECT, "Route a controller into aux B effect parameters."),
    CommandSpec(0x50, "setup_lfo", (("lfo", _b(2)), ("period_ms", H0), ("phase_ms", L1)), "LFO period and phase."),
    CommandSpec(0x58, "mode_select", (("dls_volume", _b(2)), ("no_surround", _b(1))), "Volume table / ITD mode."),
    CommandSpec(0x59, "key_group", (("group", _b(2)), ("kill", _b(1))),
                "Key off (kill: stop) other voices of the group, then join it."),
    CommandSpec(0x5A, "src_mode", (("src_type", _b(2)), ("polyphase", _b(1))), "Sample-rate conversion type."),
    CommandSpec(0x5E, "filter_switch_select", _SELECT, "Route a controller into the filter switch."),
    CommandSpec(0x5F, "filter_parameter_select", _SELECT, "Route a controller into the filter parameter."),
    CommandSpec(0x60, "add_vars", _VARS, "dest = a + b (variables, clamped to s16)."),
    CommandSpec(0x61, "sub_vars", _VARS, "dest = a - b."),
    CommandSpec(0x62, "mul_vars", _VARS, "dest = a * b."),
    CommandSpec(0x63, "div_vars", _VARS, "dest = a / b (0 when b is 0)."),
    CommandSpec(0x64, "add_immediate", (("dest_ctrl", _b(2)), ("dest", _b(1)), ("a_ctrl", _b(0)), ("a", _c(3)),
                                        ("value", lambda w0, w1: _s16((w1 >> 8) & 0xFFFF))),
                "dest = a + value."),
    CommandSpec(0x65, "set_var", (("ctrl", _b(2)), ("var", _b(1)), ("value", L1S)), "var = value."),
    CommandSpec(0x70, "if_equal", _COMPARE, "Jump to step of this macro if a == b (invert: !=)."),
    CommandSpec(0x71, "if_less", _COMPARE, "Jump to step of this macro if a < b (invert: >=)."),
)}
"""Every opcode the game's interpreter handles. Other values of the low 7 bits
are ignored (the interpreter moves on to the next command)."""

#: Variables: with ``ctrl`` 0, index 0-15 is the voice's local variable and
#: 16-31 a global one; a nonzero ``ctrl`` reads/writes MIDI controller ``index``.
LOCAL_VARIABLES = 16


@dataclass
class Command:
    opcode: int
    word0: int
    word1: int
    name: str
    fields: dict[str, int] = field(default_factory=dict)

    @property
    def known(self) -> bool:
        return self.opcode in SPECS

    def __str__(self) -> str:
        args = ", ".join(f"{k}={v}" for k, v in self.fields.items())
        return f"{self.name}({args})"


def decode(word0: int, word1: int) -> Command:
    opcode = word0 & OPCODE_MASK
    spec = SPECS.get(opcode)
    if spec is None:
        return Command(opcode, word0, word1, f"op_{opcode:02x}")
    return Command(opcode, word0, word1, spec.name, {name: get(word0, word1) for name, get in spec.fields})


def disassemble(commands: list[tuple[int, int]]) -> list[Command]:
    return [decode(w0, w1) for w0, w1 in commands]


def read_commands(data: bytes, offset: int, size: int) -> list[tuple[int, int]]:
    """The (word0, word1) pairs of one pool macro entry (``size`` includes its 8-byte header)."""
    return [struct.unpack_from(">II", data, i) for i in range(offset + 8, offset + size - 7, COMMAND_SIZE)]


@dataclass(frozen=True)
class AdsrTable:
    """A pool curve-table entry used by ``set_adsr`` (opcode 0x0C, dls 0).

    Stored **little-endian** (the engine byte-swaps it): attack and decay
    times in ms, sustain level where 0x1000 is full volume (the engine scales
    it by 8, clamped to 0x7FFF), release time in ms. Attack ramps linearly
    0 -> full, decay linearly full -> sustain, release linearly to 0 from
    the level at key off. A sustain of 0 ends the voice after the decay."""
    table_id: int
    attack_ms: int
    decay_ms: int
    sustain: int
    release_ms: int

    @property
    def sustain_level(self) -> float:
        return min(self.sustain * 8, 0x7FFF) / 0x7FFF


def parse_curve_tables(pool: bytes) -> dict[int, bytes]:
    """Pool table 1 (curves): a chain of ``u32 size, u16 id, u16 0`` + data,
    ended by ``0xFFFFFFFF``. Returns id -> data."""
    out: dict[int, bytes] = {}
    pos = struct.unpack_from(">I", pool, 4)[0]
    while pos and pos + 8 <= len(pool):
        size, table_id = struct.unpack_from(">IH", pool, pos)
        if size == 0xFFFFFFFF or size < 8:
            break
        out.setdefault(table_id, pool[pos + 8:pos + size])
        pos += size
    return out


def adsr_table(table_id: int, data: bytes) -> AdsrTable | None:
    if len(data) < 8:
        return None
    return AdsrTable(table_id, *struct.unpack_from("<4H", data, 0))


def parse_id_list(data: bytes, offset: int) -> list[int]:
    """A ``.proj`` group's id list (macros, samples, curves, keymaps or
    layers): big-endian u16 ids ended by ``0xFFFF``; an id with bit 15 set
    starts a range ``id & 0x3FFF`` .. next u16 (inclusive)."""
    ids: list[int] = []
    pos = offset
    while pos + 2 <= len(data):
        value = struct.unpack_from(">H", data, pos)[0]
        if value == 0xFFFF:
            break
        if value & 0x8000:
            end = struct.unpack_from(">H", data, pos + 2)[0]
            ids.extend(range(value & 0x3FFF, end + 1))
            pos += 4
        else:
            ids.append(value)
            pos += 2
    return ids


def id_list_size(data: bytes, offset: int) -> int:
    """Bytes the id list at ``offset`` takes, terminator included."""
    pos = offset
    while pos + 2 <= len(data):
        value = struct.unpack_from(">H", data, pos)[0]
        if value == 0xFFFF:
            return pos + 2 - offset
        pos += 4 if value & 0x8000 else 2
    return pos - offset
