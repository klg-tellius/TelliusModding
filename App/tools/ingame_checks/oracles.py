"""Reusable play functions and judges."""
from __future__ import annotations

from .ram_view import GameRam

RECORD_BYTES = 0x100


def unit_summary(u) -> dict:
    return {"handle": u.handle, "pid": u.pid, "jid": u.jid, "x": u.x, "y": u.y, "hp": u.hp, "level": u.level,
            "items": [[iid, uses] for iid, uses, _ptr in u.items]}


def map_start(pids=(), shot: str = "map", minutes: float = 6.0) -> callable:
    """Play to the first player phase; observe every unit, and for each PID in ``pids`` the RAM bytes of
    its person record, class record and item records."""

    def play(driver, facts):
        driver.to_player_phase(minutes)
        game = GameRam(driver.ram, driver.build.game_id)
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


def region_diff(path_a: str, path_b: str, box=(0.0, 0.0, 1.0, 1.0), threshold: int = 40) -> float:
    """Share of pixels in ``box`` (fractions of the width and height) that differ by more than
    ``threshold`` (grey level) between two screenshots of the same size."""
    from PIL import Image, ImageChops
    a, b = Image.open(path_a).convert("L"), Image.open(path_b).convert("L")
    w, h = a.size
    crop = (int(box[0] * w), int(box[1] * h), int(box[2] * w), int(box[3] * h))
    diff = ImageChops.difference(a.crop(crop), b.crop(crop))
    values = list(diff.getdata())
    return sum(1 for v in values if v > threshold) / max(1, len(values))


def magenta_pixels(path: str) -> int:
    """Pixels of the (184, 0, 184)-ish magenta a flat-magenta texture comes out as in Dolphin."""
    from PIL import Image
    return sum(1 for r, g, b in Image.open(path).convert("RGB").getdata()
               if r > 140 and b > 140 and g < 60 and abs(r - b) < 40)


def map_shot(name: str = "map"):
    """Play to the first player phase and take a screenshot (the cursor is on the lord, whose unit and
    terrain windows are open)."""
    def play(driver, facts):
        import time
        driver.to_player_phase(8)
        time.sleep(1.5)
        return {"shot": str(driver.snap(name)), "processes": sorted(driver.state().names)}
    return play


#: Map processes that are not weather effects (Radiant Dawn); ``E_MapWeather`` is the controller that starts
#: the effect process (``E_MapCloud``, ``E_MapSnow``, ...) for the map's weather id.
NON_WEATHER = {"E_MapDisp", "E_MapShader", "E_MapWeather"}


def weather_effects(names) -> set:
    """The weather effect processes among ``names`` (W4r/W4b, 2026-11-25: snow runs E_MapSnow, cloudy E_MapCloud)."""
    return {n for n in names or () if n.startswith("E_Map") and n not in NON_WEATHER}


def tone_profile(dump, hz: int = 440) -> dict:
    """The strongest share of ``hz`` in any one-second window of Dolphin's audio dump (read once Dolphin has
    closed it; the header is never finalised, so the samples are everything after ``data``)."""
    import struct

    import numpy as np
    if dump is None or not dump.is_file():
        return {"tone_max": 0.0, "seconds": 0.0}
    raw = dump.read_bytes()
    rate = struct.unpack_from("<I", raw, 24)[0] if raw[:4] == b"RIFF" else 32000
    at = raw.find(b"data") + 8
    pcm = np.frombuffer(raw[at:at + (len(raw) - at) // 4 * 4], dtype="<i2").astype(float)
    mono = (pcm[0::2] + pcm[1::2]) / 2
    best, window = 0.0, rate
    freqs = np.fft.rfftfreq(window, 1 / rate)
    band = (freqs > 80) & (freqs < 4000)
    near = (freqs > hz - 4) & (freqs < hz + 4)
    hann = np.hanning(window)
    for start in range(0, max(0, len(mono) - window), window // 2):
        spectrum = np.abs(np.fft.rfft(mono[start:start + window] * hann)) ** 2
        total = spectrum[band].sum()
        if total > 1e6:          # skip silence
            best = max(best, float(spectrum[near].sum() / total))
    return {"tone_max": best, "seconds": len(mono) / rate}
