"""Command-line script tools.

    python -m fe_modding.formats.cmb decompile C05.cmb [-o c05.fe9s]
    python -m fe_modding.formats.cmb compile c05.fe9s -o C05.cmb [--base C05.cmb]
    python -m fe_modding.formats.cmb roundtrip <Scripts dir>

``--base`` keeps the original file's header, string-pool order and padding
bytes, so an unchanged script compiles back byte-for-byte.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import CompileError, compile_source, decompile, read_cmb, read_cmb_path, write_cmb


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(prog="python -m fe_modding.formats.cmb")
    sub = ap.add_subparsers(dest="cmd", required=True)
    d = sub.add_parser("decompile")
    d.add_argument("cmb", type=Path)
    d.add_argument("-o", "--output", type=Path)
    c = sub.add_parser("compile")
    c.add_argument("source", type=Path)
    c.add_argument("-o", "--output", type=Path, required=True)
    c.add_argument("--base", type=Path)
    r = sub.add_parser("roundtrip")
    r.add_argument("scripts_dir", type=Path)
    args = ap.parse_args(argv)

    if args.cmd == "decompile":
        source, stats = decompile(read_cmb_path(args.cmb), args.cmb.name)
        if args.output:
            args.output.write_text(source, encoding="utf-8")
        else:
            sys.stdout.reconfigure(encoding="utf-8")
            print(source)
        print(f"{stats.structured} structured, {stats.goto} goto, {stats.asm} asm", file=sys.stderr)
        return 0
    if args.cmd == "compile":
        base = read_cmb_path(args.base) if args.base else None
        try:
            result = compile_source(args.source.read_text(encoding="utf-8"), base=base)
        except CompileError as e:
            for diag in e.diagnostics:
                print(f"{args.source}:{diag}", file=sys.stderr)
            return 1
        for diag in result.warnings:
            print(f"{args.source}:{diag}", file=sys.stderr)
        args.output.write_bytes(write_cmb(result.script))
        return 0

    failures = 0
    for path in sorted(args.scripts_dir.glob("*.cmb")):
        data = path.read_bytes()
        script = read_cmb(data)
        source, stats = decompile(script, path.name)
        rebuilt = write_cmb(compile_source(source, base=script).script)
        ok = rebuilt == data
        failures += not ok
        print(f"{path.name}: {'ok' if ok else 'DIFFERS'} ({stats.structured} structured, {stats.goto} goto, {stats.asm} asm)")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
