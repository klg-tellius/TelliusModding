"""Readable source for the AI scripts of ``cp_data.bin``.

Every script entry is one line, so a script converts to text and back
without losing anything (:func:`decompile` / :func:`compile_source`)::

    use_staff(chance=100)
    if found: goto L99
    steal(chance=100)
    if found: goto L99
    attack(chance=100, targets=TBL_PID_LAGU, exclude=True)
    L99:
    end()

Statements (see :mod:`cp_ops` for every function and its fields):

* ``L99:`` - a label (opcode 0, label id 99);
* ``goto L99`` / ``goto start`` - jump (``start`` = the first entry);
* ``if found: goto L99`` / ``if not found: goto L99``;
* ``if r0 == 3: goto L99`` - compare a register (``== != > >= < <=``); the value
  may be a result code name (``TALK_QUEUED``...);
* ``r0 = count_units(range=1.5)`` - the functions that write a register;
* ``attack(chance=100)`` - every other opcode, with keyword arguments;
* ``op(213, a=1, b=0xFFFF)`` - any entry, word by word.

Values: numbers (``-3``, ``0x10``, ``1.5`` for factors), ``True`` / ``False``,
labels (``L1``, ``start``), names (``PID_IKE``, ``TBL_PID_LAGU``, or quoted
``"SEQ_ATTACK1.5RANGEMOVE"``), ``None`` (no name / no table). Inside ``op(...)``
a bare ``TBL_*`` name is a table pointer and any other name a label string;
``ref(NAME)`` forces a section pointer. Every call also takes
``threat_limit=`` (the entry's ``b`` word: a number, ``none`` = 0xFFFF,
``keep`` = 0), unless the opcode uses ``b`` itself. ``#`` starts a comment.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field as dataclass_field
from typing import Iterable, Optional

from .cp_data import Entry, Script, SectionRef, Value
from .cp_ops import (BY_NAME, COMPARISON_CODES, COMPARISONS, HANDLED_OPS, NAME_KINDS, NO_LIMIT, OPS,
                     REGISTER_COUNT, RESULT_CODES, RESULT_NAMES, TABLE_KINDS, Field, OpSpec)

U32 = 0xFFFFFFFF
SLOTS = "abcdef"
_IDENT = re.compile(r"[A-Za-z_][A-Za-z0-9_.]*\Z")
_NUMBER = re.compile(r"[-+]?(0[xX][0-9a-fA-F]+|\d+(\.\d*)?|\.\d+)\Z")
#: ops after which a COMPARE on r0 reads a result code
_CODE_WRITERS = {5, 100, 113, 114, 200, 201, 204, 209, 212, 215, 218, 501}
_ENDINGS = {4, 1000, 1001}  # an entry the script can end with


# -- values ------------------------------------------------------------------------------

def _signed(value: int) -> int:
    value &= U32
    return value - (1 << 32) if value & 0x80000000 else value


def _name_text(name: str) -> str:
    return name if _IDENT.match(name) and name not in _WORDS else '"' + name.replace("\\", "\\\\").replace('"', '\\"') + '"'


_WORDS = {"True", "False", "None", "start", "keep", "none", "found", "not", "goto", "if", "ref"}


class _Unrepresentable(Exception):
    """The structured form can't hold this entry exactly; use ``op(...)``."""


def _fixed_text(value: int) -> str:
    number = _signed(value) / 65536
    text = f"{number:.6f}".rstrip("0").rstrip(".")
    if "." not in text:
        text += ".0"
    if round(float(text) * 65536) != _signed(value):
        raise _Unrepresentable
    return text


