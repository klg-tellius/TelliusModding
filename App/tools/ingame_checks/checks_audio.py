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
    info = brstm.read_info(template.read_bytes())
    audio = tone(info.sample_rate, channels=info.channel_count)
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
    from fe_modding import script_sources
    new, count = re.subn(r'(BGM(?:Play|FadeIn)[(][0-9]+, )"[^"]+"', lambda m: m.group(1) + f'"{cue}"', source)
    if not count:
        raise RuntimeError("chapter 1's script has no BGMPlay/BGMFadeIn with a cue")
    script = script_sources.load(ctx.project, script_sources.chapter_script(ctx.project, "02"))
    script_sources.save(ctx.project, script, new)
    ctx.facts.update(cue=cue, replaced=count)


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
    """Play to the map and listen there for a while (the runner reads the dump once Dolphin closes)."""
    import time
    driver.to_player_phase(8)
    time.sleep(8)
    return {"shot": str(driver.snap("map"))}


def listen_in_opening(driver, facts):
    import time
    obs = play_first_talk(driver, facts)
    time.sleep(8)
    return obs


def judge_tone(mod, retail, facts):
    """The tone's strongest one-second share in the whole dump: high in the edited run, low in retail."""
    if not mod.get("seconds"):
        return False, "no audio in the dump"
    ok = mod["tone_max"] > 0.3 and mod["tone_max"] > 3 * retail["tone_max"]
    return ok, (f"{facts['cue']}: 440 Hz reaches {mod['tone_max']:.0%} of a one-second window's energy in the "
                f"edited run, {retail['tone_max']:.0%} in retail ({mod['seconds']:.0f} s of audio)")


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


# -- Sound Effects › Replace audio (RD): every SFX_SYS_* menu sound's wave replaced with a 1 s 440 Hz tone, the
# same rwsd/brsar calls as the page. On the map the driver opens and closes the unit menus (A, A, A, B, B, B); the
# 440 Hz share of what plays must jump against retail.

def fixture_rd_menu_sfx(ctx):
    from fe_modding.formats import brsar, fe10_sound, lz10, rwsd
    profile = ctx.project.profile
    files = ctx.project.extracted_dir / "files"
    data_path, archive_path = profile.path(files, "sound_data"), profile.path(files, "sound_archive")
    raw = data_path.read_bytes()
    cues = fe10_sound.read_sound_data(lz10.decompress(raw) if raw[:1] == b"\x10" else raw)
    wanted = [c for c in cues if c.name.startswith("SFX_SYS_")]
    done, seen = 0, set()
    archive_bytes = archive_path.read_bytes()
    for cue in wanted:
        archive = brsar.read_brsar(archive_bytes)
        sound = next((s for s in archive.sounds if s.name == cue.resource), None)
        if sound is None or sound.sound_type != 3:
            continue
        source = archive.files[sound.file_index]
        document = rwsd.read_rwsd(source.header, source.wave_data)
        wave_index = document.entries[sound.info_index].wave_index
        if (sound.file_index, wave_index) in seen:
            continue
        seen.add((sound.file_index, wave_index))
        target = document.waves[wave_index]
        rate = target.sample_rate
        mono = tuple(int(12000 * math.sin(2 * math.pi * TONE_HZ * i / rate)) for i in range(rate))
        header, wave = rwsd.replace_wave(document, wave_index,
                                         rwsd.RwsdAudio(rate, (mono,) * len(target.channels), None))
        archive_bytes = brsar.replace_embedded_file(archive, sound.file_index, header, wave)
        done += 1
    ctx.project.write_keeping_original(archive_path, archive_bytes)
    ctx.facts.update(cue="SFX_SYS_* menu sounds", waves=done)


def tone_share(rate: int, samples: list[int]) -> float:
    """Share of the 80 Hz - 4 kHz energy within 4 Hz of the tone."""
    import numpy as np
    if rate <= 0 or len(samples) < rate // 2:
        return 0.0
    x = np.asarray(samples, dtype=float)
    spectrum = np.abs(np.fft.rfft(x * np.hanning(len(x)))) ** 2
    freqs = np.fft.rfftfreq(len(x), 1 / rate)
    band = (freqs > 80) & (freqs < 4000)
    near = (freqs > TONE_HZ - 4) & (freqs < TONE_HZ + 4)
    total = spectrum[band].sum()
    return float(spectrum[near].sum() / total) if total else 0.0


def listen_to_menus(driver, facts):
    driver.to_player_phase(8)
    for button in ("A", "A", "A", "B", "B", "B"):
        driver.press(button, gap=1.0)
    return {"shot": str(driver.snap("menus"))}


def judge_sfx(mod, retail, facts):
    if not mod.get("seconds"):
        return False, "no audio in the dump"
    ok = mod["tone_max"] > 0.15 and mod["tone_max"] > 3 * retail["tone_max"]
    return ok, (f"{facts['waves']} menu sound waves replaced: 440 Hz reaches {mod['tone_max']:.0%} of a one-second "
                f"window while the menus open and close, retail {retail['tone_max']:.0%}")


CHECKS.append(Check("SX1r", "rd", "Sound Effects › Replace audio: the menu sounds play the new wave",
                    ["1.0 §4 Sound Effects (RD)"], play=listen_to_menus, judge=judge_sfx,
                    fixture=fixture_rd_menu_sfx, start=Jump("0101"), audio=True))
