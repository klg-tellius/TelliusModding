"""The AI's decisions other than weapon attacks and moves: the heal step,
staves, steal, item use and skills, as ``main.dol`` makes them
(``research/CP_DATA_NOTES.md`` section 3.4).

Shared rules:

- **Targets.** An entry's ``targets``/``exclude`` give a predicate
  (``check_faction_mismatch``: hostile; ``cp_target_in_pid_list``;
  ``cp_target_hostile_not_in_pid_list``). Healing staves, Restore, Ward and
  Warp take the units the predicate *rejects* (the unit's own side by
  default); Silence, Sleep, Berserk and Steal take the units it accepts.
- **Scan order.** Units are looked at row by row (y, then x) in the box of
  Mov + the staff's range around the unit; a later unit replaces the best on
  a tie (``<=``), so the last one in scan order wins.
- **Tile score** (``ai_score_terrain_defense_for_tile`` +
  ``ai_score_tile_faction_proximity`` - threat >> 4): (avoid + defence +
  resistance + heal %) / 2 of the tile's terrain (the flier columns for
  fliers), plus the 0x80272E98 weights of the tiles around it (+ for a unit
  not hostile to this one, the unit itself included, - for a hostile one),
  minus the tile's ``ai_threat_map`` value >> 4. The best wins, the first in
  scan order on a tie. Adjacent staves look at the 4 tiles next to the
  target (right, left, down, up); ranged staves at every tile in range.
- **Needs healing** (unit ``+0x254`` bit 0, ``check_unit_hp_below_retreat_threshold``):
  set when HP% = (int)(100 x HP / max HP) falls under the heal record's
  ``retreat_below``, cleared when it reaches ``resume_at``. It is refreshed
  for every unit when a phase starts (``FUN_80100b08`` ->
  ``analyze_unit_equipment_and_set_status_flags``), for the two units of an
  action after it, and by the heal step. Healing staves only target units
  that carry it.
"""

from __future__ import annotations

from typing import Optional

from ..formats import cp_data, fe8data
from . import combat, movement
from .state import GameState, SimUnit, hostile
from .world import World

#: Use category 0x81 (``derive_item_use_category_from_iid``): healing staves and items.
HEALING = frozenset({"IID_LIVE", "IID_RELIVE", "IID_RECOVER", "IID_REBLOW", "IID_RESERVE", "IID_VULNERARY",
                     "IID_ELIXIR"})
#: ``ai_staff_routine_table`` (0x8028F5F8). Torch, Hammerne and Unlock have routines that return 0.
STAFF_ROUTINES = {"IID_LIVE": "heal_adjacent", "IID_RELIVE": "heal_adjacent", "IID_RECOVER": "heal_adjacent",
                  "IID_REBLOW": "heal_ranged", "IID_RESERVE": "fortify", "IID_REST": "restore",
                  "IID_SILENCE": "silence", "IID_SLEEP": "sleep", "IID_BERSERK": "sleep", "IID_WARP": "warp",
                  "IID_RESCUE": "heal_ranged", "IID_MSHIELD": "ward"}
STATUS_STAVES = {"IID_SILENCE": "silence", "IID_SLEEP": "sleep", "IID_BERSERK": "berserk"}
#: 0x80273B78: the tiles next to a target, in the order the adjacent routines try them.
ADJACENT = ((1, 0), (-1, 0), (0, 1), (0, -1))
#: The order ``dispatch_adjacent_with_vtable_offset_8`` visits a tile's neighbours (link bits 8, 2, 4, 1).
LINK_ORDER = ((0, -1), (1, 0), (0, 1), (-1, 0))
#: 0x802732A0: the tiles ``count_adjacent_matching_units`` counts (the diamond of radius 3, centre excluded).
COUNT_TABLE = tuple((dx, dy) for dy in range(-3, 4) for dx in range(-3, 4) if 0 < abs(dx) + abs(dy) <= 3)
#: Heal amounts the heal-item choice compares (``check_use_healing_item_action*``): others count 0.
ITEM_HEAL = {"IID_VULNERARY": 10}
EQUIPMENT_SLOTS = ITEM_SLOTS = 4
#: Phases a status staff's effect lasts: not traced in this game (the status nibbles at unit +0x1A4 count
#: down somewhere not decoded), the series' usual value.
STATUS_TURNS = 5
NO_SCORE = -(1 << 31)


