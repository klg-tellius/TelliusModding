"""Radiant Dawn's ``FE10Epilogue.bin``: who gets which ending after the final chapter.

A :mod:`pool_file` file. Data offset 0 and 4 point at the build time and the author; the symbol
``EPILOGUE_DATA`` (offset 8) is a u32 count and 44-byte records, read by the epilogue list
builder ``0x8027163C`` with the texts from ``Mess/<lang>epilogue.m``:

====  ========================================================================================
+00   PID
+04   ending when the unit survived (``MEP_ALIVE_...``)
+08   line when the unit was lost but only wounded (unit flag 0x20; ``MEP_PARTY_COMMON``)
+0C   line when the unit was killed (``MEP_DEAD_COMMON``)
+10   support partner PID / +14 the ending used instead when that unit is the active support
      partner at rank A
+18   PID / +1C the ending used instead when that unit is alive (or only wounded)
+20   PID / +24 the ending used instead when that unit was killed
+28   non-zero: list the entry even when the unit is not in the army (found by name instead)
====  ========================================================================================

The three alternatives are tried in that order and the first that matches replaces +04.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass, field, fields

from .pool_file import PoolFile, TableWriter, build_pool_file, read_pool_file

SYMBOL = "EPILOGUE_DATA"
RECORD_SIZE = 44


class EpilogueError(ValueError):
    pass


@dataclass
class Epilogue:
    pid: str | None
    ending: str | None = None
    wounded: str | None = "MEP_PARTY_COMMON"
    killed: str | None = "MEP_DEAD_COMMON"
    support_partner: str | None = None
    support_ending: str | None = None
    alive_partner: str | None = None
    alive_ending: str | None = None
    killed_partner: str | None = None
    killed_ending: str | None = None
    always: int = 0


TEXT_FIELDS = [f.name for f in fields(Epilogue) if f.name != "always"]


@dataclass
class EpilogueData:
    build_time: str | None = None
    author: str | None = None
    entries: list[Epilogue] = field(default_factory=list)
    trailer: bytes = b""
    header_tail: bytes = bytes(12)


def read_epilogues(data: bytes) -> EpilogueData:
    doc = read_pool_file(data)
    if [name for name, _ in doc.symbols] != [SYMBOL] or doc.symbols[0][1] != 8:
        raise EpilogueError("FE10Epilogue.bin should export EPILOGUE_DATA at offset 8.")
    body, pointers = doc.body, doc.pointers
    out = EpilogueData(pointers.get(0), pointers.get(4), header_tail=doc.header_tail)
    (count,) = struct.unpack_from(">I", body, 8)
    at = 12
    if at + count * RECORD_SIZE > len(body):
        raise EpilogueError("FE10Epilogue.bin ends inside its records.")
    for _ in range(count):
        values = []
        for k in range(10):
            offset = at + 4 * k
            if offset not in pointers and struct.unpack_from(">I", body, offset)[0]:
                raise EpilogueError(f"Expected a pointer or zero at {offset:#x}.")
            values.append(pointers.get(offset))
        if at + 40 in pointers:
            raise EpilogueError(f"Unexpected pointer at {at + 40:#x}.")
        out.entries.append(Epilogue(*values, struct.unpack_from(">I", body, at + 40)[0]))
        at += RECORD_SIZE
    out.trailer = body[at:]
    return out


def build_epilogues(document: EpilogueData) -> bytes:
    w = TableWriter()
    w.text(document.build_time)
    w.text(document.author)
    w.word(len(document.entries))
    for entry in document.entries:
        for name in TEXT_FIELDS:
            w.text(getattr(entry, name))
        w.word(entry.always)
    w.raw(document.trailer)
    return build_pool_file(PoolFile(bytes(w.body), w.pointers, [(SYMBOL, 8)], document.header_tail))


def check(document: EpilogueData, pids: set[str] | None = None, texts: set[str] | None = None) -> list[str]:
    """Half-filled alternatives, and PIDs or message keys the game data does not have."""
    problems = []
    for i, e in enumerate(document.entries):
        who = e.pid or f"entry {i}"
        for pid_field, text_field in (("support_partner", "support_ending"), ("alive_partner", "alive_ending"),
                                      ("killed_partner", "killed_ending")):
            if bool(getattr(e, pid_field)) != bool(getattr(e, text_field)):
                problems.append(f"{who}: {pid_field} and {text_field} must both be set or both empty.")
        if pids is not None:
            for name in ("pid", "support_partner", "alive_partner", "killed_partner"):
                value = getattr(e, name)
                if value and value not in pids:
                    problems.append(f"{who}: {value} is not a character in FE10Data.")
        if texts is not None:
            for name in ("ending", "wounded", "killed", "support_ending", "alive_ending", "killed_ending"):
                value = getattr(e, name)
                if value and value not in texts:
                    problems.append(f"{who}: no message {value} in the epilogue messages.")
    return problems
