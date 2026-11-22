"""Building a playthrough from a chapter's files: the :class:`~.world.World`,
units from deployment records, and the starting :class:`~.state.GameState`.

A unit's stats follow the loader as :mod:`fe_modding.battle_sim.units`
describes it (class bases plus the character's personal bonus), plus the
deployment record's ``bonus_*`` fields. The level is the record's, or the
character's base level when that is higher and the class is the
character's own (``dispo`` docstring). Autolevelled units (flag 0x01) gain
the class growths' *average* for every level above their base - the game
rolls them, so real units differ by a few points.

**Player groups on Path of Radiance** follow ``main.dol``'s two deployment rules
(US addresses). A group whose name contains ``_mikata_`` (``strstr`` at 0x80107874)
is an *army* group (0x8010764c): each record is only a starting tile. Its
character is created in the reserve when the army is empty or the record has
``FLAG_SPAWN_WHEN_ABSENT``, then the **first unit of the reserve** (force 5, in
army order, Ike aside) takes the tile. Ike's own record places Ike. Any other
name places the listed character itself (0x80107468): the reserve unit, a unit
set aside in force 7, or a new one; a character in force 6 (dead) is skipped.
A save's army is given to :func:`initial_state` as ``army``.

**Radiant Dawn** army groups (US 0x8010BF00 gathers, 0x8010C200 places) differ: a record
whose halfword flags (field 2) have ``FE10_PLACE_THIS_CHARACTER`` places its own character
when it is in force 0 or 5; ``FE10_CREATE_IF_ABSENT`` creates an absent character in the
reserve (and, on a player record, places it). Those records go first. Units with the skill
``SID_HERO`` (the lords) are only placed by their own record; every other tile takes the
first reserve unit without it. There is no empty-army exception.

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
OPENING = ("Startup", "Opening0", "Opening1", "Opening2")  # FE9 compatibility; use world.dialect.openings


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
        base = world.tactical_data.combatant(pid, jid=jid or None) if char is not None else \
            world.tactical_data.class_combatant(jid)
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
    inventory_slots = 7 if world.dialect.name == "fe10" else 8
    for i in range(inventory_slots):
        iid = record[F[f"item{i}"]]
        if isinstance(iid, str):
            item = world.items.get(iid)
            items.append([iid, item.uses if item is not None else 1, bool(int(record[F[f"item{i}_flag"]] or 0) & 1)])
    faction = int(record[F["faction"]] or 0)
    tier = 1
    if world.dialect.name == "fe10" and cls is not None:
        tier = 1 + int(bool(getattr(cls, "demotes_to", None)))
        previous = world.classes.get(getattr(cls, "demotes_to", None))
        if previous is not None and getattr(previous, "demotes_to", None):
            tier = 3
    faction = faction if faction in world.army.names else (2 if faction > 1 else faction)
    return SimUnit(
        uid=0, pid=pid, jid=jid, faction=faction, x=int(record[F["pos_x"]]), y=int(record[F["pos_y"]]),
        level=level, stats=stats, hp=stats[0], build=base.build, move=cls.movement if cls is not None else 5,
        movement_type=cls.movement_type if cls is not None else 1, skills=skills,
        categories=[c for c in (cls.categories if cls is not None else ()) if c], items=items,
        seq_attack=record[F["seq_attack"]], seq_move=record[F["seq_move"]], seq_heal=record[F["seq_heal"]],
        mtype=record[F["mtype"]], ai_order=int(record[F["ai_order"]] or 0), flags=flags, group=group,
        boss=bool(flags & dispo.FLAG_COMMANDER) and faction != PLAYER,
        team=faction, force=int(record[F["faction"]] or 0), tier=tier,
        effective_level=level + (tier - 1) * 20,
        biorhythm_type=int(getattr(char, "biorhythm", 255)) if char is not None else 255,
        authority=int(getattr(char, "authority", 0)) if char is not None else 0,
        laguz_gauge=0,
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


ARMY_GROUP_MARK = "_mikata_"
LEADER_PID = "PID_IKE"  # the army rule's exception (main.dol string 0x80273948)
LORD_SKILL = "SID_HERO"  # Radiant Dawn's exception (US main.dol 0x8010C318 -> string 0x80368860)


def force_of(unit: SimUnit) -> int:
    """The game's force list of a unit: 0-3 on the map, 5 the reserve, 6 dead, 7 set aside."""
    if unit.dead:
        return 6
    if unit.away:
        return 7
    if unit.hidden and unit.faction == PLAYER:
        return 5
    return unit.faction