# -- small rules ------------------------------------------------------------------------------------


def max_range(unit: SimUnit, item) -> int:
    """``resolve_stat_or_default_from_magic``: the item's max range, or for 255 Mag / 2 clamped to 5..15."""
    if item.max_range == 255:
        return min(15, max(5, unit.stats[2] // 2))
    return item.max_range


def heal_percent(unit: SimUnit) -> int:
    return int(100.0 * unit.hp / max(1, unit.stats[0]))


def effective_level(unit: SimUnit) -> int:
    """``get_effective_level_for_base_exp``: the level, +20 for a promoted unit."""
    return unit.level + (20 if "SID_HIGHER" in unit.skills else 0)


def magic_hit(caster: SimUnit, target: SimUnit, distance: Optional[int] = None) -> int:
    """``compute_magic_attack_score``: (Mag - Res) x 5 + Skl + 30 - 2 x distance, clamped to 0..100. The AI
    measures the distance from where the caster stands before moving."""
    d = movement.distance(caster.tile, target.tile) if distance is None else distance
    return max(0, min(100, (caster.stats[2] - target.stats[7]) * 5 + caster.stats[3] + 30 - 2 * d))


def is_equipment(item) -> bool:
    return item is not None and item.weapon_type not in (None, "item", "acc")


def equipment(world: World, unit: SimUnit) -> list:
    """The first four weapons and staves (inventory slots 0-3): [(index, ItemEntry)]."""
    out = [(i, world.items[e[0]]) for i, e in enumerate(unit.items) if is_equipment(world.items.get(e[0]))]
    return out[:EQUIPMENT_SLOTS]


def carried_items(world: World, unit: SimUnit) -> list:
    """The first four other items (slots 4-7): [(index, ItemEntry)]."""
    out = [(i, world.items[e[0]]) for i, e in enumerate(unit.items)
           if e[0] in world.items and not is_equipment(world.items[e[0]])]
    return out[:ITEM_SLOTS]


def rank_exp(item) -> int:
    """+0x16: the minimum weapon EXP of the item's rank, how the staff choice ranks staves."""
    return dict(fe8data.ITEM_RANKS).get(item.rank or "", 0)


def holds_healing_staff(world: World, unit: SimUnit) -> bool:
    """``analyze_unit_equipment_and_set_status_flags`` +0x254 bit 2: a usable staff of category 0x81."""
    return any(item.iid in HEALING for _i, item in combat.staff_items(world, unit))


def heal_record(world: World, unit: SimUnit) -> Optional[cp_data.HealRecord]:
    doc = world.cp
    if doc is None:
        return None
    name = unit.seq_heal
    if isinstance(name, int):
        names = cp_data.heal_records(doc)
        name = names[name] if 0 <= name < len(names) else None
    section = doc.section(name) if isinstance(name, str) and name else None
    if section is None or not cp_data.is_heal_section(section):
        return None
    return cp_data.read_heal(section)


def update_needs_heal(world: World, unit: SimUnit) -> bool:
    """``check_unit_hp_below_retreat_threshold``: refresh the flag; True while it is set."""
    record = heal_record(world, unit)
    if record is None:
        return False
    percent = heal_percent(unit)
    if not unit.needs_heal:
        if percent < record.retreat_below:
            unit.needs_heal = True
    elif percent >= record.resume_at:
        unit.needs_heal = False
    return unit.needs_heal


def refresh_needs_heal(world: World, state: GameState, units=None) -> None:
    for unit in (units if units is not None else state.living()):
        if unit is not None and unit.on_map:
            update_needs_heal(world, unit)


def standable(world: World, state: GameState, tile: tuple) -> bool:
    """Not an object tile (terrain byte 7), and in an ally phase not an objective-like terrain
    (``check_terrain_type_during_enemy_phase``: types 38, 39, 40, 42)."""
    from .ai_vm import ALLY_PHASE_SKIPPED_TERRAIN

    t = world.terrain_at(*tile)
    if t is None:
        return True
    if getattr(t, "flag7", 0):
        return False
    return not (state.phase == 2 and t.index in ALLY_PHASE_SKIPPED_TERRAIN)


def can_carry(world: World, unit: SimUnit, item) -> bool:
    """``can_actor_carry_item``: weight under the unit's Str, and a free slot of the item's kind."""
    if item.weight >= unit.stats[1]:
        return False
    if is_equipment(item):
        return len(equipment(world, unit)) < EQUIPMENT_SLOTS
    return len(carried_items(world, unit)) < ITEM_SLOTS


def might_threat_map(world: World, state: GameState, faction: int) -> dict:
    """``build_ai_weapon_threat_map`` (the per-phase map, read by the Warp routine): on every tile a unit
    hostile to ``faction`` could strike with its best close or ranged weapon, weapon might + Str (Mag for
    magic), the larger of its two weapons; summed over the units, capped at 255."""
    from .ai_vm import THREAT_CAP, threat_weapons

    occupied = {u.tile for u in state.units.values() if u.on_map}
    total: dict = {}
    for other in state.living():
        if not hostile(faction, other.faction):
            continue
        best: dict = {}
        stands = None
        for _i, item in threat_weapons(world, other):
            power = item.might + (other.stats[2] if item.weapon_type in combat.MAGIC_TYPES else other.stats[1])
            value = min(THREAT_CAP, power)
            if value <= 0:
                continue
            if stands is None:
                stands = [t for t in movement.destinations(world, state, other)
                          if t not in occupied or t == other.tile]
            low, high = combat.item_range(other, item)
            for stand in stands:
                for tile in movement.tiles_in_range(world, stand, low, high):
                    if best.get(tile, 0) < value:
                        best[tile] = value
        for tile, value in best.items():
            total[tile] = min(THREAT_CAP, total.get(tile, 0) + value)
    return total


# -- the routines, as methods of the AI step --------------------------------------------------------


class ActionRoutines:
    """Mixed into :class:`ai_vm.AiStep` (``self.world``, ``self.state``, ``self.unit``, ``self.turn``)."""

    # -- shared pieces ---------------------------------------------------------------------------
    def _predicate(self, table=None, exclude: bool = False):
        from .ai_vm import pid_table

        unit = self.unit
        pids = pid_table(self.world, table)
        if pids is None:
            return lambda u: hostile(unit.faction, u.faction)
        if exclude:
            return lambda u: hostile(unit.faction, u.faction) and u.pid not in pids
        return lambda u: u.pid in pids

    def _reach(self, in_place: bool = False) -> dict:
        from .ai_vm import _hold

        if in_place or _hold(self.unit):
            return {self.unit.tile: (0, None)}
        return movement.destinations(self.world, self.state, self.unit)

    def _threat(self) -> dict:
        cache = getattr(self, "_threat_cache", None)
        if cache is None:
            from .ai_vm import enemy_threat_map

            cache = self._threat_cache = enemy_threat_map(self.world, self.state, self.unit)
        return cache

    def _free(self, tile) -> bool:
        other = self.state.unit_at(*tile)
        return other is None or other.uid == self.unit.uid

    def tile_score(self, tile: tuple) -> int:
        from .ai_vm import NEAR_TABLE

        world, unit = self.world, self.unit
        t = world.terrain_at(*tile)
        terrain = 0
        if t is not None:
            three = t.alt_bonus if "fly" in unit.categories else (t.avoid, t.defense, t.resistance)
            terrain = (sum(three) + t.heal) >> 1
        near = 0
        for dx, dy, weight in NEAR_TABLE:
            n = (tile[0] + dx, tile[1] + dy)
            if not world.inside(*n):
                continue
            other = self.state.unit_at(*n)
            if other is not None:
                near += -weight if hostile(unit.faction, other.faction) else weight
        return terrain + near - ((self._threat().get(tile, 0) >> 4) & 0xFFF)

    def _adjacent_stand(self, target_tile: tuple, reach: dict) -> Optional[tuple]:
        """The best of the 4 tiles next to ``target_tile`` the unit can stop on (``score_tile_for_ai_target``)."""
        best, best_score = None, NO_SCORE
        for dx, dy in ADJACENT:
            tile = (target_tile[0] + dx, target_tile[1] + dy)
            if tile not in reach or getattr(self.world.terrain_at(*tile), "flag7", 0) or not self._free(tile):
                continue
            score = self.tile_score(tile)
            if score > best_score:
                best, best_score = tile, score
        return best

    def _ranged_stand(self, target_tile: tuple, low: int, high: int, reach: dict) -> Optional[tuple]:
        """The best tile in ``low..high`` of ``target_tile`` the unit can stop on, rows then columns."""
        best, best_score = None, NO_SCORE
        for tile in sorted(reach, key=lambda t: (t[1], t[0])):
            if not low <= movement.distance(tile, target_tile) <= high:
                continue
            if not standable(self.world, self.state, tile) or not self._free(tile):
                continue
            score = self.tile_score(tile)
            if score > best_score:
                best, best_score = tile, score
        return best

    def _box(self, radius: int) -> list:
        """The other units on the map within ``radius`` (both axes) of the unit, rows then columns."""
        x, y = self.unit.tile
        out = [u for u in self.state.living() if u.uid != self.unit.uid
               and abs(u.x - x) <= radius and abs(u.y - y) <= radius]
        return sorted(out, key=lambda u: (u.y, u.x))

    # -- staves ----------------------------------------------------------------------------------
    def try_use_staff(self, pred, in_place: bool) -> Optional[dict]:
        """``ai_try_use_staff``: each usable staff in slots 0-3 runs its routine; a healing staff (category
        0x81) is tried when its rank is at least the last healing staff that found a target, another staff
        only while no healing staff found one and at least the last one's rank. The last success wins."""
        world, unit = self.world, self.unit
        if unit.status == "silence":
            return None
        usable = {i for i, _item in combat.staff_items(world, unit)}
        chosen, heal_found, heal_rank, other_rank = None, False, 0, 0
        notes = []
        for index, item in equipment(world, unit):
            heal = item.iid in HEALING
            rank = rank_exp(item)
            if heal and rank < heal_rank:
                continue
            if not heal and (heal_found or rank < other_rank):
                continue
            routine = STAFF_ROUTINES.get(item.iid)
            if index not in usable or routine is None:
                continue
            cand = getattr(self, f"_staff_{routine}")(index, item, pred, self._reach(in_place))
            notes.append(f"{world.item_name(item.iid)}: {cand['text'] if cand else 'no target'}")
            if cand is None:
                continue
            chosen = cand
            if heal:
                heal_rank, heal_found = rank, True
            else:
                other_rank = rank
        if chosen is not None:
            chosen["notes"] = notes
        self._staff_notes = notes
        return chosen

    def _candidate(self, index, item, target, dest, text, **extra) -> dict:
        name = self.world.item_name(item.iid)
        return {"action": "staff", "dest": dest, "target": target.uid if target is not None else None,
                "item": index, "text": f"{name} {text} from {dest}", **extra}

    def _staff_heal_adjacent(self, index, item, pred, reach):
        """Live, Mend, Recover: the unit of its side next to a tile it can reach with the lowest HP%."""
        best, best_ratio = None, 100
        for u in self._box(self.unit.move + max_range(self.unit, item)):
            if pred(u) or not u.needs_heal:
                continue
            ratio = heal_percent(u)
            if ratio <= best_ratio:
                stand = self._adjacent_stand(u.tile, reach)
                if stand is not None:
                    best, best_ratio = (u, stand), ratio
        if best is None:
            return None
        u, stand = best
        return self._candidate(index, item, u, stand, f"on {self.world.name(u.pid)} (HP {best_ratio}%)")

    def _staff_heal_ranged(self, index, item, pred, reach):
        """Physic, Rescue: the same, from any tile in the staff's range."""
        low, high = max(1, item.min_range), max_range(self.unit, item)
        best, best_ratio = None, 100
        for u in self._box(self.unit.move + high):
            if pred(u) or not u.needs_heal:
                continue
            stand = self._ranged_stand(u.tile, low, high, reach)
            if stand is None:
                continue
            ratio = heal_percent(u)
            if ratio <= best_ratio:
                best, best_ratio = (u, stand), ratio
        if best is None:
            return None
        u, stand = best
        return self._candidate(index, item, u, stand, f"on {self.world.name(u.pid)} (HP {best_ratio}%)")

    def _staff_fortify(self, index, item, pred, reach):
        """Fortify: needs 3 units on the map not hostile to it that need healing; the tile with the most of
        them at 1..range (a tie: the better tile score)."""
        unit, world, state = self.unit, self.world, self.state
        wounded = [u for u in state.living() if not hostile(unit.faction, u.faction) and u.needs_heal]
        if len(wounded) < 3:
            return None
        high = max_range(unit, item)
        best, best_count = None, -1
        x, y = unit.tile
        for tile in sorted(reach, key=lambda t: (t[1], t[0])):
            if abs(tile[0] - x) > unit.move or abs(tile[1] - y) > unit.move:
                continue
            if not standable(world, state, tile) or not self._free(tile):
                continue
            count = sum(1 for u in wounded if 1 <= movement.distance(u.tile, tile) <= high
                        and standable(world, state, u.tile))
            if count and count > best_count:
                best, best_count = tile, count
            elif count and count == best_count and self.tile_score(tile) > self.tile_score(best):
                best = tile
        if best is None:
            return None
        return self._candidate(index, item, None, best, f"on {best_count} units", area=True)

    def _staff_restore(self, index, item, pred, reach):
        """Restore: the unit of its side with a status and the highest effective level."""
        best, best_level = None, 0
        for u in self._box(self.unit.move + max_range(self.unit, item)):
            if pred(u) or not u.status or effective_level(u) < best_level:
                continue
            stand = self._adjacent_stand(u.tile, reach)
            if stand is not None:
                best, best_level = (u, stand), effective_level(u)
        if best is None:
            return None
        return self._candidate(index, item, best[0], best[1], f"on {self.world.name(best[0].pid)}")

    def _staff_ward(self, index, item, pred, reach):
        """Ward: the unit of its side with the lowest Res."""
        best, best_res = None, 255
        for u in self._box(self.unit.move + max_range(self.unit, item)):
            if pred(u) or u.stats[7] > best_res:
                continue
            stand = self._adjacent_stand(u.tile, reach)
            if stand is not None:
                best, best_res = (u, stand), u.stats[7]
        if best is None:
            return None
        return self._candidate(index, item, best[0], best[1], f"on {self.world.name(best[0].pid)} (Res {best_res})")

    def _status_staff(self, index, item, pred, reach, ok, bonus):
        unit = self.unit
        low, high = max(1, item.min_range), max_range(unit, item)
        best, best_value, best_hit = None, 0, 0
        for u in self._box(unit.move + high):
            if not pred(u) or not ok(u):
                continue
            stand = self._ranged_stand(u.tile, low, high, reach)
            if stand is None:
                continue
            hit = magic_hit(unit, u)
            if hit > 4 and best_value <= hit + bonus(u):
                best, best_value, best_hit = (u, stand), hit + bonus(u), hit
        if best is None:
            return None
        return self._candidate(index, item, best[0], best[1],
                               f"on {self.world.name(best[0].pid)} (hit {best_hit}, score {best_value})")

    def _staff_silence(self, index, item, pred, reach):
        """Silence: a foe not silenced holding a usable tome or staff, hit over 4; the best hit + Mag."""
        world = self.world

        def magic_user(u):
            return u.status != "silence" and any(
                world.can_wield(u, it) and (it.weapon_type in combat.MAGIC_TYPES) for _i, it in equipment(world, u))

        return self._status_staff(index, item, pred, reach, magic_user, lambda u: u.stats[2])

    def _staff_sleep(self, index, item, pred, reach):
        """Sleep, Berserk: a foe with no status holding a usable weapon or staff, hit over 4; the best hit +
        effective level."""
        world = self.world

        def armed(u):
            return not u.status and any(world.can_wield(u, it) for _i, it in equipment(world, u))

        return self._status_staff(index, item, pred, reach, armed, effective_level)

    def _staff_warp(self, index, item, pred, reach):
        """Warp (``ai_pick_attack_target_by_stat_compare``): the unit of its side that hasn't acted, doesn't
        need healing and isn't escaping with the highest effective level, next to a tile it can reach; then
        ``ai_resolve_ranged_attack_approach_tile`` picks where to send it: the last unit of the phase's side
        standing in the might threat map of the target's foes, the nearest foe of that unit (by path), and
        among the free tiles the target could reach from that foe's tile and within Mag/2 (5..15) of the
        target, the lowest might threat."""
        world, state, unit = self.world, self.state, self.unit
        best, best_level = None, 0
        for u in self._box(unit.move + max_range(unit, item)):
            if u.done or pred(u) or u.needs_heal or effective_level(u) < best_level:
                continue
            stand = self._adjacent_stand(u.tile, reach)
            if stand is not None:
                best, best_level = (u, stand), effective_level(u)
        if best is None:
            return None
        target, stand = best
        threat = might_threat_map(world, state, target.faction)
        endangered = None
        for u in sorted(state.living(state.phase), key=lambda u: u.uid):
            if threat.get(u.tile, 0):
                endangered = u
        if endangered is None:
            return None
        paths = movement.search(world, state, endangered, budget=world.width * world.height)
        foe, foe_cost = None, 0xFF
        for tile in sorted(paths, key=lambda t: (t[1], t[0])):
            other = state.unit_at(*tile)
            if other is None or not hostile(endangered.faction, other.faction):
                continue
            if paths[tile][0] < foe_cost and standable(world, state, tile):
                foe, foe_cost = other, paths[tile][0]
        if foe is None:
            return None
        warp_range = min(15, max(5, unit.stats[2] // 2))
        dest, dest_threat = None, 0xFFFF
        for tile in sorted(movement.destinations(world, state, target, start=foe.tile),
                           key=lambda t: (t[1], t[0])):
            if state.unit_at(*tile) is not None or not standable(world, state, tile):
                continue
            if movement.distance(target.tile, tile) <= warp_range and threat.get(tile, 0) < dest_threat:
                dest, dest_threat = tile, threat.get(tile, 0)
        if dest is None:
            return None
        return self._candidate(index, item, target, stand, f"sends {world.name(target.pid)} to {dest}", to=dest)

    # -- steal -----------------------------------------------------------------------------------
    def steal_pairs(self, pred, stands) -> list:
        """The units the predicate accepts next to (through the map links) each tile in ``stands``,
        rows then columns (``scan_map_and_call_vtable_threat`` with ``check_occupancy_and_dispatch_adjacent``)."""
        out = []
        for tile in sorted(stands, key=lambda t: (t[1], t[0])):
            if getattr(self.world.terrain_at(*tile), "flag7", 0) or not self._free(tile):
                continue
            for dx, dy in LINK_ORDER:
                n = (tile[0] + dx, tile[1] + dy)
                other = self.state.unit_at(*n)
                if other is not None and other.uid != self.unit.uid and self.world.linked(*tile, *n) and pred(other):
                    out.append(other)
        return out

    def try_steal(self, pred, stands) -> Optional[dict]:
        """``check_steal_action_targeted`` / ``_scan``: needs Steal; among the units next to a tile it can
        reach that it is faster than (Spd strictly higher), the first item (inventory order) it can carry
        that ``TBL_STEALITEMS`` lists; the earliest listed wins, the first found on a tie."""
        world, unit = self.world, self.unit
        if "SID_STEAL" not in unit.skills:
            return None
        table = []
        if world.cp is not None:
            section = world.cp.section(cp_data.STEAL_SECTION)
            if section is not None:
                table = [str(v) for v in cp_data.read_list(section)]
        best, best_score = None, 1 << 31
        for foe in self.steal_pairs(pred, stands):
            if not unit.stats[4] > foe.stats[4]:
                continue
            for index, (iid, _uses, _drop) in enumerate(self._slot_order(foe)):
                item = world.items.get(iid)
                if item is None or not can_carry(world, unit, item) or iid not in table:
                    continue
                score = table.index(iid)
                if score < best_score:
                    best, best_score = (foe, index, iid), score
                break
        if best is None:
            return None
        foe, _index, iid = best
        dest = self._adjacent_stand(foe.tile, stands)
        if dest is None:
            return None
        unit.steals += 1
        slot = next(i for i, e in enumerate(foe.items) if e[0] == iid)
        return {"action": "steal", "dest": dest, "target": foe.uid, "item": slot,
                "text": f"steal {world.item_name(iid)} from {world.name(foe.pid)} (list #{best_score}) from {dest}"}

    def _slot_order(self, unit: SimUnit) -> list:
        """The unit's items as the game's slots hold them: weapons and staves, then the rest."""
        return [unit.items[i] for i, _it in equipment(self.world, unit)] + \
               [unit.items[i] for i, _it in carried_items(self.world, unit)]

    # -- items -----------------------------------------------------------------------------------
    def _heal_amount(self, iid: str) -> int:
        return self.unit.stats[0] if iid == "IID_ELIXIR" else ITEM_HEAL.get(iid, 0)

    def _better_item(self, best, cand) -> bool:
        """The heal-item comparison: the heal amount closer to the HP missing (the smaller on a tie);
        equal amounts: fewer uses left, the later one when they are equal too."""
        if best is None:
            return True
        hb, hc = self._heal_amount(best[1]), self._heal_amount(cand[1])
        if hb == hc:
            return not (best[2] < cand[2])
        small, large = (best, cand) if hb < hc else (cand, best)
        missing = self.unit.stats[0] - self.unit.hp
        hs, hl = self._heal_amount(small[1]), self._heal_amount(large[1])
        return (small if abs(missing - hs) <= abs(missing - hl) else large) is cand

    def _heal_items(self, unit: SimUnit) -> list:
        """(index, iid, uses) of the category-0x81 items in slots 4-7."""
        return [(i, item.iid, unit.items[i][1]) for i, item in carried_items(self.world, unit)
                if item.iid in HEALING]

    def safest_tile(self) -> tuple:
        """``find_minimum_cost_movement_tile``: the reachable tile with the lowest threat."""
        reach = self._reach()
        best, best_threat = self.unit.tile, 0xFFFF
        for tile in sorted(reach, key=lambda t: (t[1], t[0])):
            if not standable(self.world, self.state, tile) or not self._free(tile):
                continue
            if self._threat().get(tile, 0) < best_threat:
                best, best_threat = tile, self._threat().get(tile, 0)
        return best

    def use_own_heal_item(self) -> Optional[dict]:
        """``check_use_healing_item_action_variant``: use its own Vulnerary or Elixir on the safest tile."""
        best = None
        for cand in self._heal_items(self.unit):
            if self._better_item(best, cand):
                best = cand
        if best is None:
            return None
        dest = self.safest_tile()
        return {"action": "item", "dest": dest, "item": best[0],
                "text": f"use {self.world.item_name(best[1])} on {dest}"}

    def take_heal_item(self) -> Optional[dict]:
        """``check_use_healing_item_action`` (action 0x34): with a free item slot, take the best healing
        item of a unit of its side next to a tile it can reach, and use it."""
        unit = self.unit
        if len(carried_items(self.world, unit)) >= ITEM_SLOTS:
            return None
        reach = self._reach()
        best = None
        for ally in self.steal_pairs(lambda u: u.faction == unit.faction, reach):
            for cand in self._heal_items(ally):
                if self._better_item(best and best[1:], cand):
                    best = (ally,) + cand
        if best is None:
            return None
        ally, index, iid, _uses = best
        dest = self._adjacent_stand(ally.tile, reach)
        if dest is None:
            return None
        return {"action": "take_item", "dest": dest, "target": ally.uid, "item": index,
                "text": f"take {self.world.item_name(iid)} from {self.world.name(ally.pid)} and use it, at {dest}"}

    def item_usable(self, iid: str) -> bool:
        """The item's own use check (``FUN_80091f70``), as far as the simulator applies items: healing
        items while hurt, stat drops always. Other items aren't simulated (never usable here)."""
        if iid in ("IID_VULNERARY", "IID_ELIXIR"):
            return self.unit.hp < self.unit.stats[0]
        return iid.endswith("DROP")

    # -- the heal step ---------------------------------------------------------------------------
    def foes_around(self, tile: tuple) -> int:
        """``count_adjacent_matching_units`` with ``check_faction_mismatch``: hostile units within 3 tiles."""
        count = 0
        for dx, dy in COUNT_TABLE:
            other = self.state.unit_at(tile[0] + dx, tile[1] + dy)
            if other is not None and hostile(self.unit.faction, other.faction):
                count += 1
        return count

    def _pick_refuge(self, tiles: dict, ok) -> Optional[tuple]:
        """The refuge rule of the three retreat searches: fewer foes around and a lower path cost
        (both must hold: a tile with fewer foes but a higher cost is skipped)."""
        best, best_count, best_cost = None, 1 << 31, 0xFF
        for tile in sorted(tiles, key=lambda t: (t[1], t[0])):
            if not ok(tile):
                continue
            count = self.foes_around(tile)
            cost = tiles[tile][0]
            if count <= best_count and cost < best_cost:
                best, best_count, best_cost = tile, count, cost & 0xFF
        return best

    def heal_step(self) -> Optional[dict]:
        """``dispatch_ai_heal_steal_rescue_action``: when the heal record has priority and the unit needs
        healing: its own healing item, else an ally's, else (not escaping) a healing tile in reach, a healing
        tile or a healer anywhere, or a unit holding a healing item; after such a move, Steal or an attack
        from the tile it reaches."""
        from .ai_vm import _hold

        world, state, unit = self.world, self.state, self.unit
        record = heal_record(world, unit)
        if record is None or not record.priority or not update_needs_heal(world, unit):
            return None
        self.emit(f"needs healing: HP {heal_percent(unit)}% (flagged under {record.retreat_below}%, "
                  f"until {record.resume_at}%)")
        for routine in (self.use_own_heal_item, self.take_heal_item):
            cand = routine()
            if cand is not None:
                return cand

        def heal_tile(tile):
            t = world.terrain_at(*tile)
            return t is not None and t.heal

        def open_tile(tile):
            return standable(world, state, tile) and state.unit_at(*tile) is None

        reach = self._reach()
        dest = self._pick_refuge(reach, lambda t: open_tile(t) and heal_tile(t))
        how = "retreats to the healing tile"
        if dest is None:
            everywhere = movement.search(world, state, unit, budget=world.width * world.height)

            def refuge(tile):
                if not standable(world, state, tile):
                    return False
                other = state.unit_at(*tile)
                if heal_tile(tile):
                    if other is None:
                        return True
                    # a unit of its side on it is passed over when it can't move away (status, or the
                    # dispo hold flag: +0x254 0x3000000) and holds no healing staff
                    stuck = bool(other.status) or _hold(other)
                    return not hostile(unit.faction, other.faction) and                         (not stuck or holds_healing_staff(world, other))
                return other is not None and not hostile(unit.faction, other.faction) and \
                    holds_healing_staff(world, other)

            goal = self._pick_refuge(everywhere, refuge)
            how = "heads for the refuge"
            if goal is None:
                goal = self._pick_refuge(everywhere, lambda t: (o := state.unit_at(*t)) is not None
                                         and o.uid != unit.uid and not hostile(unit.faction, o.faction)
                                         and bool(self._heal_items(o)))
                how = "heads for the unit with a healing item"
            if goal is None or goal == unit.tile:
                return None
            dest = self._toward(goal)
            if dest is None:
                return None
            how += f" {goal}"
        cand = {"action": "wait", "dest": dest, "text": f"{how}: moves to {dest}"}
        steal = self.try_steal(self._predicate(), {dest: (0, None)})
        if steal is not None:
            return steal
        attack = self._best_attack(self._attack_targets(), in_place=False, tiles={dest: reach.get(dest, (0, None))})
        return attack or cand

    def _toward(self, goal: tuple) -> Optional[tuple]:
        """The tile of the unit's reach on the cheapest path to ``goal`` that is furthest along it."""
        reach = self._reach()
        found = movement.search(self.world, self.state, self.unit, budget=self.world.width * self.world.height)
        for tile in reversed(movement.path(found, goal)):
            if tile in reach and self._free(tile) and standable(self.world, self.state, tile):
                return tile if tile != self.unit.tile else None
        return None

    def _attack_targets(self) -> list:
        return [u for u in self.state.living() if u.uid != self.unit.uid and hostile(self.unit.faction, u.faction)]
