"""Everything that changes while a chapter plays, as plain data.

A :class:`GameState` holds the units, the turn and phase, the event flags,
the script globals, the random-number stream and the queue of pending work
(:class:`Task` s: phase changes, trigger checks, running event scripts,
messages, AI runs). Nothing in it is a generator or a callback, so
``copy.deepcopy`` gives a complete snapshot and restoring one rewinds play.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, field
from typing import Optional

from ..battle_sim import Fe9Rng
from ..formats.event_flags import ENGINE_FLAGS

PLAYER, ENEMY, ALLY, PARTNER = 0, 1, 2, 3
FACTION_NAMES = {PLAYER: "Player", ENEMY: "Enemy", ALLY: "Ally", PARTNER: "Partner"}
#: The phases in turn order; each is the faction that acts in it.
PHASE_ORDER = (PLAYER, ENEMY, ALLY, PARTNER)
FLAG_SLOTS = 96
GLOBAL_SLOTS = 32


def relation(a: int, b: int) -> str:
    """``same``, ``opposing`` (either side is the enemy) or ``other``
    (the archive's ``armies-allegiance`` article)."""
    if a == b:
        return "same"
    if ENEMY in (a, b):
        return "opposing"
    return "other"


def hostile(a: int, b: int) -> bool:
    return relation(a, b) == "opposing"


@dataclass
class SimUnit:
    uid: int
    pid: str
    jid: str
    faction: int
    x: int
    y: int
    level: int = 1
    stats: list = field(default_factory=lambda: [20] + [5] * 7)  # maximums, STAT_NAMES order
    hp: int = 20
    build: int = 5
    move: int = 5
    movement_type: int = 1
    skills: list = field(default_factory=list)  # SID_ labels
    categories: list = field(default_factory=list)  # class category tokens
    items: list = field(default_factory=list)  # [iid, uses, drops]
    seq_attack: object = 0
    seq_move: object = 0
    seq_heal: object = 0
    mtype: object = 0
    ai_pc: list = field(default_factory=lambda: [0, 0])  # attack / move program counters
    ai_order: int = 0
    route: int = 0  # next waypoint of FOLLOW_ROUTE
    flags: int = 0  # dispo field 38
    group: str = ""  # the dispo section that deployed the unit
    exp: int = 0
    done: bool = False  # acted this phase
    dead: bool = False
    hidden: bool = False  # off the map (not deployed yet, or removed by a script)
    boss: bool = False

    @property
    def tile(self) -> tuple:
        return (self.x, self.y)

    @property
    def on_map(self) -> bool:
        return not self.dead and not self.hidden


# -- tasks ----------------------------------------------------------------------------------------


@dataclass
class Task:
    """One piece of pending work at the front of :attr:`GameState.pending`."""

    @property
    def title(self) -> str:
        return type(self).__name__


@dataclass
class PhaseStart(Task):
    phase: int


@dataclass
class Preparations(Task):
    """After the opening events: when they deployed no player unit, the
    deployment file's player sections are placed (the preparations' default)."""


@dataclass
class PhaseEnd(Task):
    phase: int


@dataclass
class AiPhase(Task):
    """Picks the next unit of the phase's faction to act, until none is left."""

    phase: int


@dataclass
class TriggerCheck(Task):
    """Look for script functions of trigger ``kind`` that match ``ctx``
    (evaluated when reached, so flags set by earlier events count)."""

    kind: int
    ctx: dict = field(default_factory=dict)


@dataclass
class Frame:
    script: int  # index into World.scripts
    function: int  # index into the script's functions
    pc: int = 0  # index into the function's instruction list
    stack: list = field(default_factory=list)
    locals: list = field(default_factory=list)


@dataclass
class ScriptRun(Task):
    """A running event function: a call stack of :class:`Frame` s."""

    frames: list
    ctx: dict = field(default_factory=dict)  # me, target, x, y of the event
    name: str = ""
    executed: int = 0  # instructions run so far

    @property
    def title(self) -> str:
        return f"Script {self.name}"


@dataclass
class MessageShow(Task):
    """A conversation, shown one page (wait point) per step."""

    msg_id: str
    text: str = ""
    page: int = 0  # pages already shown
    pages: list = field(default_factory=list)  # filled on the first step

    @property
    def title(self) -> str:
        return f"Message {self.msg_id}"


@dataclass
class AiTurn(Task):
    """One AI unit's turn: its heal check, attack script and move script."""

    uid: int
    stage: str = "start"  # start, attack, move, act, done
    pc: int = 0
    steps: int = 0  # entries run in the current script (capped at 256)
    found: bool = False
    candidate: Optional[dict] = None  # the registered action
    registers: list = field(default_factory=lambda: [0, 0, 0, 0])
    threat_limit: int = 0xFFFF
    script: str = ""  # the running script's section name
    fallback: bool = False
    restarts: int = 0  # SET_SCRIPTS restarts this turn

    @property
    def title(self) -> str:
        return f"AI unit {self.uid}"


# -- state ----------------------------------------------------------------------------------------


@dataclass
class GameState:
    units: dict = field(default_factory=dict)  # uid -> SimUnit
    next_uid: int = 1
    turn: int = 1
    phase: int = PLAYER
    flags: list = field(default_factory=lambda: [[name, False] for name in ENGINE_FLAGS]
                        + [[None, False] for _ in range(FLAG_SLOTS - len(ENGINE_FLAGS))])
    globals: list = field(default_factory=lambda: [0] * GLOBAL_SLOTS)
    rng: Fe9Rng = field(default_factory=Fe9Rng)
    pending: list = field(default_factory=list)  # Task, front first
    seen: set = field(default_factory=set)  # (script, function) of one-time events that fired
    visited: set = field(default_factory=set)  # (x, y) of villages already visited (or destroyed)
    opened: set = field(default_factory=set)  # (x, y) of doors and chests opened
    dialog_result: int = 0
    canto: Optional[tuple] = None  # (uid, movement left) while a unit may still move after acting
    forced: Optional[dict] = None  # outcome choices for the next battle (battle_sim.FixedOutcomes keys)
    money: int = 0
    fog: bool = False  # show only what the player's units can see (a view; see fog.py)
    choice_plan: list = field(default_factory=list)  # entries to pick at the next choice dialogs, in order (0-based)
    deploy_only: Optional[list] = None  # PIDs the preparations place (None: every unit of the player's sections)
    over: str = ""  # "complete" / "gameover" once the chapter ended
    out: list = field(default_factory=list)  # what the last step did (cleared every step): Output

    # -- units ----------------------------------------------------------------------------------
    def add_unit(self, unit: SimUnit) -> SimUnit:
        unit.uid = self.next_uid
        self.next_uid += 1
        self.units[unit.uid] = unit
        return unit

    def unit_at(self, x: int, y: int) -> Optional[SimUnit]:
        for u in self.units.values():
            if u.on_map and u.x == x and u.y == y:
                return u
        return None

    def unit_by_pid(self, pid) -> Optional[SimUnit]:
        alive = [u for u in self.units.values() if u.pid == pid and not u.dead]
        return next((u for u in alive if u.on_map), alive[0] if alive else None)

    def living(self, faction: Optional[int] = None) -> list:
        return [u for u in self.units.values() if u.on_map and (faction is None or u.faction == faction)]

    # -- flags ----------------------------------------------------------------------------------
    def flag_slot(self, name: str) -> Optional[int]:
        for i, (n, _value) in enumerate(self.flags):
            if n == name:
                return i
        return None

    def get_flag(self, name: str) -> bool:
        slot = self.flag_slot(name)
        return slot is not None and self.flags[slot][1]

    def set_flag(self, name: str, value: bool = True) -> bool:
        """Set or clear a registered flag; an unregistered name does nothing."""
        slot = self.flag_slot(name)
        if slot is None:
            return False
        self.flags[slot][1] = bool(value)
        return True

    def register_flag(self, name: str, *, from_top: bool) -> int:
        """``regist`` (highest free slot, from_top) or ``global`` (lowest free slot)."""
        slot = self.flag_slot(name)
        if slot is not None:
            return slot
        order = range(FLAG_SLOTS - 1, -1, -1) if from_top else range(FLAG_SLOTS)
        for i in order:
            if self.flags[i][0] is None:
                self.flags[i] = [name, False]
                return i
        return -1

    # -- queue ----------------------------------------------------------------------------------
    def push_front(self, *tasks: Task) -> None:
        self.pending[0:0] = list(tasks)

    def emit(self, kind: str, text: str = "", **data) -> None:
        self.out.append(Output(kind, text, data))

    @property
    def awaiting_input(self) -> bool:
        return not self.pending and self.phase == PLAYER and not self.over

    def snapshot(self) -> "GameState":
        out, self.out = self.out, []
        try:
            return copy.deepcopy(self)
        finally:
            self.out = out


@dataclass
class Output:
    """Something a step did, for the log and the window: ``kind`` is one of
    log, action, battle, death, message, script, ai, phase, trigger, warn."""

    kind: str
    text: str = ""
    data: dict = field(default_factory=dict)
