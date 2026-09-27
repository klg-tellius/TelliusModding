"""The map zones of a chapter script: the functions triggered by a unit
entering a zone (``@on_area``, type 4) or acting on a tile
(``@on_location``, type 5). The Build tab draws them on the map and edits
them through these helpers, which - like :mod:`.source_tools` - are pure
functions over ``.fe9s`` source text (no Tk).

Deleting a zone removes its function when the function does nothing
(its body is only ``pass``) and nothing else refers to it; otherwise the
function stays, without its trigger, and its description starts with
:data:`UNUSED_MARK` and the trigger it had, so the code is kept and the zone
can be put back. Such a function can be given a new zone later, which
drops the mark."""

from __future__ import annotations

import dataclasses
import re
from dataclasses import dataclass
from typing import Optional

from . import ast as A
from . import source_tools as st
from .catalog import ACTIONS, SIDES, SPECIAL_ENTRY_POINTS, TRIGGERS
from .parser import parse

AREA, LOCATION = 4, 5
ZONE_TYPES = (AREA, LOCATION)
UNUSED_MARK = "UNUSED"
_UNUSED_LINE = re.compile(rf"^{UNUSED_MARK}\b")


@dataclass
class MapZone:
    """One zone-triggered function. ``rect`` is (x1, y1, x2, y2), inclusive
    and ordered; a location's rect is its one tile. ``mode`` is the side
    (area) or the action (location), as its name when it has one."""

    function: str
    type: int
    rect: tuple
    mode: object
    label: object  # the trigger's ``name`` (a flag/debug label) or None
    description: str = ""
    export_id: Optional[str] = None

    @property
    def is_area(self) -> bool:
        return self.type == AREA

    def contains(self, tile) -> bool:
        x1, y1, x2, y2 = self.rect
        return x1 <= tile[0] <= x2 and y1 <= tile[1] <= y2

    def trigger_text(self) -> str:
        """The decorator this zone compiles to."""
        return decorator(self.type, self.rect, self.mode, self.label)


def _trigger_values(span: st.FunctionSpan) -> Optional[dict]:
    """The zone trigger's parameters by name, raw ``@trigger(4, ...)`` form included."""
    if span.trigger_type not in ZONE_TYPES:
        return None
    kind = TRIGGERS[span.trigger_type]
    if span.raw_params is None:
        values = dict(span.trigger_values)
    elif len(span.raw_params) != len(kind.params):
        return None
    else:
        values = dict(zip((p.name for p in kind.params), span.raw_params))
        key = "side" if span.trigger_type == AREA else "action"
        values[key] = (SIDES if span.trigger_type == AREA else ACTIONS).get(values[key], values[key])
    if values.get("name") == 0:
        values["name"] = None  # a label of 0 is "no value" (the parser reads None as 0)
    return values


def _zone(span: st.FunctionSpan) -> Optional[MapZone]:
    values = _trigger_values(span)
    if values is None:
        return None
    if span.trigger_type == AREA:
        coords = [values.get(k) for k in ("x1", "y1", "x2", "y2")]
        mode = values.get("side")
    else:
        coords = [values.get("x"), values.get("y")] * 2
        mode = values.get("action")
    if not all(isinstance(c, int) for c in coords):
        return None
    x1, y1, x2, y2 = coords
    rect = (min(x1, x2), min(y1, y2), max(x1, x2), max(y1, y2))
    return MapZone(span.name, span.trigger_type, rect, mode, values.get("name"), span.description, span.export_id)


def zones(source: str) -> list[MapZone]:
    """Every zone of the script, in function order. Raises ParseError."""
    return [z for z in map(_zone, st.function_spans(source)) if z is not None]


def decorator(trigger_type: int, rect, mode, label) -> str:
    x1, y1, x2, y2 = rect
    if trigger_type == AREA:
        values = {"x1": x1, "y1": y1, "x2": x2, "y2": y2, "side": mode, "name": label}
    else:
        values = {"x": x1, "y": y1, "action": mode, "name": label}
    return st.decorator_source(None, "", trigger_type, values)[0]


def _span(source: str, name: str) -> st.FunctionSpan:
    for span in st.function_spans(source):
        if span.name == name:
            return span
    raise KeyError(f"No function named {name!r}.")


def _function(module: A.Module, name: str) -> A.FuncDef:
    return next(fd for fd in module.functions if fd.name == name)


def _walk(node):
    """Every syntax node below ``node`` (lists and dataclasses)."""
    if isinstance(node, list):
        for item in node:
            yield from _walk(item)
    elif dataclasses.is_dataclass(node) and not isinstance(node, type):
        yield node
        for f in dataclasses.fields(node):
            yield from _walk(getattr(node, f.name))
    elif isinstance(node, tuple):
        for item in node:
            yield from _walk(item)


def is_empty(source: str, name: str) -> bool:
    """Whether function ``name`` does nothing: no statement but ``pass``
    (a final ``return`` of nothing or 0 counts as nothing too)."""
    body = _function(parse(source), name).body
    for stmt in body:
        if isinstance(stmt, A.Pass):
            continue
        if isinstance(stmt, A.Return) and (stmt.value is None or stmt.value == A.Num(0)):
            continue
        return False
    return True


