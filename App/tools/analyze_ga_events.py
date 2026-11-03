"""Inventory Fire Emblem: Path of Radiance ``.ga`` event-track codes.

The disc stores animations both loose and inside LZ10-compressed ``pack``
archives.  This scanner walks both container layers without extracting them
and reports code frequency, file coverage, frame placement, and examples.
"""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path

from fe_modding.formats import animation, gcfesnd, lz10, pak


@dataclass(frozen=True)
class Occurrence:
    path: str
    frame: int
    end_frame: int
    codes: tuple[int, ...]


def walk(name: str, data: bytes):
    """Yield ``(virtual path, data)`` for every nested GA file."""
    lower = name.lower().rstrip("#")
    if data[:1] == b"\x10" and lower.endswith((".cmp", ".cms")):
        yield from walk(name + "#", lz10.decompress(data))
        return
    if data[:4] == b"pack":
        for entry in pak.read_pak_entries(data):
            child = pak.read_pak_file_content(data, entry)
            yield from walk(f"{name.rstrip('#')}:{entry.name}", child)
        return
    if lower.endswith(".ga"):
        yield name, data


def scan(root: Path) -> tuple[int, dict[int, list[Occurrence]]]:
    occurrences: dict[int, list[Occurrence]] = defaultdict(list)
    animations = 0
    for path in sorted(p for p in root.rglob("*") if p.is_file()):
        relative = path.relative_to(root).as_posix()
        for virtual_path, data in walk(relative, path.read_bytes()):
            anim = animation.read_animation_bytes(data)
            animations += 1
            for key in anim.events:
                occurrence = Occurrence(virtual_path, key.frame, anim.header.end_frame, key.codes)
                for code in key.codes:
                    occurrences[code].append(occurrence)
    return animations, occurrences


def fmt_code(code: int) -> str:
    return f"{code} (0x{code:04X})"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path, help="extracted disc files directory")
    parser.add_argument("--code", type=lambda value: int(value, 0), action="append",
                        help="show every occurrence of a code (repeatable; accepts hex)")
    parser.add_argument("--examples", type=int, default=3,
                        help="example paths per code in the summary (default: 3)")
    parser.add_argument("--details-only", action="store_true",
                        help="omit the all-code summary (use with --code)")
    args = parser.parse_args()

    animations, occurrences = scan(args.root)
    catalog_path = args.root / "Sound" / "gcfesnd.bin"
    sound_names = {}
    if catalog_path.is_file():
        # The retail table is sorted.  Three ids are duplicated; its binary
        # search currently lands on the first entry of each pair.
        for entry in gcfesnd.read_sfx_table(catalog_path.read_bytes()):
            sound_names.setdefault(entry.event_code, entry.name)
    print(f"animations: {animations}")
    print(f"distinct event codes: {len(occurrences)}")
    low_codes = sorted(code for code in occurrences if code < 1000)
    sound_codes = sorted(code for code in occurrences if code >= 1000)
    resolved_sound_codes = [code for code in sound_codes if code in sound_names]
    print(f"engine event codes (<1000): {len(low_codes)}")
    print(f"sound event codes (>=1000): {len(sound_codes)} "
          f"({len(resolved_sound_codes)} resolved, "
          f"{len(sound_codes) - len(resolved_sound_codes)} missing from SFXTable)")
    if sound_codes and len(resolved_sound_codes) != len(sound_codes):
        missing = ", ".join(str(code) for code in sound_codes if code not in sound_names)
        print(f"missing SFXTable ids: {missing}")
    if not args.details_only:
        print("code\tcue name\toccurrences\tfiles\tco-occurring codes\texamples")
        for code in sorted(occurrences):
            rows = occurrences[code]
            files = sorted({row.path for row in rows})
            companions = Counter(c for row in rows for c in row.codes if c != code)
            companion_text = ",".join(f"{c}:{n}" for c, n in companions.most_common(5)) or "-"
            examples = "; ".join(files[:args.examples])
            print(f"{fmt_code(code)}\t{sound_names.get(code, '-')}\t{len(rows)}\t{len(files)}\t{companion_text}\t{examples}")

    for code in args.code or []:
        cue = sound_names.get(code)
        print(f"\n{fmt_code(code)}{f' = {cue}' if cue else ''} occurrences")
        for row in occurrences.get(code, []):
            ratio = row.frame / row.end_frame if row.end_frame else 0.0
            codes = ",".join(str(c) for c in row.codes)
            print(f"{row.path}\tframe {row.frame}/{row.end_frame} ({ratio:.3f})\t[{codes}]")


if __name__ == "__main__":
    main()
