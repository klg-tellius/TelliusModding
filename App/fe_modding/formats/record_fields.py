"""Typed fields of fixed-size records, for the pages that edit them as forms.

A :class:`Field` names one value of a record: its offset, its kind (``label`` for a 4-byte pointer to
a name, a number format from ``u8`` to ``f32``, ``hex8``-``hex32`` for flag words shown in
hexadecimal, or ``bit`` for one bit of a byte) and a short note. :func:`read_numbers` and
:func:`write_numbers` read and write the number fields in place; each format module handles its own
``label`` fields, since the containers relocate their pointers differently.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass

LABEL = "label"
BIT = "bit"
FORMATS = {"u8": "B", "s8": "b", "u16": "H", "s16": "h", "u32": "I", "s32": "i", "f32": "f",
           "hex8": "B", "hex16": "H", "hex32": "I"}


class FieldError(ValueError):
    pass


@dataclass(frozen=True)
class Field:
    """One editable value: record-relative ``offset`` and ``kind`` (see the module docstring); a
    ``bit`` field is bit ``bit`` (0 = lowest) of the byte at ``offset``. ``choices`` maps stored
    numbers to names for a fixed list."""

    key: str
    offset: int
    kind: str
    name: str
    note: str = ""
    bit: int = 0
    choices: tuple[tuple[int, str], ...] = ()

    @property
    def size(self) -> int:
        if self.kind == LABEL:
            return 4
        if self.kind == BIT:
            return 1
        return struct.calcsize(FORMATS[self.kind])

    @property
    def is_number(self) -> bool:
        return self.kind != LABEL


def number_range(field: Field) -> tuple[int, int]:
    if field.kind == BIT:
        return 0, 1
    bits = 8 * field.size
    return (-(1 << (bits - 1)), (1 << (bits - 1)) - 1) if field.kind.startswith("s") else (0, (1 << bits) - 1)


def parse_number(field: Field, value) -> int | float:
    """``value`` (a number or the form's text) checked against ``field``'s range."""
    if field.kind == "f32":
        try:
            return float(value)
        except (TypeError, ValueError) as exc:
            raise FieldError(f"{field.name}: {value!r} is not a number.") from exc
    if isinstance(value, str):
        text = value.strip().split(" - ", 1)[0].strip()
        if field.kind == BIT and text.lower() in ("yes", "no"):
            return int(text.lower() == "yes")
        try:
            number = int(text, 16) if field.kind.startswith("hex") else int(text, 0)
        except ValueError as exc:
            raise FieldError(f"{field.name}: {value!r} is not a whole number.") from exc
    elif isinstance(value, (bool, int)):
        number = int(value)
    else:
        raise FieldError(f"{field.name}: {value!r} is not a whole number.")
    low, high = number_range(field)
    if not low <= number <= high:
        raise FieldError(f"{field.name} must be from {low} to {high}.")
    return number


def show(field: Field, value) -> str:
    """``value`` as the form shows it."""
    if field.kind == LABEL:
        return value or ""
    if field.kind == BIT:
        return "Yes" if value else "No"
    if field.kind.startswith("hex"):
        return f"{value:0{2 * field.size}X}"
    if field.kind == "f32":
        return f"{value:g}"
    names = dict(field.choices)
    return f"{value} - {names[value]}" if value in names else str(value)


def read_number(data: bytes, at: int, field: Field) -> int | float:
    if field.kind == BIT:
        return data[at + field.offset] >> field.bit & 1
    return struct.unpack_from(">" + FORMATS[field.kind], data, at + field.offset)[0]


def read_numbers(data: bytes, at: int, fields) -> dict:
    return {f.key: read_number(data, at, f) for f in fields if f.is_number}


def write_numbers(data: bytes, at: int, fields, values: dict) -> bytes:
    """``data`` with the number fields of the record at absolute ``at`` set from ``values`` (field key
    -> number or text). Keys of ``label`` fields are left to the caller; unknown keys refuse."""
    by_key = {f.key: f for f in fields}
    out = bytearray(data)
    for key, value in values.items():
        field = by_key.get(key)
        if field is None:
            raise FieldError(f"Unknown field {key}.")
        if not field.is_number:
            continue
        number = parse_number(field, value)
        if field.kind == BIT:
            mask = 1 << field.bit
            out[at + field.offset] = (out[at + field.offset] & ~mask) | (mask if number else 0)
        else:
            struct.pack_into(">" + FORMATS[field.kind], out, at + field.offset, number)
    return bytes(out)
