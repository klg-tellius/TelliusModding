"""Radiant Dawn (RFEE01) natives the shared handlers in :mod:`.natives` do not cover.

Each handler follows the native's description in ``formats/cmb/externs_fe10.json`` (written from
the decompiled RFEE01 handler, see ``research/rd/SCRIPT_NOTES.md``) and how vanilla
``startup.cmb`` uses it. Records the simulator does not otherwise model (the convoys, tile
effects, Library flags, battle-map values, unit push buffers...) live in
:attr:`GameState.fe10`, so they rewind with the rest of the state. Where a native's effect is
kept but not played out (a tile effect does not change movement, a scripted strike does not
force its outcome), the call is logged with ``warn`` so the run says so.

The event clock: every ``yield`` is one frame (:attr:`GameState.frame`); ``GetFrame`` and
``GetTime`` read it, so startup.cmb's wait loops (``CameraMoveWait``, ``WaitM``...) end.
"""

from __future__ import annotations

import copy

from . import setup
from .natives import (FE10_HANDLERS, _choice, _class_change, _dispos, _escape, _force_members, _name, _place,
                      _sally, _unit)
from .state import PLAYER

#: Flag slots 0-26 are the engine's and startup.cmb's RegistGlobalFlags'; chapter flags start above.
GLOBAL_FLAG_SLOTS = 27
#: Tile-effect types the handlers name (the table at 0x803CB770).
TT_FRAGILE, TT_LAVA, TT_BOMBER, TT_TERRAIN_NAME, TT_TERRAIN = 4, 0x0E, 0x0F, 0x10, 0x11
#: UnitTstStatus bits the simulator can answer (unit +0x10C).
ST_CARRYING, ST_CARRIED, ST_LEADER, ST_ESCAPED, ST_DEAD, ST_NEVER_SALLY = 0x2, 0x4, 0x100, 0x4000, 0x8000, 0x200000
#: UnitMoveDir step digits (numeric keypad directions).
_DIR_STEPS = {"2": (0, 1), "4": (-1, 0), "6": (1, 0), "8": (0, -1)}
#: UnitDropOff / UnitPush direction bits.
_DIR_BITS = {1: (-1, 0), 2: (1, 0), 4: (0, 1), 8: (0, -1)}


def fe10(name, *aliases):
    def register(fn):
        for n in (name,) + aliases:
            FE10_HANDLERS[n] = fn
        return fn
    return register


def _rec(vm, key: str, default):
    """A record in ``state.fe10`` (created on first use)."""
    return vm.state.fe10.setdefault(key, default)


def _not_played(vm, text: str) -> None:
    vm.state.emit("warn", f"{text} (kept, not played out by the simulator)")


def _const(value: int):
    def handler(vm, a):
        return value
    return handler


# -- build switches and debug stubs -----------------------------------------------------------------

FE10_HANDLERS.update({
    "IsFinalVersion": _const(1),  # always 1 in the retail game
    "IsPrivateViewVersion": _const(0), "IsShowVersion": _const(0),  # preview / trade-show builds
    "IsJPVersion": _const(0),  # 0 on the US disc (EU/JP native tables are not checked yet)
    "SysGetEventFlag": _const(1),  # debug stub, always 1
    "DumpUnit": _const(0), "SetCameraDisp": _const(0),  # debug stubs
    "Warning": _const(1),  # debug message, ignored in retail; returns 1
    "ScriptDbgMenu": _const(0), "ScriptDbgMenuResult": _const(0),  # registered nowhere: the VM answers 0
    # A fresh game with no Path of Radiance clear data and an empty system save.
    "IsInheritFE8Data": _const(0), "FE8UnitCheckExistsByPID": _const(0), "TstConversationFlag": _const(0),
    "IsConversationRoom": _const(0),  # chapters do not run in the conversation room
    # Byte +0x34 of the game state, by its name the playthrough round: the first one, like SysGetRound.
    "GameGetRound": _const(0),
})


