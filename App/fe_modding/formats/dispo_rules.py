"""Which deployment-record controls make sense for a given unit.

The Build tab's unit inspector uses these to show only the relevant
controls. The rules come from an audit of all 158 vanilla dispo variants
(6473 units); they hide controls, they never forbid a value: anything the
record already holds is still shown, and "All fields..." edits everything.

- the starting laguz gauge is set only on laguz-class units (the audit found
  it on 92 enemy laguz and 2 non-laguz outliers);
- the AI fields (28-31, 39) drive every non-player unit. Player-faction units
  are AI-controlled in vanilla only on 350 of about 2000 records (escorts,
  rescue targets), so for them the AI is offered on request and shown at
  once when it is not the inert default;
- the "ignore in first playthrough" item flag (0x02) is only on the class
  rings and ``IID_COIN`` in vanilla, but the loader honours it on any item,
  so it is always offered;
- the loader puts weapons and staves in inventory slots 1-4 and every
  other item in slots 5-8, whatever record slot names them, but applies an
  item's drop flag to the inventory slot with the record slot's number
  (``add_item_to_first_free_slot`` 0x80094ABC, ``init_actor_from_deployment_record``);
- flag bit 0x80 is never read; 0x10/0x20 (AI Door Key / Chest Key) are
  set on only one vanilla record each but are shown, since they work.
"""

from __future__ import annotations

from typing import Callable, Optional

from . import dispo, fe8data

PLAYER_FACTION = 0
#: The AI a player unit carries in vanilla when it is not AI-controlled.
INERT_AI = {"seq_attack": "SEQ_NOATTACK", "seq_move": "SEQ_NOMOVE", "seq_heal": "SEQ_NOHEAL"}
#: Flag bits worth showing by default; the others appear when already set.
COMMON_FLAG_MASKS = (dispo.FLAG_AUTOLEVEL, dispo.FLAG_HOLD_POSITION, dispo.FLAG_COMMANDER,
                     dispo.FLAG_SPAWN_WHEN_ABSENT, dispo.FLAG_AI_DOOR_KEY, dispo.FLAG_AI_CHEST_KEY,
                     dispo.FLAG_BRIDGE_BARRIER)


def laguz_lookup(fe8: Optional[fe8data.Fe8Data]) -> Callable[[object, object], bool]:
    """``is_laguz(jid, pid)``: whether the class the unit ends up with is a
    laguz one. A null class means the character's own."""
    if fe8 is None:
        return lambda jid, pid: False
    classes = {c.jid: c for c in fe8.classes if c.jid}
    characters = {c.pid: c for c in fe8.characters if c.pid}
    cache: dict[str, bool] = {}

    def is_laguz(jid, pid) -> bool:
        if not isinstance(jid, str):
            character = characters.get(pid) if isinstance(pid, str) else None
            jid = character.jid if character is not None else None
        if jid not in cache:
            cls = classes.get(jid)
            cache[jid] = cls is not None and fe8data.class_category(cls, fe8.classes) == "Laguz"
        return cache[jid]

    return is_laguz


def show_laguz_gauge(is_laguz: bool, gauge: int) -> bool:
    return is_laguz or gauge != 0


def ai_is_inert(seq_attack, seq_move, seq_heal, ai_order: int) -> bool:
    return (seq_attack, seq_move, seq_heal) == tuple(INERT_AI.values()) and ai_order == 0


def show_ai(faction: int, seq_attack, seq_move, seq_heal, ai_order: int) -> bool:
    """Whether the AI rows show by default: always off the player army, and on
    it only when the record holds a real behaviour."""
    return faction != PLAYER_FACTION or not ai_is_inert(seq_attack, seq_move, seq_heal, ai_order)


def is_ring_item(iid) -> bool:
    return isinstance(iid, str) and (iid.endswith("RING") or iid == "IID_COIN")


def show_ring_flag(iid, flag: int) -> bool:
    """The flag works on any item (the loader checks it for every slot)."""
    return True


def item_flag_bits(iid, flag: int):
    """``ITEM_FLAG_BITS`` that apply to this item (all of them)."""
    return dispo.ITEM_FLAG_BITS


#: Record slots 0-3 hold weapons and staves, 4-7 every other item.
WEAPON_SLOTS = range(0, 4)
ITEM_SLOTS = range(4, 8)


def weapon_lookup(fe8: Optional[fe8data.Fe8Data]) -> Callable[[object], Optional[bool]]:
    """``is_weapon(iid)``: True for weapons and staves (the inventory's slots
    1-4), False for other items, None when unknown."""
    if fe8 is None:
        return lambda iid: None
    kinds = {i.iid: i.weapon_type not in ("item", "acc", None) for i in fe8.items if i.iid}
    return lambda iid: kinds.get(iid) if isinstance(iid, str) else None


def unit_flag_bits(flags: int):
    """``FLAG_BITS`` without the unread bit 0x80, unless the record sets it."""
    return tuple(bit for bit in dispo.FLAG_BITS if bit[0] in COMMON_FLAG_MASKS or flags & bit[0])


def warnings(faction: int, is_laguz: bool, gauge: int, items: list[tuple[object, int]],
             is_weapon: Optional[Callable[[object], Optional[bool]]] = None) -> list[str]:
    """Combinations the game will not honour, for a confirmation on Apply.
    ``items`` are the eight record slots in order."""
    found = []
    if gauge and not is_laguz:
        found.append("The starting laguz gauge is set on a unit that is not a laguz class; it will not be used.")
    if sum(1 for _iid, flag in items if flag & dispo.ITEM_FLAG_DROP) > 1:
        found.append("More than one item is flagged to drop; the game drops one item per unit.")
    if is_weapon is not None:
        held = [(slot, iid, is_weapon(iid)) for slot, (iid, _flag) in enumerate(items) if isinstance(iid, str)]
        weapons = [iid for _slot, iid, weapon in held if weapon]
        others = [iid for _slot, iid, weapon in held if weapon is False]
        if len(weapons) > 4:
            found.append(f"{len(weapons)} weapons/staves: a unit holds 4; {', '.join(weapons[4:])} will not be given.")
        if len(others) > 4:
            found.append(f"{len(others)} items: a unit holds 4; {', '.join(others[4:])} will not be given.")
        for slot, iid, weapon in held:
            if weapon is None or (slot in WEAPON_SLOTS) == weapon:
                continue
            where = "weapon slots 1-4" if weapon else "item slots 5-8"
            note = (" Its Drops flag would land on another inventory slot."
                    if items[slot][1] & dispo.ITEM_FLAG_DROP else "")
            found.append(f"{iid} is in slot {slot + 1}; the game puts it in {where} anyway.{note}")
    return found
