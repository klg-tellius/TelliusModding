"""Build the test session package: one small patch folder per test instead of one disc image each.

    python -m tools.session_playtest.build --base G:\\ROM\\por_work\\GFEE01 --saves G:\\ROM\\SaveFile
        --work G:\\ROM\\tellius_test\\session_work --run-root G:\\ROM\\tellius_test\\session_run
        --package ..\\workspace\\session-playtest [--only A1 C3]

Run from ``App``. The clean disc in ``--base`` is only read. ``--work`` gets one full copy of it
(made once) that every fixture edits and that is put back after each one. Only the files a
fixture changed are stored, under ``<package>/patches/<id>/``; the runner rebuilds a bootable
tree from the clean disc plus that folder. ``--run-root`` must be on the same drive as
``--base`` so the run trees can use hard links.
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
import traceback
from collections import defaultdict
from datetime import datetime
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    __package__ = "tools.session_playtest"

from .harness import MANIFEST, WATCHED, WorkProject, sha256, write_cmd, write_lf  # noqa: E402
from .context import Context  # noqa: E402
from . import scenarios as session_scenarios  # noqa: E402
from fe_modding.games import Game  # noqa: E402

SCENARIOS = session_scenarios.SCENARIOS
#: Test sets: the PoR session (scenarios.py) and the PoR/RD parity checks (parity_scenarios.py).
SETS = {"session": "scenarios", "parity": "parity_scenarios"}
from . import docs  # noqa: E402

DEFAULT_DOLPHIN = Path(r"G:\Dolphin-x64\Dolphin.exe")


def _format(text: str, facts: dict) -> str:
    return text.format_map(defaultdict(lambda: "?", facts))


def install_jump(ctx: Context, chapter, difficulty: str) -> None:
    from fe_modding import emulator
    from fe_modding.game_code import chapter_jump, chapter_jump_fe10
    from fe_modding.game_code.catalog import Session
    from fe_modding.game_code.dol import Dol
    from fe_modding.game_code.versions import identify, read_boot_code

    from fe_modding.game_profile import disc_root_of

    extracted = disc_root_of(ctx.project)
    path = extracted / "sys" / "main.dol"
    dol = Dol.open(path)
    version = identify(dol, read_boot_code(extracted)).version
    if version is None:
        raise RuntimeError("main.dol is not a supported build after the fixture")
    if version.code.startswith("R"):   # Radiant Dawn: the chapter's internal number, from its page id
        number = emulator.rd_chapter_number(ctx.project.read_logical("game_data"), chapter)
        chapter_jump_fe10.install(Session(dol, version), number, chapter_jump_fe10.DIFFICULTIES[difficulty])
    else:
        position = emulator.chapter_position(ctx.project.read_logical("game_data"), chapter)
        chapter_jump.install(Session(dol, version), position, chapter_jump.DIFFICULTIES[difficulty])
    path.write_bytes(bytes(dol.data))


def build_one(scenario, work: WorkProject, saves: Path, package: Path) -> dict:
    from fe_modding import chapters

    work.revert()
    ctx = Context(work.project, saves)
    entry = scenario.to_json()
    patch = package / "patches" / scenario.id
    cards = package / "cards" / scenario.id
    for folder in (patch, cards):
        if folder.exists():
            shutil.rmtree(folder)
    if scenario.boot != "none":
        if scenario.build is not None:
            scenario.build(ctx)
        for chapter, turn in scenario.auto_win.items():
            ctx.auto_win(chapter, turn)
        por = not scenario.region.startswith("R")
        if scenario.anim_speed and por:
            ctx.tunes({"anim.speed": scenario.anim_speed})
        if scenario.build is not None and por:   # what the app's Build does (it also draws missing name pictures)
            chapters.ensure_name_images(ctx.project)
        if por:
            ctx.project.sync_system_archive()
        if scenario.boot == "chapter":
            install_jump(ctx, scenario.chapter, scenario.difficulty)
        changed = work.changed()
        for rel in changed:
            target = patch / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(work.extracted / rel, target)
        entry["files"] = {rel: sha256(patch / rel) for rel in changed}
        entry["patch_bytes"] = sum((patch / rel).stat().st_size for rel in changed)
    if scenario.card is not None:
        cards.mkdir(parents=True)
        for name, data in scenario.card(ctx).items():
            (cards / name).write_bytes(data)
        entry["cards"] = sorted(p.name for p in cards.iterdir())
    for key in ("steps", "checks", "notes", "app_steps"):
        entry[key] = [_format(text, ctx.facts) for text in getattr(scenario, key)]
    entry["facts"] = {k: str(v) for k, v in ctx.facts.items()}
    entry["has_after"] = scenario.after is not None
    return entry


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--base", type=Path, required=True, help="clean extracted US disc (sys/ and files/)")
    parser.add_argument("--base-pal", type=Path, default=Path(r"G:\ROM\por_work\GFEP01"),
                        help="clean extracted European disc, for the optional PAL tests")
    parser.add_argument("--saves", type=Path, required=True, help="folder with the .gci saves the fixtures start from")
    parser.add_argument("--work", type=Path, required=True, help="throw-away project folder (1.3 GB)")
    parser.add_argument("--run-root", type=Path, required=True, help="where the runner builds run trees (same drive as --base)")
    parser.add_argument("--package", type=Path, required=True, help="output: patches, cards, docs, launcher")
    parser.add_argument("--dolphin", type=Path, default=DEFAULT_DOLPHIN)
    parser.add_argument("--base-rd", type=Path, default=Path(r"G:\ROM\rd_work\RFEE01"),
                        help="clean extracted Radiant Dawn (USA) disc, for RFEE01 tests")
    parser.add_argument("--set", choices=sorted(SETS), default="session", help="which tests to build")
    parser.add_argument("--only", nargs="*", help="test ids to (re)build; the others keep their last build")
    args = parser.parse_args()
    global SCENARIOS
    import importlib
    chosen = importlib.import_module(f".{SETS[args.set]}", __package__)
    SCENARIOS = chosen.SCENARIOS

    package = args.package.resolve()
    from fe_modding.game_code.versions import identify, read_boot_code
    from fe_modding.game_code.dol import Dol
    bases = {"GFEE01": args.base.resolve()}
    if (args.base_pal / "sys" / "main.dol").is_file():
        bases["GFEP01"] = args.base_pal.resolve()
    if (args.base_rd / "sys" / "main.dol").is_file():
        bases["RFEE01"] = args.base_rd.resolve()
    for region, base in bases.items():
        if not (base / "sys" / "main.dol").is_file():
            parser.error(f"{base} is not an extracted disc")
        version = identify(Dol.open(base / "sys" / "main.dol"), read_boot_code(base)).version
        if version is None or version.code != region:
            parser.error(f"{base} is not a retail {region} build")
    package.mkdir(parents=True, exist_ok=True)
    works: dict[str, WorkProject] = {}

    def work_for(region: str) -> WorkProject:
        if region not in works:
            folder = args.work.resolve() if region == "GFEE01" else args.work.resolve().with_name(
                f"{args.work.name}_{region}")
            game = Game.RADIANT_DAWN if region.startswith("R") else Game.PATH_OF_RADIANCE
            works[region] = WorkProject(bases[region], folder, region, game)
        return works[region]

    manifest_path = package / MANIFEST
    manifest = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.is_file() else {"tests": {}}
    wanted = set(args.only or [s.id for s in SCENARIOS])
    failures = []
    for scenario in SCENARIOS:
        if scenario.id not in wanted:
            continue
        print(f"[{scenario.id}] {scenario.title}", flush=True)
        if scenario.region not in bases:
            print(f"      skipped: no clean {scenario.region} disc", flush=True)
            continue
        try:
            manifest["tests"][scenario.id] = build_one(scenario, work_for(scenario.region), args.saves.resolve(),
                                                       package)
            size = manifest["tests"][scenario.id].get("patch_bytes", 0)
            print(f"      {len(manifest['tests'][scenario.id].get('files', {}))} files, {size / 1e6:.1f} MB", flush=True)
        except Exception:  # noqa: BLE001 - report every broken fixture, keep building the others
            failures.append(scenario.id)
            traceback.print_exc()
    for work in works.values():
        work.revert()
    manifest.update({
        "built": datetime.now().isoformat(timespec="seconds"),
        "order": [s.id for s in SCENARIOS],
        "bases": {region: str(base) for region, base in bases.items()},
        "run_root": str(args.run_root.resolve()), "dolphin": str(args.dolphin),
        "app": str(Path(__file__).resolve().parents[2]), "saves": str(args.saves.resolve()),
        "base_hashes": {region: {rel: sha256(base / rel) for rel in WATCHED if (base / rel).is_file()}
                        for region, base in bases.items()},
    })
    manifest.pop("base", None)
    manifest["tests"] = {k: manifest["tests"][k] for k in manifest["order"] if k in manifest["tests"]}
    write_lf(manifest_path, json.dumps(manifest, indent=2, ensure_ascii=False) + "\n")
    write_cmd(package / "Start-Session.cmd",
              "@echo off\n"
              f'cd /d "{Path(__file__).resolve().parents[2]}"\n'
              f'"{sys.executable}" -m tools.session_playtest.run --package "%~dp0." --set {args.set}\n'
              "pause\n")
    docs.write_docs(package, manifest, chosen)
    print(f"Package: {package}")
    if failures:
        print(f"FAILED fixtures: {' '.join(failures)}")
        sys.exit(1)


if __name__ == "__main__":
    main()
