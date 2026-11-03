"""Normalize links inside raw HTML blocks for MkDocs directory URLs."""

from __future__ import annotations

import argparse
import os
import re
from pathlib import Path, PurePosixPath


ROOT = Path(__file__).resolve().parents[2]
WIKI = ROOT / "wiki"
PATTERN = re.compile(r'href="([^"#:?]+\.md)(#[^"]*)?"')


def output_directory(source: Path) -> PurePosixPath:
    relative = PurePosixPath(source.relative_to(WIKI).as_posix())
    if relative.name == "index.md":
        return relative.parent
    return relative.with_suffix("")


def replacement(source: Path, match: re.Match[str]) -> str:
    target_source = (source.parent / match.group(1)).resolve()
    try:
        target_relative = PurePosixPath(target_source.relative_to(WIKI.resolve()).as_posix())
    except ValueError:
        return match.group(0)
    target_output = target_relative.parent if target_relative.name == "index.md" else target_relative.with_suffix("")
    relative = PurePosixPath(os.path.relpath(str(target_output), str(output_directory(source))).replace("\\", "/"))
    suffix = match.group(2) or ""
    return f'href="{relative.as_posix()}/{suffix}"'


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--write", action="store_true", help="rewrite affected Markdown files")
    args = parser.parse_args()
    changed: list[Path] = []
    for source in sorted(WIKI.rglob("*.md")):
        text = source.read_text(encoding="utf-8")
        updated = PATTERN.sub(lambda match: replacement(source, match), text)
        if updated == text:
            continue
        changed.append(source)
        if args.write:
            source.write_text(updated, encoding="utf-8")
    if changed and not args.write:
        for source in changed:
            print(f"ERROR: raw HTML link needs normalization: {source.relative_to(ROOT)}")
        return 1
    print(f"{'Updated' if args.write else 'OK:'} {len(changed)} files")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
