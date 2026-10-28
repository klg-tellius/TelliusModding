"""One character's supports, read the same way on both games for the one Supports tab.

:class:`gui.support_editor.CharacterSupportsPanel` shows a character's affinity, support partners and
bonds through a :class:`SupportsModel`. The game adapters pick the model
(``session.adapter.supports_model(data)``):

- Path of Radiance (:class:`PorSupports`, :mod:`formats.supports`): each character lists up to 10
  partners with the points at which C, B and A open; a pair is written to both lists; bonds have an
  effect and a value; support conversations are ``Mess/yell.m`` messages.
- Radiant Dawn (:class:`RdSupports`, :mod:`formats.fe10data`): RelianceData lists every supporting
  character against all of them, each entry with a flag and a growth speed, so partners are edited,
  not added; bonds (KiznaData) have a bonus; support chat lines are in Assets › Conversation Lists.

A model reads one snapshot of the file. Every write takes the current bytes and returns new ones; the
panel then builds a new model from them.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from .formats import fe8data, fe10data, supports


@dataclass(frozen=True)
class PairField:
    """One editable number of a support pair or a bond (``options``: a choice of ``(value, name)``)."""
    label: str
    low: int
    high: int
    options: tuple = ()


@dataclass(frozen=True)
class PartnerRow:
    #: The partner's PID, None for an empty slot.
    partner: Optional[str]
    slot: int
    #: The cells after the partner column, as shown.
    cells: tuple


@dataclass(frozen=True)
class BondRow:
    key: int
    other: str
    cells: tuple


def _int(text: str, field: PairField) -> int:
    if field.options:
        text = text.split(":")[0]
    try:
        value = int(str(text).strip(), 0)
    except ValueError:
        raise ValueError(f"{field.label} must be a whole number.") from None
    if not field.low <= value <= field.high:
        raise ValueError(f"{field.label} must be between {field.low} and {field.high}.")
    return value


class SupportsModel:
    """What the Supports tab shows and edits. Subclasses fill these per game."""

    #: ``(heading, width)`` of the partner cells after Slot and Partner.
    partner_columns: tuple = ()
    pair_fields: tuple = ()
    pair_note: str = ""
    #: Whether partners are added and removed (otherwise the list is fixed and only edited).
    can_add_partners: bool = True
    bond_columns: tuple = ()
    bond_fields: tuple = ()
    bond_note: str = ""
    #: Support conversation ranks with one Edit/Create button each; empty: one "Open conversations" link.
    conversation_ranks: tuple = ()
    affinity_names: tuple = ()
    affinity_note: str = ""

    pids: list

    def affinity_of(self, pid: str) -> str:
        raise NotImplementedError

    def set_affinity(self, data: bytes, pid: str, name: str) -> bytes:
        raise NotImplementedError

    def partners(self, pid: str, conversations: Optional[set] = None) -> list[PartnerRow]:
        raise NotImplementedError

    def slot_note(self, pid: str) -> str:
        return ""

    def pair_values(self, pid: str, partner: str) -> tuple:
        raise NotImplementedError

    def set_pair(self, data: bytes, pid: str, partner: str, texts: list[str]) -> bytes:
        raise NotImplementedError

    def add_partner(self, data: bytes, pid: str, partner: str) -> bytes:
        raise ValueError("Partners are not added on this game.")

    def remove_partner(self, data: bytes, pid: str, partner: str) -> bytes:
        raise ValueError("Partners are not removed on this game.")

    def bonds(self, pid: str) -> list[BondRow]:
        raise NotImplementedError

    def bond_values(self, key: int) -> tuple:
        raise NotImplementedError

    def set_bond(self, data: bytes, key: int, texts: list[str]) -> bytes:
        raise NotImplementedError

    def add_bond(self, data: bytes, pid: str, other: str) -> bytes:
        raise NotImplementedError

    def remove_bond(self, data: bytes, key: int) -> bytes:
        raise NotImplementedError

    def bond_other(self, key: int, pid: str) -> str:
        raise NotImplementedError

    def problems(self, pid: str) -> list[str]:
        return []


RANKS = ("C", "B", "A")
DEFAULT_THRESHOLDS = (1, 3, 5)  # the most common real (non-filler) thresholds in vanilla


def conversation_id(pid_a: str, pid_b: str, rank: str) -> str:
    """``MYELL_<A>_<B>_<rank>``: the two names without ``PID_``, in alphabetical order."""
    a, b = sorted(p[4:] if p.startswith("PID_") else p for p in (pid_a, pid_b))
    return f"MYELL_{a}_{b}_{rank}"


class PorSupports(SupportsModel):
    partner_columns = (("Partner affinity", 110), ("C at", 50), ("B at", 50), ("A at", 50),
                       ("Bonus at A (each unit)", 230), ("Conversations", 110))
    pair_fields = (PairField("C at", 0, 253), PairField("B at", 1, 253), PairField("A at", 2, 254))
    pair_note = ("Both units gain 1 point at the end of each chapter they finish on the map together; the base "
                 "offers the conversation when the points reach C, B or A, and viewing it raises the rank. A unit "
                 "holds at most 5 support stars (C=1, B=2, A=3) and 10 partners. A pair is written to both "
                 "characters' lists; a removed partner leaves an empty slot so existing saves keep their points. "
                 "Double-click a partner to open their page.")
    bond_columns = (("This character is", 110), ("Effect", 280), ("Value", 60))
    bond_fields = (PairField("Effect", 0, 255, tuple(supports.BOND_KIND_NAMES.items())), PairField("Value", -128, 127))
    bond_note = ("Effect 1: while the two stand next to each other (same army), each gets Value extra Critical. "
                 "Effect 2: while the second character stands next to the first, enemies have 0 Critical against "
                 "the second (Value unused). Bonds need no support pair.")
    conversation_ranks = RANKS
    affinity_names = tuple(supports.AFFINITY_NAMES)
    affinity_note = "Bonuses reach allies of the same army within 3 tiles; both units' rows count."

    def __init__(self, data: bytes):
        self.fe8 = fe8data.read_fe8data(data)
        self.pids = list(dict.fromkeys(c.pid for c in self.fe8.characters if c.pid))
        self.lists = supports.read_support_lists(data)
        self.rows = supports.read_affinities(data)
        self.bond_list = supports.read_bonds(data)
        self._affinities: dict[str, int] = {}
        for c in self.fe8.characters:
            if c.pid and c.pid not in self._affinities:
                self._affinities[c.pid] = supports.character_affinity(data, c.index)

    def _list(self, pid):
        return next((x for x in self.lists if x.owner == pid), None)

    def affinity_of(self, pid):
        return supports.AFFINITY_NAMES[self._affinities.get(pid, 0)]

    def set_affinity(self, data, pid, name):
        affinity = supports.AFFINITY_NAMES.index(name or "None")
        for c in self.fe8.characters:
            if c.pid == pid:
                data = supports.patch_character_affinity(data, c.index, affinity)
        return data

    def partners(self, pid, conversations=None):
        own = self._affinities.get(pid, 0)
        rows = []
        sl = self._list(pid)
        for i, slot in enumerate(sl.slots if sl else []):
            if slot.empty:
                rows.append(PartnerRow(None, i, ("",) * len(self.partner_columns)))
                continue
            other = self._affinities.get(slot.partner, 0)
            bonus = supports.pair_bonus(self.rows, own, other, 3)
            text = ", ".join(f"{n} +{v}" for n, v in zip(supports.BONUS_NAMES, bonus) if v) or "none"
            have = "".join(r if conversation_id(pid, slot.partner, r) in conversations else "·" for r in RANKS) \
                if conversations is not None else ""
            rows.append(PartnerRow(slot.partner, i, (supports.AFFINITY_NAMES[other], slot.c, slot.b, slot.a,
                                                     text, have)))
        return rows

    def slot_note(self, pid):
        sl = self._list(pid)
        used = sum(1 for slot in sl.slots if not slot.empty) if sl else 0
        slots = len(sl.slots) if sl else 0
        return f"{used} partner{'s' if used != 1 else ''}, {slots} of {supports.MAX_SLOTS} slots used"

    def pair_values(self, pid, partner):
        sl = self._list(pid)
        slot = sl.slots[sl.slot_of(partner)] if sl and sl.slot_of(partner) >= 0 else None
        return (str(slot.c), str(slot.b), str(slot.a)) if slot else ("", "", "")

    def set_pair(self, data, pid, partner, texts):
        c, b, a = (_int(t, f) for t, f in zip(texts, self.pair_fields))
        if not c < b < a:
            raise ValueError("The thresholds must rise: C < B < A.")
        lists = supports.read_support_lists(data)
        supports.set_pair(lists, pid, partner, c, b, a)
        return supports.write_support_lists(data, lists)

    def add_partner(self, data, pid, partner):
        lists = supports.read_support_lists(data)
        sl = next((x for x in lists if x.owner == pid), None)
        if sl is not None and sl.slot_of(partner) >= 0:
            raise ValueError(f"{partner} is already a partner.")
        supports.set_pair(lists, pid, partner, *DEFAULT_THRESHOLDS)
        return supports.write_support_lists(data, lists)

    def remove_partner(self, data, pid, partner):
        lists = supports.read_support_lists(data)
        supports.remove_pair(lists, pid, partner)
        return supports.write_support_lists(data, lists)

    def bonds(self, pid):
        rows = []
        for i, bd in enumerate(self.bond_list):
            if pid not in (bd.pid1, bd.pid2):
                continue
            rows.append(BondRow(i, bd.pid2 if bd.pid1 == pid else bd.pid1, (
                "first" if bd.pid1 == pid else "second", supports.BOND_KIND_NAMES.get(bd.kind, f"unknown {bd.kind}"),
                bd.value)))
        return rows

    def bond_values(self, key):
        bd = self.bond_list[key]
        return (f"{bd.kind}: {supports.BOND_KIND_NAMES.get(bd.kind, '')}", str(bd.value))

    def set_bond(self, data, key, texts):
        old = self.bond_list[key]
        kind, value = (_int(t, f) for t, f in zip(texts, self.bond_fields))
        if (kind, value) == (old.kind, old.value):
            return data
        bonds = list(self.bond_list)
        bonds[key] = supports.Bond(old.pid1, old.pid2, kind, value, old.tail)
        return supports.write_bonds(data, bonds)

    def add_bond(self, data, pid, other):
        if other == pid:
            raise ValueError("A bond needs two different characters.")
        return supports.write_bonds(data, list(self.bond_list) + [supports.Bond(pid, other, supports.BOND_CRIT, 10)])

    def remove_bond(self, data, key):
        return supports.write_bonds(data, [bd for i, bd in enumerate(self.bond_list) if i != key])

    def bond_other(self, key, pid):
        bd = self.bond_list[key]
        return bd.pid2 if bd.pid1 == pid else bd.pid1

    def problems(self, pid):
        return [p for p in supports.validate_support_lists(self.lists) if pid and pid in p]


class RdSupports(SupportsModel):
    partner_columns = (("Partner affinity", 110), ("Flag", 60), ("Speed", 60))
    pair_fields = (PairField("Flag", 0, 255), PairField("Speed", 0, 255))
    pair_note = ("Radiant Dawn lists every supporting character against all of them (themselves included), so "
                 "the partners are edited, not added. Speed is the pair's growth speed (2 in most "
                 "retail entries); the flag is 0 or 255 in the retail data and its meaning is not decoded yet. "
                 "Each character's own list is edited; the partner's list keeps its own entry. Double-click a "
                 "partner to open their page.")
    can_add_partners = False
    bond_columns = (("This character is", 110), ("Bonus", 60))
    bond_fields = (PairField("Bonus", 0, 255),)
    bond_note = "The bonus between the two bonded units (5 or 10 in the retail data)."
    affinity_note = "The character's affinity also appears on the Stats tab."

    def __init__(self, data: bytes):
        self.db = fe10data.read_fe10data(data)
        self.pids = [r.id for r in self.db.characters if r.id]
        self.affinity_names = ("",) + tuple(dict.fromkeys(
            r.values.get("affinity") for r in self.db.table("affinity") if r.values.get("affinity")))
        self._support = {r.values.get("pid"): r for r in self.db.table("support")}
        self._characters = {r.id: r for r in self.db.characters}

    def affinity_of(self, pid):
        record = self._characters.get(pid)
        return (record.values.get("affinity") or "") if record else ""

    def set_affinity(self, data, pid, name):
        record = self._characters.get(pid)
        if record is None:
            return data
        return fe10data.patch_field(data, "character", record.index, "affinity", name or None)

    def partners(self, pid, conversations=None):
        record = self._support.get(pid)
        return [PartnerRow(partner, k, (self.affinity_of(partner or ""), flag, speed))
                for k, (partner, flag, speed) in enumerate(record.lists["partners"] if record else [])]

    def slot_note(self, pid):
        record = self._support.get(pid)
        if record is None:
            return "Not in the support table: this character has no supports."
        return f"{len(record.lists['partners'])} entries"

    def _entry(self, pid, partner):
        record = self._support.get(pid)
        if record is None:
            raise ValueError(f"{pid} is not in the support table.")
        k = next((k for k, (p, _f, _s) in enumerate(record.lists["partners"]) if p == partner), None)
        if k is None:
            raise ValueError(f"{partner} is not in {pid}'s support list.")
        return record, k

    def pair_values(self, pid, partner):
        record, k = self._entry(pid, partner)
        _p, flag, speed = record.lists["partners"][k]
        return (str(flag), str(speed))

    def set_pair(self, data, pid, partner, texts):
        flag, speed = (_int(t, f) for t, f in zip(texts, self.pair_fields))
        record, k = self._entry(pid, partner)
        return fe10data.set_support(data, record.index, k, flag, speed)

    def bonds(self, pid):
        rows = []
        for bond in self.db.table("bond"):
            a, b = bond.values.get("pid"), bond.values.get("partner")
            if pid not in (a, b):
                continue
            rows.append(BondRow(bond.index, b if a == pid else a, ("first" if a == pid else "second",
                                                                     bond.values.get("bonus"))))
        return rows

    def bond_values(self, key):
        return (str(self.db.table("bond")[key].values.get("bonus")),)

    def set_bond(self, data, key, texts):
        (bonus,) = (_int(t, f) for t, f in zip(texts, self.bond_fields))
        if bonus == self.db.table("bond")[key].values.get("bonus"):
            return data
        return fe10data.patch_field(data, "bond", key, "bonus", bonus)

    def add_bond(self, data, pid, other):
        if other == pid:
            raise ValueError("A bond needs two different characters.")
        if any({r.values.get("pid"), r.values.get("partner")} == {pid, other} for r in self.db.table("bond")):
            raise ValueError(f"A bond with {other} already exists.")
        if not self.db.table("bond"):
            raise ValueError("The bond table is empty: there is no record to copy.")
        data, index = fe10data.add_record(data, "bond", 0)
        data = fe10data.patch_field(data, "bond", index, "pid", pid)
        data = fe10data.patch_field(data, "bond", index, "partner", other)
        return fe10data.patch_field(data, "bond", index, "bonus", 10)

    def remove_bond(self, data, key):
        return fe10data.remove_record(data, "bond", key)

    def bond_other(self, key, pid):
        bond = self.db.table("bond")[key]
        return bond.values.get("partner") if bond.values.get("pid") == pid else bond.values.get("pid")
