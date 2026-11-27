"""Checks of the plan that need no Dolphin; they write their rows to the same results table.

    python -m tools.ingame_checks.static_checks

* SC1e / SC1j (RD inventory SCRIPT-01): every script of the European and Japanese discs round-trips
  byte for byte through the binary reader, and decompiles to source that compiles back to a stable file
  (with and without an appended event).
* TX1 / TX1r (1.0 checklist §6, Export as text): the export into an empty folder writes the marker and
  its folders; a second export into the same folder replaces the first (same files, no leftovers).

Run it while no Dolphin check runs: it is CPU-heavy and would slow a driven game, and it opens the shared
work projects, which a running check's build is using.
"""
from __future__ import annotations

import json
import sys
import tempfile
from datetime import datetime
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    __package__ = "tools.ingame_checks"

from .core import BASES, ROOT, work_for  # noqa: E402
from .run import RunLock, write_table  # noqa: E402

EXTRA = '\n@on_phase(turn_from=1, turn_to=1, phase="enemy")\ndef ZZStaticCheck():\n    set("gf_complete")\n'


def script_round_trips(region: str) -> tuple[bool, str]:
    from fe_modding.formats.cmb import binary, compiler, decompiler
    problems, count = [], 0
    for path in sorted((BASES[region] / "files" / "Scripts").glob("*.cmb")):
        raw = path.read_bytes()
        try:
            script = binary.read_cmb(raw)
            if binary.write_cmb(script) != raw:
                problems.append(f"{path.name}: binary round trip differs")
            source = decompiler.decompile(script, path.name)[0]
            for extra in ("", EXTRA):
                out = binary.write_cmb(compiler.compile_source(source + extra, base=script).script)
                if binary.write_cmb(binary.read_cmb(out)) != out:
                    problems.append(f"{path.name}: compiled file not stable{' (+event)' if extra else ''}")
            count += 1
        except Exception as error:  # noqa: BLE001 - every failing script is reported
            problems.append(f"{path.name}: {type(error).__name__}: {error}")
    return not problems, (f"{count} scripts: byte-identical binary round trip, decompile/compile stable"
                          if not problems else f"{len(problems)} problem(s): {problems[:4]}")


def text_export_twice(region: str) -> tuple[bool, str]:
    from fe_modding import text_export
    project = work_for(region, {}).project
    with tempfile.TemporaryDirectory() as temp:
        dest = Path(temp) / "export"
        dest.mkdir()
        text_export.export_project(project, dest)
        first = sorted(p.relative_to(dest).as_posix() for p in dest.rglob("*") if p.is_file())
        marker = (dest / text_export.MARKER).is_file()
        folders = sorted({f.split("/")[0] for f in first if "/" in f})
        stray = f"{folders[0]}/stray_leftover.txt"         # a part's folder is replaced on each export
        (dest / stray).write_text("from an older export", encoding="utf-8")
        text_export.export_project(project, dest)
        second = sorted(p.relative_to(dest).as_posix() for p in dest.rglob("*") if p.is_file())
    ok = marker and first == second and stray not in second
    return ok, (f"{len(first)} files in {folders}; marker {'written' if marker else 'MISSING'}; second export "
                f"{'replaced the first' if first == second else 'differs'}"
                f"{', a stale file in a part folder was kept' if stray in second else ''}")


def excel_round_trip(region: str) -> tuple[bool, str]:
    """Game Data › Export Excel… then Import Excel… of the unchanged workbook gives back the same file."""
    from fe_modding import excel_io
    project = work_for(region, {}).project
    data = project.read_logical("game_data")
    with tempfile.TemporaryDirectory() as temp:
        book = Path(temp) / "game_data.xlsx"
        excel_io.export_fe8(book, data)
        out, _docs, errors = excel_io.import_fe8(book, data)
    return out == data and not errors, (f"{len(data):,} bytes: the import of the exported workbook is "
                                        f"{'identical' if out == data else 'DIFFERENT'}; {len(errors)} import errors {errors[:2]}")


def reset_everything(region: str) -> tuple[bool, str]:
    """Tools › Game Code: two rows changed, then Reset everything: main.dol is the retail file again."""
    from fe_modding.game_code import entries  # noqa: F401
    from fe_modding.game_code.catalog import CATALOG
    from fe_modding.game_code.editor import CodeEditor
    from fe_modding.game_profile import disc_root_of
    work = work_for(region, {})
    project = work.project
    dol = disc_root_of(project) / "sys" / "main.dol"
    retail = (BASES[region] / "sys" / "main.dol").read_bytes()
    try:
        editor = CodeEditor(disc_root_of(project), project.write_keeping_original, project.extracted_bytes)
        editor.set_value(CATALOG.entries["combat.crit_multiplier"], 5)
        editor.set_patch(CATALOG.entries["growth.force_random"], True)
        changed = dol.read_bytes() != retail
        reset = editor.reset_all()
        same = dol.read_bytes() == retail
    finally:
        work.revert()
    return changed and same, (f"two rows set (main.dol {'changed' if changed else 'UNCHANGED'}); Reset everything "
                              f"reset {reset} row(s); main.dol {'equals retail' if same else 'DIFFERS from retail'}")


