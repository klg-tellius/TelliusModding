"""The enemy and NPC AI: a unit's turn runs its ``cp_data.bin`` scripts one
entry per step.

What follows the engine as :mod:`fe_modding.formats.cp_ops` documents it:

- a turn is the heal check, then the attack script, then the move script,
  stopping at the first that found an action; each script resumes at the
  unit's saved program counter and runs until END/STOP (which sets where the
  next run starts) or SET_SCRIPTS replaces it; after 256 entries the built-in
  fallback runs (``attack(chance=100)``, ``move_nearest()``);
- a non-zero ``b`` word sets the threat limit before the entry runs; moves
  then only stop on tiles whose threat (here: how many hostile units could
  strike the tile next turn) is at most the limit;
- jumps go to the first LABEL entry with that number, reading on past the
  end of the script into the sections that follow it (``fallthrough``);
- action entries roll their chance (``rn <= chance``), register a candidate
  and set the found flag; a later action replaces the candidate.

What is the simulator's own choice: the target and tile of an attack are
picked by a score built from the unit's MTYPE weights (damage dealt, share
of the target's HP, counter damage taken, terrain) over the battle forecast,
not the engine's exact formula; movement towards a goal takes the reachable
tile with the shortest remaining path. Steal, ballistas, rocks, skills other
than Shove and item use are logged as not simulated.
"""

from __future__ import annotations

from typing import Optional

from ..formats import cp_data
from ..formats.cp_ai_lang import entry_source
from . import combat, movement, triggers
from .actions import Act, apply as apply_command, can_shove
from .state import AiTurn, GameState, SimUnit, hostile
from .world import IMPASSABLE, World

MAX_ENTRIES = 256
MAX_RESTARTS = 8
NO_LIMIT = 0xFFFF
ATTACK, MOVE = 0, 1
FALLBACK = {ATTACK: [cp_data.Entry(101, a=100), cp_data.Entry(1001)],
            MOVE: [cp_data.Entry(206), cp_data.Entry(1001)]}
DEFAULT_SCRIPTS = {ATTACK: "SEQ_NOATTACK", MOVE: "SEQ_NOMOVE"}


# -- programs ---------------------------------------------------------------------------------------


class Program:
    """A script's entries followed by whatever the label search would read after it."""

    def __init__(self, entries: list, owners: list, name: str):
        self.entries, self.owners, self.name = entries, owners, name
        self.lines = []
        previous = None
        for e in entries:
            try:
                self.lines.append(entry_source(e, previous))
            except Exception:  # noqa: BLE001 - garbage words read past the end
                self.lines.append(f"op({e.op})")
            if e.op != 1:
                previous = e
        self.body = sum(1 for o in owners if o == name)

    def label(self, number) -> Optional[int]:
        if not number:
            return 0
        for i, e in enumerate(self.entries):
            if e.op == 0 and e.c == number:
                return i
        return None


def program(world: World, name) -> Optional[Program]:
    cache = getattr(world, "_ai_programs", None)
    if cache is None:
        cache = world._ai_programs = {}
    if name in cache:
        return cache[name]
    result = None
    doc = world.cp
    if doc is not None and isinstance(name, str):
        names = [s.name for s in doc.sections]
        if name in names:
            index = names.index(name)
            section = doc.sections[index]
            if cp_data.is_script_section(section):
                script = cp_data.read_script(section)
                entries, owners = list(script.entries), [name] * len(script.entries)
                words, word_owners = [], []
                for s in doc.sections[index + 1:]:
                    words += s.words
                    word_owners += [s.name] * len(s.words)
                    if len(words) >= 7 * MAX_ENTRIES:
                        break
                skip = (7 - len(section.words) % 7) % 7
                for i in range(skip, len(words) - 6, 7):
                    try:
                        entries.append(cp_data.Entry.from_words(words[i:i + 7]))
                    except Exception:  # noqa: BLE001
                        break
                    owners.append(word_owners[i])
                result = Program(entries, owners, name)
    cache[name] = result
    return result


def _fallback_program(kind: int) -> Program:
    entries = FALLBACK[kind]
    name = "(built-in fallback)"
    return Program(list(entries), [name] * len(entries), name)


def script_name(world: World, unit: SimUnit, kind: int):
    value = unit.seq_attack if kind == ATTACK else unit.seq_move
    if isinstance(value, str) and value:
        return value
    return DEFAULT_SCRIPTS[kind]


