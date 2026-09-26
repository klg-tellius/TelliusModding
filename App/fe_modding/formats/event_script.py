"""Disassemble a compiled event script (``Scripts/CNN.cmb`` - one per
chapter, matching ``Mess/cNN.m``). This is the bytecode for the game's
scripting VM that drives cutscenes, chapter setup/conditions, and other
in-chapter events.

This module is the lightweight read-only view the conversation preview
uses. Full editing (adding/removing instructions and functions, the
``.fe9s`` source language) lives in :mod:`fe_modding.formats.cmb`.

Layout: a small header giving where the string pool and function table
start, then one function per entry in that table: an id string (optional),
a param list, and a stream of bytecode (opcode + 0/1/2/4-byte operands,
per OPCODES/OPERAND_LENGTHS below - both reverse-engineered by hand, not
from any disassembly of the game's executable, so treat unfamiliar opcodes
with suspicion).

Unlike the .cmp-wrapped formats, ``Scripts/CNN.cmb`` isn't compressed or
packed - it's the raw bytecode directly under ``extracted/files/``, same as
``FE8Data.bin``, so editing is a direct read-patch-write with no lz10/pak
layer to round-trip.

Write support (``patch_instruction_operand()``) follows the same discipline
as every other patch-in-place format here: it only overwrites an existing
operand's raw bytes, at the same offset, same byte width - never inserting,
removing, or resizing an instruction. That sidesteps the harder of the two
problems a real assembler would have to solve (recomputing every branch
offset and instruction/function-table address after an *instruction* count
changes) at the cost of the same "existing values only" ceiling dispo.py and
fe8data.py already accept: a literal number (push8/push16/push32, a branch's
relative offset, a localCall's function index) can be set to anything that
fits the operand's byte width, but a string/label operand (pushstr*, or
externCall's first operand) can only be repointed at a label that already
exists somewhere in this same script's string pool.

**Growing the string pool is now supported** (``insert_label()``) - unlike
dispo.py's label pool, this one turned out to be the *easy* half of that
problem. A pushstr/externCall operand's stored value is a **pool-relative**
offset (0-based from where the pool starts), not an absolute file address -
confirmed by ``_read_label_map()``'s own offset bookkeeping, which
``_read_instructions()`` looks values up against directly. That means
appending a new string at the pool's *end* never changes any existing
label's relative offset - nothing needs walking and re-patching the way
dispo.py's label-pool shift required. What *does* need adjusting is
everything physically stored **after** the pool: the function address
table (absolute file addresses, one per function) and each function's own
``id_string_ptr``/``address_code`` fields (also absolute addresses) all
shift by the inserted byte count. ``insert_label()`` handles all of that;
growing the pool and pointing an operand at the new label are still two
composable steps - ``insert_label()`` then ``patch_instruction_operand()``
- the same "add, then edit" pattern as dispo.py's "duplicate a unit, then
edit its fields." ``address_parent`` (the third header word) is
deliberately **not** shifted along with the other two - see
``ScriptFunction``'s own docstring for why a disassembly finding refutes
treating it as a real relocatable address.

**A `main.dol` disassembly finding corrects a guess this module had been
carrying since it was first ported**: the game's own script-buffer loader
(`FUN_800140b4`, reached from the file-cache system found while chasing an
unrelated `research/main_dol/` lead - see that function's disassembly for
the full byte-swap/relocation sequence) confirms `id_string_ptr` and
`address_code` really are absolute, relocatable file addresses - each gets
byte-swapped (little-endian on disk, confirmed - matching this module's own
``<I`` reads), then has the script buffer's own base address added to it at
load time, exactly what this module already assumed. The third header word
(this module calls it ``address_parent``) does **not** get this treatment
at all: the loader unconditionally overwrites it with the buffer's own base
pointer, discarding whatever was stored on disk, for every function,
regardless of the file's own byte value there. That refutes - not just
leaves unconfirmed - the assumption (baked into the original field name)
that it's a real "pointer to this function's parent" needing the same
shift-on-insert treatment as the other two. See ``ScriptFunction``'s own
docstring for what's now known and still open.
"""

from __future__ import annotations

import io
import math
import struct
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO, Optional, Union