def is_referenced(source: str, name: str) -> bool:
    """Whether another function calls ``name`` (or names it in ``asm``)."""
    for fd in parse(source).functions:
        if fd.name == name:
            continue
        for node in _walk(fd.body):
            if isinstance(node, A.Call) and node.name == name and not node.extern:
                return True
            if isinstance(node, A.Asm) and any(op == name for line in node.lines for op in line[1]):
                return True
    return False


def is_unused(description: str) -> bool:
    return any(_UNUSED_LINE.match(line) for line in description.splitlines())


def _without_unused_mark(description: str) -> str:
    return "\n".join(line for line in description.splitlines() if not _UNUSED_LINE.match(line))


def _decorators(source: str, span: st.FunctionSpan, trigger: Optional[str]) -> list[str]:
    """The span's decorators with ``trigger`` in place of its trigger
    (``@export`` and ``@naked`` are kept as written)."""
    lines = source.splitlines()
    kept = [lines[ln - 1].strip() for ln in span.decorator_lines
            if re.match(r"@(export|naked)\b", lines[ln - 1].strip())]
    return kept + ([trigger] if trigger else [])


def unique_label(source: str, base: str) -> str:
    """A trigger/flag label no string in the script uses yet."""
    taken = set(re.findall(r'"([^"\\\n]*)"', source))
    if base not in taken:
        return base
    n = 2
    while f"{base}_{n}" in taken:
        n += 1
    return f"{base}_{n}"


def add_zone(source: str, trigger_type: int, rect, mode, label, function: Optional[str] = None,
             name: str = "zone_event", description: str = "") -> tuple[str, str]:
    """Add a zone. With ``function`` that function gets the zone's trigger
    (replacing any trigger it had, keeping its export, dropping an
    :data:`UNUSED_MARK`); otherwise a new function ``name`` (made unique) is
    appended. Returns (new source, the function's name)."""
    trigger = decorator(trigger_type, rect, mode, label)
    if function is not None:
        span = _span(source, function)
        text = _without_unused_mark(span.description)
        if description:
            text = description + ("\n" + text if text else "")
        return st.replace_decorators(source, span, _decorators(source, span, trigger), description=text), function
    name = st.unique_name(source, name)
    block = [f"# {line}" for line in description.splitlines()] + [trigger, f"def {name}():", "    pass"]
    return source.rstrip("\n") + "\n\n\n" + "\n".join(block) + "\n", name


def update_zone(source: str, function: str, rect=None, mode=None, label=..., trigger_type: Optional[int] = None,
                new_name: Optional[str] = None, description: Optional[str] = None) -> str:
    """Change a zone's trigger (tiles, side/action, label, kind) and its
    function's name or description; arguments left out keep their value.
    Renaming also renames the calls to it."""
    span = _span(source, function)
    zone = _zone(span)
    if zone is None:
        raise ValueError(f"{function} isn't triggered by a map zone.")
    trigger_type = zone.type if trigger_type is None else trigger_type
    if mode is None:
        mode = zone.mode if trigger_type == zone.type else ("player" if trigger_type == AREA else "visit")
    rect = zone.rect if rect is None else rect
    if trigger_type == LOCATION:
        rect = (rect[0], rect[1], rect[0], rect[1])
    label = zone.label if label is ... else label
    trigger = decorator(trigger_type, rect, mode, label)
    if new_name == function:
        new_name = None
    if new_name is not None:
        if not st.parser_identifier(new_name):
            raise ValueError(f"{new_name!r} isn't a valid function name.")
        if any(s.name == new_name for s in st.function_spans(source)):
            raise ValueError(f"There is already a function named {new_name!r}.")
    return st.replace_decorators(source, span, _decorators(source, span, trigger), new_name, description)


def delete_zone(source: str, function: str) -> tuple[str, str]:
    """Remove a zone. An empty function nothing refers to (not exported, not
    called) is deleted; any other loses its trigger and is marked unused.
    Returns (new source, "deleted" or "unused")."""
    span = _span(source, function)
    zone = _zone(span)
    if zone is None:
        raise ValueError(f"{function} isn't triggered by a map zone.")
    if span.export_id is None and is_empty(source, function) and not is_referenced(source, function):
        return st.delete_function_source(source, span), "deleted"
    old = _without_unused_mark(span.description)
    mark = f"{UNUSED_MARK}: its map zone was deleted (was {zone.trigger_text()})"
    return st.replace_decorators(source, span, _decorators(source, span, None),
                                 description=mark + ("\n" + old if old else "")), "unused"


def unused_trigger(description: str) -> Optional[str]:
    """The trigger an unused function had, from its mark (None if unknown)."""
    for line in description.splitlines():
        match = re.match(rf"^{UNUSED_MARK}\b.*\(was (@.*)\)\s*$", line)
        if match:
            return match.group(1)
    return None


def attachable_functions(source: str) -> list[tuple[str, bool]]:
    """Functions a new zone can be given: the ones without a trigger, as
    (name, marked unused), the unused ones first. Raises ParseError."""
    spans = [s for s in st.function_spans(source)
             if s.trigger_type == 0 and not s.raw_params and s.export_id not in SPECIAL_ENTRY_POINTS]
    found = [(s.name, is_unused(s.description)) for s in spans]
    return sorted(found, key=lambda item: not item[1])
