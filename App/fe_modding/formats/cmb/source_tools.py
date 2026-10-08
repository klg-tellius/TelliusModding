"""Text-level helpers the script editor uses to edit ``.fe9s`` source:
locate each function, rewrite its decorators from a form, add/duplicate/
delete/rename functions. Pure functions over source text (no Tk)."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional

from . import ast as A
from .catalog import triggers, triggers_by_decorator
from .decompiler import is_identifier, quote
from .parser import parse


@dataclass
class FunctionSpan:
    name: str
    first_line: int  # first line of the function's block (leading comments/decorators), 1-based
    def_line: int
    last_line: int
    params: list
    export_id: Optional[str] = None
    trigger_type: int = 0
    trigger_values: dict = field(default_factory=dict)  # param name -> int | str | None
    raw_params: Optional[list] = None  # set for @trigger(type, ...) raw form
    decorator_lines: list = field(default_factory=list)
    description: str = ""  # the user's comment lines above the function (not the decompiler's "function N" one)


# The comment the decompiler writes above each function ("function 3 - A unit enters a zone");
# it isn't part of a function's description.
_AUTO_COMMENT = re.compile(r"^function \d+( - .*)?$")


def _comment_text(line: str) -> Optional[str]:
    """The text of a ``# ...`` line, or None for any other line."""
    stripped = line.strip()
    return stripped[1:].strip() if stripped.startswith("#") else None


def _is_description_line(line: str) -> bool:
    text = _comment_text(line)
    return text is not None and not _AUTO_COMMENT.match(text)


def parser_identifier(name: str) -> bool:
    """Whether ``name`` can be a function or variable name."""
    return is_identifier(name)


def _const(e):
    if isinstance(e, A.Num):
        return e.value
    if isinstance(e, A.UnOp) and e.op == "-" and isinstance(e.operand, A.Num):
        return -e.operand.value
    if isinstance(e, A.Str):
        return e.value
    if isinstance(e, A.Name) and e.id == "None":
        return None
    return None


def function_spans(source: str, dialect="fe9") -> list[FunctionSpan]:
    """Raises ParseError when the source doesn't parse. ``dialect``: the
    script's game (its trigger kinds), a Dialect or its name."""
    module = parse(source)
    lines = source.splitlines()
    spans = []
    for fd in module.functions:
        first = min([d.line for d in fd.decorators] + [fd.line])
        while first > 1 and lines[first - 2].lstrip().startswith("#"):
            first -= 1
        span = FunctionSpan(fd.name, first, fd.line, fd.line, list(fd.params),
                            decorator_lines=[d.line for d in fd.decorators])
        span.description = "\n".join(_comment_text(lines[ln - 1]) for ln in range(first, fd.line)
                                     if ln not in span.decorator_lines and _is_description_line(lines[ln - 1]))
        for d in fd.decorators:
            if d.name == "export":
                span.export_id = d.args[0].value if d.args and isinstance(d.args[0], A.Str) else fd.name
            elif d.name == "trigger":
                values = [_const(a) for a in d.args]
                span.trigger_type = values[0] if values else 0
                span.raw_params = values[1:]
            elif d.name in triggers_by_decorator(dialect):
                kind = triggers_by_decorator(dialect)[d.name]
                span.trigger_type = kind.type
                for i, spec in enumerate(kind.params):
                    if i < len(d.args):
                        span.trigger_values[spec.name] = _const(d.args[i])
                    elif spec.name in d.kwargs:
                        span.trigger_values[spec.name] = _const(d.kwargs[spec.name])
        spans.append(span)
    for i, span in enumerate(spans):
        last = spans[i + 1].first_line - 1 if i + 1 < len(spans) else len(lines)
        while last > span.def_line and not lines[last - 1].strip():
            last -= 1
        span.last_line = last
    return spans


def value_source(value) -> str:
    if value is None:
        return "None"
    if isinstance(value, str):
        return quote(value)
    return str(value)


def decorator_source(export_id: Optional[str], def_name: str, trigger_type: int, values: dict,
                     raw_params: Optional[list] = None, dialect="fe9") -> list[str]:
    lines = []
    if export_id:
        lines.append("@export" if export_id == def_name else f"@export({quote(export_id)})")
    kind = triggers(dialect).get(trigger_type)
    if raw_params is not None or kind is None:
        params = raw_params or []
        if trigger_type or params:
            lines.append(f"@trigger({', '.join(str(v) for v in [trigger_type] + list(params))})")
    elif kind.decorator:
        args = [f"{spec.name}={value_source(values.get(spec.name, 0))}" for spec in kind.params]
        lines.append(f"@{kind.decorator}({', '.join(args)})")
    return lines


