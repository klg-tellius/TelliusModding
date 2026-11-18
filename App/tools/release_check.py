"""Every check that needs the game data, in one command, with one pass/fail summary.

The CI has no disc, so the tests that read real game files skip there. This runs them on a
machine that has the extracted discs and saves, for both games, then measures how much of each
disc is still undecoded and checks every ``.ga`` animation, and prints one table:

    cd App
    python -m tools.release_check --rom G:\\ROM

``--rom`` is a folder laid out like this (any part that is missing is skipped and reported):

    <rom>/por_work/GFEE01, GFEP01, GFEJ01    extracted Path of Radiance discs (sys/ and files/)
    <rom>/rd_work/RFEE01, RFEP01, RFEJ01     extracted Radiant Dawn discs (sys/ and files/)
    <rom>/SaveFile/*.gci                     Path of Radiance saves
    <rom>/SaveFile/rd/                       Radiant Dawn saves (files ending in FE10_US.dat)

Each folder can also be given on its own (``--por``, ``--rd``, ``--por-saves``, ``--rd-saves``,
``--por-eu``...). The checks:

1. ``tests``: the whole unit suite with every disc variable set (``FE9_EXTRACTED``,
   ``FE10_EXTRACTED``, their ``_FILES``, the EU/JP Radiant Dawn discs, both save folders, and
   ``FE9_BLENDER`` / ``FE9_ZDBX`` when given), with pytest in parallel when it is installed.
   ``--full`` sets ``TELLIUS_CORPUS=full`` (every file instead of a sample: slower, before a
   release).
2. ``tests-eu`` / ``tests-jp`` (``--all-regions``): the suite again with both games pointed at the
   European, then the Japanese discs.
3. ``coverage <disc>``: the byte-coverage map of each disc (:mod:`fe_modding.formats.coverage`).
   It fails when a handler rejects a file, or when more than ``--max-open`` percent of the bytes
   are still undecoded, leaving out the formats set aside for 1.0 (``SET_ASIDE_FORMATS``: the Wii
   HOME Menu and client.bin). US discs by default, all six with ``--all-regions``.
4. ``ga <disc>``: every ``.ga`` animation, loose or inside a ``pack`` archive, is read and written
   back byte for byte, and a Radiant Dawn footer moved by 64 bytes and back is unchanged.

The reports (test log, JUnit XML, coverage tables, the summary) go to ``--out``
(``App/release_check_reports/<date-time>`` by default). The exit code is 0 only when every
check passed.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import datetime as _dt
import os
import re
import struct
import subprocess
import sys
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

APP = Path(__file__).resolve().parent.parent
REGIONS = {"E": "US", "P": "EU", "J": "JP"}
#: Files the coverage and .ga walks leave out: video and streamed music (public codecs, minutes
#: of reading for no field to find) and anything over 30 MB.
COVERAGE_SKIP_SUFFIXES = (".thp", ".stm")
COVERAGE_MAX_BYTES = 30_000_000
#: Coverage formats set aside for 1.0 (the Wii HOME Menu's sounds, Nintendo's shared system
#: data, and client.bin, the GBA program): reported, but left out of the pass/fail threshold.
SET_ASIDE_FORMATS = ("home menu sound", "home menu text", "client.bin")


@dataclass
class Result:
    name: str
    ok: Optional[bool]  # None: not run
    summary: str
    seconds: float = 0.0
    details: list[str] = field(default_factory=list)


# ------------------------------------------------------------------ locations

@dataclass
class Disc:
    game: str  # "por" / "rd"
    code: str  # GFEE01...
    root: Path  # the folder holding sys/ and files/

    @property
    def files(self) -> Path:
        return self.root / "files"

    @property
    def region(self) -> str:
        return REGIONS.get(self.code[3:4], self.code)

    @property
    def label(self) -> str:
        return f"{'PoR' if self.game == 'por' else 'RD'} {self.region} ({self.code})"


def disc_code(root: Path) -> str:
    try:
        return (root / "sys" / "boot.bin").read_bytes()[:6].decode("ascii", "replace")
    except OSError:
        return ""


def find_discs(args) -> tuple[dict[tuple[str, str], Disc], list[str]]:
    """The discs given, by (game, region letter), and a note for each one missing or wrong."""
    wanted = {
        ("por", "E"): args.por, ("por", "P"): args.por_eu, ("por", "J"): args.por_jp,
        ("rd", "E"): args.rd, ("rd", "P"): args.rd_eu, ("rd", "J"): args.rd_jp,
    }
    if args.rom:
        for (game, region), path in list(wanted.items()):
            if path is None:
                prefix = "G" if game == "por" else "R"
                wanted[(game, region)] = args.rom / f"{game}_work" / f"{prefix}FE{region}01"
    discs, notes = {}, []
    for (game, region), path in wanted.items():
        name = f"{'PoR' if game == 'por' else 'RD'} {REGIONS[region]}"
        if path is None:
            continue
        if not (path / "files").is_dir():
            notes.append(f"{name}: no files/ folder in {path}")
            continue
        code = disc_code(path)
        expected = ("G" if game == "por" else "R") + "FE" + region
        if not code.startswith(expected):
            notes.append(f"{name}: {path} holds disc {code or '(no sys/boot.bin)'}, expected {expected}01")
            continue
        discs[(game, region)] = Disc(game, code, path)
    return discs, notes


def save_folders(args) -> tuple[Optional[Path], Optional[Path], list[str]]:
    por, rd, notes = args.por_saves, args.rd_saves, []
    if args.rom:
        por = por or args.rom / "SaveFile"
        rd = rd or args.rom / "SaveFile" / "rd"
    if por and not any(por.glob("*.gci")):
        notes.append(f"PoR saves: no .gci file in {por}")
        por = None
    if rd and not any(rd.rglob("*FE10_US.dat")):
        notes.append(f"RD saves: no file ending in FE10_US.dat in {rd}")
        rd = None
    return por, rd, notes


# ------------------------------------------------------------------ unit and disc tests

def test_env(por: Optional[Disc], rd: Optional[Disc], extra_rd: dict[str, Disc], args,
             por_saves: Optional[Path], rd_saves: Optional[Path]) -> dict[str, str]:
    env = dict(os.environ)
    for name in ("FE9_EXTRACTED", "FE9_EXTRACTED_FILES", "FE10_EXTRACTED", "FE10_EXTRACTED_FILES",
                 "FE10_EU_EXTRACTED", "FE10_JP_EXTRACTED", "FE9_SAVES", "FE10_SAVES"):
        env.pop(name, None)  # only what this run names, not a leftover of the shell
    if por:
        env["FE9_EXTRACTED"] = str(por.root)
        env["FE9_EXTRACTED_FILES"] = str(por.files)
    if rd:
        env["FE10_EXTRACTED"] = str(rd.root)
        env["FE10_EXTRACTED_FILES"] = str(rd.files)
    for name, disc in extra_rd.items():
        env[name] = str(disc.root)
    if por_saves:
        env["FE9_SAVES"] = str(por_saves)
    if rd_saves:
        env["FE10_SAVES"] = str(rd_saves)
    if args.blender:
        env["FE9_BLENDER"] = str(args.blender)
    if args.zdbx:
        env["FE9_ZDBX"] = str(args.zdbx)
    env["TELLIUS_CORPUS"] = "full" if args.full else env.get("TELLIUS_CORPUS", "sample")
    env["PYTHONIOENCODING"] = "utf-8"
    return env


def _has_pytest() -> bool:
    try:
        import pytest  # noqa: F401
        import xdist  # noqa: F401
    except ImportError:
        return False
    return True


def run_tests(name: str, env: dict[str, str], out: Path, args) -> Result:
    start = time.time()
    log = out / f"{name}.log"
    junit = out / f"{name}.xml"
    if _has_pytest() and not args.unittest:
        command = [sys.executable, "-m", "pytest", "-n", str(args.jobs or "auto"), "-q", "-rfE",
                   f"--junitxml={junit}"]
    else:
        command = [sys.executable, "-m", "unittest", "discover", "-s", "tests"]
    if args.tests:
        command += ["-k", args.tests]
    print(f"[{name}] {' '.join(command)}", flush=True)
    with log.open("w", encoding="utf-8", errors="replace") as handle:
        process = subprocess.run(command, cwd=APP, env=env, stdout=handle, stderr=subprocess.STDOUT)
    seconds = time.time() - start
    text = log.read_text(encoding="utf-8", errors="replace")
    if junit.is_file():
        counts, failed = _junit_counts(junit)
    else:
        counts, failed = _unittest_counts(text)
    total, failures, errors, skipped = counts
    passed = total - failures - errors - skipped
    ok = process.returncode == 0 and failures == 0 and errors == 0
    if total == 0:
        ok = False
    summary = f"{passed} passed, {failures} failed, {errors} errors, {skipped} skipped"
    if total == 0:
        summary = f"no test ran (exit code {process.returncode}), see {log.name}"
    return Result(name, ok, summary, seconds, failed[:30])


def _junit_counts(path: Path) -> tuple[tuple[int, int, int, int], list[str]]:
    root = ET.parse(path).getroot()
    suites = [root] if root.tag == "testsuite" else list(root.iter("testsuite"))
    total = failures = errors = skipped = 0
    failed = []
    for suite in suites:
        total += int(suite.get("tests", 0))
        failures += int(suite.get("failures", 0))
        errors += int(suite.get("errors", 0))
        skipped += int(suite.get("skipped", 0))
        for case in suite.iter("testcase"):
            for kind in ("failure", "error"):
                node = case.find(kind)
                if node is not None:
                    message = (node.get("message") or "").splitlines()[0][:160] if node.get("message") else ""
                    failed.append(f"{case.get('classname')}.{case.get('name')}: {message}")
    return (total, failures, errors, skipped), failed


def _unittest_counts(text: str) -> tuple[tuple[int, int, int, int], list[str]]:
    ran = re.search(r"^Ran (\d+) tests?", text, re.M)
    total = int(ran.group(1)) if ran else 0

    def count(key: str) -> int:
        found = re.search(rf"{key}=(\d+)", text.rsplit("\nRan ", 1)[-1])
        return int(found.group(1)) if found else 0

    failed = re.findall(r"^(?:FAIL|ERROR): (.+)$", text, re.M)
    return (total, count("failures"), count("errors"), count("skipped")), failed


# ------------------------------------------------------------------ coverage

def _disc_paths(files: Path) -> tuple[list[Path], list[str]]:
    paths, skipped = [], []
    for directory, subdirs, names in os.walk(files):
        subdirs[:] = sorted(d for d in subdirs if not d.endswith("_extracted"))
        for name in sorted(names):
            path = Path(directory) / name
            rel = path.relative_to(files).as_posix()
            if name.endswith((".decomp", ".bak", ".decompressed")):
                continue
            if name.lower().endswith(COVERAGE_SKIP_SUFFIXES) or path.stat().st_size > COVERAGE_MAX_BYTES:
                skipped.append(rel)
                continue
            paths.append(path)
    return paths, skipped


def coverage_job(game: str, code: str, root: str, saves: Optional[str], out: str) -> dict:
    """One disc's coverage map, in a worker process."""
    sys.path.insert(0, str(APP))
    from fe_modding.formats import coverage as c

    start = time.time()
    files = Path(root) / "files"
    report = c.Report()
    walker = c.Walker(report)
    paths, skipped = _disc_paths(files)
    for path in paths:
        walker.child(path.relative_to(files).as_posix(), path.read_bytes())
    if saves:  # the coverage map reads Path of Radiance's .gci saves; Radiant Dawn's have no handler
        for path in sorted(Path(saves).glob("*.gci")):
            walker.child(path.name, path.read_bytes())
    leaf = report.totals(True)
    total = sum(leaf) or 1
    open_bytes = leaf[c.UNCLASSIFIED] + leaf[c.UNDECODED]
    aside = sum(t.counts[c.UNCLASSIFIED] + t.counts[c.UNDECODED]
                for fmt, t in report.formats.items() if fmt in SET_ASIDE_FORMATS)
    failures = [f"{fmt}: {line}" for fmt, t in sorted(report.formats.items()) for line in t.failures]
    # The biggest open fields, for the summary.
    fields = []
    for fmt, t in report.formats.items():
        for (status, name), (n, count) in t.fields.items():
            if status in (c.UNCLASSIFIED, c.UNDECODED):
                fields.append((n, f"{fmt}: {name or '(unnamed)'} ({c.STATUS_NAMES[status]}, {count} files)"))
    fields.sort(reverse=True)
    base = Path(out) / f"coverage_{code}"
    Path(f"{base}.txt").write_text(c.format_summary(report) + "\n" + c.format_fields(report), encoding="utf-8")
    Path(f"{base}.md").write_text(c.format_markdown(report) + "\n", encoding="utf-8")
    Path(f"{base}.skipped.txt").write_text("\n".join(skipped) + "\n", encoding="utf-8")
    return {
        "files": len(paths), "bytes": total, "open": open_bytes,
        "plausible": leaf[c.PLAUSIBLE], "unread": leaf[c.UNREAD],
        "aside": aside, "percent": 100 * (open_bytes - aside) / total, "failures": failures,
        "top": [f"{n:,} B  {label}" for n, label in fields[:8]],
        "seconds": time.time() - start,
    }


