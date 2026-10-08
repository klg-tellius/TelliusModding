"""Read and write ``.cmb`` files to and from :mod:`.model`.

On-disk layout (every vanilla Path of Radiance script, checked on all 43):

* ``0x00`` header (0x2C bytes). ``+0x24`` = string-pool offset (always
  0x2C), ``+0x28`` = function-table offset. ``+0x20`` is overwritten at
  load; ``+0x22`` is the script's global-slot count.
* string pool: NUL-separated Shift-JIS strings, padded with NULs to 4.
* function table: one u32 absolute address per function, then a 0 word
  (the loader walks it until that terminator).
* per function, 4-aligned: a 20-byte record (``<IIIbbbbhh``: id-string
  ptr, code ptr, reserved word, type, num_args, num_params, reserved byte,
  index, num_vars), ``num_params`` u16 trigger params, the optional id
  string (NUL-terminated, padded to 4), then the code padded with 1-4
  bytes to the next 4-byte boundary.

Header/table/record words are little-endian; instruction operands are
big-endian and signed. A branch's target is ``opcode_offset + 1 +
operand`` (the VM does ``pc += operand - 2`` after reading the operand).

Radiant Dawn uses the same layout; its bytecode differences are described
by :class:`~.model.Dialect` (picked from the header's build stamp unless the
caller passes one).
"""

from __future__ import annotations

import struct
from pathlib import Path
from typing import Optional

from .model import (
    BRANCH_OPS,
    EXTERN_CALL,
    LOCAL_CALL,
    OPCODES,
    OPERAND_WIDTHS,
    PUSHSTR_OPS,
    PUSH_OPS,
    RET0,
    RETURN,
    RETURN_OPS,
    Dialect,
    Function,
    Instr,
    Label,
    RawStr,
    ScriptFile,
    detect_dialect,
    fits_signed,
    local_call_width,
    var_op_info,
)

ENCODING = "cp932"
HEADER_SIZE = 0x2C
RECORD = struct.Struct("<IIIbbbbhh")


class CmbError(Exception):
    pass


def _align4(value: int) -> int:
    return (value + 3) & ~3


# -- reading ----------------------------------------------------------------


def read_cmb(data: bytes, dialect: Optional[Dialect] = None) -> ScriptFile:
    if len(data) < HEADER_SIZE:
        raise CmbError("File too small to be a .cmb script.")
    dialect = dialect or detect_dialect(data)
    pool_start, table_start = struct.unpack_from("<II", data, 0x24)

    pool_bytes = data[pool_start:table_start]
    entries = pool_bytes.split(b"\x00")
    while entries and entries[-1] == b"":
        entries.pop()
    raw = b"\x00".join(entries)
    pool = [e.decode(ENCODING) for e in entries]
    offset_to_text: dict[int, str] = {}
    offset = 0
    for text, entry in zip(pool, entries):
        offset_to_text.setdefault(offset, text)
        offset += len(entry) + 1

    addresses = []
    pos = table_start
    while True:
        (addr,) = struct.unpack_from("<I", data, pos)
        pos += 4
        if addr == 0:
            break
        addresses.append(addr)

    functions = []
    for i, addr in enumerate(addresses):
        end = addresses[i + 1] if i + 1 < len(addresses) else len(data)
        functions.append(_read_function(data, addr, end, offset_to_text, dialect))

    return ScriptFile(
        header=data[:0x24],
        pool=pool,
        functions=functions,
        raw_pool_tail=pool_bytes[len(raw):],
        raw_pool_tail_entries=len(pool),
        dialect=dialect,
    )


def read_cmb_path(path: Path | str, dialect: Optional[Dialect] = None) -> ScriptFile:
    return read_cmb(Path(path).read_bytes(), dialect)


