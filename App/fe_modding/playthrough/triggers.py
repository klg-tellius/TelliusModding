"""Which event functions fire: each function's trigger type and parameters
(``cmb.catalog.TRIGGERS``) matched against what just happened.

The rules follow the archive's ``events-scripting`` and ``event-script``
articles: goal events (types 1 and 2) run once their flag is set; phase
events (3 before, 6 after the phase starts) match a turn range and a phase;
zone events (4) match the tile where a unit of the given faction acts; location
events (5) a tile and an action id; talk (8) and battle (9) events a pair of
characters, either way round when their direction flag is 1, and are
skipped while their one-time flag is set; death events (10, 11) a
character. Location, talk, battle and goal events fire once (the engine's
"seen" set); the others every time they match.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from ..formats.cmb.binary import _pool_layout
from ..formats.cmb.catalog import TRIGGERS
from ..formats.cmb.decompiler import _Names
from .state import Frame, GameState, ScriptRun
from .world import World

ONCE = frozenset({1, 2, 5, 8, 9})


@dataclass
class TriggerFn:
    script: int
    function: int
    name: str
    type: int
    params: dict = field(default_factory=dict)  # by catalog parameter name; labels as text, 0 label = None


def index(world: World) -> list:
    """Every triggered function of the loaded scripts (cached on the world)."""
    cached = getattr(world, "_trigger_index", None)
    if cached is not None:
        return cached
    out = []
    for si, script in enumerate(world.scripts):
        _blob, offsets = _pool_layout(script)
        text = {}
        for s, off in offsets.items():
            text.setdefault(off, s)
        names = _Names(script).defs
        for fi, fn in enumerate(script.functions):
            kind = TRIGGERS.get(fn.type)
            if fn.type == 0 or kind is None:
                continue
            params = {}
            for spec, value in zip(kind.params, fn.params):
                if spec.is_label:
                    params[spec.name] = None if value == 0 else text.get(value, value)
                else:
                    params[spec.name] = value
            out.append(TriggerFn(si, fi, names[fi], fn.type, params))
    world._trigger_index = out
    return out


def function_names(world: World, script: int) -> list:
    cache = getattr(world, "_function_names", None)
    if cache is None:
        cache = world._function_names = {}
    if script not in cache:
        cache[script] = _Names(world.scripts[script]).defs
    return cache[script]


def find_function(world: World, name: str) -> Optional[tuple]:
    """(script, function) of a named function, searching the chain in order."""
    for si, script in enumerate(world.scripts):
        for fi, fn in enumerate(script.functions):
            if fn.id_string == name:
                return si, fi
    return None


def start(world: World, script: int, function: int, args=(), ctx: Optional[dict] = None) -> ScriptRun:
    fn = world.scripts[script].functions[function]
    local = list(args)[: fn.num_args] + [0] * max(0, fn.num_vars - min(len(args), fn.num_args))
    name = function_names(world, script)[function]
    return ScriptRun([Frame(script, function, 0, [], local)], dict(ctx or {}), name)


def _turn_match(params: dict, turn: int) -> bool:
    low, high = params.get("turn_from", 0), params.get("turn_to", 0)
    if not low:
        return True
    return low <= turn <= high


def _zone_rect(params: dict, width: int, height: int) -> tuple:
    """Resolve the engine's inclusive right/bottom endpoints against the map edges."""
    right, bottom = params["x2"], params["y2"]
    right = (right & 0xFF) - 0x100 if right & 0x80 else right & 0xFF
    bottom = (bottom & 0xFF) - 0x100 if bottom & 0x80 else bottom & 0xFF
    if right <= 0:
        right = width - 1 - right
    if bottom <= 0:
        bottom = height - 1 - bottom
    return params["x1"], params["y1"], right, bottom


def _pair(params: dict, a: Optional[str], b: Optional[str]) -> bool:
    p1, p2 = params.get("pid1"), params.get("pid2")
    if p1 == a and (p2 is None or p2 == b):
        return True
    return bool(params.get("flag")) and p1 == b and (p2 is None or p2 == a)


def _blocked(state: GameState, t: TriggerFn) -> bool:
    if t.type in ONCE and (t.script, t.function) in state.seen:
        return True
    flag = t.params.get("name") if t.type in (8, 9) else None
    return isinstance(flag, str) and state.get_flag(flag)


def matches(world: World, state: GameState, kind: int, ctx: dict, start: int = 0) -> list:
    out = []
    for t in index(world)[start:]:
        if t.type != kind or _blocked(state, t):
            continue
        p = t.params
        if kind in (1, 2):
            ok = isinstance(p.get("flag"), str) and state.get_flag(p["flag"])
        elif kind in (3, 6):
            ok = p.get("phase") in (ctx.get("phase"), 0xFFFF) and _turn_match(p, state.turn)
        elif kind == 4:
            tile = ctx.get("tile")
            left, top, right, bottom = _zone_rect(p, world.width, world.height)
            ok = (tile is not None and p.get("side", 0) in (ctx.get("faction"), 0xFFFF)
                  and left <= tile[0] <= right and top <= tile[1] <= bottom)
        elif kind == 5:
            ok = (p.get("x"), p.get("y"), p.get("action")) == (ctx.get("x"), ctx.get("y"), ctx.get("action"))
        elif kind in (8, 9):
            ok = _pair(p, ctx.get("pid1"), ctx.get("pid2"))
        elif kind in (10, 11):
            ok = p.get("pid") == ctx.get("pid")
        else:
            ok = True
        if ok:
            out.append(t)
    return out


def talk_events(world: World, state: GameState, pid1, pid2) -> list:
    return matches(world, state, 8, {"pid1": pid1, "pid2": pid2})


def location_events(world: World, state: GameState, tile: tuple, action: int) -> list:
    return matches(world, state, 5, {"x": tile[0], "y": tile[1], "action": action})


def zones(world: World) -> list:
    """``(rect, side, name)`` of the area triggers, for drawing."""
    out = []
    for t in index(world):
        if t.type == 4:
            p = t.params
            out.append((_zone_rect(p, world.width, world.height),
                        p.get("side", 0), t.name))
        elif t.type == 5:
            p = t.params
            out.append(((p["x"], p["y"], p["x"], p["y"]), -1 - int(p.get("action") or 0), t.name))
    return out