OPCODES = [
    "nop", "pushvar8", "pushvar16", "pusharray8", "pusharray16", "pusharrayP8", "pusharrayP16",
    "pushaddr8", "pushaddr16", "pushaddrarray8", "pushaddrarray16", "pushaddrarrayP8", "pushaddrarrayP16",
    "globalpushvar8", "globalpushvar16", "globalpusharray8", "globalpusharray16", "globalpusharrayP8",
    "globalpusharrayP16", "globalpushaddr8", "globalpushaddr16", "globalpushaddrarray8",
    "globalpushaddrarray16", "globalpushaddrarrayP8", "globalpushaddrarrayP16", "push8", "push16", "push32",
    "pushstr8", "pushstr16", "pushstr32", "pushvaluefromP", "pop", "store", "add", "sub", "mul", "div", "mod",
    "neg", "bitwisenot", "logicalnot", "or", "and", "xor", "shiftl", "shiftr", "seteq", "setnoteq",
    "setlessthan", "setlesseqthan", "setgreaterthan", "setgreatereqthan", "seteqstr", "setnoteqstr",
    "localCall", "externCall", "return", "branch", "branchnz", "branchkeepz", "branchnz2", "branchkeepnz",
    "yield", "unknown", "printf", "inc", "dec", "dup", "ret0", "ret1", "assign",
]

# Operand byte-lengths per opcode; some opcodes (externCall) take two operands.
OPERAND_LENGTHS = [
    [0], [1], [2], [1], [2], [1], [2], [1], [2], [1], [2], [1], [2], [1], [2], [1], [2], [1], [2], [1], [2], [1],
    [2], [1], [2], [1], [2], [4], [1], [2], [4], [0], [0], [0], [0], [0], [0], [0], [0], [0], [0], [0], [0], [0],
    [0], [0], [0], [0], [0], [0], [0], [0], [0], [0], [0], [1], [2, 1], [0], [2], [2], [2], [2], [2], [0], [4],
    [1], [0], [0], [0], [0], [0], [0],
]

# Opcodes whose operand is a string-pool offset rather than a raw number.
_STRING_OPERAND_OPCODES = {0x1C, 0x1D, 0x1E}
_CALL_OPCODE = 0x38

Operand = Union[int, str]


class ScriptError(Exception):
    pass


@dataclass
class ScriptFunction:
    """``address_parent`` is the raw on-disk value of the function record's
    third header word (offset +8) - kept for round-tripping, but its
    original name is a **refuted** guess, not an uncertain one. A `main.dol`
    disassembly of the game's own script-buffer loader (`FUN_800140b4`)
    shows it unconditionally overwrites this word with the script buffer's
    own base pointer at load time, for every function, regardless of the
    file's stored byte value - unlike `id_string_ptr`/`address_code`
    (confirmed real relocatable addresses: each gets byte-swapped then has
    the buffer base added to it, exactly as this module already assumed).
    So whatever's stored here on disk is never read by the game as an
    address at runtime; its real on-disk meaning, if any, is unconfirmed.
    Real data is consistent with "always reserved, never meaningful" rather
    than "meaningful but not yet decoded": checked across every function in
    every real chapter script (43 files, 2100 functions), this word is
    **exactly 0 with zero exceptions** - not just usually small or usually
    zero. `insert_label()` deliberately leaves this field's raw bytes
    untouched rather than shifting it like the other two - see that
    function's module-docstring paragraph."""

    index: int
    id_string: bytes
    address_parent: int
    type: int
    num_args: int
    num_vars: int
    params: list[int]
    instructions: list[list]  # [offset, opcode_name, *operands] - offset is relative to address_code
    address_code: int = 0  # absolute file offset of this function's first instruction - needed to patch operands
    address: int = 0  # absolute file offset of this function's own record - needed to patch trigger params


@dataclass(frozen=True)
class FunctionTrigger:
    description: str
    param_labels: list  # what each of the function's `params` values means, in order - may be shorter than params
    note: Optional[str] = None
    label_param_indices: frozenset = frozenset()  # which param_labels positions are string-pool label references rather than raw numbers - see describe_function_trigger()


