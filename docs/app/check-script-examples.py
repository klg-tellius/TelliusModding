"""Compile/serialize/re-read authoring examples, without editing game files."""
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "App"))
from fe_modding.formats.cmb import compile_source, decompile, read_cmb, write_cmb


def main():
    total = 0
    for filename in ["script-tutorial.md", "script-call-reference.md"]:
        total += check_file(Path(__file__).with_name(filename))
    print(f"Verified {total} examples. Asset validity and in-game behavior require separate checks.")


def check_file(path):
    source = path.read_text(encoding="utf-8")
    blocks = list(re.finditer(r"^```fe9s\n(.*?)^```", source, re.M | re.S))
    assert blocks, "No examples found"
    for number, match in enumerate(blocks, 1):
        line = source.count("\n", 0, match.start()) + 1
        result = compile_source(match.group(1))
        assert not result.warnings, f"Example {number}, line {line}: {result.warnings}"
        data = write_cmb(result.script)
        parsed = read_cmb(data)
        assert write_cmb(parsed) == data, f"Example {number}: binary round-trip"
        text, _ = decompile(parsed)
        rebuilt = compile_source(text, base=parsed)
        assert write_cmb(rebuilt.script) == data, f"Example {number}: source round-trip"
        print(f"{path.name} example {number} (line {line}): compile and round-trips OK")
    return len(blocks)


if __name__ == "__main__":
    main()
