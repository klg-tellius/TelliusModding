"""Static rolling-rock bindings in a chapter's ``.fe9s`` source.

The visible prop is in map.bin.  A ``SetRock`` call creates its gameplay
terrain record, referring to a direction string registered by ``TTPMEntry``.
Only straight-line, literal calls can be edited here; other script code is
left intact for the Script tab.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from . import ast as A
from . import source_tools as st
from .parser import parse

INITIAL_STEPS = {1: (-1, 0), 2: (1, 0), 4: (0, 1), 8: (0, -1)}
PATH_STEPS = {"4": (-1, 0), "6": (1, 0), "2": (0, 1), "8": (0, -1)}
MAX_PATH_LENGTH = 31  # conservative limit for the game's unbounded strcpy into its motion state


@dataclass(frozen=True)
class RockRoute:
    function: str
    x: int
    y: int
    direction: int
    path: str | None
    set_line: int
    path_line: int | None
    path_variable: str | None
    editable: bool

    def tiles(self) -> list[tuple[int, int]]:
        """Rock tile, initial adjacent tile, then each route step."""
        points = [(self.x, self.y)]
        dx, dy = INITIAL_STEPS.get(self.direction, (0, 0))
        x, y = self.x + dx, self.y + dy
        points.append((x, y))
        for ch in self.path or "":
            dx, dy = PATH_STEPS.get(ch, (0, 0))
            x, y = x + dx, y + dy
            points.append((x, y))
        return points


def _number(value) -> int | None:
    if isinstance(value, A.Num):
        return value.value
    if isinstance(value, A.UnOp) and value.op == "-" and isinstance(value.operand, A.Num):
        return -value.operand.value
    return None


def _call(value, name: str) -> bool:
    return isinstance(value, A.Call) and value.name == name


def _simple_line(lines: list[str], line: int) -> bool:
    text, _comment = st._split_comment(lines[line - 1])
    return ";" not in text and bool(text.strip())


def routes(source: str) -> list[RockRoute]:
    """Find literal ``SetRock`` calls and their directly registered paths."""
    module = parse(source)
    lines = source.splitlines()
    found: list[RockRoute] = []
    for function in module.functions:
        slots: list[tuple[str | None, int | None, str | None]] = []
        named: dict[str, tuple[str | None, int | None, str | None]] = {}
        for stmt in function.body:
            value = None
            var = None
            if isinstance(stmt, A.VarInit):
                value, var = stmt.value, stmt.name
            elif isinstance(stmt, A.Assign) and isinstance(stmt.target, A.Name):
                value, var = stmt.value, stmt.target.id
            elif isinstance(stmt, A.ExprStmt):
                value = stmt.expr
            if _call(value, "TTPMInit"):
                slots.clear()
                named.clear()
            elif _call(value, "TTPMEntry"):
                path = value.args[0].value if len(value.args) == 1 and isinstance(value.args[0], A.Str) else None
                item = (path, stmt.line, var)
                slots.append(item)
                if var is not None:
                    named[var] = item
            elif _call(value, "SetRock") and len(value.args) == 4:
                x, y, direction = (_number(arg) for arg in value.args[:3])
                if None in (x, y, direction):
                    continue
                ref = value.args[3]
                path, path_line, path_var = None, None, None
                if isinstance(ref, A.Name):
                    path, path_line, path_var = named.get(ref.id, (None, None, None))
                elif isinstance(ref, A.Num) and 0 <= ref.value < len(slots):
                    path, path_line, path_var = slots[ref.value]
                elif _call(ref, "TTPMEntry") and len(ref.args) == 1 and isinstance(ref.args[0], A.Str):
                    path = ref.args[0].value
                found.append(RockRoute(function.name, x, y, direction, path, stmt.line, path_line, path_var,
                                       _simple_line(lines, stmt.line)))
    return found


def _validate(direction: int, path: str) -> None:
    if direction not in INITIAL_STEPS:
        raise ValueError("Initial direction must be left, right, down, or up.")
    if not path or len(path) > MAX_PATH_LENGTH or any(ch not in PATH_STEPS for ch in path):
        raise ValueError(f"The route needs 1–{MAX_PATH_LENGTH} steps using only 2, 4, 6, and 8.")


def _new_variable(source: str, x: int, y: int) -> str:
    base = f"rock_path_{x}_{y}"
    name = base
    n = 2
    while re.search(rf"\b{re.escape(name)}\b", source):
        name = f"{base}_{n}"
        n += 1
    return name


def _replace_line(lines: list[str], line: int, code: str) -> None:
    old = lines[line - 1]
    _body, comment = st._split_comment(old)
    indent = old[:len(old) - len(old.lstrip())]
    lines[line - 1] = indent + code + ("  " + comment.strip() if comment.strip() else "")


def set_route(source: str, x: int, y: int, direction: int, path: str) -> str:
    """Add or edit one rock without changing a path shared by other rocks."""
    _validate(direction, path)
    matching = [r for r in routes(source) if (r.x, r.y) == (x, y)]
    if len(matching) > 1:
        raise ValueError("Several SetRock calls use this tile; edit them in the Script tab.")
    lines = source.splitlines()
    if matching:
        route = matching[0]
        if not route.editable:
            raise ValueError("This SetRock call is not a standalone statement; edit it in the Script tab.")
        shared = route.path_line is not None and sum(r.path_line == route.path_line for r in routes(source)) > 1
        if route.path_line is not None and not shared and route.path is not None:
            old = lines[route.path_line - 1]
            pattern = r'TTPMEntry\s*\(\s*"(?:[^"\\]|\\.)*"\s*\)'
            new, count = re.subn(pattern, f"TTPMEntry({st.value_source(path)})", old, count=1)
            if count != 1:
                raise ValueError("The route registration needs editing in the Script tab.")
            lines[route.path_line - 1] = new
            ref = route.path_variable if route.path_variable is not None else _slot_for_line(source, route.path_line)
        else:
            if len(re.findall(r"\bTTPMEntry\s*\(", source)) >= 32:
                raise ValueError("All 32 rolling-rock route slots may be used.")
            ref = _new_variable(source, x, y)
            indent = lines[route.set_line - 1][:len(lines[route.set_line - 1]) - len(lines[route.set_line - 1].lstrip())]
            lines.insert(route.set_line - 1, f"{indent}var {ref} = TTPMEntry({st.value_source(path)})")
            route = RockRoute(route.function, x, y, direction, path, route.set_line + 1, None, ref, True)
        _replace_line(lines, route.set_line, f"SetRock({x}, {y}, {direction}, {ref})")
        result = "\n".join(lines) + "\n"
    else:
        if len(re.findall(r"\bTTPMEntry\s*\(", source)) >= 32:
            raise ValueError("All 32 rolling-rock route slots may be used.")
        name = _new_variable(source, x, y)
        block = [f"    var {name} = TTPMEntry({st.value_source(path)})",
                 f"    SetRock({x}, {y}, {direction}, {name})"]
        spans = st.function_spans(source)
        span = next((s for s in spans if s.name == "RegistLocationTT"), None)
        if span is None:
            result = source.rstrip("\n") + "\n\n@export\ndef RegistLocationTT():\n" + "\n".join(block) + "\n"
        else:
            fd = next(f for f in parse(source).functions if f.name == span.name)
            if len(fd.body) == 1 and isinstance(fd.body[0], A.Pass):
                lines[fd.body[0].line - 1:fd.body[0].line] = block
            else:
                insert_at = span.last_line
                if fd.body and isinstance(fd.body[-1], A.Return):
                    insert_at = fd.body[-1].line - 1
                lines[insert_at:insert_at] = block
            result = "\n".join(lines) + "\n"
    parse(result)
    return result


def _slot_for_line(source: str, line: int) -> int:
    """Index of an unassigned registration in its function's straight-line block."""
    module = parse(source)
    for fd in module.functions:
        index = 0
        for stmt in fd.body:
            value = stmt.expr if isinstance(stmt, A.ExprStmt) else stmt.value if isinstance(stmt, (A.VarInit, A.Assign)) else None
            if _call(value, "TTPMInit"):
                index = 0
            elif _call(value, "TTPMEntry"):
                if stmt.line == line:
                    return index
                index += 1
    raise ValueError("Could not resolve the route slot.")