def _read_function(data: bytes, addr: int, end: int, strings: dict[int, str], dialect: Dialect) -> Function:
    id_ptr, code_start, parent, fn_type, num_args, num_params, reserved, index, num_vars = RECORD.unpack_from(data, addr)
    params_end = addr + RECORD.size + 2 * num_params
    params = list(struct.unpack_from(f"<{num_params}H", data, addr + RECORD.size))

    id_string = None
    id_tail = params_pad = None
    if id_ptr:
        blob = data[id_ptr:code_start]
        nul = blob.index(0)
        id_string = blob[:nul].decode(ENCODING)
        id_tail = blob[nul:]
    else:
        params_pad = data[params_end:code_start]

    code_end = _find_code_end(data, code_start, end, dialect)
    code = _decode_code(data, code_start, code_end, strings, dialect)
    return Function(
        id_string=id_string,
        type=fn_type,
        num_args=num_args,
        num_vars=num_vars,
        params=params,
        code=code,
        index=index,
        raw_reserved_0f=reserved,
        raw_parent_word=parent,
        raw_id_tail=id_tail,
        raw_params_pad=params_pad,
        raw_code_pad=data[code_end:end],
    )


def _operand_widths(data: bytes, pos: int, dialect: Dialect) -> tuple[int, ...]:
    """Operand widths of the instruction at ``pos`` (localCall's varint
    depends on its first operand byte in FE10)."""
    op = data[pos]
    if op == LOCAL_CALL and dialect.varint_local_call and pos + 1 < len(data) and data[pos + 1] & 0x80:
        return (2,)
    return OPERAND_WIDTHS[op]


def _find_code_end(data: bytes, start: int, end: int, dialect: Dialect) -> int:
    """Code is followed by 1-4 padding bytes (sometimes garbage), so the
    code ends at an instruction boundary 1-4 bytes before ``end`` that
    follows a ``return``.

    Garbage padding can itself decode as instructions (C01 function 6 ends
    ``push8 0; return`` then pads with ``00 39 07``, which reads as ``nop;
    return``). The FE9 compiler ends every function with ``push8 0;
    return`` (FE10's ends triggered functions that way and callable ones
    with ``ret0``) and no branch goes past it, so the earliest end that fits
    both wins."""
    pos = start
    return_ends = set()
    epilogue_ends = set()
    targets = []
    returns = RETURN_OPS if dialect.extended_ops else (RETURN,)
    while pos < end:
        op = data[pos]
        if op >= len(OPCODES):
            break
        nxt = pos + 1 + sum(_operand_widths(data, pos, dialect))
        if op in returns:
            return_ends.add(nxt)
            if op == RET0 or (op == RETURN and pos - start >= 2 and data[pos - 2] == 0x19 and data[pos - 1] == 0):
                epilogue_ends.add(nxt)
        elif op in BRANCH_OPS and nxt <= end:
            targets.append(pos + 1 + _read_operand(data, pos + 1, OPERAND_WIDTHS[op][0]))
        pos = nxt
    for pad in range(4, 0, -1):
        cut = end - pad
        if cut in epilogue_ends and all(t < cut for t in targets):
            return cut
    for pad in range(1, 5):
        if end - pad in return_ends:
            return end - pad
    if end in return_ends:
        return end
    raise CmbError(f"Function code at 0x{start:X} doesn't end with a return.")


def _read_operand(data: bytes, pos: int, width: int) -> int:
    return int.from_bytes(data[pos:pos + width], "big", signed=True)


