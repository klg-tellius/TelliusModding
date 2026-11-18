"""Run every test the release needs, on every extracted disc, in one command.

The unit tests run once with no disc. Then the whole suite runs again for each extracted disc
found, with the variables its disc tests read (``FE9_EXTRACTED``, ``FE9_EXTRACTED_FILES``,
``FE9_ZDBX``, ``FE9_SAVES`` on Path of Radiance; ``FE10_EXTRACTED``, ``FE10_EXTRACTED_FILES``,
``FE10_SAVES`` on Radiant Dawn). The other game's variables are cleared, so its disc tests skip.
The Radiant Dawn tests that compare the regions (``FE10_EU_EXTRACTED``, ``FE10_JP_EXTRACTED``) run
once, in the first Radiant Dawn run, with every Radiant Dawn disc found.

    python -m tools.release_checks G:\\ROM\\por_work G:\\ROM\\rd_work --saves G:\\ROM\\SaveFile
    python -m tools.release_checks G:\\ROM\\rd_work\\RFEE01 --full --coverage
    python -m tools.release_checks G:\\ROM\\por_work --only test_formats test_cmb

Each path is a disc folder (it holds ``sys/boot.bin`` and ``files/``) or a folder of disc
folders, where each disc ID counts once (the subfolder named after it wins over a project's copy).
The disc ID in ``boot.bin`` says which game and region it is. Run from ``App/``, or use
``release\\run_release_checks.bat`` from anywhere.

Options:

* ``--saves DIR``: the saves folder. Path of Radiance reads the ``.gci`` files directly in it;
  Radiant Dawn reads every ``*FE10_US.dat`` below it (``DIR/rd`` is the usual place).
* ``--blender EXE``: also build real Blender terrain kits (``FE9_BLENDER``).
* ``--full``: walk every file of a kind instead of the sample (``TELLIUS_CORPUS=full``). Slower;
  do it before a release.
* ``--coverage``: also measure each disc's byte coverage (``fe_modding.formats.coverage``).
* ``--only MODULE...``: run only these test modules.
* ``--no-unit``: skip the run with no disc.
* ``-j N``: test modules run at once (default: the number of processors, at most 8).

Every module runs in its own process. The results go to ``release-checks/<date-time>/``:
``summary.md``, one log per module that failed, and the coverage reports. The command ends with
the exit code 1 when anything failed.
"""

from __future__ import annotations

import argparse
import datetime as _dt
import os
import re
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path

APP = Path(__file__).resolve().parent.parent
TESTS = APP / "tests"

#: Every variable a disc test reads; each run sets only its own.
DISC_VARIABLES = ("FE9_EXTRACTED", "FE9_EXTRACTED_FILES", "FE9_ZDBX", "FE9_SAVES", "FE9_BLENDER",
                  "FE10_EXTRACTED", "FE10_EXTRACTED_FILES", "FE10_EU_EXTRACTED", "FE10_JP_EXTRACTED",
                  "FE10_SAVES", "TELLIUS_CORPUS")

GAMES = {"GFE": "Path of Radiance", "RFE": "Radiant Dawn"}
REGIONS = {"E": "US", "P": "Europe", "J": "Japan"}


@dataclass
class Disc:
    root: Path
    disc_id: str

    @property
    def game(self) -> str:
        return GAMES[self.disc_id[:3]]

    @property
    def label(self) -> str:
        return f"{self.game} {REGIONS.get(self.disc_id[3], '?')} ({self.disc_id})"

    @property
    def files(self) -> Path:
        return self.root / "files"


@dataclass
class Result:
    module: str
    ran: int = 0
    failures: int = 0
    errors: int = 0
    skipped: int = 0
    seconds: float = 0.0
    returncode: int = 0
    output: str = ""
    log: str = ""

    @property
    def ok(self) -> bool:
        return self.returncode == 0 and not self.failures and not self.errors


@dataclass
class Run:
    title: str
    results: list[Result] = field(default_factory=list)
    coverage: str = ""

    @property
    def totals(self) -> tuple[int, int, int, int]:
        return (sum(r.ran for r in self.results), sum(r.failures for r in self.results),
                sum(r.errors for r in self.results), sum(r.skipped for r in self.results))

    @property
    def broken(self) -> list[Result]:
        return [r for r in self.results if not r.ok]


def read_disc_id(root: Path) -> str:
    """The six-character disc ID of an extracted disc folder, or "" when it is not one."""
    try:
        raw = (root / "sys" / "boot.bin").read_bytes()[:6].decode("ascii")
    except (OSError, UnicodeDecodeError):
        return ""
    return raw if raw[:3] in GAMES and (root / "files").is_dir() else ""