# What each ScriptFunction.type value actually triggers on, and what its
# `params` mean. The trigger *descriptions* are not reverse-engineered by
# this codebase - they're the user's own prior research
# (C:\Users\Julien\Documents\FE9\fct.xlsx, "New type" sheet), carried over
# the same way dispo.py/map_file.py originally carried over findings from
# that same external FE9 folder's one-off scripts. Treat an
# unfamiliar/unexpected type value with the same suspicion the module's
# top-level docstring already asks for with unfamiliar opcodes.
#
# **Every real script's own function-type census was checked** (a
# follow-up pass, continuing the reverse-engineering roadmap into
# event_script.py itself): all 43 real Path of Radiance scripts, every
# function's `type` value, cross-referenced against FUNCTION_TRIGGERS -
# no undocumented type value was found (every real type value falls inside
# 0-15). What WAS found: several types carry more `params` than
# fct.xlsx's own param_labels account for, or a param fct.xlsx marked "?"
# turns out to resolve cleanly against this script's own label pool - the
# same resolution mechanism `_read_instructions()` already applies to
# pushstr*/externCall operands, just never previously applied to function
# params. Confirmed by checking every real occurrence in all 43 scripts,
# filtering out the two ways a naive "does this value match a label pool
# offset" check gives a false positive (a param that's genuinely 0 always
# "resolves" to whatever the pool's first entry happens to be; an offset
# landing on a run of consecutive NUL bytes resolves to an empty string) -
# label_param_indices below marks only params that resolve to a
# real, non-empty label at a very high and consistent rate once those two
# false-positive sources are excluded, not merely "sometimes matches
# something":
#
# - Types 1/2's previously-"Param meaning unclear" param: 100% of real
#   occurrences (41/41 and 5/5) resolve to the literal label "gf_complete"
#   / "gf_gameover" - i.e. the flag being watched is itself named by this
#   param, though in every real script it's always the same name.
# - Type 4's 6th param (fct.xlsx only documented 5) and type 5's 4th
#   (fct.xlsx only documented 3): 97% (112/116) and a genuine (not
#   coincidental) subset of type 5's occurrences resolve to a per-trigger
#   descriptive label - either a human-written Japanese name ("マーシャの
#   イベントトリガ", "Marcia's event trigger") or an auto-generated one
#   encoding the trigger's own zone coordinates ("F10041009"). This
#   contradicts type 5's old note ("can carry a variable holding which
#   character performed the action") - real data never shows a PID_ label
#   here, only debug/event-name text, so that note is corrected below
#   rather than left standing.
# - Type 8's 4th param and type 9's 4th param (fct.xlsx only documented the
#   first two of four real params for both): 96%/100% resolve to a
#   descriptive scene-name label naming the conversation or battle itself
#   ("アイクティアマト" Ike-Titania, "ボス戦闘会話" boss battle
#   conversation) - the same "debug name for this specific trigger
#   instance" pattern as types 4/5's extra param, just talk/battle-flavored.
#   Types 8 and 9's first two params, already documented as "Character ID
#   1/2", are now confirmed to specifically be PID_ label-pool references
#   (not raw numeric character-table indices).
# - Type 11's "Character ID" param: confirmed the same way (100%, 342/342)
#   to be a PID_ label reference.
# - Type 14's two "?" params are now both resolved: the first is a named
#   "info flag" reference (labels like "情報２フラグ", "info flag 2"); the
#   second resolves to an MPID_-prefixed label (MPID_MERCHANT, MPID_BOLE,
#   ...) - a distinct character-ID label family from the PID_ used
#   elsewhere, seen nowhere else in this codebase but independently named
#   in a public FE9 community tool's own source (MPID.java in
#   github.com/jespoketheepic/FE9-Character-Editor-and-Randomizer) as a
#   real, separate ID type - consistent with this being a base-conversation-
#   specific character reference.
#
# Types 3 and 6 (the turn/phase triggers) were checked the same way and
# show NO genuine resolution once the false positives are excluded - their
# "Turn number" params really are raw numbers, not label references, so
# they're unchanged here.
FUNCTION_TRIGGERS = {
    0: FunctionTrigger(
        "Callable - not auto-triggered by the engine; invoked by localCall (function index) or by id string",
        [],
        "Startup and Opening0 are exceptions: the engine calls them automatically by id string despite type 0",
    ),
    1: FunctionTrigger(
        "Triggered when gfComplete is set (map goal achieved)",
        ["Flag name"],
        "Always resolves to \"gf_complete\" in every real script sampled - fixed in practice, though the field itself is a general named-flag reference",
        label_param_indices=frozenset({0}),
    ),
    2: FunctionTrigger(
        "Triggered when gf_gameover is set (map goal failed)",
        ["Flag name"],
        "Always resolves to \"gf_gameover\" in every real script sampled",
        label_param_indices=frozenset({0}),
    ),
    3: FunctionTrigger(
        "Triggered before the start of a phase (before \"xxx Phase\" appears on screen)",
        ["Turn number", "Turn number", "Phase (0=player, 1=enemy, 3=partner)"],
        "If turn=0, checked every turn",
    ),
    4: FunctionTrigger(
        "Triggered when a unit moves into a specific zone",
        [
            "Zone left X", "Zone top Y", "Zone right X", "Zone bottom Y",
            "0=playable character triggers it, 1=enemy triggers it",
            "Event name (debug label for this trigger instance, not gameplay-visible)",
        ],
        None,
        label_param_indices=frozenset({5}),
    ),
    5: FunctionTrigger(
        "Triggered when a unit takes an action at a map location",
        [
            "Location X",
            "Location Y",
            "Action (9=visit, 11=open door, 12=open chest, 13=seize, 14=escape, 37=destroy house, 41=arrive, 44=other)",
            "Event name (debug label for this trigger instance, not gameplay-visible)",
        ],
        "The old note that this can carry a variable naming which character performed the action doesn't match real data - the 4th param consistently resolves to a debug/event-name label instead (e.g. \"F2917\", \"訪問１\" \"Visit 1\")",
        label_param_indices=frozenset({3}),
    ),
    6: FunctionTrigger(
        "Triggered at the start of a phase (after \"xxx Phase\" appears)",
        ["Turn number", "Turn number", "Phase (0=player, 1=enemy)"],
        "If turn=0, checked every turn",
    ),
    7: FunctionTrigger("Checked after every action", [], None),
    8: FunctionTrigger(
        "Triggered when two units talk together",
        [
            "Character ID 1", "Character ID 2",
            "0/1 flag, meaning unclear",
            "Event name (debug label for this conversation trigger, not gameplay-visible)",
        ],
        "Unclear whether it also fires with the two characters reversed",
        label_param_indices=frozenset({0, 1, 3}),
    ),
    9: FunctionTrigger(
        "Triggered when a fight starts between two units",
        [
            "Character ID 1", "Character ID 2",
            "0/1 flag, meaning unclear (almost never a label - stays a raw number)",
            "Event name (debug label for this battle trigger, not gameplay-visible)",
        ],
        "Character ID 2 is sometimes unset (resolves to nothing) - plausibly a \"vs. any character\" case",
        label_param_indices=frozenset({0, 1, 3}),
    ),
    10: FunctionTrigger(
        "Triggered when a unit dies, once back on the battle map (handles a character having more than one death message)",
        ["Character ID"],
        None,
    ),
    11: FunctionTrigger(
        "Triggered when a unit dies in battle",
        ["Character ID"],
        None,
        label_param_indices=frozenset({0}),
    ),
    12: FunctionTrigger("Triggered after the scenario is complete", [], None),
    13: FunctionTrigger(
        "Triggered by a support conversation (handles more than one possible text depending on situation)",
        ["Character ID 1", "Character ID 2", "Support level"],
        None,
    ),
    14: FunctionTrigger(
        "Triggered by a base conversation",
        ["Info flag name", "Character (MPID_ label)", "Number of stars"],
        None,
        label_param_indices=frozenset({0, 1}),
    ),
    15: FunctionTrigger("Triggered when selecting a unit", [], None),
}

