"""Reusable play functions and judges."""
from __future__ import annotations

from .ram_view import GameRam

RECORD_BYTES = 0x100


def unit_summary(u) -> dict:
    return {"handle": u.handle, "pid": u.pid, "jid": u.jid, "x": u.x, "y": u.y, "hp": u.hp, "level": u.level,
            "items": [[iid, uses] for iid, uses, _ptr in u.items]}


def map_start(pids=(), shot: str = "map") -> callable:
    """Play to the first player phase; observe every unit, and for each PID in ``pids`` the RAM bytes of
    its person record, class record and item records."""

    def play(driver, facts):
        driver.to_player_phase()
        game = GameRam(driver.ram, driver.build.game_id if driver.build.game_id in ("GFEE01", "RFEE01")
                       else ("RFEE01" if driver.build.wii else "GFEE01"))
        obs = {"party": game.party(), "units": [unit_summary(u) for u in game.units()], "records": {}}
        for pid in pids:
            u = game.unit(pid)
            obs["records"][pid] = {
                "person": game.record(u.person, RECORD_BYTES).hex(),
                "job": game.record(u.job, RECORD_BYTES).hex(),
                "items": {iid: game.record(ptr, RECORD_BYTES).hex() for iid, _uses, ptr in u.items},
            }
        obs["shot"] = str(driver.snap(shot))
        return obs
    return play


def _record(obs: dict, pid: str, kind: str, iid: str = "") -> bytes:
    rec = obs["records"][pid]
    return bytes.fromhex(rec["items"][iid] if kind == "item" else rec[kind])


def record_edit(pid: str, kind: str, iid: str = "") -> callable:
    """Judge an edit of one byte field (facts ``old``/``new``): the record the unit uses in RAM differs
    from the retail run's, and a differing byte went from ``old`` to ``new``."""

    def judge(mod, retail, facts):
        old, new = facts["old"] & 0xFF, facts["new"] & 0xFF
        a, b = _record(retail, pid, kind, iid), _record(mod, pid, kind, iid)
        diffs = [(i, x, y) for i, (x, y) in enumerate(zip(a, b)) if x != y]
        hit = [i for i, x, y in diffs if x == old and y == new]
        where = f"{pid} {kind}{' ' + iid if iid else ''}"
        if not diffs:
            return False, f"{where}: RAM record identical to retail (edit not loaded)"
        if hit and len(diffs) <= 2:
            return True, f"{where}: RAM +{hit[0]:#x} {old} -> {new} as edited"
        return False, f"{where}: unexpected RAM differences {[(hex(i), x, y) for i, x, y in diffs[:6]]}"
    return judge