# -- helpers ----------------------------------------------------------------------------------------


def pid_table(world: World, name) -> Optional[set]:
    if not isinstance(name, (str, cp_data.SectionRef)) or not world.cp:
        return None
    section = world.cp.section(name if isinstance(name, str) else name.name)
    if section is None:
        return None
    try:
        return {str(p) for p in cp_data.read_list(section)}
    except ValueError:
        return None


def targets(world: World, state: GameState, unit: SimUnit, table=None, exclude: bool = False) -> list:
    pids = pid_table(world, table)
    out = []
    for other in state.living():
        if other.uid == unit.uid:
            continue
        if pids is None:
            ok = hostile(unit.faction, other.faction)
        elif exclude:
            ok = hostile(unit.faction, other.faction) and other.pid not in pids
        else:
            ok = other.pid in pids
        if ok:
            out.append(other)
    return out


def threat_map(world: World, state: GameState, unit: SimUnit) -> dict:
    """Tile -> number of units hostile to ``unit`` that could strike it next turn."""
    out: dict = {}
    for other in state.living():
        if not hostile(unit.faction, other.faction):
            continue
        ranges = combat.attack_ranges(world, other)
        if not ranges:
            continue
        for tile in movement.threat_tiles(world, state, other, ranges):
            out[tile] = out.get(tile, 0) + 1
    return out


def _mtype(world: World, unit: SimUnit) -> dict:
    defaults = {"damage_dealt": 4, "hp_ratio": 1, "damage_taken": 2, "terrain": 1, "turn_number": 0}
    if world.cp is None or not isinstance(unit.mtype, str):
        return defaults
    section = world.cp.section(unit.mtype)
    if section is None or not cp_data.is_mtype_section(section):
        return defaults
    return cp_data.read_mtype(section).values


def _hold(unit: SimUnit) -> bool:
    from ..formats import dispo

    return bool(unit.flags & dispo.FLAG_HOLD_POSITION)


def _goal_distances(world: World, state: GameState, unit: SimUnit, goals: set) -> dict:
    """Path cost from every tile to the nearest goal tile, for ``unit``'s movement type (units ignored)."""
    import heapq

    best = {g: 0 for g in goals if world.inside(*g)}
    heap = [(0, g) for g in best]
    heapq.heapify(heap)
    while heap:
        cost, (x, y) = heapq.heappop(heap)
        if cost > best.get((x, y), 1 << 30):
            continue
        step = world.move_cost(x, y, unit.movement_type)
        step = 1 if (x, y) in state.opened else step
        if step >= IMPASSABLE and (x, y) not in goals:
            continue
        for dx, dy in movement.NEIGHBOURS:
            n = (x + dx, y + dy)
            if not world.inside(*n) or not world.linked(n[0], n[1], x, y):
                continue
            total = cost + (step if (x, y) not in goals else 1)
            if total < best.get(n, 1 << 30):
                best[n] = total
                heapq.heappush(heap, (total, n))
    return best


# -- the turn ---------------------------------------------------------------------------------------