def _decode_code(data: bytes, start: int, end: int, strings: dict[int, str], dialect: Dialect) -> list:
    raw: list[tuple[int, Instr, Optional[int]]] = []  # (offset, instr, branch target offset)
    pos = start
    while pos < end:
        op = data[pos]
        if op >= len(OPCODES):
            raise CmbError(f"Unknown opcode 0x{op:02X} at 0x{pos:X}.")
        offset = pos - start
        widths = _operand_widths(data, pos, dialect)
        pos += 1
        operands = []
        for width in widths:
            operands.append(_read_operand(data, pos, width))
            pos += width
        if op == LOCAL_CALL and dialect.varint_local_call:
            operands[0] &= 0x7FFF if widths == (2,) else 0x7F
        target = None
        if op in BRANCH_OPS:
            target = offset + 1 + operands[0]
        elif op in PUSHSTR_OPS or op == EXTERN_CALL:
            operands[0] = strings.get(operands[0], RawStr(operands[0]))
        if op == EXTERN_CALL:
            operands[1] &= 0xFF  # argc byte
        raw.append((offset, Instr(op, operands), target))
    if pos != end:
        raise CmbError(f"Instruction at the end of 0x{start:X} runs past its function.")

    boundaries = {offset for offset, _, _ in raw} | {end - start}
    labels: dict[int, Label] = {}
    for offset, instr, target in raw:
        if target is None:
            continue
        if target not in boundaries:
            raise CmbError(f"Branch at +{offset} targets +{target}, which isn't an instruction boundary.")
        label = labels.setdefault(target, Label(f"L{target}"))
        instr.operands[0] = label

    code: list = []
    for offset, instr, _ in raw:
        if offset in labels:
            code.append(labels[offset])
        code.append(instr)
    if end - start in labels:
        code.append(labels[end - start])
    return code


# -- writing ----------------------------------------------------------------


def _pool_layout(script: ScriptFile) -> tuple[bytes, dict[str, int]]:
    encoded = [text.encode(ENCODING) for text in script.pool]
    for e in encoded:
        if b"\x00" in e:
            raise CmbError("A pool string can't contain a NUL byte.")
    offsets: dict[str, int] = {}
    offset = 0
    for text, e in zip(script.pool, encoded):
        offsets.setdefault(text, offset)
        offset += len(e) + 1
    raw = b"\x00".join(encoded)
    tail = script.raw_pool_tail
    end = HEADER_SIZE + len(raw)
    # Keep the original tail only while the pool is untouched (one vanilla
    # file ends its last string on the boundary with no NUL at all);
    # otherwise terminate the last string and pad with NULs to 4.
    if script.raw_pool_tail_entries != len(script.pool) or (end + len(tail)) % 4:
        tail = b"\x00" * (_align4(end + 1) - end)
    return raw + tail, offsets


def _string_offset(value, offsets: dict[str, int]) -> int:
    if isinstance(value, RawStr):
        return value.offset
    try:
        return offsets[value]
    except KeyError:
        raise CmbError(f"String {value!r} is not in the string pool.") from None


def _widen(op: int, value: int) -> int:
    """Smallest opcode of the same family that is at least as wide as ``op``
    and fits ``value`` (never narrows, so vanilla files keep their bytes)."""
    if op in PUSH_OPS or op in PUSHSTR_OPS:
        family = PUSH_OPS if op in PUSH_OPS else PUSHSTR_OPS
        for candidate in family[family.index(op):]:
            if fits_signed(value, OPERAND_WIDTHS[candidate][0]):
                return candidate
    elif fits_signed(value, OPERAND_WIDTHS[op][0]):
        return op
    elif var_op_info(op) is not None and not var_op_info(op)[2] and fits_signed(value, 2):
        return op + 1
    raise CmbError(f"{OPCODES[op]}: value {value} doesn't fit its operand.")


def _instr_widths(op: int, operands: list, dialect: Dialect) -> tuple[int, ...]:
    if op == LOCAL_CALL:
        return (local_call_width(operands[0], dialect),)
    return OPERAND_WIDTHS[op]


