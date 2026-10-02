"""The native functions event scripts call (``externCall``), as the simulator
models them. Behaviour follows the archive's ``script-functions`` article.

Unit handles are :attr:`SimUnit.uid` (0 = no unit). Forces: 0 player,
1 enemy, 2 allied, 3 other, 5 player reserve (modelled as an off-map player
unit), 6 dead. Calls that only animate, wait, move the camera or play sound
return 0 at once and are logged as ``script`` output; any other name the
simulator doesn't model returns 0 with a warning, as the game does for a
name nobody registered. ``startup.cmb`` helpers are not here: they are
script functions and run as bytecode.
"""

from __future__ import annotations

from . import combat, setup
from .state import ENEMY, PLAYER, MessageShow, SimUnit

HANDLERS: dict = {}

#: Natives that only present something (camera, sound, fades, images, waits...): no effect on play.
PRESENTATION_PREFIXES = (
    "BGM", "Bgm", "SE", "SFX", "ENV", "Cam", "Focus", "InstantFocus", "UnitFocus", "Fade", "Wipe", "Flash", "Rect",
    "Timei", "Tut", "GMap", "EventArrow", "EventCamera", "EventQuake", "CreateEventCamera", "DeleteEventCamera",
    "StartEventCamera", "Effect", "UnitAnim", "UnitRotate", "UnitFade", "UnitWalk", "UnitDispReload", "Wait", "Movie",
    "ChapterMoviePlay", "Disp", "Jyokyo", "Light", "Fog", "Notice", "CreateNotice", "DeleteNotice", "CopyMapCamera",
    "PastMapCamera", "InstantPastMapCamera", "InstantSetMapCamera", "HideMapCursor", "ShowMapCursor", "PreLoad",
    "GameBind", "GameUnbind", "EnableSkip", "DisableSkip", "report", "dump", "ArenaDump", "Ambient", "HidePrim2D",
    "RemoveBackdrop", "BeginMapHoldCursor", "EndMapHoldCursor", "MapUpdate", "RoofOpen", "RoofClose",
    "InstantRoof", "BuildInst", "UnitSetHold", "Sally", "UnitForcedSally", "UnitDontMoveSally", "PadSetMask",
    "PadResetMask", "Config", "TutorialLearn", "TutorialLock", "TutorialUnlock", "TutorialForget", "ArcLoad", "ArcFree",
    "AchieveSet", "UnitSetFixed", "BeginFinale", "EndFinale", "StaffRoll", "WarRecord", "IndividualWarRecord",
    "NetuzoInit", "VisitIn", "intplGetValue", "UnitMoveWait", "FocusWait", "TalkResume", "TTPM", "AddTT",
    "CmSleepScript", "CmWakeupScripts", "UnitClrStatus", "UnitSetStatus", "taikitk", "turntk", "turnatk",
)
#: Presentation calls the game answers with something other than 0.
PRESENTATION_RESULTS = {"_pldone": 1, "isFading": 0, "isFlash": 0, "isWipe": 0, "TalkExist": 0, "ProcExists": 0,
                        "FRAME2MSEC": None, "MSEC2FRAME": None}


def native(*names):
    def register(fn):
        for name in names:
            HANDLERS[name] = fn
        return fn
    return register


def unmodelled(vm, name: str, args: list) -> int:
    shown = f"{name}({', '.join(repr(a) for a in args)})"
    if name in PRESENTATION_RESULTS:
        value = PRESENTATION_RESULTS[name]
        if value is None:  # unit conversions
            value = args[0] * 1000 // 60 if name == "FRAME2MSEC" else args[0] * 60 // 1000
        return value
    if name.startswith(PRESENTATION_PREFIXES):
        vm.state.emit("script", shown)
        return 0
    vm.state.emit("warn", f"Not simulated: {shown} -> 0")
    return 0


def _unit(vm, handle):
    unit = vm.state.units.get(handle) if isinstance(handle, int) else None
    return unit


def _name(vm, unit: SimUnit) -> str:
    return vm.world.name(unit.pid)


# -- flags ------------------------------------------------------------------------------------------


@native("regist")
def _regist(vm, a):
    return vm.state.register_flag(str(a[0]), from_top=True)


@native("global")
def _global(vm, a):
    slot = vm.state.register_flag(str(a[0]), from_top=False)
    if slot >= 0:
        vm.state.flags[slot][1] = False
    return slot