def format_value(value: Value, kind: str) -> str:
    """A field value as readable text; raises :class:`_Unrepresentable`."""
    if kind in ("int", "percent"):
        if not isinstance(value, int):
            raise _Unrepresentable
        return str(_signed(value))
    if kind == "bool":
        if value == 0:
            return "False"
        if value == 1:
            return "True"
        raise _Unrepresentable
    if kind == "label":
        if not isinstance(value, int) or _signed(value) < 0:
            raise _Unrepresentable
        return "start" if value == 0 else f"L{value}"
    if kind == "fixed":
        if not isinstance(value, int):
            raise _Unrepresentable
        return _fixed_text(value)
    if kind in NAME_KINDS:
        if value == 0:
            return "None"
        if isinstance(value, str) and not isinstance(value, SectionRef) and value:
            return _name_text(value)
        raise _Unrepresentable
    if kind in TABLE_KINDS:
        if value == 0:
            return "None"
        if isinstance(value, SectionRef):
            return _name_text(value.name)
        raise _Unrepresentable
    # any
    if isinstance(value, SectionRef):
        return value.name if value.name.startswith("TBL_") and _IDENT.match(value.name) else f"ref({_name_text(value.name)})"
    if isinstance(value, str):
        return value if _IDENT.match(value) and not value.startswith("TBL_") and value not in _WORDS else (
            '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"')
    return _hex_or_int(value)


def _hex_or_int(value: int) -> str:
    signed = _signed(value)
    return f"{value & U32:#x}" if value & U32 in (0xFFFF, 0xFFFF0000) or abs(signed) >= 0x10000 else str(signed)


def _threat_text(b: int) -> str:
    if b == 0:
        return "keep"
    if b == NO_LIMIT:
        return "none"
    return str(_signed(b))


# -- decompile -------------------------------------------------------------------------------

def _structured(entry: Entry, previous: Optional[Entry]) -> str:
    spec = OPS.get(entry.op)
    if spec is None or spec.form == "header":
        raise _Unrepresentable
    used = {f.slot for f in spec.fields}
    for slot in SLOTS:
        if slot not in used and slot != "b" and getattr(entry, slot) != 0:
            raise _Unrepresentable
    b = entry.b
    if not isinstance(b, int):
        raise _Unrepresentable
    if spec.form == "label":
        if b != spec.b_default or not isinstance(entry.c, int) or _signed(entry.c) < 0:
            raise _Unrepresentable
        return f"L{entry.c}:"
    if spec.form == "goto":
        if b != spec.b_default:
            raise _Unrepresentable
        return f"goto {format_value(entry.d, 'label')}"
    if spec.form == "if_found":
        if b != spec.b_default:
            raise _Unrepresentable
        found = format_value(entry.a, "bool")
        return f"if {'' if found == 'True' else 'not '}found: goto {format_value(entry.d, 'label')}"
    if spec.form == "compare":
        if not isinstance(b, int) or b not in COMPARISONS:
            raise _Unrepresentable
        reg = _reg_text(entry.a)
        value = format_value(entry.c, "int")
        if (previous is not None and previous.op in _CODE_WRITERS and entry.a == 0
                and isinstance(entry.c, int) and entry.c in RESULT_CODES):
            value = RESULT_CODES[entry.c][0]
        return f"if {reg} {COMPARISONS[b]} {value}: goto {format_value(entry.d, 'label')}"
    args = []
    for f in spec.fields:
        if spec.form == "assign" and f.slot == "a":
            continue
        value = getattr(entry, f.slot)
        if f.default is not None and value == _raw_default(f):
            continue
        args.append(f"{f.name}={format_value(value, f.kind)}")
    if not spec.uses_b and b != spec.b_default:
        args.append(f"threat_limit={_threat_text(b)}")
    call = f"{spec.name}({', '.join(args)})"
    if spec.form == "assign":
        return f"{_reg_text(entry.a)} = {call}"
    return call


def _raw_default(f: Field) -> Value:
    if f.default is False:
        return 0
    if f.default is True:
        return 1
    return f.default


def _reg_text(value: Value) -> str:
    if not isinstance(value, int) or not 0 <= value < 1000:
        raise _Unrepresentable
    return f"r{value}"


def generic_source(entry: Entry) -> str:
    args = [str(entry.op)]
    for slot in SLOTS:
        value = getattr(entry, slot)
        if value != 0:
            args.append(f"{slot}={format_value(value, 'any')}")
    return f"op({', '.join(args)})"


def entry_source(entry: Entry, previous: Optional[Entry] = None) -> str:
    """One entry as one line of readable source."""
    try:
        text = _structured(entry, previous)
        if _parse_line(text) != _normalised(entry):
            raise _Unrepresentable
    except (_Unrepresentable, _Error, ValueError):
        return generic_source(entry)
    return text