def find_discs(paths: list[Path]) -> list[Disc]:
    """The disc folders among ``paths`` and their direct subfolders, Path of Radiance first.

    A path that is itself a disc is always kept. In a folder of discs, each disc ID is kept once,
    from the subfolder named after it when there is one (``rd_work/RFEE01`` rather than a
    project's copy beside it)."""
    found: dict[Path, Disc] = {}
    for path in paths:
        disc_id = read_disc_id(path)
        if disc_id:
            found.setdefault(path.resolve(), Disc(path, disc_id))
            continue
        children = sorted((p for p in path.iterdir() if p.is_dir()), key=lambda p: p.name) if path.is_dir() else []
        by_id: dict[str, Path] = {}
        for child in children:
            child_id = read_disc_id(child)
            if child_id and (child_id not in by_id or child.name.upper() == child_id):
                by_id[child_id] = child
        for child_id, child in by_id.items():
            found.setdefault(child.resolve(), Disc(child, child_id))
    order = {"GFE": 0, "RFE": 1}
    return sorted(found.values(), key=lambda d: (order[d.disc_id[:3]], "EPJ".find(d.disc_id[3]), d.disc_id))


def disc_environment(disc: Disc | None, args: argparse.Namespace, regions: dict[str, Disc] | None = None) -> dict[str, str]:
    """The environment of one run. ``regions``: the Radiant Dawn discs by region letter, given to
    the one run that also checks the regions against each other."""
    env = {k: v for k, v in os.environ.items() if k not in DISC_VARIABLES}
    env["PYTHONIOENCODING"] = "utf-8"
    if args.full:
        env["TELLIUS_CORPUS"] = "full"
    if disc is None:
        return env
    if disc.disc_id.startswith("GFE"):
        env["FE9_EXTRACTED"] = str(disc.root)
        env["FE9_EXTRACTED_FILES"] = str(disc.files)
        if (disc.files / "zdbx.cmp").is_file():
            env["FE9_ZDBX"] = str(disc.files / "zdbx.cmp")
        if args.saves and any(args.saves.glob("*.gci")):
            env["FE9_SAVES"] = str(args.saves)
        if args.blender:
            env["FE9_BLENDER"] = str(args.blender)
    else:
        env["FE10_EXTRACTED"] = str(disc.root)
        env["FE10_EXTRACTED_FILES"] = str(disc.files)
        for letter, name in (("P", "FE10_EU_EXTRACTED"), ("J", "FE10_JP_EXTRACTED")):
            if regions and letter in regions:
                env[name] = str(regions[letter].root)
        if args.saves:
            env["FE10_SAVES"] = str(args.saves)
    return env


_RAN = re.compile(r"^Ran (\d+) tests? in ([\d.]+)s", re.M)
_COUNT = re.compile(r"(failures|errors|skipped)=(\d+)")


def run_module(module: str, env: dict[str, str], timeout: float) -> Result:
    started = time.monotonic()
    command = [sys.executable, "-m", "unittest", "discover", "-s", "tests", "-p", module + ".py"]
    try:
        done = subprocess.run(command, cwd=APP, env=env, capture_output=True, text=True,
                              encoding="utf-8", errors="replace", timeout=timeout)
        output, code = done.stdout + done.stderr, done.returncode
    except subprocess.TimeoutExpired as exc:
        partial = exc.stdout or b""
        output = (partial.decode("utf-8", "replace") if isinstance(partial, bytes) else partial)
        output += f"\n\nTIMEOUT after {timeout:.0f} s"
        code = -1
    result = Result(module, seconds=time.monotonic() - started, returncode=code, output=output)
    ran = _RAN.findall(output)
    result.ran = int(ran[-1][0]) if ran else 0
    tail = output[output.rfind("\nRan "):] if ran else output
    for name, value in _COUNT.findall(tail.splitlines()[-1] if tail.strip() else ""):
        setattr(result, name, int(value))
    if code != 0 and not (result.failures or result.errors):
        result.errors = 1  # import error, crash or timeout: count the module once
    return result


def test_modules(only: list[str]) -> list[str]:
    modules = sorted(p.stem for p in TESTS.glob("test_*.py"))
    if only:
        wanted = {m[:-3] if m.endswith(".py") else m for m in only}
        unknown = wanted - set(modules)
        if unknown:
            raise SystemExit("unknown test module: " + ", ".join(sorted(unknown)))
        modules = [m for m in modules if m in wanted]
    return modules


def run_suite(title: str, modules: list[str], env: dict[str, str], args: argparse.Namespace) -> Run:
    run = Run(title)
    print(f"\n== {title}: {len(modules)} modules", flush=True)
    with ThreadPoolExecutor(max_workers=args.jobs) as pool:
        futures = {m: pool.submit(run_module, m, env, args.timeout) for m in modules}
        for module in modules:
            result = futures[module].result()
            run.results.append(result)
            mark = "ok  " if result.ok else "FAIL"
            print(f"  {mark} {module:<45} {result.ran:>5} tests  {result.skipped:>4} skipped  "
                  f"{result.seconds:6.1f} s", flush=True)
    ran, failures, errors, skipped = run.totals
    print(f"   {ran} tests, {failures} failures, {errors} errors, {skipped} skipped", flush=True)
    return run