@native("set")
def _set(vm, a):
    if vm.state.set_flag(str(a[0]), True):
        vm.state.emit("script", f"flag {a[0]} set")
    return 0


@native("clr")
def _clr(vm, a):
    vm.state.set_flag(str(a[0]), False)
    return 0


@native("get")
def _get(vm, a):
    return int(vm.state.get_flag(str(a[0])))


# -- chapter state ----------------------------------------------------------------------------------

_RANKS = {"n": 0, "h": 1, "m": 2, "e": 3}


@native("GetRank")
def _rank(vm, a):
    return _RANKS.get(vm.world.difficulty, 0)


@native("Normal")
def _normal(vm, a):
    return int(_rank(vm, a) in (0, 3))


@native("Hard")
def _hard(vm, a):
    return int(_rank(vm, a) == 1)


@native("Maniac")
def _maniac(vm, a):
    return int(_rank(vm, a) == 2)


@native("Easy", "NormalOnly", "GCST", "IsE3Version", "GetTutorial", "SysGetRound", "GetLanguage", "Check",
        "CmLoadScript", "CmFreeScript", "MCResult", "GetBattleType", "BMGetChapter")
def _zero(vm, a):
    return 0


@native("BMGetTurn")
def _turn(vm, a):
    return vm.state.turn


@native("BMSetTurn")
def _set_turn(vm, a):
    vm.state.turn = int(a[0])
    return 0


@native("BMGetPhase")
def _phase(vm, a):
    return vm.state.phase


@native("BMSetPhase")
def _set_phase(vm, a):
    vm.state.phase = int(a[0])
    return 0


@native("BMGetMoney")
def _money(vm, a):
    return vm.state.money


@native("BMSetMoney")
def _set_money(vm, a):
    vm.state.money = int(a[0])
    return 0


@native("MindGetMoney")
def _gain_money(vm, a):
    vm.state.money += int(a[0])
    vm.state.emit("action", f"Got {a[0]} gold")
    return 0


@native("GetRnd")
def _rnd(vm, a):
    bound = int(a[0])
    return vm.state.rng._next() % bound if bound > 0 else 0


@native("Complete18")
def _complete18(vm, a):
    vm.state.set_flag("gf_complete", True)
    return 0


# -- event context ----------------------------------------------------------------------------------


@native("MindGetMe")
def _me(vm, a):
    return vm.ctx.get("me", 0)


@native("MindGetTarget")
def _target(vm, a):
    return vm.ctx.get("target", 0)


@native("MindGetMind")
def _mind(vm, a):
    return vm.ctx.get("action", 0)


@native("EventGetX")
def _event_x(vm, a):
    return vm.ctx.get("x", 0)


@native("EventGetY")
def _event_y(vm, a):
    return vm.ctx.get("y", 0)


# -- units ------------------------------------------------------------------------------------------


@native("UnitGetByPID")
def _by_pid(vm, a):
    unit = vm.state.unit_by_pid(a[0])
    return unit.uid if unit is not None else 0


@native("UnitGetByPos", "MapGetUnit")
def _by_pos(vm, a):
    unit = vm.state.unit_at(int(a[0]), int(a[1]))
    return unit.uid if unit is not None else 0


def _force_members(vm, force: int) -> list:
    units = sorted(vm.state.units.values(), key=lambda u: u.uid)
    if force == 5:
        return [u for u in units if u.faction == PLAYER and u.hidden and not u.dead]
    if force == 6:
        return [u for u in units if u.dead]
    return [u for u in units if u.faction == force and u.on_map]


@native("ForceGetFirst")
def _force_first(vm, a):
    members = _force_members(vm, int(a[0]))
    return members[0].uid if members else 0


@native("ForceGetCount")
def _force_count(vm, a):
    return len(_force_members(vm, int(a[0])))


def _force_of(unit: SimUnit) -> int:
    if unit.dead:
        return 6
    if unit.hidden and unit.faction == PLAYER:
        return 5
    return unit.faction


@native("UnitGetNext")
def _next(vm, a):
    unit = _unit(vm, a[0])
    if unit is None:
        return 0
    members = _force_members(vm, _force_of(unit))
    ids = [u.uid for u in members]
    if unit.uid not in ids:
        return 0
    i = ids.index(unit.uid)
    return ids[i + 1] if i + 1 < len(ids) else 0


