"""Game Data edits loaded by the game: characters, classes, items (1.0 checklist section 2).

Each check edits one byte field through the format code the Game Data editors use, jumps into the first
map (PoR Prologue, RD 1-1) and compares the record the unit uses in RAM with the retail run.
"""
from __future__ import annotations

import re

from .core import Check, Jump
from .oracles import map_start, record_edit

POR_START, RD_START = Jump(1), Jump("0101", "Normal")


def _por_value(entry, field: str):
    match = re.fullmatch(r"([a-z_]+?)(\d)", field)
    if match and hasattr(entry, match.group(1)):
        return getattr(entry, match.group(1))[int(match.group(2))]
    return getattr(entry, field)


def por_edit(table: str, rid: str, field: str, delta: int):
    def fixture(ctx):
        from fe_modding.formats import fe8data
        db = ctx.data
        rows = {"character": (db.characters, "pid", fe8data.patch_character_field),
                "class": (db.classes, "jid", fe8data.patch_class_field),
                "item": (db.items, "iid", fe8data.patch_item_field)}[table]
        entry = next(e for e in rows[0] if getattr(e, rows[1]) == rid)
        old = _por_value(entry, field)
        ctx.fe8 = rows[2](ctx.fe8, entry.index, field, old + delta)
        ctx.facts.update(old=old, new=old + delta)
    return fixture


def rd_edit(kind: str, rid: str, key: str, delta: int):
    def fixture(ctx):
        from fe_modding.formats import fe10data
        data = ctx.project.read_logical("game_data")
        rec = next(r for r in fe10data.read_table(data, kind) if r.id == rid)
        old = rec.values[key]
        ctx.project.write_logical("game_data", fe10data.patch_field(data, kind, rec.index, key, old + delta))
        ctx.facts.update(old=old, new=old + delta)
    return fixture


CHECKS = [
    Check("G1", "por", "Ike's Str bonus +2 is the record his unit uses", ["1.0 §2 Characters ▸ Stats (POR)"],
          play=map_start(["PID_IKE"]), judge=record_edit("PID_IKE", "person"),
          fixture=por_edit("character", "PID_IKE", "stat_bonus1", 2), start=POR_START),
    Check("G2", "por", "Class movement +2 on Ike's class", ["1.0 §2 Game Data ▸ Classes (POR)"],
          play=map_start(["PID_IKE"]), judge=record_edit("PID_IKE", "job"),
          fixture=por_edit("class", "JID_RANGER", "movement", 2), start=POR_START),
    Check("G3", "por", "Item Might +5 (Ike's Practice Sword)", ["1.0 §2 Game Data ▸ Items (POR)"],
          play=map_start(["PID_IKE"]), judge=record_edit("PID_IKE", "item", "IID_PRACTICESWORD"),
          fixture=por_edit("item", "IID_PRACTICESWORD", "might", 5), start=POR_START),
    Check("G1r", "rd", "Micaiah's Str bonus +2 is the record her unit uses", ["1.0 §2 Characters ▸ Stats (RD)"],
          play=map_start(["PID_MICAIAH"]), judge=record_edit("PID_MICAIAH", "person"),
          fixture=rd_edit("character", "PID_MICAIAH", "bonus_str", 2), start=RD_START),
    Check("G2r", "rd", "Class movement +2 on Micaiah's class", ["1.0 §2 Game Data ▸ Classes (RD)"],
          play=map_start(["PID_MICAIAH"]), judge=record_edit("PID_MICAIAH", "job"),
          fixture=rd_edit("class", "JID_LIGHTMAGE", "movement", 2), start=RD_START),
    Check("G3r", "rd", "Iron Sword Might +5 (Edward's)", ["1.0 §2 Game Data ▸ Items (RD)"],
          play=map_start(["PID_EDDIE"]), judge=record_edit("PID_EDDIE", "item", "IID_IRONSWORD"),
          fixture=rd_edit("item", "IID_IRONSWORD", "might", 5), start=RD_START),
]
