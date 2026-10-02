"""Byte-coverage map of a whole extracted disc: which bytes have a known meaning.

The disc-wide counterpart of :mod:`fe8data_coverage`. Every byte of every
file gets one status (the same five, plus ``unclassified``):

- ``decoded``: a field with a confirmed (or strongly evidenced) meaning,
  container structure, a string, or the payload of a public codec
  (GX texels, DSP-ADPCM frames, THP video);
- ``plausible``: a field whose meaning is only a guess;
- ``undecoded``: no known meaning;
- ``reserved``: a field no code in ``main.dol`` reads (proven, see
  ``UNDECODED_BYTES_CLOSURE_PLAN.md`` Phase 4);
- ``padding``: alignment or zero fill;
- ``no-reader``: a field no reader was found for in ``main.dol`` (its value
  may still be described); it becomes ``reserved`` once Phase 4 proves it;
- ``unclassified``: no handler placed the byte. Counts as undecoded.

Containers are walked: an LZ10 stream is counted once as ``lz10`` and its
decompressed bytes again under their own format, a ``pack`` archive's
table under ``pak`` and each member under its own format. The totals
therefore count every layer; ``leaf`` totals leave containers out.

Flag fields with some unknown bits are judged on the value: a byte is
undecoded only when one of its unknown bits is set, plausible when only
plausible bits are set. A clear unknown bit carries no meaning to decode.

Run ``python -m fe_modding.formats.coverage <files dir> [--saves DIR]``
for the per-format summary and ``--fields`` for every non-decoded field.
"""

from __future__ import annotations

import argparse
import io
import re
import struct
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

UNCLASSIFIED, DECODED, PLAUSIBLE, UNDECODED, RESERVED, PADDING, UNREAD = range(7)
STATUS_NAMES = ("unclassified", "decoded", "plausible", "undecoded", "reserved", "padding", "no-reader")
OPEN = (UNCLASSIFIED, PLAUSIBLE, UNDECODED, UNREAD)

#: Formats that only hold other files; left out of the leaf totals.
CONTAINERS = {"lz10", "pak"}

#: Files of an extracted tree that are tool output, not disc content.
SKIPPED_SUFFIXES = (".decomp", ".bak", ".decompressed")


def _u16(data: bytes, offset: int) -> int:
    return struct.unpack_from(">H", data, offset)[0]


def _u32(data: bytes, offset: int) -> int:
    return struct.unpack_from(">I", data, offset)[0]


class FileCoverage:
    """Per-byte status of one file. Later marks override earlier ones."""

    def __init__(self, data: bytes, fmt: str, name: str):
        self.data = data
        self.fmt = fmt
        self.name = name
        self.status = bytearray(len(data))
        self.labels: list[tuple[int, int, int, str]] = []

    def mark(self, start: int, size: int, status: int, name: str = "") -> None:
        start = max(start, 0)
        end = min(start + size, len(self.data))
        if end <= start:
            return
        self.status[start:end] = bytes([status]) * (end - start)
        if status != DECODED:
            self.labels.append((start, end, status, name))

    def fields(self, base: int, layout, prefix: str = "") -> None:
        """``layout``: ``(offset, size, status, name)`` tuples."""
        for offset, size, status, name in layout:
            self.mark(base + offset, size, status, prefix + name)

    def bits(self, offset: int, size: int, known: int, plausible: int = 0, name: str = "") -> None:
        """A flag field: decoded unless a set bit is outside ``known``."""
        value = int.from_bytes(self.data[offset : offset + size], "big")
        for i in range(size):
            shift = 8 * (size - 1 - i)
            byte, k, p = (value >> shift) & 0xFF, (known >> shift) & 0xFF, (plausible >> shift) & 0xFF
            if byte & ~(k | p):
                self.mark(offset + i, 1, UNDECODED, f"{name} bits {(byte & ~(k | p)) << shift:#x}")
            elif byte & p:
                self.mark(offset + i, 1, PLAUSIBLE, f"{name} bits {(byte & p) << shift:#x}")
            else:
                self.mark(offset + i, 1, DECODED)

    def zero(self, offset: int, size: int, name: str, nonzero: int = UNDECODED) -> None:
        """Padding when zero, ``nonzero`` (a name for the field) otherwise."""
        chunk = self.data[offset : offset + size]
        self.mark(offset, size, PADDING if not any(chunk) else nonzero, name)

    def fill(self, status: int, name: str = "", only_zero: bool = False) -> None:
        """Mark every unclassified byte (or only the zero ones)."""
        data, st = self.data, self.status
        i = 0
        while i < len(st):
            if st[i] != UNCLASSIFIED or (only_zero and data[i]):
                i += 1
                continue
            j = i
            while j < len(st) and st[j] == UNCLASSIFIED and (not only_zero or not data[j]):
                j += 1
            self.mark(i, j - i, status, name)
            i = j

    def counts(self) -> list[int]:
        return [self.status.count(s) for s in range(len(STATUS_NAMES))]

    def open_fields(self) -> dict[tuple[int, str], int]:
        """Byte count of each named non-decoded field, by its final status."""
        result: dict[tuple[int, str], int] = defaultdict(int)
        for start, end, status, name in self.labels:
            n = self.status[start:end].count(status)
            if n:
                result[(status, re.sub(r"\[\d+\]", "[]", name))] += n
        rest = self.status.count(UNCLASSIFIED) - sum(n for (st, _), n in result.items() if st == UNCLASSIFIED)
        if rest > 0:
            result[(UNCLASSIFIED, "(unplaced bytes)")] += rest
        return result


