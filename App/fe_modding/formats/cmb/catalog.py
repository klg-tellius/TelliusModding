"""What the script language knows about the game: trigger kinds (a
function's ``type`` + ``params``) and the extern functions scripts can call.

Extern names and argument counts come from ``main.dol``'s
``register_native_handler(name, handler, argc)`` calls (exported by
``research/main_dol/scripts/export/ExportExternCatalog.java``), plus the
named script functions ``startup.cmb`` exports. Argument *kinds* (PID,
message id, ...) are hints inferred from how the vanilla scripts call each
extern - they drive editor dropdowns and warnings, never compilation.
Everything lives in ``externs_fe9.json`` / ``externs_fe10.json`` next to this
module (regenerate with ``python -m fe_modding.formats.cmb.build_catalog``).

Both tables are per game: pass the script's :class:`~.model.Dialect` (or its
name). Radiant Dawn's trigger kinds come from its trigger checkers in
``main.dol`` (``research/rd/SCRIPT_NOTES.md``): types 8/9/19/20 take a
*condition* that is either a one-time flag or the name of a script function
that must return non-zero, type 14 is (event name, flag), and 17-20 are new.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Optional

# -- triggers ---------------------------------------------------------------

PHASES = {0: "player", 1: "enemy", 3: "partner"}
SIDES = {0: "player", 1: "enemy"}
ACTIONS = {9: "visit", 11: "door", 12: "chest", 13: "seize", 14: "escape", 37: "destroy_house", 41: "arrive", 44: "other"}
PHASES_FE10 = {0: "player", 1: "enemy", 2: "other"}
SIDES_FE10 = {0: "player", 1: "enemy", 2: "other"}
ACTIONS_FE10 = {9: "visit", 11: "door", 12: "chest", 13: "seize", 14: "escape", 38: "destroy", 42: "arrive",
                55: "light_torch", 58: "open", 59: "put_out_torch"}


@dataclass(frozen=True)
class TriggerParam:
    name: str
    kind: str  # int | label | pid | mpid | phase | side | action (+ _fe10 variants)
    description: str

    @property
    def is_label(self) -> bool:
        return self.kind in ("label", "pid", "mpid")

    @property
    def enum(self) -> Optional[dict]:
        return {"phase": PHASES, "side": SIDES, "action": ACTIONS, "phase_fe10": PHASES_FE10,
                "side_fe10": SIDES_FE10, "action_fe10": ACTIONS_FE10}.get(self.kind)


@dataclass(frozen=True)
class TriggerKind:
    type: int
    decorator: str
    title: str
    params: tuple = ()


def _p(name, kind, description):
    return TriggerParam(name, kind, description)


TRIGGERS: dict[int, TriggerKind] = {t.type: t for t in [
    TriggerKind(0, "", "Callable (not triggered automatically)"),
    TriggerKind(1, "on_complete", "Map goal achieved", (_p("flag", "label", "Flag watched (always \"gf_complete\" in vanilla)"),)),
    TriggerKind(2, "on_gameover", "Map goal failed", (_p("flag", "label", "Flag watched (always \"gf_gameover\" in vanilla)"),)),
    TriggerKind(3, "before_phase", "Before a phase starts", (
        _p("turn_from", "int", "First turn (0 = every turn)"),
        _p("turn_to", "int", "Last turn"),
        _p("phase", "phase", "Phase"),
    )),
    TriggerKind(4, "on_area", "A unit enters a zone", (
        _p("x1", "int", "Zone left X"), _p("y1", "int", "Zone top Y"),
        _p("x2", "int", "Zone right X"), _p("y2", "int", "Zone bottom Y"),
        _p("side", "side", "Which side triggers it"),
        _p("name", "label", "Event name (debug label)"),
    )),
    TriggerKind(5, "on_location", "A unit acts at a map location", (
        _p("x", "int", "Location X"), _p("y", "int", "Location Y"),
        _p("action", "action", "Action"),
        _p("name", "label", "Event name (debug label)"),
    )),
    TriggerKind(6, "on_phase", "After a phase starts", (
        _p("turn_from", "int", "First turn (0 = every turn)"),
        _p("turn_to", "int", "Last turn"),
        _p("phase", "phase", "Phase"),
    )),
    TriggerKind(7, "after_action", "Checked after every action"),
    TriggerKind(8, "on_talk", "Two units talk", (
        _p("pid1", "pid", "Character 1"), _p("pid2", "pid", "Character 2"),
        _p("flag", "int", "1 = either unit may start the talk; 0 = only Character 1, to Character 2"),
        _p("name", "label", "One-time flag: the event is skipped while this flag is set"),
    )),
    TriggerKind(9, "on_battle", "A fight starts between two units", (
        _p("pid1", "pid", "Character 1"), _p("pid2", "pid", "Character 2 (None = anyone)"),
        _p("flag", "int", "1 = each character may be on either side; 0 = Character 1 must attack Character 2"),
        _p("name", "label", "One-time flag: the event is skipped while this flag is set"),
    )),
    TriggerKind(10, "on_death_map", "A unit's death, handled back on the map", (_p("pid", "pid", "Character"),)),
    TriggerKind(11, "on_death", "A unit dies in battle", (_p("pid", "pid", "Character"),)),
    TriggerKind(12, "on_scenario_end", "Scenario complete", (_p("name", "label", "Event name (debug label)"),)),
    TriggerKind(13, "on_support", "Support conversation", (
        _p("pid1", "pid", "Character 1"), _p("pid2", "pid", "Character 2"),
        _p("level", "int", "Support level: 1 = C, 2 = B, 3 = A"),
    )),
    TriggerKind(14, "on_base_talk", "Base conversation", (
        _p("flag", "label", "Info flag name"),
        _p("mpid", "mpid", "Character (MPID_)"),
        _p("stars", "int", "Number of stars"),
    )),
    TriggerKind(15, "on_select", "Selecting a unit"),
]}
TRIGGERS_BY_DECORATOR = {t.decorator: t for t in TRIGGERS.values() if t.decorator}

_COND = "One-time flag (skipped once set), or the name of a script function that must return non-zero"
TRIGGERS_FE10: dict[int, TriggerKind] = {t.type: t for t in [
    TRIGGERS[0], TRIGGERS[1], TRIGGERS[2],
    TriggerKind(3, "before_phase", "Before a phase starts", (
        _p("turn_from", "int", "First turn (0 = every turn)"),
        _p("turn_to", "int", "Last turn"),
        _p("phase", "phase_fe10", "Phase (65535 = any)"),
    )),
    TriggerKind(4, "on_area", "A unit enters a zone", (
        _p("x1", "int", "Zone left X"), _p("y1", "int", "Zone top Y"),
        _p("x2", "int", "Zone right X (0 or less counts from the right edge)"),
        _p("y2", "int", "Zone bottom Y (0 or less counts from the bottom edge)"),
        _p("side", "side_fe10", "Which army triggers it (65535 = any)"),
        _p("name", "label", "One-time flag: skipped once set"),
    )),
    TriggerKind(5, "on_location", "A unit acts at a map location", (
        _p("x", "int", "Location X"), _p("y", "int", "Location Y"),
        _p("action", "action_fe10", "Action"),
        _p("name", "label", "One-time flag: skipped once set"),
    )),
    TriggerKind(6, "on_phase", "After a phase starts", (
        _p("turn_from", "int", "First turn (0 = every turn)"),
        _p("turn_to", "int", "Last turn"),
        _p("phase", "phase_fe10", "Phase (65535 = any)"),
    )),
    TRIGGERS[7],
    TriggerKind(8, "on_talk", "Two units talk", (
        _p("pid1", "pid", "Character 1"), _p("pid2", "pid", "Character 2"),
        _p("flag", "int", "1 = either unit may start the talk; 0 = only Character 1, to Character 2"),
        _p("name", "label", _COND),
    )),
    TriggerKind(9, "on_battle", "A fight starts between two units", (
        _p("pid1", "pid", "Character 1"), _p("pid2", "pid", "Character 2 (None = anyone)"),
        _p("flag", "int", "1 = each character may be on either side; 0 = Character 1 must attack Character 2"),
        _p("name", "label", _COND),
    )),
    TRIGGERS[10], TRIGGERS[11], TRIGGERS[12], TRIGGERS[13],
    TriggerKind(14, "on_base_talk", "Base conversation", (
        _p("name", "label", "Event name (FE10Conversation.cms CONV_INFO_DATA_<chapter>_<name>)"),
        _p("flag", "label", "Flag the Base menu reads for this conversation"),
    )),
    TRIGGERS[15],
    TriggerKind(16, "on_named", "Run by name (support conversations without a type-13 event)", (
        _p("name", "label", "Event name"),
    )),
    TriggerKind(17, "on_rescue", "A unit rescues another (Rescue command)", (
        _p("pid1", "pid", "Rescuer (None = anyone)"), _p("pid2", "pid", "Rescued unit (None = anyone)"),
        _p("flag", "int", "1 = the two characters may be swapped"),
        _p("name", "label", "One-time flag: skipped once set"),
    )),
    TriggerKind(18, "on_give_take", "A carried unit is given or taken (Give / Take commands)", (
        _p("pid1", "pid", "Unit carrying (None = anyone)"), _p("pid2", "pid", "Other unit (None = anyone)"),
        _p("pid3", "pid", "Carried unit (None = anyone)"),
        _p("flag", "int", "1 = the first two characters may be swapped"),
        _p("name", "label", "One-time flag: skipped once set"),
    )),
    TriggerKind(19, "on_move_through", "A moving unit enters a tile (the move stops there)", (
        _p("pid", "pid", "Character"), _p("x", "int", "Tile X (65535 = any)"), _p("y", "int", "Tile Y (65535 = any)"),
        _p("name", "label", _COND + " (called with x, y)"),
    )),
    TriggerKind(20, "on_epilogue", "A character's epilogue entry", (
        _p("pid", "pid", "Character (None = anyone)"),
        _p("name", "label", _COND),
    )),
]}
TRIGGERS_BY_DECORATOR_FE10 = {t.decorator: t for t in TRIGGERS_FE10.values() if t.decorator}


def _dialect_name(dialect) -> str:
    return dialect if isinstance(dialect, str) else getattr(dialect, "name", "fe9")


def triggers(dialect="fe9") -> dict[int, TriggerKind]:
    """Trigger kinds by function type for a dialect (or its name)."""
    return TRIGGERS_FE10 if _dialect_name(dialect) == "fe10" else TRIGGERS


def triggers_by_decorator(dialect="fe9") -> dict[str, TriggerKind]:
    return TRIGGERS_BY_DECORATOR_FE10 if _dialect_name(dialect) == "fe10" else TRIGGERS_BY_DECORATOR

# Named entry points the engine runs automatically, whatever their type.
SPECIAL_ENTRY_POINTS = {
    "Startup": "Runs when the chapter loads",
    "Opening0": "Runs right after Startup",
    "Opening2": "Runs after preparations end",
}

# -- externs ----------------------------------------------------------------

ARG_KINDS = ("int", "str", "pid", "iid", "jid", "mpid", "mess", "bgm", "sfx", "flag", "addr")


@dataclass
class ExternSig:
    name: str
    argc: int
    source: str  # "native" | "script"
    group: str = ""  # registration hub / defining script
    args: list = field(default_factory=list)  # [{"name":..., "kind":...}]
    uses: int = 0
    note: str = ""

    def arg_kind(self, i: int) -> str:
        return self.args[i]["kind"] if i < len(self.args) else "int"

    def signature(self) -> str:
        names = [a.get("name") or f"arg{i}" for i, a in enumerate(self.args)] or [f"arg{i}" for i in range(self.argc)]
        parts = [f"{n}: {self.arg_kind(i)}" for i, n in enumerate(names[:self.argc])]
        return f"{self.name}({', '.join(parts)})"


CATALOG_PATHS = {"fe9": Path(__file__).with_name("externs_fe9.json"),
                 "fe10": Path(__file__).with_name("externs_fe10.json")}
CATALOG_PATH = CATALOG_PATHS["fe9"]


def load_externs(dialect="fe9") -> dict[str, ExternSig]:
    return _load_externs(_dialect_name(dialect))


@lru_cache(maxsize=None)
def _load_externs(name: str) -> dict[str, ExternSig]:
    path = CATALOG_PATHS[name]
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    return {key: ExternSig(name=key, **entry) for key, entry in data["externs"].items()}


def lookup_extern(name: str, dialect="fe9") -> Optional[ExternSig]:
    return load_externs(dialect).get(name)
