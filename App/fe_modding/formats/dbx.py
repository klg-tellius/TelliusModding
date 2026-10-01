"""Lossless editing of the battle engine's ``.dbx`` text tables.

A ``.dbx`` file (Shift-JIS, usually CRLF) is ``#`` comments and ``{ ... }``
blocks of ``key<TAB>value`` lines. A block's ``class`` line says what it is
(``Weapon``, ``Camera``, ``CameraAnime``, ``Param``, ``Model`` ...) and its
``name`` line names it. Keys may repeat inside a block (the camera scripts
use ``pos``/``rot``/``dist``/``time`` once per keyframe).

:class:`DbxDoc` keeps every line as it was read - indentation, spacing,
trailing comments, odd values (vanilla ``camera.dbx`` has ``rot -2.-2, ...``)
and the end-of-line style - and edits only the value it is asked to change,
so ``doc.text`` is the input again until something is edited.
"""

from __future__ import annotations

from dataclasses import dataclass


class DbxError(ValueError):
    """A ``.dbx`` edit that does not apply (missing block, missing key...)."""


@dataclass
class Field:
    line: int  # index into the document's lines
    key: str
    value: str  # text between the key and any trailing comment, stripped
    comment: str  # "# ..." after the value, or ""


@dataclass
class Block:
    start: int  # line index of "{"
    end: int  # line index of "}"
    fields: list[Field]

    def get(self, key: str, default: str | None = None) -> str | None:
        """The first value of ``key``."""
        for f in self.fields:
            if f.key == key:
                return f.value
        return default

    def get_all(self, key: str) -> list[str]:
        return [f.value for f in self.fields if f.key == key]

    @property
    def cls(self) -> str | None:
        return self.get("class")

    @property
    def name(self) -> str | None:
        return self.get("name")


def _split_line(raw: str) -> tuple[str, str]:
    body = raw.rstrip("\r\n")
    return body, raw[len(body):]


def _parse_field(body: str) -> tuple[str, str, str] | None:
    code, hash_, comment = body.partition("#")
    stripped = code.strip()
    if not stripped or stripped in ("{", "}"):
        return None
    parts = stripped.split(None, 1)
    return parts[0], parts[1].strip() if len(parts) > 1 else "", hash_ + comment


class DbxDoc:
    def __init__(self, text: str):
        self.lines = text.splitlines(keepends=True)

    @property
    def text(self) -> str:
        return "".join(self.lines)

    @property
    def eol(self) -> str:
        """The file's line ending (first one seen; CRLF when there is none)."""
        for raw in self.lines:
            ending = _split_line(raw)[1]
            if ending:
                return ending
        return "\r\n"

    def blocks(self) -> list[Block]:
        out, current = [], None
        for i, raw in enumerate(self.lines):
            body = _split_line(raw)[0]
            code = body.split("#", 1)[0].strip()
            if code == "{" and current is None:
                current = Block(i, i, [])
            elif code == "}" and current is not None:
                current.end = i
                out.append(current)
                current = None
            elif current is not None:
                parsed = _parse_field(body)
                if parsed:
                    current.fields.append(Field(i, *parsed))
        return out

    def find(self, cls: str | None = None, name: str | None = None) -> Block:
        """The first block with this ``class`` and/or ``name``."""
        for block in self.blocks():
            if (cls is None or block.cls == cls) and (name is None or block.name == name):
                return block
        raise DbxError(f"No block {cls or ''} {name or ''}".strip() + ".")

    # -- edits (all return nothing; ``text`` shows the result) -------------------

    def set_value(self, field: Field, value: str) -> None:
        """Replace one field's value, keeping its key, spacing and comment."""
        body, eol = _split_line(self.lines[field.line])
        code, hash_, comment = body.partition("#")
        prefix = code[: len(code) - len(code.lstrip()) + len(field.key)]
        rest = code[len(prefix):]
        lead = rest[: len(rest) - len(rest.lstrip())] if rest.strip() else ""
        trail = rest[len(rest.rstrip()):] if rest.strip() else ""
        self.lines[field.line] = f"{prefix}{lead or chr(9)}{value}{trail}{hash_}{comment}{eol}"

    def add_field(self, block: Block, key: str, value: str, *, after: Field | None = None) -> None:
        """Insert ``key value`` after ``after`` (default: the block's last field),
        indented like its neighbour."""
        anchor = after or (block.fields[-1] if block.fields else None)
        if anchor is not None:
            raw = self.lines[anchor.line]
            indent = raw[:len(raw) - len(raw.lstrip())]
            at = anchor.line + 1
        else:
            indent, at = "\t", block.start + 1
        eol = self.eol
        if at >= len(self.lines) or not _split_line(self.lines[at - 1])[1]:
            self.lines[at - 1] += eol  # the anchor was the file's last line
        self.lines.insert(at, f"{indent}{key}\t{value}{eol}")

    def remove_field(self, field: Field) -> None:
        del self.lines[field.line]


def parse(text: str) -> DbxDoc:
    return DbxDoc(text)