@fe10("GetFrame")
def _frame(vm, a):
    return vm.state.frame


@fe10("GetTime")
def _time(vm, a):
    return vm.state.frame * 1000 // 60


# -- deployment ------------------------------------------------------------------------------------

# startup.cmb's Dispos / InstantDispos family: mode 0 normal, 1 First (exact tiles), 2 Continue
# (units already on the map move to their second position), 3 Warp.
_DISPOS_MODES = {0: {}, 1: {"exact": True}, 2: {"existing_only": True}, 3: {}}


def _dispos_mode(animate: bool):
    def handler(vm, a):
        mode = int(a[1]) if len(a) > 1 else 0
        return _dispos(animate=animate, **_DISPOS_MODES.get(mode, {}))(vm, a[:1])
    return handler


FE10_HANDLERS.update({"_dispos": _dispos_mode(True), "_idispos": _dispos_mode(False)})


@fe10("DisposGetRankGroup")
def _rank_group(vm, a):
    # The difficulty's entry of a group (dispos_n.bin holds "<group>_n", dispos_h.bin "<group>_h");
    # "" when the chapter has none, which startup.cmb's *Rank helpers test for.
    name = f"{a[0]}_{vm.world.difficulty}"
    return name if name in vm.world.groups else ""


@fe10("SallySetByGroupRank", "SallyAddByGroupRank")
def _sally_rank(vm, a):
    group = _rank_group(vm, a)
    return _sally(vm, [group]) if group else 0


@fe10("IsDispos")
def _is_dispos(vm, a):
    # DisposWait loops while this is non-zero; the simulator's deployments finish at once.
    return 0


@fe10("SetPreSallyFlag")
def _pre_sally(vm, a):
    vm.state.fe10["pre_sally"] = int(a[0])
    return 1


@fe10("UnitNeverSally")
def _never_sally(vm, a):
    unit = _unit(vm, a[0])
    if unit is not None and unit.force in (0, 5, 6):
        _rec(vm, "never_sally", set()).add(unit.uid)
    return 1


@fe10("UnitCanParty")
def _can_party(vm, a):
    unit = _unit(vm, a[0])
    return int(unit is not None and not unit.dead and unit.uid not in vm.state.fe10.get("never_sally", ()))


# -- unit lookups ----------------------------------------------------------------------------------


@fe10("ForceUnitGetByPID")
def _force_pid(vm, a):
    unit = next((u for u in _force_members(vm, int(a[0])) if u.pid == a[1]), None)
    return unit.uid if unit is not None else 0


@fe10("UnitGetHero")
def _hero(vm, a):
    members = _force_members(vm, PLAYER)
    return members[0].uid if members else 0


@fe10("UnitGetDie")
def _die(vm, a):
    return vm.ctx.get("die", 0)


@fe10("MindSetMind")
def _set_mind(vm, a):
    vm.ctx["me"] = a[0]
    return 0


def _carrier_of(vm, unit):
    return next((u for u in vm.state.units.values() if u.rescue_partner == unit.uid), None)


@fe10("UnitGetParent")
def _parent(vm, a):
    unit = _unit(vm, a[0])
    carrier = _carrier_of(vm, unit) if unit is not None else None
    return carrier.uid if carrier is not None else 0


def _status_word(vm, unit) -> int:
    bits = 0
    if unit.rescue_partner is not None:
        bits |= ST_CARRYING
    if _carrier_of(vm, unit) is not None:
        bits |= ST_CARRIED
    if unit.boss:
        bits |= ST_LEADER
    if unit.dead:
        bits |= ST_DEAD
    elif unit.hidden and unit.uid in vm.state.fe10.get("escaped", ()):
        bits |= ST_ESCAPED
    if unit.uid in vm.state.fe10.get("never_sally", ()):
        bits |= ST_NEVER_SALLY
    return bits


@fe10("UnitTstStatus")
def _tst_status(vm, a):
    unit = _unit(vm, a[0])
    return _status_word(vm, unit) & int(a[1]) if unit is not None else 0