def _normalised(entry: Entry) -> Entry:
    def norm(v):
        return v & U32 if isinstance(v, int) and not isinstance(v, bool) else v
    return Entry(_signed(entry.op) if isinstance(entry.op, int) else entry.op,
                 *(norm(getattr(entry, s)) for s in SLOTS))


def decompile(script: Script, kind: str = "") -> str:
    """A script as readable source, one line per entry."""
    title = f"{kind} script, " if kind else ""
    lines = [f"# {script.name} - {title}id {script.script_id}"]
    lines += entry_lines(script.entries)
    return "\n".join(lines) + "\n"


def entry_lines(entries: list[Entry]) -> list[str]:
    """One source line per entry. A COMPARE reads result code names when the
    last non-COMPARE entry before it leaves codes in r0."""
    lines, context = [], None
    for entry in entries:
        lines.append(entry_source(entry, context))
        if entry.op != 1:
            context = entry
    return lines


# -- compile ---------------------------------------------------------------------------------

@dataclass
class Diagnostic:
    line: int
    severity: str  # "error" / "warning"
    message: str

    def __str__(self) -> str:
        return f"line {self.line}: {self.severity}: {self.message}" if self.line else f"{self.severity}: {self.message}"


@dataclass
class Names:
    """Known names, for checking what a script refers to. Empty sets are not checked."""

    pids: set = dataclass_field(default_factory=set)
    jids: set = dataclass_field(default_factory=set)
    iids: set = dataclass_field(default_factory=set)
    sids: set = dataclass_field(default_factory=set)
    attack_scripts: set = dataclass_field(default_factory=set)
    move_scripts: set = dataclass_field(default_factory=set)
    sections: set = dataclass_field(default_factory=set)  # every section of the file


@dataclass
class CompileResult:
    entries: list[Entry]
    lines: list[int]  # source line of each entry
    diagnostics: list[Diagnostic]

    @property
    def errors(self) -> list[Diagnostic]:
        return [d for d in self.diagnostics if d.severity == "error"]

    @property
    def ok(self) -> bool:
        return not self.errors


class _Error(Exception):
    pass


@dataclass
class _Tok:
    kind: str  # num, str, ident, label, ref
    text: str
    value: object = None


def _strip_comment(line: str) -> str:
    quoted = False
    i = 0
    while i < len(line):
        ch = line[i]
        if ch == "\\" and quoted:
            i += 2
            continue
        if ch == '"':
            quoted = not quoted
        elif ch == "#" and not quoted:
            return line[:i]
        i += 1
    return line


def _split_args(text: str) -> list[str]:
    parts, depth, quoted, current, i = [], 0, False, "", 0
    while i < len(text):
        ch = text[i]
        if quoted:
            current += ch
            if ch == "\\" and i + 1 < len(text):
                current += text[i + 1]
                i += 2
                continue
            if ch == '"':
                quoted = False
        elif ch == '"':
            quoted = True
            current += ch
        elif ch == "(":
            depth += 1
            current += ch
        elif ch == ")":
            depth -= 1
            current += ch
        elif ch == "," and depth == 0:
            parts.append(current.strip())
            current = ""
        else:
            current += ch
        i += 1
    if quoted:
        raise _Error("unterminated string")
    if current.strip() or parts:
        parts.append(current.strip())
    if any(not p for p in parts):
        raise _Error("empty argument")
    return parts


def _token(text: str) -> _Tok:
    text = text.strip()
    if not text:
        raise _Error("missing value")
    if text.startswith('"'):
        if len(text) < 2 or not text.endswith('"'):
            raise _Error(f"bad string {text}")
        body = text[1:-1]
        return _Tok("str", text, re.sub(r"\\(.)", r"\1", body))
    m = re.fullmatch(r"ref\((.*)\)", text)
    if m:
        inner = _token(m.group(1))
        if inner.kind not in ("str", "ident"):
            raise _Error(f"ref() takes a name, not {m.group(1)}")
        return _Tok("ref", text, inner.value)
    if _NUMBER.match(text):
        if re.fullmatch(r"[-+]?0[xX][0-9a-fA-F]+", text):
            return _Tok("num", text, int(text, 16))
        if "." in text:
            return _Tok("num", text, float(text))
        return _Tok("num", text, int(text))
    if re.fullmatch(r"L\d+", text):
        return _Tok("label", text, int(text[1:]))
    if _IDENT.match(text):
        return _Tok("ident", text, text)
    raise _Error(f"can't read the value '{text}'")