@native("UnitGetForce")
def _get_force(vm, a):
    unit = _unit(vm, a[0])
    return _force_of(unit) if unit is not None else 0


_UNIT_FIELDS = {5: "force", 6: "level", 7: "exp", 9: "x", 10: "y", 12: "maxhp", 13: "hp", 21: "build", 22: "move"}


@native("UnitGet")
def _unit_get(vm, a):
    unit = _unit(vm, a[0])
    field = int(a[1])
    if unit is None:
        return 0
    if field == 1:
        return _next(vm, [unit.uid])
    if field == 5:
        return _force_of(unit)
    if field in (6, 7, 9, 10, 21, 22):
        return getattr(unit, _UNIT_FIELDS[field])
    if field == 12:
        return unit.stats[0]
    if field == 13:
        return unit.hp
    if 14 <= field <= 20:
        return unit.stats[field - 13]
    if field == 23:
        t = vm.world.terrain_at(unit.x, unit.y)
        return t.avoid if t is not None else 0
    return 0


@native("UnitSet")
def _unit_set(vm, a):
    unit = _unit(vm, a[0])
    field, value = int(a[1]), int(a[2])
    if unit is None or field == 0:
        return 0
    if field == 6:
        unit.level = value
    elif field == 7:
        unit.exp = value
    elif field == 13:
        unit.hp = max(0, min(value, unit.stats[0]))
    return value


@native("UnitGetHP")
def _hp(vm, a):
    unit = _unit(vm, a[0])
    return unit.hp if unit is not None else 0


@native("UnitGetMaxHP")
def _max_hp(vm, a):
    unit = _unit(vm, a[0])
    return unit.stats[0] if unit is not None else 0


@native("UnitSetHP")
def _set_hp(vm, a):
    unit = _unit(vm, a[0])
    if unit is not None:
        unit.hp = max(0, min(int(a[1]), unit.stats[0]))
    return 0


@native("UnitSetEXP")
def _set_exp(vm, a):
    unit = _unit(vm, a[0])
    if unit is not None:
        unit.exp = int(a[1])
    return 0


@native("UnitGetX")
def _x(vm, a):
    unit = _unit(vm, a[0])
    return unit.x if unit is not None else 0


@native("UnitGetY")
def _y(vm, a):
    unit = _unit(vm, a[0])
    return unit.y if unit is not None else 0


@native("UnitGetStatus")
def _status(vm, a):
    unit = _unit(vm, a[0])
    if unit is None:
        return 0
    bits = 0x1 if unit.done else 0
    if unit.dead:
        bits |= 0x8 | 0x8000
    if unit.hidden and not unit.dead and unit.faction == PLAYER:
        bits |= 0x10
    if unit.boss:
        bits |= 0x100
    return bits


@native("UnitQueryPID")
def _query_pid(vm, a):
    unit = _unit(vm, a[0])
    return int(unit is not None and unit.pid == a[1])


@native("UnitQueryJID")
def _query_jid(vm, a):
    unit = _unit(vm, a[0])
    return int(unit is not None and unit.jid == a[1])


@native("PIDisAlive")
def _alive(vm, a):
    unit = vm.state.unit_by_pid(a[0])
    return int(unit is not None and not unit.dead)


@native("UnitGetRace")
def _race(vm, a):
    unit = _unit(vm, a[0])
    laguz = unit is not None and bool(set(unit.categories) & {"beast", "bird", "dragon", "alize"})
    return 1 if laguz else 0


def _place(vm, unit: SimUnit, x: int, y: int, how: str) -> None:
    unit.hidden = True
    unit.x, unit.y = setup.nearest_free(vm.world, vm.state, (int(x), int(y)), unit)
    unit.hidden = False
    vm.state.emit("action", f"{_name(vm, unit)} {how} {unit.tile}", uid=unit.uid)


@native("UnitSetPos")
def _set_pos(vm, a):
    unit = _unit(vm, a[0])
    if unit is None:
        return 0
    _place(vm, unit, a[1], a[2], "placed at")
    return 1


@native("UnitMovePos")
def _move_pos(vm, a):
    unit = _unit(vm, a[0])
    if unit is None:
        return 0
    _place(vm, unit, a[1], a[2], "walks to")
    return 1


