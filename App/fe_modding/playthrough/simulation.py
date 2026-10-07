"""Stepping a playthrough, with a history to go back and forward through.

Every step and every command adds an entry: the state after it and what it
did. :meth:`Simulation.back` and :meth:`Simulation.forward` only move the
cursor; stepping or giving a command from an earlier entry drops the entries
after it and plays on from there. Play is deterministic - the random stream
is part of the state - so replaying the same commands from the same entry
gives the same game.

Copying the state for every entry is what costs time (a chapter opening runs thousands of script
instructions). Unless :attr:`Simulation.fine` is set, consecutive script instructions share one entry:
they run on a working copy that becomes an entry at the next step of another kind, or when
:meth:`Simulation.flush` is called (any navigation or command does).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Optional

from . import actions, engine
from .state import GameState
from .world import World

#: Granularities of :meth:`Simulation.run`.
LINE, MESSAGE, ACTION, UNIT, PHASE, INPUT = "line", "message", "action", "unit", "phase", "input"
MAX_ENTRIES = 20_000
MAX_RUN = 50_000


@dataclass
class Entry:
    state: GameState
    label: str
    steps: list = field(default_factory=list)  # engine.Step (or a command's outputs)

    @property
    def outputs(self) -> list:
        return [o for s in self.steps for o in s.outputs]


class Simulation:
    def __init__(self, world: World, state: GameState):
        self.world = world
        self.history: list[Entry] = [Entry(state.snapshot(), "Start")]
        self.cursor = 0
        self.dropped = 0  # entries removed from the front when the history grew too long
        self.fine = False  # one entry per script instruction (line-by-line stepping)
        self._live: Optional[GameState] = None  # script steps not stored yet (see the module docstring)
        self._live_steps: list = []

    # -- position -------------------------------------------------------------------------------
    @property
    def state(self) -> GameState:
        return self._live if self._live is not None else self.history[self.cursor].state

    def flush(self) -> None:
        """Store the script steps run since the last entry as one entry."""
        if self._live is not None:
            state, steps = self._live, self._live_steps
            self._live, self._live_steps = None, []
            if steps:
                self._append(state, steps[-1].title, steps)

    @property
    def entry(self) -> Entry:
        return self.history[self.cursor]

    @property
    def at_end(self) -> bool:
        return self.cursor == len(self.history) - 1

    def back(self, count: int = 1) -> None:
        self.flush()
        self.cursor = max(0, self.cursor - count)

    def forward(self, count: int = 1) -> None:
        self.flush()
        self.cursor = min(len(self.history) - 1, self.cursor + count)

    def goto(self, index: int) -> None:
        self.flush()
        self.cursor = max(0, min(len(self.history) - 1, index))

    def back_to(self, kinds: tuple) -> None:
        """Back to the previous entry whose step was one of ``kinds`` (e.g. a command or a phase)."""
        self.flush()
        for i in range(self.cursor - 1, -1, -1):
            if self._kind(self.history[i]) in kinds or i == 0:
                self.cursor = i
                return

    def forward_to(self, kinds: tuple) -> None:
        self.flush()
        for i in range(self.cursor + 1, len(self.history)):
            if self._kind(self.history[i]) in kinds:
                self.cursor = i
                return
        self.cursor = len(self.history) - 1

    def forward_by(self, until: str) -> bool:
        """Move forward through the recorded entries to the next ``until`` boundary.
        False when the end of the history came first."""
        self.flush()
        start = self.mark()
        while self.cursor < len(self.history) - 1:
            self.cursor += 1
            for result in self.entry.steps:
                if self.boundary(until, result, start):
                    return True
        return False

    @staticmethod
    def _kind(entry: Entry) -> str:
        return entry.steps[-1].kind if entry.steps else "start"

    # -- playing --------------------------------------------------------------------------------
    def _truncate(self) -> None:
        del self.history[self.cursor + 1:]

    def _append(self, state: GameState, label: str, steps: list) -> None:
        """Store ``state`` (a private copy nothing else changes) as the new last entry."""
        state.out = []
        self.history.append(Entry(state, label, steps))
        if len(self.history) > MAX_ENTRIES:
            drop = len(self.history) - MAX_ENTRIES
            del self.history[:drop]
            self.dropped += drop
        self.cursor = len(self.history) - 1

    def command(self, command) -> list:
        """Give a command at the current entry. Returns its outputs; raises
        :class:`actions.CommandError` when it isn't possible (the history is then kept)."""
        self.flush()
        state = self.state.snapshot()
        state.out = []
        actions.apply(self.world, state, command)
        self._truncate()
        outputs = list(state.out)
        self._append(state, _command_label(self.world, state, command),
                     [engine.Step("command", "Command", outputs=outputs)])
        return outputs

    def edit(self, change: Callable[[GameState], None], label: str) -> None:
        """Change the state at the current entry (a new entry; later ones are dropped)."""
        self.flush()
        self._truncate()
        state = self.state.snapshot()
        change(state)
        self._append(state, label, [engine.Step("command", label)])

    def step(self) -> engine.Step:
        """One engine step from the current entry."""
        self._truncate()
        if self._live is None:
            self._live = self.history[self.cursor].state.snapshot()
        state = self._live
        result = engine.step(self.world, state)
        if result.kind in ("input", "over") and not result.outputs:
            if not self._live_steps:
                self._live = None
            else:
                self.flush()
            return result  # nothing happened: no entry
        self._live_steps.append(result)
        if self.fine or result.kind != "script":
            self.flush()
        return result

    def run(self, until: str = INPUT, *, stop: Optional[Callable[[engine.Step], bool]] = None,
            limit: int = MAX_RUN) -> list:
        """Step until the granularity boundary ``until`` (or ``stop`` says so,
        or the player must give a command). Returns the steps."""
        done = []
        start = self.mark()
        for _ in range(limit):
            result = self.step()
            if result.kind in ("input", "over") and not result.outputs:
                break
            done.append(result)
            if (stop is not None and stop(result)) or self.boundary(until, result, start):
                break
        self.flush()
        return done

    def mark(self) -> tuple:
        """Where a run starts, for :meth:`boundary`."""
        return (self.state.turn, self.state.phase)

    def boundary(self, until: str, result: engine.Step, start: tuple) -> bool:
        """Whether a run to ``until`` that began at ``start`` (:meth:`mark`) stops after ``result``."""
        if result.kind == "over":
            return True
        if until == LINE:
            return True
        if until == MESSAGE and result.kind == "message":
            return True
        if until == ACTION and any(o.kind in ("action", "battle", "death", "message") for o in result.outputs):
            return True
        if until == UNIT and (result.unit_done or result.kind == "command"):
            return True
        if until == PHASE and self.mark() != start:
            return True
        return self.needs_input

    @property
    def needs_input(self) -> bool:
        """The player must give a command (a phase command or a Canto move)."""
        state = self.state
        return not state.pending and not state.over and (state.phase == 0 or state.canto is not None)


def _command_label(world: World, state: GameState, command) -> str:
    if isinstance(command, actions.EndPhase):
        return "End phase"
    unit = state.units.get(getattr(command, "uid", None))
    name = world.name(unit.pid) if unit is not None else "?"
    if isinstance(command, actions.CantoMove):
        return f"{name}: Canto to {command.dest}"
    return f"{name}: {command.action} at {command.dest}"