# Named entry points the engine calls automatically by id string, regardless
# of `type` - same source as FUNCTION_TRIGGERS above.
SPECIAL_FUNCTION_TRIGGERS = {
    "Startup": "Called automatically at the beginning of the chapter",
    "Opening0": "Called automatically right after Startup",
    "Opening2": "Called automatically after ending preparation",
}


def describe_function_trigger(fn: ScriptFunction, labels: Optional[dict] = None) -> str:
    """Human-readable description of when/how a function gets called,
    combining the id-string special cases with the type-based lookup table
    above. Falls back to a plain 'type N (undocumented)' for any type not
    covered by FUNCTION_TRIGGERS.

    `labels` is a script's own label map (EventScript.labels) - optional
    and backward-compatible (omitting it reproduces the old raw-number-only
    output exactly), but when given, any param at one of
    FunctionTrigger.label_param_indices gets resolved against it and shown
    as text instead of a raw offset - see FUNCTION_TRIGGERS' module-level
    comment for which params those are and how they were confirmed."""
    id_text = fn.id_string.decode("ascii", errors="replace") if fn.id_string else ""
    special = SPECIAL_FUNCTION_TRIGGERS.get(id_text)
    trigger = FUNCTION_TRIGGERS.get(fn.type)

    if trigger is None:
        base = f"type {fn.type} (undocumented)"
    else:
        base = trigger.description
        if trigger.param_labels and fn.params:
            parts = []
            for i, (label, value) in enumerate(zip(trigger.param_labels, fn.params)):
                if labels is not None and i in trigger.label_param_indices:
                    value = labels.get(value, value)
                parts.append(f"{label}={value}")
            base += " [" + ", ".join(parts) + "]"
        if trigger.note:
            base += f" ({trigger.note})"

    return f"{special} - {base}" if special else base


