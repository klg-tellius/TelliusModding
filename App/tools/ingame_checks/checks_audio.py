"""Music edits heard in the game (1.0 checklist section 4: Music › New track, RD Sound Tables; section 3: a
script's BGMPlay).

The edited run makes a 440 Hz test tone into a new track the way Music › New track does (PoR: an ``.stm`` and
its ``BGM_`` cue in gcfesnd.bin; RD: a ``.brstm`` on the selected track's settings, its BRSAR sound and cue,
``rd_music.add_track``) and points the chapter's music at it: PoR ChapterData's map music, RD Sound Tables'
player-phase music (``SND_MAP_BGM_DATA``), or a ``BGMPlay`` in the opening event. Dolphin dumps the audio;
the judge finds the strongest frequency of what played: 440 Hz in the edited run, something else in retail.
"""
from __future__ import annotations

import math

from .checks_chapters import play_first_talk
from .core import Check, Jump

TONE_HZ = 440
TRACK = "ingame_tone"
CUE = "BGM_INGAME_TONE"


def tone(rate: int = 32000, seconds: float = 20.0, channels: int = 2):
    from fe_modding.formats import stm
    samples = [int(12000 * math.sin(2 * math.pi * TONE_HZ * i / rate)) for i in range(int(rate * seconds))]
    return stm.StmAudio(rate, [samples] * channels, loop_start=0)


def add_por_track(ctx) -> str:
    from fe_modding.formats import gcfesnd, stm
    from fe_modding.game_profile import files_root_of
    sound = files_root_of(ctx.project) / "Sound"
    ctx.project.write_keeping_original(sound / f"{TRACK}_32k.stm", stm.write_stm(tone()))
    catalog = sound / "gcfesnd.bin"
    ctx.project.write_keeping_original(catalog, gcfesnd.add_bgm_cue(catalog.read_bytes(), CUE, f"sound/{TRACK}_32k"))
    return CUE


def add_rd_track(ctx) -> str:
    from fe_modding import rd_music
    from fe_modding.formats import brstm
    from fe_modding.game_profile import files_root_of
    strm = files_root_of(ctx.project) / "Sound" / "strm"
    template = sorted(strm.glob("*.brstm"))[0]
    audio = tone()
    cue, _sound = rd_music.add_track(ctx.project, TRACK, brstm.write_brstm(audio, template.read_bytes()), template,
                                     len(audio.channels))
    return cue


def fixture_por_map_music(ctx):
    from fe_modding.formats import fe8data
    cue = add_por_track(ctx)
    record = ctx.chapter_record(2)
    ctx.fe8 = fe8data.patch_chapter_field(ctx.fe8, record.index, "bgm", cue)
    ctx.facts.update(cue=cue)


def fixture_rd_phase_music(ctx):
    from fe_modding.formats import fe10_sound_tables as tables, lz10
    cue = add_rd_track(ctx)
    path = ctx.project.profile.path(ctx.project.extracted_dir / "files", "sound_data")
    raw = path.read_bytes()
    compressed = raw[:1] == b"\x10"
    data = lz10.decompress(raw) if compressed else raw
    index = next(i for i, row in enumerate(tables.read_rows(data, "SND_MAP_BGM_DATA")) if row["chapter"] == "C0101")
    data = tables.set_row(data, "SND_MAP_BGM_DATA", index, phase_player=cue)
    ctx.project.write_keeping_original(path, lz10.compress(data) if compressed else data)
    ctx.facts.update(cue=cue)


def fixture_por_bgmplay(ctx):
    """The first BGMPlay("…") of chapter 1's script plays the tone instead."""
    import re
    cue = add_por_track(ctx)
    source = ctx.script_source(2)
    match = re.search(r'BGMPlay\("([^"]+)"', source)
    if match is None:
        raise RuntimeError("chapter 1's script has no BGMPlay with a cue name")
    ctx.replace_script(2, match.group(0), f'BGMPlay("{cue}"')
    ctx.facts.update(cue=cue, replaced=match.group(1))


def strongest(rate: int, samples: list[int]) -> tuple[float, float]:
    """(frequency of the strongest bin between 80 Hz and 4 kHz, its share of the energy there)."""
    import numpy as np
    if rate <= 0 or len(samples) < rate:
        return 0.0, 0.0
    x = np.asarray(samples[-rate * 4:], dtype=float)
    spectrum = np.abs(np.fft.rfft(x * np.hanning(len(x)))) ** 2
    freqs = np.fft.rfftfreq(len(x), 1 / rate)
    band = (freqs > 80) & (freqs < 4000)
    if not spectrum[band].sum():
        return 0.0, 0.0
    peak = int(np.argmax(np.where(band, spectrum, 0)))
    near = (freqs > freqs[peak] - 5) & (freqs < freqs[peak] + 5)
    return float(freqs[peak]), float(spectrum[near].sum() / spectrum[band].sum())


def listen_on_map(driver, facts):
    import time
    driver.to_player_phase(8)
    mark = driver.audio_mark()
    time.sleep(6)
    rate, samples = driver.audio_since(mark)
    hz, share = strongest(rate, samples)
    return {"hz": hz, "share": share, "rate": rate, "seconds": len(samples) / rate if rate else 0,
            "shot": str(driver.snap("map"))}


def listen_in_opening(driver, facts):
    obs = play_first_talk(driver, facts)
    mark = driver.audio_mark()
    import time
    time.sleep(6)
    rate, samples = driver.audio_since(mark)
    hz, share = strongest(rate, samples)
    obs.update(hz=hz, share=share, rate=rate, seconds=len(samples) / rate if rate else 0)
    return obs


def judge_tone(mod, retail, facts):
    if not mod.get("seconds"):
        return False, "no audio in the dump (is DSP dumping silent at volume 0?)"
    heard = abs(mod["hz"] - TONE_HZ) < 6 and mod["share"] > 0.3
    retail_tone = abs(retail["hz"] - TONE_HZ) < 6 and retail["share"] > 0.3
    return heard and not retail_tone, f"{facts['cue']}: edited run's strongest frequency {mod['hz']:.0f} Hz " \
                                      f"({mod['share']:.0%} of the energy), retail {retail['hz']:.0f} Hz " \
                                      f"({retail['share']:.0%}), {mod['seconds']:.1f} s heard"


CHECKS = [
    Check("M1", "por", "Music › New track as a chapter's map music", ["1.0 §4 Music New track (POR)",
          "1.0 §3 Chapter data map music (POR)"], play=listen_on_map, judge=judge_tone,
          fixture=fixture_por_map_music, start=Jump(2), audio=True),
    Check("M1r", "rd", "Music › New track as the chapter's player-phase music (Sound Tables)",
          ["1.0 §4 RD Sound Tables ⭐ chapter music", "1.0 §4 Music New track (RD)"], play=listen_on_map,
          judge=judge_tone, fixture=fixture_rd_phase_music, start=Jump("0101"), audio=True),
    Check("M2", "por", "A script's BGMPlay plays the named cue", ["1.0 §3 Script ⭐ BGMPlay (POR)"],
          play=listen_in_opening, judge=judge_tone, fixture=fixture_por_bgmplay, start=Jump(2), audio=True),
]
