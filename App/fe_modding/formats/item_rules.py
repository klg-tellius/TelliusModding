"""Optional FE9 item-use rules stored as an HSDArc export in FE8Data.bin.

The archive owns the IDs, so rules survive item-table reordering.  The extra
export is ignored by an unpatched game; the corresponding main.dol hook must
be installed before a project containing rules can be played.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass

from . import fe8data

SYMBOL = "ItemRestrictionData"
MAGIC = b"IRUL"
VERSION = 1


@dataclass(frozen=True)
class ItemRule:
    iid: str
    mode: str = "any"
    pids: tuple[str, ...] = ()
    jids: tuple[str, ...] = ()
    sids: tuple[str, ...] = ()

    @property
    def empty(self) -> bool:
        return not (self.pids or self.jids or self.sids)


def _rule_end(data: bytes, start: int) -> int:
    if data[start:start + 4] != MAGIC:
        raise ValueError("Invalid ItemRestrictionData magic.")
    version, count = struct.unpack_from(">HH", data, start + 4)
    if version != VERSION:
        raise ValueError(f"Unsupported ItemRestrictionData version {version}.")
    at = start + 8
    limit = fe8data.HEADER_SIZE + struct.unpack_from(">I", data, 4)[0]
    for _ in range(count):
        if at + 8 > limit:
            raise ValueError("Truncated item restriction record.")
        pid_count, jid_count, sid_count = data[at + 5:at + 8]
        at += 8 + 4 * (pid_count + jid_count) + 8 * sid_count
        if at > limit:
            raise ValueError("Truncated item restriction labels.")
    return at


def read_item_rules(data: bytes) -> dict[str, ItemRule]:
    """Read the optional rule export.  Vanilla FE8Data.bin returns {}."""
    offset = fe8data.symbol_offsets(data).get(SYMBOL)
    if offset is None:
        return {}
    start = fe8data.HEADER_SIZE + offset
    _rule_end(data, start)
    count = struct.unpack_from(">H", data, start + 6)[0]
    at = start + 8
    rules: dict[str, ItemRule] = {}
    for _ in range(count):
        iid_ptr, mode, npid, njid, nsid = struct.unpack_from(">IBBBB", data, at)
        at += 8
        iid = fe8data._resolve(data, iid_ptr)
        if not iid or mode not in (0, 1) or iid in rules:
            raise ValueError("Invalid item restriction identity or mode.")
        groups: list[tuple[str, ...]] = []
        for length in (npid, njid):
            group = []
            for _ in range(length):
                ptr = struct.unpack_from(">I", data, at)[0]
                at += 4
                label = fe8data._resolve(data, ptr)
                if not label:
                    raise ValueError("Invalid item restriction label.")
                group.append(label)
            groups.append(tuple(group))
        skills = []
        for _ in range(nsid):
            ptr, _index = struct.unpack_from(">II", data, at)
            at += 8
            label = fe8data._resolve(data, ptr)
            if not label:
                raise ValueError("Invalid item restriction skill.")
            skills.append(label)
        rules[iid] = ItemRule(iid, "all" if mode else "any", *groups, tuple(skills))
    return rules


def validate_item_rules(data: bytes, rules: dict[str, ItemRule]) -> None:
    fe8 = fe8data.read_fe8data(data)
    valid = {
        "IID_": {r.iid for r in fe8.items},
        "PID_": {r.pid for r in fe8.characters},
        "JID_": {r.jid for r in fe8.classes},
        "SID_": {r.sid for r in fe8.skills},
    }
    for iid, rule in rules.items():
        if rule.iid != iid or iid not in valid["IID_"]:
            raise ValueError(f"Item restriction refers to missing item {iid}.")
        if rule.mode not in ("any", "all"):
            raise ValueError(f"{iid}: mode must be any or all.")
        for prefix, labels in (("PID_", rule.pids), ("JID_", rule.jids), ("SID_", rule.sids)):
            if len(labels) > 255 or len(set(labels)) != len(labels):
                raise ValueError(f"{iid}: invalid or duplicate {prefix} entries.")
            for label in labels:
                if label not in valid[prefix]:
                    raise ValueError(f"{iid}: missing {prefix} reference {label}.")


def _write_symbol_table(data: bytes, symbols: list[tuple[int, str]]) -> bytes:
    _size, data_size, pointer_count, _count = struct.unpack_from(">IIII", data)
    table = fe8data.HEADER_SIZE + data_size + 4 * pointer_count
    entries, names = bytearray(), bytearray()
    for offset, name in symbols:
        entries += struct.pack(">II", offset, len(names))
        names += name.encode("ascii") + b"\x00"
    out = bytearray(data[:table]) + entries + names
    struct.pack_into(">I", out, 0, len(out))
    struct.pack_into(">I", out, 12, len(symbols))
    return bytes(out)


def write_item_rules(data: bytes, rules: dict[str, ItemRule]) -> bytes:
    """Replace rules, preserving every other archive section and symbol."""
    validate_item_rules(data, rules)
    old_offset = fe8data.symbol_offsets(data).get(SYMBOL)
    if not rules:
        if old_offset is None:
            return data
        start = fe8data.HEADER_SIZE + old_offset
        end = _rule_end(data, start)
        listed = [p for p in fe8data.pointer_list(data)[1]
                  if not (old_offset <= p < end - fe8data.HEADER_SIZE)]
        out = bytearray(data)
        out[start:end] = bytes(end - start)
        out = fe8data.write_pointer_list(out, listed)
        return _write_symbol_table(bytes(out), [(off, name) for _pos, off, name in fe8data._symbol_entries(out)
                                                if name != SYMBOL])

    skill_index = {r.sid: r.index for r in fe8data.read_fe8data(data).skills}
    block = bytearray(MAGIC + struct.pack(">HH", VERSION, len(rules)))
    pointer_fields: list[int] = []

    def ptr(label: str) -> None:
        offset = fe8data._label_offset(data, label)
        if offset is None or offset >= struct.unpack_from(">I", data, 4)[0]:
            raise ValueError(f"No relocatable data label for {label}.")
        pointer_fields.append(len(block))
        block.extend(struct.pack(">I", offset))

    for iid in sorted(rules):
        rule = rules[iid]
        ptr(iid)
        block.extend(bytes((int(rule.mode == "all"), len(rule.pids), len(rule.jids), len(rule.sids))))
        for label in (*rule.pids, *rule.jids):
            ptr(label)
        for label in rule.sids:
            ptr(label)
            block.extend(struct.pack(">I", skill_index[label]))

    if old_offset is not None:
        start = fe8data.HEADER_SIZE + old_offset
        end = _rule_end(data, start)
        return fe8data.replace_section(data, SYMBOL, end, bytes(block), pointer_fields)
    out, offset = fe8data.append_block(data, bytes(block), pointer_fields)
    symbols = [(off, name) for _pos, off, name in fe8data._symbol_entries(out)]
    return _write_symbol_table(out, symbols + [(offset, SYMBOL)])


def rule_matches(rule: ItemRule, pid: str, jid: str, sids: set[str]) -> bool:
    """Pure rule evaluator for previews and tests; vanilla checks are separate."""
    groups = [(rule.pids, pid), (rule.jids, jid), (rule.sids, sids)]
    matched = [value in allowed if isinstance(value, str) else bool(set(allowed) & value)
               for allowed, value in groups if allowed]
    return all(matched) if rule.mode == "all" else any(matched) if matched else True