@dataclass
class FormatTotals:
    files: int = 0
    counts: list[int] = field(default_factory=lambda: [0] * len(STATUS_NAMES))
    fields: dict[tuple[int, str], list[int]] = field(default_factory=dict)  # -> [bytes, files]
    failures: list[str] = field(default_factory=list)


class Report:
    def __init__(self) -> None:
        self.formats: dict[str, FormatTotals] = defaultdict(FormatTotals)

    def add(self, cov: FileCoverage) -> None:
        totals = self.formats[cov.fmt]
        totals.files += 1
        for s, n in enumerate(cov.counts()):
            totals.counts[s] += n
        for key, n in cov.open_fields().items():
            entry = totals.fields.setdefault(key, [0, 0])
            entry[0] += n
            entry[1] += 1

    def fail(self, fmt: str, name: str, error: Exception) -> None:
        self.formats[fmt].failures.append(f"{name}: {type(error).__name__}: {error}")

    def totals(self, leaf: bool) -> list[int]:
        result = [0] * len(STATUS_NAMES)
        for fmt, t in self.formats.items():
            if leaf and fmt in CONTAINERS:
                continue
            for s in range(len(STATUS_NAMES)):
                result[s] += t.counts[s]
        return result


# ------------------------------------------------------------------ dispatch

Handler = Callable[[FileCoverage, "Walker"], None]


class Walker:
    """Classifies files and recurses into containers."""

    def __init__(self, report: Report):
        self.report = report

    def child(self, name: str, data: bytes) -> None:
        fmt, handler = identify(name, data)
        cov = FileCoverage(data, fmt, name)
        try:
            handler(cov, self)
        except Exception as error:  # a parser rejecting real data is a finding, not a crash
            self.report.fail(fmt, name, error)
            cov.status[:] = bytes(len(data))
            cov.labels = [(0, len(data), UNCLASSIFIED, "(handler failed)")]
        self.report.add(cov)


_FORMATS: list[tuple[str, Callable[[str, bytes], bool], Handler]] = []


def handles(fmt: str, test: Callable[[str, bytes], bool]):
    def register(handler: Handler) -> Handler:
        _FORMATS.append((fmt, test, handler))
        return handler
    return register


def _base(name: str) -> str:
    """Lower-case file name of a path or an ``archive:member`` name."""
    return re.split(r"[/\:]", name.rstrip("#"))[-1].lower()


def _ext(name: str) -> str:
    base = _base(name)
    return base.rsplit(".", 1)[-1] if "." in base else ""


def _unknown(cov: FileCoverage, walker: Walker) -> None:
    cov.labels.append((0, len(cov.data), UNCLASSIFIED, f"(no handler: .{_ext(cov.name) or '?'})"))


def identify(name: str, data: bytes) -> tuple[str, Handler]:
    for fmt, test, handler in _FORMATS:
        if test(name, data):
            return fmt, handler
    return f"unknown .{_ext(name) or '?'}", _unknown


def walk_tree(root: Path, report: Report, progress: bool = False) -> None:
    walker = Walker(report)
    paths = sorted(p for p in root.rglob("*") if p.is_file() and not p.name.endswith(SKIPPED_SUFFIXES)
                   and not any(part.endswith("_extracted") for part in p.parts))
    for i, path in enumerate(paths):
        if progress:
            print(f"\r{i + 1}/{len(paths)} {path.relative_to(root).as_posix()[:60]:<60}", end="", file=sys.stderr)
        walker.child(path.relative_to(root).as_posix(), path.read_bytes())
    if progress:
        print(file=sys.stderr)


# The handlers live in coverage_handlers so this module stays the framework.
from . import coverage_handlers  # noqa: E402,F401  (registers the handlers)


# ------------------------------------------------------------------ output