def move_route(source: str, old: tuple[int, int], new: tuple[int, int]) -> str:
    """Move a literal SetRock binding with its placed prop."""
    matching = [r for r in routes(source) if (r.x, r.y) == old]
    if len(matching) != 1 or not matching[0].editable:
        return source
    route = matching[0]
    lines = source.splitlines()
    old_line = lines[route.set_line - 1]
    body, comment = st._split_comment(old_line)
    match = re.match(r"^(\s*)SetRock\s*\(\s*-?\d+\s*,\s*-?\d+\s*,\s*([^,]+),\s*(.+?)\s*\)\s*$", body)
    if match is None:
        return source
    lines[route.set_line - 1] = (f"{match.group(1)}SetRock({new[0]}, {new[1]}, {match.group(2).strip()}, "
                                 f"{match.group(3).strip()})" + comment)
    result = "\n".join(lines) + "\n"
    parse(result)
    return result


def remove_route(source: str, tile: tuple[int, int]) -> str:
    """Remove one standalone SetRock call; keep its slot to preserve other slot numbers."""
    matching = [r for r in routes(source) if (r.x, r.y) == tile]
    if len(matching) != 1 or not matching[0].editable:
        return source
    lines = source.splitlines()
    route = matching[0]
    function = next(fd for fd in parse(source).functions if fd.name == route.function)
    if len(function.body) == 1:
        _replace_line(lines, route.set_line, "pass")
    else:
        del lines[route.set_line - 1]
    result = "\n".join(lines) + "\n"
    parse(result)
    return result