@fe10("UnitGetBelongCount")
def _belong_count(vm, a):
    groups = vm.state.fe10.get("belong", {})
    return sum(1 for u in vm.state.living() if u.faction == PLAYER and groups.get(u.uid, 0) == int(a[0]))


@fe10("UnitSetOrigin")
def _set_origin(vm, a):
    unit = _unit(vm, a[0])
    if unit is not None:
        _rec(vm, "origin", {})[unit.uid] = int(a[1])
    return 0


def _died(force: int):
    def handler(vm, a):
        return sum(1 for u in vm.state.units.values() if u.dead and u.force == force)
    return handler


FE10_HANDLERS.update({"GetNumDiedPlayers": _died(0), "GetNumDiedEnemies": _died(1),
                      "GetNumDiedBrothers": _died(2), "GetNumDiedThirds": _died(3)})


# -- unit state ------------------------------------------------------------------------------------


@fe10("InstantUnitClassChange")
def _instant_cc(vm, a):
    unit = _unit(vm, a[0])
    if unit is None or "SID_EVENT_CC" not in unit.skills:
        return 0
    before = unit.jid
    _class_change(vm, a)
    return int(unit.jid != before)


@fe10("UnitTransform", "InstantUnitTransform")
def _transform(vm, a):
    unit = _unit(vm, a[0])
    if unit is not None:
        unit.transformed = bool(a[1])
        vm.state.emit("action", f"{_name(vm, unit)} {'transforms' if unit.transformed else 'reverts'}",
                      uid=unit.uid)
    return 0


@fe10("UnitResetStatus")
def _reset_status(vm, a):
    unit = _unit(vm, a[0])
    if unit is not None:
        unit.status, unit.status_turns = "", 0
    return 0


@fe10("UnitResetStatusWholeForce")
def _reset_force(vm, a):
    for unit in _force_members(vm, int(a[0])):
        unit.status, unit.status_turns = "", 0
    return 0


@fe10("UnitRunAway")
def _run_away(vm, a):
    unit = _unit(vm, a[0])
    if unit is not None:
        _rec(vm, "escaped", set()).add(unit.uid)
    return _escape(vm, a[:1])


@fe10("UnitAddSkillWhatever")
def _add_skill_whatever(vm, a):
    unit = _unit(vm, a[0])
    if unit is not None and isinstance(a[1], str) and a[1] not in unit.skills:
        unit.skills.append(a[1])  # the skill-capacity trimming is not modelled
    return 0


@fe10("UnitReorderSkill")
def _reorder_skill(vm, a):
    return 0  # the simulator's skill list has no display order


@fe10("_gs")
def _get_skill(vm, a):
    # The step behind startup.cmb's UnitGetSkillShowing(unit, sid): vanilla passes a SID.
    unit = _unit(vm, a[0])
    if unit is not None and isinstance(a[1], str) and a[1] not in unit.skills:
        unit.skills.append(a[1])
        vm.state.emit("action", f"{_name(vm, unit)} learns {a[1]}", uid=unit.uid)
    return 1


@fe10("PersonGetYellLevel")
def _yell(vm, a):
    return vm.state.fe10.get("support", {}).get(tuple(sorted((str(a[0]), str(a[1])))), 0)


@fe10("PersonSetYellLevel")
def _set_yell(vm, a):
    _rec(vm, "support", {})[tuple(sorted((str(a[0]), str(a[1]))))] = int(a[2])
    return 0


# -- AI flags --------------------------------------------------------------------------------------


@fe10("UnitSetCpForceNoMoveFlag")
def _no_move(vm, a):
    unit = _unit(vm, a[0])
    if unit is None or unit.faction == PLAYER:
        return 0
    if a[1] and "force_no_move" not in unit.ai_state:
        unit.ai_state["force_no_move"] = unit.seq_move
        unit.seq_move, unit.ai_pc[1] = "SEQ_NOMOVE", 0
    elif not a[1] and "force_no_move" in unit.ai_state:
        unit.seq_move, unit.ai_pc[1] = unit.ai_state.pop("force_no_move"), 0
    vm.state.emit("script", f"{_name(vm, unit)}: never move = {int(bool(a[1]))}")
    return 0