@native("UnitTransferToForce")
def _transfer(vm, a):
    unit = _unit(vm, a[0])
    if unit is None:
        return 0
    force = int(a[1])
    if force in (0, 1, 2, 3):
        unit.faction = force
        unit.hidden = False
    elif force == 5:
        unit.faction, unit.hidden = PLAYER, True
    elif force == 6:
        unit.dead = True
    if force != ENEMY:
        for item in unit.items:
            item[2] = False
    vm.state.emit("action", f"{_name(vm, unit)} joins force {force}", uid=unit.uid)
    return 1


@native("UnitEscape")
def _escape(vm, a):
    unit = _unit(vm, a[0])
    if unit is None:
        return 0
    unit.hidden = True
    if unit.faction != PLAYER:
        unit.dead = True
    vm.state.emit("action", f"{_name(vm, unit)} leaves the map", uid=unit.uid)
    return 1


@native("AllUnitEscape")
def _all_escape(vm, a):
    for unit in vm.state.living():
        if unit.faction in (0, 1, 2, 3):
            _escape(vm, [unit.uid, 0])
    return 0


@native("UnitDead")
def _dead(vm, a):
    unit = _unit(vm, a[0])
    if unit is not None:
        unit.dead, unit.hp = True, 0
        vm.state.emit("death", f"{_name(vm, unit)} is removed (UnitDead)", uid=unit.uid)
    return 0


@native("UnitWarpOut")
def _warp_out(vm, a):
    unit = _unit(vm, a[0])
    if unit is not None:
        unit.hidden = True
    return 0


@native("UnitClassChange")
def _class_change(vm, a):
    unit = _unit(vm, a[0])
    cls = vm.world.classes.get(unit.jid) if unit is not None else None
    if cls is None or not cls.promotes_to:
        return 0
    new = vm.world.classes.get(cls.promotes_to)
    if new is None:
        return 0
    for i in range(8):
        gain = max(0, new.base_stats[i] - cls.base_stats[i])
        unit.stats[i] += gain
        if i == 0:
            unit.hp += gain
    unit.jid, unit.move, unit.movement_type = new.jid, new.movement, new.movement_type
    unit.categories = [c for c in new.categories if c]
    vm.state.emit("action", f"{_name(vm, unit)} promotes to {new.jid}", uid=unit.uid)
    return 0


@native("UnitTackle")
def _tackle(vm, a):
    from .actions import shove_destination

    unit, target = _unit(vm, a[0]), _unit(vm, a[1])
    if unit is None or target is None:
        return 0
    for _ in range(max(1, int(a[2]))):
        to = shove_destination(vm.world, vm.state, unit.tile, target)
        if to is None:
            break
        target.x, target.y = to
    return 0


# -- inventory, skills, AI --------------------------------------------------------------------------


@native("UnitAddItem", "_gi")
def _add_item(vm, a):
    unit = _unit(vm, a[0])
    if unit is None:
        return 0
    if len(unit.items) < 8 and isinstance(a[1], str):
        item = vm.world.items.get(a[1])
        unit.items.append([a[1], item.uses if item is not None else 1, False])
        vm.state.emit("action", f"{_name(vm, unit)} gets {vm.world.item_name(a[1])}", uid=unit.uid)
    return 1


@native("UnitDelItem")
def _del_item(vm, a):
    unit = _unit(vm, a[0])
    if unit is not None and 0 <= int(a[1]) < len(unit.items):
        del unit.items[int(a[1])]
    return 0


@native("UnitReplaceItem")
def _replace_item(vm, a):
    unit = _unit(vm, a[0])
    if unit is not None and 0 <= int(a[1]) < len(unit.items) and isinstance(a[2], str):
        item = vm.world.items.get(a[2])
        unit.items[int(a[1])] = [a[2], item.uses if item is not None else 1, False]
    return 0


@native("UnitSearchItem")
def _search_item(vm, a):
    unit = _unit(vm, a[0])
    if unit is None:
        return -1
    return next((i for i, it in enumerate(unit.items) if it[0] == a[1]), -1)


@native("UnitGetItemCount")
def _item_count(vm, a):
    unit = _unit(vm, a[0])
    return len(unit.items) if unit is not None else 0


@native("UnitGetWeaponCount")
def _weapon_count(vm, a):
    unit = _unit(vm, a[0])
    return len(combat.weapon_items(vm.world, unit)) if unit is not None else 0