@dataclass
class EventScript:
    functions: list[ScriptFunction]
    labels: dict  # string-pool offset -> decoded label text, shared across every function in the script


def _read_label_map(stream: BinaryIO, label_map_start: int, function_table_start: int) -> dict:
    stream.seek(label_map_start)
    label_map_bytes = stream.read(function_table_start - label_map_start)
    labels = {}
    offset = 0
    for label in label_map_bytes.split(b"\x00"):
        labels[offset] = label.decode("shift-jis")
        offset += len(label) + 1
    return labels


def read_script(stream: BinaryIO, size: int) -> list[ScriptFunction]:
    return read_event_script(stream, size).functions


def read_event_script(stream: BinaryIO, size: int) -> EventScript:
    header = stream.read(0x2C)
    label_map_start, function_table_start = struct.unpack("<II", header[0x24:])

    labels = _read_label_map(stream, label_map_start, function_table_start)

    stream.seek(function_table_start)
    (first_function_start,) = struct.unpack("<I", stream.read(4))
    num_functions = math.floor(((first_function_start - function_table_start) - 4) / 4)

    function_addresses = [first_function_start]
    for _ in range(1, num_functions):
        (addr,) = struct.unpack("<I", stream.read(4))
        function_addresses.append(addr)

    functions = []
    for i, address in enumerate(function_addresses):
        end_address = function_addresses[i + 1] if i != len(function_addresses) - 1 else size
        functions.append(_read_function(stream, address, end_address, labels))
    return EventScript(functions=functions, labels=labels)


def read_event_script_bytes(data: bytes) -> EventScript:
    return read_event_script(io.BytesIO(data), len(data))


def read_script_path(path: Path | str) -> list[ScriptFunction]:
    return read_event_script_path(path).functions


def read_event_script_path(path: Path | str) -> EventScript:
    path = Path(path)
    with open(path, "rb") as stream:
        return read_event_script(stream, path.stat().st_size)


def _read_function(stream: BinaryIO, address: int, end_address: int, labels: dict[int, str]) -> ScriptFunction:
    stream.seek(address)
    id_string_ptr, address_code, address_parent, fn_type, num_args, num_params, _pad, index, num_vars = struct.unpack(
        "<IIIbbbbhh", stream.read(20)
    )

    params = [struct.unpack("<H", stream.read(2))[0] for _ in range(num_params)]

    id_string = b""
    if id_string_ptr != 0:
        stream.seek(id_string_ptr)
        max_len = address_code - id_string_ptr
        id_string = stream.read(max_len).split(b"\x00")[0]

    instructions = _read_instructions(stream, address_code, end_address, labels)

    return ScriptFunction(
        index=index,
        id_string=id_string,
        address_parent=address_parent,
        type=fn_type,
        num_args=num_args,
        num_vars=num_vars,
        params=params,
        instructions=instructions,
        address_code=address_code,
        address=address,
    )


