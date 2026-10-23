"""Check a built package without Dolphin: assemble every run tree the runner would boot and
verify it (patched files byte-exact, the right main.dol state, hard links to the clean disc,
test cards that parse and carry valid checksums).

    python -m tools.session_playtest.dry_run --package ..\\workspace\\session-playtest [--keep]
"""
from __future__ import annotations

import argparse
import os
import shutil
import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    __package__ = "tools.session_playtest"

from .harness import assemble_run_tree, load_manifest, sha256  # noqa: E402


def check_test(test: dict, manifest: dict, package: Path, keep: bool) -> list[str]:
    from fe_modding.formats import save_file as sf
    from fe_modding.game_code import entries  # noqa: F401
    from fe_modding.game_code.catalog import CATALOG, Session, State
    from fe_modding.game_code.dol import Dol
    from fe_modding.game_code.versions import identify, read_boot_code

    problems = []
    if test["boot"] in ("none", "image"):
        if test["boot"] == "image" and not Path(test["image"]).is_file():
            problems.append(f"image missing: {test['image']}")
        return problems
    base = Path(manifest["bases"][test["region"]])
    run = Path(manifest["run_root"]) / f"_dry_{test['id']}"
    try:
        main_dol = assemble_run_tree(base, package / "patches" / test["id"], run)
        for rel, digest in test.get("files", {}).items():
            if sha256(run / rel) != digest:
                problems.append(f"{rel}: bytes differ from the built patch")
        sample = next(p for p in (base / "files").rglob("*") if p.is_file() and
                      (Path("files") / p.relative_to(base / "files")).as_posix() not in test.get("files", {}))
        linked = run / "files" / sample.relative_to(base / "files")
        if os.stat(linked).st_nlink < 2:
            problems.append("run tree files are copies, not hard links (different drive?)")
        dol = Dol.open(main_dol)
        version = identify(dol, read_boot_code(run)).version
        if version is None or version.code != test["region"]:
            problems.append("main.dol is not recognised as the expected build")
        else:
            jump = Session(dol, version).patch_status(CATALOG.entries["dev.jump_chapter"]).state
            if (jump == State.APPLIED) != (test["boot"] == "chapter"):
                problems.append(f"jump patch state {jump} does not match boot={test['boot']}")
        cards = sorted((package / "cards" / test["id"]).glob("*.gci"))
        for card in cards:
            save = sf.SaveFile.from_bytes(card.read_bytes())
            live = [b for b in save.blocks if b is not None and b.decoded and not b.is_checkpoint
                    and b.header.save_kind == 2]
            if not live or not all(b.crc_ok for b in live):
                problems.append(f"{card.name}: no valid file save or a bad checksum")
            for block in live:
                problems += [f"{card.name} block {block.location}: {p}" for p in sf.validate(block)][:3]
    finally:
        if not keep and run.exists():
            shutil.rmtree(run)
    return problems


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--package", type=Path, required=True)
    parser.add_argument("--keep", action="store_true", help="leave the _dry_<id> run trees in place")
    args = parser.parse_args()
    package = args.package.resolve()
    manifest = load_manifest(package)
    bad = 0
    for test_id in manifest["order"]:
        test = manifest["tests"].get(test_id)
        if test is None:
            print(f"{test_id:5} NOT BUILT")
            bad += 1
            continue
        problems = check_test(test, manifest, package, args.keep)
        size = test.get("patch_bytes", 0) / 1e6
        print(f"{test_id:5} {'ok ' if not problems else 'BAD'} {len(test.get('files', {})):3} files {size:5.1f} MB  "
              f"{test['title']}")
        for problem in problems:
            print(f"        {problem}")
        bad += bool(problems)
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
