"""Write ``saves/INDEX.md``: which chapter each save of a chapter sweep starts.

    python -m tools.chapter_sweep.index --run G:/ROM/tellius_test/sweep_run_rd --out G:/ROM/tellius_test/sweep_out_rd

The work project the build used (``sweep.json``) gives the chapter titles. A save is named
``NNN_chapterCC_<file>``: CC is the game's current chapter number when the save was written,
which is the chapter the save continues into (PoR: the ``ChapterData`` id; Radiant Dawn: the
internal number, mapped to its page id).
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    __package__ = "tools.chapter_sweep"

from fe_modding import chapters  # noqa: E402
from fe_modding.project import ModProject  # noqa: E402


def chapter_labels(project, rd: bool) -> dict[int, str]:
    titles = chapters.chapter_titles(project)
    if not rd:
        return {int(cid): f"C{cid} {title}" for cid, title in titles.items() if cid.isdigit()}
    from fe_modding.game_code.rd_story import chapter_number_map
    numbers = chapter_number_map(project.read_logical("game_data"))
    return {number: f"{cid} {titles.get(cid.removeprefix('C'), '')}".strip() for number, cid in numbers.items()}


def write_index(run: Path, out: Path) -> Path:
    manifest = json.loads((run / "sweep.json").read_text(encoding="utf-8"))
    project = ModProject.load(Path(manifest["work"]))
    labels = chapter_labels(project, manifest["region"].startswith("R"))
    rows = ["| Save | Chapter number | Starts |", "|---|---|---|"]
    for path in sorted((out / "saves").iterdir()):
        match = re.match(r"\d+_chapter(\d+)_", path.name)
        if not match:
            continue
        number = int(match.group(1))
        start = "New file (no chapter yet)" if number == 0 else labels.get(number, "after the Endgame (no chapter record)")
        rows.append(f"| `{path.name}` | {number} | {start} |")
    text = (f"# Chapter sweep saves ({manifest['region']})\n\n"
            f"Every story chapter was won when the player ended turn 1 (trigger `{manifest.get('trigger', 'on_phase')}`). "
            "Each file is the game's own save at the moment it was written; the chapter is the one it "
            "continues into.\n\n" + "\n".join(rows) + "\n")
    target = out / "saves" / "INDEX.md"
    target.write_text(text, encoding="utf-8", newline="\n")
    return target


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--run", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    print(write_index(args.run, args.out))


if __name__ == "__main__":
    main()