def _read_instructions(stream: BinaryIO, address_code: int, end_address: int, labels: dict[int, str]) -> list[list]:
    stream.seek(address_code)
    instructions = []
    last_opcode = 0x00
    remaining = end_address - address_code
    offset = 0

    while remaining > 0:
        opcode = stream.read(1)[0]
        remaining -= 1
        offset += 1
        if remaining < 4 and last_opcode == 0x39 and opcode == 0:
            break  # trailing padding after a final return
        last_opcode = opcode

        if opcode >= len(OPCODES):
            continue

        instruction: list = [offset - 1, OPCODES[opcode]]
        for operand_length in OPERAND_LENGTHS[opcode]:
            if operand_length == 0:
                break
            if operand_length == 1 and remaining >= 1:
                value = stream.read(1)[0]
                remaining -= 1
                offset += 1
            elif operand_length == 2 and remaining >= 2:
                (value,) = struct.unpack(">h", stream.read(2))
                remaining -= 2
                offset += 2
            elif operand_length == 4 and remaining >= 4:
                (value,) = struct.unpack(">i", stream.read(4))
                remaining -= 4
                offset += 4  # display offset only, doesn't affect where the next opcode is read from
            else:
                continue

            if opcode in _STRING_OPERAND_OPCODES or (opcode == _CALL_OPCODE and operand_length == 2):
                instruction.append(labels.get(value, value))
            else:
                instruction.append(value)

        instructions.append(instruction)

    return instructions


def format_instruction(instruction: list) -> str:
    offset, opcode, *operands = instruction
    operand_str = ", ".join(str(op) for op in operands)
    return f"{offset:6d}  {opcode}({operand_str})" if operands else f"{offset:6d}  {opcode}"


def to_text(functions: list[ScriptFunction]) -> str:
    lines = []
    for fn in functions:
        lines.append("#" * 53)
        lines.append(f"Function id: {fn.index}")
        lines.append(f"id string: {fn.id_string}")
        lines.append(f"Header word @+8 (raw, not a real address - see ScriptFunction docstring): {fn.address_parent}")
        lines.append(f"Type: {fn.type}")
        lines.append(f"Nb args: {fn.num_args}")
        lines.append(f"Nb var: {fn.num_vars}")
        lines.append(f"Params: {fn.params}")
        for instruction in fn.instructions:
            lines.append(format_instruction(instruction))
        lines.append("")
        lines.append("")
    return "\n".join(lines)


def operand_is_label(opcode_name: str, operand_index: int) -> bool:
    """Whether a given operand of a given opcode is a string-pool label
    (pushstr*, or externCall's first operand) rather than a raw number -
    same condition _read_instructions() uses to decide whether to resolve a
    value against the label pool."""
    opcode = OPCODES.index(opcode_name)
    operand_length = OPERAND_LENGTHS[opcode][operand_index]
    return opcode in _STRING_OPERAND_OPCODES or (opcode == _CALL_OPCODE and operand_length == 2)


def find_label_offset(labels: dict, text: str) -> int | None:
    """Reverse lookup: the string-pool offset for a label's text, if that
    exact label appears anywhere in this script (needed to repoint a label
    operand at an existing string - see patch_instruction_operand())."""
    for offset, label in labels.items():
        if label == text:
            return offset
    return None


def patch_instruction_operand(
    data: bytes, labels: dict, function: ScriptFunction, instruction: list, operand_index: int, new_value
) -> bytes:
    """Return a copy of data with one operand of one instruction overwritten
    in place - same byte offset, same byte width, nothing else in the file
    shifts. `new_value` is an int for a numeric operand, or a label string
    (which must already exist in `labels`) for a label operand - see
    operand_is_label(). Every other opcode/instruction/function in the file
    is untouched."""
    offset_in_fn, opcode_name = instruction[0], instruction[1]
    opcode = OPCODES.index(opcode_name)
    operand_lengths = OPERAND_LENGTHS[opcode]
    if operand_index >= len(operand_lengths) or operand_lengths[operand_index] == 0:
        raise ScriptError(f"{opcode_name} has no operand at index {operand_index}.")

    length = operand_lengths[operand_index]
    pos = function.address_code + offset_in_fn + 1 + sum(operand_lengths[:operand_index])

    if operand_is_label(opcode_name, operand_index):
        raw = find_label_offset(labels, new_value) if isinstance(new_value, str) else int(new_value)
        if raw is None:
            raise ScriptError(f"Label {new_value!r} not found anywhere in this script's string pool.")
    else:
        raw = int(new_value)

    out = bytearray(data)
    if length == 1:
        if not (0 <= raw <= 0xFF):
            raise ScriptError(f"{raw} doesn't fit in this operand (8-bit unsigned).")
        out[pos] = raw
    elif length == 2:
        struct.pack_into(">h", out, pos, raw)
    elif length == 4:
        struct.pack_into(">i", out, pos, raw)
    return bytes(out)


