"""The game loop as a queue of tasks, advanced one small step at a time.

:func:`step` runs the task at the front of :attr:`GameState.pending` for one
step: one bytecode instruction of an event script, one page of a message,
one entry of an AI script, one fight, one trigger check... A task that has
more to do stays at the front; work it starts (a conversation, the events a
fight triggers) is put in front of it, so it runs first, as in the game.

The turn: a phase starts (units of its side may act again, units on healing
terrain recover), its "before" then "after" phase events run, then the
player gives commands until the phase is ended, or the AI moves each unit of
the side in turn order. Phases go player, enemy, ally, partner; the ally and
partner phases are skipped while their side has no unit on the map.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from . import ai_vm, combat, event_vm, setup, triggers
from .actions import AfterAction, Combat
from .state import (ENEMY, PHASE_ORDER, PLAYER, AiPhase, AiTurn, GameState, MessageShow, PhaseEnd, PhaseStart,
                    Preparations, ScriptRun, Task, TriggerCheck)
from .world import World

TRIGGER_NAMES = {1: "goal achieved", 2: "goal failed", 3: "before phase", 4: "zone", 5: "location", 6: "after phase",
                 7: "after action", 8: "talk", 9: "battle", 10: "death (map)", 11: "death (battle)"}


@dataclass
class GoalCheck(Task):
    @property
    def title(self) -> str:
        return "Goal check"


@dataclass
class CantoReady(Task):
    uid: int
    left: int


@dataclass
class ChapterEnd(Task):
    result: str


@dataclass
class Step:
    """What one call of :func:`step` did."""

    kind: str  # script, message, ai, phase, trigger, battle, action, input, over, task
    title: str = ""
    where: str = ""  # the instruction / entry / page that ran
    outputs: list = field(default_factory=list)
    unit_done: bool = False  # an AI unit's turn ended
    task_done: bool = False


def step(world: World, state: GameState) -> Step:
    state.out = []
    if state.over:
        return Step("over", f"Chapter {state.over}")
    if not state.pending:
        if state.phase == PLAYER:
            return Step("input", "Player phase: waiting for a command")
        state.pending.append(PhaseEnd(state.phase))
    task = state.pending[0]
    handler = _HANDLERS.get(type(task))
    if handler is None:
        state.pending.pop(0)
        result = Step("task", task.title, task_done=True)
    else:
        result = handler(world, state, task)
    result.outputs = list(state.out)
    return result


def _done(state: GameState, task: Task, *new: Task) -> None:
    """Replace ``task`` (at the front) by ``new``."""
    if state.pending and state.pending[0] is task:
        state.pending.pop(0)
    state.push_front(*new)


# -- phases -----------------------------------------------------------------------------------------


def _phase_start(world: World, state: GameState, task: PhaseStart) -> Step:
    phase = task.phase
    state.phase = phase
    state.canto = None
    units = state.living(phase)
    if phase not in (PLAYER, ENEMY) and not units:
        _done(state, task, PhaseEnd(phase))
        return Step("phase", f"No {_phase_name(phase)} units: phase skipped", task_done=True)
    for u in units:
        u.done = False
        t = world.terrain_at(u.x, u.y)
        if t is not None and t.heal and u.hp < u.stats[0]:
            gain = min(u.stats[0] - u.hp, max(1, u.stats[0] * t.heal // 100))
            u.hp += gain
            state.emit("action", f"{world.name(u.pid)} recovers {gain} HP on {world.terrain_name(u.x, u.y)}",
                       uid=u.uid)
    state.emit("phase", f"Turn {state.turn}: {_phase_name(phase)} phase", turn=state.turn, phase=phase)
    tasks = [TriggerCheck(3, {"phase": phase}), TriggerCheck(6, {"phase": phase}), GoalCheck()]
    if phase != PLAYER:
        tasks.append(AiPhase(phase))
    _done(state, task, *tasks)
    return Step("phase", f"Turn {state.turn}, {_phase_name(phase)} phase", task_done=True)


def _phase_name(phase: int) -> str:
    return {PLAYER: "player", ENEMY: "enemy", 2: "ally", 3: "partner"}.get(phase, str(phase))


def _phase_end(world: World, state: GameState, task: PhaseEnd) -> Step:
    order = list(PHASE_ORDER)
    i = order.index(task.phase) if task.phase in order else 0
    nxt = order[(i + 1) % len(order)]
    if nxt == order[0]:
        state.turn += 1
    for u in state.living(task.phase):
        u.done = False
    _done(state, task, PhaseStart(nxt))
    return Step("phase", f"End of the {_phase_name(task.phase)} phase", task_done=True)


def _ai_phase(world: World, state: GameState, task: AiPhase) -> Step:
    order = ai_vm.phase_order(world, state, task.phase)
    if not order:
        _done(state, task, PhaseEnd(task.phase))
        return Step("phase", f"Every {_phase_name(task.phase)} unit has acted", task_done=True)
    unit = order[0]
    state.push_front(AiTurn(unit.uid))
    return Step("ai", f"Next: {world.name(unit.pid)}", where=f"{len(order)} unit(s) left")


def _ai_turn(world: World, state: GameState, task: AiTurn) -> Step:
    unit = state.units.get(task.uid)
    finished = ai_vm.step(world, state, task)
    if finished:
        if unit is not None:
            unit.done = True
        if state.pending and state.pending[0] is task:
            state.pending.pop(0)
        else:
            state.pending.remove(task)
    where = next((o.text for o in state.out if o.kind == "ai"), "")
    return Step("ai", f"AI: {world.name(unit.pid) if unit else task.uid}", where, unit_done=finished,
                task_done=finished)


# -- events -----------------------------------------------------------------------------------------


def _trigger(world: World, state: GameState, task: TriggerCheck) -> Step:
    found = triggers.matches(world, state, task.kind, task.ctx)
    runs = []
    for t in found:
        if t.type in triggers.ONCE:
            state.seen.add((t.script, t.function))
        ctx = dict(task.ctx)
        if "action" not in ctx and t.type == 5:
            ctx["action"] = t.params.get("action")
        runs.append(triggers.start(world, t.script, t.function, ctx=ctx))
    name = TRIGGER_NAMES.get(task.kind, str(task.kind))
    if runs:
        state.emit("trigger", f"{name} event: " + ", ".join(r.name for r in runs))
    _done(state, task, *runs)
    return Step("trigger", f"Check {name} events", ", ".join(r.name for r in runs) or "none", task_done=True)


def _script(world: World, state: GameState, task: ScriptRun) -> Step:
    if not task.frames:
        _done(state, task)
        return Step("script", task.title, "(empty)", task_done=True)
    finished, where, inserted = event_vm.step(world, state, task)
    if finished:
        _done(state, task, *inserted)
        state.emit("script", f"{task.name} finished")
    else:
        state.push_front(*inserted)
    return Step("script", task.title, where, task_done=finished)


def message_pages(text: str) -> tuple:
    """``(timeline, page event indices)`` of a message: every input wait, and the end."""
    from ..formats.fe9_conversation import build_timeline

    try:
        timeline = build_timeline(text)
    except Exception:  # noqa: BLE001 - a broken message still shows as one page
        return None, [0]
    pages = [e.index for e in timeline.events if e.wait]
    last = timeline.events[-1].index if timeline.events else 0
    if not pages or (pages[-1] != last and page_text(timeline, last) != page_text(timeline, pages[-1])):
        pages.append(last)
    return timeline, pages


def page_text(timeline, index: int) -> str:
    if timeline is None:
        return ""
    event = timeline.events[index]
    texts = [b.text for b in event.state.boxes if b.visible and b.text]
    return decode("\n".join(texts))


def decode(text: str) -> str:
    try:
        return text.encode("cp437").decode("shift_jis", errors="replace")
    except UnicodeEncodeError:
        return text


def _message(world: World, state: GameState, task: MessageShow) -> Step:
    timeline, pages = message_pages(task.text)
    if not task.pages:
        task.pages = pages
    if task.page >= len(task.pages):
        _done(state, task)
        return Step("message", task.title, "(end)", task_done=True)
    index = task.pages[task.page]
    task.page += 1
    text = page_text(timeline, index) if timeline is not None else decode(task.text)
    state.emit("message", text, msg_id=task.msg_id, event=index, page=task.page, pages=len(task.pages),
               raw=task.text)
    finished = task.page >= len(task.pages)
    if finished:
        _done(state, task)
    return Step("message", task.title, f"page {task.page}/{len(task.pages)}", task_done=finished)


# -- actions ----------------------------------------------------------------------------------------


def _combat(world: World, state: GameState, task: Combat) -> Step:
    attacker, defender = state.units.get(task.attacker), state.units.get(task.defender)
    _done(state, task)
    if attacker is None or defender is None or not attacker.on_map or not defender.on_map:
        return Step("battle", "Battle cancelled", task_done=True)
    combat.fight(world, state, attacker, defender, task.item, task.distance)
    after = []
    for unit, killer in ((defender, attacker), (attacker, defender)):
        if unit.hp <= 0 and not unit.dead:
            unit.dead = True
            state.emit("death", f"{world.name(unit.pid)} is defeated", uid=unit.uid)
            for item in list(unit.items):
                if item[2] and killer.faction == PLAYER and len(killer.items) < 8:
                    killer.items.append([item[0], item[1], False])
                    state.emit("action", f"{world.name(killer.pid)} gets {world.item_name(item[0])}")
            after += [TriggerCheck(11, {"pid": unit.pid, "me": unit.uid}),
                      TriggerCheck(10, {"pid": unit.pid, "me": unit.uid})]
    state.push_front(*after)
    return Step("battle", "Battle", task_done=True)


def _after_action(world: World, state: GameState, task: AfterAction) -> Step:
    unit = state.units.get(task.uid)
    tasks = []
    if unit is not None and unit.on_map:
        tasks.append(TriggerCheck(4, {"tile": unit.tile, "faction": unit.faction, "me": unit.uid,
                                      "x": unit.x, "y": unit.y}))
    tasks += [TriggerCheck(7, {"me": task.uid}), GoalCheck()]
    if task.canto and unit is not None and unit.on_map:
        tasks.append(CantoReady(task.uid, task.canto))
    _done(state, task, *tasks)
    return Step("action", "After the action", task_done=True)


def _canto_ready(world: World, state: GameState, task: CantoReady) -> Step:
    _done(state, task)
    state.canto = (task.uid, task.left)
    unit = state.units[task.uid]
    state.emit("log", f"{world.name(unit.pid)} may move {task.left} more (Canto)")
    return Step("action", "Canto", task_done=True)


def _goal_check(world: World, state: GameState, task: GoalCheck) -> Step:
    if state.get_flag("gf_complete"):
        _done(state, task, TriggerCheck(1, {}), ChapterEnd("complete"))
        return Step("trigger", "Goal achieved", task_done=True)
    if state.get_flag("gf_gameover"):
        _done(state, task, TriggerCheck(2, {}), ChapterEnd("gameover"))
        return Step("trigger", "Goal failed", task_done=True)
    if not state.living(PLAYER) and any(u.faction == PLAYER for u in state.units.values()):
        _done(state, task, ChapterEnd("gameover"))
        return Step("trigger", "Every player unit is gone", task_done=True)
    _done(state, task)
    return Step("trigger", "Goal check", "nothing", task_done=True)


def _chapter_end(world: World, state: GameState, task: ChapterEnd) -> Step:
    state.pending.clear()
    state.over = task.result
    state.emit("phase", f"Chapter {task.result}")
    return Step("over", f"Chapter {task.result}", task_done=True)


def _preparations(world: World, state: GameState, task: Preparations) -> Step:
    _done(state, task)
    if state.living(PLAYER):
        return Step("action", "Preparations", "player units already deployed", task_done=True)
    groups = setup.fallback_player_groups(world)
    for group in groups:
        setup.deploy(world, state, group, animate=False)
    note = ", ".join(groups) if groups else "no player section found"
    state.emit("log", f"The opening deployed no player unit: placed {note}")
    return Step("action", "Preparations", note, task_done=True)


_HANDLERS = {
    PhaseStart: _phase_start, PhaseEnd: _phase_end, AiPhase: _ai_phase, AiTurn: _ai_turn, TriggerCheck: _trigger,
    ScriptRun: _script, MessageShow: _message, Combat: _combat, AfterAction: _after_action, CantoReady: _canto_ready,
    GoalCheck: _goal_check, ChapterEnd: _chapter_end, Preparations: _preparations,
}