def run_coverage(disc: Disc, env: dict[str, str], out: Path, args: argparse.Namespace) -> str:
    report = out / f"{disc.disc_id}-coverage.md"
    command = [sys.executable, "-m", "fe_modding.formats.coverage", str(disc.files),
               "--markdown-out", str(report)]
    if args.saves and disc.disc_id.startswith("GFE") and any(args.saves.glob("*.gci")):
        command += ["--saves", str(args.saves)]
    print(f"   coverage of {disc.disc_id}...", flush=True)
    done = subprocess.run(command, cwd=APP, env=env, capture_output=True, text=True,
                          encoding="utf-8", errors="replace")
    summary = (done.stdout + done.stderr).strip()
    (out / f"{disc.disc_id}-coverage.txt").write_text(summary + "\n", encoding="utf-8")
    return summary


def write_summary(out: Path, runs: list[Run], discs: list[Disc], args: argparse.Namespace) -> Path:
    lines = ["# Release checks", "",
             f"Run on {_dt.datetime.now():%Y-%m-%d %H:%M} from `{APP}`, Python {sys.version.split()[0]}.",
             f"Corpus: {'full' if args.full else 'sample'}.", ""]
    if not discs:
        lines += ["**No extracted disc was found**: only the unit tests ran.", ""]
    lines += ["| Run | Tests | Failures | Errors | Skipped | Result |", "| --- | ---: | ---: | ---: | ---: | --- |"]
    for run in runs:
        ran, failures, errors, skipped = run.totals
        lines.append(f"| {run.title} | {ran} | {failures} | {errors} | {skipped} | "
                     f"{'OK' if not run.broken else 'FAILED'} |")
    for run in runs:
        if run.broken:
            lines += ["", f"## {run.title}: failed modules", ""]
            for result in run.broken:
                lines.append(f"- `{result.module}`: {result.failures} failures, {result.errors} errors "
                             f"(log: `{result.log}`)")
        if run.coverage:
            lines += ["", f"## {run.title}: coverage", "", "```", run.coverage[-3000:], "```"]
    path = out / "summary.md"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("discs", nargs="*", type=Path, help="disc folders, or folders that hold them")
    parser.add_argument("--saves", type=Path, help="the saves folder (.gci files, and FE10_US.dat below it)")
    parser.add_argument("--blender", type=Path, help="blender.exe, to build real terrain kits")
    parser.add_argument("--full", action="store_true", help="walk every file (TELLIUS_CORPUS=full)")
    parser.add_argument("--coverage", action="store_true", help="also measure each disc's byte coverage")
    parser.add_argument("--only", nargs="+", default=[], metavar="MODULE", help="run only these test modules")
    parser.add_argument("--no-unit", action="store_true", help="skip the run with no disc")
    parser.add_argument("-j", "--jobs", type=int, default=min(8, os.cpu_count() or 2))
    parser.add_argument("--timeout", type=float, default=3600, help="seconds one module may take")
    parser.add_argument("--out", type=Path, help="report folder (default: release-checks/<date-time>)")
    args = parser.parse_args(argv)

    for path in args.discs:
        if not path.exists():
            parser.error(f"{path} does not exist")
    discs = find_discs(args.discs)
    if args.discs and not discs:
        parser.error("no extracted disc (sys/boot.bin and files/) in " + ", ".join(map(str, args.discs)))
    modules = test_modules(args.only)
    out = args.out or APP.parent / "release-checks" / _dt.datetime.now().strftime("%Y-%m-%d_%H%M%S")
    out.mkdir(parents=True, exist_ok=True)

    print("Discs: " + (", ".join(d.label for d in discs) if discs else "none"))
    runs: list[Run] = []
    if not args.no_unit:
        runs.append(run_suite("Unit tests (no disc)", modules, disc_environment(None, args), args))
    rd = [d for d in discs if d.disc_id.startswith("RFE")]
    regions = {d.disc_id[3]: d for d in reversed(rd)}  # the first disc of each region
    for disc in discs:
        env = disc_environment(disc, args, regions if rd and disc is rd[0] else None)
        run = run_suite(disc.label, modules, env, args)
        if args.coverage:
            run.coverage = run_coverage(disc, env, out, args)
        runs.append(run)

    for run in runs:
        tag = re.sub(r"[^A-Za-z0-9]+", "_", run.title).strip("_")
        for result in run.broken:
            log = out / f"{tag}__{result.module}.log"
            log.write_text(result.output, encoding="utf-8")
            result.log = log.name
    summary = write_summary(out, runs, discs, args)

    print("\nSummary")
    for run in runs:
        ran, failures, errors, skipped = run.totals
        state = "OK" if not run.broken else "FAILED: " + ", ".join(r.module for r in run.broken)
        print(f"  {run.title:<40} {ran:>6} tests  {skipped:>5} skipped  {state}")
    print(f"\nReport: {summary}")
    return 1 if any(run.broken for run in runs) else 0


if __name__ == "__main__":
    sys.exit(main())