def _as_int(tok: _Tok, what: str) -> int:
    if tok.kind == "num" and isinstance(tok.value, int):
        return tok.value & U32
    if tok.kind == "ident" and tok.text in ("True", "False"):
        return int(tok.text == "True")
    raise _Error(f"{what} must be a whole number, not {tok.text}")


def _convert(tok: _Tok, kind: str, what: str) -> Value:
    if kind in ("int", "percent"):
        if tok.kind == "ident" and tok.text in RESULT_NAMES:
            return RESULT_NAMES[tok.text]
        return _as_int(tok, what)
    if kind == "bool":
        if tok.kind == "ident" and tok.text in ("True", "False"):
            return int(tok.text == "True")
        return _as_int(tok, what)
    if kind == "label":
        if tok.kind == "label":
            return tok.value
        if tok.kind == "ident" and tok.text == "start":
            return 0
        if tok.kind == "num" and isinstance(tok.value, int):
            return tok.value & U32
        raise _Error(f"{what} must be a label (L1, start), not {tok.text}")
    if kind == "fixed":
        if tok.kind == "num":
            return round(tok.value * 65536) & U32
        raise _Error(f"{what} must be a number such as 1.5, not {tok.text}")
    if kind in NAME_KINDS:
        if tok.kind == "ident" and tok.text == "None":
            return 0
        if tok.kind in ("ident", "str") and tok.text not in ("True", "False"):
            return tok.value
        raise _Error(f"{what} must be a name, not {tok.text}")
    if kind in TABLE_KINDS:
        if tok.kind == "ident" and tok.text == "None":
            return 0
        if tok.kind in ("ident", "str", "ref") and tok.text not in ("True", "False"):
            return SectionRef(tok.value)
        raise _Error(f"{what} must be a table name, not {tok.text}")
    # any
    if tok.kind == "ref":
        return SectionRef(tok.value)
    if tok.kind == "str":
        return tok.value
    if tok.kind == "label":
        return tok.value
    if tok.kind == "num":
        if not isinstance(tok.value, int):
            raise _Error(f"{what} must be a whole number")
        return tok.value & U32
    if tok.text in ("True", "False"):
        return int(tok.text == "True")
    if tok.text == "None":
        return 0
    return SectionRef(tok.text) if tok.text.startswith("TBL_") else tok.text


def _threat_value(tok: _Tok) -> int:
    if tok.kind == "ident" and tok.text == "none":
        return NO_LIMIT
    if tok.kind == "ident" and tok.text == "keep":
        return 0
    return _as_int(tok, "threat_limit")


def _parse_call(text: str) -> tuple[str, list[str]]:
    m = re.fullmatch(r"([A-Za-z_]\w*)\s*\((.*)\)", text, re.S)
    if not m:
        raise _Error(f"can't read '{text}'")
    return m.group(1), _split_args(m.group(2))


def _keywords(args: list[str], positional_ok: int = 0) -> tuple[list[str], dict[str, str]]:
    positional, keywords = [], {}
    for arg in args:
        m = re.fullmatch(r"([A-Za-z_]\w*)\s*=\s*(.+)", arg, re.S)
        if m:
            if m.group(1) in keywords:
                raise _Error(f"{m.group(1)} is given twice")
            keywords[m.group(1)] = m.group(2)
        else:
            if keywords or len(positional) >= positional_ok:
                raise _Error(f"'{arg}': use name=value")
            positional.append(arg)
    return positional, keywords