def force_members(state: GameState, force: int) -> list:
    """A force's units in list order (creation order stands in for the game's list order)."""
    units = sorted(state.units.values(), key=lambda u: u.uid)
    if force in (5, 6, 7):
        return [u for u in units if force_of(u) == force]
    return [u for u in units if u.faction == force and u.on_map]


def is_army_group(world: World, group: str) -> bool:
    """A ``_mikata_`` group is deployed from the reserve, not by PID (both games)."""
    return world.dialect.name in ("fe9", "fe10") and ARMY_GROUP_MARK in group


def _is_lord(unit: SimUnit) -> bool:
    return LORD_SKILL in unit.skills


def _rd_army_records(state: GameState, records: list) -> list:
    """Radiant Dawn's gathering pass: ``(record, direct, create)``, the direct records first."""
    out = []
    for record in records:
        pid = record[F["pid"]]
        flags = int(record[dispo.FE10_GROWTH_FLAGS_FIELD] or 0)
        unit = state.unit_by_pid(pid) if isinstance(pid, str) and pid else None
        present = unit is not None and not unit.dead
        direct = present and bool(flags & dispo.FE10_PLACE_THIS_CHARACTER)
        create = bool(flags & dispo.FE10_CREATE_IF_ABSENT)
        if create and not present and int(record[F["faction"]] or 0) == PLAYER:
            direct = True
        out.append((record, direct, create))
    return [r for r in out if r[1]] + [r for r in out if not r[1]]


def _rd_army_unit(world: World, state: GameState, record: list, group: str, direct: bool,
                  create: bool) -> Optional[SimUnit]:
    pid = record[F["pid"]]
    own = state.unit_by_pid(pid) if isinstance(pid, str) and pid else None
    if own is None and create and isinstance(pid, str) and pid:
        own = state.add_unit(make_unit(world, record, group))
        own.faction, own.hidden = PLAYER, True
    if own is not None and not own.dead and not own.away and force_of(own) in (0, 5) and (direct or _is_lord(own)):
        return own
    return next((u for u in force_members(state, 5) if not _is_lord(u)), None)


def _army_unit(world: World, state: GameState, record: list, group: str, army_was_empty: bool) -> Optional[SimUnit]:
    """The unit an army-group record places (main.dol 0x8010764c), or None when the reserve is empty."""
    pid = record[F["pid"]]
    own = state.unit_by_pid(pid) if isinstance(pid, str) and pid else None
    if own is None and isinstance(pid, str) and pid and (
            army_was_empty or int(record[F["flags"]] or 0) & dispo.FLAG_SPAWN_WHEN_ABSENT):
        own = state.add_unit(make_unit(world, record, group))
        own.faction, own.hidden = PLAYER, True
    elif own is not None and own.away:
        own.away = False
        own.faction, own.hidden = PLAYER, True
    if own is not None and own.dead:
        own = None
    if own is not None and own.pid == LEADER_PID:
        return own
    return next((u for u in force_members(state, 5) if u.pid != LEADER_PID), None)


