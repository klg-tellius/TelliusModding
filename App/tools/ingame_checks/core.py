"""What a check is, and how its two run trees (retail and modded) are built.

A check runs twice from the same start with the same inputs: once with only the shared ``setup`` (the
retail run) and once with ``setup`` plus ``fixture`` (the edit under test). ``judge`` compares what
``play`` observed in each run. Both variants go through the same build steps, so a difference between
them comes from the fixture alone.
"""
from __future__ import annotations

import json
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

from tools.session_playtest.context import Context
from tools.session_playtest.harness import WorkProject, assemble_run_tree, sha256, write_lf

from fe_modding.games import Game

#: Clean extracted discs (read only) and the default folders on the same drive (run trees hard-link).
BASES = {"GFEE01": Path("G:/ROM/por_work/GFEE01"), "RFEE01": Path("G:/ROM/rd_work/RFEE01"),
         "RFEP01": Path("G:/ROM/rd_work/RFEP01"), "RFEJ01": Path("G:/ROM/rd_work/RFEJ01"),
         "GFEP01": Path("G:/ROM/por_work/GFEP01"), "GFEJ01": Path("G:/ROM/por_work/GFEJ01")}
ROOT = Path("G:/ROM/tellius_test/ingame")
SAVES = Path("G:/ROM/SaveFile")
SWEEP_SAVES = {"por": Path("G:/ROM/tellius_test/sweep_out_por2/saves"),
               "rd": Path("G:/ROM/tellius_test/sweep_out_rd/saves")}
VARIANTS = ("retail", "mod")


@dataclass
class Jump:
    """Boot straight into a chapter (PoR ChapterData id, RD page id such as ``"0101"``)."""
    chapter: object
    difficulty: str = "Hard"


@dataclass
class Title:
    """Normal boot to the title; ``card`` seeds the save the game loads."""


@dataclass
class Check:
    id: str
    game: str                                   # "por" or "rd"
    title: str
    covers: list[str]                           # checklist lines / inventory rows this settles
    play: Callable                              # play(driver, ctx) -> dict of observations
    judge: Callable                             # judge(mod, retail, ctx) -> (passed, text)
    fixture: Optional[Callable] = None          # fixture(ctx): the edit under test (mod run only)
    setup: Optional[Callable] = None            # setup(ctx): shared by both runs (auto-win, speed...)
    start: object = field(default_factory=Title)
    card: Optional[Callable] = None             # card(ctx, variant) -> {file name: bytes}
    region: str = ""
    minutes: float = 6.0
    retail: bool = True                         # False: judge(mod, None, ctx) only
    audio: bool = False                         # dump the game's audio (Driver.audio_mark / audio_since)
    package: Optional[Callable] = None          # package(run_dir, variant) -> disc image Dolphin boots instead
    speed: float = 1.0                          # Dolphin's emulation speed (0.25: four times slower)
    probe: bool = False                         # a run that finds a value or a path: recorded as INFO, never FAIL

    def __post_init__(self):
        if not self.region:
            self.region = "GFEE01" if self.game == "por" else "RFEE01"

    @property
    def wii(self) -> bool:
        return self.region.startswith("R")


class Ctx(Context):
    """The session-playtest context (PoR FE8Data helpers) plus what a check needs on either game."""

    def __init__(self, project, region: str, variant: str):
        super().__init__(project, SAVES)
        self.region, self.variant = region, variant

    @property
    def wii(self) -> bool:
        return self.region.startswith("R")

    @property
    def mod(self) -> bool:
        return self.variant == "mod"

    def code_entry(self, entry_id: str):
        from fe_modding.game_code import entries  # noqa: F401
        if self.region.startswith("R"):
            from fe_modding.game_code import entries_fe10  # noqa: F401
        from fe_modding.game_code.catalog import CATALOG
        return CATALOG.entries[entry_id]

    def set_code(self, entry_id: str, value=True) -> None:
        entry = self.code_entry(entry_id)
        if isinstance(value, bool):
            self.code.set_patch(entry, value)
        else:
            self.code.set_value(entry, value)

    def append_chapter_script(self, chapter, source: str) -> None:
        from fe_modding import script_sources
        key = chapter if isinstance(chapter, str) else f"{chapter:02d}"
        script = script_sources.load(self.project, script_sources.chapter_script(self.project, key))
        script_sources.save(self.project, script, script.source + source)


def work_for(region: str, cache: dict) -> WorkProject:
    if region not in cache:
        game = Game.RADIANT_DAWN if region.startswith("R") else Game.PATH_OF_RADIANCE
        cache[region] = WorkProject(BASES[region], ROOT / f"work_{region}", region, game)
    return cache[region]


def install_jump(ctx: Ctx, jump: Jump) -> None:
    from tools.session_playtest.build import install_jump as _install
    ctx.drop_editor()
    _install(ctx, jump.chapter, jump.difficulty)


def build_variant(check: Check, variant: str, works: dict) -> dict:
    """Build ``ROOT/run/<id>_<variant>``; returns the variant's manifest."""
    from fe_modding import chapters

    work = work_for(check.region, works)
    work.revert()
    ctx = Ctx(work.project, check.region, variant)
    if check.setup is not None:
        check.setup(ctx)
    if variant == "mod" and check.fixture is not None:
        check.fixture(ctx)
    if not check.wii:
        chapters.ensure_name_images(ctx.project)   # what the app's Build does
        ctx.project.sync_system_archive()
    if isinstance(check.start, Jump):
        install_jump(ctx, check.start)
    run = ROOT / "run" / f"{check.id}_{variant}"
    patch = run / "patch"
    if patch.exists():
        shutil.rmtree(patch)
    changed = work.changed()
    for rel in changed:
        target = patch / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(work.extracted / rel, target)
    cards = {}
    if check.card is not None:
        cards = check.card(ctx, variant)
    card_dir = run / "card"
    if card_dir.exists():
        shutil.rmtree(card_dir)
    card_dir.mkdir(parents=True)
    for name, data in cards.items():
        (card_dir / name).write_bytes(data)
    work.revert()
    assemble_run_tree(BASES[check.region], patch, run)
    for name in ("image.iso", "boot.json"):
        if (run / name).exists():
            (run / name).unlink()
    if check.package is not None:
        check.package(run, variant)
    manifest = {"id": check.id, "variant": variant, "region": check.region,
                "files": {rel: sha256(patch / rel) for rel in changed}, "cards": sorted(cards),
                "facts": {k: v for k, v in ctx.facts.items() if isinstance(v, (int, str, float, list, dict, bool))}}
    write_lf(run / "check.json", json.dumps(manifest, indent=2) + "\n")
    return manifest