def _build_call(spec: OpSpec, args: list[str], reg: Optional[int]) -> Entry:
    _, keywords = _keywords(args)
    words: dict[str, Value] = {s: 0 for s in SLOTS}
    words["b"] = spec.b_default
    by_name = {f.name: f for f in spec.fields if not (spec.form == "assign" and f.slot == "a")}
    for name, text in keywords.items():
        if name == "threat_limit" and not spec.uses_b:
            words["b"] = _threat_value(_token(text))
            continue
        f = by_name.get(name)
        if f is None:
            known = ", ".join(list(by_name) + ([] if spec.uses_b else ["threat_limit"])) or "nothing"
            raise _Error(f"{spec.name}() has no '{name}' (it takes {known})")
        words[f.slot] = _convert(_token(text), f.kind, name)
    for f in spec.fields:
        if f.default is None and f.name in by_name and f.name not in keywords:
            raise _Error(f"{spec.name}() needs {f.name}=")
        if f.default not in (None, 0, False) and f.name not in keywords:
            words[f.slot] = _raw_default(f)
    if spec.form == "assign":
        words["a"] = reg if reg is not None else 0
    elif reg is not None:
        raise _Error(f"{spec.name}() doesn't write a register")
    return Entry(spec.op, *(words[s] for s in SLOTS))


def _parse_line(text: str) -> Optional[Entry]:
    text = text.strip()
    if not text:
        return None
    m = re.fullmatch(r"L(\d+)\s*:", text)
    if m:
        return Entry(0, 0, OPS[0].b_default, int(m.group(1)))
    m = re.fullmatch(r"goto\s+(\S+)", text)
    if m:
        return Entry(4, 0, OPS[4].b_default, 0, _convert(_token(m.group(1)), "label", "goto"))
    m = re.fullmatch(r"if\s+(not\s+)?found\s*:\s*goto\s+(\S+)", text)
    if m:
        return Entry(6, 0 if m.group(1) else 1, OPS[6].b_default, 0, _convert(_token(m.group(2)), "label", "goto"))
    m = re.fullmatch(r"if\s+r(\d+)\s*(==|!=|>=|<=|>|<)\s*(.+?)\s*:\s*goto\s+(\S+)", text)
    if m:
        value = _convert(_token(m.group(3)), "int", "the compared value")
        return Entry(1, int(m.group(1)), COMPARISON_CODES[m.group(2)], value, _convert(_token(m.group(4)), "label", "goto"))
    if text.startswith("if "):
        raise _Error("write 'if found: goto L1', 'if not found: goto L1' or 'if r0 == 1: goto L1'")
    reg = None
    m = re.fullmatch(r"r(\d+)\s*=\s*(.+)", text, re.S)
    if m:
        reg, text = int(m.group(1)), m.group(2).strip()
    name, args = _parse_call(text)
    if name == "op":
        if reg is not None:
            raise _Error("op(...) can't be assigned")
        positional, keywords = _keywords(args, positional_ok=1)
        if not positional:
            raise _Error("op() needs the opcode first: op(101, a=100)")
        op = _signed(_as_int(_token(positional[0]), "the opcode"))
        words = {s: 0 for s in SLOTS}
        for key, value in keywords.items():
            if key not in SLOTS:
                raise _Error(f"op() takes a, b, c, d, e, f - not {key}")
            words[key] = _convert(_token(value), "any", key)
        return Entry(op, *(words[s] for s in SLOTS))
    spec = BY_NAME.get(name)
    if spec is None:
        raise _Error(f"unknown function {name}()")
    if spec.form not in ("call", "assign"):
        raise _Error(f"write {spec.name} as a statement, not a call")
    if spec.form == "assign" and reg is None:
        raise _Error(f"{name}() writes a register: write r0 = {name}(...)")
    return _build_call(spec, args, reg)


def compile_source(source: str, names: Optional[Names] = None,
                   fallthrough: Optional[dict[int, str]] = None, check: bool = True) -> CompileResult:
    """Readable source -> script entries (without the two header entries).
    ``fallthrough`` maps the labels the game would find past the end of the
    script (see :func:`fallthrough_labels`) to the section holding them."""
    entries, lines, diagnostics = [], [], []
    for number, raw in enumerate(source.splitlines(), 1):
        try:
            entry = _parse_line(_strip_comment(raw))
        except _Error as exc:
            diagnostics.append(Diagnostic(number, "error", str(exc)))
            continue
        except (ValueError, OverflowError) as exc:
            diagnostics.append(Diagnostic(number, "error", str(exc)))
            continue
        if entry is not None:
            entries.append(entry)
            lines.append(number)
    if check:
        diagnostics += check_entries(entries, lines, names, fallthrough)
    diagnostics.sort(key=lambda d: (d.line, d.severity != "error"))
    return CompileResult(entries, lines, diagnostics)


