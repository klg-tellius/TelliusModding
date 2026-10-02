"""Building a playthrough from a chapter's files: the :class:`~.world.World`,
units from deployment records, and the starting :class:`~.state.GameState`.

A unit's stats follow the loader as :mod:`fe_modding.battle_sim.units`
describes it (class bases plus the character's personal bonus), plus the
deployment record's ``bonus_*`` fields. The level is the record's, or the
character's base level when that is higher and the class is the
character's own (``dispo`` docstring). Autolevelled units (flag 0x01) gain
the class growths' *average* for every level above their base - the game
rolls them, so real units differ by a few points.

The chapter starts like the game's fixed sequence (archive ``chapters``
article): ``RegistGlobalFlags`` (``startup.cmb``, run at boot), the
chapter's ``Startup``, ``Opening0``, ``Opening1`` and ``Opening2`` (the base
and the preparations themselves are skipped), then the first player phase.
"""

from __future__ import annotations

from typing import Optional

from ..battle_sim import units as bsu
from ..formats import dispo
from . import triggers
from .state import PLAYER, GameState, PhaseStart, Preparations, SimUnit
from .world import World

F = dispo.FIELD
OPENING = ("Startup", "Opening0", "Opening1", "Opening2")


def groups(documents) -> dict:
    """Every deployment section by name, across the chapter's dispos files."""
    out = {}
    for doc in documents:
        if doc is None:
            continue
        for section in doc.sections:
            if not section.is_link:
                out.setdefault(section.name, section)
    return out


def make_unit(world: World, record: list, group: str = "") -> SimUnit:
    pid = record[F["pid"]] if isinstance(record[F["pid"]], str) else ""
    jid_field = record[F["jid"]]
    char = world.characters.get(pid)
    jid = jid_field if isinstance(jid_field, str) else (char.jid if char is not None else "")
    try:
        base = bsu.from_character(world.fe8, pid, jid=jid or None) if char is not None else \
            bsu.from_class(world.fe8, jid)
    except KeyError:
        base = bsu.Combatant(name=pid, pid=pid, jid=jid)
    cls = world.classes.get(jid)
    level = int(record[F["level"]] or 1)
    base_level = char.level if char is not None else 1
    if char is not None and jid == char.jid and char.level > level:
        level = char.level
    stats = list(base.stats)
    for i, stat in enumerate(dispo.STAT_NAMES):
        stats[i] += int(record[F[f"bonus_{stat}"]] or 0)
    flags = int(record[F["flags"]] or 0)
    if flags & dispo.FLAG_AUTOLEVEL and cls is not None and level > base_level:
        growth = list(char.growth) if char is not None else list(cls.growths)
        for i in range(8):
            stats[i] += (level - base_level) * growth[i] // 100
        caps = list(cls.stat_caps)
        stats = [min(v, c) if c else v for v, c in zip(stats, caps)]
    stats = [max(0, v) for v in stats]
    stats[0] = max(1, stats[0])
    skills = list(base.skills)
    for i in range(5):
        sid = record[F[f"skill{i}"]]
        if isinstance(sid, str) and sid not in skills:
            skills.append(sid)
    items = []
    for i in range(8):
        iid = record[F[f"item{i}"]]
        if isinstance(iid, str):
            item = world.items.get(iid)
            items.append([iid, item.uses if item is not None else 1, bool(int(record[F[f"item{i}_flag"]] or 0) & 1)])
    faction = int(record[F["faction"]] or 0)
    return SimUnit(
        uid=0, pid=pid, jid=jid, faction=faction, x=int(record[F["pos_x"]]), y=int(record[F["pos_y"]]),
        level=level, stats=stats, hp=stats[0], build=base.build, move=cls.movement if cls is not None else 5,
        movement_type=cls.movement_type if cls is not None else 1, skills=skills,
        categories=[c for c in (cls.categories if cls is not None else ()) if c], items=items,
        seq_attack=record[F["seq_attack"]], seq_move=record[F["seq_move"]], seq_heal=record[F["seq_heal"]],
        mtype=record[F["mtype"]], ai_order=int(record[F["ai_order"]] or 0), flags=flags, group=group,
        boss=bool(flags & dispo.FLAG_COMMANDER) and faction != PLAYER,
    )