class AiStep:
    def __init__(self, world: World, state: GameState, turn: AiTurn):
        self.world, self.state, self.turn = world, state, turn
        self.unit: SimUnit = state.units[turn.uid]
        self._jumped = False

    def emit(self, text: str, **data) -> None:
        self.state.emit("ai", text, uid=self.unit.uid, script=self.turn.script, pc=self.turn.pc, **data)

    # -- driving ---------------------------------------------------------------------------------
    def step(self) -> bool:
        t, unit = self.turn, self.unit
        if not unit.on_map:
            return True
        if t.stage == "start":
            t.found, t.candidate = False, None
            self.emit(f"{self.world.name(unit.pid)}'s turn")
            if self._retreat():
                t.stage = "act"
                return False
            self._begin(ATTACK)
            return False
        if t.stage in ("attack", "move"):
            self._entry()
            return False
        if t.stage == "act":
            self._act()
            t.stage = "done"
            return True
        return True

    def _kind(self) -> int:
        return ATTACK if self.turn.stage == "attack" else MOVE

    def _program(self) -> Program:
        if self.turn.fallback:
            return _fallback_program(self._kind())
        return program(self.world, self.turn.script) or _fallback_program(self._kind())

    def _begin(self, kind: int) -> None:
        t = self.turn
        t.stage = "attack" if kind == ATTACK else "move"
        t.script = script_name(self.world, self.unit, kind)
        t.fallback = program(self.world, t.script) is None
        t.pc = self.unit.ai_pc[kind] if not t.fallback else 0
        t.steps, t.threat_limit = 0, NO_LIMIT
        self.emit(f"{t.stage} script {t.script}" + (" (not found: built-in fallback)" if t.fallback else ""))

    def _finish_script(self) -> None:
        t = self.turn
        if t.found:
            t.stage = "act"
        elif t.stage == "attack":
            self._begin(MOVE)
        else:
            t.stage = "act"

    def _entry(self) -> None:
        t = self.turn
        prog = self._program()
        if t.steps >= MAX_ENTRIES and not t.fallback:
            self.emit(f"{MAX_ENTRIES} entries without END: built-in fallback")
            t.fallback, t.pc, t.steps = True, 0, 0
            return
        if t.pc >= len(prog.entries):
            self.emit("ran off the end of the readable data: built-in fallback")
            t.fallback, t.pc, t.steps = True, 0, 0
            return
        entry = prog.entries[t.pc]
        line = prog.lines[t.pc]
        owner = prog.owners[t.pc]
        where = f"{t.script}#{t.pc}" + (f" (in {owner})" if owner != t.script else "")
        t.steps += 1
        if isinstance(entry.b, int) and entry.b and entry.op not in (1000, 1001, 500, 501, 502, 600):
            t.threat_limit = entry.b & 0xFFFF
        handler = getattr(self, f"_op_{entry.op}", None)
        before = t.pc
        if handler is None:
            self.emit(f"{where}: {line}  - not simulated", line=line)
            t.pc += 1
            return
        mark = len(self.state.out)
        note = handler(entry, prog)
        later = self.state.out[mark:]  # what the entry started (a new script) is logged after the entry
        del self.state.out[mark:]
        self.emit(f"{where}: {line}" + (f"  -> {note}" if note else ""), line=line)
        self.state.out.extend(later)
        if t.pc == before and t.stage in ("attack", "move") and not getattr(self, "_jumped", False):
            t.pc += 1
        self._jumped = False

    def _jump(self, prog: Program, label) -> str:
        index = prog.label(label)
        if index is None:
            self.turn.pc = len(prog.entries)
            return f"label {label} not found"
        self.turn.pc = index
        self._jumped = True
        return f"goto L{label}"

    def _roll(self, chance) -> bool:
        return self.state.rng.rn() <= int(chance or 0)

    def _register(self, candidate: dict) -> None:
        self.turn.found = True
        self.turn.candidate = candidate

    # -- flow opcodes ----------------------------------------------------------------------------
    def _op_0(self, e, prog):
        return ""

    def _op_1(self, e, prog):
        reg = self.turn.registers[int(e.a) & 3]
        value = e.c if isinstance(e.c, int) else 0
        value = value - (1 << 32) if value & 0x80000000 else value
        ok = {0: reg > value, 1: reg >= value, 2: reg == value, 3: reg <= value, 4: reg < value,
              5: reg != value}.get(int(e.b), False)
        return self._jump(prog, e.d) if ok else f"r{int(e.a) & 3} = {reg}: no jump"

    def _op_2(self, e, prog):
        return "native call not simulated"

    def _op_3(self, e, prog):
        unit, t = self.unit, self.turn
        replaced = False
        if isinstance(e.e, str) and e.e:
            unit.seq_attack, unit.ai_pc[ATTACK] = e.e, 0
            replaced |= t.stage == "attack"
        if isinstance(e.f, str) and e.f:
            unit.seq_move, unit.ai_pc[MOVE] = e.f, 0
            replaced |= t.stage == "move"
        if replaced:
            t.fallback = False
            t.restarts += 1
            if t.restarts > MAX_RESTARTS:
                self._finish_script()
                return "too many script changes: run ends"
            kind = self._kind()
            self._begin(kind)
            self._jumped = True
            return "scripts replaced: the run restarts"
        return "scripts set"

    def _op_4(self, e, prog):
        return self._jump(prog, e.d)

    def _op_5(self, e, prog):
        self.turn.registers[int(e.a) & 3] = 9
        return "event action not simulated: r = 9"

    def _op_6(self, e, prog):
        want = bool(e.a)
        return self._jump(prog, e.d) if self.turn.found == want else "no jump"

    def _op_7(self, e, prog):
        self.turn.found, self.turn.candidate = False, None
        return "found cleared"

    def _end(self, e, prog):
        index = prog.label(e.d)
        kind = self._kind()
        if not self.turn.fallback:
            self.unit.ai_pc[kind] = index if index is not None else 0
        self._finish_script()
        self._jumped = True
        return "run ends" + (f", next run at L{e.d}" if e.d else "")

    _op_1000 = _end
    _op_1001 = _end

    # -- attacks ---------------------------------------------------------------------------------
    def _tiles(self, in_place: bool) -> dict:
        if in_place or _hold(self.unit):
            return {self.unit.tile: (0, None)}
        return movement.destinations(self.world, self.state, self.unit)

    def _best_attack(self, foes: list, in_place: bool) -> Optional[dict]:
        world, unit = self.world, self.unit
        weights = _mtype(world, unit)
        best, best_score = None, None
        tiles = self._tiles(in_place)
        original = unit.tile
        for index, item in combat.weapon_items(world, unit):
            low, high = combat.item_range(unit, item)
            for foe in foes:
                for tile in tiles:
                    d = movement.distance(tile, foe.tile)
                    if not low <= d <= high:
                        continue
                    unit.x, unit.y = tile
                    try:
                        f = combat.forecast(world, unit, foe, item, d)
                    finally:
                        unit.x, unit.y = original
                    a, b = f.attacker, f.defender
                    strikes = a.strikes * (2 if a.doubles else 1)
                    dealt = min(foe.hp, a.damage * strikes) * a.hit / 100
                    taken = (b.damage * b.strikes * (2 if b.doubles else 1) * b.hit / 100) if b.can_attack else 0
                    t = world.terrain_at(*tile)
                    terrain = (t.avoid + t.defense) if t is not None else 0
                    score = (weights.get("damage_dealt", 0) * dealt
                             + weights.get("hp_ratio", 0) * dealt * 100 / max(1, foe.hp)
                             - weights.get("damage_taken", 0) * taken
                             + weights.get("terrain", 0) * terrain
                             + (1000 if dealt >= foe.hp and a.hit >= 50 else 0)
                             - 0.01 * tiles[tile][0])
                    if best_score is None or score > best_score:
                        best_score = score
                        best = {"action": "attack", "dest": tile, "target": foe.uid, "item": index,
                                "text": f"attack {world.name(foe.pid)} from {tile} (hit {a.hit}, dmg {a.damage})"}
        return best

    def _attack(self, e, foes, in_place=False):
        if not self._roll(e.a):
            return f"chance {e.a}%: no"
        best = self._best_attack(foes, in_place)
        if best is None:
            return "no target in reach"
        self._register(best)
        return best["text"]

    def _op_100(self, e, prog):
        pid = e.e
        if e.d:
            foes = [u for u in targets(self.world, self.state, self.unit) if u.pid != pid]
        else:
            target = self.state.unit_by_pid(pid)
            if target is None or not target.on_map:
                self.turn.registers[0] = 1
                return "character not on the map: r0 = 1"
            foes = [target]
        return self._attack(e, foes)

    def _op_101(self, e, prog):
        return self._attack(e, targets(self.world, self.state, self.unit, e.e, bool(e.d)))

    def _op_103(self, e, prog):
        return self._attack(e, targets(self.world, self.state, self.unit, e.e, bool(e.d)), in_place=True)

    def _op_104(self, e, prog):
        foes = targets(self.world, self.state, self.unit)
        foes = [u for u in foes if (u.jid != e.e) == bool(e.d)]
        return self._attack(e, foes)

    _op_116 = _op_101

    def _staff(self, e, in_place: bool):
        if not self._roll(e.a):
            return f"chance {e.a}%: no"
        world, state, unit = self.world, self.state, self.unit
        staves = combat.staff_items(world, unit)
        if not staves:
            return "no staff"
        tiles = self._tiles(in_place)
        pids = pid_table(world, e.e)
        best = None
        for index, item in staves:
            low, high = combat.item_range(unit, item)
            for ally in state.living():
                if hostile(unit.faction, ally.faction) or ally.hp >= ally.stats[0]:
                    continue
                if pids is not None and ally.pid not in pids:
                    continue
                for tile in tiles:
                    if low <= movement.distance(tile, ally.tile) <= high:
                        need = ally.stats[0] - ally.hp
                        if best is None or need > best[0]:
                            best = (need, {"action": "staff", "dest": tile, "target": ally.uid, "item": index,
                                           "text": f"heal {world.name(ally.pid)} from {tile}"})
                        break
        if best is None:
            return "nobody to heal"
        self._register(best[1])
        return best[1]["text"]

    def _op_105(self, e, prog):
        return self._staff(e, False)

    def _op_106(self, e, prog):
        return self._staff(e, True)

    def _op_115(self, e, prog):
        if not self._roll(e.a):
            return f"chance {e.a}%: no"
        foes = sorted(targets(self.world, self.state, self.unit, e.e, bool(e.d)), key=lambda u: u.level)
        tiles = self._tiles(False)
        for foe in foes:
            for tile in tiles:
                if movement.distance(tile, foe.tile) == 1:
                    original = self.unit.tile
                    self.unit.x, self.unit.y = tile
                    try:
                        ok = can_shove(self.world, self.state, self.unit, tile, foe)
                    finally:
                        self.unit.x, self.unit.y = original
                    if ok:
                        self._register({"action": "shove", "dest": tile, "target": foe.uid,
                                        "text": f"shove {self.world.name(foe.pid)} from {tile}"})
                        return self.turn.candidate["text"]
        return "nobody to shove"

    def _not_simulated(self, e, prog):
        self.turn.registers[0] = 9
        return "not simulated (r0 = 9)"

    _op_107 = _op_108 = _op_110 = _op_111 = _op_112 = _op_113 = _op_114 = _op_212 = _not_simulated

    def _nop(self, e, prog):
        return ""

    _op_102 = _op_109 = _op_202 = _op_208 = _op_213 = _op_214 = _nop

    # -- movement --------------------------------------------------------------------------------
    def _move_towards(self, goals: set, *, limit: bool = True, fallback: bool = True, text: str = "") -> Optional[tuple]:
        world, state, unit = self.world, self.state, self.unit
        if not goals or _hold(unit):
            return None
        reach = movement.destinations(world, state, unit)
        dist = _goal_distances(world, state, unit, goals)
        threat = threat_map(world, state, unit) if limit and self.turn.threat_limit != NO_LIMIT else {}
        here = dist.get(unit.tile, 1 << 30)
        candidates = [t for t in reach if t in dist]
        if threat:
            safe = [t for t in candidates if threat.get(t, 0) <= self.turn.threat_limit]
            if not safe or min(dist[t] for t in safe) >= here:
                if not fallback:
                    return None
                safe = candidates
            candidates = safe
        if not candidates:
            return None
        best = min(candidates, key=lambda t: (dist[t], reach[t][0]))
        if best == unit.tile:
            return None
        self._register({"action": "wait", "dest": best, "text": text or f"move to {best}"})
        return best

    def _foe_goals(self, foes: list) -> set:
        goals = set()
        for foe in foes:
            for dx, dy in movement.NEIGHBOURS:
                goals.add((foe.x + dx, foe.y + dy))
        return goals

    def _op_200(self, e, prog):
        goal = (int(e.c), int(e.d))
        near = int(e.a or 0)
        dest = self._move_towards({goal}, text=f"move towards {goal}")
        where = dest or self.unit.tile
        if movement.distance(where, goal) <= near:
            self.turn.registers[0] = 8
            return f"arrives near {goal}: r0 = 8"
        return f"moves to {dest}" if dest else "can't get closer"

    def _toward_character(self, pid, talk: bool):
        target = self.state.unit_by_pid(pid)
        if target is None:
            self.turn.registers[0] = 9
            return None, "not found: r0 = 9"
        if not target.on_map:
            self.turn.registers[0] = 1
            return None, "not on the map: r0 = 1"
        return target, ""

    def _op_201(self, e, prog):
        target, note = self._toward_character(e.e, False)
        if target is None:
            return note
        if movement.distance(self.unit.tile, target.tile) == 1:
            self.turn.registers[0] = 2
            return "next to it: r0 = 2"
        dest = self._move_towards(self._foe_goals([target]), text=f"walk towards {self.world.name(target.pid)}")
        if dest is not None and movement.distance(dest, target.tile) == 1:
            self.turn.found, self.turn.candidate = False, None
            self.turn.registers[0] = 2
            return "can reach it: r0 = 2"
        return f"walks to {dest}" if dest else "can't get closer"

    def _op_203(self, e, prog):
        foes = [u for u in self.state.living() if u.jid == e.e and u.uid != self.unit.uid]
        dest = self._move_towards(self._foe_goals(foes))
        return f"moves to {dest}" if dest else "nothing to move to"

    def _op_204(self, e, prog):
        villages = [t for t in triggers.index(self.world) if t.type == 5 and t.params.get("action") in (9, 37)
                    and (t.params.get("x"), t.params.get("y")) not in self.state.visited]
        if not villages:
            self.turn.registers[0] = 9
            return "no village: r0 = 9"
        goals = {(t.params["x"], t.params["y"]) for t in villages}
        reach = movement.destinations(self.world, self.state, self.unit)
        here = [g for g in goals if g in reach]
        if here:
            self._register({"action": "destroy", "dest": here[0], "text": f"destroy the village at {here[0]}"})
            return self.turn.candidate["text"]
        dest = self._move_towards(goals, text="move towards a village")
        return f"moves to {dest}" if dest else "can't get closer"

    def _op_205(self, e, prog):
        reach = movement.destinations(self.world, self.state, self.unit)
        threat = threat_map(self.world, self.state, self.unit)
        best = min(reach, key=lambda t: (threat.get(t, 0), reach[t][0]))
        if best != self.unit.tile and not _hold(self.unit):
            self._register({"action": "wait", "dest": best, "text": f"move to the safest tile {best}"})
            return self.turn.candidate["text"]
        return "stays"

    def _op_206(self, e, prog):
        foes = targets(self.world, self.state, self.unit, e.e, bool(e.d))
        dest = self._move_towards(self._foe_goals(foes), fallback=bool(e.c), text="move towards the nearest target")
        return f"moves to {dest}" if dest else "stays"

    _op_207 = _op_206
    _op_217 = _op_206

    def _op_209(self, e, prog):
        events = [t for t in triggers.index(self.world) if t.type == 5 and t.params.get("action") == e.c]
        reg = int(e.a) & 3
        if not events:
            self.turn.registers[reg] = 9
            return "no such event: r = 9"
        goals = {(t.params["x"], t.params["y"]) for t in events}
        reach = movement.destinations(self.world, self.state, self.unit)
        if goals & set(reach):
            self.turn.registers[reg] = 8
        dest = self._move_towards(goals, text="move towards an event tile")
        return f"moves to {dest}" if dest else "stays"

    def _op_210(self, e, prog):
        reach = sorted(movement.destinations(self.world, self.state, self.unit))
        if not reach or _hold(self.unit):
            return "stays"
        dest = reach[self.state.rng._next() % len(reach)]
        self._register({"action": "wait", "dest": dest, "text": f"move to the random tile {dest}"})
        return self.turn.candidate["text"]

    def _op_211(self, e, prog):
        exits = {(t.params["x"], t.params["y"]) for t in triggers.index(self.world)
                 if t.type == 5 and t.params.get("action") == 44}
        if not exits:
            return "no escape point"
        reach = movement.destinations(self.world, self.state, self.unit)
        here = [g for g in exits if g in reach]
        if here:
            self._register({"action": "escape_ai", "dest": here[0], "text": f"escape at {here[0]}"})
            return self.turn.candidate["text"]
        dest = self._move_towards(exits, text="move towards the escape point")
        return f"moves to {dest}" if dest else "stays"

    def _talk(self, e, move: bool):
        target, note = self._toward_character(e.e, True)
        if target is None:
            return note
        if not triggers.talk_events(self.world, self.state, self.unit.pid, target.pid):
            self.turn.registers[0] = 9
            return "no talk event: r0 = 9"
        tiles = self._tiles(not move)
        spot = next((t for t in sorted(tiles, key=lambda t: tiles[t][0])
                     if movement.distance(t, target.tile) == 1), None)
        if spot is None:
            if move:
                dest = self._move_towards(self._foe_goals([target]), text="walk towards the talk partner")
                return f"walks to {dest}" if dest else "can't get closer"
            return "not next to it"
        self.turn.registers[0] = 3
        self._register({"action": "talk", "dest": spot, "target": target.uid,
                        "text": f"talk to {self.world.name(target.pid)} from {spot}"})
        return self.turn.candidate["text"] + ": r0 = 3"

    def _op_215(self, e, prog):
        return self._talk(e, True)

    def _op_218(self, e, prog):
        return self._talk(e, False)

    def _op_216(self, e, prog):
        section = self.world.cp.section(e.e if isinstance(e.e, str) else getattr(e.e, "name", "")) \
            if self.world.cp else None
        try:
            points = cp_data.read_route(section) if section is not None else []
        except ValueError:
            points = []
        if not points:
            return "no route"
        unit = self.unit
        index = unit.route % len(points)
        if movement.distance(unit.tile, points[index]) <= int(e.a or 0):
            unit.route = (index + 1) % len(points)
            index = unit.route
        dest = self._move_towards({points[index]}, text=f"follow the route to {points[index]}")
        return f"moves to {dest}" if dest else "stays"

    # -- registers -------------------------------------------------------------------------------
    def _op_500(self, e, prog):
        factor = (int(e.b) & 0xFFFFFFFF) / 65536 if isinstance(e.b, int) else 1.0
        budget = int(self.unit.move * factor)
        reach = movement.destinations(self.world, self.state, self.unit, budget=budget)
        extra = max((r[1] for r in combat.attack_ranges(self.world, self.unit)), default=1) if e.c else 1
        foes = targets(self.world, self.state, self.unit, e.e, bool(e.d))
        count = sum(1 for f in foes if any(movement.distance(t, f.tile) <= extra for t in reach))
        self.turn.registers[int(e.a) & 3] = count
        return f"r{int(e.a) & 3} = {count}"

    def _op_501(self, e, prog):
        value = 11 if "SID_LYCANTHROPE" in self.unit.skills else 0
        self.turn.registers[int(e.a) & 3] = value
        return f"r{int(e.a) & 3} = {value}"

    def _op_502(self, e, prog):
        if not any(it[0] == e.e for it in self.unit.items):
            return "doesn't hold it"
        return "item use not simulated"

    def _op_600(self, e, prog):
        self.unit.move += int(e.d or 0)
        self.turn.registers[int(e.a) & 3] = self.unit.move
        return f"Mov = {self.unit.move}"

    # -- retreat and acting ----------------------------------------------------------------------
    def _retreat(self) -> bool:
        unit = self.unit
        name = unit.seq_heal
        if not isinstance(name, str) or self.world.cp is None:
            return False
        section = self.world.cp.section(name)
        if section is None or not cp_data.is_heal_section(section):
            return False
        record = cp_data.read_heal(section)
        percent = unit.hp * 100 // max(1, unit.stats[0])
        if percent >= record.retreat_below or record.retreat_below <= 0:
            return False
        reach = movement.destinations(self.world, self.state, unit)
        threat = threat_map(self.world, self.state, unit)
        best = min(reach, key=lambda t: (threat.get(t, 0), reach[t][0]))
        self._register({"action": "wait", "dest": best, "text": f"retreat to {best} (HP {percent}%)"})
        self.emit(f"HP {percent}% < {record.retreat_below}%: retreats to {best}")
        return True

    def _act(self) -> None:
        unit, cand = self.unit, self.turn.candidate
        if cand is None:
            cand = {"action": "wait", "dest": unit.tile, "text": "wait"}
        action = cand["action"]
        if action == "escape_ai":
            unit.x, unit.y = cand["dest"]
            unit.hidden, unit.done = True, True
            self.state.emit("action", f"{self.world.name(unit.pid)} escapes", uid=unit.uid)
            return
        command = Act(unit.uid, cand["dest"], action, cand.get("target"), cand.get("item"))
        self.emit(f"acts: {cand['text']}")
        try:
            apply_command(self.world, self.state, command, by_ai=True)
        except ValueError as exc:
            self.state.emit("warn", f"AI action failed ({exc}); the unit waits")
            unit.done = True


def step(world: World, state: GameState, turn: AiTurn) -> bool:
    """One step of an AI unit's turn. Returns True when the turn is over."""
    return AiStep(world, state, turn).step()


def phase_order(world: World, state: GameState, faction: int) -> list:
    """The units of ``faction`` in the order they act: ``ai_order`` first,
    then faster units, then units with a staff or a weaker weapon."""
    rules = world.rules

    def key(u: SimUnit):
        _i, item = combat.equipped(world, u)
        speed = rules.attack_speed(combat.combatant(world, u, item))
        staff = 0 if combat.staff_items(world, u) else 1
        return (u.ai_order, -speed, staff, item.might if item is not None else 0, u.uid)

    return sorted((u for u in state.living(faction) if not u.done), key=key)
