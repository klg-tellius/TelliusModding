"""Build the chapter-sweep run tree: every story chapter won when the player ends turn 1.

    python -m tools.chapter_sweep.build --game por --base G:/ROM/por_work/GFEE01
        --work G:/ROM/tellius_test/session_work --run G:/ROM/tellius_test/sweep_run_por
    python -m tools.chapter_sweep.build --game rd --base G:/ROM/rd_work/RFEE01
        --work G:/ROM/tellius_test/rdcheck_work_RFEE01 --run G:/ROM/tellius_test/sweep_run_rd

Run from ``App``. ``--base`` (a clean extracted US disc) is only read. ``--work`` is a throw-away
project holding a full copy of it (made once, shared with ``tools/session_playtest``); it is put
back after the build. ``--run`` gets the bootable tree (sys copied, files hard-linked to
``--base``, so keep both on one drive) and ``patch/`` with the changed files.
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    __package__ = "tools.chapter_sweep"

from fe_modding import script_sources  # noqa: E402
from fe_modding.games import Game  # noqa: E402
from tools.prepare_extended_flag_playtest import victory_source  # noqa: E402
from tools.session_playtest.harness import WorkProject, assemble_run_tree, sha256  # noqa: E402

GAMES = {"por": ("GFEE01", Game.PATH_OF_RADIANCE, "anim.speed"),
         "rd": ("RFEE01", Game.RADIANT_DAWN, "rd.anim.speed")}

#: Story chapter scripts: PoR C01 (Prologue) .. C31; RD C0101 .. C0407e. Not the trial maps
#: (PoR C80-C96, RD T01-T04), C00/C0000 (no map) or CFINAL (the epilogue, no battle).
STORY = {"por": re.compile(r"^C(0[1-9]|[1-7]\d)$"), "rd": re.compile(r"^C0[1-4]\d\d[a-e]?$")}


def story_chapters(project, game: str) -> list[str]:
    folder = script_sources.scripts_dir(project)
    return sorted(p.stem[1:] for p in folder.glob("C*.cmb") if STORY[game].match(p.stem))


#: ``before_phase`` (trigger type 3) runs when the player phase ends, before the enemy phase starts, so
#: no enemy acts; ``on_phase`` (type 6) runs once the enemy phase has started, and the game only
#: polls the victory flag after the enemies have moved (seen on Radiant Dawn 1-1).
TRIGGERS = ("before_phase", "on_phase")


def auto_win_source(source: str, chapter: str, trigger: str = "before_phase") -> str:
    key = int(chapter) if chapter.isdigit() and len(chapter) == 2 else chapter
    block = victory_source(source, key)
    block = block.replace("# XFT automatic test victory", "# Chapter sweep: automatic victory")
    block = block.replace("def XftFinishAfterPlayerTurnOne", "def SweepWinAfterPlayerTurnOne")
    return block.replace("@on_phase(turn_from=1", f"@{trigger}(turn_from=1")


def add_auto_win(project, chapter: str, trigger: str = "before_phase") -> None:
    script = script_sources.load(project, script_sources.chapter_script(project, chapter))
    script_sources.save(project, script, script.source + auto_win_source(script.source, chapter, trigger))


def build(game: str, base: Path, work_dir: Path, run: Path, anim_speed: float,
          trigger: str = "before_phase") -> dict:
    region, game_enum, speed_id = GAMES[game]
    work = WorkProject(base, work_dir, region, game_enum)
    try:
        project = work.project
        chapters = story_chapters(project, game)
        for chapter in chapters:
            add_auto_win(project, chapter, trigger)
        if anim_speed and anim_speed != 1.0:
            from fe_modding.game_code import entries  # noqa: F401  (registers the PoR catalogue)
            if game == "rd":
                from fe_modding.game_code import entries_fe10  # noqa: F401
            from fe_modding.game_code.catalog import CATALOG
            from fe_modding.game_code.editor import CodeEditor
            from fe_modding.game_profile import disc_root_of
            editor = CodeEditor(disc_root_of(project), project.write_keeping_original, project.extracted_bytes)
            editor.set_value(CATALOG.entries[speed_id], anim_speed)
        patch = run / "patch"
        if patch.exists():
            shutil.rmtree(patch)
        changed = work.changed()
        for rel in changed:
            target = patch / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(work.extracted / rel, target)
    finally:
        work.revert()
    assemble_run_tree(base, patch, run)
    manifest = {"game": game, "region": region, "base": str(base), "work": str(work_dir), "chapters": chapters,
                "anim_speed": anim_speed, "trigger": trigger, "files": {rel: sha256(patch / rel) for rel in changed}}
    (run / "sweep.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8", newline="\n")
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--game", choices=sorted(GAMES), required=True)
    parser.add_argument("--base", type=Path, required=True, help="clean extracted US disc (sys/ and files/)")
    parser.add_argument("--work", type=Path, required=True, help="throw-away work project (copy made once)")
    parser.add_argument("--run", type=Path, required=True, help="run tree to (re)build")
    parser.add_argument("--anim-speed", type=float, default=2.0, help="Game Code animation speed (1 = off)")
    parser.add_argument("--trigger", choices=TRIGGERS, default="before_phase",
                        help="when the victory is set: as turn 1's player phase ends (default) or once the "
                             "enemy phase has started (the enemies then move first)")
    args = parser.parse_args()
    manifest = build(args.game, args.base, args.work, args.run, args.anim_speed, args.trigger)
    print(f"{len(manifest['chapters'])} chapters won on turn 1: {' '.join(manifest['chapters'])}")
    print(f"{len(manifest['files'])} changed files; run tree {args.run}")


if __name__ == "__main__":
    main()