def nearest_free(world: World, state: GameState, tile: tuple, unit: Optional[SimUnit] = None) -> tuple:
    """The free tile nearest ``tile`` (the tile itself when free) that the unit could stand on."""
    from .world import IMPASSABLE

    seen, frontier = {tile}, [tile]
    while frontier:
        nxt = []
        for x, y in frontier:
            other = state.unit_at(x, y)
            standable = world.inside(x, y) and (unit is None or world.move_cost(x, y, unit.movement_type) < IMPASSABLE)
            if standable and (other is None or (unit is not None and other.uid == unit.uid)):
                return (x, y)
            for dx, dy in ((0, -1), (1, 0), (0, 1), (-1, 0)):
                n = (x + dx, y + dy)
                if n not in seen and 0 <= n[0] < world.width and 0 <= n[1] < world.height:
                    seen.add(n)
                    nxt.append(n)
        frontier = nxt
        if len(seen) > world.width * world.height:
            break
    return tile


def deploy(world: World, state: GameState, group: str, *, animate: bool = True, exact: bool = False,
           force: Optional[int] = None, hidden: bool = False) -> list:
    """Place a deployment group's units (``Dispos`` and friends). Returns the units."""
    section = world.groups.get(group)
    if section is None:
        state.emit("warn", f"Deployment group {group!r} not found")
        return []
    placed = []
    for record in section.units:
        pid = record[F["pid"]]
        unit = state.unit_by_pid(pid) if isinstance(pid, str) else None
        if unit is None:
            unit = state.add_unit(make_unit(world, record, group))
        if force is not None:
            unit.faction = force
        unit.dead = False
        unit.hidden = hidden
        start = (int(record[F["pos_x"]]), int(record[F["pos_y"]]))
        end = (int(record[F["pos2_x"]]), int(record[F["pos2_y"]]))
        if not hidden:
            unit.hidden = True  # off the map while its tile is chosen
            unit.x, unit.y = start if exact else nearest_free(world, state, start, unit)
            unit.hidden = False
            if animate and end != start:
                unit.hidden = True
                unit.x, unit.y = nearest_free(world, state, end, unit)
                unit.hidden = False
        placed.append(unit)
    names = ", ".join(world.name(u.pid) for u in placed[:8]) + ("..." if len(placed) > 8 else "")
    state.emit("action", f"Deployed {group}: {names}" if placed else f"Deployed {group} (empty)", group=group)
    return placed


def opening_tasks(world: World) -> list:
    tasks = []
    boot = None
    for si, script in enumerate(world.scripts):
        if si > 0 and script.function_by_name("RegistGlobalFlags") is not None:
            boot = (si, script.functions.index(script.function_by_name("RegistGlobalFlags")))
            break
    if boot is not None:
        tasks.append(triggers.start(world, *boot))
    if world.scripts:
        chapter = world.scripts[0]
        for name in OPENING:
            fn = chapter.function_by_name(name)
            if fn is not None:
                tasks.append(triggers.start(world, 0, chapter.functions.index(fn)))
    return tasks


def initial_state(world: World, *, seed: int = 0, deploy_groups: tuple = ()) -> GameState:
    """The state before the chapter's first step: the opening scripts queued,
    then the first player phase. ``deploy_groups`` are placed first (used when
    the chapter has no script, or to skip the opening)."""
    from ..battle_sim import Fe9Rng

    state = GameState(rng=Fe9Rng(seed))
    for group in deploy_groups:
        deploy(world, state, group, animate=False)
    state.out.clear()
    state.pending = opening_tasks(world) + [Preparations(), PhaseStart(PLAYER)]
    return state


def fallback_player_groups(world: World) -> list:
    """The deployment sections of player units only, for this difficulty or every
    difficulty: what :class:`Preparations` places when the opening deployed nobody."""
    out = []
    for name, section in world.groups.items():
        if section.units and all(int(u[F["faction"]] or 0) == PLAYER for u in section.units):
            if name.endswith("_c") or name.endswith(f"_{world.difficulty}"):
                out.append(name)
    return out