def replace_decorators(source: str, span: FunctionSpan, new_decorators: list[str], new_name: Optional[str] = None,
                       description: Optional[str] = None) -> str:
    """Rewrite the function's decorators (and name). A ``description`` (None: leave
    as is) replaces the user comment lines above it, one ``# `` line per text line."""
    lines = source.splitlines()
    keep = [ln for ln in range(span.first_line, span.def_line) if ln not in span.decorator_lines]
    head = [lines[ln - 1] for ln in keep]
    if description is not None:
        head = [ln for ln in head if not _is_description_line(ln)]
        head += [f"# {text.strip()}" if text.strip() else "#" for text in description.strip().splitlines()]
    def_text = lines[span.def_line - 1]
    if new_name and new_name != span.name:
        def_text = re.sub(rf"\bdef\s+{re.escape(span.name)}\b", f"def {new_name}", def_text, count=1)
    block = head + new_decorators + [def_text]
    lines[span.first_line - 1:span.def_line] = block
    text = "\n".join(lines) + "\n"
    if new_name and new_name != span.name:
        text = rename_calls(text, span.name, new_name)
    return text


def rename_calls(source: str, old: str, new: str) -> str:
    """Rename local calls ``old(`` -> ``new(`` outside strings and comments."""
    out = []
    pattern = re.compile(rf"(?<![\w.\"]){re.escape(old)}(?=\s*\()")
    for line in source.splitlines(keepends=True):
        code, comment = _split_comment(line)
        parts = re.split(r'("(?:[^"\\\n]|\\.)*")', code)
        parts = [p if p.startswith('"') else pattern.sub(new, p) for p in parts]
        out.append("".join(parts) + comment)
    return "".join(out)


def _split_comment(line: str) -> tuple[str, str]:
    in_str = False
    i = 0
    while i < len(line):
        ch = line[i]
        if ch == "\\" and in_str:
            i += 2
            continue
        if ch == '"':
            in_str = not in_str
        elif ch == "#" and not in_str:
            return line[:i], line[i:]
        i += 1
    return line, ""


def unique_name(source: str, base: str) -> str:
    taken = set(re.findall(r"\bdef\s+(\w+)", source))
    if base not in taken:
        return base
    n = 2
    while f"{base}_{n}" in taken:
        n += 1
    return f"{base}_{n}"


def new_function_source(source: str, name: str = "new_event", trigger_type: int = 6,
                        dialect="fe9") -> tuple[str, str]:
    """Append a function; returns (new source, its name)."""
    name = unique_name(source, name)
    kind = triggers(dialect)[trigger_type]
    defaults = {spec.name: (None if spec.is_label else ("player" if spec.enum else 1)) for spec in kind.params}
    block = decorator_source(None, name, trigger_type, defaults, dialect=dialect) + [f"def {name}():", "    pass"]
    text = source.rstrip("\n") + "\n\n\n" + "\n".join(block) + "\n"
    return text, name


def duplicate_function_source(source: str, span: FunctionSpan) -> tuple[str, str]:
    lines = source.splitlines()
    name = unique_name(source, span.name + "_copy")
    block = lines[span.first_line - 1:span.last_line]
    rel_def = span.def_line - span.first_line
    block[rel_def] = re.sub(rf"\bdef\s+{re.escape(span.name)}\b", f"def {name}", block[rel_def], count=1)
    # a copy can't export the same global name
    block = [ln for i, ln in enumerate(block) if not (span.first_line + i in span.decorator_lines and ln.lstrip().startswith("@export"))]
    text = source.rstrip("\n") + "\n\n\n" + "\n".join(block) + "\n"
    return text, name


def delete_function_source(source: str, span: FunctionSpan) -> str:
    lines = source.splitlines()
    del lines[span.first_line - 1:span.last_line]
    return re.sub(r"\n{4,}", "\n\n\n", "\n".join(lines).rstrip("\n") + "\n")


@dataclass(frozen=True)
class StringReference:
    """A string literal passed to a call: ``call(..., "value", ...)`` on
    ``line`` of ``function``."""

    function: str
    line: int
    call: str
    value: str


def string_references(source: str) -> list[StringReference]:
    """Every string argument of every call, in source order - the Build
    tab's Disposition window uses it to find the functions that deploy a
    section (``Dispos("bmap02_first_n")``, ``DisposSetMode(...)``...).
    Raises ParseError."""
    found: list[StringReference] = []

    def visit(node, function: str, line: int) -> None:
        if isinstance(node, list):
            for item in node:
                visit(item, function, line)
            return
        if isinstance(node, tuple):
            for item in node:
                visit(item, function, line)
            return
        if not hasattr(node, "__dataclass_fields__") or isinstance(node, type):
            return
        if isinstance(node, A.Stmt) and node.line:
            line = node.line
        if isinstance(node, A.Call):
            name = node.name if isinstance(node.name, str) else f"<string {node.name.offset}>"
            for arg in node.args:
                if isinstance(arg, A.Str):
                    found.append(StringReference(function, line, name, arg.value))
        for name in node.__dataclass_fields__:
            visit(getattr(node, name), function, line)

    for fd in parse(source).functions:
        visit(fd.body, fd.name, fd.line)
    return found