@fe10("UnitSetCpTwiceMoveSeq")
def _twice_move(vm, a):
    unit = _unit(vm, a[0])
    if unit is None or unit.faction == PLAYER:
        return 0
    unit.ai_state["twice_move_seq"] = a[1]
    _not_played(vm, f"{_name(vm, unit)}: AI second-move sequence {a[1]}")
    return 1


# -- carrying (rescue, give, drop) -----------------------------------------------------------------


def _free(unit) -> bool:
    return unit is not None and unit.on_map and unit.rescue_partner is None


@fe10("UnitRescue", "UnitPairup")
def _rescue(vm, a):
    carrier, carried = _unit(vm, a[0]), _unit(vm, a[1])
    if not _free(carrier) or not _free(carried) or _carrier_of(vm, carrier) is not None:
        return 0
    carrier.rescue_partner, carried.hidden = carried.uid, True
    carried.x, carried.y = carrier.tile
    vm.state.emit("action", f"{_name(vm, carrier)} carries {_name(vm, carried)}", uid=carrier.uid)
    return 1


def _put_down(vm, carrier, tile) -> int:
    carried = vm.state.units.get(carrier.rescue_partner)
    carrier.rescue_partner = None
    if carried is None:
        return 0
    _place(vm, carried, tile[0], tile[1], "is put down at")
    return 1


@fe10("UnitBreakup")
def _breakup(vm, a):
    unit = _unit(vm, a[0])
    if unit is None:
        return 0
    carrier = unit if unit.rescue_partner is not None else _carrier_of(vm, unit)
    return _put_down(vm, carrier, carrier.tile) if carrier is not None else 0


@fe10("UnitDropOff")
def _drop_off(vm, a):
    carrier = _unit(vm, a[0])
    if carrier is None or carrier.rescue_partner is None:
        return 0
    dx, dy = _DIR_BITS.get(int(a[1]), (0, 0))
    return _put_down(vm, carrier, (carrier.x + dx, carrier.y + dy))


@fe10("UnitChildSend")
def _child_send(vm, a):
    source, receiver = _unit(vm, a[0]), _unit(vm, a[1])
    if source is None or receiver is None or source.rescue_partner is None or receiver.rescue_partner is not None:
        return 0
    source.rescue_partner, receiver.rescue_partner = None, source.rescue_partner
    return 1


# -- scripted movement (teleported to where the walk ends) -----------------------------------------


@fe10("UnitMoveRoute")
def _move_route(vm, a):
    unit = _unit(vm, a[0])
    numbers = [int(n) for n in str(a[1]).replace(" ", "").split(",") if n.lstrip("-").isdigit()]
    if unit is None or len(numbers) < 2:
        return 0
    _place(vm, unit, numbers[-2], numbers[-1], "walks to")
    return 1


@fe10("UnitMoveDir")
def _move_dir(vm, a):
    unit = _unit(vm, a[0])
    if unit is None:
        return 0
    x, y = unit.tile
    for step in str(a[1]):
        dx, dy = _DIR_STEPS.get(step, (0, 0))
        x, y = x + dx, y + dy
    _place(vm, unit, x, y, "walks to")
    return 1


@fe10("UnitPush")
def _push(vm, a):
    unit = _unit(vm, a[0])
    if unit is None:
        return 0
    dx, dy = _DIR_BITS.get(int(a[1]), (0, 0))
    tiles = int(a[2])
    _place(vm, unit, unit.x + dx * tiles, unit.y + dy * tiles, "slides to")
    return 1


# -- saving and restoring units (event scenes, tutorials) ------------------------------------------


def _unit_snapshot(state) -> dict:
    return {"units": copy.deepcopy(state.units), "next_uid": state.next_uid}