# ------------------------------------------------------------------ .ga round trips

def ga_job(game: str, code: str, root: str) -> dict:
    """Read and write back every .ga of a disc, in a worker process."""
    sys.path.insert(0, str(APP))
    from fe_modding.formats import animation, lz10, pak

    start = time.time()
    counts = {"ga": 0, "rd_footers": 0, "unreadable_archives": 0}
    bad: list[str] = []

    def check(name: str, data: bytes) -> None:
        if len(data) < 0x30:
            return
        counts["ga"] += 1
        try:
            anim = animation.read_animation_bytes(data)
            if animation.write_animation(anim) != data:
                bad.append(f"not byte-identical: {name}")
                return
            footer = struct.unpack_from(">I", data)[0]
            if footer and animation.is_fe10_animation(data):
                counts["rd_footers"] += 1
                begin = anim.header.footer_addr - len(anim.body_trailing)
                moved = animation.fe10_rebase_footer(data, begin, data[:begin] + bytes(64))
                if animation.fe10_rebase_footer(moved, begin + 64, moved[:begin]) != data:
                    bad.append(f"footer move changes the file: {name}")
        except Exception as error:  # every vanilla file must read
            bad.append(f"{type(error).__name__}: {name}: {error}")

    files = Path(root) / "files"
    for directory, subdirs, names in os.walk(files):
        subdirs[:] = sorted(d for d in subdirs if not d.endswith("_extracted"))
        for entry in sorted(names):
            path = Path(directory) / entry
            low = entry.lower()
            rel = path.relative_to(files).as_posix()
            if low.endswith(".ga"):
                check(rel, path.read_bytes())
            elif low.endswith((".cmp", ".pak")):
                data = path.read_bytes()
                if data[:4] != b"pack":
                    try:
                        data = lz10.decompress(data)
                    except Exception:
                        continue
                if data[:4] != b"pack":
                    continue
                try:
                    entries = pak.read_pak_entries(data)
                except Exception:
                    counts["unreadable_archives"] += 1
                    bad.append(f"unreadable pack: {rel}")
                    continue
                for member in entries:
                    if member.name.lower().endswith(".ga"):
                        check(f"{rel}#{member.name}", pak.read_pak_file_content(data, member))
    return {"counts": counts, "bad": bad, "seconds": time.time() - start}