def apply_patch_matches(region: str) -> tuple[bool, str]:
    """Disc & Patch › Apply patch… with X1's .tpatch on a copy of the files it touches: each written file is
    the edited one."""
    import shutil
    from fe_modding import patch
    run = ROOT / "run" / "X1_mod"
    tpatch, edited = run / "mod.tpatch", run / "disc_tree"
    if not tpatch.is_file():
        return False, "no X1 patch yet (run the sharing set first)"
    info = patch.read_patch(tpatch)
    with tempfile.TemporaryDirectory() as temp:
        target = Path(temp) / "disc"
        for rel in ("sys/boot.bin", *info.replace, *info.remove):
            (target / rel).parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(BASES[region] / rel, target / rel)
        patch.apply_patch(tpatch, target)
        wrong = [rel for rel in (*info.replace, *info.add)
                 if (target / rel).read_bytes() != (edited / rel).read_bytes()]
    return not wrong, (f"{len(info.replace)} replaced, {len(info.add)} added, {len(info.remove)} removed; "
                       f"{'every file equals the edited tree' if not wrong else f'differs: {wrong[:4]}'}")


def record_add_remove(region: str) -> tuple[bool, str]:
    """Game Data › New… (a copy of Ike) then Remove of the copy: FE8Data is the file it was."""
    from fe_modding.formats import fe8data
    project = work_for(region, {}).project
    data = project.read_logical("game_data")
    added, index = fe8data.add_record(data, "character", "PID_INGAME_CHECK", copy_from=0)
    copy = next(c for c in fe8data.read_fe8data(added).characters if c.index == index)
    back = fe8data.remove_record(added, "character", index)

    def rows(blob):          # the records as the game reads them (the table may have moved in the file)
        return [{k: v for k, v in vars(c).items() if k not in ("offset", "index")}
                for c in fe8data.read_fe8data(blob).characters]
    same = rows(back) == rows(data)
    ok = copy.pid == "PID_INGAME_CHECK" and same
    return ok, (f"copy {copy.pid} added as record {index}; after Remove the {len(rows(back))} character records are "
                f"{'the original ones' if same else 'DIFFERENT'} (file {len(back):,} bytes, was {len(data):,}: "
                f"the grown table stays at the end)")


def main() -> None:
    with RunLock():          # the shared work projects: never next to a running check's build
        _main()


def _main() -> None:
    results_path = ROOT / "results.json"
    results = json.loads(results_path.read_text(encoding="utf-8")) if results_path.is_file() else {}
    rows = [("SC1e", "RFEP01", "Scripts round-trip on the European disc", ["SCRIPT-01"], script_round_trips),
            ("SC1j", "RFEJ01", "Scripts round-trip on the Japanese disc", ["SCRIPT-01"], script_round_trips),
            ("TX1", "GFEE01", "Export as text twice into one folder", ["1.0 §6 Export as text (POR)"], text_export_twice),
            ("TX1r", "RFEE01", "Export as text twice into one folder", ["1.0 §6 Export as text (RD)"], text_export_twice),
            ("XL1", "GFEE01", "Excel export then import gives the same game data", ["1.0 §2 Excel (POR)"], excel_round_trip),
            ("GC1", "GFEE01", "Game Code: Reset everything restores main.dol", ["1.0 §5 Game Code Reset everything"],
             reset_everything),
            ("AP1", "GFEE01", "Apply patch writes the edited files", ["1.0 §6 Apply patch"], apply_patch_matches),
            ("RC1", "GFEE01", "Game Data New then Remove gives the same file", ["1.0 §2 New/Remove"], record_add_remove)]
    only = set(sys.argv[1:])
    rows = [r for r in rows if not only or r[0] in only]
    for cid, region, title, covers, fn in rows:
        print(f"== {cid}: {title}", flush=True)
        try:
            passed, details = fn(region)
            result = "PASS" if passed else "FAIL"
        except Exception as error:  # noqa: BLE001
            result, details = "ERROR", f"{type(error).__name__}: {error}"
        print(f"   {result}: {details}", flush=True)
        results[cid] = {"region": region, "title": title, "covers": covers, "result": result, "details": details,
                        "when": datetime.now().isoformat(timespec="minutes")}
    write_table(results)


if __name__ == "__main__":
    main()