def _jump_targets(entry: Entry) -> list[int]:
    if entry.op in (1, 4, 6, 1000, 1001) and isinstance(entry.d, int) and entry.d != 0:
        return [entry.d]
    return []


def check_entries(entries: list[Entry], lines: Optional[list[int]] = None,
                  names: Optional[Names] = None, fallthrough: Optional[dict[int, str]] = None) -> list[Diagnostic]:
    """Problems the game would trip on, and suspicious values."""
    lines = lines or [0] * len(entries)
    out: list[Diagnostic] = []
    if not entries:
        return [Diagnostic(0, "error", "the script has no entries")]
    if len(entries) + 2 > 256:
        out.append(Diagnostic(lines[255 - 2] if len(lines) > 253 else 0, "error",
                              f"{len(entries)} entries: the game's entry counter is one byte, so a script holds "
                              "at most 254 entries after its header"))
    labels: dict[int, int] = {}
    for entry, line in zip(entries, lines):
        if entry.op == 0 and isinstance(entry.c, int):
            if entry.c in labels:
                out.append(Diagnostic(line, "warning", f"label L{entry.c} is defined twice; jumps go to the first one"))
            else:
                labels[entry.c] = line
    for entry, line in zip(entries, lines):
        spec = OPS.get(entry.op)
        if entry.op not in HANDLED_OPS:
            out.append(Diagnostic(line, "error", f"opcode {entry.op} has no handler in the game"))
            continue
        if spec.form == "header":
            out.append(Diagnostic(line, "error", f"opcode {entry.op} only belongs in the script header"))
        for target in _jump_targets(entry):
            if target not in labels and fallthrough and target in fallthrough:
                out.append(Diagnostic(line, "warning", f"label L{target} isn't in this script: the game finds it "
                                                       f"in {fallthrough[target]}, which follows in the file, and "
                                                       "runs that code"))
            elif target not in labels:
                out.append(Diagnostic(line, "error", f"label L{target} doesn't exist: the game would run off the "
                                                     "end of the script looking for it"))
        out += _check_fields(entry, spec, line, names)
    last = entries[-1]
    if last.op not in _ENDINGS:
        out.append(Diagnostic(lines[-1], "warning", "the script doesn't end with end(), stop() or goto: the game "
                                                     "goes on into whatever section follows it in the file"))
    return out


def _check_fields(entry: Entry, spec: OpSpec, line: int, names: Optional[Names]) -> list[Diagnostic]:
    out = []
    for f in spec.fields:
        value = getattr(entry, f.slot)
        if f.kind == "percent" and isinstance(value, int) and not 0 <= _signed(value) <= 100:
            out.append(Diagnostic(line, "warning", f"{f.name} {_signed(value)} is outside 0-100"))
        if f.kind == "reg" and isinstance(value, int) and value >= REGISTER_COUNT:
            out.append(Diagnostic(line, "warning", f"r{value} is outside the {REGISTER_COUNT} registers"))
        if names is None or value == 0:
            continue
        name = value.name if isinstance(value, SectionRef) else value
        if isinstance(value, SectionRef) and names.sections and name not in names.sections:
            out.append(Diagnostic(line, "error", f"there is no table {name} in the file"))
            continue
        known = {"pid": names.pids, "jid": names.jids, "iid": names.iids, "sid": names.sids}.get(f.kind)
        if known and isinstance(name, str) and name not in known:
            out.append(Diagnostic(line, "warning", f"{name} is not a known {f.kind.upper()}"))
        if f.kind == "seq" and spec.op == 3 and isinstance(name, str):
            pool = names.attack_scripts if f.name == "attack" else names.move_scripts
            if (names.attack_scripts or names.move_scripts) and name not in pool:
                other = names.move_scripts if f.name == "attack" else names.attack_scripts
                why = f"is a {'move' if f.name == 'attack' else 'attack'} script" if name in other else "doesn't exist"
                out.append(Diagnostic(line, "error", f"{name} {why}; {f.name}= needs an {f.name} script"))
    return out