def deploy(world: World, state: GameState, group: str, *, animate: bool = True, exact: bool = False,
           force: Optional[int] = None, hidden: bool = False, only: Optional[set] = None) -> list:
    """Place a deployment group's units (``Dispos`` and friends). Returns the units.
    ``only`` limits it to the units of those PIDs."""
    section = world.groups.get(group)
    if section is None:
        state.emit("warn", f"Deployment group {group!r} not found")
        return []
    army_group = force is None and not hidden and is_army_group(world, group)
    army_was_empty = not force_members(state, PLAYER) and not force_members(state, 5)
    placed = []
    rd_army = army_group and world.dialect.name == "fe10"
    plan = _rd_army_records(state, section.units) if rd_army else [(r, False, False) for r in section.units]
    for record, direct, create in plan:
        pid = record[F["pid"]]
        if only is not None and pid not in only:
            continue
        if army_group:
            unit = (_rd_army_unit(world, state, record, group, direct, create) if rd_army
                    else _army_unit(world, state, record, group, army_was_empty))
            if unit is None:
                state.emit("warn", f"{group}: no reserve unit left for the slot of {world.name(pid)}")
                continue
            if unit.pid != pid:
                state.emit("log", f"{group}: {world.name(unit.pid)} takes the slot of {world.name(pid)} "
                                  "(an army group places the reserve's first unit)", uid=unit.uid)
        else:
            if (world.dialect.name == "fe9" and int(record[F["faction"]] or 0) == PLAYER
                    and any(u.pid == pid and u.dead for u in state.units.values())
                    and _reusable(state, pid, placed) is None):
                continue  # force 6: the game places nobody (main.dol 0x80107528)
            unit = _reusable(state, pid, placed)
        if unit is None:
            unit = state.add_unit(make_unit(world, record, group))
        if force is not None:
            unit.faction = force
        elif army_group:
            unit.faction = PLAYER
        unit.away = False
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


def _reusable(state: GameState, pid, placed: list) -> Optional[SimUnit]:
    """The existing unit a deployment record reuses: a living unit of that
    character that is off the map (the reserve) or on the player's side.
    Generic soldiers share one PID, so an enemy already on the map is not
    reused, and no unit is placed twice by one deployment."""
    if not isinstance(pid, str):
        return None
    for unit in sorted(state.units.values(), key=lambda u: u.uid):
        if unit.pid == pid and not unit.dead and unit not in placed and (unit.hidden or unit.faction == PLAYER):
            return unit
    return None


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
        for name in world.dialect.openings:
            fn = chapter.function_by_name(name)
            if fn is not None:
                tasks.append(triggers.start(world, 0, chapter.functions.index(fn)))
    return tasks


def army_member(world: World, pid: str) -> list:
    """A deployment record for a character of a save's army: its own class and base level."""
    record = [0] * 48
    record[F["pid"]] = pid
    record[F["level"]] = 1
    return record


def initial_state(world: World, *, seed: int = 0, deploy_groups: tuple = (), army: tuple = ()) -> GameState:
    """The state before the chapter's first step: the opening scripts queued,
    then the first player phase. ``deploy_groups`` are placed first (used when
    the chapter has no script, or to skip the opening). ``army`` is a save's
    army: those characters wait in the reserve (force 5), in that order."""
    from ..battle_sim import Fe10Rng, Fe9Rng
    from ..formats.event_flags import ENGINE_FLAGS

    rng = Fe10Rng(seed) if world.dialect.name == "fe10" else Fe9Rng(seed)
    capacity = world.dialect.flag_slots
    flags = [[name, False] for name in ENGINE_FLAGS] + [[None, False] for _ in range(capacity - len(ENGINE_FLAGS))]
    state = GameState(rng=rng, flags=flags, flag_capacity=capacity)
    for pid in army:
        if pid in world.characters and state.unit_by_pid(pid) is None:
            unit = state.add_unit(make_unit(world, army_member(world, pid), "army"))
            unit.faction, unit.hidden = PLAYER, True
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


def preparation_roster(world: World) -> list:
    """The PIDs the preparations would place when the opening deployed nobody: the units of
    :func:`fallback_player_groups`, in file order. A choice among them goes in ``GameState.deploy_only``."""
    roster = []
    for group in fallback_player_groups(world):
        for record in world.groups[group].units:
            pid = record[F["pid"]]
            if isinstance(pid, str) and pid not in roster:
                roster.append(pid)
    return roster