def _encode_code(code: list, offsets: dict[str, int], dialect: Dialect) -> bytes:
    """Two passes: fix every opcode/width first, then place labels and
    resolve branches (branch operands are always 2 bytes)."""
    items = []
    for item in code:
        if isinstance(item, Label):
            items.append(item)
            continue
        op, operands = item.op, list(item.operands)
        if op in PUSHSTR_OPS:
            operands[0] = _string_offset(operands[0], offsets)
            op = _widen(op, operands[0])
        elif op == EXTERN_CALL:
            operands[0] = _string_offset(operands[0], offsets)
            if not fits_signed(operands[0], 2):
                raise CmbError("externCall name offset exceeds the 16-bit operand.")
        elif op in BRANCH_OPS:
            if not isinstance(operands[0], Label):
                raise CmbError(f"{OPCODES[op]} needs a Label target.")
        elif op == LOCAL_CALL and dialect.varint_local_call:
            if not 0 <= operands[0] < 0x8000:
                raise CmbError(f"localCall index {operands[0]} doesn't fit its operand (0-32767).")
        elif OPERAND_WIDTHS[op]:
            op = _widen(op, operands[0])
        items.append((op, operands))

    label_pos: dict[int, int] = {}
    pos = 0
    for item in items:
        if isinstance(item, Label):
            label_pos[id(item)] = pos
        else:
            pos += 1 + sum(_instr_widths(item[0], item[1], dialect))

    out = bytearray()
    for item in items:
        if isinstance(item, Label):
            continue
        op, operands = item
        here = len(out)
        out.append(op)
        if op in BRANCH_OPS:
            if id(operands[0]) not in label_pos:
                raise CmbError(f"Branch to a label that isn't in this function: {operands[0]!r}")
            rel = label_pos[id(operands[0])] - (here + 1)
            if not fits_signed(rel, 2):
                raise CmbError("Branch distance exceeds 32 KB.")
            out += rel.to_bytes(2, "big", signed=True)
            continue
        if op == LOCAL_CALL and dialect.varint_local_call:
            if local_call_width(operands[0], dialect) == 2:
                out += (operands[0] | 0x8000).to_bytes(2, "big")
            else:
                out.append(operands[0])
            continue
        for width, value in zip(OPERAND_WIDTHS[op], operands):
            if op == EXTERN_CALL and width == 1:
                out.append(value & 0xFF)
            else:
                out += int(value).to_bytes(width, "big", signed=True)
    return bytes(out)


def write_cmb(script: ScriptFile) -> bytes:
    pool_bytes, offsets = _pool_layout(script)
    table_start = HEADER_SIZE + len(pool_bytes)
    n = len(script.functions)
    pos = table_start + 4 * n + 4

    bodies = []
    addresses = []
    for fn in script.functions:
        addr = _align4(pos)
        addresses.append(addr)
        params_end = addr + RECORD.size + 2 * len(fn.params)
        blob = bytearray()
        if fn.id_string is not None:
            name = fn.id_string.encode(ENCODING)
            id_ptr = params_end
            need = _align4(id_ptr + len(name) + 1) - (id_ptr + len(name))
            tail = fn.raw_id_tail if fn.raw_id_tail is not None and len(fn.raw_id_tail) == need and fn.raw_id_tail[:1] == b"\x00" else b"\x00" * need
            blob += name + tail
            code_start = id_ptr + len(blob)
        else:
            id_ptr = 0
            need = _align4(params_end) - params_end
            blob += fn.raw_params_pad if fn.raw_params_pad is not None and len(fn.raw_params_pad) == need else b"\x00" * need
            code_start = params_end + need
        code = _encode_code(fn.code, offsets, script.dialect)
        pad_len = 4 - len(code) % 4
        pad = fn.raw_code_pad if fn.raw_code_pad is not None and len(fn.raw_code_pad) == pad_len else b"\x00" * pad_len

        record = RECORD.pack(
            id_ptr, code_start, fn.raw_parent_word, fn.type, fn.num_args, len(fn.params),
            fn.raw_reserved_0f, fn.index, fn.num_vars,
        )
        params = struct.pack(f"<{len(fn.params)}H", *fn.params)
        bodies.append(record + params + bytes(blob) + code + pad)
        pos = addr + len(bodies[-1])

    out = bytearray(script.header[:0x24])
    out += struct.pack("<II", HEADER_SIZE, table_start)
    out += pool_bytes
    for addr in addresses:
        out += struct.pack("<I", addr)
    out += b"\x00" * 4  # function-table terminator
    for addr, body in zip(addresses, bodies):
        out += b"\x00" * (addr - len(out))
        out += body
    return bytes(out)


def write_cmb_path(script: ScriptFile, path: Path | str) -> None:
    Path(path).write_bytes(write_cmb(script))