def format_summary(report: Report) -> str:
    head = f"{'format':<22}{'files':>7}{'bytes':>13}" + "".join(f"{s[:7]:>11}" for s in STATUS_NAMES)
    rows = [head]

    def row(label: str, files: int, counts: list[int]) -> str:
        return f"{label:<22}{files:>7}{sum(counts):>13}" + "".join(f"{n:>11}" for n in counts)

    for fmt in sorted(report.formats, key=lambda f: -sum(report.formats[f].counts)):
        t = report.formats[fmt]
        rows.append(row(fmt, t.files, t.counts))
    for leaf in (False, True):
        counts = report.totals(leaf)
        total = sum(counts) or 1
        open_bytes = counts[UNCLASSIFIED] + counts[UNDECODED]
        rows.append(row("TOTAL (leaf)" if leaf else "TOTAL (all layers)",
                        sum(t.files for f, t in report.formats.items() if not (leaf and f in CONTAINERS)), counts))
        rows.append(f"  undecoded+unclassified {100 * open_bytes / total:.4f} %, "
                    f"plausible {100 * counts[PLAUSIBLE] / total:.4f} %, reserved {100 * counts[RESERVED] / total:.4f} %")
    return "\n".join(rows)


def format_fields(report: Report) -> str:
    rows = []
    for fmt in sorted(report.formats):
        t = report.formats[fmt]
        items = sorted(((k, v) for k, v in t.fields.items() if k[0] != RESERVED), key=lambda kv: (kv[0][0], -kv[1][0]))
        if not items and not t.failures:
            continue
        rows.append(f"\n{fmt}")
        for (status, name), (n, files) in items:
            rows.append(f"  {STATUS_NAMES[status]:<13}{n:>11} B  {files:>5} files  {name}")
        for failure in t.failures[:10]:
            rows.append(f"  FAILED {failure}")
        if len(t.failures) > 10:
            rows.append(f"  ... {len(t.failures) - 10} more failures")
    return "\n".join(rows)


def format_markdown(report: Report) -> str:
    """The open fields as Markdown, for ``STATUS_INVENTORY.md`` §2: one table
    of byte counts per status and format, then every open field."""
    open_statuses = (UNCLASSIFIED, UNDECODED, PLAUSIBLE, UNREAD)
    rows = ["| Format | Files | Bytes | " + " | ".join(STATUS_NAMES[s] for s in open_statuses) + " |",
            "|---|---:|---:|" + "---:|" * len(open_statuses)]
    for fmt in sorted(report.formats, key=lambda f: -sum(report.formats[f].counts[s] for s in open_statuses)):
        t = report.formats[fmt]
        if fmt in CONTAINERS or not any(t.counts[s] for s in open_statuses):
            continue
        rows.append(f"| {fmt} | {t.files} | {sum(t.counts):,} | "
                    + " | ".join(f"{t.counts[s]:,}" for s in open_statuses) + " |")
    counts = report.totals(leaf=True)
    total = sum(counts) or 1
    rows.append(f"| **Total (leaf)** | | {total:,} | "
                + " | ".join(f"{counts[s]:,} ({100 * counts[s] / total:.3f} %)" for s in open_statuses) + " |")
    rows += ["", "| Format | Status | Field | Bytes | Files |", "|---|---|---|---:|---:|"]
    for fmt in sorted(report.formats):
        for (status, name), (n, files) in sorted(report.formats[fmt].fields.items(), key=lambda kv: -kv[1][0]):
            if status in open_statuses:
                rows.append(f"| {fmt} | {STATUS_NAMES[status]} | {name} | {n:,} | {files} |")
    return "\n".join(rows)


def main(argv: Optional[list[str]] = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("files", type=Path, help="an extracted files/ directory")
    parser.add_argument("--saves", type=Path, help="also classify the .gci saves in this directory")
    parser.add_argument("--fields", action="store_true", help="list every non-decoded field")
    parser.add_argument("--only", help="regular expression: only files whose path matches")
    parser.add_argument("--markdown", action="store_true", help="print the open fields as Markdown tables")
    parser.add_argument("--markdown-out", type=Path, help="also write the Markdown tables to this file")
    args = parser.parse_args(argv)
    report = Report()
    if args.only:
        walker = Walker(report)
        pattern = re.compile(args.only)
        for path in sorted(args.files.rglob("*")):
            rel = path.relative_to(args.files).as_posix()
            if path.is_file() and pattern.search(rel) and not path.name.endswith(SKIPPED_SUFFIXES):
                walker.child(rel, path.read_bytes())
    else:
        walk_tree(args.files, report, progress=sys.stderr.isatty())
    if args.saves:
        walker = Walker(report)
        for path in sorted(args.saves.rglob("*.gci")):
            walker.child(path.name, path.read_bytes())
    if args.markdown_out:
        args.markdown_out.write_bytes((format_markdown(report) + "\n").encode("utf-8"))
    if args.markdown:
        print(format_markdown(report))
        return
    print(format_summary(report))
    if args.fields:
        print(format_fields(report))


if __name__ == "__main__":
    # Run through the package module: the handlers register there, not in __main__.
    from fe_modding.formats import coverage as _package_module

    _package_module.main()