# ------------------------------------------------------------------ main

def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0],
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--rom", type=Path, help="folder with por_work/, rd_work/ and SaveFile/ (see above)")
    for game, title in (("por", "Path of Radiance"), ("rd", "Radiant Dawn")):
        parser.add_argument(f"--{game}", type=Path, help=f"extracted US {title} disc (sys/ and files/)")
        parser.add_argument(f"--{game}-eu", type=Path, help=f"extracted European {title} disc")
        parser.add_argument(f"--{game}-jp", type=Path, help=f"extracted Japanese {title} disc")
        parser.add_argument(f"--{game}-saves", type=Path, help=f"{title} saves folder")
    parser.add_argument("--blender", type=Path, help="blender.exe, for the terrain-kit tests (FE9_BLENDER)")
    parser.add_argument("--zdbx", type=Path, help="a zdbx.cmp, for the battle-camera corpus test (FE9_ZDBX)")
    parser.add_argument("--all-regions", action="store_true",
                        help="also run the suite and the checks on the European and Japanese discs")
    parser.add_argument("--full", action="store_true",
                        help="TELLIUS_CORPUS=full: the disc tests walk every file (before a release)")
    parser.add_argument("--max-open", type=float, default=0.01,
                        help="coverage fails above this percent of undecoded bytes (default 0.01)")
    parser.add_argument("--only", choices=("tests", "coverage", "ga"), action="append",
                        help="run only these checks (repeatable); all by default")
    parser.add_argument("--tests", help="pytest -k expression: run only the matching tests")
    parser.add_argument("--unittest", action="store_true", help="use unittest even when pytest is installed")
    parser.add_argument("--jobs", type=int, help="test and check processes (default: every core)")
    parser.add_argument("--out", type=Path, help="report folder (default App/release_check_reports/<time>)")
    args = parser.parse_args(argv)
    only = set(args.only or ("tests", "coverage", "ga"))

    out = args.out or APP / "release_check_reports" / _dt.datetime.now().strftime("%Y-%m-%d_%H%M")
    out.mkdir(parents=True, exist_ok=True)
    discs, notes = find_discs(args)
    por_saves, rd_saves, save_notes = save_folders(args)
    notes += save_notes
    if not discs:
        print("No extracted disc found. Give --rom, or --por / --rd.", file=sys.stderr)
        for note in notes:
            print("  " + note, file=sys.stderr)
        return 2
    print("Discs:", ", ".join(f"{d.label} = {d.root}" for d in discs.values()))
    for note in notes:
        print("  missing: " + note)

    results: list[Result] = []
    regions = ("E", "P", "J") if args.all_regions else ("E",)
    started = time.time()

    if "tests" in only:
        extra = {f"FE10_{REGIONS[r]}_EXTRACTED": discs[("rd", r)] for r in ("P", "J") if ("rd", r) in discs}
        env = test_env(discs.get(("por", "E")), discs.get(("rd", "E")), extra, args, por_saves, rd_saves)
        results.append(run_tests("tests", env, out, args))
        for region in regions[1:]:
            por, rd = discs.get(("por", region)), discs.get(("rd", region))
            name = f"tests-{REGIONS[region].lower()}"
            if not (por or rd):
                results.append(Result(name, None, f"no {REGIONS[region]} disc"))
                continue
            results.append(run_tests(name, test_env(por, rd, {}, args, None, None), out, args))

    jobs = []
    with concurrent.futures.ProcessPoolExecutor(max_workers=args.jobs or os.cpu_count()) as pool:
        for region in regions:
            for game in ("por", "rd"):
                disc = discs.get((game, region))
                if disc is None:
                    continue
                if "coverage" in only:
                    saves = por_saves if game == "por" and region == "E" else None
                    jobs.append(("coverage", disc, pool.submit(
                        coverage_job, game, disc.code, str(disc.root), str(saves) if saves else None, str(out))))
                if "ga" in only:
                    jobs.append(("ga", disc, pool.submit(ga_job, game, disc.code, str(disc.root))))
        if jobs:
            print(f"Running {len(jobs)} disc checks in parallel...", flush=True)
        for kind, disc, future in jobs:
            name = f"{kind} {disc.label}"
            try:
                value = future.result()
            except Exception as error:
                results.append(Result(name, False, f"crashed: {type(error).__name__}: {error}"))
                continue
            if kind == "coverage":
                ok = not value["failures"] and value["percent"] <= args.max_open
                summary = (f"{value['percent']:.4f} % undecoded ({value['open'] - value['aside']:,} of "
                           f"{value['bytes']:,} B, {value['files']:,} files; {value['aside']:,} B set aside: HOME "
                           f"Menu, client.bin), {len(value['failures'])} handler failures")
                details = [f"FAILED {line}" for line in value["failures"][:20]] + value["top"]
                results.append(Result(name, ok, summary, value["seconds"], details))
            else:
                counts = value["counts"]
                ok = not value["bad"] and counts["ga"] > 0
                summary = (f"{counts['ga']:,} .ga read and written back, {counts['rd_footers']:,} RD footers "
                           f"moved, {len(value['bad'])} problems")
                results.append(Result(name, ok, summary, value["seconds"], value["bad"][:30]))

    text = format_summary(results, discs, notes, args, time.time() - started)
    print("\n" + text)
    (out / "SUMMARY.md").write_text(text + "\n", encoding="utf-8")
    print(f"\nReports: {out}")
    return 0 if results and all(r.ok is not False for r in results) and any(r.ok for r in results) else 1


def format_summary(results: list[Result], discs, notes: list[str], args, seconds: float) -> str:
    mark = {True: "PASS", False: "FAIL", None: "skip"}
    lines = ["# Release check", "",
             f"{_dt.datetime.now():%Y-%m-%d %H:%M}, {seconds / 60:.1f} min, "
             f"corpus {'full' if args.full else 'sample'}, max undecoded {args.max_open} %", ""]
    lines += ["| Check | Result | Details | Time |", "| --- | --- | --- | --- |"]
    for r in results:
        lines.append(f"| {r.name} | **{mark[r.ok]}** | {r.summary} | {r.seconds / 60:.1f} min |")
    if notes:
        lines += ["", "Not checked (folder missing):", ""] + [f"- {n}" for n in notes]
    for r in results:
        if r.details:
            lines += ["", f"## {r.name}", ""] + [f"- {d}" for d in r.details]
    verdict = "ALL CHECKS PASSED" if all(r.ok is not False for r in results) else "SOME CHECKS FAILED"
    lines += ["", f"**{verdict}**"]
    return "\n".join(lines)


if __name__ == "__main__":
    raise SystemExit(main())