def _restore_units(state, saved: dict) -> None:
    state.units, state.next_uid = saved["units"], max(state.next_uid, saved["next_uid"])


def _clear_chapter(state) -> None:
    state.units = {}
    state.visited, state.opened = set(), set()
    for key in ("convoy", "tt", "escaped", "never_sally", "belong"):
        state.fe10.pop(key, None)
    for slot in range(GLOBAL_FLAG_SLOTS, len(state.flags)):
        state.flags[slot][1] = False


@fe10("UnitsPush_Uninitialize")
def _units_push(vm, a):
    vm.state.fe10["units_push"] = _unit_snapshot(vm.state)
    return 0


@fe10("UnitsPop")
def _units_pop(vm, a):
    saved = vm.state.fe10.pop("units_push", None)
    if saved is not None:
        _restore_units(vm.state, saved)
        vm.state.emit("action", "Units restored (UnitsPop)")
    return 0


@fe10("UnitsInitialize")
def _units_init(vm, a):
    vm.state.units = {}
    return 0


@fe10("AllPush")
def _all_push(vm, a):
    state = vm.state
    saved = {k: copy.deepcopy(getattr(state, k)) for k in ("units", "next_uid", "flags", "visited", "opened", "money")}
    saved["fe10"] = copy.deepcopy({k: v for k, v in state.fe10.items() if k != "all_push"})
    state.fe10["all_push"] = saved
    _clear_chapter(state)
    return 0


@fe10("AllPop")
def _all_pop(vm, a):
    saved = vm.state.fe10.pop("all_push", None)
    if saved is not None:
        for key, value in saved.items():
            setattr(vm.state, key, value)
        vm.state.emit("action", "Chapter state restored (AllPop)")
    return 0


@fe10("_bmsini")
def _bmsini(vm, a):
    state = vm.state
    _clear_chapter(state)
    state.turn, state.money = 1, 1000
    state.set_flag("gf_complete", False)
    state.set_flag("gf_gameover", False)
    return 0


# -- chapter ---------------------------------------------------------------------------------------


@fe10("CompleteSubChapter")
def _complete_sub(vm, a):
    route = int(a[0])
    vm.state.fe10["route"] = route if route in (1, 2, 3) else 0
    vm.state.set_flag("gf_complete", True)
    return 0


@fe10("BMGetValue")
def _bm_get(vm, a):
    return vm.state.fe10.get("bm_values", {}).get(int(a[0]), 0)


@fe10("BMSetValue")
def _bm_set(vm, a):
    value = int(a[1]) & 0xFFFF
    _rec(vm, "bm_values", {})[int(a[0])] = value - 0x10000 if value & 0x8000 else value
    return 0


@fe10("BMSetScore")
def _bm_score(vm, a):
    vm.state.fe10["score"] = int(a[0])
    return 0


@fe10("BMAddForgeLevel")
def _forge_level(vm, a):
    levels = _rec(vm, "forge_exp", {})
    levels[int(a[0])] = min(4950, levels.get(int(a[0]), 0) + 50)
    return 0


@fe10("DDFlagOn")
def _dd_on(vm, a):
    _rec(vm, "library", set()).add(str(a[0]))
    return 0


@fe10("DDFlagOff")
def _dd_off(vm, a):
    _rec(vm, "library", set()).discard(str(a[0]))
    return 0


@fe10("DDFlagCheck")
def _dd_check(vm, a):
    return int(str(a[0]) in vm.state.fe10.get("library", ()))


@fe10("DDExtraFlagAmlitaOn")
def _dd_almedha(vm, a):
    _rec(vm, "library", set()).add(0x7F)
    return 0


@fe10("GetWeather")
def _weather(vm, a):
    return vm.state.fe10.get("weather", 0)


@fe10("SetWeather")
def _set_weather(vm, a):
    vm.state.fe10["weather"] = int(a[0])
    _not_played(vm, f"Weather {a[0]}")
    return 0


