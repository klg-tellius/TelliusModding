"""Write a per-instance JSONL inventory of undecoded FE9 .g/.gs/.ga bytes.

Usage: python App/tools/manifest_3d_unknowns.py <extracted-files> <output.jsonl>
The member path, offset, raw bytes, and SHA-256 make each finding reproducible.
"""

from __future__ import annotations

import argparse
from array import array
from collections import Counter
import hashlib
import json
import sys
from pathlib import Path

APP = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APP))

from fe_modding.formats.coverage import (  # noqa: E402
    UNDECODED, FileCoverage, Report, walk_tree,
)

FORMATS = {"skeleton", "gs", "animation"}


def undecoded_spans(cov: FileCoverage):
    """Yield final undecoded runs, splitting at coverage-label boundaries."""
    status = cov.status
    labels = ["(unlabeled)"]
    label_ids = array("I", [0]) * len(status)
    for a, b, kind, name in cov.labels:
        if kind == UNDECODED and a < b:
            labels.append(name)
            label_ids[a:b] = array("I", [len(labels) - 1]) * (b - a)
    start = 0
    while (start := status.find(UNDECODED, start)) >= 0:
        label_id = label_ids[start]
        end = start + 1
        while end < len(status) and status[end] == UNDECODED and label_ids[end] == label_id:
            end += 1
        yield start, end, labels[label_id]
        start = end


class InventoryReport(Report):
    def __init__(self, output):
        super().__init__()
        self.output = output
        self.instances = 0
        self.fields = Counter()

    def add(self, cov: FileCoverage) -> None:
        if cov.fmt not in FORMATS:
            return
        digest = hashlib.sha256(cov.data).hexdigest()
        for start, end, label in undecoded_spans(cov):
            self.output.write(json.dumps({
                "format": cov.fmt,
                "path": cov.name,
                "offset": start,
                "length": end - start,
                "raw_hex": cov.data[start:end].hex(),
                "field": label,
                "status": "undecoded",
                "sha256": digest,
            }, ensure_ascii=False) + "\n")
            self.instances += 1
            self.fields[(cov.fmt, label)] += end - start
        super().add(cov)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("files_dir", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    if not args.files_dir.is_dir():
        parser.error(f"Not a directory: {args.files_dir}")
    with args.output.open("w", encoding="utf-8", newline="\n") as output:
        report = InventoryReport(output)
        walk_tree(args.files_dir, report, progress=sys.stderr.isatty())
    for fmt in ("skeleton", "gs", "animation"):
        total = report.formats[fmt]
        print(f"{fmt}: {total.files} files, {total.counts[UNDECODED]} undecoded bytes, "
              f"{len(total.failures)} handler failures")
        for failure in total.failures[:5]:
            print(f"  {failure}", file=sys.stderr)
    for (fmt, field), count in sorted(report.fields.items()):
        print(f"  {fmt}: {field}: {count} bytes")
    print(f"{report.instances} spans -> {args.output}")


if __name__ == "__main__":
    main()