@native("UnitItemSetDrop")
def _set_drop(vm, a):
    unit = _unit(vm, a[0])
    if unit is not None and 0 <= int(a[1]) < len(unit.items):
        unit.items[int(a[1])][2] = True
    return 0


@native("UnitAddSkill")
def _add_skill(vm, a):
    unit = _unit(vm, a[0])
    if unit is not None and isinstance(a[1], str) and a[1] not in unit.skills:
        unit.skills.append(a[1])
    return 0


@native("UnitClrSkill")
def _clr_skill(vm, a):
    unit = _unit(vm, a[0])
    if unit is not None and a[1] in unit.skills:
        unit.skills.remove(a[1])
    return 0


@native("UnitTstSkill")
def _tst_skill(vm, a):
    unit = _unit(vm, a[0])
    return int(unit is not None and a[1] in unit.skills)


def _set_ai(field):
    def handler(vm, a):
        unit = _unit(vm, a[0])
        if unit is not None:
            setattr(unit, field, a[1])
            if field == "seq_attack":
                unit.ai_pc[0] = 0
            elif field == "seq_move":
                unit.ai_pc[1] = 0
            vm.state.emit("script", f"{_name(vm, unit)}: {field} = {a[1]}")
        return 0
    return handler


HANDLERS["UnitSetCpAttackSeq"] = _set_ai("seq_attack")
HANDLERS["UnitSetCpMoveSeq"] = _set_ai("seq_move")
HANDLERS["UnitSetCpHealSeq"] = _set_ai("seq_heal")
HANDLERS["UnitSetCpMTypeID"] = _set_ai("mtype")


# -- deployment -------------------------------------------------------------------------------------


def _dispos(animate=True, exact=False, rank=False, existing_only=False):
    def handler(vm, a):
        group = str(a[0])
        if rank:
            group += "_" + {"n": "n", "h": "h"}.get(vm.world.difficulty, "m")
        if existing_only:
            section = vm.world.groups.get(group)
            if section is None:
                return 0
            for record in section.units:
                unit = vm.state.unit_by_pid(record[setup.F["pid"]])
                if unit is not None:
                    _place(vm, unit, record[setup.F["pos2_x"]], record[setup.F["pos2_y"]], "moves to")
            return 1
        setup.deploy(vm.world, vm.state, group, animate=animate, exact=exact)
        return 1
    return handler


HANDLERS.update({
    "Dispos": _dispos(), "DisposAsynchronous": _dispos(), "DisposWarp": _dispos(), "DisposFirst": _dispos(exact=True),
    "InstantDispos": _dispos(animate=False), "InstantDisposFirst": _dispos(animate=False, exact=True),
    "InstantDisposRank": _dispos(animate=False, rank=True), "DisposContinue": _dispos(existing_only=True),
    "InstantDisposContinue": _dispos(existing_only=True), "DisposAuxiliary": _dispos(),
})


@native("Join")
def _join(vm, a):
    setup.deploy(vm.world, vm.state, str(a[0]), force=PLAYER, hidden=True)
    return 1


@native("SallySetByGroup", "SallyAddByGroup")
def _sally(vm, a):
    """The preparations' deployment tiles: the simulator deploys the group's player units there."""
    vm.state.emit("script", f"Preparations: deployment tiles from {a[0]}")
    section = vm.world.groups.get(str(a[0]))
    if section is not None and any(int(u[setup.F["faction"]] or 0) == PLAYER for u in section.units):
        setup.deploy(vm.world, vm.state, str(a[0]), animate=False)
    return 0


# -- checks -----------------------------------------------------------------------------------------


@native("EnemyDeadCheck")
def _enemy_dead(vm, a):
    return int(not vm.state.living(ENEMY))


@native("PlayerDeadCheck")
def _player_dead(vm, a):
    return int(not any(u.dead for u in vm.state.units.values()))


@native("GetDiedPlayerCount")
def _died_players(vm, a):
    return sum(1 for u in vm.state.units.values() if u.dead and u.faction == PLAYER)


@native("EnemyUnitCheckByPID")
def _enemy_pid(vm, a):
    return sum(1 for u in vm.state.living(ENEMY) if u.pid == a[0])