# -- convoys and items -----------------------------------------------------------------------------


def _convoy(vm, number=None) -> list:
    convoys = _rec(vm, "convoy", {})
    return convoys.setdefault(int(number) if number is not None else vm.state.fe10.get("army", 1), [])


@fe10("AddToCurrentWarehouseWhatever")
def _to_convoy(vm, a):
    if not isinstance(a[0], str):
        return 0
    item = vm.world.items.get(a[0])
    _convoy(vm).append([a[0], item.uses if item is not None else 1])
    return 1


@fe10("DelItemsFromCurrentWarehouse")
def _del_convoy(vm, a):
    convoy = _convoy(vm)
    kept = [e for e in convoy if e[0] != a[0]]
    found = len(kept) != len(convoy)
    convoy[:] = kept
    return int(found)


@fe10("DelItemsFromForce")
def _del_force(vm, a):
    found = False
    for unit in _force_members(vm, int(a[0])):
        kept = [e for e in unit.items if e[0] != a[1]]
        found |= len(kept) != len(unit.items)
        unit.items = kept
    return int(found)


def _send(vm, unit, slots, convoy: list) -> int:
    sent = 0
    for slot in sorted(slots, reverse=True):
        if 0 <= slot < len(unit.items):
            iid, uses, _drop = unit.items.pop(slot)
            convoy.append([iid, uses])
            sent += 1
    return int(sent > 0)


@fe10("UnitItemSendtoCurrentWarehouse")
def _send_one(vm, a):
    unit = _unit(vm, a[0])
    return _send(vm, unit, [int(a[1])], _convoy(vm)) if unit is not None else 0


@fe10("UnitItemSendtoCurrentWarehouseAll")
def _send_all(vm, a):
    unit = _unit(vm, a[0])
    return _send(vm, unit, range(len(unit.items)), _convoy(vm)) if unit is not None else 0


@fe10("UnitItemSendtoWarehouseAll")
def _send_all_to(vm, a):
    unit = _unit(vm, a[1])
    return _send(vm, unit, range(len(unit.items)), _convoy(vm, a[0])) if unit is not None else 0


@fe10("UnitDelAllItems")
def _del_all(vm, a):
    unit = _unit(vm, a[0])
    if unit is not None:
        unit.items = []
    return 0


@fe10("UnitItemSetEndurance")
def _endurance(vm, a):
    unit = _unit(vm, a[0])
    if unit is not None and 0 <= int(a[1]) < len(unit.items):
        unit.items[int(a[1])][1] = int(a[2])
    return 0


def _item_flag(key: str):
    def handler(vm, a):
        unit = _unit(vm, a[0])
        if unit is None or not 0 <= int(a[1]) < len(unit.items):
            return 0
        _rec(vm, key, set()).add((unit.uid, unit.items[int(a[1])][0]))
        return 1
    return handler


FE10_HANDLERS.update({"UnitItemSetBless": _item_flag("blessed"), "UnitItemSetSealSteal": _item_flag("no_steal")})


@fe10("UnitItemClrAllSubItems")
def _clr_sub(vm, a):
    return 0  # the simulator keeps no "sub item" flag (0x08) to clear


@fe10("UnitItemGetValuation")
def _valuation(vm, a):
    # The game's score is not decoded; the remaining uses stand in for it.
    unit = _unit(vm, a[0])
    if unit is None or not 0 <= int(a[1]) < len(unit.items):
        return 0
    vm.state.emit("warn", "UnitItemGetValuation: the game's item score is not decoded; remaining uses used")
    return unit.items[int(a[1])][1]


@fe10("UnitSetEquip")
def _set_equip(vm, a):
    unit = _unit(vm, a[0])
    slot = int(a[1])
    if unit is not None and 0 < slot < len(unit.items):
        unit.items.insert(0, unit.items.pop(slot))  # the first usable weapon is the equipped one
    return 0


