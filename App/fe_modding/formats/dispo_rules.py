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
- the ring item flag is used only on ring accessories and ``IID_COIN``;
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
    return is_ring_item(iid) or bool(flag & dispo.ITEM_FLAG_RING)


def item_flag_bits(iid, flag: int):
    """``ITEM_FLAG_BITS`` restricted to the bits that apply to this item."""
    return tuple(bit for bit in dispo.ITEM_FLAG_BITS
                 if bit[0] != dispo.ITEM_FLAG_RING or show_ring_flag(iid, flag))


def unit_flag_bits(flags: int):
    """``FLAG_BITS`` without the unread bit 0x80, unless the record sets it."""
    return tuple(bit for bit in dispo.FLAG_BITS if bit[0] in COMMON_FLAG_MASKS or flags & bit[0])


def warnings(faction: int, is_laguz: bool, gauge: int, items: list[tuple[object, int]]) -> list[str]:
    """Combinations the game will not honour, for a confirmation on Apply."""
    found = []
    if gauge and not is_laguz:
        found.append("The starting laguz gauge is set on a unit that is not a laguz class; it will not be used.")
    for iid, flag in items:
        if flag & dispo.ITEM_FLAG_RING and not is_ring_item(iid):
            found.append(f"{iid} is flagged as a ring but is not a ring item.")
    if sum(1 for _iid, flag in items if flag & dispo.ITEM_FLAG_DROP) > 1:
        found.append("More than one item is flagged to drop; the game drops one item per unit.")
    return found