@native("EnemyMonkCheck")
def _enemy_monks(vm, a):
    return sum(1 for u in vm.state.living(ENEMY) if u.jid in ("JID_PRIEST", "JID_BISHOP", "JID_BISHOP_F"))


@native("EnemyTigerCheck")
def _enemy_tigers(vm, a):
    return sum(1 for u in vm.state.living(ENEMY) if u.jid == "JID_TIGER")


@native("PlayerEscapeCheck", "PlayerEscapeCount", "ShooterBulletCheck", "EnemySelfDefenceCheck")
def _no_count(vm, a):
    return 0


@native("CheckAttackable")
def _attackable(vm, a):
    from . import movement

    unit = _unit(vm, a[0])
    if unit is None:
        return 0
    ranges = combat.attack_ranges(vm.world, unit)
    threat = movement.threat_tiles(vm.world, vm.state, unit, ranges) if ranges else set()
    return int(any(u.tile in threat for u in vm.state.living() if u.faction != unit.faction and
                   (u.faction == ENEMY or unit.faction == ENEMY)))


# -- map --------------------------------------------------------------------------------------------


def _open(kind):
    def handler(vm, a):
        tile = (int(a[0]), int(a[1]))
        vm.state.opened.add(tile)
        vm.state.emit("action", f"{kind} at {tile}")
        return 1
    return handler


HANDLERS.update({"DoorOpen": _open("Door opened"), "InstantDoorOpen": _open("Door opened"),
                 "TBoxOpen": _open("Chest opened")})


@native("DoorClose", "InstantDoorClose")
def _door_close(vm, a):
    vm.state.opened.discard((int(a[0]), int(a[1])))
    return 1


@native("VisitOut")
def _visit_out(vm, a):
    vm.state.visited.add((int(a[1]), int(a[2])))
    return 1


@native("BuildDestruction")
def _destroy(vm, a):
    tile = (int(a[0]), int(a[1]))
    vm.state.visited.add(tile)
    vm.state.emit("action", f"Village at {tile} destroyed")
    return 1


@native("MapGetTerrain")
def _terrain(vm, a):
    t = vm.world.terrain_at(int(a[0]), int(a[1]))
    return t.index if t is not None else 0


@native("UnitGetMoveCost")
def _move_cost(vm, a):
    unit = _unit(vm, a[0])
    index = int(a[1])
    if unit is None or not 0 <= index < len(vm.world.terrain_types):
        return 0
    costs = vm.world.terrain_types[index].move_costs
    return costs[unit.movement_type] if 0 <= unit.movement_type < len(costs) else 0


# -- conversations ----------------------------------------------------------------------------------


@native("TalkEvent", "TalkEventDirect", "Dialog", "DialogDirect", "DialogTutorial", "td", "_tt")
def _talk(vm, a):
    msg_id = str(a[0])
    vm.insert(MessageShow(msg_id, vm.world.messages.get(msg_id, "")))
    if msg_id not in vm.world.messages:
        vm.state.emit("warn", f"Message {msg_id} not found")
    return 1


def _choice(count):
    def handler(vm, a):
        for msg_id in a[:count]:
            vm.insert(MessageShow(str(msg_id), vm.world.messages.get(str(msg_id), "")))
        vm.state.dialog_result = 0
        vm.state.emit("script", f"Choice dialog: the simulator picks the first entry ({a[0]})")
        return 1
    return handler


HANDLERS.update({"Dialog2Items": _choice(2), "Dialog3Items": _choice(3), "Dialog4Items": _choice(4)})


@native("DialogResult", "DialogGetRes")
def _dialog_result(vm, a):
    return vm.state.dialog_result


@native("DefaultDieTalk", "DefaultEscapeTalk")
def _default_talk(vm, a):
    return 0


# -- scripted battle --------------------------------------------------------------------------------


@native("NetuzoBattle")
def _netuzo(vm, a):
    from . import movement
    from .actions import Combat

    attacker, defender = _unit(vm, a[0]), _unit(vm, a[1])
    if attacker is None or defender is None:
        return 0
    d = movement.distance(attacker.tile, defender.tile)
    index, _item = combat.equipped(vm.world, attacker, d)
    if index is None:
        index, _item = combat.equipped(vm.world, attacker)
    if index is None:
        return 0
    vm.insert(Combat(attacker.uid, defender.uid, index, max(1, d)))
    return 1