@fe10("UnitGetEquipWepI", "UnitSetWeaponAway")
def _equipped_slot(vm, a):
    from . import combat

    unit = _unit(vm, a[0])
    if unit is None or "SID_ANIMALIZE" in unit.skills:
        return -1
    index, _item = combat.equipped(vm.world, unit)
    return index if index is not None else -1


# -- choices and scripted battles ------------------------------------------------------------------


@fe10("Dialog3ItemsWithSt")
def _choice_with_states(vm, a):
    return _choice(3)(vm, a[:3])


@fe10("NetuzoSet", "NetuzoSetD")
def _netuzo_strike(vm, a):
    _rec(vm, "netuzo", {})[int(a[0])] = list(a[1:])
    _not_played(vm, f"Scripted strike {a[0]}: {list(a[1:])}")
    return 0


@fe10("NetuzoWeapon")
def _netuzo_weapon(vm, a):
    if not isinstance(a[1], str) or vm.world.items.get(a[1]) is None:
        return 0
    _rec(vm, "netuzo_weapon", {})[int(a[0])] = a[1]
    _not_played(vm, f"Scripted battle weapon {a[0]}: {a[1]}")
    return 1


# -- tile effects (ballistae, breakable walls, lava, terrain overrides...) -------------------------


def _tt(vm) -> dict:
    return _rec(vm, "tt", {})


def _set_tt(kind, label: str, value_args: slice = slice(2, None)):
    def handler(vm, a):
        key = (int(a[0]), int(a[1]), kind)
        values = list(a[value_args])
        _tt(vm)[key] = values[0] if len(values) == 1 else values
        _not_played(vm, f"{label} at {key[:2]}: {values}")
        return 1
    return handler


FE10_HANDLERS.update({
    "SetFragile": _set_tt(TT_FRAGILE, "Breakable object"), "SetLava": _set_tt(TT_LAVA, "Lava"),
    "SetBomber": _set_tt(TT_BOMBER, "Bomber tile"), "SetTerrName": _set_tt(TT_TERRAIN_NAME, "Terrain name"),
    "SetTerrData": _set_tt(TT_TERRAIN, "Terrain override"), "SetPit": _set_tt("pit", "Pit"),
    "SetRock": _set_tt("rock", "Rolling rock"), "SetShooter": _set_tt("shooter", "Ballista"),
})


@fe10("AddTT")
def _add_tt(vm, a):
    key = (int(a[0]), int(a[1]), int(a[2]))
    _tt(vm)[key] = list(a[3:])
    _not_played(vm, f"Tile effect {key[2]} at {key[:2]}: {list(a[3:])}")
    return 1


def _build_inst_pos(index: int):
    def handler(vm, a):
        # The map-object list is not modelled: the handler's not-found answer (that argument back).
        vm.state.emit("warn", "BuildInstGetX/Y: map objects are not modelled; the not-found value is used")
        return a[index]
    return handler


FE10_HANDLERS.update({"BuildInstGetX": _build_inst_pos(0), "BuildInstGetY": _build_inst_pos(1)})


@fe10("GetTT")
def _get_tt(vm, a):
    value = vm.state.fe10.get("tt", {}).get((int(a[0]), int(a[1]), int(a[2])), 0)
    return value if isinstance(value, int) else 1


@fe10("ClrTT")
def _clr_tt(vm, a):
    vm.state.fe10.get("tt", {}).pop((int(a[0]), int(a[1]), int(a[2])), None)
    return 0


@fe10("GetTTCount")
def _tt_count(vm, a):
    return sum(1 for key in vm.state.fe10.get("tt", {}) if key[2] == int(a[0]))


@fe10("InitializeTT")
def _init_tt(vm, a):
    vm.state.fe10["tt"] = {}
    return 0


@fe10("GetFragileHP", "GetFragileMaxHP")
def _fragile_hp(vm, a):
    value = vm.state.fe10.get("tt", {}).get((int(a[0]), int(a[1]), TT_FRAGILE), 0)
    return value if isinstance(value, int) else 0