def patch_function_param(data: bytes, function: ScriptFunction, param_index: int, new_value: int) -> bytes:
    """Return a copy of data with one entry of a function's `params` list
    overwritten in place - same patch-in-place discipline as
    patch_instruction_operand(). These are the values that control *when* a
    function triggers (see FUNCTION_TRIGGERS/describe_function_trigger()
    above for what each one means for a given `type`) - e.g. the turn
    number and phase a `type=6` function waits for, or the map coordinates
    a `type=4`/`type=5` function watches. Each param is a 2-byte unsigned
    value; the count itself (num_params) isn't editable here, since growing
    or shrinking the params list would shift the function's own code start
    (address_code) and everything after it in the file."""
    if not (0 <= param_index < len(function.params)):
        raise ScriptError(f"Function has {len(function.params)} params; no param at index {param_index}.")
    value = int(new_value)
    if not (0 <= value <= 0xFFFF):
        raise ScriptError(f"{value} doesn't fit in a trigger param (16-bit unsigned).")
    out = bytearray(data)
    struct.pack_into("<H", out, function.address + 20 + 2 * param_index, value)
    return bytes(out)


def insert_label(data: bytes, script: EventScript, new_label: str) -> bytes:
    """Return a copy of data with `new_label` appended to the string pool.

    Unlike patch_instruction_operand()/patch_function_param(), this is a
    structural insert - see the module docstring for why it's simpler than
    dispo.py's equivalent: pool-relative offsets mean every existing label
    stays valid untouched, and only absolute-address fields *after* the
    pool (the function table, and each function's id_string_ptr/
    address_code) need shifting by the inserted byte count. address_parent
    is deliberately left unshifted - see the module docstring's
    disassembly-finding paragraph and ScriptFunction's own docstring.

    `script` must be the *current* parse of `data` (from
    read_event_script_bytes()/read_event_script()) - it's used to find
    every function's original address so its shifted fields can be located.
    Does not itself point any operand at the new label - call
    find_label_offset()/patch_instruction_operand() afterward, after
    re-parsing the returned bytes (every function's address changed).

    Real files' pools don't reliably end with a NUL byte - the *last*
    label is sometimes implicitly terminated by simply reaching
    function_table_start rather than by a stored 0x00 (confirmed against a
    real chapter script: appending straight onto its pool without checking
    this silently merged the new label onto the tail of the existing last
    one instead of creating a separate entry). A leading NUL is inserted
    first whenever the byte right before function_table_start isn't
    already one, so the new label always starts its own token.
    """
    if "\x00" in new_label:
        raise ScriptError("A label can't contain a NUL byte.")

    (label_map_start,) = struct.unpack_from("<I", data, 0x24)
    (function_table_start,) = struct.unpack_from("<I", data, 0x28)
    needs_separator = function_table_start > label_map_start and data[function_table_start - 1] != 0
    new_bytes = (b"\x00" if needs_separator else b"") + new_label.encode("shift-jis") + b"\x00"
    shift = len(new_bytes)

    buf = bytearray(data[:function_table_start]) + bytearray(new_bytes) + bytearray(data[function_table_start:])

    def bump(pos: int) -> None:
        (value,) = struct.unpack_from("<I", buf, pos)
        if value != 0:
            struct.pack_into("<I", buf, pos, value + shift)

    struct.pack_into("<I", buf, 0x28, function_table_start + shift)

    for i, fn in enumerate(script.functions):
        bump(function_table_start + shift + i * 4)  # this function's own function-table entry
        fn_pos = fn.address + shift
        bump(fn_pos + 0)  # id_string_ptr
        bump(fn_pos + 4)  # address_code
        # fn_pos + 8 (address_parent) is deliberately NOT bumped - see ScriptFunction's
        # own docstring for why (main.dol's script loader overwrites this word
        # unconditionally with the script buffer's own base pointer, never reading
        # whatever was stored on disk, so treating it as a real relocatable address
        # was an unconfirmed guess this disassembly finding refutes).

    return bytes(buf)
