"""In-memory model of a compiled event script (``Scripts/CNN.cmb``).

Unlike ``event_script.py``'s read-only view (absolute offsets everywhere),
this model is *symbolic*: branches point at :class:`Label` objects, string
operands carry their text, and nothing stores a file address. That is what
lets :mod:`.binary` lay a whole file out again after instructions, strings or
functions are added or removed.

Opcode semantics below are from the game's own interpreter
(``script_interpreter_main_loop`` @ ``0x80011EDC``), not guesswork:

* Every operand is **signed** big-endian (the VM casts the high byte through
  ``char``) - so ``push8`` covers -128..127 and ``pushstr8`` only reaches the
  first 128 bytes of the string pool.
* ``frame[i]`` is the current call frame: the function's ``num_args``
  arguments are ``frame[0..num_args-1]``, its other locals follow up to
  ``num_vars`` (the VM zeroes them on entry).
* ``global*`` opcodes index the engine-wide script global table.
* Every call (``localCall``/``externCall``) leaves exactly one return value
  on the stack, and ``return`` pops exactly one value.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional, Union

OPCODES = [
    "nop", "pushvar8", "pushvar16", "pusharray8", "pusharray16", "pusharrayP8", "pusharrayP16",
    "pushaddr8", "pushaddr16", "pushaddrarray8", "pushaddrarray16", "pushaddrarrayP8", "pushaddrarrayP16",
    "globalpushvar8", "globalpushvar16", "globalpusharray8", "globalpusharray16", "globalpusharrayP8",
    "globalpusharrayP16", "globalpushaddr8", "globalpushaddr16", "globalpushaddrarray8",
    "globalpushaddrarray16", "globalpushaddrarrayP8", "globalpushaddrarrayP16", "push8", "push16", "push32",
    "pushstr8", "pushstr16", "pushstr32", "deref", "pop", "store", "add", "sub", "mul", "div", "mod",
    "neg", "bitnot", "not", "or", "and", "xor", "shl", "shr", "eq", "ne",
    "lt", "le", "gt", "ge", "streq", "strne",
    "localCall", "externCall", "return", "branch", "branchnz", "branchkeepz", "branchz", "branchkeepnz",
    "yield", "nop4", "printf", "inc", "dec", "dup", "ret0", "ret1", "assign",
]
OPCODE_BY_NAME = {name: i for i, name in enumerate(OPCODES)}

# Operand byte widths per opcode (externCall takes a 2-byte name + 1-byte argc).
OPERAND_WIDTHS: list[tuple[int, ...]] = (
    [(), (1,), (2,)] + [(1,), (2,)] * 11  # 0x01-0x18 variable-addressing family
    + [(1,), (2,), (4,)]  # push8/16/32
    + [(1,), (2,), (4,)]  # pushstr8/16/32
    + [()] * 24  # 0x1F-0x36 stack/arith/compare
    + [(1,), (2, 1), (), (2,), (2,), (2,), (2,), (2,), (), (4,), (1,)]  # 0x37-0x41
    + [()] * 6  # 0x42-0x47 (FE10 only)
)
assert len(OPERAND_WIDTHS) == len(OPCODES)

PUSH_OPS = (0x19, 0x1A, 0x1B)
PUSHSTR_OPS = (0x1C, 0x1D, 0x1E)
BRANCH_OPS = frozenset(range(0x3A, 0x3F))
LOCAL_CALL = 0x37
EXTERN_CALL = 0x38
RETURN = 0x39

# The 0x01-0x18 family: (base name, is_global) per 8/16-bit pair.
VAR_MODES = ("pushvar", "pusharray", "pusharrayP", "pushaddr", "pushaddrarray", "pushaddrarrayP")


def var_op(mode: str, is_global: bool, wide: bool) -> int:
    return 0x01 + (6 if is_global else 0) * 2 + VAR_MODES.index(mode) * 2 + (1 if wide else 0)


def var_op_info(op: int) -> Optional[tuple[str, bool, bool]]:
    """(mode, is_global, wide) for an opcode in the 0x01-0x18 family."""
    if not 0x01 <= op <= 0x18:
        return None
    i = op - 0x01
    return VAR_MODES[(i // 2) % 6], i >= 12, bool(i % 2)


def fits_signed(value: int, width: int) -> bool:
    bits = width * 8
    return -(1 << (bits - 1)) <= value < (1 << (bits - 1))


class Label:
    """A branch target. Compared by identity; ``name`` is for display only."""

    __slots__ = ("name",)

    def __init__(self, name: str = ""):
        self.name = name

    def __repr__(self) -> str:
        return f"Label({self.name!r})"


@dataclass(frozen=True)
class RawStr:
    """A string operand whose pool offset didn't land on the start of a pool
    entry - kept as the raw offset so the file still round-trips."""

    offset: int


StrOperand = Union[str, RawStr]


@dataclass(eq=False)
class Instr:
    """One instruction. Operand shapes by opcode:

    * branches: ``[Label]``
    * ``pushstr*``: ``[str | RawStr]``
    * ``externCall``: ``[str | RawStr, argc]``
    * ``localCall``: ``[function_index]``
    * everything else: raw ints (already sign-decoded)."""

    op: int
    operands: list = field(default_factory=list)

    @property
    def name(self) -> str:
        return OPCODES[self.op]

    def __repr__(self) -> str:
        ops = ", ".join(o.name if isinstance(o, Label) else repr(o) for o in self.operands)
        return f"{self.name}({ops})"


CodeItem = Union[Instr, Label]


@dataclass(eq=False)
class Function:
    """One function record. ``id_string`` is the function's global name
    (``None`` for anonymous functions); named functions are registered in
    the engine-wide name table at load time, so other scripts can
    ``externCall`` them by name.

    ``params`` are the raw u16 trigger parameters (their meaning depends on
    ``type`` - see ``event_script.FUNCTION_TRIGGERS``). The ``raw_*`` fields
    hold on-disk padding bytes (vanilla files contain leftover garbage
    there) so an unmodified file writes back byte-for-byte; they are ignored
    whenever their length no longer matches the layout."""

    id_string: Optional[str]
    type: int
    num_args: int
    num_vars: int
    params: list[int]
    code: list  # list[CodeItem]
    index: int = 0
    raw_reserved_0f: int = 0  # record byte +0x0F; never read by the game
    raw_parent_word: int = 0  # record word +0x08; overwritten by the loader
    raw_id_tail: Optional[bytes] = None
    raw_params_pad: Optional[bytes] = None
    raw_code_pad: Optional[bytes] = None

    def instructions(self) -> list[Instr]:
        return [item for item in self.code if isinstance(item, Instr)]


@dataclass(eq=False)
class ScriptFile:
    header: bytes  # the first 0x24 header bytes, verbatim ("cmb\0", file name, build date, globals count...)
    pool: list[str]  # string-pool entries, in file order
    functions: list[Function]
    raw_pool_tail: bytes = b"\x00"
    raw_pool_tail_entries: int = -1  # len(pool) when raw_pool_tail was read; -1 = none

    @property
    def global_count(self) -> int:
        """Header +0x22: how many global slots this script reserves."""
        return int.from_bytes(self.header[0x22:0x24], "little")

    def function_by_name(self, name: str) -> Optional[Function]:
        for fn in self.functions:
            if fn.id_string == name:
                return fn
        return None

    def intern(self, text: str) -> str:
        """Make sure ``text`` is in the pool (appending it if needed)."""
        if text not in self.pool:
            self.pool.append(text)
        return text