# -- editor helpers --------------------------------------------------------------------------

def parse_field_text(text: str, kind: str = "any") -> Value:
    """One field typed in a form: empty = 0, a number, or a name read as ``kind``
    wants it (a table pointer or a label string). Raises ValueError."""
    text = text.strip()
    if not text:
        return 0
    try:
        tok = _token(text)
        if kind in ("int", "percent", "bool", "label", "reg", "cmp", "fixed") and tok.kind == "num" \
                and isinstance(tok.value, int):
            return tok.value & U32
        if kind in ("reg", "cmp"):
            kind = "int"
        if kind == "fixed" and tok.kind == "num" and isinstance(tok.value, float):
            return _convert(tok, "fixed", "value")
        return _convert(tok, kind if kind != "fixed" else "int", "value")
    except _Error as exc:
        raise ValueError(str(exc)) from None


def field_text(value: Value) -> str:
    """A raw field for a form: numbers as numbers, names as names."""
    if isinstance(value, SectionRef):
        return value.name
    if isinstance(value, str):
        return value
    return _hex_or_int(value)


def signature(name: str) -> Optional[str]:
    spec = BY_NAME.get(name)
    if name == "op":
        return "op(opcode, a=, b=, c=, d=, e=, f=)  - any entry, word by word"
    if spec is None or spec.form not in ("call", "assign"):
        return None
    params = []
    for f in spec.fields:
        if spec.form == "assign" and f.slot == "a":
            continue
        params.append(f.name if f.default is None else f"{f.name}={format_value(_raw_default(f), f.kind)}")
    if not spec.uses_b:
        params.append("threat_limit=" + _threat_text(spec.b_default))
    prefix = "rN = " if spec.form == "assign" else ""
    return f"{prefix}{spec.name}({', '.join(params)})  - {spec.summary}"


def function_names() -> list[str]:
    return sorted(n for n, s in BY_NAME.items() if s.form in ("call", "assign")) + ["op"]


def statement_templates() -> list[tuple[str, str]]:
    """(label, text) pairs for an 'insert' menu."""
    out = [("label", "L1:"), ("goto", "goto L1"), ("if found", "if found: goto L1"),
           ("if not found", "if not found: goto L1"), ("compare", "if r0 == 0: goto L1")]
    for name in function_names():
        if name == "op":
            continue
        spec = BY_NAME[name]
        required = [f"{f.name}=" for f in spec.fields if f.default is None and not (spec.form == "assign" and f.slot == "a")]
        call = f"{name}({', '.join(required)})"
        out.append((name, f"r0 = {call}" if spec.form == "assign" else call))
    return out


def field_kind_at(name: str, keyword: str) -> Optional[str]:
    spec = BY_NAME.get(name)
    if spec is None:
        return None
    for f in spec.fields:
        if f.name == keyword:
            return f.kind
    return None


def fallthrough_labels(sections: list, script_name: str, limit: int = 0x100) -> dict[int, str]:
    """Labels the game's label search would find after the end of the script
    ``script_name``: it reads on, entry by entry, through the sections that
    follow it in the file. ``sections`` is the document's section list."""
    names = [s.name for s in sections]
    if script_name not in names:
        return {}
    index = names.index(script_name)
    found: dict[int, str] = {}
    words, owners = [], []
    for section in sections[index + 1:]:
        words += section.words
        owners += [section.name] * len(section.words)
        if len(words) >= 7 * limit:
            break
    start = len(sections[index].words) % 7  # entries stay 7-word aligned from the script's start
    start = (7 - start) % 7
    for i in range(start, len(words) - 6, 7):
        if words[i] == 0 and isinstance(words[i + 3], int) and words[i + 3] not in found:
            found[words[i + 3]] = owners[i]
    return found


def roundtrip_problems(scripts: Iterable[Script]) -> list[str]:
    """Scripts whose readable source doesn't compile back to the same entries."""
    problems = []
    for script in scripts:
        result = compile_source(decompile(script), check=False)
        if result.errors or result.entries != [_normalised(e) for e in script.entries]:
            problems.append(script.name)
    return problems
